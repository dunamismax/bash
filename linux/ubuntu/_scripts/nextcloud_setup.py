#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import tempfile
import shutil
import json
import asyncio
import atexit
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast

try:
    import pyfiglet
    import requests
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        DownloadColumn,
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
        "pip install rich pyfiglet requests"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "Nextcloud Setup"
VERSION: str = "1.0.0"
DOWNLOAD_URL: str = "https://download.nextcloud.com/server/releases/latest.zip"
OPERATION_TIMEOUT: int = 60
DEFAULT_WEB_USER: str = "www-data"
DEFAULT_WEBSERVER: str = "apache2"
DEFAULT_DB_TYPE: str = "pgsql"
DEFAULT_PHP_VERSION: str = "8.1"
TEMP_DIR: str = tempfile.gettempdir()

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/nextcloud_setup")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")


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
    admin_user: str = "admin"
    admin_pass: str = ""
    data_dir: str = "/var/www/nextcloud/data"
    db_name: str = "nextcloud"
    db_user: str = "nextcloud"
    db_pass: str = ""
    db_host: str = "localhost"
    db_port: str = "5432"
    db_type: str = DEFAULT_DB_TYPE
    webserver: str = DEFAULT_WEBSERVER
    php_version: str = DEFAULT_PHP_VERSION
    install_dir: str = "/var/www/nextcloud"
    domain: str = "localhost"
    use_https: bool = False
    cert_file: str = ""
    key_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Global variables
_background_task = None


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
def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: NextcloudConfig) -> bool:
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> NextcloudConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return NextcloudConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return NextcloudConfig()


def run_command(cmd: List[str], sudo: bool = False) -> Tuple[int, str, str]:
    """
    Run a command and return the return code, stdout, and stderr.
    Optionally run the command with sudo.
    """
    try:
        if sudo and os.geteuid() != 0:
            cmd = ["sudo"] + cmd

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OPERATION_TIMEOUT,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        raise Exception("Command timed out.")


def download_package(url: str, destination: str) -> bool:
    """
    Download the Nextcloud zip package from the given URL and save it to 'destination'.
    A Rich progress bar displays the download progress.
    """
    console.print(
        f"[bold {NordColors.FROST_2}]Starting download of Nextcloud package...[/]"
    )
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_length = int(response.headers.get("content-length", 0))
            with (
                open(destination, "wb") as zip_file,
                Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    " • ",
                    DownloadColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress,
            ):
                task = progress.add_task("Downloading", total=total_length)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        zip_file.write(chunk)
                        progress.update(task, advance=len(chunk))
        console.print(f"[bold {NordColors.GREEN}]Download completed successfully.[/]")
        return True
    except Exception as err:
        print_error(f"Download failed: {err}")
        return False


def find_problematic_repos() -> List[Tuple[str, str]]:
    """
    Scan apt sources files to find problematic repositories.
    Returns a list of tuples containing (file_path, problematic_line).
    """
    problematic_repos = []
    sources_dir = "/etc/apt/sources.list.d"
    sources_file = "/etc/apt/sources.list"

    # Check main sources.list file
    try:
        if os.path.exists(sources_file):
            returncode, stdout, _ = run_command(["cat", sources_file], sudo=True)
            if returncode == 0:
                for line in stdout.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Look for problematic Debian repositories
                        if (
                            ("debian" in line.lower() and "trixie" in line.lower())
                            or "NO_PUBKEY" in line
                            or "InRelease" in line
                            and "not signed" in line
                        ):
                            problematic_repos.append((sources_file, line))
    except Exception as e:
        print_warning(f"Error checking main sources file: {e}")

    # Check sources.list.d directory
    try:
        if os.path.exists(sources_dir):
            returncode, stdout, _ = run_command(["ls", sources_dir], sudo=True)
            if returncode == 0:
                for filename in stdout.splitlines():
                    if not filename.endswith(".list"):
                        continue
                    file_path = os.path.join(sources_dir, filename)
                    returncode, file_content, _ = run_command(
                        ["cat", file_path], sudo=True
                    )
                    if returncode == 0:
                        for line in file_content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                # Look for problematic repositories
                                if (
                                    (
                                        "debian" in line.lower()
                                        and "trixie" in line.lower()
                                    )
                                    or "NO_PUBKEY" in line
                                    or "InRelease" in line
                                    and "not signed" in line
                                ):
                                    problematic_repos.append((file_path, line))
    except Exception as e:
        print_warning(f"Error checking sources directory: {e}")

    return problematic_repos


