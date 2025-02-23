#!/usr/bin/env python3
"""
Script Name: deploy_scripts.py
Description: Deploys user scripts from a source directory to a target directory
             on Ubuntu Linux. Ensures proper ownership, performs a dry‑run, and
             sets executable permissions using a Nord‑themed enhanced template for
             robust error handling and logging.
Author: Your Name | License: MIT | Version: 2.1

Usage Examples:
  sudo ./deploy_scripts.py [-d|--debug] [-q|--quiet]
  sudo ./deploy_scripts.py -h|--help

Notes:
  - This script requires root privileges.
  - Logs are stored at /var/log/deploy-scripts.log by default.
"""

import os
import sys
import subprocess
import logging
import signal
import atexit
import argparse
import pwd

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/deploy-scripts.log"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()  # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE = False
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# Deployment‑specific configuration
SCRIPT_SOURCE = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
SCRIPT_TARGET = "/home/sawyer/bin"
EXPECTED_OWNER = "sawyer"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = '\033[38;2;46;52;64m'
NORD1 = '\033[38;2;59;66;82m'
NORD2 = '\033[38;2;67;76;94m'
NORD3 = '\033[38;2;76;86;106m'
NORD4 = '\033[38;2;216;222;233m'
NORD5 = '\033[38;2;229;233;240m'
NORD6 = '\033[38;2;236;239;244m'
NORD7 = '\033[38;2;143;188;187m'
NORD8 = '\033[38;2;136;192;208m'
NORD9 = '\033[38;2;129;161;193m'
NORD10 = '\033[38;2;94;129;172m'
NORD11 = '\033[38;2;191;97;106m'
NORD12 = '\033[38;2;208;135;112m'
NORD13 = '\033[38;2;235;203;139m'
NORD14 = '\033[38;2;163;190;140m'
NORD15 = '\033[38;2;180;142;173m'
NC = '\033[0m'  # Reset / No Color

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
    global LOG_LEVEL, QUIET_MODE
    logger = logging.getLogger()
    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)
    
    # Formatter for console (with colors) and file (plain)
    console_formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Add console handler only if not in quiet mode
    if not QUIET_MODE:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on {LOG_FILE}: {e}")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="Unknown error occurred", exit_code=1):
    logging.error(f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Insert any necessary cleanup tasks here

atexit.register(cleanup)

def signal_handler(signum, frame):
    handle_error(f"Script interrupted by signal {signum}.", exit_code=128+signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def enable_debug():
    global LOG_LEVEL
    LOG_LEVEL = "DEBUG"
    logging.debug("Debug mode enabled: Verbose logging activated.")

def enable_quiet_mode():
    global QUIET_MODE
    QUIET_MODE = True
    logging.info("Quiet mode enabled: Console output suppressed.")

def show_help(script_name):
    help_text = f"""Usage: {script_name} [OPTIONS]

Description:
  Deploys user scripts from a source directory to a target directory on Ubuntu.
  Ensures proper ownership, performs a dry‑run, and sets executable permissions.
  Uses a Nord‑themed enhanced template for robust error handling and logging.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output.
  -h, --help    Show this help message and exit.

Examples:
  sudo {script_name} --debug
  sudo {script_name} --quiet
  sudo {script_name} -h
"""
    print(help_text)
    sys.exit(0)

def print_section(title):
    border = "─" * 60
    logging.info(f"{NORD10}{border}{NC}")
    logging.info(f"{NORD10}  {title}{NC}")
    logging.info(f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# DEPLOYMENT FUNCTION
# ------------------------------------------------------------------------------
def deploy_user_scripts():
    print_section("Deploying User Scripts")
    logging.info("Starting deployment of user scripts...")
    
    # 1. Check ownership of source directory.
    try:
        stat_info = os.stat(SCRIPT_SOURCE)
        source_owner = pwd.getpwuid(stat_info.st_uid).pw_name
    except Exception as e:
        handle_error(f"Failed to stat source directory: {SCRIPT_SOURCE}. Error: {e}")
    
    if source_owner != EXPECTED_OWNER:
        handle_error(f"Invalid script source ownership for '{SCRIPT_SOURCE}' (Owner: {source_owner}). Expected: {EXPECTED_OWNER}")
    
    # 2. Perform a dry‑run deployment.
    logging.info("Performing dry‑run for script deployment...")
    dry_run_cmd = ["rsync", "--dry-run", "-ah", "--delete", f"{SCRIPT_SOURCE}/", SCRIPT_TARGET]
    try:
        subprocess.run(dry_run_cmd, check=True)
    except subprocess.CalledProcessError:
        handle_error("Dry‑run failed for script deployment.")
    
    # 3. Actual deployment.
    logging.info(f"Deploying scripts from '{SCRIPT_SOURCE}' to '{SCRIPT_TARGET}'...")
    deploy_cmd = ["rsync", "-ah", "--delete", f"{SCRIPT_SOURCE}/", SCRIPT_TARGET]
    try:
        subprocess.run(deploy_cmd, check=True)
    except subprocess.CalledProcessError:
        handle_error("Script deployment failed.")
    
    # 4. Set executable permissions on deployed scripts.
    logging.info("Setting executable permissions on deployed scripts...")
    chmod_cmd = f"find {SCRIPT_TARGET} -type f -exec chmod 755 {{}} \\;"
    try:
        subprocess.run(chmod_cmd, shell=True, check=True)
    except subprocess.CalledProcessError:
        handle_error(f"Failed to update script permissions in '{SCRIPT_TARGET}'.")
    
    logging.info("Script deployment completed successfully.")

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug (verbose) logging.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress console output.")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message and exit.")
    args, unknown = parser.parse_known_args()
    
    if args.help:
        show_help(os.path.basename(sys.argv[0]))
    if args.debug:
        enable_debug()
    if args.quiet:
        enable_quiet_mode()

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    check_root()
    
    # Ensure the log directory exists and secure the log file.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}. Error: {e}")
    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to create or set permissions on log file: {LOG_FILE}. Error: {e}")
    
    setup_logging()
    logging.info("Starting script deployment process...")
    parse_args()
    deploy_user_scripts()
    logging.info("Script deployment process completed.")

if __name__ == "__main__":
    main()