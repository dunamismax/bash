#!/usr/bin/env python3
"""
Ubuntu VoIP Setup Script
------------------------
Description:
  A robust and visually engaging Ubuntu VoIP setup script that installs and configures
  the necessary packages and services for a VoIP system using Asterisk and MariaDB.
  The script uses the Nord color theme, detailed logging with log-level filtering,
  rich progress spinners for long-running tasks, strict error handling, and graceful
  signal handling.

Usage:
  sudo ./ubuntu_voip_setup.py

Author: YourName | License: MIT | Version: 3.2.1
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ubuntu_voip_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night
NORD1 = "\033[38;2;59;66;82m"  # Darker Polar Night
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
    Formatter that applies the Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with both console and file handlers.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO))
    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with Nord colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (plain text)
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
    Print a section header with Nord styling.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


def run_with_progress(description: str, func, *args, **kwargs):
    """
    Execute a blocking function in a background thread while displaying a rich spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
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
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Verify that all required system commands are available.
    """
    required_commands = ["apt-get", "systemctl", "ping", "ufw", "asterisk"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.error(
            f"Missing required commands: {', '.join(missing)}. Please install them and try again."
        )
        sys.exit(1)


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS FOR SYSTEM TASKS
# ------------------------------------------------------------------------------
def check_network_connectivity():
    """
    Check network connectivity by pinging a known host.
    """
    print_section("Checking Network Connectivity")
    logging.info("Verifying network connectivity...")
    try:
        subprocess.run(
            ["ping", "-c1", "-W5", "google.com"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info("Network connectivity OK.")
    except subprocess.CalledProcessError:
        logging.error("No network connectivity detected. Exiting.")
        sys.exit(1)


def apt_get_update():
    """Run apt-get update."""
    subprocess.run(["apt-get", "update", "-y"], check=True)


def apt_get_upgrade():
    """Run apt-get upgrade."""
    subprocess.run(["apt-get", "upgrade", "-y"], check=True)


def update_system():
    """
    Update and upgrade system packages.
    """
    print_section("Updating System")
    logging.info("Updating package repository...")
    try:
        run_with_progress("Updating package repository...", apt_get_update)
    except subprocess.CalledProcessError:
        logging.warning("apt-get update encountered issues. Continuing anyway...")

    logging.info("Upgrading installed packages...")
    try:
        run_with_progress("Upgrading packages...", apt_get_upgrade)
    except subprocess.CalledProcessError:
        logging.warning("apt-get upgrade encountered issues. Continuing anyway...")


def apt_get_install(packages: list):
    """
    Install the given list of packages.
    """
    subprocess.run(["apt-get", "install", "-y"] + packages, check=True)


def install_packages():
    """
    Install all required packages for the VoIP system.
    """
    print_section("Installing Required Packages")
    packages = [
        "bash",
        "vim",
        "nano",
        "git",
        "curl",
        "wget",
        "sudo",
        "screen",
        "tmux",
        "htop",
        "asterisk",
        "asterisk-config",
        "mariadb-server",
        "mariadb-client",
    ]
    logging.info(f"Installing {len(packages)} packages for the VoIP system...")
    try:
        run_with_progress("Installing packages...", apt_get_install, packages)
        logging.info("Successfully installed required packages.")
    except subprocess.CalledProcessError:
        logging.warning(
            "One or more packages failed to install. Some functionality may be limited."
        )

    logging.info("Enabling and starting Asterisk and MariaDB services...")
    for service in ["asterisk", "mariadb"]:
        try:
            subprocess.run(["systemctl", "enable", service], check=True)
            subprocess.run(["systemctl", "start", service], check=True)
            logging.info(f"Service '{service}' enabled and started successfully.")
        except subprocess.CalledProcessError:
            logging.warning(f"Failed to enable/start '{service}' service.")


def create_asterisk_user():
    """
    Create the 'asterisk' user if it does not already exist.
    """
    print_section("Creating Asterisk User")
    try:
        subprocess.run(
            ["id", "asterisk"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info("'asterisk' user already exists.")
    except subprocess.CalledProcessError:
        logging.info("Creating 'asterisk' user...")
        try:
            subprocess.run(["useradd", "-m", "-s", "/bin/bash", "asterisk"], check=True)
            logging.info("'asterisk' user created successfully.")
        except subprocess.CalledProcessError:
            logging.warning(
                "Failed to create 'asterisk' user. Using system defaults for Asterisk."
            )


def configure_asterisk():
    """
    Configure Asterisk for wideband G.722 audio and basic SIP endpoints.
    """
    print_section("Configuring Asterisk")
    logging.info("Configuring Asterisk for G.722 wideband audio...")
    ast_config_dir = "/etc/asterisk"
    try:
        os.makedirs(ast_config_dir, exist_ok=True)
    except Exception as e:
        logging.error(
            f"Failed to create Asterisk config directory '{ast_config_dir}': {e}"
        )
        sys.exit(1)

    # Create SIP configuration
    sip_conf = os.path.join(ast_config_dir, "sip_custom.conf")
    sip_conf_content = "[general]\ndisallow=all\nallow=g722\n; allow=ulaw\n"
    try:
        with open(sip_conf, "w") as f:
            f.write(sip_conf_content)
        logging.info(f"Created SIP configuration at '{sip_conf}'.")
    except Exception as e:
        logging.error(f"Failed to write SIP configuration: {e}")
        sys.exit(1)

    # Create extensions configuration
    ext_conf = os.path.join(ast_config_dir, "extensions_custom.conf")
    ext_conf_content = (
        "[internal]\n"
        "exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})\n"
        " same => n,Dial(SIP/${EXTEN},20)\n"
        " same => n,Hangup()\n\n"
        "[default]\n"
        "exten => s,1,Answer()\n"
        " same => n,Playback(hello-world)\n"
        " same => n,Hangup()\n"
    )
    try:
        with open(ext_conf, "w") as f:
            f.write(ext_conf_content)
        logging.info(f"Created basic dialplan at '{ext_conf}'.")
    except Exception as e:
        logging.error(f"Failed to write dialplan: {e}")
        sys.exit(1)

    # Append sample SIP endpoints to SIP configuration
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
        logging.info(f"Added sample SIP endpoints to '{sip_conf}'.")
    except Exception as e:
        logging.error(f"Failed to append SIP endpoints: {e}")
        sys.exit(1)

    # Reload Asterisk configuration
    try:
        subprocess.run(["asterisk", "-rx", "core reload"], check=True)
        logging.info("Asterisk configuration reloaded successfully.")
    except subprocess.CalledProcessError:
        logging.warning(
            "Failed to reload Asterisk configuration. A manual reload may be required."
        )


def configure_ufw():
    """
    Configure UFW firewall rules for SIP and RTP traffic.
    """
    print_section("Configuring UFW Firewall")
    logging.info("Setting UFW firewall rules for SIP and RTP...")
    if not shutil.which("ufw"):
        logging.warning("UFW not found. Skipping firewall configuration.")
        return

    try:
        subprocess.run(["ufw", "allow", "5060/udp"], check=True)
        logging.info("Allowed SIP traffic on UDP port 5060.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to configure SIP traffic rule on UFW.")

    try:
        subprocess.run(["ufw", "allow", "16384:32767/udp"], check=True)
        logging.info("Allowed RTP traffic on UDP ports 16384-32767.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to configure RTP traffic rule on UFW.")

    try:
        subprocess.run(["ufw", "reload"], check=True)
        logging.info("UFW firewall rules reloaded successfully.")
    except subprocess.CalledProcessError:
        logging.warning("Failed to reload UFW firewall rules.")


def final_checks():
    """
    Perform final system checks and display status information.
    """
    print_section("Final System Checks")
    logging.info("Performing final system checks...")

    try:
        desc = (
            subprocess.check_output(["lsb_release", "-d"], text=True)
            .split(":", 1)[1]
            .strip()
        )
        logging.info(f"Ubuntu version: {desc}")
    except Exception as e:
        logging.warning(f"Failed to retrieve Ubuntu version: {e}")

    for service in ["asterisk", "mariadb"]:
        logging.info(f"Checking {service} service status:")
        try:
            output = subprocess.check_output(
                ["systemctl", "status", service, "--no-pager"],
                stderr=subprocess.STDOUT,
                text=True,
            )
            active_line = next(
                (line for line in output.splitlines() if "Active:" in line),
                "Status not found",
            )
            logging.info(f"{service.capitalize()} status: {active_line.strip()}")
        except subprocess.CalledProcessError as e:
            logging.warning(f"Failed to check {service} status: {e}")

    try:
        output = subprocess.check_output(["df", "-h", "/"], text=True)
        header, usage = output.strip().split("\n")[:2]
        logging.info(f"Disk usage (root): {usage.split()[4]} used")
    except Exception as e:
        logging.warning(f"Failed to check disk space: {e}")


def auto_reboot():
    """
    Automatically reboot the system to apply all changes.
    """
    print_section("Auto Reboot")
    logging.info("Rebooting system in 10 seconds to apply changes...")
    logging.info("Press Ctrl+C to cancel reboot if needed.")
    try:
        for i in range(10, 0, -1):
            logging.info(f"Rebooting in {i} seconds...")
            time.sleep(1)
        logging.info("Executing reboot now.")
        subprocess.run(["reboot"], check=True)
    except KeyboardInterrupt:
        logging.info("Reboot cancelled by user. Manual reboot is recommended.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Reboot failed: {e}")
        sys.exit(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the Ubuntu VoIP setup.
    """
    if sys.version_info < (3, 6):
        print(
            f"{NORD11}ERROR: This script requires Python 3.6 or higher.{NC}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create log directory if needed
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(
                f"{NORD11}ERROR: Failed to create log directory '{log_dir}': {e}{NC}",
                file=sys.stderr,
            )
            sys.exit(1)

    setup_logging()
    check_root()
    check_dependencies()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UBUNTU VOIP SETUP STARTED AT {now}")
    logging.info("=" * 80)

    # Execute setup tasks with progress where applicable
    check_network_connectivity()
    update_system()
    install_packages()
    create_asterisk_user()
    configure_asterisk()
    configure_ufw()
    final_checks()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UBUNTU VOIP SETUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

    auto_reboot()


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
