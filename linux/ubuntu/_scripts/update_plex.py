#!/usr/bin/env python3
"""
Enhanced Plex Updater
----------------------

Downloads and installs the latest Plex Media Server package,
resolves dependency issues, cleans up temporary files, and restarts
the Plex service via system commands.

Note: Run this script with root privileges.
Version: 1.0.0 | License: MIT
"""

import atexit
import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
DEFAULT_PLEX_URL: str = (
    "https://downloads.plex.tv/plex-media-server-new/"
    "1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
)
TEMP_DEB: str = "/tmp/plexmediaserver.deb"
LOG_FILE: str = "/var/log/update_plex.log"
DEFAULT_LOG_LEVEL = logging.INFO
TERM_WIDTH = 100  # Or use shutil.get_terminal_size().columns

# ------------------------------
# Nord-Themed Console Setup
# ------------------------------
console = Console()

# Nord Theme Color Palette
NORD_COLORS = {
    "dark1": "#2E3440",
    "dark2": "#3B4252",
    "dark3": "#434C5E",
    "dark4": "#4C566A",
    "light1": "#D8DEE9",
    "light2": "#E5E9F0",
    "light3": "#ECEFF4",
    "frost1": "#8FBCBB",
    "frost2": "#88C0D0",
    "frost3": "#81A1C1",
    "frost4": "#5E81AC",
    "aurora_red": "#BF616A",
    "aurora_orange": "#D08770",
    "aurora_yellow": "#EBCB8B",
    "aurora_green": "#A3BE8C",
    "aurora_purple": "#B48EAD",
}


def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NORD_COLORS['frost2']}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(
        f"\n[bold {NORD_COLORS['frost2']}]{border}[/bold {NORD_COLORS['frost2']}]"
    )
    console.print(
        f"[bold {NORD_COLORS['frost2']}]  {title.center(TERM_WIDTH - 4)}[/bold {NORD_COLORS['frost2']}]"
    )
    console.print(
        f"[bold {NORD_COLORS['frost2']}]{border}[/bold {NORD_COLORS['frost2']}]\n"
    )


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NORD_COLORS['frost3']}]{message}[/{NORD_COLORS['frost3']}]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(
        f"[bold {NORD_COLORS['aurora_green']}]✓ {message}[/bold {NORD_COLORS['aurora_green']}]"
    )


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(
        f"[bold {NORD_COLORS['aurora_yellow']}]⚠ {message}[/bold {NORD_COLORS['aurora_yellow']}]"
    )


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(
        f"[bold {NORD_COLORS['aurora_red']}]✗ {message}[/bold {NORD_COLORS['aurora_red']}]"
    )


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NORD_COLORS['frost2']}]• {text}[/{NORD_COLORS['frost2']}]")


