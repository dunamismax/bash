#!/usr/bin/env python3
"""
Simplified Unified Restore Script
Restores the following restic repositories from Backblaze B2 into:
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
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repositories (using correct B2 structure)
REPOS = {
    "system": f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:ubuntu-server/vm-backups",
    "plex": f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup",
}

# Restore locations: each repository is restored directly into its subfolder.
RESTORE_BASE = Path("/home/sawyer/restic_restore")
RESTORE_DIRS = {
    "system": RESTORE_BASE / "ubuntu-system-backup",
    "vm": RESTORE_BASE / "vm-backups",
    "plex": RESTORE_BASE / "plex-media-server-backup",
}

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
# Signal Handling
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    logging.error(f"Script interrupted by {signal.Signals(signum).name}.")
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
    """
    Run a restic command with retry logic.
    """
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
            msg = e.stderr or str(e)
            if "timeout" in msg.lower() or "connection" in msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                logging.warning(
                    f"Transient error; retrying in {delay} seconds (attempt {retries})"
                )
                time.sleep(delay)
            else:
                logging.error("Restic command failed: " + msg)
                raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot(repo: str) -> Optional[str]:
    """
    Return the latest snapshot ID from the repository.
    """
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


# ------------------------------------------------------------------------------
# Restore Operation
# ------------------------------------------------------------------------------
def restore_repo(repo: str, target: Path) -> bool:
    """
    Directly restore the latest snapshot from the repo into the target directory.
    """
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        logging.error(f"Skipping restore for {repo} - no snapshot found")
        return False

    target.mkdir(parents=True, exist_ok=True)
    logging.info(f"Restoring snapshot {snap_id} from {repo} into {target} ...")
    try:
        # Directly restore into the target directory.
        run_restic(
            repo, ["restore", snap_id, "--target", str(target)], capture_output=True
        )
        # Verify that the target directory is not empty.
        if not any(target.iterdir()):
            logging.error(f"Restore failed: {target} is empty after restore")
            return False
        logging.info(f"Successfully restored {repo} into {target}")
        return True
    except Exception as e:
        logging.error(f"Restore failed for {repo}: {e}")
        return False


# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    check_root()
    start_time = time.time()

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
