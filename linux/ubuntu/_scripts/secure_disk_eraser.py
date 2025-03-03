#!/usr/bin/env python3
"""
Enhanced Disk Eraser Tool
--------------------------------------------------

This utility securely erases disk devices using various methods (zeros, random data,
DoD-compliant). It provides detailed progress tracking, error handling, and a Nord-themed
user interface. This tool provides a complete solution for securely wiping disks on Linux systems.

Usage:
  Run the script with root privileges and follow the interactive menu prompts:
  - List available disks
  - View detailed disk information
  - Securely erase disks with various methods
  - Exit the application

Note: This script must be run with root privileges.
Version: 2.0.0 | License: MIT
"""

import atexit
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.align import Align
    from rich.style import Style
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )
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
HOSTNAME = socket.gethostname()
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
PROGRESS_WIDTH = 40
CHUNK_SIZE = 1024 * 1024  # 1MB for progress updates
LOG_FILE = "/var/log/disk_eraser.log"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
OPERATION_TIMEOUT = 60  # seconds
VERSION = "2.0.0"
APP_NAME = "Disk Eraser"
APP_SUBTITLE = "Secure Data Destruction Tool"

# Erasure method configurations
ERASURE_METHODS: Dict[str, Dict[str, Any]] = {
    "zeros": {
        "name": "Zeros",
        "description": "Overwrite disk with zeros (fast)",
        "command": "dd",
        "args": ["if=/dev/zero", "bs=4M", "conv=fsync,noerror"],
    },
    "random": {
        "name": "Random Data",
        "description": "Overwrite disk with random data (secure)",
        "command": "dd",
        "args": ["if=/dev/urandom", "bs=4M", "conv=fsync,noerror"],
    },
    "dod": {
        "name": "DoD 3-pass",
        "description": "DoD-compliant 3-pass wipe (most secure)",
        "command": "shred",
        "args": ["-n", "3", "-z", "-v"],
    },
}
DEFAULT_METHOD = "zeros"
DEFAULT_PASSES = 1


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

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
console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class DiskDevice:
    """
    Represents a physical disk device with its properties and status.

    Attributes:
        name: The device name (e.g., sda)
        path: Full device path (e.g., /dev/sda)
        size: Size in bytes
        model: Device model or manufacturer
        size_human: Human-readable size
        is_system: Whether this appears to be a system disk
        type: Type of disk (HDD, SSD, NVMe)
        mounted: Whether any partitions are mounted
    """

    def __init__(self, name: str, path: str, size: int, model: str = ""):
        self.name = name
        self.path = path
        self.size = size
        self.model = model
        self.size_human = format_size(size)
        self.is_system = is_system_disk(name)
        self.type = detect_disk_type(name)
        self.mounted = is_mounted(path)

    def __str__(self) -> str:
        return f"{self.name} ({self.size_human}, {self.type})"


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
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
                                    _ _     _    
 ___  ___  ___ _   _ _ __ ___    __| (_)___| | __
