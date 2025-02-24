#!/usr/bin/env python3
"""
Unified Backup Script
---------------------
Description:
  This script uses restic to perform four separate backups:
    1. System backup to a local WD repository.
    2. Plex backup to a local WD repository.
    3. System backup to a Backblaze B2 repository.
    4. Plex backup to a Backblaze B2 repository.

  After backup, a retention policy is enforced (removing snapshots older than a specified number of days).

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 2.0.0
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Local WD Backup Repositories
WD_BASE_PATH = "/media/WD_BLACK/ubuntu_backups"
WD_REPO_SYSTEM = os.path.join(WD_BASE_PATH, "system")
WD_REPO_PLEX = os.path.join(WD_BASE_PATH, "plex")

# Backblaze B2 Backup Repositories and Credentials
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET_SYSTEM = "your_b2_system_bucket"
B2_BUCKET_PLEX = "your_b2_plex_bucket"
# restic repository strings for B2 take the format: b2:bucket:directory
B2_REPO_SYSTEM = f"b2:{B2_BUCKET_SYSTEM}:system"
B2_REPO_PLEX = f"b2:{B2_BUCKET_PLEX}:plex"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "your_unified_restic_password"

# Backup Source Directories
SYSTEM_SOURCE = "/"  # Backup the entire system
PLEX_SOURCE = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/"

# Exclude patterns for the system backup (restic accepts --exclude flags)
SYSTEM_EXCLUDES = [
    "/proc/*",
    "/sys/*",
    "/dev/*",
    "/run/*",
    "/tmp/*",
    "/mnt/*",
    "/media/*",
    "/swapfile",
    "/lost+found",
    "/var/tmp/*",
    "/var/cache/*",
    "/var/log/*",
    "*.iso",
    "*.tmp",
    "*.swap.img",
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS = 7

# Logging Configuration
LOG_FILE = "/var/log/unified_backup.log"
DEFAULT_LOG_LEVEL = "INFO"
# ------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# Logging Setup
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


# ------------------------------------------------------------------------------
# Signal Handling and Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    logging.error("Script interrupted by signal.")
    sys.exit(130)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Add any additional cleanup tasks here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency Check
# ------------------------------------------------------------------------------
def check_dependencies():
    if not shutil.which("restic"):
        logging.error(
            "The 'restic' binary is not found in your PATH. Please install restic and try again."
        )
        sys.exit(1)


# ------------------------------------------------------------------------------
# Helper Functions for Restic Operations
# ------------------------------------------------------------------------------
def run_restic(repo: str, password: str, *args):
    """
    Executes a restic command with the given repository and password.
    If the repository is on B2, ensures that B2 credentials are set.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info("Running restic command: " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def ensure_repo_initialized(repo: str, password: str):
    """
    Checks if the restic repository is already initialized.
    If not, it initializes the repository.
    """
    try:
        run_restic(repo, password, "snapshots")
    except subprocess.CalledProcessError:
        logging.info(f"Repository {repo} not initialized. Initializing...")
        run_restic(repo, password, "init")


def backup_repo(repo: str, password: str, source: str, excludes: list = None):
    """
    Performs a restic backup of the given source directory.
    Additional --exclude flags are added if provided.
    """
    if excludes is None:
        excludes = []
    ensure_repo_initialized(repo, password)
    cmd_args = ["backup", source]
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])
    run_restic(repo, password, *cmd_args)


def cleanup_repo(repo: str, password: str, retention_days: int):
    """
    Removes snapshots older than the specified retention period.
    """
    ensure_repo_initialized(repo, password)
    run_restic(repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d")


# ------------------------------------------------------------------------------
# Main Backup Procedure
# ------------------------------------------------------------------------------
def main():
    check_dependencies()

    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

    logging.info("Unified backup script started.")

    # Verify that the WD mount point exists
    if not os.path.isdir(WD_BASE_PATH):
        logging.error(f"WD backup path '{WD_BASE_PATH}' does not exist. Aborting.")
        sys.exit(1)

    # Define backup tasks
    backup_tasks = [
        {
            "description": "Backup System to WD Repository",
            "repo": WD_REPO_SYSTEM,
            "source": SYSTEM_SOURCE,
            "excludes": SYSTEM_EXCLUDES,
        },
        {
            "description": "Backup Plex to WD Repository",
            "repo": WD_REPO_PLEX,
            "source": PLEX_SOURCE,
            "excludes": [],
        },
        {
            "description": "Backup System to Backblaze B2 Repository",
            "repo": B2_REPO_SYSTEM,
            "source": SYSTEM_SOURCE,
            "excludes": SYSTEM_EXCLUDES,
        },
        {
            "description": "Backup Plex to Backblaze B2 Repository",
            "repo": B2_REPO_PLEX,
            "source": PLEX_SOURCE,
            "excludes": [],
        },
    ]

    # Execute backup tasks
    for task in backup_tasks:
        print_section(task["description"])
        try:
            backup_repo(task["repo"], RESTIC_PASSWORD, task["source"], task["excludes"])
        except subprocess.CalledProcessError as e:
            logging.error(f"{task['description']} failed with error: {e}")
            sys.exit(e.returncode)

    # Define cleanup tasks (repositories to enforce retention policy)
    cleanup_tasks = [
        ("WD System Repository", WD_REPO_SYSTEM),
        ("WD Plex Repository", WD_REPO_PLEX),
        ("B2 System Repository", B2_REPO_SYSTEM),
        ("B2 Plex Repository", B2_REPO_PLEX),
    ]

    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    try:
        for desc, repo in cleanup_tasks:
            logging.info(f"Cleaning {desc}...")
            cleanup_repo(repo, RESTIC_PASSWORD, RETENTION_DAYS)
    except subprocess.CalledProcessError as e:
        logging.error(f"Cleanup failed: {e}")
        sys.exit(e.returncode)

    logging.info("Unified backup script completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
