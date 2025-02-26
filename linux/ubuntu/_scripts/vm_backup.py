#!/usr/bin/env python3
"""
Unified Backup Script for Virtual Machine Backups to Backblaze B2
-------------------------------------------------------------------
Description:
  This script uses restic to perform a backup of virtual machines and their configuration
  files directly to a Backblaze B2 repository. The repository is named "vm-backups" within the
  sawyer-backups bucket. If the repository does not exist, it is automatically initialized.
  After backup, a retention policy is enforced (removing snapshots older than a specified number of days).

Usage:
  sudo ./vm_backup.py

Author: Your Name | License: MIT | Version: 1.0.0
"""

import atexit
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET = "sawyer-backups"

# For virtual machine backups, we create/use a repository named "vm-backups"
B2_REPO_VM = f"b2:{B2_BUCKET}:vm-backups"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "password"

# Virtual Machine Backup Sources
# These directories typically contain virt-manager/libvirt VM configurations and disk images.
VM_SOURCES = [
    "/etc/libvirt",        # Contains XML config files for VMs
    "/var/lib/libvirt",    # Contains VM disk images and additional libvirt data
]

# (Optional) Exclude patterns – add any patterns to skip transient or irrelevant files.
VM_EXCLUDES = [
    # Example: exclude temporary libvirt cache or lock files if needed
    # "/etc/libvirt/qemu/*.lock",
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS = 7

# Logging Configuration
LOG_FILE = "/var/log/unified_vm_backup.log"
DEFAULT_LOG_LEVEL = "INFO"
# ------------------------------------------------------------------------------

def setup_logging():
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, DEFAULT_LOG_LEVEL),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_FILE)],
    )
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

setup_logging()

def print_section(title: str):
    border = "─" * 60
    logging.info(border)
    logging.info(f"  {title}")
    logging.info(border)

def signal_handler(signum, frame):
    logging.error("Script interrupted by signal.")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here.

atexit.register(cleanup)

def check_dependencies():
    if not shutil.which("restic"):
        logging.error("The 'restic' binary is not found in your PATH. Please install restic and try again.")
        sys.exit(1)

def run_restic(repo: str, password: str, *args):
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running restic command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=env)

def is_local_repo(repo: str) -> bool:
    """Determine if the repository is local (i.e., not a B2 repo)."""
    return not repo.startswith("b2:")

def ensure_repo_initialized(repo: str, password: str):
    """
    Ensures that a restic repository is initialized.
    For local repositories, check if the 'config' file exists.
    For B2 repositories, attempt a snapshots command.
    """
    if is_local_repo(repo):
        config_path = os.path.join(repo, "config")
        if os.path.exists(config_path):
            logging.info(f"Repository '{repo}' already initialized.")
            return
        else:
            logging.info(f"Repository '{repo}' not initialized. Initializing...")
            run_restic(repo, password, "init")
    else:
        try:
            run_restic(repo, password, "snapshots")
            logging.info(f"Repository '{repo}' already initialized.")
        except subprocess.CalledProcessError:
            logging.info(f"Repository '{repo}' not initialized. Initializing...")
            run_restic(repo, password, "init")

def backup_repo(repo: str, password: str, sources, excludes: list = None):
    if excludes is None:
        excludes = []
    ensure_repo_initialized(repo, password)
    # Accept a list of sources (or a single string) for backup
    cmd_args = ["backup"]
    if isinstance(sources, list):
        cmd_args.extend(sources)
    else:
        cmd_args.append(sources)
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])
    run_restic(repo, password, *cmd_args)

def cleanup_repo(repo: str, password: str, retention_days: int):
    ensure_repo_initialized(repo, password)
    run_restic(repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d")

def main():
    check_dependencies()

    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

    logging.info("Unified VM backup script started.")

    backup_tasks = [
        {
            "description": "Backup Virtual Machines to Backblaze B2 Repository",
            "repo": B2_REPO_VM,
            "source": VM_SOURCES,
            "excludes": VM_EXCLUDES,
        },
    ]

    for task in backup_tasks:
        print_section(task["description"])
        try:
            backup_repo(task["repo"], RESTIC_PASSWORD, task["source"], task["excludes"])
        except subprocess.CalledProcessError as e:
            logging.error(f"{task['description']} failed with error: {e}")
            sys.exit(e.returncode)

    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    try:
        logging.info("Cleaning Backblaze B2 VM Repository...")
        cleanup_repo(B2_REPO_VM, RESTIC_PASSWORD, RETENTION_DAYS)
    except subprocess.CalledProcessError as e:
        logging.error(f"Cleanup failed: {e}")
        sys.exit(e.returncode)

    logging.info("Unified VM backup script completed successfully.")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
