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
VERSION: str = "1.1.0"
DOWNLOAD_URL: str = "https://download.nextcloud.com/server/releases/latest.zip"
OPERATION_TIMEOUT: int = 60
DEFAULT_WEB_USER: str = "www-data"
DEFAULT_WEBSERVER: str = "apache2"
DEFAULT_DB_TYPE: str = "pgsql"
LETSENCRYPT_REPO_URL: str = "https://dl.eff.org/certbot-auto"
# Will be dynamically determined
DEFAULT_PHP_VERSION: str = ""
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
    use_https: bool = True
    cert_file: str = ""
    key_file: str = ""
    email: str = ""
    using_cloudflare: bool = False
    ssl_method: str = "letsencrypt"  # Options: "letsencrypt", "self-signed", "manual"

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
    global DEFAULT_PHP_VERSION

    print_section("Installing Dependencies")

    # Check for and fix repository issues before installing dependencies
    fix_repository_issues()

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
        "apache2",
        "postgresql",
        "postgresql-contrib",
        "unzip",
        "curl",
        "python3-certbot-apache",  # Added for Let's Encrypt support
        "certbot",  # Added for Let's Encrypt support
        "ssl-cert",  # Added for SSL support
        "openssl",  # Added for SSL support
    ]

    # Define PHP dependencies based on detected version
    php_dependencies = []
    if DEFAULT_PHP_VERSION:
        php_dependencies = [
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
        ]
    else:
        # Try generic packages if no version could be determined
        php_dependencies = [
            "libapache2-mod-php",
            "php",
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

            failed_packages = []

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

                # Option 1: Try adding the PHP repository
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
                        run_command(["apt", "update"], sudo=True)

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
                                        ["apt", "install", "-y", fixed_dep], sudo=True
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
        # Try to find PHP packages using apt
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
                run_command(["apt", "update"], sudo=True)

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


def kill_process(pid: int, force: bool = False) -> bool:
    """
    Kill a process with the given PID.
    If force is True, uses SIGKILL (-9) instead of SIGTERM.
    Returns True if successful, False otherwise.
    """
    try:
        print_step(f"Attempting to kill process with PID {pid}...")
        cmd = ["kill"]
        if force:
            cmd.append("-9")
        cmd.append(str(pid))

        returncode, _, stderr = run_command(cmd, sudo=True)

        if returncode != 0:
            print_error(f"Failed to kill process: {stderr}")
            # If normal kill failed and we didn't already try force, try with force
            if not force:
                print_step("Trying forced kill...")
                return kill_process(pid, force=True)
            return False

        # Verify the process was killed
        time.sleep(1)  # Give it a moment to terminate
        returncode, _, _ = run_command(["ps", "-p", str(pid)], sudo=True)
        if returncode == 0:
            print_warning(f"Process {pid} is still running.")
            # If it's still running and we didn't use force, try force
            if not force:
                return kill_process(pid, force=True)
            return False

        print_success(f"Process with PID {pid} was successfully terminated.")
        return True
    except Exception as e:
        print_error(f"Error killing process: {e}")
        return False


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


def setup_self_signed_ssl(config: NextcloudConfig) -> bool:
    """
    Create and set up self-signed SSL certificates for Apache.
    """
    print_section("Setting up Self-Signed SSL Certificate")

    ssl_dir = "/etc/ssl/nextcloud"
    cert_file = os.path.join(ssl_dir, f"{config.domain}.crt")
    key_file = os.path.join(ssl_dir, f"{config.domain}.key")

    # Create directory for certificates
    print_step(f"Creating SSL directory at {ssl_dir}...")
    returncode, _, stderr = run_command(["mkdir", "-p", ssl_dir], sudo=True)
    if returncode != 0:
        print_error(f"Failed to create SSL directory: {stderr}")
        return False

    # Generate self-signed certificate
    print_step("Generating self-signed SSL certificate...")
    openssl_cmd = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-days",
        "365",
        "-newkey",
        "rsa:2048",
        "-keyout",
        key_file,
        "-out",
        cert_file,
        "-subj",
        f"/CN={config.domain}/O=Nextcloud/C=US",
    ]

    returncode, _, stderr = run_command(openssl_cmd, sudo=True)
    if returncode != 0:
        print_error(f"Failed to generate SSL certificate: {stderr}")
        return False

    # Set proper permissions
    run_command(["chmod", "600", key_file], sudo=True)

    # Update config with certificate paths
    config.cert_file = cert_file
    config.key_file = key_file
    save_config(config)

    print_success("Self-signed SSL certificate generated successfully.")
    return True


