#!/usr/bin/env python3
"""
Enhanced Tailscale Reset Script

This utility resets Tailscale on Ubuntu by:
  • Stopping and disabling the tailscaled service.
  • Uninstalling tailscale and removing configuration/data directories.
  • Reinstalling tailscale via the official install script.
  • Enabling and starting the tailscaled service.
  • Running "tailscale up" to bring the daemon up.

Note: Run this script as root.
"""

import atexit
import os
import signal
import sys
import subprocess
import time
import shutil
from datetime import datetime

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
TAILSCALE_INSTALL_URL = "https://tailscale.com/install.sh"
CHECK_INTERVAL = 2  # seconds between steps

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
console = Console()

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
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
# Helper Functions
# ------------------------------
def run_command(cmd: list[str], shell: bool = False, timeout: int = 30) -> subprocess.CompletedProcess:
    """
    Execute a command and return the CompletedProcess.
    
    Args:
        cmd: Command to run as a list of strings.
        shell: Whether to run the command in shell.
        timeout: Timeout in seconds.
    
    Returns:
        CompletedProcess object.
    
    Raises:
        subprocess.CalledProcessError if command fails.
    """
    try:
        return subprocess.run(cmd, shell=shell, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd) if not shell else cmd}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
        raise

def check_root() -> None:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run as root (e.g., with sudo).")
        sys.exit(1)

# ------------------------------
# Tailscale Operations
# ------------------------------
def uninstall_tailscale() -> None:
    """Stop tailscaled, uninstall tailscale, and remove configuration/data directories."""
    print_section("Uninstalling Tailscale")
    steps = [
        ("Stopping tailscaled service", ["systemctl", "stop", "tailscaled"]),
        ("Disabling tailscaled service", ["systemctl", "disable", "tailscaled"]),
        ("Removing tailscale package", ["apt-get", "remove", "--purge", "tailscale", "-y"]),
        ("Autoremoving unused packages", ["apt-get", "autoremove", "-y"]),
    ]
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uninstalling Tailscale", total=len(steps))
        for desc, cmd in steps:
            print_step(desc)
            with progress:
                run_command(cmd)
            progress.advance(task)
    # Remove configuration/data directories
    config_paths = ["/var/lib/tailscale", "/etc/tailscale", "/usr/share/tailscale"]
    for path in config_paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print_success(f"Removed {path}")
            except Exception as e:
                print_warning(f"Failed to remove {path}: {e}")
    print_success("Tailscale uninstalled and cleaned up.")

def install_tailscale() -> None:
    """Install tailscale using the official install script."""
    print_section("Installing Tailscale")
    print_step("Running tailscale install script")
    install_cmd = f"curl -fsSL {TAILSCALE_INSTALL_URL} | sh"
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Installing tailscale", total=1)
        run_command(install_cmd, shell=True)
        progress.advance(task)
    print_success("Tailscale installed.")

def start_tailscale_service() -> None:
    """Enable and start the tailscaled service."""
    print_section("Enabling and Starting Tailscale Service")
    steps = [
        ("Enabling tailscaled service", ["systemctl", "enable", "tailscaled"]),
        ("Starting tailscaled service", ["systemctl", "start", "tailscaled"]),
    ]
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting Tailscale Service", total=len(steps))
        for desc, cmd in steps:
            print_step(desc)
            with progress:
                run_command(cmd)
            progress.advance(task)
    print_success("Tailscale service enabled and started.")

def tailscale_up() -> None:
    """Run 'tailscale up' to bring up the daemon."""
    print_section("Running 'tailscale up'")
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Executing tailscale up", total=1)
        result = run_command(["tailscale", "up"])
        progress.advance(task)
    print_success("Tailscale is up!")
    console.print(f"\n[bold]tailscale up output:[/bold]\n{result.stdout}")

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
def main() -> None:
    """
    Reset Tailscale on Ubuntu

    This utility stops and disables the tailscaled service,
    uninstalls tailscale and cleans up configuration/data files,
    reinstalls tailscale, enables and starts the service,
    and runs "tailscale up" to bring the daemon up.
    """
    check_root()
    print_header("Tailscale Reset Script")
    console.print(f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")
    uninstall_tailscale()
    time.sleep(CHECK_INTERVAL)
    install_tailscale()
    time.sleep(CHECK_INTERVAL)
    start_tailscale_service()
    time.sleep(CHECK_INTERVAL)
    tailscale_up()
    print_header("Tailscale Reset Complete")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)