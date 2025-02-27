#!/usr/bin/env python3
"""
Unified Restore Script for VM and Plex Backups
-----------------------------------------------
This script restores backups for VM and Plex from Backblaze B2 restic repositories.
It retrieves the latest snapshot for the selected service(s) and restores files into
a designated local directory.

Usage:
  sudo ./unified_restore.py [--service {vm,plex,all}]
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

#####################################
# Configuration
#####################################

B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"
RESTIC_PASSWORD: str = "12345678"

HOSTNAME: str = os.uname().nodename

# Define repositories based on hostname
B2_REPO_VM: str = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX: str = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Local restore configuration
RESTORE_BASE_DIR: str = "/home/sawyer/restic_backup_restore_data"
RESTORE_DIRS = {
    "vm": str(Path(RESTORE_BASE_DIR) / "vm"),
    "plex": str(Path(RESTORE_BASE_DIR) / "plex"),
}

# Log file location
LOG_FILE: str = "/var/log/unified_restore.log"

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    """Nord-themed ANSI color codes."""

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
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )


#####################################
# Dependency and Privilege Checks
#####################################


def check_dependencies() -> None:
    """Check if restic is installed."""
    if not shutil.which("restic"):
        logging.error(f"{Colors.RED}Restic is not installed.{Colors.ENDC}")
        sys.exit(1)


def check_root() -> None:
    """Verify the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error(f"{Colors.RED}This script must be run as root.{Colors.ENDC}")
        sys.exit(1)


#####################################
# Utility Functions
#####################################


def run_restic_command(repo: str, password: str, *args) -> subprocess.CompletedProcess:
    """
    Run a restic command with error handling.

    Args:
        repo: Repository path.
        password: Repository password.
        *args: Additional restic arguments.

    Returns:
        subprocess.CompletedProcess: The command result.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
    env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, env=env, check=True, capture_output=True, text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"{Colors.RED}Restic command failed: {e.stderr}{Colors.ENDC}")
        raise


def get_latest_snapshot(repo: str, password: str) -> str:
    """
    Retrieve the latest snapshot ID from the repository.

    Args:
        repo: Repository path.
        password: Repository password.

    Returns:
        str: Latest snapshot ID, or an empty string if none found.
    """
    try:
        result = run_restic_command(repo, password, "snapshots", "--json")
        snapshots = json.loads(result.stdout)
        if not snapshots:
            logging.error(
                f"{Colors.RED}No snapshots found in repository '{repo}'.{Colors.ENDC}"
            )
            return ""
        # Sort snapshots by time (descending) and get the first snapshot
        latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
        snapshot_id = latest.get("short_id") or latest.get("id", "")
        logging.info(f"Latest snapshot for '{repo}' is '{snapshot_id}'")
        return snapshot_id
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logging.error(f"{Colors.RED}Error retrieving snapshots: {e}{Colors.ENDC}")
        return ""


def restore_repo(repo: str, password: str, restore_target: str, task_name: str) -> bool:
    """
    Restore the latest snapshot from a repository into a target directory.

    Args:
        repo: Repository path.
        password: Repository password.
        restore_target: Directory to restore files to.
        task_name: Name of the restore task (for logging).

    Returns:
        bool: True if restore succeeded, False otherwise.
    """
    os.makedirs(restore_target, exist_ok=True)

    snapshot_id = get_latest_snapshot(repo, password)
    if not snapshot_id:
        logging.error(
            f"{Colors.RED}Could not find snapshot for {task_name}.{Colors.ENDC}"
        )
        return False

    try:
        start_time = time.time()
        run_restic_command(
            repo, password, "restore", snapshot_id, "--target", restore_target
        )
        elapsed = time.time() - start_time
        logging.info(
            f"{Colors.GREEN}{task_name.capitalize()} restore completed in {elapsed:.1f} seconds{Colors.ENDC}"
        )

        # Count restored files using 'find'
        find_result = subprocess.run(
            ["find", restore_target, "-type", "f"], capture_output=True, text=True
        )
        file_count = len(find_result.stdout.splitlines())
        logging.info(f"{task_name.capitalize()} backup: {file_count} files restored")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(
            f"{Colors.RED}{task_name.capitalize()} restore failed: {e.stderr}{Colors.ENDC}"
        )
        return False


#####################################
# CLI Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified Restore Script: Restore VM and Plex backups from restic repositories."
    )
    parser.add_argument(
        "--service",
        type=str,
        choices=["vm", "plex", "all"],
        default="all",
        help="Specify which service to restore (default: all)",
    )
    return parser.parse_args()


#####################################
# Main Function
#####################################


def main() -> None:
    setup_logging()
    check_dependencies()
    check_root()

    print_header("Unified Restore Script")
    logging.info(
        f"UNIFIED RESTORE STARTED AT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    args = parse_arguments()

    # Define available services and corresponding repositories and restore directories
    services = {
        "vm": (B2_REPO_VM, RESTORE_DIRS["vm"]),
        "plex": (B2_REPO_PLEX, RESTORE_DIRS["plex"]),
    }
    # Determine which services to restore
    if args.service == "all":
        selected_services = list(services.keys())
    else:
        selected_services = [args.service]

    logging.info(f"Selected service(s) for restore: {', '.join(selected_services)}")
    start_time = time.time()
    results = {}

    for service in selected_services:
        repo, target = services[service]
        logging.info(f"{Colors.BLUE}Restoring {service} backup...{Colors.ENDC}")
        result = restore_repo(repo, RESTIC_PASSWORD, target, service)
        results[service] = result

    elapsed = time.time() - start_time
    success_count = sum(results.values())
    total_tasks = len(results)

    # Determine overall status
    if success_count == total_tasks:
        status = "COMPLETE SUCCESS"
    elif success_count > 0:
        status = "PARTIAL SUCCESS"
    else:
        status = "FAILED"

    print_header("Restore Summary")
    logging.info(f"UNIFIED RESTORE COMPLETED WITH {status}")
    logging.info(f"Total execution time: {elapsed:.1f} seconds")
    logging.info(f"Successful restores: {success_count}/{total_tasks}")
    sys.exit(0 if success_count > 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"{Colors.RED}Unhandled exception: {ex}{Colors.ENDC}")
        import traceback

        logging.error(traceback.format_exc())
        sys.exit(1)
