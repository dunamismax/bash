#!/usr/bin/env python3
"""
ubuntu_desktop.py

Ubuntu Desktop Initialization & Maintenance Utility

This automation script configures and optimizes an Ubuntu Desktop environment by performing the following tasks:

  - Pre-flight checks: Verify root privileges and network connectivity.
  - System update: Refresh repositories and upgrade installed packages.
  - Package installation: Install essential applications and utilities.
  - Desktop configuration: Set timezone, update user settings, and configure desktop preferences.
  - Security hardening: Secure SSH, configure UFW firewall, and set up fail2ban.
  - Service deployment: Install and configure key services (e.g., Plex, Docker) and desktop applications.
  - Maintenance routines: Schedule cron jobs, rotate logs, and perform system health checks.
  - Advanced features: Configure ZFS storage, Wayland settings, and additional security measures.
  - Final steps: Clean up temporary files and prompt for system reboot.

Usage:
  Run this script with root privileges to initialize and optimize your Ubuntu Desktop:
      sudo ./ubuntu_desktop.py

Disclaimer:
  THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY. USE AT YOUR OWN RISK.

Author: dunamismax (improved by Claude)
Version: 5.0.0
Date: 2025-02-25
"""

import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ----------------------------
# Configuration Class
# ----------------------------
@dataclass
class Config:
    """Configuration class to store all global settings."""
    # Software versions and download URLs
    PLEX_VERSION: str = "1.41.3.9314-a0bfb8370"
    FASTFETCH_VERSION: str = "2.36.1"
    DOCKER_COMPOSE_VERSION: str = "2.20.2"

    # Constructed URLs
    PLEX_URL: str = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_amd64.deb"
    FASTFETCH_URL: str = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"

    # System information
    UNAME: Any = platform.uname()
    DOCKER_COMPOSE_URL: str = f"https://github.com/docker/compose/releases/download/v{DOCKER_COMPOSE_VERSION}/docker-compose-{UNAME.system}-{UNAME.machine}"

    # Logging and user configuration  
    LOG_FILE: str = "/var/log/ubuntu_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = Path(f"/home/{USERNAME}")

    # Directories and files
    CONFIG_SRC_DIR: Path = USER_HOME / "github/bash/linux/ubuntu/dotfiles"
    CONFIG_DEST_DIR: Path = USER_HOME / ".config"

    # ZFS configuration
    ZFS_POOL_NAME: str = "WD_BLACK"
    ZFS_MOUNT_POINT: Path = Path(f"/media/{ZFS_POOL_NAME}")

    # Terminal color definitions (Nord theme)
    NORD9: str = "\033[38;2;129;161;193m"    # Debug messages
    NORD10: str = "\033[38;2;94;129;172m"     # Secondary info
    NORD11: str = "\033[38;2;191;97;106m"     # Error messages
    NORD13: str = "\033[38;2;235;203;139m"    # Warning messages
    NORD14: str = "\033[38;2;163;190;140m"    # Info messages
    NC: str = "\033[0m"                       # Reset color

    # Essential packages to install
    PACKAGES: List[str] = [
        "bash", "vim", "nano", "screen", "tmux", "mc", "zsh", "htop", "btop", 
        "foot", "foot-themes", "tree", "ncdu", "neofetch",
        "build-essential", "cmake", "ninja-build", "meson", "gettext", "git", 
        "pkg-config",
        "openssh-server", "ufw", "curl", "wget", "rsync", "sudo", "bash-completion",
        "python3", "python3-dev", "python3-pip", "python3-venv", "libssl-dev", 
        "libffi-dev", "zlib1g-dev", "libreadline-dev", "libbz2-dev", "tk-dev", 
        "xz-utils", "libncurses5-dev", "libgdbm-dev", "libnss3-dev", "liblzma-dev", 
        "libxml2-dev", "libxmlsec1-dev",
        "ca-certificates", "software-properties-common", "apt-transport-https", 
        "gnupg", "lsb-release",
        "clang", "llvm", "netcat-openbsd", "lsof", "unzip", "zip",
        "xorg", "x11-xserver-utils", "xterm", "alacritty", "fonts-dejavu-core",
        "net-tools", "nmap", "iftop", "iperf3", "tcpdump", "lynis", "traceroute", "mtr",
        "iotop", "glances",
        "golang-go", "gdb", "cargo",
        "john", "hydra", "aircrack-ng", "nikto", "fail2ban", "rkhunter", "chkrootkit",
        "postgresql-client", "mysql-client", "redis-server",
        "ruby", "rustc", "jq", "yq", "certbot",
        "p7zip-full",
        "qemu-system", "libvirt-clients", "libvirt-daemon-system", "virt-manager", 
        "qemu-user-static",
    ]

    # Flatpak applications to install
    FLATPAK_APPS: List[str] = [
        "com.discordapp.Discord",
        "com.usebottles.bottles",
        "com.valvesoftware.Steam",
        "com.spotify.Client",
        "org.videolan.VLC",
        "org.libretro.RetroArch",
        "com.obsproject.Studio",
        "com.github.tchx84.Flatseal",
        "net.lutris.Lutris",
        "net.davidotek.pupgui2",
        "org.gimp.GIMP",
        "org.qbittorrent.qBittorrent",
        "com.github.Matoking.protontricks",
        "md.obsidian.Obsidian",
        "org.prismlauncher.PrismLauncher",
        "com.bitwarden.desktop",
        "org.kde.kdenlive",
        "org.signal.Signal",
        "org.gnome.Boxes",
        "com.stremio.Stremio",
        "org.blender.Blender",
        "org.localsend.localsend_app",
        "fr.handbrake.ghb",
        "org.remmina.Remmina",
        "org.audacityteam.Audacity",
        "com.rustdesk.RustDesk",
        "com.getpostman.Postman",
        "io.github.aandrew_me.ytdn",
        "org.shotcut.Shotcut",
        "com.calibre_ebook.calibre",
        "tv.plex.PlexDesktop",
        "org.filezillaproject.Filezilla",
        "com.github.k4zmu2a.spacecadetpinball",
        "org.virt_manager.virt-manager",
        "org.raspberrypi.rpi-imager",
    ]

    # Wayland environment variables
    WAYLAND_ENV_VARS: Dict[str, str] = {
        "GDK_BACKEND": "wayland",
        "QT_QPA_PLATFORM": "wayland",
        "SDL_VIDEODRIVER": "wayland",
    }

    # GitHub repositories to set up
    GITHUB_REPOS: List[str] = ["bash", "windows", "web", "python", "go", "misc"]

    # SSH security settings
    SSH_SETTINGS: Dict[str, str] = {
        "Port": "22",
        "PermitRootLogin": "no",
        "PasswordAuthentication": "no",
        "PermitEmptyPasswords": "no",
        "ChallengeResponseAuthentication": "no",
        "Protocol": "2",
        "MaxAuthTries": "5",
        "ClientAliveInterval": "600",
        "ClientAliveCountMax": "48",
    }

    # Firewall TCP ports to allow
    FIREWALL_PORTS: List[str] = ["22", "80", "443", "32400"]

    # Configuration files to backup
    CONFIG_BACKUP_FILES: List[str] = [
        "/etc/ssh/sshd_config",
        "/etc/ufw/user.rules",
        "/etc/ntp.conf",
        "/etc/sysctl.conf",
        "/etc/environment",
        "/etc/fail2ban/jail.local",
        "/etc/docker/daemon.json",
        "/etc/caddy/Caddyfile",
    ]


