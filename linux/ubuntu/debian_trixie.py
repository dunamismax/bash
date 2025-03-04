#!/usr/bin/env python3
"""
Debian Trixie Server Setup & Hardening Utility (Unattended)
------------------------------------------------------------

This fully automated utility performs preflight checks, system updates,
package installations, user environment setup, security hardening,
service installations, maintenance tasks, system tuning, and final
health checks on a Debian Trixie server.

Features:
  • Fully unattended operation – no user interaction required
  • Comprehensive system setup and hardening
  • Beautiful Nord-themed terminal interface with Pyfiglet banner and Rich output
  • Automatic APT repository configuration and self-healing package management
  • Real-time progress tracking using spinners and progress bars
  • Robust error handling and detailed logging

Run with root privileges.
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import signal
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, Set


def install_missing_packages() -> None:
    """Automatically install required Python packages if missing."""
    required_packages = ["rich", "pyfiglet"]
    missing_packages = []

    print("Checking dependencies...")
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing_packages,
                check=True,
                capture_output=True,
            )
            print("Required packages installed successfully. Restarting script...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install packages: {e}")
            sys.exit(1)
    else:
        print("All dependencies satisfied.")


install_missing_packages()

try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TaskProgressColumn,
        DownloadColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
    from rich.logging import RichHandler
    from rich.live import Live
    from rich.layout import Layout
    from rich.markdown import Markdown
except ImportError as e:
    print(f"Error importing libraries: {e}")
    sys.exit(1)

# Install Rich traceback handler for better error display
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
@dataclass
class AppConfig:
    """Global application configuration."""

    VERSION: str = "1.0.0"
    APP_NAME: str = "Debian Trixie Setup"
    APP_SUBTITLE: str = "Server Setup & Hardening Utility"

    PLATFORM: str = platform.system().lower()
    IS_WINDOWS: bool = PLATFORM == "windows"
    IS_MACOS: bool = PLATFORM == "darwin"
    IS_LINUX: bool = PLATFORM == "linux"

    # Debian-specific settings
    DEBIAN_VERSION: str = "trixie"
    DEBIAN_CODENAME: str = "trixie"  # Debian 13 codename
    DEBIAN_MIRROR: str = "deb.debian.org"
    DEBIAN_CDN: str = f"https://{DEBIAN_MIRROR}/debian"

    LOG_FILE: str = "/var/log/debian_setup.log"
    MAX_LOG_SIZE: int = 10 * 1024 * 1024  # 10MB
    USERNAME: str = "sawyer"
    USER_HOME: str = f"/home/{USERNAME}"
    BACKUP_DIR: str = "/var/backups/debian_setup"
    TEMP_DIR: str = tempfile.gettempdir()

    TERM_WIDTH: int = shutil.get_terminal_size().columns
    TERM_HEIGHT: int = shutil.get_terminal_size().lines
    PROGRESS_WIDTH: int = min(50, TERM_WIDTH - 30)

    ALLOWED_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443", "32400"]
    )

    HOSTNAME: str = socket.gethostname()

    CONFIG_FILES: List[str] = field(
        default_factory=lambda: [
            "/etc/ssh/sshd_config",
            "/etc/ufw/user.rules",
            "/etc/ntp.conf",
            "/etc/sysctl.conf",
            "/etc/environment",
            "/etc/fail2ban/jail.local",
            "/etc/docker/daemon.json",
            "/etc/apt/sources.list",
        ]
    )

    @classmethod
    def update_terminal_size(cls) -> None:
        """Update terminal size information."""
        try:
            cls.TERM_WIDTH = shutil.get_terminal_size().columns
            cls.TERM_HEIGHT = shutil.get_terminal_size().lines
            cls.PROGRESS_WIDTH = min(50, cls.TERM_WIDTH - 30)
        except Exception:
            # Fallback values if we can't get terminal size
            cls.TERM_WIDTH = 80
            cls.TERM_HEIGHT = 24
            cls.PROGRESS_WIDTH = 50


# Debian Trixie default packages list
PACKAGES: List[str] = [
    # Shell and terminal utilities
    "bash",
    "vim",
    "nano",
    "screen",
    "tmux",
    "mc",
    "zsh",
    "htop",
    "btop",
    "tree",
    "ncdu",
    # "neofetch" - removed due to availability issues
    # Build essentials and development tools
    "build-essential",
    "cmake",
    "ninja-build",
    "meson",
    "gettext",
    "git",
    "pkg-config",
    # Core system utilities
    "openssh-server",
    "ufw",
    "curl",
    "wget",
    "rsync",
    "sudo",
    "bash-completion",
    # Python packages
    "python3",
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "python3-rich",
    "python3-pyfiglet",
    # Development libraries
    "libssl-dev",
    "libffi-dev",
    "zlib1g-dev",
    "libreadline-dev",
    "libbz2-dev",
    "tk-dev",
    "xz-utils",
    "libncurses-dev",
    "libgdbm-dev",
    "libnss3-dev",
    "liblzma-dev",
    "libxml2-dev",
    "libxmlsec1-dev",
    # Package management tools
    "ca-certificates",
    # "software-properties-common" - removed due to availability issues
    "apt-transport-https",
    "gnupg",
    "lsb-release",
    # Programming languages and compilers
    "clang",
    "llvm",
    "golang-go",
    "gdb",
    "cargo",
    "ruby",
    "rustc",
    # Network tools
    "netcat-openbsd",
    "lsof",
    "unzip",
    "zip",
    "net-tools",
    "nmap",
    "iftop",
    "iperf3",
    "tcpdump",
    "traceroute",
    "mtr",
    # System monitoring
    "iotop",
    # "glances" - removed due to availability issues
    # Security tools
    "lynis",
    "fail2ban",
    "rkhunter",
    "chkrootkit",
    # Database clients
    "postgresql-client",
    "mariadb-client",
    # Utilities
    "jq",
    "yq",
    "certbot",
    "p7zip-full",
    # Virtualization
    "qemu-system",
    "libvirt-clients",
    "libvirt-daemon-system",
    "virt-manager",
    "qemu-user-static",
    # Better APT frontend
    "nala",
]

# Global status report dictionary
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "apt_sources": {"status": "pending", "message": ""},
    "nala_install": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "packages_install": {"status": "pending", "message": ""},
    "user_env": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "tuning": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}


# ----------------------------------------------------------------
# Nord-Themed Colors and Rich Console
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

    # Polar Night (dark background)
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"

    # Snow Storm (light text)
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"

    # Frost (blue accents)
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"

    # Aurora (other accents)
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"


# Initialize Rich Console with Nord theme
console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
            "header": f"{NordColors.FROST_2} bold",
            "section": f"{NordColors.FROST_3} bold",
            "step": f"{NordColors.FROST_2}",
            "prompt": f"bold {NordColors.PURPLE}",
            "command": f"bold {NordColors.FROST_4}",
            "path": f"italic {NordColors.FROST_1}",
        }
    )
)


# ----------------------------------------------------------------
# Custom Exceptions
# ----------------------------------------------------------------
class SetupError(Exception):
    """Base exception for setup errors."""

    pass


class DependencyError(SetupError):
    """Raised when a required dependency is missing."""

    pass


class ConfigurationError(SetupError):
    """Raised when configuration changes fail."""

    pass


class ExecutionError(SetupError):
    """Raised when command execution fails."""

    pass


class NetworkError(SetupError):
    """Raised when network operations fail."""

    pass


class ValidationError(SetupError):
    """Raised when validation checks fail."""

    pass


# ----------------------------------------------------------------
# Logging and Banner Helpers
# ----------------------------------------------------------------
def setup_logging() -> logging.Logger:
    """Configure logging with Rich handler and file output."""
    # Ensure log directory exists
    os.makedirs(os.path.dirname(AppConfig.LOG_FILE), exist_ok=True)

    # Rotate log if it's too large
    if (
        os.path.exists(AppConfig.LOG_FILE)
        and os.path.getsize(AppConfig.LOG_FILE) > AppConfig.MAX_LOG_SIZE
    ):
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated = f"{AppConfig.LOG_FILE}.{ts}.gz"
        try:
            with (
                open(AppConfig.LOG_FILE, "rb") as fin,
                gzip.open(rotated, "wb") as fout,
            ):
                shutil.copyfileobj(fin, fout)
            open(AppConfig.LOG_FILE, "w").close()
            print(f"Rotated log file to {rotated}")
        except Exception as e:
            print(f"Failed to rotate log file: {e}")

    # Configure logging
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        datefmt=date_format,
        handlers=[
            RichHandler(rich_tracebacks=True, markup=True, console=console),
            logging.FileHandler(AppConfig.LOG_FILE),
        ],
    )

    logger = logging.getLogger("debian_setup")
    logger.info("Logging initialized: %s", AppConfig.LOG_FILE)
    return logger


# Initialize the logger
logger = setup_logging()


def create_header() -> Panel:
    """
    Create an ASCII art header using Pyfiglet with a Nord-themed gradient.

    Returns:
        Panel: A Rich Panel containing the styled header.
    """
    # Try different fonts until one works
    fonts = ["slant", "big", "standard", "digital", "small"]
    ascii_art = ""

    AppConfig.update_terminal_size()
    adjusted_width = min(AppConfig.TERM_WIDTH - 10, 80)

    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception as e:
            logger.debug(f"Font {font} failed: {e}")

    # Fallback if all fonts fail
    if not ascii_art.strip():
        ascii_art = f"=== {AppConfig.APP_NAME} ===\n"

    # Extract non-empty lines
    lines = [line for line in ascii_art.splitlines() if line.strip()]

    # Frost color palette for gradient effect
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    # Apply gradient coloring
    styled_text = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        # Escape any square brackets in the ASCII art to prevent markup issues
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    # Add decorative borders
    border = f"[{NordColors.FROST_3}]{'━' * min(50, adjusted_width - 10)}[/]"
    full_text = f"{border}\n{styled_text}{border}"

    # Create panel with title and subtitle
    return Panel(
        Text.from_markup(full_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message to the console and log it.

    Args:
        text: The message to print
        style: The color to use
        prefix: Symbol to prefix the message with
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    logger.info(text)


def print_step(text: str) -> None:
    """
    Print a step description with arrow indication.

    Args:
        text: The step description to print
    """
    print_message(text, NordColors.FROST_3, "➜")
    logger.info(text)


def print_success(text: str) -> None:
    """
    Print a success message with checkmark.

    Args:
        text: The success message to print
    """
    print_message(text, NordColors.GREEN, "✓")
    logger.info(f"SUCCESS: {text}")


def print_warning(text: str) -> None:
    """
    Print a warning message with warning symbol.

    Args:
        text: The warning message to print
    """
    print_message(text, NordColors.YELLOW, "⚠")
    logger.warning(text)


def print_error(text: str) -> None:
    """
    Print an error message with X symbol.

    Args:
        text: The error message to print
    """
    print_message(text, NordColors.RED, "✗")
    logger.error(text)


def print_section(title: str) -> None:
    """
    Print a section header using Pyfiglet small font.

    Args:
        title: The section title to display
    """
    console.print()
    try:
        section_art = pyfiglet.figlet_format(title, font="small")
        console.print(section_art, style="section")
    except Exception:
        # Fallback if Pyfiglet fails
        console.print(f"[section]== {title.upper()} ==[/section]")

    console.print(f"[section]{'-' * 40}[/section]")
    logger.info(f"--- {title} ---")


def status_report() -> None:
    """Display a table reporting the status of all setup tasks."""
    print_section("Setup Status Report")

    # Status icons
    icons = {"success": "✓", "failed": "✗", "pending": "?", "in_progress": "⋯"}

    # Create table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Debian Trixie Setup Status[/]",
        border_style=NordColors.FROST_3,
    )

    # Define columns
    table.add_column("Task", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=f"bold {NordColors.FROST_3}")
    table.add_column("Message", style=f"{NordColors.SNOW_STORM_1}")

    # Add rows for each task
    for task, data in SETUP_STATUS.items():
        st = data["status"]
        msg = data["message"]
        icon = icons.get(st, "?")

        # Set status style based on status value
        status_style = (
            "success"
            if st == "success"
            else "error"
            if st == "failed"
            else "warning"
            if st == "in_progress"
            else "step"
        )

        # Format task name (e.g., "apt_sources" -> "Apt Sources")
        task_name = task.replace("_", " ").title()

        # Add row to table
        table.add_row(
            task_name,
            f"[{status_style}]{icon} {st.upper()}[/]",
            msg,
        )

    # Display table
    console.print(table)


# ----------------------------------------------------------------
# Command Execution Helpers
# ----------------------------------------------------------------
def run_command(
    cmd: Union[List[str], str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 300,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Execute a system command and return the CompletedProcess.

    Args:
        cmd: Command to execute (list or string)
        env: Environment variables
        check: Whether to raise an exception on non-zero exit
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print the command being executed

    Returns:
        subprocess.CompletedProcess object

    Raises:
        ExecutionError: If command execution fails
    """
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logger.debug(f"Executing: {cmd_str}")

    if verbose:
        print_step(f"Executing: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}")

    try:
        if isinstance(cmd, str):
            result = subprocess.run(
                cmd,
                env=env or os.environ.copy(),
                check=check,
                shell=True,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                cmd,
                env=env or os.environ.copy(),
                check=check,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
            )

        if verbose and result.stdout and len(result.stdout) > 0:
            console.print(f"[dim]{result.stdout.strip()}[/dim]")

        return result

    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {cmd_str}"
        if e.stdout:
            error_msg += f"\nOutput: {e.stdout.strip()}"
        if e.stderr:
            error_msg += f"\nError: {e.stderr.strip()}"

        print_error(error_msg)
        logger.error(error_msg)
        if check:
            raise ExecutionError(error_msg)
        return e

    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds: {cmd_str}"
        print_error(error_msg)
        logger.error(error_msg)
        raise ExecutionError(error_msg)

    except Exception as e:
        error_msg = f"Error executing command: {cmd_str}: {str(e)}"
        print_error(error_msg)
        logger.error(error_msg)
        raise ExecutionError(error_msg)


