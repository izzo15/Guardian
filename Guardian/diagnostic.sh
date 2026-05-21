#!/bin/bash
# OmniPanopticon AP Diagnostic Script
# Run this if your AP is not showing up on WiFi scans

echo "🔍 OmniPanopticon AP Diagnostic Tool"
echo "======================================"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Function to print section header
section() {
    echo
    echo "📋 $1"
    echo "---"
}

# 1. Check interfaces
section "1. Wireless Interfaces"
iw dev 2>/dev/null | grep -E "Interface|type" || echo "   ⚠️ iw command failed or no wireless interfaces"

echo
echo "Available interfaces:"
ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v lo || echo "   None found"

# 2. Check AP mode support
section "2. AP Mode Support"
iw list 2>/dev/null | grep -A5 "Supported interface modes" | head -10
if iw list 2>/dev/null | grep -q "* AP"; then
    echo "   ✓ AP mode supported"
else
    echo "   ❌ AP mode NOT listed - your WiFi adapter may not support AP mode"
fi

# 3. Check rfkill
section "3. RFKill Status"
rfkill list 2>/dev/null || echo "   ⚠️ rfkill not available"

# 4. Check hostapd
section "4. hostapd Service"
systemctl is-active hostapd 2>/dev/null && echo "   ✓ hostapd is running" || echo "   ❌ hostapd is not running"
systemctl status hostapd 2>/dev/null | head -5

# 5. Check hostapd config
section "5. hostapd Configuration"
if [ -f /etc/hostapd/hostapd.conf ]; then
    echo "   Config file exists:"
    cat /etc/hostapd/hostapd.conf | grep -E "interface|ssid|channel|driver"
else
    echo "   ❌ /etc/hostapd/hostapd.conf not found"
fi

# 6. Test hostapd config syntax
section "6. hostapd Config Syntax Test"
if [ -f /etc/hostapd/hostapd.conf ]; then
    hostapd -t /etc/hostapd/hostapd.conf 2>&1 && echo "   ✓ Config syntax OK" || echo "   ❌ Config syntax error"
fi

# 7. Check interface mode
section "7. Interface Mode"
if [ -n "$WIFI_IFACE" ]; then
    echo "   Interface: $WIFI_IFACE"
    iw dev "$WIFI_IFACE" info 2>/dev/null | grep "type" || echo "   ⚠️ Could not get interface info"
else
    echo "   WIFI_IFACE not set. Run Guardian.py to configure."
fi

# 8. Regulatory domain
section "8. Regulatory Domain"
iw reg get 2>/dev/null | head -5

# 9. Check NetworkManager conflict
section "9. NetworkManager"
systemctl is-active NetworkManager 2>/dev/null && echo "   ⚠️ NetworkManager is active (may conflict)" || echo "   ✓ NetworkManager is inactive"

if [ -d /etc/NetworkManager/conf.d ]; then
    echo "   NM conf.d files:"
    ls -1 /etc/NetworkManager/conf.d/ 2>/dev/null | sed "s/^/     /"
fi

# 10. Check for unmanaged device config
section "10. NM Unmanaged Devices"
if [ -f /etc/NetworkManager/conf.d/99-unmanaged-wlan0.conf ]; then
    echo "   Found unmanaged config:"
    cat /etc/NetworkManager/conf.d/99-unmanaged-wlan0.conf
else
    echo "   No unmanaged config found (NM may manage WiFi interface)"
fi

# 11. Try to determine why AP not visible
section "11. Common Issues"
echo "   If AP not visible:"
echo "   1. Check if interface supports AP: iw list | grep -A10 'Supported interface modes'"
echo "   2. Verify hostapd logs: journalctl -u hostapd -n 50"
echo "   3. Check AP mode: iw dev wlan0 info | grep type"
echo "   4. Try manual start: sudo hostapd -B /etc/hostapd/hostapd.conf"
echo "   5. Check country code: iw reg get (should match AP_COUNTRY in config)"
echo "   6. Try different channel (1, 6, 11) in config.json"
echo "   7. Disable NetworkManager: sudo systemctl stop NetworkManager"
echo "   8. Unblock WiFi: sudo rfkill unblock all"

# 12. Suggest fixes
section "12. Quick Fixes"
echo "   A. Disable NetworkManager for WiFi interface:"
echo "      sudo ./Guardian.py (will create /etc/NetworkManager/conf.d/99-unmanaged-<iface>.conf)"
echo
echo "   B. Force regulatory domain:"
echo "      sudo iw reg set US"
echo
echo "   C. Restart everything:"
echo "      sudo systemctl restart hostapd dnsmasq"
echo
echo "   D. Check if AP is actually broadcasting from another device:"
echo "      sudo iw dev eth0 scan passive | grep -A5 'SSID'"

# 13. Show Guardian config
section "13. Guardian Configuration"
if [ -f /etc/panopticon/config.json ]; then
    echo "   Current config:"
    cat /etc/panopticon/config.json | sed 's/^/     /'
else
    echo "   No config file found at /etc/panopticon/config.json"
fi

echo
echo "✅ Diagnostic complete."
echo
echo "Next steps:"
echo "1. Fix any issues shown above"
echo "2. Re-run: sudo ./Guardian.py"
echo "3. Check your phone for SSID '$AP_SSID' (see config)"
echo "4. If still not visible, check: sudo journalctl -u hostapd -f"
