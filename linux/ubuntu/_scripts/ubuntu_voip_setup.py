#!/usr/bin/env python3
"""
Enhanced Ubuntu VoIP Setup Utility

This utility sets up and configures VoIP services on Ubuntu.
It performs the following operations:
  • Verifies system compatibility and prerequisites
  • Updates system packages
  • Installs required VoIP packages (Asterisk, MariaDB, ufw)
  • Configures firewall rules for SIP and RTP
  • Creates Asterisk configuration files (with backup of existing ones)
  • Manages related services (enabling and restarting Asterisk and MariaDB)
  • Verifies the overall setup

Note: Run this script with root privileges.
"""

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
HOSTNAME = socket.gethostname()

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

# ------------------------------
# Nord‑Themed Console Setup
# ------------------------------
# Nord color palette (hex values):
# nord0:  #2E3440, nord1:  #3B4252, nord4:  #D8DEE9,
# nord7:  #8FBCBB, nord8:  #88C0D0, nord9:  #81A1C1, nord11: #BF616A
console = Console()


def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #5E81AC]⚠ {text}[/bold #5E81AC]")


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")


# ------------------------------
# Command Execution Helper
# ------------------------------
def run_command(cmd, env=None, check=True, capture_output=True, timeout=None):
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
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def signal_handler(sig, frame):
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


def cleanup():
    print_step("Performing cleanup tasks...")
    # Add any resource cleanup steps here


# ------------------------------
# Core Functions
# ------------------------------
def update_system() -> bool:
    print_section("Updating System Packages")
    try:
        with console.status("[bold #81A1C1]Updating package lists...", spinner="dots"):
            run_command(["apt-get", "update"])
        print_success("Package lists updated")
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False

    print_step("Upgrading installed packages...")
    try:
        result = run_command(["apt", "list", "--upgradable"], capture_output=True)
        lines = result.stdout.splitlines()
        package_count = max(1, len(lines) - 1)  # Exclude header
    except Exception:
        package_count = 10

    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
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
                progress.advance(task)
            console.print(line.strip(), style="dim")
        process.wait()
        if process.returncode != 0:
            print_error("System upgrade failed.")
            return False

    print_success("System packages updated successfully.")
    return True


def install_packages(packages: list) -> bool:
    if not packages:
        print_warning("No packages specified for installation")
        return True

    print_section("Installing VoIP Packages")
    print_step(f"Packages to install: {', '.join(packages)}")
    failed = False
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        console=console,
    ) as progress:
        task = progress.add_task("Installing packages", total=len(packages))
        for pkg in packages:
            print_step(f"Installing {pkg}")
            try:
                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in iter(proc.stdout.readline, ""):
                    if "Unpacking" in line or "Setting up" in line:
                        console.print("  " + line.strip(), style="#D8DEE9")
                proc.wait()
                if proc.returncode != 0:
                    print_error(f"Failed to install {pkg}")
                    failed = True
                else:
                    print_success(f"{pkg} installed")
            except Exception as e:
                print_error(f"Error installing {pkg}: {e}")
                failed = True
            progress.advance(task)
    if failed:
        print_warning("Some packages failed to install.")
        return False
    print_success("All packages installed successfully.")
    return True


def configure_firewall(rules: list) -> bool:
    print_section("Configuring Firewall")
    try:
        if not shutil.which("ufw"):
            print_warning("UFW not found. Installing ufw...")
            if not install_packages(["ufw"]):
                return False

        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            console=console,
        ) as progress:
            task = progress.add_task("Configuring firewall", total=len(rules) + 1)
            status_result = run_command(["ufw", "status"], check=False)
            if "Status: inactive" in status_result.stdout:
                print_step("Enabling UFW firewall...")
                run_command(["ufw", "--force", "enable"])
            progress.advance(task)
            for rule in rules:
                rule_desc = f"{rule['port']}/{rule['protocol']} ({rule['description']})"
                print_step(f"Adding rule for {rule_desc}")
                run_command(["ufw", "allow", f"{rule['port']}/{rule['protocol']}"])
                progress.advance(task)
            run_command(["ufw", "reload"])
            progress.advance(task)
        print_success("Firewall configured successfully.")
        return True
    except Exception as e:
        print_error(f"Firewall configuration failed: {e}")
        return False


def create_asterisk_config(configs: dict) -> bool:
    print_section("Creating Asterisk Configuration Files")
    try:
        config_dir = Path("/etc/asterisk")
        config_dir.mkdir(parents=True, exist_ok=True)
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating config files", total=len(configs))
            for filename, content in configs.items():
                file_path = config_dir / filename
                print_step(f"Creating {filename}")
                if file_path.exists():
                    backup_path = file_path.with_suffix(f".bak.{int(time.time())}")
                    shutil.copy2(file_path, backup_path)
                    print_step(f"Backed up existing file to {backup_path.name}")
                file_path.write_text(content)
                progress.advance(task)
        print_success("Asterisk configuration files created successfully.")
        return True
    except Exception as e:
        print_error(f"Failed to create Asterisk configuration files: {e}")
        return False


def manage_services(services: list, action: str) -> bool:
    print_section(f"{action.capitalize()}ing Services")
    failed = False
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"{action.capitalize()}ing services", total=len(services)
        )
        for service in services:
            print_step(f"{action.capitalize()}ing {service}")
            try:
                run_command(["systemctl", action, service])
                print_success(f"{service} {action}d successfully")
            except Exception as e:
                print_error(f"Failed to {action} {service}: {e}")
                failed = True
            progress.advance(task)
    if failed:
        print_warning("Some services failed to be managed properly.")
        return False
    return True


