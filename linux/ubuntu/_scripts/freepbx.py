#!/usr/bin/env python3
"""
Script Name: ubuntu_voip_setup.py
Description: A robust, visually engaging Ubuntu VoIP setup script using the Nord
             color theme, with strict error handling, log-level filtering,
             colorized output, and graceful signal traps.
Author: YourName | License: MIT | Version: 3.2
Usage:
  sudo ./ubuntu_voip_setup.py
Notes:
  - This script requires root privileges.
  - Logs are stored at /var/log/ubuntu_voip_setup.log by default.
"""

import os
import sys
import subprocess
import logging
import signal
import atexit
import time
import shutil

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ubuntu_voip_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9 = '\033[38;2;129;161;193m'    # Bluish (for DEBUG)
NORD10 = '\033[38;2;94;129;172m'     # Accent Blue
NORD11 = '\033[38;2;191;97;106m'     # Reddish (for ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'    # Yellowish (for WARN)
NORD14 = '\033[38;2;163;190;140m'    # Greenish (for INFO)
NC = '\033[0m'                     # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": NORD9,
        "INFO": NORD14,
        "WARNING": NORD13,
        "ERROR": NORD11,
        "CRITICAL": NORD11,
    }
    def format(self, record):
        message = super().format(record)
        if not DISABLE_COLORS:
            color = self.LEVEL_COLORS.get(record.levelname, NC)
            message = f"{color}{message}{NC}"
        return message

def setup_logging():
    logger = logging.getLogger()
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)
    
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                  "%Y-%m-%d %H:%M:%S")
    
    # File handler (plain text)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler (colorized)
    console_handler = logging.StreamHandler(sys.stderr)
    console_formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Secure the log file
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on {LOG_FILE}: {e}")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An unknown error occurred.", exit_code=1):
    logging.error(f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)

atexit.register(cleanup)

