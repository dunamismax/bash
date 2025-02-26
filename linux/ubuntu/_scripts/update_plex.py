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

Author: Your Name | License: MIT | Version: 1.1.0
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

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
# Nord Color Theme Constants (24-bit ANSI escape sequences)
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
# CUSTOM LOGGING SETUP
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom formatter applying the Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with both console and file handlers.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(DEFAULT_LOG_LEVEL)

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with Nord color formatter
    console_fmt = "[%(asctime)s] [%(levelname)s] %(message)s"
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(
        NordColorFormatter(fmt=console_fmt, datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(console_handler)

    # File handler without colors
    file_fmt = "[%(asctime)s] [%(levelname)s] %(message)s"
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(
        logging.Formatter(fmt=file_fmt, datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Log a section header with Nord theme styling.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a progress spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exiting the script.
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
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Ensure all required system commands are available.
    """
    required_commands = ["curl", "dpkg", "apt-get", "systemctl"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.error(
            f"Missing required commands: {', '.join(missing)}. Please install them and try again."
        )
        sys.exit(1)


def check_root():
    """
    Ensure the script is executed with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    """
    Execute a shell command and log its output.
    """
    log_cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.debug(f"Executing command: {log_cmd}")
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=text, **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed [{e.returncode}]: {log_cmd}")
        if capture_output:
            if e.stdout:
                logging.debug(f"Stdout: {e.stdout}")
            if e.stderr:
                logging.error(f"Stderr: {e.stderr}")
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
    logging.info("Starting Plex package download...")
    try:
        run_with_progress(
            "Downloading...", run_command, ["curl", "-L", "-o", TEMP_DEB, PLEX_URL]
        )
        logging.info("Plex package downloaded successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to download Plex package.")
        sys.exit(1)


def install_plex():
    """
    Install the Plex Media Server package and fix dependency issues if necessary.
    """
    print_section("Installing Plex Media Server")
    logging.info("Installing Plex Media Server...")
    try:
        run_with_progress("Installing...", run_command, ["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        logging.warning("Dependency issues detected. Attempting to fix dependencies...")
        try:
            run_with_progress(
                "Fixing Dependencies...",
                run_command,
                ["apt-get", "install", "-f", "-y"],
            )
            # Retry installation after fixing dependencies
            run_with_progress("Reinstalling...", run_command, ["dpkg", "-i", TEMP_DEB])
        except subprocess.CalledProcessError:
            logging.error("Failed to resolve dependencies for Plex.")
            sys.exit(1)
    logging.info("Plex Media Server installed successfully.")


def restart_plex():
    """
    Restart the Plex Media Server service.
    """
    print_section("Restarting Plex Media Server Service")
    logging.info("Restarting Plex Media Server...")
    try:
        run_with_progress(
            "Restarting Service...",
            run_command,
            ["systemctl", "restart", "plexmediaserver"],
        )
        logging.info("Plex Media Server service restarted successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to restart Plex Media Server service.")
        sys.exit(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main function to coordinate Plex update operations.
    """
    setup_logging()
    check_dependencies()
    check_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    download_plex()
    install_plex()
    restart_plex()

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
