#!/usr/bin/env python3
"""
Enhanced VM Manager
--------------------

A comprehensive virtual machine management utility for KVM/libvirt with robust error handling,
real‑time progress tracking, and a beautiful Nord‑themed interface. This tool provides a complete
solution for managing virtual machines (list, create, start, stop, delete, and snapshot management)
on Linux systems.

Note: This script must be run with root privileges.
Version: 1.0.0 | Author: YourName | License: MIT
"""

import atexit
import argparse
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

import click
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
PROGRESS_WIDTH = 40
SPINNER_DELAY = 0.1  # seconds between spinner updates
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
# Nord‑Themed Colors & Console Setup
# ------------------------------
class Colors:
    """Nord‑themed ANSI color codes."""

    HEADER = "\033[38;5;81m"  # Nord9 - Blue
    SUCCESS = "\033[38;5;142m"  # Nord14 - Green
    WARNING = "\033[38;5;179m"  # Nord13 - Yellow
    ERROR = "\033[38;5;196m"  # Nord11 - Red
    INFO = "\033[38;5;110m"  # Nord8 - Light Blue
    DETAIL = "\033[38;5;188m"  # Nord4 - Off white
    PROMPT = "\033[38;5;139m"  # Nord15 - Purple
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"


console = Console()


def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {Colors.HEADER}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {Colors.HEADER}]{border}[/{Colors.HEADER}{Colors.BOLD}]")
    console.print(
        f"[bold {Colors.HEADER}]  {title.center(TERM_WIDTH - 4)}[/{Colors.HEADER}{Colors.BOLD}]"
    )
    console.print(f"[bold {Colors.HEADER}]{border}[/{Colors.HEADER}]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{Colors.INFO}]{message}[/{Colors.INFO}]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {Colors.SUCCESS}]✓ {message}[/{Colors.SUCCESS}]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {Colors.WARNING}]⚠ {message}[/{Colors.WARNING}]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {Colors.ERROR}]✗ {message}[/{Colors.ERROR}]")


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
        fmt=f"{Colors.BOLD}[%(asctime)s] [%(levelname)s]{Colors.ENDC} %(message)s",
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
    logging.info("Performing cleanup tasks...")
    # Add any required cleanup tasks here.


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
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
# Progress Tracking Classes
# ------------------------------
class ProgressBar:
    """Thread‑safe progress bar with rate and ETA display."""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.last_update_value = 0
        self.rate = 0
        self._lock = threading.Lock()
        self._display()

    def update(self, amount: int = 1) -> None:
        with self._lock:
            self.current = min(self.current + amount, self.total)
            now = time.time()
            if now - self.last_update_time >= 0.5:
                diff = self.current - self.last_update_value
                self.rate = (
                    diff / (now - self.last_update_time)
                    if now - self.last_update_time > 0
                    else 0
                )
                self.last_update_time = now
                self.last_update_value = self.current
            self._display()

    def _display(self) -> None:
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100
        elapsed = time.time() - self.start_time
        eta = (self.total - self.current) / self.rate if self.rate > 0 else 0
        progress_line = (
            f"\r{Colors.DETAIL}{self.desc}: {Colors.ENDC}|{Colors.HEADER}{bar}{Colors.ENDC}| "
            f"{Colors.WHITE}{percent:5.1f}%{Colors.ENDC} ({self.current}/{self.total}) "
            f"[{Colors.GREEN}{self.rate:.1f}/s{Colors.ENDC}] [ETA: {int(eta)}s]"
        )
        sys.stdout.write(progress_line)
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write("\n")


