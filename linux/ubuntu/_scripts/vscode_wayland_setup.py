#!/usr/bin/env python3
"""
VS Code Wayland Automated Setup
--------------------------------------------------

A fully automatic utility for installing and configuring Visual Studio Code
with Wayland support on Linux systems. This script downloads the VS Code
.deb package, installs it, creates Wayland-specific desktop entries, and verifies
the installation—all without any user interaction.

Features:
  • Fully unattended execution
  • Stylish ASCII banner via Pyfiglet
  • Rich-based terminal output with spinners and progress bars
  • Automatic dependency checks and system compatibility validation
  • Comprehensive error handling and logging

Requires:
  • Root privileges (run with sudo)
  • Linux system with apt package manager
  • Internet connectivity
  • Python packages: rich, pyfiglet

Usage:
  sudo python3 vscode_wayland_setup.py
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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

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
    print("Install them using: pip install rich pyfiglet")
    sys.exit(1)

# Enable rich traceback for better error reporting
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

# VS Code .deb download URL (update if needed)
VSCODE_URL = (
    "https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
    "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
)
VSCODE_DEB_PATH = os.path.join(tempfile.gettempdir(), "code.deb")

# Desktop entry paths
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# Required system commands
REQUIRED_COMMANDS = ["curl", "dpkg", "apt", "apt-get"]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
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


# ----------------------------------------------------------------
# Console Initialization
# ----------------------------------------------------------------
console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class AppConfig:
    verbose: bool = False
    log_file: str = LOG_FILE
    vscode_url: str = VSCODE_URL
    vscode_deb_path: str = VSCODE_DEB_PATH
    system_desktop_path: str = SYSTEM_DESKTOP_PATH
    user_desktop_path: str = USER_DESKTOP_PATH


@dataclass
class SystemInfo:
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
    """Generate a styled ASCII banner using Pyfiglet."""
    fonts = ["slant", "small", "smslant", "digital", "mini"]
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

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = "\n".join(
        f"[bold {colors[i % len(colors)]}]{line}[/]"
        for i, line in enumerate(ascii_lines)
    )
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 36 + "[/]"
    styled_text = f"{tech_border}\n{styled_text}\n{tech_border}"
    header = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        title_align="right",
        subtitle_align="center",
    )
    return header


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message to the console and log it."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    logging.info(f"{prefix} {text}")


def print_step(text: str) -> None:
    print_message(text, NordColors.FROST_2, "•")


def print_info(text: str) -> None:
    print_message(text, NordColors.FROST_3, "ℹ")


def print_success(text: str) -> None:
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    print_message(text, NordColors.RED, "✗")
    logging.error(text)


def print_section(title: str) -> None:
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{title.center(TERM_WIDTH)}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")
    logging.info(f"SECTION: {title}")


def clear_screen() -> None:
    console.clear()


def format_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
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
        if os.path.exists(config.log_file):
            os.chmod(config.log_file, 0o600)
        print_step(f"Logging configured to: {config.log_file}")
    except Exception as e:
        print_error(f"Logging setup failed: {e}")


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_step("Performing cleanup tasks...")
    try:
        if os.path.exists(VSCODE_DEB_PATH):
            os.unlink(VSCODE_DEB_PATH)
            print_step("Removed temporary .deb file")
    except Exception as e:
        print_warning(f"Cleanup error: {e}")


atexit.register(cleanup)


def signal_handler(signum: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


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
    return os.geteuid() == 0


def ensure_directory(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False


def check_dependency(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def get_system_info() -> SystemInfo:
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
# Progress Tracking
# ----------------------------------------------------------------
class ProgressManager:
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
    """Download the VS Code .deb package."""
    print_section("Downloading Visual Studio Code")
    if os.path.exists(config.vscode_deb_path):
        print_info("VS Code package already exists. Using existing file.")
        return True
    try:
        print_info(f"Download URL: {config.vscode_url}")
        with urllib.request.urlopen(config.vscode_url) as response:
            total_size = int(response.headers.get("Content-Length", 0))
        if total_size > 0:
            print_info(f"File size: {format_size(total_size)}")
            with ProgressManager() as progress:
                task_id = progress.add_task("Downloading VS Code", total=total_size)
                downloaded = 0
                with (
                    urllib.request.urlopen(config.vscode_url) as response,
                    open(config.vscode_deb_path, "wb") as out_file,
                ):
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
            print_info("Unknown file size, performing simple download...")
            urllib.request.urlretrieve(config.vscode_url, config.vscode_deb_path)
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
    """Install the downloaded VS Code .deb package."""
    print_section("Installing Visual Studio Code")
    if not os.path.exists(config.vscode_deb_path):
        print_error("VS Code package not found. Aborting installation.")
        return False
    print_info("Installing VS Code .deb package using dpkg...")
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
        print_success("VS Code installed successfully via dpkg.")
        return True
    except subprocess.CalledProcessError:
        print_warning(
            "Initial installation failed, attempting to fix dependencies with apt..."
        )
        try:
            with ProgressManager() as progress:
                task_id = progress.add_task("Fixing dependencies", total=1.0)
                try:
                    run_command(
                        ["apt", "--fix-broken", "install", "-y"],
                        capture_output=True,
                        verbose=config.verbose,
                    )
                except Exception:
                    run_command(
                        ["apt-get", "--fix-broken", "install", "-y"],
                        capture_output=True,
                        verbose=config.verbose,
                    )
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
                )
            print_success("Dependencies fixed. VS Code installation complete.")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to fix dependencies: {e}")
            return False
    except Exception as e:
        print_error(f"Installation error: {e}")
        logging.exception("Installation error")
        return False


def create_wayland_desktop_file(config: AppConfig) -> bool:
    """Create system and user desktop entries with Wayland support."""
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
    """Verify that VS Code and desktop entries are correctly installed."""
    print_section("Verifying Installation")
    checks = [
        ("/usr/share/code/code", "VS Code binary"),
        (config.system_desktop_path, "System desktop entry"),
        (config.user_desktop_path, "User desktop entry"),
    ]
    all_ok = True
    with ProgressManager() as progress:
        task_id = progress.add_task("Verifying components", total=len(checks))
        for path, desc in checks:
            if os.path.exists(path):
                print_success(f"{desc} found at {path}")
            else:
                print_error(f"{desc} missing at {path}")
                all_ok = False
            progress.update(task_id, advance=1.0)
    print_step("Checking Wayland configuration in desktop entry...")
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
    """Ensure the system meets all requirements for the setup."""
    print_section("System Compatibility Check")
    compatible = True
    if info.platform != "Linux":
        print_error(f"This script requires Linux. Detected: {info.platform}")
        compatible = False
    else:
        print_success(f"OS check passed: {info.platform}")
    if not info.is_root:
        print_error("Script must be run with root privileges (sudo).")
        compatible = False
    else:
        print_success("Root privileges detected.")
    if info.missing_deps:
        print_error(f"Missing required commands: {', '.join(info.missing_deps)}")
        compatible = False
    else:
        print_success("All required system dependencies found.")
    if info.session_type.lower() != "wayland":
        print_warning(f"Not running a Wayland session (detected: {info.session_type}).")
        print_warning(
            "VS Code will be configured for Wayland, but log in to a Wayland session to use it."
        )
    else:
        print_success("Wayland session detected.")
    if compatible:
        print_success("System is compatible with VS Code Wayland setup.")
    else:
        print_error("System compatibility check failed.")
    return compatible


def run_automated_setup(config: AppConfig) -> bool:
    """Execute the complete VS Code Wayland setup process."""
    start_time = time.time()
    sys_info = get_system_info()
    print_info(f"System: {sys_info.platform} {platform.release()}")
    print_info(f"Architecture: {sys_info.architecture}")
    print_info(f"Desktop Environment: {sys_info.desktop_env}")
    print_info(f"Session Type: {sys_info.session_type}")
    print_info(f"Username: {sys_info.username}")
    print_info(f"Hostname: {HOSTNAME}")
    if not check_system_compatibility(sys_info):
        print_error("Setup cannot continue due to compatibility issues.")
        return False

    steps_total = 4
    steps_completed = 0

    # Step 1: Download VS Code
    if download_vscode(config):
        steps_completed += 1
    else:
        print_error("VS Code download failed. Aborting setup.")
        return False

    # Step 2: Install VS Code
    if install_vscode(config):
        steps_completed += 1
    else:
        print_error("VS Code installation failed. Aborting setup.")
        return False

    # Step 3: Create desktop entries
    if create_wayland_desktop_file(config):
        steps_completed += 1
    else:
        print_warning("Desktop entry creation encountered issues.")

    # Step 4: Verify installation
    if verify_installation(config):
        steps_completed += 1
    else:
        print_warning("Installation verification encountered issues.")

    elapsed = time.time() - start_time
    print_section("Setup Results")
    if steps_completed == steps_total:
        print_success(f"Setup completed successfully in {format_time(elapsed)}!")
    else:
        print_warning(
            f"Setup completed with issues ({steps_completed}/{steps_total} steps successful) in {format_time(elapsed)}."
        )
    return steps_completed == steps_total


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    try:
        clear_screen()
        console.print(create_header())
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
        )
        console.print()

        if not check_privileges():
            print_error("This script must be run with root privileges (sudo).")
            sys.exit(1)

        config = AppConfig(verbose=True)
        setup_logging(config)
        success = run_automated_setup(config)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_warning("Process interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
