#!/usr/bin/env python3
"""
Debian Trixie Server Setup & Hardening Utility (Unattended)
------------------------------------------------------------

This fully automated utility performs comprehensive system setup and hardening on a
Debian Trixie server with zero user interaction. The utility combines robust error
handling with a professional, visually appealing interface.

Features:
  • Fully unattended operation – zero user interaction required
  • Complete system setup and security hardening including firewall, SSH, and more
  • Professional Nord-themed terminal interface with gradient-styled Pyfiglet banners
  • Real-time operation status with dynamic progress tracking and spinners
  • Comprehensive error handling with detailed logging and recovery mechanisms
  • Self-healing package management with automatic retry strategies
  • Graceful termination handling for unattended environments
  • Detailed final system health assessment with visual reporting

Requires root privileges.
Version: 1.2.0
"""

# ----------------------------------------------------------------
# Dependency Installation and Bootstrap
# ----------------------------------------------------------------
import os
import sys
import subprocess
import tempfile
import time
import datetime
import shutil
import platform
import socket
import json
import re
import logging
import tarfile
import gzip
import filecmp
import atexit
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable


def print_status(message: str, status: str = "INFO") -> None:
    """
    Print a timestamped status message with colored output.

    Args:
        message: The status message to display.
        status: One of "INFO", "SUCCESS", "WARNING", or "ERROR".
    """
    colors = {
        "INFO": "\033[94m",  # Blue
        "SUCCESS": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "RESET": "\033[0m",  # Reset
    }
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(
        f"{timestamp} {colors.get(status, colors['INFO'])}{status}{colors['RESET']}: {message}"
    )


def check_root() -> None:
    """
    Verify that the script is running with root privileges.
    Exits with an error message if not.
    """
    if os.geteuid() != 0:
        print_status("This script must be run with root privileges!", "ERROR")
        print_status("Run with: sudo ./debian_setup.py", "WARNING")
        sys.exit(1)
    print_status("Root privileges confirmed.", "SUCCESS")


def install_nala() -> bool:
    """
    Install Nala package manager with robust error handling and fallbacks.
    This is a critical first step for the setup process.

    Returns:
        bool: True if installation succeeded, False otherwise
    """
    print_status("Installing Nala package manager...")

    # Check if nala is already installed
    try:
        subprocess.run(["which", "nala"], check=True, capture_output=True)
        print_status("Nala is already installed.", "SUCCESS")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_status("Nala not found, installing...", "INFO")

    # Try different installation methods
    methods = [
        # Method 1: Standard APT install with cleanup first
        lambda: (
            subprocess.run(
                ["apt-get", "update", "-qq"], check=False, stderr=subprocess.DEVNULL
            ),
            subprocess.run(["apt-get", "clean"], check=False),
            subprocess.run(["apt-get", "install", "-y", "nala"], check=True),
        ),
        # Method 2: Try with minimal dependencies
        lambda: (
            subprocess.run(
                ["apt-get", "install", "-y", "--no-install-recommends", "nala"],
                check=True,
            )
        ),
        # Method 3: Direct download from Debian repos
        lambda: download_and_install_nala(),
    ]

    # Try each method until one succeeds
    for i, method in enumerate(methods, 1):
        try:
            print_status(f"Trying Nala installation method {i}...")
            method()

            # Verify installation
            try:
                subprocess.run(["nala", "--version"], check=True, capture_output=True)
                print_status(f"Successfully installed Nala using method {i}", "SUCCESS")
                return True
            except (subprocess.SubprocessError, FileNotFoundError):
                print_status(
                    f"Nala verification failed after installation attempt {i}",
                    "WARNING",
                )
                continue

        except Exception as e:
            print_status(f"Nala installation method {i} failed: {e}", "WARNING")

    print_status("Failed to install Nala after trying all methods", "WARNING")
    print_status("Will use apt instead of nala for package operations", "INFO")
    return False


def download_and_install_nala() -> bool:
    """
    Download and install Nala package directly.

    Returns:
        bool: True if installation succeeded, False otherwise
    """
    temp_dir = tempfile.mkdtemp(prefix="nala_install_")
    temp_deb = os.path.join(temp_dir, "nala.deb")

    try:
        # Try multiple download URLs for redundancy
        urls = [
            "http://ftp.us.debian.org/debian/pool/main/n/nala/nala_0.14.0_all.deb",
            "http://deb.debian.org/debian/pool/main/n/nala/nala_0.14.0_all.deb",
            "http://cdn.debian.net/debian/pool/main/n/nala/nala_0.14.0_all.deb",
        ]

        download_success = False
        for url in urls:
            try:
                print_status(f"Downloading Nala from {url}...")
                subprocess.run(
                    ["wget", "-q", url, "-O", temp_deb], check=True, timeout=30
                )
                if os.path.exists(temp_deb) and os.path.getsize(temp_deb) > 0:
                    download_success = True
                    break
            except Exception as e:
                print_status(f"Download from {url} failed: {e}", "WARNING")

        if not download_success:
            raise Exception("Failed to download Nala package from any source")

        # Install dependencies
        print_status("Installing required dependencies...")
        subprocess.run(
            [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "python3-apt",
                "python3-debian",
                "apt-utils",
                "python3",
            ],
            check=True,
        )

        # Install the package
        print_status("Installing Nala package...")
        subprocess.run(["dpkg", "-i", temp_deb], check=True)

        # Fix dependencies if needed
        subprocess.run(["apt-get", "install", "-f", "-y"], check=True)

        return True

    except Exception as e:
        print_status(f"Direct Nala installation failed: {e}", "ERROR")
        return False
    finally:
        # Clean up
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def install_dependencies() -> bool:
    """
    Install essential system and Python packages required to run the script.

    Returns:
        bool: True if the installation was successful, False otherwise.
    """
    print_status("Installing required dependencies...")

    # Get apt command - prefer nala if available
    apt_cmd = "nala" if os.path.exists("/usr/bin/nala") else "apt-get"

    # First try to update package lists
    try:
        subprocess.run([apt_cmd, "update", "-qq"], check=False)
    except Exception as e:
        print_status(f"Warning: {apt_cmd} update failed: {e}", "WARNING")

    # Install essential system packages
    essential_packages = [
        "python3-pip",
        "python3-venv",
        "python3-dev",
        "wget",
        "curl",
        "git",
    ]

    try:
        print_status(
            f"Installing essential system packages: {', '.join(essential_packages)}"
        )
        subprocess.run(
            [apt_cmd, "install", "-y", "--no-install-recommends"] + essential_packages,
            check=False,
        )
    except Exception as e:
        print_status(
            f"Warning: Some essential packages may not have installed: {e}", "WARNING"
        )

    # Install Python dependencies
    print_status("Installing required Python packages...")

    # Try multiple installation methods for rich and pyfiglet
    methods = [
        # Method 1: System packages
        lambda: subprocess.run(
            [apt_cmd, "install", "-y", "python3-rich", "python3-pyfiglet"],
            check=False,
        ),
        # Method 2: Pip install
        lambda: subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--break-system-packages",
                "rich>=13.0.0",
                "pyfiglet",
            ],
            check=False,
        ),
        # Method 3: Try direct pip with options
        lambda: subprocess.run(
            ["pip3", "install", "--break-system-packages", "rich>=13.0.0", "pyfiglet"],
            check=False,
        ),
        # Method 4: Virtual environment
        lambda: setup_venv_and_install(),
    ]

    # Try each installation method until one succeeds
    for i, method in enumerate(methods, 1):
        print_status(f"Trying installation method {i}...")
        try:
            method()
            # Check if packages are now importable
            try:
                # Use a subprocess to check if the imports work
                check_imports = (
                    "import rich, pyfiglet; "
                    "print('Rich version:', rich.__version__); "
                    "print('Successfully imported dependencies')"
                )
                result = subprocess.run(
                    [sys.executable, "-c", check_imports],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                if result.returncode == 0:
                    print_status(
                        f"Successfully installed dependencies using method {i}",
                        "SUCCESS",
                    )
                    return True
                else:
                    print_status(
                        f"Installation method {i} didn't make packages importable",
                        "WARNING",
                    )
            except Exception as e:
                print_status(f"Import verification failed: {e}", "WARNING")
        except Exception as e:
            print_status(f"Installation method {i} failed: {e}", "WARNING")

    print_status(
        "Failed to install required dependencies after trying all methods", "ERROR"
    )
    return False


def setup_venv_and_install() -> bool:
    """
    Set up a virtual environment and install dependencies in it.

    Returns:
        bool: True if successful, False otherwise
    """
    venv_dir = os.path.join(tempfile.gettempdir(), "debian_setup_venv")

    try:
        os.makedirs(venv_dir, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)

        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_pip = os.path.join(venv_dir, "bin", "pip")

        subprocess.run([venv_pip, "install", "--upgrade", "pip"], check=True)

        subprocess.run([venv_pip, "install", "rich>=13.0.0", "pyfiglet"], check=True)

        # Add to Python path
        site_packages = subprocess.check_output(
            [venv_python, "-c", "import site; print(site.getsitepackages()[0])"],
            text=True,
        ).strip()

        if site_packages not in sys.path:
            sys.path.insert(0, site_packages)
            print_status(
                f"Added virtual environment site-packages to PYTHONPATH: {site_packages}",
                "INFO",
            )

        return True

    except Exception as e:
        print_status(f"Virtual environment setup failed: {e}", "WARNING")
        return False


def bootstrap() -> None:
    """
    Perform initial bootstrapping before running the main script.
    Exits if critical dependencies can't be installed.
    """
    check_root()

    # First install Nala if possible
    install_nala()

    if not install_dependencies():
        print_status("Failed to install all required dependencies", "ERROR")
        print_status("This script requires 'rich' and 'pyfiglet' packages", "ERROR")
        print_status("Please install them manually before running the script", "ERROR")
        sys.exit(1)

    print_status("Bootstrap completed successfully", "SUCCESS")


# Run bootstrap before importing any non-standard libraries
bootstrap()

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------

# Standard library imports
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

# Third-party imports
try:
    import pyfiglet
    from rich.align import Align
    from rich.box import ROUNDED, HEAVY, DOUBLE
    from rich.console import Console, Group
    from rich.live import Live
    from rich.layout import Layout
    from rich.logging import RichHandler
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
    from rich.prompt import Confirm
    from rich.style import Style
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print_status("Critical libraries not found. Bootstrapping failed.", "ERROR")
    sys.exit(1)

# Install Rich traceback handler for better error display
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
@dataclass
class AppConfig:
    """Global application configuration."""

    # Application info
    VERSION: str = "1.2.0"
    APP_NAME: str = "Debian Trixie Setup"
    APP_SUBTITLE: str = "Server Setup & Hardening Utility"

    # System info
    PLATFORM: str = platform.system().lower()
    IS_WINDOWS: bool = PLATFORM == "windows"
    IS_MACOS: bool = PLATFORM == "darwin"
    IS_LINUX: bool = PLATFORM == "linux"
    HOSTNAME: str = socket.gethostname()

    # Debian-specific settings
    DEBIAN_VERSION: str = "trixie"
    DEBIAN_CODENAME: str = "trixie"  # Debian 13 codename
    DEBIAN_MIRROR: str = "deb.debian.org"
    DEBIAN_CDN: str = f"https://{DEBIAN_MIRROR}/debian"

    # Paths and files
    LOG_FILE: str = "/var/log/debian_setup.log"
    MAX_LOG_SIZE: int = 10 * 1024 * 1024  # 10MB
    USERNAME: str = "sawyer"
    USER_HOME: str = f"/home/{USERNAME}"
    BACKUP_DIR: str = "/var/backups/debian_setup"
    TEMP_DIR: str = tempfile.gettempdir()

    # Terminal dimensions
    TERM_WIDTH: int = shutil.get_terminal_size().columns
    TERM_HEIGHT: int = shutil.get_terminal_size().lines
    PROGRESS_WIDTH: int = min(50, TERM_WIDTH - 30)

    # Security settings
    ALLOWED_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443", "32400"]
    )

    # Configuration files to manage
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

    # Operation settings
    COMMAND_TIMEOUT: int = 300  # seconds
    MAX_RETRIES: int = 3
    MAX_WORKERS: int = max(2, min(os.cpu_count() or 4, 8))

    @classmethod
    def update_terminal_size(cls) -> None:
        """Update terminal size information dynamically."""
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
    """Nord color palette for consistent theming throughout the application."""

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

    @classmethod
    def get_frost_gradient(cls, text_lines: List[str]) -> List[Tuple[str, str]]:
        """
        Create a gradient using Frost colors.

        Args:
            text_lines: List of text lines to apply gradient to

        Returns:
            List of (text, color) tuples
        """
        colors = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        gradient = []

        for i, line in enumerate(text_lines):
            color = colors[i % len(colors)]
            gradient.append((line, color))

        return gradient


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
            "highlight": f"bold {NordColors.SNOW_STORM_3}",
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


