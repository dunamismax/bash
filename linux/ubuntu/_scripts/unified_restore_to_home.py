#!/usr/bin/env python3
"""
Comprehensive Unified Restore Script (to Home directory)
--------------------------------------
Description:
  A robust unified restore solution that retrieves the latest snapshots from three restic
  repositories stored on Backblaze B2 and restores them locally. The three repositories
  are:
    1. System Backup - Contains a full system backup.
    2. VM Backup - Contains libvirt virtual machine configurations and disk images.
    3. Plex Backup - Contains Plex Media Server configuration and application data.

  All backups are restored into subdirectories under the folder:
      /home/sawyer/restic_backup_restore_data
  The script uses the rich library for progress indicators, detailed Nord-themed logging,
  strict error handling, and graceful signal handling.

Features:
  - Automatic repository detection and validation
  - Enhanced progress visualization with rich indicators
  - Detailed restore statistics and reporting
  - Robust error handling with automatic retries for transient failures
  - Verification of restore integrity
  - Nord-themed logging output

Usage:
  sudo ./unified_restore_to_home.py

Author: Your Name | License: MIT | Version: 2.0.0
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.panel import Panel
from rich.table import Table

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"

HOSTNAME = socket.gethostname()

# Restic repository strings for Backblaze B2
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

RESTIC_PASSWORD = "12345678"

# Restore target base directory
RESTORE_BASE_DIR = "/home/sawyer/restic_backup_restore_data"

# Maximum retries and delay (for restic operations)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds

# Number of parallel verify threads
VERIFY_THREADS = 4

# Global restore status for reporting
RESTORE_STATUS = {
    "system": {"status": "pending", "message": "", "stats": {}},
    "vm": {"status": "pending", "message": "", "stats": {}},
    "plex": {"status": "pending", "message": "", "stats": {}},
}

# Destination directories for each backup type
RESTORE_DIRS = {
    "system": str(Path(RESTORE_BASE_DIR) / "system"),
    "vm": str(Path(RESTORE_BASE_DIR) / "vm"),
    "plex": str(Path(RESTORE_BASE_DIR) / "plex"),
}

# Logging configuration
LOG_FILE = "/var/log/unified_restore.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# Rich console instance
console = Console(highlight=False)

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom log formatter that applies Nord theme colors to different log levels.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Configure logging with Nord-themed formatting for console and file output.
    Handles log rotation for files over 10MB.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with Nord colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler with log rotation
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logging.warning("Continuing with console logging only")

    return logger


def print_section(title: str):
    """
    Print a nicely formatted section header with Nord theme colors.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------------------
def format_size(size_bytes):
    """
    Format a byte size into a human-readable string (B, KB, MB, GB, TB).
    """
    if size_bytes is None or size_bytes == 0:
        return "0 B"

    size_bytes = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0

    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1

    return f"{size_bytes:.2f} {units[unit_index]}"


def format_duration(seconds):
    """
    Format seconds into a human-readable duration string.
    """
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"


def get_dir_size(path):
    """
    Calculate the total size of a directory and its contents.
    """
    total_size = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if not os.path.islink(file_path):
                    total_size += os.path.getsize(file_path)
        return total_size
    except Exception as e:
        logging.warning(f"Error calculating directory size: {e}")
        return 0


# ------------------------------------------------------------------------------
# Rich Progress Helper
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a rich progress spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


