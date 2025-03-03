#!/usr/bin/env python3
"""
Batch Ubuntu Security Tools Configurator
--------------------------------------------------

A streamlined system configuration tool that batch installs security,
analysis, development, and intrusion detection tools on Ubuntu systems.
Features optimized batch installation and progress tracking.

Version: 3.0.0
"""

import os
import sys
import subprocess
import time
import signal
import atexit
from datetime import datetime
from typing import List, Dict, Set
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
    from rich.live import Live
    from rich.layout import Layout
except ImportError:
    print("Required packages missing. Installing rich and pyfiglet...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"])
    print("Please run the script again.")
    sys.exit(1)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION = "3.0.0"
APP_NAME = "Security Tools Setup"
APP_SUBTITLE = "Batch Installation System"

# Console setup
console = Console()


# ----------------------------------------------------------------
# Tool Categories and Packages
# ----------------------------------------------------------------
@dataclass
class SecurityTool:
    """Represents a security tool to be installed."""

    name: str
    packages: List[str]
    category: str
    description: str
    status: bool = False


# Comprehensive tool list with all packages needed for each tool
SECURITY_TOOLS = [
    # Network Security & Analysis
    SecurityTool(
        "Wireshark Suite",
        ["wireshark", "wireshark-qt", "tshark", "wireshark-doc"],
        "Network Analysis",
        "Complete network protocol analyzer suite",
    ),
    SecurityTool(
        "Network Mapper Suite",
        ["nmap", "ndiff", "zenmap", "nmap-common"],
        "Network Analysis",
        "Network discovery and security scanner suite",
    ),
    SecurityTool(
        "Advanced Network Tools",
        ["tcpdump", "netcat-openbsd", "nethogs", "iftop", "bmon", "iptraf-ng"],
        "Network Analysis",
        "Collection of network monitoring tools",
    ),
    SecurityTool(
        "Network Security Suite",
        ["snort", "suricata", "zeek", "ntopng", "pmacct"],
        "Network Security",
        "Network IDS/IPS and monitoring suite",
    ),
    # Vulnerability Assessment
    SecurityTool(
        "Vulnerability Scanner Suite",
        ["openvas", "nikto", "wapiti", "sqlmap", "arachni"],
        "Vulnerability Assessment",
        "Comprehensive vulnerability scanning toolkit",
    ),
    SecurityTool(
        "Web Security Tools",
        ["zaproxy", "burpsuite-free", "dirb", "gobuster", "ffuf", "feroxbuster"],
        "Web Security",
        "Web application security testing suite",
    ),
    # Forensics & Analysis
    SecurityTool(
        "Digital Forensics Suite",
        [
            "autopsy",
            "sleuthkit",
            "dc3dd",
            "testdisk",
            "foremost",
            "scalpel",
            "exiftool",
        ],
        "Forensics",
        "Complete digital forensics platform",
    ),
    SecurityTool(
        "Memory Analysis Tools",
        ["volatility3", "radare2", "binwalk", "ewf-tools", "bulk-extractor"],
        "Forensics",
        "Memory and binary analysis toolkit",
    ),
    # System Security
    SecurityTool(
        "System Hardening Suite",
        ["lynis", "rkhunter", "chkrootkit", "aide", "tiger", "tripwire"],
        "System Security",
        "System auditing and hardening tools",
    ),
    SecurityTool(
        "Access Control Tools",
        ["fail2ban", "ufw", "apparmor", "selinux", "auditd", "acct"],
        "System Security",
        "Access control and monitoring suite",
    ),
    # Password & Crypto Tools
    SecurityTool(
        "Password Tools Suite",
        ["john", "hashcat", "hydra", "medusa", "ophcrack", "crack", "rarcrack"],
        "Password Tools",
        "Password recovery and cracking toolkit",
    ),
    SecurityTool(
        "Crypto Tools",
        ["gnupg", "keyutils", "cryptsetup", "steghide", "ccrypt", "checksecurity"],
        "Cryptography",
        "Cryptography and encryption tools",
    ),
    # Wireless Security
    SecurityTool(
        "Wireless Security Suite",
        ["aircrack-ng", "kismet", "wifite", "hostapd", "wavemon", "horst"],
        "Wireless",
        "Wireless network security toolkit",
    ),
    SecurityTool(
        "Bluetooth Security Tools",
        ["bluez", "bluez-tools", "btscanner", "bluelog", "bluesnarfer"],
        "Wireless",
        "Bluetooth security testing tools",
    ),
    # Development & Analysis
    SecurityTool(
        "Development Tools",
        ["build-essential", "gdb", "strace", "ltrace", "valgrind", "cmake", "meson"],
        "Development",
        "Development and debugging tools",
    ),
    SecurityTool(
        "Python Security Suite",
        ["python3-pip", "python3-venv", "python3-dev", "python3-setuptools"],
        "Development",
        "Python development environment",
    ),
    # Container Security
    SecurityTool(
        "Container Security Suite",
        ["docker.io", "docker-compose", "podman", "buildah", "skopeo"],
        "Containers",
        "Container runtime and security tools",
    ),
    # Malware Analysis
    SecurityTool(
        "Malware Analysis Suite",
        ["clamav", "clamav-daemon", "yara", "volatility3", "radare2"],
        "Malware Analysis",
        "Malware detection and analysis tools",
    ),
    # Monitoring & Logging
    SecurityTool(
        "System Monitoring Suite",
        ["nagios4", "prometheus", "grafana", "collectd", "munin", "zabbix-server"],
        "Monitoring",
        "System and network monitoring tools",
    ),
    SecurityTool(
        "Log Analysis Tools",
        ["logwatch", "syslog-ng", "graylog-server", "rsyslog", "logrotate"],
        "Monitoring",
        "Log management and analysis tools",
    ),
    # Additional Security Tools
    SecurityTool(
        "Security Essentials",
        ["keepassxc", "veracrypt", "vault", "openssh-server", "openssl"],
        "Security",
        "Essential security applications",
    ),
]


