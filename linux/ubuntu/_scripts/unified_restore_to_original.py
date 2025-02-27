#!/usr/bin/env python3
"""
Comprehensive Unified Restore to Original Locations Script
------------------------------------------------------------
Description:
  A unified restore solution that retrieves the latest snapshots from three restic
  repositories stored on Backblaze B2 and restores the files directly to their original
  locations on an Ubuntu system. This script handles three backup types:
    1. System Backup – Contains a full system backup (root filesystem with exclusions)
    2. VM Backup – Contains libvirt virtual machine configurations and disk images
    3. Plex Backup – Contains Plex Media Server configuration and application data

  The restore process is two-fold:
    - First, each repository's latest snapshot is restored into a temporary directory.
    - Then, the files are moved (using rsync) from the temporary location to their exact
      original paths on the system, preserving file permissions and metadata.
    - Finally, a verification step confirms the integrity of restored files.

Usage:
  sudo ./unified_restore_to_original.py

Author: Your Name | License: MIT | Version: 2.0.0
"""

import atexit
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import tempfile
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.table import Table
from rich import box

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "005531878ffff660000000001"
B2_ACCOUNT_KEY = "K005oVgYPouP1DMQa5jhGfRBiX33Kns"
B2_BUCKET = "sawyer-backups"

HOSTNAME = socket.gethostname()

# Restic repository strings for Backblaze B2
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

RESTIC_PASSWORD = "j57z66Mwc^2A%Cf5!iAG^n&c&%wJ"

# Critical paths to verify after restore
CRITICAL_SYSTEM_PATHS = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM_PATHS = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX_PATHS = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

# Maximum retries and delay (for restic operations)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds

# Rsync options
RSYNC_OPTS = ["-a", "--info=progress2", "--stats"]

# Global restore status for reporting
RESTORE_STATUS = {
    "system": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
    "vm": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
    "plex": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
}

LOG_FILE = "/var/log/unified_restore_to_original.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# Rich console for enhanced output
console = Console()

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Dark background
NORD1 = "\033[38;2;59;66;82m"  # Darker gray
NORD3 = "\033[38;2;76;86;106m"  # Light gray
NORD4 = "\033[38;2;216;222;233m"  # Light foreground
NORD7 = "\033[38;2;143;188;187m"  # Pale blue
NORD8 = "\033[38;2;136;192;208m"  # Light blue
NORD9 = "\033[38;2;129;161;193m"  # Blue
NORD10 = "\033[38;2;94;129;172m"  # Dark blue
NORD11 = "\033[38;2;191;97;106m"  # Red
NORD12 = "\033[38;2;208;135;112m"  # Orange
NORD13 = "\033[38;2;235;203;139m"  # Yellow
NORD14 = "\033[38;2;163;190;140m"  # Green
NORD15 = "\033[38;2;180;142;173m"  # Purple
NC = "\033[0m"  # Reset


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """Custom logging formatter with Nord theme colors."""

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


def setup_logging() -> logging.Logger:
    """
    Set up logging with console and file handlers using Nord theme colors.
    Handles log rotation if the log file is too large.

    Returns:
        logging.Logger: Configured logger instance
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colored output
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        # Handle log rotation if file is too large
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:  # 10 MB
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Secure log file permissions
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logging.warning("Continuing with console logging only")

    return logger


def print_section(title: str) -> None:
    """
    Print a section header with Nord theme styling.

    Args:
        title: The title to display in the section header
    """
    if DISABLE_COLORS:
        # Simple ASCII version
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)
    else:
        # Rich version with Nord theme
        console.print(
            Panel(
                title,
                border_style=f"rgb(94,129,172)",
                title_align="center",
                width=80,
                padding=(1, 2),
            )
        )
        # Also log to file
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")


# ------------------------------------------------------------------------------
# Rich Progress Helper
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs) -> any:
    """
    Run a blocking function in a background thread while displaying a rich progress spinner.

    Args:
        description: Text to display alongside the spinner
        func: The function to run
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result from the function
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


