#!/usr/bin/env python3
"""
Enhanced System Resource Monitor

A comprehensive monitoring utility for Linux systems that provides real-time
information about critical system resources, including:
  • Storage devices and usage
  • Network interfaces and traffic
  • CPU utilization
  • Memory consumption
  • Top processes by resource usage

Features:
  • Nord-themed color output with intuitive visualizations
  • Real-time monitoring with configurable refresh rates
  • Visual progress bars for resource utilization
  • Detailed system information
  • Export capabilities to various formats
  • Resource trending information
  • Customizable display options

Usage:
  python system_monitor.py [options]

Note: Some monitoring features require root privileges.
"""

import argparse
import csv
import datetime
import json
import math
import os
import platform
import pwd
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Union, Any, Callable, DefaultDict

#####################################
# Configuration
#####################################

# Default settings
DEFAULT_REFRESH_RATE = 2.0  # seconds
DEFAULT_HISTORY_POINTS = 60  # number of data points to keep for trends
DEFAULT_DISPLAY_ROWS = 5  # number of processes to show

# Display settings
ENABLE_ANIMATIONS = True
PROGRESS_BAR_WIDTH = 40
GRAPH_WIDTH = 50
GRAPH_HEIGHT = 5

# File paths
PROC_STAT_PATH = "/proc/stat"
PROC_MEMINFO_PATH = "/proc/meminfo"
PROC_NET_DEV_PATH = "/proc/net/dev"
PROC_MOUNTS_PATH = "/proc/mounts"
PROC_PARTITIONS_PATH = "/proc/partitions"
PROC_UPTIME_PATH = "/proc/uptime"

# Export defaults
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")

#####################################
# UI and Color Definitions (Nord Theme)
#####################################


class NordColors:
    """ANSI color codes using Nord color palette"""

    # Base colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Nord theme foreground colors
    POLAR_NIGHT_0 = "\033[38;2;46;52;64m"  # nord0
    POLAR_NIGHT_1 = "\033[38;2;59;66;82m"  # nord1
    POLAR_NIGHT_2 = "\033[38;2;67;76;94m"  # nord2
    POLAR_NIGHT_3 = "\033[38;2;76;86;106m"  # nord3

    SNOW_STORM_0 = "\033[38;2;216;222;233m"  # nord4
    SNOW_STORM_1 = "\033[38;2;229;233;240m"  # nord5
    SNOW_STORM_2 = "\033[38;2;236;239;244m"  # nord6

    FROST_0 = "\033[38;2;143;188;187m"  # nord7
    FROST_1 = "\033[38;2;136;192;208m"  # nord8
    FROST_2 = "\033[38;2;129;161;193m"  # nord9
    FROST_3 = "\033[38;2;94;129;172m"  # nord10

    AURORA_RED = "\033[38;2;191;97;106m"  # nord11
    AURORA_ORANGE = "\033[38;2;208;135;112m"  # nord12
    AURORA_YELLOW = "\033[38;2;235;203;139m"  # nord13
    AURORA_GREEN = "\033[38;2;163;190;140m"  # nord14
    AURORA_PURPLE = "\033[38;2;180;142;173m"  # nord15

    # Aliases for semantic meaning
    ERROR = AURORA_RED
    WARNING = AURORA_YELLOW
    SUCCESS = AURORA_GREEN
    INFO = FROST_1
    HEADER = FROST_2
    MUTED = POLAR_NIGHT_3
    NORMAL = SNOW_STORM_0
    HIGHLIGHT = AURORA_PURPLE

    # Background variants
    BG_DARK = "\033[48;2;46;52;64m"  # Background with nord0
    BG_LIGHT = "\033[48;2;76;86;106m"  # Background with nord3


#####################################
# Helper Functions
#####################################


def format_bytes(bytes_value: int, binary: bool = True) -> str:
    """
    Format bytes to human-readable format.

    Args:
        bytes_value: Number of bytes to format
        binary: Use binary (1024) or decimal (1000) units

    Returns:
        Formatted byte string
    """
    if bytes_value < 0:
        return "0 B"

    base = 1024 if binary else 1000
    units = (
        ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        if binary
        else ["B", "KB", "MB", "GB", "TB", "PB"]
    )

    if bytes_value < base:
        return f"{bytes_value} {units[0]}"

    exponent = min(int(math.log(bytes_value, base)), len(units) - 1)
    quotient = float(bytes_value) / base**exponent

    return f"{quotient:.1f} {units[exponent]}"


def format_time_delta(seconds: float) -> str:
    """
    Format seconds into a human-readable time delta.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds)}s"

    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{int(hours)}h {int(minutes)}m"

    days, hours = divmod(hours, 24)
    return f"{int(days)}d {int(hours)}h"


def format_rate(bytes_per_sec: float) -> str:
    """
    Format bytes per second to a human-readable transfer rate.

    Args:
        bytes_per_sec: Bytes per second

    Returns:
        Formatted rate string
    """
    return f"{format_bytes(int(bytes_per_sec))}/s"


def print_header(message: str) -> None:
    """
    Print a formatted header message.

    Args:
        message: Message to display as header
    """
    terminal_width = os.get_terminal_size().columns
    print(f"\n{NordColors.HEADER}{NordColors.BOLD}{'═' * terminal_width}")
    print(f" {message}")
    print(f"{'═' * terminal_width}{NordColors.RESET}\n")


def print_section(message: str) -> None:
    """
    Print a formatted section header.

    Args:
        message: Section header message
    """
    print(f"\n{NordColors.FROST_1}{NordColors.BOLD}▶ {message}{NordColors.RESET}")


def print_status(message: str, status_type: str = "info") -> None:
    """
    Print a status message with appropriate coloring.

    Args:
        message: Status message to display
        status_type: Type of status (info, success, warning, error)
    """
    color = {
        "info": NordColors.INFO,
        "success": NordColors.SUCCESS,
        "warning": NordColors.WARNING,
        "error": NordColors.ERROR,
    }.get(status_type.lower(), NordColors.NORMAL)

    print(f"{color}{message}{NordColors.RESET}")


def create_progress_bar(percentage: float, width: int = PROGRESS_BAR_WIDTH) -> str:
    """
    Create a Nord-themed progress bar.

    Args:
        percentage: Percentage to visualize (0-100)
        width: Width of the progress bar

    Returns:
        Formatted progress bar string
    """
    # Clamp percentage to 0-100 range
    percentage = max(0, min(100, percentage))

    # Calculate the number of filled positions
    filled_width = int(width * percentage / 100)

    # Choose color based on percentage
    if percentage >= 90:
        color = NordColors.AURORA_RED
    elif percentage >= 75:
        color = NordColors.AURORA_ORANGE
    elif percentage >= 50:
        color = NordColors.AURORA_YELLOW
    else:
        color = NordColors.AURORA_GREEN

    # Create the progress bar
    bar = (
        f"{color}█{'█' * (filled_width - 1)}{NordColors.RESET}"
        if filled_width > 0
        else ""
    )
    bar += f"{NordColors.MUTED}{'░' * (width - filled_width)}{NordColors.RESET}"

    return f"[{bar}] {percentage:.1f}%"


def run_command(cmd: List[str], timeout: int = 5, shell: bool = False) -> str:
    """
    Run a command with proper error handling and return the output.

    Args:
        cmd: Command to run as list of strings or shell command
        timeout: Maximum seconds to wait for command
        shell: Whether to run command in shell

    Returns:
        Command output or empty string on error
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
            shell=shell,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_status(f"Command failed: {e}", "error")
        return ""
    except subprocess.TimeoutExpired:
        print_status(f"Command timed out: {cmd}", "warning")
        return ""
    except Exception as e:
        print_status(f"Error running command: {e}", "error")
        return ""


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle interrupt signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True
    print(
        f"\n{NordColors.WARNING}Caught signal {sig}, shutting down gracefully...{NordColors.RESET}"
    )


