#!/usr/bin/env python3
"""
Enhanced Network Information and Diagnostics Tool

A comprehensive command-line tool for network analysis and connectivity testing
with robust functionality, user-friendly progress tracking, and clear feedback.

This toolkit provides the following network diagnostic operations:
  • interfaces - List and analyze network interfaces with detailed statistics
  • ip         - Display IP address information for all interfaces
  • ping       - Test connectivity to a target with visual response time tracking
  • traceroute - Trace network path to a target with hop latency visualization
  • dns        - Perform DNS lookups with multiple record types
  • scan       - Scan for open ports on a target host
  • monitor    - Monitor network latency to a target over time
  • bandwidth  - Simple bandwidth test to a target

Features:
  • Thread-safe progress bars and visual latency graphs
  • Comprehensive error handling with clear feedback
  • Signal handling for graceful interruption
  • Nord-themed color-coded output for better readability
  • Detailed network information collection

Note: Some operations require root privileges for full functionality.
"""

import argparse
import datetime
import ipaddress
import os
import platform
import re
import shutil  # Add this import
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, Deque

#####################################
# Configuration
#####################################

# Network operation settings
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
BANDWIDTH_TEST_SIZE = 10 * 1024 * 1024  # 10MB for bandwidth test
BANDWIDTH_CHUNK_SIZE = 1024 * 64  # 64KB chunks

# UI settings
PROGRESS_WIDTH = 50
UPDATE_INTERVAL = 0.1  # Seconds between UI updates
MAX_LATENCY_HISTORY = 100  # Number of ping results to keep for graphing
RTT_GRAPH_WIDTH = 60  # Width of the RTT graph
RTT_GRAPH_HEIGHT = 10  # Height of the RTT graph

# Known port service names
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

# Command availability
COMMANDS = {
    "ip": shutil.which("ip") is not None,
    "ping": shutil.which("ping") is not None,
    "traceroute": shutil.which("traceroute") is not None,
    "dig": shutil.which("dig") is not None,
    "nslookup": shutil.which("nslookup") is not None,
    "nmap": shutil.which("nmap") is not None,
    "netstat": shutil.which("netstat") is not None,
    "ss": shutil.which("ss") is not None,
    "ifconfig": shutil.which("ifconfig") is not None,
}

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """
    Nord-themed ANSI color codes for terminal output.
    Based on the Nord color palette (https://www.nordtheme.com/)
    """

    # Nord palette
    POLAR_NIGHT_1 = "\033[38;2;46;52;64m"  # Dark base color
    POLAR_NIGHT_2 = "\033[38;2;59;66;82m"  # Lighter dark base color
    SNOW_STORM_1 = "\033[38;2;216;222;233m"  # Light base color
    SNOW_STORM_2 = "\033[38;2;229;233;240m"  # Lighter base color
    FROST_1 = "\033[38;2;143;188;187m"  # Light blue / cyan
    FROST_2 = "\033[38;2;136;192;208m"  # Blue
    FROST_3 = "\033[38;2;129;161;193m"  # Dark blue
    FROST_4 = "\033[38;2;94;129;172m"  # Navy blue
    AURORA_RED = "\033[38;2;191;97;106m"  # Red
    AURORA_ORANGE = "\033[38;2;208;135;112m"  # Orange
    AURORA_YELLOW = "\033[38;2;235;203;139m"  # Yellow
    AURORA_GREEN = "\033[38;2;163;190;140m"  # Green
    AURORA_PURPLE = "\033[38;2;180;142;173m"  # Purple

    # Functional color aliases
    HEADER = FROST_4
    INFO = FROST_2
    SUCCESS = AURORA_GREEN
    WARNING = AURORA_YELLOW
    ERROR = AURORA_RED
    PROCESSING = FROST_3
    DETAIL = SNOW_STORM_1
    EMPHASIS = AURORA_PURPLE
    MUTED = POLAR_NIGHT_2
    CRITICAL = AURORA_RED
    NORMAL = AURORA_GREEN
    DEGRADED = AURORA_YELLOW

    # Text styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"

    # Background colors
    BG_DARK = "\033[48;2;46;52;64m"
    BG_LIGHT = "\033[48;2;216;222;233m"