def setup_letsencrypt_ssl(config: NextcloudConfig) -> bool:
    """
    Set up Let's Encrypt SSL certificate for Apache.
    """
    print_section("Setting up Let's Encrypt SSL Certificate")

    if not config.email:
        print_error("Email address is required for Let's Encrypt certificate.")
        return False

    # Make sure Apache is running and ports are available
    print_step("Ensuring Apache is running...")
    returncode, _, _ = run_command(["systemctl", "is-active", "apache2"], sudo=True)
    if returncode != 0:
        print_step("Starting Apache...")
        run_command(["systemctl", "start", "apache2"], sudo=True)

    # Check if ports 80 and 443 are free (except for Apache)
    port80_in_use, process80, _ = check_port_in_use(80)
    port443_in_use, process443, _ = check_port_in_use(443)

    if port80_in_use and process80 != "apache2":
        print_warning(f"Port 80 is in use by {process80}. Attempting to free it...")
        if not free_port(80):
            print_error("Failed to free port 80. Let's Encrypt verification may fail.")

    if port443_in_use and process443 != "apache2":
        print_warning(f"Port 443 is in use by {process443}. Attempting to free it...")
        if not free_port(443):
            print_error(
                "Failed to free port 443. Let's Encrypt may not work correctly."
            )

    # Run certbot to obtain certificates
    print_step(f"Obtaining Let's Encrypt certificate for {config.domain}...")

    # Check if Cloudflare is being used
    if config.using_cloudflare:
        print_warning(
            "Since you're using Cloudflare, we'll use DNS verification instead of HTTP."
        )
        print_warning("For Cloudflare, you need to set up DNS verification manually.")
        display_panel(
            "Cloudflare Setup",
            "When using Cloudflare with Let's Encrypt, consider these steps:\n\n"
            "1. Temporarily set Cloudflare to 'DNS Only' mode during certificate setup\n"
            "2. After obtaining certificates, you can enable Cloudflare proxy again\n"
            "3. Ensure your SSL/TLS encryption mode in Cloudflare is set to 'Full Strict'\n"
            "4. Create an Origin CA certificate in Cloudflare if Let's Encrypt fails",
            NordColors.YELLOW,
        )
        if not Confirm.ask("Proceed with Let's Encrypt setup?", default=True):
            print_warning("Skipping Let's Encrypt setup.")
            return False

    # First, try with the standalone plugin
    certbot_cmd = [
        "certbot",
        "certonly",
        "--standalone",
        "--non-interactive",
        "--agree-tos",
        "--email",
        config.email,
        "-d",
        config.domain,
    ]

    returncode, stdout, stderr = run_command(certbot_cmd, sudo=True)
    if returncode != 0:
        print_warning(f"Standalone method failed: {stderr}")

        # Try with the webroot plugin
        print_step("Trying webroot method...")
        certbot_cmd = [
            "certbot",
            "certonly",
            "--webroot",
            "--webroot-path",
            config.install_dir,
            "--non-interactive",
            "--agree-tos",
            "--email",
            config.email,
            "-d",
            config.domain,
        ]

        returncode, stdout, stderr = run_command(certbot_cmd, sudo=True)
        if returncode != 0:
            print_warning(f"Webroot method failed: {stderr}")

            # Try with the Apache plugin
            print_step("Trying Apache plugin method...")
            certbot_cmd = [
                "certbot",
                "certonly",
                "--apache",
                "--non-interactive",
                "--agree-tos",
                "--email",
                config.email,
                "-d",
                config.domain,
            ]

            returncode, stdout, stderr = run_command(certbot_cmd, sudo=True)
            if returncode != 0:
                print_error(f"All Let's Encrypt methods failed: {stderr}")
                print_step("Falling back to self-signed certificate...")
                return setup_self_signed_ssl(config)

    # Certificate paths
    cert_file = f"/etc/letsencrypt/live/{config.domain}/fullchain.pem"
    key_file = f"/etc/letsencrypt/live/{config.domain}/privkey.pem"

    # Verify the certificates exist
    returncode, _, _ = run_command(["test", "-f", cert_file], sudo=True)
    if returncode != 0:
        print_error(f"Certificate file not found at {cert_file}")
        print_step("Falling back to self-signed certificate...")
        return setup_self_signed_ssl(config)

    returncode, _, _ = run_command(["test", "-f", key_file], sudo=True)
    if returncode != 0:
        print_error(f"Key file not found at {key_file}")
        print_step("Falling back to self-signed certificate...")
        return setup_self_signed_ssl(config)

    # Update config with certificate paths
    config.cert_file = cert_file
    config.key_file = key_file
    save_config(config)

    print_success("Let's Encrypt SSL certificate obtained successfully.")

    # Set up automatic renewal
    print_step("Setting up automatic certificate renewal...")
    run_command(["systemctl", "enable", "certbot.timer"], sudo=True)
    run_command(["systemctl", "start", "certbot.timer"], sudo=True)

    return True