/ __|/ _ \/ __| | | | '__/ _ \  / _` | / __| |/ /
\__ \  __/ (__| |_| | | |  __/ | (_| | \__ \   < 
|___/\___|\___|\__,_|_|  \___|  \__,_|_|___/_|\_\
  ___ _ __ __ _ ___  ___ _ __                    
 / _ \ '__/ _` / __|/ _ \ '__|                   
|  __/ | | (_| \__ \  __/ |                      
 \___|_|  \__,_|___/\___|_|                      
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
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
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_2, "•")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * min(TERM_WIDTH, 80)
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{title.center(min(TERM_WIDTH, 80))}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")


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
# Utility Functions
# ----------------------------------------------------------------
def format_size(num_bytes: float) -> str:
    """Convert a byte value to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
    """Convert seconds into a human-readable time string."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    elif minutes:
        return f"{minutes:02d}:{secs:02d}"
    else:
        return f"{secs:02d} sec"


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure logging to both console and a rotating log file."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    try:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Could not set up log file: {e}")
        logger.warning("Continuing with console logging only")


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
    """
    try:
        logging.debug(f"Executing: {' '.join(cmd)}")
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
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    logging.info("Cleanup completed")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    logging.error(f"Script interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Validation Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """Check if the script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        print_message("Please run with sudo or as root.", NordColors.SNOW_STORM_1)
        return False
    return True


def check_dependencies() -> bool:
    """Ensure required external commands are available."""
    required = ["lsblk", "dd", "shred"]
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        print_error(f"Missing required dependencies: {', '.join(missing)}")
        print_message(
            "Please install them using your package manager.", NordColors.SNOW_STORM_1
        )
        return False
    return True


def is_valid_device(device_path: str) -> bool:
    """Validate that the provided path is a block device."""
    if not os.path.exists(device_path):
        print_error(f"Device not found: {device_path}")
        return False
    if not os.path.isabs(device_path):
        print_error("Device path must be absolute.")
        return False

    device_name = os.path.basename(device_path)
    if not os.path.exists(f"/sys/block/{device_name}") and not any(
        os.path.exists(f"/sys/block/{bd}/{device_name}")
        for bd in os.listdir("/sys/block")
    ):
        print_error(f"{device_path} is not recognized as a block device.")
        return False
    return True


# ----------------------------------------------------------------
# Disk Management Functions
# ----------------------------------------------------------------
def list_disks() -> List[DiskDevice]:
    """
    List all block devices using lsblk with JSON output.

    Returns:
        List of DiskDevice objects representing available block devices
    """
    try:
        output = run_command(
            ["lsblk", "-d", "-b", "-o", "NAME,SIZE,MODEL,TYPE", "--json"],
            capture_output=True,
        )
        data = json.loads(output.stdout)
        disks = []

        for disk_data in data.get("blockdevices", []):
            if disk_data.get("type") != "disk":
                continue

            name = disk_data.get("name", "")
            path = f"/dev/{name}"
            size = int(disk_data.get("size", 0))
            model = disk_data.get("model", "").strip() or "Unknown"

            disks.append(DiskDevice(name, path, size, model))

        return disks
    except Exception as e:
        logging.error(f"Error listing disks: {e}")
        print_error(f"Failed to list disks: {e}")
        return []


def detect_disk_type(disk: str) -> str:
    """
    Detect whether a disk is NVMe, HDD, or SSD.

    Args:
        disk: Disk name (e.g., 'sda')

    Returns:
        String indicating disk type: 'NVMe', 'SSD', 'HDD', or 'Unknown'
    """
    try:
        if disk.startswith("nvme"):
            return "NVMe"
        rotational_path = f"/sys/block/{disk}/queue/rotational"
        if os.path.exists(rotational_path):
            with open(rotational_path, "r") as f:
                return "HDD" if f.read().strip() == "1" else "SSD"
        return "Unknown"
    except Exception:
        return "Unknown"


def is_system_disk(disk: str) -> bool:
    """
    Check if the disk is likely the system disk.

    Args:
        disk: Disk name (e.g., 'sda')

    Returns:
        True if this appears to be a system disk, False otherwise
    """
    try:
        result = run_command(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True,
        )
        root_device = result.stdout.strip()
        if root_device.startswith("/dev/"):
            root_device = root_device[5:]
        base = re.sub(r"\d+$", "", root_device)
        return disk == base
    except Exception:
        # If we can't determine, better safe than sorry
        return True


def is_mounted(disk: str) -> bool:
    """
    Check if a disk or its partitions are mounted.

    Args:
        disk: Disk path (e.g., '/dev/sda')

    Returns:
        True if the disk or any of its partitions are mounted
    """
    try:
        output = run_command(["mount"], capture_output=True)
        if disk in output.stdout:
            return True

        disk_name = os.path.basename(disk)
        output = run_command(
            ["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True
        )

        for line in output.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                return True

        return False
    except Exception as e:
        logging.error(f"Error checking mount status: {e}")
        # If we can't determine, assume it's mounted to be safe
        return True


def get_disk_size(disk: str) -> int:
    """
    Return disk size in bytes.

    Args:
        disk: Disk path (e.g., '/dev/sda')

    Returns:
        Size in bytes
    """
    try:
        disk_name = os.path.basename(disk)
        size_path = f"/sys/block/{disk_name}/size"
        if os.path.exists(size_path):
            with open(size_path, "r") as f:
                return int(f.read().strip()) * 512

        output = run_command(
            ["lsblk", "-b", "-d", "-n", "-o", "SIZE", disk], capture_output=True
        )
        return int(output.stdout.strip())
    except Exception as e:
        logging.error(f"Error getting disk size: {e}")
        print_error(f"Error getting disk size: {e}")
        # Default to 1TB as a fallback
        return 1_000_000_000_000


def unmount_disk(disk: str, force: bool = False) -> bool:
    """
    Attempt to unmount the disk and its partitions.

    Args:
        disk: Disk path (e.g., '/dev/sda')
        force: Whether to force unmount if normal unmount fails

    Returns:
        True if successfully unmounted or already not mounted
    """
    if not is_mounted(disk):
        return True

    print_warning(f"{disk} is mounted. Attempting to unmount...")

    try:
        # Try to unmount the disk itself
        run_command(["umount", disk], check=False)

        # Find and unmount all partitions
        output = run_command(
            ["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True
        )

        disk_name = os.path.basename(disk)
        for line in output.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                run_command(["umount", f"/dev/{parts[0]}"], check=False)
    except Exception as e:
        logging.error(f"Failed to unmount disk: {e}")

    # Check if we succeeded
    if is_mounted(disk):
        if not force:
            choice = input(
                f"[bold {NordColors.PURPLE}]Force unmount and continue? (y/N): [/] "
            ).lower()
            if choice != "y":
                print_message("Disk erasure cancelled.", NordColors.SNOW_STORM_1)
                return False

        try:
            # Force unmount the disk
            run_command(["umount", "-f", disk], check=False)

            # Force unmount all partitions
            output = run_command(["lsblk", "-n", "-o", "NAME"], capture_output=True)
            disk_name = os.path.basename(disk)

            for line in output.stdout.splitlines():
                if line.startswith(disk_name) and line != disk_name:
                    run_command(["umount", "-f", f"/dev/{line}"], check=False)
        except Exception as e:
            logging.error(f"Force unmount failed: {e}")
            print_error(f"Could not unmount {disk} even with force.")
            return False

    return not is_mounted(disk)


def display_disk_list(disks: List[DiskDevice]) -> None:
    """
    Display available disks in a formatted table.

    Args:
        disks: List of DiskDevice objects to display
    """
    if not disks:
        print_message("No disks found.", NordColors.SNOW_STORM_1)
        return

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Disks[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=4
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Size", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Type", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Path", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Model", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("System", justify="center")
    table.add_column("Mounted", justify="center")

    for idx, disk in enumerate(disks, start=1):
        system_indicator = (
            Text("YES", style=f"bold {NordColors.RED}")
            if disk.is_system
            else Text("no", style=f"dim {NordColors.SNOW_STORM_1}")
        )
        mounted_indicator = (
            Text("YES", style=f"bold {NordColors.YELLOW}")
            if disk.mounted
            else Text("no", style=f"dim {NordColors.SNOW_STORM_1}")
        )

        table.add_row(
            str(idx),
            disk.name,
            disk.size_human,
            disk.type,
            disk.path,
            disk.model,
            system_indicator,
            mounted_indicator,
        )

    console.print(table)


def select_disk(
    prompt: str = "Select a disk by number (or 'q' to cancel): ",
) -> Optional[str]:
    """
    Prompt the user to select a disk from the list.

    Args:
        prompt: Message to display when asking for selection

    Returns:
        Selected disk path or None if canceled
    """
    disks = list_disks()
    if not disks:
        print_message("No disks available.", NordColors.SNOW_STORM_1)
        return None

    display_disk_list(disks)

    while True:
        choice = input(f"\n[bold {NordColors.PURPLE}]{prompt}[/] ").strip()
        if choice.lower() == "q":
            return None

        try:
            num = int(choice)
            if 1 <= num <= len(disks):
                return disks[num - 1].path
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


# ----------------------------------------------------------------
# Disk Erasure Functions
# ----------------------------------------------------------------
def wipe_with_dd(disk: str, source: str) -> bool:
    """
    Erase the disk using dd (with /dev/zero or /dev/urandom).

    Args:
        disk: Path to the disk to erase
        source: Source device for dd (/dev/zero or /dev/urandom)

    Returns:
        True if wiping succeeded, False otherwise
    """
    try:
        disk_size = get_disk_size(disk)
        disk_name = os.path.basename(disk)

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_3}]Wiping disk..."),
            BarColumn(
                bar_width=PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.1f}}%"),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.fields[bytes_written]}}"),
            TextColumn(f"[{NordColors.PURPLE}]{{task.fields[speed]}}/s"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Wiping {disk_name}",
                total=disk_size,
                bytes_written="0 B",
                speed="0 B/s",
            )

            dd_cmd = [
                "dd",
                f"if={source}",
                f"of={disk}",
                "bs=4M",
                "conv=fsync,noerror",
                "status=progress",
            ]

            process = subprocess.Popen(
                dd_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            bytes_written = 0
            last_update_time = time.time()

            while True:
                line = process.stdout.readline() or process.stderr.readline()
                if not line and process.poll() is not None:
                    break

                if "bytes" in line:
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if (
                                part.isdigit()
                                and i < len(parts) - 1
                                and "byte" in parts[i + 1]
                            ):
                                current = int(part)
                                now = time.time()
                                speed = (
                                    (current - bytes_written) / (now - last_update_time)
                                    if now > last_update_time
                                    else 0
                                )
                                progress.update(
                                    task,
                                    completed=current,
                                    bytes_written=format_size(current),
                                    speed=format_size(speed),
                                )
                                bytes_written = current
                                last_update_time = now
                                break
                    except Exception as e:
                        logging.error(f"Error parsing dd output: {e}")
                        progress.update(task, advance=CHUNK_SIZE)

            returncode = process.wait()
            if returncode == 0:
                progress.update(task, completed=disk_size)

            return returncode == 0
    except Exception as e:
        logging.error(f"Error during dd wipe: {e}")
        print_error(f"Error during disk erasure: {e}")
        return False


def wipe_with_shred(disk: str, passes: int) -> bool:
    """
    Erase the disk using shred (DoD-compliant).

    Args:
        disk: Path to the disk to erase
        passes: Number of wiping passes to perform

    Returns:
        True if shred succeeded, False otherwise
    """
    try:
        disk_size = get_disk_size(disk)
        disk_name = os.path.basename(disk)
        total_work = disk_size * (passes + 1)  # +1 for final zero pass

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_3}]Secure erasing..."),
            BarColumn(
                bar_width=PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.1f}}%"),
            TextColumn(
                f"[{NordColors.PURPLE}]Pass {{task.fields[current_pass]}}/{{task.fields[total_passes]}}"
            ),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Wiping {disk_name}",
                total=total_work,
                current_pass="1",
                total_passes=str(passes + 1),  # +1 for final zero pass
            )

            shred_cmd = ["shred", "-n", str(passes), "-z", "-v", disk]

            process = subprocess.Popen(
                shred_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            current_pass = 1
            current_bytes = 0

            for line in iter(process.stderr.readline, ""):
                if "pass" in line and "/" in line:
                    try:
                        pass_info = re.search(r"pass (\d+)/(\d+)", line)
                        if pass_info:
                            new_pass = int(pass_info.group(1))
                            if new_pass != current_pass:
                                current_pass = new_pass
                                current_bytes = 0
                                progress.update(task, current_pass=str(current_pass))
                    except Exception:
                        pass

                if "%" in line:
                    try:
                        pct = float(line.split("%")[0].strip())
                        new_bytes = int(disk_size * pct / 100)
                        delta = new_bytes - current_bytes
                        if delta > 0:
                            progress.update(task, advance=delta)
                            current_bytes = new_bytes
                    except Exception:
                        progress.update(task, advance=CHUNK_SIZE)

            returncode = process.wait()
            if returncode == 0:
                progress.update(task, completed=total_work)

            return returncode == 0
    except Exception as e:
        logging.error(f"Error during shred wipe: {e}")
        print_error(f"Error during secure erasure: {e}")
        return False


def erase_disk(
    disk: str, method: str, passes: int = DEFAULT_PASSES, force: bool = False
) -> bool:
    """
    Erase the specified disk using the chosen erasure method.

    Args:
        disk: Path to the disk to erase
        method: Erasure method to use (zeros, random, dod)
        passes: Number of passes for DoD method
        force: Whether to force unmount

    Returns:
        True if erasure succeeded, False otherwise
    """
    if method not in ERASURE_METHODS:
        print_error(f"Unknown erasure method: {method}")
        return False

    if not is_valid_device(disk):
        return False

    if not unmount_disk(disk, force):
        return False

    print_section("Disk Erasure Confirmation")
    print_warning(f"You are about to PERMANENTLY ERASE {disk}")
    print_message(
        f"Erasure method: {ERASURE_METHODS[method]['name']}", NordColors.FROST_3
    )
    print_message(
        f"Description: {ERASURE_METHODS[method]['description']}",
        NordColors.SNOW_STORM_1,
    )

    if method == "dod":
        print_message(f"Passes: {passes}", NordColors.SNOW_STORM_1)

    disk_name = os.path.basename(disk)
    if is_system_disk(disk_name):
        print_error(
            "⚠ WARNING: THIS APPEARS TO BE A SYSTEM DISK! Erasing it will destroy your OS!"
        )

    if not force:
        confirm = input(
            f"\n[bold {NordColors.RED}]Type 'YES' to confirm disk erasure: [/] "
        )
        if confirm != "YES":
            print_message("Disk erasure cancelled", NordColors.SNOW_STORM_1)
            return False

    disk_size = get_disk_size(disk)
    estimated_time = "unknown"

    # Rough time estimates based on method and disk size
    if method == "zeros":
        speed_factor = 100 * 1024 * 1024  # ~100 MB/s
        estimated_time = format_time(disk_size / speed_factor)
    elif method == "random":
        speed_factor = 50 * 1024 * 1024  # ~50 MB/s
        estimated_time = format_time(disk_size / speed_factor)
    elif method == "dod":
        speed_factor = 75 * 1024 * 1024  # ~75 MB/s
        estimated_time = format_time((passes + 1) * disk_size / speed_factor)

    print_message(
        f"Estimated completion time: {estimated_time} (varies by disk speed)",
        NordColors.YELLOW,
    )
    print_message("Starting disk erasure...", NordColors.FROST_3)

    success = False
    start_time = time.time()

    try:
        if method in ["zeros", "random"]:
            source = "/dev/zero" if method == "zeros" else "/dev/urandom"
            success = wipe_with_dd(disk, source)
        elif method == "dod":
            success = wipe_with_shred(disk, passes)
    except KeyboardInterrupt:
        print_warning("Disk erasure interrupted by user")
        return False

    end_time = time.time()
    elapsed = format_time(end_time - start_time)

    if success:
        print_success(f"Disk {disk} erased successfully in {elapsed}")
    else:
        print_error(f"Disk {disk} erasure failed after {elapsed}")

    return success


# ----------------------------------------------------------------
# Disk Information Functions
# ----------------------------------------------------------------
def show_disk_info() -> None:
    """Display detailed information about a selected disk."""
    disk_path = select_disk("Select a disk to view details (or 'q' to cancel): ")
    if not disk_path:
        return

    disk_name = os.path.basename(disk_path)
    print_section(f"Disk Information: {disk_name}")

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Gathering disk information...", spinner="dots"
        ):
            # Basic partition info
            output = run_command(
                ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT", disk_path],
                capture_output=True,
            )

            # Get disk details
            disk_type = detect_disk_type(disk_name)
            disk_size = get_disk_size(disk_path)
            is_system = is_system_disk(disk_name)
            mounted = is_mounted(disk_path)

            # Get model and serial
            model_output = run_command(
                ["lsblk", "-d", "-n", "-o", "MODEL", disk_path],
                capture_output=True,
                check=False,
            )
            model = model_output.stdout.strip() or "Unknown"

            serial_output = run_command(
                ["lsblk", "-d", "-n", "-o", "SERIAL", disk_path],
                capture_output=True,
                check=False,
            )
            serial = serial_output.stdout.strip() or "Unknown"

        # Create panel with disk info
        disk_info = [
            f"[{NordColors.FROST_3}]Path:[/] [{NordColors.SNOW_STORM_1}]{disk_path}[/]",
            f"[{NordColors.FROST_3}]Type:[/] [{NordColors.SNOW_STORM_1}]{disk_type}[/]",
            f"[{NordColors.FROST_3}]Size:[/] [{NordColors.SNOW_STORM_1}]{format_size(disk_size)}[/]",
            f"[{NordColors.FROST_3}]Model:[/] [{NordColors.SNOW_STORM_1}]{model}[/]",
            f"[{NordColors.FROST_3}]Serial:[/] [{NordColors.SNOW_STORM_1}]{serial}[/]",
            f"[{NordColors.FROST_3}]System Disk:[/] [{NordColors.SNOW_STORM_1}]{'Yes' if is_system else 'No'}[/]",
            f"[{NordColors.FROST_3}]Mounted:[/] [{NordColors.SNOW_STORM_1}]{'Yes' if mounted else 'No'}[/]",
        ]

        info_panel = Panel(
            Text.from_markup("\n".join(disk_info)),
            title=f"[bold {NordColors.FROST_1}]Disk Details[/]",
            border_style=NordColors.FROST_3,
        )

        console.print(info_panel)

        # Show partition info
        print_section("Partition Information")
        console.print(output.stdout)

        # Show SMART status if available
        print_section("SMART Status")
        if shutil.which("smartctl"):
            try:
                smart_output = run_command(
                    ["smartctl", "-a", disk_path], capture_output=True, check=False
                )
                smart_status = smart_output.stdout.lower()

                if "failed" in smart_status:
                    print_warning("SMART status: FAILED - Disk might be failing!")
                elif "passed" in smart_status:
                    print_success("SMART status: PASSED")
                else:
                    print_message(
                        "SMART status: Unknown or not available",
                        NordColors.SNOW_STORM_1,
                    )

                # Show important SMART attributes
                console.print(f"[{NordColors.FROST_2}]SMART data summary:[/]")
                for line in smart_output.stdout.splitlines():
                    if any(
                        attr in line.lower()
                        for attr in [
                            "reallocated",
                            "pending",
                            "uncorrectable",
                            "health",
                            "life",
                        ]
                    ):
                        console.print(f"[{NordColors.SNOW_STORM_1}]{line}[/]")
            except Exception:
                print_warning("SMART data could not be retrieved")
        else:
            print_message(
                "smartctl not found - SMART data unavailable", NordColors.FROST_3
            )
    except Exception as e:
        print_error(f"Error retrieving disk info: {e}")


