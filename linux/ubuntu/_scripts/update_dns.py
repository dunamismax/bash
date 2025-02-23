#!/usr/bin/env python3
"""
update_dns_records.py
---------------------
Updates Cloudflare DNS A records with the current public IP address
using the Cloudflare API. Designed for Debian.

Usage:
    sudo ./update_dns_records.py [--help]

Notes:
    - This script requires root privileges.
    - Logs are stored at /var/log/update_dns_records.log by default.
    - Ensure that CF_API_TOKEN and CF_ZONE_ID are set in your environment.
      (e.g., in /etc/environment)
      
Author: Your Name | License: MIT | Version: 3.1
"""

import os
import sys
import argparse
import atexit
import signal
import re
from datetime import datetime

try:
    import requests
except ImportError:
    sys.stderr.write("Error: The 'requests' library is required. Install it with 'pip install requests'.\n")
    sys.exit(1)

# ------------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/update_dns_records.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
QUIET_MODE = False

# Cloudflare API configuration must be set as environment variables.
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTIONS
# ------------------------------------------------------------------------------
def get_log_level_num(level: str) -> int:
    level = level.upper()
    levels = {"VERBOSE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "WARNING": 3, "ERROR": 4, "CRITICAL": 5}
    return levels.get(level, 2)

def log(level: str, message: str):
    upper_level = level.upper()
    if get_log_level_num(upper_level) < get_log_level_num(LOG_LEVEL):
        return

    color = NC
    if not DISABLE_COLORS:
        if upper_level == "DEBUG":
            color = NORD9
        elif upper_level == "INFO":
            color = NORD14
        elif upper_level in ("WARN", "WARNING"):
            color = NORD13
        elif upper_level in ("ERROR", "CRITICAL"):
            color = NORD11

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{upper_level}] {message}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        sys.stderr.write(f"Log file write error: {e}\n")
    if not QUIET_MODE:
        sys.stderr.write(f"{color}{log_entry}{NC}\n")

def handle_error(message: str = "An unknown error occurred", exit_code: int = 1):
    log("ERROR", f"{message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")

atexit.register(cleanup)

def signal_handler(sig, frame):
    handle_error("Script interrupted by user.", exit_code=130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def check_dependencies():
    # For this Python version we use the requests library.
    pass  # (Already checked at the start.)

def validate_config():
    if not CF_API_TOKEN:
        handle_error("Environment variable 'CF_API_TOKEN' is not set. Please set it (e.g., in /etc/environment).")
    if not CF_ZONE_ID:
        handle_error("Environment variable 'CF_ZONE_ID' is not set. Please set it (e.g., in /etc/environment).")

def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Updates Cloudflare DNS A records with the current public IP address.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Only help option is needed.
    return parser.parse_args()

def get_public_ip() -> str:
    try:
        response = requests.get("https://api.ipify.org", timeout=10)
        response.raise_for_status()
        ip = response.text.strip()
    except Exception as e:
        handle_error(f"Failed to retrieve public IP address: {e}")
    if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
        handle_error(f"Invalid IPv4 address detected: {ip}")
    return ip

# ------------------------------------------------------------------------------
# MAIN FUNCTION: Update DNS Records
# ------------------------------------------------------------------------------
def update_dns_records():
    print_section("Starting Cloudflare DNS Update")
    log("INFO", "Fetching current public IP address...")
    current_ip = get_public_ip()
    log("INFO", f"Current public IP: {current_ip}")

    log("INFO", "Fetching DNS records from Cloudflare...")
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        handle_error(f"Failed to fetch DNS records from Cloudflare: {e}")

    if "result" not in data:
        handle_error("Unexpected response from Cloudflare API.")

    errors = 0
    for record in data["result"]:
        record_id = record.get("id")
        record_name = record.get("name")
        record_type = record.get("type")
        record_ip = record.get("content")
        proxied = record.get("proxied", False)

        if record_type == "A" and record_ip != current_ip:
            log("INFO", f"Updating DNS record '{record_name}': {record_ip} → {current_ip}")
            update_url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}"
            payload = {
                "type": "A",
                "name": record_name,
                "content": current_ip,
                "ttl": 1,
                "proxied": proxied
            }
            try:
                r2 = requests.put(update_url, headers=headers, json=payload, timeout=10)
                r2.raise_for_status()
                resp = r2.json()
                if not resp.get("success"):
                    log("WARN", f"Cloudflare API reported failure for DNS record '{record_name}'")
                    errors += 1
                else:
                    log("INFO", f"Successfully updated DNS record '{record_name}'")
            except Exception as e:
                log("WARN", f"Failed to update DNS record '{record_name}': {e}")
                errors += 1
        else:
            log("DEBUG", f"No update needed for record '{record_name}' (current IP: {record_ip})")
    if errors:
        handle_error(f"DNS update completed with {errors} error(s)")
    else:
        log("INFO", "DNS update completed successfully")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    parse_args()
    check_root()
    check_dependencies()
    validate_config()

    # Ensure log directory exists and secure the log file.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}: {e}")
    try:
        with open(LOG_FILE, "a") as f:
            pass
    except Exception as e:
        handle_error(f"Failed to create log file: {LOG_FILE}: {e}")
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to set permissions on {LOG_FILE}: {e}")

    log("INFO", "Script execution started.")
    update_dns_records()
    log("INFO", "Script execution finished successfully.")

if __name__ == "__main__":
    main()