#!/usr/bin/env python3
"""
Automated Ubuntu VoIP Setup Utility
--------------------------------------------------

A beautiful terminal-based utility that automatically sets up and configures VoIP services
on Ubuntu systems without user interaction. This utility performs the following operations:
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

Version: 3.0.0
"""

import atexit
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
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
# Configuration
# ----------------------------------------------------------------
APP_NAME = "VoIP Setup"
APP_SUBTITLE = "Automated VoIP Service Configuration"
VERSION = "3.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/voip_setup.log"
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
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

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

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
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
    logging.info(f"{prefix} {text}")


def print_info(message: str) -> None:
    """Display an informational message."""
    print_message(message, NordColors.FROST_3, "ℹ")


def print_success(message: str) -> None:
    """Display a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Display a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")
    logging.warning(message)


def print_error(message: str) -> None:
    """Display an error message."""
    print_message(message, NordColors.RED, "✗")
    logging.error(message)


def print_step(text: str) -> None:
    """Display a step description."""
    print_message(text, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Display a formatted section header."""
    border = "━" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}  [/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")
    logging.info(f"SECTION: {title}")


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
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
        # Add a StreamHandler for console output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(console_handler)

        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        # Set up a basic console logger instead
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        print_step("Continuing with console logging only...")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    logging.info("Script execution completed, performing cleanup")


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
    logging.warning(f"Script interrupted by {sig_name}")
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
    silent: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        silent: Whether to suppress output to console

    Returns:
        CompletedProcess instance with command results
    """
    cmd_str = " ".join(cmd)
    if not silent:
        print_step(f"Running: {cmd_str}")
    logging.info(f"Executing command: {cmd_str}")

    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=False,  # We'll handle errors manually
            text=True,
            capture_output=capture_output,
            timeout=timeout or OPERATION_TIMEOUT,
        )

        if result.returncode != 0 and check:
            if not silent:
                print_error(
                    f"Command failed with exit code {result.returncode}: {cmd_str}"
                )
                if result.stdout and not result.stdout.isspace():
                    console.print(f"[dim]{result.stdout.strip()}[/dim]")
                if result.stderr and not result.stderr.isspace():
                    console.print(f"[bold {NordColors.RED}]{result.stderr.strip()}[/]")
            logging.error(
                f"Command failed with exit code {result.returncode}: {cmd_str}"
            )
            logging.error(f"STDOUT: {result.stdout.strip()}")
            logging.error(f"STDERR: {result.stderr.strip()}")
            if check:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )
        else:
            if not silent:
                if (
                    result.stdout
                    and not result.stdout.isspace()
                    and len(result.stdout) < 1000
                ):
                    console.print(f"[dim]{result.stdout.strip()}[/dim]")
            logging.debug(f"Command succeeded: {cmd_str}")
            logging.debug(f"STDOUT: {result.stdout.strip() if result.stdout else ''}")

        return result
    except subprocess.TimeoutExpired:
        print_error(
            f"Command timed out after {timeout or OPERATION_TIMEOUT} seconds: {cmd_str}"
        )
        logging.error(f"Command timed out: {cmd_str}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {cmd_str}\nDetails: {e}")
        logging.error(f"Error executing command: {cmd_str}\nDetails: {e}")
        raise


# ----------------------------------------------------------------
# Progress Tracking Class
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking using Rich."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {{task.fields[color]}}]{{task.description}}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TextColumn("{{task.fields[status]}}"),
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
    """
    Check if the system is compatible with the VoIP setup.
    Returns True if compatible, False otherwise.
    """
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
    print_step("Checking internet connectivity...")
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Checking internet connectivity"),
            console=console,
        ) as progress:
            task = progress.add_task("Testing connection", total=1)
            result = run_command(
                ["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False, silent=True
            )
            progress.update(task, completed=1)

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


# ----------------------------------------------------------------
# VoIP Setup Task Functions
# ----------------------------------------------------------------
def update_system() -> bool:
    """
    Update system packages.
    Returns True if successful, False otherwise.
    """
    print_section("Updating System Packages")
    try:
        # Update package lists
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Updating package lists"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Updating", total=1)
            run_command(["apt-get", "update"], silent=True)
            progress.update(task, completed=1)

        print_success("Package lists updated successfully")

        # Try to get upgradable package count for better progress reporting
        try:
            result = run_command(
                ["apt", "list", "--upgradable"], capture_output=True, silent=True
            )
            lines = result.stdout.splitlines()
            package_count = max(1, len(lines) - 1)  # First line is header
            print_info(f"Found {package_count} upgradable packages")
        except Exception:
            package_count = 10  # Default if we can't determine
            print_warning("Could not determine number of upgradable packages")

        # Perform system upgrade with progress tracking
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
    """
    Install the specified VoIP packages.
    Returns True if all packages installed successfully, False otherwise.
    """
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
                # Use DEBIAN_FRONTEND=noninteractive to prevent prompts
                env = os.environ.copy()
                env["DEBIAN_FRONTEND"] = "noninteractive"

                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
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
    """
    Configure firewall rules for VoIP services.
    Returns True if successful, False otherwise.
    """
    print_section("Configuring Firewall")
    try:
        if not shutil.which("ufw"):
            print_warning("UFW firewall not found. Installing ufw...")
            if not install_packages(["ufw"]):
                return False

        with ProgressManager() as progress:
            task = progress.add_task("Configuring firewall", total=len(rules) + 2)

            # Check UFW status
            status_result = run_command(["ufw", "status"], check=False, silent=True)
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
    """
    Create or update Asterisk configuration files (backing up existing ones).
    Returns True if successful, False otherwise.
    """
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
    """
    Enable, disable, start, restart, or stop services.
    Returns True if successful for all services, False otherwise.
    """
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
    """
    Verify the VoIP setup installation.
    Returns True if all checks pass, False otherwise.
    """
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
                    ["systemctl", "is-active", s], check=False, silent=True
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
                in run_command(
                    ["ufw", "status"], capture_output=True, silent=True
                ).stdout,
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


# ----------------------------------------------------------------
# Main Function
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function to perform the VoIP setup automatically.
    """
    start_time = time.time()

    # Clear screen and display header
    console.clear()
    console.print(create_header())

    # Configure logging
    setup_logging()

    # Display system info
    console.print(
        f"[{NordColors.FROST_3}]Hostname:[/] [{NordColors.SNOW_STORM_1}]{HOSTNAME}[/]"
    )
    console.print(
        f"[{NordColors.FROST_3}]System:[/] [{NordColors.SNOW_STORM_1}]{platform.system()} {platform.release()}[/]"
    )
    console.print(
        f"[{NordColors.FROST_3}]Timestamp:[/] [{NordColors.SNOW_STORM_1}]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
    )
    console.print()

    # Check privileges and abort if not root
    if not check_privileges():
        print_error("This script requires root privileges. Please run with sudo.")
        sys.exit(1)

    # Check system compatibility
    system_compatible = check_system_compatibility()
    if not system_compatible:
        print_warning(
            "System compatibility check failed. Continuing anyway, but errors may occur."
        )

    # Create a task list for overall progress tracking
    tasks = [
        ("Update system packages", update_system),
        ("Install VoIP packages", lambda: install_packages(VOIP_PACKAGES)),
        ("Configure firewall", lambda: configure_firewall(FIREWALL_RULES)),
        (
            "Create Asterisk configuration",
            lambda: create_asterisk_config(ASTERISK_CONFIGS),
        ),
        ("Enable services", lambda: manage_services(SERVICES, "enable")),
        ("Restart services", lambda: manage_services(SERVICES, "restart")),
        ("Verify installation", verify_installation),
    ]

    # Track overall success
    overall_success = True
    failed_tasks = []

    # Execute all tasks
    with ProgressManager() as progress:
        overall_task = progress.add_task("Overall Setup Progress", total=len(tasks))

        for task_name, task_func in tasks:
            print_section(f"Task: {task_name}")
            try:
                task_success = task_func()
                if not task_success:
                    print_warning(f"Task '{task_name}' completed with issues")
                    failed_tasks.append(task_name)
                    overall_success = False
                else:
                    print_success(f"Task '{task_name}' completed successfully")
            except Exception as e:
                print_error(f"Task '{task_name}' failed with error: {e}")
                logging.exception(f"Task '{task_name}' failed with error")
                failed_tasks.append(task_name)
                overall_success = False

            progress.update(overall_task, advance=1)

    # Display summary
    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)

    print_section("Setup Summary")
    print_success(f"Elapsed time: {int(minutes)}m {int(seconds)}s")

    if overall_success:
        print_success("VoIP setup completed successfully!")
    else:
        print_warning("VoIP setup completed with warnings or errors")
        print_warning("The following tasks had issues:")
        for task in failed_tasks:
            console.print(f"[{NordColors.RED}]• {task}[/]")

    # Next steps info
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
    console.print()

    logging.info("Script execution completed")


# ----------------------------------------------------------------
# Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unexpected error occurred")
        sys.exit(1)
