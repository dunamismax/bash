#!/usr/bin/env python3
"""
SSH Selector
-----------

A clean, two-panel terminal interface for SSH connections.
Features Nord dark theme colors with a minimalist design.

Usage:
  Run the script to see a list of machines.
  Select by number to connect via SSH.

Version: 2.0.0
"""

import os
import sys
import math
from dataclasses import dataclass
from typing import List, Tuple

try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.prompt import Prompt
    from rich import box
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
ITEMS_PER_PAGE = 8  # Items displayed per page


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
    """Load Tailscale machines in the specified order."""
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
def create_ssh_banner() -> Text:
    """Create the SSH banner for the right panel."""
    ascii_art = pyfiglet.figlet_format("ssh", font="slant")
    return Text(ascii_art, style=f"bold {Nord.FROST1}")


def create_machine_list(machines: List[Machine], page: int = 1) -> Tuple[Panel, int]:
    """Create the machine list table with pagination."""
    # Calculate pagination
    total_items = len(machines)
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
    page = min(max(1, page), total_pages)
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    # Create table
    table = Table(box=None, show_header=True, expand=True)
    table.add_column("#", style=f"bold {Nord.FROST3}", justify="right", width=3)
    table.add_column("Machine", style=f"{Nord.FROST0}")
    table.add_column("IP", style=f"{Nord.LIGHT0}")
    table.add_column("OS", style=f"{Nord.FROST2}")

    # Add machine rows
    current_machines = machines[start_idx:end_idx]
    for idx, machine in enumerate(current_machines, start_idx + 1):
        table.add_row(str(idx), machine.name, machine.ip_address, machine.os)

    # Create pagination info
    footer = f"Page {page}/{total_pages}" if total_pages > 1 else ""

    # Wrap in panel
    panel = Panel(
        table,
        title="Tailscale Machines",
        title_align="left",
        border_style=Nord.DARK3,
        box=box.ROUNDED,
        padding=(0, 1),
        subtitle=footer,
        subtitle_align="right",
    )

    return panel, total_pages


def create_local_device_list(devices: List[LocalDevice]) -> Panel:
    """Create the local device list table."""
    table = Table(box=None, show_header=True, expand=True)
    table.add_column("#", style=f"bold {Nord.FROST3}", justify="right", width=3)
    table.add_column("Device", style=f"{Nord.FROST0}")
    table.add_column("IP", style=f"{Nord.LIGHT0}")
    table.add_column("MAC", style=f"{Nord.FROST2}")

    # Add device rows
    for idx, device in enumerate(devices, 1):
        table.add_row(f"L{idx}", device.name, device.ip_address, device.mac_address)

    # Wrap in panel
    panel = Panel(
        table,
        title="Local Devices",
        title_align="left",
        border_style=Nord.DARK3,
        box=box.ROUNDED,
        padding=(0, 1),
    )

    return panel


def create_help_text() -> Text:
    """Create the help text for command options."""
    text = Text()
    text.append("• ", style=Nord.YELLOW)
    text.append("1-N", style=Nord.FROST1)
    text.append(" - Connect to Tailscale machine\n")

    text.append("• ", style=Nord.YELLOW)
    text.append("L1-L4", style=Nord.FROST1)
    text.append(" - Connect to local device\n")

    text.append("• ", style=Nord.YELLOW)
    text.append("n/p", style=Nord.FROST1)
    text.append(" - Next/previous page\n")

    text.append("• ", style=Nord.YELLOW)
    text.append("q", style=Nord.FROST1)
    text.append(" - Quit")

    return text


# ==============================
# Layout Construction
# ==============================
def create_layout() -> Layout:
    """Create the two-panel layout."""
    layout = Layout()

    # Split into main and input areas
    layout.split(Layout(name="main", ratio=9), Layout(name="input", ratio=1))

    # Split main into left and right panels
    layout["main"].split_row(
        Layout(name="list", ratio=3), Layout(name="banner", ratio=1)
    )

    # Split list into Tailscale and local devices
    layout["list"].split(
        Layout(name="tailscale", ratio=3), Layout(name="local", ratio=2)
    )

    return layout


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


# ==============================
# Main Application
# ==============================
def main():
    """Main application entry point."""
    machines = load_machines()
    local_devices = load_local_devices()

    # Create layout
    layout = create_layout()

    # Setup initial state
    current_page = 1
    total_pages = math.ceil(len(machines) / ITEMS_PER_PAGE)

    while True:
        console.clear()

        # Create components
        machine_panel, total_pages = create_machine_list(machines, current_page)
        local_panel = create_local_device_list(local_devices)
        help_panel = Panel(
            create_help_text(),
            border_style=Nord.DARK3,
            box=box.ROUNDED,
            title="Commands",
            padding=(1, 2),
        )

        # Update layout
        layout["list"]["tailscale"].update(machine_panel)
        layout["list"]["local"].update(local_panel)
        layout["banner"].update(create_ssh_banner())
        layout["input"].update(help_panel)

        # Render layout
        console.print(layout)

        # Get user input
        choice = Prompt.ask("\nEnter your choice", console=console)

        # Handle commands
        if choice.lower() == "q":
            console.clear()
            console.print("[bold {Nord.FROST1}]Goodbye![/]")
            break

        # Handle pagination
        elif choice.lower() == "n" and current_page < total_pages:
            current_page += 1
            continue
        elif choice.lower() == "p" and current_page > 1:
            current_page -= 1
            continue

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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\nExiting...")
        sys.exit(0)
