#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup Script
-----------------------------------------------

A comprehensive utility for setting up a complete virtualization environment
on Ubuntu systems with detailed progress tracking and robust error handling.

This script performs the following operations:
  • Installs all required virtualization packages (QEMU/KVM, libvirt, etc.)
  • Configures the default NAT network for VM connectivity
  • Ensures proper permissions on VM storage directories
  • Configures user group membership for libvirt access
  • Updates all existing VMs to use the default network
  • Sets VMs to autostart at system boot
  • Starts all defined virtual machines

Each operation includes real-time progress tracking and comprehensive error
handling with clear, color-coded status updates throughout the process.

Note: This script must be run with root privileges.
"""

import atexit
import logging
import os
import platform
import pwd
import grp
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# Performance settings
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)
OPERATION_TIMEOUT = 600  # seconds

# VM Storage paths
VM_STORAGE_PATHS = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]

# Virtualization package configuration
VIRTUALIZATION_PACKAGES = [
    "qemu-kvm",
    "qemu-utils",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virt-manager",
    "bridge-utils",
    "cpu-checker",
    "ovmf",
    "virtinst",
    "libguestfs-tools",
    "virt-top",
]

# Virtualization services configuration
VIRTUALIZATION_SERVICES = ["libvirtd", "virtlogd"]

# User and permission settings
VM_OWNER = "root"
VM_GROUP = "libvirt-qemu"
VM_DIR_MODE = 0o2770
VM_FILE_MODE = 0o0660
LIBVIRT_USER_GROUP = "libvirt"

# Default network XML configuration
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

# Progress tracking settings
PROGRESS_WIDTH = 50
VM_START_DELAY = 3  # seconds between VM starts

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """Nord-themed ANSI color codes for terminal output"""

    # Nord theme colors
    HEADER = "\033[38;5;81m"  # Nord9 - Blue
    GREEN = "\033[38;5;108m"  # Nord14 - Green
    YELLOW = "\033[38;5;179m"  # Nord13 - Yellow
    RED = "\033[38;5;174m"  # Nord11 - Red
    BLUE = "\033[38;5;67m"  # Nord10 - Deep Blue
    CYAN = "\033[38;5;110m"  # Nord8 - Light Blue
    MAGENTA = "\033[38;5;139m"  # Nord15 - Purple
    WHITE = "\033[38;5;253m"  # Nord4 - Light foreground
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class ProgressBar:
    """Thread-safe progress bar with status display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        """
        Initialize a progress bar.

        Args:
            total: Total number of units to track
            desc: Description to display alongside the progress bar
            width: Width of the progress bar in characters
        """
        self.total = max(1, total)  # Avoid division by zero
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self._display()

    def update(self, amount: int = 1) -> None:
        """
        Update progress safely

        Args:
            amount: Amount to increment progress by
        """
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_time(self, seconds: float) -> str:
        """
        Format seconds to a readable time string

        Args:
            seconds: Number of seconds

        Returns:
            Formatted time string
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes:.0f}m {seconds:.0f}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours:.0f}h {minutes:.0f}m"

    def _display(self) -> None:
        """Display progress bar with completion percentage and ETA"""
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        rate = self.current / max(elapsed, 0.001)
        eta = (self.total - self.current) / max(rate, 0.001)

        sys.stdout.write(
            f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| "
            f"{Colors.WHITE}{percent:>5.1f}%{Colors.ENDC} "
            f"({self.current}/{self.total}) "
            f"[ETA: {self._format_time(eta)}]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            elapsed_str = self._format_time(elapsed)
            sys.stdout.write(
                f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| "
                f"{Colors.GREEN}Complete!{Colors.ENDC} "
                f"(Took: {elapsed_str})\n"
            )
            sys.stdout.flush()


class Spinner:
    """Thread-safe spinner for operations with unknown progress"""

    def __init__(self, message: str):
        """
        Initialize a spinner.

        Args:
            message: Message to display alongside the spinner
        """
        self.message = message
        self.spinning = False
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.thread = None
        self._lock = threading.Lock()
        self.start_time = 0

    def _spin(self) -> None:
        """Animation loop for the spinner"""
        while self.spinning:
            elapsed = time.time() - self.start_time
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            elif minutes > 0:
                time_str = f"{int(minutes)}m {int(seconds)}s"
            else:
                time_str = f"{seconds:.1f}s"

            with self._lock:
                sys.stdout.write(
                    f"\r{Colors.BLUE}{self.spinner_chars[self.current]}{Colors.ENDC} "
                    f"{Colors.CYAN}{self.message}{Colors.ENDC} "
                    f"[{Colors.DIM}elapsed: {time_str}{Colors.ENDC}]"
                )
                sys.stdout.flush()
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation"""
        with self._lock:
            if not self.spinning:
                self.spinning = True
                self.start_time = time.time()
                self.thread = threading.Thread(target=self._spin)
                self.thread.daemon = True
                self.thread.start()

    def stop(self, success: bool = True) -> None:
        """
        Stop the spinner animation

        Args:
            success: Whether the operation was successful
        """
        with self._lock:
            if self.spinning:
                self.spinning = False
                if self.thread:
                    self.thread.join()

                # Calculate elapsed time
                elapsed = time.time() - self.start_time
                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours > 0:
                    time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                elif minutes > 0:
                    time_str = f"{int(minutes)}m {int(seconds)}s"
                else:
                    time_str = f"{seconds:.1f}s"

                # Clear the line
                sys.stdout.write("\r" + " " * 80 + "\r")

                # Print completion message
                if success:
                    sys.stdout.write(
                        f"{Colors.GREEN}✓{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} "
                        f"{Colors.GREEN}completed{Colors.ENDC} in {time_str}\n"
                    )
                else:
                    sys.stdout.write(
                        f"{Colors.RED}✗{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} "
                        f"{Colors.RED}failed{Colors.ENDC} after {time_str}\n"
                    )
                sys.stdout.flush()

    def __enter__(self):
        """Start the spinner when used as a context manager"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the spinner when exiting context manager"""
        self.stop(exc_type is None)


