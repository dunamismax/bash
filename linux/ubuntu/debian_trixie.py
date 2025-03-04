#!/usr/bin/env python3
"""
Debian Trixie Server Setup & Hardening Utility (Unattended)
------------------------------------------------------------

This fully automated utility performs preflight checks, system updates,
package installations, user environment setup, security hardening,
service installations, maintenance tasks, system tuning, and final
health checks on a Debian Trixie server.

Features:
  • Fully unattended operation – no user interaction required
  • Comprehensive system setup and hardening
  • Beautiful Nord-themed terminal interface with Pyfiglet banner and Rich output
  • Automatic APT repository configuration and self-healing package management
  • Real-time progress tracking using spinners and progress bars
  • Robust error handling and detailed logging

Run with root privileges.
"""

import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import signal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable


# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
def install_missing_packages() -> None:
    """Automatically install required Python packages if missing."""
    required_packages = ["rich", "pyfiglet"]
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing_packages,
                check=True,
                capture_output=True,
            )
            print("Required packages installed successfully. Restarting script...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install packages: {e}")
            sys.exit(1)


install_missing_packages()

try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
    from rich.logging import RichHandler
except ImportError as e:
    print(f"Error importing libraries: {e}")
    sys.exit(1)

install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    """Global application configuration."""

    VERSION = "1.0.0"
    APP_NAME = "Debian Trixie Setup"
    APP_SUBTITLE = "Server Setup & Hardening Utility"

    PLATFORM = platform.system().lower()
    IS_WINDOWS = PLATFORM == "windows"
    IS_MACOS = PLATFORM == "darwin"
    IS_LINUX = PLATFORM == "linux"

    # Debian-specific settings
    DEBIAN_VERSION = "trixie"
    DEBIAN_CODENAME = "trixie"  # Debian 13 codename
    DEBIAN_MIRROR = "deb.debian.org"
    DEBIAN_CDN = f"https://{DEBIAN_MIRROR}/debian"

    LOG_FILE = "/var/log/debian_setup.log"
    MAX_LOG_SIZE = 10 * 1024 * 1024
    USERNAME = "sawyer"
    USER_HOME = f"/home/{USERNAME}"
    BACKUP_DIR = "/var/backups"
    TEMP_DIR = tempfile.gettempdir()

    try:
        TERM_WIDTH = shutil.get_terminal_size().columns
    except Exception:
        TERM_WIDTH = 80
    PROGRESS_WIDTH = min(50, TERM_WIDTH - 30)

    ALLOWED_PORTS = ["22", "80", "443", "32400"]

    try:
        HOSTNAME = socket.gethostname()
    except Exception:
        HOSTNAME = "Unknown"

    CONFIG_FILES = [
        "/etc/ssh/sshd_config",
        "/etc/ufw/user.rules",
        "/etc/ntp.conf",
        "/etc/sysctl.conf",
        "/etc/environment",
        "/etc/fail2ban/jail.local",
        "/etc/docker/daemon.json",
        "/etc/apt/sources.list",
    ]


# Debian Trixie default packages list
PACKAGES = [
    "bash",
    "vim",
    "nano",
    "screen",
    "tmux",
    "mc",
    "zsh",
    "htop",
    "btop",
    "tree",
    "ncdu",
    "neofetch",
    "build-essential",
    "cmake",
    "ninja-build",
    "meson",
    "gettext",
    "git",
    "pkg-config",
    "openssh-server",
    "ufw",
    "curl",
    "wget",
    "rsync",
    "sudo",
    "bash-completion",
    "python3",
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "python3-rich",
    "python3-pyfiglet",
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
    "ca-certificates",
    "software-properties-common",
    "apt-transport-https",
    "gnupg",
    "lsb-release",
    "clang",
    "llvm",
    "netcat-openbsd",
    "lsof",
    "unzip",
    "zip",
    "net-tools",
    "nmap",
    "iftop",
    "iperf3",
    "tcpdump",
    "lynis",
    "traceroute",
    "mtr",
    "iotop",
    "glances",
    "golang-go",
    "gdb",
    "cargo",
    "fail2ban",
    "rkhunter",
    "chkrootkit",
    "postgresql-client",
    "mariadb-client",
    "ruby",
    "rustc",
    "jq",
    "yq",
    "certbot",
    "p7zip-full",
    "qemu-system",
    "libvirt-clients",
    "libvirt-daemon-system",
    "virt-manager",
    "qemu-user-static",
    "nala",
]

# Global status report dictionary
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "apt_sources": {"status": "pending", "message": ""},
    "nala_install": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "packages_install": {"status": "pending", "message": ""},
    "user_env": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "tuning": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}


# ----------------------------------------------------------------
# Nord-Themed Colors and Rich Console
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette."""

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


console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
            "header": f"{NordColors.FROST_2} bold",
            "section": f"{NordColors.FROST_3} bold",
            "step": f"{NordColors.FROST_2}",
        }
    )
)


# ----------------------------------------------------------------
# Custom Exceptions
# ----------------------------------------------------------------
class SetupError(Exception):
    """Base exception for setup errors."""

    pass


class DependencyError(SetupError):
    """Raised when a required dependency is missing."""

    pass


class ConfigurationError(SetupError):
    """Raised when configuration changes fail."""

    pass


class ExecutionError(SetupError):
    """Raised when command execution fails."""

    pass


# ----------------------------------------------------------------
# Logging and Banner Helpers
# ----------------------------------------------------------------
def setup_logging() -> logging.Logger:
    """Configure logging with Rich handler and file output."""
    os.makedirs(os.path.dirname(AppConfig.LOG_FILE), exist_ok=True)
    if (
        os.path.exists(AppConfig.LOG_FILE)
        and os.path.getsize(AppConfig.LOG_FILE) > AppConfig.MAX_LOG_SIZE
    ):
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated = f"{AppConfig.LOG_FILE}.{ts}.gz"
        try:
            with (
                open(AppConfig.LOG_FILE, "rb") as fin,
                gzip.open(rotated, "wb") as fout,
            ):
                shutil.copyfileobj(fin, fout)
            open(AppConfig.LOG_FILE, "w").close()
        except Exception:
            pass
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, markup=True, console=console),
            logging.FileHandler(AppConfig.LOG_FILE),
        ],
    )
    return logging.getLogger("debian_setup")


logger = setup_logging()


def create_header() -> Panel:
    """
    Create an ASCII art header using Pyfiglet with a Nord-themed gradient.
    """
    fonts = ["slant", "small", "standard", "digital", "big"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = "=== Debian Trixie Setup ==="
    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    full_text = f"{border}\n{styled_text}{border}"
    return Panel(
        Text.from_markup(full_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message to the console and log it."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    logger.info(text)


def print_step(text: str) -> None:
    """Print a step description with spinner indication."""
    print_message(text, NordColors.FROST_3, "➜")
    logger.info(text)


def print_success(text: str) -> None:
    """Print a success message."""
    print_message(text, NordColors.GREEN, "✓")
    logger.info(f"SUCCESS: {text}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print_message(text, NordColors.YELLOW, "⚠")
    logger.warning(text)


def print_error(text: str) -> None:
    """Print an error message."""
    print_message(text, NordColors.RED, "✗")
    logger.error(text)


def print_section(title: str) -> None:
    """Print a section header using Pyfiglet."""
    console.print()
    section_art = pyfiglet.figlet_format(title, font="small")
    console.print(section_art, style="section")
    console.print(f"[section]{'-' * 40}[/section]")
    logger.info(f"--- {title} ---")


def status_report() -> None:
    """Display a table reporting the status of all setup tasks."""
    print_section("Setup Status Report")
    icons = {"success": "✓", "failed": "✗", "pending": "?", "in_progress": "⋯"}
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Debian Trixie Setup Status[/]",
        border_style=NordColors.FROST_3,
    )
    table.add_column("Task", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=f"bold {NordColors.FROST_3}")
    table.add_column("Message", style=f"{NordColors.SNOW_STORM_1}")
    for task, data in SETUP_STATUS.items():
        st = data["status"]
        msg = data["message"]
        icon = icons.get(st, "?")
        status_style = (
            "success"
            if st == "success"
            else "error"
            if st == "failed"
            else "warning"
            if st == "in_progress"
            else "step"
        )
        table.add_row(
            task.replace("_", " ").title(),
            f"[{status_style}]{icon} {st.upper()}[/]",
            msg,
        )
    console.print(table)


# ----------------------------------------------------------------
# Command Execution Helpers
# ----------------------------------------------------------------
def run_command(
    cmd: Union[List[str], str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 300,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Execute a system command and return the CompletedProcess.
    """
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logger.debug(f"Executing: {cmd_str}")
    if verbose:
        print_step(f"Executing: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}")
    try:
        if isinstance(cmd, str):
            result = subprocess.run(
                cmd,
                env=env or os.environ.copy(),
                check=check,
                shell=True,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                cmd,
                env=env or os.environ.copy(),
                check=check,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
            )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd_str}")
        raise ExecutionError(f"Command failed: {cmd_str}: {e}")
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise ExecutionError(f"Command timed out: {cmd_str}")
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise ExecutionError(f"Command execution error: {cmd_str}: {e}")


