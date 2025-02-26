#!/usr/bin/env python3
"""
Enhanced Unified Backup Script
------------------------------
Description:
  A comprehensive backup solution that performs three types of backups to Backblaze B2:
    1. System Backup - Backs up the entire system (/)
    2. VM Backup - Backs up libvirt virtual machine configurations and disk images
    3. Plex Backup - Backs up Plex Media Server configuration and application data

  Key Features:
    - Parallel backup processing for improved performance
    - Robust error handling with automatic recovery
    - Detailed status reporting with Nord-themed output
    - Disk space validation before backup operations
    - Rich progress indicators for all operations
    - Repository health checks and automatic repair
    - Email notification system for backup results (optional)

  Each backup is stored in a separate repository within the same B2 bucket.
  Repositories are named using the hostname for organization.

Usage:
  sudo ./enhanced_backup.py

Author: Your Name | License: MIT | Version: 4.0.0
"""

import atexit
import json
import logging
import os
import platform
import shutil
import signal
import smtplib
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Rich library for progress indicators
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    BarColumn,
)
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

# Unified repository password (use a strong, secure password)
RESTIC_PASSWORD = "12345678"

# Backup source directories and exclusion patterns
SYSTEM_SOURCE = "/"
SYSTEM_EXCLUDES = [
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
]

VM_SOURCES = ["/etc/libvirt", "/var/lib/libvirt"]
VM_EXCLUDES = []  # Customize as needed

PLEX_SOURCES = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]
PLEX_EXCLUDES = [
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
]

# Configuration parameters
RETENTION_DAYS = 7
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds
PARALLEL_BACKUPS = True  # Set to False to run backups sequentially
MIN_FREE_SPACE_GB = 5  # Minimum free space required in GB
CHECK_DISK_SPACE = True  # Set to True to enable disk space checking
MAX_WORKERS = 3  # Maximum number of parallel backup jobs

# Email notification settings (optional)
EMAIL_NOTIFICATIONS = False  # Set to True to enable email notifications
EMAIL_SERVER = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USER = "your-email@gmail.com"
EMAIL_PASSWORD = "your-app-password"
EMAIL_RECIPIENT = "recipient@example.com"

# Status tracking for reporting
BACKUP_STATUS = {
    "system": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
        "size_processed": 0,
    },
    "vm": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
        "size_processed": 0,
    },
    "plex": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
        "size_processed": 0,
    },
    "cleanup_system": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
    },
    "cleanup_vm": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
    },
    "cleanup_plex": {
        "status": "pending",
        "message": "",
        "start_time": None,
        "end_time": None,
    },
}

LOG_FILE = "/var/log/unified_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Dark background
NORD1 = "\033[38;2;59;66;82m"  # Dark foreground
NORD8 = "\033[38;2;136;192;208m"  # Light blue
NORD9 = "\033[38;2;129;161;193m"  # Blue
NORD10 = "\033[38;2;94;129;172m"  # Deep blue
NORD11 = "\033[38;2;191;97;106m"  # Red
NORD13 = "\033[38;2;235;203;139m"  # Yellow
NORD14 = "\033[38;2;163;190;140m"  # Green
NC = "\033[0m"  # Reset color

