#!/usr/bin/env python3
"""
Enhanced Ubuntu Security Tools Configurator
--------------------------------------------------

A comprehensive system configuration tool that installs and configures security,
analysis, development, and intrusion detection tools on Ubuntu systems.
Features improved progress tracking, error handling, and non-interactive installations.

This script requires root privileges to install packages.
Run with: sudo python3 ubuntu_security_config.py [--simulate] [--skip-confirm]

Version: 2.0.0
"""

import os
import sys
import subprocess
import time
import signal
import atexit
import logging
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass
import argparse
import json

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
        TaskProgressColumn,
    )
    from rich.style import Style
    from rich.table import Table
    from rich.traceback import install as install_rich_traceback
    from rich.logging import RichHandler
    from rich.live import Live
    from rich.layout import Layout
except ImportError:
    print("Required packages missing. Installing rich and pyfiglet...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"])
    print("Please run the script again.")
    sys.exit(1)

# Install rich traceback handler
install_rich_traceback(show_locals=True)

# Configure logging with Rich handler
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("security_setup")

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION = "2.0.0"
APP_NAME = "Ubuntu Security Setup"
APP_SUBTITLE = "Enhanced System Configuration Tool"


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
    dependencies: List[str] = None
    post_install: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.post_install is None:
            self.post_install = []


# Extended tool list with dependencies and post-install commands
SECURITY_TOOLS = [
    # Network Analysis
    SecurityTool(
        "Wireshark",
        "wireshark",
        "Network Analysis",
        "Network protocol analyzer",
        dependencies=["wireshark-common"],
        post_install=[
            "DEBIAN_FRONTEND=noninteractive dpkg-reconfigure wireshark-common"
        ],
    ),
    SecurityTool(
        "Nmap", "nmap", "Network Analysis", "Network discovery and security scanner"
    ),
    SecurityTool(
        "Tcpdump", "tcpdump", "Network Analysis", "Command-line packet analyzer"
    ),
    SecurityTool(
        "Ettercap",
        "ettercap-graphical",
        "Network Analysis",
        "Network protocol analyzer with GUI",
    ),
    # Vulnerability Assessment
    SecurityTool(
        "OpenVAS",
        "openvas",
        "Vulnerability Assessment",
        "Vulnerability scanner",
        dependencies=["gvm"],
    ),
    SecurityTool("Nikto", "nikto", "Vulnerability Assessment", "Web server scanner"),
    SecurityTool(
        "OWASP ZAP",
        "zaproxy",
        "Vulnerability Assessment",
        "Web application security scanner",
    ),
    SecurityTool(
        "Nuclei", "nuclei", "Vulnerability Assessment", "Fast vulnerability scanner"
    ),
    # Forensics
    SecurityTool("Autopsy", "autopsy", "Forensics", "Digital forensics platform"),
    SecurityTool("Sleuth Kit", "sleuthkit", "Forensics", "Digital forensics tools"),
    SecurityTool("TestDisk", "testdisk", "Forensics", "Data recovery software"),
    SecurityTool(
        "Volatility3", "python3-volatility3", "Forensics", "Memory forensics framework"
    ),
    # System Security
    SecurityTool("Lynis", "lynis", "System Security", "Security auditing tool"),
    SecurityTool(
        "Fail2ban",
        "fail2ban",
        "System Security",
        "Intrusion prevention software",
        post_install=["systemctl enable fail2ban", "systemctl start fail2ban"],
    ),
    SecurityTool(
        "RKHunter",
        "rkhunter",
        "System Security",
        "Rootkit detection",
        post_install=["rkhunter --update", "rkhunter --propupd"],
    ),
    SecurityTool(
        "CrowdSec",
        "crowdsec",
        "System Security",
        "Modern security engine",
        post_install=["systemctl enable crowdsec", "systemctl start crowdsec"],
    ),
    # Password Tools
    SecurityTool("John the Ripper", "john", "Password Tools", "Password cracker"),
    SecurityTool("Hashcat", "hashcat", "Password Tools", "Advanced password recovery"),
    SecurityTool("Hydra", "hydra", "Password Tools", "Network login cracker"),
    # Wireless Tools
    SecurityTool("Aircrack-ng", "aircrack-ng", "Wireless", "Wireless network security"),
    SecurityTool("Kismet", "kismet", "Wireless", "Wireless network detector"),
    SecurityTool("Wifite", "wifite", "Wireless", "Automated wireless auditor"),
    # Web Security
    SecurityTool("SQLMap", "sqlmap", "Web Security", "SQL injection detection"),
    SecurityTool("Dirb", "dirb", "Web Security", "Web content scanner"),
    SecurityTool("Gobuster", "gobuster", "Web Security", "Directory/file enumeration"),
    SecurityTool(
        "Burpsuite Community", "burpsuite", "Web Security", "Web security testing"
    ),
    # Development Tools
    SecurityTool("Git", "git", "Development", "Version control system"),
    SecurityTool(
        "Python3",
        "python3",
        "Development",
        "Python programming language",
        dependencies=["python3-pip", "python3-venv"],
    ),
    SecurityTool(
        "Build Essential", "build-essential", "Development", "C/C++ compiler and tools"
    ),
    SecurityTool(
        "Docker",
        "docker.io",
        "Development",
        "Container platform",
        post_install=["systemctl enable docker", "systemctl start docker"],
    ),
    # Intrusion Detection / Antivirus
    SecurityTool(
        "ClamAV",
        "clamav",
        "Antivirus",
        "Antivirus scanning tool",
        dependencies=["clamav-daemon"],
        post_install=["systemctl enable clamav-daemon", "freshclam"],
    ),
    SecurityTool(
        "UFW",
        "ufw",
        "System Security",
        "Firewall configuration utility",
        post_install=["ufw enable"],
    ),
    SecurityTool(
        "OSSEC",
        "ossec-hids",
        "Intrusion Detection",
        "Host-based intrusion detection system",
    ),
    SecurityTool(
        "Snort",
        "snort",
        "Intrusion Detection",
        "Network intrusion detection",
        post_install=["systemctl enable snort"],
    ),
    SecurityTool(
        "Suricata",
        "suricata",
        "Intrusion Detection",
        "High performance network IDS/IPS",
        post_install=["systemctl enable suricata"],
    ),
    # Monitoring and Analysis
    SecurityTool("Nagios", "nagios4", "Monitoring", "System and network monitoring"),
    SecurityTool(
        "Prometheus",
        "prometheus",
        "Monitoring",
        "Monitoring system & time series database",
    ),
]


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def create_fancy_header() -> Panel:
    """Create an enhanced styled header panel using pyfiglet."""
    styles = ["slant", "banner3-D", "isometric1", "block"]
    try:
        # Try different fonts until one works
        for style in styles:
            try:
                fig = pyfiglet.Figlet(font=style)
                ascii_art = fig.renderText(APP_NAME)
                break
            except Exception:
                continue
    except Exception:
        ascii_art = APP_NAME

    # Create a multi-line styled header
    header_text = Text()
    header_text.append(ascii_art, style=f"bold {NordColors.FROST_2}")
    header_text.append(
        f"\nVersion {VERSION}", style=f"italic {NordColors.SNOW_STORM_2}"
    )
    header_text.append(f"\n{APP_SUBTITLE}", style=f"bold {NordColors.FROST_3}")

    return Panel(
        header_text,
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]Security Setup[/]",
        subtitle=f"[italic {NordColors.SNOW_STORM_1}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
    )


