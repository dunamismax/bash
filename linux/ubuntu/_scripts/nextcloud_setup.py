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
import yaml
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast
from pathlib import Path

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
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.markdown import Markdown
    from rich.logging import RichHandler
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet pyyaml"
    )
    sys.exit(1)

# Configuration and Constants
APP_NAME: str = "Nextcloud Installer"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER") or "sawyer"
DOMAIN_NAME: str = "nextcloud.dunamismax.com"
DOCKER_COMMAND: List[str] = ["docker"]
DOCKER_COMPOSE_V1_COMMAND: List[str] = ["docker-compose"]
DOCKER_COMPOSE_V2_COMMAND: List[str] = ["docker", "compose"]
DOCKER_COMPOSE_COMMAND: List[str] = DOCKER_COMPOSE_V2_COMMAND  # Default to V2
OPERATION_TIMEOUT: int = 60

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/nextcloud_installer")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
LOG_DIR: str = os.path.join(CONFIG_DIR, "logs")
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE: str = os.path.join(LOG_DIR, f"nextcloud_installer_{current_time}.log")

# Docker Compose setup directory
DOCKER_DIR: str = os.path.expanduser("~/nextcloud_docker")
DOCKER_COMPOSE_FILE: str = os.path.join(DOCKER_DIR, "docker-compose.yml")

# Setup logging
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RichHandler(rich_tracebacks=True, show_time=False),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("nextcloud_installer")
install_rich_traceback(show_locals=True)
console: Console = Console(record=True)


class NordColors:
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
class NextcloudConfig:
    domain: str = DOMAIN_NAME
    admin_username: str = DEFAULT_USERNAME
    admin_password: str = ""
    db_username: str = DEFAULT_USERNAME
    db_password: str = ""
    db_name: str = "nextcloud"
    db_host: str = "db"
    use_https: bool = False
    port: int = 8080
    data_dir: str = os.path.join(DOCKER_DIR, "nextcloud_data")
    db_data_dir: str = os.path.join(DOCKER_DIR, "postgres_data")
    custom_apps_dir: str = os.path.join(DOCKER_DIR, "custom_apps")
    config_dir: str = os.path.join(DOCKER_DIR, "config")
    theme_dir: str = os.path.join(DOCKER_DIR, "theme")
    installation_status: str = "not_installed"
    installed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# UI Helper Functions
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
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
    except Exception as e:
        logger.error(f"Failed to create ASCII art: {e}")
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
    message = f"{prefix} {text}"
    console.print(f"[{style}]{message}[/{style}]")
    logger.info(message)


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")
    logger.error(message)


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")
    logger.info(f"SUCCESS: {message}")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")
    logger.warning(message)


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")
    logger.info(f"STEP: {message}")


def print_section(title: str) -> None:
    console.print()
    section_title = f"[bold {NordColors.FROST_3}]{title}[/]"
    section_line = f"[{NordColors.FROST_3}]{'─' * len(title)}[/]"
    console.print(section_title)
    console.print(section_line)
    logger.info(f"SECTION: {title}")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)
    logger.info(f"PANEL [{title}]: {message}")


def save_console_output() -> None:
    """Save current console output to a file"""
    try:
        output_file = f"{LOG_DIR}/console_output_{current_time}.html"
        console.save_html(output_file)
        logger.info(f"Console output saved to {output_file}")
        print_success(f"Console output saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save console output: {e}")
        print_error(f"Failed to save console output: {e}")


# Core Functionality
async def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        logger.info(f"Created config directory: {CONFIG_DIR}")
    except Exception as e:
        error_msg = f"Could not create config directory: {e}"
        logger.error(error_msg)
        print_error(error_msg)


async def save_config(config: NextcloudConfig) -> bool:
    await ensure_config_directory()
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: json.dump(config.to_dict(), open(CONFIG_FILE, "w"), indent=2)
        )
        logger.info(f"Saved configuration to {CONFIG_FILE}")
        return True
    except Exception as e:
        error_msg = f"Failed to save configuration: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def load_config() -> NextcloudConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, lambda: json.load(open(CONFIG_FILE, "r"))
            )
            logger.info(f"Loaded configuration from {CONFIG_FILE}")
            return NextcloudConfig(**data)
    except Exception as e:
        error_msg = f"Failed to load configuration: {e}"
        logger.error(error_msg)
        print_error(error_msg)
    logger.info("Using default configuration")
    return NextcloudConfig()


