#!/usr/bin/env python3
"""
VS Code Wayland Setup Utility
--------------------------------------------------

A beautiful, interactive terminal-based utility for installing and configuring
Visual Studio Code with Wayland support on Linux systems. This script downloads
VS Code, installs it, creates desktop entries with Wayland-specific options, and
verifies the installation. All functionality is menu-driven with a Nord-themed interface.

Usage:
  Run the script with sudo to access the main menu:
  - Option 1: Complete Setup - Runs all steps in sequence
  - Option 2: Individual Setup Steps - Run specific steps as needed
  - Option 3: System Information - View detailed system compatibility info
  - Option 4: Help & Information - View troubleshooting tips
  - Option 0: Exit the application

Version: 1.1.0
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
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
    from rich.text import Text
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "VS Code Wayland Setup"
APP_SUBTITLE = "Interactive Installation Utility"
VERSION = "1.1.0"
HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/vscode_wayland_setup.log"
OPERATION_TIMEOUT = 30  # seconds

# URL for the VS Code .deb package (update as needed)
VSCODE_URL = (
    "https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
    "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
)
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
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
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
    RED = "#BF616A"  # Red - for errors
    ORANGE = "#D08770"  # Orange - for warnings
    YELLOW = "#EBCB8B"  # Yellow - for cautions
    GREEN = "#A3BE8C"  # Green - for success
    PURPLE = "#B48EAD"  # Purple - for special features


# Create a Rich Console
console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class AppConfig:
    """
    Represents the configuration settings for the application.

    Attributes:
        verbose: Whether to output verbose logging
        log_file: Path to the log file
        vscode_url: URL to download VS Code from
        vscode_deb_path: Where to store the downloaded .deb file
        system_desktop_path: Path to system-wide desktop entry
        user_desktop_path: Path to user desktop entry
    """

    verbose: bool = False
    log_file: str = LOG_FILE
    vscode_url: str = VSCODE_URL
    vscode_deb_path: str = VSCODE_DEB_PATH
    system_desktop_path: str = SYSTEM_DESKTOP_PATH
    user_desktop_path: str = USER_DESKTOP_PATH


@dataclass
class SystemInfo:
    """
    Represents system information for compatibility checking.

    Attributes:
        platform: Operating system platform
        architecture: CPU architecture
        desktop_env: Current desktop environment
        session_type: XDG session type (X11, Wayland)
        username: Current username
        is_root: Whether running with root privileges
        missing_deps: List of missing required dependencies
    """

    platform: str = ""
    architecture: str = ""
    desktop_env: str = ""
    session_type: str = ""
    username: str = ""
    is_root: bool = False
    missing_deps: List[str] = None

    def __post_init__(self):
        if self.missing_deps is None:
            self.missing_deps = []


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
                     _                 _            _               
__      ____ _ _   _| | __ _ _ __   __| |  ___  ___| |_ _   _ _ __  
\ \ /\ / / _` | | | | |/ _` | '_ \ / _` | / __|/ _ \ __| | | | '_ \ 
 \ V  V / (_| | |_| | | (_| | | | | (_| | \__ \  __/ |_| |_| | |_) |
  \_/\_/ \__,_|\__, |_|\__,_|_| |_|\__,_| |___/\___|\__|\__,_| .__/ 
               |___/                                         |_|    
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a gradient effect with Nord colors
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

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 36 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with consistent padding
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
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


def print_step(text: str) -> None:
    """Print a step description."""
    print_message(text, NordColors.FROST_2, "•")


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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.PURPLE}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get user input with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.PURPLE}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Prompt the user with a list of choices."""
    return Prompt.ask(
        f"[bold {NordColors.PURPLE}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Ask the user for confirmation."""
    return Confirm.ask(f"[bold {NordColors.PURPLE}]{prompt}[/]")


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


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(config: AppConfig) -> None:
    """
    Configure logging to file and console.

    Args:
        config: Application configuration with log settings
    """
    log_level = logging.DEBUG if config.verbose else logging.INFO
    try:
        log_dir = os.path.dirname(config.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=config.log_file,
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)

        if os.path.exists(config.log_file):
            os.chmod(config.log_file, 0o600)

        print_step(f"Logging configured to: {config.log_file}")
    except Exception as e:
        print_error(f"Could not set up logging to {config.log_file}: {e}")
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


def signal_handler(signum: int, frame: Any) -> None:
    """
    Handle termination signals gracefully.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
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


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print additional details

    Returns:
        CompletedProcess instance with command results
    """
    if verbose:
        print_step(f"Executing: {' '.join(cmd)}")
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
        if e.stdout and verbose:
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
# System Helper Functions
# ----------------------------------------------------------------
def check_privileges() -> bool:
    """Check if the script is running with root privileges."""
    return os.geteuid() == 0


def ensure_directory(path: str) -> bool:
    """
    Ensure that a directory exists.

    Args:
        path: Directory path to ensure exists

    Returns:
        True if directory exists or was created, False otherwise
    """
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False


def check_dependency(cmd: str) -> bool:
    """
    Check if a command is available on the system.

    Args:
        cmd: Command to check for

    Returns:
        True if command exists, False otherwise
    """
    return shutil.which(cmd) is not None


def get_system_info() -> SystemInfo:
    """
    Collect detailed system information.

    Returns:
        SystemInfo object with system details
    """
    info = SystemInfo()
    info.platform = platform.system()
    info.architecture = platform.machine()
    info.desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "Unknown")
    info.session_type = os.environ.get("XDG_SESSION_TYPE", "Unknown")
    info.username = os.environ.get("USER", "Unknown")
    info.is_root = check_privileges()
    info.missing_deps = [cmd for cmd in REQUIRED_COMMANDS if not check_dependency(cmd)]
    return info


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking system."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"{NordColors.FROST_9}starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


