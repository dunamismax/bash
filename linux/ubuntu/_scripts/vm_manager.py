#!/usr/bin/env python3
"""
Enhanced VM Manager
--------------------------------------------------

A comprehensive virtual machine management utility for KVM/libvirt with robust error handling,
real-time progress tracking, and a beautiful Nord-themed interface. This tool provides a complete
solution for managing virtual machines on Linux systems.

Features:
  - List, create, start, stop, and delete virtual machines
  - Create, list, revert to, and delete VM snapshots
  - Real-time VM status monitoring
  - Detailed VM information display
  - Elegant Nord-themed interface

Usage:
  Run the script with root privileges (sudo) and navigate through the interactive menu
  - Numbers 1-8: Select main menu options
  - Follow on-screen prompts for specific operations

Note: This script must be run with root privileges.
Version: 2.0.0
"""

import atexit
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    import shutil
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
APP_NAME: str = "VM Manager"
APP_SUBTITLE: str = "KVM/Libvirt Management Tool"
VERSION: str = "2.0.0"

# Directories and Files
LOG_FILE: str = "/var/log/vm_manager.log"
VM_IMAGE_DIR: str = "/var/lib/libvirt/images"
ISO_DIR: str = "/var/lib/libvirt/boot"
SNAPSHOT_DIR: str = "/var/lib/libvirt/snapshots"
DEFAULT_LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

# Default VM settings
DEFAULT_VCPUS: int = 2
DEFAULT_RAM_MB: int = 2048
DEFAULT_DISK_GB: int = 20
DEFAULT_OS_VARIANT: str = "ubuntu22.04"

# UI Settings
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
OPERATION_TIMEOUT: int = 300  # seconds

# Default network XML configuration for libvirt
DEFAULT_NETWORK_XML: str = """<network>
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


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class VMInfo:
    """
    Contains information about a virtual machine.

    Attributes:
        id: VM identifier (might be - if not running)
        name: VM name
        state: Current state (running, shut off, etc)
    """

    def __init__(self, vm_id: str, name: str, state: str):
        self.id: str = vm_id
        self.name: str = name
        self.state: str = state


class SnapshotInfo:
    """
    Contains information about a VM snapshot.

    Attributes:
        name: Snapshot name
        creation_time: When the snapshot was created
        state: Current state
    """

    def __init__(self, name: str, creation_time: str, state: Optional[str] = None):
        self.name: str = name
        self.creation_time: str = creation_time
        self.state: Optional[str] = state


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
__   ___ __ ___    _ __ ___   __ _ _ __   __ _  __ _  ___ _ __ 
\ \ / / '_ ` _ \  | '_ ` _ \ / _` | '_ \ / _` |/ _` |/ _ \ '__|
 \ V /| | | | | | | | | | | | (_| | | | | (_| | (_| |  __/ |   
  \_/ |_| |_| |_| |_| |_| |_|\__,_|_| |_|\__,_|\__, |\___|_|   
                                               |___/           
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(text: str) -> None:
    """Print an informational message."""
    print_message(text, NordColors.FROST_3, "ℹ")


def print_success(text: str) -> None:
    """Print a success message."""
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """Print an error message."""
    print_message(text, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def display_section_title(title: str) -> None:
    """
    Display a section title with decorative elements.

    Args:
        title: The section title to display
    """
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/bold {NordColors.FROST_2}]")
    console.print(
        f"[bold {NordColors.FROST_2}]  {title.center(TERM_WIDTH - 4)}[/bold {NordColors.FROST_2}]"
    )
    console.print(f"[bold {NordColors.FROST_2}]{border}[/bold {NordColors.FROST_2}]\n")


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure logging with console and rotating file handlers."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
        print_info(f"Logging to {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up log file: {e}")
        print_info("Continuing with console logging only")
        logging.warning(f"Could not set up log file: {e}")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)
    logging.info("Performing cleanup tasks")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    logging.warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    command: List[str],
    capture_output: bool = False,
    check: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> str:
    """
    Execute a shell command with error handling.

    Args:
        command: List of command arguments.
        capture_output: If True, returns stdout.
        check: If True, raises on non-zero exit.
        timeout: Timeout in seconds.

    Returns:
        Command stdout if capture_output is True, otherwise empty string.
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

        if capture_output and result.stdout:
            logging.debug(f"Command output: {result.stdout.strip()}")

        return result.stdout if capture_output else ""

    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out after {timeout}s: {cmd_str}")
        print_error(f"Command timed out after {timeout}s: {cmd_str}")
        raise

    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.strip() if e.stderr else "No error output"
        logging.error(
            f"Command failed with exit code {e.returncode}: {cmd_str}\nError: {stderr_msg}"
        )
        print_error(f"Command failed: {cmd_str}")
        if check:
            raise
        return ""