#####################################
# Data Classes
#####################################


@dataclass
class DiskInfo:
    """Enhanced storage device information"""

    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str = "unknown"
    io_stats: Dict[str, Union[int, float]] = field(default_factory=dict)

    def get_io_display(self) -> str:
        """Get formatted I/O statistics string"""
        if not self.io_stats:
            return "No I/O data"

        reads = self.io_stats.get("reads", 0)
        writes = self.io_stats.get("writes", 0)
        read_bytes = self.io_stats.get("read_bytes", 0)
        write_bytes = self.io_stats.get("write_bytes", 0)

        return (
            f"R: {format_bytes(read_bytes)} ({reads:,} ops), "
            f"W: {format_bytes(write_bytes)} ({writes:,} ops)"
        )


@dataclass
class NetworkInfo:
    """Enhanced network interface information"""

    name: str
    ipv4: str = "N/A"
    ipv6: str = "N/A"
    mac: str = "N/A"
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    bytes_sent_rate: float = 0
    bytes_recv_rate: float = 0
    is_up: bool = True
    is_loopback: bool = False
    mtu: int = 0

    def get_traffic_display(self) -> str:
        """Get formatted traffic statistics string"""
        return (
            f"▼ {format_rate(self.bytes_recv_rate)} "
            f"({format_bytes(self.bytes_recv)} total) | "
            f"▲ {format_rate(self.bytes_sent_rate)} "
            f"({format_bytes(self.bytes_sent)} total)"
        )


@dataclass
class CpuInfo:
    """CPU information and utilization"""

    usage_percent: float = 0.0
    core_count: int = 0
    model_name: str = "Unknown"
    frequency_mhz: float = 0.0
    temperature: float = 0.0
    load_avg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    per_core_usage: List[float] = field(default_factory=list)


@dataclass
class MemoryInfo:
    """Memory usage information"""

    total: int = 0
    used: int = 0
    free: int = 0
    available: int = 0
    buffers: int = 0
    cached: int = 0
    swap_total: int = 0
    swap_used: int = 0
    swap_free: int = 0
    percent_used: float = 0.0
    swap_percent_used: float = 0.0


@dataclass
class ProcessInfo:
    """Process information"""

    pid: int
    name: str
    user: str
    cpu_percent: float
    memory_percent: float
    memory_rss: int
    status: str
    threads: int
    cmdline: str
    started: float


#####################################
# Monitoring Classes
#####################################


