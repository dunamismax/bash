#!/usr/bin/env python3
"""
Ubuntu Server Setup & Hardening Utility for ARM (Raspberry Pi)
----------------------------------------------------------------

This script automates the initialization and hardening of an Ubuntu server
running on a Raspberry Pi (aarch64). It performs preflight checks, system updates,
package installations, user environment setup, security hardening, service installations,
maintenance tasks, system tuning, and final health checks.

Run with root privileges.
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

import pyfiglet
from rich.console import Console
from rich.theme import Theme
from rich.logging import RichHandler

# ----------------------------------------------------------------
# Global Configuration & Constants
# ----------------------------------------------------------------
THEME = Theme(
    {
        "nord0": "#2E3440",
        "nord1": "#3B4252",
        "nord8": "#88C0D0",
        "nord9": "#81A1C1",
        "nord10": "#5E81AC",
        "nord11": "#BF616A",
        "nord13": "#EBCB8B",
        "nord14": "#A3BE8C",
    }
)
console: Console = Console(theme=THEME)

# Log and backup settings
LOG_FILE: str = "/var/log/ubuntu_setup.log"
MAX_LOG_SIZE: int = 10 * 1024 * 1024
USERNAME: str = "sawyer"
USER_HOME: str = f"/home/{USERNAME}"
BACKUP_DIR: str = "/var/backups"
TEMP_DIR: str = tempfile.gettempdir()

# Package download settings updated for ARM (aarch64)
PLEX_VERSION: str = "1.41.4.9463-630c9f557"
PLEX_URL: str = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_arm64.deb"
FASTFETCH_VERSION: str = "2.37.0"
FASTFETCH_URL: str = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-arm64.deb"

# Files, ports and package lists to manage
CONFIG_FILES: List[str] = [
    "/etc/ssh/sshd_config",
    "/etc/ufw/user.rules",
    "/etc/ntp.conf",
    "/etc/sysctl.conf",
    "/etc/environment",
    "/etc/fail2ban/jail.local",
    "/etc/docker/daemon.json",
    "/etc/caddy/Caddyfile",
]
ALLOWED_PORTS: List[str] = ["22", "80", "443", "32400"]

# Adjusted package list for ARM Raspberry Pi (pruned to avoid problematic packages)
PACKAGES: List[str] = [
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
    "liblzma-dev",
    "libxml2-dev",
    "libxmlsec1-dev",
    "ca-certificates",
    "software-properties-common",
    "apt-transport-https",
    "gnupg",
    "lsb-release",
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
    "fail2ban",
    "rkhunter",
    "chkrootkit",
    "postgresql-client",
    "mysql-client",
    "jq",
    "yq",
    "certbot",
    "p7zip-full",
    "nala",
]

# A status dictionary to track phases of the setup
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


# ----------------------------------------------------------------
# Logging, Banner and Console Helpers
# ----------------------------------------------------------------
def setup_logging() -> logging.Logger:
    """Initialize logging with rotating file support and Rich output."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated = f"{LOG_FILE}.{ts}.gz"
        try:
            with open(LOG_FILE, "rb") as fin, gzip.open(rotated, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            open(LOG_FILE, "w").close()
        except Exception:
            pass
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, markup=True, console=console),
            logging.FileHandler(LOG_FILE),
        ],
    )
    return logging.getLogger("ubuntu_setup")


logger: logging.Logger = setup_logging()


def print_header(text: str) -> None:
    """Print a large ASCII art header."""
    ascii_art: str = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold nord14")


def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold nord8]{text}[/bold nord8]")
    logger.info(f"--- {text} ---")


def print_step(text: str) -> None:
    """Print a step message."""
    console.print(f"[nord8]• {text}[/nord8]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold nord14]✓ {text}[/bold nord14]")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold nord13]⚠ {text}[/bold nord13]")


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold nord11]✗ {text}[/bold nord11]")