def run_with_progress(
    desc: str, func: Callable, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """
    Run a function with a Rich spinner indicator.

    Args:
        desc: Description of the task
        func: Function to run
        *args: Arguments to pass to the function
        task_name: Key in SETUP_STATUS to update
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The return value of the function
    """
    # Update status if task_name provided
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{desc} in progress...",
        }

    with console.status(f"[section]{desc}...[/section]") as status:
        start = time.time()

        try:
            # Run function in a separate thread
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(func, *args, **kwargs)

                # Poll until complete
                while not future.done():
                    time.sleep(0.5)
                    status.update(f"[section]{desc}...[/section]")

                # Get result
                result = future.result()

            # Calculate elapsed time
            elapsed = time.time() - start

            # Success message
            print_success(f"{desc} completed in {elapsed:.2f}s")

            # Update status
            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "success",
                    "message": f"{desc} succeeded in {elapsed:.2f}s.",
                }

            return result

        except Exception as e:
            # Calculate elapsed time
            elapsed = time.time() - start

            # Error message
            print_error(f"{desc} failed in {elapsed:.2f}s: {e}")

            # Update status
            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"{desc} failed: {e}",
                }

            # Re-raise exception
            raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    logger.info("Performing cleanup tasks before exit.")

    # Clean up temporary files
    temp_files_removed = 0
    for fname in os.listdir(AppConfig.TEMP_DIR):
        if fname.startswith("debian_setup_"):
            try:
                os.remove(os.path.join(AppConfig.TEMP_DIR, fname))
                temp_files_removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove temp file {fname}: {e}")

    logger.info(f"Removed {temp_files_removed} temporary files")

    # Display final status report
    try:
        status_report()
    except Exception as e:
        logger.error(f"Error generating final status report: {e}")

    # Final log message
    logger.info("Cleanup complete. Exiting.")


def signal_handler(signum: int, frame: Optional[Any]) -> None:
    """
    Gracefully handle termination signals.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    # Get signal name if possible
    sig_name = f"signal {signum}"
    if hasattr(signal, "Signals"):
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            pass

    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    logger.error(f"Interrupted by {sig_name}. Exiting.")

    # Perform cleanup
    cleanup()

    # Exit with signal-specific code
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    try:
        signal.signal(sig, signal_handler)
    except (AttributeError, ValueError):
        pass

# Register cleanup function to run at exit
atexit.register(cleanup)


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
class Utils:
    """Utility methods for common operations."""

    @staticmethod
    def command_exists(cmd: str) -> bool:
        """
        Check if a command exists in the system PATH.

        Args:
            cmd: Command name to check

        Returns:
            True if the command exists, False otherwise
        """
        return shutil.which(cmd) is not None

    @staticmethod
    def backup_file(fp: str) -> Optional[str]:
        """
        Backup a file with a timestamp suffix.

        Args:
            fp: Path to the file to backup

        Returns:
            Path to the backup file, or None if backup failed
        """
        if os.path.isfile(fp):
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = f"{fp}.bak.{ts}"
            try:
                shutil.copy2(fp, backup)
                logger.info(f"Backed up {fp} to {backup}")
                return backup
            except Exception as e:
                logger.warning(f"Backup failed for {fp}: {e}")
        return None

    @staticmethod
    def ensure_directory(
        path: str, owner: Optional[str] = None, mode: int = 0o755
    ) -> bool:
        """
        Ensure a directory exists with correct permissions.

        Args:
            path: Directory path
            owner: Owner (user:group) for the directory
            mode: Permission mode

        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            if owner:
                run_command(["chown", owner, path])
            logger.debug(f"Ensured directory: {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure directory {path}: {e}")
            return False

    @staticmethod
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        """
        Check if a TCP port is open.

        Args:
            port: Port number
            host: Host to check

        Returns:
            True if the port is open, False otherwise
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex((host, port)) == 0

    @staticmethod
    def get_apt_command() -> str:
        """
        Get the appropriate package manager command (nala if available, otherwise apt).

        Returns:
            Command to use (nala or apt)
        """
        return "nala" if Utils.command_exists("nala") else "apt"

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format a file size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted size string (e.g., "4.2 MB")
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ----------------------------------------------------------------
# Preflight & Environment Checkers
# ----------------------------------------------------------------
class PreflightChecker:
    """Preflight checks to ensure system is ready for setup."""

    def check_root(self) -> None:
        """
        Ensure the script runs as root.

        Raises:
            SetupError: If not running as root
        """
        if os.geteuid() != 0:
            print_error("This script must run with root privileges!")
            logger.error("Not running as root. Exiting.")
            sys.exit(1)
        logger.info("Root privileges confirmed.")

    def check_network(self) -> bool:
        """
        Check for network connectivity.

        Returns:
            True if network is available, False otherwise
        """
        logger.info("Checking network connectivity...")

        # Try multiple hosts for redundancy
        test_hosts = ["google.com", "cloudflare.com", "1.1.1.1", "deb.debian.org"]

        for host in test_hosts:
            try:
                if (
                    run_command(
                        ["ping", "-c", "1", "-W", "5", host], check=False
                    ).returncode
                    == 0
                ):
                    logger.info(f"Network connectivity confirmed via {host}.")
                    return True
            except Exception as e:
                logger.debug(f"Ping to {host} failed: {e}")
                continue

        logger.error("Network check failed - could not reach any test hosts.")
        return False

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        """
        Check if the system is running Debian.

        Returns:
            Tuple of (os_id, version) if Debian, None otherwise
        """
        logger.info("Checking OS version...")

        if not os.path.isfile("/etc/os-release"):
            logger.warning("Missing /etc/os-release file.")
            return None

        os_info = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_info[k] = v.strip('"')

        if os_info.get("ID") != "debian":
            logger.warning(
                f"Non-Debian system detected: {os_info.get('ID', 'unknown')}."
            )
            return None

        ver = os_info.get("VERSION_ID", "")
        logger.info(f"Detected Debian version: {ver}")
        return ("debian", ver)

    def save_config_snapshot(self) -> Optional[str]:
        """
        Create a snapshot archive of key configuration files.

        Returns:
            Path to the snapshot archive, or None if failed
        """
        logger.info("Saving configuration snapshot...")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        # Ensure backup directory exists
        os.makedirs(AppConfig.BACKUP_DIR, exist_ok=True)

        snapshot_path = os.path.join(
            AppConfig.BACKUP_DIR, f"config_snapshot_{ts}.tar.gz"
        )

        try:
            with tarfile.open(snapshot_path, "w:gz") as tar:
                files_added = 0

                for cfg in AppConfig.CONFIG_FILES:
                    if os.path.isfile(cfg):
                        tar.add(cfg, arcname=os.path.basename(cfg))
                        logger.info(f"Added {cfg} to snapshot.")
                        files_added += 1

                # Add manifest file with snapshot info
                manifest = f"""Debian Trixie Configuration Snapshot
