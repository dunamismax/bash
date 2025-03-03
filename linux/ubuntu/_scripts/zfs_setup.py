#!/usr/bin/env python3
"""
Unified ZFS Management
--------------------------------------------------

A comprehensive terminal interface for ZFS pool management with Nord theme styling.
Provides streamlined workflows for:
  • ZFS Setup - Installs packages, enables services, imports pools and configures mounts
  • ZFS Expansion - Expands ZFS pools to utilize full device capacity with validation

Features elegant progress tracking, interactive prompts, and detailed logging.
Must be run with root privileges on Linux systems with ZFS support.

Usage:
  sudo python3 zfs_management.py setup [options]     # Configure and import ZFS pools
  sudo python3 zfs_management.py expand [options]    # Expand ZFS pools to use full device size

Version: 1.1.0
"""

import argparse
import atexit
import datetime
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.columns import Columns
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "1.1.0"

# ZFS Setup Defaults
DEFAULT_POOL_NAME = "tank"
DEFAULT_MOUNT_POINT = "/media/{pool_name}"
DEFAULT_CACHE_FILE = "/etc/zfs/zpool.cache"
DEFAULT_LOG_FILE = "/var/log/zfs_setup.log"

# Command preferences
APT_CMD = "apt"
if shutil.which("nala"):
    APT_CMD = "nala"  # Prefer nala if available

# Service configuration
ZFS_SERVICES = [
    "zfs-import-cache.service",
    "zfs-mount.service",
    "zfs-import.target",
    "zfs.target",
]

# Package dependencies
ZFS_PACKAGES = [
    "dpkg-dev",
    "linux-headers-generic",
    "linux-image-generic",
    "zfs-dkms",
    "zfsutils-linux",
]

REQUIRED_COMMANDS = [APT_CMD, "systemctl", "zpool", "zfs"]

# Progress tracking configuration
PROGRESS_WIDTH = 50
OPERATION_SLEEP = 0.05  # seconds

# Defaults for expansion validation
SIZE_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # in TiB (lower bound for a 2TB drive)
EXPECTED_SIZE_TIB_UPPER = 2.0  # in TiB (upper bound)

# Get terminal width but cap at reasonable size
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# Application name and subtitle for header
APP_NAME = "ZFS Manager"
APP_SUBTITLE = "Unified Pool Management"


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


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ZFSPool:
    """
    Represents a ZFS pool with its configuration and status details.

    Attributes:
        name: The pool name
        state: Current pool state (e.g., ONLINE, DEGRADED)
        mount_point: Configured mount point
        size: Total pool size in bytes
        vdevs: List of storage devices in this pool
        autoexpand: Whether autoexpand is enabled
        imported: Whether the pool is currently imported
    """

    name: str
    state: Optional[str] = None
    mount_point: Optional[str] = None
    size: Optional[int] = None
    vdevs: List[Dict[str, str]] = None
    autoexpand: Optional[bool] = None
    imported: bool = False

    def __post_init__(self):
        if self.vdevs is None:
            self.vdevs = []

    def get_primary_device(self) -> Optional[str]:
        """Returns the primary device path for expansion operations."""
        if not self.vdevs:
            return None
        return self.vdevs[0].get("path")

    def format_size(self) -> str:
        """Return human-readable size."""
        return bytes_to_human_readable(self.size)


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
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
      __                                                   
 ____/ _|___   _ __ ___   __ _ _ __   __ _  __ _  ___ _ __ 