def fix_repository_issues() -> bool:
    """
    Find and fix problematic repositories.
    Returns True if successful, False otherwise.
    """
    print_section("Checking for Repository Issues")

    problematic_repos = find_problematic_repos()

    if not problematic_repos:
        print_success("No problematic repositories found.")
        return True

    print_warning(f"Found {len(problematic_repos)} problematic repository entries:")

    for i, (file_path, repo_line) in enumerate(problematic_repos, 1):
        console.print(f"[{NordColors.YELLOW}]{i}. File: {file_path}[/]")
        console.print(f"[{NordColors.YELLOW}]   Entry: {repo_line}[/]")

    fix_repos = Confirm.ask(
        "\nWould you like to disable these problematic repositories?", default=True
    )

    if not fix_repos:
        print_warning(
            "Continuing without fixing repository issues. This might cause problems later."
        )
        return False

    success = True
    for file_path, repo_line in problematic_repos:
        try:
            # Create a backup of the file
            backup_path = f"{file_path}.bak"
            print_step(f"Creating backup of {file_path}")
            returncode, _, stderr = run_command(
                ["cp", file_path, backup_path], sudo=True
            )
            if returncode != 0:
                print_error(f"Failed to create backup of {file_path}: {stderr}")
                success = False
                continue

            # Escape special characters for sed
            escaped_line = (
                repo_line.replace("/", "\\/").replace("&", "\\&").replace(".", "\\.")
            )

            # Comment out the problematic line
            print_step(f"Disabling problematic repository in {file_path}")
            sedcmd = f"sed -i 's/{escaped_line}/# {escaped_line} # Disabled by Nextcloud setup script/g' {file_path}"
            returncode, _, stderr = run_command(["bash", "-c", sedcmd], sudo=True)

            if returncode == 0:
                print_success(f"Successfully disabled repository in {file_path}")
            else:
                print_error(f"Failed to disable repository in {file_path}: {stderr}")
                success = False
        except Exception as e:
            print_error(f"Error processing {file_path}: {e}")
            success = False

    if success:
        print_step("Updating package lists after repository changes...")
        returncode, _, stderr = run_command(["apt", "update"], sudo=True)
        if returncode != 0:
            print_warning(f"Package list update still has issues: {stderr}")
            print_warning(
                "Continuing with installation, but some packages might not be available."
            )

    return True


def install_dependencies() -> bool:
    """
    Install all required dependencies for Nextcloud using apt.
    First checks for and fixes problematic repositories.
    """
    print_section("Installing Dependencies")

    # Check for and fix repository issues before installing dependencies
    fix_repository_issues()

    dependencies = [
        "apache2",
        "postgresql",
        "postgresql-contrib",
        "libapache2-mod-php",
        f"php{DEFAULT_PHP_VERSION}",
        f"php{DEFAULT_PHP_VERSION}-gd",
        f"php{DEFAULT_PHP_VERSION}-xml",
        f"php{DEFAULT_PHP_VERSION}-mbstring",
        f"php{DEFAULT_PHP_VERSION}-zip",
        f"php{DEFAULT_PHP_VERSION}-pgsql",
        f"php{DEFAULT_PHP_VERSION}-curl",
        f"php{DEFAULT_PHP_VERSION}-intl",
        f"php{DEFAULT_PHP_VERSION}-gmp",
        f"php{DEFAULT_PHP_VERSION}-bcmath",
        f"php{DEFAULT_PHP_VERSION}-imagick",
        "unzip",
        "curl",
    ]

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
            # Update package lists
            task_update = progress.add_task(
                f"[{NordColors.FROST_2}]Updating package lists...", total=1
            )

            _, stdout, stderr = run_command(["apt", "update"], sudo=True)
            if stderr and "error" in stderr.lower():
                print_warning(
                    f"Package list update has warnings/errors, but continuing: {stderr}"
                )

            progress.update(task_update, completed=1)

            # Install dependencies
            task_install = progress.add_task(
                f"[{NordColors.FROST_2}]Installing dependencies...",
                total=len(dependencies),
            )

            for dependency in dependencies:
                progress.update(
                    task_install,
                    description=f"[{NordColors.FROST_2}]Installing {dependency}...",
                )

                returncode, stdout, stderr = run_command(
                    ["apt", "install", "-y", dependency], sudo=True
                )

                if returncode != 0:
                    print_error(f"Failed to install {dependency}: {stderr}")
                    print_warning(
                        "Continuing with installation. Some features might not work properly."
                    )

                progress.advance(task_install)

        print_success("Dependencies installation completed.")
        return True
    except Exception as e:
        print_error(f"Error installing dependencies: {e}")
        return False