def run_with_progress(
    desc: str, func: Callable, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """
    Run a function with a Rich spinner indicator.
    """
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{desc} in progress...",
        }
    with console.status(f"[section]{desc}...[/section]"):
        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(func, *args, **kwargs)
                while not future.done():
                    time.sleep(0.5)
                result = future.result()
            elapsed = time.time() - start
            print_success(f"{desc} completed in {elapsed:.2f}s")
            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "success",
                    "message": f"{desc} succeeded in {elapsed:.2f}s.",
                }
            return result
        except Exception as e:
            elapsed = time.time() - start
            print_error(f"{desc} failed in {elapsed:.2f}s: {e}")
            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"{desc} failed: {e}",
                }
            raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    logger.info("Performing cleanup tasks before exit.")
    for fname in os.listdir(AppConfig.TEMP_DIR):
        if fname.startswith("debian_setup_"):
            try:
                os.remove(os.path.join(AppConfig.TEMP_DIR, fname))
            except Exception:
                pass
    status_report()


def signal_handler(signum: int, frame: Optional[Any]) -> None:
    """Gracefully handle termination signals."""
    sig_name = f"signal {signum}"
    if hasattr(signal, "Signals"):
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            pass
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    logger.error(f"Interrupted by {sig_name}. Exiting.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    try:
        signal.signal(sig, signal_handler)
    except (AttributeError, ValueError):
        pass
atexit.register(cleanup)


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
class Utils:
    @staticmethod
    def command_exists(cmd: str) -> bool:
        """Check if a command exists."""
        return shutil.which(cmd) is not None

    @staticmethod
    def backup_file(fp: str) -> Optional[str]:
        """Backup a file with a timestamp suffix."""
        if os.path.isfile(fp):
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = f"{fp}.bak.{ts}"
            try:
                shutil.copy2(fp, backup)
                logger.info(f"Backed up {fp} to {backup}")
                return backup
            except Exception as e:
                logger.warning(f"Backup failed for {fp}: {e}")
        return None

    @staticmethod
    def ensure_directory(
        path: str, owner: Optional[str] = None, mode: int = 0o755
    ) -> bool:
        """Ensure a directory exists with correct permissions."""
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            if owner:
                run_command(["chown", owner, path])
            logger.debug(f"Ensured directory: {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure directory {path}: {e}")
            return False

    @staticmethod
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        """Check if a TCP port is open."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex((host, port)) == 0


# ----------------------------------------------------------------
# Preflight & Environment Checkers
# ----------------------------------------------------------------
class PreflightChecker:
    def check_root(self) -> None:
        """Ensure the script runs as root."""
        if os.geteuid() != 0:
            print_error("Must run as root!")
            sys.exit(1)
        logger.info("Root privileges confirmed.")

    def check_network(self) -> bool:
        """Check for network connectivity."""
        logger.info("Checking network connectivity...")
        for host in ["google.com", "cloudflare.com", "1.1.1.1", "deb.debian.org"]:
            try:
                if run_command(["ping", "-c", "1", "-W", "5", host]).returncode == 0:
                    logger.info(f"Network OK via {host}.")
                    return True
            except Exception:
                continue
        logger.error("Network check failed.")
        return False

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        """Check if the system is running Debian."""
        logger.info("Checking OS version...")
        if not os.path.isfile("/etc/os-release"):
            logger.warning("Missing /etc/os-release")
            return None
        os_info = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_info[k] = v.strip('"')
        if os_info.get("ID") != "debian":
            logger.warning("Non-Debian system detected.")
            return None
        ver = os_info.get("VERSION_ID", "")
        logger.info(f"Detected Debian version: {ver}")
        return ("debian", ver)

    def save_config_snapshot(self) -> Optional[str]:
        """Create a snapshot archive of key configuration files."""
        logger.info("Saving configuration snapshot...")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(AppConfig.BACKUP_DIR, exist_ok=True)
        snapshot = os.path.join(AppConfig.BACKUP_DIR, f"config_snapshot_{ts}.tar.gz")
        try:
            with tarfile.open(snapshot, "w:gz") as tar:
                for cfg in AppConfig.CONFIG_FILES:
                    if os.path.isfile(cfg):
                        tar.add(cfg, arcname=os.path.basename(cfg))
                        logger.info(f"Added {cfg} to snapshot.")
            logger.info(f"Snapshot saved to {snapshot}")
            return snapshot
        except Exception as e:
            logger.warning(f"Snapshot creation failed: {e}")
            return None


# ----------------------------------------------------------------
# APT Repository Manager
# ----------------------------------------------------------------
class APTSourcesManager:
    def __init__(self) -> None:
        self.sources_list = "/etc/apt/sources.list"
        self.sources_dir = "/etc/apt/sources.list.d"
        self.backup_created = False

    def backup_sources(self) -> bool:
        """Backup existing APT sources."""
        if self.backup_created:
            return True
        try:
            if os.path.exists(self.sources_list):
                Utils.backup_file(self.sources_list)
            if os.path.isdir(self.sources_dir):
                for f in os.listdir(self.sources_dir):
                    if f.endswith(".list"):
                        Utils.backup_file(os.path.join(self.sources_dir, f))
            self.backup_created = True
            return True
        except Exception as e:
            logger.error(f"Failed to backup APT sources: {e}")
            return False

    def add_debian_cdn_source(self) -> bool:
        """Configure APT to use the Debian CDN repositories."""
        logger.info("Configuring Debian Trixie CDN sources...")
        if not self.backup_sources():
            return False
        try:
            with open(self.sources_list, "w") as f:
                f.write("# Debian Trixie repositories configured by setup utility\n")
                f.write(
                    f"deb {AppConfig.DEBIAN_CDN} trixie main contrib non-free-firmware\n"
                )
                f.write(
                    f"deb {AppConfig.DEBIAN_CDN} trixie-updates main contrib non-free-firmware\n"
                )
                f.write(
                    f"deb {AppConfig.DEBIAN_CDN} trixie-security main contrib non-free-firmware\n"
                )
                f.write("# Uncomment if you need source packages\n")
                f.write(
                    f"# deb-src {AppConfig.DEBIAN_CDN} trixie main contrib non-free-firmware\n"
                )
                f.write(
                    f"# deb-src {AppConfig.DEBIAN_CDN} trixie-updates main contrib non-free-firmware\n"
                )
                f.write(
                    f"# deb-src {AppConfig.DEBIAN_CDN} trixie-security main contrib non-free-firmware\n"
                )
            logger.info(f"CDN sources configured in {self.sources_list}")
            return True
        except Exception as e:
            logger.error(f"Failed to configure Debian CDN sources: {e}")
            return False


# ----------------------------------------------------------------
# System Updater and Package Installer
# ----------------------------------------------------------------
class SystemUpdater:
    def fix_package_issues(self) -> bool:
        """Fix common package management issues."""
        logger.info("Fixing package issues...")
        try:
            run_command(["dpkg", "--configure", "-a"])
            held = run_command(["apt-mark", "showhold"], capture_output=True)
            if held.stdout.strip():
                for pkg in held.stdout.strip().splitlines():
                    if pkg.strip():
                        run_command(["apt-mark", "unhold", pkg.strip()], check=False)
            run_command(["apt", "--fix-broken", "install", "-y"])
            run_command(["apt", "clean"])
            run_command(["apt", "autoclean", "-y"])
            check = run_command(["apt-get", "check"], capture_output=True)
            if check.returncode != 0:
                logger.error("Package issues unresolved.")
                return False
            logger.info("Package issues fixed.")
            return True
        except Exception as e:
            logger.error(f"Error fixing packages: {e}")
            return False

    def update_system(self, full_upgrade: bool = False) -> bool:
        """Update system packages."""
        logger.info("Updating system...")
        try:
            if not self.fix_package_issues():
                logger.warning("Proceeding despite package issues.")
            try:
                run_command(["nala", "update"])
            except Exception as e:
                logger.warning(f"Nala update failed: {e}; using apt update")
                run_command(["apt", "update"])
            upgrade_cmd = (
                ["nala", "full-upgrade", "-y"]
                if full_upgrade
                else ["nala", "upgrade", "-y"]
            )
            try:
                run_command(upgrade_cmd)
            except Exception as e:
                logger.warning(f"Upgrade failed with nala: {e}. Trying apt...")
                alt_cmd = (
                    ["apt", "full-upgrade", "-y"]
                    if full_upgrade
                    else ["apt", "upgrade", "-y"]
                )
                run_command(alt_cmd)
            logger.info("System update completed.")
            return True
        except Exception as e:
            logger.error(f"System update error: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        """Install missing packages from the given list."""
        logger.info("Installing packages...")
        packages = packages or PACKAGES
        if not self.fix_package_issues():
            logger.warning("Proceeding despite package issues.")
        missing = []
        for pkg in packages:
            try:
                subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                missing.append(pkg)
        if not missing:
            logger.info("All packages already installed.")
            return True
        try:
            run_command(["nala", "install", "-y"] + missing)
            logger.info("Missing packages installed using nala.")
            return True
        except Exception as e:
            logger.warning(f"Nala installation failed: {e}. Trying apt...")
            try:
                run_command(["apt", "install", "-y"] + missing)
                logger.info("Missing packages installed using apt.")
                return True
            except Exception as e2:
                logger.error(f"Package installation failed: {e2}")
                return False

    def configure_timezone(self, tz: str = "America/New_York") -> bool:
        """Set the system timezone."""
        logger.info(f"Setting timezone to {tz}...")
        tz_file = f"/usr/share/zoneinfo/{tz}"
        if not os.path.isfile(tz_file):
            logger.warning(f"Timezone file {tz_file} not found.")
            return False
        try:
            if Utils.command_exists("timedatectl"):
                run_command(["timedatectl", "set-timezone", tz])
            else:
                if os.path.exists("/etc/localtime"):
                    os.remove("/etc/localtime")
                os.symlink(tz_file, "/etc/localtime")
                with open("/etc/timezone", "w") as f:
                    f.write(f"{tz}\n")
            logger.info("Timezone configured.")
            return True
        except Exception as e:
            logger.error(f"Timezone configuration error: {e}")
            return False

    def configure_locale(self, locale: str = "en_US.UTF-8") -> bool:
        """Set the system locale."""
        logger.info(f"Setting locale to {locale}...")
        try:
            run_command(["locale-gen", locale])
            run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])
            env_file = "/etc/environment"
            lines = []
            locale_set = False
            if os.path.isfile(env_file):
                with open(env_file) as f:
                    for line in f:
                        if line.startswith("LANG="):
                            lines.append(f"LANG={locale}\n")
                            locale_set = True
                        else:
                            lines.append(line)
            if not locale_set:
                lines.append(f"LANG={locale}\n")
            with open(env_file, "w") as f:
                f.writelines(lines)
            logger.info("Locale configured.")
            return True
        except Exception as e:
            logger.error(f"Locale configuration error: {e}")
            return False


# ----------------------------------------------------------------
# User Environment Setup
# ----------------------------------------------------------------
class UserEnvironment:
    def setup_repos(self) -> bool:
        """Clone or update user repositories."""
        logger.info(f"Setting up repositories for {AppConfig.USERNAME}...")
        gh_dir = os.path.join(AppConfig.USER_HOME, "github")
        Utils.ensure_directory(
            gh_dir, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
        )
        repos = ["bash", "windows", "web", "python", "go", "misc"]
        all_success = True
        for repo in repos:
            repo_dir = os.path.join(gh_dir, repo)
            if os.path.isdir(os.path.join(repo_dir, ".git")):
                try:
                    run_command(["git", "-C", repo_dir, "pull"])
                except Exception:
                    logger.warning(f"Repo update failed: {repo}")
                    all_success = False
            else:
                try:
                    run_command(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            repo_dir,
                        ]
                    )
                except Exception:
                    logger.warning(f"Repo clone failed: {repo}")
                    all_success = False
        try:
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", gh_dir]
            )
        except Exception:
            logger.warning(f"Ownership update failed for {gh_dir}.")
            all_success = False
        return all_success

    def copy_shell_configs(self) -> bool:
        """Copy shell configuration files to user and root directories."""
        logger.info("Copying shell configuration files...")
        files = [".bashrc", ".profile"]
        src_dir = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "dotfiles"
        )
        if not os.path.isdir(src_dir):
            src_dir = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
            )
        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory {src_dir} not found.")
            return False
        dest_dirs = [AppConfig.USER_HOME, "/root"]
        all_success = True
        for file in files:
            src = os.path.join(src_dir, file)
            if not os.path.isfile(src):
                continue
            for d in dest_dirs:
                dest = os.path.join(d, file)
                copy_needed = True
                if os.path.isfile(dest) and filecmp.cmp(src, dest):
                    copy_needed = False
                if copy_needed and os.path.isfile(dest):
                    Utils.backup_file(dest)
                if copy_needed:
                    try:
                        shutil.copy2(src, dest)
                        owner = (
                            f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
                            if d == AppConfig.USER_HOME
                            else "root:root"
                        )
                        run_command(["chown", owner, dest])
                    except Exception as e:
                        logger.warning(f"Copy {src} to {dest} failed: {e}")
                        all_success = False
        return all_success

    def copy_config_folders(self) -> bool:
        """Synchronize configuration folders to the user's .config directory."""
        logger.info("Synchronizing configuration folders...")
        src_dir = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "dotfiles"
        )
        if not os.path.isdir(src_dir):
            src_dir = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
            )
        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory {src_dir} not found.")
            return False
        dest_dir = os.path.join(AppConfig.USER_HOME, ".config")
        Utils.ensure_directory(
            dest_dir, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}"
        )
        try:
            run_command(["rsync", "-a", "--update", f"{src_dir}/", f"{dest_dir}/"])
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", dest_dir]
            )
            return True
        except Exception as e:
            logger.error(f"Error copying config folders: {e}")
            return False

    def set_default_shell(self) -> bool:
        """Set the default shell for the user."""
        logger.info("Setting default shell to /bin/bash...")
        if not Utils.command_exists("bash"):
            if not SystemUpdater().install_packages(["bash"]):
                return False
        try:
            with open("/etc/shells") as f:
                shells = f.read()
            if "/bin/bash" not in shells:
                with open("/etc/shells", "a") as f:
                    f.write("/bin/bash\n")
            current_shell = (
                subprocess.check_output(
                    ["getent", "passwd", AppConfig.USERNAME], text=True
                )
                .strip()
                .split(":")[-1]
            )
            if current_shell != "/bin/bash":
                run_command(["chsh", "-s", "/bin/bash", AppConfig.USERNAME])
            return True
        except Exception as e:
            logger.error(f"Error setting default shell: {e}")
            return False


