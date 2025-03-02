#!/usr/bin/env python3
"""
VS Code Wayland Setup Utility
-----------------------------

A beautiful, interactive terminal-based utility for installing and configuring
Visual Studio Code with Wayland support on Linux systems. This script downloads
VS Code, installs it, creates desktop entries with Wayland-specific options, and
verifies the installation. All functionality is menu-driven with a Nord‑themed interface.

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
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TaskID

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "VS Code Wayland Setup"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/vscode_wayland_setup.log"

# URL for the VS Code .deb package (update as needed)
VSCODE_URL = ("https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
              "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb")
VSCODE_DEB_PATH = "/tmp/code.deb"

# Desktop entry paths
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# Required system dependencies
REQUIRED_COMMANDS = ["curl", "dpkg", "apt", "apt-get"]

# ----------------------------------------------------------------
# Nord‑Themed UI Setup & Helper Functions
# ----------------------------------------------------------------
console = Console()

# Nord Color Palette
class NordColors:
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"
    NORD11 = "#BF616A"  # Errors
    NORD12 = "#D08770"  # Warnings
    NORD13 = "#EBCB8B"  # Caution
    NORD14 = "#A3BE8C"  # Success
    NORD15 = "#B48EAD"  # Special

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

def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")

def get_user_input(prompt: str, default: str = "") -> str:
    """Get user input with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)

def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Prompt the user with a list of choices."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True)

def get_user_confirmation(prompt: str) -> bool:
    """Ask the user for confirmation."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")

def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")
    for key, description in options:
        table.add_row(key, description)
    return table

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

# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(verbose: bool = False) -> None:
    """Configure logging to file and console."""
    log_level = logging.DEBUG if verbose else logging.INFO
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=LOG_FILE,
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)

        if os.path.exists(LOG_FILE):
            os.chmod(LOG_FILE, 0o600)

        print_step(f"Logging configured to: {LOG_FILE}")
    except Exception as e:
        print_error(f"Could not set up logging to {LOG_FILE}: {e}")
        print_step("Continuing with console logging only...")

# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
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
    sig_name = (signal.Signals(signum).name if hasattr(signal, "Signals") 
                else f"signal {signum}")
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ----------------------------------------------------------------
# System Helper Functions
# ----------------------------------------------------------------
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
        if e.stderr:
            print_error(f"Error details: {e.stderr.strip()}")
        raise

def check_privileges() -> bool:
    """Check if the script is running with root privileges."""
    return os.geteuid() == 0

def ensure_directory(path: str) -> bool:
    """Ensure that a directory exists."""
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False

def check_dependency(cmd: str) -> bool:
    """Check if a command is available on the system."""
    return shutil.which(cmd) is not None

# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking system."""
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

    def add_task(self, description: str, total: float, color: str = NordColors.NORD8) -> TaskID:
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self):
        self.progress.start()

    def stop(self):
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
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] [[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self) -> None:
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            console.print("\r" + " " * TERM_WIDTH, end="\r")
            if success:
                console.print(f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] [{NordColors.NORD14}]completed[/] in {time_str}")
            else:
                console.print(f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] [{NordColors.NORD11}]failed[/] after {time_str}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)