# Initialize Rich console
console = Console()


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """Custom formatter that applies Nord color theme to log messages."""

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
    """Configure logging with console and file handlers using Nord color theme."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Set up console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Set up file handler without colors
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        # Rotate log file if it's too large
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)  # Secure the log file
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logging.warning("Continuing with console logging only")

    return logger


def print_section(title: str):
    """Print a formatted section header with Nord styling."""
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
# Rich Progress Helper
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a rich progress spinner.

    Args:
        description (str): Description to display in the progress indicator
        func (callable): Function to run in the background
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of the function call
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


# ------------------------------------------------------------------------------
# Disk Space Validation
# ------------------------------------------------------------------------------
def check_free_space(path, required_gb=MIN_FREE_SPACE_GB):
    """
    Check if there's sufficient free space on the specified path.

    Args:
        path (str): Path to check for free space
        required_gb (float): Required free space in GB

    Returns:
        bool: True if sufficient space is available, False otherwise
    """
    try:
        if not CHECK_DISK_SPACE:
            return True

        # Find the mount point for the path
        mount_point = path
        while not os.path.ismount(mount_point):
            mount_point = os.path.dirname(mount_point)
            if mount_point == "/":
                break

        # Get disk usage statistics
        usage = shutil.disk_usage(mount_point)
        free_gb = usage.free / (1024**3)  # Convert bytes to GB

        if free_gb < required_gb:
            logging.error(
                f"Insufficient disk space on {mount_point}: "
                f"{free_gb:.2f}GB available, {required_gb}GB required"
            )
            return False

        logging.info(
            f"Sufficient disk space on {mount_point}: {free_gb:.2f}GB available"
        )
        return True
    except Exception as e:
        logging.warning(f"Failed to check disk space on {path}: {e}")
        # Don't fail the backup if we can't check the space
        return True


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
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


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """Perform cleanup tasks before exit."""
    logging.info("Performing cleanup tasks before exit.")
    if any(item["status"] != "pending" for item in BACKUP_STATUS.values()):
        print_status_report()

        if EMAIL_NOTIFICATIONS:
            try:
                send_email_notification()
            except Exception as e:
                logging.error(f"Failed to send email notification: {e}")


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Email Notification
# ------------------------------------------------------------------------------
def send_email_notification():
    """Send email notification with backup status."""
    if not EMAIL_NOTIFICATIONS:
        return

    # Create message
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_RECIPIENT

    # Determine overall status
    success_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "failed")
    overall_status = (
        "SUCCESS"
        if failed_count == 0
        else "PARTIAL SUCCESS"
        if success_count > 0
        else "FAILED"
    )

    msg["Subject"] = f"Backup Report for {HOSTNAME}: {overall_status}"

    # Create HTML content
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; }}
            .success {{ color: green; }}
            .failed {{ color: red; }}
            .pending {{ color: orange; }}
            .in_progress {{ color: blue; }}
            .skipped {{ color: gray; }}
        </style>
    </head>
    <body>
        <h2>Backup Report for {HOSTNAME}</h2>
        <p>Backup completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} with status: <strong>{overall_status}</strong></p>
        
        <h3>Backup Tasks</h3>
        <table>
            <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Message</th>
                <th>Duration</th>
            </tr>
    """

    # Add each backup task
    descriptions = {
        "system": "System Backup",
        "vm": "Virtual Machine Backup",
        "plex": "Plex Media Server Backup",
        "cleanup_system": "System Backup Cleanup",
        "cleanup_vm": "VM Backup Cleanup",
        "cleanup_plex": "Plex Backup Cleanup",
    }

    for task, data in BACKUP_STATUS.items():
        status = data["status"]
        msg_text = data["message"]
        task_desc = descriptions.get(task, task)

        # Calculate duration if available
        duration = ""
        if data.get("start_time") and data.get("end_time"):
            duration = f"{(data['end_time'] - data['start_time']):.1f}s"

        html += f"""
            <tr>
                <td>{task_desc}</td>
                <td class="{status}">{status.upper()}</td>
                <td>{msg_text}</td>
                <td>{duration}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    # Attach HTML content
    msg.attach(MIMEText(html, "html"))

    # Send email
    try:
        server = smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        logging.info("Email notification sent successfully")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")


# ------------------------------------------------------------------------------
# Dependency and Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies():
    """Check if required dependencies are installed."""
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
    """Check if script is running with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


