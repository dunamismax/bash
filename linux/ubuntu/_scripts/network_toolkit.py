#!/usr/bin/env python3
"""
Enhanced Network Information and Diagnostics Tool
------------------------------------------------

A beautiful, interactive terminal-based utility for comprehensive network analysis and diagnostics.
This tool provides operations including:
  • Network interfaces - List and analyze network interfaces with detailed statistics
  • IP addresses      - Display IP address information for all interfaces
  • Ping              - Test connectivity to a target with visual response time tracking
  • Traceroute        - Trace network path to a target with hop latency visualization
  • DNS lookup        - Perform DNS lookups with multiple record types
  • Port scan         - Scan for open ports on a target host
  • Latency monitor   - Monitor network latency to a target over time
  • Bandwidth test    - Perform a simple bandwidth test

All functionality is menu-driven with an attractive Nord-themed interface.

Note: Some operations require root privileges.

Version: 1.0.0
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
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskID,
)
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Network Toolkit"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.expanduser("~/network_toolkit_logs/network_toolkit.log")

# Network operation constants
PING_COUNT_DEFAULT = 4
PING_INTERVAL_DEFAULT = 1.0
TRACEROUTE_MAX_HOPS = 30
TRACEROUTE_TIMEOUT = 5.0
MONITOR_DEFAULT_INTERVAL = 1.0
MONITOR_DEFAULT_COUNT = 100
PORT_SCAN_TIMEOUT = 1.0
PORT_SCAN_COMMON_PORTS = [
    21,
    22,
    23,
    25,
    53,
    80,
    110,
    123,
    143,
    443,
    465,
    587,
    993,
    995,
    3306,
    3389,
    5432,
    8080,
    8443,
]
DNS_TYPES = ["A", "AAAA", "MX", "NS", "SOA", "TXT", "CNAME"]
BANDWIDTH_TEST_SIZE = 10 * 1024 * 1024  # 10MB
BANDWIDTH_CHUNK_SIZE = 64 * 1024  # 64KB

# Visualization constants
PROGRESS_WIDTH = 50
UPDATE_INTERVAL = 0.1
MAX_LATENCY_HISTORY = 100
RTT_GRAPH_WIDTH = 60
RTT_GRAPH_HEIGHT = 10

# Common service mappings for port scan
PORT_SERVICES = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    443: "HTTPS",
    465: "SMTP/SSL",
    587: "SMTP/TLS",
    993: "IMAP/SSL",
    995: "POP3/SSL",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    8080: "HTTP-ALT",
    8443: "HTTPS-ALT",
}

# Check for required commands
COMMANDS = {
    "ip": shutil.which("ip") is not None,
    "ping": shutil.which("ping") is not None,
    "traceroute": shutil.which("traceroute") is not None,
    "dig": shutil.which("dig") is not None,
    "nslookup": shutil.which("nslookup") is not None,
    "nmap": shutil.which("nmap") is not None,
    "ifconfig": shutil.which("ifconfig") is not None,
}

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()


class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark/background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"

    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"

    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"

    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Get a choice from the user with a styled prompt."""
    return Prompt.ask(
        f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Get confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")

    for key, description in options:
        table.add_row(key, description)

    return table


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
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


# ==============================
# Logging Setup
# ==============================
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add specific cleanup tasks here if needed


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ==============================
# Progress Tracking Classes
# ==============================
class ProgressManager:
    """Unified progress tracking system with multiple display options."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.NORD8
    ) -> TaskID:
        """Add a new task to the progress manager."""
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        """Update a task's progress."""
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self):
        """Start displaying the progress bar."""
        self.progress.start()

    def stop(self):
        """Stop displaying the progress bar."""
        self.progress.stop()


