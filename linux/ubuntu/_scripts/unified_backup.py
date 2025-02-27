#!/usr/bin/env python3
"""
Enhanced Unified Restic Backup Script

This script performs comprehensive backups of multiple system components:
  • System (root filesystem)
  • Virtual Machines (libvirt)
  • Plex Media Server

It uses restic to create efficient, incremental backups to Backblaze B2 storage with
detailed progress tracking, robust error handling, and clear status reporting.
The script handles each service independently, with appropriate exclusion patterns
and repository organization.

Improvements over the original version:
  • Enhanced progress tracking with fallback modes
  • Command-line arguments for non-interactive operation
  • More robust error handling and recovery
  • Improved Nord-themed UI
  • Backup summary and reporting
  • Optimized size estimation

Note: Run this script with root privileges.
"""

import argparse
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository paths
REPOSITORIES = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup sources and excludes
BACKUP_CONFIGS = {
    "system": {
        "paths": ["/"],
        "excludes": [
            "/proc/*",
            "/sys/*",
            "/dev/*",
            "/run/*",
            "/tmp/*",
            "/var/tmp/*",
            "/mnt/*",
            "/media/*",
            "/var/cache/*",
            "/var/log/*",
            "/home/*/.cache/*",
            "/swapfile",
            "/lost+found",
            "*.vmdk",
            "*.vdi",
            "*.qcow2",
            "*.img",
            "*.iso",
            "*.tmp",
            "*.swap.img",
            "/var/lib/docker/*",
            "/var/lib/lxc/*",
        ],
        "name": "System",
        "description": "Root filesystem backup",
    },
    "vm": {
        "paths": ["/etc/libvirt", "/var/lib/libvirt"],
        "excludes": [],
        "name": "Virtual Machines",
        "description": "VM configuration and storage",
    },
    "plex": {
        "paths": ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"],
        "excludes": [
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
        ],
        "name": "Plex Media Server",
        "description": "Plex configuration and data",
    },
}

# Progress tracking settings
PROGRESS_WIDTH = 50
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
RETENTION_POLICY = "7d"  # Keep snapshots from last 7 days
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)

# Logging settings
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

#####################################
# UI and Progress Tracking Classes
#####################################


class NordColors:
    """Nord color theme for terminal output"""

    # Nord theme colors (https://www.nordtheme.com/)
    POLAR_NIGHT_1 = "\033[38;2;46;52;64m"  # Dark background
    POLAR_NIGHT_2 = "\033[38;2;59;66;82m"  # Darker gray
    SNOW_STORM_1 = "\033[38;2;216;222;233m"  # Light foreground
    SNOW_STORM_2 = "\033[38;2;229;233;240m"  # White
    FROST_1 = "\033[38;2;143;188;187m"  # Cyan/mint
    FROST_2 = "\033[38;2;136;192;208m"  # Light blue
    FROST_3 = "\033[38;2;129;161;193m"  # Blue
    FROST_4 = "\033[38;2;94;129;172m"  # Dark blue
    AURORA_1 = "\033[38;2;191;97;106m"  # Red
    AURORA_2 = "\033[38;2;208;135;112m"  # Orange
    AURORA_3 = "\033[38;2;235;203;139m"  # Yellow
    AURORA_4 = "\033[38;2;163;190;140m"  # Green
    AURORA_5 = "\033[38;2;180;142;173m"  # Purple

    # Standard formatting
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"

    # Convenience mappings to preserve backwards compatibility
    HEADER = AURORA_5 + BOLD  # Purple
    GREEN = AURORA_4  # Green
    YELLOW = AURORA_3  # Yellow
    RED = AURORA_1  # Red
    BLUE = FROST_3  # Blue

    # Background colors
    BG_POLAR_NIGHT_1 = "\033[48;2;46;52;64m"
    BG_SNOW_STORM_1 = "\033[48;2;216;222;233m"


class ProgressMode(Enum):
    """Progress bar modes for different situations"""

    DETERMINATE = 1  # We know the total size and can track progress
    INDETERMINATE = 2  # We don't know the size, use pulse animation
    HYBRID = 3  # Start indeterminate, switch to determinate when possible


