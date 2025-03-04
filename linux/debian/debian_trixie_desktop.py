#!/usr/bin/env python3
"""
Debian Trixie Unattended Setup & Hardening Utility
-------------------------------------------------------

This fully automated utility performs pre-flight checks, system update,
repository configuration, security hardening, service installation,
user customization, maintenance tasks, certificate renewal, performance tuning,
permissions configuration, installation of additional apps, automatic updates,
and final system checks before an automated reboot.

Features:
  • Fully unattended operation with professional visual feedback
  • Nord-themed color scheme with dynamic ASCII headers
  • Comprehensive error handling with detailed logging
  • Signal handling for graceful termination
  • Progress tracking for all operations with Rich library
  • Nala APT frontend for faster package operations
  • Complete system setup with security hardening
  • Automatic cleanup and reboot

Note: This script must be run with root privileges.
"""

# ----------------------------------------------------------------
# Dependency Check & Auto-Installation
# ----------------------------------------------------------------
import os
import sys
import subprocess
import tempfile
from pathlib import Path


def ensure_dependencies() -> bool:
    """
    Ensure required Python packages are installed.
    Returns True if all dependencies are available or successfully installed.
    """
    required_packages = ["rich", "pyfiglet"]
    missing_packages = []

    print("Checking dependencies...")
    for pkg in required_packages:
        try:
            __import__(pkg)
        except ImportError:
            missing_packages.append(pkg)

    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing_packages,
                check=True,
                capture_output=True,
            )
            print("Dependencies installed successfully.")

            # Restart script to ensure dependencies are loaded properly
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install required packages: {e}")
            print("Please install the required packages manually:")
            print(f"pip install {' '.join(missing_packages)}")
            return False

    return True


# Ensure we have the required dependencies before proceeding
if not ensure_dependencies():
    sys.exit(1)

# ----------------------------------------------------------------
# Imports & Initialization
# ----------------------------------------------------------------
import atexit
import datetime
import filecmp
import gzip
import json
import logging
import platform
import re
import shutil
import signal
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Set

import pyfiglet
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    DownloadColumn,
)
from rich.style import Style
from rich.text import Text
from rich.align import Align
from rich.live import Live
from rich.layout import Layout
from rich.prompt import Confirm
from rich.syntax import Syntax


# ----------------------------------------------------------------
# Nord Color Theme & Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent styling."""

    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"


# Define a Nord theme for consistent styling
nord_theme = Theme(
    {
        "info": f"{NordColors.FROST_2}",
        "warning": f"{NordColors.YELLOW}",
        "error": f"{NordColors.RED}",
        "success": f"{NordColors.GREEN}",
        "debug": f"{NordColors.POLAR_NIGHT_4}",
        "header": f"bold {NordColors.FROST_1}",
        "title": f"bold {NordColors.FROST_3}",
        "progress": f"{NordColors.FROST_2}",
        "panel.border": f"{NordColors.FROST_4}",
    }
)

# Initialize console with Nord theme
console = Console(theme=nord_theme, highlight=False)


