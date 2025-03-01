#!/usr/bin/env python3
"""
Unified ZFS Management Script

This utility combines two core functions:
  • Enhanced ZFS Setup – installs required packages, enables services, creates mount points,
    imports and configures ZFS pools, mounts datasets, and verifies the setup.
  • ZFS Pool Expansion – enables autoexpand, performs online expansion of pools, and validates
    the expansion against expected sizes.

The script uses a Nord‑themed CLI interface with ANSI color codes, progress tracking (spinner
and progress bar), and interactive prompts. It is designed for Linux systems and must be run
with root privileges.
"""

import argparse
import csv
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
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TextIO

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

#####################################
# Global Configuration & Constants
#####################################

# Defaults for ZFS setup
DEFAULT_POOL_NAME = "tank"
DEFAULT_MOUNT_POINT = "/media/{pool_name}"
DEFAULT_CACHE_FILE = "/etc/zfs/zpool.cache"
DEFAULT_LOG_FILE = "/var/log/zfs_setup.log"

APT_CMD = "apt"
if shutil.which("nala"):
    APT_CMD = "nala"  # Prefer nala if available

ZFS_SERVICES = [
    "zfs-import-cache.service",
    "zfs-mount.service",
    "zfs-import.target",
    "zfs.target",
]

ZFS_PACKAGES = [
    "dpkg-dev",
    "linux-headers-generic",
    "linux-image-generic",
    "zfs-dkms",
    "zfsutils-linux",
]

REQUIRED_COMMANDS = [APT_CMD, "systemctl", "zpool", "zfs"]

PROGRESS_WIDTH = 50
OPERATION_SLEEP = 0.05  # seconds

