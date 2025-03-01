#!/usr/bin/env python3
"""
Ubuntu Server Initialization and Hardening Utility

This utility automates the initialization, configuration, and security hardening
of an Ubuntu server. It is divided into clear phases:
  1. Pre-flight Checks
  2. Nala Installation
  3. System Update & Basic Configuration
  4. User Environment Setup
  5. Security & Access Hardening
  6. Service Installations
  7. Maintenance Tasks
  8. System Tuning & Permissions
  9. Final Checks & Cleanup

Run this script as root. Use --help for command-line options.

Author: dunamismax (refactored)
License: MIT
Version: 6.0.0
"""

import atexit
import argparse
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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

#####################################
# Global Configuration & Constants
#####################################

USERNAME = "sawyer"
USER_HOME = f"/home/{USERNAME}"
BACKUP_DIR = "/var/backups"
TEMP_DIR = tempfile.gettempdir()
LOG_FILE = "/var/log/ubuntu_setup.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB

# Software Versions and URLs
PLEX_VERSION = "1.41.4.9463-630c9f557"
PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_amd64.deb"
FASTFETCH_VERSION = "2.37.0"
FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"

# List of configuration files to back up
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

# TCP ports allowed through the firewall
ALLOWED_PORTS = ["22", "80", "443", "32400"]

# Essential packages to be installed
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
    "foot",
    "foot-themes",
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
    "mysql-client",
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

# Global task status dictionary
SETUP_STATUS: Dict[str, Dict[str, str]] = {
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

#####################################
# ANSI Color Codes (Nord Palette)
#####################################

NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"  # Reset color

#####################################
# Logging Setup with Nord Color Formatter
#####################################


class NordColorFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True,
    ):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.use_colors:
            return message
        if record.levelname == "DEBUG":
            return f"{NORD9}{message}{NC}"
        elif record.levelname == "INFO":
            return f"{NORD14}{message}{NC}"
        elif record.levelname == "WARNING":
            return f"{NORD13}{message}{NC}"
        elif record.levelname in ("ERROR", "CRITICAL"):
            return f"{NORD11}{message}{NC}"
        return message


