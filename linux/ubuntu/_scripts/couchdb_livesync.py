#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import shutil
import socket
import json
import asyncio
import atexit
import re
import getpass
import secrets
import string
import logging
import datetime
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "couchdb installer"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER") or "user"
OPERATION_TIMEOUT: int = 60  # Extended for longer operations
DEFAULT_COUCHDB_PORT: int = 5984
DEFAULT_DOMAIN: str = "obsidian-livesync.example.com"
RETRY_COUNT: int = 3  # Number of retries for failed operations
RETRY_DELAY: int = 3  # Seconds to wait between retries

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/couchdb_installer")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
NGINX_CONFIG_PATH: str = "/etc/nginx/sites-available"
NGINX_ENABLED_PATH: str = "/etc/nginx/sites-enabled"
LOG_FILE: str = os.path.join(CONFIG_DIR, "couchdb_installer.log")
MAX_LOG_ENTRIES: int = 10000  # For in-memory log storage


class NordColors:
    """Color constants using the Nord color palette."""

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
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


@dataclass
class LogEntry:
    """Represents a log entry with timestamp, level, and message."""

    timestamp: float
    level: str
    message: str
    details: Optional[str] = None

    def formatted_time(self) -> str:
        """Return a formatted timestamp string."""
        return datetime.datetime.fromtimestamp(self.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_color(self) -> str:
        """Return the appropriate color for this log level."""
        if self.level == "ERROR":
            return NordColors.RED
        elif self.level == "WARNING":
            return NordColors.YELLOW
        elif self.level == "SUCCESS":
            return NordColors.GREEN
        elif self.level == "DEBUG":
            return NordColors.PURPLE
        else:
            return NordColors.FROST_2


class Logger:
    """Custom logger that outputs to console, file, and keeps in-memory logs."""

    def __init__(self, log_file: str, max_entries: int = 1000):
        self.log_file = log_file
        self.max_entries = max_entries
        self.logs = deque(maxlen=max_entries)

        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

        # Set up file logger
        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Add console handler for stdout
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        self.console_handler.setFormatter(formatter)

        # Create logger
        self.logger = logging.getLogger("couchdb_installer")
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate logs
        if not self.logger.handlers:
            self.logger.addHandler(self.console_handler)

    def _add_to_memory(
        self, level: str, message: str, details: Optional[str] = None
    ) -> None:
        """Add a log entry to the in-memory log storage."""
        entry = LogEntry(
            timestamp=time.time(), level=level, message=message, details=details
        )
        self.logs.append(entry)

    def debug(self, message: str, details: Optional[str] = None) -> None:
        """Log a debug message."""
        self.logger.debug(message)
        self._add_to_memory("DEBUG", message, details)

    def info(self, message: str, details: Optional[str] = None) -> None:
        """Log an info message."""
        self.logger.info(message)
        self._add_to_memory("INFO", message, details)

    def warning(self, message: str, details: Optional[str] = None) -> None:
        """Log a warning message."""
        self.logger.warning(message)
        self._add_to_memory("WARNING", message, details)

    def error(self, message: str, details: Optional[str] = None) -> None:
        """Log an error message."""
        self.logger.error(message)
        self._add_to_memory("ERROR", message, details)

    def success(self, message: str, details: Optional[str] = None) -> None:
        """Log a success message."""
        self.logger.info(f"SUCCESS: {message}")
        self._add_to_memory("SUCCESS", message, details)

    def command(
        self, cmd: List[str], returncode: int, stdout: str, stderr: str
    ) -> None:
        """Log a command execution with its output."""
        cmd_str = " ".join(cmd)
        if returncode == 0:
            self.info(f"Command executed successfully: {cmd_str}")
            if stdout:
                self.debug("Command stdout", stdout)
        else:
            self.error(
                f"Command failed with code {returncode}: {cmd_str}",
                f"STDOUT: {stdout}\nSTDERR: {stderr}",
            )

    def get_logs(self, level: Optional[str] = None, count: int = 100) -> List[LogEntry]:
        """Get the most recent logs, optionally filtered by level."""
        if level:
            filtered = [log for log in self.logs if log.level == level.upper()]
            return list(filtered)[-count:]
        return list(self.logs)[-count:]

    def get_log_file_content(self, max_lines: int = 1000) -> str:
        """Read the log file and return its content, limited to max_lines."""
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        except Exception as e:
            return f"Error reading log file: {e}"


# Initialize the global logger
app_logger = Logger(LOG_FILE, MAX_LOG_ENTRIES)


@dataclass
class CouchDBConfig:
    """Configuration for CouchDB setup."""

    domain: str = DEFAULT_DOMAIN
    port: int = DEFAULT_COUCHDB_PORT
    admin_username: str = "admin"
    admin_password: str = ""
    cookie: str = ""
    setup_complete: bool = False
    nginx_configured: bool = False
    livesync_configured: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CouchDBConfig":
        return cls(**data)


@dataclass
class InstallStatus:
    """Installation status tracking."""

    snapd_installed: bool = False
    couchdb_installed: bool = False
    couchdb_configured: bool = False
    couchdb_running: bool = False
    nginx_installed: bool = False
    nginx_configured: bool = False
    nginx_running: bool = False
    livesync_initialized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstallStatus":
        return cls(**data)


T = TypeVar("T")


# UI Helper Functions
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


async def async_prompt(message: str) -> str:
    """Async-compatible wrapper for Prompt.ask."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: Prompt.ask(message))


async def async_confirm(message: str, default: bool = False) -> bool:
    """Async-compatible wrapper for Confirm.ask."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


def create_header() -> Panel:
    """Create a header panel with the app name."""
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "mini", "digital"]
    font_to_use: str = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]
    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")
    return Panel(
        combined_text,
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print and log an error message."""
    print_message(message, NordColors.RED, "✗")
    app_logger.error(message)


def print_success(message: str) -> None:
    """Print and log a success message."""
    print_message(message, NordColors.GREEN, "✓")
    app_logger.success(message)


def print_warning(message: str) -> None:
    """Print and log a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")
    app_logger.warning(message)


def print_step(message: str) -> None:
    """Print and log a step message."""
    print_message(message, NordColors.FROST_2, "→")
    app_logger.info(message)


def print_section(title: str) -> None:
    """Print a section title."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display a panel with a title and message."""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# Core Functionality - Configuration Management
async def ensure_config_directory() -> None:
    """Ensure the configuration directory exists."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


async def save_config(config: CouchDBConfig) -> bool:
    """Save the configuration to the config file."""
    await ensure_config_directory()
    try:
        # Use async file operations for more consistent async behavior
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: json.dump(config.to_dict(), open(CONFIG_FILE, "w"), indent=2)
        )
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


async def save_status(status: InstallStatus) -> bool:
    """Save the installation status to a file."""
    await ensure_config_directory()
    try:
        status_file = os.path.join(CONFIG_DIR, "status.json")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: json.dump(status.to_dict(), open(status_file, "w"), indent=2)
        )
        return True
    except Exception as e:
        print_error(f"Failed to save status: {e}")
        return False


async def load_config() -> CouchDBConfig:
    """Load the configuration from the config file."""
    try:
        if os.path.exists(CONFIG_FILE):
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, lambda: json.load(open(CONFIG_FILE, "r"))
            )
            return CouchDBConfig.from_dict(data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return CouchDBConfig()


async def load_status() -> InstallStatus:
    """Load the installation status from a file."""
    try:
        status_file = os.path.join(CONFIG_DIR, "status.json")
        if os.path.exists(status_file):
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, lambda: json.load(open(status_file, "r"))
            )
            return InstallStatus.from_dict(data)
    except Exception as e:
        print_error(f"Failed to load status: {e}")
    return InstallStatus()


# Core Functionality - Command Execution and Utils
async def run_command_async(
    cmd: List[str], check_sudo: bool = False
) -> Tuple[int, str, str]:
    """Run a shell command asynchronously.

    Args:
        cmd: Command to run as a list of strings
        check_sudo: Whether to check for sudo privileges first

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        # If sudo is needed, check if we have sudo privileges first
        if check_sudo and "sudo" in cmd[0]:
            print_step("Checking sudo privileges...")

            # Create a process to check if we have sudo access
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "-n",
                "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await proc.communicate()

            if proc.returncode != 0:
                print_warning("Sudo privileges are required for this operation.")
                print_step("You may be prompted for your password.")

        # Run the actual command
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=OPERATION_TIMEOUT
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        return proc.returncode, stdout, stderr
    except asyncio.TimeoutError:
        return (
            1,
            "",
            f"Command timed out after {OPERATION_TIMEOUT} seconds: {' '.join(cmd)}",
        )
    except Exception as e:
        return 1, "", f"Error executing command: {e}"


async def check_command_exists(command: str) -> bool:
    """Check if a command exists on the system."""
    try:
        returncode, _, _ = await run_command_async(["which", command])
        return returncode == 0
    except Exception:
        return False


async def check_service_status(service_name: str) -> Tuple[bool, str]:
    """Check if a systemd service is active."""
    returncode, stdout, stderr = await run_command_async(
        ["systemctl", "is-active", service_name]
    )
    return returncode == 0, stdout.strip()


async def simulate_progress(progress, task_id, steps, delay=0.3):
    """Simulate progress updates for a task."""
    for step, pct in steps:
        await asyncio.sleep(delay)
        progress.update(task_id, description=step, completed=pct)


async def generate_password(length: int = 16) -> str:
    """Generate a secure random password."""
    characters = string.ascii_letters + string.digits + "!@#$%^&*()_-+=<>?"
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: "".join(secrets.choice(characters) for _ in range(length))
    )


