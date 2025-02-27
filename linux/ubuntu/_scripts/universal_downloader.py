#!/usr/bin/env python3
"""
Universal Downloader Script
---------------------------
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
import threading
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/universal_downloader.log"
DEFAULT_LOG_LEVEL = "INFO"


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

    # Console handler
    console_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(console_formatter)
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
    """Gracefully handle termination signals."""
    sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)


def cleanup():
    """Perform cleanup tasks before exit."""
    logging.info("Performing cleanup tasks before exit.")
    # Add additional cleanup steps here if needed.


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# Dependency Checks
# ------------------------------------------------------------------------------
def check_dependencies():
    """Check if required commands are available."""
    required_commands = ["wget", "yt-dlp", "ffmpeg"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.warning(f"Missing dependencies: {', '.join(missing)}")
        install_prerequisites(missing)
    else:
        logging.info("All required dependencies are installed.")


def install_prerequisites(missing_commands=None):
    """Attempt to install missing dependencies via apt."""
    if missing_commands is None:
        missing_commands = ["wget", "yt-dlp", "ffmpeg"]
    logging.info(f"Installing missing tools: {', '.join(missing_commands)}")
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
# Helper Functions
# ------------------------------------------------------------------------------
def run_command(cmd, capture_output=False, check=True):
    """Execute a command in the shell and return the result."""
    logging.debug(f"Executing command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}\nError: {e}")
        sys.exit(e.returncode)


def ensure_directory(path: str):
    """Ensure that the given directory exists."""
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
            logging.info(f"Created directory: {path}")
        except Exception as e:
            logging.error(f"Failed to create directory '{path}': {e}")
            sys.exit(1)


# ------------------------------------------------------------------------------
# Download Functions
# ------------------------------------------------------------------------------
def download_with_yt_dlp():
    """Download media from YouTube using yt-dlp."""
    print_section("YouTube Downloader (yt-dlp)")

    yt_link = input("\nEnter YouTube link (video or playlist): ").strip()
    if not yt_link:
        logging.error("YouTube link cannot be empty.")
        return

    download_dir = input("Enter target download directory: ").strip()
    if not download_dir:
        logging.error("Download directory cannot be empty.")
        return

    ensure_directory(download_dir)

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

    logging.info("Starting yt-dlp download...")
    with ConsoleSpinner("Downloading with yt-dlp..."):
        run_command(cmd)
    logging.info("yt-dlp download completed successfully.")


def download_with_wget():
    """Download file from the web using wget."""
    print_section("File Downloader (wget)")

    url = input("\nEnter URL to download: ").strip()
    if not url:
        logging.error("URL cannot be empty.")
        return

    download_dir = input("Enter output directory: ").strip()
    if not download_dir:
        logging.error("Download directory cannot be empty.")
        return

    ensure_directory(download_dir)
    cmd = ["wget", "-P", download_dir, url]

    logging.info("Starting wget download...")
    with ConsoleSpinner("Downloading with wget..."):
        run_command(cmd)
    logging.info("wget download completed successfully.")


# ------------------------------------------------------------------------------
# Interactive Menu
# ------------------------------------------------------------------------------
def display_menu():
    """Display the interactive download method menu."""
    print_section("Universal Downloader")
    print("  1) wget - Download files from the web")
    print("  2) yt-dlp - Download YouTube videos/playlists")
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
# Main Entry Point
# ------------------------------------------------------------------------------
def main():
    """Main entry point for the universal downloader."""
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
