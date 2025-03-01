#!/usr/bin/env python3
"""
Enhanced Disk Eraser Tool

This utility securely erases disk devices using various methods (zeros, random data,
DoD‑compliant). It provides detailed progress tracking, error handling, and a Nord‑themed
user interface. This script must be run with root privileges.

Features:
  • List available disk devices with detailed information
  • Detect disk types (HDD, SSD, NVMe)
  • Multiple secure erasure methods (zeros, random, DoD‑compliant)
  • Real‑time progress tracking with ETA and transfer rates
  • Comprehensive error handling and graceful interrupts
  • Nord‑themed color interface
"""

import atexit
import json
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
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
HOSTNAME = socket.gethostname()
PROGRESS_WIDTH = 40
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress updates

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
        "name": "DoD 3‑pass",
        "description": "DoD‑compliant 3‑pass wipe (most secure)",
        "command": "shred",
        "args": ["-n", "3", "-z", "-v"],
    },
}

DEFAULT_METHOD = "zeros"
DEFAULT_PASSES = 1

# ------------------------------
# Nord‑Themed Colors & Console Setup
# ------------------------------
# The following colors are defined using Nord palette hex values.
class Colors:
    HEADER = "#5E81AC"      # Nord10
    SUCCESS = "#8FBCBB"     # Nord7
    WARNING = "#EBCB8B"     # Nord13
    ERROR = "#BF616A"       # Nord11
    INFO = "#88C0D0"        # Nord8
    DETAIL = "#D8DEE9"      # Nord4
    PROMPT = "#B48EAD"      # Nord15
    BOLD = "[bold]"
    END = "[/bold]"

console = Console()

def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {Colors.HEADER}")

def print_section(text: str) -> None:
    """Print a formatted section header."""
    console.print(f"\n[bold {Colors.INFO}]{text}[/bold {Colors.INFO}]")

def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{Colors.INFO}]{message}[/{Colors.INFO}]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {Colors.SUCCESS}]✓ {message}[/bold {Colors.SUCCESS}]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {Colors.WARNING}]⚠ {message}[/bold {Colors.WARNING}]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {Colors.ERROR}]✗ {message}[/bold {Colors.ERROR}]")