# ----------------------------------------------------------------
# VM Management Helper Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Ensure the script is run with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges")
        print_info("Please run with: sudo python3 vm_manager.py")
        return False

    print_success("Running with root privileges")
    return True


def check_dependencies() -> bool:
    """
    Check if required dependencies are available.

    Returns:
        True if all dependencies are available, False otherwise
    """
    required_commands = ["virsh", "qemu-img", "virt-install"]
    missing_commands = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Checking", total=len(required_commands))

        for cmd in required_commands:
            progress.update(task, advance=0.5)
            if not shutil.which(cmd):
                missing_commands.append(cmd)
            progress.update(task, advance=0.5)

    if missing_commands:
        print_error(f"Missing required dependencies: {', '.join(missing_commands)}")
        print_info("Please install the required packages:")
        if "virsh" in missing_commands or "virt-install" in missing_commands:
            print_info(
                "  sudo apt install libvirt-clients libvirt-daemon-system virtinst"
            )
        if "qemu-img" in missing_commands:
            print_info("  sudo apt install qemu-utils")
        return False

    print_success("All required dependencies are available")
    return True


def ensure_default_network() -> bool:
    """
    Ensure the 'default' virtual network is active. If not, create and start it.

    Returns:
        True if network is active, False if setup failed
    """
    with console.status(
        f"[bold {NordColors.FROST_3}]Checking virtual network status...", spinner="dots"
    ):
        try:
            output = run_command(["virsh", "net-list", "--all"], capture_output=True)

            # Check if default network exists and its status
            if "default" in output:
                if "active" in output and not "inactive" in output:
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

                # Create a temporary file to hold network XML
                fd, xml_path = tempfile.mkstemp(suffix=".xml")
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(DEFAULT_NETWORK_XML)

                    # Define, start and enable autostart for the network
                    run_command(["virsh", "net-define", xml_path])
                    run_command(["virsh", "net-start", "default"])
                    run_command(["virsh", "net-autostart", "default"])
                    print_success("Default network created and activated")
                    return True

                finally:
                    # Clean up temporary file
                    if os.path.exists(xml_path):
                        os.unlink(xml_path)

        except Exception as e:
            logging.error(f"Error ensuring default network: {e}")
            print_error(f"Failed to configure default network: {e}")
            return False


def get_vm_list() -> List[VMInfo]:
    """
    Retrieve list of VMs using 'virsh list --all'.

    Returns:
        List of VMInfo objects
    """
    try:
        output = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "inactive" in output and "default" in output:
            ensure_default_network()

        output = run_command(["virsh", "list", "--all"], capture_output=True)
        vms = []
        lines = output.strip().splitlines()

        # Find the separator line between header and data
        try:
            sep_index = next(
                i for i, line in enumerate(lines) if line.lstrip().startswith("---")
            )
        except StopIteration:
            sep_index = 1  # Default to assuming header is on line 1

        # Process each VM entry
        for line in lines[sep_index + 1 :]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    vm_id = parts[0]
                    vm_name = parts[1]
                    vm_state = " ".join(parts[2:]) if len(parts) > 2 else ""
                    vms.append(VMInfo(vm_id, vm_name, vm_state))

        return vms

    except Exception as e:
        logging.error(f"Failed to retrieve VM list: {e}")
        print_error(f"Failed to retrieve VM list: {e}")
        return []


def get_vm_snapshots(vm_name: str) -> List[SnapshotInfo]:
    """
    Retrieve snapshots for a VM.

    Args:
        vm_name: Name of the VM

    Returns:
        List of SnapshotInfo objects
    """
    try:
        output = run_command(
            ["virsh", "snapshot-list", vm_name], capture_output=True, check=False
        )

        if not output or "failed" in output.lower():
            return []

        snapshots = []
        lines = output.strip().splitlines()

        # Filter out header and separator lines
        data_lines = [
            line
            for line in lines
            if line.strip()
            and not line.startswith("Name")
            and not line.startswith("----")
        ]

        # Process each snapshot entry
        for line in data_lines:
            parts = line.split()
            if len(parts) >= 1:
                snap_name = parts[0]
                creation_time = " ".join(parts[1:3]) if len(parts) > 2 else ""
                state = parts[3] if len(parts) > 3 else ""
                snapshots.append(SnapshotInfo(snap_name, creation_time, state))

        return snapshots

    except Exception as e:
        logging.error(f"Failed to retrieve snapshots for VM '{vm_name}': {e}")
        print_error(f"Failed to retrieve snapshots for VM '{vm_name}': {e}")
        return []


