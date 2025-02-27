#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A straightforward Ubuntu/Linux VM manager that can list, create, start, stop,
  pause, resume, and delete VMs with basic error handling and logging.

Usage:
  sudo ./vm_manager.py

Author: Your Name | License: MIT | Version: 5.1.0
"""

import atexit
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

# Simplified logging and configuration
LOG_FILE = "/var/log/vm_manager.log"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Directories for VM images and ISOs
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"

# Default sizes and resources
DEFAULT_VCPUS = 2
DEFAULT_RAM_MB = 2048
DEFAULT_DISK_GB = 20
DEFAULT_OS_VARIANT = "ubuntu22.04"

# VM Status
VM_STATUS = {
    "running": "Running",
    "paused": "Paused",
    "shut off": "Stopped",
    "crashed": "Crashed",
    "pmsuspended": "Suspended",
}


def setup_logging():
    """
    Set up basic logging with console and file handlers.
    """
    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )

    # Rotate log file if it's too large
    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")
    except Exception as e:
        logging.warning(f"Failed to rotate log file: {e}")


def print_header(title):
    """
    Print a simple header for sections.
    """
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_command(command, capture_output=False, check=True, timeout=60):
    """
    Execute a shell command with error handling.
    """
    try:
        logging.debug(f"Running command: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result.stdout if capture_output else True
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out after {timeout} seconds: {' '.join(command)}")
        return False
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Command failed: {error_msg}")
        if check:
            raise
        return False


def check_dependencies():
    """
    Check for required commands and libraries.
    """
    required_commands = ["virsh", "virt-install", "qemu-img", "wget"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]

    if missing:
        logging.error(f"Missing dependencies: {', '.join(missing)}")
        return False

    # Check libvirt service status
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "libvirtd"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning("libvirtd service may not be running.")

    return True


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root (sudo).")
        return False
    return True


def get_vm_list():
    """
    Retrieve a list of VMs.
    """
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        if output:
            lines = output.strip().splitlines()
            sep_index = next(
                (i for i, line in enumerate(lines) if line.lstrip().startswith("---")),
                None,
            )

            if sep_index is not None:
                for line in lines[sep_index + 1 :]:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            vms.append(
                                {
                                    "id": parts[0],
                                    "name": parts[1],
                                    "state": " ".join(parts[2:])
                                    if len(parts) > 2
                                    else "",
                                }
                            )
        return vms
    except Exception as e:
        logging.error(f"Failed to get VM list: {e}")
        return []


def list_vms():
    """
    Display a list of virtual machines.
    """
    print_header("Virtual Machines")
    vms = get_vm_list()

    if not vms:
        print("No VMs found.")
        return

    print("ID  Name                State")
    print("-" * 40)
    for vm in vms:
        print(f"{vm['id']:2}  {vm['name']:<20} {vm['state']}")


def select_vm(prompt="Select a VM by number: "):
    """
    Prompt user to select a VM from the list.
    """
    vms = get_vm_list()
    if not vms:
        print("No VMs found.")
        return None

    list_vms()
    while True:
        try:
            choice = input(prompt).strip()
            if choice.lower() == "q":
                return None

            index = int(choice) - 1
            if 0 <= index < len(vms):
                return vms[index]["name"]
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")


def create_vm():
    """
    Create a new virtual machine.
    """
    print_header("Create New Virtual Machine")

    # VM name
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = (
        input(f"Enter VM name (default: {default_name}): ").strip() or default_name
    )

    # Resource specifications
    try:
        vcpus = int(input(f"vCPUs (default: {DEFAULT_VCPUS}): ") or DEFAULT_VCPUS)
        ram = int(input(f"RAM in MB (default: {DEFAULT_RAM_MB}): ") or DEFAULT_RAM_MB)
        disk_size = int(
            input(f"Disk size in GB (default: {DEFAULT_DISK_GB}): ") or DEFAULT_DISK_GB
        )
    except ValueError:
        logging.error("Invalid input. vCPUs, RAM, and disk size must be numeric.")
        return

    # Validate resource specs
    if vcpus < 1 or ram < 512 or disk_size < 1:
        logging.error("Invalid resource specifications.")
        return

    # Disk image path
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        logging.error(f"Disk image {disk_image} already exists.")
        return

    # ISO selection/download (simplified)
    print("\nSelect Installation Media:")
    print("1. Use existing ISO")
    print("2. Download ISO")
    print("3. Cancel")

    choice = input("Enter choice: ").strip()
    if choice == "3":
        return

    # TODO: Implement ISO selection/download logic
    # This is a placeholder and would need more robust implementation
    iso_path = "/path/to/installation/iso"  # Replace with actual selection/download

    # Create disk image
    try:
        run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"])
    except Exception as e:
        logging.error(f"Failed to create disk image: {e}")
        return

    # VM installation command
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
        logging.error(f"Failed to create VM: {e}")
        # Cleanup
        try:
            run_command(
                ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
            )
        except:
            pass


def delete_vm():
    """
    Delete a virtual machine.
    """
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete: ")
    if not vm_name:
        return

    # Confirm deletion
    confirm = input(f"Are you sure you want to delete VM '{vm_name}'? (y/n): ").lower()
    if confirm != "y":
        print("Deletion cancelled.")
        return

    try:
        # Force stop if running
        run_command(["virsh", "destroy", vm_name], check=False)

        # Undefine and remove storage
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        logging.info(f"VM '{vm_name}' deleted successfully.")
    except Exception as e:
        logging.error(f"Failed to delete VM: {e}")


def start_vm():
    """
    Start a virtual machine.
    """
    print_header("Start Virtual Machine")
    vm_name = select_vm("Select a VM to start: ")
    if not vm_name:
        return

    try:
        run_command(["virsh", "start", vm_name])
        logging.info(f"VM '{vm_name}' started successfully.")
    except Exception as e:
        logging.error(f"Failed to start VM: {e}")


def stop_vm():
    """
    Stop a virtual machine.
    """
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop: ")
    if not vm_name:
        return

    try:
        # Attempt graceful shutdown first
        run_command(["virsh", "shutdown", vm_name])
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
    except Exception:
        # Force shutdown if graceful fails
        try:
            run_command(["virsh", "destroy", vm_name])
            logging.info(f"VM '{vm_name}' forcefully stopped.")
        except Exception as e:
            logging.error(f"Failed to stop VM: {e}")


def interactive_menu():
    """
    Display the main menu for VM management.
    """
    while True:
        print_header("VM Manager")
        print("1. List VMs")
        print("2. Create VM")
        print("3. Start VM")
        print("4. Stop VM")
        print("5. Delete VM")
        print("6. Exit")

        choice = input("Enter your choice: ").strip()

        try:
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
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            input("Press Enter to continue...")


def main():
    """
    Main entry point for the VM manager script.
    """
    # Check Python version
    if sys.version_info < (3, 6):
        print("This script requires Python 3.6 or higher.")
        sys.exit(1)

    # Setup logging
    setup_logging()

    # Check root privileges
    if not check_root():
        sys.exit(1)

    # Create necessary directories
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    # Check dependencies
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