class ProgressBar:
    """Enhanced thread-safe progress bar with multiple display modes"""

    def __init__(
        self,
        total: Optional[int] = None,
        desc: str = "",
        width: int = PROGRESS_WIDTH,
        mode: ProgressMode = ProgressMode.DETERMINATE,
    ):
        self.total = total if total is not None else 100
        self.desc = desc
        self.width = width
        self.mode = mode
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self._pulse_chars = "⣾⣽⣻⢿⡿⣟⣯⣷"  # Braille pattern for spinner
        self._pulse_idx = 0
        self._last_update_time = time.time()
        self._update_interval = 0.1  # Seconds between updates to avoid flickering

        # For rate calculation
        self._rate_window_size = 10  # Number of updates to use for average rate
        self._rate_window = []
        self._last_value = 0
        self._last_time = time.time()

    def update(self, amount: int = 1) -> None:
        """Update progress safely with the given amount"""
        with self._lock:
            if self.mode == ProgressMode.INDETERMINATE:
                self._pulse()
                return

            now = time.time()
            # Only update display if enough time has passed
            if now - self._last_update_time >= self._update_interval:
                self._last_update_time = now

                # Update rate calculation window
                if self._last_time != now:  # Avoid division by zero
                    rate = (amount) / (now - self._last_time)
                    self._rate_window.append(rate)
                    if len(self._rate_window) > self._rate_window_size:
                        self._rate_window.pop(0)
                self._last_time = now
                self._last_value = self.current

                # Update progress
                self.current = min(self.current + amount, self.total)
                self._display()

    def _pulse(self) -> None:
        """Update indeterminate progress animation"""
        now = time.time()
        if now - self._last_update_time >= self._update_interval:
            self._last_update_time = now
            self._pulse_idx = (self._pulse_idx + 1) % len(self._pulse_chars)

            # Increment current for ETA estimation in hybrid mode
            if self.mode == ProgressMode.HYBRID:
                self.current += CHUNK_SIZE

            self._display()

    def switch_to_determinate(self, total: int) -> None:
        """Switch from indeterminate to determinate mode with the given total"""
        with self._lock:
            self.mode = ProgressMode.DETERMINATE
            self.total = total
            self.current = 0
            self._display()

    def set_description(self, desc: str) -> None:
        """Update the description text"""
        with self._lock:
            self.desc = desc
            self._display()

    def _format_size(self, bytes_value: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} PB"

    def _format_time(self, seconds: float) -> str:
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

    def _get_current_rate(self) -> float:
        """Calculate current transfer rate based on sliding window"""
        if not self._rate_window:
            return 0
        return sum(self._rate_window) / len(self._rate_window)

    def _display(self) -> None:
        """Display progress bar with transfer rate and ETA"""
        elapsed = time.time() - self.start_time
        rate = self._get_current_rate()

        # Calculate the remaining time (ETA)
        if self.mode == ProgressMode.DETERMINATE:
            if rate > 0 and self.current < self.total:
                eta = (self.total - self.current) / rate
            else:
                eta = 0

            # Create the progress bar visual
            filled = int(self.width * self.current / self.total)
            bar = "█" * filled + "░" * (self.width - filled)
            percent = self.current / self.total * 100

            # Format the progress line
            progress_line = (
                f"\r{NordColors.BOLD}{self.desc}{NordColors.ENDC}: "
                f"{NordColors.FROST_3}|{bar}|{NordColors.ENDC} "
                f"{NordColors.SNOW_STORM_1}{percent:>5.1f}%{NordColors.ENDC} "
                f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
                f"[{NordColors.FROST_2}{self._format_size(rate)}/s{NordColors.ENDC}] "
                f"[ETA: {NordColors.AURORA_3}{self._format_time(eta)}{NordColors.ENDC}]"
            )
        else:
            # Indeterminate mode (spinner)
            spinner = self._pulse_chars[self._pulse_idx]
            if self.mode == ProgressMode.HYBRID:
                # In hybrid mode, show processed amount
                progress_line = (
                    f"\r{NordColors.BOLD}{self.desc}{NordColors.ENDC}: "
                    f"{NordColors.FROST_3}|{spinner}| "
                    f"{NordColors.SNOW_STORM_1}Processing...{NordColors.ENDC} "
                    f"({self._format_size(self.current)} so far) "
                    f"[{NordColors.FROST_2}{self._format_size(rate)}/s{NordColors.ENDC}] "
                    f"[Time: {NordColors.AURORA_3}{self._format_time(elapsed)}{NordColors.ENDC}]"
                )
            else:
                # Pure indeterminate mode
                progress_line = (
                    f"\r{NordColors.BOLD}{self.desc}{NordColors.ENDC}: "
                    f"{NordColors.FROST_3}|{spinner}| "
                    f"{NordColors.SNOW_STORM_1}Processing...{NordColors.ENDC} "
                    f"[Time: {NordColors.AURORA_3}{self._format_time(elapsed)}{NordColors.ENDC}]"
                )

        # Print the progress line and clear the rest of the line
        sys.stdout.write(
            progress_line
            + " "
            * (80 - len(progress_line.replace("\033[0m", "").replace("\033[1m", "")))
        )
        sys.stdout.flush()

        # Print newline if complete in determinate mode
        if self.mode == ProgressMode.DETERMINATE and self.current >= self.total:
            sys.stdout.write("\n")


#####################################
# Helper Functions
#####################################


