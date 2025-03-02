#!/usr/bin/env python3
"""
SSH Selector
------------

A minimal, side-by-side CLI interface for SSH connections.
Displays device names, IP addresses, and connectivity status using a Nord‑themed interface.
Select a machine by number to connect via SSH.

Usage:
  Run the script and select a machine by number to connect.

Version: 4.0.0
"""

# ----------------------------------------------------------------
# Imports & Dependency Check
# ----------------------------------------------------------------
import os
import sys
import subprocess
import threading
from dataclasses import dataclass
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

try:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.traceback import install as install_rich_traceback
    from rich.style import Style
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
DEFAULT_USERNAME = "sawyer"
SSH_COMMAND = "ssh"
PING_TIMEOUT = 1.5  # seconds
PING_COUNT = 1


# ----------------------------------------------------------------
# Nord‑Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    DARK3 = "#4C566A"  # Subtle dark shade
    LIGHT0 = "#D8DEE9"  # Light text
    FROST0 = "#8FBCBB"  # Primary cyan
    FROST1 = "#88C0D0"  # Light blue highlights
    FROST2 = "#81A1C1"  # Secondary blue
    FROST3 = "#5E81AC"  # Dark blue for numbers
    RED = "#BF616A"  # Error messages
    YELLOW = "#EBCB8B"  # Warnings and special items
    GREEN = "#A3BE8C"  # Success messages
    ORANGE = "#D08770"  # Warning or attention


console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """Represents an SSH-accessible device."""

    name: str
    ip_address: str
    status: Optional[bool] = (
        None  # True for online, False for offline, None for unknown
    )


# ----------------------------------------------------------------
# Device Data Loaders
# ----------------------------------------------------------------
def load_tailscale_devices() -> List[Device]:
    """
    Return a list of Tailscale devices.
    Core machines come first, then Raspberry Pis, then VMs.
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
    """Return a list of devices on the local network."""
    return [
        Device(name="ubuntu-server", ip_address="192.168.0.73"),
        Device(name="raspberrypi-5", ip_address="192.168.0.40"),
        Device(name="ubuntu-lenovo", ip_address="192.168.0.45"),
        Device(name="raspberrypi-3", ip_address="192.168.0.100"),
    ]


# ----------------------------------------------------------------
# Network Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> bool:
    """
    Check if a device is reachable by pinging it.
    Returns True if the device responds, False otherwise.
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


def check_device_statuses(devices: List[Device], progress_callback=None) -> None:
    """
    Check the status of all devices in parallel and update their status attribute.

    Args:
        devices: List of Device objects to check
        progress_callback: Optional function to call when a device status is updated
    """

    def check_single_device(device, index):
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
def print_header() -> None:
    """Render and display the SSH header using pyfiglet in a Rich Panel with gradient colors."""
    # Create ASCII art with pyfiglet
    ascii_art = pyfiglet.figlet_format("SSH Selector", font="slant")

    # Create a gradient effect by splitting lines and applying different styles
    lines = ascii_art.split("\n")
    styled_lines = []

    # Create a gradient from one color to another
    colors = [
        f"bold {NordColors.FROST1}",
        f"bold {NordColors.FROST2}",
        f"bold {NordColors.FROST0}",
        f"bold {NordColors.FROST3}",
    ]

    for i, line in enumerate(lines):
        # Cycle through colors for gradient effect
        color_index = i % len(colors)
        styled_lines.append(Text(line, style=colors[color_index]))

    # Join all styled lines - create a properly flattened list for Text.assemble
    text_components = []
    for line in styled_lines:
        text_components.append(line)
        text_components.append("\n")

    # Remove the last newline character
    if text_components and text_components[-1] == "\n":
        text_components.pop()

    # Assemble all text components together
    header_text = Text.assemble(*text_components)

    # Create a panel with the styled header
    header_panel = Panel(
        header_text,
        border_style=Style(color=NordColors.FROST0),
        padding=(1, 2),
        title="v4.0.0",
        title_align="right",
        subtitle="Connect to your machines",
        subtitle_align="center",
    )

    console.print(header_panel)