# ----------------------------
# Main Setup Class
# ----------------------------
class UbuntuDesktopSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = self.setup_logging(self.config.LOG_FILE)

    # ----------------------------
    # Logging Setup
    # ----------------------------
    def setup_logging(self, log_file: str) -> logging.Logger:
        """Configure logging to both file and console with color support."""
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o700, exist_ok=True)

        logger_obj = logging.getLogger("ubuntu_setup")
        logger_obj.setLevel(logging.DEBUG)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger_obj.addHandler(fh)

        # Define custom color formatter for console
        class ColorFormatter(logging.Formatter):
            def __init__(self, fmt=None, datefmt=None, config=None):
                super().__init__(fmt, datefmt)
                self.config = config or self.config
                self.COLORS = {
                    "DEBUG": self.config.NORD9,
                    "INFO": self.config.NORD14,
                    "WARNING": self.config.NORD13,
                    "ERROR": self.config.NORD11,
                    "CRITICAL": self.config.NORD11,
                }
            def format(self, record):
                color = self.COLORS.get(record.levelname, "")
                message = super().format(record)
                return f"{color}{message}{self.config.NC}"

        if sys.stderr.isatty():
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S", self.config))
            logger_obj.addHandler(ch)
        return logger_obj

    # ----------------------------
    # Utility Methods
    # ----------------------------
    def run_command(self, cmd: Union[List[str], str],
                    check: bool = True,
                    capture_output: bool = False,
                    text: bool = True,
                    **kwargs) -> subprocess.CompletedProcess:
        """Execute a shell command with logging and error handling."""
        cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
        self.logger.debug(f"Executing command: {cmd_str}")
        try:
            result = subprocess.run(cmd, check=check, capture_output=capture_output, text=text, **kwargs)
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed with exit code {e.returncode}: {cmd_str}")
            if e.stdout:
                self.logger.error(f"Command stdout: {e.stdout}")
            if e.stderr:
                self.logger.error(f"Command stderr: {e.stderr}")
            if check:
                raise
            return e

    def command_exists(self, cmd: str) -> bool:
        """Check if a command exists in the system's PATH."""
        return shutil.which(cmd) is not None

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Create a backup of a file with a timestamp suffix."""
        file_path = Path(file_path)
        if file_path.is_file():
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = f"{file_path}.bak.{timestamp}"
            try:
                shutil.copy2(file_path, backup)
                self.logger.info(f"Backed up {file_path} to {backup}")
                return backup
            except Exception as e:
                self.logger.warning(f"Failed to backup {file_path}: {e}")
        else:
            self.logger.warning(f"File {file_path} not found; skipping backup.")
        return None

    def print_section(self, title: str) -> None:
        """Log a section header to improve readability of log output."""
        border = "─" * 60
        self.logger.info(f"{self.config.NORD10}{border}{self.config.NC}")
        self.logger.info(f"{self.config.NORD10}  {title}{self.config.NC}")
        self.logger.info(f"{self.config.NORD10}{border}{self.config.NC}")

    def handle_error(self, msg: str, code: int = 1) -> None:
        """Log an error message and exit the script."""
        self.logger.error(f"{msg} (Exit Code: {code})")
        sys.exit(code)

    def cleanup(self) -> None:
        """Perform any necessary cleanup tasks before the script exits."""
        self.logger.info("Performing cleanup tasks before exit.")
        # Additional cleanup tasks can be added here

    def create_symlink(self, source: Union[str, Path], target: Union[str, Path], backup: bool = True) -> bool:
        """Create a symbolic link with optional backup of the target if it exists."""
        source, target = Path(source), Path(target)
        if not source.exists():
            self.logger.warning(f"Source file {source} does not exist, cannot create symlink.")
            return False
        if target.exists() or target.is_symlink():
            if backup:
                self.backup_file(target)
            try:
                target.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to remove existing target {target}: {e}")
                return False
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(source)
            self.logger.info(f"Created symlink from {source} to {target}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create symlink from {source} to {target}: {e}")
            return False

    def copy_with_backup(self, src: Union[str, Path], dest: Union[str, Path]) -> bool:
        """Copy a file with automatic backup of the destination if it exists."""
        src, dest = Path(src), Path(dest)
        if not src.exists():
            self.logger.warning(f"Source file {src} does not exist, cannot copy.")
            return False
        if dest.exists():
            self.backup_file(dest)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            self.logger.info(f"Copied {src} to {dest}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
            return False

    def download_file(self, url: str, dest_path: Union[str, Path], show_progress: bool = False) -> bool:
        """Download a file from a URL with optional progress indicator."""
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["curl", "-L"]
        if not show_progress:
            cmd.append("-s")
        cmd.extend(["-o", str(dest_path), url])
        try:
            self.run_command(cmd)
            if dest_path.exists():
                self.logger.info(f"Downloaded {url} to {dest_path}")
                return True
            else:
                self.logger.warning(f"Download command succeeded but file {dest_path} does not exist")
                return False
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to download {url}")
            return False

    def ensure_directory(self, path: Union[str, Path], mode: int = 0o755, owner: Optional[str] = None) -> bool:
        """Ensure a directory exists with the specified permissions and ownership."""
        path = Path(path)
        try:
            path.mkdir(mode=mode, parents=True, exist_ok=True)
            self.logger.info(f"Ensured directory exists: {path}")
            if owner:
                self.run_command(["chown", owner, str(path)])
                self.logger.info(f"Set ownership of {path} to {owner}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create or set permissions on directory {path}: {e}")
            return False

    def has_internet_connection(self) -> bool:
        """Check if the system has an active internet connection."""
        try:
            self.run_command(["ping", "-c", "1", "-W", "5", "8.8.8.8"], capture_output=True, check=False)
            return True
        except Exception:
            return False

    # ----------------------------
    # Pre-requisites and System Checks
    # ----------------------------
    def check_root(self) -> None:
        """Ensure the script is run as root."""
        if os.geteuid() != 0:
            self.handle_error("Script must be run as root. Exiting.")

    def check_network(self) -> None:
        """Verify network connectivity by pinging a reliable host."""
        self.print_section("Network Connectivity Check")
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.handle_error("No network connectivity. Please verify your network settings.")

    def save_config_snapshot(self) -> Optional[str]:
        """
        Create a compressed archive of key configuration files as a snapshot backup
        before making any changes.
        """
        self.print_section("Configuration Snapshot Backup")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        snapshot_file = backup_dir / f"config_snapshot_{timestamp}.tar.gz"
        try:
            backup_dir.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                files_added = 0
                for cfg_path in self.config.CONFIG_BACKUP_FILES:
                    cfg_path = Path(cfg_path)
                    if cfg_path.is_file():
                        dest = temp_dir_path / cfg_path.name
                        shutil.copy2(cfg_path, dest)
                        self.logger.info(f"Included {cfg_path} in snapshot.")
                        files_added += 1
                    else:
                        self.logger.warning(f"Configuration file {cfg_path} not found; skipping.")
                if files_added > 0:
                    with tarfile.open(snapshot_file, "w:gz") as tar:
                        tar.add(temp_dir, arcname=".")
                    self.logger.info(f"Configuration snapshot saved as {snapshot_file}.")
                    return str(snapshot_file)
                else:
                    self.logger.warning("No configuration files were found to include in the snapshot.")
                    return None
        except Exception as e:
            self.logger.warning(f"Failed to create configuration snapshot: {e}")
            return None

    # ----------------------------
    # System Update & Package Installation
    # ----------------------------
    def update_system(self) -> bool:
        """
        Update package repositories and upgrade installed packages.
        """
        self.print_section("System Update & Upgrade")
        try:
            self.logger.info("Updating package repositories...")
            self.run_command(["apt", "update", "-qq"])
            self.logger.info("Upgrading system packages...")
            self.run_command(["apt", "upgrade", "-y"])
            self.logger.info("System update and upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System update failed: {e}")
            return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
        """
        Install specified packages if they are not already installed.
        """
        self.print_section("Essential Package Installation")
        self.logger.info("Checking for required packages...")
        missing_packages = []
        success_packages = []
        failed_packages = []
        for pkg in self.config.PACKAGES:
            try:
                subprocess.run(["dpkg", "-s", pkg],
                               check=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                self.logger.info(f"Package already installed: {pkg}")
                success_packages.append(pkg)
            except subprocess.CalledProcessError:
                missing_packages.append(pkg)
        if missing_packages:
            self.logger.info(f"Installing missing packages: {' '.join(missing_packages)}")
            try:
                self.run_command(["apt", "install", "-y"] + missing_packages)
                self.logger.info("All missing packages installed successfully.")
                success_packages.extend(missing_packages)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install one or more packages: {e}")
                for pkg in missing_packages:
                    try:
                        subprocess.run(["dpkg", "-s", pkg],
                                       check=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                        success_packages.append(pkg)
                    except subprocess.CalledProcessError:
                        failed_packages.append(pkg)
        else:
            self.logger.info("All required packages are already installed.")
        return success_packages, failed_packages

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        """
        Configure the system timezone.
        """
        self.print_section("Timezone Configuration")
        self.logger.info(f"Setting timezone to {timezone}...")
        timezone_path = Path(f"/usr/share/zoneinfo/{timezone}")
        localtime_path = Path("/etc/localtime")
        if not timezone_path.is_file():
            self.logger.warning(f"Timezone file for {timezone} not found.")
            return False
        try:
            if localtime_path.exists() or localtime_path.is_symlink():
                localtime_path.unlink()
            localtime_path.symlink_to(timezone_path)
            self.logger.info(f"Timezone set to {timezone}.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to set timezone: {e}")
            return False

    # ----------------------------
    # Repository and Shell Setup
    # ----------------------------
    def setup_repos(self) -> List[str]:
        """
        Set up GitHub repositories in the user's home directory.
        """
        self.print_section("GitHub Repositories Setup")
        self.logger.info(f"Setting up GitHub repositories for user '{self.config.USERNAME}'...")
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)
        successful_repos = []
        for repo in self.config.GITHUB_REPOS:
            repo_dir = gh_dir / repo
            if (repo_dir / ".git").is_dir():
                self.logger.info(f"Repository '{repo}' already exists. Pulling latest changes...")
                try:
                    self.run_command(["git", "-C", str(repo_dir), "pull"])
                    successful_repos.append(repo)
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to update repository '{repo}'.")
            else:
                self.logger.info(f"Cloning repository '{repo}' into '{repo_dir}'...")
                try:
                    self.run_command(["git", "clone", f"https://github.com/dunamismax/{repo}.git", str(repo_dir)])
                    self.logger.info(f"Repository '{repo}' cloned successfully.")
                    successful_repos.append(repo)
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to clone repository '{repo}'.")
        try:
            self.run_command(["chown", "-R", f"{self.config.USERNAME}:{self.config.USERNAME}", str(gh_dir)])
            self.logger.info(f"Ownership of '{gh_dir}' set to '{self.config.USERNAME}'.")
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set ownership of '{gh_dir}'.")
        return successful_repos

    def copy_shell_configs(self) -> Dict[str, bool]:
        """
        Update shell configuration files from a repository source.
        """
        self.print_section("Shell Configuration Update")
        source_dir = self.config.USER_HOME / "github/bash/linux/ubuntu/dotfiles"
        destination_dirs = [self.config.USER_HOME, Path("/root")]
        results = {}
        for file_name in [".bashrc", ".profile"]:
            src = source_dir / file_name
            if not src.is_file():
                self.logger.warning(f"Source file {src} not found; skipping.")
                continue
            for dest_dir in destination_dirs:
                dest = dest_dir / file_name
                results[str(dest)] = False
                if dest.is_file() and filecmp.cmp(src, dest):
                    self.logger.info(f"File {dest} is already up-to-date.")
                    results[str(dest)] = True
                    continue
                try:
                    shutil.copy2(src, dest)
                    if dest_dir == self.config.USER_HOME:
                        self.run_command(["chown", f"{self.config.USERNAME}:{self.config.USERNAME}", str(dest)])
                    else:
                        self.run_command(["chown", "root:root", str(dest)])
                    self.logger.info(f"Copied {src} to {dest}.")
                    results[str(dest)] = True
                except Exception as e:
                    self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
        return results

    def set_bash_shell(self) -> bool:
        """
        Ensure that /bin/bash is set as the default shell for the specified user.
        """
        self.print_section("Default Shell Configuration")
        if not self.command_exists("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                self.run_command(["apt", "install", "-y", "bash"])
            except subprocess.CalledProcessError:
                self.logger.warning("Bash installation failed.")
                return False
        try:
            shells_path = Path("/etc/shells")
            if shells_path.exists():
                with open(shells_path, "r") as f:
                    shells_content = f.read()
                if "/bin/bash" not in shells_content:
                    with open(shells_path, "a") as f:
                        f.write("/bin/bash\n")
                    self.logger.info("Added /bin/bash to /etc/shells.")
            else:
                with open(shells_path, "w") as f:
                    f.write("/bin/bash\n")
                self.logger.info("Created /etc/shells with /bin/bash.")
        except Exception as e:
            self.logger.warning(f"Failed to update /etc/shells: {e}")
            return False
        try:
            self.run_command(["chsh", "-s", "/bin/bash", self.config.USERNAME])
            self.logger.info(f"Default shell for {self.config.USERNAME} set to /bin/bash.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set default shell for {self.config.USERNAME}.")
            return False

    def copy_config_folders(self) -> Dict[str, bool]:
        """
        Copy all subdirectories from dotfiles to the .config directory.
        """
        self.print_section("Copying Config Folders")
        source_dir = self.config.CONFIG_SRC_DIR
        dest_dir = self.config.CONFIG_DEST_DIR
        dest_dir.mkdir(exist_ok=True)
        self.logger.info(f"Destination directory ensured: {dest_dir}")
        results = {}
        try:
            for item in source_dir.iterdir():
                if not item.is_dir():
                    continue
                dest_path = dest_dir / item.name
                results[item.name] = False
                try:
                    shutil.copytree(item, dest_path, dirs_exist_ok=True)
                    self.logger.info(f"Copied '{item}' to '{dest_path}'.")
                    self.run_command(["chown", "-R", f"{self.config.USERNAME}:{self.config.USERNAME}", str(dest_path)])
                    results[item.name] = True
                except Exception as e:
                    self.logger.warning(f"Failed to copy '{item}' to '{dest_path}': {e}")
        except Exception as e:
            self.logger.warning(f"Error scanning source directory '{source_dir}': {e}")
        return results

    # ----------------------------
    # SSH and Sudo Security Configuration
    # ----------------------------
    def configure_ssh(self) -> bool:
        """
        Configure and secure the OpenSSH server.
        """
        self.print_section("SSH Configuration")
        self.logger.info("Configuring OpenSSH Server...")
        try:
            subprocess.run(["dpkg", "-s", "openssh-server"],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            self.logger.info("openssh-server not installed. Installing...")
            try:
                self.run_command(["apt", "install", "-y", "openssh-server"])
                self.logger.info("OpenSSH Server installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install OpenSSH Server.")
                return False
        try:
            self.run_command(["systemctl", "enable", "--now", "ssh"])
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable/start SSH service.")
            return False
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config}")
            return False
        self.backup_file(sshd_config)
        try:
            with open(sshd_config, "r") as f:
                lines = f.readlines()
            for key, value in self.config.SSH_SETTINGS.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {value}\n"
                        found = True
                        break
                if not found:
                    lines.append(f"{key} {value}\n")
            with open(sshd_config, "w") as f:
                f.writelines(lines)
            self.run_command(["systemctl", "restart", "ssh"])
            self.logger.info("SSH configuration updated and service restarted.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """
        Ensure the specified user has sudo privileges.
        """
        self.print_section("Sudo Configuration")
        self.logger.info(f"Ensuring user {self.config.USERNAME} has sudo privileges...")
        try:
            result = self.run_command(["id", "-nG", self.config.USERNAME], capture_output=True, text=True)
            if "sudo" in result.stdout.split():
                self.logger.info(f"User {self.config.USERNAME} is already in the sudo group.")
                return True
            self.run_command(["usermod", "-aG", "sudo", self.config.USERNAME])
            self.logger.info(f"User {self.config.USERNAME} added to sudo group.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to manage sudo privileges for {self.config.USERNAME}: {e}")
            return False

    def configure_firewall(self, ports: Optional[List[str]] = None) -> bool:
        """
        Configure the UFW firewall with secure defaults and specified ports.
        """
        self.print_section("Firewall Configuration")
        self.logger.info("Configuring firewall using UFW...")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            self.logger.error("UFW command not found. Please install UFW.")
            return False
        try:
            self.run_command([ufw_cmd, "default", "deny", "incoming"])
            self.logger.info("Set default deny for incoming traffic.")
            self.run_command([ufw_cmd, "default", "allow", "outgoing"])
            self.logger.info("Set default allow for outgoing traffic.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to set default UFW policies: {e}")
            return False
        for port in ports:
            try:
                self.run_command([ufw_cmd, "allow", f"{port}/tcp"])
                self.logger.info(f"Allowed TCP port {port}.")
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to allow TCP port {port}: {e}")
        try:
            result = self.run_command([ufw_cmd, "status"], capture_output=True, text=True)
            if "inactive" in result.stdout.lower():
                self.run_command([ufw_cmd, "--force", "enable"])
                self.logger.info("UFW firewall has been enabled.")
            else:
                self.logger.info("UFW firewall is already active.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to manage UFW status: {e}")
            return False
        try:
            self.run_command(["systemctl", "enable", "ufw"])
            self.run_command(["systemctl", "start", "ufw"])
            self.logger.info("UFW service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to manage UFW service: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """
        Configure and enable fail2ban with a secure basic default configuration.
        """
        self.print_section("Fail2ban Configuration")
        jail_local = Path("/etc/fail2ban/jail.local")
        config_content = """[DEFAULT]
