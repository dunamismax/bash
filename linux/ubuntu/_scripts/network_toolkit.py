#!/usr/bin/env python3
"""
Enhanced Network Toolkit
--------------------------------------------------

A beautiful, interactive terminal-based utility for comprehensive network analysis and diagnostics.
Features a clean Nord-styled interface for:
  • Network interfaces - View detailed interface statistics
  • IP addresses - Display IP configuration across all interfaces
  • Ping - Test connectivity with visual response time tracking
  • Traceroute - Trace network path with hop latency visualization
  • DNS lookup - Query multiple DNS record types
  • Port scan - Discover open ports with service identification
  • Latency monitor - Track network performance over time
  • Bandwidth test - Evaluate network throughput

Usage:
  Run the script and select an operation from the menu.
  - Some operations require elevated privileges for complete functionality
  - All results are displayed with intuitive visualizations

Version: 2.0.0
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
import ctypes
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.live import Live
    from rich.rule import Rule
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as rich_traceback_install
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Enable Rich tracebacks for better error reporting
rich_traceback_install(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Network Toolkit"
APP_SUBTITLE: str = "Comprehensive Diagnostics Suite"
VERSION: str = "2.0.0"
HOSTNAME: str = socket.gethostname()
LOG_FILE: str = os.path.expanduser("~/network_toolkit_logs/network_toolkit.log")

# Network operation constants
PING_COUNT_DEFAULT: int = 4
PING_INTERVAL_DEFAULT: float = 1.0
TRACEROUTE_MAX_HOPS: int = 30
TRACEROUTE_TIMEOUT: float = 5.0
MONITOR_DEFAULT_INTERVAL: float = 1.0
MONITOR_DEFAULT_COUNT: int = 100
PORT_SCAN_TIMEOUT: float = 1.0
PORT_SCAN_COMMON_PORTS: List[int] = [
    21,  # FTP
    22,  # SSH
    23,  # Telnet
    25,  # SMTP
    53,  # DNS
    80,  # HTTP
    110,  # POP3
    123,  # NTP
    143,  # IMAP
    443,  # HTTPS
    465,  # SMTP/SSL
    587,  # SMTP/TLS
    993,  # IMAP/SSL
    995,  # POP3/SSL
    3306,  # MySQL
    3389,  # RDP
    5432,  # PostgreSQL
    8080,  # HTTP-ALT
    8443,  # HTTPS-ALT
]
DNS_TYPES: List[str] = ["A", "AAAA", "MX", "NS", "SOA", "TXT", "CNAME"]
BANDWIDTH_TEST_SIZE: int = 10 * 1024 * 1024  # 10MB
BANDWIDTH_CHUNK_SIZE: int = 64 * 1024  # 64KB

# Visualization constants
PROGRESS_WIDTH: int = 50
UPDATE_INTERVAL: float = 0.1
MAX_LATENCY_HISTORY: int = 100
RTT_GRAPH_WIDTH: int = 60
RTT_GRAPH_HEIGHT: int = 10

# Terminal dimensions
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT: int = min(shutil.get_terminal_size().lines, 30)

# Check for required commands
COMMANDS: Dict[str, bool] = {
    "ip": shutil.which("ip") is not None,
    "ping": shutil.which("ping") is not None,
    "traceroute": shutil.which("traceroute") is not None,
    "dig": shutil.which("dig") is not None,
    "nslookup": shutil.which("nslookup") is not None,
    "nmap": shutil.which("nmap") is not None,
    "ifconfig": shutil.which("ifconfig") is not None,
}

# Common service mappings for port scan
PORT_SERVICES: Dict[int, str] = {
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


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark/background)
    NORD0 = "#2E3440"  # Darkest background
    NORD1 = "#3B4252"  # Dark background
    NORD2 = "#434C5E"  # Medium background
    NORD3 = "#4C566A"  # Light background

    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"  # Dark text
    NORD5 = "#E5E9F0"  # Medium text
    NORD6 = "#ECEFF4"  # Light text

    # Frost (blue accents)
    NORD7 = "#8FBCBB"  # Light teal
    NORD8 = "#88C0D0"  # Light blue
    NORD9 = "#81A1C1"  # Medium blue
    NORD10 = "#5E81AC"  # Dark blue

    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class NetworkInterface:
    """
    Represents a network interface with its properties.

    Attributes:
        name: Interface name (e.g., eth0, wlan0)
        status: Interface status (up, down, unknown)
        mac_address: MAC address of the interface
        ip_addresses: List of IP addresses assigned to this interface
    """

    name: str
    status: str
    mac_address: str
    ip_addresses: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class PingResult:
    """
    Represents the result of a ping operation.

    Attributes:
        target: Target hostname or IP
        sent: Number of packets sent
        received: Number of packets received
        packet_loss: Packet loss percentage
        rtt_min: Minimum round-trip time
        rtt_avg: Average round-trip time
        rtt_max: Maximum round-trip time
    """

    target: str
    sent: int = 0
    received: int = 0
    packet_loss: str = "0.0%"
    rtt_min: str = "0.0 ms"
    rtt_avg: str = "0.0 ms"
    rtt_max: str = "0.0 ms"


@dataclass
class TraceHop:
    """
    Represents a single hop in a traceroute.

    Attributes:
        hop: Hop number
        host: Hostname or IP
        times: List of round-trip times
        avg_time_ms: Average round-trip time
    """

    hop: str
    host: str
    times: List[float] = field(default_factory=list)
    avg_time_ms: Optional[float] = None


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["small", "slant", "mini", "digital", "standard"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
            _                      _      _              _ _    _ _   
 _ __   ___| |___      _____  _ __| | __ | |_ ___   ___ | | | _(_) |_ 
| '_ \ / _ \ __\ \ /\ / / _ \| '__| |/ / | __/ _ \ / _ \| | |/ / | __|
| | | |  __/ |_ \ V  V / (_) | |  |   <  | || (_) | (_) | |   <| | |_ 
|_| |_|\___|\__| \_/\_/ \___/|_|  |_|\_\  \__\___/ \___/|_|_|\_\_|\__|
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.NORD7,
        NordColors.NORD8,
        NordColors.NORD9,
        NordColors.NORD10,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.NORD9}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.NORD8),
        padding=(1, 1),
        title=f"[bold {NordColors.NORD5}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.NORD4}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(text: str, style: str = NordColors.NORD8, prefix: str = "•") -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")


def print_section(title: str) -> None:
    """Print a section title using a Rich rule."""
    console.rule(f"[bold {NordColors.NORD8}]{title}[/]", style=NordColors.NORD8)


def display_panel(
    message: str, style: str = NordColors.NORD8, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


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


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
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
        print_message(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_message("Continuing without logging to file...")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 60,
    verbose: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        shell: Whether to run command in a shell
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print command details
        env: Environment variables for the command

    Returns:
        CompletedProcess instance with command results
    """
    if verbose:
        print_message(f"Executing: {' '.join(cmd) if not shell else cmd}")
    try:
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            env=env or os.environ.copy(),
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd) if not shell else cmd}")
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.NORD11}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_message("Cleaning up resources...", NordColors.NORD9)
    # Add any necessary cleanup steps here


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"\nScript interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