#####################################
# Helper Functions
#####################################


def print_header(message: str) -> None:
    """
    Print formatted header

    Args:
        message: Header message
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """
    Print formatted section header

    Args:
        message: Section header message
    """
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def print_step(message: str) -> None:
    """
    Print step message

    Args:
        message: Step message
    """
    print(f"{Colors.CYAN}• {message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """
    Print success message

    Args:
        message: Success message
    """
    print(f"{Colors.GREEN}✓ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """
    Print warning message

    Args:
        message: Warning message
    """
    print(f"{Colors.YELLOW}⚠ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """
    Print error message

    Args:
        message: Error message
    """
    print(f"{Colors.RED}✗ {message}{Colors.ENDC}")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """
    Run command with error handling

    Args:
        cmd: Command to execute as list of strings
        env: Environment variables dictionary
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with execution results
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stdout") and e.stdout:
            print(f"{Colors.DIM}Stdout: {e.stdout.strip()}{Colors.ENDC}")
        if hasattr(e, "stderr") and e.stderr:
            print(f"{Colors.RED}Stderr: {e.stderr.strip()}{Colors.ENDC}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}")
        print_error(f"Details: {str(e)}")
        raise


def run_command_with_spinner(
    cmd: List[str], desc: str, check: bool = True, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, subprocess.CompletedProcess]:
    """
    Run a command with a spinner animation

    Args:
        cmd: Command to execute
        desc: Description for the spinner
        check: Whether to raise an exception on failure
        env: Environment variables to set

    Returns:
        Tuple of (success, result)
    """
    with Spinner(desc) as spinner:
        try:
            result = run_command(cmd, env=env, check=check)
            return True, result
        except Exception as e:
            if check:
                spinner.stop(False)
                print_error(f"Command failed: {e}")
            return False, None


