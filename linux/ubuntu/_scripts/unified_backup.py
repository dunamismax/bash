#!/usr/bin/env python3
"""
Comprehensive Unified Backup Script
-----------------------------------
Description:
  A unified backup solution that performs three types of backups to Backblaze B2:
    1. System Backup - Backs up the entire system (/)
    2. VM Backup - Backs up libvirt virtual machine configurations and disk images
    3. Plex Backup - Backs up Plex Media Server configuration and application data

  Each backup is stored in a separate repository within the same B2 bucket.
  All repositories are named with the hostname prefix for organization.
  The script automatically initializes repositories as needed, forces unlocks before backup,
  and enforces retention policies.

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 3.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "your_b2_account_id"
B2_ACCOUNT_KEY = "your_b2_account_key"
B2_BUCKET = "sawyer-backups"

# Determine the hostname to uniquely name the repositories
HOSTNAME = socket.gethostname()

# Restic repository strings for B2 follow the format: b2:bucket:directory
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Unified Restic Repository Password (use one strong, secure password everywhere)
RESTIC_PASSWORD = "password"

# Backup Source Directories and Exclusions
# System Backup
SYSTEM_SOURCE = "/"  # Backup the entire system
SYSTEM_EXCLUDES = [
    # Virtual / dynamic filesystems – always exclude these.
    "/proc/*",
    "/sys/*",
    "/dev/*",
    "/run/*",

    # Temporary directories (often changing, transient, or recreated on boot)
    "/tmp/*",
    "/var/tmp/*",

    # Mount points and removable media (to avoid backing up external or transient mounts)
    "/mnt/*",
    "/media/*",

    # Common cache directories that need not be backed up
    "/var/cache/*",
    "/var/log/*",
    # User-level cache folders (if you wish to exclude them; adjust as needed)
    "/home/*/.cache/*",

    # Swap file, lost+found, and other system artifacts
    "/swapfile",
    "/lost+found",

    # Exclude VM disk images (common locations and file extensions)
    "*.vmdk",     # VMware disk image
    "*.vdi",      # VirtualBox disk image
    "*.qcow2",    # QEMU/KVM disk image
    "*.img",      # Generic disk image (use with caution if you also have valid .img files)

    # Other large, transient files
    "*.iso",      # Disc images
    "*.tmp",
    "*.swap.img",

    # Exclude specific directories known to store ephemeral or large nonessential data
    "/var/lib/docker/*",  # Docker images/containers (if not intended to be backed up)
    "/var/lib/lxc/*",     # LXC containers (if not intended to be backed up)
]

# VM Backup
VM_SOURCES = [
    "/etc/libvirt",        # Contains XML config files for VMs
    "/var/lib/libvirt",    # Contains VM disk images and additional libvirt data
]
VM_EXCLUDES = [
    # Example: exclude temporary libvirt cache or lock files if needed
    # "/etc/libvirt/qemu/*.lock",
]

# Plex Backup
PLEX_SOURCES = [
    "/var/lib/plexmediaserver",   # Plex Media Server application data
    "/etc/default/plexmediaserver", # Plex configuration
]
PLEX_EXCLUDES = [
    # Exclude cache and transcoding directories
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
]

# Retention policy (keep snapshots within this many days)
RETENTION_DAYS = 7

# Maximum age for a lock to be considered stale (in hours)
STALE_LOCK_HOURS = 2

# Logging Configuration
LOG_FILE = "/var/log/unified_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0  = '\033[38;2;46;52;64m'     # Polar Night (dark)
NORD1  = '\033[38;2;59;66;82m'     # Polar Night (darker than NORD0)
NORD8  = '\033[38;2;136;192;208m'  # Frost (light blue)
NORD9  = '\033[38;2;129;161;193m'  # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'   # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'   # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'  # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------

class NordColorFormatter(logging.Formatter):
    """
    A custom formatter that applies Nord color theme to log messages.
    """
    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS
        
    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)
        
        if not self.use_colors:
            return msg
            
        if levelname == 'DEBUG':
            return f"{NORD9}{msg}{NC}"
        elif levelname == 'INFO':
            return f"{NORD14}{msg}{NC}"
        elif levelname == 'WARNING':
            return f"{NORD13}{msg}{NC}"
        elif levelname in ('ERROR', 'CRITICAL'):
            return f"{NORD11}{msg}{NC}"
        return msg

def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")
    
    return logger

def print_section(title: str):
    """
    Print a section header with Nord theme styling.
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)

# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------

def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------

def check_dependencies():
    """
    Check for required dependencies.
    """
    if not shutil.which("restic"):
        logging.error("The 'restic' binary is not found in your PATH. Please install restic and try again.")
        sys.exit(1)

# ------------------------------------------------------------------------------
# REPOSITORY OPERATIONS
# ------------------------------------------------------------------------------

