#!/usr/bin/env python3
"""
HighDPI Configurator
--------------------------------------------------
This script applies best-practice highDPI settings for a 27-inch 4K display
running PopOS on X11 with 150% fractional scaling. It ensures that system
applications, as well as Flatpak apps, are scaled properly and text is sharp.

Features:
  • Installs required Python libraries if needed.
  • Creates a system profile script (/etc/profile.d/90-hidpi.sh) to export
    environment variables for GTK and Qt apps.
  • Configures Xresources (or user .Xresources as a fallback) to set Xft DPI.
  • Applies Flatpak overrides for a consistent scaling experience.
  • Provides an interactive, menu-driven CLI using Rich, Pyfiglet, and prompt_toolkit.

Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import os
import sys
import time
import subprocess
import getpass
import shutil
import socket
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


# Function to install dependencies for non-root users if missing
def install_dependencies() -> None:
    """Ensure required Python libraries are installed."""
    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    try:
        import paramiko, pyfiglet
        from rich.console import Console
        from prompt_toolkit import prompt as pt_prompt
    except ImportError:
        print("Required libraries not found. Installing dependencies...")
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            # Running as root; install for the invoking user
            user = os.environ.get("SUDO_USER") or getpass.getuser()
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
        print("Dependencies installed. Please restart the script.")
        sys.exit(0)


install_dependencies()

# Import third-party libraries now that they are available
import paramiko
import pyfiglet
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.align import Align
from rich.style import Style
from rich.traceback import install as install_rich_traceback
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PtStyle

install_rich_traceback(show_locals=True)
console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "HighDPI Configurator"
VERSION: str = "1.0.0"
APP_SUBTITLE: str = "System-wide HighDPI Settings for PopOS"
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)

# Directories for backup (for user-level files)
BACKUP_DIR = os.path.join(os.path.expanduser("~"), ".hidpi_backup")
os.makedirs(BACKUP_DIR, exist_ok=True)

# HighDPI settings
GDK_SCALE: str = "1"
GDK_DPI_SCALE: str = "1.5"
QT_AUTO_SCREEN_SCALE_FACTOR: str = "0"
QT_SCALE_FACTOR: str = "1.5"
XFT_DPI: str = "144"  # 96*1.5

# Files to modify (system-wide)
PROFILE_SCRIPT: str = "/etc/profile.d/90-hidpi.sh"
XRESOURCES_DIR: str = "/etc/X11/Xresources.d"
XRESOURCES_FILE: str = os.path.join(XRESOURCES_DIR, "80-hidpi.conf")
# Fallback for user-level Xresources (if system directory not available)
USER_XRESOURCES: str = os.path.join(os.path.expanduser("~"), ".Xresources")


# ----------------------------------------------------------------
# Nord-Themed Colors (for consistency with the template)
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    SNOW_STORM_1: str = "#D8DEE9"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


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


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def wait_for_key() -> None:
    pt_prompt("Press Enter to continue...", style=get_prompt_style())


# ----------------------------------------------------------------
# Helper Functions for File Backup and Writing
# ----------------------------------------------------------------
def backup_file(file_path: str) -> None:
    """If file exists, back it up in the backup directory."""
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(
            BACKUP_DIR, os.path.basename(file_path) + f".bak_{timestamp}"
        )
        try:
            shutil.copy2(file_path, backup_path)
            print_success(f"Backed up {file_path} to {backup_path}")
        except Exception as e:
            print_warning(f"Failed to backup {file_path}: {e}")


def write_file(file_path: str, content: str) -> bool:
    """Write content to file, backing up any existing file."""
    try:
        backup_file(file_path)
        with open(file_path, "w") as f:
            f.write(content)
        print_success(f"Written settings to {file_path}")
        return True
    except Exception as e:
        print_error(f"Error writing to {file_path}: {e}")
        return False


# ----------------------------------------------------------------
# HighDPI Configuration Functions
# ----------------------------------------------------------------
def apply_system_profile_scaling() -> None:
    """
    Create or update a system-wide profile script to export HighDPI settings.
    This file will be placed in /etc/profile.d/90-hidpi.sh.
    """
    if os.geteuid() != 0:
        print_error(
            "System-wide changes require root privileges. Please run with sudo."
        )
        return

    content = (
        "#!/bin/sh\n"
        "# HighDPI settings for 150% scaling\n"
        f"export GDK_SCALE={GDK_SCALE}\n"
        f"export GDK_DPI_SCALE={GDK_DPI_SCALE}\n"
        f"export QT_AUTO_SCREEN_SCALE_FACTOR={QT_AUTO_SCREEN_SCALE_FACTOR}\n"
        f"export QT_SCALE_FACTOR={QT_SCALE_FACTOR}\n"
    )
    if write_file(PROFILE_SCRIPT, content):
        # Ensure the script is executable
        try:
            os.chmod(PROFILE_SCRIPT, 0o755)
        except Exception as e:
            print_warning(f"Could not set execute permissions on {PROFILE_SCRIPT}: {e}")


def apply_xresources_scaling() -> None:
    """
    Configure Xft DPI for X11. If the system directory /etc/X11/Xresources.d exists,
    write a configuration file there. Otherwise, update the user's ~/.Xresources.
    """
    target_file = ""
    content = f"Xft.dpi: {XFT_DPI}\n"
    if os.path.isdir(XRESOURCES_DIR):
        target_file = XRESOURCES_FILE
    else:
        print_warning(f"{XRESOURCES_DIR} not found. Falling back to user .Xresources.")
        target_file = USER_XRESOURCES
    write_file(target_file, content)
    print_message(
        "Reload your Xresources with 'xrdb -merge {}' or log out and back in.".format(
            target_file
        )
    )


def apply_flatpak_overrides() -> None:
    """
    Apply Flatpak overrides to export the necessary environment variables for
    proper scaling in Flatpak apps.
    """
    # Check if flatpak is installed
    flatpak_path = shutil.which("flatpak")
    if not flatpak_path:
        print_warning("Flatpak not found. Skipping Flatpak override configuration.")
        return

    commands = [
        ["flatpak", "override", "--user", "--env=GDK_SCALE=" + GDK_SCALE],
        ["flatpak", "override", "--user", "--env=GDK_DPI_SCALE=" + GDK_DPI_SCALE],
        [
            "flatpak",
            "override",
            "--user",
            "--env=QT_AUTO_SCREEN_SCALE_FACTOR=" + QT_AUTO_SCREEN_SCALE_FACTOR,
        ],
        ["flatpak", "override", "--user", "--env=QT_SCALE_FACTOR=" + QT_SCALE_FACTOR],
    ]
    for cmd in commands:
        try:
            subprocess.check_call(cmd)
            print_success("Applied Flatpak override: " + " ".join(cmd[-1:]))
        except subprocess.CalledProcessError as e:
            print_warning(
                "Flatpak override command failed: " + " ".join(cmd) + f" ({e})"
            )


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def main_menu() -> None:
    menu_options = [
        ("1", "Apply system profile scaling settings", apply_system_profile_scaling),
        ("2", "Apply Xresources DPI setting", apply_xresources_scaling),
        ("3", "Apply Flatpak scaling overrides", apply_flatpak_overrides),
        (
            "4",
            "Apply all HighDPI scaling settings",
            lambda: [
                func()
                for func in (
                    apply_system_profile_scaling,
                    apply_xresources_scaling,
                    apply_flatpak_overrides,
                )
            ],
        ),
        ("0", "Exit", lambda: sys.exit(0)),
    ]
    while True:
        console.clear()
        console.print(create_header())
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME} | User: {DEFAULT_USERNAME}[/]"
            )
        )
        console.print()
        table = Table(show_header=True, header_style=f"bold {NordColors.FROST_3}")
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")
        for option, description, _ in menu_options:
            table.add_row(option, description)
        console.print(table)
        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory("/tmp/hidpi_command_history"),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).strip()
        for option, _, func in menu_options:
            if choice == option:
                func()
                wait_for_key()
                break
        else:
            print_error("Invalid selection, please try again.")
            wait_for_key()


def main() -> None:
    console.clear()
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