class Spinner:
    """Thread-safe spinner for indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Internal method to update the spinner."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)  # Spinner update interval

    def start(self) -> None:
        """Start the spinner."""
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner and display completion message."""
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            # Clear the line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            if success:
                console.print(
                    f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD14}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD11}]failed[/] after {time_str}"
                )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit."""
        self.stop(success=exc_type is None)


# ==============================
# Latency Tracking
# ==============================
class LatencyTracker:
    """
    Tracks network latency measurements and provides statistics and an ASCII graph.
    """

    def __init__(
        self, max_history: int = MAX_LATENCY_HISTORY, width: int = RTT_GRAPH_WIDTH
    ):
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
            loss_pct = (
                (self.loss_count / self.total_count * 100) if self.total_count else 0
            )
            min_rtt = self.min_rtt if self.min_rtt != float("inf") else 0
            console.print(f"[bold {NordColors.NORD7}]RTT Statistics:[/]")
            console.print(f"  Min: [dim]{min_rtt:.2f} ms[/dim]")
            console.print(f"  Avg: [dim]{self.avg_rtt:.2f} ms[/dim]")
            console.print(f"  Max: [dim]{self.max_rtt:.2f} ms[/dim]")
            console.print(
                f"  Packet Loss: [bold]{loss_pct:.1f}%[/bold] ({self.loss_count}/{self.total_count})"
            )

    def display_graph(self) -> None:
        with self._lock:
            valid = [r for r in self.history if r is not None]
            if not valid:
                console.print(
                    f"[bold {NordColors.NORD13}]No latency data to display graph[/]"
                )
                return
            min_val, max_val = min(valid), max(valid)
            if max_val - min_val < 5:
                max_val = min_val + 5
            graph = []
            for rtt in list(self.history)[-self.width :]:
                if rtt is None:
                    graph.append("×")
                else:
                    ratio = (rtt - min_val) / (max_val - min_val)
                    if rtt < self.avg_rtt * 0.8:
                        color = NordColors.NORD7
                    elif rtt < self.avg_rtt * 1.2:
                        color = NordColors.NORD4
                    else:
                        color = NordColors.NORD13
                    graph.append(f"[{color}]█[/{color}]")
            console.print("\n[dim]Latency Graph:[/dim]")
            console.print("".join(graph))
            console.print(f"[dim]Min: {min_val:.1f} ms | Max: {max_val:.1f} ms[/dim]")


# ==============================
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 60,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
    if verbose:
        if shell:
            print_step(f"Executing: {cmd}")
        else:
            print_step(f"Executing: {' '.join(cmd)}")

    try:
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        if shell:
            print_error(f"Command failed: {cmd}")
        else:
            print_error(f"Command failed: {' '.join(cmd)}")

        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.NORD11}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


def check_root() -> bool:
    """Check if script is running with elevated privileges."""
    return os.geteuid() == 0


def ensure_root() -> None:
    """Ensure the script is run with root privileges."""
    if not check_root():
        print_warning("This operation performs better with root privileges.")
        print_info("Some functionality may be limited.")


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


# ==============================
# Network Operation Functions
# ==============================
def get_network_interfaces() -> List[Dict[str, Any]]:
    """Retrieve and display network interface information."""
    print_section("Network Interfaces")
    interfaces = []
    spinner = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=f"bold {NordColors.NORD8}"),
        TimeRemainingColumn(),
        console=console,
    )
    with spinner:
        task = spinner.add_task("Collecting interface info...", total=None)
        try:
            if check_command_availability("ip"):
                output = subprocess.check_output(
                    ["ip", "-o", "link", "show"], universal_newlines=True
                )
                for line in output.splitlines():
                    m = re.search(r"^\d+:\s+([^:@]+).*state\s+(\w+)", line)
                    if m:
                        name, state = m.groups()
                        if name.strip() == "lo":
                            continue
                        hw = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", line)
                        mac = hw.group(1) if hw else "Unknown"
                        interfaces.append(
                            {
                                "name": name.strip(),
                                "status": state,
                                "mac_address": mac,
                            }
                        )
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
                        interfaces.append(
                            {
                                "name": current,
                                "status": "unknown",
                                "mac_address": "Unknown",
                            }
                        )
                    elif current and "ether" in line:
                        m = re.search(r"ether\s+([0-9a-fA-F:]+)", line)
                        if m:
                            for iface in interfaces:
                                if iface["name"] == current:
                                    iface["mac_address"] = m.group(1)
            spinner.stop()

            if interfaces:
                print_success(f"Found {len(interfaces)} interfaces")
                console.print(
                    f"[bold]{'Interface':<12} {'Status':<10} {'MAC Address':<20}[/bold]"
                )
                console.print("─" * 50)
                for iface in interfaces:
                    status_color = (
                        NordColors.NORD14
                        if iface["status"].lower() in ["up", "active"]
                        else NordColors.NORD11
                    )
                    console.print(
                        f"[bold {NordColors.NORD8}]{iface['name']:<12}[/] "
                        f"[{status_color}]{iface['status']:<10}[/] "
                        f"{iface['mac_address']:<20}"
                    )
            else:
                console.print(
                    f"[bold {NordColors.NORD13}]No network interfaces found[/]"
                )
            return interfaces
        except Exception as e:
            spinner.stop()
            print_error(f"Error: {e}")
            return []


def get_ip_addresses() -> Dict[str, List[Dict[str, str]]]:
    """Retrieve and display IP address information for all interfaces."""
    print_section("IP Address Information")
    ip_info = {}
    spinner = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )
    with spinner:
        task = spinner.add_task("Collecting IP addresses...", total=None)
        try:
            if check_command_availability("ip"):
                output = subprocess.check_output(
                    ["ip", "-o", "addr"], universal_newlines=True
                )
                for line in output.splitlines():
                    parts = line.split()
                    if len(parts) >= 4:
                        iface = parts[1]
                        if iface == "lo":
                            continue
                        if "inet" in line:
                            m = re.search(r"inet\s+([^/]+)", line)
                            if m:
                                ip_info.setdefault(iface, []).append(
                                    {"type": "IPv4", "address": m.group(1)}
                                )
                        if "inet6" in line:
                            m = re.search(r"inet6\s+([^/]+)", line)
                            if m and not m.group(1).startswith("fe80"):
                                ip_info.setdefault(iface, []).append(
                                    {"type": "IPv6", "address": m.group(1)}
                                )
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
                            ip_info.setdefault(current, []).append(
                                {"type": "IPv4", "address": m.group(1)}
                            )
                    elif current and "inet6 " in line:
                        m = re.search(r"inet6\s+([0-9a-f:]+)", line)
                        if m and not m.group(1).startswith("fe80"):
                            ip_info.setdefault(current, []).append(
                                {"type": "IPv6", "address": m.group(1)}
                            )
            spinner.stop()

            if ip_info:
                print_success("IP information collected")
                for iface, addrs in ip_info.items():
                    console.print(f"[bold {NordColors.NORD8}]{iface}:[/]")
                    for addr in addrs:
                        type_color = (
                            NordColors.NORD8
                            if addr["type"] == "IPv4"
                            else NordColors.NORD15
                        )
                        console.print(
                            f"  [{type_color}]{addr['type']:<6}[/]: {addr['address']}"
                        )
            else:
                console.print(f"[bold {NordColors.NORD13}]No IP addresses found[/]")
            return ip_info
        except Exception as e:
            spinner.stop()
            print_error(f"Error: {e}")
            return {}


def ping_target(
    target: str,
    count: int = PING_COUNT_DEFAULT,
    interval: float = PING_INTERVAL_DEFAULT,
) -> Dict[str, Any]:
    """Ping a target and display real-time latency results."""
    print_section(f"Ping: {target}")
    if not validate_target(target):
        return {}
    if not check_command_availability("ping"):
        print_error("Ping command not available")
        return {}
    progress_task = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=f"bold {NordColors.NORD8}"),
        TimeRemainingColumn(),
        console=console,
    )
    latency_tracker = LatencyTracker()
    with progress_task as progress:
        task = progress.add_task("Pinging...", total=count)
        ping_cmd = ["ping", "-c", str(count), "-i", str(interval), target]
        try:
            process = subprocess.Popen(
                ping_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )
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
                    console.print(f"\r[bold {NordColors.NORD11}]Request timed out[/]")
            # Ensure complete progress
            progress.update(task, completed=count)
            console.print("")
            latency_tracker.display_statistics()
            latency_tracker.display_graph()
            results = {
                "target": target,
                "sent": latency_tracker.total_count,
                "received": latency_tracker.total_count - latency_tracker.loss_count,
                "packet_loss": f"{(latency_tracker.loss_count / latency_tracker.total_count * 100):.1f}%",
                "rtt_min": f"{latency_tracker.min_rtt:.2f} ms",
                "rtt_avg": f"{latency_tracker.avg_rtt:.2f} ms",
                "rtt_max": f"{latency_tracker.max_rtt:.2f} ms",
            }
            return results
        except Exception as e:
            print_error(f"Ping error: {e}")
            return {}


def traceroute_target(
    target: str, max_hops: int = TRACEROUTE_MAX_HOPS
) -> List[Dict[str, Any]]:
    """Perform traceroute to a target and display hop latency details."""
    print_section(f"Traceroute: {target}")
    if not validate_target(target):
        return []
    if not check_command_availability("traceroute"):
        print_error("Traceroute command not available")
        return []
    spinner = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )
    with spinner:
        task = spinner.add_task("Tracing route...", total=None)
        hops = []
        trace_cmd = [
            "traceroute",
            "-m",
            str(max_hops),
            "-w",
            str(TRACEROUTE_TIMEOUT),
            target,
        ]
        try:
            process = subprocess.Popen(
                trace_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )
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
                        avg_time = sum(times) / len(times) if times else None
                        hops.append(
                            {
                                "hop": hop_num,
                                "host": host,
                                "times": times,
                                "avg_time_ms": avg_time,
                            }
                        )
                    except Exception:
                        continue
            spinner.stop()

            if hops:
                print_success(f"Traceroute completed with {len(hops)} hops")
                console.print(f"[bold]{'Hop':<4} {'Host':<30} {'Avg Time':<10}[/bold]")
                console.print("─" * 50)
                for hop in hops:
                    avg = hop.get("avg_time_ms")
                    if avg is None:
                        avg_str = "---"
                        color = NordColors.NORD11
                    else:
                        avg_str = f"{avg:.2f} ms"
                        color = (
                            NordColors.NORD14
                            if avg < 20
                            else (NordColors.NORD13 if avg < 100 else NordColors.NORD11)
                        )
                    console.print(
                        f"{hop.get('hop', '?'):<4} {hop.get('host', 'Unknown'):<30} [{color}]{avg_str:<10}[/]"
                    )
            else:
                console.print(f"[bold {NordColors.NORD13}]No hops found[/]")
            return hops
        except Exception as e:
            spinner.stop()
            print_error(f"Traceroute error: {e}")
            return []


def dns_lookup(
    hostname: str, record_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Perform DNS lookup for a hostname and display results."""
    print_section(f"DNS Lookup: {hostname}")
    if not validate_target(hostname):
        return {}
    if record_types is None:
        record_types = ["A", "AAAA"]
    results = {"hostname": hostname}
    spinner = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )
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
                        dig_out = subprocess.check_output(
                            ["dig", "+noall", "+answer", hostname, rt],
                            universal_newlines=True,
                        )
                        recs = []
                        for line in dig_out.splitlines():
                            parts = line.split()
                            if len(parts) >= 5:
                                recs.append(
                                    {
                                        "name": parts[0],
                                        "ttl": parts[1],
                                        "type": parts[3],
                                        "value": " ".join(parts[4:]),
                                    }
                                )
                        if recs:
                            results[rt] = recs
                    except subprocess.CalledProcessError:
                        continue
            elif check_command_availability("nslookup"):
                for rt in record_types:
                    spinner.update(task, description=f"Looking up {rt} records...")
                    try:
                        ns_out = subprocess.check_output(
                            ["nslookup", "-type=" + rt, hostname],
                            universal_newlines=True,
                        )
                        recs = []
                        for line in ns_out.splitlines():
                            if "Address: " in line and not line.startswith("Server:"):
                                recs.append(
                                    {
                                        "name": hostname,
                                        "type": rt,
                                        "value": line.split("Address: ")[1].strip(),
                                    }
                                )
                        if recs:
                            results[rt] = recs
                    except subprocess.CalledProcessError:
                        continue
            spinner.stop()

            if len(results) <= 1:
                console.print(
                    f"[bold {NordColors.NORD13}]No DNS records found for {hostname}[/]"
                )
            else:
                print_success("DNS lookup completed")
                for rt, recs in results.items():
                    if rt == "hostname":
                        continue
                    console.print(f"[bold {NordColors.NORD8}]{rt} Records:[/]")
                    if isinstance(recs, list) and isinstance(recs[0], dict):
                        for rec in recs:
                            console.print(f"  {rec.get('value')}")
                    else:
                        for rec in recs:
                            console.print(f"  {rec}")
            return results
        except Exception as e:
            spinner.stop()
            print_error(f"DNS lookup error: {e}")
            return {"hostname": hostname}


