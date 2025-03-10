#!/usr/bin/env python3
"""
Fedora Package Installer
--------------------------------------------------
A fully interactive, menu-driven installer that installs a list
of system packages using DNF and Flatpak applications using Flatpak.
This script is designed for Fedora. It uses DNF (with sudo) to install
packages and assumes Flatpak (with the flathub remote) is already installed
and enabled.

The script uses Rich, Pyfiglet, prompt_toolkit, paramiko, and other libraries
to provide a production-grade CLI with stylish output, progress spinners,
and interactive prompts.

Note: This script automatically installs required Python dependencies
if they are not found.

Author: Your Name
Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import os
import sys
import time
import signal
import subprocess
import shutil
import getpass
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

# Function to install required dependencies for the non-root user when run with sudo
def install_dependencies():
    """Install required Python dependencies if they are missing."""
    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    if os.geteuid() != 0:
        print(f"Installing Python dependencies for user: {user}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        )
        return

    print(f"Running as sudo. Installing Python dependencies for user: {user}")
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
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        DownloadColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "paramiko", "rich", "pyfiglet", "prompt_toolkit"]
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
# Global Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = os.uname().nodename
VERSION: str = "1.0.0"
APP_NAME: str = "Fedora Package Installer"
APP_SUBTITLE: str = "DNF & Flatpak Package Manager"
HISTORY_DIR = os.path.expanduser(f"~{os.environ.get('SUDO_USER', os.environ.get('USER', getpass.getuser()))}/.fedora_pkg_installer")
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
PATH_HISTORY = os.path.join(HISTORY_DIR, "path_history")
for history_file in [COMMAND_HISTORY, PATH_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass

# ----------------------------------------------------------------
# Nord-Themed Colors (feel free to change as desired)
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
# Package Lists
# ----------------------------------------------------------------
PACKAGES: List[str] = [
    # Shells and editors
    "bash", "vim", "nano", "screen", "tmux", "neovim", "emacs", "micro",
    # System monitoring
    "htop", "btop", "tree", "iftop", "mtr", "iotop", "glances", "sysstat", "atop", "powertop", "nmon", "dstat", "bpytop",
    # Network and security
    "git", "openssh-server", "firewalld", "curl", "wget", "rsync", "sudo",
    "bash-completion", "net-tools", "nmap", "tcpdump", "fail2ban", "wireshark", "masscan", "netcat", "arp-scan", "hydra", "clamav", "lynis",
    # Core utilities
    "python3", "python3-pip", "ca-certificates", "dnf-plugins-core", "gnupg2", "gnupg", "pinentry", "seahorse", "keepassxc",
    # Development tools
    "gcc", "gcc-c++", "make", "cmake", "ninja-build", "meson", "gettext", "pkgconf",
    "python3-devel", "openssl-devel", "libffi-devel", "zlib-devel", "readline-devel",
    "bzip2-devel", "tk-devel", "xz", "ncurses-devel", "gdbm-devel", "nss-devel",
    "libxml2-devel", "xmlsec1-openssl-devel", "clang", "llvm", "golang", "gdb",
    "cargo", "rust", "jq", "yq", "yamllint", "shellcheck", "patch", "diffstat", "flex", "bison", "ctags", "cscope", "perf",
    # Network utilities
    "traceroute", "mtr", "bind-utils", "iproute", "iputils", "restic", "whois", "dnsmasq", "openvpn", "wireguard-tools", "nftables", "ipcalc",
    # Enhanced shells and utilities
    "zsh", "fzf", "bat", "ripgrep", "ncdu", "fd-find", "exa", "lsd", "mcfly", "autojump", "direnv", "zoxide", "progress", "pv", "tmux-powerline",
    # Container and development
    "docker", "docker-compose", "podman", "buildah", "skopeo", "nodejs", "npm", "yarn", "autoconf", "automake", "libtool",
    # Debugging and development utilities
    "strace", "ltrace", "valgrind", "tig", "colordiff", "the_silver_searcher",
    "xclip", "tmate", "iperf3", "httpie", "ngrep", "gron", "entr", "lsof", "socat", "psmisc",
    # Multimedia tools
    "ffmpeg", "imagemagick", "media-player-info", "audacity", "vlc", "obs-studio",
    # Database clients
    "mariadb", "postgresql", "sqlite", "redis", "mongo-tools", "pgadmin4",
    # Virtualization
    "virt-manager", "qemu-kvm", "libvirt", "virtualbox", "vagrant",
    # IDEs and advanced editors
    "code", "sublime-text", "jetbrains-idea-community", "pycharm-community", "visual-studio-code", "android-studio",
    # File compression and archiving
    "p7zip", "p7zip-plugins", "unrar", "unzip", "zip", "tar", "pigz", "lbzip2", "lz4",
    # Terminal multiplexers and prettifiers
    "byobu", "terminator", "kitty", "alacritty", "tilix", "ranger", "mc", "vifm", "nnn",
    # Office and productivity
    "libreoffice", "gimp", "inkscape", "dia", "calibre", "pandoc", "texlive",
    # System backup and restore
    "timeshift", "backintime", "duplicity", "borgbackup", "rclone", "syncthing",
    # Additional new packages
    "neofetch", "yt-dlp", "cmatrix", "tldr",
]

# Base Flatpak apps list (do not alter the ones below)
FLATPAK_APPS: List[str] = [
    "com.discordapp.Discord",
    "org.mozilla.Thunderbird",
    "org.signal.Signal",
    "com.spotify.Client",
    "md.obsidian.Obsidian",
    "com.bitwarden.desktop",
    "org.libreoffice.LibreOffice",
    "org.gnome.Tweaks",
    "org.videolan.VLC",
    "com.obsproject.Studio",
    "org.blender.Blender",
    "org.gimp.GIMP",
    "org.shotcut.Shotcut",
    "org.audacityteam.Audacity",
    "org.inkscape.Inkscape",
    "com.valvesoftware.Steam",
    "net.lutris.Lutris",
    "com.usebottles.bottles",
    "org.libretro.RetroArch",
    "com.github.tchx84.Flatseal",
    "net.davidotek.pupgui2",
    "org.prismlauncher.PrismLauncher",
    "org.gnome.Boxes",
    "org.remmina.Remmina",
    "com.rustdesk.RustDesk",
    "com.getpostman.Postman",
    "io.github.aandrew_me.ytdn",
    "com.calibre_ebook.calibre",
    "tv.plex.PlexDesktop",
    "org.filezillaproject.Filezilla",
    "com.github.k4zmu2a.spacecadetpinball",
    "org.raspberrypi.rpi-imager",
    "org.mozilla.firefox",
    "im.riot.Element",
    "org.gnome.Logs",
    "org.gnome.Disks",
    "org.gnome.SystemMonitor",
    # Additional top 10 popular Flatpak apps not already in the list:
    "org.telegram.desktop",
    "com.slack.Slack",
    "org.kde.krita",
    "org.kde.kdenlive",
    "org.kde.okular",
    "us.zoom.Zoom",
    "org.nextcloud.Nextcloud",
    "org.onlyoffice.desktopeditors",
    "com.github.micahflee.torbrowser-launcher",
    "org.chromium.Chromium",
]

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
    colors = [NordColors.FROST_1, NordColors.FROST_2, NordColors.FROST_3, NordColors.FROST_4]
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

def print_message(text: str, style: str = NordColors.FROST_2, prefix: str = "•") -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")

def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")

def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")

def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")

def wait_for_key() -> None:
    pt_prompt("Press Enter to continue...", style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}))

# ----------------------------------------------------------------
# Package Installation Functions
# ----------------------------------------------------------------
def install_dnf_packages() -> None:
    console.print(Panel("[bold]Installing DNF Packages...[/bold]", style=NordColors.PURPLE))
    cmd = ["sudo", "dnf", "install", "-y"] + PACKAGES
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[message_color]}]{task.fields[message]}"),
            console=console,
        ) as progress:
            task = progress.add_task("dnf-install", message="Installing system packages...", total=None, 
                                       task_fields={"message_color": NordColors.FROST_2})
            subprocess.check_call(cmd)
            progress.update(task, message="DNF packages installed successfully!", completed=100)
            time.sleep(0.5)
        print_success("DNF package installation completed.")
    except subprocess.CalledProcessError as e:
        print_error(f"DNF installation failed: {e}")

def install_flatpak_apps() -> None:
    console.print(Panel("[bold]Installing Flatpak Applications...[/bold]", style=NordColors.PURPLE))
    # Build the flatpak install command. We assume the remote 'flathub' is configured.
    cmd = ["flatpak", "install", "-y", "flathub"] + FLATPAK_APPS
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[message_color]}]{task.fields[message]}"),
            console=console,
        ) as progress:
            task = progress.add_task("flatpak-install", message="Installing Flatpak apps...", total=None,
                                       task_fields={"message_color": NordColors.FROST_2})
            subprocess.check_call(cmd)
            progress.update(task, message="Flatpak apps installed successfully!", completed=100)
            time.sleep(0.5)
        print_success("Flatpak application installation completed.")
    except subprocess.CalledProcessError as e:
        print_error(f"Flatpak installation failed: {e}")

def install_all() -> None:
    install_dnf_packages()
    install_flatpak_apps()

# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up before exit...", NordColors.FROST_3)

def signal_handler(sig: int, frame: Optional[object]) -> None:
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
def main_menu() -> None:
    menu_options = [
        ("1", "Install DNF Packages", install_dnf_packages),
        ("2", "Install Flatpak Apps", install_flatpak_apps),
        ("3", "Install Both DNF & Flatpak", install_all),
        ("0", "Exit", lambda: None),
    ]
    while True:
        console.clear()
        console.print(create_header())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"))
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Main Menu[/bold {NordColors.PURPLE}]")
        table = Table(show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True)
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")
        for option, description, _ in menu_options:
            table.add_row(option, description)
        console.print(table)
        choice = pt_prompt("Enter your choice: ", history=FileHistory(COMMAND_HISTORY), auto_suggest=AutoSuggestFromHistory(), style=PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})).strip()
        if choice == "0":
            console.print(Panel(Text("Thank you for using Fedora Package Installer!", style=f"bold {NordColors.FROST_2}"), border_style=Style(color=NordColors.FROST_1), padding=(1, 2)))
            break
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
    console.clear()
    main_menu()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
        cleanup()
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)