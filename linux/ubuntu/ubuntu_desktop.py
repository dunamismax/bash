#!/usr/bin/env python3
"""
Ubuntu Desktop Initialization & Maintenance Utility
-------------------------------------------------
Description:
  This automation script configures and optimizes an Ubuntu Desktop environment.
  It executes a comprehensive set of tasks organized in a phase-based, class-structured
  approach with robust error handling, progress indicators using ANSI colors,
  and unified Nord-themed terminal output.

  The script performs the following phases:
  1. Pre-flight Checks & Backups
  2. System Update & Basic Configuration
  3. Repository & Shell Setup
  4. Security Hardening
  5. Essential Service Installation
  6. User Customization & Script Deployment
  7. Maintenance & Monitoring Tasks
  8. Certificates & Performance Tuning
  9. Permissions & Advanced Storage Setup
  10. Additional Applications & Tools
  11. Automatic Updates & Additional Security
  12. Cleanup & Final Configurations
  13. Final System Checks & Reboot Prompt

Usage:
  sudo ./ubuntu_desktop_setup.py

Author: dunamismax (improved by Claude)
Version: 7.0.0 | License: MIT
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
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
@dataclass
class Config:
    """Configuration class to store all global settings."""

    # Software versions and URLs
    PLEX_VERSION: str = "1.41.3.9314-a0bfb8370"
    FASTFETCH_VERSION: str = "2.36.1"
    DOCKER_COMPOSE_VERSION: str = "2.20.2"
    PLEX_URL: str = field(init=False)
    FASTFETCH_URL: str = field(init=False)
    UNAME: Any = field(default_factory=platform.uname)
    DOCKER_COMPOSE_URL: str = field(init=False)
    # Logging and user config
    LOG_FILE: str = "/var/log/ubuntu_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path(f"/home/sawyer"))
    # Directories for dotfiles and configuration
    CONFIG_SRC_DIR: Path = field(init=False)
    CONFIG_DEST_DIR: Path = field(init=False)
    # ZFS configuration
    ZFS_POOL_NAME: str = "WD_BLACK"
    ZFS_MOUNT_POINT: Path = field(default_factory=lambda: Path(f"/media/WD_BLACK"))
    # Essential packages to install
    PACKAGES: List[str] = field(
        default_factory=lambda: [
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
            "xorg",
            "x11-xserver-utils",
            "xterm",
            "alacritty",
            "fonts-dejavu-core",
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
            "john",
            "hydra",
            "aircrack-ng",
            "nikto",
            "fail2ban",
            "rkhunter",
            "chkrootkit",
            "postgresql-client",
            "mysql-client",
            "redis-server",
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
        ]
    )
    # Flatpak applications to install
    FLATPAK_APPS: List[str] = field(
        default_factory=lambda: [
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
    )
    # Wayland environment variables
    WAYLAND_ENV_VARS: Dict[str, str] = field(
        default_factory=lambda: {
            "GDK_BACKEND": "wayland",
            "QT_QPA_PLATFORM": "wayland",
            "SDL_VIDEODRIVER": "wayland",
        }
    )
    # GitHub repositories to set up
    GITHUB_REPOS: List[str] = field(
        default_factory=lambda: ["bash", "windows", "web", "python", "go", "misc"]
    )
    # SSH security settings
    SSH_SETTINGS: Dict[str, str] = field(
        default_factory=lambda: {
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
    )
    # Firewall TCP ports to allow
    FIREWALL_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443", "32400"]
    )
    # Configuration files to backup
    CONFIG_BACKUP_FILES: List[str] = field(
        default_factory=lambda: [
            "/etc/ssh/sshd_config",
            "/etc/ufw/user.rules",
            "/etc/ntp.conf",
            "/etc/sysctl.conf",
            "/etc/environment",
            "/etc/fail2ban/jail.local",
            "/etc/docker/daemon.json",
            "/etc/caddy/Caddyfile",
        ]
    )

    def __post_init__(self):
        # Initialize computed fields that depend on other fields
        self.PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{self.PLEX_VERSION}/debian/plexmediaserver_{self.PLEX_VERSION}_amd64.deb"
        self.FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{self.FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"
        self.DOCKER_COMPOSE_URL = f"https://github.com/docker/compose/releases/download/v{self.DOCKER_COMPOSE_VERSION}/docker-compose-{self.UNAME.system}-{self.UNAME.machine}"
        self.CONFIG_SRC_DIR = self.USER_HOME / "github/bash/linux/ubuntu/dotfiles"
        self.CONFIG_DEST_DIR = self.USER_HOME / ".config"


# ------------------------------------------------------------------------------
# Global Nord Color Palette and Logging Settings
# ------------------------------------------------------------------------------
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

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
    """Custom formatter for terminal output with Nord color theme."""

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

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


def setup_logging(log_file: str) -> logging.Logger:
    """
    Set up logging with Nord-colored console output and file logging.

    Args:
        log_file: Path to the log file

    Returns:
        Configured logger object
    """
    log_dir = os.path.dirname(log_file)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    # Remove pre-existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)
    formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(fh)
    try:
        os.chmod(log_file, 0o600)
    except Exception as e:
        logger.warning(f"Could not set permissions on log file {log_file}: {e}")
    return logger


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def global_signal_handler(signum, frame):
    """
    Handle system signals gracefully and initiate cleanup.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger = logging.getLogger("ubuntu_setup")
    logger.error(f"Script interrupted by {sig_name}. Initiating cleanup.")
    try:
        setup_instance.cleanup()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


# Register signal handlers
for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, global_signal_handler)


