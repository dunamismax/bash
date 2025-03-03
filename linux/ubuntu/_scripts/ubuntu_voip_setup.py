#!/usr/bin/env python3
"""
Enhanced Ubuntu VoIP Setup Utility
--------------------------------------------------

A beautiful, interactive terminal-based utility for setting up and configuring VoIP services
on Ubuntu systems. This utility performs the following operations:
  • Verifies system compatibility and prerequisites
  • Updates system packages
  • Installs required VoIP packages (Asterisk, MariaDB, ufw)
  • Configures firewall rules for SIP and RTP
  • Creates Asterisk configuration files (with backup of existing ones)
  • Manages related services (enabling and restarting Asterisk and MariaDB)
  • Verifies the overall setup

Note: This script requires root privileges.

Usage:
  sudo python3 voip_setup.py

Version: 2.0.0
"""

# ----------------------------------------------------------------
# Imports & Dependency Check
# ----------------------------------------------------------------
import atexit
import datetime
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any, Callable

# Check for required dependencies
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.live import Live
    from rich.columns import Columns
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "VoIP Setup Utility"
APP_SUBTITLE = "Ubuntu VoIP Service Configuration"
VERSION = "2.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.expanduser("~/voip_setup_logs/voip_setup.log")
OPERATION_TIMEOUT = 300  # seconds

# System detection
IS_LINUX = sys.platform.startswith("linux")
IS_UBUNTU = False
if IS_LINUX:
    try:
        with open("/etc/os-release") as f:
            if "ubuntu" in f.read().lower():
                IS_UBUNTU = True
    except (FileNotFoundError, PermissionError):
        pass

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# VoIP Configuration
VOIP_PACKAGES = [
    "asterisk",
    "asterisk-config",
    "mariadb-server",
    "mariadb-client",
    "ufw",
]

FIREWALL_RULES = [
    {"port": "5060", "protocol": "udp", "description": "SIP"},
    {"port": "5061", "protocol": "tcp", "description": "SIP/TLS"},
    {"port": "16384:32767", "protocol": "udp", "description": "RTP Audio"},
]

ASTERISK_CONFIGS = {
    "sip_custom.conf": """[general]
disallow=all
allow=g722
context=internal
bindport=5060
bindaddr=0.0.0.0
transport=udp,tcp
alwaysauthreject=yes
directmedia=no
nat=force_rport,comedia

[6001]
type=friend
context=internal
host=dynamic
secret=changeme6001
callerid=Phone 6001 <6001>
disallow=all
allow=g722

[6002]
type=friend
context=internal
host=dynamic
secret=changeme6002
callerid=Phone 6002 <6002>
disallow=all
allow=g722
""",
    "extensions_custom.conf": """[internal]
exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})
 same => n,Dial(SIP/${EXTEN},20)
 same => n,Hangup()

[default]
exten => s,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
""",
}

SERVICES = ["asterisk", "mariadb"]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console
console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ServiceStatus:
    """
    Represents a service with its status information.

    Attributes:
        name: The service name
        active: Whether the service is active/running
        enabled: Whether the service is enabled at boot
        version: Version information if available
    """

    name: str
    active: Optional[bool] = None  # True = running, False = stopped, None = unknown
    enabled: Optional[bool] = None  # True = enabled, False = disabled, None = unknown
    version: Optional[str] = None


@dataclass
class FirewallRule:
    """
    Represents a firewall rule.

    Attributes:
        port: Port number or range
        protocol: Protocol (udp, tcp)
        description: Human-readable description
        active: Whether the rule is active in the firewall
    """

    port: str
    protocol: str
    description: str
    active: Optional[bool] = None  # True = active, False = inactive, None = unknown


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
    compact_fonts = ["slant", "small", "smslant", "digital", "mini"]

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

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
            _                  _               
