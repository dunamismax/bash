#!/usr/bin/env python3
"""
Script Name: universal_downloader.py
--------------------------------------------------------
Description:
  A robust universal downloader tool that lets the user choose between
  downloading with wget or yt-dlp on Ubuntu.

  For yt-dlp:
    - Prompts for a YouTube (video/playlist) link and a target download folder,
      creates it if needed, and downloads the media in highest quality,
      merging audio and video into an mp4 via ffmpeg.
  For wget:
    - Downloads the file into the specified directory.

Usage:
  sudo ./universal_downloader.py

Author: YourName | License: MIT | Version: 3.0.0
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/universal_downloader.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

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
    # Additional cleanup tasks can be added here


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["wget", "yt-dlp", "ffmpeg"]
    missing_commands = []

    for cmd in required_commands:
        if not shutil.which(cmd):
            missing_commands.append(cmd)

    if missing_commands:
        logging.warning(f"Missing dependencies: {', '.join(missing_commands)}")
        install_prerequisites(missing_commands)
    else:
        logging.info("All required dependencies are installed.")


def install_prerequisites(missing_commands=None):
    """
    Install missing dependencies.
    """
    if missing_commands is None:
        missing_commands = ["wget", "yt-dlp", "ffmpeg"]

    logging.info(f"Installing required tools: {', '.join(missing_commands)}")

    try:
        subprocess.run(["sudo", "apt", "update"], check=True, capture_output=True)
        subprocess.run(
            ["sudo", "apt", "install", "-y"] + missing_commands,
            check=True,
            capture_output=True,
        )
        logging.info("Required tools installed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install dependencies: {e}")
        sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def run_command(cmd, capture_output=False, check=True):
    """
    Run a shell command and handle errors.
    """
    logging.debug(f"Executing: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}\nError: {e}")
        sys.exit(e.returncode)


def ensure_directory(path):
    """
    Ensure the specified directory exists, creating it if necessary.
    """
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
            logging.info(f"Created directory: {path}")
        except Exception as e:
            logging.error(f"Failed to create directory '{path}': {e}")
            sys.exit(1)


# ------------------------------------------------------------------------------
# DOWNLOAD FUNCTIONS
# ------------------------------------------------------------------------------


def download_with_yt_dlp():
    """
    Download media using yt-dlp.
    """
    print_section("YouTube Downloader (yt-dlp)")

    # Prompt for YouTube link
    yt_link = input("\nEnter YouTube link (video or playlist): ").strip()
    if not yt_link:
        logging.error("YouTube link cannot be empty.")
        return

    # Prompt for download directory
    download_dir = input("Enter target download directory: ").strip()
    if not download_dir:
        logging.error("Download directory cannot be empty.")
        return

    ensure_directory(download_dir)

    # Build yt-dlp command
    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo+bestaudio",
        "--merge-output-format",
        "mp4",
        "-o",
        f"{download_dir}/%(title)s.%(ext)s",
        yt_link,
    ]

    logging.info("Starting download via yt-dlp...")
    run_command(cmd)
    logging.info("yt-dlp download completed successfully.")


def download_with_wget():
    """
    Download file using wget.
    """
    print_section("File Downloader (wget)")

    # Prompt for URL
    url = input("\nEnter URL to download: ").strip()
    if not url:
        logging.error("URL cannot be empty.")
        return

    # Prompt for download directory
    download_dir = input("Enter output directory: ").strip()
    if not download_dir:
        logging.error("Download directory cannot be empty.")
        return

    ensure_directory(download_dir)

    # Build wget command
    cmd = ["wget", "-P", download_dir, url]

    logging.info("Starting download via wget...")
    run_command(cmd)
    logging.info("wget download completed successfully.")


# ------------------------------------------------------------------------------
# INTERACTIVE MENU
# ------------------------------------------------------------------------------


def display_menu():
    """
    Display the interactive menu.
    """
    print_section("Universal Downloader")

    print("\nSelect Download Method:")
    if not DISABLE_COLORS:
        print(f"{NORD8}  1) wget - Download files from the web{NC}")
        print(f"{NORD8}  2) yt-dlp - Download YouTube videos or playlists{NC}")
        print(f"{NORD8}  q) Quit the application{NC}\n")
    else:
        print("  1) wget - Download files from the web")
        print("  2) yt-dlp - Download YouTube videos or playlists")
        print("  q) Quit the application\n")

    while True:
        choice = input("Enter your choice (1, 2, or q): ").strip().lower()

        if choice == "1":
            logging.info("User selected wget.")
            download_with_wget()
            break
        elif choice == "2":
            logging.info("User selected yt-dlp.")
            download_with_yt_dlp()
            break
        elif choice in ("q", "quit", "exit"):
            logging.info("User chose to quit.")
            sys.exit(0)
        else:
            logging.warning("Invalid selection. Please choose 1, 2, or q.")


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIVERSAL DOWNLOADER STARTED AT {now}")
    logging.info("=" * 80)

    display_menu()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIVERSAL DOWNLOADER COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