|_  / |_/ __| | '_ ` _ \ / _` | '_ \ / _` |/ _` |/ _ \ '__|
 / /|  _\__ \ | | | | | | (_| | | | | (_| | (_| |  __/ |   
/___|_| |___/ |_| |_| |_|\__,_|_| |_|\__,_|\__, |\___|_|   
                                           |___/                  
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
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
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(message: str) -> None:
    """Print an informational message."""
    print_message(message, NordColors.FROST_3, "ℹ")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(text: str, step_num: int = None, total_steps: int = None) -> None:
    """Print a step description, optionally with step numbers."""
    step_info = (
        f"[{step_num}/{total_steps}] "
        if (step_num is not None and total_steps is not None)
        else ""
    )
    print_message(f"{step_info}{text}", NordColors.FROST_2, "→")


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
    """Pause execution until the user presses Enter."""
    console.input(f"\n[{NordColors.PURPLE}]Press Enter to continue...[/]")


# ----------------------------------------------------------------
# Formatting Helpers
# ----------------------------------------------------------------
def bytes_to_human_readable(bytes_val: Optional[int]) -> str:
    """Convert bytes to a human-readable format."""
    if bytes_val is None:
        return "N/A"
    if bytes_val == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(bytes_val)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


def convert_size_to_bytes(size_str: str) -> int:
    """Convert a human-readable size string to bytes."""
    size_str = size_str.upper().strip()
    if size_str in ["0", "0B", "-", "NONE"]:
        return 0
    if size_str[-1] in SIZE_UNITS:
        try:
            value = float(size_str[:-1])
            return int(value * SIZE_UNITS[size_str[-1]])
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")
    else:
        try:
            return int(size_str)
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes, secs = divmod(seconds, 60)
        return f"{int(minutes)}m {int(secs)}s"
    else:
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(secs)}s"


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(
    log_file: str = DEFAULT_LOG_FILE, log_level: int = logging.INFO
) -> None:
    """Configure logging to file and console."""
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=log_level,
            format="%(asctime)s - %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        try:
            os.chmod(log_file, 0o600)
            logging.info("Log file permissions set to 0600")
        except Exception as e:
            logging.warning(f"Could not set log file permissions: {e}")
        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add specific cleanup tasks here if needed
    logging.info("Cleanup completed")


atexit.register(cleanup)


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
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressBar:
    """Thread-safe progress bar with transfer rate and ETA display."""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = max(1, total)
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_update_value = 0
        self.rates = []
        self._lock = threading.Lock()
        self.completed = False
        self._display()

    def update(self, amount: int = 1) -> None:
        with self._lock:
            self.current = min(self.current + amount, self.total)
            now = time.time()
            if now - self.last_update_time >= 0.5:
                delta = self.current - self.last_update_value
                rate = delta / (now - self.last_update_time)
                self.rates.append(rate)
                if len(self.rates) > 5:
                    self.rates.pop(0)
                self.last_update_time = now
                self.last_update_value = self.current
            self._display()

    def finish(self) -> None:
        with self._lock:
            self.current = self.total
            self.completed = True
            self._display()
            console.print()

    def _display(self) -> None:
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100
        elapsed = time.time() - self.start_time
        avg_rate = sum(self.rates) / max(1, len(self.rates)) if self.rates else 0
        eta = (self.total - self.current) / max(0.1, avg_rate) if avg_rate > 0 else 0
        eta_str = format_time(eta)

        text = (
            f"\r[{NordColors.FROST_2}]{self.desc}:[/] |[{NordColors.FROST_4}]{bar}[/]| "
        )
        text += f"[{NordColors.SNOW_STORM_1}]{percent:5.1f}%[/] [ETA: {eta_str}]"

        console.print(text, end="")

        if self.completed:
            elapsed_str = format_time(elapsed)
            complete_text = f"\r[{NordColors.FROST_2}]{self.desc}:[/] |[{NordColors.FROST_4}]{bar}[/]| "
            complete_text += (
                f"[{NordColors.GREEN}]100.0%[/] [Completed in: {elapsed_str}]"
            )
            console.print(complete_text)


class Spinner:
    """Thread-safe spinner for indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = f"{elapsed:.1f}s"
            with self._lock:
                console.print(
                    f"\r[{NordColors.FROST_4}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_2}]{self.message}[/] [[dim]elapsed: {time_str}[/dim]]",
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

    def stop(self, success: bool = True, message: str = None) -> None:
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            console.print("\r" + " " * TERM_WIDTH, end="\r")
            completion_message = (
                message if message else ("Completed" if success else "Failed")
            )

            if success:
                console.print(
                    f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.GREEN}]{completion_message}[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.RED}]{completion_message}[/] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# Command Execution Helper Functions
# ----------------------------------------------------------------
def run_command(
    command: Union[str, List[str]],
    error_message: Optional[str] = None,
    check: bool = True,
    spinner_text: Optional[str] = None,
    capture_output: bool = True,
    env: Optional[Dict[str, str]] = None,
    verbose: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Run a shell command with error handling and an optional spinner.

    Args:
        command: Command to run (string or list)
        error_message: Custom error message if command fails
        check: Whether to raise exception on failure
        spinner_text: Text to display in spinner while command runs
        capture_output: Whether to capture stdout/stderr
        env: Additional environment variables
        verbose: Whether to print detailed information

    Returns:
        Tuple of (success, stdout, stderr)
    """
    if verbose:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        print_step(f"Executing: {cmd_str}")

    spinner = None
    if spinner_text and not verbose:
        spinner = Spinner(spinner_text)
        spinner.start()

    try:
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)

        if capture_output:
            result = subprocess.run(
                command,
                shell=isinstance(command, str),
                check=check,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=cmd_env,
            )
            stdout = result.stdout.strip() if result.stdout else None
            stderr = result.stderr.strip() if result.stderr else None
        else:
            result = subprocess.run(
                command,
                shell=isinstance(command, str),
                check=check,
                env=cmd_env,
            )
            stdout, stderr = None, None

        if spinner:
            spinner.stop(success=True)

        return True, stdout, stderr

    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip() if e.stderr else "No error output"

        if spinner:
            spinner.stop(success=False)

        if error_message:
            logging.error(f"{error_message}: {error_output}")
            if verbose:
                print_error(f"{error_message}: {error_output}")
        else:
            cmd_str = command if isinstance(command, str) else " ".join(command)
            logging.error(f"Command failed: {cmd_str}")
            logging.error(f"Error output: {error_output}")
            if verbose:
                print_error(f"Command failed: {cmd_str}")
                print_error(f"Error output: {error_output}")

        if check:
            raise

        return False, None, error_output

    except Exception as e:
        if spinner:
            spinner.stop(success=False)

        logging.error(f"Exception running command: {e}")
        if verbose:
            print_error(f"Exception running command: {e}")

        if check:
            raise

        return False, None, str(e)


def run_command_simple(
    command: Union[str, List[str]], verbose: bool = False
) -> Optional[str]:
    """Helper that runs a command and returns stdout if successful, else None."""
    success, stdout, _ = run_command(command, check=False, verbose=verbose)
    return stdout if success else None


# ----------------------------------------------------------------
# System Check Functions
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Check if the script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with sudo or as root.")
        return False
    return True


def check_dependencies(verbose: bool = False) -> bool:
    """Check if required commands are available on the system."""
    print_step("Checking required dependencies...")
    missing = []

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        console=console,
    ) as progress:
        check_task = progress.add_task("Checking", total=len(REQUIRED_COMMANDS))

        for cmd in REQUIRED_COMMANDS:
            if not shutil.which(cmd):
                missing.append(cmd)
            progress.advance(check_task)

    if missing:
        print_error(f"Missing required commands: {', '.join(missing)}")
        print_info("Please install the missing dependencies and try again.")
        return False

    print_success("All required dependencies are installed.")
    return True


