#!/usr/bin/env python3
"""
Enhanced DNS Records Updater
----------------------------

This utility updates Cloudflare DNS A records with your current public IP address
using the Cloudflare API via the standard library. It includes comprehensive logging,
error handling, and graceful signal handling.

Usage:
  sudo ./update_dns_records.py

Notes:
  - This script must be run with root privileges.
  - Requires environment variables CF_API_TOKEN and CF_ZONE_ID (e.g., set them in /etc/environment).

Version: 4.2.0
"""

import atexit
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from typing import List, Dict, Any, Optional, Union

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
# Configuration & Constants
# ------------------------------
LOG_FILE = "/var/log/update_dns_records.log"
DEFAULT_LOG_LEVEL = "INFO"
TERM_WIDTH = 80  # Can be adjusted based on terminal size

# Cloudflare API credentials from environment variables
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")

# Fallback IP services to determine public IP
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]

# ------------------------------
# Nord-Themed Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold #88C0D0]{border}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]  {title.center(TERM_WIDTH - 4)}[/bold #88C0D0]")
    console.print(f"[bold #88C0D0]{border}[/bold #88C0D0]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[#81A1C1]{message}[/#81A1C1]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold #A3BE8C]✓ {message}[/bold #A3BE8C]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #EBCB8B]⚠ {message}[/bold #EBCB8B]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {message}[/bold #BF616A]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")


# ------------------------------
# Console Spinner for Progress Indication
# ------------------------------
class ConsoleSpinner:
    """A spinner to indicate progress for operations with unknown duration."""

    def __init__(self, message: str):
        self.message = message
        self.spinning = True
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.start_time = time.time()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            sys.stdout.write(
                f"\r{self.spinner_chars[self.current]} {self.message} [{elapsed:.1f}s elapsed]"
            )
            sys.stdout.flush()
            self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.spinning = False
        self.thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()


# ------------------------------
# Logging Configuration
# ------------------------------
def setup_logging() -> None:
    """Set up logging to both console and file."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        print_warning(f"Failed to set up log file {LOG_FILE}: {e}")
        print_warning("Continuing with console logging only")


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_step("Performing cleanup tasks before exit.")
    logging.info("Performing cleanup tasks before exit.")


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"Script interrupted by {sig_name}.")
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ------------------------------
# Dependency & Privilege Checks
# ------------------------------
def check_dependencies() -> None:
    """Check for required dependencies."""
    try:
        import rich
        import pyfiglet
    except ImportError as e:
        print(f"Error: Missing required dependency: {e}")
        print("Please install required packages using pip:")
        print("pip install rich pyfiglet")
        sys.exit(1)


def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        print_error("This script must be run as root.")
        sys.exit(1)


def validate_config() -> None:
    """Ensure required environment variables are set."""
    if not CF_API_TOKEN:
        print_error(
            "Environment variable 'CF_API_TOKEN' is not set. Please set it in /etc/environment."
        )
        sys.exit(1)
    if not CF_ZONE_ID:
        print_error(
            "Environment variable 'CF_ZONE_ID' is not set. Please set it in /etc/environment."
        )
        sys.exit(1)


# ------------------------------
# Helper Functions
# ------------------------------
def get_public_ip() -> str:
    """Retrieve the current public IP address using fallback services."""
    for service_url in IP_SERVICES:
        try:
            print_step(f"Retrieving public IP from {service_url}")
            logging.debug(f"Retrieving public IP from {service_url}")
            req = Request(service_url)
            with urlopen(req, timeout=10) as response:
                ip = response.read().decode().strip()
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                    print_success(f"Public IP from {service_url}: {ip}")
                    logging.info(f"Public IP from {service_url}: {ip}")
                    return ip
                else:
                    print_warning(f"Invalid IP format from {service_url}: {ip}")
                    logging.warning(f"Invalid IP format from {service_url}: {ip}")
        except Exception as e:
            print_warning(f"Failed to get public IP from {service_url}: {e}")
            logging.warning(f"Failed to get public IP from {service_url}: {e}")

    print_error("Failed to retrieve public IP from all services.")
    logging.error("Failed to retrieve public IP from all services.")
    sys.exit(1)


def fetch_dns_records() -> List[Dict[str, Any]]:
    """Fetch all DNS A records from Cloudflare."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if "result" not in data:
                print_error("Unexpected response from Cloudflare API.")
                logging.error("Unexpected response from Cloudflare API.")
                sys.exit(1)
            return data["result"]
    except Exception as e:
        print_error(f"Failed to fetch DNS records from Cloudflare: {e}")
        logging.error(f"Failed to fetch DNS records from Cloudflare: {e}")
        sys.exit(1)


