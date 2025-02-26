#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A production-ready Ubuntu/Linux VM manager that can list, create, start, stop,
  pause, resume, and delete VMs (along with their disk images), monitor resource usage,
  connect to the console, and manage snapshots. Uses the Nord color theme for
  visually engaging output with robust error handling, logging, and progress feedback.

Usage:
  sudo ./vm_manager.py

Author: Your Name | License: MIT | Version: 4.5.0
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
import urllib.request
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

# ------------------------------------------------------------------------------
# ENVIRONMENT CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/vm_manager.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Directories for VM images and ISOs
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

# ------------------------------------------------------------------------------
# SETUP RICH CONSOLE
# ------------------------------------------------------------------------------
console = Console()


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom formatter that applies Nord color theme to log messages.
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
    Set up logging with console and file handlers using the Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Remove existing handlers
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
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
    return logger


def print_section(title: str):
    """
    Print a section header with Nord-themed styling.
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
# PROGRESS HELPER (using rich)
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


def download_file(
    url: str, output_path: str, description: str = "Downloading ISO..."
) -> str:
    """
    Download a file from a URL with a progress bar.

    Returns the output path if successful, otherwise raises an exception.
    """
    try:
        with urllib.request.urlopen(url) as response:
            total = int(response.getheader("Content-Length", 0))
            chunk_size = 8192
            with (
                open(output_path, "wb") as f,
                Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    TimeElapsedColumn(),
                ) as progress,
            ):
                task = progress.add_task(description, total=total)
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
        return output_path
    except Exception as e:
        logging.error(f"Download failed: {e}")
        raise


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    sig_name = f"signal {signum}"
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Check for required commands.
    """
    required_commands = ["virsh", "virt-install", "qemu-img", "wget"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"Dependency '{cmd}' is missing. Please install it and try again."
            )
            sys.exit(1)


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def clear_screen():
    """
    Clear the terminal screen.
    """
    os.system("clear")


def prompt_enter():
    """
    Prompt the user to press Enter to continue.
    """
    input("Press Enter to continue...")


def print_header(title="Advanced VM Manager Tool"):
    """
    Print a header with the given title.
    """
    clear_screen()
    print_section(title)


# ------------------------------------------------------------------------------
# COMMAND EXECUTION HELPER
# ------------------------------------------------------------------------------
def run_command(command: list, capture_output: bool = False, check: bool = True):
    """
    Execute a shell command.

    Returns captured stdout if requested, else True on success or False on error.
    """
    try:
        result = subprocess.run(
            command, capture_output=capture_output, text=True, check=check
        )
        return result.stdout if capture_output else True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{' '.join(command)}' failed: {e}")
        return False


# ------------------------------------------------------------------------------
# VM LISTING & SELECTION
# ------------------------------------------------------------------------------
def get_vm_list() -> list:
    """
    Retrieve a list of VMs by parsing the output of 'virsh list --all'.

    Returns a list of dictionaries with keys: 'id', 'name', and 'state'.
    """
    output = run_command(["virsh", "list", "--all"], capture_output=True)
    vms = []
    if output:
        lines = output.strip().splitlines()
        sep_index = next(
            (i + 1 for i, line in enumerate(lines) if line.lstrip().startswith("---")),
            None,
        )
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


def select_vm(prompt_text="Select a VM by number: ") -> str:
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
        choice = input(prompt_text).strip()
        try:
            index = int(choice) - 1
            if 0 <= index < len(vms):
                return vms[index]["name"]
            else:
                print("Invalid selection. Please enter a valid number.")
        except ValueError:
            print("Please enter a valid number.")


# ------------------------------------------------------------------------------
# ISO SELECTION & DOWNLOAD
# ------------------------------------------------------------------------------
def select_iso() -> str:
    """
    Allow the user to select an ISO file from the ISO directory or enter a custom path.

    Returns the full path to the selected ISO.
    """
    print_header("Select Installation ISO")
    try:
        available_isos = [
            iso
            for iso in os.listdir(ISO_DIR)
            if os.path.isfile(os.path.join(ISO_DIR, iso))
        ]
    except Exception as e:
        logging.error(f"Error listing ISOs: {e}")
        available_isos = []
    if available_isos:
        print("Available ISO files:")
        for i, iso in enumerate(sorted(available_isos), start=1):
            print(f"{NORD14}[{i}]{NC} {iso}")
        print(f"{NORD14}[0]{NC} Enter a custom ISO path")
        while True:
            choice = input("Select an ISO by number or 0 for custom: ").strip()
            try:
                index = int(choice)
                if index == 0:
                    custom_path = input("Enter the full path to the ISO file: ").strip()
                    if os.path.isfile(custom_path):
                        return custom_path
                    else:
                        print("File not found. Please try again.")
                elif 1 <= index <= len(available_isos):
                    return os.path.join(ISO_DIR, sorted(available_isos)[index - 1])
                else:
                    print("Invalid selection, please try again.")
            except ValueError:
                print("Please enter a valid number.")
    else:
        print("No ISO files found in the ISO directory.")
        custom_path = input("Enter the full path to the ISO file: ").strip()
        if os.path.isfile(custom_path):
            return custom_path
        else:
            print("File not found. Operation cancelled.")
            return None