async def generate_cookie(length: int = 32) -> str:
    """Generate a secure random cookie for CouchDB."""
    characters = string.ascii_letters + string.digits
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: "".join(secrets.choice(characters) for _ in range(length))
    )


# Core Functionality - Installation Steps
async def check_snapd_installed() -> bool:
    """Check if snapd is installed."""
    exists = await check_command_exists("snap")
    if exists:
        print_success("Snapd is already installed")
    else:
        print_warning("Snapd is not installed")
    return exists


async def install_snapd() -> bool:
    """Install snapd if it's not already installed."""
    print_step("Installing snapd...")

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Installing snapd...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Updating package lists...", 20),
            (f"[{NordColors.FROST_2}]Installing snapd...", 60),
            (f"[{NordColors.FROST_2}]Configuring...", 80),
            (f"[{NordColors.GREEN}]Installation complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Actually install snapd
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "apt", "update", "-y"], check_sudo=True
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to update package lists: {stderr}")
            return False

        returncode, stdout, stderr = await run_command_async(
            ["sudo", "apt", "install", "snapd", "-y"], check_sudo=True
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to install snapd: {stderr}")
            return False

        # Verify installation
        installed = await check_command_exists("snap")
        if installed:
            print_success("Snapd was successfully installed")
            return True
        else:
            print_error("Snapd installation failed")
            return False


async def check_couchdb_installed() -> bool:
    """Check if CouchDB snap is installed."""
    returncode, stdout, stderr = await run_command_async(["snap", "list", "couchdb"])
    if returncode == 0:
        print_success("CouchDB snap is installed")
        return True
    else:
        print_warning("CouchDB snap is not installed")
        return False


async def install_couchdb_snap() -> bool:
    """Install CouchDB via snap."""
    print_step("Installing CouchDB via snap...")

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Installing CouchDB...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Downloading CouchDB snap...", 30),
            (f"[{NordColors.FROST_2}]Installing...", 70),
            (f"[{NordColors.GREEN}]Installation complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Actually install CouchDB
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "snap", "install", "couchdb"], check_sudo=True
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to install CouchDB snap: {stderr}")
            return False

        # Verify installation
        installed = await check_couchdb_installed()
        if installed:
            print_success("CouchDB snap was successfully installed")
            return True
        else:
            print_error("CouchDB snap installation failed")
            return False


async def configure_couchdb(config: CouchDBConfig) -> bool:
    """Configure CouchDB admin and cookie settings."""
    print_step("Configuring CouchDB...")

    # Check if we need to generate credentials
    if not config.admin_password:
        config.admin_password = await generate_password()
        print_success(f"Generated admin password: {config.admin_password}")

    if not config.cookie:
        config.cookie = await generate_cookie()
        print_success(f"Generated CouchDB cookie: {config.cookie}")

    # Save the config
    await save_config(config)

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Configuring CouchDB...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Setting admin password...", 40),
            (f"[{NordColors.FROST_2}]Setting cookie...", 70),
            (f"[{NordColors.FROST_2}]Restarting CouchDB...", 90),
            (f"[{NordColors.GREEN}]Configuration complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Set admin password
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "snap", "set", "couchdb", f"admin={config.admin_password}"],
            check_sudo=True,
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to set admin password: {stderr}")
            return False

        # Set cookie
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "snap", "set", "couchdb", f"setcookie={config.cookie}"],
            check_sudo=True,
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to set cookie: {stderr}")
            return False

        # Restart CouchDB
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "snap", "restart", "couchdb"], check_sudo=True
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to restart CouchDB: {stderr}")
            return False

        # Wait a moment for CouchDB to start
        await asyncio.sleep(3)

        # Verify CouchDB is running
        running, status = await check_service_status("snap.couchdb.couchdb")
        if running:
            print_success("CouchDB is now running")
            return True
        else:
            print_error(f"CouchDB is not running: {status}")
            return False


