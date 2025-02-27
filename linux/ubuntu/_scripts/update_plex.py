#!/usr/bin/env python3
"""
Script Name: update_plex.py
--------------------------------------------------------
Description:
  A standard library-based script that downloads and installs the
  latest Plex Media Server package, fixes dependency issues, cleans up
  temporary files, and restarts the Plex service.

Usage:
  sudo ./update_plex.py

Author: Your Name | License: MIT | Version: 1.0.0
"""

import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
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
DEFAULT_LOG_LEVEL = logging.INFO


# ------------------------------------------------------------------------------
# CUSTOM LOGGING SETUP
# ------------------------------------------------------------------------------
def setup_logging():
    """
    Set up logging with both console and file handlers.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=DEFAULT_LOG_LEVEL,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )

    # Attempt to set secure log file permissions
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logging.getLogger()


def print_section(title: str):
    """
    Log a section header.
    """
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
    missing = []

    for cmd in required_commands:
        try:
            subprocess.run(
                ["which", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError:
            missing.append(cmd)

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
def run_command(cmd, check=True, capture_output=False):
    """
    Execute a shell command and log its output.
    """
    log_cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.info(f"Executing command: {log_cmd}")
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        if result.stdout:
            logging.info(f"Command output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed [{e.returncode}]: {log_cmd}")
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
    Download the Plex Media Server package using urllib.
    """
    print_section("Downloading Plex Media Server Package")
    logging.info("Starting Plex package download...")

    try:
        logging.info(f"Downloading from: {PLEX_URL}")
        logging.info(f"Saving to: {TEMP_DEB}")

        # Create parent directory if it doesn't exist
        os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)

        # Download the file
        start_time = time.time()
        urllib.request.urlretrieve(PLEX_URL, TEMP_DEB)

        # Log download details
        download_time = time.time() - start_time
        file_size = os.path.getsize(TEMP_DEB)
        logging.info(f"Download completed in {download_time:.2f} seconds")
        logging.info(f"File size: {file_size / (1024 * 1024):.2f} MB")

    except Exception as e:
        logging.error(f"Failed to download Plex package: {e}")
        sys.exit(1)


def install_plex():
    """
    Install the Plex Media Server package and fix dependency issues if necessary.
    """
    print_section("Installing Plex Media Server")
    logging.info("Installing Plex Media Server...")
    try:
        # Attempt initial installation
        run_command(["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        logging.warning("Dependency issues detected. Attempting to fix dependencies...")
        try:
            # Fix dependencies
            run_command(["apt-get", "install", "-f", "-y"])

            # Retry installation
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
    logging.info("Restarting Plex Media Server...")
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
        logging.error(f"Unhandled exception: {ex}", exc_info=True)
        sys.exit(1)