Created: {datetime.datetime.now().isoformat()}
Hostname: {AppConfig.HOSTNAME}
Files: {files_added}
"""
                manifest_file = os.path.join(
                    AppConfig.TEMP_DIR, "snapshot_manifest.txt"
                )
                with open(manifest_file, "w") as f:
                    f.write(manifest)

                tar.add(manifest_file, arcname="MANIFEST.txt")
                os.unlink(manifest_file)

            logger.info(f"Snapshot saved to {snapshot_path}")
            print_success(f"Configuration snapshot saved to {snapshot_path}")
            return snapshot_path

        except Exception as e:
            logger.warning(f"Snapshot creation failed: {e}")
            return None


# ----------------------------------------------------------------
# APT Repository Manager
# ----------------------------------------------------------------
class APTSourcesManager:
    """Manages APT repository sources."""

    def __init__(self) -> None:
        """Initialize APT sources manager."""
        self.sources_list = "/etc/apt/sources.list"
        self.sources_dir = "/etc/apt/sources.list.d"
        self.backup_created = False

    def backup_sources(self) -> bool:
        """
        Backup existing APT sources.

        Returns:
            True if backup successful, False otherwise
        """
        if self.backup_created:
            return True

        try:
            if os.path.exists(self.sources_list):
                Utils.backup_file(self.sources_list)

            if os.path.isdir(self.sources_dir):
                for f in os.listdir(self.sources_dir):
                    if f.endswith(".list"):
                        Utils.backup_file(os.path.join(self.sources_dir, f))

            self.backup_created = True
            logger.info("APT sources backed up successfully.")
            return True

        except Exception as e:
            logger.error(f"Failed to backup APT sources: {e}")
            return False

    def add_debian_cdn_source(self) -> bool:
        """
        Configure APT to use the Debian CDN repositories.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring Debian Trixie CDN sources...")

        # Backup existing sources
        if not self.backup_sources():
            return False

        try:
            # Write new sources list
            with open(self.sources_list, "w") as f:
                f.write("# Debian Trixie repositories configured by setup utility\n")
                f.write(
                    f"deb {AppConfig.DEBIAN_CDN} trixie main contrib non-free-firmware\n"
                )
                f.write(
                    f"deb {AppConfig.DEBIAN_CDN} trixie-updates main contrib non-free-firmware\n"
                )
                # The trixie-security repository is causing 404 errors, so we'll comment it out
                # and use updates repository for security updates
                f.write(
                    f"# deb {AppConfig.DEBIAN_CDN} trixie-security main contrib non-free-firmware\n"
                )
                f.write("# Note: trixie-security is commented out due to 404 errors\n")
                f.write("# Use trixie-updates for security updates\n")
                f.write("\n# Uncomment if you need source packages\n")
                f.write(
                    f"# deb-src {AppConfig.DEBIAN_CDN} trixie main contrib non-free-firmware\n"
                )
                f.write(
                    f"# deb-src {AppConfig.DEBIAN_CDN} trixie-updates main contrib non-free-firmware\n"
                )

            logger.info(f"CDN sources configured in {self.sources_list}")
            return True

        except Exception as e:
            logger.error(f"Failed to configure Debian CDN sources: {e}")
            return False


