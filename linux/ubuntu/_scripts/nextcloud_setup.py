#!/usr/bin/env python3
"""
Nextcloud Docker Installation Script

This script interactively sets up Nextcloud on Ubuntu using Docker and Docker Compose
with PostgreSQL as the database backend. It leverages asynchronous operations and Rich for
a polished CLI experience.
Run with sudo privileges.
"""

import os
import sys
import subprocess
import random
import string
import time
import getpass
import socket
import re
import asyncio
import atexit
import shutil
import signal
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple

try:
    import pyfiglet
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n  pip install rich pyfiglet"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# ------------------------------------------------------------------------------
# Configuration and Constants
# ------------------------------------------------------------------------------
APP_NAME: str = "Nextcloud Docker Installer"
VERSION: str = "1.0.0"
NEXTCLOUD_DEFAULT_PORT: int = 4269  # Nextcloud container will listen on this port
CONFIG_DIR: str = os.path.expanduser("~/.config/nextcloud_installer")
DOCKER_COMPOSE_FILENAME: str = "docker-compose.yml"


# ------------------------------------------------------------------------------
# UI Helper Functions
# ------------------------------------------------------------------------------
def create_header() -> Panel:
    """Create a header panel using pyfiglet and Rich."""
    term_width, _ = shutil.get_terminal_size((80, 24))
    try:
        fig = pyfiglet.Figlet(font="slant", width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    header_text = Text(ascii_art, style="bold cyan")
    return Panel(
        header_text,
        border_style="cyan",
        padding=(1, 2),
        title=Text(f"v{VERSION}", style="bold green"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(text: str, style: str = "cyan", prefix: str = "•") -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, style="red", prefix="✗")


def print_success(message: str) -> None:
    print_message(message, style="green", prefix="✓")


def print_warning(message: str) -> None:
    print_message(message, style="yellow", prefix="⚠")


def print_step(step_number: int, message: str) -> None:
    console.print()  # Blank line
    console.print(f"[bold magenta][Step {step_number}][/bold magenta] {message}")
    console.rule()


# ------------------------------------------------------------------------------
# Async Command Runner
# ------------------------------------------------------------------------------
async def run_command(
    cmd: Any, shell: bool = False, timeout: int = 60
) -> Tuple[int, str]:
    """
    Run a shell command asynchronously.
    If shell is True, the command will be executed through the shell.
    """
    try:
        if shell:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True,
            )
        else:
            if isinstance(cmd, str):
                cmd = cmd.split()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True,
            )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            raise Exception(stderr.strip())
        return proc.returncode, stdout.strip()
    except asyncio.TimeoutError:
        raise Exception("Command timed out.")


# ------------------------------------------------------------------------------
# Installation Helper Functions
# ------------------------------------------------------------------------------
def check_root() -> None:
    """Ensure the script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with sudo privileges.")
        sys.exit(1)


async def update_system_async() -> None:
    """Update system packages."""
    print_step(1, "Updating system packages")
    console.print("Updating package lists...")
    await run_command("apt update", shell=True)
    console.print("Upgrading packages...")
    await run_command("apt upgrade -y", shell=True)
    print_success("System updated successfully!")


async def install_docker_async() -> None:
    """Install Docker if not already installed."""
    print_step(2, "Installing Docker")
    try:
        # Check if Docker is already installed
        await run_command("docker --version", shell=True)
        print_warning("Docker is already installed.")
    except Exception:
        console.print("Installing required packages...")
        await run_command(
            "apt install -y apt-transport-https ca-certificates curl software-properties-common",
            shell=True,
        )
        console.print("Adding Docker's GPG key...")
        await run_command(
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -",
            shell=True,
        )
        console.print("Adding Docker repository...")
        release = (await run_command("lsb_release -cs", shell=True))[1]
        await run_command(
            f'add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu {release} stable"',
            shell=True,
        )
        console.print("Installing Docker...")
        await run_command("apt update", shell=True)
        await run_command("apt install -y docker-ce", shell=True)
        print_success("Docker installed successfully!")
        docker_version = (await run_command("docker --version", shell=True))[1]
        console.print(f"Docker version: [bold green]{docker_version}[/bold green]")


async def install_docker_compose_async() -> None:
    """Install Docker Compose if not already installed."""
    print_step(3, "Installing Docker Compose")
    try:
        await run_command("docker-compose --version", shell=True)
        print_warning("Docker Compose is already installed.")
    except Exception:
        console.print("Downloading Docker Compose...")
        await run_command(
            'curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose',
            shell=True,
        )
        console.print("Setting permissions...")
        await run_command("chmod +x /usr/local/bin/docker-compose", shell=True)
        compose_version = (await run_command("docker-compose --version", shell=True))[1]
        print_success(f"Docker Compose installed successfully: {compose_version}")


def generate_password(length: int = 16) -> str:
    """Generate a random password."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(random.choice(chars) for _ in range(length))


