#!/usr/bin/env python3
"""
Script Name: vm_manager.py
--------------------------------------------------------
Description:
  A production-ready Ubuntu/Linux VM manager that can list, create, start, stop,
  pause, resume, and delete VMs (along with their disk images), monitor resource usage,
  connect to the console, and manage snapshots. Uses the Nord color theme for
  visually engaging output with robust error handling, logging, and progress feedback.

Usage:
  sudo ./vm_manager.py

Author: Your Name | License: MIT | Version: 5.0.0
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
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union, Any

# Rich library imports for enhanced terminal output
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
)

# ------------------------------------------------------------------------------
# ENVIRONMENT CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/vm_manager.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Directories for VM images and ISOs
VM_IMAGE_DIR = "/var/lib/libvirt/images"
ISO_DIR = "/var/lib/libvirt/boot"

# Default sizes and resources
DEFAULT_VCPUS = 2
DEFAULT_RAM_MB = 2048
DEFAULT_DISK_GB = 20
DEFAULT_OS_VARIANT = "ubuntu22.04"  # Updated from 20.04

# VM Status
VM_STATUS = {
    "running": "Running",
    "paused": "Paused",
    "shut off": "Stopped",
    "crashed": "Crashed",
    "pmsuspended": "Suspended",
}

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

# ------------------------------------------------------------------------------
# SETUP RICH CONSOLE
# ------------------------------------------------------------------------------
console = Console()


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom formatter that applies Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging() -> logging.Logger:
    """
    Set up logging with console and file handlers using the Nord color theme.

    Returns:
        logging.Logger: Configured logger instance
    """
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()

    # Set log level from environment or default to INFO
    try:
        logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL))
    except AttributeError:
        logger.setLevel(logging.INFO)
        logger.warning(f"Invalid log level '{DEFAULT_LOG_LEVEL}', using INFO")

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colored output
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler for persistent logging
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        # Rotate log file if it's over 10MB
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logger.info(f"Rotated previous log to {backup_log}")

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)  # Secure the log file
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

    return logger


def print_section(title: str) -> None:
    """
    Print a section header with Nord-themed styling.

    Args:
        title: The title to display in the section header
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


def format_nord(text: str, color_code: str) -> str:
    """
    Format text with Nord color if colors are enabled.

    Args:
        text: Text to format
        color_code: Nord color code to apply

    Returns:
        Formatted text string
    """
    if DISABLE_COLORS:
        return text
    return f"{color_code}{text}{NC}"


# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs) -> Any:
    """
    Run a blocking function in a background thread while displaying a progress spinner.

    Args:
        description: Description to display in the progress indicator
        func: The function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        The return value from the executed function
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            try:
                return future.result()
            except Exception as e:
                logging.error(f"Error in background task: {e}")
                raise


def download_file(
    url: str, output_path: str, description: str = "Downloading ISO..."
) -> str:
    """
    Download a file from a URL with a progress bar.

    Args:
        url: URL to download from
        output_path: Path to save the downloaded file
        description: Progress bar description

    Returns:
        The output path if successful

    Raises:
        Exception: If download fails
    """
    try:
        with urllib.request.urlopen(url) as response:
            total = int(response.getheader("Content-Length", 0))
            chunk_size = 8192
            with (
                open(output_path, "wb") as f,
                Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                ) as progress,
            ):
                task = progress.add_task(description, total=total)
                downloaded = 0
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(task, completed=downloaded)

        # Verify file exists and is not empty
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ValueError("Downloaded file is empty or does not exist")

        return output_path
    except Exception as e:
        logging.error(f"Download failed: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logging.info(f"Removed incomplete download: {output_path}")
            except Exception:
                pass
        raise


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    """
    Handle termination signals gracefully.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
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


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup() -> None:
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Add any cleanup tasks here (e.g., removing temporary files)
    temp_dir = os.path.join(tempfile.gettempdir(), "vm_manager")
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logging.debug(f"Removed temporary directory: {temp_dir}")
        except Exception as e:
            logging.warning(f"Failed to remove temporary directory: {e}")


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies() -> bool:
    """
    Check for required commands and libraries.

    Returns:
        True if all dependencies are available, False otherwise
    """
    required_commands = ["virsh", "virt-install", "qemu-img", "wget"]
    missing = []

    for cmd in required_commands:
        if not shutil.which(cmd):
            missing.append(cmd)

    if missing:
        logging.error(f"Missing dependencies: {', '.join(missing)}")
        logging.error("Please install the required packages and try again.")
        if "virsh" in missing or "virt-install" in missing:
            logging.error(
                "For virt tools: sudo apt install libvirt-clients libvirt-daemon-system virtinst"
            )
        if "qemu-img" in missing:
            logging.error("For qemu-img: sudo apt install qemu-utils")
        return False

    # Check libvirt service status
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "libvirtd"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning("libvirtd service may not be running.")
        logging.warning("Run: sudo systemctl start libvirtd")

    # Check libvirt version
    try:
        result = subprocess.run(
            ["virsh", "--version"], capture_output=True, text=True, check=True
        )
        logging.info(f"Using libvirt version: {result.stdout.strip()}")
    except Exception:
        logging.warning("Could not determine libvirt version")

    return True


