#!/usr/bin/env python3
"""
Ubuntu Server Initialization & Hardening Utility
--------------------------------------------------------------------
Description:
  This script automates the setup, configuration, and maintenance of an Ubuntu server.
  It is divided into the following phases:
    1. Pre-flight Checks
    2. Nala Installation (ensuring a fast, modern apt frontend is available)
    3. System Update & Basic Configuration
    4. User Environment Setup
    5. Security & Access Hardening
    6. Service Installations
    7. Maintenance Tasks
    8. System Tuning & Permissions
    9. Final Checks & Cleanup

  Features:
    - Comprehensive error handling with detailed logging
    - Secure configuration of core services (SSH, UFW, Fail2ban, etc.)
    - Installation of modern tooling (Docker, Tailscale, VS Code, etc.)
    - System performance tuning and security hardening
    - Automatic backup of critical configuration files

Author: dunamismax | License: MIT | Version: 4.2.0
"""

import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import signal
from typing import Any, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

# ------------------------------------------------------------------------------
# Environment Configuration & Constants
# ------------------------------------------------------------------------------
USERNAME = "sawyer"
USER_HOME = f"/home/{USERNAME}"
BACKUP_DIR = "/var/backups"
TEMP_DIR = tempfile.gettempdir()
LOG_FILE = "/var/log/ubuntu_setup.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB

# ------------------------------------------------------------------------------
# Software versions and download URLs
# ------------------------------------------------------------------------------
PLEX_VERSION = "1.41.4.9463-630c9f557"  # Updated February 7, 2025
PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_amd64.deb"

FASTFETCH_VERSION = "2.37.0"
FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"

CONFIG_FILES = [
    "/etc/ssh/sshd_config",
    "/etc/ufw/user.rules",
    "/etc/ntp.conf",
    "/etc/sysctl.conf",
    "/etc/environment",
    "/etc/fail2ban/jail.local",
    "/etc/docker/daemon.json",
    "/etc/caddy/Caddyfile",
]
ALLOWED_PORTS = ["22", "80", "443", "32400"]

PACKAGES = [
    # Shells, editors, and utilities
    "bash",
    "vim",
    "nano",
    "screen",
    "tmux",
    "mc",
    "zsh",
    "htop",
    "btop",
    "foot",
    "foot-themes",
    "tree",
    "ncdu",
    "neofetch",
    # Development and build tools
    "build-essential",
    "cmake",
    "ninja-build",
    "meson",
    "gettext",
    "git",
    "pkg-config",
    # SSH, firewall, and system management
    "openssh-server",
    "ufw",
    "curl",
    "wget",
    "rsync",
    "sudo",
    "bash-completion",
    # Python and libraries
    "python3",
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "libssl-dev",
    "libffi-dev",
    "zlib1g-dev",
    "libreadline-dev",
    "libbz2-dev",
    "tk-dev",
    "xz-utils",
    "libncurses5-dev",
    "libgdbm-dev",
    "libnss3-dev",
    "liblzma-dev",
    "libxml2-dev",
    "libxmlsec1-dev",
    # Certificates and system tools
    "ca-certificates",
    "software-properties-common",
    "apt-transport-https",
    "gnupg",
    "lsb-release",
    # Compilers and low-level tools
    "clang",
    "llvm",
    "netcat-openbsd",
    "lsof",
    "unzip",
    "zip",
    # Networking tools
    "net-tools",
    "nmap",
    "iftop",
    "iperf3",
    "tcpdump",
    "lynis",
    "traceroute",
    "mtr",
    # Monitoring tools
    "iotop",
    "glances",
    # Programming languages and debuggers
    "golang-go",
    "gdb",
    "cargo",
    # Security tools
    "fail2ban",
    "rkhunter",
    "chkrootkit",
    # Database clients and servers
    "postgresql-client",
    "mysql-client",
    # Scripting languages and utilities
    "ruby",
    "rustc",
    "jq",
    "yq",
    "certbot",
    # Archiving and compression
    "p7zip-full",
    # Virtualization tools
    "qemu-system",
    "libvirt-clients",
    "libvirt-daemon-system",
    "virt-manager",
    "qemu-user-static",
    # Nala (apt frontend)
    "nala",
]

# Global status for reporting
SETUP_STATUS = {
    "preflight": {"status": "pending", "message": ""},
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

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """Custom formatter that applies Nord color palette to log messages based on level."""

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging() -> logging.Logger:
    """
    Configure logging with file and console handlers using Nord color palette.
    Returns:
        Configured logger instance.
    """
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, mode=0o700, exist_ok=True)
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        LogManager.rotate_logs()
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    formatter = NordColorFormatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    if sys.stderr.isatty():
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger


logger = setup_logging()


def print_section(title: str):
    """
    Display a formatted section header using Nord color palette.
    """
    border = "─" * 60
    print(f"{NORD8}{border}{NC}")
    print(f"{NORD8}  {title}{NC}")
    print(f"{NORD8}{border}{NC}")
    logger.info(f"--- {title} ---")


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """Perform final cleanup tasks before exiting."""
    logger.info("Performing cleanup tasks before exit.")
    for temp_file in os.listdir(tempfile.gettempdir()):
        if temp_file.startswith("ubuntu_setup_"):
            try:
                os.remove(os.path.join(tempfile.gettempdir(), temp_file))
            except Exception:
                pass
    if any(item["status"] != "pending" for item in SETUP_STATUS.values()):
        print_status_report()


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Run-With-Progress Helper
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, task_name=None, **kwargs):
    """
    Run a function while displaying status updates.
    """
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }
    print(f"{NORD8}[*] {description}...{NC}")
    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            while not future.done():
                time.sleep(0.5)
            try:
                result = future.result()
                elapsed = time.time() - start_time
                print(f"{NORD14}[✓] {description} completed in {elapsed:.2f}s{NC}")
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "success",
                        "message": f"{description} completed successfully.",
                    }
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                print(
                    f"{NORD11}[✗] {description} failed in {elapsed:.2f}s: {str(e)}{NC}"
                )
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": f"{description} failed: {str(e)}",
                    }
                raise
    except Exception as e:
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "failed",
                "message": f"{description} failed: {str(e)}",
            }
        raise


