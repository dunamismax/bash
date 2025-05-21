#!/usr/bin/env python3
"""
Disk Eraser Tool
--------------------------------------------------

A secure disk wiping utility with multiple erasure methods and an elegant Nord-themed interface.
Features include:
  • Listing available disks with detailed information.
  • Examining disk details including SMART data.
  • Securely erasing disks using zeros, random data, or DoD-compliant (shred) methods.
  • Real-time progress tracking with spinners and progress bars.
  • A stylish interactive menu system with a Pyfiglet ASCII banner.

CAUTION: This tool permanently destroys all data on selected disks.
It must be run with root/sudo privileges.

Version: 2.1.0
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
from typing import Any, Dict, List, Optional

import pyfiglet
from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback
from rich.style import Style

# Install rich traceback handler for better debugging
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Global Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
PROGRESS_WIDTH: int = 40
CHUNK_SIZE: int = 1024 * 1024  # 1 MB chunks
LOG_FILE: str = "/var/log/disk_eraser.log"
DEFAULT_LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
OPERATION_TIMEOUT: int = 60  # seconds

VERSION: str = "2.1.0"
APP_NAME: str = "Disk Eraser"
APP_SUBTITLE: str = "Secure Data Destruction Tool"

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
DEFAULT_METHOD: str = "zeros"
DEFAULT_PASSES: int = 1


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent styling."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# Create a global Rich console with a simple theme
console: Console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class DiskDevice:
    """
    Represents a physical disk device with its properties.

    Attributes:
        name: Device name (e.g., sda)
        path: Full device path (e.g., /dev/sda)
        size: Size in bytes
        model: Device model (or manufacturer)
        size_human: Human-readable size string
        is_system: True if it appears to be a system disk
        type: Disk type (e.g., HDD, SSD, NVMe)
        mounted: True if any partitions are mounted
    """

    def __init__(self, name: str, path: str, size: int, model: str = "") -> None:
        self.name: str = name
        self.path: str = path
        self.size: int = size
        self.model: str = model
        self.size_human: str = format_size(size)
        self.is_system: bool = is_system_disk(name)
        self.type: str = detect_disk_type(name)
        self.mounted: bool = is_mounted(path)

    def __str__(self) -> str:
        return f"{self.name} ({self.size_human}, {self.type})"


# ----------------------------------------------------------------
# Console UI Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a stylish ASCII banner header using Pyfiglet and apply Nord colors.

    Returns:
        Panel object containing the header.
    """
    fonts = ["slant", "small", "digital", "mini", "smslant"]
    ascii_art: Optional[str] = None
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art or not ascii_art.strip():
        ascii_art = APP_NAME

    # Apply a gradient effect using Nord colors
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        styled_text += f"[bold {colors[i % len(colors)]}]{line}[/]\n"

    border = f"[{NordColors.FROST_3}]" + "━" * 60 + "[/]"
    styled_text = f"{border}\n{styled_text}{border}"
    header = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Display a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Display a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Display a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Display an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Display a step description."""
    print_message(message, NordColors.FROST_2, "•")


def print_section(title: str) -> None:
    """Display a formatted section header."""
    border = "═" * min(TERM_WIDTH, 80)
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{title.center(min(TERM_WIDTH, 80))}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message inside a styled panel."""
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
    """Convert seconds into a formatted time string (HH:MM:SS or MM:SS)."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}" if minutes else f"{secs:02d} sec"


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure logging to both console and a rotating log file."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
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
        logging.info(f"Logging to {LOG_FILE}")
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
    Execute a system command and return the CompletedProcess.

    Raises:
        subprocess.CalledProcessError: If command fails.
    """
    logging.debug(f"Executing: {' '.join(cmd)}")
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
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    logging.info("Cleanup completed")


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    logging.error(f"Script interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Validation Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """Verify the script is run with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        print_message("Please run with sudo or as root.", NordColors.SNOW_STORM_1)
        return False
    return True


def check_dependencies() -> bool:
    """
    Ensure required external commands are available.

    Returns:
        True if all dependencies exist; otherwise, False.
    """
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
    """
    Validate that the provided path is an absolute path to a block device.

    Returns:
        True if valid, False otherwise.
    """
    if not os.path.exists(device_path):
        print_error(f"Device not found: {device_path}")
        return False
    if not os.path.isabs(device_path):
        print_error("Device path must be absolute.")
        return False

    device_name = os.path.basename(device_path)
    sys_block = "/sys/block"
    if not os.path.exists(f"{sys_block}/{device_name}") and not any(
        os.path.exists(f"{sys_block}/{bd}/{device_name}")
        for bd in os.listdir(sys_block)
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
        A list of DiskDevice objects.
    """
    try:
        output = run_command(
            ["lsblk", "-d", "-b", "-o", "NAME,SIZE,MODEL,TYPE", "--json"],
            capture_output=True,
        )
        data = json.loads(output.stdout)
        disks: List[DiskDevice] = []
        for device in data.get("blockdevices", []):
            if device.get("type") != "disk":
                continue
            name = device.get("name", "")
            path = f"/dev/{name}"
            size = int(device.get("size", 0))
            model = device.get("model", "").strip() or "Unknown"
            disks.append(DiskDevice(name, path, size, model))
        return disks
    except Exception as e:
        logging.error(f"Error listing disks: {e}")
        print_error(f"Failed to list disks: {e}")
        return []


def detect_disk_type(disk: str) -> str:
    """
    Detect the disk type (NVMe, HDD, SSD, or Unknown).

    Returns:
        A string indicating the disk type.
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
    Check if the disk appears to be the system disk.

    Returns:
        True if it is likely the system disk, else False.
    """
    try:
        result = run_command(
            ["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True
        )
        root_device = result.stdout.strip()
        if root_device.startswith("/dev/"):
            root_device = root_device[5:]
        base = re.sub(r"\d+$", "", root_device)
        return disk == base
    except Exception:
        return True


def is_mounted(disk: str) -> bool:
    """
    Check if a disk or any of its partitions are mounted.

    Returns:
        True if mounted; otherwise, False.
    """
    try:
        output = run_command(["mount"], capture_output=True)
        if disk in output.stdout:
            return True

        disk_name = os.path.basename(disk)
        lsblk_out = run_command(
            ["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True
        )
        for line in lsblk_out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                return True
        return False
    except Exception as e:
        logging.error(f"Error checking mount status: {e}")
        return True


def get_disk_size(disk: str) -> int:
    """
    Retrieve the disk size in bytes.

    Returns:
        The size in bytes.
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
        return 1_000_000_000_000  # Fallback to 1 TB


def unmount_disk(disk: str, force: bool = False) -> bool:
    """
    Attempt to unmount the disk and its partitions.

    Returns:
        True if successfully unmounted (or already unmounted), False otherwise.
    """
    if not is_mounted(disk):
        return True

    print_warning(f"{disk} is mounted. Attempting to unmount...")
    try:
        run_command(["umount", disk], check=False)
        lsblk_out = run_command(
            ["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True
        )
        disk_name = os.path.basename(disk)
        for line in lsblk_out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                run_command(["umount", f"/dev/{parts[0]}"], check=False)
    except Exception as e:
        logging.error(f"Failed to unmount disk: {e}")
    if is_mounted(disk):
        if not force:
            choice = Prompt.ask(
                f"[bold {NordColors.PURPLE}]Force unmount and continue?[/]",
                choices=["y", "n"],
                default="n",
            )
            if choice.lower() != "y":
                print_message("Disk erasure cancelled.", NordColors.SNOW_STORM_1)
                return False
        try:
            run_command(["umount", "-f", disk], check=False)
            lsblk_names = run_command(
                ["lsblk", "-n", "-o", "NAME"], capture_output=True
            )
            disk_name = os.path.basename(disk)
            for line in lsblk_names.stdout.splitlines():
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
    table.add_column("Size", style=NordColors.SNOW_STORM_1)
    table.add_column("Type", style=NordColors.SNOW_STORM_1)
    table.add_column("Path", style=NordColors.SNOW_STORM_1)
    table.add_column("Model", style=NordColors.SNOW_STORM_1)
    table.add_column("System", justify="center")
    table.add_column("Mounted", justify="center")
    for idx, disk in enumerate(disks, start=1):
        system_text = (
            Text("YES", style=f"bold {NordColors.RED}")
            if disk.is_system
            else Text("no", style=f"dim {NordColors.SNOW_STORM_1}")
        )
        mounted_text = (
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
            system_text,
            mounted_text,
        )
    console.print(table)


def select_disk(
    prompt: str = "Select a disk by number (or 'q' to cancel): ",
) -> Optional[str]:
    """
    Prompt the user to select a disk from the list.

    Returns:
        The selected disk path or None if cancelled.
    """
    disks = list_disks()
    if not disks:
        print_message("No disks available.", NordColors.SNOW_STORM_1)
        return None
    display_disk_list(disks)
    while True:
        choice = Prompt.ask(f"[bold {NordColors.PURPLE}]{prompt}[/]")
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(disks):
                return disks[num - 1].path
            print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


# ----------------------------------------------------------------
# Disk Erasure Functions
# ----------------------------------------------------------------
def wipe_with_dd(disk: str, source: str) -> bool:
    """
    Erase the disk using dd with the specified data source.

    Returns:
        True if wiping succeeded; otherwise, False.
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
            transient=True,
            console=console,
        ) as progress:
            task_id = progress.add_task(
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            bytes_written = 0
            last_update = time.time()
            # Read output from dd to update progress
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
                                    (current - bytes_written) / (now - last_update)
                                    if now > last_update
                                    else 0
                                )
                                progress.update(
                                    task_id,
                                    completed=current,
                                    bytes_written=format_size(current),
                                    speed=format_size(speed),
                                )
                                bytes_written = current
                                last_update = now
                                break
                    except Exception as e:
                        logging.error(f"Error parsing dd output: {e}")
                        progress.update(task_id, advance=CHUNK_SIZE)
            retcode = process.wait()
            if retcode == 0:
                progress.update(task_id, completed=disk_size)
            return retcode == 0
    except Exception as e:
        logging.error(f"Error during dd wipe: {e}")
        print_error(f"Error during disk erasure: {e}")
        return False


def wipe_with_shred(disk: str, passes: int) -> bool:
    """
    Erase the disk using shred (DoD-compliant).

    Returns:
        True if shredding succeeded; otherwise, False.
    """
    try:
        disk_size = get_disk_size(disk)
        disk_name = os.path.basename(disk)
        total_work = disk_size * (passes + 1)  # Including final zero pass
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
            transient=True,
            console=console,
        ) as progress:
            task_id = progress.add_task(
                f"Wiping {disk_name}",
                total=total_work,
                current_pass="1",
                total_passes=str(passes + 1),
            )
            shred_cmd = ["shred", "-n", str(passes), "-z", "-v", disk]
            process = subprocess.Popen(
                shred_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            current_pass = 1
            current_bytes = 0
            for line in iter(process.stderr.readline, ""):
                if "pass" in line and "/" in line:
                    match = re.search(r"pass (\d+)/(\d+)", line)
                    if match:
                        new_pass = int(match.group(1))
                        if new_pass != current_pass:
                            current_pass = new_pass
                            current_bytes = 0
                            progress.update(task_id, current_pass=str(current_pass))
                if "%" in line:
                    try:
                        pct = float(line.split("%")[0].strip())
                        new_bytes = int(disk_size * pct / 100)
                        delta = new_bytes - current_bytes
                        if delta > 0:
                            progress.update(task_id, advance=delta)
                            current_bytes = new_bytes
                    except Exception:
                        progress.update(task_id, advance=CHUNK_SIZE)
            retcode = process.wait()
            if retcode == 0:
                progress.update(task_id, completed=total_work)
            return retcode == 0
    except Exception as e:
        logging.error(f"Error during shred wipe: {e}")
        print_error(f"Error during secure erasure: {e}")
        return False


def erase_disk(
    disk: str, method: str, passes: int = DEFAULT_PASSES, force: bool = False
) -> bool:
    """
    Erase the specified disk using the chosen erasure method.

    Returns:
        True if erasure succeeded; otherwise, False.
    """
    if method not in ERASURE_METHODS:
        print_error(f"Unknown erasure method: {method}")
        return False

    if not is_valid_device(disk) or not unmount_disk(disk, force):
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
        confirm = Prompt.ask(
            f"[bold {NordColors.RED}]Type 'YES' to confirm disk erasure[/]"
        )
        if confirm != "YES":
            print_message("Disk erasure cancelled", NordColors.SNOW_STORM_1)
            return False

    disk_size = get_disk_size(disk)
    # Estimate completion time based on method
    if method == "zeros":
        speed_factor = 100 * 1024 * 1024  # ~100 MB/s
    elif method == "random":
        speed_factor = 50 * 1024 * 1024  # ~50 MB/s
    elif method == "dod":
        speed_factor = 75 * 1024 * 1024  # ~75 MB/s
    estimated_time = format_time((disk_size * (passes + 1)) / speed_factor)
    print_message(
        f"Estimated completion time: {estimated_time} (varies by disk speed)",
        NordColors.YELLOW,
    )
    print_message("Starting disk erasure...", NordColors.FROST_3)
    start = time.time()
    try:
        if method in ["zeros", "random"]:
            source = "/dev/zero" if method == "zeros" else "/dev/urandom"
            success = wipe_with_dd(disk, source)
        elif method == "dod":
            success = wipe_with_shred(disk, passes)
    except KeyboardInterrupt:
        print_warning("Disk erasure interrupted by user")
        return False
    elapsed = format_time(time.time() - start)
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
            output = run_command(
                ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT", disk_path],
                capture_output=True,
            )
            disk_type = detect_disk_type(disk_name)
            disk_size = get_disk_size(disk_path)
            is_system = is_system_disk(disk_name)
            mounted = is_mounted(disk_path)
            model_out = run_command(
                ["lsblk", "-d", "-n", "-o", "MODEL", disk_path],
                capture_output=True,
                check=False,
            )
            model = model_out.stdout.strip() or "Unknown"
            serial_out = run_command(
                ["lsblk", "-d", "-n", "-o", "SERIAL", disk_path],
                capture_output=True,
                check=False,
            )
            serial = serial_out.stdout.strip() or "Unknown"
        info = [
            f"[{NordColors.FROST_3}]Path:[/] [{NordColors.SNOW_STORM_1}]{disk_path}[/]",
            f"[{NordColors.FROST_3}]Type:[/] [{NordColors.SNOW_STORM_1}]{disk_type}[/]",
            f"[{NordColors.FROST_3}]Size:[/] [{NordColors.SNOW_STORM_1}]{format_size(disk_size)}[/]",
            f"[{NordColors.FROST_3}]Model:[/] [{NordColors.SNOW_STORM_1}]{model}[/]",
            f"[{NordColors.FROST_3}]Serial:[/] [{NordColors.SNOW_STORM_1}]{serial}[/]",
            f"[{NordColors.FROST_3}]System Disk:[/] [{NordColors.SNOW_STORM_1}]{'Yes' if is_system else 'No'}[/]",
            f"[{NordColors.FROST_3}]Mounted:[/] [{NordColors.SNOW_STORM_1}]{'Yes' if mounted else 'No'}[/]",
        ]
        info_panel = Panel(
            Text.from_markup("\n".join(info)),
            title=f"[bold {NordColors.FROST_1}]Disk Details[/]",
            border_style=NordColors.FROST_3,
        )
        console.print(info_panel)
        print_section("Partition Information")
        console.print(output.stdout)
        print_section("SMART Status")
        if shutil.which("smartctl"):
            try:
                smart_out = run_command(
                    ["smartctl", "-a", disk_path], capture_output=True, check=False
                )
                smart_text = smart_out.stdout.lower()
                if "failed" in smart_text:
                    print_warning("SMART status: FAILED - Disk might be failing!")
                elif "passed" in smart_text:
                    print_success("SMART status: PASSED")
                else:
                    print_message(
                        "SMART status: Unknown or not available",
                        NordColors.SNOW_STORM_1,
                    )
                console.print(f"[{NordColors.FROST_2}]SMART data summary:[/]")
                for line in smart_out.stdout.splitlines():
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
    Display a menu of available erasure methods and return the chosen key.

    Returns:
        The selected method key or None if cancelled.
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
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    security = {"zeros": "Basic", "random": "Good", "dod": "Best"}
    table.add_column("Security", style=NordColors.SNOW_STORM_1)
    for idx, (key, info) in enumerate(ERASURE_METHODS.items(), start=1):
        table.add_row(
            str(idx), info["name"], info["description"], security.get(key, "Unknown")
        )
    console.print(table)
    while True:
        choice = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select erasure method (1-{len(ERASURE_METHODS)} or 'q' to cancel)[/]"
        )
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(ERASURE_METHODS):
                return list(ERASURE_METHODS.keys())[num - 1]
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
                passes_input = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Number of passes (1-7, default {DEFAULT_PASSES})[/]",
                    default=str(DEFAULT_PASSES),
                )
                passes = int(passes_input) if passes_input else DEFAULT_PASSES
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
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()
        menu_table = Table(
            title=f"[bold {NordColors.FROST_2}]Main Menu[/]",
            box=box.SIMPLE,
            title_style=f"bold {NordColors.FROST_1}",
            show_header=False,
            expand=True,
        )
        menu_table.add_column(
            style=f"bold {NordColors.FROST_4}", justify="right", width=4
        )
        menu_table.add_column(style=f"bold {NordColors.FROST_3}")
        menu_table.add_column(style=NordColors.SNOW_STORM_1)
        menu_table.add_row("1", "List Disks", "View all available storage devices")
        menu_table.add_row(
            "2", "Show Disk Information", "Examine disk details and SMART status"
        )
        menu_table.add_row("3", "Erase Disk", "Permanently destroy all data on a disk")
        menu_table.add_row("4", "Exit", "Quit the application")
        console.print(Panel(menu_table, border_style=Style(color=NordColors.FROST_4)))
        console.print()
        console.print(
            Panel(
                Text.from_markup(
                    "[bold]CAUTION:[/] This tool permanently destroys all data on selected disks.\nThere is NO recovery option after erasure is complete."
                ),
                border_style=Style(color=NordColors.RED),
                padding=(1, 2),
            )
        )
        console.print()
        choice = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Enter your choice[/]",
            choices=["1", "2", "3", "4"],
        )
        if choice == "1":
            display_disk_list(list_disks())
            input(f"\n[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")
        elif choice == "2":
            show_disk_info()
            input(f"\n[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")
        elif choice == "3":
            erasure_menu()
            input(f"\n[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")
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


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the Disk Eraser Tool."""
    try:
        if not check_root():
            sys.exit(1)
        setup_logging()
        logging.info(f"Starting Disk Eraser Tool v{VERSION}")
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