async def check_nginx_installed() -> bool:
    """Check if Nginx is installed."""
    exists = await check_command_exists("nginx")
    if exists:
        print_success("Nginx is already installed")
    else:
        print_warning("Nginx is not installed")
    return exists


async def install_nginx() -> bool:
    """Install Nginx if it's not already installed."""
    print_step("Installing Nginx...")

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Installing Nginx...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Updating package lists...", 20),
            (f"[{NordColors.FROST_2}]Installing Nginx...", 60),
            (f"[{NordColors.FROST_2}]Configuring...", 80),
            (f"[{NordColors.GREEN}]Installation complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Actually install Nginx
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "apt", "update", "-y"], check_sudo=True
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to update package lists: {stderr}")
            return False

        returncode, stdout, stderr = await run_command_async(
            ["sudo", "apt", "install", "nginx", "-y"], check_sudo=True
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to install Nginx: {stderr}")
            return False

        # Verify installation
        installed = await check_command_exists("nginx")
        if installed:
            print_success("Nginx was successfully installed")
            return True
        else:
            print_error("Nginx installation failed")
            return False


async def configure_nginx(config: CouchDBConfig) -> bool:
    """Configure Nginx for CouchDB access."""
    print_step(f"Configuring Nginx for domain: {config.domain}...")

    # Prepare Nginx config content
    nginx_config = f"""server {{
    listen 80;
    server_name {config.domain};

    location / {{
        proxy_pass http://localhost:{config.port};
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS configuration - important for Obsidian LiveSync
        if ($request_method = 'OPTIONS') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }}
        if ($request_method = 'POST') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'GET') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'PUT') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'DELETE') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
    }}
}}
"""

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Configuring Nginx...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Creating Nginx configuration...", 30),
            (f"[{NordColors.FROST_2}]Enabling site...", 60),
            (f"[{NordColors.FROST_2}]Restarting Nginx...", 80),
            (f"[{NordColors.GREEN}]Configuration complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Write Nginx configuration file
        config_filename = f"{config.domain}.conf"
        config_path = os.path.join(NGINX_CONFIG_PATH, config_filename)

        # Create temporary file
        temp_file = f"/tmp/{config_filename}"
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, lambda: open(temp_file, "w").write(nginx_config)
            )
        except Exception as e:
            await progress_task
            print_error(f"Failed to create temporary configuration file: {e}")
            return False

        # Move file to Nginx directory
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "mv", temp_file, config_path], check_sudo=True
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to create Nginx configuration: {stderr}")
            return False

        # Enable the site
        symlink_path = os.path.join(NGINX_ENABLED_PATH, config_filename)
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "ln", "-sf", config_path, symlink_path], check_sudo=True
        )

        if returncode != 0:
            await progress_task
            print_error(f"Failed to enable Nginx site: {stderr}")
            return False

        # Test Nginx configuration
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "nginx", "-t"], check_sudo=True
        )

        if returncode != 0:
            await progress_task
            print_error(f"Nginx configuration is invalid: {stderr}")
            return False

        # Restart Nginx
        returncode, stdout, stderr = await run_command_async(
            ["sudo", "systemctl", "restart", "nginx"], check_sudo=True
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to restart Nginx: {stderr}")
            return False

        # Verify Nginx is running
        running, status = await check_service_status("nginx")
        if running:
            print_success("Nginx is now running with the new configuration")
            return True
        else:
            print_error(f"Nginx is not running: {status}")
            return False


async def run_livesync_init() -> bool:
    """Run the LiveSync initialization script."""
    print_step("Initializing Obsidian LiveSync...")

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
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Initializing LiveSync...", total=100
        )

        steps = [
            (f"[{NordColors.FROST_2}]Downloading initialization script...", 30),
            (f"[{NordColors.FROST_2}]Running script...", 70),
            (f"[{NordColors.GREEN}]Initialization complete.", 100),
        ]

        # Run progress simulation in background
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))

        # Run the LiveSync initialization script
        returncode, stdout, stderr = await run_command_async(
            [
                "bash",
                "-c",
                "curl -s https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/main/utils/couchdb/couchdb-init.sh | bash",
            ]
        )

        # Wait for progress visualization to complete
        await progress_task

        if returncode != 0:
            print_error(f"Failed to initialize LiveSync: {stderr}")
            return False

        print_success("Obsidian LiveSync has been initialized")
        return True