def ensure_directory(path: str) -> bool:
    """Ensure that a directory exists."""
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False


# ----------------------------------------------------------------
# Package Management Functions
# ----------------------------------------------------------------
def install_packages(packages: List[str], verbose: bool = False) -> bool:
    """Install packages using the system package manager."""
    if not packages:
        return True

    package_str = " ".join(packages)
    print_step(f"Installing packages: {package_str}")

    success, _, _ = run_command(
        f"{APT_CMD} update",
        error_message="Failed to update package lists",
        check=False,
        spinner_text="Updating package lists",
        verbose=verbose,
    )

    if not success:
        print_warning("Failed to update package lists. Continuing anyway...")

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Installing packages"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        install_task = progress.add_task("Installing", total=len(packages))

        failed_packages = []
        for package in packages:
            success, _, _ = run_command(
                f"{APT_CMD} install -y {package}",
                error_message=f"Failed to install {package}",
                check=False,
                capture_output=True,
                verbose=verbose,
            )
            if not success:
                failed_packages.append(package)
            progress.advance(install_task)

    if failed_packages:
        print_warning(f"Failed to install: {', '.join(failed_packages)}")
        return False

    print_success("All packages installed successfully.")
    return True


def install_zfs_packages(verbose: bool = False) -> bool:
    """Install required ZFS packages."""
    print_step("Installing ZFS packages")
    return install_packages(ZFS_PACKAGES, verbose)


# ----------------------------------------------------------------
# ZFS Service Functions
# ----------------------------------------------------------------
def enable_zfs_services(verbose: bool = False) -> bool:
    """Enable required ZFS services."""
    print_step("Enabling ZFS services")

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Enabling services"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        console=console,
    ) as progress:
        service_task = progress.add_task("Enabling", total=len(ZFS_SERVICES))

        enabled_services = []
        failed_services = []

        for service in ZFS_SERVICES:
            success, _, _ = run_command(
                f"systemctl enable {service}",
                error_message=f"Failed to enable {service}",
                check=False,
                verbose=verbose,
            )

            if success:
                enabled_services.append(service)
            else:
                failed_services.append(service)

            progress.advance(service_task)

    if failed_services:
        print_warning(f"Failed to enable services: {', '.join(failed_services)}")
        return len(failed_services) < len(ZFS_SERVICES)

    print_success(f"Enabled services: {', '.join(enabled_services)}")
    return True


# ----------------------------------------------------------------
# ZFS Pool Functions
# ----------------------------------------------------------------
def create_mount_point(mount_point: str, verbose: bool = False) -> bool:
    """Create the mount point for the ZFS pool."""
    print_step(f"Creating mount point: {mount_point}")

    with Spinner("Creating mount point") as spinner:
        try:
            os.makedirs(mount_point, exist_ok=True)
            logging.info(f"Created mount point: {mount_point}")
            return True
        except Exception as e:
            logging.error(f"Failed to create mount point {mount_point}: {e}")
            if verbose:
                print_error(f"Error: {e}")
            return False


def list_available_pools(verbose: bool = False) -> List[str]:
    """List available ZFS pools for import."""
    print_step("Scanning for available ZFS pools")

    with Spinner("Scanning for available pools") as spinner:
        output = run_command_simple("zpool import", verbose)

    if not output:
        print_info("No available pools detected")
        return []

    pools = []
    for line in output.split("\n"):
        if line.startswith("   pool: "):
            pools.append(line.split("pool: ")[1].strip())

    if pools:
        print_info(f"Found {len(pools)} available pools: {', '.join(pools)}")
    else:
        print_info("No importable pools found")

    return pools


def is_pool_imported(pool_name: str, verbose: bool = False) -> bool:
    """Check if a ZFS pool is already imported."""
    with Spinner(f"Checking if pool '{pool_name}' is imported") as spinner:
        success, _, _ = run_command(
            f"zpool list {pool_name}",
            error_message=f"Pool {pool_name} is not imported",
            check=False,
            verbose=verbose,
        )

    if success:
        print_info(f"Pool '{pool_name}' is already imported")
    else:
        print_info(f"Pool '{pool_name}' is not currently imported")

    return success


def import_zfs_pool(pool_name: str, force: bool = False, verbose: bool = False) -> bool:
    """Import a ZFS pool."""
    print_step(f"Importing ZFS pool '{pool_name}'")

    if is_pool_imported(pool_name, verbose):
        print_success(f"ZFS pool '{pool_name}' is already imported")
        return True

    force_flag = "-f" if force else ""

    with Spinner(f"Importing ZFS pool '{pool_name}'") as spinner:
        success, _, stderr = run_command(
            f"zpool import {force_flag} {pool_name}",
            error_message=f"Failed to import ZFS pool '{pool_name}'",
            check=False,
            verbose=verbose,
        )

    if success:
        print_success(f"Successfully imported ZFS pool '{pool_name}'")
        return True
    else:
        print_error(f"Failed to import ZFS pool '{pool_name}'")
        if stderr:
            print_error(f"Error details: {stderr}")

        available = list_available_pools(verbose)
        if available:
            print_info(f"Available pools: {', '.join(available)}")
            print_info("You can specify one of these pools with the --pool-name option")
        else:
            print_info("No available pools found for import")

        return False