async def run_command_async(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and capture stdout and stderr."""
    cmd_str = " ".join(cmd)
    logger.info(f"Running command: {cmd_str}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=OPERATION_TIMEOUT
        )
        stdout = stdout_bytes.decode("utf-8").strip() if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8").strip() if stderr_bytes else ""
        returncode = proc.returncode or 0
        logger.info(f"Command completed with return code: {returncode}")
        if stdout:
            logger.debug(f"Command stdout: {stdout}")
        if stderr:
            logger.warning(f"Command stderr: {stderr}")
        return returncode, stdout, stderr
    except asyncio.TimeoutError:
        error_msg = f"Command timed out: {cmd_str}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Command failed: {e}"
        logger.error(f"{error_msg} (Command: {cmd_str})")
        raise Exception(error_msg)


async def check_docker_installed() -> bool:
    """Check if Docker is installed and available."""
    logger.info("Checking if Docker is installed")
    try:
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMMAND + ["--version"]
        )
        if returncode == 0:
            print_success(f"Docker is installed: {stdout}")
            logger.info(f"Docker is installed: {stdout}")
            return True
        else:
            print_error(f"Docker not available: {stderr}")
            logger.error(f"Docker not available: {stderr}")
            return False
    except Exception as e:
        error_msg = f"Error checking Docker: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def check_docker_compose_installed() -> bool:
    """Check if Docker Compose is installed and available."""
    global DOCKER_COMPOSE_COMMAND
    logger.info("Checking if Docker Compose is installed")
    try:
        # Try Docker Compose V2
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_V2_COMMAND + ["--version"]
        )
        if returncode == 0:
            print_success(f"Docker Compose V2 is installed: {stdout}")
            logger.info(f"Docker Compose V2 is installed: {stdout}")
            DOCKER_COMPOSE_COMMAND = DOCKER_COMPOSE_V2_COMMAND
            return True
        else:
            if "docker: 'compose'" in stderr:
                logger.info(
                    "Docker Compose V2 not available; falling back to legacy docker-compose command."
                )
                raise Exception("Docker Compose V2 plugin not available")
    except Exception as e:
        logger.warning(f"Docker Compose V2 check failed: {e}")

    # Fallback to Docker Compose V1
    try:
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_V1_COMMAND + ["--version"]
        )
        if returncode == 0:
            print_success(f"Docker Compose V1 is installed: {stdout}")
            logger.info(f"Docker Compose V1 is installed: {stdout}")
            DOCKER_COMPOSE_COMMAND = DOCKER_COMPOSE_V1_COMMAND
            return True
        else:
            print_error("Docker Compose not available")
            logger.error("Docker Compose not available")
            return False
    except Exception as e:
        error_msg = f"Error checking Docker Compose: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def check_prerequisites() -> bool:
    """Check all prerequisites for installation."""
    print_section("Checking Prerequisites")
    logger.info("Checking prerequisites")
    docker_ok = await check_docker_installed()
    compose_ok = await check_docker_compose_installed()
    if not (docker_ok and compose_ok):
        error_msg = "Missing required dependencies. Please install Docker and Docker Compose first."
        logger.error(error_msg)
        print_error(error_msg)
        return False
    logger.info("All prerequisites satisfied")
    return True


# ---------------------------
# New Docker installation function
# ---------------------------
async def install_docker() -> bool:
    """Install Docker using Docker's official installation method for Ubuntu."""
    print_step("Installing Docker...")
    commands = [
        ["sudo", "apt-get", "update"],
        ["sudo", "apt-get", "install", "ca-certificates", "curl", "-y"],
        ["sudo", "install", "-m", "0755", "-d", "/etc/apt/keyrings"],
        [
            "sudo",
            "curl",
            "-fsSL",
            "https://download.docker.com/linux/ubuntu/gpg",
            "-o",
            "/etc/apt/keyrings/docker.asc",
        ],
        ["sudo", "chmod", "a+r", "/etc/apt/keyrings/docker.asc"],
        [
            "bash",
            "-c",
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
        ],
        ["sudo", "apt-get", "update"],
        [
            "sudo",
            "apt-get",
            "install",
            "docker-ce",
            "docker-ce-cli",
            "containerd.io",
            "docker-buildx-plugin",
            "docker-compose-plugin",
            "-y",
        ],
    ]
    for cmd in commands:
        try:
            returncode, stdout, stderr = await run_command_async(cmd)
            if returncode != 0:
                print_error(f"Command '{' '.join(cmd)}' failed: {stderr}")
                return False
        except Exception as e:
            print_error(f"Error running command '{' '.join(cmd)}': {e}")
            return False
    print_success("Docker installed successfully!")
    return True


# ---------------------------
# End Docker installation function
# ---------------------------


async def create_docker_compose_file(config: NextcloudConfig) -> bool:
    """Create the Docker Compose file for Nextcloud and PostgreSQL using Docker-managed volumes."""
    logger.info("Creating Docker Compose file with named volumes")
    try:
        os.makedirs(DOCKER_DIR, exist_ok=True)
        logger.info(f"Created Docker directory: {DOCKER_DIR}")

        # Instead of creating host directories, we now rely on Docker-managed volumes.
        compose_config = {
            "version": "3",
            "services": {
                "db": {
                    "image": "postgres:15",
                    "restart": "always",
                    "volumes": ["postgres_data:/var/lib/postgresql/data"],
                    "environment": {
                        "POSTGRES_DB": config.db_name,
                        "POSTGRES_USER": config.db_username,
                        "POSTGRES_PASSWORD": config.db_password,
                    },
                },
                "app": {
                    "image": "nextcloud:apache",
                    "restart": "always",
                    "depends_on": ["db"],
                    "volumes": [
                        "nextcloud_data:/var/www/html/data",
                        "nextcloud_custom_apps:/var/www/html/custom_apps",
                        "nextcloud_config:/var/www/html/config",
                        "nextcloud_themes:/var/www/html/themes/custom",
                    ],
                    "environment": {
                        "POSTGRES_DB": config.db_name,
                        "POSTGRES_USER": config.db_username,
                        "POSTGRES_PASSWORD": config.db_password,
                        "POSTGRES_HOST": config.db_host,
                        "NEXTCLOUD_ADMIN_USER": config.admin_username,
                        "NEXTCLOUD_ADMIN_PASSWORD": config.admin_password,
                        "NEXTCLOUD_TRUSTED_DOMAINS": config.domain,
                    },
                    "ports": [f"{config.port}:80"],
                },
            },
            "volumes": {
                "postgres_data": {},
                "nextcloud_data": {},
                "nextcloud_custom_apps": {},
                "nextcloud_config": {},
                "nextcloud_themes": {},
            },
        }

        with open(DOCKER_COMPOSE_FILE, "w") as f:
            yaml.dump(compose_config, f, default_flow_style=False)

        logger.info(f"Created Docker Compose configuration at {DOCKER_COMPOSE_FILE}")
        print_success(f"Created Docker Compose configuration at {DOCKER_COMPOSE_FILE}")
        return True

    except Exception as e:
        error_msg = f"Failed to create Docker Compose file: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def start_docker_containers() -> bool:
    """Start the Docker containers defined in the compose file."""
    logger.info("Starting Docker containers")
    try:
        print_step("Starting Nextcloud containers...")
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        # Run in detached mode by adding "-d" flag
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND + ["up", "-d"]
        )
        if returncode == 0:
            print_success("Nextcloud containers started successfully")
            logger.info("Nextcloud containers started successfully")
            return True
        else:
            error_msg = f"Failed to start containers: {stderr}"
            logger.error(error_msg)
            print_error(error_msg)
            return False
    except Exception as e:
        error_msg = f"Error starting containers: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def check_nextcloud_status() -> bool:
    """Check if Nextcloud is running and accessible."""
    logger.info("Checking Nextcloud status")
    try:
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND + ["ps", "-q", "app"]
        )
        if not stdout:
            error_msg = "Nextcloud container is not running"
            logger.error(error_msg)
            print_error(error_msg)
            return False
        print_success("Nextcloud container is running")
        logger.info("Nextcloud container is running")
        return True
    except Exception as e:
        error_msg = f"Error checking Nextcloud status: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def stop_docker_containers() -> bool:
    """Stop the Docker containers."""
    logger.info("Stopping Docker containers")
    try:
        print_step("Stopping Nextcloud containers...")
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND + ["down"]
        )
        if returncode == 0:
            print_success("Nextcloud containers stopped successfully")
            logger.info("Nextcloud containers stopped successfully")
            return True
        else:
            error_msg = f"Failed to stop containers: {stderr}"
            logger.error(error_msg)
            print_error(error_msg)
            return False
    except Exception as e:
        error_msg = f"Error stopping containers: {e}"
        logger.error(error_msg)
        print_error(error_msg)
        return False


