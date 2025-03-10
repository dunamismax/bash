Please review the following Python script and use it as a reference template for all future scripts you generate for me. The goal is for all future scripts to follow the structure, style, and best practices shown in this example. You should always use Rich, Pyfiglet, prompt toolkit (if it makes sense to) and paramiko and any other libraries you need for the task at hand. All of the scripts that you write should be primarily written for PopOS. You should always use Nala instead of Apt for all apt commands and always make sure to install the required 3rd party Python dependencies / libraries that are needed for the script at the start of execution. Please let me know once you have reviewed the below script in full and understand it:


#!/usr/bin/env python3
“””
Fedora SFTP Toolkit
—————————————————
A fully interactive, menu-driven SFTP toolkit for performing
SFTP file transfer operations with a production-grade, polished
CLI that integrates prompt_toolkit for auto-completion, Rich for
stylish output, and Pyfiglet for dynamic ASCII banners.

Features:
  • Interactive, menu-driven interface with dynamic ASCII banners.
  • SFTP operations including manual connection, device-based connection,
    directory listing, file upload/download, deletion, renaming, and remote
    directory management.
  • Predefined device lists (Tailscale and local) for quick connection setup.
  • Real-time progress tracking during file transfers.
  • Robust error handling and cross-platform compatibility.
  • Fully integrated prompt_toolkit auto-completion for both local and remote
    file/directory selection.
  • Nord-themed color styling throughout the application.

This script is adapted for Fedora Linux.
Version: 3.0.0
“””

# -—————————————————————
# Dependency Check and Imports
# -—————————————————————
import atexit
import os
import sys
import time
import socket
import getpass
import signal
import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any

def install_dependencies():
    “””Install required dependencies for the non-root user when run with sudo.”””
    required_packages = [“paramiko”, “rich”, “pyfiglet”, “prompt_toolkit”]
    user = os.environ.get(“SUDO_USER”, os.environ.get(“USER”, getpass.getuser()))
    if os.geteuid() != 0:
        print(f”Installing dependencies for user: {user}”)
        subprocess.check_call(
            [sys.executable, “-m”, “pip”, “install”, “—user”] + required_packages
        )
        return

    print(f”Running as sudo. Installing dependencies for user: {user}”)
    real_user_home = os.path.expanduser(f”~{user}”)
    try:
        subprocess.check_call(
            [“sudo”, “-u”, user, sys.executable, “-m”, “pip”, “install”, “—user”]
            + required_packages
        )
        print(f”Successfully installed dependencies for user: {user}”)
    except subprocess.CalledProcessError as e:
        print(f”Failed to install dependencies: {e}”)
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
    from rich.columns import Columns
    from rich.traceback import install as install_rich_traceback

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import PathCompleter, Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle

except ImportError:
    print(“Required libraries not found. Installing dependencies...”)
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [sys.executable, “-m”, “pip”, “install”, “paramiko”, “rich”, “pyfiglet”, “prompt_toolkit”]
            )
        else:
            install_dependencies()
        print(“Dependencies installed successfully. Restarting script...”)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f”Error installing dependencies: {e}”)
        print(“Please install the required packages manually:”)
        print(“pip install paramiko rich pyfiglet prompt_toolkit”)
        sys.exit(1)

install_rich_traceback(show_locals=True)

console: Console = Console()

# -—————————————————————
# Configuration & Constants
# -—————————————————————
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = os.environ.get(“SUDO_USER”) or os.environ.get(“USER”) or getpass.getuser()
SFTP_DEFAULT_PORT: int = 22
VERSION: str = “3.0.0”
APP_NAME: str = “Fedora SFTP Toolkit”
APP_SUBTITLE: str = “Advanced File Transfer Manager for Fedora”
OPERATION_TIMEOUT: int = 30  # seconds

if os.environ.get(“SUDO_USER”):
    DEFAULT_LOCAL_FOLDER = os.path.expanduser(f”~{os.environ.get(‘SUDO_USER’)}/Downloads”)
else:
    DEFAULT_LOCAL_FOLDER = os.path.expanduser(“~/Downloads”)

HISTORY_DIR = os.path.expanduser(f”~{os.environ.get(‘SUDO_USER’, DEFAULT_USERNAME)}/.sftp_toolkit”)
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, “command_history”)
PATH_HISTORY = os.path.join(HISTORY_DIR, “path_history”)
for history_file in [COMMAND_HISTORY, PATH_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, “w”) as f:
            pass

# -—————————————————————
# Nord-Themed Colors
# -—————————————————————
class NordColors:
    POLAR_NIGHT_1: str = “#2E3440”
    POLAR_NIGHT_2: str = “#3B4252”
    POLAR_NIGHT_3: str = “#434C5E”
    POLAR_NIGHT_4: str = “#4C566A”
    SNOW_STORM_1: str = “#D8DEE9”
    SNOW_STORM_2: str = “#E5E9F0”
    SNOW_STORM_3: str = “#ECEFF4”
    FROST_1: str = “#8FBCBB”
    FROST_2: str = “#88C0D0”
    FROST_3: str = “#81A1C1”
    FROST_4: str = “#5E81AC”
    RED: str = “#BF616A”
    ORANGE: str = “#D08770”
    YELLOW: str = “#EBCB8B”
    GREEN: str = “#A3BE8C”
    PURPLE: str = “#B48EAD”

