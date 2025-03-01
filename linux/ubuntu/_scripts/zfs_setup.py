#!/usr/bin/env python3
"""
Unified ZFS Management Script
-----------------------------

This utility combines two core functions:
  • Enhanced ZFS Setup – installs required packages, enables services, creates mount points,
    imports and configures ZFS pools, mounts datasets, and verifies the setup.
  • ZFS Pool Expansion – enables autoexpand, performs online expansion of pools, and validates
    the expansion against expected sizes.

The script uses a Nord-themed CLI interface with progress tracking and interactive prompts.
It is designed for Linux systems and must be run with root privileges.

Version: 1.0.0
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, TextIO

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------

# Version info
VERSION = "1.0.0"

# Defaults for ZFS setup
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

# Defaults for expansion script
SIZE_UNITS = {"K": 1024**1, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # Lower bound (in TiB) for a 2TB drive
EXPECTED_SIZE_TIB_UPPER = 2.0  # Upper bound (in TiB) for a 2TB drive

# Terminal width
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# ------------------------------
# Nord-Themed Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold #88C0D0]{border}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]  {title.center(TERM_WIDTH - 4)}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]{border}[/bold #88C0D0]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[#81A1C1]ℹ {message}[/#81A1C1]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold #A3BE8C]✓ {message}[/bold #A3BE8C]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #EBCB8B]⚠ {message}[/bold #EBCB8B]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {message}[/bold #BF616A]")


def print_step(text: str, step_num: int = None, total_steps: int = None) -> None:
    """Print a step description."""
    step_info = (
        f"[{step_num}/{total_steps}] "
        if (step_num is not None and total_steps is not None)
        else ""
    )
    console.print(f"[#88C0D0]→ {step_info}{text}[/#88C0D0]")


def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging(
    log_file: str = DEFAULT_LOG_FILE, log_level: int = logging.INFO
) -> None:
    """Configure logging for the script."""
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
            os.chmod(log_file, 0o600)  # Secure permissions
            logging.info("Set log file permissions to 0600")
        except Exception as e:
            logging.warning(f"Could not set log file permissions: {e}")

        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add cleanup tasks here


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ------------------------------
# Progress Tracking Classes
# ------------------------------
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

    def set_progress(self, value: int) -> None:
        with self._lock:
            self.current = min(max(0, value), self.total)
            self._display()

    def finish(self) -> None:
        with self._lock:
            self.current = self.total
            self.completed = True
            self._display()
            print()

    def _display(self) -> None:
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100
        elapsed = time.time() - self.start_time

        # Calculate ETA
        avg_rate = sum(self.rates) / max(1, len(self.rates)) if self.rates else 0
        eta = (self.total - self.current) / max(0.1, avg_rate) if avg_rate > 0 else 0

        if eta > 3600:
            eta_str = f"{eta / 3600:.1f}h"
        elif eta > 60:
            eta_str = f"{eta / 60:.1f}m"
        else:
            eta_str = f"{eta:.0f}s"

        # Create progress status using rich console
        console.print(
            f"\r[#88C0D0]{self.desc}:[/#88C0D0] |[#5E81AC]{bar}[/#5E81AC]| "
            f"[#D8DEE9]{percent:5.1f}%[/#D8DEE9] "
            f"[ETA: {eta_str}]",
            end="",
        )

        if self.completed:
            elapsed_str = format_time(elapsed)
            console.print(
                f"\r[#88C0D0]{self.desc}:[/#88C0D0] |[#5E81AC]{bar}[/#5E81AC]| "
                f"[#A3BE8C]100.0%[/#A3BE8C] "
                f"[Completed in: {elapsed_str}]"
            )


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
                    f"\r[#5E81AC]{self.spinner_chars[self.current]}[/#5E81AC] "
                    f"[#88C0D0]{self.message}[/#88C0D0] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)  # Update spinner every 100ms

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

            if elapsed > 3600:
                time_str = f"{elapsed / 3600:.1f}h"
            elif elapsed > 60:
                time_str = f"{elapsed / 60:.1f}m"
            else:
                time_str = f"{elapsed:.1f}s"

            # Clear the line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            completion_message = (
                message if message else ("Completed" if success else "Failed")
            )

            if success:
                console.print(
                    f"[#A3BE8C]✓[/#A3BE8C] [#88C0D0]{self.message}[/#88C0D0] [#A3BE8C]{completion_message}[/#A3BE8C] in {time_str}"
                )
            else:
                console.print(
                    f"[#BF616A]✗[/#BF616A] [#88C0D0]{self.message}[/#88C0D0] [#BF616A]{completion_message}[/#BF616A] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ------------------------------
# Helper Functions
# ------------------------------
def run_command(
    command: Union[str, List[str]],
    error_message: Optional[str] = None,
    check: bool = True,
    spinner_text: Optional[str] = None,
    capture_output: bool = True,
    env: Optional[Dict[str, str]] = None,
    verbose: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Run a command with error handling and optional spinner."""
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
            stdout = None
            stderr = None

        if spinner:
            spinner.stop(success=True)
        return True, stdout, stderr
    except subprocess.CalledProcessError as e:
        error_output = (
            e.stderr.strip() if hasattr(e, "stderr") and e.stderr else "No error output"
        )
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


