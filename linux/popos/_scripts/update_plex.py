#!/usr/bin/env python3
"""
Plex Updater
--------------------------------------------------

A streamlined terminal interface for updating Plex Media Server on Linux systems.
This interactive script features a stylish ASCII banner, numbered menu options,
rich progress indicators, and automatic dependency resolution.

Usage:
  Run the script with root privileges (sudo) and follow the on-screen prompts.
  • Enter the Plex download URL when prompted.
  • The script will handle downloading, installation, and restarting the Plex service.

Version: 2.0.0
"""

import atexit
import os
import signal
import subprocess
import sys
import time
import urllib.request
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

# ----------------------------------------------------------------
# Third-Party Libraries
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install Rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Global Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Plex Updater"
APP_SUBTITLE: str = "Automated Plex Media Server Update Tool"
VERSION: str = "2.0.0"
TEMP_DEB: str = "/tmp/plexmediaserver.deb"
LOG_FILE: str = "/var/log/plex_updater.log"
OPERATION_TIMEOUT: int = 300  # seconds

SYSTEM_INFO: Dict[str, str] = {
    "host": platform.node(),
    "os": platform.system(),
    "dist": platform.platform(),
    "kernel": platform.release(),
}


# ----------------------------------------------------------------
# Nord-Themed Colors for Styling
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

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


# Create a Rich console instance
console: Console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class PlexServerInfo:
    """Holds information about the Plex Media Server installation."""

    version: Optional[str] = None
    status: Optional[bool] = None
    install_path: Optional[str] = None
    url: Optional[str] = None