# ----------------------------------------------------------------
# System Updater and Package Installer
# ----------------------------------------------------------------
class SystemUpdater:
    """Handles system updates and package installation."""

    def fix_package_issues(self) -> bool:
        """
        Fix common package management issues.

        Returns:
            True if issues fixed, False otherwise
        """
        logger.info("Fixing package issues...")

        try:
            # Try to fix any broken/interrupted package installations
            run_command(["dpkg", "--configure", "-a"])

            # Check for held packages
            held = run_command(["apt-mark", "showhold"], capture_output=True)
            if held.stdout.strip():
                print_warning(f"Found held packages: {held.stdout.strip()}")
                for pkg in held.stdout.strip().splitlines():
                    if pkg.strip():
                        run_command(["apt-mark", "unhold", pkg.strip()], check=False)

            # Attempt package repairs
            run_command(["apt", "--fix-broken", "install", "-y"])
            run_command(["apt", "clean"])
            run_command(["apt", "autoclean", "-y"])

            # Verify package system integrity
            check = run_command(["apt-get", "check"], capture_output=True)
            if check.returncode != 0:
                logger.error("Package system issues remain unresolved.")
                return False

            logger.info("Package issues fixed successfully.")
            return True

        except Exception as e:
            logger.error(f"Error fixing packages: {e}")
            return False

    def update_system(self, full_upgrade: bool = False) -> bool:
        """
        Update system packages.

        Args:
            full_upgrade: Whether to perform a full upgrade

        Returns:
            True if successful, False otherwise
        """
        logger.info("Updating system packages...")

        try:
            # First fix any existing package issues
            if not self.fix_package_issues():
                logger.warning(
                    "Proceeding with updates despite unresolved package issues."
                )

            # Try to use nala for update
            try:
                if Utils.command_exists("nala"):
                    run_command(["nala", "update"])
                else:
                    run_command(["apt", "update"])
            except Exception as e:
                logger.warning(f"Update failed: {e}; attempting apt update")
                run_command(["apt", "update"])

            # Perform upgrade
            upgrade_cmd = []
            if Utils.command_exists("nala"):
                upgrade_cmd = (
                    ["nala", "full-upgrade", "-y"]
                    if full_upgrade
                    else ["nala", "upgrade", "-y"]
                )
            else:
                upgrade_cmd = (
                    ["apt", "full-upgrade", "-y"]
                    if full_upgrade
                    else ["apt", "upgrade", "-y"]
                )

            try:
                run_command(upgrade_cmd)
            except Exception as e:
                logger.warning(
                    f"Upgrade failed with {upgrade_cmd[0]}: {e}. Trying apt..."
                )
                alt_cmd = (
                    ["apt", "full-upgrade", "-y"]
                    if full_upgrade
                    else ["apt", "upgrade", "-y"]
                )
                run_command(alt_cmd)

            logger.info("System update completed successfully.")
            return True

        except Exception as e:
            logger.error(f"System update error: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        """
        Install missing packages from the given list.

        Args:
            packages: List of packages to install (defaults to PACKAGES)

        Returns:
            True if successful, False otherwise
        """
        logger.info("Installing required packages...")

        # Use default package list if none provided
        packages = packages or PACKAGES

        # Fix package issues first
        if not self.fix_package_issues():
            logger.warning("Proceeding with installations despite package issues.")

        # Find missing packages
        missing = []
        for pkg in packages:
            try:
                result = subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                missing.append(pkg)

        # Skip if all packages are already installed
        if not missing:
            logger.info("All packages already installed.")
            return True

        logger.info(
            f"Installing {len(missing)} missing packages: {', '.join(missing[:5])}..."
        )
        if len(missing) > 5:
            logger.info(f"... and {len(missing) - 5} more")

        # Use batch installation to reduce failures
        success = True
        install_cmd = "nala" if Utils.command_exists("nala") else "apt"

        # Install in smaller batches to prevent failures
        batch_size = 20
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            try:
                logger.info(
                    f"Installing batch {i // batch_size + 1}/{(len(missing) + batch_size - 1) // batch_size}"
                )

                run_command(
                    [install_cmd, "install", "-y", "--no-install-recommends"] + batch,
                    check=False,
                )

                # Verify which packages were installed
                for pkg in batch:
                    try:
                        subprocess.run(
                            ["dpkg", "-s", pkg],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except subprocess.CalledProcessError:
                        logger.warning(f"Package {pkg} failed to install")
                        success = False
            except Exception as e:
                logger.warning(f"Batch installation failed: {e}")
                success = False

                # Try installing one by one if batch install fails
                for pkg in batch:
                    try:
                        run_command(
                            [
                                install_cmd,
                                "install",
                                "-y",
                                "--no-install-recommends",
                                pkg,
                            ],
                            check=False,
                        )
                    except Exception as pkg_e:
                        logger.warning(f"Failed to install {pkg}: {pkg_e}")

        # Final check to see how many packages were actually installed
        still_missing = 0
        for pkg in missing:
            try:
                subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                still_missing += 1

        installed_count = len(missing) - still_missing
        logger.info(
            f"Successfully installed {installed_count} out of {len(missing)} packages"
        )

        # Consider it a success if we installed at least 75% of packages
        if installed_count >= len(missing) * 0.75:
            return True
        else:
            logger.warning(
                f"Only {installed_count}/{len(missing)} packages were installed"
            )
            return success

    def configure_timezone(self, tz: str = "America/New_York") -> bool:
        """
        Set the system timezone.

        Args:
            tz: Timezone to set

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Setting timezone to {tz}...")

        # Verify timezone file exists
        tz_file = f"/usr/share/zoneinfo/{tz}"
        if not os.path.isfile(tz_file):
            logger.warning(f"Timezone file {tz_file} not found.")
            return False

        try:
            # Try to use timedatectl (systemd)
            if Utils.command_exists("timedatectl"):
                run_command(["timedatectl", "set-timezone", tz])
            else:
                # Legacy method
                if os.path.exists("/etc/localtime"):
                    os.remove("/etc/localtime")

                os.symlink(tz_file, "/etc/localtime")

                with open("/etc/timezone", "w") as f:
                    f.write(f"{tz}\n")

            logger.info(f"Timezone configured to {tz}.")
            return True

        except Exception as e:
            logger.error(f"Timezone configuration error: {e}")
            return False

    def configure_locale(self, locale: str = "en_US.UTF-8") -> bool:
        """
        Set the system locale.

        Args:
            locale: Locale to set

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Setting locale to {locale}...")

        try:
            # Generate locale
            run_command(["locale-gen", locale])

            # Set default locale
            run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])

            # Update environment file
            env_file = "/etc/environment"
            lines = []
            locale_set = False

            if os.path.isfile(env_file):
                with open(env_file) as f:
                    for line in f:
                        if line.startswith("LANG="):
                            lines.append(f"LANG={locale}\n")
                            locale_set = True
                        else:
                            lines.append(line)

            if not locale_set:
                lines.append(f"LANG={locale}\n")

            with open(env_file, "w") as f:
                f.writelines(lines)

            logger.info(f"Locale configured to {locale}.")
            return True

        except Exception as e:
            logger.error(f"Locale configuration error: {e}")
            return False


# ----------------------------------------------------------------
# User Environment Setup
# ----------------------------------------------------------------
class UserEnvironment:
    """Handles user environment configuration."""

    def setup_repos(self) -> bool:
        """
        Clone or update user repositories.

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Setting up repositories for {AppConfig.USERNAME}...")

        # Create GitHub directory
        gh_dir = os.path.join(AppConfig.USER_HOME, "github")
        Utils.ensure_directory(
            gh_dir, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
        )

        # Repositories to clone
        repos = ["bash", "windows", "web", "python", "go", "misc"]
        all_success = True

        # Clone/update each repository
        for repo in repos:
            repo_dir = os.path.join(gh_dir, repo)

            if os.path.isdir(os.path.join(repo_dir, ".git")):
                # Update existing repository
                try:
                    run_command(["git", "-C", repo_dir, "pull"])
                    logger.info(f"Updated repository: {repo}")
                except Exception as e:
                    logger.warning(f"Repository update failed for {repo}: {e}")
                    all_success = False
            else:
                # Clone new repository
                try:
                    run_command(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            repo_dir,
                        ]
                    )
                    logger.info(f"Cloned repository: {repo}")
                except Exception as e:
                    logger.warning(f"Repository clone failed for {repo}: {e}")
                    all_success = False

        # Fix ownership
        try:
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", gh_dir]
            )
        except Exception as e:
            logger.warning(f"Ownership update failed for {gh_dir}: {e}")
            all_success = False

        return all_success

    def copy_shell_configs(self) -> bool:
        """
        Copy shell configuration files to user and root directories.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Copying shell configuration files...")

        # Files to copy
        files = [".bashrc", ".profile"]

        # Try different source directories
        src_dir = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "dotfiles"
        )

        if not os.path.isdir(src_dir):
            src_dir = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
            )

        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory for dotfiles not found.")
            return False

        # Destination directories
        dest_dirs = [AppConfig.USER_HOME, "/root"]
        all_success = True

        # Copy each file to each destination
        for file in files:
            src = os.path.join(src_dir, file)

            if not os.path.isfile(src):
                logger.debug(f"Source file {src} not found, skipping.")
                continue

            for d in dest_dirs:
                dest = os.path.join(d, file)

                # Skip if files are identical
                copy_needed = True
                if os.path.isfile(dest) and filecmp.cmp(src, dest):
                    logger.debug(f"File {dest} is already up to date.")
                    copy_needed = False

                # Backup existing file if needed
                if copy_needed and os.path.isfile(dest):
                    Utils.backup_file(dest)

                # Copy file
                if copy_needed:
                    try:
                        shutil.copy2(src, dest)

                        # Set correct ownership
                        owner = (
                            f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
                            if d == AppConfig.USER_HOME
                            else "root:root"
                        )
                        run_command(["chown", owner, dest])

                        logger.info(f"Copied {src} to {dest}")
                    except Exception as e:
                        logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        all_success = False

        return all_success

    def copy_config_folders(self) -> bool:
        """
        Synchronize configuration folders to the user's .config directory.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Synchronizing configuration folders...")

        # Try different source directories
        src_dir = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "dotfiles"
        )

        if not os.path.isdir(src_dir):
            src_dir = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
            )

        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory for config folders not found.")
            return False

        # Ensure destination directory exists
        dest_dir = os.path.join(AppConfig.USER_HOME, ".config")
        Utils.ensure_directory(
            dest_dir, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
        )

        try:
            # Synchronize directories
            run_command(["rsync", "-a", "--update", f"{src_dir}/", f"{dest_dir}/"])

            # Fix ownership
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", dest_dir]
            )

            logger.info(f"Config folders synchronized to {dest_dir}")
            return True

        except Exception as e:
            logger.error(f"Error copying config folders: {e}")
            return False

    def set_default_shell(self) -> bool:
        """
        Set the default shell for the user.

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Setting default shell to /bin/bash for {AppConfig.USERNAME}...")

        # Ensure bash is installed
        if not Utils.command_exists("bash"):
            logger.warning("Bash not found, attempting to install...")
            if not SystemUpdater().install_packages(["bash"]):
                return False

        try:
            # Check if bash is in /etc/shells
            with open("/etc/shells") as f:
                shells = f.read()

            if "/bin/bash" not in shells:
                with open("/etc/shells", "a") as f:
                    f.write("/bin/bash\n")

            # Get current shell
            current_shell = (
                subprocess.check_output(
                    ["getent", "passwd", AppConfig.USERNAME], text=True
                )
                .strip()
                .split(":")[-1]
            )

            # Change shell if needed
            if current_shell != "/bin/bash":
                run_command(["chsh", "-s", "/bin/bash", AppConfig.USERNAME])
                logger.info(
                    f"Changed default shell to /bin/bash for {AppConfig.USERNAME}"
                )
            else:
                logger.info(
                    f"Default shell already set to /bin/bash for {AppConfig.USERNAME}"
                )

            return True

        except Exception as e:
            logger.error(f"Error setting default shell: {e}")
            return False


# ----------------------------------------------------------------
# Security Hardening
# ----------------------------------------------------------------
class SecurityHardener:
    """Implements security hardening measures."""

    def configure_ssh(self, port: int = 22) -> bool:
        """
        Secure and configure the SSH service.

        Args:
            port: SSH port to use

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring SSH service...")

        # Enable SSH service
        try:
            run_command(["systemctl", "enable", "--now", "ssh"])
        except Exception as e:
            logger.error(f"Error enabling SSH service: {e}")
            return False

        # Check SSH config file
        sshd_config = "/etc/ssh/sshd_config"
        if not os.path.isfile(sshd_config):
            logger.error(f"{sshd_config} not found.")
            return False

        # Backup original config
        Utils.backup_file(sshd_config)

        # Security settings to apply
        ssh_settings = {
            "Port": str(port),
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "PermitEmptyPasswords": "no",
            "ChallengeResponseAuthentication": "no",
            "Protocol": "2",
            "MaxAuthTries": "5",
            "ClientAliveInterval": "600",
            "ClientAliveCountMax": "48",
            "X11Forwarding": "no",
            "PermitUserEnvironment": "no",
            "DebianBanner": "no",
            "Banner": "none",
            "LogLevel": "VERBOSE",
            "StrictModes": "yes",
            "AllowAgentForwarding": "yes",
            "AllowTcpForwarding": "yes",
        }

        try:
            # Read existing config
            with open(sshd_config) as f:
                lines = f.readlines()

            # Update or add each setting
            for key, value in ssh_settings.items():
                updated = False

                # Try to update existing setting
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {value}\n"
                        updated = True
                        break

                # Add setting if not found
                if not updated:
                    lines.append(f"{key} {value}\n")

            # Write updated config
            with open(sshd_config, "w") as f:
                f.writelines(lines)

            logger.info("SSH configuration updated successfully.")

        except Exception as e:
            logger.error(f"Error updating SSH config: {e}")
            return False

        # Restart SSH service
        try:
            run_command(["systemctl", "restart", "ssh"])
            return True
        except Exception as e:
            logger.error(f"Error restarting SSH service: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """
        Configure sudoers for the designated user.

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Configuring sudoers for {AppConfig.USERNAME}...")

        # Verify user exists
        try:
            run_command(["id", AppConfig.USERNAME], capture_output=True)
        except Exception as e:
            logger.error(f"User {AppConfig.USERNAME} not found: {e}")
            return False

        try:
            # Check if user is in sudo group
            groups = subprocess.check_output(
                ["id", "-nG", AppConfig.USERNAME], text=True
            ).split()

            if "sudo" not in groups:
                run_command(["usermod", "-aG", "sudo", AppConfig.USERNAME])
                logger.info(f"Added {AppConfig.USERNAME} to sudo group")

        except Exception as e:
            logger.error(f"Error updating sudo group: {e}")
            return False

        # Create user-specific sudoers file
        sudo_file = f"/etc/sudoers.d/99-{AppConfig.USERNAME}"

        try:
            # Write sudoers configuration
            with open(sudo_file, "w") as f:
                f.write(
                    f"{AppConfig.USERNAME} ALL=(ALL:ALL) ALL\n"
                    "Defaults timestamp_timeout=15\n"
                    "Defaults requiretty\n"
                )

            # Set correct permissions
            os.chmod(sudo_file, 0o440)

            # Verify sudoers configuration
            run_command(["visudo", "-c"])

            logger.info(f"Sudoers configuration created for {AppConfig.USERNAME}")
            return True

        except Exception as e:
            logger.error(f"Sudoers configuration error: {e}")
            return False

    def configure_firewall(self) -> bool:
        """
        Configure the UFW firewall with allowed ports.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring UFW firewall...")

        # Check if UFW is available
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            logger.warning("UFW not found, attempting to install...")
            if not SystemUpdater().install_packages(["ufw"]):
                return False

        # Reset firewall rules
        try:
            run_command([ufw_cmd, "reset", "--force"], check=False)
            logger.info("Reset firewall rules")
        except Exception as e:
            logger.warning(f"UFW reset failed: {e}, continuing anyway...")

        # Set default policies
        for cmd in (
            [ufw_cmd, "default", "deny", "incoming"],
            [ufw_cmd, "default", "allow", "outgoing"],
        ):
            try:
                run_command(cmd)
            except Exception as e:
                logger.warning(f"UFW policy setting failed: {e}")

        # Allow specific ports
        for port in AppConfig.ALLOWED_PORTS:
            try:
                run_command([ufw_cmd, "allow", f"{port}/tcp"])
                logger.info(f"Allowed TCP port {port}")
            except Exception as e:
                logger.warning(f"UFW rule addition failed for port {port}: {e}")

        # Enable firewall
        try:
            status = run_command([ufw_cmd, "status"], capture_output=True)
            if "inactive" in status.stdout.lower():
                run_command([ufw_cmd, "--force", "enable"])
                logger.info("Enabled UFW firewall")
        except Exception as e:
            logger.error(f"UFW enable failed: {e}")
            return False

        # Configure logging and ensure service starts at boot
        try:
            run_command([ufw_cmd, "logging", "on"])
            run_command(["systemctl", "enable", "ufw"])
            run_command(["systemctl", "restart", "ufw"])

            # Verify firewall is active
            result = run_command(["systemctl", "is-active", "ufw"], capture_output=True)
            if "active" in result.stdout:
                logger.info("UFW firewall configured and active")
                return True
            else:
                logger.warning("UFW service is not active after configuration")
                return False

        except Exception as e:
            logger.error(f"UFW service configuration failed: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """
        Configure Fail2ban service to protect SSH.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring Fail2ban...")

        # Check if Fail2ban is installed
        if not Utils.command_exists("fail2ban-server"):
            logger.warning("Fail2ban not found, attempting to install...")
            if not SystemUpdater().install_packages(["fail2ban"]):
                return False

        # Path to jail configuration
        jail = "/etc/fail2ban/jail.local"

        # Fail2ban configuration
        config = (
            "[DEFAULT]\n"
            "bantime  = 3600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "filter   = sshd\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n"
        )

        # Backup existing config if needed
        if os.path.isfile(jail):
            Utils.backup_file(jail)

        try:
            # Write configuration
            with open(jail, "w") as f:
                f.write(config)

            # Enable and start Fail2ban
            run_command(["systemctl", "enable", "fail2ban"])
            run_command(["systemctl", "restart", "fail2ban"])

            # Verify service is active
            status = run_command(
                ["systemctl", "is-active", "fail2ban"], capture_output=True
            )

            if status.stdout.strip() == "active":
                logger.info("Fail2ban configured and running")
                return True
            else:
                logger.warning("Fail2ban service not active after configuration")
                return False

        except Exception as e:
            logger.error(f"Fail2ban configuration failed: {e}")
            return False

    def configure_apparmor(self) -> bool:
        """
        Configure AppArmor for additional system security.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring AppArmor...")

        try:
            # Install AppArmor if missing
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
                return False

            # Enable and start AppArmor
            run_command(["systemctl", "enable", "apparmor"])
            run_command(["systemctl", "start", "apparmor"])

            # Verify service is active
            status = run_command(
                ["systemctl", "is-active", "apparmor"], capture_output=True
            )

            if status.stdout.strip() == "active":
                # Update profiles if possible
                if Utils.command_exists("aa-update-profiles"):
                    try:
                        run_command(["aa-update-profiles"], check=False)
                        logger.info("Updated AppArmor profiles")
                    except Exception as e:
                        logger.warning(f"AppArmor profile update failed: {e}")

                logger.info("AppArmor configured and running")
                return True
            else:
                logger.warning("AppArmor service not active after configuration")
                return False

        except Exception as e:
            logger.error(f"AppArmor configuration failed: {e}")
            return False


# ----------------------------------------------------------------
# Service Installation and Configuration
# ----------------------------------------------------------------
class ServiceInstaller:
    """Installs and configures system services."""

    def install_nala(self) -> bool:
        """
        Install the Nala APT frontend.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Installing Nala package manager...")

        # Skip if already installed
        if Utils.command_exists("nala"):
            logger.info("Nala is already installed.")
            return True

        # Fix APT sources to temporarily bypass security repository error
        try:
            sources_list = "/etc/apt/sources.list"
            if os.path.exists(sources_list):
                # Create backup of original sources.list
                backup_file = Utils.backup_file(sources_list)
                logger.info(f"Backed up sources.list to {backup_file}")

                # Read current content
                with open(sources_list, "r") as f:
                    content = f.readlines()

                # Comment out the problematic trixie-security line
                with open(sources_list, "w") as f:
                    for line in content:
                        if "trixie-security" in line and not line.strip().startswith(
                            "#"
                        ):
                            f.write(f"# {line}")
                            logger.info(
                                "Temporarily commented out trixie-security repository"
                            )
                        else:
                            f.write(line)

            logger.info("Modified sources.list to avoid security repository errors")
        except Exception as e:
            logger.warning(f"Failed to modify sources.list: {e}")

        # Method 1: Install via APT
        try:
            # Update repositories (with reduced output to avoid errors)
            result = run_command(["apt", "update", "-qq"], check=False)
            if result.returncode != 0:
                logger.warning(
                    "APT update had errors, but continuing with installation"
                )

            # Install Nala with minimal dependencies
            run_command(["apt", "install", "nala", "-y", "--no-install-recommends"])

            # Verify installation
            if Utils.command_exists("nala"):
                logger.info("Nala installed successfully via apt")
                return True
        except Exception as e:
            logger.warning(f"Standard installation failed: {e}")

        # Method 2: Direct download fallback
        try:
            logger.info("Trying direct download method for Nala...")
            temp_dir = tempfile.mkdtemp(prefix="nala_install_")
            temp_deb = os.path.join(temp_dir, "nala.deb")

            # Download nala directly from Debian package repository
            download_urls = [
                "http://ftp.us.debian.org/debian/pool/main/n/nala/nala_0.14.0_all.deb",
                "http://deb.debian.org/debian/pool/main/n/nala/nala_0.14.0_all.deb",
            ]

            for url in download_urls:
                try:
                    logger.info(f"Downloading Nala from {url}")
                    run_command(["wget", "-q", url, "-O", temp_deb])
                    if os.path.exists(temp_deb) and os.path.getsize(temp_deb) > 0:
                        break
                except Exception:
                    continue

            if not os.path.exists(temp_deb) or os.path.getsize(temp_deb) == 0:
                raise Exception("Failed to download Nala package")

            # Install dependencies
            run_command(
                [
                    "apt",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    "python3-apt",
                    "python3-debian",
                    "apt-utils",
                    "python3",
                ]
            )

            # Install the package
            run_command(["dpkg", "-i", temp_deb])
            run_command(["apt", "--fix-broken", "install", "-y"])

            # Clean up
            shutil.rmtree(temp_dir, ignore_errors=True)

            # Verify installation
            if Utils.command_exists("nala"):
                logger.info("Nala installed successfully via direct download")
                return True
            else:
                logger.error("Nala installation failed after direct download")
                return False

        except Exception as e:
            logger.error(f"Nala installation failed completely: {e}")

            # Clean up any temp files
            if "temp_dir" in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Restore original sources.list if we modified it
            try:
                sources_backup = f"{sources_list}.bak."
                newest_backup = None
                newest_time = 0

                # Find the most recent backup
                for f in os.listdir(os.path.dirname(sources_list)):
                    if f.startswith(os.path.basename(sources_list) + ".bak."):
                        full_path = os.path.join(os.path.dirname(sources_list), f)
                        file_time = os.path.getmtime(full_path)
                        if file_time > newest_time:
                            newest_time = file_time
                            newest_backup = full_path

                if newest_backup:
                    shutil.copy2(newest_backup, sources_list)
                    logger.info(f"Restored original sources.list from {newest_backup}")
            except Exception as restore_err:
                logger.warning(f"Failed to restore sources.list: {restore_err}")

            return False

    def install_fastfetch(self) -> bool:
        """
        Install the Fastfetch system information tool.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Installing Fastfetch...")

        # Skip if already installed
        if Utils.command_exists("fastfetch"):
            logger.info("Fastfetch is already installed.")
            return True

        # Download path
        temp_deb = os.path.join(AppConfig.TEMP_DIR, "fastfetch-linux-amd64.deb")

        try:
            # Download package
            run_command(
                [
                    "curl",
                    "-L",
                    "-o",
                    temp_deb,
                    "https://github.com/fastfetch-cli/fastfetch/releases/download/2.37.0/fastfetch-linux-amd64.deb",
                ]
            )

            # Install package
            run_command(["dpkg", "-i", temp_deb])

            # Fix dependencies
            apt_cmd = Utils.get_apt_command()
            run_command([apt_cmd, "install", "-f", "-y"])

            # Clean up
            if os.path.exists(temp_deb):
                os.remove(temp_deb)

            # Verify installation
            success = Utils.command_exists("fastfetch")

            if success:
                logger.info("Fastfetch installed successfully")
            else:
                logger.error("Fastfetch installation failed")

            return success

        except Exception as e:
            logger.error(f"Fastfetch installation error: {e}")
            return False

    def docker_config(self) -> bool:
        """
        Install and configure Docker.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring Docker...")

        # Install Docker if missing
        if not Utils.command_exists("docker"):
            try:
                # Use official install script
                logger.info("Docker not found, installing...")
                script_path = os.path.join(AppConfig.TEMP_DIR, "get-docker.sh")

                run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script_path]
                )
                os.chmod(script_path, 0o755)
                run_command([script_path])
                os.remove(script_path)

                logger.info("Docker installed via official script")
            except Exception as e:
                logger.warning(f"Docker script installation failed: {e}")
                logger.info("Trying package installation...")

                # Fall back to package installation
                if not SystemUpdater().install_packages(["docker.io"]):
                    return False

        # Add user to docker group
        try:
            groups = subprocess.check_output(
                ["id", "-nG", AppConfig.USERNAME], text=True
            ).split()

            if "docker" not in groups:
                run_command(["usermod", "-aG", "docker", AppConfig.USERNAME])
                logger.info(f"Added {AppConfig.USERNAME} to docker group")
        except Exception as e:
            logger.warning(f"Failed to update docker group: {e}")

        # Configure daemon settings
        daemon_json = "/etc/docker/daemon.json"
        os.makedirs("/etc/docker", exist_ok=True)

        daemon_config = {
            "log-driver": "json-file",
            "log-opts": {"max-size": "10m", "max-file": "3"},
            "exec-opts": ["native.cgroupdriver=systemd"],
            "storage-driver": "overlay2",
            "features": {"buildkit": True},
            "default-address-pools": [{"base": "172.17.0.0/16", "size": 24}],
        }

        daemon_content = json.dumps(daemon_config, indent=4)

        # Check if config update is needed
        update_needed = True
        if os.path.isfile(daemon_json):
            try:
                with open(daemon_json) as f:
                    existing = json.load(f)

                if existing == daemon_config:
                    update_needed = False
                    logger.info("Docker daemon config is already up to date")
                else:
                    Utils.backup_file(daemon_json)
            except Exception as e:
                logger.warning(f"Failed to read docker daemon config: {e}")

        # Update config if needed
        if update_needed:
            try:
                with open(daemon_json, "w") as f:
                    f.write(daemon_content)
                logger.info("Updated Docker daemon configuration")
            except Exception as e:
                logger.warning(f"Failed to update docker daemon config: {e}")

        # Enable and restart Docker
        try:
            run_command(["systemctl", "enable", "docker"])
            run_command(["systemctl", "restart", "docker"])
        except Exception as e:
            logger.error(f"Failed to restart Docker: {e}")
            return False

        # Install docker-compose if missing
        if not Utils.command_exists("docker-compose"):
            try:
                apt_cmd = Utils.get_apt_command()
                run_command([apt_cmd, "install", "docker-compose-plugin", "-y"])
                logger.info("Docker Compose plugin installed")
            except Exception as e:
                logger.warning(f"Docker Compose installation failed: {e}")

        # Verify Docker is running
        try:
            run_command(["docker", "info"], capture_output=True)
            logger.info("Docker is configured and running")
            return True
        except Exception as e:
            logger.error(f"Docker verification failed: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        """
        Install and enable Tailscale.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Installing and enabling Tailscale...")

        # Skip if already installed
        if Utils.command_exists("tailscale"):
            logger.info("Tailscale is already installed")
        else:
            try:
                # Install using official script
                run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )
                logger.info("Tailscale installed")
            except Exception as e:
                logger.error(f"Tailscale installation failed: {e}")
                return False

        # Enable and start service
        try:
            run_command(["systemctl", "enable", "tailscaled"])
            run_command(["systemctl", "start", "tailscaled"])

            # Verify service is running
            status = run_command(
                ["systemctl", "is-active", "tailscaled"], capture_output=True
            )

            if status.stdout.strip() == "active":
                logger.info("Tailscale daemon is running")
                return True
            else:
                logger.warning("Tailscale daemon is not active after configuration")
                # Consider it success if the binary is available
                return Utils.command_exists("tailscale")

        except Exception as e:
            logger.error(f"Tailscale service configuration failed: {e}")
            return Utils.command_exists("tailscale")

    def deploy_user_scripts(self) -> bool:
        """
        Deploy user scripts to the user's bin directory.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Deploying user scripts...")

        # Try different source directories
        src = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "_scripts"
        )

        if not os.path.isdir(src):
            src = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts"
            )

        if not os.path.isdir(src):
            logger.warning("Scripts source directory not found")
            return False

        # Target directory
        tgt = os.path.join(AppConfig.USER_HOME, "bin")

        # Ensure target directory exists
        Utils.ensure_directory(tgt, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}")

        try:
            # Synchronize scripts
            run_command(["rsync", "-ah", "--delete", f"{src}/", f"{tgt}/"])

            # Make scripts executable
            run_command(["find", tgt, "-type", "f", "-exec", "chmod", "755", "{}", ";"])

            # Fix ownership
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", tgt]
            )

            logger.info(f"User scripts deployed to {tgt}")
            return True

        except Exception as e:
            logger.error(f"Failed to deploy user scripts: {e}")
            return False

    def configure_unattended_upgrades(self) -> bool:
        """
        Configure unattended upgrades for automated security updates.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Configuring unattended upgrades...")

        try:
            # Install required packages
            apt_cmd = Utils.get_apt_command()
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                return False

            # Configure automatic upgrades
            auto_file = "/etc/apt/apt.conf.d/20auto-upgrades"
            auto_content = (
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )

            with open(auto_file, "w") as f:
                f.write(auto_content)

            # Configure unattended upgrades settings
            unattended_file = "/etc/apt/apt.conf.d/50unattended-upgrades"

            if os.path.isfile(unattended_file):
                Utils.backup_file(unattended_file)

            unattended_content = (
                "Unattended-Upgrade::Allowed-Origins {\n"
                '    "${distro_id}:${distro_codename}";\n'
                '    "${distro_id}:${distro_codename}-security";\n'
                '    "${distro_id}:${distro_codename}-updates";\n'
                "};\n\n"
                "Unattended-Upgrade::Package-Blacklist {\n"
                "};\n\n"
                'Unattended-Upgrade::DevRelease "false";\n'
                'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";\n'
                'Unattended-Upgrade::Remove-Unused-Dependencies "true";\n'
                'Unattended-Upgrade::Automatic-Reboot "false";\n'
                'Unattended-Upgrade::Automatic-Reboot-Time "02:00";\n'
                'Unattended-Upgrade::SyslogEnable "true";\n'
            )

            with open(unattended_file, "w") as f:
                f.write(unattended_content)

            # Enable and start service
            run_command(["systemctl", "enable", "unattended-upgrades"])
            run_command(["systemctl", "restart", "unattended-upgrades"])

            # Verify service is running
            status = run_command(
                ["systemctl", "is-active", "unattended-upgrades"], capture_output=True
            )

            if status.stdout.strip() == "active":
                logger.info("Unattended upgrades configured and running")
                return True
            else:
                logger.warning(
                    "Unattended upgrades service not active after configuration"
                )
                return False

        except Exception as e:
            logger.error(f"Unattended upgrades configuration failed: {e}")
            return False