def setup_postgresql(config: NextcloudConfig) -> bool:
    """
    Set up the PostgreSQL database for Nextcloud.
    """
    print_section("Setting up PostgreSQL Database")

    try:
        # Ensure PostgreSQL is running
        returncode, _, _ = run_command(
            ["systemctl", "is-active", "postgresql"], sudo=True
        )
        if returncode != 0:
            print_step("Starting PostgreSQL service...")
            returncode, _, stderr = run_command(
                ["systemctl", "start", "postgresql"], sudo=True
            )
            if returncode != 0:
                print_error(f"Failed to start PostgreSQL: {stderr}")
                return False

        # Create database user
        print_step(f"Creating database user '{config.db_user}'...")
        create_user_cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-c",
            f"CREATE USER {config.db_user} WITH PASSWORD '{config.db_pass}';",
        ]
        returncode, _, stderr = run_command(create_user_cmd)
        if returncode != 0 and "already exists" not in stderr:
            print_error(f"Failed to create database user: {stderr}")
            return False

        # Create database
        print_step(f"Creating database '{config.db_name}'...")
        create_db_cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-c",
            f"CREATE DATABASE {config.db_name} OWNER {config.db_user};",
        ]
        returncode, _, stderr = run_command(create_db_cmd)
        if returncode != 0 and "already exists" not in stderr:
            print_error(f"Failed to create database: {stderr}")
            return False

        # Grant privileges
        print_step("Setting database permissions...")
        grant_cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-c",
            f"GRANT ALL PRIVILEGES ON DATABASE {config.db_name} TO {config.db_user};",
        ]
        returncode, _, stderr = run_command(grant_cmd)
        if returncode != 0:
            print_error(f"Failed to grant database privileges: {stderr}")
            return False

        print_success("PostgreSQL setup completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error setting up PostgreSQL: {e}")
        return False


def setup_apache(config: NextcloudConfig) -> bool:
    """
    Configure Apache for Nextcloud.
    """
    print_section("Configuring Apache Web Server")

    try:
        # Enable required Apache modules
        modules = ["rewrite", "headers", "env", "dir", "mime", "ssl"]

        for module in modules:
            print_step(f"Enabling Apache module: {module}")
            returncode, _, stderr = run_command(["a2enmod", module], sudo=True)
            if returncode != 0:
                print_error(f"Failed to enable Apache module {module}: {stderr}")
                return False

        # Create Apache site configuration
        site_config = f"""<VirtualHost *:80>
    ServerName {config.domain}
    DocumentRoot {config.install_dir}

    <Directory {config.install_dir}>
        Options FollowSymlinks
        AllowOverride All
        Require all granted
        <IfModule mod_dav.c>
            Dav off
        </IfModule>
    </Directory>

    ErrorLog ${{APACHE_LOG_DIR}}/nextcloud_error.log
    CustomLog ${{APACHE_LOG_DIR}}/nextcloud_access.log combined
</VirtualHost>
"""

        # Create temporary file for the configuration
        config_file = tempfile.NamedTemporaryFile(delete=False, mode="w")
        config_file.write(site_config)
        config_file.close()

        # Copy configuration to Apache sites directory
        returncode, _, stderr = run_command(
            ["cp", config_file.name, "/etc/apache2/sites-available/nextcloud.conf"],
            sudo=True,
        )

        if returncode != 0:
            print_error(f"Failed to create Apache site configuration: {stderr}")
            os.unlink(config_file.name)
            return False

        os.unlink(config_file.name)

        # Enable the site
        print_step("Enabling Nextcloud site in Apache...")
        returncode, _, stderr = run_command(["a2ensite", "nextcloud.conf"], sudo=True)
        if returncode != 0:
            print_error(f"Failed to enable Apache site: {stderr}")
            return False

        # Restart Apache
        print_step("Restarting Apache service...")
        returncode, _, stderr = run_command(
            ["systemctl", "restart", "apache2"], sudo=True
        )
        if returncode != 0:
            print_error(f"Failed to restart Apache: {stderr}")
            return False

        print_success("Apache configuration completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error configuring Apache: {e}")
        return False


