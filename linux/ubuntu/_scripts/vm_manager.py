#!/usr/bin/env python3
"""
Advanced VM Manager Tool
A production-ready Ubuntu/Linux VM manager that can list, create, start, stop, delete VMs,
monitor resource usage, connect to the console, and manage snapshots.
License: MIT
Author: Your Name
Version: 3.0
"""

import os
import sys
import subprocess
import logging
import signal
import time
import shutil
import atexit
import urllib.request
import re

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ultimate_script.log"  # Log file path
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Default directories for VM images and ISOs
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"
TMP_ISO = "/tmp/vm_install.iso"

# Ensure required directories exist
os.makedirs(ISO_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9 = "\033[38;2;129;161;193m"   # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"    # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"    # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"   # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"   # Greenish (INFO/labels)
NC = "\033[0m"                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": NORD9,
        "INFO": NORD14,
        "WARNING": NORD13,
        "ERROR": NORD11,
        "CRITICAL": NORD11,
    }
    def format(self, record):
        message = super().format(record)
        if not DISABLE_COLORS:
            color = self.LEVEL_COLORS.get(record.levelname, NC)
            message = f"{color}{message}{NC}"
        return message

def setup_logging():
    logger = logging.getLogger()
    # Set logging level from environment variable or default
    level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    
    # Console handler with color formatter
    console_handler = logging.StreamHandler(sys.stderr)
    console_formatter = ColorFormatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler without color formatting
    file_handler = logging.FileHandler(LOG_FILE)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Set secure permissions on log file
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Could not set permissions on {LOG_FILE}: {e}")

# ------------------------------------------------------------------------------
# ROOT & DEPENDENCY CHECKS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        logging.critical("This script must be run as root.")
        sys.exit(1)

def check_required_commands():
    required_cmds = ["virsh", "virt-install", "qemu-img", "wget"]
    for cmd in required_cmds:
        if shutil.which(cmd) is None:
            logging.critical(f"Required command '{cmd}' is not installed. Exiting.")
            sys.exit(1)

# ------------------------------------------------------------------------------
# CLEANUP & SIGNAL HANDLING
# ------------------------------------------------------------------------------
def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Add any additional cleanup tasks here if needed

atexit.register(cleanup)

def handle_sigint(signum, frame):
    logging.error("Script interrupted by user (SIGINT).")
    sys.exit(130)

def handle_sigterm(signum, frame):
    logging.error("Script terminated (SIGTERM).")
    sys.exit(143)

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigterm)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def clear_screen():
    os.system("clear")

def print_section(title):
    border = "─" * 60
    logging.info(f"{NORD10}{border}{NC}")
    logging.info(f"{NORD10}  {title}{NC}")
    logging.info(f"{NORD10}{border}{NC}")

def prompt_enter():
    input("Press Enter to continue...")

def print_header():
    clear_screen()
    print_section("Advanced VM Manager Tool")

def run_command(command, capture_output=False, check=True):
    """Run a shell command and optionally capture its output."""
    try:
        result = subprocess.run(command, capture_output=capture_output, text=True, check=check)
        return result.stdout if capture_output else None
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{' '.join(command)}' failed: {e}")
        return None

# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_vms():
    print_header()
    logging.info("Current Virtual Machines:")
    print("--------------------------------------------")
    output = run_command(["virsh", "list", "--all"], capture_output=True)
    if output:
        print(output)
    else:
        logging.error("Failed to list VMs.")
    print("--------------------------------------------")
    prompt_enter()

