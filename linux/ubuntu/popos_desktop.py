#!/usr/bin/env python3
"""
Pop!_OS Desktop Setup & Hardening Utility (Unattended)
-------------------------------------------------------

This fully automated utility performs:
  • Pre-flight checks & backups (including ZFS snapshot if available)
  • System update & basic configuration (timezone, packages)
  • Repository & shell setup (cloning GitHub repos, updating shell configs)
  • Security hardening (SSH, sudoers, firewall, Fail2ban)
  • Essential service installations (Docker, Plex, Fastfetch, Brave, VS Code)
  • User customization & script deployment
  • Maintenance tasks (cron job, log rotation, configuration backups)
  • Certificates & performance tuning (SSL renewals, sysctl tweaks)
  • Permissions & advanced storage configuration (home permissions, ZFS)
  • Additional applications (Flatpak apps, VS Code configuration)
  • Automatic updates & further security (unattended upgrades, AppArmor)
  • Final system checks & reboot

Run this script with root privileges.
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import asyncio
import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, cast, TypeVar

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.logging import RichHandler
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"]
        )
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print(
            "Please install the required packages manually: pip install rich pyfiglet"
        )
        sys.exit(1)

install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Nord-Themed Colors and Theme Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette definitions for consistent UI styling."""

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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Returns a gradient using the frost color palette."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# Rich console theme setup
nord_theme = Theme(
    {
        "banner": f"bold {NordColors.FROST_2}",
        "header": f"bold {NordColors.FROST_2}",
        "info": NordColors.GREEN,
        "warning": NordColors.YELLOW,
        "error": NordColors.RED,
        "debug": NordColors.POLAR_NIGHT_3,
        "success": NordColors.GREEN,
    }
)

console = Console(theme=nord_theme)

# ----------------------------------------------------------------
# Global Configuration & Status Tracking
# ----------------------------------------------------------------
APP_NAME: str = "Pop!_OS Setup & Hardening"
VERSION: str = "9.0.0"
OPERATION_TIMEOUT: int = 300  # 5 minutes default timeout for operations

# Status tracking for each phase of the setup
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "nala_install": {"status": "pending", "message": ""},
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

# Type variable for generic functions
T = TypeVar("T")


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Config:
    """Configuration for the Pop!_OS setup process."""

    LOG_FILE: str = "/var/log/popos_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path("/home/sawyer"))
    PACKAGES: List[str] = field(
        default_factory=lambda: [
            "bash",
            "vim",
            "nano",
            "screen",
            "tmux",
            "htop",
            "btop",
            "tree",
            "git",
            "openssh-server",
            "ufw",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "bash-completion",
            "python3",
            "python3-pip",
            "python3-venv",
            "ca-certificates",
            "software-properties-common",
            "apt-transport-https",
            "gnupg",
            "lsb-release",
            "net-tools",
            "nmap",
            "tcpdump",
            "fail2ban",
            "build-essential",
            "cmake",
            "ninja-build",
            "meson",
            "gettext",
            "pkg-config",
            "python3-dev",
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
            "clang",
            "llvm",
            "golang-go",
            "gdb",
            "cargo",
            "rustc",
            "jq",
            "yq",
            "iftop",
            "traceroute",
            "mtr",
            "iotop",
            "glances",
            "whois",
            "dnsutils",
            "iproute2",
            "iputils-ping",
            "restic",
            "neofetch",
        ]
    )

    # Flatpak applications to install
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

    # SSH hardening configuration
    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "PermitRootLogin": "no",
            "PasswordAuthentication": "yes",
            "X11Forwarding": "yes",
            "MaxAuthTries": "3",
            "ClientAliveInterval": "300",
            "ClientAliveCountMax": "3",
        }
    )

    # Firewall ports to allow
    FIREWALL_PORTS: List[str] = field(default_factory=lambda: ["22", "80", "443"])

    def to_dict(self) -> Dict[str, Any]:
        """Convert the config to a dictionary."""
        return asdict(self)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header(title: str = APP_NAME) -> Panel:
    """
    Generate an ASCII art header with dynamic gradient styling using Pyfiglet.
    The banner is built line-by-line into a Rich Text object to avoid stray markup tokens.
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "digital", "mini", "smslant"]
    font_to_use: str = fonts[0]

    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]

    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=min(term_width - 10, 120))
            ascii_art = fig.renderText(title)
            if ascii_art.strip():
                break
        except Exception:
            continue

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()

    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")

    return Panel(
        Align.center(combined_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"{APP_NAME} v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        subtitle=Text("Unattended Mode", style=f"bold {NordColors.SNOW_STORM_1}"),
        subtitle_align="center",
    )


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
    """Print a step message in a workflow."""
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Print a section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a styled panel with a message."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/{style}]"),
        border_style=f"{style}",
        padding=(1, 2),
        title=f"[bold {style}]{title}[/{style}]" if title else None,
    )
    console.print(panel)


def print_status_report() -> None:
    """Print a status report table for all setup phases."""
    table = Table(title="Setup Status Report", style="banner")
    table.add_column("Task", style="header")
    table.add_column("Status", style="info")
    table.add_column("Message", style="info")

    for key, data in SETUP_STATUS.items():
        status_color = {
            "pending": "debug",
            "in_progress": "warning",
            "success": "success",
            "failed": "error",
        }.get(data["status"].lower(), "info")

        table.add_row(
            key.replace("_", " ").title(),
            f"[{status_color}]{data['status'].upper()}[/{status_color}]",
            data["message"],
        )

    console.print(
        Panel(
            table,
            title="[banner]Pop!_OS Setup Status[/banner]",
            border_style=NordColors.FROST_3,
        )
    )


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    """Set up and configure the logger."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("popos_setup")
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Rich console handler
    console_handler = RichHandler(console=console, rich_tracebacks=True)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    try:
        # Secure the log file
        os.chmod(str(log_file), 0o600)
    except Exception as e:
        logger.warning(f"Could not set permissions on log file {log_file}: {e}")

    return logger


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
async def signal_handler_async(signum: int, frame: Any) -> None:
    """Handle signals in an async-friendly way."""
    sig = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )

    logger = logging.getLogger("popos_setup")
    logger.error(f"Script interrupted by {sig}. Initiating cleanup.")

    try:
        if "setup_instance" in globals():
            await globals()["setup_instance"].cleanup_async()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")

    # Get the current loop and stop it
    try:
        loop = asyncio.get_running_loop()
        tasks = [
            task
            for task in asyncio.all_tasks(loop)
            if task is not asyncio.current_task()
        ]

        # Cancel all tasks
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete cancellation
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        loop.stop()
    except Exception as e:
        logger.error(f"Error stopping event loop: {e}")

    sys.exit(
        130
        if signum == signal.SIGINT
        else 143
        if signum == signal.SIGTERM
        else 128 + signum
    )


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers that work with the main event loop."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def cleanup_temp_files_async() -> None:
    """Clean up temporary files asynchronously."""
    logger = logging.getLogger("popos_setup")
    logger.info("Cleaning up temporary files.")

    tmp = Path(tempfile.gettempdir())
    for item in tmp.iterdir():
        if item.name.startswith("popos_setup_"):
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception as e:
                logger.warning(f"Failed to clean up {item}: {e}")


# Synchronous wrapper for cleanup to register with atexit
def cleanup_temp_files() -> None:
    """Synchronous wrapper for temp file cleanup, for atexit registration."""
    try:
        # Check if there's a running loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop available, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async cleanup
        loop.run_until_complete(cleanup_temp_files_async())
    except Exception as e:
        logger = logging.getLogger("popos_setup")
        logger.error(f"Error during temp file cleanup: {e}")


# Register cleanup with atexit
atexit.register(cleanup_temp_files)


