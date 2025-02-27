#!/usr/bin/env python3
"""
Install Virtualization Packages, Enable Auto-Start for Virtual Networks and Services,
and Reconfigure Virtual Machines to Use the 'default' NAT Network on Ubuntu

This script installs common virtualization packages (QEMU/KVM, libvirt, etc.),
updates package lists, and then configures the system so that:
  • The default virtual network is created (if not already defined), started, and set to autostart.
  • All defined virtual machines are updated to use the "default" NAT network.
  • Key virtualization services (libvirtd and virtlogd) are enabled and started.
It uses only the standard library, provides clear, color-coded output, and handles interrupts gracefully.

Note: Run this script with root privileges.
"""

import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import List


# ANSI color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


# List of virtualization packages to install
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

# List of virtualization-related services to enable and start
SERVICES: List[str] = [
    "libvirtd",
    "virtlogd",
]

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


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully."""
    print(f"\n{Colors.YELLOW}Installation interrupted. Exiting...{Colors.ENDC}")
    sys.exit(1)


def run_command(cmd: List[str]) -> bool:
    """
    Run a command and stream its output.

    Args:
        cmd: A list of command arguments.

    Returns:
        True if the command succeeds, False otherwise.
    """
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        while True:
            line = process.stdout.readline()
            if not line:
                break
            sys.stdout.write(line)
        process.wait()
        if process.returncode != 0:
            print(
                f"{Colors.RED}Command {' '.join(cmd)} failed with exit code {process.returncode}.{Colors.ENDC}"
            )
            return False
        return True
    except Exception as e:
        print(f"{Colors.RED}Error running command {' '.join(cmd)}: {e}{Colors.ENDC}")
        return False


def print_header(message: str) -> None:
    """Print a formatted header message."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}")
    print(message.center(60))
    print(f"{'=' * 60}{Colors.ENDC}\n")


def install_packages(packages: List[str]) -> None:
    """Install each package one by one."""
    for idx, pkg in enumerate(packages, start=1):
        print_header(f"Installing package {idx}/{len(packages)}: {pkg}")
        if not run_command(["apt-get", "install", "-y", pkg]):
            print(
                f"{Colors.RED}Failed to install {pkg}. Aborting installation.{Colors.ENDC}"
            )
            sys.exit(1)
        else:
            print(f"{Colors.GREEN}Successfully installed {pkg}.{Colors.ENDC}")
        time.sleep(1)


def create_and_enable_default_network() -> None:
    """
    Create (if necessary) and enable the default virtual network.

    This function checks if a 'default' network exists. If not, it writes the network XML
    to a temporary file, defines it, and then starts it. It then checks if the autostart symlink
    exists before setting the network to autostart.
    """
    print_header("Configuring default virtual network")
    try:
        result = subprocess.run(
            ["virsh", "net-list", "--all"], capture_output=True, text=True, check=True
        )
        if "default" in result.stdout:
            # Attempt to start the default network
            if run_command(["virsh", "net-start", "default"]):
                print(
                    f"{Colors.GREEN}Default network started successfully.{Colors.ENDC}"
                )
            else:
                print(
                    f"{Colors.YELLOW}Default network may already be running or failed to start.{Colors.ENDC}"
                )
            # Check if the autostart symlink exists
            autostart_path = "/etc/libvirt/qemu/networks/autostart/default.xml"
            if os.path.exists(autostart_path):
                print(
                    f"{Colors.GREEN}Default network is already set to autostart.{Colors.ENDC}"
                )
            else:
                if run_command(["virsh", "net-autostart", "default"]):
                    print(
                        f"{Colors.GREEN}Default network set to autostart successfully.{Colors.ENDC}"
                    )
                else:
                    print(
                        f"{Colors.YELLOW}Failed to set default network to autostart. It may already be enabled.{Colors.ENDC}"
                    )
        else:
            # Create and define the default network
            temp_xml = "/tmp/default_network.xml"
            with open(temp_xml, "w") as f:
                f.write(DEFAULT_NETWORK_XML)
            os.chmod(temp_xml, 0o644)
            if run_command(["virsh", "net-define", temp_xml]):
                print(
                    f"{Colors.GREEN}Default network defined successfully.{Colors.ENDC}"
                )
            else:
                print(f"{Colors.RED}Failed to define default network.{Colors.ENDC}")
                return
            if run_command(["virsh", "net-start", "default"]):
                print(
                    f"{Colors.GREEN}Default network started successfully.{Colors.ENDC}"
                )
            else:
                print(f"{Colors.RED}Failed to start default network.{Colors.ENDC}")
            if run_command(["virsh", "net-autostart", "default"]):
                print(
                    f"{Colors.GREEN}Default network set to autostart successfully.{Colors.ENDC}"
                )
            else:
                print(
                    f"{Colors.YELLOW}Failed to set default network to autostart.{Colors.ENDC}"
                )
    except Exception as e:
        print(f"{Colors.RED}Error checking default network: {e}{Colors.ENDC}")