# Ban IPs for 10 minutes after reaching max retries
bantime  = 600
# Look for failed attempts within 10 minutes
findtime = 600
# Ban an IP after 3 failed login attempts
maxretry = 3
# Use systemd for reading logs on modern systems
backend  = systemd
# Resolve DNS only if necessary; warn if issues occur
usedns   = warn

[sshd]
enabled  = true
port     = ssh
logpath  = /var/log/auth.log
maxretry = 3
"""
        if jail_local.is_file():
            self.backup_file(jail_local)
        try:
            with open(jail_local, "w") as f:
                f.write(config_content)
            self.logger.info("Fail2ban configuration written to /etc/fail2ban/jail.local.")
        except Exception as e:
            self.logger.warning(f"Failed to write Fail2ban configuration: {e}")
            return False
        try:
            self.run_command(["systemctl", "enable", "fail2ban"])
            self.run_command(["systemctl", "restart", "fail2ban"])
            self.logger.info("Fail2ban service enabled and restarted successfully.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to enable or restart the Fail2ban service.")
            return False

    # ----------------------------
    # Service Installation and Configuration
    # ----------------------------
    def docker_config(self) -> bool:
        """
        Install and configure Docker and Docker Compose.
        """
        self.print_section("Docker Configuration")
        self.logger.info("Installing Docker...")
        if self.command_exists("docker"):
            self.logger.info("Docker is already installed.")
        else:
            try:
                self.run_command(["apt", "install", "-y", "docker.io"])
                self.logger.info("Docker installed successfully.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install Docker.")
                return False
        try:
            result = self.run_command(["id", "-nG", self.config.USERNAME], capture_output=True, text=True)
            if "docker" not in result.stdout.split():
                self.run_command(["usermod", "-aG", "docker", self.config.USERNAME])
                self.logger.info(f"Added user '{self.config.USERNAME}' to docker group.")
            else:
                self.logger.info(f"User '{self.config.USERNAME}' is already in docker group.")
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to add {self.config.USERNAME} to docker group.")
        daemon_json_path = Path("/etc/docker/daemon.json")
        daemon_json_dir = daemon_json_path.parent
        try:
            daemon_json_dir.mkdir(exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create {daemon_json_dir}: {e}")
            return False
        desired_daemon_json = {
            "log-driver": "json-file",
            "log-opts": {
                "max-size": "10m",
                "max-file": "3"
            },
            "exec-opts": ["native.cgroupdriver=systemd"]
        }
        write_config = True
        if daemon_json_path.is_file():
            try:
                with open(daemon_json_path, "r") as f:
                    existing_config = json.load(f)
                if existing_config == desired_daemon_json:
                    self.logger.info("Docker daemon configuration is already up-to-date.")
                    write_config = False
                else:
                    self.backup_file(daemon_json_path)
            except Exception as e:
                self.logger.warning(f"Failed to read {daemon_json_path}: {e}")
                self.backup_file(daemon_json_path)
        if write_config:
            try:
                with open(daemon_json_path, "w") as f:
                    json.dump(desired_daemon_json, f, indent=2)
                self.logger.info("Docker daemon configuration updated/created.")
            except Exception as e:
                self.logger.warning(f"Failed to write {daemon_json_path}: {e}")
        try:
            self.run_command(["systemctl", "enable", "docker"])
            self.run_command(["systemctl", "restart", "docker"])
            self.logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable or restart Docker service.")
            return False
        if not self.command_exists("docker-compose"):
            try:
                compose_path = Path("/usr/local/bin/docker-compose")
                self.download_file(self.config.DOCKER_COMPOSE_URL, compose_path)
                compose_path.chmod(0o755)
                self.logger.info("Docker Compose installed successfully.")
            except Exception as e:
                self.logger.error(f"Failed to install Docker Compose: {e}")
                return False
        else:
            self.logger.info("Docker Compose is already installed.")
        return True

    def install_plex(self) -> bool:
        """
        Install and configure Plex Media Server.
        """
        self.print_section("Plex Media Server Installation")
        self.logger.info("Installing Plex Media Server...")
        if not self.command_exists("curl"):
            self.logger.error("curl is required but not installed.")
            return False
        try:
            subprocess.run(["dpkg", "-s", "plexmediaserver"],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            self.logger.info("Plex Media Server is already installed; skipping download and installation.")
            return True
        except subprocess.CalledProcessError:
            pass
        temp_deb = Path("/tmp/plexmediaserver.deb")
        try:
            self.download_file(self.config.PLEX_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg encountered issues. Attempting to fix missing dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install dependencies for Plex.")
                return False
        plex_conf = Path("/etc/default/plexmediaserver")
        if plex_conf.is_file():
            try:
                with open(plex_conf, "r") as f:
                    conf = f.read()
                if f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}" in conf:
                    self.logger.info(f"Plex user is already configured as {self.config.USERNAME}.")
                else:
                    new_conf = []
                    for line in conf.splitlines():
                        if line.startswith("PLEX_MEDIA_SERVER_USER="):
                            new_conf.append(f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}")
                        else:
                            new_conf.append(line)
                    with open(plex_conf, "w") as f:
                        f.write("\n".join(new_conf) + "\n")
                    self.logger.info(f"Configured Plex to run as {self.config.USERNAME}.")
            except Exception as e:
                self.logger.warning(f"Failed to set Plex user in {plex_conf}: {e}")
        else:
            self.logger.warning(f"{plex_conf} not found; skipping user configuration.")
        try:
            self.run_command(["systemctl", "enable", "plexmediaserver"])
            self.logger.info("Plex service enabled.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to enable Plex service.")
        try:
            temp_deb.unlink()
        except Exception:
            pass
        self.logger.info("Plex Media Server installed successfully.")
        return True

    def install_fastfetch(self) -> bool:
        """
        Install Fastfetch, a system information tool.
        """
        self.print_section("Fastfetch Installation")
        try:
            subprocess.run(["dpkg", "-s", "fastfetch"],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            self.logger.info("Fastfetch is already installed; skipping.")
            return True
        except subprocess.CalledProcessError:
            pass
        temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")
        try:
            self.download_file(self.config.FASTFETCH_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("fastfetch installation issues; fixing dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix dependencies for fastfetch.")
                return False
        try:
            temp_deb.unlink()
        except Exception:
            pass
        self.logger.info("Fastfetch installed successfully.")
        return True

    def deploy_user_scripts(self) -> bool:
        """
        Deploy user scripts from the repository to the user's bin directory.
        """
        self.print_section("Deploying User Scripts")
        script_source = self.config.USER_HOME / "github/bash/linux/ubuntu/_scripts"
        script_target = self.config.USER_HOME / "bin"
        if not script_source.is_dir():
            self.logger.error(f"Source directory '{script_source}' does not exist.")
            return False
        script_target.mkdir(exist_ok=True)
        try:
            self.run_command(["rsync", "-ah", "--delete", f"{script_source}/", f"{script_target}/"])
            self.run_command(["find", str(script_target), "-type", "f", "-exec", "chmod", "755", "{}", ";"])
            self.run_command(["chown", "-R", f"{self.config.USERNAME}:{self.config.USERNAME}", str(script_target)])
            self.logger.info("User scripts deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Script deployment failed: {e}")
            return False

    # ----------------------------
    # Maintenance & Monitoring Tasks
    # ----------------------------
    def configure_periodic(self) -> bool:
        """
        Set up a daily cron job for system maintenance.
        """
        self.print_section("Periodic Maintenance Setup")
        cron_file = Path("/etc/cron.daily/ubuntu_maintenance")
        marker = "# Ubuntu maintenance script"
        if cron_file.is_file():
            with open(cron_file, "r") as f:
                if marker in f.read():
                    self.logger.info("Daily maintenance cron job already configured.")
                    return True
            self.backup_file(cron_file)
        content = """#!/bin/sh
