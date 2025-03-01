#!/usr/bin/env python3
"""
VS Code Wayland Setup Utility
-----------------------------

A beautiful, interactive terminal-based utility for installing and configuring
Visual Studio Code with Wayland support on Linux systems. This script handles
downloading VS Code, installing it, creating desktop entries with Wayland-specific
options, and verifying the installation.

All functionality is menu-driven with an attractive Nord-themed interface.

Version: 1.0.0
"""

import atexit
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Import Rich components for beautiful terminal interfaces
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
APP_NAME = "VS Code Wayland Setup"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/vscode_wayland_setup.log"

# URL for the VS Code .deb package (update as needed)
VSCODE_URL = "https://vscode.download.prss.microsoft.com/dbazure/download/stable/e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
VSCODE_DEB_PATH = "/tmp/code.deb"

# Desktop entry paths
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# Required system dependencies
REQUIRED_COMMANDS = ["curl", "dpkg", "apt", "apt-get"]

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


def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


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
def setup_logging(verbose: bool = False) -> None:
    """Configure logging to both a file and the console."""
    log_level = logging.DEBUG if verbose else logging.INFO

    try:
        # Ensure log directory exists
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Configure logging
        logging.basicConfig(
            filename=LOG_FILE,
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter("%(message)s"))

        # Get the root logger and add the console handler
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)

        # Set secure permissions on log file
        try:
            if os.path.exists(LOG_FILE):
                os.chmod(LOG_FILE, 0o600)
        except Exception as e:
            print_warning(f"Could not set secure permissions on log file: {e}")

        print_step(f"Logging configured to: {LOG_FILE}")

    except Exception as e:
        print_error(f"Could not set up logging to {LOG_FILE}: {e}")
        print_step("Continuing with console logging only...")


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    try:
        if os.path.exists(VSCODE_DEB_PATH):
            os.unlink(VSCODE_DEB_PATH)
            print_step("Removed temporary .deb file")
    except Exception as e:
        print_warning(f"Cleanup error: {e}")


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
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = False,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
    if verbose:
        print_step(f"Executing: {' '.join(cmd)}")
    try:
        return subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stderr") and e.stderr:
            print_error(f"Error details: {e.stderr.strip()}")
        raise


def check_privileges() -> bool:
    """Check if script is running with elevated privileges."""
    try:
        if os.name == "nt":  # Windows
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:  # Unix/Linux/Mac
            return os.geteuid() == 0
    except:
        return False


def ensure_directory(path: str) -> bool:
    """Create directory if it doesn't exist."""
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False


def check_dependency(cmd: str) -> bool:
    """Check if a command is available in the system."""
    return shutil.which(cmd) is not None


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


# ==============================
# VS Code Installation Functions
# ==============================
def download_vscode() -> bool:
    """
    Download the VS Code .deb package using urllib.

    Returns:
        bool: True if download succeeds, False otherwise.
    """
    print_section("Downloading Visual Studio Code")

    # Check if file already exists
    if os.path.exists(VSCODE_DEB_PATH):
        if get_user_confirmation("VS Code package already downloaded. Download again?"):
            try:
                os.unlink(VSCODE_DEB_PATH)
            except Exception as e:
                print_error(f"Could not remove existing file: {e}")
                return False
        else:
            print_info("Using existing downloaded package.")
            return True

    # Download with progress tracking
    try:
        print_info(f"Download URL: {VSCODE_URL}")

        # Get file size for progress tracking
        with urllib.request.urlopen(VSCODE_URL) as response:
            total_size = int(response.headers.get("Content-Length", 0))

        if total_size > 0:
            print_info(f"File size: {format_size(total_size)}")

            # Use Rich's progress bar
            with ProgressManager() as progress:
                task_id = progress.add_task("Downloading VS Code", total=total_size)
                progress.start()

                # Download in chunks
                downloaded = 0
                with urllib.request.urlopen(VSCODE_URL) as response:
                    with open(VSCODE_DEB_PATH, "wb") as out_file:
                        chunk_size = 8192
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            out_file.write(chunk)
                            downloaded += len(chunk)
                            progress.update(
                                task_id,
                                advance=len(chunk),
                                status=f"[{NordColors.NORD9}]{format_size(downloaded)}/{format_size(total_size)}",
                            )
        else:
            # Fallback for unknown size
            with Spinner("Downloading VS Code (unknown size)") as spinner:
                urllib.request.urlretrieve(VSCODE_URL, VSCODE_DEB_PATH)

        # Verify download
        if os.path.exists(VSCODE_DEB_PATH) and os.path.getsize(VSCODE_DEB_PATH) > 0:
            file_size_mb = os.path.getsize(VSCODE_DEB_PATH) / (1024 * 1024)
            print_success(f"Download completed. File size: {file_size_mb:.2f} MB")
            return True
        else:
            print_error("Downloaded file is empty or missing.")
            return False

    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def install_vscode() -> bool:
    """
    Install the downloaded VS Code .deb package.

    Returns:
        bool: True if installation (or dependency fix) succeeds, False otherwise.
    """
    print_section("Installing Visual Studio Code")

    if not os.path.exists(VSCODE_DEB_PATH):
        print_error("VS Code package not found. Please download it first.")
        return False

    print_info("Installing VS Code .deb package...")

    try:
        # Initial installation attempt with dpkg
        with Spinner("Running dpkg installation") as spinner:
            try:
                result = run_command(
                    ["dpkg", "-i", VSCODE_DEB_PATH], capture_output=True
                )
                spinner.stop(success=True)
                print_success("VS Code installed successfully.")
                return True
            except subprocess.CalledProcessError:
                spinner.stop(success=False)
                print_warning(
                    "Initial installation failed, attempting to fix dependencies..."
                )

                # Try to fix dependencies with apt
                with Spinner("Fixing dependencies with apt") as dep_spinner:
                    try:
                        # Try first with apt, then with apt-get as fallback
                        try:
                            run_command(
                                ["apt", "--fix-broken", "install", "-y"],
                                capture_output=True,
                            )
                        except:
                            run_command(
                                ["apt-get", "--fix-broken", "install", "-y"],
                                capture_output=True,
                            )

                        dep_spinner.stop(success=True)
                        print_success(
                            "Dependencies fixed. VS Code installation should now be complete."
                        )
                        return True
                    except subprocess.CalledProcessError as e:
                        dep_spinner.stop(success=False)
                        print_error(f"Failed to fix dependencies: {e}")
                        return False
    except Exception as e:
        print_error(f"Installation error: {e}")
        return False