class SpinnerAnimation:
    """Animated spinner for terminal output"""

    def __init__(self, message: str = "Processing"):
        self.message = message
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.running = False
        self.spinner_thread = None
        self.counter = 0
        self.start_time = None
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Display the spinner animation"""
        while self.running:
            with self._lock:
                frame = self.frames[self.counter % len(self.frames)]
                elapsed = time.time() - self.start_time if self.start_time else 0
                sys.stdout.write(
                    f"\r{Colors.PROCESSING}{frame} {self.message} "
                    f"{Colors.DETAIL}({elapsed:.1f}s){Colors.ENDC}"
                )
                sys.stdout.flush()
                self.counter += 1
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation in a separate thread"""
        self.running = True
        self.start_time = time.time()
        self.spinner_thread = threading.Thread(target=self._spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()

    def update_message(self, message: str) -> None:
        """Update the spinner message"""
        with self._lock:
            self.message = message

    def stop(self, message: Optional[str] = None) -> None:
        """Stop the spinner animation"""
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
        if message:
            # Clear the line and print the message
            sys.stdout.write("\r" + " " * 80)  # Clear the line
            sys.stdout.write(f"\r{message}\n")
        else:
            sys.stdout.write("\r" + " " * 80)  # Clear the line
            sys.stdout.write("\r")
        sys.stdout.flush()


class ProgressBar:
    """Thread-safe progress bar with rate display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def set_progress(self, value: int) -> None:
        """Set progress to a specific value"""
        with self._lock:
            self.current = min(value, self.total)
            self._display()

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total) if self.total > 0 else 0
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100 if self.total > 0 else 0

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (
            (self.total - self.current) / rate
            if rate > 0 and self.current < self.total
            else 0
        )

        sys.stdout.write(
            f"\r{Colors.INFO}{self.desc}: {Colors.ENDC}|{Colors.FROST_2}{bar}{Colors.ENDC}| "
            f"{Colors.EMPHASIS}{percent:>5.1f}%{Colors.ENDC} "
            f"[{Colors.SUCCESS}{format_rate(rate)}{Colors.ENDC}] "
            f"[ETA: {Colors.DETAIL}{format_time(eta)}{Colors.ENDC}]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


class LatencyTracker:
    """
    Tracks and visualizes network latency over time.
    """

    def __init__(
        self, max_history: int = MAX_LATENCY_HISTORY, width: int = RTT_GRAPH_WIDTH
    ):
        self.history: Deque[float] = deque(maxlen=max_history)
        self.min_rtt = float("inf")
        self.max_rtt = 0.0
        self.avg_rtt = 0.0
        self.loss_count = 0
        self.total_count = 0
        self.graph_width = width
        self.graph_height = RTT_GRAPH_HEIGHT
        self._lock = threading.Lock()

    def add_result(self, rtt: Optional[float]) -> None:
        """
        Add a new RTT measurement. None indicates packet loss.
        """
        with self._lock:
            self.total_count += 1

            if rtt is None:
                self.loss_count += 1
                self.history.append(None)
                return

            self.history.append(rtt)

            # Update statistics
            if rtt < self.min_rtt:
                self.min_rtt = rtt

            if rtt > self.max_rtt:
                self.max_rtt = rtt

            # Recalculate average
            valid_rtts = [r for r in self.history if r is not None]
            if valid_rtts:
                self.avg_rtt = sum(valid_rtts) / len(valid_rtts)

    def display_statistics(self) -> None:
        """
        Display RTT statistics
        """
        with self._lock:
            loss_percent = (
                (self.loss_count / self.total_count * 100)
                if self.total_count > 0
                else 0
            )

            if self.min_rtt == float("inf"):
                self.min_rtt = 0

            jitter = self._calculate_jitter()

            print(f"{Colors.INFO}RTT Statistics:{Colors.ENDC}")
            print(f"  Min: {Colors.DETAIL}{self.min_rtt:.2f} ms{Colors.ENDC}")
            print(f"  Avg: {Colors.DETAIL}{self.avg_rtt:.2f} ms{Colors.ENDC}")
            print(f"  Max: {Colors.DETAIL}{self.max_rtt:.2f} ms{Colors.ENDC}")
            print(f"  Jitter: {Colors.DETAIL}{jitter:.2f} ms{Colors.ENDC}")

            # Color-code the packet loss percentage
            if loss_percent == 0:
                loss_color = Colors.SUCCESS
            elif loss_percent < 5:
                loss_color = Colors.WARNING
            else:
                loss_color = Colors.ERROR

            print(
                f"  Packet Loss: {loss_color}{loss_percent:.1f}%{Colors.ENDC} ({self.loss_count}/{self.total_count})"
            )

    def _calculate_jitter(self) -> float:
        """
        Calculate jitter (variation in latency)
        """
        valid_rtts = [r for r in self.history if r is not None]
        if len(valid_rtts) < 2:
            return 0.0

        differences = [
            abs(valid_rtts[i] - valid_rtts[i - 1]) for i in range(1, len(valid_rtts))
        ]
        return sum(differences) / len(differences)

    def display_graph(self) -> None:
        """
        Display an ASCII graph of latency over time
        """
        with self._lock:
            if not self.history or all(rtt is None for rtt in self.history):
                print(f"{Colors.WARNING}No data to display graph{Colors.ENDC}")
                return

            # Calculate graph scale
            valid_rtts = [r for r in self.history if r is not None]
            if not valid_rtts:
                return

            min_rtt = min(valid_rtts)
            max_rtt = max(valid_rtts)

            # Ensure a minimum range for visibility
            if max_rtt - min_rtt < 5:
                max_rtt = min_rtt + 5

            # Add a bit of padding
            graph_min = max(0, min_rtt - (max_rtt - min_rtt) * 0.1)
            graph_max = max_rtt + (max_rtt - min_rtt) * 0.1

            # Create the graph canvas
            display_history = list(self.history)[-self.graph_width :]

            # Print Y-axis labels
            print(f"\n{Colors.INFO}Latency Graph (ms):{Colors.ENDC}")
            print(f"{Colors.DETAIL}{graph_max:.1f} ms{Colors.ENDC} ┐")

            # Print the graph
            for i in range(self.graph_height, 0, -1):
                row = "  "
                threshold = graph_min + (graph_max - graph_min) * i / self.graph_height

                for rtt in display_history:
                    if rtt is None:
                        row += f"{Colors.ERROR}×{Colors.ENDC}"  # Packet loss
                    elif rtt >= threshold:
                        # Color based on relative latency
                        if rtt < self.avg_rtt * 0.8:
                            color = Colors.SUCCESS
                        elif rtt < self.avg_rtt * 1.2:
                            color = Colors.DETAIL
                        else:
                            color = Colors.WARNING

                        row += f"{color}█{Colors.ENDC}"
                    else:
                        row += " "

                print(row)

            # Print X-axis
            mid_value = graph_min + (graph_max - graph_min) / 2
            print(
                f"{Colors.DETAIL}{graph_min:.1f} ms{Colors.ENDC} ┴"
                + "─" * self.graph_width
            )

            # Print time scale
            time_ago = len(display_history) * PING_INTERVAL_DEFAULT
            print(
                f"         {Colors.DETAIL}{time_ago:.0f}s ago{Colors.ENDC}"
                + " " * (self.graph_width - 15)
                + f"{Colors.DETAIL}now{Colors.ENDC}"
            )

            # Print legend
            print(
                f"\n  {Colors.SUCCESS}█{Colors.ENDC} Good   {Colors.DETAIL}█{Colors.ENDC} Normal   {Colors.WARNING}█{Colors.ENDC} High   {Colors.ERROR}×{Colors.ENDC} Loss"
            )


class NetworkGraphs:
    """
    Provides visual representations of network data
    """

    @staticmethod
    def latency_distribution(latencies: List[float], width: int = 40) -> None:
        """
        Display a distribution graph of latencies
        """
        if not latencies:
            print(f"{Colors.WARNING}No latency data available{Colors.ENDC}")
            return

        # Create bins for latency ranges
        min_latency = min(latencies)
        max_latency = max(latencies)

        if max_latency - min_latency < 1:
            # Not enough range for meaningful bins
            print(
                f"{Colors.INFO}Latency is very stable at around {min_latency:.2f} ms{Colors.ENDC}"
            )
            return

        # Create 5 bins
        bin_size = (max_latency - min_latency) / 5
        bins = [0] * 5

        for latency in latencies:
            bin_index = min(4, int((latency - min_latency) / bin_size))
            bins[bin_index] += 1

        max_count = max(bins)

        print(f"{Colors.INFO}Latency Distribution:{Colors.ENDC}")
        for i, count in enumerate(bins):
            lower = min_latency + i * bin_size
            upper = min_latency + (i + 1) * bin_size
            bar_length = int(width * count / max_count) if max_count > 0 else 0
            bar = "█" * bar_length

            # Color code based on latency range
            if i < 2:
                color = Colors.SUCCESS
            elif i < 4:
                color = Colors.WARNING
            else:
                color = Colors.ERROR

            print(
                f"  {lower:>5.1f} - {upper:<5.1f} ms | {color}{bar}{Colors.ENDC} {count}"
            )

    @staticmethod
    def hop_latency_graph(hops: List[Dict[str, Any]], width: int = 40) -> None:
        """
        Display a graph of hop latencies from traceroute
        """
        if not hops:
            print(f"{Colors.WARNING}No hop data available{Colors.ENDC}")
            return

        # Get max latency for scaling
        max_latency = 0
        for hop in hops:
            if hop.get("avg_time_ms") and hop["avg_time_ms"] != "N/A":
                max_latency = max(max_latency, hop["avg_time_ms"])

        if max_latency == 0:
            max_latency = 1  # Avoid division by zero

        print(f"{Colors.INFO}Hop Latency Graph:{Colors.ENDC}")
        for hop in hops:
            hop_num = hop.get("hop", "?")
            host = hop.get("host", "Unknown")

            if host == "*" or host == "Unknown":
                print(f"  {hop_num:>2}. {'*' * 15}")
                continue

            avg_time = hop.get("avg_time_ms")
            if avg_time == "N/A" or avg_time is None:
                print(f"  {hop_num:>2}. {host:<15} | No response")
                continue

            # Create bar graph
            bar_length = int(width * avg_time / max_latency) if max_latency > 0 else 0

            # Color code based on latency
            if avg_time < 20:
                color = Colors.SUCCESS
            elif avg_time < 100:
                color = Colors.WARNING
            else:
                color = Colors.ERROR

            bar = "█" * bar_length
            print(
                f"  {hop_num:>2}. {host:<15} | {color}{bar}{Colors.ENDC} {avg_time:.1f} ms"
            )


#####################################
# Helper Functions
#####################################


def print_header(message: str) -> None:
    """
    Print formatted header.

    Args:
        message: Header message to display
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """
    Print formatted section header.

    Args:
        message: Section header message to display
    """
    print(f"\n{Colors.INFO}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def format_time(seconds: float) -> str:
    """
    Format time in seconds to a human-readable format.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def format_rate(bytes_per_sec: float) -> str:
    """
    Format bytes per second to human-readable format.

    Args:
        bytes_per_sec: Rate in bytes per second

    Returns:
        Formatted rate string
    """
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.1f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    elif bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024 * 1024):.1f} GB/s"


def is_valid_ip(ip: str) -> bool:
    """
    Check if a string is a valid IP address.

    Args:
        ip: IP address to check

    Returns:
        True if valid, False otherwise
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_valid_hostname(hostname: str) -> bool:
    """
    Check if a string is a valid hostname.

    Args:
        hostname: Hostname to check

    Returns:
        True if valid, False otherwise
    """
    hostname_regex = re.compile(
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    return bool(hostname_regex.match(hostname))


def signal_handler(sig, frame) -> None:
    """
    Handle interrupt signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    print(f"\n{Colors.WARNING}Operation interrupted. Cleaning up...{Colors.ENDC}")
    # Clean up could go here
    sys.exit(130)  # Exit with 130 (128 + SIGINT)


def run_with_spinner(func: Callable, message: str, *args, **kwargs) -> Any:
    """
    Run a function with a spinner animation.

    Args:
        func: Function to run
        message: Message to display during execution
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function
    """
    spinner = SpinnerAnimation(message)
    spinner.start()

    try:
        result = func(*args, **kwargs)
        spinner.stop()
        return result
    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error: {e}{Colors.ENDC}")
        raise


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """
    Check if script is run with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() == 0:
        print(f"{Colors.INFO}Running with root privileges{Colors.ENDC}")
        return True

    print(
        f"{Colors.WARNING}Running without root privileges. Some operations may be limited.{Colors.ENDC}"
    )
    return False


def validate_target(target: str) -> bool:
    """
    Validate that a target is a valid hostname or IP address.

    Args:
        target: Target hostname or IP address

    Returns:
        True if valid, False otherwise
    """
    if is_valid_ip(target) or is_valid_hostname(target):
        return True

    print(f"{Colors.ERROR}Invalid target: {target}{Colors.ENDC}")
    print(f"Please provide a valid hostname or IP address.")
    return False


def check_command_availability(command: str) -> bool:
    """
    Check if a command is available on the system.

    Args:
        command: Command to check

    Returns:
        True if available, False otherwise
    """
    if not COMMANDS.get(command, False):
        print(
            f"{Colors.ERROR}Required command '{command}' is not available on your system.{Colors.ENDC}"
        )
        return False
    return True


#####################################
# Network Operation Functions
#####################################


def get_network_interfaces() -> List[Dict[str, Any]]:
    """
    Retrieve detailed network interface information.

    Returns:
        List of network interfaces with details
    """
    print_section("Network Interfaces")

    interfaces = []
    spinner = SpinnerAnimation("Collecting interface information")
    spinner.start()

    try:
        # First try using 'ip' command (Linux)
        if check_command_availability("ip"):
            output = subprocess.check_output(
                ["ip", "-o", "link", "show"], universal_newlines=True
            )

            for line in output.splitlines():
                match = re.search(r"^\d+:\s+([^:@]+).*state\s+(\w+)", line)
                if match:
                    iface_name, state = match.groups()
                    iface_name = iface_name.strip()

                    # Skip loopback
                    if iface_name == "lo":
                        continue

                    # Get additional details
                    hw_addr = "Unknown"
                    hw_match = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", line)
                    if hw_match:
                        hw_addr = hw_match.group(1)

                    # Get interface stats
                    try:
                        stats_output = subprocess.check_output(
                            ["ip", "-s", "link", "show", "dev", iface_name],
                            universal_newlines=True,
                        )

                        rx_bytes = 0
                        tx_bytes = 0

                        # Extract RX and TX stats
                        rx_match = re.search(
                            r"RX:.*bytes\s+(\d+)", stats_output, re.DOTALL
                        )
                        if rx_match:
                            rx_bytes = int(rx_match.group(1))

                        tx_match = re.search(
                            r"TX:.*bytes\s+(\d+)", stats_output, re.DOTALL
                        )
                        if tx_match:
                            tx_bytes = int(tx_match.group(1))

                        interfaces.append(
                            {
                                "name": iface_name,
                                "status": state,
                                "mac_address": hw_addr,
                                "rx_bytes": rx_bytes,
                                "tx_bytes": tx_bytes,
                            }
                        )

                    except subprocess.CalledProcessError:
                        # Fallback with less information
                        interfaces.append(
                            {
                                "name": iface_name,
                                "status": state,
                                "mac_address": hw_addr,
                                "rx_bytes": 0,
                                "tx_bytes": 0,
                            }
                        )

        # Fallback to ifconfig if ip command not available
        elif check_command_availability("ifconfig"):
            spinner.update_message("Using ifconfig for interface information")
            output = subprocess.check_output(["ifconfig"], universal_newlines=True)

            current_iface = None
            for line in output.splitlines():
                # New interface definition
                iface_match = re.match(r"^(\w+):", line)
                if iface_match:
                    current_iface = iface_match.group(1)

                    # Skip loopback
                    if current_iface == "lo":
                        current_iface = None
                        continue

                    # Initialize new interface
                    interfaces.append(
                        {
                            "name": current_iface,
                            "status": "unknown",
                            "mac_address": "Unknown",
                            "rx_bytes": 0,
                            "tx_bytes": 0,
                        }
                    )

                # Interface status
                elif current_iface and "UP" in line:
                    for iface in interfaces:
                        if iface["name"] == current_iface:
                            iface["status"] = "UP" if "UP" in line else "DOWN"

                # MAC address
                elif current_iface and "ether" in line:
                    mac_match = re.search(r"ether\s+([0-9a-fA-F:]+)", line)
                    if mac_match:
                        for iface in interfaces:
                            if iface["name"] == current_iface:
                                iface["mac_address"] = mac_match.group(1)

                # RX/TX stats
                elif current_iface and "RX packets" in line:
                    rx_bytes_match = re.search(r"RX .*bytes\s+(\d+)", line)
                    if rx_bytes_match:
                        for iface in interfaces:
                            if iface["name"] == current_iface:
                                iface["rx_bytes"] = int(rx_bytes_match.group(1))

                elif current_iface and "TX packets" in line:
                    tx_bytes_match = re.search(r"TX .*bytes\s+(\d+)", line)
                    if tx_bytes_match:
                        for iface in interfaces:
                            if iface["name"] == current_iface:
                                iface["tx_bytes"] = int(tx_bytes_match.group(1))

        spinner.stop(
            f"{Colors.SUCCESS}Found {len(interfaces)} network interfaces{Colors.ENDC}"
        )

        # Display interface information
        if interfaces:
            print(
                f"{Colors.BOLD}{'Interface':<12} {'Status':<10} {'MAC Address':<20} {'RX':<12} {'TX':<12}{Colors.ENDC}"
            )
            print("─" * 70)

            for iface in interfaces:
                # Color-code interface status
                if iface["status"].lower() in ["up", "active"]:
                    status_color = Colors.SUCCESS
                elif iface["status"].lower() in ["down", "inactive"]:
                    status_color = Colors.ERROR
                else:
                    status_color = Colors.WARNING

                rx_formatted = format_size(iface["rx_bytes"])
                tx_formatted = format_size(iface["tx_bytes"])

                print(
                    f"{Colors.EMPHASIS}{iface['name']:<12}{Colors.ENDC} "
                    f"{status_color}{iface['status']:<10}{Colors.ENDC} "
                    f"{iface['mac_address']:<20} "
                    f"{rx_formatted:<12} "
                    f"{tx_formatted:<12}"
                )
        else:
            print(f"{Colors.WARNING}No network interfaces found{Colors.ENDC}")

        return interfaces

    except Exception as e:
        spinner.stop(
            f"{Colors.ERROR}Error retrieving network interfaces: {e}{Colors.ENDC}"
        )
        return []


def format_size(bytes: int) -> str:
    """
    Format bytes to human readable size.

    Args:
        bytes: Size in bytes

    Returns:
        Formatted string representation of the size
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def get_ip_addresses() -> Dict[str, List[Dict[str, str]]]:
    """
    Retrieve IP addresses for all network interfaces.

    Returns:
        Dictionary of interfaces with their IP addresses
    """
    print_section("IP Address Information")

    ip_addresses = {}
    spinner = SpinnerAnimation("Collecting IP address information")
    spinner.start()

    try:
        # Try using 'ip' command first (Linux)
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

                    # Look for IPv4 addresses
                    if "inet " in line:
                        ip_match = re.search(r"inet\s+([^/]+)", line)
                        if ip_match:
                            ip_addresses.setdefault(iface, []).append(
                                {"type": "IPv4", "address": ip_match.group(1)}
                            )

                    # Look for IPv6 addresses
                    if "inet6 " in line:
                        ip_match = re.search(r"inet6\s+([^/]+)", line)
                        if ip_match and not ip_match.group(1).startswith("fe80"):
                            ip_addresses.setdefault(iface, []).append(
                                {"type": "IPv6", "address": ip_match.group(1)}
                            )

        # Fallback to ifconfig
        elif check_command_availability("ifconfig"):
            spinner.update_message("Using ifconfig for IP information")
            output = subprocess.check_output(["ifconfig"], universal_newlines=True)

            current_iface = None
            for line in output.splitlines():
                # New interface definition
                iface_match = re.match(r"^(\w+):", line)
                if iface_match:
                    current_iface = iface_match.group(1)

                    # Skip loopback
                    if current_iface == "lo":
                        current_iface = None
                        continue

                # IPv4 address
                elif current_iface and "inet " in line:
                    ip_match = re.search(r"inet\s+([0-9.]+)", line)
                    if ip_match:
                        ip_addresses.setdefault(current_iface, []).append(
                            {"type": "IPv4", "address": ip_match.group(1)}
                        )

                # IPv6 address
                elif current_iface and "inet6 " in line:
                    ip_match = re.search(r"inet6\s+([0-9a-f:]+)", line)
                    if ip_match and not ip_match.group(1).startswith("fe80"):
                        ip_addresses.setdefault(current_iface, []).append(
                            {"type": "IPv6", "address": ip_match.group(1)}
                        )

        spinner.stop(f"{Colors.SUCCESS}IP address information collected{Colors.ENDC}")

        # Display IP address information
        if ip_addresses:
            for iface, addrs in ip_addresses.items():
                print(f"{Colors.EMPHASIS}{iface}:{Colors.ENDC}")

                if not addrs:
                    print(f"  {Colors.WARNING}No IP addresses assigned{Colors.ENDC}")
                    continue

                for addr in addrs:
                    # Color-code IP address types
                    if addr["type"] == "IPv4":
                        type_color = Colors.FROST_2
                    else:
                        type_color = Colors.AURORA_PURPLE

                    print(
                        f"  {type_color}{addr['type']:<6}{Colors.ENDC}: {addr['address']}"
                    )
        else:
            print(f"{Colors.WARNING}No IP addresses found{Colors.ENDC}")

        return ip_addresses

    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error retrieving IP addresses: {e}{Colors.ENDC}")
        return {}


def ping_target(
    target: str,
    count: int = PING_COUNT_DEFAULT,
    interval: float = PING_INTERVAL_DEFAULT,
) -> Dict[str, Any]:
    """
    Perform ping test to a target with progress visualization.

    Args:
        target: Hostname or IP to ping
        count: Number of ping attempts
        interval: Interval between pings in seconds

    Returns:
        Dictionary with ping results
    """
    print_section(f"Ping Results for {target}")

    if not validate_target(target):
        return {}

    # Initialize trackers
    progress = ProgressBar(count, desc="Ping progress")
    latency_tracker = LatencyTracker()

    try:
        # Check ping command availability
        if not check_command_availability("ping"):
            print(
                f"{Colors.ERROR}Ping command not available on your system{Colors.ENDC}"
            )
            return {}

        # Create the ping command
        ping_cmd = ["ping", "-c", str(count)]
        if interval != 1.0:
            ping_cmd.extend(["-i", str(interval)])
        ping_cmd.append(target)

        print(
            f"Pinging {target} with {count} packets at {interval} second intervals..."
        )

        # Start the ping process
        process = subprocess.Popen(
            ping_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Process ping output in real-time
        current_count = 0
        while process.poll() is None:
            line = process.stdout.readline()
            if not line:
                continue

            # Look for ping response lines
            if line.startswith(("64 bytes", "56 bytes")):
                current_count += 1
                progress.set_progress(current_count)

                # Extract time
                time_match = re.search(r"time=(\d+\.?\d*)", line)
                if time_match:
                    rtt = float(time_match.group(1))
                    latency_tracker.add_result(rtt)

                    # Color-code based on latency
                    if rtt < 50:
                        color = Colors.SUCCESS
                    elif rtt < 150:
                        color = Colors.WARNING
                    else:
                        color = Colors.ERROR

                    # Print real-time result under the progress bar
                    print(
                        f"\r{' ' * 80}\r  Reply from {target}: time={color}{rtt:.2f} ms{Colors.ENDC}"
                    )

                    # Redraw progress bar
                    progress._display()

            # Look for timeout
            elif "Request timeout" in line or "100% packet loss" in line:
                current_count += 1
                progress.set_progress(current_count)
                latency_tracker.add_result(None)

                print(f"\r{' ' * 80}\r  {Colors.ERROR}Request timed out{Colors.ENDC}")

                # Redraw progress bar
                progress._display()

        # Process any remaining output
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Parse ping statistics
            if "packet loss" in line:
                progress.set_progress(count)  # Ensure progress bar is complete

        # Display latency statistics and graph
        print()  # Add space after progress bar
        latency_tracker.display_statistics()
        latency_tracker.display_graph()

        # Show latency distribution if we have enough data points
        if latency_tracker.total_count >= 3:
            valid_rtts = [r for r in latency_tracker.history if r is not None]
            if valid_rtts:
                NetworkGraphs.latency_distribution(valid_rtts)

        # Build the result dictionary
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

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Ping interrupted{Colors.ENDC}")
        return {}
    except Exception as e:
        print(f"{Colors.ERROR}Error during ping: {e}{Colors.ENDC}")
        return {}


def traceroute_target(
    target: str, max_hops: int = TRACEROUTE_MAX_HOPS
) -> List[Dict[str, Any]]:
    """
    Perform traceroute to a target with visual path analysis.

    Args:
        target: Hostname or IP to trace
        max_hops: Maximum number of hops

    Returns:
        List of traceroute hops with details
    """
    print_section(f"Traceroute to {target}")

    if not validate_target(target):
        return []

    hops = []
    spinner = SpinnerAnimation(f"Tracing route to {target}")
    spinner.start()

    try:
        # Check traceroute command availability
        if not check_command_availability("traceroute"):
            spinner.stop(
                f"{Colors.ERROR}Traceroute command not available on your system{Colors.ENDC}"
            )
            return []

        # Build the traceroute command
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

        # Process traceroute output in real-time
        header_processed = False
        while process.poll() is None:
            line = process.stdout.readline()
            if not line:
                continue

            # Skip the header line
            if not header_processed and "traceroute to" in line:
                header_processed = True
                continue

            # Process hop line
            parts = line.split()
            if len(parts) >= 2:
                try:
                    hop_num = parts[0]
                    spinner.update_message(f"Tracing route to {target} (hop {hop_num})")

                    # Extract hostname/IP
                    host = parts[1] if parts[1] != "*" else "Unknown"

                    # Extract times
                    times = []
                    for p in parts[2:]:
                        time_match = re.search(r"(\d+\.\d+)\s*ms", p)
                        if time_match:
                            times.append(float(time_match.group(1)))

                    # Calculate average time
                    avg_time = sum(times) / len(times) if times else None

                    # Add to hops list
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

        # Process any remaining output
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Process hop line (same as above)
            parts = line.split()
            if len(parts) >= 2:
                try:
                    hop_num = parts[0]
                    host = parts[1] if parts[1] != "*" else "Unknown"

                    times = []
                    for p in parts[2:]:
                        time_match = re.search(r"(\d+\.\d+)\s*ms", p)
                        if time_match:
                            times.append(float(time_match.group(1)))

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

        spinner.stop(
            f"{Colors.SUCCESS}Traceroute to {target} completed with {len(hops)} hops{Colors.ENDC}"
        )

        # Display traceroute results
        if hops:
            print(
                f"{Colors.BOLD}{'Hop':<4} {'Host':<20} {'Avg Time':<10} {'Min Time':<10} {'Max Time':<10}{Colors.ENDC}"
            )
            print("─" * 70)

            for hop in hops:
                hop_num = hop.get("hop", "?")
                host = hop.get("host", "Unknown")

                times = hop.get("times", [])
                min_time = min(times) if times else None
                max_time = max(times) if times else None
                avg_time = hop.get("avg_time_ms")

                # Color-code based on latency
                if avg_time is None:
                    time_color = Colors.ERROR
                    avg_time_str = "* * *"
                    min_time_str = "---"
                    max_time_str = "---"
                else:
                    if avg_time < 20:
                        time_color = Colors.SUCCESS
                    elif avg_time < 100:
                        time_color = Colors.WARNING
                    else:
                        time_color = Colors.ERROR

                    avg_time_str = f"{avg_time:.2f} ms"
                    min_time_str = (
                        f"{min_time:.2f} ms" if min_time is not None else "---"
                    )
                    max_time_str = (
                        f"{max_time:.2f} ms" if max_time is not None else "---"
                    )

                print(
                    f"{hop_num:<4} {host:<20} "
                    f"{time_color}{avg_time_str:<10}{Colors.ENDC} "
                    f"{min_time_str:<10} {max_time_str:<10}"
                )

            # Display visual hop latency graph
            print()
            NetworkGraphs.hop_latency_graph(hops)
        else:
            print(f"{Colors.WARNING}No traceroute hops found{Colors.ENDC}")

        return hops

    except KeyboardInterrupt:
        spinner.stop(f"{Colors.WARNING}Traceroute interrupted{Colors.ENDC}")
        return hops  # Return any hops collected so far
    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error during traceroute: {e}{Colors.ENDC}")
        return []


def dns_lookup(
    hostname: str, record_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Perform DNS lookup for a hostname with multiple record types.

    Args:
        hostname: Hostname to resolve
        record_types: List of DNS record types to look up

    Returns:
        Dictionary with DNS resolution details
    """
    print_section(f"DNS Lookup for {hostname}")

    if not validate_target(hostname):
        return {}

    # Use default record types if none specified
    if record_types is None:
        record_types = ["A", "AAAA"]

    results = {"hostname": hostname}
    spinner = SpinnerAnimation(f"Performing DNS lookup for {hostname}")
    spinner.start()

    try:
        # First try using socket for basic resolution
        try:
            addrs = socket.getaddrinfo(hostname, None)

            # Organize results by IP version
            for addr in addrs:
                ip = addr[4][0]
                if ":" in ip:
                    results.setdefault("AAAA", []).append(ip)
                else:
                    results.setdefault("A", []).append(ip)
        except socket.gaierror:
            pass

        # Try to use dig command for more detailed lookups
        if check_command_availability("dig"):
            for record_type in record_types:
                spinner.update_message(
                    f"Looking up {record_type} records for {hostname}"
                )

                try:
                    dig_output = subprocess.check_output(
                        ["dig", "+noall", "+answer", hostname, record_type],
                        universal_newlines=True,
                    )

                    # Parse dig output
                    records = []
                    for line in dig_output.splitlines():
                        parts = line.split()
                        if len(parts) >= 5:
                            name, ttl, _, type_, value = (
                                parts[0],
                                parts[1],
                                parts[2],
                                parts[3],
                                " ".join(parts[4:]),
                            )
                            records.append(
                                {
                                    "name": name,
                                    "ttl": ttl,
                                    "type": type_,
                                    "value": value,
                                }
                            )

                    if records:
                        results[record_type] = records
                except subprocess.CalledProcessError:
                    pass

        # Fallback to nslookup if dig is not available
        elif check_command_availability("nslookup"):
            for record_type in record_types:
                spinner.update_message(
                    f"Looking up {record_type} records for {hostname}"
                )

                try:
                    nslookup_output = subprocess.check_output(
                        ["nslookup", "-type=" + record_type, hostname],
                        universal_newlines=True,
                    )

                    # Parse nslookup output (simpler than dig)
                    records = []
                    for line in nslookup_output.splitlines():
                        if "Address: " in line and not line.startswith("Server:"):
                            ip = line.split("Address: ")[1].strip()
                            records.append(
                                {"name": hostname, "type": record_type, "value": ip}
                            )
                        elif record_type in ["MX", "NS", "CNAME"] and "=" in line:
                            parts = line.split("=")
                            if len(parts) >= 2:
                                records.append(
                                    {
                                        "name": hostname,
                                        "type": record_type,
                                        "value": parts[1].strip(),
                                    }
                                )

                    if records:
                        results[record_type] = records
                except subprocess.CalledProcessError:
                    pass

        spinner.stop(f"{Colors.SUCCESS}DNS lookup completed{Colors.ENDC}")

        # Display DNS lookup results
        if len(results) <= 1:  # Only hostname present
            print(f"{Colors.WARNING}No DNS records found for {hostname}{Colors.ENDC}")
        else:
            for record_type, records in results.items():
                if record_type == "hostname":
                    continue

                # Color-code by record type
                if record_type == "A":
                    type_color = Colors.FROST_2
                elif record_type == "AAAA":
                    type_color = Colors.AURORA_PURPLE
                elif record_type == "MX":
                    type_color = Colors.AURORA_GREEN
                elif record_type == "NS":
                    type_color = Colors.AURORA_YELLOW
                else:
                    type_color = Colors.DETAIL

                print(f"{type_color}{record_type} Records:{Colors.ENDC}")

                if isinstance(records, list):
                    if all(isinstance(r, dict) for r in records):
                        # Detailed record information
                        for record in records:
                            if "ttl" in record:
                                print(f"  {record['value']} (TTL: {record['ttl']})")
                            else:
                                print(f"  {record['value']}")
                    else:
                        # Simple list of values
                        for record in records:
                            print(f"  {record}")
                else:
                    print(f"  {records}")

        return results

    except KeyboardInterrupt:
        spinner.stop(f"{Colors.WARNING}DNS lookup interrupted{Colors.ENDC}")
        return results
    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error during DNS lookup: {e}{Colors.ENDC}")
        return {"hostname": hostname}


def port_scan(
    target: str,
    ports: Union[List[int], str] = "common",
    timeout: float = PORT_SCAN_TIMEOUT,
) -> Dict[int, Dict[str, Any]]:
    """
    Scan for open ports on a target host.

    Args:
        target: Hostname or IP to scan
        ports: List of ports to scan or "common" for common ports
        timeout: Timeout in seconds for each port connection attempt

    Returns:
        Dictionary of open ports with details
    """
    print_section(f"Port Scan for {target}")

    if not validate_target(target):
        return {}

    # Determine which ports to scan
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
            print(f"{Colors.ERROR}Invalid port specification: {ports}{Colors.ENDC}")
            print(
                f"Please use 'common', a comma-separated list, or a range (e.g., 80-443)"
            )
            return {}
    else:
        port_list = ports

    # Initialize results
    open_ports = {}
    progress = ProgressBar(len(port_list), desc=f"Scanning {len(port_list)} ports")

    print(f"Scanning {len(port_list)} ports on {target}...")
    print(
        f"{Colors.WARNING}Note: This is a simple scan and may not be accurate for all ports.{Colors.ENDC}"
    )

    try:
        # Resolve hostname to IP if needed
        ip = socket.gethostbyname(target)

        # Scan each port
        for i, port in enumerate(port_list):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            result = sock.connect_ex((ip, port))
            if result == 0:
                # Port is open, try to get service name
                try:
                    service = socket.getservbyport(port)
                except (OSError, socket.error):
                    service = PORT_SERVICES.get(port, "unknown")

                open_ports[port] = {"state": "open", "service": service}

                # Print real-time result under the progress bar
                if service != "unknown":
                    print(
                        f"\r{' ' * 80}\r  {Colors.SUCCESS}Port {port} is open: {service}{Colors.ENDC}"
                    )
                else:
                    print(
                        f"\r{' ' * 80}\r  {Colors.SUCCESS}Port {port} is open{Colors.ENDC}"
                    )

            sock.close()
            progress.set_progress(i + 1)

        print()  # Add space after progress bar

        # Display scan results summary
        if open_ports:
            print(
                f"{Colors.SUCCESS}Found {len(open_ports)} open ports on {target} ({ip}){Colors.ENDC}"
            )
            print(
                f"{Colors.BOLD}{'Port':<7} {'State':<10} {'Service':<15}{Colors.ENDC}"
            )
            print("─" * 40)

            for port in sorted(open_ports.keys()):
                info = open_ports[port]
                print(
                    f"{Colors.EMPHASIS}{port:<7}{Colors.ENDC} "
                    f"{Colors.SUCCESS}{info['state']:<10}{Colors.ENDC} "
                    f"{info['service']:<15}"
                )
        else:
            print(
                f"{Colors.WARNING}No open ports found on {target} ({ip}){Colors.ENDC}"
            )
            print(f"This could be due to a firewall, or the host may be offline.")

        return open_ports

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Port scan interrupted{Colors.ENDC}")
        return open_ports
    except socket.gaierror:
        print(f"{Colors.ERROR}Could not resolve hostname: {target}{Colors.ENDC}")
        return {}
    except Exception as e:
        print(f"{Colors.ERROR}Error during port scan: {e}{Colors.ENDC}")
        return {}


def monitor_latency(
    target: str,
    count: int = MONITOR_DEFAULT_COUNT,
    interval: float = MONITOR_DEFAULT_INTERVAL,
) -> None:
    """
    Monitor network latency to a target over time.

    Args:
        target: Hostname or IP to monitor
        count: Number of pings to send
        interval: Interval between pings in seconds
    """
    print_section(f"Network Latency Monitor for {target}")

    if not validate_target(target):
        return

    # Initialize trackers
    latency_tracker = LatencyTracker(width=RTT_GRAPH_WIDTH)

    print(f"Monitoring latency to {target}...")
    print(f"Press Ctrl+C to stop monitoring")

    try:
        # Check ping command availability
        if not check_command_availability("ping"):
            print(
                f"{Colors.ERROR}Ping command not available on your system{Colors.ENDC}"
            )
            return

        # Start endless monitoring if count is 0
        ping_indefinitely = count == 0
        remaining_count = count

        while ping_indefinitely or remaining_count > 0:
            # Create ping command for a single ping
            ping_cmd = ["ping", "-c", "1"]
            if interval != 1.0:
                ping_cmd.extend(["-i", str(interval)])
            ping_cmd.append(target)

            try:
                start_time = time.time()
                output = subprocess.check_output(
                    ping_cmd, universal_newlines=True, stderr=subprocess.STDOUT
                )

                # Extract time
                time_match = re.search(r"time=(\d+\.?\d*)", output)
                if time_match:
                    rtt = float(time_match.group(1))
                    latency_tracker.add_result(rtt)

                    # Color-code based on latency
                    if rtt < 50:
                        color = Colors.SUCCESS
                    elif rtt < 150:
                        color = Colors.WARNING
                    else:
                        color = Colors.ERROR

                    # Timestamp
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")

                    # Clear screen for better visualization
                    print("\033[H\033[J", end="")  # Clear screen

                    # Display header
                    print_header(f"Network Latency Monitor for {target}")
                    print(
                        f"{Colors.EMPHASIS}Time: {timestamp}{Colors.ENDC} | "
                        f"Current: {color}{rtt:.2f} ms{Colors.ENDC} | "
                        f"Avg: {Colors.DETAIL}{latency_tracker.avg_rtt:.2f} ms{Colors.ENDC} | "
                        f"Min: {Colors.SUCCESS}{latency_tracker.min_rtt:.2f} ms{Colors.ENDC} | "
                        f"Max: {Colors.WARNING}{latency_tracker.max_rtt:.2f} ms{Colors.ENDC}"
                    )

                    if not ping_indefinitely:
                        print(f"Remaining pings: {remaining_count - 1}")

                    # Display the latency graph
                    latency_tracker.display_graph()
                else:
                    latency_tracker.add_result(None)
                    print(f"{Colors.ERROR}Ping to {target} failed{Colors.ENDC}")

            except subprocess.CalledProcessError:
                latency_tracker.add_result(None)
                print(f"{Colors.ERROR}Ping to {target} failed{Colors.ENDC}")

            if not ping_indefinitely:
                remaining_count -= 1

            # Respect the interval
            elapsed = time.time() - start_time
            if elapsed < interval:
                time.sleep(interval - elapsed)

        # Final statistics
        print_section("Final Statistics")
        latency_tracker.display_statistics()

    except KeyboardInterrupt:
        print("\n")
        print_section("Monitoring Stopped")
        print(f"Monitored {latency_tracker.total_count} pings to {target}")
        latency_tracker.display_statistics()


def bandwidth_test(
    target: str = "example.com", size: int = BANDWIDTH_TEST_SIZE
) -> Dict[str, Any]:
    """
    Perform a simple bandwidth test.

    Args:
        target: Target hostname for bandwidth test
        size: Size of data to transfer in bytes

    Returns:
        Dictionary with bandwidth test results
    """
    print_section(f"Bandwidth Test")

    if not validate_target(target):
        return {}

    results = {"target": target, "download_speed": 0.0, "response_time": 0.0}

    print(f"Starting bandwidth test to {target}...")
    print(
        f"{Colors.WARNING}Note: This is a simple bandwidth test and may not be accurate.{Colors.ENDC}"
    )

    try:
        # Convert hostname to IP address
        ip = socket.gethostbyname(target)
        print(f"Resolved {target} to {ip}")

        # Test HTTP GET request to estimate download speed
        # Choose a suitable URL for download test
        url = f"http://{target}"
        if target == "example.com":
            url = "http://speedtest.ftp.otenet.gr/files/test10Mb.db"  # 10MB test file

        progress = ProgressBar(1, desc="Downloading test file")

        try:
            # Use curl command if available
            if shutil.which("curl"):
                start_time = time.time()

                # Build curl command
                curl_cmd = [
                    "curl",
                    "-o",
                    "/dev/null",  # Output to /dev/null (discard)
                    "-s",  # Silent
                    "--connect-timeout",
                    "5",  # Connection timeout
                    "-w",
                    "%{time_total} %{size_download} %{speed_download}",  # Format: time size speed
                    url,
                ]

                # Execute curl
                output = subprocess.check_output(curl_cmd, universal_newlines=True)
                parts = output.split()

                if len(parts) >= 3:
                    time_total = float(parts[0])
                    size_download = int(parts[1])
                    speed_download = float(parts[2])

                    results["response_time"] = time_total
                    results["download_speed"] = speed_download
                    results["download_size"] = size_download

                    progress.set_progress(1)

                    download_mbps = (
                        speed_download * 8 / 1024 / 1024
                    )  # Convert B/s to Mbps

                    print(f"\n{Colors.SUCCESS}Download test completed:{Colors.ENDC}")
                    print(f"  Response time: {time_total:.2f} seconds")
                    print(f"  Downloaded: {size_download / 1024 / 1024:.2f} MB")
                    print(
                        f"  Speed: {speed_download / 1024 / 1024:.2f} MB/s ({download_mbps:.2f} Mbps)"
                    )

            # Fallback to a socket-based test
            else:
                print(
                    f"{Colors.WARNING}Curl not found, using basic socket connection test{Colors.ENDC}"
                )

                # Test TCP connection time
                start_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((ip, 80))
                connect_time = time.time() - start_time

                # Make an HTTP request and measure response time
                request = (
                    f"GET / HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n"
                )
                start_time = time.time()
                sock.sendall(request.encode())

                # Receive data in chunks and measure time
                chunks = []
                bytes_received = 0

                while True:
                    chunk = sock.recv(BANDWIDTH_CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    bytes_received += len(chunk)
                    progress.set_progress(min(1, bytes_received / BANDWIDTH_TEST_SIZE))

                end_time = time.time()
                sock.close()

                # Calculate results
                transfer_time = end_time - start_time
                speed = bytes_received / transfer_time if transfer_time > 0 else 0

                results["response_time"] = connect_time
                results["download_speed"] = speed
                results["download_size"] = bytes_received

                # Display results
                download_mbps = speed * 8 / 1024 / 1024  # Convert B/s to Mbps

                print(f"\n{Colors.SUCCESS}Basic bandwidth test completed:{Colors.ENDC}")
                print(f"  Connection time: {connect_time:.2f} seconds")
                print(f"  Downloaded: {bytes_received / 1024:.2f} KB")
                print(f"  Speed: {speed / 1024:.2f} KB/s ({download_mbps:.2f} Mbps)")

        except subprocess.CalledProcessError as e:
            print(f"{Colors.ERROR}Error during bandwidth test: {e}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.ERROR}Error: {e}{Colors.ENDC}")

        return results

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Bandwidth test interrupted{Colors.ENDC}")
        return results
    except socket.gaierror:
        print(f"{Colors.ERROR}Could not resolve hostname: {target}{Colors.ENDC}")
        return results
    except Exception as e:
        print(f"{Colors.ERROR}Error during bandwidth test: {e}{Colors.ENDC}")
        return results


#####################################
# Main Function
#####################################


def main() -> None:
    """Main entry point for the network toolkit."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Enhanced Network Information and Diagnostics Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  List network interfaces:
    python network_toolkit.py interfaces
  
  Show IP address information:
    python network_toolkit.py ip
  
  Ping a target:
    python network_toolkit.py ping google.com -c 10
  
  Traceroute to a target:
    python network_toolkit.py traceroute github.com
  
  DNS lookup:
    python network_toolkit.py dns example.com -t A,AAAA,MX
  
  Port scan:
    python network_toolkit.py scan 192.168.1.1 -p 80,443,8080
  
  Monitor network latency:
    python network_toolkit.py monitor google.com -c 100 -i 0.5
  
  Bandwidth test:
    python network_toolkit.py bandwidth
""",
    )

    # Create subparsers for each operation
    subparsers = parser.add_subparsers(dest="operation", help="Operation to perform")

    # Interface command
    interfaces_parser = subparsers.add_parser(
        "interfaces", help="List network interfaces"
    )

    # IP command
    ip_parser = subparsers.add_parser("ip", help="Show IP address information")

    # Ping command
    ping_parser = subparsers.add_parser("ping", help="Ping a target host")
    ping_parser.add_argument("target", help="Target hostname or IP address")
    ping_parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=PING_COUNT_DEFAULT,
        help=f"Number of ping attempts (default: {PING_COUNT_DEFAULT})",
    )
    ping_parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=PING_INTERVAL_DEFAULT,
        help=f"Ping interval in seconds (default: {PING_INTERVAL_DEFAULT})",
    )

    # Traceroute command
    traceroute_parser = subparsers.add_parser(
        "traceroute", help="Traceroute to a target host"
    )
    traceroute_parser.add_argument("target", help="Target hostname or IP address")
    traceroute_parser.add_argument(
        "-m",
        "--max-hops",
        type=int,
        default=TRACEROUTE_MAX_HOPS,
        help=f"Maximum hops (default: {TRACEROUTE_MAX_HOPS})",
    )

    # DNS lookup command
    dns_parser = subparsers.add_parser("dns", help="Perform DNS lookup")
    dns_parser.add_argument("hostname", help="Hostname to resolve")
    dns_parser.add_argument(
        "-t",
        "--types",
        default="A,AAAA",
        help="Comma-separated list of record types (default: A,AAAA)",
    )

    # Port scan command
    scan_parser = subparsers.add_parser(
        "scan", help="Scan for open ports on a target host"
    )
    scan_parser.add_argument("target", help="Target hostname or IP address")
    scan_parser.add_argument(
        "-p",
        "--ports",
        default="common",
        help="Ports to scan: 'common', comma-separated list, or range (e.g., 80-443)",
    )
    scan_parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=PORT_SCAN_TIMEOUT,
        help=f"Timeout in seconds for each port (default: {PORT_SCAN_TIMEOUT})",
    )

    # Latency monitor command
    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor network latency to a target over time"
    )
    monitor_parser.add_argument("target", help="Target hostname or IP address")
    monitor_parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=MONITOR_DEFAULT_COUNT,
        help=f"Number of pings (default: {MONITOR_DEFAULT_COUNT}, 0 for unlimited)",
    )
    monitor_parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=MONITOR_DEFAULT_INTERVAL,
        help=f"Ping interval in seconds (default: {MONITOR_DEFAULT_INTERVAL})",
    )

    # Bandwidth test command
    bandwidth_parser = subparsers.add_parser(
        "bandwidth", help="Perform a simple bandwidth test"
    )
    bandwidth_parser.add_argument(
        "-t",
        "--target",
        default="example.com",
        help="Target hostname for bandwidth test (default: example.com)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Print header
    print_header("Enhanced Network Information and Diagnostics Tool")
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    print(f"Hostname: {socket.gethostname()}")
    print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check privileges
    check_root_privileges()

    try:
        # Execute the requested operation
        if args.operation == "interfaces":
            get_network_interfaces()

        elif args.operation == "ip":
            get_ip_addresses()

        elif args.operation == "ping":
            ping_target(args.target, args.count, args.interval)

        elif args.operation == "traceroute":
            traceroute_target(args.target, args.max_hops)

        elif args.operation == "dns":
            record_types = args.types.split(",")
            dns_lookup(args.hostname, record_types)

        elif args.operation == "scan":
            port_scan(args.target, args.ports, args.timeout)

        elif args.operation == "monitor":
            monitor_latency(args.target, args.count, args.interval)

        elif args.operation == "bandwidth":
            bandwidth_test(args.target)

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Operation interrupted by user{Colors.ENDC}")
        sys.exit(130)

    except Exception as e:
        print(f"{Colors.ERROR}Unexpected error: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
