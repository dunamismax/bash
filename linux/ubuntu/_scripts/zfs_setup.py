#!/usr/bin/env python3
"""
Automated ZFS Management
--------------------------------------------------
A streamlined, fully automated terminal utility for ZFS pool management.
This script performs:
  • ZFS Setup – installs required packages, enables ZFS services, creates mount points,
    imports pools, and configures mountpoints/cache settings.
  • ZFS Expansion – expands ZFS pools to utilize full device capacity and validates resizing.
Features include elegant progress tracking with Rich, a stylish ASCII banner via Pyfiglet,
and detailed logging. Must be run with root privileges on Linux systems with ZFS support.

Usage:
  sudo python3 automated_zfs.py

Version: 2.0.0
"""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "This script requires the 'rich' and 'pyfiglet' libraries.\n"
        "Please install them using: pip install rich pyfiglet"
    )
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.0.0"
DEFAULT_POOL_NAME = "tank"
DEFAULT_MOUNT_POINT = "/media/{pool_name}"
DEFAULT_CACHE_FILE = "/etc/zfs/zpool.cache"
DEFAULT_LOG_FILE = "/var/log/zfs_setup.log"

# Command preferences – use 'nala' if available, otherwise apt.
APT_CMD = "nala" if shutil.which("nala") else "apt"

# ZFS services and packages
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

# Progress tracking configuration
PROGRESS_WIDTH = 50
OPERATION_SLEEP = 0.05  # seconds

# Defaults for expansion validation (using Tebibytes for comparison)
SIZE_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # Lower bound for a 2TB drive
EXPECTED_SIZE_TIB_UPPER = 2.0  # Upper bound for a 2TB drive

TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
APP_NAME = "Auto ZFS"
APP_SUBTITLE = "Automated Pool Management"


