#!/usr/bin/env python3
"""
backblaze_b2_backup.py
----------------------
Backup script for uploading data to Backblaze B2 with retention.
Uploads data from the WD drive (mounted at /mnt/WD_BLACK/BACKUP/)
to Backblaze B2 and deletes backups older than a specified age.

Usage:
    sudo ./backblaze_b2_backup.py

Notes:
    - This script requires root privileges.
    - Logs are stored at /var/log/backblaze-b2-backup.log by default.

Author: Your Name | License: MIT | Version: 3.2
"""

import os
import sys
import subprocess
import atexit
import signal
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
BACKUP_SOURCE = "/mnt/WD_BLACK/BACKUP/"
BACKUP_DEST = "Backblaze:sawyer-backups"
LOG_FILE = "/var/log/backblaze-b2-backup.log"
RCLONE_CONFIG = "/home/sawyer/.config/rclone/rclone.conf"
RETENTION_DAYS = 30

DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
def get_log_level_num(level: str) -> int:
    level = level.upper()
    if level in ("VERBOSE", "V"):
        return 0
    elif level in ("DEBUG", "D"):
        return 1
    elif level in ("INFO", "I"):
        return 2
    elif level in ("WARN", "WARNING", "W"):
        return 3
    elif level in ("ERROR", "E"):
        return 4
    elif level in ("CRITICAL", "C"):
        return 5
    else:
        return 2  # default to INFO

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
def log(level: str, message: str):
    upper_level = level.upper()
    if get_log_level_num(upper_level) < get_log_level_num(LOG_LEVEL):
        return

    color = NC
    if not DISABLE_COLORS:
        if upper_level == "DEBUG":
            color = NORD9
        elif upper_level == "INFO":
            color = NORD14
        elif upper_level in ("WARN", "WARNING"):
            color = NORD13
        elif upper_level in ("ERROR", "CRITICAL"):
            color = NORD11

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{upper_level}] {message}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        sys.stderr.write(f"Error writing to log file: {e}\n")
    # Print to stderr if not in quiet mode (here quiet mode is always false)
    sys.stderr.write(f"{color}{log_entry}{NC}\n")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An error occurred. Check the log for details.", exit_code=1):
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")
    # Insert any additional cleanup tasks here

atexit.register(cleanup)

def signal_handler(sig, frame):
    handle_error("Script interrupted by user.", exit_code=130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
def upload_backup():
    print_section("Uploading Backup to Backblaze B2")
    log("INFO", f"Starting direct upload of {BACKUP_SOURCE} to Backblaze B2: {BACKUP_DEST}")
    try:
        subprocess.run(
            ["rclone", "--config", RCLONE_CONFIG, "copy", BACKUP_SOURCE, BACKUP_DEST, "-vv"],
            check=True
        )
        log("INFO", "Backup uploaded successfully.")
    except subprocess.CalledProcessError as e:
        handle_error("Failed to upload backup.", exit_code=e.returncode)

def cleanup_backups():
    print_section("Cleaning Up Old Backups on Backblaze B2")
    log("INFO", f"Removing old backups (older than {RETENTION_DAYS} days) from Backblaze B2: {BACKUP_DEST}")
    try:
        subprocess.run(
            ["rclone", "--config", RCLONE_CONFIG, "delete", BACKUP_DEST, "--min-age", f"{RETENTION_DAYS}d", "-vv"],
            check=True
        )
        log("INFO", "Old backups removed successfully.")
    except subprocess.CalledProcessError as e:
        log("WARN", "Failed to remove some old backups.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    check_root()

    # Ensure the log directory exists and secure the log file.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}. Error: {e}")
    try:
        with open(LOG_FILE, "a"):
            pass
    except Exception as e:
        handle_error(f"Failed to create log file: {LOG_FILE}. Error: {e}")
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to set permissions on {LOG_FILE}. Error: {e}")

    log("INFO", "Script execution started.")

    # Validate backup source directory.
    if not os.path.isdir(BACKUP_SOURCE):
        handle_error(f"Backup source directory '{BACKUP_SOURCE}' does not exist.")
    # Validate rclone configuration file.
    if not os.path.isfile(RCLONE_CONFIG):
        handle_error(f"rclone config file '{RCLONE_CONFIG}' not found.")

    upload_backup()
    cleanup_backups()

    log("INFO", "Script execution finished.")

if __name__ == "__main__":
    main()