def download_iso() -> str:
    """
    Download an ISO file from a user-provided URL.

    Returns the path to the downloaded ISO file or None if the download fails.
    """
    iso_url = input("Enter the URL for the installation ISO: ").strip()
    iso_filename = input("Enter the desired filename (e.g., ubuntu.iso): ").strip()
    iso_path = os.path.join(ISO_DIR, iso_filename)
    logging.info(f"Starting download of ISO to {iso_path}...")
    try:
        # Run download with progress bar
        run_with_progress("Downloading ISO...", download_file, iso_url, iso_path)
        logging.info("ISO downloaded successfully.")
        return iso_path
    except Exception as e:
        logging.error(f"Failed to download ISO: {e}")
        return None


# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_vms():
    """
    List all virtual machines.
    """
    print_header("Current Virtual Machines")
    vms = get_vm_list()
    if vms:
        for i, vm in enumerate(vms, start=1):
            print(f"{NORD14}[{i}]{NC} {vm['name']} - {vm['state']}")
    else:
        logging.error("No VMs found.")
    prompt_enter()


def start_vm():
    """
    Start a virtual machine.
    """
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
    """
    Stop a virtual machine.
    """
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
    """
    Pause a virtual machine.
    """
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
    """
    Resume a paused virtual machine.
    """
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
    """
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete by number: ")
    if not vm_name:
        prompt_enter()
        return
    confirm = (
        input(
            f"Are you sure you want to delete VM '{vm_name}'? This will undefine the VM and delete its disk image. (y/n): "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        logging.warning("Deletion cancelled.")
        prompt_enter()
        return

    # Retrieve disk image path from VM XML
    xml_output = run_command(
        ["virsh", "dumpxml", vm_name], capture_output=True, check=False
    )
    disk = None
    if xml_output:
        match = re.search(r'source file="([^"]+)"', xml_output)
        if match:
            disk = match.group(1)
    if not disk:
        default_disk = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
        if os.path.exists(default_disk):
            disk = default_disk

    # Force shutdown if VM is running
    running_vms = run_command(["virsh", "list", "--state-running"], capture_output=True)
    if running_vms and vm_name in running_vms:
        run_command(["virsh", "destroy", vm_name])

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
    """
    Monitor virtual machine resources in real-time.
    """
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
            print(f"{NORD10}{'-' * 60}{NC}")
            output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
            if output:
                print(output)
            else:
                logging.error("Failed to retrieve VM info.")
            print(f"{NORD10}{'-' * 60}{NC}")
            time.sleep(5)
    except KeyboardInterrupt:
        logging.info("Exiting monitor mode.")
        prompt_enter()


def remote_console():
    """
    Connect to the console of a virtual machine.
    """
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
    """
    List available ISO files in the ISO directory.
    """
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


def create_vm():
    """
    Create a new virtual machine with specified parameters.
    """
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
        logging.error("Invalid input. vCPUs, RAM, and disk size must be numeric.")
        prompt_enter()
        return

    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        logging.error(
            f"Disk image {disk_image} already exists. Choose a different VM name or remove the existing image."
        )
        prompt_enter()
        return

    print(f"{NORD14}Provide installation ISO:{NC}")
    print(f"{NORD10}[1]{NC} Use existing ISO file")
    print(f"{NORD10}[2]{NC} Download ISO via URL")
    iso_choice = input("Enter your choice (1 or 2): ").strip()
    iso_path = ""
    if iso_choice == "1":
        iso_path = select_iso()
        if not iso_path:
            logging.error("No valid ISO selected. Cancelling VM creation.")
            prompt_enter()
            return
    elif iso_choice == "2":
        iso_path = download_iso()
        if not iso_path:
            prompt_enter()
            return
    else:
        logging.warning("Invalid selection. Cancelling VM creation.")
        prompt_enter()
        return

    logging.info(f"Creating disk image at {disk_image}...")
    if not run_command(
        ["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]
    ):
        logging.error("Failed to create disk image. Cleaning up.")
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
        "--name",
        vm_name,
        "--ram",
        str(ram),
        "--vcpus",
        str(vcpus),
        "--disk",
        f"path={disk_image},size={disk_size},format=qcow2",
        "--cdrom",
        iso_path,
        "--os-variant",
        "ubuntu20.04",
        "--graphics",
        "none",
        "--console",
        "pty,target_type=serial",
        "--noautoconsole",
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
    """
    List snapshots for a selected virtual machine.
    """
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
    """
    Create a snapshot of a virtual machine.
    """
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
    """
    Revert a virtual machine to a specified snapshot.
    """
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
    """
    Delete a snapshot from a virtual machine.
    """
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
    """
    Display the snapshot management menu.
    """
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
# DISK IMAGE MANAGEMENT
# ------------------------------------------------------------------------------
def delete_disk_image():
    """
    Manually delete a VM disk image from the VM_IMAGE_DIR.
    """
    print_header("Delete Disk Image")
    try:
        disks = [d for d in os.listdir(VM_IMAGE_DIR) if d.endswith(".qcow2")]
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
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    full_disk_path = os.path.join(VM_IMAGE_DIR, selected_disk)
    confirm = (
        input(f"Are you sure you want to delete disk image '{selected_disk}'? (y/n): ")
        .strip()
        .lower()
    )
    if confirm != "y":
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
    """
    Display the interactive main menu for VM management.
    """
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
    """
    Main entry point for the VM manager script.
    """
    if sys.version_info < (3, 6):
        print("This script requires Python 3.6 or higher.")
        sys.exit(1)
    check_root()
    check_dependencies()
    os.makedirs(Path(LOG_FILE).parent, exist_ok=True)
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)
    # Touch log file if missing
    Path(LOG_FILE).touch(exist_ok=True)
    setup_logging()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"VM MANAGER STARTED AT {now}")
    logging.info("=" * 80)
    interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
