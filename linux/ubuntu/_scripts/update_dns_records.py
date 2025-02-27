#!/usr/bin/env python3
"""
Script Name: update_dns_records.py
--------------------------------------------------------
Description:
  Updates Cloudflare DNS A records with the current public IP address using the Cloudflare API.
  Includes comprehensive logging, error handling, and graceful signal handling.

Usage:
  sudo ./update_dns_records.py

Notes:
  - This script requires root privileges.
  - Requires environment variables CF_API_TOKEN and CF_ZONE_ID (e.g., set them in /etc/environment).

Author: YourName | License: MIT | Version: 4.1.0
"""

import atexit
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime

# Third-party dependency check for requests
try:
    import requests
except ImportError:
    sys.stderr.write(
        "Error: The 'requests' library is required. Install it with 'pip install requests'.\n"
    )
    sys.exit(1)

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/update_dns_records.log"
DEFAULT_LOG_LEVEL = "INFO"

# Cloudflare API configuration from environment variables
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")

# IP checking services (fallbacks)
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


# ------------------------------------------------------------------------------
# Progress Indicator
# ------------------------------------------------------------------------------
class ConsoleSpinner:
    """Simple console spinner for progress indication."""

    def __init__(self, message: str):
        self.message = message
        self.spinning = True
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.thread = threading.Thread(target=self._spin)
        self.start_time = time.time()

    def _spin(self):
        while self.spinning:
            elapsed = time.time() - self.start_time
            sys.stdout.write(
                f"\r{self.spinner_chars[self.current]} {self.message} "
                f"[{elapsed:.1f}s elapsed]"
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
        sys.stdout.write("\r" + " " * (len(self.message) + 30) + "\r")
        sys.stdout.flush()


# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
def setup_logging():
    """Set up console and file logging."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Set up formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

    return logger


def print_section(title: str):
    """Print a section header."""
    border = "=" * 60
    logging.info(border)
    logging.info(f"  {title}")
    logging.info(border)


# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
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


def cleanup():
    """Perform cleanup tasks before exiting."""
    logging.info("Performing cleanup tasks before exit.")
    # No additional cleanup required for this script.


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency & Privilege Checks
# ------------------------------------------------------------------------------
def check_dependencies():
    """Check for required dependencies."""
    # 'requests' is already checked at import time.
    pass


def check_root():
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def validate_config():
    """Validate that required environment variables are set."""
    if not CF_API_TOKEN:
        logging.error(
            "Environment variable 'CF_API_TOKEN' is not set. Please set it (e.g., in /etc/environment)."
        )
        sys.exit(1)
    if not CF_ZONE_ID:
        logging.error(
            "Environment variable 'CF_ZONE_ID' is not set. Please set it (e.g., in /etc/environment)."
        )
        sys.exit(1)


# ------------------------------------------------------------------------------
# Helper & Utility Functions
# ------------------------------------------------------------------------------
def get_public_ip() -> str:
    """Retrieve the current public IP address using multiple fallback services."""
    for service_url in IP_SERVICES:
        try:
            logging.debug(f"Attempting to retrieve public IP from {service_url}")
            response = requests.get(service_url, timeout=10)
            response.raise_for_status()
            ip = response.text.strip()
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                logging.info(f"Successfully retrieved public IP from {service_url}")
                return ip
            else:
                logging.warning(
                    f"Invalid IPv4 format received from {service_url}: {ip}"
                )
        except Exception as e:
            logging.warning(f"Failed to retrieve public IP from {service_url}: {e}")
    logging.error("Failed to retrieve public IP address from all available services.")
    sys.exit(1)


def fetch_dns_records():
    """Fetch all DNS A records from Cloudflare."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "result" not in data:
            logging.error("Unexpected response from Cloudflare API.")
            sys.exit(1)
        return data["result"]
    except Exception as e:
        logging.error(f"Failed to fetch DNS records from Cloudflare: {e}")
        sys.exit(1)


def update_dns_record(record_id, record_name, current_ip, proxied):
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
    try:
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            error_msgs = [
                error.get("message", "Unknown error")
                for error in result.get("errors", [])
            ]
            logging.warning(
                f"Cloudflare API reported failure for record '{record_name}': {', '.join(error_msgs)}"
            )
            return False
        logging.info(f"Successfully updated DNS record '{record_name}'")
        return True
    except Exception as e:
        logging.warning(f"Failed to update DNS record '{record_name}': {e}")
        return False


# ------------------------------------------------------------------------------
# Main Functionality
# ------------------------------------------------------------------------------
def update_cloudflare_dns():
    """Update Cloudflare DNS A records with the current public IP address."""
    print_section("Starting Cloudflare DNS Update")

    # Retrieve current public IP
    logging.info("Fetching current public IP address...")
    with ConsoleSpinner("Retrieving public IP..."):
        current_ip = get_public_ip()
    logging.info(f"Current public IP: {current_ip}")

    # Fetch DNS records
    logging.info("Fetching DNS records from Cloudflare...")
    with ConsoleSpinner("Fetching DNS records..."):
        records = fetch_dns_records()
    logging.info(f"Found {len(records)} DNS records in the Cloudflare zone.")

    # Update records if needed
    errors = 0
    updates = 0
    for record in records:
        record_id = record.get("id")
        record_name = record.get("name")
        record_type = record.get("type")
        record_ip = record.get("content")
        proxied = record.get("proxied", False)

        if record_type == "A":
            if record_ip != current_ip:
                logging.info(
                    f"Updating DNS record '{record_name}': {record_ip} → {current_ip}"
                )
                if update_dns_record(record_id, record_name, current_ip, proxied):
                    updates += 1
                else:
                    errors += 1
            else:
                logging.debug(
                    f"No update needed for record '{record_name}' (current IP: {record_ip})"
                )

    # Summary of updates
    if errors > 0:
        logging.warning(
            f"DNS update completed with {errors} error(s) and {updates} successful update(s)."
        )
        return False
    elif updates > 0:
        logging.info(f"DNS update completed successfully with {updates} update(s).")
        return True
    else:
        logging.info("No DNS records needed updating.")
        return True


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    """Main entry point for updating Cloudflare DNS records."""
    setup_logging()
    check_dependencies()
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


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
