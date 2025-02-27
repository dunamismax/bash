#!/usr/bin/env python3
"""
Enhanced ZFS Setup Script

A comprehensive utility for installing, configuring, and managing ZFS storage pools on Linux.
This script handles the complete ZFS setup workflow:
  • Installing ZFS packages and prerequisites
  • Enabling and configuring system services
  • Creating and importing ZFS pools
  • Configuring pool properties and mount points
  • Setting up automatic mounting
  • Verifying the configuration

The script features interactive prompts, detailed progress feedback, and thorough error handling
to ensure reliable ZFS deployment.

Note: This script must be run with root privileges.
"""

import argparse
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable, TextIO

#####################################
# Configuration
#####################################

# Default settings (can be overridden via command-line arguments)
DEFAULT_POOL_NAME = "tank"
DEFAULT_MOUNT_POINT = "/media/{pool_name}"
DEFAULT_CACHE_FILE = "/etc/zfs/zpool.cache"
DEFAULT_LOG_FILE = "/var/log/zfs_setup.log"

# System commands
APT_CMD = "apt"
if shutil.which("nala"):
    APT_CMD = "nala"  # Use nala if available (faster apt alternative)

# ZFS services to enable
ZFS_SERVICES = [
    "zfs-import-cache.service",
    "zfs-mount.service",
    "zfs-import.target",
    "zfs.target",
]

# Required packages
ZFS_PACKAGES = [
    "dpkg-dev",
    "linux-headers-generic",
    "linux-image-generic",
    "zfs-dkms",
    "zfsutils-linux",
]

# Required commands to check
REQUIRED_COMMANDS = [APT_CMD, "systemctl", "zpool", "zfs"]

# Progress tracking settings
PROGRESS_WIDTH = 50
OPERATION_SLEEP = 0.05  # Sleep time between operations for smoother progress display

#####################################
# Nord Theme ANSI Color Codes
#####################################


class NordColors:
    """Nord-themed ANSI color codes for terminal output"""

    # Polar Night (dark blues/blacks)
    POLAR_NIGHT_1 = "\033[38;2;46;52;64m"  # #2E3440
    POLAR_NIGHT_2 = "\033[38;2;59;66;82m"  # #3B4252

    # Snow Storm (whites/light grays)
    SNOW_STORM_1 = "\033[38;2;216;222;233m"  # #D8DEE9
    SNOW_STORM_2 = "\033[38;2;229;233;240m"  # #E5E9F0

    # Frost (blues)
    FROST_1 = "\033[38;2;143;188;187m"  # #8FBCBB
    FROST_2 = "\033[38;2;136;192;208m"  # #88C0D0
    FROST_3 = "\033[38;2;129;161;193m"  # #81A1C1
    FROST_4 = "\033[38;2;94;129;172m"  # #5E81AC

    # Aurora (accent colors)
    RED = "\033[38;2;191;97;106m"  # #BF616A
    ORANGE = "\033[38;2;208;135;112m"  # #D08770
    YELLOW = "\033[38;2;235;203;139m"  # #EBCB8B
    GREEN = "\033[38;2;163;190;140m"  # #A3BE8C
    PURPLE = "\033[38;2;180;142;173m"  # #B48EAD

    # Backgrounds
    BG_DARK = "\033[48;2;46;52;64m"  # #2E3440
    BG_LIGHT = "\033[48;2;76;86;106m"  # #4C566A

    # Formatting
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"

    # Common combinations
    HEADER = f"{BOLD}{FROST_2}"
    SUCCESS = f"{GREEN}"
    WARNING = f"{YELLOW}"
    ERROR = f"{RED}"
    INFO = f"{FROST_3}"
    SECTION = f"{BOLD}{FROST_4}"
    EMPHASIS = f"{BOLD}{FROST_1}"
    SUBTLE = f"{SNOW_STORM_1}"


#####################################
# Progress Tracking Classes
#####################################


