#!/usr/bin/env python3
"""
Unified Restore to Original Locations Script
----------------------------------------------
This script retrieves the latest snapshot from three restic repositories stored on Backblaze B2
and restores the files directly to their original locations on an Ubuntu system. It supports:
  1. System Backup – full system backup.
  2. VM Backup – virtual machine configurations and disk images.
  3. Plex Backup – Plex Media Server configuration and data.

Restore Process:
  • Use restic to restore the latest snapshot into a temporary directory.
  • Recursively copy the restored files from the temporary directory to the root ("/"),
    preserving file metadata.
  • Verify that all critical paths exist after restoration.

Usage:
  sudo ./unified_restore_to_original.py [--service {system,vm,plex,all}]
"""

import atexit
import argparse
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
from typing import Tuple, Optional, List, Dict, Any

#####################################
# Configuration
#####################################

B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"
RESTIC_PASSWORD: str = "12345678"

# Repository definitions (under "ubuntu-server" folder)
B2_REPO_SYSTEM: str = f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup"
B2_REPO_VM: str = f"b2:{B2_BUCKET}:ubuntu-server/vm-backups"
B2_REPO_PLEX: str = f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup"

HOSTNAME: str = socket.gethostname()

# Critical paths that must exist after restore
CRITICAL_SYSTEM: List[str] = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM: List[str] = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX: List[str] = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds

LOG_FILE: str = "/var/log/unified_restore_to_original.log"

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    """
    Nord-themed ANSI color codes.
    """

    HEADER = "\033[38;5;81m"  # Nord9
    GREEN = "\033[38;5;82m"  # Nord14
    YELLOW = "\033[38;5;226m"  # Nord13
    RED = "\033[38;5;196m"  # Nord11
    BLUE = "\033[38;5;39m"  # Nord8
    BOLD = "\033[1m"
    ENDC = "\033[0m"