def run_command_simple(command: str, verbose: bool = False) -> Optional[str]:
    """Helper that runs a command and returns stdout if successful, else None."""
    success, stdout, _ = run_command(command, check=False, verbose=verbose)
    return stdout if success else None


def check_root_privileges() -> bool:
    """Check if script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with sudo or as root.")
        return False
    return True


def check_dependencies(verbose: bool = False) -> bool:
    """Check if required dependencies are installed."""
    print_step("Checking for required commands")
    progress = ProgressBar(total=len(REQUIRED_COMMANDS), desc="Checking dependencies")
    missing_commands = []

    for cmd in REQUIRED_COMMANDS:
        time.sleep(OPERATION_SLEEP)
        if shutil.which(cmd) is None:
            missing_commands.append(cmd)
        progress.update(1)

    progress.finish()

    if missing_commands:
        print_warning("The following required commands are missing:")
        for cmd in missing_commands:
            print_error(f"  ✗ {cmd}")

        print_info("Attempting to install missing dependencies...")
        if shutil.which(APT_CMD):
            install_packages(missing_commands, verbose)
            still_missing = [cmd for cmd in missing_commands if not shutil.which(cmd)]
            if still_missing:
                print_error("Could not install all required commands:")
                for cmd in still_missing:
                    print_error(f"  ✗ {cmd}")
                return False
            else:
                print_success("All dependencies are now installed.")
                return True
        else:
            print_error("Cannot automatically install missing dependencies.")
            print_info(f"Please install: {', '.join(missing_commands)}")
            return False

    print_success("All required commands are available.")
    return True


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

    progress = ProgressBar(total=len(packages), desc="Installing packages")
    for package in packages:
        success, _, _ = run_command(
            f"{APT_CMD} install -y {package}",
            error_message=f"Failed to install {package}",
            check=False,
            capture_output=True,
            verbose=verbose,
        )

        if success:
            logging.info(f"Installed package: {package}")
        else:
            logging.error(f"Failed to install package: {package}")

        progress.update(1)

    progress.finish()

    # Verify installations
    failed_packages = []
    for package in packages:
        success, _, _ = run_command(
            f"dpkg -s {package}", check=False, capture_output=True, verbose=verbose
        )
        if not success:
            failed_packages.append(package)

    if failed_packages:
        print_warning(f"Failed to install: {', '.join(failed_packages)}")
        return False

    print_success("All packages installed successfully.")
    return True


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


# ------------------------------
# ZFS Setup Functions
# ------------------------------
def install_zfs_packages(verbose: bool = False) -> bool:
    """Install ZFS packages."""
    print_section("Installing ZFS Packages")
    return install_packages(ZFS_PACKAGES, verbose)


def enable_zfs_services(verbose: bool = False) -> bool:
    """Enable required ZFS services."""
    print_section("Enabling ZFS Services")
    progress = ProgressBar(total=len(ZFS_SERVICES), desc="Enabling services")
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
            logging.info(f"Enabled service: {service}")
        else:
            failed_services.append(service)
            logging.warning(f"Failed to enable service: {service}")

        progress.update(1)

    progress.finish()

    if failed_services:
        print_warning(f"Failed to enable services: {', '.join(failed_services)}")
        return len(failed_services) < len(ZFS_SERVICES)

    print_success(f"Enabled services: {', '.join(enabled_services)}")
    return True


def create_mount_point(mount_point: str, verbose: bool = False) -> bool:
    """Create the ZFS pool mount point."""
    print_section("Creating Mount Point")
    print_step(f"Creating directory: {mount_point}")

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
    output = run_command_simple("zpool import", verbose)
    if not output:
        return []

    pools = []
    for line in output.split("\n"):
        if line.startswith("   pool: "):
            pools.append(line.split("pool: ")[1].strip())

    return pools


def is_pool_imported(pool_name: str, verbose: bool = False) -> bool:
    """Check if a ZFS pool is already imported."""
    success, _, _ = run_command(
        f"zpool list {pool_name}",
        error_message=f"Pool {pool_name} is not imported",
        check=False,
        spinner_text=f"Checking if pool '{pool_name}' is imported",
        verbose=verbose,
    )
    return success


def import_zfs_pool(pool_name: str, force: bool = False, verbose: bool = False) -> bool:
    """Import a ZFS pool."""
    print_section(f"Importing ZFS Pool '{pool_name}'")

    if is_pool_imported(pool_name, verbose):
        print_info(f"ZFS pool '{pool_name}' is already imported.")
        return True

    force_flag = "-f" if force else ""
    success, _, stderr = run_command(
        f"zpool import {force_flag} {pool_name}",
        error_message=f"Failed to import ZFS pool '{pool_name}'",
        check=False,
        spinner_text=f"Importing ZFS pool '{pool_name}'",
        verbose=verbose,
    )

    if success:
        print_success(f"Successfully imported ZFS pool '{pool_name}'.")
        return True
    else:
        print_error(f"Failed to import ZFS pool '{pool_name}'.")
        if stderr:
            print_error(f"Error details: {stderr}")

        print_info("Checking for available pools...")
        available_pools = list_available_pools(verbose)

        if available_pools:
            print_info(f"Available pools: {', '.join(available_pools)}")
            print_info(
                "You can specify one of these pools with the --pool-name option."
            )
        else:
            print_info("No available pools found for import.")

        return False


def configure_zfs_pool(
    pool_name: str, mount_point: str, cache_file: str, verbose: bool = False
) -> bool:
    """Configure a ZFS pool with mountpoint and cache settings."""
    print_section(f"Configuring ZFS Pool '{pool_name}'")

    # Set mountpoint
    success, _, stderr = run_command(
        f"zfs set mountpoint={mount_point} {pool_name}",
        error_message=f"Failed to set mountpoint for '{pool_name}'",
        check=False,
        spinner_text=f"Setting mountpoint to '{mount_point}'",
        verbose=verbose,
    )

    if not success:
        print_error(f"Failed to set mountpoint for '{pool_name}'.")
        if stderr:
            print_error(f"Error details: {stderr}")
        return False

    print_success(f"Set mountpoint for '{pool_name}' to '{mount_point}'.")

    # Set cachefile
    success, _, stderr = run_command(
        f"zpool set cachefile={cache_file} {pool_name}",
        error_message=f"Failed to set cachefile for '{pool_name}'",
        check=False,
        spinner_text=f"Setting cachefile to '{cache_file}'",
        verbose=verbose,
    )

    if not success:
        print_error(f"Failed to set cachefile for '{pool_name}'.")
        if stderr:
            print_error(f"Error details: {stderr}")
        print_warning("Pool was imported but cachefile was not set.")
        print_info("Automatic mounting on boot may not work.")
        return False

    print_success(f"Set cachefile for '{pool_name}' to '{cache_file}'.")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    return True


def mount_zfs_datasets(verbose: bool = False) -> bool:
    """Mount all ZFS datasets."""
    print_section("Mounting ZFS Datasets")

    success, _, stderr = run_command(
        "zfs mount -a",
        error_message="Failed to mount ZFS datasets",
        check=False,
        spinner_text="Mounting all ZFS datasets",
        verbose=verbose,
    )

    if success:
        print_success("All ZFS datasets mounted successfully.")
        return True
    else:
        print_warning("Some ZFS datasets may not have mounted.")
        if stderr:
            print_warning(f"Error details: {stderr}")
        return False


def verify_mount(pool_name: str, mount_point: str, verbose: bool = False) -> bool:
    """Verify that a ZFS pool is mounted at the expected location."""
    print_section("Verifying ZFS Mount")

    success, stdout, _ = run_command(
        "zfs list -o name,mountpoint -H",
        error_message="Failed to list ZFS filesystems",
        check=False,
        spinner_text="Verifying mount status",
        verbose=verbose,
    )

    if not success:
        print_error("Failed to verify mount status.")
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
        print_success(f"ZFS pool '{pool_name}' is mounted at '{mount_point}'.")
        return True
    elif pool_found:
        print_warning(
            f"ZFS pool '{pool_name}' is mounted at '{actual_mount}' (expected: '{mount_point}')."
        )
        return False
    else:
        print_error(f"ZFS pool '{pool_name}' is not mounted.")
        print_info("Current ZFS mounts:")
        for line in stdout.splitlines():
            print(f"  {line}")
        return False


def show_zfs_status(pool_name: str, verbose: bool = False) -> None:
    """Show the status and properties of a ZFS pool."""
    print_section(f"ZFS Pool Status for '{pool_name}'")

    success, stdout, _ = run_command(
        f"zpool status {pool_name}",
        error_message=f"Failed to get status for pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )

    if success and stdout:
        console.print(f"[#81A1C1]{stdout}[/#81A1C1]")
    else:
        print_warning(f"Could not get pool status for '{pool_name}'")

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
        ]
        filtered_output = []

        for line in stdout.splitlines():
            for prop in important_props:
                if f"{pool_name}\t{prop}\t" in line:
                    filtered_output.append(line)

        if filtered_output:
            print_step("Important pool properties:")
            for line in filtered_output:
                console.print(f"  [#D8DEE9]{line}[/#D8DEE9]")
    else:
        print_warning(f"Could not get pool properties for '{pool_name}'")


def interactive_setup() -> Tuple[str, str, str, bool]:
    """Run interactive setup to gather ZFS configuration."""
    print_section("Interactive ZFS Setup")

    available_pools = list_available_pools()
    if available_pools:
        print_info(f"Available ZFS pools: {', '.join(available_pools)}")
        pool_name = (
            console.input(
                f"[bold #88C0D0]Enter pool name [{DEFAULT_POOL_NAME}]: [/bold #88C0D0]"
            ).strip()
            or DEFAULT_POOL_NAME
        )
    else:
        print_info("No available pools detected. You'll need to specify the pool name.")
        pool_name = (
            console.input(
                f"[bold #88C0D0]Enter pool name [{DEFAULT_POOL_NAME}]: [/bold #88C0D0]"
            ).strip()
            or DEFAULT_POOL_NAME
        )

    default_mount = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    mount_point = (
        console.input(
            f"[bold #88C0D0]Enter mount point [{default_mount}]: [/bold #88C0D0]"
        ).strip()
        or default_mount
    )

    cache_file = (
        console.input(
            f"[bold #88C0D0]Enter cache file path [{DEFAULT_CACHE_FILE}]: [/bold #88C0D0]"
        ).strip()
        or DEFAULT_CACHE_FILE
    )

    force_input = console.input(
        f"[bold #88C0D0]Force import if needed? (y/N): [/bold #88C0D0]"
    )
    force = force_input.lower() in ("y", "yes")

    print_info("Selected configuration:")
    console.print(f"  Pool name:    [bold #88C0D0]{pool_name}[/bold #88C0D0]")
    console.print(f"  Mount point:  [bold #88C0D0]{mount_point}[/bold #88C0D0]")
    console.print(f"  Cache file:   [bold #88C0D0]{cache_file}[/bold #88C0D0]")
    console.print(
        f"  Force import: [bold #88C0D0]{'Yes' if force else 'No'}[/bold #88C0D0]"
    )

    confirm = console.input(
        f"[bold #88C0D0]Proceed with this configuration? (Y/n): [/bold #88C0D0]"
    )
    if confirm.lower() in ("n", "no"):
        print_info("Setup cancelled by user.")
        sys.exit(0)

    return pool_name, mount_point, cache_file, force


# ------------------------------
# ZFS Pool Expansion Functions
# ------------------------------
def get_zpool_status(
    verbose: bool = False,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Get detailed status information about ZFS pools."""
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
                        {
                            "type": "disk",
                            "path": parts[0],
                            "state": parts[1],
                        }
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


