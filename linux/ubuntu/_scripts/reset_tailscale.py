#!/usr/bin/env python3
"""
Enhanced Tailscale Reset Utility
--------------------------------

A beautiful, interactive terminal-based utility for managing Tailscale on Ubuntu systems.
This tool provides options to:
  • Stop and disable the tailscaled service
  • Uninstall tailscale and remove configuration/data directories
  • Reinstall tailscale via the official install script
  • Enable and start the tailscaled service
  • Run "tailscale up" to bring the daemon up

All functionality is menu-driven with an attractive Nord-themed interface.

Note: Some operations require root privileges.

Version: 1.0.0
"""

import atexit
import datetime
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskID,
)
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Tailscale Reset Utility"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.expanduser("~/tailscale_reset_logs/tailscale_reset.log")
TAILSCALE_INSTALL_URL = "https://tailscale.com/install.sh"
CHECK_INTERVAL = 2  # seconds between steps

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()


# Nord Theme Color Definitions
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


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Get a choice from the user with a styled prompt."""
    return Prompt.ask(
        f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Get confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")

    for key, description in options:
        table.add_row(key, description)

    return table


# ==============================
# Logging Setup
# ==============================
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add specific cleanup tasks here if needed


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ==============================
# Progress Tracking Classes
# ==============================
class ProgressManager:
    """Unified progress tracking system with multiple display options."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.NORD8
    ) -> TaskID:
        """Add a new task to the progress manager."""
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        """Update a task's progress."""
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self):
        """Start displaying the progress bar."""
        self.progress.start()

    def stop(self):
        """Stop displaying the progress bar."""
        self.progress.stop()