def setup_apache(config: NextcloudConfig) -> bool:
    """
    Configure Apache for Nextcloud with SSL support.
    """
    print_section("Configuring Apache Web Server")

    try:
        # Check if ports 80 and 443 are already in use
        port80_in_use, process80_name, pid80 = check_port_in_use(80)
        port443_in_use, process443_name, pid443 = check_port_in_use(443)

        if port80_in_use and process80_name != "apache2":
            print_warning(
                f"Port 80 is already in use by {process80_name or 'unknown process'}{f' (PID: {pid80})' if pid80 else ''}."
            )

            if free_port(80):
                print_success("Successfully freed port 80 for Apache.")
            else:
                print_error("Failed to free port 80. Apache may not start correctly.")

        if port443_in_use and process443_name != "apache2":
            print_warning(
                f"Port 443 is already in use by {process443_name or 'unknown process'}{f' (PID: {pid443})' if pid443 else ''}."
            )

            if free_port(443):
                print_success("Successfully freed port 443 for Apache.")
            else:
                print_error("Failed to free port 443. Apache may not start correctly.")

        # Enable required Apache modules
        modules = ["rewrite", "headers", "env", "dir", "mime", "ssl"]

        for module in modules:
            print_step(f"Enabling Apache module: {module}")
            returncode, _, stderr = run_command(["a2enmod", module], sudo=True)
            if returncode != 0:
                print_warning(f"Could not enable Apache module {module}: {stderr}")

        # Create Apache site configuration with SSL
        if config.use_https and config.cert_file and config.key_file:
            site_config = f"""<VirtualHost *:80>
    ServerName {config.domain}
    ServerAdmin webmaster@localhost
    
    # Redirect all HTTP traffic to HTTPS
    Redirect permanent / https://{config.domain}/
    
    ErrorLog ${{APACHE_LOG_DIR}}/nextcloud_error.log
    CustomLog ${{APACHE_LOG_DIR}}/nextcloud_access.log combined
</VirtualHost>

<VirtualHost *:443>
    ServerName {config.domain}
    ServerAdmin webmaster@localhost
    DocumentRoot {config.install_dir}

    <Directory {config.install_dir}>
        Options FollowSymlinks
        AllowOverride All
        Require all granted
        <IfModule mod_dav.c>
            Dav off
        </IfModule>
        
        # HSTS (optional)
        <IfModule mod_headers.c>
            Header always set Strict-Transport-Security "max-age=15552000; includeSubDomains"
        </IfModule>
    </Directory>

    # SSL Configuration
    SSLEngine on
    SSLCertificateFile {config.cert_file}
    SSLCertificateKeyFile {config.key_file}
    
    # For Cloudflare
    SetEnvIf X-Forwarded-Proto "https" HTTPS=on

    # Modern SSL configuration
    SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLHonorCipherOrder on
    SSLCompression off
    
    ErrorLog ${{APACHE_LOG_DIR}}/nextcloud_ssl_error.log
    CustomLog ${{APACHE_LOG_DIR}}/nextcloud_ssl_access.log combined
</VirtualHost>
"""
        else:
            # HTTP-only configuration
            site_config = f"""<VirtualHost *:80>
    ServerName {config.domain}
    ServerAdmin webmaster@localhost
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

        # Create global ServerName directive to suppress warnings
        server_name_config = f"""# Global ServerName
