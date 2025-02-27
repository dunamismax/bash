#!/usr/bin/env python3
"""
Enhanced VM Manager

A comprehensive virtual machine management utility with robust error handling,
real-time progress tracking, and an elegant Nord-themed interface. This tool
provides a complete solution for managing KVM/libvirt virtual machines on
Linux systems.

Features:
  • List, create, start, stop, and delete virtual machines
  • Create, revert, and manage VM snapshots
  • Detailed VM information display
  • Thread-safe progress tracking with ETA for long operations
  • Comprehensive error handling and resource cleanup
  • Nord-themed color interface with clear visual hierarchy
  • Command-line and interactive modes

Note: This script must be run with root privileges.
"""

import argparse
import fcntl
import logging
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# Directories and Files
LOG_FILE = "/var/log/vm_manager.log"
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"
SNAPSHOT_DIR = "/var/lib/libvirt/snapshots"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Default VM settings
DEFAULT_VCPUS = 2
DEFAULT_RAM_MB = 2048
DEFAULT_DISK_GB = 20
DEFAULT_OS_VARIANT = "ubuntu22.04"

# UI Settings
PROGRESS_WIDTH = 40
SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_DELAY = 0.1

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

#####################################
# Nord Theme Colors
#####################################


class Colors:
    """Nord-themed ANSI color codes for terminal output"""

    # Nord color palette
    POLAR_NIGHT1 = "\033[38;5;59m"  # Nord0 (dark gray)
    POLAR_NIGHT2 = "\033[38;5;60m"  # Nord1
    POLAR_NIGHT3 = "\033[38;5;60m"  # Nord2
    POLAR_NIGHT4 = "\033[38;5;67m"  # Nord3 (lighter gray)

    SNOW_STORM1 = "\033[38;5;188m"  # Nord4 (off white)
    SNOW_STORM2 = "\033[38;5;189m"  # Nord5
    SNOW_STORM3 = "\033[38;5;189m"  # Nord6 (white)

    FROST1 = "\033[38;5;109m"  # Nord7 (frost pale blue)
    FROST2 = "\033[38;5;110m"  # Nord8 (frost cyan)
    FROST3 = "\033[38;5;111m"  # Nord9 (frost light blue)
    FROST4 = "\033[38;5;111m"  # Nord10 (frost deep blue)

    AURORA_RED = "\033[38;5;174m"  # Nord11 (red)
    AURORA_ORANGE = "\033[38;5;175m"  # Nord12 (orange)
    AURORA_YELLOW = "\033[38;5;179m"  # Nord13 (yellow)
    AURORA_GREEN = "\033[38;5;142m"  # Nord14 (green)
    AURORA_PURPLE = "\033[38;5;139m"  # Nord15 (purple)

    # Semantic aliases
    HEADER = FROST3
    SUCCESS = AURORA_GREEN
    WARNING = AURORA_YELLOW
    ERROR = AURORA_RED
    INFO = FROST2
    DETAIL = SNOW_STORM1
    PROMPT = AURORA_PURPLE

    # Text styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"

    # Background colors
    BG_DARK = "\033[48;5;59m"
    BG_BLUE = "\033[48;5;67m"


#####################################
# UI and Progress Tracking Classes
#####################################


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.last_update_time = time.time()
        self.last_update_value = 0
        self.rate = 0  # operations per second

    def update(self, amount: int = 1) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)

            # Calculate rate (operations per second)
            current_time = time.time()
            time_diff = current_time - self.last_update_time

            if time_diff >= 0.5:  # Update rate every half second
                value_diff = self.current - self.last_update_value
                self.rate = value_diff / time_diff if time_diff > 0 else 0
                self.last_update_time = current_time
                self.last_update_value = self.current

            self._display()

    def _format_time(self, seconds: float) -> str:
        """Format seconds to human readable time"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"

    def _display(self) -> None:
        """Display progress bar with rate information"""
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        eta = (self.total - self.current) / self.rate if self.rate > 0 else 0

        # Format progress bar with Nord colors
        progress_text = (
            f"\r{Colors.DETAIL}{self.desc}: "
            f"{Colors.FROST3}|{bar}| "
            f"{Colors.SNOW_STORM1}{percent:>5.1f}% "
            f"({self.current}/{self.total}) "
            f"{Colors.FROST2}[{self.rate:.1f}/s] "
            f"{Colors.FROST1}[ETA: {self._format_time(eta)}]{Colors.ENDC}"
        )

        sys.stdout.write(progress_text)
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


class Spinner:
    """Thread-safe spinner for operations with unknown duration"""

    def __init__(self, desc: str = ""):
        self.desc = desc
        self.active = False
        self.thread = None
        self._lock = threading.Lock()
        self.start_time = 0

    def start(self) -> None:
        """Start the spinner in a separate thread"""
        with self._lock:
            if not self.active:
                self.active = True
                self.start_time = time.time()
                self.thread = threading.Thread(target=self._spin)
                self.thread.daemon = True
                self.thread.start()

    def stop(self) -> None:
        """Stop the spinner"""
        with self._lock:
            if self.active:
                self.active = False
                if self.thread:
                    self.thread.join()
                # Clear the spinner line
                sys.stdout.write("\r" + " " * (len(self.desc) + 20) + "\r")
                sys.stdout.flush()

    def _spin(self) -> None:
        """Spin the spinner"""
        i = 0
        while self.active:
            elapsed = time.time() - self.start_time
            spinner_char = SPINNER_CHARS[i % len(SPINNER_CHARS)]

            # Format elapsed time
            elapsed_str = self._format_time(elapsed)

            sys.stdout.write(
                f"\r{Colors.FROST2}{spinner_char} {Colors.DETAIL}{self.desc} "
                f"{Colors.FROST1}[{elapsed_str}]{Colors.ENDC}"
            )
            sys.stdout.flush()

            time.sleep(SPINNER_DELAY)
            i += 1

    def _format_time(self, seconds: float) -> str:
        """Format seconds to human readable time"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"


