#!/usr/bin/env python3
"""
Fedora Package Installer
--------------------------------------------------
A fully interactive, menu-driven installer that installs a list
of system packages using DNF and Flatpak applications using Flatpak.
This script is designed for Fedora. It uses DNF (with sudo) to install
packages and assumes Flatpak (with the flathub remote) is already installed
and enabled.

Features:
  • Interactive, menu-driven interface with dynamic ASCII banners.
  • DNF package installation with real-time progress tracking.
  • Flatpak application installation with progress spinners.
  • Custom package selection and group-based installation options.
  • System information display and package management.
  • Nord-themed color styling throughout the application.
  • Robust error handling and cross-platform compatibility.

This script is adapted for Fedora Linux.
Version: 2.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import os
import sys
import time
import socket
import getpass
import signal
import subprocess
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable, Set, Tuple
from enum import Enum, auto


def install_dependencies():
    """Install required dependencies for the non-root user when run with sudo."""
    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    if os.geteuid() != 0:
        print(f"Installing dependencies for user: {user}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        )
        return

    print(f"Running as sudo. Installing dependencies for user: {user}")
    real_user_home = os.path.expanduser(f"~{user}")
    try:
        subprocess.check_call(
            ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
            + required_packages
        )
        print(f"Successfully installed dependencies for user: {user}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import paramiko
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        BarColumn,
        TaskProgressColumn,
    )
    from rich.live import Live
    from rich.align import Align
    from rich.style import Style
    from rich.columns import Columns
    from rich.traceback import install as install_rich_traceback

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle

except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "paramiko",
                    "rich",
                    "pyfiglet",
                    "prompt_toolkit",
                ]
            )
        else:
            install_dependencies()
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print("Please install the required packages manually:")
        print("pip install paramiko rich pyfiglet prompt_toolkit")
        sys.exit(1)

install_rich_traceback(show_locals=True)

console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)
VERSION: str = "2.0.0"
APP_NAME: str = "Fedora Package Installer"
APP_SUBTITLE: str = "Advanced DNF & Flatpak Package Manager"

# Configure history and configuration directories
if os.environ.get("SUDO_USER"):
    HISTORY_DIR = os.path.expanduser(
        f"~{os.environ.get('SUDO_USER')}/.fedora_pkg_installer"
    )
else:
    HISTORY_DIR = os.path.expanduser("~/.fedora_pkg_installer")

os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
PACKAGE_HISTORY = os.path.join(HISTORY_DIR, "package_history")
PACKAGE_LISTS_DIR = os.path.join(HISTORY_DIR, "package_lists")
os.makedirs(PACKAGE_LISTS_DIR, exist_ok=True)

for history_file in [COMMAND_HISTORY, PACKAGE_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass


# ----------------------------------------------------------------
# Nord-Themed Colors
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


# ----------------------------------------------------------------
# Package Categories and Data Structures
# ----------------------------------------------------------------
class PackageType(Enum):
    DNF = auto()
    FLATPAK = auto()


@dataclass
class PackageCategory:
    """
    Represents a category of packages with a name and description.
    """

    name: str
    description: str
    packages: List[str]
    package_type: PackageType
    selected: bool = True


@dataclass
class InstallationState:
    """
    Tracks the state of the current installation session.
    """

    selected_dnf_packages: Set[str] = field(default_factory=set)
    selected_flatpak_apps: Set[str] = field(default_factory=set)
    installation_complete: bool = False
    last_installed: Optional[datetime] = None
    error_packages: List[str] = field(default_factory=list)


# Initialize the installation state
install_state = InstallationState()

# ----------------------------------------------------------------
# Package Lists
# ----------------------------------------------------------------
# Define package categories
DNF_CATEGORIES = [
    PackageCategory(
        name="shells_editors",
        description="Shells and Text Editors",
        packages=["bash", "vim", "nano", "screen", "tmux", "neovim", "emacs", "micro"],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="system_monitoring",
        description="System Monitoring Tools",
        packages=[
            "htop",
            "btop",
            "tree",
            "iftop",
            "mtr",
            "iotop",
            "glances",
            "sysstat",
            "atop",
            "powertop",
            "nmon",
            "dstat",
            "bpytop",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="network_security",
        description="Network and Security Tools",
        packages=[
            "git",
            "openssh-server",
            "firewalld",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "bash-completion",
            "net-tools",
            "nmap",
            "tcpdump",
            "fail2ban",
            "wireshark",
            "masscan",
            "netcat",
            "arp-scan",
            "hydra",
            "clamav",
            "lynis",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="core_utilities",
        description="Core System Utilities",
        packages=[
            "python3",
            "python3-pip",
            "ca-certificates",
            "dnf-plugins-core",
            "gnupg2",
            "gnupg",
            "pinentry",
            "seahorse",
            "keepassxc",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="development_tools",
        description="Development Tools",
        packages=[
            "gcc",
            "gcc-c++",
            "make",
            "cmake",
            "ninja-build",
            "meson",
            "gettext",
            "pkgconf",
            "python3-devel",
            "openssl-devel",
            "libffi-devel",
            "zlib-devel",
            "readline-devel",
            "bzip2-devel",
            "tk-devel",
            "xz",
            "ncurses-devel",
            "gdbm-devel",
            "nss-devel",
            "libxml2-devel",
            "xmlsec1-openssl-devel",
            "clang",
            "llvm",
            "golang",
            "gdb",
            "cargo",
            "rust",
            "jq",
            "yq",
            "yamllint",
            "shellcheck",
            "patch",
            "diffstat",
            "flex",
            "bison",
            "ctags",
            "cscope",
            "perf",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="network_utilities",
        description="Network Utilities",
        packages=[
            "traceroute",
            "mtr",
            "bind-utils",
            "iproute",
            "iputils",
            "restic",
            "whois",
            "dnsmasq",
            "openvpn",
            "wireguard-tools",
            "nftables",
            "ipcalc",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="enhanced_shells",
        description="Enhanced Shells and Utilities",
        packages=[
            "zsh",
            "fzf",
            "bat",
            "ripgrep",
            "ncdu",
            "fd-find",
            "exa",
            "lsd",
            "mcfly",
            "autojump",
            "direnv",
            "zoxide",
            "progress",
            "pv",
            "tmux-powerline",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="containers_dev",
        description="Containers and Development",
        packages=[
            "docker",
            "docker-compose",
            "podman",
            "buildah",
            "skopeo",
            "nodejs",
            "npm",
            "yarn",
            "autoconf",
            "automake",
            "libtool",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="debug_utilities",
        description="Debugging Utilities",
        packages=[
            "strace",
            "ltrace",
            "valgrind",
            "tig",
            "colordiff",
            "the_silver_searcher",
            "xclip",
            "tmate",
            "iperf3",
            "httpie",
            "ngrep",
            "gron",
            "entr",
            "lsof",
            "socat",
            "psmisc",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="multimedia",
        description="Multimedia Tools",
        packages=[
            "ffmpeg",
            "imagemagick",
            "media-player-info",
            "audacity",
            "vlc",
            "obs-studio",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="database",
        description="Database Clients",
        packages=[
            "mariadb",
            "postgresql",
            "sqlite",
            "redis",
            "mongo-tools",
            "pgadmin4",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="virtualization",
        description="Virtualization Tools",
        packages=["virt-manager", "qemu-kvm", "libvirt", "virtualbox", "vagrant"],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="ides_editors",
        description="IDEs and Advanced Editors",
        packages=[
            "code",
            "sublime-text",
            "jetbrains-idea-community",
            "pycharm-community",
            "visual-studio-code",
            "android-studio",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="compression",
        description="File Compression and Archiving",
        packages=[
            "p7zip",
            "p7zip-plugins",
            "unrar",
            "unzip",
            "zip",
            "tar",
            "pigz",
            "lbzip2",
            "lz4",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="terminal_tools",
        description="Terminal Multiplexers and Tools",
        packages=[
            "byobu",
            "terminator",
            "kitty",
            "alacritty",
            "tilix",
            "ranger",
            "mc",
            "vifm",
            "nnn",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="office_productivity",
        description="Office and Productivity",
        packages=[
            "libreoffice",
            "gimp",
            "inkscape",
            "dia",
            "calibre",
            "pandoc",
            "texlive",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="backup_restore",
        description="System Backup and Restore",
        packages=[
            "timeshift",
            "backintime",
            "duplicity",
            "borgbackup",
            "rclone",
            "syncthing",
        ],
        package_type=PackageType.DNF,
    ),
    PackageCategory(
        name="extras",
        description="Extras and Goodies",
        packages=["neofetch", "yt-dlp", "cmatrix", "tldr"],
        package_type=PackageType.DNF,
    ),
]

FLATPAK_CATEGORIES = [
    PackageCategory(
        name="internet",
        description="Internet Applications",
        packages=[
            "org.mozilla.firefox",
            "org.mozilla.Thunderbird",
            "org.chromium.Chromium",
            "com.github.micahflee.torbrowser-launcher",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="communication",
        description="Communication Apps",
        packages=[
            "com.discordapp.Discord",
            "org.signal.Signal",
            "org.telegram.desktop",
            "com.slack.Slack",
            "us.zoom.Zoom",
            "im.riot.Element",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="multimedia",
        description="Multimedia Applications",
        packages=[
            "com.spotify.Client",
            "org.videolan.VLC",
            "com.obsproject.Studio",
            "org.kde.kdenlive",
            "org.audacityteam.Audacity",
            "org.shotcut.Shotcut",
            "tv.plex.PlexDesktop",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="graphics",
        description="Graphics and Design",
        packages=[
            "org.blender.Blender",
            "org.gimp.GIMP",
            "org.inkscape.Inkscape",
            "org.kde.krita",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="gaming",
        description="Gaming",
        packages=[
            "com.valvesoftware.Steam",
            "net.lutris.Lutris",
            "com.usebottles.bottles",
            "org.libretro.RetroArch",
            "org.prismlauncher.PrismLauncher",
            "com.github.k4zmu2a.spacecadetpinball",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="productivity",
        description="Productivity",
        packages=[
            "md.obsidian.Obsidian",
            "org.libreoffice.LibreOffice",
            "com.calibre_ebook.calibre",
            "org.onlyoffice.desktopeditors",
            "org.kde.okular",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="system",
        description="System Tools",
        packages=[
            "com.github.tchx84.Flatseal",
            "net.davidotek.pupgui2",
            "org.gnome.Tweaks",
            "org.gnome.Boxes",
            "org.gnome.Logs",
            "org.gnome.Disks",
            "org.gnome.SystemMonitor",
            "org.raspberrypi.rpi-imager",
        ],
        package_type=PackageType.FLATPAK,
    ),
    PackageCategory(
        name="utilities",
        description="Utilities",
        packages=[
            "com.bitwarden.desktop",
            "org.remmina.Remmina",
            "com.rustdesk.RustDesk",
            "org.filezillaproject.Filezilla",
            "org.nextcloud.Nextcloud",
            "com.getpostman.Postman",
            "io.github.aandrew_me.ytdn",
        ],
        package_type=PackageType.FLATPAK,
    ),
]


# ----------------------------------------------------------------
# Enhanced Spinner Progress Manager
# ----------------------------------------------------------------
class SpinnerProgressManager:
    """Manages Rich spinners with consistent styling and features."""

    def __init__(self, title: str = "", auto_refresh: bool = True):
        self.title = title
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TextColumn("[{task.fields[status]}]"),
            TimeElapsedColumn(),
            TextColumn("[{task.fields[eta]}]"),
            auto_refresh=auto_refresh,
            console=console,
        )
        self.live = None
        self.tasks = {}
        self.start_times = {}
        self.total_sizes = {}
        self.completed_sizes = {}
        self.is_started = False

    def start(self):
        """Start the progress display."""
        if not self.is_started:
            self.live = Live(self.progress, console=console, refresh_per_second=10)
            self.live.start()
            self.is_started = True

    def stop(self):
        """Stop the progress display."""
        if self.is_started and self.live:
            self.live.stop()
            self.is_started = False

    def add_task(self, description: str, total_size: Optional[int] = None) -> str:
        """Add a new task with a unique ID."""
        task_id = f"task_{len(self.tasks)}"
        self.start_times[task_id] = time.time()

        if total_size is not None:
            self.total_sizes[task_id] = total_size
            self.completed_sizes[task_id] = 0

        self.tasks[task_id] = self.progress.add_task(
            description,
            status=f"[{NordColors.FROST_3}]Starting...",
            eta="Calculating...",
        )
        return task_id

    def update_task(self, task_id: str, status: str, completed: Optional[int] = None):
        """Update a task's status and progress."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        self.progress.update(task, status=status)

        if completed is not None and task_id in self.total_sizes:
            self.completed_sizes[task_id] = completed
            percentage = min(100, int(100 * completed / self.total_sizes[task_id]))

            # Calculate ETA
            elapsed = time.time() - self.start_times[task_id]
            if percentage > 0:
                total_time = elapsed * 100 / percentage
                remaining = total_time - elapsed
                eta_str = f"[{NordColors.FROST_4}]ETA: {format_time(remaining)}"
            else:
                eta_str = f"[{NordColors.FROST_4}]Calculating..."

            # Format status with percentage
            status_with_percentage = (
                f"[{NordColors.FROST_3}]{status} [{NordColors.GREEN}]{percentage}%[/]"
            )
            self.progress.update(task, status=status_with_percentage, eta=eta_str)

    def complete_task(self, task_id: str, success: bool = True):
        """Mark a task as complete with success or failure indication."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        status_color = NordColors.GREEN if success else NordColors.RED
        status_text = "COMPLETED" if success else "FAILED"

        if task_id in self.total_sizes:
            self.completed_sizes[task_id] = self.total_sizes[task_id]

        elapsed = time.time() - self.start_times[task_id]
        elapsed_str = format_time(elapsed)

        status_msg = f"[bold {status_color}]{status_text}[/] in {elapsed_str}"
        self.progress.update(task, status=status_msg, eta="")


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def format_time(seconds: float) -> str:
    """Format seconds to human-readable time string."""
    if seconds < 1:
        return "less than a second"
    elif seconds < 60:
        return f"{seconds:.1f}s"

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds)}s"

    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
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
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
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
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def show_help() -> None:
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-9, A-C, 0[/]:   Menu selection numbers
[bold {NordColors.FROST_2}]Tab[/]:         Auto-complete package names
[bold {NordColors.FROST_2}]Up/Down[/]:     Navigate command history
[bold {NordColors.FROST_2}]Ctrl+C[/]:      Cancel current operation
[bold {NordColors.FROST_2}]h[/]:           Show this help screen
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def wait_for_key() -> None:
    pt_prompt(
        "Press Enter to continue...",
        style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}),
    )


# ----------------------------------------------------------------
# System Information and Status Functions
# ----------------------------------------------------------------
def get_fedora_version() -> str:
    """Get the current Fedora version."""
    try:
        with open("/etc/fedora-release", "r") as f:
            release_info = f.read().strip()
            return release_info
    except Exception:
        return "Fedora Linux (version unknown)"


def get_system_info() -> Dict[str, str]:
    """Gather system information."""
    info = {
        "Hostname": HOSTNAME,
        "User": DEFAULT_USERNAME,
        "OS": get_fedora_version(),
        "Kernel": os.uname().release,
        "Architecture": os.uname().machine,
    }

    # Check if DNF is available
    try:
        dnf_version = subprocess.check_output(
            ["dnf", "--version"], universal_newlines=True
        ).splitlines()[0]
        info["DNF Version"] = dnf_version
    except Exception:
        info["DNF Version"] = "Not found"

    # Check if Flatpak is available
    try:
        flatpak_version = subprocess.check_output(
            ["flatpak", "--version"], universal_newlines=True
        ).strip()
        info["Flatpak Version"] = flatpak_version
    except Exception:
        info["Flatpak Version"] = "Not found"

    return info


def display_system_info() -> None:
    """Display system information in a table."""
    system_info = get_system_info()

    table = Table(
        title="System Information",
        show_header=False,
        expand=False,
        border_style=NordColors.FROST_3,
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    for key, value in system_info.items():
        table.add_row(key, value)

    console.print(
        Panel(
            table,
            title="System Information",
            border_style=Style(color=NordColors.FROST_1),
        )
    )


# ----------------------------------------------------------------
# Package Management Functions
# ----------------------------------------------------------------
def get_all_dnf_packages() -> List[str]:
    """Get a flat list of all DNF packages from all categories."""
    all_packages = []
    for category in DNF_CATEGORIES:
        if category.selected:
            all_packages.extend(category.packages)
    return all_packages


def get_all_flatpak_apps() -> List[str]:
    """Get a flat list of all Flatpak apps from all categories."""
    all_apps = []
    for category in FLATPAK_CATEGORIES:
        if category.selected:
            all_apps.extend(category.packages)
    return all_apps


def update_selected_packages() -> None:
    """Update the installation state with selected packages."""
    install_state.selected_dnf_packages = set(get_all_dnf_packages())
    install_state.selected_flatpak_apps = set(get_all_flatpak_apps())


def install_dnf_packages() -> None:
    """Install selected DNF packages."""
    # Update the list of selected packages first
    update_selected_packages()

    # Check if there are any packages to install
    if not install_state.selected_dnf_packages:
        print_warning("No DNF packages selected for installation.")
        return

    packages_to_install = list(install_state.selected_dnf_packages)
    display_panel(
        f"Installing [bold]{len(packages_to_install)}[/] DNF packages...",
        NordColors.PURPLE,
        "DNF Installation",
    )

    # Create spinner for the installation process
    spinner = SpinnerProgressManager("DNF Installation")
    task_id = spinner.add_task(f"Installing {len(packages_to_install)} DNF packages...")

    try:
        spinner.start()

        # Prepare the DNF command
        cmd = ["sudo", "dnf", "install", "-y"] + packages_to_install

        # Create a process to execute the command
        spinner.update_task(task_id, "Preparing DNF transaction...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Track progress through the output
        installed_count = 0
        total_packages = len(packages_to_install)
        error_packages = []

        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if (
                    "Installing:" in line
                    or "Upgrading:" in line
                    or "Reinstalling:" in line
                ):
                    installed_count += 1
                    package_name = (
                        line.split()[1] if len(line.split()) > 1 else "package"
                    )
                    spinner.update_task(
                        task_id, f"Installing {package_name}", completed=installed_count
                    )
                elif "Error:" in line or "Failed:" in line:
                    error_package = line.split(":")[1].strip() if ":" in line else line
                    error_packages.append(error_package)

        # Wait for the process to complete
        return_code = process.wait()

        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success(f"Successfully installed {installed_count} DNF packages.")
            install_state.last_installed = datetime.now()
        else:
            spinner.complete_task(task_id, False)
            print_error(f"DNF installation failed with return code {return_code}")
            if error_packages:
                print_error(f"Packages with errors: {', '.join(error_packages)}")
                install_state.error_packages = error_packages

    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during DNF installation: {e}")
    finally:
        spinner.stop()


def install_flatpak_apps() -> None:
    """Install selected Flatpak applications."""
    # Update the list of selected apps first
    update_selected_packages()

    # Check if there are any apps to install
    if not install_state.selected_flatpak_apps:
        print_warning("No Flatpak applications selected for installation.")
        return

    apps_to_install = list(install_state.selected_flatpak_apps)
    display_panel(
        f"Installing [bold]{len(apps_to_install)}[/] Flatpak applications...",
        NordColors.PURPLE,
        "Flatpak Installation",
    )

    # Create spinner for the installation process
    spinner = SpinnerProgressManager("Flatpak Installation")
    task_id = spinner.add_task(
        f"Installing {len(apps_to_install)} Flatpak applications..."
    )

    try:
        spinner.start()

        # Prepare the Flatpak command - we assume the flathub remote is configured
        cmd = ["flatpak", "install", "-y", "flathub"] + apps_to_install

        # Create a process to execute the command
        spinner.update_task(task_id, "Preparing Flatpak transaction...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Track progress through the output
        installed_count = 0
        total_apps = len(apps_to_install)
        error_apps = []

        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                for app_id in apps_to_install:
                    if app_id in line and (
                        "Installing:" in line or "Upgrading:" in line
                    ):
                        installed_count += 1
                        spinner.update_task(
                            task_id, f"Installing {app_id}", completed=installed_count
                        )
                if "error:" in line.lower() or "failed:" in line.lower():
                    error_app = next(
                        (app for app in apps_to_install if app in line), "unknown app"
                    )
                    error_apps.append(error_app)

        # Wait for the process to complete
        return_code = process.wait()

        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success(
                f"Successfully installed {installed_count} Flatpak applications."
            )
            install_state.last_installed = datetime.now()
        else:
            spinner.complete_task(task_id, False)
            print_error(f"Flatpak installation failed with return code {return_code}")
            if error_apps:
                print_error(f"Applications with errors: {', '.join(error_apps)}")
                install_state.error_packages.extend(error_apps)

    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during Flatpak installation: {e}")
    finally:
        spinner.stop()


def install_all() -> None:
    """Install both DNF packages and Flatpak applications."""
    # Update selected packages
    update_selected_packages()

    # Install DNF packages first
    if install_state.selected_dnf_packages:
        install_dnf_packages()

    # Then install Flatpak apps
    if install_state.selected_flatpak_apps:
        install_flatpak_apps()

    # Set the installation complete flag
    install_state.installation_complete = True

    # Report overall success
    if not install_state.error_packages:
        display_panel(
            "All selected packages and applications have been successfully installed!",
            NordColors.GREEN,
            "Installation Complete",
        )
    else:
        display_panel(
            f"Installation completed with {len(install_state.error_packages)} errors.",
            NordColors.YELLOW,
            "Installation Completed with Warnings",
        )


def manage_dnf_categories() -> None:
    """Menu for managing DNF package categories."""
    while True:
        console.clear()
        console.print(create_header())
        print_section("DNF Package Categories")

        table = Table(
            title="Available DNF Package Categories",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
            expand=True,
        )
        table.add_column("No.", style="bold", width=4)
        table.add_column("Category", style="bold")
        table.add_column("Description")
        table.add_column("Packages", justify="right")
        table.add_column("Status", style="bold")

        for idx, category in enumerate(DNF_CATEGORIES, start=1):
            status_style = NordColors.GREEN if category.selected else NordColors.RED
            status_text = "SELECTED" if category.selected else "EXCLUDED"
            table.add_row(
                str(idx),
                category.name,
                category.description,
                str(len(category.packages)),
                f"[{status_style}]{status_text}[/]",
            )

        console.print(table)
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Category Management Options:[/]")
        console.print(
            f"[{NordColors.FROST_2}]1-{len(DNF_CATEGORIES)}[/]: Toggle category selection"
        )
        console.print(f"[{NordColors.FROST_2}]A[/]: Select All Categories")
        console.print(f"[{NordColors.FROST_2}]N[/]: Deselect All Categories")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()

        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()

        if choice == "B":
            break
        elif choice == "A":
            for category in DNF_CATEGORIES:
                category.selected = True
            print_success("All DNF categories selected.")
            time.sleep(1)
        elif choice == "N":
            for category in DNF_CATEGORIES:
                category.selected = False
            print_warning("All DNF categories deselected.")
            time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(DNF_CATEGORIES):
                    DNF_CATEGORIES[idx].selected = not DNF_CATEGORIES[idx].selected
                    status = (
                        "selected" if DNF_CATEGORIES[idx].selected else "deselected"
                    )
                    print_success(f"Category '{DNF_CATEGORIES[idx].name}' {status}.")
                    time.sleep(0.5)
                else:
                    print_error(f"Invalid selection: {choice}")
                    time.sleep(0.5)
            except ValueError:
                print_error(f"Invalid input: {choice}")
                time.sleep(0.5)

        # Update the selected packages after changes
        update_selected_packages()


def manage_flatpak_categories() -> None:
    """Menu for managing Flatpak application categories."""
    while True:
        console.clear()
        console.print(create_header())
        print_section("Flatpak Application Categories")

        table = Table(
            title="Available Flatpak Application Categories",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
            expand=True,
        )
        table.add_column("No.", style="bold", width=4)
        table.add_column("Category", style="bold")
        table.add_column("Description")
        table.add_column("Apps", justify="right")
        table.add_column("Status", style="bold")

        for idx, category in enumerate(FLATPAK_CATEGORIES, start=1):
            status_style = NordColors.GREEN if category.selected else NordColors.RED
            status_text = "SELECTED" if category.selected else "EXCLUDED"
            table.add_row(
                str(idx),
                category.name,
                category.description,
                str(len(category.packages)),
                f"[{status_style}]{status_text}[/]",
            )

        console.print(table)
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Category Management Options:[/]")
        console.print(
            f"[{NordColors.FROST_2}]1-{len(FLATPAK_CATEGORIES)}[/]: Toggle category selection"
        )
        console.print(f"[{NordColors.FROST_2}]A[/]: Select All Categories")
        console.print(f"[{NordColors.FROST_2}]N[/]: Deselect All Categories")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()

        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()

        if choice == "B":
            break
        elif choice == "A":
            for category in FLATPAK_CATEGORIES:
                category.selected = True
            print_success("All Flatpak categories selected.")
            time.sleep(1)
        elif choice == "N":
            for category in FLATPAK_CATEGORIES:
                category.selected = False
            print_warning("All Flatpak categories deselected.")
            time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(FLATPAK_CATEGORIES):
                    FLATPAK_CATEGORIES[idx].selected = not FLATPAK_CATEGORIES[
                        idx
                    ].selected
                    status = (
                        "selected" if FLATPAK_CATEGORIES[idx].selected else "deselected"
                    )
                    print_success(
                        f"Category '{FLATPAK_CATEGORIES[idx].name}' {status}."
                    )
                    time.sleep(0.5)
                else:
                    print_error(f"Invalid selection: {choice}")
                    time.sleep(0.5)
            except ValueError:
                print_error(f"Invalid input: {choice}")
                time.sleep(0.5)

        # Update the selected packages after changes
        update_selected_packages()


def custom_package_selection() -> None:
    """Menu for customizing individual package selections."""
    while True:
        console.clear()
        console.print(create_header())
        print_section("Custom Package Selection")

        console.print(f"[bold {NordColors.PURPLE}]Package Selection Options:[/]")
        console.print(f"[{NordColors.FROST_2}]1[/]: Manage DNF Package Selections")
        console.print(
            f"[{NordColors.FROST_2}]2[/]: Manage Flatpak Application Selections"
        )
        console.print(f"[{NordColors.FROST_2}]3[/]: Add Custom DNF Package")
        console.print(f"[{NordColors.FROST_2}]4[/]: Add Custom Flatpak Application")
        console.print(f"[{NordColors.FROST_2}]B[/]: Back to Main Menu")
        console.print()

        choice = pt_prompt(
            "Enter your choice: ",
            history=FileHistory(COMMAND_HISTORY),
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()

        if choice == "B":
            break
        elif choice == "1":
            manage_dnf_package_selections()
        elif choice == "2":
            manage_flatpak_app_selections()
        elif choice == "3":
            add_custom_dnf_package()
        elif choice == "4":
            add_custom_flatpak_app()
        else:
            print_error(f"Invalid selection: {choice}")
            time.sleep(0.5)


def manage_dnf_package_selections() -> None:
    """Manage individual DNF package selections."""
    # First, update the selected packages list
    update_selected_packages()

    # Create a list of all packages from all categories for easier management
    all_packages = []
    for category in DNF_CATEGORIES:
        for package in category.packages:
            all_packages.append(
                (package, category.name, package in install_state.selected_dnf_packages)
            )

    # Sort packages alphabetically
    all_packages.sort(key=lambda x: x[0])

    while True:
        console.clear()
        console.print(create_header())
        print_section("DNF Package Selection")

        # Display packages in pages for better navigation
        page_size = 20
        total_pages = (len(all_packages) + page_size - 1) // page_size
        current_page = 1

        while True:
            console.clear()
            console.print(create_header())

            # Calculate page range
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, len(all_packages))

            # Display packages table
            table = Table(
                title=f"DNF Packages (Page {current_page}/{total_pages})",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
                expand=True,
            )
            table.add_column("No.", style="bold", width=4)
            table.add_column("Package", style="bold")
            table.add_column("Category")
            table.add_column("Status", style="bold")

            for i, (package, category, selected) in enumerate(
                all_packages[start_idx:end_idx], start=start_idx + 1
            ):
                status_style = NordColors.GREEN if selected else NordColors.RED
                status_text = "SELECTED" if selected else "EXCLUDED"
                table.add_row(
                    str(i), package, category, f"[{status_style}]{status_text}[/]"
                )

            console.print(table)
            console.print()
            console.print(f"[bold {NordColors.PURPLE}]Navigation and Options:[/]")
            console.print(
                f"[{NordColors.FROST_2}]1-{end_idx - start_idx}[/]: Toggle package selection"
            )
            console.print(f"[{NordColors.FROST_2}]N[/]: Next Page")
            console.print(f"[{NordColors.FROST_2}]P[/]: Previous Page")
            console.print(f"[{NordColors.FROST_2}]S[/]: Search Packages")
            console.print(f"[{NordColors.FROST_2}]B[/]: Back to Custom Package Menu")
            console.print()

            choice = pt_prompt(
                "Enter your choice: ",
                history=FileHistory(COMMAND_HISTORY),
                auto_suggest=AutoSuggestFromHistory(),
                style=get_prompt_style(),
            ).upper()

            if choice == "B":
                return
            elif choice == "N":
                if current_page < total_pages:
                    current_page += 1
            elif choice == "P":
                if current_page > 1:
                    current_page -= 1
            elif choice == "S":
                search_term = pt_prompt(
                    "Enter search term: ",
                    history=FileHistory(PACKAGE_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).lower()

                # Filter packages by search term
                matching_packages = [
                    (i + 1, package, category, selected)
                    for i, (package, category, selected) in enumerate(all_packages)
                    if search_term in package.lower() or search_term in category.lower()
                ]

                if not matching_packages:
                    print_warning(f"No packages found matching '{search_term}'")
                    time.sleep(1)
                    continue

                # Display matching packages
                search_table = Table(
                    title=f"Search Results for '{search_term}'",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_3}",
                    expand=True,
                )
                search_table.add_column("No.", style="bold", width=4)
                search_table.add_column("Package", style="bold")
                search_table.add_column("Category")
                search_table.add_column("Status", style="bold")

                for idx, package, category, selected in matching_packages:
                    status_style = NordColors.GREEN if selected else NordColors.RED
                    status_text = "SELECTED" if selected else "EXCLUDED"
                    search_table.add_row(
                        str(idx), package, category, f"[{status_style}]{status_text}[/]"
                    )

                console.print(search_table)
                console.print()

                search_choice = pt_prompt(
                    "Enter package number to toggle selection (or 'C' to cancel): ",
                    history=FileHistory(COMMAND_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).upper()

                if search_choice == "C":
                    continue

                try:
                    search_idx = int(search_choice) - 1
                    if 0 <= search_idx < len(all_packages):
                        package, category, selected = all_packages[search_idx]
                        all_packages[search_idx] = (package, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Package '{package}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid package number: {search_choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {search_choice}")
                    time.sleep(0.5)
            else:
                try:
                    idx = int(choice) - 1 + start_idx
                    if 0 <= idx < len(all_packages):
                        package, category, selected = all_packages[idx]
                        all_packages[idx] = (package, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Package '{package}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid package number: {choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {choice}")
                    time.sleep(0.5)

    # Update the selected packages based on user choices
    selected_packages = set()
    for package, _, selected in all_packages:
        if selected:
            selected_packages.add(package)

    install_state.selected_dnf_packages = selected_packages


def manage_flatpak_app_selections() -> None:
    """Manage individual Flatpak application selections."""
    # First, update the selected apps list
    update_selected_packages()

    # Create a list of all apps from all categories for easier management
    all_apps = []
    for category in FLATPAK_CATEGORIES:
        for app in category.packages:
            all_apps.append(
                (app, category.name, app in install_state.selected_flatpak_apps)
            )

    # Sort apps alphabetically
    all_apps.sort(key=lambda x: x[0])

    while True:
        console.clear()
        console.print(create_header())
        print_section("Flatpak Application Selection")

        # Display apps in pages for better navigation
        page_size = 20
        total_pages = (len(all_apps) + page_size - 1) // page_size
        current_page = 1

        while True:
            console.clear()
            console.print(create_header())

            # Calculate page range
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, len(all_apps))

            # Display apps table
            table = Table(
                title=f"Flatpak Applications (Page {current_page}/{total_pages})",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
                expand=True,
            )
            table.add_column("No.", style="bold", width=4)
            table.add_column("Application", style="bold")
            table.add_column("Category")
            table.add_column("Status", style="bold")

            for i, (app, category, selected) in enumerate(
                all_apps[start_idx:end_idx], start=start_idx + 1
            ):
                status_style = NordColors.GREEN if selected else NordColors.RED
                status_text = "SELECTED" if selected else "EXCLUDED"
                table.add_row(
                    str(i), app, category, f"[{status_style}]{status_text}[/]"
                )

            console.print(table)
            console.print()
            console.print(f"[bold {NordColors.PURPLE}]Navigation and Options:[/]")
            console.print(
                f"[{NordColors.FROST_2}]1-{end_idx - start_idx}[/]: Toggle application selection"
            )
            console.print(f"[{NordColors.FROST_2}]N[/]: Next Page")
            console.print(f"[{NordColors.FROST_2}]P[/]: Previous Page")
            console.print(f"[{NordColors.FROST_2}]S[/]: Search Applications")
            console.print(f"[{NordColors.FROST_2}]B[/]: Back to Custom Package Menu")
            console.print()

            choice = pt_prompt(
                "Enter your choice: ",
                history=FileHistory(COMMAND_HISTORY),
                auto_suggest=AutoSuggestFromHistory(),
                style=get_prompt_style(),
            ).upper()

            if choice == "B":
                return
            elif choice == "N":
                if current_page < total_pages:
                    current_page += 1
            elif choice == "P":
                if current_page > 1:
                    current_page -= 1
            elif choice == "S":
                search_term = pt_prompt(
                    "Enter search term: ",
                    history=FileHistory(PACKAGE_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).lower()

                # Filter apps by search term
                matching_apps = [
                    (i + 1, app, category, selected)
                    for i, (app, category, selected) in enumerate(all_apps)
                    if search_term in app.lower() or search_term in category.lower()
                ]

                if not matching_apps:
                    print_warning(f"No applications found matching '{search_term}'")
                    time.sleep(1)
                    continue

                # Display matching apps
                search_table = Table(
                    title=f"Search Results for '{search_term}'",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_3}",
                    expand=True,
                )
                search_table.add_column("No.", style="bold", width=4)
                search_table.add_column("Application", style="bold")
                search_table.add_column("Category")
                search_table.add_column("Status", style="bold")

                for idx, app, category, selected in matching_apps:
                    status_style = NordColors.GREEN if selected else NordColors.RED
                    status_text = "SELECTED" if selected else "EXCLUDED"
                    search_table.add_row(
                        str(idx), app, category, f"[{status_style}]{status_text}[/]"
                    )

                console.print(search_table)
                console.print()

                search_choice = pt_prompt(
                    "Enter application number to toggle selection (or 'C' to cancel): ",
                    history=FileHistory(COMMAND_HISTORY),
                    auto_suggest=AutoSuggestFromHistory(),
                    style=get_prompt_style(),
                ).upper()

                if search_choice == "C":
                    continue

                try:
                    search_idx = int(search_choice) - 1
                    if 0 <= search_idx < len(all_apps):
                        app, category, selected = all_apps[search_idx]
                        all_apps[search_idx] = (app, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Application '{app}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid application number: {search_choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {search_choice}")
                    time.sleep(0.5)
            else:
                try:
                    idx = int(choice) - 1 + start_idx
                    if 0 <= idx < len(all_apps):
                        app, category, selected = all_apps[idx]
                        all_apps[idx] = (app, category, not selected)
                        status = "selected" if not selected else "deselected"
                        print_success(f"Application '{app}' {status}.")
                        time.sleep(0.5)
                    else:
                        print_error(f"Invalid application number: {choice}")
                        time.sleep(0.5)
                except ValueError:
                    print_error(f"Invalid input: {choice}")
                    time.sleep(0.5)

    # Update the selected apps based on user choices
    selected_apps = set()
    for app, _, selected in all_apps:
        if selected:
            selected_apps.add(app)

    install_state.selected_flatpak_apps = selected_apps


def add_custom_dnf_package() -> None:
    """Add a custom DNF package to the installation list."""
    console.clear()
    console.print(create_header())
    print_section("Add Custom DNF Package")

    # Get the custom package name from the user
    custom_package = pt_prompt(
        "Enter the DNF package name to add: ",
        history=FileHistory(PACKAGE_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not custom_package:
        print_warning("No package name provided, returning to menu.")
        time.sleep(1)
        return

    # Check if the package exists in DNF repositories
    spinner = SpinnerProgressManager("Package Verification")
    task_id = spinner.add_task(f"Checking if package '{custom_package}' exists...")

    try:
        spinner.start()

        # Use DNF to search for the package
        search_cmd = ["dnf", "search", custom_package]

        process = subprocess.Popen(
            search_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        stdout, stderr = process.communicate()

        # Check if the package exists in the output
        if "No matches found" in stdout or process.returncode != 0:
            spinner.complete_task(task_id, False)
            print_warning(f"Package '{custom_package}' not found in DNF repositories.")

            if Confirm.ask(
                f"[bold {NordColors.YELLOW}]Add package anyway?[/]", default=False
            ):
                # Add to selected packages list
                update_selected_packages()
                install_state.selected_dnf_packages.add(custom_package)
                print_success(f"Added '{custom_package}' to the installation list.")
        else:
            spinner.complete_task(task_id, True)

            # Add to selected packages if found
            update_selected_packages()
            install_state.selected_dnf_packages.add(custom_package)
            print_success(
                f"Package '{custom_package}' found and added to the installation list."
            )

    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error checking package: {e}")
    finally:
        spinner.stop()
        wait_for_key()


def add_custom_flatpak_app() -> None:
    """Add a custom Flatpak application to the installation list."""
    console.clear()
    console.print(create_header())
    print_section("Add Custom Flatpak Application")

    # Get the custom app ID from the user
    custom_app = pt_prompt(
        "Enter the Flatpak application ID to add (e.g., com.example.App): ",
        history=FileHistory(PACKAGE_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not custom_app:
        print_warning("No application ID provided, returning to menu.")
        time.sleep(1)
        return

    # Check if the app exists in Flatpak repositories
    spinner = SpinnerProgressManager("Application Verification")
    task_id = spinner.add_task(f"Checking if application '{custom_app}' exists...")

    try:
        spinner.start()

        # Use Flatpak to search for the app
        search_cmd = ["flatpak", "search", custom_app]

        process = subprocess.Popen(
            search_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        stdout, stderr = process.communicate()

        # Check if the app exists in the output
        if not stdout.strip() or process.returncode != 0:
            spinner.complete_task(task_id, False)
            print_warning(
                f"Application '{custom_app}' not found in Flatpak repositories."
            )

            if Confirm.ask(
                f"[bold {NordColors.YELLOW}]Add application anyway?[/]", default=False
            ):
                # Add to selected apps list
                update_selected_packages()
                install_state.selected_flatpak_apps.add(custom_app)
                print_success(f"Added '{custom_app}' to the installation list.")
        else:
            spinner.complete_task(task_id, True)

            # Add to selected apps if found
            update_selected_packages()
            install_state.selected_flatpak_apps.add(custom_app)
            print_success(
                f"Application '{custom_app}' found and added to the installation list."
            )

    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error checking application: {e}")
    finally:
        spinner.stop()
        wait_for_key()


def update_system() -> None:
    """Update the system using DNF."""
    console.clear()
    console.print(create_header())
    print_section("System Update")

    if not Confirm.ask(
        f"[bold {NordColors.YELLOW}]Do you want to update your system using DNF?[/]",
        default=True,
    ):
        print_warning("Update cancelled.")
        time.sleep(1)
        return

    # Create spinner for the update process
    spinner = SpinnerProgressManager("System Update")
    task_id = spinner.add_task("Updating system packages...")

    try:
        spinner.start()

        # Update the system using DNF
        spinner.update_task(task_id, "Running: sudo dnf update -y")

        cmd = ["sudo", "dnf", "update", "-y"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Track progress through the output
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if "Upgrading:" in line or "Installing:" in line or "Removing:" in line:
                    package = line.split()[1] if len(line.split()) > 1 else "package"
                    spinner.update_task(task_id, f"Processing {package}")

        # Wait for the process to complete
        return_code = process.wait()

        if return_code == 0:
            spinner.complete_task(task_id, True)
            print_success("System update completed successfully.")
        else:
            spinner.complete_task(task_id, False)
            print_error(f"System update failed with return code {return_code}")

    except Exception as e:
        spinner.complete_task(task_id, False)
        print_error(f"Error during system update: {e}")
    finally:
        spinner.stop()
        wait_for_key()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up session resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def display_status_bar() -> None:
    """Display the current status bar with installation information."""
    status_color = (
        NordColors.GREEN if install_state.installation_complete else NordColors.YELLOW
    )
    status_text = "INSTALLED" if install_state.installation_complete else "PENDING"

    dnf_count = len(install_state.selected_dnf_packages)
    flatpak_count = len(install_state.selected_flatpak_apps)

    last_installed_text = (
        f"Last installed: {install_state.last_installed.strftime('%Y-%m-%d %H:%M:%S')}"
        if install_state.last_installed
        else "Not installed yet"
    )

    console.print(
        Panel(
            Text.from_markup(
                f"[bold {status_color}]Status: {status_text}[/] | "
                f"DNF Packages: [bold]{dnf_count}[/] | "
                f"Flatpak Apps: [bold]{flatpak_count}[/] | "
                f"[dim]{last_installed_text}[/]"
            ),
            border_style=NordColors.FROST_4,
            padding=(0, 2),
        )
    )


def main_menu() -> None:
    menu_options = [
        ("1", "Install DNF Packages", install_dnf_packages),
        ("2", "Install Flatpak Apps", install_flatpak_apps),
        ("3", "Install Both DNF & Flatpak", install_all),
        ("4", "Manage DNF Package Categories", manage_dnf_categories),
        ("5", "Manage Flatpak App Categories", manage_flatpak_categories),
        ("6", "Custom Package Selection", custom_package_selection),
        ("7", "Update System", update_system),
        ("8", "System Information", display_system_info),
        ("H", "Show Help", show_help),
        ("0", "Exit", lambda: None),
    ]

    while True:
        console.clear()
        console.print(create_header())
        display_status_bar()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Main Menu[/]")
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True
        )
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")

        for option, description, _ in menu_options:
            table.add_row(option, description)

        console.print(table)
        command_history = FileHistory(COMMAND_HISTORY)
        choice = pt_prompt(
            "Enter your choice: ",
            history=command_history,
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()

        if choice == "0":
            console.print()
            console.print(
                Panel(
                    Text(
                        f"Thank you for using the Fedora Package Installer!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            sys.exit(0)
        else:
            for option, _, func in menu_options:
                if choice == option:
                    func()
                    wait_for_key()
                    break
            else:
                print_error(f"Invalid selection: {choice}")
                wait_for_key()


def main() -> None:
    # Initialize selected packages
    update_selected_packages()

    console.clear()
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
        cleanup()
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