class PermissionError(SetupError):
    """Raised when insufficient permissions are detected."""

    pass


class RecoveryError(SetupError):
    """Raised when recovery from previous error fails."""

    pass


# ----------------------------------------------------------------
# Progress Manager
# ----------------------------------------------------------------
class ProgressManager:
    """
    Singleton manager for progress displays to prevent conflicts.
    Ensures only one progress display is active at a time.
    """

    _instance = None
    _active_progress = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgressManager, cls).__new__(cls)
            cls._instance._active_progress = None
        return cls._instance

    def start_progress(self, progress):
        """
        Start a new progress display and register it with the manager.
        Ensures any existing display is properly closed first.

        Args:
            progress: A Progress object

        Returns:
            The progress object
        """
        # First clean up any existing progress
        self.stop_progress()

        # Store and return the new progress
        self._active_progress = progress
        return progress

    def stop_progress(self):
        """
        Safely stop the current progress display if one exists.
        """
        if self._active_progress is not None:
            try:
                # Check if it has a __exit__ method and hasn't been used as a context manager
                if hasattr(self._active_progress, "__exit__"):
                    self._active_progress.__exit__(None, None, None)
            except Exception:
                # Ignore errors when closing progress displays
                pass
            self._active_progress = None

    def get_active_progress(self):
        """
        Get the currently active progress display.

        Returns:
            The active progress display or None
        """
        return self._active_progress


