#!/usr/bin/env python3
"""
Unified Restore to Original Locations Script (Simplified)
-----------------------------------------------------------
Description:
  This script retrieves the latest snapshot from three restic repositories stored
  on Backblaze B2 and restores the files directly to their original locations on
  an Ubuntu system. It handles three backup types:
    1. System Backup – Contains a full system backup.
    2. VM Backup – Contains virtual machine configurations and disk images.
    3. Plex Backup – Contains Plex Media Server configuration and data.

  The restore process is:
    - Run restic to restore the latest snapshot into a temporary directory.
    - Recursively copy the restored files from the temporary directory to the root
      ("/") of the system, preserving file metadata.
    - Verify that critical files exist after restoration.

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
import tempfile
import time
from datetime import datetime
from pathlib import Path

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

# Critical paths to verify after restore
CRITICAL_SYSTEM_PATHS = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM_PATHS = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX_PATHS = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

# Maximum retries for restic operations
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds

# Global restore status for reporting
RESTORE_STATUS = {
    "system": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
    "vm": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
    "plex": {"status": "pending", "message": "", "files_restored": 0, "snapshot": ""},
}

LOG_FILE = "/var/log/unified_restore_to_original.log"


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
def setup_logging() -> None:
    """Set up logging to console and file (with simple log rotation)."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")


def print_section(title: str) -> None:
    """Print a section header to the log and console."""
    border = "=" * 80
    logging.info(border)
    logging.info(f"  {title}")
    logging.info(border)


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    logging.info("Performing cleanup tasks before exit.")
    for path in Path(tempfile.gettempdir()).glob("restic_restore_*"):
        if path.is_dir():
            logging.info(f"Removing temporary directory: {path}")
            shutil.rmtree(path, ignore_errors=True)


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency and Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies() -> None:
    """Check that required dependencies exist."""
    logging.info("Checking required dependencies...")
    if not shutil.which("restic"):
        logging.error("Missing required dependency: restic")
        sys.exit(1)


def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


def check_free_space(temp_dir: str, required_gb: int = 10) -> bool:
    """Check that there is sufficient free space in the specified directory."""
    try:
        stat = os.statvfs(temp_dir)
        free_space_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)
        if free_space_gb < required_gb:
            logging.error(
                f"Low disk space: Only {free_space_gb:.1f} GB free; {required_gb} GB required."
            )
            return False
        return True
    except Exception as e:
        logging.warning(f"Could not check free space on {temp_dir}: {e}")
        return True


