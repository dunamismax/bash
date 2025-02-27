#!/usr/bin/env python3
"""
Simplified Unified Restore Script
-----------------------------------
This script retrieves the latest snapshot from three restic repositories stored on Backblaze B2
and restores the files directly to their original locations on an Ubuntu system. It supports:
  1. System Backup – full system backup.
  2. VM Backup – virtual machine configurations and disk images.
  3. Plex Backup – Plex Media Server configuration and data.

The restore process is:
  - Use restic to restore the latest snapshot into a temporary directory.
  - Recursively copy the restored files from the temporary directory to the root ("/"),
    preserving file metadata.
  - Verify that all critical paths exist after restoration.

Usage: sudo ./unified_restore_to_original.py
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
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repositories under the "ubuntu-server" folder:
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:ubuntu-server/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup"

HOSTNAME = socket.gethostname()

# Critical paths that must exist after restore
CRITICAL_SYSTEM = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

LOG_FILE = "/var/log/unified_restore_to_original.log"


# ------------------------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------------------------
def setup_logging():
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_FILE)],
    )


# ------------------------------------------------------------------------------
# Cleanup & Signal Handling
# ------------------------------------------------------------------------------
def cleanup():
    for temp in Path(tempfile.gettempdir()).glob("restic_restore_*"):
        if temp.is_dir():
            shutil.rmtree(temp, ignore_errors=True)


atexit.register(cleanup)


def signal_handler(signum, frame):
    logging.error(f"Interrupted by {signal.Signals(signum).name}")
    cleanup()
    sys.exit(1)


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


# ------------------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def run_restic(repo, args, capture=False):
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
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
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
                logging.error("Restic failed: " + msg)
                raise


def get_latest_snapshot(repo):
    """Return the latest snapshot ID and its timestamp from the repository."""
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture=True)
        snaps = json.loads(result.stdout) if result.stdout else []
        if not snaps:
            logging.error("No snapshots found for " + repo)
            return None, None
        latest = max(snaps, key=lambda s: s.get("time", ""))
        snap_id = latest.get("short_id") or latest.get("id", "")
        snap_time = latest.get("time", "")[:19]
        logging.info(f"Latest snapshot for {repo} is {snap_id} from {snap_time}")
        return snap_id, snap_time
    except Exception as e:
        logging.error("Error retrieving snapshot: " + str(e))
        return None, None


def copy_tree(src, dst):
    """Recursively copy files from src to dst. Return number of files copied."""
    count = 0
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target, f))
            count += 1
    return count


# ------------------------------------------------------------------------------
# Restore Operation
# ------------------------------------------------------------------------------
def restore_repo(repo, critical_paths):
    """Restore the latest snapshot from repo and copy files to "/"."""
    snap_id, snap_time = get_latest_snapshot(repo)
    if not snap_id:
        return False, "No snapshot found"
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    try:
        run_restic(repo, ["restore", snap_id, "--target", temp_dir], capture=True)
    except Exception as e:
        logging.error("Restore failed: " + str(e))
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "Restore failed"
    # Restic places restored files in a subdirectory "restored-<snap_id>"
    rdir = os.path.join(temp_dir, "restored-" + snap_id)
    if not os.path.exists(rdir):
        rdir = temp_dir
        if not os.listdir(rdir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, "Empty restore directory"
    files_copied = copy_tree(rdir, "/")
    logging.info(f"Copied {files_copied} files to root")
    missing = [p for p in critical_paths if not os.path.exists(p)]
    status = "success" if not missing else "warning"
    msg = "All critical files restored" if not missing else f"Missing: {missing}"
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, msg


# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------
def main():
    setup_logging()
    check_root()
    start = time.time()

    # Define repositories and their critical paths
    repos = {
        "system": (B2_REPO_SYSTEM, CRITICAL_SYSTEM),
        "vm": (B2_REPO_VM, CRITICAL_VM),
        "plex": (B2_REPO_PLEX, CRITICAL_PLEX),
    }
    results = {}
    for name, (repo, crit) in repos.items():
        logging.info(f"Restoring {name} backup...")
        try:
            success, msg = restore_repo(repo, crit)
            results[name] = (success, msg)
        except Exception as e:
            results[name] = (False, str(e))
    total_time = time.time() - start
    for name, (succ, m) in results.items():
        logging.info(
            f"{name.capitalize()} backup: {'SUCCESS' if succ else 'FAILED'} - {m}"
        )
    logging.info(f"Total restore time: {total_time:.1f} seconds")
    if all(s for s, _ in results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error("Unhandled exception: " + str(e))
        sys.exit(1)
