#!/usr/bin/env python3
"""
Debian Trixie Setup & Hardening Utility (Unattended)
-------------------------------------------------------

This fully automated utility performs:
  • Pre-flight checks & backups (including ZFS snapshot if available)
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
  • Final system checks & automated reboot

Run this script with root privileges.
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
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Set, Callable

# ----------------------------------------------------------------
# Import Required Libraries and Install if Missing
# ----------------------------------------------------------------
def ensure_dependencies():
    """Install required dependencies if they're missing."""
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
            print("Successfully installed required packages. Restarting script...")
            # Restart the script to ensure imports work
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install required packages: {e}")
            print(
                "Please install them manually: pip install "
                + " ".join(missing_packages)
            )
            sys.exit(1)

ensure_dependencies()

import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

# ----------------------------------------------------------------
# Global Console, Theme & Status Setup
# ----------------------------------------------------------------
nord_theme = Theme(
    {
        "banner": "bold #88C0D0",
        "header": "bold #88C0D0",
        "info": "#A3BE8C",
        "warning": "#EBCB8B",
        "error": "#BF616A",
        "debug": "#81A1C1",
        "success": "#A3BE8C",
    }
)
console = Console(theme=nord_theme)

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
# Helper Functions: Status Report & Progress
# ----------------------------------------------------------------
def print_status_report() -> None:
    """Print current status of all setup tasks."""
    table = Table(title="Debian Trixie Setup Status Report", style="banner")
    table.add_column("Task", style="header")
    table.add_column("Status", style="info")
    table.add_column("Message", style="info")
    for key, data in SETUP_STATUS.items():
        status_style = {
            "success": "success",
            "failed": "error",
            "in_progress": "warning",
            "pending": "debug"
        }.get(data["status"].lower(), "info")
        table.add_row(
            key.replace("_", " ").title(), 
            f"[{status_style}]{data['status'].upper()}[/{status_style}]", 
            data["message"]
        )
    console.print(table)