def check_root() -> bool:
    """
    Ensure the script is run with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root (sudo).")
        return False
    logging.debug("Running with root privileges.")
    return True


def clear_screen() -> None:
    """
    Clear the terminal screen.
    """
    os.system("clear")


def prompt_enter() -> None:
    """
    Prompt the user to press Enter to continue.
    """
    input(format_nord("Press Enter to continue...", NORD8))


def print_header(title="Advanced VM Manager Tool") -> None:
    """
    Print a header with the given title.

    Args:
        title: Title to display in the header
    """
    clear_screen()
    print_section(title)


# ------------------------------------------------------------------------------
# COMMAND EXECUTION HELPER
# ------------------------------------------------------------------------------
def run_command(
    command: list, capture_output: bool = False, check: bool = True, timeout: int = 60
) -> Union[str, bool]:
    """
    Execute a shell command with timeout and error handling.

    Args:
        command: Command to execute as a list of strings
        capture_output: Whether to capture and return standard output
        check: Whether to check the return code
        timeout: Command timeout in seconds

    Returns:
        Command output if capture_output=True, otherwise True on success

    Raises:
        Exception: If command fails and check=True
    """
    logging.debug(f"Running command: {' '.join(command)}")
    try:
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
        logging.error(f"Command timed out after {timeout} seconds: {' '.join(command)}")
        return False
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Command '{' '.join(command)}' failed: {error_msg}")
        if check:
            raise
        return False


# ------------------------------------------------------------------------------
# VM LISTING & SELECTION
# ------------------------------------------------------------------------------
def get_vm_list() -> List[Dict[str, str]]:
    """
    Retrieve a list of VMs by parsing the output of 'virsh list --all'.

    Returns:
        A list of dictionaries with keys: 'id', 'name', and 'state'
    """
    try:
        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        if output:
            lines = output.strip().splitlines()
            # Find separator line
            sep_index = None
            for i, line in enumerate(lines):
                if line.lstrip().startswith("---"):
                    sep_index = i + 1
                    break

            if sep_index is None:
                logging.error("Unexpected output format from 'virsh list'.")
                return []

            # Parse VM data
            for line in lines[sep_index:]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    vm_id = parts[0]
                    vm_name = parts[1]
                    vm_state = " ".join(parts[2:]) if len(parts) > 2 else ""
                    vms.append({"id": vm_id, "name": vm_name, "state": vm_state})
        return vms
    except Exception as e:
        logging.error(f"Failed to get VM list: {e}")
        return []


def show_vm_list() -> None:
    """
    Display a formatted table of all VMs with their states.
    """
    vms = get_vm_list()
    if not vms:
        console.print("[bold red]No VMs found.[/bold red]")
        return

    # Create and display a rich table
    table = Table(title="Virtual Machines")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("State", style="yellow")

    for vm in vms:
        state_style = "green" if vm["state"] == "running" else "yellow"
        table.add_row(
            vm["id"], vm["name"], f"[{state_style}]{vm['state']}[/{state_style}]"
        )

    console.print(table)


def select_vm(prompt_text="Select a VM by number: ") -> Optional[str]:
    """
    Display a numbered list of VMs and prompt the user to select one.

    Args:
        prompt_text: Text to show when prompting for selection

    Returns:
        The selected VM's name or None if no VMs are available
    """
    vms = get_vm_list()
    if not vms:
        console.print("[bold red]No VMs found.[/bold red]")
        return None

    print_header("Virtual Machines")
    for i, vm in enumerate(vms, start=1):
        state_color = NORD14 if vm["state"] == "running" else NORD13
        print(
            f"{format_nord(f'[{i}]', NORD10)} {vm['name']} - {format_nord(vm['state'], state_color)}"
        )

    while True:
        choice = input(format_nord(prompt_text, NORD8)).strip()
        if choice.lower() == "q":
            return None

        try:
            index = int(choice) - 1
            if 0 <= index < len(vms):
                return vms[index]["name"]
            else:
                print(
                    format_nord(
                        "Invalid selection. Please enter a valid number or 'q' to cancel.",
                        NORD11,
                    )
                )
        except ValueError:
            print(format_nord("Please enter a valid number or 'q' to cancel.", NORD11))


def get_vm_info(vm_name: str) -> Dict[str, str]:
    """
    Get detailed information about a VM.

    Args:
        vm_name: Name of the VM

    Returns:
        Dictionary with VM information
    """
    try:
        output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
        info = {}
        if output:
            for line in output.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    info[key.strip()] = value.strip()
        return info
    except Exception as e:
        logging.error(f"Failed to get VM info for '{vm_name}': {e}")
        return {}


def get_vm_state(vm_name: str) -> str:
    """
    Get the current state of a VM.

    Args:
        vm_name: Name of the VM

    Returns:
        The VM state as a string
    """
    try:
        info = get_vm_info(vm_name)
        return info.get("State", "unknown")
    except Exception:
        return "unknown"


# ------------------------------------------------------------------------------
# ISO SELECTION & DOWNLOAD
# ------------------------------------------------------------------------------
def list_isos() -> List[str]:
    """
    List all ISO files in the ISO directory.

    Returns:
        List of ISO filenames
    """
    try:
        isos = [
            iso
            for iso in os.listdir(ISO_DIR)
            if os.path.isfile(os.path.join(ISO_DIR, iso))
            and iso.lower().endswith(".iso")
        ]
        return sorted(isos)
    except Exception as e:
        logging.error(f"Error listing ISOs: {e}")
        return []


def select_iso() -> Optional[str]:
    """
    Allow the user to select an ISO file from the ISO directory or enter a custom path.

    Returns:
        The full path to the selected ISO or None if cancelled
    """
    print_header("Select Installation ISO")
    available_isos = list_isos()

    if available_isos:
        print("Available ISO files:")
        for i, iso in enumerate(available_isos, start=1):
            print(f"{format_nord(f'[{i}]', NORD14)} {iso}")
        print(f"{format_nord('[0]', NORD14)} Enter a custom ISO path")
        print(f"{format_nord('[d]', NORD14)} Download a new ISO")
        print(f"{format_nord('[q]', NORD14)} Cancel")

        while True:
            choice = input(format_nord("Select an option: ", NORD8)).strip().lower()
            if choice == "q":
                return None

            elif choice == "d":
                return download_iso()

            else:
                try:
                    index = int(choice)
                    if index == 0:
                        custom_path = input(
                            format_nord("Enter the full path to the ISO file: ", NORD8)
                        ).strip()
                        if os.path.isfile(custom_path):
                            return custom_path
                        else:
                            print(
                                format_nord("File not found. Please try again.", NORD11)
                            )
                    elif 1 <= index <= len(available_isos):
                        return os.path.join(ISO_DIR, available_isos[index - 1])
                    else:
                        print(
                            format_nord("Invalid selection, please try again.", NORD11)
                        )
                except ValueError:
                    print(format_nord("Please enter a valid number.", NORD11))
    else:
        print(format_nord("No ISO files found in the ISO directory.", NORD13))
        print(f"{format_nord('[1]', NORD14)} Enter a custom ISO path")
        print(f"{format_nord('[2]', NORD14)} Download a new ISO")
        print(f"{format_nord('[q]', NORD14)} Cancel")

        while True:
            choice = input(format_nord("Select an option: ", NORD8)).strip().lower()
            if choice == "q":
                return None
            elif choice == "1":
                custom_path = input(
                    format_nord("Enter the full path to the ISO file: ", NORD8)
                ).strip()
                if os.path.isfile(custom_path):
                    return custom_path
                else:
                    print(format_nord("File not found. Please try again.", NORD11))
            elif choice == "2":
                return download_iso()
            else:
                print(format_nord("Invalid selection, please try again.", NORD11))


def download_iso() -> Optional[str]:
    """
    Download an ISO file from a user-provided URL.

    Returns:
        The path to the downloaded ISO file or None if the download fails
    """
    print_header("Download ISO")

    # Common distro URLs
    distros = {
        "1": {
            "name": "Ubuntu 22.04 LTS Desktop",
            "url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.3-desktop-amd64.iso",
            "filename": "ubuntu-22.04.3-desktop-amd64.iso",
        },
        "2": {
            "name": "Ubuntu 22.04 LTS Server",
            "url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.3-live-server-amd64.iso",
            "filename": "ubuntu-22.04.3-live-server-amd64.iso",
        },
        "3": {
            "name": "Debian 12",
            "url": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.4.0-amd64-netinst.iso",
            "filename": "debian-12.4.0-amd64-netinst.iso",
        },
        "4": {"name": "Custom URL", "url": "", "filename": ""},
    }

    # Display distro options
    print("Select a distribution to download:")
    for key, distro in distros.items():
        print(f"{format_nord(f'[{key}]', NORD14)} {distro['name']}")
    print(f"{format_nord('[q]', NORD14)} Cancel")

    choice = input(format_nord("Enter your choice: ", NORD8)).strip().lower()
    if choice == "q":
        return None

    if choice in distros:
        distro = distros[choice]
        if choice == "4":  # Custom URL
            iso_url = input(
                format_nord("Enter the URL for the installation ISO: ", NORD8)
            ).strip()
            iso_filename = input(
                format_nord("Enter the desired filename: ", NORD8)
            ).strip()
            if not iso_filename:
                # Extract filename from URL
                iso_filename = os.path.basename(iso_url)
                if not iso_filename:
                    iso_filename = "custom.iso"
        else:
            iso_url = distro["url"]
            iso_filename = distro["filename"]

        iso_path = os.path.join(ISO_DIR, iso_filename)
        if os.path.exists(iso_path):
            overwrite = (
                input(
                    format_nord(
                        f"File {iso_filename} already exists. Overwrite? (y/n): ",
                        NORD13,
                    )
                )
                .strip()
                .lower()
            )
            if overwrite != "y":
                return iso_path

        logging.info(f"Starting download of {iso_filename} from {iso_url}")
        try:
            # Create ISO directory if it doesn't exist
            os.makedirs(ISO_DIR, exist_ok=True)

            # Run download with progress bar
            download_file(iso_url, iso_path, f"Downloading {iso_filename}...")
            logging.info(f"ISO downloaded successfully to {iso_path}")
            return iso_path
        except Exception as e:
            logging.error(f"Failed to download ISO: {e}")
            return None
    else:
        print(format_nord("Invalid selection.", NORD11))
        return None


# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_vms():
    """
    List all virtual machines.
    """
    print_header("Current Virtual Machines")
    show_vm_list()
    prompt_enter()


def start_vm():
    """
    Start a virtual machine.
    """
    print_header("Start Virtual Machine")
    vm_name = select_vm("Select a VM to start by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state == "running":
        logging.warning(f"VM '{vm_name}' is already running.")
        prompt_enter()
        return

    logging.info(f"Starting VM '{vm_name}'...")
    try:
        result = run_with_progress(
            f"Starting VM '{vm_name}'...", run_command, ["virsh", "start", vm_name]
        )
        if result:
            logging.info(f"VM '{vm_name}' started successfully.")
        else:
            logging.error(f"Failed to start VM '{vm_name}'.")
    except Exception as e:
        logging.error(f"Error starting VM: {e}")

    prompt_enter()


def stop_vm():
    """
    Stop a virtual machine.
    """
    print_header("Stop Virtual Machine")
    vm_name = select_vm("Select a VM to stop by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state not in ["running", "paused"]:
        logging.warning(f"VM '{vm_name}' is not running.")
        prompt_enter()
        return

    # Ask for graceful or forced shutdown
    print(f"{format_nord('[1]', NORD14)} Graceful shutdown (recommended)")
    print(f"{format_nord('[2]', NORD14)} Force shutdown (may cause data loss)")
    shutdown_type = input(format_nord("Select shutdown type: ", NORD8)).strip()

    command = ["virsh", "shutdown", vm_name]
    if shutdown_type == "2":
        command = ["virsh", "destroy", vm_name]

    logging.info(f"Stopping VM '{vm_name}'...")
    try:
        result = run_with_progress(f"Stopping VM '{vm_name}'...", run_command, command)
        if result:
            logging.info(f"Shutdown signal sent to VM '{vm_name}'.")
        else:
            logging.error(f"Failed to shutdown VM '{vm_name}'.")
    except Exception as e:
        logging.error(f"Error stopping VM: {e}")

    prompt_enter()


def pause_vm():
    """
    Pause a virtual machine.
    """
    print_header("Pause Virtual Machine")
    vm_name = select_vm("Select a VM to pause by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state != "running":
        logging.warning(f"VM '{vm_name}' is not running.")
        prompt_enter()
        return

    logging.info(f"Pausing VM '{vm_name}'...")
    try:
        result = run_with_progress(
            f"Pausing VM '{vm_name}'...", run_command, ["virsh", "suspend", vm_name]
        )
        if result:
            logging.info(f"VM '{vm_name}' paused successfully.")
        else:
            logging.error(f"Failed to pause VM '{vm_name}'.")
    except Exception as e:
        logging.error(f"Error pausing VM: {e}")

    prompt_enter()


def resume_vm():
    """
    Resume a paused virtual machine.
    """
    print_header("Resume Virtual Machine")
    vm_name = select_vm("Select a VM to resume by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state != "paused":
        logging.warning(f"VM '{vm_name}' is not paused.")
        prompt_enter()
        return

    logging.info(f"Resuming VM '{vm_name}'...")
    try:
        result = run_with_progress(
            f"Resuming VM '{vm_name}'...", run_command, ["virsh", "resume", vm_name]
        )
        if result:
            logging.info(f"VM '{vm_name}' resumed successfully.")
        else:
            logging.error(f"Failed to resume VM '{vm_name}'.")
    except Exception as e:
        logging.error(f"Error resuming VM: {e}")

    prompt_enter()


def get_vm_disks(vm_name: str) -> List[str]:
    """
    Retrieve disk paths for a VM from its XML definition.

    Args:
        vm_name: Name of the VM

    Returns:
        List of disk paths used by the VM
    """
    try:
        xml_output = run_command(["virsh", "dumpxml", vm_name], capture_output=True)
        disk_paths = []
        if xml_output:
            # Use regex to find all disk paths
            matches = re.findall(r'source file=[\'"]([^\'"]+)[\'"]', xml_output)
            disk_paths.extend(matches)
        return disk_paths
    except Exception as e:
        logging.error(f"Failed to get disk paths for VM '{vm_name}': {e}")
        return []


def delete_vm():
    """
    Delete a virtual machine and its associated disk images.
    """
    print_header("Delete Virtual Machine")
    vm_name = select_vm("Select a VM to delete by number: ")
    if not vm_name:
        return

    # Get disk information for confirmation
    disk_paths = get_vm_disks(vm_name)
    disk_info = (
        "\n  ".join([f"- {d}" for d in disk_paths]) if disk_paths else "No disks found"
    )

    # Confirmation
    print(f"\nVM: {format_nord(vm_name, NORD14)}")
    print(f"Disk images that will be deleted:\n  {disk_info}")
    confirm = (
        input(
            format_nord(
                f"\nAre you sure you want to delete VM '{vm_name}' and its disk images? This action cannot be undone. (y/n): ",
                NORD13,
            )
        )
        .strip()
        .lower()
    )

    if confirm != "y":
        logging.warning("Deletion cancelled.")
        prompt_enter()
        return

    # Force shutdown if VM is running
    state = get_vm_state(vm_name)
    if state in ["running", "paused"]:
        logging.info(f"Force stopping VM '{vm_name}' before deletion...")
        run_command(["virsh", "destroy", vm_name], check=False)

    # Undefine the VM
    try:
        result = run_with_progress(
            f"Removing VM '{vm_name}'...",
            run_command,
            ["virsh", "undefine", vm_name, "--remove-all-storage"],
        )
        if result:
            logging.info(f"VM '{vm_name}' deleted successfully with all storage.")
        else:
            # Fallback to manual disk deletion if --remove-all-storage fails
            logging.warning(
                "Could not remove storage automatically. Trying manual deletion."
            )
            if run_command(["virsh", "undefine", vm_name]):
                logging.info(f"VM '{vm_name}' undefined successfully.")
                successful_deletions = 0
                for disk in disk_paths:
                    try:
                        if os.path.exists(disk):
                            os.remove(disk)
                            logging.info(f"Disk image '{disk}' removed successfully.")
                            successful_deletions += 1
                    except Exception as e:
                        logging.warning(f"Failed to remove disk image '{disk}': {e}")

                if successful_deletions == len(disk_paths):
                    logging.info("All disk images removed successfully.")
                elif disk_paths:
                    logging.warning(
                        f"Deleted {successful_deletions} of {len(disk_paths)} disk images."
                    )
                else:
                    logging.warning("No associated disk images found to remove.")
            else:
                logging.error(f"Failed to delete VM '{vm_name}'.")
    except Exception as e:
        logging.error(f"Error during VM deletion: {e}")

    prompt_enter()


def monitor_vm():
    """
    Monitor virtual machine resources in real-time.
    """
    print_header("Monitor Virtual Machine Resources")
    vm_name = select_vm("Select a VM to monitor by number: ")
    if not vm_name:
        return

    logging.info(f"Monitoring VM '{vm_name}'. Press Ctrl+C to exit.")
    try:
        while True:
            clear_screen()
            print(
                f"{format_nord('Monitoring VM:', NORD10)} {format_nord(vm_name, NORD14)}"
            )
            print(format_nord("-" * 60, NORD10))

            # Get VM basic info
            output = run_command(["virsh", "dominfo", vm_name], capture_output=True)
            if output:
                print(output)

            # Get VM CPU and memory stats
            stats_output = run_command(
                ["virsh", "domstats", vm_name, "--stats", "cpu", "--stats", "balloon"],
                capture_output=True,
                check=False,
            )
            if stats_output:
                print("\nResource Statistics:")
                print(stats_output)

            print(format_nord("-" * 60, NORD10))
            print("Press Ctrl+C to exit monitoring mode")
            time.sleep(3)
    except KeyboardInterrupt:
        logging.info("Exiting monitor mode.")
    except Exception as e:
        logging.error(f"Error in monitoring: {e}")

    prompt_enter()


def remote_console():
    """
    Connect to the console of a virtual machine.
    """
    print_header("Remote Console Access")
    vm_name = select_vm("Select a VM for console access by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state != "running":
        print(format_nord(f"VM '{vm_name}' is not running. Start it first.", NORD13))
        start_vm_first = (
            input(format_nord("Do you want to start the VM now? (y/n): ", NORD8))
            .strip()
            .lower()
        )
        if start_vm_first == "y":
            run_command(["virsh", "start", vm_name], check=False)
        else:
            prompt_enter()
            return

    logging.info(f"Connecting to console of VM '{vm_name}'. Press Ctrl+] to exit.")
    print(
        format_nord(
            "IMPORTANT: To exit the console, press Ctrl+] (right bracket)", NORD13
        )
    )
    try:
        # Small delay to ensure message is read
        time.sleep(2)
        # Connect to console
        subprocess.run(["virsh", "console", vm_name])
    except Exception as e:
        logging.error(f"Failed to connect to console: {e}")

    prompt_enter()


def show_isos():
    """
    List available ISO files in the ISO directory.
    """
    print_header("Available ISO Files")
    isos = list_isos()

    if not isos:
        print(format_nord("No ISO files found in the ISO directory.", NORD13))
    else:
        for i, iso in enumerate(isos, start=1):
            iso_size = os.path.getsize(os.path.join(ISO_DIR, iso))
            iso_size_str = f"{iso_size / (1024 * 1024):.1f} MB"
            print(f"{i}. {iso} ({iso_size_str})")

    print(f"\nISO Directory: {ISO_DIR}")
    print(f"Total ISOs: {len(isos)}")

    prompt_enter()


def generate_unique_vm_name(base_name: str) -> str:
    """
    Generate a unique VM name by appending a number if needed.

    Args:
        base_name: The desired base name

    Returns:
        A unique VM name
    """
    vms = get_vm_list()
    existing_names = [vm["name"] for vm in vms]

    if base_name not in existing_names:
        return base_name

    counter = 1
    while f"{base_name}-{counter}" in existing_names:
        counter += 1

    return f"{base_name}-{counter}"


def create_vm():
    """
    Create a new virtual machine with specified parameters.
    """
    print_header("Create a New Virtual Machine")

    # Get VM name
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name_input = input(
        format_nord(f"Enter VM name (default: {default_name}): ", NORD8)
    ).strip()
    vm_name = vm_name_input if vm_name_input else default_name
    vm_name = generate_unique_vm_name(vm_name)

    # Get VM resource specifications
    try:
        vcpus_input = input(
            format_nord(f"Enter number of vCPUs (default: {DEFAULT_VCPUS}): ", NORD8)
        ).strip()
        vcpus = int(vcpus_input) if vcpus_input else DEFAULT_VCPUS

        ram_input = input(
            format_nord(f"Enter RAM in MB (default: {DEFAULT_RAM_MB}): ", NORD8)
        ).strip()
        ram = int(ram_input) if ram_input else DEFAULT_RAM_MB

        disk_input = input(
            format_nord(f"Enter disk size in GB (default: {DEFAULT_DISK_GB}): ", NORD8)
        ).strip()
        disk_size = int(disk_input) if disk_input else DEFAULT_DISK_GB
    except ValueError:
        logging.error("Invalid input. vCPUs, RAM, and disk size must be numeric.")
        prompt_enter()
        return

    # Ensure minimum values
    if vcpus < 1 or ram < 512 or disk_size < 1:
        logging.error(
            "Invalid resource specifications. Minimum requirements: 1 vCPU, 512 MB RAM, 1 GB disk."
        )
        prompt_enter()
        return

    # Prepare disk path
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        logging.error(
            f"Disk image {disk_image} already exists. Choose a different VM name."
        )
        prompt_enter()
        return

    # Get installation media
    print(f"{format_nord('Provide installation ISO:', NORD14)}")
    print(f"{format_nord('[1]', NORD10)} Use existing ISO file")
    print(f"{format_nord('[2]', NORD10)} Download ISO via URL")
    print(f"{format_nord('[q]', NORD10)} Cancel VM creation")

    iso_choice = input(format_nord("Enter your choice: ", NORD8)).strip().lower()
    iso_path = ""

    if iso_choice == "1":
        iso_path = select_iso()
        if not iso_path:
            logging.warning("VM creation cancelled.")
            prompt_enter()
            return
    elif iso_choice == "2":
        iso_path = download_iso()
        if not iso_path:
            logging.warning("VM creation cancelled.")
            prompt_enter()
            return
    elif iso_choice == "q":
        logging.warning("VM creation cancelled.")
        prompt_enter()
        return
    else:
        logging.warning("Invalid selection. VM creation cancelled.")
        prompt_enter()
        return

    # Create the disk image
    logging.info(f"Creating disk image of {disk_size}GB at {disk_image}...")
    try:
        result = run_with_progress(
            f"Creating disk image ({disk_size}GB)...",
            run_command,
            ["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"],
        )
        if not result:
            logging.error("Failed to create disk image.")
            prompt_enter()
            return
    except Exception as e:
        logging.error(f"Error creating disk image: {e}")
        # Clean up partial disk
        if os.path.exists(disk_image):
            try:
                os.remove(disk_image)
            except Exception:
                pass
        prompt_enter()
        return

    # Determine OS variant
    os_variant = DEFAULT_OS_VARIANT
    if "ubuntu" in os.path.basename(iso_path).lower():
        os_variant = "ubuntu22.04"
    elif "debian" in os.path.basename(iso_path).lower():
        os_variant = "debian11"

    # Create VM with virt-install
    logging.info("Starting VM installation using virt-install...")
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
        os_variant,
        "--network",
        "default",
        "--graphics",
        "vnc",
        "--noautoconsole",
    ]

    try:
        result = run_with_progress(
            "Creating and starting VM installation...",
            run_command,
            virt_install_cmd,
            timeout=120,
        )
        if result:
            logging.info(
                f"VM '{vm_name}' created successfully with installation started."
            )
            logging.info(
                f"Use option 7 (Remote Console Access) to complete the installation."
            )
        else:
            logging.error(f"Failed to create VM '{vm_name}'.")
            # Attempt to clean up
            run_command(
                ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
            )
    except Exception as e:
        logging.error(f"Error creating VM: {e}")
        # Attempt to clean up
        run_command(["virsh", "undefine", vm_name, "--remove-all-storage"], check=False)
        if os.path.exists(disk_image):
            try:
                os.remove(disk_image)
                logging.info(f"Removed incomplete disk image: {disk_image}")
            except Exception:
                pass

    prompt_enter()


# ------------------------------------------------------------------------------
# SNAPSHOT MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
def list_snapshots():
    """
    List snapshots for a selected virtual machine.
    """
    print_header("List Snapshots")
    vm_name = select_vm("Select a VM to list snapshots by number: ")
    if not vm_name:
        return

    try:
        output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
        if output:
            # Create a rich table for better display
            snapshot_lines = output.strip().splitlines()

            # Check if there are any snapshots
            if len(snapshot_lines) <= 2:
                print(format_nord(f"No snapshots found for VM '{vm_name}'.", NORD13))
            else:
                table = Table(title=f"Snapshots for {vm_name}")

                # Parse header
                header_parts = snapshot_lines[0].split()
                for part in header_parts:
                    table.add_column(part)

                # Parse snapshots
                for line in snapshot_lines[2:]:
                    if line.strip():
                        table.add_row(*line.split())

                console.print(table)
        else:
            logging.error("Failed to list snapshots.")
    except Exception as e:
        logging.error(f"Error listing snapshots: {e}")

    prompt_enter()


def create_snapshot():
    """
    Create a snapshot of a virtual machine.
    """
    print_header("Create Snapshot")
    vm_name = select_vm("Select a VM to snapshot by number: ")
    if not vm_name:
        return

    state = get_vm_state(vm_name)
    if state not in ["running", "paused", "shut off"]:
        logging.warning(f"VM is in state '{state}'. Cannot create snapshot.")
        prompt_enter()
        return

    # Generate default snapshot name
    default_name = f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    snapshot_name_input = input(
        format_nord(f"Enter snapshot name (default: {default_name}): ", NORD8)
    ).strip()
    snapshot_name = snapshot_name_input if snapshot_name_input else default_name

    description = input(
        format_nord("Enter snapshot description (optional): ", NORD8)
    ).strip()

    # Build command
    cmd = ["virsh", "snapshot-create-as", vm_name, snapshot_name]
    if description:
        cmd += ["--description", description]

    try:
        result = run_with_progress(
            f"Creating snapshot '{snapshot_name}'...", run_command, cmd
        )
        if result:
            logging.info(f"Snapshot '{snapshot_name}' created for VM '{vm_name}'.")
        else:
            logging.error("Failed to create snapshot.")
    except Exception as e:
        logging.error(f"Error creating snapshot: {e}")

    prompt_enter()


def revert_snapshot():
    """
    Revert a virtual machine to a specified snapshot.
    """
    print_header("Revert to Snapshot")
    vm_name = select_vm("Select a VM to revert snapshot by number: ")
    if not vm_name:
        return

    # Get list of snapshots
    try:
        output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
        if not output or len(output.strip().splitlines()) <= 2:
            logging.warning(f"No snapshots found for VM '{vm_name}'.")
            prompt_enter()
            return

        # Parse snapshots for selection
        snapshot_lines = output.strip().splitlines()[2:]  # Skip header and separator
        snapshots = []
        for line in snapshot_lines:
            if line.strip():
                parts = line.split()
                if parts:
                    snapshots.append(parts[0])  # First column is snapshot name

        if not snapshots:
            logging.warning(f"No snapshots found for VM '{vm_name}'.")
            prompt_enter()
            return

        # Display snapshots for selection
        print(f"Available snapshots for VM '{vm_name}':")
        for i, snapshot in enumerate(snapshots, start=1):
            print(f"{format_nord(f'[{i}]', NORD14)} {snapshot}")

        # Get user selection
        while True:
            choice = input(
                format_nord("Select a snapshot to revert to by number: ", NORD8)
            ).strip()
            try:
                index = int(choice) - 1
                if 0 <= index < len(snapshots):
                    snapshot_name = snapshots[index]
                    break
                else:
                    print(format_nord("Invalid selection. Please try again.", NORD11))
            except ValueError:
                print(format_nord("Please enter a valid number.", NORD11))

        # Confirm reversion
        print(
            format_nord(
                f"WARNING: Reverting to snapshot '{snapshot_name}' will discard all changes made after the snapshot.",
                NORD13,
            )
        )
        confirm = (
            input(format_nord("Are you sure you want to proceed? (y/n): ", NORD13))
            .strip()
            .lower()
        )
        if confirm != "y":
            logging.warning("Snapshot reversion cancelled.")
            prompt_enter()
            return

        # Perform the reversion
        result = run_with_progress(
            f"Reverting to snapshot '{snapshot_name}'...",
            run_command,
            ["virsh", "snapshot-revert", vm_name, snapshot_name],
        )
        if result:
            logging.info(f"VM '{vm_name}' reverted to snapshot '{snapshot_name}'.")
        else:
            logging.error(f"Failed to revert to snapshot '{snapshot_name}'.")
    except Exception as e:
        logging.error(f"Error during snapshot reversion: {e}")

    prompt_enter()


def delete_snapshot():
    """
    Delete a snapshot from a virtual machine.
    """
    print_header("Delete Snapshot")
    vm_name = select_vm("Select a VM to delete a snapshot by number: ")
    if not vm_name:
        return

    # Get list of snapshots
    try:
        output = run_command(["virsh", "snapshot-list", vm_name], capture_output=True)
        if not output or len(output.strip().splitlines()) <= 2:
            logging.warning(f"No snapshots found for VM '{vm_name}'.")
            prompt_enter()
            return

        # Parse snapshots for selection
        snapshot_lines = output.strip().splitlines()[2:]  # Skip header and separator
        snapshots = []
        for line in snapshot_lines:
            if line.strip():
                parts = line.split()
                if parts:
                    snapshots.append(parts[0])  # First column is snapshot name

        if not snapshots:
            logging.warning(f"No snapshots found for VM '{vm_name}'.")
            prompt_enter()
            return

        # Display snapshots for selection
        print(f"Available snapshots for VM '{vm_name}':")
        for i, snapshot in enumerate(snapshots, start=1):
            print(f"{format_nord(f'[{i}]', NORD14)} {snapshot}")

        # Get user selection
        while True:
            choice = input(
                format_nord("Select a snapshot to delete by number: ", NORD8)
            ).strip()
            try:
                index = int(choice) - 1
                if 0 <= index < len(snapshots):
                    snapshot_name = snapshots[index]
                    break
                else:
                    print(format_nord("Invalid selection. Please try again.", NORD11))
            except ValueError:
                print(format_nord("Please enter a valid number.", NORD11))

        # Confirm deletion
        confirm = (
            input(
                format_nord(
                    f"Are you sure you want to delete snapshot '{snapshot_name}'? (y/n): ",
                    NORD13,
                )
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            logging.warning("Snapshot deletion cancelled.")
            prompt_enter()
            return

        # Perform the deletion
        result = run_with_progress(
            f"Deleting snapshot '{snapshot_name}'...",
            run_command,
            ["virsh", "snapshot-delete", vm_name, snapshot_name],
        )
        if result:
            logging.info(f"Snapshot '{snapshot_name}' deleted from VM '{vm_name}'.")
        else:
            logging.error(f"Failed to delete snapshot '{snapshot_name}'.")
    except Exception as e:
        logging.error(f"Error during snapshot deletion: {e}")

    prompt_enter()


def snapshot_menu():
    """
    Display the snapshot management menu.
    """
    while True:
        print_header("Snapshot Management")
        print(f"{format_nord('[1]', NORD14)} List Snapshots")
        print(f"{format_nord('[2]', NORD14)} Create Snapshot")
        print(f"{format_nord('[3]', NORD14)} Revert to Snapshot")
        print(f"{format_nord('[4]', NORD14)} Delete Snapshot")
        print(f"{format_nord('[b]', NORD14)} Back to Main Menu")

        choice = input(format_nord("Enter your choice: ", NORD8)).strip().lower()
        if choice == "1":
            list_snapshots()
        elif choice == "2":
            create_snapshot()
        elif choice == "3":
            revert_snapshot()
        elif choice == "4":
            delete_snapshot()
        elif choice == "b":
            break
        else:
            console.print(
                "[bold yellow]Invalid selection. Please try again.[/bold yellow]"
            )
            time.sleep(1)


# ------------------------------------------------------------------------------
# DISK IMAGE MANAGEMENT
# ------------------------------------------------------------------------------
def get_all_disk_images() -> List[Tuple[str, int]]:
    """
    Get all disk images with their sizes.

    Returns:
        List of tuples containing (disk_name, size_in_bytes)
    """
    try:
        disks = []
        for filename in os.listdir(VM_IMAGE_DIR):
            if filename.endswith((".qcow2", ".img", ".raw")):
                full_path = os.path.join(VM_IMAGE_DIR, filename)
                size = os.path.getsize(full_path)
                disks.append((filename, size))
        return sorted(disks)
    except Exception as e:
        logging.error(f"Failed to list disk images: {e}")
        return []


def format_size_human(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MB"
    elif size_bytes < 1024**4:
        return f"{size_bytes / 1024**3:.2f} GB"
    else:
        return f"{size_bytes / 1024**4:.2f} TB"


def delete_disk_image():
    """
    Manually delete a VM disk image from the VM_IMAGE_DIR.
    """
    print_header("Delete Disk Image")
    disks = get_all_disk_images()

    if not disks:
        console.print(
            "[bold yellow]No disk images found in the directory.[/bold yellow]"
        )
        prompt_enter()
        return

    # Create a table of disk images
    table = Table(title="Available Disk Images")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Disk Image", style="green")
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("In Use", style="red")

    # Get all VMs and their disk paths
    all_vm_disks = []
    for vm in get_vm_list():
        vm_disks = get_vm_disks(vm["name"])
        all_vm_disks.extend(vm_disks)

    # Populate the table
    for idx, (disk, size) in enumerate(disks, start=1):
        full_disk_path = os.path.join(VM_IMAGE_DIR, disk)
        in_use = "Yes" if full_disk_path in all_vm_disks else "No"
        table.add_row(str(idx), disk, format_size_human(size), in_use)

    console.print(table)

    # Get user selection
    while True:
        choice = (
            input(
                format_nord(
                    "Select a disk image to delete by number (or 'q' to cancel): ",
                    NORD8,
                )
            )
            .strip()
            .lower()
        )
        if choice == "q":
            return

        try:
            index = int(choice) - 1
            if 0 <= index < len(disks):
                selected_disk = disks[index][0]
                break
            else:
                print(format_nord("Invalid selection. Please try again.", NORD11))
        except ValueError:
            print(format_nord("Please enter a valid number or 'q' to cancel.", NORD11))

    # Check if disk is in use
    full_disk_path = os.path.join(VM_IMAGE_DIR, selected_disk)
    if full_disk_path in all_vm_disks:
        print(
            format_nord(
                f"WARNING: Disk image '{selected_disk}' is currently in use by a VM!",
                NORD11,
            )
        )
        print(
            format_nord(
                "Deleting this disk will likely corrupt the VM. You should use the 'Delete VM' option instead.",
                NORD13,
            )
        )

    # Extra confirmation for safety
    confirm = (
        input(
            format_nord(
                f"Are you absolutely sure you want to delete disk image '{selected_disk}'? This action cannot be undone. (yes/no): ",
                NORD11,
            )
        )
        .strip()
        .lower()
    )

    if confirm != "yes":
        logging.info("Disk image deletion cancelled.")
        prompt_enter()
        return

    # Perform deletion
    try:
        os.remove(full_disk_path)
        logging.info(f"Disk image '{selected_disk}' deleted successfully.")
    except Exception as e:
        logging.error(f"Failed to delete disk image '{selected_disk}': {e}")

    prompt_enter()


# ------------------------------------------------------------------------------
# SYSTEM INFORMATION
# ------------------------------------------------------------------------------
def show_system_info():
    """
    Display system and libvirt information.
    """
    print_header("System Information")

    # Host information
    hostname = socket.gethostname()

    # Get libvirt version
    try:
        libvirt_version = run_command(
            ["virsh", "--version"], capture_output=True
        ).strip()
    except Exception:
        libvirt_version = "Unknown"

    # Get QEMU version
    try:
        qemu_version = (
            run_command(["qemu-img", "--version"], capture_output=True)
            .strip()
            .split("\n")[0]
        )
    except Exception:
        qemu_version = "Unknown"

    # Get available storage
    try:
        total, used, free = shutil.disk_usage(VM_IMAGE_DIR)
        storage_info = f"Total: {format_size_human(total)}, Used: {format_size_human(used)}, Free: {format_size_human(free)}"
    except Exception:
        storage_info = "Unable to determine storage information"

    # Display the information
    console.print(
        Panel.fit(
            f"[bold]Host:[/bold] {hostname}\n"
            f"[bold]Libvirt Version:[/bold] {libvirt_version}\n"
            f"[bold]QEMU Version:[/bold] {qemu_version}\n"
            f"[bold]VM Storage Directory:[/bold] {VM_IMAGE_DIR}\n"
            f"[bold]Storage:[/bold] {storage_info}\n"
            f"[bold]ISO Directory:[/bold] {ISO_DIR}\n"
            f"[bold]Python Version:[/bold] {sys.version.split()[0]}"
        )
    )

    prompt_enter()


# ------------------------------------------------------------------------------
# INTERACTIVE MAIN MENU
# ------------------------------------------------------------------------------
def interactive_menu():
    """
    Display the interactive main menu for VM management.
    """
    while True:
        print_header("Advanced VM Manager Tool")
        # VM Management
        print(format_nord("VM MANAGEMENT", NORD10))
        print(f"{format_nord('[1]', NORD14)} List Virtual Machines")
        print(f"{format_nord('[2]', NORD14)} Create Virtual Machine")
        print(f"{format_nord('[3]', NORD14)} Start Virtual Machine")
        print(f"{format_nord('[4]', NORD14)} Stop Virtual Machine")
        print(f"{format_nord('[5]', NORD14)} Delete Virtual Machine")
        print(f"{format_nord('[6]', NORD14)} Monitor Virtual Machine Resources")
        print(f"{format_nord('[7]', NORD14)} Remote Console Access")
        print(f"{format_nord('[8]', NORD14)} Pause Virtual Machine")
        print(f"{format_nord('[9]', NORD14)} Resume Virtual Machine")

        # Snapshot Management
        print("\n" + format_nord("SNAPSHOT MANAGEMENT", NORD10))
        print(f"{format_nord('[s]', NORD14)} Snapshot Management")

        # ISO Management
        print("\n" + format_nord("ISO & DISK MANAGEMENT", NORD10))
        print(f"{format_nord('[i]', NORD14)} List Available ISOs")
        print(f"{format_nord('[d]', NORD14)} Download ISO")
        print(f"{format_nord('[x]', NORD14)} Delete Disk Image")

        # System & Exit
        print("\n" + format_nord("SYSTEM", NORD10))
        print(f"{format_nord('[y]', NORD14)} System Information")
        print(f"{format_nord('[q]', NORD14)} Quit")

        print("-" * 60)
        choice = input(format_nord("Enter your choice: ", NORD8)).strip().lower()

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
            monitor_vm()
        elif choice == "7":
            remote_console()
        elif choice == "8":
            pause_vm()
        elif choice == "9":
            resume_vm()
        elif choice == "s":
            snapshot_menu()
        elif choice == "i":
            show_isos()
        elif choice == "d":
            download_iso()
        elif choice == "x":
            delete_disk_image()
        elif choice == "y":
            show_system_info()
        elif choice == "q":
            logging.info("Exiting VM Manager. Goodbye!")
            sys.exit(0)
        else:
            console.print(
                "[bold yellow]Invalid selection. Please try again.[/bold yellow]"
            )
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the VM manager script.
    """
    if sys.version_info < (3, 6):
        print("This script requires Python 3.6 or higher.")
        sys.exit(1)

    # Check privileges and dependencies first
    if not check_root():
        sys.exit(1)

    # Create necessary directories
    os.makedirs(Path(LOG_FILE).parent, exist_ok=True)
    os.makedirs(ISO_DIR, exist_ok=True)
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    # Setup logging
    Path(LOG_FILE).touch(exist_ok=True)
    setup_logging()

    # Log startup information
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"VM MANAGER v5.0.0 STARTED AT {now}")
    logging.info("=" * 80)

    # Create a temporary directory for the application
    temp_dir = os.path.join(tempfile.gettempdir(), "vm_manager")
    os.makedirs(temp_dir, exist_ok=True)

    # Check dependencies before proceeding
    if not check_dependencies():
        logging.error("Missing critical dependencies. Exiting.")
        sys.exit(1)

    try:
        # Enter interactive menu
        interactive_menu()
    except KeyboardInterrupt:
        logging.info("Application interrupted. Exiting gracefully.")
    except Exception as ex:
        logging.critical(f"Unhandled exception: {ex}", exc_info=True)
        console.print_exception()
        sys.exit(1)
    finally:
        logging.info("VM Manager shutdown complete.")


if __name__ == "__main__":
    main()
