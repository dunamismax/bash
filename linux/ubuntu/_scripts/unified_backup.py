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
  The script automatically initializes repositories as needed, forces unlocks before backup,
  and enforces retention policies.

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 3.1.0
"""

import atexit
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET = "sawyer-backups"

# Determine the hostname to uniquely name the repositories
HOSTNAME = socket.gethostname()

# Restic repository strings for B2 follow the format: b2:bucket:directory
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "password"

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
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord theme styling.
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
    """
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Print final status report if the script is exiting gracefully
    if any(item["status"] != "pending" for item in BACKUP_STATUS.values()):
        print_status_report()


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
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


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Script is running with root privileges.")


# ------------------------------------------------------------------------------
# REPOSITORY OPERATIONS
# ------------------------------------------------------------------------------


def run_restic(
    repo: str, password: str, *args, check=True, capture_output=False, max_retries=3
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
            error_msg = e.stderr if hasattr(e, "stderr") else str(e)

            # Check for transient errors that we can retry
            transient_errors = [
                "connection reset by peer",
                "unexpected EOF",
                "timeout",
                "connection refused",
                "network error",
                "429 Too Many Requests",
            ]

            is_transient = (
                any(err in error_msg for err in transient_errors)
                if error_msg
                else False
            )

            if is_transient and retries < max_retries:
                retries += 1
                retry_delay = 5 * retries  # Exponential backoff
                logging.warning(
                    f"Transient error detected, retrying in {retry_delay} seconds ({retries}/{max_retries})..."
                )
                time.sleep(retry_delay)
                continue
            else:
                if retries > 0:
                    logging.error(f"Command failed after {retries} retries.")
                raise e


def is_local_repo(repo: str) -> bool:
    """
    Determine if the repository is local (i.e., not a B2 repo).

    Args:
        repo (str): The repository path to check

    Returns:
        bool: True if the repository is local, False otherwise
    """
    return not repo.startswith("b2:")


def ensure_repo_initialized(repo: str, password: str):
    """
    Ensures that a restic repository is initialized.
    For local repositories, check if the 'config' file exists.
    For B2 repositories, attempt a snapshots command.

    Args:
        repo (str): The repository path to check
        password (str): The repository password
    """
    logging.info(f"Ensuring repository '{repo}' is initialized...")

    if is_local_repo(repo):
        config_path = os.path.join(repo, "config")
        if os.path.exists(config_path):
            logging.info(f"Repository '{repo}' already initialized.")
            return
        else:
            logging.info(f"Repository '{repo}' not initialized. Initializing...")
            run_restic(repo, password, "init")
            logging.info(f"Repository '{repo}' successfully initialized.")
    else:
        try:
            # Use --no-lock to prevent this check from creating a lock itself
            run_restic(repo, password, "snapshots", "--no-lock", "--limit", "1")
            logging.info(f"Repository '{repo}' already initialized.")
        except subprocess.CalledProcessError:
            logging.info(f"Repository '{repo}' not initialized. Initializing...")
            run_restic(repo, password, "init")
            logging.info(f"Repository '{repo}' successfully initialized.")


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
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to force unlock repository: {e}")
        return False


# ------------------------------------------------------------------------------
# BACKUP OPERATIONS
# ------------------------------------------------------------------------------


def backup_repo(
    repo: str, password: str, source: str, excludes: list = None, task_name: str = None
):
    """
    Perform backup to a repository, with force unlock.

    Args:
        repo (str): The repository path for backup
        password (str): The repository password
        source (str or list): The source path(s) to backup
        excludes (list): Patterns to exclude from backup
        task_name (str): Name of the task for status tracking
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
        raise

    # Always force unlock the repository
    if not force_unlock_repo(repo, password):
        error_msg = "Failed to unlock repository before backup"
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        raise RuntimeError(error_msg)

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
                    run_restic(repo, password, *cmd_args)
                    success_msg = f"Backup completed successfully after retry in {time.time() - start_time:.1f} seconds"
                    logging.info(success_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": success_msg,
                        }
                except Exception as retry_e:
                    error_msg = f"Backup failed after retry: {str(retry_e)}"
                    logging.error(error_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": error_msg,
                        }
                    raise
            else:
                error_msg = f"Failed to unlock repository for retry after {elapsed_time:.1f} seconds"
                logging.error(error_msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": error_msg,
                    }
                raise RuntimeError(error_msg)
        else:
            error_msg = (
                f"Backup failed after {elapsed_time:.1f} seconds: {error_output}"
            )
            logging.error(error_msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
            raise e


def cleanup_repo(repo: str, password: str, retention_days: int, task_name: str = None):
    """
    Clean up old snapshots based on retention policy.
    Handles potential repository locks gracefully.

    Args:
        repo (str): The repository path to clean up
        password (str): The repository password
        retention_days (int): Days to keep snapshots
        task_name (str): Name of the task for status tracking
    """
    if task_name:
        BACKUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": "Cleanup in progress...",
        }

    # Ensure repository is initialized
    try:
        ensure_repo_initialized(repo, password)
    except Exception as e:
        error_msg = f"Failed to initialize repository for cleanup: {str(e)}"
        logging.error(error_msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        raise

    # Always force unlock the repository
    if not force_unlock_repo(repo, password):
        error_msg = "Failed to unlock repository before cleanup"
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
        raise RuntimeError(error_msg)

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
                    run_restic(
                        repo,
                        password,
                        "forget",
                        "--prune",
                        "--keep-within",
                        f"{retention_days}d",
                    )
                    success_msg = f"Cleanup completed successfully after retry in {time.time() - start_time:.1f} seconds"
                    logging.info(success_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": success_msg,
                        }
                except Exception as retry_e:
                    error_msg = f"Cleanup failed after retry: {str(retry_e)}"
                    logging.error(error_msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": error_msg,
                        }
                    raise
            else:
                error_msg = f"Failed to unlock repository for cleanup retry after {elapsed_time:.1f} seconds"
                logging.error(error_msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": error_msg,
                    }
                raise RuntimeError(error_msg)
        else:
            error_msg = (
                f"Cleanup failed after {elapsed_time:.1f} seconds: {error_output}"
            )
            logging.error(error_msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": error_msg}
            raise e


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
    }

    status_colors = {
        "success": NORD14,  # Green
        "failed": NORD11,  # Red
        "pending": NORD13,  # Yellow
        "in_progress": NORD8,  # Light blue
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

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)

    # Print system information
    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")

    # Force unlock all repositories before starting
    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # System Backup
    print_section("System Backup to Backblaze B2")
    try:
        backup_repo(
            B2_REPO_SYSTEM, RESTIC_PASSWORD, SYSTEM_SOURCE, SYSTEM_EXCLUDES, "system"
        )
    except Exception as e:
        logging.error(f"System backup failed: {e}")
        # Continue with other backups

    # VM Backup
    print_section("VM Backup to Backblaze B2")
    try:
        backup_repo(B2_REPO_VM, RESTIC_PASSWORD, VM_SOURCES, VM_EXCLUDES, "vm")
    except Exception as e:
        logging.error(f"VM backup failed: {e}")
        # Continue with other backups

    # Plex Backup
    print_section("Plex Media Server Backup to Backblaze B2")
    try:
        backup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, PLEX_SOURCES, PLEX_EXCLUDES, "plex")
    except Exception as e:
        logging.error(f"Plex backup failed: {e}")
        # Continue with other backups

    # Clean up old snapshots for all repositories
    print_section("Cleaning Up Old Snapshots (Retention Policy)")

    # System Cleanup
    logging.info("Cleaning System Backup Repository")
    try:
        cleanup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_system")
    except Exception as e:
        logging.error(f"System backup cleanup failed: {e}")

    # VM Cleanup
    logging.info("Cleaning VM Backup Repository")
    try:
        cleanup_repo(B2_REPO_VM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_vm")
    except Exception as e:
        logging.error(f"VM backup cleanup failed: {e}")

    # Plex Cleanup
    logging.info("Cleaning Plex Backup Repository")
    try:
        cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_plex")
    except Exception as e:
        logging.error(f"Plex backup cleanup failed: {e}")

    # Print final status report
    print_status_report()

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP COMPLETED AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
