#!/usr/bin/env python3
"""
SSH Selector
-----------

A clean, borderless CLI interface for SSH connections.
Displays all machines in a simple list with Nord dark theme colors.

Usage:
  Run the script and select a machine by number to connect.

Version: 2.0.0
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
    # Dark (background)
    DARK0 = "#2E3440"
    DARK1 = "#3B4252"
    DARK2 = "#434C5E"
    DARK3 = "#4C566A"

    # Light (text)
    LIGHT0 = "#D8DEE9"
    LIGHT1 = "#E5E9F0"
    LIGHT2 = "#ECEFF4"

    # Frost (blue accents)
    FROST0 = "#8FBCBB"
    FROST1 = "#88C0D0"
    FROST2 = "#81A1C1"
    FROST3 = "#5E81AC"

    # Aurora (accents)
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# ==============================
# Console Setup
# ==============================
console = Console()


# ==============================
# Data Structures
# ==============================
@dataclass
class Machine:
    """SSH-accessible machine."""

    name: str
    owner: str
    ip_address: str
    version: str
    os: str
    status: str = "Connected"


@dataclass
class LocalDevice:
    """Local network device."""

    name: str
    mac_address: str
    ip_address: str
    os: str
    status: str = "Active"


# ==============================
# Machine Data
# ==============================
def load_machines() -> List[Machine]:
    """Load all Tailscale machines in the specified order."""
    all_machines = [
        # Core machines first (server and lenovo)
        Machine(
            name="ubuntu-server",
            owner="dunamismax@github",
            ip_address="100.109.43.88",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-lenovo",
            owner="dunamismax@github",
            ip_address="100.66.213.7",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Expiry disabled",
        ),
        # Raspberry Pi machines
        Machine(
            name="raspberrypi-5",
            owner="dunamismax@github",
            ip_address="100.105.117.18",
            version="1.80.2",
            os="Linux 6.11.0-1008-raspi",
        ),
        Machine(
            name="raspberrypi-3",
            owner="dunamismax@github",
            ip_address="100.69.116.5",
            version="1.80.2",
            os="Linux 6.11.0-1008-raspi",
        ),
        # Ubuntu server VMs
        Machine(
            name="ubuntu-server-vm-01",
            owner="dunamismax@github",
            ip_address="100.84.119.114",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-server-vm-02",
            owner="dunamismax@github",
            ip_address="100.122.237.56",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-server-vm-03",
            owner="dunamismax@github",
            ip_address="100.97.229.120",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-server-vm-04",
            owner="dunamismax@github",
            ip_address="100.73.171.7",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        # Ubuntu lenovo VMs
        Machine(
            name="ubuntu-lenovo-vm-01",
            owner="dunamismax@github",
            ip_address="100.107.79.81",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-lenovo-vm-02",
            owner="dunamismax@github",
            ip_address="100.78.101.2",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-lenovo-vm-03",
            owner="dunamismax@github",
            ip_address="100.95.115.62",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        Machine(
            name="ubuntu-lenovo-vm-04",
            owner="dunamismax@github",
            ip_address="100.92.31.94",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
        ),
        # Windows VMs
        Machine(
            name="ubuntu-lenovo-windows-11-ent-ltsc-vm",
            owner="dunamismax@github",
            ip_address="100.103.166.85",
            version="1.80.2",
            os="Windows 11 24H2",
        ),
        Machine(
            name="ubuntu-server-windows-11-ent-ltsc-vm",
            owner="dunamismax@github",
            ip_address="100.66.128.35",
            version="1.80.2",
            os="Windows 11 24H2",
        ),
        # iOS device
        Machine(
            name="iphone-16-pro-max",
            owner="dunamismax@github",
            ip_address="100.72.245.118",
            version="1.80.2",
            os="iOS 18.3.1",
            status="Expiry disabled",
        ),
    ]
    return all_machines


def load_local_devices() -> List[LocalDevice]:
    """Load local network devices."""
    devices = [
        LocalDevice(
            name="ubuntu-server",
            mac_address="6C-1F-F7-04-59-50",
            ip_address="192.168.0.73",
            os="Linux 6.11.0-18-generic",
        ),
        LocalDevice(
            name="raspberrypi-5",
            mac_address="2C-CF-67-59-0E-03",
            ip_address="192.168.0.40",
            os="Linux 6.11.0-1008-raspi",
        ),
        LocalDevice(
            name="ubuntu-lenovo",
            mac_address="6C-1F-F7-1A-0B-28",
            ip_address="192.168.0.45",
            os="Linux 6.11.0-18-generic",
        ),
        LocalDevice(
            name="raspberrypi-3",
            mac_address="B8-27-EB-3A-11-89",
            ip_address="192.168.0.100",
            os="Linux 6.11.0-1008-raspi",
        ),
    ]
    return devices


# ==============================
# UI Components
# ==============================
def display_ssh_header():
    """Display the SSH header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format("ssh", font="slant")
    console.print(Text(ascii_art, style=f"bold {Nord.FROST1}"))