async def execute_occ_command(command: List[str]) -> Tuple[bool, str]:
    """Execute Nextcloud occ command inside the container."""
    logger.info(f"Executing occ command: {' '.join(command)}")
    try:
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        full_command = (
            DOCKER_COMPOSE_COMMAND
            + ["exec", "--user", "www-data", "app", "php", "occ"]
            + command
        )
        returncode, stdout, stderr = await run_command_async(full_command)
        if returncode == 0:
            logger.info(f"OCC command successful: {stdout}")
            return True, stdout
        else:
            logger.error(f"OCC command failed: {stderr}")
            return False, stderr
    except Exception as e:
        error_msg = f"Error executing OCC command: {e}"
        logger.error(error_msg)
        return False, str(e)


async def async_confirm(message: str, default: bool = False) -> bool:
    logger.info(f"Asking for confirmation: {message}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )
    logger.info(f"Confirmation result: {result}")
    return result


async def async_prompt(message: str, default: str = "") -> str:
    logger.info(f"Prompting user: {message}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: Prompt.ask(message, default=default)
    )
    logger.info("User input received (prompt)")
    return result


async def async_int_prompt(message: str, default: int = 0) -> int:
    logger.info(f"Prompting user for integer: {message}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: IntPrompt.ask(message, default=default)
    )
    logger.info(f"User input received: {result}")
    return result


async def async_password_prompt(message: str) -> str:
    logger.info(f"Prompting user for password: {message}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: Prompt.ask(message, password=True)
    )
    logger.info("Password input received")
    return result


async def configure_nextcloud() -> NextcloudConfig:
    """Interactive configuration for Nextcloud installation."""
    logger.info("Starting Nextcloud configuration")
    config = await load_config()
    clear_screen()
    console.print(create_header())
    display_panel(
        "Nextcloud Configuration",
        "Please provide the configuration details for your Nextcloud installation",
        NordColors.FROST_2,
    )
    config.domain = await async_prompt(
        f"[bold {NordColors.FROST_2}]Domain name for Nextcloud[/]",
        default=config.domain,
    )
    logger.info(f"Domain configured: {config.domain}")
    config.admin_username = await async_prompt(
        f"[bold {NordColors.FROST_2}]Admin username[/]", default=config.admin_username
    )
    logger.info(f"Admin username configured: {config.admin_username}")
    config.admin_password = await async_password_prompt(
        f"[bold {NordColors.FROST_2}]Admin password[/]"
    )
    logger.info("Admin password configured")
    print_section("Database Configuration")
    config.db_name = await async_prompt(
        f"[bold {NordColors.FROST_2}]Database name[/]", default=config.db_name
    )
    logger.info(f"Database name configured: {config.db_name}")
    config.db_username = await async_prompt(
        f"[bold {NordColors.FROST_2}]Database user[/]", default=config.db_username
    )
    logger.info(f"Database username configured: {config.db_username}")
    config.db_password = await async_password_prompt(
        f"[bold {NordColors.FROST_2}]Database password[/]"
    )
    logger.info("Database password configured")
    print_section("Network Configuration")
    config.port = await async_int_prompt(
        f"[bold {NordColors.FROST_2}]Port to expose Nextcloud on[/]",
        default=config.port,
    )
    logger.info(f"Port configured: {config.port}")
    config.use_https = await async_confirm(
        f"[bold {NordColors.FROST_2}]Enable HTTPS?[/]", default=config.use_https
    )
    logger.info(f"Use HTTPS configured: {config.use_https}")
    print_section("Data Directories")
    data_dir_default = os.path.join(os.path.expanduser("~"), "nextcloud_data")
    config.data_dir = await async_prompt(
        f"[bold {NordColors.FROST_2}]Nextcloud data directory[/]",
        default=config.data_dir,
    )
    logger.info(f"Data directory configured: {config.data_dir}")
    print_section("Configuration Summary")
    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("Domain", config.domain)
    table.add_row("Admin User", config.admin_username)
    table.add_row("Database Name", config.db_name)
    table.add_row("Database User", config.db_username)
    table.add_row("Port", str(config.port))
    table.add_row("HTTPS Enabled", "Yes" if config.use_https else "No")
    table.add_row("Data Directory", config.data_dir)
    console.print(table)
    console.print()
    if not await async_confirm(
        f"[bold {NordColors.FROST_2}]Is this configuration correct?[/]", default=True
    ):
        logger.info("Configuration not confirmed, starting over")
        print_warning("Configuration cancelled. Please start over.")
        return await configure_nextcloud()
    await save_config(config)
    print_success("Configuration saved successfully")
    logger.info("Configuration saved successfully")
    return config


async def install_nextcloud(config: NextcloudConfig) -> bool:
    """Install Nextcloud with the given configuration."""
    logger.info("Starting Nextcloud installation")
    try:
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
                f"[{NordColors.FROST_2}]Installing Nextcloud...", total=100
            )
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Checking prerequisites...",
                advance=10,
            )
            if not await check_prerequisites():
                logger.error("Prerequisites check failed")
                return False
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Creating Docker configuration...",
                advance=20,
            )
            if not await create_docker_compose_file(config):
                logger.error("Creating Docker configuration failed")
                return False
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Starting containers...",
                advance=30,
            )
            if not await start_docker_containers():
                logger.error("Starting containers failed")
                return False
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Waiting for containers to be ready...",
                advance=20,
            )
            logger.info("Waiting for containers to start up (5 seconds)")
            await asyncio.sleep(5)
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Verifying installation...",
                advance=10,
            )
            if not await check_nextcloud_status():
                logger.error("Verification failed - containers not running")
                return False
            progress.update(
                task_id,
                description=f"[{NordColors.GREEN}]Installation complete!",
                advance=10,
            )
        config.installation_status = "installed"
        config.installed_at = time.time()
        await save_config(config)
        logger.info("Installation completed successfully")
        return True
    except Exception as e:
        error_msg = f"Installation failed: {e}"
        logger.error(error_msg, exc_info=True)
        print_error(error_msg)
        try:
            logger.info("Attempting to get container logs for debugging")
            os.chdir(DOCKER_DIR)
            returncode, stdout, stderr = await run_command_async(
                DOCKER_COMPOSE_COMMAND + ["logs"]
            )
            log_output = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            container_log_file = os.path.join(
                LOG_DIR, f"container_logs_{current_time}.log"
            )
            with open(container_log_file, "w") as f:
                f.write(log_output)
            logger.info(f"Container logs saved to {container_log_file}")
            print_warning(
                f"Installation failed but container logs were saved to {container_log_file}"
            )
            print_warning("Please check the logs for details on the error.")
            await async_prompt("Press Enter to continue...")
        except Exception as log_e:
            logger.error(f"Failed to get container logs: {log_e}")
        return False


