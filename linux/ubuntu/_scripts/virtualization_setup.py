#!/usr/bin/env python3
"""
Complete Virtualization Environment Setup Script

This script provides an all-in-one solution for setting up a virtualization environment:
- Installs all required virtualization packages (QEMU/KVM, libvirt, etc.)
- Configures the default NAT network, ensures it's started and set to autostart
- Updates all VMs to use the default network
- Sets proper permissions on VM storage folders
- Ensures the user has proper group membership
- Configures all VMs to autostart at system boot
- Starts all defined VMs

The script uses only standard library components, provides rich progress tracking,
comprehensive error handling, and clear color-coded status messages.

Note: This script must be run with root privileges and will run unattended.
"""

import logging
import os
import pwd
import grp
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set, Union

# Configuration
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking

# VM Storage paths
DEFAULT_VM_FOLDERS = ["/var/lib/libvirt/images"]

# Virtualization package configuration
PACKAGES: List[str] = [
    "qemu-kvm",
    "qemu-utils",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virt-manager",
    "bridge-utils",
    "cpu-checker",
    "ovmf",
    "virtinst",
]

# Virtualization services configuration
SERVICES: List[str] = [
    "libvirtd",
    "virtlogd",
]

# Permission settings
OWNER = "root"
GROUP = "libvirt-qemu"
DIR_MODE = 0o2770
FILE_MODE = 0o0660

# Default network XML configuration for libvirt
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


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