def get_block_device_size(device_path: str, verbose: bool = False) -> Optional[int]:
    """Get the size of a block device in bytes."""
    base_device = re.sub(r"p?\d+$", "", device_path)
    output = run_command_simple(f"lsblk -b -n -o SIZE {base_device}", verbose)

    if output:
        try:
            return int(output)
        except ValueError:
            print_warning(f"Could not parse device size from output: '{output}'")

    return None


def set_autoexpand_property(pool_name: str, verbose: bool = False) -> bool:
    """Enable the autoexpand property on a ZFS pool."""
    current_output = run_command_simple(f"zpool get autoexpand {pool_name}", verbose)
    if not current_output:
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
        if (
            run_command_simple(f"zpool set autoexpand=on {pool_name}", verbose)
            is not None
        ):
            print_success("autoexpand property enabled.")
            return True
        else:
            print_error("Failed to enable autoexpand property.")
            return False
    else:
        print_success("autoexpand is already enabled.")
        return True


def verify_pool_resize(pool_name: str, verbose: bool = False) -> bool:
    """Verify that a pool has been resized successfully."""
    print_step("Retrieving initial pool status...")
    initial_status = get_zpool_status(verbose)

    if not initial_status:
        print_error("Failed to retrieve initial zpool status.")
        return False

    initial_pool = next(
        (p for p in initial_status["pools"] if p["name"] == pool_name), None
    )

    if not initial_pool:
        print_error(f"Pool '{pool_name}' not found in initial status.")
        return False

    initial_size = initial_pool.get("allocatable")
    print_info(
        f"Initial allocatable pool size: {bytes_to_human_readable(initial_size)}"
    )

    print_step(f"Waiting {WAIT_TIME_SECONDS} seconds for background resizing...")
    time.sleep(WAIT_TIME_SECONDS)

    print_step("Retrieving final pool status...")
    final_status = get_zpool_status(verbose)

    if not final_status:
        print_error("Failed to retrieve final zpool status.")
        return False

    final_pool = next(
        (p for p in final_status["pools"] if p["name"] == pool_name), None
    )

    if not final_pool:
        print_error(f"Pool '{pool_name}' not found in final status.")
        return False

    final_size = final_pool.get("allocatable")
    print_info(f"Final allocatable pool size: {bytes_to_human_readable(final_size)}")

    if final_size is None or initial_size is None:
        print_error("Could not compare pool sizes due to parsing issues.")
        return False

    if final_size >= initial_size:
        print_success(
            f"Pool '{pool_name}' successfully resized (or already fully expanded)."
        )
        return True
    else:
        print_warning(
            f"Pool size appears to have decreased from {bytes_to_human_readable(initial_size)} to {bytes_to_human_readable(final_size)}."
        )
        return False