#####################################
# Helper Functions
#####################################


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'═' * 80}")
    print(f"{message.center(80)}")
    print(f"{'═' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """Print formatted section header"""
    print(f"\n{Colors.FROST2}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def print_info(message: str) -> None:
    """Print informational message"""
    print(f"{Colors.INFO}{message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print success message"""
    print(f"{Colors.SUCCESS}{message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """Print warning message"""
    print(f"{Colors.WARNING}Warning: {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print error message"""
    print(f"{Colors.ERROR}Error: {message}{Colors.ENDC}")


def run_command(
    command: List[str],
    capture_output: bool = False,
    check: bool = True,
    timeout: int = 60,
) -> Union[str, bool]:
    """
    Execute a shell command with comprehensive error handling

    Args:
        command: Command and arguments as a list
        capture_output: Whether to capture and return command output
        check: Whether to raise an exception on non-zero exit
        timeout: Command timeout in seconds

    Returns:
        Command output if capture_output is True, else True for success
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

        if capture_output:
            return result.stdout
        return True

    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out after {timeout}s: {command_str}")
        print_error(f"Command timed out: {command_str}")
        return False

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Command error: {error_msg}")
        if check:
            print_error(f"Command failed: {command_str}")
            print_error(f"Error details: {error_msg}")
            raise
        return False

    except Exception as e:
        logging.error(f"Error executing command: {str(e)}")
        if check:
            print_error(f"Error executing: {command_str}")
            print_error(f"Details: {str(e)}")
            raise
        return False


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully"""
    print_warning("\nOperation interrupted. Cleaning up...")
    sys.exit(1)


def setup_logging() -> None:
    """Set up logging with both console output and file rotation"""
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Create a nice formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file handler (5 MB per file, 3 backups)
    try:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except (PermissionError, IOError) as e:
        print_warning(f"Could not set up log file: {e}")
        print_info(f"Continuing with console logging only")


#####################################
# Validation Functions
#####################################


def check_root() -> bool:
    """Ensure the script is run with root privileges"""
    if os.geteuid() != 0:
        print_error("This script requires root privileges")
        print_info("Please run with sudo or as root user")
        return False
    return True


def check_dependencies() -> bool:
    """Ensure required commands exist and that libvirt is active"""
    required_commands = ["virsh", "virt-install", "qemu-img"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]

    if missing:
        print_error(f"Missing dependencies: {', '.join(missing)}")
        print_info(
            "Please install them with: sudo apt install libvirt-bin virtinst qemu-utils"
        )
        return False

    # Check libvirtd service status
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "libvirtd"], check=True)
    except subprocess.CalledProcessError:
        print_warning("libvirtd service is not active")

        # Try to start the service
        print_info("Attempting to start libvirtd service...")
        try:
            run_command(["systemctl", "start", "libvirtd"], check=False)

            # Verify it started
            try:
                subprocess.run(
                    ["systemctl", "is-active", "--quiet", "libvirtd"], check=True
                )
                print_success("Successfully started libvirtd service")
            except subprocess.CalledProcessError:
                print_error("Failed to start libvirtd service")
                print_info("Please start it manually: sudo systemctl start libvirtd")
                return False

        except Exception as e:
            print_error(f"Failed to start libvirtd service: {e}")
            print_info("Please start it manually: sudo systemctl start libvirtd")
            return False

    return True


def ensure_default_network() -> bool:
    """
    Ensure the 'default' virtual network is active
    Create and define the network if it does not exist
    """
    spinner = Spinner("Checking network status")
    spinner.start()

    try:
        output = run_command(["virsh", "net-list", "--all"], capture_output=True)

        if "default" in output:
            if "active" in output:
                spinner.stop()
                print_success("Default network is already active")
                return True
            else:
                # Network exists but is inactive
                spinner.stop()
                print_info("Default network exists but is inactive")
                print_info("Starting default network...")

                run_command(["virsh", "net-start", "default"])
                run_command(["virsh", "net-autostart", "default"])

                print_success("Default network started and set to autostart")
                return True
        else:
            # Network doesn't exist, create it
            spinner.stop()
            print_info("Default network does not exist")
            print_info("Creating default network...")

            # Write the default network XML to a temporary file
            fd, xml_path = tempfile.mkstemp(suffix=".xml")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(DEFAULT_NETWORK_XML)

                # Set proper permissions
                os.chmod(xml_path, 0o644)

                # Define, start, and autostart the network
                run_command(["virsh", "net-define", xml_path])
                run_command(["virsh", "net-start", "default"])
                run_command(["virsh", "net-autostart", "default"])

                print_success("Default network created, started, and set to autostart")
                return True

            finally:
                # Clean up the temporary file
                if os.path.exists(xml_path):
                    os.unlink(xml_path)

    except Exception as e:
        spinner.stop()
        logging.error(f"Error ensuring default network: {e}")
        print_error(f"Failed to configure default network: {e}")
        return False


