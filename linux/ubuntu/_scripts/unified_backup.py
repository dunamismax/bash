#!/usr/bin/env python3
"""
Comprehensive Unified Backup Script
-----------------------------------
Description:
  A unified backup solution that performs three types of backups to Backblaze B2:
    1. System Backup - Backs up the entire system (/)
    2. VM Backup - Backs up libvirt virtual machine configurations and disk images
    3. Plex Backup - Backs up Plex Media Server configuration and application data

  Each backup is stored in a separate repository within the same B2 bucket.
  All repositories are named with the hostname prefix for organization.
  The script automatically checks repositories, forces unlocks before backup,
  and enforces retention policies.

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 3.2.0
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
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"

# Determine the hostname to uniquely name the repositories
HOSTNAME = socket.gethostname()

# Restic repository strings for B2 follow the format: b2:bucket:directory
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "12345678"

# Backup Source Directories and Exclusions
# System Backup
SYSTEM_SOURCE = "/"  # Backup the entire system
SYSTEM_EXCLUDES = [
    # Virtual / dynamic filesystems – always exclude these.
    "/proc/*",
    "/sys/*",
    "/dev/*",
    "/run/*",
    # Temporary directories (often changing, transient, or recreated on boot)
    "/tmp/*",
    "/var/tmp/*",
    # Mount points and removable media (to avoid backing up external or transient mounts)
    "/mnt/*",
    "/media/*",
    # Common cache directories that need not be backed up
    "/var/cache/*",
    "/var/log/*",
    # User-level cache folders (if you wish to exclude them; adjust as needed)
    "/home/*/.cache/*",
    # Swap file, lost+found, and other system artifacts
    "/swapfile",
    "/lost+found",
    # Exclude VM disk images (common locations and file extensions)
    "*.vmdk",  # VMware disk image
    "*.vdi",  # VirtualBox disk image
    "*.qcow2",  # QEMU/KVM disk image
    "*.img",  # Generic disk image (use with caution if you also have valid .img files)
    # Other large, transient files
    "*.iso",  # Disc images
    "*.tmp",
    "*.swap.img",
    # Exclude specific directories known to store ephemeral or large nonessential data
    "/var/lib/docker/*",  # Docker images/containers (if not intended to be backed up)
    "/var/lib/lxc/*",  # LXC containers (if not intended to be backed up)
]

# VM Backup
VM_SOURCES = [
    "/etc/libvirt",  # Contains XML config files for VMs
    "/var/lib/libvirt",  # Contains VM disk images and additional libvirt data
]
VM_EXCLUDES = [
    # Example: exclude temporary libvirt cache or lock files if needed
    # "/etc/libvirt/qemu/*.lock",
]

# Plex Backup
PLEX_SOURCES = [
    "/var/lib/plexmediaserver",  # Plex Media Server application data
    "/etc/default/plexmediaserver",  # Plex configuration
]
PLEX_EXCLUDES = [
    # Exclude cache and transcoding directories
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS = 7

# Maximum age for a lock to be considered stale (in hours)
STALE_LOCK_HOURS = 2

# Maximum number of retries for operations
MAX_RETRIES = 3

# Delay between retries (in seconds)
RETRY_DELAY_BASE = 5  # Will be multiplied by retry attempt number for backoff

# Status tracking for reporting
BACKUP_STATUS = {
    "system": {"status": "pending", "message": ""},
    "vm": {"status": "pending", "message": ""},
    "plex": {"status": "pending", "message": ""},
    "cleanup_system": {"status": "pending", "message": ""},
    "cleanup_vm": {"status": "pending", "message": ""},
    "cleanup_plex": {"status": "pending", "message": ""},
}

# Logging Configuration
LOG_FILE = "/var/log/unified_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------


class NordColorFormatter(logging.Formatter):
    """
    A custom formatter that applies Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)

        if not self.use_colors:
            return msg

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    Sets up logging with console and file handlers using the Nord color theme.
    Applies appropriate formatting and handles permissions for log files.

    Returns:
        logging.Logger: Configured logger instance
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        # Create a new log file with a rotation suffix if it exceeds 10MB
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Set secure permissions
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord theme styling.

    Args:
        title (str): The title to display in the section header
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------


def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.

    Args:
        signum (int): Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")

    # Do cleanup before exit
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")

    # Exit with appropriate code
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


