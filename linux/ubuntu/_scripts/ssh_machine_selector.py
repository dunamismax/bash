#!/usr/bin/env python3
"""
SSH Selector
--------------------------------------------------

A streamlined terminal interface for managing SSH connections with Nord theme styling.
Features device categorization, real-time connectivity status monitoring, and seamless connection.

Usage:
  Run the script and select a device by number to connect via SSH.
  - Numbers 1-N: Connect to Tailscale devices
  - L1-LN: Connect to local network devices
  - r: Refresh device status
  - q: Quit the application

Version: 6.1.0
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
VERSION: str = "6.1.0"
APP_NAME: str = "SSH Selector"
APP_SUBTITLE: str = "Secure Connection Manager"


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
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["small", "smslant", "mini", "digital", "times"]

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
  ___ ___ _  _   ___ ___ _    ___ ___ _____ ___  ___ 
 / __/ __| || | / __| __| |  | __/ __|_   _/ _ \| _ \\
 \__ \__ \ __ | \__ \ _|| |__| _| (__  | || (_) |   /
 |___/___/_||_| |___/___|____|___\___| |_| \___/|_|_\\
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

    # Add decorative tech elements (shorter than before)
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),  # Reduced padding
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
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
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
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
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

    with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as executor:
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
        return input().strip()


def connect_to_device(name: str, ip_address: str, username: str) -> None:
    """
    Clear the screen and initiate an SSH connection to the selected device.

    Args:
        name: Device name to connect to
        ip_address: Device IP address
        username: Username for SSH connection
    """
    console.clear()
    console.print(create_header())

    # Create a connection panel
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
        # Simple connection message
        console.print()
        print_message("Initializing secure channel...", NordColors.FROST_2, ">")
        print_message("Negotiating encryption parameters...", NordColors.FROST_2, ">")
        print_message(
            f"Establishing SSH tunnel to {ip_address}...", NordColors.FROST_2, ">"
        )
        print_message(
            "Connection established. Launching secure shell...", NordColors.FROST_2, ">"
        )
        console.print()

        time.sleep(1)  # Brief pause for visual effect

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
    console.print(create_header())

    display_panel(
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

    # Initial status check
    console.clear()
    console.print(create_header())

    display_panel(
        "Scanning network for available devices",
        style=NordColors.FROST_3,
        title="Initialization",
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
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
        console.print(create_header())

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

        # Display the tables side by side
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
        console.print()
        console.print(f"[bold {NordColors.FROST_2}]Enter your choice:[/]", end=" ")
        choice = input().strip().lower()

        # Handle commands
        if choice == "q":
            console.clear()
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
                    display_panel(
                        f"Invalid local device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    input("Press Enter to continue...")
            except ValueError:
                display_panel(
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
                    display_panel(
                        f"Invalid device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    input("Press Enter to continue...")
            except ValueError:
                display_panel(
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
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(0)
    except Exception as e:
        display_panel(f"Unhandled error: {str(e)}", style=NordColors.RED, title="Error")
        console.print_exception()
        sys.exit(1)
