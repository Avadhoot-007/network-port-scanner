# Network Port Scanner

A simple and efficient network port scanner with a graphical user interface built using Python and Tkinter.

![Python 3.6+](https://img.shields.io/badge/Python-3.6%2B-blue)
![License](https://img.shields.io/badge/License-Educational%20Use-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen)

## ✨ Features

- **TCP Port Scanning** — Scan any IP address or hostname for open ports (1–65535)
- **Service Detection** — Automatically identify 40+ common services running on open ports
- **Multi-threaded Scanning** — Configurable concurrent threads (1–1000) for fast performance
- **Banner Grabbing** — Optional service banner retrieval for version hints
- **Real-time Progress** — Live progress bar with ETA calculation and elapsed time
- **Multiple Export Formats** — Save results as TXT, JSON, or CSV
- **Scan Presets** — Quick access to common port ranges (Well-Known, Registered, All)
- **Scan History** — View and manage previous scans in the same session
- **Cross-platform** — Works on Windows, macOS, and Linux
- **No External Dependencies** — Uses only Python standard library

## 📋 Requirements

- **Python 3.6+**
- **Tkinter** (included with Python on most systems)

### Installing Tkinter

**Windows:**
```bash
# Usually included with Python. If missing, reinstall Python with "tcl/tk and IDLE" checked
```

**macOS:**
```bash
brew install python-tk
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install python3-tk
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install python3-tkinter
```

**Note:** This project uses **only Python standard library**. No pip dependencies required.

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/network-port-scanner.git
cd network-port-scanner
```

2. Verify Python and Tkinter are installed:
```bash
python --version
python -m tkinter
```

3. Run the application:
```bash
python main.py
```

## 📖 Usage

### GUI Application

Run the application:
```bash
python main.py
```

**Tabs:**

**Scanner Tab:**
1. Enter target IP (e.g., `127.0.0.1`) or hostname (e.g., `example.com`)
2. Choose port range or use presets (Well-Known, Registered, All, Common)
3. Configure options:
   - **Timeout:** Socket connection timeout in seconds (default 1.0)
   - **Threads:** Concurrent scanning threads (default 100, max 1000)
   - **Banner Grabbing:** Toggle to retrieve service banners (slower but more info)
4. Click **Start Scan** to begin
5. View open ports in real-time with services
6. Export results (TXT, JSON, or CSV)

**History Tab:**
- View all scans from the current session
- Click a scan to see detailed results
- Useful for comparing multiple scans

### Command-line Usage

You can also use the scanner programmatically:

```python
from scanner.core import PortScanner

# Create a scanner instance
scanner = PortScanner('127.0.0.1', 1, 1024, timeout=1.0, threads=100)

# Run the scan
results = scanner.scan()

# Process results
for port_info in results:
    print(f"Port {port_info['port']}: {port_info['service']}")
```

## 🔌 Supported Services

The scanner detects 40+ common services. Here are some key ones:

| Port | Service | Port | Service |
|------|---------|------|---------|
| 21 | FTP | 3306 | MySQL |
| 22 | SSH | 3389 | RDP (Remote Desktop) |
| 23 | Telnet | 5432 | PostgreSQL |
| 25 | SMTP | 5900 | VNC |
| 53 | DNS | 6379 | Redis |
| 80 | HTTP | 8080 | HTTP-Alt |
| 110 | POP3 | 8443 | HTTPS-Alt |
| 143 | IMAP | 27017 | MongoDB |
| 443 | HTTPS | 9200 | Elasticsearch |
| 445 | SMB |  |  |

Full list available in `scanner/core.py` → `ServiceMap.SERVICES`

## 📁 Project Structure

```
network-port-scanner/
├── scanner/
│   ├── __init__.py           # Package initialization
│   ├── core.py               # Port scanning engine (PortScanner, ServiceMap, ScanResult)
│   ├── gui.py                # Tkinter GUI (PortScannerGUI)
│   └── utils.py              # Utilities (Exporter, Validator)
├── main.py                   # Application entry point
├── requirements.txt          # Dependencies (empty - stdlib only)
├── README.md                 # This file
├── BUILD_SUMMARY.md          # Build details
├── .gitignore               # Git ignore rules
├── .gitattributes           # Line ending normalization
└── LICENSE                  # (optional)

## How It Works

1. **Input Validation** - Validates target, port range, and timeout values
2. **Threading** - Creates multiple threads for concurrent port scanning
3. **Socket Connection** - Attempts TCP connection to each port
4. **Service Detection** - Maps port numbers to known services
5. **Progress Tracking** - Updates progress bar and status
6. **Result Storage** - Stores open ports in memory
7. **Export** - Exports results to chosen format

## Performance Tips

- **Local Network** - Use timeout of 0.5-1.0 seconds for faster scans
- **Remote Hosts** - Use timeout of 2-5 seconds for reliability
- **Thread Count** - Higher thread count (100-500) for more parallelism
- **Port Range** - Scanning fewer ports completes faster

## Safety & Ethics

⚠️ **Important**: Only scan ports on systems you own or have explicit permission to scan. Unauthorized network scanning may be illegal in your jurisdiction.

## Limitations

- TCP connect scans only (no SYN, UDP, or other advanced scan types)
- No version detection (only port-based service identification)
- No vulnerability scanning
- Requires destination host to be reachable

## 🔧 Troubleshooting

### "No module named 'scanner'"
- Ensure you're running from the project **root directory** (not from inside `scanner/`)
- Verify the `scanner` folder exists with `__init__.py`

```bash
# Correct
cd network-port-scanner
python main.py

# Wrong
cd scanner
python ../main.py
```

### "No module named 'tkinter'"
- Install Tkinter (see [Requirements](#-requirements) section)
- Test with: `python -m tkinter`

### Slow scanning
- **Increase threads** (e.g., 200–500) for more parallelism
- **Reduce timeout** (trade speed for reliability; try 0.5–0.8 seconds)
- **Scan fewer ports** (e.g., well-known ports 1–1024 instead of all)

### "Connection refused" errors during scan
- Host is reachable but firewall is blocking the connection
- Try a different timeout value
- Check firewall rules on target machine

### Firewall blocks your scanner
- Some ISPs block port scanning
- Try from a different network
- Scan only hosts you own or have permission for

## ⚖️ License & Disclaimer

This project is open source and available for **educational and authorized testing purposes only**.

⚠️ **Important Legal Notice:**
- Only scan systems **you own** or have **explicit written permission** to scan
- Unauthorized network scanning may be illegal in your jurisdiction
- Users are responsible for ensuring compliance with all applicable laws
- Unauthorized access to computer systems is a federal crime in many countries

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Fork the repository
- Submit pull requests for improvements
- Report issues and bugs
- Suggest new features

## 📧 Contact & Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Version:** 1.0  
**Last Updated:** April 2026  
**Author:** [Avadhoot](https://github.com/Avadhoot-007)