def run_with_progress_bar(description: str, func, total: int, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a rich progress bar.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=total)

            # Monitor progress
            while not future.done():
                if "progress_callback" in kwargs:
                    current = kwargs["progress_callback"]()
                    progress.update(task, completed=min(current, total))
                time.sleep(0.5)
                progress.refresh()

            return future.result()


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle system signals gracefully, cleaning up before exit.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exiting the script.
    """
    logging.info("Performing cleanup tasks before exit.")
    if any(item["status"] != "pending" for item in RESTORE_STATUS.values()):
        print_status_report()


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency and Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Check if required dependencies are installed and working correctly.
    """
    dependencies = ["restic"]
    missing = [dep for dep in dependencies if not shutil.which(dep)]
    if missing:
        logging.error(f"Missing required dependencies: {', '.join(missing)}")
        sys.exit(1)
    try:
        result = subprocess.run(
            ["restic", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        logging.info(f"Using {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not determine restic version: {e}")


def check_root():
    """
    Verify the script is running with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


def check_restore_dirs():
    """
    Verify and create restore target directories if needed.
    """
    for name, path in RESTORE_DIRS.items():
        target_dir = Path(path)
        try:
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                logging.info(f"Created restore directory: {target_dir}")
            else:
                logging.info(f"Restore directory already exists: {target_dir}")

                # Check if directory is empty
                if any(target_dir.iterdir()):
                    logging.warning(
                        f"Restore directory '{target_dir}' is not empty. Existing files may be overwritten."
                    )
        except Exception as e:
            logging.error(f"Failed to create/check restore directory {target_dir}: {e}")
            sys.exit(1)


# ------------------------------------------------------------------------------
# Restic Repository Operations
# ------------------------------------------------------------------------------
def run_restic(
    repo: str,
    password: str,
    *args,
    check=True,
    capture_output=False,
    max_retries=MAX_RETRIES,
):
    """
    Run restic command with automatic retries for transient errors.

    Args:
        repo: Repository URL
        password: Repository password
        *args: Command line arguments for restic
        check: Whether to check return code
        capture_output: Whether to capture and return command output
        max_retries: Maximum number of retry attempts

    Returns:
        CompletedProcess object if capture_output=True, None otherwise
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)

    # Mask credentials when logging
    log_cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(log_cmd)}")

    retries = 0
    last_error = None

    while retries <= max_retries:
        try:
            if capture_output:
                result = subprocess.run(
                    cmd,
                    check=check,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                return result
            else:
                subprocess.run(cmd, check=check, env=env)
                return None
        except subprocess.CalledProcessError as e:
            last_error = e
            err_msg = e.stderr or str(e)

            # Check for transient errors that are candidates for retry
            transient = any(
                term in err_msg.lower()
                for term in [
                    "connection reset by peer",
                    "unexpected eof",
                    "timeout",
                    "connection refused",
                    "network error",
                    "429 too many requests",
                    "500 internal server error",
                    "503 service unavailable",
                    "temporarily unavailable",
                ]
            )

            # Handle special case for init command
            if "init" in args and "already initialized" in err_msg:
                logging.info("Repository already initialized, continuing.")
                return None

            # Handle retries for transient errors
            if transient and retries < max_retries:
                retries += 1
                delay = RETRY_DELAY_BASE * (2 ** (retries - 1))
                logging.warning(
                    f"Transient error detected, retrying in {delay} seconds ({retries}/{max_retries})..."
                )
                time.sleep(delay)
                continue
            else:
                if retries > 0:
                    logging.error(f"Command failed after {retries} retries.")
                raise e

    if last_error:
        raise last_error


def is_repo_initialized(repo: str, password: str) -> bool:
    """
    Check if a restic repository is initialized and accessible.

    Args:
        repo: Repository URL
        password: Repository password

    Returns:
        bool: True if repository is initialized, False otherwise
    """
    logging.info(f"Checking repository '{repo}'...")
    try:
        run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )
        logging.info(f"Repository '{repo}' is initialized and accessible.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if any(
            msg in err_msg for msg in ["already initialized", "repository master key"]
        ):
            logging.info(f"Repository '{repo}' is initialized but had access issues.")
            return True
        logging.info(f"Repository '{repo}' is not initialized or not accessible.")
        return False