#####################################
# VM Management Functions
#####################################


def get_vm_list() -> List[Dict[str, str]]:
    """
    Retrieve a list of VMs using 'virsh list --all'

    Returns:
        List of dictionaries with VM information
    """
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []

        if output:
            lines = output.strip().splitlines()

            # Find the separator line (contains dashes)
            try:
                sep_index = next(
                    i for i, line in enumerate(lines) if line.lstrip().startswith("---")
                )
            except StopIteration:
                sep_index = 1

            # Process VM entries
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


def get_vm_snapshots(vm_name: str) -> List[Dict[str, str]]:
    """
    Retrieve a list of snapshots for a specific VM

    Args:
        vm_name: Name of the VM to get snapshots for

    Returns:
        List of dictionaries with snapshot information
    """
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


def list_vms() -> List[Dict[str, str]]:
    """
    Display a numbered list of VMs with colored status

    Returns:
        List of VM dictionaries
    """
    print_header("Virtual Machines")

    spinner = Spinner("Retrieving VM list")
    spinner.start()

    vms = get_vm_list()
    spinner.stop()

    if not vms:
        print_info("No VMs found")
        return []

    # Print header
    print(f"{Colors.FROST3}{'No.':<5} {'Name':<25} {'State':<15} {'ID'}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 60}{Colors.ENDC}")

    # Print each VM with color-coded state
    for index, vm in enumerate(vms, start=1):
        # Colorize state
        state = vm["state"].lower()
        if "running" in state:
            state_color = f"{Colors.AURORA_GREEN}{vm['state']}{Colors.ENDC}"
        elif "paused" in state:
            state_color = f"{Colors.AURORA_YELLOW}{vm['state']}{Colors.ENDC}"
        elif "shut off" in state:
            state_color = f"{Colors.AURORA_RED}{vm['state']}{Colors.ENDC}"
        else:
            state_color = f"{Colors.SNOW_STORM1}{vm['state']}{Colors.ENDC}"

        print(
            f"{Colors.DETAIL}{index:<5}{Colors.ENDC} "
            f"{Colors.SNOW_STORM1}{vm['name']:<25}{Colors.ENDC} "
            f"{state_color:<15} "
            f"{Colors.DETAIL}{vm['id']}{Colors.ENDC}"
        )

    return vms


def list_vm_snapshots(vm_name: Optional[str] = None) -> List[Dict[str, str]]:
    """
    List snapshots for a specific VM or prompt for selection

    Args:
        vm_name: Optional name of VM to list snapshots for

    Returns:
        List of snapshot dictionaries
    """
    if not vm_name:
        vm_name = select_vm("Select a VM to list snapshots (or 'q' to cancel): ")
        if not vm_name:
            return []

    print_header(f"Snapshots for VM: {vm_name}")

    spinner = Spinner(f"Retrieving snapshots for {vm_name}")
    spinner.start()

    snapshots = get_vm_snapshots(vm_name)
    spinner.stop()

    if not snapshots:
        print_info(f"No snapshots found for VM '{vm_name}'")
        return []

    # Print header
    print(
        f"{Colors.FROST3}{'No.':<5} {'Name':<25} {'Creation Time':<25} {'State'}{Colors.ENDC}"
    )
    print(f"{Colors.FROST2}{'─' * 75}{Colors.ENDC}")

    # Print snapshots
    for index, snapshot in enumerate(snapshots, start=1):
        print(
            f"{Colors.DETAIL}{index:<5}{Colors.ENDC} "
            f"{Colors.SNOW_STORM1}{snapshot['name']:<25}{Colors.ENDC} "
            f"{Colors.FROST1}{snapshot['creation_time']:<25}{Colors.ENDC} "
            f"{Colors.FROST2}{snapshot['state']}{Colors.ENDC}"
        )

    return snapshots


def select_vm(
    prompt: str = "Select a VM by number (or 'q' to cancel): ",
) -> Optional[str]:
    """
    Prompt user to select a VM by number from the listed VMs

    Args:
        prompt: Text to display when prompting user

    Returns:
        Selected VM name or None if cancelled
    """
    vms = get_vm_list()
    if not vms:
        print_info("No VMs available")
        return None

    print_header("Select a Virtual Machine")

    # Print header
    print(f"{Colors.FROST3}{'No.':<5} {'Name':<25} {'State':<15}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 50}{Colors.ENDC}")

    # Print each VM with color-coded state
    for index, vm in enumerate(vms, start=1):
        # Colorize state
        state = vm["state"].lower()
        if "running" in state:
            state_color = f"{Colors.AURORA_GREEN}{vm['state']}{Colors.ENDC}"
        elif "paused" in state:
            state_color = f"{Colors.AURORA_YELLOW}{vm['state']}{Colors.ENDC}"
        elif "shut off" in state:
            state_color = f"{Colors.AURORA_RED}{vm['state']}{Colors.ENDC}"
        else:
            state_color = f"{Colors.SNOW_STORM1}{vm['state']}{Colors.ENDC}"

        print(
            f"{Colors.DETAIL}{index:<5}{Colors.ENDC} "
            f"{Colors.SNOW_STORM1}{vm['name']:<25}{Colors.ENDC} "
            f"{state_color:<15}"
        )

    while True:
        choice = input(f"\n{Colors.PROMPT}{prompt}{Colors.ENDC}").strip()

        if choice.lower() == "q":
            return None

        try:
            selection = int(choice)
            if 1 <= selection <= len(vms):
                return vms[selection - 1]["name"]
            else:
                print_error("Invalid number. Please select from the list")
        except ValueError:
            print_error("Invalid input. Please enter a valid number")


