# OmniPanopticon v5.3 – Self-Healing Ethical Network Fortress

![Status](https://img.shields.io/badge/status-enhanced-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-research%20only-yellow)

**A comprehensive network security monitoring tool for home lab research.**

## Features
- Automatic Access Point setup with self-healing
- Transparent MITM proxy with JA3 fingerprinting
- DNS exfiltration detection
- Honeypot service
- Captive portal with consent management
- Real-time dashboard with SocketIO
- Device isolation capabilities
- WireGuard VPN backhaul support
- Encrypted credential capture
- Prometheus-compatible metrics

## Quick Start
```bash
sudo ./Guardian.py
```

Select your WAN and WiFi interfaces when prompted.

## Dashboard
Access at: http://192.168.10.1:5000/

View devices, manage isolation, see live alerts.

```bash
# API
curl http://192.168.10.1:5000/api/stats
curl http://192.168.10.1:5000/api/devices
curl http://192.168.10.1:5000/metrics
```

## Files
- `Guardian.py` – Main script
- `example_config.json` – Sample configuration
- `USER_GUIDE.md` – Full documentation
- `QUICK_REFERENCE.md` – Command cheat sheet

## Important
**Use ONLY on your own network with explicit consent of all users.**

This tool is for educational and research purposes. Unauthorized interception of communications is illegal.

## Documentation
- [User Guide](USER_GUIDE.md) – Comprehensive walkthrough
- [Quick Reference](QUICK_REFERENCE.md) – Common commands
- [Implementation Report](IMPLEMENTATION_REPORT.md) – Technical details

## Requirements
- Debian/Ubuntu Linux
- Root privileges
- Two wireless interfaces (or one supporting AP + WAN)
- Internet connection for initial package install

**Author**: Rebel Genius (enhanced by Kilo)
**Version**: 5.3 Enhanced
# Guardian