# ----------------------------------------------------------------
# Maintenance Manager
# ----------------------------------------------------------------
class MaintenanceManager:
    """Manages system maintenance tasks."""

    def configure_periodic(self) -> bool:
        """
        Set up a daily maintenance cron job.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Setting up daily maintenance cron job...")

        # Cron job file path
        cron_file = "/etc/cron.daily/debian_maintenance"

        # Marker to identify our script
        marker = "# Debian maintenance script"

        # Check if script already exists
        if os.path.isfile(cron_file):
            with open(cron_file) as f:
                if marker in f.read():
                    logger.info("Maintenance cron job already exists")
                    return True

            # Backup existing file
            Utils.backup_file(cron_file)

        # Script content
        content = f"""#!/bin/sh
{marker}
LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG

# Rotate log if it's too large
if [ -f "$LOG" ] && [ $(stat -c%s "$LOG") -gt 10485760 ]; then
    gzip -c "$LOG" > "$LOG.$(date +%Y%m%d).gz"
    truncate -s 0 "$LOG"
    echo "Log rotated at $(date)" >> "$LOG"
fi

# Use nala if available, otherwise apt
if command -v nala >/dev/null 2>&1; then
    nala update -qq >> $LOG 2>&1
    nala upgrade -y >> $LOG 2>&1
    nala autoremove -y >> $LOG 2>&1
    nala clean >> $LOG 2>&1
