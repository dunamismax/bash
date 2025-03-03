Errors to fix:

 ╰────────────────────────────────────────────────────────────────────────────────────────╯                     
                             LiveError: Only one live display may be active at once                                                         
✗ Installation failed: Only one live display may be active at once


#!/usr/bin/env python3
"""
Fully Automated Security Tools Installer
--------------------------------------------------

A zero-interaction system configuration tool that installs and configures security,
analysis, development, and intrusion detection tools on Ubuntu systems.
Runs completely unattended with no user interaction or command line options.

Usage:
  Simply run with sudo: sudo python3 security_installer.py

Version: 1.0.0
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

# No command line argument parsing needed
import platform
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Callable, Set
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
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
VERSION: str = "1.0.0"
APP_NAME: str = "Unattended Security Tools Installer"
APP_SUBTITLE: str = "Automated System Security Configuration"
DEFAULT_LOG_DIR = Path("/var/log/security_setup")
DEFAULT_REPORT_DIR = Path("/var/log/security_setup/reports")
OPERATION_TIMEOUT: int = 600  # 10 minutes for long package installations


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
    },
    "ettercap-graphical": {
        "service": "ettercap.service",
        "config_dirs": ["/etc/ettercap"],
        "force_remove": False,
    },
    "openvas": {
        "service": "openvas.service",
        "config_dirs": ["/etc/openvas"],
        "force_remove": False,
    },
}

# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def setup_logging(log_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Set up logging configuration with RichHandler.

    Args:
        log_dir: Directory for log files
        verbose: Whether to show verbose output

    Returns:
        Logger instance for the application
    """
    # Create log directory if it doesn't exist
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = (
        log_dir / f"security_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    # Set log level based on verbosity
    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True, level=log_level),
            logging.FileHandler(log_file),
        ],
    )
    logger = logging.getLogger("security_setup")
    logger.info(f"Logging initialized. Log file: {log_file}")

    return logger


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
            fig = pyfiglet.Figlet(font=font_name, width=80)
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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 80 + "[/]"
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
    text: str,
    style: str = NordColors.FROST_2,
    prefix: str = "•",
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Print a styled message and optionally log it.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
        logger: Optional logger to also log the message
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    if logger:
        log_text = f"{prefix} {text}"
        if style == NordColors.RED:
            logger.error(log_text)
        elif style == NordColors.YELLOW:
            logger.warning(log_text)
        else:
            logger.info(log_text)


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
def cleanup(logger: Optional[logging.Logger] = None) -> None:
    """
    Perform any cleanup tasks before exit.

    Args:
        logger: Optional logger to log cleanup messages
    """
    message = "Cleaning up resources and temporary files..."
    print_message(message, NordColors.FROST_3)
    if logger:
        logger.info(message)

    # Remove any temporary files that might have been created
    temp_files = glob.glob("/tmp/security_setup_*")
    for file in temp_files:
        try:
            os.remove(file)
            if logger:
                logger.debug(f"Removed temporary file: {file}")
        except OSError:
            if logger:
                logger.debug(f"Failed to remove temporary file: {file}")


def signal_handler(
    sig: int, frame: Any, logger: Optional[logging.Logger] = None
) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
        logger: Optional logger to log signal information
    """
    try:
        sig_name: str = signal.Signals(sig).name
        message = f"Process interrupted by {sig_name} signal"
        print_message(message, NordColors.YELLOW, "⚠")
        if logger:
            logger.warning(message)
    except ValueError:
        message = f"Process interrupted by signal {sig}"
        print_message(message, NordColors.YELLOW, "⚠")
        if logger:
            logger.warning(message)

    cleanup(logger)
    sys.exit(128 + sig)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        logger: Optional logger to log command information

    Returns:
        CompletedProcess instance with command results
    """
    cmd_str = " ".join(cmd)
    try:
        if logger:
            logger.debug(f"Executing command: {cmd_str}")

        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )

        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Command completed: {cmd_str} (return code: {result.returncode})"
            )
            if (
                result.stdout and len(result.stdout) < 1000
            ):  # Don't log very large outputs
                logger.debug(f"Command stdout: {result.stdout.strip()}")

        return result
    except subprocess.CalledProcessError as e:
        message = f"Command failed: {cmd_str}"
        print_message(message, NordColors.RED, "✗")

        if logger:
            logger.error(message)
            if e.stdout:
                logger.error(f"Command stdout: {e.stdout.strip()}")
            if e.stderr:
                logger.error(f"Command stderr: {e.stderr.strip()}")

        if e.stdout and capture_output:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr and capture_output:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")

        raise
    except subprocess.TimeoutExpired:
        message = f"Command timed out after {timeout} seconds: {cmd_str}"
        print_message(message, NordColors.RED, "✗")
        if logger:
            logger.error(message)
        raise
    except Exception as e:
        message = f"Error executing command: {cmd_str} - Error: {e}"
        print_message(message, NordColors.RED, "✗")
        if logger:
            logger.error(message, exc_info=True)
        raise


