#!/usr/bin/env python3
"""
Enhanced Ubuntu VoIP Setup Utility
---------------------------------

A beautiful, interactive terminal-based utility for setting up and configuring VoIP services
on Ubuntu. This utility performs the following operations:
  • Verifies system compatibility and prerequisites
  • Updates system packages
  • Installs required VoIP packages (Asterisk, MariaDB, ufw)
  • Configures firewall rules for SIP and RTP
  • Creates Asterisk configuration files (with backup of existing ones)
  • Manages related services (enabling and restarting Asterisk and MariaDB)
  • Verifies the overall setup

Note: This script requires root privileges.

Version: 1.0.0
"""

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
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskID,
)
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "VoIP Setup Utility"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.expanduser("~/voip_setup_logs/voip_setup.log")

# Terminal dimensions
import shutil

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
    {"port": "16384:32767", "protocol": "udp", "description": "RTP Audio"},
]

ASTERISK_CONFIGS = {
    "sip_custom.conf": """[general]
disallow=all
allow=g722

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

OPERATION_TIMEOUT = 300  # seconds

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()


# Nord Theme Color Definitions
class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark/background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"

    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"

    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"

    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Get a choice from the user with a styled prompt."""
    return Prompt.ask(
        f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Get confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")

    for key, description in options:
        table.add_row(key, description)

    return table


# ==============================
# Logging Setup
# ==============================
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


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add specific cleanup tasks here


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ==============================
# Progress Tracking Classes
# ==============================
class ProgressManager:
    """Unified progress tracking system with multiple display options."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.NORD8
    ) -> TaskID:
        """Add a new task to the progress manager."""
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        """Update a task's progress."""
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self):
        """Start displaying the progress bar."""
        self.progress.start()

    def stop(self):
        """Stop displaying the progress bar."""
        self.progress.stop()


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
        """Internal method to update the spinner."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)  # Spinner update interval

    def start(self) -> None:
        """Start the spinner."""
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner and display completion message."""
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            # Clear the line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            if success:
                console.print(
                    f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD14}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD11}]failed[/] after {time_str}"
                )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit."""
        self.stop(success=exc_type is None)


# ==============================
# Helper Functions
# ==============================
def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def check_privileges() -> bool:
    """Check if script is running with elevated privileges."""
    try:
        if os.name == "nt":  # Windows
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:  # Unix/Linux/Mac
            return os.geteuid() == 0
    except:
        return False


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
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
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(
                f"[bold {NordColors.NORD11}]Stderr: {e.stderr.strip()}[/bold {NordColors.NORD11}]"
            )
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ==============================
# VoIP Setup Task Functions
# ==============================
def check_system_compatibility() -> bool:
    """Check if the system is compatible with VoIP setup."""
    print_section("System Compatibility Check")

    compatible = True

    # Check for root privileges
    if not check_privileges():
        print_error("This script requires root privileges. Please run with sudo.")
        compatible = False
    else:
        print_success("Running with root privileges")

    # Check for Ubuntu/Debian
    if not shutil.which("apt-get"):
        print_error("apt-get not found. This script requires Ubuntu/Debian.")
        compatible = False
    else:
        print_success("apt-get is available")

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


def update_system() -> bool:
    """Update system packages."""
    print_section("Updating System Packages")

    try:
        # Update package lists
        with Spinner("Updating package lists") as spinner:
            run_command(["apt-get", "update"])
        print_success("Package lists updated")

        # Get number of upgradable packages
        try:
            result = run_command(["apt", "list", "--upgradable"], capture_output=True)
            lines = result.stdout.splitlines()
            package_count = max(1, len(lines) - 1)  # Exclude header
            print_info(f"Found {package_count} upgradable packages")
        except Exception:
            package_count = 10
            print_warning("Could not determine number of upgradable packages")

        # Upgrade packages with progress bar
        with ProgressManager() as progress:
            task = progress.add_task("Upgrading packages", total=package_count)
            progress.start()

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
                status_text = f"[{NordColors.NORD9}]{line.strip()[:30]}"
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
    """Install the specified packages."""
    if not packages:
        print_warning("No packages specified for installation")
        return True

    print_section("Installing VoIP Packages")
    print_info(f"Packages to install: {', '.join(packages)}")

    failed_packages = []

    with ProgressManager() as progress:
        task = progress.add_task("Installing packages", total=len(packages))
        progress.start()

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
                    status_text = f"[{NordColors.NORD9}]{line.strip()[:30]}"
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
        # Check if ufw is installed
        if not shutil.which("ufw"):
            print_warning("UFW firewall not found. Installing ufw...")
            if not install_packages(["ufw"]):
                return False

        with ProgressManager() as progress:
            task = progress.add_task(
                "Configuring firewall", total=len(rules) + 2
            )  # +2 for status check and reload
            progress.start()

            # Check firewall status
            status_result = run_command(["ufw", "status"], check=False)
            if "Status: inactive" in status_result.stdout:
                print_step("Enabling UFW firewall...")
                run_command(["ufw", "--force", "enable"])
            progress.update(task, advance=1)

            # Add rules
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
    """Create or update Asterisk configuration files."""
    print_section("Creating Asterisk Configuration Files")

    try:
        config_dir = Path("/etc/asterisk")

        # Ensure config directory exists
        if not config_dir.exists():
            print_step(f"Creating configuration directory: {config_dir}")
            config_dir.mkdir(parents=True, exist_ok=True)

        with ProgressManager() as progress:
            task = progress.add_task("Creating config files", total=len(configs))
            progress.start()

            for filename, content in configs.items():
                file_path = config_dir / filename
                print_step(f"Creating {filename}")

                # Backup existing file if it exists
                if file_path.exists():
                    backup_path = file_path.with_suffix(f".bak.{int(time.time())}")
                    shutil.copy2(file_path, backup_path)
                    print_step(f"Backed up existing file to {backup_path.name}")

                # Write new config file
                file_path.write_text(content)
                print_success(f"Configuration file {filename} created")
                progress.update(task, advance=1)

        print_success("Asterisk configuration files created successfully")
        return True
    except Exception as e:
        print_error(f"Failed to create Asterisk configuration files: {e}")
        return False


def manage_services(services: List[str], action: str) -> bool:
    """Enable, disable, start, or restart services."""
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
        progress.start()

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

    # Add verification items
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

    # Check config files
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

    # Run verification
    with ProgressManager() as progress:
        task = progress.add_task(
            "Verifying installation", total=len(verification_items)
        )
        progress.start()

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

    # Print summary
    print_section("Verification Summary")
    console.print(
        f"Passed: [bold {NordColors.NORD14}]{len(passed_items)}/{len(verification_items)}[/]"
    )
    console.print(
        f"Failed: [bold {NordColors.NORD11}]{len(failed_items)}/{len(verification_items)}[/]"
    )

    if failed_items:
        print_warning("The following checks failed:")
        for item in failed_items:
            console.print(f"[{NordColors.NORD11}]• {item}[/]")

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
    print_header("Enhanced VoIP Setup")
    console.print(f"Hostname: [bold {NordColors.NORD4}]{HOSTNAME}[/]")
    console.print(
        f"Timestamp: [bold {NordColors.NORD4}]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
    )

    start_time = time.time()

    # Check for root privileges
    if not check_privileges():
        print_error("This script requires root privileges. Please run with sudo.")
        return False

    # Check system compatibility
    if not check_system_compatibility():
        if not get_user_confirmation(
            "System compatibility issues detected. Continue anyway?"
        ):
            return False

    # Update system packages
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

    # Calculate elapsed time
    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)

    # Print summary
    print_header("Setup Summary")
    print_success(f"Elapsed time: {int(minutes)}m {int(seconds)}s")

    if verification_result:
        print_success("VoIP setup completed successfully")
    else:
        print_warning("VoIP setup completed with warnings or errors")

    print_section("Next Steps")
    console.print(
        "[{NordColors.NORD4}]1. Review the Asterisk configuration files in /etc/asterisk/[/]"
    )
    console.print(
        "[{NordColors.NORD4}]2. Configure SIP clients with the provided credentials[/]"
    )
    console.print("[{NordColors.NORD4}]3. Test calling between extensions[/]")
    console.print(
        "[{NordColors.NORD4}]4. Consider securing SIP with TLS for production use[/]"
    )

    return verification_result


# ==============================
# Menu System
# ==============================
def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(
            f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))}"
        )
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Check for root privileges
        if not check_privileges():
            console.print(
                Panel(
                    "[bold {NordColors.NORD11}]This script requires root privileges.[/]\n"
                    "Please restart using sudo or as root.",
                    title="Warning",
                    border_style=f"bold {NordColors.NORD11}",
                )
            )

        # Main menu options
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Update System Packages"),
            ("3", "Install VoIP Packages"),
            ("4", "Configure Firewall Rules"),
            ("5", "Create Asterisk Configuration"),
            ("6", "Manage Services"),
            ("7", "Verify Installation"),
            ("8", "Perform Full Setup"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-8):")

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
            verify_installation()
            pause()
        elif choice == "8":
            perform_full_setup()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the VoIP Setup Utility.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def service_menu() -> None:
    """Display the service management menu."""
    while True:
        clear_screen()
        print_header("Service Management")

        # Service menu options
        menu_options = [
            ("1", "Enable Services"),
            ("2", "Disable Services"),
            ("3", "Start Services"),
            ("4", "Restart Services"),
            ("5", "Stop Services"),
            ("0", "Back to Main Menu"),
        ]

        console.print(create_menu_table("Service Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-5):")

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
        elif choice == "0":
            return
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Initial setup
        setup_logging()

        # Launch the main menu
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