# ----------------------------------------------------------------
# VS Code Wayland Installation Functions
# ----------------------------------------------------------------
def download_vscode() -> bool:
    """
    Download the VS Code .deb package using urllib.
    Returns True if the download succeeds.
    """
    print_section("Downloading Visual Studio Code")
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

    try:
        print_info(f"Download URL: {VSCODE_URL}")
        with urllib.request.urlopen(VSCODE_URL) as response:
            total_size = int(response.headers.get("Content-Length", 0))
        if total_size > 0:
            print_info(f"File size: {format_size(total_size)}")
            with ProgressManager() as progress:
                task_id = progress.add_task("Downloading VS Code", total=total_size)
                progress.start()
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
                            progress.update(task_id, advance=len(chunk),
                                            status=f"[{NordColors.NORD9}]{format_size(downloaded)}/{format_size(total_size)}")
        else:
            with Spinner("Downloading VS Code (unknown size)") as spinner:
                urllib.request.urlretrieve(VSCODE_URL, VSCODE_DEB_PATH)
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
    Returns True if installation succeeds.
    """
    print_section("Installing Visual Studio Code")
    if not os.path.exists(VSCODE_DEB_PATH):
        print_error("VS Code package not found. Please download it first.")
        return False
    print_info("Installing VS Code .deb package...")
    try:
        with Spinner("Running dpkg installation") as spinner:
            try:
                run_command(["dpkg", "-i", VSCODE_DEB_PATH], capture_output=True)
                spinner.stop(success=True)
                print_success("VS Code installed successfully.")
                return True
            except subprocess.CalledProcessError:
                spinner.stop(success=False)
                print_warning("Initial installation failed, attempting to fix dependencies...")
                with Spinner("Fixing dependencies with apt") as dep_spinner:
                    try:
                        try:
                            run_command(["apt", "--fix-broken", "install", "-y"], capture_output=True)
                        except:
                            run_command(["apt-get", "--fix-broken", "install", "-y"], capture_output=True)
                        dep_spinner.stop(success=True)
                        print_success("Dependencies fixed. Installation complete.")
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
    Create desktop entries with Wayland support.
    Returns True if both system and user desktop entries are created successfully.
    """
    print_section("Configuring Desktop Entry")
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
    print_step("Creating system-wide desktop entry...")
    try:
        with open(SYSTEM_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)
        print_success(f"System desktop entry created at {SYSTEM_DESKTOP_PATH}")
    except Exception as e:
        print_error(f"Failed to create system desktop entry: {e}")
        success = False

    print_step("Creating user desktop entry...")
    try:
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
    Verify that VS Code and desktop entries are installed.
    Returns True if all expected components are found.
    """
    print_section("Verifying Installation")
    checks = [
        ("/usr/share/code/code", "VS Code binary"),
        (SYSTEM_DESKTOP_PATH, "System desktop entry"),
        (USER_DESKTOP_PATH, "User desktop entry"),
    ]
    table = Table(title="Installation Verification", box=None)
    table.add_column("Component", style=f"{NordColors.NORD9}")
    table.add_column("Path", style=f"{NordColors.NORD4}")
    table.add_column("Status", style=f"{NordColors.NORD14}")
    all_ok = True
    for path, desc in checks:
        if os.path.exists(path):
            table.add_row(desc, path, f"[{NordColors.NORD14}]✓ Found[/]")
        else:
            table.add_row(desc, path, f"[{NordColors.NORD11}]✗ Missing[/]")
            all_ok = False
    console.print(table)
    if all_ok:
        print_success("VS Code with Wayland support has been successfully installed!")
    else:
        print_warning("Some components are missing. Installation may be incomplete.")
    return all_ok

def show_setup_summary() -> None:
    """Display a summary of the VS Code Wayland setup."""
    print_section("VS Code Wayland Setup Summary")
    table = Table(box=None)
    table.add_column("Component", style=f"{NordColors.NORD9}")
    table.add_column("Details", style=f"{NordColors.NORD4}")
    table.add_row("Application", "Visual Studio Code")
    table.add_row("Package URL", VSCODE_URL)
    table.add_row("Temporary File", VSCODE_DEB_PATH)
    table.add_row("System Desktop Entry", SYSTEM_DESKTOP_PATH)
    table.add_row("User Desktop Entry", USER_DESKTOP_PATH)
    table.add_row("Wayland Support", "Enabled (--ozone-platform=wayland)")
    console.print(table)

def check_system_compatibility() -> bool:
    """
    Check if the system is compatible with VS Code Wayland setup.
    Returns True if compatible.
    """
    print_section("System Compatibility Check")
    if platform.system() != "Linux":
        print_error(f"This script requires Linux. Detected: {platform.system()}")
        return False
    if not check_privileges():
        print_error("This script must be run with root privileges (sudo).")
        return False
    missing_cmds = [cmd for cmd in REQUIRED_COMMANDS if not check_dependency(cmd)]
    if missing_cmds:
        print_error(f"Missing required commands: {', '.join(missing_cmds)}")
        return False
    desktop_env = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    if desktop_env.lower() != "wayland":
        print_warning(f"Not running a Wayland session (detected: {desktop_env}).")
        print_warning("VS Code will be configured for Wayland, but log in to a Wayland session to use it.")
        if not get_user_confirmation("Continue anyway?"):
            return False
    else:
        print_success("Wayland session detected.")
    print_success("System is compatible with VS Code Wayland setup.")
    return True

# ----------------------------------------------------------------
# Menu System Functions
# ----------------------------------------------------------------
def run_complete_setup() -> bool:
    """
    Run the complete VS Code Wayland setup process.
    Returns True if the entire setup is successful.
    """
    print_header("VS Code Wayland Setup")
    start_time = time.time()
    if not check_system_compatibility():
        print_error("Setup cannot continue. Resolve issues and try again.")
        return False
    show_setup_summary()
    if not get_user_confirmation("Proceed with installation?"):
        print_info("Setup cancelled by user.")
        return False
    success = (download_vscode() and install_vscode() and create_wayland_desktop_file() and verify_installation())
    elapsed_time = time.time() - start_time
    if success:
        print_success(f"Setup completed successfully in {format_time(elapsed_time)}!")
        print_info("You can now launch VS Code with Wayland support from your application menu.")
    else:
        print_error(f"Setup encountered errors after {format_time(elapsed_time)}.")
        print_info("Check the log file for details and try the individual steps.")
    return success

def individual_setup_menu() -> None:
    """Display the menu for individual setup steps."""
    while True:
        clear_screen()
        print_header("Individual Setup Steps")
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Download VS Code Package"),
            ("3", "Install VS Code"),
            ("4", "Create Wayland Desktop Entries"),
            ("5", "Verify Installation"),
            ("0", "Return to Main Menu"),
        ]
        console.print(create_menu_table("Individual Setup Steps", menu_options))
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
    table = Table(title="System Information", box=None)
    table.add_column("Property", style=f"{NordColors.NORD9}")
    table.add_column("Value", style=f"{NordColors.NORD4}")
    table.add_row("Hostname", HOSTNAME)
    table.add_row("Platform", platform.system())
    table.add_row("Platform Version", platform.version())
    table.add_row("Architecture", platform.machine())
    table.add_row("Python Version", platform.python_version())
    table.add_row("Python Implementation", platform.python_implementation())
    de = os.environ.get("XDG_CURRENT_DESKTOP", "Unknown")
    session_type = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    table.add_row("Desktop Environment", de)
    table.add_row("Session Type", session_type)
    table.add_row("Username", os.environ.get("USER", "Unknown"))
    table.add_row("Home Directory", os.path.expanduser("~"))
    table.add_row("Current Directory", os.getcwd())
    table.add_row("Current Time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Timezone", time.tzname[0])
    console.print(table)
    print_section("Wayland Compatibility")
    if session_type.lower() == "wayland":
        print_success("Running a Wayland session.")
    else:
        print_warning(f"Not running Wayland (detected: {session_type}).")
        print_info("VS Code will be configured for Wayland, but log in to a Wayland session to use it.")
    print_section("VS Code Installation Status")
    vscode_installed = os.path.exists("/usr/share/code/code")
    if vscode_installed:
        print_success("VS Code is installed.")
        system_entry = os.path.exists(SYSTEM_DESKTOP_PATH)
        user_entry = os.path.exists(USER_DESKTOP_PATH)
        print_success("System desktop entry exists." if system_entry else "System desktop entry missing.")
        print_success("User desktop entry exists." if user_entry else "User desktop entry missing.")
        wayland_configured = False
        if system_entry:
            try:
                with open(SYSTEM_DESKTOP_PATH, "r") as f:
                    if "--ozone-platform=wayland" in f.read():
                        wayland_configured = True
            except:
                pass
        if wayland_configured:
            print_success("VS Code is configured for Wayland.")
        else:
            print_warning("VS Code is not configured for Wayland.")
    else:
        print_warning("VS Code is not installed.")

def help_menu() -> None:
    """Display help and troubleshooting information."""
    print_section("Help & Information")
    console.print(
        Panel(
            "This utility installs and configures Visual Studio Code with Wayland support "
            "on Linux. It downloads the VS Code .deb package, installs it (fixing dependencies if needed), "
            "creates desktop entries with Wayland flags, and verifies the installation.\n\n"
            "Wayland offers improved security and performance over X11. To benefit from Wayland support, "
            "you must log in to a Wayland session.\n\n"
            "Log files are stored at: " + LOG_FILE,
            title="About VS Code Wayland Setup",
            border_style=f"{NordColors.NORD8}",
        )
    )
    steps_table = Table(box=None)
    steps_table.add_column("Step", style=f"{NordColors.NORD9}")
    steps_table.add_column("Description", style=f"{NordColors.NORD4}")
    steps_table.add_row("1. Check Compatibility", "Verifies system requirements.")
    steps_table.add_row("2. Download", f"Downloads VS Code from {VSCODE_URL}")
    steps_table.add_row("3. Install", "Installs VS Code and fixes dependencies.")
    steps_table.add_row("4. Configure", "Creates desktop entries with Wayland flags.")
    steps_table.add_row("5. Verify", "Checks that all components are installed.")
    console.print(Panel(steps_table, title="Setup Process", border_style=f"{NordColors.NORD8}"))
    console.print(
        Panel(
            "• If the download fails, check your internet connection.\n"
            "• If installation fails with dependency errors, try running 'sudo apt --fix-broken install'.\n"
            "• Ensure you are logged into a Wayland session for full functionality.\n"
            "• Log files are at " + LOG_FILE,
            title="Troubleshooting",
            border_style=f"{NordColors.NORD8}",
        )
    )

def main_menu() -> None:
    """Display the main menu and handle user selections."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"User: {os.environ.get('USER', 'Unknown')}")
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        menu_options = [
            ("1", "Run Complete Setup"),
            ("2", "Individual Setup Steps"),
            ("3", "System Information"),
            ("4", "Help & Information"),
            ("0", "Exit"),
        ]
        console.print(create_menu_table("Main Menu", menu_options))
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

# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        if not check_privileges():
            print_error("This script must be run with root privileges (sudo).")
            print_info("Run again with: sudo python3 vscode_wayland_setup.py")
            sys.exit(1)
        setup_logging(verbose=True)
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