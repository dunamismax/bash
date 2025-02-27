#!/usr/bin/env python3
"""
ZFS Pool Resizer and Expander Script

Automates the process of resizing a ZFS pool partition to utilize full disk space.

Steps:
1. Retrieves the name of the ZFS pool
2. Extracts device and partition information
3. Resizes the partition using system commands
4. Expands the ZFS pool to use the resized partition

Usage:
  sudo python3 zfs_resizer.py

Author: Anonymous | License: MIT | Version: 1.0.0
"""

import os
import sys
import logging
import subprocess
import signal
from datetime import datetime


def setup_logging():
    """Configure logging to console and file."""
    log_file = "/var/log/zfs_resizer.log"

    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Secure log file permissions
    try:
        os.chmod(log_file, 0o600)
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


def run_command(command, error_message=None):
    """
    Run a system command and return its output.

    Args:
        command (str): Command to execute
        error_message (str, optional): Custom error message if command fails

    Returns:
        str: Command output

    Raises:
        subprocess.CalledProcessError: If command execution fails
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
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


def get_zfs_pool_name():
    """
    Retrieve the name of the ZFS pool.

    Returns:
        str: The ZFS pool name
    """
    try:
        pools = run_command("zpool list -H -o name").splitlines()

        if not pools:
            logging.error("No ZFS pools found.")
            sys.exit(1)

        if len(pools) > 1:
            logging.error("Multiple ZFS pools found. Please specify the pool name.")
            sys.exit(1)

        pool_name = pools[0]
        logging.info(f"Detected ZFS pool: {pool_name}")
        return pool_name

    except subprocess.CalledProcessError:
        logging.error("Failed to list ZFS pools.")
        sys.exit(1)


def get_partition_info(pool_name):
    """
    Get the device and partition number associated with the ZFS pool.

    Args:
        pool_name (str): The ZFS pool name

    Returns:
        tuple: (device, partition)
    """
    try:
        pool_status = run_command(f"zpool status {pool_name}")

        for line in pool_status.splitlines():
            if "/dev/" in line:
                device_info = line.split()[0]

                # Attempt to extract device and partition
                if "part" in device_info:
                    # Handle cases like /dev/sda1 or /dev/nvme0n1p1
                    if "p" in device_info:
                        device, partition = device_info.rsplit("p", 1)
                    else:
                        device = device_info[:-1]
                        partition = device_info[-1]
                else:
                    # Fallback for simple device names
                    device = device_info[:-1]
                    partition = device_info[-1]

                logging.info(f"Found device: {device}, partition: {partition}")
                return device, partition

        logging.error("No valid partition found for the ZFS pool.")
        sys.exit(1)

    except subprocess.CalledProcessError:
        logging.error("Failed to get ZFS pool status.")
        sys.exit(1)


def resize_partition(device, partition):
    """
    Resize the partition to utilize the full disk space.

    Args:
        device (str): The disk device
        partition (str): The partition identifier
    """
    logging.info(f"Resizing partition {partition} on device {device}...")

    try:
        # Resize partition
        run_command(
            f"parted {device} resizepart {partition} 100%", "Failed to resize partition"
        )

        # Update kernel partition table
        run_command("partprobe", "Failed to update partition table")

        logging.info("Partition resized successfully.")

    except subprocess.CalledProcessError:
        logging.error("Partition resize failed.")
        sys.exit(1)


def expand_zfs_pool(pool_name, device, partition):
    """
    Expand the ZFS pool to use the resized partition.

    Args:
        pool_name (str): The ZFS pool name
        device (str): The disk device
        partition (str): The partition identifier
    """
    logging.info(f"Expanding ZFS pool {pool_name}...")

    try:
        # Enable autoexpand
        run_command(
            f"zpool set autoexpand=on {pool_name}", "Failed to enable autoexpand"
        )

        # Construct device string for pool expansion
        device_str = (
            f"{device}p{partition}" if "p" in device else f"{device}{partition}"
        )

        # Expand pool online
        run_command(
            f"zpool online -e {pool_name} {device_str}", "Failed to expand ZFS pool"
        )

        logging.info("ZFS pool expanded successfully.")

    except subprocess.CalledProcessError:
        logging.error("ZFS pool expansion failed.")
        sys.exit(1)


def main():
    """Main script execution."""
    # Set up signal handling for graceful exit
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(143))

    # Verify root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Initialize logging
    setup_logging()

    # Log start time
    start_time = datetime.now()
    logging.info("=" * 60)
    logging.info(f"ZFS RESIZER STARTED AT {start_time}")
    logging.info("=" * 60)

    try:
        # Perform ZFS pool resize
        pool_name = get_zfs_pool_name()
        device, partition = get_partition_info(pool_name)
        resize_partition(device, partition)
        expand_zfs_pool(pool_name, device, partition)

        # Log completion
        end_time = datetime.now()
        logging.info("=" * 60)
        logging.info(f"ZFS RESIZER COMPLETED SUCCESSFULLY AT {end_time}")
        logging.info("=" * 60)

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