else
    apt update -qq >> $LOG 2>&1
    apt upgrade -y >> $LOG 2>&1
    apt autoremove -y >> $LOG 2>&1
    apt clean >> $LOG 2>&1
fi

# System status information
echo "Disk usage:" >> $LOG
df -h / >> $LOG 2>&1

echo "Memory usage:" >> $LOG
free -h >> $LOG 2>&1

echo "Maintenance completed $(date)" >> $LOG
"""

        try:
            # Write script
            with open(cron_file, "w") as f:
                f.write(content)

            # Make executable
            os.chmod(cron_file, 0o755)

            logger.info("Daily maintenance cron job configured")
            return True

        except Exception as e:
            logger.error(f"Failed to create maintenance cron job: {e}")
            return False

    def backup_configs(self) -> bool:
        """
        Backup important configuration files.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Backing up configuration files...")

        # Create backup directory with timestamp
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(AppConfig.BACKUP_DIR, f"debian_config_{ts}")
        os.makedirs(backup_dir, exist_ok=True)

        success = True
        files_backed_up = 0

        # Copy each config file
        for file in AppConfig.CONFIG_FILES:
            if os.path.isfile(file):
                try:
                    dest = os.path.join(backup_dir, os.path.basename(file))
                    shutil.copy2(file, dest)
                    files_backed_up += 1
                except Exception as e:
                    logger.warning(f"Backup failed for {file}: {e}")
                    success = False

        try:
            # Create manifest file
            manifest = os.path.join(backup_dir, "MANIFEST.txt")
            with open(manifest, "w") as f:
                f.write("Debian Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {AppConfig.HOSTNAME}\n\n")
                f.write("Files:\n")

                for file in AppConfig.CONFIG_FILES:
                    if os.path.isfile(os.path.join(backup_dir, os.path.basename(file))):
                        f.write(f"- {file}\n")
        except Exception as e:
            logger.warning(f"Failed to create backup manifest: {e}")

        logger.info(f"Backed up {files_backed_up} configuration files to {backup_dir}")
        return success

    def update_ssl_certificates(self) -> bool:
        """
        Update SSL certificates using certbot.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Updating SSL certificates...")

        # Install certbot if missing
        if not Utils.command_exists("certbot"):
            logger.info("Certbot not found, installing...")
            if not SystemUpdater().install_packages(["certbot"]):
                return False

        try:
            # Dry run to check for renewals
            output = run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True
            ).stdout

            # Perform actual renewal if needed
            if "No renewals were attempted" not in output:
                logger.info("Certificate renewals needed, running certbot")
                run_command(["certbot", "renew"])
            else:
                logger.info("No certificate renewals needed")

            return True

        except Exception as e:
            logger.error(f"SSL certificate update failed: {e}")
            return False


# ----------------------------------------------------------------
# System Tuning and Home Permissions
# ----------------------------------------------------------------
class SystemTuner:
    """Tunes system parameters for optimal performance."""

    def tune_system(self) -> bool:
        """
        Apply performance tuning settings to the system.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Applying system tuning settings...")

        # Path to sysctl config
        sysctl_conf = "/etc/sysctl.conf"

        # Backup original config
        if os.path.isfile(sysctl_conf):
            Utils.backup_file(sysctl_conf)

        # Performance tuning settings
        tuning = {
            "net.core.somaxconn": "1024",
            "net.core.netdev_max_backlog": "5000",
            "net.ipv4.tcp_max_syn_backlog": "8192",
            "net.ipv4.tcp_slow_start_after_idle": "0",
            "net.ipv4.tcp_tw_reuse": "1",
            "net.ipv4.ip_local_port_range": "1024 65535",
            "net.ipv4.tcp_rmem": "4096 87380 16777216",
            "net.ipv4.tcp_wmem": "4096 65536 16777216",
            "net.ipv4.tcp_mtu_probing": "1",
            "fs.file-max": "2097152",
            "vm.swappiness": "10",
            "vm.dirty_ratio": "60",
            "vm.dirty_background_ratio": "2",
            "kernel.sysrq": "0",
            "kernel.core_uses_pid": "1",
            "net.ipv4.conf.default.rp_filter": "1",
            "net.ipv4.conf.all.rp_filter": "1",
        }

        try:
            # Read existing config
            with open(sysctl_conf) as f:
                content = f.read()

            # Remove existing tuning section if present
            marker = "# Performance tuning settings for Debian"
            if marker in content:
                content = re.split(marker, content)[0]

            # Add new tuning section
            content += f"\n{marker}\n" + "".join(
                f"{k} = {v}\n" for k, v in tuning.items()
            )

            # Write updated config
            with open(sysctl_conf, "w") as f:
                f.write(content)

            # Apply settings
            run_command(["sysctl", "-p"])

            logger.info("System tuning settings applied")
            return True

        except Exception as e:
            logger.error(f"System tuning failed: {e}")
            return False

    def home_permissions(self) -> bool:
        """
        Secure user home directory permissions.

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Securing home directory for {AppConfig.USERNAME}...")

        try:
            # Set ownership
            run_command(
                [
                    "chown",
                    "-R",
                    f"{AppConfig.USERNAME}:{AppConfig.USERNAME}",
                    AppConfig.USER_HOME,
                ]
            )

            # Set base permission
            run_command(["chmod", "750", AppConfig.USER_HOME])

            # Set stricter permissions for sensitive directories
            for secure_dir in [".ssh", ".gnupg", ".config"]:
                dir_path = os.path.join(AppConfig.USER_HOME, secure_dir)
                if os.path.isdir(dir_path):
                    run_command(["chmod", "700", dir_path])
                    logger.info(f"Secured {secure_dir} directory")

            # Set group sticky bit on all directories (to maintain permissions)
            run_command(
                [
                    "find",
                    AppConfig.USER_HOME,
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    ";",
                ]
            )

            # Set default ACLs if available
            if Utils.command_exists("setfacl"):
                run_command(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{AppConfig.USERNAME}:rwX,g:{AppConfig.USERNAME}:r-X,o::---",
                        AppConfig.USER_HOME,
                    ]
                )
                logger.info("Applied ACLs to home directory")

            logger.info(f"Home directory permissions secured for {AppConfig.USERNAME}")
            return True

        except Exception as e:
            logger.error(f"Failed to secure home directory: {e}")
            return False


# ----------------------------------------------------------------
# Final Health Check and Cleanup
# ----------------------------------------------------------------
class FinalChecker:
    """Performs final system health checks and cleanup."""

    def system_health_check(self) -> Dict[str, Any]:
        """
        Perform a system health check and return details.

        Returns:
            Dictionary containing health check results
        """
        logger.info("Performing system health check...")

        # Initialize health information dictionary
        health: Dict[str, Any] = {}

        try:
            # Get uptime
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            health["uptime"] = uptime
            logger.info(f"System uptime: {uptime}")
        except Exception as e:
            logger.warning(f"Failed to get uptime: {e}")

        try:
            # Check disk usage
            df_lines = (
                subprocess.check_output(["df", "-h", "/"], text=True)
                .strip()
                .splitlines()
            )
            if len(df_lines) >= 2:
                data = df_lines[1].split()
                health["disk"] = {
                    "total": data[1],
                    "used": data[2],
                    "available": data[3],
                    "percent_used": data[4],
                }
                logger.info(
                    f"Disk usage: {data[4]} of {data[1]} used, {data[3]} available"
                )
        except Exception as e:
            logger.warning(f"Failed to check disk usage: {e}")

        try:
            # Check memory usage
            free_lines = (
                subprocess.check_output(["free", "-h"], text=True).strip().splitlines()
            )
            for line in free_lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    health["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                    }
                    logger.info(
                        f"Memory usage: {parts[2]} of {parts[1]} used, {parts[3]} free"
                    )
                    break
        except Exception as e:
            logger.warning(f"Failed to check memory usage: {e}")

        try:
            # Check system load
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]

            health["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
            logger.info(f"System load: {load[0]} (1m), {load[1]} (5m), {load[2]} (15m)")
        except Exception as e:
            logger.warning(f"Failed to check system load: {e}")

        try:
            # Check for kernel errors
            dmesg_output = subprocess.check_output(
                ["dmesg", "--level=err,crit,alert,emerg"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            health["kernel_errors"] = bool(dmesg_output)

            if health["kernel_errors"]:
                logger.warning("Kernel errors detected in dmesg output")
            else:
                logger.info("No kernel errors detected")
        except Exception as e:
            logger.warning(f"Failed to check kernel errors: {e}")

        try:
            # Check for available updates
            apt_cmd = Utils.get_apt_command()
            if apt_cmd == "nala":
                updates = (
                    subprocess.check_output(
                        ["nala", "list", "--upgradable"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                    .strip()
                    .splitlines()
                )
            else:
                updates = (
                    subprocess.check_output(
                        ["apt", "list", "--upgradable"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                    .strip()
                    .splitlines()
                )

            # Count security updates and total updates
            security_updates = sum(1 for line in updates if "security" in line.lower())
            total_updates = max(0, len(updates) - 1)  # Subtract header line

            health["updates"] = {"total": total_updates, "security": security_updates}
            logger.info(
                f"Available updates: {total_updates} total, {security_updates} security"
            )
        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")

        return health

    def verify_firewall_rules(self) -> bool:
        """
        Verify that firewall rules are set correctly.

        Returns:
            True if firewall is configured correctly, False otherwise
        """
        logger.info("Verifying firewall rules...")

        try:
            # Check UFW status
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()

            if "inactive" in ufw_status.lower():
                logger.warning("UFW firewall is inactive")
                return False

            logger.info("UFW firewall is active")

            # Check if allowed ports are accessible
            port_status = []

            for port in AppConfig.ALLOWED_PORTS:
                try:
                    # Try netcat first
                    result = subprocess.run(
                        ["nc", "-z", "-w3", "127.0.0.1", port],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                    # Fall back to socket check
                    if result.returncode != 0 and not Utils.is_port_open(int(port)):
                        logger.warning(f"Port {port} is not accessible")
                        port_status.append(False)
                    else:
                        logger.info(f"Port {port} is correctly configured")
                        port_status.append(True)
                except Exception as e:
                    logger.warning(f"Failed to check port {port}: {e}")
                    port_status.append(False)

            # At least one port should be accessible
            return any(port_status)

        except Exception as e:
            logger.error(f"Firewall verification failed: {e}")
            return False

    def final_checks(self) -> bool:
        """
        Perform final system checks.

        Returns:
            True if all checks pass, False otherwise
        """
        logger.info("Performing final system checks...")
        all_passed = True

        try:
            # Check kernel version
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            logger.info(f"Kernel version: {kernel}")

            # Check disk usage
            disk_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            disk_percent = int(disk_line.split()[4].strip("%"))

            if disk_percent > 90:
                logger.warning(f"High disk usage: {disk_percent}%")
                all_passed = False
            else:
                logger.info(f"Disk usage: {disk_percent}%")

            # Check system load
            load_avg = open("/proc/loadavg").read().split()[:3]
            cpu_count = os.cpu_count() or 1

            if float(load_avg[1]) > cpu_count:
                logger.warning(f"High system load: {load_avg[1]} (CPUs: {cpu_count})")
                all_passed = False
            else:
                logger.info(f"System load: {load_avg[1]} (CPUs: {cpu_count})")

            # Check critical services
            services = [
                "ssh",
                "ufw",
                "fail2ban",
                "docker",
                "tailscaled",
                "unattended-upgrades",
            ]

            for svc in services:
                status = subprocess.run(
                    ["systemctl", "is-active", svc],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                if status.stdout.strip() != "active" and svc in ["ssh", "ufw"]:
                    logger.warning(f"Critical service not active: {svc}")
                    all_passed = False
                else:
                    logger.info(f"Service {svc}: {status.stdout.strip()}")

            # Check for pending upgrades
            try:
                unattended_output = subprocess.check_output(
                    ["unattended-upgrade", "--dry-run", "--debug"],
                    text=True,
                    stderr=subprocess.STDOUT,
                )

                if any(
                    "Packages that will be upgraded:" in line
                    and "0 upgrades" not in line
                    for line in unattended_output.splitlines()
                ):
                    logger.warning("Pending upgrades detected")
                    all_passed = False
            except Exception as e:
                logger.debug(f"Unattended upgrade check failed: {e}")

            return all_passed

        except Exception as e:
            logger.error(f"Error during final checks: {e}")
            return False

    def cleanup_system(self) -> bool:
        """
        Perform system cleanup tasks.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Performing system cleanup...")
        success = True

        try:
            # Clean up package cache
            apt_cmd = Utils.get_apt_command()
            if apt_cmd == "nala":
                run_command(["nala", "autoremove", "-y"])
                run_command(["nala", "clean"])
                logger.info("Package cache cleaned with nala")
            else:
                run_command(["apt", "autoremove", "-y"])
                run_command(["apt", "clean"])
                logger.info("Package cache cleaned with apt")

            # Clean up old kernels
            try:
                # Get current kernel
                current_kernel = subprocess.check_output(
                    ["uname", "-r"], text=True
                ).strip()

                # List installed kernels
                installed = (
                    subprocess.check_output(
                        ["dpkg", "--list", "linux-image-*", "linux-headers-*"],
                        text=True,
                    )
                    .strip()
                    .splitlines()
                )

                # Find old kernels
                old_kernels = [
                    line.split()[1]
                    for line in installed
                    if line.startswith("ii")
                    and line.split()[1]
                    not in (
                        f"linux-image-{current_kernel}",
                        f"linux-headers-{current_kernel}",
                    )
                    and "generic" in line.split()[1]
                ]

                # Remove old kernels except the most recent one
                if len(old_kernels) > 1:
                    old_kernels.sort()
                    to_remove = old_kernels[:-1]

                    if to_remove:
                        logger.info(f"Removing {len(to_remove)} old kernels")
                        run_command([apt_cmd, "purge", "-y"] + to_remove)
            except Exception as e:
                logger.warning(f"Old kernel cleanup failed: {e}")
                success = False

            # Clean up journal logs
            if Utils.command_exists("journalctl"):
                run_command(["journalctl", "--vacuum-time=7d"])
                logger.info("Journal logs cleaned up")

            # Clean up old temporary files
            for tmp in ["/tmp", "/var/tmp"]:
                try:
                    run_command(
                        [
                            "find",
                            tmp,
                            "-type",
                            "f",
                            "-atime",
                            "+7",
                            "-not",
                            "-path",
                            "*/\\.*",
                            "-delete",
                        ]
                    )
                    logger.info(f"Cleaned up old files in {tmp}")
                except Exception as e:
                    logger.warning(f"Failed to clean {tmp}: {e}")
                    success = False

            # Compress large log files
            try:
                log_files = (
                    subprocess.check_output(
                        ["find", "/var/log", "-type", "f", "-size", "+50M"], text=True
                    )
                    .strip()
                    .splitlines()
                )

                for lf in log_files:
                    logger.info(f"Compressing large log file: {lf}")
                    with open(lf, "rb") as fin, gzip.open(f"{lf}.gz", "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                    open(lf, "w").close()
            except Exception as e:
                logger.warning(f"Log file compression failed: {e}")
                success = False

            return success

        except Exception as e:
            logger.error(f"System cleanup failed: {e}")
            return False

    def auto_reboot(self) -> None:
        """
        Automatically reboot the system after a delay.
        """
        logger.info("Setup complete. Rebooting in 60 seconds.")
        print_success("Setup completed successfully. Rebooting in 60 seconds...")

        # Show countdown
        with Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[bold green]Rebooting in"),
            TimeElapsedColumn(
                time_format="[bold]:ss[/bold]s", elapsed_when_stopped=False
            ),
            console=console,
        ) as progress:
            task = progress.add_task("Rebooting...", total=60)

            for i in range(60):
                progress.update(task, completed=i)
                time.sleep(1)

        # Reboot
        try:
            run_command(["shutdown", "-r", "now"])
        except Exception as e:
            logger.error(f"Reboot failed: {e}")


