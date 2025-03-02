#!/usr/bin/env python3
"""
SSH Selector
--------------------------------------------------

A sophisticated terminal interface for managing SSH connections with elegant Nord theme styling.
Features device categorization, real-time connectivity status monitoring, and seamless connection.

This utility performs the following tasks:
  • Displays available devices from both Tailscale and local networks
  • Monitors connection status of each device in real-time
  • Provides visual indicators of device availability
  • Offers a streamlined interface for initiating SSH connections
  • Supports custom username configuration

Usage:
  Run the script and select a device by number to connect via SSH.
  - Numbers 1-N: Connect to Tailscale devices
  - L1-LN: Connect to local network devices
  - r: Refresh device status
  - q: Quit the application

Version: 6.0.0
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable

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
DEFAULT_USERNAME: str = "sawyer"
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 1.5  # seconds
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30  # seconds
VERSION: str = "6.0.0"
APP_NAME: str = "SSH Selector"
APP_SUBTITLE: str = "Secure Connection Manager"


# ----------------------------------------------------------------
# Nord-Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Darker background shade
    POLAR_NIGHT_3 = "#434C5E"  # Dark background shade
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


# Create a Rich Console with a dark background for better contrast
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with its connection details and status.

    Attributes:
        name: The hostname or device identifier
        ip_address: IP address for SSH connection
        status: Connection status (True=online, False=offline, None=unknown)
    """

    name: str
    ip_address: str
    status: Optional[bool] = (
        None  # True for online, False for offline, None for unknown
    )


# ----------------------------------------------------------------
# Console and Logging Helpers (Nord-Themed)
# ----------------------------------------------------------------
def print_header(text: str) -> None:
    """
    Print a large, stylized ASCII art header using Pyfiglet with advanced Nord styling.

    Args:
        text: The text to convert to ASCII art
    """
    # Create ASCII art with a smaller font for better terminal compatibility
    # Use "small" or "mini" font to prevent cutoff issues
    ascii_art: str = pyfiglet.figlet_format(text, font="small")

    # Split the art into lines for advanced styling
    lines = ascii_art.split("\n")
    styled_text = ""

    # Apply a frost gradient effect to the header
    frost_colors = [
        NordColors.FROST_2,  # Light blue
        NordColors.FROST_1,  # Light cyan
        NordColors.FROST_3,  # Medium blue
        NordColors.FROST_4,  # Dark blue
    ]

    for i, line in enumerate(lines):
        if line.strip():  # Skip empty lines
            color = frost_colors[i % len(frost_colors)]
            styled_text += f"[bold {color}]{line}[/]\n"

    # Display the header in a panel with Nord styling
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),  # Reduced padding to avoid cutoff
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    console.print(header_panel)


def print_section(text: str) -> None:
    """
    Print a styled section header.

    Args:
        text: The section header text
    """
    console.print(
        f"\n[bold {NordColors.FROST_2}]== {text} ==[/bold {NordColors.FROST_2}]"
    )


def print_step(text: str) -> None:
    """
    Print a status step message.

    Args:
        text: The step message to display
    """
    console.print(f"[{NordColors.FROST_3}]• {text}[/{NordColors.FROST_3}]")


def print_success(text: str) -> None:
    """
    Print a success message.

    Args:
        text: The success message to display
    """
    console.print(f"[bold {NordColors.GREEN}]✓ {text}[/bold {NordColors.GREEN}]")


def print_warning(text: str) -> None:
    """
    Print a warning message.

    Args:
        text: The warning message to display
    """
    console.print(f"[bold {NordColors.YELLOW}]⚠ {text}[/bold {NordColors.YELLOW}]")


def print_error(text: str) -> None:
    """
    Print an error message.

    Args:
        text: The error message to display
    """
    console.print(f"[bold {NordColors.RED}]✗ {text}[/bold {NordColors.RED}]")


