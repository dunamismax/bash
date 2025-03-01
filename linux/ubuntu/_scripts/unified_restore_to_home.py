#!/usr/bin/env python3
"""
Unified Restore Script (B2 CLI Version with Recursive Scan)

This script uses the B2 CLI tool (with a full path) to scan the sawyer-backups bucket for all restic
repositories (even nested ones). It displays a numbered list of available backups and prompts the user
to select one or more repositories to restore (multiple selections allowed via space‑separated numbers).
Each selected repository is restored into its own subfolder under the restore base directory.

Note: Run this script with root privileges.
"""

import atexit
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
# Full path to the B2 CLI tool – update this path if necessary.
B2_CLI = "/home/sawyer/.local/bin/b2"

# B2 & Restic configuration
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Restore base directory (each repo will restore into its own subfolder here)
RESTORE_BASE = Path("/home/sawyer/restic_restore")

# Retry settings for restic commands
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Logging configuration
LOG_FILE = "/var/log/unified_restore.log"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Using Nord palette (example hex colors)
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
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )

# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def signal_handler(signum: int, frame: Any) -> None:
    console.print(f"[{NordColors.WARNING}]Script interrupted by {signal.Signals(signum).name}. Cleaning up...[/]")
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

def cleanup() -> None:
    console.print(f"[{NordColors.INFO}]Performing cleanup tasks...[/]")

atexit.register(cleanup)

# ------------------------------
# Utility Functions
# ------------------------------
def check_root() -> None:
    if os.geteuid() != 0:
        console.print(f"[{NordColors.ERROR}]{NordColors.BOLD}Error: This script must be run with root privileges.[/]", style=NordColors.ERROR)
        sys.exit(1)

