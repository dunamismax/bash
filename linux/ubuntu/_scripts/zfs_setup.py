#!/usr/bin/env python3
"""
ZFS Setup Script

Installs ZFS packages and configures a ZFS pool for automatic mounting.

Steps:
1. Install ZFS packages and prerequisites
2. Enable ZFS services
3. Create mount point
4. Import ZFS pool
5. Configure pool mountpoint
6. Mount ZFS datasets

Usage:
  sudo python3 zfs_setup.py

Author: Anonymous | License: MIT | Version: 1.0.0
"""

import os
import sys
import logging
import subprocess
import shutil
import signal
from datetime import datetime


# Configuration Constants
ZPOOL_NAME = "WD_BLACK"
MOUNT_POINT = f"/media/{ZPOOL_NAME}"
CACHE_FILE = "/etc/zfs/zpool.cache"
LOG_FILE = "/var/log/zfs_setup.log"


def setup_logging():
    """Configure logging to console and file."""
    # Ensure log directory exists
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Secure log file permissions
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


def run_command(command, error_message=None):
    """
    Run a system command and return its output.

    Args:
        command (str or list): Command to execute
        error_message (str, optional): Custom error message if command fails

    Returns:
        str: Command output

    Raises:
        subprocess.CalledProcessError: If command execution fails
    """
    try:
        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip()
        logging.error(error_message or f"Command failed: {command}")
        logging.error(f"Error output: {error_output}")
        raise


def check_dependencies():
    """Check for required system commands."""
    required_commands = ["apt", "systemctl", "zpool", "zfs"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(f"Required command '{cmd}' is missing.")
            sys.exit(1)


def install_zfs_packages():
    """Update package lists and install ZFS packages."""
    logging.info("Installing ZFS packages")
    try:
        run_command("apt update")
        run_command("apt install -y dpkg-dev linux-headers-generic linux-image-generic")
        run_command("apt install -y zfs-dkms zfsutils-linux")
        logging.info("ZFS packages installed successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to install ZFS packages.")
        sys.exit(1)


def enable_zfs_services():
    """Enable ZFS import and mount services."""
    logging.info("Enabling ZFS services")
    services = ["zfs-import-cache.service", "zfs-mount.service"]
    for service in services:
        try:
            run_command(f"systemctl enable {service}")
            logging.info(f"Enabled {service}")
        except subprocess.CalledProcessError:
            logging.warning(f"Could not enable {service}")


def create_mount_point():
    """Create the mount point directory if it does not exist."""
    try:
        os.makedirs(MOUNT_POINT, exist_ok=True)
        logging.info(f"Created mount point: {MOUNT_POINT}")
    except Exception as e:
        logging.error(f"Failed to create mount point {MOUNT_POINT}: {e}")
        sys.exit(1)


def import_zfs_pool():
    """
    Import the ZFS pool if it is not already imported.

    Returns:
        bool: True if pool is imported or already present
    """
    try:
        # Check if pool is already imported
        run_command(f"zpool list {ZPOOL_NAME}")
        logging.info(f"ZFS pool '{ZPOOL_NAME}' is already imported.")
        return True
    except subprocess.CalledProcessError:
        logging.info(f"ZFS pool '{ZPOOL_NAME}' not found. Attempting to import...")

        try:
            run_command(f"zpool import -f {ZPOOL_NAME}")
            logging.info(f"Successfully imported ZFS pool '{ZPOOL_NAME}'.")
            return True
        except subprocess.CalledProcessError:
            logging.error(f"Failed to import ZFS pool '{ZPOOL_NAME}'.")
            return False


def configure_zfs_pool():
    """Set the pool's mountpoint property and update its cachefile."""
    try:
        run_command(f"zfs set mountpoint={MOUNT_POINT} {ZPOOL_NAME}")
        logging.info(f"Set mountpoint for '{ZPOOL_NAME}' to '{MOUNT_POINT}'.")

        run_command(f"zpool set cachefile={CACHE_FILE} {ZPOOL_NAME}")
        logging.info(f"Updated cachefile for '{ZPOOL_NAME}' to '{CACHE_FILE}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to configure ZFS pool: {e}")
        sys.exit(1)


def mount_zfs_datasets():
    """Mount all ZFS datasets."""
    try:
        run_command("zfs mount -a")
        logging.info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Some ZFS datasets may not have mounted: {e}")


def verify_mount():
    """
    Verify that the ZFS pool is mounted at the expected mount point.

    Returns:
        bool: True if the pool is mounted correctly
    """
    try:
        output = run_command("zfs list -o name,mountpoint -H")
        for line in output.splitlines():
            if ZPOOL_NAME in line and MOUNT_POINT in line:
                logging.info(f"ZFS pool '{ZPOOL_NAME}' is mounted at '{MOUNT_POINT}'.")
                return True

        logging.warning(f"ZFS pool '{ZPOOL_NAME}' is not mounted at '{MOUNT_POINT}'.")
        logging.info("Current ZFS mounts:")
        for line in output.splitlines():
            logging.info(f"  {line}")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error verifying mount status: {e}")
        return False


def main():
    """Main script execution."""
    # Verify Python version
    if sys.version_info < (3, 6):
        print("ERROR: This script requires Python 3.6 or higher.", file=sys.stderr)
        sys.exit(1)

    # Verify root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.", file=sys.stderr)
        sys.exit(1)

    # Set up signal handling for graceful exit
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(143))

    # Initialize logging
    setup_logging()

    # Log start time
    start_time = datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        # Perform ZFS setup steps
        check_dependencies()
        install_zfs_packages()
        enable_zfs_services()
        create_mount_point()

        # Import and configure pool
        if import_zfs_pool():
            configure_zfs_pool()
            mount_zfs_datasets()

            # Verify mount
            if not verify_mount():
                logging.warning(
                    "ZFS pool verification failed. Check mount status manually."
                )
        else:
            logging.error(f"Aborting: ZFS pool '{ZPOOL_NAME}' could not be imported.")
            sys.exit(1)

        # Log completion
        end_time = datetime.now()
        logging.info("=" * 60)
        logging.info(f"ZFS SETUP COMPLETED SUCCESSFULLY AT {end_time}")
        logging.info("=" * 60)

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