def run_command(cmd: List[str], simulate: bool = False) -> bool:
    """Execute a command with proper error handling."""
    if simulate:
        logger.info(f"Simulating command: {' '.join(cmd)}")
        return True

    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        result = subprocess.run(
            cmd,
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.error(f"Error output: {e.stderr}")
        return False


def install_tool(
    tool: SecurityTool, progress: Progress, task_id: int, simulate: bool = False
) -> bool:
    """Install a single security tool with enhanced error handling and progress tracking."""
    try:
        # Install dependencies first
        for dep in tool.dependencies:
            progress.update(task_id, description=f"Installing dependency: {dep}")
            if not run_command(["apt-get", "install", "-y", dep], simulate):
                return False

        # Install main package
        progress.update(task_id, description=f"Installing {tool.name}")
        if not run_command(["apt-get", "install", "-y", tool.package], simulate):
            return False

        # Run post-install commands
        for cmd in tool.post_install:
            progress.update(task_id, description=f"Configuring {tool.name}")
            if not run_command(cmd.split(), simulate):
                logger.warning(f"Post-install command failed for {tool.name}: {cmd}")

        return True
    except Exception as e:
        logger.error(f"Error installing {tool.name}: {str(e)}")
        return False


def install_all_tools(tools: List[SecurityTool], simulate: bool = False) -> None:
    """Install all security tools with enhanced progress tracking."""
    total_steps = sum(
        len(tool.dependencies) + 1 + len(tool.post_install) for tool in tools
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        overall_task = progress.add_task(
            f"[{NordColors.FROST_2}]Installing security tools...", total=total_steps
        )

        for tool in tools:
            task_id = progress.add_task(f"Installing {tool.name}...", total=100)
            tool.status = install_tool(tool, progress, task_id, simulate)
            progress.update(task_id, completed=100)
            progress.advance(overall_task)


def create_summary_report(tools: List[SecurityTool]) -> None:
    """Generate and save a detailed installation report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "version": VERSION,
        "tools": [
            {
                "name": tool.name,
                "category": tool.category,
                "status": tool.status,
                "description": tool.description,
            }
            for tool in tools
        ],
    }

    with open("security_tools_report.json", "w") as f:
        json.dump(report, f, indent=2)


# ----------------------------------------------------------------
# Main Function
# ----------------------------------------------------------------
def main() -> None:
    """Enhanced main function with better error handling and user interface."""
    parser = argparse.ArgumentParser(
        description="Enhanced Ubuntu Security Tools Configurator"
    )
    parser.add_argument(
        "--simulate", action="store_true", help="Simulate installations"
    )
    parser.add_argument(
        "--skip-confirm", action="store_true", help="Skip confirmation prompts"
    )
    args = parser.parse_args()

    if not os.geteuid() == 0:
        console.print(
            Panel(
                Text.from_markup(
                    f"[bold {NordColors.RED}]Error: Root privileges required[/]\n"
                    f"[{NordColors.SNOW_STORM_1}]Please run with sudo: sudo python3 {sys.argv[0]}[/]"
                ),
                border_style=Style(color=NordColors.RED),
                title="Error",
                padding=(1, 2),
            )
        )
        sys.exit(1)

    # Initialize layout
    layout = Layout()
    layout.split_column(
        Layout(name="header"), Layout(name="body"), Layout(name="footer")
    )

    # Display header
    console.clear()
    header = create_fancy_header()
    console.print(header)

    # Check internet connectivity with progress spinner
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        check_task = progress.add_task(
            f"[{NordColors.FROST_2}]Checking internet connectivity...", total=1
        )

        import socket

        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            progress.update(check_task, completed=1)
            logger.info("Internet connectivity confirmed")
        except socket.error:
            progress.update(check_task, completed=1)
            console.print(
                Panel(
                    Text.from_markup(
                        f"[bold {NordColors.RED}]No internet connectivity detected[/]\n"
                        f"[{NordColors.SNOW_STORM_1}]Please check your network connection and try again[/]"
                    ),
                    border_style=Style(color=NordColors.RED),
                    title="Error",
                    padding=(1, 2),
                )
            )
            sys.exit(1)

    # Update system packages
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        update_task = progress.add_task(
            f"[{NordColors.FROST_2}]Updating system packages...", total=100
        )

        if args.simulate:
            logger.info("Simulating system update...")
            time.sleep(2)
            progress.update(update_task, completed=100)
        else:
            try:
                # Update package lists
                progress.update(
                    update_task,
                    description="[bold]Updating package lists...[/]",
                    completed=25,
                )
                subprocess.run(["apt-get", "update"], check=True, capture_output=True)

                # Upgrade packages
                progress.update(
                    update_task,
                    description="[bold]Upgrading packages...[/]",
                    completed=75,
                )
                subprocess.run(
                    ["apt-get", "upgrade", "-y"], check=True, capture_output=True
                )

                progress.update(update_task, completed=100)
                logger.info("System update completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"System update failed: {str(e)}")
                sys.exit(1)

    # Display installation plan
    categories = {}
    for tool in SECURITY_TOOLS:
        if tool.category not in categories:
            categories[tool.category] = []
        categories[tool.category].append(tool)

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Installation Plan[/]",
    )
    table.add_column("Category", style=f"bold {NordColors.FROST_4}")
    table.add_column("Tools", style=f"{NordColors.SNOW_STORM_1}")

    for category, tools in categories.items():
        tool_names = ", ".join([tool.name for tool in tools])
        table.add_row(category, tool_names)

    console.print(
        Panel(table, title="Tools to Install", border_style=NordColors.FROST_1)
    )

    # Confirm installation if not skipped
    if not args.skip_confirm:
        console.print(
            f"\n[{NordColors.SNOW_STORM_1}]Press Enter to begin installation or Ctrl+C to abort...[/]"
        )
        input()

    # Install tools
    install_all_tools(SECURITY_TOOLS, args.simulate)

    # Generate and display summary
    create_summary_report(SECURITY_TOOLS)

    # Display final summary table
    summary_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Installation Results[/]",
    )
    summary_table.add_column("Category", style=f"bold {NordColors.FROST_4}")
    summary_table.add_column("Tool", style=f"{NordColors.SNOW_STORM_1}")
    summary_table.add_column("Status", justify="center")

    successful_installs = 0
    failed_installs = 0

    for tool in SECURITY_TOOLS:
        status = (
            f"[bold {NordColors.GREEN}]✓ Success[/]"
            if tool.status
            else f"[bold {NordColors.RED}]✗ Failed[/]"
        )
        summary_table.add_row(tool.category, tool.name, status)
        if tool.status:
            successful_installs += 1
        else:
            failed_installs += 1

    console.print(
        Panel(summary_table, title="Final Summary", border_style=NordColors.FROST_1)
    )

    # Display completion message
    completion_text = Text()
    completion_text.append(
        "\n✨ Installation Complete! ✨\n\n", style=f"bold {NordColors.GREEN}"
    )
    completion_text.append(
        f"Successfully installed: {successful_installs} tools\n",
        style=NordColors.FROST_2,
    )
    if failed_installs > 0:
        completion_text.append(
            f"Failed installations: {failed_installs} tools\n", style=NordColors.RED
        )
    completion_text.append(
        f"\nDetailed report saved to: security_tools_report.json\n",
        style=NordColors.SNOW_STORM_1,
    )
    completion_text.append(
        "\nNote: Some tools may require additional configuration.\n",
        style=f"italic {NordColors.FROST_3}",
    )
    completion_text.append(
        "Please check the documentation for each tool for optimal setup.\n",
        style=f"italic {NordColors.FROST_3}",
    )

    console.print(
        Panel(
            completion_text,
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
        logger.error(f"An unexpected error occurred: {str(e)}")
        console.print_exception()
        sys.exit(1)