# Ubuntu maintenance script
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
"""
        try:
            with open(cron_file, "w") as f:
                f.write(content)
            cron_file.chmod(0o755)
            self.logger.info(f"Daily maintenance script created at {cron_file}.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> Optional[str]:
        """
        Backup critical system configuration files.
        """
        self.print_section("Configuration Backups")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path(f"/var/backups/ubuntu_config_{timestamp}")
        try:
            backup_dir.mkdir(exist_ok=True)
            files_backed_up = 0
            for file_path in ["/etc/ssh/sshd_config", "/etc/ufw/user.rules", "/etc/ntp.conf"]:
                file_path = Path(file_path)
                if file_path.is_file():
                    dest_path = backup_dir / file_path.name
                    try:
                        shutil.copy2(file_path, dest_path)
                        self.logger.info(f"Backed up {file_path}")
                        files_backed_up += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to backup {file_path}: {e}")
                else:
                    self.logger.warning(f"File {file_path} not found; skipping.")
            if files_backed_up > 0:
                self.logger.info(f"Configuration files backed up to {backup_dir}")
                return str(backup_dir)
            else:
                self.logger.warning("No configuration files were backed up.")
                backup_dir.rmdir()
                return None
        except Exception as e:
            self.logger.warning(f"Failed to create backup directory: {e}")
            return None

    def rotate_logs(self, log_file: Optional[str] = None) -> bool:
        """
        Rotate the log file by compressing it and truncating the original.
        """
        self.print_section("Log Rotation")
        if log_file is None:
            log_file = self.config.LOG_FILE
        log_path = Path(log_file)
        if not log_path.is_file():
            self.logger.warning(f"Log file {log_path} does not exist.")
            return False
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rotated_file = f"{log_path}.{timestamp}.gz"
            with open(log_path, "rb") as f_in:
                with gzip.open(rotated_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            with open(log_path, "w"):
                pass
            self.logger.info(f"Log rotated to {rotated_file}.")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def system_health_check(self) -> Dict[str, str]:
        """
        Perform basic system health checks and log the results.
        """
        self.print_section("System Health Check")
        health_info = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            self.logger.info(f"Uptime: {uptime}")
            health_info["uptime"] = uptime
        except Exception as e:
            self.logger.warning(f"Failed to get uptime: {e}")
        try:
            df_output = subprocess.check_output(["df", "-h", "/"], text=True).strip()
            for line in df_output.splitlines():
                self.logger.info(line)
            health_info["disk_usage"] = df_output
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_output = subprocess.check_output(["free", "-h"], text=True).strip()
            for line in free_output.splitlines():
                self.logger.info(line)
            health_info["memory_usage"] = free_output
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
        return health_info

    def verify_firewall_rules(self, ports: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Verify that specific ports are accessible as expected.
        """
        self.print_section("Firewall Rules Verification")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
        results = {}
        for port in ports:
            try:
                subprocess.run(["nc", "-z", "-w3", "127.0.0.1", port],
                               check=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                self.logger.info(f"Port {port} is accessible.")
                results[port] = True
            except subprocess.CalledProcessError:
                self.logger.warning(f"Port {port} is not accessible. Check ufw rules.")
                results[port] = False
        return results

    # ----------------------------
    # Certificates & Performance Tuning
    # ----------------------------
    def update_ssl_certificates(self) -> bool:
        """
        Update SSL certificates using certbot.
        """
        self.print_section("SSL Certificates Update")
        if not self.command_exists("certbot"):
            try:
                self.run_command(["apt", "install", "-y", "certbot"])
                self.logger.info("certbot installed successfully.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to install certbot.")
                return False
        try:
            self.run_command(["certbot", "renew"])
            self.logger.info("SSL certificates updated successfully.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to update SSL certificates.")
            return False

    def tune_system(self) -> bool:
        """
        Apply performance tuning settings to the system.
        """
        self.print_section("Performance Tuning")
        sysctl_conf = Path("/etc/sysctl.conf")
        marker = "# Performance tuning settings for Ubuntu"
        if sysctl_conf.is_file():
            self.backup_file(sysctl_conf)
        try:
            current_content = sysctl_conf.read_text() if sysctl_conf.is_file() else ""
            if marker not in current_content:
                tuning = f"""
{marker}
net.core.somaxconn=128
net.ipv4.tcp_rmem=4096 87380 6291456
net.ipv4.tcp_wmem=4096 16384 4194304
"""
                with open(sysctl_conf, "a") as f:
                    f.write(tuning)
                for setting in [
                    "net.core.somaxconn=128",
                    "net.ipv4.tcp_rmem=4096 87380 6291456",
                    "net.ipv4.tcp_wmem=4096 16384 4194304"
                ]:
                    self.run_command(["sysctl", "-w", setting])
                self.logger.info("Performance tuning applied.")
            else:
                self.logger.info(f"Performance tuning settings already exist in {sysctl_conf}.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply performance tuning: {e}")
            return False

    # ----------------------------
    # Permissions & Advanced Storage Setup
    # ----------------------------
    def home_permissions(self) -> bool:
        """
        Ensure correct ownership and permissions for the user's home directory.
        """
        self.print_section("Home Directory Permissions")
        home_dir = self.config.USER_HOME
        try:
            self.run_command(["chown", "-R", f"{self.config.USERNAME}:{self.config.USERNAME}", str(home_dir)])
            self.logger.info(f"Ownership of {home_dir} set to {self.config.USERNAME}.")
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to change ownership of {home_dir}.")
            return False
        try:
            self.run_command(["find", str(home_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", ";"])
            self.logger.info(f"Setgid bit set on directories in {home_dir}.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to set setgid bit on some directories.")
        if self.command_exists("setfacl"):
            try:
                self.run_command(["setfacl", "-R", "-d", "-m", f"u:{self.config.USERNAME}:rwx", str(home_dir)])
                self.logger.info(f"Default ACLs applied on {home_dir}.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to apply default ACLs.")
        else:
            self.logger.warning("setfacl not found; skipping default ACL configuration.")
        return True

    def install_configure_zfs(self) -> bool:
        """
        Install and configure ZFS for external pool.
        """
        self.print_section("ZFS Installation and Configuration")
        pool_name = self.config.ZFS_POOL_NAME
        mount_point = self.config.ZFS_MOUNT_POINT
        mount_point = Path(mount_point)
        cache_file = Path("/etc/zfs/zpool.cache")
        try:
            self.run_command(["apt", "update"])
            self.run_command(["apt", "install", "-y", "dpkg-dev", "linux-headers-generic", "linux-image-generic"])
            self.run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])
            self.logger.info("Prerequisites and ZFS packages installed successfully.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install prerequisites or ZFS packages: {e}")
            return False
        for service in ["zfs-import-cache.service", "zfs-mount.service"]:
            try:
                self.run_command(["systemctl", "enable", service])
                self.logger.info(f"Enabled {service}.")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Could not enable {service}.")
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created mount point directory: {mount_point}")
        except Exception as e:
            self.logger.warning(f"Failed to create mount point directory {mount_point}: {e}")
        pool_imported = False
        try:
            subprocess.run(["zpool", "list", pool_name],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            self.logger.info(f"ZFS pool '{pool_name}' is already imported.")
            pool_imported = True
        except subprocess.CalledProcessError:
            try:
                self.run_command(["zpool", "import", "-f", pool_name])
                self.logger.info(f"Imported ZFS pool '{pool_name}'.")
                pool_imported = True
            except subprocess.CalledProcessError:
                self.logger.warning(f"ZFS pool '{pool_name}' not found or failed to import.")
        if not pool_imported:
            self.logger.warning(f"ZFS pool '{pool_name}' could not be imported. Skipping further configuration.")
            return False
        try:
            self.run_command(["zfs", "set", f"mountpoint={mount_point}", pool_name])
            self.logger.info(f"Set mountpoint for pool '{pool_name}' to '{mount_point}'.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to set mountpoint for ZFS pool '{pool_name}': {e}")
        try:
            self.run_command(["zpool", "set", f"cachefile={cache_file}", pool_name])
            self.logger.info(f"Updated cachefile for pool '{pool_name}' to '{cache_file}'.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to update cachefile for ZFS pool '{pool_name}': {e}")
        try:
            self.run_command(["zfs", "mount", "-a"])
            self.logger.info("Mounted all ZFS datasets.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to mount ZFS datasets: {e}")
        try:
            mounts = subprocess.check_output(["zfs", "list", "-o", "name,mountpoint", "-H"], text=True)
            if any(str(mount_point) in line for line in mounts.splitlines()):
                self.logger.info(f"ZFS pool '{pool_name}' is successfully mounted at '{mount_point}'.")
                return True
            else:
                self.logger.warning(f"ZFS pool '{pool_name}' is not mounted at '{mount_point}'. Please check manually.")
                return False
        except Exception as e:
            self.logger.warning(f"Error verifying mount status for ZFS pool '{pool_name}': {e}")
            return False

    # ----------------------------
    # Additional Applications & Tools
    # ----------------------------
    def install_brave_browser(self) -> bool:
        """
        Install the Brave browser on Ubuntu.
        """
        self.print_section("Brave Browser Installation")
        self.logger.info("Installing Brave browser...")
        try:
            self.run_command(["sh", "-c", "curl -fsS https://dl.brave.com/install.sh | sh"])
            self.logger.info("Brave browser installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Brave browser: {e}")
            return False

    def install_flatpak_and_apps(self) -> Tuple[List[str], List[str]]:
        """
        Install Flatpak, add the Flathub repository, and install Flatpak applications.
        """
        self.print_section("Flatpak Installation and Setup")
        apps = self.config.FLATPAK_APPS
        self.logger.info("Installing Flatpak...")
        try:
            self.run_command(["apt", "install", "-y", "flatpak"])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Flatpak: {e}")
            return [], apps
        self.logger.info("Installing GNOME Software Flatpak plugin...")
        try:
            self.run_command(["apt", "install", "-y", "gnome-software-plugin-flatpak"])
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install GNOME Software Flatpak plugin: {e}")
        self.logger.info("Adding Flathub repository...")
        try:
            self.run_command(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to add Flathub repository: {e}")
            return [], apps
        successful_apps = []
        failed_apps = []
        self.logger.info("Installing Flatpak applications from Flathub...")
        for app in apps:
            self.logger.info(f"Installing {app}...")
            try:
                self.run_command(["flatpak", "install", "--assumeyes", "flathub", app])
                self.logger.info(f"{app} installed successfully.")
                successful_apps.append(app)
            except subprocess.CalledProcessError:
                self.logger.warning(f"Failed to install {app}.")
                failed_apps.append(app)
        return successful_apps, failed_apps

    def install_configure_caddy(self) -> bool:
        """
        Install and configure the Caddy web server.
        """
        self.print_section("Caddy Installation and Configuration")
        self.logger.info("Installing Caddy web server...")
        caddy_deb_url = "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb"
        temp_deb = Path("/tmp/caddy_2.9.1_linux_amd64.deb")
        try:
            self.download_file(caddy_deb_url, temp_deb)
        except Exception as e:
            self.logger.error(f"Failed to download Caddy package: {e}")
            return False
        try:
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("Dependency issues encountered during Caddy installation. Attempting to fix...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to resolve dependencies for Caddy: {e}")
                return False
        self.logger.info("Caddy installed successfully.")
        try:
            temp_deb.unlink()
            self.logger.info("Removed temporary Caddy package file.")
        except Exception as e:
            self.logger.warning(f"Failed to remove temporary file {temp_deb}: {e}")
        source_caddyfile = self.config.USER_HOME / "github/bash/linux/ubuntu/dotfiles/Caddyfile"
        dest_caddyfile = Path("/etc/caddy/Caddyfile")
        if not source_caddyfile.is_file():
            self.logger.warning(f"Source Caddyfile not found at {source_caddyfile}. Skipping Caddyfile configuration.")
        else:
            if dest_caddyfile.exists():
                self.backup_file(dest_caddyfile)
            try:
                shutil.copy2(source_caddyfile, dest_caddyfile)
                self.logger.info(f"Copied {source_caddyfile} to {dest_caddyfile}.")
            except Exception as e:
                self.logger.warning(f"Failed to copy Caddyfile: {e}")
        log_dir = Path("/var/log/caddy")
        log_files = [
            log_dir / "caddy.log",
            log_dir / "dunamismax_access.log",
            log_dir / "messenger_access.log",
            log_dir / "ai_agents_access.log",
            log_dir / "file_converter_access.log",
            log_dir / "notes_access.log",
        ]
        try:
            log_dir.mkdir(mode=0o755, exist_ok=True)
            self.logger.info(f"Log directory {log_dir} is ready.")
            for log_file in log_files:
                with open(log_file, "a"):
                    os.utime(log_file, None)
                log_file.chmod(0o644)
                self.logger.info(f"Prepared log file: {log_file}")
        except Exception as e:
            self.logger.warning(f"Failed to prepare log files: {e}")
        try:
            self.run_command(["systemctl", "enable", "caddy"])
            self.logger.info("Caddy service enabled.")
            self.run_command(["systemctl", "restart", "caddy"])
            self.logger.info("Caddy service started successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to enable or start Caddy service: {e}")
            return False

    def create_system_zfs_snapshot(self) -> Optional[str]:
        """
        Create a ZFS snapshot of the system's root dataset.
        """
        self.print_section("System ZFS Snapshot Backup")
        system_dataset = "rpool/ROOT/ubuntu"
        try:
            self.run_command(["zfs", "list", system_dataset], capture_output=True)
            self.logger.info(f"System dataset '{system_dataset}' found.")
        except subprocess.CalledProcessError:
            system_dataset = "rpool"
            self.logger.warning("Dataset 'rpool/ROOT/ubuntu' not found. Using 'rpool' for snapshot.")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        snapshot_name = f"{system_dataset}@backup_{timestamp}"
        try:
            self.run_command(["zfs", "snapshot", snapshot_name])
            self.logger.info(f"Created system ZFS snapshot: {snapshot_name}")
            return snapshot_name
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to create system ZFS snapshot for '{system_dataset}': {e}")
            return None

    def configure_unattended_upgrades(self) -> bool:
        """
        Install and configure unattended-upgrades for automatic security updates.
        """
        self.print_section("Unattended Upgrades Configuration")
        try:
            self.run_command(["apt", "install", "-y", "unattended-upgrades"])
            self.logger.info("Unattended-upgrades installed. Please review /etc/apt/apt.conf.d/50unattended-upgrades for customization.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install unattended-upgrades: {e}")
            return False

    def cleanup_system(self) -> bool:
        """
        Clean up temporary files, remove unused packages, and clear apt cache.
        """
        self.print_section("System Cleanup")
        try:
            self.run_command(["apt", "autoremove", "-y"])
            self.logger.info("Unused packages removed.")
            self.run_command(["apt", "clean"])
            self.logger.info("Apt cache cleared.")
            self.logger.info("System cleanup completed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"System cleanup failed: {e}")
            return False

    def configure_apparmor(self) -> bool:
        """
        Install and enable AppArmor along with its utilities.
        """
        self.print_section("AppArmor Configuration")
        try:
            self.run_command(["apt", "install", "-y", "apparmor", "apparmor-utils"])
            self.run_command(["systemctl", "enable", "apparmor"])
            self.run_command(["systemctl", "start", "apparmor"])
            self.logger.info("AppArmor installed and started successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install or start AppArmor: {e}")
            return False

    def install_configure_vscode_stable(self) -> bool:
        """
        Install Visual Studio Code - Stable and configure it to run natively on Wayland.
        """
        self.print_section("Visual Studio Code - Stable Installation and Configuration")
        vscode_url = (
            "https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
            "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
        )
        deb_path = Path("/tmp/code.deb")
        try:
            self.logger.info("Downloading VS Code Stable...")
            self.download_file(vscode_url, deb_path)
        except Exception as e:
            self.logger.error(f"Failed to download VS Code Stable: {e}")
            return False
        try:
            self.logger.info("Installing VS Code Stable...")
            self.run_command(["dpkg", "-i", str(deb_path)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg installation encountered issues. Attempting to fix dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix dependencies for VS Code Stable: {e}")
                return False
        try:
            deb_path.unlink()
        except Exception:
            pass
        desktop_file_path = Path("/usr/share/applications/code.desktop")
        desktop_content = """[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
GenericName=Text Editor
Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=TextEditor;Development;IDE;
MimeType=application/x-code-workspace;
Actions=new-empty-window;
Keywords=vscode;

[Desktop Action new-empty-window]
Name=New Empty Window
Name[de]=Neues leeres Fenster
Name[es]=Nueva ventana vacía
Name[fr]=Nouvelle fenêtre vide
Name[it]=Nuova finestra vuota
Name[ja]=新しい空のウィンドウ
Name[ko]=새 빈 창
Name[ru]=Новое пустое окно
Name[zh_CN]=新建空窗口
Name[zh_TW]=開新空視窗
Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
"""
        try:
            with open(desktop_file_path, "w") as f:
                f.write(desktop_content)
            self.logger.info(f"Updated system-wide desktop file: {desktop_file_path}")
        except Exception as e:
            self.logger.warning(f"Failed to update system-wide desktop file: {e}")
        local_app_dir = Path.home() / ".local/share/applications"
        local_desktop_file = local_app_dir / "code.desktop"
        try:
            local_app_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(desktop_file_path, local_desktop_file)
            self.logger.info(f"Copied desktop file to local directory: {local_desktop_file}")
            with open(local_desktop_file, "r") as f:
                content = f.read()
            updated_content = content.replace("StartupWMClass=Code", "StartupWMClass=code")
            with open(local_desktop_file, "w") as f:
                f.write(updated_content)
            self.logger.info(f"Updated local desktop file for Wayland compatibility: {local_desktop_file}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to update local desktop file: {e}")
            return False

    def install_nala(self) -> bool:
        """
        Install Nala (an apt front-end) if it's not already installed.
        """
        self.print_section("Nala Installation")
        if self.command_exists("nala"):
            self.logger.info("Nala is already installed.")
            return True
        try:
            self.logger.info("Nala is not installed. Installing Nala...")
            self.run_command(["apt", "update"])
            self.run_command(["apt", "install", "-y", "nala"])
            self.logger.info("Nala installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Nala: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        """
        Install and enable Tailscale on the server.
        """
        self.print_section("Tailscale Installation and Enablement")
        if self.command_exists("tailscale"):
            self.logger.info("Tailscale is already installed; skipping installation.")
        else:
            self.logger.info("Installing Tailscale...")
            try:
                self.run_command(["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"])
                self.logger.info("Tailscale installed successfully.")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Tailscale: {e}")
                return False
        try:
            self.run_command(["systemctl", "enable", "--now", "tailscaled"])
            self.logger.info("Tailscale service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to enable/start Tailscale service: {e}")
            return False

    def prompt_reboot(self) -> bool:
        """
        Prompt the user for a system reboot to apply changes.
        """
        self.print_section("Reboot Prompt")
        answer = input("Would you like to reboot now? [y/N]: ").strip().lower()
        if answer == "y":
            self.logger.info("Rebooting system now...")
            try:
                self.run_command(["shutdown", "-r", "now"])
                return True
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to reboot system: {e}")
                return False
        else:
            self.logger.info("Reboot canceled. Please reboot later for all changes to take effect.")
            return False

    # ----------------------------
    # Main Execution Flow
    # ----------------------------
    def run(self) -> int:
        """
        Main function executing the entire setup process in logical phases.
        """
        success_count = 0
        total_steps = 35  # Total number of major steps
        try:
            # Phase 1: Pre-flight Checks & Backups
            self.check_root()
            self.check_network()
            self.save_config_snapshot()
            self.create_system_zfs_snapshot()
            # Phase 2: System Update & Basic Configuration
            if self.update_system():
                success_count += 1
            installed_pkgs, failed_pkgs = self.install_packages()
            if len(failed_pkgs) == 0:
                success_count += 1
            elif len(failed_pkgs) <= len(self.config.PACKAGES) * 0.1:
                self.logger.warning(f"Some packages failed to install: {', '.join(failed_pkgs)}")
                success_count += 0.5
            if self.configure_timezone():
                success_count += 1
            # Phase 3: Repository & Shell Setup
            if self.setup_repos():
                success_count += 1
            if self.copy_shell_configs():
                success_count += 1
            if self.copy_config_folders():
                success_count += 1
            if self.set_bash_shell():
                success_count += 1
            # Phase 4: Security Hardening
            if self.configure_ssh():
                success_count += 1
            if self.setup_sudoers():
                success_count += 1
            if self.configure_firewall(self.config.FIREWALL_PORTS):
                success_count += 1
            if self.configure_fail2ban():
                success_count += 1
            # Phase 5: Essential Service Installation
            if self.docker_config():
                success_count += 1
            if self.install_plex():
                success_count += 1
            if self.install_fastfetch():
                success_count += 1
            # Phase 6: User Customization & Script Deployment
            if self.deploy_user_scripts():
                success_count += 1
            # Phase 7: Maintenance & Monitoring Tasks
            if self.configure_periodic():
                success_count += 1
            if self.backup_configs():
                success_count += 1
            if self.rotate_logs(self.config.LOG_FILE):
                success_count += 1
            if self.system_health_check():
                success_count += 1
            if self.verify_firewall_rules(self.config.FIREWALL_PORTS):
                success_count += 1
            # Phase 8: Certificates & Performance Tuning
            if self.update_ssl_certificates():
                success_count += 1
            if self.tune_system():
                success_count += 1
            # Phase 9: Permissions & Advanced Storage Setup
            if self.home_permissions():
                success_count += 1
            if self.install_configure_zfs():
                success_count += 1
            # Phase 10: Additional Applications & Tools
            if self.install_brave_browser():
                success_count += 1
            successful_apps, failed_apps = self.install_flatpak_and_apps()
            if len(failed_apps) == 0:
                success_count += 1
            elif len(failed_apps) <= len(self.config.FLATPAK_APPS) * 0.1:
                self.logger.warning(f"Some Flatpak apps failed to install: {', '.join(failed_apps)}")
                success_count += 0.5
            if self.install_configure_vscode_stable():
                success_count += 1
            # Phase 11: Automatic Updates & Additional Security
            if self.configure_unattended_upgrades():
                success_count += 1
            if self.configure_apparmor():
                success_count += 1
            # Phase 12: Cleanup & Final Configurations
            if self.cleanup_system():
                success_count += 1
            if self.configure_wayland():
                success_count += 1
            if self.install_nala():
                success_count += 1
            if self.install_enable_tailscale():
                success_count += 1
            if self.install_configure_caddy():
                success_count += 1
            # Phase 13: Final System Checks & Reboot Prompt
            if self.final_checks():
                success_count += 1
            success_rate = (success_count / total_steps) * 100
            self.logger.info(f"Setup completed with {success_rate:.1f}% success rate ({success_count}/{total_steps} steps successful)")
            self.prompt_reboot()
            return 0
        except Exception as e:
            self.logger.critical(f"Setup failed with unhandled exception: {e}", exc_info=True)
            return 1

    def configure_wayland(self) -> bool:
        """
        Configure environment variables to enable Wayland for default applications.
        """
        self.print_section("Wayland Environment Configuration")
        etc_env_file = Path("/etc/environment")
        updated_system = False
        try:
            if etc_env_file.is_file():
                self.backup_file(etc_env_file)
                current_content = etc_env_file.read_text()
            else:
                current_content = ""
            current_vars = {}
            for line in current_content.splitlines():
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    current_vars[key] = val
            for key, value in self.config.WAYLAND_ENV_VARS.items():
                if key in current_vars and current_vars[key] == value:
                    self.logger.info(f"{key} already set to {value} in {etc_env_file}.")
                else:
                    current_vars[key] = value
                    updated_system = True
            if updated_system:
                new_content = "\n".join([f"{k}={v}" for k, v in current_vars.items()]) + "\n"
                with open(etc_env_file, "w") as f:
                    f.write(new_content)
                self.logger.info(f"{etc_env_file} updated with Wayland environment variables.")
            else:
                self.logger.info(f"No changes needed for {etc_env_file}.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env_file}: {e}")
        user_env_dir = self.config.USER_HOME / ".config/environment.d"
        user_env_file = user_env_dir / "myenvvars.conf"
        try:
            user_env_dir.mkdir(parents=True, exist_ok=True)
            content = "\n".join([f"{k}={v}" for k, v in self.config.WAYLAND_ENV_VARS.items()]) + "\n"
            updated_user = False
            if user_env_file.is_file():
                current_content = user_env_file.read_text()
                if current_content.strip() == content.strip():
                    self.logger.info(f"{user_env_file} already contains the desired Wayland settings.")
                else:
                    self.backup_file(user_env_file)
                    updated_user = True
            else:
                updated_user = True
            if updated_user:
                with open(user_env_file, "w") as f:
                    f.write(content)
                self.logger.info(f"{'Updated' if user_env_file.exists() else 'Created'} {user_env_file} with Wayland environment variables.")
            self.run_command(["chown", f"{self.config.USERNAME}:{self.config.USERNAME}", str(user_env_file)])
            return True
        except Exception as e:
            self.logger.warning(f"Failed to update user environment file {user_env_file}: {e}")
            return False

    def final_checks(self) -> Dict[str, str]:
        """
        Perform final system checks and log system information.
        """
        self.print_section("Final System Checks")
        system_info = {}
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            self.logger.info(f"Kernel version: {kernel}")
            system_info["kernel"] = kernel
        except Exception as e:
            self.logger.warning(f"Failed to get kernel version: {e}")
        try:
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            self.logger.info(f"System uptime: {uptime}")
            system_info["uptime"] = uptime
        except Exception as e:
            self.logger.warning(f"Failed to get system uptime: {e}")
        try:
            disk_line = subprocess.check_output(["df", "-h", "/"], text=True).splitlines()[1]
            self.logger.info(f"Disk usage (root partition): {disk_line}")
            system_info["disk_usage"] = disk_line
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((line for line in free_out if line.startswith("Mem:")), "")
            self.logger.info(f"Memory usage: {mem_line}")
            system_info["memory"] = mem_line
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
        try:
            cpu_model = subprocess.check_output(["lscpu"], text=True)
            for line in cpu_model.splitlines():
                if "Model name" in line:
                    cpu_info = line.split(':', 1)[1].strip()
                    self.logger.info(f"CPU: {cpu_info}")
                    system_info["cpu"] = cpu_info
                    break
        except Exception as e:
            self.logger.warning(f"Failed to get CPU info: {e}")
        try:
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            self.logger.info("Active network interfaces:")
            for line in interfaces.splitlines():
                self.logger.info(f"  {line}")
            system_info["network_interfaces"] = interfaces
        except Exception as e:
            self.logger.warning(f"Failed to get network interfaces: {e}")
        try:
            with open("/proc/loadavg", "r") as f:
                load_avg = f.read().split()[:3]
                load_info = f"{', '.join(load_avg)}"
                self.logger.info(f"Load averages (1, 5, 15 min): {load_info}")
                system_info["load_avg"] = load_info
        except Exception as e:
            self.logger.warning(f"Failed to get load averages: {e}")
        return system_info


if __name__ == "__main__":
    setup_instance = UbuntuDesktopSetup()
    atexit.register(setup_instance.cleanup)
    sys.exit(setup_instance.run())