def select_vm(
    prompt: str = "Select a VM by number (or 'q' to cancel): ",
) -> Optional[str]:
    """
    Prompt the user to select a VM from the list.

    Args:
        prompt: The prompt to display to the user

    Returns:
        Selected VM name or None if cancelled
    """
    vms = get_vm_list()
    if not vms:
        print_info("No VMs available")
        return None

    display_section_title("Available Virtual Machines")

    # Create a table for VM list
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        box=None,
    )

    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("ID", style=f"{NordColors.SNOW_STORM_1}")

    # Add VMs to the table
    for idx, vm in enumerate(vms, start=1):
        state = vm.state.lower()
        if "running" in state:
            state_style = NordColors.GREEN
        elif "paused" in state:
            state_style = NordColors.YELLOW
        elif "shut off" in state:
            state_style = NordColors.RED
        else:
            state_style = NordColors.SNOW_STORM_1

        table.add_row(
            str(idx), vm.name, f"[{state_style}]{vm.state}[/{state_style}]", vm.id
        )

    console.print(table)
    console.print()

    # Get user selection
    while True:
        choice = input(f"[bold {NordColors.PURPLE}]{prompt}[/] ").strip()
        if choice.lower() == "q":
            return None

        try:
            num = int(choice)
            if 1 <= num <= len(vms):
                return vms[num - 1].name
            else:
                print_error("Invalid selection number")
        except ValueError:
            print_error("Please enter a valid number")


def select_snapshot(
    vm_name: str, prompt: str = "Select a snapshot by number (or 'q' to cancel): "
) -> Optional[str]:
    """
    Prompt the user to select a snapshot for a VM.

    Args:
        vm_name: Name of the VM
        prompt: The prompt to display to the user

    Returns:
        Selected snapshot name or None if cancelled
    """
    snapshots = get_vm_snapshots(vm_name)
    if not snapshots:
        print_info(f"No snapshots found for VM '{vm_name}'")
        return None

    display_section_title(f"Snapshots for VM: {vm_name}")

    # Create a table for snapshot list
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        box=None,
    )

    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Creation Time", style=f"{NordColors.FROST_3}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")

    # Add snapshots to the table
    for idx, snap in enumerate(snapshots, start=1):
        table.add_row(str(idx), snap.name, snap.creation_time, snap.state or "")

    console.print(table)
    console.print()

    # Get user selection
    while True:
        choice = input(f"[bold {NordColors.PURPLE}]{prompt}[/] ").strip()
        if choice.lower() == "q":
            return None

        try:
            num = int(choice)
            if 1 <= num <= len(snapshots):
                return snapshots[num - 1].name
            else:
                print_error("Invalid selection number")
        except ValueError:
            print_error("Please enter a valid number")


def confirm_action(message: str) -> bool:
    """
    Ask the user to confirm an action.

    Args:
        message: The confirmation message to display

    Returns:
        True if confirmed, False otherwise
    """
    while True:
        confirm = (
            input(f"[bold {NordColors.PURPLE}]{message} (y/n): [/] ").strip().lower()
        )
        if confirm == "y" or confirm == "yes":
            return True
        elif confirm == "n" or confirm == "no":
            return False
        else:
            print_warning("Please enter 'y' or 'n'")


# ----------------------------------------------------------------
# VM Management Functions
# ----------------------------------------------------------------
def list_vms() -> None:
    """Display a list of VMs with their status."""
    console.clear()
    console.print(create_header())

    display_section_title("Virtual Machine List")

    with console.status(
        f"[bold {NordColors.FROST_3}]Retrieving VM information...", spinner="dots"
    ):
        vms = get_vm_list()

    if not vms:
        display_panel(
            "No virtual machines found", style=NordColors.FROST_3, title="VM List"
        )
        return

    # Create a table for VM list
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Available Virtual Machines[/]",
        title_justify="center",
        box=None,
        expand=True,
    )

    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("State", justify="center")
    table.add_column("ID", style=f"{NordColors.SNOW_STORM_1}")

    # Add VMs to the table
    for idx, vm in enumerate(vms, start=1):
        state = vm.state.lower()
        if "running" in state:
            state_text = Text("● RUNNING", style=f"bold {NordColors.GREEN}")
        elif "paused" in state:
            state_text = Text("◐ PAUSED", style=f"bold {NordColors.YELLOW}")
        elif "shut off" in state:
            state_text = Text("○ STOPPED", style=f"bold {NordColors.RED}")
        else:
            state_text = Text(
                f"? {vm.state.upper()}", style=f"dim {NordColors.POLAR_NIGHT_4}"
            )

        table.add_row(str(idx), vm.name, state_text, vm.id)

    # Display the table in a panel
    panel = Panel(
        table,
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(panel)

    # Add timestamp at the bottom
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Last updated: {current_time}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
        )
    )


