#!/usr/bin/env python3
"""
Enhanced Security Tools Installer
--------------------------------------------------

A streamlined system configuration tool that installs and configures security,
analysis, development, and intrusion detection tools on Ubuntu systems.

Usage:
  Run with sudo: sudo python3 security_installer.py
  Options:
    --simulate: Simulate installation without making changes
    --skip-confirm: Skip confirmation prompts
    --skip-failed: Continue even if some packages fail to install

Version: 5.2.0
"""

import os
import sys
import subprocess
import time
import logging
import glob
import signal
import atexit
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Callable
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
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
    )
    from rich.align import Align
    from rich.style import Style
    from rich.logging import RichHandler
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing required dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"],
            check=True,
            capture_output=True,
        )
        print("Dependencies installed. Please run the script again.")
    except subprocess.SubprocessError:
        print("Failed to install dependencies. Please install manually with:")
        print("pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION: str = "5.2.0"
APP_NAME: str = "Security Tools Installer"
APP_SUBTITLE: str = "System Security Configuration Tool"
LOG_DIR = Path("/var/log/security_setup")
LOG_FILE = LOG_DIR / f"security_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


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


# ----------------------------------------------------------------
# Security Tools Categories
# ----------------------------------------------------------------
SECURITY_TOOLS = {
    "Network Analysis": [
        "wireshark",
        "nmap",
        "tcpdump",
        "netcat-openbsd",
        "nethogs",
        "iftop",
        "ettercap-graphical",
        "dsniff",
        "netsniff-ng",
        "termshark",
        "ntopng",
        "zabbix-server-mysql",
        "prometheus",
        "bettercap",
        "p0f",
        "masscan",
        "arpwatch",
        "darkstat",
    ],
    "Vulnerability Assessment": [
        "nikto",
        "wapiti",
        "sqlmap",
        "dirb",
        "gobuster",
        "whatweb",
        "openvas",
    ],
    "Forensics": [
        "autopsy",
        "sleuthkit",
        "dc3dd",
        "testdisk",
        "foremost",
        "scalpel",
        "recoverjpeg",
        "extundelete",
        "xmount",
        "guymager",
        "plaso",
    ],
    "System Hardening": [
        "lynis",
        "rkhunter",
        "chkrootkit",
        "aide",
        "ufw",
        "fail2ban",
        "auditd",
        "apparmor",
        "firejail",
        "clamav",
        "crowdsec",
        "yubikey-manager",
        "policycoreutils",
    ],
    "Password & Crypto": [
        "john",
        "hashcat",
        "hydra",
        "medusa",
        "ophcrack",
        "fcrackzip",
        "gnupg",
        "cryptsetup",
        "yubikey-personalization",
        "keepassxc",
        "pass",
        "keychain",
        "ccrypt",
    ],
    "Wireless Security": [
        "aircrack-ng",
        "wifite",
        "hostapd",
        "reaver",
        "bully",
        "pixiewps",
        "mdk4",
        "bluez-tools",
        "btscanner",
        "horst",
        "wavemon",
        "cowpatty",
    ],
    "Development Tools": [
        "build-essential",
        "git",
        "gdb",
        "lldb",
        "cmake",
        "meson",
        "python3-pip",
        "python3-venv",
        "radare2",
        "apktool",
        "binwalk",
        "patchelf",
        "elfutils",
    ],
    "Container Security": [
        "docker.io",
        "docker-compose",
        "podman",
    ],
    "Malware Analysis": [
        "clamav",
        "yara",
        "pev",
        "ssdeep",
        "inetsim",
        "radare2",
    ],
    "Privacy & Anonymity": [
        "tor",
        "torbrowser-launcher",
        "privoxy",
        "proxychains4",
        "macchanger",
        "bleachbit",
        "mat2",
        "keepassxc",
        "openvpn",
        "wireguard",
        "onionshare",
    ],
}

# ----------------------------------------------------------------
# Problematic Packages Configuration
# ----------------------------------------------------------------
PROBLEMATIC_PACKAGES = {
    "samhain": {
        "service": "samhain.service",
        "config_dirs": ["/etc/samhain", "/var/lib/samhain"],
        "force_remove": True,
    }
}

# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def setup_logging() -> logging.Logger:
    """
    Set up logging configuration with RichHandler.

    Returns:
        Logger instance for the application
    """
    # Create log directory if it doesn't exist
    LOG_DIR.mkdir(exist_ok=True, parents=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler(LOG_FILE),
        ],
    )
    return logging.getLogger("security_setup")


