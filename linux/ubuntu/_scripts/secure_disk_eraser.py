#!/usr/bin/env python3
"""
Enhanced Disk Eraser Tool

A comprehensive utility for secure disk erasure with robust progress tracking,
error handling, and user-friendly interface. The tool supports multiple erasure
methods and provides detailed feedback during the erasure process.

Features:
  • List all available disk devices with detailed information
  • Detect disk types (HDD, SSD, NVMe)
  • Multiple secure erasure methods (zeros, random, DoD-compliant)
  • Real-time progress tracking with ETA and transfer rates
  • Comprehensive error handling and graceful interrupts
  • Nord-themed color interface

Note: This script must be run with root privileges.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# UI Settings
PROGRESS_WIDTH = 40
CHUNK_SIZE = 1024 * 1024  # 1MB for progress updates

# Erasure methods
ERASURE_METHODS = {
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

# Default settings
DEFAULT_METHOD = "zeros"
DEFAULT_PASSES = 1

#####################################
# Nord Theme Colors
#####################################


class Colors:
    """Nord-themed ANSI color codes for terminal output"""

    # Nord color palette
    POLAR_NIGHT1 = "\033[38;5;59m"  # Nord0 (dark gray)
    POLAR_NIGHT2 = "\033[38;5;60m"  # Nord1
    POLAR_NIGHT3 = "\033[38;5;60m"  # Nord2
    POLAR_NIGHT4 = "\033[38;5;67m"  # Nord3 (lighter gray)

    SNOW_STORM1 = "\033[38;5;188m"  # Nord4 (off white)
    SNOW_STORM2 = "\033[38;5;189m"  # Nord5
    SNOW_STORM3 = "\033[38;5;189m"  # Nord6 (white)

    FROST1 = "\033[38;5;109m"  # Nord7 (frost pale blue)
    FROST2 = "\033[38;5;110m"  # Nord8 (frost cyan)
    FROST3 = "\033[38;5;111m"  # Nord9 (frost light blue)
    FROST4 = "\033[38;5;111m"  # Nord10 (frost deep blue)

    AURORA_RED = "\033[38;5;174m"  # Nord11 (red)
    AURORA_ORANGE = "\033[38;5;175m"  # Nord12 (orange)
    AURORA_YELLOW = "\033[38;5;179m"  # Nord13 (yellow)
    AURORA_GREEN = "\033[38;5;142m"  # Nord14 (green)
    AURORA_PURPLE = "\033[38;5;139m"  # Nord15 (purple)

    # Semantic aliases
    HEADER = FROST3
    SUCCESS = AURORA_GREEN
    WARNING = AURORA_YELLOW
    ERROR = AURORA_RED
    INFO = FROST2
    DETAIL = SNOW_STORM1
    PROMPT = AURORA_PURPLE

    # Text styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"


#####################################
# UI and Progress Tracking Classes
#####################################


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

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
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)

            # Calculate rate (bytes per second)
            current_time = time.time()
            time_diff = current_time - self.last_update_time

            if time_diff >= 0.5:  # Update rate every half second
                value_diff = self.current - self.last_update_value
                self.rate = value_diff / time_diff
                self.last_update_time = current_time
                self.last_update_value = self.current

            self._display()

    def _format_size(self, bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"

    def _format_time(self, seconds: int) -> str:
        """Format seconds to human readable time"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        eta = (self.total - self.current) / self.rate if self.rate > 0 else 0

        # Format progress bar with Nord colors
        progress_text = (
            f"\r{Colors.DETAIL}{self.desc}: "
            f"{Colors.FROST3}|{bar}| "
            f"{Colors.SNOW_STORM1}{percent:>5.1f}% "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"{Colors.FROST2}[{self._format_size(self.rate)}/s] "
            f"{Colors.FROST1}[ETA: {self._format_time(eta)}]{Colors.ENDC}"
        )

        sys.stdout.write(progress_text)
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


#####################################
# Helper Functions
#####################################


