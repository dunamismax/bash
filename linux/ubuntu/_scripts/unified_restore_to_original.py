#!/usr/bin/env python3
"""
Unified Restore to Original Locations Script
----------------------------------------------
This script retrieves the latest snapshot from three restic repositories stored on Backblaze B2
and restores the files directly to their original locations on an Ubuntu system.
It supports:
  • System Backup – full system backup.
  • VM Backup – virtual machine configurations and disk images.
  • Plex Backup – Plex Media Server configuration and data.

Restore Process:
  • Use restic to restore the latest snapshot into a temporary directory.
  • Recursively copy the restored files from the temporary directory to the root ("/"),
    preserving file metadata.
  • Verify that all critical paths exist after restoration.

Usage:
  sudo ./unified_restore_to_original.py [--service {system,vm,plex,all}]
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
from typing import Any, Dict, List, Optional, Tuple

import click
from rich.console import Console
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository definitions (repositories are stored under "ubuntu-server")
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:ubuntu-server/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup"

HOSTNAME = socket.gethostname()

# Critical paths that must exist after restore
CRITICAL_SYSTEM: List[str] = ["/etc/fstab", "/etc/passwd", "/etc/hosts"]
CRITICAL_VM: List[str] = ["/etc/libvirt/libvirtd.conf"]
CRITICAL_PLEX: List[str] = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

LOG_FILE = "/var/log/unified_restore_to_original.log"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
class NordColors:
    HEADER = "#88C0D0"
    SUCCESS = "#8FBCBB"
    WARNING = "#5E81AC"
    ERROR = "#BF616A"
    INFO = "#D8DEE9"
    BOLD = "bold"

console = Console()

def print_header(message: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(message, font="slant")
    console.print(ascii_art, style=f"{NordColors.BOLD} {NordColors.HEADER}")

# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )

# ------------------------------
# Cleanup & Signal Handling
# ------------------------------
def cleanup() -> None:
    """Clean up temporary restore directories."""
    temp_pattern = Path(tempfile.gettempdir()).glob("restic_restore_*")
    for temp_dir in temp_pattern:
        if temp_dir.is_dir():
            shutil.rmtree(temp_dir, ignore_errors=True)
    console.print("[bold #D8DEE9]Cleanup complete.[/bold #D8DEE9]")

atexit.register(cleanup)

def signal_handler(signum: int, frame: Any) -> None:
    console.print(f"[{NordColors.ERROR}]{NordColors.BOLD}Interrupted by {signal.Signals(signum).name}.[/]")
    cleanup()
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ------------------------------
# Utility Functions
# ------------------------------
def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        console.print(f"[{NordColors.ERROR}]{NordColors.BOLD}Error: This script must be run as root.[/]", style=NordColors.ERROR)
        sys.exit(1)

def run_restic(repo: str, args: List[str], capture: bool = False) -> subprocess.CompletedProcess:
    """
    Execute a restic command with retry logic.
    
    Args:
        repo: The repository path.
        args: List of additional arguments.
        capture: Whether to capture stdout/stderr.
    
    Returns:
        A CompletedProcess instance.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + args
    logging.info(f"Running: {' '.join(cmd)}")
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
                logging.warning(f"Transient error; retrying in {delay} seconds (attempt {retries}).")
                time.sleep(delay)
            else:
                logging.error(f"Restic failed: {msg}")
                raise
    raise RuntimeError("Max retries exceeded in run_restic")

