#!/usr/bin/env python3
"""
SSH Connection Manager
----------------------------------

A professional-grade terminal application for managing SSH connections with a
Nord-themed interface. This interactive CLI allows you to connect to Tailscale
and local devices, check device status, and manage SSH connections—all with
dynamic ASCII banners, progress tracking, and comprehensive error handling
for a production-grade user experience.

Usage:
  Run the script and follow the interactive menu options.

Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import os
import signal
import subprocess
import sys
import time
import shutil
import socket
import json
import traceback
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

# Enable rich traceback for debugging
install_rich_traceback(show_locals=True)
console: Console = Console()


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent styling."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Return a gradient of frost colors for dynamic banner styling."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "SSH Manager"
APP_SUBTITLE = "Professional Network Connection Tool"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
DEFAULT_USERNAME = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
SSH_COMMAND = "ssh"
PING_TIMEOUT = 1.5  # seconds for ping operations
PING_COUNT = 1
OPERATION_TIMEOUT = 30  # seconds for commands
DEFAULT_SSH_PORT = 22

# Directory and file for configuration
CONFIG_DIR = os.path.expanduser("~/.config/ssh_manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with connection details.

    Attributes:
        name: The device's name.
        ip_address: The IP address of the device.
        device_type: Either "tailscale" or "local".
        description: Optional description of the device.
        port: SSH port number.
        username: Optional username for SSH connection.
        status: True for online, False for offline, None for unknown.
        last_ping_time: When the device was last pinged.
        response_time: Response time in milliseconds, if available.
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
        """Generate an SSH connection string with username."""
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

    Attributes:
        default_username: Default username for SSH connections.
        ssh_options: Dictionary of SSH options and descriptions.
        last_refresh: Timestamp of last device status refresh.
        device_check_interval: Seconds between automatic status checks.
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
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """
    Create a dynamic ASCII banner header using Pyfiglet.
    The banner adapts to terminal width and applies a Nord-themed gradient.
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
    text_lines = []
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        text_lines.append(Text(line, style=f"bold {color}"))
    combined_text = Text()
    for i, line in enumerate(text_lines):
        combined_text.append(line)
        if i < len(text_lines) - 1:
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
    """Print a formatted message with a given prefix and style."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print an error message in red."""
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    """Print a success message in green."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    """Print a step message for procedural instructions."""
    print_message(message, NordColors.FROST_2, "→")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display a formatted panel with a title and message."""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(cmd: List[str]) -> Tuple[int, str]:
    """
    Execute a shell command and return its exit code and output.

    Args:
        cmd: List of command and arguments.

    Returns:
        Tuple containing (exit_code, output).

    Raises:
        Exception: If the command fails or times out.
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OPERATION_TIMEOUT,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception("Command timed out.")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup operations before exiting."""
    try:
        config = load_config()
        config.last_refresh = time.time()
        save_config(config)
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig, frame) -> None:
    """Gracefully handle termination signals (SIGINT, SIGTERM)."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ----------------------------------------------------------------
# Device Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
    """
    Ping a device to check connectivity and measure response time.

    Args:
        ip_address: The IP address to ping.

    Returns:
        A tuple: (is_successful, response_time_in_ms)
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
    devices: List[Device],
    progress_callback: Optional[Callable[[int, Device], None]] = None,
) -> None:
    """
    Check connectivity status for a list of devices.

    Args:
        devices: A list of Device objects to check.
        progress_callback: Optional function to call after each device check.
    """
    for i, device in enumerate(devices):
        success, response_time = ping_device(device.ip_address)
        device.status = success
        device.response_time = response_time
        device.last_ping_time = time.time()
        if progress_callback:
            progress_callback(i, device)


# ----------------------------------------------------------------
# UI Components for Device Display
# ----------------------------------------------------------------
def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a Rich table displaying device details.

    Args:
        devices: List of Device objects to display.
        prefix: Prefix for device numbering (e.g., "L" for local devices).
        title: Title for the table.

    Returns:
        A Rich Table object.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=title,
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Name", style=f"bold {NordColors.FROST_1}", width=20)
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}", width=15)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Response", justify="right", width=10)
    table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}", width=20)

    # Add rows
    for idx, device in enumerate(devices, 1):
        # Format response time
        response_time = (
            f"{device.response_time:.1f} ms"
            if device.response_time is not None
            else "—"
        )

        table.add_row(
            f"{prefix}{idx}",
            device.name,
            device.ip_address,
            device.get_status_indicator(),
            response_time,
            device.description or "",
        )

    return table


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username(default_username: str) -> str:
    """Prompt the user for a username with a default suggestion."""
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]Username for SSH connection[/]",
        default=default_username,
    )


