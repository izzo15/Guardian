# OmniPanopticon v5.3 - Complete Change Log

## Version History
- **v5.3 Original** - Base network monitoring with MITM, dashboard, consent
- **v5.3 Enhanced** - Current version with AP fixes, config improvements, real-time alerts

## Summary of All Changes

### 1. Configuration System Overhaul

#### Added Configuration Options
- `AP_CHANNEL` (default: 6) - WiFi channel number
- `AP_COUNTRY` (default: "US") - Regulatory country code
- `AP_HW_MODE` (default: "g") - Hardware mode: "g" (2.4GHz), "a" (5GHz), "bg" (dual-band)
- All AP settings now configurable via JSON config file

#### New Functions
- `load_config(config_path)` - Loads JSON config with safe defaults
- `save_config(config_path, config)` - Saves config with directory creation
- Config auto-saved after first run for persistent interface selection

#### CLI Arguments
- `--ssid` - Override AP SSID
- `--pass` - Override AP password
- `--config` - Specify config file path

**Files touched**: Guardian.py lines 34-49, 51-84, 1225-1424, 1477-1487

---

### 2. AP Startup Reliability Fixes

**Problem**: AP not broadcasting, SSID invisible to phones.

#### Root Causes Addressed
1. **NetworkManager conflict** - NM grabs interface, prevents hostapd
   - **Fix**: `disable_networkmanager()` creates NM config to ignore AP interface
   
2. **Missing regulatory domain** - hostapd refuses without country code
   - **Fix**: Auto-set via `iw reg set <country>`, persist to `/etc/default/crda`
   
3. **Interface validation missing** - script proceeds even if interface incompatible
   - **Fix**: `validate_interface()` checks existence, rfkill, AP support
   
4. **No hostapd config validation** - errors only discovered at runtime
   - **Fix**: `hostapd -t /etc/hostapd/hostapd.conf` syntax check before start
   
5. **Poor error reporting** - hostapd failures silent
   - **Fix**: `start_hostapd()` shows logs on failure, returns clear status
   
6. **Hardcoded channel 6** - may be DFS/blocked
   - **Fix**: Configurable `AP_CHANNEL`, can set to 1, 6, or 11

#### New/Modified Functions
- `disable_networkmanager(iface)` - Prevents NM interference
- `validate_interface(iface)` - Checks AP readiness
- `find_best_channel(iface)` - Placeholder for auto-channel selection (currently returns configured channel)
- `configure_network()` - Enhanced with NM disable, regulatory domain, improved hostapd config
- `start_hostapd()` - New separate function with validation
- `verify_and_heal_ap()` - Completely rewritten with better diagnostics

**Files touched**: Guardian.py lines 166-246, 615-846, 848-931

---

### 3. MITM Addon Enhancements

#### JA3 Fingerprinting Fix
**Before**: Hardcoded TLS version "771" for all JA3 hashes.
**After**: Parses Client Hello to extract actual TLS version integer.

**Impact**: Accurate JA3 fingerprints now reflect TLS 1.0, 1.2, 1.3 etc.

#### Device Tracking
**Added**: Shared JSON file `/etc/panopticon/devices.json`
- Tracks every MAC address seen
- Records: IP, name, email (if consented), first_seen, last_seen, consented flag
- Updated on each request from new device
- Dashboard reads this to show all devices

#### Configuration Loading
**Added**: Addon now reads `/etc/panopticon/config.json` to get AP_IP and DASHBOARD_PORT
- No more hardcoded `192.168.10.1:5000` in redirects
- Works with any AP_IP configured

#### Alert Queue
**Added**: File-based alert queue `/etc/panopticon/alerts.json`
- MITM addon writes JSON lines for important events
- Dashboard monitors file and pushes alerts via SocketIO
- Automatic rotation (max 1000 lines)

#### Alertable Events
- New device detected
- Login credentials captured (encrypted)
- Honeypot triggered
- Beaconing detected (5+ requests to same domain in 60s)
- DNS exfiltration (high entropy domain)
- Certificate pinning detected

#### Key Loading Robustness
**Before**: Crash if encryption key missing.
**After**: Try/except with error log, continues with ENCRYPTION_KEY=None (login capture disabled gracefully).

**Files touched**: Guardian.py lines 207-688 (MITM_ADDON string)

---

### 4. Dashboard Overhaul

#### UI/UX
- Dark theme with neon green (hacker aesthetic)
- Responsive grid layout (CSS Grid)
- Color-coded rows: green=consented, orange=pending, red=isolated
- Real-time status panel: uptime, counts, SSID, IP
- Alert feed with SocketIO push (no manual refresh needed)
- Auto-refresh every 30 seconds as fallback

#### API Endpoints
- `GET /api/stats` → JSON with total_devices, consented, isolated, uptime, ap_ssid, ap_ip
- `GET /api/devices` → Full device dictionary
- `GET /api/alerts` → Recent alerts (last 20)
- `GET /metrics` → Prometheus-compatible text format

#### Device Management
- **All devices table**: Shows every MAC, IP, name, email, consent status, first seen
- **Actions**: Isolate/unban buttons directly from table
- **Stats summary**: Total, consented, isolated counters

#### Data Persistence
- Loads from `/etc/panopticon/consent.json` at startup
- Loads from `/etc/panopticon/devices.json` at startup
- Merges consent records into device records
- Saves both on consent POST
- Directory auto-creation (`os.makedirs(..., exist_ok=True)`) prevents errors