async def show_nextcloud_info(config: NextcloudConfig) -> None:
    """Display information about the Nextcloud installation."""
    logger.info("Showing Nextcloud information")
    clear_screen()
    console.print(create_header())
    if config.installation_status != "installed":
        display_panel(
            "Nextcloud Status",
            "Nextcloud is not installed yet. Please install it first.",
            NordColors.YELLOW,
        )
        logger.info("Tried to show info but Nextcloud is not installed")
        return
    running = await check_nextcloud_status()
    status_color = NordColors.GREEN if running else NordColors.RED
    status_text = "Running" if running else "Stopped"
    display_panel(
        "Nextcloud Status",
        f"Status: [{status_color}]{status_text}[/]",
        NordColors.FROST_2,
    )
    access_url = f"http://localhost:{config.port}"
    info_table = Table(show_header=False, box=box.ROUNDED)
    info_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    info_table.add_column("Value", style=NordColors.SNOW_STORM_1)
    info_table.add_row("Access URL", access_url)
    info_table.add_row("Admin User", config.admin_username)
    info_table.add_row("Installed At", time.ctime(config.installed_at or 0))
    info_table.add_row("Data Directory", config.data_dir)
    info_table.add_row("Docker Directory", DOCKER_DIR)
    info_table.add_row("Log Directory", LOG_DIR)
    info_table.add_row("Current Log File", LOG_FILE)
    console.print(info_table)
    console.print()
    await async_prompt("Press Enter to return to the main menu")
    logger.info("Returned to main menu from info screen")


