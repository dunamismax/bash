#!/usr/bin/env python3
"""
Pop!_OS HighDPI & AMD Screen Tearing Fixer
--------------------------------------------------
This script applies system-wide HighDPI scaling settings and an AMD tear fix
for Pop!_OS running GNOME on X11. It sets the appropriate environment variables
(for GTK/Qt apps), writes the necessary Xresources for DPI configuration, applies
Flatpak overrides so that Flatpak apps use neutral scaling, and installs/configures
picom with vsync enabled to address AMD screen tearing.

Version: 1.2.0
"""

import os
import sys
import time
import socket
import signal
import atexit
import subprocess
import getpass
import shutil
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


def install_dependencies() -> None:
    """
    Ensure required third-party dependencies (paramiko, rich, pyfiglet,
    prompt_toolkit) are installed. If missing, they are installed and the script
    is restarted.
    """
    if os.environ.get("DEPENDENCIES_INSTALLED"):
        return

    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    try:
        import paramiko, pyfiglet
        from rich.console import Console
        from prompt_toolkit import prompt as pt_prompt
    except ImportError:
        print("Required libraries not found. Installing dependencies...")
        user = os.environ.get("SUDO_USER", getpass.getuser())
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        else:
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
        print("Dependencies installed. Restarting script...")
        os.environ["DEPENDENCIES_INSTALLED"] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)


install_dependencies()

# Now that dependencies are installed, import them.
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
# Configuration & Constants for Pop!_OS (GNOME on X11)
# ----------------------------------------------------------------
APP_NAME: str = "Pop!_OS HighDPI & AMD Screen Tearing Fixer"
VERSION: str = "1.2.0"
APP_SUBTITLE: str = "GNOME (X11) HighDPI Scaling & AMD Tear Fix for Pop!_OS"
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)

# Directory for configuration backups
BACKUP_DIR: str = os.path.join(os.path.expanduser("~"), ".popos_hidpi_backup")
os.makedirs(BACKUP_DIR, exist_ok=True)

# -- System (host) scaling settings for native GNOME/APT apps --
# These values are exported system-wide and applied to GTK/Qt apps.
GDK_SCALE: str = "1"
GDK_DPI_SCALE: str = "1.5"  # ~150% scaling for text
QT_AUTO_SCREEN_SCALE_FACTOR: str = "0"
QT_SCALE_FACTOR: str = "1.5"
XFT_DPI: str = "144"  # (96 * 1.5)

# -- Flatpak-specific scaling overrides --
# Flatpak apps run in a sandbox where the host DPI from Xresources is not applied.
# We use neutral (1×) scaling here to avoid double scaling.
FLATPAK_GDK_SCALE: str = "1"
FLATPAK_GDK_DPI_SCALE: str = "1"
FLATPAK_QT_AUTO_SCREEN_SCALE_FACTOR: str = "0"
FLATPAK_QT_SCALE_FACTOR: str = "1"

# System configuration file paths
PROFILE_SCRIPT: str = "/etc/profile.d/90-popos-hidpi.sh"
XRESOURCES_DIR: str = "/etc/X11/Xresources.d"
XRESOURCES_FILE: str = os.path.join(XRESOURCES_DIR, "80-hidpi.conf")
USER_XRESOURCES: str = os.path.join(os.path.expanduser("~"), ".Xresources")


# ----------------------------------------------------------------
# Nord-Themed Colors (for console UI)
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
    styled_text = f"{border}\n{styled_text}{border}"
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
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def signal_handler(sig, frame) -> None:
    print_warning(f"Interrupted by signal {sig}. Exiting...")
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(lambda: console.print("[bold dim]Exiting Pop!_OS HighDPI Fixer...[/]"))


# ----------------------------------------------------------------
# Helper Functions for Backup and File Writing
# ----------------------------------------------------------------
def backup_file(file_path: str) -> None:
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
    try:
        backup_file(file_path)
        with open(file_path, "w") as f:
            f.write(content)
        print_success(f"Settings written to {file_path}")
        return True
    except Exception as e:
        print_error(f"Error writing to {file_path}: {e}")
        return False


# ----------------------------------------------------------------
# HighDPI Scaling Configuration Functions (Pop!_OS / GNOME on X11)
# ----------------------------------------------------------------
def apply_system_profile_scaling() -> None:
    """
    Create or update a system-wide profile script to export HighDPI settings.
    This requires root privileges.
    """
    if os.geteuid() != 0:
        print_error(
            "System-wide changes require root privileges. Please run with sudo."
        )
        return

    content = (
        "#!/bin/sh\n"
        "# HighDPI settings for 150% scaling on Pop!_OS (GNOME on X11)\n"
        f"export GDK_SCALE={GDK_SCALE}\n"
        f"export GDK_DPI_SCALE={GDK_DPI_SCALE}\n"
        f"export QT_AUTO_SCREEN_SCALE_FACTOR={QT_AUTO_SCREEN_SCALE_FACTOR}\n"
        f"export QT_SCALE_FACTOR={QT_SCALE_FACTOR}\n"
    )
    if write_file(PROFILE_SCRIPT, content):
        try:
            os.chmod(PROFILE_SCRIPT, 0o755)
        except Exception as e:
            print_warning(f"Could not set execute permissions on {PROFILE_SCRIPT}: {e}")


