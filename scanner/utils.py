"""
Network Port Scanner - Utilities Module
Handles input validation and exporting results to different formats
"""

import json
import csv
import socket
from datetime import datetime
from typing import List, Dict, Tuple


# ── Exporter ─────────────────────────────────────────────────────────────────

class Exporter:
    """Exports scan results to various file formats."""

    @staticmethod
    def _header_lines(target: str, start_port: int, end_port: int,
                      open_ports: List[Dict]) -> List[str]:
        """Shared metadata lines used by text export."""
        return [
            "=" * 60,
            "NETWORK PORT SCAN REPORT",
            "=" * 60,
            "",
            f"Target:           {target}",
            f"Port Range:       {start_port} - {end_port}",
            f"Scan Date:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Open Ports Found: {len(open_ports)}",
            "",
        ]

    @staticmethod
    def _do_export(filepath: str, write_fn) -> Tuple[bool, str]:
        """
        Generic export wrapper — runs write_fn(filepath) and returns
        (success, error_message). Errors are returned, NOT printed.
        """
        try:
            write_fn(filepath)
            return True, ""
        except Exception as e:
            return False, str(e)

    @staticmethod
    def to_text(target: str, start_port: int, end_port: int,
                open_ports: List[Dict], filepath: str) -> Tuple[bool, str]:
        """Export results to a plain-text report."""

        def write(fp):
            with open(fp, 'w', encoding='utf-8') as f:
                for line in Exporter._header_lines(target, start_port, end_port, open_ports):
                    f.write(line + "\n")

                if open_ports:
                    f.write("-" * 60 + "\n")
                    f.write(f"{'PORT':<8} {'SERVICE':<20} {'BANNER'}\n")
                    f.write("-" * 60 + "\n")
                    for p in open_ports:
                        banner = p.get('banner', '')
                        f.write(f"{p['port']:<8} {p['service']:<20} {banner}\n")
                    f.write("-" * 60 + "\n")
                else:
                    f.write("No open ports found.\n")

                f.write("\n" + "=" * 60 + "\n")

        return Exporter._do_export(filepath, write)

    @staticmethod
    def to_json(target: str, start_port: int, end_port: int,
                open_ports: List[Dict], filepath: str) -> Tuple[bool, str]:
        """Export results to JSON."""

        # Capture timestamp before entering write() so it stays consistent
        # even if the file write is delayed or retried.
        scan_date = datetime.now().isoformat()

        def write(fp):
            data = {
                'target': target,
                'port_range': {'start': start_port, 'end': end_port},
                'scan_date': scan_date,
                'open_ports_count': len(open_ports),
                'open_ports': open_ports,
            }
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        return Exporter._do_export(filepath, write)

    @staticmethod
    def to_csv(target: str, start_port: int, end_port: int,
               open_ports: List[Dict], filepath: str) -> Tuple[bool, str]:
        """Export results to CSV."""

        # Capture timestamp before entering write() so it stays consistent
        # even if the file write is delayed or retried.
        scan_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        def write(fp):
            with open(fp, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Network Port Scan Report'])
                writer.writerow(['Target', target])
                writer.writerow(['Port Range', f'{start_port}-{end_port}'])
                writer.writerow(['Scan Date', scan_date])
                writer.writerow(['Total Open Ports', len(open_ports)])
                writer.writerow([])
                writer.writerow(['Port', 'Service', 'Status', 'Banner'])
                for p in open_ports:
                    writer.writerow([p['port'], p['service'],
                                     p.get('status', ''), p.get('banner', '')])

        return Exporter._do_export(filepath, write)


# ── Validator ────────────────────────────────────────────────────────────────

class Validator:
    """Validates all scanner input parameters."""

    @staticmethod
    def validate_target(target: str) -> Tuple[bool, str, str]:
        """Validate and resolve target IP / hostname.

        Returns (ok, error_message, resolved_ip).
        resolved_ip is the dotted-decimal IP on success, or '' on failure.
        Callers should reuse resolved_ip instead of doing a second DNS lookup.

        Uses setdefaulttimeout with save/restore (3 s) because getaddrinfo is a
        module-level call that ignores per-socket timeouts entirely.
        validate_target() is intentionally called from a background thread in
        the GUI so the save/restore pattern is safe there.
        """
        if not target or not target.strip():
            return False, "Target cannot be empty.", ""
        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(3.0)
            resolved_ip = socket.gethostbyname(target.strip())
        except socket.gaierror:
            return False, f"Cannot resolve host '{target}'. Check the address and your network.", ""
        except socket.timeout:
            return False, f"DNS lookup for '{target}' timed out. Check your network.", ""
        except OSError:
            return False, f"Network error while resolving '{target}'. Check your network.", ""
        finally:
            socket.setdefaulttimeout(old_timeout)
        return True, "", resolved_ip

    @staticmethod
    def validate_ports(start: int, end: int) -> Tuple[bool, str]:
        """Validate port range."""
        # bool is a subclass of int in Python, so exclude it explicitly.
        if isinstance(start, bool) or isinstance(end, bool) \
                or not isinstance(start, int) or not isinstance(end, int):
            return False, "Ports must be integers."
        if not (1 <= start <= 65535):
            return False, "Start port must be between 1 and 65535."
        if not (1 <= end <= 65535):
            return False, "End port must be between 1 and 65535."
        if start > end:
            return False, "Start port must be ≤ end port."
        return True, ""

    @staticmethod
    def validate_timeout(timeout: float) -> Tuple[bool, str]:
        """Validate socket timeout."""
        # bool is a subclass of int (and therefore passes the numeric check),
        # so exclude it explicitly.
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            return False, "Timeout must be a number."
        if timeout <= 0:
            return False, "Timeout must be greater than 0."
        if timeout > 60:
            return False, "Timeout should not exceed 60 seconds."
        return True, ""

    @staticmethod
    def validate_threads(threads: int) -> Tuple[bool, str]:
        """Validate thread count."""
        # bool is a subclass of int in Python, so exclude it explicitly.
        if isinstance(threads, bool) or not isinstance(threads, int):
            return False, "Thread count must be an integer."
        if threads < 1:
            return False, "Thread count must be at least 1."
        if threads > 1000:
            return False, "Thread count should not exceed 1000."
        return True, ""