#!/usr/bin/env python3
"""
Fail2Ban Toolkit CLI Application
----------------------------------

A professional-grade terminal application for managing Fail2Ban with a
Nord-themed interface. This interactive CLI allows you to view Fail2Ban jails,
inspect banned IPs, unban IPs, restart the Fail2Ban service, and check overall
status—all with dynamic ASCII banners, progress tracking, and comprehensive error
handling for a production-grade user experience.

Usage:
  Run the script and follow the interactive menu options.

Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import os
import signal
import subprocess
import sys
import time
import shutil
from dataclasses import dataclass, field
from typing import List, Tuple

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install python3-rich and python3-pyfiglet."
    )
    sys.exit(1)

# Enable rich traceback for debugging
install_rich_traceback(show_locals=True)
console: Console = Console()


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Return a gradient of frost colors for dynamic banner styling."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "Fail2Ban Toolkit"
APP_SUBTITLE = "Advanced CLI for Fail2Ban Management"
VERSION = "1.0.0"
OPERATION_TIMEOUT = 30  # seconds


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Jail:
    """
    Represents a Fail2Ban jail and its banned IP list.

    Attributes:
        name: The jail's name.
        banned_ips: A list of banned IP addresses.
    """

    name: str
    banned_ips: List[str] = field(default_factory=list)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """
    Create a dynamic ASCII banner header using Pyfiglet.
    The banner adapts to terminal width and applies a Nord-themed gradient.
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts = ["slant", "small", "mini", "digital"]
    font_to_use = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]
    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    text_lines = []
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        text_lines.append(Text(line, style=f"bold {color}"))
    combined_text = Text()
    for i, line in enumerate(text_lines):
        combined_text.append(line)
        if i < len(text_lines) - 1:
            combined_text.append("\n")
    return Panel(
        combined_text,
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message with a given prefix and style."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print an error message in red."""
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    """Print a success message in green."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    print_message(message, NordColors.YELLOW, "⚠")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display a formatted panel with a title and message."""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Fail2Ban Interaction Functions
# ----------------------------------------------------------------
def run_command(cmd: List[str]) -> Tuple[int, str]:
    """
    Execute a shell command and return its exit code and output.

    Raises:
        Exception: If the command fails or times out.
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OPERATION_TIMEOUT,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception("Command timed out.")


def list_jails() -> List[Jail]:
    """
    Retrieve a list of Fail2Ban jails using 'fail2ban-client status'.

    Returns:
        A list of Jail objects with their names and banned IP lists.
    """
    try:
        _, output = run_command(["fail2ban-client", "status"])
        # Example output:
        # Status
        # |- Number of jail:  2
        # `- Jail list:   sshd, apache
        jail_line = ""
        for line in output.splitlines():
            if "Jail list:" in line:
                jail_line = line.split("Jail list:")[1]
                break
        if not jail_line:
            return []
        jail_names = [j.strip() for j in jail_line.split(",")]
        jails = []
        for name in jail_names:
            banned_ips = get_banned_ips(name)
            jails.append(Jail(name=name, banned_ips=banned_ips))
        return jails
    except Exception as e:
        print_error(f"Error listing jails: {str(e)}")
        return []


def get_banned_ips(jail_name: str) -> List[str]:
    """
    Retrieve the list of banned IPs for a given jail using 'fail2ban-client status <jail>'.

    Args:
        jail_name: The name of the jail.

    Returns:
        A list of banned IP addresses.
    """
    try:
        _, output = run_command(["fail2ban-client", "status", jail_name])
        banned_line = ""
        for line in output.splitlines():
            if "Banned IP list:" in line:
                banned_line = line.split("Banned IP list:")[1]
                break
        if not banned_line:
            return []
        ips = [ip.strip() for ip in banned_line.split()]
        return ips
    except Exception as e:
        print_error(f"Error getting banned IPs for {jail_name}: {str(e)}")
        return []


def unban_ip(jail_name: str, ip: str) -> bool:
    """
    Unban an IP address from a specified jail using 'fail2ban-client set <jail> unbanip <IP>'.

    Args:
        jail_name: The name of the jail.
        ip: The IP address to unban.

    Returns:
        True if the unban operation succeeded, otherwise False.
    """
    try:
        run_command(["fail2ban-client", "set", jail_name, "unbanip", ip])
        print_success(f"Unbanned IP {ip} from jail {jail_name}.")
        return True
    except Exception as e:
        print_error(f"Error unbanning IP {ip} from {jail_name}: {str(e)}")
        return False


def restart_fail2ban() -> bool:
    """
    Restart the Fail2Ban service using 'systemctl restart fail2ban'.

    Returns:
        True if the service restarted successfully, otherwise False.
    """
    try:
        run_command(["sudo", "systemctl", "restart", "fail2ban"])
        print_success("Fail2Ban service restarted successfully.")
        return True
    except Exception as e:
        print_error(f"Error restarting Fail2Ban: {str(e)}")
        return False


def show_fail2ban_status() -> None:
    """
    Display the overall Fail2Ban status using 'fail2ban-client status'.
    """
    try:
        _, output = run_command(["fail2ban-client", "status"])
        display_panel("Fail2Ban Status", output)
    except Exception as e:
        print_error(f"Error retrieving Fail2Ban status: {str(e)}")


# ----------------------------------------------------------------
# UI Components for Fail2Ban Toolkit
# ----------------------------------------------------------------
def display_jails_table(jails: List[Jail]) -> None:
    """
    Display a table of Fail2Ban jails with the number of banned IPs.

    Args:
        jails: A list of Jail objects.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title="Fail2Ban Jails",
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Jail Name", style=f"bold {NordColors.FROST_1}", width=20)
    table.add_column(
        "Banned IPs", style=f"{NordColors.SNOW_STORM_1}", width=15, justify="center"
    )
    for idx, jail in enumerate(jails, 1):
        table.add_row(str(idx), jail.name, str(len(jail.banned_ips)))
    console.print(table)


def display_banned_ips_table(jail: Jail) -> None:
    """
    Display a table of banned IPs for a specified jail.

    Args:
        jail: A Jail object.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=f"Banned IPs in Jail: {jail.name}",
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Banned IP", style=f"{NordColors.SNOW_STORM_1}")
    for idx, ip in enumerate(jail.banned_ips, 1):
        table.add_row(str(idx), ip)
    console.print(table)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup operations before exiting."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig, frame) -> None:
    """Gracefully handle termination signals (SIGINT, SIGTERM)."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ----------------------------------------------------------------
# Main Interactive Menu
# ----------------------------------------------------------------
def main_menu() -> None:
    """Display the main menu and process user input."""
    while True:
        clear_screen()
        console.print(create_header())
        console.print(
            Align.center(Text(APP_SUBTITLE, style=f"bold {NordColors.SNOW_STORM_2}"))
        )
        console.print()
        console.print("[bold]Main Menu:[/]")
        console.print("[bold]1.[/] List Fail2Ban Jails")
        console.print("[bold]2.[/] Show Fail2Ban Status")
        console.print("[bold]3.[/] Show Banned IPs in a Jail")
        console.print("[bold]4.[/] Unban an IP from a Jail")
        console.print("[bold]5.[/] Restart Fail2Ban Service")
        console.print("[bold]6.[/] Exit")
        console.print()
        choice = Prompt.ask("Enter your choice", choices=["1", "2", "3", "4", "5", "6"])
        if choice == "1":
            list_jails_menu()
        elif choice == "2":
            show_fail2ban_status()
            Prompt.ask("Press Enter to return to the main menu")
        elif choice == "3":
            show_banned_ips_menu()
        elif choice == "4":
            unban_ip_menu()
        elif choice == "5":
            restart_fail2ban()
            Prompt.ask("Press Enter to return to the main menu")
        elif choice == "6":
            clear_screen()
            console.print(
                Panel(
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                )
            )
            break


def list_jails_menu() -> None:
    """Menu option to list Fail2Ban jails."""
    clear_screen()
    console.print(create_header())
    console.print("[bold]Listing Fail2Ban Jails...[/]")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("Retrieving jails..."),
        console=console,
    ) as progress:
        progress.add_task("Loading", total=None)
        time.sleep(1)  # Simulate delay for better UX
    jails = list_jails()
    if jails:
        display_jails_table(jails)
    else:
        print_warning("No jails found.")
    Prompt.ask("Press Enter to return to the main menu")