# ----------------------------------------------------------------
# Menu Functions
# ----------------------------------------------------------------
def select_erasure_method() -> Optional[str]:
    """
    Display a menu of available erasure methods and return the user's choice.

    Returns:
        Selected method key or None if cancelled
    """
    print_section("Select Erasure Method")

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Methods[/]",
        border_style=NordColors.FROST_3,
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Method", style=f"bold {NordColors.FROST_1}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for idx, (method_key, method_info) in enumerate(ERASURE_METHODS.items(), start=1):
        table.add_row(str(idx), method_info["name"], method_info["description"])

    console.print(table)

    while True:
        choice = input(
            f"\n[bold {NordColors.PURPLE}]Select erasure method (1-{len(ERASURE_METHODS)}, or 'q' to cancel): [/] "
        ).strip()

        if choice.lower() == "q":
            return None

        try:
            num = int(choice)
            if 1 <= num <= len(ERASURE_METHODS):
                return list(ERASURE_METHODS.keys())[num - 1]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


def erasure_menu() -> None:
    """Interactively prompt the user to erase a disk."""
    disk_path = select_disk("Select a disk to erase (or 'q' to cancel): ")
    if not disk_path:
        print_message("Erasure cancelled", NordColors.SNOW_STORM_1)
        return

    method = select_erasure_method()
    if not method:
        print_message("Erasure cancelled", NordColors.SNOW_STORM_1)
        return

    passes = DEFAULT_PASSES
    if method == "dod":
        while True:
            try:
                passes_input = input(
                    f"[bold {NordColors.PURPLE}]Number of passes (1-7, default {DEFAULT_PASSES}): [/] "
                )
                if not passes_input:
                    break

                passes = int(passes_input)
                if 1 <= passes <= 7:
                    break
                print_error("Please enter a number between 1 and 7")
            except ValueError:
                print_error("Please enter a valid number")

    force = False
    erase_disk(disk_path, method, passes, force)