def create_wayland_desktop_file() -> bool:
    """
    Create and install desktop entries with Wayland support.

    Returns:
        bool: True if desktop entries are created successfully, False otherwise.
    """
    print_section("Configuring Desktop Entry")

    # Desktop entry content with Wayland flags
    desktop_content = (
        "[Desktop Entry]\n"
        "Name=Visual Studio Code\n"
        "Comment=Code Editing. Redefined.\n"
        "GenericName=Text Editor\n"
        "Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
        "Icon=vscode\n"
        "Type=Application\n"
        "StartupNotify=false\n"
        "StartupWMClass=Code\n"
        "Categories=TextEditor;Development;IDE;\n"
        "MimeType=application/x-code-workspace;\n"
    )

    success = True

    # System-wide desktop entry
    print_step("Creating system-wide desktop entry...")
    try:
        with open(SYSTEM_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)
        print_success(f"System desktop entry created at {SYSTEM_DESKTOP_PATH}")
    except Exception as e:
        print_error(f"Failed to create system desktop entry: {e}")
        success = False

    # User desktop entry
    print_step("Creating user desktop entry...")
    try:
        # Ensure the user desktop directory exists
        os.makedirs(USER_DESKTOP_DIR, exist_ok=True)

        with open(USER_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)
        print_success(f"User desktop entry created at {USER_DESKTOP_PATH}")
    except Exception as e:
        print_error(f"Failed to create user desktop entry: {e}")
        success = False

    return success


def verify_installation() -> bool:
    """
    Verify that VS Code and the desktop entries have been installed.

    Returns:
        bool: True if all expected files are present, False otherwise.
    """
    print_section("Verifying Installation")

    checks = [
        ("/usr/share/code/code", "VS Code binary"),
        (SYSTEM_DESKTOP_PATH, "System desktop entry"),
        (USER_DESKTOP_PATH, "User desktop entry"),
    ]

    # Create a table for verification results
    table = Table(title="Installation Verification", box=None)
    table.add_column("Component", style=f"{NordColors.NORD9}")
    table.add_column("Path", style=f"{NordColors.NORD4}")
    table.add_column("Status", style=f"{NordColors.NORD14}")

    all_ok = True

    for path, description in checks:
        if os.path.exists(path):
            table.add_row(description, path, f"[{NordColors.NORD14}]✓ Found[/]")
        else:
            table.add_row(description, path, f"[{NordColors.NORD11}]✗ Missing[/]")
            all_ok = False

    console.print(table)

    if all_ok:
        print_success(
            "Visual Studio Code with Wayland support has been successfully installed!"
        )
    else:
        print_warning(
            "Some components appear to be missing. Installation may not be complete."
        )

    return all_ok