def select_snapshot(
    vm_name: str, prompt: str = "Select a snapshot by number (or 'q' to cancel): "
) -> Optional[str]:
    """
    Prompt user to select a snapshot by number

    Args:
        vm_name: Name of the VM to select snapshot from
        prompt: Text to display when prompting user

    Returns:
        Selected snapshot name or None if cancelled
    """
    snapshots = get_vm_snapshots(vm_name)
    if not snapshots:
        print_info(f"No snapshots available for VM '{vm_name}'")
        return None

    print_header(f"Select a Snapshot for VM: {vm_name}")

    # Print header
    print(f"{Colors.FROST3}{'No.':<5} {'Name':<25} {'Creation Time':<25}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 60}{Colors.ENDC}")

    # Print snapshots
    for index, snapshot in enumerate(snapshots, start=1):
        print(
            f"{Colors.DETAIL}{index:<5}{Colors.ENDC} "
            f"{Colors.SNOW_STORM1}{snapshot['name']:<25}{Colors.ENDC} "
            f"{Colors.FROST1}{snapshot['creation_time']:<25}{Colors.ENDC}"
        )

    while True:
        choice = input(f"\n{Colors.PROMPT}{prompt}{Colors.ENDC}").strip()

        if choice.lower() == "q":
            return None

        try:
            selection = int(choice)
            if 1 <= selection <= len(snapshots):
                return snapshots[selection - 1]["name"]
            else:
                print_error("Invalid number. Please select from the list")
        except ValueError:
            print_error("Invalid input. Please enter a valid number")


def create_vm() -> None:
    """Create a new virtual machine by gathering user inputs"""
    print_header("Create New Virtual Machine")

    # Make sure network is ready
    if not ensure_default_network():
        print_error("Cannot proceed without default network")
        return

    # Generate default name with timestamp
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = (
        input(
            f"{Colors.PROMPT}Enter VM name (default: {default_name}): {Colors.ENDC}"
        ).strip()
        or default_name
    )

    # Sanitize VM name (remove special chars)
    vm_name = "".join(c for c in vm_name if c.isalnum() or c in "-_")
    if not vm_name:
        print_error("VM name cannot be empty after sanitization")
        return

    print_section("Virtual Machine Resources")

    try:
        vcpus = int(
            input(f"{Colors.PROMPT}vCPUs (default: {DEFAULT_VCPUS}): {Colors.ENDC}")
            or DEFAULT_VCPUS
        )
        ram = int(
            input(
                f"{Colors.PROMPT}RAM in MB (default: {DEFAULT_RAM_MB}): {Colors.ENDC}"
            )
            or DEFAULT_RAM_MB
        )
        disk_size = int(
            input(
                f"{Colors.PROMPT}Disk size in GB (default: {DEFAULT_DISK_GB}): {Colors.ENDC}"
            )
            or DEFAULT_DISK_GB
        )
    except ValueError:
        print_error("Invalid input: vCPUs, RAM, and disk size must be numbers")
        return

    # Validate resource specifications
    if vcpus < 1 or ram < 512 or disk_size < 1:
        print_error(
            "Resource specifications are too low. vCPUs must be >=1, RAM >=512MB, and disk size >=1GB"
        )
        return

    # Check if disk image already exists
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        print_error(f"Disk image '{disk_image}' already exists")
        print_info("Please choose a different VM name")
        return

    print_section("Installation Media")
    print(f"{Colors.SNOW_STORM1}1. Use existing ISO{Colors.ENDC}")
    print(f"{Colors.SNOW_STORM1}2. Cancel{Colors.ENDC}")

    media_choice = input(f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC}").strip()
    if media_choice != "1":
        print_info("VM creation cancelled")
        return

    iso_path = input(
        f"{Colors.PROMPT}Enter the full path to the ISO file: {Colors.ENDC}"
    ).strip()
    if not os.path.isfile(iso_path):
        print_error("ISO file not found. VM creation cancelled")
        return

    # Ensure directory exists
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    # Create disk image
    print_section("Creating Disk Image")
    print_info(f"Creating {disk_size}GB disk image at {disk_image}")

    spinner = Spinner(f"Creating disk image")
    spinner.start()

    try:
        run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"])
        spinner.stop()
        print_success("Disk image created successfully")
    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to create disk image: {e}")
        print_error(f"Failed to create disk image: {e}")
        return

    # Create VM
    print_section("Creating Virtual Machine")
    print_info(f"Creating VM '{vm_name}' with {vcpus} vCPUs and {ram}MB RAM")

    spinner = Spinner(f"Creating virtual machine")
    spinner.start()

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
        spinner.stop()
        print_success(f"VM '{vm_name}' created successfully")
        logging.info(f"VM '{vm_name}' created successfully")

        # Print connection info
        print_info(
            f"VM is now installing from ISO. You can connect to the console with:"
        )
        print(f"  {Colors.DETAIL}virsh console {vm_name}{Colors.ENDC}")
        print_info(f"Or use a VNC viewer to connect to the graphical console")

    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to create VM '{vm_name}': {e}")
        print_error(f"Failed to create VM '{vm_name}': {e}")

        # Clean up on failure
        print_info("Cleaning up failed VM creation...")
        try:
            run_command(
                ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
            )
            print_info("Cleanup completed")
        except Exception:
            print_warning("Could not completely clean up resources")