def create_vm() -> None:
    """Create a new VM by gathering user input interactively."""
    console.clear()
    console.print(create_header())

    display_section_title("Create New Virtual Machine")

    # Ensure the default network is active before proceeding
    if not ensure_default_network():
        display_panel(
            "Cannot create VM without an active network",
            style=NordColors.RED,
            title="Network Error",
        )
        return

    # Gather VM name
    default_name = f"vm-{int(time.time()) % 10000}"
    vm_name = (
        input(
            f"[bold {NordColors.PURPLE}]Enter VM name (default: {default_name}): [/] "
        ).strip()
        or default_name
    )

    # Sanitize VM name (alphanumeric and dash/underscore only)
    vm_name = "".join(c for c in vm_name if c.isalnum() or c in "-_")
    if not vm_name:
        print_error("Invalid VM name")
        return

    # Gather VM resource specifications
    display_section_title("VM Resource Specifications")

    try:
        vcpus = int(
            input(
                f"[bold {NordColors.PURPLE}]Number of vCPUs (default: {DEFAULT_VCPUS}): [/] "
            )
            or DEFAULT_VCPUS
        )
        ram = int(
            input(
                f"[bold {NordColors.PURPLE}]RAM in MB (default: {DEFAULT_RAM_MB}): [/] "
            )
            or DEFAULT_RAM_MB
        )
        disk_size = int(
            input(
                f"[bold {NordColors.PURPLE}]Disk size in GB (default: {DEFAULT_DISK_GB}): [/] "
            )
            or DEFAULT_DISK_GB
        )
    except ValueError:
        print_error("vCPUs, RAM, and disk size must be numbers")
        return

    # Validate resource specifications
    if vcpus < 1 or ram < 512 or disk_size < 1:
        print_error("Invalid resource specifications")
        print_info(
            "vCPUs must be >= 1, RAM must be >= 512 MB, Disk size must be >= 1 GB"
        )
        return

    # Check for existing disk image
    disk_image = os.path.join(VM_IMAGE_DIR, f"{vm_name}.qcow2")
    if os.path.exists(disk_image):
        print_error(
            f"Disk image '{disk_image}' already exists. Choose a different VM name."
        )
        return

    # Select installation media
    display_section_title("Installation Media")

    print_info("Select the installation method:")
    console.print(f"[{NordColors.SNOW_STORM_1}]1. Use existing ISO file[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]2. Cancel VM creation[/]")

    media_choice = input(
        f"\n[bold {NordColors.PURPLE}]Enter your choice (1-2): [/] "
    ).strip()

    if media_choice != "1":
        print_info("VM creation cancelled")
        return

    # Get ISO path
    iso_path = input(
        f"[bold {NordColors.PURPLE}]Enter full path to the ISO file: [/] "
    ).strip()

    if not os.path.isfile(iso_path):
        print_error("ISO file not found")
        print_info(
            f"The specified file '{iso_path}' does not exist or is not accessible"
        )
        return

    # Create directories if they don't exist
    os.makedirs(VM_IMAGE_DIR, exist_ok=True)

    # Create disk image
    display_section_title("Creating VM Disk Image")

    print_info(f"Creating {disk_size}GB disk image at {disk_image}")

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Creating disk image..."),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
        console=console,
    ) as progress:
        disk_task = progress.add_task("Creating", total=100)

        try:
            # Make the progress bar move to simulate activity
            progress.update(disk_task, completed=10)

            # Create the disk image
            run_command(
                ["qemu-img", "create", "-f", "qcow2", disk_image, f"{disk_size}G"]
            )

            # Complete the progress bar
            progress.update(disk_task, completed=100)
            print_success("Disk image created successfully")

        except Exception as e:
            print_error(f"Failed to create disk image: {e}")
            return

    # Create and start the VM
    display_section_title("Creating Virtual Machine")

    print_info(f"Creating VM '{vm_name}' with {vcpus} vCPUs and {ram}MB RAM")

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Creating virtual machine..."),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
        console=console,
    ) as progress:
        vm_task = progress.add_task("Creating", total=100)

        try:
            # Start the progress bar
            progress.update(vm_task, completed=10)

            # Prepare virt-install command
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

            # Progress update before running the command
            progress.update(vm_task, completed=30)

            # Create the VM
            run_command(virt_install_cmd)

            # Complete the progress bar
            progress.update(vm_task, completed=100)

            # Show success message
            print_success(f"VM '{vm_name}' created successfully")
            print_info("To connect to the console, use:")
            console.print(f"  [bold {NordColors.FROST_3}]virsh console {vm_name}[/]")
            print_info("Or use a VNC viewer to connect")

        except Exception as e:
            print_error(f"Failed to create VM '{vm_name}': {e}")
            print_info("Cleaning up failed VM creation...")

            try:
                run_command(
                    ["virsh", "undefine", vm_name, "--remove-all-storage"], check=False
                )
                print_info("Cleanup completed")
            except Exception as cleanup_error:
                print_warning(f"Incomplete cleanup: {cleanup_error}")

            return


