#!/usr/bin/env python3
"""
Simplified Unified Restore Script
Restores system, VM, and Plex backups using restic
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Configuration - REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET = "your_backup_bucket"
RESTIC_PASSWORD = "your_restic_password"

# Backup Repositories
REPOS = {
    "system": f"b2:{B2_BUCKET}/system-backup",
    "vm": f"b2:{B2_BUCKET}/vm-backup",
    "plex": f"b2:{B2_BUCKET}/plex-backup",
}

# Restore Locations
RESTORE_BASE = Path("/mnt/restore")
RESTORE_DIRS = {
    "system": RESTORE_BASE / "system",
    "vm": RESTORE_BASE / "vm",
    "plex": RESTORE_BASE / "plex",
}

# Logging Configuration
LOG_FILE = "/var/log/unified_restore.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)


class RestoreError(Exception):
    """Custom exception for restore failures"""

    pass


def run_restic_command(
    args: List[str], capture_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Run a restic command with error handling and environment setup

    Args:
        args: List of arguments for restic command
        capture_output: Whether to capture command output

    Returns:
        subprocess.CompletedProcess with command results

    Raises:
        RestoreError: If the command fails
    """
    # Prepare environment with credentials
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    # Construct full command
    full_cmd = ["restic"] + args

    try:
        # Run the command
        result = subprocess.run(
            full_cmd, env=env, capture_output=capture_output, text=True, check=True
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Restic command failed: {full_cmd}")
        logging.error(f"Error output: {e.stderr}")
        raise RestoreError(f"Restic command failed: {e.stderr}")


def get_latest_snapshot(repo: str) -> Optional[str]:
    """
    Get the ID of the latest snapshot in a repository

    Args:
        repo: Repository URL

    Returns:
        Latest snapshot ID or None
    """
    try:
        # List snapshots in JSON format
        result = run_restic_command(
            ["--repo", repo, "snapshots", "--json"], capture_output=True
        )

        # Parse snapshots
        snapshots = json.loads(result.stdout)

        if not snapshots:
            logging.warning(f"No snapshots found in repository: {repo}")
            return None

        # Sort and get the latest snapshot
        latest_snapshot = max(snapshots, key=lambda s: s.get("time", ""))
        return latest_snapshot.get("id")

    except (json.JSONDecodeError, RestoreError) as e:
        logging.error(f"Error retrieving snapshots: {e}")
        return None


def restore_snapshot(repo: str, snapshot_id: str, target: Path):
    """
    Restore a specific snapshot to a target directory

    Args:
        repo: Repository URL
        snapshot_id: Snapshot ID to restore
        target: Target directory for restore

    Raises:
        RestoreError: If restore fails
    """
    # Ensure target directory exists
    target.mkdir(parents=True, exist_ok=True)

    logging.info(f"Restoring snapshot {snapshot_id} from {repo} to {target}")

    try:
        # Perform restore
        run_restic_command(
            ["--repo", repo, "restore", snapshot_id, "--target", str(target)]
        )

        logging.info(f"Successfully restored {repo} snapshot")

    except RestoreError as e:
        logging.error(f"Restore failed for {repo}: {e}")
        raise


def verify_restore(restore_path: Path) -> Dict[str, int]:
    """
    Verify the restore by counting files and calculating total size

    Args:
        restore_path: Path to restored files

    Returns:
        Dictionary with restore statistics
    """
    stats = {"total_files": 0, "total_size_bytes": 0}

    try:
        for root, _, files in os.walk(restore_path):
            for file in files:
                file_path = Path(root) / file
                stats["total_files"] += 1
                stats["total_size_bytes"] += file_path.stat().st_size

        return stats

    except Exception as e:
        logging.error(f"Verification failed: {e}")
        return stats


def main():
    """
    Main restore process
    """
    # Ensure script is run as root
    if os.geteuid() != 0:
        logging.error("This script must be run with root privileges")
        sys.exit(1)

    start_time = time.time()

    try:
        # Restore each repository
        for name, repo in REPOS.items():
            logging.info(f"Processing {name} backup")

            # Get latest snapshot
            snapshot_id = get_latest_snapshot(repo)
            if not snapshot_id:
                logging.warning(f"Skipping {name} backup - no snapshots found")
                continue

            # Restore snapshot
            target_dir = RESTORE_DIRS[name]
            restore_snapshot(repo, snapshot_id, target_dir)

            # Verify restore
            stats = verify_restore(target_dir)
            logging.info(
                f"{name} backup restore complete: "
                f"{stats['total_files']} files, "
                f"{stats['total_size_bytes'] / (1024 * 1024):.2f} MB"
            )

        logging.info(f"Total restore time: {time.time() - start_time:.2f} seconds")
        sys.exit(0)

    except Exception as e:
        logging.error(f"Restore process failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