def signal_handler(sig, frame) -> None:
    """
    Handle interrupt signals gracefully

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print(
        f"\n{Colors.YELLOW}Process interrupted by {sig_name}. Cleaning up...{Colors.ENDC}"
    )
    cleanup()
    sys.exit(128 + sig)


def cleanup() -> None:
    """Perform cleanup tasks before exit"""
    # Add any specific cleanup tasks here
    print_step("Performing cleanup tasks...")


def get_system_info() -> Dict[str, str]:
    """
    Get system information for reporting

    Returns:
        Dictionary of system information
    """
    info = {
        "hostname": HOSTNAME,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "kernel": platform.release(),
        "cpu_count": str(os.cpu_count() or 0),
        "user": os.environ.get("USER", "unknown"),
    }

    # Check if KVM is available
    try:
        kvm_result = run_command(["kvm-ok"], check=False)
        if kvm_result.returncode == 0:
            info["kvm_status"] = "Supported"
        else:
            info["kvm_status"] = "Not supported"
    except Exception:
        info["kvm_status"] = "Unknown"

    return info


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """
    Check if script is run with root privileges

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_step("Try running with: sudo python3 virt_setup.py")
        return False
    return True


def check_virtualization_support() -> bool:
    """
    Check if hardware virtualization is supported

    Returns:
        True if virtualization is supported, False otherwise
    """
    print_section("Checking Virtualization Support")

    try:
        # Check CPU flags
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()

        # Check for virtualization flags
        has_vmx = "vmx" in cpuinfo  # Intel
        has_svm = "svm" in cpuinfo  # AMD

        if has_vmx:
            print_success("Intel VT-x virtualization support detected")
        elif has_svm:
            print_success("AMD-V virtualization support detected")
        else:
            print_warning("CPU virtualization extensions not found")
            print_step("This system may not support hardware virtualization")
            return False

        # Check if KVM modules are loaded
        lsmod_result = run_command(["lsmod"], capture_output=True)
        has_kvm = "kvm" in lsmod_result.stdout

        if has_kvm:
            print_success("KVM kernel modules are loaded")
        else:
            print_warning("KVM kernel modules not detected")
            print_step("Modules will be loaded after installing KVM packages")

        return True

    except Exception as e:
        print_error(f"Error checking virtualization support: {e}")
        return False


#####################################
# Package and Service Management
#####################################


def update_system_packages() -> bool:
    """
    Update apt package lists

    Returns:
        True if successful, False otherwise
    """
    print_section("Updating System Package Lists")

    try:
        with Spinner("Updating package lists") as spinner:
            result = run_command(["apt-get", "update"], check=True)

        print_success("Package lists updated successfully")
        return True

    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False