def start_vm() -> None:
    """Start an existing VM after ensuring the default network is active."""
    console.clear()
    console.print(create_header())

    display_section_title("Start Virtual Machine")

    # Ensure the default network is active
    if not ensure_default_network():
        display_panel(
            "Network is not ready. VMs may not have network connectivity.",
            style=NordColors.YELLOW,
            title="Network Warning",
        )

    # Select VM to start
    vm_name = select_vm("Select a VM to start (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    try:
        # Check if VM is already running
        output = run_command(["virsh", "domstate", vm_name], capture_output=True)
        if "running" in output.lower():
            print_warning(f"VM '{vm_name}' is already running")
            return

        # Start the VM with a progress animation
        print_info(f"Starting VM '{vm_name}'...")

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Starting VM '{vm_name}'..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
            console=console,
        ) as progress:
            start_task = progress.add_task("Starting", total=100)

            # Update progress and start VM
            progress.update(start_task, completed=10)
            run_command(["virsh", "start", vm_name])

            # Simulate checking status
            for i in range(10, 100, 10):
                time.sleep(0.5)
                progress.update(start_task, completed=i)

            # Complete progress
            progress.update(start_task, completed=100)

        print_success(f"VM '{vm_name}' started successfully")

        # Check state to confirm
        time.sleep(1)
        state = run_command(["virsh", "domstate", vm_name], capture_output=True).strip()
        if "running" in state.lower():
            # Try to get IP address if VM is running
            try:
                ip_info = run_command(
                    ["virsh", "domifaddr", vm_name], capture_output=True, check=False
                )
                if "ipv4" in ip_info.lower():
                    print_info("Network information:")
                    console.print(f"  [bold {NordColors.FROST_3}]{ip_info.strip()}[/]")
            except Exception:
                print_info("VM started but network information is not yet available")

    except Exception as e:
        print_error(f"Error starting VM '{vm_name}': {e}")


def stop_vm() -> None:
    """Stop a running VM with graceful shutdown and forced destruction if needed."""
    console.clear()
    console.print(create_header())

    display_section_title("Stop Virtual Machine")

    # Select VM to stop
    vm_name = select_vm("Select a VM to stop (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    # Check VM state
    output = run_command(["virsh", "domstate", vm_name], capture_output=True)
    if "shut off" in output.lower():
        print_warning(f"VM '{vm_name}' is already stopped")
        return

    # Confirm before stopping
    if not confirm_action(f"Are you sure you want to stop VM '{vm_name}'?"):
        print_info("Operation cancelled")
        return

    try:
        # Attempt graceful shutdown first
        print_info(f"Sending shutdown signal to VM '{vm_name}'...")
        run_command(["virsh", "shutdown", vm_name])

        # Wait for VM to shut down with progress indication
        shutdown_time = 30  # Seconds to wait for graceful shutdown

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Waiting for VM to shut down..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            console=console,
        ) as progress:
            shutdown_task = progress.add_task("Shutting down", total=shutdown_time)

            # Check VM state repeatedly
            for i in range(shutdown_time):
                time.sleep(1)
                progress.update(shutdown_task, completed=i + 1)

                output = run_command(
                    ["virsh", "domstate", vm_name], capture_output=True, check=False
                )

                if "shut off" in output.lower():
                    progress.update(shutdown_task, completed=shutdown_time)
                    print_success("VM shut down gracefully")
                    return

        # If we reach here, graceful shutdown failed
        print_warning("VM did not shut down gracefully within the timeout period")

        # Ask for confirmation before forcing shutdown
        if confirm_action("Force VM to stop?"):
            with console.status(
                f"[bold {NordColors.FROST_3}]Forcing VM to stop...", spinner="dots"
            ):
                run_command(["virsh", "destroy", vm_name])
            print_success(f"VM '{vm_name}' forcefully stopped")
        else:
            print_info("VM shutdown aborted. The VM is still running.")

    except Exception as e:
        print_error(f"Error stopping VM '{vm_name}': {e}")


def delete_vm() -> None:
    """Delete an existing VM and its associated storage."""
    console.clear()
    console.print(create_header())

    display_section_title("Delete Virtual Machine")

    # Select VM to delete
    vm_name = select_vm("Select a VM to delete (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    # Double-check with user - this is destructive!
    if not confirm_action(
        f"CAUTION: This will permanently delete VM '{vm_name}' and ALL its storage. Continue?"
    ):
        print_info("Deletion cancelled")
        return

    # One more confirmation for running VMs
    output = run_command(
        ["virsh", "domstate", vm_name], capture_output=True, check=False
    )
    if "running" in output.lower():
        if not confirm_action(
            f"VM '{vm_name}' is currently running. Stop it and proceed with deletion?"
        ):
            print_info("Deletion cancelled")
            return

    try:
        # Shutdown VM if running
        if "running" in output.lower():
            print_info(f"Shutting down VM '{vm_name}'...")

            # Try graceful shutdown first
            run_command(["virsh", "shutdown", vm_name], check=False)

            with console.status(
                f"[bold {NordColors.FROST_3}]Waiting for VM to shut down...",
                spinner="dots",
            ):
                # Wait for a few seconds
                time.sleep(5)

            # Check state again
            output = run_command(
                ["virsh", "domstate", vm_name], capture_output=True, check=False
            )
            if "running" in output.lower():
                print_warning("VM did not shut down gracefully, forcing power off...")
                run_command(["virsh", "destroy", vm_name], check=False)

        # Delete the VM and its storage
        print_info(f"Deleting VM '{vm_name}' and all its storage...")

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Deleting VM..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
            console=console,
        ) as progress:
            delete_task = progress.add_task("Deleting", total=100)

            # Start the progress bar
            progress.update(delete_task, completed=30)

            # Delete VM with storage
            run_command(["virsh", "undefine", vm_name, "--remove-all-storage"])

            # Update progress
            progress.update(delete_task, completed=100)

        print_success(f"VM '{vm_name}' deleted successfully")

    except Exception as e:
        print_error(f"Error deleting VM '{vm_name}': {e}")
        logging.error(f"Error deleting VM '{vm_name}': {e}")