def run_with_progress(
    description: str, func: Callable, *args, task_name: Optional[str] = None, **kwargs
) -> Any:
    """Run a function with live progress tracking."""
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }

    console.print(f"[bold]▶ Starting: {description}...[/bold]")
    start = time.time()
    
    with Progress(
        SpinnerColumn(style="bold #88C0D0"),
        TextColumn("[bold #88C0D0]{task.description}"),
        BarColumn(complete_style="#A3BE8C", finished_style="#A3BE8C"),
        TextColumn("[#ECEFF4]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        expand=True
    ) as progress:
        task = progress.add_task(description, total=100)
        
        # Use a thread to update progress while the function runs
        def progress_updater():
            while not progress.tasks[task].finished:
                progress.update(task, advance=0.5)
                time.sleep(0.1)
                
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_updater = executor.submit(progress_updater)
            future_result = executor.submit(func, *args, **kwargs)
            
            try:
                result = future_result.result()
                # Mark task as complete
                progress.update(task, completed=100)
                elapsed = time.time() - start
                console.print(f"[success]✓ {description} completed in {elapsed:.2f}s[/success]")
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "success",
                        "message": f"{description} completed successfully.",
                    }
                return result
            except Exception as e:
                # Mark task as failed
                progress.update(task, completed=100)
                elapsed = time.time() - start
                console.print(f"[error]✗ {description} failed in {elapsed:.2f}s: {e}[/error]")
                if task_name:
                    SETUP_STATUS[task_name] = {
                        "status": "failed",
                        "message": f"{description} failed: {e}",
                    }
                raise


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    """Configure and return a logger with rich formatting."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("debian_setup")
    logger.setLevel(logging.DEBUG)
    # Remove pre-existing handlers
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    handler = RichHandler(console=console, rich_tracebacks=True)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    
    # Add file handler for persistent logging
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        os.chmod(str(log_file), 0o600)
    except Exception as e:
        logger.warning(f"Could not set up file logging to {log_file}: {e}")
    
    return logger


# ----------------------------------------------------------------
# Signal Handling & Cleanup of Temp Files
# ----------------------------------------------------------------
def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    sig = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.getLogger("debian_setup").error(
        f"Script interrupted by {sig}. Initiating cleanup."
    )
    try:
        setup_instance.cleanup()
    except Exception as e:
        logging.getLogger("debian_setup").error(
            f"Error during cleanup after signal: {e}"
        )
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
    """Remove temporary files created during execution."""
    logging.getLogger("debian_setup").info("Cleaning up temporary files.")
    tmp = Path(tempfile.gettempdir())
    for item in tmp.iterdir():
        if item.name.startswith("debian_setup_"):
            try:
                item.unlink() if item.is_file() else shutil.rmtree(item)
            except Exception:
                pass


atexit.register(cleanup_temp_files)


# ----------------------------------------------------------------
# Configuration Dataclass
# ----------------------------------------------------------------
@dataclass
class Config:
    """Configuration settings for the Debian setup script."""
    PLEX_VERSION: str = "1.41.4.9463-630c9f557"
    FASTFETCH_VERSION: str = "2.37.0"
    DOCKER_COMPOSE_VERSION: str = "2.20.2"
    LOG_FILE: str = "/var/log/debian_setup.log"
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
            "mariadb-client",
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
    DEBIAN_REPOS: Dict[str, Dict[str, Dict[str, List[str]]]] = field(
        default_factory=lambda: {
            "default": {
                "sources": {
                    "deb https://deb.debian.org/debian": ["trixie", "main", "contrib", "non-free-firmware"],
                    "deb https://security.debian.org/debian-security": ["trixie-security", "main", "contrib", "non-free-firmware"],
                    "deb https://deb.debian.org/debian": ["trixie-updates", "main", "contrib", "non-free-firmware"],
                }
            },
            "mirrors": {
                "sources": {
                    "deb http://mirrors.kernel.org/debian": ["trixie", "main", "contrib", "non-free-firmware"],
                    "deb http://security.debian.org/debian-security": ["trixie-security", "main", "contrib", "non-free-firmware"],
                    "deb http://mirrors.kernel.org/debian": ["trixie-updates", "main", "contrib", "non-free-firmware"],
                }
            },
            "local": {
                "sources": {
                    "deb file:/var/local/debian": ["trixie", "main", "contrib", "non-free-firmware"],
                }
            }
        }
    )

    def __post_init__(self):
        self.PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{self.PLEX_VERSION}/debian/plexmediaserver_{self.PLEX_VERSION}_amd64.deb"
        self.FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{self.FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"
        self.DOCKER_COMPOSE_URL = f"https://github.com/docker/compose/releases/download/v{self.DOCKER_COMPOSE_VERSION}/{platform.system()}-{platform.machine()}"
        self.CONFIG_SRC_DIR = (
            self.USER_HOME / "github" / "bash" / "linux" / "debian" / "dotfiles"
        )
        self.CONFIG_DEST_DIR = self.USER_HOME / ".config"


# ----------------------------------------------------------------
# Main Setup Class
# ----------------------------------------------------------------
class DebianTrixieSetup:
    """Main class to handle the Debian Trixie setup and hardening process."""
    
    def __init__(self, config: Config = Config()):
        """Initialize the setup with configuration and logger."""
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self.logger.info("Debian Trixie Setup started")

    def print_section(self, title: str) -> None:
        """Print a section header with Pyfiglet ASCII art."""
        try:
            banner = pyfiglet.figlet_format(title, font="slant")
            console.print(Panel(banner, style="header"))
            self.logger.info(f"--- {title} ---")
        except Exception as e:
            # Fallback if Pyfiglet fails
            console.print(Panel(f"[bold header]{title}[/]"))
            self.logger.info(f"--- {title} --- (Pyfiglet error: {e})")

    # Phase 1: Pre-flight Checks & Backups
    def phase_preflight(self) -> bool:
        self.print_section("Phase 1: Pre-flight Checks & Backups")
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
                "Creating system ZFS snapshot if available",
                self.create_system_zfs_snapshot,
                task_name="preflight",
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            return False

    def check_root(self) -> None:
        """Verify the script is running with root privileges."""
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root.")
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    def has_internet_connection(self) -> bool:
        """Check if the system has internet connectivity."""
        try:
            result = self.run_command(
                ["ping", "-c", "1", "-W", "5", "8.8.8.8"],
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_network(self) -> None:
        """Verify network connectivity."""
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity. Please check your settings.")
            sys.exit(1)

    def save_config_snapshot(self) -> Optional[str]:
        """Create a backup of important configuration files."""
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
        """Create a ZFS snapshot if ZFS is available on the system."""
        try:
            # Check if ZFS is installed and available
            result = self.run_command(["zfs", "version"], capture_output=True, check=False)
            if result.returncode != 0:
                self.logger.info("ZFS not available on this system; skipping snapshot.")
                return None
                
            system_dataset = "rpool/ROOT/debian"
            try:
                self.run_command(["zfs", "list", system_dataset], capture_output=True)
                self.logger.info(f"Dataset '{system_dataset}' found.")
            except subprocess.CalledProcessError:
                system_dataset = "rpool"
                self.logger.warning("Dataset 'rpool/ROOT/debian' not found; using 'rpool'.")
                
                try:
                    self.run_command(["zfs", "list", system_dataset], capture_output=True)
                    self.logger.info(f"Dataset '{system_dataset}' found.")
                except subprocess.CalledProcessError:
                    self.logger.warning("No suitable ZFS root dataset found; skipping snapshot.")
                    return None
                
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            snapshot_name = f"{system_dataset}@backup_{timestamp}"
            try:
                self.run_command(["zfs", "snapshot", snapshot_name])
                self.logger.info(f"Created ZFS snapshot: {snapshot_name}")
                return snapshot_name
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to create ZFS snapshot: {e}")
                return None
        except Exception as e:
            self.logger.warning(f"Error checking ZFS: {e}")
            return None

    # Phase 2: System Update & Basic Configuration
    def phase_system_update(self) -> bool:
        self.print_section("Phase 2: System Update & Basic Configuration")
        status = True
        
        # Configure Debian repositories first
        if not run_with_progress(
            "Configuring Debian repositories", 
            self.configure_debian_repos, 
            task_name="system_update"
        ):
            status = False
            
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

    def configure_debian_repos(self, repo_type: str = "default") -> bool:
        """Configure Debian repositories according to specified type."""
        self.print_section("Debian Repository Configuration")
        
        # Validate repo_type
        if repo_type not in self.config.DEBIAN_REPOS:
            self.logger.warning(f"Unknown repository type '{repo_type}'; using default")
            repo_type = "default"
            
        self.logger.info(f"Configuring Debian repositories using '{repo_type}' configuration")
        
        # Backup existing sources.list
        sources_file = Path("/etc/apt/sources.list")
        if sources_file.exists():
            self.backup_file(sources_file)
            self.logger.info("Backed up existing sources.list")
        
        # Write new sources.list
        try:
            repo_config = self.config.DEBIAN_REPOS[repo_type]["sources"]
            content = "# Debian Trixie repositories configured by setup script\n"
            content += f"# Configuration type: {repo_type}\n"
            content += "# Date: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n"
            
            for base_url, entries in repo_config.items():
                for suite in entries[0:1]:  # First entry is the suite
                    components = " ".join(entries[1:])  # Rest are components
                    content += f"{base_url} {suite} {components}\n"
            
            # Add security and updates repositories
            sources_file.write_text(content)
            self.logger.info(f"Updated {sources_file} with {repo_type} repositories")
            
            # Create sources.list.d directory if it doesn't exist
            sources_dir = Path("/etc/apt/sources.list.d")
            sources_dir.mkdir(exist_ok=True)
            
            # Update package lists
            self.run_command(["apt-get", "update", "-qq"])
            self.logger.info("Updated package lists with new repositories")
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure repositories: {e}")
            return False

    def update_system(self) -> bool:
        """Update and upgrade the Debian system."""
        self.print_section("System Update & Upgrade")
        try:
            self.logger.info("Updating package repositories...")
            self.run_command(["apt-get", "update", "-qq"])
            self.logger.info("Upgrading system packages...")
            self.run_command(["apt-get", "upgrade", "-y"])
            self.logger.info("System update and upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System update failed: {e}")
            return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
        """Install required packages defined in the configuration."""
        self.print_section("Essential Package Installation")
        self.logger.info("Checking for required packages...")
        missing = []
        success = []
        failed = []
        
        for pkg in self.config.PACKAGES:
            try:
                result = subprocess.run(
                    ["dpkg-query", "-W", "-f='${Status}'", pkg],
                    check=False,
                    capture_output=True,
                    text=True
                )
                if "install ok installed" in result.stdout:
                    self.logger.debug(f"Package already installed: {pkg}")
                    success.append(pkg)
                else:
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)
                
        if missing:
            self.logger.info(f"Installing missing packages: {' '.join(missing)}")
            
            # Install packages in smaller batches to prevent too-long command lines
            batch_size = 20
            for i in range(0, len(missing), batch_size):
                batch = missing[i:i+batch_size]
                try:
                    self.run_command(["apt-get", "install", "-y"] + batch)
                    success.extend(batch)
                    self.logger.info(f"Installed batch of {len(batch)} packages")
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to install package batch: {e}")
                    
                    # Check which packages in this batch were actually installed
                    for pkg in batch:
                        try:
                            result = subprocess.run(
                                ["dpkg-query", "-W", "-f='${Status}'", pkg],
                                check=False,
                                capture_output=True,
                                text=True
                            )
                            if "install ok installed" in result.stdout:
                                success.append(pkg)
                            else:
                                failed.append(pkg)
                        except Exception:
                            failed.append(pkg)
            
            self.logger.info(f"Installed {len(success)} packages, {len(failed)} failed")
        else:
            self.logger.info("All required packages are already installed.")
            
        return success, failed

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        """Set the system timezone."""
        self.print_section("Timezone Configuration")
        self.logger.info(f"Setting timezone to {timezone}...")
        try:
            self.run_command(["timedatectl", "set-timezone", timezone])
            self.logger.info(f"Timezone set to {timezone}")
            return True
        except subprocess.CalledProcessError:
            # Fallback method if timedatectl fails
            try:
                tz_file = Path(f"/usr/share/zoneinfo/{timezone}")
                localtime = Path("/etc/localtime")
                if not tz_file.is_file():
                    self.logger.warning(f"Timezone file not found: {tz_file}")
                    return False
                    
                if localtime.exists() or localtime.is_symlink():
                    localtime.unlink()
                localtime.symlink_to(tz_file)
                self.logger.info(f"Timezone set to {timezone} (fallback method)")
                return True
            except Exception as e:
                self.logger.error(f"Failed to set timezone: {e}")
                return False

    # Phase 3: Repository & Shell Setup
    def phase_repo_shell_setup(self) -> bool:
        self.print_section("Phase 3: Repository & Shell Setup")
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
        """Clone or update GitHub repositories."""
        self.print_section("GitHub Repositories Setup")
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
        """Copy shell configuration files from repository to home directories."""
        self.print_section("Shell Configuration Update")
        source_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "debian" / "dotfiles"
        )
        destination_dirs = [self.config.USER_HOME, Path("/root")]
        overall = True
        
        # If source directory doesn't exist, create minimal configs
        if not source_dir.is_dir():
            self.logger.warning(f"Source directory {source_dir} not found; creating minimal configs")
            source_dir = Path("/tmp/debian_setup_dotfiles")
            source_dir.mkdir(exist_ok=True)
            
            # Create minimal .bashrc
            with open(source_dir / ".bashrc", "w") as f:
                f.write("""# ~/.bashrc: executed by bash for non-login shells
if [ -f /etc/bash.bashrc ]; then
    . /etc/bash.bashrc
fi

# If not running interactively, don't do anything
[ -z "$PS1" ] && return

# Alias definitions
alias ls='ls --color=auto'
alias ll='ls -l'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'

# Prompt
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '

# Environment variables
export PATH=$HOME/bin:$PATH
""")
            
            # Create minimal .profile
            with open(source_dir / ".profile", "w") as f:
                f.write("""# ~/.profile: executed by the command interpreter for login shells
