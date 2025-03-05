#!/usr/bin/env python3
"""
SSH Connection Manager (Advanced Terminal Application)
---------------------------------------------------------

A professional-grade terminal application for managing SSH connections with a
Nord-themed interface. This version provides a fully interactive, menu-driven
experience with dynamic ASCII banners, real-time progress tracking, and robust
error handling.

Usage:
  Run the script and use the numbered menu options to select a device:
    - Numbers 1-N: Connect to a Tailscale device by number
    - L1-LN:      Connect to a Local device by number
    - r:          Refresh device status
    - q:          Quit the application

Version: 8.5.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import atexit
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install python3-rich and python3-pyfiglet using Nala."
    )
    sys.exit(1)

# Enable rich traceback for debugging with local variables
install_rich_traceback(show_locals=True)

# Global Rich Console
console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "SSH Connector"
APP_SUBTITLE: str = "Professional Network Access Solution"
VERSION: str = "8.5.0"
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 1.5  # seconds for ping operations
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30  # seconds for commands
DEFAULT_SSH_PORT: int = 22
TRANSITION_DELAY: float = 0.3  # delay for UI transitions

# Directory and file for configuration
CONFIG_DIR: str = os.path.expanduser("~/.config/ssh_manager")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent styling"""

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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Returns a gradient of frost colors (cycled if more steps are needed)"""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return (
            frosts[:steps]
            if steps <= len(frosts)
            else frosts * ((steps // len(frosts)) + 1)
        )


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with connection details.
    """

    name: str
    ip_address: str
    device_type: str = "local"  # Either "tailscale" or "local"
    description: Optional[str] = None
    port: int = DEFAULT_SSH_PORT
    username: Optional[str] = None
    status: Optional[bool] = None  # True for online, False for offline, None unknown
    last_ping_time: float = field(default_factory=time.time)
    response_time: Optional[float] = None

    def get_connection_string(self, username: Optional[str] = None) -> str:
        """Generate an SSH connection string with username and auto-accept host keys."""
        user = username or self.username or DEFAULT_USERNAME
        if self.port == DEFAULT_SSH_PORT:
            return f"{user}@{self.ip_address}"
        return f"{user}@{self.ip_address} -p {self.port}"

    def get_status_indicator(self) -> Text:
        """Return a formatted status indicator as a Rich Text object."""
        if self.status is True:
            return Text("● ONLINE", style=f"bold {NordColors.GREEN}")
        elif self.status is False:
            return Text("● OFFLINE", style=f"bold {NordColors.RED}")
        return Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")


