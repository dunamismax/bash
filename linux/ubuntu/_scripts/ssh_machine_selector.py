#!/usr/bin/env python3
"""
SSH Machine Selector
-------------------

A beautiful, interactive terminal-based utility for connecting to SSH machines.
This tool provides:
  • A numbered list of available machines
  • Quick selection by number
  • SSH connection handling with proper terminal management
  • Visual indication of connection status
  • Local IP device management

Features a Nord-themed interface for easy readability and selection.

Usage:
  Simply run the script or alias it to 'ssh' for quick access.
  Select a machine by number to connect via SSH.

Version: 1.1.0
"""

import os
import sys
import subprocess
import shutil
import platform
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, IntPrompt
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich import box
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "SSH Machine Selector"
VERSION = "1.1.0"
DEFAULT_USERNAME = "sawyer"  # Default SSH username
SSH_COMMAND = "ssh"  # SSH command to use

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()


class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark/background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"

    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"

    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"

    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)


# ==============================
# Machine Data Structure
# ==============================
@dataclass
class Machine:
    """Represents an SSH-accessible machine."""

    name: str
    owner: str
    ip_address: str
    version: str
    os: str
    status: str = "Unknown"

    def get_display_name(self) -> str:
        """Get formatted display name for the machine."""
        return f"{self.name}"

    def get_display_ip(self) -> str:
        """Get formatted IP address."""
        return f"{self.ip_address}"

    def get_display_os(self) -> str:
        """Get formatted OS info."""
        return f"{self.os}"

    def get_display_status(self) -> str:
        """Get formatted status with appropriate coloring."""
        if self.status.lower() == "connected":
            return Text(self.status, style=f"bold {NordColors.NORD14}")
        elif "disabled" in self.status.lower():
            return Text(self.status, style=f"bold {NordColors.NORD13}")
        else:
            return Text(self.status, style="dim")