# -—————————————————————
# Data Structures
# -—————————————————————
@dataclass
class Device:
    “””
    Represents an SFTP-accessible device with connection details.
    “””
    name: str
    ip_address: str
    description: str
    device_type: str = “local”  # ‘tailscale’ or ‘local’
    username: Optional[str] = None
    port: int = SFTP_DEFAULT_PORT
    favorite: bool = False
    last_connected: Optional[datetime] = None

    def get_favorite_indicator(self) -> str:
        “””Return a star indicator if the device is marked as favorite.”””
        return “★ “ if self.favorite else “”

@dataclass
class SFTPConnection:
    sftp: Optional[paramiko.SFTPClient] = None
    transport: Optional[paramiko.Transport] = None
    hostname: Optional[str] = None
    username: Optional[str] = None
    port: int = SFTP_DEFAULT_PORT
    connected_at: Optional[datetime] = None

    def is_connected(self) -> bool:
        return (
            self.sftp is not None and 
            self.transport is not None and 
            self.transport.is_active()
        )

    def get_connection_info(self) -> str:
        if not self.is_connected():
            return “Not connected”
        connected_time = (f”Connected at: {self.connected_at.strftime(‘%Y-%m-%d %H:%M:%S’)}”
                          if self.connected_at else “”)
        return f”{self.username}@{self.hostname}:{self.port} | {connected_time}”

sftp_connection = SFTPConnection()

# -—————————————————————
# Static Device Lists (Fedora-based names)
# -—————————————————————
STATIC_TAILSCALE_DEVICES: List[Device] = [
    Device(
        name=“fedora-server”,
        ip_address=“100.109.43.88”,
        device_type=“tailscale”,
        description=“Main Fedora Server”,
        username=“fedorauser”,
    ),
    Device(
        name=“fedora-workstation”,
        ip_address=“100.88.172.104”,
        device_type=“tailscale”,
        description=“Fedora Workstation”,
        username=“fedorauser”,
    ),
    Device(
        name=“fedora-vm-01”,
        ip_address=“100.84.119.114”,
        device_type=“tailscale”,
        description=“VM 01”,
        username=“fedorauser”,
    ),
    Device(
        name=“fedora-vm-02”,
        ip_address=“100.122.237.56”,
        device_type=“tailscale”,
        description=“VM 02”,
        username=“fedorauser”,
    ),
    Device(
        name=“fedora-vm-03”,
        ip_address=“100.97.229.120”,
        device_type=“tailscale”,
        description=“VM 03”,
        username=“fedorauser”,
    ),
    Device(
        name=“fedora-vm-04”,
        ip_address=“100.73.171.7”,
        device_type=“tailscale”,
        description=“VM 04”,
        username=“fedorauser”,
    ),
]

STATIC_LOCAL_DEVICES: List[Device] = [
    Device(
        name=“fedora-server”,
        ip_address=“192.168.68.52”,
        device_type=“local”,
        description=“Main Fedora Server”,
    ),
    Device(
        name=“fedora-workstation”,
        ip_address=“192.168.68.54”,
        device_type=“local”,
        description=“Fedora Workstation”,
    ),
]

def load_tailscale_devices() -> List[Device]:
    “””Return the preset Tailscale devices.”””
    return STATIC_TAILSCALE_DEVICES

def load_local_devices() -> List[Device]:
    “””Return the preset local network devices.”””
    return STATIC_LOCAL_DEVICES

# -—————————————————————
# Custom Remote Path Completer
# -—————————————————————
class RemotePathCompleter(Completer):
    def __init__(self, sftp_client, base_path=“.”):
        self.sftp = sftp_client
        self.base_path = base_path

    def get_completions(self, document, complete_event):
        text = document.text
        if not text or text == “.”:
            dir_path = self.base_path
            prefix = “”
        elif “/“ in text:
            dir_path = os.path.dirname(text) or “.”
            prefix = os.path.basename(text)
        else:
            dir_path = self.base_path
            prefix = text
        try:
            files = self.sftp.listdir(dir_path)
            for filename in files:
                if not filename.startswith(prefix):
                    continue
                full_path = os.path.join(dir_path, filename)
                try:
                    attrs = self.sftp.stat(full_path)
                    is_dir = attrs.st_mode & 0o40000  # directory check
                    suggestion = filename + “/“ if is_dir else filename
                    yield Completion(
                        suggestion,
                        start_position=-len(prefix),
                        display=suggestion,
                        style=“bg:#3B4252 fg:#A3BE8C” if is_dir else “bg:#3B4252 fg:#88C0D0”,
                    )
                except Exception:
                    continue
        except Exception:
            pass