def connect_to_device(device: Device, username: Optional[str] = None) -> None:
    """
    Establish an SSH connection to the chosen device.

    Args:
        device: The Device object to connect to.
        username: Optional username override.
    """
    clear_screen()
    console.print(create_header())
    display_panel(
        "SSH Connection",
        f"Connecting to {device.name} ({device.ip_address})",
        NordColors.FROST_2,
    )

    effective_username = username or device.username or DEFAULT_USERNAME

    # Connection details
    details_table = Table(show_header=False, box=None, padding=(0, 3))
    details_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    details_table.add_column("Value", style=f"{NordColors.SNOW_STORM_2}")

    details_table.add_row("Address", device.ip_address)
    details_table.add_row("User", effective_username)
    if device.description:
        details_table.add_row("Description", device.description)
    if device.port != DEFAULT_SSH_PORT:
        details_table.add_row("Port", str(device.port))
    details_table.add_row("Status", "Online" if device.status else "Unknown/Offline")
    if device.response_time:
        details_table.add_row("Latency", f"{device.response_time:.1f} ms")

    console.print(details_table)
    console.print()

    # Connection progress
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Create main connection task
            task_id = progress.add_task(
                f"[{NordColors.FROST_2}]Establishing connection...", total=100
            )

            # Animated progress for connection steps
            for step, pct in [
                (f"[{NordColors.FROST_2}]Resolving hostname...", 20),
                (f"[{NordColors.FROST_2}]Establishing connection...", 40),
                (f"[{NordColors.FROST_2}]Negotiating SSH protocol...", 60),
                (f"[{NordColors.FROST_2}]Authenticating...", 80),
                (f"[{NordColors.GREEN}]Connection established.", 100),
            ]:
                time.sleep(0.3)
                progress.update(task_id, description=step, completed=pct)

        # Build SSH command with options from configuration
        ssh_args = [SSH_COMMAND]
        config = load_config()

        # Add SSH options
        for option, (value, _) in config.ssh_options.items():
            ssh_args.extend(["-o", f"{option}={value}"])

        # Add port if non-standard
        if device.port != DEFAULT_SSH_PORT:
            ssh_args.extend(["-p", str(device.port)])

        # Add destination
        ssh_args.append(f"{effective_username}@{device.ip_address}")

        # Execute SSH command
        print_success(f"Connecting to {device.name} as {effective_username}...")
        os.execvp(SSH_COMMAND, ssh_args)

    except Exception as e:
        print_error(f"Connection failed: {str(e)}")
        console.print_exception()
        print_section("Troubleshooting Tips")
        print_step("Check that the device is online using ping.")
        print_step("Verify that the SSH service is running on the target device.")
        print_step("Check your SSH key configuration.")
        print_step("Try connecting with verbose output: ssh -v user@host")

        Prompt.ask("Press Enter to return to the main menu")


def print_section(title: str) -> None:
    """Print a section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


# ----------------------------------------------------------------
# Device Status Refresh
# ----------------------------------------------------------------
def refresh_device_statuses(devices: List[Device]) -> None:
    """
    Refresh the status of all devices with progress visualization.

    Args:
        devices: List of Device objects to refresh.
    """
    clear_screen()
    console.print(create_header())
    display_panel(
        "Network Scan",
        "Checking connectivity for all configured devices",
        NordColors.FROST_3,
    )

    # Create task for progress tracking
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task(
            f"[{NordColors.FROST_2}]Scanning", total=len(devices)
        )

        def update_progress(index: int, device: Device) -> None:
            progress.advance(scan_task)
            progress.update(
                scan_task,
                description=f"[{NordColors.FROST_2}]Checking {device.name} ({device.ip_address})",
            )

        check_device_statuses(devices, update_progress)

    # Show summary
    online_count = sum(1 for d in devices if d.status is True)
    offline_count = sum(1 for d in devices if d.status is False)

    print_success(f"Scan complete: {online_count} online, {offline_count} offline")

    # Update last refresh time in config
    config = load_config()
    config.last_refresh = time.time()
    save_config(config)

    Prompt.ask("Press Enter to return to the main menu")


# ----------------------------------------------------------------
# Main Interactive Menu Loop
# ----------------------------------------------------------------
def main_menu() -> None:
    """Display the main menu and process user input."""
    devices = DEVICES

    # Initial scan
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("Initializing..."),
        console=console,
    ) as progress:
        progress.add_task("Loading", total=None)
        check_device_statuses(devices)

    while True:
        clear_screen()
        console.print(create_header())

        # Separate devices by type
        tailscale_devices = [d for d in devices if d.device_type == "tailscale"]
        local_devices = [d for d in devices if d.device_type == "local"]

        # Display device tables
        console.print(create_device_table(tailscale_devices, "", "Tailscale Devices"))
        console.print()
        console.print(create_device_table(local_devices, "L", "Local Devices"))

        console.print()

        choice = Prompt.ask("Enter your choice").strip().lower()

        if choice in ("q", "quit", "exit"):
            clear_screen()
            console.print(
                Panel(
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
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
                        f"This device appears offline. Connect anyway?",
                        default=False,
                    ):
                        continue
                    username = get_username(device.username or DEFAULT_USERNAME)
                    connect_to_device(device, username)
                else:
                    print_error(f"Invalid device number: {choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
                Prompt.ask("Press Enter to continue")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tailscale_devices):
                    device = tailscale_devices[idx]
                    if device.status is False and not Confirm.ask(
                        f"This device appears offline. Connect anyway?",
                        default=False,
                    ):
                        continue
                    username = get_username(device.username or DEFAULT_USERNAME)
                    connect_to_device(device, username)
                else:
                    print_error(f"Invalid device number: {choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
                Prompt.ask("Press Enter to continue")


def main() -> None:
    """Main entry point for the SSH Connection Manager."""
    try:
        ensure_config_directory()
        main_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {str(e)}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