def create_snapshot() -> None:
    """Create a snapshot of a virtual machine"""
    print_header("Create VM Snapshot")

    vm_name = select_vm("Select a VM to snapshot (or 'q' to cancel): ")
    if not vm_name:
        return

    # Get VM state
    output = run_command(["virsh", "domstate", vm_name], capture_output=True)
    if "running" not in output.lower():
        print_warning(
            f"VM '{vm_name}' is not running. For best results, the VM should be running"
        )
        proceed = input(
            f"{Colors.PROMPT}Do you want to continue anyway? (y/n): {Colors.ENDC}"
        ).lower()
        if proceed != "y":
            return

    # Gather snapshot details
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_snapshot_name = f"{vm_name}-snap-{timestamp}"

    snapshot_name = (
        input(
            f"{Colors.PROMPT}Enter snapshot name (default: {default_snapshot_name}): {Colors.ENDC}"
        ).strip()
        or default_snapshot_name
    )

    description = input(
        f"{Colors.PROMPT}Enter snapshot description (optional): {Colors.ENDC}"
    ).strip()

    # Create snapshot directory
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Create snapshot XML file
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""

    # Use a temporary file for the snapshot XML
    fd, snapshot_xml_path = tempfile.mkstemp(suffix=".xml")

    spinner = Spinner(f"Creating snapshot '{snapshot_name}'")

    try:
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)

        # Create snapshot
        spinner.start()
        run_command(
            ["virsh", "snapshot-create", vm_name, "--xmlfile", snapshot_xml_path]
        )
        spinner.stop()

        logging.info(
            f"Snapshot '{snapshot_name}' created successfully for VM '{vm_name}'"
        )
        print_success(f"Snapshot '{snapshot_name}' created successfully")

    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to create snapshot: {e}")
        print_error(f"Failed to create snapshot: {e}")

    finally:
        # Clean up temporary XML file
        if os.path.exists(snapshot_xml_path):
            os.unlink(snapshot_xml_path)


def revert_to_snapshot() -> None:
    """Revert a VM to a previous snapshot"""
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
        f"{Colors.PROMPT}Are you sure you want to revert VM '{vm_name}' to snapshot '{snapshot_name}'? (y/n): {Colors.ENDC}"
    ).lower()

    if confirm != "y":
        print_info("Revert operation cancelled")
        return

    try:
        # Get current VM state
        vm_running = False
        output = run_command(["virsh", "domstate", vm_name], capture_output=True)

        if "running" in output.lower():
            vm_running = True
            # Try graceful shutdown first
            print_info(f"Shutting down VM '{vm_name}'...")
            run_command(["virsh", "shutdown", vm_name], check=False)

            # Create a progress spinner while waiting
            spinner = Spinner("Waiting for VM to shut down")
            spinner.start()

            # Wait for VM to shut down (with timeout)
            timeout = 30  # seconds
            start_time = time.time()

            while time.time() - start_time < timeout:
                output = run_command(
                    ["virsh", "domstate", vm_name], capture_output=True
                )
                if "shut off" in output.lower():
                    break
                time.sleep(1)

            spinner.stop()

            # Check if VM is still running
            output = run_command(["virsh", "domstate", vm_name], capture_output=True)
            if "running" in output.lower():
                print_warning("VM did not shut down gracefully, forcing off...")
                run_command(["virsh", "destroy", vm_name], check=False)

        # Revert to snapshot
        print_info(f"Reverting VM to snapshot '{snapshot_name}'...")

        spinner = Spinner("Reverting to snapshot")
        spinner.start()

        run_command(["virsh", "snapshot-revert", vm_name, snapshot_name])

        spinner.stop()
        logging.info(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully"
        )
        print_success(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully"
        )

        # Restart VM if it was running before
        if vm_running:
            restart = input(
                f"{Colors.PROMPT}Would you like to restart the VM? (y/n): {Colors.ENDC}"
            ).lower()
            if restart == "y":
                print_info(f"Starting VM '{vm_name}'...")
                run_command(["virsh", "start", vm_name])
                print_success(f"VM '{vm_name}' started")

    except Exception as e:
        logging.error(f"Failed to revert to snapshot: {e}")
        print_error(f"Failed to revert to snapshot: {e}")


def delete_snapshot() -> None:
    """Delete a VM snapshot"""
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
        f"{Colors.PROMPT}Are you sure you want to delete snapshot '{snapshot_name}' for VM '{vm_name}'? (y/n): {Colors.ENDC}"
    ).lower()

    if confirm != "y":
        print_info("Deletion cancelled")
        return

    try:
        spinner = Spinner(f"Deleting snapshot '{snapshot_name}'")
        spinner.start()

        run_command(["virsh", "snapshot-delete", vm_name, snapshot_name])

        spinner.stop()
        logging.info(
            f"Snapshot '{snapshot_name}' for VM '{vm_name}' deleted successfully"
        )
        print_success(
            f"Snapshot '{snapshot_name}' for VM '{vm_name}' deleted successfully"
        )

    except Exception as e:
        spinner.stop()
        logging.error(f"Failed to delete snapshot: {e}")
        print_error(f"Failed to delete snapshot: {e}")