# ------------------------------------------------------------------------------
# Restic Repository Operations
# ------------------------------------------------------------------------------
def run_restic(
    repo: str, password: str, *args, capture_output: bool = False
) -> subprocess.CompletedProcess:
    """Run a restic command with retry logic."""
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(cmd)}")
    retries = 0
    while retries <= MAX_RETRIES:
        try:
            result = subprocess.run(
                cmd,
                env=env,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr or str(e)
            transient = any(
                term in err_msg.lower()
                for term in ["timeout", "connection", "temporarily unavailable"]
            )
            if transient and retries < MAX_RETRIES:
                retries += 1
                delay = RETRY_DELAY_BASE * (2 ** (retries - 1))
                logging.warning(
                    f"Transient error; retrying in {delay} seconds... (attempt {retries})"
                )
                time.sleep(delay)
                continue
            logging.error(f"Restic command failed: {err_msg}")
            raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot_id(repo: str, password: str) -> (str, str):
    """Get the latest snapshot ID and its timestamp from a repository."""
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        if not snapshots:
            logging.error(f"No snapshots found in repository '{repo}'.")
            return "", ""
        latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
        snapshot_id = latest.get("short_id") or latest.get("id", "")
        snapshot_time = latest.get("time", "")[:19]
        logging.info(
            f"Latest snapshot for '{repo}' is '{snapshot_id}' from {snapshot_time}."
        )
        return snapshot_id, snapshot_time
    except Exception as e:
        logging.error(f"Error retrieving latest snapshot from '{repo}': {e}")
        return "", ""


def force_unlock_repo(repo: str, password: str) -> bool:
    """Force unlock a restic repository by removing stale locks."""
    logging.info(f"Forcing unlock of repository '{repo}'")
    try:
        # Try listing snapshots (ignoring locks)
        run_restic(
            repo, password, "snapshots", "--no-lock", "--json", capture_output=True
        )
        # Remove locks
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


def format_size(size_bytes: int) -> str:
    """Convert a byte count into a human-readable format."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {units[i]}"


def get_repo_stats(repo: str, password: str) -> dict:
    """Retrieve simple statistics about the repository."""
    stats = {
        "snapshots": 0,
        "total_size": "unknown",
        "latest_snapshot": "never",
        "files": 0,
    }
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        stats["snapshots"] = len(snapshots)
        if snapshots:
            latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
            stats["latest_snapshot"] = latest.get("time", "unknown")[:19]
            # Get stats from latest snapshot
            snapshot_id = latest.get("short_id") or latest.get("id", "")
            try:
                result = run_restic(
                    repo, password, "stats", snapshot_id, "--json", capture_output=True
                )
                snap_stats = json.loads(result.stdout) if result.stdout else {}
                stats["files"] = snap_stats.get("total_file_count", 0)
            except Exception:
                pass
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        repo_stats = json.loads(result.stdout) if result.stdout else {}
        stats["total_size"] = format_size(repo_stats.get("total_size", 0))
    except Exception as e:
        logging.warning(f"Could not get repository stats: {e}")
    return stats


# ------------------------------------------------------------------------------
# File Copy (Replacement for rsync)
# ------------------------------------------------------------------------------
def copy_tree(src: str, dst: str) -> int:
    """
    Recursively copy files from src to dst.
    Returns the number of files copied.
    """
    files_copied = 0
    for root, _, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel_path) if rel_path != "." else dst
        os.makedirs(dest_dir, exist_ok=True)
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(dest_dir, file)
            shutil.copy2(src_file, dst_file)
            files_copied += 1
    return files_copied


# ------------------------------------------------------------------------------
# Restore Operation
# ------------------------------------------------------------------------------
def restore_repo_to_original(
    repo: str, password: str, task_name: str, critical_paths: list = None
) -> bool:
    """
    Restore a repository:
      - Retrieve the latest snapshot.
      - Run restic to restore into a temporary directory.
      - Recursively copy files from the temporary directory to the root directory.
      - Verify that all critical paths exist.
    """
    if critical_paths is None:
        critical_paths = []
    RESTORE_STATUS[task_name] = {
        "status": "in_progress",
        "message": "Restore in progress...",
        "files_restored": 0,
        "snapshot": "",
    }

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
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    logging.info(f"Created temporary directory: {temp_dir}")

    if not check_free_space(temp_dir):
        msg = "Insufficient disk space for restore."
        logging.error(msg)
        RESTORE_STATUS[task_name]["message"] = msg
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Run restic restore into temporary directory
    logging.info(f"Restoring snapshot {snapshot_id} from {repo} into {temp_dir}")
    try:
        run_restic(
            repo,
            password,
            "restore",
            snapshot_id,
            "--target",
            temp_dir,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        msg = f"Restic restore failed: {e.stderr or str(e)}"
        logging.error(msg)
        RESTORE_STATUS[task_name]["status"] = "failed"
        RESTORE_STATUS[task_name]["message"] = msg
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Determine restored directory
    restored_dir = os.path.join(temp_dir, "restored-" + snapshot_id)
    if not os.path.exists(restored_dir):
        restored_dir = temp_dir
        if not os.path.isdir(restored_dir) or not os.listdir(restored_dir):
            msg = "Restored directory is empty."
            logging.error(msg)
            RESTORE_STATUS[task_name]["status"] = "failed"
            RESTORE_STATUS[task_name]["message"] = msg
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    # Copy files from the restored directory to the root filesystem
    logging.info("Copying restored files to original locations...")
    files_copied = copy_tree(restored_dir, "/")
    RESTORE_STATUS[task_name]["files_restored"] = files_copied
    logging.info(f"Copied {files_copied} files to root directory.")

    # Verify critical paths
    if critical_paths:
        missing = [path for path in critical_paths if not os.path.exists(path)]
        if missing:
            msg = f"Verification failed; missing: {', '.join(missing)}"
            logging.error(msg)
            RESTORE_STATUS[task_name]["status"] = "warning"
            RESTORE_STATUS[task_name]["message"] = msg
        else:
            logging.info("All critical paths verified.")

    total_time = time.time() - os.path.getmtime(temp_dir)
    msg = (
        f"Restore completed in {total_time:.1f} seconds. {files_copied} files restored."
    )
    RESTORE_STATUS[task_name]["status"] = "success"
    RESTORE_STATUS[task_name]["message"] = msg
    logging.info(msg)

    # Clean up temporary directory
    try:
        shutil.rmtree(temp_dir)
        logging.info(f"Removed temporary directory: {temp_dir}")
    except Exception as e:
        logging.warning(f"Failed to remove temporary directory: {e}")
    return True


# ------------------------------------------------------------------------------
# Reporting Functions
# ------------------------------------------------------------------------------
def print_status_report() -> None:
    """Print a summary report of all restore operations."""
    print_section("Restore Status Report")
    header = f"{'Task':<15} {'Status':<12} {'Files':<8} {'Snapshot Time':<20} Message"
    print(header)
    print("-" * len(header))
    tasks = {"system": "System Restore", "vm": "VM Restore", "plex": "Plex Restore"}
    for task, info in RESTORE_STATUS.items():
        print(
            f"{tasks.get(task, task):<15} {info['status'].upper():<12} "
            f"{info['files_restored']:<8} {info['snapshot']:<20} {info['message']}"
        )
    print("-" * len(header))


def print_repository_info() -> None:
    """Print information about available repositories."""
    print_section("Repository Information")
    repos = [
        ("System", B2_REPO_SYSTEM, CRITICAL_SYSTEM_PATHS),
        ("VM", B2_REPO_VM, CRITICAL_VM_PATHS),
        ("Plex", B2_REPO_PLEX, CRITICAL_PLEX_PATHS),
    ]
    header = f"{'Repository':<10} {'Snapshots':<10} {'Files':<10} {'Size':<12} {'Latest Snapshot':<20}"
    print(header)
    print("-" * len(header))
    for name, repo, _ in repos:
        stats = get_repo_stats(repo, RESTIC_PASSWORD)
        if stats["snapshots"] > 0:
            print(
                f"{name:<10} {stats['snapshots']:<10} {stats['files']:<10} "
                f"{stats['total_size']:<12} {stats['latest_snapshot']:<20}"
            )
        else:
            print(f"{name:<10} No snapshots found")
    print("-" * len(header))


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"RESTORE STARTED AT {now}")
    logging.info("=" * 80)

    # Print system info
    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"User: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")
    try:
        uname = os.uname()
        logging.info(f"OS: {uname.sysname} {uname.release}")
    except Exception:
        logging.info("OS information unavailable.")

    # Display repository info
    print_repository_info()

    # Force unlock repositories
    print_section("Force Unlocking Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # Perform restores
    print_section("Restoring System Backup")
    restore_repo_to_original(
        B2_REPO_SYSTEM, RESTIC_PASSWORD, "system", CRITICAL_SYSTEM_PATHS
    )

    print_section("Restoring VM Backup")
    restore_repo_to_original(B2_REPO_VM, RESTIC_PASSWORD, "vm", CRITICAL_VM_PATHS)

    print_section("Restoring Plex Backup")
    restore_repo_to_original(B2_REPO_PLEX, RESTIC_PASSWORD, "plex", CRITICAL_PLEX_PATHS)

    # Print status report
    print_status_report()

    elapsed = time.time() - start_time
    success_count = sum(1 for v in RESTORE_STATUS.values() if v["status"] == "success")
    failed_count = sum(
        1 for v in RESTORE_STATUS.values() if v["status"] in ("failed", "warning")
    )
    total_files = sum(v.get("files_restored", 0) for v in RESTORE_STATUS.values())
    summary = "SUCCESS" if failed_count == 0 else "FAILED"

    logging.info("=" * 80)
    logging.info(
        f"RESTORE COMPLETED WITH {summary} AT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (took {elapsed:.1f} seconds)"
    )
    logging.info(f"Total files restored: {total_files}")
    logging.info("=" * 80)
    sys.exit(0 if summary == "SUCCESS" else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}", exc_info=True)
        sys.exit(1)