# Create a global instance of the progress manager
progress_manager = ProgressManager()


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
            console.print(f"Rotated log file to [path]{rotated}[/path]")
        except Exception as e:
            console.print(f"[warning]Failed to rotate log file: {e}[/warning]")

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
    fonts = ["slant", "big", "standard", "digital", "doom", "small"]
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
    border = f"[{NordColors.FROST_3}]{'━' * min(60, adjusted_width - 5)}[/]"
    full_text = f"{border}\n{styled_text}{border}"

    # Create panel with title and subtitle
    return Panel(
        Text.from_markup(full_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        box=ROUNDED,
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
    Print a section header using Pyfiglet small font with decorative elements.

    Args:
        title: The section title to display
    """
    console.print()

    try:
        # First try with Pyfiglet
        section_art = pyfiglet.figlet_format(title, font="small")
        console.print(section_art, style=f"bold {NordColors.FROST_2}")
    except Exception:
        # Fallback if Pyfiglet fails
        console.print(f"[bold {NordColors.FROST_1}]== {title.upper()} ==[/]")

    # Add decorative separator with Nord styling
    separator = "─" * 60
    console.print(f"[{NordColors.FROST_3}]{separator}[/]")

    # Log the section for the log file
    logger.info(f"--- {title} ---")


def status_report() -> None:
    """Display a table reporting the status of all setup tasks with rich formatting."""
    print_section("Setup Status Report")

    # Status icons
    icons = {"success": "✓", "failed": "✗", "pending": "?", "in_progress": "⋯"}

    # Create table with Nord styling
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        box=ROUNDED,
        title=f"[bold {NordColors.FROST_2}]Debian Trixie Setup Status[/]",
        title_justify="center",
        expand=True,
    )

    # Define columns
    table.add_column("Task", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=f"bold {NordColors.FROST_3}", justify="center")
    table.add_column("Message", style=f"{NordColors.SNOW_STORM_1}", ratio=3)

    # Count statuses for summary
    status_counts = {"success": 0, "failed": 0, "pending": 0, "in_progress": 0}

    # Add rows for each task
    for task, data in SETUP_STATUS.items():
        st = data["status"]
        msg = data["message"]
        icon = icons.get(st, "?")
        status_counts[st] = status_counts.get(st, 0) + 1

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

    # Create summary panel
    summary = Text()
    summary.append("Status Summary: ", style=f"bold {NordColors.FROST_3}")
    summary.append(
        f"{status_counts['success']} Succeeded", style=f"bold {NordColors.GREEN}"
    )
    summary.append(" | ")
    summary.append(f"{status_counts['failed']} Failed", style=f"bold {NordColors.RED}")
    summary.append(" | ")
    summary.append(
        f"{status_counts['in_progress']} In Progress", style=f"bold {NordColors.YELLOW}"
    )
    summary.append(" | ")
    summary.append(
        f"{status_counts['pending']} Pending", style=f"bold {NordColors.POLAR_NIGHT_4}"
    )

    # Display table and summary
    console.print(
        Panel(
            Group(table, Align.center(summary)),
            border_style=Style(color=NordColors.FROST_4),
            padding=(0, 1),
            box=ROUNDED,
        )
    )


# ----------------------------------------------------------------
# Command Execution Helpers
# ----------------------------------------------------------------
def run_command(
    cmd: Union[List[str], str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = AppConfig.COMMAND_TIMEOUT,
    verbose: bool = False,
    retry: int = 1,
    use_nala: bool = True,
) -> subprocess.CompletedProcess:
    """
    Execute a system command with robust error handling and automatic retries.
    Automatically uses nala instead of apt when appropriate.

    Args:
        cmd: Command to execute (list or string)
        env: Environment variables
        check: Whether to raise an exception on non-zero exit
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print the command being executed
        retry: Number of retry attempts for transient failures
        use_nala: Whether to replace apt commands with nala when available

    Returns:
        subprocess.CompletedProcess object

    Raises:
        ExecutionError: If command execution fails after all retries
    """
    # Replace apt with nala if requested and available
    if use_nala and shutil.which("nala") is not None:
        if isinstance(cmd, list) and len(cmd) > 0:
            if cmd[0] in ["apt", "apt-get"]:
                # Special case handling
                if len(cmd) > 1 and cmd[1] in ["update", "clean", "autoclean"]:
                    # For these commands, just replace the command name
                    cmd_copy = cmd.copy()
                    cmd_copy[0] = "nala"
                    cmd = cmd_copy
                    logger.debug(f"Using nala for apt command: {' '.join(cmd)}")
                else:
                    # For other apt commands
                    cmd_copy = cmd.copy()
                    cmd_copy[0] = "nala"
                    cmd = cmd_copy
                    logger.debug(f"Using nala instead of apt: {' '.join(cmd)}")
        elif isinstance(cmd, str):
            # For string commands, do simple replacements
            cmd = cmd.replace("apt-get ", "nala ").replace("apt ", "nala ")
            logger.debug(f"Using nala in command string: {cmd}")

    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logger.debug(f"Executing: {cmd_str}")

    if verbose:
        # Truncate very long commands in display, but show full command in log
        display_cmd = cmd_str[:80] + ("..." if len(cmd_str) > 80 else "")
        print_step(f"Executing: {display_cmd}")

    # Initialize retry counter and result
    attempts = 0
    result = None

    while attempts < retry:
        attempts += 1
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

            # If we get here without an exception, command succeeded
            if attempts > 1:
                logger.info(f"Command succeeded on attempt {attempts}")

            if verbose and result.stdout and len(result.stdout) > 0:
                console.print(f"[dim]{result.stdout.strip()}[/dim]")

            return result

        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed (code {e.returncode}): {cmd_str}"
            if e.stdout:
                error_msg += f"\nOutput: {e.stdout.strip()}"
            if e.stderr:
                error_msg += f"\nError: {e.stderr.strip()}"

            if attempts < retry:
                logger.warning(f"{error_msg}. Retrying ({attempts}/{retry})...")
                time.sleep(1)  # Brief pause before retry
                continue
            else:
                logger.error(f"{error_msg}. All {retry} attempts failed.")
                if check:
                    raise ExecutionError(error_msg)
                return e

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {timeout} seconds: {cmd_str}"
            if attempts < retry:
                logger.warning(f"{error_msg}. Retrying ({attempts}/{retry})...")
                continue
            else:
                logger.error(f"{error_msg}. All {retry} attempts failed.")
                raise ExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Error executing command: {cmd_str}: {str(e)}"
            if attempts < retry:
                logger.warning(f"{error_msg}. Retrying ({attempts}/{retry})...")
                continue
            else:
                logger.error(f"{error_msg}. All {retry} attempts failed.")
                raise ExecutionError(error_msg)


def run_with_progress(
    desc: str, func: Callable, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """
    Run a function with a Rich progress indicator and status tracking.
    Uses the progress manager to prevent display conflicts.

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

    # Get the progress manager to handle display conflicts
    progress_mgr = progress_manager

    # Stop any active progress displays
    progress_mgr.stop_progress()

    # Create a new progress display
    progress = Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(
            bar_width=AppConfig.PROGRESS_WIDTH,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    # Register with the manager and start display
    progress.__enter__()
    progress_mgr.start_progress(progress)

    # Create an indeterminate progress task
    task_id = progress.add_task(desc, total=None)
    start = time.time()

    try:
        # Run function directly (no threading to avoid conflicts)
        result = func(*args, **kwargs)

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
    finally:
        # Ensure progress display is properly closed
        progress_mgr.stop_progress()


def run_with_detailed_progress(
    desc: str,
    func: Callable,
    total: int,
    *args,
    task_name: Optional[str] = None,
    **kwargs,
) -> Any:
    """
    Run a function with a detailed progress bar showing completion percentage.
    Uses the progress manager to prevent display conflicts.

    Args:
        desc: Description of the task
        func: Function to run with task_id and progress parameters
        total: Total number of steps
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

    # Get the progress manager to handle display conflicts
    progress_mgr = progress_manager

    # Stop any active progress displays
    progress_mgr.stop_progress()

    # Create a new progress display with percentage
    progress = Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(
            bar_width=AppConfig.PROGRESS_WIDTH,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    )

    # Register with the manager and start display
    progress.__enter__()
    progress_mgr.start_progress(progress)

    # Create a determinate progress task
    task_id = progress.add_task(desc, total=total)
    start = time.time()

    try:
        # Add progress to kwargs to be used by the function
        kwargs["task_id"] = task_id
        kwargs["progress"] = progress

        # Run function directly (no threading to avoid conflicts)
        result = func(*args, **kwargs)

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
    finally:
        # Ensure progress display is properly closed
        progress_mgr.stop_progress()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit with proper resource management."""
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

    # Ensure any active progress displays are stopped
    progress_manager.stop_progress()

    # Display final status report
    try:
        status_report()
    except Exception as e:
        logger.error(f"Error generating final status report: {e}")

    # Final log message
    logger.info("Cleanup complete. Exiting.")

    # Print goodbye message
    try:
        console.print()
        console.print(
            Panel(
                Text(
                    f"Debian Trixie Setup completed. See {AppConfig.LOG_FILE} for details.",
                    style=f"bold {NordColors.FROST_2}",
                ),
                border_style=Style(color=NordColors.FROST_1),
                box=ROUNDED,
                padding=(1, 2),
            )
        )
    except Exception:
        pass


def signal_handler(signum: int, frame: Optional[Any]) -> None:
    """
    Gracefully handle termination signals with proper resource cleanup.

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

    console.print()
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    logger.error(f"Interrupted by {sig_name}. Exiting.")

    # Stop any active progress displays
    progress_manager.stop_progress()

    # Perform cleanup
    cleanup()

    # Exit with signal-specific code
    sys.exit(128 + signum)


# Register signal handlers for common termination signals
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

    @staticmethod
    def retry_operation(
        operation: Callable,
        max_attempts: int = AppConfig.MAX_RETRIES,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True,
        operation_name: str = "Operation",
    ) -> Any:
        """
        Retry an operation with exponential backoff.

        Args:
            operation: Function to retry
            max_attempts: Maximum number of attempts
            retry_delay: Initial delay between retries in seconds
            exponential_backoff: Whether to increase delay exponentially
            operation_name: Name of the operation for logging

        Returns:
            Result of the operation if successful

        Raises:
            Exception: The last exception raised by the operation after all retries
        """
        attempt = 0
        last_exception = None

        while attempt < max_attempts:
            try:
                return operation()
            except Exception as e:
                attempt += 1
                last_exception = e

                if attempt < max_attempts:
                    delay = retry_delay
                    if exponential_backoff:
                        delay = retry_delay * (2 ** (attempt - 1))

                    logger.warning(
                        f"{operation_name} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"{operation_name} failed after {max_attempts} attempts: {e}"
                    )

        if last_exception:
            raise last_exception

        # This should never happen if max_attempts > 0
        raise ValueError(f"{operation_name} failed without an exception")


# ----------------------------------------------------------------
# Preflight & Environment Checkers
# ----------------------------------------------------------------
class PreflightChecker:
    """Preflight checks to ensure system is ready for setup."""

    def check_root(self) -> None:
        """
        Ensure the script runs as root.

        Raises:
            PermissionError: If not running as root
        """
        if os.geteuid() != 0:
            print_error("This script must run with root privileges!")
            logger.error("Not running as root. Exiting.")
            raise PermissionError("This script must run with root privileges")
        logger.info("Root privileges confirmed.")

    def check_network(self) -> bool:
        """
        Check for network connectivity using multiple hosts for redundancy.

        Returns:
            True if network is available, False otherwise
        """
        logger.info("Checking network connectivity...")

        # Try multiple hosts for redundancy
        test_hosts = [
            "google.com",
            "cloudflare.com",
            "1.1.1.1",
            "deb.debian.org",
            "8.8.8.8",
        ]

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display for network checking
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Checking network connectivity..."),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Checking...", total=len(test_hosts))

            for host in test_hosts:
                try:
                    progress.update(task, description=f"Pinging {host}...")
                    # Use ICMP ping or simple TCP socket connection based on platform
                    if Utils.command_exists("ping"):
                        ping_cmd = ["ping", "-c", "1", "-W", "5", host]
                        result = subprocess.run(
                            ping_cmd, check=False, capture_output=True, timeout=6
                        )
                        if result.returncode == 0:
                            logger.info(f"Network connectivity confirmed via {host}.")
                            progress.update(task, completed=len(test_hosts))
                            return True
                    else:
                        # Fall back to socket connection
                        try:
                            socket.create_connection((host, 80), timeout=5)
                            logger.info(f"Network connectivity confirmed via {host}.")
                            progress.update(task, completed=len(test_hosts))
                            return True
                        except (socket.timeout, socket.error):
                            pass

                    progress.advance(task)
                except Exception as e:
                    logger.debug(f"Ping to {host} failed: {e}")
                    progress.advance(task)

            logger.error("Network check failed - could not reach any test hosts.")
            return False
        finally:
            # Ensure progress display is properly closed
            progress_mgr.stop_progress()

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        """
        Check if the system is running Debian and identify version.

        Returns:
            Tuple of (os_id, version) if Debian, None otherwise
        """
        logger.info("Checking OS version...")

        if not os.path.isfile("/etc/os-release"):
            logger.warning("Missing /etc/os-release file.")
            return None

        os_info = {}
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        os_info[k] = v.strip('"')

            logger.info(
                f"Detected OS: {os_info.get('ID', 'unknown')} {os_info.get('VERSION_ID', 'unknown')}"
            )

            if os_info.get("ID") != "debian":
                logger.warning(
                    f"Non-Debian system detected: {os_info.get('ID', 'unknown')}."
                )
                return None

            ver = os_info.get("VERSION_ID", "")
            logger.info(f"Detected Debian version: {ver}")

            return ("debian", ver)
        except Exception as e:
            logger.error(f"Failed to determine OS version: {e}")
            return None

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

    def verify_system_requirements(self) -> bool:
        """
        Verify the system meets minimum requirements for setup.

        Returns:
            True if system meets requirements, False otherwise
        """
        logger.info("Verifying system requirements...")
        requirements_met = True

        # Check disk space
        try:
            stat = os.statvfs("/")
            free_space_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)

            if free_space_mb < 2000:  # 2GB minimum
                logger.warning(
                    f"Low disk space: {free_space_mb:.1f} MB available, 2000 MB recommended"
                )
                requirements_met = False
            else:
                logger.info(f"Disk space: {free_space_mb:.1f} MB available")
        except Exception as e:
            logger.warning(f"Could not check disk space: {e}")

        # Check memory
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        mem_kb = int(line.split()[1])
                        mem_mb = mem_kb / 1024

                        if mem_mb < 1024:  # 1GB minimum
                            logger.warning(
                                f"Low memory: {mem_mb:.1f} MB available, 1024 MB recommended"
                            )
                            requirements_met = False
                        else:
                            logger.info(f"Memory: {mem_mb:.1f} MB available")
                        break
        except Exception as e:
            logger.warning(f"Could not check memory: {e}")

        # Check for essential commands
        essential_commands = ["apt-get", "dpkg", "systemctl"]
        missing_commands = []

        for cmd in essential_commands:
            if not Utils.command_exists(cmd):
                missing_commands.append(cmd)

        if missing_commands:
            logger.warning(f"Missing essential commands: {', '.join(missing_commands)}")
            requirements_met = False
        else:
            logger.info("All essential commands are available")

        return requirements_met


# ----------------------------------------------------------------
# APT Repository Manager
# ----------------------------------------------------------------
class APTSourcesManager:
    """Manages APT repository sources with robust error handling."""

    def __init__(self) -> None:
        """Initialize APT sources manager."""
        self.sources_list = "/etc/apt/sources.list"
        self.sources_dir = "/etc/apt/sources.list.d"
        self.backup_created = False

    def backup_sources(self) -> bool:
        """
        Backup existing APT sources.

        Returns:
            bool: True if backup successful, False otherwise
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
        Configure APT to use the Debian CDN repositories with error handling.

        Returns:
            bool: True if successful, False otherwise
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
    """Handles system updates and package installation with retries and progress tracking."""

    def fix_package_issues(self) -> bool:
        """
        Fix common package management issues with progress indication.

        Returns:
            bool: True if issues fixed, False otherwise
        """
        logger.info("Fixing package issues...")

        # Get the package manager command
        apt_cmd = Utils.get_apt_command()

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Fixing package issues...", total=None)

            # Try to fix any broken/interrupted package installations
            progress.update(task, description="Configuring pending packages...")
            run_command(["dpkg", "--configure", "-a"])

            # Check for held packages
            progress.update(task, description="Checking for held packages...")
            held = run_command(["apt-mark", "showhold"], capture_output=True)
            if held.stdout.strip():
                logger.warning(f"Found held packages: {held.stdout.strip()}")
                for pkg in held.stdout.strip().splitlines():
                    if pkg.strip():
                        progress.update(
                            task, description=f"Releasing hold on {pkg.strip()}..."
                        )
                        run_command(["apt-mark", "unhold", pkg.strip()], check=False)

            # Attempt package repairs
            progress.update(task, description="Running package repairs...")
            run_command([apt_cmd, "install", "-y", "-f"])
            run_command([apt_cmd, "clean"])
            run_command([apt_cmd, "autoclean", "-y"])

            # Verify package system integrity
            progress.update(task, description="Checking package system integrity...")
            check = run_command(["apt-get", "check"], capture_output=True)
            if check.returncode != 0:
                logger.error("Package system issues remain unresolved.")
                return False

            logger.info("Package issues fixed successfully.")
            return True

        except Exception as e:
            logger.error(f"Error fixing packages: {e}")
            return False
        finally:
            # Ensure progress display is properly closed
            progress_mgr.stop_progress()

    def update_system(self, full_upgrade: bool = False) -> bool:
        """
        Update system packages with visual progress indicators.

        Args:
            full_upgrade: Whether to perform a full upgrade

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Updating system packages...")

        # Get the package manager command
        apt_cmd = Utils.get_apt_command()

        try:
            # First fix any existing package issues
            if not self.fix_package_issues():
                logger.warning(
                    "Proceeding with updates despite unresolved package issues."
                )

            # Get the progress manager
            progress_mgr = progress_manager

            # Stop any active progress displays
            progress_mgr.stop_progress()

            # Create a new progress display
            progress = Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
                BarColumn(
                    bar_width=AppConfig.PROGRESS_WIDTH,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TextColumn(
                    f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"
                ),
                TimeElapsedColumn(),
                console=console,
            )

            # Register with the manager and start display
            progress.__enter__()
            progress_mgr.start_progress(progress)

            try:
                update_task = progress.add_task("Updating package lists...", total=100)

                # Update package lists
                try:
                    progress.update(update_task, advance=25)
                    run_command([apt_cmd, "update"])
                except Exception as e:
                    logger.warning(
                        f"Update failed with {apt_cmd}: {e}; attempting apt update"
                    )
                    progress.update(update_task, advance=25)
                    run_command(["apt", "update"])

                progress.update(update_task, completed=100)

                # Perform upgrade
                upgrade_task = progress.add_task("Upgrading packages...", total=100)

                upgrade_cmd = []
                if apt_cmd == "nala":
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
                    # Update progress as we go
                    progress.update(
                        upgrade_task,
                        advance=30,
                        description="Starting package upgrade...",
                    )
                    run_command(upgrade_cmd)
                    progress.update(
                        upgrade_task,
                        advance=60,
                        description="Package upgrade completed",
                    )

                except Exception as e:
                    logger.warning(
                        f"Upgrade failed with {upgrade_cmd[0]}: {e}. Trying apt..."
                    )
                    alt_cmd = (
                        ["apt", "full-upgrade", "-y"]
                        if full_upgrade
                        else ["apt", "upgrade", "-y"]
                    )
                    progress.update(
                        upgrade_task, advance=30, description="Retrying with apt..."
                    )
                    run_command(alt_cmd)
                    progress.update(
                        upgrade_task,
                        advance=30,
                        description="Package upgrade completed",
                    )

                progress.update(upgrade_task, completed=100)

                logger.info("System update completed successfully.")
                return True

            finally:
                # Ensure progress display is properly closed
                progress_mgr.stop_progress()

        except Exception as e:
            logger.error(f"System update error: {e}")
            return False

    def install_packages(
        self,
        packages: Optional[List[str]] = None,
        task_id: Optional[int] = None,
        progress: Optional[Progress] = None,
    ) -> bool:
        """
        Install missing packages from the given list with visual progress tracking.

        Args:
            packages: List of packages to install (defaults to PACKAGES)
            task_id: Progress task ID if called from run_with_detailed_progress
            progress: Progress instance if called from run_with_detailed_progress

        Returns:
            bool: True if successful, False otherwise
        """
        # Get the package manager command
        apt_cmd = Utils.get_apt_command()

        # Use default package list if none provided
        packages = packages or PACKAGES
        logger.info(f"Checking {len(packages)} packages for installation...")

        # Fix package issues first
        if not self.fix_package_issues():
            logger.warning("Proceeding with installations despite package issues.")

        # Find missing packages
        missing = []
        package_check_count = 0

        # Use provided progress if available, otherwise create our own
        if not (progress and task_id):
            # Create a new progress display for package checking
            progress_mgr = progress_manager
            progress_mgr.stop_progress()

            check_progress = Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Checking package status..."),
                BarColumn(
                    bar_width=AppConfig.PROGRESS_WIDTH,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TextColumn(
                    f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"
                ),
                console=console,
            )

            check_progress.__enter__()
            progress_mgr.start_progress(check_progress)

            check_task = check_progress.add_task(
                "Checking packages...", total=len(packages)
            )

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

                check_progress.update(check_task, advance=1)
                package_check_count += 1

            # Close the check progress
            progress_mgr.stop_progress()

        # If outer progress is provided, update it
        if progress and task_id:
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

                # Calculate progress percentage
                package_check_count += 1
                completed = int(
                    (package_check_count / len(packages)) * 30
                )  # Use 30% of progress bar for checking
                progress.update(task_id, completed=completed)

        # Skip if all packages are already installed
        if not missing:
            logger.info("All packages already installed.")
            if progress and task_id:
                progress.update(
                    task_id, completed=100, description="All packages already installed"
                )
            return True

        logger.info(
            f"Installing {len(missing)} missing packages: {', '.join(missing[:5])}..."
        )
        if len(missing) > 5:
            logger.info(f"... and {len(missing) - 5} more")

        # Use batch installation to reduce failures
        success = True

        # Calculate total batches for progress tracking
        batch_size = 20
        total_batches = (len(missing) + batch_size - 1) // batch_size
        batch_num = 0
        packages_installed = 0

        # Setup installation progress (unless we're using an outer progress)
        install_prog = None

        if not (progress and task_id):
            # Create a new progress display for installation
            progress_mgr = progress_manager
            progress_mgr.stop_progress()

            install_prog = Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
                BarColumn(
                    bar_width=AppConfig.PROGRESS_WIDTH,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
            )

            install_prog.__enter__()
            progress_mgr.start_progress(install_prog)

            install_task = install_prog.add_task(
                "Installing packages...", total=len(missing)
            )
        else:
            # Use the provided progress
            install_task = task_id

        try:
            # Install in smaller batches to prevent failures
            for i in range(0, len(missing), batch_size):
                batch_num += 1
                batch = missing[i : i + batch_size]
                try:
                    batch_desc = f"Installing batch {batch_num}/{total_batches}"
                    logger.info(batch_desc)

                    # Update progress
                    if progress and task_id:
                        # Calculate progress for outer progress
                        outer_completed = 30 + int(
                            (batch_num / total_batches) * 70
                        )  # 30% was for checking, 70% for installation
                        progress.update(
                            task_id, description=batch_desc, completed=outer_completed
                        )
                    elif install_prog:
                        # Update our own progress
                        install_prog.update(
                            install_task, description=batch_desc, advance=len(batch)
                        )

                    run_command(
                        [apt_cmd, "install", "-y", "--no-install-recommends"] + batch,
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
                            packages_installed += 1
                        except subprocess.CalledProcessError:
                            logger.warning(f"Package {pkg} failed to install")
                            success = False
                except Exception as e:
                    logger.warning(f"Batch installation failed: {e}")
                    success = False

                    # Try installing one by one if batch install fails
                    for pkg in batch:
                        try:
                            inner_desc = f"Retrying package {pkg}"
                            if progress and task_id:
                                progress.update(task_id, description=inner_desc)
                            elif install_prog:
                                install_prog.update(
                                    install_task, description=inner_desc
                                )

                            run_command(
                                [
                                    apt_cmd,
                                    "install",
                                    "-y",
                                    "--no-install-recommends",
                                    pkg,
                                ],
                                check=False,
                            )

                            # Verify installation
                            try:
                                subprocess.run(
                                    ["dpkg", "-s", pkg],
                                    check=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                                packages_installed += 1
                            except subprocess.CalledProcessError:
                                pass
                        except Exception as pkg_e:
                            logger.warning(f"Failed to install {pkg}: {pkg_e}")

            # Update progress to 100% if we created it
            if install_prog:
                install_prog.update(
                    install_task,
                    description="Installation completed",
                    completed=len(missing),
                )

            # Update outer progress to 100% if provided
            if progress and task_id:
                progress.update(
                    task_id, description="Package installation completed", completed=100
                )

            # Final report
            logger.info(
                f"Successfully installed {packages_installed} out of {len(missing)} packages"
            )

            # Consider it a success if we installed at least 75% of packages
            if packages_installed >= len(missing) * 0.75:
                return True
            else:
                logger.warning(
                    f"Only {packages_installed}/{len(missing)} packages were installed"
                )
                return success

        finally:
            # Close the progress display if we created it
            if install_prog and not (progress and task_id):
                progress_manager.stop_progress()

    def configure_timezone(self, tz: str = "America/New_York") -> bool:
        """
        Set the system timezone.

        Args:
            tz: Timezone to set

        Returns:
            bool: True if successful, False otherwise
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
            bool: True if successful, False otherwise
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
        Clone or update user repositories with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
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

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=AppConfig.PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Setting up repositories...", total=len(repos))

            # Clone/update each repository
            for repo in repos:
                repo_dir = os.path.join(gh_dir, repo)
                progress.update(task, description=f"Processing {repo} repository...")

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

                progress.advance(task)

            # Fix ownership
            progress.update(task, description="Setting permissions...")
            try:
                run_command(
                    [
                        "chown",
                        "-R",
                        f"{AppConfig.USERNAME}:{AppConfig.USERNAME}",
                        gh_dir,
                    ]
                )
            except Exception as e:
                logger.warning(f"Ownership update failed for {gh_dir}: {e}")
                all_success = False

            return all_success

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def copy_shell_configs(self) -> bool:
        """
        Copy shell configuration files to user and root directories with progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Copying shell configuration files...")

        # Files to copy
        files = [".bashrc", ".profile", ".zshrc", ".bash_aliases"]

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

        # Calculate total operations for progress tracking
        total_operations = sum(
            1
            for file in files
            for _ in dest_dirs
            if os.path.isfile(os.path.join(src_dir, file))
        )

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=AppConfig.PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task(
                "Copying shell configurations...", total=total_operations
            )

            # Copy each file to each destination
            for file in files:
                src = os.path.join(src_dir, file)

                if not os.path.isfile(src):
                    logger.debug(f"Source file {src} not found, skipping.")
                    continue

                for d in dest_dirs:
                    dest = os.path.join(d, file)
                    progress.update(
                        task,
                        description=f"Processing {file} for {os.path.basename(d)}...",
                    )

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

                    progress.advance(task)

            return all_success

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def copy_config_folders(self) -> bool:
        """
        Synchronize configuration folders to the user's .config directory with progress tracking.

        Returns:
            bool: True if successful, False otherwise
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

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task(
                "Synchronizing configuration folders...", total=None
            )

            # Synchronize directories
            progress.update(task, description="Copying configuration files...")
            run_command(["rsync", "-a", "--update", f"{src_dir}/", f"{dest_dir}/"])

            # Fix ownership
            progress.update(task, description="Setting permissions...")
            run_command(
                [
                    "chown",
                    "-R",
                    f"{AppConfig.USERNAME}:{AppConfig.USERNAME}",
                    dest_dir,
                ]
            )

            logger.info(f"Config folders synchronized to {dest_dir}")
            return True

        except Exception as e:
            logger.error(f"Error copying config folders: {e}")
            return False
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def set_default_shell(self) -> bool:
        """
        Set the default shell for the user.

        Returns:
            bool: True if successful, False otherwise
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
    """Implements security hardening measures with progress tracking."""

    def configure_ssh(self, port: int = 22) -> bool:
        """
        Secure and configure the SSH service with detailed progress tracking.

        Args:
            port: SSH port to use

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring SSH service...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring SSH...", total=None)

            # Enable SSH service
            try:
                progress.update(task, description="Enabling SSH service...")
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
            progress.update(task, description="Backing up SSH configuration...")
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
                progress.update(task, description="Updating SSH configuration...")

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
                progress.update(task, description="Restarting SSH service...")
                run_command(["systemctl", "restart", "ssh"])

                # Verify service is running
                result = run_command(
                    ["systemctl", "is-active", "ssh"], capture_output=True
                )
                if result.stdout.strip() == "active":
                    logger.info("SSH service is active after configuration")
                    return True
                else:
                    logger.warning("SSH service is not active after restart")
                    return False
            except Exception as e:
                logger.error(f"Error restarting SSH service: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def setup_sudoers(self) -> bool:
        """
        Configure sudoers for the designated user with proper error handling.

        Returns:
            bool: True if successful, False otherwise
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
        Configure the UFW firewall with allowed ports and detailed progress indicators.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring UFW firewall...")

        # Check if UFW is available
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            logger.warning("UFW not found, attempting to install...")
            if not SystemUpdater().install_packages(["ufw"]):
                return False

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=AppConfig.PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            # Calculate total steps
            total_steps = (
                3 + len(AppConfig.ALLOWED_PORTS) + 2
            )  # reset + policies + ports + logging + enable
            task = progress.add_task("Configuring firewall...", total=total_steps)

            # Reset firewall rules
            try:
                progress.update(task, description="Resetting firewall rules...")
                run_command([ufw_cmd, "reset", "--force"], check=False)
                logger.info("Reset firewall rules")
                progress.advance(task)
            except Exception as e:
                logger.warning(f"UFW reset failed: {e}, continuing anyway...")
                progress.advance(task)

            # Set default policies
            policies = [
                ["default", "deny", "incoming"],
                ["default", "allow", "outgoing"],
            ]

            for i, policy in enumerate(policies):
                try:
                    progress.update(
                        task, description=f"Setting default policy {i + 1}/2..."
                    )
                    run_command([ufw_cmd] + policy)
                    progress.advance(task)
                except Exception as e:
                    logger.warning(f"UFW policy setting failed: {e}")
                    progress.advance(task)

            # Allow specific ports
            for i, port in enumerate(AppConfig.ALLOWED_PORTS):
                try:
                    progress.update(task, description=f"Allowing port {port}...")
                    run_command([ufw_cmd, "allow", f"{port}/tcp"])
                    logger.info(f"Allowed TCP port {port}")
                    progress.advance(task)
                except Exception as e:
                    logger.warning(f"UFW rule addition failed for port {port}: {e}")
                    progress.advance(task)

            # Configure logging and enable firewall
            try:
                progress.update(task, description="Enabling UFW logging...")
                run_command([ufw_cmd, "logging", "on"])
                progress.advance(task)

                progress.update(task, description="Enabling UFW firewall...")
                status = run_command([ufw_cmd, "status"], capture_output=True)
                if "inactive" in status.stdout.lower():
                    run_command([ufw_cmd, "--force", "enable"])
                    logger.info("Enabled UFW firewall")
                progress.advance(task)

                # Configure service to start at boot
                run_command(["systemctl", "enable", "ufw"])
                run_command(["systemctl", "restart", "ufw"])

                # Verify firewall is active
                result = run_command(
                    ["systemctl", "is-active", "ufw"], capture_output=True
                )
                if "active" in result.stdout:
                    logger.info("UFW firewall configured and active")
                    return True
                else:
                    logger.warning("UFW service is not active after configuration")
                    return False

            except Exception as e:
                logger.error(f"UFW service configuration failed: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def configure_fail2ban(self) -> bool:
        """
        Configure Fail2ban service to protect SSH with detailed progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring Fail2ban...")

        # Check if Fail2ban is installed
        if not Utils.command_exists("fail2ban-server"):
            logger.warning("Fail2ban not found, attempting to install...")
            if not SystemUpdater().install_packages(["fail2ban"]):
                return False

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring Fail2ban...", total=None)

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
                progress.update(
                    task, description="Backing up existing configuration..."
                )
                Utils.backup_file(jail)

            # Write configuration
            progress.update(task, description="Writing Fail2ban configuration...")
            with open(jail, "w") as f:
                f.write(config)

            # Enable and start Fail2ban
            progress.update(task, description="Enabling Fail2ban service...")
            run_command(["systemctl", "enable", "fail2ban"])

            progress.update(task, description="Starting Fail2ban service...")
            run_command(["systemctl", "restart", "fail2ban"])

            # Verify service is active
            progress.update(task, description="Verifying Fail2ban service...")
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def configure_apparmor(self) -> bool:
        """
        Configure AppArmor for additional system security.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring AppArmor...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring AppArmor...", total=None)

            # Install AppArmor if missing
            progress.update(task, description="Installing AppArmor packages...")
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
                return False

            # Enable and start AppArmor
            progress.update(task, description="Enabling AppArmor service...")
            run_command(["systemctl", "enable", "apparmor"])

            progress.update(task, description="Starting AppArmor service...")
            run_command(["systemctl", "start", "apparmor"])

            # Verify service is active
            progress.update(task, description="Verifying AppArmor service...")
            status = run_command(
                ["systemctl", "is-active", "apparmor"], capture_output=True
            )

            if status.stdout.strip() == "active":
                # Update profiles if possible
                if Utils.command_exists("aa-update-profiles"):
                    try:
                        progress.update(
                            task, description="Updating AppArmor profiles..."
                        )
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()


# ----------------------------------------------------------------
# Service Installation and Configuration
# ----------------------------------------------------------------
class ServiceInstaller:
    """Installs and configures system services with progress visualization."""

    def install_fastfetch(self) -> bool:
        """
        Install the Fastfetch system information tool.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Installing Fastfetch...")

        # Skip if already installed
        if Utils.command_exists("fastfetch"):
            logger.info("Fastfetch is already installed.")
            return True

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Installing Fastfetch...", total=None)

            # Download path
            temp_deb = os.path.join(AppConfig.TEMP_DIR, "fastfetch-linux-amd64.deb")

            # Download package
            progress.update(task, description="Downloading Fastfetch package...")
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
            progress.update(task, description="Installing Fastfetch package...")
            run_command(["dpkg", "-i", temp_deb])

            # Fix dependencies
            progress.update(task, description="Resolving dependencies...")
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
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            return False
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def docker_config(self) -> bool:
        """
        Install and configure Docker with detailed visual progress.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring Docker...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring Docker...", total=None)

            # Install Docker if missing
            if not Utils.command_exists("docker"):
                try:
                    # Use official install script
                    progress.update(task, description="Installing Docker...")
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
                    progress.update(task, description="Trying package installation...")
                    logger.info("Trying package installation...")

                    # Fall back to package installation
                    if not SystemUpdater().install_packages(["docker.io"]):
                        return False

            # Add user to docker group
            try:
                progress.update(task, description="Configuring Docker permissions...")
                groups = subprocess.check_output(
                    ["id", "-nG", AppConfig.USERNAME], text=True
                ).split()

                if "docker" not in groups:
                    run_command(["usermod", "-aG", "docker", AppConfig.USERNAME])
                    logger.info(f"Added {AppConfig.USERNAME} to docker group")
            except Exception as e:
                logger.warning(f"Failed to update docker group: {e}")

            # Configure daemon settings
            progress.update(task, description="Configuring Docker daemon...")
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
                progress.update(task, description="Enabling Docker service...")
                run_command(["systemctl", "enable", "docker"])

                progress.update(task, description="Restarting Docker service...")
                run_command(["systemctl", "restart", "docker"])
            except Exception as e:
                logger.error(f"Failed to restart Docker: {e}")
                return False

            # Install docker-compose if missing
            if not Utils.command_exists("docker-compose"):
                try:
                    progress.update(task, description="Installing Docker Compose...")
                    apt_cmd = Utils.get_apt_command()
                    run_command([apt_cmd, "install", "docker-compose-plugin", "-y"])
                    logger.info("Docker Compose plugin installed")
                except Exception as e:
                    logger.warning(f"Docker Compose installation failed: {e}")

            # Verify Docker is running
            try:
                progress.update(task, description="Verifying Docker installation...")
                run_command(["docker", "info"], capture_output=True)
                logger.info("Docker is configured and running")
                return True
            except Exception as e:
                logger.error(f"Docker verification failed: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def install_enable_tailscale(self) -> bool:
        """
        Install and enable Tailscale with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Installing and enabling Tailscale...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring Tailscale...", total=None)

            # Skip if already installed
            if Utils.command_exists("tailscale"):
                logger.info("Tailscale is already installed")
                progress.update(task, description="Tailscale already installed")
            else:
                try:
                    # Install using official script
                    progress.update(task, description="Installing Tailscale...")

                    # Use a temporary script file approach instead of piping directly
                    script_path = os.path.join(
                        AppConfig.TEMP_DIR, "tailscale_install.sh"
                    )
                    run_command(
                        [
                            "curl",
                            "-fsSL",
                            "https://tailscale.com/install.sh",
                            "-o",
                            script_path,
                        ]
                    )
                    os.chmod(script_path, 0o755)
                    run_command([script_path])
                    os.remove(script_path)

                    logger.info("Tailscale installed")
                except Exception as e:
                    logger.error(f"Tailscale installation failed: {e}")
                    return False

            # Enable and start service
            try:
                progress.update(task, description="Enabling Tailscale service...")
                run_command(["systemctl", "enable", "tailscaled"])

                progress.update(task, description="Starting Tailscale service...")
                run_command(["systemctl", "start", "tailscaled"])

                # Verify service is running
                progress.update(task, description="Verifying Tailscale service...")
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

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def deploy_user_scripts(self) -> bool:
        """
        Deploy user scripts to the user's bin directory with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Deploying user scripts...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Deploying user scripts...", total=None)

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
            progress.update(task, description="Creating bin directory...")
            Utils.ensure_directory(
                tgt, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
            )

            try:
                # Synchronize scripts
                progress.update(task, description="Copying scripts...")
                run_command(["rsync", "-ah", "--delete", f"{src}/", f"{tgt}/"])

                # Make scripts executable
                progress.update(task, description="Setting permissions...")
                run_command(
                    ["find", tgt, "-type", "f", "-exec", "chmod", "755", "{}", ";"]
                )

                # Fix ownership
                run_command(
                    ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", tgt]
                )

                logger.info(f"User scripts deployed to {tgt}")
                return True

            except Exception as e:
                logger.error(f"Failed to deploy user scripts: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def configure_unattended_upgrades(self) -> bool:
        """
        Configure unattended upgrades for automated security updates.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Configuring unattended upgrades...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Configuring unattended upgrades...", total=None)

            # Install required packages
            progress.update(task, description="Installing required packages...")
            apt_cmd = Utils.get_apt_command()
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                return False

            # Configure automatic upgrades
            progress.update(task, description="Configuring automatic upgrades...")
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
            progress.update(
                task, description="Writing unattended upgrades configuration..."
            )
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
            progress.update(task, description="Enabling unattended upgrades service...")
            run_command(["systemctl", "enable", "unattended-upgrades"])

            progress.update(task, description="Starting unattended upgrades service...")
            run_command(["systemctl", "restart", "unattended-upgrades"])

            # Verify service is running
            progress.update(task, description="Verifying service status...")
            status = run_command(
                ["systemctl", "is-active", "unattended-upgrades"],
                capture_output=True,
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()


# ----------------------------------------------------------------
# Maintenance Manager
# ----------------------------------------------------------------
class MaintenanceManager:
    """Manages system maintenance tasks with visual progress tracking."""

    def configure_periodic(self) -> bool:
        """
        Set up a daily maintenance cron job.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Setting up daily maintenance cron job...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Setting up maintenance cron job...", total=None)

            # Cron job file path
            cron_file = "/etc/cron.daily/debian_maintenance"

            # Marker to identify our script
            marker = "# Debian maintenance script"

            # Check if script already exists
            if os.path.isfile(cron_file):
                progress.update(task, description="Checking existing cron job...")
                with open(cron_file) as f:
                    if marker in f.read():
                        logger.info("Maintenance cron job already exists")
                        return True

                # Backup existing file
                Utils.backup_file(cron_file)

            # Get the apt command to use
            apt_cmd = Utils.get_apt_command()

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
                progress.update(task, description="Creating maintenance script...")
                with open(cron_file, "w") as f:
                    f.write(content)

                # Make executable
                os.chmod(cron_file, 0o755)

                logger.info("Daily maintenance cron job configured")
                return True

            except Exception as e:
                logger.error(f"Failed to create maintenance cron job: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def backup_configs(self) -> bool:
        """
        Backup important configuration files with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Backing up configuration files...")

        # Calculate total files for progress tracking
        total_files = sum(1 for file in AppConfig.CONFIG_FILES if os.path.isfile(file))

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=AppConfig.PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            # Create task first before trying to update it
            task = progress.add_task("Creating backup directory...", total=total_files)

            # Create backup directory with timestamp
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup_dir = os.path.join(AppConfig.BACKUP_DIR, f"debian_config_{ts}")

            os.makedirs(backup_dir, exist_ok=True)

            # Update task description for the next phase
            progress.update(task, description="Backing up configuration files...")

            success = True
            files_backed_up = 0

            # Copy each config file
            for file in AppConfig.CONFIG_FILES:
                if os.path.isfile(file):
                    progress.update(
                        task, description=f"Backing up {os.path.basename(file)}..."
                    )
                    try:
                        dest = os.path.join(backup_dir, os.path.basename(file))
                        shutil.copy2(file, dest)
                        files_backed_up += 1
                        progress.advance(task)
                    except Exception as e:
                        logger.warning(f"Backup failed for {file}: {e}")
                        success = False
                        progress.advance(task)

            try:
                # Create manifest file
                progress.update(task, description="Creating backup manifest...")
                manifest = os.path.join(backup_dir, "MANIFEST.txt")
                with open(manifest, "w") as f:
                    f.write("Debian Configuration Backup\n")
                    f.write(f"Created: {datetime.datetime.now()}\n")
                    f.write(f"Hostname: {AppConfig.HOSTNAME}\n\n")
                    f.write("Files:\n")

                    for file in AppConfig.CONFIG_FILES:
                        if os.path.isfile(
                            os.path.join(backup_dir, os.path.basename(file))
                        ):
                            f.write(f"- {file}\n")
            except Exception as e:
                logger.warning(f"Failed to create backup manifest: {e}")

            logger.info(
                f"Backed up {files_backed_up} configuration files to {backup_dir}"
            )
            return success

        except Exception as e:
            logger.error(f"Backup configuration failed: {e}")
            return False
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def update_ssl_certificates(self) -> bool:
        """
        Update SSL certificates using certbot with visual progress.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Updating SSL certificates...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Updating SSL certificates...", total=None)

            # Install certbot if missing
            if not Utils.command_exists("certbot"):
                progress.update(task, description="Installing certbot...")
                logger.info("Certbot not found, installing...")
                if not SystemUpdater().install_packages(["certbot"]):
                    return False

            # Dry run to check for renewals
            progress.update(task, description="Checking for certificate renewals...")
            output = run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True
            ).stdout

            # Perform actual renewal if needed
            if "No renewals were attempted" not in output:
                progress.update(task, description="Renewing certificates...")
                logger.info("Certificate renewals needed, running certbot")
                run_command(["certbot", "renew"])
            else:
                logger.info("No certificate renewals needed")

            return True

        except Exception as e:
            logger.error(f"SSL certificate update failed: {e}")
            return False
        finally:
            # Close the progress display
            progress_mgr.stop_progress()


# ----------------------------------------------------------------
# System Tuning and Home Permissions
# ----------------------------------------------------------------
class SystemTuner:
    """Tunes system parameters for optimal performance with visual feedback."""

    def tune_system(self) -> bool:
        """
        Apply performance tuning settings to the system with progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Applying system tuning settings...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Tuning system parameters...", total=None)

            # Path to sysctl config
            sysctl_conf = "/etc/sysctl.conf"

            # Backup original config
            if os.path.isfile(sysctl_conf):
                progress.update(task, description="Backing up sysctl configuration...")
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
                progress.update(task, description="Reading current configuration...")
                with open(sysctl_conf) as f:
                    content = f.read()

                # Remove existing tuning section if present
                marker = "# Performance tuning settings for Debian"
                if marker in content:
                    progress.update(task, description="Removing old tuning settings...")
                    content = re.split(marker, content)[0]

                # Add new tuning section
                progress.update(
                    task, description="Adding new performance tuning settings..."
                )
                content += f"\n{marker}\n" + "".join(
                    f"{k} = {v}\n" for k, v in tuning.items()
                )

                # Write updated config
                with open(sysctl_conf, "w") as f:
                    f.write(content)

                # Apply settings
                progress.update(task, description="Applying new settings...")
                run_command(["sysctl", "-p"])

                logger.info("System tuning settings applied")
                return True

            except Exception as e:
                logger.error(f"System tuning failed: {e}")
                return False

        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def home_permissions(self) -> bool:
        """
        Secure user home directory permissions with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Securing home directory for {AppConfig.USERNAME}...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task(
                "Securing home directory permissions...", total=None
            )

            # Set ownership
            progress.update(task, description="Setting home directory ownership...")
            run_command(
                [
                    "chown",
                    "-R",
                    f"{AppConfig.USERNAME}:{AppConfig.USERNAME}",
                    AppConfig.USER_HOME,
                ]
            )

            # Set base permission
            progress.update(task, description="Setting base permissions...")
            run_command(["chmod", "750", AppConfig.USER_HOME])

            # Set stricter permissions for sensitive directories
            for secure_dir in [".ssh", ".gnupg", ".config"]:
                dir_path = os.path.join(AppConfig.USER_HOME, secure_dir)
                if os.path.isdir(dir_path):
                    progress.update(
                        task, description=f"Securing {secure_dir} directory..."
                    )
                    run_command(["chmod", "700", dir_path])
                    logger.info(f"Secured {secure_dir} directory")

            # Set group sticky bit on all directories (to maintain permissions)
            progress.update(task, description="Setting group sticky bits...")
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
                progress.update(task, description="Setting default ACLs...")
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()


# ----------------------------------------------------------------
# Final Health Check and Cleanup
# ----------------------------------------------------------------
class FinalChecker:
    """Performs final system health checks and cleanup with visual reporting."""

    def system_health_check(self) -> Dict[str, Any]:
        """
        Perform a system health check and return details with visual progress.

        Returns:
            Dictionary containing health check results
        """
        logger.info("Performing system health check...")

        # Initialize health information dictionary
        health: Dict[str, Any] = {}

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Checking system health...", total=None)

            # Get uptime
            progress.update(task, description="Checking system uptime...")
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            health["uptime"] = uptime
            logger.info(f"System uptime: {uptime}")

            # Check disk usage
            progress.update(task, description="Checking disk usage...")
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

            # Check memory usage
            progress.update(task, description="Checking memory usage...")
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

            # Check system load
            progress.update(task, description="Checking system load...")
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]

            health["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
            logger.info(f"System load: {load[0]} (1m), {load[1]} (5m), {load[2]} (15m)")

            # Check for kernel errors
            progress.update(task, description="Checking kernel logs...")
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

            # Check for available updates
            progress.update(task, description="Checking for package updates...")
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

            health["updates"] = {
                "total": total_updates,
                "security": security_updates,
            }
            logger.info(
                f"Available updates: {total_updates} total, {security_updates} security"
            )

            return health

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {}
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def verify_firewall_rules(self) -> bool:
        """
        Verify that firewall rules are set correctly with visual progress.

        Returns:
            bool: True if firewall is configured correctly, False otherwise
        """
        logger.info("Verifying firewall rules...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=AppConfig.PROGRESS_WIDTH,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.FROST_3}][{{task.completed}}/{{task.total}}]"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task(
                "Verifying firewall...", total=len(AppConfig.ALLOWED_PORTS) + 1
            )

            # Check UFW status
            progress.update(task, description="Checking firewall status...")
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            progress.advance(task)

            if "inactive" in ufw_status.lower():
                logger.warning("UFW firewall is inactive")
                return False

            logger.info("UFW firewall is active")

            # Check if allowed ports are accessible
            port_status = []

            for port in AppConfig.ALLOWED_PORTS:
                progress.update(task, description=f"Checking port {port}...")
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

                progress.advance(task)

            # At least one port should be accessible
            return any(port_status)

        except Exception as e:
            logger.error(f"Firewall verification failed: {e}")
            return False
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def final_checks(self) -> bool:
        """
        Perform final system checks with visual progress tracking.

        Returns:
            bool: True if all checks pass, False otherwise
        """
        logger.info("Performing final system checks...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Running final checks...", total=None)
            all_passed = True

            # Check kernel version
            progress.update(task, description="Checking kernel version...")
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            logger.info(f"Kernel version: {kernel}")

            # Check disk usage
            progress.update(task, description="Checking disk usage...")
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
            progress.update(task, description="Checking system load...")
            load_avg = open("/proc/loadavg").read().split()[:3]
            cpu_count = os.cpu_count() or 1

            if float(load_avg[1]) > cpu_count:
                logger.warning(f"High system load: {load_avg[1]} (CPUs: {cpu_count})")
                all_passed = False
            else:
                logger.info(f"System load: {load_avg[1]} (CPUs: {cpu_count})")

            # Check critical services
            progress.update(task, description="Checking critical services...")
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
            progress.update(task, description="Checking for pending upgrades...")
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def cleanup_system(self) -> bool:
        """
        Perform system cleanup tasks with visual progress tracking.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Performing system cleanup...")

        # Get the package manager command
        apt_cmd = Utils.get_apt_command()

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TimeElapsedColumn(),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            task = progress.add_task("Cleaning up system...", total=None)
            success = True

            # Clean up package cache
            progress.update(task, description="Cleaning package cache...")
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
                progress.update(task, description="Checking for old kernels...")
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
                        progress.update(
                            task,
                            description=f"Removing {len(to_remove)} old kernels...",
                        )
                        logger.info(f"Removing {len(to_remove)} old kernels")
                        run_command([apt_cmd, "purge", "-y"] + to_remove)
            except Exception as e:
                logger.warning(f"Old kernel cleanup failed: {e}")
                success = False

            # Clean up journal logs
            if Utils.command_exists("journalctl"):
                progress.update(task, description="Cleaning up journal logs...")
                run_command(["journalctl", "--vacuum-time=7d"])
                logger.info("Journal logs cleaned up")

            # Clean up old temporary files
            progress.update(task, description="Cleaning up old temporary files...")
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
                progress.update(task, description="Compressing large log files...")
                log_files = (
                    subprocess.check_output(
                        ["find", "/var/log", "-type", "f", "-size", "+50M"],
                        text=True,
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
        finally:
            # Close the progress display
            progress_mgr.stop_progress()

    def auto_reboot(self) -> None:
        """
        Automatically reboot the system after a countdown with visual timer.
        """
        logger.info("Setup complete. Rebooting in 60 seconds.")
        print_success("Setup completed successfully. Rebooting in 60 seconds...")

        # Get the progress manager
        progress_mgr = progress_manager

        # Stop any active progress displays
        progress_mgr.stop_progress()

        # Create a new progress display
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.GREEN}]Rebooting in"),
            BarColumn(
                bar_width=30, style=NordColors.FROST_4, complete_style=NordColors.RED
            ),
            TextColumn(f"[bold {NordColors.YELLOW}]{{task.remaining}}s"),
            console=console,
        )

        # Register with the manager and start display
        progress.__enter__()
        progress_mgr.start_progress(progress)

        try:
            # Count down from 60 seconds
            task = progress.add_task("Rebooting...", total=60)

            for i in range(60):
                time.sleep(1)
                progress.update(task, advance=1)

            # Reboot
            console.print(f"[bold {NordColors.GREEN}]Rebooting now...[/]")
            run_command(["shutdown", "-r", "now"])
        except Exception as e:
            logger.error(f"Reboot failed: {e}")
        finally:
            # Close the progress display
            progress_mgr.stop_progress()


# ----------------------------------------------------------------
# Main Orchestration Class
# ----------------------------------------------------------------
class DebianServerSetup:
    """Main orchestration class for Debian server setup with comprehensive progress tracking."""

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
        Run the complete Debian server setup and hardening process with detailed progress tracking.

        Returns:
            int: Exit code (0 for success, 1 for failure)
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
                    "message": "Network check failed - cannot continue without connectivity",
                }
                print_error("Network check failed. Cannot continue setup.")
                sys.exit(1)

            if not run_with_progress(
                "Checking OS version",
                self.preflight.check_os_version,
            ):
                logger.warning("OS check failed – proceeding with caution.")

            run_with_progress(
                "Verifying system requirements",
                self.preflight.verify_system_requirements,
            )

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

        # Phase 3: Ensure Nala is Installed
        print_section("Phase 3: Installing Nala")
        try:
            if not run_with_progress(
                "Installing Nala package manager",
                install_nala,
                task_name="nala_install",
            ):
                logger.warning("Nala installation failed, will use apt instead.")
        except Exception as e:
            logger.error(f"Nala installation error: {e}")
            logger.warning("Will use apt instead of nala.")

        # Phase 4: System Update & Basic Configuration
        print_section("Phase 4: System Update & Basic Configuration")
        try:
            run_with_progress(
                "Fixing broken packages",
                self.updater.fix_package_issues,
            )
        except Exception as e:
            logger.warning(f"Package fix error: {e}")

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
            if not run_with_detailed_progress(
                "Installing required packages",
                self.updater.install_packages,
                total=100,
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

        # Phase 5: User Environment Setup
        print_section("Phase 5: User Environment Setup")
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

        # Phase 6: Security & Hardening
        print_section("Phase 6: Security & Hardening")
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

        # Phase 7: Service Installations
        print_section("Phase 7: Service Installations")
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

        # Phase 8: Maintenance Tasks
        print_section("Phase 8: Maintenance Tasks")
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

        # Phase 9: System Tuning & Permissions
        print_section("Phase 9: System Tuning & Permissions")
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

        # Phase 10: Final Checks & Cleanup
        print_section("Phase 10: Final Checks & Cleanup")
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

        # Display detailed summary
        print_section("Setup Summary")
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.FROST_2}]Debian Trixie Setup Completed[/]\n\n"
                    f"[bold {NordColors.FROST_3}]Total Duration:[/] {int(minutes)}m {int(seconds)}s\n"
                    f"[bold {NordColors.FROST_3}]Status:[/] {'[bold green]SUCCESS' if self.success and final_result else '[bold red]COMPLETED WITH ISSUES'}[/]\n"
                    f"[bold {NordColors.FROST_3}]Log File:[/] {AppConfig.LOG_FILE}\n\n"
                    f"{'[bold green]✓ System is ready for use![/]' if self.success and final_result else '[bold yellow]⚠ Some issues were detected. Check the log for details.[/]'}"
                ),
                border_style=Style(color=NordColors.FROST_1),
                box=ROUNDED,
                padding=(1, 2),
                title=f"[bold {NordColors.SNOW_STORM_2}]Debian Trixie[/]",
                title_align="center",
            )
        )

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
        int: Exit code (0 for success, non-zero for failure)
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
