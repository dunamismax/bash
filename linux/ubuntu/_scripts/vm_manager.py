#!/usr/bin/env python3
"""
Enhanced VM Manager
--------------------

A comprehensive virtual machine management utility for KVM/libvirt with robust error handling,
real‑time progress tracking, and a beautiful Nord‑themed interface. This tool provides a complete
solution for managing virtual machines (list, create, start, stop, delete, and snapshot management)
on Linux systems.

Note: This script must be run with root privileges.
Version: 1.0.0 | License: MIT
"""

import atexit
import fcntl
import json
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import shutil
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
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
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

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

# ------------------------------
# Nord‑Themed Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold #88C0D0]{border}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]  {title.center(TERM_WIDTH - 4)}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]{border}[/bold #88C0D0]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[#81A1C1]{message}[/#81A1C1]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {message}[/bold #8FBCBB]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #EBCB8B]⚠ {message}[/bold #EBCB8B]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {message}[/bold #BF616A]")


def check_root() -> bool:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        return False
    return True


def check_dependencies() -> bool:
    """Check if required dependencies are available."""
    required = ["virsh", "qemu-img", "virt-install"]
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        print_error(f"Missing required dependencies: {', '.join(missing)}")
        return False
    return True


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    """Configure logging with console and rotating file handlers."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    try:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Could not set up log file: {e}")
        logger.warning("Continuing with console logging only")


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    logging.info("Performing cleanup tasks...")
    # Add any required cleanup tasks here.


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"Script interrupted by {sig_name}.")
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ------------------------------
# Command Execution Helper
# ------------------------------
def run_command(
    command: List[str],
    capture_output: bool = False,
    check: bool = True,
    timeout: int = 60,
) -> str:
    """
    Execute a shell command with error handling.

    Args:
        command: List of command arguments.
        capture_output: If True, returns stdout.
        check: If True, raises on non-zero exit.
        timeout: Timeout in seconds.

    Returns:
        Command stdout if capture_output is True.
    """
    try:
        cmd_str = " ".join(shlex.quote(arg) for arg in command)
        logging.debug(f"Executing: {cmd_str}")
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result.stdout if capture_output else ""
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {cmd_str}")
        print_error(f"Command timed out: {cmd_str}")
        raise
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {cmd_str} with error: {e.stderr}")
        print_error(f"Command failed: {cmd_str}")
        raise


# ------------------------------
# VM Management Helper Functions
# ------------------------------
def ensure_default_network() -> bool:
    """
    Ensure the 'default' virtual network is active. If not, create and start it.
    """
    with console.status(
        "[bold #81A1C1]Checking default network status...", spinner="dots"
    ) as status:
        try:
            output = run_command(["virsh", "net-list", "--all"], capture_output=True)
            if "default" in output:
                if "active" in output:
                    print_success("Default network is active")
                    return True
                else:
                    print_info("Default network exists but is inactive. Starting it...")
                    run_command(["virsh", "net-start", "default"])
                    run_command(["virsh", "net-autostart", "default"])
                    print_success("Default network started and set to autostart")
                    return True
            else:
                print_info("Default network does not exist. Creating it...")
                fd, xml_path = tempfile.mkstemp(suffix=".xml")
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(DEFAULT_NETWORK_XML)
                    os.chmod(xml_path, 0o644)
                    run_command(["virsh", "net-define", xml_path])
                    run_command(["virsh", "net-start", "default"])
                    run_command(["virsh", "net-autostart", "default"])
                    print_success("Default network created and activated")
                    return True
                finally:
                    if os.path.exists(xml_path):
                        os.unlink(xml_path)
        except Exception as e:
            logging.error(f"Error ensuring default network: {e}")
            print_error(f"Failed to configure default network: {e}")
            return False


def get_vm_list() -> List[Dict[str, str]]:
    """
    Retrieve VM list using 'virsh list --all'

    Returns:
        List of dictionaries with VM info.
    """
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        lines = output.strip().splitlines()
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


def get_vm_snapshots(vm_name: str) -> List[Dict[str, str]]:
    """
    Retrieve snapshots for a VM.

    Args:
        vm_name: Name of the VM.

    Returns:
        List of snapshot info dictionaries.
    """
    try:
        output = run_command(
            ["virsh", "snapshot-list", vm_name], capture_output=True, check=False
        )
        if not output or "failed" in output.lower():
            return []
        snapshots = []
        lines = output.strip().splitlines()
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
                snapshots.append(
                    {
                        "name": parts[0],
                        "creation_time": " ".join(parts[1:3]) if len(parts) > 2 else "",
                        "state": parts[3] if len(parts) > 3 else "",
                    }
                )
        return snapshots
    except Exception as e:
        logging.error(f"Failed to retrieve snapshots for VM '{vm_name}': {e}")
        return []


def select_vm(
    prompt: str = "Select a VM by number (or 'q' to cancel): ",
) -> Optional[str]:
    """
    Prompt the user to select a VM from the list.

    Returns:
        Selected VM name or None if cancelled.
    """
    vms = get_vm_list()
    if not vms:
        print_info("No VMs available")
        return None

    print_section("Select a Virtual Machine")
    print(f"[#ECEFF4]{'No.':<5} {'Name':<25} {'State':<15}[/#ECEFF4]")
    print(f"[#81A1C1]{'─' * 50}[/#81A1C1]")

    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_str = f"[#A3BE8C]{vm['state']}[/#A3BE8C]"
        elif "paused" in state:
            state_str = f"[#EBCB8B]{vm['state']}[/#EBCB8B]"
        elif "shut off" in state:
            state_str = f"[#BF616A]{vm['state']}[/#BF616A]"
        else:
            state_str = f"[#D8DEE9]{vm['state']}[/#D8DEE9]"
        print(
            f"[#D8DEE9]{idx:<5}[/#D8DEE9] [#D8DEE9]{vm['name']:<25}[/#D8DEE9] {state_str:<15}"
        )

    while True:
        choice = input(f"\n[bold #B48EAD]{prompt}[/bold #B48EAD] ").strip()
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(vms):
                return vms[num - 1]["name"]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


def select_snapshot(
    vm_name: str, prompt: str = "Select a snapshot by number (or 'q' to cancel): "
) -> Optional[str]:
    """
    Prompt the user to select a snapshot for a VM.

    Returns:
        Selected snapshot name or None.
    """
    snapshots = get_vm_snapshots(vm_name)
    if not snapshots:
        print_info(f"No snapshots found for VM '{vm_name}'")
        return None

    print_section(f"Snapshots for VM: {vm_name}")
    print(f"[#ECEFF4]{'No.':<5} {'Name':<25} {'Creation Time':<25}[/#ECEFF4]")
    print(f"[#81A1C1]{'─' * 60}[/#81A1C1]")

    for idx, snap in enumerate(snapshots, start=1):
        print(
            f"[#D8DEE9]{idx:<5}[/#D8DEE9] [#D8DEE9]{snap['name']:<25}[/#D8DEE9] [#81A1C1]{snap['creation_time']:<25}[/#81A1C1]"
        )

    while True:
        choice = input(f"\n[bold #B48EAD]{prompt}[/bold #B48EAD] ").strip()
        if choice.lower() == "q":
            return None
        try:
            num = int(choice)
            if 1 <= num <= len(snapshots):
                return snapshots[num - 1]["name"]
            else:
                print_error("Invalid selection number.")
        except ValueError:
            print_error("Please enter a valid number.")


# ------------------------------
# VM Management Functions
# ------------------------------
def list_vms() -> None:
    """Display a list of VMs."""
    print_header("Virtual Machines")
    vms = get_vm_list()
    if not vms:
        print_info("No VMs found.")
        return
    print(f"[#ECEFF4]{'No.':<5} {'Name':<25} {'State':<15} {'ID'}[/#ECEFF4]")
    print(f"[#81A1C1]{'─' * 60}[/#81A1C1]")
    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_str = f"[#A3BE8C]{vm['state']}[/#A3BE8C]"
        elif "paused" in state:
            state_str = f"[#EBCB8B]{vm['state']}[/#EBCB8B]"
        elif "shut off" in state:
            state_str = f"[#BF616A]{vm['state']}[/#BF616A]"
        else:
            state_str = f"[#D8DEE9]{vm['state']}[/#D8DEE9]"
        print(
            f"[#D8DEE9]{idx:<5}[/#D8DEE9] [#D8DEE9]{vm['name']:<25}[/#D8DEE9] {state_str:<15} [#D8DEE9]{vm['id']}[/#D8DEE9]"
        )


def create_vm() -> None:
    """Create a new VM by gathering user input interactively."""
    print_header("Create New Virtual Machine")
    if not ensure_default_network():
        print_error("Default network is not active. Cannot proceed.")
        return

    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = (
        input(
            f"[bold #B48EAD]Enter VM name (default: {default_name}): [/bold #B48EAD] "
        ).strip()
        or default_name
    )
    vm_name = "".join(c for c in vm_name if c.isalnum() or c in "-_")
    if not vm_name:
        print_error("Invalid VM name.")
        return

    print_section("Specify VM Resources")
    try:
        vcpus = int(
            input(f"[bold #B48EAD]vCPUs (default: {DEFAULT_VCPUS}): [/bold #B48EAD] ")
            or DEFAULT_VCPUS
        )
        ram = int(
            input(
                f"[bold #B48EAD]RAM in MB (default: {DEFAULT_RAM_MB}): [/bold #B48EAD] "
            )
            or DEFAULT_RAM_MB
        )
        disk_size = int(
            input(
                f"[bold #B48EAD]Disk size in GB (default: {DEFAULT_DISK_GB}): [/bold #B48EAD] "
            )
            or DEFAULT_DISK_GB
        )
    except ValueError:
        print_error("vCPUs, RAM, and disk size must be numbers.")
        return

    if vcpus < 1 or ram < 512 or disk_size < 1:
        print_error("Invalid resource specifications.")
        return

    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        print_error(
            f"Disk image '{disk_image}' already exists. Choose a different VM name."
        )
        return

    print_section("Installation Media")
    print(f"[#D8DEE9]1. Use existing ISO[/#D8DEE9]")
    print(f"[#D8DEE9]2. Cancel[/#D8DEE9]")
    media_choice = input(f"\n[bold #B48EAD]Enter your choice: [/bold #B48EAD] ").strip()
    if media_choice != "1":
        print_info("VM creation cancelled.")
        return

    iso_path = input(
        f"[bold #B48EAD]Enter full path to the ISO file: [/bold #B48EAD] "
    ).strip()
    if not os.path.isfile(iso_path):
        print_error("ISO file not found. VM creation cancelled.")
        return

    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    print_section("Creating Disk Image")
    print_info(f"Creating {disk_size}GB disk image at {disk_image}")
    with console.status(
        "[bold #81A1C1]Creating disk image...", spinner="dots"
    ) as status:
        try:
            run_command(
                ["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]
            )
            print_success("Disk image created successfully")
        except Exception as e:
            print_error(f"Failed to create disk image: {e}")
            return

    print_section("Creating Virtual Machine")
    print_info(f"Creating VM '{vm_name}' with {vcpus} vCPUs and {ram}MB RAM")
    with console.status(
        "[bold #81A1C1]Creating virtual machine...", spinner="dots"
    ) as status:
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
            print_success(f"VM '{vm_name}' created successfully")
            print_info("To connect to the console, use:")
            print(f"  [#D8DEE9]virsh console {vm_name}[/#D8DEE9]")
        except Exception as e:
            print_error(f"Failed to create VM '{vm_name}': {e}")
            print_info("Cleaning up failed VM creation...")
            try:
                run_command(
                    ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
                )
            except Exception:
                print_warning("Incomplete cleanup")
            return


def start_vm() -> None:
    """Start an existing VM after ensuring the default network is active."""
    print_header("Start Virtual Machine")
    if not ensure_default_network():
        print_error("Default network is not active. Aborting start.")
        return
    vm_name = select_vm("Select a VM to start (or 'q' to cancel): ")
    if not vm_name:
        return
    try:
        output = run_command(["virsh", "domstate", vm_name], capture_output=True)
        if "running" in output.lower():
            print_warning(f"VM '{vm_name}' is already running.")
            return

        print_info(f"Starting VM '{vm_name}'...")
        with console.status(
            f"[bold #81A1C1]Starting VM '{vm_name}'...", spinner="dots"
        ) as status:
            run_command(["virsh", "start", vm_name])
            print_success(f"VM '{vm_name}' started successfully")
    except Exception as e:
        print_error(f"Error starting VM '{vm_name}': {e}")


def stop_vm() -> None:
    """Stop a running VM with graceful shutdown and forced destruction if needed."""
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop (or 'q' to cancel): ")
    if not vm_name:
        return

    output = run_command(["virsh", "domstate", vm_name], capture_output=True)
    if "shut off" in output.lower():
        print_warning(f"VM '{vm_name}' is already stopped.")
        return

    try:
        print_info(f"Sending shutdown signal to VM '{vm_name}'...")
        run_command(["virsh", "shutdown", vm_name])

        with console.status(
            "[bold #81A1C1]Waiting for VM to shut down...", spinner="dots"
        ) as status:
            for _ in range(30):
                time.sleep(1)
                output = run_command(
                    ["virsh", "domstate", vm_name], capture_output=True, check=False
                )
                if "shut off" in output.lower():
                    print_success("VM shut down successfully")
                    return

            print_warning("VM did not shut down gracefully; forcing stop...")
            run_command(["virsh", "destroy", vm_name], check=False)
            print_success(f"VM '{vm_name}' forcefully stopped")
    except Exception as e:
        print_error(f"Error stopping VM '{vm_name}': {e}")


def delete_vm() -> None:
    """Delete an existing VM and its associated storage."""
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return

    confirm = input(
        f"[bold #B48EAD]Are you sure you want to delete VM '{vm_name}'? (y/n): [/bold #B48EAD] "
    ).lower()
    if confirm != "y":
        print_info("Deletion cancelled")
        return

    try:
        output = run_command(
            ["virsh", "domstate", vm_name], capture_output=True, check=False
        )
        if "running" in output.lower():
            print_info(f"Shutting down VM '{vm_name}'...")
            run_command(["virsh", "shutdown", vm_name], check=False)

            with console.status(
                "[bold #81A1C1]Waiting for VM shutdown...", spinner="dots"
            ) as status:
                time.sleep(5)

            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "running" in output.lower():
                print_warning("Forcing VM off...")
                run_command(["virsh", "destroy", vm_name], check=False)

        print_info(f"Deleting VM '{vm_name}' and its storage...")
        with console.status("[bold #81A1C1]Deleting VM...", spinner="dots") as status:
            run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])

        print_success(f"VM '{vm_name}' deleted successfully")
    except Exception as e:
        print_error(f"Error deleting VM '{vm_name}': {e}")


def show_vm_info() -> None:
    """Display detailed information for a selected VM."""
    print_header("VM Information")
    vm_name = select_vm("Select a VM to show info (or 'q' to cancel): ")
    if not vm_name:
        return

    try:
        print_section("Basic VM Information")
        output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                print(
                    f"[#81A1C1]{key.strip()}:[/#81A1C1] [#D8DEE9]{value.strip()}[/#D8DEE9]"
                )

        print_section("Network Information")
        net_output = run_command(
            ["virsh", "domifaddr", vm_name], capture_output=True, check=False
        )
        if net_output and "failed" not in net_output.lower():
            print(f"[#D8DEE9]{net_output}[/#D8DEE9]")
        else:
            print_info("No network information available")

        print_section("Snapshots")
        snapshots = get_vm_snapshots(vm_name)
        print(
            f"[#81A1C1]Total snapshots:[/#81A1C1] [#D8DEE9]{len(snapshots)}[/#D8DEE9]"
        )
        if snapshots:
            for idx, snap in enumerate(snapshots, 1):
                print(
                    f"  [#D8DEE9]{idx}.[/#D8DEE9] [#D8DEE9]{snap['name']}[/#D8DEE9] ([#81A1C1]{snap['creation_time']}[/#81A1C1])"
                )

        print_section("Storage Devices")
        storage_output = run_command(
            ["virsh", "domblklist", vm_name], capture_output=True
        )
        if "Target     Source" in storage_output:
            lines = storage_output.splitlines()
            print(f"[#5E81AC]{lines[0]}[/#5E81AC]")
            print(f"[#81A1C1]{lines[1]}[/#81A1C1]")
            for line in lines[2:]:
                print(f"[#D8DEE9]{line}[/#D8DEE9]")
        else:
            print(f"[#D8DEE9]{storage_output}[/#D8DEE9]")
    except Exception as e:
        print_error(f"Error retrieving VM info: {e}")


def list_vm_snapshots(vm: Optional[str] = None) -> None:
    """
    List all snapshots for a specified VM. If no VM is provided,
    prompt the user to select one.
    """
    if not vm:
        vm = select_vm("Select a VM to list snapshots (or 'q' to cancel): ")
        if not vm:
            print_info("No VM selected.")
            return

    snapshots = get_vm_snapshots(vm)
    if not snapshots:
        print_info(f"No snapshots found for VM '{vm}'.")
        return

    print_header(f"Snapshots for VM: {vm}")
    print(f"[#ECEFF4]{'No.':<5} {'Name':<25} {'Creation Time':<25}[/#ECEFF4]")
    print(f"[#81A1C1]{'─' * 60}[/#81A1C1]")

    for idx, snap in enumerate(snapshots, start=1):
        print(
            f"[#D8DEE9]{idx:<5}[/#D8DEE9] [#D8DEE9]{snap['name']:<25}[/#D8DEE9] [#81A1C1]{snap['creation_time']:<25}[/#81A1C1]"
        )


def create_snapshot() -> None:
    """Create a snapshot for a VM."""
    print_header("Create VM Snapshot")
    vm_name = select_vm("Select a VM to snapshot (or 'q' to cancel): ")
    if not vm_name:
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_snapshot = f"{vm_name}-snap-{timestamp}"
    snapshot_name = (
        input(
            f"[bold #B48EAD]Enter snapshot name (default: {default_snapshot}): [/bold #B48EAD] "
        ).strip()
        or default_snapshot
    )

    description = input(
        f"[bold #B48EAD]Enter snapshot description (optional): [/bold #B48EAD] "
    ).strip()

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""

    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)

        with console.status(
            f"[bold #81A1C1]Creating snapshot '{snapshot_name}'...", spinner="dots"
        ) as status:
            run_command(["virsh", "snapshot-create", vm_name, "--xmlfile", xml_path])

        print_success(f"Snapshot '{snapshot_name}' created successfully")
    except Exception as e:
        print_error(f"Failed to create snapshot: {e}")
    finally:
        if os.path.exists(xml_path):
            os.unlink(xml_path)


def revert_to_snapshot() -> None:
    """Revert a VM to a selected snapshot."""
    print_header("Revert VM to Snapshot")
    vm_name = select_vm("Select a VM to revert (or 'q' to cancel): ")
    if not vm_name:
        return

    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to revert to (or 'q' to cancel): "
    )
    if not snapshot_name:
        return

    confirm = (
        input(
            f"[bold #B48EAD]Confirm revert of VM '{vm_name}' to snapshot '{snapshot_name}'? (y/n): [/bold #B48EAD] "
        )
        .strip()
        .lower()
    )

    if confirm != "y":
        print_info("Revert operation cancelled")
        return

    try:
        with console.status(
            "[bold #81A1C1]Reverting to snapshot...", spinner="dots"
        ) as status:
            run_command(["virsh", "snapshot-revert", vm_name, snapshot_name])

        print_success(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully"
        )

        if (
            "running"
            in run_command(["virsh", "domstate", vm_name], capture_output=True).lower()
        ):
            restart = (
                input(f"[bold #B48EAD]Restart VM now? (y/n): [/bold #B48EAD] ")
                .strip()
                .lower()
            )
            if restart == "y":
                print_info(f"Starting VM '{vm_name}'...")
                run_command(["virsh", "start", vm_name])
                print_success(f"VM '{vm_name}' started")
    except Exception as e:
        print_error(f"Failed to revert snapshot: {e}")


def delete_snapshot() -> None:
    """Delete a snapshot for a VM."""
    print_header("Delete VM Snapshot")
    vm_name = select_vm("Select a VM (or 'q' to cancel): ")
    if not vm_name:
        return

    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to delete (or 'q' to cancel): "
    )
    if not snapshot_name:
        return

    confirm = (
        input(
            f"[bold #B48EAD]Delete snapshot '{snapshot_name}' for VM '{vm_name}'? (y/n): [/bold #B48EAD] "
        )
        .strip()
        .lower()
    )

    if confirm != "y":
        print_info("Deletion cancelled")
        return

    try:
        with console.status(
            f"[bold #81A1C1]Deleting snapshot '{snapshot_name}'...", spinner="dots"
        ) as status:
            run_command(["virsh", "snapshot-delete", vm_name, snapshot_name])

        print_success(f"Snapshot '{snapshot_name}' deleted successfully")
    except Exception as e:
        print_error(f"Failed to delete snapshot: {e}")


# ------------------------------
# Interactive Menu Functions
# ------------------------------
def snapshot_management_menu() -> None:
    """Display the snapshot management submenu."""
    while True:
        print_header("Snapshot Management")
        console.print("[#D8DEE9]1. List Snapshots[/#D8DEE9]")
        console.print("[#D8DEE9]2. Create Snapshot[/#D8DEE9]")
        console.print("[#D8DEE9]3. Revert to Snapshot[/#D8DEE9]")
        console.print("[#D8DEE9]4. Delete Snapshot[/#D8DEE9]")
        console.print("[#D8DEE9]5. Return to Main Menu[/#D8DEE9]")

        snap_choice = input(
            "\n[bold #B48EAD]Enter your choice: [/bold #B48EAD] "
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
            print_error("Invalid choice. Please try again.")

        input("\n[bold #B48EAD]Press Enter to continue...[/bold #B48EAD]")


def interactive_menu() -> None:
    """Display the interactive VM management menu."""
    while True:
        print_header("VM Manager")
        console.print("[#D8DEE9]1. List VMs[/#D8DEE9]")
        console.print("[#D8DEE9]2. Create VM[/#D8DEE9]")
        console.print("[#D8DEE9]3. Start VM[/#D8DEE9]")
        console.print("[#D8DEE9]4. Stop VM[/#D8DEE9]")
        console.print("[#D8DEE9]5. Delete VM[/#D8DEE9]")
        console.print("[#D8DEE9]6. Show VM Info[/#D8DEE9]")
        console.print("[#D8DEE9]7. Snapshot Management[/#D8DEE9]")
        console.print("[#D8DEE9]8. Exit[/#D8DEE9]")

        choice = input("\n[bold #B48EAD]Enter your choice: [/bold #B48EAD] ").strip()

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
            snapshot_management_menu()
        elif choice == "8":
            print_info("Exiting VM Manager. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again.")

        if choice != "7":  # We don't need this after the snapshot submenu
            input("\n[bold #B48EAD]Press Enter to continue...[/bold #B48EAD]")


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    """Main entry point for the VM Manager."""
    try:
        print_header("Enhanced VM Manager v1.0.0")
        console.print(f"Hostname: [bold #81A1C1]{HOSTNAME}[/bold #81A1C1]")
        console.print(
            f"Date: [bold #81A1C1]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #81A1C1]"
        )

        if not check_root():
            sys.exit(1)

        setup_logging()

        # Ensure directories exist
        os.makedirs(ISO_DIR, exist_ok=True)
        os.makedirs(VM_IMAGE_DIR, exist_ok=True)
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

        if not check_dependencies():
            logging.error("Missing critical dependencies")
            sys.exit(1)

        # Launch interactive menu
        interactive_menu()

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