# ------------------------------------------------------------------------------
# Utility Functions & Classes
# ------------------------------------------------------------------------------
class Utils:
    """Utility functions for common operations."""

    @staticmethod
    def run_command(
        cmd: Union[List[str], str],
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        logger.debug(f"Executing command: {cmd_str}")
        try:
            result = subprocess.run(
                cmd, check=check, capture_output=capture_output, text=text, **kwargs
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd_str} with exit code {e.returncode}")
            logger.debug(f"Error output: {getattr(e, 'stderr', 'N/A')}")
            raise

    @staticmethod
    def command_exists(cmd: str) -> bool:
        return shutil.which(cmd) is not None

    @staticmethod
    def backup_file(file_path: str) -> Optional[str]:
        if os.path.isfile(file_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = f"{file_path}.bak.{timestamp}"
            try:
                shutil.copy2(file_path, backup)
                logger.info(f"Backed up {file_path} to {backup}")
                return backup
            except Exception as e:
                logger.warning(f"Failed to backup {file_path}: {e}")
                return None
        else:
            logger.warning(f"File {file_path} not found; skipping backup.")
            return None

    @staticmethod
    def ensure_directory(
        path: str, owner: Optional[str] = None, mode: int = 0o755
    ) -> bool:
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            if owner:
                Utils.run_command(["chown", owner, path])
            logger.debug(f"Ensured directory exists: {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure directory {path}: {e}")
            return False

    @staticmethod
    def generate_unique_filename(base_path: str, extension: str = "") -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        ext = f".{extension}" if extension else ""
        return f"{base_path}_{timestamp}{ext}"

    @staticmethod
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0


class LogManager:
    """Manage log files, including rotation and cleanup."""

    @staticmethod
    def rotate_logs() -> bool:
        logger.info("Rotating logs...")
        if not os.path.isfile(LOG_FILE):
            logger.warning(f"Log file {LOG_FILE} does not exist.")
            return False
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated_file = f"{LOG_FILE}.{timestamp}.gz"
        try:
            with open(LOG_FILE, "rb") as f_in:
                with gzip.open(rotated_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            open(LOG_FILE, "w").close()
            logger.info(f"Log rotated to {rotated_file}.")
            return True
        except Exception as e:
            logger.warning(f"Log rotation failed: {e}")
            return False


def print_status_report():
    """Display a formatted report of all setup tasks and their status."""
    print_section("Setup Status Report")
    icons = {
        "success": "✓",
        "failed": "✗",
        "pending": "?",
        "in_progress": "⋯",
        "skipped": "⏭",
        "warning": "⚠",
    }
    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD9,
        "skipped": NORD8,
        "warning": NORD13,
    }
    descriptions = {
        "preflight": "Pre-flight Checks",
        "nala_install": "Nala Installation",
        "system_update": "System Update",
        "packages_install": "Package Installation",
        "user_env": "User Environment Setup",
        "security": "Security Hardening",
        "services": "Service Installation",
        "maintenance": "Maintenance Tasks",
        "tuning": "System Tuning",
        "final": "Final Checks & Cleanup",
    }
    for task, data in SETUP_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)
        icon = icons[status]
        color = colors[status]
        print(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")


# ------------------------------------------------------------------------------
# Phase 1: Pre-flight Checks
# ------------------------------------------------------------------------------
class PreflightChecker:
    """Perform initial system checks before proceeding with setup."""

    def check_root(self) -> None:
        if os.geteuid() != 0:
            print(f"{NORD11}Error: This script must be run as root.{NC}")
            print(f"Please run with: sudo {sys.argv[0]}")
            sys.exit(1)
        logger.info("Root privileges confirmed.")

    def check_network(self) -> bool:
        logger.info("Performing network connectivity check...")
        test_hosts = ["google.com", "cloudflare.com", "1.1.1.1"]
        for host in test_hosts:
            try:
                result = Utils.run_command(
                    ["ping", "-c", "1", "-W", "5", host],
                    check=False,
                    capture_output=True,
                )
                if result.returncode == 0:
                    logger.info(f"Network connectivity verified via {host}.")
                    return True
            except Exception as e:
                logger.debug(f"Ping to {host} failed: {e}")
        logger.error("No network connectivity. Please verify your network settings.")
        return False

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        logger.info("Checking OS version...")
        if not os.path.isfile("/etc/os-release"):
            logger.warning("Cannot determine OS: /etc/os-release not found")
            return None
        os_info = {}
        with open("/etc/os-release", "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os_info[key] = value.strip('"')
        if os_info.get("ID") != "ubuntu":
            logger.warning(
                f"Detected non-Ubuntu system: {os_info.get('ID', 'unknown')}"
            )
            return None
        version = os_info.get("VERSION_ID", "").strip('"')
        pretty_name = os_info.get("PRETTY_NAME", "Unknown")
        logger.info(f"Detected OS: {pretty_name}")
        supported = ["20.04", "22.04", "24.04"]
        if version not in supported:
            logger.warning(
                f"Ubuntu {version} is not officially supported. Supported: {', '.join(supported)}"
            )
        return ("ubuntu", version)

    def save_config_snapshot(self) -> Optional[str]:
        logger.info("Saving configuration snapshot...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        snapshot_file = os.path.join(BACKUP_DIR, f"config_snapshot_{timestamp}.tar.gz")
        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                for cfg in CONFIG_FILES:
                    if os.path.isfile(cfg):
                        tar.add(cfg, arcname=os.path.basename(cfg))
                        logger.info(f"Included {cfg} in snapshot.")
                    else:
                        logger.debug(f"Configuration file {cfg} not found; skipping.")
            logger.info(f"Configuration snapshot saved to {snapshot_file}")
            return snapshot_file
        except Exception as e:
            logger.warning(f"Failed to create configuration snapshot: {e}")
            return None


# ------------------------------------------------------------------------------
# Phase 2: System Update & Basic Configuration
# ------------------------------------------------------------------------------
class SystemUpdater:
    """Update the system, install packages, and configure basic settings."""

    def update_system(self, full_upgrade: bool = False) -> bool:
        logger.info("Updating system repositories and packages using Nala...")
        try:
            Utils.run_command(["nala", "update"])
            cmd = (
                ["nala", "upgrade", "-y"]
                if not full_upgrade
                else ["nala", "full-upgrade", "-y"]
            )
            Utils.run_command(cmd)
            logger.info("System update and upgrade completed.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"System update failed: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        logger.info("Installing essential packages using Nala...")
        packages = packages or PACKAGES
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
                logger.debug(f"Package not installed: {pkg}")
            else:
                logger.debug(f"Package already installed: {pkg}")
        if not missing:
            logger.info("All required packages are already installed.")
            return True
        essential_packages = [
            "bash",
            "vim",
            "nano",
            "sudo",
            "openssh-server",
            "ufw",
            "python3",
            "curl",
            "wget",
            "ca-certificates",
        ]
        failed_packages = []
        installer = ["nala", "install", "-y"]
        logger.info(f"Installing {len(missing)} missing packages...")
        batch_size = 10
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            logger.info(f"Installing batch {i // batch_size + 1}...")
            try:
                Utils.run_command(installer + batch)
                logger.info(f"Batch {i // batch_size + 1} installed successfully.")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Batch installation failed: {e}")
                for pkg in batch:
                    try:
                        logger.info(f"Trying individual installation of {pkg}...")
                        Utils.run_command(installer + [pkg], check=False)
                        logger.info(f"Successfully installed {pkg}.")
                    except Exception as pkg_error:
                        failed_packages.append(pkg)
                        logger.warning(f"Failed to install {pkg}: {pkg_error}")
        essential_failed = [pkg for pkg in failed_packages if pkg in essential_packages]
        if failed_packages:
            logger.warning(
                f"Failed to install {len(failed_packages)} packages: {', '.join(failed_packages)}"
            )
        if essential_failed:
            logger.error(
                f"Failed to install essential packages: {', '.join(essential_failed)}"
            )
            return False
        logger.info(
            f"Installed {len(missing) - len(failed_packages)} of {len(missing)} packages successfully."
        )
        return True

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        logger.info(f"Setting timezone to {timezone}...")
        tz_file = f"/usr/share/zoneinfo/{timezone}"
        if not os.path.isfile(tz_file):
            logger.warning(f"Timezone file for {timezone} not found.")
            return False
        try:
            if Utils.command_exists("timedatectl"):
                Utils.run_command(["timedatectl", "set-timezone", timezone])
            else:
                if os.path.exists("/etc/localtime"):
                    os.remove("/etc/localtime")
                os.symlink(tz_file, "/etc/localtime")
                with open("/etc/timezone", "w") as f:
                    f.write(f"{timezone}\n")
            logger.info("Timezone configured successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to set timezone: {e}")
            return False

    def configure_locale(self, locale: str = "en_US.UTF-8") -> bool:
        """
        Set the system locale.
        """
        logger.info(f"Setting locale to {locale}...")
        try:
            Utils.run_command(["locale-gen", locale])
            Utils.run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])
            env_file = "/etc/environment"
            env_content = []
            locale_added = False
            if os.path.isfile(env_file):
                with open(env_file, "r") as f:
                    for line in f:
                        if line.strip().startswith("LANG="):
                            env_content.append(f"LANG={locale}\n")
                            locale_added = True
                        else:
                            env_content.append(line)
            if not locale_added:
                env_content.append(f"LANG={locale}\n")
            with open(env_file, "w") as f:
                f.writelines(env_content)
            logger.info("Locale configured successfully.")
            return True
        except Exception as e:
            logger.error(f"Locale configuration failed: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 3: User Environment Setup
# ------------------------------------------------------------------------------
class UserEnvironment:
    """Set up user environment, repositories, and configuration files."""

    def setup_repos(self) -> bool:
        logger.info(f"Setting up GitHub repositories for user '{USERNAME}'...")
        gh_dir = os.path.join(USER_HOME, "github")
        Utils.ensure_directory(gh_dir, owner=f"{USERNAME}:{USERNAME}")
        repos = ["bash", "windows", "web", "python", "go", "misc"]
        all_success = True
        for repo in repos:
            repo_dir = os.path.join(gh_dir, repo)
            if os.path.isdir(os.path.join(repo_dir, ".git")):
                logger.info(f"Repository '{repo}' exists; pulling latest changes...")
                try:
                    Utils.run_command(["git", "-C", repo_dir, "pull"], check=False)
                except subprocess.CalledProcessError:
                    logger.warning(f"Failed to update repository '{repo}'.")
                    all_success = False
            else:
                logger.info(f"Cloning repository '{repo}'...")
                try:
                    Utils.run_command(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            repo_dir,
                        ],
                        check=False,
                    )
                    logger.info(f"Repository '{repo}' cloned successfully.")
                except subprocess.CalledProcessError:
                    logger.warning(f"Failed to clone repository '{repo}'.")
                    all_success = False
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", gh_dir])
            logger.info(f"Ownership of '{gh_dir}' set to '{USERNAME}'.")
        except subprocess.CalledProcessError:
            logger.warning(f"Failed to set ownership of '{gh_dir}'.")
            all_success = False
        return all_success

    def copy_shell_configs(self) -> bool:
        logger.info("Updating shell configuration files...")
        files_to_copy = [".bashrc", ".profile"]
        source_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        if not os.path.isdir(source_dir):
            logger.warning(
                f"Source directory {source_dir} not found. Skipping shell config update."
            )
            return False
        destination_dirs = [USER_HOME, "/root"]
        all_successful = True
        for file in files_to_copy:
            src = os.path.join(source_dir, file)
            if not os.path.isfile(src):
                logger.debug(f"Source file {src} not found; skipping.")
                continue
            for dest_dir in destination_dirs:
                dest = os.path.join(dest_dir, file)
                copy_needed = True
                if os.path.isfile(dest) and filecmp.cmp(src, dest):
                    logger.info(f"File {dest} is already up-to-date.")
                    copy_needed = False
                if copy_needed and os.path.isfile(dest):
                    Utils.backup_file(dest)
                if copy_needed:
                    try:
                        shutil.copy2(src, dest)
                        owner = (
                            f"{USERNAME}:{USERNAME}"
                            if dest_dir == USER_HOME
                            else "root:root"
                        )
                        Utils.run_command(["chown", owner, dest])
                        logger.info(f"Copied {src} to {dest}.")
                    except Exception as e:
                        logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        all_successful = False
        return all_successful

    def copy_config_folders(self) -> bool:
        logger.info("Copying configuration folders...")
        source_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        dest_dir = os.path.join(USER_HOME, ".config")
        Utils.ensure_directory(dest_dir, owner=f"{USERNAME}:{USERNAME}")
        success = True
        try:
            for item in os.listdir(source_dir):
                src_path = os.path.join(source_dir, item)
                if os.path.isdir(src_path):
                    dest_path = os.path.join(dest_dir, item)
                    os.makedirs(dest_path, exist_ok=True)
                    Utils.run_command(
                        ["rsync", "-a", "--update", src_path + "/", dest_path + "/"]
                    )
                    Utils.run_command(
                        ["chown", "-R", f"{USERNAME}:{USERNAME}", dest_path]
                    )
                    logger.info(f"Copied '{item}' configuration to '{dest_path}'.")
            return success
        except Exception as e:
            logger.error(f"Error scanning source directory '{source_dir}': {e}")
            return False

    def set_bash_shell(self) -> bool:
        logger.info("Ensuring /bin/bash is the default shell...")
        if not Utils.command_exists("bash"):
            logger.info("Bash not found; installing...")
            if not SystemUpdater().install_packages(["bash"]):
                logger.warning("Bash installation failed.")
                return False
        try:
            with open("/etc/shells", "r") as f:
                shells = f.read()
            if "/bin/bash" not in shells:
                with open("/etc/shells", "a") as f:
                    f.write("/bin/bash\n")
                logger.info("Added /bin/bash to /etc/shells.")
            else:
                logger.info("/bin/bash is already present in /etc/shells.")
        except Exception as e:
            logger.warning(f"Failed to update /etc/shells: {e}")
        try:
            current_shell = (
                subprocess.check_output(["getent", "passwd", USERNAME], text=True)
                .strip()
                .split(":")[-1]
            )
            if current_shell == "/bin/bash":
                logger.info(f"Default shell for {USERNAME} is already /bin/bash.")
                return True
            Utils.run_command(["chsh", "-s", "/bin/bash", USERNAME])
            logger.info(f"Default shell for {USERNAME} set to /bin/bash.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set default shell for {USERNAME}: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 4: Security & Access Hardening
# ------------------------------------------------------------------------------
class SecurityHardener:
    """Implement security hardening measures for the system."""

    def configure_ssh(self, port: int = 22) -> bool:
        logger.info("Configuring OpenSSH Server...")
        try:
            Utils.run_command(["systemctl", "enable", "--now", "ssh"])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to enable/start SSH: {e}")
            return False
        sshd_config = "/etc/ssh/sshd_config"
        if not os.path.isfile(sshd_config):
            logger.error(f"SSHD configuration file not found: {sshd_config}")
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
            with open(sshd_config, "r") as f:
                lines = f.readlines()
            for key, value in ssh_settings.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("#"):
                        continue
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {value}\n"
                        found = True
                        break
                if not found:
                    lines.append(f"{key} {value}\n")
            with open(sshd_config, "w") as f:
                f.writelines(lines)
        except Exception as e:
            logger.error(f"Failed to update SSH configuration: {e}")
            return False
        try:
            Utils.run_command(["systemctl", "restart", "ssh"])
            logger.info("SSH configuration updated successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart SSH service: {e}")
            return False

    def setup_sudoers(self) -> bool:
        logger.info(f"Configuring sudo privileges for {USERNAME}...")
        try:
            Utils.run_command(["id", USERNAME], capture_output=True)
        except subprocess.CalledProcessError:
            logger.error(f"User {USERNAME} does not exist.")
            return False
        try:
            result = subprocess.run(
                ["id", "-nG", USERNAME], capture_output=True, text=True, check=True
            )
            if "sudo" not in result.stdout.split():
                Utils.run_command(["usermod", "-aG", "sudo", USERNAME])
                logger.info(f"Added {USERNAME} to sudo group.")
            else:
                logger.info(f"{USERNAME} is already in sudo group.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add {USERNAME} to sudo group: {e}")
            return False
        sudoers_file = f"/etc/sudoers.d/99-{USERNAME}"
        try:
            with open(sudoers_file, "w") as f:
                f.write(f"{USERNAME} ALL=(ALL:ALL) ALL\n")
                f.write("Defaults timestamp_timeout=15\n")
                f.write("Defaults requiretty\n")
            os.chmod(sudoers_file, 0o440)
            logger.info(f"Secure sudoers configuration created for {USERNAME}.")
            Utils.run_command(["visudo", "-c"], check=True)
            logger.info("Sudoers syntax verified.")
            return True
        except Exception as e:
            logger.error(f"Failed to configure sudoers: {e}")
            return False

    def configure_firewall(self) -> bool:
        logger.info("Configuring UFW firewall...")
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            logger.info("UFW not found; installing...")
            if not SystemUpdater().install_packages(["ufw"]):
                logger.error("Failed to install UFW.")
                return False
        try:
            Utils.run_command([ufw_cmd, "reset", "--force"], check=False)
            logger.info("UFW reset to defaults.")
        except subprocess.CalledProcessError:
            logger.warning("Failed to reset UFW configuration.")
        for cmd, desc in [
            (
                [ufw_cmd, "default", "deny", "incoming"],
                "set default deny for incoming traffic",
            ),
            (
                [ufw_cmd, "default", "allow", "outgoing"],
                "set default allow for outgoing traffic",
            ),
        ]:
            try:
                Utils.run_command(cmd)
                logger.info(f"Successfully {desc}.")
            except subprocess.CalledProcessError:
                logger.warning(f"Failed to {desc}.")
        for port in ALLOWED_PORTS:
            try:
                Utils.run_command([ufw_cmd, "allow", f"{port}/tcp"])
                logger.info(f"Allowed TCP port {port}.")
            except subprocess.CalledProcessError:
                logger.warning(f"Failed to allow TCP port {port}.")
        try:
            result = Utils.run_command(
                [ufw_cmd, "status"], capture_output=True, text=True
            )
            if "inactive" in result.stdout.lower():
                try:
                    Utils.run_command([ufw_cmd, "--force", "enable"])
                    logger.info("UFW firewall enabled.")
                except subprocess.CalledProcessError:
                    logger.error("Failed to enable UFW.")
                    return False
            else:
                logger.info("UFW firewall is active.")
        except subprocess.CalledProcessError:
            logger.error("Failed to retrieve UFW status.")
            return False
        try:
            Utils.run_command([ufw_cmd, "logging", "on"])
            logger.info("UFW logging enabled.")
        except subprocess.CalledProcessError:
            logger.warning("Failed to enable UFW logging.")
        try:
            Utils.run_command(["systemctl", "enable", "ufw"])
            Utils.run_command(["systemctl", "restart", "ufw"])
            logger.info("UFW service enabled and restarted.")
            return True
        except subprocess.CalledProcessError:
            logger.error("Failed to manage UFW service.")
            return False

    def configure_fail2ban(self) -> bool:
        logger.info("Configuring Fail2ban...")
        if not Utils.command_exists("fail2ban-server"):
            logger.info("fail2ban not installed; installing...")
            if not SystemUpdater().install_packages(["fail2ban"]):
                logger.error("Failed to install fail2ban.")
                return False
        jail_local = "/etc/fail2ban/jail.local"
        config_content = """[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
backend  = systemd
usedns   = warn

[sshd]
enabled  = true
port     = ssh
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3

[sshd-ddos]
enabled  = true
port     = ssh
filter   = sshd-ddos
logpath  = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[pam-generic]
enabled = true
banaction = %(banaction_allports)s
logpath = /var/log/auth.log
"""
        if os.path.isfile(jail_local):
            Utils.backup_file(jail_local)
        try:
            with open(jail_local, "w") as f:
                f.write(config_content)
            logger.info("Fail2ban configuration written to /etc/fail2ban/jail.local.")
            Utils.run_command(["systemctl", "enable", "fail2ban"])
            Utils.run_command(["systemctl", "restart", "fail2ban"])
            status = Utils.run_command(
                ["systemctl", "is-active", "fail2ban"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Fail2ban is active.")
                return True
            else:
                logger.warning("Fail2ban may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"Failed to configure Fail2ban: {e}")
            return False

    def configure_apparmor(self) -> bool:
        logger.info("Configuring AppArmor...")
        try:
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
                logger.error("Failed to install AppArmor packages.")
                return False
            Utils.run_command(["systemctl", "enable", "apparmor"])
            Utils.run_command(["systemctl", "start", "apparmor"])
            status = Utils.run_command(
                ["systemctl", "is-active", "apparmor"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("AppArmor is active.")
                if Utils.command_exists("aa-update-profiles"):
                    try:
                        Utils.run_command(["aa-update-profiles"], check=False)
                        logger.info("AppArmor profiles updated.")
                    except Exception as e:
                        logger.warning(f"Failed to update AppArmor profiles: {e}")
                else:
                    logger.warning(
                        "aa-update-profiles command not found; skipping profile update."
                    )
                return True
            else:
                logger.warning("AppArmor may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"Failed to configure AppArmor: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 5: Service Installations
# ------------------------------------------------------------------------------
class ServiceInstaller:
    """Install and configure various services and applications."""

    def install_fastfetch(self) -> bool:
        logger.info("Installing Fastfetch...")
        if Utils.command_exists("fastfetch"):
            logger.info("Fastfetch is already installed; skipping.")
            return True
        temp_deb = os.path.join(TEMP_DIR, "fastfetch-linux-amd64.deb")
        try:
            logger.debug(f"Downloading Fastfetch from {FASTFETCH_URL}...")
            Utils.run_command(["curl", "-L", "-o", temp_deb, FASTFETCH_URL])
            Utils.run_command(["dpkg", "-i", temp_deb])
            Utils.run_command(["apt", "install", "-f", "-y"])
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            if Utils.command_exists("fastfetch"):
                logger.info("Fastfetch installed successfully.")
                return True
            else:
                logger.error("Fastfetch installation failed verification.")
                return False
        except Exception as e:
            logger.error(f"Failed to install Fastfetch: {e}")
            return False

    def docker_config(self) -> bool:
        logger.info("Configuring Docker and Docker Compose...")
        if Utils.command_exists("docker"):
            logger.info("Docker is already installed.")
        else:
            try:
                logger.info("Installing Docker using official script...")
                script_path = os.path.join(TEMP_DIR, "get-docker.sh")
                Utils.run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script_path]
                )
                os.chmod(script_path, 0o755)
                Utils.run_command([script_path], check=True)
                os.remove(script_path)
                logger.info("Docker installed successfully.")
            except Exception as e:
                logger.error(f"Failed to install Docker: {e}")
                logger.warning("Trying alternative Docker installation method...")
                if not SystemUpdater().install_packages(["docker.io"]):
                    logger.error("Alternative Docker installation failed.")
                    return False
        try:
            result = subprocess.run(
                ["id", "-nG", USERNAME], capture_output=True, text=True, check=True
            )
            if "docker" not in result.stdout.split():
                Utils.run_command(["usermod", "-aG", "docker", USERNAME])
                logger.info(f"Added {USERNAME} to docker group.")
            else:
                logger.info(f"{USERNAME} is already in docker group.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to add {USERNAME} to docker group: {e}")
        daemon_json_path = "/etc/docker/daemon.json"
        os.makedirs("/etc/docker", exist_ok=True)
        desired_daemon_json = """{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "exec-opts": ["native.cgroupdriver=systemd"],
    "storage-driver": "overlay2",
    "features": {
        "buildkit": true
    },
    "default-address-pools": [
        {
        "base": "172.17.0.0/16",
        "size": 24
        }
    ]
    }
    """
        update_needed = True
        if os.path.isfile(daemon_json_path):
            try:
                with open(daemon_json_path, "r") as f:
                    existing = f.read()
                existing_config = json.loads(existing)
                desired_config = json.loads(desired_daemon_json)
                if existing_config == desired_config:
                    logger.info("Docker daemon configuration is already up-to-date.")
                    update_needed = False
                else:
                    Utils.backup_file(daemon_json_path)
            except Exception as e:
                logger.warning(f"Failed to read {daemon_json_path}: {e}")
        if update_needed:
            try:
                with open(daemon_json_path, "w") as f:
                    f.write(desired_daemon_json)
                logger.info("Docker daemon configuration updated.")
            except Exception as e:
                logger.warning(f"Failed to write {daemon_json_path}: {e}")
        try:
            Utils.run_command(["systemctl", "enable", "docker"])
            Utils.run_command(["systemctl", "restart", "docker"])
            logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to manage Docker service: {e}")
            return False
        if not Utils.command_exists("docker-compose"):
            try:
                Utils.run_command(["nala", "install", "docker-compose-plugin"])
                logger.info("Docker Compose plugin installed successfully.")
            except Exception as e:
                logger.error(f"Failed to install Docker Compose plugin: {e}")
                return False
        else:
            logger.info("Docker Compose is already installed.")
        try:
            Utils.run_command(["docker", "info"], capture_output=True)
            logger.info("Docker is running and accessible.")
            return True
        except subprocess.CalledProcessError:
            logger.error("Docker is not running or is inaccessible.")
            return False

    def install_configure_caddy(self) -> bool:
        logger.info("Installing Caddy web server...")
        if Utils.command_exists("caddy"):
            logger.info("Caddy is already installed.")
            caddy_installed = True
        else:
            try:
                Utils.run_command(
                    [
                        "nala",
                        "install",
                        "-y",
                        "debian-keyring",
                        "debian-archive-keyring",
                        "apt-transport-https",
                        "curl",
                    ]
                )
                Utils.run_command(
                    "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg",
                    shell=True,
                )
                Utils.run_command(
                    "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list",
                    shell=True,
                )
                Utils.run_command(["nala", "update"])
                Utils.run_command(["nala", "install", "caddy"])
                logger.info("Caddy installed successfully via repository method.")
                caddy_installed = True
            except Exception as e:
                logger.error(f"Failed to install Caddy: {e}")
                return False
        try:
            Utils.ensure_directory("/etc/caddy", "root:root", 0o755)
            Utils.ensure_directory("/var/log/caddy", "caddy:caddy", 0o755)
            caddyfile_source = os.path.join(
                USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles", "Caddyfile"
            )
            caddyfile_dest = "/etc/caddy/Caddyfile"
            if os.path.isfile(caddyfile_source):
                if os.path.isfile(caddyfile_dest):
                    Utils.backup_file(caddyfile_dest)
                shutil.copy2(caddyfile_source, caddyfile_dest)
                logger.info(f"Copied Caddyfile from {caddyfile_source}")
            else:
                if not os.path.isfile(caddyfile_dest):
                    with open(caddyfile_dest, "w") as f:
                        f.write(f"""# Caddy default configuration
# Created by ubuntu_server_setup.py on {datetime.datetime.now().strftime("%Y-%m-%d")}

:80 {{
    root * /var/www/html
    file_server
    log {{
        output file /var/log/caddy/access.log
        format console
    }}
}}
""")
                    logger.info("Created default Caddyfile.")
            Utils.run_command(["chown", "root:caddy", caddyfile_dest])
            Utils.run_command(["chmod", "644", caddyfile_dest])
            Utils.ensure_directory("/var/www/html", "caddy:caddy", 0o755)
            index_file = "/var/www/html/index.html"
            if not os.path.isfile(index_file):
                with open(index_file, "w") as f:
                    server_name = socket.gethostname()
                    f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Server: {server_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; }}
        h1 {{ color: #2c3e50; }}
    </style>
</head>
<body>
    <h1>Welcome to {server_name}</h1>
    <p>Configured by ubuntu_server_setup.py on {datetime.datetime.now().strftime("%Y-%m-%d")}.</p>
</body>
</html>""")
                logger.info("Created default index.html file.")
            Utils.run_command(["chown", "caddy:caddy", index_file])
            Utils.run_command(["chmod", "644", index_file])
            Utils.run_command(["systemctl", "enable", "caddy"])
            Utils.run_command(["systemctl", "restart", "caddy"])
            status = Utils.run_command(
                ["systemctl", "is-active", "caddy"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Caddy web server is active and running.")
                return True
            else:
                logger.warning("Caddy service may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"Failed to configure Caddy: {e}")
            return caddy_installed

    def install_nala(self) -> bool:
        logger.info("Installing Nala (apt frontend)...")
        if Utils.command_exists("nala"):
            logger.info("Nala is already installed.")
            return True
        try:
            logger.info("Updating apt repositories...")
            Utils.run_command(["apt", "update"])
            logger.info("Upgrading existing packages...")
            Utils.run_command(["apt", "upgrade", "-y"])
            logger.info("Fixing any broken package installations...")
            Utils.run_command(["apt", "--fix-broken", "install", "-y"])
            logger.info("Installing nala package...")
            Utils.run_command(["apt", "install", "nala", "-y"])
            if Utils.command_exists("nala"):
                logger.info("Nala installed successfully.")
                try:
                    Utils.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    logger.info("Configured faster mirrors with Nala.")
                except subprocess.CalledProcessError:
                    logger.warning("Failed to configure mirrors with Nala.")
                return True
            else:
                logger.error("Nala installation verification failed.")
                return False
        except Exception as e:
            logger.error(f"Failed to install Nala: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        logger.info("Installing and configuring Tailscale...")
        if Utils.command_exists("tailscale"):
            logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                logger.info("Installing Tailscale using the official script...")
                Utils.run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )
                tailscale_installed = Utils.command_exists("tailscale")
                if tailscale_installed:
                    logger.info("Tailscale installed successfully.")
                else:
                    logger.error("Tailscale installation failed.")
                    return False
            except Exception as e:
                logger.error(f"Failed to install Tailscale: {e}")
                return False
        try:
            Utils.run_command(["systemctl", "enable", "tailscaled"])
            Utils.run_command(["systemctl", "start", "tailscaled"])
            status = Utils.run_command(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Tailscale service is active and running.")
                logger.info("To authenticate, run: tailscale up")
                return True
            else:
                logger.warning("Tailscale service may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    def deploy_user_scripts(self) -> bool:
        logger.info("Deploying user scripts...")
        script_source = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts"
        )
        script_target = os.path.join(USER_HOME, "bin")
        if not os.path.isdir(script_source):
            logger.warning(f"Source directory '{script_source}' does not exist.")
            return False
        Utils.ensure_directory(script_target, owner=f"{USERNAME}:{USERNAME}")
        try:
            Utils.run_command(
                ["rsync", "-ah", "--delete", f"{script_source}/", f"{script_target}/"]
            )
            Utils.run_command(
                [
                    "find",
                    script_target,
                    "-type",
                    "f",
                    "-exec",
                    "chmod",
                    "755",
                    "{}",
                    ";",
                ]
            )
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", script_target])
            logger.info("User scripts deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Script deployment failed: {e}")
            return False

    def configure_unattended_upgrades(self) -> bool:
        logger.info("Configuring unattended upgrades...")
        try:
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                logger.error("Failed to install unattended-upgrades packages.")
                return False
            auto_upgrades_file = "/etc/apt/apt.conf.d/20auto-upgrades"
            auto_upgrades_content = (
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )
            try:
                with open(auto_upgrades_file, "w") as f:
                    f.write(auto_upgrades_content)
                logger.info(
                    f"Auto-upgrades configuration written to {auto_upgrades_file}"
                )
            except Exception as e:
                logger.error(f"Failed to write auto-upgrades configuration: {e}")
                return False
            unattended_file = "/etc/apt/apt.conf.d/50unattended-upgrades"
            if os.path.isfile(unattended_file):
                Utils.backup_file(unattended_file)
            unattended_content = (
                "Unattended-Upgrade::Allowed-Origins {\n"
                '    "${distro_id}:${distro_codename}";\n'
                '    "${distro_id}:${distro_codename}-security";\n'
                '    "${distro_id}ESMApps:${distro_codename}-apps-security";\n'
                '    "${distro_id}ESM:${distro_codename}-infra-security";\n'
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
            try:
                with open(unattended_file, "w") as f:
                    f.write(unattended_content)
                logger.info(
                    f"Unattended-upgrades configuration written to {unattended_file}"
                )
            except Exception as e:
                logger.error(f"Failed to write unattended-upgrades configuration: {e}")
                return False
            Utils.run_command(["systemctl", "enable", "unattended-upgrades"])
            Utils.run_command(["systemctl", "restart", "unattended-upgrades"])
            status = Utils.run_command(
                ["systemctl", "is-active", "unattended-upgrades"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Unattended upgrades service is active and running.")
                return True
            else:
                logger.warning(
                    "Unattended upgrades service may not be running correctly."
                )
                return False
        except Exception as e:
            logger.error(f"Failed to configure unattended upgrades: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 6: Maintenance Tasks
# ------------------------------------------------------------------------------
class MaintenanceManager:
    """Configure maintenance tasks and backups."""

    def configure_periodic(self) -> bool:
        logger.info("Setting up daily maintenance cron job...")
        cron_file = "/etc/cron.daily/ubuntu_maintenance"
        marker = "# Ubuntu maintenance script"
        if os.path.isfile(cron_file):
            with open(cron_file, "r") as f:
                if marker in f.read():
                    logger.info("Daily maintenance cron job already configured.")
                    return True
            Utils.backup_file(cron_file)
        content = f"""#!/bin/sh
# Ubuntu maintenance script
# Created by ubuntu_server_setup.py on $(date)

LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG
echo "Updating package lists..." >> $LOG
nala update -qq >> $LOG 2>&1
echo "Checking for security updates..." >> $LOG
nala list --upgradable | grep -i security >> $LOG 2>&1
echo "Upgrading packages..." >> $LOG
nala upgrade -y >> $LOG 2>&1
echo "Removing unnecessary packages..." >> $LOG
nala autoremove -y >> $LOG 2>&1
echo "Cleaning package cache..." >> $LOG
nala clean >> $LOG 2>&1
echo "Disk space usage:" >> $LOG
df -h / >> $LOG 2>&1
echo "Largest files in /var/log:" >> $LOG
find /var/log -type f -size +10M -exec ls -lh {{}} \\; | sort -k5,5hr | head -5 >> $LOG 2>&1
find /var/log -name "*.log" -size +100M -exec bash -c 'gzip -c {{}} > {{}}.$(date +%Y%m%d).gz && cat /dev/null > {{}}' \\; >> $LOG 2>&1
echo "Daily maintenance completed at $(date)" >> $LOG
"""
        try:
            with open(cron_file, "w") as f:
                f.write(content)
            os.chmod(cron_file, 0o755)
            logger.info(f"Daily maintenance script created at {cron_file}.")
            return True
        except Exception as e:
            logger.error(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> bool:
        logger.info("Backing up critical configuration files...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(BACKUP_DIR, f"ubuntu_config_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)
        success = True
        for file in CONFIG_FILES:
            if os.path.isfile(file):
                try:
                    shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
                    logger.info(f"Backed up {file}")
                except Exception as e:
                    logger.warning(f"Failed to backup {file}: {e}")
                    if file in ["/etc/ssh/sshd_config", "/etc/ufw/user.rules"]:
                        success = False
            else:
                logger.debug(f"File {file} not found; skipping.")
        try:
            with open(os.path.join(backup_dir, "MANIFEST.txt"), "w") as f:
                f.write("Ubuntu Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {socket.gethostname()}\n\n")
                f.write("Files included:\n")
                for file in CONFIG_FILES:
                    if os.path.isfile(os.path.join(backup_dir, os.path.basename(file))):
                        f.write(f"- {file}\n")
            logger.info(f"Configuration backups saved to {backup_dir}")
        except Exception as e:
            logger.warning(f"Failed to create backup manifest: {e}")
        return success

    def update_ssl_certificates(self) -> bool:
        logger.info("Updating SSL certificates via certbot...")
        if not Utils.command_exists("certbot"):
            logger.info("certbot not installed; installing...")
            if not SystemUpdater().install_packages(["certbot"]):
                logger.warning("Failed to install certbot.")
                return False
        try:
            output = Utils.run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True, text=True
            ).stdout
            logger.info("SSL certificate dry-run completed.")
            if "No renewals were attempted" in output:
                logger.info("No certificates need renewal at this time.")
            else:
                Utils.run_command(["certbot", "renew"])
                logger.info("SSL certificates updated successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to update SSL certificates: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 7: System Tuning & Permissions
# ------------------------------------------------------------------------------
class SystemTuner:
    """Apply system optimizations and secure permissions."""

    def tune_system(self) -> bool:
        logger.info("Applying system performance tuning...")
        sysctl_conf = "/etc/sysctl.conf"
        if os.path.isfile(sysctl_conf):
            Utils.backup_file(sysctl_conf)
        tuning_settings = {
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
            with open(sysctl_conf, "r") as f:
                content = f.read()
            marker = "# Performance tuning settings for Ubuntu"
            if marker in content:
                logger.info(
                    "Performance tuning settings already exist. Updating settings..."
                )
                content = re.split(marker, content)[0]
            content += f"\n{marker}\n"
            for key, value in tuning_settings.items():
                content += f"{key} = {value}\n"
            with open(sysctl_conf, "w") as f:
                f.write(content)
            Utils.run_command(["sysctl", "-p"])
            logger.info("Performance tuning applied successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to apply performance tuning: {e}")
            return False

    def home_permissions(self) -> bool:
        logger.info("Configuring home directory permissions...")
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", USER_HOME])
            Utils.run_command(["chmod", "750", USER_HOME])
            sensitive_dirs = [
                os.path.join(USER_HOME, ".ssh"),
                os.path.join(USER_HOME, ".gnupg"),
                os.path.join(USER_HOME, ".config"),
            ]
            for directory in sensitive_dirs:
                if os.path.isdir(directory):
                    Utils.run_command(["chmod", "700", directory])
                    logger.info(f"Set secure permissions on {directory}")
            Utils.run_command(
                ["find", USER_HOME, "-type", "d", "-exec", "chmod", "g+s", "{}", ";"]
            )
            if Utils.command_exists("setfacl"):
                Utils.run_command(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{USERNAME}:rwX,g:{USERNAME}:r-X,o::---",
                        USER_HOME,
                    ]
                )
                logger.info(f"Default ACLs applied on {USER_HOME}.")
            else:
                logger.warning("setfacl not found; skipping default ACL configuration.")
            logger.info(f"Home directory permissions for {USERNAME} set correctly.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set home directory permissions: {e}")
            return False


# ------------------------------------------------------------------------------
# Phase 8: Final Checks & Cleanup
# ------------------------------------------------------------------------------
class FinalChecker:
    """Perform final system checks and cleanup tasks."""

    def system_health_check(self) -> Dict[str, Any]:
        logger.info("Performing system health check...")
        health_data = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            logger.info(f"Uptime: {uptime}")
            health_data["uptime"] = uptime
        except Exception as e:
            logger.warning(f"Failed to get uptime: {e}")
        try:
            df_output = (
                subprocess.check_output(["df", "-h", "/"], text=True)
                .strip()
                .splitlines()
            )
            if len(df_output) >= 2:
                data = df_output[1].split()
                logger.info(f"Disk usage: {data[4]} used ({data[2]} of {data[1]})")
                health_data["disk"] = {
                    "total": data[1],
                    "used": data[2],
                    "available": data[3],
                    "percent_used": data[4],
                }
                percent = int(data[4].strip("%"))
                if percent > 90:
                    logger.warning(f"Critical disk usage: {percent}% used!")
                elif percent > 75:
                    logger.warning(f"Warning: Disk usage at {percent}%.")
        except Exception as e:
            logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_output = (
                subprocess.check_output(["free", "-h"], text=True).strip().splitlines()
            )
            for line in free_output:
                logger.info(line)
                if line.startswith("Mem:"):
                    parts = line.split()
                    health_data["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                        "shared": parts[4],
                        "buffers": parts[5],
                        "cache": parts[6],
                    }
        except Exception as e:
            logger.warning(f"Failed to get memory usage: {e}")
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()[:3]
            logger.info(f"Load averages: {', '.join(load)}")
            health_data["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
            cpu_count = os.cpu_count() or 1
            if float(load[1]) > cpu_count:
                logger.warning(
                    f"High 5min load ({load[1]}) exceeds CPU count ({cpu_count})"
                )
        except Exception as e:
            logger.warning(f"Failed to get load averages: {e}")
        try:
            dmesg = subprocess.check_output(
                ["dmesg", "--level=err,crit,alert,emerg"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if dmesg:
                logger.warning("Recent kernel errors detected:")
                for line in dmesg.splitlines()[-5:]:
                    logger.warning(line)
                health_data["kernel_errors"] = True
            else:
                logger.info("No recent kernel errors detected.")
                health_data["kernel_errors"] = False
        except Exception as e:
            logger.warning(f"Failed to check kernel errors: {e}")
        try:
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
            if total_updates > 0:
                logger.info(
                    f"Available updates: {total_updates} total, {security_updates} security"
                )
                if security_updates > 0:
                    logger.warning(f"Security updates available: {security_updates}")
                health_data["updates"] = {
                    "total": total_updates,
                    "security": security_updates,
                }
            else:
                logger.info("System is up to date.")
                health_data["updates"] = {"total": 0, "security": 0}
        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")
        return health_data

    def verify_firewall_rules(self) -> bool:
        logger.info("Verifying firewall rules...")
        all_correct = True
        try:
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            logger.info("Current UFW status:")
            for line in ufw_status.splitlines()[:10]:
                logger.info(line)
            if "inactive" in ufw_status.lower():
                logger.warning("UFW is inactive!")
                return False
        except Exception as e:
            logger.warning(f"Failed to get UFW status: {e}")
        for port in ALLOWED_PORTS:
            try:
                result = subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if result.returncode == 0:
                    logger.info(f"Port {port} is accessible on localhost.")
                else:
                    if Utils.is_port_open(int(port)):
                        logger.info(
                            f"Port {port} is listening but may be blocked by firewall."
                        )
                    else:
                        logger.warning(f"Port {port} is closed.")
                        all_correct = False
            except Exception as e:
                logger.warning(f"Failed to check port {port}: {e}")
                all_correct = False
        try:
            route = subprocess.check_output(
                ["ip", "-o", "-4", "route", "show", "default"], text=True
            ).strip()
            interface = route.split()[4]
            interface_ip = (
                subprocess.check_output(
                    ["ip", "-o", "-4", "addr", "show", "dev", interface], text=True
                )
                .strip()
                .split()[3]
                .split("/")[0]
            )
            logger.info(f"Default interface: {interface} ({interface_ip})")
            for port in ALLOWED_PORTS:
                try:
                    result = subprocess.run(
                        ["nc", "-z", "-w3", interface_ip, port],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if result.returncode == 0:
                        logger.info(f"Port {port} accessible on external interface.")
                    else:
                        logger.warning(
                            f"Port {port} not accessible on external interface."
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Could not check external interface: {e}")
        return all_correct

    def final_checks(self) -> bool:
        logger.info("Performing final system checks...")
        all_passed = True
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            logger.info(f"Kernel version: {kernel}")
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            logger.info(f"System uptime: {uptime}")
            disk_usage = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            logger.info(f"Disk usage (root): {disk_usage}")
            disk_percent = int(disk_usage.split()[4].strip("%"))
            if disk_percent > 90:
                logger.warning("Critical: Disk usage over 90%!")
                all_passed = False
            elif disk_percent > 80:
                logger.warning("Warning: Disk usage over 80%.")
            free_output = subprocess.check_output(
                ["free", "-h"], text=True
            ).splitlines()
            mem_line = next(
                (line for line in free_output if line.startswith("Mem:")), ""
            )
            logger.info(f"Memory usage: {mem_line}")
            cpu_model = ""
            cpu_output = subprocess.check_output(["lscpu"], text=True)
            for line in cpu_output.splitlines():
                if "Model name" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    logger.info(f"CPU: {cpu_model}")
                    break
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            logger.info("Active network interfaces:")
            for line in interfaces.splitlines():
                logger.info(line)
            netstat = subprocess.check_output(["ss", "-tuln"], text=True).splitlines()[
                :10
            ]
            logger.info("Active network connections:")
            for line in netstat:
                logger.info(line)
            with open("/proc/loadavg", "r") as f:
                load_avg = f.read().split()[:3]
            if load_avg:
                logger.info(f"Load averages (1, 5, 15 min): {', '.join(load_avg)}")
                cpu_count = os.cpu_count() or 1
                if float(load_avg[1]) > cpu_count:
                    logger.warning(
                        f"Warning: 5min load average ({load_avg[1]}) exceeds CPU count ({cpu_count})."
                    )
            services_to_check = [
                "ssh",
                "ufw",
                "fail2ban",
                "caddy",
                "docker",
                "tailscaled",
                "unattended-upgrades",
            ]
            for service in services_to_check:
                status = subprocess.run(
                    ["systemctl", "is-active", service],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                status_str = status.stdout.strip()
                if status_str == "active":
                    logger.info(f"{service}: active")
                else:
                    logger.warning(f"{service}: {status_str}")
                    if service in ["ssh", "ufw"]:
                        all_passed = False
            try:
                unattended_output = subprocess.check_output(
                    ["unattended-upgrade", "--dry-run", "--debug"],
                    text=True,
                    stderr=subprocess.STDOUT,
                )
                for line in unattended_output.splitlines():
                    if ("Packages that will be upgraded:" in line) and (
                        "0 upgrades" not in line
                    ):
                        logger.warning("Pending security updates detected!")
                        all_passed = False
            except Exception:
                logger.debug("Unable to check for security updates.")
            return all_passed
        except Exception as e:
            logger.error(f"Error during final checks: {e}")
            return False

    def cleanup_system(self) -> bool:
        logger.info("Performing system cleanup...")
        success = True
        try:
            if Utils.command_exists("nala"):
                Utils.run_command(["nala", "autoremove", "-y"])
            else:
                Utils.run_command(["apt", "autoremove", "-y"])
            if Utils.command_exists("nala"):
                Utils.run_command(["nala", "clean"])
            else:
                Utils.run_command(["apt", "clean"])
            try:
                current = subprocess.check_output(["uname", "-r"], text=True).strip()
                running_image = f"linux-image-{current}"
                running_headers = f"linux-headers-{current}"
                installed = (
                    subprocess.check_output(
                        ["dpkg", "--list", "linux-image-*", "linux-headers-*"],
                        text=True,
                    )
                    .strip()
                    .splitlines()
                )
                old_kernel_packages = []
                for line in installed:
                    if line.startswith("ii"):
                        parts = line.split()
                        package = parts[1]
                        if package == running_image or package == running_headers:
                            continue
                        if "generic" not in package:
                            continue
                        old_kernel_packages.append(package)
                if len(old_kernel_packages) > 1:
                    old_kernel_packages.sort()
                    to_remove = old_kernel_packages[:-1]
                    if to_remove:
                        logger.info(f"Removing {len(to_remove)} old kernel packages...")
                        Utils.run_command(["apt", "purge", "-y"] + to_remove)
                else:
                    logger.info("No old kernels to remove.")
            except Exception as e:
                logger.warning(f"Failed to remove old kernels: {e}")
            if Utils.command_exists("journalctl"):
                logger.info("Clearing systemd journal logs older than 7 days...")
                Utils.run_command(["journalctl", "--vacuum-time=7d"])
            for tmp_dir in ["/tmp", "/var/tmp"]:
                logger.info(f"Cleaning {tmp_dir} directory...")
                try:
                    Utils.run_command(
                        [
                            "find",
                            tmp_dir,
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
                except Exception as e:
                    logger.warning(f"Failed to clean {tmp_dir}: {e}")
            try:
                log_files = (
                    subprocess.check_output(
                        ["find", "/var/log", "-type", "f", "-size", "+50M"], text=True
                    )
                    .strip()
                    .splitlines()
                )
                for log_file in log_files:
                    logger.debug(f"Compressing large log file: {log_file}")
                    with open(log_file, "rb") as f_in:
                        with gzip.open(f"{log_file}.gz", "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    open(log_file, "w").close()
            except Exception as e:
                logger.warning(f"Failed to rotate logs: {e}")
            logger.info("System cleanup completed successfully.")
            return success
        except Exception as e:
            logger.error(f"System cleanup failed: {e}")
            return False

    def prompt_reboot(self) -> None:
        """Prompt the user to reboot the system."""
        logger.info("Prompting for system reboot...")
        print(
            f"{NORD14}Setup completed! A reboot is recommended to apply all changes.{NC}"
        )
        answer = input("Would you like to reboot now? [y/N]: ").strip().lower()
        if answer == "y":
            logger.info("Rebooting system now...")
            try:
                Utils.run_command(["shutdown", "-r", "now"])
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to reboot system: {e}")
        else:
            logger.info(
                "Reboot canceled. Please reboot later (e.g. with: sudo reboot)."
            )


# ------------------------------------------------------------------------------
# Main Orchestration
# ------------------------------------------------------------------------------
class UbuntuServerSetup:
    """Main class to orchestrate the entire setup process."""

    def __init__(self):
        self.logger = logger
        self.success = True
        self.start_time = time.time()
        self.preflight = PreflightChecker()
        self.updater = SystemUpdater()
        self.user_env = UserEnvironment()
        self.security = SecurityHardener()
        self.services = ServiceInstaller()
        self.maintenance = MaintenanceManager()
        self.tuner = SystemTuner()
        self.final_checker = FinalChecker()

    def run(self) -> int:
        try:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{NORD8}----------------------------------------{NC}")
            print(f"{NORD8}  Starting Ubuntu Server Setup v6.0.0{NC}")
            print(f"{NORD8}  {now}{NC}")
            print(f"{NORD8}----------------------------------------{NC}")
            logger.info(
                f"Starting Ubuntu Server Setup v6.0.0 on {datetime.datetime.now()}"
            )
            print_section("Phase 1: Pre-flight Checks")
            try:
                run_with_progress(
                    "Running Pre-flight Checks...",
                    self.preflight.check_root,
                    task_name="preflight",
                )
                if not self.preflight.check_network():
                    self.logger.error("Network connectivity check failed. Aborting.")
                    SETUP_STATUS["preflight"] = {
                        "status": "failed",
                        "message": "Network connectivity check failed",
                    }
                    sys.exit(1)
                if not self.preflight.check_os_version():
                    self.logger.warning(
                        "OS version check failed; proceeding with caution."
                    )
                self.preflight.save_config_snapshot()
            except Exception as e:
                self.logger.error(f"Error in preflight phase: {e}")
                self.success = False
            print_section("Phase 2: Installing Nala Package Manager")
            try:
                if not run_with_progress(
                    "Installing Nala...",
                    self.services.install_nala,
                    task_name="nala_install",
                ):
                    self.logger.error(
                        "Nala installation failed. Proceeding with caution."
                    )
                    self.success = False
            except Exception as e:
                self.logger.error(f"Error in Nala installation phase: {e}")
                self.success = False
            print_section("Phase 3: System Update & Basic Configuration")
            try:
                if not run_with_progress(
                    "Updating system...",
                    self.updater.update_system,
                    task_name="system_update",
                ):
                    self.logger.warning("System update failed; continuing.")
                    self.success = False
            except Exception as e:
                self.logger.error(f"Error in system update: {e}")
                self.success = False
            try:
                if not run_with_progress(
                    "Installing packages...",
                    self.updater.install_packages,
                    task_name="packages_install",
                ):
                    self.logger.warning("Package installation encountered issues.")
                    self.success = False
            except Exception as e:
                self.logger.error(f"Error in package installation: {e}")
                self.success = False
            try:
                if not run_with_progress(
                    "Configuring timezone...", self.updater.configure_timezone
                ):
                    self.logger.warning("Timezone configuration failed.")
                    self.success = False
            except Exception as e:
                self.logger.error(f"Error in timezone configuration: {e}")
                self.success = False
            try:
                if hasattr(self.updater, "configure_locale"):
                    if not run_with_progress(
                        "Configuring locale...", self.updater.configure_locale
                    ):
                        self.logger.warning("Locale configuration failed.")
                        self.success = False
                else:
                    self.logger.warning("configure_locale method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in locale configuration: {e}")
                self.success = False
            print_section("Phase 4: User Environment Setup")
            try:
                if hasattr(self.user_env, "setup_repos"):
                    if not run_with_progress(
                        "Setting up user repositories...",
                        self.user_env.setup_repos,
                        task_name="user_env",
                    ):
                        self.logger.warning("Repository setup failed.")
                        self.success = False
                else:
                    self.logger.warning("setup_repos method not found, skipping.")
                    SETUP_STATUS["user_env"] = {
                        "status": "skipped",
                        "message": "setup_repos method not found",
                    }
            except Exception as e:
                self.logger.error(f"Error in repository setup: {e}")
                self.success = False
            try:
                if hasattr(self.user_env, "copy_shell_configs"):
                    if not run_with_progress(
                        "Copying shell configs...", self.user_env.copy_shell_configs
                    ):
                        self.logger.warning("Shell configuration update failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "copy_shell_configs method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in shell configuration: {e}")
                self.success = False
            try:
                if hasattr(self.user_env, "copy_config_folders"):
                    if not run_with_progress(
                        "Copying config folders...", self.user_env.copy_config_folders
                    ):
                        self.logger.warning("Copying configuration folders failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "copy_config_folders method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in copying config folders: {e}")
                self.success = False
            try:
                if hasattr(self.user_env, "set_bash_shell"):
                    if not run_with_progress(
                        "Setting default shell...", self.user_env.set_bash_shell
                    ):
                        self.logger.warning("Default shell update failed.")
                        self.success = False
                else:
                    self.logger.warning("set_bash_shell method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in setting bash shell: {e}")
                self.success = False
            print_section("Phase 5: Security & Access Hardening")
            try:
                if hasattr(self.security, "configure_ssh"):
                    if not run_with_progress(
                        "Configuring SSH...",
                        self.security.configure_ssh,
                        task_name="security",
                    ):
                        self.logger.warning("SSH configuration failed.")
                        self.success = False
                else:
                    self.logger.warning("configure_ssh method not found, skipping.")
                    SETUP_STATUS["security"] = {
                        "status": "skipped",
                        "message": "configure_ssh method not found",
                    }
            except Exception as e:
                self.logger.error(f"Error in SSH configuration: {e}")
                self.success = False
            try:
                if hasattr(self.security, "setup_sudoers"):
                    if not run_with_progress(
                        "Configuring sudoers...", self.security.setup_sudoers
                    ):
                        self.logger.warning("Sudoers configuration failed.")
                        self.success = False
                else:
                    self.logger.warning("setup_sudoers method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in sudoers configuration: {e}")
                self.success = False
            try:
                if hasattr(self.security, "configure_firewall"):
                    if not run_with_progress(
                        "Configuring firewall...", self.security.configure_firewall
                    ):
                        self.logger.warning("Firewall configuration failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "configure_firewall method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in firewall configuration: {e}")
                self.success = False
            try:
                if hasattr(self.security, "configure_fail2ban"):
                    if not run_with_progress(
                        "Configuring Fail2ban...", self.security.configure_fail2ban
                    ):
                        self.logger.warning("Fail2ban configuration failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "configure_fail2ban method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in Fail2ban configuration: {e}")
                self.success = False
            try:
                if hasattr(self.security, "configure_apparmor"):
                    if not run_with_progress(
                        "Configuring AppArmor...", self.security.configure_apparmor
                    ):
                        self.logger.warning("AppArmor configuration failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "configure_apparmor method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in AppArmor configuration: {e}")
                self.success = False
            print_section("Phase 6: Service Installations")
            try:
                if hasattr(self.services, "install_fastfetch"):
                    if not run_with_progress(
                        "Installing Fastfetch...",
                        self.services.install_fastfetch,
                        task_name="services",
                    ):
                        self.logger.warning("Fastfetch installation failed.")
                        self.success = False
                else:
                    self.logger.warning("install_fastfetch method not found, skipping.")
                    SETUP_STATUS["services"] = {
                        "status": "skipped",
                        "message": "install_fastfetch method not found",
                    }
            except Exception as e:
                self.logger.error(f"Error in Fastfetch installation: {e}")
                self.success = False
            try:
                if hasattr(self.services, "docker_config"):
                    if not run_with_progress(
                        "Configuring Docker...", self.services.docker_config
                    ):
                        self.logger.warning("Docker configuration failed.")
                        self.success = False
                else:
                    self.logger.warning("docker_config method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in Docker configuration: {e}")
                self.success = False
            try:
                if hasattr(self.services, "install_enable_tailscale"):
                    if not run_with_progress(
                        "Installing Tailscale...",
                        self.services.install_enable_tailscale,
                    ):
                        self.logger.warning("Tailscale installation failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "install_enable_tailscale method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in Tailscale installation: {e}")
                self.success = False
            try:
                if hasattr(self.services, "configure_unattended_upgrades"):
                    if not run_with_progress(
                        "Configuring unattended upgrades...",
                        self.services.configure_unattended_upgrades,
                    ):
                        self.logger.warning("Unattended upgrades configuration failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "configure_unattended_upgrades method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in unattended upgrades configuration: {e}")
                self.success = False
            try:
                if hasattr(self.services, "install_configure_caddy"):
                    if not run_with_progress(
                        "Installing Caddy...", self.services.install_configure_caddy
                    ):
                        self.logger.warning("Caddy installation failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "install_configure_caddy method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in Caddy installation: {e}")
                self.success = False
            try:
                if hasattr(self.services, "deploy_user_scripts"):
                    if not run_with_progress(
                        "Deploying user scripts...", self.services.deploy_user_scripts
                    ):
                        self.logger.warning("User scripts deployment failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "deploy_user_scripts method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in user scripts deployment: {e}")
                self.success = False
            print_section("Phase 7: Maintenance Tasks")
            try:
                if hasattr(self.maintenance, "configure_periodic"):
                    if not run_with_progress(
                        "Configuring periodic maintenance...",
                        self.maintenance.configure_periodic,
                        task_name="maintenance",
                    ):
                        self.logger.warning(
                            "Periodic maintenance configuration failed."
                        )
                        self.success = False
                else:
                    self.logger.warning(
                        "configure_periodic method not found, skipping."
                    )
                    SETUP_STATUS["maintenance"] = {
                        "status": "skipped",
                        "message": "configure_periodic method not found",
                    }
            except Exception as e:
                self.logger.error(f"Error in periodic maintenance configuration: {e}")
                self.success = False
            try:
                if hasattr(self.maintenance, "backup_configs"):
                    if not run_with_progress(
                        "Backing up configurations...", self.maintenance.backup_configs
                    ):
                        self.logger.warning("Configuration backup failed.")
                        self.success = False
                else:
                    self.logger.warning("backup_configs method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in configuration backup: {e}")
                self.success = False
            try:
                if hasattr(self.maintenance, "update_ssl_certificates"):
                    if not run_with_progress(
                        "Updating SSL certificates...",
                        self.maintenance.update_ssl_certificates,
                    ):
                        self.logger.warning("SSL certificate update failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "update_ssl_certificates method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in SSL certificate update: {e}")
                self.success = False
            print_section("Phase 8: System Tuning & Permissions")
            try:
                if hasattr(self.tuner, "tune_system"):
                    if not run_with_progress(
                        "Applying system tuning...",
                        self.tuner.tune_system,
                        task_name="tuning",
                    ):
                        self.logger.warning("System tuning failed.")
                        self.success = False
                else:
                    self.logger.warning("tune_system method not found, skipping.")
                    SETUP_STATUS["tuning"] = {
                        "status": "skipped",
                        "message": "tune_system method not found",
                    }
            except Exception as e:
                self.logger.error(f"Error in system tuning: {e}")
                self.success = False
            try:
                if hasattr(self.tuner, "home_permissions"):
                    if not run_with_progress(
                        "Setting home permissions...", self.tuner.home_permissions
                    ):
                        self.logger.warning(
                            "Home directory permission configuration failed."
                        )
                        self.success = False
                else:
                    self.logger.warning("home_permissions method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in home permissions setup: {e}")
                self.success = False
            print_section("Phase 9: Final Checks & Cleanup")
            SETUP_STATUS["final"] = {
                "status": "in_progress",
                "message": "Running final checks...",
            }
            try:
                if hasattr(self.final_checker, "system_health_check"):
                    self.final_checker.system_health_check()
                else:
                    self.logger.warning(
                        "system_health_check method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in system health check: {e}")
                self.success = False
            try:
                if hasattr(self.final_checker, "verify_firewall_rules"):
                    if not self.final_checker.verify_firewall_rules():
                        self.logger.warning("Firewall rule verification failed.")
                        self.success = False
                else:
                    self.logger.warning(
                        "verify_firewall_rules method not found, skipping."
                    )
            except Exception as e:
                self.logger.error(f"Error in firewall rule verification: {e}")
                self.success = False
            final_result = True
            try:
                if hasattr(self.final_checker, "final_checks"):
                    final_result = self.final_checker.final_checks()
                else:
                    self.logger.warning("final_checks method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in final checks: {e}")
                self.success = False
                final_result = False
            try:
                if hasattr(self.final_checker, "cleanup_system"):
                    self.final_checker.cleanup_system()
                else:
                    self.logger.warning("cleanup_system method not found, skipping.")
            except Exception as e:
                self.logger.error(f"Error in system cleanup: {e}")
                self.success = False
            duration = time.time() - self.start_time
            minutes, seconds = divmod(duration, 60)
            if self.success and final_result:
                self.logger.info(
                    f"Ubuntu Server Setup completed successfully in {int(minutes)}m {int(seconds)}s."
                )
                SETUP_STATUS["final"] = {
                    "status": "success",
                    "message": f"Completed successfully in {int(minutes)}m {int(seconds)}s.",
                }
            else:
                self.logger.warning(
                    f"Ubuntu Server Setup completed with warnings in {int(minutes)}m {int(seconds)}s."
                )
                SETUP_STATUS["final"] = {
                    "status": "warning",
                    "message": f"Completed with warnings in {int(minutes)}m {int(seconds)}s.",
                }
            try:
                print_status_report()
            except Exception as e:
                self.logger.error(f"Error printing status report: {e}")
            try:
                if hasattr(self.final_checker, "prompt_reboot"):
                    self.final_checker.prompt_reboot()
                else:
                    self.logger.debug(
                        "prompt_reboot method not found, skipping reboot prompt."
                    )
            except Exception as e:
                self.logger.error(f"Error in reboot prompt: {e}")
            return 0 if self.success and final_result else 1
        except KeyboardInterrupt:
            self.logger.warning("Setup interrupted by user.")
            return 130
        except Exception as e:
            self.logger.error(f"Unhandled exception: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return 1


def main() -> int:
    """Main entry point for the script."""
    setup_instance = UbuntuServerSetup()
    return setup_instance.run()


if __name__ == "__main__":
    sys.exit(main())