# ----------------------------------------------------------------
# Main Orchestration Class
# ----------------------------------------------------------------
class DebianServerSetup:
    """Main orchestration class for Debian server setup."""

    def __init__(self) -> None:
        """Initialize the setup orchestrator."""
        self.success = True
        self.start_time = time.time()
        self.preflight = PreflightChecker()
        self.apt_sources = APTSourcesManager()
        self.updater = SystemUpdater()
        self.user_env = UserEnvironment()
        self.security = SecurityHardener()
        self.services = ServiceInstaller()
        self.maintenance = MaintenanceManager()
        self.tuner = SystemTuner()
        self.final_checker = FinalChecker()

    def run(self) -> int:
        """
        Run the complete Debian server setup and hardening process.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(create_header())
        print_step(f"Starting Debian Trixie setup at {now}")
        logger.info(f"Starting Debian Trixie Server Setup at {now}")

        # Phase 1: Pre-flight Checks
        print_section("Phase 1: Pre-flight Checks")
        try:
            run_with_progress(
                "Checking root privileges",
                self.preflight.check_root,
                task_name="preflight",
            )

            if not run_with_progress(
                "Checking network connectivity",
                self.preflight.check_network,
            ):
                logger.error("Network check failed.")
                SETUP_STATUS["preflight"] = {
                    "status": "failed",
                    "message": "Network check failed",
                }
                print_error("Network check failed. Cannot continue setup.")
                sys.exit(1)

            if not run_with_progress(
                "Checking OS version",
                self.preflight.check_os_version,
            ):
                logger.warning("OS check failed – proceeding with caution.")

            run_with_progress(
                "Saving configuration snapshot",
                self.preflight.save_config_snapshot,
            )
        except Exception as e:
            logger.error(f"Preflight error: {e}")
            self.success = False

        # Phase 2: Configure APT Sources
        print_section("Phase 2: Configure APT Sources")
        try:
            if not run_with_progress(
                "Configuring Debian Trixie APT sources",
                self.apt_sources.add_debian_cdn_source,
                task_name="apt_sources",
            ):
                logger.error("APT sources configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"APT sources error: {e}")
            self.success = False

        # Phase 3: Installing Nala (MUST HAPPEN FIRST)
        print_section("Phase 3: Installing Nala")
        try:
            if not run_with_progress(
                "Installing Nala package manager",
                self.services.install_nala,
                task_name="nala_install",
            ):
                logger.warning("Nala installation failed, will use apt instead.")
        except Exception as e:
            logger.error(f"Nala installation error: {e}")
            logger.warning("Will use apt instead of nala.")

        # Phase 4: Fix broken packages
        print_section("Fix Broken Packages")

        def fix_broken():
            """Fix broken package installations."""
            # Clean up old unattended upgrade backups
            backup_dir = "/etc/apt/apt.conf.d/"
            count = 0
            for fname in os.listdir(backup_dir):
                if fname.startswith("50unattended-upgrades.bak."):
                    try:
                        os.remove(os.path.join(backup_dir, fname))
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove {fname}: {e}")

            if count > 0:
                logger.info(f"Removed {count} old unattended-upgrades backup files")

            # Fix broken packages with appropriate command
            apt_cmd = Utils.get_apt_command()
            return run_command([apt_cmd, "--fix-broken", "install", "-y"])

        run_with_progress(
            "Fixing broken packages",
            fix_broken,
            task_name="fix_broken",
        )

        # Phase 5: System Update & Basic Configuration
        print_section("Phase 5: System Update & Basic Configuration")
        try:
            if not run_with_progress(
                "Updating system packages",
                self.updater.update_system,
                task_name="system_update",
            ):
                logger.warning("System update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"System update error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Installing required packages",
                self.updater.install_packages,
                task_name="packages_install",
            ):
                logger.warning("Package installation issues.")
                self.success = False
        except Exception as e:
            logger.error(f"Package installation error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring timezone",
                self.updater.configure_timezone,
            ):
                logger.warning("Timezone configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring locale",
                self.updater.configure_locale,
            ):
                logger.warning("Locale configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Locale error: {e}")
            self.success = False

        # Phase 6: User Environment Setup
        print_section("Phase 6: User Environment Setup")
        try:
            if not run_with_progress(
                "Setting up user repositories",
                self.user_env.setup_repos,
                task_name="user_env",
            ):
                logger.warning("User repository setup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"User repos error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Copying shell configuration files",
                self.user_env.copy_shell_configs,
            ):
                logger.warning("Shell configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Shell config error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Copying configuration folders",
                self.user_env.copy_config_folders,
            ):
                logger.warning("Config folder copy failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Config folder error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Setting default shell",
                self.user_env.set_default_shell,
            ):
                logger.warning("Default shell update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Default shell error: {e}")
            self.success = False

        # Phase 7: Security & Hardening
        print_section("Phase 7: Security & Hardening")
        try:
            if not run_with_progress(
                "Configuring SSH server",
                self.security.configure_ssh,
                task_name="security",
            ):
                logger.warning("SSH configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSH error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring sudoers",
                self.security.setup_sudoers,
            ):
                logger.warning("Sudoers configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Sudoers error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring firewall",
                self.security.configure_firewall,
            ):
                logger.warning("Firewall configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring Fail2ban",
                self.security.configure_fail2ban,
            ):
                logger.warning("Fail2ban configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fail2ban error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring AppArmor",
                self.security.configure_apparmor,
            ):
                logger.warning("AppArmor configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"AppArmor error: {e}")
            self.success = False

        # Phase 8: Service Installations
        print_section("Phase 8: Service Installations")
        try:
            if not run_with_progress(
                "Installing Fastfetch",
                self.services.install_fastfetch,
                task_name="services",
            ):
                logger.warning("Fastfetch installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fastfetch error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring Docker",
                self.services.docker_config,
            ):
                logger.warning("Docker configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Docker error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Installing Tailscale",
                self.services.install_enable_tailscale,
            ):
                logger.warning("Tailscale installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Tailscale error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Configuring unattended upgrades",
                self.services.configure_unattended_upgrades,
            ):
                logger.warning("Unattended upgrades configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Unattended upgrades error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Deploying user scripts",
                self.services.deploy_user_scripts,
            ):
                logger.warning("User scripts deployment failed.")
                self.success = False
        except Exception as e:
            logger.error(f"User scripts error: {e}")
            self.success = False

        # Phase 9: Maintenance Tasks
        print_section("Phase 9: Maintenance Tasks")
        try:
            if not run_with_progress(
                "Configuring periodic maintenance",
                self.maintenance.configure_periodic,
                task_name="maintenance",
            ):
                logger.warning("Periodic maintenance configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Periodic maintenance error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Backing up configurations",
                self.maintenance.backup_configs,
            ):
                logger.warning("Configuration backup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Backup error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Updating SSL certificates",
                self.maintenance.update_ssl_certificates,
            ):
                logger.warning("SSL certificate update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSL certificate error: {e}")
            self.success = False

        # Phase 10: System Tuning & Permissions
        print_section("Phase 10: System Tuning & Permissions")
        try:
            if not run_with_progress(
                "Applying system tuning",
                self.tuner.tune_system,
                task_name="tuning",
            ):
                logger.warning("System tuning failed.")
                self.success = False
        except Exception as e:
            logger.error(f"System tuning error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Securing home directory",
                self.tuner.home_permissions,
            ):
                logger.warning("Home directory security failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Home permissions error: {e}")
            self.success = False

        # Phase 11: Final Checks & Cleanup
        print_section("Phase 11: Final Checks & Cleanup")
        SETUP_STATUS["final"] = {
            "status": "in_progress",
            "message": "Running final checks...",
        }

        try:
            health_info = run_with_progress(
                "Performing system health check",
                self.final_checker.system_health_check,
            )
            logger.info(f"Health check results: {health_info}")
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self.success = False

        try:
            if not run_with_progress(
                "Verifying firewall rules",
                self.final_checker.verify_firewall_rules,
            ):
                logger.warning("Firewall verification failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall verification error: {e}")
            self.success = False

        final_result = True
        try:
            final_result = run_with_progress(
                "Performing final system checks",
                self.final_checker.final_checks,
            )

            if not final_result:
                logger.warning("Final system checks detected issues.")
                self.success = False
        except Exception as e:
            logger.error(f"Final checks error: {e}")
            self.success = False
            final_result = False

        try:
            if not run_with_progress(
                "Cleaning up system",
                self.final_checker.cleanup_system,
            ):
                logger.warning("System cleanup had issues.")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

        # Calculate total duration
        duration = time.time() - self.start_time
        minutes, seconds = divmod(duration, 60)

        # Final status update
        if self.success and final_result:
            SETUP_STATUS["final"] = {
                "status": "success",
                "message": f"Completed in {int(minutes)}m {int(seconds)}s.",
            }
        else:
            SETUP_STATUS["final"] = {
                "status": "failed",
                "message": f"Completed with issues in {int(minutes)}m {int(seconds)}s.",
            }

        # Show status report
        status_report()

        # Reboot if successful
        if self.success and final_result:
            self.final_checker.auto_reboot()
        else:
            print_warning(
                "Setup completed with issues. Please review the log and status report."
            )
            print_message(f"Log file: {AppConfig.LOG_FILE}", NordColors.FROST_2)

        return 0 if self.success and final_result else 1


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> int:
    """
    Main entry point for the Debian Trixie Setup Utility.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Clear screen for better readability
        os.system("clear")

        # Show welcome banner
        console.print(create_header())

        # Show initial information
        print_step(
            f"Starting Debian Trixie Setup & Hardening Utility v{AppConfig.VERSION}"
        )
        print_step(f"System: {platform.system()} {platform.release()}")
        print_step(f"Hostname: {AppConfig.HOSTNAME}")

        # Check if running as root
        if os.geteuid() != 0:
            print_error("This script must be run with root privileges!")
            print_message("Run with: sudo ./debian_setup.py", NordColors.YELLOW)
            return 1

        # Run the setup
        return DebianServerSetup().run()

    except KeyboardInterrupt:
        print_warning("Process interrupted by user")
        return 130

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        return 1


if __name__ == "__main__":
    sys.exit(main())
