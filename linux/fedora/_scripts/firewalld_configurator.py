#!/usr/bin/env python3
"""
Fedora Firewalld Configurator
--------------------------------------------------
A fully interactive, menu-driven toolkit for installing and
configuring Firewalld on Fedora Linux. This script checks for and
installs Firewalld via DNF (if not already installed), enables and
starts the service, and configures the firewall to allow traffic on:

  • Common ports (both TCP & UDP): 22, 80, 443
  • TCP-only ports: 32400 (Plex Media Server), 8324 (Plex Companion),
    32469 (Plex DLNA Server)
  • UDP-only ports: 1900 (Plex DLNA), 5353 (Bonjour/Avahi),
    32410, 32412, 32413, 32414 (GDM network discovery)

Version: 1.0.0
"""

import os
import sys
import time
import subprocess
import shutil
import signal
import atexit
from datetime import datetime

# ----------------------------------------------------------------
# Fedora Linux Check
# ----------------------------------------------------------------
if not os.path.exists("/etc/fedora-release"):
    print("This script is tailored for Fedora Linux. Exiting.")
    sys.exit(1)


# ----------------------------------------------------------------
# Dependency Check and Installation
# ----------------------------------------------------------------
def install_dependencies():
    """
    Ensure required third-party packages are installed.
    Installs via pip (using --user if not run as root):
      - rich
      - pyfiglet
      - prompt_toolkit
    """
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    try:
        # Attempt imports first
        import rich, pyfiglet, prompt_toolkit  # noqa: F401
    except ImportError:
        user = os.environ.get("SUDO_USER") or os.environ.get("USER")
        print(f"Installing dependencies for user: {user}")
        try:
            if os.geteuid() != 0:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--user"]
                    + required_packages
                )
            else:
                subprocess.check_call(
                    [
                        "sudo",
                        "-u",
                        user,
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--user",
                    ]
                    + required_packages
                )
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            sys.exit(1)


# Attempt to import dependencies; install if missing
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import InMemoryHistory
except ImportError:
    print("Required Python packages not found. Installing dependencies...")
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ----------------------------------------------------------------
# Nord-Themed Colors (for styling)
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    SNOW_STORM_1 = "#D8DEE9"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    RED = "#BF616A"
    PURPLE = "#B48EAD"


console = Console()


# ----------------------------------------------------------------
# Helper Functions for CLI Output
# ----------------------------------------------------------------
def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    try:
        ascii_art = pyfiglet.figlet_format(
            "Fedora Firewall", font="slant", width=adjusted_width
        )
    except Exception:
        ascii_art = "Fedora Firewall"
    styled_text = f"[bold {NordColors.FROST_2}]{ascii_art}[/]"
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v1.0.0[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]Firewalld Configurator[/]",
        subtitle_align="center",
    )
    return header_panel


# ----------------------------------------------------------------
# Firewalld Management Functions
# ----------------------------------------------------------------
def install_firewalld() -> bool:
    """
    Check if Firewalld is installed. If not, install it using dnf.
    """
    if shutil.which("firewall-cmd") is not None:
        print_success("Firewalld is already installed.")
        return True

    print_warning("Firewalld not found. Attempting to install via DNF...")
    try:
        # Use sudo if not root
        cmd = ["dnf", "install", "-y", "firewalld"]
        if os.geteuid() != 0:
            cmd.insert(0, "sudo")
        subprocess.check_call(cmd)
        print_success("Firewalld installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install Firewalld: {e}")
        return False


def start_firewalld() -> bool:
    """
    Enable and start the firewalld service.
    """
    print_message("Enabling and starting firewalld service...")
    try:
        cmd = ["systemctl", "enable", "--now", "firewalld"]
        if os.geteuid() != 0:
            cmd.insert(0, "sudo")
        subprocess.check_call(cmd)
        print_success("Firewalld service is enabled and running.")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to start firewalld: {e}")
        return False


