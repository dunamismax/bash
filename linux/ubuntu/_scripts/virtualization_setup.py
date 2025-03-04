#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup Script
--------------------------------------------------

A powerful and beautiful terminal-based utility for setting up a complete
virtualization environment on Ubuntu with automated execution and rich visuals.

Features:
  • Updates package lists and installs virtualization packages
  • Manages virtualization services
  • Configures and recreates the default NAT network
  • Fixes storage permissions and user group settings
  • Updates VM network settings, configures autostart, and starts VMs
  • Verifies the overall setup and installs a systemd service
  • Runs fully unattended without requiring user interaction
  • Beautiful Nord-themed terminal interface with real-time progress tracking

Note: Run this script with root privileges.

Version: 2.0.0
"""

import atexit
import datetime
import grp
import os
import platform
import pwd
import random
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Set, Callable


# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
def install_missing_packages():
    """Install required Python packages if they're missing."""
    required_packages = ["rich", "pyfiglet"]
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing_packages,
                check=True,
                capture_output=True,
            )
            print("Successfully installed required packages. Restarting script...")
            # Restart the script to ensure imports work
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install required packages: {e}")
            print(
                "Please install them manually: pip install "
                + " ".join(missing_packages)
            )
            sys.exit(1)


# Try installing missing packages
install_missing_packages()

# Now import the installed packages
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
        TaskProgressColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
except ImportError as e:
    print(f"Error importing required libraries: {e}")
    print("Please install them manually: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    """Application configuration settings."""

    VERSION = "2.0.0"
    APP_NAME = "VirtSetup"
    APP_SUBTITLE = "Enhanced Virtualization Environment"

    # Host info
    try:
        HOSTNAME = socket.gethostname()
    except:
        HOSTNAME = "Unknown"

    # Terminal settings
    try:
        TERM_WIDTH = shutil.get_terminal_size().columns
    except:
        TERM_WIDTH = 80
    PROGRESS_WIDTH = min(50, TERM_WIDTH - 30)

    # Command timeouts
    DEFAULT_TIMEOUT = 300  # 5 minutes default timeout for commands

    # Virtualization-specific settings
    VM_STORAGE_PATHS = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]
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
    VIRTUALIZATION_SERVICES = ["libvirtd", "virtlogd"]

    VM_OWNER = "root"
    VM_GROUP = "libvirt-qemu"
    VM_DIR_MODE = 0o2770
    VM_FILE_MODE = 0o0660
    LIBVIRT_USER_GROUP = "libvirt"

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

    SERVICE_PATH = Path("/etc/systemd/system/virtualization_setup.service")
    SERVICE_CONTENT = """[Unit]
Description=Virtualization Setup Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {script_path}
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


# Create a Rich Console with Nord theme
console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
        }
    )
)


# ----------------------------------------------------------------
# Custom Exception Classes
# ----------------------------------------------------------------
class VirtualizationSetupError(Exception):
    """Base exception for Virtualization Setup errors."""

    pass


class CommandError(VirtualizationSetupError):
    """Raised when a system command fails."""

    pass


class NetworkConfigError(VirtualizationSetupError):
    """Raised when network configuration fails."""

    pass


class PermissionError(VirtualizationSetupError):
    """Raised when permission operations fail."""

    pass


class ServiceError(VirtualizationSetupError):
    """Raised when service management fails."""

    pass


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class VMState(Enum):
    """Enum representing different states of virtual machines."""

    RUNNING = auto()
    IDLE = auto()
    PAUSED = auto()
    SHUTDOWN = auto()
    CRASHED = auto()
    UNKNOWN = auto()

    @classmethod
    def from_libvirt_state(cls, state_string: str) -> "VMState":
        """Convert libvirt state string to VMState enum."""
        state_map = {
            "running": cls.RUNNING,
            "idle": cls.IDLE,
            "paused": cls.PAUSED,
            "shut off": cls.SHUTDOWN,
            "crashed": cls.CRASHED,
        }

        for libvirt_state, enum_state in state_map.items():
            if libvirt_state in state_string.lower():
                return enum_state

        return cls.UNKNOWN


@dataclass
class VirtualMachine:
    """
    Represents a virtual machine with its details and status.

    Attributes:
        id: The VM's ID in libvirt
        name: The VM's name
        state: Current state as a VMState enum
        state_text: Original state text from libvirt
        autostart: Whether autostart is enabled
    """

    id: str
    name: str
    state_text: str
    state: VMState = field(init=False)
    autostart: Optional[bool] = None

    def __post_init__(self):
        self.state = VMState.from_libvirt_state(self.state_text)

    @property
    def is_running(self) -> bool:
        """Check if the VM is in running state."""
        return self.state == VMState.RUNNING