async def check_couchdb_access(config: CouchDBConfig) -> bool:
    """Check if CouchDB is accessible."""
    print_step("Checking CouchDB access...")

    url = f"http://localhost:{config.port}/"
    returncode, stdout, stderr = await run_command_async(["curl", "-s", url])

    if returncode != 0 or "couchdb" not in stdout.lower():
        print_error(f"CouchDB is not accessible at {url}")
        return False

    print_success(f"CouchDB is accessible at {url}")
    return True


async def display_summary(config: CouchDBConfig, status: InstallStatus) -> None:
    """Display a summary of the installation."""
    clear_screen()
    console.print(create_header())

    print_section("Installation Summary")

    # Create a status table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        padding=(0, 2),
    )

    table.add_column("Component", style=f"bold {NordColors.FROST_1}")
    table.add_column("Status", style=f"bold {NordColors.SNOW_STORM_1}")

    # Add rows
    table.add_row(
        "Snapd",
        Text("✓ Installed", style=NordColors.GREEN)
        if status.snapd_installed
        else Text("✗ Not installed", style=NordColors.RED),
    )

    table.add_row(
        "CouchDB",
        Text("✓ Installed", style=NordColors.GREEN)
        if status.couchdb_installed
        else Text("✗ Not installed", style=NordColors.RED),
    )

    table.add_row(
        "CouchDB Configuration",
        Text("✓ Configured", style=NordColors.GREEN)
        if status.couchdb_configured
        else Text("✗ Not configured", style=NordColors.RED),
    )

    table.add_row(
        "Nginx",
        Text("✓ Installed", style=NordColors.GREEN)
        if status.nginx_installed
        else Text("✗ Not installed", style=NordColors.RED),
    )

    table.add_row(
        "Nginx Configuration",
        Text("✓ Configured", style=NordColors.GREEN)
        if status.nginx_configured
        else Text("✗ Not configured", style=NordColors.RED),
    )

    table.add_row(
        "LiveSync",
        Text("✓ Initialized", style=NordColors.GREEN)
        if status.livesync_initialized
        else Text("✗ Not initialized", style=NordColors.RED),
    )

    console.print(table)
    console.print()

    # Show connection details
    if status.couchdb_configured and status.nginx_configured:
        print_section("Connection Details")

        details_table = Table(show_header=False, box=None, padding=(0, 3))
        details_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        details_table.add_column("Value", style=f"{NordColors.SNOW_STORM_2}")

        details_table.add_row("CouchDB URL", f"http://{config.domain}")
        details_table.add_row("Admin Username", config.admin_username)
        details_table.add_row("Admin Password", config.admin_password)
        details_table.add_row("Local URL", f"http://localhost:{config.port}")

        console.print(details_table)
        console.print()

        print_section("Next Steps")
        print_step("Set up your DNS to point your domain to this server")
        print_step("Install the Obsidian LiveSync plugin in your Obsidian vault")
        print_step(f"Use the following URL in LiveSync: http://{config.domain}")
        print_step(
            f"Use admin credentials: {config.admin_username}/{config.admin_password}"
        )
        console.print()

        print_warning("Important: Keep these credentials safe and secure!")
    else:
        print_section("Next Steps")
        print_step("Complete the installation process to get connection details")


