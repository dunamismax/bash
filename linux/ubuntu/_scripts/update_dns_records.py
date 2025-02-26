#!/usr/bin/env python3
"""
Script Name: update_dns_records.py
--------------------------------------------------------
Description:
  Updates Cloudflare DNS A records with the current public IP address
  using the Cloudflare API. Uses the Nord color theme for visual feedback
  and includes comprehensive logging and error handling.

Usage:
  sudo ./update_dns_records.py

Notes:
  - This script requires root privileges.
  - Requires environment variables CF_API_TOKEN and CF_ZONE_ID.
  - Set them in /etc/environment for system-wide availability.

Author: YourName | License: MIT | Version: 4.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime

# Third-party dependencies
try:
    import requests
except ImportError:
    sys.stderr.write(
        "Error: The 'requests' library is required. Install it with 'pip install requests'.\n"
    )
    sys.exit(1)

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/update_dns_records.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# Cloudflare API configuration
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")

# IP checking services (fallbacks in case one fails)
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------


class NordColorFormatter(logging.Formatter):
    """
    A custom formatter that applies Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)

        if not self.use_colors:
            return msg

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord theme styling.
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------


def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # No specific cleanup required for this script


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    # Already checked for the 'requests' library at the top
    pass


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def validate_config():
    """
    Validate that required environment variables are set.
    """
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


def get_public_ip() -> str:
    """
    Get the current public IP address using multiple services for redundancy.
    """
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
                    f"Invalid IPv4 address format received from {service_url}: {ip}"
                )
        except Exception as e:
            logging.warning(f"Failed to retrieve public IP from {service_url}: {e}")

    # If all services fail
    logging.error("Failed to retrieve public IP address from all available services.")
    sys.exit(1)


def fetch_dns_records():
    """
    Fetch all DNS A records from Cloudflare.
    """
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
    """
    Update a single DNS record with the new IP address.
    """
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
                f"Cloudflare API reported failure for DNS record '{record_name}': {', '.join(error_msgs)}"
            )
            return False

        logging.info(f"Successfully updated DNS record '{record_name}'")
        return True
    except Exception as e:
        logging.warning(f"Failed to update DNS record '{record_name}': {e}")
        return False


# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------


def update_cloudflare_dns():
    """
    Update Cloudflare DNS A records with the current public IP.
    """
    print_section("Starting Cloudflare DNS Update")

    # Get current public IP
    logging.info("Fetching current public IP address...")
    current_ip = get_public_ip()
    logging.info(f"Current public IP: {current_ip}")

    # Fetch DNS records from Cloudflare
    logging.info("Fetching DNS records from Cloudflare...")
    records = fetch_dns_records()
    logging.info(f"Found {len(records)} DNS records in Cloudflare zone")

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

    # Summary
    if errors > 0:
        logging.warning(
            f"DNS update completed with {errors} error(s) and {updates} successful update(s)"
        )
        return False
    elif updates > 0:
        logging.info(f"DNS update completed successfully with {updates} update(s)")
        return True
    else:
        logging.info("No DNS records needed updating")
        return True


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    logger = setup_logging()
    check_dependencies()
    check_root()
    validate_config()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"DNS UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main function
    success = update_cloudflare_dns()

    # Finish up
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