if [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi

# Set PATH to include private bin if it exists
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi
""")

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
        """Copy configuration folders from repository to user's .config directory."""
        self.print_section("Copying Configuration Folders")
        src = self.config.CONFIG_SRC_DIR
        dest = self.config.CONFIG_DEST_DIR
        
        if not src.is_dir():
            self.logger.warning(f"Source config directory {src} not found; skipping.")
            return True  # Not a critical failure
            
        dest.mkdir(exist_ok=True)
        overall = True
        
        try:
            for item in src.iterdir():
                if item.is_dir():
                    dest_path = dest / item.name
                    if dest_path.exists():
                        self.logger.info(f"Config dir {dest_path} exists; backing up before overwrite")
                        self.backup_directory(dest_path)
                        
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
        """Set bash as the default shell for the user."""
        self.print_section("Default Shell Configuration")
        if not self.command_exists("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                self.run_command(["apt-get", "install", "-y", "bash"])
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

    # Phase 4: Security Hardening
    def phase_security_hardening(self) -> bool:
        self.print_section("Phase 4: Security Hardening")
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
        """Configure SSH server with secure settings."""
        self.print_section("SSH Configuration")
        try:
            subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "openssh-server"],
                check=False,
                capture_output=True,
                text=True
            )
            if "install ok installed" not in result.stdout:
                self.logger.info("openssh-server not installed. Installing...")
                try:
                    self.run_command(["apt-get", "install", "-y", "openssh-server"])
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install OpenSSH Server.")
                    return False
        except Exception:
            self.logger.info("Error checking openssh-server; attempting install")
            try:
                self.run_command(["apt-get", "install", "-y", "openssh-server"])
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
            modified_lines = []
            
            # Process existing lines
            for line in lines:
                skip_line = False
                for key in self.config.SSH_SETTINGS:
                    if line.strip().startswith(key) or line.strip().startswith(f"#{key}"):
                        # Skip existing options we'll add later
                        skip_line = True
                        break
                if not skip_line:
                    modified_lines.append(line)
                    
            # Add our settings at the end of the file
            modified_lines.append("\n# Security settings from Debian setup script")
            for key, val in self.config.SSH_SETTINGS.items():
                modified_lines.append(f"{key} {val}")
                
            # Write the modified file
            sshd_config.write_text("\n".join(modified_lines) + "\n")
            
            # Restart SSH service
            self.run_command(["systemctl", "restart", "ssh"])
            self.logger.info("SSH configuration updated and service restarted.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    def setup_sudoers(self) -> bool:
        """Configure sudo access for the user."""
        self.print_section("Sudo Configuration")
        try:
            # Check if sudo is installed
            if not self.command_exists("sudo"):
                self.logger.info("sudo not installed; installing...")
                self.run_command(["apt-get", "install", "-y", "sudo"])
                
            # Check if user is in sudo group
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )
            if "sudo" in result.stdout.split():
                self.logger.info(f"User {self.config.USERNAME} already in sudo group.")
                return True
                
            # Add user to sudo group
            self.run_command(["usermod", "-aG", "sudo", self.config.USERNAME])
            self.logger.info(f"User {self.config.USERNAME} added to sudo group.")
            
            # Create a custom sudoers file for the user
            sudoers_d = Path("/etc/sudoers.d")
            sudoers_d.mkdir(exist_ok=True)
            
            user_sudoers = sudoers_d / self.config.USERNAME
            user_sudoers.write_text(f"{self.config.USERNAME} ALL=(ALL) ALL\n")
            user_sudoers.chmod(0o440)
            
            self.logger.info(f"Created sudoers entry for {self.config.USERNAME}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(
                f"Failed to configure sudoers for {self.config.USERNAME}: {e}"
            )
            return False

    def configure_firewall(self, ports: Optional[List[str]] = None) -> bool:
        """Configure UFW firewall with necessary ports open."""
        self.print_section("Firewall Configuration")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
            
        # Install UFW if not present
        if not self.command_exists("ufw"):
            try:
                self.run_command(["apt-get", "install", "-y", "ufw"])
                self.logger.info("UFW installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install UFW.")
                return False
                
        try:
            # Reset UFW to ensure clean configuration
            self.run_command(["ufw", "--force", "reset"])
            self.logger.info("UFW reset to default configuration.")
            
            # Configure default policies
            self.run_command(["ufw", "default", "deny", "incoming"])
            self.run_command(["ufw", "default", "allow", "outgoing"])
            
            # Allow required ports
            for port in ports:
                self.run_command(["ufw", "allow", f"{port}/tcp"])
                self.logger.info(f"Allowed TCP port {port}.")
                
            # Enable UFW
            self.run_command(["ufw", "--force", "enable"])
            self.logger.info("UFW firewall enabled.")
            
            # Enable UFW service
            self.run_command(["systemctl", "enable", "ufw"])
            self.run_command(["systemctl", "start", "ufw"])
            self.logger.info("UFW service enabled and started.")
            
            # Verify status
            status = self.run_command(["ufw", "status"], capture_output=True, text=True)
            self.logger.info(f"UFW Status:\n{status.stdout}")
            
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to configure firewall: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """Configure Fail2ban for SSH protection."""
        self.print_section("Fail2ban Configuration")
        
        # Install Fail2ban if not present
        if not self.command_exists("fail2ban-server"):
            try:
                self.run_command(["apt-get", "install", "-y", "fail2ban"])
                self.logger.info("Fail2ban installed.")
            except subprocess.CalledProcessError:
                self.logger.error("Failed to install Fail2ban.")
                return False
                
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
            
            # Verify fail2ban status
            status = self.run_command(
                ["fail2ban-client", "status"], 
                capture_output=True, 
                text=True,
                check=False
            )
            if status.returncode == 0:
                self.logger.info(f"Fail2ban Status:\n{status.stdout}")
            
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to manage fail2ban service: {e}")
            return False

    # Phase 5: Service Installation
    def phase_service_installation(self) -> bool:
        self.print_section("Phase 5: Essential Service Installation")
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
        """Install and configure Docker."""
        self.print_section("Docker Configuration")
        
        # Check if Docker is already installed
        if self.command_exists("docker"):
            self.logger.info("Docker already installed.")
        else:
            try:
                # Add Docker repository
                self.run_command([
                    "curl", "-fsSL", 
                    "https://download.docker.com/linux/debian/gpg", 
                    "-o", "/etc/apt/keyrings/docker.asc"
                ])
                
                # Ensure directory exists
                Path("/etc/apt/keyrings").mkdir(exist_ok=True)
                
                # Add Docker repository
                docker_sources = Path("/etc/apt/sources.list.d/docker.list")
                docker_sources.write_text(
                    "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] "
                    "https://download.docker.com/linux/debian trixie stable\n"
                )
                
                # Update package lists
                self.run_command(["apt-get", "update", "-qq"])
                
                # Install Docker
                self.run_command([
                    "apt-get", "install", "-y",
                    "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin"
                ])
                
                self.logger.info("Docker installed.")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Docker: {e}")
                
                # Fallback to docker.io package
                try:
                    self.logger.info("Trying fallback installation method...")
                    self.run_command(["apt-get", "install", "-y", "docker.io"])
                    self.logger.info("Docker installed via fallback method.")
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install Docker via fallback.")
                    return False
        
        # Add user to docker group
        try:
            result = self.run_command(
                ["id", "-nG", self.config.USERNAME], capture_output=True, text=True
            )
            if "docker" not in result.stdout.split():
                self.run_command(["usermod", "-aG", "docker", self.config.USERNAME])
                self.logger.info(f"User {self.config.USERNAME} added to docker group.")
            else:
                self.logger.info(f"User {self.config.USERNAME} already in docker group.")
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to add {self.config.USERNAME} to docker group.")
            
        # Configure Docker daemon
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
                
        # Enable and restart Docker service
        try:
            self.run_command(["systemctl", "enable", "docker"])
            self.run_command(["systemctl", "restart", "docker"])
            self.logger.info("Docker service enabled and restarted.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Docker service: {e}")
            return False
            
        # Install Docker Compose if not present
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
        """Install Plex Media Server."""
        self.print_section("Plex Media Server Installation")
        
        # Check if Plex is already installed
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "plexmediaserver"],
                check=False,
                capture_output=True,
                text=True
            )
            if "install ok installed" in result.stdout:
                self.logger.info("Plex Media Server already installed; skipping.")
                return True
        except Exception:
            # Continue with installation
            pass
            
        # Download and install Plex
        temp_deb = Path("/tmp/plexmediaserver.deb")
        try:
            self.download_file(self.config.PLEX_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("dpkg issues with Plex; fixing dependencies...")
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Plex dependencies.")
                return False
                
        # Configure Plex to run as the specified user
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
                    self.logger.info(f"Configured Plex to run as {self.config.USERNAME}.")
                else:
                    self.logger.info("Plex user already configured.")
            except Exception as e:
                self.logger.warning(f"Failed to update {plex_conf}: {e}")
        else:
            self.logger.warning(f"{plex_conf} not found; skipping user configuration.")
            
        # Enable Plex service
        try:
            self.run_command(["systemctl", "enable", "plexmediaserver"])
            self.run_command(["systemctl", "restart", "plexmediaserver"])
            self.logger.info("Plex service enabled and started.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to enable Plex service.")
            
        # Clean up
        try:
            temp_deb.unlink()
        except Exception:
            pass
            
        self.logger.info("Plex Media Server installation complete.")
        return True

    def install_fastfetch(self) -> bool:
        """Install Fastfetch system information tool."""
        self.print_section("Fastfetch Installation")
        
        # Check if Fastfetch is already installed
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f='${Status}'", "fastfetch"],
                check=False,
                capture_output=True,
                text=True
            )
            if "install ok installed" in result.stdout or self.command_exists("fastfetch"):
                self.logger.info("Fastfetch already installed; skipping.")
                return True
        except Exception:
            # Continue with installation
            pass
            
        # Download and install Fastfetch
        temp_deb = Path("/tmp/fastfetch-linux-amd64.deb")
        try:
            self.download_file(self.config.FASTFETCH_URL, temp_deb)
            self.run_command(["dpkg", "-i", str(temp_deb)])
        except subprocess.CalledProcessError:
            self.logger.warning("Fastfetch installation issues; fixing dependencies...")
            try:
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError:
                self.logger.error("Failed to fix Fastfetch dependencies.")
                return False
                
        # Clean up
        try:
            temp_deb.unlink()
        except Exception:
            pass
            
        # Verify installation
        if self.command_exists("fastfetch"):
            self.logger.info("Fastfetch installed successfully.")
            return True
        else:
            self.logger.warning("Fastfetch installation verification failed.")
            return False

    # Phase 6: User Customization & Script Deployment
    def phase_user_customization(self) -> bool:
        self.print_section("Phase 6: User Customization & Script Deployment")
        return run_with_progress(
            "Deploying user scripts", 
            self.deploy_user_scripts, 
            task_name="user_custom"
        )

    def deploy_user_scripts(self) -> bool:
        """Deploy user scripts to the bin directory."""
        self.print_section("Deploying User Scripts")
        src = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "debian" / "_scripts"
        )
        target = self.config.USER_HOME / "bin"
        
        # Check if source directory exists
        if not src.is_dir():
            # Create sample scripts
            self.logger.info(f"Script source directory {src} does not exist; creating samples.")
            src.parent.mkdir(parents=True, exist_ok=True)
            src.mkdir(exist_ok=True)
            
            # Create a simple update script
            update_script = src / "update-system.sh"
            update_script.write_text("""#!/bin/bash
# Simple system update script
echo "Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
echo "Cleaning up..."
sudo apt-get autoremove -y && sudo apt-get autoclean -y
echo "System updated successfully."
""")
            update_script.chmod(0o755)
            
            # Create a backup script
            backup_script = src / "backup-home.sh"
            backup_script.write_text("""#!/bin/bash
# Simple home directory backup script
BACKUP_DIR="/var/backups/home_backup"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_FILE="$BACKUP_DIR/home_backup_$TIMESTAMP.tar.gz"

# Create backup directory if it doesn't exist
sudo mkdir -p "$BACKUP_DIR"

# Backup home directory excluding large files and caches
echo "Creating backup of home directory..."
tar -czf "$BACKUP_FILE" --exclude="*/node_modules" --exclude="*/.cache" \
    --exclude="*/venv" --exclude="*/.venv" --exclude="*/__pycache__" \
    -C /home .

echo "Backup completed: $BACKUP_FILE"
""")
            backup_script.chmod(0o755)
            
            # Set ownership
            self.run_command(
                ["chown", "-R", f"{self.config.USERNAME}:{self.config.USERNAME}", str(src)]
            )
        
        # Create target directory
        target.mkdir(exist_ok=True)
        
        try:
            # Copy scripts
            self.run_command(["rsync", "-ah", "--delete", f"{src}/", f"{target}/"])
            
            # Make scripts executable
            self.run_command(
                ["find", str(target), "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )
            
            # Set ownership
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

    # Phase 7: Maintenance & Monitoring
    def phase_maintenance_monitoring(self) -> bool:
        self.print_section("Phase 7: Maintenance & Monitoring Tasks")
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
        """Set up periodic maintenance tasks."""
        self.print_section("Periodic Maintenance Setup")
        
        # Setup APT periodic configuration
        apt_periodic = Path("/etc/apt/apt.conf.d/02periodic")
        periodic_content = '''// Configure periodic apt tasks
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
'''
        
        try:
            apt_periodic.write_text(periodic_content)
            self.logger.info("APT periodic tasks configured.")
        except Exception as e:
            self.logger.warning(f"Failed to configure APT periodic tasks: {e}")
        
        # Setup daily maintenance cron job
        cron_file = Path("/etc/cron.daily/debian_maintenance")
        marker = "# Debian maintenance script"
        
        if cron_file.is_file() and marker in cron_file.read_text():
            self.logger.info("Daily maintenance cron job already configured.")
            return True
            
        if cron_file.is_file():
            self.backup_file(cron_file)
            
        content = '''#!/bin/sh
# Debian maintenance script
# Created by Debian Trixie setup script

# Update package lists
apt-get update -qq

# Upgrade packages
apt-get upgrade -y

# Remove unused packages
apt-get autoremove -y

# Clean up package cache
apt-get autoclean -y

# Check for broken packages
dpkg --audit || true

# Trim SSD if applicable
if command -v fstrim > /dev/null; then
    fstrim -av || true
fi

# Update man database
if command -v mandb > /dev/null; then
    mandb -q || true
fi

# Update locate database
if command -v updatedb > /dev/null; then
    updatedb || true
fi

# Log completion
echo "$(date): System maintenance completed" >> /var/log/debian_maintenance.log
'''

        try:
            cron_file.write_text(content)
            cron_file.chmod(0o755)
            self.logger.info(f"Created daily maintenance script at {cron_file}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create maintenance script: {e}")
            return False

    def backup_configs(self) -> Optional[str]:
        """Create backups of important configuration files."""
        self.print_section("Configuration Backups")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path(f"/var/backups/debian_config_{timestamp}")
        
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            
            for file in self.config.CONFIG_BACKUP_FILES:
                fpath = Path(file)
                if fpath.is_file():
                    # If it's a directory with name in the path, create the directory structure
                    dest_path = backup_dir / fpath.name
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    shutil.copy2(fpath, dest_path)
                    self.logger.info(f"Backed up {fpath}")
                    count += 1
                else:
                    self.logger.warning(f"{fpath} not found; skipping.")
                    
            if count:
                # Create a timestamp file
                (backup_dir / "backup_info.txt").write_text(
                    f"Backup created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Host: {platform.node()}\n"
                    f"Debian version: {platform.freedesktop_os_release().get('VERSION_ID', 'Unknown')}\n"
                    f"Files backed up: {count}\n"
                )
                
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
        """Rotate log files to prevent them from growing too large."""
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
                
            open(log_path, "w").close()  # Truncate the original log file
            os.chmod(rotated, 0o600)  # Set secure permissions
            
            self.logger.info(f"Log rotated to {rotated}")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def system_health_check(self) -> Dict[str, str]:
        """Perform a basic system health check."""
        self.print_section("System Health Check")
        info = {}
        
        try:
            # Uptime
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            self.logger.info(f"Uptime: {uptime}")
            info["uptime"] = uptime
            
            # Disk usage
            df_out = subprocess.check_output(["df", "-h", "/"], text=True).strip()
            self.logger.info(f"Disk usage:\n{df_out}")
            info["disk_usage"] = df_out
            
            # Memory usage
            free_out = subprocess.check_output(["free", "-h"], text=True).strip()
            self.logger.info(f"Memory usage:\n{free_out}")
            info["memory_usage"] = free_out
            
            # System load
            load = subprocess.check_output(["cat", "/proc/loadavg"], text=True).strip()
            self.logger.info(f"System load: {load}")
            info["load"] = load
            
            # Check for failed services
            try:
                failed_services = subprocess.check_output(
                    ["systemctl", "--failed", "--no-legend"], 
                    text=True
                ).strip()
                
                if failed_services:
                    self.logger.warning(f"Failed services:\n{failed_services}")
                    info["failed_services"] = failed_services
                else:
                    self.logger.info("No failed services found.")
                    info["failed_services"] = "None"
            except Exception as e:
                self.logger.warning(f"Could not check for failed services: {e}")
                
            # Check disk health
            try:
                if self.command_exists("smartctl"):
                    # Get the root device
                    root_device = subprocess.check_output(
                        ["findmnt", "-n", "-o", "SOURCE", "/"], 
                        text=True
                    ).strip()
                    
                    # Extract the disk device (e.g., /dev/sda from /dev/sda1)
                    disk_device = re.sub(r'p?\d+$', '', root_device)
                    
                    # Run smartctl
                    smart_info = subprocess.check_output(
                        ["smartctl", "-H", disk_device],
                        text=True,
                        stderr=subprocess.STDOUT
                    ).strip()
                    
                    self.logger.info(f"Disk health:\n{smart_info}")
                    info["disk_health"] = smart_info
            except Exception as e:
                self.logger.warning(f"Could not check disk health: {e}")
                
            return info
        except Exception as e:
            self.logger.warning(f"Health check error: {e}")
            return {"error": str(e)}

    def verify_firewall_rules(self, ports: Optional[List[str]] = None) -> Dict[str, bool]:
        """Verify that firewall rules are properly configured."""
        self.print_section("Firewall Rules Verification")
        if ports is None:
            ports = self.config.FIREWALL_PORTS
            
        results = {}
        
        # Check UFW status
        try:
            ufw_status = self.run_command(
                ["ufw", "status"], 
                capture_output=True, 
                text=True
            )
            
            if "Status: active" in ufw_status.stdout:
                self.logger.info("UFW is active.")
                results["ufw_active"] = True
            else:
                self.logger.warning("UFW is not active.")
                results["ufw_active"] = False
                
            # Log the full status
            self.logger.info(f"UFW status:\n{ufw_status.stdout}")
        except Exception as e:
            self.logger.warning(f"Failed to check UFW status: {e}")
            results["ufw_active"] = False
            
        # Check individual ports
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

    # Phase 8: Certificates & Performance Tuning
    def phase_certificates_performance(self) -> bool:
        self.print_section("Phase 8: Certificates & Performance Tuning")
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
        """Update SSL certificates using certbot."""
        self.print_section("SSL Certificates Update")
        
        # Install certbot if not present
        if not self.command_exists("certbot"):
            try:
                self.run_command(["apt-get", "install", "-y", "certbot"])
                self.logger.info("certbot installed.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to install certbot.")
                return False
                
        try:
            # Check if there are any certificates to renew
            certbot_certs = self.run_command(
                ["certbot", "certificates"], 
                capture_output=True, 
                text=True,
                check=False
            )
            
            if "No certificates found" in certbot_certs.stdout:
                self.logger.info("No SSL certificates found to renew.")
                return True
                
            # Renew certificates
            self.run_command(["certbot", "renew", "--non-interactive"])
            self.logger.info("SSL certificates updated.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to update SSL certificates: {e}")
            return False

    def tune_system(self) -> bool:
        """Apply performance tuning settings to the system."""
        self.print_section("Performance Tuning")
        
        # Update sysctl.conf
        sysctl_file = Path("/etc/sysctl.conf")
        marker = "# Performance tuning settings for Debian Trixie"
        
        try:
            current = sysctl_file.read_text() if sysctl_file.is_file() else ""
            
            if marker not in current:
                tuning = f'''
{marker}
# Increase file descriptors limit
fs.file-max = 100000

# Network tuning
net.core.somaxconn = 128
net.ipv4.tcp_rmem = 4096 87380 6291456
net.ipv4.tcp_wmem = 4096 16384 4194304
net.ipv4.tcp_max_syn_backlog = 4096
net.core.netdev_max_backlog = 4096

# Virtual memory
vm.swappiness = 10
vm.vfs_cache_pressure = 50

# I/O scheduler settings for SSDs
# Applied at runtime - consider udev rules for persistence
'''
                with open(sysctl_file, "a") as f:
                    f.write(tuning)
                    
                # Apply the settings
                self.run_command(["sysctl", "-p"])
                self.logger.info("Performance tuning applied.")
            else:
                self.logger.info("Performance tuning settings already exist.")
                
            # Configure I/O schedulers for better SSD performance
            if Path("/sys/block").is_dir():
                for device in Path("/sys/block").iterdir():
                    # Only process actual block devices
                    if device.is_dir() and device.name.startswith(("sd", "nvme", "vd")):
                        scheduler_file = device / "queue" / "scheduler"
                        
                        if scheduler_file.is_file():
                            try:
                                # Check if this is an SSD
                                rotational = (device / "queue" / "rotational").read_text().strip()
                                
                                if rotational == "0":  # SSD
                                    # Check current scheduler
                                    current_scheduler = scheduler_file.read_text().strip()
                                    
                                    # For SSDs, prefer none, mq-deadline, or deadline
                                    if "[none]" not in current_scheduler:
                                        if "none" in current_scheduler:
                                            scheduler_file.write_text("none")
                                        elif "mq-deadline" in current_scheduler:
                                            scheduler_file.write_text("mq-deadline")
                                        elif "deadline" in current_scheduler:
                                            scheduler_file.write_text("deadline")
                                            
                                        self.logger.info(f"Set I/O scheduler for {device.name} (SSD)")
                            except Exception as e:
                                self.logger.debug(f"Could not set scheduler for {device.name}: {e}")
                                
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply performance tuning: {e}")
            return False

    # Phase 9: Permissions & Advanced Storage Setup
    def phase_permissions_storage(self) -> bool:
        self.print_section("Phase 9: Permissions & Advanced Storage Setup")
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
        """Configure secure permissions for the home directory."""
        self.print_section("Home Directory Permissions")
        
        try:
            # Set ownership
            self.run_command(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(self.config.USER_HOME),
                ]
            )
            self.logger.info(f"Ownership of {self.config.USER_HOME} set to {self.config.USERNAME}.")
            
            # Set secure permissions on home directory
            self.run_command(["chmod", "750", str(self.config.USER_HOME)])
            self.logger.info(f"Set permissions 750 on {self.config.USER_HOME}.")
            
            # Set setgid bit on directories for consistent group permissions
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
            
            # Apply ACLs if available
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
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to configure home directory permissions: {e}")
            return False

    def install_configure_zfs(self) -> bool:
        """Install and configure ZFS if applicable."""
        self.print_section("ZFS Installation & Configuration")
        pool = self.config.ZFS_POOL_NAME
        mount_point = self.config.ZFS_MOUNT_POINT
        
        # Check if ZFS is already installed
        zfs_installed = self.command_exists("zfs") and self.command_exists("zpool")
        
        if not zfs_installed:
            try:
                self.run_command(["apt-get", "install", "-y", "zfsutils-linux"])
                self.logger.info("ZFS packages installed.")
                zfs_installed = True
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install ZFS packages: {e}")
                return False
                
        if not zfs_installed:
            self.logger.error("ZFS installation failed or not supported.")
            return False
            
        # Enable ZFS services
        for service in ["zfs-import-cache.service", "zfs-mount.service"]:
            try:
                self.run_command(["systemctl", "enable", service])
                self.logger.info(f"Enabled {service}.")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Could not enable {service}.")
                
        # Create mount point
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Mount point {mount_point} ensured.")
        except Exception as e:
            self.logger.warning(f"Failed to create mount point {mount_point}: {e}")
            
        # Check if pool exists
        pool_imported = False
        try:
            result = self.run_command(
                ["zpool", "list", pool], 
                capture_output=True, 
                check=False
            )
            
            if result.returncode == 0:
                self.logger.info(f"ZFS pool '{pool}' already imported.")
                pool_imported = True
            else:
                # Try to import the pool
                try:
                    self.run_command(["zpool", "import", "-f", pool])
                    self.logger.info(f"Imported ZFS pool '{pool}'.")
                    pool_imported = True
                except subprocess.CalledProcessError:
                    self.logger.warning(f"ZFS pool '{pool}' not found or failed to import.")
        except Exception as e:
            self.logger.warning(f"Error checking ZFS pool: {e}")
            
        if not pool_imported:
            self.logger.info("No existing ZFS pool found with the specified name.")
            return True  # Not a failure, just no pool present
            
        # If pool exists, configure it
        try:
            # Set mountpoint
            self.run_command(["zfs", "set", f"mountpoint={mount_point}", pool])
            self.logger.info(f"Set mountpoint for pool '{pool}' to {mount_point}.")
            
            # Set cache file
            cache_file = Path("/etc/zfs/zpool.cache")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.run_command(["zpool", "set", f"cachefile={cache_file}", pool])
            self.logger.info(f"Cachefile for pool '{pool}' updated to {cache_file}.")
            
            # Mount all datasets
            self.run_command(["zfs", "mount", "-a"])
            self.logger.info("Mounted all ZFS datasets.")
            
            # Verify mount
            mounts = subprocess.check_output(
                ["zfs", "list", "-o", "name,mountpoint", "-H"], 
                text=True
            )
            
            if any(str(mount_point) in line for line in mounts.splitlines()):
                self.logger.info(f"ZFS pool '{pool}' mounted at {mount_point}.")
                return True
            else:
                self.logger.warning(f"ZFS pool '{pool}' not mounted at {mount_point}.")
                return False
        except Exception as e:
            self.logger.warning(f"Error configuring ZFS pool: {e}")
            return False

    # Phase 10: Additional Applications & Tools
    def phase_additional_apps(self) -> bool:
        self.print_section("Phase 10: Additional Applications & Tools")
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
        """Install Brave browser."""
        self.print_section("Brave Browser Installation")
        
        # Check if already installed
        if self.command_exists("brave-browser"):
            self.logger.info("Brave browser already installed.")
            return True
            
        try:
            # Add keyring directory
            Path("/etc/apt/keyrings").mkdir(parents=True, exist_ok=True)
            
            # Add Brave repository key
            self.run_command([
                "curl", "-fsSL", 
                "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg",
                "-o", "/etc/apt/keyrings/brave-browser-archive-keyring.gpg"
            ])
            
            # Add Brave repository
            brave_sources = Path("/etc/apt/sources.list.d/brave-browser-release.list")
            brave_sources.write_text(
                "deb [signed-by=/etc/apt/keyrings/brave-browser-archive-keyring.gpg] "
                "https://brave-browser-apt-release.s3.brave.com/ stable main\n"
            )
            
            # Update package lists
            self.run_command(["apt-get", "update", "-qq"])
            
            # Install Brave
            self.run_command(["apt-get", "install", "-y", "brave-browser"])
            
            self.logger.info("Brave browser installed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install Brave browser: {e}")
            return False

    def install_flatpak_and_apps(self) -> Tuple[List[str], List[str]]:
        """Install Flatpak and selected applications."""
        self.print_section("Flatpak Installation & Setup")
        
        # Install Flatpak if not present
        if not self.command_exists("flatpak"):
            try:
                self.run_command(["apt-get", "install", "-y", "flatpak"])
                self.logger.info("Flatpak installed.")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install Flatpak: {e}")
                return [], self.config.FLATPAK_APPS
                
        # Install GNOME Software plugin for Flatpak
        try:
            self.run_command(["apt-get", "install", "-y", "gnome-software-plugin-flatpak"])
            self.logger.info("Flatpak GNOME Software plugin installed.")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to install Flatpak plugin: {e}")
            
        # Add Flathub repository
        try:
            self.run_command([
                "flatpak",
                "remote-add",
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ])
            self.logger.info("Flathub repository added.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to add Flathub repository: {e}")
            return [], self.config.FLATPAK_APPS
            
        # Install applications
        successful = []
        failed = []
        
        for app in self.config.FLATPAK_APPS:
            try:
                # Check if already installed
                result = self.run_command(
                    ["flatpak", "list", "--app", "--columns=application"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if app in result.stdout:
                    self.logger.info(f"Flatpak app already installed: {app}")
                    successful.append(app)
                else:
                    # Install the app
                    self.run_command(["flatpak", "install", "--assumeyes", "flathub", app])
                    self.logger.info(f"Installed Flatpak app: {app}")
                    successful.append(app)
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to install Flatpak app {app}: {e}")
                failed.append(app)
                
        return successful, failed

    def install_configure_vscode_stable(self) -> bool:
        """Install and configure Visual Studio Code."""
        self.print_section("VS Code Installation & Configuration")
        
        # Check if already installed
        if self.command_exists("code"):
            self.logger.info("VS Code already installed.")
            return True
            
        # Download and install VS Code
        vscode_url = (
            "https://go.microsoft.com/fwlink/?LinkID=760868"
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
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to fix VS Code dependencies: {e}")
                return False
                
        # Clean up
        try:
            deb_path.unlink()
        except Exception:
            pass
            
        # Configure for Wayland
        desktop_file = Path("/usr/share/applications/code.desktop")
        if desktop_file.exists():
            try:
                content = desktop_file.read_text()
                wayland_exec = "/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F"
                
                # Replace Exec line
                content = re.sub(
                    r"Exec=.*",
                    f"Exec={wayland_exec}",
                    content
                )
                
                # Also replace in the new-empty-window action
                content = re.sub(
                    r"Exec=/usr/share/code/code --new-window.*",
                    f"Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F",
                    content
                )
                
                desktop_file.write_text(content)
                self.logger.info("Updated VS Code desktop file for Wayland compatibility.")
            except Exception as e:
                self.logger.warning(f"Failed to update VS Code desktop file: {e}")
                
        # Create user configuration directory
        vscode_config_dir = self.config.USER_HOME / ".config" / "Code" / "User"
        vscode_config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create settings.json with reasonable defaults
        settings_file = vscode_config_dir / "settings.json"
        if not settings_file.exists():
            settings = {
                "editor.fontFamily": "'Fira Code', 'Droid Sans Mono', 'monospace'",
                "editor.fontSize": 14,
                "editor.renderWhitespace": "boundary",
                "editor.rulers": [80, 120],
                "editor.minimap.enabled": True,
                "workbench.startupEditor": "none",
                "workbench.colorTheme": "Default Dark Modern",
                "window.titleBarStyle": "custom",
                "files.autoSave": "afterDelay",
                "terminal.integrated.fontFamily": "'Fira Code', monospace",
                "telemetry.telemetryLevel": "off"
            }
            
            try:
                settings_file.write_text(json.dumps(settings, indent=2))
                self.logger.info("Created VS Code default settings.")
            except Exception as e:
                self.logger.warning(f"Failed to create VS Code settings: {e}")
                
        # Set correct permissions
        try:
            self.run_command([
                "chown", "-R", 
                f"{self.config.USERNAME}:{self.config.USERNAME}", 
                str(vscode_config_dir.parent)
            ])
        except Exception as e:
            self.logger.warning(f"Failed to set VS Code config permissions: {e}")
            
        return True

    # Phase 11: Automatic Updates & Additional Security
    def phase_automatic_updates_security(self) -> bool:
        self.print_section("Phase 11: Automatic Updates & Additional Security")
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
        """Configure automatic security updates."""
        self.print_section("Unattended Upgrades Configuration")
        
        try:
            # Install required packages
            self.run_command(["apt-get", "install", "-y", "unattended-upgrades", "apt-listchanges"])
            
            # Configure automatic updates
            auto_file = Path("/etc/apt/apt.conf.d/20auto-upgrades")
            auto_file.write_text(
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )
            
            # Configure unattended upgrades
            unattended_file = Path("/etc/apt/apt.conf.d/50unattended-upgrades")
            if unattended_file.exists():
                self.backup_file(unattended_file)
                
            unattended_file.write_text(
                'Unattended-Upgrade::Origins-Pattern {\n'
                '    // Archive or Suite based matching:\n'
                '    "origin=Debian,codename=${distro_codename},label=Debian";\n'
                '    "origin=Debian,codename=${distro_codename},label=Debian-Security";\n'
                '    "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";\n'
                '};\n\n'
                'Unattended-Upgrade::Package-Blacklist {\n'
                '    // Do not upgrade these packages automatically\n'
                '};\n\n'
                'Unattended-Upgrade::DevRelease "false";\n'
                'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";\n'
                'Unattended-Upgrade::Remove-Unused-Dependencies "true";\n'
                'Unattended-Upgrade::Automatic-Reboot "false";\n'
                'Unattended-Upgrade::Automatic-Reboot-Time "02:00";\n'
                'Unattended-Upgrade::SyslogEnable "true";\n'
            )
            
            # Enable and restart service
            self.run_command(["systemctl", "enable", "unattended-upgrades"])
            self.run_command(["systemctl", "restart", "unattended-upgrades"])
            
            self.logger.info("Unattended upgrades configured successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure unattended upgrades: {e}")
            return False

    def configure_apparmor(self) -> bool:
        """Install and configure AppArmor."""
        self.print_section("AppArmor Configuration")
        
        try:
            # Install AppArmor if not present
            if not self.command_exists("apparmor_status"):
                self.run_command(["apt-get", "install", "-y", "apparmor", "apparmor-utils"])
                self.logger.info("AppArmor installed.")
                
            # Check if AppArmor is enabled in the kernel
            status = self.run_command(
                ["apparmor_status"], 
                capture_output=True, 
                text=True,
                check=False
            )
            
            if "apparmor filesystem is not mounted" in status.stdout:
                self.logger.warning("AppArmor is not enabled in the kernel.")
                return False
                
            # Enable and start AppArmor
            self.run_command(["systemctl", "enable", "apparmor"])
            self.run_command(["systemctl", "start", "apparmor"])
            
            # Set all profiles to enforce mode
            self.run_command(["aa-enforce", "/etc/apparmor.d/*"], check=False)
            
            self.logger.info("AppArmor enabled and configured.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to configure AppArmor: {e}")
            return False

    # Phase 12: Cleanup & Final Configurations
    def phase_cleanup_final(self) -> bool:
        self.print_section("Phase 12: Cleanup & Final Configurations")
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
            "Installing Nala", self.install_nala, task_name="cleanup_final"
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
        """Clean up the system by removing unnecessary packages and files."""
        self.print_section("System Cleanup")
        
        try:
            # Remove unneeded packages
            self.run_command(["apt-get", "autoremove", "-y"])
            self.logger.info("Removed unused packages.")
            
            # Clean package cache
            self.run_command(["apt-get", "autoclean", "-y"])
            self.logger.info("Cleaned package cache.")
            
            # Clean apt lists
            self.run_command(["apt-get", "clean"])
            self.logger.info("Cleaned apt lists.")
            
            # Clean temporary files
            for tmp_dir in ["/tmp", "/var/tmp"]:
                self.run_command(["find", tmp_dir, "-type", "f", "-mtime", "+10", "-delete"])
            self.logger.info("Cleaned old temporary files.")
            
            # Clean old log files
            self.run_command(["find", "/var/log", "-type", "f", "-name", "*.gz", "-mtime", "+30", "-delete"])
            self.logger.info("Removed old compressed log files.")
            
            # Truncate large log files
            for log_pattern in ["/var/log/*.log", "/var/log/*/*.log"]:
                self.run_command(["find", "/var/log", "-type", "f", "-size", "+50M", "-exec", "truncate", "-s", "0", "{}", ";"])
            self.logger.info("Truncated large log files.")
            
            self.logger.info("System cleanup completed.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            return False

    def configure_wayland(self) -> bool:
        """Configure Wayland environment variables."""
        self.print_section("Wayland Environment Configuration")
        
        # Configure global environment variables
        etc_env = Path("/etc/environment")
        try:
            current = etc_env.read_text() if etc_env.is_file() else ""
            vars_current = {}
            
            # Parse current environment
            for line in current.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.split("=", 1)
                    vars_current[key.strip()] = value.strip().strip('"')
                    
            updated = False
            for key, val in self.config.WAYLAND_ENV_VARS.items():
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True
                    
            if updated:
                # Create new environment file content
                new_content = "\n".join(f'{k}="{v}"' for k, v in vars_current.items())
                etc_env.write_text(new_content + "\n")
                self.logger.info(f"Updated {etc_env} with Wayland variables.")
            else:
                self.logger.info(f"No changes needed in {etc_env}.")
        except Exception as e:
            self.logger.warning(f"Failed to update {etc_env}: {e}")
            
        # Configure user environment
        user_env_dir = self.config.USER_HOME / ".config" / "environment.d"
        user_env_file = user_env_dir / "wayland.conf"
        
        try:
            user_env_dir.mkdir(parents=True, exist_ok=True)
            
            # Create environment.d config
            content = "\n".join(f'{k}="{v}"' for k, v in self.config.WAYLAND_ENV_VARS.items()) + "\n"
            
            if user_env_file.is_file():
                if user_env_file.read_text().strip() != content.strip():
                    self.backup_file(user_env_file)
                    user_env_file.write_text(content)
                    self.logger.info(f"Updated {user_env_file} with Wayland variables.")
            else:
                user_env_file.write_text(content)
                self.logger.info(f"Created {user_env_file} with Wayland variables.")
                
            # Set ownership
            self.run_command(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_file),
                ]
            )
            self.run_command(
                [
                    "chown",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(user_env_dir),
                ]
            )
            
            return True
        except Exception as e:
            self.logger.warning(f"Failed to update {user_env_file}: {e}")
            return False

    def install_nala(self) -> bool:
        """Install Nala, an improved frontend for APT."""
        self.print_section("Nala Installation")
        
        # Check if Nala is already installed
        if self.command_exists("nala"):
            self.logger.info("Nala is already installed.")
            return True
            
        try:
            # Update repositories
            self.run_command(["apt-get", "update", "-qq"])
            
            # Install Nala
            self.run_command(["apt-get", "install", "nala", "-y"])
            
            # Verify installation
            if self.command_exists("nala"):
                self.logger.info("Nala installed successfully.")
                
                # Configure faster mirrors
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
        """Install and configure Tailscale VPN client."""
        self.print_section("Tailscale Installation")
        
        # Check if Tailscale is already installed
        if self.command_exists("tailscale"):
            self.logger.info("Tailscale is already installed.")
            tailscale_installed = True
        else:
            try:
                # Add Tailscale repository key
                self.run_command([
                    "curl", "-fsSL", 
                    "https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg",
                    "-o", "/usr/share/keyrings/tailscale-archive-keyring.gpg"
                ])
                
                # Add Tailscale repository
                tailscale_sources = Path("/etc/apt/sources.list.d/tailscale.list")
                tailscale_sources.write_text(
                    "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] "
                    "https://pkgs.tailscale.com/stable/debian trixie main\n"
                )
                
                # Update package lists
                self.run_command(["apt-get", "update", "-qq"])
                
                # Install Tailscale
                self.run_command(["apt-get", "install", "-y", "tailscale"])
                
                tailscale_installed = self.command_exists("tailscale")
                if tailscale_installed:
                    self.logger.info("Tailscale installed successfully.")
                else:
                    self.logger.error("Tailscale installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install Tailscale: {e}")
                return False
                
        # Enable and start Tailscale service
        try:
            self.run_command(["systemctl", "enable", "tailscaled"])
            self.run_command(["systemctl", "start", "tailscaled"])
            
            # Check service status
            status = self.run_command(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )
            
            if status.stdout.strip() == "active":
                self.logger.info(
                    "Tailscale service is active. To authenticate, run: tailscale up"
                )
                return True
            else:
                self.logger.warning("Tailscale service may not be running correctly.")
                return tailscale_installed
        except Exception as e:
            self.logger.error(f"Failed to enable/start Tailscale: {e}")
            return tailscale_installed

    def install_configure_caddy(self) -> bool:
        """Install and configure Caddy web server."""
        self.print_section("Caddy Installation & Configuration")
        
        # Check if Caddy is already installed
        if self.command_exists("caddy"):
            self.logger.info("Caddy is already installed.")
            return True
            
        # Download and install Caddy
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
                self.run_command(["apt-get", "install", "-f", "-y"])
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to resolve Caddy dependencies: {e}")
                return False
                
        # Clean up
        try:
            temp_deb.unlink()
        except Exception:
            pass
            
        # Configure Caddy
        source_caddyfile = (
            self.config.USER_HOME
            / "github"
            / "bash"
            / "linux"
            / "debian"
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
            # Create a minimal Caddyfile
            self.logger.warning(f"Source Caddyfile not found at {source_caddyfile}; creating minimal config.")
            
            dest_caddyfile.parent.mkdir(parents=True, exist_ok=True)
            dest_caddyfile.write_text("""# Minimal Caddyfile
:80 {
	# Set this path to serve static content
	root * /var/www/html
	file_server

	# Enable logging
	log {
		output file /var/log/caddy/access.log
	}
}
""")
            self.logger.info(f"Created minimal Caddyfile at {dest_caddyfile}")
            
        # Create log directory
        log_dir = Path("/var/log/caddy")
        try:
            log_dir.mkdir(mode=0o755, exist_ok=True)
            
            # Create empty log files
            for fname in ["caddy.log", "access.log"]:
                fpath = log_dir / fname
                with open(fpath, "a"):
                    os.utime(fpath, None)
                    fpath.chmod(0o644)
                self.logger.info(f"Prepared log file: {fpath}")
        except Exception as e:
            self.logger.warning(f"Failed to prepare Caddy log files: {e}")
            
        # Create web root directory
        web_root = Path("/var/www/html")
        try:
            web_root.mkdir(parents=True, exist_ok=True)
            
            # Create a test index.html
            index_html = web_root / "index.html"
            if not index_html.exists():
                index_html.write_text("""<!DOCTYPE html>
<html>
<head>
    <title>Caddy on Debian Trixie</title>
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
        }
        h1 { color: #3B4252; }
        .success { color: #A3BE8C; }
    </style>
</head>
<body>
    <h1>Caddy Server is Running</h1>
    <p>If you're seeing this page, Caddy is successfully installed and running on your Debian Trixie system.</p>
    <p class="success">Congratulations on your secure and modern web server setup!</p>
    <p>Edit files in /var/www/html to replace this placeholder page.</p>
</body>
</html>""")
                self.logger.info("Created test index.html page.")
        except Exception as e:
            self.logger.warning(f"Failed to prepare web root: {e}")
            
        # Enable and start Caddy service
        try:
            self.run_command(["systemctl", "enable", "caddy"])
            self.run_command(["systemctl", "restart", "caddy"])
            self.logger.info("Caddy service enabled and started.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to manage Caddy service: {e}")
            return False

    # Phase 13: Final Checks & Reboot
    def phase_final_checks(self) -> bool:
        self.print_section("Phase 13: Final System Checks & Automatic Reboot")
        self.final_checks()
        return self.reboot_system()

    def final_checks(self) -> Dict[str, str]:
        """Perform final system checks before reboot."""
        self.print_section("Final System Checks")
        info = {}
        
        try:
            # Kernel version
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            self.logger.info(f"Kernel version: {kernel}")
            info["kernel"] = kernel
            
            # System uptime
            uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
            self.logger.info(f"System uptime: {uptime}")
            info["uptime"] = uptime
            
            # Disk usage
            df_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            self.logger.info(f"Disk usage (root): {df_line}")
            info["disk_usage"] = df_line
            
            # Memory usage
            free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
            mem_line = next((l for l in free_out if l.startswith("Mem:")), "")
            self.logger.info(f"Memory usage: {mem_line}")
            info["memory"] = mem_line
            
            # CPU info
            cpu_info = ""
            for line in subprocess.check_output(["lscpu"], text=True).splitlines():
                if "Model name" in line:
                    cpu_info = line.split(":", 1)[1].strip()
                    break
            self.logger.info(f"CPU: {cpu_info}")
            info["cpu"] = cpu_info
            
            # Network interfaces
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            self.logger.info("Active network interfaces:")
            for line in interfaces.splitlines():
                self.logger.info(line)
            info["network_interfaces"] = interfaces
            
            # Check for errors in logs
            try:
                errors = subprocess.check_output(
                    ["journalctl", "-p", "err", "-n", "10", "--no-pager"],
                    text=True
                ).strip()
                
                if errors:
                    self.logger.warning("Recent errors in system logs:\n" + errors)
                    info["recent_errors"] = errors
                else:
                    self.logger.info("No recent errors found in system logs.")
                    info["recent_errors"] = "None"
            except Exception as e:
                self.logger.warning(f"Could not check system logs: {e}")
                
            # Verify critical services
            critical_services = ["ssh", "ufw", "fail2ban"]
            services_status = {}
            
            for service in critical_services:
                try:
                    result = self.run_command(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    status = result.stdout.strip()
                    services_status[service] = status
                    
                    if status == "active":
                        self.logger.info(f"Service {service} is active.")
                    else:
                        self.logger.warning(f"Service {service} is {status}.")
                except Exception as e:
                    self.logger.warning(f"Could not check service {service}: {e}")
                    services_status[service] = "unknown"
                    
            info["services"] = services_status
            
            return info
        except Exception as e:
            self.logger.warning(f"Error in final system checks: {e}")
            return {"error": str(e)}

    def reboot_system(self) -> bool:
        """Reboot the system automatically."""
        self.print_section("System Reboot")
        
        self.logger.info("Setup completed successfully. Rebooting system in 10 seconds...")
        
        # Display final status report
        print_status_report()
        
        # Create a flag file to indicate successful setup
        setup_flag = Path("/var/lib/debian_setup_completed")
        setup_flag.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            setup_flag.write_text(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            self.logger.info("Created setup completion flag.")
        except Exception as e:
            self.logger.warning(f"Failed to create setup completion flag: {e}")
            
        # Schedule reboot with a delay
        try:
            self.run_command(["shutdown", "-r", "+1", "System reboot after Debian Trixie setup"])
            self.logger.info("System reboot scheduled for 1 minute from now.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to schedule system reboot: {e}")
            return False

    # Helper methods for command execution, file backup, etc.
    def run_command(
        self,
        cmd: Union[List[str], str],
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Run a command and return the result."""
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
        """Check if a command exists in the system."""
        return shutil.which(cmd) is not None

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Create a backup of a file."""
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
                return None
        else:
            self.logger.warning(f"File {file_path} not found; skipping backup.")
            return None

    def backup_directory(self, dir_path: Union[str, Path]) -> Optional[str]:
        """Create a backup of a directory."""
        dir_path = Path(dir_path)
        if dir_path.is_dir():
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = f"{dir_path}.bak.{timestamp}"
            try:
                shutil.copytree(dir_path, backup)
                self.logger.info(f"Backed up directory {dir_path} to {backup}")
                return backup
            except Exception as e:
                self.logger.warning(f"Failed to backup directory {dir_path}: {e}")
                return None
        else:
            self.logger.warning(f"Directory {dir_path} not found; skipping backup.")
            return None

    def download_file(
        self, url: str, dest_path: Union[str, Path], show_progress: bool = True
    ) -> bool:
        """Download a file from a URL."""
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

    def cleanup(self) -> None:
        """Perform cleanup tasks before exit."""
        self.logger.info("Performing global cleanup tasks before exit.")
        try:
            self.cleanup_system()
        except Exception as e:
            self.logger.warning(f"Cleanup error: {e}")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> int:
    """Main entry point for the Debian Trixie setup script."""
    global setup_instance
    
    # Display beautiful ASCII art banner
    ascii_banner = pyfiglet.figlet_format("Debian Trixie Setup", font="big")
    console.print(Panel(ascii_banner, style="banner"))
    
    console.print("[info]Starting Debian Trixie Setup & Hardening Utility...[/info]")
    console.print("[info]This script will configure your system automatically.[/info]")
    console.print("[warning]Please ensure you have a backup before proceeding.[/warning]\n")
    
    # Initialize setup instance
    setup_instance = DebianTrixieSetup()
    atexit.register(setup_instance.cleanup)
    
    # Define the phases to execute
    phases = [
        setup_instance.phase_preflight,
        setup_instance.phase_system_update,
        setup_instance.phase_repo_shell_setup,
        setup_instance.phase_security_hardening,
        setup_instance.phase_service_installation,
        setup_instance.phase_user_customization,
        setup_instance.phase_maintenance_monitoring,
        setup_instance.phase_certificates_performance,
        setup_instance.phase_permissions_storage,
        setup_instance.phase_additional_apps,
        setup_instance.phase_automatic_updates_security,
        setup_instance.phase_cleanup_final,
        setup_instance.phase_final_checks,
    ]
    
    total = len(phases)
    success_count = 0
    
    with Progress(
        SpinnerColumn(style="bold #88C0D0"),
        TextColumn("[bold #88C0D0]Phase {task.completed}/{task.total}"),
        BarColumn(complete_style="#A3BE8C", finished_style="#A3BE8C"),
        TextColumn("[#ECEFF4]{task.percentage:>3.0f}%"),
        console=console,
        expand=True
    ) as overall_progress:
        task = overall_progress.add_task("Overall Progress", total=total)
        
        for idx, phase in enumerate(phases, start=1):
            setup_instance.print_section(f"Phase {idx}/{total}")
            try:
                result = run_with_progress(f"Running Phase {idx}", phase)
                if result:
                    success_count += 1
                    setup_instance.logger.info(f"Phase {idx} completed successfully.")
                else:
                    setup_instance.logger.warning(f"Phase {idx} encountered issues.")
            except Exception as e:
                setup_instance.logger.critical(
                    f"Phase {idx} failed with exception: {e}", exc_info=True
                )
                
            overall_progress.update(task, completed=idx)
    
    # Calculate success rate
    success_rate = (success_count / total) * 100
    setup_instance.logger.info(
        f"Setup completed with {success_rate:.1f}% success ({success_count}/{total} phases)."
    )
    
    # Final report
    console.print(Panel(
        f"[success]Debian Trixie Setup & Hardening completed with {success_rate:.1f}% success.[/success]\n"
        f"[info]Successful phases: {success_count}/{total}[/info]\n"
        f"[info]Total runtime: {(time.time() - setup_instance.start_time) / 60:.1f} minutes[/info]\n"
        f"[warning]Your system will reboot shortly to apply all changes.[/warning]",
        title="Setup Complete",
        border_style="green"
    ))
    
    # Display final status report
    print_status_report()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())