#!/usr/bin/env python3
"""
Script Name: ubuntu_voip_setup.py
--------------------------------------------------------
Description:
  A robust, visually engaging Ubuntu VoIP setup script using the Nord
  color theme, with strict error handling, log-level filtering,
  colorized output, and graceful signal handling.

Usage:
  sudo ./ubuntu_voip_setup.py

Author: YourName | License: MIT | Version: 3.2.1
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ubuntu_voip_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0  = '\033[38;2;46;52;64m'     # Polar Night (dark)
NORD1  = '\033[38;2;59;66;82m'     # Polar Night (darker than NORD0)
NORD8  = '\033[38;2;136;192;208m'  # Frost (light blue)
NORD9  = '\033[38;2;129;161;193m'  # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'   # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'   # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'  # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

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

        if levelname == 'DEBUG':
            return f"{NORD9}{msg}{NC}"
        elif levelname == 'INFO':
            return f"{NORD14}{msg}{NC}"
        elif levelname == 'WARNING':
            return f"{NORD13}{msg}{NC}"
        elif levelname in ('ERROR', 'CRITICAL'):
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
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
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
    # Additional cleanup tasks can be added here

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------

def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["apt-get", "systemctl", "ping", "ufw"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(f"The '{cmd}' command is not found in your PATH. Please install it and try again.")
            sys.exit(1)

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

def check_network():
    """
    Check network connectivity to ensure package downloads will work.
    """
    print_section("Checking Network Connectivity")
    logging.info("Verifying network connectivity...")
    try:
        subprocess.run(["ping", "-c1", "-W5", "google.com"], check=True,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("Network connectivity OK.")
    except subprocess.CalledProcessError:
        logging.error("No network connectivity detected. Exiting.")
        sys.exit(1)

def update_system():
    """
    Update system packages to ensure we have the latest versions.
    """
    print_section("Updating System")
    logging.info("Updating package repository...")
    try:
        subprocess.run(["apt-get", "update", "-y"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("apt-get update encountered issues. Continuing anyway...")
    
    logging.info("Upgrading installed packages...")
    try:
        subprocess.run(["apt-get", "upgrade", "-y"], check=True)
    except subprocess.CalledProcessError:
        logging.warning("apt-get upgrade encountered issues. Continuing anyway...")

# ------------------------------------------------------------------------------
# VOIP SETUP FUNCTIONS
# ------------------------------------------------------------------------------

def install_packages():
    """
    Install all required packages for the VoIP system.
    """
    print_section("Installing Required Packages")
    packages = [
        "bash", "vim", "nano", "git", "curl", "wget", "sudo", "screen", "tmux", "htop",
        "asterisk", "asterisk-config",
        "mariadb-server", "mariadb-client"
    ]
    logging.info(f"Installing {len(packages)} required packages for the VoIP system...")
    try:
        subprocess.run(["apt-get", "install", "-y"] + packages, check=True)
        logging.info("Successfully installed all packages.")
    except subprocess.CalledProcessError:
        logging.warning("One or more packages failed to install. Some functionality may be limited.")
    
    logging.info("Enabling and starting Asterisk and MariaDB services...")
    for service in ["asterisk", "mariadb"]:
        try:
            subprocess.run(["systemctl", "enable", service], check=True)
            subprocess.run(["systemctl", "start", service], check=True)
            logging.info(f"Service {service} enabled and started successfully.")
        except subprocess.CalledProcessError:
            logging.warning(f"Failed to enable/start {service} service. VoIP functionality may be limited.")

def create_asterisk_user():
    """
    Create the Asterisk user account if it doesn't already exist.
    """
    print_section("Creating Asterisk User")
    # Check if user 'asterisk' exists
    try:
        subprocess.run(["id", "asterisk"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("'asterisk' user already exists.")
    except subprocess.CalledProcessError:
        logging.info("Creating 'asterisk' user...")
        try:
            subprocess.run(["useradd", "-m", "-s", "/bin/bash", "asterisk"], check=True)
            logging.info("'asterisk' user created successfully.")
        except subprocess.CalledProcessError:
            logging.warning("Failed to create 'asterisk' user. Using system default user for Asterisk.")

def configure_asterisk():
    """
    Configure Asterisk for G.722 wideband audio and basic SIP endpoints.
    """
    print_section("Configuring Asterisk")
    logging.info("Configuring Asterisk for G.722 wideband audio...")
    ast_config_dir = "/etc/asterisk"
    try:
        os.makedirs(ast_config_dir, exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create Asterisk config directory: {ast_config_dir}. Error: {e}")
        sys.exit(1)
    
    # Create SIP configuration
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
        logging.error(f"Failed to write SIP configuration: {e}")
        sys.exit(1)

    # Create extensions configuration
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
        logging.error(f"Failed to write dialplan: {e}")
        sys.exit(1)
    
    # Add sample SIP endpoints
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
        logging.error(f"Failed to append SIP endpoints: {e}")
        sys.exit(1)
    
    # Reload Asterisk configuration (assumes Asterisk is running)
    try:
        subprocess.run(["asterisk", "-rx", "core reload"], check=True)
        logging.info("Asterisk configuration reloaded successfully.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to reload Asterisk configuration. A manual reload may be required.")

def configure_ufw():
    """
    Configure UFW firewall for SIP and RTP traffic.
    """
    print_section("Configuring UFW Firewall")
    logging.info("Setting UFW firewall rules for SIP and RTP...")
    
    # Check if UFW is installed and enabled
    if not shutil.which("ufw"):
        logging.warning("UFW not found. Skipping firewall configuration.")
        return
        
    # Add rules for SIP traffic
    try:
        subprocess.run(["ufw", "allow", "5060/udp"], check=True)
        logging.info("UFW rule added: SIP traffic (UDP 5060) allowed.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to allow SIP traffic on UFW.")
    
    # Add rules for RTP traffic
    try:
        subprocess.run(["ufw", "allow", "16384:32767/udp"], check=True)
        logging.info("UFW rule added: RTP traffic (UDP 16384-32767) allowed.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to allow RTP traffic on UFW.")
    
    # Reload UFW
    try:
        subprocess.run(["ufw", "reload"], check=True)
        logging.info("UFW firewall rules reloaded successfully.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to reload UFW firewall.")

def final_checks():
    """
    Perform final system checks and display status information.
    """
    print_section("Final System Checks")
    logging.info("Performing final system checks...")
    
    # Check Ubuntu version
    try:
        desc = subprocess.check_output(["lsb_release", "-d"], text=True).split(":", 1)[1].strip()
        logging.info(f"Ubuntu version: {desc}")
    except Exception as e:
        logging.warning(f"Failed to retrieve Ubuntu version: {e}")
    
    # Check Asterisk service status
    logging.info("Checking Asterisk service status:")
    try:
        output = subprocess.check_output(["systemctl", "status", "asterisk", "--no-pager"], 
                                         stderr=subprocess.STDOUT, text=True)
        active_line = [line for line in output.split('\n') if 'Active:' in line]
        if active_line:
            logging.info(f"Asterisk status: {active_line[0].strip()}")
        else:
            logging.info("Asterisk status: Not found in systemctl output")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to check Asterisk status: {e}")
    
    # Check MariaDB service status
    logging.info("Checking MariaDB service status:")
    try:
        output = subprocess.check_output(["systemctl", "status", "mariadb", "--no-pager"], 
                                         stderr=subprocess.STDOUT, text=True)
        active_line = [line for line in output.split('\n') if 'Active:' in line]
        if active_line:
            logging.info(f"MariaDB status: {active_line[0].strip()}")
        else:
            logging.info("MariaDB status: Not found in systemctl output")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to check MariaDB status: {e}")
    
    # Check disk space
    logging.info("Checking disk space:")
    try:
        output = subprocess.check_output(["df", "-h", "/"], text=True)
        header, values = output.strip().split('\n')
        logging.info(f"Disk usage (root): {values.split()[4]} used")
    except Exception as e:
        logging.warning(f"Failed to check disk space: {e}")

def auto_reboot():
    """
    Automatically reboot the system to apply all changes.
    """
    print_section("Auto Reboot")
    logging.info("Rebooting system in 10 seconds to apply all changes...")
    logging.info("Press Ctrl+C to cancel reboot if needed.")
    
    try:
        # Wait 10 seconds before rebooting to allow user to cancel if needed
        for i in range(10, 0, -1):
            logging.info(f"Rebooting in {i} seconds...")
            time.sleep(1)
        
        logging.info("Executing reboot now.")
        subprocess.run(["reboot"], check=True)
    except KeyboardInterrupt:
        logging.info("Reboot cancelled by user. Manual reboot recommended.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Reboot failed: {e}")
        sys.exit(1)

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for the script.
    """
    # Ensure the script is run with Python 3.6+
    if sys.version_info < (3, 6):
        print(f"{NORD11}ERROR: This script requires Python 3.6 or higher.{NC}", file=sys.stderr)
        sys.exit(1)
    
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"{NORD11}ERROR: Failed to create log directory: {log_dir}. Error: {e}{NC}", file=sys.stderr)
            sys.exit(1)
    
    setup_logging()
    check_root()
    check_dependencies()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UBUNTU VOIP SETUP STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main functions
    check_network()
    update_system()
    install_packages()
    create_asterisk_user()
    configure_asterisk()
    configure_ufw()
    final_checks()
    
    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UBUNTU VOIP SETUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)
    
    # Reboot to apply changes
    auto_reboot()

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)