def get_verified_password(prompt_text: str, confirm_prompt: str) -> Optional[str]:
    """Prompt user for a password and verify it."""
    while True:
        password = getpass.getpass(prompt_text)
        if not password:
            return None
        confirm = getpass.getpass(confirm_prompt)
        if password == confirm:
            return password
        print_error("Passwords do not match. Please try again.")


async def async_prompt(prompt_text: str, default: Optional[str] = None) -> str:
    """Asynchronously prompt for input using Rich Prompt."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Prompt.ask(prompt_text, default=default)
    )


async def async_confirm(prompt_text: str, default: bool = False) -> bool:
    """Asynchronously prompt for confirmation using Rich Confirm."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(prompt_text, default=default)
    )


async def async_get_verified_password(prompt_text: str, confirm_prompt: str) -> str:
    """Asynchronously get and verify a password."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: get_verified_password(prompt_text, confirm_prompt)
        or generate_password(),
    )


async def create_nextcloud_directory_async() -> str:
    """Create the installation directory for Nextcloud."""
    print_step(4, "Creating Nextcloud directory")
    home_dir: str = os.path.expanduser("~")
    default_dir: str = f"{home_dir}/nextcloud"
    dir_input: str = (
        await async_prompt(
            f"Enter the directory for Nextcloud installation", default=default_dir
        )
    ).strip()
    nextcloud_dir: str = os.path.abspath(dir_input) if dir_input else default_dir
    data_dir: str = os.path.join(nextcloud_dir, "data")
    console.print(f"Creating directory: [bold]{nextcloud_dir}[/bold]")
    os.makedirs(data_dir, exist_ok=True)
    print_success(f"Directory created: {nextcloud_dir}")
    return nextcloud_dir


async def get_user_credentials_async() -> Dict[str, str]:
    """Prompt the user for PostgreSQL and Nextcloud admin credentials."""
    print_step(5, "Setting up user credentials")
    credentials: Dict[str, str] = {}

    console.print("[yellow]Provide PostgreSQL database credentials:[/yellow]")
    postgres_user: str = (
        await async_prompt("PostgreSQL admin username", default="postgres")
    ).strip() or "postgres"
    credentials["postgres_user"] = postgres_user

    postgres_password: str = await async_get_verified_password(
        "PostgreSQL admin password [leave empty to generate random password]: ",
        "Confirm PostgreSQL admin password: ",
    )
    if postgres_password and not postgres_password.strip():
        postgres_password = generate_password()
        print_success("Generated random PostgreSQL admin password.")
    credentials["postgres_password"] = postgres_password

    postgres_nc_user: str = (
        await async_prompt("PostgreSQL Nextcloud username", default="nextcloud")
    ).strip() or "nextcloud"
    credentials["postgres_nc_user"] = postgres_nc_user

    postgres_nc_password: str = await async_get_verified_password(
        f"PostgreSQL {postgres_nc_user} password [leave empty to generate random password]: ",
        f"Confirm PostgreSQL {postgres_nc_user} password: ",
    )
    if postgres_nc_password and not postgres_nc_password.strip():
        postgres_nc_password = generate_password()
        print_success(f"Generated random PostgreSQL {postgres_nc_user} password.")
    credentials["postgres_nc_password"] = postgres_nc_password

    postgres_db: str = (
        await async_prompt("PostgreSQL database name", default="nextcloud")
    ).strip() or "nextcloud"
    credentials["postgres_db"] = postgres_db

    console.print("\n[yellow]Provide Nextcloud admin credentials:[/yellow]")
    nc_admin: str = (
        await async_prompt("Nextcloud admin username", default="admin")
    ).strip() or "admin"
    credentials["nc_admin"] = nc_admin

    nc_password: str = await async_get_verified_password(
        "Nextcloud admin password [leave empty to generate random password]: ",
        "Confirm Nextcloud admin password: ",
    )
    if nc_password and not nc_password.strip():
        nc_password = generate_password()
        print_success("Generated random Nextcloud admin password.")
    credentials["nc_password"] = nc_password

    return credentials


async def setup_redis_cache_async() -> bool:
    """Ask the user if they want to set up Redis cache."""
    print_step(6, "Redis Cache Setup (Optional)")
    return await async_confirm(
        "Do you want to set up Redis cache for better performance?", default=False
    )


async def create_docker_compose_file_async(
    nextcloud_dir: str, credentials: Dict[str, str], use_redis: bool
) -> Dict[str, Any]:
    """Create the Docker Compose configuration file for Nextcloud."""
    print_step(7, "Creating Docker Compose configuration")
    port_input: str = (
        await async_prompt(
            "Enter the port for Nextcloud", default=str(NEXTCLOUD_DEFAULT_PORT)
        )
    ).strip()
    try:
        port: int = int(port_input) if port_input else NEXTCLOUD_DEFAULT_PORT
    except ValueError:
        port = NEXTCLOUD_DEFAULT_PORT

    docker_compose_path: str = os.path.join(nextcloud_dir, DOCKER_COMPOSE_FILENAME)
    with open(docker_compose_path, "w") as f:
        f.write("version: '3'\n\n")
        f.write("services:\n")
        # PostgreSQL service
        f.write("  db:\n")
        f.write("    image: postgres:14\n")
        f.write("    container_name: nextcloud-postgres\n")
        f.write("    restart: always\n")
        f.write("    volumes:\n")
        f.write("      - db_data:/var/lib/postgresql/data\n")
        f.write("    environment:\n")
        f.write(f"      - POSTGRES_PASSWORD={credentials['postgres_password']}\n")
        f.write(f"      - POSTGRES_USER={credentials['postgres_user']}\n")
        f.write(f"      - POSTGRES_DB={credentials['postgres_db']}\n")
        f.write("    networks:\n")
        f.write("      - nextcloud_network\n\n")
        # Optional Redis service
        if use_redis:
            f.write("  redis:\n")
            f.write("    image: redis:alpine\n")
            f.write("    container_name: nextcloud-redis\n")
            f.write("    restart: always\n")
            f.write("    networks:\n")
            f.write("      - nextcloud_network\n\n")
        # Nextcloud service
        f.write("  app:\n")
        f.write("    image: nextcloud:latest\n")
        f.write("    container_name: nextcloud-app\n")
        f.write("    restart: always\n")
        f.write("    ports:\n")
        f.write(f'      - "{port}:80"\n')
        f.write("    volumes:\n")
        f.write("      - nextcloud_data:/var/www/html\n")
        f.write("      - ./data:/var/www/html/data\n")
        f.write("    environment:\n")
        f.write("      - POSTGRES_HOST=db\n")
        f.write(f"      - POSTGRES_DB={credentials['postgres_db']}\n")
        f.write(f"      - POSTGRES_USER={credentials['postgres_nc_user']}\n")
        f.write(f"      - POSTGRES_PASSWORD={credentials['postgres_nc_password']}\n")
        f.write(f"      - NEXTCLOUD_ADMIN_USER={credentials['nc_admin']}\n")
        f.write(f"      - NEXTCLOUD_ADMIN_PASSWORD={credentials['nc_password']}\n")
        if use_redis:
            f.write("      - REDIS_HOST=redis\n")
        f.write("    depends_on:\n")
        f.write("      - db\n")
        if use_redis:
            f.write("      - redis\n")
        f.write("    networks:\n")
        f.write("      - nextcloud_network\n\n")
        # Networks and volumes
        f.write("networks:\n")
        f.write("  nextcloud_network:\n\n")
        f.write("volumes:\n")
        f.write("  nextcloud_data:\n")
        f.write("  db_data:\n")
    print_success(f"Docker Compose configuration created at: {docker_compose_path}")

    # Save credentials to a secure file
    credentials_file: str = os.path.join(nextcloud_dir, ".nextcloud_credentials")
    with open(credentials_file, "w") as f:
        f.write(f"PostgreSQL admin user: {credentials['postgres_user']}\n")
        f.write(f"PostgreSQL admin password: {credentials['postgres_password']}\n")
        f.write(f"PostgreSQL Nextcloud user: {credentials['postgres_nc_user']}\n")
        f.write(
            f"PostgreSQL Nextcloud password: {credentials['postgres_nc_password']}\n"
        )
        f.write(f"PostgreSQL database: {credentials['postgres_db']}\n")
        f.write(f"Nextcloud admin user: {credentials['nc_admin']}\n")
        f.write(f"Nextcloud admin password: {credentials['nc_password']}\n")
    os.chmod(credentials_file, 0o600)
    print_warning(f"Credentials saved to: {credentials_file} (owner read-only)")
    return {"port": port, "credentials": credentials}


async def create_db_init_script_async(
    nextcloud_dir: str, credentials: Dict[str, str]
) -> str:
    """Create a database initialization script for PostgreSQL."""
    print_step(8, "Creating PostgreSQL DB initialization script")
    db_init_dir: str = os.path.join(nextcloud_dir, "db-init")
    os.makedirs(db_init_dir, exist_ok=True)
    db_init_path: str = os.path.join(db_init_dir, "init-nextcloud-db.sh")
    with open(db_init_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("set -e\n\n")
        f.write(
            'psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL\n'
        )
        f.write(
            f"    CREATE USER {credentials['postgres_nc_user']} WITH PASSWORD '{credentials['postgres_nc_password']}';\n"
        )
        f.write(
            f"    CREATE DATABASE {credentials['postgres_db']} OWNER {credentials['postgres_nc_user']};\n"
        )
        f.write(
            f"    GRANT ALL PRIVILEGES ON DATABASE {credentials['postgres_db']} TO {credentials['postgres_nc_user']};\n"
        )
        f.write("EOSQL\n")
    os.chmod(db_init_path, 0o755)
    print_success(f"Database initialization script created at: {db_init_path}")
    return db_init_dir


async def start_nextcloud_async(nextcloud_dir: str) -> None:
    """Start Nextcloud containers using Docker Compose."""
    print_step(9, "Starting Nextcloud")
    cwd = os.getcwd()
    os.chdir(nextcloud_dir)
    console.print("Starting Docker containers...")
    await run_command("docker-compose up -d", shell=True)
    console.print("Waiting for containers to initialize...")
    await asyncio.sleep(5)
    await run_command("docker-compose ps", shell=True)
    os.chdir(cwd)
    print_success("Nextcloud containers started!")


async def install_watchtower_async() -> None:
    """Set up Watchtower for automatic container updates (Optional)."""
    print_step(10, "Setting up automatic updates with Watchtower (Optional)")
    use_watchtower: bool = await async_confirm(
        "Do you want to set up Watchtower for automatic container updates?",
        default=False,
    )
    if not use_watchtower:
        print_warning("Skipping Watchtower setup.")
        return
    console.print("Installing Watchtower...")
    await run_command(
        "docker run -d --name watchtower --restart always "
        "-v /var/run/docker.sock:/var/run/docker.sock "
        "containrrr/watchtower --cleanup --interval 86400 nextcloud-app nextcloud-postgres",
        shell=True,
    )
    print_success("Watchtower installed for automatic daily updates!")


def print_completion_message(nextcloud_dir: str, config: Dict[str, Any]) -> None:
    """Print final instructions and next steps."""
    print_step(11, "Installation Complete")
    hostname: str = socket.gethostname()
    ip_address: str = socket.gethostbyname(hostname)
    console.print(
        "[bold green]Nextcloud has been successfully installed with Docker![/bold green]\n"
    )
    console.print("Next steps:")
    console.print(f"1. Wait a few minutes for Nextcloud to initialize fully.")
    console.print(
        f"2. Open your web browser and navigate to: [bold]{ip_address}:{config['port']}[/bold]"
    )
    console.print("3. Log in with the following credentials:")
    console.print(f"   - Username: [bold]{config['credentials']['nc_admin']}[/bold]")
    console.print(
        f"   - Password: [bold]{config['credentials']['nc_password']}[/bold]\n"
    )
    console.print("Database information:")
    console.print(f"   - Database type: PostgreSQL")
    console.print(f"   - Database host: db")
    console.print(
        f"   - Database name: [bold]{config['credentials']['postgres_db']}[/bold]"
    )
    console.print(
        f"   - Database user: [bold]{config['credentials']['postgres_nc_user']}[/bold]"
    )
    console.print(
        f"   - Database password: [bold]{config['credentials']['postgres_nc_password']}[/bold]\n"
    )
    console.print("Useful commands:")
    console.print(
        f" - To view container status: cd {nextcloud_dir} && docker-compose ps"
    )
    console.print(
        f" - To view container logs: cd {nextcloud_dir} && docker-compose logs"
    )
    console.print(
        f" - To update containers: cd {nextcloud_dir} && docker-compose pull && docker-compose down && docker-compose up -d"
    )
    console.print(
        f" - To enable maintenance mode: docker exec -u www-data nextcloud-app php occ maintenance:mode --on"
    )
    console.print(
        f" - To disable maintenance mode: docker exec -u www-data nextcloud-app php occ maintenance:mode --off\n"
    )
    console.print(
        f"All credentials are saved in: [italic]{os.path.join(nextcloud_dir, '.nextcloud_credentials')}[/italic]"
    )
    console.print(
        "[bold blue]\nThank you for using the Nextcloud Docker Installer![/bold blue]"
    )


# ------------------------------------------------------------------------------
# Graceful Shutdown and Signal Handling
# ------------------------------------------------------------------------------
async def async_cleanup() -> None:
    """Clean up resources at exit."""
    print_message("Cleaning up resources...", style="cyan")


def proper_shutdown() -> None:
    """Synchronous shutdown handler."""
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(async_cleanup())
    except Exception as e:
        print_error(f"Error during shutdown: {e}")


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig))
        )


async def signal_handler_async(sig: int) -> None:
    try:
        print_warning(f"Process interrupted by signal {sig}. Cleaning up...")
    except Exception:
        print_warning("Process interrupted.")
    await async_cleanup()
    sys.exit(0)


# ------------------------------------------------------------------------------
# Main Execution Flow
# ------------------------------------------------------------------------------
async def main_async() -> None:
    console.print(create_header())
    check_root()
    await update_system_async()
    await install_docker_async()
    await install_docker_compose_async()
    nextcloud_dir: str = await create_nextcloud_directory_async()
    credentials: Dict[str, str] = await get_user_credentials_async()
    use_redis: bool = await setup_redis_cache_async()
    config: Dict[str, Any] = await create_docker_compose_file_async(
        nextcloud_dir, credentials, use_redis
    )
    await create_db_init_script_async(nextcloud_dir, credentials)
    await start_nextcloud_async(nextcloud_dir)
    await install_watchtower_async()
    print_completion_message(nextcloud_dir, config)


def main() -> None:
    """Main entry point."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        atexit.register(proper_shutdown)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Keyboard interrupt received. Exiting...")
        sys.exit(1)
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as e:
            print_error(f"Error during shutdown: {e}")
        loop.close()
        print_message("Application terminated.", style="cyan")


if __name__ == "__main__":
    main()