# ----------------------------------------------------------------
# Security Hardening
# ----------------------------------------------------------------
class SecurityHardener:
    def configure_ssh(self, port: int = 22) -> bool:
        """Secure and configure the SSH service."""
        logger.info("Configuring SSH service...")
        try:
            run_command(["systemctl", "enable", "--now", "ssh"])
        except Exception as e:
            logger.error(f"Error enabling SSH: {e}")
            return False
        sshd_config = "/etc/ssh/sshd_config"
        if not os.path.isfile(sshd_config):
            logger.error(f"{sshd_config} not found.")
            return False
        Utils.backup_file(sshd_config)
        ssh_settings = {
            "Port": str(port),
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "PermitEmptyPasswords": "no",
            "ChallengeResponseAuthentication": "no",
            "Protocol": "2",
            "MaxAuthTries": "5",
            "ClientAliveInterval": "600",
            "ClientAliveCountMax": "48",
            "X11Forwarding": "no",
            "PermitUserEnvironment": "no",
            "DebianBanner": "no",
            "Banner": "none",
            "LogLevel": "VERBOSE",
            "StrictModes": "yes",
            "AllowAgentForwarding": "yes",
            "AllowTcpForwarding": "yes",
        }
        try:
            with open(sshd_config) as f:
                lines = f.readlines()
            for key, value in ssh_settings.items():
                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {value}\n"
                        updated = True
                        break
                if not updated:
                    lines.append(f"{key} {value}\n")
            with open(sshd_config, "w") as f:
                f.writelines(lines)
        except Exception as e:
            logger.error(f"Error updating SSH config: {e}")
            return False
        try:
            run_command(["systemctl", "restart", "ssh"])
            return True
        except Exception as e:
            logger.error(f"Error restarting SSH: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """Configure sudoers for the designated user."""
        logger.info(f"Configuring sudoers for {AppConfig.USERNAME}...")
        try:
            run_command(["id", AppConfig.USERNAME], capture_output=True)
        except Exception:
            logger.error(f"User {AppConfig.USERNAME} not found.")
            return False
        try:
            groups = subprocess.check_output(
                ["id", "-nG", AppConfig.USERNAME], text=True
            ).split()
            if "sudo" not in groups:
                run_command(["usermod", "-aG", "sudo", AppConfig.USERNAME])
        except Exception as e:
            logger.error(f"Error updating sudo group: {e}")
            return False
        sudo_file = f"/etc/sudoers.d/99-{AppConfig.USERNAME}"
        try:
            with open(sudo_file, "w") as f:
                f.write(
                    f"{AppConfig.USERNAME} ALL=(ALL:ALL) ALL\nDefaults timestamp_timeout=15\nDefaults requiretty\n"
                )
            os.chmod(sudo_file, 0o440)
            run_command(["visudo", "-c"])
            return True
        except Exception as e:
            logger.error(f"Sudoers configuration error: {e}")
            return False

    def configure_firewall(self) -> bool:
        """Configure the UFW firewall with allowed ports."""
        logger.info("Configuring UFW firewall...")
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            if not SystemUpdater().install_packages(["ufw"]):
                return False
        try:
            run_command([ufw_cmd, "reset", "--force"], check=False)
        except Exception:
            pass
        for cmd in (
            [ufw_cmd, "default", "deny", "incoming"],
            [ufw_cmd, "default", "allow", "outgoing"],
        ):
            try:
                run_command(cmd)
            except Exception:
                pass
        for port in AppConfig.ALLOWED_PORTS:
            try:
                run_command([ufw_cmd, "allow", f"{port}/tcp"])
            except Exception:
                pass
        try:
            status = run_command([ufw_cmd, "status"], capture_output=True)
            if "inactive" in status.stdout.lower():
                run_command([ufw_cmd, "--force", "enable"])
        except Exception:
            return False
        try:
            run_command([ufw_cmd, "logging", "on"])
            run_command(["systemctl", "enable", "ufw"])
            run_command(["systemctl", "restart", "ufw"])
            return True
        except Exception:
            return False

    def configure_fail2ban(self) -> bool:
        """Configure Fail2ban service to protect SSH."""
        logger.info("Configuring Fail2ban...")
        if not Utils.command_exists("fail2ban-server"):
            if not SystemUpdater().install_packages(["fail2ban"]):
                return False
        jail = "/etc/fail2ban/jail.local"
        config = (
            "[DEFAULT]\n"
            "bantime  = 3600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "filter   = sshd\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n"
        )
        if os.path.isfile(jail):
            Utils.backup_file(jail)
        try:
            with open(jail, "w") as f:
                f.write(config)
            run_command(["systemctl", "enable", "fail2ban"])
            run_command(["systemctl", "restart", "fail2ban"])
            status = run_command(
                ["systemctl", "is-active", "fail2ban"], capture_output=True
            )
            return status.stdout.strip() == "active"
        except Exception:
            return False

    def configure_apparmor(self) -> bool:
        """Configure AppArmor for additional system security."""
        logger.info("Configuring AppArmor...")
        try:
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
                return False
            run_command(["systemctl", "enable", "apparmor"])
            run_command(["systemctl", "start", "apparmor"])
            status = run_command(
                ["systemctl", "is-active", "apparmor"], capture_output=True
            )
            if status.stdout.strip() == "active" and Utils.command_exists(
                "aa-update-profiles"
            ):
                try:
                    run_command(["aa-update-profiles"], check=False)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False


# ----------------------------------------------------------------
# Service Installation and Configuration
# ----------------------------------------------------------------
class ServiceInstaller:
    def install_nala(self) -> bool:
        """Install the Nala APT frontend."""
        logger.info("Installing Nala...")
        if Utils.command_exists("nala"):
            return True
        try:
            run_command(["apt", "update"])
            run_command(["apt", "install", "nala", "-y"])
            if Utils.command_exists("nala"):
                try:
                    run_command(["nala", "fetch", "--auto", "-y"], check=False)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False

    def install_fastfetch(self) -> bool:
        """Install the Fastfetch system information tool."""
        logger.info("Installing Fastfetch...")
        if Utils.command_exists("fastfetch"):
            return True
        temp_deb = os.path.join(AppConfig.TEMP_DIR, "fastfetch-linux-amd64.deb")
        try:
            run_command(
                [
                    "curl",
                    "-L",
                    "-o",
                    temp_deb,
                    "https://github.com/fastfetch-cli/fastfetch/releases/download/2.37.0/fastfetch-linux-amd64.deb",
                ]
            )
            run_command(["dpkg", "-i", temp_deb])
            if Utils.command_exists("nala"):
                run_command(["nala", "install", "-f", "-y"])
            else:
                run_command(["apt", "install", "-f", "-y"])
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            return Utils.command_exists("fastfetch")
        except Exception:
            return False

    def docker_config(self) -> bool:
        """Install and configure Docker."""
        logger.info("Configuring Docker...")
        if not Utils.command_exists("docker"):
            try:
                script_path = os.path.join(AppConfig.TEMP_DIR, "get-docker.sh")
                run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script_path]
                )
                os.chmod(script_path, 0o755)
                run_command([script_path])
                os.remove(script_path)
            except Exception as e:
                if not SystemUpdater().install_packages(["docker.io"]):
                    return False
        try:
            groups = subprocess.check_output(
                ["id", "-nG", AppConfig.USERNAME], text=True
            ).split()
            if "docker" not in groups:
                run_command(["usermod", "-aG", "docker", AppConfig.USERNAME])
        except Exception:
            pass
        daemon = "/etc/docker/daemon.json"
        os.makedirs("/etc/docker", exist_ok=True)
        desired = json.dumps(
            {
                "log-driver": "json-file",
                "log-opts": {"max-size": "10m", "max-file": "3"},
                "exec-opts": ["native.cgroupdriver=systemd"],
                "storage-driver": "overlay2",
                "features": {"buildkit": True},
                "default-address-pools": [{"base": "172.17.0.0/16", "size": 24}],
            },
            indent=4,
        )
        update_needed = True
        if os.path.isfile(daemon):
            try:
                with open(daemon) as f:
                    existing = json.load(f)
                if existing == json.loads(desired):
                    update_needed = False
                else:
                    Utils.backup_file(daemon)
            except Exception:
                pass
        if update_needed:
            try:
                with open(daemon, "w") as f:
                    f.write(desired)
            except Exception:
                pass
        try:
            run_command(["systemctl", "enable", "docker"])
            run_command(["systemctl", "restart", "docker"])
        except Exception:
            return False
        if not Utils.command_exists("docker-compose"):
            try:
                if Utils.command_exists("nala"):
                    run_command(["nala", "install", "docker-compose-plugin", "-y"])
                else:
                    run_command(["apt", "install", "docker-compose-plugin", "-y"])
            except Exception:
                return False
        try:
            run_command(["docker", "info"], capture_output=True)
            return True
        except Exception:
            return False

    def install_enable_tailscale(self) -> bool:
        """Install and enable Tailscale."""
        logger.info("Installing and enabling Tailscale...")
        if not Utils.command_exists("tailscale"):
            try:
                run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )
            except Exception:
                return False
        try:
            run_command(["systemctl", "enable", "tailscaled"])
            run_command(["systemctl", "start", "tailscaled"])
            status = run_command(
                ["systemctl", "is-active", "tailscaled"], capture_output=True
            )
            return status.stdout.strip() == "active"
        except Exception:
            return Utils.command_exists("tailscale")

    def deploy_user_scripts(self) -> bool:
        """Deploy user scripts to the user's bin directory."""
        logger.info("Deploying user scripts...")
        src = os.path.join(
            AppConfig.USER_HOME, "github", "bash", "linux", "debian", "_scripts"
        )
        if not os.path.isdir(src):
            src = os.path.join(
                AppConfig.USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts"
            )
        if not os.path.isdir(src):
            return False
        tgt = os.path.join(AppConfig.USER_HOME, "bin")
        Utils.ensure_directory(tgt, owner=f"{AppConfig.USERNAME}:{AppConfig.USERNAME}")
        try:
            run_command(["rsync", "-ah", "--delete", f"{src}/", f"{tgt}/"])
            run_command(["find", tgt, "-type", "f", "-exec", "chmod", "755", "{}", ";"])
            run_command(
                ["chown", "-R", f"{AppConfig.USERNAME}:{AppConfig.USERNAME}", tgt]
            )
            return True
        except Exception:
            return False

    def configure_unattended_upgrades(self) -> bool:
        """Configure unattended upgrades for automated security updates."""
        logger.info("Configuring unattended upgrades...")
        try:
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                return False
            auto_file = "/etc/apt/apt.conf.d/20auto-upgrades"
            auto_content = (
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )
            with open(auto_file, "w") as f:
                f.write(auto_content)
            unattended_file = "/etc/apt/apt.conf.d/50unattended-upgrades"
            if os.path.isfile(unattended_file):
                Utils.backup_file(unattended_file)
            unattended_content = (
                "Unattended-Upgrade::Allowed-Origins {\n"
                '    "${distro_id}:${distro_codename}";\n'
                '    "${distro_id}:${distro_codename}-security";\n'
                '    "${distro_id}:${distro_codename}-updates";\n'
                "};\n\n"
                "Unattended-Upgrade::Package-Blacklist {\n"
                "};\n\n"
                'Unattended-Upgrade::DevRelease "false";\n'
                'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";\n'
                'Unattended-Upgrade::Remove-Unused-Dependencies "true";\n'
                'Unattended-Upgrade::Automatic-Reboot "false";\n'
                'Unattended-Upgrade::Automatic-Reboot-Time "02:00";\n'
                'Unattended-Upgrade::SyslogEnable "true";\n'
            )
            with open(unattended_file, "w") as f:
                f.write(unattended_content)
            run_command(["systemctl", "enable", "unattended-upgrades"])
            run_command(["systemctl", "restart", "unattended-upgrades"])
            status = run_command(
                ["systemctl", "is-active", "unattended-upgrades"], capture_output=True
            )
            return status.stdout.strip() == "active"
        except Exception:
            return False


# ----------------------------------------------------------------
# Maintenance Manager
# ----------------------------------------------------------------
class MaintenanceManager:
    def configure_periodic(self) -> bool:
        """Set up a daily maintenance cron job."""
        logger.info("Setting up daily maintenance cron job...")
        cron_file = "/etc/cron.daily/debian_maintenance"
        marker = "# Debian maintenance script"
        if os.path.isfile(cron_file):
            with open(cron_file) as f:
                if marker in f.read():
                    return True
            Utils.backup_file(cron_file)
        content = f"""#!/bin/sh
{marker}
LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG

if command -v nala >/dev/null 2>&1; then
    nala update -qq >> $LOG 2>&1
    nala upgrade -y >> $LOG 2>&1
    nala autoremove -y >> $LOG 2>&1
    nala clean >> $LOG 2>&1
else
    apt update -qq >> $LOG 2>&1
    apt upgrade -y >> $LOG 2>&1
    apt autoremove -y >> $LOG 2>&1
    apt clean >> $LOG 2>&1
fi

df -h / >> $LOG 2>&1
echo "Completed $(date)" >> $LOG
"""
        try:
            with open(cron_file, "w") as f:
                f.write(content)
            os.chmod(cron_file, 0o755)
            return True
        except Exception:
            return False

    def backup_configs(self) -> bool:
        """Backup important configuration files."""
        logger.info("Backing up configuration files...")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(AppConfig.BACKUP_DIR, f"debian_config_{ts}")
        os.makedirs(backup_dir, exist_ok=True)
        success = True
        for file in AppConfig.CONFIG_FILES:
            if os.path.isfile(file):
                try:
                    shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
                except Exception as e:
                    logger.warning(f"Backup failed for {file}: {e}")
                    success = False
        try:
            manifest = os.path.join(backup_dir, "MANIFEST.txt")
            with open(manifest, "w") as f:
                f.write("Debian Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {socket.gethostname()}\n\nFiles:\n")
                for file in AppConfig.CONFIG_FILES:
                    if os.path.isfile(os.path.join(backup_dir, os.path.basename(file))):
                        f.write(f"- {file}\n")
        except Exception:
            pass
        return success

    def update_ssl_certificates(self) -> bool:
        """Update SSL certificates using certbot."""
        logger.info("Updating SSL certificates...")
        if not Utils.command_exists("certbot"):
            if not SystemUpdater().install_packages(["certbot"]):
                return False
        try:
            output = run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True
            ).stdout
            if "No renewals were attempted" not in output:
                run_command(["certbot", "renew"])
            return True
        except Exception:
            return False


