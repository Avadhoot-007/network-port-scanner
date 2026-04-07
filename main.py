#!/usr/bin/env python3
"""
Network Port Scanner
A simple and efficient port scanning tool with GUI

Usage:
    python main.py
"""

import tkinter as tk
from scanner.gui import PortScannerGUI


def main():
    """Main entry point"""
    root = tk.Tk()
    app = PortScannerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()