def display_message_panel(
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
    Raises an error with detailed output if the command fails.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results

    Raises:
        subprocess.CalledProcessError: If the command fails and check is True
        subprocess.TimeoutExpired: If the command times out
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
            console.print(
                f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/bold {NordColors.RED}]"
            )
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    console.print()


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Device Data Functions
# ----------------------------------------------------------------
def load_tailscale_devices() -> List[Device]:
    """
    Load a list of Tailscale devices.

    Returns:
        List of Device objects representing Tailscale network devices
    """
    return [
        Device(name="ubuntu-server", ip_address="100.109.43.88"),
        Device(name="ubuntu-lenovo", ip_address="100.66.213.7"),
        Device(name="raspberrypi-5", ip_address="100.105.117.18"),
        Device(name="raspberrypi-3", ip_address="100.69.116.5"),
        Device(name="ubuntu-server-vm-01", ip_address="100.84.119.114"),
        Device(name="ubuntu-server-vm-02", ip_address="100.122.237.56"),
        Device(name="ubuntu-server-vm-03", ip_address="100.97.229.120"),
        Device(name="ubuntu-server-vm-04", ip_address="100.73.171.7"),
        Device(name="ubuntu-lenovo-vm-01", ip_address="100.107.79.81"),
        Device(name="ubuntu-lenovo-vm-02", ip_address="100.78.101.2"),
        Device(name="ubuntu-lenovo-vm-03", ip_address="100.95.115.62"),
        Device(name="ubuntu-lenovo-vm-04", ip_address="100.92.31.94"),
    ]


def load_local_devices() -> List[Device]:
    """
    Load a list of devices on the local network.

    Returns:
        List of Device objects representing local network devices
    """
    return [
        Device(name="ubuntu-server", ip_address="192.168.0.73"),
        Device(name="raspberrypi-5", ip_address="192.168.0.40"),
        Device(name="ubuntu-lenovo", ip_address="192.168.0.31"),
        Device(name="raspberrypi-3", ip_address="192.168.0.100"),
    ]