ServerName {config.domain}
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

        # Create ServerName config file
        server_name_file = tempfile.NamedTemporaryFile(delete=False, mode="w")
        server_name_file.write(server_name_config)
        server_name_file.close()

        returncode, _, stderr = run_command(
            [
                "cp",
                server_name_file.name,
                "/etc/apache2/conf-available/servername.conf",
            ],
            sudo=True,
        )

        if returncode != 0:
            print_warning(f"Could not create ServerName configuration: {stderr}")
        else:
            # Enable the ServerName config
            run_command(["a2enconf", "servername.conf"], sudo=True)

        os.unlink(server_name_file.name)

        # Disable any existing sites that might conflict
        print_step("Checking for enabled Apache sites that might conflict...")
        returncode, stdout, _ = run_command(
            ["ls", "-1", "/etc/apache2/sites-enabled"], sudo=True
        )
        if returncode == 0:
            enabled_sites = [
                site for site in stdout.splitlines() if site != "nextcloud.conf"
            ]

            if enabled_sites:
                print_warning(f"Found other enabled sites: {', '.join(enabled_sites)}")
                print_step("Disabling other Apache sites to avoid conflicts...")

                for site in enabled_sites:
                    print_step(f"Disabling site {site}...")
                    run_command(["a2dissite", site], sudo=True)

        # Enable the Nextcloud site
        print_step("Enabling Nextcloud site in Apache...")
        returncode, _, stderr = run_command(["a2ensite", "nextcloud.conf"], sudo=True)
        if returncode != 0:
            print_error(f"Failed to enable Apache site: {stderr}")
            return False

        # Verify Apache configuration
        print_step("Verifying Apache configuration...")
        returncode, _, stderr = run_command(["apache2ctl", "configtest"], sudo=True)
        if returncode != 0:
            print_warning(f"Apache configuration test failed: {stderr}")
            if not Confirm.ask("Continue anyway?", default=False):
                return False

        # Make sure ports are still free before starting Apache
        port80_in_use, process80_name, pid80 = check_port_in_use(80)
        if port80_in_use and process80_name != "apache2":
            print_warning(
                f"Port 80 is in use again by {process80_name or 'unknown process'}{f' (PID: {pid80})' if pid80 else ''}."
            )
            if free_port(80):
                print_success("Successfully freed port 80 for Apache.")
            else:
                print_error("Failed to free port 80. Apache may not start correctly.")

        if config.use_https:
            port443_in_use, process443_name, pid443 = check_port_in_use(443)
            if port443_in_use and process443_name != "apache2":
                print_warning(
                    f"Port 443 is in use again by {process443_name or 'unknown process'}{f' (PID: {pid443})' if pid443 else ''}."
                )
                if free_port(443):
                    print_success("Successfully freed port 443 for Apache.")
                else:
                    print_error(
                        "Failed to free port 443. Apache may not start correctly."
                    )

        # Restart Apache
        print_step("Restarting Apache service...")
        returncode, _, stderr = run_command(
            ["systemctl", "restart", "apache2"], sudo=True
        )
        if returncode != 0:
            print_error(f"Failed to restart Apache: {stderr}")

            # Try stopping and starting instead
            print_step("Trying alternative method: stop and start Apache...")
            run_command(["systemctl", "stop", "apache2"], sudo=True)
            time.sleep(2)  # Give it time to fully stop

            # Check if required ports are free before starting
            port80_in_use, _, _ = check_port_in_use(80)
            if port80_in_use:
                if free_port(80):
                    print_success("Successfully freed port 80 for Apache.")
                else:
                    print_error(
                        "Failed to free port 80. Apache may not start correctly."
                    )

            if config.use_https:
                port443_in_use, _, _ = check_port_in_use(443)
                if port443_in_use:
                    if free_port(443):
                        print_success("Successfully freed port 443 for Apache.")
                    else:
                        print_error(
                            "Failed to free port 443. Apache may not start correctly."
                        )

            returncode, _, stderr = run_command(
                ["systemctl", "start", "apache2"], sudo=True
            )
            if returncode != 0:
                print_error(f"Failed to start Apache: {stderr}")
                return False

        # Verify Apache is running
        returncode, _, _ = run_command(["systemctl", "is-active", "apache2"], sudo=True)
        if returncode != 0:
            print_error("Apache is not running after configuration.")
            return False

        print_success("Apache configuration completed successfully.")
        return True
    except Exception as e:
        print_error(f"Error configuring Apache: {e}")
        return False