def ensure_network_commands() -> None:
    """
    Explicitly run 'virsh net-start default' and 'virsh net-autostart default'
    to ensure the default network is active and set to autostart.
    """
    print_header("Ensuring default network is active")
    if run_command(["virsh", "net-start", "default"]):
        print(f"{Colors.GREEN}Default network started.{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}Default network may already be active.{Colors.ENDC}")
    if run_command(["virsh", "net-autostart", "default"]):
        print(f"{Colors.GREEN}Default network set to autostart.{Colors.ENDC}")
    else:
        print(
            f"{Colors.YELLOW}Default network autostart configuration might already exist.{Colors.ENDC}"
        )


def get_vm_list() -> List[dict]:
    """
    Retrieve a list of virtual machines using 'virsh list --all'.

    Returns:
        A list of dictionaries containing 'id', 'name', and 'state' for each VM.
    """
    vms = []
    try:
        result = subprocess.run(
            ["virsh", "list", "--all"], capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().splitlines()
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
    except Exception as e:
        print(f"{Colors.RED}Error retrieving VM list: {e}{Colors.ENDC}")
    return vms


def update_vm_networks() -> None:
    """
    Update all virtual machines to use the 'default' NAT network.

    For each VM, this function retrieves its XML definition and looks for any interface
    of type "network" that is not using the 'default' network. For each such interface,
    it detaches it (using its MAC address) and attaches a new interface on the 'default'
    network using a virtio model.
    """
    print_header("Updating Virtual Machines to Use 'default' NAT Network")
    vms = get_vm_list()
    if not vms:
        print(f"{Colors.YELLOW}No virtual machines found to update.{Colors.ENDC}")
        return
    for vm in vms:
        vm_name = vm["name"]
        print(f"{Colors.BOLD}Processing VM: {vm_name}{Colors.ENDC}")
        try:
            result = subprocess.run(
                ["virsh", "dumpxml", vm_name],
                capture_output=True,
                text=True,
                check=True,
            )
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
                            detach_cmd = [
                                "virsh",
                                "detach-interface",
                                vm_name,
                                "network",
                                "--mac",
                                mac,
                                "--config",
                                "--live",
                            ]
                            if run_command(detach_cmd):
                                print(
                                    f"{Colors.YELLOW}Detached interface with MAC {mac} from VM {vm_name}.{Colors.ENDC}"
                                )
                                modified = True
                            else:
                                print(
                                    f"{Colors.RED}Failed to detach interface with MAC {mac} from VM {vm_name}.{Colors.ENDC}"
                                )
            if modified:
                attach_cmd = [
                    "virsh",
                    "attach-interface",
                    vm_name,
                    "network",
                    "default",
                    "--model",
                    "virtio",
                    "--config",
                    "--live",
                ]
                if run_command(attach_cmd):
                    print(
                        f"{Colors.GREEN}Attached new 'default' network interface to VM {vm_name}.{Colors.ENDC}"
                    )
                else:
                    print(
                        f"{Colors.RED}Failed to attach new network interface to VM {vm_name}.{Colors.ENDC}"
                    )
            else:
                print(
                    f"{Colors.GREEN}VM {vm_name} is already using the 'default' network.{Colors.ENDC}"
                )
        except Exception as e:
            print(f"{Colors.RED}Error processing VM {vm_name}: {e}{Colors.ENDC}")
        time.sleep(1)


def enable_virtualization_services(services: List[str]) -> None:
    """
    Enable and start essential virtualization services.

    Args:
        services: A list of service names to enable and start using systemctl.
    """
    print_header("Enabling virtualization services")
    for service in services:
        print(f"{Colors.BOLD}Processing service: {service}{Colors.ENDC}")
        if run_command(["systemctl", "enable", "--now", service]):
            print(
                f"{Colors.GREEN}{service} enabled and started successfully.{Colors.ENDC}"
            )
        else:
            print(
                f"{Colors.YELLOW}Failed to enable/start {service}. Please check the service status manually.{Colors.ENDC}"
            )
        time.sleep(0.5)


def main() -> None:
    """Main execution function."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)

    print_header("Updating package lists")
    if not run_command(["apt-get", "update"]):
        print(f"{Colors.RED}Failed to update package lists. Aborting.{Colors.ENDC}")
        sys.exit(1)

    print_header("Installing virtualization packages")
    install_packages(PACKAGES)

    create_and_enable_default_network()
    # Explicitly ensure that the default network is active
    ensure_network_commands()
    enable_virtualization_services(SERVICES)
    update_vm_networks()

    print_header("Installation Complete")
    print(
        f"{Colors.GREEN}All virtualization packages installed, default network configured, "
        f"VMs updated, and virtualization services enabled successfully.{Colors.ENDC}"
    )


if __name__ == "__main__":
    main()