def show_banned_ips_menu() -> None:
    """Menu option to display banned IPs for a selected jail."""
    clear_screen()
    jails = list_jails()
    if not jails:
        print_warning("No jails available.")
        Prompt.ask("Press Enter to return to the main menu")
        return
    display_jails_table(jails)
    jail_choice = Prompt.ask("Enter the number of the jail to view banned IPs")
    try:
        idx = int(jail_choice) - 1
        if 0 <= idx < len(jails):
            selected_jail = jails[idx]
            display_banned_ips_table(selected_jail)
        else:
            print_error("Invalid jail selection.")
    except ValueError:
        print_error("Invalid input.")
    Prompt.ask("Press Enter to return to the main menu")


def unban_ip_menu() -> None:
    """Menu option to unban an IP from a selected jail."""
    clear_screen()
    jails = list_jails()
    if not jails:
        print_warning("No jails available.")
        Prompt.ask("Press Enter to return to the main menu")
        return
    display_jails_table(jails)
    jail_choice = Prompt.ask("Enter the number of the jail to unban an IP from")
    try:
        idx = int(jail_choice) - 1
        if 0 <= idx < len(jails):
            selected_jail = jails[idx]
            if not selected_jail.banned_ips:
                print_warning("No banned IPs in this jail.")
                Prompt.ask("Press Enter to return to the main menu")
                return
            display_banned_ips_table(selected_jail)
            ip_choice = Prompt.ask("Enter the number of the IP to unban")
            try:
                ip_idx = int(ip_choice) - 1
                if 0 <= ip_idx < len(selected_jail.banned_ips):
                    ip_to_unban = selected_jail.banned_ips[ip_idx]
                    if Confirm.ask(f"Are you sure you want to unban {ip_to_unban}?"):
                        unban_ip(selected_jail.name, ip_to_unban)
                else:
                    print_error("Invalid IP selection.")
            except ValueError:
                print_error("Invalid input.")
        else:
            print_error("Invalid jail selection.")
    except ValueError:
        print_error("Invalid input.")
    Prompt.ask("Press Enter to return to the main menu")


def main() -> None:
    """Main entry point for the Fail2Ban Toolkit CLI application."""
    try:
        main_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
