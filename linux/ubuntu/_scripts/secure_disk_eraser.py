#!/usr/bin/env python3
"""
Secure Disk Eraser Tool
------------------------
An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
This script installs required tools, lists attached disks with details,
detects whether a disk is an HDD, SSD, or NVMe, and lets the user choose
from several secure erasure methods (using hdparm, nvme-cli, or shred). 
It includes robust interactive prompts with double‑check confirmations and
offers a dry-run mode to simulate destructive actions.

Author: Your Name | License: MIT | Version: 1.1 (Enhanced)
Usage:
    sudo ./secure_disk_eraser.py [--dry-run] [--verbose] [--version]
"""

import os
import sys
import subprocess
import argparse
import signal
import atexit
import re
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/secure_disk_eraser.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)
DRY_RUN = False

# Required tools
REQUIRED_TOOLS = ["hdparm", "nvme", "shred", "lsblk", "apt"]

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN/labels)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO/success)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING AND ERROR HANDLING
# ------------------------------------------------------------------------------
def get_log_level_num(level: str) -> int:
    level = level.upper()
    if level in ("VERBOSE", "V"):
        return 0
    elif level in ("DEBUG", "D"):
        return 1
    elif level in ("INFO", "I"):
        return 2
    elif level in ("WARN", "WARNING", "W"):
        return 3
    elif level in ("ERROR", "E"):
        return 4
    elif level in ("CRITICAL", "C"):
        return 5
    else:
        return 2

def log(level: str, message: str):
    upper_level = level.upper()
    if get_log_level_num(upper_level) < get_log_level_num(LOG_LEVEL):
        return

    color = NC
    if not DISABLE_COLORS:
        if upper_level == "DEBUG":
            color = NORD9
        elif upper_level == "INFO":
            color = NORD14
        elif upper_level in ("WARN", "WARNING"):
            color = NORD13
        elif upper_level in ("ERROR", "CRITICAL"):
            color = NORD11

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{upper_level}] {message}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        sys.stderr.write(f"Log file write error: {e}\n")
    sys.stderr.write(f"{color}{log_entry}{NC}\n")