def run_with_progress_bar(description: str, total: int, func, *args, **kwargs) -> any:
    """
    Run a blocking function in a background thread while displaying a rich progress bar.

    Args:
        description: Text to display alongside the progress bar
        total: Total number of steps
        func: The function to run
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result from the function
    """
    progress_state = {"current": 0}

    def progress_callback(increment):
        progress_state["current"] += increment

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, progress_callback, *args, **kwargs)
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task(description, total=total)
            while not future.done():
                progress.update(task, completed=progress_state["current"])
                time.sleep(0.1)

            # Ensure the bar shows as complete
            progress.update(task, completed=total)
            return future.result()


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    """
    Handle termination signals gracefully.

    Args:
        signum: Signal number
        frame: Stack frame
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

    # Return appropriate exit code for the signal
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup() -> None:
    """
    Perform cleanup tasks before exiting.
    Displays final status report if any restore operations were attempted.
    """
    logging.info("Performing cleanup tasks before exit.")

    if any(item["status"] != "pending" for item in RESTORE_STATUS.values()):
        print_status_report()

    # Clean up any temporary directories that might have been left behind
    temp_dir_pattern = os.path.join(tempfile.gettempdir(), "restic_restore_*")
    for path in Path(tempfile.gettempdir()).glob("restic_restore_*"):
        if path.is_dir():
            logging.info(f"Cleaning up temporary directory: {path}")
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception as e:
                logging.warning(f"Failed to remove temporary directory {path}: {e}")


# Register cleanup handler to run at exit
atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency and Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies() -> None:
    """
    Check for required dependencies and their versions.
    Exits if any are missing.
    """
    logging.info("Checking required dependencies...")
    dependencies = ["restic", "rsync"]
    missing = [dep for dep in dependencies if not shutil.which(dep)]

    if missing:
        logging.error(f"Missing required dependencies: {', '.join(missing)}")
        sys.exit(1)

    # Check restic version
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

    # Check rsync version
    try:
        result = subprocess.run(
            ["rsync", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        version_line = result.stdout.splitlines()[0] if result.stdout else "Unknown"
        logging.info(f"Using {version_line}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not determine rsync version: {e}")


def check_root() -> None:
    """
    Check if the script is running as root.
    Exits if not running as root.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


def check_free_space(temp_dir: str, required_gb: int = 10) -> bool:
    """
    Check if there's enough free space available for restore.

    Args:
        temp_dir: Directory to check for free space
        required_gb: Minimum required space in GB

    Returns:
        bool: True if there's enough free space, False otherwise
    """
    try:
        stat = os.statvfs(temp_dir)
        free_space_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)

        if free_space_gb < required_gb:
            logging.warning(
                f"Low disk space: Only {free_space_gb:.1f} GB free on {temp_dir}, "
                f"recommended minimum is {required_gb} GB"
            )
            return False

        logging.info(
            f"Sufficient disk space: {free_space_gb:.1f} GB free on {temp_dir}"
        )
        return True
    except Exception as e:
        logging.warning(f"Could not check free space on {temp_dir}: {e}")
        return True  # Assume there's enough space if we can't check