# Defaults for expansion script
SIZE_UNITS = {"K": 1024**1, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # Lower bound (in TiB) for a 2TB drive
EXPECTED_SIZE_TIB_UPPER = 2.0  # Upper bound (in TiB) for a 2TB drive

#####################################
# Nord‑Themed ANSI Colors & Printing
#####################################


class NordColors:
    """Nord‑themed ANSI color codes for terminal output"""

    POLAR_NIGHT_1 = "\033[38;2;46;52;64m"  # #2E3440
    POLAR_NIGHT_2 = "\033[38;2;59;66;82m"  # #3B4252
    SNOW_STORM_1 = "\033[38;2;216;222;233m"  # #D8DEE9
    SNOW_STORM_2 = "\033[38;2;229;233;240m"  # #E5E9F0
    FROST_1 = "\033[38;2;143;188;187m"  # #8FBCBB
    FROST_2 = "\033[38;2;136;192;208m"  # #88C0D0
    FROST_3 = "\033[38;2;129;161;193m"  # #81A1C1
    FROST_4 = "\033[38;2;94;129;172m"  # #5E81AC
    RED = "\033[38;2;191;97;106m"  # #BF616A
    ORANGE = "\033[38;2;208;135;112m"  # #D08770
    YELLOW = "\033[38;2;235;203;139m"  # #EBCB8B
    GREEN = "\033[38;2;163;190;140m"  # #A3BE8C
    PURPLE = "\033[38;2;180;142;173m"  # #B48EAD
    BG_DARK = "\033[48;2;46;52;64m"  # #2E3440
    BG_LIGHT = "\033[48;2;76;86;106m"  # #4C566A
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    HEADER = f"{BOLD}{FROST_2}"
    SUCCESS = f"{GREEN}"
    WARNING = f"{YELLOW}"
    ERROR = f"{RED}"
    INFO = f"{FROST_3}"
    SECTION = f"{BOLD}{FROST_4}"
    EMPHASIS = f"{BOLD}{FROST_1}"
    SUBTLE = f"{SNOW_STORM_1}"


def print_header(message: str) -> None:
    """Print formatted header with ASCII art"""
    term_width = shutil.get_terminal_size().columns
    ascii_art = pyfiglet.figlet_format(message, font="slant")
    print(
        f"\n{NordColors.BG_DARK}{NordColors.FROST_2}{' ' * term_width}{NordColors.RESET}"
    )
    for line in ascii_art.splitlines():
        print(
            f"{NordColors.BG_DARK}{NordColors.BOLD}{line.center(term_width)}{NordColors.RESET}"
        )
    print(
        f"{NordColors.BG_DARK}{NordColors.FROST_2}{' ' * term_width}{NordColors.RESET}\n"
    )


def print_section(message: str) -> None:
    """Print a section header"""
    print(f"\n{NordColors.SECTION}▶ {message}{NordColors.RESET}")


def print_step(message: str, step_num: int = None, total_steps: int = None) -> None:
    """Print a step in the process"""
    step_info = (
        f"[{step_num}/{total_steps}] "
        if (step_num is not None and total_steps is not None)
        else ""
    )
    print(f"{NordColors.FROST_1}→ {step_info}{message}{NordColors.RESET}")


def print_info(message: str) -> None:
    """Print an informational message"""
    print(f"{NordColors.INFO}ℹ {message}{NordColors.RESET}")


def print_success(message: str) -> None:
    """Print a success message"""
    print(f"{NordColors.SUCCESS}✓ {message}{NordColors.RESET}")


def print_warning(message: str) -> None:
    """Print a warning message"""
    print(f"{NordColors.WARNING}⚠ {message}{NordColors.RESET}")


def print_error(message: str) -> None:
    """Print an error message"""
    print(f"{NordColors.ERROR}✗ {message}{NordColors.RESET}")


#####################################
# Progress Tracking Classes
#####################################


class ProgressBar:
    """Thread‑safe progress bar for tracking operations"""

    def __init__(self, total: int = 100, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.completed = False

    def update(self, amount: int = 1) -> None:
        with self._lock:
            self.current = min(self.current + amount, self.total)
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
        eta_str = (
            format_time((self.total - self.current) * elapsed / self.current)
            if (elapsed > 0 and self.current > 0)
            else "N/A"
        )
        sys.stdout.write(
            f"\r{NordColors.SUBTLE}{self.desc}: {NordColors.RESET}"
            f"{NordColors.BG_DARK}{NordColors.FROST_2} {bar} {NordColors.RESET} "
            f"{NordColors.FROST_3}{percent:>5.1f}%{NordColors.RESET} [ETA: {NordColors.FROST_1}{eta_str}{NordColors.RESET}]"
        )
        sys.stdout.flush()
        if self.completed:
            elapsed_str = format_time(elapsed)
            print(
                f"\r{NordColors.SUBTLE}{self.desc}: {NordColors.RESET}"
                f"{NordColors.BG_DARK}{NordColors.FROST_2} {bar} {NordColors.RESET} "
                f"{NordColors.SUCCESS}100.0%{NordColors.RESET} [Completed in: {NordColors.FROST_1}{elapsed_str}{NordColors.RESET}]"
            )


class Spinner:
    """Thread‑safe spinner for long‑running operations"""

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
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._spin)
            self.thread.daemon = True
            self.thread.start()

    def stop(self, success: bool = True, message: str = None) -> None:
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
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"


def setup_logging(log_file: str, log_level: int = logging.INFO) -> None:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
        ],
    )
    try:
        os.chmod(log_file, 0o600)
        logging.info("Set log file permissions to 0600")
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