class DiskMonitor:
    """Monitor disk and storage information"""

    def __init__(self) -> None:
        """Initialize disk monitor"""
        self.disks: List[DiskInfo] = []
        self.last_update_time: float = 0
        self.last_io_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
        """Update disk information"""
        self.disks = []

        # Get disk usage information
        try:
            # Use df command to get disk usage
            df_output = run_command(["df", "-P", "-k", "-T"])

            # Read I/O stats from /proc/diskstats
            io_stats = self._get_disk_io_stats()

            # Parse df output
            for line in df_output.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 7:
                    continue

                device = parts[0]
                filesystem = parts[1]
                # Skip pseudo filesystems
                if filesystem in ("tmpfs", "devtmpfs", "squashfs", "overlay"):
                    continue

                # Extract disk name for I/O stats matching
                disk_name = os.path.basename(device)

                total = int(parts[2]) * 1024
                used = int(parts[3]) * 1024
                free = int(parts[4]) * 1024
                percent = float(parts[5].rstrip("%"))
                mountpoint = parts[6]

                disk_info = DiskInfo(
                    device=device,
                    mountpoint=mountpoint,
                    total=total,
                    used=used,
                    free=free,
                    percent=percent,
                    filesystem=filesystem,
                    io_stats=io_stats.get(disk_name, {}),
                )

                self.disks.append(disk_info)

        except Exception as e:
            print_status(f"Error collecting disk info: {e}", "error")

    def _get_disk_io_stats(self) -> Dict[str, Dict[str, Union[int, float]]]:
        """
        Collect disk I/O statistics

        Returns:
            Dictionary of disk I/O statistics
        """
        current_time = time.time()
        current_stats = {}
        result_stats = {}

        try:
            # Read diskstats
            with open("/proc/diskstats", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 14:
                        continue

                    # Get the disk name from the third field
                    disk_name = parts[2]

                    # Skip partitions and non-physical devices
                    if re.match(r"^(loop|ram|sr|fd|dm-)", disk_name):
                        continue

                    # Parse the I/O stats
                    reads = int(parts[3])
                    read_sectors = int(parts[5])
                    writes = int(parts[7])
                    write_sectors = int(parts[9])

                    # Store in current stats
                    current_stats[disk_name] = {
                        "reads": reads,
                        "read_sectors": read_sectors,
                        "writes": writes,
                        "write_sectors": write_sectors,
                        "read_bytes": read_sectors * 512,  # Sector size is 512 bytes
                        "write_bytes": write_sectors * 512,
                    }

                    # Calculate rates if we have previous data
                    if self.last_update_time > 0 and disk_name in self.last_io_stats:
                        last_stats = self.last_io_stats[disk_name]
                        time_diff = current_time - self.last_update_time

                        if time_diff > 0:
                            # Calculate read and write rates
                            read_rate = (
                                current_stats[disk_name]["read_bytes"]
                                - last_stats["read_bytes"]
                            ) / time_diff
                            write_rate = (
                                current_stats[disk_name]["write_bytes"]
                                - last_stats["write_bytes"]
                            ) / time_diff

                            current_stats[disk_name]["read_rate"] = read_rate
                            current_stats[disk_name]["write_rate"] = write_rate

                    # Add to result stats
                    result_stats[disk_name] = current_stats[disk_name]

        except Exception as e:
            print_status(f"Error reading disk I/O stats: {e}", "error")

        # Update last stats and time
        self.last_io_stats = current_stats
        self.last_update_time = current_time

        return result_stats


class NetworkMonitor:
    """Monitor network interfaces and traffic"""

    def __init__(self) -> None:
        """Initialize network monitor"""
        self.interfaces: List[NetworkInfo] = []
        self.last_update_time: float = 0
        self.last_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
        """Update network information"""
        current_time = time.time()
        current_stats = {}

        try:
            # Read network statistics from /proc/net/dev
            with open(PROC_NET_DEV_PATH, "r") as f:
                # Skip header lines
                f.readline()
                f.readline()

                for line in f:
                    if ":" not in line:
                        continue

                    name, stats_str = line.split(":")
                    name = name.strip()

                    # Parse network stats
                    stats = stats_str.split()
                    bytes_recv = int(stats[0])
                    packets_recv = int(stats[1])
                    bytes_sent = int(stats[8])
                    packets_sent = int(stats[9])

                    # Store current stats
                    current_stats[name] = {
                        "bytes_recv": bytes_recv,
                        "packets_recv": packets_recv,
                        "bytes_sent": bytes_sent,
                        "packets_sent": packets_sent,
                    }

                    # Determine if interface is up and get IP address
                    ip_info = self._get_interface_ip(name)

                    # Calculate rates if we have previous data
                    bytes_recv_rate = 0
                    bytes_sent_rate = 0

                    if self.last_update_time > 0 and name in self.last_stats:
                        time_diff = current_time - self.last_update_time
                        if time_diff > 0:
                            bytes_recv_rate = (
                                bytes_recv - self.last_stats[name]["bytes_recv"]
                            ) / time_diff
                            bytes_sent_rate = (
                                bytes_sent - self.last_stats[name]["bytes_sent"]
                            ) / time_diff

                    # Create network interface info
                    interface = NetworkInfo(
                        name=name,
                        ipv4=ip_info.get("ipv4", "N/A"),
                        ipv6=ip_info.get("ipv6", "N/A"),
                        mac=ip_info.get("mac", "N/A"),
                        bytes_sent=bytes_sent,
                        bytes_recv=bytes_recv,
                        packets_sent=packets_sent,
                        packets_recv=packets_recv,
                        bytes_sent_rate=bytes_sent_rate,
                        bytes_recv_rate=bytes_recv_rate,
                        is_up=ip_info.get("is_up", False),
                        is_loopback=(name == "lo"),
                        mtu=ip_info.get("mtu", 0),
                    )

                    self.interfaces.append(interface)

            # Update last stats and time
            self.last_stats = current_stats
            self.last_update_time = current_time

        except Exception as e:
            print_status(f"Error collecting network info: {e}", "error")

    def _get_interface_ip(self, interface: str) -> Dict[str, Any]:
        """
        Get IP address information for a network interface

        Args:
            interface: Network interface name

        Returns:
            Dictionary with IP address information
        """
        ip_info = {"ipv4": "N/A", "ipv6": "N/A", "mac": "N/A", "is_up": False, "mtu": 0}

        try:
            # Get interface info using ip command
            ip_output = run_command(["ip", "addr", "show", interface])

            # Parse output
            for line in ip_output.splitlines():
                line = line.strip()

                # Check if interface is up
                if "state UP" in line:
                    ip_info["is_up"] = True

                # Get MTU
                mtu_match = re.search(r"mtu (\d+)", line)
                if mtu_match:
                    ip_info["mtu"] = int(mtu_match.group(1))

                # Get MAC address
                mac_match = re.search(r"link/\w+ ([0-9a-f:]{17})", line)
                if mac_match:
                    ip_info["mac"] = mac_match.group(1)

                # Get IPv4 address
                ipv4_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                if ipv4_match:
                    ip_info["ipv4"] = ipv4_match.group(1)

                # Get IPv6 address (simplified)
                ipv6_match = re.search(r"inet6 ([0-9a-f:]+)", line)
                if ipv6_match:
                    ip_info["ipv6"] = ipv6_match.group(1)

        except Exception:
            # Fall back to simpler method for the primary IPv4
            if interface != "lo" and ip_info["ipv4"] == "N/A":
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip_info["ipv4"] = s.getsockname()[0]
                    s.close()
                    ip_info["is_up"] = True
                except Exception:
                    pass

        return ip_info


class CpuMonitor:
    """Monitor CPU usage and information"""

    def __init__(self) -> None:
        """Initialize CPU monitor"""
        self.info = CpuInfo()
        self.last_cpu_stats: Dict[str, List[int]] = {}
        self.history: deque = deque(maxlen=DEFAULT_HISTORY_POINTS)
        self.cpu_count = os.cpu_count() or 1  # Number of CPU cores

    def update(self) -> None:
        """Update CPU information"""
        try:
            # Get CPU model information (once)
            if not self.info.model_name:
                self._get_cpu_model_info()

            # Get current usage
            self._update_cpu_usage()

            # Get load average
            self._update_load_average()

            # Try to get CPU temperature (if sensors available)
            self._update_cpu_temperature()

            # Add to history
            self.history.append(self.info.usage_percent)

        except Exception as e:
            print_status(f"Error collecting CPU info: {e}", "error")

    def _update_cpu_usage(self) -> None:
        """Update CPU usage statistics"""
        try:
            # Read /proc/stat for CPU statistics
            with open(PROC_STAT_PATH, "r") as f:
                cpu_stats = {}

                for line in f:
                    if not line.startswith("cpu"):
                        continue

                    fields = line.split()
                    if len(fields) < 8:
                        continue

                    cpu_name = fields[0]

                    # Parse the values (user, nice, system, idle, iowait, irq, softirq, steal)
                    values = [int(val) for val in fields[1:9]]
                    cpu_stats[cpu_name] = values

                # Calculate CPU usage percentage
                if "cpu" in cpu_stats:
                    if "cpu" in self.last_cpu_stats:
                        # Current values
                        current = cpu_stats["cpu"]
                        # Previous values
                        previous = self.last_cpu_stats["cpu"]

                        # Calculate differences
                        diff_idle = current[3] - previous[3]
                        diff_total = sum(current) - sum(previous)

                        # Calculate usage percentage
                        if diff_total > 0:
                            self.info.usage_percent = 100.0 * (
                                1.0 - diff_idle / diff_total
                            )

                    # Store for next calculation
                    self.last_cpu_stats["cpu"] = cpu_stats["cpu"]

                # Calculate per-core usage
                per_core_usage = []
                for i in range(self.cpu_count):
                    core_name = f"cpu{i}"
                    if core_name in cpu_stats:
                        if core_name in self.last_cpu_stats:
                            # Current values
                            current = cpu_stats[core_name]
                            # Previous values
                            previous = self.last_cpu_stats[core_name]

                            # Calculate differences
                            diff_idle = current[3] - previous[3]
                            diff_total = sum(current) - sum(previous)

                            # Calculate usage percentage
                            if diff_total > 0:
                                usage = 100.0 * (1.0 - diff_idle / diff_total)
                                per_core_usage.append(usage)

                        # Store for next calculation
                        self.last_cpu_stats[core_name] = cpu_stats[core_name]

                self.info.per_core_usage = per_core_usage
                self.info.core_count = len(per_core_usage)

        except Exception as e:
            print_status(f"Error updating CPU usage: {e}", "error")

    def _update_load_average(self) -> None:
        """Update system load average"""
        try:
            with open(PROC_UPTIME_PATH, "r") as f:
                uptime_str = f.read().strip()
                self.info.uptime = float(uptime_str.split()[0])

            with open("/proc/loadavg", "r") as f:
                load_avg_str = f.read().strip()
                load_parts = load_avg_str.split()
                self.info.load_avg = [
                    float(load_parts[0]),
                    float(load_parts[1]),
                    float(load_parts[2]),
                ]
        except Exception as e:
            print_status(f"Error updating load average: {e}", "error")

    def _update_cpu_temperature(self) -> None:
        """Update CPU temperature if available"""
        try:
            # Use sensors command if available
            sensors_output = run_command(["sensors"], timeout=2)

            # Parse the output looking for CPU temperature
            if sensors_output:
                for line in sensors_output.splitlines():
                    if any(
                        cpu_temp in line.lower()
                        for cpu_temp in ["core temp", "cpu temp", "package id"]
                    ):
                        temp_match = re.search(r"[+-](\d+\.\d+)°C", line)
                        if temp_match:
                            self.info.temperature = float(temp_match.group(1))
                            break
        except Exception:
            # Ignore temperature errors
            pass

    def _get_cpu_model_info(self) -> None:
        """Get CPU model information"""
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    # Look for model name
                    if line.startswith("model name"):
                        self.info.model_name = line.split(":", 1)[1].strip()
                        break

            # Get CPU frequency
            try:
                freq_output = run_command(
                    ["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"]
                )
                if freq_output and freq_output.isdigit():
                    # Convert from kHz to MHz
                    self.info.frequency_mhz = float(freq_output) / 1000
            except Exception:
                # Fall back to cpuinfo
                try:
                    with open("/proc/cpuinfo", "r") as f:
                        for line in f:
                            if line.startswith("cpu MHz"):
                                self.info.frequency_mhz = float(
                                    line.split(":", 1)[1].strip()
                                )
                                break
                except Exception:
                    # Just leave at default
                    pass

        except Exception as e:
            print_status(f"Error getting CPU model info: {e}", "error")


class MemoryMonitor:
    """Monitor memory usage"""

    def __init__(self) -> None:
        """Initialize memory monitor"""
        self.info = MemoryInfo()
        self.history: deque = deque(maxlen=DEFAULT_HISTORY_POINTS)

    def update(self) -> None:
        """Update memory information"""
        try:
            # Read /proc/meminfo for memory statistics
            mem_info = {}
            with open(PROC_MEMINFO_PATH, "r") as f:
                for line in f:
                    if ":" not in line:
                        continue

                    key, value = line.split(":", 1)
                    key = key.strip()

                    # Remove 'kB' and convert to bytes
                    value = value.strip()
                    if value.endswith("kB"):
                        value_kb = int(value[:-2].strip())
                        mem_info[key] = value_kb * 1024
                    else:
                        try:
                            mem_info[key] = int(value)
                        except ValueError:
                            mem_info[key] = value

            # Fill memory info structure
            self.info.total = mem_info.get("MemTotal", 0)
            self.info.free = mem_info.get("MemFree", 0)
            self.info.available = mem_info.get("MemAvailable", self.info.free)
            self.info.buffers = mem_info.get("Buffers", 0)
            self.info.cached = mem_info.get("Cached", 0)
            self.info.swap_total = mem_info.get("SwapTotal", 0)
            self.info.swap_free = mem_info.get("SwapFree", 0)

            # Calculate derived values
            self.info.used = (
                self.info.total - self.info.free - self.info.buffers - self.info.cached
            )
            self.info.swap_used = self.info.swap_total - self.info.swap_free

            # Calculate percentages
            if self.info.total > 0:
                # True memory usage (excluding buffers/cache)
                self.info.percent_used = 100.0 * self.info.used / self.info.total

            if self.info.swap_total > 0:
                self.info.swap_percent_used = (
                    100.0 * self.info.swap_used / self.info.swap_total
                )

            # Add to history
            self.history.append(self.info.percent_used)

        except Exception as e:
            print_status(f"Error collecting memory info: {e}", "error")


class ProcessMonitor:
    """Monitor system processes"""

    def __init__(self) -> None:
        """Initialize process monitor"""
        self.processes: List[ProcessInfo] = []
        self.process_count = 0
        self.threads_count = 0

        # For CPU percentage calculation
        self.last_process_times: Dict[int, float] = {}
        self.last_update_time = 0

    def update(self) -> None:
        """Update process information"""
        current_time = time.time()
        try:
            # Get all processes
            processes = []
            total_threads = 0

            # Get all numeric directories in /proc (PIDs)
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue

                pid = int(pid_dir)
                try:
                    # Read process information
                    process = self._get_process_info(pid, current_time)
                    if process:
                        processes.append(process)
                        total_threads += process.threads
                except Exception:
                    # Skip processes that disappear during processing
                    continue

            # Sort processes by CPU usage (descending)
            processes.sort(key=lambda p: p.cpu_percent, reverse=True)

            # Keep the top processes
            self.processes = processes[:DEFAULT_DISPLAY_ROWS]
            self.process_count = len(processes)
            self.threads_count = total_threads

            # Update last update time
            self.last_update_time = current_time

        except Exception as e:
            print_status(f"Error collecting process info: {e}", "error")

    def _get_process_info(self, pid: int, current_time: float) -> Optional[ProcessInfo]:
        """
        Get information about a specific process

        Args:
            pid: Process ID
            current_time: Current timestamp

        Returns:
            ProcessInfo object or None if process is no longer available
        """
        try:
            # Check if process still exists
            stat_path = f"/proc/{pid}/stat"
            if not os.path.exists(stat_path):
                return None

            # Read the /proc/[pid]/stat file
            with open(stat_path, "r") as f:
                stat_content = f.read().strip()

            # Parse the stat file
            # The second field (comm) is in parentheses and may contain spaces
            m = re.match(r"(\d+) \((.+?)\) (\S) .+", stat_content)
            if not m:
                return None

            pid = int(m.group(1))
            name = m.group(2)
            state = m.group(3)

            # Get user name
            try:
                with open(f"/proc/{pid}/status", "r") as f:
                    for line in f:
                        if line.startswith("Uid:"):
                            uid = int(line.split()[1])
                            try:
                                user = pwd.getpwuid(uid).pw_name
                            except KeyError:
                                user = str(uid)
                            break
                    else:
                        user = "?"
            except Exception:
                user = "?"

            # Get thread count
            try:
                with open(f"/proc/{pid}/status", "r") as f:
                    for line in f:
                        if line.startswith("Threads:"):
                            threads = int(line.split()[1])
                            break
                    else:
                        threads = 1
            except Exception:
                threads = 1

            # Get memory information
            try:
                with open(f"/proc/{pid}/statm", "r") as f:
                    statm = f.read().strip().split()
                    rss = int(statm[1]) * os.sysconf("SC_PAGE_SIZE")
            except Exception:
                rss = 0

            # Get start time and calculate CPU usage
            start_time = 0
            cpu_time = 0

            # Parse stat file in more detail to get CPU time
            with open(stat_path, "r") as f:
                stat_parts = f.read().strip().split()

                # Utime is at index 13, stime at index 14
                if len(stat_parts) >= 15:
                    utime = int(stat_parts[13])
                    stime = int(stat_parts[14])
                    cpu_time = (utime + stime) / os.sysconf("SC_CLK_TCK")

                # Start time is at index 21
                if len(stat_parts) >= 22:
                    start_ticks = int(stat_parts[21])
                    uptime = 0
                    with open(PROC_UPTIME_PATH, "r") as uptime_file:
                        uptime = float(uptime_file.read().split()[0])

                    start_time = (
                        current_time - uptime + (start_ticks / os.sysconf("SC_CLK_TCK"))
                    )

            # Calculate CPU usage percentage
            cpu_percent = 0.0
            if pid in self.last_process_times and self.last_update_time > 0:
                time_diff = current_time - self.last_update_time
                cpu_diff = cpu_time - self.last_process_times[pid]

                if time_diff > 0:
                    # Multiply by 100 for percentage and by # of processors for true usage
                    cpu_percent = 100.0 * cpu_diff / time_diff * os.cpu_count()

            # Store current CPU time for next calculation
            self.last_process_times[pid] = cpu_time

            # Get command line
            try:
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    cmdline = f.read().replace("\0", " ").strip()
                    if not cmdline:
                        cmdline = name  # Use name if cmdline is empty
            except Exception:
                cmdline = name

            # Calculate memory percent
            memory_percent = 0.0
            try:
                with open(PROC_MEMINFO_PATH, "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            mem_total = (
                                int(line.split()[1]) * 1024
                            )  # Convert kB to bytes
                            if mem_total > 0:
                                memory_percent = 100.0 * rss / mem_total
                            break
            except Exception:
                pass

            # Map state letter to descriptive status
            status_map = {
                "R": "Running",
                "S": "Sleeping",
                "D": "Disk Wait",
                "Z": "Zombie",
                "T": "Stopped",
                "t": "Tracing",
                "X": "Dead",
                "I": "Idle",
            }
            status = status_map.get(state, f"Unknown({state})")

            return ProcessInfo(
                pid=pid,
                name=name,
                user=user,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_rss=rss,
                status=status,
                threads=threads,
                cmdline=cmdline,
                started=start_time,
            )

        except Exception:
            # Process may have terminated during collection
            return None


class SystemMonitor:
    """Complete system resource monitoring utility"""

    def __init__(self, refresh_rate: float = DEFAULT_REFRESH_RATE):
        """
        Initialize system monitor with components.

        Args:
            refresh_rate: Seconds between updates
        """
        self.refresh_rate = refresh_rate
        self.start_time = time.time()

        # Initialize monitors
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor()

        # Settings
        self.display_all_disks = True
        self.display_all_interfaces = True
        self.display_settings = {
            "cpu": True,
            "memory": True,
            "disks": True,
            "network": True,
            "processes": True,
        }

        # For refresh display
        self.iteration = 0

    def update(self) -> None:
        """Update all system monitors"""
        self.disk_monitor.update()
        self.network_monitor.update()
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.process_monitor.update()

    def _draw_graph(
        self, data: List[float], width: int = GRAPH_WIDTH, height: int = GRAPH_HEIGHT
    ) -> None:
        """
        Draw a simple ASCII graph of data

        Args:
            data: List of data points (0-100)
            width: Graph width
            height: Graph height
        """
        if not data:
            return

        # Create graph array
        graph = [[" " for _ in range(width)] for _ in range(height)]

        # Fill in the graph
        max_value = max(max(data), 1.0)  # Avoid division by zero
        recent_data = list(data)[-width:]

        for x, value in enumerate(recent_data):
            # Scale value to height
            scaled_value = min(value / max_value * height, height)

            # Fill in the columns
            for y in range(height):
                if height - y - 1 < scaled_value:
                    # Choose character based on value
                    if value > 90:
                        char = NordColors.AURORA_RED + "█" + NordColors.RESET
                    elif value > 70:
                        char = NordColors.AURORA_ORANGE + "█" + NordColors.RESET
                    elif value > 40:
                        char = NordColors.AURORA_YELLOW + "█" + NordColors.RESET
                    else:
                        char = NordColors.AURORA_GREEN + "█" + NordColors.RESET

                    graph[height - y - 1][x] = char

        # Print the graph
        for row in graph:
            print("".join(row))

        # Print x-axis
        max_label = f"{max_value:.1f}%"
        print(f"{max_label:<{width}}")

    def display_cpu_info(self) -> None:
        """Display CPU information"""
        if not self.display_settings["cpu"]:
            return

        print_section("CPU Information")

        # Display basic CPU info
        print(
            f"{NordColors.NORMAL}Model: {NordColors.FROST_1}{self.cpu_monitor.info.model_name}{NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}Cores: {NordColors.FROST_1}{self.cpu_monitor.info.core_count}{NordColors.RESET}"
        )

        if self.cpu_monitor.info.frequency_mhz > 0:
            print(
                f"{NordColors.NORMAL}Frequency: {NordColors.FROST_1}{self.cpu_monitor.info.frequency_mhz:.1f} MHz{NordColors.RESET}"
            )

        if self.cpu_monitor.info.temperature > 0:
            # Choose color based on temperature
            temp = self.cpu_monitor.info.temperature
            temp_color = (
                NordColors.AURORA_RED
                if temp > 80
                else NordColors.AURORA_ORANGE
                if temp > 70
                else NordColors.AURORA_YELLOW
                if temp > 60
                else NordColors.AURORA_GREEN
            )
            print(
                f"{NordColors.NORMAL}Temperature: {temp_color}{temp:.1f}°C{NordColors.RESET}"
            )

        # Display load averages
        load_1, load_5, load_15 = self.cpu_monitor.info.load_avg
        load_color = (
            NordColors.AURORA_RED
            if load_1 > self.cpu_monitor.info.core_count
            else NordColors.AURORA_YELLOW
            if load_1 > self.cpu_monitor.info.core_count * 0.7
            else NordColors.AURORA_GREEN
        )
        print(
            f"{NordColors.NORMAL}Load Average: {load_color}{load_1:.2f}{NordColors.RESET} (1m), {load_5:.2f} (5m), {load_15:.2f} (15m)"
        )

        # Display current CPU usage
        cpu_usage = self.cpu_monitor.info.usage_percent
        usage_color = (
            NordColors.AURORA_RED
            if cpu_usage > 90
            else NordColors.AURORA_ORANGE
            if cpu_usage > 70
            else NordColors.AURORA_YELLOW
            if cpu_usage > 40
            else NordColors.AURORA_GREEN
        )
        print(
            f"{NordColors.NORMAL}CPU Usage: {usage_color}{cpu_usage:.1f}%{NordColors.RESET}"
        )

        # Show progress bar
        print(
            f"{NordColors.NORMAL}Usage: {create_progress_bar(cpu_usage)}{NordColors.RESET}"
        )

        # Display per-core usage bars if we have enough cores
        if (
            self.cpu_monitor.info.core_count > 1
            and self.cpu_monitor.info.core_count <= 32
        ):
            print(f"\n{NordColors.NORMAL}Per-Core Usage:{NordColors.RESET}")

            # Create a multi-column layout for cores
            num_cores = len(self.cpu_monitor.info.per_core_usage)

            # Determine number of columns based on terminal width
            term_width = os.get_terminal_size().columns
            max_bar_width = 25  # Maximum width for progress bars
            bar_width = min(
                max_bar_width, term_width // 2 - 15
            )  # Allow for labels and spacing

            # Display in columns
            if num_cores <= 8 or term_width < 100:
                # Single column for few cores or narrow terminals
                for i, usage in enumerate(self.cpu_monitor.info.per_core_usage):
                    print(
                        f"{NordColors.NORMAL}Core {i:2d}: {create_progress_bar(usage, bar_width)}{NordColors.RESET}"
                    )
            else:
                # Calculate number of cores per column
                cols = 2 if term_width < 140 else 3
                cores_per_col = (num_cores + cols - 1) // cols

                # Create each row
                for row in range(cores_per_col):
                    row_str = ""
                    for col in range(cols):
                        idx = row + col * cores_per_col
                        if idx < num_cores:
                            usage = self.cpu_monitor.info.per_core_usage[idx]
                            core_str = f"{NordColors.NORMAL}Core {idx:2d}: {create_progress_bar(usage, bar_width)}{NordColors.RESET}"
                            row_str += core_str + " " * 5
                    print(row_str)

        # Show usage history graph
        if len(self.cpu_monitor.history) > 1:
            print(f"\n{NordColors.NORMAL}CPU Usage History:{NordColors.RESET}")
            self._draw_graph(list(self.cpu_monitor.history))

    def display_memory_info(self) -> None:
        """Display memory information"""
        if not self.display_settings["memory"]:
            return

        print_section("Memory Information")

        # Display RAM usage
        total = self.memory_monitor.info.total
        used = self.memory_monitor.info.used
        avail = self.memory_monitor.info.available
        percent = self.memory_monitor.info.percent_used

        print(
            f"{NordColors.NORMAL}Total RAM: {NordColors.FROST_1}{format_bytes(total)}{NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}Used RAM: {NordColors.FROST_1}{format_bytes(used)} ({percent:.1f}%){NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}Available: {NordColors.FROST_1}{format_bytes(avail)}{NordColors.RESET}"
        )

        # RAM usage progress bar
        print(
            f"{NordColors.NORMAL}Usage: {create_progress_bar(percent)}{NordColors.RESET}"
        )

        # Display Swap usage if available
        if self.memory_monitor.info.swap_total > 0:
            swap_total = self.memory_monitor.info.swap_total
            swap_used = self.memory_monitor.info.swap_used
            swap_percent = self.memory_monitor.info.swap_percent_used

            print(
                f"\n{NordColors.NORMAL}Total Swap: {NordColors.FROST_1}{format_bytes(swap_total)}{NordColors.RESET}"
            )
            print(
                f"{NordColors.NORMAL}Used Swap: {NordColors.FROST_1}{format_bytes(swap_used)} ({swap_percent:.1f}%){NordColors.RESET}"
            )

            # Swap usage progress bar
            print(
                f"{NordColors.NORMAL}Swap: {create_progress_bar(swap_percent)}{NordColors.RESET}"
            )

        # Show memory usage history graph
        if len(self.memory_monitor.history) > 1:
            print(f"\n{NordColors.NORMAL}Memory Usage History:{NordColors.RESET}")
            self._draw_graph(list(self.memory_monitor.history))

    def display_disk_info(self) -> None:
        """Display disk information"""
        if not self.display_settings["disks"]:
            return

        print_section("Disk Information")

        # Header for disk table
        print(f"{NordColors.BOLD}{NordColors.FROST_1}")
        print(
            f"{'Device':<15} {'Mountpoint':<15} {'Size':<10} {'Used':<10} {'Free':<10} {'Use%':<8} {'Filesystem':<10}"
        )
        print(f"{NordColors.RESET}{NordColors.MUTED}{'-' * 80}{NordColors.RESET}")

        # Sort disks by device name
        sorted_disks = sorted(self.disk_monitor.disks, key=lambda d: d.device)

        for disk in sorted_disks:
            # Skip pseudo filesystems unless display_all_disks is True
            if not self.display_all_disks and disk.filesystem in ("tmpfs", "devtmpfs"):
                continue

            # Choose color based on usage percentage
            usage_color = (
                NordColors.AURORA_RED
                if disk.percent >= 90
                else NordColors.AURORA_ORANGE
                if disk.percent >= 75
                else NordColors.AURORA_YELLOW
                if disk.percent >= 50
                else NordColors.AURORA_GREEN
            )

            # Truncate long device names and mount points
            device = disk.device[:14]
            mountpoint = disk.mountpoint[:14]

            # Print disk information row
            print(
                f"{device:<15} {mountpoint:<15} "
                f"{format_bytes(disk.total):<10} {format_bytes(disk.used):<10} "
                f"{format_bytes(disk.free):<10} {usage_color}{disk.percent:>6.1f}%{NordColors.RESET} "
                f"{disk.filesystem:<10}"
            )

            # Show I/O statistics if available
            if "read_rate" in disk.io_stats and "write_rate" in disk.io_stats:
                read_rate = disk.io_stats["read_rate"]
                write_rate = disk.io_stats["write_rate"]

                print(
                    f"  {NordColors.NORMAL}I/O: "
                    f"Read {format_rate(read_rate)} | "
                    f"Write {format_rate(write_rate)}{NordColors.RESET}"
                )

        # Display overall summary
        try:
            total_size = sum(disk.total for disk in self.disk_monitor.disks)
            total_used = sum(disk.used for disk in self.disk_monitor.disks)
            total_free = sum(disk.free for disk in self.disk_monitor.disks)

            if total_size > 0:
                percent_used = 100.0 * total_used / total_size

                print(f"\n{NordColors.NORMAL}Total Storage: {format_bytes(total_size)}")
                print(f"Total Used: {format_bytes(total_used)} ({percent_used:.1f}%)")
                print(f"Total Free: {format_bytes(total_free)}")

                # Overall usage progress bar
                print(
                    f"Overall Usage: {create_progress_bar(percent_used)}{NordColors.RESET}"
                )
        except Exception:
            pass

    def display_network_info(self) -> None:
        """Display network information"""
        if not self.display_settings["network"]:
            return

        print_section("Network Information")

        # Sort interfaces by name
        sorted_interfaces = sorted(
            self.network_monitor.interfaces, key=lambda i: (i.is_loopback, i.name)
        )

        for interface in sorted_interfaces:
            # Skip loopback interface unless display_all_interfaces is True
            if interface.is_loopback and not self.display_all_interfaces:
                continue

            # Choose color based on status
            status_color = (
                NordColors.AURORA_GREEN if interface.is_up else NordColors.AURORA_RED
            )

            # Interface header
            print(
                f"{NordColors.FROST_1}{NordColors.BOLD}{interface.name}{NordColors.RESET} "
                f"({status_color}{'Up' if interface.is_up else 'Down'}{NordColors.RESET})"
            )

            # IP addresses
            print(
                f"  {NordColors.NORMAL}IPv4: {NordColors.FROST_1}{interface.ipv4}{NordColors.RESET}"
            )
            if interface.ipv6 != "N/A":
                print(
                    f"  {NordColors.NORMAL}IPv6: {NordColors.FROST_1}{interface.ipv6}{NordColors.RESET}"
                )

            # MAC and MTU
            print(
                f"  {NordColors.NORMAL}MAC: {interface.mac}  MTU: {interface.mtu}{NordColors.RESET}"
            )

            # Traffic statistics
            print(
                f"  {NordColors.NORMAL}Traffic: {interface.get_traffic_display()}{NordColors.RESET}"
            )

            # Traffic rate bars
            if interface.bytes_recv_rate > 0 or interface.bytes_sent_rate > 0:
                # Calculate percentage based on a reference bandwidth (e.g., 1 Gbps = 125 MB/s)
                reference_bw = 125_000_000  # 1 Gbps in bytes/sec

                recv_percent = min(100, interface.bytes_recv_rate / reference_bw * 100)
                sent_percent = min(100, interface.bytes_sent_rate / reference_bw * 100)

                print(
                    f"  {NordColors.NORMAL}Receive: {create_progress_bar(recv_percent, 30)}{NordColors.RESET}"
                )
                print(
                    f"  {NordColors.NORMAL}Send:    {create_progress_bar(sent_percent, 30)}{NordColors.RESET}"
                )

            print("")  # Add empty line between interfaces

    def display_process_info(self) -> None:
        """Display process information"""
        if not self.display_settings["processes"]:
            return

        print_section("Process Information")

        # Show process and thread count
        print(
            f"{NordColors.NORMAL}Total Processes: {self.process_monitor.process_count}"
        )
        print(f"Total Threads: {self.process_monitor.threads_count}{NordColors.RESET}")

        # Header for process table
        print(f"\n{NordColors.BOLD}{NordColors.FROST_1}")
        print(
            f"{'PID':<7} {'User':<12} {'CPU%':>6} {'MEM%':>6} {'Memory':>10} {'Status':<10} {'Name':<20}"
        )
        print(f"{NordColors.RESET}{NordColors.MUTED}{'-' * 80}{NordColors.RESET}")

        # Display processes
        for process in self.process_monitor.processes:
            # Choose color based on CPU usage
            cpu_color = (
                NordColors.AURORA_RED
                if process.cpu_percent > 50
                else NordColors.AURORA_ORANGE
                if process.cpu_percent > 30
                else NordColors.AURORA_YELLOW
                if process.cpu_percent > 10
                else NordColors.NORMAL
            )

            # Choose color based on memory usage
            mem_color = (
                NordColors.AURORA_RED
                if process.memory_percent > 30
                else NordColors.AURORA_ORANGE
                if process.memory_percent > 20
                else NordColors.AURORA_YELLOW
                if process.memory_percent > 10
                else NordColors.NORMAL
            )

            # Process name (truncated if necessary)
            name = process.name
            if len(name) > 19:
                name = name[:16] + "..."

            # User (truncated if necessary)
            user = process.user
            if len(user) > 11:
                user = user[:8] + "..."

            # Print process information row
            print(
                f"{process.pid:<7} {user:<12} "
                f"{cpu_color}{process.cpu_percent:>6.1f}{NordColors.RESET} "
                f"{mem_color}{process.memory_percent:>6.1f}{NordColors.RESET} "
                f"{format_bytes(process.memory_rss):>10} "
                f"{process.status:<10} {name:<20}"
            )

    def export_data(
        self, export_format: str, output_file: Optional[str] = None
    ) -> None:
        """
        Export monitoring data to file

        Args:
            export_format: 'json' or 'csv'
            output_file: Output file path (or None for auto-generated)
        """
        try:
            # Ensure export directory exists
            os.makedirs(EXPORT_DIR, exist_ok=True)

            # Generate filename if not provided
            if output_file is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = os.path.join(
                    EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}"
                )
            elif not os.path.isabs(output_file):
                output_file = os.path.join(EXPORT_DIR, output_file)

            # Collect data to export
            export_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "system": {
                    "hostname": socket.gethostname(),
                    "platform": platform.platform(),
                    "uptime": self._get_uptime_seconds(),
                },
                "cpu": {
                    "usage_percent": self.cpu_monitor.info.usage_percent,
                    "core_count": self.cpu_monitor.info.core_count,
                    "model_name": self.cpu_monitor.info.model_name,
                    "load_avg": self.cpu_monitor.info.load_avg,
                    "per_core_usage": self.cpu_monitor.info.per_core_usage,
                },
                "memory": asdict(self.memory_monitor.info),
                "disks": [asdict(disk) for disk in self.disk_monitor.disks],
                "network": [asdict(iface) for iface in self.network_monitor.interfaces],
                "processes": [asdict(proc) for proc in self.process_monitor.processes],
            }

            # Export based on format
            if export_format.lower() == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, default=str)
            elif export_format.lower() == "csv":
                # For CSV, create multiple files, one for each data type
                base_name = os.path.splitext(output_file)[0]

                # Export CPU data
                with open(
                    f"{base_name}_cpu.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "usage_percent",
                            "core_count",
                            "model_name",
                            "load_avg_1m",
                            "load_avg_5m",
                            "load_avg_15m",
                        ]
                    )
                    writer.writerow(
                        [
                            export_data["timestamp"],
                            export_data["cpu"]["usage_percent"],
                            export_data["cpu"]["core_count"],
                            export_data["cpu"]["model_name"],
                            export_data["cpu"]["load_avg"][0],
                            export_data["cpu"]["load_avg"][1],
                            export_data["cpu"]["load_avg"][2],
                        ]
                    )

                # Export memory data
                with open(
                    f"{base_name}_memory.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "total",
                            "used",
                            "free",
                            "available",
                            "percent_used",
                            "swap_total",
                            "swap_used",
                            "swap_free",
                            "swap_percent_used",
                        ]
                    )
                    writer.writerow(
                        [
                            export_data["timestamp"],
                            export_data["memory"]["total"],
                            export_data["memory"]["used"],
                            export_data["memory"]["free"],
                            export_data["memory"]["available"],
                            export_data["memory"]["percent_used"],
                            export_data["memory"]["swap_total"],
                            export_data["memory"]["swap_used"],
                            export_data["memory"]["swap_free"],
                            export_data["memory"]["swap_percent_used"],
                        ]
                    )

                # Export disk data
                with open(
                    f"{base_name}_disks.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "device",
                            "mountpoint",
                            "total",
                            "used",
                            "free",
                            "percent",
                            "filesystem",
                        ]
                    )
                    for disk in export_data["disks"]:
                        writer.writerow(
                            [
                                export_data["timestamp"],
                                disk["device"],
                                disk["mountpoint"],
                                disk["total"],
                                disk["used"],
                                disk["free"],
                                disk["percent"],
                                disk["filesystem"],
                            ]
                        )

                # Export network data
                with open(
                    f"{base_name}_network.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "name",
                            "ipv4",
                            "bytes_sent",
                            "bytes_recv",
                            "bytes_sent_rate",
                            "bytes_recv_rate",
                            "is_up",
                        ]
                    )
                    for iface in export_data["network"]:
                        writer.writerow(
                            [
                                export_data["timestamp"],
                                iface["name"],
                                iface["ipv4"],
                                iface["bytes_sent"],
                                iface["bytes_recv"],
                                iface["bytes_sent_rate"],
                                iface["bytes_recv_rate"],
                                iface["is_up"],
                            ]
                        )

                # Export process data
                with open(
                    f"{base_name}_processes.csv", "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "pid",
                            "name",
                            "user",
                            "cpu_percent",
                            "memory_percent",
                            "memory_rss",
                            "status",
                            "threads",
                        ]
                    )
                    for proc in export_data["processes"]:
                        writer.writerow(
                            [
                                export_data["timestamp"],
                                proc["pid"],
                                proc["name"],
                                proc["user"],
                                proc["cpu_percent"],
                                proc["memory_percent"],
                                proc["memory_rss"],
                                proc["status"],
                                proc["threads"],
                            ]
                        )

                output_file = base_name + "*.csv"

            print_status(f"Data exported to {output_file}", "success")
            return True

        except Exception as e:
            print_status(f"Export failed: {str(e)}", "error")
            return False

    def _get_uptime_seconds(self) -> float:
        """Get system uptime in seconds"""
        try:
            with open(PROC_UPTIME_PATH, "r") as f:
                uptime_str = f.read().strip().split()[0]
                return float(uptime_str)
        except Exception:
            return 0.0

    def display_system_info(self) -> None:
        """Display general system information"""
        # Get hostname and uptime
        hostname = socket.gethostname()
        uptime = self._get_uptime_seconds()

        # Get OS info
        system_info = platform.system()
        release_info = platform.release()
        version_info = platform.version()

        # Calculate runtime
        runtime = time.time() - self.start_time

        # Clear screen (works on most Unix/Linux systems)
        os.system("clear")

        # Header with system information
        print_header(f"System Monitor - {hostname}")
        print(
            f"{NordColors.NORMAL}OS: {NordColors.FROST_1}{system_info} {release_info}{NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}System Uptime: {NordColors.FROST_1}{format_time_delta(uptime)}{NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}Monitor Running: {NordColors.FROST_1}{format_time_delta(runtime)}{NordColors.RESET}"
        )
        print(
            f"{NordColors.NORMAL}Refresh Rate: {NordColors.FROST_1}{self.refresh_rate:.1f}s{NordColors.RESET}"
        )

        # Display mini status for all
        status_width = 12  # Width for each status item
        cpu_usage = self.cpu_monitor.info.usage_percent
        mem_usage = self.memory_monitor.info.percent_used

        # Determine threshold colors
        cpu_color = (
            NordColors.AURORA_RED
            if cpu_usage > 90
            else NordColors.AURORA_ORANGE
            if cpu_usage > 70
            else NordColors.AURORA_YELLOW
            if cpu_usage > 40
            else NordColors.AURORA_GREEN
        )

        mem_color = (
            NordColors.AURORA_RED
            if mem_usage > 90
            else NordColors.AURORA_ORANGE
            if mem_usage > 70
            else NordColors.AURORA_YELLOW
            if mem_usage > 40
            else NordColors.AURORA_GREEN
        )

        # Print mini status line
        print(
            f"\n{NordColors.NORMAL}Status: {NordColors.BOLD}"
            f"CPU: {cpu_color}{cpu_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
            f"Memory: {mem_color}{mem_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
            f"Processes: {self.process_monitor.process_count}{NordColors.RESET}"
        )

        print(
            f"{NordColors.MUTED}Press Ctrl+C to quit. Iteration: {self.iteration}{NordColors.RESET}"
        )

    def display(self) -> None:
        """Display all monitoring information"""
        # Increment iteration counter
        self.iteration += 1

        # Display system header and info
        self.display_system_info()

        # Display individual monitor data
        self.display_cpu_info()
        self.display_memory_info()
        self.display_disk_info()
        self.display_network_info()
        self.display_process_info()

    def monitor(
        self, export_interval: Optional[int] = None, export_format: Optional[str] = None
    ) -> None:
        """
        Main monitoring loop.

        Args:
            export_interval: Optional interval in minutes for data export
            export_format: Format for data export (json or csv)
        """
        last_export_time = 0

        try:
            while not SHUTDOWN_FLAG:
                # Update all monitors
                self.update()

                # Display information
                self.display()

                # Handle export if configured
                if export_interval and export_format:
                    current_time = time.time()
                    if current_time - last_export_time >= export_interval * 60:
                        self.export_data(export_format)
                        last_export_time = current_time

                # Sleep for the refresh interval
                time.sleep(self.refresh_rate)

        except KeyboardInterrupt:
            # Already handled by signal handler
            pass
        except Exception as e:
            print_status(f"Monitoring error: {e}", "error")
        finally:
            print_status("\nSystem monitoring stopped", "info")


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """
    Check if script is run with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_status(
            "Warning: Some system information may be limited without root privileges.",
            "warning",
        )
        print_status(
            "Consider running with 'sudo' for full access to system data.", "warning"
        )
        return False
    return True


def check_system_compatibility() -> bool:
    """
    Check if the script is running on a compatible system.

    Returns:
        True if system is compatible, False otherwise
    """
    if platform.system() != "Linux":
        print_status("Error: This script is designed for Linux systems only.", "error")
        return False
    return True


def validate_export_path(path: str) -> bool:
    """
    Validate that the export path is writable.

    Args:
        path: Directory path to validate

    Returns:
        True if path is valid, False otherwise
    """
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".test_write")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception as e:
        print_status(f"Export path is not writable: {e}", "error")
        return False


#####################################
# Main Function
#####################################


def main() -> None:
    """Main entry point for system monitor"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Enhanced System Resource Monitor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Basic options
    parser.add_argument(
        "-r",
        "--refresh",
        type=float,
        default=DEFAULT_REFRESH_RATE,
        help="Refresh interval in seconds",
    )

    # Display options
    display_group = parser.add_argument_group("Display Options")
    display_group.add_argument(
        "--no-cpu", action="store_true", help="Hide CPU information"
    )
    display_group.add_argument(
        "--no-memory", action="store_true", help="Hide memory information"
    )
    display_group.add_argument(
        "--no-disk", action="store_true", help="Hide disk information"
    )
    display_group.add_argument(
        "--no-network", action="store_true", help="Hide network information"
    )
    display_group.add_argument(
        "--no-process", action="store_true", help="Hide process information"
    )
    display_group.add_argument(
        "--all-disks",
        action="store_true",
        help="Show all disks including pseudo filesystems",
    )
    display_group.add_argument(
        "--all-interfaces",
        action="store_true",
        help="Show all network interfaces including loopback",
    )
    display_group.add_argument(
        "--top-processes",
        type=int,
        default=DEFAULT_DISPLAY_ROWS,
        help="Number of top processes to display",
    )

    # Export options
    export_group = parser.add_argument_group("Export Options")
    export_group.add_argument(
        "-e",
        "--export",
        choices=["json", "csv"],
        help="Export data in the specified format",
    )
    export_group.add_argument(
        "-i",
        "--export-interval",
        type=int,
        default=0,
        help="Interval in minutes between automatic exports (0 to disable)",
    )
    export_group.add_argument(
        "-o",
        "--output",
        help="Output file for export (auto-generated if not specified)",
    )
    export_group.add_argument(
        "--export-dir", default=EXPORT_DIR, help="Directory for exported files"
    )

    args = parser.parse_args()

    # Update global export directory if specified
    if args.export_dir:
        global EXPORT_DIR
        EXPORT_DIR = os.path.expanduser(args.export_dir)

    # Check system compatibility
    if not check_system_compatibility():
        sys.exit(1)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set global shutdown flag
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = False

    # Check root privileges
    check_root_privileges()

    # Validate export directory if exporting
    if args.export and not validate_export_path(EXPORT_DIR):
        print_status(f"Will not be able to export to {EXPORT_DIR}", "warning")

    # Update global display constants
    global DEFAULT_DISPLAY_ROWS
    DEFAULT_DISPLAY_ROWS = args.top_processes

    # Create system monitor instance
    monitor = SystemMonitor(refresh_rate=args.refresh)

    # Configure display options
    monitor.display_settings = {
        "cpu": not args.no_cpu,
        "memory": not args.no_memory,
        "disks": not args.no_disk,
        "network": not args.no_network,
        "processes": not args.no_process,
    }
    monitor.display_all_disks = args.all_disks
    monitor.display_all_interfaces = args.all_interfaces

    # Set up export options
    export_interval = (
        args.export_interval if args.export and args.export_interval > 0 else None
    )

    # Start monitoring
    try:
        monitor.monitor(export_interval=export_interval, export_format=args.export)

        # Perform final export if requested
        if args.export and not export_interval:
            monitor.export_data(args.export, args.output)

    except Exception as e:
        print_status(f"Unexpected error: {str(e)}", "error")
        sys.exit(1)


# Global shutdown flag
SHUTDOWN_FLAG = False

if __name__ == "__main__":
    main()