@dataclass
class AppConfig:
    """
    Configuration for SSH options.
    """

    default_username: str = DEFAULT_USERNAME
    ssh_options: Dict[str, Tuple[str, str]] = field(
        default_factory=lambda: {
            "ServerAliveInterval": ("30", "Interval (sec) to send keepalive packets"),
            "ServerAliveCountMax": ("3", "Packets to send before disconnecting"),
            "ConnectTimeout": ("10", "Timeout (sec) for establishing connection"),
            "StrictHostKeyChecking": ("accept-new", "Auto-accept new host keys"),
            "Compression": ("yes", "Enable compression"),
            "LogLevel": ("ERROR", "SSH logging verbosity"),
        }
    )
    last_refresh: float = field(default_factory=time.time)
    device_check_interval: int = 300  # seconds between automatic checks
    terminal_width: int = 80
    terminal_height: int = 24

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for JSON serialization."""
        return asdict(self)


# ----------------------------------------------------------------
# Static Device Lists
# ----------------------------------------------------------------
# Preconfigured Tailscale Devices
STATIC_TAILSCALE_DEVICES: List[Device] = [
    Device(
        name="ubuntu-server",
        ip_address="100.109.43.88",
        device_type="tailscale",
        description="Main Server",
        username="sawyer",
    ),
    Device(
        name="ubuntu-lenovo",
        ip_address="100.88.172.104",
        device_type="tailscale",
        description="Lenovo Laptop",
        username="sawyer",
    ),
    Device(
        name="raspberrypi-5",
        ip_address="100.105.117.18",
        device_type="tailscale",
        description="Raspberry Pi 5",
        username="sawyer",
    ),
    Device(
        name="raspberrypi-3",
        ip_address="100.116.191.42",
        device_type="tailscale",
        description="Raspberry Pi 3",
        username="sawyer",
    ),
    Device(
        name="ubuntu-server-vm-01",
        ip_address="100.84.119.114",
        device_type="tailscale",
        description="VM 01",
        username="sawyer",
    ),
    Device(
        name="ubuntu-server-vm-02",
        ip_address="100.122.237.56",
        device_type="tailscale",
        description="VM 02",
        username="sawyer",
    ),
    Device(
        name="ubuntu-server-vm-03",
        ip_address="100.97.229.120",
        device_type="tailscale",
        description="VM 03",
        username="sawyer",
    ),
    Device(
        name="ubuntu-server-vm-04",
        ip_address="100.73.171.7",
        device_type="tailscale",
        description="VM 04",
        username="sawyer",
    ),
]

# Preconfigured Local Devices
STATIC_LOCAL_DEVICES: List[Device] = [
    Device(
        name="ubuntu-server",
        ip_address="192.168.0.73",
        device_type="local",
        description="Main Server",
    ),
    Device(
        name="ubuntu-lenovo",
        ip_address="192.168.0.45",
        device_type="local",
        description="Lenovo Laptop",
    ),
    Device(
        name="raspberrypi-5",
        ip_address="192.168.0.40",
        device_type="local",
        description="Raspberry Pi 5",
    ),
    Device(
        name="raspberrypi-3",
        ip_address="192.168.0.100",
        device_type="local",
        description="Raspberry Pi 3",
    ),
]

# Combined Device List
DEVICES: List[Device] = STATIC_TAILSCALE_DEVICES + STATIC_LOCAL_DEVICES


# ----------------------------------------------------------------
# File System Operations (SSH Configuration)
# ----------------------------------------------------------------
def ensure_config_directory() -> None:
    """Ensure the configuration directory exists."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    """Save the application configuration to a JSON file."""
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    """Load configuration from JSON file or return default config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal display."""
    console.clear()


def create_header() -> Panel:
    """
    Generate a dynamic ASCII art header using Pyfiglet.
    The header adapts to terminal width and applies a frost gradient.
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts = ["slant", "small", "mini", "digital"]
    font_to_use = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]

    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        combined_text.append(Text(line, style=f"bold {colors[i % len(colors)]}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")

    return Panel(
        combined_text,
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step message for procedural instructions."""
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Print a section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a formatted panel with a title and message."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=style,
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
        box=box.ROUNDED,
    )
    console.print(panel)


def display_system_info() -> None:
    """Display system information (time, host, platform) in the header."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info = (
        f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Platform: {platform.system()}[/]"
    )
    console.print(Align.center(info))
    console.print()


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Execute a shell command with error handling and return the result."""
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup operations before application exit."""
    try:
        print_message("Cleaning up session resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """Handle interruption signals (SIGINT, SIGTERM) gracefully."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except (ValueError, AttributeError):
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Device Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
    """
    Ping a device to check connectivity and measure response time.
    Returns a tuple: (is_successful, response_time_in_ms)
    """
    start_time = time.time()
    try:
        if sys.platform == "win32":
            cmd = [
                "ping",
                "-n",
                str(PING_COUNT),
                "-w",
                str(int(PING_TIMEOUT * 1000)),
                ip_address,
            ]
        else:
            cmd = [
                "ping",
                "-c",
                str(PING_COUNT),
                "-W",
                str(int(PING_TIMEOUT)),
                ip_address,
            ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PING_TIMEOUT + 1,
        )
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # in milliseconds
        return (
            result.returncode == 0
        ), response_time if result.returncode == 0 else None
    except Exception:
        return False, None


def check_device_statuses(
    devices: List[Device], progress_callback: Optional[Callable[[int], None]] = None
) -> None:
    """
    Check connectivity status for a list of devices.
    Calls an optional progress_callback after each device check.
    """

    def check_single(device: Device, index: int) -> None:
        success, response_time = ping_device(device.ip_address)
        device.status = success
        device.response_time = response_time
        device.last_ping_time = time.time()
        if progress_callback:
            progress_callback(index)

    for i, device in enumerate(devices):
        check_single(device, i)


# ----------------------------------------------------------------
# UI Components for Device Display
# ----------------------------------------------------------------
def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a Rich table displaying device details in a compact format.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=False,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=3)
    table.add_column("Name", style=f"bold {NordColors.FROST_1}", width=20, no_wrap=True)
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}", width=15)
    table.add_column("Status", justify="center", width=12)
    table.add_column(
        "Label", style=f"dim {NordColors.SNOW_STORM_1}", width=15, no_wrap=True
    )
    online_count = sum(1 for d in devices if d.status is True)
    for idx, device in enumerate(devices, 1):
        table.add_row(
            f"{prefix}{idx}",
            Text(device.name, overflow="ellipsis"),
            device.ip_address,
            device.get_status_indicator(),
            Text(device.description or "", overflow="ellipsis"),
        )
    if devices:
        footer = Text.from_markup(
            f"[{NordColors.FROST_3}]{online_count}/{len(devices)} online[/]"
        )
        table.caption = footer
    return table


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username(default_username: str) -> str:
    """Prompt the user for a username with a default suggestion."""
    return Prompt.ask(
        f"Username for SSH connection [{default_username}]: ", default=default_username
    )


