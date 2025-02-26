#!/usr/bin/env python3
"""
ZFS Pool Resizer and Expander Script
-------------------------------------
Description:
  This script automates the process of resizing a ZFS pool partition to utilize the full disk space
  and expanding the ZFS pool accordingly.

  It performs the following steps:
    1. Retrieves the name of the ZFS pool.
    2. Extracts the device and partition information from the pool's status.
    3. Resizes the partition using 'parted' and updates the kernel partition table.
    4. Expands the ZFS pool to use the resized partition.

Usage:
  sudo ./zfs_resizer.py

Author: Your Name | License: MIT | Version: 1.0.0
"""

# ------------------------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------------------------
import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# CONFIGURATION & GLOBAL VARIABLES
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/zfs_resizer.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# Nord color theme for logging output (24-bit ANSI escape sequences)
NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"

# ------------------------------------------------------------------------------
# CUSTOM LOGGING SETUP
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """Custom formatter to add Nord color codes to logging output."""
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
    """Set up logging to console and file with Nord-themed formatting."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logging.warning("Continuing with console logging only")
    return logger

# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """Handle system signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else f"signal {signum}"
    logging.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

def cleanup():
    """Perform any necessary cleanup before exiting."""
    logging.info("Performing cleanup tasks before exit.")

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function with a rich progress spinner.
    
    Args:
        description (str): Description of the current task.
        func (callable): Function to run.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.
    
    Returns:
        The result of the function call.
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
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def run_command(command: str) -> str:
    """
    Run a system command and return its output.
    
    Args:
        command (str): The command to execute.
    
    Returns:
        str: Decoded standard output from the command.
    
    Raises:
        subprocess.CalledProcessError: If the command execution fails.
    """
    try:
        result = subprocess.run(
            command, check=True, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return result.stdout.decode().strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode().strip()
        logging.error(f"Error executing command: {command}\n{error_msg}")
        raise

def get_zfs_pool_name() -> str:
    """
    Retrieve the name of the ZFS pool.
    
    Returns:
        str: The ZFS pool name.
    
    Exits if no pool is found or if multiple pools are detected.
    """
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

def get_partition_info(pool_name: str) -> (str, str):
    """
    Get the device and partition number associated with the ZFS pool.
    
    Args:
        pool_name (str): The ZFS pool name.
    
    Returns:
        tuple: (device, partition) where 'device' is the disk and 'partition' is the partition identifier.
    
    Exits if no valid partition is found.
    """
    pool_status = run_command(f"zpool status {pool_name}")
    for line in pool_status.splitlines():
        if "/dev/" in line:
            device_info = line.split()[0]
            if "part" in device_info:
                # Expecting a device like /dev/sda-part1; split at the last occurrence of "p"
                device, partition = device_info.rsplit("p", 1)
            else:
                # Fallback: assume the last character is the partition
                device = device_info[:-1]
                partition = device_info[-1]
            logging.info(f"Found device: {device}, partition: {partition}")
            return device, partition
    logging.error("No valid partition found for the ZFS pool.")
    sys.exit(1)

def resize_partition(device: str, partition: str):
    """
    Resize the partition to utilize the full disk space.
    
    Args:
        device (str): The disk device (e.g. /dev/sda).
        partition (str): The partition identifier.
    """
    logging.info(f"Resizing partition {partition} on device {device}...")
    run_with_progress("Resizing partition...", run_command,
                      f"parted {device} resizepart {partition} 100%")
    run_with_progress("Updating partition table...", run_command, "partprobe")
    logging.info("Partition resized successfully.")

def expand_zfs_pool(pool_name: str, device: str, partition: str):
    """
    Expand the ZFS pool to use the resized partition.
    
    Args:
        pool_name (str): The ZFS pool name.
        device (str): The disk device.
        partition (str): The partition identifier.
    """
    logging.info(f"Expanding ZFS pool {pool_name}...")
    run_with_progress("Enabling autoexpand...", run_command,
                      f"zpool set autoexpand=on {pool_name}")
    # Construct the device string for the pool expansion command.
    device_str = f"{device}p{partition}"
    run_with_progress("Expanding pool online...", run_command,
                      f"zpool online -e {pool_name} {device_str}")
    logging.info("ZFS pool expanded successfully.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    setup_logging()
    logging.info("=" * 80)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"ZFS RESIZER STARTED AT {now}")
    logging.info("=" * 80)

    # Retrieve pool name and partition info
    pool_name = get_zfs_pool_name()
    device, partition = get_partition_info(pool_name)

    # Perform partition resize and pool expansion
    resize_partition(device, partition)
    expand_zfs_pool(pool_name, device, partition)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ZFS RESIZER COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)