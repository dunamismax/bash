#!/usr/bin/env python3
"""
SSH Selector
------------

A minimal, side-by-side CLI interface for SSH connections.
Displays device names and IP addresses using a Nord‑themed interface.
Select a machine by number to connect via SSH.

Usage:
  Run the script and select a machine by number to connect.

Version: 3.0.0
"""

# ----------------------------------------------------------------
# Imports & Dependency Check
# ----------------------------------------------------------------
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
    from rich.panel import Panel
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
DEFAULT_USERNAME = "sawyer"
SSH_COMMAND = "ssh"

# ----------------------------------------------------------------
# Nord‑Themed Colors & Console Setup
# ----------------------------------------------------------------
class NordColors:
    DARK3  = "#4C566A"  # Subtle dark shade
    LIGHT0 = "#D8DEE9"  # Light text
    FROST0 = "#8FBCBB"  # Primary cyan
    FROST1 = "#88C0D0"  # Light blue highlights
    FROST2 = "#81A1C1"  # Secondary blue
    FROST3 = "#5E81AC"  # Dark blue for numbers
    RED    = "#BF616A"  # Error messages
    YELLOW = "#EBCB8B"  # Warnings and special items

console = Console()

# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """Represents an SSH-accessible device."""
    name: str
    ip_address: str

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
# UI Components
# ----------------------------------------------------------------
def print_header() -> None:
    """Render and display the SSH header using pyfiglet in a Rich Panel."""
    ascii_art = pyfiglet.figlet_format("SSH", font="slant")
    header_panel = Panel(Text(ascii_art, justify="center", style=f"bold {NordColors.FROST1}"),
                         style=f"{NordColors.FROST1}")
    console.print(header_panel)

def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a table displaying device numbers, names, and IP addresses.
    'prefix' is prepended to the device number (e.g. "L" for local devices).
    """
    table = Table(show_header=True, header_style=f"bold {NordColors.FROST0}", box=None, expand=True)
    table.add_column("#", style=f"bold {NordColors.FROST3}", justify="right", width=3)
    table.add_column(title, style=f"bold {NordColors.FROST0}")
    table.add_column("IP Address", style=f"{NordColors.LIGHT0}")
    for idx, device in enumerate(devices, 1):
        table.add_row(f"{prefix}{idx}", device.name, device.ip_address)
    return table

# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username() -> str:
    """
    Ask the user whether to use the default username or enter a new one.
    """
    use_default = Prompt.ask(
        f"Use default username '[bold]{DEFAULT_USERNAME}[/]'?",
        choices=["y", "n"],
        default="y"
    )
    if use_default.lower() == "y":
        return DEFAULT_USERNAME
    else:
        return Prompt.ask("Enter username")

def connect_to_device(name: str, ip_address: str, username: str) -> None:
    """
    Clear the screen and initiate an SSH connection to the selected device.
    """
    console.clear()
    console.print(f"Connecting to [bold {NordColors.FROST1}]{name}[/] ([{NordColors.LIGHT0}]{ip_address}[/])")
    console.print(f"User: [bold {NordColors.FROST0}]{username}[/]")
    try:
        ssh_args = [SSH_COMMAND, f"{username}@{ip_address}"]
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        console.print(f"[bold {NordColors.RED}]Error:[/] {str(e)}")
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

    while True:
        console.clear()
        print_header()

        # Create tables for Tailscale and Local devices
        tailscale_table = create_device_table(tailscale_devices, "", "Tailscale Devices")
        local_table = create_device_table(local_devices, "L", "Local Devices")

        # Display the tables side by side
        console.print(Columns([tailscale_table, local_table]))
        console.print()
        console.print(
            f"[bold {NordColors.YELLOW}]Options:[/] "
            f"[bold {NordColors.FROST1}]1-{len(tailscale_devices)}[/] for Tailscale • "
            f"[bold {NordColors.FROST1}]L1-L{len(local_devices)}[/] for Local • "
            f"[bold {NordColors.FROST1}]q[/] to quit"
        )
        console.print()
        choice = Prompt.ask("Enter your choice")

        # Quit option
        if choice.lower() == "q":
            console.clear()
            console.print(f"[bold {NordColors.FROST1}]Goodbye![/]")
            break

        # Handle local device selection (choices starting with "L")
        elif choice.upper().startswith("L"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]
                    username = get_username()
                    connect_to_device(device.name, device.ip_address, username)
                else:
                    console.print(f"[bold {NordColors.RED}]Invalid local device number[/]")
                    input("Press Enter to continue...")
            except ValueError:
                console.print(f"[bold {NordColors.RED}]Invalid choice[/]")
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
                    console.print(f"[bold {NordColors.RED}]Invalid device number[/]")
                    input("Press Enter to continue...")
            except ValueError:
                console.print(f"[bold {NordColors.RED}]Invalid choice[/]")
                input("Press Enter to continue...")

# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\nExiting...")
        sys.exit(0)