# -—————————————————————
# UI Helper Functions
# -—————————————————————
def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = [“slant”, “big”, “digital”, “standard”, “small”]
    ascii_art = “”
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
    styled_text = “”
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace(“[“, “\\[“).replace(“]”, “\\]”)
        styled_text += f”[bold {color}]{escaped_line}[/]\n”
    border = f”[{NordColors.FROST_3}]{‘━’ * (adjusted_width - 6)}[/]”
    styled_text = border + “\n” + styled_text + border
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f”[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]”,
        title_align=“right”,
        subtitle=f”[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]”,
        subtitle_align=“center”,
    )
    return header_panel

def print_message(text: str, style: str = NordColors.FROST_2, prefix: str = “•”) -> None:
    console.print(f”[{style}]{prefix} {text}[/{style}]”)

def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, “✓”)

def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, “⚠”)

def print_error(message: str) -> None:
    print_message(message, NordColors.RED, “✗”)

def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, “→”)

def display_panel(message: str, style: str = NordColors.FROST_2, title: Optional[str] = None) -> None:
    panel = Panel(
        Text.from_markup(f”[{style}]{message}[/]”),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f”[bold {style}]{title}[/]” if title else None,
    )
    console.print(panel)

def print_section(title: str) -> None:
    console.print()
    console.print(f”[bold {NordColors.FROST_3}]{title}[/]”)
    console.print(f”[{NordColors.FROST_3}]{‘─’ * len(title)}[/]”)
    console.print()

def show_help() -> None:
    help_text = f”””
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-9, A, 0[/]:   Menu selection numbers
[bold {NordColors.FROST_2}]Tab[/]:         Auto-complete file paths and commands
[bold {NordColors.FROST_2}]Up/Down[/]:     Navigate command history
[bold {NordColors.FROST_2}]Ctrl+C[/]:      Cancel current operation
[bold {NordColors.FROST_2}]h[/]:           Show this help screen
“””
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f”[bold {NordColors.FROST_1}]Help & Commands[/]”,
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )

def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({“prompt”: f”bold {NordColors.PURPLE}”})

# -—————————————————————
# Environment Loader and SSH Key Helper Functions
# -—————————————————————
def load_env() -> Dict[str, str]:
    env_vars = {}
    env_file = os.path.join(HISTORY_DIR, “.env”)
    try:
        if os.path.exists(env_file):
            with open(env_file, “r”) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(“#”) and “=“ in line:
                        key, value = line.split(“=“, 1)
                        env_vars[key.strip()] = value.strip().strip(‘”’).strip(“’”)
                        os.environ[key.strip()] = value.strip().strip(‘”’).strip(“’”)
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Error loading .env file: {e}[/]”)
    return env_vars

def get_default_username() -> str:
    return os.environ.get(“SUDO_USER”) or os.environ.get(“USER”) or getpass.getuser()

def get_ssh_key_path() -> str:
    if os.environ.get(“SUDO_USER”):
        return os.path.expanduser(f”~{os.environ.get(‘SUDO_USER’)}/.ssh/id_rsa”)
    else:
        return os.path.expanduser(“~/.ssh/id_rsa”)

def load_private_key():
    key_path = get_ssh_key_path()
    try:
        key = paramiko.RSAKey.from_private_key_file(key_path)
        return key
    except paramiko.PasswordRequiredException:
        key_password = os.environ.get(“SSH_KEY_PASSWORD”)
        if not key_password:
            key_password = pt_prompt(“Enter SSH key password: “, is_password=True, style=get_prompt_style())
            os.environ[“SSH_KEY_PASSWORD”] = key_password
        try:
            key = paramiko.RSAKey.from_private_key_file(key_path, password=key_password)
            return key
        except Exception as e:
            console.print(f”[bold {NordColors.RED}]Error loading private key with passphrase: {e}[/]”)
            return None
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Error loading private key: {e}[/]”)
        return None

# -—————————————————————
# Signal Handling and Cleanup
# -—————————————————————
def cleanup() -> None:
    print_message(“Cleaning up session resources...”, NordColors.FROST_3)
    if sftp_connection.is_connected():
        try:
            if sftp_connection.sftp:
                sftp_connection.sftp.close()
            if sftp_connection.transport:
                sftp_connection.transport.close()
        except Exception as e:
            print_error(f”Error during connection cleanup: {e}”)

def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f”Process interrupted by {sig_name}”)
    except Exception:
        print_warning(f”Process interrupted by signal {sig}”)
    cleanup()
    sys.exit(128 + sig)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