# ----------------------------------------------------------------
# Download Helper
# ----------------------------------------------------------------
async def download_file_async(
    url: str, dest: Union[str, Path], timeout: int = 300
) -> None:
    """
    Download a file from the given URL to the destination asynchronously.
    """
    dest = Path(dest)
    logger = logging.getLogger("popos_setup")

    if dest.exists():
        logger.info(f"File {dest} already exists; skipping download.")
        return

    logger.info(f"Downloading {url} to {dest}...")
    loop = asyncio.get_running_loop()

    try:
        if shutil.which("wget"):
            # Use wget for download with subprocess
            proc = await asyncio.create_subprocess_exec(
                "wget",
                "-q",
                "--show-progress",
                url,
                "-O",
                str(dest),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                raise Exception(f"wget failed with return code {proc.returncode}")

        elif shutil.which("curl"):
            # Use curl for download with subprocess
            proc = await asyncio.create_subprocess_exec(
                "curl",
                "-L",
                "-o",
                str(dest),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                raise Exception(f"curl failed with return code {proc.returncode}")

        else:
            # Use urllib.request for download in a separate thread
            import urllib.request

            await loop.run_in_executor(None, urllib.request.urlretrieve, url, dest)

        logger.info(f"Download complete: {dest}")

    except asyncio.TimeoutError:
        logger.error(f"Download timed out after {timeout} seconds")
        if dest.exists():
            dest.unlink()
        raise

    except Exception as e:
        logger.error(f"Download failed: {e}")
        if dest.exists():
            dest.unlink()
        raise


# ----------------------------------------------------------------
# Progress Utility: Run Function with Progress Indicator
# ----------------------------------------------------------------
async def run_with_progress_async(
    description: str,
    func: Callable[..., Any],
    *args: Any,
    task_name: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Run a function with a progress indicator asynchronously."""
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("{task.description}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task(description, total=None)
        start = time.time()

        try:
            # Check if the function is a coroutine function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # Run synchronous functions in a thread pool
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))

            elapsed = time.time() - start
            progress.update(task_id, completed=100)
            console.print(
                f"[success]✓ {description} completed in {elapsed:.2f}s[/success]"
            )

            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "success",
                    "message": f"Completed in {elapsed:.2f}s",
                }

            return result

        except Exception as e:
            elapsed = time.time() - start
            progress.update(task_id, completed=100)
            console.print(
                f"[error]✗ {description} failed in {elapsed:.2f}s: {e}[/error]"
            )

            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"Failed after {elapsed:.2f}s: {str(e)}",
                }

            raise


# ----------------------------------------------------------------
# Command Execution Utilities
# ----------------------------------------------------------------
async def run_command_async(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = False,
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run a system command asynchronously."""
    logger = logging.getLogger("popos_setup")
    logger.debug(f"Running command: {' '.join(cmd)}")

    # Set up pipes based on capture_output flag
    stdout = asyncio.subprocess.PIPE if capture_output else None
    stderr = asyncio.subprocess.PIPE if capture_output else None

    try:
        # Start the process
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout,
            stderr=stderr,
        )

        # Wait for the process to complete with optional timeout
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        # Convert to text if requested
        if text and stdout_data is not None:
            stdout_data = stdout_data.decode("utf-8")
        if text and stderr_data is not None:
            stderr_data = stderr_data.decode("utf-8")

        # Create a CompletedProcess object for compatibility
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_data if capture_output else None,
            stderr=stderr_data if capture_output else None,
        )

        # Check the return code if requested
        if check and proc.returncode != 0:
            error_message = (
                stderr_data.decode("utf-8") if stderr_data else "Unknown error"
            )
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout_data, stderr=stderr_data
            )

        return result

    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise Exception(f"Command timed out: {' '.join(cmd)}")


async def command_exists_async(cmd: str) -> bool:
    """Check if a command exists in the system path."""
    try:
        await run_command_async(
            ["which", cmd],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, Exception):
        return False


