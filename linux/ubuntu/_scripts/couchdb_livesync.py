#!/usr/bin/env python3
"""
CouchDB Installer for Obsidian LiveSync

This script installs and configures CouchDB (via snap) along with Nginx,
configures the CouchDB admin user and cookie, and initializes Obsidian LiveSync.
It provides an interactive CLI using Rich for colored output and progress bars.

Refactored and improved version:
  - Uses pathlib for file paths.
  - Consolidates common file operations with context managers.
  - Improves error reporting and logging.
  - Fixes LiveSync hostname handling: if the domain is still the default,
    it uses the machine’s hostname (via socket.gethostname()).
  - Cleaner async structure and signal handling.
"""

import os
import sys
import signal
import json
import time
import shutil
import socket
import asyncio
import atexit
import re
import getpass
import secrets
import string
import logging
import datetime
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

# Third-party libraries
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

# =============================================================================
# Configuration and Constants
# =============================================================================

APP_NAME: str = "couchdb installer"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER", "user")
OPERATION_TIMEOUT: int = 60  # seconds
DEFAULT_COUCHDB_PORT: int = 5984
DEFAULT_DOMAIN: str = "obsidian-livesync.example.com"
RETRY_COUNT: int = 3
RETRY_DELAY: int = 3

# Directories and file paths (using pathlib)
CONFIG_DIR: Path = Path.home() / ".config" / "couchdb_installer"
CONFIG_FILE: Path = CONFIG_DIR / "config.json"
STATUS_FILE: Path = CONFIG_DIR / "status.json"
LOG_FILE: Path = CONFIG_DIR / "couchdb_installer.log"
NGINX_CONFIG_PATH: Path = Path("/etc/nginx/sites-available")
NGINX_ENABLED_PATH: Path = Path("/etc/nginx/sites-enabled")
MAX_LOG_ENTRIES: int = 10000

T = TypeVar("T")

# =============================================================================
# Color Palette
# =============================================================================


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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# =============================================================================
# Logging
# =============================================================================


