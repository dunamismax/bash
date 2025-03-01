#!/usr/bin/env python3
"""
Unified System Resource Monitor

This utility provides a real‑time dashboard of system metrics for Linux systems.
It monitors:
  • CPU frequencies, usage (overall and per‑core), temperature, and load averages
  • Memory consumption (RAM and swap)
  • Disk usage and I/O statistics
  • Network I/O and interface status
  • Top processes sorted by CPU or memory usage
  • GPU frequency (if available)

It also supports data export (JSON or CSV) and uses a Nord‑themed, visually appealing dashboard.
Use command‑line options to adjust refresh rates, run duration, export settings, and which metrics to show.

Note: Some metrics (e.g., GPU) may not be available on all systems.
Run this script with root privileges for full functionality.
"""

import atexit
import csv
import json
import logging
import math
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import click
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
import pyfiglet
import psutil

# ------------------------------
# Configuration Constants
# ------------------------------
DEFAULT_REFRESH_RATE = 2.0         # seconds between dashboard updates
DEFAULT_HISTORY_POINTS = 60        # data points for trend graphs
DEFAULT_TOP_PROCESSES = 5          # top processes to display
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")

# ------------------------------
# Nord‑Themed Colors & Console Setup
# ------------------------------
# Using Nord colors for Rich theme
nord_theme = {
    "header": "#81A1C1",    # light blue
    "cpu": "#88C0D0",       # bright blue
    "mem": "#8FBCBB",       # soft cyan
    "load": "#BF616A",      # red-ish
    "proc": "#EBCB8B",      # yellow
    "gpu": "#81A1C1",       # same as header
    "label": "#D8DEE9",     # almost white
    "temp": "#D08770",      # orange-ish
    "uptime": "#A3BE8C",    # green-ish
}
console = Console(theme=console.theme if console.theme else None)

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")

# ------------------------------
# Logging Setup
# ------------------------------
LOG_FILE = "/var/log/system_monitor.log"
def setup_logging() -> None:
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, mode="a")],
    )

# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
SHUTDOWN_FLAG = False
def signal_handler(sig: int, frame: Any) -> None:
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True
    console.print(f"[bold #BF616A]Interrupted by {signal.Signals(sig).name}. Shutting down...[/]")
    sys.exit(128 + sig)

for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)

def cleanup() -> None:
    # Placeholder for any cleanup routines if needed.
    pass
atexit.register(cleanup)

# ------------------------------
# Helper Functions for Basic Metrics
# ------------------------------
def get_cpu_metrics() -> Tuple[float, float, List[float]]:
    freq = psutil.cpu_freq()
    current = freq.current if freq else 0.0
    maximum = freq.max if freq else 0.0
    usage = psutil.cpu_percent(interval=None, percpu=True)
    return current, maximum, usage

def get_load_average() -> Tuple[float, float, float]:
    try:
        return os.getloadavg()
    except Exception:
        return (0.0, 0.0, 0.0)

def get_memory_metrics() -> Tuple[float, float, float, float]:
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available, mem.percent

def get_cpu_temperature() -> Optional[float]:
    temps = psutil.sensors_temperatures()
    if temps:
        for key in ("coretemp", "cpu-thermal"):
            if key in temps and temps[key]:
                sensor = temps[key]
                return sum(t.current for t in sensor) / len(sensor)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return None

def get_gpu_frequency() -> Optional[int]:
    try:
        result = subprocess.run(["vcgencmd", "measure_clock", "gpu"], capture_output=True, text=True, timeout=1)
        output = result.stdout.strip()
        if output.startswith("frequency("):
            parts = output.split("=")
            if len(parts) == 2:
                return int(parts[1])
    except Exception:
        return None
    return None

def get_system_uptime() -> str:
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"

def get_top_processes(limit: int = DEFAULT_TOP_PROCESSES, sort_by: str = "cpu") -> List[Dict[str, Any]]:
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(proc.info)
        except Exception:
            continue
    if sort_by.lower() == "memory":
        procs.sort(key=lambda p: p.get('memory_percent', 0), reverse=True)
    else:
        procs.sort(key=lambda p: p.get('cpu_percent', 0), reverse=True)
    return procs[:limit]

# ------------------------------
# Monitor Classes (Disk, Network, CPU, Memory, Process)
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