def force_unlock_repo(repo: str, password: str) -> bool:
    """
    Force unlock a restic repository to remove stale locks.

    Args:
        repo: Repository URL
        password: Repository password

    Returns:
        bool: True if unlock succeeded or was unnecessary, False otherwise
    """
    logging.warning(f"Forcing unlock of repository '{repo}'")
    try:
        if not is_repo_initialized(repo, password):
            logging.warning(f"Repo '{repo}' is not initialized; cannot unlock.")
            return False
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if "no locks to remove" in err_msg:
            logging.info("Repository was already unlocked.")
            return True
        logging.error(f"Failed to unlock repository: {err_msg}")
        return False


def get_snapshot_list(repo: str, password: str):
    """
    Get a list of all snapshots in a repository.

    Args:
        repo: Repository URL
        password: Repository password

    Returns:
        list: List of snapshot objects or empty list on failure
    """
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []
        return snapshots
    except Exception as e:
        logging.error(f"Error retrieving snapshots from '{repo}': {e}")
        return []


def get_latest_snapshot_id(repo: str, password: str) -> str:
    """
    Retrieve the most recent snapshot ID from the repository.

    Args:
        repo: Repository URL
        password: Repository password

    Returns:
        str: Snapshot ID or empty string if no snapshots or error
    """
    snapshots = get_snapshot_list(repo, password)

    if not snapshots:
        logging.error(f"No snapshots found in repository '{repo}'.")
        return ""

    # Sort snapshots by time (newest first)
    latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
    snapshot_id = latest.get("short_id") or latest.get("id", "")
    snapshot_time = latest.get("time", "")[:19]  # Truncate to remove microseconds/TZ

    logging.info(
        f"Latest snapshot for '{repo}' is '{snapshot_id}' from {snapshot_time}."
    )
    return snapshot_id


def get_repo_stats(repo: str, password: str):
    """
    Get repository statistics including total size and snapshot count.

    Args:
        repo: Repository URL
        password: Repository password

    Returns:
        dict: Statistics dictionary with keys for total_size, snapshots, latest_snapshot
    """
    stats = {
        "total_size": "unknown",
        "snapshots": 0,
        "latest_snapshot": "never",
        "snapshot_id": "",
    }

    # Check if repository is initialized
    if not is_repo_initialized(repo, password):
        return stats

    try:
        # Get snapshot information
        snapshots = get_snapshot_list(repo, password)
        stats["snapshots"] = len(snapshots)

        if snapshots:
            latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
            stats["latest_snapshot"] = latest.get("time", "unknown")[:19]
            stats["snapshot_id"] = latest.get("short_id") or latest.get("id", "")

        # Get repository size information
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        repo_stats = json.loads(result.stdout) if result and result.stdout else {}
        total = repo_stats.get("total_size", 0)
        stats["total_size"] = format_size(total)

        return stats
    except Exception as e:
        logging.warning(f"Could not get complete repository statistics: {e}")
        return stats