def apply_xresources_scaling() -> None:
    """
    Configure Xft DPI via Xresources for X11.
    """
    content = f"Xft.dpi: {XFT_DPI}\n"
    target_file = XRESOURCES_FILE if os.path.isdir(XRESOURCES_DIR) else USER_XRESOURCES
    if target_file == USER_XRESOURCES:
        print_warning(f"{XRESOURCES_DIR} not found. Falling back to user .Xresources.")
    if write_file(target_file, content):
        print_message(
            f"Reload Xresources with 'xrdb -merge {target_file}' or log out and back in."
        )


def apply_flatpak_overrides() -> None:
    """
    Apply Flatpak environment overrides so that Flatpak apps
    use neutral (1×) scaling. This avoids extra scaling on top of the system
    settings already applied via Xresources and the profile script.
    """
    flatpak_path = shutil.which("flatpak")
    if not flatpak_path:
        print_warning("Flatpak not found. Skipping Flatpak override configuration.")
        return

    commands = [
        ["flatpak", "override", "--user", "--env=GDK_SCALE=" + FLATPAK_GDK_SCALE],
        [
            "flatpak",
            "override",
            "--user",
            "--env=GDK_DPI_SCALE=" + FLATPAK_GDK_DPI_SCALE,
        ],
        [
            "flatpak",
            "override",
            "--user",
            "--env=QT_AUTO_SCREEN_SCALE_FACTOR=" + FLATPAK_QT_AUTO_SCREEN_SCALE_FACTOR,
        ],
        [
            "flatpak",
            "override",
            "--user",
            "--env=QT_SCALE_FACTOR=" + FLATPAK_QT_SCALE_FACTOR,
        ],
    ]
    for cmd in commands:
        try:
            subprocess.check_call(cmd)
            print_success("Applied Flatpak override: " + " ".join(cmd[-1:]))
        except subprocess.CalledProcessError as e:
            print_warning(
                "Flatpak override command failed: " + " ".join(cmd) + f" ({e})"
            )


def apply_amd_screen_tearing_fix() -> None:
    """
    Fix AMD screen tearing on X11 by installing/configuring picom with vsync enabled.
    """
    picom_path = shutil.which("picom")
    if not picom_path:
        print_warning("picom is not installed. It is required for the AMD tear fix.")
        if Confirm.ask(
            "[bold " + NordColors.PURPLE + "]Install picom via apt?[/]", default=True
        ):
            try:
                subprocess.check_call(["sudo", "apt", "install", "-y", "picom"])
                print_success("picom installed successfully.")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to install picom: {e}")
                return
        else:
            print_warning(
                "picom installation skipped. Cannot apply screen tearing fix."
            )
            return

    config_dir = os.path.join(os.path.expanduser("~"), ".config")
    os.makedirs(config_dir, exist_ok=True)
    picom_config = os.path.join(config_dir, "picom.conf")
    content = (
        "# picom configuration for AMD tear-free rendering on X11 (Pop!_OS)\n"
        'backend = "glx";\n'
        "vsync = true;\n"
        "unredir-if-possible = true;\n"
    )
    if write_file(picom_config, content):
        print_success(f"picom configuration written to {picom_config}.")
        print_message(
            "Restart picom or log out and back in for changes to take effect."
        )
    else:
        print_error("Failed to write picom configuration.")


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def main_menu() -> None:
    menu_options = [
        ("1", "Apply system profile scaling settings", apply_system_profile_scaling),
        ("2", "Apply Xresources DPI setting", apply_xresources_scaling),
        ("3", "Apply Flatpak scaling overrides", apply_flatpak_overrides),
        ("4", "Apply AMD screen tearing fix (picom)", apply_amd_screen_tearing_fix),
        (
            "5",
            "Apply all fixes",
            lambda: [
                func()
                for func in (
                    apply_system_profile_scaling,
                    apply_xresources_scaling,
                    apply_flatpak_overrides,
                    apply_amd_screen_tearing_fix,
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
            history=FileHistory("/tmp/popos_hidpi_history"),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).strip()
        executed = False
        for option, _, func in menu_options:
            if choice == option:
                if option == "0":
                    sys.exit(0)
                func()
                executed = True
                if not Confirm.ask("Return to main menu?", default=True):
                    sys.exit(0)
                break
        if not executed:
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