def validate_configuration():
    """Validate backup configuration and paths."""
    problems = []

    # Check if source paths exist
    if not os.path.exists(SYSTEM_SOURCE):
        problems.append(f"System source path does not exist: {SYSTEM_SOURCE}")

    for path in VM_SOURCES:
        if not os.path.exists(path):
            problems.append(f"VM source path does not exist: {path}")

    for path in PLEX_SOURCES:
        if not os.path.exists(path):
            problems.append(f"Plex source path does not exist: {path}")

    # Check if B2 credentials are set
    if B2_ACCOUNT_ID == "12345678" or B2_ACCOUNT_KEY == "12345678":
        problems.append("B2 credentials appear to be default values")

    # Check if restic password is set
    if RESTIC_PASSWORD == "12345678":
        problems.append("Restic password appears to be a default value")

    # Report problems
    if problems:
        print_section("Configuration Problems Detected")
        for problem in problems:
            logging.warning(problem)

        # Don't exit, just warn
        logging.warning("Continuing despite configuration issues.")

    return len(problems) == 0


# ------------------------------------------------------------------------------
# Repository Health Check and Repair
# ------------------------------------------------------------------------------
def check_and_repair_repo(repo: str, password: str) -> bool:
    """
    Check repository integrity and attempt repair if issues are found.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        bool: True if repository is healthy or was repaired, False otherwise
    """
    if not is_repo_initialized(repo, password):
        logging.warning(
            f"Repository '{repo}' is not initialized. Skipping health check."
        )
        return False

    logging.info(f"Checking repository integrity: '{repo}'")
    try:
        # Try a basic check operation
        run_restic(
            repo, password, "check", "--read-data-subset=1%", capture_output=True
        )
        logging.info(f"Repository '{repo}' appears to be healthy.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        logging.warning(f"Repository integrity issues detected: {err_msg}")

        # Try to repair
        try:
            logging.info(f"Attempting to repair repository '{repo}'")
            run_restic(repo, password, "repair", "index", capture_output=True)
            logging.info(f"Repository repair completed for '{repo}'")

            # Verify the repair was successful
            run_restic(
                repo, password, "check", "--read-data-subset=1%", capture_output=True
            )
            logging.info(f"Repository '{repo}' is now healthy after repair.")
            return True
        except subprocess.CalledProcessError as repair_e:
            repair_err = repair_e.stderr or str(repair_e)
            logging.error(f"Repository repair failed: {repair_err}")
            return False


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
    Run a restic command with proper environment and error handling.

    Args:
        repo (str): Repository path
        password (str): Repository password
        *args: Command arguments for restic
        check (bool): Whether to check for command errors
        capture_output (bool): Whether to capture and return command output
        max_retries (int): Maximum number of retries for transient errors

    Returns:
        subprocess.CompletedProcess or None: Command result if capture_output=True, None otherwise

    Raises:
        subprocess.CalledProcessError: If command fails and check=True
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(cmd)}")

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

            # Check for non-fatal conditions
            if "init" in args and "already initialized" in err_msg:
                logging.info("Repository already initialized, continuing.")
                return None

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
    Check if a repository is initialized.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        bool: True if repository is initialized, False otherwise
    """
    logging.info(f"Checking repository '{repo}'...")
    try:
        run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )
        logging.info(f"Repository '{repo}' is initialized.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if any(
            msg in err_msg for msg in ["already initialized", "repository master key"]
        ):
            logging.info(f"Repository '{repo}' is initialized but had access issues.")
            return True
        logging.info(f"Repository '{repo}' is not initialized.")
        return False


def ensure_repo_initialized(repo: str, password: str):
    """
    Ensure a repository is initialized, initializing it if necessary.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        bool: True if repository is initialized, False on failure

    Raises:
        RuntimeError: If repository initialization fails
    """
    logging.info(f"Ensuring repository '{repo}' is initialized...")
    if is_repo_initialized(repo, password):
        return True

    try:
        run_restic(repo, password, "init")
        logging.info(f"Repository '{repo}' successfully initialized.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if "already initialized" in err_msg:
            logging.info(f"Repository '{repo}' is already initialized (during init).")
            return True
        logging.error(f"Failed to initialize repository: {err_msg}")
        raise RuntimeError(f"Repo init failed: {err_msg}")


def force_unlock_repo(repo: str, password: str) -> bool:
    """
    Force unlock a repository, removing any stale locks.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        bool: True if unlock was successful, False otherwise
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


