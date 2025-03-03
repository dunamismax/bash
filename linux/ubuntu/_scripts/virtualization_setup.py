#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup Script
--------------------------------------------------

A streamlined terminal interface for setting up a virtualization environment on Ubuntu.
Features clean, user-friendly output with Nord theme styling and comprehensive
progress indicators, following best practices for terminal applications.

This utility performs the following tasks:
  • Updates package lists and installs virtualization packages
  • Manages virtualization services
  • Configures and recreates the default NAT network
  • Fixes storage permissions and user group settings
  • Updates VM network settings, configures autostart, and starts VMs
  • Verifies the overall setup and installs a systemd service

Note: Run this script with root privileges.

Version: 1.0.0
"""

import atexit
import os
import pwd
import grp
import signal
import socket
import subprocess
import sys
import time
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable

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
OPERATION_TIMEOUT: int = 600  # seconds
VERSION: str = "1.0.0"
APP_NAME: str = "Virt Setup"
APP_SUBTITLE: str = "Enhanced Virtualization Environment"

VM_STORAGE_PATHS: List[str] = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]
VIRTUALIZATION_PACKAGES: List[str] = [
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
VIRTUALIZATION_SERVICES: List[str] = ["libvirtd", "virtlogd"]

VM_OWNER: str = "root"
VM_GROUP: str = "libvirt-qemu"
VM_DIR_MODE: int = 0o2770
VM_FILE_MODE: int = 0o0660
LIBVIRT_USER_GROUP: str = "libvirt"

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

SERVICE_PATH: Path = Path("/etc/systemd/system/virtualization_setup.service")
SERVICE_CONTENT: str = """[Unit]
Description=Virtualization Setup Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/this_script.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

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


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class VirtualMachine:
    """
    Represents a virtual machine with its details and status.

    Attributes:
        id: The VM's ID in libvirt
        name: The VM's name
        state: Current state (running, shut off, etc.)
        autostart: Whether autostart is enabled
    """

    id: str
    name: str
    state: str
    autostart: Optional[bool] = None


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Try to use a tech-looking font
    compact_fonts = ["slant", "small", "smslant", "digital", "times"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
       _      _                                _               
__   _(_)_ __| |_    ___ _ ____   __  ___  ___| |_ _   _ _ __  
\ \ / / | '__| __|  / _ \ '_ \ \ / / / __|/ _ \ __| | | | '_ \ 
 \ V /| | |  | |_  |  __/ | | \ V /  \__ \  __/ |_| |_| | |_) |
  \_/ |_|_|   \__|  \___|_| |_|\_/   |___/\___|\__|\__,_| .__/ 
                                                        |_|    
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


def print_success(text: str) -> None:
    """Print a success message with the appropriate styling."""
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """Print a warning message with the appropriate styling."""
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """Print an error message with the appropriate styling."""
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


def create_section_header(title: str) -> Panel:
    """
    Create a styled section header panel.

    Args:
        title: The section title

    Returns:
        A styled panel for the section
    """
    return Panel(
        Text(title, style=f"bold {NordColors.FROST_1}"),
        border_style=Style(color=NordColors.FROST_3),
        padding=(0, 2),
    )


