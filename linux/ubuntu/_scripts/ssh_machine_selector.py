#!/usr/bin/env python3
"""
Secure Shell Selector
-------------------

A clean, minimal terminal-based utility for connecting to SSH machines.
This tool provides:
  • A numbered list of available machines
  • Quick selection by number
  • SSH connection handling with proper terminal management
  • Visual indication of connection status
  • Local IP device management

Features a borderless Nord-themed interface for easy readability.

Usage:
  Simply run the script or alias it to 'ssh' for quick access.
  Select a machine by number to connect via SSH.

Version: 1.3.0
"""

import os
import sys
import shutil
import platform
from datetime import datetime
from dataclasses import dataclass
from typing import List

try:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.prompt import Prompt, IntPrompt
    from rich import box
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Secure Shell Selector"
VERSION = "1.3.0"
DEFAULT_USERNAME = "sawyer"  # Default SSH username
SSH_COMMAND = "ssh"  # SSH command to use

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
            return Text("Connected", style=f"bold {NordColors.NORD14}")
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
    os: str = "Unknown"  # Added OS field for consistency with Machine class

    def get_display_status(self) -> Text:
        """Get formatted status with appropriate coloring."""
        if self.status.lower() == "active":
            return Text("Active", style=f"bold {NordColors.NORD14}")
        elif self.status.lower() == "inactive":
            return Text("Inactive", style="dim")
        else:
            return Text(self.status, style=f"bold {NordColors.NORD13}")

    def get_display_name(self) -> str:
        """Get formatted display name for the local device."""
        return f"{self.name}"

    def get_display_ip(self) -> str:
        """Get formatted IP address."""
        return f"{self.ip_address}"

    def get_display_os(self) -> str:
        """Get formatted OS info."""
        return f"{self.os}"


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Create a striking header using pyfiglet with no borders."""
    # Use small font to save space
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(Text(ascii_art, style=f"bold {NordColors.NORD8}"))
    console.print(Text(f"v{VERSION}", style=f"{NordColors.NORD9}"), justify="right")
    console.print()  # Add some spacing


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


# ==============================
# Machine List Functions
# ==============================
def load_machines() -> List[Machine]:
    """Load the list of machines."""
    # Updated Tailscale machine list (excluding Windows machines and iPhone)
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
            name="raspberrypi-5",
            owner="dunamismax@github",
            ip_address="100.105.117.18",
            version="1.80.2",
            os="Linux 6.11.0-1008-raspi",
            status="Connected",
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
    ]
    return machines


def load_local_devices() -> List[LocalDevice]:
    """Load the list of local network devices."""
    # Updated local device list with exact data provided
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


def create_machine_table(machines: List[Machine]) -> Table:
    """Create a clean table of machines with their details."""
    # Create a borderless table
    table = Table(
        show_header=True,
        box=None,  # No borders
        header_style=f"bold {NordColors.NORD8}",
        title="Tailscale Machines",
        title_style=f"bold {NordColors.NORD7}",
        title_justify="left",
        expand=True,
        padding=(0, 2),  # Vertical padding of 0, horizontal padding of 2
    )

    # Define columns
    table.add_column(
        "#", style=f"bold {NordColors.NORD9}", justify="right", no_wrap=True
    )
    table.add_column("Machine Name", style=f"{NordColors.NORD8}", justify="left")
    table.add_column("IP Address", style=f"{NordColors.NORD4}", justify="left")
    table.add_column("OS", style=f"{NordColors.NORD7}", justify="left")
    table.add_column("Status", justify="left")

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
    """Create a clean table of local network devices."""
    # Create a borderless table
    table = Table(
        show_header=True,
        box=None,  # No borders
        header_style=f"bold {NordColors.NORD8}",
        title="Local IP Devices",
        title_style=f"bold {NordColors.NORD7}",
        title_justify="left",
        expand=True,
        padding=(0, 2),  # Vertical padding of 0, horizontal padding of 2
    )

    # Define columns
    table.add_column(
        "#", style=f"bold {NordColors.NORD9}", justify="right", no_wrap=True
    )
    table.add_column("Device Name", style=f"{NordColors.NORD8}", justify="left")
    table.add_column("MAC Address", style=f"{NordColors.NORD4}", justify="left")
    table.add_column("IP Address", style=f"{NordColors.NORD7}", justify="left")
    table.add_column("OS", style=f"{NordColors.NORD4}", justify="left")
    table.add_column("Status", justify="left")

    # Add rows
    for idx, device in enumerate(devices, 1):
        table.add_row(
            f"L{idx}",  # "L" prefix to differentiate from machine list
            device.name,
            device.mac_address,
            device.ip_address,
            device.get_display_os(),
            device.get_display_status(),
        )

    return table


# ==============================
# SSH Connection Functions
# ==============================
def connect_to_machine(
    name: str, ip_address: str, username: str = DEFAULT_USERNAME
) -> None:
    """Connect to a machine (either Tailscale or Local) via SSH."""
    console.print(Text(f"Connecting to {name}", style=f"bold {NordColors.NORD8}"))
    print_info(f"Establishing SSH connection to {username}@{ip_address}...")

    try:
        # Build the SSH command
        ssh_args = [SSH_COMMAND, f"{username}@{ip_address}"]

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
def show_main_menu() -> None:
    """Display the main menu and handle user selection."""
    machines = load_machines()
    local_devices = load_local_devices()

    while True:
        clear_screen()

        # Print header
        print_header(APP_NAME)

        # Display machine tables
        console.print(create_machine_table(machines))
        console.print("")  # Add spacing
        console.print(create_local_devices_table(local_devices))
        console.print("")  # Add spacing

        # Display options
        console.print(Text("Options:", style=f"bold {NordColors.NORD13}"))
        console.print(
            Text(
                "• Enter 1-11 to connect to a Tailscale machine", style=NordColors.NORD9
            )
        )
        console.print(
            Text(
                "• Enter L1-L4 to connect to a local IP device", style=NordColors.NORD9
            )
        )
        console.print(Text("• Type 'q' to quit", style=NordColors.NORD9))
        console.print("")  # Add spacing

        # Get user selection
        try:
            choice = get_user_input("\nEnter your choice:")

            if choice.lower() == "q":
                clear_screen()
                print_info("Thank you for using the Secure Shell Selector.")
                sys.exit(0)

            # Handle local device selection (L1-L4)
            if choice.upper().startswith("L"):
                try:
                    # Extract the number after "L"
                    local_idx = int(choice[1:])
                    if 1 <= local_idx <= len(local_devices):
                        selected_device = local_devices[local_idx - 1]

                        # Option to use a different username
                        use_diff_username = (
                            get_user_input(
                                f"Use default username '{DEFAULT_USERNAME}'? (y/n)", "y"
                            ).lower()
                            != "y"
                        )

                        username = DEFAULT_USERNAME
                        if use_diff_username:
                            username = get_user_input("Enter username:")

                        # Connect to the selected local device
                        connect_to_machine(
                            selected_device.name, selected_device.ip_address, username
                        )
                    else:
                        print_error(
                            f"Invalid local device choice. Please enter L1-L{len(local_devices)}."
                        )
                        input("\nPress Enter to continue...")
                except ValueError:
                    print_error(
                        "Invalid local device selection format. Use L1, L2, etc."
                    )
                    input("\nPress Enter to continue...")
                continue

            # Handle Tailscale machine selection
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
                        username = get_user_input("Enter username:")

                    # Connect to the selected Tailscale machine
                    connect_to_machine(
                        selected_machine.name, selected_machine.ip_address, username
                    )
                else:
                    print_error(
                        f"Invalid choice. Please enter a number between 1 and {len(machines)}."
                    )
                    input("\nPress Enter to continue...")
            except ValueError:
                print_error(
                    "Invalid input. Please enter a machine number (1-11), local device (L1-L4), or 'q'."
                )
                input("\nPress Enter to continue...")
        except KeyboardInterrupt:
            clear_screen()
            print_info("Thank you for using the Secure Shell Selector.")
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