def delete_vm() -> None:
    """Delete an existing virtual machine"""
    print_header("Delete Virtual Machine")

    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return

    # Check if VM has snapshots
    spinner = Spinner(f"Checking snapshots for '{vm_name}'")
    spinner.start()

    snapshots = get_vm_snapshots(vm_name)
    spinner.stop()

    if snapshots:
        print_warning(f"VM '{vm_name}' has {len(snapshots)} snapshot(s)")
        print_warning("All snapshots will be deleted along with the VM")

    confirm = input(
        f"{Colors.PROMPT}Are you sure you want to delete VM '{vm_name}'? (y/n): {Colors.ENDC}"
    ).lower()
    if confirm != "y":
        print_info("Deletion cancelled")
        return

    try:
        # Check if VM is running
        output = run_command(
            ["virsh", "domstate", vm_name], capture_output=True, check=False
        )

        if "running" in output.lower():
            print_info(f"Shutting down VM '{vm_name}'...")
            run_command(["virsh", "shutdown", vm_name], check=False)

            # Wait a bit for graceful shutdown
            spinner = Spinner("Waiting for VM to shut down")
            spinner.start()
            time.sleep(5)
            spinner.stop()

        # Check again and force off if still running
        output = run_command(
            ["virsh", "domstate", vm_name], capture_output=True, check=False
        )
        if "running" in output.lower():
            print_warning("Forcing VM off...")
            run_command(["virsh", "destroy", vm_name], check=False)

        # Delete the VM and storage
        print_info(f"Deleting VM '{vm_name}' and all associated storage...")

        spinner = Spinner("Deleting virtual machine")
        spinner.start()

        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])

        spinner.stop()
        logging.info(f"VM '{vm_name}' deleted successfully")
        print_success(f"VM '{vm_name}' deleted successfully")

    except Exception as e:
        if "spinner" in locals() and spinner:
            spinner.stop()
        logging.error(f"Error deleting VM '{vm_name}': {e}")
        print_error(f"Error deleting VM '{vm_name}': {e}")