# Core Application Functions
async def view_logs_async() -> None:
    """Display the application logs with filtering and paging."""
    logs_viewed = False
    current_filter = None
    page_size = 20
    current_page = 0

    while True:
        clear_screen()
        console.print(create_header())

        print_section("Log Viewer")

        # Get the logs with current filter
        logs = app_logger.get_logs(level=current_filter)
        total_pages = max(1, (len(logs) + page_size - 1) // page_size)
        current_page = min(current_page, total_pages - 1)

        # Display filter info
        if current_filter:
            print_message(f"Filter: {current_filter.upper()}", NordColors.YELLOW)
        else:
            print_message("Showing all logs", NordColors.FROST_2)

        print_message(f"Page {current_page + 1} of {total_pages}", NordColors.FROST_3)
        console.print()

        # Display the logs for the current page
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(logs))

        if logs:
            for log in logs[start_idx:end_idx]:
                level_style = log.get_color()
                timestamp = log.formatted_time()
                console.print(
                    f"[{NordColors.FROST_4}]{timestamp}[/] [{level_style}][{log.level}][/] {log.message}"
                )

                if log.details:
                    # Split details into lines and indent them
                    details_lines = log.details.split("\n")
                    for line in details_lines:
                        if line.strip():
                            console.print(f"  [{NordColors.POLAR_NIGHT_4}]{line}[/]")
        else:
            print_message("No logs found", NordColors.YELLOW)

        console.print()
        print_section("Commands")
        console.print(f"[bold {NordColors.FROST_2}]n[/]: Next page")
        console.print(f"[bold {NordColors.FROST_2}]p[/]: Previous page")
        console.print(f"[bold {NordColors.FROST_2}]f[/]: Filter logs")
        console.print(f"[bold {NordColors.FROST_2}]c[/]: Clear filter")
        console.print(f"[bold {NordColors.FROST_2}]s[/]: Save logs to file")
        console.print(f"[bold {NordColors.FROST_2}]q[/]: Return to main menu")

        choice = await async_prompt("Enter command")
        choice = choice.lower()

        if choice == "q":
            break
        elif choice == "n":
            if current_page < total_pages - 1:
                current_page += 1
        elif choice == "p":
            if current_page > 0:
                current_page -= 1
        elif choice == "f":
            filter_choice = await async_prompt(
                "Filter by (i)nfo, (e)rror, (w)arning, (s)uccess, (d)ebug"
            )
            if filter_choice:
                filter_type = None
                if filter_choice.lower() in ("i", "info"):
                    filter_type = "INFO"
                elif filter_choice.lower() in ("e", "error"):
                    filter_type = "ERROR"
                elif filter_choice.lower() in ("w", "warning"):
                    filter_type = "WARNING"
                elif filter_choice.lower() in ("s", "success"):
                    filter_type = "SUCCESS"
                elif filter_choice.lower() in ("d", "debug"):
                    filter_type = "DEBUG"

                if filter_type:
                    current_filter = filter_type
                    current_page = 0
                    print_success(f"Filtering logs by {filter_type}")
                else:
                    print_error("Invalid filter type")
                    await async_prompt("Press Enter to continue")
        elif choice == "c":
            current_filter = None
            current_page = 0
        elif choice == "s":
            save_path = await async_prompt(
                "Enter path to save logs (default: ~/couchdb_installer_logs.txt)"
            )
            if not save_path:
                save_path = os.path.expanduser("~/couchdb_installer_logs.txt")

            try:
                log_content = app_logger.get_log_file_content()
                with open(save_path, "w") as f:
                    f.write(log_content)
                print_success(f"Logs saved to {save_path}")
            except Exception as e:
                print_error(f"Failed to save logs: {e}")

            await async_prompt("Press Enter to continue")

        logs_viewed = True

    if logs_viewed:
        print_success("Returning to main menu")
        await async_prompt("Press Enter to continue")