class DiskMonitor:
    def __init__(self) -> None:
        self.disks: List[DiskInfo] = []
        self.last_update: float = 0
        self.last_stats: Dict[str, Dict[str, int]] = {}
    def update(self) -> None:
        self.disks = []
        try:
            df = subprocess.run(["df", "-P", "-k", "-T"], capture_output=True, text=True, check=True).stdout
            lines = df.splitlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) < 7:
                    continue
                device, fs, _, _, _, usage, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
                total = int(parts[2]) * 1024
                used = int(parts[3]) * 1024
                free = int(parts[4]) * 1024
                percent = float(usage.rstrip("%"))
                self.disks.append(DiskInfo(device, mount, total, used, free, percent, filesystem=fs))
        except Exception as e:
            console.print(f"[bold #BF616A]Error updating disk info: {e}[/bold #BF616A]")

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
    bytes_sent_rate: float = 0.0
    bytes_recv_rate: float = 0.0
    is_up: bool = True
    mtu: int = 0

class NetworkMonitor:
    def __init__(self) -> None:
        self.interfaces: List[NetworkInfo] = []
        self.last_update: float = 0
        self.last_stats: Dict[str, Dict[str, int]] = {}
    def update(self) -> None:
        current_time = time.time()
        self.interfaces = []
        stats = {}
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]
                for line in lines:
                    if ":" not in line:
                        continue
                    name, data = line.split(":", 1)
                    name = name.strip()
                    fields = data.split()
                    bytes_recv = int(fields[0])
                    packets_recv = int(fields[1])
                    bytes_sent = int(fields[8])
                    packets_sent = int(fields[9])
                    stats[name] = {"bytes_recv": bytes_recv, "bytes_sent": bytes_sent}
                    # For simplicity, skip detailed IP/MAC info
                    self.interfaces.append(NetworkInfo(name=name, ipv4="N/A", mac="N/A", is_up=True))
            self.last_stats = stats
            self.last_update = current_time
        except Exception as e:
            console.print(f"[bold #BF616A]Error updating network info: {e}[/bold #BF616A]")

class CpuMonitor:
    def __init__(self) -> None:
        self.usage_percent: float = 0.0
        self.per_core: List[float] = []
        self.core_count: int = os.cpu_count() or 1
        self.load_avg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    def update(self) -> None:
        self.usage_percent = psutil.cpu_percent(interval=None)
        self.per_core = psutil.cpu_percent(interval=None, percpu=True)
        self.load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)

@dataclass
class MemoryInfo:
    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0

class MemoryMonitor:
    def __init__(self) -> None:
        self.info = MemoryInfo()
    def update(self) -> None:
        mem = psutil.virtual_memory()
        self.info.total = mem.total
        self.info.used = mem.used
        self.info.available = mem.available
        self.info.percent = mem.percent
        swap = psutil.swap_memory()
        self.info.swap_total = swap.total
        self.info.swap_used = swap.used
        self.info.swap_percent = swap.percent

class ProcessMonitor:
    def __init__(self, limit: int = DEFAULT_TOP_PROCESSES) -> None:
        self.limit = limit
        self.processes: List[Dict[str, Any]] = []
    def update(self, sort_by: str = "cpu") -> None:
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                procs.append(proc.info)
            except Exception:
                continue
        if sort_by.lower() == "memory":
            procs.sort(key=lambda p: p.get('memory_percent', 0), reverse=True)
        else:
            procs.sort(key=lambda p: p.get('cpu_percent', 0), reverse=True)
        self.processes = procs[:self.limit]

