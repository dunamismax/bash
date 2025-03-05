#!/usr/bin/env python3
"""
Ubuntu Desktop Setup & Hardening Utility (Unattended)
-------------------------------------------------------

This fully automated utility performs:
  • Pre-flight checks & backups (including ZFS snapshot)
  • System update & basic configuration (timezone, packages)
  • Repository & shell setup (cloning GitHub repos, updating shell configs)
  • Security hardening (SSH, sudoers, firewall, Fail2ban)
  • Essential service installations (Docker, Plex, Fastfetch, Brave, VS Code)
  • User customization & script deployment
  • Maintenance tasks (cron job, log rotation, configuration backups)
  • Certificates & performance tuning (SSL renewals, sysctl tweaks)
  • Permissions & advanced storage configuration (home permissions, ZFS)
  • Additional applications (Flatpak apps, VS Code configuration)
  • Automatic updates & further security (unattended upgrades, AppArmor)
  • Final system checks & reboot

Run this script with root privileges.
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
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
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.logging import RichHandler
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.text import Text
    from rich.columns import Columns
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"]
        )
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print(
            "Please install the required packages manually: pip install rich pyfiglet"
        )
        sys.exit(1)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
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


nord_theme = Theme(
    {
        "banner": f"bold {NordColors.FROST_2}",
        "header": f"bold {NordColors.FROST_2}",
        "info": NordColors.GREEN,
        "warning": NordColors.YELLOW,
        "error": NordColors.RED,
        "debug": NordColors.FROST_3,
        "success": NordColors.GREEN,
    }
)

console = Console(theme=nord_theme)

# ----------------------------------------------------------------
# Setup Status Tracking
# ----------------------------------------------------------------
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "repo_shell": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "user_custom": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "certs_perf": {"status": "pending", "message": ""},
    "permissions_storage": {"status": "pending", "message": ""},
    "additional_apps": {"status": "pending", "message": ""},
    "auto_updates": {"status": "pending", "message": ""},
    "cleanup_final": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Config:
    PLEX_VERSION: str = "1.41.4.9463-630c9f557"
    FASTFETCH_VERSION: str = "2.37.0"
    DOCKER_COMPOSE_VERSION: str = "2.20.2"
    LOG_FILE: str = "/var/log/ubuntu_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path(f"/home/sawyer"))
    ZFS_POOL_NAME: str = "WD_BLACK"
    ZFS_MOUNT_POINT: Path = field(default_factory=lambda: Path("/media/WD_BLACK"))
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
    WAYLAND_ENV_VARS: Dict[str, str] = field(
        default_factory=lambda: {
            "GDK_BACKEND": "wayland",
            "QT_QPA_PLATFORM": "wayland",
            "SDL_VIDEODRIVER": "wayland",
        }
    )
    GITHUB_REPOS: List[str] = field(
        default_factory=lambda: ["bash", "windows", "web", "python", "go", "misc"]
    )
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
    FIREWALL_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443", "32400"]
    )
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
        self.PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{self.PLEX_VERSION}/debian/plexmediaserver_{self.PLEX_VERSION}_amd64.deb"
        self.FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{self.FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"
        self.DOCKER_COMPOSE_URL = f"https://github.com/docker/compose/releases/download/v{self.DOCKER_COMPOSE_VERSION}/{platform.system()}-{platform.machine()}"
        self.CONFIG_SRC_DIR = (
            self.USER_HOME / "github" / "bash" / "linux" / "ubuntu" / "dotfiles"
        )
        self.CONFIG_DEST_DIR = self.USER_HOME / ".config"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header(title: str) -> Panel:
    """
    Generate an ASCII art header with dynamic gradient styling using Pyfiglet.
    """
    fonts = ["slant", "small", "digital", "mini", "smslant"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(title)
            if ascii_art.strip():
                break
        except Exception:
            continue

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    border = f"[{NordColors.FROST_3}]{'━' * 80}[/]"
    styled_text = border + "\n" + styled_text + border

    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=f"{NordColors.FROST_1}",
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]Ubuntu Setup & Hardening[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]Unattended Mode[/]",
        subtitle_align="center",
    )
    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message in a styled Rich panel."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=f"{style}",
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_status_report() -> None:
    """
    Print the current status of all setup phases.
    """
    table = Table(title="Setup Status Report", style="banner")
    table.add_column("Task", style="header")
    table.add_column("Status", style="info")
    table.add_column("Message", style="info")

    for key, data in SETUP_STATUS.items():
        status_color = {
            "pending": "debug",
            "in_progress": "warning",
            "success": "success",
            "failed": "error",
        }.get(data["status"].lower(), "info")

        table.add_row(
            key.replace("_", " ").title(),
            f"[{status_color}]{data['status'].upper()}[/{status_color}]",
            data["message"],
        )

    console.print(
        Panel(
            table,
            title="[banner]Ubuntu Setup Status[/banner]",
            border_style=NordColors.FROST_3,
        )
    )


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    # Remove pre-existing handlers
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Console handler
    console_handler = RichHandler(console=console, rich_tracebacks=True)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(str(log_file), 0o600)
    except Exception as e:
        logger.warning(f"Could not set permissions on log file {log_file}: {e}")

    return logger


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def signal_handler(signum, frame):
    sig = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger = logging.getLogger("ubuntu_setup")
    logger.error(f"Script interrupted by {sig}. Initiating cleanup.")
    try:
        setup_instance.cleanup()
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


def cleanup_temp_files() -> None:
    logger = logging.getLogger("ubuntu_setup")
    logger.info("Cleaning up temporary files.")
    tmp = Path(tempfile.gettempdir())
    for item in tmp.iterdir():
        if item.name.startswith("ubuntu_setup_"):
            try:
                item.unlink() if item.is_file() else shutil.rmtree(item)
            except Exception:
                pass


atexit.register(cleanup_temp_files)


# ----------------------------------------------------------------
# Task Running Utilities
# ----------------------------------------------------------------
def run_with_progress(
    description: str, func, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """Run a function with progress indication."""
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }

    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold {task.fields[status_color]}]{task.description}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_id = progress.add_task(
            description, total=None, status_color=NordColors.FROST_2
        )

        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start

            # Update progress
            progress.update(task_id, completed=100, status_color=NordColors.GREEN)
            progress.stop_task(task_id)

            # Log success
            console.print(
                f"[success]✓ {description} completed in {elapsed:.2f}s[/success]"
            )

            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "success",
                    "message": f"Completed in {elapsed:.2f}s",
                }
            return result

        except Exception as e:
            elapsed = time.time() - start

            # Update progress to show failure
            progress.update(task_id, completed=100, status_color=NordColors.RED)
            progress.stop_task(task_id)

            # Log error
            console.print(
                f"[error]✗ {description} failed in {elapsed:.2f}s: {e}[/error]"
            )

            if task_name:
                SETUP_STATUS[task_name] = {
                    "status": "failed",
                    "message": f"Failed after {elapsed:.2f}s: {str(e)}",
                }
            raise


# ----------------------------------------------------------------
# Main Setup Class
# ----------------------------------------------------------------
class UbuntuDesktopSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self.nala_installed = False

    def print_section(self, title: str) -> None:
        """Print a section header using Pyfiglet ASCII art."""
        console.print(create_header(title))
        self.logger.info(f"--- {title} ---")

    # ----------------------------------------------------------------
    # Phase 0: Install Nala
    # ----------------------------------------------------------------
    def phase_install_nala(self) -> bool:
        """First phase: Install Nala package manager."""
        self.print_section("Install Nala")
        try:
            if self.command_exists("nala"):
                self.logger.info("Nala is already installed.")
                self.nala_installed = True
                return True

            self.logger.info("Installing Nala package manager...")
            self.run_command(["apt", "update", "-qq"])
            self.run_command(["apt", "install", "nala", "-y"])

            if self.command_exists("nala"):
                self.logger.info("Nala installed successfully.")
                self.nala_installed = True

                # Configure faster mirrors
                try:
                    self.logger.info("Configuring faster mirrors with Nala...")
                    self.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    self.logger.info("Mirrors configured successfully.")
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to configure mirrors: {e}")

                return True
            else:
                self.logger.error("Nala installation verification failed.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to install Nala: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 1: Pre-flight Checks & Backups
    # ----------------------------------------------------------------
    def phase_preflight(self) -> bool:
        self.print_section("Pre-flight Checks & Backups")
        try:
            run_with_progress(
                "Checking for root privileges", self.check_root, task_name="preflight"
            )
            run_with_progress(
                "Checking network connectivity",
                self.check_network,
                task_name="preflight",
            )
            run_with_progress(
                "Saving configuration snapshot",
                self.save_config_snapshot,
                task_name="preflight",
            )
            run_with_progress(
                "Creating system ZFS snapshot",
                self.create_system_zfs_snapshot,
                task_name="preflight",
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            return False

    def check_root(self) -> None:
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root.")
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    def has_internet_connection(self) -> bool:
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
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity. Please check your settings.")
            sys.exit(1)

    def save_config_snapshot(self) -> Optional[str]:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot_file = backup_dir / f"config_snapshot_{timestamp}.tar.gz"
        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                files_added = 0
                for cfg in self.config.CONFIG_BACKUP_FILES:
                    cfg_path = Path(cfg)
                    if cfg_path.is_file():
                        tar.add(str(cfg_path), arcname=cfg_path.name)
                        self.logger.info(f"Included {cfg_path} in snapshot.")
                        files_added += 1
                    else:
                        self.logger.debug(f"{cfg_path} not found; skipping.")
                if files_added:
                    self.logger.info(f"Configuration snapshot saved: {snapshot_file}")
                    return str(snapshot_file)
                else:
                    self.logger.warning("No configuration files found for snapshot.")
                    return None
        except Exception as e:
            self.logger.warning(f"Failed to create config snapshot: {e}")
            return None

    def create_system_zfs_snapshot(self) -> Optional[str]:
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

    # ----------------------------------------------------------------
    # Phase 2: System Update & Basic Configuration
    # ----------------------------------------------------------------
    def phase_system_update(self) -> bool:
        self.print_section("System Update & Basic Configuration")
        status = True
        if not run_with_progress(
            "Updating system", self.update_system, task_name="system_update"
        ):
            status = False
        success, failed = self.install_packages()
        if failed and len(failed) > len(self.config.PACKAGES) * 0.1:
            self.logger.error(f"Failed packages: {', '.join(failed)}")
            status = False
        if not run_with_progress(
            "Configuring timezone", self.configure_timezone, task_name="system_update"
        ):
            status = False
        return status

    def update_system(self) -> bool:
        try:
            self.logger.info("Updating package repositories...")
            if self.nala_installed:
                self.run_command(["nala", "update", "-y"])
                self.logger.info("Upgrading system packages with Nala...")
                self.run_command(["nala", "upgrade", "-y"])
            else:
                self.run_command(["apt", "update", "-qq"])
                self.logger.info("Upgrading system packages with apt...")
                self.run_command(["apt", "upgrade", "-y"])

            self.logger.info("System update and upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System update failed: {e}")
            return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
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
                self.logger.debug(f"Package already installed: {pkg}")
                success.append(pkg)
            except subprocess.CalledProcessError:
                missing.append(pkg)

        if missing:
            self.logger.info(f"Installing missing packages: {' '.join(missing)}")
            try:
                if self.nala_installed:
                    self.run_command(["nala", "install", "-y"] + missing)
                else:
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
            self.logger.error(f"Failed to set timezone: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 3: Repository & Shell Setup
    # ----------------------------------------------------------------
    def phase_repo_shell_setup(self) -> bool:
        self.print_section("Repository & Shell Setup")
        status = True
        if not run_with_progress(
            "Setting up GitHub repositories", self.setup_repos, task_name="repo_shell"
        ):
            status = False
        if not run_with_progress(
            "Copying shell configurations", self.copy_shell_configs
        ):
            status = False
        if not run_with_progress(
            "Copying configuration folders", self.copy_config_folders
        ):
            status = False
        if not run_with_progress("Setting default shell to bash", self.set_bash_shell):
            status = False
        return status

    def setup_repos(self) -> bool:
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)
        all_success = True

        for repo in self.config.GITHUB_REPOS:
            repo_dir = gh_dir / repo
            if (repo_dir / ".git").is_dir():
                self.logger.info(f"Repository '{repo}' exists; pulling updates...")
                try:
                    self.run_command(["git", "-C", str(repo_dir), "pull"])
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to update repository '{repo}'.")
                    all_success = False
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
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to clone repository '{repo}'.")
                    all_success = False

        try:
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(gh_dir),
                ]
            )
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set ownership of {gh_dir}.")
            all_success = False

        return all_success

    def copy_shell_configs(self) -> bool:
        source_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "ubuntu" / "dotfiles"
        )
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
                        if dest.is_file():
                            self.backup_file(dest)
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
        src = self.config.CONFIG_SRC_DIR
        dest = self.config.CONFIG_DEST_DIR
        dest.mkdir(exist_ok=True)
        overall = True

        try:
            for item in src.iterdir():
                if item.is_dir():
                    dest_path = dest / item.name
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

            return overall
        except Exception as e:
            self.logger.error(f"Error copying config folders: {e}")
            return False

    def set_bash_shell(self) -> bool:
        if not self.command_exists("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                if self.nala_installed:
                    self.run_command(["nala", "install", "-y", "bash"])
                else:
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

    # ----------------------------------------------------------------
    # Phase 4: Security Hardening
    # ----------------------------------------------------------------
    def phase_security_hardening(self) -> bool:
        self.print_section("Security Hardening")
        status = True
        if not run_with_progress(
            "Configuring SSH", self.configure_ssh, task_name="security"
        ):
            status = False
        if not run_with_progress("Setting up sudoers", self.setup_sudoers):
            status = False
        if not run_with_progress("Configuring firewall", self.configure_firewall):
            status = False
        if not run_with_progress("Configuring Fail2ban", self.configure_fail2ban):
            status = False
        return status

    def configure_ssh(self) -> bool:
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
                if self.nala_installed:
                    self.run_command(["nala", "install", "-y", "openssh-server"])
                else:
                    self.run_command(["apt", "install", "-y", "openssh-server"])
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
                f"Failed to configure sudoers for {self.config.USERNAME}: {e}"
            )
            return False

    def configure_firewall(self, ports: Optional[List[str]] = None) -> bool:
        if ports is None:
            ports = self.config.FIREWALL_PORTS

        ufw_cmd = "/usr/sbin/ufw"
        if not (Path(ufw_cmd).is_file() and os.access(ufw_cmd, os.X_OK)):
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

    # ----------------------------------------------------------------
    # Phase 5: Service Installation
    # ----------------------------------------------------------------
    def phase_service_installation(self) -> bool:
        self.print_section("Essential Service Installation")
        status = True
        if not run_with_progress(
            "Configuring Docker", self.docker_config, task_name="services"
        ):
            status = False
        if not run_with_progress(
            "Installing Plex Media Server", self.install_plex, task_name="services"
        ):
            status = False
        if not run_with_progress(
            "Installing Fastfetch", self.install_fastfetch, task_name="services"
        ):
            status = False
        return status

    def docker_config(self) -> bool:
        if self.command_exists("docker"):
            self.logger.info("Docker already installed.")
        else:
            try:
                if self.nala_installed:
                    self.run_command(["nala", "install", "-y", "docker.io"])
                else:
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
        daemon_json.parent.mkdir(exist_ok=True)
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
                daemon_json.write_text(json.dumps(desired_config, indent=2))
                self.logger.info("Docker daemon configuration updated.")
            except Exception as e:
                self.logger.warning(f"Failed to write {daemon_json}: {e}")

        try:
            self.run_command(["systemctl", "enable", "docker"])
            self.run_command(["systemctl", "restart", "docker"])
            self.logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Docker service: {e}")
            return False

        if not self.command_exists("docker-compose"):
            try:
                dest = Path("/usr/local/bin/docker-compose")
                self.download_file(self.config.DOCKER_COMPOSE_URL, dest)
                dest.chmod(0o755)
                self.logger.info("Docker Compose installed.")
            except Exception as e:
                self.logger.error(f"Failed to install Docker Compose: {e}")
                return False
        else:
            self.logger.info("Docker Compose already installed.")

        return True

    def install_plex(self) -> bool:
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
            self.logger.warning("dpkg issues with Plex; fixing dependencies...")
            try:
                if self.nala_installed:
                    self.run_command(["nala", "install", "-f", "-y"])
                else:
                    self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Plex dependencies.")
                return False

        plex_conf = Path("/etc/default/plexmediaserver")
        if plex_conf.is_file():
            try:
                conf = plex_conf.read_text()
                if f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}" not in conf:
                    new_conf = [
                        f"PLEX_MEDIA_SERVER_USER={self.config.USERNAME}"
                        if line.startswith("PLEX_MEDIA_SERVER_USER=")
                        else line
                        for line in conf.splitlines()
                    ]
                    plex_conf.write_text("\n".join(new_conf) + "\n")
                    self.logger.info(
                        f"Configured Plex to run as {self.config.USERNAME}."
                    )
                else:
                    self.logger.info("Plex user already configured.")
            except Exception as e:
                self.logger.warning(f"Failed to update {plex_conf}: {e}")
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

        self.logger.info("Plex Media Server installation complete.")
        return True

    def install_fastfetch(self) -> bool:
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
                if self.nala_installed:
                    self.run_command(["nala", "install", "-f", "-y"])
                else:
                    self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Fastfetch dependencies.")
                return False

        try:
            temp_deb.unlink()
        except Exception:
            pass

        self.logger.info("Fastfetch installed successfully.")
        return True

    # ----------------------------------------------------------------
    # Phase 6: User Customization & Script Deployment
    # ----------------------------------------------------------------
    def phase_user_customization(self) -> bool:
        self.print_section("User Customization & Script Deployment")
        return run_with_progress(
            "Deploying user scripts", self.deploy_user_scripts, task_name="user_custom"
        )

    def deploy_user_scripts(self) -> bool:
        src = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "ubuntu" / "_scripts"
        )
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

    # ----------------------------------------------------------------
    # Phase 7: Maintenance & Monitoring
    # ----------------------------------------------------------------
    def phase_maintenance_monitoring(self) -> bool:
        self.print_section("Maintenance & Monitoring Tasks")
        status = True
        if not run_with_progress(
            "Configuring periodic maintenance",
            self.configure_periodic,
            task_name="maintenance",
        ):
            status = False
        if not run_with_progress("Backing up configuration files", self.backup_configs):
            status = False
        if not run_with_progress("Rotating logs", self.rotate_logs):
            status = False
        run_with_progress("Performing system health check", self.system_health_check)
        run_with_progress("Verifying firewall rules", self.verify_firewall_rules)
        return status

    def configure_periodic(self) -> bool:
        cron_file = Path("/etc/cron.daily/ubuntu_maintenance")
        marker = "# Ubuntu maintenance script"

        if cron_file.is_file() and marker in cron_file.read_text():
            self.logger.info("Daily maintenance cron job already configured.")
            return True

        if cron_file.is_file():
            self.backup_file(cron_file)

        # Use nala if installed
        pkg_mgr = "nala" if self.nala_installed else "apt"
        content = f"#!/bin/sh\n{marker}\n{pkg_mgr} update -qq && {pkg_mgr} upgrade -y && {pkg_mgr} autoremove -y && {pkg_mgr} autoclean -y\n"

        try:
            cron_file.write_text(content)
            cron_file.chmod(0o755)
            self.logger.info(f"Created daily maintenance script at {cron_file}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> Optional[str]:
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

            if count:
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

            open(log_path, "w").close()
            self.logger.info(f"Log rotated to {rotated}")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def system_health_check(self) -> Dict[str, str]:
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

    # ----------------------------------------------------------------
    # Phase 8: Certificates & Performance Tuning
    # ----------------------------------------------------------------
    def phase_certificates_performance(self) -> bool:
        self.print_section("Certificates & Performance Tuning")
        status = True
        if not run_with_progress(
            "Updating SSL certificates",
            self.update_ssl_certificates,
            task_name="certs_perf",
        ):
            status = False
        if not run_with_progress(
            "Applying performance tuning", self.tune_system, task_name="certs_perf"
        ):
            status = False
        return status

    def update_ssl_certificates(self) -> bool:
        if not self.command_exists("certbot"):
            try:
                if self.nala_installed:
                    self.run_command(["nala", "install", "-y", "certbot"])
                else:
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
        sysctl_file = Path("/etc/sysctl.conf")
        marker = "# Performance tuning settings for Ubuntu"

        try:
            current = sysctl_file.read_text() if sysctl_file.is_file() else ""
            if marker not in current:
                tuning = f"\n{marker}\nnet.core.somaxconn=128\nnet.ipv4.tcp_rmem=4096 87380 6291456\nnet.ipv4.tcp_wmem=4096 16384 4194304\n"
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

    # ----------------------------------------------------------------
    # Phase 9: Permissions & Advanced Storage Setup
    # ----------------------------------------------------------------
    def phase_permissions_storage(self) -> bool:
        self.print_section("Permissions & Advanced Storage Setup")
        status = True
        if not run_with_progress(
            "Configuring home directory permissions",
            self.home_permissions,
            task_name="permissions_storage",
        ):
            status = False
        if not run_with_progress(
            "Installing & Configuring ZFS",
            self.install_configure_zfs,
            task_name="permissions_storage",
        ):
            status = False
        return status

    def home_permissions(self) -> bool:
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
                self.logger.info("Default ACLs applied on home directory.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to apply default ACLs.")
        else:
            self.logger.warning("setfacl not found; skipping ACL configuration.")

        return True

    def install_configure_zfs(self) -> bool:
        pool = self.config.ZFS_POOL_NAME
        mount_point = self.config.ZFS_MOUNT_POINT

        try:
            if self.nala_installed:
                self.run_command(
                    ["nala", "install", "-y", "zfs-dkms", "zfsutils-linux"]
                )
            else:
                self.run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"])
            self.logger.info("ZFS packages installed.")
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

    # ----------------------------------------------------------------
    # Phase 10: Additional Applications & Tools
    # ----------------------------------------------------------------
    def phase_additional_apps(self) -> bool:
        self.print_section("Additional Applications & Tools")
        status = True
        if not run_with_progress(
            "Installing Brave browser",
            self.install_brave_browser,
            task_name="additional_apps",
        ):
            status = False

        apps_success, apps_failed = self.install_flatpak_and_apps()
        if apps_failed and len(apps_failed) > len(self.config.FLATPAK_APPS) * 0.1:
            self.logger.error(
                f"Flatpak app installation failures: {', '.join(apps_failed)}"
            )
            status = False

        if not run_with_progress(
            "Installing VS Code Stable",
            self.install_configure_vscode_stable,
            task_name="additional_apps",
        ):
            status = False

        return status

    def install_brave_browser(self) -> bool:
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
        try:
            if self.nala_installed:
                self.run_command(["nala", "install", "-y", "flatpak"])
            else:
                self.run_command(["apt", "install", "-y", "flatpak"])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Flatpak: {e}")
            return [], self.config.FLATPAK_APPS

        try:
            if self.nala_installed:
                self.run_command(
                    ["nala", "install", "-y", "gnome-software-plugin-flatpak"]
                )
            else:
                self.run_command(
                    ["apt", "install", "-y", "gnome-software-plugin-flatpak"]
                )
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
            return [], self.config.FLATPAK_APPS

        successful = []
        failed = []

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[status_color]}]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                "Installing Flatpak apps...",
                total=len(self.config.FLATPAK_APPS),
                status_color=NordColors.FROST_2,
            )

            for i, app in enumerate(self.config.FLATPAK_APPS):
                progress.update(
                    task_id,
                    description=f"Installing {app}...",
                    completed=i,
                    status_color=NordColors.FROST_2,
                )

                try:
                    self.run_command(
                        ["flatpak", "install", "--assumeyes", "flathub", app]
                    )
                    self.logger.info(f"Installed Flatpak app: {app}")
                    successful.append(app)
                    progress.update(task_id, status_color=NordColors.GREEN)
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to install Flatpak app: {app}")
                    failed.append(app)
                    progress.update(task_id, status_color=NordColors.RED)

            progress.update(
                task_id,
                completed=len(self.config.FLATPAK_APPS),
                description=f"Installed {len(successful)}/{len(self.config.FLATPAK_APPS)} Flatpak apps",
            )

        return successful, failed

    def install_configure_vscode_stable(self) -> bool:
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
                if self.nala_installed:
                    self.run_command(["nala", "install", "-f", "-y"])
                else:
                    self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix VS Code dependencies: {e}")
                return False

        try:
            deb_path.unlink()
        except Exception:
            pass

        desktop_file = Path("/usr/share/applications/code.desktop")
        desktop_content = (
            "[Desktop Entry]\nName=Visual Studio Code\nComment=Code Editing. Redefined.\n"
            "GenericName=Text Editor\nExec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
            "Icon=vscode\nType=Application\nStartupNotify=false\nStartupWMClass=Code\nCategories=TextEditor;Development;IDE;\n"
            "MimeType=application/x-code-workspace;\nActions=new-empty-window;\n\n"
            "[Desktop Action new-empty-window]\nName=New Empty Window\nExec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F\nIcon=vscode\n"
        )

        try:
            desktop_file.write_text(desktop_content)
            self.logger.info(f"Updated desktop file: {desktop_file}")
        except Exception as e:
            self.logger.warning(f"Failed to update desktop file: {e}")

        local_dir = self.config.USER_HOME / ".local" / "share" / "applications"
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

    # ----------------------------------------------------------------
    # Phase 11: Automatic Updates & Additional Security
    # ----------------------------------------------------------------
    def phase_automatic_updates_security(self) -> bool:
        self.print_section("Automatic Updates & Additional Security")
        status = True
        if not run_with_progress(
            "Configuring unattended upgrades",
            self.configure_unattended_upgrades,
            task_name="auto_updates",
        ):
            status = False
        if not run_with_progress(
            "Configuring AppArmor", self.configure_apparmor, task_name="auto_updates"
        ):
            status = False
        return status

    def configure_unattended_upgrades(self) -> bool:
        try:
            if self.nala_installed:
                self.run_command(
                    ["nala", "install", "-y", "unattended-upgrades", "apt-listchanges"]
                )
            else:
                self.run_command(
                    ["apt", "install", "-y", "unattended-upgrades", "apt-listchanges"]
                )

            auto_file = Path("/etc/apt/apt.conf.d/20auto-upgrades")
            auto_file.write_text(
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )

            unattended_file = Path("/etc/apt/apt.conf.d/50unattended-upgrades")
            if unattended_file.exists():
                self.backup_file(unattended_file)

            unattended_file.write_text(
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

            self.run_command(["systemctl", "enable", "unattended-upgrades"])
            self.run_command(["systemctl", "restart", "unattended-upgrades"])
            self.logger.info("Unattended upgrades configured successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure unattended upgrades: {e}")
            return False

    def configure_apparmor(self) -> bool:
        try:
            if self.nala_installed:
                self.run_command(
                    ["nala", "install", "-y", "apparmor", "apparmor-utils"]
                )
            else:
                self.run_command(["apt", "install", "-y", "apparmor", "apparmor-utils"])

            self.run_command(["systemctl", "enable", "apparmor"])
            self.run_command(["systemctl", "start", "apparmor"])
            self.logger.info("AppArmor installed and enabled.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to configure AppArmor: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 12: Cleanup & Final Configurations
    # ----------------------------------------------------------------
    def phase_cleanup_final(self) -> bool:
        self.print_section("Cleanup & Final Configurations")
        status = True
        if not run_with_progress(
            "Cleaning up system", self.cleanup_system, task_name="cleanup_final"
        ):
            status = False
        if not run_with_progress(
            "Configuring Wayland environment",
            self.configure_wayland,
            task_name="cleanup_final",
        ):
            status = False
        if not run_with_progress(
            "Installing and enabling Tailscale",
            self.install_enable_tailscale,
            task_name="cleanup_final",
        ):
            status = False
        if not run_with_progress(
            "Installing & configuring Caddy",
            self.install_configure_caddy,
            task_name="cleanup_final",
        ):
            status = False
        return status

    def cleanup_system(self) -> bool:
        try:
            if self.nala_installed:
                self.run_command(["nala", "autoremove", "-y"])
                self.run_command(["nala", "clean", "-y"])
            else:
                self.run_command(["apt", "autoremove", "-y"])
                self.run_command(["apt", "autoclean", "-y"])

            self.logger.info("System cleanup completed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            return False

    def configure_wayland(self) -> bool:
        etc_env = Path("/etc/environment")
        try:
            current = etc_env.read_text() if etc_env.is_file() else ""
            vars_current = {
                line.split("=", 1)[0]: line.split("=", 1)[1]
                for line in current.splitlines()
                if "=" in line
            }
            updated = False

            for key, val in self.config.WAYLAND_ENV_VARS.items():
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True

            if updated:
                new_content = (
                    "\n".join(f"{k}={v}" for k, v in vars_current.items()) + "\n"
                )
                etc_env.write_text(new_content)
                self.logger.info(f"{etc_env} updated with Wayland variables.")
            else:
                self.logger.info(f"No changes needed in {etc_env}.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env}: {e}")

        user_env_dir = self.config.USER_HOME / ".config" / "environment.d"
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

    def install_enable_tailscale(self) -> bool:
        self.logger.info("Installing and configuring Tailscale...")

        if self.command_exists("tailscale"):
            self.logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                self.logger.info("Installing Tailscale using official script...")
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
                self.logger.info("Tailscale service is active.")
                return True
            else:
                self.logger.warning("Tailscale service may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            self.logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    def install_configure_caddy(self) -> bool:
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
                if self.nala_installed:
                    self.run_command(["nala", "install", "-f", "-y"])
                else:
                    self.run_command(["apt", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to resolve Caddy dependencies: {e}")
                return False

        try:
            temp_deb.unlink()
        except Exception as e:
            self.logger.warning(f"Failed to remove temporary Caddy file: {e}")

        source_caddyfile = (
            self.config.USER_HOME
            / "github"
            / "bash"
            / "linux"
            / "ubuntu"
            / "dotfiles"
            / "Caddyfile"
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

    # ----------------------------------------------------------------
    # Phase 13: Final Checks & Reboot
    # ----------------------------------------------------------------
    def phase_final_checks(self) -> bool:
        self.print_section("Final System Checks")
        info = self.final_checks()

        # Display summary of what was done
        self.print_section("Setup Complete")
        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        summary = f"""
        ✅ Ubuntu Setup & Hardening completed successfully!
        
        ⏱️ Total runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s
        
        System Information:
        • Kernel: {info.get("kernel", "Unknown")}
        • CPU: {info.get("cpu", "Unknown")}
        • Disk Usage: {info.get("disk_usage", "Unknown").split("\n")[0] if isinstance(info.get("disk_usage"), str) else "Unknown"}
        • Memory: {info.get("memory", "Unknown").split("\n")[0] if isinstance(info.get("memory"), str) else "Unknown"}
        
        The system will automatically reboot in 10 seconds to apply all changes.
        """

        display_panel(summary, style=NordColors.GREEN, title="Success")
        print_status_report()

        # Automatic reboot in unattended mode
        self.logger.info("Scheduling automatic reboot in 10 seconds...")
        self.run_command(["shutdown", "-r", "+1"], check=False)
        return True

    def final_checks(self) -> Dict[str, str]:
        """
        Perform final system checks and collect system information.
        """
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
                self.logger.info(line)
            info["network_interfaces"] = interfaces
        except Exception as e:
            self.logger.warning(f"Failed to get network interfaces: {e}")

        return info

    # ----------------------------------------------------------------
    # Helper Methods
    # ----------------------------------------------------------------
    def command_exists(self, cmd: str) -> bool:
        """Check if a command exists and is executable."""
        try:
            subprocess.run(
                ["which", cmd],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def run_command(
        self,
        cmd: List[str],
        capture_output: bool = False,
        text: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a system command with logging."""
        cmd_str = " ".join(cmd)
        self.logger.debug(f"Running command: {cmd_str}")
        result = subprocess.run(
            cmd, capture_output=capture_output, text=text, check=check
        )
        return result

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Create a backup of a file with timestamp."""
        file_path = Path(file_path)
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak.{timestamp}")
        try:
            shutil.copy2(file_path, backup_path)
            self.logger.debug(f"Backed up {file_path} to {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.warning(f"Failed to backup {file_path}: {e}")
            return None

    def download_file(
        self, url: str, dest: Union[str, Path], timeout: int = 300
    ) -> None:
        """Download a file from URL to destination with progress tracking."""
        dest = Path(dest)
        if dest.exists():
            self.logger.info(f"File {dest} already exists; skipping download.")
            return

        self.logger.info(f"Downloading {url} to {dest}...")

        with Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[status_color]}]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            task_id = progress.add_task(
                f"Downloading {Path(url).name}",
                total=None,
                status_color=NordColors.FROST_2,
            )

            try:
                # First try with wget if available
                if self.command_exists("wget"):
                    self.run_command(
                        ["wget", "-q", "--show-progress", url, "-O", str(dest)]
                    )
                # Fall back to curl
                elif self.command_exists("curl"):
                    self.run_command(["curl", "-#", "-L", url, "-o", str(dest)])
                # Fall back to Python's urllib
                else:
                    import urllib.request

                    urllib.request.urlretrieve(url, dest)

                progress.update(task_id, completed=100, status_color=NordColors.GREEN)
                self.logger.info(f"Download complete: {dest}")
            except Exception as e:
                progress.update(task_id, completed=100, status_color=NordColors.RED)
                self.logger.error(f"Download failed: {e}")
                raise

    def cleanup(self) -> None:
        """Clean up temporary files and restore backups if needed."""
        self.logger.info("Performing cleanup before exit...")
        try:
            # Remove temporary files
            tmp = Path(tempfile.gettempdir())
            for item in tmp.glob("ubuntu_setup_*"):
                try:
                    item.unlink() if item.is_file() else shutil.rmtree(item)
                except Exception as e:
                    self.logger.warning(f"Failed to clean up {item}: {e}")

            # Final log rotation
            try:
                self.rotate_logs()
            except Exception as e:
                self.logger.warning(f"Failed to rotate logs: {e}")

            self.logger.info("Cleanup completed.")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")


# ----------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------
def main() -> None:
    """Main function to run the setup script."""
    console.print(create_header("Ubuntu Setup & Hardening"))

    try:
        setup = UbuntuDesktopSetup()
        global setup_instance
        setup_instance = setup

        # Check for root permissions first
        setup.check_root()

        # Start with Nala installation
        setup.phase_install_nala()

        # Execute all setup phases sequentially
        phases = [
            ("Pre-flight Checks & Backups", setup.phase_preflight),
            ("System Update & Basic Configuration", setup.phase_system_update),
            ("Repository & Shell Setup", setup.phase_repo_shell_setup),
            ("Security Hardening", setup.phase_security_hardening),
            ("Essential Service Installation", setup.phase_service_installation),
            ("User Customization & Script Deployment", setup.phase_user_customization),
            ("Maintenance & Monitoring Tasks", setup.phase_maintenance_monitoring),
            ("Certificates & Performance Tuning", setup.phase_certificates_performance),
            ("Permissions & Advanced Storage Setup", setup.phase_permissions_storage),
            ("Additional Applications & Tools", setup.phase_additional_apps),
            (
                "Automatic Updates & Additional Security",
                setup.phase_automatic_updates_security,
            ),
            ("Cleanup & Final Configurations", setup.phase_cleanup_final),
            ("Final System Checks", setup.phase_final_checks),
        ]

        # Track overall success
        overall_success = True

        # Execute each phase
        for name, phase_func in phases:
            try:
                SETUP_STATUS[phase_func.__name__.replace("phase_", "")] = {
                    "status": "in_progress",
                    "message": f"Phase {name} started",
                }

                console.print(f"\n[header]Running Phase: {name}[/header]\n")
                success = phase_func()

                if success:
                    console.print(
                        f"[success]✓ Phase {name} completed successfully[/success]"
                    )
                    SETUP_STATUS[phase_func.__name__.replace("phase_", "")] = {
                        "status": "success",
                        "message": f"Completed successfully",
                    }
                else:
                    console.print(
                        f"[warning]⚠ Phase {name} completed with warnings[/warning]"
                    )
                    SETUP_STATUS[phase_func.__name__.replace("phase_", "")] = {
                        "status": "warning",
                        "message": f"Completed with warnings",
                    }
                    overall_success = False

            except Exception as e:
                console.print(f"[error]✗ Phase {name} failed: {e}[/error]")
                SETUP_STATUS[phase_func.__name__.replace("phase_", "")] = {
                    "status": "failed",
                    "message": f"Failed: {str(e)}",
                }
                overall_success = False
                setup.logger.error(
                    f"Phase {name} failed with exception: {e}", exc_info=True
                )

                # Continue with next phase despite failure
                continue

        # Set final status
        SETUP_STATUS["final"] = {
            "status": "success" if overall_success else "warning",
            "message": "Setup completed successfully"
            if overall_success
            else "Setup completed with issues",
        }

    except KeyboardInterrupt:
        console.print("\n[warning]Setup interrupted by user.[/warning]")
        try:
            setup_instance.cleanup()
        except Exception as e:
            console.print(f"[error]Cleanup after interruption failed: {e}[/error]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[error]Fatal error: {e}[/error]")
        try:
            if "setup_instance" in globals():
                setup_instance.cleanup()
        except Exception as cleanup_error:
            console.print(f"[error]Cleanup after error failed: {cleanup_error}[/error]")
        sys.exit(1)


if __name__ == "__main__":
    try:
        setup_instance = None  # Initialize global instance variable
        main()
    except Exception as e:
        console.print_exception()
        sys.exit(1)
