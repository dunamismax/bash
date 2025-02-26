#!/usr/bin/env python3
"""
Script Name: secure_disk_eraser.py
--------------------------------------------------------
Description:
  An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
  This script installs required tools, lists attached disks with details,
  detects whether a disk is an HDD, SSD, or NVMe, and lets the user choose
  from several secure erasure methods (using hdparm, nvme-cli, or shred).
  It includes robust interactive prompts with double‑check confirmations.

Usage:
  sudo ./secure_disk_eraser.py

Author: YourName | License: MIT | Version: 2.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/secure_disk_eraser.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# Required tools for disk erasure
REQUIRED_TOOLS = ["hdparm", "nvme", "shred", "lsblk", "apt"]

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
    # Additional cleanup tasks can be added here


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    missing_tools = []
    for cmd in REQUIRED_TOOLS:
        if not shutil.which(cmd):
            missing_tools.append(cmd)

    if missing_tools:
        logging.warning(
            f"The following required tools are missing: {', '.join(missing_tools)}"
        )
        return False
    return True


def install_prerequisites():
    """
    Install required tools if they're missing.
    """
    print_section("Installing Required Tools")
    logging.info("Updating package repositories...")
    run_cmd(["apt", "update"])
    logging.info("Installing required tools (hdparm, nvme-cli, coreutils)...")
    run_cmd(["apt", "install", "-y", "hdparm", "nvme-cli", "coreutils"])
    logging.info("Prerequisites installed.")


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


def prompt_enter():
    """
    Prompt the user to press Enter to continue.
    """
    input("Press Enter to continue...")


def run_cmd(cmd, capture_output=False, check=True):
    """
    Run a shell command with optional dry-run mode.
    """
    logging.debug(f"Executing command: {' '.join(cmd)}")
    if DRY_RUN:
        logging.info(f"DRY RUN: Command not executed: {' '.join(cmd)}")
        return None
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}\nError: {e}")
        return None


def is_mounted(disk: str) -> bool:
    """
    Check if a disk device is mounted (warn user if so).
    """
    mounts = subprocess.run(["mount"], capture_output=True, text=True).stdout
    return disk in mounts


# ------------------------------------------------------------------------------
# DISK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------


def list_disks() -> str:
    """
    List all available disks with their details.
    """
    result = run_cmd(
        ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,MOUNTPOINT"],
        capture_output=True,
    )
    return result.stdout if result else ""


def detect_disk_type(disk: str) -> str:
    """
    Detect whether a disk is an HDD, SSD, or NVMe.
    """
    if disk.startswith("nvme"):
        return "nvme"
    rotational_path = f"/sys/block/{disk}/queue/rotational"
    if os.path.exists(rotational_path):
        try:
            with open(rotational_path) as f:
                rota = f.read().strip()
            return "hdd" if rota == "1" else "ssd"
        except Exception:
            return "unknown"
    return "unknown"


def select_disk() -> str:
    """
    Display available disks and let the user select one for erasure.
    """
    logging.info("Scanning for attached disks...")
    disks_out = list_disks()
    if not disks_out.strip():
        logging.error("No disks found on the system.")
        sys.exit(1)

    print(f"{NORD10}Attached Disks:{NC}")
    print(f"{NORD10}{'-' * 50}{NC}")

    disk_map = {}
    lines = disks_out.strip().splitlines()[1:]  # skip header
    for i, line in enumerate(lines, start=1):
        parts = line.split()
        # Expected fields: NAME, SIZE, TYPE, ROTA, MODEL, [MOUNTPOINT]
        if len(parts) < 5:
            continue
        name, size, _, _, model = parts[:5]
        mountpoint = parts[5] if len(parts) >= 6 else ""
        disk_type = detect_disk_type(name)
        extra = f", Mounted: {mountpoint}" if mountpoint and mountpoint != "-" else ""
        print(
            f"{NORD10}[{i}]{NC} /dev/{name} - Size: {size}, Type: {disk_type}, Model: {model}{extra}"
        )
        disk_map[str(i)] = name

    print(f"{NORD10}{'-' * 50}{NC}")
    while True:
        choice = input(
            "Enter the number of the disk to erase (or 'q' to quit): "
        ).strip()
        if choice.lower() == "q":
            print(f"{NORD14}Exiting...{NC}")
            sys.exit(0)
        if choice in disk_map:
            selected = f"/dev/{disk_map[choice]}"
            logging.info(f"Selected disk: {selected}")
            if is_mounted(selected):
                logging.warning(f"Warning: {selected} appears to be mounted!")
                confirm = input(
                    "This disk is mounted. Are you sure you want to continue? (yes/no): "
                )
                if confirm.lower() != "yes":
                    logging.info("Operation cancelled by user.")
                    sys.exit(0)
            return selected
        else:
            print(f"{NORD13}Invalid selection. Please try again.{NC}")


# ------------------------------------------------------------------------------
# DISK ERASURE METHODS
# ------------------------------------------------------------------------------


def secure_erase_hdparm(disk: str):
    """
    Securely erase a disk using hdparm secure erase command.
    """
    print(f"{NORD14}Preparing to securely erase {disk} using hdparm...{NC}")
    sec_pass = input("Enter a temporary security password (will be cleared): ").strip()
    print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return

    # Execute hdparm commands
    logging.info(f"Setting security password for {disk}")
    run_cmd(["hdparm", "--user-master", "u", "--security-set-pass", sec_pass, disk])

    logging.info(f"Executing secure erase on {disk}")
    run_cmd(["hdparm", "--user-master", "u", "--security-erase", sec_pass, disk])

    logging.info(f"Secure Erase via hdparm completed successfully on {disk}.")
    print(f"{NORD14}Secure Erase via hdparm completed successfully on {disk}.{NC}")


def nvme_secure_erase(disk: str):
    """
    Format an NVMe drive using nvme-cli.
    """
    print(f"{NORD14}Preparing to format NVMe drive {disk} using nvme-cli...{NC}")
    print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return

    logging.info(f"Executing NVMe format on {disk}")
    run_cmd(["nvme", "format", disk])

    logging.info(f"NVMe format completed successfully on {disk}.")
    print(f"{NORD14}NVMe format completed successfully on {disk}.{NC}")


def shred_wipe(disk: str):
    """
    Wipe a disk using shred with multiple overwrites.
    """
    try:
        num_overwrites = int(
            input("Enter number of overwrites (recommended 3): ").strip()
        )
    except ValueError:
        print(f"{NORD13}Invalid input; defaulting to 3 overwrites.{NC}")
        num_overwrites = 3

    print(
        f"{NORD14}Preparing to wipe {disk} using shred with {num_overwrites} passes...{NC}"
    )
    print(
        f"{NORD13}WARNING: This operation is irreversible and may take a long time.{NC}"
    )
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return

    logging.info(f"Executing shred with {num_overwrites} passes on {disk}")
    run_cmd(["shred", "-n", str(num_overwrites), "-z", "-v", disk])

    logging.info(f"Disk wipe with shred completed successfully on {disk}.")
    print(f"{NORD14}Disk wipe with shred completed successfully on {disk}.{NC}")


# ------------------------------------------------------------------------------
# DISK ERASER MENU
# ------------------------------------------------------------------------------


def disk_eraser_menu():
    """
    Display the menu for selecting the disk erasure method.
    """
    selected_disk = select_disk()
    disk_basename = os.path.basename(selected_disk)
    disk_type = detect_disk_type(disk_basename)

    print(f"{NORD10}Detected disk type: {disk_type}{NC}")
    print(f"{NORD10}Select the erasure method:{NC}")

    # For NVMe drives offer NVMe format; for others offer hdparm and shred.
    if disk_type == "nvme":
        print(f"{NORD10}[1]{NC} NVMe Format (nvme-cli)")
        print(f"{NORD10}[2]{NC} Shred Wipe (use with caution on SSDs)")
    elif disk_type == "ssd":
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm) [Works on some SSDs]")
        print(f"{NORD10}[2]{NC} Shred Wipe (Not recommended for SSDs)")
    elif disk_type == "hdd":
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        print(f"{NORD10}[2]{NC} Shred Wipe (multiple overwrites)")
    else:
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        print(f"{NORD10}[2]{NC} Shred Wipe")

    print(f"{NORD10}[0]{NC} Return to Main Menu")
    choice = input("Enter your choice: ").strip()

    if choice == "1":
        if disk_type == "nvme":
            nvme_secure_erase(selected_disk)
        else:
            secure_erase_hdparm(selected_disk)
    elif choice == "2":
        shred_wipe(selected_disk)
    elif choice == "0":
        return
    else:
        print(f"{NORD13}Invalid selection. Returning to main menu.{NC}")

    prompt_enter()


# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------


def main_menu():
    """
    Display the main interactive menu.
    """
    while True:
        os.system("clear")
        print(f"{NORD10}============================================{NC}")
        print(f"{NORD10}       Secure HDD/SSD Eraser Tool           {NC}")
        print(f"{NORD10}============================================{NC}")
        print(f"{NORD14}[1]{NC} List Attached Disks")
        print(f"{NORD14}[2]{NC} Erase a Disk")
        print(f"{NORD14}[q]{NC} Quit")
        print(f"{NORD10}--------------------------------------------{NC}")

        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            print(f"{NORD14}Attached Disks:{NC}")
            print(list_disks())
            prompt_enter()
        elif choice == "2":
            disk_eraser_menu()
        elif choice == "q":
            print(f"{NORD14}Goodbye!{NC}")
            sys.exit(0)
        else:
            print(f"{NORD13}Invalid selection. Please try again.{NC}")
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_root()

    if DRY_RUN:
        logging.info(
            "Dry-run mode activated. No destructive actions will be performed."
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"SECURE DISK ERASER STARTED AT {now}")
    logging.info("=" * 80)

    # Check and install dependencies if needed
    if not check_dependencies():
        install_prerequisites()

    # Execute main menu
    main_menu()

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"SECURE DISK ERASER COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