__   _____ (_)_ __    ___  ___| |_ _   _ _ __  
\ \ / / _ \| | '_ \  / __|/ _ \ __| | | | '_ \ 
 \ V / (_) | | |_) | \__ \  __/ |_| |_| | |_) |
  \_/ \___/|_| .__/  |___/\___|\__|\__,_| .__/ 
             |_|                        |_|    
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding
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
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(message: str) -> None:
    """Display an informational message."""
    print_message(message, NordColors.FROST_3, "ℹ")


def print_success(message: str) -> None:
    """Display a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Display a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Display an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(text: str) -> None:
    """Display a step description."""
    print_message(text, NordColors.FROST_2, "→")


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


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """
    Create a menu table using Rich.

    Args:
        title: Table title
        options: List of (key, description) tuples

    Returns:
        A Rich Table object
    """
    table = Table(
        title=title,
        box=None,
        title_style=f"bold {NordColors.FROST_2}",
        show_header=True,
        expand=True,
    )

    table.add_column(
        "Option", style=f"bold {NordColors.FROST_4}", justify="right", width=6
    )
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for key, description in options:
        table.add_row(key, description)

    return table


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until the user presses Enter."""
    console.input(f"\n[{NordColors.PURPLE}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get user input with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.FROST_3}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Get a user choice from a list of options."""
    return Prompt.ask(
        f"[bold {NordColors.FROST_3}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Prompt the user for a yes/no confirmation."""
    return Confirm.ask(f"[bold {NordColors.FROST_3}]{prompt}[/]")


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add any additional cleanup tasks here if needed


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
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
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout or OPERATION_TIMEOUT,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(
            f"Command timed out after {timeout or OPERATION_TIMEOUT} seconds: {' '.join(cmd)}"
        )
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking using Rich."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"[{NordColors.FROST_3}]starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """Thread-safe spinner for indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.FROST_2}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_3}]{self.message}[/] [[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self) -> None:
        with self._lock:
            if self.spinning:
                return
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            if not self.spinning:
                return
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            console.print("\r" + " " * TERM_WIDTH, end="\r")
            if success:
                console.print(
                    f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_3}]{self.message}[/] [{NordColors.GREEN}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.RED}]✗[/] [{NordColors.FROST_3}]{self.message}[/] [{NordColors.RED}]failed[/] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ----------------------------------------------------------------
# System Check Functions
# ----------------------------------------------------------------
def check_privileges() -> bool:
    """Check if the script is running with elevated privileges."""
    try:
        if os.name == "nt":
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except:
        return False


def check_system_compatibility() -> bool:
    """Check if the system is compatible with the VoIP setup."""
    print_section("System Compatibility Check")
    compatible = True

    if not check_privileges():
        print_error("This script requires root privileges. Please run with sudo.")
        compatible = False
    else:
        print_success("Running with root privileges")

    if not IS_LINUX:
        print_error("This script is designed for Linux systems.")
        compatible = False
    else:
        print_success("Linux system detected")

    if not IS_UBUNTU:
        print_warning(
            "Non-Ubuntu Linux detected. Some features might not work correctly."
        )
    else:
        print_success("Ubuntu system detected")

    if not shutil.which("apt-get"):
        print_error("apt-get not found. This script requires Ubuntu/Debian.")
        compatible = False
    else:
        print_success("apt-get is available")

    # Check total memory
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
            mem_total = (
                int(
                    [line for line in meminfo.split("\n") if "MemTotal" in line][
                        0
                    ].split()[1]
                )
                // 1024
            )
            if mem_total < 512:
                print_warning(
                    f"Low memory detected: {mem_total}MB. Recommended: at least 1GB."
                )
            else:
                print_success(f"Memory check passed: {mem_total}MB available")
    except:
        print_warning("Could not check system memory")

    # Check internet connectivity
    try:
        with Spinner("Checking internet connectivity") as spinner:
            result = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False)
        if result.returncode == 0:
            print_success("Internet connectivity confirmed")
        else:
            print_warning("Internet connectivity issues detected. Setup may fail.")
            compatible = False
    except Exception as e:
        print_error(f"Internet connectivity check failed: {e}")
        compatible = False

    if compatible:
        print_success("System is compatible with VoIP setup")
    else:
        print_warning("System compatibility issues detected")

    return compatible


def print_header(text: str) -> None:
    """Display a stylized section header using pyfiglet."""
    try:
        ascii_art = pyfiglet.figlet_format(text, font="slant")
        console.print(ascii_art, style=f"bold {NordColors.FROST_2}")
    except Exception:
        # Fallback if pyfiglet fails
        border = "=" * TERM_WIDTH
        console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
        console.print(f"[bold {NordColors.FROST_2}]  {text.center(TERM_WIDTH - 4)}[/]")
        console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")


def print_section(title: str) -> None:
    """Display a formatted section header."""
    border = "━" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}  [/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")


# ----------------------------------------------------------------
# VoIP Setup Task Functions
# ----------------------------------------------------------------
def update_system() -> bool:
    """Update system packages."""
    print_section("Updating System Packages")
    try:
        with Spinner("Updating package lists") as spinner:
            run_command(["apt-get", "update"])
        print_success("Package lists updated successfully")

        try:
            result = run_command(["apt", "list", "--upgradable"], capture_output=True)
            lines = result.stdout.splitlines()
            package_count = max(1, len(lines) - 1)  # First line is header
            print_info(f"Found {package_count} upgradable packages")
        except Exception:
            package_count = 10  # Default if we can't determine
            print_warning("Could not determine number of upgradable packages")

        with ProgressManager() as progress:
            task = progress.add_task("Upgrading packages", total=package_count)

            process = subprocess.Popen(
                ["apt-get", "upgrade", "-y"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in iter(process.stdout.readline, ""):
                if "Unpacking" in line or "Setting up" in line:
                    progress.update(task, advance=1)
                status_text = f"[{NordColors.FROST_3}]{line.strip()[:40]}"
                progress.update(task, status=status_text)

            process.wait()
            if process.returncode != 0:
                print_error("System upgrade failed")
                return False

        print_success("System packages updated successfully")
        return True
    except Exception as e:
        print_error(f"System update failed: {e}")
        return False


def install_packages(packages: List[str]) -> bool:
    """Install the specified VoIP packages."""
    if not packages:
        print_warning("No packages specified for installation")
        return True

    print_section("Installing VoIP Packages")
    print_info(f"Packages to install: {', '.join(packages)}")

    failed_packages = []
    with ProgressManager() as progress:
        task = progress.add_task("Installing packages", total=len(packages))

        for idx, pkg in enumerate(packages):
            print_step(f"Installing {pkg} ({idx + 1}/{len(packages)})")
            try:
                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                for line in iter(proc.stdout.readline, ""):
                    status_text = f"[{NordColors.FROST_3}]{line.strip()[:40]}"
                    progress.update(task, status=status_text)

                proc.wait()
                if proc.returncode != 0:
                    print_error(f"Failed to install {pkg}")
                    failed_packages.append(pkg)
                else:
                    print_success(f"{pkg} installed successfully")
            except Exception as e:
                print_error(f"Error installing {pkg}: {e}")
                failed_packages.append(pkg)

            progress.update(task, advance=1)

    if failed_packages:
        print_warning(
            f"Failed to install the following packages: {', '.join(failed_packages)}"
        )
        return False

    print_success("All packages installed successfully")
    return True


def configure_firewall(rules: List[Dict[str, str]]) -> bool:
    """Configure firewall rules for VoIP services."""
    print_section("Configuring Firewall")
    try:
        if not shutil.which("ufw"):
            print_warning("UFW firewall not found. Installing ufw...")
            if not install_packages(["ufw"]):
                return False

        with ProgressManager() as progress:
            task = progress.add_task("Configuring firewall", total=len(rules) + 2)

            # Check UFW status
            status_result = run_command(["ufw", "status"], check=False)
            if "Status: inactive" in status_result.stdout:
                print_step("Enabling UFW firewall...")
                run_command(["ufw", "--force", "enable"])
            progress.update(task, advance=1)

            # Configure each rule
            for rule in rules:
                rule_desc = f"{rule['port']}/{rule['protocol']} ({rule['description']})"
                print_step(f"Adding rule for {rule_desc}")
                run_command(["ufw", "allow", f"{rule['port']}/{rule['protocol']}"])
                progress.update(task, advance=1)

            # Reload firewall
            print_step("Reloading firewall configuration")
            run_command(["ufw", "reload"])
            progress.update(task, advance=1)

        print_success("Firewall configured successfully")
        return True
    except Exception as e:
        print_error(f"Firewall configuration failed: {e}")
        return False


def create_asterisk_config(configs: Dict[str, str]) -> bool:
    """Create or update Asterisk configuration files (backing up existing ones)."""
    print_section("Creating Asterisk Configuration Files")
    try:
        config_dir = Path("/etc/asterisk")
        if not config_dir.exists():
            print_step(f"Creating configuration directory: {config_dir}")
            config_dir.mkdir(parents=True, exist_ok=True)

        with ProgressManager() as progress:
            task = progress.add_task("Creating config files", total=len(configs))

            for filename, content in configs.items():
                file_path = config_dir / filename
                print_step(f"Creating {filename}")

                # Backup existing file if needed
                if file_path.exists():
                    backup_path = file_path.with_suffix(f".bak.{int(time.time())}")
                    shutil.copy2(file_path, backup_path)
                    print_info(f"Backed up existing file to {backup_path.name}")

                # Write new configuration
                file_path.write_text(content)
                print_success(f"Configuration file {filename} created")
                progress.update(task, advance=1)

        print_success("Asterisk configuration files created successfully")
        return True
    except Exception as e:
        print_error(f"Failed to create Asterisk configuration files: {e}")
        return False


def manage_services(services: List[str], action: str) -> bool:
    """Enable, disable, start, restart, or stop services."""
    valid_actions = ["enable", "disable", "start", "restart", "stop"]
    if action not in valid_actions:
        print_error(
            f"Invalid action '{action}'. Valid actions are: {', '.join(valid_actions)}"
        )
        return False

    print_section(f"{action.capitalize()}ing Services")
    failed_services = []

    with ProgressManager() as progress:
        task = progress.add_task(
            f"{action.capitalize()}ing services", total=len(services)
        )

        for service in services:
            print_step(f"{action.capitalize()}ing {service}")
            try:
                run_command(["systemctl", action, service])
                print_success(f"{service} {action}ed successfully")
            except Exception as e:
                print_error(f"Failed to {action} {service}: {e}")
                failed_services.append(service)

            progress.update(task, advance=1)

    if failed_services:
        print_warning(
            f"Failed to {action} the following services: {', '.join(failed_services)}"
        )
        return False

    print_success(f"All services {action}ed successfully")
    return True


def verify_installation() -> bool:
    """Verify the VoIP setup installation."""
    print_section("Verifying VoIP Setup")
    verification_items = []
    passed_items = []
    failed_items = []

    # Define verification items
    verification_items.append(
        ("Asterisk Installation", lambda: bool(shutil.which("asterisk")))
    )
    verification_items.append(
        ("MariaDB Installation", lambda: bool(shutil.which("mysql")))
    )

    # Check services
    for service in SERVICES:
        verification_items.append(
            (
                f"{service.capitalize()} Service",
                lambda s=service: run_command(
                    ["systemctl", "is-active", s], check=False
                ).stdout.strip()
                == "active",
            )
        )

    # Check configuration files
    config_dir = Path("/etc/asterisk")
    for filename in ASTERISK_CONFIGS.keys():
        verification_items.append(
            (f"{filename} Config", lambda f=filename: (config_dir / f).exists())
        )

    # Check firewall rules
    for rule in FIREWALL_RULES:
        rule_str = f"{rule['port']}/{rule['protocol']}"
        verification_items.append(
            (
                f"Firewall Rule: {rule_str}",
                lambda r=rule_str: r
                in run_command(["ufw", "status"], capture_output=True).stdout,
            )
        )

    # Run the verification checks
    with ProgressManager() as progress:
        task = progress.add_task(
            "Verifying installation", total=len(verification_items)
        )

        for item_name, check_func in verification_items:
            print_step(f"Checking {item_name}")
            try:
                if check_func():
                    print_success(f"{item_name}: Passed")
                    passed_items.append(item_name)
                else:
                    print_error(f"{item_name}: Failed")
                    failed_items.append(item_name)
            except Exception as e:
                print_error(f"Error checking {item_name}: {e}")
                failed_items.append(item_name)

            progress.update(task, advance=1)

    # Display verification summary
    print_section("Verification Summary")
    console.print(
        f"Passed: [bold {NordColors.GREEN}]{len(passed_items)}/{len(verification_items)}[/]"
    )
    console.print(
        f"Failed: [bold {NordColors.RED}]{len(failed_items)}/{len(verification_items)}[/]"
    )

    if failed_items:
        print_warning("The following checks failed:")
        for item in failed_items:
            console.print(f"[{NordColors.RED}]• {item}[/]")

    if len(passed_items) == len(verification_items):
        print_success(
            "Verification completed successfully. VoIP setup is properly configured."
        )
        return True
    else:
        print_warning("Verification completed with some issues.")
        return False


def perform_full_setup() -> bool:
    """Perform a full VoIP setup."""
    clear_screen()
    console.print(create_header())

    # Display system info
    console.print(f"Hostname: [bold {NordColors.SNOW_STORM_1}]{HOSTNAME}[/]")
    console.print(
        f"System: [bold {NordColors.SNOW_STORM_1}]{platform.system()} {platform.release()}[/]"
    )
    console.print(
        f"Timestamp: [bold {NordColors.SNOW_STORM_1}]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
    )

    start_time = time.time()

    # Check privileges
    if not check_privileges():
        print_error("This script requires root privileges. Please run with sudo.")
        return False

    # Check system compatibility
    if not check_system_compatibility():
        if not get_user_confirmation(
            "System compatibility issues detected. Continue anyway?"
        ):
            return False

    # Update system
    if get_user_confirmation("Update system packages?"):
        if not update_system():
            if not get_user_confirmation(
                "System update encountered issues. Continue anyway?"
            ):
                return False

    # Install VoIP packages
    if get_user_confirmation("Install VoIP packages?"):
        if not install_packages(VOIP_PACKAGES):
            if not get_user_confirmation(
                "Package installation failed. Continue anyway?"
            ):
                return False

    # Configure firewall
    if get_user_confirmation("Configure firewall rules?"):
        if not configure_firewall(FIREWALL_RULES):
            if not get_user_confirmation(
                "Firewall configuration failed. Continue anyway?"
            ):
                return False

    # Create Asterisk configuration
    if get_user_confirmation("Create Asterisk configuration files?"):
        if not create_asterisk_config(ASTERISK_CONFIGS):
            if not get_user_confirmation(
                "Asterisk configuration failed. Continue anyway?"
            ):
                return False

    # Enable and restart services
    if get_user_confirmation("Enable and restart services?"):
        if not manage_services(SERVICES, "enable") or not manage_services(
            SERVICES, "restart"
        ):
            if not get_user_confirmation("Service management failed. Continue anyway?"):
                return False

    # Verify installation
    verification_result = False
    if get_user_confirmation("Verify the installation?"):
        verification_result = verify_installation()

    # Display summary
    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)

    print_header("Setup Summary")
    print_success(f"Elapsed time: {int(minutes)}m {int(seconds)}s")

    if verification_result:
        print_success("VoIP setup completed successfully")
    else:
        print_warning("VoIP setup completed with warnings or errors")

    # Next steps
    print_section("Next Steps")
    console.print(
        f"[{NordColors.SNOW_STORM_1}]1. Review the Asterisk configuration files in /etc/asterisk/[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]2. Configure SIP clients with the credentials from sip_custom.conf[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]3. Test calling between the configured extensions (6001-6002)[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]4. Consider securing SIP with TLS for production use[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]5. Set up voicemail and additional call routing as needed[/]"
    )

    return verification_result


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def service_menu() -> None:
    """Display and handle the service management menu."""
    while True:
        clear_screen()
        console.print(create_header())
        print_section("Service Management")

        menu_options = [
            ("1", "Enable Services"),
            ("2", "Disable Services"),
            ("3", "Start Services"),
            ("4", "Restart Services"),
            ("5", "Stop Services"),
            ("6", "View Service Status"),
            ("0", "Back to Main Menu"),
        ]

        console.print(create_menu_table("Service Menu", menu_options))
        choice = get_user_input("Enter your choice (0-6):")

        if choice == "1":
            manage_services(SERVICES, "enable")
            pause()
        elif choice == "2":
            manage_services(SERVICES, "disable")
            pause()
        elif choice == "3":
            manage_services(SERVICES, "start")
            pause()
        elif choice == "4":
            manage_services(SERVICES, "restart")
            pause()
        elif choice == "5":
            manage_services(SERVICES, "stop")
            pause()
        elif choice == "6":
            # Display service status
            print_section("Service Status")
            table = Table(show_header=True)
            table.add_column("Service", style=f"bold {NordColors.FROST_3}")
            table.add_column("Status", style=f"{NordColors.SNOW_STORM_1}")
            table.add_column("Enabled", style=f"{NordColors.SNOW_STORM_1}")

            for service in SERVICES:
                try:
                    active = run_command(
                        ["systemctl", "is-active", service], check=False
                    ).stdout.strip()
                    enabled = run_command(
                        ["systemctl", "is-enabled", service], check=False
                    ).stdout.strip()

                    active_status = "Active" if active == "active" else "Inactive"
                    active_style = (
                        NordColors.GREEN if active == "active" else NordColors.RED
                    )

                    enabled_status = "Yes" if enabled == "enabled" else "No"
                    enabled_style = (
                        NordColors.GREEN if enabled == "enabled" else NordColors.RED
                    )

                    table.add_row(
                        service,
                        f"[{active_style}]{active_status}[/]",
                        f"[{enabled_style}]{enabled_status}[/]",
                    )
                except Exception as e:
                    table.add_row(
                        service,
                        f"[{NordColors.RED}]Error[/]",
                        f"[{NordColors.RED}]Error[/]",
                    )

            console.print(table)
            pause()
        elif choice == "0":
            return
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def configuration_menu() -> None:
    """Display and handle the configuration menu."""
    while True:
        clear_screen()
        console.print(create_header())
        print_section("Configuration Options")

        menu_options = [
            ("1", "Show Asterisk Configuration"),
            ("2", "Show Firewall Rules"),
            ("3", "Edit sip_custom.conf"),
            ("4", "Edit extensions_custom.conf"),
            ("5", "Restart Asterisk to Apply Changes"),
            ("0", "Back to Main Menu"),
        ]

        console.print(create_menu_table("Configuration Menu", menu_options))
        choice = get_user_input("Enter your choice (0-5):")

        if choice == "1":
            # Show Asterisk Configuration
            print_section("Asterisk Configuration")

            config_dir = Path("/etc/asterisk")
            for filename in ASTERISK_CONFIGS.keys():
                file_path = config_dir / filename
                if file_path.exists():
                    content = file_path.read_text()
                    console.print(
                        Panel(
                            Text(content, style=f"{NordColors.SNOW_STORM_1}"),
                            title=f"[bold {NordColors.FROST_2}]{filename}[/]",
                            border_style=Style(color=NordColors.FROST_3),
                            expand=False,
                        )
                    )
                else:
                    print_warning(f"Configuration file {filename} not found")

            pause()
        elif choice == "2":
            # Show Firewall Rules
            print_section("Firewall Rules")
            try:
                result = run_command(["ufw", "status", "verbose"], check=False)
                if result.returncode == 0:
                    console.print(
                        Panel(
                            Text(result.stdout, style=f"{NordColors.SNOW_STORM_1}"),
                            title=f"[bold {NordColors.FROST_2}]UFW Status[/]",
                            border_style=Style(color=NordColors.FROST_3),
                            expand=False,
                        )
                    )
                else:
                    print_error("Failed to get firewall status")
            except Exception as e:
                print_error(f"Error checking firewall status: {e}")

            pause()
        elif choice == "3" or choice == "4":
            # Edit configuration files
            filename = "sip_custom.conf" if choice == "3" else "extensions_custom.conf"
            editor = os.environ.get("EDITOR", "nano")

            print_info(f"Opening {filename} with {editor}...")
            print_warning(
                "Be careful with your edits. Invalid configuration can break your VoIP setup."
            )

            file_path = Path(f"/etc/asterisk/{filename}")
            if not file_path.exists():
                print_error(f"File {filename} not found. Creating it first.")
                create_asterisk_config({filename: ASTERISK_CONFIGS[filename]})

            try:
                subprocess.run([editor, file_path])
                print_success(f"Finished editing {filename}")
            except Exception as e:
                print_error(f"Error editing file: {e}")

            pause()
        elif choice == "5":
            # Restart Asterisk
            if get_user_confirmation(
                "Restart Asterisk to apply configuration changes?"
            ):
                manage_services(["asterisk"], "restart")
            pause()
        elif choice == "0":
            return
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        console.print(create_header())

        # Display system info
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(
            f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))}"
        )
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Warning for non-root users
        if not check_privileges():
            console.print(
                Panel(
                    "[bold "
                    + NordColors.RED
                    + "]This script requires root privileges.[/]\nPlease restart using sudo or as root.",
                    title="Warning",
                    border_style=f"bold {NordColors.RED}",
                )
            )

        # Menu options
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Update System Packages"),
            ("3", "Install VoIP Packages"),
            ("4", "Configure Firewall Rules"),
            ("5", "Create Asterisk Configuration"),
            ("6", "Service Management"),
            ("7", "Configuration Options"),
            ("8", "Verify Installation"),
            ("9", "Perform Full Setup"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))
        choice = get_user_input("Enter your choice (0-9):")

        if choice == "1":
            check_system_compatibility()
            pause()
        elif choice == "2":
            update_system()
            pause()
        elif choice == "3":
            install_packages(VOIP_PACKAGES)
            pause()
        elif choice == "4":
            configure_firewall(FIREWALL_RULES)
            pause()
        elif choice == "5":
            create_asterisk_config(ASTERISK_CONFIGS)
            pause()
        elif choice == "6":
            service_menu()
        elif choice == "7":
            configuration_menu()
        elif choice == "8":
            verify_installation()
            pause()
        elif choice == "9":
            perform_full_setup()
            pause()
        elif choice == "0":
            clear_screen()
            console.print(create_header())
            print_success("Thank you for using the VoIP Setup Utility!")
            console.print(
                Panel(
                    "Developed with ♥ using Rich and Pyfiglet",
                    border_style=Style(color=NordColors.FROST_1),
                    title=f"[bold {NordColors.FROST_2}]Goodbye![/]",
                    padding=(1, 2),
                )
            )
            time.sleep(1.5)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        setup_logging()
        main_menu()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