# -—————————————————————
# Device Data Functions
# -—————————————————————
def select_device_menu() -> Optional[Device]:
    console.print(Panel(f”[bold {NordColors.FROST_2}]Select Device Type[/]”, expand=False))
    device_type = Prompt.ask(f”[bold {NordColors.PURPLE}]Choose device type[/]”, choices=[“tailscale”, “local”, “cancel”], default=“local”)
    if device_type == “cancel”:
        print_warning(“Device selection canceled”)
        return None
    devices = load_tailscale_devices() if device_type == “tailscale” else load_local_devices()
    table = Table(title=f”Available {device_type.capitalize()} Devices”, show_header=True, header_style=f”bold {NordColors.FROST_3}”)
    table.add_column(“No.”, style=“bold”, width=4)
    table.add_column(“Name”, style=“bold”)
    table.add_column(“IP Address”, style=f”bold {NordColors.GREEN}”)
    table.add_column(“Type”, style=“bold”)
    table.add_column(“Description”, style=“italic”)
    for idx, device in enumerate(devices, start=1):
        table.add_row(str(idx), f”{device.get_favorite_indicator()}{device.name}”, device.ip_address, device.device_type, device.description)
    console.print(table)
    console.print(f”[{NordColors.YELLOW}]Enter 0 to cancel selection[/]”)
    choice = IntPrompt.ask(f”[bold {NordColors.PURPLE}]Select device number[/]”, default=1)
    if choice == 0:
        print_warning(“Device selection canceled”)
        return None
    try:
        selected_device = devices[choice - 1]
        console.print(f”[bold {NordColors.GREEN}]Selected device:[/] {selected_device.name} ({selected_device.ip_address})”)
        return selected_device
    except (IndexError, TypeError):
        console.print(f”[bold {NordColors.RED}]Invalid selection. Please try again.[/]”)
        return None

def connect_device_via_menu() -> bool:
    device = select_device_menu()
    if device:
        return connect_sftp_device(device)
    return False

