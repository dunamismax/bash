#!/usr/bin/env python3
"""
Simplified Unified Restore Script
Restores the following restic repositories from Backblaze B2 into the user folder:
/home/sawyer/restic_restore/[subfolder]

Repositories:
  - ubuntu-system-backup
  - vm-backups
  - plex-media-server-backup

Repository structure on B2:
  Buckets / sawyer-backups / ubuntu-server / [repo-name]

Usage:
  sudo python3 unified_restore_to_home.py
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repositories (using the correct B2 structure)
REPOS = {
    "system": f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:ubuntu-server/vm-backups",
    "plex": f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup",
}

# Restore base directory (target subfolders under /home/sawyer/restic_restore)
RESTORE_BASE = Path("/home/sawyer/restic_restore")
RESTORE_DIRS = {
    "system": RESTORE_BASE / "ubuntu-system-backup",
    "vm": RESTORE_BASE / "vm-backups",
    "plex": RESTORE_BASE / "plex-media-server-backup",
}

# Critical paths to verify after restore (if needed)
CRITICAL_SYSTEM = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

LOG_FILE = "/var/log/unified_restore.log"


# ------------------------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------------------------
def setup_logging() -> None:
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )


# ------------------------------------------------------------------------------
# Cleanup & Signal Handling
# ------------------------------------------------------------------------------
def cleanup() -> None:
    for temp in Path(tempfile.gettempdir()).glob("restic_restore_*"):
        if temp.is_dir():
            shutil.rmtree(temp, ignore_errors=True)


import atexit

atexit.register(cleanup)

import signal


def signal_handler(signum, frame) -> None:
    logging.error(f"Interrupted by {signal.Signals(signum).name}")
    cleanup()
    sys.exit(1)


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


# ------------------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------------------
def check_root() -> None:
    if os.geteuid() != 0:
        logging.error("This script must be run with root privileges.")
        sys.exit(1)


def run_restic(
    repo: str, args: List[str], capture_output: bool = False
) -> subprocess.CompletedProcess:
    """Run a restic command with retry logic."""
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + args
    logging.info("Running: " + " ".join(cmd))
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
            if "timeout" in err_msg.lower() or "connection" in err_msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                logging.warning(
                    f"Transient error; retrying in {delay} seconds (attempt {retries})"
                )
                time.sleep(delay)
            else:
                logging.error("Restic command failed: " + err_msg)
                raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot(repo: str) -> Optional[str]:
    """Return the latest snapshot ID from the repository."""
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        if not snapshots:
            logging.warning(f"No snapshots found in repository: {repo}")
            return None
        latest = max(snapshots, key=lambda s: s.get("time", ""))
        logging.info(f"Latest snapshot for {repo} is {latest.get('id')}")
        return latest.get("id")
    except Exception as e:
        logging.error(f"Error retrieving snapshots: {e}")
        return None


def copy_tree(src: str, dst: str) -> int:
    """Recursively copy files from src to dst. Return number of files copied."""
    count = 0
    for root, _, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        target = os.path.join(dst, rel_path) if rel_path != "." else dst
        os.makedirs(target, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target, f))
            count += 1
    return count


# ------------------------------------------------------------------------------
# Restore Operation
# ------------------------------------------------------------------------------
def restore_repo(repo: str, target: Path, critical_paths: List[str] = None) -> bool:
    """
    Restore the latest snapshot from the repo into the target directory.
    Optionally verify that all critical_paths exist.
    """
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        logging.error(f"Skipping restore for {repo} - no snapshot found")
        return False
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    try:
        run_restic(
            repo, ["restore", snap_id, "--target", temp_dir], capture_output=True
        )
    except Exception as e:
        logging.error(f"Restore failed for {repo}: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False
    # Restic typically restores into a subfolder named "restored-<snap_id>"
    restored_dir = os.path.join(temp_dir, "restored-" + snap_id)
    if not os.path.exists(restored_dir):
        restored_dir = temp_dir
        if not os.listdir(restored_dir):
            logging.error("Empty restore directory.")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    files_copied = copy_tree(restored_dir, str(target))
    logging.info(f"Copied {files_copied} files to {target}")
    if critical_paths:
        missing = [p for p in critical_paths if not os.path.exists(p)]
        if missing:
            logging.warning(f"Missing critical paths: {missing}")
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True


# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    check_root()
    start_time = time.time()

    # Process each repository restore into its corresponding subfolder
    results = {}
    for name, repo in REPOS.items():
        target_dir = RESTORE_DIRS[name]
        logging.info(f"Restoring {name} backup into {target_dir} ...")
        success = restore_repo(repo, target_dir)
        results[name] = success

    total_time = time.time() - start_time
    for name, success in results.items():
        logging.info(
            f"{name.capitalize()} backup restore: {'SUCCESS' if success else 'FAILED'}"
        )
    logging.info(f"Total restore time: {total_time:.2f} seconds")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error("Unhandled exception: " + str(e))
        sys.exit(1)