def configure_firewalld() -> bool:
    """
    Configure firewalld to allow specified TCP and UDP ports.
    """
    print_message("Configuring firewalld rules...")
    # Define port lists
    common_ports = [22, 80, 443]  # Allow both TCP and UDP
    tcp_ports = [32400, 8324, 32469]  # TCP-only ports
    udp_ports = [1900, 5353, 32410, 32412, 32413, 32414]  # UDP-only ports

    # Function to add a port rule
    def add_port(port: int, protocol: str) -> None:
        try:
            cmd = ["firewall-cmd", "--permanent", f"--add-port={port}/{protocol}"]
            if os.geteuid() != 0:
                cmd.insert(0, "sudo")
            subprocess.check_call(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print_success(f"Added {port}/{protocol}")
        except subprocess.CalledProcessError:
            print_warning(f"Could not add {port}/{protocol}")

    # Add rules for common ports (both TCP & UDP)
    for port in common_ports:
        add_port(port, "tcp")
        add_port(port, "udp")

    # Add TCP-only rules
    for port in tcp_ports:
        add_port(port, "tcp")

    # Add UDP-only rules
    for port in udp_ports:
        add_port(port, "udp")

    # Reload firewall rules
    print_message("Reloading firewalld configuration...")
    try:
        cmd = ["firewall-cmd", "--reload"]
        if os.geteuid() != 0:
            cmd.insert(0, "sudo")
        subprocess.check_call(cmd)
        print_success("Firewalld configuration reloaded.")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to reload firewalld configuration: {e}")
        return False


# ----------------------------------------------------------------
# Spinner Progress Manager (Simplified)
# ----------------------------------------------------------------
class Spinner:
    def __init__(self, task_desc: str):
        self.task_desc = task_desc
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold green]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            transient=True,
        )
        self.task_id = None

    def start(self):
        self.progress.start()
        self.task_id = self.progress.add_task(self.task_desc, total=100)

    def update(self, completed: int):
        if self.task_id is not None:
            self.progress.update(self.task_id, completed=completed)

    def stop(self):
        self.progress.stop()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up resources...", NordColors.FROST_1)


def signal_handler(sig, frame) -> None:
    print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def main_menu() -> None:
    history = InMemoryHistory()
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(Align.center(f"[dim]Current Time: {current_time}[/dim]"))
        console.print()
        console.print("[bold underline magenta]Firewalld Configuration Menu[/]\n")
        console.print("1. Install/Update Firewalld")
        console.print("2. Start Firewalld Service")
        console.print("3. Configure Firewalld (Open required ports)")
        console.print("H. Help")
        console.print("0. Exit\n")
        choice = pt_prompt("Enter your choice: ", history=history).strip().upper()

        if choice == "0":
            console.print("\nThank you for using the Fedora Firewalld Configurator!")
            sys.exit(0)
        elif choice == "1":
            if install_firewalld():
                time.sleep(1)
            pt_prompt("Press Enter to continue...")
        elif choice == "2":
            if start_firewalld():
                time.sleep(1)
            pt_prompt("Press Enter to continue...")
        elif choice == "3":
            if configure_firewalld():
                time.sleep(1)
            pt_prompt("Press Enter to continue...")
        elif choice == "H":
            console.print(
                Panel(
                    "[bold]Available Commands:[/]\n"
                    "1 - Install or update Firewalld\n"
                    "2 - Start and enable Firewalld service\n"
                    "3 - Configure Firewalld to allow specified ports\n"
                    "0 - Exit the configurator\n",
                    title="[bold magenta]Help[/bold magenta]",
                    border_style=NordColors.FROST_3,
                    padding=(1, 2),
                )
            )
            pt_prompt("Press Enter to continue...")
        else:
            print_error(f"Invalid selection: {choice}")
            pt_prompt("Press Enter to continue...")


def main() -> None:
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