def configure_zfs_pool(
    pool_name: str, mount_point: str, cache_file: str, verbose: bool = False
) -> bool:
    """Configure a ZFS pool with the proper mountpoint and cachefile."""
    print_step(f"Configuring ZFS pool '{pool_name}'")

    # Set mountpoint
    with Spinner(f"Setting mountpoint to '{mount_point}'") as spinner:
        success, _, stderr = run_command(
            f"zfs set mountpoint={mount_point} {pool_name}",
            error_message=f"Failed to set mountpoint for '{pool_name}'",
            check=False,
            verbose=verbose,
        )

    if not success:
        print_error(f"Failed to set mountpoint for '{pool_name}'")
        if stderr:
            print_error(f"Error details: {stderr}")
        return False

    print_success(f"Set mountpoint for '{pool_name}' to '{mount_point}'")

    # Set cachefile
    with Spinner(f"Setting cachefile to '{cache_file}'") as spinner:
        # Make sure the parent directory exists
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        success, _, stderr = run_command(
            f"zpool set cachefile={cache_file} {pool_name}",
            error_message=f"Failed to set cachefile for '{pool_name}'",
            check=False,
            verbose=verbose,
        )

    if not success:
        print_error(f"Failed to set cachefile for '{pool_name}'")
        if stderr:
            print_error(f"Error details: {stderr}")
        print_warning(
            "Pool was imported but cachefile was not set. Automatic mounting on boot may not work"
        )
        return False

    print_success(f"Set cachefile for '{pool_name}' to '{cache_file}'")
    return True


def mount_zfs_datasets(verbose: bool = False) -> bool:
    """Mount all ZFS datasets."""
    print_step("Mounting ZFS datasets")

    with Spinner("Mounting all ZFS datasets") as spinner:
        success, _, stderr = run_command(
            "zfs mount -a",
            error_message="Failed to mount ZFS datasets",
            check=False,
            verbose=verbose,
        )

    if success:
        print_success("All ZFS datasets mounted successfully")
        return True
    else:
        print_warning("Some ZFS datasets may not have mounted")
        if stderr:
            print_warning(f"Error details: {stderr}")
        return False


def verify_mount(pool_name: str, mount_point: str, verbose: bool = False) -> bool:
    """Verify that a ZFS pool is mounted at the expected mount point."""
    print_step("Verifying ZFS mount points")

    with Spinner("Verifying mount status") as spinner:
        success, stdout, _ = run_command(
            "zfs list -o name,mountpoint -H",
            error_message="Failed to list ZFS filesystems",
            check=False,
            verbose=verbose,
        )

    if not success:
        print_error("Failed to verify mount status")
        return False

    pool_found = False
    correct_mount = False
    actual_mount = None

    for line in stdout.splitlines():
        try:
            fs_name, fs_mount = line.split("\t")
            if fs_name == pool_name:
                pool_found = True
                actual_mount = fs_mount
                if fs_mount == mount_point:
                    correct_mount = True
                    break
        except ValueError:
            continue

    if pool_found and correct_mount:
        print_success(f"ZFS pool '{pool_name}' is mounted at '{mount_point}'")
        return True
    elif pool_found:
        print_warning(
            f"ZFS pool '{pool_name}' is mounted at '{actual_mount}' (expected: '{mount_point}')"
        )
        return False
    else:
        print_error(f"ZFS pool '{pool_name}' is not mounted")

        # Show current mounts for context
        print_info("Current ZFS mounts:")
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
        )
        table.add_column("Dataset", style=f"bold {NordColors.FROST_2}")
        table.add_column("Mount Point", style=NordColors.SNOW_STORM_1)

        for line in stdout.splitlines():
            try:
                fs_name, fs_mount = line.split("\t")
                table.add_row(fs_name, fs_mount)
            except ValueError:
                continue

        console.print(table)
        return False


def show_zfs_status(pool_name: str, verbose: bool = False) -> None:
    """Display the status and properties of a ZFS pool."""
    print_step(f"Retrieving status for ZFS pool '{pool_name}'")

    # Get pool status
    success, stdout, _ = run_command(
        f"zpool status {pool_name}",
        error_message=f"Failed to get status for pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )

    if success and stdout:
        display_panel(stdout, NordColors.FROST_3, "Pool Status")
    else:
        print_warning(f"Could not get pool status for '{pool_name}'")

    # Get important properties
    success, stdout, _ = run_command(
        f"zpool get all {pool_name}",
        error_message=f"Failed to get properties for pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )

    if success and stdout:
        important_props = [
            "size",
            "capacity",
            "health",
            "fragmentation",
            "free",
            "allocated",
            "autoexpand",
        ]

        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
            title=f"[bold {NordColors.FROST_2}]Important Pool Properties[/]",
            title_justify="center",
        )

        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)
        table.add_column("Source", style=NordColors.SNOW_STORM_2)

        for line in stdout.splitlines():
            for prop in important_props:
                if f"{pool_name}\t{prop}\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        table.add_row(parts[1], parts[2], parts[3])

        console.print(table)
    else:
        print_warning(f"Could not get pool properties for '{pool_name}'")