atexit.register(cleanup)


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking system with multiple display options."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.NORD9}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None, complete_style=NordColors.NORD8),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.NORD8
    ) -> TaskID:
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


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
            time.sleep(0.1)

    def start(self) -> None:
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
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
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# Latency Tracking
# ----------------------------------------------------------------
class LatencyTracker:
    """
    Tracks network latency measurements and provides statistics and visualizations.
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
        console.print(f"[bold {NordColors.NORD7}]RTT Statistics:[/]")
        console.print(self.get_statistics_str())

    def get_statistics_str(self) -> str:
        with self._lock:
            loss_pct = (
                (self.loss_count / self.total_count * 100) if self.total_count else 0
            )
            min_rtt = self.min_rtt if self.min_rtt != float("inf") else 0
            return (
                f"Min: {min_rtt:.2f} ms\n"
                f"Avg: {self.avg_rtt:.2f} ms\n"
                f"Max: {self.max_rtt:.2f} ms\n"
                f"Packet Loss: {loss_pct:.1f}% ({self.loss_count}/{self.total_count})"
            )

    def display_graph(self) -> None:
        console.print("\n[dim]Latency Graph:[/dim]")
        console.print(self.get_graph_str())
        valid = [r for r in self.history if r is not None]
        if valid:
            min_val, max_val = min(valid), max(valid)
            console.print(f"[dim]Min: {min_val:.1f} ms | Max: {max_val:.1f} ms[/dim]")

    def get_graph_str(self) -> str:
        with self._lock:
            valid = [r for r in self.history if r is not None]
            if not valid:
                return f"[bold {NordColors.NORD13}]No latency data to display graph[/]"
            min_val, max_val = min(valid), max(valid)
            if max_val - min_val < 5:
                max_val = min_val + 5
            graph = []
            for rtt in list(self.history)[-self.width :]:
                if rtt is None:
                    graph.append("×")
                else:
                    if rtt < self.avg_rtt * 0.8:
                        color = NordColors.NORD14  # Good latency
                    elif rtt < self.avg_rtt * 1.2:
                        color = NordColors.NORD4  # Average latency
                    else:
                        color = NordColors.NORD13  # High latency
                    graph.append(f"[{color}]█[/{color}]")
            return "".join(graph)


# ----------------------------------------------------------------
# System Helper Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """Check if the script is running with root privileges."""
    if sys.platform.startswith("win"):
        # On Windows, check if running as administrator
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False
    else:
        # On Unix-like systems, check if UID is 0
        return os.geteuid() == 0


def ensure_root() -> None:
    """Warn if the script is not running with root privileges."""
    if not check_root():
        print_warning("This operation performs better with root privileges.")
        print_message("Some functionality may be limited.", NordColors.NORD9)


def is_valid_ip(ip: str) -> bool:
    """Validate if a string is a valid IP address."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_valid_hostname(hostname: str) -> bool:
    """Validate if a string is a valid hostname."""
    pattern = re.compile(
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    return bool(pattern.match(hostname))


def validate_target(target: str) -> bool:
    """Validate if a target is a valid IP or hostname."""
    if is_valid_ip(target) or is_valid_hostname(target):
        return True
    print_error(f"Invalid target: {target}")
    return False


def check_command_availability(command: str) -> bool:
    """Check if a required command is available on the system."""
    if not COMMANDS.get(command, False):
        print_error(f"Required command '{command}' is not available.")
        return False
    return True


# ----------------------------------------------------------------
# Network Operation Functions
# ----------------------------------------------------------------
def get_network_interfaces() -> List[NetworkInterface]:
    """
    List and analyze network interfaces.

    Returns:
        List of NetworkInterface objects with detailed information
    """
    print_section("Network Interfaces")
    interfaces = []

    with ProgressManager() as progress:
        task = progress.add_task("Collecting interface info...", total=None)
        try:
            if check_command_availability("ip"):
                # Get interface information using 'ip' command
                output = run_command(["ip", "-o", "link", "show"], check=False).stdout
                for line in output.splitlines():
                    m = re.search(r"^\d+:\s+([^:@]+).*state\s+(\w+)", line)
                    if m:
                        name, state = m.groups()
                        if name.strip() == "lo":
                            continue
                        hw = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", line)
                        mac = hw.group(1) if hw else "Unknown"
                        interfaces.append(
                            NetworkInterface(
                                name=name.strip(), status=state, mac_address=mac
                            )
                        )

            elif check_command_availability("ifconfig"):
                # Fall back to 'ifconfig' if 'ip' is not available
                output = run_command(["ifconfig"], check=False).stdout
                current = None
                for line in output.splitlines():
                    iface = re.match(r"^(\w+):", line)
                    if iface:
                        current = iface.group(1)
                        if current == "lo":
                            current = None
                            continue
                        interfaces.append(
                            NetworkInterface(
                                name=current, status="unknown", mac_address="Unknown"
                            )
                        )
                    elif current and "ether" in line:
                        m = re.search(r"ether\s+([0-9a-fA-F:]+)", line)
                        if m:
                            for iface in interfaces:
                                if iface.name == current:
                                    iface.mac_address = m.group(1)

            # Get IP address information for each interface
            if interfaces:
                for iface in interfaces:
                    # Update task description to show current interface
                    progress.update(
                        task, description=f"Getting IP info for {iface.name}..."
                    )

                    # Get IP addresses for this interface
                    if check_command_availability("ip"):
                        ip_cmd = ["ip", "-o", "addr", "show", "dev", iface.name]
                        ip_output = run_command(ip_cmd, check=False).stdout

                        for line in ip_output.splitlines():
                            if "inet " in line:
                                m = re.search(r"inet\s+([^/]+)", line)
                                if m:
                                    iface.ip_addresses.append(
                                        {"type": "IPv4", "address": m.group(1)}
                                    )
                            if "inet6 " in line and "scope global" in line:
                                m = re.search(r"inet6\s+([^/]+)", line)
                                if m:
                                    iface.ip_addresses.append(
                                        {"type": "IPv6", "address": m.group(1)}
                                    )

                    elif check_command_availability("ifconfig"):
                        ip_cmd = ["ifconfig", iface.name]
                        ip_output = run_command(ip_cmd, check=False).stdout

                        for line in ip_output.splitlines():
                            if "inet " in line:
                                m = re.search(r"inet\s+([0-9.]+)", line)
                                if m:
                                    iface.ip_addresses.append(
                                        {"type": "IPv4", "address": m.group(1)}
                                    )
                            if "inet6 " in line and not "fe80::" in line:
                                m = re.search(r"inet6\s+([0-9a-f:]+)", line)
                                if m:
                                    iface.ip_addresses.append(
                                        {"type": "IPv6", "address": m.group(1)}
                                    )

            # Display interfaces in a table
            if interfaces:
                print_success(f"Found {len(interfaces)} interfaces")
                table = Table(title="Network Interfaces", border_style=NordColors.NORD8)
                table.add_column(
                    "Interface", style=f"{NordColors.NORD9}", justify="left"
                )
                table.add_column("Status", style=f"{NordColors.NORD14}", justify="left")
                table.add_column(
                    "MAC Address", style=f"{NordColors.NORD4}", justify="left"
                )
                table.add_column(
                    "IP Addresses", style=f"{NordColors.NORD4}", justify="left"
                )

                for iface in interfaces:
                    # Determine status color based on interface state
                    status_color = (
                        NordColors.NORD14
                        if iface.status.lower() in ["up", "active"]
                        else NordColors.NORD11
                    )

                    # Format IP addresses
                    ip_list = []
                    for ip in iface.ip_addresses:
                        ip_type_color = (
                            NordColors.NORD8
                            if ip["type"] == "IPv4"
                            else NordColors.NORD15
                        )
                        ip_list.append(
                            f"[{ip_type_color}]{ip['type']}:[/] {ip['address']}"
                        )

                    ip_text = "\n".join(ip_list) if ip_list else "None"

                    table.add_row(
                        iface.name,
                        f"[{status_color}]{iface.status}[/]",
                        iface.mac_address,
                        ip_text,
                    )

                console.print(table)
            else:
                display_panel(
                    "No network interfaces found",
                    style=NordColors.NORD13,
                    title="Error",
                )

            return interfaces

        except Exception as e:
            print_error(f"Error collecting network interface information: {e}")
            return []


def get_ip_addresses() -> Dict[str, List[Dict[str, str]]]:
    """
    Display IP address information for all interfaces.

    Returns:
        Dictionary mapping interface names to lists of IP addresses
    """
    print_section("IP Address Information")
    ip_info = {}

    with ProgressManager() as progress:
        task = progress.add_task("Collecting IP addresses...", total=None)
        try:
            if check_command_availability("ip"):
                output = run_command(["ip", "-o", "addr"], check=False).stdout
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
                output = run_command(["ifconfig"], check=False).stdout
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

            if ip_info:
                print_success("IP information collected successfully")
                for iface, addrs in ip_info.items():
                    table = Table(
                        title=f"Interface: {iface}",
                        border_style=NordColors.NORD8,
                        show_header=True,
                    )
                    table.add_column(
                        "Type", style=f"{NordColors.NORD8}", justify="center"
                    )
                    table.add_column(
                        "Address", style=f"{NordColors.NORD4}", justify="left"
                    )

                    for addr in addrs:
                        type_color = (
                            NordColors.NORD8
                            if addr["type"] == "IPv4"
                            else NordColors.NORD15
                        )
                        table.add_row(
                            f"[{type_color}]{addr['type']}[/]", addr["address"]
                        )

                    console.print(table)
            else:
                display_panel(
                    "No IP addresses found",
                    style=NordColors.NORD13,
                    title="Information",
                )

            return ip_info

        except Exception as e:
            print_error(f"Error collecting IP address information: {e}")
            return {}


def ping_target(
    target: str,
    count: int = PING_COUNT_DEFAULT,
    interval: float = PING_INTERVAL_DEFAULT,
) -> PingResult:
    """
    Ping a target to test connectivity with visual response time tracking.

    Args:
        target: Hostname or IP address to ping
        count: Number of ping packets to send
        interval: Time between pings in seconds

    Returns:
        PingResult object with ping statistics
    """
    print_section(f"Ping: {target}")

    result = PingResult(target=target)

    if not validate_target(target):
        return result

    if not check_command_availability("ping"):
        print_error("Ping command not available")
        return result

    latency_tracker = LatencyTracker()

    with ProgressManager() as progress:
        task = progress.add_task(f"Pinging {target}...", total=count)

        try:
            # Construct ping command based on platform
            if sys.platform == "win32":
                ping_cmd = [
                    "ping",
                    "-n",
                    str(count),
                    "-w",
                    str(int(interval * 1000)),
                    target,
                ]
            else:  # Linux, macOS, etc.
                ping_cmd = ["ping", "-c", str(count), "-i", str(interval), target]

            # Start the ping process
            process = subprocess.Popen(
                ping_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )

            # Process output in real-time
            while process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue

                # Look for ping response lines
                if "bytes from" in line or "Reply from" in line:
                    progress.update(task, advance=1)

                    # Extract round-trip time
                    m = re.search(r"time=(\d+\.?\d*)", line)
                    if m:
                        rtt = float(m.group(1))
                        latency_tracker.add_result(rtt)
                        console.print(f"\r[dim]Reply: time={rtt:.2f} ms[/dim]")

                # Look for timeout indicators
                elif "Request timeout" in line or "100% packet loss" in line:
                    progress.update(task, advance=1)
                    latency_tracker.add_result(None)
                    console.print(f"\r[bold {NordColors.NORD11}]Request timed out[/]")

            # Ensure task shows as complete
            progress.update(task, completed=count)

            # Display results
            console.print("")
            latency_tracker.display_statistics()
            latency_tracker.display_graph()

            # Create result object
            loss_percent = (
                (latency_tracker.loss_count / latency_tracker.total_count * 100)
                if latency_tracker.total_count
                else 0
            )
            min_rtt = (
                latency_tracker.min_rtt
                if latency_tracker.min_rtt != float("inf")
                else 0
            )

            result = PingResult(
                target=target,
                sent=latency_tracker.total_count,
                received=latency_tracker.total_count - latency_tracker.loss_count,
                packet_loss=f"{loss_percent:.1f}%",
                rtt_min=f"{min_rtt:.2f} ms",
                rtt_avg=f"{latency_tracker.avg_rtt:.2f} ms",
                rtt_max=f"{latency_tracker.max_rtt:.2f} ms",
            )

            return result

        except Exception as e:
            print_error(f"Ping error: {e}")
            return result


def traceroute_target(
    target: str, max_hops: int = TRACEROUTE_MAX_HOPS
) -> List[TraceHop]:
    """
    Trace network path to a target with hop latency visualization.

    Args:
        target: Hostname or IP address to trace
        max_hops: Maximum number of hops to trace

    Returns:
        List of TraceHop objects representing each hop
    """
    print_section(f"Traceroute: {target}")

    if not validate_target(target):
        return []

    if not check_command_availability("traceroute"):
        print_error("Traceroute command not available")
        return []

    hops = []

    with ProgressManager() as progress:
        task = progress.add_task("Tracing route...", total=None)

        try:
            # Construct traceroute command
            trace_cmd = [
                "traceroute",
                "-m",
                str(max_hops),
                "-w",
                str(TRACEROUTE_TIMEOUT),
                target,
            ]

            # Start the traceroute process
            process = subprocess.Popen(
                trace_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )

            # Process output in real-time
            header = True
            while process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    continue

                # Skip the header line
                if header and "traceroute to" in line:
                    header = False
                    continue

                # Parse hop information
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        hop_num = parts[0]
                        host = parts[1] if parts[1] != "*" else "Unknown"

                        # Extract round-trip times
                        times = []
                        for p in parts[2:]:
                            m = re.search(r"(\d+\.\d+)\s*ms", p)
                            if m:
                                times.append(float(m.group(1)))

                        # Calculate average time
                        avg_time = sum(times) / len(times) if times else None

                        # Add hop to results
                        hops.append(
                            TraceHop(
                                hop=hop_num,
                                host=host,
                                times=times,
                                avg_time_ms=avg_time,
                            )
                        )

                        # Update status with current hop
                        progress.update(
                            task, description=f"Tracing route... (Hop {hop_num})"
                        )

                    except Exception:
                        continue

            # Display results
            if hops:
                print_success(f"Traceroute completed with {len(hops)} hops")

                table = Table(title="Traceroute Hops", border_style=NordColors.NORD8)
                table.add_column(
                    "Hop", justify="center", style=f"bold {NordColors.NORD9}"
                )
                table.add_column("Host", justify="left", style=f"{NordColors.NORD4}")
                table.add_column("Avg Time", justify="right", style="bold")
                table.add_column(
                    "RTT Samples", justify="left", style=f"dim {NordColors.NORD4}"
                )

                for hop in hops:
                    # Format average time with color based on latency
                    avg = hop.avg_time_ms
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

                    # Format RTT samples
                    times_str = (
                        ", ".join(f"{t:.1f}ms" for t in hop.times)
                        if hop.times
                        else "---"
                    )

                    table.add_row(
                        hop.hop, hop.host, f"[{color}]{avg_str}[/{color}]", times_str
                    )

                console.print(table)
            else:
                display_panel("No hops found", style=NordColors.NORD13, title="Error")

            return hops

        except Exception as e:
            print_error(f"Traceroute error: {e}")
            return []


def dns_lookup(
    hostname: str, record_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Perform DNS lookups with multiple record types.

    Args:
        hostname: The hostname to lookup
        record_types: List of DNS record types to query

    Returns:
        Dictionary with DNS lookup results
    """
    print_section(f"DNS Lookup: {hostname}")

    if not validate_target(hostname):
        return {}

    if record_types is None:
        record_types = ["A", "AAAA"]

    results = {"hostname": hostname}

    with ProgressManager() as progress:
        task = progress.add_task("Looking up DNS records...", total=None)

        try:
            # Try basic socket resolution first
            try:
                addrs = socket.getaddrinfo(hostname, None)
                for addr in addrs:
                    ip = addr[4][0]
                    rec_type = "AAAA" if ":" in ip else "A"
                    results.setdefault(rec_type, []).append(ip)
            except socket.gaierror:
                pass

            # Use dig if available for more detailed records
            if check_command_availability("dig"):
                for rt in record_types:
                    progress.update(task, description=f"Looking up {rt} records...")
                    try:
                        dig_cmd = ["dig", "+noall", "+answer", hostname, rt]
                        dig_out = run_command(dig_cmd, check=False).stdout

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
                    except Exception:
                        continue

            # Fall back to nslookup if dig is not available
            elif check_command_availability("nslookup"):
                for rt in record_types:
                    progress.update(task, description=f"Looking up {rt} records...")
                    try:
                        ns_cmd = ["nslookup", "-type=" + rt, hostname]
                        ns_out = run_command(ns_cmd, check=False).stdout

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
                    except Exception:
                        continue

            # Display results
            if len(results) <= 1:
                display_panel(
                    f"No DNS records found for {hostname}",
                    style=NordColors.NORD13,
                    title="Error",
                )
            else:
                print_success("DNS lookup completed")

                # Create a table for results
                table = Table(
                    title=f"DNS Records for {hostname}", border_style=NordColors.NORD8
                )
                table.add_column(
                    "Type", style=f"bold {NordColors.NORD9}", justify="center"
                )
                table.add_column("Value", style=f"{NordColors.NORD4}", justify="left")
                table.add_column(
                    "TTL", style=f"dim {NordColors.NORD4}", justify="right"
                )

                for rt, recs in results.items():
                    if rt == "hostname":
                        continue

                    if isinstance(recs, list):
                        if isinstance(recs[0], dict):
                            # Detailed records
                            for rec in recs:
                                ttl = (
                                    rec.get("ttl", "") if isinstance(rec, dict) else ""
                                )
                                value = (
                                    rec.get("value", "")
                                    if isinstance(rec, dict)
                                    else str(rec)
                                )
                                table.add_row(rt, value, ttl)
                        else:
                            # Simple records (strings)
                            for rec in recs:
                                table.add_row(rt, str(rec), "")

                console.print(table)

            return results

        except Exception as e:
            print_error(f"DNS lookup error: {e}")
            return {"hostname": hostname}


def port_scan(
    target: str,
    ports: Union[List[int], str] = "common",
    timeout: float = PORT_SCAN_TIMEOUT,
) -> Dict[int, Dict[str, Any]]:
    """
    Scan for open ports on a target host.

    Args:
        target: Hostname or IP address to scan
        ports: Ports to scan (list, range, or "common")
        timeout: Connection timeout in seconds

    Returns:
        Dictionary mapping port numbers to port information
    """
    print_section(f"Port Scan: {target}")

    if not validate_target(target):
        return {}

    # Parse port specification
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

    with ProgressManager() as progress:
        task = progress.add_task(
            f"Scanning {len(port_list)} ports...", total=len(port_list)
        )

        try:
            # Resolve target to IP address
            ip = socket.gethostbyname(target)
            console.print(f"Resolved {target} to [bold]{ip}[/]")

            # Scan each port
            for port in port_list:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)

                # Try to connect to the port
                if sock.connect_ex((ip, port)) == 0:
                    # If connection succeeds, port is open
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

            # Display results
            console.print("")
            if open_ports:
                print_success(f"Found {len(open_ports)} open ports on {target} ({ip})")

                table = Table(title="Port Scan Results", border_style=NordColors.NORD8)
                table.add_column(
                    "Port", justify="center", style=f"bold {NordColors.NORD8}"
                )
                table.add_column(
                    "State", justify="center", style=f"{NordColors.NORD14}"
                )
                table.add_column("Service", justify="left", style=f"{NordColors.NORD4}")

                for port in sorted(open_ports.keys()):
                    info = open_ports[port]
                    table.add_row(str(port), info["state"], info["service"])

                console.print(table)
            else:
                display_panel(
                    f"No open ports found on {target} ({ip})",
                    style=NordColors.NORD13,
                    title="Information",
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
    """
    Monitor network latency to a target over time.

    Args:
        target: Hostname or IP address to monitor
        count: Number of pings to send (0 for unlimited)
        interval: Time between pings in seconds
    """
    print_section(f"Latency Monitor: {target}")

    if not validate_target(target):
        return

    latency_tracker = LatencyTracker(width=RTT_GRAPH_WIDTH)

    print_message(
        f"Monitoring latency to {target}. Press Ctrl+C to stop.", NordColors.NORD9
    )

    try:
        if not check_command_availability("ping"):
            print_error("Ping command not available")
            return

        ping_indefinitely = count == 0
        remaining = count

        with Live(refresh_per_second=4, screen=True) as live:
            while ping_indefinitely or remaining > 0:
                # Construct ping command based on platform
                if sys.platform == "win32":
                    ping_cmd = [
                        "ping",
                        "-n",
                        "1",
                        "-w",
                        str(int(interval * 1000)),
                        target,
                    ]
                else:  # Linux, macOS, etc.
                    ping_cmd = ["ping", "-c", "1", "-i", str(interval), target]

                # Execute ping and measure time
                start = time.time()
                try:
                    output = subprocess.check_output(
                        ping_cmd, universal_newlines=True, stderr=subprocess.STDOUT
                    )

                    # Extract round-trip time
                    m = re.search(r"time=(\d+\.?\d*)", output)
                    if m:
                        rtt = float(m.group(1))
                        latency_tracker.add_result(rtt)
                    else:
                        latency_tracker.add_result(None)
                except subprocess.CalledProcessError:
                    latency_tracker.add_result(None)

                # Calculate elapsed time
                elapsed = time.time() - start
                now = datetime.datetime.now().strftime("%H:%M:%S")

                # Get current RTT
                current_rtt = (
                    f"{latency_tracker.history[-1]:.2f}"
                    if latency_tracker.history
                    and latency_tracker.history[-1] is not None
                    else "timeout"
                )

                # Build panel content
                panel_content = (
                    f"[bold]Target:[/bold] {target}\n"
                    f"[bold]Time:[/bold] {now}\n"
                    f"[bold]Current RTT:[/bold] {current_rtt} ms\n\n"
                    f"[bold]Latency Graph:[/bold]\n{latency_tracker.get_graph_str()}\n\n"
                    f"[bold]Statistics:[/bold]\n{latency_tracker.get_statistics_str()}\n\n"
                    f"[dim]Press Ctrl+C to stop[/dim]"
                )

                # Update live display
                live.update(
                    Panel(
                        panel_content,
                        title=f"Latency Monitor: {target}",
                        border_style=NordColors.NORD8,
                    )
                )

                # Update remaining count
                if not ping_indefinitely:
                    remaining -= 1

                # Sleep for the remaining interval time
                if elapsed < interval:
                    time.sleep(interval - elapsed)

        # Display final statistics
        print_section("Final Statistics")
        console.print(latency_tracker.get_statistics_str())

    except KeyboardInterrupt:
        console.print("\n")
        print_section("Monitoring Stopped")
        print_message(f"Total pings: {latency_tracker.total_count}", NordColors.NORD9)
        console.print(latency_tracker.get_statistics_str())


def bandwidth_test(
    target: str = "example.com", size: int = BANDWIDTH_TEST_SIZE
) -> Dict[str, Any]:
    """
    Perform a simple bandwidth test.

    Args:
        target: Hostname or IP address to test
        size: Size of test data in bytes

    Returns:
        Dictionary with bandwidth test results
    """
    print_section("Bandwidth Test")

    if not validate_target(target):
        return {}

    results = {"target": target, "download_speed": 0.0, "response_time": 0.0}

    print_message(f"Starting bandwidth test to {target}...", NordColors.NORD9)
    print_warning("Note: This is a simple test and may not be fully accurate.")

    try:
        # Resolve target to IP address
        ip = socket.gethostbyname(target)
        print_message(f"Resolved {target} to {ip}", NordColors.NORD9)

        with ProgressManager() as progress:
            task = progress.add_task("Downloading test file...", total=1)

            # Try using curl if available
            if shutil.which("curl"):
                start = time.time()

                curl_cmd = [
                    "curl",
                    "-o",
                    "/dev/null",  # Discard output
                    "-s",  # Silent mode
                    "--connect-timeout",
                    "5",
                    "-w",
                    "%{time_total} %{size_download} %{speed_download}",  # Output format
                    f"http://{target}",
                ]

                output = run_command(curl_cmd, check=False).stdout
                parts = output.split()

                if len(parts) >= 3:
                    total_time = float(parts[0])
                    size_download = int(parts[1])
                    speed_download = float(parts[2])

                    results["response_time"] = total_time
                    results["download_speed"] = speed_download
                    results["download_size"] = size_download

                    progress.update(task, completed=1)

                    # Calculate megabits per second
                    download_mbps = speed_download * 8 / 1024 / 1024

                    # Display results
                    console.print("")
                    print_success("Download test completed")

                    table = Table(
                        title="Bandwidth Test Results", border_style=NordColors.NORD8
                    )
                    table.add_column(
                        "Metric", style=f"bold {NordColors.NORD9}", justify="right"
                    )
                    table.add_column(
                        "Value", style=f"{NordColors.NORD4}", justify="left"
                    )

                    table.add_row("Response time", f"{total_time:.2f} s")
                    table.add_row(
                        "Downloaded", f"{size_download / (1024 * 1024):.2f} MB"
                    )
                    table.add_row(
                        "Speed",
                        f"{speed_download / (1024 * 1024):.2f} MB/s ({download_mbps:.2f} Mbps)",
                    )

                    console.print(table)

            # Fall back to socket test if curl is not available
            else:
                print_warning("Curl not available, using socket test")

                # Measure connection time
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((ip, 80))
                conn_time = time.time() - start

                # Prepare HTTP request
                request = (
                    f"GET / HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n"
                )

                # Send request and start measuring download time
                start = time.time()
                sock.sendall(request.encode())

                # Receive response
                bytes_received = 0
                while True:
                    chunk = sock.recv(BANDWIDTH_CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_received += len(chunk)
                    progress.update(task, completed=min(1, bytes_received / size))

                # Calculate results
                end = time.time()
                sock.close()

                transfer_time = end - start
                speed = bytes_received / transfer_time if transfer_time > 0 else 0

                results["response_time"] = conn_time
                results["download_speed"] = speed
                results["download_size"] = bytes_received

                # Calculate megabits per second
                download_mbps = speed * 8 / 1024 / 1024

                # Display results
                console.print("")
                print_success("Basic bandwidth test completed")

                table = Table(
                    title="Bandwidth Test Results", border_style=NordColors.NORD8
                )
                table.add_column(
                    "Metric", style=f"bold {NordColors.NORD9}", justify="right"
                )
                table.add_column("Value", style=f"{NordColors.NORD4}", justify="left")

                table.add_row("Connection time", f"{conn_time:.2f} s")
                table.add_row("Downloaded", f"{bytes_received / 1024:.2f} KB")
                table.add_row(
                    "Speed", f"{speed / 1024:.2f} KB/s ({download_mbps:.2f} Mbps)"
                )

                console.print(table)

        return results

    except Exception as e:
        print_error(f"Bandwidth test error: {e}")
        return results


# ----------------------------------------------------------------
# Menu Systems
# ----------------------------------------------------------------
def ping_menu() -> None:
    """Interface for configuring and running ping tests."""
    clear_screen()
    console.print(create_header())
    print_section("Ping Configuration")

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

    clear_screen()
    console.print(create_header())
    ping_target(target, count, interval)
    pause()


def traceroute_menu() -> None:
    """Interface for configuring and running traceroute."""
    clear_screen()
    console.print(create_header())
    print_section("Traceroute Configuration")

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

    clear_screen()
    console.print(create_header())
    traceroute_target(target, max_hops)
    pause()


def dns_menu() -> None:
    """Interface for configuring and running DNS lookups."""
    clear_screen()
    console.print(create_header())
    print_section("DNS Lookup Configuration")

    hostname = get_user_input("Enter hostname to lookup", "example.com")
    if not validate_target(hostname):
        pause()
        return

    rec_types_str = get_user_input("Record types (comma-separated)", "A,AAAA,MX,TXT")
    rec_types = [rt.strip().upper() for rt in rec_types_str.split(",")]

    clear_screen()
    console.print(create_header())
    dns_lookup(hostname, rec_types)
    pause()


def scan_menu() -> None:
    """Interface for configuring and running port scans."""
    clear_screen()
    console.print(create_header())
    print_section("Port Scan Configuration")

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

    clear_screen()
    console.print(create_header())
    port_scan(target, port_spec, timeout)
    pause()


def monitor_menu() -> None:
    """Interface for configuring and running latency monitoring."""
    clear_screen()
    console.print(create_header())
    print_section("Latency Monitor Configuration")

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

    clear_screen()
    console.print(create_header())
    monitor_latency(target, count, interval)
    pause()


def bandwidth_menu() -> None:
    """Interface for configuring and running bandwidth tests."""
    clear_screen()
    console.print(create_header())
    print_section("Bandwidth Test Configuration")

    target = get_user_input("Enter target hostname or IP", "example.com")
    if not validate_target(target):
        pause()
        return

    clear_screen()
    console.print(create_header())
    bandwidth_test(target)
    pause()


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main_menu() -> None:
    """Main application menu loop."""
    while True:
        clear_screen()
        console.print(create_header())

        # Display system information
        system_info = Table(box=None, show_header=False, expand=False)
        system_info.add_column(style=f"bold {NordColors.NORD9}")
        system_info.add_column(style=f"{NordColors.NORD4}")

        system_info.add_row("System:", f"{platform.system()} {platform.release()}")
        system_info.add_row("Host:", HOSTNAME)
        system_info.add_row(
            "Time:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        system_info.add_row("Running as root:", "Yes" if check_root() else "No")

        console.print(system_info)
        console.print()

        # Display menu options
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

        # Get user choice
        choice = get_user_input("Enter your choice (0-8):")

        if choice == "1":
            clear_screen()
            console.print(create_header())
            get_network_interfaces()
            pause()
        elif choice == "2":
            clear_screen()
            console.print(create_header())
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
            console.print(create_header())
            display_panel(
                "Thank you for using the Network Toolkit!",
                style=NordColors.NORD14,
                title="Goodbye",
            )
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the application."""
    try:
        # Setup logging
        setup_logging()

        # Check for root privileges
        if not check_root():
            print_warning(
                "Some operations may have limited functionality without root privileges."
            )

        # Start main menu
        main_menu()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