def install_virtualization_packages(packages: List[str]) -> bool:
    """
    Install required virtualization packages

    Args:
        packages: List of packages to install

    Returns:
        True if successful, False otherwise
    """
    print_section("Installing Virtualization Packages")

    if not packages:
        print_warning("No packages specified")
        return True

    # Count total packages
    total_packages = len(packages)
    print_step(f"Installing {total_packages} packages: {', '.join(packages)}")

    # Create progress bar
    progress = ProgressBar(total_packages, "Installation progress")

    # Install each package individually to track progress
    failed_packages = []

    for i, package in enumerate(packages):
        try:
            print(f"\nInstalling package ({i + 1}/{total_packages}): {package}")

            # Install the package
            process = subprocess.Popen(
                ["apt-get", "install", "-y", package],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Process output line by line
            for line in iter(process.stdout.readline, ""):
                # Print important output lines
                if "Unpacking" in line or "Setting up" in line:
                    print(f"  {line.strip()}")

            # Wait for completion
            process.wait()

            # Check result
            if process.returncode != 0:
                print_error(f"Failed to install {package}")
                failed_packages.append(package)
            else:
                print_success(f"Package {package} installed successfully")

            # Update progress
            progress.update(1)

        except Exception as e:
            print_error(f"Error installing {package}: {e}")
            failed_packages.append(package)
            progress.update(1)

    # Report results
    if failed_packages:
        print_warning(
            f"Failed to install {len(failed_packages)} packages: {', '.join(failed_packages)}"
        )
        return False
    else:
        print_success("All virtualization packages installed successfully")
        return True


def manage_virtualization_services(services: List[str]) -> bool:
    """
    Enable and start virtualization services

    Args:
        services: List of service names

    Returns:
        True if successful, False otherwise
    """
    print_section("Managing Virtualization Services")

    if not services:
        print_warning("No services specified")
        return True

    print_step(f"Enabling and starting {len(services)} services: {', '.join(services)}")

    # Create progress bar
    progress = ProgressBar(
        len(services) * 2, "Service management"
    )  # *2 for enable and start actions

    # Track failures
    failed_services = []

    for service in services:
        # Enable service
        try:
            print(f"Enabling service: {service}")
            run_command(["systemctl", "enable", service])
            print_success(f"Service {service} enabled")
            progress.update(1)
        except Exception as e:
            print_error(f"Failed to enable {service}: {e}")
            failed_services.append(f"{service} (enable)")
            progress.update(1)

        # Start service
        try:
            print(f"Starting service: {service}")
            run_command(["systemctl", "start", service])
            print_success(f"Service {service} started")
            progress.update(1)
        except Exception as e:
            print_error(f"Failed to start {service}: {e}")
            failed_services.append(f"{service} (start)")
            progress.update(1)

    # Check service status
    print_step("Verifying service status:")
    for service in services:
        try:
            result = run_command(["systemctl", "is-active", service], check=False)
            status = result.stdout.strip()

            if status == "active":
                print_success(f"Service {service} is active")
            else:
                print_warning(f"Service {service} status: {status}")

        except Exception as e:
            print_error(f"Error checking {service} status: {e}")

    if failed_services:
        print_warning(f"Issues with services: {', '.join(failed_services)}")
        return False
    else:
        print_success("All services enabled and started successfully")
        return True


#####################################
# Network Configuration
#####################################


def configure_default_network() -> bool:
    """
    Configure the default NAT network for virtual machines

    Returns:
        True if successful, False otherwise
    """
    print_section("Configuring Default Network")

    try:
        # Check if default network already exists
        net_list_result = run_command(
            ["virsh", "net-list", "--all"], capture_output=True
        )

        if "default" in net_list_result.stdout:
            print_step("Default network already exists")

            # Check if default network is active
            net_active = (
                "active" in net_list_result.stdout
                and "default" in net_list_result.stdout
            )

            if not net_active:
                print_step("Starting default network")
                try:
                    run_command(["virsh", "net-start", "default"])
                    print_success("Default network started")
                except Exception as e:
                    print_error(f"Failed to start default network: {e}")
                    return False

        else:
            print_step("Creating default network from template")

            # Create temporary XML file
            net_xml_path = "/tmp/default_network.xml"
            with open(net_xml_path, "w") as f:
                f.write(DEFAULT_NETWORK_XML)

            # Define network from XML
            try:
                run_command(["virsh", "net-define", net_xml_path])
                print_success("Default network defined")
            except Exception as e:
                print_error(f"Failed to define default network: {e}")
                return False

            # Start the network
            try:
                run_command(["virsh", "net-start", "default"])
                print_success("Default network started")
            except Exception as e:
                print_error(f"Failed to start default network: {e}")
                return False

        # Set network to autostart
        try:
            run_command(["virsh", "net-autostart", "default"])
            print_success("Default network set to autostart")
        except Exception as e:
            print_warning(f"Failed to set default network to autostart: {e}")

        # Verify network configuration
        try:
            net_info = run_command(
                ["virsh", "net-info", "default"], capture_output=True
            )
            print_step("Default network configuration:")

            for line in net_info.stdout.splitlines():
                if line.strip():
                    print(f"  {line.strip()}")

        except Exception as e:
            print_warning(f"Failed to get network info: {e}")

        return True

    except Exception as e:
        print_error(f"Error configuring default network: {e}")
        return False


#####################################
# VM Management Functions
#####################################


def get_virtual_machines() -> List[Dict[str, str]]:
    """
    Get list of all virtual machines

    Returns:
        List of VMs with their details
    """
    vms = []

    try:
        # Get all VMs
        result = run_command(["virsh", "list", "--all"], capture_output=True)

        # Parse output
        lines = result.stdout.strip().splitlines()

        # Find header/separator line
        sep_index = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("----"):
                sep_index = i
                break

        if sep_index < 0:
            return []

        # Parse VM data
        for i in range(sep_index + 1, len(lines)):
            line = lines[i].strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) >= 3:
                vm_id = parts[0]
                vm_name = parts[1]
                vm_state = " ".join(parts[2:])

                vms.append({"id": vm_id, "name": vm_name, "state": vm_state})

        return vms

    except Exception as e:
        print_error(f"Error retrieving virtual machine list: {e}")
        return []