def signal_handler(signum, frame):
    handle_error(f"Script interrupted by signal {signum}.", exit_code=128+signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title):
    border = "─" * 60
    logging.info(f"{NORD10}{border}{NC}")
    logging.info(f"{NORD10}  {title}{NC}")
    logging.info(f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
def check_network():
    print_section("Checking Network Connectivity")
    logging.info("Verifying network connectivity...")
    try:
        subprocess.run(["ping", "-c1", "-W5", "google.com"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("Network connectivity OK.")
    except subprocess.CalledProcessError:
        handle_error("No network connectivity detected. Exiting.")

def update_system():
    print_section("Updating System")
    logging.info("Updating package repository...")
    try:
        subprocess.run(["apt-get", "update", "-y"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("apt-get update encountered issues.")
    logging.info("Upgrading installed packages...")
    try:
        subprocess.run(["apt-get", "upgrade", "-y"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("apt-get upgrade encountered issues.")

def install_packages():
    print_section("Installing Required Packages")
    packages = [
        "bash", "vim", "nano", "git", "curl", "wget", "sudo", "screen", "tmux", "htop",
        "asterisk", "asterisk-config",
        "mariadb-server", "mariadb-client"
    ]
    logging.info("Installing required packages for the VoIP system...")
    try:
        subprocess.run(["apt-get", "install", "-y"] + packages, check=True)
    except subprocess.CalledProcessError:
        logging.warning("One or more packages failed to install.")
    logging.info("Enabling and starting Asterisk and MariaDB services...")
    for service in ["asterisk", "mariadb"]:
        try:
            subprocess.run(["systemctl", "enable", service], check=True)
            subprocess.run(["systemctl", "start", service], check=True)
        except subprocess.CalledProcessError:
            logging.warning(f"Failed to enable/start {service} service.")

def create_asterisk_user():
    print_section("Creating Asterisk User")
    # Check if user 'asterisk' exists
    try:
        subprocess.run(["id", "asterisk"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("'asterisk' user already exists.")
    except subprocess.CalledProcessError:
        logging.info("Creating 'asterisk' user...")
        try:
            subprocess.run(["useradd", "-m", "-s", "/bin/bash", "asterisk"], check=True)
        except subprocess.CalledProcessError:
            logging.warning("Failed to create 'asterisk' user.")

def configure_asterisk():
    print_section("Configuring Asterisk")
    logging.info("Configuring Asterisk for G.722 wideband audio...")
    ast_config_dir = "/etc/asterisk"
    try:
        os.makedirs(ast_config_dir, exist_ok=True)
    except Exception as e:
        handle_error(f"Failed to create Asterisk config directory: {ast_config_dir}. Error: {e}")
    
    sip_conf = os.path.join(ast_config_dir, "sip_custom.conf")
    sip_conf_content = (
        "[general]\n"
        "; Disable all codecs first\n"
        "disallow=all\n"
        "; Allow high-quality wideband G.722 codec\n"
        "allow=g722\n"
        "; (Optional fallback: allow ulaw for legacy endpoints)\n"
        "; allow=ulaw\n"
    )
    try:
        with open(sip_conf, "w") as f:
            f.write(sip_conf_content)
        logging.info(f"Created SIP configuration at {sip_conf}.")
    except Exception as e:
        handle_error(f"Failed to write SIP configuration: {e}")

    ext_conf = os.path.join(ast_config_dir, "extensions_custom.conf")
    ext_conf_content = (
        "[internal]\n"
        "; Simple dialplan: dial a SIP endpoint (assumes endpoints are named by extension number)\n"
        "exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})\n"
        " same => n,Dial(SIP/${EXTEN},20)\n"
        " same => n,Hangup()\n\n"
        "[default]\n"
        "; Fallback context plays a greeting message\n"
        "exten => s,1,Answer()\n"
        " same => n,Playback(hello-world)\n"
        " same => n,Hangup()\n"
    )
    try:
        with open(ext_conf, "w") as f:
            f.write(ext_conf_content)
        logging.info(f"Created basic dialplan at {ext_conf}.")
    except Exception as e:
        handle_error(f"Failed to write dialplan: {e}")
    
    # Append sample SIP endpoints to sip_custom.conf
    endpoints = (
        "\n[6001]\n"
        "type=friend\n"
        "context=internal\n"
        "host=dynamic\n"
        "secret=changeme6001\n"
        "callerid=Phone 6001 <6001>\n"
        "disallow=all\n"
        "allow=g722\n\n"
        "[6002]\n"
        "type=friend\n"
        "context=internal\n"
        "host=dynamic\n"
        "secret=changeme6002\n"
        "callerid=Phone 6002 <6002>\n"
        "disallow=all\n"
        "allow=g722\n"
    )
    try:
        with open(sip_conf, "a") as f:
            f.write(endpoints)
        logging.info(f"Added sample SIP endpoints to {sip_conf}.")
    except Exception as e:
        handle_error(f"Failed to append SIP endpoints: {e}")
    
    # Reload Asterisk configuration (assumes Asterisk is running)
    try:
        subprocess.run(["asterisk", "-rx", "core reload"], check=True)
        logging.info("Asterisk configuration reloaded successfully.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to reload Asterisk configuration.")

def configure_ufw():
    print_section("Configuring UFW Firewall")
    logging.info("Setting UFW firewall rules for SIP and RTP...")
    try:
        subprocess.run(["ufw", "allow", "5060/udp"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("Failed to allow SIP traffic on UFW.")
    try:
        subprocess.run(["ufw", "allow", "16384:32767/udp"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("Failed to allow RTP traffic on UFW.")
    try:
        subprocess.run(["ufw", "reload"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("Failed to reload UFW firewall.")
    logging.info("UFW firewall rules updated for SIP and RTP.")

def final_checks():
    print_section("Final System Checks")
    logging.info("Performing final system checks...")
    try:
        desc = subprocess.check_output(["lsb_release", "-d"], text=True).split(":", 1)[1].strip()
        logging.info(f"Ubuntu version: {desc}")
    except Exception as e:
        logging.warning(f"Failed to retrieve Ubuntu version: {e}")
    logging.info("Asterisk status:")
    subprocess.run(["systemctl", "status", "asterisk", "--no-pager"])
    logging.info("MariaDB status:")
    subprocess.run(["systemctl", "status", "mariadb", "--no-pager"])
    subprocess.run(["df", "-h", "/"])

def auto_reboot():
    print_section("Auto Reboot")
    logging.info("Rebooting system now to apply all changes...")
    try:
        subprocess.run(["reboot"], check=True)
    except subprocess.CalledProcessError as e:
        handle_error(f"Reboot failed: {e}")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    # Ensure the script is run with Bash (original script check) – here we simply check Python version.
    if sys.version_info < (3, 6):
        print(f"{NORD11}ERROR: This script requires Python 3.6 or higher.{NC}", file=sys.stderr)
        sys.exit(1)
    
    check_root()
    
    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}. Error: {e}")
    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to create or set permissions on log file: {LOG_FILE}. Error: {e}")
    
    setup_logging()
    logging.info("Script execution started.")
    
    check_network()
    update_system()
    install_packages()
    create_asterisk_user()
    configure_asterisk()
    configure_ufw()
    final_checks()
    auto_reboot()
    
    logging.info("Script execution finished successfully.")

if __name__ == "__main__":
    main()