def verify_installation() -> bool:
    print_section("Verifying VoIP Setup")
    passed = True
    try:
        result = run_command(["asterisk", "-V"], capture_output=True)
        version = result.stdout.strip()
        print_success(f"Asterisk version: {version}")
    except Exception as e:
        print_error(f"Failed to get Asterisk version: {e}")
        passed = False

    for service in SERVICES:
        try:
            result = run_command(
                ["systemctl", "is-active", service], capture_output=True, check=False
            )
            status = result.stdout.strip()
            if status != "active":
                print_error(f"Service {service} is not active: {status}")
                passed = False
            else:
                print_success(f"Service {service} is active")
        except Exception as e:
            print_error(f"Error checking service {service}: {e}")
            passed = False

    try:
        result = run_command(["ufw", "status"], capture_output=True)
        for rule in FIREWALL_RULES:
            rule_str = f"{rule['port']}/{rule['protocol']}"
            if rule_str not in result.stdout:
                print_warning(f"Firewall rule {rule_str} not found")
                passed = False
            else:
                print_success(f"Firewall rule {rule_str} is active")
    except Exception as e:
        print_error(f"Failed to verify firewall rules: {e}")
        passed = False

    config_dir = Path("/etc/asterisk")
    for filename in ASTERISK_CONFIGS.keys():
        if not (config_dir / filename).exists():
            print_error(f"Configuration file {filename} is missing")
            passed = False
        else:
            print_success(f"Configuration file {filename} exists")
    if passed:
        print_success(
            "Verification completed successfully. VoIP setup is properly configured."
        )
    else:
        print_warning("Verification completed with some issues.")
    return passed


def perform_voip_setup() -> bool:
    print_header("Enhanced VoIP Setup")
    console.print(f"Hostname: [bold #D8DEE9]{HOSTNAME}[/bold #D8DEE9]")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )
    start_time = time.time()

    print_section("Checking Prerequisites")
    if os.geteuid() != 0:
        print_error("Run this script as root (e.g., using sudo)")
        return False
    if not shutil.which("apt-get"):
        print_error("apt-get is not available. This script requires Ubuntu.")
        return False
    try:
        result = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False)
        if result.returncode != 0:
            print_warning("No internet connectivity detected. Setup may fail.")
    except Exception as e:
        print_warning(f"Internet connectivity check failed: {e}")

    if not update_system():
        print_warning("System update encountered issues.")

    if not install_packages(VOIP_PACKAGES):
        print_error("Package installation failed. Aborting setup.")
        return False

    if not configure_firewall(FIREWALL_RULES):
        print_warning("Firewall configuration failed.")

    if not create_asterisk_config(ASTERISK_CONFIGS):
        print_error("Asterisk configuration failed. Aborting setup.")
        return False

    manage_services(SERVICES, "enable")
    manage_services(SERVICES, "restart")

    verification = verify_installation()

    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)
    print_header("Setup Summary")
    print_success(f"Elapsed time: {int(minutes)}m {int(seconds)}s")
    if verification:
        print_success("VoIP setup completed successfully.")
    else:
        print_warning("VoIP setup completed with warnings or errors.")

    print_section("Next Steps")
    console.print("1. Review the Asterisk configuration files in /etc/asterisk/")
    console.print("2. Configure SIP clients with the provided credentials")
    console.print("3. Test calling between extensions")
    console.print("4. Consider securing SIP with TLS for production use")

    return verification


# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.option("--check", is_flag=True, help="Perform system compatibility check only")
@click.option("--update", is_flag=True, help="Update system packages only")
@click.option(
    "--install", "install_only", is_flag=True, help="Install VoIP packages only"
)
@click.option("--firewall", is_flag=True, help="Configure firewall rules only")
@click.option("--asterisk", is_flag=True, help="Configure Asterisk only")
@click.option("--verify", is_flag=True, help="Verify installation only")
@click.option("--full", is_flag=True, help="Perform full VoIP setup")
@click.option("--verbose", is_flag=True, help="Enable verbose output")
def main(check, update, install_only, firewall, asterisk, verify, full, verbose):
    """Enhanced Ubuntu VoIP Setup Utility"""
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if os.geteuid() != 0:
        print_error("Run this script as root (e.g., using sudo)")
        sys.exit(1)

    if check:
        print_header("System Compatibility Check")
        if not shutil.which("apt-get"):
            print_error("apt-get not available.")
        else:
            print_success("apt-get is available.")
        try:
            result = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False)
            if result.returncode == 0:
                print_success("Internet connectivity confirmed.")
            else:
                print_warning("Internet connectivity issue detected.")
        except Exception as e:
            print_warning(f"Internet connectivity check failed: {e}")
        sys.exit(0)

    if update:
        if not update_system():
            sys.exit(1)
        sys.exit(0)

    if install_only:
        if not install_packages(VOIP_PACKAGES):
            sys.exit(1)
        sys.exit(0)

    if firewall:
        if not configure_firewall(FIREWALL_RULES):
            sys.exit(1)
        sys.exit(0)

    if asterisk:
        if not create_asterisk_config(ASTERISK_CONFIGS):
            sys.exit(1)
        sys.exit(0)

    if verify:
        if not verify_installation():
            sys.exit(1)
        sys.exit(0)

    # Full setup or no specific option provided
    if full or not any([check, update, install_only, firewall, asterisk, verify]):
        if not perform_voip_setup():
            sys.exit(1)


if __name__ == "__main__":
    main()
