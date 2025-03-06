#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import tempfile
import shutil
import json
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
VERSION: str = "2.0.0"
DOWNLOAD_URL: str = "https://download.nextcloud.com/server/releases/latest.zip"
OPERATION_TIMEOUT: int = 60
DEFAULT_WEB_USER: str = "www-data"
DEFAULT_WEBSERVER: str = "caddy"
DEFAULT_DB_TYPE: str = "pgsql"
# Will be dynamically determined
DEFAULT_PHP_VERSION: str = ""
TEMP_DIR: str = tempfile.gettempdir()

# Certificate paths (hardcoded to user's files)
CERT_FILE: str = "/home/sawyer/dunamismax.com.pem"
KEY_FILE: str = "/home/sawyer/dunamismax.com.key"

# Caddy file paths
CADDY_CONFIG_DIR: str = "/etc/caddy"
CADDYFILE_PATH: str = "/etc/caddy/Caddyfile"

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
    use_https: bool = True
    cert_file: str = CERT_FILE
    key_file: str = KEY_FILE
    email: str = ""
    using_cloudflare: bool = True

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

            # Filter out fields that don't exist in our current NextcloudConfig class
            valid_fields = {
                field
                for field in dir(NextcloudConfig())
                if not field.startswith("_")
                and not callable(getattr(NextcloudConfig(), field))
            }
            filtered_data = {k: v for k, v in data.items() if k in valid_fields}

            # Create a new config with only the valid fields
            return NextcloudConfig(**filtered_data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
        # If loading fails, delete the old config file
        try:
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
                print_warning(
                    "Removed incompatible configuration file. Using defaults."
                )
        except Exception:
            pass
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
        returncode, _, stderr = run_command(["nala", "update"], sudo=True)
        if returncode != 0:
            print_warning(f"Package list update still has issues: {stderr}")
            print_warning(
                "Continuing with installation, but some packages might not be available."
            )

    return True


def install_dependencies() -> bool:
    """
    Install all required dependencies for Nextcloud using nala.
    First checks for and fixes problematic repositories.
    """
    global DEFAULT_PHP_VERSION

    print_section("Installing Dependencies")

    # Check for and fix repository issues before installing dependencies
    fix_repository_issues()

    # Install nala if it's not already installed
    print_step("Checking if nala is installed...")
    returncode, _, _ = run_command(["which", "nala"])
    if returncode != 0:
        print_step("Installing nala package manager...")
        returncode, _, stderr = run_command(["apt", "install", "-y", "nala"], sudo=True)
        if returncode != 0:
            print_error(f"Failed to install nala: {stderr}")
            return False
        print_success("Nala package manager installed.")
    else:
        print_success("Nala package manager is already installed.")

    # Detect PHP versions
    php_versions = detect_available_php_versions()

    if not php_versions:
        print_error(
            "No PHP versions could be detected. Trying to install without specifying version."
        )
        DEFAULT_PHP_VERSION = ""
    else:
        print_step(f"Available PHP versions: {', '.join(php_versions)}")
        # Choose the newest PHP version that's >= 7.4 (Nextcloud requirement)
        suitable_versions = [v for v in php_versions if float(v) >= 7.4]

        if suitable_versions:
            DEFAULT_PHP_VERSION = suitable_versions[-1]  # Get the newest version
            print_success(
                f"Selected PHP version {DEFAULT_PHP_VERSION} for installation."
            )
        else:
            print_warning(
                "No suitable PHP version found (>= 7.4). Trying to use oldest available."
            )
            DEFAULT_PHP_VERSION = php_versions[0] if php_versions else ""

    # Update the config with the detected PHP version
    config = load_config()
    config.php_version = DEFAULT_PHP_VERSION
    save_config(config)

    # Define base dependencies
    base_dependencies = [
        "postgresql",
        "postgresql-contrib",
        "unzip",
        "curl",
        "ssl-cert",
        "openssl",
    ]

    # Define PHP dependencies based on detected version
    php_dependencies = []
    if DEFAULT_PHP_VERSION:
        php_dependencies = [
            f"php{DEFAULT_PHP_VERSION}-fpm",
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
        ]
    else:
        # Try generic packages if no version could be determined
        php_dependencies = [
            "php-fpm",
            "php-gd",
            "php-xml",
            "php-mbstring",
            "php-zip",
            "php-pgsql",
            "php-curl",
            "php-intl",
            "php-gmp",
            "php-bcmath",
            "php-imagick",
        ]

    # Combine dependencies
    dependencies = base_dependencies + php_dependencies

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

            _, stdout, stderr = run_command(["nala", "update"], sudo=True)
            if stderr and "error" in stderr.lower():
                print_warning(
                    f"Package list update has warnings/errors, but continuing: {stderr}"
                )

            progress.update(task_update, completed=1)

            # Install Caddy
            task_caddy = progress.add_task(
                f"[{NordColors.FROST_2}]Installing Caddy...", total=1
            )

            # Add Caddy official repository
            print_step("Adding Caddy official repository...")

            # Install dependencies for adding apt repositories
            run_command(
                ["nala", "install", "-y", "apt-transport-https", "gnupg"], sudo=True
            )

            # Download and install Caddy's signing key
            run_command(
                [
                    "curl",
                    "-1sLf",
                    "https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
                    "-o",
                    "/usr/share/keyrings/caddy-stable-archive-keyring.asc",
                ],
                sudo=True,
            )

            # Add Caddy repository to apt sources
            run_command(
                [
                    "curl",
                    "-1sLf",
                    "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt",
                    "-o",
                    "/etc/apt/sources.list.d/caddy-stable.list",
                ],
                sudo=True,
            )

            # Update package lists after adding Caddy repository
            run_command(["nala", "update"], sudo=True)

            # Install Caddy
            returncode, _, stderr = run_command(
                ["nala", "install", "-y", "caddy"], sudo=True
            )
            if returncode != 0:
                print_error(f"Failed to install Caddy: {stderr}")
                return False

            progress.update(task_caddy, completed=1)

            # Install other dependencies
            task_install = progress.add_task(
                f"[{NordColors.FROST_2}]Installing dependencies...",
                total=len(dependencies),
            )

            failed_packages = []

            for dependency in dependencies:
                progress.update(
                    task_install,
                    description=f"[{NordColors.FROST_2}]Installing {dependency}...",
                )

                returncode, stdout, stderr = run_command(
                    ["nala", "install", "-y", dependency], sudo=True
                )

                if returncode != 0:
                    print_error(f"Failed to install {dependency}: {stderr}")
                    failed_packages.append(dependency)
                    print_warning(
                        "Continuing with installation. Some features might not work properly."
                    )

                progress.advance(task_install)

            # If PHP installation failed, try alternative approaches
            if failed_packages and any(
                pkg.startswith("php") for pkg in failed_packages
            ):
                print_warning(
                    "PHP package installation had issues. Trying alternative approaches..."
                )

                # Try adding the PHP repository
                if Confirm.ask(
                    "Would you like to add the PHP repository and try again?",
                    default=True,
                ):
                    print_step("Adding PHP repository...")
                    returncode, _, stderr = run_command(
                        ["add-apt-repository", "-y", "ppa:ondrej/php"], sudo=True
                    )

                    if returncode == 0:
                        print_step("Updating package lists...")
                        run_command(["nala", "update"], sudo=True)

                        # Detect PHP versions again
                        php_versions = detect_available_php_versions()
                        if php_versions:
                            # Choose PHP version
                            print_step(
                                f"Available PHP versions after adding repository: {', '.join(php_versions)}"
                            )
                            suitable_versions = [
                                v for v in php_versions if float(v) >= 7.4
                            ]

                            if suitable_versions:
                                DEFAULT_PHP_VERSION = suitable_versions[-1]
                                config.php_version = DEFAULT_PHP_VERSION
                                save_config(config)
                                print_success(
                                    f"Selected PHP version {DEFAULT_PHP_VERSION} for installation."
                                )

                                # Try installing PHP packages again
                                print_step("Retrying PHP package installation...")
                                for dep in [
                                    d for d in failed_packages if d.startswith("php")
                                ]:
                                    if DEFAULT_PHP_VERSION:
                                        fixed_dep = dep.replace(
                                            "php8.1", f"php{DEFAULT_PHP_VERSION}"
                                        )
                                    else:
                                        fixed_dep = dep

                                    print_step(f"Installing {fixed_dep}...")
                                    run_command(
                                        ["nala", "install", "-y", fixed_dep], sudo=True
                                    )
                    else:
                        print_warning(f"Failed to add PHP repository: {stderr}")

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


def detect_available_php_versions() -> List[str]:
    """
    Detect available PHP versions in the system.
    Returns a list of available PHP version strings (e.g., ["7.4", "8.0", "8.1"])
    """
    available_versions = []

    try:
        # Try to find PHP packages using apt/nala
        returncode, stdout, _ = run_command(
            ["nala", "list", "--installed", "php*-common"], sudo=True
        )
        if returncode == 0:
            for line in stdout.splitlines():
                if "php" in line and "-common" in line:
                    parts = line.split()[0].split("-")[
                        0
                    ]  # Get "php7.4" from "php7.4-common"
                    version = parts[3:]  # Get "7.4" from "php7.4"
                    if version and version not in available_versions:
                        available_versions.append(version)

        # If no versions found, try using apt-cache search
        if not available_versions:
            returncode, stdout, _ = run_command(
                ["apt-cache", "search", "^php[0-9]+\\.[0-9]+-common$"], sudo=True
            )
            if returncode == 0:
                for line in stdout.splitlines():
                    # Extract version from package name (e.g., php7.4-common)
                    if line.startswith("php"):
                        parts = line.split(" - ")[0].split("-")[
                            0
                        ]  # Get "php7.4" from "php7.4-common"
                        version = parts[3:]  # Get "7.4" from "php7.4"
                        if version and version not in available_versions:
                            available_versions.append(version)
    except Exception as e:
        print_warning(f"Error detecting PHP versions: {e}")

    # If no versions found, try to check installed PHP
    if not available_versions:
        try:
            returncode, stdout, _ = run_command(["php", "-v"])
            if returncode == 0 and "PHP" in stdout:
                # Extract version from PHP -v output
                version_line = stdout.splitlines()[0]
                if "PHP " in version_line:
                    version = version_line.split("PHP ")[1].split(" ")[0]
                    major_minor = ".".join(
                        version.split(".")[:2]
                    )  # Get "7.4" from "7.4.3"
                    available_versions.append(major_minor)
        except Exception:
            pass

    # Add PPA repository if no supported versions found
    if not available_versions or not any(float(v) >= 7.4 for v in available_versions):
        print_warning("No suitable PHP versions found. Will try to add PHP repository.")
        try:
            # Try to add the PHP repository
            returncode, _, _ = run_command(
                ["add-apt-repository", "-y", "ppa:ondrej/php"], sudo=True
            )
            if returncode == 0:
                print_step("Updating package lists after adding repository...")
                run_command(["nala", "update"], sudo=True)

                # Check again for available versions
                returncode, stdout, _ = run_command(
                    ["apt-cache", "search", "^php[0-9]+\\.[0-9]+-common$"], sudo=True
                )
                if returncode == 0:
                    for line in stdout.splitlines():
                        if line.startswith("php"):
                            parts = line.split(" - ")[0].split("-")[0]
                            version = parts[3:]
                            if version and version not in available_versions:
                                available_versions.append(version)
        except Exception as e:
            print_warning(f"Error adding PHP repository: {e}")

    # Sort versions
    available_versions.sort(key=lambda v: [int(x) for x in v.split(".")])

    return available_versions


def check_port_in_use(port: int) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Check if a port is already in use and if so, by which process.
    Returns a tuple (is_in_use, process_name, process_pid)
    """
    try:
        # First try with ss command (most modern)
        returncode, stdout, _ = run_command(["ss", "-tulpn"], sudo=True)
        if returncode == 0:
            for line in stdout.splitlines():
                if f":{port}" in line and "LISTEN" in line:
                    # Extract process info - format: users:(("process",pid,fd))
                    if "users:" in line:
                        process_info = line.split("users:")[1].strip()
                        if "pid=" in process_info:
                            # Extract from newer format: pid=1234,fd=5
                            pid_str = process_info.split("pid=")[1].split(",")[0]
                            process = (
                                process_info.split('"')[1]
                                if '"' in process_info
                                else "unknown"
                            )
                            try:
                                return True, process, int(pid_str)
                            except ValueError:
                                return True, process, None
                        elif '(("' in process_info:
                            # Extract from format: ((\"process\",pid,fd))
                            parts = process_info.strip("()").split(",")
                            if len(parts) >= 2:
                                process = parts[0].strip('("')
                                try:
                                    pid = int(parts[1])
                                    return True, process, pid
                                except ValueError:
                                    return True, process, None
                    return True, None, None

        # Try with netstat if ss failed
        returncode, stdout, _ = run_command(["netstat", "-tulpn"], sudo=True)
        if returncode == 0:
            for line in stdout.splitlines():
                if f":{port}" in line and "LISTEN" in line:
                    # Extract process info - format: process_name/pid
                    parts = line.split()
                    if len(parts) >= 7:
                        process_info = parts[6]
                        if "/" in process_info:
                            process, pid_str = process_info.split("/")
                            try:
                                return True, process, int(pid_str)
                            except ValueError:
                                return True, process, None
                    return True, None, None

        # Try with lsof as a fallback
        returncode, stdout, _ = run_command(["lsof", "-i", f":{port}"], sudo=True)
        if returncode == 0 and stdout.strip():
            lines = stdout.splitlines()
            if len(lines) > 1:  # First line is headers
                parts = lines[1].split()
                if len(parts) > 1:
                    process_name = parts[0]
                    pid_str = parts[1]
                    try:
                        return True, process_name, int(pid_str)
                    except ValueError:
                        return True, process_name, None

        return False, None, None
    except Exception as e:
        print_warning(f"Error checking port: {e}")
        # If command failed, try a basic socket check
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            s.close()
            return False, None, None
        except socket.error:
            return True, None, None


def free_port(port: int) -> bool:
    """
    Find and kill any process using the specified port.
    Uses multiple methods to ensure the port is freed.
    Returns True if the port was successfully freed, False otherwise.
    """
    # First try using fuser (most direct method)
    try:
        print_step(f"Forcibly freeing port {port} with fuser...")
        run_command(["fuser", "-k", f"{port}/tcp"], sudo=True)

        # Give it a moment
        time.sleep(2)

        # Check if port is now free
        port_still_in_use, _, _ = check_port_in_use(port)
        if not port_still_in_use:
            print_success(f"Successfully freed port {port}.")
            return True
    except Exception:
        pass  # Continue with other methods if fuser fails

    # Try using ss -K (socket statistics kill)
    try:
        print_step(f"Attempting to free port {port} with ss...")
        run_command(["ss", "-K", f"sport = :{port}"], sudo=True)

        time.sleep(2)

        # Check if port is now free
        port_still_in_use, _, _ = check_port_in_use(port)
        if not port_still_in_use:
            print_success(f"Successfully freed port {port}.")
            return True
    except Exception:
        pass  # Continue with other methods if ss fails

    # Fall back to identifying and killing processes
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        port_in_use, process_name, pid = check_port_in_use(port)

        if not port_in_use:
            print_success(f"Port {port} is now free.")
            return True

        attempts += 1
        print_warning(f"Attempt {attempts}/{max_attempts} to free port {port}...")

        if pid:
            print_step(f"Killing process {process_name or 'unknown'} (PID: {pid})...")
            # Always use force kill (-9) to ensure termination
            run_command(["kill", "-9", str(pid)], sudo=True)

            # Give it time to die
            time.sleep(2)
        else:
            # If we can't get PID, try more aggressive methods
            print_warning(f"Cannot identify PID for process using port {port}")
            try:
                # Try using lsof with kill
                run_command(
                    ["bash", "-c", f"lsof -ti:{port} | xargs kill -9"], sudo=True
                )
                time.sleep(1)
            except Exception:
                pass

    # As a last resort, try restarting networking
    print_step("Attempting to restart networking services...")
    try:
        run_command(["systemctl", "restart", "networking"], sudo=True)
        time.sleep(5)  # Give enough time for networking to restart
    except Exception:
        pass

    # One final check
    port_in_use, _, _ = check_port_in_use(port)
    if not port_in_use:
        print_success(f"Successfully freed port {port} after multiple attempts.")
        return True

    print_error(f"Failed to free port {port} after {max_attempts} attempts.")
    return False


def setup_caddy(config: NextcloudConfig) -> bool:
    """
    Configure Caddy for Nextcloud with SSL support using the provided certificates.
    """
    print_section("Configuring Caddy Web Server")

    try:
        # Check if ports 80 and 443 are already in use
        port80_in_use, process80_name, pid80 = check_port_in_use(80)
        port443_in_use, process443_name, pid443 = check_port_in_use(443)

        if port80_in_use and process80_name != "caddy":
            print_warning(
                f"Port 80 is already in use by {process80_name or 'unknown process'}{f' (PID: {pid80})' if pid80 else ''}."
            )

            if free_port(80):
                print_success("Successfully freed port 80 for Caddy.")
            else:
                print_error("Failed to free port 80. Caddy may not start correctly.")

        if port443_in_use and process443_name != "caddy":
            print_warning(
                f"Port 443 is already in use by {process443_name or 'unknown process'}{f' (PID: {pid443})' if pid443 else ''}."
            )

            if free_port(443):
                print_success("Successfully freed port 443 for Caddy.")
            else:
                print_error("Failed to free port 443. Caddy may not start correctly.")

        # Create Caddy directory if it doesn't exist
        print_step("Creating Caddy configuration directory...")
        run_command(["mkdir", "-p", CADDY_CONFIG_DIR], sudo=True)

        # Determine which PHP-FPM socket to use
        php_version = (
            config.php_version if config.php_version else "7.4"
        )  # Default fallback
        php_fpm_sock = f"/run/php/php{php_version}-fpm.sock"

        # Check if the socket exists
        returncode, _, _ = run_command(["test", "-S", php_fpm_sock], sudo=True)
        if returncode != 0:
            print_warning(
                f"PHP-FPM socket {php_fpm_sock} not found. Checking alternatives..."
            )

            # Try to find any PHP-FPM socket
            returncode, stdout, _ = run_command(
                ["find", "/run/php", "-name", "*.sock"], sudo=True
            )
            if returncode == 0 and stdout.strip():
                php_fpm_sock = stdout.splitlines()[0].strip()
                print_success(f"Found alternative PHP-FPM socket: {php_fpm_sock}")
            else:
                print_error(
                    "No PHP-FPM socket found. PHP might not be properly installed."
                )
                return False

        # Create Caddyfile configuration
        caddyfile_content = f"""# Nextcloud Caddyfile
{config.domain} {{
    root * {config.install_dir}
    
    # If you want to use Caddy's automatic HTTPS, remove or comment out these lines
    # and remove the tls directives below
    # Caddy would handle certificates automatically, but using Cloudflare certificates here
    tls {config.cert_file} {config.key_file}
    
    # PHP-FPM handler
    php_fastcgi unix/{php_fpm_sock}
    
    # Nextcloud specific headers
    header Strict-Transport-Security "max-age=15552000; includeSubDomains"
    
    # For Cloudflare support
    @cloudflareIPs {{
        remote_ip 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 104.16.0.0/12 108.162.192.0/18 131.0.72.0/22 141.101.64.0/18 162.158.0.0/15 172.64.0.0/13 173.245.48.0/20 188.114.96.0/20 190.93.240.0/20 197.234.240.0/22 198.41.128.0/17
    }}
    
    # Properly handle HTTPS when behind Cloudflare
    @cloudflare_redirect {{
        header_regexp X-Forwarded-Proto X-Forwarded-Proto "^http$"
        match @cloudflareIPs
    }}
    redir @cloudflare_redirect https://{config.domain}{{{{uri}}}}

    # Needed for /.well-known URLs
    rewrite /.well-known/* /.well-known/{{{{path}}}}
    
    # Nextcloud .htaccess rules converted for Caddy
    rewrite /_next/* /_next/{{{{path}}}}
    rewrite /core/js/* /core/js/{{{{path}}}}
    rewrite /core/css/* /core/css/{{{{path}}}}
    
    # Prohibit direct access to sensitive directories
    @blocked {{
        path /data/* /config/* /db_structure/* /.ht*
    }}
    respond @blocked 403
    
    # Pretty URLs for Nextcloud
    try_files {{{{path}}}} {{{{path}}}}/index.php {{{{path}}}}/index.html
    
    # Handle .well-known urls (for ACME challenges and Caldav/Carddav)
    handle /.well-known/* {{
        try_files {{{{path}}}} /index.php{{{{uri}}}}
    }}
    
    # Primary rule for Nextcloud - all PHP requests go to index.php
    @phpFiles {{
        path *.php
    }}
    rewrite @phpFiles /index.php{{{{query}}}}
    
    # Optimization for static files
    header /favicon.ico Cache-Control "max-age=604800"
    header /static/* Cache-Control "max-age=604800"
    
    # Enable compression
    encode gzip zstd
    
    # Basic security headers
    header {{
        # Enable XSS filtering for legacy browsers
        X-XSS-Protection "1; mode=block"
        # Control MIME type sniffing
        X-Content-Type-Options "nosniff"
        # Prevent embedding in frames (clickjacking protection)
        X-Frame-Options "SAMEORIGIN"
        # Content Security Policy
        Content-Security-Policy "frame-ancestors 'self'"
        # Remove server header
        -Server
    }}
    
    # Log configuration
    log {{
        output file /var/log/caddy/nextcloud.log
        format console
    }}
}}
"""

        # Create temporary file for the Caddyfile
        caddy_config_file = tempfile.NamedTemporaryFile(delete=False, mode="w")
        caddy_config_file.write(caddyfile_content)
        caddy_config_file.close()

        # Copy configuration to Caddy directory
        print_step("Creating Caddy configuration...")
        returncode, _, stderr = run_command(
            ["cp", caddy_config_file.name, CADDYFILE_PATH], sudo=True
        )

        if returncode != 0:
            print_error(f"Failed to create Caddy configuration: {stderr}")
            os.unlink(caddy_config_file.name)
            return False

        os.unlink(caddy_config_file.name)

        # Create log directory for Caddy
        print_step("Creating Caddy log directory...")
        run_command(["mkdir", "-p", "/var/log/caddy"], sudo=True)
        run_command(["chown", "-R", "caddy:caddy", "/var/log/caddy"], sudo=True)

        # Validate Caddy configuration
        print_step("Validating Caddy configuration...")
        returncode, _, stderr = run_command(
            ["caddy", "validate", "--config", CADDYFILE_PATH], sudo=True
        )
        if returncode != 0:
            print_error(f"Caddy configuration validation failed: {stderr}")
            if not Confirm.ask("Continue anyway?", default=False):
                return False

        # Reload Caddy to apply the new configuration
        print_step("Reloading Caddy service...")
        returncode, _, stderr = run_command(["systemctl", "reload", "caddy"], sudo=True)

        # If reload fails, try restart
        if returncode != 0:
            print_warning(f"Failed to reload Caddy: {stderr}")
            print_step("Trying to restart Caddy...")
            returncode, _, stderr = run_command(
                ["systemctl", "restart", "caddy"], sudo=True
            )
            if returncode != 0:
                print_error(f"Failed to restart Caddy: {stderr}")
                return False

        # Verify Caddy is running
        print_step("Verifying Caddy service status...")
        returncode, _, _ = run_command(["systemctl", "is-active", "caddy"], sudo=True)
        if returncode != 0:
            print_error("Caddy is not running after configuration.")
            print_step("Checking Caddy logs for errors...")
            run_command(["journalctl", "-u", "caddy", "-n", "20"], sudo=True)
            return False

        print_success("Caddy configuration completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error configuring Caddy: {e}")
        return False


def verify_ssl_certificates(config: NextcloudConfig) -> bool:
    """
    Verify that the Cloudflare SSL certificates exist and are readable.
    """
    print_section("Verifying SSL Certificates")

    # Check if certificate files exist
    print_step(f"Checking certificate file: {config.cert_file}")
    returncode, _, _ = run_command(["test", "-f", config.cert_file], sudo=True)
    if returncode != 0:
        print_error(f"Certificate file not found: {config.cert_file}")
        return False

    print_step(f"Checking key file: {config.key_file}")
    returncode, _, _ = run_command(["test", "-f", config.key_file], sudo=True)
    if returncode != 0:
        print_error(f"Key file not found: {config.key_file}")
        return False

    # Ensure correct permissions for SSL certificate files
    print_step("Setting correct permissions for SSL files...")
    run_command(["chmod", "644", config.cert_file], sudo=True)
    run_command(["chmod", "600", config.key_file], sudo=True)

    # Verify the certificate is valid
    print_step("Verifying SSL certificate format...")
    returncode, stdout, stderr = run_command(
        ["openssl", "x509", "-in", config.cert_file, "-text", "-noout"], sudo=True
    )
    if returncode != 0:
        print_error(f"Certificate file is not valid: {stderr}")
        return False

    print_success("SSL certificates verified successfully.")
    return True


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
    Configure Nextcloud using the occ command or direct configuration.
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

        # Verify the occ command exists
        occ_path = os.path.join(config.install_dir, "occ")
        returncode, _, _ = run_command(["test", "-f", occ_path], sudo=True)
        if returncode != 0:
            print_warning(f"OCC command not found at {occ_path}")
            print_step("Looking for OCC in alternative locations...")

            # Try to find occ in subdirectories
            returncode, stdout, _ = run_command(
                ["find", config.install_dir, "-name", "occ", "-type", "f"], sudo=True
            )

            if returncode == 0 and stdout.strip():
                occ_path = stdout.splitlines()[0].strip()
                print_success(f"Found OCC at {occ_path}")
            else:
                print_error(
                    "OCC command not found. Nextcloud may not be properly extracted."
                )
                return False

        # Verify PHP is working properly
        php_check_cmd = ["php", "-v"]
        returncode, stdout, stderr = run_command(php_check_cmd)
        if returncode != 0:
            print_error(f"PHP is not working properly: {stderr}")
            return False

        print_step("Verifying Nextcloud installation...")

        # First method: Try using setup-nextcloud.php if it exists
        setup_php_path = os.path.join(config.install_dir, "setup-nextcloud.php")
        returncode, _, _ = run_command(["test", "-f", setup_php_path], sudo=True)
        if returncode == 0:
            print_step("Using setup-nextcloud.php for installation...")
            # Create config file content
            setup_content = f"""<?php
$CONFIG = array (
  'instanceid' => '{os.urandom(16).hex()}',
  'passwordsalt' => '{os.urandom(30).hex()}',
  'datadirectory' => '{config.data_dir}',
  'dbtype' => '{config.db_type}',
  'dbname' => '{config.db_name}',
  'dbhost' => '{config.db_host}',
  'dbport' => '{config.db_port}',
  'dbtableprefix' => 'oc_',
  'dbuser' => '{config.db_user}',
  'dbpassword' => '{config.db_pass}',
  'installed' => true,
);
"""
            # Write to a temporary file
            temp_config = tempfile.NamedTemporaryFile(delete=False, mode="w")
            temp_config.write(setup_content)
            temp_config.close()

            # Copy to the Nextcloud config directory
            config_dir = os.path.join(config.install_dir, "config")
            run_command(["mkdir", "-p", config_dir], sudo=True)
            run_command(
                ["cp", temp_config.name, os.path.join(config_dir, "config.php")],
                sudo=True,
            )
            run_command(
                [
                    "chown",
                    f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}",
                    os.path.join(config_dir, "config.php"),
                ],
                sudo=True,
            )
            os.unlink(temp_config.name)

            # Run the setup script
            setup_cmd = [
                "sudo",
                "-u",
                DEFAULT_WEB_USER,
                "php",
                setup_php_path,
                "--admin-user",
                config.admin_user,
                "--admin-pass",
                config.admin_pass,
            ]
            returncode, stdout, stderr = run_command(setup_cmd)
            if returncode != 0:
                print_warning(f"Setup script method failed: {stderr}")
                # Continue to try other methods
            else:
                print_success("Nextcloud installed via setup script")
                # Skip to the occ configuration for trusted domains

        # Second method: Try direct occ command
        print_step("Running Nextcloud installation via OCC command...")
        # Make sure occ is executable
        run_command(["chmod", "+x", occ_path], sudo=True)

        occ_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            occ_path,
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
            print_warning(f"OCC installation method failed: {stderr}")

            # Third method: Manual config file creation
            print_step("Trying manual configuration method...")

            # Create autoconfig.php
            autoconfig_content = f"""<?php
$AUTOCONFIG = array (
  'dbtype' => '{config.db_type}',
  'dbname' => '{config.db_name}',
  'dbuser' => '{config.db_user}',
  'dbpass' => '{config.db_pass}',
  'dbhost' => '{config.db_host}',
  'dbport' => '{config.db_port}',
  'dbtableprefix' => 'oc_',
  'directory' => '{config.data_dir}',
  'adminlogin' => '{config.admin_user}',
  'adminpass' => '{config.admin_pass}',
);
"""
            # Write to a temporary file
            temp_autoconfig = tempfile.NamedTemporaryFile(delete=False, mode="w")
            temp_autoconfig.write(autoconfig_content)
            temp_autoconfig.close()

            # Copy to the Nextcloud config directory
            config_dir = os.path.join(config.install_dir, "config")
            run_command(["mkdir", "-p", config_dir], sudo=True)
            run_command(
                [
                    "cp",
                    temp_autoconfig.name,
                    os.path.join(config_dir, "autoconfig.php"),
                ],
                sudo=True,
            )
            run_command(
                [
                    "chown",
                    f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}",
                    os.path.join(config_dir, "autoconfig.php"),
                ],
                sudo=True,
            )
            os.unlink(temp_autoconfig.name)

            # Now try to access the web UI to trigger installation
            print_step("Manual configuration files created.")
            print_step("Web-based installation should trigger on first access.")

            # Create a status.php access to try to initialize
            status_url = f"http://localhost/status.php"
            try:
                response = requests.get(status_url, timeout=10)
                if response.status_code == 200:
                    print_success("Installation verification successful")
                else:
                    print_warning(
                        f"Installation verification returned status {response.status_code}"
                    )
            except Exception as e:
                print_warning(f"Could not verify installation: {e}")

            # Final verification: check if config.php exists
            config_php_path = os.path.join(config_dir, "config.php")
            returncode, _, _ = run_command(["test", "-f", config_php_path], sudo=True)
            if returncode != 0:
                print_warning("Could not verify successful installation.")
                print_warning(
                    "You may need to complete setup through the web interface."
                )
                print_warning(
                    f"Visit https://{config.domain}/ to complete installation if needed."
                )
            else:
                print_success("Nextcloud configuration files detected.")

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

        # Configure overwrite.cli.url for proper redirects
        overwrite_url_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "overwrite.cli.url",
            "--value",
            f"https://{config.domain}",
        ]

        returncode, _, stderr = run_command(overwrite_url_cmd)
        if returncode != 0:
            print_error(f"Failed to set overwrite URL: {stderr}")
            return False

        # Force HTTPS
        print_step("Configuring Nextcloud to use HTTPS...")
        force_https_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "force_https",
            "--type",
            "boolean",
            "--value",
            "true",
        ]
        run_command(force_https_cmd)

        # Configure trusted proxies for Cloudflare
        print_step("Configuring trusted proxies for Cloudflare...")

        # Cloudflare IPv4 ranges
        cf_ranges = [
            "173.245.48.0/20",
            "103.21.244.0/22",
            "103.22.200.0/22",
            "103.31.4.0/22",
            "141.101.64.0/18",
            "108.162.192.0/18",
            "190.93.240.0/20",
            "188.114.96.0/20",
            "197.234.240.0/22",
            "198.41.128.0/17",
            "162.158.0.0/15",
            "104.16.0.0/12",
            "172.64.0.0/13",
            "131.0.72.0/22",
        ]

        # Add each Cloudflare range as a trusted proxy
        for i, ip_range in enumerate(cf_ranges):
            trusted_proxy_cmd = [
                "sudo",
                "-u",
                DEFAULT_WEB_USER,
                "php",
                os.path.join(config.install_dir, "occ"),
                "config:system:set",
                "trusted_proxies",
                str(i),
                "--value",
                ip_range,
            ]
            run_command(trusted_proxy_cmd)

        # Set reverse proxy headers
        proxy_headers_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "overwriteprotocol",
            "--value",
            "https",
        ]
        run_command(proxy_headers_cmd)

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

        # Find the correct PHP ini path
        php_version = config.php_version

        if not php_version:
            # Try to detect PHP version if not set in config
            print_step("PHP version not set in config, detecting installed version...")
            php_versions = detect_available_php_versions()
            if php_versions:
                php_version = php_versions[-1]  # Get the newest version
                print_step(f"Using detected PHP version: {php_version}")
            else:
                print_warning(
                    "Could not detect PHP version. Skipping PHP optimization."
                )
                return True

        # Verify PHP ini path exists
        potential_paths = [
            f"/etc/php/{php_version}/fpm/php.ini",  # Debian/Ubuntu with PHP-FPM
            f"/etc/php/{php_version}/cli/php.ini",  # CLI version
            "/etc/php.ini",  # Generic fallback
        ]

        php_ini_path = None
        for path in potential_paths:
            returncode, _, _ = run_command(["test", "-f", path], sudo=True)
            if returncode == 0:
                php_ini_path = path
                print_step(f"Found PHP configuration at: {php_ini_path}")
                break

        if not php_ini_path:
            print_warning(
                "Could not find PHP configuration file. Skipping PHP optimization."
            )
            return True

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

        # Restart PHP-FPM to apply changes
        print_step("Restarting PHP-FPM to apply changes...")
        returncode, _, stderr = run_command(
            ["systemctl", "restart", f"php{php_version}-fpm"], sudo=True
        )
        if returncode != 0:
            print_warning(f"Failed to restart PHP-FPM: {stderr}")
            print_warning(
                "PHP optimizations may not be applied until PHP-FPM is restarted."
            )
            # Continue anyway as this is not critical

        print_success("Nextcloud optimization completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error optimizing Nextcloud: {e}")
        return False


def display_cloudflare_instructions(config: NextcloudConfig) -> None:
    """
    Display helpful instructions for configuring Cloudflare with Nextcloud.
    """
    print_section("Cloudflare Configuration Instructions")

    instructions = f"""
Your Nextcloud instance is configured to work with Cloudflare using the origin certificates:
- Certificate: {config.cert_file}
- Key: {config.key_file}

To complete your Cloudflare configuration:

1. Login to your Cloudflare account and go to the DNS settings for {config.domain}

2. Ensure you have an A record pointing to your server's IP address:
   - Type: A
   - Name: {config.domain.split(".")[0] if "." in config.domain else "@"}
   - Content: Your server IP
   - Proxy status: ON (orange cloud)

3. SSL/TLS settings:
   - Set SSL/TLS encryption mode to "Full (strict)"
   - This ensures secure communication between Cloudflare and your origin server

4. Page Rules (recommended):
   - Create a page rule for https://{config.domain}/*
   - Set Cache Level to "Bypass"
   - This prevents Cloudflare from caching your Nextcloud content

5. Additional SSL/TLS settings:
   - Enable "Always Use HTTPS"
   - Set Minimum TLS Version to TLS 1.2

Your Nextcloud server has been configured with Caddy and the necessary settings to work with Cloudflare's proxy.
"""

    display_panel("Cloudflare Configuration", instructions, NordColors.FROST_2)


def setup_nextcloud(config: NextcloudConfig) -> bool:
    """
    Perform the complete Nextcloud setup process.
    """
    # Define zip file path
    zip_path = os.path.join(TEMP_DIR, "nextcloud-latest.zip")

    # Verify the certificate files exist and are valid
    if not verify_ssl_certificates(config):
        return False

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

    # Configure permissions properly before Caddy setup
    print_step("Setting proper permissions for all Nextcloud files...")
    run_command(
        ["find", config.install_dir, "-type", "f", "-exec", "chmod", "0640", "{}", ";"],
        sudo=True,
    )
    run_command(
        ["find", config.install_dir, "-type", "d", "-exec", "chmod", "0750", "{}", ";"],
        sudo=True,
    )
    run_command(
        ["chown", "-R", f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}", config.install_dir],
        sudo=True,
    )

    # Set up Caddy with SSL
    if not setup_caddy(config):
        return False

    # Configure Nextcloud
    if not configure_nextcloud(config):
        print_warning("Automatic Nextcloud configuration had issues.")
        print_warning("You may need to complete the setup through the web interface.")
        print_step("Setting permissions to ensure web setup can work...")

        # Make sure config directory is writable for web setup
        config_dir = os.path.join(config.install_dir, "config")
        run_command(["mkdir", "-p", config_dir], sudo=True)
        run_command(
            ["chown", "-R", f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}", config_dir],
            sudo=True,
        )
        run_command(["chmod", "0770", config_dir], sudo=True)

    # Optimize Nextcloud
    optimize_nextcloud(config)

    # Make sure web server has proper file access
    print_step("Ensuring web server has proper access to Nextcloud files...")
    run_command(
        ["chown", "-R", f"{DEFAULT_WEB_USER}:{DEFAULT_WEB_USER}", config.data_dir],
        sudo=True,
    )
    run_command(
        ["chmod", "0770", config.data_dir],
        sudo=True,
    )

    # Display Cloudflare-specific instructions
    display_cloudflare_instructions(config)

    # Restart Caddy one final time
    print_step("Restarting Caddy for final configuration...")
    run_command(["systemctl", "restart", "caddy"], sudo=True)

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
        "[bold]Enter domain name for Nextcloud[/]", default="dunamismax.com"
    )
    config.email = Prompt.ask(
        "[bold]Enter email address (for admin notifications)[/]",
        default="admin@example.com",
    )

    # Installation directories
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
        # Simply print a cleanup message
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    cleanup()
    sys.exit(128 + sig)


def proper_shutdown():
    """Clean up resources at exit."""
    try:
        cleanup()
    except Exception as e:
        print_error(f"Error during shutdown: {e}")


# Simplified Menu with just two options: Full Setup and Exit
def show_menu() -> None:
    """
    Display a simplified menu system with just full setup and exit options.
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
        console.print(f"[bold {NordColors.FROST_2}]1.[/] Complete Nextcloud Setup")
        console.print(f"[bold {NordColors.FROST_2}]2.[/] Exit\n")

        choice = Prompt.ask(
            f"[bold {NordColors.FROST_1}]Enter your choice[/]",
            choices=["1", "2"],
            default="1",
        )

        if choice == "1":
            config = get_nextcloud_config()
            if setup_nextcloud(config):
                display_panel(
                    "Installation Complete",
                    f"Nextcloud has been successfully installed and configured!\n\n"
                    f"You can access your Nextcloud instance at: https://{config.domain}/\n"
                    f"Admin user: {config.admin_user}\n\n"
                    f"SSL is properly configured with your Cloudflare origin certificates.\n\n"
                    f"Cloudflare proxy configuration has been applied.",
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
        elif choice == "2":
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
