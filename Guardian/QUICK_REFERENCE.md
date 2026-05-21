# OmniPanopticon Quick Reference

## Startup
```bash
# Auto-detect interfaces (interactive)
sudo ./Guardian.py

# With config file
sudo ./Guardian.py --config /etc/panopticon/config.json

# Override SSID/password on command line
sudo ./Guardian.py --ssid "MyAP" --pass "Secret123"
```

## URLs
- Dashboard: http://192.168.10.1:5000/
- Consent: http://192.168.10.1:5000/consent
- API Stats: http://192.168.10.1:5000/api/stats
- Metrics: http://192.168.10.1:5000/metrics

## Management
```bash
# Isolate device
sudo ./Guardian.py --isolate AA:BB:CC:DD:EE:FF

# Unban device
sudo ./Guardian.py --unban AA:BB:CC:DD:EE:FF

# Decrypt captured logins (requires key)
sudo ./Guardian.py --decrypt

# View running services
ps aux | grep -E "(hostapd|dnsmasq|mitmproxy|captive|honeypot|Guardian)"

# Stop everything manually
sudo systemctl stop hostapd dnsmasq
sudo pkill -f mitmproxy
sudo pkill -f captive_portal
sudo pkill -f honeypot
```

## File Locations
- Config: `/etc/panopticon/config.json`
- CA cert: `/etc/panopticon/rootCA.pem`
- Encryption key: `/etc/panopticon/login_encryption.key`
- Devices: `/etc/panopticon/devices.json`
- Consent: `/etc/panopticon/consent.json`
- Logs: `/var/log/panopticon/`

## Useful Commands
```bash
# Watch activity log
sudo tail -f /var/log/panopticon/activities.log

# Decrypt logins on the fly
sudo ./Guardian.py --decrypt | less

# Check AP mode
iw dev wlan0 info | grep type

# Scan for AP
iw dev eth0 scan | grep -A5 "OmniNet"

# View iptables rules
sudo iptables -L -v -n

# Flush iptables
sudo iptables -F
sudo iptables -t nat -F
```

## Troubleshooting
```bash
# Run full diagnostic
sudo ./diagnostic.sh

# No wireless interfaces detected?
iw dev

# Interface not in AP mode?
iw list | grep -A10 "Supported interface modes"

# hostapd failing?
sudo journalctl -u hostapd -n 50

# Test hostapd config syntax
sudo hostapd -t /etc/hostapd/hostapd.conf

# Run hostapd manually (debug)
sudo hostapd -dd /etc/hostapd/hostapd.conf

# mitmproxy not running?
sudo pkill -9 mitmproxy; sudo ./Guardian.py

# Dashboard not loading?
curl http://192.168.10.1:5000/api/stats
sudo netstat -tlnp | grep 5000

# Reset everything
sudo ./Guardian.py --stop 2>/dev/null || true
sudo systemctl stop hostapd dnsmasq
sudo rm -f /etc/panopticon/devices.json /etc/panopticon/consent.json
sudo iptables -F; iptables -t nat -F
sudo systemctl restart networking

# Reconfigure interfaces
sudo ./Guardian.py  # Choose different interfaces

# Disable NetworkManager (if conflict)
sudo systemctl stop NetworkManager
sudo rm -f /etc/NetworkManager/conf.d/99-unmanaged-*.conf
```

## Log Analysis
```bash
# Count requests per IP
awk '{print $3}' /var/log/panopticon/activities.log | sort | uniq -c | sort -nr

# Find login attempts
grep -i "username\|password" /var/log/panopticon/activities.log

# Show recent alerts
tail -50 /var/log/panopticon/events.log | grep -E "🍯|⏱️|🧬|🔒|📌"

# Extract unique domains
awk '{print $5}' /var/log/panopticon/activities.log | sed 's|.*://||' | cut -d/ -f1 | sort | uniq

# High entropy domains (potential exfil)
grep "DNS EXFIL" /var/log/panopticon/events.log
```

## Network
- AP subnet: 192.168.10.0/24
- AP IP: 192.168.10.1
- DHCP range: 192.168.10.50 - 192.168.10.150
- DNAT: Port 80/443 -> mitmproxy (8080)

## Security Notes
- Always obtain consent before monitoring
- Protect `/etc/panopticon/` (600 permissions)
- Encrypted key stored separately from logs
- Auto-flushes iptables on exit
- Clear browser data after testing (HSTS pinning may break)

## Tips for Home Lab
1. Use a secondary WiFi adapter for AP mode
2. Connect WAN to your home router (eth0)
3. Set client device DNS to 192.168.10.1 for DNS capture
4. Install CA certificate on test devices
5. Monitor alerts in real-time via dashboard
6. Test isolation before actual testing
7. Rotate AP password periodically
8. Backup `/etc/panopticon/` regularly

---

**Version**: 5.3 Enhanced
**Last Updated**: 2026-05-10