# ----------------------------------------------------------------
# Nord-Themed Colors for Consistent Styling
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# Create a Rich Console instance
console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ZFSPool:
    """
    Represents a ZFS pool and its properties.
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

    def format_size(self) -> str:
        return bytes_to_human_readable(self.size)


# ----------------------------------------------------------------
# Console Helpers and ASCII Banner
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate a stylish ASCII banner using Pyfiglet and wrap it in a Rich Panel.
    """
    fonts = ["slant", "small", "digital", "big"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        styled_text += f"[bold {colors[i % len(colors)]}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    content = f"{border}\n{styled_text}{border}"
    header_panel = Panel(
        Text.from_markup(content),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def log_message(message: str, level: str = "info") -> None:
    """Log a message and print it using styled Rich text."""
    if level == "error":
        console.print(f"[bold {NordColors.RED}]✗ {message}[/]")
    elif level == "warning":
        console.print(f"[bold {NordColors.YELLOW}]⚠ {message}[/]")
    elif level == "success":
        console.print(f"[bold {NordColors.GREEN}]✓ {message}[/]")
    else:
        console.print(f"[bold {NordColors.FROST_2}]ℹ {message}[/]")


# ----------------------------------------------------------------
# Formatting Helpers
# ----------------------------------------------------------------
def bytes_to_human_readable(num_bytes: Optional[int]) -> str:
    if num_bytes is None:
        return "N/A"
    if num_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


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
    return int(size_str)


def format_time(seconds: float) -> str:
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
def setup_logging(log_file: str = DEFAULT_LOG_FILE, level: int = logging.INFO) -> None:
    try:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=level,
            format="%(asctime)s - %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        os.chmod(log_file, 0o600)
        log_message(f"Logging configured to: {log_file}", "info")
    except Exception as e:
        log_message(f"Logging setup failed: {e}", "warning")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    log_message("Performing cleanup tasks...", "info")
    logging.info("Cleanup completed")


atexit.register(cleanup)


def signal_handler(sig: int, frame: Any) -> None:
    sig_name = getattr(signal, "Signals", lambda s: f"signal {s}")(sig)
    log_message(f"Script interrupted by {sig_name}.", "warning")
    cleanup()
    sys.exit(128 + sig)


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


# ----------------------------------------------------------------
# Command Execution Helpers
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
    Execute a shell command with an optional spinner and error handling.
    """
    spinner = None
    if spinner_text and not verbose:
        spinner = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{spinner_text}[/]"),
            transient=True,
            console=console,
        )
        spinner.start()
    try:
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            check=check,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            env=cmd_env,
        )
        stdout = result.stdout.strip() if result.stdout else None
        stderr = result.stderr.strip() if result.stderr else None
        if spinner:
            spinner.stop()
        return True, stdout, stderr
    except subprocess.CalledProcessError as e:
        err_output = e.stderr.strip() if e.stderr else "No error output"
        if spinner:
            spinner.stop()
        if error_message:
            logging.error(f"{error_message}: {err_output}")
            if verbose:
                log_message(f"{error_message}: {err_output}", "error")
        else:
            logging.error(f"Command failed: {command}")
            logging.error(f"Error: {err_output}")
            if verbose:
                log_message(f"Command failed: {command}", "error")
                log_message(f"Error: {err_output}", "error")
        if check:
            raise
        return False, None, err_output
    except Exception as e:
        if spinner:
            spinner.stop()
        logging.error(f"Exception while running command: {e}")
        if verbose:
            log_message(f"Exception while running command: {e}", "error")
        if check:
            raise
        return False, None, str(e)


def run_command_simple(
    command: Union[str, List[str]], verbose: bool = False
) -> Optional[str]:
    success, stdout, _ = run_command(command, check=False, verbose=verbose)
    return stdout if success else None


# ----------------------------------------------------------------
# System Check and Package Management
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    if os.geteuid() != 0:
        log_message("This script must be run as root. Exiting.", "error")
        return False
    return True


def check_dependencies(verbose: bool = False) -> bool:
    log_message("Checking required dependencies...", "info")
    missing = []
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn("[bold {NordColors.SNOW_STORM_1}]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Checking", total=len(REQUIRED_COMMANDS))
        for cmd in REQUIRED_COMMANDS:
            if not shutil.which(cmd):
                missing.append(cmd)
            progress.advance(task)
    if missing:
        log_message(f"Missing required commands: {', '.join(missing)}", "error")
        return False
    log_message("All required dependencies are installed.", "success")
    return True


def install_packages(packages: List[str], verbose: bool = False) -> bool:
    if not packages:
        return True
    package_str = " ".join(packages)
    log_message(f"Installing packages: {package_str}", "info")
    # Update package lists
    success, _, _ = run_command(
        f"{APT_CMD} update",
        error_message="Failed to update package lists",
        spinner_text="Updating package lists",
        verbose=verbose,
    )
    if not success:
        log_message("Package list update failed. Continuing anyway...", "warning")
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Installing packages"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn("[bold {NordColors.SNOW_STORM_1}]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Installing", total=len(packages))
        failed = []
        for package in packages:
            success, _, _ = run_command(
                f"{APT_CMD} install -y {package}",
                error_message=f"Failed to install {package}",
                check=False,
                verbose=verbose,
            )
            if not success:
                failed.append(package)
            progress.advance(task)
    if failed:
        log_message(f"Failed to install: {', '.join(failed)}", "warning")
        return False
    log_message("All packages installed successfully.", "success")
    return True


def enable_zfs_services(verbose: bool = False) -> bool:
    log_message("Enabling ZFS services...", "info")
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Enabling services"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn("[bold {NordColors.SNOW_STORM_1}]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Enabling", total=len(ZFS_SERVICES))
        enabled, failed = [], []
        for service in ZFS_SERVICES:
            success, _, _ = run_command(
                f"systemctl enable {service}",
                error_message=f"Failed to enable {service}",
                check=False,
                verbose=verbose,
            )
            if success:
                enabled.append(service)
            else:
                failed.append(service)
            progress.advance(task)
    if failed:
        log_message(f"Failed to enable services: {', '.join(failed)}", "warning")
        return len(failed) < len(ZFS_SERVICES)
    log_message(f"Enabled services: {', '.join(enabled)}", "success")
    return True


def create_mount_point(mount_point: str, verbose: bool = False) -> bool:
    log_message(f"Creating mount point: {mount_point}", "info")
    try:
        os.makedirs(mount_point, exist_ok=True)
        logging.info(f"Created mount point: {mount_point}")
        return True
    except Exception as e:
        log_message(f"Failed to create mount point '{mount_point}': {e}", "error")
        return False


# ----------------------------------------------------------------
# ZFS Pool and Dataset Functions
# ----------------------------------------------------------------
def list_available_pools(verbose: bool = False) -> List[str]:
    log_message("Scanning for available ZFS pools...", "info")
    output = run_command_simple("zpool import", verbose)
    if not output:
        log_message("No available pools detected.", "info")
        return []
    pools = []
    for line in output.splitlines():
        if line.strip().startswith("pool:"):
            pools.append(line.split("pool:")[1].strip())
    if pools:
        log_message(f"Found available pools: {', '.join(pools)}", "info")
    else:
        log_message("No importable pools found.", "info")
    return pools


def is_pool_imported(pool_name: str, verbose: bool = False) -> bool:
    success, _, _ = run_command(
        f"zpool list {pool_name}",
        error_message=f"Pool {pool_name} is not imported",
        check=False,
        verbose=verbose,
    )
    if success:
        log_message(f"Pool '{pool_name}' is already imported.", "info")
    else:
        log_message(f"Pool '{pool_name}' is not imported.", "info")
    return success


def import_zfs_pool(pool_name: str, force: bool = False, verbose: bool = False) -> bool:
    log_message(f"Importing ZFS pool '{pool_name}'...", "info")
    if is_pool_imported(pool_name, verbose):
        log_message(f"Pool '{pool_name}' is already imported.", "success")
        return True
    force_flag = "-f" if force else ""
    success, _, stderr = run_command(
        f"zpool import {force_flag} {pool_name}",
        error_message=f"Failed to import pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )
    if success:
        log_message(f"Successfully imported pool '{pool_name}'.", "success")
        return True
    else:
        log_message(f"Failed to import pool '{pool_name}'. Error: {stderr}", "error")
        # Attempt to import first available pool if our desired one is missing
        available = list_available_pools(verbose)
        if available and pool_name not in available:
            alt_pool = available[0]
            log_message(f"Attempting to import alternative pool '{alt_pool}'.", "info")
            return import_zfs_pool(alt_pool, force, verbose)
        return False


def configure_zfs_pool(
    pool_name: str, mount_point: str, cache_file: str, verbose: bool = False
) -> bool:
    log_message(f"Configuring pool '{pool_name}'...", "info")
    # Set mountpoint
    success, _, stderr = run_command(
        f"zfs set mountpoint={mount_point} {pool_name}",
        error_message=f"Failed to set mountpoint for '{pool_name}'",
        check=False,
        verbose=verbose,
    )
    if not success:
        log_message(f"Failed to set mountpoint for '{pool_name}': {stderr}", "error")
        return False
    log_message(f"Mountpoint set to '{mount_point}' for pool '{pool_name}'.", "success")
    # Set cachefile (ensure directory exists)
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    success, _, stderr = run_command(
        f"zpool set cachefile={cache_file} {pool_name}",
        error_message=f"Failed to set cachefile for '{pool_name}'",
        check=False,
        verbose=verbose,
    )
    if not success:
        log_message(f"Failed to set cachefile for '{pool_name}': {stderr}", "error")
        log_message(
            "Pool imported but cachefile was not set. Mount on boot may fail.",
            "warning",
        )
        return False
    log_message(f"Cachefile set to '{cache_file}' for pool '{pool_name}'.", "success")
    return True


def mount_zfs_datasets(verbose: bool = False) -> bool:
    log_message("Mounting ZFS datasets...", "info")
    success, _, stderr = run_command(
        "zfs mount -a",
        error_message="Failed to mount ZFS datasets",
        check=False,
        verbose=verbose,
    )
    if success:
        log_message("ZFS datasets mounted successfully.", "success")
        return True
    else:
        log_message(f"Mounting datasets encountered issues: {stderr}", "warning")
        return False


def verify_mount(pool_name: str, mount_point: str, verbose: bool = False) -> bool:
    log_message("Verifying ZFS mount points...", "info")
    success, stdout, _ = run_command(
        "zfs list -o name,mountpoint -H",
        error_message="Failed to list ZFS filesystems",
        check=False,
        verbose=verbose,
    )
    if not success or not stdout:
        log_message("Failed to verify mount status.", "error")
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
        log_message(
            f"Pool '{pool_name}' is mounted correctly at '{mount_point}'.", "success"
        )
        return True
    elif pool_found:
        log_message(
            f"Pool '{pool_name}' is mounted at '{actual_mount}' (expected: '{mount_point}').",
            "warning",
        )
        return False
    else:
        log_message(f"Pool '{pool_name}' is not mounted.", "error")
        # Optionally display current mounts in a table
        table = Table(show_header=True, header_style=f"bold {NordColors.FROST_1}")
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
    log_message(f"Retrieving status for pool '{pool_name}'...", "info")
    success, stdout, _ = run_command(
        f"zpool status {pool_name}",
        error_message=f"Failed to get status for pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )
    if success and stdout:
        panel = Panel(
            Text.from_markup(stdout),
            title=f"[bold {NordColors.FROST_2}]Pool Status[/]",
            border_style=NordColors.FROST_3,
        )
        console.print(panel)
    else:
        log_message(f"Could not get pool status for '{pool_name}'.", "warning")
    success, stdout, _ = run_command(
        f"zpool get all {pool_name}",
        error_message=f"Failed to get properties for pool '{pool_name}'",
        check=False,
        verbose=verbose,
    )
    if success and stdout:
        props = [
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
            title=f"[bold {NordColors.FROST_2}]Important Pool Properties[/]",
            title_justify="center",
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)
        table.add_column("Source", style=NordColors.SNOW_STORM_2)
        for line in stdout.splitlines():
            for prop in props:
                if f"{pool_name}\t{prop}\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        table.add_row(parts[1], parts[2], parts[3])
        console.print(table)
    else:
        log_message(f"Could not get pool properties for '{pool_name}'.", "warning")


# ----------------------------------------------------------------
# ZFS Expansion Functions
# ----------------------------------------------------------------
def get_zpool_status(
    verbose: bool = False,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
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
            current_pool = {
                "name": pool_match.group(1).strip(),
                "vdevs": [],
                "allocatable": None,
            }
            pool_info["pools"].append(current_pool)
            continue
        if current_pool:
            state_match = state_regex.match(line)
            if state_match:
                current_pool["state"] = state_match.group(1).strip()
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
    log_message(f"Checking autoexpand property for pool '{pool_name}'...", "info")
    current_output = run_command_simple(f"zpool get autoexpand {pool_name}", verbose)
    if not current_output:
        log_message("Failed to get autoexpand property.", "error")
        return False
    autoexpand_value = None
    match = re.search(rf"{re.escape(pool_name)}\s+autoexpand\s+(\S+)", current_output)
    if match:
        autoexpand_value = match.group(1).strip()
    elif "on" in current_output.lower():
        autoexpand_value = "on"
    elif "off" in current_output.lower():
        autoexpand_value = "off"
    if autoexpand_value is None:
        log_message(
            f"Could not parse autoexpand value from: '{current_output}'", "warning"
        )
        return False
    if autoexpand_value != "on":
        log_message(f"autoexpand is '{autoexpand_value}'. Enabling it...", "info")
        success = (
            run_command_simple(f"zpool set autoexpand=on {pool_name}", verbose)
            is not None
        )
        if success:
            log_message("autoexpand property enabled.", "success")
            return True
        else:
            log_message("Failed to enable autoexpand property.", "error")
            return False
    else:
        log_message("autoexpand is already enabled.", "success")
        return True


def verify_pool_resize(pool_name: str, verbose: bool = False) -> bool:
    log_message("Retrieving initial pool status...", "info")
    initial_status = get_zpool_status(verbose)
    if not initial_status:
        log_message("Failed to retrieve initial zpool status.", "error")
        return False
    initial_pool = next(
        (p for p in initial_status["pools"] if p["name"] == pool_name), None
    )
    if not initial_pool:
        log_message(f"Pool '{pool_name}' not found in initial status.", "error")
        return False
    initial_size = initial_pool.get("allocatable")
    log_message(
        f"Initial allocatable size: {bytes_to_human_readable(initial_size)}", "info"
    )
    log_message(
        f"Waiting {WAIT_TIME_SECONDS} seconds for background resizing...", "info"
    )
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Waiting for resizing"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Waiting", total=WAIT_TIME_SECONDS)
        for _ in range(WAIT_TIME_SECONDS):
            time.sleep(1)
            progress.advance(task)
    log_message("Retrieving final pool status...", "info")
    final_status = get_zpool_status(verbose)
    if not final_status:
        log_message("Failed to retrieve final zpool status.", "error")
        return False
    final_pool = next(
        (p for p in final_status["pools"] if p["name"] == pool_name), None
    )
    if not final_pool:
        log_message(f"Pool '{pool_name}' not found in final status.", "error")
        return False
    final_size = final_pool.get("allocatable")
    log_message(
        f"Final allocatable size: {bytes_to_human_readable(final_size)}", "info"
    )
    if final_size is None or initial_size is None:
        log_message("Could not compare pool sizes.", "error")
        return False
    if final_size >= initial_size:
        log_message(f"Pool '{pool_name}' successfully resized.", "success")
        if final_size > initial_size:
            log_message(
                f"Size increased by: {bytes_to_human_readable(final_size - initial_size)}",
                "success",
            )
        return True
    else:
        log_message(
            f"Pool size decreased from {bytes_to_human_readable(initial_size)} to {bytes_to_human_readable(final_size)}",
            "warning",
        )
        return False


def expand_zpool(pool_name: str, device_path: str, verbose: bool = False) -> bool:
    total_steps = 3
    log_message("Step 1: Enabling autoexpand property...", "info")
    set_autoexpand_property(pool_name, verbose)
    log_message("Step 2: Initiating online expansion...", "info")
    success = (
        run_command_simple(f"zpool online -e {pool_name} {device_path}", verbose)
        is not None
    )
    if not success:
        log_message(
            f"Failed to initiate online expansion for device '{device_path}' in pool '{pool_name}'",
            "error",
        )
        return False
    log_message(
        f"Online expansion initiated for device '{device_path}' in pool '{pool_name}'",
        "success",
    )
    log_message("Step 3: Verifying pool resize...", "info")
    return verify_pool_resize(pool_name, verbose)


def validate_expansion(verbose: bool = False) -> bool:
    log_message("Validating ZFS expansion results...", "info")
    zpool_info = get_zpool_status(verbose)
    zfs_datasets = get_zfs_list(verbose)
    if not zpool_info or not zfs_datasets:
        log_message(
            "Failed to retrieve pool or dataset information for validation.", "error"
        )
        return False
    total_pool_size = None
    if zpool_info["pools"]:
        pool_to_check = next(
            (p for p in zpool_info["pools"] if p["name"] == "rpool"),
            zpool_info["pools"][0],
        )
        total_pool_size = pool_to_check.get("allocatable")
    log_message(
        f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size)}", "info"
    )
    total_used = 0
    total_available = 0
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
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
            log_message(
                f"Could not parse used space '{dataset['used']}' for dataset {dataset['name']}",
                "warning",
            )
        if dataset["available"] != "-":
            try:
                total_available += convert_size_to_bytes(dataset["available"])
            except ValueError:
                log_message(
                    f"Could not parse available space '{dataset['available']}' for dataset {dataset['name']}",
                    "warning",
                )
    console.print(table)
    summary = Panel(
        Text.from_markup(
            f"Total Used Space: [{NordColors.FROST_2}]{bytes_to_human_readable(total_used)}[/]\n"
            f"Total Available Space: [{NordColors.FROST_2}]{bytes_to_human_readable(total_available)}[/]\n"
            f"Total Pool Size: [{NordColors.FROST_2}]{bytes_to_human_readable(total_pool_size)}[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]Expansion Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(summary)
    expected_lower = EXPECTED_SIZE_TIB_LOWER * (1024**4)
    if total_pool_size is not None and total_pool_size > expected_lower:
        log_message(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is within expected range.",
            "success",
        )
        return True
    else:
        log_message(
            f"Pool size ({bytes_to_human_readable(total_pool_size)}) is smaller than expected.",
            "warning",
        )
        return False


# ----------------------------------------------------------------
# Automated ZFS Setup and Expansion Execution
# ----------------------------------------------------------------
def execute_zfs_setup(verbose: bool = False) -> bool:
    """
    Execute the complete ZFS setup process automatically.
    Returns True if successful, False otherwise.
    """
    pool_name = DEFAULT_POOL_NAME
    mount_point = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
    cache_file = DEFAULT_CACHE_FILE
    force = True

    total_steps = 6
    setup_logging(DEFAULT_LOG_FILE, logging.DEBUG if verbose else logging.INFO)
    start_time = datetime.datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        log_message("PHASE 1: ZFS SETUP", "info")
        # Step 1: Check dependencies
        log_message("Checking system dependencies...", "info")
        if not check_dependencies(verbose):
            return False
        # Step 2: Install ZFS packages
        log_message("Installing ZFS packages...", "info")
        if not install_packages(ZFS_PACKAGES, verbose):
            log_message(
                "Issues encountered during package installation, continuing...",
                "warning",
            )
        # Step 3: Enable ZFS services
        enable_zfs_services(verbose)
        # Step 4: Create mount point
        if not create_mount_point(mount_point, verbose):
            return False
        # Check available pools; if found, use the first one
        available_pools = list_available_pools(verbose)
        if available_pools:
            pool_name = available_pools[0]
            mount_point = DEFAULT_MOUNT_POINT.format(pool_name=pool_name)
            log_message(f"Found available pool: {pool_name}", "info")
            log_message(f"Using mount point: {mount_point}", "info")
            create_mount_point(mount_point, verbose)
        # Step 5: Import pool
        if not import_zfs_pool(pool_name, force, verbose):
            return False
        # Step 6: Configure pool
        if not configure_zfs_pool(pool_name, mount_point, cache_file, verbose):
            log_message(
                "Pool configuration encountered issues, continuing...", "warning"
            )
        # Extra: Mount datasets and verify mount
        mount_zfs_datasets(verbose)
        verify_mount(pool_name, mount_point, verbose)
        # Show pool status for logging
        show_zfs_status(pool_name, verbose)
        return True
    except Exception as e:
        logging.error(f"Unhandled exception in setup: {e}")
        log_message(f"Setup failed: {e}", "error")
        return False


def execute_zfs_expansion(verbose: bool = False) -> bool:
    """
    Execute ZFS pool expansion on available pools.
    Returns True if expansion and validation are successful.
    """
    pool_status = get_zpool_status(verbose)
    if not pool_status or not pool_status["pools"]:
        log_message("No ZFS pools found for expansion.", "error")
        return False
    pool_device_paths = {}
    for pool in pool_status["pools"]:
        pool_name = pool["name"]
        vdevs = pool.get("vdevs", [])
        if not vdevs:
            log_message(f"No vdevs found for pool '{pool_name}'. Skipping.", "warning")
            continue
        device_path = vdevs[0].get("path")
        if not device_path:
            log_message(
                f"Could not determine device for pool '{pool_name}'. Skipping.",
                "warning",
            )
            continue
        pool_device_paths[pool_name] = device_path
    if not pool_device_paths:
        log_message("No valid pool-device pairs found. Aborting expansion.", "error")
        return False
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        title=f"[bold {NordColors.FROST_2}]Detected ZFS Pools and Devices[/]",
        title_justify="center",
    )
    table.add_column("Pool", style=f"bold {NordColors.FROST_2}")
    table.add_column("Device", style=NordColors.SNOW_STORM_1)
    for name, dev in pool_device_paths.items():
        table.add_row(name, dev)
    console.print(table)
    log_message("Starting ZFS Pool Expansion Process...", "info")
    expansion_results = {}
    for pool_name, device_path in pool_device_paths.items():
        panel = Panel(
            f"Pool: {pool_name}\nDevice: {device_path}",
            title=f"[bold {NordColors.FROST_2}]Expanding Pool[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
        console.print(panel)
        result = expand_zpool(pool_name, device_path, verbose)
        expansion_results[pool_name] = result
    log_message("Validating Expansion Results...", "info")
    validation = validate_expansion(verbose)
    results_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
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
    overall = (
        "Successful" if all(expansion_results.values()) and validation else "Failed"
    )
    overall_color = NordColors.GREEN if overall == "Successful" else NordColors.RED
    results_table.add_row("Overall Validation", f"[bold {overall_color}]{overall}[/]")
    console.print(results_table)
    return all(expansion_results.values()) and validation


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function: automatically executes ZFS setup and expansion."""
    if not check_root_privileges():
        sys.exit(1)
    clear_screen()
    console.print(create_header())
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message(f"Auto ZFS Script started at: {current_time}", "info")
    log_message("Running in fully automated mode.", "info")
    verbose = True  # Set True for detailed logging and output
    log_message("PHASE 1: ZFS SETUP", "info")
    setup_success = execute_zfs_setup(verbose)
    if not setup_success:
        log_message("ZFS setup completed with issues.", "warning")
    else:
        log_message("ZFS setup completed successfully.", "success")
    log_message("PHASE 2: ZFS EXPANSION", "info")
    expansion_success = execute_zfs_expansion(verbose)
    if not expansion_success:
        log_message("ZFS expansion completed with issues.", "warning")
    else:
        log_message("ZFS expansion completed successfully.", "success")
    final_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall_status = (
        "Successful" if setup_success and expansion_success else "Completed with issues"
    )
    status_color = (
        NordColors.GREEN if setup_success and expansion_success else NordColors.YELLOW
    )
    summary_panel = Panel(
        Text.from_markup(
            f"Status: [{status_color}]{overall_status}[/]\n"
            f"Completed at: [{NordColors.FROST_2}]{final_time}[/]\n"
            f"Log file: [{NordColors.FROST_2}]{DEFAULT_LOG_FILE}[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]ZFS Management Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(summary_panel)
    sys.exit(0 if setup_success and expansion_success else 1)


if __name__ == "__main__":
    main()