def start_vm():
    print_header()
    logging.info("Start a Virtual Machine:")
    list_vms()
    vm_name = input("Enter the VM name to start: ").strip()
    if run_command(["virsh", "start", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' started successfully.")
    else:
        logging.error(f"Failed to start VM '{vm_name}'.")
    prompt_enter()

def stop_vm():
    print_header()
    logging.info("Stop a Virtual Machine:")
    list_vms()
    vm_name = input("Enter the VM name to stop (graceful shutdown): ").strip()
    if run_command(["virsh", "shutdown", vm_name]) is not None:
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
    else:
        logging.error(f"Failed to shutdown VM '{vm_name}'.")
    prompt_enter()

def delete_vm():
    print_header()
    logging.info("Delete a Virtual Machine:")
    list_vms()
    vm_name = input("Enter the VM name to delete: ").strip()
    confirm = input(f"Are you sure you want to delete VM '{vm_name}'? This will undefine the VM. (y/n): ").strip().lower()
    if confirm != 'y':
        logging.warning("Deletion cancelled.")
        prompt_enter()
        return

    # Retrieve disk image path from VM XML
    xml_output = run_command(["virsh", "dumpxml", vm_name], capture_output=True, check=False)
    disk = None
    if xml_output:
        match = re.search(r'source file="([^"]+)"', xml_output)
        if match:
            disk = match.group(1)

    # Force shutdown if VM is running
    running_vms = run_command(["virsh", "list", "--state-running"], capture_output=True)
    if running_vms and vm_name in running_vms:
        run_command(["virsh", "destroy", vm_name])
    if run_command(["virsh", "undefine", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' undefined successfully.")
        if disk:
            remove_disk = input(f"Do you want to remove its disk image at {disk}? (y/n): ").strip().lower()
            if remove_disk == 'y':
                try:
                    os.remove(disk)
                    logging.info("Disk image removed.")
                except Exception as e:
                    logging.warning(f"Failed to remove disk image: {e}")
    else:
        logging.error(f"Failed to delete VM '{vm_name}'.")
    prompt_enter()

def monitor_vm():
    print_header()
    logging.info("Monitor Virtual Machine Resource Usage:")
    list_vms()
    vm_name = input("Enter the VM name to monitor: ").strip()
    logging.info("Press Ctrl+C to exit monitoring and return to the menu.")
    try:
        while True:
            clear_screen()
            print(f"{NORD10}Monitoring VM: {NORD14}{vm_name}{NC}")
            print(f"{NORD10}--------------------------------------------{NC}")
            output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
            if output:
                print(output)
            else:
                logging.error("Failed to retrieve VM info.")
            print(f"{NORD10}--------------------------------------------{NC}")
            time.sleep(5)
    except KeyboardInterrupt:
        pass

def download_iso():
    iso_url = input("Enter the URL for the installation ISO: ").strip()
    iso_filename = input("Enter the desired filename (e.g., ubuntu.iso): ").strip()
    iso_path = os.path.join(ISO_DIR, iso_filename)
    logging.info(f"Downloading ISO to {iso_path}...")
    try:
        with urllib.request.urlopen(iso_url) as response, open(iso_path, 'wb') as out_file:
            out_file.write(response.read())
        logging.info("ISO downloaded successfully.")
        return iso_path
    except Exception as e:
        logging.error(f"Failed to download ISO: {e}")
        return None

def create_vm():
    print_header()
    logging.info("Create a New Virtual Machine:")
    vm_name = input("Enter VM name: ").strip()
    vcpus = input("Enter number of vCPUs: ").strip()
    ram = input("Enter RAM in MB: ").strip()
    disk_size = input("Enter disk size in GB: ").strip()
    
    print(f"{NORD14}Provide installation ISO:{NC}")
    print(f"{NORD10}[1]{NC} Use existing ISO file")
    print(f"{NORD10}[2]{NC} Download ISO via URL")
    iso_choice = input("Enter your choice (1 or 2): ").strip()
    iso_path = ""
    if iso_choice == "1":
        iso_path = input("Enter full path to ISO file: ").strip()
        if not os.path.isfile(iso_path):
            logging.error(f"ISO file not found at {iso_path}.")
            prompt_enter()
            return
    elif iso_choice == "2":
        iso_path = download_iso()
        if iso_path is None:
            prompt_enter()
            return
    else:
        logging.warning("Invalid selection. Cancelling VM creation.")
        prompt_enter()
        return

    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    logging.info(f"Creating disk image at {disk_image}...")
    if run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]) is None:
        logging.error("Failed to create disk image.")
        prompt_enter()
        return

    logging.info("Starting VM installation using virt-install...")
    virt_install_cmd = [
        "virt-install",
        "--name", vm_name,
        "--ram", ram,
        "--vcpus", vcpus,
        "--disk", f"path={disk_image},size={disk_size},format=qcow2",
        "--cdrom", iso_path,
        "--os-type", "linux",
        "--os-variant", "ubuntu20.04",
        "--graphics", "none",
        "--console", "pty,target_type=serial",
        "--noautoconsole"
    ]
    if run_command(virt_install_cmd) is not None:
        logging.info(f"VM '{vm_name}' created successfully.")
    else:
        logging.error(f"Failed to create VM '{vm_name}'.")
    prompt_enter()

def remote_console():
    print_header()
    logging.info("Remote Console Access:")
    list_vms()
    vm_name = input("Enter the VM name to connect to its console: ").strip()
    logging.info(f"Connecting to console of VM '{vm_name}'. Press Ctrl+] to exit.")
    try:
        subprocess.run(["virsh", "console", vm_name])
    except Exception as e:
        logging.error(f"Failed to connect to console: {e}")
    prompt_enter()

# ------------------------------------------------------------------------------
# ADDITIONAL FEATURE: SNAPSHOT MANAGEMENT
# ------------------------------------------------------------------------------
def list_snapshots():
    vm_name = input("Enter the VM name to list snapshots: ").strip()
    output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
    if output:
        print(output)
    else:
        logging.error("Failed to list snapshots.")
    prompt_enter()

def create_snapshot():
    vm_name = input("Enter the VM name to create a snapshot for: ").strip()
    snapshot_name = input("Enter snapshot name: ").strip()
    description = input("Enter snapshot description (optional): ").strip()
    cmd = ["virsh", "snapshot-create-as", vm_name, snapshot_name]
    if description:
        cmd += ["--description", description]
    if run_command(cmd) is not None:
        logging.info(f"Snapshot '{snapshot_name}' created for VM '{vm_name}'.")
    else:
        logging.error("Failed to create snapshot.")
    prompt_enter()

def revert_snapshot():
    vm_name = input("Enter the VM name to revert snapshot for: ").strip()
    snapshot_name = input("Enter snapshot name to revert to: ").strip()
    if run_command(["virsh", "snapshot-revert", vm_name, snapshot_name]) is not None:
        logging.info(f"VM '{vm_name}' reverted to snapshot '{snapshot_name}'.")
    else:
        logging.error("Failed to revert snapshot.")
    prompt_enter()

def delete_snapshot():
    vm_name = input("Enter the VM name to delete a snapshot from: ").strip()
    snapshot_name = input("Enter snapshot name to delete: ").strip()
    if run_command(["virsh", "snapshot-delete", vm_name, snapshot_name]) is not None:
        logging.info(f"Snapshot '{snapshot_name}' deleted from VM '{vm_name}'.")
    else:
        logging.error("Failed to delete snapshot.")
    prompt_enter()

def snapshot_menu():
    while True:
        print_header()
        print(f"{NORD14}[1]{NC} List Snapshots")
        print(f"{NORD14}[2]{NC} Create Snapshot")
        print(f"{NORD14}[3]{NC} Revert to Snapshot")
        print(f"{NORD14}[4]{NC} Delete Snapshot")
        print(f"{NORD14}[b]{NC} Back to Main Menu")
        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            list_snapshots()
        elif choice == "2":
            create_snapshot()
        elif choice == "3":
            revert_snapshot()
        elif choice == "4":
            delete_snapshot()
        elif choice == "b":
            break
        else:
            logging.warning("Invalid selection. Please try again.")
            time.sleep(1)

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
def main_menu():
    while True:
        print_header()
        print(f"{NORD14}[1]{NC} List Virtual Machines")
        print(f"{NORD14}[2]{NC} Create Virtual Machine")
        print(f"{NORD14}[3]{NC} Start Virtual Machine")
        print(f"{NORD14}[4]{NC} Stop Virtual Machine")
        print(f"{NORD14}[5]{NC} Delete Virtual Machine")
        print(f"{NORD14}[6]{NC} Monitor Virtual Machine Resources")
        print(f"{NORD14}[7]{NC} Remote Console Access")
        print(f"{NORD14}[8]{NC} Snapshot Management")
        print(f"{NORD14}[q]{NC} Quit")
        print("--------------------------------------------")
        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            list_vms()
        elif choice == "2":
            create_vm()
        elif choice == "3":
            start_vm()
        elif choice == "4":
            stop_vm()
        elif choice == "5":
            delete_vm()
        elif choice == "6":
            monitor_vm()
        elif choice == "7":
            remote_console()
        elif choice == "8":
            snapshot_menu()
        elif choice == "q":
            logging.info("Goodbye!")
            sys.exit(0)
        else:
            logging.warning("Invalid selection. Please try again.")
            time.sleep(1)

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    if sys.version_info < (3, 6):
        print("This script requires Python 3.6 or higher.")
        sys.exit(1)
    check_root()
    check_required_commands()
    # Ensure log directory exists
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    # Touch log file if missing
    with open(LOG_FILE, "a"):
        pass
    setup_logging()
    logging.info("Script execution started.")
    main_menu()

if __name__ == "__main__":
    main()