def display_machines(machines: List[Machine]):
    """Display the list of Tailscale machines."""
    # Create a simple table without borders
    table = Table(
        show_header=True, box=None, expand=True, show_edge=False, padding=(0, 1)
    )

    # Add columns
    table.add_column("#", style=f"bold {Nord.FROST3}", justify="right", width=3)
    table.add_column("Machine", style=f"bold {Nord.FROST0}")
    table.add_column("IP Address", style=f"{Nord.LIGHT0}")
    table.add_column("OS", style=f"{Nord.FROST2}")
    table.add_column("Status", style=f"{Nord.FROST1}")

    # Add machine rows
    for idx, machine in enumerate(machines, 1):
        status_style = (
            f"bold {Nord.GREEN}"
            if machine.status.lower() == "connected"
            else Nord.YELLOW
        )
        status_display = machine.status if machine.status else "Connected"

        table.add_row(
            str(idx),
            machine.name,
            machine.ip_address,
            machine.os,
            Text(status_display, style=status_style),
        )

    # Display header and table
    console.print(Text("\nTailscale Machines", style=f"bold {Nord.FROST0}"))
    console.print(table)


def display_local_devices(devices: List[LocalDevice]):
    """Display the list of local devices."""
    # Create a simple table without borders
    table = Table(
        show_header=True, box=None, expand=True, show_edge=False, padding=(0, 1)
    )

    # Add columns
    table.add_column("#", style=f"bold {Nord.FROST3}", justify="right", width=3)
    table.add_column("Device", style=f"bold {Nord.FROST0}")
    table.add_column("IP Address", style=f"{Nord.LIGHT0}")
    table.add_column("MAC Address", style=f"{Nord.FROST2}")
    table.add_column("OS", style=f"{Nord.FROST1}")

    # Add device rows
    for idx, device in enumerate(devices, 1):
        table.add_row(
            f"L{idx}", device.name, device.ip_address, device.mac_address, device.os
        )

    # Display header and table
    console.print(Text("\nLocal Devices", style=f"bold {Nord.FROST0}"))
    console.print(table)


def display_help():
    """Display help information."""
    console.print()
    console.print(Text("Options:", style=f"bold {Nord.YELLOW}"))
    console.print(
        f"• [bold {Nord.FROST1}]1-{len(load_machines())}[/] - Connect to Tailscale machine"
    )
    console.print(
        f"• [bold {Nord.FROST1}]L1-L{len(load_local_devices())}[/] - Connect to local device"
    )
    console.print(f"• [bold {Nord.FROST1}]q[/] - Quit")
    console.print()


# ==============================
# SSH Connection
# ==============================
def connect_to_machine(
    name: str, ip_address: str, username: str = DEFAULT_USERNAME
) -> None:
    """Connect to a machine via SSH."""
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
    machines = load_machines()
    local_devices = load_local_devices()

    while True:
        # Clear screen and display content
        console.clear()

        # Display SSH header
        display_ssh_header()

        # Display machine and device lists
        display_machines(machines)
        display_local_devices(local_devices)

        # Display help information
        display_help()

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
                    connect_to_machine(device.name, device.ip_address, username)
                else:
                    console.print(f"[bold {Nord.RED}]Invalid local device number[/]")
                    input("Press Enter to continue...")
            except ValueError:
                console.print(f"[bold {Nord.RED}]Invalid choice[/]")
                input("Press Enter to continue...")

        # Handle machine selection
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(machines):
                    machine = machines[idx]
                    username = get_username()
                    connect_to_machine(machine.name, machine.ip_address, username)
                else:
                    console.print(f"[bold {Nord.RED}]Invalid machine number[/]")
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