@dataclass
class LogEntry:
    timestamp: float
    level: str
    message: str
    details: Optional[str] = None

    def formatted_time(self) -> str:
        return datetime.datetime.fromtimestamp(self.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_color(self) -> str:
        mapping = {
            "ERROR": NordColors.RED,
            "WARNING": NordColors.YELLOW,
            "SUCCESS": NordColors.GREEN,
            "DEBUG": NordColors.PURPLE,
        }
        return mapping.get(self.level, NordColors.FROST_2)


class Logger:
    """Custom logger for console, file, and in-memory storage."""

    def __init__(self, log_file: Path, max_entries: int = 1000) -> None:
        self.log_file = log_file
        self.max_entries = max_entries
        self.logs = deque(maxlen=max_entries)
        os.makedirs(self.log_file.parent, exist_ok=True)

        logging.basicConfig(
            filename=str(log_file),
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        self.console_handler.setFormatter(formatter)
        self.logger = logging.getLogger("couchdb_installer")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            self.logger.addHandler(self.console_handler)

    def _add_to_memory(
        self, level: str, message: str, details: Optional[str] = None
    ) -> None:
        entry = LogEntry(
            timestamp=time.time(), level=level, message=message, details=details
        )
        self.logs.append(entry)

    def debug(self, message: str, details: Optional[str] = None) -> None:
        self.logger.debug(message)
        self._add_to_memory("DEBUG", message, details)

    def info(self, message: str, details: Optional[str] = None) -> None:
        self.logger.info(message)
        self._add_to_memory("INFO", message, details)

    def warning(self, message: str, details: Optional[str] = None) -> None:
        self.logger.warning(message)
        self._add_to_memory("WARNING", message, details)

    def error(self, message: str, details: Optional[str] = None) -> None:
        self.logger.error(message)
        self._add_to_memory("ERROR", message, details)

    def success(self, message: str, details: Optional[str] = None) -> None:
        self.logger.info(f"SUCCESS: {message}")
        self._add_to_memory("SUCCESS", message, details)

    def command(
        self, cmd: List[str], returncode: int, stdout: str, stderr: str
    ) -> None:
        cmd_str = " ".join(cmd)
        if returncode == 0:
            self.info(f"Command executed successfully: {cmd_str}")
            if stdout:
                self.debug("Command stdout", stdout)
        else:
            self.error(
                f"Command failed ({returncode}): {cmd_str}",
                f"STDOUT: {stdout}\nSTDERR: {stderr}",
            )

    def get_logs(self, level: Optional[str] = None, count: int = 100) -> List[LogEntry]:
        logs = [
            log for log in self.logs if (level is None or log.level == level.upper())
        ]
        return logs[-count:]

    def get_log_file_content(self, max_lines: int = 1000) -> str:
        try:
            with self.log_file.open("r") as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        except Exception as e:
            return f"Error reading log file: {e}"


# Global logger instance
app_logger = Logger(LOG_FILE, MAX_LOG_ENTRIES)

# =============================================================================
# Data Classes for Configuration and Status
# =============================================================================


@dataclass
class CouchDBConfig:
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


# =============================================================================
# UI Helper Functions
# =============================================================================


def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts = ["slant", "small", "mini", "digital"]
    font_to_use = (
        fonts[0] if term_width >= 60 else (fonts[1] if term_width >= 40 else fonts[2])
    )
    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        combined_text.append(Text(line, style=f"bold {colors[i % len(colors)]}"))
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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")
    app_logger.error(message)


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")
    app_logger.success(message)


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")
    app_logger.warning(message)


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")
    app_logger.info(message)


def print_section(title: str) -> None:
    console.print("\n")
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message, title=title, border_style=style, padding=(1, 2), box=box.ROUNDED
    )
    console.print(panel)


async def async_prompt(message: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: Prompt.ask(message))


async def async_confirm(message: str, default: bool = False) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


# =============================================================================
# Configuration and Status File Management
# =============================================================================


async def ensure_config_directory() -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


async def save_config(config: CouchDBConfig) -> bool:
    await ensure_config_directory()
    try:
        with CONFIG_FILE.open("w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


async def load_config() -> CouchDBConfig:
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r") as f:
                data = json.load(f)
            return CouchDBConfig.from_dict(data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return CouchDBConfig()


async def save_status(status: InstallStatus) -> bool:
    await ensure_config_directory()
    try:
        with STATUS_FILE.open("w") as f:
            json.dump(status.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save status: {e}")
        return False


async def load_status() -> InstallStatus:
    try:
        if STATUS_FILE.exists():
            with STATUS_FILE.open("r") as f:
                data = json.load(f)
            return InstallStatus.from_dict(data)
    except Exception as e:
        print_error(f"Failed to load status: {e}")
    return InstallStatus()


# =============================================================================
# Command Execution Utilities
# =============================================================================


async def run_command_async(
    cmd: List[str], check_sudo: bool = False
) -> Tuple[int, str, str]:
    """Run a command asynchronously and return (returncode, stdout, stderr)."""
    try:
        if check_sudo and "sudo" in cmd[0]:
            print_step("Checking sudo privileges...")
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
    return (await run_command_async(["which", command]))[0] == 0


async def check_service_status(service_name: str) -> Tuple[bool, str]:
    # For snap-based services, try a different check
    if service_name.startswith("snap."):
        ret, stdout, _ = await run_command_async(["snap", "services", service_name])
        if ret == 0 and "active" in stdout:
            return True, "active"
        # Special check for CouchDB via curl
        if "couchdb" in service_name:
            ret, stdout, _ = await run_command_async(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-I",
                    "-w",
                    "%{http_code}",
                    "http://localhost:5984/",
                ]
            )
            if ret == 0 or "200" in stdout:
                app_logger.info("CouchDB is responding on port 5984")
                return True, "responding on port"
    ret, stdout, _ = await run_command_async(["systemctl", "is-active", service_name])
    return ret == 0, stdout.strip()


async def simulate_progress(
    progress, task_id, steps: List[Tuple[str, int]], delay: float = 0.3
) -> None:
    for step, pct in steps:
        await asyncio.sleep(delay)
        progress.update(task_id, description=step, completed=pct)


async def generate_password(length: int = 16) -> str:
    characters = string.ascii_letters + string.digits + "!@#$%^&*()_-+=<>?"
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: "".join(secrets.choice(characters) for _ in range(length))
    )


async def generate_cookie(length: int = 32) -> str:
    characters = string.ascii_letters + string.digits
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: "".join(secrets.choice(characters) for _ in range(length))
    )


# =============================================================================
# Installation Steps
# =============================================================================


async def check_snapd_installed() -> bool:
    exists = await check_command_exists("snap")
    if exists:
        print_success("Snapd is already installed")
    else:
        print_warning("Snapd is not installed")
    return exists


async def install_snapd() -> bool:
    print_step("Installing snapd...")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            "[{0}]Installing snapd...".format(NordColors.FROST_2), total=100
        )
        steps = [
            (f"[{NordColors.FROST_2}]Updating package lists...", 20),
            (f"[{NordColors.FROST_2}]Installing snapd...", 60),
            (f"[{NordColors.FROST_2}]Configuring...", 80),
            (f"[{NordColors.GREEN}]Installation complete.", 100),
        ]
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        ret, _, stderr = await run_command_async(
            ["sudo", "apt", "update", "-y"], check_sudo=True
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to update package lists: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "apt", "install", "snapd", "-y"], check_sudo=True
        )
        await progress_task
        if ret != 0:
            print_error(f"Failed to install snapd: {stderr}")
            return False
        if await check_command_exists("snap"):
            print_success("Snapd was successfully installed")
            return True
        else:
            print_error("Snapd installation failed")
            return False


