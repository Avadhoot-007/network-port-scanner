# Network Port Scanner

A simple and efficient network port scanner with a graphical user interface built using Python and Tkinter.

![Python 3.6+](https://img.shields.io/badge/Python-3.6%2B-blue)
![License](https://img.shields.io/badge/License-Educational%20Use-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen)

## Features

- **TCP Port Scanning** — Scan any IP address or hostname for open ports
- **Service Detection** — Automatically identify 40+ common services
- **Multi-threaded** — Configurable concurrent threads for fast scanning
- **Real-time Progress** — Live progress bar with ETA calculation
- **Export Results** — Save as TXT, JSON, or CSV
- **Scan History** — View previous scans in the session
- **Banner Grabbing** — Optional service banner retrieval
- **No Dependencies** — Uses only Python standard library

## Requirements

- Python 3.6+
- Tkinter (included with Python on most systems)

### Install Tkinter

**Windows:** Usually included. Reinstall Python with "tcl/tk and IDLE" checked if missing.

**macOS:**
```
brew install python-tk
```

**Linux (Debian/Ubuntu):**
```
sudo apt-get install python3-tk
```

**Linux (Fedora/RHEL):**
```
sudo dnf install python3-tkinter
```

## Installation

1. Clone the repository:
```
git clone https://github.com/YOUR_USERNAME/network-port-scanner.git
cd network-port-scanner
```

2. Run the application:
```
python main.py
```

## Usage

### GUI Application

Run `python main.py` to open the graphical interface.

**Scanner Tab:**
- Enter target IP or hostname
- Choose port range or use presets (Well-Known, Registered, All)
- Configure timeout (default 1.0s) and thread count (default 100)
- Toggle banner grabbing if needed
- Click **Start Scan** to begin
- View results in real-time
- Export results to TXT, JSON, or CSV

**History Tab:**
- View all scans from current session
- Click a scan to see detailed results

### Programmatic Usage

```python
from scanner.core import PortScanner

scanner = PortScanner('127.0.0.1', 1, 1024, timeout=1.0, threads=100)
results = scanner.scan()

for port in results:
    print(f"Port {port['port']}: {port['service']}")
```

## Project Structure

```
network-port-scanner/
├── scanner/
│   ├── __init__.py           # Package initialization
│   ├── core.py               # Port scanning engine
│   ├── gui.py                # Tkinter GUI
│   └── utils.py              # Validation and export
├── main.py                   # Entry point
├── requirements.txt          # Dependencies (empty - stdlib only)
├── README.md                 # This file
├── .gitignore               # Git ignore rules
└── .gitattributes           # Line ending normalization
```

## How It Works

1. **Input Validation** — Validates target, port range, and timeout
2. **Threading** — Creates worker threads for concurrent scanning
3. **Socket Connection** — Attempts TCP connect to each port
4. **Service Detection** — Maps ports to known services
5. **Progress Tracking** — Updates progress bar in real-time
6. **Result Export** — Saves results in chosen format

## Performance Tips

- **Local network:** timeout 0.5–1.0s for faster scans
- **Remote hosts:** timeout 2–5s for reliability
- **Thread count:** 100–500 for good parallelism
- **Scan fewer ports:** Reduces scan time significantly

## Limitations

- TCP connect scans only (no SYN, UDP, or advanced types)
- No version detection (port-based service identification only)
- No vulnerability scanning
- Requires destination host to be reachable

## Troubleshooting

**"No module named 'scanner'"**
- Run from project root directory, not from inside `scanner/`

**"No module named 'tkinter'"**
- Install Tkinter (see [Requirements](#requirements))
- Test with: `python -m tkinter`

**Slow scanning**
- Increase threads (e.g., 200–500)
- Reduce timeout (try 0.5–0.8s)
- Scan fewer ports

**Firewall blocks scanning**
- Some ISPs block port scanning
- Try from a different network
- Check firewall rules on target machine

## Legal Notice

⚠️ **Important:** Only scan systems you own or have explicit permission to scan. Unauthorized network scanning may be illegal in your jurisdiction.

## License

Open source for educational and authorized testing purposes only.

## Contributing

Contributions welcome! Feel free to fork, submit issues, or suggest improvements.

---

**Version:** 1.0  
**Author:** [Your Name](https://github.com/YOUR_USERNAME)  
**Last Updated:** April 2026