def handle_error(error_message="An error occurred. See log for details.", exit_code=1):
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")
    # (Optional cleanup tasks)

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum in (signal.SIGINT, signal.SIGTERM):
        handle_error("Script interrupted by user.", exit_code=130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def prompt_enter():
    input("Press Enter to continue...")

def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

def run_cmd(cmd, capture_output=False, check=True):
    """Run a shell command with optional dry-run."""
    log("DEBUG", f"Executing command: {' '.join(cmd)}")
    if DRY_RUN:
        log("INFO", f"DRY RUN: Command not executed: {' '.join(cmd)}")
        return None
    try:
        result = subprocess.run(cmd, capture_output=capture_output, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        handle_error(f"Command failed: {' '.join(cmd)}\nError: {e}", exit_code=e.returncode)

def is_mounted(disk: str) -> bool:
    """Check if a disk device is mounted (warn user if so)."""
    mounts = subprocess.run(["mount"], capture_output=True, text=True).stdout
    return disk in mounts

# ------------------------------------------------------------------------------
# INSTALL PREREQUISITES
# ------------------------------------------------------------------------------
def install_prerequisites():
    print_section("Installing Required Tools")
    log("INFO", "Updating package repositories...")
    run_cmd(["apt", "update"])
    log("INFO", "Installing required tools (hdparm, nvme-cli, coreutils)...")
    run_cmd(["apt", "install", "-y", "hdparm", "nvme-cli", "coreutils"])
    log("INFO", "Prerequisites installed.")

# ------------------------------------------------------------------------------
# DISK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
def list_disks() -> str:
    result = run_cmd(["lsblk", "-d", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,MOUNTPOINT"], capture_output=True)
    return result.stdout if result else ""

def detect_disk_type(disk: str) -> str:
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
    log("INFO", "Scanning for attached disks...")
    disks_out = list_disks()
    if not disks_out.strip():
        log("ERROR", "No disks found on the system.")
        sys.exit(1)
    print(f"{NORD10}Attached Disks:{NC}")
    print(f"{NORD10}{'-'*50}{NC}")
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
        print(f"{NORD10}[{i}]{NC} /dev/{name} - Size: {size}, Type: {disk_type}, Model: {model}{extra}")
        disk_map[str(i)] = name
    print(f"{NORD10}{'-'*50}{NC}")
    while True:
        choice = input("Enter the number of the disk to erase (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            print(f"{NORD14}Exiting...{NC}")
            sys.exit(0)
        if choice in disk_map:
            selected = f"/dev/{disk_map[choice]}"
            log("INFO", f"Selected disk: {selected}")
            if is_mounted(selected):
                log("WARN", f"Warning: {selected} appears to be mounted!")
                confirm = input("This disk is mounted. Are you sure you want to continue? (yes/no): ")
                if confirm.lower() != "yes":
                    log("INFO", "Operation cancelled by user.")
                    sys.exit(0)
            return selected
        else:
            print(f"{NORD13}Invalid selection. Please try again.{NC}")

# ------------------------------------------------------------------------------
# DISK ERASURE METHODS
# ------------------------------------------------------------------------------
def secure_erase_hdparm(disk: str):
    print(f"{NORD14}Preparing to securely erase {disk} using hdparm...{NC}")
    sec_pass = input("Enter a temporary security password (will be cleared): ").strip()
    print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return
    # Execute hdparm commands
    run_cmd(["hdparm", "--user-master", "u", "--security-set-pass", sec_pass, disk])
    run_cmd(["hdparm", "--user-master", "u", "--security-erase", sec_pass, disk])
    print(f"{NORD14}Secure Erase via hdparm completed successfully on {disk}.{NC}")

def nvme_secure_erase(disk: str):
    print(f"{NORD14}Preparing to format NVMe drive {disk} using nvme-cli...{NC}")
    print(f"{NORD13}WARNING: This operation is irreversible.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return
    run_cmd(["nvme", "format", disk])
    print(f"{NORD14}NVMe format completed successfully on {disk}.{NC}")

def shred_wipe(disk: str):
    try:
        num_overwrites = int(input("Enter number of overwrites (recommended 3): ").strip())
    except ValueError:
        print(f"{NORD13}Invalid input; defaulting to 3 overwrites.{NC}")
        num_overwrites = 3
    print(f"{NORD14}Preparing to wipe {disk} using shred with {num_overwrites} passes...{NC}")
    print(f"{NORD13}WARNING: This operation is irreversible and may take a long time.{NC}")
    confirm = input("Type 'YES ERASE' to confirm and proceed: ")
    if confirm != "YES ERASE":
        print(f"{NORD13}Operation cancelled.{NC}")
        return
    run_cmd(["shred", "-n", str(num_overwrites), "-z", "-v", disk])
    print(f"{NORD14}Disk wipe with shred completed successfully on {disk}.{NC}")

# ------------------------------------------------------------------------------
# DISK ERASER MENU
# ------------------------------------------------------------------------------
def disk_eraser_menu():
    selected_disk = select_disk()
    disk_basename = os.path.basename(selected_disk)
    disk_type = detect_disk_type(disk_basename)
    print(f"{NORD10}Detected disk type: {disk_type}{NC}")
    print(f"{NORD10}Select the erasure method:{NC}")
    # For NVMe drives offer NVMe format; for others offer hdparm and shred.
    if disk_type == "nvme":
        print(f"{NORD10}[1]{NC} NVMe Format (nvme-cli)")
        print(f"{NORD10}[3]{NC} Shred Wipe (use with caution on SSDs)")
    elif disk_type == "ssd":
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm) [Works on some SSDs]")
        print(f"{NORD10}[3]{NC} Shred Wipe (Not recommended for SSDs)")
    elif disk_type == "hdd":
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        print(f"{NORD10}[3]{NC} Shred Wipe (multiple overwrites)")
    else:
        print(f"{NORD10}[1]{NC} Secure Erase (hdparm)")
        print(f"{NORD10}[3]{NC} Shred Wipe")
    print(f"{NORD10}[0]{NC} Return to Main Menu")
    choice = input("Enter your choice: ").strip()
    if choice == "1":
        if disk_type == "nvme":
            nvme_secure_erase(selected_disk)
        else:
            secure_erase_hdparm(selected_disk)
    elif choice == "3":
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
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Secure Disk Eraser Tool (Enhanced)",
        add_help=False
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate erasure commands without executing them.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose (DEBUG) logging.")
    parser.add_argument("--version", action="version", version="Secure Disk Eraser v1.1")
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
    return parser.parse_args()

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    global DRY_RUN, LOG_LEVEL
    args = parse_arguments()
    if args.verbose:
        LOG_LEVEL = "DEBUG"
    if args.dry_run:
        DRY_RUN = True
        log("INFO", "Dry-run mode activated. No destructive actions will be performed.")
    check_root()
    log("INFO", "Starting Secure Disk Eraser Tool...")
    install_prerequisites()
    main_menu()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        handle_error(f"Unhandled exception: {e}", exit_code=1)