def set_vm_autostart(vms: List[Dict[str, str]]) -> bool:
    """
    Configure VMs to autostart at boot

    Args:
        vms: List of VM information dictionaries

    Returns:
        True if successful, False otherwise
    """
    print_section("Configuring VM Autostart")

    if not vms:
        print_warning("No virtual machines found")
        return True

    # Create progress bar
    progress = ProgressBar(len(vms), "VM autostart configuration")

    # Track results
    success_count = 0
    failed_vms = []

    for vm in vms:
        vm_name = vm["name"]
        try:
            print_step(f"Setting VM '{vm_name}' to autostart")

            # Check current autostart setting
            info_result = run_command(
                ["virsh", "dominfo", vm_name], capture_output=True
            )
            current_autostart = "Autostart:        yes" in info_result.stdout

            if current_autostart:
                print_success(f"VM '{vm_name}' already set to autostart")
            else:
                # Enable autostart
                run_command(["virsh", "autostart", vm_name])
                print_success(f"VM '{vm_name}' set to autostart")

            success_count += 1

        except Exception as e:
            print_error(f"Failed to set autostart for VM '{vm_name}': {e}")
            failed_vms.append(vm_name)

        progress.update(1)

    # Report results
    if failed_vms:
        print_warning(
            f"Failed to set autostart for {len(failed_vms)} VMs: {', '.join(failed_vms)}"
        )
        return False
    else:
        print_success(f"Successfully configured autostart for all {len(vms)} VMs")
        return True


