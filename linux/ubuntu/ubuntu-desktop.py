#!/usr/bin/env python3
"""
ubuntu-desktop.py

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
      sudo ./ubuntu-desktop.py

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
# Logging Setup
# ----------------------------

def setup_logging(log_file: str) -> logging.Logger:
    """
    Configure logging to both file and console with color support.
    
    Args:
        log_file: Path to the log file
        
    Returns:
        Configured logger instance
    """
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o700, exist_ok=True)

    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    class ColorFormatter(logging.Formatter):
        """Custom formatter to add color to console log output."""
        def __init__(self, fmt=None, datefmt=None, config=None):
            super().__init__(fmt, datefmt)
            self.config = config or Config()
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
        ch.setFormatter(ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S", Config()))
        logger.addHandler(ch)
        
    return logger


# ----------------------------
# Utility Functions
# ----------------------------

def run_command(
    cmd: Union[List[str], str], 
    check: bool = True, 
    capture_output: bool = False, 
    text: bool = True, 
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Execute a shell command with improved logging and error handling.
    """
    cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
    logger.debug(f"Executing command: {cmd_str}")
    try:
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=text, **kwargs)
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with exit code {e.returncode}: {cmd_str}")
        if e.stdout:
            logger.error(f"Command stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Command stderr: {e.stderr}")
        if check:
            raise
        return e


def command_exists(cmd: str) -> bool:
    """Check if a command exists in the system's PATH."""
    return shutil.which(cmd) is not None


def backup_file(file_path: Union[str, Path]) -> Optional[str]:
    """Create a backup of a file with a timestamp suffix."""
    file_path = Path(file_path)
    if file_path.is_file():
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup = f"{file_path}.bak.{timestamp}"
        try:
            shutil.copy2(file_path, backup)
            logger.info(f"Backed up {file_path} to {backup}")
            return backup
        except Exception as e:
            logger.warning(f"Failed to backup {file_path}: {e}")
    else:
        logger.warning(f"File {file_path} not found; skipping backup.")
    return None


def print_section(title: str, config: Config = Config()) -> None:
    """Log a section header to improve readability of log output."""
    border = "─" * 60
    logger.info(f"{config.NORD10}{border}{config.NC}")
    logger.info(f"{config.NORD10}  {title}{config.NC}")
    logger.info(f"{config.NORD10}{border}{config.NC}")


def handle_error(msg: str, code: int = 1) -> None:
    """Log an error message and exit the script."""
    logger.error(f"{msg} (Exit Code: {code})")
    sys.exit(code)


def cleanup() -> None:
    """Perform any necessary cleanup tasks before the script exits."""
    logger.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


def create_symlink(source: Union[str, Path], target: Union[str, Path], backup: bool = True) -> bool:
    """Create a symbolic link with optional backup of the target if it exists."""
    source, target = Path(source), Path(target)
    if not source.exists():
        logger.warning(f"Source file {source} does not exist, cannot create symlink.")
        return False
    if target.exists() or target.is_symlink():
        if backup:
            backup_file(target)
        try:
            target.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove existing target {target}: {e}")
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(source)
        logger.info(f"Created symlink from {source} to {target}")
        return True
    except Exception as e:
        logger.warning(f"Failed to create symlink from {source} to {target}: {e}")
        return False