# ----------------------------------------------------------------
# VS Code Wayland Installation Functions
# ----------------------------------------------------------------
def download_vscode(config: AppConfig) -> bool:
    """
    Download the VS Code .deb package using urllib.

    Args:
        config: Application configuration

    Returns:
        True if the download succeeds
    """
    print_section("Downloading Visual Studio Code")

    if os.path.exists(config.vscode_deb_path):
        if get_user_confirmation("VS Code package already downloaded. Download again?"):
            try:
                os.unlink(config.vscode_deb_path)
            except Exception as e:
                print_error(f"Could not remove existing file: {e}")
                return False
        else:
            print_info("Using existing downloaded package.")
            return True

    try:
        print_info(f"Download URL: {config.vscode_url}")

        # Get file size if possible
        with urllib.request.urlopen(config.vscode_url) as response:
            total_size = int(response.headers.get("Content-Length", 0))

        if total_size > 0:
            print_info(f"File size: {format_size(total_size)}")

            with ProgressManager() as progress:
                task_id = progress.add_task("Downloading VS Code", total=total_size)
                downloaded = 0

                with urllib.request.urlopen(config.vscode_url) as response:
                    with open(config.vscode_deb_path, "wb") as out_file:
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
                                status=f"[{NordColors.FROST_3}]{format_size(downloaded)}/{format_size(total_size)}",
                            )
        else:
            # Fall back to simple download with spinner
            print_info("File size unknown, downloading...")
            urllib.request.urlretrieve(config.vscode_url, config.vscode_deb_path)

        # Verify download
        if (
            os.path.exists(config.vscode_deb_path)
            and os.path.getsize(config.vscode_deb_path) > 0
        ):
            file_size_mb = os.path.getsize(config.vscode_deb_path) / (1024 * 1024)
            print_success(f"Download completed. File size: {file_size_mb:.2f} MB")
            return True
        else:
            print_error("Downloaded file is empty or missing.")
            return False

    except Exception as e:
        print_error(f"Download failed: {e}")
        logging.exception("Download error")
        return False


def install_vscode(config: AppConfig) -> bool:
    """
    Install the downloaded VS Code .deb package.

    Args:
        config: Application configuration

    Returns:
        True if installation succeeds
    """
    print_section("Installing Visual Studio Code")

    if not os.path.exists(config.vscode_deb_path):
        print_error("VS Code package not found. Please download it first.")
        return False

    print_info("Installing VS Code .deb package...")

    try:
        # First attempt with dpkg
        print_step("Running dpkg installation...")
        try:
            run_command(
                ["dpkg", "-i", config.vscode_deb_path],
                capture_output=True,
                verbose=config.verbose,
            )
            print_success("VS Code installed successfully.")
            return True
        except subprocess.CalledProcessError:
            print_warning(
                "Initial installation failed, attempting to fix dependencies..."
            )

            # Second attempt with apt fix-broken
            print_step("Fixing dependencies with apt...")
            try:
                try:
                    run_command(
                        ["apt", "--fix-broken", "install", "-y"],
                        capture_output=True,
                        verbose=config.verbose,
                    )
                except:
                    run_command(
                        ["apt-get", "--fix-broken", "install", "-y"],
                        capture_output=True,
                        verbose=config.verbose,
                    )
                print_success("Dependencies fixed. Installation complete.")
                return True
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to fix dependencies: {e}")
                return False
    except Exception as e:
        print_error(f"Installation error: {e}")
        logging.exception("Installation error")
        return False


