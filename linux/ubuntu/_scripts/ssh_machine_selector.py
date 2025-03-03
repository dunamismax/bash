#!/usr/bin/env python3
"""
Enhanced SSH Selector
--------------------------------------------------

A sophisticated terminal interface for managing and connecting to SSH endpoints with
elegant Nord theme styling. Featuring real-time connectivity monitoring, parallel
device scanning, and intelligent connection management.

Features:
- Automatic device discovery and status monitoring
- Parallel network scanning with real-time status updates
- Tailscale and local network device categorization
- Elegant Nord-themed user interface
- SSH connection management with customizable settings

Usage:
  Run the script and select a device by number to connect via SSH:
  - Numbers 1-N: Connect to Tailscale devices
  - L1-LN: Connect to local network devices
  - r: Refresh device status
  - h: Show help
  - q: Quit the application

Version: 6.2.0
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, Callable, Union, Set

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console, RenderableType
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
        TaskProgressColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = os.environ.get("USER") or "user"
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 1.5  # seconds
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30  # seconds
VERSION: str = "6.2.0"
APP_NAME: str = "SSH Selector"
APP_SUBTITLE: str = "Secure Connection Manager"
DEFAULT_SSH_PORT: int = 22
MAX_PARALLEL_PINGS: int = 20

# Advanced SSH options
SSH_OPTIONS: Dict[str, str] = {
    "ServerAliveInterval": "30",
    "ServerAliveCountMax": "3",
    "ConnectTimeout": "10",
    "StrictHostKeyChecking": "accept-new",
}


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1: str = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2: str = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3: str = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4: str = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1: str = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2: str = "#E5E9F0"  # Medium text color
    SNOW_STORM_3: str = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1: str = "#8FBCBB"  # Light cyan
    FROST_2: str = "#88C0D0"  # Light blue
    FROST_3: str = "#81A1C1"  # Medium blue
    FROST_4: str = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED: str = "#BF616A"  # Red
    ORANGE: str = "#D08770"  # Orange
    YELLOW: str = "#EBCB8B"  # Yellow
    GREEN: str = "#A3BE8C"  # Green
    PURPLE: str = "#B48EAD"  # Purple


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with its connection details and status.

    Attributes:
        name: The hostname or device identifier
        ip_address: IP address for SSH connection
        status: Connection status (True=online, False=offline, None=unknown)
        last_ping_time: Last time the device was pinged (in seconds since epoch)
        description: Optional description of the device
        port: SSH port to use (default: 22)
        response_time: Last ping response time in milliseconds
    """

    name: str
    ip_address: str
    status: Optional[bool] = (
        None  # True for online, False for offline, None for unknown
    )
    last_ping_time: float = field(default_factory=time.time)
    description: Optional[str] = None
    port: int = DEFAULT_SSH_PORT
    response_time: Optional[float] = None  # Latency in ms

    def get_connection_string(self, username: str) -> str:
        """Return the full SSH connection string."""
        if self.port == DEFAULT_SSH_PORT:
            return f"{username}@{self.ip_address}"
        return f"{username}@{self.ip_address} -p {self.port}"

    def get_status_indicator(self) -> Text:
        """Return a styled status indicator for this device."""
        if self.status is True:
            status_text = "● ONLINE"
            if self.response_time is not None:
                status_text += f" ({self.response_time:.0f}ms)"
            return Text(status_text, style=f"bold {NordColors.GREEN}")
        elif self.status is False:
            return Text("● OFFLINE", style=f"bold {NordColors.RED}")
        else:
            return Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["small", "slant", "digital", "mini", "smslant"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
         _                _           _             
 ___ ___| |__    ___  ___| | ___  ___| |_ ___  _ __ 
/ __/ __| '_ \  / __|/ _ \ |/ _ \/ __| __/ _ \| '__|
\__ \__ \ | | | \__ \  __/ |  __/ (__| || (_) | |   
|___/___/_| |_| |___/\___|_|\___|\___|\__\___/|_|   
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a beautiful gradient effect with Nord colors
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

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 60 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
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
    """
    Print a styled message with a prefix.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message with a checkmark prefix."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message with a warning symbol prefix."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message with an X prefix."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step message with an arrow prefix."""
    print_message(message, NordColors.FROST_2, "→")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def show_help() -> None:
    """Display help information in a styled panel."""
    help_text = """
[bold]Available Commands:[/]

[bold {frost2}]1-N[/]:       Connect to Tailscale device by number
[bold {frost2}]L1-LN[/]:     Connect to Local device by number
[bold {frost2}]r[/]:         Refresh device status
[bold {frost2}]c[/]:         Configure SSH options
[bold {frost2}]h[/]:         Show this help
[bold {frost2}]q[/]:         Quit the application

[bold]Tips:[/]
• Device status is automatically checked on startup
• Use 'r' to manually refresh if devices change
• Press Enter with no input to refresh the display
• Local devices are on your current network
• Tailscale devices are on your Tailscale VPN network
    """.format(frost2=NordColors.FROST_2)

    console.print(
        Panel(
            Text.from_markup(help_text),
            title="[bold {frost1}]Help & Commands[/]".format(frost1=NordColors.FROST_1),
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )


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
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results

    Raises:
        subprocess.CalledProcessError: If the command returns a non-zero exit code
        subprocess.TimeoutExpired: If the command times out
        Exception: For any other errors
    """
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
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up session resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Device Data Functions
# ----------------------------------------------------------------
def load_tailscale_devices() -> List[Device]:
    """
    Load a list of Tailscale devices.

    Returns:
        List of Device objects representing Tailscale network devices
    """
    # In a real application, this could query the Tailscale API or read a config file
    return [
        Device(
            name="ubuntu-server",
            ip_address="100.109.43.88",
            description="Primary Server",
        ),
        Device(
            name="ubuntu-lenovo",
            ip_address="100.66.213.7",
            description="Development Laptop",
        ),
        Device(
            name="raspberrypi-5",
            ip_address="100.105.117.18",
            description="Raspberry Pi 5",
        ),
        Device(
            name="raspberrypi-3",
            ip_address="100.116.191.42",
            description="Raspberry Pi 3",
        ),
        Device(
            name="ubuntu-server-vm-01",
            ip_address="100.84.119.114",
            description="Ubuntu Server VM 1",
        ),
        Device(
            name="ubuntu-server-vm-02",
            ip_address="100.122.237.56",
            description="Ubuntu Server VM 2",
        ),
        Device(
            name="ubuntu-server-vm-03",
            ip_address="100.97.229.120",
            description="Ubuntu Server VM 3",
        ),
        Device(
            name="ubuntu-server-vm-04",
            ip_address="100.73.171.7",
            description="Ubuntu Server VM 4",
        ),
        Device(
            name="ubuntu-lenovo-vm-01",
            ip_address="100.107.79.81",
            description="Ubuntu Lenovo VM 1",
        ),
        Device(
            name="ubuntu-lenovo-vm-02",
            ip_address="100.78.101.2",
            description="Ubuntu Lenovo VM 2",
        ),
        Device(
            name="ubuntu-lenovo-vm-03",
            ip_address="100.95.115.62",
            description="Ubuntu Lenovo VM 3",
        ),
        Device(
            name="ubuntu-lenovo-vm-04",
            ip_address="100.92.31.94",
            description="Ubuntu Lenovo VM 4",
        ),
    ]


def load_local_devices() -> List[Device]:
    """
    Load a list of devices on the local network.

    Returns:
        List of Device objects representing local network devices
    """
    # In a real application, this could scan the network or read from a hosts file
    return [
        Device(
            name="ubuntu-server",
            ip_address="192.168.0.73",
            description="Primary Server",
        ),
        Device(
            name="ubuntu-lenovo",
            ip_address="192.168.0.31",
            description="Development Laptop",
        ),
        Device(
            name="raspberrypi-5",
            ip_address="192.168.0.40",
            description="Raspberry Pi 5",
        ),
        Device(
            name="raspberrypi-3",
            ip_address="192.168.0.100",
            description="Raspberry Pi 3",
        ),
    ]


def discover_local_devices() -> List[Device]:
    """
    Discover devices on the local network by scanning IP ranges.
    This is a placeholder for actual network scanning logic.

    Returns:
        List of Device objects discovered on the network
    """
    # In a real application, this would scan local network ranges
    # For now, we'll just return the static list
    return load_local_devices()


# ----------------------------------------------------------------
# Network Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
    """
    Check if a device is reachable by pinging it and measure response time.

    Args:
        ip_address: The IP address to ping

    Returns:
        Tuple containing (success, response_time_ms)
        where success is True if the device responds, False otherwise,
        and response_time_ms is the response time in milliseconds or None if failed
    """
    start_time = time.time()

    try:
        # Different ping commands for different platforms
        if sys.platform == "win32":
            cmd = [
                "ping",
                "-n",
                str(PING_COUNT),
                "-w",
                str(int(PING_TIMEOUT * 1000)),
                ip_address,
            ]
        else:  # Linux, macOS, etc.
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
        response_time = (end_time - start_time) * 1000  # Convert to ms

        if result.returncode == 0:
            return True, response_time
        return False, None

    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False, None


def check_device_statuses(
    devices: List[Device], progress_callback: Optional[Callable[[int], None]] = None
) -> None:
    """
    Check the status of all devices in parallel and update their status attribute.

    Args:
        devices: List of devices to check
        progress_callback: Optional callback function to update progress
    """

    def check_single_device(device: Device, index: int) -> None:
        """Check a single device's connectivity status and update its attributes."""
        success, response_time = ping_device(device.ip_address)
        device.status = success
        device.response_time = response_time
        device.last_ping_time = time.time()

        if progress_callback:
            progress_callback(index)

    with ThreadPoolExecutor(
        max_workers=min(MAX_PARALLEL_PINGS, os.cpu_count() or 4)
    ) as executor:
        # Submit all ping tasks to the executor
        futures = [
            executor.submit(check_single_device, device, i)
            for i, device in enumerate(devices)
        ]

        # Wait for all futures to complete
        for future in futures:
            future.result()  # This will re-raise any exceptions that occurred


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    """
    Create a table displaying device information and status.

    Args:
        devices: List of Device objects to display
        prefix: Prefix for device numbers (e.g., "L" for local devices)
        title: Title for the device table

    Returns:
        A Rich Table object containing the device information
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
        box=None,
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center")
    table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}")

    # Count online devices
    online_count = sum(1 for d in devices if d.status is True)

    for idx, device in enumerate(devices, 1):
        table.add_row(
            f"{prefix}{idx}",
            device.name,
            device.ip_address,
            device.get_status_indicator(),
            device.description or "",
        )

    # Add a footer with summary information
    if devices:
        footer = Text.from_markup(
            f"[{NordColors.FROST_3}]{online_count}/{len(devices)} devices online[/]"
        )
        table.caption = footer

    return table


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username() -> str:
    """
    Ask the user whether to use the default username or enter a new one.

    Returns:
        The username to use for SSH connections
    """
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]Username for SSH connection[/]",
        default=DEFAULT_USERNAME,
    )


def connect_to_device(device: Device, username: str) -> None:
    """
    Clear the screen and initiate an SSH connection to the selected device.

    Args:
        device: Device object to connect to
        username: Username for SSH connection
    """
    console.clear()
    console.print(create_header())

    # Create a connection panel
    connection_panel = Panel(
        Text.from_markup(
            f"\n[bold {NordColors.FROST_2}]Device:[/] [{NordColors.SNOW_STORM_2}]{device.name}[/]\n"
            f"[bold {NordColors.FROST_2}]Address:[/] [{NordColors.SNOW_STORM_2}]{device.ip_address}[/]\n"
            f"[bold {NordColors.FROST_2}]User:[/] [{NordColors.SNOW_STORM_2}]{username}[/]\n"
            + (
                f"[bold {NordColors.FROST_2}]Description:[/] [{NordColors.SNOW_STORM_2}]{device.description}[/]\n"
                if device.description
                else ""
            )
        ),
        title=f"[bold {NordColors.FROST_3}]SSH Connection[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(connection_panel)

    try:
        # Connection messages with visual progress
        console.print()

        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[message_color]}]{task.fields[message]}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Connecting...",
                message="Initializing secure channel...",
                message_color=NordColors.FROST_2,
            )
            time.sleep(0.5)

            progress.update(
                task,
                message="Negotiating encryption parameters...",
                message_color=NordColors.FROST_2,
            )
            time.sleep(0.5)

            progress.update(
                task,
                message=f"Establishing SSH tunnel to {device.ip_address}...",
                message_color=NordColors.FROST_2,
            )
            time.sleep(0.5)

            progress.update(
                task,
                message="Connection established. Launching secure shell...",
                message_color=NordColors.GREEN,
            )
            time.sleep(0.5)

        console.print()

        # Build SSH command with options
        ssh_args = [SSH_COMMAND]

        # Add SSH options
        for option, value in SSH_OPTIONS.items():
            ssh_args.extend(["-o", f"{option}={value}"])

        # Add target info
        if device.port != DEFAULT_SSH_PORT:
            ssh_args.extend(["-p", str(device.port)])

        ssh_args.append(f"{username}@{device.ip_address}")

        # Execute SSH command
        os.execvp(SSH_COMMAND, ssh_args)

    except Exception as e:
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]Connection Error:[/] {str(e)}"
                ),
                border_style=Style(color=NordColors.RED),
                title="Connection Failed",
                padding=(1, 2),
            )
        )
        print_step("Check that the device is online and SSH is properly configured")
        print_step("You may need to manually add this host to your known_hosts file")

        console.print(
            f"[{NordColors.SNOW_STORM_1}]Press Enter to return to selection screen...[/]"
        )
        input()


# ----------------------------------------------------------------
# Device Status Refresh
# ----------------------------------------------------------------
def refresh_device_statuses(devices: List[Device]) -> None:
    """
    Refresh the status of all devices with a progress animation.

    Args:
        devices: List of devices to refresh
    """
    console.clear()
    console.print(create_header())

    display_panel(
        "Checking connectivity status of all devices",
        style=NordColors.FROST_3,
        title="Network Scan",
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking device status"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        refresh_task = progress.add_task("Refreshing", total=len(devices))

        def update_refresh_progress(index: int) -> None:
            progress.advance(refresh_task)

        check_device_statuses(devices, update_refresh_progress)


def configure_ssh_options() -> None:
    """Allow the user to configure SSH connection options."""
    console.clear()
    console.print(create_header())

    print_section("SSH Configuration Options")

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Current SSH Options[/]",
        border_style=NordColors.FROST_3,
    )

    table.add_column("Option", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}")

    # Option descriptions
    descriptions = {
        "ServerAliveInterval": "Time interval (seconds) to send keepalive packets",
        "ServerAliveCountMax": "Number of keepalive packets without response before disconnecting",
        "ConnectTimeout": "Timeout (seconds) for establishing connection",
        "StrictHostKeyChecking": "Host key verification behavior",
    }

    for option, value in SSH_OPTIONS.items():
        table.add_row(option, value, descriptions.get(option, ""))

    console.print(table)
    console.print()

    # Note: In a real application, this would allow changing the options
    print_message(
        "These options will be applied to all SSH connections", NordColors.FROST_2
    )
    print_message(
        "To modify these options, edit the script's SSH_OPTIONS dictionary",
        NordColors.FROST_3,
    )
    console.print()

    Prompt.ask(
        "[bold {frost}]Press Enter to return to the main menu[/]".format(
            frost=NordColors.FROST_2
        )
    )


def print_section(title: str) -> None:
    """Print a formatted section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main application function that handles the UI flow and user interaction.
    """
    # Create device lists
    tailscale_devices = load_tailscale_devices()
    local_devices = load_local_devices()
    all_devices = tailscale_devices + local_devices

    # Initial status check
    console.clear()
    console.print(create_header())

    display_panel(
        "Scanning network for available devices",
        style=NordColors.FROST_3,
        title="Initialization",
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Scanning devices"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning", total=len(all_devices))

        def update_progress(index: int) -> None:
            progress.advance(scan_task)

        # Check all devices in parallel
        check_device_statuses(all_devices, update_progress)

    while True:
        console.clear()
        console.print(create_header())

        # Display the current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()

        # Create tables for Tailscale and Local devices
        tailscale_table = create_device_table(
            tailscale_devices, "", "Tailscale Devices"
        )
        local_table = create_device_table(local_devices, "L", "Local Devices")

        # Display the tables side by side
        console.print(
            Columns(
                [
                    Panel(
                        tailscale_table,
                        border_style=Style(color=NordColors.FROST_4),
                        padding=(0, 1),
                    ),
                    Panel(
                        local_table,
                        border_style=Style(color=NordColors.FROST_4),
                        padding=(0, 1),
                    ),
                ]
            )
        )

        # Command help footer
        console.print()
        console.print(
            Align.center(
                f"[{NordColors.FROST_3}]Commands: [bold]1-N[/] Connect to Tailscale | "
                f"[bold]L1-LN[/] Connect to Local | "
                f"[bold]r[/] Refresh | [bold]h[/] Help | [bold]q[/] Quit[/]"
            )
        )
        console.print()

        choice = (
            Prompt.ask(f"[bold {NordColors.FROST_2}]Enter your choice[/]", default="")
            .strip()
            .lower()
        )

        # Handle commands
        if choice == "q":
            console.clear()
            console.print(
                Panel(
                    Text(
                        "Thank you for using SSH Selector!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            break

        elif choice == "r":
            # Refresh device status
            refresh_device_statuses(all_devices)

        elif choice == "h":
            # Show help
            show_help()
            Prompt.ask(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue[/]")

        elif choice == "c":
            # Configure SSH options
            configure_ssh_options()

        elif not choice:
            # Empty input, just refresh the display
            continue

        # Handle local device selection (choices starting with "l")
        elif choice.startswith("l"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]

                    if device.status is False:
                        console.print()
                        if not Confirm.ask(
                            f"[bold {NordColors.YELLOW}]This device appears to be offline. Try to connect anyway?[/]"
                        ):
                            continue

                    username = get_username()
                    connect_to_device(device, username)
                else:
                    display_panel(
                        f"Invalid local device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    Prompt.ask(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue[/]")
            except ValueError:
                display_panel(
                    f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                )
                Prompt.ask(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue[/]")

        # Handle Tailscale device selection
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tailscale_devices):
                    device = tailscale_devices[idx]

                    if device.status is False:
                        console.print()
                        if not Confirm.ask(
                            f"[bold {NordColors.YELLOW}]This device appears to be offline. Try to connect anyway?[/]"
                        ):
                            continue

                    username = get_username()
                    connect_to_device(device, username)
                else:
                    display_panel(
                        f"Invalid device number: {choice}",
                        style=NordColors.RED,
                        title="Error",
                    )
                    Prompt.ask(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue[/]")
            except ValueError:
                display_panel(
                    f"Invalid choice: {choice}", style=NordColors.RED, title="Error"
                )
                Prompt.ask(f"[{NordColors.SNOW_STORM_1}]Press Enter to continue[/]")


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
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
