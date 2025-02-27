#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A robust Ubuntu/Linux VM manager that can list, create, start, stop,
  delete, and snapshot VMs with improved error handling, logging, and
  optional command-line support. The script ensures that the default virtual network
  is active by creating the default network XML file and starting the network.

Usage:
  sudo ./vm_manager.py           # Interactive mode
  sudo ./vm_manager.py --list    # Direct command mode

Author: Your Name | License: MIT | Version: 7.0.0
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
SNAPSHOT_DIR = "/var/lib/libvirt/snapshots"

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


def get_vm_snapshots(vm_name):
    """Retrieve a list of snapshots for a specific VM."""
    try:
        output = run_command(
            ["virsh", "snapshot-list", vm_name], capture_output=True, check=False
        )
        if not output or "failed" in output.lower() or "error" in output.lower():
            return []

        snapshots = []
        lines = output.strip().splitlines()
        # Skip header lines
        data_lines = [
            line
            for line in lines
            if line.strip()
            and not line.startswith("Name")
            and not line.startswith("----")
        ]

        for line in data_lines:
            parts = line.split()
            if len(parts) >= 1:
                snapshot = {
                    "name": parts[0],
                    "creation_time": " ".join(parts[1:3]) if len(parts) > 2 else "",
                    "state": parts[3] if len(parts) > 3 else "",
                }
                snapshots.append(snapshot)
        return snapshots
    except Exception as e:
        logging.error(f"Failed to retrieve snapshots for VM '{vm_name}': {e}")
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
        return []
    print("No.  Name                State")
    print("-" * 40)
    for index, vm in enumerate(vms, start=1):
        print(f"{index:>3}. {vm['name']:<20} {vm['state']}")
    return vms


def list_vm_snapshots(vm_name=None):
    """List snapshots for a specific VM or prompt for selection."""
    if not vm_name:
        vm_name = select_vm("Select a VM to list snapshots (or 'q' to cancel): ")
        if not vm_name:
            return

    snapshots = get_vm_snapshots(vm_name)
    print_header(f"Snapshots for VM: {vm_name}")

    if not snapshots:
        print(f"No snapshots found for VM '{vm_name}'.")
        return []

    print("No.  Name                Creation Time           State")
    print("-" * 60)
    for index, snapshot in enumerate(snapshots, start=1):
        print(
            f"{index:>3}. {snapshot['name']:<20} {snapshot['creation_time']:<22} {snapshot['state']}"
        )

    return snapshots


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


def select_snapshot(vm_name, prompt="Select a snapshot by number (or 'q' to cancel): "):
    """
    Prompt user to select a snapshot by number from the listed snapshots.
    Returns the selected snapshot's name, or None if cancelled.
    """
    snapshots = get_vm_snapshots(vm_name)
    if not snapshots:
        print(f"No snapshots available for VM '{vm_name}'.")
        return None

    print_header(f"Select a Snapshot for VM: {vm_name}")
    for index, snapshot in enumerate(snapshots, start=1):
        print(f"{index:>3}. {snapshot['name']:<20} {snapshot['creation_time']}")

    while True:
        choice = input(prompt).strip()
        if choice.lower() == "q":
            return None
        try:
            selection = int(choice)
            if 1 <= selection <= len(snapshots):
                return snapshots[selection - 1]["name"]
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
        print(f"VM '{vm_name}' created successfully.")
    except Exception as e:
        logging.error(f"Failed to create VM '{vm_name}': {e}")
        try:
            run_command(
                ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
            )
        except Exception:
            pass