def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a table displaying device numbers, names, IP addresses, and status.
    'prefix' is prepended to the device number (e.g. "L" for local devices).
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST0}",
        expand=True,
        title=title,
        title_style=f"bold {NordColors.FROST1}",
        title_justify="center",
        caption="Select a device by its number",
        caption_style=f"{NordColors.DARK3}",
        caption_justify="right",
    )

    table.add_column("#", style=f"bold {NordColors.FROST3}", justify="right", width=3)
    table.add_column("Name", style=f"bold {NordColors.FROST0}")
    table.add_column("IP Address", style=f"{NordColors.LIGHT0}")
    table.add_column("Status", justify="center", width=6)

    for idx, device in enumerate(devices, 1):
        # Create status indicator
        if device.status is True:
            status = Text("●", style=f"bold {NordColors.GREEN}")
        elif device.status is False:
            status = Text("●", style=f"bold {NordColors.RED}")
        else:
            status = Text("○", style=f"dim {NordColors.DARK3}")

        table.add_row(f"{prefix}{idx}", device.name, device.ip_address, status)

    return table


def display_help_panel() -> None:
    """Display a help panel with instructions and shortcuts."""
    help_panel = Panel(
        Text.from_markup(
            "\n".join(
                [
                    f"[bold {NordColors.FROST1}]Navigation:[/]",
                    f"• Enter device number ([bold {NordColors.FROST3}]1-n[/]) to connect to a Tailscale device",
                    f"• Enter [bold {NordColors.FROST3}]L1-Ln[/] to connect to a Local device",
                    f"• Press [bold {NordColors.FROST3}]r[/] to refresh device status",
                    f"• Press [bold {NordColors.FROST3}]h[/] to show/hide this help",
                    f"• Press [bold {NordColors.FROST3}]q[/] to quit",
                    "",
                    f"[bold {NordColors.FROST1}]Status Indicators:[/]",
                    f"• [bold {NordColors.GREEN}]●[/] Device is online and responding to ping",
                    f"• [bold {NordColors.RED}]●[/] Device is offline or not responding",
                    f"• [dim {NordColors.DARK3}]○[/] Status unknown or not checked",
                ]
            )
        ),
        title="Help & Commands",
        border_style=Style(color=NordColors.FROST2),
        padding=(1, 2),
    )
    console.print(help_panel)


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username() -> str:
    """
    Ask the user whether to use the default username or enter a new one.
    """
    use_default = Prompt.ask(
        Text.from_markup(
            f"Use default username '[bold {NordColors.FROST1}]{DEFAULT_USERNAME}[/]'?"
        ),
        choices=["y", "n"],
        default="y",
    )
    if use_default.lower() == "y":
        return DEFAULT_USERNAME
    else:
        return Prompt.ask("Enter username", style=f"bold {NordColors.FROST0}")