# -—————————————————————
# SFTP Connection Operations
# -—————————————————————
def connect_sftp() -> bool:
    console.print(Panel(f”[bold {NordColors.FROST_2}]SFTP Connection Setup[/]”, expand=False))
    hostname = pt_prompt(“Enter SFTP Hostname: “, history=FileHistory(COMMAND_HISTORY), auto_suggest=AutoSuggestFromHistory(), style=get_prompt_style())
    if not hostname:
        print_warning(“Connection canceled - hostname required”)
        return False
    port = IntPrompt.ask(f”[bold {NordColors.PURPLE}]Enter Port[/]”, default=SFTP_DEFAULT_PORT)
    username = pt_prompt(“Enter Username: “, default=get_default_username(), history=FileHistory(COMMAND_HISTORY), auto_suggest=AutoSuggestFromHistory(), style=get_prompt_style())
    key = load_private_key()
    if key is None:
        console.print(f”[bold {NordColors.RED}]Could not load SSH private key. Connection aborted.[/]”)
        return False
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_1}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“Connecting...”, message=“Initializing secure channel...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            transport = paramiko.Transport((hostname, port))
            progress.update(task, message=“Negotiating encryption parameters...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            transport.connect(username=username, pkey=key)
            progress.update(task, message=f”Establishing SFTP connection to {hostname}...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            sftp = paramiko.SFTPClient.from_transport(transport)
            progress.update(task, message=“Connection established successfully!”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        sftp_connection.sftp = sftp
        sftp_connection.transport = transport
        sftp_connection.hostname = hostname
        sftp_connection.username = username
        sftp_connection.port = port
        sftp_connection.connected_at = datetime.now()
        console.print(f”[bold {NordColors.GREEN}]Successfully connected to SFTP server using key-based authentication.[/]”)
        return True
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Error connecting to SFTP server: {e}[/]”)
        return False

def connect_sftp_device(device: Device) -> bool:
    console.print(Panel(f”[bold {NordColors.FROST_2}]Connecting to {device.name} ({device.ip_address})[/]”, expand=False))
    port = IntPrompt.ask(f”[bold {NordColors.PURPLE}]Enter Port[/]”, default=device.port)
    default_user = device.username if device.username else get_default_username()
    username = pt_prompt(“Enter Username: “, default=default_user, history=FileHistory(COMMAND_HISTORY), auto_suggest=AutoSuggestFromHistory(), style=get_prompt_style())
    key = load_private_key()
    if key is None:
        console.print(f”[bold {NordColors.RED}]Could not load SSH private key. Connection aborted.[/]”)
        return False
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_1}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“Connecting...”, message=“Initializing secure channel...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            transport = paramiko.Transport((device.ip_address, port))
            progress.update(task, message=“Negotiating encryption parameters...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            transport.connect(username=username, pkey=key)
            progress.update(task, message=f”Establishing SFTP connection to {device.name}...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            sftp = paramiko.SFTPClient.from_transport(transport)
            progress.update(task, message=“Connection established successfully!”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        sftp_connection.sftp = sftp
        sftp_connection.transport = transport
        sftp_connection.hostname = device.ip_address
        sftp_connection.username = username
        sftp_connection.port = port
        sftp_connection.connected_at = datetime.now()
        device.last_connected = datetime.now()
        console.print(f”[bold {NordColors.GREEN}]Successfully connected to {device.name} using key-based authentication.[/]”)
        return True
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Error connecting to {device.name}: {e}[/]”)
        return False

def disconnect_sftp() -> None:
    if not sftp_connection.is_connected():
        console.print(f”[bold {NordColors.YELLOW}]Not currently connected.[/]”)
        return
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_1}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“Disconnecting...”, message=“Closing SFTP channel...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            if sftp_connection.sftp:
                sftp_connection.sftp.close()
            progress.update(task, message=“Terminating transport...”, message_color=NordColors.FROST_2)
            time.sleep(0.5)
            if sftp_connection.transport:
                sftp_connection.transport.close()
            progress.update(task, message=“Connection closed successfully”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        sftp_connection.sftp = None
        sftp_connection.transport = None
        sftp_connection.connected_at = None
        console.print(f”[bold {NordColors.YELLOW}]Disconnected from SFTP server.[/]”)
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Error during disconnect: {e}[/]”)

def check_connection() -> bool:
    if sftp_connection.is_connected():
        return True
    console.print(f”[bold {NordColors.RED}]Not connected to any SFTP server.[/]”)
    if Confirm.ask(f”[bold {NordColors.YELLOW}]Would you like to establish a connection now?[/]”, default=True):
        connect_method = Prompt.ask(f”[bold {NordColors.PURPLE}]Connection method[/]”, choices=[“device”, “manual”, “cancel”], default=“device”)
        if connect_method == “cancel”:
            return False
        elif connect_method == “device”:
            return connect_device_via_menu()
        else:
            return connect_sftp()
    return False

# -—————————————————————
# SFTP File Operations
# -—————————————————————
def list_remote_directory() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    remote_path = pt_prompt(“Enter remote directory path: “,
                            completer=remote_completer,
                            default=“.”,
                            history=FileHistory(PATH_HISTORY),
                            auto_suggest=AutoSuggestFromHistory(),
                            style=get_prompt_style())
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_1}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“Listing...”, message=f”Retrieving directory listing for {remote_path}...”, message_color=NordColors.FROST_2)
            file_list = sftp_connection.sftp.listdir_attr(remote_path)
            progress.update(task, message=f”Retrieved {len(file_list)} items”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        sorted_items = sorted(file_list, key=lambda x: (not (x.st_mode & 0o40000), x.filename.lower()))
        table = Table(title=f”Contents of {remote_path}”, show_header=True, header_style=f”bold {NordColors.FROST_3}”, expand=True)
        table.add_column(“Type”, style=“bold”, width=4)
        table.add_column(“Name”, style=“bold”)
        table.add_column(“Size”, justify=“right”)
        table.add_column(“Permissions”, width=10)
        table.add_column(“Modified Time”)
        dir_count = 0
        file_count = 0
        total_size = 0
        for item in sorted_items:
            is_dir = item.st_mode & 0o40000
            if is_dir:
                size_str = “<DIR>”
                dir_count += 1
            else:
                size = item.st_size
                total_size += size
                if size < 1024:
                    size_str = f”{size} B”
                elif size < 1024 * 1024:
                    size_str = f”{size / 1024:.1f} KB”
                elif size < 1024 * 1024 * 1024:
                    size_str = f”{size / (1024 * 1024):.1f} MB”
                else:
                    size_str = f”{size / (1024 * 1024 * 1024):.2f} GB”
                file_count += 1
            mod_time = time.strftime(“%Y-%m-%d %H:%M:%S”, time.localtime(item.st_mtime))
            perm = “”
            modes = [(0o400, “r”), (0o200, “w”), (0o100, “x”),
                     (0o040, “r”), (0o020, “w”), (0o010, “x”),
                     (0o004, “r”), (0o002, “w”), (0o001, “x”)]
            for mask, char in modes:
                perm += char if (item.st_mode & mask) else “-“
            type_indicator = “📁” if is_dir else “📄”
            name_style = f”link {NordColors.FROST_3}” if is_dir else “”
            table.add_row(type_indicator, f”[{name_style}]{item.filename}[/]”, size_str, perm, mod_time)
        console.print(table)
        size_display = (f”{total_size / 1024:.2f} KB” if total_size < 1024 * 1024 else f”{total_size / (1024 * 1024):.2f} MB”)
        console.print(f”[{NordColors.FROST_3}]Total: {dir_count} directories, {file_count} files, {size_display}[/]”)
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Failed to list directory: {e}[/]”)