def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Set up logging with console and file handlers using Nord-themed formatting."""
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(DEFAULT_LOG_LEVEL)

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(log_file, 0o600)
        print_info(f"Logging to {log_file}")
    except Exception as e:
        print_warning(f"Failed to set up log file {log_file}: {e}")
        print_info("Continuing with console logging only")


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    if os.path.exists(TEMP_DEB):
        try:
            os.remove(TEMP_DEB)
            print_info(f"Removed temporary file: {TEMP_DEB}")
            logging.info(f"Removed temporary file: {TEMP_DEB}")
        except Exception as e:
            print_warning(f"Failed to remove temporary file {TEMP_DEB}: {e}")
            logging.warning(f"Failed to remove temporary file {TEMP_DEB}: {e}")


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"Script interrupted by {sig_name}.")
    logging.warning(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ------------------------------
# Dependency & Privilege Checks
# ------------------------------
def check_dependencies() -> None:
    """
    Ensure required system commands are available.
    Required: dpkg, apt-get, systemctl.
    """
    required_commands: List[str] = ["dpkg", "apt-get", "systemctl"]
    missing: List[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Checking dependencies..."),
        transient=True,
    ) as progress:
        task = progress.add_task("Checking", total=len(required_commands))

        for cmd in required_commands:
            try:
                subprocess.run(
                    ["which", cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError:
                missing.append(cmd)
            progress.update(task, advance=1)

    if missing:
        print_error(f"Missing required commands: {', '.join(missing)}")
        logging.error(f"Missing required commands: {', '.join(missing)}")
        sys.exit(1)
    else:
        print_success("All dependencies found.")


def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        logging.error("This script must be run as root.")
        print_info("Please run with: sudo python3 plex_updater.py")
        sys.exit(1)
    else:
        print_success("Running with root privileges.")


# ------------------------------
# Helper Functions
# ------------------------------
def run_command(
    cmd: List[str], check: bool = True, capture_output: bool = False
) -> subprocess.CompletedProcess:
    """Execute a command and log its output."""
    logging.info(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=True
        )
        if result.stdout and capture_output:
            logging.info(result.stdout.strip())
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}")
        if e.stderr:
            logging.error(e.stderr.strip())
        if check:
            raise
        return e


def confirm_action(message: str = "Continue with this action?") -> bool:
    """Ask the user to confirm an action."""
    while True:
        console.print(
            f"[bold {NORD_COLORS['aurora_purple']}]{message} (y/n): [/bold {NORD_COLORS['aurora_purple']}]",
            end="",
        )
        response = input().strip().lower()
        if response in ["y", "yes"]:
            return True
        elif response in ["n", "no"]:
            return False
        print_warning("Please enter 'y' or 'n'")


# ------------------------------
# Plex Update Functions
# ------------------------------
def download_plex(plex_url: str) -> None:
    """
    Download the Plex Media Server package using urllib.

    Args:
        plex_url: URL of the Plex package.
    """
    print_section("Downloading Plex Package")
    print_info(f"Downloading Plex from {plex_url}")
    print_info(f"Saving package to {TEMP_DEB}")
    logging.info(f"Downloading Plex from {plex_url}")

    os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)

    try:
        # Get file size first for progress bar
        with urllib.request.urlopen(plex_url) as response:
            file_size = int(response.info().get("Content-Length", 0))

        # Download with progress bar
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:.0f}%"),
            TextColumn("•"),
            TimeRemainingColumn(),
            TextColumn("•"),
            TextColumn("[bold blue]{task.fields[size]}"),
        ) as progress:
            task = progress.add_task("Downloading", total=file_size, size="0 B")

            def update_progress(block_num, block_size, total_size):
                downloaded = block_num * block_size
                progress.update(
                    task,
                    completed=min(downloaded, total_size),
                    size=format_size(downloaded),
                )

            start_time = time.time()
            urllib.request.urlretrieve(plex_url, TEMP_DEB, reporthook=update_progress)
            elapsed = time.time() - start_time

        final_size = os.path.getsize(TEMP_DEB)
        print_success(
            f"Downloaded in {elapsed:.2f} seconds, size: {format_size(final_size)}"
        )
        logging.info(
            f"Downloaded in {elapsed:.2f} seconds, size: {format_size(final_size)}"
        )
    except Exception as e:
        print_error(f"Failed to download Plex package: {e}")
        logging.error(f"Failed to download Plex package: {e}")
        sys.exit(1)


def install_plex() -> None:
    """
    Install the Plex Media Server package and fix dependency issues.
    """
    print_section("Installing Plex Media Server")
    print_step("Installing Plex package...")
    logging.info("Installing Plex package...")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Installing package..."),
            transient=True,
        ) as progress:
            task = progress.add_task("Installing", total=None)
            run_command(["dpkg", "-i", TEMP_DEB])
            progress.update(task, completed=1)
        print_success("Plex package installed successfully.")
    except subprocess.CalledProcessError:
        print_warning("Dependency issues detected; attempting to fix...")
        logging.warning("Dependency issues detected; attempting to fix...")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Resolving dependencies..."),
                transient=True,
            ) as progress:
                task = progress.add_task("Fixing", total=None)
                run_command(["apt-get", "install", "-f", "-y"])
                progress.update(task, completed=1)

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Reinstalling Plex..."),
                transient=True,
            ) as progress:
                task = progress.add_task("Reinstalling", total=None)
                run_command(["dpkg", "-i", TEMP_DEB])
                progress.update(task, completed=1)

            print_success("Dependencies resolved and Plex installed successfully.")
            logging.info("Dependencies resolved and Plex installed successfully.")
        except subprocess.CalledProcessError:
            print_error("Failed to resolve dependencies for Plex.")
            logging.error("Failed to resolve dependencies for Plex.")
            sys.exit(1)


def restart_plex() -> None:
    """
    Restart the Plex Media Server service.
    """
    print_section("Restarting Plex Service")
    print_step("Restarting Plex service...")
    logging.info("Restarting Plex service...")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Restarting service..."),
            transient=True,
        ) as progress:
            task = progress.add_task("Restarting", total=None)
            run_command(["systemctl", "restart", "plexmediaserver"])
            progress.update(task, completed=1)

        print_success("Plex service restarted successfully.")
        logging.info("Plex service restarted successfully.")
    except subprocess.CalledProcessError:
        print_error("Failed to restart Plex service.")
        logging.error("Failed to restart Plex service.")
        sys.exit(1)


def check_running_plex() -> bool:
    """Check if Plex service is running."""
    try:
        result = run_command(
            ["systemctl", "is-active", "plexmediaserver"],
            check=False,
            capture_output=True,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


# ------------------------------
# Interactive Menu Functions
# ------------------------------
def get_custom_url() -> str:
    """Get a custom Plex download URL from the user."""
    console.print(
        f"\n[{NORD_COLORS['light1']}]Enter the URL to download the Plex package:[/{NORD_COLORS['light1']}]"
    )
    console.print(
        f"[{NORD_COLORS['frost4']}](Press ENTER to use default: {DEFAULT_PLEX_URL})[/{NORD_COLORS['frost4']}]"
    )
    url = input("> ").strip()
    return url if url else DEFAULT_PLEX_URL


def plex_version_menu() -> str:
    """Display versions menu and return selected URL."""
    print_section("Plex Media Server Versions")
    console.print(
        f"[{NORD_COLORS['light1']}]1. Latest Stable (v1.41.4.9463)[/{NORD_COLORS['light1']}]"
    )
    console.print(
        f"[{NORD_COLORS['light1']}]2. Previous Stable (v1.40.1.8227)[/{NORD_COLORS['light1']}]"
    )
    console.print(
        f"[{NORD_COLORS['light1']}]3. Beta Version (v1.42.0.9599)[/{NORD_COLORS['light1']}]"
    )
    console.print(
        f"[{NORD_COLORS['light1']}]4. Specify Custom URL[/{NORD_COLORS['light1']}]"
    )

    versions = {
        "1": "https://downloads.plex.tv/plex-media-server-new/1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb",
        "2": "https://downloads.plex.tv/plex-media-server-new/1.40.1.8227-c0dd5a73e/debian/plexmediaserver_1.40.1.8227-c0dd5a73e_amd64.deb",
        "3": "https://downloads.plex.tv/plex-media-server-new/1.42.0.9599-2f5a2e231/debian/plexmediaserver_1.42.0.9599-2f5a2e231_amd64.deb",
    }

    while True:
        console.print(
            f"\n[bold {NORD_COLORS['aurora_purple']}]Enter your choice (1-4): [/bold {NORD_COLORS['aurora_purple']}]",
            end="",
        )
        choice = input().strip()

        if choice in ["1", "2", "3"]:
            return versions[choice]
        elif choice == "4":
            return get_custom_url()
        else:
            print_error("Invalid choice. Please try again.")


def interactive_menu() -> None:
    """Display the interactive menu."""
    while True:
        print_header("Plex Updater")
        console.print(
            f"Date: [bold {NORD_COLORS['frost3']}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold {NORD_COLORS['frost3']}]"
        )

        # Check if Plex is running
        plex_status = "Running" if check_running_plex() else "Not Running"
        status_color = (
            NORD_COLORS["aurora_green"]
            if plex_status == "Running"
            else NORD_COLORS["aurora_red"]
        )
        console.print(
            f"Plex Status: [bold {status_color}]{plex_status}[/bold {status_color}]"
        )

        console.print(
            f"\n[{NORD_COLORS['light1']}]1. Update Plex (Default Version)[/{NORD_COLORS['light1']}]"
        )
        console.print(
            f"[{NORD_COLORS['light1']}]2. Select Version to Install[/{NORD_COLORS['light1']}]"
        )
        console.print(
            f"[{NORD_COLORS['light1']}]3. Restart Plex Service[/{NORD_COLORS['light1']}]"
        )
        console.print(f"[{NORD_COLORS['light1']}]4. Exit[/{NORD_COLORS['light1']}]")

        console.print(
            f"\n[bold {NORD_COLORS['aurora_purple']}]Enter your choice: [/bold {NORD_COLORS['aurora_purple']}]",
            end="",
        )
        choice = input().strip()

        if choice == "1":
            if confirm_action("Update Plex to the default version?"):
                update_plex(DEFAULT_PLEX_URL)
        elif choice == "2":
            url = plex_version_menu()
            if confirm_action(f"Install Plex from {url}?"):
                update_plex(url)
        elif choice == "3":
            if confirm_action("Restart Plex service?"):
                restart_plex()
        elif choice == "4":
            print_info("Exiting. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again.")

        if choice in ["1", "2", "3"]:
            console.print(
                f"\n[bold {NORD_COLORS['aurora_purple']}]Press Enter to continue...[/bold {NORD_COLORS['aurora_purple']}]"
            )
            input()


def update_plex(plex_url: str) -> None:
    """Complete Plex update process."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    download_plex(plex_url)
    install_plex()
    restart_plex()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

    print_success("Plex update completed successfully!")


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        print_header("Plex Updater v1.0.0")
        setup_logging()
        check_dependencies()
        check_root()

        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Plex Media Server Updater")
        parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Run in non-interactive mode with default settings",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=DEFAULT_PLEX_URL,
            help="URL to download the Plex package (non-interactive mode only)",
        )
        args = parser.parse_args()

        if args.non_interactive:
            update_plex(args.url)
        else:
            interactive_menu()

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