def extract_nextcloud(zip_path: str, install_dir: str) -> bool:
    """
    Extract the Nextcloud zip file to the installation directory.
    """
    print_section("Extracting Nextcloud Files")

    try:
        temp_extract_dir = os.path.join(TEMP_DIR, "nextcloud_extract")
        os.makedirs(temp_extract_dir, exist_ok=True)

        # Extract to temporary directory first
        print_step(f"Extracting files to temporary location...")
        returncode, _, stderr = run_command(
            ["unzip", "-q", zip_path, "-d", temp_extract_dir]
        )
        if returncode != 0:
            print_error(f"Failed to extract Nextcloud archive: {stderr}")
            return False

        # Create installation directory if it doesn't exist
        print_step(f"Creating installation directory at {install_dir}...")
        returncode, _, stderr = run_command(["mkdir", "-p", install_dir], sudo=True)
        if returncode != 0:
            print_error(f"Failed to create installation directory: {stderr}")
            return False

        # Move files to installation directory
        print_step("Moving files to installation directory...")
        src_dir = os.path.join(temp_extract_dir, "nextcloud")
        returncode, _, stderr = run_command(
            ["cp", "-a", f"{src_dir}/.", install_dir], sudo=True
        )
        if returncode != 0:
            print_error(f"Failed to move files to installation directory: {stderr}")
            return False

        # Set proper permissions
        print_step("Setting file permissions...")
        returncode, _, stderr = run_command(
            ["chown", "-R", f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}", install_dir],
            sudo=True,
        )
        if returncode != 0:
            print_error(f"Failed to set file permissions: {stderr}")
            return False

        # Clean up temporary directory
        shutil.rmtree(temp_extract_dir, ignore_errors=True)

        print_success("Nextcloud files extracted successfully.")
        return True
    except Exception as e:
        print_error(f"Error extracting Nextcloud files: {e}")
        return False


def configure_nextcloud(config: NextcloudConfig) -> bool:
    """
    Configure Nextcloud using the occ command.
    """
    print_section("Configuring Nextcloud")

    try:
        # Create data directory if it doesn't exist
        print_step(f"Creating data directory at {config.data_dir}...")
        returncode, _, stderr = run_command(["mkdir", "-p", config.data_dir], sudo=True)
        if returncode != 0:
            print_error(f"Failed to create data directory: {stderr}")
            return False

        # Set proper permissions on data directory
        returncode, _, stderr = run_command(
            ["chown", "-R", f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}", config.data_dir],
            sudo=True,
        )
        if returncode != 0:
            print_error(f"Failed to set data directory permissions: {stderr}")
            return False

        # Run Nextcloud installation command
        print_step("Running Nextcloud installation...")
        occ_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "maintenance:install",
            "--database",
            config.db_type,
            "--database-name",
            config.db_name,
            "--database-user",
            config.db_user,
            "--database-pass",
            config.db_pass,
            "--database-host",
            config.db_host,
            "--database-port",
            config.db_port,
            "--admin-user",
            config.admin_user,
            "--admin-pass",
            config.admin_pass,
            "--data-dir",
            config.data_dir,
        ]

        returncode, stdout, stderr = run_command(occ_cmd)
        if returncode != 0:
            print_error(f"Failed to configure Nextcloud: {stderr}")
            return False

        # Set trusted domain
        print_step(f"Setting trusted domain to {config.domain}...")
        trusted_domain_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "trusted_domains",
            "1",
            "--value",
            config.domain,
        ]

        returncode, _, stderr = run_command(trusted_domain_cmd)
        if returncode != 0:
            print_error(f"Failed to set trusted domain: {stderr}")
            return False

        print_success("Nextcloud configuration completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error configuring Nextcloud: {e}")
        return False