def format_size(bytes_value: int) -> str:
    """Format bytes to human readable size"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} PB"


def print_header(message: str) -> None:
    """Print formatted header with Nord theme"""
    print(
        f"\n{NordColors.BG_POLAR_NIGHT_1}{NordColors.SNOW_STORM_1}{NordColors.BOLD}{'═' * 80}"
    )
    print(message.center(80))
    print(f"{'═' * 80}{NordColors.ENDC}\n")


def print_section(message: str) -> None:
    """Print formatted section header with Nord theme"""
    print(f"\n{NordColors.FROST_3}{NordColors.BOLD}▶ {message}{NordColors.ENDC}")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run command with enhanced error handling"""
    try:
        logging.debug(f"Running command: {' '.join(cmd)}")
        if capture_output:
            return subprocess.run(
                cmd, env=env, check=check, text=True, capture_output=True
            )
        else:
            # Run without capturing output (useful for long-running processes)
            return subprocess.run(cmd, env=env, check=check)
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {' '.join(cmd)}\nError: {e.stderr if hasattr(e, 'stderr') else str(e)}"
        logging.error(error_msg)
        print(f"{NordColors.RED}{error_msg}{NordColors.ENDC}")
        raise


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully with cleanup"""
    logging.warning("Backup interrupted by signal.")
    print(f"\n{NordColors.YELLOW}Backup interrupted. Cleaning up...{NordColors.ENDC}")
    # Perform any necessary cleanup here
    sys.exit(1)


def get_disk_usage(path: str = "/") -> Tuple[int, int, float]:
    """
    Get disk usage statistics with better error handling

    Args:
        path: The path to check

    Returns:
        Tuple[int, int, float]: (total_bytes, used_bytes, percent_used)
    """
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bfree * stat.f_frsize
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0

        return total, used, percent
    except Exception as e:
        logging.error(f"Failed to get disk usage for {path}: {e}")
        # Return reasonable defaults
        return 0, 0, 0


def check_service_status(service_name: str) -> Tuple[bool, str]:
    """
    Enhanced service status check with more details

    Args:
        service_name: Name of the service to check

    Returns:
        Tuple[bool, str]: (is_running, status_message)
    """
    try:
        # First check if service is active
        result = run_command(["systemctl", "is-active", service_name], check=False)
        is_running = result.returncode == 0
        status = result.stdout.strip()

        if is_running:
            # Get more details if running
            details = run_command(
                ["systemctl", "status", service_name, "--no-pager"], check=False
            )

            # Extract uptime and loaded info from status output
            uptime_match = re.search(
                r"Active: active \((.*?)\) since (.*?);", details.stdout
            )
            if uptime_match:
                active_state = uptime_match.group(1)
                since_time = uptime_match.group(2)
                return True, f"running ({active_state} since {since_time})"

            return True, "running"
        else:
            # Get more details about why it's not running
            details = run_command(
                ["systemctl", "status", service_name, "--no-pager"], check=False
            )

            # Try to extract the failure reason
            failed_match = re.search(r"Active: (.*?) \((.*?)\)", details.stdout)
            if failed_match:
                active_state = failed_match.group(1)
                reason = failed_match.group(2)
                return False, f"{status} ({active_state}: {reason})"

            return False, status
    except Exception as e:
        logging.error(f"Failed to check service status for {service_name}: {e}")
        return False, f"unknown (error: {str(e)})"


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """Check if script is run with root privileges"""
    if os.geteuid() != 0:
        msg = "This script must be run with root privileges."
        logging.error(msg)
        print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
        return False
    return True


def check_dependencies() -> bool:
    """Check if required tools are installed with version info"""
    if not shutil.which("restic"):
        msg = "Restic is not installed. Please install restic first."
        logging.error(msg)
        print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
        return False

    # Check restic version
    try:
        result = run_command(["restic", "version"])
        version = result.stdout.strip()
        logging.info(f"Using {version}")
        print(f"{NordColors.GREEN}✓ {version}{NordColors.ENDC}")
    except Exception as e:
        logging.warning(f"Could not determine restic version: {e}")

    return True


def check_environment() -> bool:
    """Check if required environment variables and configs are valid"""
    missing_vars = []

    if not B2_ACCOUNT_ID:
        missing_vars.append("B2_ACCOUNT_ID")
    if not B2_ACCOUNT_KEY:
        missing_vars.append("B2_ACCOUNT_KEY")
    if not RESTIC_PASSWORD:
        missing_vars.append("RESTIC_PASSWORD")

    if missing_vars:
        msg = f"The following configuration variables are not set: {', '.join(missing_vars)}"
        logging.error(msg)
        print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
        return False

    return True


def check_service_paths(service: str) -> bool:
    """
    Check if required paths for a service exist with enhanced error reporting

    Args:
        service: Service name to check paths for

    Returns:
        bool: True if all critical paths exist, False otherwise
    """
    config = BACKUP_CONFIGS[service]
    missing_paths = []

    if service == "system":
        # System backup always has valid root path
        return True

    elif service == "vm":
        paths_to_check = ["/etc/libvirt", "/var/lib/libvirt"]
        for path in paths_to_check:
            if not os.path.exists(path):
                missing_paths.append(path)

        if missing_paths:
            msg = f"VM directories not found: {', '.join(missing_paths)}. Is libvirt installed?"
            logging.error(msg)
            print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
            return False
        return True

    elif service == "plex":
        paths_to_check = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]
        for path in paths_to_check:
            if not os.path.exists(path):
                missing_paths.append(path)

        if missing_paths:
            msg = f"Plex Media Server paths not found: {', '.join(missing_paths)}"
            logging.error(msg)
            print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
            return False
        return True

    return False


def setup_logging() -> None:
    """Setup logging to both file and console"""
    try:
        # Create log directory if it doesn't exist
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
        )

        # Suppress excessive logging from some modules
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        logging.info(f"Logging initialized. Log file: {LOG_FILE}")
    except Exception as e:
        print(
            f"{NordColors.RED}Warning: Could not set up logging: {e}{NordColors.ENDC}"
        )
        # Fall back to basic logging
        logging.basicConfig(
            level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT
        )


#####################################
# Repository Management Functions
#####################################


def initialize_repository(service: str) -> bool:
    """
    Initialize repository for a service if not already initialized

    Args:
        service: Service name to initialize repository for

    Returns:
        bool: True if repository is initialized successfully, False otherwise
    """
    repo = REPOSITORIES[service]

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Check if repository exists
        try:
            logging.info(f"Checking if repository exists: {repo}")
            run_command(["restic", "--repo", repo, "snapshots"], env=env)
            print(f"{NordColors.GREEN}Repository already initialized.{NordColors.ENDC}")
            return True
        except subprocess.CalledProcessError:
            # Repository doesn't exist, initialize it
            logging.info(f"Repository not found. Initializing: {repo}")
            print(
                f"{NordColors.YELLOW}Repository not found. Initializing...{NordColors.ENDC}"
            )

            # Show a spinner while initializing
            progress = ProgressBar(
                desc="Initializing repository", mode=ProgressMode.INDETERMINATE
            )

            # Start initialization in a separate thread
            def init_repo():
                nonlocal env
                run_command(["restic", "--repo", repo, "init"], env=env)

            init_thread = threading.Thread(target=init_repo)
            init_thread.start()

            # Show progress while thread is running
            while init_thread.is_alive():
                progress.update()
                time.sleep(0.1)

            # Wait for thread to complete
            init_thread.join()

            print(
                f"{NordColors.GREEN}Repository initialized successfully.{NordColors.ENDC}"
            )
            logging.info(f"Repository initialized successfully: {repo}")
            return True

    except Exception as e:
        msg = f"Failed to initialize repository: {e}"
        logging.error(msg)
        print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
        return False


#####################################
# Size Estimation Functions
#####################################


def estimate_system_backup_size() -> int:
    """
    Improved system backup size estimation with better sampling

    Returns:
        int: Estimated backup size in bytes
    """
    print(
        f"{NordColors.FROST_3}Estimating system backup size (this may take a moment)...{NordColors.ENDC}"
    )

    # Show indeterminate progress while estimating
    progress = ProgressBar(desc="Scanning filesystem", mode=ProgressMode.INDETERMINATE)

    # Start a thread to do the actual estimation
    result = {"size": 0}

    def do_estimation():
        # Get total system disk usage
        total, used, percent = get_disk_usage("/")

        # Sample key directories to estimate what percentage will be backed up
        excluded_size = 0
        excludes = BACKUP_CONFIGS["system"]["excludes"]

        # More efficient sampling by checking larger excluded directories first
        for exclude in excludes:
            # Update progress
            progress.update()

            if "*" not in exclude:
                # This is a directory exclusion
                path = exclude.rstrip("/*")
                try:
                    if os.path.exists(path):
                        dir_size = 0
                        try:
                            # Use du command for faster size estimation
                            du_result = subprocess.run(
                                ["du", "-sb", path],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if du_result.returncode == 0:
                                dir_size = int(du_result.stdout.split()[0])
                            else:
                                # Fallback to Python's walk
                                dir_size = sum(
                                    os.path.getsize(os.path.join(dirpath, filename))
                                    for dirpath, _, filenames in os.walk(path)
                                    for filename in filenames
                                )
                        except (PermissionError, OSError):
                            pass
                        excluded_size += dir_size
                except (PermissionError, OSError):
                    pass

        # Estimate: Used space minus excluded size, with safety margin
        estimated_size = max(used - excluded_size, 0)

        # Apply a compression factor (restic uses compression)
        compression_factor = 0.7  # Assume 30% compression ratio
        estimated_backup_size = int(estimated_size * compression_factor)

        # If this is an incremental backup, estimate a smaller size
        try:
            env = os.environ.copy()
            env.update(
                {
                    "RESTIC_PASSWORD": RESTIC_PASSWORD,
                    "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                    "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
                }
            )

            # Check if previous snapshots exist
            snapshots_result = subprocess.run(
                ["restic", "--repo", REPOSITORIES["system"], "snapshots", "--json"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            if snapshots_result.returncode == 0 and snapshots_result.stdout.strip():
                # This is likely an incremental backup, so we'll be much smaller
                try:
                    snapshots = json.loads(snapshots_result.stdout)
                    if snapshots and len(snapshots) > 0:
                        # For incremental, estimate 5-10% of full backup size
                        estimated_backup_size = int(estimated_backup_size * 0.1)
                except (json.JSONDecodeError, KeyError):
                    pass
        except Exception:
            # If checking previous snapshots fails, stick with the original estimate
            pass

        result["size"] = estimated_backup_size

    # Run estimation in thread
    estimation_thread = threading.Thread(target=do_estimation)
    estimation_thread.start()

    # Show progress while estimating
    while estimation_thread.is_alive():
        progress.update()
        time.sleep(0.1)

    # Wait for thread to complete
    estimation_thread.join()

    # Return the estimated size
    return result["size"]


def calculate_directory_size(
    paths: List[str], excludes: List[str] = None
) -> Tuple[int, int]:
    """
    Improved directory size calculation with faster system tools when available

    Args:
        paths: List of paths to calculate size for
        excludes: List of exclude patterns

    Returns:
        Tuple[int, int]: (total_size_bytes, file_count)
    """
    print(f"{NordColors.FROST_3}Calculating directory sizes...{NordColors.ENDC}")

    # Use indeterminate progress while calculating
    progress = ProgressBar(desc="Scanning directories", mode=ProgressMode.INDETERMINATE)

    # Start a thread to do the actual calculation
    result = {"total_size": 0, "file_count": 0}

    def do_calculation():
        total_size = 0
        file_count = 0

        # Create a list of excluded path prefixes
        exclude_prefixes = []
        if excludes:
            exclude_prefixes = [
                exclude.rstrip("*") for exclude in excludes if "*" in exclude
            ]

        # Try to use system du command first for speed
        try:
            for path in paths:
                if not os.path.exists(path):
                    logging.warning(f"Path {path} does not exist, skipping.")
                    continue

                # Update progress
                progress.update()

                # First try with du command for faster scanning
                exclude_args = []
                for excl in exclude_prefixes:
                    if os.path.exists(excl.rstrip("/")):
                        exclude_args.extend(["--exclude", excl.rstrip("/")])

                try:
                    # Get total size with du
                    du_cmd = ["du", "-sb"]
                    du_cmd.extend(exclude_args)
                    du_cmd.append(path)

                    du_result = subprocess.run(
                        du_cmd, capture_output=True, text=True, check=False
                    )

                    if du_result.returncode == 0:
                        size = int(du_result.stdout.split()[0])
                        total_size += size

                        # Get file count with find
                        find_cmd = ["find", path, "-type", "f"]
                        for excl in exclude_prefixes:
                            find_cmd.extend(["-not", "-path", f"{excl.rstrip('/')}*"])
                        find_cmd.extend(
                            ["-not", "-path", "*/\\.*"]
                        )  # Exclude hidden files
                        find_cmd.append("-print")

                        # Pipe to wc to count lines
                        find_proc = subprocess.Popen(find_cmd, stdout=subprocess.PIPE)
                        wc_proc = subprocess.Popen(
                            ["wc", "-l"],
                            stdin=find_proc.stdout,
                            stdout=subprocess.PIPE,
                            text=True,
                        )
                        find_proc.stdout.close()
                        wc_output = wc_proc.communicate()[0].strip()

                        if wc_output and wc_output.isdigit():
                            file_count += int(wc_output)

                        continue  # Skip Python fallback
                except (subprocess.SubprocessError, ValueError):
                    pass  # Fall back to Python method

                # Fallback to Python method
                for root, dirs, files in os.walk(path):
                    # Update progress periodically
                    progress.update()

                    # Check if this directory should be excluded
                    skip = False
                    for exclude_prefix in exclude_prefixes:
                        if root.startswith(exclude_prefix):
                            skip = True
                            break

                    if skip:
                        continue

                    # Process files in this directory
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            # Check if file matches any exclude pattern
                            file_skip = False
                            if excludes:
                                for exclude in excludes:
                                    if "*." in exclude:
                                        ext = exclude.split("*.")[-1]
                                        if file.endswith(f".{ext}"):
                                            file_skip = True
                                            break

                            if file_skip:
                                continue

                            stat = os.stat(file_path)
                            total_size += stat.st_size
                            file_count += 1
                        except (FileNotFoundError, PermissionError, OSError):
                            pass
        except Exception as e:
            logging.error(f"Error calculating directory size: {e}")
            # Fall back to a reasonable estimate
            for path in paths:
                if os.path.exists(path):
                    try:
                        stat = os.stat(path)
                        total_size += stat.st_size
                        file_count += 1
                    except:
                        pass

        result["total_size"] = total_size
        result["file_count"] = file_count

    # Run calculation in thread
    calc_thread = threading.Thread(target=do_calculation)
    calc_thread.start()

    # Show progress while calculating
    while calc_thread.is_alive():
        progress.update()
        time.sleep(0.1)

    # Wait for thread to complete
    calc_thread.join()

    # Return the results
    return result["total_size"], result["file_count"]


#####################################
# Backup Execution Functions
#####################################


def perform_backup(service: str) -> bool:
    """
    Perform a backup for a specific service with improved progress tracking

    Args:
        service: Service name to backup

    Returns:
        bool: True if backup succeeded, False otherwise
    """
    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    print_header(f"Starting {config['name']} Backup")
    logging.info(f"Starting backup for {config['name']}")

    try:
        # Estimate backup size for progress tracking
        print_section("Calculating Backup Size")

        if service == "system":
            estimated_size = estimate_system_backup_size()
            file_count = 0  # We don't count files for system backup
            print(f"Estimated backup size: {format_size(estimated_size)}")
            logging.info(f"Estimated system backup size: {format_size(estimated_size)}")
        else:
            total_size, file_count = calculate_directory_size(
                config["paths"], config["excludes"]
            )
            estimated_size = total_size
            print(f"Found {file_count:,} files totaling {format_size(estimated_size)}")
            logging.info(
                f"Calculated size for {config['name']}: {format_size(estimated_size)} in {file_count:,} files"
            )

        if estimated_size == 0:
            msg = f"No files found to backup for {config['name']}."
            logging.warning(msg)
            print(f"{NordColors.YELLOW}Warning: {msg}{NordColors.ENDC}")
            return False

        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        print_section("Executing Backup")
        logging.info(f"Starting restic backup process for {config['name']}")

        # Start with a hybrid progress mode
        progress = ProgressBar(
            estimated_size, desc="Backup progress", mode=ProgressMode.HYBRID
        )

        # Construct backup command
        backup_cmd = ["restic", "--repo", repo, "backup"]

        # Add paths
        backup_cmd.extend(config["paths"])

        # Add excludes
        for exclude in config["excludes"]:
            backup_cmd.extend(["--exclude", exclude])

        # Add progress monitoring
        backup_cmd.append("--json")  # Get structured output
        backup_cmd.append("--verbose")  # And verbose status

        # Run backup command with progress tracking
        process = subprocess.Popen(
            backup_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Improved parsing of restic output for progress tracking
        file_count_pattern = re.compile(r"scan finished in .*?: (\d+) files")
        summary_pattern = re.compile(r"Added to the repository: ([\d.]+) ([KMG]iB)")
        processed_pattern = re.compile(r"processed (\d+) files")
        json_line_pattern = re.compile(r"^\s*{.*}\s*$")

        total_files = None
        processed_files = 0
        current_file = ""
        json_data = {}

        # Parse output to update progress
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Skip empty lines
            if not line.strip():
                continue

            # Try to parse JSON lines
            if json_line_pattern.match(line):
                try:
                    json_data = json.loads(line)
                    if "message_type" in json_data:
                        if json_data["message_type"] == "status":
                            # Update current file
                            if (
                                "current_files" in json_data
                                and json_data["current_files"]
                            ):
                                current_file = json_data["current_files"][0]
                                progress.set_description(f"Processing {current_file}")

                        elif json_data["message_type"] == "summary":
                            # End of backup stats
                            if "total_bytes_processed" in json_data:
                                total_processed = json_data["total_bytes_processed"]
                                # Update to final value
                                progress.current = total_processed
                                progress.total = total_processed
                                progress._display()

                except json.JSONDecodeError:
                    pass

            # Extract total file count if available
            file_count_match = file_count_pattern.search(line)
            if file_count_match and total_files is None:
                total_files = int(file_count_match.group(1))
                print(f"\rFound {total_files:,} files to backup")

            # Extract processed file count
            processed_match = processed_pattern.search(line)
            if processed_match:
                new_processed = int(processed_match.group(1))
                if new_processed > processed_files:
                    processed_files = new_processed
                    if total_files:
                        file_percent = (processed_files / total_files) * 100
                        print(
                            f"\rProcessed {processed_files:,}/{total_files:,} files ({file_percent:.1f}%)"
                        )

            # Extract summary data
            summary_match = summary_pattern.search(line)
            if summary_match:
                size_val = float(summary_match.group(1))
                size_unit = summary_match.group(2)

                # Convert to bytes
                multiplier = {
                    "B": 1,
                    "KiB": 1024,
                    "MiB": 1024**2,
                    "GiB": 1024**3,
                    "TiB": 1024**4,
                }.get(size_unit, 1)

                bytes_processed = int(size_val * multiplier)

                # Update progress with actual final size
                progress.mode = ProgressMode.DETERMINATE
                progress.total = bytes_processed
                progress.current = bytes_processed
                progress._display()

            # Print verbose output in a way that doesn't interfere with progress bar
            sys.stdout.write(f"\r{' ' * (PROGRESS_WIDTH + 60)}\r")
            print(line.strip())

            # Update progress based on processed files (this is approximate)
            if "added to the repository" in line:
                try:
                    # Extract bytes processed
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.endswith("B") and i > 0 and parts[i - 1].isdigit():
                            bytes_str = parts[i - 1] + part

                            # Convert to bytes for progress
                            for unit, multiplier in {
                                "B": 1,
                                "KiB": 1024,
                                "MiB": 1024**2,
                                "GiB": 1024**3,
                                "TiB": 1024**4,
                            }.items():
                                if unit in bytes_str:
                                    size = float(bytes_str.replace(unit, "").strip())
                                    bytes_processed = int(size * multiplier)
                                    progress.update(bytes_processed)
                                    break
                except Exception:
                    # If parsing fails, just update with a small increment
                    progress.update(CHUNK_SIZE)

            # Ensure progress bar is redrawn
            progress._display()

        # Wait for process to complete
        process.wait()

        # Check if backup was successful
        if process.returncode != 0:
            msg = f"Backup failed with return code {process.returncode}."
            logging.error(msg)
            print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
            return False

        success_msg = f"{config['name']} backup completed successfully."
        logging.info(success_msg)
        print(f"{NordColors.GREEN}{success_msg}{NordColors.ENDC}")
        return True

    except Exception as e:
        msg = f"Backup failed: {str(e)}"
        logging.error(msg, exc_info=True)
        print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
        return False


def perform_retention(service: str) -> bool:
    """
    Apply retention policy to keep the repository size manageable

    Args:
        service: Service name to apply retention policy for

    Returns:
        bool: True if retention succeeded, False otherwise
    """
    repo = REPOSITORIES[service]
    config = BACKUP_CONFIGS[service]

    print_section("Applying Retention Policy")
    logging.info(f"Applying retention policy for {config['name']}")

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Show what we're about to do
        print(f"Applying retention policy: keeping snapshots within {RETENTION_POLICY}")

        # Start progress indicator
        progress = ProgressBar(
            desc="Pruning old snapshots", mode=ProgressMode.INDETERMINATE
        )

        # Construct retention command
        retention_cmd = [
            "restic",
            "--repo",
            repo,
            "forget",
            "--prune",
            "--keep-within",
            RETENTION_POLICY,  # Keep snapshots from last 7 days
        ]

        # Run retention in a separate thread with progress indicator
        result = {"success": False, "output": ""}

        def run_retention():
            try:
                retention_result = run_command(retention_cmd, env=env)
                result["success"] = True
                result["output"] = retention_result.stdout
            except Exception as e:
                result["success"] = False
                result["output"] = str(e)

        retention_thread = threading.Thread(target=run_retention)
        retention_thread.start()

        # Show progress while thread is running
        while retention_thread.is_alive():
            progress.update()
            time.sleep(0.1)

        # Wait for thread to complete
        retention_thread.join()

        if result["success"]:
            logging.info("Retention policy applied successfully")
            print(
                f"{NordColors.GREEN}Retention policy applied successfully.{NordColors.ENDC}"
            )

            # Parse and display retention results
            removed_snapshots = 0
            removed_data = "0 B"

            for line in result["output"].splitlines():
                if "snapshots have been removed" in line:
                    match = re.search(r"(\d+) snapshots have been removed", line)
                    if match:
                        removed_snapshots = int(match.group(1))
                elif "Deleted data:" in line:
                    match = re.search(r"Deleted data: ([\d.]+ [KMGT]?B)", line)
                    if match:
                        removed_data = match.group(1)

            if removed_snapshots > 0:
                print(f"  • Removed {removed_snapshots} old snapshots")
                print(f"  • Freed up {removed_data} of storage")
            else:
                print(f"  • No snapshots needed to be removed")

            return True
        else:
            msg = f"Failed to apply retention policy: {result['output']}"
            logging.error(msg)
            print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
            return False

    except Exception as e:
        msg = f"Failed to apply retention policy: {str(e)}"
        logging.error(msg, exc_info=True)
        print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
        return False


def list_snapshots(service: str) -> bool:
    """
    List all snapshots in the repository for a service with enhanced formatting

    Args:
        service: Service name to list snapshots for

    Returns:
        bool: True if listing succeeded, False otherwise
    """
    repo = REPOSITORIES[service]
    config = BACKUP_CONFIGS[service]

    print_section("Listing Snapshots")
    logging.info(f"Listing snapshots for {config['name']}")

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Run snapshots command with JSON output for better parsing
        try:
            result = run_command(
                ["restic", "--repo", repo, "snapshots", "--json"], env=env
            )
            snapshots_json = json.loads(result.stdout)

            if snapshots_json:
                # Sort by time, newest first
                snapshots_json.sort(key=lambda x: x.get("time", ""), reverse=True)

                # Print header
                print(
                    f"\n{NordColors.FROST_2}{NordColors.BOLD}{'ID':<10} {'Date':<20} {'Tags':<15} {'Size':<10}{NordColors.ENDC}"
                )
                print("-" * 60)

                # Print each snapshot with formatting
                for snapshot in snapshots_json:
                    # Format ID as short ID
                    short_id = snapshot.get("short_id", "unknown")

                    # Format time
                    time_str = snapshot.get("time", "")
                    if time_str:
                        try:
                            # Parse and format the time
                            timestamp = datetime.fromisoformat(
                                time_str.replace("Z", "+00:00")
                            )
                            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            pass

                    # Get tags and paths
                    tags = snapshot.get("tags", [])
                    tags_str = ", ".join(tags) if tags else "-"

                    # Get size if available
                    size_str = snapshot.get("stats", {}).get(
                        "total_size_formatted", "-"
                    )

                    # Print line
                    print(
                        f"{short_id:<10} {time_str:<20} {tags_str:<15} {size_str:<10}"
                    )

                # Print summary
                print("-" * 60)
                print(f"Total: {len(snapshots_json)} snapshots")
            else:
                print(
                    f"{NordColors.YELLOW}No snapshots found in the repository.{NordColors.ENDC}"
                )
        except (json.JSONDecodeError, subprocess.CalledProcessError):
            # Fall back to standard output if JSON parsing fails
            result = run_command(["restic", "--repo", repo, "snapshots"], env=env)
            if result.stdout.strip():
                print(result.stdout)
            else:
                print(
                    f"{NordColors.YELLOW}No snapshots found in the repository.{NordColors.ENDC}"
                )

        return True

    except Exception as e:
        msg = f"Failed to list snapshots: {str(e)}"
        logging.error(msg)
        print(f"{NordColors.RED}{msg}{NordColors.ENDC}")
        return False


#####################################
# Service-Specific Functions
#####################################


def backup_service(service: str) -> bool:
    """
    Execute the full backup workflow for a specific service

    Args:
        service: Service name to backup

    Returns:
        bool: True if all steps succeeded, False otherwise
    """
    if service not in BACKUP_CONFIGS:
        msg = f"Unknown service '{service}'."
        logging.error(msg)
        print(f"{NordColors.RED}Error: {msg}{NordColors.ENDC}")
        return False

    config = BACKUP_CONFIGS[service]
    logging.info(f"Starting backup workflow for {config['name']}")

    print_header(f"Processing {config['name']} Backup")
    print(f"{NordColors.FROST_2}Description:{NordColors.ENDC} {config['description']}")
    print(f"{NordColors.FROST_2}Repository:{NordColors.ENDC} {REPOSITORIES[service]}")
    print(f"{NordColors.FROST_2}Paths:{NordColors.ENDC} {', '.join(config['paths'])}")
    print(
        f"{NordColors.FROST_2}Excludes:{NordColors.ENDC} {len(config['excludes'])} patterns"
    )

    # Check service-specific dependencies
    if not check_service_paths(service):
        return False

    # Check service status if applicable
    if service == "vm":
        vm_status, status_text = check_service_status("libvirtd")
        print(
            f"{NordColors.FROST_2}libvirtd Service Status:{NordColors.ENDC} {status_text}"
        )
        logging.info(f"libvirtd status: {status_text}")
    elif service == "plex":
        plex_status, status_text = check_service_status("plexmediaserver")
        print(
            f"{NordColors.FROST_2}Plex Service Status:{NordColors.ENDC} {status_text}"
        )
        logging.info(f"plexmediaserver status: {status_text}")

    # Initialize repository
    if not initialize_repository(service):
        return False

    # Get start time for this service
    service_start_time = time.time()

    # Perform backup
    backup_success = perform_backup(service)
    if not backup_success:
        return False

    # Apply retention policy
    retention_success = perform_retention(service)
    if not retention_success:
        logging.warning("Failed to apply retention policy, but backup was successful.")
        print(
            f"{NordColors.YELLOW}Warning: Failed to apply retention policy, but backup was successful.{NordColors.ENDC}"
        )

    # List snapshots
    list_snapshots(service)

    # Calculate and show elapsed time for this service
    service_elapsed = time.time() - service_start_time
    hours, remainder = divmod(service_elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)

    print_section("Service Backup Summary")
    print(f"{NordColors.GREEN}✓ {config['name']} backup completed{NordColors.ENDC}")
    print(f"Elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")

    return True


def backup_all_services() -> Dict[str, bool]:
    """
    Backup all configured services with better progress reporting

    Returns:
        Dict[str, bool]: Results of each service backup
    """
    results = {}
    total_services = len(BACKUP_CONFIGS)
    current_service = 0

    print_header("Starting Backup of All Services")
    logging.info(f"Starting backup of all {total_services} configured services")

    all_start_time = time.time()

    for service in BACKUP_CONFIGS:
        current_service += 1
        service_name = BACKUP_CONFIGS[service]["name"]

        print_header(
            f"--- Service {current_service}/{total_services}: {service_name} ---"
        )

        # Backup the service
        service_start_time = time.time()
        results[service] = backup_service(service)
        service_elapsed = time.time() - service_start_time

        # Log the result
        if results[service]:
            logging.info(
                f"Successfully backed up {service_name} in {service_elapsed:.1f} seconds"
            )
        else:
            logging.error(
                f"Failed to back up {service_name} after {service_elapsed:.1f} seconds"
            )

    # Calculate total elapsed time
    all_elapsed = time.time() - all_start_time

    return results


#####################################
# Main Function
#####################################


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Unified Restic Backup Script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--service",
        choices=list(BACKUP_CONFIGS.keys()) + ["all"],
        help="Service to backup (system, vm, plex, or all)",
    )

    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode (requires --service)",
    )

    parser.add_argument(
        "--retention",
        default=RETENTION_POLICY,
        help="Retention policy for snapshots (e.g., 7d, 30d, 1y)",
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    return parser.parse_args()


def main() -> None:
    """Main execution function with improved CLI interface"""
    # Parse arguments
    args = parse_arguments()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Setup logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    setup_logging()

    # Update retention policy if provided
    global RETENTION_POLICY
    if args.retention:
        RETENTION_POLICY = args.retention
        logging.info(f"Using custom retention policy: {RETENTION_POLICY}")

    # Check root privileges
    if not check_root_privileges():
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check environment
    if not check_environment():
        sys.exit(1)

    print_header("Unified Restic Backup Script")
    print(f"{NordColors.FROST_2}Hostname:{NordColors.ENDC} {HOSTNAME}")
    print(f"{NordColors.FROST_2}Platform:{NordColors.ENDC} {platform.platform()}")
    print(f"{NordColors.FROST_2}Backup bucket:{NordColors.ENDC} {B2_BUCKET}")
    print(f"{NordColors.FROST_2}Retention policy:{NordColors.ENDC} {RETENTION_POLICY}")
    print(
        f"{NordColors.FROST_2}Available services:{NordColors.ENDC} {', '.join(BACKUP_CONFIGS.keys())}"
    )

    # Log start of backup process
    logging.info(
        f"Starting backup script on {HOSTNAME} with retention policy {RETENTION_POLICY}"
    )

    # Non-interactive mode with specified service
    if args.non_interactive and args.service:
        logging.info(f"Running in non-interactive mode for service: {args.service}")
        start_time = time.time()

        try:
            if args.service == "all":
                results = backup_all_services()
                success = all(results.values())
            else:
                success = backup_service(args.service)

            if not success:
                logging.error(f"Backup failed for {args.service}")
                sys.exit(1)

        except Exception as e:
            logging.error(f"Backup failed with exception: {e}", exc_info=True)
            print(f"\n{NordColors.RED}Backup failed: {e}{NordColors.ENDC}")
            sys.exit(1)

    # Interactive mode
    else:
        # Prompt for service selection
        print(f"\nSelect service to backup:")
        services = list(BACKUP_CONFIGS.keys())
        for i, service in enumerate(services, 1):
            config = BACKUP_CONFIGS[service]
            print(f"{i}. {config['name']} - {config['description']}")
        print(f"{len(services) + 1}. All Services")

        try:
            choice = input(
                f"\n{NordColors.FROST_3}Enter your choice (1-{len(services) + 1}): {NordColors.ENDC}"
            )
            choice = int(choice.strip())

            if choice < 1 or choice > len(services) + 1:
                print(f"{NordColors.RED}Invalid choice. Exiting.{NordColors.ENDC}")
                sys.exit(1)

            start_time = time.time()

            if choice <= len(services):
                # Single service backup
                service = services[choice - 1]
                success = backup_service(service)

                if not success:
                    print(
                        f"{NordColors.RED}Backup of {BACKUP_CONFIGS[service]['name']} failed.{NordColors.ENDC}"
                    )
                    sys.exit(1)
            else:
                # All services
                results = backup_all_services()

                # Check for failures
                failures = [
                    service for service, success in results.items() if not success
                ]

                if failures:
                    print_header("Backup Summary - FAILURES DETECTED")
                    print(
                        f"{NordColors.RED}The following services failed to backup:{NordColors.ENDC}"
                    )
                    for service in failures:
                        print(f"  • {BACKUP_CONFIGS[service]['name']}")
                    sys.exit(1)

        except KeyboardInterrupt:
            print(f"\n{NordColors.YELLOW}Backup interrupted by user{NordColors.ENDC}")
            logging.warning("Backup interrupted by user")
            sys.exit(130)
        except ValueError:
            print(
                f"{NordColors.RED}Invalid input. Please enter a number.{NordColors.ENDC}"
            )
            sys.exit(1)
        except Exception as e:
            print(f"\n{NordColors.RED}Backup failed: {e}{NordColors.ENDC}")
            logging.error(f"Backup failed with exception: {e}", exc_info=True)
            sys.exit(1)

    # Calculate elapsed time
    end_time = time.time()
    elapsed = end_time - start_time
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Print final summary
    print_header("Backup Summary")
    print(f"{NordColors.GREEN}Backup completed successfully.{NordColors.ENDC}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    print(f"Log file: {LOG_FILE}")

    # Log completion
    logging.info(
        f"Backup completed successfully in {int(hours)}h {int(minutes)}m {int(seconds)}s"
    )


if __name__ == "__main__":
    main()