@dataclass
class LocalDevice:
    """Represents a local network device with reserved IP."""

    name: str
    mac_address: str
    ip_address: str
    status: str = "Active"

    def get_display_status(self) -> Text:
        """Get formatted status with appropriate coloring."""
        if self.status.lower() == "active":
            return Text(self.status, style=f"bold {NordColors.NORD14}")
        elif self.status.lower() == "inactive":
            return Text(self.status, style="dim")
        else:
            return Text(self.status, style=f"bold {NordColors.NORD13}")


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> Panel:
    """Create a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    return Panel(
        Text(ascii_art, style=f"bold {NordColors.NORD8}"),
        border_style=NordColors.NORD10,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def create_section(title: str) -> Panel:
    """Create a formatted section header."""
    return Panel(
        Text(title, style=f"bold {NordColors.NORD8}"),
        border_style=NordColors.NORD9,
        box=box.HEAVY_EDGE,
        padding=(0, 2),
    )


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(Text(message, style=NordColors.NORD9))


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(Text(f"✓ {message}", style=f"bold {NordColors.NORD14}"))


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(Text(f"⚠ {message}", style=f"bold {NordColors.NORD13}"))


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(Text(f"✗ {message}", style=f"bold {NordColors.NORD11}"))


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)


def get_user_number(prompt: str, min_value: int = 1, max_value: int = 100) -> int:
    """Get a number from the user with a styled prompt."""
    return IntPrompt.ask(
        f"[bold {NordColors.NORD15}]{prompt}[/]",
        min_value=min_value,
        max_value=max_value,
    )


# ==============================
# Machine List Functions
# ==============================
def load_machines() -> List[Machine]:
    """Load the list of machines."""
    # Hardcoded machine list from the data provided
    machines = [
        Machine(
            name="ubuntu-lenovo",
            owner="dunamismax@github",
            ip_address="100.66.213.7",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="raspberrypi-3",
            owner="dunamismax@github",
            ip_address="100.69.116.5",
            version="1.80.2",
            os="Linux 6.11.0-1008-raspi",
            status="1:53 PM EST",
        ),
        Machine(
            name="raspberrypi-5",
            owner="dunamismax@github",
            ip_address="100.94.91.82",
            version="1.80.2",
            os="Linux 6.11.0-1008-raspi",
            status="1:50 PM EST",
        ),
        Machine(
            name="ubuntu-lenovo-vm-01",
            owner="dunamismax@github",
            ip_address="100.107.79.81",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-lenovo-vm-02",
            owner="dunamismax@github",
            ip_address="100.78.101.2",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-lenovo-vm-03",
            owner="dunamismax@github",
            ip_address="100.95.115.62",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-lenovo-vm-04",
            owner="dunamismax@github",
            ip_address="100.92.31.94",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-lenovo-windows-11-ent-ltsc-vm",
            owner="dunamismax@github",
            ip_address="100.103.166.85",
            version="1.80.2",
            os="Windows 11 24H2",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server",
            owner="dunamismax@github",
            ip_address="100.109.43.88",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server-vm-01",
            owner="dunamismax@github",
            ip_address="100.84.119.114",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server-vm-02",
            owner="dunamismax@github",
            ip_address="100.122.237.56",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server-vm-03",
            owner="dunamismax@github",
            ip_address="100.97.229.120",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server-vm-04",
            owner="dunamismax@github",
            ip_address="100.73.171.7",
            version="1.80.2",
            os="Linux 6.11.0-18-generic",
            status="Connected",
        ),
        Machine(
            name="ubuntu-server-windows-11-ent-ltsc-vm",
            owner="dunamismax@github",
            ip_address="100.66.128.35",
            version="1.80.2",
            os="Windows 11 24H2",
            status="Connected",
        ),
    ]
    return machines


def load_local_devices() -> List[LocalDevice]:
    """Load the list of local network devices."""
    # Hardcoded local device list from the provided data
    devices = [
        LocalDevice(
            name="ubuntu-server",
            mac_address="6C-1F-F7-04-59-50",
            ip_address="192.168.0.73",
        ),
        LocalDevice(
            name="raspberrypi-5",
            mac_address="2C-CF-67-59-0E-03",
            ip_address="192.168.0.40",
        ),
        LocalDevice(
            name="ubuntu-lenovo",
            mac_address="6C-1F-F7-1A-0B-28",
            ip_address="192.168.0.45",
        ),
        LocalDevice(
            name="raspberrypi-3",
            mac_address="B8-27-EB-3A-11-89",
            ip_address="192.168.0.100",
        ),
    ]
    return devices


def create_machine_table(machines: List[Machine]) -> Table:
    """Create a formatted table of machines with their details."""
    table = Table(
        title="Available Machines",
        box=box.ROUNDED,
        title_style=f"bold {NordColors.NORD8}",
        border_style=NordColors.NORD3,
        title_justify="center",
        expand=True,
    )

    # Define columns
    table.add_column(
        "#", style=f"bold {NordColors.NORD9}", justify="right", no_wrap=True
    )
    table.add_column("Machine Name", style=f"{NordColors.NORD8}", justify="left")
    table.add_column("IP Address", style=f"{NordColors.NORD4}", justify="left")
    table.add_column("OS", style=f"{NordColors.NORD7}", justify="left")
    table.add_column("Status", justify="center")

    # Add rows
    for idx, machine in enumerate(machines, 1):
        table.add_row(
            str(idx),
            machine.get_display_name(),
            machine.get_display_ip(),
            machine.get_display_os(),
            machine.get_display_status(),
        )

    return table


def create_local_devices_table(devices: List[LocalDevice]) -> Table:
    """Create a formatted table of local network devices."""
    table = Table(
        title="Local IP Devices",
        box=box.ROUNDED,
        title_style=f"bold {NordColors.NORD8}",
        border_style=NordColors.NORD3,
        title_justify="center",
        expand=True,
    )

    # Define columns
    table.add_column("Device Name", style=f"{NordColors.NORD8}", justify="left")
    table.add_column("MAC Address", style=f"{NordColors.NORD4}", justify="center")
    table.add_column(
        "Reserved IP Address", style=f"{NordColors.NORD7}", justify="center"
    )
    table.add_column("Status", justify="center")
    table.add_column("Modify", style=f"{NordColors.NORD10}", justify="center")

    # Add rows
    for device in devices:
        table.add_row(
            device.name,
            device.mac_address,
            device.ip_address,
            device.get_display_status(),
            "[Edit]",
        )

    return table


# ==============================
# SSH Connection Functions
# ==============================
def connect_to_machine(machine: Machine, username: str = DEFAULT_USERNAME) -> None:
    """Connect to the selected machine via SSH."""
    console.print(create_section(f"Connecting to {machine.name}"))
    print_info(f"Establishing SSH connection to {username}@{machine.ip_address}...")

    try:
        # Build the SSH command
        ssh_args = [SSH_COMMAND, f"{username}@{machine.ip_address}"]

        # Use os.execvp to replace the current process with SSH
        # This ensures proper terminal handling and STDIN/STDOUT passthrough
        os.execvp(SSH_COMMAND, ssh_args)

        # Note: code below this point will not execute since execvp replaces the process
    except Exception as e:
        print_error(f"Failed to establish SSH connection: {str(e)}")
        print_info("Press Enter to return to the menu...")
        input()


# ==============================
# Main Application Functions
# ==============================
def create_app_layout() -> Layout:
    """Create the application layout structure."""
    layout = Layout()

    # Create main sections
    layout.split(
        Layout(name="header"),
        Layout(name="info"),
        Layout(name="main", ratio=4),
        Layout(name="footer"),
    )

    # Split the main section into two columns
    layout["main"].split_row(
        Layout(name="machines"),
        Layout(name="devices"),
    )

    return layout


def render_header() -> Panel:
    """Render the application header."""
    return print_header(APP_NAME)


def render_info() -> Panel:
    """Render the application info panel."""
    info_text = Text()
    info_text.append(f"Version: {VERSION}\n", style=NordColors.NORD9)
    info_text.append(
        f"System: {platform.system()} {platform.release()}\n", style=NordColors.NORD9
    )
    info_text.append(
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        style=NordColors.NORD9,
    )
    info_text.append(f"Default Username: {DEFAULT_USERNAME}", style=NordColors.NORD9)

    return Panel(
        info_text, border_style=NordColors.NORD3, box=box.ROUNDED, padding=(1, 2)
    )


def render_footer() -> Panel:
    """Render the application footer with options."""
    footer_text = Text()
    footer_text.append("Options:\n", style=f"bold {NordColors.NORD13}")
    footer_text.append(
        "Enter a number to connect to that machine\n", style=NordColors.NORD9
    )
    footer_text.append("Type 'l' to manage local devices\n", style=NordColors.NORD9)
    footer_text.append("Type 'q' to quit", style=NordColors.NORD9)

    return Panel(
        footer_text, border_style=NordColors.NORD3, box=box.ROUNDED, padding=(1, 2)
    )


def show_main_menu() -> None:
    """Display the main menu and handle user selection."""
    machines = load_machines()
    local_devices = load_local_devices()

    # Create and configure the layout
    layout = create_app_layout()

    while True:
        clear_screen()

        # Update layout components
        layout["header"].update(render_header())
        layout["info"].update(render_info())
        layout["machines"].update(create_machine_table(machines))
        layout["devices"].update(create_local_devices_table(local_devices))
        layout["footer"].update(render_footer())

        # Render the layout
        console.print(layout)

        # Get user selection
        try:
            choice = get_user_input(
                "\nEnter your choice (1-14, 'l' for local devices, or 'q' to quit)"
            )

            if choice.lower() == "q":
                clear_screen()
                console.print(print_header("Goodbye!"))
                print_info("Thank you for using the SSH Machine Selector.")
                sys.exit(0)

            if choice.lower() == "l":
                # Placeholder for local device management
                print_info("Local device management feature coming soon...")
                input("Press Enter to continue...")
                continue

            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(machines):
                    selected_machine = machines[choice_num - 1]

                    # Option to use a different username
                    use_diff_username = (
                        get_user_input(
                            f"Use default username '{DEFAULT_USERNAME}'? (y/n)", "y"
                        ).lower()
                        != "y"
                    )

                    username = DEFAULT_USERNAME
                    if use_diff_username:
                        username = get_user_input("Enter username")

                    # Connect to the selected machine
                    connect_to_machine(selected_machine, username)
                else:
                    print_error(
                        f"Invalid choice. Please enter a number between 1 and {len(machines)}."
                    )
                    input("Press Enter to continue...")
            except ValueError:
                print_error("Invalid input. Please enter a number, 'l', or 'q'.")
                input("Press Enter to continue...")
        except KeyboardInterrupt:
            clear_screen()
            console.print(print_header("Goodbye!"))
            print_info("Thank you for using the SSH Machine Selector.")
            sys.exit(0)


def main() -> None:
    """Main entry point for the script."""
    try:
        show_main_menu()
    except KeyboardInterrupt:
        print_info("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print_error(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