async def start_nextcloud() -> bool:
    """Start the Nextcloud containers."""
    logger.info("Starting Nextcloud")
    clear_screen()
    console.print(create_header())
    display_panel(
        "Starting Nextcloud", "Starting Nextcloud containers...", NordColors.FROST_2
    )
    if await start_docker_containers():
        print_success("Nextcloud started successfully")
        logger.info("Nextcloud started successfully")
        await async_prompt("Press Enter to return to the main menu")
        return True
    else:
        print_error("Failed to start Nextcloud")
        logger.error("Failed to start Nextcloud")
        await async_prompt("Press Enter to return to the main menu")
        return False


async def stop_nextcloud() -> bool:
    """Stop the Nextcloud containers."""
    logger.info("Stopping Nextcloud")
    clear_screen()
    console.print(create_header())
    display_panel(
        "Stopping Nextcloud", "Stopping Nextcloud containers...", NordColors.FROST_2
    )
    if await stop_docker_containers():
        print_success("Nextcloud stopped successfully")
        logger.info("Nextcloud stopped successfully")
        await async_prompt("Press Enter to return to the main menu")
        return True
    else:
        print_error("Failed to stop Nextcloud")
        logger.error("Failed to stop Nextcloud")
        await async_prompt("Press Enter to return to the main menu")
        return False