class ProgressBar:
    """Thread-safe progress bar for tracking operations"""

    def __init__(self, total: int = 100, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.completed = False

    def update(self, amount: int = 1) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def set_progress(self, value: int) -> None:
        """Set progress to a specific value"""
        with self._lock:
            self.current = min(max(0, value), self.total)
            self._display()

    def finish(self) -> None:
        """Mark progress as complete"""
        with self._lock:
            self.current = self.total
            self.completed = True
            self._display()
            print()  # Add a newline after the progress bar

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time

        if elapsed > 0 and self.current > 0:
            eta = (self.total - self.current) * elapsed / self.current
            eta_str = format_time(eta)
        else:
            eta_str = "N/A"

        sys.stdout.write(
            f"\r{NordColors.SUBTLE}{self.desc}: {NordColors.RESET}"
            f"{NordColors.BG_DARK}{NordColors.FROST_2} {bar} {NordColors.RESET} "
            f"{NordColors.FROST_3}{percent:>5.1f}%{NordColors.RESET} "
            f"[ETA: {NordColors.FROST_1}{eta_str}{NordColors.RESET}]"
        )
        sys.stdout.flush()

        if self.completed:
            elapsed_str = format_time(elapsed)
            print(
                f"\r{NordColors.SUBTLE}{self.desc}: {NordColors.RESET}"
                f"{NordColors.BG_DARK}{NordColors.FROST_2} {bar} {NordColors.RESET} "
                f"{NordColors.SUCCESS}100.0%{NordColors.RESET} "
                f"[Completed in: {NordColors.FROST_1}{elapsed_str}{NordColors.RESET}]"
            )


class Spinner:
    """Thread-safe spinner for long-running operations"""

    def __init__(self, desc: str = "", delay: float = 0.1, stdout: TextIO = sys.stdout):
        self.desc = desc
        self.delay = delay
        self.spinner_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        self.index = 0
        self.running = False
        self.thread = None
        self.stdout = stdout
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Display the spinner animation"""
        while self.running:
            with self._lock:
                self.stdout.write(
                    f"\r{NordColors.SUBTLE}{self.desc} {NordColors.FROST_2}"
                    f"{self.spinner_chars[self.index]}{NordColors.RESET}"
                )
                self.stdout.flush()
            self.index = (self.index + 1) % len(self.spinner_chars)
            time.sleep(self.delay)

    def start(self) -> None:
        """Start the spinner in a separate thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._spin)
            self.thread.daemon = True
            self.thread.start()

    def stop(self, success: bool = True, message: str = None) -> None:
        """Stop the spinner and show a completion message"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()

            status_symbol = (
                f"{NordColors.SUCCESS}✓" if success else f"{NordColors.ERROR}✗"
            )
            completion_message = (
                message if message else ("Completed" if success else "Failed")
            )

            self.stdout.write(
                f"\r{NordColors.SUBTLE}{self.desc} {status_symbol}{NordColors.RESET} "
                f"{NordColors.FROST_3}{completion_message}{NordColors.RESET}\n"
            )
            self.stdout.flush()


#####################################
# Helper Functions
#####################################


def format_time(seconds: float) -> str:
    """Format seconds into human-readable time string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"


def print_header(message: str) -> None:
    """Print formatted header"""
    term_width = shutil.get_terminal_size().columns

    # Adjust for ANSI color escape codes
    effective_length = len(message)

    # Use Nord theme colors for the header
    print(
        f"\n{NordColors.BG_DARK}{NordColors.FROST_2}{' ' * term_width}{NordColors.RESET}"
    )
    print(
        f"{NordColors.BG_DARK}{NordColors.BOLD}{message.center(term_width)}{NordColors.RESET}"
    )
    print(
        f"{NordColors.BG_DARK}{NordColors.FROST_2}{' ' * term_width}{NordColors.RESET}\n"
    )


def print_section(message: str) -> None:
    """Print formatted section header"""
    print(f"\n{NordColors.SECTION}▶ {message}{NordColors.RESET}")


def print_step(message: str, step_num: int = None, total_steps: int = None) -> None:
    """Print a step in the process"""
    step_info = ""
    if step_num is not None and total_steps is not None:
        step_info = f"[{step_num}/{total_steps}] "

    print(f"{NordColors.FROST_1}→ {step_info}{message}{NordColors.RESET}")


def print_info(message: str) -> None:
    """Print info message"""
    print(f"{NordColors.INFO}ℹ {message}{NordColors.RESET}")


def print_success(message: str) -> None:
    """Print success message"""
    print(f"{NordColors.SUCCESS}✓ {message}{NordColors.RESET}")


def print_warning(message: str) -> None:
    """Print warning message"""
    print(f"{NordColors.WARNING}⚠ {message}{NordColors.RESET}")


def print_error(message: str) -> None:
    """Print error message"""
    print(f"{NordColors.ERROR}✗ {message}{NordColors.RESET}")