def get_repo_stats(repo: str, password: str):
    """
    Get repository statistics including snapshot count, size, and latest snapshot.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        dict: Repository statistics
    """
    stats = {"snapshots": 0, "total_size": "unknown", "latest_snapshot": "never"}

    if not is_repo_initialized(repo, password):
        return stats

    # Get snapshots
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []
        stats["snapshots"] = len(snapshots)
        if snapshots:
            latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
            stats["latest_snapshot"] = latest.get("time", "unknown")[:19]
    except Exception as e:
        logging.warning(f"Could not get snapshot info: {e}")

    # Get repo size
    try:
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        repo_stats = json.loads(result.stdout) if result and result.stdout else {}
        total = repo_stats.get("total_size", 0)
        stats["total_size"] = format_size(total)
    except Exception as e:
        logging.warning(f"Could not get repo size info: {e}")

    return stats


def format_size(size_bytes):
    """Format byte size into human-readable string."""
    if size_bytes == 0:
        return "0 B"

    names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(names) - 1:
        size_bytes /= 1024
        i += 1

    return f"{size_bytes:.2f} {names[i]}"


# ------------------------------------------------------------------------------
# Backup & Cleanup Operations (with Rich Progress)
# ------------------------------------------------------------------------------
def backup_repo(
    repo: str, password: str, source, excludes: list = None, task_name: str = None
) -> bool:
    """
    Perform a backup operation with detailed progress and status tracking.

    Args:
        repo (str): Repository path
        password (str): Repository password
        source: Source path(s) to backup
        excludes (list): Exclusion patterns
        task_name (str): Task name for status tracking

    Returns:
        bool: True if backup was successful, False otherwise
    """
    if excludes is None:
        excludes = []

    if task_name:
        BACKUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": "Backup in progress...",
            "start_time": time.time(),
            "end_time": None,
            "size_processed": 0,
        }

    # Check free space before backup
    temp_dir = os.environ.get("TMPDIR", "/tmp")
    if not check_free_space(temp_dir):
        msg = f"Insufficient disk space for backup operation."
        logging.error(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }
        return False

    # Initialize and unlock repository
    try:
        ensure_repo_initialized(repo, password)
    except Exception as e:
        msg = f"Repo init failed: {e}"
        logging.error(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }
        return False

    if not force_unlock_repo(repo, password):
        msg = "Failed to unlock repository before backup."
        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }
        return False

    # Build backup command
    cmd_args = ["backup"]
    if isinstance(source, list):
        cmd_args.extend(source)
    else:
        cmd_args.append(source)

    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])

    # Check repository health before backup
    check_and_repair_repo(repo, password)

    # Perform backup
    start = time.time()
    try:
        result = run_with_progress(
            "Performing backup...",
            run_restic,
            repo,
            password,
            *cmd_args,
            capture_output=True,
        )

        elapsed = time.time() - start

        # Extract processed data size from output
        size_processed = 0
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if "processed" in line and "files" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "processed":
                            try:
                                size_processed = float(parts[i - 1])
                                size_unit = parts[i - 2].lower()
                                if "kb" in size_unit:
                                    size_processed *= 1024
                                elif "mb" in size_unit:
                                    size_processed *= 1024 * 1024
                                elif "gb" in size_unit:
                                    size_processed *= 1024 * 1024 * 1024
                                elif "tb" in size_unit:
                                    size_processed *= 1024 * 1024 * 1024 * 1024
                            except (ValueError, IndexError):
                                pass

        msg = f"Backup completed in {elapsed:.1f} seconds."
        logging.info(msg)

        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "success",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
                "size_processed": size_processed,
            }

        # Log summary information
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(
                    x in line
                    for x in ["Files:", "Added to the", "processed", "snapshot"]
                ):
                    logging.info(f"Summary: {line.strip()}")

        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"

        # Handle repository lock issues
        if "repository is already locked" in err_output:
            logging.warning("Backup failed due to lock. Retrying after force unlock...")

            if force_unlock_repo(repo, password):
                try:
                    result = run_with_progress(
                        "Retrying backup...",
                        run_restic,
                        repo,
                        password,
                        *cmd_args,
                        capture_output=True,
                    )

                    total = time.time() - start
                    msg = f"Backup completed after retry in {total:.1f} seconds."
                    logging.info(msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": msg,
                            "start_time": BACKUP_STATUS[task_name]["start_time"],
                            "end_time": time.time(),
                        }

                    return True

                except Exception as retry_e:
                    msg = f"Backup failed after retry: {retry_e}"
                    logging.error(msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": msg,
                            "start_time": BACKUP_STATUS[task_name]["start_time"],
                            "end_time": time.time(),
                        }

                    return False
            else:
                msg = f"Failed to unlock repo after {elapsed:.1f} seconds."
                logging.error(msg)

                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": msg,
                        "start_time": BACKUP_STATUS[task_name]["start_time"],
                        "end_time": time.time(),
                    }

                return False
        else:
            msg = f"Backup failed after {elapsed:.1f} seconds: {err_output}"
            logging.error(msg)

            if task_name:
                BACKUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": msg,
                    "start_time": BACKUP_STATUS[task_name]["start_time"],
                    "end_time": time.time(),
                }

            return False