def setup_logging() -> logging.Logger:
    os.makedirs(os.path.dirname(LOG_FILE), mode=0o700, exist_ok=True)
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        # Simple log rotation: archive the old log
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated_file = f"{LOG_FILE}.{timestamp}.gz"
        try:
            with open(LOG_FILE, "rb") as fin, gzip.open(rotated_file, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            open(LOG_FILE, "w").close()
        except Exception:
            pass
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    # Remove existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)
    formatter = NordColorFormatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if sys.stderr.isatty():
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


logger = setup_logging()

#####################################
# Helper Functions
#####################################


def print_section(title: str) -> None:
    border = "─" * 60
    print(f"{NORD8}{border}{NC}")
    print(f"{NORD8}  {title}{NC}")
    print(f"{NORD8}{border}{NC}")
    logger.info(f"--- {title} ---")


def print_status_report() -> None:
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
        icon = icons.get(status, "?")
        color = colors.get(status, "")
        print(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")


def run_with_progress(
    description: str, func, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
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
        print(f"{NORD11}[✗] {description} failed in {elapsed:.2f}s: {e}{NC}")
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "failed",
                "message": f"{description} failed: {e}",
            }
        raise


#####################################
# Signal Handling & Cleanup
#####################################


def signal_handler(signum: int, frame: Optional[Any]) -> None:
    sig_name = (
        getattr(signal, "Signals", lambda x: f"signal {x}")(signum).name
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


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


def cleanup() -> None:
    logger.info("Performing cleanup tasks before exit.")
    for fname in os.listdir(tempfile.gettempdir()):
        if fname.startswith("ubuntu_setup_"):
            try:
                os.remove(os.path.join(tempfile.gettempdir(), fname))
            except Exception:
                pass
    if any(item["status"] != "pending" for item in SETUP_STATUS.values()):
        print_status_report()


atexit.register(cleanup)

#####################################
# Utility Class
#####################################


class Utils:
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
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0


#####################################
# Phase 1: Pre-flight Checks
#####################################


class PreflightChecker:
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
        version = os_info.get("VERSION_ID", "")
        pretty_name = os_info.get("PRETTY_NAME", "Unknown")
        logger.info(f"Detected OS: {pretty_name}")
        supported = ["20.04", "22.04", "24.04"]
        if version not in supported:
            logger.warning(
                f"Ubuntu {version} is not officially supported. Supported versions: {', '.join(supported)}"
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
                        logger.debug(f"{cfg} not found; skipping.")
            logger.info(f"Configuration snapshot saved to {snapshot_file}")
            return snapshot_file
        except Exception as e:
            logger.warning(f"Failed to create configuration snapshot: {e}")
            return None


#####################################
# Phase 2: System Update & Basic Configuration
#####################################


class SystemUpdater:
    def fix_package_issues(self) -> bool:
        logger.info("Checking and fixing package management issues...")
        try:
            dpkg_status = Utils.run_command(
                ["dpkg", "--configure", "-a"],
                check=False,
                capture_output=True,
                text=True,
            )
            if dpkg_status.returncode != 0:
                logger.warning(f"dpkg issues: {dpkg_status.stderr}")
                Utils.run_command(["dpkg", "--configure", "-a"])
            held_packages = Utils.run_command(
                ["apt-mark", "showhold"], check=False, capture_output=True, text=True
            )
            if held_packages.stdout.strip():
                held_list = held_packages.stdout.strip().split("\n")
                logger.warning(f"Held packages: {', '.join(held_list)}")
                for pkg in held_list:
                    if pkg.strip():
                        try:
                            Utils.run_command(
                                ["apt-mark", "unhold", pkg.strip()], check=False
                            )
                            logger.info(f"Unheld package: {pkg}")
                        except Exception as e:
                            logger.warning(f"Failed to unhold {pkg}: {e}")
            logger.info("Fixing broken dependencies and cleaning caches...")
            Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
            Utils.run_command(["apt", "clean"], check=False)
            Utils.run_command(["apt", "autoclean", "-y"], check=False)
            check_result = Utils.run_command(
                ["apt-get", "check"], check=False, capture_output=True, text=True
            )
            if check_result.returncode != 0:
                logger.warning(f"Package check issues: {check_result.stderr}")
                Utils.run_command(["apt", "--fix-missing", "update"], check=False)
                Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
                final_check = Utils.run_command(
                    ["apt-get", "check"], check=False, capture_output=True, text=True
                )
                if final_check.returncode != 0:
                    logger.error("Unable to resolve package issues.")
                    return False
            logger.info("Package management issues fixed.")
            return True
        except Exception as e:
            logger.error(f"Error fixing package issues: {e}")
            return False

    def update_system(self, full_upgrade: bool = False) -> bool:
        logger.info("Updating repositories and upgrading packages...")
        try:
            if not self.fix_package_issues():
                logger.warning("Continuing despite package issues.")
            try:
                logger.info("Attempting update with Nala...")
                Utils.run_command(["nala", "update"])
            except Exception as e:
                logger.warning(f"Nala update failed: {e}; falling back to apt update")
                Utils.run_command(["apt", "update"])
            upgrade_cmd = (
                ["nala", "full-upgrade", "-y"]
                if full_upgrade
                else ["nala", "upgrade", "-y"]
            )
            try:
                logger.info(
                    f"Running {'full-upgrade' if full_upgrade else 'upgrade'}..."
                )
                Utils.run_command(upgrade_cmd)
            except Exception as e:
                logger.warning(f"Upgrade failed: {e}. Retrying fix_package_issues...")
                self.fix_package_issues()
                Utils.run_command(upgrade_cmd)
                logger.info("System upgrade succeeded on retry.")
            logger.info("System update completed successfully.")
            return True
        except Exception as e:
            logger.error(f"System update error: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        logger.info("Installing required packages...")
        packages = packages or PACKAGES
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
        if not self.fix_package_issues():
            logger.warning("Proceeding despite package issues.")
        missing = []
        logger.info("Checking for missing packages...")
        for pkg in packages:
            try:
                subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.debug(f"{pkg} already installed.")
            except subprocess.CalledProcessError:
                missing.append(pkg)
                logger.debug(f"{pkg} missing.")
        if not missing:
            logger.info("All packages already installed.")
            return True
        installer = ["nala", "install", "-y"]
        try:
            logger.info(f"Installing missing packages: {', '.join(missing)}")
            Utils.run_command(installer + missing)
            logger.info("All packages installed successfully.")
            return True
        except Exception as e:
            logger.error(f"Bulk package installation error: {e}")
            return False

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
            logger.info("Timezone configured.")
            return True
        except Exception as e:
            logger.error(f"Timezone configuration failed: {e}")
            return False

    def configure_locale(self, locale: str = "en_US.UTF-8") -> bool:
        logger.info(f"Setting locale to {locale}...")
        try:
            Utils.run_command(["locale-gen", locale])
            Utils.run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])
            env_file = "/etc/environment"
            lines = []
            locale_set = False
            if os.path.isfile(env_file):
                with open(env_file, "r") as f:
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
            logger.error(f"Locale configuration failed: {e}")
            return False


#####################################
# Phase 3: User Environment Setup
#####################################


class UserEnvironment:
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
                except Exception:
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
                    logger.info(f"Repository '{repo}' cloned.")
                except Exception:
                    logger.warning(f"Failed to clone repository '{repo}'.")
                    all_success = False
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", gh_dir])
            logger.info(f"Set ownership of '{gh_dir}' to '{USERNAME}'.")
        except Exception:
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
        all_success = True
        for file in files_to_copy:
            src = os.path.join(source_dir, file)
            if not os.path.isfile(src):
                logger.debug(f"{src} not found; skipping.")
                continue
            for dest_dir in destination_dirs:
                dest = os.path.join(dest_dir, file)
                copy_needed = True
                if os.path.isfile(dest) and filecmp.cmp(src, dest):
                    logger.info(f"{dest} is up-to-date.")
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
                        all_success = False
        return all_success

    def copy_config_folders(self) -> bool:
        logger.info("Synchronizing configuration folders...")
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
                    logger.info(f"Copied '{item}' to '{dest_path}'.")
            return success
        except Exception as e:
            logger.error(f"Error copying config folders: {e}")
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
            current_shell = (
                subprocess.check_output(["getent", "passwd", USERNAME], text=True)
                .strip()
                .split(":")[-1]
            )
            if current_shell != "/bin/bash":
                Utils.run_command(["chsh", "-s", "/bin/bash", USERNAME])
                logger.info(f"Default shell for {USERNAME} set to /bin/bash.")
            else:
                logger.info(f"{USERNAME}'s default shell is already /bin/bash.")
            return True
        except Exception as e:
            logger.error(f"Error setting default shell: {e}")
            return False


#####################################
# Phase 4: Security & Access Hardening
#####################################


class SecurityHardener:
    def configure_ssh(self, port: int = 22) -> bool:
        logger.info("Configuring SSH server...")
        try:
            Utils.run_command(["systemctl", "enable", "--now", "ssh"])
        except Exception as e:
            logger.error(f"Failed to start SSH: {e}")
            return False
        sshd_config = "/etc/ssh/sshd_config"
        if not os.path.isfile(sshd_config):
            logger.error(f"SSHD config not found: {sshd_config}")
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
            logger.error(f"Failed to update SSH config: {e}")
            return False
        try:
            Utils.run_command(["systemctl", "restart", "ssh"])
            logger.info("SSH configured successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to restart SSH: {e}")
            return False

    def setup_sudoers(self) -> bool:
        logger.info(f"Configuring sudoers for {USERNAME}...")
        try:
            Utils.run_command(["id", USERNAME], capture_output=True)
        except Exception:
            logger.error(f"User {USERNAME} does not exist.")
            return False
        try:
            groups = subprocess.check_output(["id", "-nG", USERNAME], text=True).split()
            if "sudo" not in groups:
                Utils.run_command(["usermod", "-aG", "sudo", USERNAME])
                logger.info(f"Added {USERNAME} to sudo group.")
            else:
                logger.info(f"{USERNAME} is already in sudo group.")
        except Exception as e:
            logger.error(f"Error updating sudo group: {e}")
            return False
        sudoers_file = f"/etc/sudoers.d/99-{USERNAME}"
        try:
            with open(sudoers_file, "w") as f:
                f.write(f"{USERNAME} ALL=(ALL:ALL) ALL\n")
                f.write("Defaults timestamp_timeout=15\n")
                f.write("Defaults requiretty\n")
            os.chmod(sudoers_file, 0o440)
            Utils.run_command(["visudo", "-c"], check=True)
            logger.info("Sudoers configuration set and verified.")
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
        except Exception:
            logger.warning("Failed to reset UFW.")
        for cmd in (
            [ufw_cmd, "default", "deny", "incoming"],
            [ufw_cmd, "default", "allow", "outgoing"],
        ):
            try:
                Utils.run_command(cmd)
                logger.info(f"Executed: {' '.join(cmd)}")
            except Exception:
                logger.warning(f"Failed to run: {' '.join(cmd)}")
        for port in ALLOWED_PORTS:
            try:
                Utils.run_command([ufw_cmd, "allow", f"{port}/tcp"])
                logger.info(f"Allowed TCP port {port}.")
            except Exception:
                logger.warning(f"Failed to allow port {port}.")
        try:
            status = Utils.run_command(
                [ufw_cmd, "status"], capture_output=True, text=True
            )
            if "inactive" in status.stdout.lower():
                Utils.run_command([ufw_cmd, "--force", "enable"])
                logger.info("UFW enabled.")
            else:
                logger.info("UFW already active.")
        except Exception as e:
            logger.error(f"Error retrieving UFW status: {e}")
            return False
        try:
            Utils.run_command([ufw_cmd, "logging", "on"])
            logger.info("UFW logging enabled.")
        except Exception:
            logger.warning("Failed to enable UFW logging.")
        try:
            Utils.run_command(["systemctl", "enable", "ufw"])
            Utils.run_command(["systemctl", "restart", "ufw"])
            logger.info("UFW service enabled and restarted.")
            return True
        except Exception as e:
            logger.error(f"UFW service management failed: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        logger.info("Configuring Fail2ban...")
        if not Utils.command_exists("fail2ban-server"):
            logger.info("Fail2ban not installed; installing...")
            if not SystemUpdater().install_packages(["fail2ban"]):
                logger.error("Failed to install Fail2ban.")
                return False
        jail_local = "/etc/fail2ban/jail.local"
        config_content = (
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
            "maxretry = 3\n\n"
            "[sshd-ddos]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "filter   = sshd-ddos\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n\n"
            "[nginx-http-auth]\n"
            "enabled = true\n"
            "filter = nginx-http-auth\n"
            "port = http,https\n"
            "logpath = /var/log/nginx/error.log\n\n"
            "[pam-generic]\n"
            "enabled = true\n"
            "banaction = %(banaction_allports)s\n"
            "logpath = /var/log/auth.log\n"
        )
        if os.path.isfile(jail_local):
            Utils.backup_file(jail_local)
        try:
            with open(jail_local, "w") as f:
                f.write(config_content)
            logger.info("Fail2ban configuration written.")
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
            logger.error(f"Fail2ban configuration error: {e}")
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
                        logger.warning(f"Profile update failed: {e}")
                else:
                    logger.warning(
                        "aa-update-profiles command not found; skipping update."
                    )
                return True
            else:
                logger.warning("AppArmor may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"AppArmor configuration error: {e}")
            return False


#####################################
# Phase 5: Service Installations
#####################################


class ServiceInstaller:
    def install_fastfetch(self) -> bool:
        logger.info("Installing Fastfetch...")
        if Utils.command_exists("fastfetch"):
            logger.info("Fastfetch already installed; skipping.")
            return True
        temp_deb = os.path.join(TEMP_DIR, "fastfetch-linux-amd64.deb")
        try:
            logger.debug(f"Downloading Fastfetch from {FASTFETCH_URL}...")
            Utils.run_command(["curl", "-L", "-o", temp_deb, FASTFETCH_URL])
            Utils.run_command(["dpkg", "-i", temp_deb])
            Utils.run_command(["nala", "install", "-f", "-y"])
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            if Utils.command_exists("fastfetch"):
                logger.info("Fastfetch installed successfully.")
                return True
            else:
                logger.error("Fastfetch installation verification failed.")
                return False
        except Exception as e:
            logger.error(f"Fastfetch installation error: {e}")
            return False

    def docker_config(self) -> bool:
        logger.info("Configuring Docker and Docker Compose...")
        if not Utils.command_exists("docker"):
            try:
                logger.info("Installing Docker via official script...")
                script_path = os.path.join(TEMP_DIR, "get-docker.sh")
                Utils.run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script_path]
                )
                os.chmod(script_path, 0o755)
                Utils.run_command([script_path], check=True)
                os.remove(script_path)
                logger.info("Docker installed successfully.")
            except Exception as e:
                logger.error(f"Docker installation failed: {e}")
                if not SystemUpdater().install_packages(["docker.io"]):
                    logger.error("Alternative Docker installation failed.")
                    return False
        try:
            groups = subprocess.check_output(["id", "-nG", USERNAME], text=True).split()
            if "docker" not in groups:
                Utils.run_command(["usermod", "-aG", "docker", USERNAME])
                logger.info(f"Added {USERNAME} to docker group.")
            else:
                logger.info(f"{USERNAME} already in docker group.")
        except Exception as e:
            logger.warning(f"Error adding {USERNAME} to docker group: {e}")
        daemon_json_path = "/etc/docker/daemon.json"
        os.makedirs("/etc/docker", exist_ok=True)
        desired_daemon_json = json.dumps(
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
        if os.path.isfile(daemon_json_path):
            try:
                with open(daemon_json_path, "r") as f:
                    existing = json.load(f)
                if existing == json.loads(desired_daemon_json):
                    logger.info("Docker daemon configuration is up-to-date.")
                    update_needed = False
                else:
                    Utils.backup_file(daemon_json_path)
            except Exception as e:
                logger.warning(f"Error reading {daemon_json_path}: {e}")
        if update_needed:
            try:
                with open(daemon_json_path, "w") as f:
                    f.write(desired_daemon_json)
                logger.info("Docker daemon configuration updated.")
            except Exception as e:
                logger.warning(f"Error writing {daemon_json_path}: {e}")
        try:
            Utils.run_command(["systemctl", "enable", "docker"])
            Utils.run_command(["systemctl", "restart", "docker"])
            logger.info("Docker service enabled and restarted.")
        except Exception as e:
            logger.error(f"Docker service error: {e}")
            return False
        if not Utils.command_exists("docker-compose"):
            try:
                Utils.run_command(["nala", "install", "docker-compose-plugin"])
                logger.info("Docker Compose plugin installed.")
            except Exception as e:
                logger.error(f"Docker Compose plugin installation failed: {e}")
                return False
        else:
            logger.info("Docker Compose already installed.")
        try:
            Utils.run_command(["docker", "info"], capture_output=True)
            logger.info("Docker is running.")
            return True
        except Exception:
            logger.error("Docker is not accessible.")
            return False

    def install_configure_caddy(self) -> bool:
        logger.info("Installing Caddy web server...")
        caddy_installed = False
        if Utils.command_exists("caddy"):
            logger.info("Caddy already installed.")
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
                logger.info("Caddy installed via repository.")
                caddy_installed = True
            except Exception as e:
                logger.error(f"Caddy installation error: {e}")
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
                logger.info(f"Copied Caddyfile from {caddyfile_source}.")
            else:
                if not os.path.isfile(caddyfile_dest):
                    with open(caddyfile_dest, "w") as f:
                        f.write(f"""# Default Caddy configuration
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
  <title>Server: {server_name}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; }}
    h1 {{ color: #2c3e50; }}
  </style>
</head>
<body>
  <h1>Welcome to {server_name}</h1>
  <p>Configured by Ubuntu Server Setup on {datetime.datetime.now().strftime("%Y-%m-%d")}.</p>
</body>
</html>
""")
                logger.info("Created default index.html.")
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
                logger.info("Caddy is active.")
                return True
            else:
                logger.warning("Caddy may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"Caddy configuration error: {e}")
            return caddy_installed

    def install_nala(self) -> bool:
        logger.info("Installing Nala (apt frontend)...")
        if Utils.command_exists("nala"):
            logger.info("Nala already installed.")
            return True
        try:
            Utils.run_command(["nala", "update"])
            Utils.run_command(["nala", "upgrade", "-y"])
            Utils.run_command(["apt", "--fix-broken", "install", "-y"])
            Utils.run_command(["apt", "install", "nala", "-y"])
            if Utils.command_exists("nala"):
                logger.info("Nala installed successfully.")
                try:
                    Utils.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    logger.info("Configured faster mirrors with Nala.")
                except Exception:
                    logger.warning("Failed to configure mirrors with Nala.")
                return True
            else:
                logger.error("Nala installation verification failed.")
                return False
        except Exception as e:
            logger.error(f"Nala installation error: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        logger.info("Installing and configuring Tailscale...")
        if Utils.command_exists("tailscale"):
            logger.info("Tailscale already installed.")
            tailscale_installed = True
        else:
            try:
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
                logger.error(f"Tailscale installation error: {e}")
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
                logger.info("Tailscale is active. To authenticate, run: tailscale up")
                return True
            else:
                logger.warning("Tailscale may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            logger.error(f"Tailscale enable/start error: {e}")
            return tailscale_installed

    def deploy_user_scripts(self) -> bool:
        logger.info("Deploying user scripts...")
        script_source = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts"
        )
        script_target = os.path.join(USER_HOME, "bin")
        if not os.path.isdir(script_source):
            logger.warning(f"Script source '{script_source}' does not exist.")
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
        except Exception as e:
            logger.error(f"User scripts deployment error: {e}")
            return False

    def configure_unattended_upgrades(self) -> bool:
        logger.info("Configuring unattended upgrades...")
        try:
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                logger.error("Failed to install unattended-upgrades packages.")
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
            logger.info(f"Auto-upgrades config written to {auto_file}.")
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
            with open(unattended_file, "w") as f:
                f.write(unattended_content)
            logger.info(f"Unattended-upgrades config written to {unattended_file}.")
            Utils.run_command(["systemctl", "enable", "unattended-upgrades"])
            Utils.run_command(["systemctl", "restart", "unattended-upgrades"])
            status = Utils.run_command(
                ["systemctl", "is-active", "unattended-upgrades"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Unattended-upgrades service is active.")
                return True
            else:
                logger.warning("Unattended-upgrades may not be running correctly.")
                return False
        except Exception as e:
            logger.error(f"Unattended-upgrades configuration error: {e}")
            return False


#####################################
# Phase 6: Maintenance Tasks
#####################################


class MaintenanceManager:
    def configure_periodic(self) -> bool:
        logger.info("Setting up daily maintenance cron job...")
        cron_file = "/etc/cron.daily/ubuntu_maintenance"
        marker = "# Ubuntu maintenance script"
        if os.path.isfile(cron_file):
            with open(cron_file, "r") as f:
                if marker in f.read():
                    logger.info("Daily maintenance cron job already exists.")
                    return True
            Utils.backup_file(cron_file)
        content = f"""#!/bin/sh
# Ubuntu maintenance script
# Created on $(date)

LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG
echo "Updating package lists..." >> $LOG
nala update -qq >> $LOG 2>&1
echo "Upgrading packages..." >> $LOG
nala upgrade -y >> $LOG 2>&1
echo "Removing unnecessary packages..." >> $LOG
nala autoremove -y >> $LOG 2>&1
echo "Cleaning package cache..." >> $LOG
nala clean >> $LOG 2>&1
echo "Disk usage:" >> $LOG
df -h / >> $LOG 2>&1
echo "Daily maintenance completed at $(date)" >> $LOG
"""
        try:
            with open(cron_file, "w") as f:
                f.write(content)
            os.chmod(cron_file, 0o755)
            logger.info(f"Daily maintenance cron job created at {cron_file}.")
            return True
        except Exception as e:
            logger.error(f"Error creating maintenance cron job: {e}")
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
                logger.debug(f"{file} not found; skipping.")
        try:
            manifest = os.path.join(backup_dir, "MANIFEST.txt")
            with open(manifest, "w") as f:
                f.write("Ubuntu Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {socket.gethostname()}\n\n")
                f.write("Files included:\n")
                for file in CONFIG_FILES:
                    if os.path.isfile(os.path.join(backup_dir, os.path.basename(file))):
                        f.write(f"- {file}\n")
            logger.info(f"Backup manifest created at {backup_dir}")
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
            logger.info("certbot dry-run completed.")
            if "No renewals were attempted" in output:
                logger.info("No certificates need renewal.")
            else:
                Utils.run_command(["certbot", "renew"])
                logger.info("SSL certificates updated.")
            return True
        except Exception as e:
            logger.warning(f"SSL certificate update failed: {e}")
            return False


#####################################
# Phase 7: System Tuning & Permissions
#####################################


class SystemTuner:
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
                logger.info("Tuning settings already exist; updating...")
                content = re.split(marker, content)[0]
            content += f"\n{marker}\n"
            for key, value in tuning_settings.items():
                content += f"{key} = {value}\n"
            with open(sysctl_conf, "w") as f:
                f.write(content)
            Utils.run_command(["sysctl", "-p"])
            logger.info("Performance tuning applied.")
            return True
        except Exception as e:
            logger.error(f"System tuning failed: {e}")
            return False

    def home_permissions(self) -> bool:
        logger.info(f"Securing home directory for {USERNAME}...")
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", USER_HOME])
            Utils.run_command(["chmod", "750", USER_HOME])
            for d in [
                os.path.join(USER_HOME, ".ssh"),
                os.path.join(USER_HOME, ".gnupg"),
                os.path.join(USER_HOME, ".config"),
            ]:
                if os.path.isdir(d):
                    Utils.run_command(["chmod", "700", d])
                    logger.info(f"Set secure permissions on {d}")
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
                logger.info("Default ACLs applied on home directory.")
            else:
                logger.warning("setfacl not found; skipping ACL configuration.")
            logger.info("Home directory secured.")
            return True
        except Exception as e:
            logger.error(f"Failed to secure home directory: {e}")
            return False


#####################################
# Phase 8: Final Checks & Cleanup
#####################################


class FinalChecker:
    def system_health_check(self) -> Dict[str, Any]:
        logger.info("Performing system health check...")
        health_data: Dict[str, Any] = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            logger.info(f"Uptime: {uptime}")
            health_data["uptime"] = uptime
        except Exception as e:
            logger.warning(f"Failed to get uptime: {e}")
        try:
            df_lines = (
                subprocess.check_output(["df", "-h", "/"], text=True)
                .strip()
                .splitlines()
            )
            if len(df_lines) >= 2:
                data = df_lines[1].split()
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
                    logger.warning(f"Disk usage warning: {percent}% used.")
        except Exception as e:
            logger.warning(f"Disk usage check failed: {e}")
        try:
            free_lines = (
                subprocess.check_output(["free", "-h"], text=True).strip().splitlines()
            )
            for line in free_lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    health_data["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                    }
                    logger.info(f"Memory usage: {line}")
        except Exception as e:
            logger.warning(f"Memory usage check failed: {e}")
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().split()[:3]
            logger.info(f"Load averages: {', '.join(load)}")
            health_data["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
            cpu_count = os.cpu_count() or 1
            if float(load[1]) > cpu_count:
                logger.warning(
                    f"High 5min load: {load[1]} exceeds CPU count ({cpu_count})."
                )
        except Exception as e:
            logger.warning(f"Load average check failed: {e}")
        try:
            dmesg_output = subprocess.check_output(
                ["dmesg", "--level=err,crit,alert,emerg"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if dmesg_output:
                logger.warning("Recent kernel errors detected:")
                for line in dmesg_output.splitlines()[-5:]:
                    logger.warning(line)
                health_data["kernel_errors"] = True
            else:
                logger.info("No kernel errors detected.")
                health_data["kernel_errors"] = False
        except Exception as e:
            logger.warning(f"Kernel error check failed: {e}")
        try:
            updates = (
                subprocess.check_output(
                    ["nala", "list", "--upgradable"],
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
                    f"Updates available: {total_updates} total, {security_updates} security"
                )
                if security_updates > 0:
                    logger.warning(f"Security updates available: {security_updates}")
                health_data["updates"] = {
                    "total": total_updates,
                    "security": security_updates,
                }
            else:
                logger.info("System up to date.")
                health_data["updates"] = {"total": 0, "security": 0}
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
        return health_data

    def verify_firewall_rules(self) -> bool:
        logger.info("Verifying firewall rules...")
        all_correct = True
        try:
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            logger.info("UFW status:")
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
                        logger.info(f"Port {port} is listening but may be firewalled.")
                    else:
                        logger.warning(f"Port {port} is closed.")
                        all_correct = False
            except Exception as e:
                logger.warning(f"Error checking port {port}: {e}")
                all_correct = False
        return all_correct

    def final_checks(self) -> bool:
        logger.info("Performing final system checks...")
        all_passed = True
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            logger.info(f"Kernel: {kernel}")
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            logger.info(f"System uptime: {uptime}")
            disk_usage_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            logger.info(f"Disk usage: {disk_usage_line}")
            disk_percent = int(disk_usage_line.split()[4].strip("%"))
            if disk_percent > 90:
                logger.warning("Critical disk usage over 90%!")
                all_passed = False
            free_lines = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((l for l in free_lines if l.startswith("Mem:")), "")
            logger.info(f"Memory usage: {mem_line}")
            cpu_info = subprocess.check_output(["lscpu"], text=True)
            for line in cpu_info.splitlines():
                if "Model name" in line:
                    logger.info(f"CPU: {line.split(':', 1)[1].strip()}")
                    break
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            logger.info("Network interfaces:")
            for line in interfaces.splitlines():
                logger.info(line)
            load_avg = open("/proc/loadavg").read().split()[:3]
            logger.info(f"Load averages: {', '.join(load_avg)}")
            cpu_count = os.cpu_count() or 1
            if float(load_avg[1]) > cpu_count:
                logger.warning(
                    f"5min load ({load_avg[1]}) exceeds CPU count ({cpu_count})."
                )
            services = [
                "ssh",
                "ufw",
                "fail2ban",
                "caddy",
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
                if status.stdout.strip() == "active":
                    logger.info(f"{svc}: active")
                else:
                    logger.warning(f"{svc}: {status.stdout.strip()}")
                    if svc in ["ssh", "ufw"]:
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
                    logger.warning("Pending security updates detected!")
                    all_passed = False
            except Exception:
                logger.debug("Could not check unattended upgrades.")
            return all_passed
        except Exception as e:
            logger.error(f"Final checks error: {e}")
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
                old_kernels = []
                for line in installed:
                    if line.startswith("ii"):
                        parts = line.split()
                        pkg = parts[1]
                        if (
                            pkg
                            in (
                                f"linux-image-{current_kernel}",
                                f"linux-headers-{current_kernel}",
                            )
                            or "generic" not in pkg
                        ):
                            continue
                        old_kernels.append(pkg)
                if len(old_kernels) > 1:
                    old_kernels.sort()
                    to_remove = old_kernels[:-1]
                    if to_remove:
                        logger.info(f"Removing old kernels: {', '.join(to_remove)}")
                        Utils.run_command(["apt", "purge", "-y"] + to_remove)
                else:
                    logger.info("No old kernels to remove.")
            except Exception as e:
                logger.warning(f"Old kernels removal failed: {e}")
            if Utils.command_exists("journalctl"):
                Utils.run_command(["journalctl", "--vacuum-time=7d"])
                logger.info("Old journal logs cleared.")
            for tmp in ["/tmp", "/var/tmp"]:
                try:
                    Utils.run_command(
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
                    logger.info(f"Cleaned temporary directory {tmp}.")
                except Exception as e:
                    logger.warning(f"Failed to clean {tmp}: {e}")
            try:
                log_files = (
                    subprocess.check_output(
                        ["find", "/var/log", "-type", "f", "-size", "+50M"], text=True
                    )
                    .strip()
                    .splitlines()
                )
                for lf in log_files:
                    logger.debug(f"Compressing {lf}")
                    with open(lf, "rb") as fin, gzip.open(f"{lf}.gz", "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                    open(lf, "w").close()
            except Exception as e:
                logger.warning(f"Log rotation failed: {e}")
            logger.info("System cleanup completed.")
            return success
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return False

    def prompt_reboot(self) -> None:
        logger.info("Prompting for reboot...")
        print(
            f"{NORD14}Setup completed! A reboot is recommended to apply all changes.{NC}"
        )
        answer = input("Reboot now? [y/N]: ").strip().lower()
        if answer == "y":
            logger.info("Rebooting system...")
            try:
                Utils.run_command(["shutdown", "-r", "now"])
            except Exception as e:
                logger.warning(f"Reboot failed: {e}")
        else:
            logger.info("Reboot canceled. Please reboot later.")


#####################################
# Main Orchestrator
#####################################


class UbuntuServerSetup:
    def __init__(self) -> None:
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
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{NORD8}{'-' * 40}{NC}")
        print(f"{NORD8}  Starting Ubuntu Server Setup v6.0.0{NC}")
        print(f"{NORD8}  {now}{NC}")
        print(f"{NORD8}{'-' * 40}{NC}")
        logger.info(f"Starting Ubuntu Server Setup v6.0.0 at {datetime.datetime.now()}")

        # Phase 1: Pre-flight Checks
        print_section("Phase 1: Pre-flight Checks")
        try:
            run_with_progress(
                "Running Pre-flight Checks...",
                self.preflight.check_root,
                task_name="preflight",
            )
            if not self.preflight.check_network():
                logger.error("Network check failed. Aborting.")
                SETUP_STATUS["preflight"] = {
                    "status": "failed",
                    "message": "Network check failed",
                }
                sys.exit(1)
            if not self.preflight.check_os_version():
                logger.warning("OS version check failed; proceeding with caution.")
            self.preflight.save_config_snapshot()
        except Exception as e:
            logger.error(f"Preflight phase error: {e}")
            self.success = False

        # Fix broken package installations
        print_section("Fixing Broken Packages")

        def fix_broken():
            backup_dir = "/etc/apt/apt.conf.d/"
            for fname in os.listdir(backup_dir):
                if fname.startswith("50unattended-upgrades.bak."):
                    try:
                        os.remove(os.path.join(backup_dir, fname))
                        logger.info(f"Removed backup file: {fname}")
                    except Exception as e:
                        logger.warning(f"Could not remove {fname}: {e}")
            return Utils.run_command(["apt", "--fix-broken", "install", "-y"])

        run_with_progress(
            "Running apt --fix-broken install", fix_broken, task_name="fix_broken"
        )

        # Phase 2: Nala Installation
        print_section("Phase 2: Installing Nala")
        try:
            if not run_with_progress(
                "Installing Nala...",
                self.services.install_nala,
                task_name="nala_install",
            ):
                logger.error("Nala installation failed. Proceeding with caution.")
                self.success = False
        except Exception as e:
            logger.error(f"Nala installation error: {e}")
            self.success = False

        # Phase 3: System Update & Basic Configuration
        print_section("Phase 3: System Update & Basic Configuration")
        try:
            if not run_with_progress(
                "Updating system...",
                self.updater.update_system,
                task_name="system_update",
            ):
                logger.warning("System update failed; continuing.")
                self.success = False
        except Exception as e:
            logger.error(f"System update error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Installing packages...",
                self.updater.install_packages,
                task_name="packages_install",
            ):
                logger.warning("Package installation encountered issues.")
                self.success = False
        except Exception as e:
            logger.error(f"Package installation error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring timezone...", self.updater.configure_timezone
            ):
                logger.warning("Timezone configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Timezone configuration error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring locale...", self.updater.configure_locale
            ):
                logger.warning("Locale configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Locale configuration error: {e}")
            self.success = False

        # Phase 4: User Environment Setup
        print_section("Phase 4: User Environment Setup")
        try:
            if not run_with_progress(
                "Setting up user repositories...",
                self.user_env.setup_repos,
                task_name="user_env",
            ):
                logger.warning("Repository setup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Repository setup error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Copying shell configs...", self.user_env.copy_shell_configs
            ):
                logger.warning("Shell configuration update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Shell config error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Copying config folders...", self.user_env.copy_config_folders
            ):
                logger.warning("Configuration folder copy failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Config folder copy error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Setting default shell...", self.user_env.set_bash_shell
            ):
                logger.warning("Default shell update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Bash shell error: {e}")
            self.success = False

        # Phase 5: Security & Access Hardening
        print_section("Phase 5: Security & Access Hardening")
        try:
            if not run_with_progress(
                "Configuring SSH...", self.security.configure_ssh, task_name="security"
            ):
                logger.warning("SSH configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSH configuration error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring sudoers...", self.security.setup_sudoers
            ):
                logger.warning("Sudoers configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Sudoers error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring firewall...", self.security.configure_firewall
            ):
                logger.warning("Firewall configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall configuration error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring Fail2ban...", self.security.configure_fail2ban
            ):
                logger.warning("Fail2ban configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fail2ban error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring AppArmor...", self.security.configure_apparmor
            ):
                logger.warning("AppArmor configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"AppArmor error: {e}")
            self.success = False

        # Phase 6: Service Installations
        print_section("Phase 6: Service Installations")
        try:
            if not run_with_progress(
                "Installing Fastfetch...",
                self.services.install_fastfetch,
                task_name="services",
            ):
                logger.warning("Fastfetch installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Fastfetch error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring Docker...", self.services.docker_config
            ):
                logger.warning("Docker configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Docker error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Installing Tailscale...", self.services.install_enable_tailscale
            ):
                logger.warning("Tailscale installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Tailscale error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring unattended upgrades...",
                self.services.configure_unattended_upgrades,
            ):
                logger.warning("Unattended upgrades configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Unattended upgrades error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Installing Caddy...", self.services.install_configure_caddy
            ):
                logger.warning("Caddy installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Caddy error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Deploying user scripts...", self.services.deploy_user_scripts
            ):
                logger.warning("User scripts deployment failed.")
                self.success = False
        except Exception as e:
            logger.error(f"User scripts error: {e}")
            self.success = False

        # Phase 7: Maintenance Tasks
        print_section("Phase 7: Maintenance Tasks")
        try:
            if not run_with_progress(
                "Configuring periodic maintenance...",
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
                "Backing up configurations...", self.maintenance.backup_configs
            ):
                logger.warning("Configuration backup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Backup configs error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Updating SSL certificates...", self.maintenance.update_ssl_certificates
            ):
                logger.warning("SSL certificate update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"SSL update error: {e}")
            self.success = False

        # Phase 8: System Tuning & Permissions
        print_section("Phase 8: System Tuning & Permissions")
        try:
            if not run_with_progress(
                "Applying system tuning...", self.tuner.tune_system, task_name="tuning"
            ):
                logger.warning("System tuning failed.")
                self.success = False
        except Exception as e:
            logger.error(f"System tuning error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Securing home directory...", self.tuner.home_permissions
            ):
                logger.warning("Home directory permission setup failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Home permissions error: {e}")
            self.success = False

        # Phase 9: Final Checks & Cleanup
        print_section("Phase 9: Final Checks & Cleanup")
        SETUP_STATUS["final"] = {
            "status": "in_progress",
            "message": "Running final checks...",
        }
        try:
            self.final_checker.system_health_check()
        except Exception as e:
            logger.error(f"System health check error: {e}")
            self.success = False
        try:
            if not self.final_checker.verify_firewall_rules():
                logger.warning("Firewall rule verification failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Firewall verification error: {e}")
            self.success = False
        final_result = True
        try:
            final_result = self.final_checker.final_checks()
        except Exception as e:
            logger.error(f"Final checks error: {e}")
            self.success = False
            final_result = False
        try:
            self.final_checker.cleanup_system()
        except Exception as e:
            logger.error(f"System cleanup error: {e}")
            self.success = False

        duration = time.time() - self.start_time
        minutes, seconds = divmod(duration, 60)
        if self.success and final_result:
            logger.info(
                f"Setup completed successfully in {int(minutes)}m {int(seconds)}s."
            )
            SETUP_STATUS["final"] = {
                "status": "success",
                "message": f"Completed in {int(minutes)}m {int(seconds)}s.",
            }
        else:
            logger.warning(
                f"Setup completed with warnings in {int(minutes)}m {int(seconds)}s."
            )
            SETUP_STATUS["final"] = {
                "status": "warning",
                "message": f"Completed with warnings in {int(minutes)}m {int(seconds)}s.",
            }
        try:
            print_status_report()
        except Exception as e:
            logger.error(f"Error printing status report: {e}")
        try:
            self.final_checker.prompt_reboot()
        except Exception as e:
            logger.error(f"Reboot prompt error: {e}")
        return 0 if self.success and final_result else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ubuntu Server Initialization and Hardening Utility"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run (simulate actions without making changes)",
    )
    args = parser.parse_args()
    # For this example, dry-run is not implemented separately.
    setup_instance = UbuntuServerSetup()
    return setup_instance.run()


if __name__ == "__main__":
    sys.exit(main())
