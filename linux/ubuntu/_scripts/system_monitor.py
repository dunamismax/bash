#!/usr/bin/env python3
"""
Unified System Monitor and Benchmarker

This utility combines benchmarking tools for CPU and GPU performance with a real‑time system
resource monitor. It benchmarks the CPU via prime number calculations and the GPU via NumPy
matrix multiplications. In addition, it displays a live dashboard of system metrics including CPU,
memory, disk, network, and top processes.

Features:
  • Nord‑themed CLI interface with striking ASCII art headers (pyfiglet)
  • Interactive progress indicators and status messages (Rich)
  • Command‑line options and interactive menus (Click)
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

import click
import GPUtil
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
    while time.time() < end_time:
        if is_prime(num):
            prime_count += 1
        num += 1
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
    with console.status(
        f"[bold {NORD_COLORS['gpu']}]Running CPU benchmark for {benchmark_duration} seconds...",
        spinner="dots",
    ):
        prime_results = cpu_prime_benchmark(benchmark_duration)
    cpu_info = get_cpu_info()
    return {**prime_results, **cpu_info}


def gpu_matrix_benchmark(benchmark_duration: int) -> dict:
    """
    Benchmark GPU performance via matrix multiplication using NumPy.
    Returns:
      {'iterations_per_sec': float, 'elapsed_time': float, 'gpu_object': GPU info} or error message.
    """
    try:
        gpus = GPUtil.getGPUs()
        if not gpus:
            return {
                "error": "No GPUs detected. Ensure drivers are installed and GPUtil is working correctly."
            }
        gpu = gpus[0]
    except Exception as e:
        return {"error": f"Error retrieving GPU info: {e}"}
    matrix_size = 1024
    A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
    B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
    iterations = 0
    start_time = time.time()
    end_time = start_time + benchmark_duration
    while time.time() < end_time:
        np.dot(A, B)
        iterations += 1
    elapsed = time.time() - start_time
    return {
        "iterations_per_sec": iterations / elapsed if elapsed > 0 else 0,
        "elapsed_time": elapsed,
        "gpu_object": gpu,
    }


def get_gpu_info_from_benchmark(result: dict) -> dict:
    """
    Extract relevant GPU details from the benchmark result.
    Returns GPU details or error message.
    """
    if "error" in result:
        return result
    gpu = result["gpu_object"]
    return {
        "name": gpu.name,
        "load": gpu.load * 100,
        "memory_util": gpu.memoryUtil * 100,
        "temperature": gpu.temperature,
    }


def gpu_benchmark(benchmark_duration: int = DEFAULT_BENCHMARK_DURATION) -> dict:
    """Run a comprehensive GPU benchmark."""
    with console.status(
        f"[bold {NORD_COLORS['gpu']}]Running GPU benchmark for {benchmark_duration} seconds...",
        spinner="dots",
    ):
        gpu_results = gpu_matrix_benchmark(benchmark_duration)
    if "error" in gpu_results:
        return gpu_results
    gpu_info = get_gpu_info_from_benchmark(gpu_results)
    return {**gpu_results, **gpu_info}


def display_cpu_results(results: dict) -> None:
    """Display formatted CPU benchmark results."""
    print_header("CPU Benchmark Results")
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
    if "error" in results:
        print_error("GPU Benchmark Error")
        console.print(
            f"[bold {NORD_COLORS['error']}]{results['error']}[/bold {NORD_COLORS['error']}]"
        )
        console.print(
            "\n[bold "
            + NORD_COLORS["warning"]
            + "]Troubleshooting Tips:[/bold "
            + NORD_COLORS["warning"]
            + "]"
        )
        console.print("- Ensure GPU drivers are installed correctly.")
        console.print("- Verify that GPUtil3 is installed (pip install GPUtil3).")
        console.print(
            "- For more intensive benchmarks, consider using libraries like CuPy or TensorFlow."
        )
    else:
        print_header("GPU Benchmark Results")
        console.print(
            f"GPU Name: [bold {NORD_COLORS['gpu']}]{results['name']}[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"Benchmark Duration: [bold {NORD_COLORS['gpu']}]{results['elapsed_time']:.2f} seconds[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"[bold {NORD_COLORS['success']}]✓ Matrix Multiplications per Second: {results['iterations_per_sec']:.2f}[/bold {NORD_COLORS['success']}]"
        )
        console.print(
            f"GPU Load during Benchmark: [bold {NORD_COLORS['gpu']}]{results['load']:.2f}%[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"GPU Memory Utilization: [bold {NORD_COLORS['gpu']}]{results['memory_util']:.2f}%[/bold {NORD_COLORS['gpu']}]"
        )
        console.print(
            f"GPU Temperature: [bold {NORD_COLORS['gpu']}]{results['temperature']:.2f}°C[/bold {NORD_COLORS['gpu']}]"
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

    def update(self) -> None:
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
            console.print(
                f"[bold {NORD_COLORS['error']}]Error updating disk info: {e}[/bold {NORD_COLORS['error']}]"
            )


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
        self.last_stats: Dict[str, Dict[str, int]] = {}

    def update(self) -> None:
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
            console.print(
                f"[bold {NORD_COLORS['error']}]Error updating network info: {e}[/bold {NORD_COLORS['error']}]"
            )


class CpuMonitor:
    def __init__(self) -> None:
        self.usage_percent: float = 0.0
        self.per_core: List[float] = []
        self.core_count: int = os.cpu_count() or 1
        self.load_avg: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def update(self) -> None:
        self.usage_percent = psutil.cpu_percent(interval=None)
        self.per_core = psutil.cpu_percent(interval=None, percpu=True)
        self.load_avg = (
            os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        )


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
        console.print(
            f"[bold {NORD_COLORS['success']}]Data exported to {output_file}[/bold {NORD_COLORS['success']}]"
        )


# ------------------------------
# CLI Commands with Click
# ------------------------------
@click.group()
@click.version_option(version=VERSION)
def cli() -> None:
    """
    Unified System Monitor and Benchmarker CLI

    Benchmark your system's CPU and GPU performance and monitor system resources in real‑time.
    """
    pass


# Benchmark Commands
@cli.group()
def bench() -> None:
    """Run benchmarks for CPU and GPU."""
    pass


@bench.command()
@click.option(
    "--duration",
    default=DEFAULT_BENCHMARK_DURATION,
    type=int,
    help="Duration of the CPU benchmark in seconds.",
    metavar="SECONDS",
)
def cpu(duration: int) -> None:
    """Run CPU benchmark."""
    print_header("Starting CPU Benchmark")
    try:
        results = cpu_benchmark(duration)
        display_cpu_results(results)
        print_success("CPU Benchmark Completed")
    except Exception as e:
        print_error(f"Error during CPU benchmark: {e}")
        traceback.print_exc()


@bench.command()
@click.option(
    "--duration",
    default=DEFAULT_BENCHMARK_DURATION,
    type=int,
    help="Duration of the GPU benchmark in seconds.",
    metavar="SECONDS",
)
def gpu(duration: int) -> None:
    """Run GPU benchmark."""
    print_header("Starting GPU Benchmark")
    try:
        results = gpu_benchmark(duration)
        display_gpu_results(results)
        print_success("GPU Benchmark Completed")
    except Exception as e:
        print_error(f"Error during GPU benchmark: {e}")
        traceback.print_exc()


@bench.command()
@click.option(
    "--duration",
    default=DEFAULT_BENCHMARK_DURATION,
    type=int,
    help="Duration of both benchmarks in seconds.",
    metavar="SECONDS",
)
def both(duration: int) -> None:
    """Run both CPU and GPU benchmarks concurrently."""
    print_header("Starting CPU and GPU Benchmarks")
    cpu_results = {}
    gpu_results = {}

    def run_cpu() -> None:
        nonlocal cpu_results
        cpu_results = cpu_benchmark(duration)

    def run_gpu() -> None:
        nonlocal gpu_results
        gpu_results = gpu_benchmark(duration)

    cpu_thread = threading.Thread(target=run_cpu)
    gpu_thread = threading.Thread(target=run_gpu)
    cpu_thread.start()
    gpu_thread.start()
    cpu_thread.join()
    gpu_thread.join()
    display_cpu_results(cpu_results)
    display_gpu_results(gpu_results)
    print_success("CPU and GPU Benchmarks Completed")


@bench.command()
def menu() -> None:
    """Interactive menu to select and run benchmarks."""
    while True:
        print_header("Benchmark Menu")
        console.print(
            f"[bold {NORD_COLORS['section']}]Select a benchmark to run:[/bold {NORD_COLORS['section']}]"
        )
        console.print(
            f"[bold {NORD_COLORS['section']}]1.[/bold {NORD_COLORS['section']}] CPU Benchmark"
        )
        console.print(
            f"[bold {NORD_COLORS['section']}]2.[/bold {NORD_COLORS['section']}] GPU Benchmark"
        )
        console.print(
            f"[bold {NORD_COLORS['section']}]3.[/bold {NORD_COLORS['section']}] CPU and GPU Benchmarks"
        )
        console.print(
            f"[bold {NORD_COLORS['section']}]4.[/bold {NORD_COLORS['section']}] Exit"
        )
        try:
            choice = click.prompt(
                f"[bold {NORD_COLORS['section']}]Enter your choice [1-4][/bold {NORD_COLORS['section']}]",
                type=click.IntRange(1, 4),
            )
        except Exception as e:
            print_error(f"Invalid input: {e}")
            continue
        ctx = click.get_current_context()
        if choice == 1:
            ctx.invoke(cpu)
        elif choice == 2:
            ctx.invoke(gpu)
        elif choice == 3:
            ctx.invoke(both)
        elif choice == 4:
            console.print(
                f"[bold {NORD_COLORS['section']}]Exiting Benchmark Tool...[/bold {NORD_COLORS['section']}]"
            )
            break
        else:
            print_error("Invalid choice. Please select from 1-4.")


# Monitor Command
@cli.command()
@click.option(
    "--refresh",
    "-r",
    default=DEFAULT_REFRESH_RATE,
    type=float,
    help="Refresh interval in seconds (default: 2.0)",
)
@click.option(
    "--duration",
    "-d",
    default=0.0,
    type=float,
    help="Total duration to run in seconds (0 means run indefinitely)",
)
@click.option(
    "--export",
    "-e",
    type=click.Choice(["json", "csv"]),
    default=None,
    help="Export monitoring data in specified format",
)
@click.option(
    "--export-interval",
    type=float,
    default=0.0,
    help="Interval in minutes between exports (0 to disable)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path for export (auto-generated if not specified)",
)
@click.option(
    "--sort-by",
    type=click.Choice(["cpu", "memory"], case_sensitive=False),
    default="cpu",
    help="Sort top processes by CPU or memory usage",
)
def monitor(
    refresh: float,
    duration: float,
    export: Optional[str],
    export_interval: float,
    output: Optional[str],
    sort_by: str,
) -> None:
    """Unified System Resource Monitor with Live Dashboard and Export capabilities."""
    setup_logging()
    if os.geteuid() != 0:
        console.print(
            f"[bold {NORD_COLORS['error']}]This script must be run as root.[/bold {NORD_COLORS['error']}]"
        )
        sys.exit(1)
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
                if export and export_interval > 0:
                    if time.time() - last_export >= export_interval * 60:
                        monitor_obj.export_data(export, output)
                        last_export = time.time()
                if duration > 0 and (time.time() - start_time) >= duration:
                    break
                time.sleep(refresh)
    except KeyboardInterrupt:
        console.print(f"\nExiting monitor...", style=f"{NORD_COLORS['header']}")
    except Exception as e:
        console.print(
            f"[bold {NORD_COLORS['error']}]Unexpected error: {e}[/bold {NORD_COLORS['error']}]"
        )
        sys.exit(1)
    if export and not export_interval:
        monitor_obj.export_data(export, output)
    console.print(f"\nMonitor stopped.", style=f"{NORD_COLORS['header']}")


# ------------------------------
# Main Execution
# ------------------------------
if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        print_warning("Setup interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)
