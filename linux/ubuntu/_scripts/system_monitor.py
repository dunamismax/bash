#!/usr/bin/env python3
"""
Enhanced System Monitor and Benchmarker
--------------------------------------------------

A sophisticated terminal interface for monitoring system performance metrics and
running benchmarks. Featuring CPU and GPU performance analysis with real-time
resource tracking presented in an elegant Nord-themed interface.

Features:
- Real-time system resource monitoring with historical data
- CPU benchmarking via prime number calculations
- GPU benchmarking via matrix multiplication operations
- Process monitoring with sorting by CPU or memory usage
- Data export capabilities in JSON or CSV format
- Fully interactive menu-driven interface
- Elegant Nord-themed styling throughout

Usage:
  Run the script and select an option from the menu:
  - System Monitor: View real-time system metrics
  - Benchmarks: Run performance tests on CPU and GPU
  - Quick CPU Status: Get immediate CPU performance overview
  - Export Options: Save system data for analysis

Version: 2.0.0
"""

# ----------------------------------------------------------------
# Imports & Dependency Check
# ----------------------------------------------------------------
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
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, Set

# Check for required external dependencies
try:
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
        TaskProgressColumn,
    )
    from rich.table import Table
    from rich.text import Text
    from rich.columns import Columns
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm
    from rich.traceback import install as install_rich_traceback
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("Please install required dependencies using:")
    print("pip install numpy psutil pyfiglet rich")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.0.0"
APP_NAME = "System Monitor"
APP_SUBTITLE = "Performance Analysis Suite"
DEFAULT_BENCHMARK_DURATION = 10  # seconds
DEFAULT_REFRESH_RATE = 2.0  # seconds between dashboard updates
DEFAULT_HISTORY_POINTS = 60  # data points for trend graphs
DEFAULT_TOP_PROCESSES = 8  # top processes to display
EXPORT_DIR = os.path.expanduser("~/system_monitor_exports")
LOG_FILE = "/var/log/system_monitor.log"
OPERATION_TIMEOUT = 30  # seconds


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple

    # Component-specific mappings for consistent application
    CPU = FROST_2  # CPU-related elements
    MEM = FROST_1  # Memory-related elements
    DISK = FROST_3  # Disk-related elements
    NET = FROST_4  # Network-related elements
    LOAD = RED  # Load average and warnings
    TEMP = ORANGE  # Temperature indicators
    PROC = YELLOW  # Process information
    GPU = PURPLE  # GPU-related elements
    SUCCESS = GREEN  # Success messages and indicators
    HEADER = FROST_2  # Headers and titles
    TEXT = SNOW_STORM_1  # Normal text


# ----------------------------------------------------------------
# Console Setup
# ----------------------------------------------------------------
console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Utility Print Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "digital", "mini", "smslant"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=70)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
               _                                         _ _             
 ___ _   _ ___| |_ ___ _ __ ___    _ __ ___   ___  _ __ (_) |_ ___  _ __ 
