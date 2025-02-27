#!/usr/bin/env python3
"""
Unified File Restore Utility
----------------------------
This script restores files from specified backup directories to their
original locations while preserving permissions and metadata. It supports
multiple restore tasks (e.g. VM configuration, system files, Plex data) and
handles graceful termination.

Usage:
  sudo ./file_restore.py -b /path/to/backup -s all

Author: Your Name | License: MIT | Version: 1.0.0
"""

import atexit
import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
import time

# ------------------------------------------------------------------------------
# Restore Task Mapping
# ------------------------------------------------------------------------------
RESTORE_TASKS = {
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
    "ubuntu-system": {
        "name": "Ubuntu System",
        "source": "/home/sawyer/restic_restore/ubuntu-system-backup",
        "target": "/",
        "service": None,
    },
    "plex": {
        "name": "Plex Media Server",
        "source": "/home/sawyer/restic_restore/plex-media-server-backup/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "service": "plexmediaserver",
    },
}


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove pre-existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    fmt = "[%(asctime)s] [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(handler)

    log_file = "/var/log/file_restore.log"
    try:
        log_dir = os.path.dirname(log_file)
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(file_handler)
        os.chmod(log_file, 0o600)
    except Exception as e:
        logger.warning(f"Could not set up file logging: {e}")

    return logger


logger = setup_logging()


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    sig_name = (
        getattr(signal, "Signals", lambda x: x)(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger.error(f"Script interrupted by {sig_name}.")
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

atexit.register(lambda: logger.info("Cleanup complete."))


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def run_command(cmd: str, verbose: bool = False) -> str:
    if verbose:
        print(f"Running: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {cmd}")
        logger.error(f"Error: {e.stderr}")
        raise


def is_service_active(service: str) -> bool:
    try:
        output = run_command(f"systemctl is-active {service}")
        return output.strip() == "active"
    except Exception:
        return False


def control_service(service: str, action: str, verbose: bool = False) -> None:
    try:
        run_command(f"systemctl {action} {service}", verbose)
        time.sleep(2)  # Allow time for service to change state
    except Exception as e:
        logger.error(f"Failed to {action} service {service}: {e}")
        raise


def copy_with_progress(source: str, target: str) -> None:
    print(f"Copying from {source} to {target}...")
    try:
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(source, target, copy_function=shutil.copy2)
        print("Copy completed.")
    except Exception as e:
        logger.error(f"Error copying files: {e}")
        raise


# ------------------------------------------------------------------------------
# Restore Operations
# ------------------------------------------------------------------------------
def restore_task(task_key: str, verbose: bool = False) -> bool:
    if task_key not in RESTORE_TASKS:
        logger.error(f"Unknown restore task: {task_key}")
        return False

    config = RESTORE_TASKS[task_key]
    name = config.get("name", task_key)
    source = config["source"]
    target = config["target"]
    service = config.get("service")

    print(f"Restoring {name}...")

    if not os.path.exists(source):
        logger.error(f"Backup source not found: {source}")
        print(f"Source not found: {source}")
        return False

    try:
        if service and is_service_active(service):
            print(f"Stopping service {service}...")
            control_service(service, "stop", verbose)

        print(f"Restoring files from {source} to {target}...")
        copy_with_progress(source, target)

        if service:
            print(f"Starting service {service}...")
            control_service(service, "start", verbose)

        print(f"Successfully restored: {name}")
        logger.info(f"Restored {name} from {source} to {target}")
        return True
    except Exception as e:
        logger.error(f"Error restoring {name}: {e}", exc_info=True)
        print(f"Error restoring {name}: {e}")
        return False


def restore_all(verbose: bool = False) -> dict:
    results = {}
    for key in RESTORE_TASKS:
        results[key] = restore_task(key, verbose)
    return results


def print_status_report(results: dict) -> None:
    print("\nRestore Status Report:")
    print("-" * 30)
    for key, success in results.items():
        name = RESTORE_TASKS[key].get("name", key)
        status_str = "SUCCESS" if success else "FAILED"
        print(f"{name:30} {status_str}")
    print("-" * 30)


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main() -> None:
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Unified File Restore Utility")
    parser.add_argument(
        "-b", "--backup-base", help="Base path for backup directories", required=True
    )
    parser.add_argument(
        "-s",
        "--service",
        choices=list(RESTORE_TASKS.keys()) + ["all"],
        default="all",
        help="Restore a specific task or all tasks",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    args = parser.parse_args()

    # Override task sources if backup base is provided (if needed)
    base = os.path.abspath(args.backup_base)
    # You can update RESTORE_TASKS here if the backup base should modify the source paths

    print("Starting File Restore Operations")
    start_time = time.time()

    if args.service == "all":
        results = restore_all(args.verbose)
    else:
        results = {args.service: restore_task(args.service, args.verbose)}

    print_status_report(results)
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f} seconds")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logger.error(f"Unhandled exception: {ex}", exc_info=True)
        print(f"Unhandled exception: {ex}")
        sys.exit(1)