# ------------------------------
# Unified Monitor Class
# ------------------------------
class UnifiedMonitor:
    def __init__(self, refresh_rate: float = DEFAULT_REFRESH_RATE, top_limit: int = DEFAULT_TOP_PROCESSES) -> None:
        self.refresh_rate = refresh_rate
        self.start_time = time.time()
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor(limit=top_limit)
        # History for graphing CPU usage
        self.cpu_history = deque(maxlen=DEFAULT_HISTORY_POINTS)
    def update(self) -> None:
        self.disk_monitor.update()
        self.network_monitor.update()
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.process_monitor.update()
        self.cpu_history.append(self.cpu_monitor.usage_percent)
    def build_dashboard(self, sort_by: str) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3)
        )
        header_text = f"[header]Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Uptime: {get_system_uptime()}[/header]"
        layout["header"].update(Panel(header_text, style="header"))
        # Build Metrics Table (CPU, Memory, Load, GPU, etc.)
        metrics = []
        cpu_current, cpu_max, per_core = get_cpu_metrics()
        cpu_temp = get_cpu_temperature()
        gpu_freq = get_gpu_frequency()
        load = self.cpu_monitor.load_avg
        mem_total, mem_used, mem_avail, mem_percent = get_memory_metrics()
        metrics.append(f"CPU: {cpu_current:.1f} MHz (Max: {cpu_max:.1f} MHz), Usage: {self.cpu_monitor.usage_percent:.1f}%")
        metrics.append(f"Load: {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")
        metrics.append(f"Memory: {mem_percent:.1f}% used ({mem_used/1e9:.2f}GB / {mem_total/1e9:.2f}GB)")
        if cpu_temp is not None:
            metrics.append(f"CPU Temp: {cpu_temp:.1f} °C")
        if gpu_freq is not None:
            metrics.append(f"GPU Frequency: {gpu_freq/1e6:.2f} MHz")
        # Combine metrics into one panel
        metrics_panel = Panel("\n".join(metrics), title="System Metrics", border_style="cpu")
        # Build Top Processes Panel
        proc_lines = ["PID   Name                CPU%   MEM%"]
        for proc in self.process_monitor.processes:
            proc_lines.append(f"{proc.get('pid', ''):<5} {proc.get('name', '')[:18]:<18} {proc.get('cpu_percent',0):>5.1f} {proc.get('memory_percent',0):>5.1f}")
        proc_panel = Panel("\n".join(proc_lines), title="Top Processes", border_style="proc")
        body = Layout()
        body.split_row(
            Layout(metrics_panel, name="metrics"),
            Layout(proc_panel, name="processes")
        )
        layout["body"].update(body)
        footer_text = "[label]Press Ctrl+C to exit.[/label]"
        layout["footer"].update(Panel(footer_text, style="header"))
        return layout

    def export_data(self, export_format: str, output_file: Optional[str] = None) -> None:
        data = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "usage_percent": self.cpu_monitor.usage_percent,
                "per_core": self.cpu_monitor.per_core,
                "load_avg": self.cpu_monitor.load_avg,
            },
            "memory": asdict(self.memory_monitor.info),
            "disks": [asdict(d) for d in self.disk_monitor.disks],
            "network": [asdict(n) for n in self.network_monitor.interfaces],
            "processes": self.process_monitor.processes,
        }
        os.makedirs(EXPORT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_file:
            output_file = os.path.join(EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}")
        if export_format.lower() == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        elif export_format.lower() == "csv":
            # For brevity, export only CPU and Memory metrics as CSV.
            base, _ = os.path.splitext(output_file)
            with open(f"{base}_cpu.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "usage_percent", "load_avg_1m", "load_avg_5m", "load_avg_15m"])
                writer.writerow([data["timestamp"],
                                 data["cpu"]["usage_percent"],
                                 data["cpu"]["load_avg"][0],
                                 data["cpu"]["load_avg"][1],
                                 data["cpu"]["load_avg"][2]])
            with open(f"{base}_mem.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "total", "used", "available", "percent"])
                mem = data["memory"]
                writer.writerow([data["timestamp"], mem["total"], mem["used"], mem["available"], mem["percent"]])
        console.print(f"[bold #8FBCBB]Data exported to {output_file}[/bold #8FBCBB]")

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.option("--refresh", "-r", default=DEFAULT_REFRESH_RATE, type=float,
              help="Refresh interval in seconds (default: 2.0)")
@click.option("--duration", "-d", default=0.0, type=float,
              help="Total duration to run in seconds (0 means run indefinitely)")
@click.option("--export", "-e", type=click.Choice(["json", "csv"]), default=None,
              help="Export monitoring data in specified format")
@click.option("--export-interval", type=float, default=0.0,
              help="Interval in minutes between exports (0 to disable)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output file path for export (auto-generated if not specified)")
@click.option("--sort-by", type=click.Choice(["cpu", "memory"], case_sensitive=False), default="cpu",
              help="Sort top processes by CPU or memory usage")
def main(refresh: float, duration: float, export: Optional[str],
         export_interval: float, output: Optional[str], sort_by: str) -> None:
    """Unified System Resource Monitor with Live Dashboard and Export capabilities."""
    setup_logging()
    if os.geteuid() != 0:
        console.print("[bold #BF616A]This script must be run as root.[/bold #BF616A]")
        sys.exit(1)
    print_header("System Resource Monitor")
    start_time = time.time()
    monitor = UnifiedMonitor(refresh_rate=refresh, top_limit=DEFAULT_TOP_PROCESSES)
    last_export = 0.0
    try:
        with Live(monitor.build_dashboard(sort_by), refresh_per_second=1, screen=True) as live:
            while True:
                monitor.update()
                live.update(monitor.build_dashboard(sort_by))
                if export and export_interval > 0:
                    if time.time() - last_export >= export_interval * 60:
                        monitor.export_data(export, output)
                        last_export = time.time()
                if duration > 0 and (time.time() - start_time) >= duration:
                    break
                time.sleep(refresh)
    except KeyboardInterrupt:
        console.print("\nExiting monitor...", style="header")
    except Exception as e:
        console.print(f"[bold #BF616A]Unexpected error: {e}[/bold #BF616A]")
        sys.exit(1)
    if export and not export_interval:
        monitor.export_data(export, output)
    console.print("\nMonitor stopped.", style="header")

if __name__ == "__main__":
    main()