def update_vm_networks(vms: List[Dict[str, str]]) -> bool:
    """
    Update VMs to use the default network

    Args:
        vms: List of VM information dictionaries

    Returns:
        True if successful, False otherwise
    """
    print_section("Updating VM Network Configuration")

    if not vms:
        print_warning("No virtual machines found")
        return True

    # Create progress bar
    progress = ProgressBar(len(vms), "VM network update")

    # Track results
    success_count = 0
    skipped_count = 0
    failed_vms = []

    for vm in vms:
        vm_name = vm["name"]
        try:
            print_step(f"Checking network configuration for VM '{vm_name}'")

            # Get VM XML
            xml_result = run_command(["virsh", "dumpxml", vm_name], capture_output=True)
            root = ET.fromstring(xml_result.stdout)

            # Find network interfaces
            interfaces = root.findall(".//interface[@type='network']")

            if not interfaces:
                print_warning(f"VM '{vm_name}' has no network interfaces")
                skipped_count += 1
                progress.update(1)
                continue

            # Check if already using default network
            using_default = False
            for interface in interfaces:
                source = interface.find("source")
                if source is not None and source.get("network") == "default":
                    using_default = True
                    break

            if using_default:
                print_success(f"VM '{vm_name}' already using default network")
                success_count += 1
                progress.update(1)
                continue

            # Update network configuration
            print_step(f"Updating network for VM '{vm_name}'")

            # Determine if VM is running
            is_running = vm["state"].lower() == "running"

            for interface in interfaces:
                # Get MAC address for identification
                mac_elem = interface.find("mac")
                if mac_elem is None:
                    continue

                mac = mac_elem.get("address")
                source = interface.find("source")
                if source is None or source.get("network") == "default":
                    continue

                # Detach the interface
                print_step(f"Detaching interface with MAC {mac}")
                detach_cmd = [
                    "virsh",
                    "detach-interface",
                    vm_name,
                    "network",
                    "--mac",
                    mac,
                    "--config",
                ]

                if is_running:
                    detach_cmd.append("--live")

                run_command(detach_cmd)

                # Attach new interface to default network
                print_step("Attaching new interface to default network")
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

                if is_running:
                    attach_cmd.append("--live")

                run_command(attach_cmd)

                print_success(f"Successfully updated network for VM '{vm_name}'")
                success_count += 1

        except Exception as e:
            print_error(f"Failed to update network for VM '{vm_name}': {e}")
            failed_vms.append(vm_name)

        progress.update(1)

    # Report results
    if failed_vms:
        print_warning(
            f"Failed to update network for {len(failed_vms)} VMs: {', '.join(failed_vms)}"
        )
        print_step(
            f"Successfully updated: {success_count}, Skipped: {skipped_count}, Failed: {len(failed_vms)}"
        )
        return False
    else:
        print_success(
            f"Successfully updated network for {success_count} VMs (Skipped: {skipped_count})"
        )
        return True


def start_virtual_machines(vms: List[Dict[str, str]]) -> bool:
    """
    Start all virtual machines

    Args:
        vms: List of VM information dictionaries

    Returns:
        True if successful, False otherwise
    """
    print_section("Starting Virtual Machines")

    if not vms:
        print_warning("No virtual machines found")
        return True

    # Filter out already running VMs
    vms_to_start = [vm for vm in vms if vm["state"].lower() != "running"]

    if not vms_to_start:
        print_success("All VMs are already running")
        return True

    # Create progress bar
    progress = ProgressBar(len(vms_to_start), "VM startup")

    # Track results
    success_count = 0
    failed_vms = []

    for vm in vms_to_start:
        vm_name = vm["name"]
        try:
            print_step(f"Starting VM '{vm_name}'")

            # Start the VM
            with Spinner(f"Starting VM '{vm_name}'") as spinner:
                run_command(["virsh", "start", vm_name])

            print_success(f"VM '{vm_name}' started successfully")
            success_count += 1

            # Add delay between VM starts to avoid overloading the system
            if VM_START_DELAY > 0:
                time.sleep(VM_START_DELAY)

        except Exception as e:
            print_error(f"Failed to start VM '{vm_name}': {e}")
            failed_vms.append(vm_name)

        progress.update(1)

    # Report results
    if failed_vms:
        print_warning(f"Failed to start {len(failed_vms)} VMs: {', '.join(failed_vms)}")
        return False
    else:
        print_success(f"Successfully started all {len(vms_to_start)} VMs")
        return True


#####################################
# Permission and User Management
#####################################