# ------------------------------------------------------------------------------
# Restore Operations (with Rich Progress)
# ------------------------------------------------------------------------------
def restore_repo(repo: str, password: str, restore_target: str, task_name: str) -> bool:
    """
    Restore the latest snapshot from a repository to a target directory.
    Updates global RESTORE_STATUS with progress and results.

    Args:
        repo: Repository URL
        password: Repository password
        restore_target: Target directory for restore
        task_name: Task identifier for status tracking

    Returns:
        bool: True if restore succeeded, False otherwise
    """
    # Update status to in-progress
    RESTORE_STATUS[task_name] = {
        "status": "in_progress",
        "message": "Restore in progress...",
        "stats": {},
    }

    # Get latest snapshot ID
    snapshot_id = get_latest_snapshot_id(repo, password)
    if not snapshot_id:
        msg = f"No snapshots found for repository '{repo}'."
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "stats": {"error": "No snapshots found"},
        }
        return False

    # Ensure target directory exists
    target_path = Path(restore_target)
    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        msg = f"Failed to create target directory '{restore_target}': {e}"
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "stats": {"error": f"Directory creation failed: {e}"},
        }
        return False

    # Prepare restore command
    cmd_args = ["restore", snapshot_id, "--target", restore_target]

    # Start timing
    start = time.time()

    # Perform restore with progress spinner
    try:
        result = run_with_progress(
            f"Restoring backup to {restore_target}...",
            run_restic,
            repo,
            password,
            *cmd_args,
            capture_output=True,
        )

        # Calculate timing
        elapsed = time.time() - start

        # Extract statistics from restore output
        stats = extract_restore_stats(result.stdout if result else "", restore_target)
        stats["duration"] = format_duration(elapsed)
        stats["snapshot_id"] = snapshot_id

        # Update status
        msg = f"Restore completed in {elapsed:.1f} seconds."
        logging.info(msg)
        RESTORE_STATUS[task_name] = {
            "status": "success",
            "message": msg,
            "stats": stats,
        }

        # Log detailed output
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(
                    kw in line.lower()
                    for kw in ["files restored", "processed", "added to", "snapshot"]
                ):
                    logging.info(f"Restore output: {line.strip()}")

        # Try to verify the restore
        verification_results = verify_restore(restore_target, start_time=start)
        RESTORE_STATUS[task_name]["stats"].update(verification_results)

        return True

    except subprocess.CalledProcessError as e:
        # Handle failures
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"

        # Check for repository lock issues
        if "repository is already locked" in err_output:
            logging.warning(
                "Restore failed due to lock. Retrying after force unlock..."
            )

            # Try to force unlock and retry
            if force_unlock_repo(repo, password):
                try:
                    result = run_with_progress(
                        f"Retrying restore to {restore_target}...",
                        run_restic,
                        repo,
                        password,
                        *cmd_args,
                        capture_output=True,
                    )

                    # Success after retry
                    total = time.time() - start
                    msg = f"Restore completed after retry in {total:.1f} seconds."
                    logging.info(msg)

                    # Get stats after successful retry
                    stats = extract_restore_stats(
                        result.stdout if result else "", restore_target
                    )
                    stats["duration"] = format_duration(total)
                    stats["snapshot_id"] = snapshot_id
                    stats["needed_retry"] = True

                    RESTORE_STATUS[task_name] = {
                        "status": "success",
                        "message": msg,
                        "stats": stats,
                    }

                    # Try to verify the restore
                    verification_results = verify_restore(
                        restore_target, start_time=start
                    )
                    RESTORE_STATUS[task_name]["stats"].update(verification_results)

                    return True

                except Exception as retry_e:
                    # Failed even after unlock and retry
                    msg = f"Restore failed after retry: {retry_e}"
                    logging.error(msg)
                    RESTORE_STATUS[task_name] = {
                        "status": "failed",
                        "message": msg,
                        "stats": {
                            "error": str(retry_e),
                            "duration": format_duration(time.time() - start),
                        },
                    }
                    return False
            else:
                # Could not unlock repository
                msg = f"Failed to unlock repo after {elapsed:.1f} seconds."
                logging.error(msg)
                RESTORE_STATUS[task_name] = {
                    "status": "failed",
                    "message": msg,
                    "stats": {"error": "Repository unlock failed"},
                }
                return False
        else:
            # General failure not related to locks
            msg = f"Restore failed after {elapsed:.1f} seconds: {err_output}"
            logging.error(msg)
            RESTORE_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "stats": {"error": err_output, "duration": format_duration(elapsed)},
            }
            return False


def extract_restore_stats(output_text, restore_path):
    """
    Extract statistics from restic restore output.

    Args:
        output_text: Command output from restic restore
        restore_path: Path where files were restored

    Returns:
        dict: Statistics extracted from the output
    """
    stats = {
        "files_restored": 0,
        "total_size": "0 B",
        "restore_size_bytes": 0,
    }

    # Try to parse files restored count from output
    files_match = re.search(r"(\d+)\s+files\s+restored", output_text, re.IGNORECASE)
    if files_match:
        stats["files_restored"] = int(files_match.group(1))

    # Calculate restored data size
    try:
        size_bytes = get_dir_size(restore_path)
        stats["restore_size_bytes"] = size_bytes
        stats["total_size"] = format_size(size_bytes)
    except Exception as e:
        logging.warning(f"Could not calculate restored data size: {e}")

    return stats