def print_header(message: str) -> None:
    """Print a formatted header using Nord-themed colors."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


#####################################
# Logging Setup
#####################################


def setup_logging() -> None:
    log_dir: str = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=f"{Colors.BOLD}[%(asctime)s] [%(levelname)s]{Colors.ENDC} %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )


#####################################
# Cleanup & Signal Handling
#####################################


def cleanup() -> None:
    """Clean up temporary restore directories."""
    temp_pattern = Path(tempfile.gettempdir()).glob("restic_restore_*")
    for temp_dir in temp_pattern:
        if temp_dir.is_dir():
            shutil.rmtree(temp_dir, ignore_errors=True)


atexit.register(cleanup)


def signal_handler(signum: int, frame: Any) -> None:
    """Handle interrupt signals gracefully."""
    logging.error(
        f"{Colors.RED}Interrupted by {signal.Signals(signum).name}{Colors.ENDC}"
    )
    cleanup()
    sys.exit(1)


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)

#####################################
# Utility Functions
#####################################


def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        logging.error(f"{Colors.RED}This script must be run as root.{Colors.ENDC}")
        sys.exit(1)


def run_restic(
    repo: str, args: List[str], capture: bool = False
) -> subprocess.CompletedProcess:
    """
    Execute a restic command with retry logic.

    Args:
        repo: The repository path.
        args: Additional arguments for restic.
        capture: Whether to capture stdout/stderr.

    Returns:
        CompletedProcess instance.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd: List[str] = ["restic", "--repo", repo] + args
    logging.info(f"Running: {' '.join(cmd)}")
    retries: int = 0

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
            msg: str = e.stderr or str(e)
            if "timeout" in msg.lower() or "connection" in msg.lower():
                retries += 1
                delay: int = RETRY_DELAY * (2 ** (retries - 1))
                logging.warning(
                    f"{Colors.YELLOW}Transient error; retrying in {delay} seconds (attempt {retries}).{Colors.ENDC}"
                )
                time.sleep(delay)
            else:
                logging.error(f"{Colors.RED}Restic failed: {msg}{Colors.ENDC}")
                raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot(repo: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Retrieve the latest snapshot ID and timestamp from the repository.

    Returns:
        A tuple (snapshot_id, snapshot_time) or (None, None) if not found.
    """
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture=True)
        snaps = json.loads(result.stdout) if result.stdout else []
        if not snaps:
            logging.error(f"{Colors.RED}No snapshots found for {repo}{Colors.ENDC}")
            return None, None
        latest = max(snaps, key=lambda s: s.get("time", ""))
        snap_id: str = latest.get("short_id") or latest.get("id", "")
        snap_time: str = latest.get("time", "")[:19]
        logging.info(f"Latest snapshot for {repo} is {snap_id} from {snap_time}")
        return snap_id, snap_time
    except Exception as e:
        logging.error(f"{Colors.RED}Error retrieving snapshot: {e}{Colors.ENDC}")
        return None, None


def copy_tree(src: str, dst: str) -> int:
    """
    Recursively copy files from src to dst preserving metadata.

    Returns:
        Number of files copied.
    """
    count: int = 0
    for root, _, files in os.walk(src):
        rel: str = os.path.relpath(root, src)
        target: str = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target, f))
            count += 1
    return count


#####################################
# Restore Operation
#####################################


def restore_repo(repo: str, critical_paths: List[str]) -> Tuple[bool, str]:
    """
    Restore the latest snapshot from repo and copy files to the root ("/").

    Args:
        repo: The repository path.
        critical_paths: List of critical paths to verify post-restore.

    Returns:
        A tuple (success, message).
    """
    snap_id, snap_time = get_latest_snapshot(repo)
    if not snap_id:
        return False, "No snapshot found"

    temp_dir: str = tempfile.mkdtemp(prefix="restic_restore_")
    try:
        run_restic(repo, ["restore", snap_id, "--target", temp_dir], capture=True)
    except Exception as e:
        logging.error(f"{Colors.RED}Restore failed: {e}{Colors.ENDC}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "Restore failed"

    # Restic typically restores files under a subdirectory named "restored-<snap_id>"
    restored_path: str = os.path.join(temp_dir, "restored-" + snap_id)
    if not os.path.exists(restored_path):
        restored_path = temp_dir
        if not os.listdir(restored_path):
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, "Empty restore directory"

    files_copied: int = copy_tree(restored_path, "/")
    logging.info(f"Copied {files_copied} files to root")

    missing: List[str] = [p for p in critical_paths if not os.path.exists(p)]
    status: str = "success" if not missing else "warning"
    msg: str = "All critical files restored" if not missing else f"Missing: {missing}"
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, msg


#####################################
# CLI Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified Restore Script: Restore restic snapshots to their original locations."
    )
    parser.add_argument(
        "--service",
        type=str,
        choices=["system", "vm", "plex", "all"],
        default="all",
        help="Specify which service to restore (default: all)",
    )
    return parser.parse_args()


#####################################
# Main Function
#####################################


def main() -> None:
    setup_logging()
    check_root()
    print_header("Unified Restore to Original Locations")
    logging.info(f"Restore started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    args = parse_arguments()

    # Define repositories and their critical paths
    services: Dict[str, Tuple[str, List[str]]] = {
        "system": (B2_REPO_SYSTEM, CRITICAL_SYSTEM),
        "vm": (B2_REPO_VM, CRITICAL_VM),
        "plex": (B2_REPO_PLEX, CRITICAL_PLEX),
    }

    # Determine which services to restore
    if args.service == "all":
        selected: List[str] = list(services.keys())
    else:
        selected = [args.service]

    logging.info(f"Selected service(s) for restore: {', '.join(selected)}")
    start_time: float = time.time()
    results: Dict[str, Tuple[bool, str]] = {}

    for service in selected:
        repo, crit = services[service]
        logging.info(f"{Colors.BLUE}Restoring {service} backup...{Colors.ENDC}")
        try:
            success, msg = restore_repo(repo, crit)
            results[service] = (success, msg)
        except Exception as e:
            results[service] = (False, str(e))

    total_time: float = time.time() - start_time
    print_header("Restore Summary")
    for name, (succ, m) in results.items():
        status: str = (
            f"{Colors.GREEN}SUCCESS{Colors.ENDC}"
            if succ
            else f"{Colors.RED}FAILED{Colors.ENDC}"
        )
        logging.info(f"{name.capitalize()} restore: {status} - {m}")
        print(f"{name.capitalize()} restore: {status} - {m}")

    logging.info(f"Total restore time: {total_time:.1f} seconds")
    print(f"\nTotal restore time: {total_time:.1f} seconds")
    sys.exit(0 if all(s for s, _ in results.values()) else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"{Colors.RED}Unhandled exception: {e}{Colors.ENDC}")
        sys.exit(1)
