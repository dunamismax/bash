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
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet pyyaml"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "Nextcloud Installer"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER") or "sawyer"
DOMAIN_NAME: str = "nextcloud.dunamismax.com"
DOCKER_COMMAND: str = "docker"
DOCKER_COMPOSE_COMMAND: str = "docker compose"
OPERATION_TIMEOUT: int = 60

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/nextcloud_installer")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")

# Docker Compose setup directory
DOCKER_DIR: str = os.path.expanduser("~/nextcloud_docker")
DOCKER_COMPOSE_FILE: str = os.path.join(DOCKER_DIR, "docker-compose.yml")


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
    use_traefik: bool = False
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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# Core Functionality
async def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


async def save_config(config: NextcloudConfig) -> bool:
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


async def load_config() -> NextcloudConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, lambda: json.load(open(CONFIG_FILE, "r"))
            )
            return NextcloudConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return NextcloudConfig()


async def run_command_async(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and capture stdout and stderr."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=OPERATION_TIMEOUT
        )

        # Decode bytes to strings
        stdout = stdout_bytes.decode("utf-8").strip() if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8").strip() if stderr_bytes else ""

        return proc.returncode or 0, stdout, stderr
    except asyncio.TimeoutError:
        raise Exception(f"Command timed out: {' '.join(cmd)}")
    except Exception as e:
        raise Exception(f"Command failed: {e}")


async def check_docker_installed() -> bool:
    """Check if Docker is installed and available."""
    try:
        returncode, stdout, stderr = await run_command_async(
            [DOCKER_COMMAND, "--version"]
        )
        if returncode == 0:
            print_success(f"Docker is installed: {stdout}")
            return True
        else:
            print_error(f"Docker not available: {stderr}")
            return False
    except Exception as e:
        print_error(f"Error checking Docker: {e}")
        return False


async def check_docker_compose_installed() -> bool:
    """Check if Docker Compose is installed and available."""
    global DOCKER_COMPOSE_COMMAND
    try:
        # First try with docker compose (newer Docker versions)
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND.split() + ["--version"]
        )
        if returncode == 0:
            print_success(f"Docker Compose is installed: {stdout}")
            return True

        # If that fails, try with docker-compose (older versions)
        returncode, stdout, stderr = await run_command_async(
            ["docker-compose", "--version"]
        )
        if returncode == 0:
            print_success(f"Docker Compose is installed: {stdout}")
            DOCKER_COMPOSE_COMMAND = "docker-compose"
            return True

        print_error("Docker Compose not available")
        return False
    except Exception as e:
        print_error(f"Error checking Docker Compose: {e}")
        return False


async def check_prerequisites() -> bool:
    """Check all prerequisites for installation."""
    print_section("Checking Prerequisites")

    docker_ok = await check_docker_installed()
    compose_ok = await check_docker_compose_installed()

    if not (docker_ok and compose_ok):
        print_error(
            "Missing required dependencies. Please install Docker and Docker Compose first."
        )
        return False

    return True