# ----------------------------------------------------------------
# System Tuning and Home Permissions
# ----------------------------------------------------------------
class SystemTuner:
    def tune_system(self) -> bool:
        """Apply performance tuning settings to the system."""
        logger.info("Applying system tuning settings...")
        sysctl_conf = "/etc/sysctl.conf"
        if os.path.isfile(sysctl_conf):
            Utils.backup_file(sysctl_conf)
        tuning = {
            "net.core.somaxconn": "1024",
            "net.core.netdev_max_backlog": "5000",
            "net.ipv4.tcp_max_syn_backlog": "8192",
            "net.ipv4.tcp_slow_start_after_idle": "0",
            "net.ipv4.tcp_tw_reuse": "1",
            "net.ipv4.ip_local_port_range": "1024 65535",
            "net.ipv4.tcp_rmem": "4096 87380 16777216",
            "net.ipv4.tcp_wmem": "4096 65536 16777216",
            "net.ipv4.tcp_mtu_probing": "1",
            "fs.file-max": "2097152",
            "vm.swappiness": "10",
            "vm.dirty_ratio": "60",
            "vm.dirty_background_ratio": "2",
            "kernel.sysrq": "0",
            "kernel.core_uses_pid": "1",
            "net.ipv4.conf.default.rp_filter": "1",
            "net.ipv4.conf.all.rp_filter": "1",
        }
        try:
            with open(sysctl_conf) as f:
                content = f.read()
            marker = "# Performance tuning settings for Debian"
            if marker in content:
                content = re.split(marker, content)[0]
            content += f"\n{marker}\n" + "".join(
                f"{k} = {v}\n" for k, v in tuning.items()
            )
            with open(sysctl_conf, "w") as f:
                f.write(content)
            run_command(["sysctl", "-p"])
            return True
        except Exception:
            return False

    def home_permissions(self) -> bool:
        """Secure user home directory permissions."""
        logger.info(f"Securing home directory for {AppConfig.USERNAME}...")
        try:
            run_command(
                [
                    "chown",
                    "-R",
                    f"{AppConfig.USERNAME}:{AppConfig.USERNAME}",
                    AppConfig.USER_HOME,
                ]
            )
            run_command(["chmod", "750", AppConfig.USER_HOME])
            for sub in [".ssh", ".gnupg", ".config"]:
                d = os.path.join(AppConfig.USER_HOME, sub)
                if os.path.isdir(d):
                    run_command(["chmod", "700", d])
            run_command(
                [
                    "find",
                    AppConfig.USER_HOME,
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    ";",
                ]
            )
            if Utils.command_exists("setfacl"):
                run_command(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{AppConfig.USERNAME}:rwX,g:{AppConfig.USERNAME}:r-X,o::---",
                        AppConfig.USER_HOME,
                    ]
                )
            return True
        except Exception:
            return False