async def check_couchdb_installed() -> bool:
    ret, _, _ = await run_command_async(["snap", "list", "couchdb"])
    if ret == 0:
        print_success("CouchDB snap is installed")
        return True
    else:
        print_warning("CouchDB snap is not installed")
        return False


async def install_couchdb_snap() -> bool:
    print_step("Installing CouchDB via snap...")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
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
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        ret, _, stderr = await run_command_async(
            ["sudo", "snap", "install", "couchdb"], check_sudo=True
        )
        await progress_task
        if ret != 0:
            print_error(f"Failed to install CouchDB snap: {stderr}")
            return False
        if await check_couchdb_installed():
            print_success("CouchDB snap was successfully installed")
            return True
        else:
            print_error("CouchDB snap installation failed")
            return False


async def configure_couchdb(config: CouchDBConfig) -> bool:
    print_step("Configuring CouchDB...")
    if not config.admin_password:
        config.admin_password = await generate_password()
        print_success(f"Generated admin password: {config.admin_password}")
    if not config.cookie:
        config.cookie = await generate_cookie()
        print_success(f"Generated CouchDB cookie: {config.cookie}")
    await save_config(config)
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
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
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        ret, _, stderr = await run_command_async(
            ["sudo", "snap", "set", "couchdb", f"admin={config.admin_password}"],
            check_sudo=True,
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to set admin password: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "snap", "set", "couchdb", f"setcookie={config.cookie}"],
            check_sudo=True,
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to set cookie: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "snap", "restart", "couchdb"], check_sudo=True
        )
        await progress_task
        if ret != 0:
            print_error(f"Failed to restart CouchDB: {stderr}")
            return False
        await asyncio.sleep(3)
        running, status_str = await check_service_status("snap.couchdb.couchdb")
        if running:
            print_success("CouchDB is now running")
            return True
        else:
            print_error(f"CouchDB is not running: {status_str}")
            return False


async def check_nginx_installed() -> bool:
    exists = await check_command_exists("nginx")
    if exists:
        print_success("Nginx is already installed")
    else:
        print_warning("Nginx is not installed")
    return exists


async def install_nginx() -> bool:
    print_step("Installing Nginx...")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
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
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        ret, _, stderr = await run_command_async(
            ["sudo", "apt", "update", "-y"], check_sudo=True
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to update package lists: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "apt", "install", "nginx", "-y"], check_sudo=True
        )
        await progress_task
        if ret != 0:
            print_error(f"Failed to install Nginx: {stderr}")
            return False
        if await check_nginx_installed():
            print_success("Nginx was successfully installed")
            return True
        else:
            print_error("Nginx installation failed")
            return False