# ----------------------------------------------------------------
# Network Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> bool:
    """
    Check if a device is reachable by pinging it.

    Args:
        ip_address: The IP address to ping

    Returns:
        True if the device responds, False otherwise
    """
    try:
        # Different ping commands for different platforms
        if sys.platform == "win32":
            cmd = [
                "ping",
                "-n",
                str(PING_COUNT),
                "-w",
                str(int(PING_TIMEOUT * 1000)),
                ip_address,
            ]
        else:  # Linux, macOS, etc.
            cmd = [
                "ping",
                "-c",
                str(PING_COUNT),
                "-W",
                str(int(PING_TIMEOUT)),
                ip_address,
            ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PING_TIMEOUT + 1,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def check_device_statuses(
    devices: List[Device], progress_callback: Optional[Callable[[int], None]] = None
) -> None:
    """
    Check the status of all devices in parallel and update their status attribute.

    Args:
        devices: List of devices to check
        progress_callback: Optional callback function to update progress
    """

    def check_single_device(device: Device, index: int) -> None:
        """Check a single device's connectivity status."""
        device.status = ping_device(device.ip_address)
        if progress_callback:
            progress_callback(index)

    with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() or 4)) as executor:
        # Submit all ping tasks to the executor
        futures = [
            executor.submit(check_single_device, device, i)
            for i, device in enumerate(devices)
        ]

        # Wait for all futures to complete
        for future in futures:
            future.result()  # This will re-raise any exceptions that occurred


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_ascii_header() -> Panel:
    """
    Create an enhanced ASCII art header with gradient styling.

    Returns:
        Panel containing the styled ASCII art header
    """
    # Using a more compact header to avoid display issues
    header = """
  ___ ___ _  _   ___ ___ _    ___ ___ _____ ___  ___ 
 / __/ __| || | / __| __| |  | __/ __|_   _/ _ \| _ \\
 \__ \__ \ __ | \__ \ _|| |__| _| (__  | || (_) |   /
 |___/___/_||_| |___/___|____|___\___| |_| \___/|_|_\\
    """

    # Apply gradient styling to the custom ASCII art
    styled_header = ""
    lines = header.strip().split("\n")

    colors = [
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_1,
        NordColors.FROST_4,
        NordColors.FROST_2,
    ]

    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled_header += f"[bold {color}]{line}[/]\n"

    # Create panel with the styled header
    header_panel = Panel(
        Text.from_markup(styled_header),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def typing_animation(text: str, speed: float = 0.01) -> None:
    """
    Display text with a typing animation effect.

    Args:
        text: The text to display (can include Rich markup)
        speed: Delay between characters in seconds
    """
    # Simpler implementation to avoid style issues
    console = Console(highlight=False)
    full_text = Text.from_markup(text)

    # Display characters one by one with proper styling
    for i in range(len(full_text.plain)):
        # Print up to the current character
        partial_text = Text.from_markup(text)
        partial_text.plain = full_text.plain[: i + 1]
        console.print(partial_text, end="\r")
        time.sleep(speed)

    console.print()


def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a table displaying device information and status.

    Args:
        devices: List of Device objects to display
        prefix: Prefix for device numbers (e.g., "L" for local devices)
        title: Title for the device table

    Returns:
        A Rich Table object containing the device information
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
        box=None,
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center", width=10)

    for idx, device in enumerate(devices, 1):
        # Create status indicator
        if device.status is True:
            status = Text("● ONLINE", style=f"bold {NordColors.GREEN}")
        elif device.status is False:
            status = Text("● OFFLINE", style=f"bold {NordColors.RED}")
        else:
            status = Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")

        table.add_row(f"{prefix}{idx}", device.name, device.ip_address, status)

    return table


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username() -> str:
    """
    Ask the user whether to use the default username or enter a new one.

    Returns:
        The username to use for SSH connections
    """
    console.print(
        f"[bold {NordColors.FROST_2}]Use default username '[/][{NordColors.SNOW_STORM_1}]{DEFAULT_USERNAME}[/][bold {NordColors.FROST_2}]'? (y/n)[/]",
        end=" ",
    )
    choice = input().strip().lower()

    if choice != "n":
        return DEFAULT_USERNAME
    else:
        console.print(f"[bold {NordColors.FROST_2}]Enter username:[/]", end=" ")
        return input()


def connection_animation(
    device_name: str, ip_address: str, duration: float = 2.0
) -> None:
    """
    Display a connection animation with progress and status messages.

    Args:
        device_name: Name of the device being connected to
        ip_address: IP address of the device
        duration: Approximate duration of the animation
    """
    with Progress(
        TextColumn(f"[bold {NordColors.FROST_2}]Establishing connection"),
        SpinnerColumn("dots12", style=f"bold {NordColors.FROST_1}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn(f"[bold {NordColors.FROST_3}]{{task.percentage:>3.0f}}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Connecting", total=100)

        # Simulate connection process with progress updates
        while not progress.finished:
            progress.update(task, advance=random.uniform(0.5, 2.0))
            time.sleep(0.05)

    # Show connection sequence text using improved typing animation
    console.print()
    typing_animation(
        f"[bold {NordColors.FROST_2}]> Initializing secure channel to {device_name}...[/]",
        0.01,
    )
    typing_animation(
        f"[bold {NordColors.FROST_2}]> Negotiating encryption parameters...[/]", 0.01
    )
    typing_animation(
        f"[bold {NordColors.FROST_2}]> Establishing SSH tunnel to {ip_address}...[/]",
        0.01,
    )
    typing_animation(
        f"[bold {NordColors.FROST_2}]> Connection established. Launching secure shell...[/]",
        0.01,
    )
    console.print()


def connect_to_device(name: str, ip_address: str, username: str) -> None:
    """
    Clear the screen and initiate an SSH connection to the selected device.

    Args:
        name: Device name to connect to
        ip_address: Device IP address
        username: Username for SSH connection
    """
    console.clear()
    console.print(create_ascii_header())

    # Create a fancy connection panel
    connection_panel = Panel(
        Text.from_markup(
            f"\n[bold {NordColors.FROST_2}]Device:[/] [{NordColors.SNOW_STORM_2}]{name}[/]\n"
            f"[bold {NordColors.FROST_2}]Address:[/] [{NordColors.SNOW_STORM_2}]{ip_address}[/]\n"
            f"[bold {NordColors.FROST_2}]User:[/] [{NordColors.SNOW_STORM_2}]{username}[/]\n"
        ),
        title=f"[bold {NordColors.FROST_3}]SSH Connection[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(connection_panel)

    try:
        # Simple connection message instead of animation to avoid errors
        console.print()
        console.print(
            f"[bold {NordColors.FROST_2}]> Initializing secure channel to {name}...[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]> Negotiating encryption parameters...[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]> Establishing SSH tunnel to {ip_address}...[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]> Connection established. Launching secure shell...[/]"
        )
        console.print()

        time.sleep(1.5)  # Brief pause for visual effect

        # Execute SSH command
        ssh_args = [SSH_COMMAND, f"{username}@{ip_address}"]
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]Connection Error:[/] {str(e)}"
                ),
                border_style=Style(color=NordColors.RED),
                title="Connection Failed",
                padding=(1, 2),
            )
        )
        console.print(
            f"[{NordColors.SNOW_STORM_1}]Press Enter to return to selection screen...[/]"
        )
        input()


