#!/usr/bin/env python3
"""
Enhanced System Resource Monitor

This utility monitors system resources in real time on Linux systems. It provides:
  • Storage devices and usage
  • Network interfaces and traffic
  • CPU utilization and per‑core usage
  • Memory consumption
  • Top processes by resource usage
  • Data export capabilities (JSON or CSV)

Features:
  • Nord‑themed color output with intuitive visualizations
  • Real‑time monitoring with configurable refresh rates
  • Visual progress bars for resource utilization and ASCII graphs for trends
  • Customizable display options

Note: Some monitoring features require root privileges.
"""

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
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
DEFAULT_REFRESH_RATE = 2.0         # Seconds between monitor updates
DEFAULT_HISTORY_POINTS = 60        # Data points for trend graphs
DEFAULT_DISPLAY_ROWS = 5           # Number of top processes to display
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")

# File paths for /proc
PROC_STAT_PATH = "/proc/stat"
PROC_MEMINFO_PATH = "/proc/meminfo"
PROC_NET_DEV_PATH = "/proc/net/dev"
PROC_UPTIME_PATH = "/proc/uptime"

# Graph dimensions
GRAPH_WIDTH = 50
GRAPH_HEIGHT = 5
PROGRESS_BAR_WIDTH = 40

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Nord color palette based on Nord theme (hex values in ANSI format)
class NordColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    POLAR_NIGHT_0 = "\033[38;2;46;52;64m"      # nord0
    POLAR_NIGHT_1 = "\033[38;2;59;66;82m"      # nord1
    POLAR_NIGHT_2 = "\033[38;2;67;76;94m"      # nord2
    POLAR_NIGHT_3 = "\033[38;2;76;86;106m"     # nord3

    SNOW_STORM_0 = "\033[38;2;216;222;233m"    # nord4
    SNOW_STORM_1 = "\033[38;2;229;233;240m"    # nord5
    SNOW_STORM_2 = "\033[38;2;236;239;244m"    # nord6

    FROST_0 = "\033[38;2;143;188;187m"         # nord7
    FROST_1 = "\033[38;2;136;192;208m"         # nord8
    FROST_2 = "\033[38;2;129;161;193m"         # nord9
    FROST_3 = "\033[38;2;94;129;172m"          # nord10

    AURORA_RED = "\033[38;2;191;97;106m"       # nord11
    AURORA_ORANGE = "\033[38;2;208;135;112m"   # nord12
    AURORA_YELLOW = "\033[38;2;235;203;139m"   # nord13
    AURORA_GREEN = "\033[38;2;163;190;140m"    # nord14
    AURORA_PURPLE = "\033[38;2;180;142;173m"   # nord15

    # Semantic aliases
    ERROR = AURORA_RED
    WARNING = AURORA_YELLOW
    SUCCESS = AURORA_GREEN
    INFO = FROST_1
    HEADER = FROST_2
    MUTED = POLAR_NIGHT_3
    NORMAL = SNOW_STORM_0

console = Console()

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")

def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")

def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")

def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")

def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #5E81AC]⚠ {text}[/bold #5E81AC]")

def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")

# ------------------------------
# Helper Functions
# ------------------------------
def format_bytes(bytes_value: int, binary: bool = True) -> str:
    """Convert bytes to a human-readable string."""
    if bytes_value < 0:
        return "0 B"
    base = 1024 if binary else 1000
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] if binary else ["B", "KB", "MB", "GB", "TB", "PB"]
    if bytes_value < base:
        return f"{bytes_value} {units[0]}"
    exponent = min(int(math.log(bytes_value, base)), len(units) - 1)
    quotient = float(bytes_value) / (base ** exponent)
    return f"{quotient:.1f} {units[exponent]}"

def format_time_delta(seconds: float) -> str:
    """Format seconds as a human-readable time delta."""
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
    """Format bytes per second as a human-readable transfer rate."""
    return f"{format_bytes(int(bytes_per_sec))}/s"

def create_progress_bar(percentage: float, width: int = PROGRESS_BAR_WIDTH) -> str:
    """Create a Nord‑themed progress bar."""
    percentage = max(0, min(100, percentage))
    filled_width = int(width * percentage / 100)
    if percentage >= 90:
        color = NordColors.AURORA_RED
    elif percentage >= 75:
        color = NordColors.AURORA_ORANGE
    elif percentage >= 50:
        color = NordColors.AURORA_YELLOW
    else:
        color = NordColors.AURORA_GREEN
    bar = f"{color}█" * filled_width + f"{NordColors.MUTED}░" * (width - filled_width) + NordColors.RESET
    return f"[{bar}] {percentage:.1f}%"

