#!/usr/bin/env python3
"""
Enhanced Network Information and Diagnostics Tool

This utility performs comprehensive network analysis and connectivity testing.
It provides operations including:
  • interfaces  – List and analyze network interfaces with detailed statistics
  • ip          – Display IP address information for all interfaces
  • ping        – Test connectivity to a target with visual response time tracking
  • traceroute  – Trace network path to a target with hop latency visualization
  • dns         – Perform DNS lookups with multiple record types
  • scan        – Scan for open ports on a target host
  • monitor     – Monitor network latency to a target over time
  • bandwidth   – Perform a simple bandwidth test

Note: Some operations require root privileges.
"""

import atexit
import datetime
import ipaddress
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
PING_COUNT_DEFAULT = 4
PING_INTERVAL_DEFAULT = 1.0
TRACEROUTE_MAX_HOPS = 30
TRACEROUTE_TIMEOUT = 5.0
MONITOR_DEFAULT_INTERVAL = 1.0
MONITOR_DEFAULT_COUNT = 100
PORT_SCAN_TIMEOUT = 1.0
PORT_SCAN_COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 123, 143, 443, 465, 587, 993, 995, 3306, 3389, 5432, 8080, 8443]
DNS_TYPES = ["A", "AAAA", "MX", "NS", "SOA", "TXT", "CNAME"]
BANDWIDTH_TEST_SIZE = 10 * 1024 * 1024  # 10MB
BANDWIDTH_CHUNK_SIZE = 64 * 1024  # 64KB

PROGRESS_WIDTH = 50
UPDATE_INTERVAL = 0.1
MAX_LATENCY_HISTORY = 100
RTT_GRAPH_WIDTH = 60
RTT_GRAPH_HEIGHT = 10

PORT_SERVICES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP",
    110: "POP3", 123: "NTP", 143: "IMAP", 443: "HTTPS", 465: "SMTP/SSL",
    587: "SMTP/TLS", 993: "IMAP/SSL", 995: "POP3/SSL", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 8080: "HTTP-ALT", 8443: "HTTPS-ALT",
}

COMMANDS = {
    "ip": shutil.which("ip") is not None,
    "ping": shutil.which("ping") is not None,
    "traceroute": shutil.which("traceroute") is not None,
    "dig": shutil.which("dig") is not None,
    "nslookup": shutil.which("nslookup") is not None,
    "nmap": shutil.which("nmap") is not None,
    "ifconfig": shutil.which("ifconfig") is not None,
}

# ------------------------------
# Nord‑Themed UI Setup
# ------------------------------
console = Console()

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")

def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")

def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")

def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #EBCB8B]⚠ {text}[/bold #EBCB8B]")

def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")