def port_scan(
    target: str,
    ports: Union[List[int], str] = "common",
    timeout: float = PORT_SCAN_TIMEOUT,
) -> Dict[int, Dict[str, Any]]:
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
            print_error(f"Invalid port specification: {ports}")
            return {}
    else:
        port_list = ports
    open_ports = {}
    progress_task = Progress(
        SpinnerColumn(style=f"bold {NordColors.NORD9}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=f"bold {NordColors.NORD8}"),
        console=console,
    )
    with progress_task as progress:
        task = progress.add_task(
            f"Scanning {len(port_list)} ports...", total=len(port_list)
        )
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
                    console.print(
                        f"\r[bold {NordColors.NORD14}]Port {port} is open: {service}[/]"
                    )
                sock.close()
                progress.update(task, advance=1)
            console.print("")
            if open_ports:
                print_success(f"Found {len(open_ports)} open ports on {target} ({ip})")
                console.print(f"[bold]{'Port':<7} {'State':<10} {'Service':<15}[/bold]")
                console.print("─" * 40)
                for port in sorted(open_ports.keys()):
                    info = open_ports[port]
                    console.print(
                        f"[bold {NordColors.NORD8}]{port:<7}[/] [bold {NordColors.NORD14}]{info['state']:<10}[/] {info['service']:<15}"
                    )
            else:
                console.print(
                    f"[bold {NordColors.NORD13}]No open ports found on {target} ({ip})[/]"
                )
            return open_ports
        except Exception as e:
            print_error(f"Port scan error: {e}")
            return {}


def monitor_latency(
    target: str,
    count: int = MONITOR_DEFAULT_COUNT,
    interval: float = MONITOR_DEFAULT_INTERVAL,
) -> None:
    """Continuously monitor network latency to a target and display an ASCII graph."""
    print_section(f"Latency Monitor: {target}")
    if not validate_target(target):
        return
    latency_tracker = LatencyTracker(width=RTT_GRAPH_WIDTH)
    print_info(f"Monitoring latency to {target}. Press Ctrl+C to stop.")
    try:
        if not check_command_availability("ping"):
            print_error("Ping command not available")
            return
        ping_indefinitely = count == 0
        remaining = count
        while ping_indefinitely or remaining > 0:
            ping_cmd = ["ping", "-c", "1", "-i", str(interval), target]
            try:
                start = time.time()
                output = subprocess.check_output(
                    ping_cmd, universal_newlines=True, stderr=subprocess.STDOUT
                )
                m = re.search(r"time=(\d+\.?\d*)", output)
                if m:
                    rtt = float(m.group(1))
                    latency_tracker.add_result(rtt)
                else:
                    latency_tracker.add_result(None)
            except subprocess.CalledProcessError:
                latency_tracker.add_result(None)

            # Clear the screen to update the graph
            clear_screen()
            print_header(f"Latency Monitor: {target}")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            console.print(
                f"[bold]Time:[/bold] {now} | [bold]Current:[/bold] {latency_tracker.history[-1] if latency_tracker.history and latency_tracker.history[-1] is not None else 'timeout'} ms"
            )
            latency_tracker.display_graph()
            if not ping_indefinitely:
                remaining -= 1
                print_info(f"Remaining pings: {remaining}")

            elapsed = time.time() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)

        print_section("Final Statistics")
        latency_tracker.display_statistics()
    except KeyboardInterrupt:
        print("\n")
        print_section("Monitoring Stopped")
        print_info(f"Total pings: {latency_tracker.total_count}")
        latency_tracker.display_statistics()


