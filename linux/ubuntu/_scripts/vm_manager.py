#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A robust Ubuntu/Linux VM manager that can list, create, start, stop,
  and delete VMs with improved error handling, logging, and optional
  command-line support. The script ensures that the default virtual network
  is active by creating the default network XML file (with proper permissions)
  and starting the network.

Usage:
  sudo ./vm_manager.py           # Interactive mode
  sudo ./vm_manager.py --list    # Direct command mode

Author: Your Name | License: MIT | Version: 6.0.0
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
import shlex
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Configuration Constants
LOG_FILE = "/var/log/vm_manager.log"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"

# Default resource settings
DEFAULT_VCPUS = 2
DEFAULT_RAM_MB = 2048
DEFAULT_DISK_GB = 20
DEFAULT_OS_VARIANT = "ubuntu22.04"

# Default network XML configuration (could be externalized to a config file)
DEFAULT_NETWORK_XML = """<network>
  <name>default</name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.2' end='192.168.122.254'/>
    </dhcp>
  </ip>
</network>
"""


def setup_logging():
    """Set up logging with both console output and file rotation."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file handler (5 MB per file, 3 backups)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(formatter)
    logger.addHandler(fh)


def run_command(command, capture_output=False, check=True, timeout=60):
    """
    Execute a shell command with improved error handling.
    Returns the command output if capture_output is True, else returns True.
    """
    try:
        # Use shlex.join for logging readability if available, else join manually.
        command_str = " ".join(shlex.quote(arg) for arg in command)
        logging.debug(f"Executing: {command_str}")
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result.stdout if capture_output else True
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {command_str}")
        return False
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Command error: {error_msg}")
        if check:
            raise
        return False


def check_dependencies():
    """Ensure required commands exist and that libvirt is active."""
    required_commands = ["virsh", "virt-install", "qemu-img"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.error(
            f"Missing dependencies: {', '.join(missing)}. "
            "Please install them (e.g., apt-get install libvirt-bin virtinst qemu-utils)."
        )
        return False

    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "libvirtd"], check=True)
    except subprocess.CalledProcessError:
        logging.warning(
            "libvirtd service is not active. Please start the service with 'systemctl start libvirtd'."
        )
    return True


def check_root():
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script requires root privileges. Please run with sudo.")
        return False
    return True


def ensure_default_network():
    """
    Ensure the 'default' virtual network is active.
    Create and define the network if it does not exist.
    """
    try:
        output = run_command(["virsh", "net-list", "--all"], capture_output=True)
        if "default" in output:
            if "active" in output:
                return True
            else:
                run_command(["virsh", "net-start", "default"])
                run_command(["virsh", "net-autostart", "default"])
                logging.info("Default network started and set to autostart.")
                return True
        else:
            # Write the default network XML to a temporary file.
            xml_path = "/tmp/default_network.xml"
            with open(xml_path, "w") as f:
                f.write(DEFAULT_NETWORK_XML)
            os.chmod(xml_path, 0o644)
            run_command(["virsh", "net-define", xml_path])
            run_command(["virsh", "net-start", "default"])
            run_command(["virsh", "net-autostart", "default"])
            logging.info("Default network defined, started, and set to autostart.")
            return True
    except Exception as e:
        logging.error(f"Error ensuring default network: {e}")
        return False


def get_vm_list():
    """Retrieve a list of VMs using 'virsh list --all'."""
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        if output:
            lines = output.strip().splitlines()
            # Identify header separator line (usually contains dashes)
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


def print_header(title):
    """Print a formatted header for sections."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


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
            print("Invalid input. Please enter a valid number.")


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

    # Validate resource specifications.
    if vcpus < 1 or ram < 512 or disk_size < 1:
        logging.error(
            "Resource specifications are too low. vCPUs must be >=1, RAM >=512MB, and disk size >=1GB."
        )
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
        run_command(["virsh", "destroy", vm_name], check=False)
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        logging.info(f"VM '{vm_name}' deleted successfully.")
    except Exception as e:
        logging.error(f"Error deleting VM '{vm_name}': {e}")


def start_vm():
    """Start a virtual machine after ensuring the default network is active."""
    print_header("Start Virtual Machine")
    if not ensure_default_network():
        print("Could not ensure default network is active. Aborting start.")
        return

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


def parse_args():
    """Set up and parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage Virtual Machines using libvirt (requires root privileges)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List all VMs")
    group.add_argument("--create", action="store_true", help="Create a new VM")
    group.add_argument("--start", action="store_true", help="Start an existing VM")
    group.add_argument("--stop", action="store_true", help="Stop an existing VM")
    group.add_argument("--delete", action="store_true", help="Delete an existing VM")
    return parser.parse_args()


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

    args = parse_args()

    # Command-line direct mode if any argument is provided.
    if args.list:
        list_vms()
    elif args.create:
        create_vm()
    elif args.start:
        start_vm()
    elif args.stop:
        stop_vm()
    elif args.delete:
        delete_vm()
    else:
        # Launch interactive menu if no direct command was provided.
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
        except Exception as ex:
            logging.error(f"Unhandled exception: {ex}")
            sys.exit(1)


if __name__ == "__main__":
    main()