async def troubleshoot_async(config: CouchDBConfig, status: InstallStatus) -> None:
    """Provide troubleshooting steps for common issues."""
    clear_screen()
    console.print(create_header())

    print_section("Troubleshooting Assistant")

    # Check which components failed
    failed_components = []

    if not status.snapd_installed:
        failed_components.append("Snapd")
    if not status.couchdb_installed:
        failed_components.append("CouchDB")
    if not status.couchdb_configured:
        failed_components.append("CouchDB Configuration")
    if not status.nginx_installed:
        failed_components.append("Nginx")
    if not status.nginx_configured:
        failed_components.append("Nginx Configuration")
    if not status.livesync_initialized:
        failed_components.append("LiveSync")

    if not failed_components:
        print_success("All components appear to be installed and configured correctly!")
        print_step(
            "If you're still experiencing issues, please check the logs for more details."
        )
        await async_prompt("Press Enter to return to the main menu")
        return

    # Display failed components
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        padding=(0, 2),
    )

    table.add_column("Failed Component", style=f"bold {NordColors.RED}")
    table.add_column("Troubleshooting Steps", style=f"{NordColors.SNOW_STORM_1}")

    # Add rows with troubleshooting steps
    for component in failed_components:
        if component == "Snapd":
            table.add_row(
                "Snapd",
                "1. Check if your system supports snap\n"
                "2. Try installing manually: sudo apt update && sudo apt install snapd\n"
                "3. Check if snapd service is running: systemctl status snapd",
            )

        elif component == "CouchDB":
            table.add_row(
                "CouchDB",
                "1. Try installing manually: sudo snap install couchdb\n"
                "2. Check if the CouchDB snap is available: snap find couchdb\n"
                "3. Verify snap is working: snap list",
            )

        elif component == "CouchDB Configuration":
            table.add_row(
                "CouchDB Configuration",
                "1. Check CouchDB status: sudo snap services couchdb\n"
                "2. Check logs: sudo snap logs couchdb -f\n"
                "3. Try manual config:\n   sudo snap set couchdb admin=password\n   sudo snap set couchdb setcookie=cookie\n   sudo snap restart couchdb\n"
                "4. Verify CouchDB is running: curl http://localhost:5984",
            )

        elif component == "Nginx":
            table.add_row(
                "Nginx",
                "1. Try installing manually: sudo apt update && sudo apt install nginx\n"
                "2. Check if any other web server is using port 80\n"
                "3. Check nginx status: systemctl status nginx",
            )

        elif component == "Nginx Configuration":
            table.add_row(
                "Nginx Configuration",
                "1. Check nginx configuration: sudo nginx -t\n"
                "2. Check nginx error logs: sudo cat /var/log/nginx/error.log\n"
                "3. Ensure nginx sites-enabled directory exists\n"
                "4. Verify permissions on config files",
            )

        elif component == "LiveSync":
            table.add_row(
                "LiveSync",
                "1. Check if CouchDB is running: curl http://localhost:5984\n"
                "2. Try running script manually:\n   curl -s https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/main/utils/couchdb/couchdb-init.sh | bash\n"
                "3. Verify internet connection and GitHub access\n"
                "4. Check if the required databases exist in CouchDB",
            )

    console.print(table)
    console.print()

    # Offer automatic repair for specific components
    print_section("Automatic Repair")

    if "CouchDB Configuration" in failed_components:
        proceed = await async_confirm(
            "Attempt to automatically repair CouchDB configuration?", default=True
        )
        if proceed:
            print_step("Attempting to repair CouchDB configuration...")

            # Perform CouchDB configuration repair
            success = await configure_couchdb(config)

            if success:
                print_success("CouchDB configuration repaired successfully!")
                status.couchdb_configured = True
                await save_status(status)
            else:
                print_error("Failed to repair CouchDB configuration")

    if "LiveSync" in failed_components:
        proceed = await async_confirm(
            "Attempt to automatically initialize LiveSync?", default=True
        )
        if proceed:
            print_step("Attempting to initialize LiveSync...")

            # Perform LiveSync initialization repair
            success = await run_livesync_init()

            if success:
                print_success("LiveSync initialized successfully!")
                status.livesync_initialized = True
                await save_status(status)
            else:
                print_error("Failed to initialize LiveSync")

    print_section("Diagnostics")

    # Offer to collect diagnostic information
    proceed = await async_confirm(
        "Run diagnostics to gather more information?", default=True
    )
    if proceed:
        # Create a diagnostic report
        print_step("Running diagnostics...")

        # Check system information
        returncode, stdout, stderr = await run_command_async(["uname", "-a"])
        system_info = stdout if returncode == 0 else "Unknown"

        # Check free disk space
        returncode, stdout, stderr = await run_command_async(["df", "-h", "/var"])
        disk_space = stdout if returncode == 0 else "Unknown"

        # Check CouchDB status
        returncode, stdout, stderr = await run_command_async(
            ["curl", "-s", f"http://localhost:{config.port}"]
        )
        couchdb_response = stdout if returncode == 0 else "Not responding"

        # Display diagnostic info
        print_section("Diagnostic Results")

        diagnostics_table = Table(show_header=False, box=None, padding=(0, 3))
        diagnostics_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        diagnostics_table.add_column("Value", style=f"{NordColors.SNOW_STORM_2}")

        diagnostics_table.add_row("System Info", system_info)
        diagnostics_table.add_row("Disk Space", disk_space)
        diagnostics_table.add_row("CouchDB Response", couchdb_response)

        console.print(diagnostics_table)

    print_section("Next Steps")
    print_step("Check the application logs for detailed error messages")
    print_step("Consider re-running the installer for failed components")
    print_step("Consult the CouchDB and Nginx documentation for manual configuration")

    await async_prompt("Press Enter to return to the main menu")