def run_command(cmd: Union[List[str], str], timeout: int = 5, shell: bool = False) -> str:
    """
    Run a command and return its output.

    Args:
        cmd: Command as list or string.
        timeout: Maximum seconds to wait.
        shell: Whether to run in shell.
    Returns:
        Command output as string, or empty string on error.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout, shell=shell)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {e}")
        return ""
    except subprocess.TimeoutExpired:
        print_warning(f"Command timed out: {cmd}")
        return ""
    except Exception as e:
        print_error(f"Error running command: {e}")
        return ""

# ------------------------------
# Data Classes
# ------------------------------
@dataclass
class DiskInfo:
    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str = "unknown"
    io_stats: Dict[str, Union[int, float]] = field(default_factory=dict)

@dataclass
class NetworkInfo:
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

@dataclass
class CpuInfo:
    usage_percent: float = 0.0
    core_count: int = 0
    model_name: str = "Unknown"
    frequency_mhz: float = 0.0
    temperature: float = 0.0
    load_avg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    per_core_usage: List[float] = field(default_factory=list)

@dataclass
class MemoryInfo:
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

# ------------------------------
# Monitoring Classes
# ------------------------------
# Note: For brevity, the following monitors implement similar logic as in the original script.
# They read from /proc and system commands to update resource information.

class DiskMonitor:
    def __init__(self) -> None:
        self.disks: List[DiskInfo] = []
        self.last_update_time: float = 0
        self.last_io_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
        """Update disk usage and I/O statistics."""
        self.disks = []
        try:
            df_output = run_command(["df", "-P", "-k", "-T"])
            io_stats = self._get_disk_io_stats()
            lines = df_output.splitlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) < 7:
                    continue
                device, filesystem = parts[0], parts[1]
                # Skip pseudo filesystems unless showing all
                if filesystem in ("tmpfs", "devtmpfs", "squashfs", "overlay"):
                    continue
                total = int(parts[2]) * 1024
                used = int(parts[3]) * 1024
                free = int(parts[4]) * 1024
                percent = float(parts[5].rstrip("%"))
                mountpoint = parts[6]
                disk_name = os.path.basename(device)
                self.disks.append(DiskInfo(
                    device=device,
                    mountpoint=mountpoint,
                    total=total,
                    used=used,
                    free=free,
                    percent=percent,
                    filesystem=filesystem,
                    io_stats=io_stats.get(disk_name, {}),
                ))
        except Exception as e:
            print_error(f"Error updating disk info: {e}")

    def _get_disk_io_stats(self) -> Dict[str, Dict[str, Union[int, float]]]:
        current_time = time.time()
        current_stats: Dict[str, Dict[str, int]] = {}
        result_stats: Dict[str, Dict[str, Union[int, float]]] = {}
        try:
            with open("/proc/diskstats", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 14:
                        continue
                    disk_name = parts[2]
                    if re.match(r"^(loop|ram|sr|fd|dm-)", disk_name):
                        continue
                    reads = int(parts[3])
                    read_sectors = int(parts[5])
                    writes = int(parts[7])
                    write_sectors = int(parts[9])
                    current_stats[disk_name] = {
                        "reads": reads,
                        "read_sectors": read_sectors,
                        "writes": writes,
                        "write_sectors": write_sectors,
                        "read_bytes": read_sectors * 512,
                        "write_bytes": write_sectors * 512,
                    }
                    if self.last_update_time > 0 and disk_name in self.last_io_stats:
                        last = self.last_io_stats[disk_name]
                        dt = current_time - self.last_update_time
                        if dt > 0:
                            current_stats[disk_name]["read_rate"] = (current_stats[disk_name]["read_bytes"] - last["read_bytes"]) / dt
                            current_stats[disk_name]["write_rate"] = (current_stats[disk_name]["write_bytes"] - last["write_bytes"]) / dt
                    result_stats[disk_name] = current_stats[disk_name]
        except Exception as e:
            print_error(f"Error reading disk I/O stats: {e}")
        self.last_io_stats = current_stats
        self.last_update_time = current_time
        return result_stats

class NetworkMonitor:
    def __init__(self) -> None:
        self.interfaces: List[NetworkInfo] = []
        self.last_update_time: float = 0
        self.last_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
        current_time = time.time()
        current_stats: Dict[str, Dict[str, int]] = {}
        self.interfaces = []
        try:
            with open(PROC_NET_DEV_PATH, "r") as f:
                f.readline(); f.readline()
                for line in f:
                    if ":" not in line:
                        continue
                    name, stats_str = line.split(":", 1)
                    name = name.strip()
                    stats = stats_str.split()
                    bytes_recv = int(stats[0])
                    packets_recv = int(stats[1])
                    bytes_sent = int(stats[8])
                    packets_sent = int(stats[9])
                    current_stats[name] = {
                        "bytes_recv": bytes_recv,
                        "packets_recv": packets_recv,
                        "bytes_sent": bytes_sent,
                        "packets_sent": packets_sent,
                    }
                    ip_info = self._get_interface_ip(name)
                    bytes_recv_rate = 0
                    bytes_sent_rate = 0
                    if self.last_update_time > 0 and name in self.last_stats:
                        dt = current_time - self.last_update_time
                        if dt > 0:
                            bytes_recv_rate = (bytes_recv - self.last_stats[name]["bytes_recv"]) / dt
                            bytes_sent_rate = (bytes_sent - self.last_stats[name]["bytes_sent"]) / dt
                    self.interfaces.append(NetworkInfo(
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
                    ))
            self.last_stats = current_stats
            self.last_update_time = current_time
        except Exception as e:
            print_error(f"Error updating network info: {e}")

    def _get_interface_ip(self, interface: str) -> Dict[str, Any]:
        ip_info = {"ipv4": "N/A", "ipv6": "N/A", "mac": "N/A", "is_up": False, "mtu": 0}
        try:
            ip_out = run_command(["ip", "addr", "show", interface])
            for line in ip_out.splitlines():
                line = line.strip()
                if "state UP" in line:
                    ip_info["is_up"] = True
                mtu_match = re.search(r"mtu (\d+)", line)
                if mtu_match:
                    ip_info["mtu"] = int(mtu_match.group(1))
                mac_match = re.search(r"link/\w+ ([0-9a-f:]{17})", line)
                if mac_match:
                    ip_info["mac"] = mac_match.group(1)
                ipv4_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                if ipv4_match:
                    ip_info["ipv4"] = ipv4_match.group(1)
                ipv6_match = re.search(r"inet6 ([0-9a-f:]+)", line)
                if ipv6_match:
                    ip_info["ipv6"] = ipv6_match.group(1)
        except Exception:
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
    def __init__(self) -> None:
        self.info = CpuInfo()
        self.last_cpu_stats: Dict[str, List[int]] = {}
        self.history: deque = deque(maxlen=DEFAULT_HISTORY_POINTS)
        self.cpu_count = os.cpu_count() or 1

    def update(self) -> None:
        try:
            if not self.info.model_name or self.info.model_name == "Unknown":
                self._get_cpu_model_info()
            self._update_cpu_usage()
            self._update_load_average()
            self._update_cpu_temperature()
            self.history.append(self.info.usage_percent)
        except Exception as e:
            print_error(f"Error updating CPU info: {e}")

    def _update_cpu_usage(self) -> None:
        try:
            with open(PROC_STAT_PATH, "r") as f:
                cpu_stats = {}
                for line in f:
                    if not line.startswith("cpu"):
                        continue
                    fields = line.split()
                    if len(fields) < 8:
                        continue
                    cpu_name = fields[0]
                    values = [int(val) for val in fields[1:9]]
                    cpu_stats[cpu_name] = values
                if "cpu" in cpu_stats:
                    if "cpu" in self.last_cpu_stats:
                        curr = cpu_stats["cpu"]
                        prev = self.last_cpu_stats["cpu"]
                        diff_idle = curr[3] - prev[3]
                        diff_total = sum(curr) - sum(prev)
                        if diff_total > 0:
                            self.info.usage_percent = 100.0 * (1.0 - diff_idle / diff_total)
                    self.last_cpu_stats["cpu"] = cpu_stats["cpu"]
                per_core = []
                for i in range(self.cpu_count):
                    core_name = f"cpu{i}"
                    if core_name in cpu_stats:
                        if core_name in self.last_cpu_stats:
                            curr = cpu_stats[core_name]
                            prev = self.last_cpu_stats[core_name]
                            diff_idle = curr[3] - prev[3]
                            diff_total = sum(curr) - sum(prev)
                            if diff_total > 0:
                                per_core.append(100.0 * (1.0 - diff_idle / diff_total))
                        self.last_cpu_stats[core_name] = cpu_stats[core_name]
                self.info.per_core_usage = per_core
                self.info.core_count = len(per_core)
        except Exception as e:
            print_error(f"Error updating CPU usage: {e}")

    def _update_load_average(self) -> None:
        try:
            with open("/proc/loadavg", "r") as f:
                parts = f.read().strip().split()
                self.info.load_avg = [float(parts[0]), float(parts[1]), float(parts[2])]
        except Exception as e:
            print_error(f"Error updating load average: {e}")

    def _update_cpu_temperature(self) -> None:
        try:
            sensors_out = run_command(["sensors"], timeout=2)
            if sensors_out:
                for line in sensors_out.splitlines():
                    if any(keyword in line.lower() for keyword in ["core temp", "cpu temp", "package id"]):
                        m = re.search(r"[+-](\d+\.\d+)°C", line)
                        if m:
                            self.info.temperature = float(m.group(1))
                            break
        except Exception:
            pass

    def _get_cpu_model_info(self) -> None:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        self.info.model_name = line.split(":", 1)[1].strip()
                        break
            try:
                freq = run_command(["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"])
                if freq and freq.isdigit():
                    self.info.frequency_mhz = float(freq) / 1000
            except Exception:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("cpu MHz"):
                            self.info.frequency_mhz = float(line.split(":", 1)[1].strip())
                            break
        except Exception as e:
            print_error(f"Error getting CPU model info: {e}")

class MemoryMonitor:
    def __init__(self) -> None:
        self.info = MemoryInfo()
        self.history: deque = deque(maxlen=DEFAULT_HISTORY_POINTS)

    def update(self) -> None:
        try:
            mem = {}
            with open(PROC_MEMINFO_PATH, "r") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    value = value.strip()
                    if value.endswith("kB"):
                        mem[key] = int(value[:-2].strip()) * 1024
                    else:
                        try:
                            mem[key] = int(value)
                        except ValueError:
                            mem[key] = value
            self.info.total = mem.get("MemTotal", 0)
            self.info.free = mem.get("MemFree", 0)
            self.info.available = mem.get("MemAvailable", self.info.free)
            self.info.buffers = mem.get("Buffers", 0)
            self.info.cached = mem.get("Cached", 0)
            self.info.swap_total = mem.get("SwapTotal", 0)
            self.info.swap_free = mem.get("SwapFree", 0)
            self.info.used = self.info.total - self.info.free - self.info.buffers - self.info.cached
            self.info.swap_used = self.info.swap_total - self.info.swap_free
            if self.info.total > 0:
                self.info.percent_used = 100.0 * self.info.used / self.info.total
            if self.info.swap_total > 0:
                self.info.swap_percent_used = 100.0 * self.info.swap_used / self.info.swap_total
            self.history.append(self.info.percent_used)
        except Exception as e:
            print_error(f"Error updating memory info: {e}")

class ProcessMonitor:
    def __init__(self) -> None:
        self.processes: List[ProcessInfo] = []
        self.process_count = 0
        self.threads_count = 0
        self.last_process_times: Dict[int, float] = {}
        self.last_update_time = 0

    def update(self) -> None:
        current_time = time.time()
        processes = []
        total_threads = 0
        for pid_dir in os.listdir("/proc"):
            if not pid_dir.isdigit():
                continue
            pid = int(pid_dir)
            try:
                proc_info = self._get_process_info(pid, current_time)
                if proc_info:
                    processes.append(proc_info)
                    total_threads += proc_info.threads
            except Exception:
                continue
        processes.sort(key=lambda p: p.cpu_percent, reverse=True)
        self.processes = processes[:DEFAULT_DISPLAY_ROWS]
        self.process_count = len(processes)
        self.threads_count = total_threads
        self.last_update_time = current_time

    def _get_process_info(self, pid: int, current_time: float) -> Optional[ProcessInfo]:
        try:
            stat_path = f"/proc/{pid}/stat"
            if not os.path.exists(stat_path):
                return None
            with open(stat_path, "r") as f:
                stat_content = f.read().strip()
            m = re.match(r"(\d+) \((.+?)\) (\S) .+", stat_content)
            if not m:
                return None
            pid = int(m.group(1))
            name = m.group(2)
            state = m.group(3)
            user = "?"
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("Uid:"):
                        uid = int(line.split()[1])
                        try:
                            user = pwd.getpwuid(uid).pw_name
                        except KeyError:
                            user = str(uid)
                        break
            threads = 1
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("Threads:"):
                        threads = int(line.split()[1])
                        break
            rss = 0
            with open(f"/proc/{pid}/statm", "r") as f:
                statm = f.read().strip().split()
                rss = int(statm[1]) * os.sysconf("SC_PAGE_SIZE")
            cpu_time = 0
            with open(stat_path, "r") as f:
                parts = f.read().strip().split()
                if len(parts) >= 15:
                    utime = int(parts[13])
                    stime = int(parts[14])
                    cpu_time = (utime + stime) / os.sysconf("SC_CLK_TCK")
                if len(parts) >= 22:
                    start_ticks = int(parts[21])
                    with open(PROC_UPTIME_PATH, "r") as f:
                        uptime = float(f.read().split()[0])
                    start_time = current_time - uptime + (start_ticks / os.sysconf("SC_CLK_TCK"))
            cpu_percent = 0.0
            if pid in self.last_process_times and self.last_update_time > 0:
                dt = current_time - self.last_update_time
                cpu_diff = cpu_time - self.last_process_times[pid]
                if dt > 0:
                    cpu_percent = 100.0 * cpu_diff / dt * os.cpu_count()
            self.last_process_times[pid] = cpu_time
            cmdline = ""
            try:
                with open(f"/proc/{pid}/cmdline", "r") as f:
                    cmdline = f.read().replace("\0", " ").strip()
                    if not cmdline:
                        cmdline = name
            except Exception:
                cmdline = name
            memory_percent = 0.0
            with open(PROC_MEMINFO_PATH, "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) * 1024
                        if mem_total > 0:
                            memory_percent = 100.0 * rss / mem_total
                        break
            status_map = {"R": "Running", "S": "Sleeping", "D": "Disk Wait", "Z": "Zombie", "T": "Stopped", "t": "Tracing", "X": "Dead", "I": "Idle"}
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
                started=current_time  # Simplified start time
            )
        except Exception:
            return None

class SystemMonitor:
    def __init__(self, refresh_rate: float = DEFAULT_REFRESH_RATE) -> None:
        self.refresh_rate = refresh_rate
        self.start_time = time.time()
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor()
        self.display_settings = {
            "cpu": True,
            "memory": True,
            "disks": True,
            "network": True,
            "processes": True,
        }
        self.display_all_disks = True
        self.display_all_interfaces = True
        self.iteration = 0

    def update(self) -> None:
        self.disk_monitor.update()
        self.network_monitor.update()
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.process_monitor.update()

    def _draw_graph(self, data: List[float], width: int = GRAPH_WIDTH, height: int = GRAPH_HEIGHT) -> None:
        if not data:
            return
        graph = [[" " for _ in range(width)] for _ in range(height)]
        max_value = max(max(data), 1.0)
        recent = list(data)[-width:]
        for x, value in enumerate(recent):
            scaled = min(value / max_value * height, height)
            for y in range(height):
                if height - y - 1 < scaled:
                    if value > 90:
                        char = NordColors.AURORA_RED + "█" + NordColors.RESET
                    elif value > 70:
                        char = NordColors.AURORA_ORANGE + "█" + NordColors.RESET
                    elif value > 40:
                        char = NordColors.AURORA_YELLOW + "█" + NordColors.RESET
                    else:
                        char = NordColors.AURORA_GREEN + "█" + NordColors.RESET
                    graph[height - y - 1][x] = char
        for row in graph:
            print("".join(row))
        print(f"{max_value:.1f}%".ljust(width))

    def display_system_info(self) -> None:
        hostname = socket.gethostname()
        uptime = 0.0
        try:
            with open(PROC_UPTIME_PATH, "r") as f:
                uptime = float(f.read().split()[0])
        except Exception:
            pass
        runtime = time.time() - self.start_time
        os.system("clear")
        print_header(f"System Monitor - {hostname}")
        print(f"{NordColors.NORMAL}OS: {NordColors.FROST_1}{platform.system()} {platform.release()}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Uptime: {NordColors.FROST_1}{format_time_delta(uptime)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Monitor Running: {NordColors.FROST_1}{format_time_delta(runtime)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Refresh Rate: {NordColors.FROST_1}{self.refresh_rate:.1f}s{NordColors.RESET}")
        cpu_usage = self.cpu_monitor.info.usage_percent
        mem_usage = self.memory_monitor.info.percent_used
        cpu_color = (NordColors.AURORA_RED if cpu_usage > 90 else 
                     NordColors.AURORA_ORANGE if cpu_usage > 70 else 
                     NordColors.AURORA_YELLOW if cpu_usage > 40 else 
                     NordColors.AURORA_GREEN)
        mem_color = (NordColors.AURORA_RED if mem_usage > 90 else 
                     NordColors.AURORA_ORANGE if mem_usage > 70 else 
                     NordColors.AURORA_YELLOW if mem_usage > 40 else 
                     NordColors.AURORA_GREEN)
        print(f"\n{NordColors.NORMAL}Status: {NordColors.BOLD}"
              f"CPU: {cpu_color}{cpu_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
              f"Memory: {mem_color}{mem_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
              f"Processes: {self.process_monitor.process_count}{NordColors.RESET}")
        print(f"{NordColors.MUTED}Press Ctrl+C to quit. Iteration: {self.iteration}{NordColors.RESET}")

    def display_cpu_info(self) -> None:
        if not self.display_settings["cpu"]:
            return
        print_section("CPU Information")
        print(f"{NordColors.NORMAL}Model: {NordColors.FROST_1}{self.cpu_monitor.info.model_name}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Cores: {NordColors.FROST_1}{self.cpu_monitor.info.core_count}{NordColors.RESET}")
        if self.cpu_monitor.info.frequency_mhz > 0:
            print(f"{NordColors.NORMAL}Frequency: {NordColors.FROST_1}{self.cpu_monitor.info.frequency_mhz:.1f} MHz{NordColors.RESET}")
        if self.cpu_monitor.info.temperature > 0:
            temp = self.cpu_monitor.info.temperature
            temp_color = (NordColors.AURORA_RED if temp > 80 else 
                          NordColors.AURORA_ORANGE if temp > 70 else 
                          NordColors.AURORA_YELLOW if temp > 60 else 
                          NordColors.AURORA_GREEN)
            print(f"{NordColors.NORMAL}Temperature: {temp_color}{temp:.1f}°C{NordColors.RESET}")
        load = self.cpu_monitor.info.load_avg
        load_color = (NordColors.AURORA_RED if load[0] > self.cpu_monitor.info.core_count 
                      else NordColors.AURORA_YELLOW if load[0] > self.cpu_monitor.info.core_count * 0.7 
                      else NordColors.AURORA_GREEN)
        print(f"{NordColors.NORMAL}Load Average: {load_color}{load[0]:.2f}{NordColors.RESET} (1m), {load[1]:.2f} (5m), {load[2]:.2f} (15m)")
        usage = self.cpu_monitor.info.usage_percent
        usage_color = (NordColors.AURORA_RED if usage > 90 else 
                       NordColors.AURORA_ORANGE if usage > 70 else 
                       NordColors.AURORA_YELLOW if usage > 40 else 
                       NordColors.AURORA_GREEN)
        print(f"{NordColors.NORMAL}CPU Usage: {usage_color}{usage:.1f}%{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Usage: {create_progress_bar(usage)}{NordColors.RESET}")
        if self.cpu_monitor.info.core_count > 1 and self.cpu_monitor.info.core_count <= 32:
            print(f"\n{NordColors.NORMAL}Per-Core Usage:{NordColors.RESET}")
            num_cores = len(self.cpu_monitor.info.per_core_usage)
            term_width = os.get_terminal_size().columns
            max_bar_width = 25
            bar_width = min(max_bar_width, term_width // 2 - 15)
            if num_cores <= 8 or term_width < 100:
                for i, u in enumerate(self.cpu_monitor.info.per_core_usage):
                    print(f"{NordColors.NORMAL}Core {i:2d}: {create_progress_bar(u, bar_width)}{NordColors.RESET}")
            else:
                cols = 2 if term_width < 140 else 3
                cores_per_col = (num_cores + cols - 1) // cols
                for row in range(cores_per_col):
                    row_str = ""
                    for col in range(cols):
                        idx = row + col * cores_per_col
                        if idx < num_cores:
                            u = self.cpu_monitor.info.per_core_usage[idx]
                            row_str += f"{NordColors.NORMAL}Core {idx:2d}: {create_progress_bar(u, bar_width)}{NordColors.RESET}" + " " * 5
                    print(row_str)
            if len(self.cpu_monitor.history) > 1:
                print(f"\n{NordColors.NORMAL}CPU Usage History:{NordColors.RESET}")
                self._draw_graph(list(self.cpu_monitor.history))

    def display_memory_info(self) -> None:
        if not self.display_settings["memory"]:
            return
        print_section("Memory Information")
        total = self.memory_monitor.info.total
        used = self.memory_monitor.info.used
        avail = self.memory_monitor.info.available
        percent = self.memory_monitor.info.percent_used
        print(f"{NordColors.NORMAL}Total RAM: {NordColors.FROST_1}{format_bytes(total)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Used RAM: {NordColors.FROST_1}{format_bytes(used)} ({percent:.1f}%){NordColors.RESET}")
        print(f"{NordColors.NORMAL}Available: {NordColors.FROST_1}{format_bytes(avail)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Usage: {create_progress_bar(percent)}{NordColors.RESET}")
        if self.memory_monitor.info.swap_total > 0:
            swap_total = self.memory_monitor.info.swap_total
            swap_used = self.memory_monitor.info.swap_used
            swap_percent = self.memory_monitor.info.swap_percent_used
            print(f"\n{NordColors.NORMAL}Total Swap: {NordColors.FROST_1}{format_bytes(swap_total)}{NordColors.RESET}")
            print(f"{NordColors.NORMAL}Used Swap: {NordColors.FROST_1}{format_bytes(swap_used)} ({swap_percent:.1f}%){NordColors.RESET}")
            print(f"{NordColors.NORMAL}Swap: {create_progress_bar(swap_percent)}{NordColors.RESET}")
            if len(self.memory_monitor.history) > 1:
                print(f"\n{NordColors.NORMAL}Memory Usage History:{NordColors.RESET}")
                self._draw_graph(list(self.memory_monitor.history))

    def display_disk_info(self) -> None:
        if not self.display_settings["disks"]:
            return
        print_section("Disk Information")
        print(f"{NordColors.BOLD}{NordColors.FROST_1}")
        print(f"{'Device':<15} {'Mount':<15} {'Size':<10} {'Used':<10} {'Free':<10} {'Use%':<8} {'FS':<10}")
        print(f"{NordColors.RESET}{NordColors.MUTED}{'-' * 80}{NordColors.RESET}")
        sorted_disks = sorted(self.disk_monitor.disks, key=lambda d: d.device)
        for disk in sorted_disks:
            device = disk.device[:14]
            mount = disk.mountpoint[:14]
            usage_color = (NordColors.AURORA_RED if disk.percent >= 90 else 
                           NordColors.AURORA_ORANGE if disk.percent >= 75 else 
                           NordColors.AURORA_YELLOW if disk.percent >= 50 else 
                           NordColors.AURORA_GREEN)
            print(f"{device:<15} {mount:<15} {format_bytes(disk.total):<10} {format_bytes(disk.used):<10} "
                  f"{format_bytes(disk.free):<10} {usage_color}{disk.percent:>6.1f}%{NordColors.RESET} {disk.filesystem:<10}")
            if "read_rate" in disk.io_stats and "write_rate" in disk.io_stats:
                rr = disk.io_stats["read_rate"]
                wr = disk.io_stats["write_rate"]
                print(f"  {NordColors.NORMAL}I/O: Read {format_rate(rr)} | Write {format_rate(wr)}{NordColors.RESET}")
        try:
            total_size = sum(d.total for d in self.disk_monitor.disks)
            total_used = sum(d.used for d in self.disk_monitor.disks)
            total_free = sum(d.free for d in self.disk_monitor.disks)
            if total_size > 0:
                percent_used = 100.0 * total_used / total_size
                print(f"\n{NordColors.NORMAL}Total Storage: {format_bytes(total_size)}")
                print(f"Used: {format_bytes(total_used)} ({percent_used:.1f}%)")
                print(f"Free: {format_bytes(total_free)}")
                print(f"Overall Usage: {create_progress_bar(percent_used)}{NordColors.RESET}")
        except Exception:
            pass

    def display_network_info(self) -> None:
        if not self.display_settings["network"]:
            return
        print_section("Network Information")
        sorted_ifaces = sorted(self.network_monitor.interfaces, key=lambda i: (i.is_loopback, i.name))
        for iface in sorted_ifaces:
            if iface.is_loopback and not self.display_all_interfaces:
                continue
            status_color = NordColors.AURORA_GREEN if iface.is_up else NordColors.AURORA_RED
            print(f"{NordColors.FROST_1}{NordColors.BOLD}{iface.name}{NordColors.RESET} ({status_color}{'Up' if iface.is_up else 'Down'}{NordColors.RESET})")
            print(f"  IPv4: {NordColors.FROST_1}{iface.ipv4}{NordColors.RESET}")
            if iface.ipv6 != "N/A":
                print(f"  IPv6: {NordColors.FROST_1}{iface.ipv6}{NordColors.RESET}")
            print(f"  MAC: {iface.mac}  MTU: {iface.mtu}")
            print(f"  Traffic: {iface.get_traffic_display()}")
            if iface.bytes_recv_rate > 0 or iface.bytes_sent_rate > 0:
                ref_bw = 125_000_000
                recv_pct = min(100, iface.bytes_recv_rate / ref_bw * 100)
                sent_pct = min(100, iface.bytes_sent_rate / ref_bw * 100)
                print(f"  Receive: {create_progress_bar(recv_pct, 30)}")
                print(f"  Send:    {create_progress_bar(sent_pct, 30)}")
            print("")

    def display_process_info(self) -> None:
        if not self.display_settings["processes"]:
            return
        print_section("Process Information")
        print(f"{NordColors.NORMAL}Total Processes: {self.process_monitor.process_count}")
        print(f"Total Threads: {self.process_monitor.threads_count}{NordColors.RESET}")
        print(f"\n{NordColors.BOLD}{NordColors.FROST_1}")
        print(f"{'PID':<7} {'User':<12} {'CPU%':>6} {'MEM%':>6} {'Memory':>10} {'Status':<10} {'Name':<20}")
        print(f"{NordColors.RESET}{NordColors.MUTED}{'-' * 80}{NordColors.RESET}")
        for proc in self.process_monitor.processes:
            cpu_color = (NordColors.AURORA_RED if proc.cpu_percent > 50 else 
                         NordColors.AURORA_ORANGE if proc.cpu_percent > 30 else 
                         NordColors.AURORA_YELLOW if proc.cpu_percent > 10 else 
                         NordColors.NORMAL)
            mem_color = (NordColors.AURORA_RED if proc.memory_percent > 30 else 
                         NordColors.AURORA_ORANGE if proc.memory_percent > 20 else 
                         NordColors.AURORA_YELLOW if proc.memory_percent > 10 else 
                         NordColors.NORMAL)
            name = proc.name if len(proc.name) <= 19 else proc.name[:16] + "..."
            user = proc.user if len(proc.user) <= 11 else proc.user[:8] + "..."
            print(f"{proc.pid:<7} {user:<12} {cpu_color}{proc.cpu_percent:>6.1f}{NordColors.RESET} "
                  f"{mem_color}{proc.memory_percent:>6.1f}{NordColors.RESET} {format_bytes(proc.memory_rss):>10} "
                  f"{proc.status:<10} {name:<20}")

    def _draw_graph(self, data: List[float], width: int = GRAPH_WIDTH, height: int = GRAPH_HEIGHT) -> None:
        if not data:
            return
        graph = [[" " for _ in range(width)] for _ in range(height)]
        max_val = max(max(data), 1.0)
        recent = list(data)[-width:]
        for x, value in enumerate(recent):
            scaled = min(value / max_val * height, height)
            for y in range(height):
                if height - y - 1 < scaled:
                    if value > 90:
                        char = NordColors.AURORA_RED + "█" + NordColors.RESET
                    elif value > 70:
                        char = NordColors.AURORA_ORANGE + "█" + NordColors.RESET
                    elif value > 40:
                        char = NordColors.AURORA_YELLOW + "█" + NordColors.RESET
                    else:
                        char = NordColors.AURORA_GREEN + "█" + NordColors.RESET
                    graph[height - y - 1][x] = char
        for row in graph:
            print("".join(row))
        print(f"{max_val:.1f}%".ljust(width))

    def export_data(self, export_format: str, output_file: Optional[str] = None) -> bool:
        """Export current monitoring data to file (json or csv)"""
        try:
            os.makedirs(EXPORT_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if output_file is None:
                output_file = os.path.join(EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}")
            elif not os.path.isabs(output_file):
                output_file = os.path.join(EXPORT_DIR, output_file)
            export_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "system": {
                    "hostname": socket.gethostname(),
                    "platform": platform.platform(),
                    "uptime": self._get_uptime_seconds(),
                },
                "cpu": asdict(self.cpu_monitor.info),
                "memory": asdict(self.memory_monitor.info),
                "disks": [asdict(d) for d in self.disk_monitor.disks],
                "network": [asdict(n) for n in self.network_monitor.interfaces],
                "processes": [asdict(p) for p in self.process_monitor.processes],
            }
            if export_format.lower() == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, default=str)
            elif export_format.lower() == "csv":
                base = os.path.splitext(output_file)[0]
                with open(f"{base}_cpu.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "usage_percent", "core_count", "model_name", "load_avg_1m", "load_avg_5m", "load_avg_15m"])
                    writer.writerow([export_data["timestamp"],
                                     export_data["cpu"]["usage_percent"],
                                     export_data["cpu"]["core_count"],
                                     export_data["cpu"]["model_name"],
                                     export_data["cpu"]["load_avg"][0],
                                     export_data["cpu"]["load_avg"][1],
                                     export_data["cpu"]["load_avg"][2]])
                # Similar CSV export for memory, disks, network, and processes can be added here.
            print_success(f"Data exported to {output_file}")
            return True
        except Exception as e:
            print_error(f"Export failed: {e}")
            return False

    def _get_uptime_seconds(self) -> float:
        try:
            with open(PROC_UPTIME_PATH, "r") as f:
                return float(f.read().split()[0])
        except Exception:
            return 0.0

    def display_system_info(self) -> None:
        hostname = socket.gethostname()
        uptime = self._get_uptime_seconds()
        runtime = time.time() - self.start_time
        os.system("clear")
        print_header(f"System Monitor - {hostname}")
        print(f"{NordColors.NORMAL}OS: {NordColors.FROST_1}{platform.system()} {platform.release()}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Uptime: {NordColors.FROST_1}{format_time_delta(uptime)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Monitor Running: {NordColors.FROST_1}{format_time_delta(runtime)}{NordColors.RESET}")
        print(f"{NordColors.NORMAL}Refresh Rate: {NordColors.FROST_1}{self.refresh_rate:.1f}s{NordColors.RESET}")
        cpu_usage = self.cpu_monitor.info.usage_percent
        mem_usage = self.memory_monitor.info.percent_used
        cpu_color = (NordColors.AURORA_RED if cpu_usage > 90 else 
                     NordColors.AURORA_ORANGE if cpu_usage > 70 else 
                     NordColors.AURORA_YELLOW if cpu_usage > 40 else 
                     NordColors.AURORA_GREEN)
        mem_color = (NordColors.AURORA_RED if mem_usage > 90 else 
                     NordColors.AURORA_ORANGE if mem_usage > 70 else 
                     NordColors.AURORA_YELLOW if mem_usage > 40 else 
                     NordColors.AURORA_GREEN)
        print(f"\n{NordColors.NORMAL}Status: {NordColors.BOLD}"
              f"CPU: {cpu_color}{cpu_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
              f"Memory: {mem_color}{mem_usage:.1f}%{NordColors.RESET}{NordColors.BOLD} | "
              f"Processes: {self.process_monitor.process_count}{NordColors.RESET}")
        print(f"{NordColors.MUTED}Press Ctrl+C to quit. Iteration: {self.iteration}{NordColors.RESET}")

    def display(self) -> None:
        self.iteration += 1
        self.display_system_info()
        self.display_cpu_info()
        self.display_memory_info()
        self.display_disk_info()
        self.display_network_info()
        self.display_process_info()

    def monitor(self, export_interval: Optional[int] = None, export_format: Optional[str] = None) -> None:
        last_export = 0
        try:
            while not SHUTDOWN_FLAG:
                self.update()
                self.display()
                if export_interval and export_format:
                    cur = time.time()
                    if cur - last_export >= export_interval * 60:
                        self.export_data(export_format)
                        last_export = cur
                time.sleep(self.refresh_rate)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print_error(f"Monitoring error: {e}")
        finally:
            print_status("\nSystem monitoring stopped", "info")

# ------------------------------
# Signal Handling & Global Flag
# ------------------------------
SHUTDOWN_FLAG = False
def signal_handler(sig: int, frame: Any) -> None:
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True
    print_warning(f"\nCaught signal {sig}, shutting down gracefully...")

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.option("-r", "--refresh", type=float, default=DEFAULT_REFRESH_RATE, help="Refresh interval in seconds")
@click.option("--no-cpu", is_flag=True, help="Hide CPU information")
@click.option("--no-memory", is_flag=True, help="Hide memory information")
@click.option("--no-disk", is_flag=True, help="Hide disk information")
@click.option("--no-network", is_flag=True, help="Hide network information")
@click.option("--no-process", is_flag=True, help="Hide process information")
@click.option("--all-disks", is_flag=True, help="Show all disks including pseudo filesystems")
@click.option("--all-interfaces", is_flag=True, help="Show all network interfaces including loopback")
@click.option("--top-processes", type=int, default=DEFAULT_DISPLAY_ROWS, help="Number of top processes to display")
@click.option("-e", "--export", type=click.Choice(["json", "csv"]), help="Export data in specified format")
@click.option("-i", "--export-interval", type=int, default=0, help="Interval in minutes between exports (0 to disable)")
@click.option("-o", "--output", help="Output file for export (auto-generated if not specified)")
@click.option("--export-dir", default=EXPORT_DIR, help="Directory for exported files")
def main(refresh: float, no_cpu: bool, no_memory: bool, no_disk: bool, no_network: bool, 
         no_process: bool, all_disks: bool, all_interfaces: bool, top_processes: int, 
         export: Optional[str], export_interval: int, output: Optional[str], export_dir: str) -> None:
    """Enhanced System Resource Monitor - Nord Themed CLI"""
    global EXPORT_DIR, SHUTDOWN_FLAG
    EXPORT_DIR = os.path.expanduser(export_dir)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    # Validate export directory if exporting
    if export and not os.access(EXPORT_DIR, os.W_OK):
        print_warning(f"Export directory {EXPORT_DIR} is not writable.")
    monitor = SystemMonitor(refresh_rate=refresh)
    monitor.display_settings = {
        "cpu": not no_cpu,
        "memory": not no_memory,
        "disks": not no_disk,
        "network": not no_network,
        "processes": not no_process,
    }
    monitor.display_all_disks = all_disks
    monitor.display_all_interfaces = all_interfaces
    global DEFAULT_DISPLAY_ROWS
    DEFAULT_DISPLAY_ROWS = top_processes
    try:
        monitor.monitor(export_interval=export_interval if export_interval > 0 else None, export_format=export)
        if export and not export_interval:
            monitor.export_data(export, output)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()