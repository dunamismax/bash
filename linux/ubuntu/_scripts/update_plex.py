#!/usr/bin/env python3
"""
Enhanced Plex Updater
--------------------------------------------------

A streamlined terminal interface for updating Plex Media Server on Linux systems.
Features interactive menus, download progress tracking, and automatic dependency resolution.
The script prompts for the latest Plex download URL and handles the entire update process.

Usage:
  Run the script with root privileges (sudo) and follow the on-screen prompts.
  - Enter the Plex download URL when prompted
  - The script will handle downloading, installation, and restarting the Plex service
  - You can also use the interactive menu to perform specific actions

Version: 2.0.0
"""

import atexit
import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
import platform
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
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

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
APP_NAME: str = "Plex Updater"
APP_SUBTITLE: str = "Automated Plex Media Server Update Tool"
VERSION: str = "2.0.0"
TEMP_DEB: str = "/tmp/plexmediaserver.deb"
LOG_FILE: str = "/var/log/plex_updater.log"
SYSTEM_INFO: Dict[str, str] = {
    "host": platform.node(),
    "os": platform.system(),
    "dist": " ".join(platform.dist())
    if hasattr(platform, "dist")
    else platform.platform(),
    "kernel": platform.release(),
}
OPERATION_TIMEOUT: int = 300  # seconds


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class PlexServerInfo:
    """
    Contains information about the Plex Media Server installation.

    Attributes:
        version: Current installed version
        status: Service status (running/stopped)
        install_path: Path to the Plex installation
        url: URL for the update package
    """

    version: Optional[str] = None
    status: Optional[bool] = None
    install_path: Optional[str] = None
    url: Optional[str] = None


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with Nord styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
       _                             _       _            
 _ __ | | _____  __  _   _ _ __   __| | __ _| |_ ___ _ __ 