def cleanup_repo(
    repo: str, password: str, retention_days: int, task_name: str = None
) -> bool:
    """
    Clean up old snapshots according to retention policy.

    Args:
        repo (str): Repository path
        password (str): Repository password
        retention_days (int): Days to keep snapshots
        task_name (str): Task name for status tracking

    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    if task_name:
        BACKUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": "Cleanup in progress...",
            "start_time": time.time(),
            "end_time": None,
        }

    # Check if repository is initialized
    try:
        if not is_repo_initialized(repo, password):
            msg = f"Repository '{repo}' not initialized. Skipping cleanup."
            logging.warning(msg)

            if task_name:
                BACKUP_STATUS[task_name] = {
                    "status": "skipped",
                    "message": msg,
                    "start_time": BACKUP_STATUS[task_name]["start_time"],
                    "end_time": time.time(),
                }

            return False
    except Exception as e:
        msg = f"Repo check failed for cleanup: {e}"
        logging.error(msg)

        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }

        return False

    # Unlock repository
    if not force_unlock_repo(repo, password):
        msg = "Failed to unlock repository before cleanup."

        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "failed",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }

        return False

    # Perform cleanup
    start = time.time()
    try:
        result = run_with_progress(
            "Performing cleanup...",
            run_restic,
            repo,
            password,
            "forget",
            "--prune",
            "--keep-within",
            f"{retention_days}d",
            capture_output=True,
        )

        elapsed = time.time() - start
        msg = f"Cleanup completed in {elapsed:.1f} seconds."
        logging.info(msg)

        if task_name:
            BACKUP_STATUS[task_name] = {
                "status": "success",
                "message": msg,
                "start_time": BACKUP_STATUS[task_name]["start_time"],
                "end_time": time.time(),
            }

        # Log summary information
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(
                    x in line for x in ["snapshots", "removing", "remaining", "deleted"]
                ):
                    logging.info(f"Cleanup: {line.strip()}")

        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"

        # Handle repository lock issues
        if "repository is already locked" in err_output:
            logging.warning(
                "Cleanup failed due to lock. Retrying after force unlock..."
            )

            if force_unlock_repo(repo, password):
                try:
                    result = run_with_progress(
                        "Retrying cleanup...",
                        run_restic,
                        repo,
                        password,
                        "forget",
                        "--prune",
                        "--keep-within",
                        f"{retention_days}d",
                        capture_output=True,
                    )

                    total = time.time() - start
                    msg = f"Cleanup completed after retry in {total:.1f} seconds."
                    logging.info(msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "success",
                            "message": msg,
                            "start_time": BACKUP_STATUS[task_name]["start_time"],
                            "end_time": time.time(),
                        }

                    return True

                except Exception as retry_e:
                    msg = f"Cleanup failed after retry: {retry_e}"
                    logging.error(msg)

                    if task_name:
                        BACKUP_STATUS[task_name] = {
                            "status": "failed",
                            "message": msg,
                            "start_time": BACKUP_STATUS[task_name]["start_time"],
                            "end_time": time.time(),
                        }

                    return False
            else:
                msg = f"Failed to unlock repo for cleanup after {elapsed:.1f} seconds."
                logging.error(msg)

                if task_name:
                    BACKUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": msg,
                        "start_time": BACKUP_STATUS[task_name]["start_time"],
                        "end_time": time.time(),
                    }

                return False
        else:
            msg = f"Cleanup failed after {elapsed:.1f} seconds: {err_output}"
            logging.error(msg)

            if task_name:
                BACKUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": msg,
                    "start_time": BACKUP_STATUS[task_name]["start_time"],
                    "end_time": time.time(),
                }

            return False


# ------------------------------------------------------------------------------
# Status Reporting
# ------------------------------------------------------------------------------
def print_status_report():
    """Print a detailed status report with rich formatting."""
    print_section("Backup Status Report")

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
        "system": "System Backup",
        "vm": "Virtual Machine Backup",
        "plex": "Plex Media Server Backup",
        "cleanup_system": "System Backup Cleanup",
        "cleanup_vm": "VM Backup Cleanup",
        "cleanup_plex": "Plex Backup Cleanup",
    }

    # Create a rich table for console output
    if not DISABLE_COLORS and "TERM" in os.environ:
        table = Table(title="Backup Status Summary")
        table.add_column("Task", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Duration", style="magenta")
        table.add_column("Message")

        for task, data in BACKUP_STATUS.items():
            status = data["status"]
            msg = data["message"]
            task_desc = descriptions.get(task, task)

            # Calculate duration if available
            duration = "N/A"
            if data.get("start_time") and data.get("end_time"):
                elapsed = data["end_time"] - data["start_time"]
                duration = f"{elapsed:.1f}s"

            # Add row with appropriate styling
            status_style = {
                "success": "green",
                "failed": "red",
                "pending": "yellow",
                "in_progress": "blue",
                "skipped": "dim",
            }.get(status, "")

            table.add_row(task_desc, status.upper(), duration, msg, style=status_style)

        console.print(table)

    # Also log to traditional logging for the log file
    for task, data in BACKUP_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)

        # Calculate duration for logging
        duration = ""
        if data.get("start_time") and data.get("end_time"):
            elapsed = data["end_time"] - data["start_time"]
            duration = f" (took {elapsed:.1f}s)"

        if not DISABLE_COLORS:
            icon = icons[status]
            color = colors[status]
            logging.info(
                f"{color}{icon} {task_desc}: {status.upper()}{NC}{duration} - {msg}"
            )
        else:
            logging.info(
                f"{icons[status]} {task_desc}: {status.upper()}{duration} - {msg}"
            )

    # Print summary
    success_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "failed")
    summary = (
        "SUCCESS"
        if failed_count == 0
        else "PARTIAL SUCCESS"
        if success_count > 0
        else "FAILED"
    )

    if not DISABLE_COLORS:
        summary_color = (
            NORD14 if failed_count == 0 else NORD13 if success_count > 0 else NORD11
        )
        logging.info(f"Overall status: {summary_color}{summary}{NC}")
    else:
        logging.info(f"Overall status: {summary}")


def print_repository_info():
    """Print detailed information about all repositories."""
    print_section("Repository Information")

    repos = [("System", B2_REPO_SYSTEM), ("VM", B2_REPO_VM), ("Plex", B2_REPO_PLEX)]

    # Use Rich table for console output if colors are enabled
    if not DISABLE_COLORS and "TERM" in os.environ:
        table = Table(title="Repository Information")
        table.add_column("Repository", style="cyan")
        table.add_column("Snapshots", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Latest Snapshot")

        for name, repo in repos:
            try:
                stats = get_repo_stats(repo, RESTIC_PASSWORD)
                if stats["snapshots"] > 0:
                    table.add_row(
                        name,
                        str(stats["snapshots"]),
                        stats["total_size"],
                        stats["latest_snapshot"],
                    )
                else:
                    table.add_row(name, "0", "N/A", "Never", style="dim")
            except Exception as e:
                table.add_row(name, "Error", "Error", str(e), style="red")

        console.print(table)

    # Also log to traditional logging for the log file
    for name, repo in repos:
        try:
            stats = get_repo_stats(repo, RESTIC_PASSWORD)
            logging.info(f"{name} Repository: {repo}")
            if stats["snapshots"] > 0:
                logging.info(f"  • Snapshots: {stats['snapshots']}")
                logging.info(f"  • Size: {stats['total_size']}")
                logging.info(f"  • Latest snapshot: {stats['latest_snapshot']}")
            else:
                logging.info("  • No snapshots found")
        except Exception as e:
            logging.warning(f"Could not get info for {name} repo: {e}")


# ------------------------------------------------------------------------------
# Parallel Backup Processing
# ------------------------------------------------------------------------------
def run_parallel_backups():
    """Run backup processes in parallel using ThreadPoolExecutor."""
    logging.info("Starting parallel backup operations...")

    backup_tasks = [
        {
            "name": "system",
            "repo": B2_REPO_SYSTEM,
            "source": SYSTEM_SOURCE,
            "excludes": SYSTEM_EXCLUDES,
            "description": "System Backup",
        },
        {
            "name": "vm",
            "repo": B2_REPO_VM,
            "source": VM_SOURCES,
            "excludes": VM_EXCLUDES,
            "description": "VM Backup",
        },
        {
            "name": "plex",
            "repo": B2_REPO_PLEX,
            "source": PLEX_SOURCES,
            "excludes": PLEX_EXCLUDES,
            "description": "Plex Backup",
        },
    ]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all backup tasks
        futures = {}
        for task in backup_tasks:
            print_section(f"Starting {task['description']}")
            future = executor.submit(
                backup_repo,
                task["repo"],
                RESTIC_PASSWORD,
                task["source"],
                task["excludes"],
                task["name"],
            )
            futures[future] = task["name"]

        # Wait for all tasks to complete
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                # Get the result (and propagate any exceptions)
                future.result()
                print_section(f"Completed {task_name}")
            except Exception as e:
                logging.error(f"Unhandled exception in {task_name}: {e}")
                BACKUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"Unhandled exception: {e}",
                    "start_time": BACKUP_STATUS[task_name].get(
                        "start_time", time.time()
                    ),
                    "end_time": time.time(),
                }


def run_sequential_backups():
    """Run backup processes sequentially."""
    logging.info("Starting sequential backup operations...")

    print_section("System Backup to Backblaze B2")
    backup_repo(
        B2_REPO_SYSTEM, RESTIC_PASSWORD, SYSTEM_SOURCE, SYSTEM_EXCLUDES, "system"
    )

    print_section("VM Backup to Backblaze B2")
    backup_repo(B2_REPO_VM, RESTIC_PASSWORD, VM_SOURCES, VM_EXCLUDES, "vm")

    print_section("Plex Media Server Backup to Backblaze B2")
    backup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, PLEX_SOURCES, PLEX_EXCLUDES, "plex")


def run_parallel_cleanups():
    """Run cleanup processes in parallel using ThreadPoolExecutor."""
    logging.info("Starting parallel cleanup operations...")

    cleanup_tasks = [
        {
            "name": "cleanup_system",
            "repo": B2_REPO_SYSTEM,
            "description": "System Backup Cleanup",
        },
        {
            "name": "cleanup_vm",
            "repo": B2_REPO_VM,
            "description": "VM Backup Cleanup",
        },
        {
            "name": "cleanup_plex",
            "repo": B2_REPO_PLEX,
            "description": "Plex Backup Cleanup",
        },
    ]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all cleanup tasks
        futures = {}
        for task in cleanup_tasks:
            print_section(f"Starting {task['description']}")
            future = executor.submit(
                cleanup_repo,
                task["repo"],
                RESTIC_PASSWORD,
                RETENTION_DAYS,
                task["name"],
            )
            futures[future] = task["name"]

        # Wait for all tasks to complete
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                # Get the result (and propagate any exceptions)
                future.result()
                print_section(f"Completed {task_name}")
            except Exception as e:
                logging.error(f"Unhandled exception in {task_name}: {e}")
                BACKUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"Unhandled exception: {e}",
                    "start_time": BACKUP_STATUS[task_name].get(
                        "start_time", time.time()
                    ),
                    "end_time": time.time(),
                }


def run_sequential_cleanups():
    """Run cleanup processes sequentially."""
    logging.info("Starting sequential cleanup operations...")

    print_section("Cleaning System Backup Repository")
    cleanup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_system")

    print_section("Cleaning VM Backup Repository")
    cleanup_repo(B2_REPO_VM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_vm")

    print_section("Cleaning Plex Backup Repository")
    cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_plex")


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    """Main entry point of the script."""
    setup_logging()
    check_dependencies()
    check_root()
    validate_configuration()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Print fancy header with rich
    if not DISABLE_COLORS and "TERM" in os.environ:
        console.print(
            Panel.fit(
                f"[bold blue]ENHANCED UNIFIED BACKUP[/bold blue]\n"
                f"[cyan]Started at: {now}[/cyan]\n"
                f"[cyan]Hostname: {HOSTNAME}[/cyan]",
                border_style="blue",
                padding=(1, 2),
            )
        )

    logging.info("=" * 80)
    logging.info(f"ENHANCED UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)

    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Platform: {platform.platform()}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")

    print_repository_info()

    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # Run backups (parallel or sequential)
    if PARALLEL_BACKUPS:
        run_parallel_backups()
    else:
        run_sequential_backups()

    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    # Run cleanups (parallel or sequential)
    if PARALLEL_BACKUPS:
        run_parallel_cleanups()
    else:
        run_sequential_cleanups()

    # Print final status report
    print_status_report()

    # Calculate runtime and print summary
    elapsed = time.time() - start_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "failed")
    summary = (
        "SUCCESS"
        if failed_count == 0
        else "PARTIAL SUCCESS"
        if success_count > 0
        else "FAILED"
    )

    # Print fancy footer with rich
    if not DISABLE_COLORS and "TERM" in os.environ:
        status_color = (
            "green" if failed_count == 0 else "yellow" if success_count > 0 else "red"
        )
        console.print(
            Panel.fit(
                f"[bold {status_color}]BACKUP COMPLETED WITH {summary}[/bold {status_color}]\n"
                f"[cyan]Finished at: {now}[/cyan]\n"
                f"[cyan]Total duration: {elapsed:.1f} seconds[/cyan]",
                border_style=status_color,
                padding=(1, 2),
            )
        )

    logging.info("=" * 80)
    logging.info(
        f"ENHANCED UNIFIED BACKUP COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)"
    )
    logging.info("=" * 80)

    # Send email notification if enabled
    if EMAIL_NOTIFICATIONS:
        try:
            send_email_notification()
        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