def expand_zpool(pool_name: str, device_path: str, verbose: bool = False) -> bool:
    """Expand a ZFS pool to use the full size of its underlying device."""
    print_header(f"Expanding ZFS Pool: {pool_name}")

    print_step("Step 1: Enabling autoexpand property...")
    if not set_autoexpand_property(pool_name, verbose):
        print_warning("Could not set autoexpand property. Continuing anyway...")

    print_step("Step 2: Initiating online expansion...")
    if (
        run_command_simple(f"zpool online -e {pool_name} {device_path}", verbose)
        is None
    ):
        print_error(
            f"Failed to initiate online expansion for '{device_path}' in pool '{pool_name}'."
        )
        return False

    print_success(
        f"Online expansion initiated for '{device_path}' in pool '{pool_name}'."
    )

    print_step("Step 3: Verifying pool resize...")
    return verify_pool_resize(pool_name, verbose)


def validate_expansion(verbose: bool = False) -> bool:
    """Validate the results of a ZFS pool expansion."""
    print_section("Validating ZFS Expansion")

    zpool_info = get_zpool_status(verbose)
    zfs_datasets = get_zfs_list(verbose)

    if not zpool_info or not zfs_datasets:
        print_error("Failed to retrieve pool or dataset information for validation.")
        return False

    total_pool_size = None
    if zpool_info["pools"]:
        pool_to_check = next(
            (p for p in zpool_info["pools"] if p["name"] == "rpool"),
            zpool_info["pools"][0],
        )
        total_pool_size = pool_to_check.get("allocatable")

    print_info(f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size)}")

    total_used = 0
    total_available = 0

    print_section("ZFS Datasets Summary:")
    for dataset in zfs_datasets:
        console.print(f"  Dataset: [bold]{dataset['name']}[/bold]")
        console.print(f"    Used: {dataset['used']}")
        console.print(f"    Available: {dataset['available']}")
        console.print(f"    Mountpoint: {dataset['mountpoint']}")

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

    print_section("Summary:")
    console.print(f"Total Used Space (datasets): {bytes_to_human_readable(total_used)}")
    console.print(
        f"Total Available Space (datasets): {bytes_to_human_readable(total_available)}"
    )

    expected_lower = EXPECTED_SIZE_TIB_LOWER * (1024**4)
    if total_pool_size is not None and total_pool_size > expected_lower:
        print_success(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is within expected range for a 2TB drive."
        )
        return True
    else:
        print_warning(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is smaller than expected for a 2TB drive."
        )
        return False