def upload_file() -> None:
    if not check_connection():
        return
    path_completer = PathCompleter(only_directories=False, expanduser=True)
    local_path = pt_prompt(“Enter the local file path to upload: “,
                           completer=path_completer,
                           default=DEFAULT_LOCAL_FOLDER,
                           history=FileHistory(PATH_HISTORY),
                           auto_suggest=AutoSuggestFromHistory(),
                           style=get_prompt_style())
    if not os.path.isfile(local_path):
        console.print(f”[bold {NordColors.RED}]Local file does not exist: {local_path}[/]”)
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    default_remote_name = os.path.basename(local_path)
    remote_path = pt_prompt(“Enter the remote destination path: “,
                            completer=remote_completer,
                            default=default_remote_name,
                            history=FileHistory(PATH_HISTORY),
                            auto_suggest=AutoSuggestFromHistory(),
                            style=get_prompt_style())
    file_size = os.path.getsize(local_path)
    if not Confirm.ask(f”[bold {NordColors.YELLOW}]Upload {os.path.basename(local_path)} ({file_size / 1024:.1f} KB) to {remote_path}?[/]”, default=True):
        print_warning(“Upload canceled”)
        return

    def progress_callback(transferred, total):
        progress.update(task, completed=transferred)

    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_2}”),
                      TextColumn(f”[bold {NordColors.FROST_2}]Uploading...”),
                      BarColumn(),
                      TaskProgressColumn(),
                      DownloadColumn(),
                      TimeRemainingColumn(),
                      console=console) as progress:
            task = progress.add_task(“upload”, total=file_size)
            sftp_connection.sftp.put(local_path, remote_path, callback=progress_callback)
        print_success(f”Upload completed: {local_path} → {remote_path}”)
    except Exception as e:
        print_error(f”Upload failed: {e}”)

def download_file() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    remote_path = pt_prompt(“Enter the remote file path to download: “,
                            completer=remote_completer,
                            history=FileHistory(PATH_HISTORY),
                            auto_suggest=AutoSuggestFromHistory(),
                            style=get_prompt_style())
    path_completer = PathCompleter(only_directories=True, expanduser=True)
    local_dest = pt_prompt(“Enter the local destination directory: “,
                           completer=path_completer,
                           default=DEFAULT_LOCAL_FOLDER,
                           history=FileHistory(PATH_HISTORY),
                           auto_suggest=AutoSuggestFromHistory(),
                           style=get_prompt_style())
    if not os.path.isdir(local_dest):
        console.print(f”[bold {NordColors.RED}]Local directory does not exist: {local_dest}[/]”)
        if Confirm.ask(f”[bold {NordColors.YELLOW}]Would you like to create this directory?[/]”, default=True):
            try:
                os.makedirs(local_dest, exist_ok=True)
                print_success(f”Created directory: {local_dest}”)
            except Exception as e:
                print_error(f”Failed to create directory: {e}”)
                return
        else:
            return
    try:
        file_stat = sftp_connection.sftp.stat(remote_path)
        file_size = file_stat.st_size
        if file_stat.st_mode & 0o40000:
            print_error(f”{remote_path} is a directory, not a file”)
            return
        remote_filename = os.path.basename(remote_path)
        dest_path = os.path.join(local_dest, remote_filename)
        if os.path.exists(dest_path):
            if not Confirm.ask(f”[bold {NordColors.YELLOW}]File {dest_path} already exists. Overwrite?[/]”, default=False):
                print_warning(“Download canceled”)
                return
    except Exception as e:
        console.print(f”[bold {NordColors.RED}]Could not retrieve file information: {e}[/]”)
        return
    if not Confirm.ask(f”[bold {NordColors.YELLOW}]Download {os.path.basename(remote_path)} ({file_size / 1024:.1f} KB) to {local_dest}?[/]”, default=True):
        print_warning(“Download canceled”)
        return

    def progress_callback(transferred, total):
        progress.update(task, completed=transferred)

    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_2}”),
                      TextColumn(f”[bold {NordColors.FROST_2}]Downloading...”),
                      BarColumn(),
                      TaskProgressColumn(),
                      DownloadColumn(),
                      TimeRemainingColumn(),
                      console=console) as progress:
            task = progress.add_task(“download”, total=file_size)
            sftp_connection.sftp.get(remote_path, dest_path, callback=progress_callback)
        print_success(f”Download completed: {remote_path} → {dest_path}”)
    except Exception as e:
        print_error(f”Download failed: {e}”)

def delete_remote_file() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    remote_path = pt_prompt(“Enter the remote file path to delete: “,
                            completer=remote_completer,
                            history=FileHistory(PATH_HISTORY),
                            auto_suggest=AutoSuggestFromHistory(),
                            style=get_prompt_style())
    try:
        stat = sftp_connection.sftp.stat(remote_path)
        is_dir = stat.st_mode & 0o40000
    except Exception as e:
        print_error(f”Cannot access {remote_path}: {e}”)
        return
    if is_dir:
        print_warning(f”{remote_path} is a directory. Use the delete directory option instead.”)
        return
    if Confirm.ask(f”[bold {NordColors.RED}]Are you sure you want to delete {remote_path}?[/]”, default=False):
        try:
            with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.RED}”),
                          TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                          console=console) as progress:
                task = progress.add_task(“deleting”, message=f”Deleting {remote_path}...”, message_color=NordColors.RED)
                sftp_connection.sftp.remove(remote_path)
                progress.update(task, message=f”File deleted successfully”, message_color=NordColors.GREEN)
                time.sleep(0.5)
            print_success(f”Deleted remote file: {remote_path}”)
        except Exception as e:
            print_error(f”Failed to delete file: {e}”)