# Initialize logger
logger = setup_logging()


def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["small", "slant", "digital", "chunky", "standard"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
 _                _    _               _              _     
| |__   __ _  ___| | _(_)_ __   __ _  | |_ ___   ___ | |___ 
| '_ \ / _` |/ __| |/ / | '_ \ / _` | | __/ _ \ / _ \| / __|
| | | | (_| | (__|   <| | | | | (_| | | || (_) | (_) | \__ \
|_| |_|\__,_|\___|_|\_\_|_| |_|\__, |  \__\___/ \___/|_|___/
                               |___/                        
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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 60 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with the header
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
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)
    # Additional cleanup tasks can be added here


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
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
    timeout: int = 30,
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
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise


# ----------------------------------------------------------------
# System Setup Class
# ----------------------------------------------------------------
class SystemSetup:
    """Handles system setup and package management operations."""

    def __init__(self, simulate: bool = False):
        self.simulate = simulate
        self.failed_packages: List[str] = []
        self.successful_packages: List[str] = []

    @staticmethod
    def check_root() -> bool:
        """Check if script is running with root privileges."""
        return os.geteuid() == 0

    def remove_problematic_package(self, package_name: str) -> bool:
        """
        Thoroughly remove a problematic package.

        Args:
            package_name: Name of the package to remove

        Returns:
            True if removal was successful or simulated, False otherwise
        """
        if self.simulate:
            logger.info(f"Simulating removal of problematic package {package_name}")
            return True

        pkg_info = PROBLEMATIC_PACKAGES.get(package_name)
        if not pkg_info:
            return True

        try:
            # Stop the service if it exists
            if pkg_info.get("service"):
                print_message(
                    f"Stopping service {pkg_info['service']}...", NordColors.FROST_3
                )
                subprocess.run(
                    ["systemctl", "stop", pkg_info["service"]],
                    check=False,
                    stderr=subprocess.DEVNULL,
                )

            # Kill any running processes
            print_message(
                f"Terminating any running processes for {package_name}...",
                NordColors.FROST_3,
            )
            subprocess.run(
                ["killall", "-9", package_name], check=False, stderr=subprocess.DEVNULL
            )

            # Remove package using different methods
            print_message(f"Removing package {package_name}...", NordColors.FROST_3)
            commands = [
                ["apt-get", "remove", "-y", package_name],
                ["apt-get", "purge", "-y", package_name],
                ["dpkg", "--remove", "--force-all", package_name],
                ["dpkg", "--purge", "--force-all", package_name],
            ]

            for cmd in commands:
                try:
                    subprocess.run(cmd, check=False, stderr=subprocess.PIPE)
                except subprocess.SubprocessError:
                    continue

            # Remove configuration directories
            if pkg_info.get("config_dirs"):
                for directory in pkg_info["config_dirs"]:
                    try:
                        if Path(directory).exists():
                            print_message(
                                f"Removing directory {directory}...", NordColors.FROST_3
                            )
                            subprocess.run(["rm", "-rf", directory], check=False)
                    except Exception as e:
                        logger.warning(f"Failed to remove directory {directory}: {e}")

            # Final cleanup of package status
            status_file = "/var/lib/dpkg/status"
            temp_file = "/var/lib/dpkg/status.tmp"
            try:
                if pkg_info.get("force_remove"):
                    print_message("Cleaning package status file...", NordColors.FROST_3)
                    with open(status_file, "r") as f_in, open(temp_file, "w") as f_out:
                        skip_block = False
                        for line in f_in:
                            if line.startswith(f"Package: {package_name}"):
                                skip_block = True
                                continue
                            if skip_block and line.startswith("Package:"):
                                skip_block = False
                            if not skip_block:
                                f_out.write(line)
                    os.rename(temp_file, status_file)
            except Exception as e:
                logger.warning(f"Failed to clean package status: {e}")

            print_message(
                f"Package {package_name} removed successfully", NordColors.GREEN, "✓"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to remove problematic package {package_name}: {e}")
            return False

    def cleanup_package_system(self) -> bool:
        """
        Clean up package management system and remove invalid files.

        Returns:
            True if cleanup was successful or simulated, False otherwise
        """
        try:
            # Clean up invalid .bak files in apt.conf.d
            apt_conf_path = "/etc/apt/apt.conf.d/"

            if self.simulate:
                print_message(
                    "Simulating package system cleanup...", NordColors.FROST_3
                )
                time.sleep(1)
                return True

            invalid_files = glob.glob(f"{apt_conf_path}/*.bak.*")
            if invalid_files:
                print_message(
                    f"Found {len(invalid_files)} invalid files to remove",
                    NordColors.FROST_3,
                )
                for file in invalid_files:
                    try:
                        os.remove(file)
                        logger.info(f"Removed invalid file: {file}")
                    except OSError as e:
                        logger.error(f"Failed to remove {file}: {e}")
            else:
                print_message("No invalid backup files found", NordColors.FROST_3)

            # Remove problematic packages first
            for package in PROBLEMATIC_PACKAGES:
                print_message(
                    f"Checking problematic package: {package}", NordColors.FROST_3
                )
                if not self.remove_problematic_package(package):
                    logger.warning(f"Failed to completely remove {package}")

            # Fix any interrupted dpkg processes
            print_message(
                "Configuring pending package installations...", NordColors.FROST_3
            )
            run_command(["dpkg", "--configure", "-a"])

            # Check if nala is installed, if not, use apt
            if Path("/usr/bin/nala").exists():
                print_message("Cleaning package cache with nala...", NordColors.FROST_3)
                run_command(["nala", "clean"])
                print_message(
                    "Removing unused packages with nala...", NordColors.FROST_3
                )
                run_command(["nala", "autoremove", "-y"])
            else:
                print_message("Cleaning package cache with apt...", NordColors.FROST_3)
                run_command(["apt", "clean"])
                print_message(
                    "Removing unused packages with apt...", NordColors.FROST_3
                )
                run_command(["apt", "autoremove", "-y"])

            print_message(
                "Package system cleanup completed successfully", NordColors.GREEN, "✓"
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Package system cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        """
        Configure and update package manager.

        Returns:
            True if setup was successful or simulated, False otherwise
        """
        try:
            if self.simulate:
                print_message("Simulating package manager setup...", NordColors.FROST_3)
                time.sleep(1)
                return True

            # First install nala if not present
            has_nala = Path("/usr/bin/nala").exists()

            if not has_nala:
                print_message("Installing nala package manager...", NordColors.FROST_3)
                run_command(["apt", "update"])
                run_command(["apt", "install", "nala", "-y"])
                print_message(
                    "Nala package manager installed successfully", NordColors.GREEN, "✓"
                )
                has_nala = True

            # Update package lists
            if has_nala:
                print_message("Updating package lists with nala...", NordColors.FROST_3)
                run_command(["nala", "update"])
                print_message("Upgrading packages with nala...", NordColors.FROST_3)
                run_command(["nala", "upgrade", "-y"])
            else:
                print_message("Updating package lists with apt...", NordColors.FROST_3)
                run_command(["apt", "update"])
                print_message("Upgrading packages with apt...", NordColors.FROST_3)
                run_command(["apt", "upgrade", "-y"])

            print_message(
                "Package manager setup completed successfully", NordColors.GREEN, "✓"
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(self, packages: List[str]) -> Tuple[bool, List[str]]:
        """
        Install packages using nala or apt.

        Args:
            packages: List of package names to install

        Returns:
            Tuple of (success, failed_packages)
        """
        try:
            if self.simulate:
                print_message(
                    f"Simulating installation of {len(packages)} packages",
                    NordColors.YELLOW,
                )
                time.sleep(2)
                return True, []

            failed_packages = []
            has_nala = Path("/usr/bin/nala").exists()
            pkg_manager = "nala" if has_nala else "apt"

            # Install in chunks to avoid command line length limits
            chunk_size = 20
            for i in range(0, len(packages), chunk_size):
                chunk = packages[i : i + chunk_size]
                try:
                    print_message(
                        f"Installing packages {i + 1}-{min(i + chunk_size, len(packages))} of {len(packages)}...",
                        NordColors.FROST_3,
                    )
                    run_command([pkg_manager, "install", "-y"] + chunk)
                    self.successful_packages.extend(chunk)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install chunk: {e}")
                    failed_packages.extend(chunk)

                    # Try to install packages individually if chunk fails
                    print_message(
                        "Retrying failed packages individually...",
                        NordColors.YELLOW,
                        "⚠",
                    )
                    for package in chunk:
                        if package not in self.successful_packages:
                            try:
                                print_message(
                                    f"Installing {package}...", NordColors.FROST_3
                                )
                                run_command([pkg_manager, "install", "-y", package])
                                self.successful_packages.append(package)
                                if package in failed_packages:
                                    failed_packages.remove(package)
                            except subprocess.CalledProcessError:
                                logger.error(
                                    f"Failed to install individual package: {package}"
                                )
                                if package not in failed_packages:
                                    failed_packages.append(package)

            if failed_packages:
                return False, failed_packages
            return True, []

        except Exception as e:
            logger.error(f"Package installation failed: {e}")
            return False, packages

    def save_installation_report(self) -> None:
        """Save installation report to a JSON file."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "successful_packages": sorted(self.successful_packages),
            "failed_packages": sorted(self.failed_packages),
            "simulation_mode": self.simulate,
        }

        report_file = (
            LOG_DIR
            / f"installation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Installation report saved to {report_file}")
        print_message(f"Installation report saved to {report_file}", NordColors.FROST_3)


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def show_installation_plan() -> None:
    """Display installation plan with category table."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )

    table.add_column("Category", style=f"bold {NordColors.FROST_2}")
    table.add_column("Tools", justify="right", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Package List", style=f"dim {NordColors.SNOW_STORM_1}")

    total = 0
    for category, tools in SECURITY_TOOLS.items():
        # Format the list of tools nicely
        tool_list = ", ".join(tools[:4])
        if len(tools) > 4:
            tool_list += f" +{len(tools) - 4} more"

        table.add_row(category, str(len(tools)), tool_list)
        total += len(tools)

    # Get unique package count (some packages may appear in multiple categories)
    unique_packages = set()
    for tools in SECURITY_TOOLS.values():
        unique_packages.update(tools)

    console.print(
        Panel(
            table,
            title="[bold]Installation Plan[/]",
            border_style=f"{NordColors.FROST_2}",
        )
    )
    console.print(
        f"Total packages to install: [bold {NordColors.FROST_1}]{len(unique_packages)}[/] (from {total} category entries)"
    )


# ----------------------------------------------------------------
# Main Application Function
# ----------------------------------------------------------------
def main() -> None:
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Security Tools Installer")
    parser.add_argument("--simulate", action="store_true", help="Simulate installation")
    parser.add_argument("--skip-confirm", action="store_true", help="Skip confirmation")
    parser.add_argument(
        "--skip-failed", action="store_true", help="Continue on package failures"
    )
    args = parser.parse_args()

    try:
        if not SystemSetup.check_root():
            console.print(
                Panel(
                    "[bold]This script requires root privileges.[/]\n"
                    "Please run with sudo: [bold cyan]sudo python3 security_installer.py[/]",
                    title="[bold red]Error[/]",
                    border_style=f"{NordColors.RED}",
                )
            )
            sys.exit(1)

        setup = SystemSetup(simulate=args.simulate)

        console.clear()
        console.print(create_header())

        # Display simulation warning if needed
        if args.simulate:
            console.print(
                Panel(
                    "[bold]Running in simulation mode[/]\n"
                    "No actual changes will be made to your system.",
                    title="[bold yellow]Simulation Mode[/]",
                    border_style=f"{NordColors.YELLOW}",
                )
            )

        show_installation_plan()

        if not args.skip_confirm:
            console.print()
            console.print(
                f"[bold {NordColors.FROST_2}]Ready to proceed with installation? Press Enter to continue or Ctrl+C to abort...[/]"
            )
            try:
                input()
            except KeyboardInterrupt:
                console.print("\n[yellow]Operation cancelled[/]")
                sys.exit(0)

        with Progress(
            SpinnerColumn(style=f"{NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[bold {task.percentage:>3.0f}%]"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Setup system
            task = progress.add_task("[cyan]Setting up system...", total=100)

            # Clean up package system first
            progress.update(
                task, description=f"[{NordColors.FROST_2}]Cleaning up package system..."
            )
            if not setup.cleanup_package_system():
                console.print(
                    Panel(
                        "[bold]Failed to clean up package system[/]\n"
                        "Check the logs for more details.",
                        title="[bold red]Error[/]",
                        border_style=f"{NordColors.RED}",
                    )
                )
                sys.exit(1)
            progress.update(task, completed=20)

            # Setup package manager
            progress.update(
                task, description=f"[{NordColors.FROST_2}]Setting up package manager..."
            )
            if not setup.setup_package_manager():
                console.print(
                    Panel(
                        "[bold]Failed to setup package manager[/]\n"
                        "Check the logs for more details.",
                        title="[bold red]Error[/]",
                        border_style=f"{NordColors.RED}",
                    )
                )
                sys.exit(1)
            progress.update(task, completed=40)

            # Install packages
            progress.update(
                task, description=f"[{NordColors.FROST_2}]Installing security tools..."
            )
            all_packages = [pkg for tools in SECURITY_TOOLS.values() for pkg in tools]
            unique_packages = list(set(all_packages))

            success, failed_packages = setup.install_packages(unique_packages)
            if failed_packages:
                setup.failed_packages = failed_packages
                if not args.skip_failed and not args.simulate:
                    console.print(
                        Panel(
                            f"[bold]Failed to install {len(failed_packages)} packages[/]\n"
                            f"Failed packages: {', '.join(failed_packages[:5])}{'...' if len(failed_packages) > 5 else ''}",
                            title="[bold red]Installation Error[/]",
                            border_style=f"{NordColors.RED}",
                        )
                    )
                    console.print(
                        f"Use [bold cyan]--skip-failed[/] to continue despite package failures."
                    )
                    sys.exit(1)
                else:
                    progress.update(
                        task,
                        description=f"[{NordColors.YELLOW}]Some packages failed to install...",
                    )
            else:
                progress.update(
                    task,
                    description=f"[{NordColors.GREEN}]Installation completed successfully!",
                )

            progress.update(task, completed=100)

        # Save installation report
        setup.save_installation_report()

        # Display installation summary
        console.print()
        if args.simulate:
            console.print(
                Panel(
                    "[bold]Simulation completed successfully[/]\n"
                    "No changes were made to your system.",
                    title="[bold green]Simulation Complete[/]",
                    border_style=f"{NordColors.GREEN}",
                )
            )
        elif setup.failed_packages:
            console.print(
                Panel(
                    f"[bold]Installation completed with some failures[/]\n\n"
                    f"[bold]Successfully installed:[/] {len(setup.successful_packages)} packages\n"
                    f"[bold]Failed packages:[/] {len(setup.failed_packages)}\n\n"
                    f"Failed package list: {', '.join(setup.failed_packages[:10])}{'...' if len(setup.failed_packages) > 10 else ''}",
                    title="[bold yellow]Installation Summary[/]",
                    border_style=f"{NordColors.YELLOW}",
                )
            )
        else:
            console.print(
                Panel(
                    f"[bold]Installation completed successfully![/]\n\n"
                    f"[bold]Installed:[/] {len(setup.successful_packages)} security tools\n",
                    title="[bold green]Installation Complete[/]",
                    border_style=f"{NordColors.GREEN}",
                )
            )

        console.print(f"\nDetailed logs available at: [bold]{LOG_FILE}[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/]")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        console.print(
            Panel(
                f"[bold]An unexpected error occurred:[/]\n{str(e)}",
                title="[bold red]Error[/]",
                border_style=f"{NordColors.RED}",
            )
        )
        console.print("\nCheck the logs for more details.")
        sys.exit(1)


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
