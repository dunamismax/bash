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

Author: YourName | License: MIT | Version: 4.1.0
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

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
LOG_FILE = "/var/log/update_dns_records.log"
DEFAULT_LOG_LEVEL = "INFO"

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
# Nord‑Themed Colors & Console Setup
# ------------------------------
class Colors:
    """Nord-themed ANSI color codes for terminal output."""
    HEADER = "\033[38;5;81m"     # Nord9 - Blue
    GREEN = "\033[38;5;108m"     # Nord14 - Green
    YELLOW = "\033[38;5;179m"    # Nord13 - Yellow
    RED = "\033[38;5;174m"       # Nord11 - Red
    BLUE = "\033[38;5;67m"       # Nord10 - Deep Blue
    CYAN = "\033[38;5;110m"      # Nord8 - Light Blue
    MAGENTA = "\033[38;5;139m"   # Nord15 - Purple
    WHITE = "\033[38;5;253m"     # Nord4 - Light foreground
    BOLD = "\033[1m"
    ENDC = "\033[0m"

console = Console()

def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {Colors.HEADER}")

def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * 60
    console.print(f"[{Colors.BOLD}{Colors.HEADER}]{border}[/{Colors.HEADER}{Colors.BOLD}]")
    console.print(f"[{Colors.BOLD}{Colors.HEADER}]  {title}[/{Colors.HEADER}{Colors.BOLD}]")
    console.print(f"[{Colors.HEADER}]{border}[/{Colors.HEADER}]\n")

# ------------------------------
# Console Spinner for Progress Indication
# ------------------------------
class ConsoleSpinner:
    """A simple spinner to indicate progress for operations with unknown duration."""
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
    """Set up logging to both console and file using Nord-themed formatting."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove existing handlers
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
        file_handler = logging.FileHandler(LOG_FILE)
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
    """Perform cleanup tasks before exiting."""
    logging.info("Performing cleanup tasks before exit.")

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    logging.error(f"Script interrupted by signal {signal.Signals(signum).name}.")
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
    """No additional external dependencies beyond the standard library are required."""
    pass  # All dependencies are from the standard library.

def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

def validate_config() -> None:
    """Ensure required environment variables are set."""
    if not CF_API_TOKEN:
        logging.error("Environment variable 'CF_API_TOKEN' is not set. Please set it in /etc/environment.")
        sys.exit(1)
    if not CF_ZONE_ID:
        logging.error("Environment variable 'CF_ZONE_ID' is not set. Please set it in /etc/environment.")
        sys.exit(1)

# ------------------------------
# Helper Functions
# ------------------------------
def get_public_ip() -> str:
    """Retrieve the current public IP address using fallback services."""
    for service_url in IP_SERVICES:
        try:
            logging.debug(f"Retrieving public IP from {service_url}")
            req = Request(service_url)
            with urlopen(req, timeout=10) as response:
                ip = response.read().decode().strip()
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                    logging.info(f"Public IP from {service_url}: {ip}")
                    return ip
                else:
                    logging.warning(f"Invalid IP format from {service_url}: {ip}")
        except Exception as e:
            logging.warning(f"Failed to get public IP from {service_url}: {e}")
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
                logging.error("Unexpected response from Cloudflare API.")
                sys.exit(1)
            return data["result"]
    except Exception as e:
        logging.error(f"Failed to fetch DNS records from Cloudflare: {e}")
        sys.exit(1)

def update_dns_record(record_id: str, record_name: str, current_ip: str, proxied: bool) -> bool:
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
                errors = ", ".join(error.get("message", "Unknown error") for error in result.get("errors", []))
                logging.warning(f"Failed to update record '{record_name}': {errors}")
                return False
            logging.info(f"Successfully updated DNS record '{record_name}'.")
            return True
    except Exception as e:
        logging.warning(f"Error updating DNS record '{record_name}': {e}")
        return False

# ------------------------------
# Main Functionality
# ------------------------------
def update_cloudflare_dns() -> bool:
    """Update Cloudflare DNS A records with the current public IP."""
    print_section("Starting Cloudflare DNS Update")
    logging.info("Fetching current public IP...")
    with ConsoleSpinner("Retrieving public IP..."):
        current_ip = get_public_ip()
    logging.info(f"Current public IP: {current_ip}")

    logging.info("Fetching DNS records from Cloudflare...")
    with ConsoleSpinner("Fetching DNS records..."):
        records = fetch_dns_records()
    logging.info(f"Found {len(records)} DNS records.")

    errors = 0
    updates = 0
    for record in records:
        if record.get("type") != "A":
            continue
        record_id = record.get("id")
        record_name = record.get("name")
        record_ip = record.get("content")
        proxied = record.get("proxied", False)
        if record_ip != current_ip:
            logging.info(f"Updating '{record_name}': {record_ip} → {current_ip}")
            if update_dns_record(record_id, record_name, current_ip, proxied):
                updates += 1
            else:
                errors += 1
        else:
            logging.debug(f"No update needed for '{record_name}' (IP: {record_ip})")

    if errors > 0:
        logging.warning(f"Completed with {errors} error(s) and {updates} update(s).")
        return False
    elif updates > 0:
        logging.info(f"Completed successfully with {updates} update(s).")
        return True
    else:
        logging.info("No DNS records required updating.")
        return True

# ------------------------------
# Main Entry Point
# ------------------------------
@click.command()
def cli() -> None:
    """Update Cloudflare DNS A records with the current public IP address."""
    print_header("Cloudflare DNS Updater")
    setup_logging()
    check_dependencies()  # No extra dependencies beyond standard library
    check_root()
    validate_config()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"DNS UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    success = update_cloudflare_dns()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    if success:
        logging.info(f"DNS UPDATE COMPLETED SUCCESSFULLY AT {now}")
    else:
        logging.warning(f"DNS UPDATE COMPLETED WITH ERRORS AT {now}")
    logging.info("=" * 80)

def main() -> None:
    try:
        cli()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()