def setup_ssl(config: NextcloudConfig) -> bool:
    """
    Set up SSL certificate based on the chosen method.
    """
    if not config.use_https:
        print_warning("HTTPS is disabled. Skipping SSL setup.")
        return True

    print_section("Setting up SSL")

    if config.ssl_method == "letsencrypt":
        return setup_letsencrypt_ssl(config)
    elif config.ssl_method == "self-signed":
        return setup_self_signed_ssl(config)
    elif config.ssl_method == "manual":
        print_step("Using manually provided certificate files...")
        # Check if certificate files exist
        returncode, _, _ = run_command(["test", "-f", config.cert_file], sudo=True)
        if returncode != 0:
            print_error(f"Certificate file not found at {config.cert_file}")
            return False

        returncode, _, _ = run_command(["test", "-f", config.key_file], sudo=True)
        if returncode != 0:
            print_error(f"Key file not found at {config.key_file}")
            return False

        print_success("Manual certificate files verified.")
        return True
    else:
        print_error(f"Unknown SSL method: {config.ssl_method}")
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

        # Configure overwrite.cli.url for proper redirects
        protocol = "https" if config.use_https else "http"
        overwrite_url_cmd = [
            "sudo",
            "-u",
            DEFAULT_WEB_USER,
            "php",
            os.path.join(config.install_dir, "occ"),
            "config:system:set",
            "overwrite.cli.url",
            "--value",
            f"{protocol}://{config.domain}",
        ]

        returncode, _, stderr = run_command(overwrite_url_cmd)
        if returncode != 0:
            print_error(f"Failed to set overwrite URL: {stderr}")
            return False

        # Force HTTPS if enabled
        if config.use_https:
            print_step("Configuring Nextcloud to use HTTPS...")
            https_cmd = [
                "sudo",
                "-u",
                DEFAULT_WEB_USER,
                "php",
                os.path.join(config.install_dir, "occ"),
                "config:system:set",
                "htaccess.RewriteBase",
                "--value",
                "/",
            ]
            run_command(https_cmd)

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

            # Update .htaccess
            update_htaccess_cmd = [
                "sudo",
                "-u",
                DEFAULT_WEB_USER,
                "php",
                os.path.join(config.install_dir, "occ"),
                "maintenance:update:htaccess",
            ]
            run_command(update_htaccess_cmd)

        # If using Cloudflare, add trusted proxy configuration
        if config.using_cloudflare:
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
            f"/etc/php/{php_version}/apache2/php.ini",  # Debian/Ubuntu with apache2
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

        # Restart Apache to apply PHP changes
        print_step("Restarting Apache to apply changes...")
        returncode, _, stderr = run_command(
            ["systemctl", "restart", "apache2"], sudo=True
        )
        if returncode != 0:
            print_warning(f"Failed to restart Apache: {stderr}")
            print_warning(
                "PHP optimizations may not be applied until Apache is restarted."
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

    protocol = "https" if config.use_https else "http"
    url = f"{protocol}://{config.domain}"

    instructions = f"""
To correctly configure Cloudflare with your Nextcloud installation:

1. Login to your Cloudflare account and go to the DNS settings for {config.domain}

2. Ensure you have an A record pointing to your server's IP address:
   - Type: A
   - Name: {config.domain.split(".")[0] if "." in config.domain else "@"}
   - Content: Your server IP
   - Proxy status: {("ON (recommended)" if config.use_https else "OFF (required until SSL is set up)")}

3. SSL/TLS settings:
   - Set SSL/TLS encryption mode to "Full (strict)" 
   - This requires valid SSL certificates on your origin server (which we've set up)

4. Page Rules (recommended):
   - Create a page rule for {url}/*
   - Set Cache Level to "Bypass"
   - This prevents Cloudflare from caching your Nextcloud content

5. If you experience issues:
   - Try setting Cloudflare to DNS Only mode temporarily
   - Once everything is working, you can enable the proxy again
   - Verify SSL certificates on both your server and Cloudflare

Your Nextcloud installation is already configured to work with Cloudflare proxy.
"""

    display_panel("Cloudflare Configuration", instructions, NordColors.FROST_2)


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

    # Set up SSL if enabled
    if config.use_https:
        if not setup_ssl(config):
            print_warning("SSL setup failed, continuing with HTTP only...")
            config.use_https = False
            save_config(config)

    # Set up Apache
    if not setup_apache(config):
        return False

    # Configure Nextcloud
    if not configure_nextcloud(config):
        return False

    # Optimize Nextcloud
    if not optimize_nextcloud(config):
        return False

    # Display Cloudflare-specific instructions if needed
    if config.using_cloudflare:
        display_cloudflare_instructions(config)

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

    # SSL configuration
    config.use_https = Confirm.ask("[bold]Enable HTTPS (recommended)?[/]", default=True)

    if config.use_https:
        config.email = Prompt.ask(
            "[bold]Enter email address (required for Let's Encrypt)[/]"
        )

        # Ask about Cloudflare
        config.using_cloudflare = Confirm.ask(
            "[bold]Are you using Cloudflare as a proxy?[/]", default=False
        )

        if config.using_cloudflare:
            display_panel(
                "Cloudflare Configuration",
                "Since you're using Cloudflare, we'll configure Nextcloud to work properly with Cloudflare's proxy.\n\n"
                "Important: Make sure to set Cloudflare's SSL/TLS encryption mode to 'Full (strict)' after setup.",
                NordColors.FROST_2,
            )

        # Ask about SSL method
        ssl_options = {
            "1": "Let's Encrypt (automatic, recommended)",
            "2": "Self-signed certificate (quick setup, not recommended for production)",
            "3": "I'll provide my own certificates (manual)",
        }

        console.print("[bold]Choose SSL certificate method:[/]")
        for key, value in ssl_options.items():
            console.print(f"  {key}. {value}")

        ssl_choice = Prompt.ask(
            "[bold]Enter your choice[/]", choices=["1", "2", "3"], default="1"
        )

        if ssl_choice == "1":
            config.ssl_method = "letsencrypt"
        elif ssl_choice == "2":
            config.ssl_method = "self-signed"
        else:
            config.ssl_method = "manual"
            config.cert_file = Prompt.ask("[bold]Enter path to SSL certificate file[/]")
            config.key_file = Prompt.ask("[bold]Enter path to SSL key file[/]")

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
                protocol = "https" if config.use_https else "http"
                display_panel(
                    "Installation Complete",
                    f"Nextcloud has been successfully installed and configured!\n\n"
                    f"You can access your Nextcloud instance at: {protocol}://{config.domain}/\n"
                    f"Admin user: {config.admin_user}\n\n"
                    f"{'SSL is properly configured for secure access.' if config.use_https else 'Consider enabling HTTPS for better security.'}\n\n"
                    f"{'Cloudflare proxy configuration has been applied.' if config.using_cloudflare else ''}",
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