# ----------------------------------------------------------------
# System Setup Class
# ----------------------------------------------------------------
class SystemSetup:
    """Handles system setup and package management operations."""

    def __init__(
        self,
        simulate: bool = False,
        verbose: bool = False,
        logger: Optional[logging.Logger] = None,
        selected_categories: Optional[List[str]] = None,
    ):
        self.simulate = simulate
        self.verbose = verbose
        self.logger = logger
        self.selected_categories = selected_categories
        self.failed_packages: List[str] = []
        self.successful_packages: List[str] = []
        self.skipped_packages: List[str] = []
        self.start_time = datetime.now()

    @staticmethod
    def check_root() -> bool:
        """Check if script is running with root privileges."""
        return os.geteuid() == 0

    def get_target_packages(self) -> List[str]:
        """
        Get the list of packages to install based on selected categories.

        Returns:
            List of package names to install
        """
        if not self.selected_categories:
            # No specific categories selected, install all packages
            all_packages = [pkg for tools in SECURITY_TOOLS.values() for pkg in tools]
            return list(set(all_packages))  # Remove duplicates

        # Only install packages from selected categories
        target_packages = []
        for category, packages in SECURITY_TOOLS.items():
            if category in self.selected_categories:
                target_packages.extend(packages)

        return list(set(target_packages))  # Remove duplicates

    def log_operation(
        self, message: str, level: str = "info", prefix: str = "•"
    ) -> None:
        """
        Log an operation message with appropriate styling.

        Args:
            message: Message to log
            level: Logging level (info, warning, error)
            prefix: Prefix symbol for the message
        """
        style_map = {
            "info": NordColors.FROST_2,
            "warning": NordColors.YELLOW,
            "error": NordColors.RED,
            "success": NordColors.GREEN,
        }

        style = style_map.get(level, NordColors.FROST_2)
        print_message(message, style, prefix, self.logger)

    def remove_problematic_package(self, package_name: str) -> bool:
        """
        Thoroughly remove a problematic package.

        Args:
            package_name: Name of the package to remove

        Returns:
            True if removal was successful or simulated, False otherwise
        """
        if self.simulate:
            self.log_operation(
                f"Simulating removal of problematic package {package_name}"
            )
            return True

        pkg_info = PROBLEMATIC_PACKAGES.get(package_name)
        if not pkg_info:
            return True

        try:
            # Stop the service if it exists
            if pkg_info.get("service"):
                self.log_operation(f"Stopping service {pkg_info['service']}...")
                subprocess.run(
                    ["systemctl", "stop", pkg_info["service"]],
                    check=False,
                    stderr=subprocess.DEVNULL,
                )

            # Kill any running processes
            self.log_operation(
                f"Terminating any running processes for {package_name}..."
            )
            subprocess.run(
                ["killall", "-9", package_name], check=False, stderr=subprocess.DEVNULL
            )

            # Remove package using different methods
            self.log_operation(f"Removing package {package_name}...")
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
                            self.log_operation(f"Removing directory {directory}...")
                            subprocess.run(["rm", "-rf", directory], check=False)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(
                                f"Failed to remove directory {directory}: {e}"
                            )

            # Final cleanup of package status
            status_file = "/var/lib/dpkg/status"
            temp_file = "/var/lib/dpkg/status.tmp"
            try:
                if pkg_info.get("force_remove"):
                    self.log_operation("Cleaning package status file...")
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
                if self.logger:
                    self.logger.warning(f"Failed to clean package status: {e}")

            self.log_operation(
                f"Package {package_name} removed successfully", "success", "✓"
            )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Failed to remove problematic package {package_name}: {e}"
                )
            return False

    def cleanup_package_system(self) -> bool:
        """
        Clean up package management system and remove invalid files.

        Returns:
            True if cleanup was successful or simulated, False otherwise
        """
        try:
            if self.simulate:
                self.log_operation("Simulating package system cleanup...")
                time.sleep(1)
                return True

            # Clean up invalid .bak files in apt.conf.d
            apt_conf_path = "/etc/apt/apt.conf.d/"
            invalid_files = glob.glob(f"{apt_conf_path}/*.bak.*")

            if invalid_files:
                self.log_operation(
                    f"Found {len(invalid_files)} invalid files to remove"
                )
                for file in invalid_files:
                    try:
                        os.remove(file)
                        if self.logger:
                            self.logger.info(f"Removed invalid file: {file}")
                    except OSError as e:
                        if self.logger:
                            self.logger.error(f"Failed to remove {file}: {e}")
            else:
                self.log_operation("No invalid backup files found")

            # Remove problematic packages first
            for package in PROBLEMATIC_PACKAGES:
                self.log_operation(f"Checking problematic package: {package}")
                if not self.remove_problematic_package(package):
                    if self.logger:
                        self.logger.warning(f"Failed to completely remove {package}")

            # Fix any interrupted dpkg processes
            self.log_operation("Configuring pending package installations...")
            run_command(["dpkg", "--configure", "-a"], logger=self.logger)

            # Check if nala is installed, if not, use apt
            use_nala = Path("/usr/bin/nala").exists()
            pkg_manager = "nala" if use_nala else "apt"

            self.log_operation(f"Cleaning package cache with {pkg_manager}...")
            run_command([pkg_manager, "clean"], logger=self.logger)

            self.log_operation(f"Removing unused packages with {pkg_manager}...")
            run_command([pkg_manager, "autoremove", "-y"], logger=self.logger)

            self.log_operation(
                "Package system cleanup completed successfully", "success", "✓"
            )
            return True

        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Package system cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        """
        Configure and update package manager.

        Returns:
            True if setup was successful or simulated, False otherwise
        """
        try:
            if self.simulate:
                self.log_operation("Simulating package manager setup...")
                time.sleep(1)
                return True

            # First install nala if not present (for better package management)
            has_nala = Path("/usr/bin/nala").exists()

            if not has_nala:
                self.log_operation("Installing nala package manager...")
                run_command(["apt", "update"], logger=self.logger)
                run_command(["apt", "install", "nala", "-y"], logger=self.logger)
                self.log_operation(
                    "Nala package manager installed successfully", "success", "✓"
                )
                has_nala = True

            # Update package lists
            pkg_manager = "nala" if has_nala else "apt"
            self.log_operation(f"Updating package lists with {pkg_manager}...")
            run_command([pkg_manager, "update"], logger=self.logger)

            self.log_operation(f"Upgrading packages with {pkg_manager}...")
            run_command([pkg_manager, "upgrade", "-y"], logger=self.logger)

            self.log_operation(
                "Package manager setup completed successfully", "success", "✓"
            )
            return True

        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(
        self, packages: List[str], skip_failed: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Install packages using nala or apt.

        Args:
            packages: List of package names to install
            skip_failed: Whether to continue even if some packages fail

        Returns:
            Tuple of (success, failed_packages)
        """
        try:
            if self.simulate:
                self.log_operation(
                    f"Simulating installation of {len(packages)} packages", "warning"
                )
                time.sleep(2)
                return True, []

            # Check for presence of nala package manager
            has_nala = Path("/usr/bin/nala").exists()
            pkg_manager = "nala" if has_nala else "apt"

            # Add --assume-yes for apt to avoid interactive prompts
            install_cmd = [pkg_manager, "install", "-y", "--no-install-recommends"]

            # Add options to avoid interactive prompts completely
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"

            failed_packages = []
            # Install in chunks to avoid command line length limits
            chunk_size = 15  # Smaller chunks for better error handling

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
                install_task = progress.add_task(
                    f"[{NordColors.FROST_2}]Installing packages...", total=len(packages)
                )

                for i in range(0, len(packages), chunk_size):
                    chunk = packages[i : i + chunk_size]
                    try:
                        progress.update(
                            install_task,
                            description=f"[{NordColors.FROST_2}]Installing packages {i + 1}-{min(i + chunk_size, len(packages))} of {len(packages)}...",
                        )

                        run_command(install_cmd + chunk, env=env, logger=self.logger)
                        self.successful_packages.extend(chunk)
                        progress.advance(install_task, len(chunk))

                    except subprocess.CalledProcessError as e:
                        # Chunk failed, try individual packages
                        if self.logger:
                            self.logger.error(f"Failed to install chunk: {e}")

                        progress.update(
                            install_task,
                            description=f"[{NordColors.YELLOW}]Retrying failed packages individually...",
                        )

                        for package in chunk:
                            if package not in self.successful_packages:
                                try:
                                    run_command(
                                        install_cmd + [package],
                                        env=env,
                                        logger=self.logger,
                                    )
                                    self.successful_packages.append(package)
                                    progress.advance(install_task, 1)

                                except subprocess.CalledProcessError:
                                    failed_packages.append(package)
                                    if self.logger:
                                        self.logger.error(
                                            f"Failed to install individual package: {package}"
                                        )

                                    # Still advance the progress bar
                                    progress.advance(install_task, 1)

            if failed_packages:
                if skip_failed:
                    self.log_operation(
                        f"Completed with {len(failed_packages)} package failures, continuing as requested...",
                        "warning",
                        "⚠",
                    )
                    self.failed_packages = failed_packages
                    return True, failed_packages
                else:
                    self.log_operation(
                        f"Installation failed for {len(failed_packages)} packages",
                        "error",
                        "✗",
                    )
                    self.failed_packages = failed_packages
                    return False, failed_packages

            self.log_operation(
                f"Successfully installed all {len(self.successful_packages)} packages",
                "success",
                "✓",
            )
            return True, []

        except Exception as e:
            if self.logger:
                self.logger.error(f"Package installation failed: {e}", exc_info=True)
            self.failed_packages = packages
            self.log_operation(f"Installation failed: {e}", "error", "✗")
            return False, packages

    def configure_installed_services(self) -> bool:
        """
        Configure and enable key services that were installed.

        Returns:
            True if configuration was successful, False otherwise
        """
        try:
            if self.simulate:
                self.log_operation("Simulating service configuration...")
                time.sleep(1)
                return True

            # Services to enable and start
            services_to_configure = {
                "ufw": {
                    "enable": True,
                    "commands": [
                        ["ufw", "default", "deny", "incoming"],
                        ["ufw", "default", "allow", "outgoing"],
                        ["ufw", "allow", "ssh"],
                        ["ufw", "--force", "enable"],
                    ],
                },
                "fail2ban": {"enable": True, "commands": []},
                "clamav-freshclam": {
                    "enable": True,
                    "commands": [
                        ["systemctl", "stop", "clamav-freshclam"],
                        ["freshclam"],
                    ],
                },
                "apparmor": {"enable": True, "commands": []},
                "auditd": {"enable": True, "commands": []},
            }

            for service, config in services_to_configure.items():
                # Check if the service package is installed
                if self._check_if_installed(service):
                    self.log_operation(f"Configuring {service}...")

                    # Run any specific commands for this service
                    for cmd in config.get("commands", []):
                        try:
                            run_command(cmd, check=False, logger=self.logger)
                        except Exception as e:
                            self.log_operation(
                                f"Command failed for {service}: {e}", "warning", "⚠"
                            )

                    # Enable and start the service if requested
                    if config.get("enable", False):
                        try:
                            self.log_operation(f"Enabling and starting {service}...")
                            run_command(
                                ["systemctl", "enable", service],
                                check=False,
                                logger=self.logger,
                            )
                            run_command(
                                ["systemctl", "restart", service],
                                check=False,
                                logger=self.logger,
                            )
                        except Exception as e:
                            self.log_operation(
                                f"Failed to enable/start {service}: {e}", "warning", "⚠"
                            )
                else:
                    if self.logger:
                        self.logger.debug(
                            f"Service {service} not installed, skipping configuration"
                        )

            self.log_operation("Service configuration completed", "success", "✓")
            return True

        except Exception as e:
            self.log_operation(f"Service configuration failed: {e}", "error", "✗")
            if self.logger:
                self.logger.error(f"Service configuration failed: {e}", exc_info=True)
            return False

    def _check_if_installed(self, package: str) -> bool:
        """
        Check if a package is installed.

        Args:
            package: Package name to check

        Returns:
            True if the package is installed, False otherwise
        """
        try:
            result = run_command(
                ["dpkg", "-l", package],
                check=False,
                capture_output=True,
                logger=self.logger,
            )
            return "ii" in result.stdout and package in result.stdout
        except Exception:
            return False

    def save_installation_report(self, report_dir: Path) -> str:
        """
        Save installation report to a JSON file.

        Args:
            report_dir: Directory to save report

        Returns:
            Path to the saved report file
        """
        # Create report directory if it doesn't exist
        report_dir.mkdir(exist_ok=True, parents=True)

        # Calculate elapsed time
        elapsed_time = (datetime.now() - self.start_time).total_seconds()
        elapsed_str = f"{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s"

        # Get system information
        system_info = {
            "hostname": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }

        # Create the report
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_info": system_info,
            "duration": elapsed_str,
            "successful_packages": sorted(self.successful_packages),
            "failed_packages": sorted(self.failed_packages),
            "skipped_packages": sorted(self.skipped_packages),
            "simulation_mode": self.simulate,
            "selected_categories": self.selected_categories,
            "total_packages_attempted": len(self.successful_packages)
            + len(self.failed_packages)
            + len(self.skipped_packages),
        }

        # Save the report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"installation_report_{timestamp}.json"
        report_txt = report_dir / f"installation_report_{timestamp}.txt"

        # Save JSON format
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Save human-readable format
        with open(report_txt, "w") as f:
            f.write(f"Security Tools Installation Report\n")
            f.write(f"================================\n\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {elapsed_str}\n")
            f.write(f"Simulation Mode: {'Yes' if self.simulate else 'No'}\n\n")

            f.write(f"System Information:\n")
            for key, value in system_info.items():
                f.write(f"  {key}: {value}\n")

            f.write(f"\nInstallation Summary:\n")
            f.write(
                f"  Successfully installed: {len(self.successful_packages)} packages\n"
            )
            f.write(f"  Failed to install: {len(self.failed_packages)} packages\n")
            f.write(f"  Skipped: {len(self.skipped_packages)} packages\n")
            f.write(
                f"  Total packages attempted: {report['total_packages_attempted']}\n\n"
            )

            if self.selected_categories:
                f.write(f"Selected categories:\n")
                for category in self.selected_categories:
                    f.write(f"  - {category}\n")
                f.write("\n")

            if self.failed_packages:
                f.write(f"Failed packages:\n")
                for package in sorted(self.failed_packages):
                    f.write(f"  - {package}\n")
                f.write("\n")

        if self.logger:
            self.logger.info(
                f"Installation report saved to {report_file} and {report_txt}"
            )

        self.log_operation(f"Installation report saved to {report_file}", "info")

        return str(report_file)


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def show_installation_plan(selected_categories: Optional[List[str]] = None) -> None:
    """
    Display installation plan with all categories in a table.
    Since the script is fully automated, this is just informational.

    Args:
        selected_categories: List of categories to install, or None for all
    """
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
    categories_to_show = SECURITY_TOOLS.items()

    # If specific categories are selected, only show those
    if selected_categories:
        categories_to_show = {
            category: tools
            for category, tools in SECURITY_TOOLS.items()
            if category in selected_categories
        }.items()

    for category, tools in categories_to_show:
        # Format the list of tools nicely
        tool_list = ", ".join(tools[:4])
        if len(tools) > 4:
            tool_list += f" +{len(tools) - 4} more"

        # Use a checkmark for selected categories
        prefix = (
            "✓ " if (not selected_categories or category in selected_categories) else ""
        )

        table.add_row(f"{prefix}{category}", str(len(tools)), tool_list)
        total += len(tools)

    # Get unique package count (some packages may appear in multiple categories)
    unique_packages = set()
    for category, tools in categories_to_show:
        unique_packages.update(tools)

    console.print(
        Panel(
            table,
            title="[bold]Installation Plan[/]",
            border_style=f"{NordColors.FROST_2}",
        )
    )

    if selected_categories:
        console.print(
            f"Installing [bold {NordColors.FROST_1}]{len(unique_packages)}[/] unique packages "
            f"from [bold {NordColors.FROST_1}]{len(selected_categories)}[/] selected categories"
        )
    else:
        console.print(
            f"Installing [bold {NordColors.FROST_1}]{len(unique_packages)}[/] unique packages "
            f"from all {len(SECURITY_TOOLS)} categories"
        )


# ----------------------------------------------------------------
# Main Application Function
# ----------------------------------------------------------------
def main() -> None:
    """Main execution function with fully automated operation."""
    # Set default configuration
    simulate = False  # Actually perform installation
    verbose = False  # Normal output level
    skip_failed = True  # Continue despite package failures
    selected_categories = None  # Install all categories
    report_dir = DEFAULT_REPORT_DIR
    log_dir = DEFAULT_LOG_DIR
    show_header = True  # Display the ASCII art header

    # Setup logging
    logger = setup_logging(log_dir, verbose)

    # Register signal handlers with logger
    def handle_signal(sig, frame):
        signal_handler(sig, frame, logger)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Register cleanup with logger
    def handle_cleanup():
        cleanup(logger)

    atexit.register(handle_cleanup)

    try:
        # Check for root privileges (required for package management)
        if not SystemSetup.check_root():
            display_panel(
                "[bold]This script requires root privileges.[/]\n"
                "Please run with sudo: [bold cyan]sudo python3 security_installer.py[/]",
                style=NordColors.RED,
                title="Error",
            )
            sys.exit(1)

        # Clear console and show header
        if show_header:
            console.clear()
            console.print(create_header())

        # Initialize system setup
        setup = SystemSetup(
            simulate=simulate,
            verbose=verbose,
            logger=logger,
            selected_categories=selected_categories,
        )

        # Display installation plan
        show_installation_plan(selected_categories)
        console.print()

        # Start main installation process
        with Progress(
            SpinnerColumn(style=f"{NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Create main task
            main_task = progress.add_task("[cyan]Setting up system...", total=100)

            # Step 1: Clean up package system
            progress.update(
                main_task,
                description=f"[{NordColors.FROST_2}]Cleaning up package system...",
                completed=0,
            )
            if not setup.cleanup_package_system():
                if not skip_failed:
                    display_panel(
                        "[bold]Failed to clean up package system[/]\n"
                        "Check the logs for more details.",
                        style=NordColors.RED,
                        title="Error",
                    )
                    sys.exit(1)
                else:
                    print_message(
                        "Package system cleanup failed, continuing with installation anyway...",
                        NordColors.YELLOW,
                        "⚠",
                        logger,
                    )
            progress.update(main_task, completed=20)

            # Step 2: Setup package manager
            progress.update(
                main_task,
                description=f"[{NordColors.FROST_2}]Setting up package manager...",
                completed=20,
            )
            if not setup.setup_package_manager():
                if not skip_failed:
                    display_panel(
                        "[bold]Failed to setup package manager[/]\n"
                        "Check the logs for more details.",
                        style=NordColors.RED,
                        title="Error",
                    )
                    sys.exit(1)
                else:
                    print_message(
                        "Package manager setup failed, continuing with installation anyway...",
                        NordColors.YELLOW,
                        "⚠",
                        logger,
                    )
            progress.update(main_task, completed=40)

            # Step 3: Install selected packages
            progress.update(
                main_task,
                description=f"[{NordColors.FROST_2}]Installing security tools...",
                completed=40,
            )

            # Get list of packages to install
            target_packages = setup.get_target_packages()

            success, failed_packages = setup.install_packages(
                target_packages, skip_failed=skip_failed
            )

            if failed_packages and not skip_failed and not simulate:
                display_panel(
                    f"[bold]Failed to install {len(failed_packages)} packages[/]\n"
                    f"Failed packages: {', '.join(failed_packages[:10])}{'...' if len(failed_packages) > 10 else ''}",
                    style=NordColors.RED,
                    title="Installation Error",
                )
                sys.exit(1)
            elif failed_packages:
                progress.update(
                    main_task,
                    description=f"[{NordColors.YELLOW}]Some packages failed to install...",
                    completed=80,
                )
            else:
                progress.update(
                    main_task,
                    description=f"[{NordColors.GREEN}]Package installation completed successfully!",
                    completed=80,
                )

            # Step 4: Configure installed services
            progress.update(
                main_task,
                description=f"[{NordColors.FROST_2}]Configuring services...",
                completed=80,
            )

            setup.configure_installed_services()

            # Complete the progress
            progress.update(
                main_task,
                description=f"[{NordColors.GREEN}]Installation completed!",
                completed=100,
            )

        # Save installation report
        report_file = setup.save_installation_report(report_dir)

        # Display installation summary
        console.print()
        if setup.failed_packages:
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

        # Log file location
        log_files = list(log_dir.glob("security_setup_*.log"))
        latest_log = (
            max(log_files, key=lambda p: p.stat().st_mtime) if log_files else None
        )

        if latest_log:
            console.print(f"\nDetailed logs available at: [bold]{latest_log}[/]")
            console.print(f"Installation report saved to: [bold]{report_file}[/]")

        # Final summary message
        finish_time = datetime.now()
        elapsed = (finish_time - setup.start_time).total_seconds()
        console.print(
            f"\nTotal installation time: [bold]{int(elapsed // 60)} minutes, {int(elapsed % 60)} seconds[/]"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/]")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        display_panel(
            f"[bold]An unexpected error occurred:[/]\n{str(e)}",
            style=NordColors.RED,
            title="Error",
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