def verify_restore(restore_path, start_time=None):
    """
    Verify the integrity of restored files.

    Args:
        restore_path: Path where files were restored
        start_time: Optional timestamp for timing calculations

    Returns:
        dict: Verification statistics
    """
    verification = {
        "verified": True,
        "verification_note": "Basic verification passed",
    }

    # Start timing if not provided
    if start_time is None:
        start_time = time.time()

    try:
        # Check if the directory exists and is accessible
        restore_dir = Path(restore_path)
        if not restore_dir.exists():
            verification["verified"] = False
            verification["verification_note"] = "Restore directory does not exist"
            return verification

        # Count files and directories
        file_count = 0
        dir_count = 0
        empty_dirs = 0

        for dirpath, dirnames, filenames in os.walk(restore_path):
            dir_count += len(dirnames)
            file_count += len(filenames)

            # Detect empty directories
            if not dirnames and not filenames and dirpath != restore_path:
                empty_dirs += 1

        verification["file_count"] = file_count
        verification["directory_count"] = dir_count
        verification["empty_directories"] = empty_dirs

        # Warn if no files found
        if file_count == 0:
            verification["verified"] = False
            verification["verification_note"] = "No files found in restore directory"

        # Calculate verification time
        verification["verification_duration"] = format_duration(
            time.time() - start_time
        )

        return verification
    except Exception as e:
        logging.error(f"Error during restore verification: {e}")
        verification["verified"] = False
        verification["verification_note"] = f"Verification error: {str(e)}"
        return verification


# ------------------------------------------------------------------------------
# Status Reporting
# ------------------------------------------------------------------------------
def print_repository_info():
    """
    Display information about all repositories before restore.
    """
    print_section("Repository Information")

    repos = [("System", B2_REPO_SYSTEM), ("VM", B2_REPO_VM), ("Plex", B2_REPO_PLEX)]

    repo_table = Table(title="Available Backup Repositories")
    repo_table.add_column("Repository", style="cyan")
    repo_table.add_column("Snapshots", justify="right", style="green")
    repo_table.add_column("Total Size", justify="right")
    repo_table.add_column("Latest Snapshot", style="magenta")
    repo_table.add_column("Status", style="yellow")

    all_initialized = True

    for name, repo in repos:
        try:
            stats = get_repo_stats(repo, RESTIC_PASSWORD)
            status = "Available" if stats["snapshots"] > 0 else "Empty"

            # Add to table
            repo_table.add_row(
                name,
                str(stats["snapshots"]),
                stats["total_size"],
                stats["latest_snapshot"],
                status,
            )

            # Log additional details
            if stats["snapshots"] > 0:
                logging.info(f"{name} Repository: {repo}")
                logging.info(f"  • Snapshots: {stats['snapshots']}")
                logging.info(f"  • Size: {stats['total_size']}")
                logging.info(f"  • Latest snapshot: {stats['latest_snapshot']}")
            else:
                logging.info(f"{name} Repository: {repo} - No snapshots found")
                all_initialized = False

        except Exception as e:
            repo_table.add_row(name, "Error", "Unknown", "Unknown", f"Error: {str(e)}")
            logging.warning(f"Could not get info for {name} repo: {e}")
            all_initialized = False

    # Print the table
    if not DISABLE_COLORS:
        console.print(repo_table)

    # Check if all repositories are ready
    if not all_initialized:
        logging.warning("Some repositories have no snapshots or returned errors.")


