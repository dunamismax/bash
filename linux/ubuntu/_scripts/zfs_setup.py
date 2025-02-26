#!/usr/bin/env python3
"""
ZFS Setup Script
----------------
Description:
  A robust and visually engaging script to install ZFS packages and configure
  the ZFS pool 'WD_BLACK' so that it automatically mounts at /media/WD_BLACK on
  Ubuntu systems. The script performs the following tasks:
    - Verifies that it is run as root and checks for necessary dependencies.
    - Updates package lists and installs prerequisites and ZFS packages.
    - Enables ZFS import and mount services.
    - Creates the mount point (/media/WD_BLACK) if missing.
    - Imports the ZFS pool if it isn’t already imported.
    - Configures the pool’s mountpoint property and updates the cachefile.
    - Attempts to mount all ZFS datasets and verifies that the pool is mounted.

Usage:
  sudo ./zfs_setup.py

Author: YourName | License: MIT | Version: 1.1.0
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/zfs_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ZFS Configuration
ZPOOL_NAME = "WD_BLACK"
MOUNT_POINT = f"/media/{ZPOOL_NAME}"
CACHE_FILE = "/etc/zfs/zpool.cache"

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARNING)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color


# ------------------------------------------------------------------------------
# CUSTOM LOGGING SETUP
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom formatter that applies the Nord color theme to log messages.
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
    Configure logging to output to both console (with Nord colors) and a log file.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Clear any pre-existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (without colors)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a formatted section header using the Nord theme.
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
    Execute a blocking function with a progress spinner.
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
    Gracefully handle termination signals.
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
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup steps can be added here.


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY AND PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Check that required system commands exist.
    """
    required_cmds = ["apt", "systemctl", "zpool", "zfs"]
    missing = [cmd for cmd in required_cmds if not shutil.which(cmd)]
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
    logging.debug("Running with root privileges.")


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def run_command(cmd, check=True, capture_output=False, text=True):
    """
    Execute a shell command and return the CompletedProcess.
    """
    command_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.debug(f"Executing: {command_str}")
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=text
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{command_str}' failed with error: {e}")
        if check:
            raise
        return e


# ------------------------------------------------------------------------------
# ZFS INSTALLATION & CONFIGURATION FUNCTIONS
# ------------------------------------------------------------------------------
def install_zfs_packages():
    """
    Update package lists and install prerequisites and ZFS packages.
    """
    print_section("Installing ZFS Packages")
    try:
        run_with_progress("Updating package lists...", run_command, ["apt", "update"])
        run_with_progress(
            "Installing prerequisites...",
            run_command,
            [
                "apt",
                "install",
                "-y",
                "dpkg-dev",
                "linux-headers-generic",
                "linux-image-generic",
            ],
        )
        run_with_progress(
            "Installing ZFS packages...",
            run_command,
            ["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"],
        )
        logging.info("ZFS packages installed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install ZFS packages: {e}")
        sys.exit(1)


def enable_zfs_services():
    """
    Enable ZFS import and mount services.
    """
    print_section("Enabling ZFS Services")
    services = ["zfs-import-cache.service", "zfs-mount.service"]
    for svc in services:
        try:
            run_with_progress(
                f"Enabling {svc}...", run_command, ["systemctl", "enable", svc]
            )
            logging.info(f"Enabled {svc}.")
        except subprocess.CalledProcessError:
            logging.warning(
                f"Could not enable {svc}; auto-mounting may not work properly."
            )


def create_mount_point():
    """
    Create the mount point directory if it does not exist.
    """
    print_section("Creating Mount Point")
    if not os.path.isdir(MOUNT_POINT):
        try:
            os.makedirs(MOUNT_POINT, exist_ok=True)
            logging.info(f"Created mount point: {MOUNT_POINT}")
        except Exception as e:
            logging.error(f"Failed to create mount point {MOUNT_POINT}: {e}")
            sys.exit(1)
    else:
        logging.info(f"Mount point {MOUNT_POINT} already exists.")


def import_zfs_pool():
    """
    Import the ZFS pool if it is not already imported.
    Returns:
        bool: True if the pool is imported or already present; False otherwise.
    """
    print_section("Importing ZFS Pool")
    # Check if pool is already imported
    try:
        run_command(["zpool", "list", ZPOOL_NAME], capture_output=True)
        logging.info(f"ZFS pool '{ZPOOL_NAME}' is already imported.")
        return True
    except subprocess.CalledProcessError:
        logging.info(f"ZFS pool '{ZPOOL_NAME}' not found among imported pools.")
    # Attempt to import the pool
    try:
        run_with_progress(
            "Importing pool...", run_command, ["zpool", "import", "-f", ZPOOL_NAME]
        )
        logging.info(f"Successfully imported ZFS pool '{ZPOOL_NAME}'.")
        return True
    except subprocess.CalledProcessError:
        logging.error(
            f"Failed to import ZFS pool '{ZPOOL_NAME}'. Is the drive connected?"
        )
        return False


def configure_zfs_pool():
    """
    Set the pool's mountpoint property and update its cachefile.
    """
    print_section("Configuring ZFS Pool")
    try:
        run_with_progress(
            "Setting mountpoint...",
            run_command,
            ["zfs", "set", f"mountpoint={MOUNT_POINT}", ZPOOL_NAME],
        )
        logging.info(f"Set mountpoint for '{ZPOOL_NAME}' to '{MOUNT_POINT}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to set mountpoint: {e}")
        sys.exit(1)
    try:
        run_with_progress(
            "Updating pool cachefile...",
            run_command,
            ["zpool", "set", f"cachefile={CACHE_FILE}", ZPOOL_NAME],
        )
        logging.info(f"Updated cachefile for '{ZPOOL_NAME}' to '{CACHE_FILE}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to update cachefile: {e}")
        sys.exit(1)


def mount_zfs_datasets():
    """
    Mount all ZFS datasets.
    """
    print_section("Mounting ZFS Datasets")
    try:
        run_with_progress("Mounting datasets...", run_command, ["zfs", "mount", "-a"])
        logging.info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Some ZFS datasets may not have mounted: {e}")


def verify_mount():
    """
    Verify that the ZFS pool is mounted at the expected mount point.
    Returns:
        bool: True if the pool is mounted correctly, False otherwise.
    """
    print_section("Verifying ZFS Mount")
    try:
        output = run_command(
            ["zfs", "list", "-o", "name,mountpoint", "-H"], capture_output=True
        ).stdout
        for line in output.splitlines():
            if ZPOOL_NAME in line and MOUNT_POINT in line:
                logging.info(
                    f"✓ ZFS pool '{ZPOOL_NAME}' is mounted at '{MOUNT_POINT}'."
                )
                return True
        logging.warning(f"⚠ ZFS pool '{ZPOOL_NAME}' is not mounted at '{MOUNT_POINT}'.")
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
    logging.info(f"ZFS SETUP STARTED AT {now}")
    logging.info("=" * 80)

    install_zfs_packages()
    enable_zfs_services()
    create_mount_point()

    if import_zfs_pool():
        configure_zfs_pool()
        mount_zfs_datasets()
        if not verify_mount():
            logging.warning(
                "ZFS pool verification failed. Please check the mount status manually."
            )
    else:
        logging.error(
            f"Aborting configuration: ZFS pool '{ZPOOL_NAME}' could not be imported."
        )
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ZFS SETUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
