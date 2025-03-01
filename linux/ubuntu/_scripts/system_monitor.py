#!/usr/bin/env python3
"""
Interactive System Monitor and Benchmarker

This utility combines benchmarking tools for CPU and GPU performance with a real‑time system
resource monitor. It benchmarks the CPU via prime number calculations and the GPU via NumPy
matrix multiplications. In addition, it displays a live dashboard of system metrics including CPU,
memory, disk, network, and top processes.

Features:
  • Nord‑themed CLI interface with striking ASCII art headers (pyfiglet)
  • Interactive progress indicators and status messages (Rich)
  • Fully interactive menu-driven interface with numbered options
  • Robust error handling, signal handling, and resource cleanup
  • Data export in JSON or CSV format for the monitoring dashboard

Note: Run this script with root privileges for full functionality.
Version: 1.0.0
"""

import atexit
import csv
import json
import logging
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import psutil
import pyfiglet
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)

# ------------------------------
# Configuration Constants
# ------------------------------
VERSION = "1.0.0"
DEFAULT_BENCHMARK_DURATION = 10  # seconds

# Monitor-specific configuration
DEFAULT_REFRESH_RATE = 2.0  # seconds between dashboard updates
DEFAULT_HISTORY_POINTS = 60  # data points for trend graphs
DEFAULT_TOP_PROCESSES = 5  # top processes to display
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")
LOG_FILE = "/var/log/unified_monitor.log"

# Nord‑themed colors
NORD_COLORS = {
    "header": "#88C0D0",  # striking blue for headers
    "section": "#88C0D0",
    "step": "#88C0D0",
    "success": "#8FBCBB",
    "warning": "#5E81AC",
    "error": "#BF616A",
    "label": "#D8DEE9",
    "cpu": "#88C0D0",
    "mem": "#8FBCBB",
    "load": "#BF616A",
    "proc": "#EBCB8B",
    "gpu": "#81A1C1",
    "temp": "#D08770",
    "uptime": "#A3BE8C",
}

# ------------------------------
# Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NORD_COLORS['header']}")


def print_section(text: str) -> None:
    """Print a section header."""
    console.print(
        f"\n[bold {NORD_COLORS['section']}]{text}[/bold {NORD_COLORS['section']}]"
    )


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NORD_COLORS['step']}]• {text}[/{NORD_COLORS['step']}]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(
        f"[bold {NORD_COLORS['success']}]✓ {text}[/bold {NORD_COLORS['success']}]"
    )


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(
        f"[bold {NORD_COLORS['warning']}]⚠ {text}[/bold {NORD_COLORS['warning']}]"
    )


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(
        f"[bold {NORD_COLORS['error']}]✗ {text}[/bold {NORD_COLORS['error']}]"
    )


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add additional cleanup steps if necessary


def signal_handler(sig, frame) -> None:
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


atexit.register(cleanup)
for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    """Setup logging configuration."""
    try:
        log_dir = Path(LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(LOG_FILE, mode="a"),
            ],
        )
        print_success("Logging initialized successfully")
    except Exception as e:
        print_error(f"Failed to setup logging: {e}")


# ------------------------------
# Benchmark Functions
# ------------------------------
def is_prime(n: int) -> bool:
    """Check if a number is prime."""
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def cpu_prime_benchmark(benchmark_duration: int) -> dict:
    """
    Benchmark CPU performance by calculating prime numbers.
    Returns:
      {'primes_per_sec': float, 'elapsed_time': float}
    """
    start_time = time.time()
    end_time = start_time + benchmark_duration
    prime_count = 0
    num = 2

    with Progress(
        SpinnerColumn(style=f"bold {NORD_COLORS['cpu']}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style=f"bold {NORD_COLORS['cpu']}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Calculating primes for {benchmark_duration} seconds...", total=100
        )

        while time.time() < end_time:
            if is_prime(num):
                prime_count += 1
            num += 1

            # Update progress based on time passed
            elapsed = time.time() - start_time
            percent_complete = min(100, (elapsed / benchmark_duration) * 100)
            progress.update(task, completed=percent_complete)

    elapsed = time.time() - start_time
    return {
        "primes_per_sec": prime_count / elapsed if elapsed > 0 else 0,
        "elapsed_time": elapsed,
    }


def get_cpu_info() -> dict:
    """
    Retrieve detailed CPU information.
    Returns:
      {'cores': int, 'threads': int, 'frequency_current': float, 'usage': float}
    """
    freq = psutil.cpu_freq()
    usage = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=False)
    threads = psutil.cpu_count(logical=True)
    return {
        "cores": cores,
        "threads": threads,
        "frequency_current": freq.current if freq else 0,
        "usage": usage,
    }


