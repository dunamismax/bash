#!/usr/bin/env python3
"""
Real time system monitor script.

This script uses Click for CLI handling and Rich for a beautiful,
Nord dark–themed, real–time dashboard that polls system metrics at a
configurable interval. It displays:
  - CPU frequency (current and max) and per-core usage,
  - Load averages,
  - Memory usage,
  - CPU temperature (if available),
  - System uptime,
  - GPU frequency (using vcgencmd, if available or enabled),
  - (Optionally) Disk usage,
  - (Optionally) Network I/O,
  - Top processes sorted by CPU or memory usage.

Command–line options allow you to adjust the refresh interval, run duration,
sorting criteria, enable/disable additional metrics, and even log metrics to a file.
Tested on Raspberry Pi (with vcgencmd installed); if GPU data is not available,
it will show "N/A" (or "Disabled" if --no-gpu is specified).
"""

import time
import os
import subprocess
from datetime import datetime
from typing import Tuple, List, Optional

import psutil
import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.theme import Theme

# Define a Nord dark theme (colors inspired by Nord)
nord_theme = Theme({
    "header": "#81A1C1",    # Light blue
    "cpu": "#88C0D0",       # Bright blue
    "mem": "#8FBCBB",       # Soft cyan
    "load": "#BF616A",      # Red-ish
    "proc": "#EBCB8B",      # Yellow
    "gpu": "#81A1C1",       # Same as header
    "label": "#D8DEE9",     # Almost white
    "temp": "#D08770",      # Orange-ish for temperature
    "uptime": "#A3BE8C",    # Green-ish for uptime
})

console = Console(theme=nord_theme)

def get_cpu_metrics() -> Tuple[float, float, List[float]]:
    """Retrieve current and max CPU frequencies and per-core usage percentages."""
    freq = psutil.cpu_freq()
    current_freq = freq.current if freq else 0.0
    max_freq = freq.max if freq else 0.0
    usage = psutil.cpu_percent(interval=None, percpu=True)
    return current_freq, max_freq, usage

def get_load_average() -> Tuple[float, float, float]:
    """Retrieve system load averages (1, 5, and 15 minutes)."""
    try:
        return os.getloadavg()
    except (AttributeError, OSError):
        return (0.0, 0.0, 0.0)

def get_memory_metrics() -> Tuple[float, float, float, float]:
    """Retrieve memory usage statistics: total, used, available, and percent used."""
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available, mem.percent

def get_cpu_temperature() -> Optional[float]:
    """
    Retrieve CPU temperature in Celsius using psutil if available or fallback
    to reading /sys/class/thermal/thermal_zone0/temp.
    """
    temps = psutil.sensors_temperatures()
    if temps:
        for key in ("coretemp", "cpu-thermal"):
            if key in temps and temps[key]:
                sensor = temps[key]
                return sum(t.current for t in sensor) / len(sensor)
    # Fallback for Linux systems
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return None

def get_top_processes(limit: int = 5, sort_by: str = "cpu") -> List[dict]:
    """
    Return a list of the top processes sorted by CPU or memory usage.

    Args:
        limit (int): Number of processes to return.
        sort_by (str): Sorting criteria: "cpu" or "memory".

    Returns:
        List of process info dictionaries.
    """
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if sort_by.lower() == "memory":
        procs.sort(key=lambda p: p.get('memory_percent', 0), reverse=True)
    else:
        procs.sort(key=lambda p: p.get('cpu_percent', 0), reverse=True)
    return procs[:limit]

def get_gpu_frequency() -> Optional[int]:
    """
    Retrieve GPU frequency using the 'vcgencmd' command.
    Expected output format: frequency(1)=<value>
    
    Returns:
        Frequency in Hz or None if unavailable.
    """
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_clock", "gpu"],
            capture_output=True, text=True, timeout=1
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
    """Return system uptime as a formatted string."""
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"

def build_metrics_table(no_gpu: bool, enable_disk: bool, enable_net: bool) -> Table:
    """
    Build a Rich Table containing system metrics.
    """
    table = Table(title="System Monitor", expand=True, style="header")
    table.add_column("Metric", style="label", no_wrap=True)
    table.add_column("Value", style="label")
    
    # CPU metrics
    cpu_current, cpu_max, cpu_usage = get_cpu_metrics()
    table.add_row("CPU Frequency", f"{cpu_current:.2f} MHz (Max: {cpu_max:.2f} MHz)")
    table.add_row("CPU Usage", ", ".join(f"{u:.1f}%" for u in cpu_usage))
    
    # Load averages
    load1, load5, load15 = get_load_average()
    table.add_row("Load Average", f"{load1:.2f}, {load5:.2f}, {load15:.2f}")
    
    # Memory usage
    total, used, available, mem_percent = get_memory_metrics()
    table.add_row("Memory Usage", f"{mem_percent:.1f}% ({used/1e9:.2f}GB / {total/1e9:.2f}GB)")
    
    # CPU temperature
    cpu_temp = get_cpu_temperature()
    temp_str = f"{cpu_temp:.1f} °C" if cpu_temp is not None else "N/A"
    table.add_row("CPU Temp", temp_str, style="temp")
    
    # System uptime
    table.add_row("Uptime", get_system_uptime(), style="uptime")
    
    # GPU frequency
    if no_gpu:
        gpu_str = "Disabled"
    else:
        gpu_freq = get_gpu_frequency()
        gpu_str = f"{gpu_freq/1e6:.2f} MHz" if gpu_freq is not None else "N/A"
    table.add_row("GPU Frequency", gpu_str, style="gpu")
    
    # Disk usage
    if enable_disk:
        try:
            disk = psutil.disk_usage('/')
            table.add_row("Disk Usage", f"{disk.percent:.1f}% ({disk.used/1e9:.2f}GB / {disk.total/1e9:.2f}GB)")
        except Exception:
            table.add_row("Disk Usage", "N/A")
    
    # Network I/O
    if enable_net:
        try:
            net = psutil.net_io_counters()
            table.add_row("Network I/O", f"Sent: {net.bytes_sent/1e6:.2f}MB, Recv: {net.bytes_recv/1e6:.2f}MB")
        except Exception:
            table.add_row("Network I/O", "N/A")
    
    return table

