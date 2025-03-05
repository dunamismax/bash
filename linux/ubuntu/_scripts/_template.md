# Advanced Terminal Application Script Generation Guidelines

This document provides comprehensive guidelines for generating sophisticated Python terminal applications with professional interfaces. These guidelines ensure all scripts maintain consistent structure, excellent user experience, and robust operational patterns aligned with the latest best practices.

## Core Interaction Principles

- **Professional Design Philosophy:** Create applications with an intuitive, visually appealing interface that guides users through complex operations with clarity.
- **User-Centric Experience:** Focus on responsive design, clear feedback, and graceful handling of user input and errors.
- **Operational Robustness:** Ensure applications can handle unexpected scenarios through comprehensive error handling and recovery mechanisms.
- **Visual Consistency:** Maintain consistent visual language with the Nord color theme and structured UI components.

## Technical Architecture Guidelines

When creating Python terminal applications, adhere to these structural patterns:

### 1. Modular Organization

- **Clearly Commented Sections:** Use standardized section delimiters (e.g., `# ----------------------------------------------------------------`) for improved readability.
- **Logical Function Grouping:** Organize related functions into cohesive groups (UI helpers, file operations, connection management).
- **Separation of Concerns:** Keep data structures, UI components, and business logic in distinct sections.
- **Progressive Flow:** Structure applications with clear initialization, interactive menu systems, and graceful termination.

### 2. Professional UI Implementation

- **Nord Color Theme:** Implement the complete Nord palette for consistent, visually appealing interfaces.
- **Dynamic ASCII Headers:** Use Pyfiglet with gradient styling that adapts to terminal width.
- **Rich Library Integration:** Utilize Panels, Tables, Progress bars, and styled text for sophisticated presentation.
- **Responsive Design:** Dynamically adjust display elements based on terminal dimensions using `shutil.get_terminal_size()`.
- **prompt_toolkit Integration:** Implement tab completion, command history, and styled prompts for enhanced user input.

### 3. Robust Error Handling

- **Comprehensive Try/Except Blocks:** Surround all external operations with appropriate error handling.
- **Color-Coded Messaging:** Use consistent color schemes for success, warning, and error messages.
- **User-Friendly Feedback:** Present errors with clear descriptions and potential solutions.
- **Graceful Recovery:** Provide fallback mechanisms and allow users to retry operations when possible.
- **Session Cleanup:** Ensure all resources are properly released even during abnormal termination.

### 4. Interactive Components

- **Rich Progress Tracking:** Implement visual progress indicators with real-time statistics during lengthy operations.
- **Confirmation Dialogs:** Use Rich's Confirm class for potentially destructive operations.
- **Numbered Menu Systems:** Create intuitive numbered menus with clear options and visual highlighting.
- **Enhanced Input Methods:** Integrate prompt_toolkit for path completion, command history, and styled input.
- **Contextual Help:** Provide clear instructions and help information throughout the application.

### 5. Data Structures & Management

- **Type Annotations:** Use Python type hints consistently for all function signatures and variables.
- **Dataclasses:** Employ dataclasses for structured data representation with appropriate defaults.
- **Constants Section:** Group configuration constants in a dedicated section at the beginning.
- **Global State Management:** Handle global state carefully with clear documentation.

### 6. Operational Robustness

- **Dependency Management:** Include automatic dependency detection and installation mechanisms.
- **Signal Handling:** Register appropriate signal handlers for graceful termination (SIGINT, SIGTERM).
- **Environment Awareness:** Detect and adapt to different user environments (admin/sudo contexts).

## Implementation Guidelines

When generating a terminal application for users:

1. Understand the core requirements completely before starting implementation.
2. Structure your code following the section order in the template:
   - Dependencies and imports
   - Configuration and constants
   - Data structures
   - UI helper functions
   - Core functionality
   - Main menu and control flow
   - Entry point
3. Maintain a consistent visual style throughout the application using the Nord theme.
4. Implement robust error handling for all operations that might fail.
5. Ensure comprehensive help and guidance is available within the application.
6. Create a responsive design that adapts to the user's terminal environment.
7. Include detailed docstrings for all functions, classes, and modules.

Remember to tailor the complexity to match user requirements while maintaining the professional structure and robust architecture demonstrated in the template. All scripts should be written to work on Ubuntu.