def connect_to_device(name: str, ip_address: str, username: str) -> None:
    """
    Clear the screen and initiate an SSH connection to the selected device.
    """
    console.clear()
    # Create a visually appealing connection info panel
    connection_info = Panel(
        Text.from_markup(
            f"\nConnecting to [bold {NordColors.FROST1}]{name}[/] ([{NordColors.LIGHT0}]{ip_address}[/])\n"
            f"User: [bold {NordColors.FROST0}]{username}[/]\n"
        ),
        title="SSH Connection",
        border_style=Style(color=NordColors.FROST1),
        padding=(1, 2),
    )
    console.print(connection_info)

    try:
        # Create a short delay for visual effect
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST1}"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Establishing connection...", total=None)
            # Small sleep for visual effect
            import time

            time.sleep(0.5)

        # Execute SSH command
        ssh_args = [SSH_COMMAND, f"{username}@{ip_address}"]
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        console.print(
            Panel(
                Text.from_markup(f"[bold {NordColors.RED}]Error:[/] {str(e)}"),
                border_style=Style(color=NordColors.RED),
                title="Connection Failed",
                padding=(1, 2),
            )
        )
        input("Press Enter to return...")


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main loop that displays the device tables and handles user input to initiate SSH connections.
    """
    tailscale_devices = load_tailscale_devices()
    local_devices = load_local_devices()
    show_help = True

    # Initial status check with progress display
    console.clear()
    console.print(
        Panel(
            "Checking device status...",
            title="Initializing",
            border_style=Style(color=NordColors.FROST2),
            padding=(1, 1),
        )
    )

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST1}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        status_task = progress.add_task(
            "Pinging devices...", total=len(tailscale_devices) + len(local_devices)
        )

        def update_progress(index):
            progress.advance(status_task)

        # Check all devices in parallel
        all_devices = tailscale_devices + local_devices
        check_device_statuses(all_devices, update_progress)

    while True:
        console.clear()
        print_header()

        # Create tables for Tailscale and Local devices
        tailscale_table = create_device_table(
            tailscale_devices, "", "Tailscale Devices"
        )
        local_table = create_device_table(local_devices, "L", "Local Devices")

        # Display the tables side by side
        console.print(Columns([tailscale_table, local_table]))
        console.print()

        # Show help panel if enabled
        if show_help:
            display_help_panel()
        else:
            console.print(
                Panel(
                    Text.from_markup(
                        f"[bold {NordColors.FROST1}]1-{len(tailscale_devices)}[/] for Tailscale • "
                        f"[bold {NordColors.FROST1}]L1-L{len(local_devices)}[/] for Local • "
                        f"[bold {NordColors.FROST1}]r[/] to refresh • "
                        f"[bold {NordColors.FROST1}]h[/] for help • "
                        f"[bold {NordColors.FROST1}]q[/] to quit"
                    ),
                    border_style=None,
                    padding=(1, 0),
                )
            )

        console.print()
        choice = Prompt.ask("Enter your choice", style=f"bold {NordColors.FROST0}")
        choice = choice.strip().lower()

        # Handle various commands
        if choice == "q":
            console.clear()
            console.print(
                Panel(
                    Text(
                        "Thanks for using SSH Selector!",
                        style=f"bold {NordColors.FROST1}",
                    ),
                    border_style=Style(color=NordColors.FROST0),
                    padding=(1, 2),
                )
            )
            break

        elif choice == "r":
            # Refresh device status
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST1}"),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                refresh_task = progress.add_task(
                    "Refreshing device status...", total=len(all_devices)
                )

                def update_refresh_progress(index):
                    progress.advance(refresh_task)

                check_device_statuses(all_devices, update_refresh_progress)

        elif choice == "h":
            # Toggle help panel
            show_help = not show_help

        # Handle local device selection (choices starting with "l")
        elif choice.startswith("l"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    console.print(
                        Panel(
                            Text(
                                f"Invalid local device number: {choice}",
                                style=f"bold {NordColors.RED}",
                            ),
                            border_style=Style(color=NordColors.RED),
                            padding=(1, 2),
                        )
                    )
                    input("Press Enter to continue...")
            except ValueError:
                console.print(
                    Panel(
                        Text(
                            f"Invalid choice: {choice}", style=f"bold {NordColors.RED}"
                        ),
                        border_style=Style(color=NordColors.RED),
                        padding=(1, 2),
                    )
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
                    console.print(
                        Panel(
                            Text(
                                f"Invalid device number: {choice}",
                                style=f"bold {NordColors.RED}",
                            ),
                            border_style=Style(color=NordColors.RED),
                            padding=(1, 2),
                        )
                    )
                    input("Press Enter to continue...")
            except ValueError:
                console.print(
                    Panel(
                        Text(
                            f"Invalid choice: {choice}", style=f"bold {NordColors.RED}"
                        ),
                        border_style=Style(color=NordColors.RED),
                        padding=(1, 2),
                    )
                )
                input("Press Enter to continue...")


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(
            Panel(
                Text("Operation cancelled by user", style=f"bold {NordColors.YELLOW}"),
                border_style=Style(color=NordColors.YELLOW),
                padding=(1, 2),
            )
        )
        sys.exit(0)
    except Exception as e:
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]Unhandled error:[/] {str(e)}"
                ),
                border_style=Style(color=NordColors.RED),
                title="Error",
                padding=(1, 2),
            )
        )
        console.print_exception()
        sys.exit(1)