def start_vm() -> None:
    """Start a virtual machine after ensuring the default network is active"""
    print_header("Start Virtual Machine")

    if not ensure_default_network():
        print_error("Could not ensure default network is active. Aborting start")
        return

    vm_name = select_vm("Select a VM to start (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        # Check if VM is already running
        output = run_command(["virsh", "domstate", vm_name], capture_output=True)
        if "running" in output.lower():
            print_warning(f"VM '{vm_name}' is already running")
            return

        print_info(f"Starting VM '{vm_name}'...")

        spinner = Spinner(f"Starting VM '{vm_name}'")
        spinner.start()

        run_command(["virsh", "start", vm_name])

        spinner.stop()
        logging.info(f"VM '{vm_name}' started successfully")
        print_success(f"VM '{vm_name}' started successfully")

    except Exception as e:
        if "spinner" in locals() and spinner:
            spinner.stop()
        logging.error(f"Error starting VM '{vm_name}': {e}")
        print_error(f"Error starting VM '{vm_name}': {e}")


def stop_vm() -> None:
    """Stop a virtual machine, attempting graceful shutdown first"""
    print_header("Stop Virtual Machine")

    vm_name = select_vm("Select a VM to stop (or 'q' to cancel): ")
    if not vm_name:
        return

    # Check VM state first
    output = run_command(["virsh", "domstate", vm_name], capture_output=True)
    if "shut off" in output.lower():
        print_warning(f"VM '{vm_name}' is already stopped")
        return

    try:
        print_info(f"Sending shutdown signal to VM '{vm_name}'...")
        run_command(["virsh", "shutdown", vm_name])
        logging.info(f"Shutdown signal sent to VM '{vm_name}'")

        # Create a progress bar for waiting
        print_info("Waiting for VM to shut down...")
        spinner = Spinner("Shutdown in progress")
        spinner.start()

        # Wait for the VM to shut down gracefully
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "shut off" in output.lower():
                spinner.stop()
                print_success("VM shut down successfully")
                return

        spinner.stop()
        print_warning("VM is taking longer to shut down")
        force_shutdown = input(
            f"{Colors.PROMPT}Force VM to stop now? (y/n): {Colors.ENDC}"
        ).lower()

        if force_shutdown == "y":
            print_info("Forcing VM to stop...")
            run_command(["virsh", "destroy", vm_name])
            logging.info(f"VM '{vm_name}' forcefully stopped")
            print_success(f"VM '{vm_name}' forcefully stopped")
        else:
            print_info(
                f"VM '{vm_name}' shutdown in progress. Check status later with 'List VMs'"
            )

    except Exception as e:
        if "spinner" in locals() and spinner:
            spinner.stop()
        logging.error(f"Error stopping VM '{vm_name}': {e}")
        print_error(f"Error stopping VM '{vm_name}': {e}")


def show_vm_info() -> None:
    """Show detailed information about a VM"""
    print_header("VM Information")

    vm_name = select_vm("Select a VM to show info (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        print_section("Gathering VM Information")
        spinner = Spinner(f"Retrieving VM details for '{vm_name}'")
        spinner.start()

        # Get VM basic info
        output = run_command(["virsh", "dominfo", vm_name], capture_output=True)

        # Format the output with colors
        formatted_info = []
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                formatted_info.append(
                    f"{Colors.FROST2}{key.strip()}:{Colors.ENDC} {Colors.SNOW_STORM1}{value.strip()}{Colors.ENDC}"
                )

        # Get VM network info
        net_output = run_command(
            ["virsh", "domifaddr", vm_name], capture_output=True, check=False
        )

        # Get snapshots
        snapshots = get_vm_snapshots(vm_name)

        # Get VM storage info
        storage_output = run_command(
            ["virsh", "domblklist", vm_name], capture_output=True
        )

        spinner.stop()

        # Print basic VM info
        print_section("Basic VM Information")
        for line in formatted_info:
            print(line)

        # Print network interfaces
        print_section("Network Interfaces")
        if net_output and "failed" not in net_output.lower():
            print(f"{Colors.SNOW_STORM1}{net_output}{Colors.ENDC}")
        else:
            print_info("No network information available")

        # Print snapshots
        print_section("Snapshots")
        print(
            f"{Colors.FROST2}Total snapshots:{Colors.ENDC} {Colors.SNOW_STORM1}{len(snapshots)}{Colors.ENDC}"
        )

        if snapshots:
            print(f"{Colors.FROST2}Available snapshots:{Colors.ENDC}")
            for i, snap in enumerate(snapshots, 1):
                print(
                    f"  {Colors.DETAIL}{i}.{Colors.ENDC} {Colors.SNOW_STORM1}{snap['name']}{Colors.ENDC} ({Colors.FROST1}{snap['creation_time']}{Colors.ENDC})"
                )

        # Print storage devices
        print_section("Storage Devices")
        if "Target     Source" in storage_output:
            # Format the storage output
            lines = storage_output.splitlines()
            header = lines[0]
            separator = lines[1] if len(lines) > 1 else ""

            print(f"{Colors.FROST3}{header}{Colors.ENDC}")
            print(f"{Colors.FROST2}{separator}{Colors.ENDC}")

            for line in lines[2:]:
                print(f"{Colors.SNOW_STORM1}{line}{Colors.ENDC}")
        else:
            print(f"{Colors.SNOW_STORM1}{storage_output}{Colors.ENDC}")

    except Exception as e:
        if "spinner" in locals() and spinner:
            spinner.stop()
        logging.error(f"Error retrieving VM info: {e}")
        print_error(f"Error retrieving VM info: {e}")


#####################################
# Menu Functions
#####################################


def interactive_menu() -> None:
    """Display the main interactive menu for managing VMs"""
    while True:
        print_header("VM Manager")
        print(f"{Colors.SNOW_STORM1}1. List VMs{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}2. Create VM{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}3. Start VM{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}4. Stop VM{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}5. Delete VM{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}6. VM Information{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}7. Snapshot Management{Colors.ENDC}")
        print(f"{Colors.SNOW_STORM1}8. Exit{Colors.ENDC}")

        choice = input(f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC}").strip()

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
                print(f"{Colors.SNOW_STORM1}1. List Snapshots{Colors.ENDC}")
                print(f"{Colors.SNOW_STORM1}2. Create Snapshot{Colors.ENDC}")
                print(f"{Colors.SNOW_STORM1}3. Revert to Snapshot{Colors.ENDC}")
                print(f"{Colors.SNOW_STORM1}4. Delete Snapshot{Colors.ENDC}")
                print(f"{Colors.SNOW_STORM1}5. Return to Main Menu{Colors.ENDC}")

                snap_choice = input(
                    f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC}"
                ).strip()

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
                    print_error("Invalid choice. Please try again")

                if snap_choice != "5":
                    input(f"\n{Colors.PROMPT}Press Enter to continue...{Colors.ENDC}")
        elif choice == "8":
            print_info("Exiting VM Manager. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again")

        if choice != "8":
            input(f"\n{Colors.PROMPT}Press Enter to continue...{Colors.ENDC}")


#####################################
# Command Line Arguments
#####################################


def parse_args() -> argparse.Namespace:
    """
    Set up and parse command-line arguments

    Returns:
        Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Enhanced VM Manager - Manage Virtual Machines using libvirt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo ./vm_manager.py                     # Interactive mode
  sudo ./vm_manager.py --list              # List all VMs
  sudo ./vm_manager.py --start --vm test   # Start VM named 'test'
  sudo ./vm_manager.py --create-snapshot --vm test   # Create snapshot for VM 'test'
""",
    )

    # Create a group of mutually exclusive command options
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

    # Additional options
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--version", action="version", version="Enhanced VM Manager v1.0.0"
    )

    return parser.parse_args()


#####################################
# Main Function
#####################################