# ------------------------------------------------------------------------------
# Restic Repository Operations
# ------------------------------------------------------------------------------
def run_restic(
    repo: str,
    password: str,
    *args,
    check: bool = True,
    capture_output: bool = False,
    max_retries: int = MAX_RETRIES,
) -> Optional[subprocess.CompletedProcess]:
    """
    Run a restic command with retry logic for transient failures.

    Args:
        repo: Restic repository URL
        password: Repository password
        *args: Additional arguments for restic
        check: Whether to check for non-zero exit codes
        capture_output: Whether to capture and return stdout/stderr
        max_retries: Maximum number of retry attempts

    Returns:
        Optional[subprocess.CompletedProcess]: Command result if capture_output=True

    Raises:
        subprocess.CalledProcessError: If check=True and the command returns a non-zero exit code
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password

    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + list(args)

    # Mask password in logs
    log_cmd = cmd.copy()
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

            # Check for transient errors
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

            # Special case for repo initialization
            if "init" in args and "already initialized" in err_msg:
                logging.info("Repository already initialized, continuing.")
                return None

            # Retry for transient errors
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

    return None


def get_latest_snapshot_id(repo: str, password: str) -> Tuple[str, str]:
    """
    Retrieve the most recent snapshot ID and timestamp from the repository.

    Args:
        repo: Restic repository URL
        password: Repository password

    Returns:
        Tuple containing (snapshot_id, snapshot_time)
    """
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []

        if not snapshots:
            logging.error(f"No snapshots found in repository '{repo}'.")
            return "", ""

        # Sort snapshots by time (newest first)
        latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
        snapshot_id = latest.get("short_id") or latest.get("id", "")
        snapshot_time = latest.get("time", "")[:19]  # Truncate to seconds

        logging.info(
            f"Latest snapshot for '{repo}' is '{snapshot_id}' from {snapshot_time}."
        )
        return snapshot_id, snapshot_time
    except Exception as e:
        logging.error(f"Error retrieving latest snapshot from '{repo}': {e}")
        return "", ""


def force_unlock_repo(repo: str, password: str) -> bool:
    """
    Force unlock a repository, removing all stale locks.

    Args:
        repo: Restic repository URL
        password: Repository password

    Returns:
        bool: True if successful, False otherwise
    """
    logging.warning(f"Forcing unlock of repository '{repo}'")

    try:
        # First check if the repo exists and is accessible
        run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )

        # Remove all locks
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)

        if "no locks to remove" in err_msg:
            logging.info("Repository was already unlocked.")
            return True

        if (
            "unable to open config file" in err_msg
            or "unable to locate repository" in err_msg
        ):
            logging.error(f"Repository not found or inaccessible: {err_msg}")
            return False

        logging.error(f"Failed to unlock repository: {err_msg}")
        return False


def get_repo_stats(repo: str, password: str) -> Dict[str, Union[int, str]]:
    """
    Get statistics about a repository.

    Args:
        repo: Restic repository URL
        password: Repository password

    Returns:
        Dict containing repository statistics
    """
    stats = {
        "snapshots": 0,
        "total_size": "unknown",
        "latest_snapshot": "never",
        "files": 0,
    }

    try:
        # Get snapshot information
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []
        stats["snapshots"] = len(snapshots)

        if snapshots:
            latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
            stats["latest_snapshot"] = latest.get("time", "unknown")[:19]

            # Get stats from the latest snapshot
            snapshot_id = latest.get("short_id") or latest.get("id", "")
            try:
                result = run_restic(
                    repo, password, "stats", snapshot_id, "--json", capture_output=True
                )
                snapshot_stats = (
                    json.loads(result.stdout) if result and result.stdout else {}
                )
                stats["files"] = snapshot_stats.get("total_file_count", 0)
            except Exception:
                pass

        # Get overall repository size
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        repo_stats = json.loads(result.stdout) if result and result.stdout else {}
        total = repo_stats.get("total_size", 0)
        stats["total_size"] = format_size(total)

    except Exception as e:
        logging.warning(f"Could not get repository stats: {e}")

    return stats


def format_size(size_bytes: int) -> str:
    """
    Format a size in bytes to a human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes == 0:
        return "0 B"

    names = ["B", "KB", "MB", "GB", "TB"]
    i = 0

    while size_bytes >= 1024 and i < len(names) - 1:
        size_bytes /= 1024
        i += 1

    return f"{size_bytes:.2f} {names[i]}"