def interactive_menu() -> None:
    """Display the main interactive menu for the Disk Eraser Tool."""
    while True:
        console.clear()
        console.print(create_header())

        # Display system info
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()

        # Create menu table
        menu_table = Table(
            title=f"[bold {NordColors.FROST_2}]Main Menu[/]",
            box=None,
            title_style=f"bold {NordColors.FROST_1}",
            show_header=False,
            expand=True,
        )

        menu_table.add_column(
            style=f"bold {NordColors.FROST_4}", justify="right", width=4
        )
        menu_table.add_column(style=f"bold {NordColors.FROST_3}")

        menu_table.add_row("1", "List Disks")
        menu_table.add_row("2", "Show Disk Information")
        menu_table.add_row("3", "Erase Disk")
        menu_table.add_row("4", "Exit")

        console.print(Panel(menu_table, border_style=Style(color=NordColors.FROST_4)))
        console.print()

        choice = input(f"[bold {NordColors.PURPLE}]Enter your choice: [/] ").strip()

        if choice == "1":
            display_disk_list(list_disks())
        elif choice == "2":
            show_disk_info()
        elif choice == "3":
            erasure_menu()
        elif choice == "4":
            console.clear()
            console.print(
                Panel(
                    Text(
                        "Thank you for using the Disk Eraser Tool!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            break
        else:
            print_error("Invalid choice. Please try again.")

        input(f"\n[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the Disk Eraser Tool."""
    try:
        if not check_root():
            sys.exit(1)

        setup_logging()

        if not check_dependencies():
            sys.exit(1)

        interactive_menu()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
