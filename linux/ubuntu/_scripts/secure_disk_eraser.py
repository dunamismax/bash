#!/usr/bin/env python3
"""
Secure Disk Eraser Tool
--------------------------------------------------------
Description:
  An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
  This script installs required tools, lists attached disks with details,
  detects whether a disk is an HDD, SSD, or NVMe, and lets the user choose
  from several secure erasure methods (using hdparm, nvme-cli, or shred).
  It features robust interactive prompts with double‑check confirmations,
  detailed logging with the Nord color palette, progress spinners using rich,
  and graceful signal and cleanup handling.

Usage:
  sudo ./secure_disk_eraser.py

Author: YourName | License: MIT | Version: 2.1.0
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
from rich.console import Console

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/secure_disk_eraser.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
REQUIRED_TOOLS = ["hdparm", "nvme", "shred", "lsblk", "apt"]

console = Console()

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
NC = "\033[0m"  # No Color / Reset


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom logging formatter applying Nord color theme.
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
    Configure logging with console and file handlers.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove any existing handlers
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
        logger.warning(f"Failed to set file permissions on {LOG_FILE}: {e}")
    return logger


def print_section(title: str):
    """
    Print a section header with Nord styling.
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
# RICH PROGRESS HELPER
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


def run_cmd(cmd, capture_output=False, check=True):
    """
    Execute a shell command with optional dry-run mode.
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


def run_cmd_with_progress(cmd, description, capture_output=False, check=True):
    """
    Execute a shell command wrapped with a rich progress spinner.
    """
    return run_with_progress(
        description, run_cmd, cmd, capture_output=capture_output, check=check
    )


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Gracefully handle termination signals.
    """
    sig_name = f"signal {signum}"
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by {sig_name}.")
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING & INSTALLATION
# ------------------------------------------------------------------------------
def check_dependencies() -> bool:
    """
    Check for required dependencies.
    """
    missing = [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]
    if missing:
        logging.warning(f"Missing required tools: {', '.join(missing)}")
        return False
    return True


def install_prerequisites():
    """
    Install missing required tools.
    """
    print_section("Installing Required Tools")
    logging.info("Updating package repositories...")
    run_cmd_with_progress(["apt", "update"], "Updating package repos...")
    logging.info("Installing required tools (hdparm, nvme-cli, coreutils)...")
    run_cmd_with_progress(
        ["apt", "install", "-y", "hdparm", "nvme-cli", "coreutils"],
        "Installing tools...",
    )
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


def is_mounted(disk: str) -> bool:
    """
    Check if a disk is mounted.
    """
    mounts = run_cmd(["mount"], capture_output=True)
    return disk in (mounts.stdout if mounts and mounts.stdout else "")


# ------------------------------------------------------------------------------
# DISK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
def list_disks() -> str:
    """
    List all available disks with details.
    """
    result = run_cmd(
        ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,MOUNTPOINT"],
        capture_output=True,
    )
    return result.stdout if result and result.stdout else ""


def detect_disk_type(disk: str) -> str:
    """
    Detect whether a disk is HDD, SSD, or NVMe.
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
    Display available disks and let the user select one.
    """
    logging.info("Scanning for attached disks...")
    disks_output = list_disks()
    if not disks_output.strip():
        logging.error("No disks found on the system.")
        sys.exit(1)

    console.print(f"[{NORD10}bold]Attached Disks:[/]")
    console.print(f"{NORD10}{'-' * 50}{NC}")

    disk_map = {}
    lines = disks_output.strip().splitlines()[1:]  # Skip header
    for i, line in enumerate(lines, start=1):
        parts = line.split()
        if len(parts) < 5:
            continue
        name, size, _, _, model = parts[:5]
        mountpoint = parts[5] if len(parts) >= 6 else ""
        disk_type = detect_disk_type(name)
        extra = f", Mounted: {mountpoint}" if mountpoint and mountpoint != "-" else ""
        console.print(
            f"{NORD10}[{i}]{NC} /dev/{name} - Size: {size}, Type: {disk_type}, Model: {model}{extra}"
        )
        disk_map[str(i)] = name

    console.print(f"{NORD10}{'-' * 50}{NC}")
    while True:
        choice = input(
            "Enter the number of the disk to erase (or 'q' to quit): "
        ).strip()
        if choice.lower() == "q":
            console.print(f"{NORD14}Exiting...{NC}")
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
            console.print(f"{NORD13}Invalid selection. Please try again.{NC}")