def connect_to_device(device: Device, username: Optional[str] = None) -> None:
    """
    Establish an SSH connection to the chosen device.
    Uses a progress spinner and builds the SSH command to include auto-accept keys.
    Always uses the Ubuntu ssh key located at /home/sawyer/.ssh/id_rsa.
    """
    clear_screen()
    console.print(create_header())
    effective_username = username or device.username or DEFAULT_USERNAME
    connection_info = (
        f"\n[bold {NordColors.FROST_2}]Device:[/] [bold {NordColors.SNOW_STORM_2}]{device.name}[/]\n"
        f"[bold {NordColors.FROST_2}]Address:[/] [bold {NordColors.SNOW_STORM_2}]{device.ip_address}[/]\n"
        f"[bold {NordColors.FROST_2}]User:[/] [bold {NordColors.SNOW_STORM_2}]{effective_username}[/]\n"
    )
    if device.description:
        connection_info += f"[bold {NordColors.FROST_2}]Description:[/] [bold {NordColors.SNOW_STORM_2}]{device.description}[/]\n"
    if device.port != DEFAULT_SSH_PORT:
        connection_info += f"[bold {NordColors.FROST_2}]Port:[/] [bold {NordColors.SNOW_STORM_2}]{device.port}[/]\n"
    console.print(
        Panel(
            Text.from_markup(connection_info),
            title=f"[bold {NordColors.FROST_3}]SSH Connection[/]",
            border_style=NordColors.FROST_3,
            padding=(1, 2),
            box=box.ROUNDED,
        )
    )
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                "[bold]Initializing secure channel...", total=None
            )
            time.sleep(0.4)
            progress.update(
                task_id, description=f"[bold]Negotiating encryption parameters..."
            )
            time.sleep(0.4)
            progress.update(
                task_id,
                description=f"[bold]Establishing SSH tunnel to {device.ip_address}...",
            )
            time.sleep(0.4)
            progress.update(
                task_id,
                description=f"[bold {NordColors.GREEN}]Connection established. Launching secure shell...",
            )
            time.sleep(0.4)
        # Build SSH command with options from configuration.
        # Always include the Ubuntu key with -i /home/sawyer/.ssh/id_rsa.
        ssh_args = [SSH_COMMAND, "-i", "/home/sawyer/.ssh/id_rsa"]
        config = load_config()
        for option, (value, _) in config.ssh_options.items():
            ssh_args.extend(["-o", f"{option}={value}"])
        if device.port != DEFAULT_SSH_PORT:
            ssh_args.extend(["-p", str(device.port)])
        ssh_args.append(f"{effective_username}@{device.ip_address}")
        os.execvp(SSH_COMMAND, ssh_args)
    except Exception as e:
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]Connection Error:[/] {str(e)}"
                ),
                border_style=NordColors.RED,
                title="Connection Failed",
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )
        print_section("Troubleshooting Tips")
        print_step("Check that the device is online and SSH is properly configured.")
        print_step("Verify that SSH is installed and running on the target device.")
        print_step("Ensure the correct username and IP address were used.")
        print_step("Try connecting manually with 'ssh -v' for verbose output.")
        Prompt.ask("Press Enter to return to the main menu")


