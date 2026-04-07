"""
Network Port Scanner - Core Scanning Module
Handles TCP port scanning with multi-threading and service detection
"""

import socket
import threading
import time
from enum import Enum
from queue import Queue, Empty
from typing import List, Dict, Tuple, Optional


# ── Event type constants (fixes magic strings) ─────────────────────────────

class EventType(str, Enum):
    OPEN_PORT      = 'open_port'
    PROGRESS       = 'progress'
    SCAN_COMPLETE  = 'scan_complete'
    STATUS         = 'status'
    ERROR          = 'error'


# ── Service map ─────────────────────────────────────────────────────────────

class ServiceMap:
    """Maps port numbers to service names, with stdlib fallback"""

    SERVICES = {
        21:    'FTP',
        22:    'SSH',
        23:    'Telnet',
        25:    'SMTP',
        53:    'DNS',
        67:    'DHCP',
        68:    'DHCP-Client',
        69:    'TFTP',
        79:    'Finger',
        80:    'HTTP',
        88:    'Kerberos',
        110:   'POP3',
        111:   'RPC',
        119:   'NNTP',
        123:   'NTP',
        135:   'MS-RPC',
        137:   'NetBIOS-NS',
        139:   'NetBIOS-SSN',
        143:   'IMAP',
        161:   'SNMP',
        194:   'IRC',
        389:   'LDAP',
        443:   'HTTPS',
        445:   'SMB',
        465:   'SMTPS',
        514:   'Syslog',
        587:   'SMTP-Submission',
        631:   'IPP',
        636:   'LDAPS',
        993:   'IMAPS',
        995:   'POP3S',
        1080:  'SOCKS',
        1194:  'OpenVPN',
        1433:  'MSSQL',
        1521:  'Oracle-DB',
        1723:  'PPTP',
        2049:  'NFS',
        2181:  'ZooKeeper',
        2375:  'Docker',
        2376:  'Docker-TLS',
        3000:  'Dev-Server',
        3306:  'MySQL',
        3389:  'RDP',
        4200:  'Angular-Dev',
        5000:  'Flask/Dev',
        5432:  'PostgreSQL',
        5672:  'RabbitMQ',
        5900:  'VNC',
        6379:  'Redis',
        6443:  'Kubernetes',
        7001:  'WebLogic',
        8000:  'HTTP-Dev',
        8080:  'HTTP-Alt',
        8443:  'HTTPS-Alt',
        8888:  'Jupyter',
        9000:  'SonarQube',
        9090:  'Prometheus',
        9200:  'Elasticsearch',
        9300:  'Elasticsearch-Cluster',
        27017: 'MongoDB',
        27018: 'MongoDB-Shard',
        50000: 'SAP',
    }

    @staticmethod
    def get_service(port: int) -> str:
        """Get service name — checks hardcoded map first, then stdlib."""
        if port in ServiceMap.SERVICES:
            return ServiceMap.SERVICES[port]
        try:
            if 0 <= port <= 65535:
                return socket.getservbyport(port, 'tcp')
        except OSError:
            pass
        return 'Unknown'


# ── Banner grabber ───────────────────────────────────────────────────────────

# Service-appropriate probes for banner grabbing.
# Ports not listed here get a passive listen (no probe sent).
_BANNER_PROBES: Dict[int, bytes] = {
    # HTTP-like services
    80:   b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n',
    8080: b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n',
    8000: b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n',
    8443: b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n',
    443:  b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n',
    # FTP, SMTP, POP3, IMAP — these send a banner on connect, no probe needed
    # but sending nothing also works; use a gentle QUIT to avoid leaving open sessions
    21:   b'',
    25:   b'EHLO scanner\r\n',
    110:  b'',
    143:  b'',
    # SSH, MySQL, RDP — send banner on connect, no probe needed
    22:   b'',
    3306: b'',
    3389: b'',
    # Redis
    6379: b'PING\r\n',
    # Generic fallback for everything else: empty (listen only)
}


def _read_banner_from_sock(sock: socket.socket, port: int) -> Optional[str]:
    """
    Read a banner from an already-connected socket.
    Sends a service-appropriate probe first if needed.
    Does NOT close the socket — caller owns it.
    """
    try:
        probe = _BANNER_PROBES.get(port, b'')
        if probe:
            try:
                sock.send(probe)
            except Exception:
                pass
        try:
            raw = sock.recv(1024)
        except Exception:
            raw = b''
        banner = raw.decode('utf-8', errors='replace').strip()
        first_line = banner.splitlines()[0] if banner else None
        return first_line[:120] if first_line else None
    except Exception:
        return None