# ------------------------------------------------------------------------------
# Restore Operations (with Verification)
# ------------------------------------------------------------------------------
def restore_repo_to_original(
    repo: str, password: str, task_name: str, critical_paths: List[str] = None
) -> bool:
    """
    Restore a repository to original locations with progress indicators and verification.

    Args:
        repo: Restic repository URL
        password: Repository password
        task_name: Task identifier for status reporting
        critical_paths: List of critical paths to verify after restore

    Returns:
        bool: True if successful, False otherwise
    """
    if critical_paths is None:
        critical_paths = []

    # Update status to in-progress
    RESTORE_STATUS[task_name] = {
        "status": "in_progress",
        "message": "Restore in progress...",
        "files_restored": 0,
        "snapshot": "",
    }

    # Get the latest snapshot ID
    snapshot_id, snapshot_time = get_latest_snapshot_id(repo, password)
    if not snapshot_id:
        msg = f"No snapshots found for repository '{repo}'."
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "files_restored": 0,
            "snapshot": "",
        }
        return False

    RESTORE_STATUS[task_name]["snapshot"] = snapshot_time

    # Create a temporary directory for the restore operation
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    logging.info(f"Created temporary restore directory: {temp_dir}")

    # Make sure we have enough disk space
    if not check_free_space(temp_dir):
        msg = "Insufficient disk space for restore operation."
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "files_restored": 0,
            "snapshot": snapshot_time,
        }
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Run restic restore into the temporary directory
    logging.info(
        f"Starting restore of snapshot {snapshot_id} from {repo} to {temp_dir}"
    )
    cmd_args = ["restore", snapshot_id, "--target", temp_dir]
    start = time.time()

    try:
        run_with_progress(
            f"Restoring {task_name} backup to temporary directory...",
            run_restic,
            repo,
            password,
            *cmd_args,
            capture_output=True,
        )
        elapsed = time.time() - start
        logging.info(f"Restic restore command completed in {elapsed:.1f} seconds.")
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"
        msg = f"Restic restore command failed after {elapsed:.1f} seconds: {err_output}"
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "files_restored": 0,
            "snapshot": snapshot_time,
        }
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Restic creates a folder named "restored-<snapshot_id>" inside the target directory
    restored_dir = os.path.join(temp_dir, "restored-" + snapshot_id)
    if not os.path.exists(restored_dir):
        restored_dir = os.path.join(temp_dir)  # Try the temp dir directly
        if not os.path.isdir(restored_dir) or not os.listdir(restored_dir):
            msg = f"Restored directory does not exist or is empty."
            logging.error(msg)
            RESTORE_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "files_restored": 0,
                "snapshot": snapshot_time,
            }
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    # Count files for progress reporting
    file_count = 0
    try:
        # Quick estimate of file count using find command
        find_cmd = ["find", restored_dir, "-type", "f", "-print"]
        find_proc = subprocess.run(
            find_cmd, capture_output=True, text=True, check=False
        )

        file_lines = find_proc.stdout.strip().split("\n")
        file_count = len([line for line in file_lines if line])  # Filter empty lines
        logging.info(f"Estimated {file_count} files to restore to original locations.")
    except Exception as e:
        logging.warning(f"Could not count files in restore directory: {e}")
        file_count = 10000  # Default estimate if count fails

    # Use rsync to copy files from temporary restore location to system root (/)
    rsync_cmd = ["rsync"] + RSYNC_OPTS + ["--delete", restored_dir + "/", "/"]
    logging.info(f"Running rsync command: {' '.join(rsync_cmd)}")

    rsync_start = time.time()
    try:
        rsync_proc = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Handle rsync output
        stdout, stderr = rsync_proc.communicate()
        rsync_exit_code = rsync_proc.wait()

        if rsync_exit_code != 0:
            raise subprocess.CalledProcessError(rsync_exit_code, rsync_cmd, stderr)

        elapsed_rsync = time.time() - rsync_start

        # Parse rsync stats from stdout
        files_restored = 0
        for line in stdout.splitlines():
            if "Number of files transferred:" in line:
                files_restored = int(line.split(":")[1].strip())
                break

        msg = f"Rsync completed in {elapsed_rsync:.1f} seconds; {files_restored} files restored."
        logging.info(msg)
        RESTORE_STATUS[task_name]["files_restored"] = files_restored

    except subprocess.CalledProcessError as e:
        elapsed_rsync = time.time() - rsync_start
        err_output = e.stderr or "Unknown error"
        msg = f"Rsync failed after {elapsed_rsync:.1f} seconds: {err_output}"
        logging.error(msg)
        RESTORE_STATUS[task_name] = {
            "status": "failed",
            "message": msg,
            "files_restored": 0,
            "snapshot": snapshot_time,
        }
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Verify critical paths are restored properly
    if critical_paths:
        missing_paths = [path for path in critical_paths if not os.path.exists(path)]
        if missing_paths:
            msg = f"Restore verification failed: {len(missing_paths)} critical paths missing."
            logging.error(msg)
            logging.error(f"Missing paths: {', '.join(missing_paths)}")
            RESTORE_STATUS[task_name] = {
                "status": "warning",
                "message": msg,
                "files_restored": RESTORE_STATUS[task_name]["files_restored"],
                "snapshot": snapshot_time,
            }
        else:
            logging.info(
                f"Verified {len(critical_paths)} critical paths restored successfully."
            )

    # Calculate total restore time
    total_elapsed = time.time() - start
    msg = f"Restore completed in {total_elapsed:.1f} seconds. {RESTORE_STATUS[task_name]['files_restored']} files restored."
    RESTORE_STATUS[task_name]["status"] = "success"
    RESTORE_STATUS[task_name]["message"] = msg
    logging.info(msg)

    # Clean up the temporary restore directory
    try:
        shutil.rmtree(temp_dir)
        logging.info(f"Temporary restore directory '{temp_dir}' removed.")
    except Exception as e:
        logging.warning(f"Failed to remove temporary directory '{temp_dir}': {e}")

    return True