def fix_storage_permissions(storage_paths: List[str]) -> bool:
    """
    Fix permissions on VM storage directories

    Args:
        storage_paths: List of storage directory paths

    Returns:
        True if successful, False otherwise
    """
    print_section("Fixing VM Storage Permissions")

    if not storage_paths:
        print_warning("No storage paths specified")
        return True

    # Try to get user and group IDs
    try:
        uid = pwd.getpwnam(VM_OWNER).pw_uid
        gid = grp.getgrnam(VM_GROUP).gr_gid
    except KeyError as e:
        print_error(f"User or group not found: {e}")
        return False

    # Process each storage path
    for path in storage_paths:
        print_step(f"Processing storage path: {path}")

        # Check if path exists
        if not os.path.exists(path):
            print_warning(f"Path '{path}' does not exist, creating it")
            try:
                os.makedirs(path, mode=VM_DIR_MODE, exist_ok=True)
            except Exception as e:
                print_error(f"Failed to create directory '{path}': {e}")
                continue

        # Count items for progress bar
        total_items = 0
        for root, dirs, files in os.walk(path):
            total_items += 1  # Count the directory itself
            total_items += len(dirs)
            total_items += len(files)

        print_step(f"Found {total_items} items to process")

        # Create progress bar
        progress = ProgressBar(total_items, "Permission updates")

        # Fix permissions
        try:
            # First fix the root directory
            print_step(f"Setting owner and permissions on {path}")
            os.chown(path, uid, gid)
            os.chmod(path, VM_DIR_MODE)
            progress.update(1)

            # Now recursively process subdirectories and files
            for root, dirs, files in os.walk(path):
                # Fix directory permissions
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        os.chown(dir_path, uid, gid)
                        os.chmod(dir_path, VM_DIR_MODE)
                    except Exception as e:
                        print_warning(f"Failed to set permissions on {dir_path}: {e}")
                    progress.update(1)

                # Fix file permissions
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        os.chown(file_path, uid, gid)
                        os.chmod(file_path, VM_FILE_MODE)
                    except Exception as e:
                        print_warning(f"Failed to set permissions on {file_path}: {e}")
                    progress.update(1)

        except Exception as e:
            print_error(f"Failed to set permissions on {path}: {e}")
            return False

    print_success("Storage permissions updated successfully")
    return True


def configure_user_groups() -> bool:
    """
    Add current user to required groups

    Returns:
        True if successful, False otherwise
    """
    print_section("Configuring User Group Membership")

    # Get sudo user
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print_warning("SUDO_USER environment variable not found")
        print_step("Skipping user group configuration")
        return True

    print_step(f"Configuring group membership for user '{sudo_user}'")

    # Check if user exists
    try:
        pwd.getpwnam(sudo_user)
    except KeyError:
        print_error(f"User '{sudo_user}' not found")
        return False

    # Check if group exists
    try:
        grp.getgrnam(LIBVIRT_USER_GROUP)
    except KeyError:
        print_error(f"Group '{LIBVIRT_USER_GROUP}' not found")
        return False

    # Check if user is already in the group
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary_gid = pwd.getpwnam(sudo_user).pw_gid
    primary_group = grp.getgrgid(primary_gid).gr_name

    if primary_group not in user_groups:
        user_groups.append(primary_group)

    if LIBVIRT_USER_GROUP in user_groups:
        print_success(
            f"User '{sudo_user}' is already in the '{LIBVIRT_USER_GROUP}' group"
        )
        return True

    # Add user to group
    try:
        print_step(f"Adding user '{sudo_user}' to group '{LIBVIRT_USER_GROUP}'")
        run_command(["usermod", "-a", "-G", LIBVIRT_USER_GROUP, sudo_user])
        print_success(f"User '{sudo_user}' added to group '{LIBVIRT_USER_GROUP}'")
        print_step(
            "You will need to log out and log back in for the group changes to take effect"
        )
        return True
    except Exception as e:
        print_error(f"Failed to add user to group: {e}")
        return False


#####################################
# Main Function
#####################################