def create_snapshot():
    """Create a snapshot of a virtual machine."""
    print_header("Create VM Snapshot")
    vm_name = select_vm("Select a VM to snapshot (or 'q' to cancel): ")
    if not vm_name:
        return

    # Get VM state
    output = run_command(["virsh", "domstate", vm_name], capture_output=True)
    if "running" not in output.lower():
        print(
            f"Warning: VM '{vm_name}' is not running. For best results, the VM should be running."
        )
        proceed = input("Do you want to continue anyway? (y/n): ").lower()
        if proceed != "y":
            return

    # Gather snapshot details
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_snapshot_name = f"{vm_name}-snap-{timestamp}"
    snapshot_name = (
        input(f"Enter snapshot name (default: {default_snapshot_name}): ").strip()
        or default_snapshot_name
    )

    description = input("Enter snapshot description (optional): ").strip()

    # Create snapshot directory if it doesn't exist
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Create snapshot XML file
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""

    snapshot_xml_path = os.path.join(SNAPSHOT_DIR, f"{snapshot_name}.xml")
    with open(snapshot_xml_path, "w") as f:
        f.write(snapshot_xml)

    try:
        run_command(
            ["virsh", "snapshot-create", vm_name, "--xmlfile", snapshot_xml_path]
        )
        logging.info(
            f"Snapshot '{snapshot_name}' created successfully for VM '{vm_name}'."
        )
        print(f"Snapshot '{snapshot_name}' created successfully.")
    except Exception as e:
        logging.error(f"Failed to create snapshot: {e}")
        print(f"Failed to create snapshot: {e}")
    finally:
        # Clean up temporary XML file
        if os.path.exists(snapshot_xml_path):
            os.unlink(snapshot_xml_path)


def revert_to_snapshot():
    """Revert a VM to a previous snapshot."""
    print_header("Revert VM to Snapshot")
    vm_name = select_vm("Select a VM to revert (or 'q' to cancel): ")
    if not vm_name:
        return

    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to revert to (or 'q' to cancel): "
    )
    if not snapshot_name:
        return

    # Confirm reversion
    confirm = input(
        f"Are you sure you want to revert VM '{vm_name}' to snapshot '{snapshot_name}'? (y/n): "
    ).lower()
    if confirm != "y":
        print("Revert operation cancelled.")
        return

    try:
        # Get current VM state
        vm_running = False
        output = run_command(["virsh", "domstate", vm_name], capture_output=True)
        if "running" in output.lower():
            vm_running = True
            # Stop VM if it's running
            run_command(["virsh", "shutdown", vm_name], check=False)
            print(f"Shutting down VM '{vm_name}'...")

            # Wait for VM to shut down (with timeout)
            timeout = 30  # seconds
            start_time = time.time()
            while time.time() - start_time < timeout:
                output = run_command(
                    ["virsh", "domstate", vm_name], capture_output=True
                )
                if "shut off" in output.lower():
                    break
                print(".", end="", flush=True)
                time.sleep(1)
            print()  # Newline after dots

            output = run_command(["virsh", "domstate", vm_name], capture_output=True)
            if "running" in output.lower():
                print("VM did not shut down gracefully, forcing off...")
                run_command(["virsh", "destroy", vm_name], check=False)

        # Revert to snapshot
        run_command(["virsh", "snapshot-revert", vm_name, snapshot_name])
        logging.info(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully."
        )
        print(f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully.")

        # Restart VM if it was running before
        if vm_running:
            restart = input("Would you like to restart the VM? (y/n): ").lower()
            if restart == "y":
                run_command(["virsh", "start", vm_name])
                print(f"VM '{vm_name}' started.")
    except Exception as e:
        logging.error(f"Failed to revert to snapshot: {e}")
        print(f"Failed to revert to snapshot: {e}")


def delete_snapshot():
    """Delete a VM snapshot."""
    print_header("Delete VM Snapshot")
    vm_name = select_vm("Select a VM (or 'q' to cancel): ")
    if not vm_name:
        return

    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to delete (or 'q' to cancel): "
    )
    if not snapshot_name:
        return

    # Confirm deletion
    confirm = input(
        f"Are you sure you want to delete snapshot '{snapshot_name}' for VM '{vm_name}'? (y/n): "
    ).lower()
    if confirm != "y":
        print("Deletion cancelled.")
        return

    try:
        run_command(["virsh", "snapshot-delete", vm_name, snapshot_name])
        logging.info(
            f"Snapshot '{snapshot_name}' for VM '{vm_name}' deleted successfully."
        )
        print(f"Snapshot '{snapshot_name}' for VM '{vm_name}' deleted successfully.")
    except Exception as e:
        logging.error(f"Failed to delete snapshot: {e}")
        print(f"Failed to delete snapshot: {e}")