#### Alert Integration
- `add_alert()` function broadcasts via SocketIO
- Background thread `monitor_alerts()` tails alerts file
- New lines from MITM addon appear instantly in dashboard

**Files touched**: Guardian.py lines 913-1270, 1340-1424

---

### 5. Service Management Improvements

#### PID Tracking
- Global `service_pids = []` list
- `start_services()` appends PIDs for: mitmproxy, captive_portal, honeypot
- `cleanup()` iterates PIDs and sends SIGTERM
- Prevents orphan processes on shutdown

**Files touched**: Guardian.py lines 87-137, 889-931

---

### 6. Error Handling & Robustness

#### Run Function
**Before**: Always exited on CalledProcessError even when `check=False`
**After**: Returns exception object for non-fatal errors

**Impact**: Script continues on non-critical failures.

#### Directory Creation
All file writes now ensure parent directory exists via `os.makedirs(..., exist_ok=True)`

#### Permission Error Handling
`--decrypt` mode now catches PermissionError explicitly.

**Files touched**: Guardian.py lines 86-95, 964-979, 1014-1015

---

### 7. Documentation

#### New Files
- `diagnostic.sh` - Bash script to diagnose AP issues (executable)
- `AP_TROUBLESHOOTING.md` - Quick fix guide (this summary)
- Updated `USER_GUIDE.md` (added 100+ lines of AP troubleshooting)
- Updated `QUICK_REFERENCE.md` (added diagnostic commands)
- Updated `IMPLEMENTATION_REPORT.md` (detailed tech summary)

#### Updated Files
- `example_config.json` - Added AP_CHANNEL, AP_COUNTRY, AP_HW_MODE
- `test_config.json` - Same updates

---

## Configuration File Format

```json
{
  "AP_SSID": "MyNetwork",
  "AP_PASS": "SecurePassword123",
  "AP_IP": "192.168.10.1",
  "AP_CHANNEL": 6,
  "AP_COUNTRY": "US",
  "AP_HW_MODE": "g",
  "AP_DHCP_START": "192.168.10.50",
  "AP_DHCP_END": "192.168.10.150",
  "WAN_IFACE": "eth0",
  "WIFI_IFACE": "wlan0",
  "WIREGUARD_IFACE": "",
  "DASHBOARD_PORT": 5000,
  "DASHBOARD_USER": "admin",
  "DASHBOARD_PASS": "admin",
  "wireguard": null
}
```

---

## New File Structure

```
 Guardian/
├── Guardian.py                     (main script, ~1500 lines)
├── diagnostic.sh                   (new, executable AP troubleshooter)
├── example_config.json             (updated with new options)
├── test_config.json                (updated)
├── README.md                       (project overview)
├── USER_GUIDE.md                   (comprehensive manual)
├── QUICK_REFERENCE.md              (cheat sheet)
├── IMPLEMENTATION_REPORT.md        (technical details)
├── AP_TROUBLESHOOTING.md           (quick AP fixes - NEW)
└── __pycache__/                    (compiled Python)
```

---

## Testing Checklist

After running `sudo ./Guardian.py`:

- [ ] hostapd service starts (check `systemctl status hostapd`)
- [ ] Interface in AP mode (`iw dev wlan0 info` shows `type AP`)
- [ ] AP-ENABLED in logs (`journalctl -u hostapd | grep AP-ENABLED`)
- [ ] SSID visible on phone/computer WiFi scan
- [ ] Client can connect and get IP (check `ip addr` on client)
- [ ] Dashboard accessible: http://192.168.10.1:5000/
- [ ] Dashboard shows device after connection
- [ ] Real-time alerts appear when events trigger (test by visiting HTTP site)
- [ ] Mitmproxy intercepts traffic (check activities.log)
- [ ] `sudo ./Guardian.py --isolate <MAC>` blocks device
- [ ] `sudo ./diagnostic.sh` runs without critical errors

---

## Migration from v5.3 Original

If you have an old installation:

1. Backup your data:
```bash
sudo tar -czf ~/panopticon-backup-$(date +%Y%m%d).tar.gz /etc/panopticon /var/log/panopticon
```

2. Replace `Guardian.py` with new version

3. Run diagnostic: `sudo ./diagnostic.sh`

4. Reconfigure: `sudo ./Guardian.py` (select interfaces again)

5. Restore consent/device data if needed (copy JSON files from backup)

6. Test AP visibility

---

## Known Issues

1. **Alert file race condition** - mitmproxy and dashboard both write to alerts.json without locking. Usually fine for single-user lab but could lose alerts under heavy load. **Workaround**: None yet. **Future**: Implement file locking or switch to SQLite.

2. **Dashboard thread not tracked** - Daemon thread can't be killed by PID. `sudo pkill -9 Guardian` kills parent process but not thread cleanly. **Workaround**: Use `killall python3` if needed. **Future**: Use multiprocessing.

3. **Channel auto-selection not implemented** - `AP_CHANNEL: "auto"` will be future feature. For now use numeric 1/6/11.

---

## Support

If AP still doesn't show:
1. Run `sudo ./diagnostic.sh`
2. Check `USER_GUIDE.md` section "AP Not Showing on Phone/Device"
3. Post error messages from hostapd logs
4. Verify WiFi adapter supports AP mode (`iw list | grep -A10 "Supported interface modes"`)

---

**Last Updated**: 2026-05-10
**Version**: 5.3 Enhanced - AP Reliability Update
**Status**: Production-ready for home lab