def get_latest_snapshot(repo: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Retrieve the latest snapshot's short ID and timestamp from the repository.
    
    Returns:
        A tuple (snapshot_id, snapshot_time) or (None, None) if not found.
    """
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture=True)
        snaps = json.loads(result.stdout) if result.stdout else []
        if not snaps:
            logging.error(f"No snapshots found for {repo}")
            return None, None
        latest = max(snaps, key=lambda s: s.get("time", ""))
        snap_id = latest.get("short_id") or latest.get("id", "")
        snap_time = latest.get("time", "")[:19]
        logging.info(f"Latest snapshot for {repo} is {snap_id} from {snap_time}")
        return snap_id, snap_time
    except Exception as e:
        logging.error(f"Error retrieving snapshot for {repo}: {e}")
        return None, None

def copy_tree(src: str, dst: str) -> int:
    """
    Recursively copy files from src to dst preserving metadata.
    
    Returns:
        Number of files copied.
    """
    count = 0
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for file in files:
            shutil.copy2(os.path.join(root, file), os.path.join(target, file))
            count += 1
    return count

# ------------------------------
# Restore Operation
# ------------------------------
def restore_repo(repo: str, critical_paths: List[str]) -> Tuple[bool, str]:
    """
    Restore the latest snapshot from a repository and copy files to their original locations.
    
    Args:
        repo: The restic repository path.
        critical_paths: List of paths that must exist after restore.
    
    Returns:
        Tuple (success, message).
    """
    snap_id, snap_time = get_latest_snapshot(repo)
    if not snap_id:
        return False, "No snapshot found"
    
    temp_dir = tempfile.mkdtemp(prefix="restic_restore_")
    try:
        run_restic(repo, ["restore", snap_id, "--target", temp_dir], capture=True)
    except Exception as e:
        logging.error(f"Restore failed: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, "Restore failed"
    
    # Restic may restore into a subfolder; adjust accordingly.
    restored_path = os.path.join(temp_dir, "restored-" + snap_id)
    if not os.path.exists(restored_path):
        restored_path = temp_dir
        if not os.listdir(restored_path):
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, "Empty restore directory"
    
    files_copied = copy_tree(restored_path, "/")
    logging.info(f"Copied {files_copied} files to root")
    
    missing = [p for p in critical_paths if not os.path.exists(p)]
    status = "success" if not missing else "warning"
    msg = "All critical files restored" if not missing else f"Missing: {missing}"
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, msg

# ------------------------------
# CLI Argument Parsing with Click
# ------------------------------
@click.command()
@click.option("--service", type=click.Choice(["system", "vm", "plex", "all"]), default="all",
              help="Specify which service to restore (default: all)")
def main(service: str) -> None:
    """Unified Restore to Original Locations Script"""
    setup_logging()
    check_root()
    print_header("Unified Restore to Original Locations")
    logging.info(f"Restore started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Define repositories and critical paths per service.
    services: Dict[str, Tuple[str, List[str]]] = {
        "system": (B2_REPO_SYSTEM, CRITICAL_SYSTEM),
        "vm": (B2_REPO_VM, CRITICAL_VM),
        "plex": (B2_REPO_PLEX, CRITICAL_PLEX),
    }
    
    if service == "all":
        selected = list(services.keys())
    else:
        selected = [service]
    
    logging.info(f"Selected service(s) for restore: {', '.join(selected)}")
    start_time = time.time()
    results: Dict[str, Tuple[bool, str]] = {}
    
    for svc in selected:
        repo, crit = services[svc]
        logging.info(f"Restoring {svc} backup from {repo}...")
        try:
            success, msg = restore_repo(repo, crit)
            results[svc] = (success, msg)
        except Exception as e:
            results[svc] = (False, str(e))
    
    total_time = time.time() - start_time
    print_header("Restore Summary")
    for svc, (succ, msg) in results.items():
        status = f"[{NordColors.SUCCESS}]SUCCESS[/]" if succ else f"[{NordColors.ERROR}]FAILED[/]"
        logging.info(f"{svc.capitalize()} restore: {status} - {msg}")
        console.print(f"{svc.capitalize()} restore: {status} - {msg}")
    
    logging.info(f"Total restore time: {total_time:.1f} seconds")
    console.print(f"\nTotal restore time: {total_time:.1f} seconds")
    sys.exit(0 if all(s for s, _ in results.values()) else 1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)