def delete_vm():
    """Delete an existing virtual machine."""
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return

    # Check if VM has snapshots
    snapshots = get_vm_snapshots(vm_name)
    if snapshots:
        print(f"Warning: VM '{vm_name}' has {len(snapshots)} snapshot(s).")
        print("All snapshots will be deleted along with the VM.")

    confirm = input(f"Are you sure you want to delete VM '{vm_name}'? (y/n): ").lower()
    if confirm != "y":
        print("Deletion cancelled.")
        return

    try:
        # Try graceful shutdown first if VM is running
        output = run_command(
            ["virsh", "domstate", vm_name], capture_output=True, check=False
        )
        if "running" in output.lower():
            print(f"Shutting down VM '{vm_name}'...")
            run_command(["virsh", "shutdown", vm_name], check=False)

            # Give the VM some time to shut down gracefully
            time.sleep(5)

        # Force off if still running
        output = run_command(
            ["virsh", "domstate", vm_name], capture_output=True, check=False
        )
        if "running" in output.lower():
            print("Forcing VM off...")
            run_command(["virsh", "destroy", vm_name], check=False)

        # Delete the VM and storage
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        logging.info(f"VM '{vm_name}' deleted successfully.")
        print(f"VM '{vm_name}' deleted successfully.")
    except Exception as e:
        logging.error(f"Error deleting VM '{vm_name}': {e}")
        print(f"Error deleting VM '{vm_name}': {e}")


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
        print(f"VM '{vm_name}' started successfully.")
    except Exception as e:
        logging.error(f"Error starting VM '{vm_name}': {e}")
        print(f"Error starting VM '{vm_name}': {e}")


def stop_vm():
    """Stop a virtual machine, attempting graceful shutdown first."""
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        print(f"Sending shutdown signal to VM '{vm_name}'...")
        run_command(["virsh", "shutdown", vm_name])
        logging.info(f"Shutdown signal sent to VM '{vm_name}'.")

        # Give the VM some time to shut down gracefully
        print("Waiting for VM to shut down...", end="", flush=True)
        for _ in range(10):  # Wait up to 10 seconds
            time.sleep(1)
            print(".", end="", flush=True)
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "shut off" in output.lower():
                print("\nVM shut down successfully.")
                return

        print("\nVM is taking longer to shut down...")
        force_shutdown = input("Force VM to stop now? (y/n): ").lower()
        if force_shutdown == "y":
            run_command(["virsh", "destroy", vm_name])
            logging.info(f"VM '{vm_name}' forcefully stopped.")
            print(f"VM '{vm_name}' forcefully stopped.")
        else:
            print(
                f"VM '{vm_name}' shutdown in progress. Check status later with 'List VMs'."
            )
    except Exception as e:
        logging.error(f"Error stopping VM '{vm_name}': {e}")
        print(f"Error stopping VM '{vm_name}': {e}")


