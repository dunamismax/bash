Please review the following Python script and use it as a reference template for all future scripts you generate for me. The goal is for all future scripts to follow the structure, style, and best practices shown in this example. Let me know once you've reviewed it.

```python
#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import shutil
import socket
import json
import asyncio
import atexit
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast

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
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "ssh connector"
VERSION: str = "1.0.0"
DEFAULT_USERNAME: str = os.environ.get("USER") or "user"
SSH_COMMAND: str = "ssh"
PING_TIMEOUT: float = 0.4  # Reduced timeout for faster checks
PING_COUNT: int = 1
OPERATION_TIMEOUT: int = 30
DEFAULT_SSH_PORT: int = 22

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/ssh_manager")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")


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


@dataclass
class Device:
    name: str
    ip_address: str
    device_type: str = "local"
    description: Optional[str] = None
    port: int = DEFAULT_SSH_PORT
    username: Optional[str] = None
    status: Optional[bool] = None
    last_ping_time: float = field(default_factory=time.time)
    response_time: Optional[float] = None

    def get_connection_string(self, username: Optional[str] = None) -> str:
        user: str = username or self.username or DEFAULT_USERNAME
        if self.port == DEFAULT_SSH_PORT:
            return f"{user}@{self.ip_address}"
        return f"{user}@{self.ip_address} -p {self.port}"

    def get_status_indicator(self) -> Text:
        if self.status is True:
            return Text("● ONLINE", style=f"bold {NordColors.GREEN}")
        else:
            return Text("● OFFLINE", style=f"bold {NordColors.RED}")


T = TypeVar("T")


@dataclass
class AppConfig:
    default_username: str = DEFAULT_USERNAME
    ssh_options: Dict[str, Tuple[str, str]] = field(
        default_factory=lambda: {
            "ServerAliveInterval": ("30", "Interval in sec to send keepalive packets"),
            "ServerAliveCountMax": ("3", "Packets to send before disconnecting"),
            "ConnectTimeout": ("10", "Timeout in sec for connection"),
            "StrictHostKeyChecking": ("accept-new", "Auto-accept new host keys"),
            "Compression": ("yes", "Enable compression"),
            "LogLevel": ("ERROR", "SSH logging level"),
        }
    )
    last_refresh: float = field(default_factory=time.time)
    device_check_interval: int = 300

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Global variables to track async tasks
_background_task = None


# UI Helper Functions
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "mini", "digital"]
    font_to_use: str = fonts[0]
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
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# Core Functionality
def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


def run_command(cmd: List[str]) -> Tuple[int, str]:
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


async def async_ping_device(ip_address: str) -> Tuple[bool, Optional[float]]:
    start_time = time.time()
    try:
        cmd = [
            "ping",
            "-c",
            str(PING_COUNT),
            "-W",
            str(int(PING_TIMEOUT)),
            ip_address,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.wait_for(proc.communicate(), timeout=PING_TIMEOUT + 0.5)
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # in ms
            return proc.returncode == 0, response_time if proc.returncode == 0 else None
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.terminate()
            return False, None

    except Exception:
        return False, None


async def async_check_device_status(device: Device) -> None:
    success, response_time = await async_ping_device(device.ip_address)
    device.status = success
    device.response_time = response_time
    device.last_ping_time = time.time()


async def async_check_device_statuses(devices: List[Device]) -> None:
    tasks = [async_check_device_status(device) for device in devices]
    await asyncio.gather(*tasks)


def check_device_statuses(
    devices: List[Device],
    progress_callback: Optional[Callable[[int, Device], None]] = None,
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        if progress_callback:
            for i, device in enumerate(devices):
                loop.run_until_complete(async_check_device_status(device))
                progress_callback(i, device)
        else:
            loop.run_until_complete(async_check_device_statuses(devices))
    finally:
        loop.close()


def create_device_table(devices: List[Device], prefix: str, title: str) -> Table:
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

    for idx, device in enumerate(devices, 1):
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


def get_username(default_username: str) -> str:
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]Username for SSH connection[/]",
        default=default_username,
    )


def connect_to_device(device: Device, username: Optional[str] = None) -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "SSH Connection",
        f"Connecting to {device.name} ({device.ip_address})",
        NordColors.FROST_2,
    )

    effective_username: str = username or device.username or DEFAULT_USERNAME

    details_table = Table(show_header=False, box=None, padding=(0, 3))
    details_table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    details_table.add_column("Value", style=f"{NordColors.SNOW_STORM_2}")
    details_table.add_row("Address", device.ip_address)
    details_table.add_row("User", effective_username)
    if device.description:
        details_table.add_row("Description", device.description)
    if device.port != DEFAULT_SSH_PORT:
        details_table.add_row("Port", str(device.port))
    details_table.add_row("Status", "Online" if device.status else "Offline")
    if device.response_time:
        details_table.add_row("Latency", f"{device.response_time:.1f} ms")
    console.print(details_table)
    console.print()

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
            task_id = progress.add_task(
                f"[{NordColors.FROST_2}]Establishing connection...", total=100
            )
            for step, pct in [
                (f"[{NordColors.FROST_2}]Resolving hostname...", 20),
                (f"[{NordColors.FROST_2}]Establishing connection...", 40),
                (f"[{NordColors.FROST_2}]Negotiating SSH protocol...", 60),
                (f"[{NordColors.FROST_2}]Authenticating...", 80),
                (f"[{NordColors.GREEN}]Connection established.", 100),
            ]:
                time.sleep(0.3)
                progress.update(task_id, description=step, completed=pct)

        ssh_args: List[str] = [SSH_COMMAND]
        config = load_config()
        for option, (value, _) in config.ssh_options.items():
            ssh_args.extend(["-o", f"{option}={value}"])
        if device.port != DEFAULT_SSH_PORT:
            ssh_args.extend(["-p", str(device.port)])
        ssh_args.append(f"{effective_username}@{device.ip_address}")
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


def refresh_device_statuses(devices: List[Device]) -> None:
    clear_screen()
    console.print(create_header())
    display_panel(
        "Network Scan",
        "Checking connectivity for all configured devices",
        NordColors.FROST_3,
    )
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
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

    online_count = sum(1 for d in devices if d.status is True)
    offline_count = sum(1 for d in devices if d.status is False)
    print_success(f"Scan complete: {online_count} online, {offline_count} offline")
    config = load_config()
    config.last_refresh = time.time()
    save_config(config)
    Prompt.ask("Press Enter to return to the main menu")


def main_menu() -> None:
    devices = DEVICES
    global _background_task

    # Start background device status check without blocking the UI
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("Initializing..."),
        console=console,
    ) as progress:
        progress.add_task("Loading", total=None)

        # Create a new event loop for initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Start the checks but don't wait for them to complete
            _background_task = loop.create_task(async_check_device_statuses(devices))

            # Give the checks a small head start but proceed quickly
            loop.run_until_complete(asyncio.sleep(0.3))

            # Don't close the loop yet - we need to properly clean it up
            # We'll just detach from it and let it continue running
        except Exception as e:
            print_error(f"Error starting device checks: {e}")
            loop.close()

    while True:
        clear_screen()
        console.print(create_header())

        tailscale_devices = [d for d in devices if d.device_type == "tailscale"]
        local_devices = [d for d in devices if d.device_type == "local"]

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
                        f"This device appears offline. Connect anyway?", default=False
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
                        f"This device appears offline. Connect anyway?", default=False
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


def cleanup() -> None:
    try:
        # Cancel any pending asyncio tasks
        for task in asyncio.all_tasks(asyncio.get_event_loop_policy().get_event_loop()):
            if not task.done():
                task.cancel()

        config = load_config()
        config.last_refresh = time.time()
        save_config(config)
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current event loop if one exists
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule the cleanup to run properly in the loop
            loop.call_soon_threadsafe(cleanup)
            # Give a moment for cleanup to run
            time.sleep(0.2)
        else:
            cleanup()
    except Exception:
        # If we can't get the loop or it's closed already, just attempt cleanup directly
        cleanup()

    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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

DEVICES: List[Device] = STATIC_TAILSCALE_DEVICES + STATIC_LOCAL_DEVICES


def proper_shutdown():
    """Clean up resources at exit, specifically asyncio tasks."""
    global _background_task

    # Cancel any pending asyncio tasks
    try:
        if _background_task and not _background_task.done():
            _background_task.cancel()

        # Get the current event loop and cancel all tasks
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()

                # Run the loop briefly to process cancellations
                if tasks and loop.is_running():
                    pass  # Loop is already running, let it process cancellations
                elif tasks:
                    loop.run_until_complete(asyncio.sleep(0.1))

                # Close the loop
                loop.close()
        except Exception:
            pass  # Loop might already be closed

    except Exception as e:
        print_error(f"Error during shutdown: {e}")


def main() -> None:
    try:
        # Register the proper shutdown function
        atexit.register(proper_shutdown)

        ensure_config_directory()
        main_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
```
