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

Author: Your Name | License: MIT | Version: 1.0.0
"""

import os
import sys
import subprocess
import logging
import signal
import datetime
import atexit

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Local WD Backup Repositories
WD_BASE_PATH         = "/media/WD_BLACK/ubuntu_backups"
WD_REPO_SYSTEM       = os.path.join(WD_BASE_PATH, "system")
WD_REPO_PLEX         = os.path.join(WD_BASE_PATH, "plex")

# Backblaze B2 Backup Repositories and Credentials
B2_ACCOUNT_ID        = "your_b2_account_id"
B2_ACCOUNT_KEY       = "your_b2_account_key"
B2_BUCKET_SYSTEM     = "your_b2_system_bucket"
B2_BUCKET_PLEX       = "your_b2_plex_bucket"
# Note: restic repository strings for B2 take the format: b2:bucket:directory
B2_REPO_SYSTEM       = f"b2:{B2_BUCKET_SYSTEM}:system"
B2_REPO_PLEX         = f"b2:{B2_BUCKET_PLEX}:plex"

# Restic Repository Passwords (choose strong, secure passwords)
RESTIC_PASSWORD_SYSTEM    = "your_system_repo_password"
RESTIC_PASSWORD_PLEX      = "your_plex_repo_password"
RESTIC_PASSWORD_B2_SYSTEM = "your_b2_system_repo_password"
RESTIC_PASSWORD_B2_PLEX   = "your_b2_plex_repo_password"

# Backup Source Directories
SYSTEM_SOURCE       = "/"   # Backup the entire system
PLEX_SOURCE         = "/usr/local/plexdata/Library/Application Support/Plex Media Server/"

# Exclude patterns for the system backup (restic accepts --exclude flags)
SYSTEM_EXCLUDES     = [
    "/proc/*", "/sys/*", "/dev/*", "/run/*", "/tmp/*",
    "/mnt/*", "/media/*", "/swapfile", "/lost+found",
    "/var/tmp/*", "/var/cache/*", "/var/log/*", "*.iso", "*.tmp", "*.swap.img"
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS      = 7

# Logging Configuration
LOG_FILE            = "/var/log/unified_backup.log"
DEFAULT_LOG_LEVEL   = "INFO"
DISABLE_COLORS      = False
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
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_FILE)
        ]
    )
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on log file: {LOG_FILE}. Error: {e}")

setup_logging()

# Optional: Simple section header printer for clarity in the logs
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
    # Add any necessary cleanup tasks here

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

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

def backup_repo(repo: str, password: str, source: str, excludes: list = []):
    """
    Performs a restic backup of the given source directory.
    Additional --exclude flags are added if provided.
    """
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
    check_root()
    logging.info("Unified backup script started.")

    # Verify that the WD mount point exists
    if not os.path.isdir(WD_BASE_PATH):
        logging.error(f"WD backup path '{WD_BASE_PATH}' does not exist. Aborting.")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # 1. Backup System to WD Repository
    # --------------------------------------------------------------------------
    print_section("Backup System to WD Repository")
    try:
        backup_repo(WD_REPO_SYSTEM, RESTIC_PASSWORD_SYSTEM, SYSTEM_SOURCE, excludes=SYSTEM_EXCLUDES)
    except subprocess.CalledProcessError as e:
        logging.error(f"System backup to WD failed: {e}")
        sys.exit(e.returncode)

    # --------------------------------------------------------------------------
    # 2. Backup Plex to WD Repository
    # --------------------------------------------------------------------------
    print_section("Backup Plex to WD Repository")
    try:
        backup_repo(WD_REPO_PLEX, RESTIC_PASSWORD_PLEX, PLEX_SOURCE)
    except subprocess.CalledProcessError as e:
        logging.error(f"Plex backup to WD failed: {e}")
        sys.exit(e.returncode)

    # --------------------------------------------------------------------------
    # 3. Backup System to Backblaze B2 Repository
    # --------------------------------------------------------------------------
    print_section("Backup System to Backblaze B2 Repository")
    try:
        backup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD_B2_SYSTEM, SYSTEM_SOURCE, excludes=SYSTEM_EXCLUDES)
    except subprocess.CalledProcessError as e:
        logging.error(f"System backup to B2 failed: {e}")
        sys.exit(e.returncode)

    # --------------------------------------------------------------------------
    # 4. Backup Plex to Backblaze B2 Repository
    # --------------------------------------------------------------------------
    print_section("Backup Plex to Backblaze B2 Repository")
    try:
        backup_repo(B2_REPO_PLEX, RESTIC_PASSWORD_B2_PLEX, PLEX_SOURCE)
    except subprocess.CalledProcessError as e:
        logging.error(f"Plex backup to B2 failed: {e}")
        sys.exit(e.returncode)

    # --------------------------------------------------------------------------
    # Cleanup: Enforce retention policy on all repositories
    # --------------------------------------------------------------------------
    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    try:
        logging.info("Cleaning WD repositories...")
        cleanup_repo(WD_REPO_SYSTEM, RESTIC_PASSWORD_SYSTEM, RETENTION_DAYS)
        cleanup_repo(WD_REPO_PLEX, RESTIC_PASSWORD_PLEX, RETENTION_DAYS)
        logging.info("Cleaning Backblaze B2 repositories...")
        cleanup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD_B2_SYSTEM, RETENTION_DAYS)
        cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD_B2_PLEX, RETENTION_DAYS)
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