def setup_logging(log_file: str, log_level: int = logging.INFO) -> None:
    """Configure logging to console and file."""
    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
            # No stream handler - we'll use our custom print functions instead
        ],
    )

    # Secure log file permissions
    try:
        os.chmod(log_file, 0o600)
        logging.info(f"Set log file permissions to 0600")
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


def run_command(
    command: Union[str, List[str]],
    error_message: str = None,
    check: bool = True,
    spinner_text: str = None,
    capture_output: bool = True,
    env: Dict[str, str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Run a system command with error handling and optional spinner.

    Args:
        command: Command to execute (string or list)
        error_message: Custom error message if command fails
        check: Whether to raise an exception on failure
        spinner_text: Text for spinner display (if None, no spinner is shown)
        capture_output: Whether to capture and return command output
        env: Environment variables for the command

    Returns:
        Tuple[bool, str, str]: (success, stdout, stderr)
    """
    spinner = None
    if spinner_text:
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
        else:
            cmd_str = command if isinstance(command, str) else " ".join(command)
            logging.error(f"Command failed: {cmd_str}")
            logging.error(f"Error output: {error_output}")

        if check:
            raise

        return False, None, error_output

    except Exception as e:
        if spinner:
            spinner.stop(success=False)

        logging.error(f"Exception running command: {e}")

        if check:
            raise

        return False, None, str(e)


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
    missing_commands = []

    print_step("Checking for required commands")
    progress = ProgressBar(total=len(REQUIRED_COMMANDS), desc="Checking dependencies")

    for i, cmd in enumerate(REQUIRED_COMMANDS):
        time.sleep(OPERATION_SLEEP)  # For smoother progress display
        has_command = shutil.which(cmd) is not None
        progress.update(1)

        if not has_command:
            missing_commands.append(cmd)

    progress.finish()

    if missing_commands:
        print_warning(f"The following required commands are missing:")
        for cmd in missing_commands:
            print(f"  {NordColors.RED}✗ {cmd}{NordColors.RESET}")

        print_info("Installing missing dependencies...")

        # Try to install missing commands (if apt/nala is available)
        if shutil.which(APT_CMD):
            install_packages(missing_commands)

            # Verify installation
            still_missing = [cmd for cmd in missing_commands if not shutil.which(cmd)]

            if still_missing:
                print_error(f"Could not install all required commands.")
                for cmd in still_missing:
                    print(f"  {NordColors.RED}✗ {cmd}{NordColors.RESET}")
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


def check_zfs_support() -> bool:
    """
    Check if ZFS is supported on this system.

    Returns:
        bool: True if ZFS is supported
    """
    # Check kernel module
    success, stdout, _ = run_command(
        "modprobe zfs",
        error_message="Failed to load ZFS kernel module",
        check=False,
        spinner_text="Checking ZFS kernel module",
    )

    if not success:
        print_warning("ZFS kernel module could not be loaded.")

        # Check if we can see the module in the list
        success, stdout, _ = run_command(
            "find /lib/modules/$(uname -r) -name 'zfs.ko*'",
            check=False,
            spinner_text="Looking for ZFS kernel module",
        )

        if not success or not stdout:
            print_error("ZFS kernel module not found.")
            print_info("You may need to install ZFS packages first.")
            return False

    # Check if ZFS commands are available
    if not shutil.which("zfs") or not shutil.which("zpool"):
        print_error("ZFS commands not found.")
        print_info("Please ensure ZFS packages are installed.")
        return False

    print_success("ZFS is supported on this system.")
    return True


#####################################
# Installation Functions
#####################################


def install_packages(packages: List[str]) -> bool:
    """
    Install required packages.

    Args:
        packages: List of packages to install

    Returns:
        bool: True if installation succeeded
    """
    if not packages:
        return True

    package_str = " ".join(packages)
    print_step(f"Installing packages: {package_str}")

    # Update package lists
    success, _, _ = run_command(
        f"{APT_CMD} update",
        error_message="Failed to update package lists",
        check=False,
        spinner_text="Updating package lists",
    )

    if not success:
        print_warning("Failed to update package lists. Continuing anyway...")

    # Install packages with progress tracking
    total_packages = len(packages)
    progress = ProgressBar(total=total_packages, desc="Installing packages")

    for i, package in enumerate(packages):
        success, _, _ = run_command(
            f"{APT_CMD} install -y {package}",
            error_message=f"Failed to install {package}",
            check=False,
            capture_output=True,
        )

        if success:
            logging.info(f"Installed package: {package}")
        else:
            logging.error(f"Failed to install package: {package}")

        progress.update(1)

    progress.finish()

    # Verify installation
    failed_packages = []
    for package in packages:
        # Simple check if package is installed
        success, _, _ = run_command(
            f"dpkg -s {package}",
            check=False,
            capture_output=True,
        )

        if not success:
            failed_packages.append(package)

    if failed_packages:
        print_warning(f"Failed to install: {', '.join(failed_packages)}")
        return False

    print_success(f"All packages installed successfully.")
    return True


def install_zfs_packages() -> bool:
    """
    Install ZFS packages and dependencies.

    Returns:
        bool: True if installation succeeded
    """
    print_section("Installing ZFS Packages")

    return install_packages(ZFS_PACKAGES)


def enable_zfs_services() -> bool:
    """
    Enable ZFS-related system services.

    Returns:
        bool: True if enabling services succeeded
    """
    print_section("Enabling ZFS Services")

    progress = ProgressBar(total=len(ZFS_SERVICES), desc="Enabling services")
    enabled_services = []
    failed_services = []

    for service in ZFS_SERVICES:
        success, _, _ = run_command(
            f"systemctl enable {service}",
            error_message=f"Failed to enable {service}",
            check=False,
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


#####################################
# ZFS Setup Functions
#####################################


def create_mount_point(mount_point: str) -> bool:
    """
    Create the ZFS mount point directory.

    Args:
        mount_point: Directory to create

    Returns:
        bool: True if directory was created or already exists
    """
    print_section("Creating Mount Point")
    print_step(f"Creating directory: {mount_point}")

    spinner = Spinner("Creating mount point")
    spinner.start()

    try:
        os.makedirs(mount_point, exist_ok=True)
        spinner.stop(success=True, message=f"Created: {mount_point}")
        logging.info(f"Created mount point: {mount_point}")
        return True
    except Exception as e:
        spinner.stop(success=False, message=f"Failed: {str(e)}")
        logging.error(f"Failed to create mount point {mount_point}: {e}")
        return False


def list_available_pools() -> List[str]:
    """
    List all available ZFS pools that can be imported.

    Returns:
        List[str]: Names of available pools
    """
    success, stdout, _ = run_command(
        "zpool import",
        error_message="Failed to list available pools",
        check=False,
        spinner_text="Searching for available ZFS pools",
    )

    if not success or not stdout:
        return []

    # Parse the output to find pool names
    pools = []
    current_pool = None

    for line in stdout.split("\n"):
        if line.startswith("   pool: "):
            current_pool = line.split("pool: ")[1].strip()
            pools.append(current_pool)

    return pools


def is_pool_imported(pool_name: str) -> bool:
    """
    Check if a ZFS pool is already imported.

    Args:
        pool_name: Name of the pool to check

    Returns:
        bool: True if pool is imported
    """
    success, stdout, _ = run_command(
        f"zpool list {pool_name}",
        error_message=f"Pool {pool_name} is not imported",
        check=False,
        spinner_text=f"Checking if pool '{pool_name}' is imported",
    )

    return success


def import_zfs_pool(pool_name: str, force: bool = False) -> bool:
    """
    Import a ZFS pool.

    Args:
        pool_name: Name of the pool to import
        force: Whether to force import

    Returns:
        bool: True if pool was imported successfully
    """
    print_section(f"Importing ZFS Pool '{pool_name}'")

    # Check if pool is already imported
    if is_pool_imported(pool_name):
        print_info(f"ZFS pool '{pool_name}' is already imported.")
        return True

    # Try to import the pool
    force_flag = "-f" if force else ""

    success, stdout, stderr = run_command(
        f"zpool import {force_flag} {pool_name}",
        error_message=f"Failed to import ZFS pool '{pool_name}'",
        check=False,
        spinner_text=f"Importing ZFS pool '{pool_name}'",
    )

    if success:
        print_success(f"Successfully imported ZFS pool '{pool_name}'.")
        return True
    else:
        print_error(f"Failed to import ZFS pool '{pool_name}'.")
        if stderr:
            print(f"{NordColors.ERROR}Error details: {stderr}{NordColors.RESET}")

        # List available pools
        print_info("Checking for available pools...")
        available_pools = list_available_pools()

        if available_pools:
            print_info(f"Available pools: {', '.join(available_pools)}")
            print_info(
                "You can specify one of these pools with the --pool-name option."
            )
        else:
            print_info("No available pools found for import.")

        return False


def configure_zfs_pool(pool_name: str, mount_point: str, cache_file: str) -> bool:
    """
    Configure ZFS pool properties.

    Args:
        pool_name: Name of the pool to configure
        mount_point: Mount point to set
        cache_file: Cache file path

    Returns:
        bool: True if configuration succeeded
    """
    print_section(f"Configuring ZFS Pool '{pool_name}'")

    # Set mountpoint property
    success, _, stderr = run_command(
        f"zfs set mountpoint={mount_point} {pool_name}",
        error_message=f"Failed to set mountpoint for '{pool_name}'",
        check=False,
        spinner_text=f"Setting mountpoint to '{mount_point}'",
    )

    if not success:
        print_error(f"Failed to set mountpoint for '{pool_name}'.")
        if stderr:
            print(f"{NordColors.ERROR}Error details: {stderr}{NordColors.RESET}")
        return False

    print_success(f"Set mountpoint for '{pool_name}' to '{mount_point}'.")

    # Set cachefile property
    success, _, stderr = run_command(
        f"zpool set cachefile={cache_file} {pool_name}",
        error_message=f"Failed to set cachefile for '{pool_name}'",
        check=False,
        spinner_text=f"Setting cachefile to '{cache_file}'",
    )

    if not success:
        print_error(f"Failed to set cachefile for '{pool_name}'.")
        if stderr:
            print(f"{NordColors.ERROR}Error details: {stderr}{NordColors.RESET}")
        print_warning("Pool was imported but cachefile was not set.")
        print_info("Automatic mounting on boot may not work.")
        return False

    print_success(f"Set cachefile for '{pool_name}' to '{cache_file}'.")

    # Ensure cachefile directory exists
    cache_dir = os.path.dirname(cache_file)
    os.makedirs(cache_dir, exist_ok=True)

    return True


def mount_zfs_datasets() -> bool:
    """
    Mount all ZFS datasets.

    Returns:
        bool: True if mounting succeeded
    """
    print_section("Mounting ZFS Datasets")

    success, stdout, stderr = run_command(
        "zfs mount -a",
        error_message="Failed to mount ZFS datasets",
        check=False,
        spinner_text="Mounting all ZFS datasets",
    )

    if success:
        print_success("All ZFS datasets mounted successfully.")
        return True
    else:
        print_warning("Some ZFS datasets may not have mounted.")
        if stderr:
            print(f"{NordColors.WARNING}Error details: {stderr}{NordColors.RESET}")
        return False


def verify_mount(pool_name: str, mount_point: str) -> bool:
    """
    Verify that a ZFS pool is mounted correctly.

    Args:
        pool_name: Name of the pool to verify
        mount_point: Expected mount point

    Returns:
        bool: True if pool is mounted correctly
    """
    print_section("Verifying ZFS Mount")

    success, stdout, _ = run_command(
        "zfs list -o name,mountpoint -H",
        error_message="Failed to list ZFS filesystems",
        check=False,
        spinner_text="Verifying mount status",
    )

    if not success:
        print_error("Failed to verify mount status.")
        return False

    # Check if pool is in the list with correct mountpoint
    pool_found = False
    correct_mount = False

    for line in stdout.splitlines():
        try:
            fs_name, fs_mount = line.split("\t")
            if fs_name == pool_name:
                pool_found = True
                if fs_mount == mount_point:
                    correct_mount = True
                    break
        except ValueError:
            continue

    if pool_found and correct_mount:
        print_success(f"ZFS pool '{pool_name}' is mounted at '{mount_point}'.")
        return True
    elif pool_found:
        actual_mount = None
        for line in stdout.splitlines():
            try:
                fs_name, fs_mount = line.split("\t")
                if fs_name == pool_name:
                    actual_mount = fs_mount
                    break
            except ValueError:
                continue

        print_warning(
            f"ZFS pool '{pool_name}' is mounted at '{actual_mount}' (expected: '{mount_point}')."
        )
        return False
    else:
        print_error(f"ZFS pool '{pool_name}' is not mounted.")
        print_info("Current ZFS mounts:")
        for line in stdout.splitlines():
            print(f"  {NordColors.SUBTLE}{line}{NordColors.RESET}")
        return False


def show_zfs_status(pool_name: str) -> None:
    """Display detailed status of a ZFS pool"""
    print_section(f"ZFS Pool Status for '{pool_name}'")

    # Get pool status
    success, stdout, _ = run_command(
        f"zpool status {pool_name}",
        error_message=f"Failed to get status for pool '{pool_name}'",
        check=False,
    )

    if success and stdout:
        print(f"{NordColors.FROST_3}{stdout}{NordColors.RESET}")
    else:
        print_warning(f"Could not get pool status for '{pool_name}'")

    # Get pool properties
    success, stdout, _ = run_command(
        f"zpool get all {pool_name}",
        error_message=f"Failed to get properties for pool '{pool_name}'",
        check=False,
    )

    if success and stdout:
        # Just show some important properties
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
                print(f"  {NordColors.SUBTLE}{line}{NordColors.RESET}")
    else:
        print_warning(f"Could not get pool properties for '{pool_name}'")


#####################################
# Main Functions
#####################################


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Enhanced ZFS Setup Script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--pool-name", default=DEFAULT_POOL_NAME, help="Name of the ZFS pool to import"
    )

    parser.add_argument(
        "--mount-point",
        help="Mount point for the ZFS pool (default: /media/{pool_name})",
    )

    parser.add_argument(
        "--cache-file", default=DEFAULT_CACHE_FILE, help="Path to the ZFS cache file"
    )

    parser.add_argument(
        "--log-file", default=DEFAULT_LOG_FILE, help="Path to the log file"
    )

    parser.add_argument(
        "--force", action="store_true", help="Force import of the ZFS pool"
    )

    parser.add_argument(
        "--skip-install", action="store_true", help="Skip package installation"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    # Set default mount point if not specified
    if not args.mount_point:
        args.mount_point = DEFAULT_MOUNT_POINT.format(pool_name=args.pool_name)

    return args


def interactive_setup() -> Tuple[str, str, str, bool]:
    """
    Interactive setup to gather user preferences

    Returns:
        Tuple[str, str, str, bool]: (pool_name, mount_point, cache_file, force)
    """
    print_section("Interactive ZFS Setup")

    # List available pools
    available_pools = list_available_pools()
    if available_pools:
        print_info(f"Available ZFS pools: {', '.join(available_pools)}")
        pool_name = input(
            f"{NordColors.FROST_1}Enter pool name [{DEFAULT_POOL_NAME}]: {NordColors.RESET}"
        )
        pool_name = pool_name.strip() if pool_name.strip() else DEFAULT_POOL_NAME
    else:
        print_info("No available pools detected. You'll need to specify the pool name.")
        pool_name = input(
            f"{NordColors.FROST_1}Enter pool name [{DEFAULT_POOL_NAME}]: {NordColors.RESET}"
        )
        pool_name = pool_name.strip() if pool_name.strip() else DEFAULT_POOL_NAME

    default_mount = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    mount_point = input(
        f"{NordColors.FROST_1}Enter mount point [{default_mount}]: {NordColors.RESET}"
    )
    mount_point = mount_point.strip() if mount_point.strip() else default_mount

    cache_file = input(
        f"{NordColors.FROST_1}Enter cache file path [{DEFAULT_CACHE_FILE}]: {NordColors.RESET}"
    )
    cache_file = cache_file.strip() if cache_file.strip() else DEFAULT_CACHE_FILE

    force_input = input(
        f"{NordColors.FROST_1}Force import if needed? (y/N): {NordColors.RESET}"
    )
    force = force_input.lower() in ("y", "yes")

    print_info(f"Selected configuration:")
    print(f"  {NordColors.FROST_3}Pool name:    {NordColors.RESET}{pool_name}")
    print(f"  {NordColors.FROST_3}Mount point:  {NordColors.RESET}{mount_point}")
    print(f"  {NordColors.FROST_3}Cache file:   {NordColors.RESET}{cache_file}")
    print(
        f"  {NordColors.FROST_3}Force import: {NordColors.RESET}{'Yes' if force else 'No'}"
    )

    confirm = input(
        f"{NordColors.FROST_1}Proceed with this configuration? (Y/n): {NordColors.RESET}"
    )
    if confirm.lower() in ("n", "no"):
        print_info("Setup cancelled by user.")
        sys.exit(0)

    return pool_name, mount_point, cache_file, force


def execute_zfs_setup(args: argparse.Namespace) -> bool:
    """
    Execute the ZFS setup process

    Args:
        args: Command-line arguments

    Returns:
        bool: True if setup succeeded
    """
    pool_name = args.pool_name
    mount_point = args.mount_point
    cache_file = args.cache_file
    force = args.force

    # Steps counter for progress feedback
    steps_total = 6  # Total number of main steps
    current_step = 0

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(args.log_file, log_level)

    # Log start time
    start_time = datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        # Step 1: Check dependencies
        current_step += 1
        print_step("Checking system dependencies", current_step, steps_total)
        if not check_dependencies():
            return False

        # Step 2: Install ZFS packages (if not skipped)
        current_step += 1
        if not args.skip_install:
            print_step("Installing ZFS packages", current_step, steps_total)
            if not install_zfs_packages():
                print_warning("ZFS package installation had issues, but continuing...")
        else:
            print_step(
                "Skipping ZFS package installation (--skip-install)",
                current_step,
                steps_total,
            )

        # Step 3: Enable ZFS services
        current_step += 1
        print_step("Enabling ZFS services", current_step, steps_total)
        enable_zfs_services()  # Continue even if this fails

        # Step 4: Create mount point
        current_step += 1
        print_step(f"Creating mount point: {mount_point}", current_step, steps_total)
        if not create_mount_point(mount_point):
            return False

        # Step 5: Import ZFS pool
        current_step += 1
        print_step(f"Importing ZFS pool: {pool_name}", current_step, steps_total)
        if not import_zfs_pool(pool_name, force):
            return False

        # Step 6: Configure ZFS pool
        current_step += 1
        print_step(f"Configuring ZFS pool: {pool_name}", current_step, steps_total)
        if not configure_zfs_pool(pool_name, mount_point, cache_file):
            print_warning("Pool configuration had issues, but continuing...")

        # Mount ZFS datasets
        mount_zfs_datasets()  # Continue even if this fails

        # Verify mount
        if not verify_mount(pool_name, mount_point):
            print_warning("ZFS mount verification failed. Check mount status manually.")

        # Show final status
        show_zfs_status(pool_name)

        return True

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        print_error(f"Setup failed: {e}")
        return False


def main() -> None:
    """Main execution function"""
    # Clear screen for better presentation
    os.system("clear" if os.name == "posix" else "cls")

    # Setup signal handlers for graceful exit
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(143))

    # Print header
    print_header("Enhanced ZFS Setup Script")

    # Check root privileges
    if not check_root_privileges():
        sys.exit(1)

    # Check ZFS kernel module support
    if not check_zfs_support():
        print_warning("ZFS support check failed. Continuing anyway...")

    # Parse command-line arguments
    args = parse_arguments()

    # Choose setup mode: interactive or from arguments
    if len(sys.argv) == 1:  # No command-line arguments provided
        try:
            pool_name, mount_point, cache_file, force = interactive_setup()
            args.pool_name = pool_name
            args.mount_point = mount_point
            args.cache_file = cache_file
            args.force = force
        except KeyboardInterrupt:
            print("\n")
            print_warning("Setup cancelled by user.")
            sys.exit(130)

    # Start time
    start_time = time.time()

    # Run ZFS setup
    success = execute_zfs_setup(args)

    # End time
    end_time = time.time()
    elapsed = end_time - start_time

    # Print final summary
    print_header("ZFS Setup Summary")

    if success:
        print_success("ZFS setup completed successfully!")
    else:
        print_error("ZFS setup encountered errors.")

    print_info(f"Pool name: {args.pool_name}")
    print_info(f"Mount point: {args.mount_point}")
    print_info(f"Elapsed time: {format_time(elapsed)}")
    print_info(f"Log file: {args.log_file}")

    # Print next steps
    if success:
        print_section("Next Steps")
        print(
            f"{NordColors.FROST_3}Your ZFS pool is now configured and imported.{NordColors.RESET}"
        )
        print(
            f"{NordColors.FROST_3}You can access your data at: {NordColors.RESET}{args.mount_point}"
        )
        print(f"{NordColors.FROST_3}Some helpful ZFS commands:{NordColors.RESET}")
        print(
            f"  {NordColors.FROST_1}zfs list{NordColors.RESET}              - List ZFS filesystems"
        )
        print(
            f"  {NordColors.FROST_1}zpool status {args.pool_name}{NordColors.RESET}  - Show pool status"
        )
        print(
            f"  {NordColors.FROST_1}zfs get all {args.pool_name}{NordColors.RESET}   - Show all properties"
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