def rename_remote_file() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    old_name = pt_prompt(“Enter the current remote file path: “,
                         completer=remote_completer,
                         history=FileHistory(PATH_HISTORY),
                         auto_suggest=AutoSuggestFromHistory(),
                         style=get_prompt_style())
    try:
        stat = sftp_connection.sftp.stat(old_name)
        is_dir = stat.st_mode & 0o40000
    except Exception as e:
        print_error(f”Cannot access {old_name}: {e}”)
        return
    parent_dir = os.path.dirname(old_name)
    file_name = os.path.basename(old_name)
    same_dir_completer = RemotePathCompleter(sftp_connection.sftp, parent_dir if parent_dir else “.”)
    new_name = pt_prompt(“Enter the new remote file name/path: “,
                         completer=same_dir_completer,
                         default=file_name,
                         history=FileHistory(PATH_HISTORY),
                         auto_suggest=AutoSuggestFromHistory(),
                         style=get_prompt_style())
    if “/“ not in new_name and parent_dir:
        new_name = f”{parent_dir}/{new_name}”
    entity_type = “directory” if is_dir else “file”
    if not Confirm.ask(f”[bold {NordColors.YELLOW}]Rename {entity_type} from {old_name} to {new_name}?[/]”, default=True):
        print_warning(“Rename canceled”)
        return
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_2}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“renaming”, message=f”Renaming {old_name} to {new_name}...”, message_color=NordColors.FROST_2)
            sftp_connection.sftp.rename(old_name, new_name)
            progress.update(task, message=f”{entity_type.capitalize()} renamed successfully”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        print_success(f”Renamed remote {entity_type}: {old_name} → {new_name}”)
    except Exception as e:
        print_error(f”Failed to rename {entity_type}: {e}”)

def create_remote_directory() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    remote_dir = pt_prompt(“Enter the remote directory to create: “,
                           completer=remote_completer,
                           history=FileHistory(PATH_HISTORY),
                           auto_suggest=AutoSuggestFromHistory(),
                           style=get_prompt_style())
    try:
        sftp_connection.sftp.stat(remote_dir)
        print_warning(f”Directory {remote_dir} already exists”)
        return
    except IOError:
        pass
    try:
        with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.FROST_2}”),
                      TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                      console=console) as progress:
            task = progress.add_task(“creating”, message=f”Creating directory {remote_dir}...”, message_color=NordColors.FROST_2)
            sftp_connection.sftp.mkdir(remote_dir)
            progress.update(task, message=f”Directory created successfully”, message_color=NordColors.GREEN)
            time.sleep(0.5)
        print_success(f”Created remote directory: {remote_dir}”)
    except Exception as e:
        print_error(f”Failed to create directory: {e}”)

def delete_remote_directory() -> None:
    if not check_connection():
        return
    remote_completer = RemotePathCompleter(sftp_connection.sftp)
    remote_dir = pt_prompt(“Enter the remote directory to delete: “,
                           completer=remote_completer,
                           history=FileHistory(PATH_HISTORY),
                           auto_suggest=AutoSuggestFromHistory(),
                           style=get_prompt_style())
    try:
        stat = sftp_connection.sftp.stat(remote_dir)
        is_dir = stat.st_mode & 0o40000
        if not is_dir:
            print_error(f”{remote_dir} is not a directory.”)
            return
    except Exception as e:
        print_error(f”Cannot access {remote_dir}: {e}”)
        return
    try:
        contents = sftp_connection.sftp.listdir(remote_dir)
        if contents:
            print_warning(f”Directory is not empty. Contains {len(contents)} items.”)
            if not Confirm.ask(f”[bold {NordColors.RED}]Force delete non-empty directory?[/]”, default=False):
                return
            if Confirm.ask(f”[bold {NordColors.RED}]WARNING: This will delete ALL contents. Proceed?[/]”, default=False):
                def rm_rf(path):
                    try:
                        files = sftp_connection.sftp.listdir(path)
                        for f in files:
                            filepath = os.path.join(path, f)
                            try:
                                try:
                                    sftp_connection.sftp.listdir(filepath)
                                    rm_rf(filepath)
                                except:
                                    sftp_connection.sftp.remove(filepath)
                                    print_step(f”Deleted file: {filepath}”)
                            except Exception as e:
                                print_error(f”Failed to remove {filepath}: {e}”)
                                return False
                        sftp_connection.sftp.rmdir(path)
                        return True
                    except Exception as e:
                        print_error(f”Failed operation on {path}: {e}”)
                        return False
                with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.RED}”),
                              TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                              console=console) as progress:
                    task = progress.add_task(“deleting”, message=f”Recursively deleting {remote_dir}...”, message_color=NordColors.RED)
                    success = rm_rf(remote_dir)
                    if success:
                        progress.update(task, message=f”Directory and all contents deleted”, message_color=NordColors.GREEN)
                        print_success(f”Recursively deleted remote directory: {remote_dir}”)
                    else:
                        progress.update(task, message=f”Failed to delete all contents”, message_color=NordColors.RED)
                        print_error(f”Failed to recursively delete directory: {remote_dir}”)
                return
            else:
                return
    except Exception as e:
        print_error(f”Failed to check directory contents: {e}”)
        return
    if Confirm.ask(f”[bold {NordColors.RED}]Are you sure you want to delete this directory?[/]”, default=False):
        try:
            with Progress(SpinnerColumn(“dots”, style=f”bold {NordColors.RED}”),
                          TextColumn(“[bold {task.fields[message_color]}]{task.fields[message]}”),
                          console=console) as progress:
                task = progress.add_task(“deleting”, message=f”Deleting directory {remote_dir}...”, message_color=NordColors.RED)
                sftp_connection.sftp.rmdir(remote_dir)
                progress.update(task, message=f”Directory deleted successfully”, message_color=NordColors.GREEN)
                time.sleep(0.5)
            print_success(f”Deleted remote directory: {remote_dir}”)
        except Exception as e:
            print_error(f”Failed to delete directory: {e}”)

