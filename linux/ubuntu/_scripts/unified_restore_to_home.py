#!/usr/bin/env python3
"""
Unified Restore Script

This script restores the following restic repositories from Backblaze B2 into:
  • /home/sawyer/restic_restore/ubuntu-system-backup
  • /home/sawyer/restic_restore/vm-backups
  • /home/sawyer/restic_restore/plex-media-server-backup

Repository structure on B2:
  Bucket: sawyer-backups / Path: ubuntu-server/[repo-name]

Usage:
  sudo python3 unified_restore.py [--service {system,vm,plex,all}]
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

#####################################
# Configuration
#####################################

# Backblaze B2 and restic credentials
B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"
RESTIC_PASSWORD: str = "12345678"

# Repository definitions (B2 repository paths)
REPOS: Dict[str, str] = {
    "system": f"b2:{B2_BUCKET}:ubuntu-server/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:ubuntu-server/vm-backups",
    "plex": f"b2:{B2_BUCKET}:ubuntu-server/plex-media-server-backup",
}

# Restore destination directories
RESTORE_BASE: Path = Path("/home/sawyer/restic_restore")
RESTORE_DIRS: Dict[str, Path] = {
    "system": RESTORE_BASE / "ubuntu-system-backup",
    "vm": RESTORE_BASE / "vm-backups",
    "plex": RESTORE_BASE / "plex-media-server-backup",
}

# Retry settings for restic commands
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds

# Logging configuration
LOG_FILE: str = "/var/log/unified_restore.log"


#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    """
    Nord-themed ANSI color codes.
    Adjust these codes if needed for your terminal.
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
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )


#####################################
# Signal Handling
#####################################


def signal_handler(signum: int, frame: Any) -> None:
    """Handle interrupt signals gracefully."""
    logging.error(
        f"{Colors.RED}Script interrupted by {signal.Signals(signum).name}.{Colors.ENDC}"
    )
    sys.exit(1)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


#####################################
# Utility Functions
#####################################


def check_root() -> None:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error(
            f"{Colors.RED}This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)


def run_restic(
    repo: str, args: List[str], capture_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Execute a restic command with retry logic.

    Args:
        repo: The repository path.
        args: List of additional arguments for restic.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        The CompletedProcess instance.

    Raises:
        RuntimeError: If maximum retries are exceeded.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd: List[str] = ["restic", "--repo", repo] + args
    logging.info(f"Running command: {' '.join(cmd)}")
    retries: int = 0

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
            error_msg: str = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay: int = RETRY_DELAY * (2 ** (retries - 1))
                logging.warning(
                    f"{Colors.YELLOW}Transient error detected; retrying in {delay} seconds (attempt {retries}).{Colors.ENDC}"
                )
                time.sleep(delay)
            else:
                logging.error(
                    f"{Colors.RED}Restic command failed: {error_msg}{Colors.ENDC}"
                )
                raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot(repo: str) -> Optional[str]:
    """
    Retrieve the latest snapshot ID from the given repository.

    Args:
        repo: The repository path.

    Returns:
        The snapshot ID as a string, or None if not found.
    """
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        if not snapshots:
            logging.warning(
                f"{Colors.YELLOW}No snapshots found in repository: {repo}{Colors.ENDC}"
            )
            return None
        latest = max(snapshots, key=lambda s: s.get("time", ""))
        snap_id = latest.get("id")
        logging.info(f"Latest snapshot for {repo} is {snap_id}")
        return snap_id
    except Exception as e:
        logging.error(f"{Colors.RED}Error retrieving snapshots: {e}{Colors.ENDC}")
        return None


#####################################
# Restore Operation
#####################################


def restore_repo(repo: str, target: Path) -> bool:
    """
    Restore the latest snapshot from the specified repository into the target directory.

    Args:
        repo: The repository path.
        target: The target directory as a Path object.

    Returns:
        True if restore succeeds, False otherwise.
    """
    snap_id: Optional[str] = get_latest_snapshot(repo)
    if not snap_id:
        logging.error(
            f"{Colors.RED}Skipping restore for {repo} - no snapshot found.{Colors.ENDC}"
        )
        return False

    target.mkdir(parents=True, exist_ok=True)
    logging.info(
        f"{Colors.BLUE}Restoring snapshot {snap_id} from {repo} into {target}...{Colors.ENDC}"
    )
    try:
        run_restic(
            repo, ["restore", snap_id, "--target", str(target)], capture_output=True
        )
        if not any(target.iterdir()):
            logging.error(
                f"{Colors.RED}Restore failed: {target} is empty after restore.{Colors.ENDC}"
            )
            return False
        logging.info(
            f"{Colors.GREEN}Successfully restored {repo} into {target}.{Colors.ENDC}"
        )
        return True
    except Exception as e:
        logging.error(f"{Colors.RED}Restore failed for {repo}: {e}{Colors.ENDC}")
        return False


#####################################
# CLI Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments using argparse."""
    parser = argparse.ArgumentParser(
        description="Unified Restore Script: Restore restic repositories from B2 into local directories."
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
    """Main execution function."""
    setup_logging()
    check_root()
    print_header("Unified Restore Script")
    logging.info(f"Restore started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    args = parse_arguments()

    # Determine which services to restore
    if args.service == "all":
        services: List[str] = list(REPOS.keys())
    else:
        services = [args.service]

    # Display a simple numbered menu for clarity
    print(f"{Colors.BOLD}Services selected for restore:{Colors.ENDC}")
    for i, service in enumerate(services, 1):
        print(f"  {i}. {service.capitalize()}")

    start_time = time.time()
    results: Dict[str, bool] = {}

    for service in services:
        repo = REPOS[service]
        target_dir = RESTORE_DIRS[service]
        logging.info(f"Restoring {service} repository into {target_dir}...")
        result = restore_repo(repo, target_dir)
        results[service] = result

    total_time = time.time() - start_time
    print_header("Restore Summary")
    for service, success in results.items():
        status = (
            f"{Colors.GREEN}SUCCESS{Colors.ENDC}"
            if success
            else f"{Colors.RED}FAILED{Colors.ENDC}"
        )
        logging.info(f"{service.capitalize()} restore: {status}")
        print(f"{service.capitalize()} restore: {status}")

    logging.info(f"Total restore time: {total_time:.2f} seconds")
    print(f"\nTotal restore time: {total_time:.2f} seconds")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"{Colors.RED}Unhandled exception: {e}{Colors.ENDC}")
        sys.exit(1)
