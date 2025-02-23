#!/usr/bin/env python3
"""
Script Name: ubuntu_backup.py
Description: Backup script for Ubuntu systems with compression and retention,
             using the WD drive mounted at /mnt/WD_BLACK. Logs are stored at
             /var/log/ubuntu_backup.log.
Author: Your Name | License: MIT | Version: 1.0.0

Usage:
    sudo ./ubuntu_backup.py

Notes:
    - This script requires root privileges.
    - Logs are stored at /var/log/ubuntu_backup.log by default.
"""

import os
import sys
import subprocess
import logging
import signal
import time
import datetime
import atexit

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ubuntu_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

SOURCE = "/"  # Source directory for backup
DESTINATION = "/mnt/WD_BLACK/BACKUP/ubuntu-backups"  # Destination directory for backups
RETENTION_DAYS = 7

TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
BACKUP_NAME = f"backup-{TIMESTAMP}.tar.gz"

# Exclusion patterns for tar
EXCLUDES = [
    "./proc/*",
    "./sys/*",
    "./dev/*",
    "./run/*",
    "./tmp/*",
    "./mnt/*",
    "./media/*",
    "./swapfile",
    "./lost+found",
    "./var/tmp/*",
    "./var/cache/*",
    "./var/log/*",
    "*.iso",
    "*.tmp",
    "*.swap.img"
]

EXCLUDES_ARGS = [f"--exclude={pattern}" for pattern in EXCLUDES]

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9 = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC = '\033[0m'                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": NORD9,
        "INFO": NORD14,
        "WARNING": NORD13,
        "ERROR": NORD11,
        "CRITICAL": NORD11,
    }
    
    def format(self, record):
        message = super().format(record)
        if not DISABLE_COLORS:
            color = self.LEVEL_COLORS.get(record.levelname, NC)
            message = f"{color}{message}{NC}"
        return message

def setup_logging():
    logger = logging.getLogger()
    level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    
    # Console handler with color formatter
    console_handler = logging.StreamHandler(sys.stderr)
    console_formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler without color codes
    file_handler = logging.FileHandler(LOG_FILE)
    file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on {LOG_FILE}: {e}")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An unknown error occurred", exit_code=1):
    logging.error(f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Insert any necessary cleanup tasks here

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum == signal.SIGINT:
        handle_error("Script interrupted by user.", 130)
    elif signum == signal.SIGTERM:
        handle_error("Script terminated.", 143)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title):
    border = "─" * 60
    logging.info(f"{NORD10}{border}{NC}")
    logging.info(f"{NORD10}  {title}{NC}")
    logging.info(f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
def perform_backup():
    print_section("Starting Backup Process")
    backup_path = os.path.join(DESTINATION, BACKUP_NAME)
    logging.info(f"Creating backup archive {backup_path}")
    
    # Build tar command with pigz compression and exclusion patterns.
    command = ["tar", "-I", "pigz", "-cf", backup_path] + EXCLUDES_ARGS + ["-C", SOURCE, "."]
    try:
        subprocess.run(command, check=True)
        logging.info(f"Backup and compression completed: {backup_path}")
    except subprocess.CalledProcessError:
        handle_error("Backup process failed.")

def cleanup_backups():
    print_section("Cleaning Up Old Backups")
    logging.info(f"Removing backups in {DESTINATION} older than {RETENTION_DAYS} days")
    
    # Use find to remove files older than RETENTION_DAYS days.
    command = ["find", DESTINATION, "-mindepth", "1", "-maxdepth", "1",
               "-type", "f", "-mtime", f"+{RETENTION_DAYS}", "-delete"]
    try:
        subprocess.run(command, check=True)
        logging.info("Old backups removed successfully.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to remove some old backups.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    check_root()
    
    # Ensure the log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}. Error: {e}")
    
    # Touch log file and set permissions
    try:
        with open(LOG_FILE, "a") as f:
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to create or set permissions on log file: {LOG_FILE}. Error: {e}")
    
    setup_logging()
    logging.info("Script execution started.")
    
    # Create destination directory if it doesn't exist.
    try:
        os.makedirs(DESTINATION, exist_ok=True)
    except Exception as e:
        handle_error(f"Failed to create destination directory: {DESTINATION}. Error: {e}")
    
    # Check if the destination mount point is active.
    try:
        mount_output = subprocess.check_output(["mount"], text=True)
    except subprocess.CalledProcessError:
        handle_error("Failed to get mount information.")
    
    if DESTINATION not in mount_output:
        handle_error(f"Destination mount point '{DESTINATION}' is not available.")
    
    perform_backup()
    cleanup_backups()
    
    logging.info("Script execution finished successfully.")

if __name__ == "__main__":
    main()