def bandwidth_test(
    target: str = "example.com", size: int = BANDWIDTH_TEST_SIZE
) -> Dict[str, Any]:
    """Perform a simple bandwidth test to a target and display download speed."""
    print_section("Bandwidth Test")
    if not validate_target(target):
        return {}
    results = {"target": target, "download_speed": 0.0, "response_time": 0.0}
    print_info(f"Starting bandwidth test to {target}...")
    print_warning("Note: This is a simple test and may not be fully accurate.")
    try:
        ip = socket.gethostbyname(target)
        print_info(f"Resolved {target} to {ip}")
        progress_task = Progress(
            SpinnerColumn(style=f"bold {NordColors.NORD9}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style=f"bold {NordColors.NORD8}"),
            console=console,
        )
        with progress_task as progress:
            task = progress.add_task("Downloading test file...", total=1)
            if shutil.which("curl"):
                start = time.time()
                curl_cmd = [
                    "curl",
                    "-o",
                    "/dev/null",
                    "-s",
                    "--connect-timeout",
                    "5",
                    "-w",
                    "%{time_total} %{size_download} %{speed_download}",
                    f"http://{target}",
                ]
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
                    console.print("")
                    print_success("Download test completed")
                    console.print(f"  Response time: {total_time:.2f} s")
                    console.print(
                        f"  Downloaded: {size_download / (1024 * 1024):.2f} MB"
                    )
                    console.print(
                        f"  Speed: {speed_download / (1024 * 1024):.2f} MB/s ({download_mbps:.2f} Mbps)"
                    )
            else:
                print_warning("Curl not available, using socket test")
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((ip, 80))
                conn_time = time.time() - start
                request = (
                    f"GET / HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n"
                )
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
                console.print("")
                print_success("Basic bandwidth test completed")
                console.print(f"  Connection time: {conn_time:.2f} s")
                console.print(f"  Downloaded: {bytes_received / 1024:.2f} KB")
                console.print(
                    f"  Speed: {speed / 1024:.2f} KB/s ({download_mbps:.2f} Mbps)"
                )
        return results
    except Exception as e:
        print_error(f"Bandwidth test error: {e}")
        return results


# ==============================
# Menu Systems
# ==============================
def ping_menu() -> None:
    """Interactive menu for ping operations."""
    clear_screen()
    print_header("Ping")

    target = get_user_input("Enter target hostname or IP", "google.com")
    if not validate_target(target):
        pause()
        return

    count = get_user_input("Number of pings", str(PING_COUNT_DEFAULT))
    try:
        count = int(count)
        if count <= 0:
            print_error("Count must be a positive integer")
            pause()
            return
    except ValueError:
        print_error("Invalid count value")
        pause()
        return

    interval = get_user_input(
        "Time between pings (seconds)", str(PING_INTERVAL_DEFAULT)
    )
    try:
        interval = float(interval)
        if interval <= 0:
            print_error("Interval must be a positive number")
            pause()
            return
    except ValueError:
        print_error("Invalid interval value")
        pause()
        return

    ping_target(target, count, interval)
    pause()


def traceroute_menu() -> None:
    """Interactive menu for traceroute operations."""
    clear_screen()
    print_header("Traceroute")

    target = get_user_input("Enter target hostname or IP", "google.com")
    if not validate_target(target):
        pause()
        return

    max_hops = get_user_input("Maximum number of hops", str(TRACEROUTE_MAX_HOPS))
    try:
        max_hops = int(max_hops)
        if max_hops <= 0:
            print_error("Maximum hops must be a positive integer")
            pause()
            return
    except ValueError:
        print_error("Invalid maximum hops value")
        pause()
        return

    traceroute_target(target, max_hops)
    pause()


def dns_menu() -> None:
    """Interactive menu for DNS lookup operations."""
    clear_screen()
    print_header("DNS Lookup")

    hostname = get_user_input("Enter hostname to lookup", "example.com")
    if not validate_target(hostname):
        pause()
        return

    rec_types_str = get_user_input("Record types (comma-separated)", "A,AAAA,MX,TXT")
    rec_types = [rt.strip().upper() for rt in rec_types_str.split(",")]

    dns_lookup(hostname, rec_types)
    pause()


def scan_menu() -> None:
    """Interactive menu for port scanning operations."""
    clear_screen()
    print_header("Port Scan")

    target = get_user_input("Enter target hostname or IP", "example.com")
    if not validate_target(target):
        pause()
        return

    port_spec = get_user_input(
        "Ports to scan (common, comma-separated list, or range like 80-443)", "common"
    )

    timeout = get_user_input("Timeout per port (seconds)", str(PORT_SCAN_TIMEOUT))
    try:
        timeout = float(timeout)
        if timeout <= 0:
            print_error("Timeout must be a positive number")
            pause()
            return
    except ValueError:
        print_error("Invalid timeout value")
        pause()
        return

    port_scan(target, port_spec, timeout)
    pause()


def monitor_menu() -> None:
    """Interactive menu for latency monitoring operations."""
    clear_screen()
    print_header("Latency Monitor")

    target = get_user_input("Enter target hostname or IP", "google.com")
    if not validate_target(target):
        pause()
        return

    count = get_user_input(
        "Number of pings (0 for unlimited)", str(MONITOR_DEFAULT_COUNT)
    )
    try:
        count = int(count)
        if count < 0:
            print_error("Count must be a non-negative integer")
            pause()
            return
    except ValueError:
        print_error("Invalid count value")
        pause()
        return

    interval = get_user_input(
        "Time between pings (seconds)", str(MONITOR_DEFAULT_INTERVAL)
    )
    try:
        interval = float(interval)
        if interval <= 0:
            print_error("Interval must be a positive number")
            pause()
            return
    except ValueError:
        print_error("Invalid interval value")
        pause()
        return

    monitor_latency(target, count, interval)
    pause()


def bandwidth_menu() -> None:
    """Interactive menu for bandwidth testing operations."""
    clear_screen()
    print_header("Bandwidth Test")

    target = get_user_input("Enter target hostname or IP", "example.com")
    if not validate_target(target):
        pause()
        return

    bandwidth_test(target)
    pause()


def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"Host: {HOSTNAME}")
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Running as root: {'Yes' if check_root() else 'No'}")

        # Main menu options
        menu_options = [
            ("1", "Network Interfaces - List and analyze network interfaces"),
            ("2", "IP Addresses - Display IP address information"),
            ("3", "Ping - Test connectivity to a target"),
            ("4", "Traceroute - Trace network path to a target"),
            ("5", "DNS Lookup - Perform DNS lookups with multiple record types"),
            ("6", "Port Scan - Scan for open ports on a target host"),
            ("7", "Latency Monitor - Monitor network latency over time"),
            ("8", "Bandwidth Test - Perform a simple bandwidth test"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-8):")

        if choice == "1":
            get_network_interfaces()
            pause()
        elif choice == "2":
            get_ip_addresses()
            pause()
        elif choice == "3":
            ping_menu()
        elif choice == "4":
            traceroute_menu()
        elif choice == "5":
            dns_menu()
        elif choice == "6":
            scan_menu()
        elif choice == "7":
            monitor_menu()
        elif choice == "8":
            bandwidth_menu()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Network Toolkit.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Initial setup
        setup_logging()

        # Check if root, but don't exit if not
        if not check_root():
            print_warning(
                "Some operations may have limited functionality without root privileges."
            )

        # Launch the main menu
        main_menu()

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
