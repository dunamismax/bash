#!/usr/bin/env python3
"""
Nala-based Security Tools Configurator
--------------------------------------------------

A streamlined system configuration tool that batch installs security tools
using nala package manager for better performance and error handling.

Version: 3.1.0
"""

import os
import sys
import subprocess
import time
import signal
import atexit
import psutil
from datetime import datetime
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
        TaskProgressColumn,
    )
    from rich.style import Style
    from rich.table import Table
    from rich.live import Live
except ImportError:
    print("Required packages missing. Installing dependencies...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet", "psutil"])
    print("Please run the script again.")
    sys.exit(1)

# Console setup
console = Console()


# Check if nala is installed
def ensure_nala_installed():
    """Ensure nala is installed on the system."""
    try:
        subprocess.run(["which", "nala"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        console.print("[yellow]Installing nala package manager...[/]")
        try:
            subprocess.run(["apt-get", "update"], check=True)
            subprocess.run(["apt-get", "install", "nala", "-y"], check=True)
        except subprocess.CalledProcessError as e:
            console.print("[red]Failed to install nala. Please install it manually:[/]")
            console.print("sudo apt update && sudo apt install nala -y")
            sys.exit(1)


def check_and_kill_package_locks():
    """Check for and handle package manager locks."""
    lock_files = [
        "/var/lib/dpkg/lock",
        "/var/lib/apt/lists/lock",
        "/var/cache/apt/archives/lock",
        "/var/lib/dpkg/lock-frontend",
    ]

    for lock_file in lock_files:
        if os.path.exists(lock_file):
            try:
                # Find processes holding the lock
                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        if any(
                            cmd in str(proc.info["cmdline"])
                            for cmd in ["apt", "dpkg", "nala"]
                        ):
                            console.print(
                                f"[yellow]Found blocking process: {proc.info['name']} (PID: {proc.info['pid']})[/]"
                            )
                            prompt = input(f"Kill process {proc.info['pid']}? (y/n): ")
                            if prompt.lower() == "y":
                                proc.kill()
                                time.sleep(1)  # Wait for process to terminate
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                # Remove lock files
                if os.path.exists(lock_file):
                    os.remove(lock_file)
                    console.print(f"[green]Removed lock file: {lock_file}[/]")
            except Exception as e:
                console.print(f"[red]Error handling lock file {lock_file}: {str(e)}[/]")
                return False
    return True


def update_system(simulate: bool = False) -> bool:
    """Update system packages using nala."""
    try:
        if not check_and_kill_package_locks():
            return False

        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"

        if not simulate:
            # Update package lists
            result = subprocess.run(
                ["nala", "update"], env=env, check=True, capture_output=True, text=True
            )
            console.print(result.stdout)

            # Upgrade packages
            result = subprocess.run(
                ["nala", "upgrade", "-y"],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
        else:
            time.sleep(2)

        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error updating system: {e.stderr}[/]")
        return False


def install_packages(packages: list, simulate: bool = False) -> bool:
    """Install packages using nala."""
    try:
        if not check_and_kill_package_locks():
            return False

        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"

        cmd = ["nala", "install", "-y"] + packages

        if simulate:
            console.print("[yellow]Simulating package installation...[/]")
            time.sleep(2)
            return True

        result = subprocess.run(
            cmd, env=env, check=True, capture_output=True, text=True
        )
        console.print(result.stdout)
        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error installing packages: {e.stderr}[/]")
        return False


# Security tools configuration
SECURITY_TOOLS = {
    "Network Analysis": [
        "wireshark",
        "wireshark-qt",
        "tshark",
        "nmap",
        "tcpdump",
        "netcat-openbsd",
        "nethogs",
        "iftop",
    ],
    "Vulnerability Assessment": ["nikto", "sqlmap", "wapiti", "dirb", "gobuster"],
    "Forensics": ["autopsy", "sleuthkit", "testdisk", "foremost", "dc3dd", "exiftool"],
    "System Security": ["lynis", "rkhunter", "chkrootkit", "fail2ban", "ufw", "aide"],
    "Password Tools": ["john", "hashcat", "hydra", "crackmapexec", "medusa"],
    "Wireless Security": ["aircrack-ng", "kismet", "wifite", "hostapd", "wavemon"],
    "Development": [
        "build-essential",
        "python3-pip",
        "python3-venv",
        "git",
        "gdb",
        "strace",
    ],
    "Containers": ["docker.io", "docker-compose", "podman", "buildah"],
    "Monitoring": ["nagios4", "prometheus", "grafana", "zabbix-server", "munin"],
}


def main():
    parser = argparse.ArgumentParser(description="Security Tools Installer using nala")
    parser.add_argument("--simulate", action="store_true", help="Simulate installation")
    parser.add_argument("--skip-confirm", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if os.geteuid() != 0:
        console.print("[red]Error: This script requires root privileges.[/]")
        sys.exit(1)

    # Ensure nala is installed
    ensure_nala_installed()

    console.clear()
    header = pyfiglet.figlet_format("Security Tools", font="slant")
    console.print(f"[cyan]{header}[/]")
    console.print("[cyan]Using nala package manager for better performance[/]\n")

    # Flatten package list
    all_packages = [pkg for category in SECURITY_TOOLS.values() for pkg in category]
    console.print(f"Preparing to install [cyan]{len(all_packages)}[/] packages")

    if not args.skip_confirm:
        console.print("\nPress Enter to continue or Ctrl+C to abort...")
        input()

    with Progress(
        SpinnerColumn("dots", style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=50),
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

        # Install packages
        install_task = progress.add_task(
            "[cyan]Installing security tools...", total=100
        )
        if install_packages(all_packages, args.simulate):
            progress.update(install_task, completed=100)
        else:
            console.print("[red]Installation failed.[/]")
            sys.exit(1)

    # Display completion message
    console.print(
        Panel(
            Text.from_markup(
                "[green]Installation Complete![/]\n\n"
                f"[cyan]Successfully installed {len(all_packages)} security tools[/]\n"
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