def display_vm_table(vms: List[VirtualMachine]) -> None:
    """
    Create and display a table of virtual machines.

    Args:
        vms: List of VirtualMachine objects to display
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Virtual Machines[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("ID", style=f"bold {NordColors.FROST_4}", justify="right", width=6)
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("State", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Autostart", justify="center", width=10)

    for vm in vms:
        # Create status indicator for state
        if "running" in vm.state.lower():
            state = Text(vm.state, style=f"bold {NordColors.GREEN}")
        else:
            state = Text(vm.state, style=f"dim {NordColors.POLAR_NIGHT_4}")

        # Create status indicator for autostart
        if vm.autostart is True:
            autostart = Text("● Enabled", style=f"bold {NordColors.GREEN}")
        elif vm.autostart is False:
            autostart = Text("○ Disabled", style=f"bold {NordColors.RED}")
        else:
            autostart = Text("? Unknown", style=f"dim {NordColors.POLAR_NIGHT_4}")

        table.add_row(vm.id, vm.name, state, autostart)

    console.print(
        Panel(
            table,
            border_style=Style(color=NordColors.FROST_4),
            padding=(0, 1),
        )
    )


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
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
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Virtualization Setup Functions
# ----------------------------------------------------------------
def update_system_packages() -> bool:
    """Update the package lists using apt-get."""
    console.print(create_section_header("Updating Package Lists"))
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Updating package lists...", spinner="dots"
        ):
            run_command(["apt-get", "update"])
        print_success("Package lists updated successfully")
        return True
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False


def install_virtualization_packages(packages: List[str]) -> bool:
    """Install the required virtualization packages."""
    console.print(create_section_header("Installing Virtualization Packages"))
    if not packages:
        print_warning("No packages specified")
        return True

    total: int = len(packages)
    print_message(f"Installing {total} package(s)")
    failed: List[str] = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Installing packages", total=total)
        for pkg in packages:
            progress.update(task, description=f"Installing {pkg}")
            try:
                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in iter(proc.stdout.readline, ""):
                    if "Unpacking" in line or "Setting up" in line:
                        console.print(
                            "  " + line.strip(), style=f"{NordColors.SNOW_STORM_1}"
                        )
                proc.wait()
                if proc.returncode != 0:
                    print_error(f"Failed to install {pkg}")
                    failed.append(pkg)
                else:
                    print_success(f"{pkg} installed")
            except Exception as e:
                print_error(f"Error installing {pkg}: {e}")
                failed.append(pkg)
            progress.advance(task)

    if failed:
        print_warning(f"Failed to install: {', '.join(failed)}")
        return False

    print_success("All virtualization packages installed successfully")
    return True


def manage_virtualization_services(services: List[str]) -> bool:
    """Enable and start virtualization-related services."""
    console.print(create_section_header("Managing Virtualization Services"))
    if not services:
        print_warning("No services specified")
        return True

    total: int = len(services) * 2  # Each service has enable and start actions
    failed: List[str] = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Managing services", total=total)
        for svc in services:
            for action, cmd in [
                ("enable", ["systemctl", "enable", svc]),
                ("start", ["systemctl", "start", svc]),
            ]:
                progress.update(task, description=f"{action.capitalize()}ing {svc}")
                try:
                    run_command(cmd)
                    print_success(f"{svc} {action}d")
                except Exception as e:
                    print_error(f"Failed to {action} {svc}: {e}")
                    failed.append(f"{svc} ({action})")
                progress.advance(task)

    if failed:
        print_warning(f"Issues with services: {', '.join(failed)}")
        return False

    print_success("Services managed successfully")
    return True


def recreate_default_network() -> bool:
    """Recreate the default NAT network."""
    console.print(create_section_header("Recreating Default Network"))
    try:
        # Check if default network exists
        result = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "default" in result.stdout:
            print_message("Removing existing default network")
            run_command(["virsh", "net-destroy", "default"], check=False)

            # Remove autostart symlink if it exists
            autostart_path: Path = Path(
                "/etc/libvirt/qemu/networks/autostart/default.xml"
            )
            if autostart_path.exists() or autostart_path.is_symlink():
                autostart_path.unlink()
                print_message("Removed autostart link")

            run_command(["virsh", "net-undefine", "default"], check=False)
            print_message("Undefined old network")

        # Create temporary XML file
        net_xml_path: Path = Path("/tmp/default_network.xml")
        net_xml_path.write_text(DEFAULT_NETWORK_XML)
        print_message("Created network definition file")

        # Define, start and autostart the network
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Configuring network", total=3)

            progress.update(task, description="Defining network")
            run_command(["virsh", "net-define", str(net_xml_path)])
            progress.advance(task)

            progress.update(task, description="Starting network")
            run_command(["virsh", "net-start", "default"])
            progress.advance(task)

            progress.update(task, description="Setting autostart")
            run_command(["virsh", "net-autostart", "default"])
            progress.advance(task)

        # Verify network is active
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        if "default" in net_list.stdout and "active" in net_list.stdout:
            print_success("Default network is active")
            return True

        print_error("Default network not running after recreation")
        return False
    except Exception as e:
        print_error(f"Error recreating network: {e}")
        return False


def configure_default_network() -> bool:
    """Ensure the default network exists and is active."""
    console.print(create_section_header("Configuring Default Network"))
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Checking network status...", spinner="dots"
        ):
            net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)

        if "default" in net_list.stdout:
            print_message("Default network exists")
            if "active" not in net_list.stdout:
                print_message("Default network is inactive, starting it")
                try:
                    run_command(["virsh", "net-start", "default"])
                    print_success("Default network started")
                except Exception as e:
                    print_error(f"Network start failed: {e}")
                    print_message("Attempting full network recreation")
                    return recreate_default_network()
        else:
            print_message("Default network missing, creating it")
            return recreate_default_network()

        # Ensure autostart is set
        try:
            net_info = run_command(
                ["virsh", "net-info", "default"], capture_output=True
            )
            if "Autostart:      yes" not in net_info.stdout:
                print_message("Setting autostart for default network")
                run_command(["virsh", "net-autostart", "default"])
                print_success("Network autostart enabled")
            else:
                print_success("Network autostart already enabled")
        except Exception as e:
            print_warning(f"Autostart configuration issue: {e}")

        return True
    except Exception as e:
        print_error(f"Network configuration error: {e}")
        return False


def get_virtual_machines() -> List[VirtualMachine]:
    """
    Retrieve a list of defined virtual machines with their status.

    Returns:
        List of VirtualMachine objects
    """
    vms: List[VirtualMachine] = []
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Retrieving VM information...", spinner="dots"
        ):
            # Get all VMs
            result = run_command(["virsh", "list", "--all"], capture_output=True)
            lines: List[str] = result.stdout.strip().splitlines()

            # Find separator line
            sep_index: int = next(
                (i for i, line in enumerate(lines) if line.strip().startswith("----")),
                -1,
            )

            if sep_index < 0:
                return vms

            # Parse VM information
            for line in lines[sep_index + 1 :]:
                parts = line.split()
                if len(parts) >= 3:
                    vm = VirtualMachine(
                        id=parts[0],
                        name=parts[1],
                        state=" ".join(parts[2:]),
                    )

                    # Get autostart info
                    try:
                        info = run_command(
                            ["virsh", "dominfo", vm.name], capture_output=True
                        )
                        vm.autostart = "Autostart:      yes" in info.stdout
                    except:
                        pass

                    vms.append(vm)

        return vms
    except Exception as e:
        print_error(f"Error retrieving VMs: {e}")
        return vms


def set_vm_autostart(vms: List[VirtualMachine]) -> bool:
    """
    Set virtual machines to start automatically.

    Args:
        vms: List of VirtualMachine objects

    Returns:
        True if successful, False otherwise
    """
    console.print(create_section_header("Configuring VM Autostart"))
    if not vms:
        print_warning("No VMs found")
        return True

    failed: List[str] = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        console=console,
    ) as progress:
        task = progress.add_task("Setting VM autostart", total=len(vms))
        for vm in vms:
            progress.update(task, description=f"Configuring {vm.name}")
            try:
                if vm.autostart:
                    print_success(f"{vm.name} already set to autostart")
                else:
                    run_command(["virsh", "autostart", vm.name])
                    vm.autostart = True
                    print_success(f"{vm.name} set to autostart")
            except Exception as e:
                print_error(f"Autostart failed for {vm.name}: {e}")
                failed.append(vm.name)
            progress.advance(task)

    if failed:
        print_warning(f"Autostart configuration failed for: {', '.join(failed)}")
        return False

    return True


def ensure_network_active_before_vm_start() -> bool:
    """
    Verify that the default network is active before starting VMs.

    Returns:
        True if network is active, False otherwise
    """
    print_message("Verifying network status before starting VMs")
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Checking network...", spinner="dots"
        ):
            net_list = run_command(["virsh", "net-list"], capture_output=True)

        for line in net_list.stdout.splitlines():
            if "default" in line and "active" in line:
                print_success("Default network is active")
                return True

        print_warning("Default network inactive; attempting recreation")
        return recreate_default_network()
    except Exception as e:
        print_error(f"Network verification error: {e}")
        return False


def start_virtual_machines(vms: List[VirtualMachine]) -> bool:
    """
    Start any virtual machines that are not currently running.

    Args:
        vms: List of VirtualMachine objects

    Returns:
        True if all VMs started successfully, False otherwise
    """
    console.print(create_section_header("Starting Virtual Machines"))
    if not vms:
        print_warning("No VMs found")
        return True

    to_start: List[VirtualMachine] = [
        vm for vm in vms if "running" not in vm.state.lower()
    ]

    if not to_start:
        print_success("All VMs are already running")
        return True

    if not ensure_network_active_before_vm_start():
        print_error("Default network not active; VM start may fail")

    failed: List[str] = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        console=console,
    ) as progress:
        task = progress.add_task("Starting VMs", total=len(to_start))

        for vm in to_start:
            progress.update(task, description=f"Starting {vm.name}")
            success: bool = False

            for attempt in range(1, 4):
                try:
                    result = run_command(["virsh", "start", vm.name], check=False)
                    if result.returncode == 0:
                        print_success(f"{vm.name} started successfully")
                        vm.state = "running"
                        success = True
                        break
                    else:
                        if (
                            result.stderr
                            and "Only one live display may be active" in result.stderr
                        ):
                            print_warning(
                                f"{vm.name} failed to start due to display conflict; retrying in 5 seconds..."
                            )
                            time.sleep(5)
                        else:
                            print_error(f"Failed to start {vm.name}: {result.stderr}")
                            break
                except Exception as e:
                    print_error(f"Error starting {vm.name}: {e}")
                    break

            if not success:
                failed.append(vm.name)

            progress.advance(task)
            time.sleep(2)  # Brief pause between VM starts

    if failed:
        print_warning(f"Failed to start VMs: {', '.join(failed)}")
        return False

    print_success("Virtual machines started successfully")
    return True


def fix_storage_permissions(paths: List[str]) -> bool:
    """
    Fix storage directory and file permissions for VM storage.

    Args:
        paths: List of storage directory paths

    Returns:
        True if successful, False otherwise
    """
    console.print(create_section_header("Fixing VM Storage Permissions"))
    if not paths:
        print_warning("No storage paths specified")
        return True

    try:
        uid: int = pwd.getpwnam(VM_OWNER).pw_uid
        gid: int = grp.getgrnam(VM_GROUP).gr_gid
    except KeyError as e:
        print_error(f"User/group not found: {e}")
        return False

    for path_str in paths:
        path: Path = Path(path_str)
        print_message(f"Processing {path}")

        if not path.exists():
            print_warning(f"{path} does not exist; creating directory")
            path.mkdir(mode=VM_DIR_MODE, parents=True, exist_ok=True)

        # Count total items for progress bar
        total_items = 0
        for root, dirs, files in os.walk(str(path)):
            total_items += 1 + len(dirs) + len(files)

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Updating permissions for {path.name}", total=total_items
            )

            try:
                # Set permission on the root path
                os.chown(str(path), uid, gid)
                os.chmod(str(path), VM_DIR_MODE)
                progress.advance(task)

                # Process all subdirectories and files
                for root, dirs, files in os.walk(str(path)):
                    for d in dirs:
                        dpath = Path(root) / d
                        progress.update(task, description=f"Directory: {dpath.name}")
                        try:
                            os.chown(str(dpath), uid, gid)
                            os.chmod(str(dpath), VM_DIR_MODE)
                        except Exception as e:
                            print_warning(f"Error on {dpath}: {e}")
                        progress.advance(task)

                    for f in files:
                        fpath = Path(root) / f
                        progress.update(task, description=f"File: {fpath.name}")
                        try:
                            os.chown(str(fpath), uid, gid)
                            os.chmod(str(fpath), VM_FILE_MODE)
                        except Exception as e:
                            print_warning(f"Error on {fpath}: {e}")
                        progress.advance(task)
            except Exception as e:
                print_error(f"Failed to update permissions on {path}: {e}")
                return False

    print_success("Storage permissions updated successfully")
    return True


def configure_user_groups() -> bool:
    """
    Ensure that the invoking (sudo) user is a member of the required group.

    Returns:
        True if successful, False otherwise
    """
    console.print(create_section_header("Configuring User Group Membership"))
    sudo_user: Optional[str] = os.environ.get("SUDO_USER")

    if not sudo_user:
        print_warning("SUDO_USER not set; skipping group configuration")
        return True

    try:
        pwd.getpwnam(sudo_user)
        grp.getgrnam(LIBVIRT_USER_GROUP)
    except KeyError as e:
        print_error(f"User or group error: {e}")
        return False

    # Get current user groups
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary = grp.getgrgid(pwd.getpwnam(sudo_user).pw_gid).gr_name

    if primary not in user_groups:
        user_groups.append(primary)

    # Check if user is already in the required group
    if LIBVIRT_USER_GROUP in user_groups:
        print_success(f"User '{sudo_user}' is already in group '{LIBVIRT_USER_GROUP}'")
        return True

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Adding user to group...", spinner="dots"
        ):
            run_command(["usermod", "-a", "-G", LIBVIRT_USER_GROUP, sudo_user])

        print_success(f"User '{sudo_user}' added to group '{LIBVIRT_USER_GROUP}'")
        print_warning("Please log out and log back in for changes to take effect")
        return True
    except Exception as e:
        print_error(f"Failed to add user to group: {e}")
        return False


def verify_virtualization_setup() -> bool:
    """
    Perform a series of checks to verify the virtualization environment.

    Returns:
        True if all checks pass, False otherwise
    """
    console.print(create_section_header("Verifying Virtualization Setup"))
    checks = [
        ("libvirtd Service", "systemctl is-active libvirtd", "active"),
        ("KVM Modules", "lsmod | grep kvm", "kvm"),
        ("Default Network", "virsh net-list", "default"),
    ]

    results = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Running verification checks", total=len(checks) + len(VM_STORAGE_PATHS)
        )

        # Run service and module checks
        for name, cmd, expected in checks:
            progress.update(task, description=f"Checking {name}")
            try:
                if "|" in cmd:
                    # Handle piped commands
                    cmd_parts = cmd.split("|")
                    p1 = subprocess.Popen(
                        cmd_parts[0].strip().split(), stdout=subprocess.PIPE
                    )
                    p2 = subprocess.Popen(
                        cmd_parts[1].strip().split(),
                        stdin=p1.stdout,
                        stdout=subprocess.PIPE,
                        text=True,
                    )
                    p1.stdout.close()
                    output = p2.communicate()[0]
                    result = expected in output
                else:
                    # Single command
                    result = run_command(cmd.split(), check=False, capture_output=True)
                    if isinstance(result.stdout, str):
                        result = expected in result.stdout.strip()
                    else:
                        result = False

                if result:
                    print_success(f"{name}: OK")
                    results.append(True)
                else:
                    print_error(f"{name}: FAILED")
                    results.append(False)
            except Exception as e:
                print_error(f"{name} check error: {e}")
                results.append(False)

            progress.advance(task)

        # Check storage paths
        for path_str in VM_STORAGE_PATHS:
            path = Path(path_str)
            progress.update(task, description=f"Checking storage: {path.name}")

            if path.exists():
                print_success(f"Storage exists: {path}")
                results.append(True)
            else:
                print_error(f"Storage missing: {path}")
                try:
                    path.mkdir(mode=VM_DIR_MODE, parents=True, exist_ok=True)
                    print_success(f"Created storage directory: {path}")
                    results.append(True)
                except Exception as e:
                    print_error(f"Failed to create {path}: {e}")
                    results.append(False)

            progress.advance(task)

    # Display verification results
    if all(results):
        display_panel(
            "All verification checks passed! Your virtualization environment is ready.",
            style=NordColors.GREEN,
            title="Verification Complete",
        )
        return True
    else:
        failed_count = results.count(False)
        display_panel(
            f"{failed_count} verification check(s) failed. See details above.",
            style=NordColors.YELLOW,
            title="Verification Issues",
        )
        return False


def install_and_enable_service() -> bool:
    """
    Install the systemd unit file for virtualization setup,
    reload systemd, enable and start the service.

    Returns:
        True if successful, False otherwise
    """
    console.print(create_section_header("Installing Systemd Service"))

    current_script = Path(sys.argv[0]).resolve()
    # Update service content with actual script path
    service_content = SERVICE_CONTENT.replace(
        "/path/to/this_script.py", str(current_script)
    )

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Setting up service", total=4)

            progress.update(task, description="Installing service file")
            SERVICE_PATH.write_text(service_content)
            print_success(f"Service file installed to {SERVICE_PATH}")
            progress.advance(task)

            progress.update(task, description="Reloading systemd")
            run_command(["systemctl", "daemon-reload"])
            print_success("Systemd daemon reloaded")
            progress.advance(task)

            progress.update(task, description="Enabling service")
            run_command(["systemctl", "enable", "virtualization_setup.service"])
            print_success("Service enabled")
            progress.advance(task)

            progress.update(task, description="Starting service")
            run_command(["systemctl", "start", "virtualization_setup.service"])
            print_success("Service started")
            progress.advance(task)

        return True
    except Exception as e:
        print_error(f"Failed to install and enable service: {e}")
        return False


# ----------------------------------------------------------------
# Main Execution Flow
# ----------------------------------------------------------------
def main() -> None:
    """Main function to orchestrate the virtualization setup."""
    console.clear()
    console.print(create_header())

    # Display system information
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Hostname: {HOSTNAME}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
    )
    console.print()

    # Check for root privileges
    if os.geteuid() != 0:
        display_panel(
            "This script must be run as root (e.g., using sudo)",
            style=NordColors.RED,
            title="Permission Error",
        )
        sys.exit(1)

    # Display setup summary
    display_panel(
        "This utility will set up a complete virtualization environment on Ubuntu.\n"
        "It will install packages, configure networks, fix permissions, and start VMs.\n"
        "The setup process may take several minutes to complete.",
        style=NordColors.FROST_2,
        title="Setup Overview",
    )
    console.print()

    # Ask for confirmation
    console.print(f"[bold {NordColors.FROST_2}]Proceed with setup? (y/n)[/]", end=" ")
    choice = input().strip().lower()
    if choice != "y":
        display_panel(
            "Setup cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(0)

    console.print()

    # Execute each setup task sequentially
    tasks_results = {}

    # 1. Update package lists
    tasks_results["package_update"] = update_system_packages()
    console.print()

    # 2. Install virtualization packages
    tasks_results["package_install"] = install_virtualization_packages(
        VIRTUALIZATION_PACKAGES
    )
    console.print()

    # 3. Manage virtualization services
    tasks_results["services"] = manage_virtualization_services(VIRTUALIZATION_SERVICES)
    console.print()

    # 4. Install systemd service
    tasks_results["systemd_service"] = install_and_enable_service()
    console.print()

    # 5. Configure network (with retries)
    network_configured = False
    for attempt in range(1, 4):
        print_message(f"Network configuration attempt {attempt}")
        if configure_default_network():
            network_configured = True
            break
        time.sleep(2)

    if not network_configured:
        print_error("Failed to configure network after multiple attempts")
        recreate_default_network()

    tasks_results["network"] = network_configured
    console.print()

    # 6. Fix storage permissions
    tasks_results["storage"] = fix_storage_permissions(VM_STORAGE_PATHS)
    console.print()

    # 7. Configure user groups
    tasks_results["user_groups"] = configure_user_groups()
    console.print()

    # 8. Get and display VM information
    vms = get_virtual_machines()
    if vms:
        print_success(f"Found {len(vms)} virtual machine(s)")
        display_vm_table(vms)

        # 9. Configure VM autostart
        tasks_results["vm_autostart"] = set_vm_autostart(vms)
        console.print()

        # 10. Start VMs
        tasks_results["vm_start"] = start_virtual_machines(vms)
    else:
        print_message("No virtual machines found")
        tasks_results["vm_autostart"] = True
        tasks_results["vm_start"] = True

    console.print()

    # 11. Verify the setup
    tasks_results["verification"] = verify_virtualization_setup()
    console.print()

    # Display summary
    success_count = sum(1 for result in tasks_results.values() if result)
    total_tasks = len(tasks_results)

    # Create summary table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Setup Summary[/]",
        border_style=NordColors.FROST_3,
    )

    table.add_column("Task", style=f"bold {NordColors.FROST_4}")
    table.add_column("Status", justify="center")

    for task, result in tasks_results.items():
        task_name = task.replace("_", " ").title()
        status = (
            Text("✓ Success", style=f"bold {NordColors.GREEN}")
            if result
            else Text("✗ Failed", style=f"bold {NordColors.RED}")
        )
        table.add_row(task_name, status)

    console.print(
        Panel(
            table,
            border_style=Style(color=NordColors.FROST_4),
            padding=(1, 2),
        )
    )

    # Final status message
    if success_count == total_tasks:
        display_panel(
            "Virtualization environment setup completed successfully!\n\n"
            "Next steps:\n"
            "• Log out and log back in for group changes to take effect\n"
            "• Run 'virt-manager' to manage virtual machines\n"
            "• Check logs with 'journalctl -u libvirtd'",
            style=NordColors.GREEN,
            title="Setup Complete",
        )
    else:
        display_panel(
            f"Setup completed with {total_tasks - success_count} issue(s).\n"
            "Review the warnings and errors above for details.",
            style=NordColors.YELLOW,
            title="Setup Complete with Issues",
        )


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Setup interrupted by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(130)
    except Exception as e:
        display_panel(f"Unhandled error: {e}", style=NordColors.RED, title="Error")
        console.print_exception()
        sys.exit(1)