async def create_docker_compose_file(config: NextcloudConfig) -> bool:
    """Create the Docker Compose file for Nextcloud and PostgreSQL."""
    try:
        # Ensure the docker directory exists
        os.makedirs(DOCKER_DIR, exist_ok=True)

        # Create required directories
        os.makedirs(config.data_dir, exist_ok=True)
        os.makedirs(config.db_data_dir, exist_ok=True)
        os.makedirs(config.custom_apps_dir, exist_ok=True)
        os.makedirs(config.config_dir, exist_ok=True)
        os.makedirs(config.theme_dir, exist_ok=True)

        # Create the docker-compose.yml file
        compose_config = {
            "version": "3",
            "services": {
                "db": {
                    "image": "postgres:15",
                    "restart": "always",
                    "volumes": [f"{config.db_data_dir}:/var/lib/postgresql/data"],
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
                        f"{config.data_dir}:/var/www/html/data",
                        f"{config.custom_apps_dir}:/var/www/html/custom_apps",
                        f"{config.config_dir}:/var/www/html/config",
                        f"{config.theme_dir}:/var/www/html/themes/custom",
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
                },
            },
        }

        # Add port mapping if not using Traefik
        if not config.use_traefik:
            compose_config["services"]["app"]["ports"] = [f"{config.port}:80"]
        else:
            # Add Traefik labels for reverse proxy
            compose_config["services"]["app"]["labels"] = [
                "traefik.enable=true",
                f"traefik.http.routers.nextcloud.rule=Host(`{config.domain}`)",
                "traefik.http.routers.nextcloud.entrypoints=websecure",
                "traefik.http.routers.nextcloud.tls=true",
                "traefik.http.routers.nextcloud.tls.certresolver=letsencrypt",
            ]
            # Make sure app is on the same network as Traefik
            compose_config["services"]["app"]["networks"] = ["traefik-public"]
            # Add the network definition
            compose_config["networks"] = {"traefik-public": {"external": True}}

        # Write the compose file
        with open(DOCKER_COMPOSE_FILE, "w") as f:
            yaml.dump(compose_config, f, default_flow_style=False)

        print_success(f"Created Docker Compose configuration at {DOCKER_COMPOSE_FILE}")
        return True

    except Exception as e:
        print_error(f"Failed to create Docker Compose file: {e}")
        return False


async def start_docker_containers() -> bool:
    """Start the Docker containers defined in the compose file."""
    try:
        print_step("Starting Nextcloud containers...")

        # Change to the directory containing docker-compose.yml
        os.chdir(DOCKER_DIR)

        # Run docker-compose up -d
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND.split() + ["up", "-d"]
        )

        if returncode == 0:
            print_success("Nextcloud containers started successfully")
            return True
        else:
            print_error(f"Failed to start containers: {stderr}")
            return False

    except Exception as e:
        print_error(f"Error starting containers: {e}")
        return False


async def check_nextcloud_status() -> bool:
    """Check if Nextcloud is running and accessible."""
    try:
        # Check if the containers are running
        os.chdir(DOCKER_DIR)

        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND.split() + ["ps", "-q", "app"]
        )

        if not stdout:
            print_error("Nextcloud container is not running")
            return False

        print_success("Nextcloud container is running")
        return True

    except Exception as e:
        print_error(f"Error checking Nextcloud status: {e}")
        return False


async def stop_docker_containers() -> bool:
    """Stop the Docker containers."""
    try:
        print_step("Stopping Nextcloud containers...")

        # Change to the directory containing docker-compose.yml
        os.chdir(DOCKER_DIR)

        # Run docker-compose down
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND.split() + ["down"]
        )

        if returncode == 0:
            print_success("Nextcloud containers stopped successfully")
            return True
        else:
            print_error(f"Failed to stop containers: {stderr}")
            return False

    except Exception as e:
        print_error(f"Error stopping containers: {e}")
        return False


async def execute_occ_command(command: List[str]) -> Tuple[bool, str]:
    """Execute Nextcloud occ command inside the container."""
    try:
        os.chdir(DOCKER_DIR)

        full_command = (
            DOCKER_COMPOSE_COMMAND.split()
            + ["exec", "--user", "www-data", "app", "php", "occ"]
            + command
        )

        returncode, stdout, stderr = await run_command_async(full_command)

        if returncode == 0:
            return True, stdout
        else:
            return False, stderr

    except Exception as e:
        return False, str(e)


async def async_confirm(message: str, default: bool = False) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


async def async_prompt(message: str, default: str = "") -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Prompt.ask(message, default=default)
    )


async def async_int_prompt(message: str, default: int = 0) -> int:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: IntPrompt.ask(message, default=default)
    )


async def async_password_prompt(message: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: Prompt.ask(message, password=True))


