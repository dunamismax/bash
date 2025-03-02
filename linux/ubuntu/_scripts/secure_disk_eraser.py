#!/usr/bin/env python3
"""
Enhanced Disk Eraser Tool
-------------------------

This utility securely erases disk devices using various methods (zeros, random data,
DoD-compliant). It provides detailed progress tracking, error handling, and a Nord-themed
user interface. This tool provides a complete solution for securely wiping disks on Linux systems.

Note: This script must be run with root privileges.
Version: 1.0.0 | License: MIT
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
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
HOSTNAME = socket.gethostname()
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
PROGRESS_WIDTH = 40
CHUNK_SIZE = 1024 * 1024  # 1MB for progress updates
LOG_FILE = "/var/log/disk_eraser.log"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

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

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()

class NordColors:
    """Nord theme color palette for consistent UI styling."""
    # Polar Night (background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"
    # Snow Storm (foreground)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"
    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"
    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)

# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")

def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]{title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")

def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")

def print_step(message: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {message}[/]")

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

def get_user_input(prompt: str, default: str = "") -> str:
    """Prompt the user for input with a styled message."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)

def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Prompt the user to choose from given options."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True)

def get_user_confirmation(prompt: str) -> bool:
    """Prompt the user for a yes/no confirmation."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")

def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Generate a table of menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")
    for key, desc in options:
        table.add_row(key, desc)
    return table

# ==============================
# Logging Setup
# ==============================
def setup_logging() -> None:
    """Configure logging to both console and a rotating log file."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    formatter = logging.Formatter(fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    try:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Could not set up log file: {e}")
        logger.warning("Continuing with console logging only")

# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform any necessary cleanup before exiting."""
    print_step("Performing cleanup tasks...")
    logging.info("Performing cleanup tasks...")
    # Additional cleanup tasks can be added here

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    print_warning(f"Script interrupted by {sig_name}.")
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ==============================
# Command Execution Helper
# ==============================
def run_command(
    command: List[str],
    capture_output: bool = False,
    check: bool = True,
    timeout: int = 60,
) -> str:
    """
    Execute a shell command with error handling.

    Args:
        command: List of command arguments.
        capture_output: If True, returns stdout.
        check: If True, raises error on non-zero exit.
        timeout: Command timeout in seconds.
        
    Returns:
        Command stdout if capture_output is True.
    """
    try:
        logging.debug(f"Executing: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result.stdout if capture_output else ""
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {' '.join(command)}")
        print_error(f"Command timed out: {' '.join(command)}")
        raise
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(command)} with error: {e.stderr}")
        print_error(f"Command failed: {' '.join(command)}")
        raise

