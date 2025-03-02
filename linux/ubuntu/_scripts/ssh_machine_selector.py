#!/usr/bin/env python3
"""
SSH Selector
-----------

A minimal, side-by-side CLI interface for SSH connections.
Shows only device names and IP addresses with Nord dark theme.

Usage:
  Run the script and select a machine by number to connect.

Version: 3.0.0
"""

import os
import sys
from dataclasses import dataclass
from typing import List

try:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.columns import Columns
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# ==============================
# Configuration
# ==============================
DEFAULT_USERNAME = "sawyer"
SSH_COMMAND = "ssh"


# ==============================
# Nord Theme Colors
# ==============================
class Nord:
    DARK3 = "#4C566A"  # Dark shade for subtle elements
    LIGHT0 = "#D8DEE9"  # Light shade for text
    FROST0 = "#8FBCBB"  # Cyan for primary elements
    FROST1 = "#88C0D0"  # Light blue for highlights
    FROST2 = "#81A1C1"  # Blue for secondary elements
    FROST3 = "#5E81AC"  # Dark blue for numbers
    RED = "#BF616A"  # Error messages
    YELLOW = "#EBCB8B"  # Warnings/special items


# ==============================
# Console Setup
# ==============================
console = Console()


# ==============================
# Data Structures
# ==============================
@dataclass
class Device:
    """SSH-accessible device."""

    name: str
    ip_address: str


# ==============================
# Device Data
# ==============================
def load_tailscale_devices() -> List[Device]:
    """Load Tailscale devices in the specified order (Linux only)."""
    devices = [
        # Core machines first
        Device(name="ubuntu-server", ip_address="100.109.43.88"),
        Device(name="ubuntu-lenovo", ip_address="100.66.213.7"),
        # Raspberry Pi machines
        Device(name="raspberrypi-5", ip_address="100.105.117.18"),
        Device(name="raspberrypi-3", ip_address="100.69.116.5"),
        # Ubuntu server VMs
        Device(name="ubuntu-server-vm-01", ip_address="100.84.119.114"),
        Device(name="ubuntu-server-vm-02", ip_address="100.122.237.56"),
        Device(name="ubuntu-server-vm-03", ip_address="100.97.229.120"),
        Device(name="ubuntu-server-vm-04", ip_address="100.73.171.7"),
        # Ubuntu lenovo VMs
        Device(name="ubuntu-lenovo-vm-01", ip_address="100.107.79.81"),
        Device(name="ubuntu-lenovo-vm-02", ip_address="100.78.101.2"),
        Device(name="ubuntu-lenovo-vm-03", ip_address="100.95.115.62"),
        Device(name="ubuntu-lenovo-vm-04", ip_address="100.92.31.94"),
    ]
    return devices


def load_local_devices() -> List[Device]:
    """Load local network devices."""
    devices = [
        Device(name="ubuntu-server", ip_address="192.168.0.73"),
        Device(name="raspberrypi-5", ip_address="192.168.0.40"),
        Device(name="ubuntu-lenovo", ip_address="192.168.0.45"),
        Device(name="raspberrypi-3", ip_address="192.168.0.100"),
    ]
    return devices


# ==============================
# UI Components
# ==============================
def display_ssh_header():
    """Display the SSH header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format("ssh", font="slant")
    console.print(Text(ascii_art, style=f"bold {Nord.FROST1}"))


def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """Create a simple table for devices."""
    table = Table(
        box=None, show_header=True, expand=True, show_edge=False, padding=(0, 2)
    )

    # Add columns - only name and IP
    table.add_column("#", style=f"bold {Nord.FROST3}", justify="right", width=3)
    table.add_column(title, style=f"bold {Nord.FROST0}")
    table.add_column("IP Address", style=f"{Nord.LIGHT0}")

    # Add device rows
    for idx, device in enumerate(devices, 1):
        table.add_row(f"{prefix}{idx}", device.name, device.ip_address)

    return table


# ==============================
# SSH Connection
# ==============================
def connect_to_device(
    name: str, ip_address: str, username: str = DEFAULT_USERNAME
) -> None:
    """Connect to a device via SSH."""
    console.clear()
    console.print(
        f"Connecting to [bold {Nord.FROST1}]{name}[/] ([{Nord.LIGHT0}]{ip_address}[/])"
    )
    console.print(f"User: [bold {Nord.FROST0}]{username}[/]")

    try:
        ssh_args = [SSH_COMMAND, f"{username}@{ip_address}"]
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        console.print(f"[bold {Nord.RED}]Error:[/] {str(e)}")
        input("Press Enter to return...")


def get_username() -> str:
    """Get the username for SSH connection."""
    use_default = Prompt.ask(
        f"Use default username '[bold]{DEFAULT_USERNAME}[/]'?",
        choices=["y", "n"],
        default="y",
    )

    if use_default.lower() == "y":
        return DEFAULT_USERNAME
    else:
        return Prompt.ask("Enter username")


# ==============================
# Main Application
# ==============================
def main():
    """Main application entry point."""
    tailscale_devices = load_tailscale_devices()
    local_devices = load_local_devices()

    while True:
        # Clear screen
        console.clear()

        # Display SSH header
        display_ssh_header()

        # Create tables
        tailscale_table = create_device_table(
            tailscale_devices, "", "Tailscale Devices"
        )
        local_table = create_device_table(local_devices, "L", "Local Devices")

        # Display tables side by side
        console.print(Columns([tailscale_table, local_table]))

        # Display help text
        console.print()
        console.print(
            f"[bold {Nord.YELLOW}]Options:[/] [bold {Nord.FROST1}]1-{len(tailscale_devices)}[/] for Tailscale • [bold {Nord.FROST1}]L1-L{len(local_devices)}[/] for Local • [bold {Nord.FROST1}]q[/] to quit"
        )
        console.print()

        # Get user choice
        choice = Prompt.ask("Enter your choice")

        # Process user choice
        if choice.lower() == "q":
            console.clear()
            console.print(f"[bold {Nord.FROST1}]Goodbye![/]")
            break

        # Handle local device selection
        elif choice.upper().startswith("L"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    console.print(f"[bold {Nord.RED}]Invalid local device number[/]")
                    input("Press Enter to continue...")
            except ValueError:
                console.print(f"[bold {Nord.RED}]Invalid choice[/]")
                input("Press Enter to continue...")

        # Handle tailscale device selection
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tailscale_devices):
                    device = tailscale_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    console.print(f"[bold {Nord.RED}]Invalid device number[/]")
                    input("Press Enter to continue...")
            except ValueError:
                console.print(f"[bold {Nord.RED}]Invalid choice[/]")
                input("Press Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\nExiting...")
        sys.exit(0)