def show_vm_info():
    """Show detailed information about a VM."""
    print_header("VM Information")
    vm_name = select_vm("Select a VM to show info (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        # Get VM basic info
        output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
        print("\n--- Basic VM Information ---")
        print(output)

        # Get VM network info
        output = run_command(
            ["virsh", "domifaddr", vm_name], capture_output=True, check=False
        )
        if output and "failed" not in output.lower():
            print("\n--- Network Interfaces ---")
            print(output)

        # Get snapshots count
        snapshots = get_vm_snapshots(vm_name)
        print(f"\n--- Snapshots ---")
        print(f"Total snapshots: {len(snapshots)}")
        if snapshots:
            print("Available snapshots:")
            for i, snap in enumerate(snapshots, 1):
                print(f"  {i}. {snap['name']} ({snap['creation_time']})")

        # Get VM storage info
        output = run_command(["virsh", "domblklist", vm_name], capture_output=True)
        print("\n--- Storage Devices ---")
        print(output)
    except Exception as e:
        logging.error(f"Error retrieving VM info: {e}")
        print(f"Error retrieving VM info: {e}")


def interactive_menu():
    """Display the main interactive menu for managing VMs."""
    while True:
        print_header("VM Manager")
        print("1. List VMs")
        print("2. Create VM")
        print("3. Start VM")
        print("4. Stop VM")
        print("5. Delete VM")
        print("6. VM Information")
        print("7. Snapshot Management")
        print("8. Exit")

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
            show_vm_info()
        elif choice == "7":
            # Snapshot submenu
            while True:
                print_header("Snapshot Management")
                print("1. List Snapshots")
                print("2. Create Snapshot")
                print("3. Revert to Snapshot")
                print("4. Delete Snapshot")
                print("5. Return to Main Menu")

                snap_choice = input("Enter your choice: ").strip()

                if snap_choice == "1":
                    list_vm_snapshots()
                elif snap_choice == "2":
                    create_snapshot()
                elif snap_choice == "3":
                    revert_to_snapshot()
                elif snap_choice == "4":
                    delete_snapshot()
                elif snap_choice == "5":
                    break
                else:
                    print("Invalid choice. Please try again.")

                if snap_choice != "5":
                    input("\nPress Enter to continue...")
        elif choice == "8":
            print("Exiting VM Manager.")
            break
        else:
            print("Invalid choice. Please try again.")

        if choice != "8":
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
    group.add_argument("--info", action="store_true", help="Show VM information")

    # Snapshot-related arguments
    group.add_argument(
        "--list-snapshots", action="store_true", help="List snapshots for a VM"
    )
    group.add_argument(
        "--create-snapshot", action="store_true", help="Create a snapshot for a VM"
    )
    group.add_argument(
        "--revert-snapshot", action="store_true", help="Revert a VM to a snapshot"
    )
    group.add_argument(
        "--delete-snapshot", action="store_true", help="Delete a VM snapshot"
    )

    # VM name argument (optional for most commands)
    parser.add_argument("--vm", help="Specify VM name for operations")

    # Snapshot name argument (optional for snapshot operations)
    parser.add_argument("--snapshot", help="Specify snapshot name for operations")

    return parser.parse_args()


def main():
    """Main entry point for the script."""
    if sys.version_info < (3, 6):
        print("Python 3.6 or higher is required.")
        sys.exit(1)

    setup_logging()

    if not check_root():
        sys.exit(1)

    # Create necessary directories
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

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
        if args.vm:
            # If VM name is provided, start specific VM
            try:
                run_command(["virsh", "start", args.vm])
                logging.info(f"VM '{args.vm}' started successfully.")
                print(f"VM '{args.vm}' started successfully.")
            except Exception as e:
                logging.error(f"Error starting VM '{args.vm}': {e}")
                print(f"Error starting VM '{args.vm}': {e}")
        else:
            start_vm()
    elif args.stop:
        if args.vm:
            # If VM name is provided, stop specific VM
            try:
                run_command(["virsh", "shutdown", args.vm])
                logging.info(f"Shutdown signal sent to VM '{args.vm}'.")
                print(f"Shutdown signal sent to VM '{args.vm}'.")
            except Exception as e:
                logging.error(f"Error stopping VM '{args.vm}': {e}")
                print(f"Error stopping VM '{args.vm}': {e}")
        else:
            stop_vm()
    elif args.delete:
        if args.vm:
            # Confirm deletion
            confirm = input(
                f"Are you sure you want to delete VM '{args.vm}'? (y/n): "
            ).lower()
            if confirm == "y":
                try:
                    run_command(["virsh", "destroy", args.vm], check=False)
                    run_command(["virsh", "undefine", args.vm, "--remove-all-storage"])
                    logging.info(f"VM '{args.vm}' deleted successfully.")
                    print(f"VM '{args.vm}' deleted successfully.")
                except Exception as e:
                    logging.error(f"Error deleting VM '{args.vm}': {e}")
                    print(f"Error deleting VM '{args.vm}': {e}")
            else:
                print("Deletion cancelled.")
        else:
            delete_vm()
    elif args.info:
        if args.vm:
            try:
                # Get VM basic info
                output = run_command(["virsh", "dominfo", args.vm], capture_output=True)
                print("\n--- Basic VM Information ---")
                print(output)

                # Get snapshots count
                snapshots = get_vm_snapshots(args.vm)
                print(f"\nSnapshots: {len(snapshots)}")
            except Exception as e:
                logging.error(f"Error retrieving VM info: {e}")
                print(f"Error retrieving VM info: {e}")
        else:
            show_vm_info()
    # Snapshot command handling
    elif args.list_snapshots:
        if args.vm:
            list_vm_snapshots(args.vm)
        else:
            list_vm_snapshots()
    elif args.create_snapshot:
        if args.vm:
            # Create snapshot with specified name or auto-generated name
            vm_name = args.vm
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            snapshot_name = args.snapshot or f"{vm_name}-snap-{timestamp}"
            description = (
                f"Snapshot created on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Create snapshot directory if it doesn't exist
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)

            # Create snapshot XML file
            snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""

            snapshot_xml_path = os.path.join(SNAPSHOT_DIR, f"{snapshot_name}.xml")
            with open(snapshot_xml_path, "w") as f:
                f.write(snapshot_xml)

            try:
                run_command(
                    [
                        "virsh",
                        "snapshot-create",
                        vm_name,
                        "--xmlfile",
                        snapshot_xml_path,
                    ]
                )
                logging.info(
                    f"Snapshot '{snapshot_name}' created successfully for VM '{vm_name}'."
                )
                print(f"Snapshot '{snapshot_name}' created successfully.")
            except Exception as e:
                logging.error(f"Failed to create snapshot: {e}")
                print(f"Failed to create snapshot: {e}")
            finally:
                # Clean up temporary XML file
                if os.path.exists(snapshot_xml_path):
                    os.unlink(snapshot_xml_path)
        else:
            create_snapshot()
    elif args.revert_snapshot:
        if args.vm and args.snapshot:
            # Confirm reversion
            confirm = input(
                f"Are you sure you want to revert VM '{args.vm}' to snapshot '{args.snapshot}'? (y/n): "
            ).lower()
            if confirm == "y":
                try:
                    run_command(["virsh", "snapshot-revert", args.vm, args.snapshot])
                    logging.info(
                        f"VM '{args.vm}' reverted to snapshot '{args.snapshot}' successfully."
                    )
                    print(
                        f"VM '{args.vm}' reverted to snapshot '{args.snapshot}' successfully."
                    )
                except Exception as e:
                    logging.error(f"Failed to revert to snapshot: {e}")
                    print(f"Failed to revert to snapshot: {e}")
            else:
                print("Revert operation cancelled.")
        else:
            revert_to_snapshot()
    elif args.delete_snapshot:
        if args.vm and args.snapshot:
            # Confirm deletion
            confirm = input(
                f"Are you sure you want to delete snapshot '{args.snapshot}' for VM '{args.vm}'? (y/n): "
            ).lower()
            if confirm == "y":
                try:
                    run_command(["virsh", "snapshot-delete", args.vm, args.snapshot])
                    logging.info(
                        f"Snapshot '{args.snapshot}' for VM '{args.vm}' deleted successfully."
                    )
                    print(
                        f"Snapshot '{args.snapshot}' for VM '{args.vm}' deleted successfully."
                    )
                except Exception as e:
                    logging.error(f"Failed to delete snapshot: {e}")
                    print(f"Failed to delete snapshot: {e}")
            else:
                print("Deletion cancelled.")
        else:
            delete_snapshot()
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