def show_setup_summary() -> None:
    """Display a summary of what will be installed."""
    print_section("VS Code Wayland Setup Summary")

    table = Table(box=None)
    table.add_column("Component", style=f"{NordColors.NORD9}")
    table.add_column("Details", style=f"{NordColors.NORD4}")

    table.add_row("Application", "Visual Studio Code")
    table.add_row("Package URL", VSCODE_URL)
    table.add_row("Temporary Files", VSCODE_DEB_PATH)
    table.add_row("Desktop Entry (System)", SYSTEM_DESKTOP_PATH)
    table.add_row("Desktop Entry (User)", USER_DESKTOP_PATH)
    table.add_row("Wayland Support", "Enabled (--ozone-platform=wayland)")

    console.print(table)


def check_system_compatibility() -> bool:
    """
    Check if the system is compatible with this VS Code Wayland setup.

    Returns:
        bool: True if system is compatible, False otherwise.
    """
    print_section("System Compatibility Check")

    # Check operating system
    if platform.system() != "Linux":
        print_error(f"This script requires Linux. Detected: {platform.system()}")
        return False

    # Check root privileges
    if not check_privileges():
        print_error("This script must be run with root privileges (sudo).")
        return False

    # Check for required commands
    missing_commands = []
    for cmd in REQUIRED_COMMANDS:
        if not check_dependency(cmd):
            missing_commands.append(cmd)

    if missing_commands:
        print_error(
            f"The following required commands are missing: {', '.join(missing_commands)}"
        )
        return False

    # Check desktop environment
    desktop_env = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    if desktop_env.lower() != "wayland":
        print_warning(
            f"You're not currently running a Wayland session (detected: {desktop_env})."
        )
        print_warning(
            "While the setup will complete, VS Code may not use Wayland until you log in to a Wayland session."
        )
        if not get_user_confirmation("Continue anyway?"):
            return False
    else:
        print_success("Wayland session detected.")

    print_success("System is compatible with VS Code Wayland setup.")
    return True


# ==============================
# Menu System Functions
# ==============================
def run_complete_setup() -> bool:
    """
    Run the complete VS Code Wayland setup process.

    Returns:
        bool: True if the entire setup was successful, False otherwise.
    """
    print_header("VS Code Wayland Setup")

    # Record start time
    start_time = time.time()

    # Check system compatibility
    if not check_system_compatibility():
        print_error("Setup cannot continue. Please resolve the issues and try again.")
        return False

    # Show what will be installed
    show_setup_summary()

    # Confirm before proceeding
    if not get_user_confirmation("Do you want to proceed with the installation?"):
        print_info("Setup cancelled by user.")
        return False

    # Execute installation steps
    success = (
        download_vscode()
        and install_vscode()
        and create_wayland_desktop_file()
        and verify_installation()
    )

    # Calculate elapsed time
    elapsed_time = time.time() - start_time

    # Display completion message
    if success:
        print_success(
            f"VS Code Wayland setup completed successfully in {format_time(elapsed_time)}!"
        )
        print_info(
            "You can now launch VS Code with Wayland support from your application menu."
        )
    else:
        print_error(
            f"VS Code Wayland setup encountered errors after {format_time(elapsed_time)}."
        )
        print_info("Check the log file for details and try the individual setup steps.")

    return success


