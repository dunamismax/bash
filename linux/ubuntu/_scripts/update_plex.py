#!/usr/bin/env python3
"""
Enhanced Plex Updater
----------------------

Downloads and installs the latest Plex Media Server package,
resolves dependency issues, cleans up temporary files, and restarts
the Plex service via system commands.

Note: Run this script with root privileges.
Version: 1.0.0 | License: MIT | Author: Your Name
"""

import atexit
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
DEFAULT_PLEX_URL: str = (
    "https://downloads.plex.tv/plex-media-server-new/"
    "1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
)
TEMP_DEB: str = "/tmp/plexmediaserver.deb"
LOG_FILE: str = "/var/log/update_plex.log"
DEFAULT_LOG_LEVEL = logging.INFO

# ------------------------------
# Nord‑Themed Colors & Console Setup
# ------------------------------
class Colors:
    """Nord‑themed ANSI color codes."""
    HEADER = "\033[38;5;81m"     # Nord9 (Blue)
    GREEN = "\033[38;5;108m"     # Nord14 (Green)
    YELLOW = "\033[38;5;179m"    # Nord13 (Yellow)
    RED = "\033[38;5;196m"       # Nord11 (Red)
    CYAN = "\033[38;5;110m"      # Nord8 (Light Blue)
    BOLD = "\033[1m"
    ENDC = "\033[0m"

console = Console()

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {Colors.HEADER}")

def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * 60
    console.print(f"\n[bold {Colors.HEADER}]{border}[/bold {Colors.HEADER}]")
    console.print(f"[bold {Colors.HEADER}]  {title}[/bold {Colors.HEADER}]")
    console.print(f"[bold {Colors.HEADER}]{border}[/bold {Colors.HEADER}]\n")

def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{Colors.CYAN}]{message}[/{Colors.CYAN}]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {Colors.GREEN}]✓ {message}[/{Colors.GREEN}]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {Colors.YELLOW}]⚠ {message}[/{Colors.YELLOW}]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {Colors.RED}]✗ {message}[/{Colors.RED}]")

# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    """Set up logging with console and file handlers using Nord‑themed formatting."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(DEFAULT_LOG_LEVEL)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    formatter = logging.Formatter(
        fmt=f"{Colors.BOLD}[%(asctime)s] [%(levelname)s]{Colors.ENDC} %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    try:
        file_handler = logging.FileHandler(LOG_FILE, mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    logging.info("Performing cleanup tasks before exit.")
    if os.path.exists(TEMP_DEB):
        try:
            os.remove(TEMP_DEB)
            logging.info(f"Removed temporary file: {TEMP_DEB}")
        except Exception as e:
            logging.warning(f"Failed to remove temporary file {TEMP_DEB}: {e}")

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ------------------------------
# Dependency & Privilege Checks
# ------------------------------
def check_dependencies() -> None:
    """
    Ensure required system commands are available.
    Required: dpkg, apt-get, systemctl.
    """
    required_commands: List[str] = ["dpkg", "apt-get", "systemctl"]
    missing: List[str] = []
    for cmd in required_commands:
        try:
            subprocess.run(["which", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError:
            missing.append(cmd)
    if missing:
        logging.error(f"Missing required commands: {', '.join(missing)}")
        sys.exit(1)

def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

# ------------------------------
# Helper Functions
# ------------------------------
def run_command(cmd: List[str], check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Execute a command and log its output."""
    logging.info(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        if result.stdout:
            logging.info(result.stdout.strip())
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}")
        if e.stderr:
            logging.error(e.stderr.strip())
        if check:
            raise
        return e

# ------------------------------
# Plex Update Functions
# ------------------------------
def download_plex(plex_url: str) -> None:
    """
    Download the Plex Media Server package using urllib.
    
    Args:
        plex_url: URL of the Plex package.
    """
    print_section("Downloading Plex Package")
    logging.info(f"Downloading Plex from {plex_url}")
    logging.info(f"Saving package to {TEMP_DEB}")
    os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)
    try:
        start_time = time.time()
        urllib.request.urlretrieve(plex_url, TEMP_DEB)
        elapsed = time.time() - start_time
        file_size = os.path.getsize(TEMP_DEB)
        logging.info(f"Downloaded in {elapsed:.2f} seconds, size: {format_size(file_size)}")
    except Exception as e:
        logging.error(f"Failed to download Plex package: {e}")
        sys.exit(1)

def install_plex() -> None:
    """
    Install the Plex Media Server package and fix dependency issues.
    """
    print_section("Installing Plex Media Server")
    logging.info("Installing Plex package...")
    try:
        run_command(["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        logging.warning("Dependency issues detected; attempting to fix...")
        try:
            run_command(["apt-get", "install", "-f", "-y"])
            run_command(["dpkg", "-i", TEMP_DEB])
        except subprocess.CalledProcessError:
            logging.error("Failed to resolve dependencies for Plex.")
            sys.exit(1)
    logging.info("Plex installed successfully.")

def restart_plex() -> None:
    """
    Restart the Plex Media Server service.
    """
    print_section("Restarting Plex Service")
    logging.info("Restarting Plex service...")
    try:
        run_command(["systemctl", "restart", "plexmediaserver"])
        logging.info("Plex service restarted successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to restart Plex service.")
        sys.exit(1)

# ------------------------------
# CLI Argument Parsing with Click
# ------------------------------
@click.command()
@click.option("--plex-url", type=str, default=DEFAULT_PLEX_URL, help="URL to download the Plex package")
def cli(plex_url: str) -> None:
    """Download, install, and restart Plex Media Server."""
    print_header(f"Plex Updater v1.0.0")
    setup_logging()
    check_dependencies()
    check_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    download_plex(plex_url)
    install_plex()
    restart_plex()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    try:
        cli()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()