async def uninstall_nextcloud() -> bool:
    """Uninstall Nextcloud and remove all data."""
    logger.info("Starting Nextcloud uninstallation")
    clear_screen()
    console.print(create_header())
    display_panel(
        "Uninstall Nextcloud",
        "⚠️ This will remove Nextcloud and all its data!",
        NordColors.RED,
    )
    confirm = await async_confirm(
        f"[bold {NordColors.RED}]Are you sure you want to uninstall Nextcloud? This cannot be undone![/]",
        default=False,
    )
    if not confirm:
        print_warning("Uninstallation cancelled")
        logger.info("Uninstallation cancelled by user")
        await async_prompt("Press Enter to return to the main menu")
        return False
    confirm_data = await async_confirm(
        f"[bold {NordColors.RED}]Should we also delete all data directories? This will PERMANENTLY DELETE all your Nextcloud files![/]",
        default=False,
    )
    logger.info(f"User confirmed data deletion: {confirm_data}")
    print_step("Stopping Nextcloud containers...")
    await stop_docker_containers()
    print_step("Removing Docker containers...")
    try:
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND + ["down", "--rmi", "all", "--volumes"]
        )
        if returncode == 0:
            logger.info("Docker containers removed successfully")
        else:
            logger.warning(f"Issues removing Docker containers: {stderr}")
    except Exception as e:
        error_msg = f"Error removing containers: {e}"
        logger.error(error_msg)
        print_error(error_msg)
    config = await load_config()
    if confirm_data:
        print_step("Removing data directories...")
        for directory in [
            config.data_dir,
            config.db_data_dir,
            config.custom_apps_dir,
            config.config_dir,
            config.theme_dir,
        ]:
            try:
                if os.path.exists(directory):
                    shutil.rmtree(directory)
                    print_success(f"Removed {directory}")
                    logger.info(f"Removed directory {directory}")
            except Exception as e:
                error_msg = f"Error removing directory {directory}: {e}"
                logger.error(error_msg)
                print_error(error_msg)
    try:
        print_step("Removing Docker configuration...")
        if os.path.exists(DOCKER_COMPOSE_FILE):
            os.remove(DOCKER_COMPOSE_FILE)
            print_success(f"Removed {DOCKER_COMPOSE_FILE}")
            logger.info(f"Removed {DOCKER_COMPOSE_FILE}")
        if confirm_data and os.path.exists(DOCKER_DIR):
            shutil.rmtree(DOCKER_DIR)
            print_success(f"Removed {DOCKER_DIR}")
            logger.info(f"Removed {DOCKER_DIR}")
    except Exception as e:
        error_msg = f"Error removing Docker configuration: {e}"
        logger.error(error_msg)
        print_error(error_msg)
    config.installation_status = "not_installed"
    config.installed_at = None
    await save_config(config)
    logger.info("Updated configuration - marked as not installed")
    print_success("Nextcloud has been uninstalled")
    logger.info("Nextcloud uninstallation completed")
    await async_prompt("Press Enter to return to the main menu")
    return True


async def view_logs() -> None:
    """View the most recent log entries."""
    logger.info("Viewing logs")
    clear_screen()
    console.print(create_header())
    display_panel(
        "Log Viewer", "Showing the most recent log entries", NordColors.FROST_2
    )
    try:
        log_files = sorted(
            [f for f in os.listdir(LOG_DIR) if f.endswith(".log")],
            key=lambda x: os.path.getmtime(os.path.join(LOG_DIR, x)),
            reverse=True,
        )
        if not log_files:
            print_warning("No log files found.")
            await async_prompt("Press Enter to return to the main menu")
            return
        log_table = Table(show_header=True, box=box.ROUNDED)
        log_table.add_column("#", style=f"bold {NordColors.FROST_2}")
        log_table.add_column("Log File", style=NordColors.SNOW_STORM_1)
        log_table.add_column("Size", style=NordColors.SNOW_STORM_1)
        log_table.add_column("Last Modified", style=NordColors.SNOW_STORM_1)
        for i, log_file in enumerate(log_files[:10], 1):
            file_path = os.path.join(LOG_DIR, log_file)
            size = os.path.getsize(file_path)
            size_str = f"{size / 1024:.1f} KB"
            modified = time.ctime(os.path.getmtime(file_path))
            log_table.add_row(str(i), log_file, size_str, modified)
        console.print(log_table)
        console.print()
        choice = await async_prompt(
            f"[bold {NordColors.FROST_2}]Enter a number to view a log file (or 'q' to return to menu)[/]"
        )
        if choice.lower() == "q":
            return
        try:
            file_index = int(choice) - 1
            if 0 <= file_index < len(log_files):
                selected_file = os.path.join(LOG_DIR, log_files[file_index])
                with open(selected_file, "r") as f:
                    lines = f.readlines()
                    tail_lines = lines[-100:] if len(lines) > 100 else lines
                clear_screen()
                console.print(create_header())
                display_panel(
                    f"Log File: {log_files[file_index]}",
                    f"Showing last {len(tail_lines)} lines",
                    NordColors.FROST_2,
                )
                for line in tail_lines:
                    if "ERROR" in line:
                        console.print(f"[bold {NordColors.RED}]{line.strip()}[/]")
                    elif "WARNING" in line:
                        console.print(f"[bold {NordColors.YELLOW}]{line.strip()}[/]")
                    else:
                        console.print(line.strip())
                console.print()
                await async_prompt("Press Enter to return to the main menu")
            else:
                print_error("Invalid selection")
                await async_prompt("Press Enter to try again")
                await view_logs()
        except ValueError:
            print_error("Please enter a number")
            await async_prompt("Press Enter to try again")
            await view_logs()
    except Exception as e:
        error_msg = f"Error viewing logs: {e}"
        logger.error(error_msg)
        print_error(error_msg)
    logger.info("Returned to main menu from log viewer")