# ------------------------------
# Main ZFS Setup Function
# ------------------------------
def execute_zfs_setup(args) -> bool:
    """Execute the ZFS setup process."""
    pool_name = args.pool_name
    mount_point = args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    cache_file = args.cache_file
    force = args.force
    verbose = args.verbose

    steps_total = 6
    current_step = 0

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(args.log_file, log_level)

    start_time = datetime.datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        current_step += 1
        print_step("Checking system dependencies", current_step, steps_total)
        if not check_dependencies(verbose):
            return False

        current_step += 1
        if not args.skip_install:
            print_step("Installing ZFS packages", current_step, steps_total)
            if not install_zfs_packages(verbose):
                print_warning("ZFS package installation had issues, but continuing...")
        else:
            print_step(
                "Skipping ZFS package installation (--skip-install)",
                current_step,
                steps_total,
            )

        current_step += 1
        print_step("Enabling ZFS services", current_step, steps_total)
        enable_zfs_services(verbose)

        current_step += 1
        print_step(f"Creating mount point: {mount_point}", current_step, steps_total)
        if not create_mount_point(mount_point, verbose):
            return False

        current_step += 1
        print_step(f"Importing ZFS pool: {pool_name}", current_step, steps_total)
        if not import_zfs_pool(pool_name, force, verbose):
            return False

        current_step += 1
        print_step(f"Configuring ZFS pool: {pool_name}", current_step, steps_total)
        if not configure_zfs_pool(pool_name, mount_point, cache_file, verbose):
            print_warning("Pool configuration had issues, but continuing...")

        mount_zfs_datasets(verbose)

        if not verify_mount(pool_name, mount_point, verbose):
            print_warning("ZFS mount verification failed. Check mount status manually.")

        show_zfs_status(pool_name, verbose)
        return True

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        print_error(f"Setup failed: {e}")
        return False


