# AP Not Broadcasting? Quick Fix Guide

## Run Diagnostic First
```bash
sudo ./diagnostic.sh
```

This will identify the most common issues.

## Most Common Fixes (90% of cases)

### 1. NetworkManager Conflict
```bash
sudo systemctl stop NetworkManager
sudo ./Guardian.py  # will create unmanaged config
```

### 2. Set Regulatory Domain
```bash
sudo iw reg set US
# Or your country code
```

Also set in config: `"AP_COUNTRY": "US"`

### 3. Change Channel
Edit `/etc/panopticon/config.json`:
```json
{
  "AP_CHANNEL": 1
}
```
Use 1, 6, or 11 (non-DFS channels).

### 4. Unblock WiFi
```bash
sudo rfkill unblock all
sudo iw dev wlan0 set power_save off
```

### 5. Reinstall firmware (Realtek)
```bash
sudo apt update
sudo apt install firmware-realtek
sudo reboot
```

### 6. Manual hostapd test (debug)
```bash
sudo hostapd -t /etc/hostapd/hostapd.conf  # Check syntax
sudo hostapd -dd /etc/hostapd/hostapd.conf  # Run in foreground with debug output
```

Watch the output for errors. Press Ctrl+C to exit.

## Step-by-Step Recovery

```bash
# 1. Stop everything
sudo pkill -9 mitmproxy 2>/dev/null
sudo systemctl stop hostapd dnsmasq 2>/dev/null

# 2. Clean interfaces
sudo ip addr flush dev wlan0 2>/dev/null
sudo ip link set wlan0 down

# 3. Disable NetworkManager
sudo systemctl stop NetworkManager

# 4. Start Guardian clean
sudo ./Guardian.py
```

## Check AP Is Broadcasting

From another computer/phone: Scan WiFi networks for SSID "OmniNet" (or your configured name).

From another interface (if available):
```bash
sudo iw dev eth0 scan passive | grep -A5 "SSID"
```

## Still Not Working?

1. Check hostapd logs:
```bash
sudo journalctl -u hostapd -n 50 --no-pager
```

2. Check interface mode:
```bash
iw dev wlan0 info | grep type
```
Should show `type AP` when hostapd is running.

3. Verify AP is in air:
```bash
sudo iw dev wlan0 survey dump  # Shows channel utilization
```

4. Check dmesg for driver errors:
```bash
dmesg | tail -30
```

5. Try different hw_mode in config:
```json
{
  "AP_HW_MODE": "a"  # for 5GHz (if adapter supports)
}
```

## WiFi Adapter Compatibility

**Known Good**: Intel (iwlwifi), Atheros (ath9k), Ralink (rt2800usb)

**Problematic**: Some Realtek chipsets may need `firmware-realtek` package.

Check your adapter:
```bash
lspci -k | grep -A3 -i network
# or for USB
lsusb
```

Search online: `<adapter model> linux AP mode support`

## What Guardian Does Now

When you run `sudo ./Guardian.py`:

1. Disables NetworkManager on the AP interface
2. Sets regulatory domain (country code)
3. Brings interface up and assigns IP 192.168.10.1
4. Writes improved hostapd.conf with country_code and ctrl_interface
5. Tests hostapd config syntax
6. Starts hostapd service and verifies AP-ENABLED
7. Starts dnsmasq (DHCP/DNS)
8. Starts mitmproxy, captive portal, honeypot, dashboard
9. Verifies SSID is broadcasting via scan
10. Prints warnings if anything fails

## File Locations

- Config: `/etc/panopticon/config.json`
- hostapd config: `/etc/hostapd/hostapd.conf`
- dnsmasq config: `/etc/dnsmasq.conf`
- NM unmanaged config: `/etc/NetworkManager/conf.d/99-unmanaged-<iface>.conf`
- Logs: `/var/log/panopticon/`
- hostapd logs: `journalctl -u hostapd`

## Need More Help?

1. Run `sudo ./diagnostic.sh` and save output
2. Check `USER_GUIDE.md` section "AP Not Showing on Phone/Device"
3. Verify WiFi adapter supports AP mode (`iw list`)
4. Try manual hostapd test to see error messages
5. Search for your adapter model + "hostapd" + "Linux"

Good luck! 🚀