async def view_container_logs() -> None:
    """View the Docker container logs."""
    logger.info("Viewing container logs")
    clear_screen()
    console.print(create_header())
    display_panel(
        "Container Logs", "Showing the Docker container logs", NordColors.FROST_2
    )
    try:
        config = await load_config()
        if config.installation_status != "installed":
            print_warning(
                "Nextcloud is not installed yet. No container logs available."
            )
            await async_prompt("Press Enter to return to the main menu")
            return
        os.chdir(DOCKER_DIR)
        logger.info(f"Changed directory to {DOCKER_DIR}")
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND + ["logs", "--tail=100"]
        )
        if returncode == 0:
            clear_screen()
            console.print(create_header())
            display_panel(
                "Container Logs", "Last 100 lines of container logs", NordColors.FROST_2
            )
            if stdout:
                console.print(stdout)
            if stderr:
                console.print(f"[bold {NordColors.RED}]STDERR:[/]")
                console.print(stderr)
            save_logs = await async_confirm(
                f"[bold {NordColors.FROST_2}]Save container logs to file?[/]",
                default=True,
            )
            if save_logs:
                log_file = os.path.join(LOG_DIR, f"container_logs_{current_time}.log")
                with open(log_file, "w") as f:
                    f.write(f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}")
                print_success(f"Container logs saved to {log_file}")
                logger.info(f"Container logs saved to {log_file}")
        else:
            print_error(f"Failed to get container logs: {stderr}")
            logger.error(f"Failed to get container logs: {stderr}")
    except Exception as e:
        error_msg = f"Error viewing container logs: {e}"
        logger.error(error_msg)
        print_error(error_msg)
    await async_prompt("Press Enter to return to the main menu")
    logger.info("Returned to main menu from container logs viewer")


async def main_menu_async() -> None:
    """Main menu for the Nextcloud installer."""
    logger.info("Starting main menu")
    try:
        while True:
            config = await load_config()
            clear_screen()
            console.print(create_header())
            is_installed = config.installation_status == "installed"
            is_running = False
            if is_installed:
                is_running = await check_nextcloud_status()
            status_text = "Not Installed"
            status_color = NordColors.YELLOW
            if is_installed:
                if is_running:
                    status_text = "Running"
                    status_color = NordColors.GREEN
                else:
                    status_text = "Stopped"
                    status_color = NordColors.RED
            menu_panel = Panel(
                f"Status: [{status_color}]{status_text}[/]\n\n"
                "1. Configure Nextcloud\n"
                "2. Install Nextcloud\n"
                "3. Start Nextcloud\n"
                "4. Stop Nextcloud\n"
                "5. Show Nextcloud Information\n"
                "6. Uninstall Nextcloud\n"
                "7. View Application Logs\n"
                "8. View Container Logs\n"
                "9. Install Docker\n"
                "q. Quit",
                title="Main Menu",
                border_style=NordColors.FROST_1,
                box=box.ROUNDED,
            )
            console.print(menu_panel)
            choice = await async_prompt("Enter your choice")
            choice = choice.strip().lower()
            logger.info(f"User selected menu option: {choice}")
            if choice in ("q", "quit", "exit"):
                clear_screen()
                console.print(
                    Panel(
                        Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                        border_style=NordColors.FROST_1,
                    )
                )
                logger.info("Exiting application")
                break
            elif choice == "1":
                await configure_nextcloud()
            elif choice == "2":
                if not config.admin_password or not config.db_password:
                    print_warning("Please configure Nextcloud first")
                    logger.warning("Installation attempted without configuration")
                    config = await configure_nextcloud()
                success = await install_nextcloud(config)
                if not success:
                    print_error("Installation failed. Check the logs for details.")
                    print_warning(f"Log file: {LOG_FILE}")
                    logger.error("Installation failed")
                    await async_prompt("Press Enter to continue...")
            elif choice == "3":
                if not is_installed:
                    print_warning(
                        "Nextcloud is not installed yet. Please install it first."
                    )
                    logger.warning("Attempted to start without installation")
                    await async_prompt("Press Enter to continue")
                    continue
                await start_nextcloud()
            elif choice == "4":
                if not is_installed:
                    print_warning(
                        "Nextcloud is not installed yet. Please install it first."
                    )
                    logger.warning("Attempted to stop without installation")
                    await async_prompt("Press Enter to continue")
                    continue
                await stop_nextcloud()
            elif choice == "5":
                await show_nextcloud_info(config)
            elif choice == "6":
                await uninstall_nextcloud()
            elif choice == "7":
                await view_logs()
            elif choice == "8":
                await view_container_logs()
            elif choice == "9":
                if await async_confirm(
                    "This will install Docker using the official Ubuntu method. Proceed?",
                    default=False,
                ):
                    success = await install_docker()
                    if success:
                        print_success("Docker installation completed successfully.")
                    else:
                        print_error("Docker installation failed.")
                    await async_prompt("Press Enter to return to the main menu")
            else:
                print_error(f"Invalid choice: {choice}")
                logger.warning(f"Invalid menu choice: {choice}")
                await async_prompt("Press Enter to continue")
    except Exception as e:
        error_msg = f"An error occurred in the main menu: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print_error(error_msg)
        console.print_exception()
        save_console_output()
        print_warning("An exception has been logged. Press Enter to try to continue...")
        try:
            input()
        except:
            pass