def run_command(
    command: Union[str, List[str]],
    error_message: Optional[str] = None,
    check: bool = True,
    spinner_text: Optional[str] = None,
    capture_output: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
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


def run_command_simple(command: str) -> Optional[str]:
    """Helper that runs a command and returns stdout if successful, else None."""
    success, stdout, _ = run_command(command, check=False)
    return stdout if success else None


#####################################
# ZFS Setup Functions
#####################################


def check_root_privileges() -> bool:
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with sudo or as root.")
        return False
    return True


def check_dependencies() -> bool:
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
            print(f"  {NordColors.RED}✗ {cmd}{NordColors.RESET}")
        print_info("Attempting to install missing dependencies...")
        if shutil.which(APT_CMD):
            install_packages(missing_commands)
            still_missing = [cmd for cmd in missing_commands if not shutil.which(cmd)]
            if still_missing:
                print_error("Could not install all required commands:")
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


def install_packages(packages: List[str]) -> bool:
    if not packages:
        return True
    package_str = " ".join(packages)
    print_step(f"Installing packages: {package_str}")
    success, _, _ = run_command(
        f"{APT_CMD} update",
        error_message="Failed to update package lists",
        check=False,
        spinner_text="Updating package lists",
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
        )
        if success:
            logging.info(f"Installed package: {package}")
        else:
            logging.error(f"Failed to install package: {package}")
        progress.update(1)
    progress.finish()
    failed_packages = []
    for package in packages:
        success, _, _ = run_command(
            f"dpkg -s {package}", check=False, capture_output=True
        )
        if not success:
            failed_packages.append(package)
    if failed_packages:
        print_warning(f"Failed to install: {', '.join(failed_packages)}")
        return False
    print_success("All packages installed successfully.")
    return True


def install_zfs_packages() -> bool:
    print_section("Installing ZFS Packages")
    return install_packages(ZFS_PACKAGES)


def enable_zfs_services() -> bool:
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


def create_mount_point(mount_point: str) -> bool:
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
    output = run_command_simple("zpool import")
    if not output:
        return []
    pools = []
    for line in output.split("\n"):
        if line.startswith("   pool: "):
            pools.append(line.split("pool: ")[1].strip())
    return pools


def is_pool_imported(pool_name: str) -> bool:
    success, _, _ = run_command(
        f"zpool list {pool_name}",
        error_message=f"Pool {pool_name} is not imported",
        check=False,
        spinner_text=f"Checking if pool '{pool_name}' is imported",
    )
    return success


def import_zfs_pool(pool_name: str, force: bool = False) -> bool:
    print_section(f"Importing ZFS Pool '{pool_name}'")
    if is_pool_imported(pool_name):
        print_info(f"ZFS pool '{pool_name}' is already imported.")
        return True
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
    print_section(f"Configuring ZFS Pool '{pool_name}'")
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
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    return True


def mount_zfs_datasets() -> bool:
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
            print(f"  {NordColors.SUBTLE}{line}{NordColors.RESET}")
        return False


def show_zfs_status(pool_name: str) -> None:
    print_section(f"ZFS Pool Status for '{pool_name}'")
    success, stdout, _ = run_command(
        f"zpool status {pool_name}",
        error_message=f"Failed to get status for pool '{pool_name}'",
        check=False,
    )
    if success and stdout:
        print(f"{NordColors.FROST_3}{stdout}{NordColors.RESET}")
    else:
        print_warning(f"Could not get pool status for '{pool_name}'")
    success, stdout, _ = run_command(
        f"zpool get all {pool_name}",
        error_message=f"Failed to get properties for pool '{pool_name}'",
        check=False,
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
                print(f"  {NordColors.SUBTLE}{line}{NordColors.RESET}")
    else:
        print_warning(f"Could not get pool properties for '{pool_name}'")


def interactive_setup() -> Tuple[str, str, str, bool]:
    print_section("Interactive ZFS Setup")
    available_pools = list_available_pools()
    if available_pools:
        print_info(f"Available ZFS pools: {', '.join(available_pools)}")
        pool_name = (
            input(
                f"{NordColors.FROST_1}Enter pool name [{DEFAULT_POOL_NAME}]: {NordColors.RESET}"
            ).strip()
            or DEFAULT_POOL_NAME
        )
    else:
        print_info("No available pools detected. You'll need to specify the pool name.")
        pool_name = (
            input(
                f"{NordColors.FROST_1}Enter pool name [{DEFAULT_POOL_NAME}]: {NordColors.RESET}"
            ).strip()
            or DEFAULT_POOL_NAME
        )
    default_mount = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    mount_point = (
        input(
            f"{NordColors.FROST_1}Enter mount point [{default_mount}]: {NordColors.RESET}"
        ).strip()
        or default_mount
    )
    cache_file = (
        input(
            f"{NordColors.FROST_1}Enter cache file path [{DEFAULT_CACHE_FILE}]: {NordColors.RESET}"
        ).strip()
        or DEFAULT_CACHE_FILE
    )
    force_input = input(
        f"{NordColors.FROST_1}Force import if needed? (y/N): {NordColors.RESET}"
    )
    force = force_input.lower() in ("y", "yes")
    print_info("Selected configuration:")
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


def execute_zfs_setup(args: Any) -> bool:
    pool_name = args.pool_name
    mount_point = args.mount_point
    cache_file = args.cache_file
    force = args.force
    steps_total = 6
    current_step = 0
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(args.log_file, log_level)
    start_time = datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)
    try:
        current_step += 1
        print_step("Checking system dependencies", current_step, steps_total)
        if not check_dependencies():
            return False
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
        current_step += 1
        print_step("Enabling ZFS services", current_step, steps_total)
        enable_zfs_services()
        current_step += 1
        print_step(f"Creating mount point: {mount_point}", current_step, steps_total)
        if not create_mount_point(mount_point):
            return False
        current_step += 1
        print_step(f"Importing ZFS pool: {pool_name}", current_step, steps_total)
        if not import_zfs_pool(pool_name, force):
            return False
        current_step += 1
        print_step(f"Configuring ZFS pool: {pool_name}", current_step, steps_total)
        if not configure_zfs_pool(pool_name, mount_point, cache_file):
            print_warning("Pool configuration had issues, but continuing...")
        mount_zfs_datasets()
        if not verify_mount(pool_name, mount_point):
            print_warning("ZFS mount verification failed. Check mount status manually.")
        show_zfs_status(pool_name)
        return True
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        print_error(f"Setup failed: {e}")
        return False


#####################################
# ZFS Pool Expansion Functions
#####################################


def get_zpool_status() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    output = run_command_simple("zpool status")
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


def get_zfs_list() -> Optional[List[Dict[str, str]]]:
    output = run_command_simple(
        "zfs list -o name,used,available,refer,mountpoint -t all -H"
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


def get_block_device_size(device_path: str) -> Optional[int]:
    base_device = re.sub(r"p?\d+$", "", device_path)
    output = run_command_simple(f"lsblk -b -n -o SIZE {base_device}")
    if output:
        try:
            return int(output)
        except ValueError:
            print_warning(f"Could not parse device size from output: '{output}'")
    return None


def _set_autoexpand_property(pool_name: str) -> bool:
    current_output = run_command_simple(f"zpool get autoexpand {pool_name}")
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
        if run_command_simple(f"zpool set autoexpand=on {pool_name}") is not None:
            print_success("autoexpand property enabled.")
            return True
        else:
            print_error("Failed to enable autoexpand property.")
            return False
    else:
        print_success("autoexpand is already enabled.")
        return True


def _verify_pool_resize(pool_name: str) -> bool:
    print_step("Retrieving initial pool status...")
    initial_status = get_zpool_status()
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
    print(f"Initial allocatable pool size: {bytes_to_human_readable(initial_size)}")
    print_step(f"Waiting {WAIT_TIME_SECONDS} seconds for background resizing...")
    time.sleep(WAIT_TIME_SECONDS)
    print_step("Retrieving final pool status...")
    final_status = get_zpool_status()
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
    print(f"Final allocatable pool size: {bytes_to_human_readable(final_size)}")
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


def expand_zpool(pool_name: str, device_path: str) -> bool:
    print_header(f"Expanding ZFS Pool: {pool_name}")
    print_step("Step 1: Enabling autoexpand property...")
    if not _set_autoexpand_property(pool_name):
        print_warning("Could not set autoexpand property. Continuing anyway...")
    print_step("Step 2: Initiating online expansion...")
    if run_command_simple(f"zpool online -e {pool_name} {device_path}") is None:
        print_error(
            f"Failed to initiate online expansion for '{device_path}' in pool '{pool_name}'."
        )
        return False
    print_success(
        f"Online expansion initiated for '{device_path}' in pool '{pool_name}'."
    )
    print_step("Step 3: Verifying pool resize...")
    return _verify_pool_resize(pool_name)


def convert_size_to_bytes(size_str: str) -> int:
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


def bytes_to_human_readable(bytes_val: Optional[int]) -> str:
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


def validate_expansion() -> bool:
    print_section("Validating ZFS Expansion")
    zpool_info = get_zpool_status()
    zfs_datasets = get_zfs_list()
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
    print(f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size)}")
    total_used = 0
    total_available = 0
    print_section("ZFS Datasets Summary:")
    for dataset in zfs_datasets:
        console = Console()
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


#####################################
# CLI Command Group
#####################################


@click.group()
@click.version_option(version="1.0.0")
def cli() -> None:
    """
    Unified ZFS Management CLI

    Use the 'setup' command to install, configure, and import a ZFS pool.
    Use the 'expand' command to perform online expansion of ZFS pools.
    """
    pass


@cli.command()
@click.option(
    "--pool-name", default=DEFAULT_POOL_NAME, help="Name of the ZFS pool to import"
)
@click.option(
    "--mount-point",
    default=None,
    help="Mount point for the ZFS pool (default: /media/{pool_name})",
)
@click.option(
    "--cache-file", default=DEFAULT_CACHE_FILE, help="Path to the ZFS cache file"
)
@click.option("--force", is_flag=True, help="Force import of the ZFS pool")
@click.option("--skip-install", is_flag=True, help="Skip package installation")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--interactive", is_flag=True, help="Run interactive setup")
def setup(
    pool_name: str,
    mount_point: Optional[str],
    cache_file: str,
    force: bool,
    skip_install: bool,
    verbose: bool,
    interactive: bool,
) -> None:
    """Enhanced ZFS Setup – install packages, enable services, import and configure a ZFS pool."""
    os.system("clear" if os.name == "posix" else "cls")
    print_header("Enhanced ZFS Setup")
    if not check_root_privileges():
        sys.exit(1)
    if not run_command_simple("modprobe zfs"):
        print_warning(
            "ZFS kernel module could not be loaded. You may need to install ZFS packages first."
        )
    if interactive:
        try:
            pool_name, mount_point, cache_file, force = interactive_setup()
        except KeyboardInterrupt:
            print_warning("Setup cancelled by user.")
            sys.exit(130)
    else:
        if mount_point is None:
            mount_point = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)

    class Args:
        pass

    args = Args()
    args.pool_name = pool_name
    args.mount_point = mount_point
    args.cache_file = cache_file
    args.force = force
    args.skip_install = skip_install
    args.verbose = verbose
    start_time = time.time()
    success = execute_zfs_setup(args)
    end_time = time.time()
    elapsed = end_time - start_time
    print_header("ZFS Setup Summary")
    if success:
        print_success("ZFS setup completed successfully!")
    else:
        print_error("ZFS setup encountered errors.")
    print_info(f"Pool name: {pool_name}")
    print_info(f"Mount point: {mount_point}")
    print_info(f"Elapsed time: {format_time(elapsed)}")
    print_info(f"Log file: {DEFAULT_LOG_FILE}")
    if success:
        print_section("Next Steps")
        print(
            f"{NordColors.FROST_3}Your ZFS pool is now configured and imported.{NordColors.RESET}"
        )
        print(
            f"{NordColors.FROST_3}Access your data at: {NordColors.RESET}{mount_point}"
        )
        print(f"{NordColors.FROST_3}Helpful ZFS commands:{NordColors.RESET}")
        print(
            f"  {NordColors.FROST_1}zfs list{NordColors.RESET}              - List ZFS filesystems"
        )
        print(
            f"  {NordColors.FROST_1}zpool status {pool_name}{NordColors.RESET}  - Show pool status"
        )
        print(
            f"  {NordColors.FROST_1}zfs get all {pool_name}{NordColors.RESET}   - Show all properties"
        )
    sys.exit(0 if success else 1)