# ----------------------------------------------------------------
# ZFS Pool Expansion Functions
# ----------------------------------------------------------------
def get_zpool_status(
    verbose: bool = False,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Retrieve detailed status information about ZFS pools."""
    output = run_command_simple("zpool status", verbose)
    if not output:
        return None

    pool_info = {"pools": []}
    current_pool = None
    pool_name_regex = re.compile(r"pool:\s+(.+)")
    state_regex = re.compile(r"state:\s+(.+)")
    capacity_regex = re.compile(
        r"capacity:.+allocatable\s+([\d.]+)([KMGTP]?)", re.IGNORECASE
    )

    for line in output.splitlines():
        line = line.strip()
        pool_match = pool_name_regex.match(line)

        if pool_match:
            pool_name = pool_match.group(1).strip()
            current_pool = {"name": pool_name, "vdevs": [], "allocatable": None}
            pool_info["pools"].append(current_pool)
            continue

        if current_pool:
            state_match = state_regex.match(line)
            if state_match:
                current_pool["state"] = state_match.group(1).strip()
                continue

            if line.startswith("NAME") and "STATE" in line:
                continue

            if line and not any(
                line.startswith(prefix)
                for prefix in ("errors:", "config:", "capacity:")
            ):
                parts = line.split()
                if len(parts) >= 2 and parts[1] in [
                    "ONLINE",
                    "DEGRADED",
                    "OFFLINE",
                    "FAULTED",
                    "REMOVED",
                    "UNAVAIL",
                ]:
                    current_pool["vdevs"].append(
                        {"type": "disk", "path": parts[0], "state": parts[1]}
                    )
                    continue

            capacity_match = capacity_regex.search(line)
            if capacity_match:
                size_value = float(capacity_match.group(1))
                size_unit = (
                    capacity_match.group(2).upper() if capacity_match.group(2) else ""
                )
                multiplier = SIZE_UNITS.get(size_unit, 1)
                current_pool["allocatable"] = int(size_value * multiplier)

    return pool_info


def get_zfs_list(verbose: bool = False) -> Optional[List[Dict[str, str]]]:
    """Get a list of all ZFS datasets and their properties."""
    output = run_command_simple(
        "zfs list -o name,used,available,refer,mountpoint -t all -H", verbose
    )

    if not output:
        return None

    datasets = []
    for line in output.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 5:
            datasets.append(
                {
                    "name": parts[0],
                    "used": parts[1],
                    "available": parts[2],
                    "refer": parts[3],
                    "mountpoint": parts[4],
                }
            )

    return datasets


def set_autoexpand_property(pool_name: str, verbose: bool = False) -> bool:
    """Enable the autoexpand property on a ZFS pool."""
    print_step(f"Checking autoexpand property for pool '{pool_name}'")

    with Spinner("Checking autoexpand property") as spinner:
        current_output = run_command_simple(
            f"zpool get autoexpand {pool_name}", verbose
        )

    if not current_output:
        print_error("Failed to get autoexpand property")
        return False

    autoexpand_value = None
    match = re.search(rf"{re.escape(pool_name)}\s+autoexpand\s+(\S+)", current_output)

    if match:
        autoexpand_value = match.group(1).strip()
    else:
        if "on" in current_output.lower():
            autoexpand_value = "on"
        elif "off" in current_output.lower():
            autoexpand_value = "off"

    if autoexpand_value is None:
        print_warning(f"Could not parse autoexpand value from: '{current_output}'")
        return False

    if autoexpand_value != "on":
        print_step(f"autoexpand is '{autoexpand_value}'. Enabling it...")

        with Spinner("Enabling autoexpand property") as spinner:
            success = (
                run_command_simple(f"zpool set autoexpand=on {pool_name}", verbose)
                is not None
            )

        if success:
            print_success("autoexpand property enabled")
            return True
        else:
            print_error("Failed to enable autoexpand property")
            return False
    else:
        print_success("autoexpand is already enabled")
        return True


def verify_pool_resize(pool_name: str, verbose: bool = False) -> bool:
    """Verify that a pool has been resized successfully."""
    print_step("Retrieving initial pool status...")

    with Spinner("Getting initial pool size") as spinner:
        initial_status = get_zpool_status(verbose)

    if not initial_status:
        print_error("Failed to retrieve initial zpool status")
        return False

    initial_pool = next(
        (p for p in initial_status["pools"] if p["name"] == pool_name), None
    )

    if not initial_pool:
        print_error(f"Pool '{pool_name}' not found in initial status")
        return False

    initial_size = initial_pool.get("allocatable")
    print_info(
        f"Initial allocatable pool size: {bytes_to_human_readable(initial_size)}"
    )

    print_step(f"Waiting {WAIT_TIME_SECONDS} seconds for background resizing...")

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Waiting for resizing"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        wait_task = progress.add_task("Waiting", total=WAIT_TIME_SECONDS)

        for _ in range(WAIT_TIME_SECONDS):
            time.sleep(1)
            progress.advance(wait_task)

    print_step("Retrieving final pool status...")

    with Spinner("Getting final pool size") as spinner:
        final_status = get_zpool_status(verbose)

    if not final_status:
        print_error("Failed to retrieve final zpool status")
        return False

    final_pool = next(
        (p for p in final_status["pools"] if p["name"] == pool_name), None
    )

    if not final_pool:
        print_error(f"Pool '{pool_name}' not found in final status")
        return False

    final_size = final_pool.get("allocatable")
    print_info(f"Final allocatable pool size: {bytes_to_human_readable(final_size)}")

    if final_size is None or initial_size is None:
        print_error("Could not compare pool sizes due to parsing issues")
        return False

    if final_size >= initial_size:
        print_success(
            f"Pool '{pool_name}' successfully resized (or already fully expanded)"
        )
        if final_size > initial_size:
            print_success(
                f"Size increased by: {bytes_to_human_readable(final_size - initial_size)}"
            )
        return True
    else:
        print_warning(
            f"Pool size appears to have decreased from {bytes_to_human_readable(initial_size)} to {bytes_to_human_readable(final_size)}"
        )
        return False


def expand_zpool(pool_name: str, device_path: str, verbose: bool = False) -> bool:
    """Expand a ZFS pool to use the full size of its underlying device."""
    total_steps = 3

    # Step 1: Enable autoexpand
    print_step("Step 1: Enabling autoexpand property...", 1, total_steps)
    if not set_autoexpand_property(pool_name, verbose):
        print_warning("Could not set autoexpand property. Continuing anyway...")

    # Step 2: Initiate online expansion
    print_step("Step 2: Initiating online expansion...", 2, total_steps)

    with Spinner(f"Expanding device '{device_path}'") as spinner:
        success = (
            run_command_simple(f"zpool online -e {pool_name} {device_path}", verbose)
            is not None
        )

    if not success:
        print_error(
            f"Failed to initiate online expansion for '{device_path}' in pool '{pool_name}'"
        )
        return False

    print_success(
        f"Online expansion initiated for '{device_path}' in pool '{pool_name}'"
    )

    # Step 3: Verify resize
    print_step("Step 3: Verifying pool resize...", 3, total_steps)
    return verify_pool_resize(pool_name, verbose)


def validate_expansion(verbose: bool = False) -> bool:
    """Validate the results of a ZFS pool expansion."""
    print_step("Validating ZFS expansion results")

    with Spinner("Gathering pool information") as spinner:
        zpool_info = get_zpool_status(verbose)
        zfs_datasets = get_zfs_list(verbose)

    if not zpool_info or not zfs_datasets:
        print_error("Failed to retrieve pool or dataset information for validation")
        return False

    # Find the pool size
    total_pool_size = None
    if zpool_info["pools"]:
        pool_to_check = next(
            (p for p in zpool_info["pools"] if p["name"] == "rpool"),
            zpool_info["pools"][0],
        )
        total_pool_size = pool_to_check.get("allocatable")

    print_info(f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size)}")

    # Calculate total space across datasets
    total_used = 0
    total_available = 0

    # Create a table of datasets
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]ZFS Datasets Summary[/]",
        title_justify="center",
    )

    table.add_column("Dataset", style=f"bold {NordColors.FROST_2}")
    table.add_column("Used", style=NordColors.SNOW_STORM_1)
    table.add_column("Available", style=NordColors.SNOW_STORM_1)
    table.add_column("Mountpoint", style=NordColors.SNOW_STORM_2)

    for dataset in zfs_datasets:
        table.add_row(
            dataset["name"],
            dataset["used"],
            dataset["available"],
            dataset["mountpoint"],
        )

        try:
            total_used += convert_size_to_bytes(dataset["used"])
        except ValueError:
            print_warning(
                f"Could not parse used space '{dataset['used']}' for dataset {dataset['name']}"
            )

        if dataset["available"] != "-":
            try:
                total_available += convert_size_to_bytes(dataset["available"])
            except ValueError:
                print_warning(
                    f"Could not parse available space '{dataset['available']}' for dataset {dataset['name']}"
                )

    console.print(table)

    # Display summary
    summary_panel = Panel(
        Text.from_markup(
            f"Total Used Space: [{NordColors.FROST_2}]{bytes_to_human_readable(total_used)}[/]\n"
            f"Total Available Space: [{NordColors.FROST_2}]{bytes_to_human_readable(total_available)}[/]\n"
            f"Total Pool Size: [{NordColors.FROST_2}]{bytes_to_human_readable(total_pool_size)}[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]Expansion Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(summary_panel)

    # Validate against expected size
    expected_lower = EXPECTED_SIZE_TIB_LOWER * (1024**4)
    if total_pool_size is not None and total_pool_size > expected_lower:
        print_success(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is within expected range for a 2TB drive"
        )
        return True
    else:
        print_warning(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is smaller than expected for a 2TB drive"
        )
        return False


# ----------------------------------------------------------------
# Interactive ZFS Setup Function
# ----------------------------------------------------------------
def interactive_setup() -> Tuple[str, str, str, bool]:
    """Run interactive setup to gather ZFS configuration parameters."""
    print_step("Starting interactive ZFS setup")

    # Check for available pools first
    available_pools = list_available_pools()

    if available_pools:
        print_info(f"Available ZFS pools: {', '.join(available_pools)}")
        pool_name = (
            console.input(
                f"[bold {NordColors.FROST_2}]Enter pool name [{DEFAULT_POOL_NAME}]: [/]"
            ).strip()
            or DEFAULT_POOL_NAME
        )
    else:
        print_info("No available pools detected. Specify the pool name manually.")
        pool_name = (
            console.input(
                f"[bold {NordColors.FROST_2}]Enter pool name [{DEFAULT_POOL_NAME}]: [/]"
            ).strip()
            or DEFAULT_POOL_NAME
        )

    # Get mount point
    default_mount = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    mount_point = (
        console.input(
            f"[bold {NordColors.FROST_2}]Enter mount point [{default_mount}]: [/]"
        ).strip()
        or default_mount
    )

    # Get cache file
    cache_file = (
        console.input(
            f"[bold {NordColors.FROST_2}]Enter cache file path [{DEFAULT_CACHE_FILE}]: [/]"
        ).strip()
        or DEFAULT_CACHE_FILE
    )

    # Force option
    force_input = console.input(
        f"[bold {NordColors.FROST_2}]Force import if needed? (y/N): [/]"
    )
    force = force_input.lower() in ("y", "yes")

    # Show summary panel
    summary_panel = Panel(
        Text.from_markup(
            f"Pool name:    [{NordColors.FROST_2}]{pool_name}[/]\n"
            f"Mount point:  [{NordColors.FROST_2}]{mount_point}[/]\n"
            f"Cache file:   [{NordColors.FROST_2}]{cache_file}[/]\n"
            f"Force import: [{NordColors.FROST_2}]{'Yes' if force else 'No'}[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]Configuration Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(summary_panel)

    # Confirm
    confirm = console.input(
        f"[bold {NordColors.FROST_2}]Proceed with this configuration? (Y/n): [/]"
    )

    if confirm.lower() in ("n", "no"):
        print_info("Setup cancelled by user.")
        sys.exit(0)

    return pool_name, mount_point, cache_file, force


# ----------------------------------------------------------------
# Main ZFS Setup Function
# ----------------------------------------------------------------
def execute_zfs_setup(args) -> bool:
    """
    Execute the complete ZFS setup process.
    Returns True if setup is successful, False otherwise.
    """
    pool_name = args.pool_name
    mount_point = args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    cache_file = args.cache_file
    force = args.force
    verbose = args.verbose

    total_steps = 6
    current_step = 0

    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logging(args.log_file, log_level)

    start_time = datetime.datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        # Step 1: Check dependencies
        current_step += 1
        print_step("Checking system dependencies", current_step, total_steps)
        if not check_dependencies(verbose):
            return False

        # Step 2: Install packages (if not skipped)
        current_step += 1
        if not args.skip_install:
            print_step("Installing ZFS packages", current_step, total_steps)
            if not install_zfs_packages(verbose):
                print_warning("ZFS package installation had issues, but continuing...")
        else:
            print_step(
                "Skipping ZFS package installation (--skip-install)",
                current_step,
                total_steps,
            )

        # Step 3: Enable services
        current_step += 1
        print_step("Enabling ZFS services", current_step, total_steps)
        enable_zfs_services(verbose)

        # Step 4: Create mount point
        current_step += 1
        print_step(f"Creating mount point: {mount_point}", current_step, total_steps)
        if not create_mount_point(mount_point, verbose):
            return False

        # Step 5: Import pool
        current_step += 1
        print_step(f"Importing ZFS pool: {pool_name}", current_step, total_steps)
        if not import_zfs_pool(pool_name, force, verbose):
            return False

        # Step 6: Configure pool
        current_step += 1
        print_step(f"Configuring ZFS pool: {pool_name}", current_step, total_steps)
        if not configure_zfs_pool(pool_name, mount_point, cache_file, verbose):
            print_warning("Pool configuration had issues, but continuing...")

        # Extra step: Mount datasets
        print_step("Mounting ZFS datasets", current_step, total_steps)
        mount_zfs_datasets(verbose)

        # Extra step: Verify mount
        print_step("Verifying ZFS mount", current_step, total_steps)
        if not verify_mount(pool_name, mount_point, verbose):
            print_warning("ZFS mount verification failed. Check mount status manually.")

        # Show pool status
        show_zfs_status(pool_name, verbose)
        return True

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        print_error(f"Setup failed: {e}")
        return False


# ----------------------------------------------------------------
# Command Line Parsing
# ----------------------------------------------------------------
def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified ZFS Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run setup with default options
  sudo python3 zfs_management.py setup

  # Run interactive setup
  sudo python3 zfs_management.py setup --interactive

  # Setup with custom pool name and mount point
  sudo python3 zfs_management.py setup --pool-name mypool --mount-point /data/mypool

  # Expand pools
  sudo python3 zfs_management.py expand
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Configure and import ZFS pools")
    setup_parser.add_argument(
        "--pool-name", default=DEFAULT_POOL_NAME, help="Name of the ZFS pool to import"
    )
    setup_parser.add_argument(
        "--mount-point",
        default=None,
        help="Mount point for the ZFS pool (default: /media/{pool_name})",
    )
    setup_parser.add_argument(
        "--cache-file", default=DEFAULT_CACHE_FILE, help="Path to the ZFS cache file"
    )
    setup_parser.add_argument(
        "--log-file", default=DEFAULT_LOG_FILE, help="Path to the log file"
    )
    setup_parser.add_argument(
        "--force", action="store_true", help="Force import of the ZFS pool"
    )
    setup_parser.add_argument(
        "--skip-install", action="store_true", help="Skip package installation"
    )
    setup_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    setup_parser.add_argument(
        "--interactive", action="store_true", help="Run interactive setup"
    )

    # Expand command
    expand_parser = subparsers.add_parser(
        "expand", help="Expand ZFS pools to use full device size"
    )
    expand_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"Unified ZFS Management Script v{VERSION}",
    )
    return parser.parse_args()


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the Unified ZFS Management Script."""
    try:
        args = parse_arguments()
        if not args.command:
            clear_screen()
            console.print(create_header())
            print_error("No command specified.")
            print_info(
                "Use 'setup' or 'expand' command. See --help for more information."
            )
            sys.exit(1)

        clear_screen()
        console.print(create_header())

        if args.command == "setup":
            if not check_root_privileges():
                sys.exit(1)

            if not run_command_simple("modprobe zfs"):
                print_warning(
                    "ZFS kernel module could not be loaded. You may need to install ZFS packages first."
                )

            if args.interactive:
                try:
                    args.pool_name, args.mount_point, args.cache_file, args.force = (
                        interactive_setup()
                    )
                except KeyboardInterrupt:
                    print_warning("Setup cancelled by user.")
                    sys.exit(130)

            # Execute setup process
            start_time = time.time()
            success = execute_zfs_setup(args)
            elapsed = time.time() - start_time

            # Show summary
            summary_panel = Panel(
                Text.from_markup(
                    f"Status: [{NordColors.GREEN if success else NordColors.RED}]{'Successful' if success else 'Failed'}[/]\n"
                    f"Pool name: [{NordColors.FROST_2}]{args.pool_name}[/]\n"
                    f"Mount point: [{NordColors.FROST_2}]{args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=args.pool_name)}[/]\n"
                    f"Elapsed time: [{NordColors.FROST_2}]{format_time(elapsed)}[/]\n"
                    f"Log file: [{NordColors.FROST_2}]{args.log_file}[/]"
                ),
                title=f"[bold {NordColors.FROST_2}]ZFS Setup Summary[/]",
                border_style=Style(color=NordColors.FROST_3),
                padding=(1, 2),
            )
            console.print(summary_panel)

            if success:
                # Show next steps
                next_steps_panel = Panel(
                    Text.from_markup(
                        f"Your ZFS pool is now configured and imported.\n\n"
                        f"Access your data at: [{NordColors.FROST_2}]{args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=args.pool_name)}[/]\n\n"
                        f"Helpful ZFS commands:\n"
                        f"  [bold {NordColors.FROST_2}]zfs list[/]              - List ZFS filesystems\n"
                        f"  [bold {NordColors.FROST_2}]zpool status {args.pool_name}[/]  - Show pool status\n"
                        f"  [bold {NordColors.FROST_2}]zfs get all {args.pool_name}[/]   - Show all properties"
                    ),
                    title=f"[bold {NordColors.FROST_2}]Next Steps[/]",
                    border_style=Style(color=NordColors.FROST_3),
                    padding=(1, 2),
                )
                console.print(next_steps_panel)

            sys.exit(0 if success else 1)

        elif args.command == "expand":
            if not check_root_privileges():
                sys.exit(1)

            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print_info(f"Started at: {current_time}")

            pool_status = get_zpool_status(args.verbose)
            if not pool_status or not pool_status["pools"]:
                print_error(
                    "Could not retrieve ZFS pool status or no pools found. Ensure ZFS is configured."
                )
                sys.exit(1)

            pools = pool_status["pools"]
            expected_pools = ["bpool", "rpool"]
            found_pools = [p["name"] for p in pools]

            if set(found_pools) != set(expected_pools):
                print_warning(
                    f"Expected pools {expected_pools} but found {found_pools}. Proceed with caution."
                )

            # Find devices for each pool
            pool_device_paths = {}
            for pool in pools:
                pool_name = pool["name"]
                vdevs = pool.get("vdevs", [])

                if not vdevs:
                    print_warning(f"No vdevs found for pool '{pool_name}'. Skipping.")
                    continue

                device_path = vdevs[0].get("path")
                if not device_path:
                    print_warning(
                        f"Could not determine device for pool '{pool_name}'. Skipping."
                    )
                    continue

                pool_device_paths[pool_name] = device_path

            # Display detected pools and devices
            if pool_device_paths:
                table = Table(
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                    border_style=NordColors.FROST_3,
                    title=f"[bold {NordColors.FROST_2}]Detected ZFS Pools and Devices[/]",
                    title_justify="center",
                )

                table.add_column("Pool", style=f"bold {NordColors.FROST_2}")
                table.add_column("Device", style=NordColors.SNOW_STORM_1)

                for name, dev in pool_device_paths.items():
                    table.add_row(name, dev)

                console.print(table)
            else:
                print_error("No valid pool-device pairs found. Aborting expansion.")
                sys.exit(1)

            # Expand each pool
            print_step("Starting ZFS Pool Expansion Process")
            expansion_results = {}

            for pool_name, device_path in pool_device_paths.items():
                panel = Panel(
                    f"Pool: {pool_name}\nDevice: {device_path}",
                    title=f"[bold {NordColors.FROST_2}]Expanding Pool[/]",
                    border_style=Style(color=NordColors.FROST_3),
                    padding=(1, 2),
                )
                console.print(panel)

                result = expand_zpool(pool_name, device_path, args.verbose)
                expansion_results[pool_name] = result
                console.print()

            # Validate expansion
            print_step("Validating Expansion Results")
            validation = validate_expansion(args.verbose)

            # Show results summary
            results_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                border_style=NordColors.FROST_3,
                title=f"[bold {NordColors.FROST_2}]Expansion Results Summary[/]",
                title_justify="center",
            )

            results_table.add_column("Pool", style=f"bold {NordColors.FROST_2}")
            results_table.add_column("Result", style=NordColors.SNOW_STORM_1)

            for pool_name, result in expansion_results.items():
                status_text = (
                    f"[bold {NordColors.GREEN}]Successful[/]"
                    if result
                    else f"[bold {NordColors.RED}]Failed[/]"
                )
                results_table.add_row(pool_name, status_text)

            # Add validation result
            overall = (
                "Successful"
                if all(expansion_results.values()) and validation
                else "Failed"
            )
            overall_color = (
                NordColors.GREEN if overall == "Successful" else NordColors.RED
            )
            results_table.add_row(
                "Overall Validation", f"[bold {overall_color}]{overall}[/]"
            )

            console.print(results_table)

            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print_info(f"Completed at: {current_time}")

            sys.exit(0 if all(expansion_results.values()) and validation else 1)

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(130)

    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(0)
    except Exception as e:
        display_panel(f"Unhandled error: {str(e)}", style=NordColors.RED, title="Error")
        console.print_exception()
        sys.exit(1)