def create_wayland_desktop_file(config: AppConfig) -> bool:
    """
    Create desktop entries with Wayland support.

    Args:
        config: Application configuration

    Returns:
        True if desktop entries are created successfully
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

    # System-wide desktop entry
    print_step("Creating system-wide desktop entry...")
    try:
        with open(config.system_desktop_path, "w") as f:
            f.write(desktop_content)
        print_success(f"System desktop entry created at {config.system_desktop_path}")
    except Exception as e:
        print_error(f"Failed to create system desktop entry: {e}")
        logging.exception("System desktop entry creation error")
        success = False

    # User desktop entry
    print_step("Creating user desktop entry...")
    try:
        os.makedirs(os.path.dirname(config.user_desktop_path), exist_ok=True)
        with open(config.user_desktop_path, "w") as f:
            f.write(desktop_content)
        print_success(f"User desktop entry created at {config.user_desktop_path}")
    except Exception as e:
        print_error(f"Failed to create user desktop entry: {e}")
        logging.exception("User desktop entry creation error")
        success = False

    return success


def verify_installation(config: AppConfig) -> bool:
    """
    Verify that VS Code and desktop entries are installed.

    Args:
        config: Application configuration

    Returns:
        True if all expected components are found
    """
    print_section("Verifying Installation")

    checks = [
        ("/usr/share/code/code", "VS Code binary"),
        (config.system_desktop_path, "System desktop entry"),
        (config.user_desktop_path, "User desktop entry"),
    ]

    table = Table(
        title="Installation Verification",
        box=None,
        title_style=f"bold {NordColors.FROST_2}",
    )
    table.add_column("Component", style=f"{NordColors.FROST_3}")
    table.add_column("Path", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", style=f"{NordColors.GREEN}")

    all_ok = True
    for path, desc in checks:
        if os.path.exists(path):
            table.add_row(desc, path, f"[{NordColors.GREEN}]✓ Found[/]")
        else:
            table.add_row(desc, path, f"[{NordColors.RED}]✗ Missing[/]")
            all_ok = False

    console.print(table)

    # Check Wayland flags in desktop entries
    print_step("Checking Wayland configuration...")
    wayland_configured = False
    if os.path.exists(config.system_desktop_path):
        try:
            with open(config.system_desktop_path, "r") as f:
                if "--ozone-platform=wayland" in f.read():
                    wayland_configured = True
                    print_success("Wayland flags are properly configured.")
                else:
                    print_warning("Wayland flags are missing in desktop entry.")
                    all_ok = False
        except Exception as e:
            print_error(f"Could not check desktop entry: {e}")
            all_ok = False

    if all_ok:
        print_success("VS Code with Wayland support has been successfully installed!")
    else:
        print_warning("Some components are missing. Installation may be incomplete.")

    return all_ok


def check_system_compatibility(info: SystemInfo) -> bool:
    """
    Check if the system is compatible with VS Code Wayland setup.

    Args:
        info: System information

    Returns:
        True if compatible
    """
    print_section("System Compatibility Check")

    # Check OS type
    if info.platform != "Linux":
        print_error(f"This script requires Linux. Detected: {info.platform}")
        return False

    # Check privileges
    if not info.is_root:
        print_error("This script must be run with root privileges (sudo).")
        print_info("Run again with: sudo python3 vscode_wayland_setup.py")
        return False

    # Check dependencies
    if info.missing_deps:
        print_error(f"Missing required commands: {', '.join(info.missing_deps)}")
        print_info("Please install the missing dependencies and try again.")
        return False

    # Check session type
    if info.session_type.lower() != "wayland":
        print_warning(f"Not running a Wayland session (detected: {info.session_type}).")
        print_warning(
            "VS Code will be configured for Wayland, but you must log in to a Wayland session to use it."
        )
        if not get_user_confirmation("Continue anyway?"):
            return False
    else:
        print_success("Wayland session detected.")

    print_success("System is compatible with VS Code Wayland setup.")
    return True


def print_section(title: str) -> None:
    """
    Print a formatted section header.

    Args:
        title: Section title to display
    """
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")


def show_setup_summary(config: AppConfig) -> None:
    """
    Display a summary of the VS Code Wayland setup.

    Args:
        config: Application configuration
    """
    print_section("VS Code Wayland Setup Summary")

    table = Table(box=None, title_style=f"bold {NordColors.FROST_2}")
    table.add_column("Component", style=f"{NordColors.FROST_3}")
    table.add_column("Details", style=f"{NordColors.SNOW_STORM_1}")

    table.add_row("Application", "Visual Studio Code")
    table.add_row("Package URL", config.vscode_url)
    table.add_row("Temporary File", config.vscode_deb_path)
    table.add_row("System Desktop Entry", config.system_desktop_path)
    table.add_row("User Desktop Entry", config.user_desktop_path)
    table.add_row("Wayland Support", "Enabled (--ozone-platform=wayland)")

    console.print(table)


# ----------------------------------------------------------------
# Menu System Functions
# ----------------------------------------------------------------
def run_complete_setup(config: AppConfig) -> bool:
    """
    Run the complete VS Code Wayland setup process.

    Args:
        config: Application configuration

    Returns:
        True if the entire setup is successful
    """
    clear_screen()
    console.print(create_header())

    start_time = time.time()
    system_info = get_system_info()

    if not check_system_compatibility(system_info):
        print_error("Setup cannot continue. Resolve issues and try again.")
        return False

    show_setup_summary(config)

    if not get_user_confirmation("Proceed with installation?"):
        print_info("Setup cancelled by user.")
        return False

    # Run the installation steps
    success = (
        download_vscode(config)
        and install_vscode(config)
        and create_wayland_desktop_file(config)
        and verify_installation(config)
    )

    elapsed_time = time.time() - start_time

    if success:
        print_success(f"Setup completed successfully in {format_time(elapsed_time)}!")
        print_info(
            "You can now launch VS Code with Wayland support from your application menu."
        )
    else:
        print_error(f"Setup encountered errors after {format_time(elapsed_time)}.")
        print_info(f"Check the log file at {config.log_file} for details.")

    return success


def individual_setup_menu(config: AppConfig) -> None:
    """
    Display the menu for individual setup steps.

    Args:
        config: Application configuration
    """
    while True:
        clear_screen()
        console.print(create_header())

        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Download VS Code Package"),
            ("3", "Install VS Code"),
            ("4", "Create Wayland Desktop Entries"),
            ("5", "Verify Installation"),
            ("0", "Return to Main Menu"),
        ]

        table = create_menu_table("Individual Setup Steps", menu_options)
        console.print(table)

        choice = get_user_input("Enter your choice (0-5):")

        if choice == "1":
            check_system_compatibility(get_system_info())
            pause()
        elif choice == "2":
            download_vscode(config)
            pause()
        elif choice == "3":
            install_vscode(config)
            pause()
        elif choice == "4":
            create_wayland_desktop_file(config)
            pause()
        elif choice == "5":
            verify_installation(config)
            pause()
        elif choice == "0":
            return
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """
    Create a Rich table for menu options.

    Args:
        title: Title of the menu
        options: List of (key, description) tuples for menu options

    Returns:
        A Rich Table object containing the menu options
    """
    table = Table(
        title=title, box=None, title_style=f"bold {NordColors.FROST_2}", expand=True
    )
    table.add_column(
        "Option", style=f"bold {NordColors.FROST_3}", justify="right", width=6
    )
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for key, description in options:
        table.add_row(key, description)

    return table


def system_info_menu() -> None:
    """Display detailed system information."""
    print_section("System Information")

    # Gather system info
    info = get_system_info()

    # Basic system info table
    sys_table = Table(
        title="System Details", box=None, title_style=f"bold {NordColors.FROST_2}"
    )
    sys_table.add_column("Property", style=f"{NordColors.FROST_3}")
    sys_table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    sys_table.add_row("Hostname", HOSTNAME)
    sys_table.add_row("Platform", platform.system())
    sys_table.add_row("Platform Version", platform.version())
    sys_table.add_row("Architecture", platform.machine())
    sys_table.add_row("Python Version", platform.python_version())
    sys_table.add_row("Python Implementation", platform.python_implementation())
    sys_table.add_row("Desktop Environment", info.desktop_env)
    sys_table.add_row("Session Type", info.session_type)
    sys_table.add_row("Username", info.username)
    sys_table.add_row("Home Directory", os.path.expanduser("~"))
    sys_table.add_row("Current Directory", os.getcwd())
    sys_table.add_row(
        "Current Time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    sys_table.add_row("Timezone", time.tzname[0])

    console.print(sys_table)

    # Wayland compatibility section
    print_section("Wayland Compatibility")
    if info.session_type.lower() == "wayland":
        print_success("Running a Wayland session.")
    else:
        print_warning(f"Not running Wayland (detected: {info.session_type}).")
        print_info(
            "VS Code will be configured for Wayland, but log in to a Wayland session to use it."
        )

    # VS Code installation status
    print_section("VS Code Installation Status")
    vscode_installed = os.path.exists("/usr/share/code/code")
    if vscode_installed:
        print_success("VS Code is installed.")

        system_entry = os.path.exists(SYSTEM_DESKTOP_PATH)
        user_entry = os.path.exists(USER_DESKTOP_PATH)

        print_success(
            "System desktop entry exists."
        ) if system_entry else print_warning("System desktop entry missing.")
        print_success("User desktop entry exists.") if user_entry else print_warning(
            "User desktop entry missing."
        )

        # Check if Wayland is configured
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

    # About panel
    about_text = (
        "This utility installs and configures Visual Studio Code with Wayland support "
        "on Linux systems. It downloads the VS Code .deb package, installs it (fixing dependencies if needed), "
        "creates desktop entries with Wayland flags, and verifies the installation.\n\n"
        "Wayland offers improved security and performance over X11. To benefit from Wayland support, "
        "you must log in to a Wayland session.\n\n"
        f"Log files are stored at: {LOG_FILE}"
    )

    console.print(
        Panel(
            about_text,
            title="About VS Code Wayland Setup",
            border_style=f"{NordColors.FROST_2}",
            padding=(1, 2),
        )
    )

    # Steps table
    steps_table = Table(box=None)
    steps_table.add_column("Step", style=f"{NordColors.FROST_3}")
    steps_table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    steps_table.add_row("1. Check Compatibility", "Verifies system requirements.")
    steps_table.add_row("2. Download", f"Downloads VS Code from {VSCODE_URL}")
    steps_table.add_row("3. Install", "Installs VS Code and fixes dependencies.")
    steps_table.add_row("4. Configure", "Creates desktop entries with Wayland flags.")
    steps_table.add_row("5. Verify", "Checks that all components are installed.")

    console.print(
        Panel(
            steps_table,
            title="Setup Process",
            border_style=f"{NordColors.FROST_2}",
            padding=(1, 2),
        )
    )

    # Troubleshooting panel
    troubleshooting_text = (
        "• If the download fails, check your internet connection.\n"
        "• If installation fails with dependency errors, try running 'sudo apt --fix-broken install'.\n"
        "• Ensure you are logged into a Wayland session for full functionality.\n"
        f"• Log files are at {LOG_FILE}\n"
        "• For persistent issues, try the individual setup steps menu.\n"
    )

    console.print(
        Panel(
            troubleshooting_text,
            title="Troubleshooting",
            border_style=f"{NordColors.FROST_2}",
            padding=(1, 2),
        )
    )


def main_menu(config: AppConfig) -> None:
    """
    Display the main menu and handle user selections.

    Args:
        config: Application configuration
    """
    while True:
        clear_screen()
        console.print(create_header())

        # Display system information
        info = get_system_info()
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]System: {info.platform} {platform.release()}[/] | "
                f"[{NordColors.SNOW_STORM_1}]User: {info.username}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )

        # Display current time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
        )
        console.print()

        # Menu options
        menu_options = [
            ("1", "Run Complete Setup"),
            ("2", "Individual Setup Steps"),
            ("3", "System Information"),
            ("4", "Help & Information"),
            ("0", "Exit"),
        ]

        table = create_menu_table("Main Menu", menu_options)
        console.print(table)
        console.print()

        choice = get_user_input("Enter your choice (0-4):")

        if choice == "1":
            run_complete_setup(config)
            pause()
        elif choice == "2":
            individual_setup_menu(config)
        elif choice == "3":
            system_info_menu()
            pause()
        elif choice == "4":
            help_menu()
            pause()
        elif choice == "0":
            clear_screen()
            console.print(create_header())
            console.print(
                Panel(
                    Text(
                        "Thank you for using the VS Code Wayland Setup Utility!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
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
        # Check for root privileges first
        if not check_privileges():
            print_error("This script must be run with root privileges (sudo).")
            print_info("Run again with: sudo python3 vscode_wayland_setup.py")
            sys.exit(1)

        # Initialize configuration
        config = AppConfig(verbose=True)

        # Setup logging
        setup_logging(config)

        # Start main menu
        main_menu(config)

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unexpected error")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
