#!/usr/bin/env python3
"""
Script Name: update_plex.py
--------------------------------------------------------
Description:
  A robust, visually engaging script that downloads and installs the
  latest Plex Media Server package, fixes dependency issues, cleans up
  temporary files, and restarts the Plex service.

Usage:
  sudo ./update_plex.py

Author: Your Name | License: MIT | Version: 1.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
PLEX_URL = (
    "https://downloads.plex.tv/plex-media-server-new/"
    "1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
)
TEMP_DEB = "/tmp/plexmediaserver.deb"
LOG_FILE = "/var/log/update_plex.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

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

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
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
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
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
    if os.path.exists(TEMP_DEB):
        try:
            os.remove(TEMP_DEB)
            logging.info(f"Removed temporary file: {TEMP_DEB}")
        except Exception as e:
            logging.warning(f"Failed to remove temporary file {TEMP_DEB}: {e}")


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["curl", "dpkg", "apt-get", "systemctl"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"The '{cmd}' command is not found in your PATH. Please install it and try again."
            )
            sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    """
    Run a shell command and log its execution.

    Args:
        cmd: Command to run (list or string)
        check: Whether to check the return code
        capture_output: Whether to capture the command output
        text: Whether to return text output instead of bytes

    Returns:
        subprocess.CompletedProcess object
    """
    log_cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.debug(f"Executing command: {log_cmd}")

    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=text, **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with return code {e.returncode}: {log_cmd}")
        if capture_output and e.stdout:
            logging.debug(f"Command stdout: {e.stdout}")
        if capture_output and e.stderr:
            logging.error(f"Command stderr: {e.stderr}")
        if check:
            raise
        return e


# ------------------------------------------------------------------------------
# PLEX UPDATE FUNCTIONS
# ------------------------------------------------------------------------------


def download_plex():
    """
    Download the Plex Media Server package.
    """
    print_section("Downloading Plex Media Server Package")
    logging.info("Downloading Plex Media Server package...")
    try:
        run_command(["curl", "-L", "-o", TEMP_DEB, PLEX_URL])
        logging.info("Plex package downloaded successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to download Plex package.")
        sys.exit(1)


def install_plex():
    """
    Install the Plex Media Server package and handle any dependency issues.
    """
    print_section("Installing Plex Media Server")
    logging.info("Installing Plex Media Server...")
    try:
        run_command(["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        logging.warning("Dependency issues detected. Attempting to fix dependencies...")
        try:
            run_command(["apt-get", "install", "-f", "-y"])
            # Try installing again after fixing dependencies
            run_command(["dpkg", "-i", TEMP_DEB])
        except subprocess.CalledProcessError:
            logging.error("Failed to resolve dependencies for Plex.")
            sys.exit(1)
    logging.info("Plex Media Server installed successfully.")


def restart_plex():
    """
    Restart the Plex Media Server service.
    """
    print_section("Restarting Plex Media Server Service")
    logging.info("Restarting Plex Media Server service...")
    try:
        run_command(["systemctl", "restart", "plexmediaserver"])
        logging.info("Plex Media Server service restarted successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to restart Plex Media Server service.")
        sys.exit(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()
    check_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main functions
    download_plex()
    install_plex()
    restart_plex()

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