#####################################
# Progress Tracking Functions
#####################################


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

    def __init__(self, total: int, desc: str = "", width: int = 50):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_size(self, bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = "=" * filled + "-" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0

        sys.stdout.write(
            f"\r{self.desc}: |{bar}| {percent:>5.1f}% "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{self._format_size(rate)}/s] [ETA: {eta:.0f}s]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


#####################################
# UI and Command Execution Functions
#####################################


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def run_command(
    cmd: Union[List[str], str], check: bool = True, stream_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Run command with error handling and optional output streaming

    Args:
        cmd: Command to run (list or string)
        check: Whether to raise an exception on failure
        stream_output: Whether to stream command output to stdout

    Returns:
        CompletedProcess instance with command results
    """
    try:
        if stream_output:
            if isinstance(cmd, str):
                cmd_list = cmd.split()
            else:
                cmd_list = cmd

            process = subprocess.Popen(
                cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            while True:
                line = process.stdout.readline()
                if not line:
                    break
                sys.stdout.write(line)

            process.wait()
            if check and process.returncode != 0:
                cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
                print(f"{Colors.RED}Command failed: {cmd_str}")
                print(f"Exit code: {process.returncode}{Colors.ENDC}")
                raise subprocess.CalledProcessError(process.returncode, cmd)

            return subprocess.CompletedProcess(cmd, process.returncode, "", "")
        else:
            return subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                check=check,
                text=True,
                capture_output=True,
            )
    except subprocess.CalledProcessError as e:
        if check:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            print(f"{Colors.RED}Command failed: {cmd_str}")
            print(f"Error: {e.stderr}{Colors.ENDC}")
        raise
    except Exception as e:
        if check:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            print(f"{Colors.RED}Error executing command: {cmd_str}")
            print(f"Error: {str(e)}{Colors.ENDC}")
        raise


def execute_with_progress(cmd: Union[List[str], str], desc: str = "Progress") -> bool:
    """
    Execute a command with a simple progress indicator

    Args:
        cmd: Command to run (list or string)
        desc: Description for the progress display

    Returns:
        True if command succeeds, False otherwise
    """
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    print(f"{desc}... ", end="", flush=True)
    try:
        run_command(cmd, check=True)
        print(f"{Colors.GREEN}Done!{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"{Colors.RED}Failed!{Colors.ENDC}")
        return False


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully"""
    print(f"\n{Colors.YELLOW}Process interrupted. Exiting...{Colors.ENDC}")
    sys.exit(1)


#####################################
# Package Installation Functions
#####################################


def update_package_lists() -> bool:
    """Update apt package lists"""
    print_header("Updating Package Lists")
    return execute_with_progress(["apt-get", "update"], "Updating package lists")


def install_packages(packages: List[str]) -> bool:
    """
    Install required packages

    Args:
        packages: List of package names to install

    Returns:
        True if all packages were installed successfully, False otherwise
    """
    print_header("Installing Virtualization Packages")

    total_packages = len(packages)
    progress = ProgressBar(total_packages, desc="Installation progress")

    for i, package in enumerate(packages):
        print(f"\nInstalling {package} ({i + 1}/{total_packages})...")
        try:
            run_command(
                ["apt-get", "install", "-y", package], check=True, stream_output=True
            )
            print(f"{Colors.GREEN}Successfully installed {package}{Colors.ENDC}")
            progress.update(1)
        except Exception as e:
            print(f"{Colors.RED}Failed to install {package}: {str(e)}{Colors.ENDC}")
            return False

    return True


#####################################
# Service Management Functions
#####################################


def enable_services(services: List[str]) -> bool:
    """
    Enable and start all required services

    Args:
        services: List of service names to enable

    Returns:
        True if all services were enabled successfully, False otherwise
    """
    print_header("Enabling Virtualization Services")

    for service in services:
        print(f"Enabling and starting {service}...")
        try:
            run_command(["systemctl", "enable", "--now", service], check=True)
            print(
                f"{Colors.GREEN}Successfully enabled and started {service}{Colors.ENDC}"
            )
        except Exception as e:
            print(
                f"{Colors.YELLOW}Warning: Failed to enable/start {service}: {str(e)}{Colors.ENDC}"
            )
            print("Continuing anyway, as the service might already be running...")

    return True


#####################################
# Network Management Functions
#####################################


def create_and_start_default_network() -> bool:
    """
    Create, start, and enable autostart for the default network

    Returns:
        True if network is successfully configured, False otherwise
    """
    print_header("Configuring Default Virtual Network")

    # Check if default network exists
    try:
        result = run_command(["virsh", "net-list", "--all"])
        if "default" not in result.stdout:
            # Create default network from XML
            print("Creating default network...")
            with open("/tmp/default_network.xml", "w") as f:
                f.write(DEFAULT_NETWORK_XML)

            try:
                run_command(["virsh", "net-define", "/tmp/default_network.xml"])
                print(
                    f"{Colors.GREEN}Default network defined successfully{Colors.ENDC}"
                )
            except Exception as e:
                print(
                    f"{Colors.RED}Failed to define default network: {str(e)}{Colors.ENDC}"
                )
                return False
        else:
            print("Default network already exists")
    except Exception as e:
        print(f"{Colors.RED}Error checking network existence: {str(e)}{Colors.ENDC}")
        return False

    # Start the network (if not running)
    try:
        run_command(["virsh", "net-start", "default"], check=False)
        print(f"{Colors.GREEN}Default network started{Colors.ENDC}")
    except Exception:
        print(
            f"{Colors.YELLOW}Note: Default network may already be running{Colors.ENDC}"
        )

    # Set to autostart
    try:
        run_command(["virsh", "net-autostart", "default"], check=False)
        print(f"{Colors.GREEN}Default network set to autostart{Colors.ENDC}")
    except Exception:
        print(
            f"{Colors.YELLOW}Note: Default network may already be set to autostart{Colors.ENDC}"
        )

    return True


#####################################
# VM Management Functions
#####################################


def get_vm_list() -> List[Dict[str, str]]:
    """
    Get list of all defined virtual machines

    Returns:
        List of VM info dictionaries with 'id', 'name', and 'state' keys
    """
    vms = []
    try:
        result = run_command(["virsh", "list", "--all"])
        lines = result.stdout.strip().splitlines()

        # Find separator line
        try:
            sep_index = next(
                i for i, line in enumerate(lines) if line.lstrip().startswith("---")
            )
        except StopIteration:
            sep_index = 1

        # Parse VM data
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
    except Exception as e:
        print(f"{Colors.RED}Error retrieving VM list: {str(e)}{Colors.ENDC}")

    return vms


def update_vm_networks() -> None:
    """
    Update all VMs to use the default network
    """
    print_header("Updating Virtual Machines to Use Default NAT Network")

    vms = get_vm_list()
    if not vms:
        print(f"{Colors.YELLOW}No virtual machines found to update{Colors.ENDC}")
        return

    total_vms = len(vms)
    progress = ProgressBar(total_vms, desc="VM network update progress")

    for vm in vms:
        vm_name = vm["name"]
        print(f"\nProcessing VM: {vm_name}")

        try:
            # Get VM XML
            result = run_command(["virsh", "dumpxml", vm_name])
            root = ET.fromstring(result.stdout)
            interfaces = root.findall("devices/interface")

            modified = False
            for iface in interfaces:
                if iface.get("type") == "network":
                    source = iface.find("source")
                    if source is not None and source.get("network") != "default":
                        mac_elem = iface.find("mac")
                        if mac_elem is not None:
                            mac = mac_elem.get("address")
                            # Detach non-default network interface
                            try:
                                detach_cmd = [
                                    "virsh",
                                    "detach-interface",
                                    vm_name,
                                    "network",
                                    "--mac",
                                    mac,
                                    "--config",
                                ]

                                # Add --live flag if VM is running
                                if vm["state"].lower() == "running":
                                    detach_cmd.append("--live")

                                run_command(detach_cmd)
                                print(
                                    f"{Colors.YELLOW}Detached interface with MAC {mac}{Colors.ENDC}"
                                )
                                modified = True
                            except Exception as e:
                                print(
                                    f"{Colors.RED}Failed to detach interface: {str(e)}{Colors.ENDC}"
                                )

            if modified:
                # Attach new default network interface
                attach_cmd = [
                    "virsh",
                    "attach-interface",
                    vm_name,
                    "network",
                    "default",
                    "--model",
                    "virtio",
                    "--config",
                ]

                # Add --live flag if VM is running
                if vm["state"].lower() == "running":
                    attach_cmd.append("--live")

                try:
                    run_command(attach_cmd)
                    print(
                        f"{Colors.GREEN}Attached new default network interface{Colors.ENDC}"
                    )
                except Exception as e:
                    print(
                        f"{Colors.RED}Failed to attach interface: {str(e)}{Colors.ENDC}"
                    )
            else:
                print(f"{Colors.GREEN}VM already using default network{Colors.ENDC}")

        except Exception as e:
            print(f"{Colors.RED}Error processing VM {vm_name}: {str(e)}{Colors.ENDC}")

        progress.update(1)


def set_vms_autostart() -> None:
    """
    Configure all VMs to autostart at system boot
    """
    print_header("Setting VMs to Autostart at Boot")

    vms = get_vm_list()
    if not vms:
        print(f"{Colors.YELLOW}No virtual machines found to configure{Colors.ENDC}")
        return

    total_vms = len(vms)
    progress = ProgressBar(total_vms, desc="Autostart configuration progress")

    for vm in vms:
        vm_name = vm["name"]
        print(f"Setting VM '{vm_name}' to autostart... ", end="", flush=True)

        try:
            run_command(["virsh", "autostart", vm_name])
            print(f"{Colors.GREEN}Done!{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}Failed: {str(e)}{Colors.ENDC}")

        progress.update(1)


def start_all_vms() -> None:
    """
    Start all defined virtual machines that aren't already running
    """
    print_header("Starting All Virtual Machines")

    vms = get_vm_list()
    if not vms:
        print(f"{Colors.YELLOW}No virtual machines found to start{Colors.ENDC}")
        return

    # Filter VMs that aren't running
    vms_to_start = [vm for vm in vms if vm["state"].lower() != "running"]

    if not vms_to_start:
        print(f"{Colors.YELLOW}All VMs are already running{Colors.ENDC}")
        return

    total_vms = len(vms_to_start)
    progress = ProgressBar(total_vms, desc="VM startup progress")

    print(f"Starting {total_vms} virtual machines...")

    for vm in vms_to_start:
        vm_name = vm["name"]
        print(f"Starting VM '{vm_name}'... ", end="", flush=True)

        try:
            run_command(["virsh", "start", vm_name])
            print(f"{Colors.GREEN}Started!{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}Failed: {str(e)}{Colors.ENDC}")

        progress.update(1)
        # Short delay between VM starts to avoid overloading the system
        time.sleep(2)


#####################################
# Permission and Group Functions
#####################################


def fix_vm_folder_permissions(folders: List[str]) -> None:
    """
    Fix permissions on VM folders

    Args:
        folders: List of folder paths to fix permissions on
    """
    print_header("Fixing VM Folder Permissions")

    # Get UID and GID
    try:
        uid = pwd.getpwnam(OWNER).pw_uid
        gid = grp.getgrnam(GROUP).gr_gid
    except KeyError as e:
        print(f"{Colors.RED}Error: User or group not found: {str(e)}{Colors.ENDC}")
        return

    for folder in folders:
        print(f"Processing folder: {folder}")

        if not os.path.exists(folder):
            print(f"{Colors.YELLOW}Path not found, creating: {folder}{Colors.ENDC}")
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                print(f"{Colors.RED}Failed to create directory: {str(e)}{Colors.ENDC}")
                continue

        # Count files for progress tracking
        total_items = 0
        for root, dirs, files in os.walk(folder):
            total_items += len(dirs) + len(files) + 1  # +1 for root dir itself

        progress = ProgressBar(total_items, desc="Permission fix progress")

        # Process all directories and files
        for root, dirs, files in os.walk(folder):
            try:
                # Fix root directory
                os.chown(root, uid, gid)
                os.chmod(root, DIR_MODE)
                progress.update(1)

                # Fix all directories first
                for dirname in dirs:
                    dir_path = os.path.join(root, dirname)
                    try:
                        os.chown(dir_path, uid, gid)
                        os.chmod(dir_path, DIR_MODE)
                    except Exception as e:
                        print(
                            f"{Colors.RED}Error fixing directory {dir_path}: {str(e)}{Colors.ENDC}"
                        )
                    progress.update(1)

                # Then fix all files
                for filename in files:
                    file_path = os.path.join(root, filename)
                    try:
                        os.chown(file_path, uid, gid)
                        os.chmod(file_path, FILE_MODE)
                    except Exception as e:
                        print(
                            f"{Colors.RED}Error fixing file {file_path}: {str(e)}{Colors.ENDC}"
                        )
                    progress.update(1)

            except Exception as e:
                print(
                    f"{Colors.RED}Error processing directory {root}: {str(e)}{Colors.ENDC}"
                )


def ensure_group_membership() -> None:
    """
    Ensure the SUDO_USER is a member of the libvirt group
    """
    print_header("Ensuring User Group Membership")

    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print(
            f"{Colors.YELLOW}Warning: SUDO_USER not found, skipping group membership check{Colors.ENDC}"
        )
        return

    target_group = "libvirt"

    try:
        # Check if user exists
        user_info = pwd.getpwnam(sudo_user)

        # Get user groups
        user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
        primary_group = grp.getgrgid(user_info.pw_gid).gr_name
        if primary_group not in user_groups:
            user_groups.append(primary_group)

        if target_group in user_groups:
            print(
                f"{Colors.GREEN}User '{sudo_user}' is already in the '{target_group}' group{Colors.ENDC}"
            )
        else:
            print(f"Adding user '{sudo_user}' to the '{target_group}' group...")
            try:
                run_command(["usermod", "-a", "-G", target_group, sudo_user])
                print(f"{Colors.GREEN}Successfully added user to group{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.RED}Failed to add user to group: {str(e)}{Colors.ENDC}")

    except KeyError:
        print(f"{Colors.YELLOW}Warning: User '{sudo_user}' not found{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}Error checking group membership: {str(e)}{Colors.ENDC}")


#####################################
# Main Function
#####################################


def main() -> None:
    """Main execution function"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check root privileges
    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges{Colors.ENDC}"
        )
        sys.exit(1)

    try:
        # 1. Update package lists
        if not update_package_lists():
            print(f"{Colors.RED}Failed to update package lists, aborting{Colors.ENDC}")
            sys.exit(1)

        # 2. Install virtualization packages
        if not install_packages(PACKAGES):
            print(f"{Colors.RED}Failed to install all required packages{Colors.ENDC}")
            sys.exit(1)

        # 3. Configure default network
        if not create_and_start_default_network():
            print(
                f"{Colors.YELLOW}Warning: Failed to fully configure default network{Colors.ENDC}"
            )

        # 4. Enable and start virtualization services
        enable_services(SERVICES)

        # 5. Fix VM folder permissions
        fix_vm_folder_permissions(DEFAULT_VM_FOLDERS)

        # 6. Ensure user is in the libvirt group
        ensure_group_membership()

        # 7. Update VM networks to use default network
        update_vm_networks()

        # 8. Set VMs to autostart at boot
        set_vms_autostart()

        # 9. Start all VMs
        start_all_vms()

        # Done!
        print_header("Virtualization Environment Setup Complete")
        print(
            f"{Colors.GREEN}All virtualization components have been installed and configured successfully.{Colors.ENDC}"
        )
        print(
            f"{Colors.GREEN}Virtual machines are now running and configured to start automatically at boot.{Colors.ENDC}"
        )

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup interrupted by user{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Setup failed: {str(e)}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