# ------------------------------------------------------------------------------
# DISK ERASURE METHODS
# ------------------------------------------------------------------------------
def secure_erase_hdparm(disk: str):
    """
    Securely erase a disk using hdparm.
    """
    console.print(f"{NORD14}Preparing to securely erase {disk} using hdparm...{NC}")
    sec_pass = input("Enter a temporary security password (will be cleared): ").strip()
    console.print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        console.print(f"{NORD13}Operation cancelled.{NC}")
        return

    logging.info(f"Setting security password for {disk}")
    run_cmd_with_progress(
        ["hdparm", "--user-master", "u", "--security-set-pass", sec_pass, disk],
        "Setting security password...",
    )
    logging.info(f"Executing secure erase on {disk}")
    run_cmd_with_progress(
        ["hdparm", "--user-master", "u", "--security-erase", sec_pass, disk],
        "Executing secure erase...",
    )
    logging.info(f"Secure erase via hdparm completed on {disk}.")
    console.print(f"{NORD14}Secure erase via hdparm completed on {disk}.{NC}")


def nvme_secure_erase(disk: str):
    """
    Securely format an NVMe drive using nvme-cli.
    """
    console.print(
        f"{NORD14}Preparing to format NVMe drive {disk} using nvme-cli...{NC}"
    )
    console.print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        console.print(f"{NORD13}Operation cancelled.{NC}")
        return

    logging.info(f"Executing NVMe format on {disk}")
    run_cmd_with_progress(["nvme", "format", disk], "Formatting NVMe drive...")
    logging.info(f"NVMe format completed on {disk}.")
    console.print(f"{NORD14}NVMe format completed on {disk}.{NC}")


def shred_wipe(disk: str):
    """
    Wipe a disk using shred with multiple overwrites.
    """
    try:
        num_overwrites = int(
            input("Enter number of overwrites (recommended 3): ").strip()
        )
    except ValueError:
        console.print(f"{NORD13}Invalid input; defaulting to 3 overwrites.{NC}")
        num_overwrites = 3

    console.print(
        f"{NORD14}Preparing to wipe {disk} using shred with {num_overwrites} passes...{NC}"
    )
    console.print(
        f"{NORD13}WARNING: This operation is irreversible and may take a long time.{NC}"
    )
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        console.print(f"{NORD13}Operation cancelled.{NC}")
        return

    logging.info(f"Executing shred with {num_overwrites} passes on {disk}")
    run_cmd_with_progress(
        ["shred", "-n", str(num_overwrites), "-z", "-v", disk],
        "Wiping disk with shred...",
    )
    logging.info(f"Disk wipe with shred completed on {disk}.")
    console.print(f"{NORD14}Disk wipe with shred completed on {disk}.{NC}")


# ------------------------------------------------------------------------------
# DISK ERASER MENU
# ------------------------------------------------------------------------------
def disk_eraser_menu():
    """
    Display the disk erasure menu.
    """
    selected_disk = select_disk()
    disk_basename = os.path.basename(selected_disk)
    disk_type = detect_disk_type(disk_basename)

    console.print(f"{NORD10}Detected disk type: {disk_type}{NC}")
    console.print(f"{NORD10}Select the erasure method:{NC}")

    if disk_type == "nvme":
        console.print(f"{NORD10}[1]{NC} NVMe Format (nvme-cli)")
        console.print(f"{NORD10}[2]{NC} Shred Wipe (use with caution on SSDs)")
    elif disk_type == "ssd":
        console.print(f"{NORD10}[1]{NC} Secure Erase (hdparm) [Works on some SSDs]")
        console.print(f"{NORD10}[2]{NC} Shred Wipe (Not recommended for SSDs)")
    elif disk_type == "hdd":
        console.print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        console.print(f"{NORD10}[2]{NC} Shred Wipe (multiple overwrites)")
    else:
        console.print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        console.print(f"{NORD10}[2]{NC} Shred Wipe")

    console.print(f"{NORD10}[0]{NC} Return to Main Menu")
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
        console.print(f"{NORD13}Invalid selection. Returning to main menu.{NC}")
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
        console.print(f"{NORD10}============================================{NC}")
        console.print(f"{NORD10}       Secure HDD/SSD Eraser Tool           {NC}")
        console.print(f"{NORD10}============================================{NC}")
        console.print(f"{NORD14}[1]{NC} List Attached Disks")
        console.print(f"{NORD14}[2]{NC} Erase a Disk")
        console.print(f"{NORD14}[q]{NC} Quit")
        console.print(f"{NORD10}--------------------------------------------{NC}")

        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            console.print(f"{NORD14}Attached Disks:{NC}")
            console.print(list_disks())
            prompt_enter()
        elif choice == "2":
            disk_eraser_menu()
        elif choice == "q":
            console.print(f"{NORD14}Goodbye!{NC}")
            sys.exit(0)
        else:
            console.print(f"{NORD13}Invalid selection. Please try again.{NC}")
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the Secure Disk Eraser.
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

    if not check_dependencies():
        install_prerequisites()

    main_menu()

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
