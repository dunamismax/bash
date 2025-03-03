#!/usr/bin/env python3
"""
Enhanced Security Tools Installer
-------------------------------
A streamlined system configuration tool that installs and configures security,
analysis, development, and intrusion detection tools on Ubuntu systems.

Version: 5.1.0
Author: Your Name
License: MIT
"""

import os
import sys
import subprocess
import time
import logging
import glob
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import argparse
import json
from datetime import datetime

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.panel import Panel
    from rich.table import Table
    from rich.logging import RichHandler
except ImportError:
    subprocess.run(["pip3", "install", "rich"])
    print("Dependencies installed. Please run the script again.")
    sys.exit(1)

# Initialize Rich console
console = Console()

# Setup logging
LOG_DIR = Path("/var/log/security_setup")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"security_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RichHandler(console=console, rich_tracebacks=True),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("security_setup")

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


class InstallationError(Exception):
    """Custom exception for installation errors."""

    pass


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

    def cleanup_package_system(self) -> bool:
        """Clean up package management system and remove invalid files."""
        try:
            # Clean up invalid .bak files in apt.conf.d
            apt_conf_path = "/etc/apt/apt.conf.d/"
            invalid_files = glob.glob(f"{apt_conf_path}/*.bak.*")
            for file in invalid_files:
                try:
                    if not self.simulate:
                        os.remove(file)
                    logger.info(f"Removed invalid file: {file}")
                except OSError as e:
                    logger.error(f"Failed to remove {file}: {e}")

            if not self.simulate:
                # Fix interrupted dpkg
                subprocess.run(["dpkg", "--configure", "-a"], check=True)
                # Clean package cache
                subprocess.run(["nala", "clean"], check=True)

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Package system cleanup failed: {e}")
            return False

    def setup_package_manager(self) -> bool:
        """Configure and update package manager."""
        try:
            if not self.simulate:
                # First install nala if not present
                if not Path("/usr/bin/nala").exists():
                    subprocess.run(["apt", "install", "nala", "-y"], check=True)

                # Update package lists using nala
                subprocess.run(["nala", "update"], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Package manager setup failed: {e}")
            return False

    def install_packages(self, packages: List[str]) -> Tuple[bool, List[str]]:
        """Install packages using nala."""
        try:
            if self.simulate:
                console.print(
                    f"[yellow]Simulating installation of {len(packages)} packages[/]"
                )
                time.sleep(2)
                return True, []

            failed_packages = []
            # Install in chunks to avoid command line length limits
            chunk_size = 50
            for i in range(0, len(packages), chunk_size):
                chunk = packages[i : i + chunk_size]
                try:
                    subprocess.run(["nala", "install", "-y"] + chunk, check=True)
                    self.successful_packages.extend(chunk)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install chunk: {chunk}")
                    logger.error(f"Error: {str(e)}")
                    failed_packages.extend(chunk)

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


def display_header():
    """Display script header."""
    console.print(
        Panel.fit(
            "[bold cyan]Enhanced Security Tools Installer v5.1.0[/]\n"
            "[dim]A comprehensive security toolkit installer for Ubuntu systems[/]",
            border_style="cyan",
        )
    )


def show_installation_plan():
    """Display installation plan with category table."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Category", style="cyan")
    table.add_column("Tools", justify="right", style="green")

    total = 0
    for category, tools in SECURITY_TOOLS.items():
        table.add_row(category, str(len(tools)))
        total += len(tools)

    console.print(Panel(table, title="Installation Plan", border_style="cyan"))
    console.print(f"\nTotal packages: [bold cyan]{total}[/]")


def main():
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
            console.print("[red]Error: This script requires root privileges[/]")
            sys.exit(1)

        setup = SystemSetup(simulate=args.simulate)

        console.clear()
        display_header()
        show_installation_plan()

        if not args.skip_confirm:
            console.print("\nPress Enter to continue or Ctrl+C to abort...")
            try:
                input()
            except KeyboardInterrupt:
                console.print("\n[yellow]Operation cancelled[/]")
                sys.exit(0)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            # Setup system
            task = progress.add_task("[cyan]Setting up system...", total=100)

            # Clean up package system first
            progress.update(task, description="[cyan]Cleaning up package system...")
            if not setup.cleanup_package_system():
                console.print("[red]Failed to clean up package system[/]")
                sys.exit(1)
            progress.update(task, completed=20)

            # Setup package manager
            progress.update(task, description="[cyan]Setting up package manager...")
            if not setup.setup_package_manager():
                console.print("[red]Failed to setup package manager[/]")
                sys.exit(1)
            progress.update(task, completed=40)

            # Install packages
            progress.update(task, description="[cyan]Installing security tools...")
            all_packages = [pkg for tools in SECURITY_TOOLS.values() for pkg in tools]
            unique_packages = list(set(all_packages))

            success, failed_packages = setup.install_packages(unique_packages)
            if failed_packages:
                setup.failed_packages = failed_packages
                if not args.skip_failed:
                    console.print("[red]Failed to install some packages[/]")
                    console.print("Failed packages:", ", ".join(failed_packages))
                    sys.exit(1)
                else:
                    console.print("[yellow]Some packages failed to install[/]")
                    console.print("Failed packages:", ", ".join(failed_packages))

            progress.update(task, completed=100)

        # Save installation report
        setup.save_installation_report()

        if setup.failed_packages:
            console.print("\n[yellow]⚠️ Installation completed with some failures[/]")
            console.print(f"Failed packages: {len(setup.failed_packages)}")
            console.print(f"Successfully installed: {len(setup.successful_packages)}")
        else:
            console.print("\n[bold green]🎉 Installation completed successfully![/]")

        console.print(f"\nDetailed logs available at: {LOG_FILE}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/]")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        console.print(f"[red]An unexpected error occurred: {str(e)}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
