#!/usr/bin/env python3
"""
Script Name: update_plex.py
Description: Downloads and installs the latest Plex Media Server package,
             fixes dependency issues if any, cleans up temporary files, and
             restarts the Plex service.
Author: Your Name | License: MIT | Version: 1.0

Usage:
    sudo ./update_plex.py

Notes:
    This script must be run as root.
"""

import os
import sys
import subprocess
import logging
import shutil
import datetime
import atexit
import signal

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
PLEX_URL = ("https://downloads.plex.tv/plex-media-server-new/"
            "1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb")
TEMP_DEB = "/tmp/plexmediaserver.deb"
LOG_FILE = "/var/log/update_plex.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
QUIET_MODE = False

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'  # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'   # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'   # Reddish (ERROR)
NORD13 = '\033[38;2;235;203;139m'  # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Greenish (INFO)
NC     = '\033[0m'                # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
def setup_logging():
    logger = logging.getLogger("update_plex")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                  "%Y-%m-%d %H:%M:%S")

    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o700, exist_ok=True)

    # File handler
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler with color support if running in a tty
    class ColorFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': NORD9,
            'INFO': NORD14,
            'WARNING': NORD13,
            'ERROR': NORD11,
            'CRITICAL': NORD11,
        }
        def format(self, record):
            color = "" if DISABLE_COLORS else self.COLORS.get(record.levelname, '')
            message = super().format(record)
            return f"{color}{message}{NC}" if color else message

    if sys.stderr.isatty():
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(ColorFormatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                         "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(ch)
    return logger

logger = setup_logging()

def log_info(message: str) -> None:
    logger.info(message)

def log_warn(message: str) -> None:
    logger.warning(message)

def log_error(message: str) -> None:
    logger.error(message)

def log_debug(message: str) -> None:
    logger.debug(message)

def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    log_debug(f"Executing command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text, **kwargs)

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(message: str, exit_code: int = 1) -> None:
    log_error(f"{message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup() -> None:
    log_info("Cleaning up temporary files.")
    if os.path.exists(TEMP_DEB):
        try:
            os.remove(TEMP_DEB)
            log_info(f"Removed temporary file: {TEMP_DEB}")
        except Exception as e:
            log_warn(f"Failed to remove temporary file {TEMP_DEB}: {e}")

atexit.register(cleanup)

def signal_handler(signum, frame):
    handle_error(f"Script interrupted by signal {signum}.", exit_code=signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root() -> None:
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title: str) -> None:
    border = "─" * 60
    log_info(f"{NORD10}{border}{NC}")
    log_info(f"{NORD10}  {title}{NC}")
    log_info(f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# FUNCTION: Download Plex Package
# ------------------------------------------------------------------------------
def download_plex() -> None:
    print_section("Downloading Plex Media Server Package")
    log_info("Downloading Plex Media Server package...")
    try:
        run_command(["curl", "-L", "-o", TEMP_DEB, PLEX_URL])
        log_info("Plex package downloaded successfully.")
    except subprocess.CalledProcessError:
        handle_error("Failed to download Plex package.")

# ------------------------------------------------------------------------------
# FUNCTION: Install Plex Package
# ------------------------------------------------------------------------------
def install_plex() -> None:
    print_section("Installing Plex Media Server")
    log_info("Installing Plex Media Server...")
    try:
        run_command(["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        log_warn("Dependency issues detected. Attempting to fix dependencies...")
        try:
            run_command(["apt-get", "install", "-f", "-y"])
        except subprocess.CalledProcessError:
            handle_error("Failed to resolve dependencies for Plex.")
    log_info("Plex Media Server installed successfully.")

# ------------------------------------------------------------------------------
# FUNCTION: Restart Plex Service
# ------------------------------------------------------------------------------
def restart_plex() -> None:
    print_section("Restarting Plex Media Server Service")
    log_info("Restarting Plex Media Server service...")
    try:
        run_command(["systemctl", "restart", "plexmediaserver"])
        log_info("Plex Media Server service restarted successfully.")
    except subprocess.CalledProcessError:
        handle_error("Failed to restart Plex Media Server service.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main() -> None:
    check_root()

    # Ensure log file exists with proper permissions
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, mode=0o700, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory {log_dir}: {e}")
    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to create or set permissions on log file {LOG_FILE}: {e}")

    log_info("Script execution started.")

    download_plex()
    install_plex()
    restart_plex()

    log_info("Plex Media Server has been updated and restarted successfully.")

if __name__ == "__main__":
    main()