def main() -> None:
    """Main entry point for the script"""
    # Ensure minimum Python version
    if sys.version_info < (3, 6):
        print_error("Python 3.6 or higher is required")
        sys.exit(1)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set up logging
    setup_logging()

    # Print welcome banner
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(f"{'Enhanced VM Manager v1.0.0'.center(80)}")
    print(f"{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.DETAIL}System: {os.uname().sysname} {os.uname().release}")
    print(f"Hostname: {HOSTNAME}{Colors.ENDC}")

    # Check root privileges
    if not check_root():
        sys.exit(1)

    # Create necessary directories
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Check dependencies
    if not check_dependencies():
        logging.error("Missing critical dependencies")
        sys.exit(1)

    args = parse_args()

    # Set more verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose mode enabled")

    # Command-line direct mode if any operation argument is provided
    if args.list:
        list_vms()
    elif args.create:
        create_vm()
    elif args.start:
        if args.vm:
            # Direct VM start
            try:
                output = run_command(
                    ["virsh", "domstate", args.vm], capture_output=True, check=False
                )
                if "running" in output.lower():
                    print_warning(f"VM '{args.vm}' is already running")
                    sys.exit(0)

                # Ensure network is ready
                ensure_default_network()

                print_info(f"Starting VM '{args.vm}'...")
                run_command(["virsh", "start", args.vm])
                print_success(f"VM '{args.vm}' started successfully")
            except Exception as e:
                logging.error(f"Error starting VM '{args.vm}': {e}")
                print_error(f"Error starting VM '{args.vm}': {e}")
                sys.exit(1)
        else:
            start_vm()
    elif args.stop:
        if args.vm:
            # Direct VM stop
            try:
                output = run_command(
                    ["virsh", "domstate", args.vm], capture_output=True, check=False
                )
                if "shut off" in output.lower():
                    print_warning(f"VM '{args.vm}' is already stopped")
                    sys.exit(0)

                print_info(f"Sending shutdown signal to VM '{args.vm}'...")
                run_command(["virsh", "shutdown", args.vm])
                print_success(f"Shutdown signal sent to VM '{args.vm}'")
            except Exception as e:
                logging.error(f"Error stopping VM '{args.vm}': {e}")
                print_error(f"Error stopping VM '{args.vm}': {e}")
                sys.exit(1)
        else:
            stop_vm()
    elif args.delete:
        if args.vm:
            # Direct VM deletion with confirmation
            confirm = input(
                f"{Colors.PROMPT}Are you sure you want to delete VM '{args.vm}'? (y/n): {Colors.ENDC}"
            ).lower()
            if confirm == "y":
                try:
                    run_command(["virsh", "destroy", args.vm], check=False)
                    run_command(["virsh", "undefine", args.vm, "--remove-all-storage"])
                    print_success(f"VM '{args.vm}' deleted successfully")
                except Exception as e:
                    logging.error(f"Error deleting VM '{args.vm}': {e}")
                    print_error(f"Error deleting VM '{args.vm}': {e}")
                    sys.exit(1)
            else:
                print_info("Deletion cancelled")
        else:
            delete_vm()
    elif args.info:
        if args.vm:
            # Direct VM info
            try:
                # Get VM basic info
                output = run_command(["virsh", "dominfo", args.vm], capture_output=True)
                print_section("Basic VM Information")

                # Format the output with colors
                for line in output.splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        print(
                            f"{Colors.FROST2}{key.strip()}:{Colors.ENDC} {Colors.SNOW_STORM1}{value.strip()}{Colors.ENDC}"
                        )

                # Get snapshots count
                snapshots = get_vm_snapshots(args.vm)
                print_section("Snapshots")
                print(
                    f"{Colors.FROST2}Total snapshots:{Colors.ENDC} {Colors.SNOW_STORM1}{len(snapshots)}{Colors.ENDC}"
                )
            except Exception as e:
                logging.error(f"Error retrieving VM info: {e}")
                print_error(f"Error retrieving VM info: {e}")
                sys.exit(1)
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

            fd, snapshot_xml_path = tempfile.mkstemp(suffix=".xml")

            try:
                with os.fdopen(fd, "w") as f:
                    f.write(snapshot_xml)

                print_info(f"Creating snapshot '{snapshot_name}' for VM '{vm_name}'...")
                run_command(
                    [
                        "virsh",
                        "snapshot-create",
                        vm_name,
                        "--xmlfile",
                        snapshot_xml_path,
                    ]
                )
                print_success(f"Snapshot '{snapshot_name}' created successfully")
            except Exception as e:
                logging.error(f"Failed to create snapshot: {e}")
                print_error(f"Failed to create snapshot: {e}")
                sys.exit(1)
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
                f"{Colors.PROMPT}Are you sure you want to revert VM '{args.vm}' to snapshot '{args.snapshot}'? (y/n): {Colors.ENDC}"
            ).lower()

            if confirm == "y":
                try:
                    print_info(
                        f"Reverting VM '{args.vm}' to snapshot '{args.snapshot}'..."
                    )
                    run_command(["virsh", "snapshot-revert", args.vm, args.snapshot])
                    print_success(
                        f"VM '{args.vm}' reverted to snapshot '{args.snapshot}' successfully"
                    )
                except Exception as e:
                    logging.error(f"Failed to revert to snapshot: {e}")
                    print_error(f"Failed to revert to snapshot: {e}")
                    sys.exit(1)
            else:
                print_info("Revert operation cancelled")
        else:
            revert_to_snapshot()
    elif args.delete_snapshot:
        if args.vm and args.snapshot:
            # Confirm deletion
            confirm = input(
                f"{Colors.PROMPT}Are you sure you want to delete snapshot '{args.snapshot}' for VM '{args.vm}'? (y/n): {Colors.ENDC}"
            ).lower()

            if confirm == "y":
                try:
                    print_info(
                        f"Deleting snapshot '{args.snapshot}' for VM '{args.vm}'..."
                    )
                    run_command(["virsh", "snapshot-delete", args.vm, args.snapshot])
                    print_success(
                        f"Snapshot '{args.snapshot}' for VM '{args.vm}' deleted successfully"
                    )
                except Exception as e:
                    logging.error(f"Failed to delete snapshot: {e}")
                    print_error(f"Failed to delete snapshot: {e}")
                    sys.exit(1)
            else:
                print_info("Deletion cancelled")
        else:
            delete_snapshot()
    else:
        # Launch interactive menu if no direct command was provided
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print_warning("\nOperation cancelled by user")
            sys.exit(130)
        except Exception as e:
            logging.error(f"Unhandled exception: {e}")
            print_error(f"An unexpected error occurred: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