async def configure_nginx(config: CouchDBConfig) -> bool:
    print_step(f"Configuring Nginx for domain: {config.domain}...")
    nginx_config = f"""server {{
    listen 80;
    server_name {config.domain};
    
    access_log /var/log/nginx/{config.domain}-access.log;
    error_log /var/log/nginx/{config.domain}-error.log;

    real_ip_header CF-Connecting-IP;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 2400:cb00::/32;
    set_real_ip_from 2606:4700::/32;
    set_real_ip_from 2803:f800::/32;
    set_real_ip_from 2405:b500::/32;
    set_real_ip_from 2405:8100::/32;
    set_real_ip_from 2c0f:f248::/32;
    set_real_ip_from 2a06:98c0::/29;

    location / {{
        proxy_pass http://localhost:{config.port};
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        if ($request_method = 'OPTIONS') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost https://{config.domain} http://{config.domain}';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }}
        if ($request_method = 'POST') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost https://{config.domain} http://{config.domain}' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'GET') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost https://{config.domain} http://{config.domain}' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'PUT') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost https://{config.domain} http://{config.domain}' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        }}
        if ($request_method = 'DELETE') {{
            add_header 'Access-Control-Allow-Origin' 'app://obsidian.md capacitor://localhost http://localhost https://{config.domain} http://{config.domain}' always;
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
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
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
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        config_filename = f"{config.domain}.conf"
        config_path = NGINX_CONFIG_PATH / config_filename
        temp_file = Path("/tmp") / config_filename
        try:
            with temp_file.open("w") as f:
                f.write(nginx_config)
        except Exception as e:
            await progress_task
            print_error(f"Failed to create temporary configuration file: {e}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "mv", str(temp_file), str(config_path)], check_sudo=True
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to create Nginx configuration: {stderr}")
            return False
        symlink_path = NGINX_ENABLED_PATH / config_filename
        ret, _, stderr = await run_command_async(
            ["sudo", "ln", "-sf", str(config_path), str(symlink_path)], check_sudo=True
        )
        if ret != 0:
            await progress_task
            print_error(f"Failed to enable Nginx site: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "nginx", "-t"], check_sudo=True
        )
        if ret != 0:
            await progress_task
            print_error(f"Nginx configuration is invalid: {stderr}")
            return False
        ret, _, stderr = await run_command_async(
            ["sudo", "systemctl", "restart", "nginx"], check_sudo=True
        )
        await progress_task
        if ret != 0:
            print_error(f"Failed to restart Nginx: {stderr}")
            return False
        running, status_str = await check_service_status("nginx")
        if running:
            print_success("Nginx is now running with the new configuration")
            return True
        else:
            print_error(f"Nginx is not running: {status_str}")
            return False


async def run_livesync_init(config: Optional[CouchDBConfig] = None) -> bool:
    """
    Initialize Obsidian LiveSync.

    If no configuration is provided, the configuration file is loaded.
    IMPORTANT: If the domain is still the default value, this version now uses
    socket.gethostname() as the hostname instead of "localhost", preventing the
    'Hostname missing' error.
    """
    print_step("Initializing Obsidian LiveSync...")
    if config is None:
        config = await load_config()
    # Use the configured domain if provided; if it is still the default, use the machine hostname.
    hostname = (
        config.domain
        if config.domain != DEFAULT_DOMAIN
        else (socket.gethostname() or "localhost")
    )
    print_step(f"Using hostname: {hostname}")
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            f"[{NordColors.FROST_2}]Initializing LiveSync...", total=100
        )
        steps = [
            (f"[{NordColors.FROST_2}]Downloading initialization script...", 20),
            (f"[{NordColors.FROST_2}]Preparing script...", 40),
            (f"[{NordColors.FROST_2}]Running script...", 70),
            (f"[{NordColors.GREEN}]Initialization complete.", 100),
        ]
        progress_task = asyncio.create_task(simulate_progress(progress, task_id, steps))
        temp_script_path = Path("/tmp") / "livesync_init_auto.sh"
        temp_output_path = Path("/tmp") / "livesync_output.log"
        try:
            ret, _, stderr = await run_command_async(
                [
                    "curl",
                    "-s",
                    "-o",
                    str(temp_script_path),
                    "https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/main/utils/couchdb/couchdb-init.sh",
                ]
            )
            if ret != 0:
                await progress_task
                print_error(f"Failed to download LiveSync script: {stderr}")
                return False
            await run_command_async(["chmod", "+x", str(temp_script_path)])
            ret, stdout, _ = await run_command_async(
                ["curl", "-s", f"http://localhost:{config.port}"]
            )
            if ret != 0 or "couchdb" not in stdout.lower():
                await progress_task
                print_error("CouchDB not accessible. Cannot initialize LiveSync.")
                return False
            env_vars = f"HOSTNAME={hostname} COUCH_URL=http://{hostname}:{config.port}"
            ret, _, stderr = await run_command_async(
                [
                    "bash",
                    "-c",
                    f"{env_vars} yes | {str(temp_script_path)} > {str(temp_output_path)} 2>&1",
                ]
            )
            if ret != 0:
                print_warning(
                    "First initialization attempt failed, trying with explicit parameters..."
                )
                ret, _, stderr = await run_command_async(
                    [
                        "bash",
                        "-c",
                        f"yes | {str(temp_script_path)} -h {hostname} > {str(temp_output_path)} 2>&1",
                    ]
                )
            try:
                with temp_output_path.open("r") as f:
                    output_log = f.read()
                app_logger.debug("LiveSync initialization output", output_log)
                if "error" in output_log.lower() or "failed" in output_log.lower():
                    error_lines = [
                        line
                        for line in output_log.splitlines()
                        if "error" in line.lower() or "failed" in line.lower()
                    ]
                    error_details = "\n".join(error_lines)
                    print_error(f"LiveSync initialization had errors:\n{error_details}")
            except Exception as e:
                app_logger.error(f"Failed to read LiveSync output log: {e}")
            await progress_task
            if ret != 0:
                print_error("Failed to initialize LiveSync. Check logs for details.")
                return False
            ret, stdout, _ = await run_command_async(
                ["curl", "-s", f"http://localhost:{config.port}/_all_dbs"]
            )
            if ret == 0 and (
                "livesync" in stdout.lower() or "obsidian" in stdout.lower()
            ):
                print_success("Obsidian LiveSync has been initialized successfully")
                return True
            else:
                print_warning(
                    "LiveSync initialization completed but databases may not be properly created"
                )
                return True
        except Exception as e:
            print_error(f"Error during LiveSync initialization: {e}")
            return False
        finally:
            for temp_file in (temp_script_path, temp_output_path):
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception as e:
                    app_logger.warning(
                        f"Failed to clean up temporary file {temp_file}: {e}"
                    )


async def check_couchdb_access(config: CouchDBConfig) -> bool:
    print_step("Checking CouchDB access...")
    url = f"http://localhost:{config.port}/"
    ret, stdout, _ = await run_command_async(["curl", "-s", url])
    if ret != 0 or "couchdb" not in stdout.lower():
        print_error(f"CouchDB is not accessible at {url}")
        return False
    print_success(f"CouchDB is accessible at {url}")
    return True


async def display_summary(config: CouchDBConfig, status: InstallStatus) -> None:
    clear_screen()
    console.print(create_header())
    print_section("Installation Summary")
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        padding=(0, 2),
    )
    table.add_column("Component", style=f"bold {NordColors.FROST_1}")
    table.add_column("Status", style=f"bold {NordColors.SNOW_STORM_1}")
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
        print_section("Next Steps")
        print_step("Set up your DNS to point your domain to this server")
        print_step("Install the Obsidian LiveSync plugin in your Obsidian vault")
        print_step(f"Use the following URL in LiveSync: http://{config.domain}")
        print_step(
            f"Use admin credentials: {config.admin_username}/{config.admin_password}"
        )
        print_warning("Important: Keep these credentials safe and secure!")
    else:
        print_section("Next Steps")
        print_step("Complete the installation process to get connection details")


# =============================================================================
# Interactive Menu and Troubleshooting
# =============================================================================


async def view_logs_async() -> None:
    logs_viewed = False
    current_filter: Optional[str] = None
    page_size = 20
    current_page = 0
    while True:
        clear_screen()
        console.print(create_header())
        print_section("Log Viewer")
        logs = app_logger.get_logs(level=current_filter)
        total_pages = max(1, (len(logs) + page_size - 1) // page_size)
        current_page = min(current_page, total_pages - 1)
        if current_filter:
            print_message(f"Filter: {current_filter.upper()}", NordColors.YELLOW)
        else:
            print_message("Showing all logs", NordColors.FROST_2)
        print_message(f"Page {current_page + 1} of {total_pages}", NordColors.FROST_3)
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
                    for line in log.details.splitlines():
                        if line.strip():
                            console.print(f"  [{NordColors.POLAR_NIGHT_4}]{line}[/]")
        else:
            print_message("No logs found", NordColors.YELLOW)
        print_section("Commands")
        console.print(f"[bold {NordColors.FROST_2}]n[/]: Next page")
        console.print(f"[bold {NordColors.FROST_2}]p[/]: Previous page")
        console.print(f"[bold {NordColors.FROST_2}]f[/]: Filter logs")
        console.print(f"[bold {NordColors.FROST_2}]c[/]: Clear filter")
        console.print(f"[bold {NordColors.FROST_2}]s[/]: Save logs to file")
        console.print(f"[bold {NordColors.FROST_2}]q[/]: Return to main menu")
        choice = (await async_prompt("Enter command")).lower()
        if choice == "q":
            break
        elif choice == "n" and current_page < total_pages - 1:
            current_page += 1
        elif choice == "p" and current_page > 0:
            current_page -= 1
        elif choice == "f":
            filter_choice = (
                await async_prompt(
                    "Filter by (i)nfo, (e)rror, (w)arning, (s)uccess, (d)ebug"
                )
            ).lower()
            mapping = {
                "i": "INFO",
                "info": "INFO",
                "e": "ERROR",
                "error": "ERROR",
                "w": "WARNING",
                "warning": "WARNING",
                "s": "SUCCESS",
                "success": "SUCCESS",
                "d": "DEBUG",
                "debug": "DEBUG",
            }
            if filter_choice in mapping:
                current_filter = mapping[filter_choice]
                current_page = 0
                print_success(f"Filtering logs by {current_filter}")
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
                save_path = str(Path.home() / "couchdb_installer_logs.txt")
            try:
                with open(save_path, "w") as f:
                    f.write(app_logger.get_log_file_content())
                print_success(f"Logs saved to {save_path}")
            except Exception as e:
                print_error(f"Failed to save logs: {e}")
            await async_prompt("Press Enter to continue")
        logs_viewed = True
    if logs_viewed:
        print_success("Returning to main menu")
        await async_prompt("Press Enter to continue")


async def troubleshoot_async(config: CouchDBConfig, status: InstallStatus) -> None:
    clear_screen()
    console.print(create_header())
    print_section("Troubleshooting Assistant")
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
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        padding=(0, 2),
    )
    table.add_column("Failed Component", style=f"bold {NordColors.RED}")
    table.add_column("Troubleshooting Steps", style=f"{NordColors.SNOW_STORM_1}")
    for component in failed_components:
        if component == "Snapd":
            table.add_row(
                "Snapd",
                "1. Check if your system supports snap\n2. Try installing manually: sudo apt update && sudo apt install snapd\n3. Check if snapd service is running: systemctl status snapd",
            )
        elif component == "CouchDB":
            table.add_row(
                "CouchDB",
                "1. Try installing manually: sudo snap install couchdb\n2. Check if the CouchDB snap is available: snap find couchdb\n3. Verify snap is working: snap list",
            )
        elif component == "CouchDB Configuration":
            table.add_row(
                "CouchDB Configuration",
                "1. Check CouchDB status: sudo snap services couchdb\n2. Check logs: sudo snap logs couchdb -f\n3. Try manual config: sudo snap set couchdb admin=password, setcookie=cookie and restart",
            )
        elif component == "Nginx":
            table.add_row(
                "Nginx",
                "1. Try installing manually: sudo apt update && sudo apt install nginx\n2. Check if another service is using port 80\n3. Check nginx status: systemctl status nginx",
            )
        elif component == "Nginx Configuration":
            table.add_row(
                "Nginx Configuration",
                "1. Check nginx configuration: sudo nginx -t\n2. Check error logs: sudo cat /var/log/nginx/error.log\n3. Verify sites-enabled and permissions",
            )
        elif component == "LiveSync":
            table.add_row(
                "LiveSync",
                "1. Check if CouchDB is running: curl http://localhost:5984\n2. Run script manually: curl -s https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/main/utils/couchdb/couchdb-init.sh | bash\n3. Verify internet connectivity and required databases",
            )
    console.print(table)
    print_section("Automatic Repair")
    if "CouchDB Configuration" in failed_components:
        if await async_confirm(
            "Attempt to automatically repair CouchDB configuration?", default=True
        ):
            print_step("Attempting to repair CouchDB configuration...")
            success = await configure_couchdb(config)
            if success:
                print_success("CouchDB configuration repaired successfully!")
                status.couchdb_configured = True
                await save_status(status)
            else:
                print_error("Failed to repair CouchDB configuration")
    if "LiveSync" in failed_components:
        if await async_confirm(
            "Attempt to automatically initialize LiveSync?", default=True
        ):
            print_step("Attempting to initialize LiveSync...")
            success = await run_livesync_init()
            if success:
                print_success("LiveSync initialized successfully!")
                status.livesync_initialized = True
                await save_status(status)
            else:
                print_error("Failed to initialize LiveSync")
    print_section("Diagnostics")
    if await async_confirm("Run diagnostics to gather more information?", default=True):
        print_step("Running diagnostics...")
        ret, sys_info, _ = await run_command_async(["uname", "-a"])
        ret, disk_space, _ = await run_command_async(["df", "-h", "/var"])
        ret, couchdb_response, _ = await run_command_async(
            ["curl", "-s", f"http://localhost:{config.port}"]
        )
        print_section("Diagnostic Results")
        diag_table = Table(show_header=False, box=None, padding=(0, 3))
        diag_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        diag_table.add_column("Value", style=f"{NordColors.SNOW_STORM_2}")
        diag_table.add_row("System Info", sys_info if ret == 0 else "Unknown")
        diag_table.add_row("Disk Space", disk_space if ret == 0 else "Unknown")
        diag_table.add_row(
            "CouchDB Response", couchdb_response if ret == 0 else "Not responding"
        )
        console.print(diag_table)
    print_section("Next Steps")
    print_step("Check the application logs for detailed error messages")
    print_step("Consider re-running the installer for failed components")
    print_step("Consult CouchDB and Nginx documentation for manual configuration")
    await async_prompt("Press Enter to return to the main menu")


async def install_manager_async() -> None:
    config = await load_config()
    status = await load_status()
    clear_screen()
    console.print(create_header())
    display_panel(
        "CouchDB Installer for Obsidian LiveSync",
        "This wizard will guide you through installing and configuring CouchDB with Nginx for Obsidian LiveSync",
        NordColors.FROST_3,
    )
    if not config.domain or config.domain == DEFAULT_DOMAIN:
        new_domain = await async_prompt(
            f"Enter your domain for Obsidian LiveSync (default: {DEFAULT_DOMAIN})"
        )
        config.domain = new_domain if new_domain else DEFAULT_DOMAIN
        await save_config(config)
    print_section("Step 1: Setting up snapd")
    if not status.snapd_installed:
        status.snapd_installed = await check_snapd_installed()
        if not status.snapd_installed:
            if await async_confirm("Install snapd?", default=True):
                status.snapd_installed = await install_snapd()
                await save_status(status)
            else:
                print_warning("Snapd installation skipped")
                await async_prompt("Press Enter to continue")
                return
    print_section("Step 2: Installing CouchDB")
    if not status.couchdb_installed:
        status.couchdb_installed = await check_couchdb_installed()
        if not status.couchdb_installed:
            if await async_confirm("Install CouchDB via snap?", default=True):
                status.couchdb_installed = await install_couchdb_snap()
                await save_status(status)
            else:
                print_warning("CouchDB installation skipped")
                await async_prompt("Press Enter to continue")
                return
    print_section("Step 3: Configuring CouchDB")
    if not status.couchdb_configured:
        if await async_confirm(
            "Configure CouchDB with admin credentials?", default=True
        ):
            status.couchdb_configured = await configure_couchdb(config)
            await save_status(status)
        else:
            print_warning("CouchDB configuration skipped")
            await async_prompt("Press Enter to continue")
            return
    print_section("Step 4: Verifying CouchDB")
    if not await check_couchdb_access(config):
        print_warning(
            "CouchDB is not accessible. Please check the installation and configuration."
        )
        await async_prompt("Press Enter to continue")
        return
    print_section("Step 5: Setting up Nginx")
    if not status.nginx_installed:
        status.nginx_installed = await check_nginx_installed()
        if not status.nginx_installed:
            if await async_confirm("Install Nginx?", default=True):
                status.nginx_installed = await install_nginx()
                await save_status(status)
            else:
                print_warning("Nginx installation skipped")
                await async_prompt("Press Enter to continue")
                return
    print_section("Step 6: Configuring Nginx")
    if not status.nginx_configured:
        if await async_confirm(
            f"Configure Nginx for domain: {config.domain}?", default=True
        ):
            status.nginx_configured = await configure_nginx(config)
            await save_status(status)
        else:
            print_warning("Nginx configuration skipped")
            await async_prompt("Press Enter to continue")
            return
    print_section("Step 7: Initializing Obsidian LiveSync")
    if not status.livesync_initialized:
        if await async_confirm("Initialize Obsidian LiveSync?", default=True):
            status.livesync_initialized = await run_livesync_init(config)
            await save_status(status)
        else:
            print_warning("LiveSync initialization skipped")
            await async_prompt("Press Enter to continue")
            return
    await display_summary(config, status)
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
    config = await load_config()
    status = await load_status()
    while True:
        clear_screen()
        console.print(create_header())
        print_section("CouchDB Installer Menu")
        console.print(
            f"[bold {NordColors.FROST_2}]1.[/] [ {NordColors.SNOW_STORM_2}]Run Installation Wizard[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]2.[/] [ {NordColors.SNOW_STORM_2}]View Installation Status[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]3.[/] [ {NordColors.SNOW_STORM_2}]Change Domain Configuration[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]4.[/] [ {NordColors.SNOW_STORM_2}]View Logs[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]5.[/] [ {NordColors.SNOW_STORM_2}]Troubleshooting[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]6.[/] [ {NordColors.SNOW_STORM_2}]Run LiveSync Initialization Only[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]7.[/] [ {NordColors.SNOW_STORM_2}]Update Nginx Configuration Only[/]"
        )
        console.print(
            f"[bold {NordColors.FROST_2}]q.[/] [ {NordColors.SNOW_STORM_2}]Quit[/]"
        )
        choice = (await async_prompt("Enter your choice")).lower()
        if choice in ("q", "quit", "exit"):
            break
        elif choice == "1":
            await install_manager_async()
        elif choice == "2":
            await display_summary(config, status)
            await async_prompt("Press Enter to return to the menu")
        elif choice == "3":
            new_domain = await async_prompt(
                f"Enter new domain (current: {config.domain})"
            )
            if new_domain:
                config.domain = new_domain
                await save_config(config)
                print_success(f"Domain updated to {config.domain}")
                if status.nginx_configured:
                    if await async_confirm(
                        "Reconfigure Nginx with new domain?", default=True
                    ):
                        status.nginx_configured = await configure_nginx(config)
                        await save_status(status)
            await async_prompt("Press Enter to return to the menu")
        elif choice == "4":
            await view_logs_async()
        elif choice == "5":
            await troubleshoot_async(config, status)
        elif choice == "6":
            print_section("Running LiveSync Initialization")
            if await run_livesync_init(config):
                status.livesync_initialized = True
                await save_status(status)
                print_success("LiveSync initialization completed successfully")
            else:
                print_error("LiveSync initialization failed")
            await async_prompt("Press Enter to return to the menu")
        elif choice == "7":
            print_section("Updating Nginx Configuration")
            if await configure_nginx(config):
                status.nginx_configured = True
                await save_status(status)
                print_success("Nginx configuration updated successfully")
            else:
                print_error("Failed to update Nginx configuration")
            await async_prompt("Press Enter to return to the menu")
        else:
            print_error(f"Invalid choice: {choice}")
            await async_prompt("Press Enter to continue")


async def async_cleanup() -> None:
    """Perform any necessary async cleanup (placeholder)."""
    pass


async def signal_handler_async(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    loop = asyncio.get_running_loop()
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()
    await async_cleanup()
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def proper_shutdown_async():
    try:
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=2.0)
    except RuntimeError:
        pass
    except Exception as e:
        print_error(f"Error during async shutdown: {e}")


def proper_shutdown():
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                print_warning("Event loop already running during shutdown")
                return
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(proper_shutdown_async())
        loop.close()
    except Exception as e:
        print_error(f"Error during synchronous shutdown: {e}")


async def main_async() -> None:
    try:
        await ensure_config_directory()
        await main_menu_async()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        atexit.register(proper_shutdown)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Received keyboard interrupt, shutting down...")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")
        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