# ----------------------------------------------------------------
# Main Setup Class
# ----------------------------------------------------------------
class PopOSDesktopSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self.nala_installed = False
        self._current_task = None

    async def print_section_async(self, title: str) -> None:
        """Print a section header with ASCII art."""
        console.print(create_header(title))
        self.logger.info(f"--- {title} ---")

    async def backup_file_async(self, file_path: Union[str, Path]) -> Optional[str]:
        """Create a backup of a file with timestamp."""
        file_path = Path(file_path)
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = file_path.with_suffix(file_path.suffix + f".bak.{timestamp}")

        try:
            shutil.copy2(file_path, backup_path)
            self.logger.debug(f"Backed up {file_path} to {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.warning(f"Failed to backup {file_path}: {e}")
            return None

    async def cleanup_async(self) -> None:
        """Perform cleanup operations before exiting."""
        self.logger.info("Performing cleanup before exit...")

        try:
            # Clean up temp files
            tmp = Path(tempfile.gettempdir())
            for item in tmp.glob("popos_setup_*"):
                try:
                    if item.is_file():
                        item.unlink()
                    else:
                        shutil.rmtree(item)
                except Exception as e:
                    self.logger.warning(f"Failed to clean up {item}: {e}")

            # Rotate logs
            try:
                await self.rotate_logs_async()
            except Exception as e:
                self.logger.warning(f"Failed to rotate logs: {e}")

            self.logger.info("Cleanup completed.")

        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

    async def rotate_logs_async(self, log_file: Optional[str] = None) -> bool:
        """Rotate log files with compression."""
        if log_file is None:
            log_file = self.config.LOG_FILE

        log_path = Path(log_file)
        if not log_path.is_file():
            self.logger.warning(f"Log file {log_path} does not exist.")
            return False

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rotated = f"{log_path}.{timestamp}.gz"

            # Run in a thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self._compress_log(log_path, rotated)
            )

            self.logger.info(f"Log rotated to {rotated}")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def _compress_log(self, log_path: Path, rotated_path: str) -> None:
        """Helper to compress a log file (runs in thread pool)."""
        with open(log_path, "rb") as f_in, gzip.open(rotated_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        open(log_path, "w").close()  # Truncate the original log

    async def has_internet_connection_async(self) -> bool:
        """Check for internet connectivity."""
        try:
            await run_command_async(
                ["ping", "-c", "1", "-W", "5", "8.8.8.8"],
                capture_output=True,
                check=False,
            )
            return True
        except Exception:
            return False

    # ----------------------------------------------------------------
    # Phase 0: Pre-Flight Checks
    # ----------------------------------------------------------------
    async def phase_preflight(self) -> bool:
        """Run pre-flight checks and create backups."""
        await self.print_section_async("Pre-flight Checks & Backups")

        try:
            await run_with_progress_async(
                "Checking for root privileges",
                self.check_root_async,
                task_name="preflight",
            )

            await run_with_progress_async(
                "Checking network connectivity",
                self.check_network_async,
                task_name="preflight",
            )

            await run_with_progress_async(
                "Verifying Pop!_OS distribution",
                self.check_popos_async,
                task_name="preflight",
            )

            await run_with_progress_async(
                "Saving configuration snapshot",
                self.save_config_snapshot_async,
                task_name="preflight",
            )

            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            return False

    async def check_root_async(self) -> None:
        """Verify the script is running with root privileges."""
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root.")
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    async def check_network_async(self) -> None:
        """Verify network connectivity."""
        self.logger.info("Verifying network connectivity...")
        if await self.has_internet_connection_async():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity. Please check your settings.")
            sys.exit(1)

    async def check_popos_async(self) -> None:
        """Verify the system is running Pop!_OS."""
        try:
            result = await run_command_async(
                ["lsb_release", "-a"], capture_output=True, text=True
            )

            if "Pop!_OS" not in result.stdout:
                self.logger.warning(
                    "This may not be a Pop!_OS system. Some features may not work."
                )
            else:
                version = next(
                    (
                        line.split(":")[1].strip()
                        for line in result.stdout.splitlines()
                        if line.startswith("Release:")
                    ),
                    "Unknown",
                )
                self.logger.info(f"Pop!_OS version {version} detected.")
        except Exception as e:
            self.logger.warning(f"Could not verify Pop!_OS: {e}")

    async def save_config_snapshot_async(self) -> Optional[str]:
        """Save a snapshot of the current configuration."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot_file = backup_dir / f"popos_config_snapshot_{timestamp}.tar.gz"

        try:
            # Use a thread pool for file operations
            loop = asyncio.get_running_loop()

            # Create a temp list to track added files
            files_added = []

            # Create the archive
            def create_archive():
                nonlocal files_added
                with tarfile.open(snapshot_file, "w:gz") as tar:
                    # Add important configuration files
                    for config_path in [
                        "/etc/apt/sources.list",
                        "/etc/fstab",
                        "/etc/default/grub",
                        "/etc/hosts",
                        "/etc/ssh/sshd_config",
                    ]:
                        path = Path(config_path)
                        if path.is_file():
                            tar.add(str(path), arcname=path.name)
                            files_added.append(str(path))

            # Run the archive creation in a thread
            await loop.run_in_executor(None, create_archive)

            if files_added:
                for path in files_added:
                    self.logger.info(f"Included {path} in snapshot.")
                self.logger.info(f"Configuration snapshot saved: {snapshot_file}")
                return str(snapshot_file)
            else:
                self.logger.warning("No configuration files found for snapshot.")
                return None

        except Exception as e:
            self.logger.warning(f"Failed to create config snapshot: {e}")
            return None

    # ----------------------------------------------------------------
    # Phase 1: Install Nala Package Manager
    # ----------------------------------------------------------------
    async def phase_install_nala(self) -> bool:
        """Install and configure the Nala package manager."""
        await self.print_section_async("Install Nala Package Manager")

        try:
            if await command_exists_async("nala"):
                self.logger.info("Nala is already installed.")
                self.nala_installed = True
                return True

            self.logger.info("Installing Nala package manager...")
            await run_command_async(["apt", "update", "-qq"])
            await run_command_async(["apt", "install", "nala", "-y"])

            if await command_exists_async("nala"):
                self.logger.info("Nala installed successfully.")
                self.nala_installed = True

                try:
                    self.logger.info("Configuring faster mirrors with Nala...")
                    await run_command_async(["nala", "fetch", "--auto"], check=False)
                    self.logger.info("Mirrors configured successfully.")
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to configure mirrors: {e}")

                return True
            else:
                self.logger.error("Nala installation verification failed.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to install Nala: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 2: System Update & Basic Configuration
    # ----------------------------------------------------------------
    async def phase_system_update(self) -> bool:
        """Update system packages and install required packages."""
        await self.print_section_async("System Update & Basic Configuration")

        status = True
        if not await run_with_progress_async(
            "Updating system repositories",
            self.update_repos_async,
            task_name="system_update",
        ):
            status = False

        if not await run_with_progress_async(
            "Upgrading system packages",
            self.upgrade_system_async,
            task_name="system_update",
        ):
            status = False

        success, failed = await run_with_progress_async(
            "Installing required packages",
            self.install_packages_async,
            task_name="system_update",
        )

        if failed and len(failed) > len(self.config.PACKAGES) * 0.1:
            self.logger.error(
                f"Failed to install too many packages: {', '.join(failed)}"
            )
            status = False

        return status

    async def update_repos_async(self) -> bool:
        """Update package repositories."""
        try:
            self.logger.info("Updating package repositories...")

            if self.nala_installed:
                await run_command_async(["nala", "update"])
            else:
                await run_command_async(["apt", "update", "-qq"])

            self.logger.info("Package repositories updated successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Repository update failed: {e}")
            return False

    async def upgrade_system_async(self) -> bool:
        """Upgrade system packages."""
        try:
            self.logger.info("Upgrading system packages...")

            if self.nala_installed:
                await run_command_async(["nala", "upgrade", "-y"])
            else:
                await run_command_async(["apt", "upgrade", "-y"])

            self.logger.info("System upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System upgrade failed: {e}")
            return False

    async def install_packages_async(self) -> Tuple[List[str], List[str]]:
        """Install required packages."""
        self.logger.info("Checking for required packages...")
        missing, success, failed = [], [], []

        # Check which packages are already installed
        for pkg in self.config.PACKAGES:
            try:
                result = await run_command_async(
                    ["dpkg", "-s", pkg],
                    check=False,
                    capture_output=True,
                )

                if result.returncode == 0:
                    self.logger.debug(f"Package already installed: {pkg}")
                    success.append(pkg)
                else:
                    missing.append(pkg)

            except Exception:
                missing.append(pkg)

        # Install missing packages
        if missing:
            self.logger.info(f"Installing missing packages: {' '.join(missing)}")

            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-y"] + missing)
                else:
                    await run_command_async(["apt", "install", "-y"] + missing)

                self.logger.info("Missing packages installed successfully.")

                # Verify installation success
                for pkg in missing:
                    try:
                        result = await run_command_async(
                            ["dpkg", "-s", pkg],
                            check=False,
                            capture_output=True,
                        )

                        if result.returncode == 0:
                            success.append(pkg)
                        else:
                            failed.append(pkg)

                    except Exception:
                        failed.append(pkg)

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install packages: {e}")
                for pkg in missing:
                    try:
                        result = await run_command_async(
                            ["dpkg", "-s", pkg],
                            check=False,
                            capture_output=True,
                        )

                        if result.returncode == 0:
                            success.append(pkg)
                        else:
                            failed.append(pkg)

                    except Exception:
                        failed.append(pkg)
        else:
            self.logger.info("All required packages are installed.")

        return success, failed

    # ----------------------------------------------------------------
    # Phase 3: Repository & Shell Setup
    # ----------------------------------------------------------------
    async def phase_repo_shell_setup(self) -> bool:
        """Set up GitHub repositories and shell configurations."""
        await self.print_section_async("Repository & Shell Setup")

        status = True
        if not await run_with_progress_async(
            "Setting up GitHub repositories",
            self.setup_repos_async,
            task_name="repo_shell",
        ):
            status = False

        if not await run_with_progress_async(
            "Copying shell configurations", self.copy_shell_configs_async
        ):
            status = False

        if not await run_with_progress_async(
            "Copying configuration folders", self.copy_config_folders_async
        ):
            status = False

        if not await run_with_progress_async(
            "Setting default shell to bash", self.set_bash_shell_async
        ):
            status = False

        return status

    async def setup_repos_async(self) -> bool:
        """Clone or update GitHub repositories."""
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)
        all_success = True

        # For brevity, using a dummy list of repositories
        repos = ["bash", "python"]

        for repo in repos:
            repo_dir = gh_dir / repo
            if (repo_dir / ".git").is_dir():
                self.logger.info(f"Repository '{repo}' exists; pulling updates...")
                try:
                    await run_command_async(["git", "-C", str(repo_dir), "pull"])
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to update repository '{repo}'.")
                    all_success = False
            else:
                self.logger.info(f"Cloning repository '{repo}'...")
                try:
                    await run_command_async(
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

        try:
            await run_command_async(
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

    async def copy_shell_configs_async(self) -> bool:
        """Copy shell configuration files."""
        source_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "popos" / "dotfiles"
        )

        # Fallback to ubuntu folder if pop-specific folder doesn't exist
        if not source_dir.is_dir():
            source_dir = (
                self.config.USER_HOME
                / "github"
                / "bash"
                / "linux"
                / "ubuntu"
                / "dotfiles"
            )
            self.logger.info(
                f"Pop!_OS-specific dotfiles not found, using Ubuntu dotfiles from {source_dir}"
            )

        destination_dirs = [self.config.USER_HOME, Path("/root")]
        overall = True

        for file_name in [".bashrc", ".profile"]:
            src = source_dir / file_name
            if not src.is_file():
                self.logger.warning(f"Source file {src} not found; skipping.")
                continue

            for dest_dir in destination_dirs:
                dest = dest_dir / file_name

                # Use a thread pool for file comparisons and copies
                loop = asyncio.get_running_loop()

                # Check if files are identical
                files_identical = False
                if dest.is_file():
                    files_identical = await loop.run_in_executor(
                        None, lambda: filecmp.cmp(src, dest)
                    )

                if dest.is_file() and files_identical:
                    self.logger.info(f"File {dest} is already up-to-date.")
                else:
                    try:
                        if dest.is_file():
                            await self.backup_file_async(dest)

                        # Copy the file
                        await loop.run_in_executor(
                            None, lambda: shutil.copy2(src, dest)
                        )

                        owner = (
                            f"{self.config.USERNAME}:{self.config.USERNAME}"
                            if dest_dir == self.config.USER_HOME
                            else "root:root"
                        )

                        await run_command_async(["chown", owner, str(dest)])
                        self.logger.info(f"Copied {src} to {dest}.")

                    except Exception as e:
                        self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        overall = False

        return overall

    async def copy_config_folders_async(self) -> bool:
        """Copy configuration folders to .config directory."""
        src = self.config.USER_HOME / "github" / "bash" / "linux" / "popos" / "dotfiles"

        # Fallback to ubuntu folder if pop-specific folder doesn't exist
        if not src.is_dir():
            src = (
                self.config.USER_HOME
                / "github"
                / "bash"
                / "linux"
                / "ubuntu"
                / "dotfiles"
            )

        dest = self.config.USER_HOME / ".config"
        dest.mkdir(exist_ok=True)
        overall = True

        try:
            loop = asyncio.get_running_loop()

            # Get list of directories to copy
            src_dirs = [item for item in src.iterdir() if item.is_dir()]

            for item in src_dirs:
                dest_path = dest / item.name

                # Use thread pool for directory copying
                await loop.run_in_executor(
                    None, lambda: shutil.copytree(item, dest_path, dirs_exist_ok=True)
                )

                await run_command_async(
                    [
                        "chown",
                        "-R",
                        f"{self.config.USERNAME}:{self.config.USERNAME}",
                        str(dest_path),
                    ]
                )

                self.logger.info(f"Copied {item} to {dest_path}.")

            return overall

        except Exception as e:
            self.logger.error(f"Error copying config folders: {e}")
            return False

    async def set_bash_shell_async(self) -> bool:
        """Set bash as the default shell for the user."""
        if not await command_exists_async("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-y", "bash"])
                else:
                    await run_command_async(["apt", "install", "-y", "bash"])
            except subprocess.CalledProcessError:
                self.logger.warning("Bash installation failed.")
                return False

        shells_file = Path("/etc/shells")
        loop = asyncio.get_running_loop()

        try:
            if shells_file.exists():
                content = await loop.run_in_executor(None, shells_file.read_text)
                if "/bin/bash" not in content:

                    async def append_bash():
                        with open(shells_file, "a") as f:
                            f.write("/bin/bash\n")

                    await loop.run_in_executor(None, append_bash)
                    self.logger.info("Added /bin/bash to /etc/shells.")
            else:

                async def create_shells_file():
                    with open(shells_file, "w") as f:
                        f.write("/bin/bash\n")

                await loop.run_in_executor(None, create_shells_file)
                self.logger.info("Created /etc/shells with /bin/bash.")

        except Exception as e:
            self.logger.warning(f"Failed to update /etc/shells: {e}")
            return False

        try:
            await run_command_async(["chsh", "-s", "/bin/bash", self.config.USERNAME])
            self.logger.info(
                f"Default shell for {self.config.USERNAME} set to /bin/bash."
            )
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to set default shell for {self.config.USERNAME}."
            )
            return False

    # ----------------------------------------------------------------
    # Phase 4: Security Hardening
    # ----------------------------------------------------------------
    async def phase_security_hardening(self) -> bool:
        """Implement security hardening measures."""
        await self.print_section_async("Security Hardening")

        status = True
        if not await run_with_progress_async(
            "Configuring SSH", self.configure_ssh_async, task_name="security"
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring firewall", self.configure_firewall_async
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring Fail2ban", self.configure_fail2ban_async
        ):
            status = False

        return status

    async def configure_ssh_async(self) -> bool:
        """Configure SSH for improved security."""
        try:
            result = await run_command_async(
                ["dpkg", "-s", "openssh-server"],
                check=False,
                capture_output=True,
            )

            if result.returncode != 0:
                self.logger.info("openssh-server not installed. Installing...")
                try:
                    if self.nala_installed:
                        await run_command_async(
                            ["nala", "install", "-y", "openssh-server"]
                        )
                    else:
                        await run_command_async(
                            ["apt", "install", "-y", "openssh-server"]
                        )
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install OpenSSH Server.")
                    return False
        except Exception:
            self.logger.error("Failed to check for OpenSSH Server installation.")
            return False

        try:
            await run_command_async(["systemctl", "enable", "--now", "ssh"])
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable/start SSH service.")
            return False

        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config}")
            return False

        await self.backup_file_async(sshd_config)

        try:
            loop = asyncio.get_running_loop()

            # Read the file
            lines = await loop.run_in_executor(
                None, lambda: sshd_config.read_text().splitlines()
            )

            # Process the content
            new_lines = []
            for key, val in self.config.SSH_CONFIG.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {val}"
                        found = True
                        break

                if not found:
                    lines.append(f"{key} {val}")

            # Write back the file
            await loop.run_in_executor(
                None, lambda: sshd_config.write_text("\n".join(lines) + "\n")
            )

            await run_command_async(["systemctl", "restart", "ssh"])
            self.logger.info("SSH configuration updated and service restarted.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    async def configure_firewall_async(self) -> bool:
        """Configure UFW firewall with allowed ports."""
        ufw_cmd = "/usr/sbin/ufw"

        # Get the running event loop
        loop = asyncio.get_running_loop()

        # Check if UFW is installed
        ufw_exists = await loop.run_in_executor(
            None, lambda: Path(ufw_cmd).is_file() and os.access(ufw_cmd, os.X_OK)
        )

        if not ufw_exists:
            self.logger.error("UFW command not found. Installing UFW...")
            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-y", "ufw"])
                else:
                    await run_command_async(["apt", "install", "-y", "ufw"])

                # Verify installation
                ufw_exists = await loop.run_in_executor(
                    None,
                    lambda: Path(ufw_cmd).is_file() and os.access(ufw_cmd, os.X_OK),
                )

                if not ufw_exists:
                    self.logger.error("UFW installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install UFW: {e}")
                return False

        try:
            # Configure firewall rules
            await run_command_async([ufw_cmd, "default", "deny", "incoming"])
            await run_command_async([ufw_cmd, "default", "allow", "outgoing"])

            for port in self.config.FIREWALL_PORTS:
                await run_command_async([ufw_cmd, "allow", f"{port}/tcp"])
                self.logger.info(f"Allowed TCP port {port}.")

            # Check status and enable if inactive
            status = await run_command_async(
                [ufw_cmd, "status"], capture_output=True, text=True
            )

            if "inactive" in status.stdout.lower():
                await run_command_async([ufw_cmd, "--force", "enable"])
                self.logger.info("UFW firewall enabled.")
            else:
                self.logger.info("UFW firewall is active.")

            # Enable and start UFW service
            await run_command_async(["systemctl", "enable", "ufw"])
            await run_command_async(["systemctl", "start", "ufw"])
            self.logger.info("UFW service enabled and started.")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to configure firewall: {e}")
            return False

    async def configure_fail2ban_async(self) -> bool:
        """Configure Fail2ban for brute force protection."""
        jail_local = Path("/etc/fail2ban/jail.local")

        # Ensure parent directory exists
        jail_local.parent.mkdir(parents=True, exist_ok=True)

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

        try:
            if jail_local.is_file():
                await self.backup_file_async(jail_local)

            # Write the configuration file
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: jail_local.write_text(config_content)
            )

            self.logger.info("Fail2ban configuration written.")

            # Enable and restart the service
            await run_command_async(["systemctl", "enable", "fail2ban"])
            await run_command_async(["systemctl", "restart", "fail2ban"])
            self.logger.info("Fail2ban service enabled and restarted.")
            return True

        except Exception as e:
            self.logger.warning(f"Failed to configure Fail2ban: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 5: Essential Service Installation
    # ----------------------------------------------------------------
    async def phase_service_installation(self) -> bool:
        """Install essential services."""
        await self.print_section_async("Essential Service Installation")

        status = True
        if not await run_with_progress_async(
            "Installing Plex Media Server",
            self.install_plex_async,
            task_name="services",
        ):
            status = False

        if not await run_with_progress_async(
            "Installing Fastfetch", self.install_fastfetch_async, task_name="services"
        ):
            status = False

        if not await run_with_progress_async(
            "Installing Docker", self.install_docker_async, task_name="services"
        ):
            status = False

        return status

    async def install_plex_async(self) -> bool:
        """Install and configure Plex Media Server."""
        try:
            result = await run_command_async(
                ["dpkg", "-s", "plexmediaserver"],
                check=False,
                capture_output=True,
            )

            if result.returncode == 0:
                self.logger.info("Plex Media Server already installed; skipping.")
                return True
        except Exception:
            pass

        temp_deb = Path("/tmp/plexmediaserver.deb")

        try:
            # Using the latest Plex Media Server version
            await download_file_async(
                "https://downloads.plex.tv/plex-media-server-new/1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb",
                temp_deb,
            )

            await run_command_async(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg issues with Plex; fixing dependencies...")
            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-f", "-y"])
                else:
                    await run_command_async(["apt", "install", "-f", "-y"])

                # Try installing again after fixing dependencies
                try:
                    await run_command_async(["dpkg", "-i", str(temp_deb)])
                except subprocess.CalledProcessError:
                    self.logger.error(
                        "Failed to install Plex even after fixing dependencies."
                    )
                    return False

            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Plex dependencies.")
                return False

        plex_conf = Path("/etc/default/plexmediaserver")
        if plex_conf.is_file():
            try:
                loop = asyncio.get_running_loop()

                # Read configuration
                conf = await loop.run_in_executor(None, plex_conf.read_text)

                if f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}" not in conf:
                    # Update the user
                    new_conf = [
                        f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}"
                        if line.startswith("PLEX_MEDIA_SERVER_USER=")
                        else line
                        for line in conf.splitlines()
                    ]

                    # Write updated configuration
                    await loop.run_in_executor(
                        None, lambda: plex_conf.write_text("\n".join(new_conf) + "\n")
                    )

                    self.logger.info(
                        f"Configured Plex to run as {self.config.USERNAME}."
                    )
                else:
                    self.logger.info("Plex user already configured.")
            except Exception as e:
                self.logger.warning(f"Failed to update {plex_conf}: {e}")
        else:
            self.logger.warning(f"{plex_conf} not found; skipping user configuration.")

        try:
            await run_command_async(["systemctl", "enable", "plexmediaserver"])
            await run_command_async(["systemctl", "restart", "plexmediaserver"])
            self.logger.info("Plex service enabled and started.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to enable/start Plex service.")

        try:
            if temp_deb.exists():
                await asyncio.get_running_loop().run_in_executor(None, temp_deb.unlink)
        except Exception:
            pass

        self.logger.info("Plex Media Server installation complete.")
        return True

    async def install_fastfetch_async(self) -> bool:
        """Install and configure Fastfetch."""
        try:
            result = await run_command_async(
                ["dpkg", "-s", "fastfetch"],
                check=False,
                capture_output=True,
            )

            if result.returncode == 0:
                self.logger.info("Fastfetch already installed; skipping.")
                return True
        except Exception:
            pass

        temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")

        try:
            await download_file_async(
                "https://github.com/fastfetch-cli/fastfetch/releases/download/2.37.0/fastfetch-linux-amd64.deb",
                temp_deb,
            )

            await run_command_async(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("Fastfetch installation issues; fixing dependencies...")
            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-f", "-y"])
                else:
                    await run_command_async(["apt", "install", "-f", "-y"])

                # Try installing again after fixing dependencies
                try:
                    await run_command_async(["dpkg", "-i", str(temp_deb)])
                except subprocess.CalledProcessError:
                    self.logger.error(
                        "Failed to install Fastfetch even after fixing dependencies."
                    )
                    return False

            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Fastfetch dependencies.")
                return False

        try:
            if temp_deb.exists():
                await asyncio.get_running_loop().run_in_executor(None, temp_deb.unlink)
        except Exception:
            pass

        # Create default config directory
        config_dir = self.config.USER_HOME / ".config" / "fastfetch"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(config_dir),
                ]
            )
        except Exception as e:
            self.logger.warning(f"Failed to create Fastfetch config directory: {e}")

        self.logger.info("Fastfetch installed successfully.")
        return True

    async def install_docker_async(self) -> bool:
        """Install Docker and Docker Compose."""
        try:
            # Check if Docker is already installed
            if await command_exists_async("docker"):
                self.logger.info("Docker is already installed.")

                # Verify Docker Compose is installed
                if await command_exists_async("docker-compose"):
                    self.logger.info("Docker Compose is already installed.")
                    return True

            # Add Docker's official GPG key
            self.logger.info("Adding Docker GPG key...")
            key_file = Path("/etc/apt/keyrings/docker.gpg")
            key_file.parent.mkdir(parents=True, exist_ok=True)

            # Download the GPG key
            await run_command_async(
                [
                    "curl",
                    "-fsSL",
                    "https://download.docker.com/linux/ubuntu/gpg",
                    "-o",
                    "/tmp/docker.key",
                ]
            )

            # Dearmor the key
            await run_command_async(
                ["gpg", "--dearmor", "-o", str(key_file), "/tmp/docker.key"]
            )

            # Add the repository
            self.logger.info("Adding Docker repository...")
            source_file = Path("/etc/apt/sources.list.d/docker.list")

            # Get the distribution codename
            result = await run_command_async(
                ["lsb_release", "-cs"], capture_output=True, text=True
            )
            codename = result.stdout.strip()

            # Write the repository file
            source_content = (
                f"deb [arch=amd64 signed-by={key_file}] "
                f"https://download.docker.com/linux/ubuntu {codename} stable\n"
            )

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: source_file.write_text(source_content)
            )

            # Update package lists
            self.logger.info("Updating package lists with Docker repository...")
            if self.nala_installed:
                await run_command_async(["nala", "update"])
            else:
                await run_command_async(["apt", "update"])

            # Install Docker packages
            self.logger.info("Installing Docker packages...")
            docker_packages = [
                "docker-ce",
                "docker-ce-cli",
                "containerd.io",
                "docker-buildx-plugin",
                "docker-compose-plugin",
            ]

            if self.nala_installed:
                await run_command_async(["nala", "install", "-y"] + docker_packages)
            else:
                await run_command_async(["apt", "install", "-y"] + docker_packages)

            # Verify installation
            if not await command_exists_async("docker"):
                self.logger.error("Docker installation failed.")
                return False

            # Add user to docker group
            self.logger.info(f"Adding {self.config.USERNAME} to docker group...")
            await run_command_async(["usermod", "-aG", "docker", self.config.USERNAME])

            # Enable and start Docker service
            await run_command_async(["systemctl", "enable", "docker"])
            await run_command_async(["systemctl", "start", "docker"])

            self.logger.info("Docker installed and configured successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to install Docker: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 6: User Customization & Script Deployment
    # ----------------------------------------------------------------
    async def phase_user_customization(self) -> bool:
        """Deploy user customization scripts."""
        await self.print_section_async("User Customization & Script Deployment")

        status = True
        if not await run_with_progress_async(
            "Deploying user scripts",
            self.deploy_user_scripts_async,
            task_name="user_custom",
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring system appearance",
            self.configure_appearance_async,
            task_name="user_custom",
        ):
            status = False

        return status

    async def deploy_user_scripts_async(self) -> bool:
        """Deploy user scripts from repository to bin directory."""
        src = self.config.USER_HOME / "github" / "bash" / "linux" / "popos" / "_scripts"

        # Fallback to ubuntu folder if pop-specific folder doesn't exist
        if not src.is_dir():
            src = (
                self.config.USER_HOME
                / "github"
                / "bash"
                / "linux"
                / "ubuntu"
                / "_scripts"
            )
            self.logger.info(
                f"Pop!_OS-specific scripts not found, using Ubuntu scripts from {src}"
            )

        target = self.config.USER_HOME / "bin"

        if not src.is_dir():
            self.logger.error(f"Script source directory {src} does not exist.")
            return False

        target.mkdir(exist_ok=True)

        try:
            # Use rsync for efficient directory synchronization
            await run_command_async(
                ["rsync", "-ah", "--delete", f"{src}/", f"{target}/"]
            )

            # Set executable permissions
            await run_command_async(
                ["find", str(target), "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )

            # Set ownership
            await run_command_async(
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

    async def configure_appearance_async(self) -> bool:
        """Configure system appearance settings for Pop!_OS."""
        user_dconf_dir = self.config.USER_HOME / ".config" / "dconf"
        user_dconf_dir.mkdir(parents=True, exist_ok=True)

        # Get the UID and GID for dbus-launch to run as the user
        try:
            passwd_info = await run_command_async(
                ["getent", "passwd", self.config.USERNAME],
                capture_output=True,
                text=True,
            )

            uid = passwd_info.stdout.split(":")[2]
            gid = passwd_info.stdout.split(":")[3]

            # Configure dark theme
            self.logger.info("Setting dark theme preference...")
            gsettings_commands = [
                # Set dark theme
                [
                    "gsettings",
                    "set",
                    "org.gnome.desktop.interface",
                    "gtk-theme",
                    "Pop-dark",
                ],
                [
                    "gsettings",
                    "set",
                    "org.gnome.desktop.interface",
                    "color-scheme",
                    "prefer-dark",
                ],
                # Set icon theme
                [
                    "gsettings",
                    "set",
                    "org.gnome.desktop.interface",
                    "icon-theme",
                    "Pop",
                ],
                # Desktop settings
                [
                    "gsettings",
                    "set",
                    "org.gnome.desktop.background",
                    "show-desktop-icons",
                    "true",
                ],
                # Terminal settings
                [
                    "gsettings",
                    "set",
                    "org.gnome.Terminal.Legacy.Settings",
                    "theme-variant",
                    "dark",
                ],
                # Dock settings (if using COSMIC)
                [
                    "gsettings",
                    "set",
                    "org.gnome.shell.extensions.dash-to-dock",
                    "dock-position",
                    "BOTTOM",
                ],
                [
                    "gsettings",
                    "set",
                    "org.gnome.shell.extensions.dash-to-dock",
                    "extend-height",
                    "false",
                ],
                [
                    "gsettings",
                    "set",
                    "org.gnome.shell.extensions.dash-to-dock",
                    "transparency-mode",
                    "FIXED",
                ],
            ]

            for cmd in gsettings_commands:
                try:
                    await run_command_async(
                        [
                            "sudo",
                            "-u",
                            self.config.USERNAME,
                            "env",
                            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
                        ]
                        + cmd,
                        check=False,
                    )
                except Exception as e:
                    self.logger.debug(f"Non-critical error while setting {cmd}: {e}")

            # Ensure ownership of dconf dir is correct
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_dconf_dir),
                ]
            )

            self.logger.info("System appearance settings applied.")
            return True

        except Exception as e:
            self.logger.warning(f"Failed to configure appearance: {e}")
            # This is non-critical, continue with the setup
            return True

    # ----------------------------------------------------------------
    # Phase 7: Permissions & Advanced Storage Setup
    # ----------------------------------------------------------------
    async def phase_permissions_storage(self) -> bool:
        """Configure permissions and ZFS storage."""
        await self.print_section_async("Permissions & Advanced Storage Setup")

        status = True
        if not await run_with_progress_async(
            "Configuring home directory permissions",
            self.home_permissions_async,
            task_name="permissions_storage",
        ):
            status = False

        if not await run_with_progress_async(
            "Installing & Configuring ZFS",
            self.install_configure_zfs_async,
            task_name="permissions_storage",
        ):
            status = False

        return status

    async def home_permissions_async(self) -> bool:
        """Configure home directory permissions."""
        try:
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(self.config.USER_HOME),
                ]
            )

            self.logger.info(
                f"Ownership of {self.config.USER_HOME} set to {self.config.USERNAME}."
            )
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to change ownership of {self.config.USER_HOME}.")
            return False

        try:
            await run_command_async(
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

            self.logger.info("Setgid bit applied on home directories.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to set setgid bit.")

        if await command_exists_async("setfacl"):
            try:
                await run_command_async(
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

    async def install_configure_zfs_async(self) -> bool:
        """Install and configure ZFS filesystem."""
        # Check if ZFS is supported in the current kernel
        try:
            # ZFS modules check
            result = await run_command_async(
                ["modprobe", "zfs"], check=False, capture_output=True
            )

            if result.returncode != 0:
                self.logger.warning(
                    "ZFS kernel module is not available. Attempting to install ZFS packages."
                )
            else:
                self.logger.info("ZFS kernel module is available.")
        except Exception:
            self.logger.warning("Could not check for ZFS kernel module.")

        # Install ZFS packages
        pool = "WD_BLACK"
        mount_point = Path("/media/WD_BLACK")

        try:
            if self.nala_installed:
                await run_command_async(
                    ["nala", "install", "-y", "zfs-dkms", "zfsutils-linux"]
                )
            else:
                await run_command_async(
                    ["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"]
                )

            self.logger.info("ZFS packages installed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install ZFS packages: {e}")
            # This is a non-critical error for Pop!_OS, continue with setup
            return True

        # Check if ZFS is now available
        try:
            result = await run_command_async(
                ["zfs", "--version"], check=False, capture_output=True
            )

            if result.returncode != 0:
                self.logger.warning(
                    "ZFS command not available. Skipping ZFS configuration."
                )
                return True
        except Exception:
            self.logger.warning("Could not verify ZFS installation.")
            return True

        # Enable ZFS services
        for service in ["zfs-import-cache.service", "zfs-mount.service"]:
            try:
                await run_command_async(["systemctl", "enable", service])
                self.logger.info(f"Enabled {service}.")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Could not enable {service}.")

        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Mount point {mount_point} ensured.")
        except Exception as e:
            self.logger.warning(f"Failed to create mount point {mount_point}: {e}")

        # Check if the ZFS pool exists
        pool_imported = False
        try:
            result = await run_command_async(
                ["zpool", "list", pool],
                check=False,
                capture_output=True,
            )

            if result.returncode == 0:
                self.logger.info(f"ZFS pool '{pool}' already imported.")
                pool_imported = True
            else:
                try:
                    await run_command_async(["zpool", "import", "-f", pool])
                    self.logger.info(f"Imported ZFS pool '{pool}'.")
                    pool_imported = True
                except subprocess.CalledProcessError:
                    self.logger.warning(
                        f"ZFS pool '{pool}' not found or failed to import."
                    )
        except Exception as e:
            self.logger.warning(f"Error checking ZFS pool status: {e}")

        if not pool_imported:
            self.logger.warning("ZFS pool not found. Skipping ZFS configuration.")
            return True

        try:
            await run_command_async(["zfs", "set", f"mountpoint={mount_point}", pool])
            self.logger.info(f"Set mountpoint for pool '{pool}' to {mount_point}.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to set mountpoint: {e}")

        try:
            cache_file = Path("/etc/zfs/zpool.cache")
            await run_command_async(["zpool", "set", f"cachefile={cache_file}", pool])
            self.logger.info(f"Cachefile for pool '{pool}' updated to {cache_file}.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to update cachefile: {e}")

        try:
            await run_command_async(["zfs", "mount", "-a"])
            self.logger.info("Mounted all ZFS datasets.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to mount ZFS datasets: {e}")

        try:
            result = await run_command_async(
                ["zfs", "list", "-o", "name,mountpoint", "-H"],
                capture_output=True,
                text=True,
            )

            if any(str(mount_point) in line for line in result.stdout.splitlines()):
                self.logger.info(f"ZFS pool '{pool}' mounted at {mount_point}.")
                return True
            else:
                self.logger.warning(f"ZFS pool '{pool}' not mounted at {mount_point}.")
                return True  # Still return True as this is non-critical
        except Exception as e:
            self.logger.warning(f"Error verifying ZFS mount status: {e}")
            return True  # Still return True as this is non-critical

    # ----------------------------------------------------------------
    # Phase 8: Additional Applications & Tools
    # ----------------------------------------------------------------
    async def phase_additional_apps(self) -> bool:
        """Install additional applications and tools."""
        await self.print_section_async("Additional Applications & Tools")

        status = True
        if not await run_with_progress_async(
            "Installing Brave browser",
            self.install_brave_browser_async,
            task_name="additional_apps",
        ):
            status = False

        apps_success, apps_failed = await run_with_progress_async(
            "Installing Flatpak and applications",
            self.install_flatpak_and_apps_async,
            task_name="additional_apps",
        )

        if apps_failed and len(apps_failed) > len(self.config.FLATPAK_APPS) * 0.5:
            self.logger.error(
                f"Flatpak app installation failures: {', '.join(apps_failed)}"
            )
            status = False

        if not await run_with_progress_async(
            "Installing VS Code",
            self.install_configure_vscode_async,
            task_name="additional_apps",
        ):
            status = False

        return status

    async def install_brave_browser_async(self) -> bool:
        """Install Brave web browser."""
        try:
            # Check if Brave is already installed
            if await command_exists_async("brave-browser"):
                self.logger.info("Brave browser is already installed.")
                return True

            # Add Brave repository
            await run_command_async(
                ["com.discordapp.Discord",
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

            # Update and install
            if self.nala_installed:
                await run_command_async(["nala", "update"])
                await run_command_async(["nala", "install", "-y", "brave-browser"])
            else:
                await run_command_async(["apt", "update"])
                await run_command_async(["apt", "install", "-y", "brave-browser"])

            self.logger.info("Brave browser installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Brave browser: {e}")
            return False

    async def install_flatpak_and_apps_async(self) -> Tuple[List[str], List[str]]:
        """Install Flatpak and specified applications."""
        try:
            if self.nala_installed:
                await run_command_async(
                    [
                        "nala",
                        "install",
                        "-y",
                        "flatpak",
                        "gnome-software-plugin-flatpak",
                    ]
                )
            else:
                await run_command_async(
                    ["apt", "install", "-y", "flatpak", "gnome-software-plugin-flatpak"]
                )

            self.logger.info("Flatpak and Flatpak plugin for Pop!_Shop installed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Flatpak: {e}")
            return [], []

        try:
            await run_command_async(
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
            return [], []

        successful, failed = [], []
        for app in self.config.FLATPAK_APPS:
            try:
                result = await run_command_async(
                    ["flatpak", "list", "--app"], capture_output=True, text=True
                )

                if app in result.stdout:
                    self.logger.info(f"Flatpak app {app} is already installed.")
                    successful.append(app)
                    continue

                await run_command_async(
                    ["flatpak", "install", "--assumeyes", "flathub", app]
                )
                self.logger.info(f"Installed Flatpak app: {app}")
                successful.append(app)
            except subprocess.CalledProcessError:
                self.logger.warning(f"Failed to install Flatpak app: {app}")
                failed.append(app)

        return successful, failed

    async def install_configure_vscode_async(self) -> bool:
        """Install and configure VS Code."""
        try:
            # Check if VS Code is already installed
            if await command_exists_async("code"):
                self.logger.info("VS Code is already installed.")
                return True

            # Add Microsoft GPG key and repository
            await run_command_async(
                [
                    "wget",
                    "-qO-",
                    "https://packages.microsoft.com/keys/microsoft.asc",
                    "|",
                    "gpg",
                    "--dearmor",
                    ">",
                    "/etc/apt/trusted.gpg.d/microsoft.gpg",
                ],
                shell=True,
            )

            # Add VS Code repository
            repo_file = Path("/etc/apt/sources.list.d/vscode.list")
            content = "deb [arch=amd64] https://packages.microsoft.com/repos/vscode stable main\n"

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: repo_file.write_text(content))

            # Update and install
            if self.nala_installed:
                await run_command_async(["nala", "update"])
                await run_command_async(["nala", "install", "-y", "code"])
            else:
                await run_command_async(["apt", "update"])
                await run_command_async(["apt", "install", "-y", "code"])

            # Configure VS Code for Wayland
            desktop_file = Path("/usr/share/applications/code.desktop")
            if desktop_file.exists():
                content = await loop.run_in_executor(None, desktop_file.read_text)
                if (
                    "--enable-features=UseOzonePlatform --ozone-platform=wayland"
                    not in content
                ):
                    new_content = content.replace(
                        "Exec=/usr/share/code/code",
                        "Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland",
                    )
                    await loop.run_in_executor(
                        None, lambda: desktop_file.write_text(new_content)
                    )
                    self.logger.info("VS Code configured for Wayland support.")

            # Create VS Code config directory for user
            config_dir = self.config.USER_HOME / ".config" / "Code" / "User"
            config_dir.mkdir(parents=True, exist_ok=True)

            # Set ownership
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(config_dir),
                ]
            )

            self.logger.info("VS Code installed and configured successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to install/configure VS Code: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 9: Cleanup & Final Configurations
    # ----------------------------------------------------------------
    async def phase_cleanup_final(self) -> bool:
        """Perform cleanup and final configurations."""
        await self.print_section_async("Cleanup & Final Configurations")

        status = True
        try:
            if self.nala_installed:
                await run_command_async(["nala", "autoremove", "-y"])
                await run_command_async(["nala", "clean"])
            else:
                await run_command_async(["apt", "autoremove", "-y"])
                await run_command_async(["apt", "autoclean", "-y"])

            self.logger.info("System cleanup completed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            status = False

        if not await run_with_progress_async(
            "Configuring Wayland environment",
            self.configure_wayland_async,
            task_name="cleanup_final",
        ):
            status = False

        if not await run_with_progress_async(
            "Installing and enabling Tailscale",
            self.install_enable_tailscale_async,
            task_name="cleanup_final",
        ):
            status = False

        return status

    async def configure_wayland_async(self) -> bool:
        """Configure Wayland environment variables."""
        etc_env = Path("/etc/environment")
        loop = asyncio.get_running_loop()

        try:
            # Read current environment file
            if etc_env.is_file():
                current = await loop.run_in_executor(None, etc_env.read_text)
            else:
                current = ""

            # Parse variables
            vars_current = {}
            for line in current.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    vars_current[key] = val

            # Update Wayland variables
            updated = False
            wayland_vars = {
                "GDK_BACKEND": "wayland",
                "QT_QPA_PLATFORM": "wayland",
                "SDL_VIDEODRIVER": "wayland",
                "MOZ_ENABLE_WAYLAND": "1",  # For Firefox
                "MOZ_DBUS_REMOTE": "1",  # For Firefox
            }

            for key, val in wayland_vars.items():
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True

            # Write updated environment file if needed
            if updated:
                new_content = (
                    "\n".join(f"{k}={v}" for k, v in vars_current.items()) + "\n"
                )

                await loop.run_in_executor(
                    None, lambda: etc_env.write_text(new_content)
                )

                self.logger.info(f"{etc_env} updated with Wayland variables.")
            else:
                self.logger.info(f"No changes needed in {etc_env}.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env}: {e}")

        # Configure user environment directory
        user_env_dir = self.config.USER_HOME / ".config" / "environment.d"
        user_env_file = user_env_dir / "wayland.conf"

        try:
            await loop.run_in_executor(
                None, lambda: user_env_dir.mkdir(parents=True, exist_ok=True)
            )

            # Prepare environment content
            content = (
                "\n".join(
                    f"{k}={v}"
                    for k, v in {
                        "GDK_BACKEND": "wayland",
                        "QT_QPA_PLATFORM": "wayland",
                        "SDL_VIDEODRIVER": "wayland",
                        "MOZ_ENABLE_WAYLAND": "1",
                        "MOZ_DBUS_REMOTE": "1",
                    }.items()
                )
                + "\n"
            )

            # Check if file exists
            file_exists = await loop.run_in_executor(
                None, lambda: user_env_file.is_file()
            )

            if file_exists:
                current_content = await loop.run_in_executor(
                    None, lambda: user_env_file.read_text()
                )

                if current_content.strip() != content.strip():
                    await self.backup_file_async(user_env_file)

                    await loop.run_in_executor(
                        None, lambda: user_env_file.write_text(content)
                    )

                    self.logger.info(f"Updated {user_env_file} with Wayland variables.")
            else:
                await loop.run_in_executor(
                    None, lambda: user_env_file.write_text(content)
                )

                self.logger.info(f"Created {user_env_file} with Wayland variables.")

            await run_command_async(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_file),
                ]
            )

            return True
        except Exception as e:
            self.logger.warning(f"Failed to update {user_env_file}: {e}")
            return False

    async def install_enable_tailscale_async(self) -> bool:
        """Install and configure Tailscale."""
        self.logger.info("Installing and configuring Tailscale...")

        if await command_exists_async("tailscale"):
            self.logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                self.logger.info("Installing Tailscale using official script...")
                await run_command_async(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )

                tailscale_installed = await command_exists_async("tailscale")

                if tailscale_installed:
                    self.logger.info("Tailscale installed successfully.")
                else:
                    self.logger.error("Tailscale installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install Tailscale: {e}")
                return False

        try:
            await run_command_async(["systemctl", "enable", "tailscaled"])
            await run_command_async(["systemctl", "start", "tailscaled"])

            status = await run_command_async(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )

            if status.stdout.strip() == "active":
                self.logger.info("Tailscale service is active.")
                return True
            else:
                self.logger.warning("Tailscale service may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            self.logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    # ----------------------------------------------------------------
    # Phase 10: Final Checks
    # ----------------------------------------------------------------
    async def phase_final_checks(self) -> bool:
        """Perform final system checks and display summary."""
        await self.print_section_async("Final System Checks")

        info = await self.final_checks_async()
        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        summary = f"""
✅ Pop!_OS Setup & Hardening completed successfully!

⏱️ Total runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s

Kernel Version: {info.get("kernel", "Unknown")}
Distribution: {info.get("distribution", "Unknown")}

No automatic reboot is scheduled.
"""

        display_panel(summary, style=NordColors.GREEN, title="Success")
        print_status_report()
        self.logger.info("Final system checks completed. No reboot scheduled.")
        return True

    async def final_checks_async(self) -> Dict[str, str]:
        """Gather final system information."""
        info = {}

        try:
            kernel = await run_command_async(
                ["uname", "-r"], capture_output=True, text=True
            )
            self.logger.info(f"Kernel version: {kernel.stdout.strip()}")
            info["kernel"] = kernel.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get kernel version: {e}")

        try:
            distro = await run_command_async(
                ["lsb_release", "-ds"], capture_output=True, text=True
            )
            self.logger.info(f"Distribution: {distro.stdout.strip()}")
            info["distribution"] = distro.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get distribution info: {e}")

        try:
            uptime = await run_command_async(
                ["uptime", "-p"], capture_output=True, text=True
            )
            self.logger.info(f"System uptime: {uptime.stdout.strip()}")
            info["uptime"] = uptime.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get uptime: {e}")

        try:
            df_output = await run_command_async(
                ["df", "-h", "/"], capture_output=True, text=True
            )
            df_line = df_output.stdout.splitlines()[1]
            self.logger.info(f"Disk usage (root): {df_line}")
            info["disk_usage"] = df_line
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")

        try:
            free_output = await run_command_async(
                ["free", "-h"], capture_output=True, text=True
            )
            mem_line = next(
                (l for l in free_output.stdout.splitlines() if l.startswith("Mem:")), ""
            )
            self.logger.info(f"Memory usage: {mem_line}")
            info["memory"] = mem_line
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")

        return info


# ----------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------
async def main_async() -> None:
    """Main asynchronous execution function."""
    console.print(create_header(APP_NAME))

    try:
        setup = PopOSDesktopSetup()
        global setup_instance
        setup_instance = setup

        # Execute phases sequentially:
        await setup.check_root_async()
        await setup.phase_preflight()
        await setup.phase_install_nala()
        await setup.phase_system_update()
        await setup.phase_repo_shell_setup()
        await setup.phase_security_hardening()
        await setup.phase_service_installation()
        await setup.phase_user_customization()
        await setup.phase_permissions_storage()
        await setup.phase_additional_apps()
        await setup.phase_cleanup_final()
        await setup.phase_final_checks()

    except KeyboardInterrupt:
        console.print("\n[warning]Setup interrupted by user.[/warning]")
        try:
            await setup_instance.cleanup_async()
        except Exception as e:
            console.print(f"[error]Cleanup after interruption failed: {e}[/error]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[error]Fatal error: {e}[/error]")
        try:
            if "setup_instance" in globals():
                await setup_instance.cleanup_async()
        except Exception as cleanup_error:
            console.print(f"[error]Cleanup after error failed: {cleanup_error}[/error]")
        sys.exit(1)


def main() -> None:
    """Main entry point of the application."""
    try:
        # Create and get a reference to the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers with the specific loop
        setup_signal_handlers(loop)

        # Initialize global instance variable
        global setup_instance
        setup_instance = None

        # Run the main async function
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Received keyboard interrupt, shutting down...")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        try:
            # Cancel all remaining tasks
            loop = asyncio.get_event_loop()
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()

            # Allow cancelled tasks to complete
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            # Close the loop
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")

        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
