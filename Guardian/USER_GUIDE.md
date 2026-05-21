# OmniPanopticon v5.3 - Enhanced User Guide

## Overview
OmniPanopticon is an ethical network security monitoring tool designed for home lab research. It creates a managed access point with:
- Transparent MITM proxy for traffic analysis
- JA3 fingerprinting for client identification
- DNS exfiltration detection
- Honeypot service
- Captive portal with consent management
- Real-time monitoring dashboard
- Device isolation capabilities

## Installation & First Run

### Prerequisites
- Root access / sudo
- Linux system with at least 2 wireless interfaces (or one that supports AP mode and another for WAN)
- Internet connection for package installation

### Quick Start
```bash
sudo ./Guardian.py
```

The script will:
1. Prompt you to select WAN and AP interfaces
2. Install required system packages
3. Generate CA certificates
4. Configure network and firewall
5. Start all services

### Using Configuration File
Create a JSON config file (e.g., `/etc/panopticon/config.json`):
```json
{
  "AP_SSID": "MyNetwork",
  "AP_PASS": "SecurePassword123",
  "WAN_IFACE": "eth0",
  "WIFI_IFACE": "wlan0",
  "DASHBOARD_PORT": 5000,
  "wireguard": {
    "interface": "wg0",
    "private_key": "<your-private-key>",
    "address": "10.0.0.1/24",
    "peer_public_key": "<peer-public-key>",
    "endpoint": "example.com:51820"
  }
}
```

Run with:
```bash
sudo ./Guardian.py --config /etc/panopticon/config.json
```

### Command-Line Options
```
--config PATH     JSON configuration file
--ssid NAME       Override AP SSID
--pass PASSWORD   Override AP password
--decrypt         Decrypt captured login data (requires key)
--isolate MAC     Isolate device by MAC address
--unban MAC       Remove device from isolation
```

## Dashboard Access

After startup, access the dashboard at:
- http://192.168.10.1:5000/

### Dashboard Features
- **Real-time statistics**: Device counts, uptime, network info
- **Device management**: View all detected devices, consent status, isolation state
- **Live alerts**: Real-time security notifications via SocketIO
- **Device control**: Isolate/unban devices with one click
- **REST API**: JSON endpoints for integration
- **Metrics endpoint**: Prometheus-compatible metrics at `/metrics`

### API Endpoints
- `GET /api/stats` - Network statistics JSON
- `GET /api/devices` - All devices JSON
- `GET /api/alerts` - Recent alerts JSON
- `GET /metrics` - Prometheus metrics

### Alert Types
The dashboard displays alerts for:
- New device connections
- Login credentials captured
- Honeypot triggers
- Beaconing behavior
- DNS exfiltration attempts
- Internal network access
- Certificate pinning detection
- Device isolation/unban events

## Consent Management

### Captive Portal
Unauthenticated users are redirected to:
http://192.168.10.1:5000/consent

They must enter name/email and agree to monitoring to gain full access.

### Consent Files
- Consent records: `/etc/panopticon/consent.json`
- Device tracking: `/etc/panopticon/devices.json`

## Security Features

### MITM Inspection
- JA3 fingerprinting for TLS client identification
- Login credential capture (encrypted at rest)
- DNS entropy analysis for exfiltration detection
- Beaconing detection (rapid repeated connections)
- Certificate pinning detection

### Data Protection
- Login data encrypted with AES-256-GCM using key at `/etc/panopticon/login_encryption.key`
- Logging with compressed rotation (10MB per file, 5 backups)
- Syslog integration for audit events

### Device Isolation
Block malicious or suspicious devices via:
- Dashboard UI: Click "Isolate" next to device
- CLI: `./Guardian.py --isolate <MAC>`
- CLI unban: `./Guardian.py --unban <MAC>`

Isolated devices can access the network but cannot forward traffic (man-in-the-middle still works).

## Log Files

Logs are stored in `/var/log/panopticon/`:
- `activities.log` - All HTTP activity
- `logins.log` - Encrypted captured credentials
- `events.log` - Security events (new devices, alerts)
- `audit.log` - Audit trail (also sent to syslog)