# ----------------------------------------------------------------
# Device Status Refresh
# ----------------------------------------------------------------
def refresh_device_statuses(devices: List[Device]) -> None:
    """
    Refresh the status of all devices with a progress animation.

    Args:
        devices: List of devices to refresh
    """
    console.clear()
    console.print(create_ascii_header())

    display_message_panel(
        "Refreshing device status", style=NordColors.FROST_3, title="Network Scan"
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Refreshing"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        refresh_task = progress.add_task("Refreshing", total=len(devices))

        def update_refresh_progress(index):
            progress.advance(refresh_task)

        check_device_statuses(devices, update_refresh_progress)


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main application function that handles the UI flow and user interaction.
    """
    # Create device lists
    tailscale_devices = load_tailscale_devices()
    local_devices = load_local_devices()
    all_devices = tailscale_devices + local_devices

    # Initial status check with enhanced styling
    console.clear()
    console.print(create_ascii_header())

    display_message_panel(
        "Scanning network for available devices",
        style=NordColors.FROST_3,
        title="Initialization",
    )

    with Progress(
        SpinnerColumn("dots12", style=f"bold {NordColors.FROST_3}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Scanning devices"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning", total=len(all_devices))

        def update_progress(index):
            progress.advance(scan_task)

        # Check all devices in parallel
        check_device_statuses(all_devices, update_progress)

    while True:
        console.clear()
        console.print(create_ascii_header())

        # Display the current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()

        # Create tables for Tailscale and Local devices
        tailscale_table = create_device_table(
            tailscale_devices, "", "Tailscale Devices"
        )
        local_table = create_device_table(local_devices, "L", "Local Devices")

        # Display the tables side by side with improved layout
        console.print(
            Columns(
                [
                    Panel(
                        tailscale_table,
                        border_style=Style(color=NordColors.FROST_4),
                        padding=(0, 1),
                    ),
                    Panel(
                        local_table,
                        border_style=Style(color=NordColors.FROST_4),
                        padding=(0, 1),
                    ),
                ]
            )
        )
        console.print()

        # Enhanced command bar with Nord styling
        commands = [
            f"[bold {NordColors.FROST_3}]1-{len(tailscale_devices)}[/]: [{NordColors.SNOW_STORM_2}]Tailscale[/]",
            f"[bold {NordColors.FROST_3}]L1-L{len(local_devices)}[/]: [{NordColors.SNOW_STORM_2}]Local[/]",
            f"[bold {NordColors.FROST_3}]r[/]: [{NordColors.SNOW_STORM_2}]Refresh[/]",
            f"[bold {NordColors.FROST_3}]q[/]: [{NordColors.SNOW_STORM_2}]Quit[/]",
        ]

        command_text = " | ".join(commands)
        console.print(
            Panel(
                Align.center(Text.from_markup(command_text)),
                border_style=Style(color=NordColors.FROST_2),
                padding=(1, 1),
            )
        )

        console.print()
        console.print(f"[bold {NordColors.FROST_2}]Enter your choice:[/]", end=" ")
        choice = input().strip().lower()

        # Handle commands
        if choice == "q":
            console.clear()

            # Farewell message
            console.print(
                Panel(
                    Text(
                        "Thank you for using SSH Selector!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            break

        elif choice == "r":
            # Refresh device status
            refresh_device_statuses(all_devices)

        # Handle local device selection (choices starting with "l")
        elif choice.startswith("l"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    display_message_panel(
                        f"Invalid local device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    input("Press Enter to continue...")
            except ValueError:
                display_message_panel(
                    f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                )
                input("Press Enter to continue...")

        # Handle Tailscale device selection
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tailscale_devices):
                    device = tailscale_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    display_message_panel(
                        f"Invalid device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    input("Press Enter to continue...")
            except ValueError:
                display_message_panel(
                    f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                )
                input("Press Enter to continue...")


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_message_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(0)
    except Exception as e:
        display_message_panel(
            f"Unhandled error: {str(e)}", style=NordColors.RED, title="Error"
        )
        console.print_exception()
        sys.exit(1)