def run_restic(repo: str, password: str, *args, check=True, capture_output=False):
    """
    Run a restic command with appropriate environment variables.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running restic command: {' '.join(cmd)}")
    
    if capture_output:
        result = subprocess.run(cmd, check=check, env=env, 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
        return result
    else:
        subprocess.run(cmd, check=check, env=env)
        return None

def is_local_repo(repo: str) -> bool:
    """
    Determine if the repository is local (i.e., not a B2 repo).
    """
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
            # Use --no-lock to prevent this check from creating a lock itself
            run_restic(repo, password, "snapshots", "--no-lock")
            logging.info(f"Repository '{repo}' already initialized.")
        except subprocess.CalledProcessError:
            logging.info(f"Repository '{repo}' not initialized. Initializing...")
            run_restic(repo, password, "init")

def force_unlock_repo(repo: str, password: str):
    """
    Force unlock a repository, removing all locks regardless of age.
    """
    logging.warning(f"Forcing unlock of repository '{repo}'")
    try:
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to force unlock repository: {e}")
        return False

# ------------------------------------------------------------------------------
# BACKUP OPERATIONS
# ------------------------------------------------------------------------------

def backup_repo(repo: str, password: str, source: str, excludes: list = None):
    """
    Perform backup to a repository, with force unlock.
    """
    if excludes is None:
        excludes = []
    
    # Check if repository is initialized
    ensure_repo_initialized(repo, password)
    
    # Always force unlock the repository
    force_unlock_repo(repo, password)
    
    # Prepare backup command
    cmd_args = ["backup"]
    
    # Handle both single source and multiple sources
    if isinstance(source, list):
        cmd_args.extend(source)
    else:
        cmd_args.append(source)
    
    # Add excludes
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])
    
    # Run backup
    try:
        run_restic(repo, password, *cmd_args)
    except subprocess.CalledProcessError as e:
        # If backup fails due to lock, try to force unlock and retry
        if "repository is already locked" in str(e):
            logging.warning("Backup failed due to repository lock. Attempting to unlock again...")
            if force_unlock_repo(repo, password):
                logging.info("Retrying backup after force unlock...")
                run_restic(repo, password, *cmd_args)
            else:
                raise e
        else:
            raise e

def cleanup_repo(repo: str, password: str, retention_days: int):
    """
    Clean up old snapshots based on retention policy.
    Handles potential repository locks gracefully.
    """
    # Ensure repository is initialized
    ensure_repo_initialized(repo, password)
    
    # Always force unlock the repository
    force_unlock_repo(repo, password)
    
    # Run cleanup command
    try:
        run_restic(repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d")
    except subprocess.CalledProcessError as e:
        # If cleanup fails due to lock, try to force unlock and retry
        if "repository is already locked" in str(e):
            logging.warning("Cleanup failed due to repository lock. Attempting to force unlock again...")
            if force_unlock_repo(repo, password):
                logging.info("Retrying cleanup after force unlock...")
                run_restic(repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d")
            else:
                raise e
        else:
            raise e

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------

def main():
    setup_logging()
    check_dependencies()

    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)
    
    # Define all backup tasks (system, VM, and Plex)
    backup_tasks = [
        {
            "description": "System Backup to Backblaze B2",
            "repo": B2_REPO_SYSTEM,
            "source": SYSTEM_SOURCE,
            "excludes": SYSTEM_EXCLUDES,
        },
        {
            "description": "VM Backup to Backblaze B2",
            "repo": B2_REPO_VM,
            "source": VM_SOURCES,
            "excludes": VM_EXCLUDES,
        },
        {
            "description": "Plex Media Server Backup to Backblaze B2",
            "repo": B2_REPO_PLEX,
            "source": PLEX_SOURCES,
            "excludes": PLEX_EXCLUDES,
        }
    ]
    
    # Force unlock all repositories before starting
    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    # Execute all backup tasks sequentially
    for task in backup_tasks:
        print_section(task["description"])
        try:
            backup_repo(task["repo"], RESTIC_PASSWORD, task["source"], task["excludes"])
        except subprocess.CalledProcessError as e:
            logging.error(f"{task['description']} failed with error: {e}")
            sys.exit(e.returncode)

    # Clean up old snapshots for all repositories
    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    
    cleanup_tasks = [
        {
            "description": "Cleaning System Backup Repository",
            "repo": B2_REPO_SYSTEM,
        },
        {
            "description": "Cleaning VM Backup Repository",
            "repo": B2_REPO_VM,
        },
        {
            "description": "Cleaning Plex Backup Repository",
            "repo": B2_REPO_PLEX,
        }
    ]
    
    for task in cleanup_tasks:
        logging.info(task["description"])
        try:
            cleanup_repo(task["repo"], RESTIC_PASSWORD, RETENTION_DAYS)
        except subprocess.CalledProcessError as e:
            logging.error(f"{task['description']} failed: {e}")
            sys.exit(e.returncode)

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)