# ------------------------------
# Command Line Parsing
# ------------------------------
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

    # Version information
    parser.add_argument(
        "--version",
        action="version",
        version=f"Unified ZFS Management Script v{VERSION}",
    )

    return parser.parse_args()


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        args = parse_arguments()

        if not args.command:
            print_header("Unified ZFS Management")
            print_error("No command specified.")
            print_info(
                "Use 'setup' or 'expand' command. See --help for more information."
            )
            sys.exit(1)

        # Clear screen
        os.system("clear" if os.name == "posix" else "cls")

        if args.command == "setup":
            print_header("Enhanced ZFS Setup")
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

            start_time = time.time()
            success = execute_zfs_setup(args)
            end_time = time.time()
            elapsed = end_time - start_time

            print_header("ZFS Setup Summary")
            if success:
                print_success("ZFS setup completed successfully!")
            else:
                print_error("ZFS setup encountered errors.")

            print_info(f"Pool name: {args.pool_name}")
            print_info(
                f"Mount point: {args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=args.pool_name)}"
            )
            print_info(f"Elapsed time: {format_time(elapsed)}")
            print_info(f"Log file: {args.log_file}")

            if success:
                print_section("Next Steps")
                print_info("Your ZFS pool is now configured and imported.")
                print_info(
                    f"Access your data at: {args.mount_point or DEFAULT_MOUNT_POINT.format(pool_name=args.pool_name)}"
                )
                print_info("Helpful ZFS commands:")
                console.print(
                    f"  [bold #88C0D0]zfs list[/bold #88C0D0]              - List ZFS filesystems"
                )
                console.print(
                    f"  [bold #88C0D0]zpool status {args.pool_name}[/bold #88C0D0]  - Show pool status"
                )
                console.print(
                    f"  [bold #88C0D0]zfs get all {args.pool_name}[/bold #88C0D0]   - Show all properties"
                )

            sys.exit(0 if success else 1)

        elif args.command == "expand":
            print_header("ZFS Pool Expansion")
            print_info(
                f"Started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if not check_root_privileges():
                sys.exit(1)

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

            print_section("Detected ZFS Pools and Devices")
            for name, dev in pool_device_paths.items():
                console.print(
                    f"  Pool: [bold]{name}[/bold], Device: [italic]{dev}[/italic]"
                )

            if not pool_device_paths:
                print_error("No valid pool-device pairs found. Aborting expansion.")
                sys.exit(1)

            print_section("Starting ZFS Pool Expansion Process")
            expansion_results = {}

            for pool_name, device_path in pool_device_paths.items():
                result = expand_zpool(pool_name, device_path, args.verbose)
                expansion_results[pool_name] = result

            print_section("Expansion Process Completed")
            validation = validate_expansion(args.verbose)

            print_section("Expansion Results Summary")
            for pool_name, success in expansion_results.items():
                status_text = (
                    "[bold #A3BE8C]Successful[/bold #A3BE8C]"
                    if success
                    else "[bold #BF616A]Failed[/bold #BF616A]"
                )
                console.print(f"  Pool [bold]{pool_name}[/bold]: {status_text}")

            overall = (
                "Successful"
                if all(expansion_results.values()) and validation
                else "Failed"
            )
            console.print(
                f"Overall validation: [bold]{'[#A3BE8C]' if overall == 'Successful' else '[#BF616A]'}{overall}[/bold]"
            )
            print_info(
                f"Completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            sys.exit(0 if all(expansion_results.values()) and validation else 1)

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