# ------------------------------
# Restic Command Helper with Retries
# ------------------------------
def run_restic(repo: str, args: List[str], capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a restic command with retries on transient errors."""
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + args
    logging.info(f"Running command: {' '.join(cmd)}")
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
            error_msg = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                console.print(f"[{NordColors.WARNING}]Transient error; retrying in {delay} seconds (attempt {retries}).[/]")
                time.sleep(delay)
            else:
                console.print(f"[{NordColors.ERROR}]Restic command failed: {error_msg}[/]")
                raise
    raise RuntimeError("Max retries exceeded in run_restic")

def get_latest_snapshot(repo: str) -> Optional[str]:
    """Retrieve the ID of the latest snapshot in the given repository."""
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        if not snapshots:
            console.print(f"[{NordColors.WARNING}]No snapshots found in repository: {repo}[/]")
            return None
        latest = max(snapshots, key=lambda s: s.get("time", ""))
        snap_id = latest.get("id")
        logging.info(f"Latest snapshot for {repo} is {snap_id}")
        return snap_id
    except Exception as e:
        console.print(f"[{NordColors.ERROR}]Error retrieving snapshots for {repo}: {e}[/]")
        return None

# ------------------------------
# Scanning for Repositories Using B2 CLI
# ------------------------------
def scan_for_repos() -> Dict[int, Tuple[str, str]]:
    """
    Recursively scan the B2 bucket for restic repositories.
    A repository is identified by the presence of a 'config' file.
    
    Returns:
        Dictionary mapping menu numbers to (repo_name, repo_path)
    """
    repos: Dict[int, Tuple[str, str]] = {}
    seen: set = set()
    try:
        cmd = [B2_CLI, "ls", B2_BUCKET, "--recursive"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            line = line.strip()
            parts = line.split("/")
            if parts[-1] == "config" and len(parts) > 1:
                repo_folder = "/".join(parts[:-1])
                if repo_folder in seen:
                    continue
                seen.add(repo_folder)
                repo_name = repo_folder.split("/")[-1]
                repo_path = f"b2:{B2_BUCKET}:{repo_folder}"
                repos[len(repos) + 1] = (repo_name, repo_path)
    except subprocess.CalledProcessError as e:
        console.print(f"[{NordColors.ERROR}]Error scanning B2 bucket: {e.stderr or str(e)}[/]")
    return repos

# ------------------------------
# Restore Operation
# ------------------------------
def restore_repo(repo: str, target: Path) -> bool:
    """Restore the latest snapshot from the given repository into the target directory."""
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        console.print(f"[{NordColors.ERROR}]Skipping restore for {repo} – no snapshot found.[/]")
        return False
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[{NordColors.INFO}]Restoring snapshot {snap_id} from {repo} into {target}...[/]")
    try:
        run_restic(repo, ["restore", snap_id, "--target", str(target)], capture_output=True)
        if not any(target.iterdir()):
            console.print(f"[{NordColors.ERROR}]Restore failed: {target} is empty after restore.[/]")
            return False
        console.print(f"[{NordColors.SUCCESS}]Successfully restored {repo} into {target}.[/]")
        return True
    except Exception as e:
        console.print(f"[{NordColors.ERROR}]Restore failed for {repo}: {e}[/]")
        return False

# ------------------------------
# CLI Argument Parsing with Click
# ------------------------------
@click.command()
@click.option("--non-interactive", is_flag=True, help="Restore a specific repository by providing its repo path via --repo (skips scanning menu).")
@click.option("--repo", type=str, default="", help="Specify a single restic repository path to restore (e.g., 'b2:sawyer-backups:some/repo').")
def main(non_interactive: bool, repo: str) -> None:
    """Unified Restore Script: Scan B2 for restic repositories and restore selected backups."""
    setup_logging()
    check_root()
    print_header("Unified Restore Script")
    logging.info(f"Restore started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # In non-interactive mode, use provided repo only.
    if non_interactive and repo:
        selected_repos = {1: ("CustomRepo", repo)}
    else:
        available_repos = scan_for_repos()
        if not available_repos:
            console.print(f"[{NordColors.ERROR}]No restic repositories found in bucket {B2_BUCKET}.[/]")
            sys.exit(1)
        console.print(f"[{NordColors.BOLD}]Available Restic Repositories:[/]")
        for num, (repo_name, repo_path) in available_repos.items():
            console.print(f"  {num}. {repo_name}  [{repo_path}]")
        selection = click.prompt("Enter the numbers of the repositories to restore (separated by spaces)", type=str).strip()
        if not selection:
            console.print(f"[{NordColors.ERROR}]No selection made. Exiting.[/]")
            sys.exit(1)
        try:
            choices = [int(num) for num in selection.split()]
        except ValueError:
            console.print(f"[{NordColors.ERROR}]Invalid input. Please enter valid numbers separated by spaces.[/]")
            sys.exit(1)
        selected_repos = {num: available_repos[num] for num in choices if num in available_repos}
        if not selected_repos:
            console.print(f"[{NordColors.ERROR}]No valid repositories selected. Exiting.[/]")
            sys.exit(1)

    start_time = time.time()
    results: Dict[str, bool] = {}
    for _, (repo_name, repo_path) in selected_repos.items():
        target_dir = RESTORE_BASE / repo_name
        console.print(f"[{NordColors.INFO}]Restoring repository '{repo_name}' from {repo_path} into {target_dir}...[/]")
        result = restore_repo(repo_path, target_dir)
        results[repo_name] = result

    total_time = time.time() - start_time
    print_header("Restore Summary")
    for repo_name, success in results.items():
        status = f"[{NordColors.SUCCESS}]SUCCESS[/]" if success else f"[{NordColors.ERROR}]FAILED[/]"
        logging.info(f"{repo_name} restore: {status}")
        console.print(f"{repo_name} restore: {status}")
    logging.info(f"Total restore time: {total_time:.2f} seconds")
    console.print(f"\nTotal restore time: {total_time:.2f} seconds")
    sys.exit(0 if all(results.values()) else 1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"[{NordColors.ERROR}]Unhandled exception: {e}[/]")
        sys.exit(1)