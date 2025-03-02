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
  • Pagination support for large machine lists

Features a Nord-themed interface for easy readability and selection.

Usage:
  Simply run the script or alias it to 'ssh' for quick access.
  Select a machine by number to connect via SSH.

Version: 1.2.0
"""

import os
import sys
import subprocess
import shutil
import platform
import math
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

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
APP_NAME = "SSH Selector"  # Adjusted name for better display
VERSION = "1.2.0"
DEFAULT_USERNAME = "sawyer"  # Default SSH username
SSH_COMMAND = "ssh"  # SSH command to use

# Get terminal dimensions
TERM_WIDTH = shutil.get_terminal_size().columns
TERM_HEIGHT = shutil.get_terminal_size().lines

# Items per page for pagination
ITEMS_PER_PAGE = 10  # Adjust as needed

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
def print_header(text: str) -> Panel:
    """Create a striking header using pyfiglet."""
    # Use small font to save space
    ascii_art = pyfiglet.figlet_format(text, font="small")
    return Panel(
        Text(ascii_art, style=f"bold {NordColors.NORD8}"),
        border_style=NordColors.NORD10,
        box=box.ROUNDED,
        padding=(0, 1),  # Reduced padding
        title=f"v{VERSION}",
        title_align="right",
    )


def create_section(title: str) -> Panel:
    """Create a formatted section header."""
    return Panel(
        Text(title, style=f"bold {NordColors.NORD8}"),
        border_style=NordColors.NORD9,
        box=box.HEAVY_EDGE,
        padding=(0, 1),  # Reduced padding
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


def create_machine_table(machines: List[Machine], page: int = 1) -> Tuple[Table, int]:
    """Create a formatted table of machines with their details."""
    # Calculate pagination info
    total_pages = math.ceil(len(machines) / ITEMS_PER_PAGE)
    page = min(max(1, page), total_pages)  # Ensure page is in valid range
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, len(machines))

    # Get current page of machines
    current_page_machines = machines[start_idx:end_idx]

    # Pagination info for title
    pagination_info = f"Page {page}/{total_pages}" if total_pages > 1 else ""

    table = Table(
        title=f"Tailscale Machines {pagination_info}",
        box=box.SIMPLE_HEAD,  # Simpler box style to save space
        title_style=f"bold {NordColors.NORD8}",
        border_style=NordColors.NORD3,
        title_justify="center",
        expand=True,
        padding=(0, 1),  # Minimal padding
    )

    # Define more compact columns
    table.add_column(
        "#", style=f"bold {NordColors.NORD9}", justify="right", no_wrap=True, width=3
    )
    table.add_column(
        "Machine Name", style=f"{NordColors.NORD8}", justify="left", width=24
    )
    table.add_column(
        "IP Address", style=f"{NordColors.NORD4}", justify="left", width=15
    )
    table.add_column("OS", style=f"{NordColors.NORD7}", justify="left", width=22)
    table.add_column("Status", justify="center", width=10)

    # Add rows for current page
    for idx, machine in enumerate(current_page_machines, start_idx + 1):
        table.add_row(
            str(idx),
            machine.get_display_name(),
            machine.get_display_ip(),
            machine.get_display_os(),
            machine.get_display_status(),
        )

    return table, total_pages


def create_local_devices_table(devices: List[LocalDevice]) -> Table:
    """Create a formatted table of local network devices."""
    table = Table(
        title="Local IP Devices",
        box=box.SIMPLE_HEAD,  # Simpler box style
        title_style=f"bold {NordColors.NORD8}",
        border_style=NordColors.NORD3,
        title_justify="center",
        expand=True,
        padding=(0, 1),  # Minimal padding
    )

    # Define columns with compact widths
    table.add_column(
        "#", style=f"bold {NordColors.NORD9}", justify="right", no_wrap=True, width=3
    )
    table.add_column(
        "Device Name", style=f"{NordColors.NORD8}", justify="left", width=18
    )
    table.add_column(
        "MAC Address", style=f"{NordColors.NORD4}", justify="center", width=18
    )
    table.add_column(
        "IP Address", style=f"{NordColors.NORD7}", justify="center", width=15
    )
    table.add_column("OS", style=f"{NordColors.NORD4}", justify="left", width=22)
    table.add_column("Status", justify="center", width=8)

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
    console.print(create_section(f"Connecting to {name}"))
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
def create_app_layout() -> Layout:
    """Create the application layout structure."""
    layout = Layout(name="root")

    # Create main sections in vertical arrangement to maximize space
    layout.split(
        Layout(name="header", size=5),  # Reduced header size
        Layout(name="machines", ratio=3),  # Give more space to machines
        Layout(name="devices", ratio=2),  # Local devices
        Layout(name="footer", size=6),  # Reduced footer size
    )

    return layout


def render_compact_header() -> Panel:
    """Render a more compact header with system info."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header_text = Text()
    header_text.append(f"{APP_NAME} ", style=f"bold {NordColors.NORD8}")
    header_text.append(f"v{VERSION}\n", style=NordColors.NORD9)
    header_text.append("System: ", style=f"bold {NordColors.NORD7}")
    header_text.append(
        f"{platform.system()} {platform.release()}\n", style=NordColors.NORD9
    )
    header_text.append("Time: ", style=f"bold {NordColors.NORD7}")
    header_text.append(f"{current_time}", style=NordColors.NORD9)

    return Panel(
        header_text,
        border_style=NordColors.NORD10,
        box=box.ROUNDED,
        padding=(0, 1),  # Minimal padding
    )