def optimize_nextcloud(config: NextcloudConfig) -> bool:
    """
    Apply optimizations to Nextcloud.
    """
    print_section("Optimizing Nextcloud")

    try:
        # Enable caching
        print_step("Enabling memory cache...")
        cache_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "memcache.local",
            "--value",
            "\\OC\\Memcache\\APCu",
        ]

        returncode, _, stderr = run_command(cache_cmd)
        if returncode != 0:
            print_error(f"Failed to enable memory cache: {stderr}")
            return False

        # Enable opcache in php.ini
        php_ini_path = f"/etc/php/{config.php_version}/apache2/php.ini"

        # Create PHP optimization settings
        php_settings = """
; Nextcloud recommended PHP settings
opcache.enable=1
opcache.interned_strings_buffer=8
opcache.max_accelerated_files=10000
opcache.memory_consumption=128
opcache.save_comments=1
opcache.revalidate_freq=1
"""

        # Create temporary file for PHP settings
        php_settings_file = tempfile.NamedTemporaryFile(delete=False, mode="w")
        php_settings_file.write(php_settings)
        php_settings_file.close()

        # Append settings to php.ini
        print_step("Optimizing PHP settings...")
        returncode, _, stderr = run_command(
            ["bash", "-c", f"cat {php_settings_file.name} >> {php_ini_path}"], sudo=True
        )
        if returncode != 0:
            print_error(f"Failed to update PHP settings: {stderr}")
            os.unlink(php_settings_file.name)
            return False

        os.unlink(php_settings_file.name)

        # Restart Apache to apply PHP changes
        print_step("Restarting Apache to apply changes...")
        returncode, _, stderr = run_command(
            ["systemctl", "restart", "apache2"], sudo=True
        )
        if returncode != 0:
            print_error(f"Failed to restart Apache: {stderr}")
            return False

        print_success("Nextcloud optimization completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error optimizing Nextcloud: {e}")
        return False


def setup_nextcloud(config: NextcloudConfig) -> bool:
    """
    Perform the complete Nextcloud setup process.
    """
    # Define zip file path
    zip_path = os.path.join(TEMP_DIR, "nextcloud-latest.zip")

    # Download Nextcloud
    if not download_package(DOWNLOAD_URL, zip_path):
        return False

    # Install dependencies
    if not install_dependencies():
        return False

    # Set up PostgreSQL
    if not setup_postgresql(config):
        return False

    # Extract Nextcloud
    if not extract_nextcloud(zip_path, config.install_dir):
        return False

    # Set up Apache
    if not setup_apache(config):
        return False

    # Configure Nextcloud
    if not configure_nextcloud(config):
        return False

    # Optimize Nextcloud
    if not optimize_nextcloud(config):
        return False

    # Clean up
    try:
        os.remove(zip_path)
    except Exception:
        pass

    return True


def get_nextcloud_config() -> NextcloudConfig:
    """
    Get Nextcloud configuration through interactive prompts.
    """
    config = NextcloudConfig()

    print_section("Nextcloud Configuration")

    # Admin account
    config.admin_user = Prompt.ask(
        "[bold]Enter Nextcloud admin username[/]", default="admin"
    )
    config.admin_pass = Prompt.ask(
        "[bold]Enter Nextcloud admin password[/]", password=True
    )

    # Database configuration
    print_section("Database Configuration")
    config.db_name = Prompt.ask("[bold]Enter database name[/]", default="nextcloud")
    config.db_user = Prompt.ask("[bold]Enter database user[/]", default="nextcloud")
    config.db_pass = Prompt.ask("[bold]Enter database password[/]", password=True)
    config.db_host = Prompt.ask("[bold]Enter database host[/]", default="localhost")
    config.db_port = Prompt.ask("[bold]Enter database port[/]", default="5432")

    # Server configuration
    print_section("Server Configuration")
    config.domain = Prompt.ask(
        "[bold]Enter domain name for Nextcloud[/]", default="localhost"
    )

    use_custom_dir = Confirm.ask(
        "[bold]Use custom installation directory?[/]", default=False
    )
    if use_custom_dir:
        config.install_dir = Prompt.ask(
            "[bold]Enter installation directory[/]", default="/var/www/nextcloud"
        )
        config.data_dir = Prompt.ask(
            "[bold]Enter data directory[/]", default=f"{config.install_dir}/data"
        )

    return config