def individual_setup_menu() -> None:
    """Display and handle the individual setup steps menu."""
    while True:
        clear_screen()
        print_header("Individual Setup Steps")

        # Menu options
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Download VS Code Package"),
            ("3", "Install VS Code"),
            ("4", "Create Wayland Desktop Entries"),
            ("5", "Verify Installation"),
            ("0", "Return to Main Menu"),
        ]

        console.print(create_menu_table("Individual Setup Steps", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-5):")

        if choice == "1":
            check_system_compatibility()
            pause()
        elif choice == "2":
            download_vscode()
            pause()
        elif choice == "3":
            install_vscode()
            pause()
        elif choice == "4":
            create_wayland_desktop_file()
            pause()
        elif choice == "5":
            verify_installation()
            pause()
        elif choice == "0":
            return
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def system_info_menu() -> None:
    """Display detailed system information."""
    print_section("System Information")

    # Create a table for system info
    table = Table(title="System Information", box=None)
    table.add_column("Property", style=f"{NordColors.NORD9}")
    table.add_column("Value", style=f"{NordColors.NORD4}")

    # System details
    table.add_row("Hostname", HOSTNAME)
    table.add_row("Platform", platform.system())
    table.add_row("Platform Version", platform.version())
    table.add_row("Architecture", platform.machine())

    # Python details
    table.add_row("Python Version", platform.python_version())
    table.add_row("Python Implementation", platform.python_implementation())

    # Desktop environment details
    de = os.environ.get("XDG_CURRENT_DESKTOP", "Unknown")
    session_type = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    table.add_row("Desktop Environment", de)
    table.add_row("Session Type", session_type)

    # User details
    table.add_row(
        "Username", os.environ.get("USER", os.environ.get("USERNAME", "Unknown"))
    )
    table.add_row("Home Directory", os.path.expanduser("~"))
    table.add_row("Current Directory", os.getcwd())

    # Time details
    table.add_row("Current Time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Timezone", time.tzname[0])

    console.print(table)

    # Check for Wayland compatibility
    print_section("Wayland Compatibility")

    if session_type.lower() == "wayland":
        print_success("You are currently running a Wayland session.")
    else:
        print_warning(
            f"You are not running a Wayland session (detected: {session_type})."
        )
        print_info(
            "VS Code will be configured for Wayland, but you'll need to log into a Wayland session to use it."
        )

    # VS Code installation status
    print_section("VS Code Installation Status")

    vscode_installed = os.path.exists("/usr/share/code/code")
    if vscode_installed:
        print_success("VS Code is installed on this system.")

        # Check desktop entries
        system_entry_exists = os.path.exists(SYSTEM_DESKTOP_PATH)
        user_entry_exists = os.path.exists(USER_DESKTOP_PATH)

        if system_entry_exists:
            print_success("System-wide desktop entry exists.")
        else:
            print_warning("System-wide desktop entry is missing.")

        if user_entry_exists:
            print_success("User desktop entry exists.")
        else:
            print_warning("User desktop entry is missing.")

        # Check for Wayland flags in desktop entries
        wayland_configured = False
        if system_entry_exists:
            try:
                with open(SYSTEM_DESKTOP_PATH, "r") as f:
                    content = f.read()
                    if "--ozone-platform=wayland" in content:
                        wayland_configured = True
            except:
                pass

        if wayland_configured:
            print_success("VS Code is configured for Wayland.")
        else:
            print_warning("VS Code is not configured for Wayland.")
    else:
        print_warning("VS Code is not installed on this system.")


def help_menu() -> None:
    """Display help information about this utility."""
    print_section("Help & Information")

    # About this utility
    console.print(
        Panel(
            "This utility helps you install and configure Visual Studio Code with Wayland support "
            "on Linux systems. It handles downloading VS Code, installing it, creating desktop "
            "entries with Wayland-specific options, and verifying the installation.\n\n"
            "Wayland is a modern display server protocol that offers better security, simpler "
            "design, and performance improvements over X11. By configuring VS Code to use "
            "Wayland, you can get better HiDPI support, smoother graphics, and improved "
            "integration with Wayland-based desktop environments like GNOME and KDE.\n\n"
            "This utility requires root privileges because it installs software system-wide "
            "and modifies system files.",
            title="About VS Code Wayland Setup",
            border_style=f"{NordColors.NORD8}",
        )
    )

    # Setup steps explanation
    steps_table = Table(box=None)
    steps_table.add_column("Step", style=f"{NordColors.NORD9}")
    steps_table.add_column("Description", style=f"{NordColors.NORD4}")

    steps_table.add_row(
        "1. Check Compatibility",
        "Verifies your system meets the requirements for VS Code with Wayland.",
    )
    steps_table.add_row(
        "2. Download", f"Downloads the VS Code .deb package from {VSCODE_URL}"
    )
    steps_table.add_row(
        "3. Install", "Installs VS Code using dpkg and handles any dependency issues."
    )
    steps_table.add_row(
        "4. Configure", "Creates desktop entries with the necessary Wayland flags."
    )
    steps_table.add_row(
        "5. Verify", "Checks that all components are installed correctly."
    )

    console.print(
        Panel(steps_table, title="Setup Process", border_style=f"{NordColors.NORD8}")
    )

    # Troubleshooting
    console.print(
        Panel(
            "• If the download fails, check your internet connection or try downloading manually.\n"
            "• If installation fails with dependency errors, try running 'sudo apt --fix-broken install' manually.\n"
            "• If VS Code doesn't use Wayland, make sure you're logged into a Wayland session.\n"
            "• Log files are stored at " + LOG_FILE + "\n"
            "• For more help, visit https://code.visualstudio.com/docs/setup/linux",
            title="Troubleshooting",
            border_style=f"{NordColors.NORD8}",
        )
    )


# ==============================
# Main Menu System
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

        # Main menu options
        menu_options = [
            ("1", "Run Complete Setup"),
            ("2", "Individual Setup Steps"),
            ("3", "System Information"),
            ("4", "Help & Information"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-4):")

        if choice == "1":
            run_complete_setup()
            pause()
        elif choice == "2":
            individual_setup_menu()
        elif choice == "3":
            system_info_menu()
            pause()
        elif choice == "4":
            help_menu()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the VS Code Wayland Setup Utility.")
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
        # Check for root privileges
        if not check_privileges():
            print_error("This script must be run with root privileges (sudo).")
            print_info("Please run again with: sudo python3 vscode_wayland_setup.py")
            sys.exit(1)

        # Initial setup
        setup_logging(verbose=True)

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