def build_processes_table(limit: int = 5, sort_by: str = "cpu") -> Table:
    """
    Build a Rich Table displaying the top processes.
    """
    proc_table = Table(title="Top Processes", expand=True, style="proc")
    proc_table.add_column("PID", style="label")
    proc_table.add_column("Name", style="label")
    proc_table.add_column("CPU %", style="label")
    proc_table.add_column("Mem %", style="label")
    
    for proc in get_top_processes(limit, sort_by):
        proc_table.add_row(
            str(proc.get('pid', '')),
            (proc.get('name') or "")[:20],
            f"{proc.get('cpu_percent', 0):.1f}",
            f"{proc.get('memory_percent', 0):.1f}"
        )
    return proc_table

def build_header() -> Panel:
    """Build header panel with current time and uptime."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime_str = get_system_uptime()
    header_text = f"[header]Time: {current_time} | Uptime: {uptime_str}[/header]"
    return Panel(header_text, style="header")

def build_footer() -> Panel:
    """Build footer panel with exit instruction."""
    return Panel("[label]Press Ctrl+C to exit.[/label]", style="header")

def build_dashboard(no_gpu: bool, enable_disk: bool, enable_net: bool, sort_by: str) -> Layout:
    """
    Construct the overall dashboard layout.
    """
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="metrics"),
        Layout(name="processes")
    )
    layout["header"].update(build_header())
    layout["metrics"].update(Panel(build_metrics_table(no_gpu, enable_disk, enable_net),
                                    title="System Metrics", border_style="cpu"))
    layout["processes"].update(Panel(build_processes_table(limit=5, sort_by=sort_by),
                                      title="Top Processes", border_style="proc"))
    layout["footer"].update(build_footer())
    return layout

@click.command()
@click.option('--interval', '-i', default=1.0, type=float,
              help="Refresh interval in seconds (default: 1.0)")
@click.option('--duration', '-d', default=0.0, type=float,
              help="Total duration to run in seconds (0 means run indefinitely)")
@click.option('--no-gpu', is_flag=True,
              help="Disable GPU metrics (if GPU data is not needed or unavailable)")
@click.option('--enable-disk', is_flag=True,
              help="Include disk usage metrics")
@click.option('--enable-net', is_flag=True,
              help="Include network I/O metrics")
@click.option('--sort-by', type=click.Choice(['cpu', 'memory'], case_sensitive=False),
              default='cpu', help="Sort top processes by CPU or memory usage")
@click.option('--log-file', type=click.Path(), default=None,
              help="Optional file path to log metrics (appends data)")
def monitor(interval: float, duration: float, no_gpu: bool, enable_disk: bool,
            enable_net: bool, sort_by: str, log_file: Optional[str]) -> None:
    """
    Real-time system monitor.

    Polls and displays CPU, GPU (if enabled), load, memory, CPU temperature,
    uptime, and top process metrics. Optionally includes disk usage and network I/O.
    The dashboard refreshes every INTERVAL seconds. Use DURATION to run for a fixed period.
    Top processes are sorted by the criteria specified in --sort-by.
    If LOG_FILE is provided, metrics are logged to the specified file.
    """
    start_time = time.time()
    log_fp = open(log_file, "a") if log_file else None

    try:
        with Live(build_dashboard(no_gpu, enable_disk, enable_net, sort_by),
                  refresh_per_second=1, screen=True) as live:
            while True:
                live.update(build_dashboard(no_gpu, enable_disk, enable_net, sort_by))
                if log_fp:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cpu_current, cpu_max, cpu_usage = get_cpu_metrics()
                    load1, load5, load15 = get_load_average()
                    total, used, available, mem_percent = get_memory_metrics()
                    cpu_temp = get_cpu_temperature()
                    temp_str = f"{cpu_temp:.1f}°C" if cpu_temp is not None else "N/A"
                    gpu_freq = get_gpu_frequency() if not no_gpu else None
                    gpu_str = f"{gpu_freq/1e6:.2f}MHz" if gpu_freq is not None else "N/A"
                    log_line = (
                        f"{timestamp} | CPU: {cpu_current:.2f}/{cpu_max:.2f}MHz, "
                        f"Usage: {','.join(f'{u:.1f}%' for u in cpu_usage)} | "
                        f"Load: {load1:.2f}/{load5:.2f}/{load15:.2f} | "
                        f"Memory: {mem_percent:.1f}% | CPU Temp: {temp_str} | "
                        f"GPU: {gpu_str} | Uptime: {get_system_uptime()}\n"
                    )
                    log_fp.write(log_line)
                    log_fp.flush()
                time.sleep(interval)
                if duration > 0 and (time.time() - start_time) >= duration:
                    break
    except KeyboardInterrupt:
        console.print("\nExiting monitor...", style="header")
    finally:
        if log_fp:
            log_fp.close()
    console.print("\nMonitor stopped.", style="header")

if __name__ == "__main__":
    monitor()