def show_vm_info() -> None:
    """Display detailed information for a selected VM."""
    console.clear()
    console.print(create_header())

    display_section_title("VM Information")

    # Select VM
    vm_name = select_vm("Select a VM to show info (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Gathering VM information...", spinner="dots"
        ):
            # Get basic VM information
            output = run_command(["virsh", "dominfo", vm_name], capture_output=True)

            # Get network information
            net_output = run_command(
                ["virsh", "domifaddr", vm_name], capture_output=True, check=False
            )

            # Get snapshot information
            snapshots = get_vm_snapshots(vm_name)

            # Get storage information
            storage_output = run_command(
                ["virsh", "domblklist", vm_name], capture_output=True
            )

        # Display basic information
        display_panel(
            f"Information for VM: {vm_name}",
            style=NordColors.FROST_2,
            title="VM Details",
        )

        # Create panels for different information categories
        panels = []

        # Basic info panel
        basic_info_content = ""
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                basic_info_content += f"[bold {NordColors.FROST_3}]{key.strip()}:[/] [{NordColors.SNOW_STORM_1}]{value.strip()}[/]\n"

        basic_info_panel = Panel(
            Text.from_markup(basic_info_content),
            title=f"[bold {NordColors.FROST_2}]Basic Information[/]",
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
        )
        panels.append(basic_info_panel)

        # Network info panel
        network_content = ""
        if net_output and "failed" not in net_output.lower():
            network_content = f"[{NordColors.SNOW_STORM_1}]{net_output.strip()}[/]"
        else:
            network_content = (
                f"[{NordColors.SNOW_STORM_1}]No network information available[/]"
            )

        network_panel = Panel(
            Text.from_markup(network_content),
            title=f"[bold {NordColors.FROST_2}]Network Information[/]",
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
        )
        panels.append(network_panel)

        # Snapshots panel
        snapshot_content = f"[bold {NordColors.FROST_3}]Total snapshots:[/] [{NordColors.SNOW_STORM_1}]{len(snapshots)}[/]\n\n"
        if snapshots:
            for idx, snap in enumerate(snapshots, 1):
                snapshot_content += (
                    f"[bold {NordColors.FROST_3}]{idx}.[/] [{NordColors.SNOW_STORM_1}]{snap.name}[/] "
                    f"([{NordColors.FROST_3}]{snap.creation_time}[/])\n"
                )
        else:
            snapshot_content += f"[{NordColors.SNOW_STORM_1}]No snapshots available[/]"

        snapshot_panel = Panel(
            Text.from_markup(snapshot_content),
            title=f"[bold {NordColors.FROST_2}]Snapshots[/]",
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
        )
        panels.append(snapshot_panel)

        # Storage panel
        storage_content = ""
        if "Target     Source" in storage_output:
            lines = storage_output.splitlines()
            storage_content += f"[bold {NordColors.FROST_3}]{lines[0]}[/]\n"
            storage_content += f"[{NordColors.FROST_2}]{lines[1]}[/]\n"
            for line in lines[2:]:
                storage_content += f"[{NordColors.SNOW_STORM_1}]{line}[/]\n"
        else:
            storage_content = f"[{NordColors.SNOW_STORM_1}]{storage_output}[/]"

        storage_panel = Panel(
            Text.from_markup(storage_content),
            title=f"[bold {NordColors.FROST_2}]Storage Devices[/]",
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
        )
        panels.append(storage_panel)

        # Display panels in two columns if terminal is wide enough
        if console.width > 120:
            console.print(Columns(panels))
        else:
            for panel in panels:
                console.print(panel)
                console.print()

    except Exception as e:
        print_error(f"Error retrieving VM info: {e}")
        logging.error(f"Error retrieving VM info: {e}")