def format_size(num_bytes: float) -> str:
    """Convert bytes to a human‑readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"

# ------------------------------
# Progress Tracking Class
# ------------------------------
class ProgressBar:
    """Thread‑safe progress bar with rate and ETA display."""
    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.last_update_time = time.time()
        self.last_update_value = 0
        self.rate = 0  # bytes per second

    def update(self, amount: int) -> None:
        with self._lock:
            self.current = min(self.current + amount, self.total)
            now = time.time()
            if now - self.last_update_time >= 0.5:
                self.rate = (self.current - self.last_update_value) / (now - self.last_update_time)
                self.last_update_time = now
                self.last_update_value = self.current
            self._display()

    def _display(self) -> None:
        filled = int(self.width * self.current / self.total) if self.total else 0
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100 if self.total else 0
        elapsed = time.time() - self.start_time
        eta = (self.total - self.current) / self.rate if self.rate > 0 else 0
        progress_line = (f"\r[{Colors.DETAIL}]{self.desc}:{Colors.END} |"
                         f"[{Colors.HEADER}]{bar}{Colors.END}| "
                         f"[{Colors.INFO}]{percent:5.1f}%{Colors.END} "
                         f"({format_size(self.current)}/{format_size(self.total)}) "
                         f"[{format_size(self.rate)}/s] "
                         f"[ETA: {format_time(eta)}]")
        sys.stdout.write(progress_line)
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write("\n")

# ------------------------------
# Helper Functions
# ------------------------------
def run_command(cmd: List[str], env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    """Run a shell command with error handling."""
    try:
        return subprocess.run(cmd, env=env, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stderr:
            print_error(f"Error details: {e.stderr.strip()}")
        raise

def signal_handler(sig, frame) -> None:
    """Handle interrupts gracefully."""
    print_warning("\nOperation interrupted. Exiting...")
    sys.exit(1)

# ------------------------------
# Validation Functions
# ------------------------------
def check_root_privileges() -> bool:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with sudo or as root.")
        return False
    return True

def check_dependencies() -> bool:
    """Verify that required system tools are available."""
    required = ["lsblk", "dd", "shred"]
    missing = [tool for tool in required if not shutil.which(tool)]
    if missing:
        print_error(f"Missing required tools: {', '.join(missing)}")
        print_info("Please install them using your package manager.")
        return False
    return True

def is_valid_device(device_path: str) -> bool:
    """Check if the provided path is a valid block device."""
    if not os.path.exists(device_path):
        print_error(f"Device not found: {device_path}")
        return False
    if not os.path.isabs(device_path):
        print_error("Device path must be absolute.")
        return False
    # For Linux, check if device exists in /sys/block or as a partition.
    device_name = os.path.basename(device_path)
    if not os.path.exists(f"/sys/block/{device_name}") and not any(
        os.path.exists(f"/sys/block/{bd}/{device_name}") for bd in os.listdir("/sys/block")
    ):
        print_error(f"{device_path} is not recognized as a block device.")
        return False
    return True

# ------------------------------
# Disk Eraser Class
# ------------------------------
class DiskEraser:
    """
    Securely erase disks using various methods.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def run_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """Wrapper for running shell commands."""
        if self.verbose:
            print_info(f"Running: {' '.join(cmd)}")
        return run_command(cmd)

    def list_disks(self) -> List[Dict[str, Any]]:
        """List all block devices using lsblk (JSON output)."""
        try:
            result = self.run_command(["lsblk", "-d", "-o", "NAME,SIZE,MODEL", "--json"])
            data = json.loads(result.stdout)
            disks = data.get("blockdevices", [])
            for disk in disks:
                disk["path"] = f"/dev/{disk.get('name', '')}"
                disk["device_type"] = self.detect_disk_type(disk.get("name", ""))
                disk["system_disk"] = self.is_system_disk(disk.get("name", ""))
            return disks
        except Exception as e:
            print_error(f"Error listing disks: {e}")
            return []

    def print_disk_list(self, disks: List[Dict[str, Any]]) -> None:
        """Display disk information in a formatted table."""
        if not disks:
            print_info("No disks found.")
            return
        print_section("Available Disks")
        header = f"[bold {Colors.FROST3}]{'NAME':<12} {'SIZE':<10} {'TYPE':<8} {'PATH':<12} {'SYSTEM':<8} {'MODEL':<30}[/bold {Colors.FROST3}]"
        console.print(header)
        console.print(f"[{Colors.FROST2}]{'─' * 80}[/{Colors.FROST2}]")
        for disk in disks:
            name = disk.get("name", "")
            size = disk.get("size", "")
            dtype = disk.get("device_type", "Unknown")
            path = disk.get("path", "")
            system = "✓" if disk.get("system_disk", False) else ""
            model = disk.get("model", "").strip() or "N/A"
            name_style = Colors.AURORA_YELLOW if disk.get("system_disk", False) else Colors.SNOW_STORM1
            type_color = Colors.FROST3 if dtype == "SSD" else (Colors.AURORA_PURPLE if dtype == "NVMe" else Colors.FROST1)
            console.print(f"[{name_style}]{name:<12}[/{name_style}] "
                          f"[{Colors.DETAIL}]{size:<10}[/{Colors.DETAIL}] "
                          f"[{type_color}]{dtype:<8}[/{type_color}] "
                          f"[{Colors.SNOW_STORM1}]{path:<12}[/{Colors.SNOW_STORM1}] "
                          f"{system:<8} "
                          f"[{Colors.DETAIL}]{model:<30}[/{Colors.DETAIL}]")

    def detect_disk_type(self, disk: str) -> str:
        """Detect whether disk is NVMe, HDD, or SSD."""
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

    def is_system_disk(self, disk: str) -> bool:
        """Check if a disk is likely the system disk."""
        try:
            result = self.run_command(["findmnt", "-n", "-o", "SOURCE", "/"])
            root_device = result.stdout.strip()
            if root_device.startswith("/dev/"):
                root_device = root_device[5:]
            base = re.sub(r"\d+$", "", root_device)
            return disk == base
        except Exception:
            return True

    def is_mounted(self, disk: str) -> bool:
        """Check if a disk or its partitions are mounted."""
        try:
            output = self.run_command(["mount"])
            if disk in output.stdout:
                return True
            disk_name = os.path.basename(disk)
            output = self.run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"])
            for line in output.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                    return True
            return False
        except Exception as e:
            print_error(f"Error checking mount status: {e}")
            return True

    def get_disk_size(self, disk: str) -> int:
        """Return disk size in bytes."""
        try:
            disk_name = os.path.basename(disk)
            size_path = f"/sys/block/{disk_name}/size"
            if os.path.exists(size_path):
                with open(size_path, "r") as f:
                    return int(f.read().strip()) * 512
            output = self.run_command(["lsblk", "-b", "-d", "-n", "-o", "SIZE", disk])
            return int(output.stdout.strip())
        except Exception as e:
            print_error(f"Error getting disk size: {e}")
            return 1_000_000_000_000  # Default to 1 TB

    def wipe_with_dd(self, disk: str, source: str) -> bool:
        """Erase disk using dd (with /dev/zero or /dev/urandom)."""
        try:
            disk_size = self.get_disk_size(disk)
            progress = ProgressBar(disk_size, desc=f"Wiping {Path(disk).name}")
            dd_cmd = ["dd", f"if={source}", f"of={disk}", f"bs={4 * 1024 * 1024}", "conv=fsync,noerror"]
            process = subprocess.Popen(dd_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                                       text=True, bufsize=1, universal_newlines=True)
            bytes_written = 0
            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if "bytes" in line:
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.isdigit() and i < len(parts) - 1 and parts[i + 1].startswith("byte"):
                                current = int(part)
                                delta = current - bytes_written
                                if delta > 0:
                                    progress.update(delta)
                                    bytes_written = current
                                break
                    except Exception:
                        progress.update(CHUNK_SIZE)
            returncode = process.wait()
            if returncode == 0:
                progress.current = progress.total
                progress._display()
                print()
            return returncode == 0
        except Exception as e:
            print_error(f"Error during dd wipe: {e}")
            return False

    def wipe_with_shred(self, disk: str, passes: int) -> bool:
        """Erase disk using shred (DoD‑compliant)."""
        try:
            disk_size = self.get_disk_size(disk)
            total_work = disk_size * (passes + 1)
            progress = ProgressBar(total_work, desc=f"Erasing {Path(disk).name}")
            shred_cmd = ["shred", "-n", str(passes), "-z", "-v", disk]
            process = subprocess.Popen(shred_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                                       text=True, bufsize=1, universal_newlines=True)
            current_bytes = 0
            for line in iter(process.stderr.readline, ""):
                if "overwriting" in line:
                    current_bytes = 0
                elif "%" in line:
                    try:
                        pct = float(line.split("%")[0].strip())
                        new_bytes = int(disk_size * pct / 100)
                        delta = new_bytes - current_bytes
                        if delta > 0:
                            progress.update(delta)
                            current_bytes = new_bytes
                    except Exception:
                        progress.update(CHUNK_SIZE)
            returncode = process.wait()
            if returncode == 0:
                progress.current = progress.total
                progress._display()
                print()
            return returncode == 0
        except Exception as e:
            print_error(f"Error during shred wipe: {e}")
            return False

    def erase_disk(self, disk: str, method: str, passes: int = DEFAULT_PASSES, force: bool = False) -> bool:
        """Erase the specified disk using the chosen method."""
        if method not in ERASURE_METHODS:
            print_error(f"Unknown erasure method: {method}")
            return False
        if not is_valid_device(disk):
            return False
        if self.is_mounted(disk):
            print_warning(f"{disk} is currently mounted. Attempting to unmount...")
            try:
                self.run_command(["umount", disk])
                output = self.run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"])
                disk_name = os.path.basename(disk)
                for line in output.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                        self.run_command(["umount", f"/dev/{parts[0]}"])
            except Exception as e:
                print_error(f"Failed to unmount: {e}")
            if self.is_mounted(disk):
                if not force:
                    choice = input(f"[bold {Colors.PROMPT}]Force unmount and continue? (y/N): [/{Colors.PROMPT}]").lower()
                    if choice != "y":
                        print_info("Disk erasure cancelled")
                        return False
                try:
                    self.run_command(["umount", "-f", disk])
                except Exception:
                    pass
        print_section("Disk Erasure Confirmation")
        print_warning(f"You are about to PERMANENTLY ERASE {disk}")
        print_info(f"Erasure method: {ERASURE_METHODS[method]['name']}")
        print_info(f"Description: {ERASURE_METHODS[method]['description']}")
        if method == "dod":
            print_info(f"Passes: {passes}")
        disk_name = os.path.basename(disk)
        if self.is_system_disk(disk_name):
            print_error("⚠ WARNING: THIS APPEARS TO BE A SYSTEM DISK! Erasing it will destroy your OS!")
        if not force:
            confirm = input(f"\n[bold {Colors.AURORA_RED}]Type 'YES' to confirm disk erasure: [/{Colors.AURORA_RED}]")
            if confirm != "YES":
                print_info("Disk erasure cancelled")
                return False
        print_header(f"Starting Disk Erasure - {ERASURE_METHODS[method]['name']}")
        if method in ["zeros", "random"]:
            source = "/dev/zero" if method == "zeros" else "/dev/urandom"
            success = self.wipe_with_dd(disk, source)
        elif method == "dod":
            success = self.wipe_with_shred(disk, passes)
        else:
            print_error(f"Unsupported method: {method}")
            return False
        if success:
            print_success(f"Disk {disk} erased successfully")
        else:
            print_error(f"Disk {disk} erasure failed")
        return success

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.group()
def cli() -> None:
    """Enhanced Disk Eraser Tool"""
    print_header("Disk Eraser Tool")
    console.print(f"Hostname: [bold {Colors.INFO}]{HOSTNAME}[/{Colors.INFO}]")
    console.print(f"Date: [bold {Colors.INFO}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/{Colors.INFO}]")
    if not check_root_privileges():
        sys.exit(1)
    if not check_dependencies():
        sys.exit(1)

@cli.command()
def list() -> None:
    """List available disk devices."""
    eraser = DiskEraser()
    disks = eraser.list_disks()
    eraser.print_disk_list(disks)

@cli.command()
@click.option("-d", "--disk", required=True, help="Disk device to erase (e.g., /dev/sdb)")
@click.option("-m", "--method", type=click.Choice(list(ERASURE_METHODS.keys())), default=DEFAULT_METHOD, help="Erasure method")
@click.option("-p", "--passes", type=int, default=DEFAULT_PASSES, help="Number of passes for DoD method")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation (use with caution)")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
def erase(disk: str, method: str, passes: int, yes: bool, verbose: bool) -> None:
    """Erase a specified disk device securely."""
    eraser = DiskEraser(verbose=verbose)
    if not os.path.exists(disk):
        print_error(f"Disk device not found: {disk}")
        sys.exit(1)
    eraser.erase_disk(disk, method, passes, force=yes)

def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)

atexit.register(lambda: console.print("[dim]Cleaning up resources...[/dim]"))
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(128 + sig))

if __name__ == "__main__":
    main()