#!/usr/bin/env python3
"""
Script Name: zfs_setup.py
--------------------------------------------------------
Description:
  A robust, visually engaging script to install ZFS packages and
  configure the ZFS pool 'WD_BLACK' to automatically mount at
  /media/WD_BLACK on Ubuntu systems.

  This script:
  - Checks that it is run as root
  - Updates package lists and installs ZFS packages
  - Enables ZFS import and mount services
  - Creates mount point (/media/WD_BLACK) if needed
  - Imports the ZFS pool if not already imported
  - Sets the mountpoint property for the pool
  - Updates the pool cachefile for auto-import at boot
  - Attempts to mount all ZFS datasets
  - Verifies that the pool is mounted correctly

Usage:
  sudo ./zfs_setup.py

Author: YourName | License: MIT | Version: 1.0.0
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
LOG_FILE = "/var/log/zfs_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ZFS Configuration
ZPOOL_NAME = "WD_BLACK"
MOUNT_POINT = f"/media/{ZPOOL_NAME}"
CACHE_FILE = "/etc/zfs/zpool.cache"

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
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

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
    # Additional cleanup tasks can be added here


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["apt", "systemctl"]
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
    Execute a shell command and log the results.

    Args:
        cmd: Command to execute (list or string)
        check: If True, raises CalledProcessError if return code is non-zero
        capture_output: If True, captures stdout and stderr
        text: If True, returns string output instead of bytes
        **kwargs: Additional arguments to pass to subprocess.run

    Returns:
        CompletedProcess instance
    """
    command_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.debug(f"Executing command: {command_str}")

    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=text, **kwargs
        )
        if result.returncode == 0:
            logging.debug(f"Command executed successfully with return code 0")
        else:
            logging.warning(f"Command returned non-zero exit code: {result.returncode}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}: {e}")
        if check:
            raise
        return e


# ------------------------------------------------------------------------------
# ZFS INSTALLATION AND CONFIGURATION FUNCTIONS
# ------------------------------------------------------------------------------


def install_zfs_packages():
    """
    Update package lists and install ZFS packages.
    """
    print_section("Installing ZFS Packages")

    try:
        logging.info("Updating package lists...")
        run_command(["apt", "update"])

        logging.info("Installing prerequisites...")
        run_command(
            [
                "apt",
                "install",
                "-y",
                "dpkg-dev",
                "linux-headers-generic",
                "linux-image-generic",
            ]
        )

        logging.info("Installing ZFS packages...")
        run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])

        logging.info("ZFS packages installed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install ZFS packages: {e}")
        sys.exit(1)


def enable_zfs_services():
    """
    Enable ZFS import and mount services.
    """
    print_section("Enabling ZFS Services")

    for service in ["zfs-import-cache.service", "zfs-mount.service"]:
        try:
            run_command(["systemctl", "enable", service])
            logging.info(f"Enabled {service}.")
        except subprocess.CalledProcessError:
            logging.warning(
                f"Could not enable {service}. ZFS auto-mounting may not work properly."
            )


def create_mount_point():
    """
    Create the mount point directory if it doesn't exist.
    """
    print_section("Creating Mount Point")

    if not os.path.isdir(MOUNT_POINT):
        try:
            os.makedirs(MOUNT_POINT, exist_ok=True)
            logging.info(f"Created mount point directory: {MOUNT_POINT}")
        except Exception as e:
            logging.error(f"Failed to create mount point directory {MOUNT_POINT}: {e}")
            sys.exit(1)
    else:
        logging.info(f"Mount point directory {MOUNT_POINT} already exists.")


def import_zfs_pool():
    """
    Import the ZFS pool if it's not already imported.
    Returns:
        bool: True if pool is imported successfully, False otherwise
    """
    print_section("Importing ZFS Pool")

    # Check if pool is already imported
    try:
        subprocess.run(
            ["zpool", "list", ZPOOL_NAME],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info(f"ZFS pool '{ZPOOL_NAME}' is already imported.")
        return True
    except subprocess.CalledProcessError:
        logging.info(f"ZFS pool '{ZPOOL_NAME}' not found in imported pools list.")

    # Try to import the pool
    try:
        run_command(["zpool", "import", "-f", ZPOOL_NAME])
        logging.info(f"Successfully imported ZFS pool '{ZPOOL_NAME}'.")
        return True
    except subprocess.CalledProcessError:
        logging.error(
            f"ZFS pool '{ZPOOL_NAME}' could not be imported. Is the drive connected?"
        )
        return False


def configure_zfs_pool():
    """
    Configure the ZFS pool mountpoint and cachefile.
    """
    print_section("Configuring ZFS Pool")

    # Set the mountpoint property
    try:
        run_command(["zfs", "set", f"mountpoint={MOUNT_POINT}", ZPOOL_NAME])
        logging.info(f"Set mountpoint for pool '{ZPOOL_NAME}' to '{MOUNT_POINT}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to set mountpoint for ZFS pool '{ZPOOL_NAME}': {e}")
        sys.exit(1)

    # Update the pool cachefile
    try:
        run_command(["zpool", "set", f"cachefile={CACHE_FILE}", ZPOOL_NAME])
        logging.info(f"Updated cachefile for pool '{ZPOOL_NAME}' to '{CACHE_FILE}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to update cachefile for ZFS pool '{ZPOOL_NAME}': {e}")
        sys.exit(1)


def mount_zfs_datasets():
    """
    Mount all ZFS datasets.
    """
    print_section("Mounting ZFS Datasets")

    try:
        run_command(["zfs", "mount", "-a"])
        logging.info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to mount some ZFS datasets: {e}")


def verify_mount():
    """
    Verify that the ZFS pool is mounted correctly.
    """
    print_section("Verifying ZFS Mount")

    try:
        output = subprocess.check_output(
            ["zfs", "list", "-o", "name,mountpoint", "-H"], text=True
        )

        for line in output.splitlines():
            if ZPOOL_NAME in line and MOUNT_POINT in line:
                logging.info(
                    f"✓ ZFS pool '{ZPOOL_NAME}' is successfully mounted at '{MOUNT_POINT}'."
                )
                return True

        logging.warning(
            f"⚠ ZFS pool '{ZPOOL_NAME}' appears to be not mounted at '{MOUNT_POINT}'."
        )
        logging.info("Current ZFS mounts:")
        for line in output.splitlines():
            logging.info(f"  {line}")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error verifying mount status: {e}")
        return False


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    # Check Python version
    if sys.version_info < (3, 6):
        print(
            f"{NORD11}ERROR: This script requires Python 3.6 or higher.{NC}",
            file=sys.stderr,
        )
        sys.exit(1)

    setup_logging()
    check_root()
    check_dependencies()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ZFS INSTALLATION AND CONFIGURATION STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main functions
    install_zfs_packages()
    enable_zfs_services()
    create_mount_point()

    if import_zfs_pool():
        configure_zfs_pool()
        mount_zfs_datasets()
        verify_mount()
    else:
        logging.error(
            f"Cannot proceed with configuration since ZFS pool '{ZPOOL_NAME}' could not be imported."
        )
        sys.exit(1)

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ZFS INSTALLATION AND CONFIGURATION COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
