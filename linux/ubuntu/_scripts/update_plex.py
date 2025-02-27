#!/usr/bin/env python3
"""
Script Name: update_plex.py
--------------------------------------------------------
Description:
  Downloads and installs the latest Plex Media Server package,
  fixes dependency issues, cleans up temporary files, and restarts
  the Plex service. Uses only standard library modules.

Usage:
  sudo ./update_plex.py [--plex-url <url>]

Author: Your Name | License: MIT | Version: 1.0.0
"""

import atexit
import argparse
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

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    """Nord-themed ANSI color codes."""

    HEADER = "\033[38;5;81m"  # Nord9
    GREEN = "\033[38;5;82m"  # Nord14
    YELLOW = "\033[38;5;226m"  # Nord13
    RED = "\033[38;5;196m"  # Nord11
    BLUE = "\033[38;5;39m"  # Nord8
    BOLD = "\033[1m"
    ENDC = "\033[0m"


def print_section(title: str) -> None:
    """Log a formatted section header."""
    border = f"{Colors.BLUE}{'─' * 60}{Colors.ENDC}"
    logging.info(border)
    logging.info(f"  {Colors.BOLD}{title}{Colors.ENDC}")
    logging.info(border)


#####################################
# Configuration
#####################################

# Default Plex package URL (can be overridden via CLI)
DEFAULT_PLEX_URL: str = (
    "https://downloads.plex.tv/plex-media-server-new/"
    "1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
)
# Temporary file to store downloaded package
TEMP_DEB: str = "/tmp/plexmediaserver.deb"
# Log file location
LOG_FILE: str = "/var/log/update_plex.log"
DEFAULT_LOG_LEVEL = logging.INFO

#####################################
# Logging Setup
#####################################


def setup_logging() -> logging.Logger:
    """Set up logging with both console and file handlers."""
    log_dir: str = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(DEFAULT_LOG_LEVEL)
    # Remove any existing handlers
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
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

    return logger


#####################################
# Signal Handling & Cleanup
#####################################


def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
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

#####################################
# Dependency & Privilege Checks
#####################################


def check_dependencies() -> None:
    """
    Ensure required system commands are available.
    Required commands: dpkg, apt-get, systemctl.
    """
    required_commands: List[str] = ["dpkg", "apt-get", "systemctl"]
    missing: List[str] = []
    for cmd in required_commands:
        try:
            subprocess.run(
                ["which", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError:
            missing.append(cmd)
    if missing:
        logging.error(
            f"Missing required commands: {', '.join(missing)}. Please install them and try again."
        )
        sys.exit(1)


def check_root() -> None:
    """Ensure the script is executed with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


#####################################
# Helper Functions
#####################################


def run_command(
    cmd: List[str], check: bool = True, capture_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Execute a shell command and log its output.

    Args:
        cmd: Command to execute.
        check: Raise error on non-zero exit.
        capture_output: Capture stdout/stderr.

    Returns:
        subprocess.CompletedProcess instance.
    """
    log_cmd = " ".join(cmd)
    logging.info(f"Executing command: {log_cmd}")
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=True
        )
        if result.stdout:
            logging.info(f"Command output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed [{e.returncode}]: {log_cmd}")
        if e.stdout:
            logging.debug(f"Stdout: {e.stdout}")
        if e.stderr:
            logging.error(f"Stderr: {e.stderr}")
        if check:
            raise
        return e


#####################################
# Plex Update Functions
#####################################


def download_plex(plex_url: str) -> None:
    """
    Download the Plex Media Server package using urllib.

    Args:
        plex_url: URL to download the Plex package from.
    """
    print_section("Downloading Plex Media Server Package")
    logging.info("Starting Plex package download...")
    logging.info(f"Downloading from: {plex_url}")
    logging.info(f"Saving to: {TEMP_DEB}")

    os.makedirs(os.path.dirname(TEMP_DEB), exist_ok=True)
    try:
        start_time = time.time()
        urllib.request.urlretrieve(plex_url, TEMP_DEB)
        download_time = time.time() - start_time
        file_size = os.path.getsize(TEMP_DEB)
        logging.info(f"Download completed in {download_time:.2f} seconds")
        logging.info(f"File size: {file_size / (1024 * 1024):.2f} MB")
    except Exception as e:
        logging.error(f"Failed to download Plex package: {e}")
        sys.exit(1)


def install_plex() -> None:
    """
    Install the Plex Media Server package and fix dependency issues if necessary.
    """
    print_section("Installing Plex Media Server")
    logging.info("Installing Plex Media Server...")
    try:
        run_command(["dpkg", "-i", TEMP_DEB])
    except subprocess.CalledProcessError:
        logging.warning("Dependency issues detected. Attempting to fix dependencies...")
        try:
            run_command(["apt-get", "install", "-f", "-y"])
            run_command(["dpkg", "-i", TEMP_DEB])
        except subprocess.CalledProcessError:
            logging.error("Failed to resolve dependencies for Plex.")
            sys.exit(1)
    logging.info("Plex Media Server installed successfully.")


def restart_plex() -> None:
    """
    Restart the Plex Media Server service.
    """
    print_section("Restarting Plex Media Server Service")
    logging.info("Restarting Plex Media Server...")
    try:
        run_command(["systemctl", "restart", "plexmediaserver"])
        logging.info("Plex Media Server service restarted successfully.")
    except subprocess.CalledProcessError:
        logging.error("Failed to restart Plex Media Server service.")
        sys.exit(1)


#####################################
# CLI Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Optional argument:
      --plex-url : Override the default Plex package URL.
    """
    parser = argparse.ArgumentParser(
        description="Update Plex Media Server: Download, install, and restart Plex."
    )
    parser.add_argument(
        "--plex-url",
        type=str,
        default=DEFAULT_PLEX_URL,
        help="URL to download the Plex package (default: use built-in URL)",
    )
    return parser.parse_args()


#####################################
# Main Function
#####################################


def main() -> None:
    setup_logging()
    check_dependencies()
    check_root()

    args = parse_arguments()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE STARTED AT {now}")
    logging.info("=" * 80)

    download_plex(args.plex_url)
    install_plex()
    restart_plex()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PLEX UPDATE COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}", exc_info=True)
        sys.exit(1)