class Spinner:
    """Thread-safe spinner for indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Internal method to update the spinner."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)  # Spinner update interval

    def start(self) -> None:
        """Start the spinner."""
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner and display completion message."""
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            # Clear the line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            if success:
                console.print(
                    f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD14}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD11}]failed[/] after {time_str}"
                )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit."""
        self.stop(success=exc_type is None)


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ==============================
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 60,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
    if verbose:
        if shell:
            print_step(f"Executing: {cmd}")
        else:
            print_step(f"Executing: {' '.join(cmd)}")

    try:
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        if shell:
            print_error(f"Command failed: {cmd}")
        else:
            print_error(f"Command failed: {' '.join(cmd)}")

        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.NORD11}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


def check_root() -> bool:
    """Check if script is running with elevated privileges."""
    return os.geteuid() == 0


def ensure_root() -> None:
    """Ensure the script is run with root privileges."""
    if not check_root():
        print_error("This operation requires root privileges.")
        print_info("Please run the script with sudo.")
        sys.exit(1)


# ==============================
# Tailscale Operation Functions
# ==============================
def uninstall_tailscale() -> None:
    """Stop tailscaled, uninstall tailscale, and remove configuration/data directories."""
    ensure_root()
    print_section("Uninstalling Tailscale")

    # Define steps for uninstallation
    steps = [
        ("Stopping tailscaled service", ["systemctl", "stop", "tailscaled"]),
        ("Disabling tailscaled service", ["systemctl", "disable", "tailscaled"]),
        (
            "Removing tailscale package",
            ["apt-get", "remove", "--purge", "tailscale", "-y"],
        ),
        ("Autoremoving unused packages", ["apt-get", "autoremove", "-y"]),
    ]

    # Execute each step with progress tracking
    with ProgressManager() as progress:
        task = progress.add_task("Uninstalling Tailscale", total=len(steps))
        progress.start()

        for desc, cmd in steps:
            print_step(desc)
            try:
                run_command(cmd)
                progress.update(
                    task, advance=1, status=f"[{NordColors.NORD9}]Completed"
                )
            except Exception as e:
                print_error(f"Error during {desc}: {e}")
                if not get_user_confirmation("Continue with remaining steps?"):
                    print_warning("Uninstallation aborted.")
                    return
                progress.update(task, advance=1, status=f"[{NordColors.NORD11}]Failed")

    # Remove configuration/data directories
    config_paths = ["/var/lib/tailscale", "/etc/tailscale", "/usr/share/tailscale"]
    print_step("Removing configuration directories...")

    for path in config_paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print_success(f"Removed {path}")
            except Exception as e:
                print_warning(f"Failed to remove {path}: {e}")

    print_success("Tailscale uninstalled and cleaned up.")


def install_tailscale() -> None:
    """Install tailscale using the official install script."""
    ensure_root()
    print_section("Installing Tailscale")

    print_step("Running tailscale install script")
    install_cmd = f"curl -fsSL {TAILSCALE_INSTALL_URL} | sh"

    with Spinner("Installing Tailscale") as spinner:
        try:
            result = run_command(install_cmd, shell=True)
            if result.returncode == 0:
                print_success("Tailscale installed successfully.")
            else:
                print_warning("Tailscale installation may have issues.")
        except Exception as e:
            print_error(f"Installation failed: {e}")
            spinner.stop(success=False)
            raise


def start_tailscale_service() -> None:
    """Enable and start the tailscaled service."""
    ensure_root()
    print_section("Enabling and Starting Tailscale Service")

    steps = [
        ("Enabling tailscaled service", ["systemctl", "enable", "tailscaled"]),
        ("Starting tailscaled service", ["systemctl", "start", "tailscaled"]),
    ]

    with ProgressManager() as progress:
        task = progress.add_task("Configuring Tailscale Service", total=len(steps))
        progress.start()

        for desc, cmd in steps:
            print_step(desc)
            try:
                run_command(cmd)
                progress.update(
                    task, advance=1, status=f"[{NordColors.NORD9}]Completed"
                )
            except Exception as e:
                print_error(f"Error during {desc}: {e}")
                progress.update(task, advance=1, status=f"[{NordColors.NORD11}]Failed")
                if not get_user_confirmation("Continue with remaining steps?"):
                    print_warning("Service configuration aborted.")
                    return

    print_success("Tailscale service enabled and started.")


def tailscale_up() -> None:
    """Run 'tailscale up' to bring up the daemon."""
    ensure_root()
    print_section("Running 'tailscale up'")

    with Spinner("Executing tailscale up") as spinner:
        try:
            result = run_command(["tailscale", "up"])
            spinner.stop(success=True)
            print_success("Tailscale is up!")
            console.print(f"\n[bold]tailscale up output:[/bold]\n{result.stdout}")
        except Exception as e:
            spinner.stop(success=False)
            print_error(f"Failed to bring Tailscale up: {e}")
            raise


def check_tailscale_status() -> None:
    """Check and display the current Tailscale status."""
    print_section("Tailscale Status")

    with Spinner("Checking Tailscale status") as spinner:
        try:
            result = run_command(["tailscale", "status"])
            spinner.stop(success=True)

            if result.stdout.strip():
                console.print(
                    Panel(
                        result.stdout,
                        title="Tailscale Status",
                        border_style=f"bold {NordColors.NORD8}",
                    )
                )
            else:
                print_warning(
                    "No status information available. Tailscale may not be running."
                )
        except Exception as e:
            spinner.stop(success=False)
            print_error(f"Failed to check Tailscale status: {e}")
            print_info("Tailscale may not be installed or running.")


def reset_tailscale() -> None:
    """Perform a complete reset of Tailscale: uninstall, install, start, up."""
    ensure_root()
    print_section("Complete Tailscale Reset")

    if not get_user_confirmation("This will completely reset Tailscale. Continue?"):
        print_info("Reset cancelled.")
        return

    try:
        # Step 1: Uninstall
        uninstall_tailscale()
        time.sleep(CHECK_INTERVAL)

        # Step 2: Install
        install_tailscale()
        time.sleep(CHECK_INTERVAL)

        # Step 3: Start service
        start_tailscale_service()
        time.sleep(CHECK_INTERVAL)

        # Step 4: Bring up
        tailscale_up()

        print_success("Tailscale has been completely reset!")
    except Exception as e:
        print_error(f"Reset process failed: {e}")
        print_warning("Tailscale may be in an inconsistent state.")


# ==============================
# Menu System
# ==============================
def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(
            f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))}"
        )
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Running as root: {'Yes' if check_root() else 'No'}")

        # Main menu options
        menu_options = [
            ("1", "Complete Tailscale Reset (uninstall, reinstall, restart)"),
            ("2", "Uninstall Tailscale"),
            ("3", "Install Tailscale"),
            ("4", "Start Tailscale Service"),
            ("5", "Run 'tailscale up'"),
            ("6", "Check Tailscale Status"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-6):")

        if choice == "1":
            reset_tailscale()
            pause()
        elif choice == "2":
            uninstall_tailscale()
            pause()
        elif choice == "3":
            install_tailscale()
            pause()
        elif choice == "4":
            start_tailscale_service()
            pause()
        elif choice == "5":
            tailscale_up()
            pause()
        elif choice == "6":
            check_tailscale_status()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Tailscale Reset Utility.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Initial setup
        setup_logging()

        # Launch the main menu
        main_menu()

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