async def configure_nextcloud() -> NextcloudConfig:
    """Interactive configuration for Nextcloud installation."""
    config = await load_config()

    clear_screen()
    console.print(create_header())
    display_panel(
        "Nextcloud Configuration",
        "Please provide the configuration details for your Nextcloud installation",
        NordColors.FROST_2,
    )

    # Domain configuration
    config.domain = await async_prompt(
        f"[bold {NordColors.FROST_2}]Domain name for Nextcloud[/]",
        default=config.domain,
    )

    # Admin account
    config.admin_username = await async_prompt(
        f"[bold {NordColors.FROST_2}]Admin username[/]", default=config.admin_username
    )

    config.admin_password = await async_password_prompt(
        f"[bold {NordColors.FROST_2}]Admin password[/]"
    )

    # Database configuration
    print_section("Database Configuration")
    config.db_name = await async_prompt(
        f"[bold {NordColors.FROST_2}]Database name[/]", default=config.db_name
    )

    config.db_username = await async_prompt(
        f"[bold {NordColors.FROST_2}]Database user[/]", default=config.db_username
    )

    config.db_password = await async_password_prompt(
        f"[bold {NordColors.FROST_2}]Database password[/]"
    )

    # Networking configuration
    print_section("Network Configuration")

    config.use_traefik = await async_confirm(
        f"[bold {NordColors.FROST_2}]Use Traefik reverse proxy?[/]",
        default=config.use_traefik,
    )

    if not config.use_traefik:
        config.port = await async_int_prompt(
            f"[bold {NordColors.FROST_2}]Port to expose Nextcloud on[/]",
            default=config.port,
        )

    config.use_https = await async_confirm(
        f"[bold {NordColors.FROST_2}]Enable HTTPS?[/]", default=config.use_https
    )

    # Data directories
    print_section("Data Directories")

    data_dir_default = os.path.join(os.path.expanduser("~"), "nextcloud_data")
    config.data_dir = await async_prompt(
        f"[bold {NordColors.FROST_2}]Nextcloud data directory[/]",
        default=config.data_dir,
    )

    # Confirm the config
    print_section("Configuration Summary")

    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    table.add_row("Domain", config.domain)
    table.add_row("Admin User", config.admin_username)
    table.add_row("Database Name", config.db_name)
    table.add_row("Database User", config.db_username)
    table.add_row("Using Traefik", "Yes" if config.use_traefik else "No")
    if not config.use_traefik:
        table.add_row("Port", str(config.port))
    table.add_row("HTTPS Enabled", "Yes" if config.use_https else "No")
    table.add_row("Data Directory", config.data_dir)

    console.print(table)
    console.print()

    if not await async_confirm(
        f"[bold {NordColors.FROST_2}]Is this configuration correct?[/]", default=True
    ):
        print_warning("Configuration cancelled. Please start over.")
        return await configure_nextcloud()

    # Save the configuration
    await save_config(config)
    print_success("Configuration saved successfully")

    return config


async def install_nextcloud(config: NextcloudConfig) -> bool:
    """Install Nextcloud with the given configuration."""
    try:
        # Create progress tracker
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
            # Create task for overall progress
            task_id = progress.add_task(
                f"[{NordColors.FROST_2}]Installing Nextcloud...", total=100
            )

            # Check prerequisites
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Checking prerequisites...",
                advance=10,
            )
            if not await check_prerequisites():
                return False

            # Create the Docker Compose file
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Creating Docker configuration...",
                advance=20,
            )
            if not await create_docker_compose_file(config):
                return False

            # Start the containers
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Starting containers...",
                advance=30,
            )
            if not await start_docker_containers():
                return False

            # Wait for containers to be ready
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Waiting for containers to be ready...",
                advance=20,
            )
            await asyncio.sleep(5)  # Give some time for containers to start

            # Check if Nextcloud is running
            progress.update(
                task_id,
                description=f"[{NordColors.FROST_2}]Verifying installation...",
                advance=10,
            )
            if not await check_nextcloud_status():
                return False

            # Complete
            progress.update(
                task_id,
                description=f"[{NordColors.GREEN}]Installation complete!",
                advance=10,
            )

        # Update config with installation status
        config.installation_status = "installed"
        config.installed_at = time.time()
        await save_config(config)

        return True

    except Exception as e:
        print_error(f"Installation failed: {e}")
        return False


