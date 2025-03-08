#!/usr/bin/env python3

# ----------------------------------------------------------------
# Dependencies and Imports
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
    from rich import box
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
APP_NAME: str = "Ubuntu Server Setup"
VERSION: str = "1.0.0"
OPERATION_TIMEOUT: int = 300  # 5 minutes default timeout for operations

# Status tracking for each phase of the setup
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "user_setup": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "essential_packages": {"status": "pending", "message": ""},
    "dev_tools": {"status": "pending", "message": ""},
    "docker_setup": {"status": "pending", "message": ""},
    "network_tools": {"status": "pending", "message": ""},
    "storage_config": {"status": "pending", "message": ""},
    "custom_apps": {"status": "pending", "message": ""},
    "auto_updates": {"status": "pending", "message": ""},
    "cleanup": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}

# Type variable for generic functions
T = TypeVar("T")


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Config:
    """Configuration for the Ubuntu server setup process."""

    LOG_FILE: str = "/var/log/ubuntu_server_setup.log"
    USERNAME: str = "admin"
    USER_HOME: Path = field(default_factory=lambda: Path("/home/admin"))
    SSH_PORT: int = 22
    HOSTNAME: str = "ubuntu-server"
    TIMEZONE: str = "UTC"
    ESSENTIAL_PACKAGES: List[str] = field(
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
            "nala",
            "restic",
        ]
    )

    DEV_PACKAGES: List[str] = field(
        default_factory=lambda: [
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
        ]
    )

    NETWORK_PACKAGES: List[str] = field(
        default_factory=lambda: [
            "iftop",
            "traceroute",
            "mtr",
            "glances",
            "whois",
            "dnsutils",
            "iproute2",
            "iputils-ping",
        ]
    )

    CUSTOM_APPS: List[str] = field(
        default_factory=lambda: [
            "tailscale",
            "docker",
            "docker-compose",
            "fastfetch",
        ]
    )

    # SSH hardening configuration
    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "Port": "22",
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "X11Forwarding": "no",
            "MaxAuthTries": "3",
            "ClientAliveInterval": "300",
            "ClientAliveCountMax": "3",
            "AllowTcpForwarding": "yes",
            "AllowAgentForwarding": "yes",
            "AuthorizedKeysFile": ".ssh/authorized_keys",
            "PubkeyAuthentication": "yes",
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
        subtitle=Text(
            "Server Configuration Tool", style=f"bold {NordColors.SNOW_STORM_1}"
        ),
        subtitle_align="center",
        box=box.ROUNDED,
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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=f"{style}",
        padding=(1, 2),
        title=f"[bold {style}]{title}[/{style}]" if title else None,
        box=box.ROUNDED,
    )
    console.print(panel)