def format_size(bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 80}")
    print(f"{message.center(80)}")
    print(f"{'═' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """Print formatted section header"""
    print(f"\n{Colors.FROST2}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def print_info(message: str) -> None:
    """Print informational message"""
    print(f"{Colors.INFO}{message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print success message"""
    print(f"{Colors.SUCCESS}{message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """Print warning message"""
    print(f"{Colors.WARNING}Warning: {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print error message"""
    print(f"{Colors.ERROR}Error: {message}{Colors.ENDC}")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run command with error handling"""
    try:
        return subprocess.run(
            cmd, env=env, check=check, text=True, capture_output=capture_output
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stderr") and e.stderr:
            print_error(f"Error details: {e.stderr}")
        raise


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully"""
    print_warning("\nOperation interrupted. Cleaning up...")
    sys.exit(1)


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """Check if script is run with root privileges"""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with sudo or as root user.")
        return False
    return True


def check_dependencies() -> bool:
    """Check if required tools are installed"""
    required_tools = ["lsblk", "dd", "shred"]
    missing_tools = []

    for tool in required_tools:
        if not shutil.which(tool):
            missing_tools.append(tool)

    if missing_tools:
        print_error(f"Required tools are missing: {', '.join(missing_tools)}")
        print_info("Please install the missing tools using your package manager.")
        return False

    return True


def is_valid_device(device_path: str) -> bool:
    """
    Check if the provided path is a valid block device

    Args:
        device_path: Path to the device to check

    Returns:
        bool: True if it's a valid block device, False otherwise
    """
    if not os.path.exists(device_path):
        print_error(f"Device path does not exist: {device_path}")
        return False

    if not os.path.isabs(device_path):
        print_error(f"Device path must be absolute: {device_path}")
        return False

    # Check if it's a block device
    try:
        if not os.path.isdir("/sys/block"):
            print_error("Cannot access /sys/block. Is this a Linux system?")
            return False

        device_name = os.path.basename(device_path)
        if not os.path.exists(f"/sys/block/{device_name}"):
            parent_device = None
            for block in os.listdir("/sys/block"):
                if os.path.exists(f"/sys/block/{block}/{device_name}"):
                    parent_device = block
                    break

            if not parent_device:
                print_error(f"{device_path} is not a recognized block device")
                return False
    except Exception as e:
        print_error(f"Error validating device: {e}")
        return False

    return True


#####################################
# Disk Management Functions
#####################################


class DiskEraser:
    """
    Enhanced utility for secure disk erasure with progress tracking
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize disk eraser

        Args:
            verbose: Enable detailed output
        """
        self.verbose = verbose

    def run_command(
        self, cmd: List[str], capture_output: bool = True, check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a shell command safely

        Args:
            cmd: Command to execute
            capture_output: Capture command output
            check: Raise exception on non-zero exit

        Returns:
            Command execution result
        """
        if self.verbose:
            print_info(f"Running: {' '.join(cmd)}")

        try:
            result = run_command(cmd, capture_output=capture_output, check=check)
            return result
        except subprocess.CalledProcessError as e:
            print_error(f"Command failed: {' '.join(cmd)}")
            if hasattr(e, "stdout") and e.stdout:
                print_info(f"Output: {e.stdout}")
            if hasattr(e, "stderr") and e.stderr:
                print_error(f"Error: {e.stderr}")
            raise

    def list_disks(self) -> List[Dict[str, str]]:
        """
        List all block devices with detailed information

        Returns:
            List of dictionaries containing disk information
        """
        try:
            # Get basic disk information
            output = self.run_command(
                ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MODEL,MOUNTPOINT", "--json"]
            )

            result = []

            # Parse lsblk output using standard library
            import json

            data = json.loads(output.stdout)
            devices = data.get("blockdevices", [])

            for device in devices:
                name = device.get("name", "")
                if not name:
                    continue

                # Add device type
                device_type = self.detect_disk_type(name)
                device["device_type"] = device_type

                # Add full path
                device["path"] = f"/dev/{name}"

                # Check if system disk
                device["system_disk"] = self.is_system_disk(name)

                # Add device to result
                result.append(device)

            return result

        except Exception as e:
            print_error(f"Error listing disks: {e}")
            return []

    def print_disk_list(self, disks: List[Dict[str, str]]) -> None:
        """
        Print formatted disk list

        Args:
            disks: List of disk dictionaries
        """
        if not disks:
            print_info("No disks found")
            return

        print_section("Available Disks")

        # Print header
        header = f"{Colors.FROST3}{'NAME':<12} {'SIZE':<10} {'TYPE':<8} {'PATH':<12} {'SYSTEM':<8} {'MODEL':<30}{Colors.ENDC}"
        print(header)
        print(f"{Colors.FROST2}{'-' * 80}{Colors.ENDC}")

        # Print each disk
        for disk in disks:
            name = disk.get("name", "")
            size = disk.get("size", "")
            disk_type = disk.get("device_type", "Unknown")
            path = disk.get("path", "")
            system_disk = "✓" if disk.get("system_disk", False) else ""
            model = disk.get("model", "").strip() or "N/A"

            # Colorize system disks
            if disk.get("system_disk", False):
                name_color = Colors.AURORA_YELLOW
                is_system = f"{Colors.AURORA_YELLOW}✓{Colors.ENDC}"
            else:
                name_color = Colors.SNOW_STORM1
                is_system = ""

            # Colorize based on disk type
            if disk_type == "SSD":
                type_color = Colors.FROST3
            elif disk_type == "NVMe":
                type_color = Colors.AURORA_PURPLE
            else:  # HDD or unknown
                type_color = Colors.FROST1

            print(
                f"{name_color}{name:<12}{Colors.ENDC} "
                f"{Colors.DETAIL}{size:<10}{Colors.ENDC} "
                f"{type_color}{disk_type:<8}{Colors.ENDC} "
                f"{Colors.SNOW_STORM1}{path:<12}{Colors.ENDC} "
                f"{is_system:<8} "
                f"{Colors.DETAIL}{model:<30}{Colors.ENDC}"
            )

    def detect_disk_type(self, disk: str) -> str:
        """
        Detect disk type (HDD, SSD, NVMe)

        Args:
            disk: Disk device name (without /dev/ prefix)

        Returns:
            Disk type string
        """
        try:
            # Check if NVMe
            if disk.startswith("nvme"):
                return "NVMe"

            # Check if rotational (HDD)
            rotational_path = f"/sys/block/{disk}/queue/rotational"
            if os.path.exists(rotational_path):
                with open(rotational_path, "r") as f:
                    return "HDD" if f.read().strip() == "1" else "SSD"

            return "Unknown"
        except Exception:
            return "Unknown"

    def is_system_disk(self, disk: str) -> bool:
        """
        Check if a disk is likely a system disk

        Args:
            disk: Disk device name (without /dev/ prefix)

        Returns:
            True if system disk, False otherwise
        """
        try:
            # Get root mount device
            root_mount = self.run_command(["findmnt", "-n", "-o", "SOURCE", "/"])
            root_device = root_mount.stdout.strip()

            # Extract the base device (e.g., /dev/sda1 -> sda)
            if root_device.startswith("/dev/"):
                root_device = root_device[5:]  # Remove /dev/ prefix

            # Remove partition number if present
            import re

            base_device = re.sub(r"\d+$", "", root_device)

            # Check if this is the system disk
            return disk == base_device
        except Exception:
            # If in doubt, assume it might be a system disk
            return True

    def is_mounted(self, disk: str) -> bool:
        """
        Check if a disk or any of its partitions are mounted

        Args:
            disk: Full disk device path (e.g., /dev/sda)

        Returns:
            True if mounted, False otherwise
        """
        try:
            # Check if the disk itself is mounted
            output = self.run_command(["mount"])
            if disk in output.stdout:
                return True

            # Check if any partitions are mounted
            disk_name = os.path.basename(disk)
            output = self.run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"])

            for line in output.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                    return True

            return False
        except Exception as e:
            print_error(f"Error checking mount status: {e}")
            return True  # Assume mounted for safety

    def get_disk_size(self, disk: str) -> int:
        """
        Get the size of a disk in bytes

        Args:
            disk: Full disk device path

        Returns:
            Disk size in bytes
        """
        try:
            disk_name = os.path.basename(disk)
            size_path = f"/sys/block/{disk_name}/size"

            if os.path.exists(size_path):
                with open(size_path, "r") as f:
                    # Size is in 512-byte sectors
                    return int(f.read().strip()) * 512

            # Fall back to lsblk if sysfs fails
            output = self.run_command(["lsblk", "-b", "-d", "-n", "-o", "SIZE", disk])
            return int(output.stdout.strip())
        except Exception as e:
            print_error(f"Error getting disk size: {e}")
            # Default to a large size to ensure progress works
            return 1000 * 1024 * 1024 * 1024  # 1 TB

    def wipe_with_dd(
        self, disk: str, source: str = "/dev/zero", bs: int = 4 * 1024 * 1024
    ) -> bool:
        """
        Wipe disk using dd with progress tracking

        Args:
            disk: Disk device path
            source: Input source (/dev/zero or /dev/urandom)
            bs: Block size in bytes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get disk size
            disk_size = self.get_disk_size(disk)

            # Create a progress bar
            progress = ProgressBar(disk_size, desc=f"Wiping {os.path.basename(disk)}")

            # Build dd command
            dd_cmd = [
                "dd",
                f"if={source}",
                f"of={disk}",
                f"bs={bs}",
                "conv=fsync,noerror",
            ]

            # Execute in background process to monitor progress
            process = subprocess.Popen(
                dd_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Set up monitoring
            bytes_written = 0

            # Create a thread to send SIGUSR1 to dd periodically for status
            stop_event = threading.Event()

            def signal_dd():
                while not stop_event.is_set():
                    if process.poll() is not None:
                        break
                    try:
                        # Send SIGUSR1 to dd to get progress report
                        process.send_signal(signal.SIGUSR1)
                    except Exception:
                        pass
                    time.sleep(1)

            # Start the monitoring thread
            monitor_thread = threading.Thread(target=signal_dd)
            monitor_thread.daemon = True
            monitor_thread.start()

            # Monitor dd output
            try:
                while True:
                    line = process.stderr.readline()
                    if not line and process.poll() is not None:
                        break

                    # Parse dd output
                    if "bytes" in line:
                        try:
                            # Extract bytes written
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if (
                                    part.isdigit()
                                    and i < len(parts) - 1
                                    and parts[i + 1].startswith("byte")
                                ):
                                    current_bytes = int(part)
                                    # Update progress with delta
                                    delta = current_bytes - bytes_written
                                    if delta > 0:
                                        progress.update(delta)
                                        bytes_written = current_bytes
                                    break
                        except Exception:
                            # Just update with block size if parsing fails
                            progress.update(bs)
            finally:
                # Clean up monitoring
                stop_event.set()

                # Wait for process to complete
                returncode = process.wait()

                # Ensure progress bar shows completion
                if returncode == 0:
                    progress.current = progress.total
                    progress._display()
                    print()  # Add a newline

            return returncode == 0

        except Exception as e:
            print_error(f"Error during disk wiping: {e}")
            return False

    def wipe_with_shred(self, disk: str, passes: int = 3) -> bool:
        """
        Securely erase disk using shred with progress tracking

        Args:
            disk: Disk device path
            passes: Number of overwrite passes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get disk size
            disk_size = self.get_disk_size(disk)

            # Create a progress bar
            progress = ProgressBar(
                disk_size * (passes + 1),  # +1 for the zero pass
                desc=f"Secure erase of {os.path.basename(disk)}",
            )

            # Build shred command
            shred_cmd = [
                "shred",
                "-n",
                str(passes),  # Number of passes
                "-z",  # Final pass with zeros
                "-v",  # Verbose mode
                disk,
            ]

            # Execute in background process to monitor progress
            process = subprocess.Popen(
                shred_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Track current pass and progress
            current_pass = 1
            current_pass_bytes = 0

            # Process shred output
            for line in iter(process.stderr.readline, ""):
                # Update progress based on shred output
                if "overwriting" in line and "pass" in line:
                    # Extract pass information
                    current_pass_bytes = 0

                    # Format: "shred: /dev/sdX: pass 1/3 (random)..."
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "pass" and i + 1 < len(parts):
                                pass_info = parts[i + 1].split("/")
                                if len(pass_info) == 2:
                                    current_pass = int(pass_info[0])
                    except Exception:
                        pass

                # Extract progress within current pass
                elif "%" in line:
                    try:
                        # Format: " xx.x% done, xx:xx left"
                        pct = float(line.split("%")[0].strip())
                        new_bytes = int(disk_size * pct / 100)

                        # Calculate progress delta
                        delta = new_bytes - current_pass_bytes
                        if delta > 0:
                            progress.update(delta)
                            current_pass_bytes = new_bytes
                    except Exception:
                        # Just update with a chunk if parsing fails
                        progress.update(CHUNK_SIZE)

            # Wait for process to complete
            returncode = process.wait()

            # Ensure progress bar shows completion
            if returncode == 0:
                progress.current = progress.total
                progress._display()
                print()  # Add a newline

            return returncode == 0

        except Exception as e:
            print_error(f"Error during secure erase: {e}")
            return False

    def erase_disk(self, disk: str, method: str, passes: int = 1) -> bool:
        """
        Erase a disk using the specified method

        Args:
            disk: Disk device path
            method: Erasure method (zeros, random, dod)
            passes: Number of passes for methods that support it

        Returns:
            True if successful, False otherwise
        """
        if method not in ERASURE_METHODS:
            print_error(f"Unknown erasure method: {method}")
            return False

        # Validate disk
        if not is_valid_device(disk):
            return False

        # Check if mounted
        if self.is_mounted(disk):
            print_warning(f"{disk} is currently mounted")
            print_info("Attempting to unmount...")

            # Try to unmount
            disk_name = os.path.basename(disk)
            try:
                self.run_command(["umount", disk], check=False)

                # Also try to unmount all partitions
                output = self.run_command(["lsblk", "-n", "-o", "NAME,MOUNTPOINT"])
                for line in output.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].startswith(disk_name) and parts[1]:
                        self.run_command(["umount", f"/dev/{parts[0]}"], check=False)

            except Exception as e:
                print_error(f"Failed to unmount: {e}")

            # Check if still mounted
            if self.is_mounted(disk):
                print_warning(f"{disk} is still mounted and cannot be safely erased")
                choice = input(
                    f"{Colors.PROMPT}Force unmount and continue? (y/N): {Colors.ENDC}"
                ).lower()
                if choice != "y":
                    print_info("Disk erasure cancelled")
                    return False

                # Try forced unmount
                try:
                    self.run_command(["umount", "-f", disk], check=False)
                except Exception:
                    pass

        # Final safety check
        print_section("Disk Erasure Confirmation")
        print_warning(f"You are about to PERMANENTLY ERASE {disk}")
        print_info(f"Erasure method: {ERASURE_METHODS[method]['name']}")
        print_info(f"Description: {ERASURE_METHODS[method]['description']}")

        if method == "dod":
            print_info(f"Passes: {passes}")

        # Additional warning for system disk
        disk_name = os.path.basename(disk)
        if self.is_system_disk(disk_name):
            print_error("⚠️  WARNING: THIS APPEARS TO BE A SYSTEM DISK! ⚠️")
            print_error("Erasing this disk will destroy your operating system!")

        # Final confirmation
        confirm = input(
            f"\n{Colors.AURORA_RED}{Colors.BOLD}Type 'YES' to confirm disk erasure: {Colors.ENDC}"
        )
        if confirm != "YES":
            print_info("Disk erasure cancelled")
            return False

        print_header(f"Starting Disk Erasure - {ERASURE_METHODS[method]['name']}")

        # Execute erasure based on method
        if method == "zeros":
            success = self.wipe_with_dd(disk, source="/dev/zero")
        elif method == "random":
            success = self.wipe_with_dd(disk, source="/dev/urandom")
        elif method == "dod":
            success = self.wipe_with_shred(disk, passes=passes)
        else:
            print_error(f"Unsupported erasure method: {method}")
            return False

        if success:
            print_success(f"Disk {disk} erasure completed successfully")
        else:
            print_error(f"Disk {disk} erasure failed")

        return success


#####################################
# Main Function
#####################################


def main() -> None:
    """Main execution function"""

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check requirements
    if not check_root_privileges():
        sys.exit(1)

    if not check_dependencies():
        sys.exit(1)

    # Parse arguments
    parser = argparse.ArgumentParser(description="Enhanced Disk Eraser Tool")
    parser.add_argument(
        "-l", "--list", action="store_true", help="List available disks"
    )
    parser.add_argument(
        "-e", "--erase", type=str, help="Erase specified disk device (e.g., /dev/sdb)"
    )
    parser.add_argument(
        "-m",
        "--method",
        type=str,
        choices=list(ERASURE_METHODS.keys()),
        default=DEFAULT_METHOD,
        help="Erasure method to use",
    )
    parser.add_argument(
        "-p",
        "--passes",
        type=int,
        default=DEFAULT_PASSES,
        help="Number of passes for DoD erasure method",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation (use with caution!)"
    )

    args = parser.parse_args()

    # Create disk eraser instance
    eraser = DiskEraser(verbose=args.verbose)

    # Process command-line arguments
    if args.list:
        disks = eraser.list_disks()
        eraser.print_disk_list(disks)
        return

    if args.erase:
        if os.path.exists(args.erase):
            method = args.method
            passes = args.passes

            if method == "dod" and passes < 1:
                print_error("Passes must be at least 1")
                return

            eraser.erase_disk(args.erase, method, passes)
            return
        else:
            print_error(f"Disk device not found: {args.erase}")
            return

    # No arguments provided - show interactive menu
    print_header("Enhanced Disk Eraser Tool")
    print_info(f"System: {os.uname().sysname} {os.uname().release}")
    print_info(f"Hostname: {HOSTNAME}")
    print_info(f"Available erasure methods:")

    for key, method in ERASURE_METHODS.items():
        print(
            f"  • {Colors.FROST3}{method['name']}{Colors.ENDC}: {method['description']}"
        )

    # Interactive menu
    while True:
        print_section("Main Menu")
        print(f"{Colors.SNOW_STORM1}1. List Disks{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}2. Erase Disk{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}3. Exit{Colors.ENDC}")

        choice = input(f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC}").strip()

        if choice == "1":
            disks = eraser.list_disks()
            eraser.print_disk_list(disks)

        elif choice == "2":
            # List disks first
            disks = eraser.list_disks()
            eraser.print_disk_list(disks)

            # Prompt for disk selection
            disk = input(
                f"\n{Colors.PROMPT}Enter disk device to erase (e.g., /dev/sdb): {Colors.ENDC}"
            ).strip()

            # Validate disk exists
            if not os.path.exists(disk):
                print_error(f"Disk device not found: {disk}")
                continue

            # Prompt for erasure method
            print_section("Select Erasure Method")
            for i, (key, method) in enumerate(ERASURE_METHODS.items(), 1):
                print(
                    f"{Colors.SNOW_STORM1}{i}. {method['name']}{Colors.ENDC}: {method['description']}"
                )

            method_choice = input(
                f"\n{Colors.PROMPT}Select method (1-{len(ERASURE_METHODS)}): {Colors.ENDC}"
            ).strip()

            # Validate method choice
            try:
                method_idx = int(method_choice) - 1
                if method_idx < 0 or method_idx >= len(ERASURE_METHODS):
                    raise ValueError()

                method = list(ERASURE_METHODS.keys())[method_idx]
            except ValueError:
                print_error("Invalid choice")
                continue

            # Prompt for passes if DoD method
            passes = DEFAULT_PASSES
            if method == "dod":
                passes_input = input(
                    f"{Colors.PROMPT}Number of passes (default {DEFAULT_PASSES}): {Colors.ENDC}"
                ).strip()
                if passes_input.isdigit() and int(passes_input) > 0:
                    passes = int(passes_input)

            # Execute erasure
            eraser.erase_disk(disk, method, passes)

        elif choice == "3":
            print_info("Exiting disk eraser. Goodbye!")
            break

        else:
            print_error("Invalid choice. Please try again.")

        print()  # Add a newline for spacing


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