def update_dns_record(
    record_id: str, record_name: str, current_ip: str, proxied: bool
) -> bool:
    """Update a single DNS A record with the new IP address."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "A",
        "name": record_name,
        "content": current_ip,
        "ttl": 1,
        "proxied": proxied,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="PUT")
    try:
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            if not result.get("success"):
                errors = ", ".join(
                    error.get("message", "Unknown error")
                    for error in result.get("errors", [])
                )
                print_warning(f"Failed to update record '{record_name}': {errors}")
                logging.warning(f"Failed to update record '{record_name}': {errors}")
                return False
            print_success(f"Successfully updated DNS record '{record_name}'")
            logging.info(f"Successfully updated DNS record '{record_name}'")
            return True
    except Exception as e:
        print_warning(f"Error updating DNS record '{record_name}': {e}")
        logging.warning(f"Error updating DNS record '{record_name}': {e}")
        return False


# ------------------------------
# Main Functionality
# ------------------------------
def update_cloudflare_dns() -> bool:
    """Update Cloudflare DNS A records with the current public IP."""
    print_section("Cloudflare DNS Update Process")
    logging.info("Starting Cloudflare DNS update process")

    print_info("Fetching current public IP...")
    logging.info("Fetching current public IP...")
    with ConsoleSpinner("Retrieving public IP..."):
        current_ip = get_public_ip()
    print_info(f"Current public IP: {current_ip}")
    logging.info(f"Current public IP: {current_ip}")

    print_info("Fetching DNS records from Cloudflare...")
    logging.info("Fetching DNS records from Cloudflare...")
    with ConsoleSpinner("Fetching DNS records..."):
        records = fetch_dns_records()
    print_info(f"Found {len(records)} DNS records")
    logging.info(f"Found {len(records)} DNS records")

    # Use Rich progress bar for tracking record updates
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold #88C0D0]{task.description}"),
        BarColumn(complete_style="#A3BE8C", finished_style="#A3BE8C"),
        TextColumn("[#81A1C1]{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Updating DNS records...", total=len(records))

        errors = 0
        updates = 0
        for record in records:
            if record.get("type") != "A":
                progress.update(task, advance=1)
                continue

            record_id = record.get("id")
            record_name = record.get("name")
            record_ip = record.get("content")
            proxied = record.get("proxied", False)

            progress.update(task, description=f"Processing '{record_name}'")

            if record_ip != current_ip:
                logging.info(f"Updating '{record_name}': {record_ip} → {current_ip}")
                if update_dns_record(record_id, record_name, current_ip, proxied):
                    updates += 1
                else:
                    errors += 1
            else:
                logging.debug(f"No update needed for '{record_name}' (IP: {record_ip})")

            progress.update(task, advance=1)

    if errors > 0:
        print_warning(f"Completed with {errors} error(s) and {updates} update(s)")
        logging.warning(f"Completed with {errors} error(s) and {updates} update(s)")
        return False
    elif updates > 0:
        print_success(f"Completed successfully with {updates} update(s)")
        logging.info(f"Completed successfully with {updates} update(s)")
        return True
    else:
        print_success("No DNS records required updating")
        logging.info("No DNS records required updating")
        return True


# ------------------------------
# Interactive Menu Functions
# ------------------------------
def interactive_menu() -> None:
    """Display the interactive menu."""
    while True:
        print_header("DNS Updater")
        console.print("[#D8DEE9]1. Update DNS Records[/#D8DEE9]")
        console.print("[#D8DEE9]2. View Current Public IP[/#D8DEE9]")
        console.print("[#D8DEE9]3. View Configuration[/#D8DEE9]")
        console.print("[#D8DEE9]4. Exit[/#D8DEE9]")

        choice = input("\nEnter your choice [1-4]: ").strip()

        if choice == "1":
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            logging.info(f"DNS UPDATE STARTED AT {now}")
            logging.info("=" * 60)

            success = update_cloudflare_dns()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            if success:
                logging.info(f"DNS UPDATE COMPLETED SUCCESSFULLY AT {now}")
            else:
                logging.warning(f"DNS UPDATE COMPLETED WITH ERRORS AT {now}")
            logging.info("=" * 60)

        elif choice == "2":
            print_section("Current Public IP")
            with ConsoleSpinner("Retrieving public IP..."):
                current_ip = get_public_ip()
            print_info(f"Your current public IP address: {current_ip}")

        elif choice == "3":
            print_section("Configuration")
            print_info(f"Log file: {LOG_FILE}")
            print_info(f"Zone ID: {CF_ZONE_ID if CF_ZONE_ID else 'Not configured'}")
            token_status = "Configured" if CF_API_TOKEN else "Not configured"
            print_info(f"API Token: {token_status}")
            print_info(f"IP Services: {', '.join(IP_SERVICES)}")

        elif choice == "4":
            print_info("Exiting. Goodbye!")
            break
        else:
            print_error("Invalid choice. Please try again.")

        input("\nPress Enter to continue...")


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        print_header("Cloudflare DNS Updater v4.2.0")
        console.print(
            f"Date: [bold #81A1C1]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #81A1C1]"
        )

        setup_logging()
        check_dependencies()
        check_root()
        validate_config()

        if len(sys.argv) > 1 and sys.argv[1] == "--non-interactive":
            # Non-interactive mode
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            logging.info(f"DNS UPDATE STARTED AT {now}")
            logging.info("=" * 60)

            success = update_cloudflare_dns()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            if success:
                logging.info(f"DNS UPDATE COMPLETED SUCCESSFULLY AT {now}")
            else:
                logging.warning(f"DNS UPDATE COMPLETED WITH ERRORS AT {now}")
            logging.info("=" * 60)
        else:
            # Interactive menu mode
            interactive_menu()

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