# ==============================
# Validation Functions
# ==============================
def check_root() -> bool:
    """Check if the script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        print_info("Please run with sudo or as root.")
        return False
    return True

def check_dependencies() -> bool:
    """Ensure required external commands are available."""
    required = ["lsblk", "dd", "shred"]
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        print_error(f"Missing required dependencies: {', '.join(missing)}")
        print_info("Please install them using your package manager.")
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
        os.path.exists(f"/sys/block/{bd}/{device_name}") for bd in os.listdir("/sys/block")
    ):
        print_error(f"{device_path} is not recognized as a block device.")
        return False
    return True

# ==============================
# Progress Tracking
# ==============================
class ProgressTracker:
    """Real-time progress tracking using Rich Progress."""
    def __init__(self, description: str, total_bytes: int):
        self.description = description
        self.total_bytes = total_bytes
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold #81A1C1]{task.description}"),
            BarColumn(complete_style="#8FBCBB", finished_style="#A3BE8C"),
            TextColumn("[#88C0D0]{task.percentage:>3.1f}%"),
            TextColumn("[#D8DEE9]{task.fields[processed]}"),
            TextColumn("[#B48EAD]{task.fields[speed]}/s"),
            TimeRemainingColumn(),
        )
        self.task_id = self.progress.add_task(
            self.description,
            total=total_bytes,
            processed="0 B",
            speed="0 B",
        )
    def start(self):
        self.progress.start()
    def stop(self):
        self.progress.stop()
    def update(self, advance: int, speed: float):
        self.progress.update(
            self.task_id,
            advance=advance,
            processed=format_size(self.progress.tasks[self.task_id].completed),
            speed=format_size(speed),
        )

# ==============================
# Disk Management Functions
# ==============================
def list_disks() -> List[Dict[str, Any]]:
    """List all block devices using lsblk with JSON output."""
    try:
        output = run_command(
            ["lsblk", "-d", "-o", "NAME,SIZE,MODEL,TYPE", "--json"],
            capture_output=True,
        )
        data = json.loads(output)
        disks = data.get("blockdevices", [])
        # Add extra fields for each disk
        for disk in disks:
            disk["path"] = f"/dev/{disk.get('name', '')}"
        return disks
    except Exception as e:
        logging.error(f"Error listing disks: {e}")
        print_error(f"Failed to list disks: {e}")
        return []

def detect_disk_type(disk: str) -> str:
    """Detect whether a disk is NVMe, HDD, or SSD."""
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
    """Check if the disk is likely the system disk."""
    try:
        result = run_command(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True,
        )
        root_device = result.strip()
        if root_device.startswith("/dev/"):
            root_device = root_device[5:]
        base = re.sub(r"\d+$", "", root_device)
        return disk == base
    except Exception:
        return True

def display_disk_list(disks: List[Dict[str, Any]]) -> None:
    """Display available disks in a formatted table."""
    if not disks:
        print_info("No disks found.")
        return
    print_section("Available Disks")
    header = f"{'No.':<5} {'NAME':<12} {'SIZE':<10} {'TYPE':<8} {'PATH':<12} {'MODEL':<30}"
    console.print(f"[#ECEFF4]{header}[/#ECEFF4]")
    console.print(f"[#81A1C1]{'─' * 80}[/#81A1C1]")
    for idx, disk in enumerate(disks, start=1):
        name = disk.get("name", "")
        size = disk.get("size", "")
        dtype = detect_disk_type(name)
        path = disk.get("path", "")
        model = disk.get("model", "").strip() or "N/A"
        console.print(
            f"[#D8DEE9]{idx:<5} {name:<12} {size:<10} {dtype:<8} {path:<12} {model:<30}[/#D8DEE9]"
        )

def select_disk(prompt: str = "Select a disk by number (or 'q' to cancel): ") -> Optional[str]:
    """Prompt the user to select a disk from the list."""
    disks = list_disks()
    if not disks:
        print_info("No disks available.")
        return None
    display_disk_list(disks)
    while True:
        choice = input(f"\n[bold #B48EAD]{prompt}[/bold #B48EAD] ").strip()
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(disks):
                return disks[num - 1]["path"]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")

def is_mounted(disk: str) -> bool:
    """Check if a disk or its partitions are mounted."""
    try:
        output = run_command(["mount"], capture_output=True)
        if disk in output:
            return True
        disk_name = os.path.basename(disk)
        output = run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                return True
        return False
    except Exception as e:
        logging.error(f"Error checking mount status: {e}")
        print_error(f"Error checking mount status: {e}")
        return True

def get_disk_size(disk: str) -> int:
    """Return disk size in bytes."""
    try:
        disk_name = os.path.basename(disk)
        size_path = f"/sys/block/{disk_name}/size"
        if os.path.exists(size_path):
            with open(size_path, "r") as f:
                return int(f.read().strip()) * 512
        output = run_command(["lsblk", "-b", "-d", "-n", "-o", "SIZE", disk], capture_output=True)
        return int(output.strip())
    except Exception as e:
        logging.error(f"Error getting disk size: {e}")
        print_error(f"Error getting disk size: {e}")
        return 1_000_000_000_000  # Default to 1TB

def unmount_disk(disk: str, force: bool = False) -> bool:
    """Attempt to unmount the disk and its partitions."""
    if not is_mounted(disk):
        return True
    print_warning(f"{disk} is mounted. Attempting to unmount...")
    try:
        run_command(["umount", disk], check=False)
        output = run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"], capture_output=True)
        disk_name = os.path.basename(disk)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                run_command(["umount", f"/dev/{parts[0]}"], check=False)
    except Exception as e:
        logging.error(f"Failed to unmount disk: {e}")
    if is_mounted(disk):
        if not force:
            choice = input(f"[bold #B48EAD]Force unmount and continue? (y/N): [/bold #B48EAD] ").lower()
            if choice != "y":
                print_info("Disk erasure cancelled.")
                return False
        try:
            run_command(["umount", "-f", disk], check=False)
            output = run_command(["lsblk", "-n", "-o", "NAME"], capture_output=True)
            disk_name = os.path.basename(disk)
            for line in output.splitlines():
                if line.startswith(disk_name) and line != disk_name:
                    run_command(["umount", "-f", f"/dev/{line}"], check=False)
        except Exception as e:
            logging.error(f"Force unmount failed: {e}")
            print_error(f"Could not unmount {disk} even with force.")
            return False
    return not is_mounted(disk)

# ==============================
# Disk Erasure Functions
# ==============================
def wipe_with_dd(disk: str, source: str) -> bool:
    """Erase the disk using dd (with /dev/zero or /dev/urandom)."""
    try:
        disk_size = get_disk_size(disk)
        disk_name = os.path.basename(disk)
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold #81A1C1]Wiping disk..."),
            BarColumn(complete_style="#8FBCBB"),
            TextColumn("[#88C0D0]{task.percentage:>3.1f}%"),
            TextColumn("[#D8DEE9]{task.fields[bytes_written]}"),
            TextColumn("[#B48EAD]{task.fields[speed]}/s"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"Wiping {disk_name}", total=disk_size, bytes_written="0 B", speed="0 B/s")
            dd_cmd = [
                "dd",
                f"if={source}",
                f"of={disk}",
                "bs=4M",
                "conv=fsync,noerror",
                "status=progress",
            ]
            process = subprocess.Popen(dd_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
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
                            if part.isdigit() and i < len(parts) - 1 and "byte" in parts[i + 1]:
                                current = int(part)
                                now = time.time()
                                speed = (current - bytes_written) / (now - last_update_time) if now > last_update_time else 0
                                progress.update(task, completed=current, bytes_written=format_size(current), speed=format_size(speed))
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
    """Erase the disk using shred (DoD-compliant)."""
    try:
        disk_size = get_disk_size(disk)
        disk_name = os.path.basename(disk)
        total_work = disk_size * (passes + 1)
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold #81A1C1]Secure erasing..."),
            BarColumn(complete_style="#8FBCBB"),
            TextColumn("[#88C0D0]{task.percentage:>3.1f}%"),
            TextColumn("[#B48EAD]Pass {task.fields[current_pass]}/{task.fields[total_passes]}"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"Wiping {disk_name}", total=total_work, current_pass="1", total_passes=str(passes + 1))
            shred_cmd = ["shred", "-n", str(passes), "-z", "-v", disk]
            process = subprocess.Popen(shred_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
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

def erase_disk(disk: str, method: str, passes: int = DEFAULT_PASSES, force: bool = False) -> bool:
    """Erase the specified disk using the chosen erasure method."""
    if method not in ERASURE_METHODS:
        print_error(f"Unknown erasure method: {method}")
        return False
    if not is_valid_device(disk):
        return False
    if not unmount_disk(disk, force):
        return False
    print_section("Disk Erasure Confirmation")
    print_warning(f"You are about to PERMANENTLY ERASE {disk}")
    print_info(f"Erasure method: {ERASURE_METHODS[method]['name']}")
    print_info(f"Description: {ERASURE_METHODS[method]['description']}")
    if method == "dod":
        print_info(f"Passes: {passes}")
    disk_name = os.path.basename(disk)
    if is_system_disk(disk_name):
        print_error("⚠ WARNING: THIS APPEARS TO BE A SYSTEM DISK! Erasing it will destroy your OS!")
    if not force:
        confirm = input(f"\n[bold #BF616A]Type 'YES' to confirm disk erasure: [/bold #BF616A] ")
        if confirm != "YES":
            print_info("Disk erasure cancelled")
            return False
    print_header(f"Starting Disk Erasure - {ERASURE_METHODS[method]['name']}")
    if method in ["zeros", "random"]:
        source = "/dev/zero" if method == "zeros" else "/dev/urandom"
        success = wipe_with_dd(disk, source)
    elif method == "dod":
        success = wipe_with_shred(disk, passes)
    else:
        print_error(f"Unsupported method: {method}")
        return False
    if success:
        print_success(f"Disk {disk} erased successfully")
    else:
        print_error(f"Disk {disk} erasure failed")
    return success

# ==============================
# Menu Functions
# ==============================
def select_erasure_method() -> Optional[str]:
    """Display a menu of available erasure methods and return the user's choice."""
    print_section("Select Erasure Method")
    for idx, (method_key, method_info) in enumerate(ERASURE_METHODS.items(), start=1):
        console.print(f"[#D8DEE9]{idx}. {method_info['name']}[/#D8DEE9]")
        console.print(f"   [#81A1C1]{method_info['description']}[/#81A1C1]")
    while True:
        choice = input(f"\n[bold #B48EAD]Select erasure method (1-{len(ERASURE_METHODS)}, or 'q' to cancel): [/bold #B48EAD] ").strip()
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

