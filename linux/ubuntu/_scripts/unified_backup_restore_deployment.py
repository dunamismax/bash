#!/usr/bin/env python3
"""
Restore Script

Restores files for VM and Plex data from a previously created restic backup.
This script supports restoring individual tasks (VM Libvirt or Plex)
or all tasks at once.

Note: Run this script with root privileges.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

#####################################
# Restore Task Configuration
#####################################

RESTORE_TASKS: Dict[str, Dict[str, str]] = {
    "vm-libvirt-var": {
        "name": "VM Libvirt (var)",
        "source": "/home/sawyer/restic_restore/vm-backups/var/lib/libvirt",
        "target": "/var/lib/libvirt",
        "service": "libvirtd",
    },
    "vm-libvirt-etc": {
        "name": "VM Libvirt (etc)",
        "source": "/home/sawyer/restic_restore/vm-backups/etc/libvirt",
        "target": "/etc/libvirt",
        "service": "libvirtd",
    },
    "plex": {
        "name": "Plex Media Server",
        "source": "/home/sawyer/restic_restore/plex-media-server-backup/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "service": "plexmediaserver",
    },
}

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class NordColors:
    HEADER = "\033[38;2;216;222;233m"  # Light gray
    INFO = "\033[38;2;136;192;208m"  # Light blue
    SUCCESS = "\033[38;2;163;190;140m"  # Green
    WARNING = "\033[38;2;235;203;139m"  # Yellow
    ERROR = "\033[38;2;191;97;106m"  # Red
    RESET = "\033[0m"
    BOLD = "\033[1m"


#####################################
# Helper Functions
#####################################


def run_command(cmd: str) -> str:
    """
    Run a shell command and return its output.
    Exit with an error message if the command fails.
    """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"{NordColors.ERROR}Error running command '{cmd}': {result.stderr}{NordColors.RESET}"
        )
        sys.exit(result.returncode)
    return result.stdout.strip()


def control_service(service: str, action: str) -> None:
    """
    Stop or start a given service using systemctl.
    """
    print(
        f"{NordColors.INFO}{action.capitalize()}ing service '{service}'...{NordColors.RESET}"
    )
    run_command(f"systemctl {action} {service}")
    time.sleep(2)


def is_restore_completed(source: str, target: str) -> bool:
    """
    Compare source and target directories.
    Returns True if all files in source exist in target with the same file size.
    """
    if not os.path.exists(target):
        return False

    for root, dirs, files in os.walk(source):
        rel_path = os.path.relpath(root, source)
        dest_root = os.path.join(target, rel_path)
        for d in dirs:
            dest_dir = os.path.join(dest_root, d)
            if not os.path.exists(dest_dir):
                return False
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(dest_root, file)
            if not os.path.exists(dst_file):
                return False
            if os.path.getsize(src_file) != os.path.getsize(dst_file):
                return False
    return True


def copy_directory(source: str, target: str) -> None:
    """
    Recursively copy files from source to target.
    The target directory is recreated if it already exists.
    """
    print(
        f"{NordColors.INFO}Copying from '{source}' to '{target}'...{NordColors.RESET}"
    )
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)
    for root, dirs, files in os.walk(source):
        rel_path = os.path.relpath(root, source)
        dest_dir = os.path.join(target, rel_path)
        os.makedirs(dest_dir, exist_ok=True)
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(dest_dir, file)
            if os.path.exists(src_file):
                try:
                    shutil.copy2(src_file, dst_file)
                except Exception as e:
                    print(
                        f"{NordColors.ERROR}Error copying '{src_file}' to '{dst_file}': {e}{NordColors.RESET}"
                    )
            else:
                print(
                    f"{NordColors.WARNING}Warning: Skipping missing file '{src_file}'{NordColors.RESET}"
                )
    print(f"{NordColors.SUCCESS}Copy completed.{NordColors.RESET}")


#####################################
# Signal Handler
#####################################


def signal_handler(sig: int, frame) -> None:
    """
    Handle interrupt signals gracefully.
    """
    print(f"\n{NordColors.WARNING}Restore interrupted. Exiting...{NordColors.RESET}")
    sys.exit(1)


#####################################
# Restore Task Functions
#####################################


def restore_task(task_key: str) -> bool:
    """
    Restore a single task defined in RESTORE_TASKS.
    Stops the associated service, copies files, and then restarts the service.
    """
    if task_key not in RESTORE_TASKS:
        print(f"{NordColors.ERROR}Unknown restore task: {task_key}{NordColors.RESET}")
        return False

    config = RESTORE_TASKS[task_key]
    name = config["name"]
    source = config["source"]
    target = config["target"]
    service = config.get("service", "")

    print(f"\n{NordColors.HEADER}Restoring {name}...{NordColors.RESET}")
    if not os.path.exists(source):
        print(
            f"{NordColors.ERROR}Source directory not found: {source}{NordColors.RESET}"
        )
        return False

    if os.path.exists(target) and is_restore_completed(source, target):
        print(
            f"{NordColors.INFO}Restore already completed for {name}. Skipping copy.{NordColors.RESET}"
        )
        return True

    if service:
        control_service(service, "stop")

    copy_directory(source, target)

    if service:
        control_service(service, "start")

    print(f"{NordColors.SUCCESS}Successfully restored {name}.{NordColors.RESET}")
    return True


def restore_all() -> Dict[str, bool]:
    """
    Restore all tasks defined in RESTORE_TASKS.
    Returns a dictionary mapping task keys to boolean success values.
    """
    results: Dict[str, bool] = {}
    for key in RESTORE_TASKS:
        results[key] = restore_task(key)
    return results


def print_status_report(results: Dict[str, bool]) -> None:
    """
    Print a summary report of restore statuses.
    """
    print(f"\n{NordColors.BOLD}Restore Status Report:{NordColors.RESET}")
    print("-" * 30)
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        status_str = "SUCCESS" if success else "FAILED"
        print(f"{name:30} {status_str}")
    print("-" * 30)


#####################################
# Main Execution Flow
#####################################


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple File Restore Utility for VM and Plex Data"
    )
    parser.add_argument(
        "-s",
        "--service",
        choices=list(RESTORE_TASKS.keys()) + ["all"],
        default="all",
        help="Restore a specific task or all tasks",
    )
    args = parser.parse_args()

    print(f"{NordColors.BOLD}Starting Restore Operations{NordColors.RESET}")
    start_time = time.time()

    if args.service == "all":
        results = restore_all()
    else:
        results = {args.service: restore_task(args.service)}

    print_status_report(results)
    elapsed = time.time() - start_time
    print(f"{NordColors.INFO}Completed in {elapsed:.1f} seconds{NordColors.RESET}")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print(
            f"{NordColors.ERROR}This script must be run with root privileges.{NordColors.RESET}"
        )
        sys.exit(1)
    # Setup signal handlers for graceful interruption
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()