async def show_nextcloud_info(config: NextcloudConfig) -> None:
    """Display information about the Nextcloud installation."""
    clear_screen()
    console.print(create_header())

    if config.installation_status != "installed":
        display_panel(
            "Nextcloud Status",
            "Nextcloud is not installed yet. Please install it first.",
            NordColors.YELLOW,
        )
        return

    # Check if containers are running
    running = await check_nextcloud_status()

    # Create the info panel
    status_color = NordColors.GREEN if running else NordColors.RED
    status_text = "Running" if running else "Stopped"

    display_panel(
        "Nextcloud Status",
        f"Status: [{status_color}]{status_text}[/]",
        NordColors.FROST_2,
    )

    # Display access information
    access_url = (
        f"https://{config.domain}" if config.use_https else f"http://{config.domain}"
    )
    if not config.use_traefik:
        access_url = f"http://localhost:{config.port}"

    info_table = Table(show_header=False, box=box.ROUNDED)
    info_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    info_table.add_column("Value", style=NordColors.SNOW_STORM_1)

    info_table.add_row("Access URL", access_url)
    info_table.add_row("Admin User", config.admin_username)
    info_table.add_row("Installed At", time.ctime(config.installed_at or 0))
    info_table.add_row("Data Directory", config.data_dir)
    info_table.add_row("Docker Directory", DOCKER_DIR)

    console.print(info_table)
    console.print()

    # Wait for user to press a key
    await async_prompt("Press Enter to return to the main menu")


async def start_nextcloud() -> bool:
    """Start the Nextcloud containers."""
    clear_screen()
    console.print(create_header())
    display_panel(
        "Starting Nextcloud", "Starting Nextcloud containers...", NordColors.FROST_2
    )

    if await start_docker_containers():
        print_success("Nextcloud started successfully")
        await async_prompt("Press Enter to return to the main menu")
        return True
    else:
        print_error("Failed to start Nextcloud")
        await async_prompt("Press Enter to return to the main menu")
        return False


async def stop_nextcloud() -> bool:
    """Stop the Nextcloud containers."""
    clear_screen()
    console.print(create_header())
    display_panel(
        "Stopping Nextcloud", "Stopping Nextcloud containers...", NordColors.FROST_2
    )

    if await stop_docker_containers():
        print_success("Nextcloud stopped successfully")
        await async_prompt("Press Enter to return to the main menu")
        return True
    else:
        print_error("Failed to stop Nextcloud")
        await async_prompt("Press Enter to return to the main menu")
        return False


async def uninstall_nextcloud() -> bool:
    """Uninstall Nextcloud and remove all data."""
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
        await async_prompt("Press Enter to return to the main menu")
        return False

    # Double confirm for data deletion
    confirm_data = await async_confirm(
        f"[bold {NordColors.RED}]Should we also delete all data directories? This will PERMANENTLY DELETE all your Nextcloud files![/]",
        default=False,
    )

    # Stop containers
    print_step("Stopping Nextcloud containers...")
    await stop_docker_containers()

    # Remove containers and images
    print_step("Removing Docker containers...")
    try:
        os.chdir(DOCKER_DIR)
        returncode, stdout, stderr = await run_command_async(
            DOCKER_COMPOSE_COMMAND.split() + ["down", "--rmi", "all", "--volumes"]
        )
    except Exception as e:
        print_error(f"Error removing containers: {e}")

    # Load config to get data directories
    config = await load_config()

    # Delete data directories if confirmed
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
            except Exception as e:
                print_error(f"Error removing directory {directory}: {e}")

    # Remove Docker directory
    try:
        print_step("Removing Docker configuration...")
        if os.path.exists(DOCKER_COMPOSE_FILE):
            os.remove(DOCKER_COMPOSE_FILE)
            print_success(f"Removed {DOCKER_COMPOSE_FILE}")

        # Don't remove the DOCKER_DIR if we're keeping data
        if confirm_data and os.path.exists(DOCKER_DIR):
            shutil.rmtree(DOCKER_DIR)
            print_success(f"Removed {DOCKER_DIR}")
    except Exception as e:
        print_error(f"Error removing Docker configuration: {e}")

    # Update config
    config.installation_status = "not_installed"
    config.installed_at = None
    await save_config(config)

    print_success("Nextcloud has been uninstalled")
    await async_prompt("Press Enter to return to the main menu")
    return True