def print_status_report():
    """
    Display a detailed report of the restore operation results.
    """
    print_section("Restore Status Report")

    # Define icons and colors for different status types
    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "skipped": "⏭" if not DISABLE_COLORS else "[SKIPPED]",
    }

    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
        "skipped": NORD9,
    }

    descriptions = {
        "system": "System Restore",
        "vm": "VM Restore",
        "plex": "Plex Restore",
    }

    # Display status for each task
    for task, data in RESTORE_STATUS.items():
        status = data["status"]
        msg = data["message"]
        stats = data.get("stats", {})
        task_desc = descriptions.get(task, task)

        # Log the basic status
        if not DISABLE_COLORS:
            icon = icons.get(status, "?")
            color = colors.get(status, "")
            logging.info(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")
        else:
            logging.info(
                f"{icons.get(status, '?')} {task_desc}: {status.upper()} - {msg}"
            )

        # Log additional statistics if available
        if status == "success" and stats:
            logging.info(
                f"    • Files Restored: {stats.get('files_restored', 'unknown')}"
            )
            logging.info(f"    • Total Size: {stats.get('total_size', 'unknown')}")
            logging.info(f"    • Duration: {stats.get('duration', 'unknown')}")
            logging.info(f"    • Snapshot ID: {stats.get('snapshot_id', 'unknown')}")

            # Verification results
            if stats.get("verified", False):
                logging.info(f"    • Verification: Passed")
            else:
                logging.info(
                    f"    • Verification: {stats.get('verification_note', 'Failed')}"
                )

        elif status == "failed" and "error" in stats:
            logging.info(f"    • Error: {stats['error']}")

    # Create a rich table summary
    if not DISABLE_COLORS:
        summary_table = Table(title="Restore Summary")
        summary_table.add_column("Task", style="cyan")
        summary_table.add_column("Status", style="yellow")
        summary_table.add_column("Files", justify="right")
        summary_table.add_column("Size", justify="right")
        summary_table.add_column("Duration")

        for task, data in RESTORE_STATUS.items():
            task_desc = descriptions.get(task, task)
            status = data["status"]
            stats = data.get("stats", {})

            status_style = (
                "green"
                if status == "success"
                else "red"
                if status == "failed"
                else "yellow"
            )

            summary_table.add_row(
                task_desc,
                status.upper(),
                str(stats.get("files_restored", "N/A")),
                stats.get("total_size", "N/A"),
                stats.get("duration", "N/A"),
                style=None if status != "failed" else "red",
            )

        console.print(summary_table)


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    """
    Main function to orchestrate the restore process.
    """
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED RESTORE STARTED AT {now}")
    logging.info("=" * 80)

    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")

    # Check and create restore directories
    check_restore_dirs()

    # Display repository information
    print_repository_info()

    # Unlock repositories before restore operations
    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # Perform restore operations
    print_section("Restoring System Backup from Backblaze B2")
    restore_repo(
        B2_REPO_SYSTEM,
        RESTIC_PASSWORD,
        RESTORE_DIRS["system"],
        "system",
    )

    print_section("Restoring VM Backup from Backblaze B2")
    restore_repo(B2_REPO_VM, RESTIC_PASSWORD, RESTORE_DIRS["vm"], "vm")

    print_section("Restoring Plex Backup from Backblaze B2")
    restore_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RESTORE_DIRS["plex"], "plex")

    # Display final status report
    print_status_report()

    # Calculate and display summary
    elapsed = time.time() - start_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "failed")

    summary = (
        "SUCCESS"
        if failed_count == 0
        else "PARTIAL SUCCESS"
        if success_count > 0
        else "FAILED"
    )

    total_files = sum(
        data.get("stats", {}).get("files_restored", 0)
        for data in RESTORE_STATUS.values()
        if data["status"] == "success"
    )

    logging.info("=" * 80)
    logging.info(
        f"UNIFIED RESTORE COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)"
    )
    logging.info(f"Total of {total_files} files restored")
    logging.info("=" * 80)

    # Print restore locations for successful operations
    if success_count > 0:
        logging.info("Restore locations:")
        for task, data in RESTORE_STATUS.items():
            if data["status"] == "success":
                logging.info(f"  • {task.title()}: {RESTORE_DIRS[task]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        import traceback

        logging.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