async def install_manager_async() -> None:
    """Main installer function that walks through all installation steps."""
    # Load or initialize configuration and status
    config = await load_config()
    status = await load_status()

    clear_screen()
    console.print(create_header())

    display_panel(
        "CouchDB Installer for Obsidian LiveSync",
        "This wizard will guide you through installing and configuring CouchDB with Nginx for Obsidian LiveSync",
        NordColors.FROST_3,
    )

    # Ask for domain if not configured
    if not config.domain or config.domain == DEFAULT_DOMAIN:
        config.domain = await async_prompt(
            f"[bold {NordColors.FROST_2}]Enter your domain for Obsidian LiveSync[/] (default: {DEFAULT_DOMAIN})"
        )
        if not config.domain:
            config.domain = DEFAULT_DOMAIN
        await save_config(config)

    # Step 1: Check and install snapd if needed
    print_section("Step 1: Setting up snapd")
    if not status.snapd_installed:
        status.snapd_installed = await check_snapd_installed()
        if not status.snapd_installed:
            proceed = await async_confirm("Install snapd?", default=True)
            if proceed:
                status.snapd_installed = await install_snapd()
                await save_status(status)
            else:
                print_warning("Snapd installation skipped")
                await async_prompt("Press Enter to continue")
                return

    # Step 2: Check and install CouchDB if needed
    print_section("Step 2: Installing CouchDB")
    if not status.couchdb_installed:
        status.couchdb_installed = await check_couchdb_installed()
        if not status.couchdb_installed:
            proceed = await async_confirm("Install CouchDB via snap?", default=True)
            if proceed:
                status.couchdb_installed = await install_couchdb_snap()
                await save_status(status)
            else:
                print_warning("CouchDB installation skipped")
                await async_prompt("Press Enter to continue")
                return

    # Step 3: Configure CouchDB
    print_section("Step 3: Configuring CouchDB")
    if not status.couchdb_configured:
        proceed = await async_confirm(
            "Configure CouchDB with admin credentials?", default=True
        )
        if proceed:
            status.couchdb_configured = await configure_couchdb(config)
            await save_status(status)
        else:
            print_warning("CouchDB configuration skipped")
            await async_prompt("Press Enter to continue")
            return

    # Step 4: Check CouchDB access
    print_section("Step 4: Verifying CouchDB")
    couchdb_accessible = await check_couchdb_access(config)
    if not couchdb_accessible:
        print_warning(
            "CouchDB is not accessible. Please check the installation and configuration."
        )
        await async_prompt("Press Enter to continue")
        return

    # Step 5: Check and install Nginx if needed
    print_section("Step 5: Setting up Nginx")
    if not status.nginx_installed:
        status.nginx_installed = await check_nginx_installed()
        if not status.nginx_installed:
            proceed = await async_confirm("Install Nginx?", default=True)
            if proceed:
                status.nginx_installed = await install_nginx()
                await save_status(status)
            else:
                print_warning("Nginx installation skipped")
                await async_prompt("Press Enter to continue")
                return

    # Step 6: Configure Nginx
    print_section("Step 6: Configuring Nginx")
    if not status.nginx_configured:
        proceed = await async_confirm(
            f"Configure Nginx for domain: {config.domain}?", default=True
        )
        if proceed:
            status.nginx_configured = await configure_nginx(config)
            await save_status(status)
        else:
            print_warning("Nginx configuration skipped")
            await async_prompt("Press Enter to continue")
            return

    # Step 7: Initialize LiveSync
    print_section("Step 7: Initializing Obsidian LiveSync")
    if not status.livesync_initialized:
        proceed = await async_confirm("Initialize Obsidian LiveSync?", default=True)
        if proceed:
            status.livesync_initialized = await run_livesync_init()
            await save_status(status)
        else:
            print_warning("LiveSync initialization skipped")
            await async_prompt("Press Enter to continue")
            return

    # Display summary
    await display_summary(config, status)

    # Final message
    if (
        status.couchdb_installed
        and status.couchdb_configured
        and status.nginx_configured
    ):
        print_success("Installation completed successfully!")
    else:
        print_warning("Installation completed with some components skipped or failed.")

    await async_prompt("Press Enter to exit")