@cli.command()
def expand() -> None:
    """ZFS Pool Expansion – expand pools to use the full size of underlying devices."""
    print_header("ZFS Pool Expansion")
    print_info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if not check_root_privileges():
        sys.exit(1)
    pool_status = get_zpool_status()
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
    pool_device_paths: Dict[str, str] = {}
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
        print(f"  Pool: [bold]{name}[/bold], Device: [italic]{dev}[/italic]")
    if not pool_device_paths:
        print_error("No valid pool-device pairs found. Aborting expansion.")
        sys.exit(1)
    print_section("Starting ZFS Pool Expansion Process")
    expansion_results: Dict[str, bool] = {}
    for pool_name, device_path in pool_device_paths.items():
        result = expand_zpool(pool_name, device_path)
        expansion_results[pool_name] = result
    print_section("Expansion Process Completed")
    validation = validate_expansion()
    print_section("Expansion Results Summary")
    for pool_name, success in expansion_results.items():
        status_text = "Successful" if success else "Failed"
        print(f"  Pool [bold]{pool_name}[/bold]: {status_text}")
    overall = (
        "Successful" if all(expansion_results.values()) and validation else "Failed"
    )
    print(f"Overall validation: [bold]{overall}[/bold]")
    print_info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sys.exit(0 if all(expansion_results.values()) and validation else 1)


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