# ----------------------------------------------------------------
# Snapshot Management Functions
# ----------------------------------------------------------------
def list_vm_snapshots(vm: Optional[str] = None) -> None:
    """
    List all snapshots for a specified VM. If no VM is provided, prompt the user.

    Args:
        vm: Optional VM name, if not provided user will be prompted
    """
    console.clear()
    console.print(create_header())

    display_section_title("VM Snapshots")

    # If VM name not provided, prompt for selection
    if not vm:
        vm = select_vm("Select a VM to list snapshots (or 'q' to cancel): ")
        if not vm:
            print_info("Operation cancelled")
            return

    # Get snapshots with status indicator
    with console.status(
        f"[bold {NordColors.FROST_3}]Retrieving snapshots for VM '{vm}'...",
        spinner="dots",
    ):
        snapshots = get_vm_snapshots(vm)

    if not snapshots:
        display_panel(
            f"No snapshots found for VM '{vm}'",
            style=NordColors.FROST_3,
            title="Snapshot List",
        )
        return

    # Create a table for snapshot list
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Snapshots for VM: {vm}[/]",
        title_justify="center",
        box=None,
        expand=True,
    )

    table.add_column(
        "No.", style=f"bold {NordColors.FROST_4}", justify="right", width=5
    )
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Creation Time", style=f"{NordColors.FROST_3}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")

    # Add snapshots to the table
    for idx, snap in enumerate(snapshots, start=1):
        table.add_row(str(idx), snap.name, snap.creation_time, snap.state or "")

    # Display the table in a panel
    panel = Panel(
        table,
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(panel)

    # Add snapshot management tips
    console.print()
    print_info("Snapshot Management Tips:")
    console.print(
        f"• [bold {NordColors.FROST_2}]Create snapshot:[/] Use the 'Create Snapshot' option"
    )
    console.print(
        f"• [bold {NordColors.FROST_2}]Revert to snapshot:[/] Use the 'Revert to Snapshot' option"
    )
    console.print(
        f"• [bold {NordColors.FROST_2}]Delete snapshot:[/] Use the 'Delete Snapshot' option"
    )


def create_snapshot() -> None:
    """Create a snapshot for a VM."""
    console.clear()
    console.print(create_header())

    display_section_title("Create VM Snapshot")

    # Select VM
    vm_name = select_vm("Select a VM to snapshot (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    # Get snapshot name and description
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_snapshot = f"{vm_name}-snap-{timestamp}"

    snapshot_name = (
        input(
            f"[bold {NordColors.PURPLE}]Enter snapshot name (default: {default_snapshot}): [/] "
        ).strip()
        or default_snapshot
    )

    description = input(
        f"[bold {NordColors.PURPLE}]Enter snapshot description (optional): [/] "
    ).strip()

    # Ensure snapshot directory exists
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # Create snapshot XML
    snapshot_xml = f"""<domainsnapshot>
  <name>{snapshot_name}</name>
  <description>{description}</description>
</domainsnapshot>"""

    # Create temporary XML file
    fd, xml_path = tempfile.mkstemp(suffix=".xml")

    try:
        # Write XML to temporary file
        with os.fdopen(fd, "w") as f:
            f.write(snapshot_xml)

        # Create snapshot with progress indicator
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Creating snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
            console=console,
        ) as progress:
            snap_task = progress.add_task("Creating", total=100)

            # Start progress
            progress.update(snap_task, completed=10)

            # Create snapshot
            run_command(["virsh", "snapshot-create", vm_name, "--xmlfile", xml_path])

            # Update progress
            progress.update(snap_task, completed=100)

        print_success(f"Snapshot '{snapshot_name}' created successfully")

    except Exception as e:
        print_error(f"Failed to create snapshot: {e}")
        logging.error(f"Failed to create snapshot: {e}")

    finally:
        # Clean up temporary file
        if os.path.exists(xml_path):
            os.unlink(xml_path)


def revert_to_snapshot() -> None:
    """Revert a VM to a selected snapshot."""
    console.clear()
    console.print(create_header())

    display_section_title("Revert VM to Snapshot")

    # Select VM
    vm_name = select_vm("Select a VM to revert (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    # Select snapshot
    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to revert to (or 'q' to cancel): "
    )
    if not snapshot_name:
        print_info("Operation cancelled")
        return

    # Warn about state loss and confirm
    display_panel(
        "WARNING: Reverting to a snapshot will discard all changes made since the snapshot was taken.",
        style=NordColors.YELLOW,
        title="Data Loss Warning",
    )

    if not confirm_action(
        f"Confirm revert of VM '{vm_name}' to snapshot '{snapshot_name}'?"
    ):
        print_info("Revert operation cancelled")
        return

    try:
        # Get current VM state
        current_state = run_command(
            ["virsh", "domstate", vm_name], capture_output=True
        ).strip()

        # Revert to snapshot with progress indicator
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Reverting to snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
            console=console,
        ) as progress:
            revert_task = progress.add_task("Reverting", total=100)

            # Update progress and revert
            progress.update(revert_task, completed=20)
            run_command(["virsh", "snapshot-revert", vm_name, snapshot_name])

            # Complete progress
            progress.update(revert_task, completed=100)

        print_success(
            f"VM '{vm_name}' reverted to snapshot '{snapshot_name}' successfully"
        )

        # Check if VM was running before and ask to restart
        if "running" in current_state.lower():
            if confirm_action(
                "VM was previously running. Would you like to start it now?"
            ):
                print_info(f"Starting VM '{vm_name}'...")
                run_command(["virsh", "start", vm_name])
                print_success(f"VM '{vm_name}' started")

    except Exception as e:
        print_error(f"Failed to revert to snapshot: {e}")
        logging.error(f"Failed to revert to snapshot: {e}")


