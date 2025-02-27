#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A straightforward Ubuntu/Linux VM manager that can list, create, start, stop,
  and delete VMs with basic error handling and logging.

Usage:
  sudo ./vm_manager.py

Author: Your Name | License: MIT | Version: 5.2.0
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
from pathlib import Path

# Configuration
LOG_FILE = "/var/log/vm_manager.log"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"

# Default resource settings
DEFAULT_VCPUS = 2
DEFAULT_RAM_MB = 2048
DEFAULT_DISK_GB = 20
DEFAULT_OS_VARIANT = "ubuntu22.04"

# VM Status dictionary (for reference)
VM_STATUS = {
    "running": "Running",
    "paused": "Paused",
    "shut off": "Stopped",
    "crashed": "Crashed",
    "pmsuspended": "Suspended",
}


def setup_logging():
    """Set up logging to both console and file with rotation."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )

    # Rotate log file if it exceeds 10MB
    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated log file to {backup_log}")
    except Exception as e:
        logging.warning(f"Could not rotate log file: {e}")


def print_header(title):
    """Print a formatted header for a section."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_command(command, capture_output=False, check=True, timeout=60):
    """
    Execute a shell command with error handling.
    Returns command output if capture_output is True, else True.
    """
    try:
        logging.debug(f"Executing: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result.stdout if capture_output else True
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {' '.join(command)}")
        return False
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Command error: {error_msg}")
        if check:
            raise
        return False


def check_dependencies():
    """Check if required commands are available and if libvirt is active."""
    required_commands = ["virsh", "virt-install", "qemu-img"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.error(f"Missing dependencies: {', '.join(missing)}")
        return False

    # Check if libvirt service is active
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "libvirtd"], check=True)
    except Exception:
        logging.warning("libvirtd service may not be running.")
    return True


def check_root():
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script requires root privileges. Please run with sudo.")
        return False
    return True


def get_vm_list():
    """Retrieve a list of VMs using 'virsh list --all'."""
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        if output:
            lines = output.strip().splitlines()
            # Find the separator line (usually starts with '---')
            try:
                sep_index = next(
                    i for i, line in enumerate(lines) if line.lstrip().startswith("---")
                )
            except StopIteration:
                sep_index = 1
            for line in lines[sep_index + 1 :]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        # Append VM details; id may be '-' if not running.
                        vms.append(
                            {
                                "id": parts[0],
                                "name": parts[1],
                                "state": " ".join(parts[2:]) if len(parts) > 2 else "",
                            }
                        )
        return vms
    except Exception as e:
        logging.error(f"Failed to retrieve VM list: {e}")
        return []


def list_vms():
    """Display a numbered list of VMs."""
    print_header("Virtual Machines")
    vms = get_vm_list()
    if not vms:
        print("No VMs found.")
        return

    print("No.  Name                State")
    print("-" * 40)
    for index, vm in enumerate(vms, start=1):
        print(f"{index:>3}. {vm['name']:<20} {vm['state']}")
    return vms


def select_vm(prompt="Select a VM by number (or 'q' to cancel): "):
    """
    Prompt user to select a VM by number from the listed VMs.
    Returns the selected VM's name, or None if cancelled.
    """
    vms = get_vm_list()
    if not vms:
        print("No VMs available.")
        return None

    # Display VMs with numbering
    print_header("Select a Virtual Machine")
    for index, vm in enumerate(vms, start=1):
        print(f"{index:>3}. {vm['name']:<20} {vm['state']}")

    while True:
        choice = input(prompt).strip()
        if choice.lower() == "q":
            return None
        try:
            selection = int(choice)
            if 1 <= selection <= len(vms):
                return vms[selection - 1]["name"]
            else:
                print("Invalid number. Please select from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def create_vm():
    """Create a new virtual machine by gathering user inputs."""
    print_header("Create New Virtual Machine")
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = (
        input(f"Enter VM name (default: {default_name}): ").strip() or default_name
    )

    try:
        vcpus = int(input(f"vCPUs (default: {DEFAULT_VCPUS}): ") or DEFAULT_VCPUS)
        ram = int(input(f"RAM in MB (default: {DEFAULT_RAM_MB}): ") or DEFAULT_RAM_MB)
        disk_size = int(
            input(f"Disk size in GB (default: {DEFAULT_DISK_GB}): ") or DEFAULT_DISK_GB
        )
    except ValueError:
        logging.error("Invalid input: vCPUs, RAM, and disk size must be numbers.")
        return

    if vcpus < 1 or ram < 512 or disk_size < 1:
        logging.error("Resource specifications are too low.")
        return

    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        logging.error(f"Disk image '{disk_image}' already exists.")
        return

    print("\nSelect Installation Media:")
    print("1. Use existing ISO")
    print("2. Cancel")
    media_choice = input("Enter your choice: ").strip()
    if media_choice != "1":
        print("VM creation cancelled.")
        return

    iso_path = input("Enter the full path to the ISO file: ").strip()
    if not os.path.isfile(iso_path):
        logging.error("ISO file not found. VM creation cancelled.")
        return

    try:
        run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"])
    except Exception as e:
        logging.error(f"Failed to create disk image: {e}")
        return

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
        DEFAULT_OS_VARIANT,
        "--network",
        "default",
        "--graphics",
        "vnc",
        "--noautoconsole",
    ]
    try:
        run_command(virt_install_cmd)
        logging.info(f"VM '{vm_name}' created successfully.")
    except Exception as e:
        logging.error(f"Failed to create VM '{vm_name}': {e}")
        try:
            run_command(
                ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
            )
        except Exception:
            pass


def delete_vm():
    """Delete an existing virtual machine."""
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return

    confirm = input(f"Are you sure you want to delete VM '{vm_name}'? (y/n): ").lower()
    if confirm != "y":
        print("Deletion cancelled.")
        return

    try:
        # Attempt to destroy VM if running
        run_command(["virsh", "destroy", vm_name], check=False)
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        logging.info(f"VM '{vm_name}' deleted successfully.")
    except Exception as e:
        logging.error(f"Error deleting VM '{vm_name}': {e}")


def start_vm():
    """Start a virtual machine."""
    print_header("Start Virtual Machine")
    vm_name = select_vm("Select a VM to start (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        run_command(["virsh", "start", vm_name])
        logging.info(f"VM '{vm_name}' started successfully.")
    except Exception as e:
        logging.error(f"Error starting VM '{vm_name}': {e}")


def stop_vm():
    """Stop a virtual machine, attempting graceful shutdown first."""
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        run_command(["virsh", "shutdown", vm_name])
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
    except Exception:
        try:
            run_command(["virsh", "destroy", vm_name])
            logging.info(f"VM '{vm_name}' forcefully stopped.")
        except Exception as e:
            logging.error(f"Error stopping VM '{vm_name}': {e}")


def interactive_menu():
    """Display the main interactive menu for managing VMs."""
    while True:
        print_header("VM Manager")
        print("1. List VMs")
        print("2. Create VM")
        print("3. Start VM")
        print("4. Stop VM")
        print("5. Delete VM")
        print("6. Exit")

        choice = input("Enter your choice: ").strip()
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
            print("Exiting VM Manager.")
            break
        else:
            print("Invalid choice. Please try again.")

        input("\nPress Enter to continue...")


def main():
    """Main entry point for the script."""
    if sys.version_info < (3, 6):
        print("Python 3.6 or higher is required.")
        sys.exit(1)

    setup_logging()

    if not check_root():
        sys.exit(1)

    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    if not check_dependencies():
        logging.error("Missing critical dependencies.")
        sys.exit(1)

    try:
        interactive_menu()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()