## Troubleshooting

### AP Not Showing on Phone/Device

If the SSID is not visible in your WiFi scan:

#### Quick Diagnostic
Run the included diagnostic script:
```bash
sudo ./diagnostic.sh
```

This will check:
- Interface AP mode support
- hostapd status and configuration
- NetworkManager conflicts
- Regulatory domain settings
- RF kill switches

#### Common Causes & Fixes

**1. NetworkManager Conflict** (Most Common)
NetworkManager often takes control of the WiFi interface, preventing hostapd from using it.

**Fix**: Stop NetworkManager or configure it to ignore the AP interface:
```bash
# Stop NM temporarily
sudo systemctl stop NetworkManager

# Or permanently: Guardian.py creates config in /etc/NetworkManager/conf.d/
sudo ./Guardian.py
```

**2. Interface Doesn't Support AP Mode**
Not all WiFi adapters can act as Access Points.

**Check**:
```bash
iw list | grep -A10 "Supported interface modes"
```
Look for `* AP` in the output.

**Fix**: Use a WiFi adapter that supports AP mode (most Intel, Atheros, Ralink, Realtek with firmware).

**3. Regulatory Domain Blocking Channel**
Your regulatory domain may block channel 6 (default) or restrict power.

**Fix**: Set correct country code:
```bash
# Check current
iw reg get

# Set to US (or your country)
sudo iw reg set US

# Make persistent (Guardian.py does this automatically)
echo "REGDOMAIN=US" | sudo tee /etc/default/crda
```

Also, edit `/etc/panopticon/config.json` and set `"AP_COUNTRY": "US"` (or your 2-letter code).

**4. Wrong Interface Selected**
You may have selected the wrong interface during setup.

**Fix**: Reconfigure:
```bash
sudo ./Guardian.py
# When prompted, select correct WAN and WiFi interfaces
```

Or edit `/etc/panopticon/config.json` manually with correct interface names (e.g., "wlan0", "wlp2s0").

**5. Channel Issues**
Channel 6 may be DFS (Dynamic Frequency Selection) in your region, requiring radar detection which hostapd may not handle.

**Fix**: Change channel in config.json:
```json
{
  "AP_CHANNEL": 1
}
```
Use channels 1, 6, or 11 for 2.4GHz (non-DFS).

**6. Power Management / RF Kill**
WiFi may be soft or hard blocked.

**Fix**:
```bash
# Check rfkill
rfkill list

# Unblock all
sudo rfkill unblock all

# Disable power save on interface
sudo iw dev wlan0 set power_save off
```

**7. hostapd Configuration Error**
Syntax errors in hostapd.conf can cause silent failures.

**Check**:
```bash
sudo hostapd -t /etc/hostapd/hostapd.conf
```
This tests config without daemonizing.

**Fix**: Check `/etc/hostapd/hostapd.conf` for errors. Ensure `AP_SSID` and `AP_PASS` have no special characters that break config.

**8. hostapd Service Not Starting**
Service may fail to start due to missing drivers or permissions.

**Check**:
```bash
sudo systemctl status hostapd
sudo journalctl -u hostapd -n 50 --no-pager
```

**Fix**: Look for error messages like "Could not configure driver interface", "nl80211 not found", or "Permission denied".

**9. Interface Already in Use**
Interface may be managed by wpa_supplicant or another process.

**Fix**: Bring interface down before starting:
```bash
sudo ip link set wlan0 down
sudo ./Guardian.py
```

Guardian.py's `disable_networkmanager()` function handles this, but if NM is stubborn, manually stop it:
```bash
sudo systemctl stop NetworkManager
sudo rm /etc/NetworkManager/conf.d/99-unmanaged-*.conf 2>/dev/null
```

**10. Driver/Firmware Missing**
Some WiFi chipsets need proprietary firmware.

**Check**:
```bash
dmesg | grep -i firmware
dmesg | grep -i wlan
```

**Fix**: Install firmware:
```bash
# Realtek
sudo apt install firmware-realtek

# Broadcom
sudo apt install firmware-b43-installer

# Intel (usually built-in)
sudo apt install firmware-iwlwifi
```