class Spinner:
    """Thread‑safe spinner for operations with indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self.active = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def _spin(self) -> None:
        i = 0
        while self.active:
            elapsed = time.time() - self.start_time
            time_str = f"{elapsed:.1f}s"
            sys.stdout.write(
                f"\r{Colors.FROST2}{self.spinner_chars[i % len(self.spinner_chars)]}{Colors.ENDC} "
                f"{Colors.DETAIL}{self.message} [elapsed: {time_str}]{Colors.ENDC}"
            )
            sys.stdout.flush()
            time.sleep(SPINNER_DELAY)
            i += 1

    def stop(self) -> None:
        with self._lock:
            if self.active:
                self.active = False
                if self.thread:
                    self.thread.join()
                sys.stdout.write("\r" + " " * (TERM_WIDTH) + "\r")
                sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


# ------------------------------
# VM Management Helper Functions
# ------------------------------
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
    print(f"{Colors.DETAIL}{'No.':<5} {'Name':<25} {'Creation Time':<25}{Colors.ENDC}")
    print(f"{Colors.DETAIL}{'─' * 60}{Colors.ENDC}")
    for idx, snap in enumerate(snapshots, start=1):
        print(
            f"{Colors.DETAIL}{idx:<5}{Colors.ENDC} {Colors.DETAIL}{snap['name']:<25}{Colors.ENDC} {Colors.DETAIL}{snap['creation_time']:<25}{Colors.ENDC}"
        )


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


def ensure_default_network() -> bool:
    """
    Ensure the 'default' virtual network is active. If not, create and start it.
    """
    spinner = Spinner("Checking default network status")
    spinner.start()
    try:
        output = run_command(["virsh", "net-list", "--all"], capture_output=True)
        if "default" in output:
            if "active" in output:
                spinner.stop()
                print_success("Default network is active")
                return True
            else:
                spinner.stop()
                print_info("Default network exists but is inactive. Starting it...")
                run_command(["virsh", "net-start", "default"])
                run_command(["virsh", "net-autostart", "default"])
                print_success("Default network started and set to autostart")
                return True
        else:
            spinner.stop()
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
        spinner.stop()
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

    print_header("Select a Virtual Machine")
    print(f"{Colors.DETAIL}{'No.':<5} {'Name':<25} {'State':<15}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 50}{Colors.ENDC}")

    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_str = f"{Colors.AURORA_GREEN}{vm['state']}{Colors.ENDC}"
        elif "paused" in state:
            state_str = f"{Colors.AURORA_YELLOW}{vm['state']}{Colors.ENDC}"
        elif "shut off" in state:
            state_str = f"{Colors.AURORA_RED}{vm['state']}{Colors.ENDC}"
        else:
            state_str = f"{Colors.SNOW_STORM1}{vm['state']}{Colors.ENDC}"
        print(
            f"{Colors.DETAIL}{idx:<5}{Colors.ENDC} {Colors.SNOW_STORM1}{vm['name']:<25}{Colors.ENDC} {state_str:<15}"
        )

    while True:
        choice = input(f"\n{Colors.PROMPT}{prompt}{Colors.ENDC} ").strip()
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

    print_header(f"Snapshots for VM: {vm_name}")
    print(f"{Colors.DETAIL}{'No.':<5} {'Name':<25} {'Creation Time':<25}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 60}{Colors.ENDC}")

    for idx, snap in enumerate(snapshots, start=1):
        print(
            f"{Colors.DETAIL}{idx:<5}{Colors.ENDC} {Colors.SNOW_STORM1}{snap['name']:<25}{Colors.ENDC} {Colors.FROST1}{snap['creation_time']:<25}{Colors.ENDC}"
        )

    while True:
        choice = input(f"\n{Colors.PROMPT}{prompt}{Colors.ENDC} ").strip()
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
    print(f"{Colors.FROST3}{'No.':<5} {'Name':<25} {'State':<15} {'ID'}{Colors.ENDC}")
    print(f"{Colors.FROST2}{'─' * 60}{Colors.ENDC}")
    for idx, vm in enumerate(vms, start=1):
        state = vm["state"].lower()
        if "running" in state:
            state_str = f"{Colors.AURORA_GREEN}{vm['state']}{Colors.ENDC}"
        elif "paused" in state:
            state_str = f"{Colors.AURORA_YELLOW}{vm['state']}{Colors.ENDC}"
        elif "shut off" in state:
            state_str = f"{Colors.AURORA_RED}{vm['state']}{Colors.ENDC}"
        else:
            state_str = f"{Colors.SNOW_STORM1}{vm['state']}{Colors.ENDC}"
        print(
            f"{Colors.DETAIL}{idx:<5}{Colors.ENDC} {Colors.SNOW_STORM1}{vm['name']:<25}{Colors.ENDC} {state_str:<15} {Colors.DETAIL}{vm['id']}{Colors.ENDC}"
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
            f"{Colors.PROMPT}Enter VM name (default: {default_name}): {Colors.ENDC} "
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
            input(f"{Colors.PROMPT}vCPUs (default: {DEFAULT_VCPUS}): {Colors.ENDC} ")
            or DEFAULT_VCPUS
        )
        ram = int(
            input(
                f"{Colors.PROMPT}RAM in MB (default: {DEFAULT_RAM_MB}): {Colors.ENDC} "
            )
            or DEFAULT_RAM_MB
        )
        disk_size = int(
            input(
                f"{Colors.PROMPT}Disk size in GB (default: {DEFAULT_DISK_GB}): {Colors.ENDC} "
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
    print(f"{Colors.SNOW_STORM1}1. Use existing ISO{Colors.ENDC}")
    print(f"{Colors.SNOW_STORM1}2. Cancel{Colors.ENDC}")
    media_choice = input(f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC} ").strip()
    if media_choice != "1":
        print_info("VM creation cancelled.")
        return

    iso_path = input(
        f"{Colors.PROMPT}Enter full path to the ISO file: {Colors.ENDC} "
    ).strip()
    if not os.path.isfile(iso_path):
        print_error("ISO file not found. VM creation cancelled.")
        return

    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    print_section("Creating Disk Image")
    print_info(f"Creating {disk_size}GB disk image at {disk_image}")
    spinner = Spinner("Creating disk image")
    spinner.start()
    try:
        run_command(["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"])
        spinner.stop()
        print_success("Disk image created successfully")
    except Exception as e:
        spinner.stop()
        print_error(f"Failed to create disk image: {e}")
        return

    print_section("Creating Virtual Machine")
    print_info(f"Creating VM '{vm_name}' with {vcpus} vCPUs and {ram}MB RAM")
    spinner = Spinner("Creating virtual machine")
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
        print_info("To connect to the console, use:")
        print(f"  {Colors.DETAIL}virsh console {vm_name}{Colors.ENDC}")
    except Exception as e:
        spinner.stop()
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
        spinner = Spinner(f"Starting VM '{vm_name}'")
        spinner.start()
        run_command(["virsh", "start", vm_name])
        spinner.stop()
        print_success(f"VM '{vm_name}' started successfully")
    except Exception as e:
        spinner.stop()
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
        spinner = Spinner("Waiting for VM to shut down")
        spinner.start()
        for _ in range(30):
            time.sleep(1)
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "shut off" in output.lower():
                spinner.stop()
                print_success("VM shut down successfully")
                return
        spinner.stop()
        print_warning("VM did not shut down gracefully; forcing stop...")
        run_command(["virsh", "destroy", vm_name], check=False)
        print_success(f"VM '{vm_name}' forcefully stopped")
    except Exception as e:
        spinner.stop()
        print_error(f"Error stopping VM '{vm_name}': {e}")


def delete_vm() -> None:
    """Delete an existing VM and its associated storage."""
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return
    confirm = input(
        f"{Colors.PROMPT}Are you sure you want to delete VM '{vm_name}'? (y/n): {Colors.ENDC} "
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
            spinner = Spinner("Waiting for VM shutdown")
            spinner.start()
            time.sleep(5)
            spinner.stop()
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "running" in output.lower():
                print_warning("Forcing VM off...")
                run_command(["virsh", "destroy", vm_name], check=False)
        print_info(f"Deleting VM '{vm_name}' and its storage...")
        spinner = Spinner("Deleting VM")
        spinner.start()
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        spinner.stop()
        print_success(f"VM '{vm_name}' deleted successfully")
    except Exception as e:
        spinner.stop()
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
                    f"{Colors.FROST2}{key.strip()}:{Colors.ENDC} {Colors.SNOW_STORM1}{value.strip()}{Colors.ENDC}"
                )

        print_section("Network Information")
        net_output = run_command(
            ["virsh", "domifaddr", vm_name], capture_output=True, check=False
        )
        if net_output and "failed" not in net_output.lower():
            print(f"{Colors.SNOW_STORM1}{net_output}{Colors.ENDC}")
        else:
            print_info("No network information available")

        print_section("Snapshots")
        snapshots = get_vm_snapshots(vm_name)
        print(
            f"{Colors.FROST2}Total snapshots:{Colors.ENDC} {Colors.SNOW_STORM1}{len(snapshots)}{Colors.ENDC}"
        )
        if snapshots:
            for idx, snap in enumerate(snapshots, 1):
                print(
                    f"  {Colors.DETAIL}{idx}.{Colors.ENDC} {Colors.SNOW_STORM1}{snap['name']}{Colors.ENDC} ({Colors.FROST1}{snap['creation_time']}{Colors.ENDC})"
                )

        print_section("Storage Devices")
        storage_output = run_command(
            ["virsh", "domblklist", vm_name], capture_output=True
        )
        if "Target     Source" in storage_output:
            lines = storage_output.splitlines()
            print(f"{Colors.FROST3}{lines[0]}{Colors.ENDC}")
            print(f"{Colors.FROST2}{lines[1]}{Colors.ENDC}")
            for line in lines[2:]:
                print(f"{Colors.SNOW_STORM1}{line}{Colors.ENDC}")
        else:
            print(f"{Colors.SNOW_STORM1}{storage_output}{Colors.ENDC}")
    except Exception as e:
        print_error(f"Error retrieving VM info: {e}")


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
            f"{Colors.PROMPT}Enter snapshot name (default: {default_snapshot}): {Colors.ENDC} "
        ).strip()
        or default_snapshot
    )
    description = input(
        f"{Colors.PROMPT}Enter snapshot description (optional): {Colors.ENDC} "
    ).strip()
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""
    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    spinner = Spinner(f"Creating snapshot '{snapshot_name}'")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)
        spinner.start()
        run_command(["virsh", "snapshot-create", vm_name, "--xmlfile", xml_path])
        spinner.stop()
        print_success(f"Snapshot '{snapshot_name}' created successfully")
    except Exception as e:
        spinner.stop()
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
            f"{Colors.PROMPT}Confirm revert of VM '{vm_name}' to snapshot '{snapshot_name}'? (y/n): {Colors.ENDC} "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print_info("Revert operation cancelled")
        return
    try:
        spinner = Spinner("Reverting to snapshot")
        spinner.start()
        run_command(["virsh", "snapshot-revert", vm_name, snapshot_name])
        spinner.stop()
        print_success(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully"
        )
        if (
            "running"
            in run_command(["virsh", "domstate", vm_name], capture_output=True).lower()
        ):
            restart = (
                input(f"{Colors.PROMPT}Restart VM now? (y/n): {Colors.ENDC} ")
                .strip()
                .lower()
            )
            if restart == "y":
                print_info(f"Starting VM '{vm_name}'...")
                run_command(["virsh", "start", vm_name])
                print_success(f"VM '{vm_name}' started")
    except Exception as e:
        spinner.stop()
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
            f"{Colors.PROMPT}Delete snapshot '{snapshot_name}' for VM '{vm_name}'? (y/n): {Colors.ENDC} "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print_info("Deletion cancelled")
        return
    try:
        spinner = Spinner(f"Deleting snapshot '{snapshot_name}'")
        spinner.start()
        run_command(["virsh", "snapshot-delete", vm_name, snapshot_name])
        spinner.stop()
        print_success(f"Snapshot '{snapshot_name}' deleted successfully")
    except Exception as e:
        spinner.stop()
        print_error(f"Failed to delete snapshot: {e}")


def delete_vm() -> None:
    """Delete a VM and its associated storage."""
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        return
    confirm = (
        input(
            f"{Colors.PROMPT}Confirm deletion of VM '{vm_name}'? (y/n): {Colors.ENDC} "
        )
        .strip()
        .lower()
    )
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
            spinner = Spinner("Waiting for shutdown")
            spinner.start()
            time.sleep(5)
            spinner.stop()
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "running" in output.lower():
                print_warning("Forcing VM shutdown...")
                run_command(["virsh", "destroy", vm_name], check=False)
        print_info(f"Deleting VM '{vm_name}' and storage...")
        spinner = Spinner("Deleting VM")
        spinner.start()
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])
        spinner.stop()
        print_success(f"VM '{vm_name}' deleted successfully")
    except Exception as e:
        spinner.stop()
        print_error(f"Error deleting VM '{vm_name}': {e}")


def show_vm_info() -> None:
    """Display detailed information about a VM."""
    print_header("VM Information")
    vm_name = select_vm("Select a VM to view info (or 'q' to cancel): ")
    if not vm_name:
        return
    try:
        print_section("Basic Information")
        output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                print(
                    f"{Colors.FROST2}{key.strip()}:{Colors.ENDC} {Colors.SNOW_STORM1}{value.strip()}{Colors.ENDC}"
                )
        print_section("Network Information")
        net_output = run_command(
            ["virsh", "domifaddr", vm_name], capture_output=True, check=False
        )
        if net_output and "failed" not in net_output.lower():
            print(f"{Colors.SNOW_STORM1}{net_output}{Colors.ENDC}")
        else:
            print_info("No network info available")
        print_section("Snapshots")
        snapshots = get_vm_snapshots(vm_name)
        print(
            f"{Colors.FROST2}Total snapshots:{Colors.ENDC} {Colors.SNOW_STORM1}{len(snapshots)}{Colors.ENDC}"
        )
        if snapshots:
            for idx, snap in enumerate(snapshots, 1):
                print(
                    f"  {Colors.DETAIL}{idx}.{Colors.ENDC} {Colors.SNOW_STORM1}{snap['name']}{Colors.ENDC} ({Colors.FROST1}{snap['creation_time']}{Colors.ENDC})"
                )
        print_section("Storage Devices")
        storage_output = run_command(
            ["virsh", "domblklist", vm_name], capture_output=True
        )
        if "Target     Source" in storage_output:
            lines = storage_output.splitlines()
            print(f"{Colors.FROST3}{lines[0]}{Colors.ENDC}")
            print(f"{Colors.FROST2}{lines[1]}{Colors.ENDC}")
            for line in lines[2:]:
                print(f"{Colors.SNOW_STORM1}{line}{Colors.ENDC}")
        else:
            print(f"{Colors.SNOW_STORM1}{storage_output}{Colors.ENDC}")
    except Exception as e:
        print_error(f"Error retrieving VM info: {e}")


# ------------------------------
# Interactive Menu
# ------------------------------
def interactive_menu() -> None:
    """Display the interactive VM management menu."""
    while True:
        print_header("VM Manager")
        console.print(f"[{Colors.SNOW_STORM1}]1. List VMs")
        console.print(f"[{Colors.SNOW_STORM1}]2. Create VM")
        console.print(f"[{Colors.SNOW_STORM1}]3. Start VM")
        console.print(f"[{Colors.SNOW_STORM1}]4. Stop VM")
        console.print(f"[{Colors.SNOW_STORM1}]5. Delete VM")
        console.print(f"[{Colors.SNOW_STORM1}]6. Show VM Info")
        console.print(f"[{Colors.SNOW_STORM1}]7. Snapshot Management")
        console.print(f"[{Colors.SNOW_STORM1}]8. Exit[{Colors.ENDC}]")
        choice = input(f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC} ").strip()
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
            while True:
                print_header("Snapshot Management")
                console.print(f"[{Colors.SNOW_STORM1}]1. List Snapshots")
                console.print(f"[{Colors.SNOW_STORM1}]2. Create Snapshot")
                console.print(f"[{Colors.SNOW_STORM1}]3. Revert to Snapshot")
                console.print(f"[{Colors.SNOW_STORM1}]4. Delete Snapshot")
                console.print(
                    f"[{Colors.SNOW_STORM1}]5. Return to Main Menu[{Colors.ENDC}]"
                )
                snap_choice = input(
                    f"\n{Colors.PROMPT}Enter your choice: {Colors.ENDC} "
                ).strip()
                if snap_choice == "1":
                    list_vm_snapshots()  # This function should be similar to select_snapshot but list all snapshots
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
                input(f"\n{Colors.PROMPT}Press Enter to continue...{Colors.ENDC}")
        elif choice == "8":
            print_info("Exiting VM Manager. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again.")
        input(f"\n{Colors.PROMPT}Press Enter to continue...{Colors.ENDC}")


# ------------------------------
# CLI Argument Parsing with Click
# ------------------------------
@click.group()
def cli() -> None:
    """Enhanced VM Manager: Manage VMs via libvirt."""
    print_header("Enhanced VM Manager v1.0.0")
    console.print(f"Hostname: [bold {Colors.INFO}]{HOSTNAME}[/{Colors.INFO}]")
    console.print(
        f"Date: [bold {Colors.INFO}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/{Colors.INFO}]"
    )
    if not check_root():
        sys.exit(1)
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    if not check_dependencies():
        logging.error("Missing critical dependencies")
        sys.exit(1)


@cli.command()
def list() -> None:
    """List all virtual machines."""
    list_vms()


@cli.command()
def create() -> None:
    """Create a new virtual machine."""
    create_vm()


@cli.command()
@click.option("--vm", help="Name of the VM to start")
def start(vm: Optional[str]) -> None:
    """Start a virtual machine."""
    if vm:
        try:
            output = run_command(
                ["virsh", "domstate", vm], capture_output=True, check=False
            )
            if "running" in output.lower():
                print_warning(f"VM '{vm}' is already running")
                sys.exit(0)
            ensure_default_network()
            print_info(f"Starting VM '{vm}'...")
            run_command(["virsh", "start", vm])
            print_success(f"VM '{vm}' started successfully")
        except Exception as e:
            print_error(f"Error starting VM '{vm}': {e}")
            sys.exit(1)
    else:
        start_vm()


@cli.command()
@click.option("--vm", help="Name of the VM to stop")
def stop(vm: Optional[str]) -> None:
    """Stop a virtual machine."""
    if vm:
        try:
            output = run_command(
                ["virsh", "domstate", vm], capture_output=True, check=False
            )
            if "shut off" in output.lower():
                print_warning(f"VM '{vm}' is already stopped")
                sys.exit(0)
            print_info(f"Shutting down VM '{vm}'...")
            run_command(["virsh", "shutdown", vm])
            print_success(f"Shutdown signal sent to VM '{vm}'")
        except Exception as e:
            print_error(f"Error stopping VM '{vm}': {e}")
            sys.exit(1)
    else:
        stop_vm()


@cli.command()
@click.option("--vm", help="Name of the VM to delete")
def delete(vm: Optional[str]) -> None:
    """Delete a virtual machine."""
    if vm:
        confirm = (
            input(
                f"{Colors.PROMPT}Confirm deletion of VM '{vm}'? (y/n): {Colors.ENDC} "
            )
            .strip()
            .lower()
        )
        if confirm == "y":
            try:
                run_command(["virsh", "destroy", vm], check=False)
                run_command(["virsh", "undefine", vm, "--remove-all-storage"])
                print_success(f"VM '{vm}' deleted successfully")
            except Exception as e:
                print_error(f"Error deleting VM '{vm}': {e}")
                sys.exit(1)
        else:
            print_info("Deletion cancelled")
    else:
        delete_vm()


@cli.command()
@click.option("--vm", help="Name of the VM to display info for")
def info(vm: Optional[str]) -> None:
    """Display detailed information for a virtual machine."""
    if vm:
        try:
            output = run_command(["virsh", "dominfo", vm], capture_output=True)
            print_section("Basic VM Information")
            for line in output.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    print(
                        f"{Colors.FROST2}{key.strip()}:{Colors.ENDC} {Colors.SNOW_STORM1}{value.strip()}{Colors.ENDC}"
                    )
            snapshots = get_vm_snapshots(vm)
            print_section("Snapshots")
            print(
                f"{Colors.FROST2}Total snapshots:{Colors.ENDC} {Colors.SNOW_STORM1}{len(snapshots)}{Colors.ENDC}"
            )
        except Exception as e:
            print_error(f"Error retrieving info for VM '{vm}': {e}")
            sys.exit(1)
    else:
        show_vm_info()


@cli.group()
def snapshot() -> None:
    """Manage VM snapshots."""
    pass


@snapshot.command("list")
@click.option("--vm", help="Name of the VM to list snapshots for")
def list_snapshots(vm: Optional[str]) -> None:
    """List snapshots for a VM."""
    if vm:
        list_vm_snapshots(vm)
    else:
        list_vm_snapshots()


@snapshot.command("create")
@click.option("--vm", required=True, help="Name of the VM to snapshot")
@click.option("--snapshot", help="Snapshot name (optional)")
def create_snap(vm: str, snapshot: Optional[str]) -> None:
    """Create a snapshot for a VM."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_name = snapshot or f"{vm}-snap-{timestamp}"
    description = f"Snapshot created on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""
    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)
        print_info(f"Creating snapshot '{snapshot_name}' for VM '{vm}'...")
        run_command(["virsh", "snapshot-create", vm, "--xmlfile", xml_path])
        print_success(f"Snapshot '{snapshot_name}' created successfully")
    except Exception as e:
        print_error(f"Failed to create snapshot: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(xml_path):
            os.unlink(xml_path)


@snapshot.command("revert")
@click.option("--vm", required=True, help="Name of the VM")
@click.option("--snapshot", required=True, help="Snapshot name to revert to")
def revert_snap(vm: str, snapshot: str) -> None:
    """Revert a VM to a specified snapshot."""
    confirm = (
        input(
            f"{Colors.PROMPT}Confirm revert of VM '{vm}' to snapshot '{snapshot}'? (y/n): {Colors.ENDC} "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print_info("Revert cancelled")
        return
    try:
        print_info(f"Reverting VM '{vm}' to snapshot '{snapshot}'...")
        run_command(["virsh", "snapshot-revert", vm, snapshot])
        print_success(f"VM '{vm}' reverted to snapshot '{snapshot}' successfully")
        restart = (
            input(f"{Colors.PROMPT}Restart VM now? (y/n): {Colors.ENDC} ")
            .strip()
            .lower()
        )
        if restart == "y":
            print_info(f"Starting VM '{vm}'...")
            run_command(["virsh", "start", vm])
            print_success(f"VM '{vm}' started")
    except Exception as e:
        print_error(f"Failed to revert snapshot: {e}")
        sys.exit(1)


@snapshot.command("delete")
@click.option("--vm", required=True, help="Name of the VM")
@click.option("--snapshot", required=True, help="Snapshot name to delete")
def delete_snap(vm: str, snapshot: str) -> None:
    """Delete a VM snapshot."""
    confirm = (
        input(
            f"{Colors.PROMPT}Confirm deletion of snapshot '{snapshot}' for VM '{vm}'? (y/n): {Colors.ENDC} "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print_info("Deletion cancelled")
        return
    try:
        print_info(f"Deleting snapshot '{snapshot}' for VM '{vm}'...")
        run_command(["virsh", "snapshot-delete", vm, snapshot])
        print_success(f"Snapshot '{snapshot}' deleted successfully")
    except Exception as e:
        print_error(f"Failed to delete snapshot: {e}")
        sys.exit(1)


@cli.command()
def interactive() -> None:
    """Launch interactive VM management mode."""
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    try:
        cli()
    except Exception as e:
        print_error(f"Unhandled exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