def cpu_benchmark(benchmark_duration: int = DEFAULT_BENCHMARK_DURATION) -> dict:
    """Run a comprehensive CPU benchmark."""
    print_section("Running CPU Benchmark")
    print_step(f"Running CPU benchmark for {benchmark_duration} seconds...")

    try:
        prime_results = cpu_prime_benchmark(benchmark_duration)
        cpu_info = get_cpu_info()
        return {**prime_results, **cpu_info}
    except Exception as e:
        print_error(f"Error during CPU benchmark: {e}")
        return {"error": str(e)}


def gpu_matrix_benchmark(benchmark_duration: int) -> dict:
    """
    Benchmark GPU performance via matrix multiplication using NumPy.
    Returns:
      {'iterations_per_sec': float, 'elapsed_time': float, 'gpu_info': dict} or error message.
    """
    gpu_info = {}
    try:
        # Try to import GPUtil, but handle case where it's not installed
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info = {
                    "name": gpu.name,
                    "load": gpu.load * 100,
                    "memory_util": gpu.memoryUtil * 100,
                    "temperature": gpu.temperature,
                }
            else:
                gpu_info = {"error": "No GPUs detected"}
        except ImportError:
            gpu_info = {"error": "GPUtil not installed"}
            print_warning("GPUtil not installed. GPU details will be limited.")
    except Exception as e:
        gpu_info = {"error": f"Error retrieving GPU info: {e}"}

    # Matrix multiplication benchmark
    matrix_size = 1024

    with Progress(
        SpinnerColumn(style=f"bold {NORD_COLORS['gpu']}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style=f"bold {NORD_COLORS['gpu']}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running matrix calculations for {benchmark_duration} seconds...",
            total=100,
        )

        A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
        B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
        iterations = 0
        start_time = time.time()
        end_time = start_time + benchmark_duration

        while time.time() < end_time:
            np.dot(A, B)
            iterations += 1

            # Update progress based on time passed
            elapsed = time.time() - start_time
            percent_complete = min(100, (elapsed / benchmark_duration) * 100)
            progress.update(task, completed=percent_complete)

    elapsed = time.time() - start_time
    return {
        "iterations_per_sec": iterations / elapsed if elapsed > 0 else 0,
        "elapsed_time": elapsed,
        "gpu_info": gpu_info,
    }


def gpu_benchmark(benchmark_duration: int = DEFAULT_BENCHMARK_DURATION) -> dict:
    """Run a comprehensive GPU benchmark."""
    print_section("Running GPU Benchmark")
    print_step(f"Running GPU benchmark for {benchmark_duration} seconds...")

    try:
        gpu_results = gpu_matrix_benchmark(benchmark_duration)
        return gpu_results
    except Exception as e:
        print_error(f"Error during GPU benchmark: {e}")
        return {"error": str(e)}


def display_cpu_results(results: dict) -> None:
    """Display formatted CPU benchmark results."""
    print_header("CPU Benchmark Results")

    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return

    console.print(
        f"CPU Cores (Physical): [bold {NORD_COLORS['cpu']}]{results['cores']}[/bold {NORD_COLORS['cpu']}]"
    )
    console.print(
        f"CPU Threads (Logical): [bold {NORD_COLORS['cpu']}]{results['threads']}[/bold {NORD_COLORS['cpu']}]"
    )
    console.print(
        f"CPU Frequency (Current): [bold {NORD_COLORS['cpu']}]{results['frequency_current']:.2f} MHz[/bold {NORD_COLORS['cpu']}]"
    )
    console.print(
        f"CPU Usage during Benchmark: [bold {NORD_COLORS['cpu']}]{results['usage']:.2f}%[/bold {NORD_COLORS['cpu']}]"
    )
    console.print(
        f"Benchmark Duration: [bold {NORD_COLORS['cpu']}]{results['elapsed_time']:.2f} seconds[/bold {NORD_COLORS['cpu']}]"
    )
    console.print(
        f"[bold {NORD_COLORS['success']}]✓ Prime Numbers per Second: {results['primes_per_sec']:.2f}[/bold {NORD_COLORS['success']}]"
    )
    console.print(
        "\n[bold "
        + NORD_COLORS["cpu"]
        + "]Benchmark Details:[/bold "
        + NORD_COLORS["cpu"]
        + "]"
    )
    console.print("- Prime number calculation is used to stress the CPU.")


def display_gpu_results(results: dict) -> None:
    """Display formatted GPU benchmark results."""
    print_header("GPU Benchmark Results")

    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return

    gpu_info = results.get("gpu_info", {})

    if "error" in gpu_info:
        print_warning(f"GPU Detection Issue: {gpu_info['error']}")
        console.print(
            "\n[bold "
            + NORD_COLORS["warning"]
            + "]Troubleshooting Tips:[/bold "
            + NORD_COLORS["warning"]
            + "]"
        )
        console.print("- Ensure GPU drivers are installed correctly.")
        console.print("- Verify that GPUtil is installed (pip install GPUtil3).")
        console.print(
            "- For more intensive benchmarks, consider using libraries like CuPy or TensorFlow."
        )

    # Display matrix multiplication benchmark results regardless of GPU detection
    console.print(
        f"Benchmark Duration: [bold {NORD_COLORS['gpu']}]{results['elapsed_time']:.2f} seconds[/bold {NORD_COLORS['gpu']}]"
    )
    console.print(
        f"[bold {NORD_COLORS['success']}]✓ Matrix Multiplications per Second: {results['iterations_per_sec']:.2f}[/bold {NORD_COLORS['success']}]"
    )

    # Display GPU details if available
    if "name" in gpu_info:
        console.print(
            f"GPU Name: [bold {NORD_COLORS['gpu']}]{gpu_info['name']}[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"GPU Load during Benchmark: [bold {NORD_COLORS['gpu']}]{gpu_info['load']:.2f}%[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"GPU Memory Utilization: [bold {NORD_COLORS['gpu']}]{gpu_info['memory_util']:.2f}%[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"GPU Temperature: [bold {NORD_COLORS['gpu']}]{gpu_info['temperature']:.2f}°C[/bold {NORD_COLORS['gpu']}]"
        )

    console.print(
        "\n[bold "
        + NORD_COLORS["gpu"]
        + "]Benchmark Details:[/bold "
        + NORD_COLORS["gpu"]
        + "]"
    )
    console.print("- Matrix multiplication (NumPy) is used as the workload.")
    console.print("- GPU utilization may vary based on system configuration.")


# ------------------------------
# System Monitor Functions & Classes
# ------------------------------
def get_cpu_metrics() -> Tuple[float, float, List[float]]:
    """Get current CPU metrics."""
    freq = psutil.cpu_freq()
    current = freq.current if freq else 0.0
    maximum = freq.max if freq else 0.0
    usage = psutil.cpu_percent(interval=None, percpu=True)
    return current, maximum, usage


def get_load_average() -> Tuple[float, float, float]:
    """Get system load average."""
    try:
        return os.getloadavg()
    except Exception:
        return (0.0, 0.0, 0.0)


def get_memory_metrics() -> Tuple[float, float, float, float]:
    """Get memory usage metrics."""
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available, mem.percent


def get_cpu_temperature() -> Optional[float]:
    """Get CPU temperature if available."""
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
    """Get GPU frequency if available (primarily for Raspberry Pi)."""
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_clock", "gpu"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        output = result.stdout.strip()
        if output.startswith("frequency("):
            parts = output.split("=")
            if len(parts) == 2:
                return int(parts[1])
    except Exception:
        return None
    return None


def get_system_uptime() -> str:
    """Get formatted system uptime."""
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def get_top_processes(
    limit: int = DEFAULT_TOP_PROCESSES, sort_by: str = "cpu"
) -> List[Dict[str, Any]]:
    """Get list of top processes sorted by CPU or memory usage."""
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(proc.info)
        except Exception:
            continue
    if sort_by.lower() == "memory":
        procs.sort(key=lambda p: p.get("memory_percent", 0), reverse=True)
    else:
        procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
    return procs[:limit]


@dataclass
class DiskInfo:
    """Class to hold disk information."""

    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str = "unknown"
    io_stats: Dict[str, Union[int, float]] = field(default_factory=dict)


class DiskMonitor:
    """Monitor disk usage and IO statistics."""

    def __init__(self) -> None:
        self.disks: List[DiskInfo] = []

    def update(self) -> None:
        """Update disk information."""
        self.disks = []
        try:
            df = subprocess.run(
                ["df", "-P", "-k", "-T"], capture_output=True, text=True, check=True
            ).stdout
            lines = df.splitlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) < 7:
                    continue
                device, fs, _, _, _, usage, mount = (
                    parts[0],
                    parts[1],
                    parts[2],
                    parts[3],
                    parts[4],
                    parts[5],
                    parts[6],
                )
                total = int(parts[2]) * 1024
                used = int(parts[3]) * 1024
                free = int(parts[4]) * 1024
                percent = float(usage.rstrip("%"))
                self.disks.append(
                    DiskInfo(device, mount, total, used, free, percent, filesystem=fs)
                )
        except Exception as e:
            print_error(f"Error updating disk info: {e}")


@dataclass
class NetworkInfo:
    """Class to hold network interface information."""

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
    """Monitor network interfaces and traffic."""

    def __init__(self) -> None:
        self.interfaces: List[NetworkInfo] = []
        self.last_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
        """Update network information."""
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
                    self.interfaces.append(
                        NetworkInfo(name=name, ipv4="N/A", mac="N/A", is_up=True)
                    )
            self.last_stats = stats
        except Exception as e:
            print_error(f"Error updating network info: {e}")


class CpuMonitor:
    """Monitor CPU usage and load."""

    def __init__(self) -> None:
        self.usage_percent: float = 0.0
        self.per_core: List[float] = []
        self.core_count: int = os.cpu_count() or 1
        self.load_avg: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def update(self) -> None:
        """Update CPU metrics."""
        self.usage_percent = psutil.cpu_percent(interval=None)
        self.per_core = psutil.cpu_percent(interval=None, percpu=True)
        self.load_avg = (
            os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        )


@dataclass
class MemoryInfo:
    """Class to hold memory information."""

    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0


class MemoryMonitor:
    """Monitor system memory usage."""

    def __init__(self) -> None:
        self.info = MemoryInfo()

    def update(self) -> None:
        """Update memory metrics."""
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
    """Monitor top processes by CPU or memory usage."""

    def __init__(self, limit: int = DEFAULT_TOP_PROCESSES) -> None:
        self.limit = limit
        self.processes: List[Dict[str, Any]] = []

    def update(self, sort_by: str = "cpu") -> None:
        """Update process list."""
        procs = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent"]
        ):
            try:
                procs.append(proc.info)
            except Exception:
                continue
        if sort_by.lower() == "memory":
            procs.sort(key=lambda p: p.get("memory_percent", 0), reverse=True)
        else:
            procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
        self.processes = procs[: self.limit]