def format_time(seconds: float) -> str:
    """Format seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"

def format_rate(bps: float) -> str:
    """Format bytes per second into a human-readable rate."""
    if bps < 1024:
        return f"{bps:.1f} B/s"
    elif bps < 1024**2:
        return f"{bps / 1024:.1f} KB/s"
    elif bps < 1024**3:
        return f"{bps / 1024**2:.1f} MB/s"
    else:
        return f"{bps / 1024**3:.1f} GB/s"

def is_valid_ip(ip: str) -> bool:
    """Return True if ip is a valid IP address."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_valid_hostname(hostname: str) -> bool:
    """Return True if hostname is valid."""
    pattern = re.compile(
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    return bool(pattern.match(hostname))

def check_root_privileges() -> None:
    """Warn if not running as root."""
    if os.geteuid() != 0:
        print_warning("Running without root privileges; some operations may be limited.")

def validate_target(target: str) -> bool:
    """Validate that the target is a valid IP or hostname."""
    if is_valid_ip(target) or is_valid_hostname(target):
        return True
    print_error(f"Invalid target: {target}")
    return False

def check_command_availability(command: str) -> bool:
    """Check if a system command is available."""
    if not COMMANDS.get(command, False):
        print_error(f"Required command '{command}' is not available.")
        return False
    return True

# ------------------------------
# Latency Tracking
# ------------------------------
class LatencyTracker:
    """
    Tracks network latency measurements and provides statistics and an ASCII graph.
    """
    def __init__(self, max_history: int = MAX_LATENCY_HISTORY, width: int = RTT_GRAPH_WIDTH):
        self.history: deque = deque(maxlen=max_history)
        self.min_rtt = float("inf")
        self.max_rtt = 0.0
        self.avg_rtt = 0.0
        self.loss_count = 0
        self.total_count = 0
        self.width = width
        self._lock = threading.Lock()

    def add_result(self, rtt: Optional[float]) -> None:
        with self._lock:
            self.total_count += 1
            if rtt is None:
                self.loss_count += 1
                self.history.append(None)
            else:
                self.history.append(rtt)
                if rtt < self.min_rtt:
                    self.min_rtt = rtt
                if rtt > self.max_rtt:
                    self.max_rtt = rtt
                valid = [r for r in self.history if r is not None]
                if valid:
                    self.avg_rtt = sum(valid) / len(valid)

    def display_statistics(self) -> None:
        with self._lock:
            loss_pct = (self.loss_count / self.total_count * 100) if self.total_count else 0
            min_rtt = self.min_rtt if self.min_rtt != float("inf") else 0
            console.print(f"[bold #8FBCBB]RTT Statistics:[/bold #8FBCBB]")
            console.print(f"  Min: [dim]{min_rtt:.2f} ms[/dim]")
            console.print(f"  Avg: [dim]{self.avg_rtt:.2f} ms[/dim]")
            console.print(f"  Max: [dim]{self.max_rtt:.2f} ms[/dim]")
            console.print(f"  Packet Loss: [bold]{loss_pct:.1f}%[/bold] ({self.loss_count}/{self.total_count})")

    def display_graph(self) -> None:
        with self._lock:
            valid = [r for r in self.history if r is not None]
            if not valid:
                console.print("[bold #EBCB8B]No latency data to display graph[/bold #EBCB8B]")
                return
            min_val, max_val = min(valid), max(valid)
            if max_val - min_val < 5:
                max_val = min_val + 5
            graph = []
            for rtt in list(self.history)[-self.width:]:
                if rtt is None:
                    graph.append("×")
                else:
                    ratio = (rtt - min_val) / (max_val - min_val)
                    if rtt < self.avg_rtt * 0.8:
                        color = "#8FBCBB"
                    elif rtt < self.avg_rtt * 1.2:
                        color = "#D8DEE9"
                    else:
                        color = "#EBCB8B"
                    graph.append(f"[{color}]█[/{color}]")
            console.print("\n[dim]Latency Graph:[/dim]")
            console.print("".join(graph))
            console.print(f"[dim]Min: {min_val:.1f} ms | Max: {max_val:.1f} ms[/dim]")

# ------------------------------
# Network Operation Functions
# ------------------------------
def get_network_interfaces() -> List[Dict[str, Any]]:
    """Retrieve and display network interface information."""
    print_section("Network Interfaces")
    interfaces = []
    spinner = Progress(SpinnerColumn(style="bold #81A1C1"),
                       TextColumn("[progress.description]{task.description}"),
                       BarColumn(style="bold #88C0D0"),
                       TimeRemainingColumn(),
                       console=console)
    with spinner:
        task = spinner.add_task("Collecting interface info...", total=None)
        try:
            if check_command_availability("ip"):
                output = subprocess.check_output(["ip", "-o", "link", "show"], universal_newlines=True)
                for line in output.splitlines():
                    m = re.search(r"^\d+:\s+([^:@]+).*state\s+(\w+)", line)
                    if m:
                        name, state = m.groups()
                        if name.strip() == "lo":
                            continue
                        hw = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", line)
                        mac = hw.group(1) if hw else "Unknown"
                        interfaces.append({
                            "name": name.strip(),
                            "status": state,
                            "mac_address": mac,
                        })
            elif check_command_availability("ifconfig"):
                output = subprocess.check_output(["ifconfig"], universal_newlines=True)
                current = None
                for line in output.splitlines():
                    iface = re.match(r"^(\w+):", line)
                    if iface:
                        current = iface.group(1)
                        if current == "lo":
                            current = None
                            continue
                        interfaces.append({"name": current, "status": "unknown", "mac_address": "Unknown"})
                    elif current and "ether" in line:
                        m = re.search(r"ether\s+([0-9a-fA-F:]+)", line)
                        if m:
                            for iface in interfaces:
                                if iface["name"] == current:
                                    iface["mac_address"] = m.group(1)
            spinner.stop(f"[bold #8FBCBB]Found {len(interfaces)} interfaces[/bold #8FBCBB]")
            if interfaces:
                console.print(f"[bold]{'Interface':<12} {'Status':<10} {'MAC Address':<20}[/bold]")
                console.print("─" * 50)
                for iface in interfaces:
                    status_color = "#8FBCBB" if iface["status"].lower() in ["up", "active"] else "#BF616A"
                    console.print(f"[bold #88C0D0]{iface['name']:<12}[/bold #88C0D0] "
                                  f"[{status_color}]{iface['status']:<10}[/{status_color}] "
                                  f"{iface['mac_address']:<20}")
            else:
                console.print("[bold #EBCB8B]No network interfaces found[/bold #EBCB8B]")
            return interfaces
        except Exception as e:
            spinner.stop(f"[bold #BF616A]Error: {e}[/bold #BF616A]")
            return []

def get_ip_addresses() -> Dict[str, List[Dict[str, str]]]:
    """Retrieve and display IP address information for all interfaces."""
    print_section("IP Address Information")
    ip_info = {}
    spinner = Progress(SpinnerColumn(style="bold #81A1C1"),
                       TextColumn("[progress.description]{task.description}"),
                       console=console)
    with spinner:
        task = spinner.add_task("Collecting IP addresses...", total=None)
        try:
            if check_command_availability("ip"):
                output = subprocess.check_output(["ip", "-o", "addr"], universal_newlines=True)
                for line in output.splitlines():
                    parts = line.split()
                    if len(parts) >= 4:
                        iface = parts[1]
                        if iface == "lo":
                            continue
                        if "inet" in line:
                            m = re.search(r"inet\s+([^/]+)", line)
                            if m:
                                ip_info.setdefault(iface, []).append({"type": "IPv4", "address": m.group(1)})
                        if "inet6" in line:
                            m = re.search(r"inet6\s+([^/]+)", line)
                            if m and not m.group(1).startswith("fe80"):
                                ip_info.setdefault(iface, []).append({"type": "IPv6", "address": m.group(1)})
            elif check_command_availability("ifconfig"):
                output = subprocess.check_output(["ifconfig"], universal_newlines=True)
                current = None
                for line in output.splitlines():
                    iface = re.match(r"^(\w+):", line)
                    if iface:
                        current = iface.group(1)
                        if current == "lo":
                            current = None
                            continue
                    elif current and "inet " in line:
                        m = re.search(r"inet\s+([0-9.]+)", line)
                        if m:
                            ip_info.setdefault(current, []).append({"type": "IPv4", "address": m.group(1)})
                    elif current and "inet6 " in line:
                        m = re.search(r"inet6\s+([0-9a-f:]+)", line)
                        if m and not m.group(1).startswith("fe80"):
                            ip_info.setdefault(current, []).append({"type": "IPv6", "address": m.group(1)})
            spinner.stop(f"[bold #8FBCBB]IP information collected[/bold #8FBCBB]")
            if ip_info:
                for iface, addrs in ip_info.items():
                    console.print(f"[bold #88C0D0]{iface}:[/bold #88C0D0]")
                    for addr in addrs:
                        type_color = "#88C0D0" if addr["type"] == "IPv4" else "#B48EAD"
                        console.print(f"  [{type_color}]{addr['type']:<6}[/{type_color}]: {addr['address']}")
            else:
                console.print("[bold #EBCB8B]No IP addresses found[/bold #EBCB8B]")
            return ip_info
        except Exception as e:
            spinner.stop(f"[bold #BF616A]Error: {e}[/bold #BF616A]")
            return {}

def ping_target(target: str, count: int = PING_COUNT_DEFAULT, interval: float = PING_INTERVAL_DEFAULT) -> Dict[str, Any]:
    """Ping a target and display real-time latency results."""
    print_section(f"Ping: {target}")
    if not validate_target(target):
        return {}
    if not check_command_availability("ping"):
        console.print("[bold #BF616A]Ping command not available[/bold #BF616A]")
        return {}
    progress_task = Progress(SpinnerColumn(style="bold #81A1C1"),
                             TextColumn("[progress.description]{task.description}"),
                             BarColumn(style="bold #88C0D0"),
                             TimeRemainingColumn(),
                             console=console)
    latency_tracker = LatencyTracker()
    with progress_task as progress:
        task = progress.add_task("Pinging...", total=count)
        ping_cmd = ["ping", "-c", str(count), "-i", str(interval), target]
        try:
            process = subprocess.Popen(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
            current = 0
            while process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue
                if line.startswith(("64 bytes", "56 bytes")):
                    current += 1
                    progress.update(task, advance=1)
                    m = re.search(r"time=(\d+\.?\d*)", line)
                    if m:
                        rtt = float(m.group(1))
                        latency_tracker.add_result(rtt)
                        console.print(f"\r[dim]Reply: time={rtt:.2f} ms[/dim]")
                elif "Request timeout" in line or "100% packet loss" in line:
                    current += 1
                    progress.update(task, advance=1)
                    latency_tracker.add_result(None)
                    console.print(f"\r[bold #BF616A]Request timed out[/bold #BF616A]")
            # Ensure complete progress
            progress.update(task, completed=count)
            console.print("")
            latency_tracker.display_statistics()
            latency_tracker.display_graph()
            results = {
                "target": target,
                "sent": latency_tracker.total_count,
                "received": latency_tracker.total_count - latency_tracker.loss_count,
                "packet_loss": f"{(latency_tracker.loss_count/latency_tracker.total_count*100):.1f}%",
                "rtt_min": f"{latency_tracker.min_rtt:.2f} ms",
                "rtt_avg": f"{latency_tracker.avg_rtt:.2f} ms",
                "rtt_max": f"{latency_tracker.max_rtt:.2f} ms",
            }
            return results
        except Exception as e:
            print_error(f"Ping error: {e}")
            return {}

def traceroute_target(target: str, max_hops: int = TRACEROUTE_MAX_HOPS) -> List[Dict[str, Any]]:
    """Perform traceroute to a target and display hop latency details."""
    print_section(f"Traceroute: {target}")
    if not validate_target(target):
        return []
    if not check_command_availability("traceroute"):
        console.print("[bold #BF616A]Traceroute command not available[/bold #BF616A]")
        return []
    spinner = Progress(SpinnerColumn(style="bold #81A1C1"),
                       TextColumn("[progress.description]{task.description}"),
                       console=console)
    with spinner:
        task = spinner.add_task("Tracing route...", total=None)
        hops = []
        trace_cmd = ["traceroute", "-m", str(max_hops), "-w", str(TRACEROUTE_TIMEOUT), target]
        try:
            process = subprocess.Popen(trace_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
            header = True
            while process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue
                if header and "traceroute to" in line:
                    header = False
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        hop_num = parts[0]
                        host = parts[1] if parts[1] != "*" else "Unknown"
                        times = []
                        for p in parts[2:]:
                            m = re.search(r"(\d+\.\d+)\s*ms", p)
                            if m:
                                times.append(float(m.group(1)))
                        avg_time = sum(times)/len(times) if times else None
                        hops.append({
                            "hop": hop_num,
                            "host": host,
                            "times": times,
                            "avg_time_ms": avg_time,
                        })
                    except Exception:
                        continue
            spinner.stop(f"[bold #8FBCBB]Traceroute completed with {len(hops)} hops[/bold #8FBCBB]")
            if hops:
                console.print(f"[bold]{'Hop':<4} {'Host':<20} {'Avg Time':<10}[/bold]")
                console.print("─" * 50)
                for hop in hops:
                    avg = hop.get("avg_time_ms")
                    if avg is None:
                        avg_str = "---"
                        color = "#BF616A"
                    else:
                        avg_str = f"{avg:.2f} ms"
                        color = "#8FBCBB" if avg < 20 else ("#EBCB8B" if avg < 100 else "#BF616A")
                    console.print(f"{hop.get('hop', '?'):<4} {hop.get('host', 'Unknown'):<20} [{color}]{avg_str:<10}[/{color}]")
            else:
                console.print("[bold #EBCB8B]No hops found[/bold #EBCB8B]")
            return hops
        except Exception as e:
            spinner.stop(f"[bold #BF616A]Traceroute error: {e}[/bold #BF616A]")
            return []

def dns_lookup(hostname: str, record_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Perform DNS lookup for a hostname and display results."""
    print_section(f"DNS Lookup: {hostname}")
    if not validate_target(hostname):
        return {}
    if record_types is None:
        record_types = ["A", "AAAA"]
    results = {"hostname": hostname}
    spinner = Progress(SpinnerColumn(style="bold #81A1C1"),
                       TextColumn("[progress.description]{task.description}"),
                       console=console)
    with spinner:
        task = spinner.add_task("Looking up DNS records...", total=None)
        try:
            try:
                addrs = socket.getaddrinfo(hostname, None)
                for addr in addrs:
                    ip = addr[4][0]
                    rec_type = "AAAA" if ":" in ip else "A"
                    results.setdefault(rec_type, []).append(ip)
            except socket.gaierror:
                pass
            if check_command_availability("dig"):
                for rt in record_types:
                    spinner.update(task, description=f"Looking up {rt} records...")
                    try:
                        dig_out = subprocess.check_output(["dig", "+noall", "+answer", hostname, rt], universal_newlines=True)
                        recs = []
                        for line in dig_out.splitlines():
                            parts = line.split()
                            if len(parts) >= 5:
                                recs.append({"name": parts[0], "ttl": parts[1], "type": parts[3], "value": " ".join(parts[4:])})
                        if recs:
                            results[rt] = recs
                    except subprocess.CalledProcessError:
                        continue
            elif check_command_availability("nslookup"):
                for rt in record_types:
                    spinner.update(task, description=f"Looking up {rt} records...")
                    try:
                        ns_out = subprocess.check_output(["nslookup", "-type=" + rt, hostname], universal_newlines=True)
                        recs = []
                        for line in ns_out.splitlines():
                            if "Address: " in line and not line.startswith("Server:"):
                                recs.append({"name": hostname, "type": rt, "value": line.split("Address: ")[1].strip()})
                        if recs:
                            results[rt] = recs
                    except subprocess.CalledProcessError:
                        continue
            spinner.stop(f"[bold #8FBCBB]DNS lookup completed[/bold #8FBCBB]")
            if len(results) <= 1:
                console.print(f"[bold #EBCB8B]No DNS records found for {hostname}[/bold #EBCB8B]")
            else:
                for rt, recs in results.items():
                    if rt == "hostname":
                        continue
                    console.print(f"[bold #88C0D0]{rt} Records:[/bold #88C0D0]")
                    for rec in recs:
                        console.print(f"  {rec.get('value')}")
            return results
        except Exception as e:
            spinner.stop(f"[bold #BF616A]DNS lookup error: {e}[/bold #BF616A]")
            return {"hostname": hostname}

def port_scan(target: str, ports: Union[List[int], str] = "common", timeout: float = PORT_SCAN_TIMEOUT) -> Dict[int, Dict[str, Any]]:
    """Scan for open ports on a target host and display results."""
    print_section(f"Port Scan: {target}")
    if not validate_target(target):
        return {}
    if ports == "common":
        port_list = PORT_SCAN_COMMON_PORTS
    elif isinstance(ports, str):
        try:
            if "-" in ports:
                start, end = map(int, ports.split("-"))
                port_list = list(range(start, end + 1))
            else:
                port_list = list(map(int, ports.split(",")))
        except ValueError:
            console.print(f"[bold #BF616A]Invalid port specification: {ports}[/bold #BF616A]")
            return {}
    else:
        port_list = ports
    open_ports = {}
    progress_task = Progress(SpinnerColumn(style="bold #81A1C1"),
                             TextColumn("[progress.description]{task.description}"),
                             BarColumn(style="bold #88C0D0"),
                             console=console)
    with progress_task as progress:
        task = progress.add_task(f"Scanning {len(port_list)} ports...", total=len(port_list))
        try:
            ip = socket.gethostbyname(target)
            for i, port in enumerate(port_list):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                if sock.connect_ex((ip, port)) == 0:
                    try:
                        service = socket.getservbyport(port)
                    except Exception:
                        service = PORT_SERVICES.get(port, "unknown")
                    open_ports[port] = {"state": "open", "service": service}
                    console.print(f"\r[bold #8FBCBB]Port {port} is open: {service}[/bold #8FBCBB]")
                sock.close()
                progress.update(task, advance=1)
            console.print("")
            if open_ports:
                console.print(f"[bold #8FBCBB]Found {len(open_ports)} open ports on {target} ({ip})[/bold #8FBCBB]")
                console.print(f"[bold]{'Port':<7} {'State':<10} {'Service':<15}[/bold]")
                console.print("─" * 40)
                for port in sorted(open_ports.keys()):
                    info = open_ports[port]
                    console.print(f"[bold #88C0D0]{port:<7}[/bold #88C0D0] [bold #8FBCBB]{info['state']:<10}[/bold #8FBCBB] {info['service']:<15}")
            else:
                console.print(f"[bold #EBCB8B]No open ports found on {target} ({ip})[/bold #EBCB8B]")
            return open_ports
        except Exception as e:
            console.print(f"[bold #BF616A]Port scan error: {e}[/bold #BF616A]")
            return {}

def monitor_latency(target: str, count: int = MONITOR_DEFAULT_COUNT, interval: float = MONITOR_DEFAULT_INTERVAL) -> None:
    """Continuously monitor network latency to a target and display an ASCII graph."""
    print_section(f"Latency Monitor: {target}")
    if not validate_target(target):
        return
    latency_tracker = LatencyTracker(width=RTT_GRAPH_WIDTH)
    console.print(f"Monitoring latency to {target}. Press Ctrl+C to stop.")
    try:
        if not check_command_availability("ping"):
            console.print(f"[bold #BF616A]Ping command not available[/bold #BF616A]")
            return
        ping_indefinitely = (count == 0)
        remaining = count
        while ping_indefinitely or remaining > 0:
            ping_cmd = ["ping", "-c", "1", "-i", str(interval), target]
            try:
                start = time.time()
                output = subprocess.check_output(ping_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
                m = re.search(r"time=(\d+\.?\d*)", output)
                if m:
                    rtt = float(m.group(1))
                    latency_tracker.add_result(rtt)
                else:
                    latency_tracker.add_result(None)
            except subprocess.CalledProcessError:
                latency_tracker.add_result(None)
            os.system("clear")
            print_header(f"Latency Monitor: {target}")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            console.print(f"[bold]Time:[/bold] {now} | [bold]Current:[/bold] {latency_tracker.history[-1] if latency_tracker.history[-1] is not None else 'timeout'} ms")
            latency_tracker.display_graph()
            if not ping_indefinitely:
                remaining -= 1
            elapsed = time.time() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)
        print_section("Final Statistics")
        latency_tracker.display_statistics()
    except KeyboardInterrupt:
        print("\n")
        print_section("Monitoring Stopped")
        console.print(f"Total pings: {latency_tracker.total_count}")
        latency_tracker.display_statistics()

def bandwidth_test(target: str = "example.com", size: int = BANDWIDTH_TEST_SIZE) -> Dict[str, Any]:
    """Perform a simple bandwidth test to a target and display download speed."""
    print_section("Bandwidth Test")
    if not validate_target(target):
        return {}
    results = {"target": target, "download_speed": 0.0, "response_time": 0.0}
    console.print(f"Starting bandwidth test to {target}...")
    console.print("[bold #EBCB8B]Note: This is a simple test and may not be fully accurate.[/bold #EBCB8B]")
    try:
        ip = socket.gethostbyname(target)
        console.print(f"Resolved {target} to {ip}")
        progress_task = Progress(SpinnerColumn(style="bold #81A1C1"),
                                 TextColumn("[progress.description]{task.description}"),
                                 BarColumn(style="bold #88C0D0"),
                                 console=console)
        with progress_task as progress:
            task = progress.add_task("Downloading test file...", total=1)
            if shutil.which("curl"):
                start = time.time()
                curl_cmd = ["curl", "-o", "/dev/null", "-s", "--connect-timeout", "5", "-w", "%{time_total} %{size_download} %{speed_download}", f"http://{target}"]
                output = subprocess.check_output(curl_cmd, universal_newlines=True)
                parts = output.split()
                if len(parts) >= 3:
                    total_time = float(parts[0])
                    size_download = int(parts[1])
                    speed_download = float(parts[2])
                    results["response_time"] = total_time
                    results["download_speed"] = speed_download
                    results["download_size"] = size_download
                    progress.update(task, completed=1)
                    download_mbps = speed_download * 8 / 1024 / 1024
                    console.print(f"\n[bold #8FBCBB]Download test completed:[/bold #8FBCBB]")
                    console.print(f"  Response time: {total_time:.2f} s")
                    console.print(f"  Downloaded: {size_download / (1024*1024):.2f} MB")
                    console.print(f"  Speed: {speed_download / (1024*1024):.2f} MB/s ({download_mbps:.2f} Mbps)")
            else:
                console.print(f"[bold #EBCB8B]Curl not available, using socket test[/bold #EBCB8B]")
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((ip, 80))
                conn_time = time.time() - start
                request = f"GET / HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n"
                start = time.time()
                sock.sendall(request.encode())
                bytes_received = 0
                while True:
                    chunk = sock.recv(BANDWIDTH_CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_received += len(chunk)
                    progress.update(task, completed=min(1, bytes_received / size))
                end = time.time()
                sock.close()
                transfer_time = end - start
                speed = bytes_received / transfer_time if transfer_time > 0 else 0
                results["response_time"] = conn_time
                results["download_speed"] = speed
                results["download_size"] = bytes_received
                download_mbps = speed * 8 / 1024 / 1024
                console.print(f"\n[bold #8FBCBB]Basic bandwidth test completed:[/bold #8FBCBB]")
                console.print(f"  Connection time: {conn_time:.2f} s")
                console.print(f"  Downloaded: {bytes_received/1024:.2f} KB")
                console.print(f"  Speed: {speed/1024:.2f} KB/s ({download_mbps:.2f} Mbps)")
        return results
    except Exception as e:
        console.print(f"[bold #BF616A]Bandwidth test error: {e}[/bold #BF616A]")
        return results

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.group()
def cli() -> None:
    """Enhanced Network Information and Diagnostics Tool"""
    print_header("Network Toolkit")
    console.print(f"System: [bold #D8DEE9]{platform.system()} {platform.release()}[/bold #D8DEE9]")
    console.print(f"Python: [bold #D8DEE9]{platform.python_version()}[/bold #D8DEE9]")
    console.print(f"Hostname: [bold #D8DEE9]{socket.gethostname()}[/bold #D8DEE9]")
    console.print(f"Date: [bold #D8DEE9]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")
    check_root_privileges()

@cli.command()
def interfaces() -> None:
    """List and analyze network interfaces."""
    get_network_interfaces()

@cli.command()
def ip() -> None:
    """Display IP address information for all interfaces."""
    get_ip_addresses()

@cli.command()
@click.argument("target")
@click.option("-c", "--count", type=int, default=PING_COUNT_DEFAULT, help="Number of ping attempts")
@click.option("-i", "--interval", type=float, default=PING_INTERVAL_DEFAULT, help="Ping interval in seconds")
def ping(target: str, count: int, interval: float) -> None:
    """Test connectivity to a target."""
    ping_target(target, count, interval)

@cli.command()
@click.argument("target")
@click.option("-m", "--max-hops", type=int, default=TRACEROUTE_MAX_HOPS, help="Maximum hops")
def traceroute(target: str, max_hops: int) -> None:
    """Trace network path to a target."""
    traceroute_target(target, max_hops)

@cli.command()
@click.argument("hostname")
@click.option("-t", "--types", default="A,AAAA", help="Comma-separated list of DNS record types")
def dns(hostname: str, types: str) -> None:
    """Perform DNS lookup."""
    rec_types = [t.strip() for t in types.split(",")]
    dns_lookup(hostname, rec_types)

@cli.command()
@click.argument("target")
@click.option("-p", "--ports", default="common", help="Ports to scan: 'common', comma-separated list, or range (e.g., 80-443)")
@click.option("-t", "--timeout", type=float, default=PORT_SCAN_TIMEOUT, help="Timeout per port (seconds)")
def scan(target: str, ports: str, timeout: float) -> None:
    """Scan for open ports on a target host."""
    port_scan(target, ports, timeout)

@cli.command()
@click.argument("target")
@click.option("-c", "--count", type=int, default=MONITOR_DEFAULT_COUNT, help="Number of pings (0 for unlimited)")
@click.option("-i", "--interval", type=float, default=MONITOR_DEFAULT_INTERVAL, help="Ping interval in seconds")
def monitor(target: str, count: int, interval: float) -> None:
    """Monitor network latency over time."""
    monitor_latency(target, count, interval)

@cli.command()
@click.option("-t", "--target", default="example.com", help="Target hostname for bandwidth test")
def bandwidth(target: str) -> None:
    """Perform a simple bandwidth test."""
    bandwidth_test(target)

def main() -> None:
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print(f"\n[bold #EBCB8B]Operation interrupted by user[/bold #EBCB8B]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[bold #BF616A]Unexpected error: {e}[/bold #BF616A]")
        sys.exit(1)

atexit.register(lambda: console.print("[dim]Cleaning up resources...[/dim]"))
signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(130))
signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(128 + sig))

if __name__ == "__main__":
    main()