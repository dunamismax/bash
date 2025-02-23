#!/usr/bin/env python3
"""
Plex Backup Script
------------------
Backup script for Plex Media Server data with compression and retention on Ubuntu.
Backups are stored on a WD drive mounted at /mnt/WD_BLACK.

Usage:
    sudo ./plex_backup.py

Notes:
    - This script requires root privileges.
    - Logs are stored at /var/log/plex-backup.log by default.
Author: Your Name | License: MIT | Version: 3.2
"""

import os
import sys
import subprocess
import signal
import atexit
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
SOURCE = "/usr/local/plexdata/Library/Application Support/Plex Media Server/"
DESTINATION = "/mnt/WD_BLACK/BACKUP/plex-backups"
LOG_FILE = "/var/log/plex-backup.log"
RETENTION_DAYS = 7
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
BACKUP_NAME = f"plex-backup-{TIMESTAMP}.tar.gz"

DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (Section Headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION
# ------------------------------------------------------------------------------
LOG_LEVELS = {
    "VERBOSE": 0, "V": 0,
    "DEBUG": 1, "D": 1,
    "INFO": 2, "I": 2,
    "WARN": 3, "WARNING": 3, "W": 3,
    "ERROR": 4, "E": 4,
    "CRITICAL": 5, "C": 5,
}

def get_log_level_num(level: str) -> int:
    return LOG_LEVELS.get(level.upper(), 2)  # default to INFO

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
def log(level: str, message: str):
    upper_level = level.upper()
    msg_level = get_log_level_num(upper_level)
    current_level = get_log_level_num(os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL))
    if msg_level < current_level:
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
        sys.stderr.write(f"Failed to write to log file: {e}\n")
    
    sys.stderr.write(f"{color}{log_entry}{NC}\n")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An error occurred. Check the log for details.", exit_code=1, lineno=None, func="main"):
    lineno = lineno if lineno is not None else sys._getframe().f_lineno
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    log("ERROR", f"Script failed at line {lineno} in function '{func}'.")
    sys.stderr.write(f"{NORD11}ERROR: {error_message} (Exit Code: {exit_code}){NC}\n")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")
    # Add any necessary cleanup tasks here

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum == signal.SIGINT:
        handle_error("Script interrupted by user.", 130, func="signal_handler")
    elif signum == signal.SIGTERM:
        handle_error("Script terminated.", 143, func="signal_handler")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.getuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
def perform_backup():
    print_section("Performing Plex Backup")
    backup_path = os.path.join(DESTINATION, BACKUP_NAME)
    log("INFO", f"Starting on-the-fly backup and compression to {backup_path}")
    
    # Build the tar command. The -I option tells tar to use pigz for compression.
    tar_cmd = [
        "tar", "-I", "pigz", "--one-file-system", "-cf", backup_path,
        "-C", SOURCE, "."
    ]
    try:
        subprocess.run(tar_cmd, check=True)
        log("INFO", f"Backup and compression completed: {backup_path}")
    except subprocess.CalledProcessError as e:
        handle_error("Backup process failed.")

def cleanup_backups():
    print_section("Cleaning Up Old Backups")
    log("INFO", f"Removing backups older than {RETENTION_DAYS} days from {DESTINATION}")
    
    # Use find to remove backup files older than RETENTION_DAYS.
    find_cmd = [
        "find", DESTINATION, "-mindepth", "1", "-maxdepth", "1",
        "-type", "f", "-mtime", f"+{RETENTION_DAYS}", "-delete"
    ]
    try:
        subprocess.run(find_cmd, check=True)
        log("INFO", "Old backups removed.")
    except subprocess.CalledProcessError:
        log("WARN", "Failed to remove some old backups.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    check_root()
    
    # Ensure log directory exists and set proper permissions.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir} ({e})")
    try:
        with open(LOG_FILE, "a") as f:
            pass
    except Exception as e:
        handle_error(f"Failed to create log file: {LOG_FILE} ({e})")
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to set permissions on {LOG_FILE} ({e})")

    log("INFO", "Script execution started.")

    # Verify that the Plex data source directory exists.
    if not os.path.isdir(SOURCE):
        handle_error(f"Source directory '{SOURCE}' does not exist.")
    
    # Create destination directory if it doesn't exist.
    try:
        os.makedirs(DESTINATION, exist_ok=True)
    except Exception as e:
        handle_error(f"Failed to create destination directory: {DESTINATION} ({e})")
    
    # Check if the destination mount point is available.
    try:
        mount_output = subprocess.check_output(["mount"], text=True)
    except Exception as e:
        handle_error(f"Failed to check mounts: {e}")
    
    if DESTINATION not in mount_output:
        handle_error(f"Destination mount point for '{DESTINATION}' is not available.")
    
    perform_backup()
    cleanup_backups()
    
    log("INFO", "Script execution finished.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        handle_error(f"Unhandled exception: {e}", exit_code=1, func="main")