class UnifiedMonitor:
    """Unified system monitor combining all monitoring components."""

    def __init__(
        self,
        refresh_rate: float = DEFAULT_REFRESH_RATE,
        top_limit: int = DEFAULT_TOP_PROCESSES,
    ) -> None:
        self.refresh_rate = refresh_rate
        self.start_time = time.time()
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor(limit=top_limit)
        self.cpu_history = deque(maxlen=DEFAULT_HISTORY_POINTS)

    def update(self) -> None:
        """Update all monitor components."""
        self.disk_monitor.update()
        self.network_monitor.update()
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.process_monitor.update()
        self.cpu_history.append(self.cpu_monitor.usage_percent)

    def build_dashboard(self, sort_by: str) -> Layout:
        """Build the live dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        header_text = f"[bold {NORD_COLORS['header']}]Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Uptime: {get_system_uptime()}[/bold {NORD_COLORS['header']}]"
        layout["header"].update(Panel(header_text, style=f"{NORD_COLORS['header']}"))
        metrics = []
        cpu_current, cpu_max, per_core = get_cpu_metrics()
        cpu_temp = get_cpu_temperature()
        gpu_freq = get_gpu_frequency()
        load = self.cpu_monitor.load_avg
        mem_total, mem_used, mem_avail, mem_percent = get_memory_metrics()
        metrics.append(
            f"CPU: {cpu_current:.1f} MHz (Max: {cpu_max:.1f} MHz), Usage: {self.cpu_monitor.usage_percent:.1f}%"
        )
        metrics.append(f"Load: {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")
        metrics.append(
            f"Memory: {mem_percent:.1f}% used ({mem_used / 1e9:.2f}GB / {mem_total / 1e9:.2f}GB)"
        )
        if cpu_temp is not None:
            metrics.append(f"CPU Temp: {cpu_temp:.1f} °C")
        if gpu_freq is not None:
            metrics.append(f"GPU Frequency: {gpu_freq / 1e6:.2f} MHz")
        metrics_panel = Panel(
            "\n".join(metrics),
            title="System Metrics",
            border_style=f"{NORD_COLORS['cpu']}",
        )
        proc_lines = ["PID   Name                CPU%   MEM%"]
        for proc in self.process_monitor.processes:
            proc_lines.append(
                f"{proc.get('pid', ''):<5} {proc.get('name', '')[:18]:<18} {proc.get('cpu_percent', 0):>5.1f} {proc.get('memory_percent', 0):>5.1f}"
            )
        proc_panel = Panel(
            "\n".join(proc_lines),
            title="Top Processes",
            border_style=f"{NORD_COLORS['proc']}",
        )
        body = Layout()
        body.split_row(
            Layout(metrics_panel, name="metrics"), Layout(proc_panel, name="processes")
        )
        layout["body"].update(body)
        footer_text = (
            f"[{NORD_COLORS['label']}]Press Ctrl+C to exit.[/{NORD_COLORS['label']}]"
        )
        layout["footer"].update(Panel(footer_text, style=f"{NORD_COLORS['header']}"))
        return layout

    def export_data(
        self, export_format: str, output_file: Optional[str] = None
    ) -> None:
        """Export monitoring data to JSON or CSV format."""
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
            output_file = os.path.join(
                EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}"
            )

        if export_format.lower() == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        elif export_format.lower() == "csv":
            base, _ = os.path.splitext(output_file)
            # Export CPU data
            with open(f"{base}_cpu.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "usage_percent",
                        "load_avg_1m",
                        "load_avg_5m",
                        "load_avg_15m",
                    ]
                )
                writer.writerow(
                    [
                        data["timestamp"],
                        data["cpu"]["usage_percent"],
                        data["cpu"]["load_avg"][0],
                        data["cpu"]["load_avg"][1],
                        data["cpu"]["load_avg"][2],
                    ]
                )
            # Export memory data
            with open(f"{base}_mem.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "total", "used", "available", "percent"])
                mem = data["memory"]
                writer.writerow(
                    [
                        data["timestamp"],
                        mem["total"],
                        mem["used"],
                        mem["available"],
                        mem["percent"],
                    ]
                )
        print_success(f"Data exported to {output_file}")


# ------------------------------
# Interactive Monitor Functions
# ------------------------------
def run_monitor(
    refresh: float = DEFAULT_REFRESH_RATE,
    duration: float = 0.0,
    export_format: Optional[str] = None,
    export_interval: float = 0.0,
    output_file: Optional[str] = None,
    sort_by: str = "cpu",
) -> None:
    """Run the system resource monitor with specified settings."""
    setup_logging()
    if os.geteuid() != 0:
        print_error("This script must be run as root for full functionality.")
        if input("Continue anyway? (y/n): ").lower() != "y":
            return

    print_header("System Resource Monitor")
    start_time = time.time()
    monitor_obj = UnifiedMonitor(refresh_rate=refresh, top_limit=DEFAULT_TOP_PROCESSES)
    last_export = 0.0

    try:
        with Live(
            monitor_obj.build_dashboard(sort_by), refresh_per_second=1, screen=True
        ) as live:
            while True:
                monitor_obj.update()
                live.update(monitor_obj.build_dashboard(sort_by))

                if export_format and export_interval > 0:
                    if time.time() - last_export >= export_interval * 60:
                        monitor_obj.export_data(export_format, output_file)
                        last_export = time.time()

                if duration > 0 and (time.time() - start_time) >= duration:
                    break

                time.sleep(refresh)
    except KeyboardInterrupt:
        console.print(f"\nExiting monitor...", style=f"{NORD_COLORS['header']}")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        traceback.print_exc()

    if export_format and not export_interval:
        monitor_obj.export_data(export_format, output_file)

    console.print(f"\nMonitor stopped.", style=f"{NORD_COLORS['header']}")


def monitor_menu() -> None:
    """Interactive menu for setting up and running the system monitor."""
    refresh_rate = DEFAULT_REFRESH_RATE
    duration = 0.0
    export_format = None
    export_interval = 0.0
    output_file = None
    sort_by = "cpu"

    while True:
        print_header("System Monitor Configuration")
        print_section("Current Settings")
        console.print(
            f"1. Refresh Rate: [bold {NORD_COLORS['label']}]{refresh_rate} seconds[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"2. Duration: [bold {NORD_COLORS['label']}]{duration if duration > 0 else 'Unlimited'} seconds[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"3. Export Format: [bold {NORD_COLORS['label']}]{export_format if export_format else 'None'}[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"4. Export Interval: [bold {NORD_COLORS['label']}]{export_interval} minutes[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"5. Output File: [bold {NORD_COLORS['label']}]{output_file if output_file else 'Auto-generated'}[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"6. Sort Processes By: [bold {NORD_COLORS['label']}]{sort_by.upper()}[/bold {NORD_COLORS['label']}]"
        )
        console.print(
            f"7. [bold {NORD_COLORS['success']}]Start Monitor[/bold {NORD_COLORS['success']}]"
        )
        console.print(f"8. Return to Main Menu")

        try:
            choice = input("\nEnter your choice [1-8]: ").strip()

            if choice == "1":
                try:
                    value = float(input("Enter refresh rate in seconds: "))
                    if value <= 0:
                        print_error("Refresh rate must be greater than 0")
                    else:
                        refresh_rate = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "2":
                try:
                    value = float(
                        input("Enter duration in seconds (0 for unlimited): ")
                    )
                    if value < 0:
                        print_error("Duration cannot be negative")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "3":
                print_section("Export Formats")
                console.print("1. None")
                console.print("2. JSON")
                console.print("3. CSV")
                format_choice = input("Choose export format [1-3]: ").strip()
                if format_choice == "1":
                    export_format = None
                elif format_choice == "2":
                    export_format = "json"
                elif format_choice == "3":
                    export_format = "csv"
                else:
                    print_error("Invalid choice")

            elif choice == "4":
                try:
                    value = float(
                        input(
                            "Enter export interval in minutes (0 for export at end only): "
                        )
                    )
                    if value < 0:
                        print_error("Interval cannot be negative")
                    else:
                        export_interval = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "5":
                path = input(
                    "Enter output file path (empty for auto-generated): "
                ).strip()
                output_file = path if path else None

            elif choice == "6":
                print_section("Sort Options")
                console.print("1. CPU Usage")
                console.print("2. Memory Usage")
                sort_choice = input("Choose sort criteria [1-2]: ").strip()
                if sort_choice == "1":
                    sort_by = "cpu"
                elif sort_choice == "2":
                    sort_by = "memory"
                else:
                    print_error("Invalid choice")

            elif choice == "7":
                run_monitor(
                    refresh=refresh_rate,
                    duration=duration,
                    export_format=export_format,
                    export_interval=export_interval,
                    output_file=output_file,
                    sort_by=sort_by,
                )

            elif choice == "8":
                break

            else:
                print_error("Invalid choice. Please select 1-8.")

        except KeyboardInterrupt:
            print_warning("Operation cancelled.")

        input("\nPress Enter to continue...")


# ------------------------------
# Interactive Benchmarking Menu
# ------------------------------
def benchmark_menu() -> None:
    """Interactive menu for running benchmarks."""
    duration = DEFAULT_BENCHMARK_DURATION

    while True:
        print_header("Benchmark Menu")
        print_section("Current Settings")
        console.print(
            f"Benchmark Duration: [bold {NORD_COLORS['label']}]{duration} seconds[/bold {NORD_COLORS['label']}]"
        )

        print_section("Available Benchmarks")
        console.print("1. Change Benchmark Duration")
        console.print("2. Run CPU Benchmark")
        console.print("3. Run GPU Benchmark")
        console.print("4. Run Both CPU and GPU Benchmarks")
        console.print("5. Return to Main Menu")

        try:
            choice = input("\nEnter your choice [1-5]: ").strip()

            if choice == "1":
                try:
                    value = int(input("Enter benchmark duration in seconds: "))
                    if value <= 0:
                        print_error("Duration must be greater than 0")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "2":
                print_header("Running CPU Benchmark")
                results = cpu_benchmark(duration)
                display_cpu_results(results)

            elif choice == "3":
                print_header("Running GPU Benchmark")
                results = gpu_benchmark(duration)
                display_gpu_results(results)

            elif choice == "4":
                print_header("Running CPU and GPU Benchmarks")
                cpu_results = {}
                gpu_results = {}

                def run_cpu() -> None:
                    nonlocal cpu_results
                    cpu_results = cpu_benchmark(duration)

                def run_gpu() -> None:
                    nonlocal gpu_results
                    gpu_results = gpu_benchmark(duration)

                with console.status(
                    f"[bold {NORD_COLORS['cpu']}]Running benchmarks for {duration} seconds...",
                    spinner="dots",
                ):
                    cpu_thread = threading.Thread(target=run_cpu)
                    gpu_thread = threading.Thread(target=run_gpu)
                    cpu_thread.start()
                    gpu_thread.start()
                    cpu_thread.join()
                    gpu_thread.join()

                display_cpu_results(cpu_results)
                display_gpu_results(gpu_results)
                print_success("CPU and GPU Benchmarks Completed")

            elif choice == "5":
                break

            else:
                print_error("Invalid choice. Please select 1-5.")

        except KeyboardInterrupt:
            print_warning("Benchmark interrupted.")

        input("\nPress Enter to continue...")


# ------------------------------
# Main Menu and Entry Point
# ------------------------------
def check_root_privileges() -> bool:
    """Check if script is running with root privileges."""
    return os.geteuid() == 0


def display_system_info() -> None:
    """Display basic system information."""
    hostname = socket.gethostname()
    console.print(
        f"Hostname: [bold {NORD_COLORS['label']}]{hostname}[/bold {NORD_COLORS['label']}]"
    )
    console.print(
        f"Time: [bold {NORD_COLORS['label']}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold {NORD_COLORS['label']}]"
    )
    console.print(
        f"Uptime: [bold {NORD_COLORS['label']}]{get_system_uptime()}[/bold {NORD_COLORS['label']}]"
    )

    cpu_info = get_cpu_info()
    console.print(
        f"CPU: [bold {NORD_COLORS['cpu']}]{cpu_info['cores']} cores / {cpu_info['threads']} threads[/bold {NORD_COLORS['cpu']}]"
    )

    mem = psutil.virtual_memory()
    console.print(
        f"Memory: [bold {NORD_COLORS['mem']}]{mem.total / (1024**3):.2f} GB total[/bold {NORD_COLORS['mem']}]"
    )

    if not check_root_privileges():
        print_warning(
            "Running without root privileges. Some functionality may be limited."
        )


def main_menu() -> None:
    """Display and handle the main menu."""
    while True:
        print_header("System Monitor and Benchmarker")
        display_system_info()

        print_section("Main Menu")
        console.print("1. System Monitor")
        console.print("2. Benchmarks")
        console.print("3. Quick CPU Status")
        console.print("4. Exit")

        try:
            choice = input("\nEnter your choice [1-4]: ").strip()

            if choice == "1":
                monitor_menu()
            elif choice == "2":
                benchmark_menu()
            elif choice == "3":
                # Quick CPU status display
                print_section("Current CPU Status")
                cpu_usage = psutil.cpu_percent(interval=1, percpu=True)
                for i, usage in enumerate(cpu_usage):
                    console.print(
                        f"Core {i}: [bold {NORD_COLORS['cpu']}]{usage}%[/bold {NORD_COLORS['cpu']}]"
                    )
                console.print(
                    f"Average: [bold {NORD_COLORS['cpu']}]{sum(cpu_usage) / len(cpu_usage):.1f}%[/bold {NORD_COLORS['cpu']}]"
                )

                load1, load5, load15 = get_load_average()
                console.print(
                    f"Load Average: [bold {NORD_COLORS['load']}]{load1:.2f}, {load5:.2f}, {load15:.2f}[/bold {NORD_COLORS['load']}]"
                )

                temp = get_cpu_temperature()
                if temp:
                    console.print(
                        f"Temperature: [bold {NORD_COLORS['temp']}]{temp:.1f}°C[/bold {NORD_COLORS['temp']}]"
                    )
            elif choice == "4":
                print_header("Exiting")
                break
            else:
                print_error("Invalid choice. Please select 1-4.")

        except KeyboardInterrupt:
            print_warning("Operation cancelled.")
            continue

        if choice != "3":  # Don't prompt after quick status
            input("\nPress Enter to continue...")


def main() -> None:
    """Main entry point for the application."""
    # Setup signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    try:
        main_menu()
    except KeyboardInterrupt:
        print_warning("Program interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