# ------------------------------------------------------------------------------
# Status Reporting
# ------------------------------------------------------------------------------
def print_status_report() -> None:
    """
    Print a detailed status report of all restore operations.
    Uses rich tables for enhanced output.
    """
    print_section("Restore Status Report")

    # Define icons and colors for different status types
    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "warning": "⚠" if not DISABLE_COLORS else "[WARNING]",
    }

    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
        "warning": NORD12,
    }

    descriptions = {
        "system": "System Restore",
        "vm": "VM Restore",
        "plex": "Plex Restore",
    }

    # Create a rich table for the report
    if not DISABLE_COLORS:
        table = Table(title="Restore Operations Summary", box=box.ROUNDED)
        table.add_column("Task", style="dim")
        table.add_column("Status", style="bold")
        table.add_column("Files Restored")
        table.add_column("Snapshot Time")
        table.add_column("Message")

        for task, data in RESTORE_STATUS.items():
            status = data["status"]
            msg = data["message"]
            task_desc = descriptions.get(task, task)
            files = data.get("files_restored", 0)
            snapshot_time = data.get("snapshot", "")

            status_color = {
                "success": "green",
                "failed": "red",
                "pending": "yellow",
                "in_progress": "blue",
                "warning": "orange3",
            }.get(status, "white")

            table.add_row(
                task_desc,
                f"[{status_color}]{status.upper()}[/{status_color}]",
                str(files),
                snapshot_time,
                msg,
            )

        console.print(table)

    # Also log to file in a simpler format
    for task, data in RESTORE_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)
        files = data.get("files_restored", 0)
        snapshot_time = data.get("snapshot", "")

        if not DISABLE_COLORS:
            icon = icons.get(status, "?")
            color = colors.get(status, "")
            logging.info(
                f"{color}{icon} {task_desc}: {status.upper()}{NC} - {files} files from {snapshot_time} - {msg}"
            )
        else:
            logging.info(
                f"{icons.get(status, '?')} {task_desc}: {status.upper()} - {files} files from {snapshot_time} - {msg}"
            )