def cleanup() -> None:
    try:
        # Cancel any pending asyncio tasks
        for task in asyncio.all_tasks(asyncio.get_event_loop_policy().get_event_loop()):
            if not task.done():
                task.cancel()

        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current event loop if one exists
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule the cleanup to run properly in the loop
            loop.call_soon_threadsafe(cleanup)
            # Give a moment for cleanup to run
            time.sleep(0.2)
        else:
            cleanup()
    except Exception:
        # If we can't get the loop or it's closed already, just attempt cleanup directly
        cleanup()

    sys.exit(128 + sig)


def proper_shutdown():
    """Clean up resources at exit, specifically asyncio tasks."""
    global _background_task

    # Cancel any pending asyncio tasks
    try:
        if _background_task and not _background_task.done():
            _background_task.cancel()

        # Get the current event loop and cancel all tasks
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()

                # Run the loop briefly to process cancellations
                if tasks and loop.is_running():
                    pass  # Loop is already running, let it process cancellations
                elif tasks:
                    loop.run_until_complete(asyncio.sleep(0.1))

                # Close the loop
                loop.close()
        except Exception:
            pass  # Loop might already be closed

    except Exception as e:
        print_error(f"Error during shutdown: {e}")


# Menu Functions
def show_menu() -> None:
    """
    Display a numbered menu system and process user selections.
    """
    while True:
        clear_screen()
        console.print(create_header())

        console.print(
            Panel.fit(
                "MAIN MENU",
                title="[bold]Nextcloud Setup",
                border_style=NordColors.FROST_3,
            )
        )
        console.print(f"[bold {NordColors.FROST_2}]1.[/] Download Nextcloud Package")
        console.print(f"[bold {NordColors.FROST_2}]2.[/] Install Dependencies")
        console.print(f"[bold {NordColors.FROST_2}]3.[/] Set Up PostgreSQL Database")
        console.print(
            f"[bold {NordColors.FROST_2}]4.[/] Install and Configure Nextcloud"
        )
        console.print(f"[bold {NordColors.FROST_2}]5.[/] Full Setup (All Steps)")
        console.print(f"[bold {NordColors.FROST_2}]6.[/] Exit\n")

        choice = Prompt.ask(
            f"[bold {NordColors.FROST_1}]Enter your choice[/]",
            choices=["1", "2", "3", "4", "5", "6"],
            default="6",
        )

        if choice == "1":
            zip_path = os.path.join(TEMP_DIR, "nextcloud-latest.zip")
            download_package(DOWNLOAD_URL, zip_path)
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "2":
            install_dependencies()
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "3":
            config = get_nextcloud_config()
            setup_postgresql(config)
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "4":
            config = get_nextcloud_config()
            zip_path = os.path.join(TEMP_DIR, "nextcloud-latest.zip")

            if not os.path.exists(zip_path):
                print_warning("Nextcloud package not found. Downloading it now...")
                if not download_package(DOWNLOAD_URL, zip_path):
                    Prompt.ask("\nPress Enter to return to the menu")
                    continue

            extract_nextcloud(zip_path, config.install_dir)
            setup_apache(config)
            configure_nextcloud(config)
            optimize_nextcloud(config)

            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "5":
            config = get_nextcloud_config()
            if setup_nextcloud(config):
                display_panel(
                    "Installation Complete",
                    f"Nextcloud has been successfully installed and configured!\n\n"
                    f"You can access your Nextcloud instance at: http://{config.domain}/\n"
                    f"Admin user: {config.admin_user}\n"
                    f"Remember to secure your installation with HTTPS!",
                    NordColors.GREEN,
                )
            else:
                display_panel(
                    "Installation Failed",
                    "There were errors during the Nextcloud installation process.\n"
                    "Please check the error messages above and try again.",
                    NordColors.RED,
                )
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "6":
            console.print(
                Panel(
                    "[bold green]Exiting Nextcloud Setup. Goodbye![/]",
                    border_style=NordColors.GREEN,
                )
            )
            sys.exit(0)


def main() -> None:
    """
    Main function that sets up signal handlers and launches the interactive menu.
    """
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Register the proper shutdown function
        atexit.register(proper_shutdown)

        # Ensure config directory exists
        ensure_config_directory()

        # Clear screen and show menu
        clear_screen()
        show_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
