#!/usr/bin/env python3
"""
VS Code Wayland Automated Setup
--------------------------------------------------

A beautiful, automatic utility for installing and configuring
Visual Studio Code with Wayland support on Linux systems. This script downloads
VS Code, installs it, creates desktop entries with Wayland-specific options, and
verifies the installation - all without user interaction.

Features:
  - Automatic download of VS Code .deb package
  - System dependency resolution and installation
  - Wayland-specific desktop entries configuration
  - Installation verification
  - Beautiful Nord-themed output with progress indicators

Requires:
  - Root privileges (must be run with sudo)
  - Linux system with apt package manager
  - Internet connection for downloading VS Code

Usage:
  sudo python3 vscode_wayland_setup.py

Version: 2.0.0
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
APP_SUBTITLE = "Automated Installation Utility"
VERSION = "2.0.0"
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
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

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
    logging.info(f"{prefix} {text}")


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
    logging.error(text)


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
    logging.info(f"{title if title else 'Panel'}: {message}")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


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
    logging.info(f"SECTION: {title}")


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

        # Ensure log file permissions are secure
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
            status=f"{NordColors.FROST_3}starting",
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
        print_info("VS Code package already downloaded. Using existing file.")
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
            with ProgressManager() as progress:
                task_id = progress.add_task("Installing package", total=1.0)

                run_command(
                    ["dpkg", "-i", config.vscode_deb_path],
                    capture_output=True,
                    verbose=config.verbose,
                )

                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
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
                with ProgressManager() as progress:
                    task_id = progress.add_task("Fixing dependencies", total=1.0)

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

                    progress.update(
                        task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
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

    with ProgressManager() as progress:
        task_id = progress.add_task("Creating desktop entries", total=2.0)

        # System-wide desktop entry
        print_step("Creating system-wide desktop entry...")
        try:
            with open(config.system_desktop_path, "w") as f:
                f.write(desktop_content)
            print_success(
                f"System desktop entry created at {config.system_desktop_path}"
            )
            progress.update(task_id, advance=1.0)
        except Exception as e:
            print_error(f"Failed to create system desktop entry: {e}")
            logging.exception("System desktop entry creation error")
            success = False
            progress.update(task_id, advance=1.0, status=f"[{NordColors.RED}]Failed")

        # User desktop entry
        print_step("Creating user desktop entry...")
        try:
            os.makedirs(os.path.dirname(config.user_desktop_path), exist_ok=True)
            with open(config.user_desktop_path, "w") as f:
                f.write(desktop_content)
            print_success(f"User desktop entry created at {config.user_desktop_path}")
            progress.update(
                task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
            )
        except Exception as e:
            print_error(f"Failed to create user desktop entry: {e}")
            logging.exception("User desktop entry creation error")
            success = False
            progress.update(task_id, advance=1.0, status=f"[{NordColors.RED}]Failed")

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

    with ProgressManager() as progress:
        task_id = progress.add_task("Verifying components", total=len(checks))
        all_ok = True

        for i, (path, desc) in enumerate(checks):
            if os.path.exists(path):
                print_success(f"{desc} found at {path}")
            else:
                print_error(f"{desc} missing at {path}")
                all_ok = False
            progress.update(task_id, advance=1.0)

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

    with ProgressManager() as progress:
        task_id = progress.add_task("Checking system compatibility", total=3.0)
        compatible = True

        # Check OS type
        if info.platform != "Linux":
            print_error(f"This script requires Linux. Detected: {info.platform}")
            compatible = False
        else:
            print_success(f"OS check passed: {info.platform}")
        progress.update(task_id, advance=1.0)

        # Check privileges
        if not info.is_root:
            print_error("This script must be run with root privileges (sudo).")
            print_info("Run again with: sudo python3 vscode_wayland_setup.py")
            compatible = False
        else:
            print_success("Root privileges detected.")
        progress.update(task_id, advance=1.0)

        # Check dependencies
        if info.missing_deps:
            print_error(f"Missing required commands: {', '.join(info.missing_deps)}")
            compatible = False
        else:
            print_success("All required system dependencies found.")
        progress.update(task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete")

    # Check session type - just a warning, doesn't prevent installation
    if info.session_type.lower() != "wayland":
        print_warning(f"Not running a Wayland session (detected: {info.session_type}).")
        print_warning(
            "VS Code will be configured for Wayland, but you must log in to a Wayland session to use it."
        )
    else:
        print_success("Wayland session detected.")

    if compatible:
        print_success("System is compatible with VS Code Wayland setup.")
    else:
        print_error("System compatibility check failed.")

    return compatible


def run_automated_setup(config: AppConfig) -> bool:
    """
    Run the complete VS Code Wayland setup process automatically.

    Args:
        config: Application configuration

    Returns:
        True if the entire setup is successful
    """
    start_time = time.time()
    system_info = get_system_info()

    # Show system info
    print_info(f"System: {system_info.platform} {platform.release()}")
    print_info(f"Architecture: {system_info.architecture}")
    print_info(f"Desktop Environment: {system_info.desktop_env}")
    print_info(f"Session Type: {system_info.session_type}")
    print_info(f"Username: {system_info.username}")
    print_info(f"Hostname: {HOSTNAME}")

    # Check compatibility
    if not check_system_compatibility(system_info):
        print_error("Setup cannot continue. Resolve issues and try again.")
        return False

    # Run the installation steps
    steps_completed = 0
    steps_total = 4

    # Display a summary table
    table = Table(box=None)
    table.add_column("Step", style=f"{NordColors.FROST_3}")
    table.add_column("Action", style=f"{NordColors.SNOW_STORM_1}")

    table.add_row("1", "Download VS Code package")
    table.add_row("2", "Install VS Code")
    table.add_row("3", "Configure Wayland desktop entries")
    table.add_row("4", "Verify installation")

    console.print(
        Panel(
            table,
            title="Setup Process",
            border_style=f"{NordColors.FROST_2}",
            padding=(1, 1),
        )
    )

    # Step 1: Download
    step_success = download_vscode(config)
    if step_success:
        steps_completed += 1
    else:
        print_error("VS Code download failed. Setup cannot continue.")
        return False

    # Step 2: Install
    step_success = install_vscode(config)
    if step_success:
        steps_completed += 1
    else:
        print_error("VS Code installation failed. Setup cannot continue.")
        return False

    # Step 3: Configure desktop entries
    step_success = create_wayland_desktop_file(config)
    if step_success:
        steps_completed += 1
    else:
        print_warning("Desktop entry creation had some issues, but continuing...")

    # Step 4: Verify
    step_success = verify_installation(config)
    if step_success:
        steps_completed += 1
    else:
        print_warning("Installation verification had some issues.")

    # Report overall results
    elapsed_time = time.time() - start_time

    print_section("Setup Results")

    if steps_completed == steps_total:
        print_success(f"Setup completed successfully in {format_time(elapsed_time)}!")
        print_info(
            "You can now launch VS Code with Wayland support from your application menu."
        )

        result_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]VS Code with Wayland support successfully installed.[/]\n\n"
                f"[{NordColors.SNOW_STORM_1}]• Binary location: /usr/share/code/code[/]\n"
                f"[{NordColors.SNOW_STORM_1}]• System desktop entry: {config.system_desktop_path}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]• User desktop entry: {config.user_desktop_path}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]• Log file: {config.log_file}[/]\n\n"
                f"[{NordColors.FROST_3}]To test the installation, log into a Wayland session and launch VS Code.[/]"
            ),
            title="Installation Complete",
            border_style=Style(color=NordColors.GREEN),
            padding=(1, 2),
        )
        console.print(result_panel)

        return True
    else:
        print_warning(
            f"Setup completed with issues ({steps_completed}/{steps_total} steps successful) in {format_time(elapsed_time)}."
        )
        print_info(f"Check the log file at {config.log_file} for details.")

        result_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.YELLOW}]VS Code installation completed with some issues.[/]\n\n"
                f"[{NordColors.SNOW_STORM_1}]• Successful steps: {steps_completed}/{steps_total}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]• Total time: {format_time(elapsed_time)}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]• Log file: {config.log_file}[/]\n\n"
                f"[{NordColors.FROST_3}]You may need to manually verify or fix some components.[/]"
            ),
            title="Installation Completed With Issues",
            border_style=Style(color=NordColors.YELLOW),
            padding=(1, 2),
        )
        console.print(result_panel)

        return False


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        # Clear screen and show header
        clear_screen()
        console.print(create_header())

        # Display current time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
        )
        console.print()

        # Check for root privileges first
        if not check_privileges():
            print_error("This script must be run with root privileges (sudo).")
            print_info("Run again with: sudo python3 vscode_wayland_setup.py")
            sys.exit(1)

        # Initialize configuration
        config = AppConfig(verbose=True)

        # Setup logging
        setup_logging(config)

        # Run the automated setup
        success = run_automated_setup(config)

        # Exit with appropriate status code
        sys.exit(0 if success else 1)

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
