#!/usr/bin/env python3

"""
Nextcloud Docker Installation Script

This script interactively sets up Nextcloud on Ubuntu using Docker and Docker Compose
with PostgreSQL as the database backend. Designed for use with an existing Caddy reverse
proxy configuration.

Run with sudo privileges.
"""

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
import random
import string
import getpass
import re
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
APP_NAME: str = "nextcloud installer"
VERSION: str = "1.0.0"
DEFAULT_PORT: int = 4269  # Port for Caddy reverse proxy


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
class Credentials:
    """Data class to hold all credentials for the Nextcloud installation"""

    postgres_user: str
    postgres_password: str
    postgres_nc_user: str
    postgres_nc_password: str
    postgres_db: str
    nc_admin: str
    nc_password: str


@dataclass
class NextcloudConfig:
    """Configuration for the Nextcloud installation"""

    dir_path: str
    port: int
    credentials: Credentials
    use_redis: bool = False
    use_watchtower: bool = False


# UI Helper Functions
def clear_screen() -> None:
    """Clear the terminal screen"""
    console.clear()


def create_header() -> Panel:
    """Create a styled header panel for the application"""
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
    """Print formatted message with color and prefix"""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print error message"""
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    """Print success message"""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print warning message"""
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    """Print step message"""
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Print section header"""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display information in a panel"""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# Core Functionality - Made Async
async def run_command_async(
    cmd: Union[List[str], str], check: bool = True, shell: bool = False
) -> Tuple[int, str]:
    """Run a shell command asynchronously and return the result"""
    try:
        if shell:
            # For shell commands, use subprocess.shell=True
            proc = await asyncio.create_subprocess_shell(
                cmd if isinstance(cmd, str) else " ".join(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # For non-shell commands, use subprocess.exec with command parts
            cmd_list = cmd.split() if isinstance(cmd, str) else cmd
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        stdout_bytes, stderr_bytes = await proc.communicate()

        # Manually decode the output from bytes to string
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0 and check:
            raise Exception(stderr)

        return proc.returncode, stdout
    except Exception as e:
        print_error(f"Command failed: {e}")
        if check:
            sys.exit(1)
        return 1, str(e)


async def check_root() -> None:
    """Check if script is run with root privileges"""
    if os.geteuid() != 0:
        print_error("Error: This script must be run with sudo privileges.")
        sys.exit(1)


async def update_system() -> None:
    """Update system packages"""
    print_section("Updating system packages")
    print_step("Updating package lists...")
    await run_command_async("apt update")
    print_step("Upgrading packages...")
    await run_command_async("apt upgrade -y")
    print_success("System updated successfully!")


async def install_docker() -> bool:
    """Install Docker on the system"""
    print_section("Installing Docker")

    # Check if Docker is already installed
    docker_check = await run_command_async("docker --version", check=False)
    if docker_check[0] == 0:
        print_warning("Docker is already installed:")
        console.print(docker_check[1])
        return True

    print_step("Installing required packages...")
    await run_command_async(
        "apt install -y apt-transport-https ca-certificates curl software-properties-common"
    )

    print_step("Adding Docker's GPG key...")
    await run_command_async(
        "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -",
        shell=True,
    )

    print_step("Adding Docker repository...")
    release_result = await run_command_async("lsb_release -cs")
    release = release_result[1]
    await run_command_async(
        f'add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu {release} stable"',
        shell=True,
    )

    print_step("Installing Docker...")
    await run_command_async("apt update")
    await run_command_async("apt install -y docker-ce")

    print_step("Checking Docker status...")
    await run_command_async("systemctl status docker --no-pager")

    # Verify installation
    docker_version = await run_command_async("docker --version")
    print_success(f"Docker installed successfully: {docker_version[1]}")
    return True


async def install_docker_compose() -> bool:
    """Install Docker Compose"""
    print_section("Installing Docker Compose")

    # Check if Docker Compose is already installed
    compose_check = await run_command_async("docker-compose --version", check=False)
    if compose_check[0] == 0:
        print_warning("Docker Compose is already installed:")
        console.print(compose_check[1])
        return True

    print_step("Downloading Docker Compose...")
    await run_command_async(
        'curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose',
        shell=True,
    )

    print_step("Setting permissions...")
    await run_command_async("chmod +x /usr/local/bin/docker-compose")

    # Verify installation
    compose_version = await run_command_async("docker-compose --version")
    print_success(f"Docker Compose installed successfully: {compose_version[1]}")
    return True


def generate_password(length: int = 16) -> str:
    """Generate a random secure password"""
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(random.choice(chars) for _ in range(length))


async def get_verified_password(
    prompt: str, confirm_prompt: str = "Confirm password: "
) -> Optional[str]:
    """Get password with confirmation in an async-friendly way"""
    loop = asyncio.get_running_loop()

    while True:
        # Use the loop to run blocking getpass in executor
        password = await loop.run_in_executor(None, lambda: getpass.getpass(prompt))
        if not password:
            return None

        confirm = await loop.run_in_executor(
            None, lambda: getpass.getpass(confirm_prompt)
        )
        if password == confirm:
            return password

        print_error("Passwords do not match. Please try again.")


async def async_prompt(message: str, default: str = "") -> str:
    """Run Prompt.ask in an async-friendly way"""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: Prompt.ask(message, default=default)
    )
    return result


async def async_confirm(message: str, default: bool = False) -> bool:
    """Run Confirm.ask in an async-friendly way"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


async def create_nextcloud_directory() -> str:
    """Create directory for Nextcloud"""
    print_section("Creating Nextcloud directory")

    home_dir = os.path.expanduser("~")
    nextcloud_dir = await async_prompt(
        f"Enter the directory for Nextcloud installation [default: {home_dir}/nextcloud]: "
    )

    if not nextcloud_dir:
        nextcloud_dir = f"{home_dir}/nextcloud"

    nextcloud_dir = os.path.abspath(nextcloud_dir)
    data_dir = f"{nextcloud_dir}/data"

    print_step(f"Creating directory: {nextcloud_dir}")
    os.makedirs(data_dir, exist_ok=True)

    print_success(f"Directory created: {nextcloud_dir}")
    return nextcloud_dir


async def get_user_credentials() -> Credentials:
    """Get and verify credentials for both Nextcloud and PostgreSQL"""
    print_section("Setting up user credentials")

    # PostgreSQL credentials
    print_warning("Please provide PostgreSQL database credentials:")

    # PostgreSQL admin user
    postgres_user = await async_prompt(
        "PostgreSQL admin username [default: postgres]: "
    )
    if not postgres_user:
        postgres_user = "postgres"

    # PostgreSQL admin password
    postgres_password = await get_verified_password(
        "PostgreSQL admin password [leave empty to generate random password]: ",
        "Confirm PostgreSQL admin password: ",
    )
    if not postgres_password:
        postgres_password = generate_password()
        print_success("Generated random PostgreSQL admin password.")

    # PostgreSQL Nextcloud user
    postgres_nc_user = await async_prompt(
        "PostgreSQL Nextcloud username [default: nextcloud]: "
    )
    if not postgres_nc_user:
        postgres_nc_user = "nextcloud"

    # PostgreSQL Nextcloud user password
    postgres_nc_password = await get_verified_password(
        f"PostgreSQL {postgres_nc_user} password [leave empty to generate random password]: ",
        f"Confirm PostgreSQL {postgres_nc_user} password: ",
    )
    if not postgres_nc_password:
        postgres_nc_password = generate_password()
        print_success(f"Generated random PostgreSQL {postgres_nc_user} password.")

    # PostgreSQL database name
    postgres_db = await async_prompt("PostgreSQL database name [default: nextcloud]: ")
    if not postgres_db:
        postgres_db = "nextcloud"

    # Nextcloud admin credentials
    print_warning("\nPlease provide Nextcloud admin credentials:")

    # Nextcloud admin username
    nc_admin = await async_prompt("Nextcloud admin username [default: admin]: ")
    if not nc_admin:
        nc_admin = "admin"

    # Nextcloud admin password
    nc_password = await get_verified_password(
        "Nextcloud admin password [leave empty to generate random password]: ",
        "Confirm Nextcloud admin password: ",
    )
    if not nc_password:
        nc_password = generate_password()
        print_success("Generated random Nextcloud admin password.")

    return Credentials(
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_nc_user=postgres_nc_user,
        postgres_nc_password=postgres_nc_password,
        postgres_db=postgres_db,
        nc_admin=nc_admin,
        nc_password=nc_password,
    )


async def create_docker_compose_file(
    nextcloud_dir: str, credentials: Credentials, use_redis: bool = False
) -> Dict[str, Any]:
    """Create Docker Compose configuration file"""
    print_section("Creating Docker Compose configuration")

    # Use the default port for Caddy reverse proxy
    port = DEFAULT_PORT
    print_step(f"Configuring Nextcloud to use port {port} for Caddy reverse proxy")

    # Create docker-compose.yml file
    docker_compose_path = f"{nextcloud_dir}/docker-compose.yml"

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
        f.write(f"      - POSTGRES_PASSWORD={credentials.postgres_password}\n")
        f.write(f"      - POSTGRES_USER={credentials.postgres_user}\n")
        f.write(f"      - POSTGRES_DB={credentials.postgres_db}\n")
        f.write("    networks:\n")
        f.write("      - nextcloud_network\n\n")

        # Redis service (optional)
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
        f.write(f"      - {port}:80\n")
        f.write("    volumes:\n")
        f.write("      - nextcloud_data:/var/www/html\n")
        f.write("      - ./data:/var/www/html/data\n")
        f.write("    environment:\n")
        f.write("      - POSTGRES_HOST=db\n")
        f.write(f"      - POSTGRES_DB={credentials.postgres_db}\n")
        f.write(f"      - POSTGRES_USER={credentials.postgres_nc_user}\n")
        f.write(f"      - POSTGRES_PASSWORD={credentials.postgres_nc_password}\n")
        f.write(f"      - NEXTCLOUD_ADMIN_USER={credentials.nc_admin}\n")
        f.write(f"      - NEXTCLOUD_ADMIN_PASSWORD={credentials.nc_password}\n")

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

    print_success(f"Docker Compose configuration created: {docker_compose_path}")

    # Save credentials to a secure file
    credentials_file = f"{nextcloud_dir}/.nextcloud_credentials"
    with open(credentials_file, "w") as f:
        f.write(f"PostgreSQL admin user: {credentials.postgres_user}\n")
        f.write(f"PostgreSQL admin password: {credentials.postgres_password}\n")
        f.write(f"PostgreSQL Nextcloud user: {credentials.postgres_nc_user}\n")
        f.write(f"PostgreSQL Nextcloud password: {credentials.postgres_nc_password}\n")
        f.write(f"PostgreSQL database: {credentials.postgres_db}\n")
        f.write(f"Nextcloud admin user: {credentials.nc_admin}\n")
        f.write(f"Nextcloud admin password: {credentials.nc_password}\n")

    os.chmod(credentials_file, 0o600)  # Set secure permissions
    print_warning(
        f"Credentials saved to: {credentials_file} (read permissions for owner only)"
    )

    return {"port": port, "credentials": credentials}


async def start_nextcloud(nextcloud_dir: str) -> None:
    """Start Nextcloud containers with progress indication"""
    print_section("Starting Nextcloud")

    os.chdir(nextcloud_dir)

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
            f"[{NordColors.FROST_2}]Starting Docker containers...", total=100
        )

        # Simulate progress while actually starting containers
        progress.update(task_id, completed=10)
        await run_command_async("docker-compose up -d")
        progress.update(task_id, completed=70)

        # Check container status
        await asyncio.sleep(5)  # Give containers time to start
        await run_command_async("docker-compose ps")
        progress.update(task_id, completed=100)

    print_success("Nextcloud containers started!")


async def setup_redis_cache() -> bool:
    """Ask user if they want to set up Redis cache"""
    print_section("Setting up Redis cache (Optional)")

    setup_redis = await async_confirm(
        "Do you want to set up Redis cache for better performance?", default=False
    )
    return setup_redis


async def install_watchtower() -> bool:
    """Install Watchtower for automatic container updates"""
    print_section("Setting up automatic updates (Optional)")

    setup_watchtower = await async_confirm(
        "Do you want to set up Watchtower for automatic container updates?",
        default=False,
    )
    if not setup_watchtower:
        print_warning("Skipping Watchtower setup.")
        return False

    print_step("Installing Watchtower...")
    await run_command_async(
        "docker run -d --name watchtower --restart always "
        "-v /var/run/docker.sock:/var/run/docker.sock "
        "containrrr/watchtower --cleanup --interval 86400 nextcloud-app nextcloud-postgres"
    )

    print_success("Watchtower installed for automatic daily updates!")
    return True


async def print_completion_message(nextcloud_dir: str, config: Dict[str, Any]) -> None:
    """Print completion message with next steps"""
    hostname = socket.gethostname()
    try:
        ip_address = socket.gethostbyname(hostname)
    except:
        ip_address = "your.server.ip"

    print_section("Installation Complete")

    completion_message = f"""
Nextcloud has been successfully installed with Docker!

Next steps:
1. Wait a few minutes for Nextcloud to initialize fully
2. Access Nextcloud through your Caddy reverse proxy
3. Log in with the following credentials:
   - Username: {config["credentials"].nc_admin}
   - Password: {config["credentials"].nc_password}

Database information:
   - Database type: PostgreSQL
   - Database host: db
   - Database name: {config["credentials"].postgres_db}
   - Database user: {config["credentials"].postgres_nc_user}
   - Database password: {config["credentials"].postgres_nc_password}

Useful commands:
- To view container status: cd {nextcloud_dir} && docker-compose ps
- To view container logs: cd {nextcloud_dir} && docker-compose logs
- To update containers: cd {nextcloud_dir} && docker-compose pull && docker-compose down && docker-compose up -d
- To enable maintenance mode: docker exec -u www-data nextcloud-app php occ maintenance:mode --on
- To disable maintenance mode: docker exec -u www-data nextcloud-app php occ maintenance:mode --off

Credentials:
- All your credentials are saved in: {nextcloud_dir}/.nextcloud_credentials

Thank you for using the Nextcloud Docker installation script!
"""

    display_panel("Installation Complete", completion_message, NordColors.GREEN)


async def async_cleanup() -> None:
    """Cleanup function for atexit and signal handling"""
    try:
        # Cancel any pending asyncio tasks
        for task in asyncio.all_tasks():
            if not task.done() and task != asyncio.current_task():
                task.cancel()

        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


async def signal_handler_async(sig: int, frame: Any) -> None:
    """Handle signals in an async-friendly way"""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current running loop
    loop = asyncio.get_running_loop()

    # Cancel all tasks except the current one
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()

    # Clean up resources
    await async_cleanup()

    # Stop the loop
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers that work with the main event loop"""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


async def proper_shutdown_async() -> None:
    """Clean up resources at exit, specifically asyncio tasks"""
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


def proper_shutdown() -> None:
    """Synchronous wrapper for the async shutdown function"""
    try:
        # Check if there's a running loop first
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If a loop is already running, we can't run a new one
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
    """Main async function to run the installation script"""
    try:
        # Display header
        clear_screen()
        console.print(create_header())
        display_panel(
            "Nextcloud Docker Installer",
            "This script will set up Nextcloud with Docker and PostgreSQL",
            NordColors.FROST_2,
        )

        # Check for root privileges
        await check_root()

        # Update system
        await update_system()

        # Install Docker
        await install_docker()

        # Install Docker Compose
        await install_docker_compose()

        # Create directory for Nextcloud
        nextcloud_dir = await create_nextcloud_directory()

        # Get user credentials
        credentials = await get_user_credentials()

        # Ask about Redis
        use_redis = await setup_redis_cache()

        # Create Docker Compose configuration
        config = await create_docker_compose_file(nextcloud_dir, credentials, use_redis)

        # Start Nextcloud
        await start_nextcloud(nextcloud_dir)

        # Setup Watchtower (optional)
        use_watchtower = await install_watchtower()

        # Print completion message
        await print_completion_message(nextcloud_dir, config)

    except KeyboardInterrupt:
        print_warning("\n\nInstallation interrupted. Exiting.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nAn error occurred: {e}")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    """Main entry point of the application"""
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