def show_disk_info() -> None:
    """Display detailed information about a selected disk."""
    print_header("Disk Information")
    disk_path = select_disk("Select a disk to view details (or 'q' to cancel): ")
    if not disk_path:
        return
    disk_name = os.path.basename(disk_path)
    print_section(f"Disk Information: {disk_name}")
    try:
        with console.status("[bold #81A1C1]Gathering disk information...", spinner="dots"):
            output = run_command(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT", disk_path], capture_output=True)
            disk_type = detect_disk_type(disk_name)
            disk_size = get_disk_size(disk_path)
            is_system = is_system_disk(disk_name)
            mounted = is_mounted(disk_path)
            model_output = run_command(["lsblk", "-d", "-n", "-o", "MODEL", disk_path], capture_output=True, check=False)
            model = model_output.strip() or "Unknown"
            serial_output = run_command(["lsblk", "-d", "-n", "-o", "SERIAL", disk_path], capture_output=True, check=False)
            serial = serial_output.strip() or "Unknown"
        console.print(f"[#81A1C1]Path:[/#81A1C1] [#D8DEE9]{disk_path}[/#D8DEE9]")
        console.print(f"[#81A1C1]Type:[/#81A1C1] [#D8DEE9]{disk_type}[/#D8DEE9]")
        console.print(f"[#81A1C1]Size:[/#81A1C1] [#D8DEE9]{format_size(disk_size)}[/#D8DEE9]")
        console.print(f"[#81A1C1]Model:[/#81A1C1] [#D8DEE9]{model}[/#D8DEE9]")
        console.print(f"[#81A1C1]Serial:[/#81A1C1] [#D8DEE9]{serial}[/#D8DEE9]")
        console.print(f"[#81A1C1]System Disk:[/#81A1C1] [#D8DEE9]{'Yes' if is_system else 'No'}[/#D8DEE9]")
        console.print(f"[#81A1C1]Mounted:[/#81A1C1] [#D8DEE9]{'Yes' if mounted else 'No'}[/#D8DEE9]")
        print_section("Partition Information")
        console.print(f"[#D8DEE9]{output}[/#D8DEE9]")
        print_section("SMART Status")
        if shutil.which("smartctl"):
            try:
                smart_output = run_command(["smartctl", "-a", disk_path], capture_output=True, check=False)
                if "failed" in smart_output.lower():
                    print_warning("SMART status: FAILED - Disk might be failing!")
                elif "passed" in smart_output.lower():
                    print_success("SMART status: PASSED")
                else:
                    print_info("SMART status: Unknown or not available")
                console.print(f"[#D8DEE9]SMART data summary:[/#D8DEE9]")
                for line in smart_output.splitlines():
                    if any(attr in line.lower() for attr in ["reallocated", "pending", "uncorrectable", "health", "life"]):
                        console.print(f"[#D8DEE9]{line}[/#D8DEE9]")
            except Exception:
                print_warning("SMART data could not be retrieved")
        else:
            print_info("smartctl not found - SMART data unavailable")
    except Exception as e:
        print_error(f"Error retrieving disk info: {e}")

def erasure_menu() -> None:
    """Interactively prompt the user to erase a disk."""
    print_header("Disk Erasure")
    disk_path = select_disk("Select a disk to erase (or 'q' to cancel): ")
    if not disk_path:
        print_info("Erasure cancelled")
        return
    method = select_erasure_method()
    if not method:
        print_info("Erasure cancelled")
        return
    passes = DEFAULT_PASSES
    if method == "dod":
        while True:
            try:
                passes_input = input(f"[bold #B48EAD]Number of passes (1-7, default {DEFAULT_PASSES}): [/bold #B48EAD] ")
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
        print_header("Disk Eraser Tool")
        console.print(f"Hostname: [bold #81A1C1]{HOSTNAME}[/bold #81A1C1]")
        console.print(f"Date: [bold #81A1C1]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #81A1C1]")
        console.print("[#D8DEE9]1. List Disks[/#D8DEE9]")
        console.print("[#D8DEE9]2. Show Disk Information[/#D8DEE9]")
        console.print("[#D8DEE9]3. Erase Disk[/#D8DEE9]")
        console.print("[#D8DEE9]4. Exit[/#D8DEE9]")
        choice = input("\n[bold #B48EAD]Enter your choice: [/bold #B48EAD] ").strip()
        if choice == "1":
            display_disk_list(list_disks())
        elif choice == "2":
            show_disk_info()
        elif choice == "3":
            erasure_menu()
        elif choice == "4":
            print_info("Exiting Disk Eraser Tool. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again.")
        input("\n[bold #B48EAD]Press Enter to continue...[/bold #B48EAD]")

# ==============================
# Main Entry Point
# ==============================
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