def render_footer(current_page: int, total_pages: int) -> Panel:
    """Render the application footer with options."""
    footer_text = Text()

    # Navigation options
    if total_pages > 1:
        footer_text.append(
            f"Page {current_page}/{total_pages} | ", style=f"bold {NordColors.NORD13}"
        )
        footer_text.append(
            "n = next page, p = previous page, g = go to page\n", style=NordColors.NORD9
        )

    # Connection options
    footer_text.append("Options: ", style=f"bold {NordColors.NORD13}")
    footer_text.append("Enter # to connect to machine, ", style=NordColors.NORD9)
    footer_text.append("L# for local device, ", style=NordColors.NORD9)
    footer_text.append("q to quit", style=NordColors.NORD9)

    return Panel(
        footer_text,
        border_style=NordColors.NORD3,
        box=box.ROUNDED,
        padding=(0, 1),  # Minimal padding
    )


def show_main_menu() -> None:
    """Display the main menu and handle user selection."""
    machines = load_machines()
    local_devices = load_local_devices()
    current_page = 1
    total_pages = math.ceil(len(machines) / ITEMS_PER_PAGE)

    # Create and configure the layout
    layout = create_app_layout()

    while True:
        clear_screen()

        # Create tables with pagination for current page
        machine_table, total_pages = create_machine_table(machines, current_page)
        local_device_table = create_local_devices_table(local_devices)

        # Update layout components
        layout["header"].update(render_compact_header())
        layout["machines"].update(machine_table)
        layout["devices"].update(local_device_table)
        layout["footer"].update(render_footer(current_page, total_pages))

        # Render the layout
        console.print(layout)

        # Get user selection
        try:
            choice = get_user_input(
                "\nEnter choice (machine #, L# for local, n/p for pages, q to quit):"
            )

            # Handle quit
            if choice.lower() == "q":
                clear_screen()
                print_info("Thank you for using the SSH Machine Selector.")
                sys.exit(0)

            # Handle pagination
            if choice.lower() == "n" and current_page < total_pages:
                current_page += 1
                continue
            elif choice.lower() == "p" and current_page > 1:
                current_page -= 1
                continue
            elif choice.lower() == "g":
                try:
                    page = get_user_number(
                        f"Enter page number (1-{total_pages}):", 1, total_pages
                    )
                    current_page = page
                except ValueError:
                    print_error("Invalid page number.")
                    input("\nPress Enter to continue...")
                continue

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
                    # Check if selection is on current page
                    page_start = (current_page - 1) * ITEMS_PER_PAGE + 1
                    page_end = min(page_start + ITEMS_PER_PAGE - 1, len(machines))

                    if page_start <= choice_num <= page_end:
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
                        # If selection is not on current page, navigate to that page
                        target_page = (choice_num - 1) // ITEMS_PER_PAGE + 1
                        print_info(
                            f"Selection {choice_num} is on page {target_page}. Navigating..."
                        )
                        current_page = target_page
                else:
                    print_error(
                        f"Invalid choice. Please enter a number between 1 and {len(machines)}."
                    )
                    input("\nPress Enter to continue...")
            except ValueError:
                # If not a recognized command, show help
                if choice.strip() and choice.lower() not in ["n", "p", "g", "q"]:
                    print_error(
                        "Invalid input. Enter a machine number, L# for local device, n/p for page navigation, or q to quit."
                    )
                    input("\nPress Enter to continue...")
        except KeyboardInterrupt:
            clear_screen()
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
