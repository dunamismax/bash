#!/usr/bin/env python3
"""
Simplified Unified Restore Script

Restores backups for VM and Plex from Backblaze B2 restic repositories.
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

HOSTNAME = os.uname().nodename

# Repositories
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Restore configuration
RESTORE_BASE_DIR = "/home/sawyer/restic_backup_restore_data"
RESTORE_DIRS = {
    "vm": str(Path(RESTORE_BASE_DIR) / "vm"),
    "plex": str(Path(RESTORE_BASE_DIR) / "plex"),
}
LOG_FILE = "/var/log/unified_restore.log"


def setup_logging():
    """Configure basic logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
    )


def check_dependencies():
    """Check if required dependencies are installed."""
    if not shutil.which("restic"):
        logging.error("Restic is not installed.")
        sys.exit(1)


def check_root():
    """Verify script is running with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def run_restic_command(repo, password, *args):
    """
    Run a restic command with error handling.

    Args:
        repo (str): Repository path
        password (str): Repository password
        *args: Restic command arguments

    Returns:
        subprocess.CompletedProcess: Command result
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
    env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(cmd)}")

    try:
        return subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Restic command failed: {e.stderr}")
        raise


def get_latest_snapshot(repo, password):
    """
    Get the latest snapshot ID from a repository.

    Args:
        repo (str): Repository path
        password (str): Repository password

    Returns:
        str: Latest snapshot ID
    """
    try:
        result = run_restic_command(repo, password, "snapshots", "--json")
        snapshots = json.loads(result.stdout)

        if not snapshots:
            logging.error(f"No snapshots found in repository '{repo}'.")
            return None

        # Sort snapshots by time and get the latest
        latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
        snapshot_id = latest.get("short_id") or latest.get("id", "")
        logging.info(f"Latest snapshot for '{repo}' is '{snapshot_id}'")
        return snapshot_id

    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logging.error(f"Error retrieving snapshots: {e}")
        return None


def restore_repo(repo, password, restore_target, task_name):
    """
    Restore the latest snapshot to the specified target directory.

    Args:
        repo (str): Repository path
        password (str): Repository password
        restore_target (str): Directory to restore to
        task_name (str): Name of the restore task

    Returns:
        bool: True if restore succeeded, False otherwise
    """
    # Ensure restore directory exists
    os.makedirs(restore_target, exist_ok=True)

    # Get latest snapshot
    snapshot_id = get_latest_snapshot(repo, password)
    if not snapshot_id:
        logging.error(f"Could not find snapshot for {task_name}")
        return False

    try:
        # Perform restore
        start_time = time.time()
        result = run_restic_command(
            repo, password, "restore", snapshot_id, "--target", restore_target
        )

        # Log restore details
        elapsed = time.time() - start_time
        logging.info(
            f"{task_name.capitalize()} restore completed in {elapsed:.1f} seconds"
        )

        # Count restored files
        find_result = subprocess.run(
            ["find", restore_target, "-type", "f"], capture_output=True, text=True
        )
        file_count = len(find_result.stdout.splitlines())
        logging.info(f"{task_name.capitalize()} backup: {file_count} files restored")

        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"{task_name.capitalize()} restore failed: {e.stderr}")
        return False


def main():
    """Main script execution."""
    # Setup and initial checks
    setup_logging()
    check_dependencies()
    check_root()

    # Log start of script
    start_time = time.time()
    logging.info("=" * 60)
    logging.info(f"UNIFIED RESTORE STARTED AT {datetime.now()}")
    logging.info("=" * 60)

    # Perform restores
    restore_results = {
        "vm": restore_repo(B2_REPO_VM, RESTIC_PASSWORD, RESTORE_DIRS["vm"], "vm"),
        "plex": restore_repo(
            B2_REPO_PLEX, RESTIC_PASSWORD, RESTORE_DIRS["plex"], "plex"
        ),
    }

    # Final summary
    elapsed = time.time() - start_time
    success_count = sum(restore_results.values())
    total_tasks = len(restore_results)

    # Determine overall status
    if success_count == total_tasks:
        status = "COMPLETE SUCCESS"
    elif success_count > 0:
        status = "PARTIAL SUCCESS"
    else:
        status = "FAILED"

    logging.info("=" * 60)
    logging.info(f"UNIFIED RESTORE COMPLETED WITH {status}")
    logging.info(f"Total execution time: {elapsed:.1f} seconds")
    logging.info(f"Successful restores: {success_count}/{total_tasks}")
    logging.info("=" * 60)

    # Exit with appropriate status code
    sys.exit(0 if success_count > 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        import traceback

        logging.error(traceback.format_exc())
        sys.exit(1)