async def main_menu_async() -> None:
    """Main menu to select actions."""
    config = await load_config()
    status = await load_status()

    while True:
        clear_screen()
        console.print(create_header())

        print_section("CouchDB Installer Menu")

        console.print(
            f"[bold {NordColors.FROST_2}]1. [/][{NordColors.SNOW_STORM_2}]Run Installation Wizard[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]2. [/][{NordColors.SNOW_STORM_2}]View Installation Status[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]3. [/][{NordColors.SNOW_STORM_2}]Change Domain Configuration[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]4. [/][{NordColors.SNOW_STORM_2}]View Logs[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]5. [/][{NordColors.SNOW_STORM_2}]Troubleshooting[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]q. [/][{NordColors.SNOW_STORM_2}]Quit[/]"
        )

        console.print()
        choice = await async_prompt("Enter your choice")

        if choice.lower() in ("q", "quit", "exit"):
            break
        elif choice == "1":
            await install_manager_async()
        elif choice == "2":
            await display_summary(config, status)
            await async_prompt("Press Enter to return to the menu")
        elif choice == "3":
            new_domain = await async_prompt(
                f"[bold {NordColors.FROST_2}]Enter new domain[/] (current: {config.domain})"
            )
            if new_domain:
                config.domain = new_domain
                await save_config(config)
                print_success(f"Domain updated to {config.domain}")

                # Ask if user wants to reconfigure Nginx
                if status.nginx_configured:
                    reconfigure = await async_confirm(
                        "Reconfigure Nginx with new domain?", default=True
                    )
                    if reconfigure:
                        status.nginx_configured = await configure_nginx(config)
                        await save_status(status)

            await async_prompt("Press Enter to return to the menu")
        elif choice == "4":
            await view_logs_async()
        elif choice == "5":
            await troubleshoot_async(config, status)
        else:
            print_error(f"Invalid choice: {choice}")
            await async_prompt("Press Enter to continue")


async def async_cleanup() -> None:
    """Clean up resources."""
    pass  # Nothing specific to clean up


async def signal_handler_async(sig: int, frame: Any) -> None:
    """Handle signals in an async-friendly way."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current running loop instead of creating a new one
    loop = asyncio.get_running_loop()

    # Cancel all tasks except the current one
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()

    # Clean up resources
    await async_cleanup()

    # Stop the loop instead of exiting directly
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers that work with the main event loop."""
    # Use asyncio's built-in signal handling
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def proper_shutdown_async():
    """Clean up resources at exit."""
    try:
        # Try to get the current running loop, but don't fail if there isn't one
        try:
            loop = asyncio.get_running_loop()
            tasks = [
                t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()
            ]

            # Cancel all tasks
            for task in tasks:
                task.cancel()

            # Wait for all tasks to complete cancellation with a timeout
            if tasks:
                await asyncio.wait(tasks, timeout=2.0)

        except RuntimeError:
            # No running event loop
            pass

    except Exception as e:
        print_error(f"Error during async shutdown: {e}")


def proper_shutdown():
    """Synchronous wrapper for the async shutdown function."""
    try:
        # Check if there's a running loop first
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If a loop is already running, we can't run a new one
                # Just log and return
                print_warning("Event loop already running during shutdown")
                return
        except RuntimeError:
            # No event loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async cleanup
        loop.run_until_complete(proper_shutdown_async())
        loop.close()
    except Exception as e:
        print_error(f"Error during synchronous shutdown: {e}")


async def main_async() -> None:
    """Main async entry point."""
    try:
        # Initialize stuff
        await ensure_config_directory()

        # Run the main menu
        await main_menu_async()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    """Main entry point of the application."""
    try:
        # Create and get a reference to the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers with the specific loop
        setup_signal_handlers(loop)

        # Register shutdown handler
        atexit.register(proper_shutdown)

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