Then reboot.

#### Step-by-Step Recovery

If AP still not visible after running Guardian.py:

1. **Stop everything**:
```bash
sudo ./Guardian.py --stop 2>/dev/null || true
sudo systemctl stop hostapd dnsmasq 2>/dev/null
sudo pkill -9 mitmproxy 2>/dev/null
sudo pkill -9 captive_portal 2>/dev/null
```

2. **Clean up network state**:
```bash
sudo iptables -F
sudo iptables -t nat -F
sudo ip addr flush dev wlan0
```

3. **Disable NetworkManager**:
```bash
sudo systemctl stop NetworkManager
sudo ./Guardian.py  # This will create unmanaged config
```

4. **Check interface manually**:
```bash
iw dev wlan0 info
# Should show nothing or "type managed"
```

5. **Test hostapd manually** (foreground, verbose):
```bash
sudo hostapd -dd /etc/hostapd/hostapd.conf
```
Watch output for errors. Press Ctrl+C to exit.

6. **If hostapd works manually but not as service**:
```bash
sudo systemctl restart hostapd
sudo journalctl -u hostapd -f  # Follow logs
```

7. **Verify AP broadcasting** (from another device or second interface):
```bash
# If you have eth0 and wlan0:
sudo iw dev eth0 scan passive | grep -A5 "YourSSID"
```

Or use `wash` (aircrack-ng suite) to detect APs:
```bash
sudo apt install aircrack-ng
sudo wash -i eth0
```

#### Still Not Working?

- Try a different channel (1, 6, 11) in config.json
- Try different hw_mode: "g" (2.4GHz), "a" (5GHz if supported)
- Test with a simple hostapd config:
```bash
sudo bash -c 'cat > /tmp/test.conf <<EOF
interface=wlan0
driver=nl80211
ssid=TestAP
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=test1234
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF'
sudo hostapd -dd /tmp/test.conf
```
- Check dmesg for driver errors: `dmesg | tail -50`
- Search online for your WiFi adapter model + "AP mode Linux"

### Dashboard Not Accessible

1. Verify dashboard is running:
```bash
ps aux | grep Guardian
```

2. Check dashboard port:
```bash
sudo netstat -tlnp | grep 5000
```

3. Access directly from AP client:
```bash
# From a device connected to the AP:
curl http://192.168.10.1:5000/api/stats
```

4. If connection refused, dashboard thread may have crashed. Check logs via `journalctl` or restart Guardian.

### No Devices Showing in Dashboard

1. **MITM proxy not running**:
```bash
ps aux | grep mitmproxy
```

2. **CA certificate not installed** on client device - required for HTTPS interception:
   - Visit http://192.168.10.1:5000/cert on client
   - Download and install `/etc/panopticon/rootCA.pem`
   - Trust the certificate in system settings

3. **Client not using DNS** - Ensure client gets DNS 192.168.10.1 from DHCP or set manually.

4. **Check device file**:
```bash
cat /etc/panopticon/devices.json
```

### Hostapd Fails with "nl80211 not found"

Your driver doesn't support nl80211. Try:
- Update kernel/firmware
- Use `driver=hostap` (deprecated) if your card supports it
- Different WiFi adapter

### Hostapd Fails with "Permission denied"

Most likely rfkill block or interface down:
```bash
sudo rfkill unblock all
sudo ip link set wlan0 up
```

Or NetworkManager conflict - stop NM.

### DNS Not Working (Clients can't browse)

1. Check dnsmasq:
```bash
sudo systemctl status dnsmasq
sudo journalctl -u dnsmasq -n 30
```

2. Verify DNS port 53 listening:
```bash
sudo netstat -tlnp | grep :53
```

3. Test DNS from client:
```bash
nslookup google.com 192.168.10.1
```

4. Check `/etc/dnsmasq.conf` has `interface=wlan0`

### Captive Portal Redirect Not Working

1. Check iptables rules:
```bash
sudo iptables -t nat -L PREROUTING -n -v
```
Should see ports 80/443 redirecting to 8080.

