#!/usr/bin/env python3
"""
Advanced VM Manager Tool
A production-ready Ubuntu/Linux VM manager that can list, create, start, stop, pause, resume,
delete VMs (along with their disk images), monitor resource usage, connect to the console,
and manage snapshots.
License: MIT
Author: Your Name
Version: 4.3
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

# Ensure required directories exist
os.makedirs(ISO_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"   # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"   # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO/labels)
NC     = "\033[0m"                # Reset / No Color

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
    
    # Secure log file permissions
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
    # Additional cleanup tasks can be added here.

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

def print_header(title="Advanced VM Manager Tool"):
    clear_screen()
    print_section(title)

def run_command(command, capture_output=False, check=True):
    """
    Run a shell command.
    If capture_output is True, return the command's stdout (as a string) on success.
    Otherwise, return True if successful or False on error.
    """
    try:
        result = subprocess.run(command, capture_output=capture_output, text=True, check=check)
        if capture_output:
            return result.stdout
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{' '.join(command)}' failed: {e}")
        return False

def get_vm_list():
    """
    Retrieve a list of VMs by parsing the output of 'virsh list --all'.
    Returns a list of dictionaries with keys: 'id', 'name', 'state'.
    """
    output = run_command(["virsh", "list", "--all"], capture_output=True)
    vms = []
    if output:
        lines = output.strip().splitlines()
        # Find index of separator (dashed line)
        sep_index = None
        for i, line in enumerate(lines):
            if line.lstrip().startswith('---'):
                sep_index = i + 1
                break
        if sep_index is None:
            logging.error("Unexpected output format from 'virsh list'.")
            return vms
        for line in lines[sep_index:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                vm_id = parts[0]
                vm_name = parts[1]
                vm_state = " ".join(parts[2:]) if len(parts) > 2 else ""
                vms.append({"id": vm_id, "name": vm_name, "state": vm_state})
    return vms

def select_vm(prompt="Select a VM by number: "):
    """
    Display a numbered list of VMs and prompt the user to select one.
    Returns the selected VM's name or None if no VMs are available.
    """
    vms = get_vm_list()
    if not vms:
        logging.error("No VMs found.")
        return None
    print_header("Virtual Machines")
    for i, vm in enumerate(vms, start=1):
        print(f"{NORD14}[{i}]{NC} {vm['name']} - {vm['state']}")
    while True:
        choice = input(prompt).strip()
        try:
            index = int(choice) - 1
            if 0 <= index < len(vms):
                return vms[index]["name"]
            else:
                print("Invalid selection. Please enter a number corresponding to a VM.")
        except ValueError:
            print("Please enter a valid number.")

# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_vms():
    print_header("Current Virtual Machines")
    vms = get_vm_list()
    if vms:
        for i, vm in enumerate(vms, start=1):
            print(f"{NORD14}[{i}]{NC} {vm['name']} - {vm['state']}")
    else:
        logging.error("No VMs found.")
    prompt_enter()

def start_vm():
    print_header("Start Virtual Machine")
    vm_name = select_vm("Select a VM to start by number: ")
    if not vm_name:
        prompt_enter()
        return
    if run_command(["virsh", "start", vm_name]):
        logging.info(f"VM '{vm_name}' started successfully.")
    else:
        logging.error(f"Failed to start VM '{vm_name}'.")
    prompt_enter()

def stop_vm():
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop by number: ")
    if not vm_name:
        prompt_enter()
        return
    if run_command(["virsh", "shutdown", vm_name]):
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
    else:
        logging.error(f"Failed to shutdown VM '{vm_name}'.")
    prompt_enter()

def pause_vm():
    print_header("Pause Virtual Machine")
    vm_name = select_vm("Select a VM to pause by number: ")
    if not vm_name:
        prompt_enter()
        return
    if run_command(["virsh", "suspend", vm_name]):
        logging.info(f"VM '{vm_name}' paused successfully.")
    else:
        logging.error(f"Failed to pause VM '{vm_name}'.")
    prompt_enter()

def resume_vm():
    print_header("Resume Virtual Machine")
    vm_name = select_vm("Select a VM to resume by number: ")
    if not vm_name:
        prompt_enter()
        return
    if run_command(["virsh", "resume", vm_name]):
        logging.info(f"VM '{vm_name}' resumed successfully.")
    else:
        logging.error(f"Failed to resume VM '{vm_name}'.")
    prompt_enter()

def delete_vm():
    """
    Delete a virtual machine and its associated disk image.
    The function lets you select a VM, undefines it, and then automatically
    removes the disk image. If the VM XML does not provide a disk image path,
    it also checks for a default disk image named <vm_name>.qcow2.
    """
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete by number: ")
    if not vm_name:
        prompt_enter()
        return
    confirm = input(f"Are you sure you want to delete VM '{vm_name}'? This will undefine the VM and delete its disk image. (y/n): ").strip().lower()
    if confirm != 'y':
        logging.warning("Deletion cancelled.")
        prompt_enter()
        return

    # Retrieve disk image path from VM XML
    xml_output = run_command(["virsh", "dumpxml", vm_name], capture_output=True, check=False)
    disk = None
    if xml_output and isinstance(xml_output, str):
        match = re.search(r'source file="([^"]+)"', xml_output)
        if match:
            disk = match.group(1)

    # If disk image not found via XML, try default naming convention
    if not disk:
        default_disk = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
        if os.path.exists(default_disk):
            disk = default_disk

    # Force shutdown if VM is running
    running_vms = run_command(["virsh", "list", "--state-running"], capture_output=True)
    if running_vms and vm_name in running_vms:
        run_command(["virsh", "destroy", vm_name])
    
    # Undefine the VM
    if run_command(["virsh", "undefine", vm_name]):
        logging.info(f"VM '{vm_name}' undefined successfully.")
        if disk:
            try:
                os.remove(disk)
                logging.info(f"Disk image '{disk}' removed successfully.")
            except Exception as e:
                logging.warning(f"Failed to remove disk image '{disk}': {e}")
        else:
            logging.warning("No associated disk image found to remove.")
    else:
        logging.error(f"Failed to delete VM '{vm_name}'.")
    prompt_enter()

def monitor_vm():
    print_header("Monitor Virtual Machine Resources")
    vm_name = select_vm("Select a VM to monitor by number: ")
    if not vm_name:
        prompt_enter()
        return
    logging.info(f"Monitoring VM '{vm_name}'. Press Ctrl+C to exit.")
    try:
        while True:
            clear_screen()
            print(f"{NORD10}Monitoring VM: {NORD14}{vm_name}{NC}")
            print(f"{NORD10}{'-'*60}{NC}")
            output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
            if output:
                print(output)
            else:
                logging.error("Failed to retrieve VM info.")
            print(f"{NORD10}{'-'*60}{NC}")
            time.sleep(5)
    except KeyboardInterrupt:
        logging.info("Exiting monitor mode.")
        prompt_enter()

def remote_console():
    print_header("Remote Console Access")
    vm_name = select_vm("Select a VM for console access by number: ")
    if not vm_name:
        prompt_enter()
        return
    logging.info(f"Connecting to console of VM '{vm_name}'. Press Ctrl+] to exit.")
    try:
        subprocess.run(["virsh", "console", vm_name])
    except Exception as e:
        logging.error(f"Failed to connect to console: {e}")
    prompt_enter()

def list_isos():
    print_header("Available ISO Files")
    try:
        isos = os.listdir(ISO_DIR)
        if not isos:
            print("No ISO files found in the ISO directory.")
        else:
            for iso in sorted(isos):
                print(f"- {iso}")
    except Exception as e:
        logging.error(f"Failed to list ISOs: {e}")
    prompt_enter()

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
    print_header("Create a New Virtual Machine")
    vm_name = input("Enter VM name: ").strip()
    if not vm_name:
        logging.error("VM name cannot be empty.")
        prompt_enter()
        return

    try:
        vcpus = int(input("Enter number of vCPUs: ").strip())
        ram = int(input("Enter RAM in MB: ").strip())
        disk_size = int(input("Enter disk size in GB: ").strip())
    except ValueError:
        logging.error("Invalid input. vCPUs, RAM and disk size must be numeric values.")
        prompt_enter()
        return

    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        logging.error(f"Disk image {disk_image} already exists. Choose a different VM name or remove the existing image.")
        prompt_enter()
        return

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

    logging.info(f"Creating disk image at {disk_image}...")
    if not run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]):
        logging.error("Failed to create disk image. Cleaning up if necessary.")
        if os.path.exists(disk_image):
            try:
                os.remove(disk_image)
            except Exception as e:
                logging.warning(f"Could not remove partial disk image: {e}")
        prompt_enter()
        return

    logging.info("Starting VM installation using virt-install...")
    virt_install_cmd = [
        "virt-install",
        "--name", vm_name,
        "--ram", str(ram),
        "--vcpus", str(vcpus),
        "--disk", f"path={disk_image},size={disk_size},format=qcow2",
        "--cdrom", iso_path,
        "--os-variant", "ubuntu20.04",
        "--graphics", "none",
        "--console", "pty,target_type=serial",
        "--noautoconsole"
    ]
    if run_command(virt_install_cmd):
        logging.info(f"VM '{vm_name}' created successfully.")
    else:
        logging.error(f"Failed to create VM '{vm_name}'.")
    prompt_enter()

# ------------------------------------------------------------------------------
# SNAPSHOT MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_snapshots():
    print_header("List Snapshots")
    vm_name = select_vm("Select a VM to list snapshots by number: ")
    if not vm_name:
        prompt_enter()
        return
    output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
    if output:
        print(output)
    else:
        logging.error("Failed to list snapshots.")
    prompt_enter()

def create_snapshot():
    print_header("Create Snapshot")
    vm_name = select_vm("Select a VM to snapshot by number: ")
    if not vm_name:
        prompt_enter()
        return
    snapshot_name = input("Enter snapshot name: ").strip()
    description = input("Enter snapshot description (optional): ").strip()
    cmd = ["virsh", "snapshot-create-as", vm_name, snapshot_name]
    if description:
        cmd += ["--description", description]
    if run_command(cmd):
        logging.info(f"Snapshot '{snapshot_name}' created for VM '{vm_name}'.")
    else:
        logging.error("Failed to create snapshot.")
    prompt_enter()

def revert_snapshot():
    print_header("Revert Snapshot")
    vm_name = select_vm("Select a VM to revert snapshot by number: ")
    if not vm_name:
        prompt_enter()
        return
    snapshot_name = input("Enter snapshot name to revert to: ").strip()
    if run_command(["virsh", "snapshot-revert", vm_name, snapshot_name]):
        logging.info(f"VM '{vm_name}' reverted to snapshot '{snapshot_name}'.")
    else:
        logging.error("Failed to revert snapshot.")
    prompt_enter()

def delete_snapshot():
    print_header("Delete Snapshot")
    vm_name = select_vm("Select a VM to delete a snapshot by number: ")
    if not vm_name:
        prompt_enter()
        return
    snapshot_name = input("Enter snapshot name to delete: ").strip()
    if run_command(["virsh", "snapshot-delete", vm_name, snapshot_name]):
        logging.info(f"Snapshot '{snapshot_name}' deleted from VM '{vm_name}'.")
    else:
        logging.error("Failed to delete snapshot.")
    prompt_enter()

def snapshot_menu():
    while True:
        print_header("Snapshot Management")
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
# DISK IMAGE MANAGEMENT FUNCTION
# ------------------------------------------------------------------------------
def delete_disk_image():
    """
    Manually delete a VM disk image.
    Lists all .qcow2 files in VM_IMAGE_DIR and lets you select one to delete.
    """
    print_header("Delete Disk Image")
    try:
        disks = [d for d in os.listdir(VM_IMAGE_DIR) if d.endswith('.qcow2')]
    except Exception as e:
        logging.error(f"Failed to list disk images: {e}")
        prompt_enter()
        return
    if not disks:
        logging.info("No disk images found in the directory.")
        prompt_enter()
        return

    print("Available Disk Images:")
    for idx, disk in enumerate(sorted(disks), start=1):
        print(f"{NORD14}[{idx}]{NC} {disk}")

    while True:
        choice = input("Select a disk image to delete by number: ").strip()
        try:
            index = int(choice) - 1
            if 0 <= index < len(disks):
                selected_disk = disks[index]
                break
            else:
                print("Invalid selection. Please enter a valid number.")
        except ValueError:
            print("Please enter a valid number.")

    full_disk_path = os.path.join(VM_IMAGE_DIR, selected_disk)
    confirm = input(f"Are you sure you want to delete disk image '{selected_disk}'? (y/n): ").strip().lower()
    if confirm != 'y':
        logging.info("Disk image deletion cancelled.")
        prompt_enter()
        return
    try:
        os.remove(full_disk_path)
        logging.info(f"Disk image '{selected_disk}' deleted successfully.")
    except Exception as e:
        logging.error(f"Failed to delete disk image '{selected_disk}': {e}")
    prompt_enter()

# ------------------------------------------------------------------------------
# INTERACTIVE MAIN MENU
# ------------------------------------------------------------------------------
def interactive_menu():
    while True:
        print_header("Advanced VM Manager Tool")
        print(f"{NORD14}[1]{NC} List Virtual Machines")
        print(f"{NORD14}[2]{NC} Create Virtual Machine")
        print(f"{NORD14}[3]{NC} Start Virtual Machine")
        print(f"{NORD14}[4]{NC} Stop Virtual Machine")
        print(f"{NORD14}[5]{NC} Delete Virtual Machine")
        print(f"{NORD14}[6]{NC} Monitor Virtual Machine Resources")
        print(f"{NORD14}[7]{NC} Remote Console Access")
        print(f"{NORD14}[8]{NC} Pause Virtual Machine")
        print(f"{NORD14}[9]{NC} Resume Virtual Machine")
        print(f"{NORD14}[a]{NC} List Available ISOs")
        print(f"{NORD14}[s]{NC} Snapshot Management")
        print(f"{NORD14}[x]{NC} Delete Disk Image")
        print(f"{NORD14}[q]{NC} Quit")
        print("-" * 60)
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
            pause_vm()
        elif choice == "9":
            resume_vm()
        elif choice == "a":
            list_isos()
        elif choice == "s":
            snapshot_menu()
        elif choice == "x":
            delete_disk_image()
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
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    # Touch log file if missing
    with open(LOG_FILE, "a"):
        pass
    setup_logging()
    logging.info("Script execution started.")
    interactive_menu()

if __name__ == "__main__":
    main()