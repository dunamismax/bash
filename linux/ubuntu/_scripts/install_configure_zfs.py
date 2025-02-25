#!/usr/bin/env python3
"""
Standalone script to install ZFS packages and configure the ZFS pool 'WD_BLACK'
to automatically mount at /media/WD_BLACK on Ubuntu.

This script:
  - Checks that it is run as root.
  - Updates the package lists and installs prerequisites along with ZFS packages.
  - Enables ZFS import and mount services.
  - Creates the mount point (/media/WD_BLACK) if needed.
  - Imports the ZFS pool if not already imported.
  - Sets the mountpoint property for the pool.
  - Updates the pool cachefile so the pool is auto-imported at boot.
  - Attempts to mount all ZFS datasets.
  - Verifies that the pool is mounted correctly.
"""

import os
import sys
import subprocess
import logging
import shutil

# ----------------------------
# Logging Setup
# ----------------------------

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_info(message: str) -> None:
    logger.info(message)

def log_warn(message: str) -> None:
    logger.warning(message)

def log_error(message: str) -> None:
    logger.error(message)

def print_section(title: str) -> None:
    border = "─" * 60
    log_info(border)
    log_info(f"  {title}")
    log_info(border)

# ----------------------------
# Utility Functions
# ----------------------------

def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    """
    Execute a shell command.
    """
    command_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    log_info(f"Executing command: {command_str}")
    result = subprocess.run(cmd, check=check, capture_output=capture_output, text=text, **kwargs)
    return result

def command_exists(cmd: str) -> bool:
    """Check if a command exists in the system's PATH."""
    return shutil.which(cmd) is not None

def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        log_error("This script must be run as root. Exiting.")
        sys.exit(1)

# ----------------------------
# ZFS Installation and Configuration
# ----------------------------

def install_configure_zfs() -> None:
    """
    Install and configure ZFS for external pool 'WD_BLACK' with mount point '/media/WD_BLACK'.

    The function:
      - Updates package lists and installs prerequisites and ZFS packages.
      - Enables the ZFS import and mount services.
      - Creates the desired mount point directory.
      - Imports the ZFS pool (if not already imported).
      - Sets the mountpoint property on the pool.
      - Updates the pool cachefile property to ensure auto-import at boot.
      - Mounts all ZFS datasets and verifies the mount.
    """
    print_section("ZFS Installation and Configuration")
    zpool_name = "WD_BLACK"
    mount_point = f"/media/{zpool_name}"
    cache_file = "/etc/zfs/zpool.cache"

    # Update package lists and install prerequisites
    try:
        run_command(["apt", "update"])
        run_command(["apt", "install", "-y", "dpkg-dev", "linux-headers-generic", "linux-image-generic"])
        run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])
        log_info("Prerequisites and ZFS packages installed successfully.")
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to install prerequisites or ZFS packages: {e}")
        sys.exit(1)

    # Enable ZFS services (import and mount)
    for service in ["zfs-import-cache.service", "zfs-mount.service"]:
        try:
            run_command(["systemctl", "enable", service])
            log_info(f"Enabled {service}.")
        except subprocess.CalledProcessError:
            log_warn(f"Could not enable {service}.")

    # Ensure the mount point directory exists
    if not os.path.isdir(mount_point):
        try:
            os.makedirs(mount_point, exist_ok=True)
            log_info(f"Created mount point directory: {mount_point}")
        except Exception as e:
            log_warn(f"Failed to create mount point directory {mount_point}: {e}")

    # Import the pool if it is not already imported
    pool_imported = False
    try:
        subprocess.run(
            ["zpool", "list", zpool_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log_info(f"ZFS pool '{zpool_name}' is already imported.")
        pool_imported = True
    except subprocess.CalledProcessError:
        try:
            run_command(["zpool", "import", "-f", zpool_name])
            log_info(f"Imported ZFS pool '{zpool_name}'.")
            pool_imported = True
        except subprocess.CalledProcessError:
            log_warn(f"ZFS pool '{zpool_name}' not found or failed to import.")

    if not pool_imported:
        log_error(f"ZFS pool '{zpool_name}' could not be imported. Exiting configuration.")
        sys.exit(1)

    # Set the mountpoint property on the pool/dataset
    try:
        run_command(["zfs", "set", f"mountpoint={mount_point}", zpool_name])
        log_info(f"Set mountpoint for pool '{zpool_name}' to '{mount_point}'.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to set mountpoint for ZFS pool '{zpool_name}': {e}")

    # Update the pool cachefile so it is recorded for auto-import at boot
    try:
        run_command(["zpool", "set", f"cachefile={cache_file}", zpool_name])
        log_info(f"Updated cachefile for pool '{zpool_name}' to '{cache_file}'.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to update cachefile for ZFS pool '{zpool_name}': {e}")

    # Attempt to mount all ZFS datasets
    try:
        run_command(["zfs", "mount", "-a"])
        log_info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to mount ZFS datasets: {e}")

    # Verify that the pool is mounted at the desired mount point
    try:
        mounts = subprocess.check_output(["zfs", "list", "-o", "name,mountpoint", "-H"], text=True)
        if any(mount_point in line for line in mounts.splitlines()):
            log_info(f"ZFS pool '{zpool_name}' is successfully mounted at '{mount_point}'.")
        else:
            log_warn(f"ZFS pool '{zpool_name}' is not mounted at '{mount_point}'. Please check manually.")
    except Exception as e:
        log_warn(f"Error verifying mount status for ZFS pool '{zpool_name}': {e}")

# ----------------------------
# Main Execution Flow
# ----------------------------

def main() -> None:
    check_root()
    install_configure_zfs()

if __name__ == "__main__":
    main()