# Register signal handlers for common termination signals
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    Prints a final status report and performs any necessary cleanup operations.
    """
    logging.info("Performing cleanup tasks before exit.")

    # Print final status report if the script has started any operations
    if any(item["status"] != "pending" for item in BACKUP_STATUS.values()):
        print_status_report()

    # You could add additional cleanup tasks here if needed
    # For example, removing temporary files or releasing resources


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    Verifies that all required external commands are available in the system PATH.

    Raises:
        SystemExit: If any required dependency is missing
    """
    dependencies = ["restic"]
    missing_deps = []

    for dep in dependencies:
        if not shutil.which(dep):
            missing_deps.append(dep)

    if missing_deps:
        logging.error(f"Missing required dependencies: {', '.join(missing_deps)}")
        logging.error("Please install these dependencies and try again.")
        sys.exit(1)
    else:
        logging.debug("All required dependencies are installed.")

    # Check restic version to ensure compatibility
    try:
        result = subprocess.run(
            ["restic", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        version_output = result.stdout.strip()
        logging.info(f"Using {version_output}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not determine restic version: {e}")


def check_root():
    """
    Ensure the script is run with root privileges.

    Raises:
        SystemExit: If the script is not run as root
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Script is running with root privileges.")


# ------------------------------------------------------------------------------
# REPOSITORY OPERATIONS
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
    Run a restic command with appropriate environment variables and retry logic.

    Args:
        repo (str): The restic repository path
        password (str): The repository password
        *args: Command arguments to pass to restic
        check (bool): Whether to check for command success
        capture_output (bool): Whether to capture and return command output
        max_retries (int): Maximum number of retry attempts for transient errors

    Returns:
        subprocess.CompletedProcess: The command result if capture_output is True, else None

    Raises:
        subprocess.CalledProcessError: If the command fails and check=True
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    cmd_safe = cmd.copy()

    # Mask password in logs if it appears in the command
    if "--password-file" in cmd_safe:
        password_index = cmd_safe.index("--password-file") + 1
        if password_index < len(cmd_safe):
            cmd_safe[password_index] = "[REDACTED]"

    logging.info(f"Running restic command: {' '.join(cmd_safe)}")

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
            error_msg = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)

            # Check for transient errors that we can retry
            transient_errors = [
                "connection reset by peer",
                "unexpected EOF",
                "timeout",
                "connection refused",
                "network error",
                "429 Too Many Requests",
                "500 Internal Server Error",
                "503 Service Unavailable",
                "temporarily unavailable",
            ]

            is_transient = any(
                err.lower() in error_msg.lower() for err in transient_errors
            )

            # Special handling for init errors when repository already exists
            if "init" in args and "already initialized" in error_msg:
                logging.info("Repository is already initialized, continuing.")
                return None

            if is_transient and retries < max_retries:
                retries += 1
                retry_delay = RETRY_DELAY_BASE * (
                    2 ** (retries - 1)
                )  # Exponential backoff
                logging.warning(
                    f"Transient error detected, retrying in {retry_delay} seconds ({retries}/{max_retries})..."
                )
                time.sleep(retry_delay)
                continue
            else:
                if retries > 0:
                    logging.error(f"Command failed after {retries} retries.")
                raise e

    # If we've exhausted retries, raise the last error
    if last_error:
        raise last_error

    return None


def is_repo_initialized(repo: str, password: str) -> bool:
    """
    Check if a repository is already initialized.

    Args:
        repo (str): The repository path to check
        password (str): The repository password

    Returns:
        bool: True if the repository is initialized, False otherwise
    """
    logging.info(f"Checking if repository '{repo}' is initialized...")

    try:
        # Using snapshots with --no-lock is a reliable way to check if a repo exists
        run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )
        logging.info(f"Repository '{repo}' is initialized.")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if hasattr(e, "stderr") else str(e)

        # Check for specific error messages that indicate the repo is initialized but has other issues
        if any(
            msg in error_msg
            for msg in [
                "config is already initialized",
                "already initialized",
                "repository master key and config already initialized",
            ]
        ):
            logging.info(f"Repository '{repo}' is initialized but had access issues.")
            return True

        logging.info(f"Repository '{repo}' is not initialized.")
        return False


def ensure_repo_initialized(repo: str, password: str):
    """
    Ensures that a restic repository is initialized.
    Checks if a repository exists first, and only initializes if needed.

    Args:
        repo (str): The repository path to check
        password (str): The repository password

    Returns:
        bool: True if the repository is ready to use

    Raises:
        RuntimeError: If repository initialization fails after retries
    """
    logging.info(f"Ensuring repository '{repo}' is initialized...")

    # First check if the repository is already initialized
    if is_repo_initialized(repo, password):
        logging.info(f"Repository '{repo}' is already initialized and accessible.")
        return True

    # If not initialized, try to initialize it
    logging.info(
        f"Repository '{repo}' not initialized or not accessible. Initializing..."
    )

    try:
        run_restic(repo, password, "init")
        logging.info(f"Repository '{repo}' successfully initialized.")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if hasattr(e, "stderr") else str(e)

        # Check if the error is because the repository is already initialized
        if "already initialized" in error_msg:
            logging.info(
                f"Repository '{repo}' is already initialized (discovered during init)."
            )
            return True

        # Otherwise, it's a real error
        logging.error(f"Failed to initialize repository: {error_msg}")
        raise RuntimeError(f"Failed to initialize repository: {error_msg}")


def force_unlock_repo(repo: str, password: str):
    """
    Force unlock a repository, removing all locks regardless of age.

    Args:
        repo (str): The repository path to unlock
        password (str): The repository password

    Returns:
        bool: True if successful, False otherwise
    """
    logging.warning(f"Forcing unlock of repository '{repo}'")

    try:
        # First check if the repository is initialized
        if not is_repo_initialized(repo, password):
            logging.warning(
                f"Cannot unlock repository '{repo}' as it is not initialized."
            )
            return False

        # Try to unlock
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if hasattr(e, "stderr") else str(e)

        # Ignore already unlocked errors
        if "no locks to remove" in error_msg:
            logging.info("Repository was already unlocked.")
            return True

        logging.error(f"Failed to force unlock repository: {error_msg}")
        return False


def get_repo_stats(repo: str, password: str):
    """
    Get repository statistics including size, number of snapshots, etc.

    Args:
        repo (str): The repository path
        password (str): The repository password

    Returns:
        dict: Repository statistics or empty dict if statistics cannot be retrieved
    """
    stats = {"snapshots": 0, "total_size": "unknown", "latest_snapshot": "never"}

    if not is_repo_initialized(repo, password):
        return stats

    # Get snapshot count and dates
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        if result and result.stdout:
            snapshots = json.loads(result.stdout)
            stats["snapshots"] = len(snapshots)

            if snapshots:
                # Sort by time and get the most recent
                sorted_snapshots = sorted(
                    snapshots, key=lambda x: x.get("time", ""), reverse=True
                )
                latest = sorted_snapshots[0]
                stats["latest_snapshot"] = latest.get("time", "unknown")[
                    :19
                ]  # Truncate to date and time only
    except Exception as e:
        logging.warning(f"Could not get snapshot information: {e}")

    # Get repository size
    try:
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        if result and result.stdout:
            repo_stats = json.loads(result.stdout)
            total_size_bytes = repo_stats.get("total_size", 0)
            # Convert to human-readable format
            stats["total_size"] = format_size(total_size_bytes)
    except Exception as e:
        logging.warning(f"Could not get repository size information: {e}")

    return stats


def format_size(size_bytes):
    """Convert bytes to human-readable format"""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1

    return f"{size_bytes:.2f} {size_names[i]}"


# ------------------------------------------------------------------------------
# BACKUP OPERATIONS
# ------------------------------------------------------------------------------


def backup_repo(
    repo: str, password: str, source, excludes: list = None, task_name: str = None
):
    """
    Perform backup to a repository, with force unlock.

    Args:
        repo (str): The repository path for backup
        password (str): The repository password
        source (str or list): The source path(s) to backup
        excludes (list): Patterns to exclude from backup
        task_name (str): Name of the task for status tracking

    Returns:
        bool: True if the backup was successful, False otherwise
    """
    if excludes is None:
        excludes = []

    # Track task status if name provided
    if task_name:
        BACKUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": "Backup in progress...",
        }

    # Check if repository is initialized
    try:
        ensure_repo_initialized(repo, password)
    except Exception as e:
        error_msg = f"Failed to initialize repository: {str(e)}"
        logging.error(error_msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        return False

    # Always force unlock the repository
    if not force_unlock_repo(repo, password):
        error_msg = "Failed to unlock repository before backup"
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        return False

    # Prepare backup command
    cmd_args = ["backup"]

    # Handle both single source and multiple sources
    if isinstance(source, list):
        cmd_args.extend(source)
    else:
        cmd_args.append(source)

    # Add excludes
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])

    # Run backup
    start_time = time.time()
    try:
        result = run_restic(repo, password, *cmd_args, capture_output=True)
        elapsed_time = time.time() - start_time
        success_msg = f"Backup completed successfully in {elapsed_time:.1f} seconds"
        logging.info(success_msg)

        if task_name:
            BACKUP_STATUS[task_name] = {"status": "success", "message": success_msg}

        # Log summary info from the backup
        if result and result.stdout:
            if "Files:" in result.stdout:
                for line in result.stdout.splitlines():
                    if any(
                        x in line
                        for x in ["Files:", "Added to the", "processed", "snapshot"]
                    ):
                        logging.info(f"Summary: {line.strip()}")

        return True

    except subprocess.CalledProcessError as e:
        elapsed_time = time.time() - start_time
        error_output = e.stderr if hasattr(e, "stderr") else "Unknown error"

        # If backup fails due to lock, try to force unlock and retry
        if "repository is already locked" in error_output:
            logging.warning(
                "Backup failed due to repository lock. Attempting to unlock again..."
            )
            if force_unlock_repo(repo, password):
                logging.info("Retrying backup after force unlock...")
                try:
                    result = run_restic(repo, password, *cmd_args, capture_output=True)
                    total_time = time.time() - start_time
                    success_msg = f"Backup completed successfully after retry in {total_time:.1f} seconds"
                    logging.info(success_msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": success_msg,
                        }

                    # Log summary info
                    if result and result.stdout:
                        for line in result.stdout.splitlines():
                            if any(
                                x in line
                                for x in [
                                    "Files:",
                                    "Added to the",
                                    "processed",
                                    "snapshot",
                                ]
                            ):
                                logging.info(f"Summary: {line.strip()}")

                    return True

                except Exception as retry_e:
                    error_msg = f"Backup failed after retry: {str(retry_e)}"
                    logging.error(error_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": error_msg,
                        }
                    return False
            else:
                error_msg = f"Failed to unlock repository for retry after {elapsed_time:.1f} seconds"
                logging.error(error_msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": error_msg,
                    }
                return False
        else:
            error_msg = (
                f"Backup failed after {elapsed_time:.1f} seconds: {error_output}"
            )
            logging.error(error_msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
            return False


def cleanup_repo(repo: str, password: str, retention_days: int, task_name: str = None):
    """
    Clean up old snapshots based on retention policy.
    Handles potential repository locks gracefully.

    Args:
        repo (str): The repository path to clean up
        password (str): The repository password
        retention_days (int): Days to keep snapshots
        task_name (str): Name of the task for status tracking

    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    if task_name:
        BACKUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": "Cleanup in progress...",
        }

    # Ensure repository is initialized
    try:
        if not is_repo_initialized(repo, password):
            msg = f"Repository '{repo}' is not initialized or accessible. Skipping cleanup."
            logging.warning(msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "skipped", "message": msg}
            return False
    except Exception as e:
        error_msg = f"Failed to check repository status for cleanup: {str(e)}"
        logging.error(error_msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        return False

    # Always force unlock the repository
    if not force_unlock_repo(repo, password):
        error_msg = "Failed to unlock repository before cleanup"
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        return False

    # Run cleanup command
    start_time = time.time()
    try:
        result = run_restic(
            repo,
            password,
            "forget",
            "--prune",
            "--keep-within",
            f"{retention_days}d",
            capture_output=True,
        )
        elapsed_time = time.time() - start_time
        success_msg = f"Cleanup completed successfully in {elapsed_time:.1f} seconds"
        logging.info(success_msg)

        if task_name:
            BACKUP_STATUS[task_name] = {"status": "success", "message": success_msg}

        # Log summary info from the cleanup
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(
                    x in line for x in ["snapshots", "removing", "remaining", "deleted"]
                ):
                    logging.info(f"Cleanup: {line.strip()}")

        return True

    except subprocess.CalledProcessError as e:
        elapsed_time = time.time() - start_time
        error_output = e.stderr if hasattr(e, "stderr") else "Unknown error"

        # If cleanup fails due to lock, try to force unlock and retry
        if "repository is already locked" in error_output:
            logging.warning(
                "Cleanup failed due to repository lock. Attempting to force unlock again..."
            )
            if force_unlock_repo(repo, password):
                logging.info("Retrying cleanup after force unlock...")
                try:
                    result = run_restic(
                        repo,
                        password,
                        "forget",
                        "--prune",
                        "--keep-within",
                        f"{retention_days}d",
                        capture_output=True,
                    )
                    total_time = time.time() - start_time
                    success_msg = f"Cleanup completed successfully after retry in {total_time:.1f} seconds"
                    logging.info(success_msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": success_msg,
                        }

                    # Log summary info
                    if result and result.stdout:
                        for line in result.stdout.splitlines():
                            if any(
                                x in line
                                for x in [
                                    "snapshots",
                                    "removing",
                                    "remaining",
                                    "deleted",
                                ]
                            ):
                                logging.info(f"Cleanup: {line.strip()}")

                    return True

                except Exception as retry_e:
                    error_msg = f"Cleanup failed after retry: {str(retry_e)}"
                    logging.error(error_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": error_msg,
                        }
                    return False
            else:
                error_msg = f"Failed to unlock repository for cleanup retry after {elapsed_time:.1f} seconds"
                logging.error(error_msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": error_msg,
                    }
                return False
        else:
            error_msg = (
                f"Cleanup failed after {elapsed_time:.1f} seconds: {error_output}"
            )
            logging.error(error_msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
            return False


# ------------------------------------------------------------------------------
# STATUS REPORTING
# ------------------------------------------------------------------------------


def print_status_report():
    """
    Print a formatted status report of all backup operations.
    """
    print_section("Backup Status Report")

    status_icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "skipped": "⏭" if not DISABLE_COLORS else "[SKIPPED]",
    }

    status_colors = {
        "success": NORD14,  # Green
        "failed": NORD11,  # Red
        "pending": NORD13,  # Yellow
        "in_progress": NORD8,  # Light blue
        "skipped": NORD9,  # Light blue
    }

    # Map task names to human-readable descriptions
    task_descriptions = {
        "system": "System Backup",
        "vm": "Virtual Machine Backup",
        "plex": "Plex Media Server Backup",
        "cleanup_system": "System Backup Cleanup",
        "cleanup_vm": "VM Backup Cleanup",
        "cleanup_plex": "Plex Backup Cleanup",
    }

    for task_name, status_data in BACKUP_STATUS.items():
        status = status_data["status"]
        message = status_data["message"]

        task_desc = task_descriptions.get(task_name, task_name)

        if not DISABLE_COLORS:
            status_icon = status_icons[status]
            status_color = status_colors[status]
            logging.info(
                f"{status_color}{status_icon} {task_desc}: {status.upper()}{NC} - {message}"
            )
        else:
            status_icon = status_icons[status]
            logging.info(f"{status_icon} {task_desc}: {status.upper()} - {message}")


def print_repository_info():
    """
    Print information about all repositories.
    """
    print_section("Repository Information")

    repos = [("System", B2_REPO_SYSTEM), ("VM", B2_REPO_VM), ("Plex", B2_REPO_PLEX)]

    for name, repo in repos:
        try:
            stats = get_repo_stats(repo, RESTIC_PASSWORD)

            if stats["snapshots"] > 0:
                logging.info(f"{name} Repository: {repo}")
                logging.info(f"  • Snapshots: {stats['snapshots']}")
                logging.info(f"  • Size: {stats['total_size']}")
                logging.info(f"  • Latest snapshot: {stats['latest_snapshot']}")
            else:
                logging.info(f"{name} Repository: {repo}")
                logging.info(f"  • No snapshots found")
        except Exception as e:
            logging.warning(f"Could not get information for {name} repository: {e}")


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)

    # Print system information
    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")

    # Print repository information
    print_repository_info()

    # Force unlock all repositories before starting
    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # System Backup
    print_section("System Backup to Backblaze B2")
    system_success = backup_repo(
        B2_REPO_SYSTEM, RESTIC_PASSWORD, SYSTEM_SOURCE, SYSTEM_EXCLUDES, "system"
    )

    # VM Backup
    print_section("VM Backup to Backblaze B2")
    vm_success = backup_repo(B2_REPO_VM, RESTIC_PASSWORD, VM_SOURCES, VM_EXCLUDES, "vm")

    # Plex Backup
    print_section("Plex Media Server Backup to Backblaze B2")
    plex_success = backup_repo(
        B2_REPO_PLEX, RESTIC_PASSWORD, PLEX_SOURCES, PLEX_EXCLUDES, "plex"
    )

    # Clean up old snapshots for all repositories
    print_section("Cleaning Up Old Snapshots (Retention Policy)")

    # System Cleanup
    logging.info("Cleaning System Backup Repository")
    cleanup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_system")

    # VM Cleanup
    logging.info("Cleaning VM Backup Repository")
    cleanup_repo(B2_REPO_VM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_vm")

    # Plex Cleanup
    logging.info("Cleaning Plex Backup Repository")
    cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_plex")

    # Print final status report
    print_status_report()

    # Finish up
    elapsed_time = time.time() - start_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    success_count = sum(
        1 for item in BACKUP_STATUS.values() if item["status"] == "success"
    )
    failed_count = sum(
        1 for item in BACKUP_STATUS.values() if item["status"] == "failed"
    )
    status_summary = (
        "SUCCESS"
        if failed_count == 0
        else "PARTIAL SUCCESS"
        if success_count > 0
        else "FAILED"
    )

    logging.info(
        f"UNIFIED BACKUP COMPLETED WITH {status_summary} AT {now} (took {elapsed_time:.1f} seconds)"
    )
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
