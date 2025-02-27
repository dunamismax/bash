#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import time

# ------------------------------------------------------------------------------
# Restore Task Mapping (VM and Plex only)
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
    If destination doesn't exist, it is created.
    Missing files are skipped with a warning.
    """
    print(f"Copying from '{source}' to '{target}'...")
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
                    print(f"Error copying '{src_file}' to '{dst_file}': {e}")
            else:
                print(f"Warning: Skipping missing file '{src_file}'")
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

    if os.path.exists(target) and is_restore_completed(source, target):
        print(f"Restore already completed for {name}. Skipping copy.")
        return True

    if service:
        control_service(service, "stop")

    copy_directory(source, target)

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