@dataclass
class TaskResult:
    """
    Tracks the result of a setup task.

    Attributes:
        name: The task name
        success: Whether the task was successful
        message: Optional result message
        details: Additional details about the task execution
    """

    name: str
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


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
    compact_fonts = ["slant", "small", "standard", "digital", "big"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(AppConfig.APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
       _      _               _ _          _   _             
__   _(_)_ __| |_ _   _  __ _| (_)______ _| |_(_) ___  _ __  
\ \ / / | '__| __| | | |/ _` | | |_  / _` | __| |/ _ \| '_ \ 
 \ V /| | |  | |_| |_| | (_| | | |/ / (_| | |_| | (_) | | | |
  \_/ |_|_|   \__|\__,_|\__,_|_|_/___\__,_|\__|_|\___/|_| |_|
 ___  ___| |_ _   _ _ __                                     
/ __|/ _ \ __| | | | '_ \                                    
\__ \  __/ |_| |_| | |_) |                                   
|___/\___|\__|\__,_| .__/                                    
                   |_|                                       
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
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


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


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
        Text.from_markup(f"[{style}]{message}[/]"),
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
        if vm.is_running:
            state = Text(vm.state_text, style=f"bold {NordColors.GREEN}")
        else:
            state = Text(vm.state_text, style=f"dim {NordColors.POLAR_NIGHT_4}")

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


def display_results_table(results: List[TaskResult]) -> None:
    """
    Display a table summarizing task results.

    Args:
        results: List of TaskResult objects
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Setup Summary[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("Task", style=f"bold {NordColors.FROST_4}")
    table.add_column("Status", justify="center")
    table.add_column("Message", style=f"{NordColors.SNOW_STORM_1}")

    for result in results:
        task_name = result.name.replace("_", " ").title()
        status = (
            Text("✓ Success", style=f"bold {NordColors.GREEN}")
            if result.success
            else Text("✗ Failed", style=f"bold {NordColors.RED}")
        )
        table.add_row(task_name, status, result.message)

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
    timeout: int = AppConfig.DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print detailed information

    Returns:
        CompletedProcess instance with command results

    Raises:
        CommandError: If the command fails and check is True
    """
    try:
        cmd_str = " ".join(cmd)
        if verbose:
            print_step(f"Executing: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}")

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
        if e.stdout and verbose:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        if check:
            raise CommandError(f"Command failed: {' '.join(cmd)}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        if check:
            raise CommandError(f"Command timeout: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        if check:
            raise CommandError(f"Command error: {' '.join(cmd)}")
        raise


def run_direct_command(
    cmd: List[str], verbose: bool = False
) -> subprocess.CompletedProcess:
    """
    Run a command directly, capturing all output and properly handling errors.

    Args:
        cmd: Command and arguments as a list
        verbose: Whether to show verbose output

    Returns:
        CompletedProcess instance with command results
    """
    try:
        if verbose:
            print_step(f"Running command: {' '.join(cmd)}")

        result = subprocess.run(cmd, text=True, capture_output=True, check=False)

        if result.returncode != 0 and verbose:
            print_error(f"Command failed with exit code {result.returncode}")
            if result.stderr:
                print_error(f"Error output: {result.stderr}")

        return result
    except Exception as e:
        print_error(f"Failed to execute command: {e}")
        raise CommandError(f"Direct command failed: {' '.join(cmd)}")


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
    sig_name = str(sig)
    if hasattr(signal, "Signals"):
        try:
            sig_name = signal.Signals(sig).name
        except ValueError:
            pass

    print_message(f"Process interrupted by signal {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers (if supported by platform)
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except (AttributeError, ValueError):
    # Some signals might not be available on all platforms
    pass
atexit.register(cleanup)


# ----------------------------------------------------------------
# Virtualization Setup Functions
# ----------------------------------------------------------------
def update_system_packages() -> TaskResult:
    """
    Update the package lists using apt-get.

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Updating Package Lists"))

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Updating package lists...", spinner="dots"
        ):
            run_command(["apt-get", "update"])

        print_success("Package lists updated successfully")
        return TaskResult(
            name="package_update",
            success=True,
            message="Package lists updated successfully",
        )
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return TaskResult(
            name="package_update",
            success=False,
            message=f"Failed to update package lists: {e}",
        )


def install_virtualization_packages(packages: List[str]) -> TaskResult:
    """
    Install the required virtualization packages.

    Args:
        packages: List of packages to install

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Installing Virtualization Packages"))

    if not packages:
        print_warning("No packages specified")
        return TaskResult(
            name="package_install", success=True, message="No packages specified"
        )

    total: int = len(packages)
    print_message(f"Installing {total} package(s)")
    failed: List[str] = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
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
        return TaskResult(
            name="package_install",
            success=False,
            message=f"Failed to install {len(failed)} of {total} packages",
            details={"failed_packages": failed},
        )

    print_success("All virtualization packages installed successfully")
    return TaskResult(
        name="package_install",
        success=True,
        message=f"Successfully installed {total} packages",
    )


def manage_virtualization_services(services: List[str]) -> TaskResult:
    """
    Enable and start virtualization-related services.

    Args:
        services: List of services to manage

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Managing Virtualization Services"))

    if not services:
        print_warning("No services specified")
        return TaskResult(
            name="services", success=True, message="No services specified"
        )

    total: int = len(services) * 2  # Each service has enable and start actions
    failed: List[str] = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
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
        return TaskResult(
            name="services",
            success=False,
            message=f"Issues with {len(failed)} service operations",
            details={"failed_services": failed},
        )

    print_success("Services managed successfully")
    return TaskResult(
        name="services",
        success=True,
        message=f"Successfully managed {len(services)} services",
    )


def recreate_default_network() -> TaskResult:
    """
    Recreate the default NAT network.

    Returns:
        TaskResult with the outcome of the operation
    """
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
        net_xml_path.write_text(AppConfig.DEFAULT_NETWORK_XML)
        print_message("Created network definition file")

        # Define, start and autostart the network
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
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
            return TaskResult(
                name="network_recreation",
                success=True,
                message="Default network successfully recreated and activated",
            )

        print_error("Default network not running after recreation")
        return TaskResult(
            name="network_recreation",
            success=False,
            message="Default network not running after recreation",
        )
    except Exception as e:
        print_error(f"Error recreating network: {e}")
        return TaskResult(
            name="network_recreation",
            success=False,
            message=f"Error recreating network: {e}",
        )


def configure_default_network() -> TaskResult:
    """
    Ensure the default network exists and is active.

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Configuring Default Network"))

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Checking network status...", spinner="dots"
        ):
            net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)

        if "default" in net_list.stdout:
            print_message("Default network exists")
            if "active" not in net_list.stdout or "inactive" in net_list.stdout:
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

        return TaskResult(
            name="network_configuration",
            success=True,
            message="Default network properly configured",
        )
    except Exception as e:
        print_error(f"Network configuration error: {e}")
        return TaskResult(
            name="network_configuration",
            success=False,
            message=f"Network configuration error: {e}",
        )


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
                        state_text=" ".join(parts[2:]),
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


def set_vm_autostart(vms: List[VirtualMachine]) -> TaskResult:
    """
    Set virtual machines to start automatically.

    Args:
        vms: List of VirtualMachine objects

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Configuring VM Autostart"))

    if not vms:
        print_warning("No VMs found")
        return TaskResult(
            name="vm_autostart", success=True, message="No VMs found to configure"
        )

    failed: List[str] = []
    success_count = 0

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Setting VM autostart", total=len(vms))

        for vm in vms:
            progress.update(task, description=f"Configuring {vm.name}")
            try:
                if vm.autostart:
                    print_success(f"{vm.name} already set to autostart")
                    success_count += 1
                else:
                    run_command(["virsh", "autostart", vm.name])
                    vm.autostart = True
                    print_success(f"{vm.name} set to autostart")
                    success_count += 1
            except Exception as e:
                print_error(f"Autostart failed for {vm.name}: {e}")
                failed.append(vm.name)

            progress.advance(task)

    if failed:
        print_warning(f"Autostart configuration failed for: {', '.join(failed)}")
        return TaskResult(
            name="vm_autostart",
            success=False,
            message=f"Autostart failed for {len(failed)} of {len(vms)} VMs",
            details={"failed_vms": failed},
        )

    return TaskResult(
        name="vm_autostart",
        success=True,
        message=f"Successfully configured autostart for {success_count} VMs",
    )


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
        result = recreate_default_network()
        return result.success
    except Exception as e:
        print_error(f"Network verification error: {e}")
        return False


def start_virtual_machines(vms: List[VirtualMachine]) -> TaskResult:
    """
    Start any virtual machines that are not currently running.

    Args:
        vms: List of VirtualMachine objects

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Starting Virtual Machines"))

    if not vms:
        print_warning("No VMs found")
        return TaskResult(
            name="vm_start", success=True, message="No VMs found to start"
        )

    to_start: List[VirtualMachine] = [vm for vm in vms if not vm.is_running]

    if not to_start:
        print_success("All VMs are already running")
        return TaskResult(
            name="vm_start", success=True, message="All VMs are already running"
        )

    if not ensure_network_active_before_vm_start():
        print_error("Default network not active; VM start may fail")

    failed: List[str] = []
    success_count = 0

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting VMs", total=len(to_start))

        for vm in to_start:
            progress.update(task, description=f"Starting {vm.name}")
            success: bool = False

            for attempt in range(1, 4):  # Try up to 3 times
                try:
                    result = run_command(["virsh", "start", vm.name], check=False)
                    if result.returncode == 0:
                        print_success(f"{vm.name} started successfully")
                        vm.state = VMState.RUNNING
                        vm.state_text = "running"
                        success = True
                        success_count += 1
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
        return TaskResult(
            name="vm_start",
            success=False,
            message=f"Failed to start {len(failed)} of {len(to_start)} VMs",
            details={"failed_vms": failed},
        )

    print_success("Virtual machines started successfully")
    return TaskResult(
        name="vm_start",
        success=True,
        message=f"Successfully started {success_count} VMs",
    )


def fix_storage_permissions(paths: List[str]) -> TaskResult:
    """
    Fix storage directory and file permissions for VM storage.

    Args:
        paths: List of storage directory paths

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Fixing VM Storage Permissions"))

    if not paths:
        print_warning("No storage paths specified")
        return TaskResult(
            name="storage", success=True, message="No storage paths specified"
        )

    try:
        uid: int = pwd.getpwnam(AppConfig.VM_OWNER).pw_uid
        gid: int = grp.getgrnam(AppConfig.VM_GROUP).gr_gid
    except KeyError as e:
        print_error(f"User/group not found: {e}")
        return TaskResult(
            name="storage", success=False, message=f"User/group not found: {e}"
        )

    fixed_paths = []
    failed_paths = []

    for path_str in paths:
        path: Path = Path(path_str)
        print_message(f"Processing {path}")

        if not path.exists():
            print_warning(f"{path} does not exist; creating directory")
            try:
                path.mkdir(mode=AppConfig.VM_DIR_MODE, parents=True, exist_ok=True)
            except Exception as e:
                print_error(f"Failed to create directory {path}: {e}")
                failed_paths.append(str(path))
                continue

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
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Updating permissions for {path.name}", total=total_items
            )

            try:
                # Set permission on the root path
                os.chown(str(path), uid, gid)
                os.chmod(str(path), AppConfig.VM_DIR_MODE)
                progress.advance(task)

                errors = False

                # Process all subdirectories and files
                for root, dirs, files in os.walk(str(path)):
                    for d in dirs:
                        dpath = Path(root) / d
                        progress.update(task, description=f"Directory: {dpath.name}")
                        try:
                            os.chown(str(dpath), uid, gid)
                            os.chmod(str(dpath), AppConfig.VM_DIR_MODE)
                        except Exception as e:
                            print_warning(f"Error on {dpath}: {e}")
                            errors = True
                        progress.advance(task)

                    for f in files:
                        fpath = Path(root) / f
                        progress.update(task, description=f"File: {fpath.name}")
                        try:
                            os.chown(str(fpath), uid, gid)
                            os.chmod(str(fpath), AppConfig.VM_FILE_MODE)
                        except Exception as e:
                            print_warning(f"Error on {fpath}: {e}")
                            errors = True
                        progress.advance(task)

                if errors:
                    print_warning(f"Some permissions could not be set on {path}")
                else:
                    fixed_paths.append(str(path))
            except Exception as e:
                print_error(f"Failed to update permissions on {path}: {e}")
                failed_paths.append(str(path))

    if failed_paths:
        print_warning(f"Failed to fix permissions on: {', '.join(failed_paths)}")
        return TaskResult(
            name="storage",
            success=False,
            message=f"Fixed {len(fixed_paths)} paths, failed on {len(failed_paths)} paths",
            details={"fixed_paths": fixed_paths, "failed_paths": failed_paths},
        )

    print_success("Storage permissions updated successfully")
    return TaskResult(
        name="storage",
        success=True,
        message=f"Successfully updated permissions on {len(fixed_paths)} paths",
    )


def configure_user_groups() -> TaskResult:
    """
    Ensure that the invoking (sudo) user is a member of the required group.

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Configuring User Group Membership"))

    sudo_user: Optional[str] = os.environ.get("SUDO_USER")

    if not sudo_user:
        print_warning("SUDO_USER not set; skipping group configuration")
        return TaskResult(
            name="user_groups",
            success=True,
            message="SUDO_USER not set; skipping group configuration",
        )

    try:
        pwd.getpwnam(sudo_user)
        grp.getgrnam(AppConfig.LIBVIRT_USER_GROUP)
    except KeyError as e:
        print_error(f"User or group error: {e}")
        return TaskResult(
            name="user_groups", success=False, message=f"User or group error: {e}"
        )

    # Get current user groups
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary = grp.getgrgid(pwd.getpwnam(sudo_user).pw_gid).gr_name

    if primary not in user_groups:
        user_groups.append(primary)

    # Check if user is already in the required group
    if AppConfig.LIBVIRT_USER_GROUP in user_groups:
        print_success(
            f"User '{sudo_user}' is already in group '{AppConfig.LIBVIRT_USER_GROUP}'"
        )
        return TaskResult(
            name="user_groups",
            success=True,
            message=f"User '{sudo_user}' is already in group '{AppConfig.LIBVIRT_USER_GROUP}'",
        )

    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Adding user to group...", spinner="dots"
        ):
            run_command(
                ["usermod", "-a", "-G", AppConfig.LIBVIRT_USER_GROUP, sudo_user]
            )

        print_success(
            f"User '{sudo_user}' added to group '{AppConfig.LIBVIRT_USER_GROUP}'"
        )
        print_warning("Please log out and log back in for changes to take effect")
        return TaskResult(
            name="user_groups",
            success=True,
            message=f"User '{sudo_user}' added to group '{AppConfig.LIBVIRT_USER_GROUP}'. Logout required.",
        )
    except Exception as e:
        print_error(f"Failed to add user to group: {e}")
        return TaskResult(
            name="user_groups",
            success=False,
            message=f"Failed to add user to group: {e}",
        )


def verify_virtualization_setup() -> TaskResult:
    """
    Perform a series of checks to verify the virtualization environment.

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Verifying Virtualization Setup"))

    checks = [
        ("libvirtd Service", "systemctl is-active libvirtd", "active"),
        ("KVM Modules", "lsmod | grep kvm", "kvm"),
        ("Default Network", "virsh net-list", "default"),
    ]

    results = []
    check_details = {}

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=None, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Running verification checks",
            total=len(checks) + len(AppConfig.VM_STORAGE_PATHS),
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
                    check_details[name] = "OK"
                else:
                    print_error(f"{name}: FAILED")
                    results.append(False)
                    check_details[name] = "FAILED"
            except Exception as e:
                print_error(f"{name} check error: {e}")
                results.append(False)
                check_details[name] = f"ERROR: {e}"

            progress.advance(task)

        # Check storage paths
        for path_str in AppConfig.VM_STORAGE_PATHS:
            path = Path(path_str)
            progress.update(task, description=f"Checking storage: {path.name}")

            if path.exists():
                print_success(f"Storage exists: {path}")
                results.append(True)
                check_details[f"Storage {path}"] = "OK"
            else:
                print_error(f"Storage missing: {path}")
                try:
                    path.mkdir(mode=AppConfig.VM_DIR_MODE, parents=True, exist_ok=True)
                    print_success(f"Created storage directory: {path}")
                    results.append(True)
                    check_details[f"Storage {path}"] = "Created"
                except Exception as e:
                    print_error(f"Failed to create {path}: {e}")
                    results.append(False)
                    check_details[f"Storage {path}"] = f"FAILED: {e}"

            progress.advance(task)

    # Display verification results
    if all(results):
        display_panel(
            "All verification checks passed! Your virtualization environment is ready.",
            style=NordColors.GREEN,
            title="Verification Complete",
        )
        return TaskResult(
            name="verification",
            success=True,
            message="All verification checks passed",
            details=check_details,
        )
    else:
        failed_count = results.count(False)
        display_panel(
            f"{failed_count} verification check(s) failed. See details above.",
            style=NordColors.YELLOW,
            title="Verification Issues",
        )
        return TaskResult(
            name="verification",
            success=False,
            message=f"{failed_count} verification check(s) failed",
            details=check_details,
        )


def install_and_enable_service() -> TaskResult:
    """
    Install the systemd unit file for virtualization setup,
    reload systemd, enable and start the service.

    Returns:
        TaskResult with the outcome of the operation
    """
    console.print(create_section_header("Installing Systemd Service"))

    current_script = Path(sys.argv[0]).resolve()
    # Update service content with actual script path
    service_content = AppConfig.SERVICE_CONTENT.format(script_path=str(current_script))

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Setting up service", total=4)

            progress.update(task, description="Installing service file")
            AppConfig.SERVICE_PATH.write_text(service_content)
            print_success(f"Service file installed to {AppConfig.SERVICE_PATH}")
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

        return TaskResult(
            name="systemd_service",
            success=True,
            message="Systemd service installed, enabled, and started successfully",
        )
    except Exception as e:
        print_error(f"Failed to install and enable service: {e}")
        return TaskResult(
            name="systemd_service",
            success=False,
            message=f"Failed to install and enable service: {e}",
        )


# ----------------------------------------------------------------
# Main Execution Flow
# ----------------------------------------------------------------
def main() -> None:
    """Main function to orchestrate the virtualization setup."""
    # Clear the console and display the header
    console.clear()
    console.print(create_header())

    # Display system information
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Hostname: {AppConfig.HOSTNAME}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
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
        "This utility will automatically set up a complete virtualization environment on Ubuntu.\n"
        "It will install packages, configure networks, fix permissions, and start VMs.\n"
        "The setup process runs unattended and may take several minutes to complete.",
        style=NordColors.FROST_2,
        title="Setup Overview",
    )
    console.print()

    # Execute each setup task sequentially and collect results
    tasks_results = []

    # 1. Update package lists
    tasks_results.append(update_system_packages())
    console.print()

    # 2. Install virtualization packages
    tasks_results.append(
        install_virtualization_packages(AppConfig.VIRTUALIZATION_PACKAGES)
    )
    console.print()

    # 3. Manage virtualization services
    tasks_results.append(
        manage_virtualization_services(AppConfig.VIRTUALIZATION_SERVICES)
    )
    console.print()

    # 4. Install systemd service
    tasks_results.append(install_and_enable_service())
    console.print()

    # 5. Configure network (with retries)
    network_result = None
    for attempt in range(1, 4):
        print_message(f"Network configuration attempt {attempt}")
        network_result = configure_default_network()
        if network_result.success:
            break
        time.sleep(2)

    if not (network_result and network_result.success):
        print_error("Failed to configure network after multiple attempts")
        network_result = recreate_default_network()

    tasks_results.append(network_result)
    console.print()

    # 6. Fix storage permissions
    tasks_results.append(fix_storage_permissions(AppConfig.VM_STORAGE_PATHS))
    console.print()

    # 7. Configure user groups
    tasks_results.append(configure_user_groups())
    console.print()

    # 8. Get and display VM information
    vms = get_virtual_machines()
    if vms:
        print_success(f"Found {len(vms)} virtual machine(s)")
        display_vm_table(vms)

        # 9. Configure VM autostart
        tasks_results.append(set_vm_autostart(vms))
        console.print()

        # 10. Start VMs
        tasks_results.append(start_virtual_machines(vms))
    else:
        print_message("No virtual machines found")
        tasks_results.append(
            TaskResult(
                name="vm_autostart",
                success=True,
                message="No virtual machines found to configure",
            )
        )
        tasks_results.append(
            TaskResult(
                name="vm_start",
                success=True,
                message="No virtual machines found to start",
            )
        )

    console.print()

    # 11. Verify the setup
    tasks_results.append(verify_virtualization_setup())
    console.print()

    # Display summary table
    display_results_table(tasks_results)

    # Final status message
    success_count = sum(1 for result in tasks_results if result.success)
    total_tasks = len(tasks_results)

    if success_count == total_tasks:
        display_panel(
            "Virtualization environment setup completed successfully!\n\n"
            "Next steps:\n"
            "• Log out and log back in for group changes to take effect\n"
            "• Run 'virt-manager' to manage virtual machines\n"
            "• Check logs with 'journalctl -u libvirtd'\n"
            "• Systemd service is installed to maintain configuration",
            style=NordColors.GREEN,
            title="Setup Complete",
        )
    else:
        display_panel(
            f"Setup completed with {total_tasks - success_count} issue(s).\n"
            "Review the warnings and errors above for details.\n\n"
            "You may need to manually fix some issues and re-run the script.",
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