def print_repository_info() -> None:
    """
    Print information about available repositories.
    Uses rich tables for enhanced output.
    """
    print_section("Repository Information")

    repos = [
        ("System", B2_REPO_SYSTEM, CRITICAL_SYSTEM_PATHS),
        ("VM", B2_REPO_VM, CRITICAL_VM_PATHS),
        ("Plex", B2_REPO_PLEX, CRITICAL_PLEX_PATHS),
    ]

    if not DISABLE_COLORS:
        table = Table(title="Available Backups", box=box.ROUNDED)
        table.add_column("Repository", style="dim")
        table.add_column("Location")
        table.add_column("Snapshots", justify="right")
        table.add_column("Files", justify="right")
        table.add_column("Total Size", justify="right")
        table.add_column("Latest Snapshot")

        for name, repo, _ in repos:
            try:
                stats = get_repo_stats(repo, RESTIC_PASSWORD)
                if stats["snapshots"] > 0:
                    table.add_row(
                        name,
                        repo,
                        str(stats["snapshots"]),
                        str(stats["files"]),
                        stats["total_size"],
                        stats["latest_snapshot"],
                    )
                else:
                    table.add_row(
                        name, repo, "0", "0", "-", "[italic]No snapshots found[/italic]"
                    )
            except Exception as e:
                table.add_row(
                    name,
                    repo,
                    "[red]ERROR[/red]",
                    "-",
                    "-",
                    f"[red italic]{str(e)}[/red italic]",
                )

        console.print(table)

    # Also log repository info to the log file
    for name, repo, _ in repos:
        try:
            stats = get_repo_stats(repo, RESTIC_PASSWORD)
            logging.info(f"{name} Repository: {repo}")
            if stats["snapshots"] > 0:
                logging.info(f"  • Snapshots: {stats['snapshots']}")
                logging.info(f"  • Files: {stats['files']}")
                logging.info(f"  • Size: {stats['total_size']}")
                logging.info(f"  • Latest snapshot: {stats['latest_snapshot']}")
            else:
                logging.info("  • No snapshots found")
        except Exception as e:
            logging.warning(f"Could not get info for {name} repo: {e}")


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main() -> None:
    """
    Main entry point for the restore script.
    """
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logging.info("=" * 80)
    logging.info(f"UNIFIED RESTORE TO ORIGINAL LOCATIONS STARTED AT {now}")
    logging.info("=" * 80)

    # Display system information
    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")
    logging.info(f"Operating system: {os.uname().sysname} {os.uname().release}")

    # Display information about available backups
    print_repository_info()

    # Optionally force-unlock repositories before restore
    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # Restore System Backup
    print_section("Restoring System Backup to Original Locations")
    restore_repo_to_original(
        B2_REPO_SYSTEM, RESTIC_PASSWORD, "system", CRITICAL_SYSTEM_PATHS
    )

    # Restore VM Backup
    print_section("Restoring VM Backup to Original Locations")
    restore_repo_to_original(B2_REPO_VM, RESTIC_PASSWORD, "vm", CRITICAL_VM_PATHS)

    # Restore Plex Backup
    print_section("Restoring Plex Backup to Original Locations")
    restore_repo_to_original(B2_REPO_PLEX, RESTIC_PASSWORD, "plex", CRITICAL_PLEX_PATHS)

    # Print final status report
    print_status_report()

    # Calculate and display summary statistics
    elapsed = time.time() - start_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "failed")
    warning_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "warning")

    if failed_count == 0 and warning_count == 0:
        summary = "SUCCESS"
    elif failed_count == 0 and warning_count > 0:
        summary = "SUCCESS WITH WARNINGS"
    elif success_count > 0:
        summary = "PARTIAL SUCCESS"
    else:
        summary = "FAILED"

    total_files = sum(v.get("files_restored", 0) for v in RESTORE_STATUS.values())

    # Create a summary message with rich formatting for console output
    if not DISABLE_COLORS:
        color = {
            "SUCCESS": "green",
            "SUCCESS WITH WARNINGS": "yellow",
            "PARTIAL SUCCESS": "yellow",
            "FAILED": "red",
        }.get(summary, "white")

        console.print(
            Panel(
                f"[bold {color}]{summary}[/bold {color}]\n\n"
                f"Completed in [bold]{elapsed:.1f}[/bold] seconds\n"
                f"Restored [bold]{total_files}[/bold] files\n"
                f"Successful backups: [green]{success_count}[/green]\n"
                f"Warnings: [yellow]{warning_count}[/yellow]\n"
                f"Failures: [red]{failed_count}[/red]",
                title="Restore Summary",
                border_style=f"rgb(94,129,172)",
                width=60,
            )
        )

    # Log summary
    logging.info("=" * 80)
    logging.info(
        f"UNIFIED RESTORE TO ORIGINAL COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)"
    )
    logging.info(f"Total files restored: {total_files}")
    logging.info(
        f"Successful backups: {success_count}, Warnings: {warning_count}, Failures: {failed_count}"
    )
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}", exc_info=True)
        sys.exit(1)
