#!/usr/bin/env python3
"""
Ubuntu Security Tools Configurator
--------------------------------------------------

A streamlined system configuration tool that installs and sets up security,
analysis, development, and intrusion detection tools on Ubuntu systems.
Features progress tracking, error handling, connectivity checks, and detailed status reporting.

This script requires root privileges to install packages.
Run with: sudo python3 ubuntu_security_config.py [--simulate]

Version: 1.1.0
"""

import os
import sys
import subprocess
import time
import signal
import atexit
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
import argparse

try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.style import Style
    from rich.table import Table
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Required packages missing. Installing rich and pyfiglet...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"])
    print("Please run the script again.")
    sys.exit(1)

# Install rich traceback handler for improved error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION = "1.1.0"
APP_NAME = "Ubuntu Security Setup"
APP_SUBTITLE = "System Configuration Tool"


# ----------------------------------------------------------------
# Nord Theme Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"


# Create console instance
console = Console()


# ----------------------------------------------------------------
# Tool Categories and Packages
# ----------------------------------------------------------------
@dataclass
class SecurityTool:
    """Represents a security tool to be installed."""

    name: str
    package: str
    category: str
    description: str
    status: Optional[bool] = None


SECURITY_TOOLS = [
    # Network Analysis
    SecurityTool(
        "Wireshark", "wireshark", "Network Analysis", "Network protocol analyzer"
    ),
    SecurityTool(
        "Nmap", "nmap", "Network Analysis", "Network discovery and security scanner"
    ),
    SecurityTool(
        "Tcpdump", "tcpdump", "Network Analysis", "Command-line packet analyzer"
    ),
    # Vulnerability Assessment
    SecurityTool(
        "OpenVAS", "openvas", "Vulnerability Assessment", "Vulnerability scanner"
    ),
    SecurityTool("Nikto", "nikto", "Vulnerability Assessment", "Web server scanner"),
    SecurityTool(
        "OWASP ZAP",
        "zaproxy",
        "Vulnerability Assessment",
        "Web application security scanner",
    ),
    # Forensics
    SecurityTool("Autopsy", "autopsy", "Forensics", "Digital forensics platform"),
    SecurityTool("Sleuth Kit", "sleuthkit", "Forensics", "Digital forensics tools"),
    SecurityTool("TestDisk", "testdisk", "Forensics", "Data recovery software"),
    # System Security
    SecurityTool("Lynis", "lynis", "System Security", "Security auditing tool"),
    SecurityTool(
        "Fail2ban", "fail2ban", "System Security", "Intrusion prevention software"
    ),
    SecurityTool("RKHunter", "rkhunter", "System Security", "Rootkit detection"),
    # Password Tools
    SecurityTool("John the Ripper", "john", "Password Tools", "Password cracker"),
    SecurityTool("Hashcat", "hashcat", "Password Tools", "Advanced password recovery"),
    # Wireless Tools
    SecurityTool("Aircrack-ng", "aircrack-ng", "Wireless", "Wireless network security"),
    SecurityTool("Kismet", "kismet", "Wireless", "Wireless network detector"),
    # Web Security
    SecurityTool("SQLMap", "sqlmap", "Web Security", "SQL injection detection"),
    SecurityTool("Dirb", "dirb", "Web Security", "Web content scanner"),
    SecurityTool("Gobuster", "gobuster", "Web Security", "Directory/file enumeration"),
    # Development Tools
    SecurityTool("Git", "git", "Development", "Version control system"),
    SecurityTool("Python3", "python3", "Development", "Python programming language"),
    SecurityTool(
        "Build Essential", "build-essential", "Development", "C/C++ compiler and tools"
    ),
    # Intrusion Detection / Antivirus
    SecurityTool("ClamAV", "clamav", "Antivirus", "Antivirus scanning tool"),
    SecurityTool("UFW", "ufw", "System Security", "Firewall configuration utility"),
    SecurityTool(
        "OSSEC",
        "ossec-hids",
        "Intrusion Detection",
        "Host-based intrusion detection system",
    ),
    SecurityTool(
        "Snort", "snort", "Intrusion Detection", "Network intrusion detection"
    ),
    SecurityTool(
        "Suricata",
        "suricata",
        "Intrusion Detection",
        "High performance network IDS/IPS",
    ),
]


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def log_message(text: str, style: str = NordColors.FROST_2, prefix: str = "•") -> None:
    """Log a message with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[{style}]{prefix} {timestamp} - {text}[/{style}]")


def check_root() -> bool:
    """Check if script is running with root privileges."""
    return os.geteuid() == 0


def check_internet_connectivity(
    host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0
) -> bool:
    """
    Check for internet connectivity by attempting to open a socket.
    Default uses Google DNS (8.8.8.8).
    """
    import socket

    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False


def create_header() -> Panel:
    """Create a styled header panel using pyfiglet."""
    try:
        fig = pyfiglet.Figlet(font="slant")
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = APP_NAME
    styled_text = f"[bold {NordColors.FROST_2}]{ascii_art}[/]"
    header = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header


# ----------------------------------------------------------------
# System Update Functions
# ----------------------------------------------------------------
def update_system(simulate: bool = False) -> bool:
    """Update system packages and upgrade installed packages."""
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            update_task = progress.add_task(
                f"[{NordColors.FROST_2}]Updating package lists...", total=100
            )
            if simulate:
                log_message("Simulating package list update...", NordColors.YELLOW)
                time.sleep(1)
            else:
                subprocess.run(
                    ["apt-get", "update"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            progress.update(update_task, completed=50)
            if simulate:
                log_message("Simulating package upgrade...", NordColors.YELLOW)
                time.sleep(1)
            else:
                subprocess.run(
                    ["apt-get", "upgrade", "-y"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            progress.update(update_task, completed=100)
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Error updating system: {str(e)}", NordColors.RED, "✗")
        return False


# ----------------------------------------------------------------
# Tool Installation Functions
# ----------------------------------------------------------------
def install_tool(tool: SecurityTool, simulate: bool = False) -> bool:
    """Install a single security tool."""
    try:
        cmd = ["apt-get", "install", "-y", tool.package]
        if simulate:
            log_message(f"Simulated install: {' '.join(cmd)}", NordColors.YELLOW)
            time.sleep(0.5)
            return True
        else:
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
    except subprocess.CalledProcessError:
        return False


def install_all_tools(tools: List[SecurityTool], simulate: bool = False) -> None:
    """Install all security tools with progress tracking."""
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task(
            f"[{NordColors.FROST_2}]Installing security tools...", total=len(tools)
        )
        for tool in tools:
            progress.update(
                overall_task,
                description=f"[{NordColors.FROST_2}]Installing {tool.name}...",
            )
            tool.status = install_tool(tool, simulate)
            progress.advance(overall_task)


def display_installation_summary(tools: List[SecurityTool]) -> None:
    """Display a summary table of installed tools."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Installation Summary[/]",
    )
    table.add_column("Category", style=f"bold {NordColors.FROST_4}")
    table.add_column("Tool", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center")
    for tool in tools:
        status = (
            f"[bold {NordColors.GREEN}]✓ Installed[/]"
            if tool.status
            else f"[bold {NordColors.RED}]✗ Failed[/]"
        )
        table.add_row(tool.category, tool.name, status)
    console.print(Panel(table, title="Summary", border_style=NordColors.FROST_1))


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Cleanup function to run on exit."""
    log_message("Cleaning up before exit...", NordColors.FROST_3)


def signal_handler(sig, frame) -> None:
    """Gracefully handle termination signals."""
    log_message(
        f"Process interrupted (signal {sig}). Exiting...", NordColors.YELLOW, "⚠"
    )
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Function
# ----------------------------------------------------------------
def main() -> None:
    """Main function to run the configuration process."""
    parser = argparse.ArgumentParser(description="Ubuntu Security Tools Configurator")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate installations without executing commands",
    )
    args = parser.parse_args()

    if not check_root():
        console.print(
            f"[bold {NordColors.RED}]Error: This script requires root privileges.[/]\n"
            f"[{NordColors.SNOW_STORM_1}]Please run with sudo: sudo python3 {sys.argv[0]}[/]"
        )
        sys.exit(1)

    console.clear()
    console.print(create_header())

    # Check internet connectivity before update
    if not check_internet_connectivity():
        log_message(
            "No internet connectivity detected. Please check your network and try again.",
            NordColors.RED,
            "✗",
        )
        sys.exit(1)

    log_message("Starting system update...", NordColors.FROST_2)
    if not update_system(args.simulate):
        log_message("Failed to update system. Exiting.", NordColors.RED, "✗")
        sys.exit(1)
    log_message("System update completed successfully.", NordColors.GREEN, "✓")

    # Confirm installation
    console.print()
    console.print(
        Panel(
            Text(
                "Proceed with installing security tools?",
                style=f"bold {NordColors.FROST_2}",
            ),
            border_style=NordColors.FROST_1,
        )
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]Press Enter to continue or Ctrl+C to abort...[/]"
    )
    input()

    log_message("Starting installation of security tools...", NordColors.FROST_2)
    install_all_tools(SECURITY_TOOLS, args.simulate)

    console.print("\n")
    display_installation_summary(SECURITY_TOOLS)

    console.print(
        Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]Installation Complete![/]\n\n"
                f"[{NordColors.SNOW_STORM_1}]All selected security tools have been installed "
                f"{'(simulation mode)' if args.simulate else ''}.[/]\n"
                f"[{NordColors.SNOW_STORM_1}]You may need to log out and back in for some changes to take effect.[/]"
            ),
            border_style=Style(color=NordColors.FROST_1),
            padding=(1, 2),
            title="Setup Complete",
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"\n[bold {NordColors.YELLOW}]Operation cancelled by user.[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold {NordColors.RED}]An error occurred: {str(e)}[/]")
        console.print_exception()
        sys.exit(1)