/ __| | | / __| __/ _ \ '_ ` _ \  | '_ ` _ \ / _ \| '_ \| | __/ _ \| '__|
\__ \ |_| \__ \ ||  __/ | | | | | | | | | | | (_) | | | | | || (_) | |   
|___/\__, |___/\__\___|_| |_| |_| |_| |_| |_|\___/|_| |_|_|\__\___/|_|   
     |___/                                                                
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a beautiful gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 70 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message with a prefix.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message with a checkmark prefix."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message with a warning symbol prefix."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message with an X prefix."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step message with an arrow prefix."""
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Additional cleanup steps can be added here


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"Signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Setup logging configuration."""
    try:
        log_dir = Path(LOG_FILE).parent
        if os.access(str(log_dir), os.W_OK) or (
            not log_dir.exists() and os.access(str(log_dir.parent), os.W_OK)
        ):
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
        else:
            print_warning(
                f"Cannot write to log directory {log_dir}. Logging to file disabled."
            )
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                handlers=[logging.StreamHandler(sys.stdout)],
            )
    except Exception as e:
        print_error(f"Failed to setup logging: {e}")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results

    Raises:
        subprocess.CalledProcessError: If the command returns a non-zero exit code
        subprocess.TimeoutExpired: If the command times out
        Exception: For any other errors
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# System Information Functions
# ----------------------------------------------------------------
def get_system_uptime() -> str:
    """Return formatted system uptime."""
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def get_cpu_info() -> Dict[str, Any]:
    """
    Retrieve CPU information.
    Returns a dictionary with 'cores', 'threads', 'frequency_current', and 'usage'.
    """
    freq = psutil.cpu_freq()
    usage = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=False)
    threads = psutil.cpu_count(logical=True)

    # Try to get CPU model name
    cpu_name = "Unknown CPU"
    try:
        if sys.platform == "linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        cpu_name = line.split(":", 1)[1].strip()
                        break
        elif sys.platform == "darwin":
            result = run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
            cpu_name = result.stdout.strip()
        elif sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
    except Exception:
        pass

    return {
        "model": cpu_name,
        "cores": cores,
        "threads": threads,
        "frequency_current": freq.current if freq else 0,
        "frequency_max": freq.max if freq and freq.max else 0,
        "usage": usage,
    }


def get_cpu_temperature() -> Optional[float]:
    """Retrieve CPU temperature if available."""
    temps = psutil.sensors_temperatures()
    if temps:
        for key in ("coretemp", "cpu_thermal", "cpu-thermal", "k10temp"):
            if key in temps and temps[key]:
                sensor = temps[key]
                return sum(t.current for t in sensor) / len(sensor)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return None


def get_gpu_info() -> Dict[str, Any]:
    """
    Retrieve GPU information if available.
    """
    gpu_info = {
        "name": "No GPU detected",
        "load": 0.0,
        "memory": 0.0,
        "temperature": None,
    }

    try:
        # Try GPUtil first
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # Get the first GPU
                gpu_info = {
                    "name": gpu.name,
                    "load": gpu.load * 100,
                    "memory": gpu.memoryUtil * 100,
                    "temperature": gpu.temperature,
                }
                return gpu_info
        except ImportError:
            pass

        # Try nvidia-smi for NVIDIA GPUs
        try:
            result = run_command(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ]
            )
            if result.stdout:
                values = result.stdout.strip().split(",")
                gpu_info = {
                    "name": values[0].strip(),
                    "load": float(values[1].strip()),
                    "memory": float(values[2].strip()),
                    "temperature": float(values[3].strip()),
                }
                return gpu_info
        except Exception:
            pass

        # Try lspci for basic GPU identification
        if sys.platform == "linux":
            try:
                result = run_command(["lspci", "-v"], check=False)
                for line in result.stdout.split("\n"):
                    if "VGA" in line or "3D" in line:
                        gpu_info["name"] = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass

    except Exception as e:
        logging.warning(f"Error retrieving GPU info: {e}")

    return gpu_info


def get_memory_metrics() -> Tuple[float, float, float, float]:
    """Retrieve memory usage metrics."""
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available, mem.percent


def get_load_average() -> Tuple[float, float, float]:
    """Retrieve system load average."""
    try:
        return os.getloadavg()
    except Exception:
        # Windows doesn't support getloadavg
        return (0.0, 0.0, 0.0)


# ----------------------------------------------------------------
# Benchmark Functions
# ----------------------------------------------------------------
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


def cpu_prime_benchmark(benchmark_duration: int) -> Dict[str, Any]:
    """
    Benchmark CPU performance by calculating prime numbers.
    Returns a dictionary with keys 'primes_per_sec' and 'elapsed_time'.
    """
    start_time = time.time()
    end_time = start_time + benchmark_duration
    prime_count = 0
    num = 2

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.CPU}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.CPU, complete_style=NordColors.FROST_2
        ),
        TextColumn("[{task.percentage:.0f}%]"),
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
            elapsed = time.time() - start_time
            progress.update(
                task, completed=min(100, (elapsed / benchmark_duration) * 100)
            )

    elapsed = time.time() - start_time

    return {
        "primes_per_sec": prime_count / elapsed if elapsed > 0 else 0,
        "elapsed_time": elapsed,
        "prime_count": prime_count,
        "highest_prime_checked": num - 1,
    }


def cpu_benchmark(
    benchmark_duration: int = DEFAULT_BENCHMARK_DURATION,
) -> Dict[str, Any]:
    """Run a comprehensive CPU benchmark combining prime calculation and CPU info."""
    print_section("Running CPU Benchmark")
    print_step(f"Benchmarking for {benchmark_duration} seconds...")
    try:
        prime_results = cpu_prime_benchmark(benchmark_duration)
        cpu_info = get_cpu_info()
        return {**prime_results, **cpu_info}
    except Exception as e:
        print_error(f"Error during CPU benchmark: {e}")
        logging.exception("CPU benchmark error")
        return {"error": str(e)}


def gpu_matrix_benchmark(benchmark_duration: int) -> Dict[str, Any]:
    """
    Benchmark GPU performance via matrix multiplication (NumPy).
    Returns a dictionary with 'iterations_per_sec', 'elapsed_time', and 'gpu_info'.
    """
    # Get GPU info first
    gpu_info = get_gpu_info()

    # Determine matrix size based on available memory
    matrix_size = 1024  # Default size
    try:
        mem = psutil.virtual_memory()
        # Scale matrix size based on available memory, but cap it
        avail_gb = mem.available / (1024**3)
        if avail_gb > 8:
            matrix_size = 2048
        elif avail_gb < 2:
            matrix_size = 512
    except Exception:
        pass

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.GPU}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.GPU, complete_style=NordColors.FROST_1
        ),
        TextColumn("[{task.percentage:.0f}%]"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running matrix calculations ({matrix_size}x{matrix_size}) for {benchmark_duration} seconds...",
            total=100,
        )

        # Initialize matrices
        try:
            A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
            B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
        except MemoryError:
            # If we fail, try a smaller size
            matrix_size = 512
            A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
            B = np.random.rand(matrix_size, matrix_size).astype(np.float32)

        iterations = 0
        start_time = time.time()
        end_time = start_time + benchmark_duration

        while time.time() < end_time:
            np.dot(A, B)
            iterations += 1
            elapsed = time.time() - start_time
            progress.update(
                task, completed=min(100, (elapsed / benchmark_duration) * 100)
            )

    elapsed = time.time() - start_time

    return {
        "iterations_per_sec": iterations / elapsed if elapsed > 0 else 0,
        "elapsed_time": elapsed,
        "matrix_size": matrix_size,
        "gpu_info": gpu_info,
    }


def gpu_benchmark(
    benchmark_duration: int = DEFAULT_BENCHMARK_DURATION,
) -> Dict[str, Any]:
    """Run a comprehensive GPU benchmark."""
    print_section("Running GPU Benchmark")
    print_step(f"Benchmarking for {benchmark_duration} seconds...")
    try:
        return gpu_matrix_benchmark(benchmark_duration)
    except Exception as e:
        print_error(f"Error during GPU benchmark: {e}")
        logging.exception("GPU benchmark error")
        return {"error": str(e)}


def display_cpu_results(results: Dict[str, Any]) -> None:
    """Display formatted CPU benchmark results."""
    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]CPU Benchmark Results[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    # Add CPU info rows
    if "model" in results:
        table.add_row("CPU Model", results["model"])
    table.add_row("Physical Cores", str(results["cores"]))
    table.add_row("Logical Cores", str(results["threads"]))
    table.add_row("Current Frequency", f"{results['frequency_current']:.2f} MHz")
    if results.get("frequency_max", 0) > 0:
        table.add_row("Maximum Frequency", f"{results['frequency_max']:.2f} MHz")
    table.add_row("CPU Usage", f"{results['usage']:.2f}%")

    # Add benchmark result rows
    table.add_row("Benchmark Duration", f"{results['elapsed_time']:.2f} seconds")
    table.add_row("Prime Numbers Found", f"{results['prime_count']:,}")
    table.add_row("Highest Number Checked", f"{results['highest_prime_checked']:,}")
    table.add_row(
        "Prime Calculations/Second",
        f"{results['primes_per_sec']:.2f}",
        style=f"bold {NordColors.SUCCESS}",
    )

    console.print(table)

    # Add some context
    console.print("\n[bold {0}]Benchmark Explanation:[/{0}]".format(NordColors.FROST_2))
    console.print(
        "• Prime number calculations stress single-core performance and integer operations"
    )
    console.print(
        "• Higher values indicate better CPU performance for general computing tasks"
    )
    console.print(
        "• This benchmark is particularly sensitive to CPU clock speed and IPC efficiency"
    )


def display_gpu_results(results: Dict[str, Any]) -> None:
    """Display formatted GPU benchmark results."""
    if "error" in results:
        print_error(f"Benchmark Error: {results['error']}")
        return

    gpu_info = results.get("gpu_info", {})

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]GPU Benchmark Results[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    # Add GPU info rows if available
    if gpu_info:
        table.add_row("GPU Name", gpu_info.get("name", "Unknown"))
        if "load" in gpu_info:
            table.add_row("GPU Load", f"{gpu_info['load']:.2f}%")
        if "memory" in gpu_info:
            table.add_row("GPU Memory Usage", f"{gpu_info['memory']:.2f}%")
        if "temperature" in gpu_info and gpu_info["temperature"]:
            table.add_row("GPU Temperature", f"{gpu_info['temperature']:.1f}°C")

    # Add benchmark result rows
    table.add_row("Benchmark Duration", f"{results['elapsed_time']:.2f} seconds")
    table.add_row("Matrix Size", f"{results['matrix_size']}x{results['matrix_size']}")
    table.add_row(
        "Matrix Operations/Second",
        f"{results['iterations_per_sec']:.2f}",
        style=f"bold {NordColors.SUCCESS}",
    )

    console.print(table)

    # Add some context or notes
    console.print("\n[bold {0}]Benchmark Explanation:[/{0}]".format(NordColors.FROST_2))
    console.print("• Matrix multiplication tests floating-point performance")
    console.print(
        "• This benchmark primarily uses NumPy which may use CPU-based optimizations"
    )
    console.print(
        "• For true GPU benchmarking, specialized libraries like CUDA or OpenCL would be more accurate"
    )

    if "error" in gpu_info or "No GPU" in gpu_info.get("name", ""):
        console.print(
            "\n[bold {0}]Troubleshooting Tips:[/{0}]".format(NordColors.WARNING)
        )
        console.print("• Ensure GPU drivers are installed correctly")
        console.print(
            "• Consider installing GPUtil or PyTorch for better GPU detection"
        )
        console.print("• For NVIDIA GPUs, ensure nvidia-smi is working properly")


# ----------------------------------------------------------------
# Data Structures for System Monitoring
# ----------------------------------------------------------------
@dataclass
class DiskInfo:
    """Data class to hold disk information."""

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
    """Data class to hold network interface information."""

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


@dataclass
class MemoryInfo:
    """Data class to hold memory information."""

    total: int = 0
    used: int = 0
    available: int = 0
    percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0


# ----------------------------------------------------------------
# System Monitor Classes
# ----------------------------------------------------------------
class DiskMonitor:
    """Monitor disk usage and IO statistics."""

    def __init__(self) -> None:
        self.disks: List[DiskInfo] = []
        self.last_update: float = 0.0

    def update(self) -> None:
        """Update disk information."""
        self.last_update = time.time()
        self.disks = []

        try:
            # Get basic partition information
            partitions = psutil.disk_partitions(all=False)
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    device = partition.device
                    mountpoint = partition.mountpoint

                    disk = DiskInfo(
                        device=device,
                        mountpoint=mountpoint,
                        total=usage.total,
                        used=usage.used,
                        free=usage.free,
                        percent=usage.percent,
                        filesystem=partition.fstype,
                    )

                    # Try to get IO statistics
                    try:
                        if hasattr(psutil, "disk_io_counters"):
                            io_counters = psutil.disk_io_counters(perdisk=True)
                            # Find the appropriate disk name
                            disk_name = device.split("/")[-1]
                            if disk_name in io_counters:
                                io_stats = io_counters[disk_name]
                                disk.io_stats = {
                                    "read_count": io_stats.read_count,
                                    "write_count": io_stats.write_count,
                                    "read_bytes": io_stats.read_bytes,
                                    "write_bytes": io_stats.write_bytes,
                                }
                    except Exception as e:
                        logging.debug(f"Could not get IO stats for {device}: {e}")

                    self.disks.append(disk)
                except (PermissionError, FileNotFoundError):
                    # Skip if we can't access this mountpoint
                    continue
                except Exception as e:
                    logging.warning(
                        f"Error getting disk info for {partition.mountpoint}: {e}"
                    )
        except Exception as e:
            logging.error(f"Error updating disk info: {e}")
            print_error(f"Error updating disk info: {e}")


class NetworkMonitor:
    """Monitor network interfaces and traffic."""

    def __init__(self) -> None:
        self.interfaces: List[NetworkInfo] = []
        self.last_stats: Dict[str, Dict[str, int]] = {}
        self.last_update: float = 0.0

    def update(self) -> None:
        """Update network interface information."""
        now = time.time()
        time_delta = now - self.last_update if self.last_update > 0 else 1.0
        self.last_update = now

        try:
            # Get network addresses
            addresses = psutil.net_if_addrs()

            # Get IO counters
            io_counters = psutil.net_io_counters(pernic=True)

            # Get interface stats
            stats = psutil.net_if_stats()

            # Build interfaces list
            self.interfaces = []
            for name, addrs in addresses.items():
                interface = NetworkInfo(name=name)

                # Get addresses
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        interface.ipv4 = addr.address
                    elif addr.family == socket.AF_INET6:
                        interface.ipv6 = addr.address
                    elif addr.family == psutil.AF_LINK:
                        interface.mac = addr.address

                # Get stats
                if name in stats:
                    interface.is_up = stats[name].isup
                    interface.mtu = stats[name].mtu

                # Get IO counters
                if name in io_counters:
                    interface.bytes_sent = io_counters[name].bytes_sent
                    interface.bytes_recv = io_counters[name].bytes_recv
                    interface.packets_sent = io_counters[name].packets_sent
                    interface.packets_recv = io_counters[name].packets_recv

                    # Calculate rates
                    if name in self.last_stats:
                        last = self.last_stats[name]
                        interface.bytes_sent_rate = (
                            interface.bytes_sent - last.get("bytes_sent", 0)
                        ) / time_delta
                        interface.bytes_recv_rate = (
                            interface.bytes_recv - last.get("bytes_recv", 0)
                        ) / time_delta

                    # Update last stats
                    self.last_stats[name] = {
                        "bytes_sent": interface.bytes_sent,
                        "bytes_recv": interface.bytes_recv,
                    }

                self.interfaces.append(interface)
        except Exception as e:
            logging.error(f"Error updating network info: {e}")
            print_error(f"Error updating network info: {e}")


class CpuMonitor:
    """Monitor CPU usage and load."""

    def __init__(self) -> None:
        self.usage_percent: float = 0.0
        self.per_core: List[float] = []
        self.core_count: int = os.cpu_count() or 1
        self.load_avg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.frequency: float = 0.0
        self.temperature: Optional[float] = None
        self.last_update: float = 0.0

    def update(self) -> None:
        """Update CPU metrics."""
        self.last_update = time.time()

        try:
            # Get usage
            self.usage_percent = psutil.cpu_percent(interval=None)
            self.per_core = psutil.cpu_percent(interval=None, percpu=True)

            # Get load average
            try:
                self.load_avg = (
                    os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
                )
            except Exception:
                self.load_avg = (0.0, 0.0, 0.0)

            # Get frequency
            freq = psutil.cpu_freq()
            self.frequency = freq.current if freq else 0.0

            # Get temperature
            self.temperature = get_cpu_temperature()
        except Exception as e:
            logging.error(f"Error updating CPU info: {e}")
            print_error(f"Error updating CPU info: {e}")


class MemoryMonitor:
    """Monitor system memory usage."""

    def __init__(self) -> None:
        self.info = MemoryInfo()
        self.last_update: float = 0.0

    def update(self) -> None:
        """Update memory metrics."""
        self.last_update = time.time()

        try:
            # Get virtual memory info
            mem = psutil.virtual_memory()
            self.info.total = mem.total
            self.info.used = mem.used
            self.info.available = mem.available
            self.info.percent = mem.percent

            # Get swap info
            swap = psutil.swap_memory()
            self.info.swap_total = swap.total
            self.info.swap_used = swap.used
            self.info.swap_percent = swap.percent
        except Exception as e:
            logging.error(f"Error updating memory info: {e}")
            print_error(f"Error updating memory info: {e}")


class ProcessMonitor:
    """Monitor top processes by CPU or memory usage."""

    def __init__(self, limit: int = DEFAULT_TOP_PROCESSES) -> None:
        self.limit = limit
        self.processes: List[Dict[str, Any]] = []
        self.last_update: float = 0.0

    def update(self, sort_by: str = "cpu") -> None:
        """
        Update process list sorted by usage.

        Args:
            sort_by: Sort criteria - "cpu" or "memory"
        """
        self.last_update = time.time()
        procs = []

        try:
            # Get process information
            for proc in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    proc_info = proc.info
                    # Get additional info
                    with proc.oneshot():
                        try:
                            proc_info["create_time"] = proc.create_time()
                        except Exception:
                            proc_info["create_time"] = 0

                        try:
                            proc_info["memory_info"] = proc.memory_info()
                            proc_info["memory_mb"] = proc_info["memory_info"].rss / (
                                1024 * 1024
                            )
                        except Exception:
                            proc_info["memory_mb"] = 0.0

                    procs.append(proc_info)
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue
                except Exception as e:
                    logging.debug(f"Error getting process info: {e}")

            # Sort processes
            if sort_by.lower() == "memory":
                procs.sort(key=lambda p: p.get("memory_percent", 0), reverse=True)
            else:
                procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)

            # Limit the number of processes
            self.processes = procs[: self.limit]
        except Exception as e:
            logging.error(f"Error updating process list: {e}")
            print_error(f"Error updating process list: {e}")


class UnifiedMonitor:
    """Unified system monitor combining all components."""

    def __init__(
        self,
        refresh_rate: float = DEFAULT_REFRESH_RATE,
        top_limit: int = DEFAULT_TOP_PROCESSES,
    ) -> None:
        self.refresh_rate = refresh_rate
        self.start_time = time.time()
        self.top_limit = top_limit

        # Initialize component monitors
        self.disk_monitor = DiskMonitor()
        self.network_monitor = NetworkMonitor()
        self.cpu_monitor = CpuMonitor()
        self.memory_monitor = MemoryMonitor()
        self.process_monitor = ProcessMonitor(limit=top_limit)

        # Initialize history
        self.cpu_history = deque(maxlen=DEFAULT_HISTORY_POINTS)
        self.memory_history = deque(maxlen=DEFAULT_HISTORY_POINTS)

        # Monitoring flags
        self.stop_requested = False

    def update(self) -> None:
        """Update all system metrics."""
        self.cpu_monitor.update()
        self.memory_monitor.update()
        self.disk_monitor.update()
        self.network_monitor.update()
        self.process_monitor.update()

        # Update history
        self.cpu_history.append(self.cpu_monitor.usage_percent)
        self.memory_history.append(self.memory_monitor.info.percent)

    def build_dashboard(self, sort_by: str = "cpu") -> Layout:
        """
        Build a rich dashboard layout with all system metrics.

        Args:
            sort_by: Criteria for sorting processes ("cpu" or "memory")

        Returns:
            Layout object containing the dashboard
        """
        # Create main layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Create header
        hostname = socket.gethostname()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = get_system_uptime()

        header_text = f"[bold {NordColors.HEADER}]Hostname: {hostname} | Time: {current_time} | Uptime: {uptime}[/]"
        layout["header"].update(Panel(header_text, style=NordColors.HEADER))

        # Split body into sections
        body = Layout()
        body.split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=3),
        )

        # Create metrics panels
        body["left"].split_column(
            Layout(name="cpu", ratio=2),
            Layout(name="memory", ratio=1),
            Layout(name="disk", ratio=2),
        )

        body["right"].split_column(
            Layout(name="processes", ratio=2),
            Layout(name="network", ratio=1),
        )

        # CPU panel
        cpu_info = self.cpu_monitor
        cpu_temp = cpu_info.temperature

        cpu_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.CPU}",
            expand=True,
            box=None,
        )

        cpu_table.add_column(
            "Core", style=f"bold {NordColors.FROST_4}", justify="right"
        )
        cpu_table.add_column("Usage", style=f"{NordColors.TEXT}")
        cpu_table.add_column(
            "Bar", style=f"{NordColors.CPU}", justify="center", ratio=3
        )

        # Add overall CPU usage
        cpu_table.add_row(
            "All",
            f"{cpu_info.usage_percent:.1f}%",
            self._create_bar(cpu_info.usage_percent, NordColors.CPU),
        )

        # Add individual cores
        for i, usage in enumerate(cpu_info.per_core):
            cpu_table.add_row(
                f"{i + 1}", f"{usage:.1f}%", self._create_bar(usage, NordColors.CPU)
            )

        # Add additional CPU metrics
        cpu_stats = Table(box=None, expand=True, show_header=False)
        cpu_stats.add_column("Metric", style=f"bold {NordColors.FROST_3}")
        cpu_stats.add_column("Value", style=f"{NordColors.TEXT}")

        cpu_stats.add_row("Frequency", f"{cpu_info.frequency:.1f} MHz")
        cpu_stats.add_row(
            "Load Avg",
            f"{cpu_info.load_avg[0]:.2f}, {cpu_info.load_avg[1]:.2f}, {cpu_info.load_avg[2]:.2f}",
        )

        if cpu_temp is not None:
            temp_color = self._get_temperature_color(cpu_temp)
            cpu_stats.add_row("Temperature", f"[{temp_color}]{cpu_temp:.1f}°C[/]")

        cpu_panel = Panel(
            Columns([cpu_table, cpu_stats], expand=True),
            title=f"[bold {NordColors.CPU}]CPU Usage[/]",
            border_style=NordColors.CPU,
        )
        body["left"]["cpu"].update(cpu_panel)

        # Memory panel
        mem_info = self.memory_monitor.info
        mem_table = Table(box=None, expand=True)
        mem_table.add_column("Memory", style=f"bold {NordColors.MEM}")
        mem_table.add_column("Usage", style=f"{NordColors.TEXT}")
        mem_table.add_column("Bar", ratio=3, justify="center")

        # RAM
        mem_used_gb = mem_info.used / (1024**3)
        mem_total_gb = mem_info.total / (1024**3)
        mem_table.add_row(
            "RAM",
            f"{mem_info.percent:.1f}% ({mem_used_gb:.1f}/{mem_total_gb:.1f} GB)",
            self._create_bar(mem_info.percent, NordColors.MEM),
        )

        # Swap if available
        if mem_info.swap_total > 0:
            swap_used_gb = mem_info.swap_used / (1024**3)
            swap_total_gb = mem_info.swap_total / (1024**3)
            mem_table.add_row(
                "Swap",
                f"{mem_info.swap_percent:.1f}% ({swap_used_gb:.1f}/{swap_total_gb:.1f} GB)",
                self._create_bar(mem_info.swap_percent, NordColors.MEM),
            )

        mem_panel = Panel(
            mem_table,
            title=f"[bold {NordColors.MEM}]Memory Usage[/]",
            border_style=NordColors.MEM,
        )
        body["left"]["memory"].update(mem_panel)

        # Disk panel
        disk_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.DISK}",
            expand=True,
            box=None,
        )

        disk_table.add_column("Mount", style=f"bold {NordColors.FROST_3}")
        disk_table.add_column("Size", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column("Used", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column("Free", style=f"{NordColors.TEXT}", justify="right")
        disk_table.add_column(
            "Usage", style=f"{NordColors.TEXT}", justify="center", ratio=2
        )

        for disk in self.disk_monitor.disks[
            :4
        ]:  # Limit to 4 disks to avoid overcrowding
            disk_table.add_row(
                disk.mountpoint,
                f"{disk.total / (1024**3):.1f} GB",
                f"{disk.used / (1024**3):.1f} GB",
                f"{disk.free / (1024**3):.1f} GB",
                self._create_bar(disk.percent, NordColors.DISK),
            )

        disk_panel = Panel(
            disk_table,
            title=f"[bold {NordColors.DISK}]Disk Usage[/]",
            border_style=NordColors.DISK,
        )
        body["left"]["disk"].update(disk_panel)

        # Process panel
        process_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.PROC}",
            expand=True,
            box=None,
        )

        process_table.add_column(
            "PID", style=f"bold {NordColors.FROST_4}", justify="right"
        )
        process_table.add_column("Name", style=f"{NordColors.TEXT}")
        process_table.add_column("CPU%", style=f"{NordColors.CPU}", justify="right")
        process_table.add_column("MEM%", style=f"{NordColors.MEM}", justify="right")
        process_table.add_column("MEM", style=f"{NordColors.TEXT}", justify="right")
        process_table.add_column("User", style=f"{NordColors.TEXT}")
        process_table.add_column("Status", style=f"{NordColors.TEXT}")

        for proc in self.process_monitor.processes:
            status_color = {
                "running": NordColors.GREEN,
                "sleeping": NordColors.FROST_3,
                "stopped": NordColors.YELLOW,
                "zombie": NordColors.RED,
            }.get(proc.get("status", ""), NordColors.TEXT)

            process_table.add_row(
                str(proc.get("pid", "N/A")),
                proc.get("name", "Unknown")[:20],
                f"{proc.get('cpu_percent', 0.0):.1f}",
                f"{proc.get('memory_percent', 0.0):.1f}",
                f"{proc.get('memory_mb', 0.0):.1f} MB",
                proc.get("username", "")[:10],
                f"[{status_color}]{proc.get('status', 'unknown')}[/]",
            )

        process_panel = Panel(
            process_table,
            title=f"[bold {NordColors.PROC}]Top Processes (sorted by {sort_by.upper()})[/]",
            border_style=NordColors.PROC,
        )
        body["right"]["processes"].update(process_panel)

        # Network panel
        network_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.NET}",
            expand=True,
            box=None,
        )

        network_table.add_column("Interface", style=f"bold {NordColors.FROST_3}")
        network_table.add_column("IP Address", style=f"{NordColors.TEXT}")
        network_table.add_column("RX", style=f"{NordColors.TEXT}", justify="right")
        network_table.add_column("TX", style=f"{NordColors.TEXT}", justify="right")
        network_table.add_column("Status", style=f"{NordColors.TEXT}", justify="center")

        # Filter interfaces to show only physical and virtual adapters (no loopback)
        active_interfaces = [
            iface
            for iface in self.network_monitor.interfaces
            if iface.bytes_recv_rate > 0
            or iface.bytes_sent_rate > 0
            or iface.name.startswith(("en", "eth", "wl", "ww"))
        ]

        # If no active interfaces, show all
        if not active_interfaces:
            active_interfaces = self.network_monitor.interfaces

        for iface in active_interfaces[:4]:  # Limit to 4 interfaces
            # Format rates in appropriate units
            rx_rate = self._format_network_rate(iface.bytes_recv_rate)
            tx_rate = self._format_network_rate(iface.bytes_sent_rate)

            # Status indicator
            status = "● Online" if iface.is_up else "○ Offline"
            status_color = NordColors.GREEN if iface.is_up else NordColors.RED

            network_table.add_row(
                iface.name, iface.ipv4, rx_rate, tx_rate, f"[{status_color}]{status}[/]"
            )

        network_panel = Panel(
            network_table,
            title=f"[bold {NordColors.NET}]Network Interfaces[/]",
            border_style=NordColors.NET,
        )
        body["right"]["network"].update(network_panel)

        # Update the main body
        layout["body"].update(body)

        # Create footer
        footer_text = f"[{NordColors.TEXT}]Press Ctrl+C to exit | r: refresh | q: quit | e: export data[/{NordColors.TEXT}]"
        layout["footer"].update(Panel(footer_text, style=NordColors.HEADER))

        return layout

    def _create_bar(self, percentage: float, color: str) -> str:
        """Create a visual bar representing a percentage."""
        width = 20
        filled = int((percentage / 100) * width)

        # Choose color based on percentage
        if percentage > 90:
            bar_color = NordColors.RED
        elif percentage > 70:
            bar_color = NordColors.YELLOW
        else:
            bar_color = color

        bar = f"[{bar_color}]{'█' * filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - filled)}[/]"
        return bar

    def _get_temperature_color(self, temp: float) -> str:
        """Get appropriate color for temperature value."""
        if temp > 80:
            return NordColors.RED
        elif temp > 70:
            return NordColors.ORANGE
        elif temp > 60:
            return NordColors.YELLOW
        else:
            return NordColors.GREEN

    def _format_network_rate(self, bytes_per_sec: float) -> str:
        """Format network rate in appropriate units."""
        if bytes_per_sec > 1024**3:
            return f"{bytes_per_sec / 1024**3:.2f} GB/s"
        elif bytes_per_sec > 1024**2:
            return f"{bytes_per_sec / 1024**2:.2f} MB/s"
        elif bytes_per_sec > 1024:
            return f"{bytes_per_sec / 1024:.2f} KB/s"
        else:
            return f"{bytes_per_sec:.1f} B/s"

    def export_data(
        self, export_format: str, output_file: Optional[str] = None
    ) -> None:
        """
        Export system data to file.

        Args:
            export_format: "json" or "csv"
            output_file: Optional output file path
        """
        # Build data structure
        data = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "hostname": socket.gethostname(),
                "uptime": get_system_uptime(),
            },
            "cpu": {
                "usage_percent": self.cpu_monitor.usage_percent,
                "per_core": self.cpu_monitor.per_core,
                "load_avg": self.cpu_monitor.load_avg,
                "frequency": self.cpu_monitor.frequency,
                "temperature": self.cpu_monitor.temperature,
            },
            "memory": asdict(self.memory_monitor.info),
            "disks": [asdict(d) for d in self.disk_monitor.disks],
            "network": [asdict(n) for n in self.network_monitor.interfaces],
            "processes": self.process_monitor.processes,
        }

        # Create export directory
        os.makedirs(EXPORT_DIR, exist_ok=True)

        # Generate filename if not provided
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_file:
            output_file = os.path.join(
                EXPORT_DIR, f"system_monitor_{timestamp}.{export_format}"
            )

        try:
            # Export based on format
            if export_format.lower() == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    # Use a custom serializer for non-serializable objects
                    def default_serializer(obj):
                        if hasattr(obj, "__dict__"):
                            return obj.__dict__
                        return str(obj)

                    json.dump(data, f, indent=2, default=default_serializer)
                print_success(f"Data exported to {output_file}")

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
                            "frequency",
                            "temperature",
                        ]
                    )
                    writer.writerow(
                        [
                            data["timestamp"],
                            data["cpu"]["usage_percent"],
                            data["cpu"]["load_avg"][0],
                            data["cpu"]["load_avg"][1],
                            data["cpu"]["load_avg"][2],
                            data["cpu"]["frequency"],
                            data["cpu"]["temperature"] or "N/A",
                        ]
                    )

                # Export memory data
                with open(f"{base}_memory.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "total",
                            "used",
                            "available",
                            "percent",
                            "swap_total",
                            "swap_used",
                            "swap_percent",
                        ]
                    )
                    mem = data["memory"]
                    writer.writerow(
                        [
                            data["timestamp"],
                            mem["total"],
                            mem["used"],
                            mem["available"],
                            mem["percent"],
                            mem["swap_total"],
                            mem["swap_used"],
                            mem["swap_percent"],
                        ]
                    )

                # Export disk data
                with open(f"{base}_disks.csv", "w", newline="", encoding="utf-8") as f:
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
                    for disk in data["disks"]:
                        writer.writerow(
                            [
                                data["timestamp"],
                                disk["device"],
                                disk["mountpoint"],
                                disk["total"],
                                disk["used"],
                                disk["free"],
                                disk["percent"],
                                disk["filesystem"],
                            ]
                        )

                print_success(f"Data exported to {base}_*.csv files")
            else:
                print_error(f"Unsupported export format: {export_format}")
        except Exception as e:
            print_error(f"Error exporting data: {e}")
            logging.exception("Error exporting data")


# ----------------------------------------------------------------
# Interactive Monitor Functions
# ----------------------------------------------------------------
def run_monitor(
    refresh: float = DEFAULT_REFRESH_RATE,
    duration: float = 0.0,
    export_format: Optional[str] = None,
    export_interval: float = 0.0,
    output_file: Optional[str] = None,
    sort_by: str = "cpu",
) -> None:
    """
    Run the system resource monitor with the specified settings.

    Args:
        refresh: Refresh rate in seconds
        duration: Monitoring duration in seconds (0 for unlimited)
        export_format: Export format ("json", "csv", or None)
        export_interval: Export interval in minutes (0 for export at end only)
        output_file: Output file path
        sort_by: Process sort criteria ("cpu" or "memory")
    """
    setup_logging()

    # Check for root privileges
    if os.name == "posix" and os.geteuid() != 0:
        print_warning("Limited functionality without root privileges")
        if Confirm.ask("Continue anyway?"):
            pass
        else:
            return

    # Create monitor
    console.clear()
    console.print(create_header())

    start_time = time.time()
    monitor = UnifiedMonitor(refresh_rate=refresh, top_limit=DEFAULT_TOP_PROCESSES)
    last_export_time = 0.0

    try:
        with Live(
            monitor.build_dashboard(sort_by),
            refresh_per_second=1 / refresh,
            screen=True,
        ) as live:
            running = True
            while running:
                try:
                    # Update monitor data
                    monitor.update()

                    # Update the live display
                    live.update(monitor.build_dashboard(sort_by))

                    # Handle exports if configured
                    now = time.time()
                    if export_format and export_interval > 0:
                        if now - last_export_time >= export_interval * 60:
                            monitor.export_data(export_format, output_file)
                            last_export_time = now

                    # Check duration limit
                    if duration > 0 and (now - start_time) >= duration:
                        break

                    # Pause for refresh rate
                    time.sleep(refresh)
                except KeyboardInterrupt:
                    running = False
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        traceback.print_exc()

    # Final export if configured
    if export_format and not export_interval:
        monitor.export_data(export_format, output_file)

    console.print(f"\n[bold {NordColors.SUCCESS}]Monitor session completed.[/]")


def monitor_menu() -> None:
    """Interactive menu for system monitor configuration and execution."""
    refresh_rate = DEFAULT_REFRESH_RATE
    duration = 0.0
    export_format = None
    export_interval = 0.0
    output_file = None
    sort_by = "cpu"

    while True:
        console.clear()
        console.print(create_header())

        print_section("Monitor Configuration")

        # Build settings table
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            expand=True,
            box=None,
        )

        table.add_column("Option", style=f"bold {NordColors.FROST_3}")
        table.add_column("Setting", style=f"{NordColors.TEXT}")
        table.add_column("Description", style=f"dim {NordColors.TEXT}")

        table.add_row(
            "1. Refresh Rate", f"{refresh_rate} seconds", "Time between updates"
        )
        table.add_row(
            "2. Duration",
            f"{duration if duration > 0 else 'Unlimited'} seconds",
            "Total monitoring time (0 = unlimited)",
        )
        table.add_row(
            "3. Export Format",
            f"{export_format if export_format else 'None'}",
            "Data export file format",
        )
        table.add_row(
            "4. Export Interval",
            f"{export_interval} minutes",
            "Time between data exports (0 = end only)",
        )
        table.add_row(
            "5. Output File",
            f"{output_file if output_file else 'Auto-generated'}",
            "Export file location",
        )
        table.add_row(
            "6. Sort Processes By",
            f"{sort_by.upper()}",
            "Process list sorting criteria",
        )

        console.print(
            Panel(table, title="Current Settings", border_style=NordColors.FROST_2)
        )

        # Actions
        actions_table = Table(show_header=False, box=None, expand=True)
        actions_table.add_column("Action", style=f"bold {NordColors.FROST_2}")
        actions_table.add_column("Description", style=f"{NordColors.TEXT}")

        actions_table.add_row("7", "[bold]Start Monitor[/]")
        actions_table.add_row("8", "Return to Main Menu")

        console.print(
            Panel(actions_table, title="Actions", border_style=NordColors.FROST_3)
        )

        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5", "6", "7", "8"],
                default="7",
            )

            if choice == "1":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter refresh rate in seconds", default=str(refresh_rate)
                        )
                    )
                    if value <= 0:
                        print_error("Refresh rate must be greater than 0")
                    else:
                        refresh_rate = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "2":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter duration in seconds (0 for unlimited)",
                            default=str(duration),
                        )
                    )
                    if value < 0:
                        print_error("Duration cannot be negative")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "3":
                console.print(
                    "\n[bold {0}]Export Formats:[/{0}]".format(NordColors.FROST_2)
                )
                console.print("1. None")
                console.print("2. JSON")
                console.print("3. CSV")

                format_choice = Prompt.ask(
                    "Choose export format", choices=["1", "2", "3"], default="1"
                )

                if format_choice == "1":
                    export_format = None
                elif format_choice == "2":
                    export_format = "json"
                elif format_choice == "3":
                    export_format = "csv"

            elif choice == "4":
                try:
                    value = float(
                        Prompt.ask(
                            "Enter export interval in minutes (0 for export at end only)",
                            default=str(export_interval),
                        )
                    )
                    if value < 0:
                        print_error("Interval cannot be negative")
                    else:
                        export_interval = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "5":
                path = Prompt.ask(
                    "Enter output file path (empty for auto-generated)",
                    default="" if not output_file else output_file,
                )
                output_file = path if path else None

            elif choice == "6":
                console.print(
                    "\n[bold {0}]Sort Options:[/{0}]".format(NordColors.FROST_2)
                )
                console.print("1. CPU Usage")
                console.print("2. Memory Usage")

                sort_choice = Prompt.ask(
                    "Choose sort criteria",
                    choices=["1", "2"],
                    default="1" if sort_by == "cpu" else "2",
                )

                sort_by = "cpu" if sort_choice == "1" else "memory"

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

        except KeyboardInterrupt:
            print_warning("Operation cancelled.")

        # Only ask for Enter if not starting monitor or returning to main menu
        if choice not in ["7", "8"]:
            Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")


def benchmark_menu() -> None:
    """Interactive menu for running benchmarks."""
    duration = DEFAULT_BENCHMARK_DURATION

    while True:
        console.clear()
        console.print(create_header())

        print_section("Benchmark Configuration")

        # Settings table
        settings_table = Table(show_header=False, box=None, expand=True)
        settings_table.add_column("Setting", style=f"bold {NordColors.FROST_3}")
        settings_table.add_column("Value", style=f"{NordColors.TEXT}")

        settings_table.add_row("Benchmark Duration", f"{duration} seconds")

        console.print(
            Panel(
                settings_table,
                title="Current Settings",
                border_style=NordColors.FROST_2,
            )
        )

        # Actions table
        actions_table = Table(show_header=False, box=None, expand=True)
        actions_table.add_column("Option", style=f"bold {NordColors.FROST_2}")
        actions_table.add_column("Description", style=f"{NordColors.TEXT}")

        actions_table.add_row("1", "Change Benchmark Duration")
        actions_table.add_row("2", "Run CPU Benchmark")
        actions_table.add_row("3", "Run GPU Benchmark")
        actions_table.add_row("4", "Run Both CPU and GPU Benchmarks")
        actions_table.add_row("5", "Return to Main Menu")

        console.print(
            Panel(
                actions_table,
                title="Available Benchmarks",
                border_style=NordColors.FROST_3,
            )
        )

        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5"],
                default="2",
            )

            if choice == "1":
                try:
                    value = int(
                        Prompt.ask(
                            "Enter benchmark duration in seconds", default=str(duration)
                        )
                    )
                    if value <= 0:
                        print_error("Duration must be greater than 0")
                    else:
                        duration = value
                except ValueError:
                    print_error("Please enter a valid number")

            elif choice == "2":
                console.clear()
                console.print(create_header())
                results = cpu_benchmark(duration)
                display_cpu_results(results)

            elif choice == "3":
                console.clear()
                console.print(create_header())
                results = gpu_benchmark(duration)
                display_gpu_results(results)

            elif choice == "4":
                console.clear()
                console.print(create_header())

                cpu_results = {}
                gpu_results = {}

                # Define thread functions
                def run_cpu() -> None:
                    nonlocal cpu_results
                    cpu_results = cpu_benchmark(duration)

                def run_gpu() -> None:
                    nonlocal gpu_results
                    gpu_results = gpu_benchmark(duration)

                # Run benchmarks in parallel
                with Progress(
                    SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                    TextColumn("[progress.description]{task.description}"),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    progress.add_task(
                        f"Running benchmarks for {duration} seconds...", total=None
                    )

                    cpu_thread = threading.Thread(target=run_cpu)
                    gpu_thread = threading.Thread(target=run_gpu)

                    cpu_thread.start()
                    gpu_thread.start()

                    cpu_thread.join()
                    gpu_thread.join()

                # Display results
                display_cpu_results(cpu_results)
                print()
                display_gpu_results(gpu_results)
                print_success("CPU and GPU Benchmarks Completed")

            elif choice == "5":
                break

        except KeyboardInterrupt:
            print_warning("Benchmark interrupted.")

        # Only ask for Enter if not returning to main menu
        if choice != "5":
            Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")


# ----------------------------------------------------------------
# Main Menu and Entry Point
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Check if the script is running as root."""
    if os.name == "posix":
        return os.geteuid() == 0
    return False


def display_system_info() -> None:
    """Display basic system information."""
    hostname = socket.gethostname()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime = get_system_uptime()

    info_table = Table(show_header=False, box=None, expand=True)
    info_table.add_column("Property", style=f"bold {NordColors.FROST_3}")
    info_table.add_column("Value", style=f"{NordColors.TEXT}")

    info_table.add_row("Hostname", hostname)
    info_table.add_row("Time", current_time)
    info_table.add_row("Uptime", uptime)

    # CPU and memory info
    cpu_info = get_cpu_info()
    mem = psutil.virtual_memory()

    info_table.add_row(
        "CPU",
        f"{cpu_info['model'][:40]}... ({cpu_info['cores']} cores / {cpu_info['threads']} threads)",
    )
    info_table.add_row("Memory", f"{mem.total / (1024**3):.2f} GB total")

    # Check for root privileges
    if not check_root_privileges() and os.name == "posix":
        info_table.add_row(
            "Privileges",
            "[bold {0}]Running without root privileges. Some functionality may be limited.[/]".format(
                NordColors.YELLOW
            ),
        )

    console.print(
        Panel(info_table, title="System Information", border_style=NordColors.FROST_2)
    )


def quick_cpu_status() -> None:
    """Display quick CPU status information."""
    console.clear()
    console.print(create_header())

    print_section("Current CPU Status")

    # Create progress
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.CPU}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Measuring CPU usage...", total=None)
        # Measure for 1 second for more accurate reading
        cpu_usage = psutil.cpu_percent(interval=1, percpu=True)
        progress.update(task, description="CPU information gathered")

    # Build the table for per-core display
    cpu_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.CPU}",
        expand=True,
        title=f"[bold {NordColors.CPU}]Per-Core CPU Usage[/]",
        border_style=NordColors.CPU,
    )

    cpu_table.add_column("Core", style=f"bold {NordColors.FROST_4}", justify="right")
    cpu_table.add_column("Usage", style=f"{NordColors.TEXT}", justify="right")
    cpu_table.add_column("Bar", style=f"{NordColors.CPU}", ratio=3)

    # Add rows for each core
    for i, usage in enumerate(cpu_usage):
        # Determine color based on usage
        if usage > 90:
            bar_color = NordColors.RED
        elif usage > 70:
            bar_color = NordColors.YELLOW
        else:
            bar_color = NordColors.CPU

        # Create bar visualization
        width = 30
        filled = int((usage / 100) * width)
        bar = f"[{bar_color}]{'█' * filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - filled)}[/]"

        cpu_table.add_row(f"Core {i + 1}", f"{usage:.1f}%", bar)

    # Add overall average
    avg = sum(cpu_usage) / len(cpu_usage)
    avg_bar_color = (
        NordColors.RED
        if avg > 90
        else NordColors.YELLOW
        if avg > 70
        else NordColors.GREEN
    )
    avg_filled = int((avg / 100) * width)
    avg_bar = f"[{avg_bar_color}]{'█' * avg_filled}[/][{NordColors.POLAR_NIGHT_4}]{'█' * (width - avg_filled)}[/]"

    cpu_table.add_row(
        "Average", f"{avg:.1f}%", avg_bar, style=f"bold {NordColors.FROST_2}"
    )

    console.print(cpu_table)

    # Show additional CPU info
    info_table = Table(show_header=False, box=None, expand=True)
    info_table.add_column("Metric", style=f"bold {NordColors.FROST_3}")
    info_table.add_column("Value", style=f"{NordColors.TEXT}")

    # Get CPU info
    cpu_info = get_cpu_info()
    load = get_load_average()
    temp = get_cpu_temperature()

    # Add rows
    if "model" in cpu_info:
        info_table.add_row("CPU Model", cpu_info["model"])

    info_table.add_row(
        "Cores / Threads",
        f"{cpu_info['cores']} physical cores / {cpu_info['threads']} logical cores",
    )
    info_table.add_row("Frequency", f"{cpu_info['frequency_current']:.1f} MHz")

    # Add load average
    load_color = (
        NordColors.RED
        if load[0] > cpu_info["threads"]
        else NordColors.YELLOW
        if load[0] > cpu_info["threads"] / 2
        else NordColors.LOAD
    )
    info_table.add_row(
        "Load Average", f"[{load_color}]{load[0]:.2f}[/], {load[1]:.2f}, {load[2]:.2f}"
    )

    # Add temperature if available
    if temp:
        temp_color = (
            NordColors.RED
            if temp > 80
            else NordColors.ORANGE
            if temp > 70
            else NordColors.YELLOW
            if temp > 60
            else NordColors.GREEN
        )
        info_table.add_row("Temperature", f"[{temp_color}]{temp:.1f}°C[/]")

    console.print(
        Panel(
            info_table,
            title="Additional CPU Information",
            border_style=NordColors.FROST_3,
        )
    )


def main_menu() -> None:
    """Display and handle the main menu."""
    while True:
        console.clear()
        console.print(create_header())

        # Display system info
        display_system_info()

        # Create menu table
        menu_table = Table(
            show_header=False,
            box=None,
            expand=True,
            title=f"[bold {NordColors.FROST_2}]Main Menu[/]",
            title_justify="center",
            border_style=NordColors.FROST_2,
        )

        menu_table.add_column("Option", style=f"bold {NordColors.FROST_2}")
        menu_table.add_column("Description", style=f"{NordColors.TEXT}")

        menu_table.add_row("1", "System Monitor (Real-time Dashboard)")
        menu_table.add_row("2", "Run Performance Benchmarks")
        menu_table.add_row("3", "Quick CPU Status")
        menu_table.add_row("4", "About This Tool")
        menu_table.add_row("5", "Exit")

        console.print(Panel(menu_table))

        try:
            choice = Prompt.ask(
                f"[bold {NordColors.FROST_2}]Enter your choice[/]",
                choices=["1", "2", "3", "4", "5"],
                default="1",
            )

            if choice == "1":
                monitor_menu()
            elif choice == "2":
                benchmark_menu()
            elif choice == "3":
                quick_cpu_status()
                Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")
            elif choice == "4":
                console.clear()
                console.print(create_header())

                about_text = f"""
[bold {NordColors.FROST_2}]Enhanced System Monitor and Benchmarker v{VERSION}[/]

A sophisticated terminal application for monitoring system performance metrics and 
running benchmarks. This tool combines real-time monitoring capabilities with 
performance testing tools in an elegant Nord-themed interface.

[bold {NordColors.FROST_3}]Key Features:[/]
• Real-time system resource monitoring with historical data tracking
• CPU benchmarking via prime number calculations
• GPU benchmarking via matrix multiplication operations 
• Process monitoring with sorting by CPU or memory usage
• Data export capabilities in JSON or CSV format
• Fully interactive menu-driven interface

[bold {NordColors.FROST_3}]Technologies:[/]
• Built with Python 3 and the Rich library for terminal styling
• Uses psutil for system metrics collection
• Employs NumPy for matrix operations in GPU benchmarking
• Features pyfiglet for ASCII art headers
                """

                console.print(
                    Panel(about_text, title="About", border_style=NordColors.FROST_2)
                )

                Prompt.ask(f"[{NordColors.TEXT}]Press Enter to continue[/]", default="")
            elif choice == "5":
                console.clear()
                goodbye_panel = Panel(
                    f"[bold {NordColors.FROST_2}]Thank you for using the Enhanced System Monitor![/]",
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
                console.print(goodbye_panel)
                break

        except KeyboardInterrupt:
            print_warning("Operation cancelled.")
            continue


def main() -> None:
    """Main entry point for the application."""
    # Register signal handlers and cleanup
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