def grab_banner(host: str, port: int, timeout: float = 2.0) -> Optional[str]:
    """
    Open a fresh connection to host:port and read the service banner.
    Use _read_banner_from_sock() when you already have an open socket.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        return _read_banner_from_sock(sock, port)
    except Exception:
        return None
    finally:
        if sock is not None:
            sock.close()


# ── Main scanner ─────────────────────────────────────────────────────────────

class PortScanner:
    """
    Multi-threaded TCP port scanner with banner grabbing.

    Attributes:
        target (str): IP address or hostname to scan
        start_port (int): Starting port number
        end_port (int): Ending port number
        timeout (float): Socket timeout in seconds
        thread_count (int): Number of concurrent threads
        grab_banners (bool): Whether to attempt banner grabbing on open ports
    """

    def __init__(self, target: str, start_port: int, end_port: int,
                 timeout: float = 1.0, threads: int = 100,
                 grab_banners: bool = False,
                 port_list: Optional[List[int]] = None,
                 resolved_ip: Optional[str] = None):
        self.target = target
        self.start_port = start_port
        self.end_port = end_port
        self.timeout = timeout
        self.thread_count = threads
        self.grab_banners = grab_banners
        self.port_list = port_list  # If set, overrides start/end range

        ports = port_list if port_list else list(range(start_port, end_port + 1))
        self.open_ports: List[Dict] = []
        self.total_ports = len(ports)
        self._ports_to_scan = ports
        self.scanned_count = 0
        self.is_running = False
        self.should_stop = False
        # Accept a pre-resolved IP from the caller (e.g. from Validator.validate_target)
        # to avoid performing DNS resolution a second time inside scan().
        self._resolved_ip: Optional[str] = resolved_ip
        self.scan_time: float = 0.0   # populated after scan() completes

        self.lock = threading.Lock()
        # Queues are created fresh each scan() call — see scan()
        self.work_queue: Queue = Queue()
        self.result_queue: Queue = Queue()

    def resolve_target(self) -> str:
        """
        Resolve hostname to IP address once, cache the result.
        Uses a 3-second timeout to avoid blocking indefinitely on slow DNS.

        Raises:
            socket.gaierror: If hostname cannot be resolved
            socket.timeout: If DNS lookup times out
        """
        if self._resolved_ip is None:
            # getaddrinfo respects the per-socket timeout set on a dummy socket,
            # but the simplest cross-platform approach for a one-shot DNS call
            # is to use a short default timeout scoped with save/restore under a lock.
            # Since resolve_target() is only called from the single scan() call path
            # (not from worker threads), temporarily mutating the default timeout here
            # is safe.
            old_timeout = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(3.0)
                self._resolved_ip = socket.gethostbyname(self.target)
            finally:
                socket.setdefaulttimeout(old_timeout)
        return self._resolved_ip

    def check_reachability(self) -> bool:
        """
        Quick reachability pre-check: try connecting to port 80 or 443.
        Falls back to attempting any port in the scan range.
        Returns True if host appears reachable, False otherwise.
        """
        probe_ports = [80, 443, self.start_port]
        for port in probe_ports:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(min(self.timeout, 2.0))
                result = sock.connect_ex((self._resolved_ip or self.target, port))
                # result == 0 means open, ECONNREFUSED means host is up but port closed
                # 111 = Linux, 61 = macOS, 10061 = Windows
                if result in (0, 61, 111, 10061):
                    return True
            except Exception:
                pass
            finally:
                if sock is not None:
                    sock.close()
        return False

    def scan_port(self, port: int) -> None:
        """Scan a single port via TCP connect, optionally grabbing its banner."""
        if self.should_stop:
            return

        host = self._resolved_ip or self.target
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((host, port))

            if result == 0:
                # Port is open — reuse the live socket for banner grabbing
                # instead of opening a second connection.
                service = ServiceMap.get_service(port)
                banner  = None
                if self.grab_banners:
                    # Give banner reading a bit more time than the connect timeout
                    sock.settimeout(max(self.timeout, 2.0))
                    banner = _read_banner_from_sock(sock, port)

                port_info = {
                    'port':    port,
                    'service': service,
                    'status':  'open',
                    'banner':  banner or '',
                }
                with self.lock:
                    self.open_ports.append(port_info)
                self.result_queue.put((EventType.OPEN_PORT, port_info))

        except Exception:
            pass
        finally:
            if sock is not None:
                sock.close()
            with self.lock:
                self.scanned_count += 1
                count = self.scanned_count
            self.result_queue.put((EventType.PROGRESS, count, self.total_ports))

    def worker_thread(self) -> None:
        """Worker: pulls port numbers from work_queue only."""
        while not self.should_stop:
            try:
                port = self.work_queue.get(timeout=0.1)
                if port is None:            # Sentinel value
                    self.work_queue.task_done()
                    break
                try:
                    self.scan_port(port)
                finally:
                    self.work_queue.task_done()
            except Empty:
                pass    # Timeout on empty queue — loop again
            except Exception:
                pass

    def scan(self) -> List[Dict]:
        """
        Start the port scan.

        Returns:
            Sorted list of open port dicts.
        """
        # Re-create queues so re-running a scan is safe
        self.work_queue = Queue()
        self.result_queue = Queue()

        self.is_running = True
        self.should_stop = False
        self.open_ports = []
        self.scanned_count = 0
        self.scan_time = 0.0
        _start = time.monotonic()

        # Resolve hostname once — emits a STATUS event for the GUI
        try:
            ip = self.resolve_target()
            if ip != self.target:
                self.result_queue.put((EventType.STATUS, f"Resolved {self.target} → {ip}"))
        except (socket.gaierror, socket.timeout) as e:
            self.result_queue.put((EventType.ERROR, f"Cannot resolve host: {e}"))
            self.is_running = False
            self.result_queue.put((EventType.SCAN_COMPLETE, []))
            return []

        # Populate work queue
        for port in self._ports_to_scan:
            self.work_queue.put(port)

        # Start workers
        actual_threads = min(self.thread_count, self.total_ports)
        threads = []
        for _ in range(actual_threads):
            t = threading.Thread(target=self.worker_thread, daemon=True)
            t.start()
            threads.append(t)

        # Wait for all ports to be processed
        self.work_queue.join()

        # Drain workers with sentinels
        for _ in range(len(threads)):
            self.work_queue.put(None)
        for t in threads:
            t.join(timeout=2.0)

        self.is_running = False
        self.scan_time = time.monotonic() - _start
        results = self.get_open_ports()
        self.result_queue.put((EventType.SCAN_COMPLETE, results, self.scan_time))
        return results

    def stop(self) -> None:
        """Signal workers to stop and drain the work queue to unblock join()."""
        self.should_stop = True
        # Drain remaining items so work_queue.join() can unblock
        while not self.work_queue.empty():
            try:
                self.work_queue.get_nowait()
                self.work_queue.task_done()
            except Empty:
                break

    def get_open_ports(self) -> List[Dict]:
        with self.lock:
            return sorted(self.open_ports.copy(), key=lambda x: x['port'])

    def get_progress(self) -> Tuple[int, int]:
        with self.lock:
            return (self.scanned_count, self.total_ports)


# ── Scan result container ────────────────────────────────────────────────────

class ScanResult:
    """Holds and formats the results of a completed port scan."""

    def __init__(self, target: str, start_port: int, end_port: int,
                 open_ports: List[Dict], scan_time: float = 0.0):
        self.target = target
        self.start_port = start_port
        self.end_port = end_port
        self.open_ports = open_ports
        self.scan_time = scan_time

    def __str__(self) -> str:
        lines = [
            f"Scan Results for {self.target}",
            f"Port Range: {self.start_port}-{self.end_port}",
            f"Scan Time: {self.scan_time:.2f}s",
            f"Open Ports Found: {len(self.open_ports)}",
            "",
        ]
        if self.open_ports:
            lines.append("Open Ports:")
            for p in self.open_ports:
                banner = f"  [{p['banner']}]" if p.get('banner') else ""
                lines.append(f"  Port {p['port']:<6} {p['service']}{banner}")
        else:
            lines.append("No open ports found.")
        return '\n'.join(lines)