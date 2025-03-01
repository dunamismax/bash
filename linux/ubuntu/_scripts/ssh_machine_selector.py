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

Features a Nord-themed interface for easy readability and selection.

Usage:
  Simply run the script or alias it to 'ssh' for quick access.
  Select a machine by number to connect via SSH.

Version: 1.0.0
"""

import os
import sys
import subprocess
import shutil
import platform
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, IntPrompt
    from rich.text import Text
    import pyfiglet
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' packages.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "SSH Machine Selector"
VERSION = "1.0.0"
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
            return f"[bold {NordColors.NORD14}]{self.status}[/]"
        elif "disabled" in self.status.lower():
            return f"[bold {NordColors.NORD13}]{self.status}[/]"
        else:
            return f"[dim]{self.status}[/]"


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")


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


def display_machine_list(machines: List[Machine]) -> None:
    """Display a formatted list of machines with their details."""
    table = Table(
        title="Available Machines", box=None, title_style=f"bold {NordColors.NORD8}"
    )

    # Define columns
    table.add_column("#", style=f"bold {NordColors.NORD9}", justify="right")
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

    console.print(table)


# ==============================
# SSH Connection Functions
# ==============================
def connect_to_machine(machine: Machine, username: str = DEFAULT_USERNAME) -> None:
    """Connect to the selected machine via SSH."""
    print_section(f"Connecting to {machine.name}")
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
def show_main_menu() -> None:
    """Display the main menu and handle user selection."""
    machines = load_machines()

    while True:
        clear_screen()
        print_header(APP_NAME)

        # Show application info
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Default Username: {DEFAULT_USERNAME}")
        print_section("Machine Selection")

        # Display machines
        display_machine_list(machines)

        # Show options footer
        console.print(f"\n[bold {NordColors.NORD13}]Options:[/]")
        console.print(
            f"[{NordColors.NORD9}]Enter a number to connect to that machine[/]"
        )
        console.print(f"[{NordColors.NORD9}]Type 'q' to quit[/]")

        # Get user selection
        try:
            choice = get_user_input("\nEnter your choice (1-14 or 'q' to quit)")

            if choice.lower() == "q":
                clear_screen()
                print_header("Goodbye!")
                print_info("Thank you for using the SSH Machine Selector.")
                sys.exit(0)

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
                print_error("Invalid input. Please enter a number or 'q'.")
                input("Press Enter to continue...")
        except KeyboardInterrupt:
            clear_screen()
            print_header("Goodbye!")
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