# ----------------------------------------------------------------
# Command Execution with Progress
# ----------------------------------------------------------------
def run_with_progress(
    desc: str, func, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """
    Run a function with a progress indicator.
    Update SETUP_STATUS accordingly.
    """
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{desc} in progress...",
        }
    with console.status(f"[bold nord8]{desc}...[/]"):
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
                    "message": f"{desc} completed successfully.",
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
def signal_handler(signum: int, frame: Optional[Any]) -> None:
    sig_name = (
        getattr(signal, "Signals", lambda s: f"signal {s}")(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")
    sys.exit(
        130
        if signum == signal.SIGINT
        else 143
        if signum == signal.SIGTERM
        else 128 + signum
    )


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)


def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    logger.info("Performing cleanup tasks before exit.")
    # Remove temporary files starting with 'ubuntu_setup_'
    for fname in os.listdir(TEMP_DIR):
        if fname.startswith("ubuntu_setup_"):
            try:
                os.remove(os.path.join(TEMP_DIR, fname))
            except Exception:
                pass
    # Display final status if any task is not pending
    if any(item["status"] != "pending" for item in SETUP_STATUS.values()):
        status_report()


atexit.register(cleanup)


def status_report() -> None:
    """Display a summary of setup task statuses."""
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
        "success": "nord14",
        "failed": "nord11",
        "pending": "nord13",
        "in_progress": "nord9",
        "skipped": "nord0",
        "warning": "nord13",
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
        st = data["status"]
        msg = data["message"]
        console.print(
            f"[{colors.get(st, '')}]{icons.get(st, '?')} {descriptions.get(task, task)}: {st.upper()}[/] - {msg}"
        )


# ----------------------------------------------------------------
# Utility Functions & Classes
# ----------------------------------------------------------------
class Utils:
    """Helper utilities for command execution, backups, and directory management."""

    @staticmethod
    def run_command(
        cmd: Union[List[str], str],
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        logger.debug(f"Executing: {cmd_str}")
        try:
            return subprocess.run(
                cmd, check=check, capture_output=capture_output, text=text, **kwargs
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd_str} (exit {e.returncode})")
            logger.debug(f"Error: {getattr(e, 'stderr', 'N/A')}")
            raise

    @staticmethod
    def command_exists(cmd: str) -> bool:
        return shutil.which(cmd) is not None

    @staticmethod
    def backup_file(fp: str) -> Optional[str]:
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
        logger.warning(f"{fp} not found; skipping backup.")
        return None

    @staticmethod
    def ensure_directory(
        path: str, owner: Optional[str] = None, mode: int = 0o755
    ) -> bool:
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            if owner:
                Utils.run_command(["chown", owner, path])
            logger.debug(f"Directory ensured: {path}")
            return True
        except Exception as e:
            logger.warning(f"Ensure directory failed for {path}: {e}")
            return False

    @staticmethod
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            res = s.connect_ex((host, port))
        return res == 0


# ----------------------------------------------------------------
# Preflight & Environment Checkers
# ----------------------------------------------------------------
class PreflightChecker:
    """Perform preflight checks like root privileges, network, and OS version."""

    def check_root(self) -> None:
        if os.geteuid() != 0:
            print_error("Error: Must run as root.")
            console.print(f"Run with: sudo {sys.argv[0]}")
            sys.exit(1)
        logger.info("Root privileges confirmed.")

    def check_network(self) -> bool:
        logger.info("Checking network connectivity...")
        for host in ["google.com", "cloudflare.com", "1.1.1.1"]:
            try:
                if (
                    Utils.run_command(
                        ["ping", "-c", "1", "-W", "5", host],
                        check=False,
                        capture_output=True,
                    ).returncode
                    == 0
                ):
                    logger.info(f"Network via {host} OK.")
                    return True
            except Exception as e:
                logger.debug(f"Ping {host} failed: {e}")
        logger.error("Network check failed.")
        return False

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        logger.info("Checking OS version...")
        if not os.path.isfile("/etc/os-release"):
            logger.warning("/etc/os-release missing")
            return None
        os_info: Dict[str, str] = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_info[k] = v.strip('"')
        if os_info.get("ID") != "ubuntu":
            logger.warning(f"Non-Ubuntu system: {os_info.get('ID', 'unknown')}")
            return None
        ver = os_info.get("VERSION_ID", "")
        logger.info(f"OS: {os_info.get('PRETTY_NAME', 'Unknown')}")
        if ver not in ["20.04", "22.04", "24.04"]:
            logger.warning(f"Ubuntu {ver} may be unsupported.")
        return ("ubuntu", ver)

    def save_config_snapshot(self) -> Optional[str]:
        logger.info("Saving configuration snapshot...")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        snapshot = os.path.join(BACKUP_DIR, f"config_snapshot_{ts}.tar.gz")
        try:
            with tarfile.open(snapshot, "w:gz") as tar:
                for cfg in CONFIG_FILES:
                    if os.path.isfile(cfg):
                        tar.add(cfg, arcname=os.path.basename(cfg))
                        logger.info(f"Added {cfg}")
                    else:
                        logger.debug(f"Skipped {cfg}")
            logger.info(f"Snapshot saved to {snapshot}")
            return snapshot
        except Exception as e:
            logger.warning(f"Snapshot creation failed: {e}")
            return None


# ----------------------------------------------------------------
# System Updater and Package Installer
# ----------------------------------------------------------------
class SystemUpdater:
    """Update the system and install required packages."""

    def fix_package_issues(self) -> bool:
        logger.info("Fixing package issues...")
        try:
            dpkg_status = Utils.run_command(
                ["dpkg", "--configure", "-a"], check=False, capture_output=True
            )
            if dpkg_status.returncode != 0:
                logger.warning(f"dpkg issues: {dpkg_status.stderr}")
                Utils.run_command(["dpkg", "--configure", "-a"])
            held = Utils.run_command(
                ["apt-mark", "showhold"], check=False, capture_output=True, text=True
            )
            if held.stdout.strip():
                for pkg in held.stdout.strip().split("\n"):
                    if pkg.strip():
                        try:
                            Utils.run_command(
                                ["apt-mark", "unhold", pkg.strip()], check=False
                            )
                        except Exception as e:
                            logger.warning(f"Unhold for {pkg} failed: {e}")
            Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
            Utils.run_command(["apt", "clean"], check=False)
            Utils.run_command(["apt", "autoclean", "-y"], check=False)
            check = Utils.run_command(
                ["apt-get", "check"], check=False, capture_output=True, text=True
            )
            if check.returncode != 0:
                logger.warning(f"apt-get check issues: {check.stderr}")
                Utils.run_command(["apt", "--fix-missing", "update"], check=False)
                Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
                final = Utils.run_command(
                    ["apt-get", "check"], check=False, capture_output=True, text=True
                )
                if final.returncode != 0:
                    logger.error("Package issues unresolved.")
                    return False
            logger.info("Package issues fixed.")
            return True
        except Exception as e:
            logger.error(f"Error fixing package issues: {e}")
            return False

    def update_system(self, full_upgrade: bool = False) -> bool:
        logger.info("Updating system...")
        try:
            if not self.fix_package_issues():
                logger.warning("Proceeding despite package issues.")
            try:
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
                Utils.run_command(upgrade_cmd)
            except Exception as e:
                logger.warning(f"Upgrade failed: {e}. Retrying...")
                self.fix_package_issues()
                Utils.run_command(upgrade_cmd)
            logger.info("System update completed.")
            return True
        except Exception as e:
            logger.error(f"System update error: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
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
            logger.info("All packages are already installed.")
            return True
        try:
            Utils.run_command(["nala", "install", "-y"] + missing)
            logger.info("Missing packages installed.")
            return True
        except Exception as e:
            logger.error(f"Error installing packages: {e}")
            return False

    def configure_timezone(self, tz: str = "America/New_York") -> bool:
        logger.info(f"Setting timezone to {tz}...")
        tz_file = f"/usr/share/zoneinfo/{tz}"
        if not os.path.isfile(tz_file):
            logger.warning(f"Timezone file {tz_file} not found.")
            return False
        try:
            if Utils.command_exists("timedatectl"):
                Utils.run_command(["timedatectl", "set-timezone", tz])
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
        logger.info(f"Setting locale to {locale}...")
        try:
            Utils.run_command(["locale-gen", locale])
            Utils.run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])
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
    """Set up user repositories, shell configuration, and dotfiles."""

    def setup_repos(self) -> bool:
        logger.info(f"Setting up repositories for {USERNAME}...")
        gh_dir = os.path.join(USER_HOME, "github")
        Utils.ensure_directory(gh_dir, owner=f"{USERNAME}:{USERNAME}")
        repos = ["bash", "windows", "web", "python", "go", "misc"]
        all_success = True
        for repo in repos:
            repo_dir = os.path.join(gh_dir, repo)
            if os.path.isdir(os.path.join(repo_dir, ".git")):
                try:
                    Utils.run_command(["git", "-C", repo_dir, "pull"], check=False)
                except Exception:
                    logger.warning(f"Update failed for repo: {repo}")
                    all_success = False
            else:
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
                except Exception:
                    logger.warning(f"Clone failed for repo: {repo}")
                    all_success = False
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", gh_dir])
        except Exception:
            logger.warning(f"Ownership update failed for {gh_dir}.")
            all_success = False
        return all_success

    def copy_shell_configs(self) -> bool:
        logger.info("Updating shell configuration files...")
        files = [".bashrc", ".profile"]
        src_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        if not os.path.isdir(src_dir):
            logger.warning(f"Source directory {src_dir} not found.")
            return False
        dest_dirs = [USER_HOME, "/root"]
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
                            f"{USERNAME}:{USERNAME}" if d == USER_HOME else "root:root"
                        )
                        Utils.run_command(["chown", owner, dest])
                    except Exception as e:
                        logger.warning(f"Copying {src} to {dest} failed: {e}")
                        all_success = False
        return all_success

    def copy_config_folders(self) -> bool:
        logger.info("Synchronizing configuration folders...")
        src_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        dest_dir = os.path.join(USER_HOME, ".config")
        Utils.ensure_directory(dest_dir, owner=f"{USERNAME}:{USERNAME}")
        success = True
        try:
            for item in os.listdir(src_dir):
                src_path = os.path.join(src_dir, item)
                if os.path.isdir(src_path):
                    dest_path = os.path.join(dest_dir, item)
                    os.makedirs(dest_path, exist_ok=True)
                    Utils.run_command(
                        ["rsync", "-a", "--update", f"{src_path}/", f"{dest_path}/"]
                    )
                    Utils.run_command(
                        ["chown", "-R", f"{USERNAME}:{USERNAME}", dest_path]
                    )
            return success
        except Exception as e:
            logger.error(f"Error copying configuration folders: {e}")
            return False

    def set_bash_shell(self) -> bool:
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
                subprocess.check_output(["getent", "passwd", USERNAME], text=True)
                .strip()
                .split(":")[-1]
            )
            if current_shell != "/bin/bash":
                Utils.run_command(["chsh", "-s", "/bin/bash", USERNAME])
            return True
        except Exception as e:
            logger.error(f"Error setting default shell: {e}")
            return False