# ----------------------------------------------------------------
# UI Helpers: Banner, Messages & Panels
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate an ASCII art header using Pyfiglet with Nord styling.
    Returns:
        A Rich Panel containing the styled header.
    """
    fonts = ["slant", "small", "smslant", "mini", "digital"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME

    # Apply gradient style
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_lines = []
    for i, line in enumerate(ascii_art.splitlines()):
        if line.strip():
            color = colors[i % len(colors)]
            styled_lines.append(f"[bold {color}]{line}[/]")
    styled_text = "\n".join(styled_lines)
    border = f"[{NordColors.FROST_3}]{'━' * 30}[/]"

    header_markup = f"{border}\n{styled_text}\n{border}"
    return Panel(
        Text.from_markup(header_markup),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message to the console."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(text: str) -> None:
    """Print an informational message."""
    print_message(text, NordColors.FROST_3, "ℹ")


def print_success(text: str) -> None:
    """Print a success message."""
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """Print an error message."""
    print_message(text, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message inside a styled Rich panel."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def display_section_title(title: str) -> None:
    """Display a decorative section title."""
    width = console.width or 80
    border = "═" * width
    console.print(f"[bold {NordColors.FROST_1}]{border}[/]")
    console.print(Align.center(f"[bold {NordColors.FROST_2}]{title.upper()}[/]"))
    console.print(f"[bold {NordColors.FROST_1}]{border}[/]\n")


def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Execute a system command.
    Returns:
        A CompletedProcess instance with command results.
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    if os.path.exists(TEMP_DEB):
        try:
            print_info(f"Removing temporary file: {TEMP_DEB}")
            os.remove(TEMP_DEB)
            print_success("Cleanup completed")
        except Exception as e:
            print_warning(f"Failed to remove temporary file: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """Gracefully handle termination signals."""
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# System & Dependency Checks
# ----------------------------------------------------------------
def check_root() -> bool:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_info("Please run with: sudo python3 plex_updater.py")
        return False
    print_success("Running with root privileges")
    return True


def check_dependencies() -> bool:
    """
    Verify that required system commands exist.
    Returns:
        True if all commands are available, False otherwise.
    """
    required_commands = ["dpkg", "apt-get", "systemctl"]
    missing = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Checking", total=len(required_commands))
        for cmd in required_commands:
            try:
                run_command(["which", cmd])
                progress.advance(task)
            except Exception:
                missing.append(cmd)
                progress.advance(task)
    if missing:
        print_error(f"Missing commands: {', '.join(missing)}")
        return False
    print_success("All required dependencies are available")
    return True


def get_plex_status() -> PlexServerInfo:
    """
    Retrieve the current Plex Media Server status.
    Returns:
        A PlexServerInfo object with version, status, and install path.
    """
    info = PlexServerInfo()
    try:
        result = run_command(["systemctl", "is-active", "plexmediaserver"], check=False)
        info.status = result.stdout.strip() == "active"
    except Exception:
        info.status = False
    try:
        result = run_command(
            ["dpkg-query", "-W", "-f=${Version}", "plexmediaserver"],
            check=False,
        )
        if result.returncode == 0:
            info.version = result.stdout.strip()
    except Exception:
        info.version = None
    info.install_path = "/usr/lib/plexmediaserver"
    return info


# ----------------------------------------------------------------
# Core Update Functions
# ----------------------------------------------------------------
def get_plex_download_url() -> str:
    """
    Prompt the user to enter the Plex download URL.
    Returns:
        A valid Plex download URL string.
    """
    display_panel(
        "Visit https://www.plex.tv/media-server-downloads/ for the latest download link.",
        style=NordColors.FROST_3,
        title="Download Information",
    )
    console.print(f"[bold {NordColors.FROST_2}]Enter the Plex download URL:[/]")
    while True:
        url = input("> ").strip()
        if not url:
            print_error("URL cannot be empty.")
            continue
        if not (url.startswith("http://") or url.startswith("https://")):
            print_error("URL must start with http:// or https://")
            continue
        if not url.endswith(".deb"):
            print_warning(
                "URL does not end with .deb – is this a Debian/Ubuntu package?"
            )
            if not confirm_action("Continue with this URL anyway?"):
                continue
        return url


def download_plex(url: str) -> bool:
    """
    Download the Plex Media Server package.
    Returns:
        True if the download is successful, False otherwise.
    """
    display_section_title("Downloading Plex Media Server")
    print_info(f"Download URL: {url}")
    print_info(f"Saving to: {TEMP_DEB}")
    try:
        os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)
        with urllib.request.urlopen(url) as response:
            file_size = int(response.info().get("Content-Length", 0))
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TextColumn(f"[{NordColors.FROST_3}]{{task.fields[size]}}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=file_size, size="0 B")

            def update_progress(
                block_num: int, block_size: int, total_size: int
            ) -> None:
                downloaded = block_num * block_size
                progress.update(
                    task,
                    completed=min(downloaded, total_size),
                    size=format_size(downloaded),
                )

            start = time.time()
            urllib.request.urlretrieve(url, TEMP_DEB, reporthook=update_progress)
            elapsed = time.time() - start
        final_size = os.path.getsize(TEMP_DEB)
        print_success(f"Download completed in {elapsed:.2f} seconds")
        print_success(f"Package size: {format_size(final_size)}")
        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def install_plex() -> bool:
    """
    Install the downloaded Plex package.
    Returns:
        True if installation is successful, False otherwise.
    """
    display_section_title("Installing Plex Media Server")
    if not os.path.exists(TEMP_DEB):
        print_error(f"Package file not found: {TEMP_DEB}")
        return False
    print_info("Installing Plex Media Server package...")
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing package..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Installing", total=None)
            run_command(["dpkg", "-i", TEMP_DEB])
            progress.update(task, completed=1)
        print_success("Package installed successfully")
        return True
    except subprocess.CalledProcessError:
        print_warning("Dependency issues detected; attempting to resolve...")
        try:
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Resolving dependencies..."),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Fixing", total=None)
                run_command(["apt-get", "install", "-f", "-y"])
                progress.update(task, completed=1)
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Reinstalling package..."),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Reinstalling", total=None)
                run_command(["dpkg", "-i", TEMP_DEB])
                progress.update(task, completed=1)
            print_success("Dependencies resolved and package installed successfully")
            return True
        except Exception as e:
            print_error(f"Installation failed: {e}")
            return False
    except Exception as e:
        print_error(f"Installation failed: {e}")
        return False


def restart_plex_service() -> bool:
    """
    Restart the Plex Media Server service.
    Returns:
        True if the service restarts successfully, False otherwise.
    """
    display_section_title("Restarting Plex Media Server")
    print_info("Restarting Plex service...")
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Restarting service..."),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Restarting", total=None)
            run_command(["systemctl", "restart", "plexmediaserver"])
            progress.update(task, completed=1)
        time.sleep(2)
        result = run_command(["systemctl", "is-active", "plexmediaserver"], check=False)
        if result.stdout.strip() == "active":
            print_success("Plex service restarted successfully")
            return True
        else:
            print_error("Plex service failed to start")
            return False
    except Exception as e:
        print_error(f"Service restart failed: {e}")
        return False


def update_plex() -> bool:
    """
    Execute the complete Plex update process.
    Returns:
        True if update is successful, False otherwise.
    """
    url = get_plex_download_url()
    console.print()
    if not confirm_action(
        f"Ready to download and install Plex from:\n{url}\n\nContinue?"
    ):
        print_info("Update cancelled by user")
        return False
    if not download_plex(url):
        return False
    if not install_plex():
        return False
    if not restart_plex_service():
        return False
    display_panel(
        "Plex Media Server has been successfully updated!",
        style=NordColors.GREEN,
        title="Update Complete",
    )
    return True


# ----------------------------------------------------------------
# User Interaction Helpers
# ----------------------------------------------------------------
def confirm_action(message: str = "Continue with this action?") -> bool:
    """
    Prompt the user for a yes/no confirmation.
    Returns:
        True if confirmed, False otherwise.
    """
    while True:
        console.print(f"[bold {NordColors.PURPLE}]{message} (y/n):[/] ", end="")
        choice = input().strip().lower()
        if choice in ["y", "yes"]:
            return True
        elif choice in ["n", "no"]:
            return False
        else:
            print_warning("Please enter 'y' or 'n'.")


def press_enter_to_continue() -> None:
    """Wait for the user to press Enter."""
    console.print(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue...[/]", end="")
    input()


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def display_status_panel() -> None:
    """Display current Plex server status information."""
    server_info = get_plex_status()
    status = "RUNNING" if server_info.status else "STOPPED"
    color = NordColors.GREEN if server_info.status else NordColors.RED
    message = f"Status: [bold {color}]{status}[/]\n"
    message += f"Version: [bold {NordColors.SNOW_STORM_1}]{server_info.version or 'Unknown'}[/]\n"
    message += f"Install Path: [bold {NordColors.SNOW_STORM_1}]{server_info.install_path or 'N/A'}[/]"
    panel = Panel(
        Text.from_markup(message),
        title=f"[bold {NordColors.FROST_3}]Plex Server Information[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(panel)


def show_main_menu() -> None:
    """Display the main interactive menu and process user selections."""
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {SYSTEM_INFO['host']}[/]"
            )
        )
        console.print()
        display_status_panel()
        console.print()
        console.print(f"[bold {NordColors.FROST_2}]Main Menu[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]1. Update Plex Media Server[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]2. Restart Plex Service[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]3. Exit[/]")
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Enter your choice (1-3):[/] ", end="")
        choice = input().strip()
        if choice == "1":
            update_plex()
            press_enter_to_continue()
        elif choice == "2":
            if confirm_action("Are you sure you want to restart the Plex service?"):
                restart_plex_service()
            press_enter_to_continue()
        elif choice == "3":
            console.clear()
            display_panel(
                "Thank you for using the Plex Updater!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break
        else:
            print_error("Invalid choice. Please enter a number between 1 and 3.")
            press_enter_to_continue()


# ----------------------------------------------------------------
# Main Program Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Set up the environment and launch the interactive menu."""
    try:
        console.clear()
        console.print(create_header())
        if not check_root() or not check_dependencies():
            display_panel(
                "Please address the issues above and try again.",
                style=NordColors.RED,
                title="Setup Failed",
            )
            sys.exit(1)
        show_main_menu()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