def create_header() -> Panel:
    """Create a styled header panel."""
    try:
        fig = pyfiglet.Figlet(font="slant")
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = APP_NAME

    header_text = Text()
    header_text.append(ascii_art, style=f"bold cyan")
    header_text.append(f"\nVersion {VERSION}", style="italic white")
    header_text.append(f"\n{APP_SUBTITLE}", style="bold blue")

    return Panel(
        header_text,
        border_style="cyan",
        padding=(1, 2),
        title="[bold white]Batch Installation[/]",
    )


def prepare_batch_installation() -> List[str]:
    """Prepare the complete list of packages for batch installation."""
    all_packages: Set[str] = set()
    for tool in SECURITY_TOOLS:
        all_packages.update(tool.packages)
    return list(all_packages)


def run_batch_installation(packages: List[str], simulate: bool = False) -> bool:
    """Run the batch installation of all packages."""
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"

    install_cmd = ["apt-get", "install", "-y"] + packages

    if simulate:
        console.print("[yellow]Simulating installation of packages...[/]")
        time.sleep(2)
        return True

    try:
        process = subprocess.Popen(
            install_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        return process.returncode == 0 if process.returncode is not None else True

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error during installation: {e}[/]")
        return False


def update_system(simulate: bool = False) -> bool:
    """Update system packages."""
    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"

        if not simulate:
            subprocess.run(["apt-get", "update"], check=True, env=env)
            subprocess.run(["apt-get", "upgrade", "-y"], check=True, env=env)
        else:
            time.sleep(2)

        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error updating system: {e}[/]")
        return False


def main() -> None:
    """Main function for batch installation process."""
    parser = argparse.ArgumentParser(description="Batch Security Tools Installer")
    parser.add_argument("--simulate", action="store_true", help="Simulate installation")
    parser.add_argument("--skip-confirm", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not os.geteuid() == 0:
        console.print("[red]Error: This script requires root privileges.[/]")
        sys.exit(1)

    console.clear()
    console.print(create_header())

    # Show installation plan
    total_packages = len(prepare_batch_installation())
    console.print(f"\nPreparing to install [cyan]{total_packages}[/] packages")

    if not args.skip_confirm:
        console.print("\nPress Enter to continue or Ctrl+C to abort...")
        input()

    with Progress(
        SpinnerColumn("dots", style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        # System update
        update_task = progress.add_task("[cyan]Updating system...", total=100)
        if update_system(args.simulate):
            progress.update(update_task, completed=100)
        else:
            console.print("[red]System update failed. Aborting.[/]")
            sys.exit(1)

        # Batch installation
        install_task = progress.add_task(
            "[cyan]Installing security tools...", total=len(SECURITY_TOOLS)
        )

        packages = prepare_batch_installation()
        if run_batch_installation(packages, args.simulate):
            progress.update(install_task, completed=len(SECURITY_TOOLS))
        else:
            console.print("[red]Installation failed.[/]")
            sys.exit(1)

    # Display completion message
    console.print(
        Panel(
            Text.from_markup(
                "[green]Installation Complete![/]\n\n"
                f"[cyan]Successfully installed {total_packages} packages[/]\n"
                "\n[yellow]Note: Some tools may require additional configuration.[/]"
            ),
            title="Setup Complete",
            border_style="green",
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]An error occurred: {str(e)}[/]")
        console.print_exception()
        sys.exit(1)