# -—————————————————————
# Main Menu and Program Control
# -—————————————————————
def display_status_bar() -> None:
    connection_status = sftp_connection.get_connection_info()
    status_color = NordColors.GREEN if sftp_connection.is_connected() else NordColors.RED
    status_text = “CONNECTED” if sftp_connection.is_connected() else “DISCONNECTED”
    console.print(Panel(Text.from_markup(f”[bold {status_color}]Status: {status_text}[/] | [dim]{connection_status}[/]”),
                        border_style=NordColors.FROST_4,
                        padding=(0, 2)))

def wait_for_key() -> None:
    pt_prompt(“Press Enter to continue...”, style=PtStyle.from_dict({“prompt”: f”{NordColors.FROST_2}”}))

def main_menu() -> None:
    menu_options = [
        (“1”, “Connect to SFTP Server (manual)”, lambda: connect_sftp()),
        (“2”, “Connect to SFTP Server (select device)”, lambda: connect_device_via_menu()),
        (“3”, “List Remote Directory”, lambda: list_remote_directory()),
        (“4”, “Upload File”, lambda: upload_file()),
        (“5”, “Download File”, lambda: download_file()),
        (“6”, “Rename Remote File/Directory”, lambda: rename_remote_file()),
        (“7”, “Create Remote Directory”, lambda: create_remote_directory()),
        (“8”, “Delete Remote File”, lambda: delete_remote_file()),
        (“9”, “Delete Remote Directory”, lambda: delete_remote_directory()),
        (“A”, “Disconnect from SFTP Server”, lambda: disconnect_sftp()),
        (“H”, “Show Help”, lambda: show_help()),
        (“0”, “Exit”, lambda: None),
    ]
    while True:
        console.clear()
        console.print(create_header())
        display_status_bar()
        current_time = datetime.now().strftime(“%Y-%m-%d %H:%M:%S”)
        console.print(Align.center(f”[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]”))
        console.print()
        console.print(f”[bold {NordColors.PURPLE}]SFTP Toolkit Menu[/]”)
        table = Table(show_header=True, header_style=f”bold {NordColors.FROST_3}”, expand=True)
        table.add_column(“Option”, style=“bold”, width=8)
        table.add_column(“Description”, style=“bold”)
        for option, description, _ in menu_options:
            if option in [“3”, “4”, “5”, “6”, “7”, “8”, “9”] and not sftp_connection.is_connected():
                table.add_row(option, f”[dim]{description} (requires connection)[/dim]”)
            elif option == “A” and not sftp_connection.is_connected():
                table.add_row(option, f”[dim]{description} (not connected)[/dim]”)
            else:
                table.add_row(option, description)
        console.print(table)
        command_history = FileHistory(COMMAND_HISTORY)
        choice = pt_prompt(“Enter your choice: “, history=command_history, auto_suggest=AutoSuggestFromHistory(), style=get_prompt_style()).upper()
        if choice == “0”:
            if sftp_connection.is_connected():
                disconnect_sftp()
            console.print()
            console.print(Panel(Text(f”Thank you for using SFTP Toolkit!”, style=f”bold {NordColors.FROST_2}”),
                                border_style=Style(color=NordColors.FROST_1),
                                padding=(1, 2)))
            sys.exit(0)
        else:
            for option, _, func in menu_options:
                if choice == option:
                    func()
                    wait_for_key()
                    break
            else:
                print_error(f”Invalid selection: {choice}”)
                wait_for_key()

def main() -> None:
    load_env()
    console.clear()
    main_menu()

if __name__ == “__main__”:
    try:
        main()
    except KeyboardInterrupt:
        print_warning(“Operation cancelled by user”)
        if sftp_connection.is_connected():
            disconnect_sftp()
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f”An unexpected error occurred: {e}”)
         sys.exit(1)