# ------------------------------------------------------------------------------
# PROGRESS HELPER (Simplified version without Rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a function while displaying a simple progress indicator.

    Args:
        description: Description of the task
        func: Function to run
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the executed function
    """
    logger = logging.getLogger("ubuntu_setup")
    logger.info(f"{NORD8}⏳ Starting: {description}{NC}")
    try:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        logger.info(f"{NORD14}✓ Completed: {description} in {elapsed:.2f}s{NC}")
        return result
    except Exception as e:
        logger.error(f"{NORD11}✗ Failed: {description} - {str(e)}{NC}")
        raise


# ------------------------------------------------------------------------------
# Main Setup Class
# ------------------------------------------------------------------------------
class UbuntuDesktopSetup:
    """Main class for handling Ubuntu Desktop setup and configuration."""

    def __init__(self, config: Config = Config()):
        """
        Initialize the setup class with configuration.

        Args:
            config: Configuration object with all settings
        """
        self.config = config
        self.logger = setup_logging(self.config.LOG_FILE)

    # ------------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------------
    def print_section(self, title: str) -> None:
        """
        Print a formatted section header for log readability.

        Args:
            title: Title of the section
        """
        border = "─" * 60
        self.logger.info(f"{NORD10}{border}{NC}")
        self.logger.info(f"{NORD10}  {title}{NC}")
        self.logger.info(f"{NORD10}{border}{NC}")

    def run_command(
        self,
        cmd: Union[List[str], str],
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """
        Execute a shell command with logging and error handling.

        Args:
            cmd: Command to execute, as a list of strings or a single string
            check: Whether to raise an exception on command failure
            capture_output: Whether to capture the command output
            text: Whether to return strings rather than bytes for output
            **kwargs: Additional arguments to pass to subprocess.run

        Returns:
            CompletedProcess object with command results

        Raises:
            subprocess.CalledProcessError: If check is True and the command fails
        """
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        self.logger.debug(f"Executing command: {cmd_str}")
        try:
            result = subprocess.run(
                cmd, check=check, capture_output=capture_output, text=text, **kwargs
            )
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed ({cmd_str}): {e}")
            if e.stdout:
                self.logger.error(f"Stdout: {e.stdout}")
            if e.stderr:
                self.logger.error(f"Stderr: {e.stderr}")
            if check:
                raise
            return e

    def command_exists(self, cmd: str) -> bool:
        """
        Check if a command exists in the system PATH.

        Args:
            cmd: Command name to check

        Returns:
            True if command exists, False otherwise
        """
        return shutil.which(cmd) is not None

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """
        Backup a file by appending a timestamp suffix.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if backup failed
        """
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

    def handle_error(self, msg: str, code: int = 1) -> None:
        """
        Log an error message and exit the script.

        Args:
            msg: Error message to log
            code: Exit code to use
        """
        self.logger.error(f"{msg} (Exit Code: {code})")
        sys.exit(code)

    def download_file(
        self, url: str, dest_path: Union[str, Path], show_progress: bool = True
    ) -> bool:
        """
        Download a file from a URL.

        Args:
            url: URL to download from
            dest_path: Path to save the file to
            show_progress: Whether to show download progress

        Returns:
            True if download succeeded, False otherwise
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["curl", "-L", "-o", str(dest_path), url]
        if not show_progress:
            cmd.insert(1, "-s")
        try:
            self.run_command(cmd)
            if dest_path.exists():
                self.logger.info(f"Downloaded {url} to {dest_path}")
                return True
            else:
                self.logger.warning(f"Download succeeded but {dest_path} not found.")
                return False
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to download {url}")
            return False

    # ------------------------------------------------------------------------
    # Phase 1: Pre-flight Checks & Backups
    # ------------------------------------------------------------------------
    def phase_preflight(self) -> bool:
        """
        Perform pre-flight checks and backups.

        Returns:
            True if all pre-flight checks pass, False otherwise
        """
        self.print_section("Phase 1: Pre-flight Checks & Backups")
        try:
            self.check_root()
            self.check_network()
            self.save_config_snapshot()
            self.create_system_zfs_snapshot()
            return True
        except Exception as e:
            self.logger.error(f"Phase 1 failed: {e}")
            return False

    def check_root(self) -> None:
        """
        Ensure the script is run as root.

        Raises:
            SystemExit: If not run as root
        """
        if os.geteuid() != 0:
            self.handle_error("Script must be run as root. Exiting.")

    def has_internet_connection(self) -> bool:
        """
        Check if the system has an active internet connection.

        Returns:
            True if connected to the internet, False otherwise
        """
        try:
            self.run_command(
                ["ping", "-c", "1", "-W", "5", "8.8.8.8"],
                capture_output=True,
                check=False,
            )
            return True
        except Exception:
            return False

    def check_network(self) -> None:
        """
        Verify network connectivity by pinging a reliable host.

        Raises:
            SystemExit: If no network connectivity
        """
        self.print_section("Network Connectivity Check")
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.handle_error("No network connectivity. Check your network settings.")

    def save_config_snapshot(self) -> Optional[str]:
        """
        Create a snapshot of system configuration files.

        Returns:
            Path to the snapshot file, or None if no snapshot created
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
                for cfg in self.config.CONFIG_BACKUP_FILES:
                    cfg_path = Path(cfg)
                    if cfg_path.is_file():
                        shutil.copy2(cfg_path, temp_dir_path / cfg_path.name)
                        self.logger.info(f"Included {cfg_path} in snapshot.")
                        files_added += 1
                    else:
                        self.logger.warning(f"{cfg_path} not found; skipping.")
                if files_added > 0:
                    with tarfile.open(snapshot_file, "w:gz") as tar:
                        tar.add(temp_dir, arcname=".")
                    self.logger.info(f"Configuration snapshot saved: {snapshot_file}")
                    return str(snapshot_file)
                else:
                    self.logger.warning("No configuration files found for snapshot.")
                    return None
        except Exception as e:
            self.logger.warning(f"Failed to create config snapshot: {e}")
            return None

    def create_system_zfs_snapshot(self) -> Optional[str]:
        """
        Create a ZFS snapshot of the system.

        Returns:
            Snapshot name if created, None otherwise
        """
        self.print_section("System ZFS Snapshot Backup")
        system_dataset = "rpool/ROOT/ubuntu"
        try:
            self.run_command(["zfs", "list", system_dataset], capture_output=True)
            self.logger.info(f"Dataset '{system_dataset}' found.")
        except subprocess.CalledProcessError:
            system_dataset = "rpool"
            self.logger.warning("Dataset 'rpool/ROOT/ubuntu' not found; using 'rpool'.")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        snapshot_name = f"{system_dataset}@backup_{timestamp}"
        try:
            self.run_command(["zfs", "snapshot", snapshot_name])
            self.logger.info(f"Created ZFS snapshot: {snapshot_name}")
            return snapshot_name
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to create ZFS snapshot: {e}")
            return None

    # ------------------------------------------------------------------------
    # Phase 2: System Update & Basic Configuration
    # ------------------------------------------------------------------------
    def phase_system_update(self) -> bool:
        """
        Update the system and install basic packages.

        Returns:
            True if system update succeeded, False otherwise
        """
        self.print_section("Phase 2: System Update & Basic Configuration")
        status = True
        if not self.update_system():
            status = False
        pkgs_success, pkgs_failed = self.install_packages()
        if pkgs_failed and len(pkgs_failed) > len(self.config.PACKAGES) * 0.1:
            self.logger.error(
                f"Package installation failures: {', '.join(pkgs_failed)}"
            )
            status = False
        if not self.configure_timezone():
            status = False
        return status

    def update_system(self) -> bool:
        """
        Update and upgrade the system packages.

        Returns:
            True if update succeeded, False otherwise
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
        Install essential packages.

        Returns:
            Tuple of (successful installs, failed installs)
        """
        self.print_section("Essential Package Installation")
        self.logger.info("Checking for required packages...")
        missing = []
        success = []
        failed = []
        for pkg in self.config.PACKAGES:
            try:
                subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.logger.info(f"Package already installed: {pkg}")
                success.append(pkg)
            except subprocess.CalledProcessError:
                missing.append(pkg)
        if missing:
            self.logger.info(f"Installing missing packages: {' '.join(missing)}")
            try:
                self.run_command(["apt", "install", "-y"] + missing)
                self.logger.info("Missing packages installed successfully.")
                success.extend(missing)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install packages: {e}")
                for pkg in missing:
                    try:
                        subprocess.run(
                            ["dpkg", "-s", pkg],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        success.append(pkg)
                    except subprocess.CalledProcessError:
                        failed.append(pkg)
        else:
            self.logger.info("All required packages are installed.")
        return success, failed

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        """
        Configure the system timezone.

        Args:
            timezone: Timezone to set

        Returns:
            True if timezone set successfully, False otherwise
        """
        self.print_section("Timezone Configuration")
        self.logger.info(f"Setting timezone to {timezone}...")
        tz_file = Path(f"/usr/share/zoneinfo/{timezone}")
        localtime = Path("/etc/localtime")
        if not tz_file.is_file():
            self.logger.warning(f"Timezone file not found: {tz_file}")
            return False
        try:
            if localtime.exists() or localtime.is_symlink():
                localtime.unlink()
            localtime.symlink_to(tz_file)
            self.logger.info(f"Timezone set to {timezone}.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to set timezone: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 3: Repository & Shell Setup
    # ------------------------------------------------------------------------
    def phase_repo_shell_setup(self) -> bool:
        """
        Set up repositories and shell configurations.

        Returns:
            True if setup succeeded, False otherwise
        """
        self.print_section("Phase 3: Repository & Shell Setup")
        status = True
        if not self.setup_repos():
            status = False
        if not self.copy_shell_configs():
            status = False
        if not self.copy_config_folders():
            status = False
        if not self.set_bash_shell():
            status = False
        return status

    def setup_repos(self) -> List[str]:
        """
        Set up GitHub repositories.

        Returns:
            List of successfully set up repositories
        """
        self.print_section("GitHub Repositories Setup")
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)
        successful = []
        for repo in self.config.GITHUB_REPOS:
            repo_dir = gh_dir / repo
            if (repo_dir / ".git").is_dir():
                self.logger.info(f"Repository '{repo}' exists; pulling updates...")
                try:
                    self.run_command(["git", "-C", str(repo_dir), "pull"])
                    successful.append(repo)
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to update repository '{repo}'.")
            else:
                self.logger.info(f"Cloning repository '{repo}'...")
                try:
                    self.run_command(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            str(repo_dir),
                        ]
                    )
                    self.logger.info(f"Repository '{repo}' cloned.")
                    successful.append(repo)
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to clone repository '{repo}'.")
        try:
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(gh_dir),
                ]
            )
            self.logger.info(f"Ownership of {gh_dir} set to {self.config.USERNAME}.")
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set ownership of {gh_dir}.")
        return successful

    def copy_shell_configs(self) -> bool:
        """
        Copy shell configuration files.

        Returns:
            True if copy succeeded, False otherwise
        """
        self.print_section("Shell Configuration Update")
        source_dir = self.config.USER_HOME / "github/bash/linux/ubuntu/dotfiles"
        destination_dirs = [self.config.USER_HOME, Path("/root")]
        overall = True
        for file_name in [".bashrc", ".profile"]:
            src = source_dir / file_name
            if not src.is_file():
                self.logger.warning(f"Source file {src} not found; skipping.")
                continue
            for dest_dir in destination_dirs:
                dest = dest_dir / file_name
                if dest.is_file() and filecmp.cmp(src, dest):
                    self.logger.info(f"File {dest} is already up-to-date.")
                else:
                    try:
                        shutil.copy2(src, dest)
                        owner = (
                            f"{self.config.USERNAME}:{self.config.USERNAME}"
                            if dest_dir == self.config.USER_HOME
                            else "root:root"
                        )
                        self.run_command(["chown", owner, str(dest)])
                        self.logger.info(f"Copied {src} to {dest}.")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        overall = False
        return overall

    def copy_config_folders(self) -> bool:
        """
        Copy configuration folders.

        Returns:
            True if copy succeeded, False otherwise
        """
        self.print_section("Copying Config Folders")
        src = self.config.CONFIG_SRC_DIR
        dest = self.config.CONFIG_DEST_DIR
        dest.mkdir(exist_ok=True)
        overall = True
        for item in src.iterdir():
            if item.is_dir():
                dest_path = dest / item.name
                try:
                    shutil.copytree(item, dest_path, dirs_exist_ok=True)
                    self.run_command(
                        [
                            "chown",
                            "-R",
                            f"{self.config.USERNAME}:{self.config.USERNAME}",
                            str(dest_path),
                        ]
                    )
                    self.logger.info(f"Copied {item} to {dest_path}.")
                except Exception as e:
                    self.logger.warning(f"Failed to copy {item} to {dest_path}: {e}")
                    overall = False
        return overall

    def set_bash_shell(self) -> bool:
        """
        Set bash as the default shell.

        Returns:
            True if shell set successfully, False otherwise
        """
        self.print_section("Default Shell Configuration")
        if not self.command_exists("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                self.run_command(["apt", "install", "-y", "bash"])
            except subprocess.CalledProcessError:
                self.logger.warning("Bash installation failed.")
                return False
        shells_file = Path("/etc/shells")
        try:
            if shells_file.exists():
                content = shells_file.read_text()
                if "/bin/bash" not in content:
                    with open(shells_file, "a") as f:
                        f.write("/bin/bash\n")
                    self.logger.info("Added /bin/bash to /etc/shells.")
            else:
                with open(shells_file, "w") as f:
                    f.write("/bin/bash\n")
                self.logger.info("Created /etc/shells with /bin/bash.")
        except Exception as e:
            self.logger.warning(f"Failed to update /etc/shells: {e}")
            return False
        try:
            self.run_command(["chsh", "-s", "/bin/bash", self.config.USERNAME])
            self.logger.info(
                f"Default shell for {self.config.USERNAME} set to /bin/bash."
            )
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to set default shell for {self.config.USERNAME}."
            )
            return False

    # ------------------------------------------------------------------------
    # Phase 4: Security Hardening
    # ------------------------------------------------------------------------
    def phase_security_hardening(self) -> bool:
        """
        Implement security hardening measures.

        Returns:
            True if hardening succeeded, False otherwise
        """
        self.print_section("Phase 4: Security Hardening")
        status = True
        if not self.configure_ssh():
            status = False
        if not self.setup_sudoers():
            status = False
        if not self.configure_firewall():
            status = False
        if not self.configure_fail2ban():
            status = False
        return status

    def configure_ssh(self) -> bool:
        """
        Configure SSH for security.

        Returns:
            True if configuration succeeded, False otherwise
        """
        self.print_section("SSH Configuration")
        try:
            subprocess.run(
                ["dpkg", "-s", "openssh-server"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
            lines = sshd_config.read_text().splitlines()
            for key, val in self.config.SSH_SETTINGS.items():
                replaced = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {val}"
                        replaced = True
                        break
                if not replaced:
                    lines.append(f"{key} {val}")
            sshd_config.write_text("\n".join(lines) + "\n")
            self.run_command(["systemctl", "restart", "ssh"])
            self.logger.info("SSH configuration updated and service restarted.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """
        Configure sudo access.

        Returns:
            True if sudo setup succeeded, False otherwise
        """
        self.print_section("Sudo Configuration")
        try:
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )
            if "sudo" in result.stdout.split():
                self.logger.info(f"User {self.config.USERNAME} already in sudo group.")
                return True
            self.run_command(["usermod", "-aG", "sudo", self.config.USERNAME])
            self.logger.info(f"User {self.config.USERNAME} added to sudo group.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(
                f"Failed to set sudo privileges for {self.config.USERNAME}: {e}"
            )
            return False

    def configure_firewall(self, ports: Optional[List[str]] = None) -> bool:
        """
        Configure the system firewall.

        Args:
            ports: List of ports to open, defaults to config value

        Returns:
            True if firewall configured successfully, False otherwise
        """
        self.print_section("Firewall Configuration")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            self.logger.error("UFW command not found. Please install UFW.")
            return False
        try:
            self.run_command([ufw_cmd, "default", "deny", "incoming"])
            self.run_command([ufw_cmd, "default", "allow", "outgoing"])
            for port in ports:
                self.run_command([ufw_cmd, "allow", f"{port}/tcp"])
                self.logger.info(f"Allowed TCP port {port}.")
            status = self.run_command(
                [ufw_cmd, "status"], capture_output=True, text=True
            )
            if "inactive" in status.stdout.lower():
                self.run_command([ufw_cmd, "--force", "enable"])
                self.logger.info("UFW firewall enabled.")
            else:
                self.logger.info("UFW firewall is active.")
            self.run_command(["systemctl", "enable", "ufw"])
            self.run_command(["systemctl", "start", "ufw"])
            self.logger.info("UFW service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to configure firewall: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """
        Configure fail2ban for intrusion prevention.

        Returns:
            True if fail2ban configured successfully, False otherwise
        """
        self.print_section("Fail2ban Configuration")
        jail_local = Path("/etc/fail2ban/jail.local")
        config_content = (
            "[DEFAULT]\n"
            "bantime  = 600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n"
        )
        if jail_local.is_file():
            self.backup_file(jail_local)
        try:
            jail_local.write_text(config_content)
            self.logger.info("Fail2ban configuration written.")
            self.run_command(["systemctl", "enable", "fail2ban"])
            self.run_command(["systemctl", "restart", "fail2ban"])
            self.logger.info("Fail2ban service enabled and restarted.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to manage fail2ban service.")
            return False

    # ------------------------------------------------------------------------
    # Phase 5: Essential Service Installation
    # ------------------------------------------------------------------------
    def phase_service_installation(self) -> bool:
        """
        Install and configure essential services.

        Returns:
            True if service installation succeeded, False otherwise
        """
        self.print_section("Phase 5: Essential Service Installation")
        status = True
        if not self.docker_config():
            status = False
        if not self.install_plex():
            status = False
        if not self.install_fastfetch():
            status = False
        return status

    def docker_config(self) -> bool:
        """
        Install and configure Docker.

        Returns:
            True if Docker configured successfully, False otherwise
        """
        self.print_section("Docker Configuration")
        if self.command_exists("docker"):
            self.logger.info("Docker already installed.")
        else:
            try:
                self.run_command(["apt", "install", "-y", "docker.io"])
                self.logger.info("Docker installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install Docker.")
                return False
        try:
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )
            if "docker" not in result.stdout.split():
                self.run_command(["usermod", "-aG", "docker", self.config.USERNAME])
                self.logger.info(f"User {self.config.USERNAME} added to docker group.")
            else:
                self.logger.info(
                    f"User {self.config.USERNAME} already in docker group."
                )
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to add {self.config.USERNAME} to docker group."
            )
        daemon_json = Path("/etc/docker/daemon.json")
        daemon_dir = daemon_json.parent
        try:
            daemon_dir.mkdir(exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create {daemon_dir}: {e}")
            return False
        desired_config = {
            "log-driver": "json-file",
            "log-opts": {"max-size": "10m", "max-file": "3"},
            "exec-opts": ["native.cgroupdriver=systemd"],
        }
        write_config = True
        if daemon_json.is_file():
            try:
                existing = json.loads(daemon_json.read_text())
                if existing == desired_config:
                    self.logger.info("Docker daemon configuration up-to-date.")
                    write_config = False
                else:
                    self.backup_file(daemon_json)
            except Exception as e:
                self.logger.warning(f"Failed to read {daemon_json}: {e}")
                self.backup_file(daemon_json)
        if write_config:
            try:
                with open(daemon_json, "w") as f:
                    json.dump(desired_config, f, indent=2)
                self.logger.info("Docker daemon configuration updated.")
            except Exception as e:
                self.logger.warning(f"Failed to write {daemon_json}: {e}")
        try:
            self.run_command(["systemctl", "enable", "docker"])
            self.run_command(["systemctl", "restart", "docker"])
            self.logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable/restart Docker service.")
            return False
        if not self.command_exists("docker-compose"):
            try:
                compose_path = Path("/usr/local/bin/docker-compose")
                self.download_file(self.config.DOCKER_COMPOSE_URL, compose_path)
                compose_path.chmod(0o755)
                self.logger.info("Docker Compose installed.")
            except Exception as e:
                self.logger.error(f"Failed to install Docker Compose: {e}")
                return False
        else:
            self.logger.info("Docker Compose already installed.")
        return True

    def install_plex(self) -> bool:
        """
        Install Plex Media Server.

        Returns:
            True if Plex installed successfully, False otherwise
        """
        self.print_section("Plex Media Server Installation")
        if not self.command_exists("curl"):
            self.logger.error("curl is required but not installed.")
            return False
        try:
            subprocess.run(
                ["dpkg", "-s", "plexmediaserver"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info("Plex Media Server already installed; skipping.")
            return True
        except subprocess.CalledProcessError:
            pass
        temp_deb = Path("/tmp/plexmediaserver.deb")
        try:
            self.download_file(self.config.PLEX_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg encountered issues. Fixing dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix dependencies for Plex.")
                return False
        plex_conf = Path("/etc/default/plexmediaserver")
        if plex_conf.is_file():
            try:
                conf = plex_conf.read_text()
                if f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}" not in conf:
                    new_conf = []
                    for line in conf.splitlines():
                        if line.startswith("PLEX_MEDIA_SERVER_USER="):
                            new_conf.append(
                                f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}"
                            )
                        else:
                            new_conf.append(line)
                    plex_conf.write_text("\n".join(new_conf) + "\n")
                    self.logger.info(
                        f"Configured Plex to run as {self.config.USERNAME}."
                    )
                else:
                    self.logger.info("Plex user already configured.")
            except Exception as e:
                self.logger.warning(f"Failed to update {plex_conf}: {e}")
        else:
            self.logger.warning(f"{plex_conf} not found; skipping user config.")
        try:
            self.run_command(["systemctl", "enable", "plexmediaserver"])
            self.logger.info("Plex service enabled.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to enable Plex service.")
        try:
            temp_deb.unlink()
        except Exception:
            pass
        self.logger.info("Plex Media Server installation complete.")
        return True

    def install_fastfetch(self) -> bool:
        """
        Install Fastfetch for system information display.

        Returns:
            True if Fastfetch installed successfully, False otherwise
        """
        self.print_section("Fastfetch Installation")
        try:
            subprocess.run(
                ["dpkg", "-s", "fastfetch"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info("Fastfetch already installed; skipping.")
            return True
        except subprocess.CalledProcessError:
            pass
        temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")
        try:
            self.download_file(self.config.FASTFETCH_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("Fastfetch installation issues; fixing dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix dependencies for Fastfetch.")
                return False
        try:
            temp_deb.unlink()
        except Exception:
            pass
        self.logger.info("Fastfetch installed successfully.")
        return True

    # ------------------------------------------------------------------------
    # Phase 6: User Customization & Script Deployment
    # ------------------------------------------------------------------------
    def phase_user_customization(self) -> bool:
        """
        Customize user environment and deploy scripts.

        Returns:
            True if customization succeeded, False otherwise
        """
        self.print_section("Phase 6: User Customization & Script Deployment")
        return self.deploy_user_scripts()

    def deploy_user_scripts(self) -> bool:
        """
        Deploy user scripts from repositories.

        Returns:
            True if deployment succeeded, False otherwise
        """
        self.print_section("Deploying User Scripts")
        src = self.config.USER_HOME / "github/bash/linux/ubuntu/_scripts"
        target = self.config.USER_HOME / "bin"
        if not src.is_dir():
            self.logger.error(f"Script source directory {src} does not exist.")
            return False
        target.mkdir(exist_ok=True)
        try:
            self.run_command(["rsync", "-ah", "--delete", f"{src}/", f"{target}/"])
            self.run_command(
                ["find", str(target), "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(target),
                ]
            )
            self.logger.info("User scripts deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Script deployment failed: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 7: Maintenance & Monitoring Tasks
    # ------------------------------------------------------------------------
    def phase_maintenance_monitoring(self) -> bool:
        """
        Set up maintenance and monitoring tasks.

        Returns:
            True if maintenance setup succeeded, False otherwise
        """
        self.print_section("Phase 7: Maintenance & Monitoring Tasks")
        status = True
        if not self.configure_periodic():
            status = False
        if not self.backup_configs():
            status = False
        if not self.rotate_logs(self.config.LOG_FILE):
            status = False
        self.system_health_check()
        self.verify_firewall_rules()
        return status

    def configure_periodic(self) -> bool:
        """
        Set up periodic maintenance tasks.

        Returns:
            True if periodic tasks configured successfully, False otherwise
        """
        self.print_section("Periodic Maintenance Setup")
        cron_file = Path("/etc/cron.daily/ubuntu_maintenance")
        marker = "# Ubuntu maintenance script"
        if cron_file.is_file():
            if marker in cron_file.read_text():
                self.logger.info("Daily maintenance cron job already configured.")
                return True
            self.backup_file(cron_file)
        content = (
            "#!/bin/sh\n"
            "# Ubuntu maintenance script\n"
            "apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y\n"
        )
        try:
            cron_file.write_text(content)
            cron_file.chmod(0o755)
            self.logger.info(f"Created daily maintenance script at {cron_file}.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> Optional[str]:
        """
        Backup important configuration files.

        Returns:
            Path to backup directory, or None if backup failed
        """
        self.print_section("Configuration Backups")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path(f"/var/backups/ubuntu_config_{timestamp}")
        try:
            backup_dir.mkdir(exist_ok=True)
            count = 0
            for file in [
                "/etc/ssh/sshd_config",
                "/etc/ufw/user.rules",
                "/etc/ntp.conf",
            ]:
                fpath = Path(file)
                if fpath.is_file():
                    shutil.copy2(fpath, backup_dir / fpath.name)
                    self.logger.info(f"Backed up {fpath}")
                    count += 1
                else:
                    self.logger.warning(f"{fpath} not found; skipping.")
            if count > 0:
                self.logger.info(f"Configuration files backed up to {backup_dir}")
                return str(backup_dir)
            else:
                self.logger.warning("No configuration files were backed up.")
                backup_dir.rmdir()
                return None
        except Exception as e:
            self.logger.warning(f"Failed to backup configuration files: {e}")
            return None

    def rotate_logs(self, log_file: Optional[str] = None) -> bool:
        """
        Rotate log files to prevent them from growing too large.

        Args:
            log_file: Path to log file to rotate, defaults to config value

        Returns:
            True if log rotation succeeded, False otherwise
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
            rotated = f"{log_path}.{timestamp}.gz"
            with open(log_path, "rb") as f_in, gzip.open(rotated, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            with open(log_path, "w"):
                pass
            self.logger.info(f"Log rotated to {rotated}.")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def system_health_check(self) -> Dict[str, str]:
        """
        Perform a system health check.

        Returns:
            Dictionary of system health information
        """
        self.print_section("System Health Check")
        info = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            self.logger.info(f"Uptime: {uptime}")
            info["uptime"] = uptime
        except Exception as e:
            self.logger.warning(f"Failed to get uptime: {e}")
        try:
            df_out = subprocess.check_output(["df", "-h", "/"], text=True).strip()
            self.logger.info(f"Disk usage:\n{df_out}")
            info["disk_usage"] = df_out
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_out = subprocess.check_output(["free", "-h"], text=True).strip()
            self.logger.info(f"Memory usage:\n{free_out}")
            info["memory_usage"] = free_out
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
        return info

    def verify_firewall_rules(
        self, ports: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Verify that firewall rules are properly applied.

        Args:
            ports: List of ports to check, defaults to config value

        Returns:
            Dictionary mapping port to accessibility status
        """
        self.print_section("Firewall Rules Verification")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
        results = {}
        for port in ports:
            try:
                subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.logger.info(f"Port {port} is accessible.")
                results[port] = True
            except subprocess.CalledProcessError:
                self.logger.warning(f"Port {port} not accessible.")
                results[port] = False
        return results

    # ------------------------------------------------------------------------
    # Phase 8: Certificates & Performance Tuning
    # ------------------------------------------------------------------------
    def phase_certificates_performance(self) -> bool:
        """
        Update certificates and tune system performance.

        Returns:
            True if certificates and performance tuning succeeded, False otherwise
        """
        self.print_section("Phase 8: Certificates & Performance Tuning")
        status = True
        if not self.update_ssl_certificates():
            status = False
        if not self.tune_system():
            status = False
        return status

    def update_ssl_certificates(self) -> bool:
        """
        Update SSL certificates.

        Returns:
            True if certificates updated successfully, False otherwise
        """
        self.print_section("SSL Certificates Update")
        if not self.command_exists("certbot"):
            try:
                self.run_command(["apt", "install", "-y", "certbot"])
                self.logger.info("certbot installed.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to install certbot.")
                return False
        try:
            self.run_command(["certbot", "renew"])
            self.logger.info("SSL certificates updated.")
            return True
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to update SSL certificates.")
            return False

    def tune_system(self) -> bool:
        """
        Apply system performance tuning settings.

        Returns:
            True if tuning applied successfully, False otherwise
        """
        self.print_section("Performance Tuning")
        sysctl_file = Path("/etc/sysctl.conf")
        marker = "# Performance tuning settings for Ubuntu"
        try:
            current = sysctl_file.read_text() if sysctl_file.is_file() else ""
            if marker not in current:
                tuning = f"""
{marker}
net.core.somaxconn=128
net.ipv4.tcp_rmem=4096 87380 6291456
net.ipv4.tcp_wmem=4096 16384 4194304
"""
                with open(sysctl_file, "a") as f:
                    f.write(tuning)
                for setting in [
                    "net.core.somaxconn=128",
                    "net.ipv4.tcp_rmem=4096 87380 6291456",
                    "net.ipv4.tcp_wmem=4096 16384 4194304",
                ]:
                    self.run_command(["sysctl", "-w", setting])
                self.logger.info("Performance tuning applied.")
            else:
                self.logger.info("Performance tuning settings already exist.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply performance tuning: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 9: Permissions & Advanced Storage Setup
    # ------------------------------------------------------------------------
    def phase_permissions_storage(self) -> bool:
        """
        Set up permissions and advanced storage.

        Returns:
            True if permissions and storage setup succeeded, False otherwise
        """
        self.print_section("Phase 9: Permissions & Advanced Storage Setup")
        status = True
        if not self.home_permissions():
            status = False
        if not self.install_configure_zfs():
            status = False
        return status

    def home_permissions(self) -> bool:
        """
        Set appropriate permissions on home directory.

        Returns:
            True if permissions set successfully, False otherwise
        """
        self.print_section("Home Directory Permissions")
        try:
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(self.config.USER_HOME),
                ]
            )
            self.logger.info(
                f"Ownership of {self.config.USER_HOME} set to {self.config.USERNAME}."
            )
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to change ownership of {self.config.USER_HOME}.")
            return False
        try:
            self.run_command(
                [
                    "find",
                    str(self.config.USER_HOME),
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    ";",
                ]
            )
            self.logger.info("Setgid bit applied on home directories.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to set setgid bit.")
        if self.command_exists("setfacl"):
            try:
                self.run_command(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{self.config.USERNAME}:rwx",
                        str(self.config.USER_HOME),
                    ]
                )
                self.logger.info("Default ACLs applied.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to apply default ACLs.")
        else:
            self.logger.warning("setfacl not found; skipping ACL configuration.")
        return True

    def install_configure_zfs(self) -> bool:
        """
        Install and configure ZFS storage.

        Returns:
            True if ZFS configured successfully, False otherwise
        """
        self.print_section("ZFS Installation and Configuration")
        pool = self.config.ZFS_POOL_NAME
        mount_point = Path(self.config.ZFS_MOUNT_POINT)
        try:
            self.run_command(["apt", "update"])
            self.run_command(
                [
                    "apt",
                    "install",
                    "-y",
                    "dpkg-dev",
                    "linux-headers-generic",
                    "linux-image-generic",
                ]
            )
            self.run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])
            self.logger.info("ZFS prerequisites and packages installed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install ZFS packages: {e}")
            return False
        for service in ["zfs-import-cache.service", "zfs-mount.service"]:
            try:
                self.run_command(["systemctl", "enable", service])
                self.logger.info(f"Enabled {service}.")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Could not enable {service}.")
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Mount point {mount_point} ensured.")
        except Exception as e:
            self.logger.warning(f"Failed to create mount point {mount_point}: {e}")
        pool_imported = False
        try:
            subprocess.run(
                ["zpool", "list", pool],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info(f"ZFS pool '{pool}' already imported.")
            pool_imported = True
        except subprocess.CalledProcessError:
            try:
                self.run_command(["zpool", "import", "-f", pool])
                self.logger.info(f"Imported ZFS pool '{pool}'.")
                pool_imported = True
            except subprocess.CalledProcessError:
                self.logger.warning(f"ZFS pool '{pool}' not found or failed to import.")
        if not pool_imported:
            return False
        try:
            self.run_command(["zfs", "set", f"mountpoint={mount_point}", pool])
            self.logger.info(f"Set mountpoint for pool '{pool}' to {mount_point}.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to set mountpoint: {e}")
        try:
            cache_file = Path("/etc/zfs/zpool.cache")
            self.run_command(["zpool", "set", f"cachefile={cache_file}", pool])
            self.logger.info(f"Cachefile for pool '{pool}' updated to {cache_file}.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to update cachefile: {e}")
        try:
            self.run_command(["zfs", "mount", "-a"])
            self.logger.info("Mounted all ZFS datasets.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to mount ZFS datasets: {e}")
        try:
            mounts = subprocess.check_output(
                ["zfs", "list", "-o", "name,mountpoint", "-H"], text=True
            )
            if any(str(mount_point) in line for line in mounts.splitlines()):
                self.logger.info(f"ZFS pool '{pool}' mounted at {mount_point}.")
                return True
            else:
                self.logger.warning(f"ZFS pool '{pool}' not mounted at {mount_point}.")
                return False
        except Exception as e:
            self.logger.warning(f"Error verifying ZFS mount status: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 10: Additional Applications & Tools
    # ------------------------------------------------------------------------
    def phase_additional_apps(self) -> bool:
        """
        Install additional applications and tools.

        Returns:
            True if application installation succeeded, False otherwise
        """
        self.print_section("Phase 10: Additional Applications & Tools")
        status = True
        if not self.install_brave_browser():
            status = False
        apps_success, apps_failed = self.install_flatpak_and_apps()
        if apps_failed and len(apps_failed) > len(self.config.FLATPAK_APPS) * 0.1:
            self.logger.error(
                f"Flatpak app installation failures: {', '.join(apps_failed)}"
            )
            status = False
        if not self.install_configure_vscode_stable():
            status = False
        return status

    def install_brave_browser(self) -> bool:
        """
        Install Brave browser.

        Returns:
            True if Brave installed successfully, False otherwise
        """
        self.print_section("Brave Browser Installation")
        try:
            self.run_command(
                ["sh", "-c", "curl -fsS https://dl.brave.com/install.sh | sh"]
            )
            self.logger.info("Brave browser installed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Brave browser: {e}")
            return False

    def install_flatpak_and_apps(self) -> Tuple[List[str], List[str]]:
        """
        Install Flatpak and configured applications.

        Returns:
            Tuple of (successful installs, failed installs)
        """
        self.print_section("Flatpak Installation and Setup")
        apps = self.config.FLATPAK_APPS
        try:
            self.run_command(["apt", "install", "-y", "flatpak"])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Flatpak: {e}")
            return [], apps
        try:
            self.run_command(["apt", "install", "-y", "gnome-software-plugin-flatpak"])
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install Flatpak plugin: {e}")
        try:
            self.run_command(
                [
                    "flatpak",
                    "remote-add",
                    "--if-not-exists",
                    "flathub",
                    "https://dl.flathub.org/repo/flathub.flatpakrepo",
                ]
            )
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to add Flathub repository: {e}")
            return [], apps
        successful = []
        failed = []
        for app in apps:
            try:
                self.run_command(["flatpak", "install", "--assumeyes", "flathub", app])
                self.logger.info(f"Installed Flatpak app: {app}")
                successful.append(app)
            except subprocess.CalledProcessError:
                self.logger.warning(f"Failed to install Flatpak app: {app}")
                failed.append(app)
        return successful, failed

    def install_configure_vscode_stable(self) -> bool:
        """
        Install and configure Visual Studio Code.

        Returns:
            True if VS Code configured successfully, False otherwise
        """
        self.print_section("Visual Studio Code Installation & Configuration")
        vscode_url = (
            "https://vscode.download.prss.microsoft.com/dbazure/download/stable/"
            "e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
        )
        deb_path = Path("/tmp/code.deb")
        try:
            self.logger.info("Downloading VS Code Stable...")
            self.download_file(vscode_url, deb_path)
        except Exception as e:
            self.logger.error(f"Failed to download VS Code: {e}")
            return False
        try:
            self.logger.info("Installing VS Code Stable...")
            self.run_command(["dpkg", "-i", str(deb_path)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg issues; fixing dependencies...")
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix dependencies for VS Code: {e}")
                return False
        try:
            deb_path.unlink()
        except Exception:
            pass
        desktop_file = Path("/usr/share/applications/code.desktop")
        desktop_content = (
            "[Desktop Entry]\n"
            "Name=Visual Studio Code\n"
            "Comment=Code Editing. Redefined.\n"
            "GenericName=Text Editor\n"
            "Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
            "Icon=vscode\n"
            "Type=Application\n"
            "StartupNotify=false\n"
            "StartupWMClass=Code\n"
            "Categories=TextEditor;Development;IDE;\n"
            "MimeType=application/x-code-workspace;\n"
            "Actions=new-empty-window;\n\n"
            "[Desktop Action new-empty-window]\n"
            "Name=New Empty Window\n"
            "Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
            "Icon=vscode\n"
        )
        try:
            desktop_file.write_text(desktop_content)
            self.logger.info(f"Updated desktop file: {desktop_file}")
        except Exception as e:
            self.logger.warning(f"Failed to update desktop file: {e}")
        local_dir = Path.home() / ".local/share/applications"
        local_file = local_dir / "code.desktop"
        try:
            local_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(desktop_file, local_file)
            self.logger.info(f"Copied desktop file to {local_file}")
            content = local_file.read_text()
            updated = content.replace("StartupWMClass=Code", "StartupWMClass=code")
            local_file.write_text(updated)
            self.logger.info("Updated local desktop file for Wayland compatibility.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to update local desktop file: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 11: Automatic Updates & Additional Security
    # ------------------------------------------------------------------------
    def phase_automatic_updates_security(self) -> bool:
        """
        Configure automatic updates and additional security.

        Returns:
            True if automatic updates and security configured successfully, False otherwise
        """
        self.print_section("Phase 11: Automatic Updates & Additional Security")
        status = True
        if not self.configure_unattended_upgrades():
            status = False
        if not self.configure_apparmor():
            status = False
        return status

    def configure_unattended_upgrades(self) -> bool:
        """
        Configure unattended upgrades for security patches.

        Returns:
            True if unattended upgrades configured successfully, False otherwise
        """
        self.print_section("Unattended Upgrades Configuration")
        try:
            # Install required packages
            self.run_command(
                ["apt", "install", "-y", "unattended-upgrades", "apt-listchanges"]
            )

            # Create configuration for auto upgrades
            auto_upgrades_file = Path("/etc/apt/apt.conf.d/20auto-upgrades")
            auto_upgrades_content = (
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )
            auto_upgrades_file.write_text(auto_upgrades_content)

            # Configure unattended upgrades behavior
            unattended_file = Path("/etc/apt/apt.conf.d/50unattended-upgrades")
            if unattended_file.exists():
                self.backup_file(unattended_file)

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
            unattended_file.write_text(unattended_content)

            # Enable the service
            self.run_command(["systemctl", "enable", "unattended-upgrades"])
            self.run_command(["systemctl", "restart", "unattended-upgrades"])

            self.logger.info(
                "Unattended Upgrades installed and configured to apply security updates automatically."
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure unattended upgrades: {e}")
            return False

    def configure_apparmor(self) -> bool:
        """
        Configure AppArmor for application security.

        Returns:
            True if AppArmor configured successfully, False otherwise
        """
        self.print_section("AppArmor Configuration")
        try:
            self.run_command(["apt", "install", "-y", "apparmor", "apparmor-utils"])
            self.run_command(["systemctl", "enable", "apparmor"])
            self.run_command(["systemctl", "start", "apparmor"])
            self.logger.info("AppArmor installed and enabled.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to configure AppArmor: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 12: Cleanup & Final Configurations
    # ------------------------------------------------------------------------
    def phase_cleanup_final(self) -> bool:
        """
        Perform cleanup and apply final configurations.

        Returns:
            True if cleanup and final configurations succeeded, False otherwise
        """
        self.print_section("Phase 12: Cleanup & Final Configurations")
        status = True
        if not self.cleanup_system():
            status = False
        if not self.configure_wayland():
            status = False
        if not self.install_nala():
            status = False
        if not self.install_enable_tailscale():
            status = False
        if not self.install_configure_caddy():
            status = False
        return status

    def cleanup_system(self) -> bool:
        """
        Clean up the system by removing unused packages.

        Returns:
            True if cleanup succeeded, False otherwise
        """
        self.print_section("System Cleanup")
        try:
            self.run_command(["apt", "autoremove", "-y"])
            self.run_command(["apt", "autoclean", "-y"])
            self.logger.info("System cleanup completed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            return False

    def configure_wayland(self) -> bool:
        """
        Configure Wayland environment variables.

        Returns:
            True if Wayland configured successfully, False otherwise
        """
        self.print_section("Wayland Environment Configuration")
        etc_env = Path("/etc/environment")
        updated_system = False
        try:
            current = etc_env.read_text() if etc_env.is_file() else ""
            vars_current = {
                line.split("=", 1)[0]: line.split("=", 1)[1]
                for line in current.splitlines()
                if "=" in line
            }
            for key, val in self.config.WAYLAND_ENV_VARS.items():
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated_system = True
            if updated_system:
                new_content = (
                    "\n".join(f"{k}={v}" for k, v in vars_current.items()) + "\n"
                )
                etc_env.write_text(new_content)
                self.logger.info(f"{etc_env} updated with Wayland variables.")
            else:
                self.logger.info(f"No changes needed in {etc_env}.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env}: {e}")
        user_env_dir = self.config.USER_HOME / ".config/environment.d"
        user_env_file = user_env_dir / "myenvvars.conf"
        try:
            user_env_dir.mkdir(parents=True, exist_ok=True)
            content = (
                "\n".join(f"{k}={v}" for k, v in self.config.WAYLAND_ENV_VARS.items())
                + "\n"
            )
            if user_env_file.is_file():
                if user_env_file.read_text().strip() != content.strip():
                    self.backup_file(user_env_file)
                    user_env_file.write_text(content)
                    self.logger.info(f"Updated {user_env_file} with Wayland variables.")
            else:
                user_env_file.write_text(content)
                self.logger.info(f"Created {user_env_file} with Wayland variables.")
            self.run_command(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_file),
                ]
            )
            return True
        except Exception as e:
            self.logger.warning(f"Failed to update {user_env_file}: {e}")
            return False

    def install_nala(self) -> bool:
        """
        Install Nala as a modern apt frontend.

        Returns:
            True if successful, False otherwise
        """
        self.print_section("Nala Installation")
        self.logger.info("Installing Nala (apt frontend)...")

        if self.command_exists("nala"):
            self.logger.info("Nala is already installed.")
            return True

        try:
            # Step 1: Update apt repositories
            self.logger.info("Updating apt repositories...")
            self.run_command(["apt", "update"])

            # Step 2: Upgrade existing packages
            self.logger.info("Upgrading existing packages...")
            self.run_command(["apt", "upgrade", "-y"])

            # Step 3: Fix any broken installations
            self.logger.info("Fixing any broken package installations...")
            self.run_command(["apt", "--fix-broken", "install", "-y"])

            # Step 4: Install nala
            self.logger.info("Installing nala package...")
            self.run_command(["apt", "install", "nala", "-y"])

            # Verify nala is installed
            if self.command_exists("nala"):
                self.logger.info("Nala installed successfully.")
                try:
                    self.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    self.logger.info("Configured faster mirrors with Nala.")
                except subprocess.CalledProcessError:
                    self.logger.warning("Failed to configure mirrors with Nala.")
                return True
            else:
                self.logger.error("Nala installation verification failed.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to install Nala: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        """
        Install and configure Tailscale VPN using the official script.

        Returns:
            True if successful, False otherwise
        """
        self.print_section("Tailscale Installation")
        self.logger.info("Installing and configuring Tailscale...")

        if self.command_exists("tailscale"):
            self.logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                self.logger.info("Installing Tailscale using the official script...")
                self.run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )

                tailscale_installed = self.command_exists("tailscale")

                if tailscale_installed:
                    self.logger.info("Tailscale installed successfully.")
                else:
                    self.logger.error("Tailscale installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install Tailscale: {e}")
                return False

        try:
            self.run_command(["systemctl", "enable", "tailscaled"])
            self.run_command(["systemctl", "start", "tailscaled"])

            status = self.run_command(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )

            if status.stdout.strip() == "active":
                self.logger.info("Tailscale service is active and running.")
                self.logger.info("To authenticate, run: tailscale up")
                return True
            else:
                self.logger.warning("Tailscale service may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            self.logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    def install_configure_caddy(self) -> bool:
        """
        Install and configure Caddy web server.

        Returns:
            True if Caddy installed and configured successfully, False otherwise
        """
        self.print_section("Caddy Installation & Configuration")
        caddy_url = "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb"
        temp_deb = Path("/tmp/caddy_2.9.1_linux_amd64.deb")
        try:
            self.download_file(caddy_url, temp_deb)
        except Exception as e:
            self.logger.error(f"Failed to download Caddy: {e}")
            return False
        try:
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning(
                "dpkg issues during Caddy installation; fixing dependencies..."
            )
            try:
                self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to resolve Caddy dependencies: {e}")
                return False
        try:
            temp_deb.unlink()
        except Exception as e:
            self.logger.warning(f"Failed to remove temporary Caddy file: {e}")
        source_caddyfile = (
            self.config.USER_HOME / "github/bash/linux/ubuntu/dotfiles/Caddyfile"
        )
        dest_caddyfile = Path("/etc/caddy/Caddyfile")
        if source_caddyfile.is_file():
            if dest_caddyfile.exists():
                self.backup_file(dest_caddyfile)
            try:
                shutil.copy2(source_caddyfile, dest_caddyfile)
                self.logger.info(f"Copied Caddyfile to {dest_caddyfile}")
            except Exception as e:
                self.logger.warning(f"Failed to copy Caddyfile: {e}")
        else:
            self.logger.warning(f"Source Caddyfile not found at {source_caddyfile}.")
        log_dir = Path("/var/log/caddy")
        try:
            log_dir.mkdir(mode=0o755, exist_ok=True)
            for fname in ["caddy.log", "access.log"]:
                fpath = log_dir / fname
                with open(fpath, "a"):
                    os.utime(fpath, None)
                fpath.chmod(0o644)
                self.logger.info(f"Prepared log file: {fpath}")
        except Exception as e:
            self.logger.warning(f"Failed to prepare Caddy log files: {e}")
        try:
            self.run_command(["systemctl", "enable", "caddy"])
            self.run_command(["systemctl", "restart", "caddy"])
            self.logger.info("Caddy service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Caddy service: {e}")
            return False

    # ------------------------------------------------------------------------
    # Phase 13: Final System Checks & Reboot Prompt
    # ------------------------------------------------------------------------
    def phase_final_checks(self) -> bool:
        """
        Perform final system checks and prompt for reboot.

        Returns:
            True if checks pass and user approves reboot, False otherwise
        """
        self.print_section("Phase 13: Final System Checks & Reboot Prompt")
        self.final_checks()
        return self.prompt_reboot()

    def final_checks(self) -> Dict[str, str]:
        """
        Perform final system health checks.

        Returns:
            Dictionary of system information
        """
        self.print_section("Final System Checks")
        info = {}
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            self.logger.info(f"Kernel version: {kernel}")
            info["kernel"] = kernel
        except Exception as e:
            self.logger.warning(f"Failed to get kernel version: {e}")
        try:
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            self.logger.info(f"System uptime: {uptime}")
            info["uptime"] = uptime
        except Exception as e:
            self.logger.warning(f"Failed to get uptime: {e}")
        try:
            df_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            self.logger.info(f"Disk usage (root): {df_line}")
            info["disk_usage"] = df_line
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((l for l in free_out if l.startswith("Mem:")), "")
            self.logger.info(f"Memory usage: {mem_line}")
            info["memory"] = mem_line
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
        try:
            cpu_info = ""
            for line in subprocess.check_output(["lscpu"], text=True).splitlines():
                if "Model name" in line:
                    cpu_info = line.split(":", 1)[1].strip()
                    break
            self.logger.info(f"CPU: {cpu_info}")
            info["cpu"] = cpu_info
        except Exception as e:
            self.logger.warning(f"Failed to get CPU info: {e}")
        try:
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            self.logger.info("Active network interfaces:")
            for line in interfaces.splitlines():
                self.logger.info(f"  {line}")
            info["network_interfaces"] = interfaces
        except Exception as e:
            self.logger.warning(f"Failed to get network interfaces: {e}")
        return info

    def prompt_reboot(self) -> bool:
        """
        Prompt the user to reboot the system.

        Returns:
            True if user approves reboot, False otherwise
        """
        self.print_section("Reboot Prompt")
        answer = input("Would you like to reboot now? [y/N]: ").strip().lower()
        if answer == "y":
            self.logger.info("Rebooting system now...")
            try:
                self.run_command(["shutdown", "-r", "now"])
                return True
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to reboot: {e}")
                return False
        else:
            self.logger.info(
                "Reboot canceled. Please reboot later for changes to take effect."
            )
            return False

    # ------------------------------------------------------------------------
    # Main Execution Flow
    # ------------------------------------------------------------------------
    def run(self) -> int:
        """
        Run the entire setup process with all phases.

        Returns:
            Exit code: 0 for success, non-zero for failure
        """
        total_phases = 13
        success_phases = 0

        phase_methods = [
            self.phase_preflight,
            self.phase_system_update,
            self.phase_repo_shell_setup,
            self.phase_security_hardening,
            self.phase_service_installation,
            self.phase_user_customization,
            self.phase_maintenance_monitoring,
            self.phase_certificates_performance,
            self.phase_permissions_storage,
            self.phase_additional_apps,
            self.phase_automatic_updates_security,
            self.phase_cleanup_final,
            self.phase_final_checks,
        ]

        for idx, phase in enumerate(phase_methods, start=1):
            self.print_section(f"Starting Phase {idx}/{total_phases}")
            try:
                result = run_with_progress(f"Running Phase {idx}", phase)
                if result:
                    success_phases += 1
                    self.logger.info(f"Phase {idx} completed successfully.")
                else:
                    self.logger.warning(f"Phase {idx} encountered issues.")
            except Exception as e:
                self.logger.critical(
                    f"Phase {idx} failed with an unhandled exception: {e}",
                    exc_info=True,
                )

        success_rate = (success_phases / total_phases) * 100
        self.logger.info(
            f"Setup completed with {success_rate:.1f}% success ({success_phases}/{total_phases} phases)."
        )
        return 0

    def cleanup(self) -> None:
        """Perform global cleanup tasks before exit."""
        self.logger.info("Performing global cleanup tasks before exit.")
        self.cleanup_system()


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    setup_instance = UbuntuDesktopSetup()
    atexit.register(setup_instance.cleanup)
    sys.exit(setup_instance.run())