# ----------------------------------------------------------------
# Security Hardening
# ----------------------------------------------------------------
class SecurityHardener:
    """Harden system security by configuring SSH, sudoers, firewall, fail2ban, and AppArmor."""

    def configure_ssh(self, port: int = 22) -> bool:
        logger.info("Configuring SSH service...")
        try:
            Utils.run_command(["systemctl", "enable", "--now", "ssh"])
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
            Utils.run_command(["systemctl", "restart", "ssh"])
            return True
        except Exception as e:
            logger.error(f"Error restarting SSH: {e}")
            return False

    def setup_sudoers(self) -> bool:
        logger.info(f"Configuring sudoers for {USERNAME}...")
        try:
            Utils.run_command(["id", USERNAME], capture_output=True)
        except Exception:
            logger.error(f"User {USERNAME} not found.")
            return False
        try:
            groups = subprocess.check_output(["id", "-nG", USERNAME], text=True).split()
            if "sudo" not in groups:
                Utils.run_command(["usermod", "-aG", "sudo", USERNAME])
        except Exception as e:
            logger.error(f"Error updating sudo group: {e}")
            return False
        sudo_file = f"/etc/sudoers.d/99-{USERNAME}"
        try:
            with open(sudo_file, "w") as f:
                f.write(
                    f"{USERNAME} ALL=(ALL:ALL) ALL\nDefaults timestamp_timeout=15\nDefaults requiretty\n"
                )
            os.chmod(sudo_file, 0o440)
            Utils.run_command(["visudo", "-c"], check=True)
            return True
        except Exception as e:
            logger.error(f"Error configuring sudoers: {e}")
            return False

    def configure_firewall(self) -> bool:
        logger.info("Configuring UFW firewall...")
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            if not SystemUpdater().install_packages(["ufw"]):
                return False
        try:
            Utils.run_command([ufw_cmd, "reset", "--force"], check=False)
        except Exception:
            pass
        for cmd in (
            [ufw_cmd, "default", "deny", "incoming"],
            [ufw_cmd, "default", "allow", "outgoing"],
        ):
            try:
                Utils.run_command(cmd)
            except Exception:
                pass
        for port in ALLOWED_PORTS:
            try:
                Utils.run_command([ufw_cmd, "allow", f"{port}/tcp"])
            except Exception:
                pass
        try:
            status = Utils.run_command(
                [ufw_cmd, "status"], capture_output=True, text=True
            )
            if "inactive" in status.stdout.lower():
                Utils.run_command([ufw_cmd, "--force", "enable"])
        except Exception as e:
            return False
        try:
            Utils.run_command([ufw_cmd, "logging", "on"])
        except Exception:
            pass
        try:
            Utils.run_command(["systemctl", "enable", "ufw"])
            Utils.run_command(["systemctl", "restart", "ufw"])
            return True
        except Exception as e:
            return False

    def configure_fail2ban(self) -> bool:
        logger.info("Configuring Fail2ban...")
        if not Utils.command_exists("fail2ban-server"):
            if not SystemUpdater().install_packages(["fail2ban"]):
                return False
        jail = "/etc/fail2ban/jail.local"
        config = (
            "[DEFAULT]\nbantime  = 3600\nfindtime = 600\nmaxretry = 3\nbackend  = systemd\nusedns   = warn\n\n"
            "[sshd]\nenabled  = true\nport     = ssh\nfilter   = sshd\nlogpath  = /var/log/auth.log\nmaxretry = 3\n\n"
            "[sshd-ddos]\nenabled  = true\nport     = ssh\nfilter   = sshd-ddos\nlogpath  = /var/log/auth.log\nmaxretry = 3\n\n"
            "[nginx-http-auth]\nenabled = true\nfilter = nginx-http-auth\nport = http,https\nlogpath = /var/log/nginx/error.log\n\n"
            "[pam-generic]\nenabled = true\nbanaction = %(banaction_allports)s\nlogpath = /var/log/auth.log\n"
        )
        if os.path.isfile(jail):
            Utils.backup_file(jail)
        try:
            with open(jail, "w") as f:
                f.write(config)
            Utils.run_command(["systemctl", "enable", "fail2ban"])
            Utils.run_command(["systemctl", "restart", "fail2ban"])
            status = Utils.run_command(
                ["systemctl", "is-active", "fail2ban"],
                capture_output=True,
                text=True,
                check=False,
            )
            return status.stdout.strip() == "active"
        except Exception:
            return False

    def configure_apparmor(self) -> bool:
        logger.info("Configuring AppArmor...")
        try:
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
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
                if Utils.command_exists("aa-update-profiles"):
                    try:
                        Utils.run_command(["aa-update-profiles"], check=False)
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
    """Install and configure various services such as Fastfetch, Docker, Caddy, Nala, Tailscale, and user scripts."""

    def install_fastfetch(self) -> bool:
        logger.info("Installing Fastfetch...")
        if Utils.command_exists("fastfetch"):
            return True
        temp_deb = os.path.join(TEMP_DIR, "fastfetch-linux-arm64.deb")
        try:
            Utils.run_command(["curl", "-L", "-o", temp_deb, FASTFETCH_URL])
            Utils.run_command(["dpkg", "-i", temp_deb])
            Utils.run_command(["nala", "install", "-f", "-y"])
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            return Utils.command_exists("fastfetch")
        except Exception:
            return False

    def docker_config(self) -> bool:
        logger.info("Configuring Docker...")
        if not Utils.command_exists("docker"):
            try:
                script_path = os.path.join(TEMP_DIR, "get-docker.sh")
                Utils.run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script_path]
                )
                os.chmod(script_path, 0o755)
                Utils.run_command([script_path], check=True)
                os.remove(script_path)
            except Exception as e:
                if not SystemUpdater().install_packages(["docker.io"]):
                    return False
        try:
            groups = subprocess.check_output(["id", "-nG", USERNAME], text=True).split()
            if "docker" not in groups:
                Utils.run_command(["usermod", "-aG", "docker", USERNAME])
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
            Utils.run_command(["systemctl", "enable", "docker"])
            Utils.run_command(["systemctl", "restart", "docker"])
        except Exception as e:
            return False
        if not Utils.command_exists("docker-compose"):
            try:
                Utils.run_command(["nala", "install", "docker-compose-plugin"])
            except Exception:
                return False
        try:
            Utils.run_command(["docker", "info"], capture_output=True)
            return True
        except Exception:
            return False

    def install_configure_caddy(self) -> bool:
        logger.info("Installing and configuring Caddy...")
        caddy_installed = Utils.command_exists("caddy")
        if not caddy_installed:
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
                caddy_installed = True
            except Exception:
                return False
        try:
            Utils.ensure_directory("/etc/caddy", "root:root", 0o755)
            Utils.ensure_directory("/var/log/caddy", "caddy:caddy", 0o755)
            caddy_src = os.path.join(
                USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles", "Caddyfile"
            )
            caddy_dest = "/etc/caddy/Caddyfile"
            if os.path.isfile(caddy_src):
                if os.path.isfile(caddy_dest):
                    Utils.backup_file(caddy_dest)
                shutil.copy2(caddy_src, caddy_dest)
            else:
                if not os.path.isfile(caddy_dest):
                    with open(caddy_dest, "w") as f:
                        f.write(
                            "# Default Caddy configuration\n:80 {\n    root * /var/www/html\n    file_server\n    log {\n        output file /var/log/caddy/access.log\n        format console\n    }\n}\n"
                        )
            Utils.run_command(["chown", "root:caddy", caddy_dest])
            Utils.run_command(["chmod", "644", caddy_dest])
            Utils.ensure_directory("/var/www/html", "caddy:caddy", 0o755)
            index = "/var/www/html/index.html"
            if not os.path.isfile(index):
                with open(index, "w") as f:
                    f.write(
                        f"<!DOCTYPE html>\n<html lang='en'>\n<head>\n  <meta charset='UTF-8'>\n  <title>Server: {socket.gethostname()}</title>\n</head>\n<body>\n  <h1>Welcome to {socket.gethostname()}</h1>\n  <p>Configured on {datetime.datetime.now().strftime('%Y-%m-%d')}.</p>\n</body>\n</html>\n"
                    )
            Utils.run_command(["chown", "caddy:caddy", index])
            Utils.run_command(["chmod", "644", index])
            Utils.run_command(["systemctl", "enable", "caddy"])
            Utils.run_command(["systemctl", "restart", "caddy"])
            status = Utils.run_command(
                ["systemctl", "is-active", "caddy"],
                capture_output=True,
                text=True,
                check=False,
            )
            return status.stdout.strip() == "active"
        except Exception:
            return caddy_installed

    def install_nala(self) -> bool:
        logger.info("Installing Nala...")
        if Utils.command_exists("nala"):
            return True
        try:
            Utils.run_command(["nala", "update"])
            Utils.run_command(["nala", "upgrade", "-y"])
            Utils.run_command(["apt", "--fix-broken", "install", "-y"])
            Utils.run_command(["apt", "install", "nala", "-y"])
            if Utils.command_exists("nala"):
                try:
                    Utils.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False

    def install_enable_tailscale(self) -> bool:
        logger.info("Installing and enabling Tailscale...")
        if not Utils.command_exists("tailscale"):
            try:
                Utils.run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )
            except Exception:
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
            return status.stdout.strip() == "active"
        except Exception:
            return Utils.command_exists("tailscale")

    def deploy_user_scripts(self) -> bool:
        logger.info("Deploying user scripts...")
        src = os.path.join(USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts")
        tgt = os.path.join(USER_HOME, "bin")
        if not os.path.isdir(src):
            return False
        Utils.ensure_directory(tgt, owner=f"{USERNAME}:{USERNAME}")
        try:
            Utils.run_command(["rsync", "-ah", "--delete", f"{src}/", f"{tgt}/"])
            Utils.run_command(
                ["find", tgt, "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", tgt])
            return True
        except Exception:
            return False

    def configure_unattended_upgrades(self) -> bool:
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
            Utils.run_command(["systemctl", "enable", "unattended-upgrades"])
            Utils.run_command(["systemctl", "restart", "unattended-upgrades"])
            status = Utils.run_command(
                ["systemctl", "is-active", "unattended-upgrades"],
                capture_output=True,
                text=True,
                check=False,
            )
            return status.stdout.strip() == "active"
        except Exception:
            return False


# ----------------------------------------------------------------
# Maintenance Manager
# ----------------------------------------------------------------
class MaintenanceManager:
    """Handle maintenance tasks such as cron job setup, config backups, and SSL certificate updates."""

    def configure_periodic(self) -> bool:
        logger.info("Setting up daily maintenance cron job...")
        cron_file = "/etc/cron.daily/ubuntu_maintenance"
        marker = "# Ubuntu maintenance script"
        if os.path.isfile(cron_file):
            with open(cron_file) as f:
                if marker in f.read():
                    return True
            Utils.backup_file(cron_file)
        content = f"""#!/bin/sh
{marker}
LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG
nala update -qq >> $LOG 2>&1
nala upgrade -y >> $LOG 2>&1
nala autoremove -y >> $LOG 2>&1
nala clean >> $LOG 2>&1
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
        logger.info("Backing up configuration files...")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(BACKUP_DIR, f"ubuntu_config_{ts}")
        os.makedirs(backup_dir, exist_ok=True)
        success = True
        for file in CONFIG_FILES:
            if os.path.isfile(file):
                try:
                    shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
                except Exception as e:
                    logger.warning(f"Backup failed for {file}: {e}")
                    success = False
        try:
            manifest = os.path.join(backup_dir, "MANIFEST.txt")
            with open(manifest, "w") as f:
                f.write("Ubuntu Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {socket.gethostname()}\n\nFiles:\n")
                for file in CONFIG_FILES:
                    if os.path.isfile(os.path.join(backup_dir, os.path.basename(file))):
                        f.write(f"- {file}\n")
        except Exception:
            pass
        return success

    def update_ssl_certificates(self) -> bool:
        logger.info("Updating SSL certificates...")
        if not Utils.command_exists("certbot"):
            if not SystemUpdater().install_packages(["certbot"]):
                return False
        try:
            output = Utils.run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True, text=True
            ).stdout
            if "No renewals were attempted" not in output:
                Utils.run_command(["certbot", "renew"])
            return True
        except Exception:
            return False


# ----------------------------------------------------------------
# System Tuning and Home Permissions
# ----------------------------------------------------------------
class SystemTuner:
    """Apply system tuning settings and secure user home directory permissions."""

    def tune_system(self) -> bool:
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
            marker = "# Performance tuning settings for Ubuntu"
            if marker in content:
                content = re.split(marker, content)[0]
            content += f"\n{marker}\n" + "".join(
                f"{k} = {v}\n" for k, v in tuning.items()
            )
            with open(sysctl_conf, "w") as f:
                f.write(content)
            Utils.run_command(["sysctl", "-p"])
            return True
        except Exception:
            return False

    def home_permissions(self) -> bool:
        logger.info(f"Securing home directory for {USERNAME}...")
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", USER_HOME])
            Utils.run_command(["chmod", "750", USER_HOME])
            for sub in [".ssh", ".gnupg", ".config"]:
                d = os.path.join(USER_HOME, sub)
                if os.path.isdir(d):
                    Utils.run_command(["chmod", "700", d])
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
            return True
        except Exception:
            return False


# ----------------------------------------------------------------
# Final Health Check and Cleanup
# ----------------------------------------------------------------
class FinalChecker:
    """Perform final system health checks, firewall verification, and cleanup."""

    def system_health_check(self) -> Dict[str, Any]:
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
            health["updates"] = {"total": total_updates, "security": security_updates}
        except Exception:
            pass
        return health

    def verify_firewall_rules(self) -> bool:
        logger.info("Verifying firewall rules...")
        all_correct = True
        try:
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            if "inactive" in ufw_status.lower():
                return False
        except Exception:
            pass
        for port in ALLOWED_PORTS:
            try:
                result = subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if result.returncode != 0 and not Utils.is_port_open(int(port)):
                    all_correct = False
            except Exception:
                all_correct = False
        return all_correct

    def final_checks(self) -> bool:
        logger.info("Performing final system checks...")
        all_passed = True
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            disk_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            disk_percent = int(disk_line.split()[4].strip("%"))
            if disk_percent > 90:
                all_passed = False
            load_avg = open("/proc/loadavg").read().split()[:3]
            cpu_count = os.cpu_count() or 1
            if float(load_avg[1]) > cpu_count:
                all_passed = False
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
                if status.stdout.strip() != "active" and svc in ["ssh", "ufw"]:
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
                    all_passed = False
            except Exception:
                pass
            return all_passed
        except Exception:
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
                        Utils.run_command(["apt", "purge", "-y"] + to_remove)
            except Exception:
                pass
            if Utils.command_exists("journalctl"):
                Utils.run_command(["journalctl", "--vacuum-time=7d"])
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

    def prompt_reboot(self) -> None:
        console.print("[bold nord14]Setup completed! A reboot is recommended.[/]")
        ans = input("Reboot now? [y/N]: ").strip().lower()
        if ans == "y":
            try:
                Utils.run_command(["shutdown", "-r", "now"])
            except Exception:
                pass


# ----------------------------------------------------------------
# Ubuntu Server Setup Orchestration
# ----------------------------------------------------------------
class UbuntuServerSetup:
    """Main orchestration class for Ubuntu Server Setup."""

    def __init__(self) -> None:
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
        console.print(f"[nord8]{'-' * 40}[/]")
        console.print(f"[nord8]  Starting Ubuntu Server Setup for ARM (v6.0.0)[/]")
        console.print(f"[nord8]  {now}[/]")
        console.print(f"[nord8]{'-' * 40}[/]")
        logger.info(
            f"Starting Ubuntu Server Setup for ARM (v6.0.0) at {datetime.datetime.now()}"
        )

        # Phase 1: Pre-flight Checks
        print_section("Phase 1: Pre-flight Checks")
        try:
            run_with_progress(
                "Running Pre-flight Checks...",
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
                logger.warning("OS version check failed; proceeding anyway.")
            self.preflight.save_config_snapshot()
        except Exception as e:
            logger.error(f"Preflight error: {e}")
            self.success = False

        # Fix any broken packages
        print_section("Fixing Broken Packages")

        def fix_broken():
            backup_dir = "/etc/apt/apt.conf.d/"
            for fname in os.listdir(backup_dir):
                if fname.startswith("50unattended-upgrades.bak."):
                    try:
                        os.remove(os.path.join(backup_dir, fname))
                    except Exception:
                        pass
            return Utils.run_command(["apt", "--fix-broken", "install", "-y"])

        run_with_progress(
            "Running apt --fix-broken install", fix_broken, task_name="fix_broken"
        )

        # Phase 2: Installing Nala
        print_section("Phase 2: Installing Nala")
        try:
            if not run_with_progress(
                "Installing Nala...",
                self.services.install_nala,
                task_name="nala_install",
            ):
                logger.error("Nala installation failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Nala error: {e}")
            self.success = False

        # Phase 3: System Update & Basic Configuration
        print_section("Phase 3: System Update & Basic Configuration")
        try:
            if not run_with_progress(
                "Updating system...",
                self.updater.update_system,
                task_name="system_update",
            ):
                logger.warning("System update failed.")
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
                logger.warning("Package installation issues.")
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
            logger.error(f"Timezone error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Configuring locale...", self.updater.configure_locale
            ):
                logger.warning("Locale configuration failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Locale error: {e}")
            self.success = False

        # Phase 4: User Environment Setup
        print_section("Phase 4: User Environment Setup")
        try:
            if not run_with_progress(
                "Setting up user repositories...",
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
                "Copying shell configs...", self.user_env.copy_shell_configs
            ):
                logger.warning("Shell configuration update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Shell configs error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Copying config folders...", self.user_env.copy_config_folders
            ):
                logger.warning("Config folder copy failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Config folders error: {e}")
            self.success = False
        try:
            if not run_with_progress(
                "Setting default shell...", self.user_env.set_bash_shell
            ):
                logger.warning("Default shell update failed.")
                self.success = False
        except Exception as e:
            logger.error(f"Set shell error: {e}")
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
            logger.error(f"SSH error: {e}")
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
            logger.error(f"Firewall error: {e}")
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
                logger.warning("Home directory security failed.")
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
        except Exception as e:
            logger.error(f"Final checks error: {e}")
            self.success = False
            final_result = False
        try:
            self.final_checker.cleanup_system()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            self.success = False

        duration = time.time() - self.start_time
        minutes, seconds = divmod(duration, 60)
        if self.success and final_result:
            SETUP_STATUS["final"] = {
                "status": "success",
                "message": f"Completed in {int(minutes)}m {int(seconds)}s.",
            }
        else:
            SETUP_STATUS["final"] = {
                "status": "warning",
                "message": f"Completed with warnings in {int(minutes)}m {int(seconds)}s.",
            }
        try:
            status_report()
        except Exception as e:
            logger.error(f"Status report error: {e}")
        try:
            self.final_checker.prompt_reboot()
        except Exception as e:
            logger.error(f"Reboot prompt error: {e}")
        return 0 if self.success and final_result else 1


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ubuntu Server Initialization and Hardening Utility for ARM (Raspberry Pi)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making changes",
    )
    args = parser.parse_args()
    return UbuntuServerSetup().run()


if __name__ == "__main__":
    sys.exit(main())