def delete_snapshot() -> None:
    """Delete a snapshot for a VM."""
    console.clear()
    console.print(create_header())

    display_section_title("Delete VM Snapshot")

    # Select VM
    vm_name = select_vm("Select a VM (or 'q' to cancel): ")
    if not vm_name:
        print_info("Operation cancelled")
        return

    # Select snapshot
    snapshot_name = select_snapshot(
        vm_name, "Select a snapshot to delete (or 'q' to cancel): "
    )
    if not snapshot_name:
        print_info("Operation cancelled")
        return

    # Confirm deletion
    if not confirm_action(f"Delete snapshot '{snapshot_name}' for VM '{vm_name}'?"):
        print_info("Deletion cancelled")
        return

    try:
        # Delete snapshot with progress indicator
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Deleting snapshot..."),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]"),
            console=console,
        ) as progress:
            delete_task = progress.add_task("Deleting", total=100)

            # Update progress and delete
            progress.update(delete_task, completed=20)
            run_command(["virsh", "snapshot-delete", vm_name, snapshot_name])

            # Complete progress
            progress.update(delete_task, completed=100)

        print_success(f"Snapshot '{snapshot_name}' deleted successfully")

    except Exception as e:
        print_error(f"Failed to delete snapshot: {e}")
        logging.error(f"Failed to delete snapshot: {e}")


# ----------------------------------------------------------------
# Menu System Functions
# ----------------------------------------------------------------
def snapshot_management_menu() -> None:
    """Display the snapshot management submenu."""
    while True:
        console.clear()
        console.print(create_header())

        display_section_title("Snapshot Management")

        # Show snapshot menu options
        console.print(f"[{NordColors.SNOW_STORM_1}]1. List Snapshots[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]2. Create Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]3. Revert to Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]4. Delete Snapshot[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]5. Return to Main Menu[/]")

        console.print()
        snap_choice = input(
            f"[bold {NordColors.PURPLE}]Enter your choice (1-5): [/] "
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
            return
        else:
            console.clear()
            console.print(create_header())
            print_error("Invalid choice. Please enter a number between 1 and 5.")

        # Pause after operation
        if snap_choice != "5":
            console.print()
            input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")


def interactive_menu() -> None:
    """Display the interactive VM management menu."""
    while True:
        console.clear()
        console.print(create_header())

        # Display current date/time and system info
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )

        display_section_title("Main Menu")

        # Main menu options
        console.print(f"[{NordColors.SNOW_STORM_1}]1. List VMs[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]2. Create VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]3. Start VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]4. Stop VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]5. Delete VM[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]6. Show VM Info[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]7. Snapshot Management[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]8. Exit[/]")

        console.print()
        choice = input(
            f"[bold {NordColors.PURPLE}]Enter your choice (1-8): [/] "
        ).strip()

        # Handle menu choices
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
            continue  # Skip the pause after submenu returns
        elif choice == "8":
            console.clear()
            display_panel(
                "Thank you for using the VM Manager!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break
        else:
            console.clear()
            console.print(create_header())
            print_error("Invalid choice. Please enter a number between 1 and 8.")

        # Pause after operation (except for submenu and exit)
        if choice != "7" and choice != "8":
            console.print()
            input(f"[bold {NordColors.PURPLE}]Press Enter to continue...[/] ")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the Enhanced VM Manager."""
    try:
        console.clear()
        console.print(create_header())

        # Display system information
        console.print(f"Hostname: [bold {NordColors.FROST_3}]{HOSTNAME}[/]")
        console.print(
            f"Date: [bold {NordColors.FROST_3}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
        console.print()

        # Check root privileges
        if not check_root():
            sys.exit(1)

        # Setup logging
        setup_logging()
        logging.info(f"VM Manager v{VERSION} started")

        # Create required directories
        os.makedirs(ISO_DIR, exist_ok=True)
        os.makedirs(VM_IMAGE_DIR, exist_ok=True)
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

        # Check dependencies
        if not check_dependencies():
            logging.error("Missing critical dependencies")
            sys.exit(1)

        # Start the interactive menu
        interactive_menu()

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        logging.info("Program terminated by keyboard interrupt")
        sys.exit(130)

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