2. Verify mitmproxy is running and listening on 8080:
```bash
sudo netstat -tlnp | grep 8080
```

3. Check client DNS - must be 192.168.10.1 for DNS redirect to work.

## Advanced Troubleshooting

### Enable Debug Mode

Add `--debug` flag (future) or manually:
```bash
# Run mitmproxy in foreground with verbose logging
sudo mitmproxy --mode transparent --showhost -s /etc/panopticon/guardian_addon.py --set confdir=/etc/panopticon --set console_eventlog_verbosity=debug

# In another terminal, tail logs:
sudo tail -f /var/log/panopticon/events.log
```

### Check for Packet Drops
```bash
# View iptables packet counters
sudo iptables -L -v -n | head -20
```

High drop counts indicate misconfiguration or insufficient resources.

### Monitor Airwaves
```bash
# See all WiFi networks in range
sudo iw dev wlan0 scan | grep "SSID\|freq\|signal"

# Check channel utilization
sudo iw dev wlan0 survey dump
```

### Collect Debug Bundle
```bash
sudo ./Guardian.py --debug > debug.log 2>&1
# Then send debug.log for analysis
```

## Getting Help

1. Run `./diagnostic.sh` and include output
2. Check `/var/log/panopticon/` for relevant logs
3. Verify hardware compatibility (WiFi adapter AP support)
4. Ensure all packages installed: `sudo apt install hostapd dnsmasq iptables-persistent mitmproxy`

### Dashboard Not Accessible
1. Verify dashboard is running: `ps aux | grep Guardian`
2. Check firewall rules: `iptables -L`
3. Ensure port 5000 is listening: `netstat -tlnp | grep 5000`

### No Devices Showing
1. Check MITM proxy is running: `ps aux | grep mitmproxy`
2. Verify CA certificate installed on client devices
3. Check device tracking file: `cat /etc/panopticon/devices.json`

### Certificate Issues
- CA certificate: `/etc/panopticon/rootCA.pem`
- Install on client devices via captive portal or manual download
- Mitmproxy config directory: `/etc/panopticon/`

## Advanced Configuration

### WireGuard VPN Backhaul
Add to config.json:
```json
{
  "wireguard": {
    "interface": "wg0",
    "private_key": "<base64-private-key>",
    "address": "10.0.0.1/24",
    "dns": "1.1.1.1",
    "peer_public_key": "<base64-public-key>",
    "endpoint": "vpn.example.com:51820"
  }
}
```

### Honeypot
Honeypot runs on port 9999. Access attempts are logged as security events.
Customize with `/etc/panopticon/honeypot.py`.

### Custom Detection Rules
Modify the MITM addon (`/etc/panopticon/guardian_addon.py`) to add custom detection logic.
Reload mitmproxy to apply changes.

## Maintenance

### View Captured Data
Decrypt logins:
```bash
sudo ./Guardian.py --decrypt
```

### Backup Configuration
```bash
sudo tar -czf panopticon-backup-$(date +%Y%m%d).tar.gz /etc/panopticon /var/log/panopticon
```

### Restore Configuration
```bash
sudo tar -xzf backup.tar.gz -C /
sudo systemctl restart hostapd dnsmasq
```

### Update CA Certificate
Regenerate:
```bash
sudo rm /etc/panopticon/rootCA.* /etc/panopticon/login_encryption.key
sudo ./Guardian.py
```

## Ethics & Legal

**USE ONLY ON YOUR OWN NETWORK WITH EXPLICIT CONSENT OF ALL USERS.**

This tool is for security research and education. Unauthorized interception of communications is illegal in many jurisdictions. Always:
- Obtain informed consent from all users
- Post clear notices about monitoring
- Protect collected data
- Comply with applicable laws (GDPR, CCPA, etc.)
- Delete data when no longer needed

## Support

For issues, feature requests, or contributions:
- Check logs in `/var/log/panopticon/`
- Review this guide
- Ensure all dependencies are installed

---

**Version**: 5.3 Enhanced
**Author**: Rebel Genius (with love for Pliny)
**License**: For research use only
