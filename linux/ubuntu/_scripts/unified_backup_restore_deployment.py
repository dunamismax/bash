#!/usr/bin/env python3
import argparse
import os
import shutil
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


def run_command(cmd: str) -> str:
    """Run a shell command and return its output. Exit on error."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command '{cmd}': {result.stderr}")
        sys.exit(result.returncode)
    return result.stdout.strip()


def control_service(service: str, action: str) -> None:
    """Stop or start a given service."""
    print(f"{action.capitalize()}ing service '{service}'...")
    run_command(f"systemctl {action} {service}")
    time.sleep(2)


def copy_directory(source: str, target: str) -> None:
    """Remove target (if exists) and copy source directory to target."""
    print(f"Copying from '{source}' to '{target}'...")
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(source, target, copy_function=shutil.copy2)
    print("Copy completed.")


def restore_task(task_key: str) -> bool:
    if task_key not in RESTORE_TASKS:
        print(f"Unknown restore task: {task_key}")
        return False

    config = RESTORE_TASKS[task_key]
    name = config["name"]
    source = config["source"]
    target = config["target"]
    service = config["service"]

    print(f"\nRestoring {name}...")
    if not os.path.exists(source):
        print(f"Source directory not found: {source}")
        return False

    # Stop the service if specified and active
    if service:
        control_service(service, "stop")

    # Copy files from source to target
    copy_directory(source, target)

    # Restart the service if specified
    if service:
        control_service(service, "start")

    print(f"Successfully restored {name}")
    return True


def restore_all() -> dict:
    results = {}
    for key in RESTORE_TASKS:
        results[key] = restore_task(key)
    return results


def print_status_report(results: dict) -> None:
    print("\nRestore Status Report:")
    print("-" * 30)
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        status_str = "SUCCESS" if success else "FAILED"
        print(f"{name:30} {status_str}")
    print("-" * 30)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple File Restore Utility")
    parser.add_argument(
        "-s",
        "--service",
        choices=list(RESTORE_TASKS.keys()) + ["all"],
        default="all",
        help="Restore a specific task or all tasks",
    )
    args = parser.parse_args()

    print("Starting Restore Operations")
    start_time = time.time()

    if args.service == "all":
        results = restore_all()
    else:
        results = {args.service: restore_task(args.service)}

    print_status_report(results)
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f} seconds")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)
    main()