## Template / Example Script (Advanced Terminal Application standards)

```python
#!/usr/bin/env python3
"""
SSH Connection Manager (Advanced Terminal Application)
---------------------------------------------------------

A professional-grade terminal application for managing SSH connections with a
Nord-themed interface. This version provides an interactive, menu-driven interface,
real-time progress tracking, and robust error handling—all without auto-completion or
machine-editing features. The device lists are statically configured.

Features:
  • Dynamic ASCII banners with gradient styling via Pyfiglet
  • Interactive numbered menus using Rich prompts
  • Real-time progress tracking and spinners with Rich
  • Comprehensive error handling with color-coded messages and recovery suggestions
  • Graceful signal handling for SIGINT and SIGTERM
  • Type annotations and dataclasses for improved readability
  • System-wide dependency management via Nala (for python3-rich and python3-pyfiglet)

Usage:
  Run the script and use the numbered menu options to select a device:
    - Numbers 1-N: Connect to a Tailscale device
    - L1-LN:      Connect to a local device
    - r:          Refresh device status
    - c:          Configure SSH options
    - s:          Search for devices
    - h:          Show help information
    - q:          Quit the application

Version: 8.0.0
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
from datetime import datetime
from dataclasses import dataclass, field
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

# Enable rich traceback for debugging
install_rich_traceback(show_locals=True)

# Initialize global Rich Console
console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "SSH Connection Manager"
APP_SUBTITLE: str = "Professional Network Access Solution"
VERSION: str = "8.0.0"
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 1.5  # seconds
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30  # seconds
DEFAULT_SSH_PORT: int = 22
MAX_PARALLEL_PINGS: int = min(20, os.cpu_count() or 4)
TRANSITION_DELAY: float = 0.3  # seconds

# Configuration file for SSH options (stored in user config directory)
CONFIG_DIR: str = os.path.expanduser("~/.config/ssh_manager")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")


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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Device:
    """
    Represents an SSH-accessible device with connection details.

    Attributes:
        name: The device's display name.
        ip_address: IP address used for SSH connection.
        device_type: "tailscale" or "local".
        description: A short description (e.g. OS, version).
        port: SSH port number.
        username: Optional default username for the device.
        status: True if online, False if offline, None if unknown.
        last_ping_time: Timestamp of the last ping check.
        response_time: Ping response time in milliseconds.
    """

    name: str
    ip_address: str
    device_type: str = "local"  # "tailscale" or "local"
    description: Optional[str] = None
    port: int = DEFAULT_SSH_PORT
    username: Optional[str] = None
    status: Optional[bool] = None
    last_ping_time: float = field(default_factory=time.time)
    response_time: Optional[float] = None

    def get_connection_string(self, username: Optional[str] = None) -> str:
        user = username or self.username or DEFAULT_USERNAME
        if self.port == DEFAULT_SSH_PORT:
            return f"{user}@{self.ip_address}"
        return f"{user}@{self.ip_address} -p {self.port}"

    def get_status_indicator(self) -> Text:
        if self.status is True:
            text = "● ONLINE"
            if self.response_time is not None:
                text += f" ({self.response_time:.0f}ms)"
            return Text(text, style=f"bold {NordColors.GREEN}")
        elif self.status is False:
            return Text("● OFFLINE", style=f"bold {NordColors.RED}")
        else:
            return Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")


@dataclass
class AppConfig:
    """
    Application configuration for SSH options.

    Attributes:
        default_username: Default SSH username.
        ssh_options: Dictionary of SSH options with (value, description).
        last_refresh: Timestamp of the last device status refresh.
        device_check_interval: Seconds between automatic status checks.
        terminal_width: Last known terminal width.
        terminal_height: Last known terminal height.
    """

    default_username: str = DEFAULT_USERNAME
    ssh_options: Dict[str, Tuple[str, str]] = field(
        default_factory=lambda: {
            "ServerAliveInterval": ("30", "Interval (sec) to send keepalive packets"),
            "ServerAliveCountMax": ("3", "Packets to send before disconnecting"),
            "ConnectTimeout": ("10", "Timeout (sec) for establishing connection"),
            "StrictHostKeyChecking": ("accept-new", "Host key verification behavior"),
            "Compression": ("yes", "Enable compression"),
            "LogLevel": ("ERROR", "SSH logging verbosity"),
        }
    )
    last_refresh: float = field(default_factory=time.time)
    device_check_interval: int = 300  # seconds
    terminal_width: int = 80
    terminal_height: int = 24


# ----------------------------------------------------------------
# Static Device Lists
# ----------------------------------------------------------------
# Tailscale Devices
STATIC_TAILSCALE_DEVICES: List[Device] = [
    Device(
        name="raspberrypi-3",
        ip_address="100.116.191.42",
        device_type="tailscale",
        description="dunamismax@github | v1.80.2 | Linux 6.11.0-1008-raspi | Mar 3, 1:44 PM EST",
        username="dunamismax@github",
    ),
    Device(
        name="raspberrypi-5",
        ip_address="100.105.117.18",
        device_type="tailscale",
        description="dunamismax@github | v1.80.2 | Linux 6.11.0-1008-raspi | Mar 3, 1:44 PM EST",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-lenovo",
        ip_address="100.88.172.104",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-19-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server",
        ip_address="100.109.43.88",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-18-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server-vm-01",
        ip_address="100.84.119.114",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-18-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server-vm-02",
        ip_address="100.122.237.56",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-18-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server-vm-03",
        ip_address="100.97.229.120",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-18-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server-vm-04",
        ip_address="100.73.171.7",
        device_type="tailscale",
        description="dunamismax@github | v1.80.3 | Linux 6.11.0-18-generic | Connected",
        username="dunamismax@github",
    ),
    Device(
        name="ubuntu-server-windows-11-ent-ltsc-vm",
        ip_address="100.66.128.35",
        device_type="tailscale",
        description="dunamismax@github | v1.80.2 | Windows 11 24H2 | Connected",
        username="dunamismax@github",
    ),
]

# Local Devices
STATIC_LOCAL_DEVICES: List[Device] = [
    Device(
        name="ubuntu-server",
        ip_address="192.168.0.73",
        device_type="local",
        description="MAC: 6C-1F-F7-04-59-50 | Reserved IP: 192.168.0.73",
    ),
    Device(
        name="raspberrypi-5",
        ip_address="192.168.0.40",
        device_type="local",
        description="MAC: 2C-CF-67-59-0E-03 | Reserved IP: 192.168.0.40",
    ),
    Device(
        name="ubuntu-lenovo",
        ip_address="192.168.0.45",
        device_type="local",
        description="MAC: 6C-1F-F7-1A-0B-28 | Reserved IP: 192.168.0.45",
    ),
    Device(
        name="raspberrypi-3",
        ip_address="192.168.0.100",
        device_type="local",
        description="MAC: B8-27-EB-3A-11-89 | Reserved IP: 192.168.0.100",
    ),
]

# Combined static device list
DEVICES: List[Device] = STATIC_TAILSCALE_DEVICES + STATIC_LOCAL_DEVICES


# ----------------------------------------------------------------
# File System Operations (for SSH configuration)
# ----------------------------------------------------------------
def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    ensure_config_directory()
    try:
        import json

        with open(CONFIG_FILE, "w") as f:
            json.dump(config.__dict__, f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    try:
        import json

        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            config = AppConfig(**data)
            # Rebuild ssh_options with descriptions if necessary
            return config
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    """
    Create a dynamic ASCII art header with a gradient using Pyfiglet.
    The header adapts to terminal width.
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
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * min(term_width - 4, 80)}[/]"
    styled_text = border + "\n" + styled_text + border
    return Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


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


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=style,
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
        box=box.ROUNDED,
    )
    console.print(panel)


def show_help() -> None:
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-N[/]:       Connect to a Tailscale device by number
[bold {NordColors.FROST_2}]L1-LN[/]:     Connect to a Local device by number
[bold {NordColors.FROST_2}]r[/]:         Refresh device status
[bold {NordColors.FROST_2}]c[/]:         Configure SSH options
[bold {NordColors.FROST_2}]s[/]:         Search for devices
[bold {NordColors.FROST_2}]h[/]:         Show help information
[bold {NordColors.FROST_2}]q[/]:         Quit the application
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=NordColors.FROST_3,
            padding=(1, 2),
            box=box.ROUNDED,
        )
    )


def display_system_info() -> None:
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
    print_message("Cleaning up session resources...", NordColors.FROST_3)
    # Additional cleanup tasks can be added here.


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
# Device Status Functions
# ----------------------------------------------------------------
def ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
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
        response_time = (end_time - start_time) * 1000  # ms
        return (
            result.returncode == 0
        ), response_time if result.returncode == 0 else None
    except Exception:
        return False, None


def check_device_statuses(
    devices: List[Device], progress_callback: Optional[Callable[[int], None]] = None
) -> None:
    def check_single(device: Device, index: int) -> None:
        success, response_time = ping_device(device.ip_address)
        device.status = success
        device.response_time = response_time
        device.last_ping_time = time.time()
        if progress_callback:
            progress_callback(index)

    # Use a simple sequential loop (could be parallelized if needed)
    for i, device in enumerate(devices):
        check_single(device, i)


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
    term_width, _ = shutil.get_terminal_size((80, 24))
    compact_mode = term_width < 100
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
        box=box.ROUNDED,
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center")
    if not compact_mode:
        table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}")
    online_count = sum(1 for d in devices if d.status is True)
    for idx, device in enumerate(devices, 1):
        if compact_mode:
            table.add_row(
                f"{prefix}{idx}",
                device.name,
                device.ip_address,
                device.get_status_indicator(),
            )
        else:
            table.add_row(
                f"{prefix}{idx}",
                device.name,
                device.ip_address,
                device.get_status_indicator(),
                device.description or "",
            )
    if devices:
        footer = Text.from_markup(
            f"[{NordColors.FROST_3}]{online_count}/{len(devices)} devices online[/]"
        )
        table.caption = footer
    return table


def create_commands_panel() -> Panel:
    command_text = (
        f"[{NordColors.FROST_3}]Commands: [bold]1-N[/] Tailscale | [bold]L1-LN[/] Local | "
        f"[bold]r[/] Refresh | [bold]c[/] Config | [bold]s[/] Search | [bold]h[/] Help | [bold]q[/] Quit"
    )
    return Panel(
        Align.center(Text.from_markup(command_text)),
        border_style=NordColors.FROST_4,
        padding=(1, 2),
        box=box.ROUNDED,
    )


# ----------------------------------------------------------------
# SSH Connection Functions
# ----------------------------------------------------------------
def get_username(default_username: str) -> str:
    return Prompt.ask(
        f"Username for SSH connection [{default_username}]: ", default=default_username
    )


def connect_to_device(device: Device, username: Optional[str] = None) -> None:
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
            TextColumn("[bold {task.fields[message_color]}]{task.fields[message]}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Connecting...",
                total=4,
                visible=True,
                task_fields={
                    "message": "Initializing secure channel...",
                    "message_color": NordColors.FROST_2,
                },
            )
            time.sleep(0.4)
            progress.update(task, message="Negotiating encryption parameters...")
            time.sleep(0.4)
            progress.update(
                task, message=f"Establishing SSH tunnel to {device.ip_address}..."
            )
            time.sleep(0.4)
            progress.update(
                task,
                message="Connection established. Launching secure shell...",
                task_fields={"message_color": NordColors.GREEN},
            )
            time.sleep(0.4)
        ssh_args = [SSH_COMMAND]
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
        print_step("Check that the device is online and SSH is properly configured")
        print_step("Verify that SSH is installed and running on the target device")
        print_step("Ensure the correct username and IP address were used")
        print_step("Try connecting manually with 'ssh -v' for verbose output")
        Prompt.ask("Press Enter to return to the main menu")


# ----------------------------------------------------------------
# Device Status Refresh and SSH Option Configuration
# ----------------------------------------------------------------
def refresh_device_statuses(devices: List[Device]) -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "Checking connectivity status of all devices",
        style=NordColors.FROST_3,
        title="Network Scan",
    )
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold {task.fields[message]}]{task.fields[message]}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task(
            "Refreshing",
            total=len(devices),
            visible=True,
            task_fields={"message": "Checking device status"},
        )

        def update_progress(index: int) -> None:
            progress.advance(scan_task)

        check_device_statuses(devices, update_progress)
    Prompt.ask("Press Enter to return to the main menu")


def configure_ssh_options() -> None:
    clear_screen()
    console.print(create_header())
    print_section("SSH Configuration Options")
    config = load_config()
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Current SSH Options[/]",
        border_style=NordColors.FROST_3,
        box=box.ROUNDED,
    )
    table.add_column("Option", style=f"bold {NordColors.FROST_3}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}")
    for option, (value, description) in config.ssh_options.items():
        table.add_row(option, value, description)
    console.print(table)
    print_message(
        "These options will be applied to all SSH connections", NordColors.FROST_2
    )
    choices = [
        "1. Modify an option",
        "2. Add a new option",
        "3. Reset to defaults",
        "4. Change default username",
        "5. Return to main menu",
    ]
    for choice in choices:
        console.print(f"[{NordColors.FROST_2}]{choice}[/]")
    selected = Prompt.ask(
        "Select an option", choices=["1", "2", "3", "4", "5"], default="5"
    )
    if selected == "1":
        option_keys = list(config.ssh_options.keys())
        if not option_keys:
            print_error("No options to modify")
        else:
            console.print("Available Options:")
            for i, key in enumerate(option_keys, 1):
                console.print(f"[bold]{i}[/]: {key}")
            option_num = Prompt.ask("Enter option number to modify", default="1")
            try:
                idx = int(option_num) - 1
                if 0 <= idx < len(option_keys):
                    key = option_keys[idx]
                    current_value, description = config.ssh_options[key]
                    new_value = Prompt.ask(
                        f"New value for {key}", default=current_value
                    )
                    config.ssh_options[key] = (new_value, description)
                    save_config(config)
                    print_success(f"Updated {key} to: {new_value}")
                else:
                    print_error("Invalid option number")
            except ValueError:
                print_error("Invalid input")
    elif selected == "2":
        new_key = Prompt.ask("Option name")
        new_value = Prompt.ask("Option value")
        description = Prompt.ask("Option description", default="Custom SSH option")
        config.ssh_options[new_key] = (new_value, description)
        save_config(config)
        print_success(f"Added new option: {new_key}={new_value}")
    elif selected == "3":
        if Confirm.ask("Reset all SSH options to defaults?", default=False):
            config.ssh_options = {
                "ServerAliveInterval": (
                    "30",
                    "Interval (sec) to send keepalive packets",
                ),
                "ServerAliveCountMax": ("3", "Packets to send before disconnecting"),
                "ConnectTimeout": ("10", "Timeout (sec) for establishing connection"),
                "StrictHostKeyChecking": (
                    "accept-new",
                    "Host key verification behavior",
                ),
                "Compression": ("yes", "Enable compression"),
                "LogLevel": ("ERROR", "SSH logging verbosity"),
            }
            save_config(config)
            print_success("SSH options reset to defaults")
    elif selected == "4":
        current = config.default_username
        new_username = Prompt.ask("New default username", default=current)
        config.default_username = new_username
        save_config(config)
        print_success(f"Default username changed to: {new_username}")
    Prompt.ask("Press Enter to return to the main menu")


def search_for_devices(devices: List[Device]) -> None:
    clear_screen()
    console.print(create_header())
    search_term = Prompt.ask("Enter search term (name, IP, or description)")
    if not search_term:
        return
    term = search_term.lower()
    matching = [
        d
        for d in devices
        if term in d.name.lower()
        or term in d.ip_address.lower()
        or (d.description and term in d.description.lower())
    ]
    print_section(f"Search Results for '{search_term}'")
    if not matching:
        display_panel(
            f"No devices found matching '{search_term}'",
            style=NordColors.YELLOW,
            title="No Results",
        )
    else:
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            expand=True,
            title=f"[bold {NordColors.FROST_2}]Matching Devices ({len(matching)})[/]",
            border_style=NordColors.FROST_3,
            box=box.ROUNDED,
        )
        table.add_column("Type", style=f"bold {NordColors.FROST_4}")
        table.add_column("Name", style=f"bold {NordColors.FROST_1}")
        table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
        table.add_column("Status", justify="center")
        table.add_column("Description", style=f"dim {NordColors.SNOW_STORM_1}")
        for d in matching:
            dev_type = "Tailscale" if d.device_type == "tailscale" else "Local"
            table.add_row(
                dev_type,
                d.name,
                d.ip_address,
                d.get_status_indicator(),
                d.description or "",
            )
        console.print(table)
        choice = Prompt.ask(
            "Connect to a device? Enter its number or 'n' to cancel", default="n"
        )
        if choice.lower() != "n":
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(matching):
                    selected_device = matching[idx]
                    uname = get_username(selected_device.username or DEFAULT_USERNAME)
                    connect_to_device(selected_device, uname)
                    return
                else:
                    print_error(f"Invalid device number: {choice}")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
    Prompt.ask("Press Enter to return to the main menu")


# ----------------------------------------------------------------
# Main Interactive Menu Loop
# ----------------------------------------------------------------
def main() -> None:
    ensure_config_directory()
    config = load_config()
    # Use static device list (DEVICES)
    devices = DEVICES

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
        TextColumn("[bold {task.fields[message]}]{task.fields[message]}"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task(
            "Scanning",
            total=len(devices),
            visible=True,
            task_fields={"message": "Pinging devices"},
        )

        def update_progress(index: int) -> None:
            progress.advance(scan_task)

        check_device_statuses(devices, update_progress)
    time.sleep(0.5)

    while True:
        term_width, _ = shutil.get_terminal_size()
        config.terminal_width = term_width
        clear_screen()
        console.print(create_header())
        display_system_info()
        # Split devices by type
        tailscale_devices = [d for d in devices if d.device_type == "tailscale"]
        local_devices = [d for d in devices if d.device_type == "local"]
        tailscale_table = create_device_table(
            tailscale_devices, "", "Tailscale Devices"
        )
        local_table = create_device_table(local_devices, "L", "Local Devices")
        if term_width >= 160:
            from rich.columns import Columns

            console.print(
                Columns(
                    [
                        Panel(
                            tailscale_table,
                            border_style=NordColors.FROST_4,
                            padding=(0, 1),
                            box=box.ROUNDED,
                        ),
                        Panel(
                            local_table,
                            border_style=NordColors.FROST_4,
                            padding=(0, 1),
                            box=box.ROUNDED,
                        ),
                    ]
                )
            )
        else:
            console.print(
                Panel(
                    tailscale_table,
                    border_style=NordColors.FROST_4,
                    padding=(0, 1),
                    box=box.ROUNDED,
                )
            )
            console.print(
                Panel(
                    local_table,
                    border_style=NordColors.FROST_4,
                    padding=(0, 1),
                    box=box.ROUNDED,
                )
            )
        console.print()
        console.print(create_commands_panel())
        console.print()
        choice = Prompt.ask("Enter your choice").strip().lower()
        if choice in ("q", "quit", "exit"):
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        f"Thank you for using {APP_NAME}!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=NordColors.FROST_1,
                    padding=(1, 2),
                    box=box.ROUNDED,
                )
            )
            break
        elif choice in ("r", "refresh"):
            refresh_device_statuses(devices)
        elif choice in ("h", "help"):
            show_help()
            Prompt.ask("Press Enter to continue")
        elif choice in ("c", "config", "configure"):
            configure_ssh_options()
        elif choice in ("s", "search"):
            search_for_devices(devices)
        elif choice.startswith("l"):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(local_devices):
                    device = local_devices[idx]
                    if device.status is False and not Confirm.ask(
                        "This device appears offline. Connect anyway?", default=False
                    ):
                        continue
                    uname = get_username(device.username or config.default_username)
                    connect_to_device(device, uname)
                else:
                    display_panel(
                        f"Invalid local device number: {choice}",
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
                        "This device appears offline. Connect anyway?", default=False
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
```

## Final Guidelines for User Interaction

When creating terminal applications for users:

Understanding Requirements: Begin by thoroughly understanding the user's specific needs, technical level, and use case. Ask clarifying questions about functionality, platform requirements, and preferred interaction patterns before generating code.
Architecture-First Approach: Establish a clear application architecture following the template patterns, adapting complexity to match the user's requirements while maintaining robustness.
Progressive Enhancement: Start with core functionality, then layer in advanced features like tab completion, progress tracking, and styled UI elements. This allows for testing fundamental operations before enhancing the user experience.
User Experience Focus: Prioritize user interaction patterns with:

Intuitive menu navigation
Clear visual feedback for operations
Comprehensive error messages with recovery suggestions
Interactive confirmations for destructive operations
Responsive design that adapts to terminal dimensions

Documentation & Guidance: Ensure code includes thorough documentation with:

Descriptive docstrings for all components
Clear section delimiters and explanatory comments
Contextual help embedded within the application
Appropriate input validation with user guidance

By following these guidelines, you'll create terminal applications that combine professional architecture with exceptional user experience, adapted specifically to each user's requirements.