async def async_cleanup() -> None:
    try:
        for task in asyncio.all_tasks():
            if not task.done() and task != asyncio.current_task():
                task.cancel()
        print_message("Cleaning up resources...", NordColors.FROST_3)
        logger.info("Cleaning up resources")
    except Exception as e:
        error_msg = f"Error during cleanup: {e}"
        logger.error(error_msg)
        print_error(error_msg)


async def signal_handler_async(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        warning_msg = f"Process interrupted by {sig_name}"
        logger.warning(warning_msg)
        print_warning(warning_msg)
    except Exception:
        warning_msg = f"Process interrupted by signal {sig}"
        logger.warning(warning_msg)
        print_warning(warning_msg)
    loop = asyncio.get_running_loop()
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()
    await async_cleanup()
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    logger.info("Setting up signal handlers")
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def proper_shutdown_async():
    logger.info("Performing async shutdown")
    try:
        try:
            loop = asyncio.get_running_loop()
            tasks = [
                t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.wait(tasks, timeout=2.0)
                logger.info(f"Cancelled {len(tasks)} pending tasks")
        except RuntimeError:
            logger.info("No running event loop during shutdown")
            pass
    except Exception as e:
        error_msg = f"Error during async shutdown: {e}"
        logger.error(error_msg)
        print_error(error_msg)


def proper_shutdown():
    logger.info("Starting proper shutdown")
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.warning("Event loop already running during shutdown")
                print_warning("Event loop already running during shutdown")
                return
        except RuntimeError:
            logger.info("Creating new event loop for shutdown")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(proper_shutdown_async())
        loop.close()
        logger.info("Shutdown completed successfully")
    except Exception as e:
        error_msg = f"Error during synchronous shutdown: {e}"
        logger.error(error_msg)
        print_error(error_msg)


async def main_async() -> None:
    logger.info(f"Starting {APP_NAME} v{VERSION}")
    try:
        await ensure_config_directory()
        await main_menu_async()
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        logger.error(error_msg, exc_info=True)
        print_error(error_msg)
        console.print_exception()
        save_console_output()
        sys.exit(1)


def main() -> None:
    try:
        logger.info(f"=== {APP_NAME} v{VERSION} starting ===")
        logger.info(f"Log file: {LOG_FILE}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        atexit.register(proper_shutdown)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        warning_msg = "Received keyboard interrupt, shutting down..."
        logger.warning(warning_msg)
        print_warning(warning_msg)
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        logger.error(error_msg, exc_info=True)
        print_error(error_msg)
        console.print_exception()
        save_console_output()
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                logger.info(f"Cancelling {len(tasks)} remaining tasks")
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
            logger.info("Event loop closed")
        except Exception as e:
            error_msg = f"Error during shutdown: {e}"
            logger.error(error_msg)
            print_error(error_msg)
        final_msg = "Application terminated."
        logger.info(final_msg)
        print_message(final_msg, NordColors.FROST_3)


if __name__ == "__main__":
    main()
