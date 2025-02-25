#!/usr/bin/env python3
"""
Advanced VM Manager Tool
A production-ready Ubuntu/Linux VM manager that can list, create, start, stop, pause, resume, delete VMs,
monitor resource usage, connect to the console, and manage snapshots.
Also supports both interactive and CLI modes.
License: MIT
Author: Your Name
Version: 4.0
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
import argparse

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
NORD9  = "\033[38;2;129;161;193m"   # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"    # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"    # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"   # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"   # Greenish (INFO/labels)
NC     = "\033[0m"                 # Reset / No Color

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
    print_header("Current Virtual Machines")
    logging.info("Listing virtual machines...")
    output = run_command(["virsh", "list", "--all"], capture_output=True)
    if output:
        print(output)
    else:
        logging.error("Failed to list VMs.")
    prompt_enter()

def start_vm(vm_name):
    logging.info(f"Starting VM '{vm_name}'...")
    if run_command(["virsh", "start", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' started successfully.")
    else:
        logging.error(f"Failed to start VM '{vm_name}'.")

def stop_vm(vm_name):
    logging.info(f"Stopping VM '{vm_name}' (graceful shutdown)...")
    if run_command(["virsh", "shutdown", vm_name]) is not None:
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
    else:
        logging.error(f"Failed to shutdown VM '{vm_name}'.")

def pause_vm(vm_name):
    logging.info(f"Pausing VM '{vm_name}'...")
    if run_command(["virsh", "suspend", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' paused successfully.")
    else:
        logging.error(f"Failed to pause VM '{vm_name}'.")

def resume_vm(vm_name):
    logging.info(f"Resuming VM '{vm_name}'...")
    if run_command(["virsh", "resume", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' resumed successfully.")
    else:
        logging.error(f"Failed to resume VM '{vm_name}'.")

def delete_vm(vm_name, remove_disk=False):
    print_header("Delete Virtual Machine")
    logging.info(f"Deleting VM '{vm_name}'...")
    # Dump XML to locate disk image
    xml_output = run_command(["virsh", "dumpxml", vm_name], capture_output=True, check=False)
    disk = None
    if xml_output:
        match = re.search(r'source file="([^"]+)"', xml_output)
        if match:
            disk = match.group(1)

    # Force shutdown if running
    running_vms = run_command(["virsh", "list", "--state-running"], capture_output=True)
    if running_vms and vm_name in running_vms:
        run_command(["virsh", "destroy", vm_name])
    if run_command(["virsh", "undefine", vm_name]) is not None:
        logging.info(f"VM '{vm_name}' undefined successfully.")
        if disk and remove_disk:
            try:
                os.remove(disk)
                logging.info("Disk image removed.")
            except Exception as e:
                logging.warning(f"Failed to remove disk image: {e}")
    else:
        logging.error(f"Failed to delete VM '{vm_name}'.")

def monitor_vm(vm_name):
    print_header(f"Monitoring VM: {vm_name}")
    logging.info(f"Monitoring resource usage for VM '{vm_name}'. Press Ctrl+C to exit.")
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

def remote_console(vm_name):
    print_header(f"Connecting to Console of VM: {vm_name}")
    logging.info(f"Connecting to console of VM '{vm_name}'. Press Ctrl+] to exit.")
    try:
        subprocess.run(["virsh", "console", vm_name])
    except Exception as e:
        logging.error(f"Failed to connect to console: {e}")

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

def create_vm_interactive():
    print_header("Create a New Virtual Machine")
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

def create_vm_cli(vm_name, vcpus, ram, disk_size, iso, iso_url):
    # Determine ISO source (either provided directly or via download)
    if iso:
        if not os.path.isfile(iso):
            logging.critical(f"ISO file not found at {iso}.")
            sys.exit(1)
        iso_path = iso
    elif iso_url:
        logging.info("Downloading ISO from URL...")
        iso_path = download_iso_via_cli(iso_url)
        if iso_path is None:
            sys.exit(1)
    else:
        logging.critical("No ISO source provided. Exiting.")
        sys.exit(1)
    
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    logging.info(f"Creating disk image at {disk_image}...")
    if run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]) is None:
        logging.error("Failed to create disk image.")
        sys.exit(1)
    
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
        sys.exit(1)

def download_iso_via_cli(iso_url):
    # Use the basename of the URL as filename
    iso_filename = os.path.basename(iso_url)
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

# ------------------------------------------------------------------------------
# SNAPSHOT MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_snapshots(vm_name):
    logging.info(f"Listing snapshots for VM '{vm_name}'...")
    output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
    if output:
        print(output)
    else:
        logging.error("Failed to list snapshots.")
    prompt_enter()

def create_snapshot(vm_name, snapshot_name=None, description=""):
    if not snapshot_name:
        snapshot_name = input("Enter snapshot name: ").strip()
    cmd = ["virsh", "snapshot-create-as", vm_name, snapshot_name]
    if description:
        cmd += ["--description", description]
    if run_command(cmd) is not None:
        logging.info(f"Snapshot '{snapshot_name}' created for VM '{vm_name}'.")
    else:
        logging.error("Failed to create snapshot.")
    prompt_enter()

def revert_snapshot(vm_name, snapshot_name):
    logging.info(f"Reverting VM '{vm_name}' to snapshot '{snapshot_name}'...")
    if run_command(["virsh", "snapshot-revert", vm_name, snapshot_name]) is not None:
        logging.info(f"VM '{vm_name}' reverted to snapshot '{snapshot_name}'.")
    else:
        logging.error("Failed to revert snapshot.")
    prompt_enter()

def delete_snapshot(vm_name, snapshot_name):
    logging.info(f"Deleting snapshot '{snapshot_name}' from VM '{vm_name}'...")
    if run_command(["virsh", "snapshot-delete", vm_name, snapshot_name]) is not None:
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
            vm = input("Enter VM name: ").strip()
            list_snapshots(vm)
        elif choice == "2":
            vm = input("Enter VM name: ").strip()
            snap_name = input("Enter snapshot name: ").strip()
            desc = input("Enter snapshot description (optional): ").strip()
            create_snapshot(vm, snap_name, desc)
        elif choice == "3":
            vm = input("Enter VM name: ").strip()
            snap_name = input("Enter snapshot name to revert to: ").strip()
            revert_snapshot(vm, snap_name)
        elif choice == "4":
            vm = input("Enter VM name: ").strip()
            snap_name = input("Enter snapshot name to delete: ").strip()
            delete_snapshot(vm, snap_name)
        elif choice == "b":
            break
        else:
            logging.warning("Invalid selection. Please try again.")
            time.sleep(1)

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
        print(f"{NORD14}[q]{NC} Quit")
        print("-" * 60)
        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            list_vms()
        elif choice == "2":
            create_vm_interactive()
        elif choice == "3":
            vm = input("Enter the VM name to start: ").strip()
            start_vm(vm)
            prompt_enter()
        elif choice == "4":
            vm = input("Enter the VM name to stop: ").strip()
            stop_vm(vm)
            prompt_enter()
        elif choice == "5":
            vm = input("Enter the VM name to delete: ").strip()
            confirm = input(f"Are you sure you want to delete VM '{vm}'? (y/n): ").strip().lower()
            if confirm == "y":
                remove = input("Remove disk image as well? (y/n): ").strip().lower() == "y"
                delete_vm(vm, remove)
            else:
                logging.warning("Deletion cancelled.")
                prompt_enter()
        elif choice == "6":
            vm = input("Enter the VM name to monitor: ").strip()
            monitor_vm(vm)
        elif choice == "7":
            vm = input("Enter the VM name for console access: ").strip()
            remote_console(vm)
        elif choice == "8":
            vm = input("Enter the VM name to pause: ").strip()
            pause_vm(vm)
            prompt_enter()
        elif choice == "9":
            vm = input("Enter the VM name to resume: ").strip()
            resume_vm(vm)
            prompt_enter()
        elif choice == "a":
            list_isos()
        elif choice == "s":
            snapshot_menu()
        elif choice == "q":
            logging.info("Goodbye!")
            sys.exit(0)
        else:
            logging.warning("Invalid selection. Please try again.")
            time.sleep(1)

# ------------------------------------------------------------------------------
# COMMAND-LINE ARGUMENT PARSING & DISPATCH
# ------------------------------------------------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description="Advanced VM Manager Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List VMs
    subparsers.add_parser("list", help="List virtual machines")

    # Create VM
    create_parser = subparsers.add_parser("create", help="Create a virtual machine")
    create_parser.add_argument("--name", required=True, help="Name of the virtual machine")
    create_parser.add_argument("--vcpus", required=True, help="Number of vCPUs")
    create_parser.add_argument("--ram", required=True, help="RAM in MB")
    create_parser.add_argument("--disk", required=True, help="Disk size in GB")
    group = create_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--iso", help="Path to an existing ISO file")
    group.add_argument("--iso-url", help="URL to download an ISO file")

    # Start VM
    start_parser = subparsers.add_parser("start", help="Start a virtual machine")
    start_parser.add_argument("vm_name", help="Name of the virtual machine")

    # Stop VM
    stop_parser = subparsers.add_parser("stop", help="Stop a virtual machine")
    stop_parser.add_argument("vm_name", help="Name of the virtual machine")

    # Delete VM
    delete_parser = subparsers.add_parser("delete", help="Delete a virtual machine")
    delete_parser.add_argument("vm_name", help="Name of the virtual machine")
    delete_parser.add_argument("--remove-disk", action="store_true", help="Remove disk image")

    # Monitor VM
    monitor_parser = subparsers.add_parser("monitor", help="Monitor a virtual machine")
    monitor_parser.add_argument("vm_name", help="Name of the virtual machine")

    # Remote Console
    console_parser = subparsers.add_parser("console", help="Connect to a virtual machine console")
    console_parser.add_argument("vm_name", help="Name of the virtual machine")

    # Snapshot management
    snapshot_parser = subparsers.add_parser("snapshot", help="Manage snapshots")
    snapshot_subparsers = snapshot_parser.add_subparsers(dest="action", help="Snapshot actions")
    # List snapshots
    snap_list = snapshot_subparsers.add_parser("list", help="List snapshots")
    snap_list.add_argument("vm_name", help="Name of the virtual machine")
    # Create snapshot
    snap_create = snapshot_subparsers.add_parser("create", help="Create a snapshot")
    snap_create.add_argument("vm_name", help="Name of the virtual machine")
    snap_create.add_argument("--name", required=True, help="Snapshot name")
    snap_create.add_argument("--description", help="Snapshot description", default="")
    # Revert snapshot
    snap_revert = snapshot_subparsers.add_parser("revert", help="Revert to a snapshot")
    snap_revert.add_argument("vm_name", help="Name of the virtual machine")
    snap_revert.add_argument("--name", required=True, help="Snapshot name")
    # Delete snapshot
    snap_delete = snapshot_subparsers.add_parser("delete", help="Delete a snapshot")
    snap_delete.add_argument("vm_name", help="Name of the virtual machine")
    snap_delete.add_argument("--name", required=True, help="Snapshot name")

    # Pause VM
    pause_parser = subparsers.add_parser("pause", help="Pause a virtual machine")
    pause_parser.add_argument("vm_name", help="Name of the virtual machine")

    # Resume VM
    resume_parser = subparsers.add_parser("resume", help="Resume a paused virtual machine")
    resume_parser.add_argument("vm_name", help="Name of the virtual machine")

    # List ISOs
    subparsers.add_parser("listisos", help="List available ISO files")

    # Version
    subparsers.add_parser("version", help="Show version information")

    return parser.parse_args()

def dispatch_command(args):
    if args.command == "list":
        list_vms()
    elif args.command == "create":
        create_vm_cli(args.name, args.vcpus, args.ram, args.disk, args.iso, args.iso_url)
    elif args.command == "start":
        start_vm(args.vm_name)
    elif args.command == "stop":
        stop_vm(args.vm_name)
    elif args.command == "delete":
        delete_vm(args.vm_name, remove_disk=args.remove_disk)
    elif args.command == "monitor":
        monitor_vm(args.vm_name)
    elif args.command == "console":
        remote_console(args.vm_name)
    elif args.command == "snapshot":
        if args.action == "list":
            list_snapshots(args.vm_name)
        elif args.action == "create":
            create_snapshot(args.vm_name, snapshot_name=args.name, description=args.description)
        elif args.action == "revert":
            revert_snapshot(args.vm_name, args.name)
        elif args.action == "delete":
            delete_snapshot(args.vm_name, args.name)
        else:
            logging.error("Unknown snapshot action.")
    elif args.command == "pause":
        pause_vm(args.vm_name)
    elif args.command == "resume":
        resume_vm(args.vm_name)
    elif args.command == "listisos":
        list_isos()
    elif args.command == "version":
        print("Advanced VM Manager Tool Version 4.0")
    else:
        logging.error("Unknown command.")

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
    with open(LOG_FILE, "a"):
        pass
    setup_logging()
    logging.info("Script execution started.")

    # If command-line arguments are provided, run in CLI mode; otherwise, use interactive menu.
    if len(sys.argv) > 1:
        args = parse_arguments()
        dispatch_command(args)
    else:
        interactive_menu()

if __name__ == "__main__":
    main()