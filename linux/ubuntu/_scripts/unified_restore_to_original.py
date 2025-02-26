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
    - First, each repository’s latest snapshot is restored into a temporary directory.
    - Then, the files are moved (using rsync) from the temporary location to their exact
      original paths on the system, preserving file permissions and metadata.

Usage:
  sudo ./unified_restore_to_original.py

Author: Your Name | License: MIT | Version: 1.0.0
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

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

# Maximum retries and delay (for restic operations)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds

# Global restore status for reporting
RESTORE_STATUS = {
    "system": {"status": "pending", "message": ""},
    "vm": {"status": "pending", "message": ""},
    "plex": {"status": "pending", "message": ""},
}

LOG_FILE = "/var/log/unified_restore_to_original.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

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
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
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
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
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
    logging.info("Performing cleanup tasks before exit.")
    if any(item["status"] != "pending" for item in RESTORE_STATUS.values()):
        print_status_report()


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency and Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies():
    # Ensure both restic and rsync are available.
    dependencies = ["restic", "rsync"]
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
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


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
            if "init" in args and "already initialized" in err_msg:
                logging.info("Repository already initialized, continuing.")
                return None
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


def get_latest_snapshot_id(repo: str, password: str) -> str:
    """
    Retrieve the most recent snapshot ID from the repository.
    Returns the snapshot's short_id if available, otherwise the id.
    """
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []
        if not snapshots:
            logging.error(f"No snapshots found in repository '{repo}'.")
            return ""
        # Sort snapshots by time (newest first)
        latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
        snapshot_id = latest.get("short_id") or latest.get("id", "")
        logging.info(f"Latest snapshot for '{repo}' is '{snapshot_id}'.")
        return snapshot_id
    except Exception as e:
        logging.error(f"Error retrieving latest snapshot from '{repo}': {e}")
        return ""


def force_unlock_repo(repo: str, password: str) -> bool:
    logging.warning(f"Forcing unlock of repository '{repo}'")
    try:
        # A simple check to see if the repo is initialized.
        result = run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )
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


# ------------------------------------------------------------------------------
# Restore Operations (to Original Locations using a Temporary Directory and rsync)
# ------------------------------------------------------------------------------
def restore_repo_to_original(repo: str, password: str, task_name: str) -> bool:
    RESTORE_STATUS[task_name] = {
        "status": "in_progress",
        "message": "Restore in progress...",
    }
    snapshot_id = get_latest_snapshot_id(repo, password)
    if not snapshot_id:
        msg = f"No snapshots found for repository '{repo}'."
        logging.error(msg)
        RESTORE_STATUS[task_name] = {"status": "failed", "message": msg}
        return False

    # Create a temporary directory for the restore operation.
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    logging.info(f"Created temporary restore directory: {temp_dir}")

    # Run restic restore into the temporary directory.
    cmd_args = ["restore", snapshot_id, "--target", temp_dir]
    start = time.time()
    try:
        run_with_progress(
            "Restoring backup to temporary directory...",
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
        RESTORE_STATUS[task_name] = {"status": "failed", "message": msg}
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Restic creates a folder named "restored-<snapshot_id>" inside the target directory.
    restored_dir = os.path.join(temp_dir, "restored-" + snapshot_id)
    if not os.path.exists(restored_dir):
        msg = f"Restored directory '{restored_dir}' does not exist."
        logging.error(msg)
        RESTORE_STATUS[task_name] = {"status": "failed", "message": msg}
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Use rsync to copy files from the temporary restore location to the system root (/)
    rsync_cmd = ["rsync", "-a", "--delete", restored_dir + "/", "/"]
    logging.info(f"Running rsync command: {' '.join(rsync_cmd)}")
    try:
        subprocess.run(rsync_cmd, check=True)
        elapsed_rsync = time.time() - start
        msg = f"Rsync completed in {elapsed_rsync:.1f} seconds; files restored to original locations."
        logging.info(msg)
        RESTORE_STATUS[task_name] = {"status": "success", "message": msg}
    except subprocess.CalledProcessError as e:
        elapsed_rsync = time.time() - start
        err_output = e.stderr or "Unknown error"
        msg = f"Rsync failed after {elapsed_rsync:.1f} seconds: {err_output}"
        logging.error(msg)
        RESTORE_STATUS[task_name] = {"status": "failed", "message": msg}
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Clean up the temporary restore directory.
    try:
        shutil.rmtree(temp_dir)
        logging.info(f"Temporary restore directory '{temp_dir}' removed.")
    except Exception as e:
        logging.warning(f"Failed to remove temporary directory '{temp_dir}': {e}")

    return True


# ------------------------------------------------------------------------------
# Status Reporting
# ------------------------------------------------------------------------------
def print_status_report():
    print_section("Restore Status Report")
    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
    }
    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
    }
    descriptions = {
        "system": "System Restore",
        "vm": "VM Restore",
        "plex": "Plex Restore",
    }
    for task, data in RESTORE_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)
        if not DISABLE_COLORS:
            icon = icons.get(status, "?")
            color = colors.get(status, "")
            logging.info(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")
        else:
            logging.info(
                f"{icons.get(status, '?')} {task_desc}: {status.upper()} - {msg}"
            )


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED RESTORE TO ORIGINAL LOCATIONS STARTED AT {now}")
    logging.info("=" * 80)

    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")

    # Optionally force-unlock repositories before restore
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    print_section("Restoring System Backup to Original Locations")
    restore_repo_to_original(B2_REPO_SYSTEM, RESTIC_PASSWORD, "system")

    print_section("Restoring VM Backup to Original Locations")
    restore_repo_to_original(B2_REPO_VM, RESTIC_PASSWORD, "vm")

    print_section("Restoring Plex Backup to Original Locations")
    restore_repo_to_original(B2_REPO_PLEX, RESTIC_PASSWORD, "plex")

    print_status_report()
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
    logging.info("=" * 80)
    logging.info(
        f"UNIFIED RESTORE TO ORIGINAL COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)"
    )
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