# ----------------------------------------------------------------
# Device Status Refresh
# ----------------------------------------------------------------
def refresh_device_statuses(devices: List[Device]) -> None:
    """Refresh the status of all devices with a progress indicator."""
    clear_screen()
    console.print(create_header())
    display_panel(
        "Checking connectivity status of all devices",
        style=NordColors.FROST_3,
        title="Network Scan",
    )
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("Pinging devices"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning", total=len(devices), visible=True)

        def update_progress(index: int) -> None:
            progress.advance(scan_task)

        check_device_statuses(devices, update_progress)
    Prompt.ask("Press Enter to return to the main menu")


# ----------------------------------------------------------------
# Main Interactive Menu Loop
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point and interactive menu loop."""
    ensure_config_directory()
    config = load_config()
    devices = DEVICES
    try:
        # Initial network scan
        clear_screen()
        console.print(create_header())
        display_panel(
            "Scanning network for available devices",
            style=NordColors.FROST_3,
            title="Initialization",
        )
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("Pinging devices"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            scan_task = progress.add_task("Scanning", total=len(devices))

            def update_progress(index: int) -> None:
                progress.advance(scan_task)

            check_device_statuses(devices, update_progress)
        time.sleep(0.5)
        # Main application loop
        while True:
            term_width, term_height = shutil.get_terminal_size((80, 24))
            config.terminal_width = term_width
            config.terminal_height = term_height
            clear_screen()
            console.print(create_header())
            display_system_info()
            tailscale_devices = [d for d in devices if d.device_type == "tailscale"]
            local_devices = [d for d in devices if d.device_type == "local"]
            tailscale_table = create_device_table(
                tailscale_devices, "", "Tailscale Devices"
            )
            local_table = create_device_table(local_devices, "L", "Local Devices")
            if term_width >= 120:
                from rich.columns import Columns

                console.print(Columns([tailscale_table, local_table], padding=(0, 2)))
            else:
                console.print(tailscale_table)
                console.print()
                console.print(local_table)
            console.print()
            choice = (
                Prompt.ask(
                    "Enter choice (number for Tailscale, L# for Local, r:refresh, q:quit)"
                )
                .strip()
                .lower()
            )
            if choice in ("q", "quit", "exit"):
                clear_screen()
                console.print(
                    Panel(
                        Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                        border_style=NordColors.FROST_1,
                        padding=(1, 2),
                        box=box.ROUNDED,
                    )
                )
                break
            elif choice in ("r", "refresh"):
                refresh_device_statuses(devices)
            elif choice.startswith("l"):
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(local_devices):
                        device = local_devices[idx]
                        if device.status is False and not Confirm.ask(
                            "This device appears offline. Connect anyway?",
                            default=False,
                        ):
                            continue
                        uname = get_username(device.username or config.default_username)
                        connect_to_device(device, uname)
                    else:
                        display_panel(
                            f"Invalid device number: {choice}",
                            style=NordColors.RED,
                            title="Error",
                        )
                        Prompt.ask("Press Enter to continue")
                except ValueError:
                    display_panel(
                        f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                    )
                    Prompt.ask("Press Enter to continue")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(tailscale_devices):
                        device = tailscale_devices[idx]
                        if device.status is False and not Confirm.ask(
                            "This device appears offline. Connect anyway?",
                            default=False,
                        ):
                            continue
                        uname = get_username(device.username or config.default_username)
                        connect_to_device(device, uname)
                    else:
                        display_panel(
                            f"Invalid device number: {choice}",
                            style=NordColors.RED,
                            title="Error",
                        )
                        Prompt.ask("Press Enter to continue")
                except ValueError:
                    display_panel(
                        f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                    )
                    Prompt.ask("Press Enter to continue")
    except Exception as e:
        error_msg = str(e)
        tb_str = traceback.format_exc()
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]An unexpected error occurred:[/]\n\n{error_msg}\n\n[dim]{tb_str}[/dim]"
                ),
                border_style=NordColors.RED,
                title="Unhandled Error",
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        sys.exit(0)
    except Exception as e:
        display_panel(f"Unhandled error: {str(e)}", style=NordColors.RED, title="Error")
        console.print_exception()
        sys.exit(1)