# ----------------------------------------------------------------
# Configuration Dataclass
# ----------------------------------------------------------------
@dataclass
class Config:
    """Configuration settings for the Debian Trixie setup script."""

    # Software versions
    PLEX_VERSION: str = "1.41.4.9463-630c9f557"
    FASTFETCH_VERSION: str = "2.37.0"
    DOCKER_COMPOSE_VERSION: str = "2.20.2"

    # File paths
    LOG_FILE: str = "/var/log/debian_setup.log"

    # User configuration
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path(f"/home/sawyer"))

    # Storage configuration
    ZFS_POOL_NAME: str = "WD_BLACK"
    ZFS_MOUNT_POINT: Path = field(default_factory=lambda: Path("/media/WD_BLACK"))

    # Package lists
    PACKAGES: List[str] = field(
        default_factory=lambda: [
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
            "neofetch",
            "build-essential",
            "cmake",
            "ninja-build",
            "meson",
            "gettext",
            "git",
            "pkg-config",
            "openssh-server",
            "ufw",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "bash-completion",
            "python3",
            "python3-dev",
            "python3-pip",
            "python3-venv",
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
            "ca-certificates",
            "apt-transport-https",
            "gnupg",
            "lsb-release",
            "clang",
            "llvm",
            "netcat-openbsd",
            "lsof",
            "unzip",
            "zip",
            "xorg",
            "x11-xserver-utils",
            "xterm",
            "alacritty",
            "fonts-dejavu-core",
            "net-tools",
            "nmap",
            "iftop",
            "iperf3",
            "tcpdump",
            "lynis",
            "traceroute",
            "mtr",
            "iotop",
            "glances",
            "golang-go",
            "gdb",
            "cargo",
            "fail2ban",
            "rkhunter",
            "chkrootkit",
            "postgresql-client",
            "mariadb-client",
            "redis-server",
            "ruby",
            "rustc",
            "jq",
            "yq",
            "certbot",
            "p7zip-full",
            "qemu-system",
            "libvirt-clients",
            "libvirt-daemon-system",
            "virt-manager",
            "qemu-user-static",
        ]
    )

    FLATPAK_APPS: List[str] = field(
        default_factory=lambda: [
            "com.discordapp.Discord",
            "com.usebottles.bottles",
            "com.valvesoftware.Steam",
            "com.spotify.Client",
            "org.videolan.VLC",
            "org.libretro.RetroArch",
            "com.obsproject.Studio",
            "com.github.tchx84.Flatseal",
            "net.lutris.Lutris",
            "net.davidotek.pupgui2",
            "org.gimp.GIMP",
            "org.qbittorrent.qBittorrent",
            "com.github.Matoking.protontricks",
            "md.obsidian.Obsidian",
            "org.prismlauncher.PrismLauncher",
            "com.bitwarden.desktop",
            "org.kde.kdenlive",
            "org.signal.Signal",
            "org.gnome.Boxes",
            "com.stremio.Stremio",
            "org.blender.Blender",
            "org.localsend.localsend_app",
            "fr.handbrake.ghb",
            "org.remmina.Remmina",
            "org.audacityteam.Audacity",
            "com.rustdesk.RustDesk",
            "com.getpostman.Postman",
            "io.github.aandrew_me.ytdn",
            "org.shotcut.Shotcut",
            "com.calibre_ebook.calibre",
            "tv.plex.PlexDesktop",
            "org.filezillaproject.Filezilla",
            "com.github.k4zmu2a.spacecadetpinball",
            "org.virt_manager.virt-manager",
            "org.raspberrypi.rpi-imager",
        ]
    )

    WAYLAND_ENV_VARS: Dict[str, str] = field(
        default_factory=lambda: {
            "GDK_BACKEND": "wayland",
            "QT_QPA_PLATFORM": "wayland",
            "SDL_VIDEODRIVER": "wayland",
        }
    )

    GITHUB_REPOS: List[str] = field(
        default_factory=lambda: ["bash", "windows", "web", "python", "go", "misc"]
    )

    SSH_SETTINGS: Dict[str, str] = field(
        default_factory=lambda: {
            "Port": "22",
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "PermitEmptyPasswords": "no",
            "ChallengeResponseAuthentication": "no",
            "Protocol": "2",
            "MaxAuthTries": "5",
            "ClientAliveInterval": "600",
            "ClientAliveCountMax": "48",
        }
    )

    FIREWALL_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443", "32400"]
    )

    CONFIG_BACKUP_FILES: List[str] = field(
        default_factory=lambda: [
            "/etc/ssh/sshd_config",
            "/etc/ufw/user.rules",
            "/etc/ntp.conf",
            "/etc/sysctl.conf",
            "/etc/environment",
            "/etc/fail2ban/jail.local",
            "/etc/docker/daemon.json",
            "/etc/caddy/Caddyfile",
        ]
    )

    DEBIAN_REPOS: Dict[str, Dict[str, Dict[str, List[str]]]] = field(
        default_factory=lambda: {
            "default": {
                "sources": {
                    "deb https://deb.debian.org/debian": [
                        "trixie",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                    "deb https://security.debian.org/debian-security": [
                        "trixie-security",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                    "deb https://deb.debian.org/debian": [
                        "trixie-updates",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                }
            },
            "mirrors": {
                "sources": {
                    "deb http://mirrors.kernel.org/debian": [
                        "trixie",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                    "deb http://security.debian.org/debian-security": [
                        "trixie-security",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                    "deb http://mirrors.kernel.org/debian": [
                        "trixie-updates",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ],
                }
            },
            "local": {
                "sources": {
                    "deb file:/var/local/debian": [
                        "trixie",
                        "main",
                        "contrib",
                        "non-free-firmware",
                    ]
                }
            },
        }
    )

    def __post_init__(self):
        """Initialize derived configuration values after the dataclass is created."""
        self.PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{self.PLEX_VERSION}/debian/plexmediaserver_{self.PLEX_VERSION}_amd64.deb"
        self.FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{self.FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"
        self.DOCKER_COMPOSE_URL = f"https://github.com/docker/compose/releases/download/v{self.DOCKER_COMPOSE_VERSION}/{platform.system()}-{platform.machine()}"
        self.CONFIG_SRC_DIR = (
            self.USER_HOME / "github" / "bash" / "linux" / "debian" / "dotfiles"
        )
        self.CONFIG_DEST_DIR = self.USER_HOME / ".config"


# ----------------------------------------------------------------
# Global State Tracking
# ----------------------------------------------------------------
# Status dictionary for each phase
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "nala_setup": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "repo_shell": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "user_custom": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "certs_perf": {"status": "pending", "message": ""},
    "permissions_storage": {"status": "pending", "message": ""},
    "additional_apps": {"status": "pending", "message": ""},
    "auto_updates": {"status": "pending", "message": ""},
    "cleanup_final": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header(title: str) -> Panel:
    """
    Generate a dynamic ASCII art header with gradient styling using Pyfiglet.

    Args:
        title: The title text to display in the ASCII art

    Returns:
        A Rich Panel containing the styled ASCII art header
    """
    # Get terminal width for responsive design
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)  # Account for panel borders

    # Try various fonts until we find one that works well
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""

    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(title)
            if ascii_art.strip():
                break
        except Exception:
            continue

    # Split the ASCII art into lines for gradient coloring
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]

    # Create a gradient of Nord Frost colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    styled_text = Text()

    # Apply gradient coloring
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        line_text = Text(line, style=Style(color=color, bold=True))
        styled_text.append(line_text)
        styled_text.append("\n")

    # Create a separator border with Frost color
    border_text = Text(
        "━" * (adjusted_width - 6), style=Style(color=NordColors.FROST_3)
    )

    # Combine everything into a panel
    content = Text()
    content.append(border_text)
    content.append("\n")
    content.append(styled_text)
    content.append(border_text)

    header_panel = Panel(
        content,
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"v1.0.0",
        title_align="right",
    )

    return header_panel


def print_section(title: str) -> None:
    """
    Display a section header with consistent styling.

    Args:
        title: The section title text
    """
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step message."""
    print_message(message, NordColors.FROST_2, "→")


def print_status_report() -> None:
    """Display a summary status report of all phases."""
    table = Table(
        title="Debian Trixie Setup Status Report",
        title_style=f"bold {NordColors.FROST_1}",
        border_style=f"{NordColors.FROST_3}",
        box=box.ROUNDED,
        highlight=True,
        show_lines=True,
    )

    table.add_column("Task", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style="bold")
    table.add_column("Message")

    for key, data in SETUP_STATUS.items():
        status_style = {
            "success": NordColors.GREEN,
            "failed": NordColors.RED,
            "in_progress": NordColors.YELLOW,
            "pending": NordColors.FROST_3,
        }.get(data["status"].lower(), NordColors.FROST_2)

        table.add_row(
            key.replace("_", " ").title(),
            f"[{status_style}]{data['status'].upper()}[/{status_style}]",
            data["message"],
        )

    console.print(Panel(table, border_style=f"{NordColors.FROST_1}"))


def run_with_progress(
    description: str, func: Callable, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """
    Execute a function while displaying a live progress bar.
    Updates the SETUP_STATUS for the given phase (if task_name is provided).

    Args:
        description: Description of the task being performed
        func: Function to execute
        task_name: Optional name of the task for status tracking
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The return value of the executed function
    """
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }

    console.print(
        f"[bold {NordColors.FROST_2}]▶ {description}...[/bold {NordColors.FROST_2}]"
    )
    start = time.time()

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(
            complete_style=f"{NordColors.GREEN}", finished_style=f"{NordColors.GREEN}"
        ),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task = progress.add_task(description, total=100)

        def progress_updater():
            while not progress.tasks[task].finished:
                progress.update(task, advance=0.5)
                time.sleep(0.1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            updater_future = executor.submit(progress_updater)
            result_future = executor.submit(func, *args, **kwargs)
            try:
                result = result_future.result()
                progress.update(task, completed=100)
                elapsed = time.time() - start
                console.print(
                    f"[{NordColors.GREEN}]✓ {description} completed in {elapsed:.2f}s[/{NordColors.GREEN}]"
                )
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "success",
                        "message": f"{description} completed successfully.",
                    }
                return result
            except Exception as e:
                progress.update(task, completed=100)
                elapsed = time.time() - start
                console.print(
                    f"[{NordColors.RED}]✗ {description} failed in {elapsed:.2f}s: {str(e)}[/{NordColors.RED}]"
                )
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": f"{description} failed: {str(e)}",
                    }
                raise


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    """
    Configure a logger with Rich formatting and persistent file logging.

    Args:
        log_file: Path to the log file

    Returns:
        Configured logger instance
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("debian_setup")
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create and configure Rich console handler
    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=False,
    )

    # Create formatter for file handler
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    rich_handler.setFormatter(fmt)
    logger.addHandler(rich_handler)

    # Create and configure file handler
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        os.chmod(str(log_file), 0o600)  # Secure the log file
    except Exception as e:
        logger.warning(f"Could not set up file logging to {log_file}: {e}")

    return logger


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def backup_file(file_path: Union[str, Path]) -> Optional[Path]:
    """
    Create a backup of a file with timestamp.

    Args:
        file_path: Path to the file to back up

    Returns:
        Path to the backup file or None if backup failed
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = file_path.with_suffix(f"{file_path.suffix}.{timestamp}.bak")

    try:
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception:
        return None


def backup_directory(dir_path: Union[str, Path]) -> Optional[Path]:
    """
    Create a backup of a directory with timestamp.

    Args:
        dir_path: Path to the directory to back up

    Returns:
        Path to the backup directory or None if backup failed
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = dir_path.with_suffix(f".{timestamp}.bak")

    try:
        shutil.copytree(dir_path, backup_path)
        return backup_path
    except Exception:
        return None


def command_exists(command: str) -> bool:
    """
    Check if a command exists in the system.

    Args:
        command: Name of the command to check

    Returns:
        True if the command exists, False otherwise
    """
    try:
        subprocess.run(
            ["which", command],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.SubprocessError:
        return False


def download_file(url: str, dest_path: Union[str, Path]) -> bool:
    """
    Download a file from a URL to a local path.

    Args:
        url: URL to download from
        dest_path: Local path to save the file to

    Returns:
        True if download succeeded, False otherwise
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["wget", "-q", "--show-progress", url, "-O", str(dest_path)],
            check=True,
        )
        return True
    except subprocess.SubprocessError:
        try:
            subprocess.run(
                ["curl", "-L", "-o", str(dest_path), url],
                check=True,
            )
            return True
        except subprocess.SubprocessError:
            return False


def run_command(
    command: List[str],
    capture_output: bool = False,
    text: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a shell command with optional output capture.

    Args:
        command: Command as a list of strings
        capture_output: Whether to capture stdout/stderr
        text: Whether to decode output as text
        check: Whether to check the return code

    Returns:
        CompletedProcess instance with command results
    """
    return subprocess.run(
        command,
        capture_output=capture_output,
        text=text,
        check=check,
    )


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    """
    Gracefully handle termination signals.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    try:
        sig_name = (
            signal.Signals(signum).name
            if hasattr(signal, "Signals")
            else f"signal {signum}"
        )
        logging.getLogger("debian_setup").error(
            f"Script interrupted by {sig_name}. Initiating cleanup."
        )
        console.print(
            f"[bold {NordColors.RED}]Script interrupted by {sig_name}. Cleaning up...[/]"
        )
    except Exception:
        pass

    try:
        cleanup_temp_files()
    except Exception:
        pass

    sys.exit(128 + signum)


def cleanup_temp_files() -> None:
    """Clean up temporary files created during execution."""
    logging.getLogger("debian_setup").info("Cleaning up temporary files.")

    # Find and remove temporary files created by this script
    tmp = Path(tempfile.gettempdir())
    patterns = ["debian_setup_*", "plexmediaserver*", "code*", "fastfetch*", "caddy*"]

    for pattern in patterns:
        for item in tmp.glob(pattern):
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception:
                pass


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# Register cleanup function to run at exit
atexit.register(cleanup_temp_files)


# ----------------------------------------------------------------
# Main Setup Class
# ----------------------------------------------------------------
class DebianTrixieSetup:
    """Core class that runs all setup phases sequentially."""

    def __init__(self, config: Config = Config()):
        """
        Initialize the setup class with configuration and logger.

        Args:
            config: Configuration object with setup parameters
        """
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self.logger.info("Debian Trixie Setup started.")

        # For tracking if Nala is installed
        self.nala_available = False

        # Set to track executed package installs to avoid redundancy
        self.installed_packages: Set[str] = set()

    def print_section(self, title: str) -> None:
        """
        Display a section header using Pyfiglet and a Rich panel.

        Args:
            title: Section title text
        """
        try:
            # Display header using create_header function
            header = create_header(title)
            console.print(header)
            self.logger.info(f"--- {title} ---")
        except Exception as e:
            # Fallback if pyfiglet fails
            console.print(Panel(f"[bold {NordColors.FROST_2}]{title}[/]"))
            self.logger.info(f"--- {title} --- (Display error: {e})")

    def run_command(
        self,
        command: List[str],
        capture_output: bool = False,
        text: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run a shell command, replacing apt with nala when appropriate.

        Args:
            command: Command as a list of strings
            capture_output: Whether to capture stdout/stderr
            text: Whether to decode output as text
            check: Whether to check the return code

        Returns:
            CompletedProcess instance with command results
        """
        # Replace apt/apt-get with nala if it's available and appropriate
        if self.nala_available and len(command) > 0:
            if command[0] in ["apt", "apt-get"]:
                # Keep original command for logging
                original_command = command.copy()

                # Replace the command with nala
                command[0] = "nala"

                # Log the substitution
                self.logger.debug(
                    f"Replacing '{original_command[0]}' with 'nala': {' '.join(command)}"
                )

        # Log the command being executed
        cmd_str = " ".join(command)
        self.logger.debug(f"Executing: {cmd_str}")

        # Execute the command
        return run_command(command, capture_output, text, check)

    # --- Phase: Nala Installation ---
    def phase_nala_setup(self) -> bool:
        """Install Nala APT frontend as the first setup phase."""
        self.print_section("Nala APT Frontend Installation")

        try:
            # First check if Nala is already installed
            if command_exists("nala"):
                self.logger.info("Nala is already installed.")
                self.nala_available = True
                SETUP_STATUS["nala_setup"] = {
                    "status": "success",
                    "message": "Nala was already installed.",
                }
                return True

            # Fix repository configuration first
            self.logger.info("Fixing repository configuration...")

            # Create a fixed sources.list with correct repositories
            sources_file = Path("/etc/apt/sources.list")
            backup_path = None

            if sources_file.exists():
                backup_path = backup_file(sources_file)
                if backup_path:
                    self.logger.info(
                        f"Backed up original sources.list to {backup_path}"
                    )

            # Create a fixed sources.list without the problematic trixie-security
            # Using standard stable security repository instead
            fixed_sources = """# Fixed Debian repositories by setup script
# Main repositories
deb http://deb.debian.org/debian trixie main contrib non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free-firmware

# Debian Security Updates 
deb http://security.debian.org/debian-security bookworm-security main contrib non-free-firmware
"""

            # Write the fixed sources.list
            try:
                sources_file.write_text(fixed_sources)
                self.logger.info("Updated sources.list with corrected repositories.")
            except Exception as e:
                self.logger.error(f"Failed to update sources.list: {e}")
                # Restore backup if available
                if backup_path:
                    try:
                        shutil.copy2(backup_path, sources_file)
                        self.logger.info("Restored original sources.list from backup.")
                    except Exception:
                        pass
                return False

            # Clean apt cache and update package lists
            self.logger.info("Cleaning APT cache and updating package lists...")

            try:
                # Make sure everything is in a clean state
                self.run_command(["apt-get", "clean"], check=False)
                self.run_command(["apt-get", "autoclean"], check=False)

                # Run configuration fix commands
                self.run_command(["dpkg", "--configure", "-a"], check=False)

                # Update package lists
                self.run_command(["apt-get", "update"])
                self.logger.info("Repository update completed successfully.")
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Repository update encountered issues: {e}")
                self.logger.info("Continuing with installation attempt...")

            # Try to fix any broken packages before proceeding
            try:
                self.run_command(
                    ["apt-get", "--fix-broken", "install", "-y"], check=False
                )
            except subprocess.CalledProcessError:
                self.logger.warning(
                    "Failed to fix broken packages, continuing anyway..."
                )

            # Install Nala with careful error handling
            self.logger.info("Installing Nala APT frontend...")

            try:
                # First try to install just nala
                self.run_command(["apt-get", "install", "nala", "-y"])
                self.logger.info("Nala installed successfully via apt-get.")
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Standard Nala installation failed: {e}")

                # Try with more verbose output to see what's happening
                try:
                    self.logger.info("Trying alternative installation method...")
                    # Try installing with --no-install-recommends
                    self.run_command(
                        ["apt-get", "install", "--no-install-recommends", "nala", "-y"]
                    )
                    self.logger.info(
                        "Nala installed with --no-install-recommends option."
                    )
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"All Nala installation attempts failed: {e}")

                    # If Nala installation fails, we can still continue without it
                    SETUP_STATUS["nala_setup"] = {
                        "status": "failed",
                        "message": f"Failed to install Nala, continuing with apt: {e}",
                    }
                    return False

            # Verify installation
            if command_exists("nala"):
                self.nala_available = True
                self.logger.info("Nala installation confirmed.")

                # Configure faster mirrors with nala
                try:
                    # Skip mirror fetching if it fails, it's not critical
                    self.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    self.logger.info("Configured faster mirrors with Nala.")
                except Exception as e:
                    self.logger.warning(f"Mirror configuration skipped: {e}")

                SETUP_STATUS["nala_setup"] = {
                    "status": "success",
                    "message": "Nala installed and configured successfully.",
                }
                return True
            else:
                self.logger.error("Nala installation verification failed.")
                SETUP_STATUS["nala_setup"] = {
                    "status": "failed",
                    "message": "Nala installation verification failed, continuing with apt.",
                }
                return False

        except Exception as e:
            self.logger.error(f"Nala setup failed: {e}")
            SETUP_STATUS["nala_setup"] = {
                "status": "failed",
                "message": f"Nala setup failed with unexpected error: {e}",
            }
            return False

    # --- Phase 1: Pre-flight Checks & Backups ---
    def phase_preflight(self) -> bool:
        """Perform pre-flight checks and create backups before main operations."""
        self.print_section("Pre-flight Checks & Backups")
        try:
            run_with_progress(
                "Verifying root privileges", self.check_root, task_name="preflight"
            )
            run_with_progress(
                "Checking network connectivity",
                self.check_network,
                task_name="preflight",
            )
            run_with_progress(
                "Saving configuration snapshot",
                self.save_config_snapshot,
                task_name="preflight",
            )
            run_with_progress(
                "Creating ZFS snapshot if available",
                self.create_system_zfs_snapshot,
                task_name="preflight",
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            return False

    def check_root(self) -> None:
        """Ensure script is run with root privileges."""
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root.")
            console.print(
                Panel(
                    f"[bold {NordColors.RED}]This script must be run with root privileges.[/]",
                    border_style=f"{NordColors.RED}",
                )
            )
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    def has_internet_connection(self) -> bool:
        """Return True if the system can reach the internet."""
        try:
            result = self.run_command(
                ["ping", "-c", "1", "-W", "5", "8.8.8.8"],
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_network(self) -> None:
        """Check network connectivity; exit if unavailable."""
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity detected. Aborting.")
            console.print(
                Panel(
                    f"[bold {NordColors.RED}]No network connectivity detected. The setup cannot continue without internet access.[/]",
                    border_style=f"{NordColors.RED}",
                )
            )
            sys.exit(1)

    def save_config_snapshot(self) -> Optional[str]:
        """Backup critical configuration files into a compressed tarball."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot_file = backup_dir / f"config_snapshot_{timestamp}.tar.gz"

        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                files_added = 0
                for cfg in self.config.CONFIG_BACKUP_FILES:
                    cfg_path = Path(cfg)
                    if cfg_path.is_file():
                        tar.add(str(cfg_path), arcname=cfg_path.name)
                        self.logger.info(f"Included {cfg_path} in snapshot.")
                        files_added += 1
                    else:
                        self.logger.debug(f"{cfg_path} not found; skipping.")

                if files_added:
                    self.logger.info(f"Configuration snapshot saved: {snapshot_file}")
                    return str(snapshot_file)
                else:
                    self.logger.warning("No configuration files found to backup.")
                    return None
        except Exception as e:
            self.logger.warning(f"Failed to create config snapshot: {e}")
            return None

    def create_system_zfs_snapshot(self) -> Optional[str]:
        """Create a ZFS snapshot if ZFS is available."""
        try:
            result = self.run_command(
                ["zfs", "version"], capture_output=True, check=False
            )
            if result.returncode != 0:
                self.logger.info("ZFS not available; skipping snapshot.")
                return None

            # Try to find the appropriate system dataset
            system_dataset = "rpool/ROOT/debian"
            try:
                self.run_command(["zfs", "list", system_dataset], capture_output=True)
                self.logger.info(f"Dataset '{system_dataset}' found.")
            except subprocess.CalledProcessError:
                system_dataset = "rpool"
                self.logger.warning(
                    "Dataset 'rpool/ROOT/debian' not found; using 'rpool'."
                )
                try:
                    self.run_command(
                        ["zfs", "list", system_dataset], capture_output=True
                    )
                    self.logger.info(f"Dataset '{system_dataset}' found.")
                except subprocess.CalledProcessError:
                    self.logger.warning(
                        "No suitable ZFS dataset found; skipping snapshot."
                    )
                    return None

            # Create the snapshot
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            snapshot_name = f"{system_dataset}@backup_{timestamp}"
            try:
                self.run_command(["zfs", "snapshot", snapshot_name])
                self.logger.info(f"Created ZFS snapshot: {snapshot_name}")
                return snapshot_name
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to create ZFS snapshot: {e}")
                return None
        except Exception as e:
            self.logger.warning(f"Error checking ZFS: {e}")
            return None

    # --- Phase 2: System Update & Basic Configuration ---
    def phase_system_update(self) -> bool:
        """Update system packages and configure basic settings."""
        self.print_section("System Update & Basic Configuration")
        status = True

        if not run_with_progress(
            "Configuring Debian repositories",
            self.configure_debian_repos,
            task_name="system_update",
        ):
            status = False

        if not run_with_progress(
            "Updating system packages", self.update_system, task_name="system_update"
        ):
            status = False

        success, failed = self.install_packages()
        if failed and len(failed) > len(self.config.PACKAGES) * 0.1:
            self.logger.error(f"Failed packages: {', '.join(failed)}")
            status = False

        if not run_with_progress(
            "Setting system timezone",
            self.configure_timezone,
            task_name="system_update",
        ):
            status = False

        return status

    def configure_debian_repos(self, repo_type: str = "default") -> bool:
        """Configure Debian repositories using the specified configuration."""
        self.print_section("Debian Repository Configuration")

        # Skip repository configuration if it was already done during Nala setup
        if self.nala_available:
            self.logger.info(
                "Repository configuration already performed during Nala setup."
            )
            return True

        if repo_type not in self.config.DEBIAN_REPOS:
            self.logger.warning(f"Unknown repo type '{repo_type}'; using default")
            repo_type = "default"

        self.logger.info(f"Configuring repositories with '{repo_type}' configuration.")
        sources_file = Path("/etc/apt/sources.list")

        if sources_file.exists():
            backup_path = backup_file(sources_file)
            if backup_path:
                self.logger.info(f"Backed up existing sources.list to {backup_path}")

        try:
            # Use safe fixed repositories that we know work
            content = (
                """# Debian Trixie repositories configured by setup script
# Date: """
                + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + """

# Main repositories
deb http://deb.debian.org/debian trixie main contrib non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free-firmware

# Debian Security Updates 
deb http://security.debian.org/debian-security bookworm-security main contrib non-free-firmware
"""
            )

            sources_file.write_text(content)
            self.logger.info(f"Updated {sources_file} with stable repositories.")

            # Clean apt cache before updating
            self.run_command(["apt-get", "clean"], check=False)

            # Fix any broken packages
            self.run_command(["dpkg", "--configure", "-a"], check=False)

            # Update package lists
            try:
                self.run_command(["apt-get", "update"])
                self.logger.info("Package lists updated successfully.")
                return True
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Repository update encountered issues: {e}")
                self.logger.info(
                    "These issues might be non-critical, continuing setup..."
                )
                # Return True anyway as this is not fatal
                return True
        except Exception as e:
            self.logger.error(f"Failed to configure repositories: {e}")
            return False

    def update_system(self) -> bool:
        """Perform system update and upgrade."""
        self.print_section("System Update & Upgrade")

        try:
            # Update package lists
            self.logger.info("Updating package lists...")
            self.run_command(["apt-get", "update", "-qq"])

            # Perform system upgrade
            self.logger.info("Upgrading installed packages...")
            if self.nala_available:
                # Use non-interactive mode with nala
                self.run_command(["nala", "upgrade", "-y"])
            else:
                self.run_command(["apt-get", "upgrade", "-y"])

            self.logger.info("System update and upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System update failed: {e}")
            return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
        """Check and install missing packages."""
        self.print_section("Essential Package Installation")
        self.logger.info("Verifying required packages...")

        missing = []
        success = []
        failed = []

        # First check which packages are already installed
        for pkg in self.config.PACKAGES:
            if pkg in self.installed_packages:
                success.append(pkg)
                continue

            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f='${Status}'", pkg],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if "install ok installed" in result.stdout:
                    self.logger.debug(f"Package already installed: {pkg}")
                    success.append(pkg)
                    self.installed_packages.add(pkg)  # Track installed packages
                else:
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)

        # Install missing packages in batches for better performance
        if missing:
            self.logger.info(f"Installing {len(missing)} missing packages...")
            batch_size = 20

            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Installing packages..."),
                BarColumn(complete_style=f"{NordColors.GREEN}"),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Installing", total=len(missing))

                for i in range(0, len(missing), batch_size):
                    batch = missing[i : i + batch_size]
                    try:
                        self.run_command(["apt-get", "install", "-y"] + batch)
                        success.extend(batch)
                        for pkg in batch:
                            self.installed_packages.add(pkg)  # Track installed packages

                        self.logger.info(f"Installed batch of {len(batch)} packages.")
                        progress.update(task, advance=len(batch))
                    except subprocess.CalledProcessError as e:
                        self.logger.error(f"Failed to install batch: {e}")

                        # Check each package individually to determine which ones failed
                        for pkg in batch:
                            try:
                                result = subprocess.run(
                                    ["dpkg-query", "-W", "-f='${Status}'", pkg],
                                    check=False,
                                    capture_output=True,
                                    text=True,
                                )
                                if "install ok installed" in result.stdout:
                                    success.append(pkg)
                                    self.installed_packages.add(
                                        pkg
                                    )  # Track installed packages
                                    progress.update(task, advance=1)
                                else:
                                    failed.append(pkg)
                            except Exception:
                                failed.append(pkg)

            self.logger.info(
                f"Package installation: {len(success)} succeeded, {len(failed)} failed."
            )

            if failed:
                self.logger.warning(f"Failed packages: {', '.join(failed)}")
        else:
            self.logger.info("All required packages are already installed.")

        return success, failed

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        """Set the system timezone."""
        self.print_section("Timezone Configuration")
        self.logger.info(f"Setting timezone to {timezone}...")

        try:
            # Try using timedatectl first (systemd)
            self.run_command(["timedatectl", "set-timezone", timezone])
            self.logger.info("Timezone updated via timedatectl.")
            return True
        except subprocess.CalledProcessError:
            # Fall back to manual symlink method
            try:
                tz_file = Path(f"/usr/share/zoneinfo/{timezone}")
                localtime = Path("/etc/localtime")

                if not tz_file.is_file():
                    self.logger.warning(f"Timezone file not found: {tz_file}")
                    return False

                # Remove existing symlink or file if present
                if localtime.exists() or localtime.is_symlink():
                    localtime.unlink()

                # Create new symlink
                localtime.symlink_to(tz_file)
                self.logger.info("Timezone set using fallback method.")
                return True
            except Exception as e:
                self.logger.error(f"Failed to set timezone: {e}")
                return False

    # --- Phase 3: Repository & Shell Setup ---
    def phase_repo_shell_setup(self) -> bool:
        """Set up Git repositories and shell configuration."""
        self.print_section("Repository & Shell Setup")
        status = True

        if not run_with_progress(
            "Setting up GitHub repositories", self.setup_repos, task_name="repo_shell"
        ):
            status = False

        if not run_with_progress(
            "Copying shell configuration files", self.copy_shell_configs
        ):
            status = False

        if not run_with_progress(
            "Copying configuration folders", self.copy_config_folders
        ):
            status = False

        if not run_with_progress("Setting default shell to bash", self.set_bash_shell):
            status = False

        return status

    def setup_repos(self) -> bool:
        """Clone or update GitHub repositories."""
        self.print_section("GitHub Repositories Setup")

        # Create the main GitHub directory
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)

        all_success = True
        repo_count = len(self.config.GITHUB_REPOS)

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Setting up repositories..."),
            BarColumn(complete_style=f"{NordColors.GREEN}"),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Repositories", total=repo_count)

            for repo in self.config.GITHUB_REPOS:
                repo_dir = gh_dir / repo

                if (repo_dir / ".git").is_dir():
                    # Repository exists, pull updates
                    self.logger.info(f"Repository '{repo}' exists; pulling updates.")
                    try:
                        self.run_command(["git", "-C", str(repo_dir), "pull"])
                    except subprocess.CalledProcessError:
                        self.logger.warning(f"Failed to update repository '{repo}'.")
                        all_success = False
                else:
                    # Clone the repository
                    self.logger.info(f"Cloning repository '{repo}'...")
                    try:
                        self.run_command(
                            [
                                "git",
                                "clone",
                                f"https://github.com/dunamismax/{repo}.git",
                                str(repo_dir),
                            ]
                        )
                    except subprocess.CalledProcessError:
                        self.logger.warning(f"Failed to clone repository '{repo}'.")
                        all_success = False

                progress.update(task, advance=1)

        # Set proper ownership of the repositories
        try:
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(gh_dir),
                ]
            )
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set ownership of {gh_dir}.")
            all_success = False

        return all_success

    def copy_shell_configs(self) -> bool:
        """Copy shell configuration files from repository to home directories."""
        self.print_section("Shell Configuration Update")

        source_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "debian" / "dotfiles"
        )
        destination_dirs = [self.config.USER_HOME, Path("/root")]
        overall = True

        # Create minimal configs if source directory not found
        if not source_dir.is_dir():
            self.logger.warning(
                f"Source directory {source_dir} not found; creating minimal configs."
            )
            source_dir = Path("/tmp/debian_setup_dotfiles")
            source_dir.mkdir(exist_ok=True)

            # Create minimal .bashrc
            (source_dir / ".bashrc").write_text(
                r"""# Minimal .bashrc
if [ -f /etc/bash.bashrc ]; then
    . /etc/bash.bashrc
fi
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
export PATH=$HOME/bin:$PATH
"""
            )

            # Create minimal .profile
            (source_dir / ".profile").write_text(
                r"""# Minimal .profile
if [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi
"""
            )

            # Set appropriate ownership
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(source_dir),
                ]
            )

        # Copy shell config files
        for file_name in [".bashrc", ".profile"]:
            src = source_dir / file_name

            if not src.is_file():
                self.logger.warning(f"Source file {src} not found; skipping.")
                continue

            for dest_dir in destination_dirs:
                dest = dest_dir / file_name

                # Check if file is already up-to-date
                if dest.is_file() and filecmp.cmp(src, dest):
                    self.logger.info(f"File {dest} is up-to-date.")
                else:
                    try:
                        # Backup existing file if it exists
                        if dest.is_file():
                            backup_path = backup_file(dest)
                            if backup_path:
                                self.logger.info(f"Backed up {dest} to {backup_path}")

                        # Copy the file
                        shutil.copy2(src, dest)

                        # Set appropriate ownership
                        owner = (
                            f"{self.config.USERNAME}:{self.config.USERNAME}"
                            if dest_dir == self.config.USER_HOME
                            else "root:root"
                        )
                        self.run_command(["chown", owner, str(dest)])

                        self.logger.info(f"Copied {src} to {dest}.")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        overall = False

        return overall

    def copy_config_folders(self) -> bool:
        """Copy configuration folders from repository to user's .config directory."""
        self.print_section("Configuration Folders Setup")

        src = self.config.CONFIG_SRC_DIR
        dest = self.config.CONFIG_DEST_DIR

        if not src.is_dir():
            self.logger.warning(
                f"Source config directory {src} not found; skipping folder copy."
            )
            return True

        # Ensure destination directory exists
        dest.mkdir(exist_ok=True)
        overall = True

        try:
            # Get list of subdirectories to copy
            config_dirs = [item for item in src.iterdir() if item.is_dir()]

            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn(
                    f"[bold {NordColors.FROST_2}]Copying configuration folders..."
                ),
                BarColumn(complete_style=f"{NordColors.GREEN}"),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Copying", total=len(config_dirs))

                for item in config_dirs:
                    dest_path = dest / item.name

                    # Backup existing directory if it exists
                    if dest_path.exists():
                        self.logger.info(f"Backing up existing directory {dest_path}.")
                        backup_path = backup_directory(dest_path)
                        if backup_path:
                            self.logger.info(f"Backed up {dest_path} to {backup_path}")

                    # Copy the directory
                    shutil.copytree(item, dest_path, dirs_exist_ok=True)

                    # Set appropriate ownership
                    self.run_command(
                        [
                            "chown",
                            "-R",
                            f"{self.config.USERNAME}:{self.config.USERNAME}",
                            str(dest_path),
                        ]
                    )

                    self.logger.info(f"Copied {item} to {dest_path}.")
                    progress.update(task, advance=1)

            return overall
        except Exception as e:
            self.logger.error(f"Error copying config folders: {e}")
            return False

    def set_bash_shell(self) -> bool:
        """Ensure bash is installed and set as the default shell for the user."""
        self.print_section("Default Shell Configuration")

        # Ensure bash is installed
        if not command_exists("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                self.run_command(["apt-get", "install", "-y", "bash"])
            except subprocess.CalledProcessError:
                self.logger.warning("Bash installation failed.")
                return False

        # Check and update /etc/shells if needed
        shells_file = Path("/etc/shells")
        try:
            if shells_file.exists():
                content = shells_file.read_text()
                if "/bin/bash" not in content:
                    with open(shells_file, "a") as f:
                        f.write("/bin/bash\n")
                    self.logger.info("Added /bin/bash to /etc/shells.")
            else:
                with open(shells_file, "w") as f:
                    f.write("/bin/bash\n")
                self.logger.info("Created /etc/shells with /bin/bash.")
        except Exception as e:
            self.logger.warning(f"Failed to update /etc/shells: {e}")
            return False

        # Set default shell for the user
        try:
            self.run_command(["chsh", "-s", "/bin/bash", self.config.USERNAME])
            self.logger.info(f"Set default shell for {self.config.USERNAME} to bash.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to change default shell for {self.config.USERNAME}."
            )
            return False

    # --- Phase 4: Security Hardening ---
    def phase_security_hardening(self) -> bool:
        """Configure security settings for SSH, firewall, and other services."""
        self.print_section("Security Hardening")
        status = True

        if not run_with_progress(
            "Configuring SSH", self.configure_ssh, task_name="security"
        ):
            status = False

        if not run_with_progress("Setting up sudoers", self.setup_sudoers):
            status = False

        if not run_with_progress("Configuring firewall", self.configure_firewall):
            status = False

        if not run_with_progress("Configuring Fail2ban", self.configure_fail2ban):
            status = False

        return status

    def configure_ssh(self) -> bool:
        """Securely configure the SSH server."""
        self.print_section("SSH Configuration")

        # Ensure openssh-server is installed
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "openssh-server"],
                check=False,
                capture_output=True,
                text=True,
            )
            if "install ok installed" not in result.stdout:
                self.logger.info("openssh-server not installed; installing...")
                try:
                    self.run_command(["apt-get", "install", "-y", "openssh-server"])
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install OpenSSH Server.")
                    return False
        except Exception:
            try:
                self.run_command(["apt-get", "install", "-y", "openssh-server"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install OpenSSH Server.")
                return False

        # Enable and start SSH service
        try:
            self.run_command(["systemctl", "enable", "--now", "ssh"])
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable/start SSH service.")
            return False

        # Update SSH configuration
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config}")
            return False

        # Backup the SSH config file
        backup_path = backup_file(sshd_config)
        if backup_path:
            self.logger.info(f"Backed up SSH config to {backup_path}")

        try:
            # Read existing configuration
            lines = sshd_config.read_text().splitlines()

            # Remove existing settings that we want to override
            modified_lines = [
                line
                for line in lines
                if not any(
                    line.strip().startswith(key) or line.strip().startswith(f"#{key}")
                    for key in self.config.SSH_SETTINGS
                )
            ]

            # Add our secure settings
            modified_lines.append("\n# Security settings from setup script")
            for key, val in self.config.SSH_SETTINGS.items():
                modified_lines.append(f"{key} {val}")

            # Write the modified configuration
            sshd_config.write_text("\n".join(modified_lines) + "\n")

            # Restart SSH service to apply changes
            self.run_command(["systemctl", "restart", "ssh"])

            self.logger.info("SSH configuration updated and service restarted.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """Ensure the user has sudo privileges."""
        self.print_section("Sudo Configuration")

        try:
            # Ensure sudo is installed
            if not command_exists("sudo"):
                self.logger.info("sudo not installed; installing...")
                self.run_command(["apt-get", "install", "-y", "sudo"])

            # Check if user is already in sudo group
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )

            if "sudo" not in result.stdout.split():
                # Add user to sudo group
                self.run_command(["usermod", "-aG", "sudo", self.config.USERNAME])
                self.logger.info(f"Added {self.config.USERNAME} to sudo group.")

            # Add a custom sudoers entry for the user
            user_sudoers = Path("/etc/sudoers.d") / self.config.USERNAME
            user_sudoers.write_text(f"{self.config.USERNAME} ALL=(ALL) ALL\n")

            # Set correct permissions on the sudoers file
            user_sudoers.chmod(0o440)

            self.logger.info(f"Sudoers entry created for {self.config.USERNAME}.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Sudoers configuration failed: {e}")
            return False

    def configure_firewall(self, ports: Optional[List[str]] = None) -> bool:
        """Configure UFW firewall to allow only required ports."""
        self.print_section("Firewall Configuration")

        if ports is None:
            ports = self.config.FIREWALL_PORTS

        # Ensure UFW is installed
        if not command_exists("ufw"):
            try:
                self.run_command(["apt-get", "install", "-y", "ufw"])
                self.logger.info("UFW installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install UFW.")
                return False

        try:
            # Reset to default state
            self.run_command(["ufw", "--force", "reset"])

            # Set default policies
            self.run_command(["ufw", "default", "deny", "incoming"])
            self.run_command(["ufw", "default", "allow", "outgoing"])

            # Allow required ports
            for port in ports:
                self.run_command(["ufw", "allow", f"{port}/tcp"])
                self.logger.info(f"Allowed TCP port {port}.")

            # Enable UFW
            self.run_command(["ufw", "--force", "enable"])
            self.run_command(["systemctl", "enable", "ufw"])
            self.run_command(["systemctl", "start", "ufw"])

            self.logger.info("UFW enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Firewall configuration failed: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """Install and configure Fail2ban for SSH protection."""
        self.print_section("Fail2ban Configuration")

        # Ensure Fail2ban is installed
        if not command_exists("fail2ban-server"):
            try:
                self.run_command(["apt-get", "install", "-y", "fail2ban"])
                self.logger.info("Fail2ban installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install Fail2ban.")
                return False

        # Configure Fail2ban
        jail_local = Path("/etc/fail2ban/jail.local")
        config_content = (
            "[DEFAULT]\n"
            "bantime  = 600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n"
        )

        # Backup existing config if it exists
        if jail_local.is_file():
            backup_path = backup_file(jail_local)
            if backup_path:
                self.logger.info(f"Backed up Fail2ban config to {backup_path}")

        try:
            # Write the configuration
            jail_local.write_text(config_content)
            self.logger.info("Fail2ban configuration updated.")

            # Enable and restart the service
            self.run_command(["systemctl", "enable", "fail2ban"])
            self.run_command(["systemctl", "restart", "fail2ban"])

            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to manage Fail2ban service: {e}")
            return False

    # --- Phase 5: Essential Service Installation ---
    def phase_service_installation(self) -> bool:
        """Install and configure essential services."""
        self.print_section("Essential Service Installation")
        status = True

        if not run_with_progress(
            "Configuring Docker", self.docker_config, task_name="services"
        ):
            status = False

        if not run_with_progress(
            "Installing Plex Media Server", self.install_plex, task_name="services"
        ):
            status = False

        if not run_with_progress(
            "Installing Fastfetch", self.install_fastfetch, task_name="services"
        ):
            status = False

        return status

    def docker_config(self) -> bool:
        """Install and configure Docker and Docker Compose."""
        self.print_section("Docker Configuration")

        # Check if Docker is already installed
        if command_exists("docker"):
            self.logger.info("Docker is already installed.")
        else:
            try:
                # Add Docker repository keyring
                self.logger.info("Adding Docker repository...")
                self.run_command(
                    [
                        "curl",
                        "-fsSL",
                        "https://download.docker.com/linux/debian/gpg",
                        "-o",
                        "/etc/apt/keyrings/docker.asc",
                    ]
                )

                # Ensure keyring directory exists
                Path("/etc/apt/keyrings").mkdir(exist_ok=True)

                # Add Docker repository
                docker_sources = Path("/etc/apt/sources.list.d/docker.list")
                docker_sources.write_text(
                    "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable\n"
                )

                # Update package lists
                self.run_command(["apt-get", "update", "-qq"])

                # Install Docker
                self.run_command(
                    [
                        "apt-get",
                        "install",
                        "-y",
                        "docker-ce",
                        "docker-ce-cli",
                        "containerd.io",
                        "docker-buildx-plugin",
                    ]
                )

                self.logger.info("Docker installed.")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Docker CE: {e}")
                try:
                    # Fallback to docker.io package
                    self.logger.info("Trying fallback installation with docker.io...")
                    self.run_command(["apt-get", "install", "-y", "docker.io"])
                    self.logger.info("Docker installed via fallback method.")
                except subprocess.CalledProcessError:
                    self.logger.error("Docker installation failed via all methods.")
                    return False

        # Add user to docker group
        try:
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )

            if "docker" not in result.stdout.split():
                self.run_command(["usermod", "-aG", "docker", self.config.USERNAME])
                self.logger.info(f"Added {self.config.USERNAME} to docker group.")
            else:
                self.logger.info(f"{self.config.USERNAME} already in docker group.")
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to modify docker group membership for {self.config.USERNAME}."
            )

        # Configure Docker daemon
        daemon_json = Path("/etc/docker/daemon.json")
        daemon_json.parent.mkdir(exist_ok=True)

        desired_config = {
            "log-driver": "json-file",
            "log-opts": {"max-size": "10m", "max-file": "3"},
            "exec-opts": ["native.cgroupdriver=systemd"],
        }

        write_config = True

        if daemon_json.is_file():
            try:
                existing = json.loads(daemon_json.read_text())
                if existing == desired_config:
                    self.logger.info("Docker daemon configuration is up-to-date.")
                    write_config = False
                else:
                    backup_path = backup_file(daemon_json)
                    if backup_path:
                        self.logger.info(
                            f"Backed up Docker daemon config to {backup_path}"
                        )
            except Exception as e:
                self.logger.warning(f"Error reading {daemon_json}: {e}")
                backup_file(daemon_json)

        # Write daemon configuration if needed
        if write_config:
            try:
                daemon_json.write_text(json.dumps(desired_config, indent=2))
                self.logger.info("Docker daemon configuration updated.")
            except Exception as e:
                self.logger.warning(f"Failed to write {daemon_json}: {e}")

        # Enable and restart Docker service
        try:
            self.run_command(["systemctl", "enable", "docker"])
            self.run_command(["systemctl", "restart", "docker"])
            self.logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Docker service: {e}")
            return False

        # Install Docker Compose if needed
        if not command_exists("docker-compose"):
            try:
                dest = Path("/usr/local/bin/docker-compose")
                self.download_file(self.config.DOCKER_COMPOSE_URL, dest)
                dest.chmod(0o755)
                self.logger.info("Docker Compose installed.")
            except Exception as e:
                self.logger.error(f"Failed to install Docker Compose: {e}")
                return False
        else:
            self.logger.info("Docker Compose already installed.")

        return True

    def install_plex(self) -> bool:
        """Install Plex Media Server."""
        self.print_section("Plex Media Server Installation")

        # Check if Plex is already installed
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "plexmediaserver"],
                check=False,
                capture_output=True,
                text=True,
            )
            if "install ok installed" in result.stdout:
                self.logger.info("Plex Media Server is already installed.")
                return True
        except Exception:
            pass

        # Download and install Plex
        temp_deb = Path("/tmp/plexmediaserver.deb")
        try:
            self.logger.info(
                f"Downloading Plex Media Server from {self.config.PLEX_URL}..."
            )
            self.download_file(self.config.PLEX_URL, temp_deb)

            self.logger.info("Installing Plex Media Server...")
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning(
                "dpkg reported issues with Plex; attempting to fix dependencies..."
            )
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Plex dependencies.")
                return False

        # Configure Plex to run as the specified user
        plex_conf = Path("/etc/default/plexmediaserver")
        if plex_conf.is_file():
            try:
                conf = plex_conf.read_text()
                if f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}" not in conf:
                    new_conf = [
                        f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}"
                        if line.startswith("PLEX_MEDIA_SERVER_USER=")
                        else line
                        for line in conf.splitlines()
                    ]
                    plex_conf.write_text("\n".join(new_conf) + "\n")
                    self.logger.info(
                        f"Configured Plex to run as {self.config.USERNAME}."
                    )
            except Exception as e:
                self.logger.warning(f"Failed to update Plex configuration: {e}")
        else:
            self.logger.warning(
                f"{plex_conf} not found; skipping Plex user configuration."
            )

        # Enable and restart Plex service
        try:
            self.run_command(["systemctl", "enable", "plexmediaserver"])
            self.run_command(["systemctl", "restart", "plexmediaserver"])
            self.logger.info("Plex service enabled and restarted.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to manage Plex service.")

        # Clean up the downloaded file
        try:
            temp_deb.unlink()
        except Exception:
            pass

        self.logger.info("Plex Media Server installation complete.")
        return True

    def install_fastfetch(self) -> bool:
        """Install Fastfetch."""
        self.print_section("Fastfetch Installation")

        # Check if Fastfetch is already installed
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "fastfetch"],
                check=False,
                capture_output=True,
                text=True,
            )
            if "install ok installed" in result.stdout or command_exists("fastfetch"):
                self.logger.info("Fastfetch is already installed.")
                return True
        except Exception:
            pass

        # Download and install Fastfetch
        temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")
        try:
            self.logger.info(
                f"Downloading Fastfetch from {self.config.FASTFETCH_URL}..."
            )
            self.download_file(self.config.FASTFETCH_URL, temp_deb)

            self.logger.info("Installing Fastfetch...")
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning(
                "Fastfetch installation issues; attempting dependency fix..."
            )
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Fastfetch dependencies.")
                return False

        # Clean up the downloaded file
        try:
            temp_deb.unlink()
        except Exception:
            pass

        # Verify installation
        if command_exists("fastfetch"):
            self.logger.info("Fastfetch installed successfully.")
            return True
        else:
            self.logger.warning("Fastfetch installation verification failed.")
            return False

    # --- Phase 6: User Customization & Script Deployment ---
    def phase_user_customization(self) -> bool:
        """Deploy user customization files and scripts."""
        self.print_section("User Customization & Script Deployment")
        return run_with_progress(
            "Deploying user scripts", self.deploy_user_scripts, task_name="user_custom"
        )

    def deploy_user_scripts(self) -> bool:
        """Deploy user scripts to the user's bin directory."""
        self.print_section("User Scripts Deployment")

        src = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "debian" / "_scripts"
        )
        target = self.config.USER_HOME / "bin"

        # Create sample scripts if source directory is not found
        if not src.is_dir():
            self.logger.info(f"Script source {src} not found; creating sample scripts.")
            src.parent.mkdir(parents=True, exist_ok=True)
            src.mkdir(exist_ok=True)

            # Create system update script
            (src / "update-system.sh").write_text(
                r"""#!/bin/bash
echo "Updating system packages..."
sudo nala update && sudo nala upgrade -y
echo "Cleaning up..."
sudo nala autoremove -y && sudo nala clean
echo "System update complete."
"""
            )

            # Create home backup script
            (src / "backup-home.sh").write_text(
                r"""#!/bin/bash
BACKUP_DIR="/var/backups/home_backup"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_FILE="$BACKUP_DIR/home_backup_$TIMESTAMP.tar.gz"
sudo mkdir -p "$BACKUP_DIR"
echo "Backing up home directory..."
tar -czf "$BACKUP_FILE" --exclude="*/node_modules" --exclude="*/.cache" \
    --exclude="*/venv" --exclude="*/.venv" --exclude="*/__pycache__" -C /home .
echo "Backup complete: $BACKUP_FILE"
"""
            )

            # Set appropriate ownership
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(src),
                ]
            )

        # Create the target directory
        target.mkdir(exist_ok=True)

        try:
            # Use rsync to copy scripts
            self.run_command(["rsync", "-ah", "--delete", f"{src}/", f"{target}/"])

            # Set executable permissions
            self.run_command(
                ["find", str(target), "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )

            # Set appropriate ownership
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(target),
                ]
            )

            self.logger.info("User scripts deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Script deployment failed: {e}")
            return False

    # --- Phase 7: Maintenance & Monitoring ---
    def phase_maintenance_monitoring(self) -> bool:
        """Configure maintenance tasks and monitoring."""
        self.print_section("Maintenance & Monitoring")
        status = True

        if not run_with_progress(
            "Configuring periodic maintenance",
            self.configure_periodic,
            task_name="maintenance",
        ):
            status = False

        if not run_with_progress("Backing up configuration files", self.backup_configs):
            status = False

        if not run_with_progress("Rotating logs", self.rotate_logs):
            status = False

        run_with_progress("Performing system health check", self.system_health_check)

        run_with_progress("Verifying firewall rules", self.verify_firewall_rules)

        return status

    def configure_periodic(self) -> bool:
        """Set up daily maintenance tasks via cron and APT periodic settings."""
        self.print_section("Periodic Maintenance Setup")

        # Configure APT periodic tasks
        apt_periodic = Path("/etc/apt/apt.conf.d/02periodic")
        periodic_content = r"""// APT periodic tasks configuration
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
"""

        try:
            apt_periodic.write_text(periodic_content)
            self.logger.info("APT periodic tasks configured.")
        except Exception as e:
            self.logger.warning(f"Failed to configure APT periodic tasks: {e}")

        # Set up daily maintenance cron job
        cron_file = Path("/etc/cron.daily/debian_maintenance")
        marker = "# Debian maintenance script"

        if cron_file.is_file() and marker in cron_file.read_text():
            self.logger.info("Daily maintenance cron job already exists.")
            return True

        # Backup existing file if it exists
        if cron_file.is_file():
            backup_path = backup_file(cron_file)
            if backup_path:
                self.logger.info(f"Backed up cron job to {backup_path}")

        # Create maintenance script content (using nala if available)
        content = r"""#!/bin/sh
# Debian maintenance script
"""

        # Use nala if available, otherwise use apt
        content += "if command -v nala > /dev/null; then\n"
        content += "    nala update -qq\n"
        content += "    nala upgrade -y\n"
        content += "    nala autoremove -y\n"
        content += "    nala clean\n"
        content += "else\n"
        content += "    apt-get update -qq\n"
        content += "    apt-get upgrade -y\n"
        content += "    apt-get autoremove -y\n"
        content += "    apt-get autoclean -y\n"
        content += "fi\n\n"

        # Add additional maintenance tasks
        content += r"""dpkg --audit || true
if command -v fstrim > /dev/null; then
    fstrim -av || true
fi
if command -v mandb > /dev/null; then
    mandb -q || true
fi
if command -v updatedb > /dev/null; then
    updatedb || true
fi
echo "$(date): Maintenance complete" >> /var/log/debian_maintenance.log
"""

        try:
            cron_file.write_text(content)
            cron_file.chmod(0o755)
            self.logger.info(f"Created daily maintenance script at {cron_file}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> Optional[str]:
        """Backup important configuration files."""
        self.print_section("Configuration Backups")

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path(f"/var/backups/debian_config_{timestamp}")

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            count = 0

            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn(
                    f"[bold {NordColors.FROST_2}]Backing up configuration files..."
                ),
                BarColumn(complete_style=f"{NordColors.GREEN}"),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Backing up", total=len(self.config.CONFIG_BACKUP_FILES)
                )

                for file in self.config.CONFIG_BACKUP_FILES:
                    fpath = Path(file)
                    if fpath.is_file():
                        dest_path = backup_dir / fpath.name
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(fpath, dest_path)
                        self.logger.info(f"Backed up {fpath}")
                        count += 1
                    else:
                        self.logger.warning(f"{fpath} not found; skipping.")

                    progress.update(task, advance=1)

            if count:
                # Create a summary file
                (backup_dir / "backup_info.txt").write_text(
                    f"Backup: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Host: {platform.node()}\n"
                    f"Files backed up: {count}\n"
                )

                self.logger.info(f"Configuration backed up to {backup_dir}")
                return str(backup_dir)
            else:
                self.logger.warning("No configuration files backed up.")
                try:
                    backup_dir.rmdir()
                except Exception:
                    pass
                return None
        except Exception as e:
            self.logger.warning(f"Failed to backup configurations: {e}")
            return None

    def rotate_logs(self, log_file: Optional[str] = None) -> bool:
        """Rotate the main log file."""
        self.print_section("Log Rotation")

        if log_file is None:
            log_file = self.config.LOG_FILE

        log_path = Path(log_file)
        if not log_path.is_file():
            self.logger.warning(f"Log file {log_path} does not exist.")
            return False

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rotated = f"{log_path}.{timestamp}.gz"

            self.logger.info(f"Rotating log file {log_path} to {rotated}")

            # Compress the log file
            with open(log_path, "rb") as f_in, gzip.open(rotated, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Clear the original log file
            open(log_path, "w").close()

            # Set secure permissions
            os.chmod(rotated, 0o600)

            self.logger.info(f"Log rotated to {rotated}")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def system_health_check(self) -> Dict[str, str]:
        """Perform system health checks."""
        self.print_section("System Health Check")

        info = {}

        try:
            # Get kernel version
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            self.logger.info(f"Kernel: {kernel}")
            info["kernel"] = kernel

            # Get system uptime
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            self.logger.info(f"Uptime: {uptime}")
            info["uptime"] = uptime

            # Check disk usage
            df_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            self.logger.info(f"Disk usage: {df_line}")
            info["disk_usage"] = df_line

            # Check memory usage
            free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((l for l in free_out if l.startswith("Mem:")), "")
            self.logger.info(f"Memory: {mem_line}")
            info["memory"] = mem_line

            # Get CPU information
            cpu_info = ""
            for line in subprocess.check_output(["lscpu"], text=True).splitlines():
                if "Model name" in line:
                    cpu_info = line.split(":", 1)[1].strip()
                    break
            self.logger.info(f"CPU: {cpu_info}")
            info["cpu"] = cpu_info

            # Get network interfaces
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            self.logger.info("Network interfaces:\n" + interfaces)
            info["network_interfaces"] = interfaces

            # Check for recent errors in system logs
            try:
                errors = subprocess.check_output(
                    ["journalctl", "-p", "err", "-n", "10", "--no-pager"], text=True
                ).strip()

                if errors:
                    self.logger.warning("Recent log errors:\n" + errors)
                    info["recent_errors"] = errors
                else:
                    self.logger.info("No recent errors found.")
                    info["recent_errors"] = "None"
            except Exception as e:
                self.logger.warning(f"Failed to check logs: {e}")

            # Check status of critical services
            critical_services = ["ssh", "ufw", "fail2ban"]
            services_status = {}

            for service in critical_services:
                try:
                    result = self.run_command(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    status = result.stdout.strip()
                    services_status[service] = status

                    if status == "active":
                        self.logger.info(f"Service {service} is active.")
                    else:
                        self.logger.warning(f"Service {service} is {status}.")
                except Exception as e:
                    self.logger.warning(f"Error checking {service}: {e}")
                    services_status[service] = "unknown"

            info["services"] = services_status

            return info
        except Exception as e:
            self.logger.warning(f"Health check error: {e}")
            return {"error": str(e)}

    def verify_firewall_rules(
        self, ports: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """Verify that the firewall is active and required ports are accessible."""
        self.print_section("Firewall Rules Verification")

        if ports is None:
            ports = self.config.FIREWALL_PORTS

        results = {}

        try:
            # Check if UFW is active
            ufw_status = self.run_command(
                ["ufw", "status"], capture_output=True, text=True
            )

            if "Status: active" in ufw_status.stdout:
                self.logger.info("UFW is active.")
                results["ufw_active"] = True
            else:
                self.logger.warning("UFW is not active.")
                results["ufw_active"] = False
        except Exception as e:
            self.logger.warning(f"Error checking UFW status: {e}")
            results["ufw_active"] = False

        # Test each required port
        for port in ports:
            try:
                subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.logger.info(f"Port {port} is accessible.")
                results[port] = True
            except subprocess.CalledProcessError:
                self.logger.warning(f"Port {port} is not accessible.")
                results[port] = False

        return results

    # --- Phase 8: Certificates & Performance Tuning ---
    def phase_certificates_performance(self) -> bool:
        """Configure certificates and tune system performance."""
        self.print_section("Certificates & Performance Tuning")
        status = True

        if not run_with_progress(
            "Updating SSL certificates",
            self.update_ssl_certificates,
            task_name="certs_perf",
        ):
            status = False

        if not run_with_progress(
            "Applying performance tuning", self.tune_system, task_name="certs_perf"
        ):
            status = False

        return status

    def update_ssl_certificates(self) -> bool:
        """Renew SSL certificates via certbot."""
        self.print_section("SSL Certificates Update")

        # Ensure certbot is installed
        if not command_exists("certbot"):
            try:
                self.run_command(["apt-get", "install", "-y", "certbot"])
                self.logger.info("certbot installed.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to install certbot.")
                return False

        try:
            # Check for existing certificates
            certbot_certs = self.run_command(
                ["certbot", "certificates"], capture_output=True, text=True, check=False
            )

            if "No certificates found" in certbot_certs.stdout:
                self.logger.info("No SSL certificates to renew.")
                return True

            # Renew certificates
            self.run_command(["certbot", "renew", "--non-interactive"])
            self.logger.info("SSL certificates renewed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"SSL certificate renewal failed: {e}")
            return False

    def tune_system(self) -> bool:
        """Apply sysctl and I/O scheduler tuning for improved performance."""
        self.print_section("Performance Tuning")

        # Configure sysctl parameters
        sysctl_file = Path("/etc/sysctl.conf")
        marker = "# Performance tuning for Debian Trixie"

        try:
            current = sysctl_file.read_text() if sysctl_file.is_file() else ""

            if marker not in current:
                # Backup existing file if it exists
                if sysctl_file.is_file():
                    backup_path = backup_file(sysctl_file)
                    if backup_path:
                        self.logger.info(f"Backed up sysctl.conf to {backup_path}")

                # Append performance tuning settings
                tuning = f"""
{marker}
fs.file-max = 100000
net.core.somaxconn = 128
net.ipv4.tcp_rmem = 4096 87380 6291456
net.ipv4.tcp_wmem = 4096 16384 4194304
net.ipv4.tcp_max_syn_backlog = 4096
net.core.netdev_max_backlog = 4096
vm.swappiness = 10
vm.vfs_cache_pressure = 50
"""
                with open(sysctl_file, "a") as f:
                    f.write(tuning)

                # Apply the settings
                self.run_command(["sysctl", "-p"])
                self.logger.info("Performance tuning applied via sysctl.")
            else:
                self.logger.info("Performance tuning already configured.")

            # Configure I/O schedulers for block devices
            if Path("/sys/block").is_dir():
                for device in Path("/sys/block").iterdir():
                    if device.is_dir() and device.name.startswith(("sd", "nvme", "vd")):
                        scheduler_file = device / "queue" / "scheduler"

                        if scheduler_file.is_file():
                            try:
                                # Check if device is SSD (non-rotational)
                                rotational = (
                                    (device / "queue" / "rotational")
                                    .read_text()
                                    .strip()
                                )

                                if rotational == "0":
                                    # Device is an SSD
                                    current_scheduler = (
                                        scheduler_file.read_text().strip()
                                    )

                                    if "[none]" not in current_scheduler:
                                        # Set appropriate scheduler
                                        if "none" in current_scheduler:
                                            scheduler_file.write_text("none")
                                        elif "mq-deadline" in current_scheduler:
                                            scheduler_file.write_text("mq-deadline")
                                        elif "deadline" in current_scheduler:
                                            scheduler_file.write_text("deadline")

                                        self.logger.info(
                                            f"Set I/O scheduler for {device.name}."
                                        )
                            except Exception as e:
                                self.logger.debug(
                                    f"Could not set scheduler for {device.name}: {e}"
                                )

            return True
        except Exception as e:
            self.logger.warning(f"Performance tuning failed: {e}")
            return False

    # --- Phase 9: Permissions & Advanced Storage ---
    def phase_permissions_storage(self) -> bool:
        """Configure permissions and storage options."""
        self.print_section("Permissions & Advanced Storage Setup")
        status = True

        if not run_with_progress(
            "Configuring home directory permissions",
            self.home_permissions,
            task_name="permissions_storage",
        ):
            status = False

        if not run_with_progress(
            "Installing & Configuring ZFS",
            self.install_configure_zfs,
            task_name="permissions_storage",
        ):
            status = False

        return status

    def home_permissions(self) -> bool:
        """Set secure ownership and permissions for the home directory."""
        self.print_section("Home Directory Permissions")

        try:
            # Set ownership
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(self.config.USER_HOME),
                ]
            )

            # Set base directory permissions
            self.run_command(["chmod", "750", str(self.config.USER_HOME)])

            # Set group sticky bit on directories
            self.run_command(
                [
                    "find",
                    str(self.config.USER_HOME),
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    ";",
                ]
            )

            # Set ACLs if available
            if command_exists("setfacl"):
                try:
                    self.run_command(
                        [
                            "setfacl",
                            "-R",
                            "-d",
                            "-m",
                            f"u:{self.config.USERNAME}:rwx",
                            str(self.config.USER_HOME),
                        ]
                    )
                    self.logger.info("Default ACLs applied on home directory.")
                except subprocess.CalledProcessError:
                    self.logger.warning("Failed to apply default ACLs.")
            else:
                self.logger.warning("setfacl not found; skipping ACL configuration.")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Home directory permission configuration failed: {e}")
            return False

    def install_configure_zfs(self) -> bool:
        """Install and configure ZFS if available."""
        self.print_section("ZFS Installation & Configuration")

        pool = self.config.ZFS_POOL_NAME
        mount_point = self.config.ZFS_MOUNT_POINT

        # Check if ZFS is already installed
        zfs_installed = command_exists("zfs") and command_exists("zpool")

        if not zfs_installed:
            try:
                self.run_command(["apt-get", "install", "-y", "zfsutils-linux"])
                self.logger.info("ZFS packages installed.")
                zfs_installed = True
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install ZFS: {e}")
                return False

        if not zfs_installed:
            self.logger.error("ZFS installation failed; skipping.")
            return False

        # Enable ZFS services
        for service in ["zfs-import-cache.service", "zfs-mount.service"]:
            try:
                self.run_command(["systemctl", "enable", service])
                self.logger.info(f"Enabled {service}.")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Could not enable {service}.")

        # Create mount point
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Mount point {mount_point} ensured.")
        except Exception as e:
            self.logger.warning(f"Failed to create mount point {mount_point}: {e}")

        # Check if pool exists or import it
        pool_imported = False
        try:
            result = self.run_command(
                ["zpool", "list", pool], capture_output=True, check=False
            )

            if result.returncode == 0:
                self.logger.info(f"ZFS pool '{pool}' found.")
                pool_imported = True
            else:
                try:
                    self.run_command(["zpool", "import", "-f", pool])
                    self.logger.info(f"Imported ZFS pool '{pool}'.")
                    pool_imported = True
                except subprocess.CalledProcessError:
                    self.logger.warning(f"ZFS pool '{pool}' not found.")
        except Exception as e:
            self.logger.warning(f"Error checking ZFS pool: {e}")

        if not pool_imported:
            self.logger.info("No ZFS pool found; skipping ZFS configuration.")
            return True

        # Configure pool and mount it
        try:
            # Set mount point
            self.run_command(["zfs", "set", f"mountpoint={mount_point}", pool])
            self.logger.info(f"Set mountpoint for pool '{pool}'.")

            # Update cache file
            cache_file = Path("/etc/zfs/zpool.cache")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.run_command(["zpool", "set", f"cachefile={cache_file}", pool])
            self.logger.info(f"Updated cachefile for pool '{pool}'.")

            # Mount all ZFS datasets
            self.run_command(["zfs", "mount", "-a"])
            self.logger.info("Mounted all ZFS datasets.")

            # Verify mount
            mounts = subprocess.check_output(
                ["zfs", "list", "-o", "name,mountpoint", "-H"], text=True
            )

            if any(str(mount_point) in line for line in mounts.splitlines()):
                self.logger.info(f"ZFS pool '{pool}' mounted at {mount_point}.")
                return True
            else:
                self.logger.warning(f"ZFS pool '{pool}' not mounted at {mount_point}.")
                return False
        except Exception as e:
            self.logger.warning(f"Error configuring ZFS: {e}")
            return False

    # --- Phase 10: Additional Applications & Tools ---
    def phase_additional_apps(self) -> bool:
        """Install additional applications and tools."""
        self.print_section("Additional Applications & Tools")
        status = True

        if not run_with_progress(
            "Installing Brave browser",
            self.install_brave_browser,
            task_name="additional_apps",
        ):
            status = False

        apps_success, apps_failed = run_with_progress(
            "Installing Flatpak applications",
            self.install_flatpak_and_apps,
            task_name="additional_apps",
        )

        if apps_failed and len(apps_failed) > len(self.config.FLATPAK_APPS) * 0.1:
            self.logger.error(
                f"Flatpak app installation failures: {', '.join(apps_failed)}"
            )
            status = False

        if not run_with_progress(
            "Installing VS Code Stable",
            self.install_configure_vscode_stable,
            task_name="additional_apps",
        ):
            status = False

        return status

    def install_brave_browser(self) -> bool:
        """Install Brave browser."""
        self.print_section("Brave Browser Installation")

        # Check if Brave is already installed
        if command_exists("brave-browser"):
            self.logger.info("Brave browser is already installed.")
            return True

        try:
            # Create keyring directory
            Path("/etc/apt/keyrings").mkdir(parents=True, exist_ok=True)

            # Download Brave keyring
            self.run_command(
                [
                    "curl",
                    "-fsSL",
                    "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg",
                    "-o",
                    "/etc/apt/keyrings/brave-browser-archive-keyring.gpg",
                ]
            )

            # Add Brave repository
            brave_sources = Path("/etc/apt/sources.list.d/brave-browser-release.list")
            brave_sources.write_text(
                "deb [signed-by=/etc/apt/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main\n"
            )

            # Update package lists
            self.run_command(["apt-get", "update", "-qq"])

            # Install Brave browser
            self.run_command(["apt-get", "install", "-y", "brave-browser"])

            self.logger.info("Brave browser installed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Brave browser: {e}")
            return False

    def install_flatpak_and_apps(self) -> Tuple[List[str], List[str]]:
        """Install Flatpak and Flatpak applications."""
        self.print_section("Flatpak Installation & Setup")

        # Ensure Flatpak is installed
        if not command_exists("flatpak"):
            try:
                self.run_command(["apt-get", "install", "-y", "flatpak"])
                self.logger.info("Flatpak installed.")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Flatpak: {e}")
                return [], self.config.FLATPAK_APPS

        # Install Flatpak GNOME plugin
        try:
            self.run_command(
                ["apt-get", "install", "-y", "gnome-software-plugin-flatpak"]
            )
            self.logger.info("Flatpak GNOME plugin installed.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install Flatpak plugin: {e}")

        # Add Flathub repository
        try:
            self.run_command(
                [
                    "flatpak",
                    "remote-add",
                    "--if-not-exists",
                    "flathub",
                    "https://dl.flathub.org/repo/flathub.flatpakrepo",
                ]
            )
            self.logger.info("Flathub repository added.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to add Flathub repository: {e}")
            return [], self.config.FLATPAK_APPS

        # Install Flatpak applications
        successful = []
        failed = []

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing Flatpak apps..."),
            BarColumn(complete_style=f"{NordColors.GREEN}"),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Installing", total=len(self.config.FLATPAK_APPS))

            for app in self.config.FLATPAK_APPS:
                try:
                    # Check if app is already installed
                    result = self.run_command(
                        ["flatpak", "list", "--app", "--columns=application"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    if app in result.stdout:
                        self.logger.info(f"Flatpak app already installed: {app}")
                        successful.append(app)
                    else:
                        # Install the app
                        self.run_command(
                            ["flatpak", "install", "--assumeyes", "flathub", app]
                        )
                        self.logger.info(f"Installed Flatpak app: {app}")
                        successful.append(app)
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to install Flatpak app {app}: {e}")
                    failed.append(app)

                progress.update(task, advance=1)

        return successful, failed

    def install_configure_vscode_stable(self) -> bool:
        """Install and configure Visual Studio Code Stable."""
        self.print_section("VS Code Installation & Configuration")

        # Check if VS Code is already installed
        if command_exists("code"):
            self.logger.info("VS Code is already installed.")
            return True

        # Download VS Code package
        vscode_url = "https://go.microsoft.com/fwlink/?LinkID=760868"
        deb_path = Path("/tmp/code.deb")

        try:
            self.logger.info("Downloading VS Code...")
            self.download_file(vscode_url, deb_path)
        except Exception as e:
            self.logger.error(f"Failed to download VS Code: {e}")
            return False

        # Install VS Code
        try:
            self.logger.info("Installing VS Code...")
            self.run_command(["dpkg", "-i", str(deb_path)])
        except subprocess.CalledProcessError:
            self.logger.warning(
                "dpkg issues during VS Code installation; fixing dependencies..."
            )
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix VS Code dependencies: {e}")
                return False

        # Clean up the downloaded file
        try:
            deb_path.unlink()
        except Exception:
            pass

        # Configure VS Code for Wayland
        desktop_file = Path("/usr/share/applications/code.desktop")
        if desktop_file.exists():
            try:
                content = desktop_file.read_text()
                wayland_exec = "/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F"
                content = re.sub(r"Exec=.*", f"Exec={wayland_exec}", content)
                desktop_file.write_text(content)
                self.logger.info("Updated VS Code desktop file for Wayland.")
            except Exception as e:
                self.logger.warning(f"Failed to update VS Code desktop file: {e}")

        # Create default settings
        vscode_config_dir = self.config.USER_HOME / ".config" / "Code" / "User"
        vscode_config_dir.mkdir(parents=True, exist_ok=True)
        settings_file = vscode_config_dir / "settings.json"

        if not settings_file.exists():
            settings = {
                "editor.fontFamily": "'Fira Code', 'Droid Sans Mono', 'monospace'",
                "editor.fontSize": 14,
                "editor.renderWhitespace": "boundary",
                "editor.rulers": [80, 120],
                "editor.minimap.enabled": True,
                "workbench.startupEditor": "none",
                "workbench.colorTheme": "Default Dark Modern",
                "window.titleBarStyle": "custom",
                "files.autoSave": "afterDelay",
                "terminal.integrated.fontFamily": "'Fira Code', monospace",
                "telemetry.telemetryLevel": "off",
            }

            try:
                settings_file.write_text(json.dumps(settings, indent=2))
                self.logger.info("Created default VS Code settings.")
            except Exception as e:
                self.logger.warning(f"Failed to create VS Code settings: {e}")

        # Set appropriate ownership
        try:
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(vscode_config_dir.parent),
                ]
            )
        except Exception as e:
            self.logger.warning(f"Failed to set VS Code config permissions: {e}")

        return True

    # --- Phase 11: Automatic Updates & Additional Security ---
    def phase_automatic_updates_security(self) -> bool:
        """Configure automatic updates and additional security measures."""
        self.print_section("Automatic Updates & Additional Security")
        status = True

        if not run_with_progress(
            "Configuring unattended upgrades",
            self.configure_unattended_upgrades,
            task_name="auto_updates",
        ):
            status = False

        if not run_with_progress(
            "Configuring AppArmor", self.configure_apparmor, task_name="auto_updates"
        ):
            status = False

        return status

    def configure_unattended_upgrades(self) -> bool:
        """Configure automatic security updates."""
        self.print_section("Unattended Upgrades Configuration")

        try:
            # Install required packages
            self.run_command(
                ["apt-get", "install", "-y", "unattended-upgrades", "apt-listchanges"]
            )

            # Configure automatic updates
            auto_file = Path("/etc/apt/apt.conf.d/20auto-upgrades")
            auto_file.write_text(
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )

            # Configure unattended upgrades
            unattended_file = Path("/etc/apt/apt.conf.d/50unattended-upgrades")

            # Backup existing file if it exists
            if unattended_file.exists():
                backup_path = backup_file(unattended_file)
                if backup_path:
                    self.logger.info(
                        f"Backed up unattended-upgrades config to {backup_path}"
                    )

            # Write the configuration
            unattended_file.write_text(
                "Unattended-Upgrade::Origins-Pattern {\n"
                '    "origin=Debian,codename=${distro_codename},label=Debian";\n'
                '    "origin=Debian,codename=${distro_codename},label=Debian-Security";\n'
                '    "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";\n'
                "};\n"
                "Unattended-Upgrade::Package-Blacklist {};\n"
                'Unattended-Upgrade::Automatic-Reboot "false";\n'
                'Unattended-Upgrade::Automatic-Reboot-Time "02:00";\n'
                'Unattended-Upgrade::SyslogEnable "true";\n'
            )

            # Enable and restart the service
            self.run_command(["systemctl", "enable", "unattended-upgrades"])
            self.run_command(["systemctl", "restart", "unattended-upgrades"])

            self.logger.info("Unattended upgrades configured.")
            return True
        except Exception as e:
            self.logger.error(f"Unattended upgrades configuration failed: {e}")
            return False

    def configure_apparmor(self) -> bool:
        """Install and configure AppArmor."""
        self.print_section("AppArmor Configuration")

        try:
            # Ensure AppArmor is installed
            if not command_exists("apparmor_status"):
                self.run_command(
                    ["apt-get", "install", "-y", "apparmor", "apparmor-utils"]
                )
                self.logger.info("AppArmor installed.")

            # Check if AppArmor is enabled in the kernel
            status = self.run_command(
                ["apparmor_status"], capture_output=True, text=True, check=False
            )

            if "apparmor filesystem is not mounted" in status.stdout:
                self.logger.warning("AppArmor not enabled in kernel.")
                return False

            # Enable and start AppArmor
            self.run_command(["systemctl", "enable", "apparmor"])
            self.run_command(["systemctl", "start", "apparmor"])

            # Enforce all profiles
            self.run_command(["aa-enforce", "/etc/apparmor.d/*"], check=False)

            self.logger.info("AppArmor enabled and configured.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"AppArmor configuration failed: {e}")
            return False

    # --- Phase 12: Cleanup & Final Configurations ---
    def phase_cleanup_final(self) -> bool:
        """Perform final cleanup and configurations."""
        self.print_section("Cleanup & Final Configurations")
        status = True

        if not run_with_progress(
            "Cleaning up system", self.cleanup_system, task_name="cleanup_final"
        ):
            status = False

        if not run_with_progress(
            "Configuring Wayland environment",
            self.configure_wayland,
            task_name="cleanup_final",
        ):
            status = False

        if not run_with_progress(
            "Installing and enabling Tailscale",
            self.install_enable_tailscale,
            task_name="cleanup_final",
        ):
            status = False

        if not run_with_progress(
            "Installing & configuring Caddy",
            self.install_configure_caddy,
            task_name="cleanup_final",
        ):
            status = False

        return status

    def cleanup_system(self) -> bool:
        """Clean up unnecessary packages, files, and logs."""
        self.print_section("System Cleanup")

        try:
            # Clean up package cache and remove unnecessary packages
            if self.nala_available:
                self.run_command(["nala", "autoremove", "-y"])
                self.run_command(["nala", "clean"])
            else:
                self.run_command(["apt-get", "autoremove", "-y"])
                self.run_command(["apt-get", "autoclean", "-y"])
                self.run_command(["apt-get", "clean"])

            # Clean up old temporary files
            for tmp_dir in ["/tmp", "/var/tmp"]:
                self.run_command(
                    ["find", tmp_dir, "-type", "f", "-mtime", "+10", "-delete"]
                )

            # Clean up old log files
            self.run_command(
                [
                    "find",
                    "/var/log",
                    "-type",
                    "f",
                    "-name",
                    "*.gz",
                    "-mtime",
                    "+30",
                    "-delete",
                ]
            )

            # Truncate large log files
            self.run_command(
                [
                    "find",
                    "/var/log",
                    "-type",
                    "f",
                    "-size",
                    "+50M",
                    "-exec",
                    "truncate",
                    "-s",
                    "0",
                    "{}",
                    ";",
                ]
            )

            self.logger.info("System cleanup complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            return False

    def configure_wayland(self) -> bool:
        """Configure Wayland environment variables for global and user settings."""
        self.print_section("Wayland Environment Configuration")

        # Configure global environment variables
        etc_env = Path("/etc/environment")
        try:
            current = etc_env.read_text() if etc_env.is_file() else ""
            vars_current = {}

            # Parse existing variables
            for line in current.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.split("=", 1)
                    vars_current[key.strip()] = value.strip().strip('"')

            # Check if updates are needed
            updated = False
            for key, val in self.config.WAYLAND_ENV_VARS.items():
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True

            # Write updated configuration if needed
            if updated:
                # Backup existing file if it exists
                if etc_env.is_file():
                    backup_path = backup_file(etc_env)
                    if backup_path:
                        self.logger.info(
                            f"Backed up global environment to {backup_path}"
                        )

                new_content = "\n".join(f'{k}="{v}"' for k, v in vars_current.items())
                etc_env.write_text(new_content + "\n")
                self.logger.info(f"Updated {etc_env} with Wayland variables.")
            else:
                self.logger.info("No changes needed in global environment.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env}: {e}")

        # Configure user environment variables
        user_env_dir = self.config.USER_HOME / ".config" / "environment.d"
        user_env_file = user_env_dir / "wayland.conf"

        try:
            user_env_dir.mkdir(parents=True, exist_ok=True)

            # Create the content
            content = (
                "\n".join(f'{k}="{v}"' for k, v in self.config.WAYLAND_ENV_VARS.items())
                + "\n"
            )

            # Check if update is needed
            if user_env_file.is_file():
                if user_env_file.read_text().strip() != content.strip():
                    backup_path = backup_file(user_env_file)
                    if backup_path:
                        self.logger.info(f"Backed up user environment to {backup_path}")

                    user_env_file.write_text(content)
                    self.logger.info(f"Updated {user_env_file} with Wayland variables.")
            else:
                user_env_file.write_text(content)
                self.logger.info(f"Created {user_env_file} with Wayland variables.")

            # Set appropriate ownership
            self.run_command(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_file),
                ]
            )

            self.run_command(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_dir),
                ]
            )

            return True
        except Exception as e:
            self.logger.warning(f"Failed to update user environment: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        """Install and enable Tailscale VPN."""
        self.print_section("Tailscale Installation")

        # Check if Tailscale is already installed
        if command_exists("tailscale"):
            self.logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                # Download Tailscale keyring
                self.run_command(
                    [
                        "curl",
                        "-fsSL",
                        "https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg",
                        "-o",
                        "/usr/share/keyrings/tailscale-archive-keyring.gpg",
                    ]
                )

                # Add Tailscale repository
                tailscale_sources = Path("/etc/apt/sources.list.d/tailscale.list")
                tailscale_sources.write_text(
                    "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian trixie main\n"
                )

                # Update package lists
                self.run_command(["apt-get", "update", "-qq"])

                # Install Tailscale
                self.run_command(["apt-get", "install", "-y", "tailscale"])

                # Verify installation
                tailscale_installed = command_exists("tailscale")

                if tailscale_installed:
                    self.logger.info("Tailscale installed successfully.")
                else:
                    self.logger.error("Tailscale installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install Tailscale: {e}")
                return False

        try:
            # Enable and start Tailscale service
            self.run_command(["systemctl", "enable", "tailscaled"])
            self.run_command(["systemctl", "start", "tailscaled"])

            # Check if service is active
            status = self.run_command(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )

            if status.stdout.strip() == "active":
                self.logger.info(
                    "Tailscale service is active. (Authenticate manually via 'tailscale up' if required.)"
                )
                return True
            else:
                self.logger.warning("Tailscale service is not active.")
                return tailscale_installed
        except Exception as e:
            self.logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    def install_configure_caddy(self) -> bool:
        """Install and configure Caddy web server."""
        self.print_section("Caddy Installation & Configuration")

        # Check if Caddy is already installed
        if command_exists("caddy"):
            self.logger.info("Caddy is already installed.")
            return True

        # Download Caddy
        caddy_url = "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb"
        temp_deb = Path("/tmp/caddy_2.9.1_linux_amd64.deb")

        try:
            self.logger.info(f"Downloading Caddy from {caddy_url}...")
            self.download_file(caddy_url, temp_deb)
        except Exception as e:
            self.logger.error(f"Failed to download Caddy: {e}")
            return False

        # Install Caddy
        try:
            self.logger.info("Installing Caddy...")
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning(
                "dpkg issues during Caddy installation; fixing dependencies..."
            )
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix Caddy dependencies: {e}")
                return False

        # Clean up downloaded file
        try:
            temp_deb.unlink()
        except Exception:
            pass

        # Configure Caddy
        source_caddyfile = (
            self.config.USER_HOME
            / "github"
            / "bash"
            / "linux"
            / "debian"
            / "dotfiles"
            / "Caddyfile"
        )
        dest_caddyfile = Path("/etc/caddy/Caddyfile")

        if source_caddyfile.is_file():
            # Backup existing file if it exists
            if dest_caddyfile.exists():
                backup_path = backup_file(dest_caddyfile)
                if backup_path:
                    self.logger.info(f"Backed up Caddyfile to {backup_path}")

            try:
                shutil.copy2(source_caddyfile, dest_caddyfile)
                self.logger.info(f"Copied Caddyfile to {dest_caddyfile}")
            except Exception as e:
                self.logger.warning(f"Failed to copy Caddyfile: {e}")
        else:
            self.logger.warning(
                f"Source Caddyfile not found at {source_caddyfile}; creating minimal config."
            )

            # Create minimal configuration
            dest_caddyfile.parent.mkdir(parents=True, exist_ok=True)
            dest_caddyfile.write_text(
                r"""# Minimal Caddyfile
:80 {
    root * /var/www/html
    file_server
    log {
        output file /var/log/caddy/access.log
    }
}
"""
            )
            self.logger.info(f"Created minimal Caddyfile at {dest_caddyfile}")

        # Prepare log directories
        log_dir = Path("/var/log/caddy")
        try:
            log_dir.mkdir(mode=0o755, exist_ok=True)

            for fname in ["caddy.log", "access.log"]:
                fpath = log_dir / fname
                with open(fpath, "a"):
                    os.utime(fpath, None)
                    fpath.chmod(0o644)
                self.logger.info(f"Prepared log file: {fpath}")
        except Exception as e:
            self.logger.warning(f"Failed to prepare Caddy log files: {e}")

        # Prepare web root
        web_root = Path("/var/www/html")
        try:
            web_root.mkdir(parents=True, exist_ok=True)
            index_html = web_root / "index.html"

            if not index_html.exists():
                index_html.write_text(
                    r"""<!DOCTYPE html>
<html>
<head>
  <title>Caddy on Debian Trixie</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    h1 { color: #3B4252; }
    p { color: #A3BE8C; }
  </style>
</head>
<body>
  <h1>Caddy Server is Running</h1>
  <p>Your web server is configured successfully.</p>
</body>
</html>
"""
                )
                self.logger.info("Created test index.html page.")
        except Exception as e:
            self.logger.warning(f"Failed to set up web root: {e}")

        try:
            # Enable and start Caddy service
            self.run_command(["systemctl", "enable", "caddy"])
            self.run_command(["systemctl", "restart", "caddy"])

            self.logger.info("Caddy service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Caddy service: {e}")
            return False

    # --- Phase 13: Final Checks & Reboot ---
    def phase_final_checks(self) -> bool:
        """Perform final system checks before reboot."""
        self.print_section("Final System Checks")

        system_info = run_with_progress(
            "Performing final system checks", self.final_checks, task_name="final"
        )

        # Wait a moment to allow logs to be written
        time.sleep(2)

        # Display a summary of the setup
        self.print_setup_summary()

        # Schedule a reboot
        reboot = run_with_progress(
            "Scheduling system reboot", self.reboot_system, task_name="final"
        )

        return True

    def final_checks(self) -> Dict[str, str]:
        """Perform final system checks."""
        self.print_section("Final System Checks")

        info = {}

        try:
            # Get kernel version
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            self.logger.info(f"Kernel version: {kernel}")
            info["kernel"] = kernel

            # Get system uptime
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            self.logger.info(f"System uptime: {uptime}")
            info["uptime"] = uptime

            # Check disk usage
            df_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            self.logger.info(f"Disk usage (root): {df_line}")
            info["disk_usage"] = df_line

            # Check memory usage
            free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((l for l in free_out if l.startswith("Mem:")), "")
            self.logger.info(f"Memory usage: {mem_line}")
            info["memory"] = mem_line

            # Get CPU information
            cpu_info = ""
            for line in subprocess.check_output(["lscpu"], text=True).splitlines():
                if "Model name" in line:
                    cpu_info = line.split(":", 1)[1].strip()
                    break
            self.logger.info(f"CPU: {cpu_info}")
            info["cpu"] = cpu_info

            # Get network interfaces
            interfaces = subprocess.check_output(
                ["ip", "-brief", "address"], text=True
            ).strip()
            self.logger.info(f"Network interfaces:\n{interfaces}")
            info["network_interfaces"] = interfaces

            # Check for recent system errors
            try:
                errors = subprocess.check_output(
                    ["journalctl", "-p", "err", "-n", "5", "--no-pager"], text=True
                ).strip()

                if errors:
                    self.logger.warning(f"Recent system errors:\n{errors}")
                    info["recent_errors"] = errors
                else:
                    info["recent_errors"] = "None"
            except Exception as e:
                self.logger.warning(f"Failed to retrieve recent errors: {e}")
                info["recent_errors"] = "Error retrieving logs"

            self.logger.info("Final system checks completed successfully.")
        except Exception as e:
            self.logger.error(f"Final checks encountered an error: {e}")
            info["final_checks_error"] = str(e)

        return info

    def print_setup_summary(self) -> None:
        """Print a summary of the setup process."""
        self.print_section("Setup Summary")

        # Calculate elapsed time
        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        elapsed_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

        # Build the summary table
        table = Table(
            title=f"Debian Trixie Setup Summary",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=f"{NordColors.FROST_3}",
            box=box.ROUNDED,
        )

        table.add_column("Phase", style=f"bold {NordColors.FROST_2}")
        table.add_column("Status", style="bold")

        # Add a row for each phase
        for phase, data in SETUP_STATUS.items():
            status_style = {
                "success": NordColors.GREEN,
                "failed": NordColors.RED,
                "in_progress": NordColors.YELLOW,
                "pending": NordColors.FROST_3,
            }.get(data["status"].lower(), NordColors.FROST_2)

            table.add_row(
                phase.replace("_", " ").title(),
                f"[{status_style}]{data['status'].upper()}[/{status_style}]",
            )

        # Create the summary panel
        summary_panel = Panel(
            Group(
                Text(
                    f"Total elapsed time: {elapsed_str}",
                    style=f"bold {NordColors.FROST_2}",
                ),
                Text(
                    f"Completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    style=f"{NordColors.FROST_2}",
                ),
                table,
                Text(
                    "\nLog file: " + self.config.LOG_FILE, style=f"{NordColors.FROST_3}"
                ),
                Text(
                    "System will reboot shortly to complete the setup.",
                    style=f"bold {NordColors.YELLOW}",
                ),
            ),
            title="Setup Complete",
            title_align="center",
            border_style=f"bold {NordColors.FROST_1}",
            padding=(1, 2),
        )

        console.print(summary_panel)

        # Log the summary
        self.logger.info(f"Setup completed in {elapsed_str}")
        self.logger.info(
            f"Final status: {', '.join([f'{k}: {v["status"]}' for k, v in SETUP_STATUS.items()])}"
        )

    def reboot_system(self) -> bool:
        """Reboot the system after completing setup."""
        self.print_section("System Reboot")

        try:
            reboot_delay = 10  # seconds
            self.logger.info(f"System will reboot in {reboot_delay} seconds...")

            console.print(
                f"[bold {NordColors.YELLOW}]System will reboot in {reboot_delay} seconds. Please save any work.[/]"
            )

            # Give time for logs to be written and for the user to see the message
            time.sleep(reboot_delay)

            # Execute the reboot command
            self.run_command(["shutdown", "-r", "now"])

            return True
        except Exception as e:
            self.logger.error(f"Failed to reboot the system: {e}")
            return False


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> int:
    """Main function that runs the setup process."""
    # Display banner
    console.print(create_header("Debian Trixie Setup"))

    try:
        # Initialize the setup class
        setup = DebianTrixieSetup()

        # Define the phases to run
        phases = [
            ("Nala APT Frontend Installation", setup.phase_nala_setup),
            ("Pre-flight Checks & Backups", setup.phase_preflight),
            ("System Update & Basic Configuration", setup.phase_system_update),
            ("Repository & Shell Setup", setup.phase_repo_shell_setup),
            ("Security Hardening", setup.phase_security_hardening),
            ("Essential Service Installation", setup.phase_service_installation),
            ("User Customization & Script Deployment", setup.phase_user_customization),
            ("Maintenance & Monitoring", setup.phase_maintenance_monitoring),
            ("Certificates & Performance Tuning", setup.phase_certificates_performance),
            ("Permissions & Advanced Storage Setup", setup.phase_permissions_storage),
            ("Additional Applications & Tools", setup.phase_additional_apps),
            (
                "Automatic Updates & Additional Security",
                setup.phase_automatic_updates_security,
            ),
            ("Cleanup & Final Configurations", setup.phase_cleanup_final),
            ("Final Checks & Reboot", setup.phase_final_checks),
        ]

        # Run each phase
        overall_status = True

        for phase_name, phase_func in phases:
            console.print(
                f"\n[bold {NordColors.FROST_1}]Starting phase: {phase_name}[/]"
            )

            try:
                phase_success = phase_func()

                if not phase_success:
                    overall_status = False
                    console.print(
                        f"[bold {NordColors.RED}]Phase '{phase_name}' failed. Continuing with best effort...[/]"
                    )
            except Exception as e:
                overall_status = False
                setup.logger.error(f"Error in phase '{phase_name}': {e}")
                console.print(
                    f"[bold {NordColors.RED}]Error in phase '{phase_name}': {str(e)}[/]"
                )
                console.print(
                    f"[bold {NordColors.YELLOW}]Continuing with next phase...[/]"
                )

        # Print final status message
        if overall_status:
            console.print(
                f"\n[bold {NordColors.GREEN}]Setup completed successfully![/]"
            )
            return 0
        else:
            console.print(
                f"\n[bold {NordColors.YELLOW}]Setup completed with some issues. Check the log for details: {setup.config.LOG_FILE}[/]"
            )
            return 1

    except KeyboardInterrupt:
        console.print(f"[bold {NordColors.RED}]Setup interrupted by user.[/]")
        return 130
    except Exception as e:
        console.print(f"[bold {NordColors.RED}]Unhandled error: {str(e)}[/]")
        return 1


if __name__ == "__main__":
    import box
    from rich.group import Group

    try:
        sys.exit(main())
    except Exception as e:
        console.print(f"[bold {NordColors.RED}]Fatal error: {str(e)}[/]")
        sys.exit(1)