def copy_with_backup(src: Union[str, Path], dest: Union[str, Path]) -> bool:
    """Copy a file with automatic backup of the destination if it exists."""
    src, dest = Path(src), Path(dest)
    if not src.exists():
        logger.warning(f"Source file {src} does not exist, cannot copy.")
        return False
    if dest.exists():
        backup_file(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        logger.info(f"Copied {src} to {dest}")
        return True
    except Exception as e:
        logger.warning(f"Failed to copy {src} to {dest}: {e}")
        return False


def download_file(url: str, dest_path: Union[str, Path], show_progress: bool = False) -> bool:
    """Download a file from a URL with optional progress indicator."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-L"]
    if not show_progress:
        cmd.append("-s")
    cmd.extend(["-o", str(dest_path), url])
    try:
        run_command(cmd)
        if dest_path.exists():
            logger.info(f"Downloaded {url} to {dest_path}")
            return True
        else:
            logger.warning(f"Download command succeeded but file {dest_path} does not exist")
            return False
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to download {url}")
        return False


def ensure_directory(path: Union[str, Path], mode: int = 0o755, owner: Optional[str] = None) -> bool:
    """Ensure a directory exists with the specified permissions and ownership."""
    path = Path(path)
    try:
        path.mkdir(mode=mode, parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {path}")
        if owner:
            run_command(["chown", owner, str(path)])
            logger.info(f"Set ownership of {path} to {owner}")
        return True
    except Exception as e:
        logger.warning(f"Failed to create or set permissions on directory {path}: {e}")
        return False


def has_internet_connection() -> bool:
    """Check if the system has an active internet connection."""
    try:
        run_command(["ping", "-c", "1", "-W", "5", "8.8.8.8"], capture_output=True, check=False)
        return True
    except Exception:
        return False


# ----------------------------
# Pre-requisites and System Checks
# ----------------------------

def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        handle_error("Script must be run as root. Exiting.")


def check_network() -> None:
    """Verify network connectivity by pinging a reliable host."""
    print_section("Network Connectivity Check")
    logger.info("Verifying network connectivity...")
    if has_internet_connection():
        logger.info("Network connectivity verified.")
    else:
        handle_error("No network connectivity. Please verify your network settings.")


def save_config_snapshot(config: Config = Config()) -> Optional[str]:
    """
    Create a compressed archive of key configuration files as a snapshot backup
    before making any changes.
    """
    print_section("Configuration Snapshot Backup")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = Path("/var/backups")
    snapshot_file = backup_dir / f"config_snapshot_{timestamp}.tar.gz"
    try:
        backup_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            files_added = 0
            for cfg_path in config.CONFIG_BACKUP_FILES:
                cfg_path = Path(cfg_path)
                if cfg_path.is_file():
                    dest = temp_dir_path / cfg_path.name
                    shutil.copy2(cfg_path, dest)
                    logger.info(f"Included {cfg_path} in snapshot.")
                    files_added += 1
                else:
                    logger.warning(f"Configuration file {cfg_path} not found; skipping.")
            if files_added > 0:
                with tarfile.open(snapshot_file, "w:gz") as tar:
                    tar.add(temp_dir, arcname=".")
                logger.info(f"Configuration snapshot saved as {snapshot_file}.")
                return str(snapshot_file)
            else:
                logger.warning("No configuration files were found to include in the snapshot.")
                return None
    except Exception as e:
        logger.warning(f"Failed to create configuration snapshot: {e}")
        return None


# ----------------------------
# System Update & Package Installation
# ----------------------------

def update_system() -> bool:
    """
    Update package repositories and upgrade installed packages.
    """
    print_section("System Update & Upgrade")
    try:
        logger.info("Updating package repositories...")
        run_command(["apt", "update", "-qq"])
        logger.info("Upgrading system packages...")
        run_command(["apt", "upgrade", "-y"])
        logger.info("System update and upgrade complete.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"System update failed: {e}")
        return False


def install_packages(packages: List[str]) -> Tuple[List[str], List[str]]:
    """
    Install specified packages if they are not already installed.
    """
    print_section("Essential Package Installation")
    logger.info("Checking for required packages...")
    missing_packages = []
    success_packages = []
    failed_packages = []
    for pkg in packages:
        try:
            subprocess.run(["dpkg", "-s", pkg],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            logger.info(f"Package already installed: {pkg}")
            success_packages.append(pkg)
        except subprocess.CalledProcessError:
            missing_packages.append(pkg)
    if missing_packages:
        logger.info(f"Installing missing packages: {' '.join(missing_packages)}")
        try:
            run_command(["apt", "install", "-y"] + missing_packages)
            logger.info("All missing packages installed successfully.")
            success_packages.extend(missing_packages)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install one or more packages: {e}")
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
        logger.info("All required packages are already installed.")
    return success_packages, failed_packages


# ----------------------------
# Timezone and NTP Configuration
# ----------------------------

def configure_timezone(timezone: str = "America/New_York") -> bool:
    """
    Configure the system timezone.
    """
    print_section("Timezone Configuration")
    logger.info(f"Setting timezone to {timezone}...")
    timezone_path = Path(f"/usr/share/zoneinfo/{timezone}")
    localtime_path = Path("/etc/localtime")
    if not timezone_path.is_file():
        logger.warning(f"Timezone file for {timezone} not found.")
        return False
    try:
        if localtime_path.exists() or localtime_path.is_symlink():
            localtime_path.unlink()
        localtime_path.symlink_to(timezone_path)
        logger.info(f"Timezone set to {timezone}.")
        return True
    except Exception as e:
        logger.warning(f"Failed to set timezone: {e}")
        return False


# ----------------------------
# Repository and Shell Setup
# ----------------------------

def setup_repos(config: Config = Config()) -> List[str]:
    """
    Set up GitHub repositories in the user's home directory.
    """
    print_section("GitHub Repositories Setup")
    logger.info(f"Setting up GitHub repositories for user '{config.USERNAME}'...")
    gh_dir = config.USER_HOME / "github"
    gh_dir.mkdir(exist_ok=True)
    successful_repos = []
    for repo in config.GITHUB_REPOS:
        repo_dir = gh_dir / repo
        if (repo_dir / ".git").is_dir():
            logger.info(f"Repository '{repo}' already exists. Pulling latest changes...")
            try:
                run_command(["git", "-C", str(repo_dir), "pull"])
                successful_repos.append(repo)
            except subprocess.CalledProcessError:
                logger.warning(f"Failed to update repository '{repo}'.")
        else:
            logger.info(f"Cloning repository '{repo}' into '{repo_dir}'...")
            try:
                run_command(["git", "clone", f"https://github.com/dunamismax/{repo}.git", str(repo_dir)])
                logger.info(f"Repository '{repo}' cloned successfully.")
                successful_repos.append(repo)
            except subprocess.CalledProcessError:
                logger.warning(f"Failed to clone repository '{repo}'.")
    try:
        run_command(["chown", "-R", f"{config.USERNAME}:{config.USERNAME}", str(gh_dir)])
        logger.info(f"Ownership of '{gh_dir}' set to '{config.USERNAME}'.")
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to set ownership of '{gh_dir}'.")
    return successful_repos


def copy_shell_configs(config: Config = Config()) -> Dict[str, bool]:
    """
    Update shell configuration files from a repository source.
    """
    print_section("Shell Configuration Update")
    source_dir = config.USER_HOME / "github/bash/linux/ubuntu/dotfiles"
    destination_dirs = [config.USER_HOME, Path("/root")]
    results = {}
    for file_name in [".bashrc", ".profile"]:
        src = source_dir / file_name
        if not src.is_file():
            logger.warning(f"Source file {src} not found; skipping.")
            continue
        for dest_dir in destination_dirs:
            dest = dest_dir / file_name
            results[str(dest)] = False
            if dest.is_file() and filecmp.cmp(src, dest):
                logger.info(f"File {dest} is already up-to-date.")
                results[str(dest)] = True
                continue
            try:
                shutil.copy2(src, dest)
                if dest_dir == config.USER_HOME:
                    run_command(["chown", f"{config.USERNAME}:{config.USERNAME}", str(dest)])
                else:
                    run_command(["chown", "root:root", str(dest)])
                logger.info(f"Copied {src} to {dest}.")
                results[str(dest)] = True
            except Exception as e:
                logger.warning(f"Failed to copy {src} to {dest}: {e}")
    return results


def set_bash_shell(username: str = "sawyer") -> bool:
    """
    Ensure that /bin/bash is set as the default shell for the specified user.
    """
    print_section("Default Shell Configuration")
    if not command_exists("bash"):
        logger.info("Bash not found; installing...")
        try:
            run_command(["apt", "install", "-y", "bash"])
        except subprocess.CalledProcessError:
            logger.warning("Bash installation failed.")
            return False
    try:
        shells_path = Path("/etc/shells")
        if shells_path.exists():
            with open(shells_path, "r") as f:
                shells_content = f.read()
            if "/bin/bash" not in shells_content:
                with open(shells_path, "a") as f:
                    f.write("/bin/bash\n")
                logger.info("Added /bin/bash to /etc/shells.")
        else:
            with open(shells_path, "w") as f:
                f.write("/bin/bash\n")
            logger.info("Created /etc/shells with /bin/bash.")
    except Exception as e:
        logger.warning(f"Failed to update /etc/shells: {e}")
        return False
    try:
        run_command(["chsh", "-s", "/bin/bash", username])
        logger.info(f"Default shell for {username} set to /bin/bash.")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to set default shell for {username}.")
        return False


def copy_config_folders(config: Config = Config()) -> Dict[str, bool]:
    """
    Copy all subdirectories from dotfiles to the .config directory.
    """
    print_section("Copying Config Folders")
    source_dir = config.CONFIG_SRC_DIR
    dest_dir = config.CONFIG_DEST_DIR
    dest_dir.mkdir(exist_ok=True)
    logger.info(f"Destination directory ensured: {dest_dir}")
    results = {}
    try:
        for item in source_dir.iterdir():
            if not item.is_dir():
                continue
            dest_path = dest_dir / item.name
            results[item.name] = False
            try:
                shutil.copytree(item, dest_path, dirs_exist_ok=True)
                logger.info(f"Copied '{item}' to '{dest_path}'.")
                run_command(["chown", "-R", f"{config.USERNAME}:{config.USERNAME}", str(dest_path)])
                results[item.name] = True
            except Exception as e:
                logger.warning(f"Failed to copy '{item}' to '{dest_path}': {e}")
    except Exception as e:
        logger.warning(f"Error scanning source directory '{source_dir}': {e}")
    return results


# ----------------------------
# SSH and Sudo Security Configuration
# ----------------------------

def configure_ssh(config: Config = Config()) -> bool:
    """
    Configure and secure the OpenSSH server.
    """
    print_section("SSH Configuration")
    logger.info("Configuring OpenSSH Server...")
    try:
        subprocess.run(["dpkg", "-s", "openssh-server"],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        logger.info("openssh-server not installed. Installing...")
        try:
            run_command(["apt", "install", "-y", "openssh-server"])
            logger.info("OpenSSH Server installed.")
        except subprocess.CalledProcessError:
            logger.error("Failed to install OpenSSH Server.")
            return False
    try:
        run_command(["systemctl", "enable", "--now", "ssh"])
    except subprocess.CalledProcessError:
        logger.error("Failed to enable/start SSH service.")
        return False
    sshd_config = Path("/etc/ssh/sshd_config")
    if not sshd_config.is_file():
        logger.error(f"SSHD configuration file not found: {sshd_config}")
        return False
    backup_file(sshd_config)
    try:
        with open(sshd_config, "r") as f:
            lines = f.readlines()
        for key, value in config.SSH_SETTINGS.items():
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
        run_command(["systemctl", "restart", "ssh"])
        logger.info("SSH configuration updated and service restarted.")
        return True
    except Exception as e:
        logger.error(f"Failed to update SSH configuration: {e}")
        return False


def setup_sudoers(username: str = "sawyer") -> bool:
    """
    Ensure the specified user has sudo privileges.
    """
    print_section("Sudo Configuration")
    logger.info(f"Ensuring user {username} has sudo privileges...")
    try:
        result = run_command(["id", "-nG", username], capture_output=True, text=True)
        if "sudo" in result.stdout.split():
            logger.info(f"User {username} is already in the sudo group.")
            return True
        run_command(["usermod", "-aG", "sudo", username])
        logger.info(f"User {username} added to sudo group.")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to manage sudo privileges for {username}: {e}")
        return False


def configure_firewall(ports: List[str] = None, config: Config = Config()) -> bool:
    """
    Configure the UFW firewall with secure defaults and specified ports.
    """
    print_section("Firewall Configuration")
    logger.info("Configuring firewall using UFW...")
    if ports is None:
        ports = config.FIREWALL_PORTS
    ufw_cmd = "/usr/sbin/ufw"
    if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
        logger.error("UFW command not found. Please install UFW.")
        return False
    try:
        run_command([ufw_cmd, "default", "deny", "incoming"])
        logger.info("Set default deny for incoming traffic.")
        run_command([ufw_cmd, "default", "allow", "outgoing"])
        logger.info("Set default allow for outgoing traffic.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to set default UFW policies: {e}")
        return False
    for port in ports:
        try:
            run_command([ufw_cmd, "allow", f"{port}/tcp"])
            logger.info(f"Allowed TCP port {port}.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to allow TCP port {port}: {e}")
    try:
        result = run_command([ufw_cmd, "status"], capture_output=True, text=True)
        if "inactive" in result.stdout.lower():
            run_command([ufw_cmd, "--force", "enable"])
            logger.info("UFW firewall has been enabled.")
        else:
            logger.info("UFW firewall is already active.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to manage UFW status: {e}")
        return False
    try:
        run_command(["systemctl", "enable", "ufw"])
        run_command(["systemctl", "start", "ufw"])
        logger.info("UFW service enabled and started.")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to manage UFW service: {e}")
        return False


# ----------------------------
# Service Installation and Configuration
# ----------------------------

def install_plex(config: Config = Config()) -> bool:
    """
    Install and configure Plex Media Server.
    """
    print_section("Plex Media Server Installation")
    logger.info("Installing Plex Media Server...")
    if not command_exists("curl"):
        logger.error("curl is required but not installed.")
        return False
    try:
        subprocess.run(["dpkg", "-s", "plexmediaserver"],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        logger.info("Plex Media Server is already installed; skipping download and installation.")
        return True
    except subprocess.CalledProcessError:
        pass
    temp_deb = Path("/tmp/plexmediaserver.deb")
    try:
        download_file(config.PLEX_URL, temp_deb)
        run_command(["dpkg", "-i", str(temp_deb)])
    except subprocess.CalledProcessError:
        logger.warning("dpkg encountered issues. Attempting to fix missing dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError:
            logger.error("Failed to install dependencies for Plex.")
            return False
    plex_conf = Path("/etc/default/plexmediaserver")
    if plex_conf.is_file():
        try:
            with open(plex_conf, "r") as f:
                conf = f.read()
            if f"PLEX_MEDIA_SERVER_USER={config.USERNAME}" in conf:
                logger.info(f"Plex user is already configured as {config.USERNAME}.")
            else:
                new_conf = []
                for line in conf.splitlines():
                    if line.startswith("PLEX_MEDIA_SERVER_USER="):
                        new_conf.append(f"PLEX_MEDIA_SERVER_USER={config.USERNAME}")
                    else:
                        new_conf.append(line)
                with open(plex_conf, "w") as f:
                    f.write("\n".join(new_conf) + "\n")
                logger.info(f"Configured Plex to run as {config.USERNAME}.")
        except Exception as e:
            logger.warning(f"Failed to set Plex user in {plex_conf}: {e}")
    else:
        logger.warning(f"{plex_conf} not found; skipping user configuration.")
    try:
        run_command(["systemctl", "enable", "plexmediaserver"])
        logger.info("Plex service enabled.")
    except subprocess.CalledProcessError:
        logger.warning("Failed to enable Plex service.")
    try:
        temp_deb.unlink()
    except Exception:
        pass
    logger.info("Plex Media Server installed successfully.")
    return True


def install_fastfetch(config: Config = Config()) -> bool:
    """
    Install Fastfetch, a system information tool.
    """
    print_section("Fastfetch Installation")
    try:
        subprocess.run(["dpkg", "-s", "fastfetch"],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        logger.info("Fastfetch is already installed; skipping.")
        return True
    except subprocess.CalledProcessError:
        pass
    temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")
    try:
        download_file(config.FASTFETCH_URL, temp_deb)
        run_command(["dpkg", "-i", str(temp_deb)])
    except subprocess.CalledProcessError:
        logger.warning("fastfetch installation issues; fixing dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError:
            logger.error("Failed to fix dependencies for fastfetch.")
            return False
    try:
        temp_deb.unlink()
    except Exception:
        pass
    logger.info("Fastfetch installed successfully.")
    return True


def docker_config(config: Config = Config()) -> bool:
    """
    Install and configure Docker and Docker Compose.
    """
    print_section("Docker Configuration")
    logger.info("Installing Docker...")
    if command_exists("docker"):
        logger.info("Docker is already installed.")
    else:
        try:
            run_command(["apt", "install", "-y", "docker.io"])
            logger.info("Docker installed successfully.")
        except subprocess.CalledProcessError:
            logger.error("Failed to install Docker.")
            return False
    try:
        result = run_command(["id", "-nG", config.USERNAME], capture_output=True, text=True)
        if "docker" not in result.stdout.split():
            run_command(["usermod", "-aG", "docker", config.USERNAME])
            logger.info(f"Added user '{config.USERNAME}' to docker group.")
        else:
            logger.info(f"User '{config.USERNAME}' is already in docker group.")
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to add {config.USERNAME} to docker group.")
    daemon_json_path = Path("/etc/docker/daemon.json")
    daemon_json_dir = daemon_json_path.parent
    try:
        daemon_json_dir.mkdir(exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create {daemon_json_dir}: {e}")
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
                logger.info("Docker daemon configuration is already up-to-date.")
                write_config = False
            else:
                backup_file(daemon_json_path)
        except Exception as e:
            logger.warning(f"Failed to read {daemon_json_path}: {e}")
            backup_file(daemon_json_path)
    if write_config:
        try:
            with open(daemon_json_path, "w") as f:
                json.dump(desired_daemon_json, f, indent=2)
            logger.info("Docker daemon configuration updated/created.")
        except Exception as e:
            logger.warning(f"Failed to write {daemon_json_path}: {e}")
    try:
        run_command(["systemctl", "enable", "docker"])
        run_command(["systemctl", "restart", "docker"])
        logger.info("Docker service enabled and restarted.")
    except subprocess.CalledProcessError:
        logger.error("Failed to enable or restart Docker service.")
        return False
    if not command_exists("docker-compose"):
        try:
            compose_path = Path("/usr/local/bin/docker-compose")
            download_file(config.DOCKER_COMPOSE_URL, compose_path)
            compose_path.chmod(0o755)
            logger.info("Docker Compose installed successfully.")
        except Exception as e:
            logger.error(f"Failed to install Docker Compose: {e}")
            return False
    else:
        logger.info("Docker Compose is already installed.")
    return True


def deploy_user_scripts(config: Config = Config()) -> bool:
    """
    Deploy user scripts from the repository to the user's bin directory.
    """
    print_section("Deploying User Scripts")
    script_source = config.USER_HOME / "github/bash/linux/ubuntu/_scripts"
    script_target = config.USER_HOME / "bin"
    if not script_source.is_dir():
        logger.error(f"Source directory '{script_source}' does not exist.")
        return False
    script_target.mkdir(exist_ok=True)
    try:
        run_command(["rsync", "-ah", "--delete", f"{script_source}/", f"{script_target}/"])
        run_command(["find", str(script_target), "-type", "f", "-exec", "chmod", "755", "{}", ";"])
        run_command(["chown", "-R", f"{config.USERNAME}:{config.USERNAME}", str(script_target)])
        logger.info("User scripts deployed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Script deployment failed: {e}")
        return False


def configure_periodic() -> bool:
    """
    Set up a daily cron job for system maintenance.
    """
    print_section("Periodic Maintenance Setup")
    cron_file = Path("/etc/cron.daily/ubuntu_maintenance")
    marker = "# Ubuntu maintenance script"
    if cron_file.is_file():
        with open(cron_file, "r") as f:
            if marker in f.read():
                logger.info("Daily maintenance cron job already configured.")
                return True
        backup_file(cron_file)
    content = """#!/bin/sh
# Ubuntu maintenance script
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
"""
    try:
        with open(cron_file, "w") as f:
            f.write(content)
        cron_file.chmod(0o755)
        logger.info(f"Daily maintenance script created at {cron_file}.")
        return True
    except Exception as e:
        logger.warning(f"Failed to create maintenance script: {e}")
        return False


def backup_configs(config: Config = Config()) -> Optional[str]:
    """
    Backup critical system configuration files.
    """
    print_section("Configuration Backups")
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
                    logger.info(f"Backed up {file_path}")
                    files_backed_up += 1
                except Exception as e:
                    logger.warning(f"Failed to backup {file_path}: {e}")
            else:
                logger.warning(f"File {file_path} not found; skipping.")
        if files_backed_up > 0:
            logger.info(f"Configuration files backed up to {backup_dir}")
            return str(backup_dir)
        else:
            logger.warning("No configuration files were backed up.")
            backup_dir.rmdir()
            return None
    except Exception as e:
        logger.warning(f"Failed to create backup directory: {e}")
        return None


def rotate_logs(log_file: Optional[str] = None, config: Config = Config()) -> bool:
    """
    Rotate the log file by compressing it and truncating the original.
    """
    print_section("Log Rotation")
    if log_file is None:
        log_file = config.LOG_FILE
    log_path = Path(log_file)
    if not log_path.is_file():
        logger.warning(f"Log file {log_path} does not exist.")
        return False
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated_file = f"{log_path}.{timestamp}.gz"
        with open(log_path, "rb") as f_in:
            with gzip.open(rotated_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        with open(log_path, "w"):
            pass
        logger.info(f"Log rotated to {rotated_file}.")
        return True
    except Exception as e:
        logger.warning(f"Log rotation failed: {e}")
        return False


def system_health_check() -> Dict[str, str]:
    """
    Perform basic system health checks and log the results.
    """
    print_section("System Health Check")
    health_info = {}
    try:
        uptime = subprocess.check_output(["uptime"], text=True).strip()
        logger.info(f"Uptime: {uptime}")
        health_info["uptime"] = uptime
    except Exception as e:
        logger.warning(f"Failed to get uptime: {e}")
    try:
        df_output = subprocess.check_output(["df", "-h", "/"], text=True).strip()
        for line in df_output.splitlines():
            logger.info(line)
        health_info["disk_usage"] = df_output
    except Exception as e:
        logger.warning(f"Failed to get disk usage: {e}")
    try:
        free_output = subprocess.check_output(["free", "-h"], text=True).strip()
        for line in free_output.splitlines():
            logger.info(line)
        health_info["memory_usage"] = free_output
    except Exception as e:
        logger.warning(f"Failed to get memory usage: {e}")
    return health_info


def verify_firewall_rules(ports: List[str] = None, config: Config = Config()) -> Dict[str, bool]:
    """
    Verify that specific ports are accessible as expected.
    """
    print_section("Firewall Rules Verification")
    if ports is None:
        ports = config.FIREWALL_PORTS
    results = {}
    for port in ports:
        try:
            subprocess.run(["nc", "-z", "-w3", "127.0.0.1", port],
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            logger.info(f"Port {port} is accessible.")
            results[port] = True
        except subprocess.CalledProcessError:
            logger.warning(f"Port {port} is not accessible. Check ufw rules.")
            results[port] = False
    return results


def update_ssl_certificates() -> bool:
    """
    Update SSL certificates using certbot.
    """
    print_section("SSL Certificates Update")
    if not command_exists("certbot"):
        try:
            run_command(["apt", "install", "-y", "certbot"])
            logger.info("certbot installed successfully.")
        except subprocess.CalledProcessError:
            logger.warning("Failed to install certbot.")
            return False
    try:
        run_command(["certbot", "renew"])
        logger.info("SSL certificates updated successfully.")
        return True
    except subprocess.CalledProcessError:
        logger.warning("Failed to update SSL certificates.")
        return False


def tune_system() -> bool:
    """
    Apply performance tuning settings to the system.
    """
    print_section("Performance Tuning")
    sysctl_conf = Path("/etc/sysctl.conf")
    marker = "# Performance tuning settings for Ubuntu"
    if sysctl_conf.is_file():
        backup_file(sysctl_conf)
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
                run_command(["sysctl", "-w", setting])
            logger.info("Performance tuning applied.")
        else:
            logger.info(f"Performance tuning settings already exist in {sysctl_conf}.")
        return True
    except Exception as e:
        logger.warning(f"Failed to apply performance tuning: {e}")
        return False


def final_checks() -> Dict[str, str]:
    """
    Perform final system checks and log system information.
    """
    print_section("Final System Checks")
    system_info = {}
    try:
        kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
        logger.info(f"Kernel version: {kernel}")
        system_info["kernel"] = kernel
    except Exception as e:
        logger.warning(f"Failed to get kernel version: {e}")
    try:
        uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
        logger.info(f"System uptime: {uptime}")
        system_info["uptime"] = uptime
    except Exception as e:
        logger.warning(f"Failed to get system uptime: {e}")
    try:
        disk_line = subprocess.check_output(["df", "-h", "/"], text=True).splitlines()[1]
        logger.info(f"Disk usage (root partition): {disk_line}")
        system_info["disk_usage"] = disk_line
    except Exception as e:
        logger.warning(f"Failed to get disk usage: {e}")
    try:
        free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
        mem_line = next((line for line in free_out if line.startswith("Mem:")), "")
        logger.info(f"Memory usage: {mem_line}")
        system_info["memory"] = mem_line
    except Exception as e:
        logger.warning(f"Failed to get memory usage: {e}")
    try:
        cpu_model = subprocess.check_output(["lscpu"], text=True)
        for line in cpu_model.splitlines():
            if "Model name" in line:
                cpu_info = line.split(':', 1)[1].strip()
                logger.info(f"CPU: {cpu_info}")
                system_info["cpu"] = cpu_info
                break
    except Exception as e:
        logger.warning(f"Failed to get CPU info: {e}")
    try:
        interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
        logger.info("Active network interfaces:")
        for line in interfaces.splitlines():
            logger.info(f"  {line}")
        system_info["network_interfaces"] = interfaces
    except Exception as e:
        logger.warning(f"Failed to get network interfaces: {e}")
    try:
        with open("/proc/loadavg", "r") as f:
            load_avg = f.read().split()[:3]
            load_info = f"{', '.join(load_avg)}"
            logger.info(f"Load averages (1, 5, 15 min): {load_info}")
            system_info["load_avg"] = load_info
    except Exception as e:
        logger.warning(f"Failed to get load averages: {e}")
    return system_info


def home_permissions(config: Config = Config()) -> bool:
    """
    Ensure correct ownership and permissions for the user's home directory.
    """
    print_section("Home Directory Permissions")
    home_dir = config.USER_HOME
    try:
        run_command(["chown", "-R", f"{config.USERNAME}:{config.USERNAME}", str(home_dir)])
        logger.info(f"Ownership of {home_dir} set to {config.USERNAME}.")
    except subprocess.CalledProcessError:
        logger.error(f"Failed to change ownership of {home_dir}.")
        return False
    try:
        run_command(["find", str(home_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", ";"])
        logger.info(f"Setgid bit set on directories in {home_dir}.")
    except subprocess.CalledProcessError:
        logger.warning("Failed to set setgid bit on some directories.")
    if command_exists("setfacl"):
        try:
            run_command(["setfacl", "-R", "-d", "-m", f"u:{config.USERNAME}:rwx", str(home_dir)])
            logger.info(f"Default ACLs applied on {home_dir}.")
        except subprocess.CalledProcessError:
            logger.warning("Failed to apply default ACLs.")
    else:
        logger.warning("setfacl not found; skipping default ACL configuration.")
    return True


def install_configure_zfs(pool_name: str = None, mount_point: Union[str, Path] = None, config: Config = Config()) -> bool:
    """
    Install and configure ZFS for external pool.
    """
    print_section("ZFS Installation and Configuration")
    if pool_name is None:
        pool_name = config.ZFS_POOL_NAME
    if mount_point is None:
        mount_point = config.ZFS_MOUNT_POINT
    mount_point = Path(mount_point)
    cache_file = Path("/etc/zfs/zpool.cache")
    try:
        run_command(["apt", "update"])
        run_command(["apt", "install", "-y", "dpkg-dev", "linux-headers-generic", "linux-image-generic"])
        run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])
        logger.info("Prerequisites and ZFS packages installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install prerequisites or ZFS packages: {e}")
        return False
    for service in ["zfs-import-cache.service", "zfs-mount.service"]:
        try:
            run_command(["systemctl", "enable", service])
            logger.info(f"Enabled {service}.")
        except subprocess.CalledProcessError:
            logger.warning(f"Could not enable {service}.")
    try:
        mount_point.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created mount point directory: {mount_point}")
    except Exception as e:
        logger.warning(f"Failed to create mount point directory {mount_point}: {e}")
    pool_imported = False
    try:
        subprocess.run(["zpool", "list", pool_name],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        logger.info(f"ZFS pool '{pool_name}' is already imported.")
        pool_imported = True
    except subprocess.CalledProcessError:
        try:
            run_command(["zpool", "import", "-f", pool_name])
            logger.info(f"Imported ZFS pool '{pool_name}'.")
            pool_imported = True
        except subprocess.CalledProcessError:
            logger.warning(f"ZFS pool '{pool_name}' not found or failed to import.")
    if not pool_imported:
        logger.warning(f"ZFS pool '{pool_name}' could not be imported. Skipping further configuration.")
        return False
    try:
        run_command(["zfs", "set", f"mountpoint={mount_point}", pool_name])
        logger.info(f"Set mountpoint for pool '{pool_name}' to '{mount_point}'.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to set mountpoint for ZFS pool '{pool_name}': {e}")
    try:
        run_command(["zpool", "set", f"cachefile={cache_file}", pool_name])
        logger.info(f"Updated cachefile for pool '{pool_name}' to '{cache_file}'.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to update cachefile for ZFS pool '{pool_name}': {e}")
    try:
        run_command(["zfs", "mount", "-a"])
        logger.info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to mount ZFS datasets: {e}")
    try:
        mounts = subprocess.check_output(["zfs", "list", "-o", "name,mountpoint", "-H"], text=True)
        if any(str(mount_point) in line for line in mounts.splitlines()):
            logger.info(f"ZFS pool '{pool_name}' is successfully mounted at '{mount_point}'.")
            return True
        else:
            logger.warning(f"ZFS pool '{pool_name}' is not mounted at '{mount_point}'. Please check manually.")
            return False
    except Exception as e:
        logger.warning(f"Error verifying mount status for ZFS pool '{pool_name}': {e}")
        return False


def configure_fail2ban() -> bool:
    """
    Configure and enable fail2ban with a secure basic default configuration.
    """
    print_section("Fail2ban Configuration")
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
        backup_file(jail_local)
    try:
        with open(jail_local, "w") as f:
            f.write(config_content)
        logger.info("Fail2ban configuration written to /etc/fail2ban/jail.local.")
    except Exception as e:
        logger.warning(f"Failed to write Fail2ban configuration: {e}")
        return False
    try:
        run_command(["systemctl", "enable", "fail2ban"])
        run_command(["systemctl", "restart", "fail2ban"])
        logger.info("Fail2ban service enabled and restarted successfully.")
        return True
    except subprocess.CalledProcessError:
        logger.warning("Failed to enable or restart the Fail2ban service.")
        return False


def configure_wayland(config: Config = Config()) -> bool:
    """
    Configure environment variables to enable Wayland for default applications.
    """
    print_section("Wayland Environment Configuration")
    etc_env_file = Path("/etc/environment")
    updated_system = False
    try:
        if etc_env_file.is_file():
            backup_file(etc_env_file)
            current_content = etc_env_file.read_text()
        else:
            current_content = ""
        current_vars = {}
        for line in current_content.splitlines():
            if "=" in line:
                key, val = line.strip().split("=", 1)
                current_vars[key] = val
        for key, value in config.WAYLAND_ENV_VARS.items():
            if key in current_vars and current_vars[key] == value:
                logger.info(f"{key} already set to {value} in {etc_env_file}.")
            else:
                current_vars[key] = value
                updated_system = True
        if updated_system:
            new_content = "\n".join([f"{k}={v}" for k, v in current_vars.items()]) + "\n"
            with open(etc_env_file, "w") as f:
                f.write(new_content)
            logger.info(f"{etc_env_file} updated with Wayland environment variables.")
        else:
            logger.info(f"No changes needed for {etc_env_file}.")
    except Exception as e:
        logger.warning(f"Failed to update {etc_env_file}: {e}")
    user_env_dir = config.USER_HOME / ".config/environment.d"
    user_env_file = user_env_dir / "myenvvars.conf"
    try:
        user_env_dir.mkdir(parents=True, exist_ok=True)
        content = "\n".join([f"{k}={v}" for k, v in config.WAYLAND_ENV_VARS.items()]) + "\n"
        updated_user = False
        if user_env_file.is_file():
            current_content = user_env_file.read_text()
            if current_content.strip() == content.strip():
                logger.info(f"{user_env_file} already contains the desired Wayland settings.")
            else:
                backup_file(user_env_file)
                updated_user = True
        else:
            updated_user = True
        if updated_user:
            with open(user_env_file, "w") as f:
                f.write(content)
            logger.info(f"{'Updated' if user_env_file.exists() else 'Created'} {user_env_file} with Wayland environment variables.")
        run_command(["chown", f"{config.USERNAME}:{config.USERNAME}", str(user_env_file)])
        return True
    except Exception as e:
        logger.warning(f"Failed to update user environment file {user_env_file}: {e}")
        return False


def install_brave_browser() -> bool:
    """
    Install the Brave browser on Ubuntu.
    """
    print_section("Brave Browser Installation")
    logger.info("Installing Brave browser...")
    try:
        run_command(["sh", "-c", "curl -fsS https://dl.brave.com/install.sh | sh"])
        logger.info("Brave browser installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Brave browser: {e}")
        return False


def install_flatpak_and_apps(apps: List[str] = None, config: Config = Config()) -> Tuple[List[str], List[str]]:
    """
    Install Flatpak, add the Flathub repository, and install Flatpak applications.
    """
    print_section("Flatpak Installation and Setup")
    if apps is None:
        apps = config.FLATPAK_APPS
    logger.info("Installing Flatpak...")
    try:
        run_command(["apt", "install", "-y", "flatpak"])
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Flatpak: {e}")
        return [], apps
    logger.info("Installing GNOME Software Flatpak plugin...")
    try:
        run_command(["apt", "install", "-y", "gnome-software-plugin-flatpak"])
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to install GNOME Software Flatpak plugin: {e}")
    logger.info("Adding Flathub repository...")
    try:
        run_command(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to add Flathub repository: {e}")
        return [], apps
    successful_apps = []
    failed_apps = []
    logger.info("Installing Flatpak applications from Flathub...")
    for app in apps:
        logger.info(f"Installing {app}...")
        try:
            run_command(["flatpak", "install", "--assumeyes", "flathub", app])
            logger.info(f"{app} installed successfully.")
            successful_apps.append(app)
        except subprocess.CalledProcessError:
            logger.warning(f"Failed to install {app}.")
            failed_apps.append(app)
    return successful_apps, failed_apps


def install_configure_caddy() -> bool:
    """
    Install and configure the Caddy web server.
    """
    print_section("Caddy Installation and Configuration")
    logger.info("Installing Caddy web server...")
    caddy_deb_url = "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb"
    temp_deb = Path("/tmp/caddy_2.9.1_linux_amd64.deb")
    try:
        download_file(caddy_deb_url, temp_deb)
    except Exception as e:
        logger.error(f"Failed to download Caddy package: {e}")
        return False
    try:
        run_command(["dpkg", "-i", str(temp_deb)])
    except subprocess.CalledProcessError:
        logger.warning("Dependency issues encountered during Caddy installation. Attempting to fix...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to resolve dependencies for Caddy: {e}")
            return False
    logger.info("Caddy installed successfully.")
    try:
        temp_deb.unlink()
        logger.info("Removed temporary Caddy package file.")
    except Exception as e:
        logger.warning(f"Failed to remove temporary file {temp_deb}: {e}")
    source_caddyfile = Path("/home/sawyer/github/bash/linux/ubuntu/dotfiles/Caddyfile")
    dest_caddyfile = Path("/etc/caddy/Caddyfile")
    if not source_caddyfile.is_file():
        logger.warning(f"Source Caddyfile not found at {source_caddyfile}. Skipping Caddyfile configuration.")
    else:
        if dest_caddyfile.exists():
            backup_file(dest_caddyfile)
        try:
            shutil.copy2(source_caddyfile, dest_caddyfile)
            logger.info(f"Copied {source_caddyfile} to {dest_caddyfile}.")
        except Exception as e:
            logger.warning(f"Failed to copy Caddyfile: {e}")
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
        logger.info(f"Log directory {log_dir} is ready.")
        for log_file in log_files:
            with open(log_file, "a"):
                os.utime(log_file, None)
            log_file.chmod(0o644)
            logger.info(f"Prepared log file: {log_file}")
    except Exception as e:
        logger.warning(f"Failed to prepare log files: {e}")
    try:
        run_command(["systemctl", "enable", "caddy"])
        logger.info("Caddy service enabled.")
        run_command(["systemctl", "restart", "caddy"])
        logger.info("Caddy service started successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to enable or start Caddy service: {e}")
        return False


def create_system_zfs_snapshot() -> Optional[str]:
    """
    Create a ZFS snapshot of the system's root dataset.
    """
    print_section("System ZFS Snapshot Backup")
    system_dataset = "rpool/ROOT/ubuntu"
    try:
        run_command(["zfs", "list", system_dataset], capture_output=True)
        logger.info(f"System dataset '{system_dataset}' found.")
    except subprocess.CalledProcessError:
        system_dataset = "rpool"
        logger.warning("Dataset 'rpool/ROOT/ubuntu' not found. Using 'rpool' for snapshot.")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    snapshot_name = f"{system_dataset}@backup_{timestamp}"
    try:
        run_command(["zfs", "snapshot", snapshot_name])
        logger.info(f"Created system ZFS snapshot: {snapshot_name}")
        return snapshot_name
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to create system ZFS snapshot for '{system_dataset}': {e}")
        return None


def configure_unattended_upgrades() -> bool:
    """
    Install and configure unattended-upgrades for automatic security updates.
    """
    print_section("Unattended Upgrades Configuration")
    try:
        run_command(["apt", "install", "-y", "unattended-upgrades"])
        logger.info("Unattended-upgrades installed. Please review /etc/apt/apt.conf.d/50unattended-upgrades for customization.")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to install unattended-upgrades: {e}")
        return False


def cleanup_system() -> bool:
    """
    Clean up temporary files, remove unused packages, and clear apt cache.
    """
    print_section("System Cleanup")
    try:
        run_command(["apt", "autoremove", "-y"])
        logger.info("Unused packages removed.")
        run_command(["apt", "clean"])
        logger.info("Apt cache cleared.")
        logger.info("System cleanup completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"System cleanup failed: {e}")
        return False


def configure_apparmor() -> bool:
    """
    Install and enable AppArmor along with its utilities.
    """
    print_section("AppArmor Configuration")
    try:
        run_command(["apt", "install", "-y", "apparmor", "apparmor-utils"])
        run_command(["systemctl", "enable", "apparmor"])
        run_command(["systemctl", "start", "apparmor"])
        logger.info("AppArmor installed and started successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to install or start AppArmor: {e}")
        return False


def install_configure_vscode_stable() -> bool:
    """
    Install Visual Studio Code - Stable and configure it to run natively on Wayland.
    """
    print_section("Visual Studio Code - Stable Installation and Configuration")
    vscode_url = (
        "https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
        "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
    )
    deb_path = Path("/tmp/code.deb")
    try:
        logger.info("Downloading VS Code Stable...")
        download_file(vscode_url, deb_path)
    except Exception as e:
        logger.error(f"Failed to download VS Code Stable: {e}")
        return False
    try:
        logger.info("Installing VS Code Stable...")
        run_command(["dpkg", "-i", str(deb_path)])
    except subprocess.CalledProcessError:
        logger.warning("dpkg installation encountered issues. Attempting to fix dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fix dependencies for VS Code Stable: {e}")
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
        logger.info(f"Updated system-wide desktop file: {desktop_file_path}")
    except Exception as e:
        logger.warning(f"Failed to update system-wide desktop file: {e}")
    local_app_dir = Path.home() / ".local/share/applications"
    local_desktop_file = local_app_dir / "code.desktop"
    try:
        local_app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(desktop_file_path, local_desktop_file)
        logger.info(f"Copied desktop file to local directory: {local_desktop_file}")
        with open(local_desktop_file, "r") as f:
            content = f.read()
        updated_content = content.replace("StartupWMClass=Code", "StartupWMClass=code")
        with open(local_desktop_file, "w") as f:
            f.write(updated_content)
        logger.info(f"Updated local desktop file for Wayland compatibility: {local_desktop_file}")
        return True
    except Exception as e:
        logger.warning(f"Failed to update local desktop file: {e}")
        return False


def install_nala() -> bool:
    """
    Install Nala (an apt front-end) if it's not already installed.
    """
    print_section("Nala Installation")
    if command_exists("nala"):
        logger.info("Nala is already installed.")
        return True
    try:
        logger.info("Nala is not installed. Installing Nala...")
        run_command(["apt", "update"])
        run_command(["apt", "install", "-y", "nala"])
        logger.info("Nala installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Nala: {e}")
        return False


def install_enable_tailscale() -> bool:
    """
    Install and enable Tailscale on the server.
    """
    print_section("Tailscale Installation and Enablement")
    if command_exists("tailscale"):
        logger.info("Tailscale is already installed; skipping installation.")
    else:
        logger.info("Installing Tailscale...")
        try:
            run_command(["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"])
            logger.info("Tailscale installed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Tailscale: {e}")
            return False
    try:
        run_command(["systemctl", "enable", "--now", "tailscaled"])
        logger.info("Tailscale service enabled and started.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to enable/start Tailscale service: {e}")
        return False


def prompt_reboot() -> bool:
    """
    Prompt the user for a system reboot to apply changes.
    """
    print_section("Reboot Prompt")
    answer = input("Would you like to reboot now? [y/N]: ").strip().lower()
    if answer == "y":
        logger.info("Rebooting system now...")
        try:
            run_command(["shutdown", "-r", "now"])
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to reboot system: {e}")
            return False
    else:
        logger.info("Reboot canceled. Please reboot later for all changes to take effect.")
        return False


# ----------------------------
# Main Execution Flow
# ----------------------------

def main() -> int:
    """
    Main function executing the entire setup process in logical phases.
    """
    config = Config()
    success_count = 0
    total_steps = 35  # Total number of major steps
    try:
        # Phase 1: Pre-flight Checks & Backups
        check_root()
        check_network()
        save_config_snapshot(config)
        create_system_zfs_snapshot()
        # Phase 2: System Update & Basic Configuration
        if update_system():
            success_count += 1
        installed_pkgs, failed_pkgs = install_packages(config.PACKAGES)
        if len(failed_pkgs) == 0:
            success_count += 1
        elif len(failed_pkgs) <= len(config.PACKAGES) * 0.1:
            logger.warning(f"Some packages failed to install: {', '.join(failed_pkgs)}")
            success_count += 0.5
        if configure_timezone():
            success_count += 1
        # Phase 3: Repository & Shell Setup
        if setup_repos(config):
            success_count += 1
        if copy_shell_configs(config):
            success_count += 1
        if copy_config_folders(config):
            success_count += 1
        if set_bash_shell(config.USERNAME):
            success_count += 1
        # Phase 4: Security Hardening
        if configure_ssh(config):
            success_count += 1
        if setup_sudoers(config.USERNAME):
            success_count += 1
        if configure_firewall(config.FIREWALL_PORTS, config):
            success_count += 1
        if configure_fail2ban():
            success_count += 1
        # Phase 5: Essential Service Installation
        if docker_config(config):
            success_count += 1
        if install_plex(config):
            success_count += 1
        if install_fastfetch(config):
            success_count += 1
        # Phase 6: User Customization & Script Deployment
        if deploy_user_scripts(config):
            success_count += 1
        # Phase 7: Maintenance & Monitoring Tasks
        if configure_periodic():
            success_count += 1
        if backup_configs(config):
            success_count += 1
        if rotate_logs(config.LOG_FILE, config):
            success_count += 1
        if system_health_check():
            success_count += 1
        if verify_firewall_rules(config.FIREWALL_PORTS, config):
            success_count += 1
        # Phase 8: Certificates & Performance Tuning
        if update_ssl_certificates():
            success_count += 1
        if tune_system():
            success_count += 1
        # Phase 9: Permissions & Advanced Storage Setup
        if home_permissions(config):
            success_count += 1
        if install_configure_zfs(config.ZFS_POOL_NAME, config.ZFS_MOUNT_POINT, config):
            success_count += 1
        # Phase 10: Additional Applications & Tools
        if install_brave_browser():
            success_count += 1
        successful_apps, failed_apps = install_flatpak_and_apps(config.FLATPAK_APPS, config)
        if len(failed_apps) == 0:
            success_count += 1
        elif len(failed_apps) <= len(config.FLATPAK_APPS) * 0.1:
            logger.warning(f"Some Flatpak apps failed to install: {', '.join(failed_apps)}")
            success_count += 0.5
        if install_configure_vscode_stable():
            success_count += 1
        # Phase 11: Automatic Updates & Additional Security
        if configure_unattended_upgrades():
            success_count += 1
        if configure_apparmor():
            success_count += 1
        # Phase 12: Cleanup & Final Configurations
        if cleanup_system():
            success_count += 1
        if configure_wayland(config):
            success_count += 1
        if install_nala():
            success_count += 1
        if install_enable_tailscale():
            success_count += 1
        if install_configure_caddy():
            success_count += 1
        # Phase 13: Final System Checks & Reboot Prompt
        if final_checks():
            success_count += 1
        success_rate = (success_count / total_steps) * 100
        logger.info(f"Setup completed with {success_rate:.1f}% success rate ({success_count}/{total_steps} steps successful)")
        prompt_reboot()
        return 0
    except Exception as e:
        logger.critical(f"Setup failed with unhandled exception: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    logger = setup_logging(Config.LOG_FILE)
    atexit.register(cleanup)
    sys.exit(main())