# ----------------------------------------------------------------
# Final Health Check and Cleanup
# ----------------------------------------------------------------
class FinalChecker:
    def system_health_check(self) -> Dict[str, Any]:
        """Perform a system health check and return details."""
        logger.info("Performing system health check...")
        health: Dict[str, Any] = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            health["uptime"] = uptime
        except Exception:
            pass
        try:
            df_lines = (
                subprocess.check_output(["df", "-h", "/"], text=True)
                .strip()
                .splitlines()
            )
            if len(df_lines) >= 2:
                data = df_lines[1].split()
                health["disk"] = {
                    "total": data[1],
                    "used": data[2],
                    "available": data[3],
                    "percent_used": data[4],
                }
        except Exception:
            pass
        try:
            free_lines = (
                subprocess.check_output(["free", "-h"], text=True).strip().splitlines()
            )
            for line in free_lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    health["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                    }
        except Exception:
            pass
        try:
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]
            health["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
        except Exception:
            pass
        try:
            dmesg_output = subprocess.check_output(
                ["dmesg", "--level=err,crit,alert,emerg"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            health["kernel_errors"] = bool(dmesg_output)
        except Exception:
            pass
        try:
            if Utils.command_exists("nala"):
                updates = (
                    subprocess.check_output(
                        ["nala", "list", "--upgradable"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                    .strip()
                    .splitlines()
                )
            else:
                updates = (
                    subprocess.check_output(
                        ["apt", "list", "--upgradable"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                    .strip()
                    .splitlines()
                )
            security_updates = sum(1 for line in updates if "security" in line.lower())
            total_updates = len(updates) - 1
            health["updates"] = {"total": total_updates, "security": security_updates}
        except Exception:
            pass
        return health

    def verify_firewall_rules(self) -> bool:
        """Verify that firewall rules are set correctly."""
        logger.info("Verifying firewall rules...")
        try:
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            if "inactive" in ufw_status.lower():
                return False
        except Exception:
            return False
        for port in AppConfig.ALLOWED_PORTS:
            try:
                result = subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if result.returncode != 0 and not Utils.is_port_open(int(port)):
                    return False
            except Exception:
                return False
        return True

    def final_checks(self) -> bool:
        """Perform final system checks and return True if all pass."""
        logger.info("Performing final system checks...")
        all_passed = True
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            disk_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            disk_percent = int(disk_line.split()[4].strip("%"))
            if disk_percent > 90:
                logger.warning(f"High disk usage: {disk_percent}%")
                all_passed = False
            load_avg = open("/proc/loadavg").read().split()[:3]
            cpu_count = os.cpu_count() or 1
            if float(load_avg[1]) > cpu_count:
                logger.warning(f"High system load: {load_avg[1]} (CPUs: {cpu_count})")
                all_passed = False
            services = [
                "ssh",
                "ufw",
                "fail2ban",
                "docker",
                "tailscaled",
                "unattended-upgrades",
            ]
            for svc in services:
                status = subprocess.run(
                    ["systemctl", "is-active", svc],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if status.stdout.strip() != "active" and svc in ["ssh", "ufw"]:
                    logger.warning(f"Critical service not active: {svc}")
                    all_passed = False
            try:
                unattended_output = subprocess.check_output(
                    ["unattended-upgrade", "--dry-run", "--debug"],
                    text=True,
                    stderr=subprocess.STDOUT,
                )
                if any(
                    "Packages that will be upgraded:" in line
                    and "0 upgrades" not in line
                    for line in unattended_output.splitlines()
                ):
                    logger.warning("Pending upgrades detected")
                    all_passed = False
            except Exception:
                pass
            return all_passed
        except Exception as e:
            logger.error(f"Error during final checks: {e}")
            return False

    def cleanup_system(self) -> bool:
        """Perform system cleanup tasks."""
        logger.info("Performing system cleanup...")
        success = True
        try:
            if Utils.command_exists("nala"):
                run_command(["nala", "autoremove", "-y"])
                run_command(["nala", "clean"])
            else:
                run_command(["apt", "autoremove", "-y"])
                run_command(["apt", "clean"])
            try:
                current_kernel = subprocess.check_output(
                    ["uname", "-r"], text=True
                ).strip()
                installed = (
                    subprocess.check_output(
                        ["dpkg", "--list", "linux-image-*", "linux-headers-*"],
                        text=True,
                    )
                    .strip()
                    .splitlines()
                )
                old_kernels = [
                    line.split()[1]
                    for line in installed
                    if line.startswith("ii")
                    and line.split()[1]
                    not in (
                        f"linux-image-{current_kernel}",
                        f"linux-headers-{current_kernel}",
                    )
                    and "generic" in line.split()[1]
                ]
                if len(old_kernels) > 1:
                    old_kernels.sort()
                    to_remove = old_kernels[:-1]
                    if to_remove:
                        run_command(["apt", "purge", "-y"] + to_remove)
            except Exception as e:
                logger.warning(f"Old kernel cleanup failed: {e}")
            if Utils.command_exists("journalctl"):
                run_command(["journalctl", "--vacuum-time=7d"])
            for tmp in ["/tmp", "/var/tmp"]:
                try:
                    run_command(
                        [
                            "find",
                            tmp,
                            "-type",
                            "f",
                            "-atime",
                            "+7",
                            "-not",
                            "-path",
                            "*/\\.*",
                            "-delete",
                        ]
                    )
                except Exception:
                    pass
            try:
                log_files = (
                    subprocess.check_output(
                        ["find", "/var/log", "-type", "f", "-size", "+50M"], text=True
                    )
                    .strip()
                    .splitlines()
                )
                for lf in log_files:
                    with open(lf, "rb") as fin, gzip.open(f"{lf}.gz", "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                    open(lf, "w").close()
            except Exception:
                pass
            return success
        except Exception:
            return False

    def auto_reboot(self) -> None:
        """Automatically reboot the system after a delay."""
        logger.info("Setup complete. Rebooting in 60 seconds.")
        print_success("Setup completed successfully. Rebooting in 60 seconds...")
        time.sleep(60)
        try:
            run_command(["shutdown", "-r", "now"])
        except Exception:
            pass


# ----------------------------------------------------------------
# Main Orchestration Class
# ----------------------------------------------------------------
class DebianServerSetup:
    def __init__(self) -> None:
        self.success = True
        self.start_time = time.time()
        self.preflight = PreflightChecker()
        self.apt_sources = APTSourcesManager()
        self.updater = SystemUpdater()
        self.user_env = UserEnvironment()
        self.security = SecurityHardener()
        self.services = ServiceInstaller()
        self.maintenance = MaintenanceManager()
        self.tuner = SystemTuner()
        self.final_checker = FinalChecker()

    def run(self) -> int:
        """Run the complete Debian server setup and hardening process."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(create_header())
        print_step(f"Starting Debian Trixie setup at {now}")
        logger.info(f"Starting Debian Trixie Server Setup at {now}")

        # Phase 1: Pre-flight Checks
        print_section("Phase 1: Pre-flight Checks")
        try:
            run_with_progress(
                "Checking root privileges",
                self.preflight.check_root,
                task_name="preflight",
            )
            if not self.preflight.check_network():
                logger.error("Network check failed.")
                SETUP_STATUS["preflight"] = {
                    "status": "failed",
                    "message": "Network check failed",
                }
                sys.exit(1)
            if not self.preflight.check_os_version():
                logger.warning("OS check failed – proceeding with caution.")
            self.preflight.save_config_snapshot()
        except Exception as e:
            logger.error(f"Preflight error: {e}")
            self.success = False

        # Phase 2: Configure APT Sources
        print_section("Phase 2: Configure APT Sources")
        try:
            if not run_with_progress(
                "Configuring Debian Trixie APT sources",
                self.apt_sources.add_debian_cdn_source,
                task_name="apt_sources",
            ):
                logger.error("APT sources configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"APT sources error: {e}")
            self.success = False

        # Fix broken packages
        print_section("Fix Broken Packages")

        def fix_broken():
            backup_dir = "/etc/apt/apt.conf.d/"
            for fname in os.listdir(backup_dir):
                if fname.startswith("50unattended-upgrades.bak."):
                    try:
                        os.remove(os.path.join(backup_dir, fname))
                    except Exception:
                        pass
            return run_command(["apt", "--fix-broken", "install", "-y"])

        run_with_progress(
            "Running apt --fix-broken install", fix_broken, task_name="fix_broken"
        )

        # Phase 3: Installing Nala
        print_section("Phase 3: Installing Nala")
        try:
            if not run_with_progress(
                "Installing Nala", self.services.install_nala, task_name="nala_install"
            ):
                logger.warning("Nala installation failed, will use apt instead.")
        except Exception as e:
            logger.error(f"Nala error: {e}")
            logger.warning("Will use apt instead of nala.")

        # Phase 4: System Update & Basic Configuration
        print_section("Phase 4: System Update & Basic Configuration")
        try:
            if not run_with_progress(
                "Updating system", self.updater.update_system, task_name="system_update"
            ):
                logger.warning("System update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"System update error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Installing packages",
                self.updater.install_packages,
                task_name="packages_install",
            ):
                logger.warning("Package installation issues.")
                self.success = False
        except Exception as e:
            logger.error(f"Package installation error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring timezone", self.updater.configure_timezone
            ):
                logger.warning("Timezone configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring locale", self.updater.configure_locale
            ):
                logger.warning("Locale configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Locale error: {e}")
            self.success = False

        # Phase 5: User Environment Setup
        print_section("Phase 5: User Environment Setup")
        try:
            if not run_with_progress(
                "Setting up user repositories",
                self.user_env.setup_repos,
                task_name="user_env",
            ):
                logger.warning("User repository setup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"User repos error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Copying shell configs", self.user_env.copy_shell_configs
            ):
                logger.warning("Shell configuration update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Shell configs error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Copying config folders", self.user_env.copy_config_folders
            ):
                logger.warning("Config folder copy failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Config folders error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Setting default shell", self.user_env.set_default_shell
            ):
                logger.warning("Default shell update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Set shell error: {e}")
            self.success = False

        # Phase 6: Security & Hardening
        print_section("Phase 6: Security & Hardening")
        try:
            if not run_with_progress(
                "Configuring SSH", self.security.configure_ssh, task_name="security"
            ):
                logger.warning("SSH configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSH error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring sudoers", self.security.setup_sudoers
            ):
                logger.warning("Sudoers configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Sudoers error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring firewall", self.security.configure_firewall
            ):
                logger.warning("Firewall configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring Fail2ban", self.security.configure_fail2ban
            ):
                logger.warning("Fail2ban configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fail2ban error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring AppArmor", self.security.configure_apparmor
            ):
                logger.warning("AppArmor configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"AppArmor error: {e}")
            self.success = False

        # Phase 7: Service Installations
        print_section("Phase 7: Service Installations")
        try:
            if not run_with_progress(
                "Installing Fastfetch",
                self.services.install_fastfetch,
                task_name="services",
            ):
                logger.warning("Fastfetch installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fastfetch error: {e}")
            self.success = False
        try:
            if not run_with_progress("Configuring Docker", self.services.docker_config):
                logger.warning("Docker configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Docker error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Installing Tailscale", self.services.install_enable_tailscale
            ):
                logger.warning("Tailscale installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Tailscale error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring unattended upgrades",
                self.services.configure_unattended_upgrades,
            ):
                logger.warning("Unattended upgrades configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Unattended upgrades error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Deploying user scripts", self.services.deploy_user_scripts
            ):
                logger.warning("User scripts deployment failed.")
                self.success = False
        except Exception as e:
            logger.error(f"User scripts error: {e}")
            self.success = False

        # Phase 8: Maintenance Tasks
        print_section("Phase 8: Maintenance Tasks")
        try:
            if not run_with_progress(
                "Configuring periodic maintenance",
                self.maintenance.configure_periodic,
                task_name="maintenance",
            ):
                logger.warning("Periodic maintenance configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Periodic maintenance error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Backing up configurations", self.maintenance.backup_configs
            ):
                logger.warning("Configuration backup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Backup configs error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Updating SSL certificates", self.maintenance.update_ssl_certificates
            ):
                logger.warning("SSL certificate update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSL update error: {e}")
            self.success = False

        # Phase 9: System Tuning & Home Permissions
        print_section("Phase 9: System Tuning & Permissions")
        try:
            if not run_with_progress(
                "Applying system tuning", self.tuner.tune_system, task_name="tuning"
            ):
                logger.warning("System tuning failed.")
                self.success = False
        except Exception as e:
            logger.error(f"System tuning error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Securing home directory", self.tuner.home_permissions
            ):
                logger.warning("Home directory security failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Home permissions error: {e}")
            self.success = False

        # Phase 10: Final Checks & Cleanup
        print_section("Phase 10: Final Checks & Cleanup")
        SETUP_STATUS["final"] = {
            "status": "in_progress",
            "message": "Running final checks...",
        }
        try:
            health_info = self.final_checker.system_health_check()
            logger.info(f"Health check results: {health_info}")
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self.success = False
        try:
            if not self.final_checker.verify_firewall_rules():
                logger.warning("Firewall verification failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall verification error: {e}")
            self.success = False
        final_result = True
        try:
            final_result = self.final_checker.final_checks()
            if not final_result:
                logger.warning("Final system checks detected issues.")
                self.success = False
        except Exception as e:
            logger.error(f"Final checks error: {e}")
            self.success = False
            final_result = False
        try:
            if not self.final_checker.cleanup_system():
                logger.warning("System cleanup had issues.")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        duration = time.time() - self.start_time
        minutes, seconds = divmod(duration, 60)
        if self.success and final_result:
            SETUP_STATUS["final"] = {
                "status": "success",
                "message": f"Completed in {int(minutes)}m {int(seconds)}s.",
            }
        else:
            SETUP_STATUS["final"] = {
                "status": "failed",
                "message": f"Completed with issues in {int(minutes)}m {int(seconds)}s.",
            }
        status_report()
        if self.success and final_result:
            self.final_checker.auto_reboot()
        else:
            print_warning(
                "Setup completed with issues. Please review the log and status report."
            )
        return 0 if self.success and final_result else 1


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> int:
    """Main entry point for the Debian Trixie Setup Utility."""
    try:
        console.print(create_header())
        print_step(
            f"Starting Debian Trixie Setup & Hardening Utility v{AppConfig.VERSION}"
        )
        print_step(f"System: {platform.system()} {platform.release()}")
        print_step(f"Hostname: {AppConfig.HOSTNAME}")
        return DebianServerSetup().run()
    except KeyboardInterrupt:
        print_warning("Process interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