def print_status_report() -> None:
    """Print a status report table for all setup phases."""
    table = Table(title="Setup Status Report", style="banner", box=box.ROUNDED)
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
            title="[banner]Ubuntu Server Setup Status[/banner]",
            border_style=NordColors.FROST_3,
            box=box.ROUNDED,
        )
    )


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    """Set up and configure the logger."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ubuntu_server_setup")
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

    logger = logging.getLogger("ubuntu_server_setup")
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
    logger = logging.getLogger("ubuntu_server_setup")
    logger.info("Cleaning up temporary files.")

    tmp = Path(tempfile.gettempdir())
    for item in tmp.iterdir():
        if item.name.startswith("ubuntu_server_setup_"):
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
        logger = logging.getLogger("ubuntu_server_setup")
        logger.error(f"Error during temp file cleanup: {e}")


# Register cleanup with atexit
atexit.register(cleanup_temp_files)


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
    logger = logging.getLogger("ubuntu_server_setup")
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
# Download Helper
# ----------------------------------------------------------------
async def download_file_async(
    url: str, dest: Union[str, Path], timeout: int = 300
) -> None:
    """
    Download a file from the given URL to the destination asynchronously.
    """
    dest = Path(dest)
    logger = logging.getLogger("ubuntu_server_setup")

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
# Main Setup Class
# ----------------------------------------------------------------
class UbuntuServerSetup:
    """Main class for Ubuntu Server setup and configuration."""

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
            for item in tmp.glob("ubuntu_server_setup_*"):
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
    # Phase 0: Preflight Checks
    # ----------------------------------------------------------------
    async def phase_preflight(self) -> bool:
        """Run pre-flight checks and create backups."""
        await self.print_section_async("Pre-flight Checks")

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
                "Installing Nala package manager",
                self.install_nala_async,
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

    async def install_nala_async(self) -> bool:
        """Install and configure the Nala package manager."""
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

    async def save_config_snapshot_async(self) -> Optional[str]:
        """Save a snapshot of the current configuration."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot_file = backup_dir / f"config_snapshot_{timestamp}.tar.gz"

        important_configs = [
            "/etc/passwd",
            "/etc/group",
            "/etc/ssh/sshd_config",
            "/etc/hostname",
            "/etc/hosts",
            "/etc/fstab",
            "/etc/sudoers",
            "/etc/netplan",
        ]

        try:
            # Use a thread pool for file operations
            loop = asyncio.get_running_loop()

            # Create a temp list to track added files
            files_added = []

            # Create the archive
            def create_archive():
                nonlocal files_added
                with tarfile.open(snapshot_file, "w:gz") as tar:
                    for cfg_path in important_configs:
                        cfg = Path(cfg_path)
                        if cfg.is_file():
                            tar.add(str(cfg), arcname=cfg.name)
                            files_added.append(str(cfg))
                        elif cfg.is_dir():
                            for file in cfg.glob("*"):
                                if file.is_file():
                                    tar.add(
                                        str(file), arcname=f"{cfg.name}/{file.name}"
                                    )
                                    files_added.append(str(file))

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
    # Phase 1: System Update & Basic Configuration
    # ----------------------------------------------------------------
    async def phase_system_update(self) -> bool:
        """Update system packages and configure basic settings."""
        await self.print_section_async("System Update & Basic Configuration")

        status = True
        if not await run_with_progress_async(
            "Updating system packages",
            self.update_system_async,
            task_name="system_update",
        ):
            status = False

        if not await run_with_progress_async(
            "Setting hostname", self.set_hostname_async, task_name="system_update"
        ):
            status = False

        if not await run_with_progress_async(
            "Setting timezone", self.set_timezone_async, task_name="system_update"
        ):
            status = False

        return status

    async def update_system_async(self) -> bool:
        """Update and upgrade system packages."""
        try:
            self.logger.info("Updating package repositories...")

            if self.nala_installed:
                await run_command_async(["nala", "update"])
                self.logger.info("Upgrading system packages with Nala...")
                await run_command_async(["nala", "upgrade", "-y"])
            else:
                await run_command_async(["apt", "update", "-qq"])
                self.logger.info("Upgrading system packages with apt...")
                await run_command_async(["apt", "upgrade", "-y"])

            self.logger.info("System update and upgrade complete.")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"System update failed: {e}")
            return False

    async def set_hostname_async(self) -> bool:
        """Set the system hostname."""
        try:
            hostname_file = Path("/etc/hostname")

            # Backup existing hostname file
            if hostname_file.exists():
                await self.backup_file_async(hostname_file)

            # Write new hostname
            hostname_file.write_text(self.config.HOSTNAME)

            # Update /etc/hosts file
            hosts_file = Path("/etc/hosts")
            if hosts_file.exists():
                await self.backup_file_async(hosts_file)

                # Read current hosts file
                hosts_content = hosts_file.read_text()

                # Process and update hosts file
                new_hosts = []
                for line in hosts_content.splitlines():
                    if "127.0.1.1" in line:
                        new_hosts.append(f"127.0.1.1\t{self.config.HOSTNAME}")
                    else:
                        new_hosts.append(line)

                # Write updated hosts file
                hosts_file.write_text("\n".join(new_hosts) + "\n")

            # Apply hostname change immediately
            await run_command_async(["hostname", self.config.HOSTNAME])

            self.logger.info(f"Hostname set to {self.config.HOSTNAME}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to set hostname: {e}")
            return False

    async def set_timezone_async(self) -> bool:
        """Set the system timezone."""
        try:
            await run_command_async(
                ["timedatectl", "set-timezone", self.config.TIMEZONE]
            )
            self.logger.info(f"Timezone set to {self.config.TIMEZONE}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set timezone: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 2: User Setup
    # ----------------------------------------------------------------
    async def phase_user_setup(self) -> bool:
        """Set up user accounts and configurations."""
        await self.print_section_async("User Setup")

        status = True
        if not await run_with_progress_async(
            "Creating user account", self.create_user_async, task_name="user_setup"
        ):
            status = False

        if not await run_with_progress_async(
            "Setting up SSH keys", self.setup_ssh_keys_async, task_name="user_setup"
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring sudo access", self.configure_sudo_async, task_name="user_setup"
        ):
            status = False

        return status

    async def create_user_async(self) -> bool:
        """Create the user account if it doesn't exist."""
        try:
            # Check if user exists
            try:
                result = await run_command_async(
                    ["id", self.config.USERNAME],
                    check=False,
                    capture_output=True,
                )
                if result.returncode == 0:
                    self.logger.info(f"User {self.config.USERNAME} already exists.")
                    return True
            except Exception:
                pass

            # Create the user
            self.logger.info(f"Creating user {self.config.USERNAME}...")
            await run_command_async(
                ["useradd", "-m", "-s", "/bin/bash", "-G", "sudo", self.config.USERNAME]
            )

            # Create home directories
            user_home = Path(f"/home/{self.config.USERNAME}")
            user_ssh_dir = user_home / ".ssh"
            user_ssh_dir.mkdir(mode=0o700, exist_ok=True)

            # Set ownership
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_home),
                ]
            )

            self.logger.info(f"User {self.config.USERNAME} created successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to create user: {e}")
            return False

    async def setup_ssh_keys_async(self) -> bool:
        """Set up SSH keys for the user."""
        try:
            ssh_dir = self.config.USER_HOME / ".ssh"
            ssh_dir.mkdir(mode=0o700, exist_ok=True)

            authorized_keys = ssh_dir / "authorized_keys"

            # Ask user for SSH public key or create a new key pair
            console.print()
            choice = Prompt.ask(
                "[bold]Do you want to [1] add an existing SSH public key or [2] generate a new key pair?[/]",
                choices=["1", "2"],
                default="1",
            )

            if choice == "1":
                # Add existing public key
                pub_key = Prompt.ask("[bold]Paste your SSH public key[/]")

                if pub_key.strip():
                    # Write to authorized_keys
                    with open(authorized_keys, "a") as f:
                        f.write(f"{pub_key.strip()}\n")

                    self.logger.info("SSH public key added to authorized_keys.")
                else:
                    self.logger.warning("No SSH key provided.")
                    return False
            else:
                # Generate new key pair
                key_file = self.config.USER_HOME / ".ssh" / "id_rsa"
                await run_command_async(
                    [
                        "ssh-keygen",
                        "-t",
                        "rsa",
                        "-b",
                        "4096",
                        "-f",
                        str(key_file),
                        "-N",
                        "",  # Empty passphrase
                    ]
                )

                # Add to authorized_keys
                shutil.copy2(f"{key_file}.pub", authorized_keys)

                console.print(
                    f"[success]New SSH key pair generated at {key_file}[/success]"
                )
                console.print(
                    f"[warning]The private key will be shown once. Save it securely:[/warning]"
                )

                with open(key_file, "r") as f:
                    private_key = f.read()
                    console.print(
                        Panel(
                            private_key,
                            title="Private Key",
                            border_style=NordColors.YELLOW,
                        )
                    )

            # Set proper permissions
            os.chmod(authorized_keys, 0o600)
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(ssh_dir),
                ]
            )

            self.logger.info("SSH keys configured successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to set up SSH keys: {e}")
            return False

    async def configure_sudo_async(self) -> bool:
        """Configure sudo access for the user."""
        try:
            sudoers_dir = Path("/etc/sudoers.d")
            sudoers_dir.mkdir(exist_ok=True)

            user_sudoers = sudoers_dir / self.config.USERNAME
            sudoers_content = f"{self.config.USERNAME} ALL=(ALL) NOPASSWD:ALL\n"

            # Write to file
            with open(user_sudoers, "w") as f:
                f.write(sudoers_content)

            # Set proper permissions
            os.chmod(user_sudoers, 0o440)

            self.logger.info(f"Sudo access configured for {self.config.USERNAME}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to configure sudo access: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 3: Essential Packages Installation
    # ----------------------------------------------------------------
    async def phase_essential_packages(self) -> bool:
        """Install essential system packages."""
        await self.print_section_async("Essential Packages Installation")

        status = True
        success, failed = await self.install_packages_async(
            self.config.ESSENTIAL_PACKAGES, "essential_packages"
        )

        if failed and len(failed) > len(self.config.ESSENTIAL_PACKAGES) * 0.1:
            self.logger.error(
                f"Failed to install essential packages: {', '.join(failed)}"
            )
            status = False

        return status

    async def install_packages_async(
        self, packages: List[str], task_name: Optional[str] = None
    ) -> Tuple[List[str], List[str]]:
        """Install required packages."""
        description = "Installing packages"
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "in_progress",
                "message": f"{description} in progress...",
            }

        self.logger.info(f"Installing packages: {', '.join(packages)}")
        missing, success, failed = [], [], []

        # Check which packages are already installed
        for pkg in packages:
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
            total_steps = len(missing)

            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn("[bold]{task.description}[/bold]"),
                BarColumn(
                    bar_width=40,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            ) as progress:
                task_id = progress.add_task(
                    f"Installing {len(missing)} packages", total=total_steps
                )

                # Install packages individually for better progress tracking
                for idx, pkg in enumerate(missing):
                    try:
                        progress.update(
                            task_id,
                            description=f"Installing {pkg} ({idx + 1}/{total_steps})",
                        )

                        if self.nala_installed:
                            await run_command_async(["nala", "install", "-y", pkg])
                        else:
                            await run_command_async(["apt", "install", "-y", pkg])

                        success.append(pkg)
                        progress.update(task_id, advance=1)

                    except subprocess.CalledProcessError as e:
                        self.logger.error(f"Failed to install {pkg}: {e}")
                        failed.append(pkg)
                        progress.update(task_id, advance=1)

                    except Exception as e:
                        self.logger.error(f"Error installing {pkg}: {e}")
                        failed.append(pkg)
                        progress.update(task_id, advance=1)
        else:
            self.logger.info("All required packages are installed.")

        # Update task status
        if task_name:
            if not failed:
                SETUP_STATUS[task_name] = {
                    "status": "success",
                    "message": f"All {len(success)} packages installed successfully",
                }
            else:
                SETUP_STATUS[task_name] = {
                    "status": "failed"
                    if len(failed) > len(packages) * 0.1
                    else "success",
                    "message": f"{len(success)} installed, {len(failed)} failed",
                }

        return success, failed

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
            "Configuring firewall", self.configure_firewall_async, task_name="security"
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring Fail2ban", self.configure_fail2ban_async, task_name="security"
        ):
            status = False

        if not await run_with_progress_async(
            "Hardening system settings", self.harden_system_async, task_name="security"
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
            for line in lines:
                # Skip lines with these configs as we'll add them later
                if any(
                    line.strip().startswith(key)
                    for key in self.config.SSH_CONFIG.keys()
                ):
                    continue
                new_lines.append(line)

            # Add our configurations
            for key, val in self.config.SSH_CONFIG.items():
                new_lines.append(f"{key} {val}")

            # Write back the file
            await loop.run_in_executor(
                None, lambda: sshd_config.write_text("\n".join(new_lines) + "\n")
            )

            # Update port in firewall rules if changed
            if self.config.SSH_PORT != 22:
                self.config.FIREWALL_PORTS = [
                    str(self.config.SSH_PORT) if port == "22" else port
                    for port in self.config.FIREWALL_PORTS
                ]

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
            # Reset existing rules
            await run_command_async([ufw_cmd, "reset"])

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
        try:
            # Check if fail2ban is installed
            if not await command_exists_async("fail2ban-client"):
                self.logger.info("fail2ban not installed. Installing...")
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-y", "fail2ban"])
                else:
                    await run_command_async(["apt", "install", "-y", "fail2ban"])
        except Exception as e:
            self.logger.error(f"Failed to install fail2ban: {e}")
            return False

        jail_local = Path("/etc/fail2ban/jail.local")

        # Ensure parent directory exists
        jail_local.parent.mkdir(parents=True, exist_ok=True)

        config_content = (
            "[DEFAULT]\n"
            "bantime  = 3600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            f"port     = {self.config.SSH_PORT}\n"
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

    async def harden_system_async(self) -> bool:
        """Implement additional system hardening measures."""
        try:
            # Harden sysctl settings
            sysctl_config = Path("/etc/sysctl.d/99-security.conf")

            sysctl_settings = [
                # Disable IPv4 forwarding
                "net.ipv4.ip_forward = 0",
                # Enable TCP SYN cookies
                "net.ipv4.tcp_syncookies = 1",
                # Disable packet forwarding
                "net.ipv4.conf.all.send_redirects = 0",
                "net.ipv4.conf.default.send_redirects = 0",
                # Disable IP source routing
                "net.ipv4.conf.all.accept_source_route = 0",
                "net.ipv4.conf.default.accept_source_route = 0",
                # Enable IP spoofing protection
                "net.ipv4.conf.all.rp_filter = 1",
                "net.ipv4.conf.default.rp_filter = 1",
                # Log suspicious packets
                "net.ipv4.conf.all.log_martians = 1",
                "net.ipv4.conf.default.log_martians = 1",
                # Disable ICMP redirect acceptance
                "net.ipv4.conf.all.accept_redirects = 0",
                "net.ipv4.conf.default.accept_redirects = 0",
                "net.ipv6.conf.all.accept_redirects = 0",
                "net.ipv6.conf.default.accept_redirects = 0",
                # Disable secure ICMP redirect acceptance
                "net.ipv4.conf.all.secure_redirects = 0",
                "net.ipv4.conf.default.secure_redirects = 0",
                # Ignore broadcast requests
                "net.ipv4.icmp_echo_ignore_broadcasts = 1",
                # Enable bad error message protection
                "net.ipv4.icmp_ignore_bogus_error_responses = 1",
            ]

            # Write sysctl settings
            with open(sysctl_config, "w") as f:
                f.write("\n".join(sysctl_settings) + "\n")

            # Apply settings
            await run_command_async(["sysctl", "-p", str(sysctl_config)])

            # Harden user resource limits
            limits_config = Path("/etc/security/limits.d/99-resource-limits.conf")

            limits_settings = [
                "# Limit user processes",
                "* soft nproc 1024",
                "* hard nproc 2048",
                "# Limit file descriptors",
                "* soft nofile 4096",
                "* hard nofile 8192",
                "# Limit core dumps",
                "* soft core 0",
                "* hard core 0",
            ]

            # Write limits settings
            with open(limits_config, "w") as f:
                f.write("\n".join(limits_settings) + "\n")

            self.logger.info("System hardening complete.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to harden system: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 5: Development Tools Installation
    # ----------------------------------------------------------------
    async def phase_dev_tools(self) -> bool:
        """Install development tools and libraries."""
        await self.print_section_async("Development Tools Installation")

        status = True
        success, failed = await self.install_packages_async(
            self.config.DEV_PACKAGES, "dev_tools"
        )

        if failed and len(failed) > len(self.config.DEV_PACKAGES) * 0.1:
            self.logger.error(
                f"Failed to install development packages: {', '.join(failed)}"
            )
            status = False

        if not await run_with_progress_async(
            "Configuring Python environment",
            self.configure_python_async,
            task_name="dev_tools",
        ):
            status = False

        return status

    async def configure_python_async(self) -> bool:
        """Configure Python development environment."""
        try:
            # Install pip packages globally
            global_pip_packages = [
                "ipython",
                "virtualenv",
                "pipenv",
                "pylint",
                "flake8",
                "black",
                "mypy",
                "requests",
                "rich",
                "pyfiglet",
            ]

            self.logger.info(
                f"Installing global pip packages: {', '.join(global_pip_packages)}"
            )

            try:
                await run_command_async(
                    ["pip3", "install", "--upgrade"] + global_pip_packages
                )
                self.logger.info("Global pip packages installed successfully.")
            except Exception as e:
                self.logger.warning(f"Failed to install some pip packages: {e}")

            # Create Python virtual environment directory
            venv_dir = self.config.USER_HOME / "venvs"
            venv_dir.mkdir(exist_ok=True)

            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(venv_dir),
                ]
            )

            self.logger.info("Python environment configured.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to configure Python environment: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 6: Docker Installation and Setup
    # ----------------------------------------------------------------
    async def phase_docker_setup(self) -> bool:
        """Install and configure Docker."""
        await self.print_section_async("Docker Installation and Setup")

        status = True
        if not await run_with_progress_async(
            "Installing Docker", self.install_docker_async, task_name="docker_setup"
        ):
            status = False

        if not await run_with_progress_async(
            "Setting up Docker Compose",
            self.setup_docker_compose_async,
            task_name="docker_setup",
        ):
            status = False

        return status

    async def install_docker_async(self) -> bool:
        """Install Docker using the official script."""
        try:
            # Check if Docker is already installed
            if await command_exists_async("docker"):
                self.logger.info("Docker is already installed.")

                # Ensure Docker service is enabled
                await run_command_async(["systemctl", "enable", "docker"])
                await run_command_async(["systemctl", "start", "docker"])

                return True

            # Add Docker GPG key and repository
            self.logger.info("Adding Docker repository...")

            # Make sure prerequisites are installed
            await run_command_async(
                [
                    "apt",
                    "install",
                    "-y",
                    "apt-transport-https",
                    "ca-certificates",
                    "curl",
                    "gnupg",
                    "lsb-release",
                ]
            )

            # Add Docker's official GPG key
            keyring_dir = Path("/etc/apt/keyrings")
            keyring_dir.mkdir(exist_ok=True)

            await run_command_async(
                [
                    "sh",
                    "-c",
                    "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
                ]
            )

            # Add repository
            await run_command_async(
                [
                    "sh",
                    "-c",
                    "echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable' > /etc/apt/sources.list.d/docker.list",
                ]
            )

            # Update package lists
            if self.nala_installed:
                await run_command_async(["nala", "update"])
            else:
                await run_command_async(["apt", "update"])

            # Install Docker packages
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

            # Check if Docker was installed
            if not await command_exists_async("docker"):
                self.logger.error("Docker installation failed.")
                return False

            # Enable and start Docker
            await run_command_async(["systemctl", "enable", "docker"])
            await run_command_async(["systemctl", "start", "docker"])

            # Add user to docker group
            await run_command_async(["usermod", "-aG", "docker", self.config.USERNAME])

            self.logger.info("Docker installed and configured successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to install Docker: {e}")
            return False

    async def setup_docker_compose_async(self) -> bool:
        """Set up Docker Compose."""
        try:
            # Check if Docker Compose plugin is installed
            if await command_exists_async("docker") and await command_exists_async(
                "docker-compose"
            ):
                self.logger.info("Docker Compose is already installed.")
                return True

            # Docker Compose should be installed with Docker plugin by default
            if await command_exists_async("docker") and await command_exists_async(
                "docker compose"
            ):
                # Create symlink for compatibility
                docker_compose_path = Path("/usr/local/bin/docker-compose")
                if not docker_compose_path.exists():
                    docker_compose_path.parent.mkdir(exist_ok=True)
                    os.symlink(
                        "/usr/libexec/docker/cli-plugins/docker-compose",
                        docker_compose_path,
                    )
                    self.logger.info(
                        "Created docker-compose symlink for compatibility."
                    )
                return True

            # If we don't have the plugin, install compose separately
            self.logger.info("Installing Docker Compose as standalone...")

            # Download latest compose release
            await download_file_async(
                "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64",
                "/usr/local/bin/docker-compose",
            )

            # Make it executable
            os.chmod("/usr/local/bin/docker-compose", 0o755)

            if await command_exists_async("docker-compose"):
                self.logger.info("Docker Compose installed successfully.")
                return True
            else:
                self.logger.error("Docker Compose installation failed.")
                return False

        except Exception as e:
            self.logger.error(f"Failed to set up Docker Compose: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 7: Network Tools Installation
    # ----------------------------------------------------------------
    async def phase_network_tools(self) -> bool:
        """Install network monitoring and analysis tools."""
        await self.print_section_async("Network Tools Installation")

        status = True
        success, failed = await self.install_packages_async(
            self.config.NETWORK_PACKAGES, "network_tools"
        )

        if failed and len(failed) > len(self.config.NETWORK_PACKAGES) * 0.1:
            self.logger.error(
                f"Failed to install network packages: {', '.join(failed)}"
            )
            status = False

        return status

    # ----------------------------------------------------------------
    # Phase 8: Storage Configuration
    # ----------------------------------------------------------------
    async def phase_storage_config(self) -> bool:
        """Configure storage and backup solutions."""
        await self.print_section_async("Storage Configuration")

        status = True
        if not await run_with_progress_async(
            "Configuring storage directories",
            self.setup_storage_directories_async,
            task_name="storage_config",
        ):
            status = False

        return status

    async def setup_storage_directories_async(self) -> bool:
        """Create and configure storage directories."""
        try:
            # Create common directories
            directories = {
                "/data": 0o755,  # Main data directory
                "/data/backups": 0o750,  # Backups
                "/data/logs": 0o755,  # Logs
                "/data/docker": 0o755,  # Docker volumes
                "/data/www": 0o755,  # Web content
                f"/home/{self.config.USERNAME}/scripts": 0o750,  # User scripts
                f"/home/{self.config.USERNAME}/bin": 0o750,  # User binaries
            }

            for directory, permissions in directories.items():
                dir_path = Path(directory)
                dir_path.mkdir(exist_ok=True, parents=True)
                os.chmod(directory, permissions)

                # Set ownership for user directories
                if directory.startswith(f"/home/{self.config.USERNAME}"):
                    await run_command_async(
                        [
                            "chown",
                            "-R",
                            f"{self.config.USERNAME}:{self.config.USERNAME}",
                            directory,
                        ]
                    )

            # Link Docker data directory
            docker_dir = Path("/var/lib/docker")
            docker_data_dir = Path("/data/docker")

            if docker_dir.exists() and not docker_dir.is_symlink():
                # Stop Docker service
                await run_command_async(["systemctl", "stop", "docker"])

                # Move existing Docker data
                if docker_dir.exists() and docker_dir.is_dir():
                    temp_backup = Path("/var/lib/docker.bak")
                    shutil.move(docker_dir, temp_backup)

                    # Create the new directory and copy data
                    docker_data_dir.mkdir(exist_ok=True, parents=True)
                    await run_command_async(
                        ["rsync", "-a", f"{temp_backup}/", f"{docker_data_dir}/"]
                    )

                    # Remove the original directory
                    shutil.rmtree(temp_backup, ignore_errors=True)

                # Create symlink
                docker_dir.symlink_to(docker_data_dir)

                # Start Docker service
                await run_command_async(["systemctl", "start", "docker"])

                self.logger.info("Docker data directory moved to /data/docker")

            self.logger.info("Storage directories configured.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to configure storage directories: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 9: Custom Applications Installation
    # ----------------------------------------------------------------
    async def phase_custom_apps(self) -> bool:
        """Install custom applications."""
        await self.print_section_async("Custom Applications Installation")

        status = True
        for app in self.config.CUSTOM_APPS:
            if not await run_with_progress_async(
                f"Installing {app}",
                self.install_custom_app_async,
                app,
                task_name="custom_apps",
            ):
                status = False

        return status

    async def install_custom_app_async(self, app_name: str) -> bool:
        """Install a custom application."""
        try:
            if app_name.lower() == "tailscale":
                return await self.install_tailscale_async()
            elif app_name.lower() == "fastfetch":
                return await self.install_fastfetch_async()
            else:
                self.logger.warning(f"No installation method defined for {app_name}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to install {app_name}: {e}")
            return False

    async def install_tailscale_async(self) -> bool:
        """Install and configure Tailscale."""
        self.logger.info("Installing and configuring Tailscale...")

        if await command_exists_async("tailscale"):
            self.logger.info("Tailscale is already installed.")
            return True

        try:
            # Add Tailscale repository
            await run_command_async(
                [
                    "sh",
                    "-c",
                    "curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null",
                ]
            )

            await run_command_async(
                [
                    "sh",
                    "-c",
                    "curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list",
                ]
            )

            # Update and install
            if self.nala_installed:
                await run_command_async(["nala", "update"])
                await run_command_async(["nala", "install", "-y", "tailscale"])
            else:
                await run_command_async(["apt", "update"])
                await run_command_async(["apt", "install", "-y", "tailscale"])

            # Enable and start service
            await run_command_async(["systemctl", "enable", "--now", "tailscaled"])

            console.print(
                Panel(
                    "Tailscale installed. Run 'sudo tailscale up' to connect to your Tailscale network.",
                    title="Tailscale Setup",
                    border_style=NordColors.FROST_2,
                    box=box.ROUNDED,
                )
            )

            # Check if installation was successful
            if await command_exists_async("tailscale"):
                self.logger.info("Tailscale installed successfully.")
                return True
            else:
                self.logger.error("Tailscale installation verification failed.")
                return False

        except Exception as e:
            self.logger.error(f"Failed to install Tailscale: {e}")
            return False

    async def install_fastfetch_async(self) -> bool:
        """Install Fastfetch for system information display."""
        try:
            if await command_exists_async("fastfetch"):
                self.logger.info("Fastfetch is already installed.")
                return True

            # Download and install Fastfetch
            temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")

            await download_file_async(
                "https://github.com/fastfetch-cli/fastfetch/releases/download/2.8.3/fastfetch-linux-amd64.deb",
                temp_deb,
            )

            await run_command_async(["dpkg", "-i", str(temp_deb)])

            # Fix dependencies if needed
            try:
                if self.nala_installed:
                    await run_command_async(["nala", "install", "-f", "-y"])
                else:
                    await run_command_async(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to fix Fastfetch dependencies.")

            # Clean up
            if temp_deb.exists():
                temp_deb.unlink()

            # Check if installation was successful
            if await command_exists_async("fastfetch"):
                self.logger.info("Fastfetch installed successfully.")
                return True
            else:
                self.logger.error("Fastfetch installation verification failed.")
                return False

        except Exception as e:
            self.logger.error(f"Failed to install Fastfetch: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 10: Automatic Updates Configuration
    # ----------------------------------------------------------------
    async def phase_auto_updates(self) -> bool:
        """Configure automatic security updates."""
        await self.print_section_async("Automatic Updates Configuration")

        return await run_with_progress_async(
            "Setting up automatic security updates",
            self.configure_auto_updates_async,
            task_name="auto_updates",
        )

    async def configure_auto_updates_async(self) -> bool:
        """Configure unattended-upgrades for automatic security updates."""
        try:
            # Install unattended-upgrades
            if self.nala_installed:
                await run_command_async(
                    ["nala", "install", "-y", "unattended-upgrades", "apt-listchanges"]
                )
            else:
                await run_command_async(
                    ["apt", "install", "-y", "unattended-upgrades", "apt-listchanges"]
                )

            # Configure unattended-upgrades
            config_file = Path("/etc/apt/apt.conf.d/50unattended-upgrades")
            auto_update_file = Path("/etc/apt/apt.conf.d/20auto-upgrades")

            if config_file.exists():
                await self.backup_file_async(config_file)

            # Configuration content
            config_content = """// Automatically upgrade packages from these (origin:archive) pairs
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
    "${distro_id}:${distro_codename}-updates";
};

// List of packages to not update
Unattended-Upgrade::Package-Blacklist {
//    "vim";
//    "libc6";
//    "libc6-dev";
//    "libc6-i686";
};

// This option will controls whether the updates should be downloaded and installed immediately
// or should be just downloaded (and installed later)
Unattended-Upgrade::AutoFixInterruptedDpkg "true";

// Split the upgrade into the smallest possible chunks so that
// they can be interrupted with SIGTERM.
Unattended-Upgrade::MinimalSteps "true";

// Install all unattended-upgrades when the machine is shutting down
// instead of doing it in the background while the machine is running
// This will (obviously) make shutdown slower
Unattended-Upgrade::InstallOnShutdown "false";

// Send email to this address for problems or packages upgrades
// If empty or unset then no email is sent, make sure that you
// have a working mail setup on your system. A package that provides
// 'mailx' must be installed. E.g. "user@example.com"
Unattended-Upgrade::Mail "";

// Set this value to "true" to get emails only on errors. Default
// is to always send a mail if Unattended-Upgrade::Mail is set
Unattended-Upgrade::MailOnlyOnError "true";

// Remove unused automatically installed kernel-related packages
// (kernel images, kernel headers and kernel version dependent packages).
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";

// Do automatic removal of newly unused dependencies after the upgrade
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";

// Do automatic removal of unused packages after the upgrade
// (equivalent to apt-get autoremove)
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// Automatically reboot *WITHOUT CONFIRMATION*
// if the file /var/run/reboot-required is found after the upgrade
Unattended-Upgrade::Automatic-Reboot "false";

// If automatic reboot is enabled and needed, reboot at the specific
// time instead of immediately
// Default: "now"
Unattended-Upgrade::Automatic-Reboot-Time "02:00";

// Use apt bandwidth limit feature, this example limits the download
// speed to 70kb/sec
//Acquire::http::Dl-Limit "70";
"""

            # Write configuration
            with open(config_file, "w") as f:
                f.write(config_content)

            # Configure auto-upgrades
            auto_update_content = """APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
"""

            with open(auto_update_file, "w") as f:
                f.write(auto_update_content)

            # Enable the service
            await run_command_async(["systemctl", "enable", "unattended-upgrades"])
            await run_command_async(["systemctl", "restart", "unattended-upgrades"])

            self.logger.info("Automatic security updates configured.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to configure automatic updates: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 11: Cleanup & Final Configuration
    # ----------------------------------------------------------------
    async def phase_cleanup(self) -> bool:
        """Perform final cleanup and optimization."""
        await self.print_section_async("Cleanup & Final Configuration")

        status = True
        if not await run_with_progress_async(
            "Cleaning up system", self.system_cleanup_async, task_name="cleanup"
        ):
            status = False

        if not await run_with_progress_async(
            "Configuring .bashrc", self.configure_bashrc_async, task_name="cleanup"
        ):
            status = False

        return status

    async def system_cleanup_async(self) -> bool:
        """Clean up unnecessary packages and files."""
        try:
            # Remove unnecessary packages
            if self.nala_installed:
                await run_command_async(["nala", "autoremove", "-y"])
                await run_command_async(["nala", "clean"])
            else:
                await run_command_async(["apt", "autoremove", "-y"])
                await run_command_async(["apt", "clean"])

            # Clear logs
            log_dir = Path("/var/log")
            for log_file in log_dir.glob("*.log.*"):
                try:
                    log_file.unlink()
                except:
                    pass

            # Clear temporary files
            tmp_dir = Path("/tmp")
            for item in tmp_dir.glob("*"):
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                except:
                    pass

            self.logger.info("System cleanup completed.")
            return True

        except Exception as e:
            self.logger.error(f"Error during system cleanup: {e}")
            return False

    async def configure_bashrc_async(self) -> bool:
        """Configure user .bashrc with useful aliases and settings."""
        try:
            # Create bashrc file
            bashrc_file = self.config.USER_HOME / ".bashrc"
            bashrc_backup = None

            if bashrc_file.exists():
                bashrc_backup = await self.backup_file_async(bashrc_file)

            bashrc_content = """# ~/.bashrc: executed by bash(1) for non-login shells.

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# don't put duplicate lines or lines starting with space in the history
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length
HISTSIZE=10000
HISTFILESIZE=20000

# check the window size after each command
shopt -s checkwinsize

# make less more friendly for non-text input files
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# set a fancy prompt
PS1='${debian_chroot:+($debian_chroot)}\\[\\033[01;32m\\]\\u@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ '

# enable color support
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# colored GCC warnings and errors
export GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

# some more ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Add an "alert" alias
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" "$(history|tail -n1|sed -e '\''s/^\\s*[0-9]\\+\\s*//;s/[;&|]\\s*alert$//'\'')"'

# enable programmable completion features
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi

# User specific aliases and functions
alias update='sudo nala update && sudo nala upgrade -y'
alias install='sudo nala install -y'
alias remove='sudo nala remove'
alias search='nala search'
alias dpurge='docker system prune -af'
alias dcup='docker-compose up -d'
alias dcdown='docker-compose down'
alias dcps='docker-compose ps'
alias dclogs='docker-compose logs -f'

# Add user's bin directory to PATH
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi

# Display system information on login if available
if command -v fastfetch &> /dev/null; then
    fastfetch
elif command -v neofetch &> /dev/null; then
    neofetch
fi

# Set default editor
export EDITOR=vim
export VISUAL=vim

# Customize history
export HISTTIMEFORMAT="%F %T "
export HISTIGNORE="ls:ll:history:pwd:exit:clear"

# Set terminal colors
export TERM=xterm-256color

# User specific environment variables
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
"""

            with open(bashrc_file, "w") as f:
                f.write(bashrc_content)

            # Set correct ownership
            await run_command_async(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(bashrc_file),
                ]
            )

            # Set correct permissions
            os.chmod(bashrc_file, 0o644)

            self.logger.info("Configured .bashrc for enhanced user experience.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to configure .bashrc: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 12: Final Checks & Summary
    # ----------------------------------------------------------------
    async def phase_final_checks(self) -> bool:
        """Perform final system checks and display summary."""
        await self.print_section_async("Final System Checks")

        system_info = await self.get_system_info_async()
        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        summary = f"""
✅ Ubuntu Server Setup completed successfully!

⏱️ Total runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s

System Information:
- Hostname: {system_info.get("hostname", "Unknown")}
- IP Address: {system_info.get("ip_address", "Unknown")}
- SSH Port: {self.config.SSH_PORT}
- Username: {self.config.USERNAME}

Storage Information:
{system_info.get("disk_usage", "Disk usage information not available")}

A reboot is recommended to apply all changes.
"""

        display_panel(summary, style=NordColors.GREEN, title="Success")
        print_status_report()

        # Ask about reboot
        if Confirm.ask("Would you like to reboot the system now?", default=False):
            self.logger.info("Rebooting system...")
            await run_command_async(["reboot"])
        else:
            self.logger.info("System ready. Reboot recommended when convenient.")

        return True

    async def get_system_info_async(self) -> Dict[str, str]:
        """Gather system information for the final report."""
        info = {}

        try:
            # Get hostname
            hostname_result = await run_command_async(
                ["hostname"], capture_output=True, text=True
            )
            info["hostname"] = hostname_result.stdout.strip()

            # Get IP address (prefer non-loopback IP)
            ip_result = await run_command_async(
                ["hostname", "-I"], capture_output=True, text=True
            )
            ip_addresses = ip_result.stdout.strip().split()
            if ip_addresses:
                info["ip_address"] = ip_addresses[0]
            else:
                info["ip_address"] = "Not available"

            # Get kernel version
            kernel_result = await run_command_async(
                ["uname", "-r"], capture_output=True, text=True
            )
            info["kernel"] = kernel_result.stdout.strip()

            # Get disk usage
            df_result = await run_command_async(
                ["df", "-h"], capture_output=True, text=True
            )
            info["disk_usage"] = df_result.stdout

            # Get memory usage
            free_result = await run_command_async(
                ["free", "-h"], capture_output=True, text=True
            )
            info["memory"] = free_result.stdout

            return info

        except Exception as e:
            self.logger.error(f"Error gathering system information: {e}")
            return {"error": str(e)}


# ----------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------
async def main_async() -> None:
    """Main asynchronous execution function."""
    console.print(create_header(APP_NAME))

    try:
        # Create setup instance
        config = Config()  # Default config or parse command line arguments
        setup = UbuntuServerSetup(config)
        global setup_instance
        setup_instance = setup

        # Execute phases sequentially
        await setup.phase_preflight()
        await setup.phase_system_update()
        await setup.phase_user_setup()
        await setup.phase_essential_packages()
        await setup.phase_security_hardening()
        await setup.phase_dev_tools()
        await setup.phase_docker_setup()
        await setup.phase_network_tools()
        await setup.phase_storage_config()
        await setup.phase_custom_apps()
        await setup.phase_auto_updates()
        await setup.phase_cleanup()
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
        console.print_exception()
        try:
            if "setup_instance" in globals():
                await setup_instance.cleanup_async()
        except Exception as cleanup_error:
            console.print(f"[error]Cleanup after error failed: {cleanup_error}[/error]")
        sys.exit(1)