def verify_virtualization_setup() -> bool:
    """
    Verify the virtualization setup is working

    Returns:
        True if verification passes, False otherwise
    """
    print_section("Verifying Virtualization Setup")

    verification_results = {}

    # Check libvirtd service
    try:
        service_result = run_command(
            ["systemctl", "is-active", "libvirtd"], check=False
        )
        is_active = service_result.stdout.strip() == "active"
        verification_results["libvirtd_service"] = is_active

        if is_active:
            print_success("libvirtd service is active")
        else:
            print_error(
                f"libvirtd service is not active: {service_result.stdout.strip()}"
            )
    except Exception as e:
        print_error(f"Failed to check libvirtd service: {e}")
        verification_results["libvirtd_service"] = False

    # Check default network
    try:
        net_result = run_command(
            ["virsh", "net-list"], check=False, capture_output=True
        )
        has_default = "default" in net_result.stdout and "active" in net_result.stdout
        verification_results["default_network"] = has_default

        if has_default:
            print_success("Default network is active")
        else:
            print_error("Default network is not active")
    except Exception as e:
        print_error(f"Failed to check default network: {e}")
        verification_results["default_network"] = False

    # Check KVM modules
    try:
        lsmod_result = run_command(["lsmod"], capture_output=True)
        has_kvm = "kvm" in lsmod_result.stdout
        verification_results["kvm_modules"] = has_kvm

        if has_kvm:
            print_success("KVM kernel modules are loaded")
        else:
            print_error("KVM kernel modules are not loaded")
    except Exception as e:
        print_error(f"Failed to check KVM modules: {e}")
        verification_results["kvm_modules"] = False

    # Check VM storage directories
    for path in VM_STORAGE_PATHS:
        key = f"storage_{path.replace('/', '_')}"
        if os.path.exists(path):
            print_success(f"Storage path exists: {path}")
            verification_results[key] = True
        else:
            print_error(f"Storage path does not exist: {path}")
            verification_results[key] = False

    # Calculate overall result
    all_passed = all(verification_results.values())
    if all_passed:
        print_success("All verification checks passed!")
    else:
        print_warning(
            "Some verification checks failed. Review the output above for details."
        )

    return all_passed


def main() -> None:
    """Main execution function"""
    # Register signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    # Setup header
    print_header("Enhanced Virtualization Environment Setup")

    # Display system information
    system_info = get_system_info()
    print_section("System Information")
    for key, value in system_info.items():
        print(f"  {key.replace('_', ' ').title()}: {value}")

    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check requirements
    if not check_root_privileges():
        sys.exit(1)

    # Check hardware virtualization support
    if not check_virtualization_support():
        print_warning(
            "Hardware virtualization may not be fully supported on this system"
        )
        print_step("Continuing with setup, but performance may be affected")

    # Update system package lists
    if not update_system_packages():
        print_warning("Failed to update package lists")
        print_step("Continuing with installation, but some packages may be outdated")

    # Install virtualization packages
    if not install_virtualization_packages(VIRTUALIZATION_PACKAGES):
        print_error("Failed to install all virtualization packages")
        print_step("Continuing with setup, but some functionality may be limited")

    # Configure virtualization services
    if not manage_virtualization_services(VIRTUALIZATION_SERVICES):
        print_warning("Some services could not be started")
        print_step("This may affect virtualization functionality")

    # Configure default network
    if not configure_default_network():
        print_error("Failed to configure default network")
        print_step("VMs may not have network connectivity")

    # Fix storage permissions
    if not fix_storage_permissions(VM_STORAGE_PATHS):
        print_warning("Failed to set all storage permissions")
        print_step("You may encounter permission issues with VM storage")

    # Configure user groups
    if not configure_user_groups():
        print_warning("Failed to configure user group membership")
        print_step("You may need to manually add your user to the libvirt group")

    # Get list of virtual machines
    print_step("Retrieving list of virtual machines")
    vms = get_virtual_machines()

    if vms:
        print_success(f"Found {len(vms)} virtual machines")

        # Update VM network configuration
        update_vm_networks(vms)

        # Configure VM autostart
        set_vm_autostart(vms)

        # Start VMs
        start_virtual_machines(vms)
    else:
        print_step("No existing virtual machines found")

    # Verify setup
    verify_virtualization_setup()

    # Display completion message
    print_header("Virtualization Environment Setup Complete")
    print_success("Virtualization environment has been set up successfully!")
    print()
    print_step("Next steps:")
    print("  1. Log out and log back in for group changes to take effect")
    print("  2. Run 'virt-manager' to create and manage virtual machines")
    print("  3. For issues, check system logs with 'journalctl -u libvirtd'")
    print()
    print(f"Setup completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup interrupted by user.{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Unhandled error during setup: {e}{Colors.ENDC}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