async def main_menu_async() -> None:
    """Main menu for the Nextcloud installer."""
    try:
        while True:
            # Load current config
            config = await load_config()

            clear_screen()
            console.print(create_header())

            # Check installation status
            is_installed = config.installation_status == "installed"
            is_running = False

            if is_installed:
                is_running = await check_nextcloud_status()

            # Create status indicator
            status_text = "Not Installed"
            status_color = NordColors.YELLOW

            if is_installed:
                if is_running:
                    status_text = "Running"
                    status_color = NordColors.GREEN
                else:
                    status_text = "Stopped"
                    status_color = NordColors.RED

            # Display menu
            menu_panel = Panel(
                f"Status: [{status_color}]{status_text}[/]\n\n"
                "1. Configure Nextcloud\n"
                "2. Install Nextcloud\n"
                "3. Start Nextcloud\n"
                "4. Stop Nextcloud\n"
                "5. Show Nextcloud Information\n"
                "6. Uninstall Nextcloud\n"
                "q. Quit",
                title="Main Menu",
                border_style=NordColors.FROST_1,
                box=box.ROUNDED,
            )
            console.print(menu_panel)

            choice = await async_prompt("Enter your choice")
            choice = choice.strip().lower()

            if choice in ("q", "quit", "exit"):
                clear_screen()
                console.print(
                    Panel(
                        Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                        border_style=NordColors.FROST_1,
                    )
                )
                break
            elif choice == "1":
                await configure_nextcloud()
            elif choice == "2":
                # Make sure we have config first
                if not config.admin_password or not config.db_password:
                    print_warning("Please configure Nextcloud first")
                    config = await configure_nextcloud()

                await install_nextcloud(config)
            elif choice == "3":
                if not is_installed:
                    print_warning(
                        "Nextcloud is not installed yet. Please install it first."
                    )
                    await async_prompt("Press Enter to continue")
                    continue

                await start_nextcloud()
            elif choice == "4":
                if not is_installed:
                    print_warning(
                        "Nextcloud is not installed yet. Please install it first."
                    )
                    await async_prompt("Press Enter to continue")
                    continue

                await stop_nextcloud()
            elif choice == "5":
                await show_nextcloud_info(config)
            elif choice == "6":
                await uninstall_nextcloud()
            else:
                print_error(f"Invalid choice: {choice}")
                await async_prompt("Press Enter to continue")
    except Exception as e:
        print_error(f"An error occurred in the main menu: {str(e)}")
        console.print_exception()


async def async_cleanup() -> None:
    try:
        # Cancel any pending asyncio tasks
        for task in asyncio.all_tasks():
            if not task.done() and task != asyncio.current_task():
                task.cancel()

        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


async def signal_handler_async(sig: int, frame: Any) -> None:
    """Handle signals in an async-friendly way without creating new event loops."""
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
    """Clean up resources at exit, specifically asyncio tasks."""
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
    """Synchronous wrapper for the async shutdown function.
    This is called by atexit and should be safe to call from any context."""
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
