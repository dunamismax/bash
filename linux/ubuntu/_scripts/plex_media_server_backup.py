#!/usr/bin/env python3
"""
Plex Media Server Backup Script to Backblaze B2 with Service Stop/Start
------------------------------------------------------------------------
Description:
  This script stops the Plex Media Server service, then uses restic to back up the
  Plex Media Server data located at:
    /var/lib/plexmediaserver/Library/Application Support/Plex Media Server/
  The backup is stored in a Backblaze B2 repository within the bucket "sawyer-backups" in
  a repository folder named "plex-media-server-backups". After the backup (and retention
  cleanup) is complete, the Plex Media Server service is restarted.

Usage:
  sudo ./plex_backup_with_service_restart.py

Author: Your Name | License: MIT | Version: 1.0.0
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
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET = "sawyer-backups"

# Define the repository as "plex-media-server-backups" inside the "sawyer-backups" bucket.
B2_REPO_PLEX = f"b2:{B2_BUCKET}:plex-media-server-backups"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "password"

# Plex Media Server Backup Source
PLEX_SOURCE = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/"

# (Optional) Exclude patterns – add any patterns to skip transient or irrelevant files.
PLEX_EXCLUDES = [
    # Example: Exclude temporary files if any are found in the Plex data directory.
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS = 7

# Logging Configuration
LOG_FILE = "/var/log/plex_backup.log"
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

def backup_repo(repo: str, password: str, source, excludes: list = None):
    if excludes is None:
        excludes = []
    ensure_repo_initialized(repo, password)
    cmd_args = ["backup", source]
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])
    run_restic(repo, password, *cmd_args)

def cleanup_repo(repo: str, password: str, retention_days: int):
    ensure_repo_initialized(repo, password)
    run_restic(repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d")

def stop_service():
    logging.info("Stopping Plex Media Server service...")
    subprocess.run(["systemctl", "stop", "plexmediaserver"], check=True)

def start_service():
    logging.info("Starting Plex Media Server service...")
    subprocess.run(["systemctl", "start", "plexmediaserver"], check=True)

def main():
    check_dependencies()

    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

    logging.info("Plex Media Server backup script started.")

    # Stop the Plex Media Server service before backup.
    try:
        stop_service()
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to stop Plex Media Server service: {e}")
        sys.exit(e.returncode)

    try:
        backup_tasks = [
            {
                "description": "Backup Plex Media Server Data to Backblaze B2 Repository",
                "repo": B2_REPO_PLEX,
                "source": PLEX_SOURCE,
                "excludes": PLEX_EXCLUDES,
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
            logging.info("Cleaning Backblaze B2 Plex Repository...")
            cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RETENTION_DAYS)
        except subprocess.CalledProcessError as e:
            logging.error(f"Cleanup failed: {e}")
            sys.exit(e.returncode)
    finally:
        # Always restart the Plex Media Server service even if backup fails.
        try:
            start_service()
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to start Plex Media Server service: {e}")
            sys.exit(e.returncode)

    logging.info("Plex Media Server backup script completed successfully.")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