| '_ \| |/ _ \ \/ / | | | | '_ \ / _` |/ _` | __/ _ \ '__|
| |_) | |  __/>  <  | |_| | |_) | (_| | (_| | ||  __/ |   
| .__/|_|\___/_/\_\  \__,_| .__/ \__,_|\__,_|\__\___|_|   
|_|                       |_|                             
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements (shorter than before)
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),  # Reduced padding
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
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
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def display_section_title(title: str) -> None:
    """
    Display a section title with decorative elements.

    Args:
        title: The section title to display
    """
    width = console.width or 80
    border = "═" * width

    console.print(f"[bold {NordColors.FROST_1}]{border}[/]")
    console.print(Align.center(f"[bold {NordColors.FROST_2}]{title.upper()}[/]"))
    console.print(f"[bold {NordColors.FROST_1}]{border}[/]")
    console.print()  # Add an empty line after the title


def format_size(num_bytes: float) -> str:
    """
    Convert bytes to a human-readable string.

    Args:
        num_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "5.2 MB")
    """
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
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
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
    """Perform any cleanup tasks before exit."""
    if os.path.exists(TEMP_DEB):
        try:
            print_info(f"Removing temporary file: {TEMP_DEB}")
            os.remove(TEMP_DEB)
            print_success("Cleanup completed successfully")
        except Exception as e:
            print_warning(f"Failed to clean up temporary file: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# System and Dependency Checks
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges")
        print_info("Please run with: sudo python3 plex_updater.py")
        return False

    print_success("Running with root privileges")
    return True


def check_dependencies() -> bool:
    """
    Verify that all required system commands are available.

    Returns:
        True if all dependencies are met, False otherwise
    """
    required_commands = ["dpkg", "apt-get", "systemctl"]
    missing_commands = []

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking dependencies..."),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Checking", total=len(required_commands))

        for cmd in required_commands:
            try:
                run_command(["which", cmd], check=True, capture_output=True)
                progress.update(task, advance=1)
            except Exception:
                missing_commands.append(cmd)
                progress.update(task, advance=1)

    if missing_commands:
        print_error(f"Missing required commands: {', '.join(missing_commands)}")
        return False

    print_success("All required dependencies are available")
    return True


def get_plex_status() -> PlexServerInfo:
    """
    Get current Plex server information.

    Returns:
        PlexServerInfo object with current Plex server status
    """
    server_info = PlexServerInfo()

    # Check if Plex service is running
    try:
        result = run_command(
            ["systemctl", "is-active", "plexmediaserver"],
            check=False,
            capture_output=True,
        )
        server_info.status = result.stdout.strip() == "active"
    except Exception:
        server_info.status = False

    # Try to get version information
    try:
        # This command might vary depending on the system
        result = run_command(
            ["dpkg-query", "-W", "-f=${Version}", "plexmediaserver"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            server_info.version = result.stdout.strip()
    except Exception:
        server_info.version = None

    # Try to get install path
    try:
        server_info.install_path = "/usr/lib/plexmediaserver"
    except Exception:
        server_info.install_path = None

    return server_info


# ----------------------------------------------------------------
# Core Update Functions
# ----------------------------------------------------------------
def get_plex_download_url() -> str:
    """
    Prompt the user to enter the Plex download URL.

    Returns:
        The URL entered by the user
    """
    console.print()
    display_panel(
        "Please visit https://www.plex.tv/media-server-downloads/ to get the latest download link",
        style=NordColors.FROST_3,
        title="Download Information",
    )

    console.print(f"[bold {NordColors.FROST_2}]Enter the Plex download URL:[/]")

    # Keep asking until we get a valid URL
    while True:
        url = input("> ").strip()

        if not url:
            print_error("URL cannot be empty. Please enter a valid Plex download URL.")
            continue

        if not (url.startswith("http://") or url.startswith("https://")):
            print_error("URL must start with http:// or https://")
            continue

        if not url.endswith(".deb"):
            print_warning(
                "URL does not end with .deb - is this a Debian/Ubuntu package?"
            )
            if not confirm_action("Continue with this URL anyway?"):
                continue

        return url


def download_plex(url: str) -> bool:
    """
    Download the Plex Media Server package.

    Args:
        url: The URL to download from

    Returns:
        True if download was successful, False otherwise
    """
    display_section_title("Downloading Plex Media Server")

    print_info(f"Download URL: {url}")
    print_info(f"Saving to: {TEMP_DEB}")

    try:
        # Create temporary directory if it doesn't exist
        os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)

        # Get file size if possible
        with urllib.request.urlopen(url) as response:
            file_size = int(response.info().get("Content-Length", 0))

        # Download with progress bar
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

            # Start download with progress reporting
            start_time = time.time()
            urllib.request.urlretrieve(url, TEMP_DEB, reporthook=update_progress)
            elapsed = time.time() - start_time

        # Get final file size and report success
        final_size = os.path.getsize(TEMP_DEB)
        print_success(f"Download completed in {elapsed:.2f} seconds")
        print_success(f"Package size: {format_size(final_size)}")
        return True

    except Exception as e:
        print_error(f"Download failed: {str(e)}")
        return False


def install_plex() -> bool:
    """
    Install the downloaded Plex Media Server package.

    Returns:
        True if installation was successful, False otherwise
    """
    display_section_title("Installing Plex Media Server")

    if not os.path.exists(TEMP_DEB):
        print_error(f"Package file not found: {TEMP_DEB}")
        return False

    print_info("Installing Plex Media Server package...")

    try:
        # First attempt: Try direct installation
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
        # Second attempt: Fix dependencies and retry
        print_warning("Dependency issues detected, attempting to resolve...")

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
            print_error(f"Installation failed: {str(e)}")
            return False

    except Exception as e:
        print_error(f"Installation failed: {str(e)}")
        return False


def restart_plex_service() -> bool:
    """
    Restart the Plex Media Server service.

    Returns:
        True if service was restarted successfully, False otherwise
    """
    display_section_title("Restarting Plex Media Server")

    print_info("Restarting Plex Media Server service...")

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

        # Add a short delay to allow the service to start
        time.sleep(2)

        # Verify the service is now running
        result = run_command(
            ["systemctl", "is-active", "plexmediaserver"],
            check=False,
            capture_output=True,
        )

        if result.stdout.strip() == "active":
            print_success("Plex Media Server service restarted successfully")
            return True
        else:
            print_error("Plex Media Server service failed to start")
            return False

    except Exception as e:
        print_error(f"Failed to restart service: {str(e)}")
        return False


def update_plex() -> bool:
    """
    Run the complete Plex update process.

    Returns:
        True if the update was successful, False otherwise
    """
    # Get the download URL from user
    url = get_plex_download_url()

    # Confirm before proceeding
    console.print()
    if not confirm_action(
        f"Ready to download and install Plex from:\n{url}\n\nContinue?"
    ):
        print_info("Update cancelled by user")
        return False

    # Download the package
    if not download_plex(url):
        return False

    # Install the package
    if not install_plex():
        return False

    # Restart the service
    if not restart_plex_service():
        return False

    # Update completed successfully
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
    Prompt the user for confirmation.

    Args:
        message: The confirmation message to display

    Returns:
        True if the user confirms, False otherwise
    """
    while True:
        console.print(f"[bold {NordColors.PURPLE}]{message} (y/n):[/] ", end="")
        choice = input().strip().lower()

        if choice in ["y", "yes"]:
            return True
        elif choice in ["n", "no"]:
            return False
        else:
            print_warning("Please enter 'y' or 'n'")


def press_enter_to_continue() -> None:
    """Prompt user to press Enter to continue."""
    console.print(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue...[/]", end="")
    input()


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def display_status_panel() -> None:
    """Display the current Plex server status."""
    server_info = get_plex_status()

    # Determine status color
    status_text = "RUNNING" if server_info.status else "STOPPED"
    status_color = NordColors.GREEN if server_info.status else NordColors.RED

    # Create message
    message = f"Status: [bold {status_color}]{status_text}[/]\n"

    if server_info.version:
        message += (
            f"Version: [bold {NordColors.SNOW_STORM_1}]{server_info.version}[/]\n"
        )
    else:
        message += f"Version: [dim {NordColors.POLAR_NIGHT_4}]Unknown[/]\n"

    if server_info.install_path:
        message += f"Install Path: [bold {NordColors.SNOW_STORM_1}]{server_info.install_path}[/]"

    panel = Panel(
        Text.from_markup(message),
        title=f"[bold {NordColors.FROST_3}]Plex Server Information[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )

    console.print(panel)


def show_main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        console.clear()
        console.print(create_header())

        # Display current date/time and system info
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {SYSTEM_INFO['host']}[/]"
            )
        )
        console.print()

        # Display current Plex status
        display_status_panel()
        console.print()

        # Display menu options
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
            return
        else:
            print_error("Invalid choice. Please enter a number between 1 and 3.")
            press_enter_to_continue()


# ----------------------------------------------------------------
# Main Program Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main program entry point."""
    try:
        console.clear()
        console.print(create_header())

        # Check root and dependencies
        if not check_root() or not check_dependencies():
            display_panel(
                "Please address the issues above and try again.",
                style=NordColors.RED,
                title="Setup Failed",
            )
            sys.exit(1)

        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Plex Media Server Updater")
        parser.add_argument(
            "--update-only",
            action="store_true",
            help="Skip the menu and directly update Plex",
        )
        args = parser.parse_args()

        if args.update_only:
            update_plex()
        else:
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
