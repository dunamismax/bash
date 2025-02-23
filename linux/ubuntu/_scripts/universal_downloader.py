#!/usr/bin/env python3
"""
Universal Downloader Tool
-------------------------
Advanced auto-download tool that lets the user choose between downloading
with wget or yt-dlp on Ubuntu.

For yt-dlp:
  - Prompts for a YouTube (video/playlist) link and a target download folder,
    creates it if needed, and downloads the media in highest quality,
    merging audio and video into an mp4 via ffmpeg.
For wget:
  - Downloads the file into the specified directory.

Additional features include:
  - Command-line options for non-interactive use.
  - Dry-run mode to simulate actions.
  - Verbose and quiet logging.
  - Automatic installation of missing dependencies via apt.

Author: Your Name | License: MIT | Version: 2.2
"""

import os
import sys
import subprocess
import argparse
import signal
import atexit
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/media_downloader.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL = DEFAULT_LOG_LEVEL
QUIET_MODE = False
DRY_RUN = False

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD8  = '\033[38;2;136;192;208m'  # Accent (for banner)
NORD9  = '\033[38;2;129;161;193m'  # Blue (DEBUG)
NORD11 = '\033[38;2;191;97;106m'   # Red (ERROR)
NORD13 = '\033[38;2;235;203;139m'  # Yellow (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Green (INFO)
NC     = '\033[0m'                # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTIONS
# ------------------------------------------------------------------------------
def get_log_level_num(level: str) -> int:
    level = level.upper()
    if level in ("VERBOSE", "V"):
        return 0
    elif level in ("DEBUG", "D"):
        return 1
    elif level in ("INFO", "I"):
        return 2
    elif level in ("WARN", "WARNING", "W"):
        return 3
    elif level in ("ERROR", "E"):
        return 4
    elif level in ("CRITICAL", "C"):
        return 5
    else:
        return 2

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

def handle_error(error_message="Unknown error occurred", exit_code=1):
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Cleanup: Exiting script.")
    # Add any additional cleanup tasks here.

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum in (signal.SIGINT, signal.SIGTERM):
        handle_error("Script interrupted by user.", exit_code=130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def run_cmd(cmd, capture_output=False, check=True):
    """Run a shell command with optional dry-run."""
    log("DEBUG", f"Executing: {' '.join(cmd)}")
    if DRY_RUN:
        log("INFO", f"DRY RUN: Would execute: {' '.join(cmd)}")
        return None
    try:
        result = subprocess.run(cmd, capture_output=capture_output, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        handle_error(f"Command failed: {' '.join(cmd)}\nError: {e}", exit_code=e.returncode)

def ensure_directory(path: str):
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
            log("INFO", f"Created directory: {path}")
        except Exception as e:
            handle_error(f"Failed to create directory '{path}': {e}")

# ------------------------------------------------------------------------------
# INSTALL PREREQUISITES
# ------------------------------------------------------------------------------
def install_prerequisites():
    log("INFO", "Installing required tools...")
    run_cmd(["sudo", "apt", "update"])
    run_cmd(["sudo", "apt", "install", "-y", "wget", "yt-dlp", "ffmpeg"])
    log("INFO", "Required tools installed.")

# ------------------------------------------------------------------------------
# DOWNLOAD FUNCTIONS
# ------------------------------------------------------------------------------
def download_with_yt_dlp(yt_link: str = None, download_dir: str = None):
    # Prompt for YouTube link if not provided
    if not yt_link:
        yt_link = input("\nEnter YouTube link (video or playlist): ").strip()
        if not yt_link:
            handle_error("YouTube link cannot be empty.")
    # Prompt for download directory if not provided
    if not download_dir:
        download_dir = input("Enter target download directory: ").strip()
        if not download_dir:
            handle_error("Download directory cannot be empty.")
    ensure_directory(download_dir)
    # Build yt-dlp command
    cmd = [
        "yt-dlp", "-f", "bestvideo+bestaudio", "--merge-output-format", "mp4",
        "-o", f"{download_dir}/%(title)s.%(ext)s", yt_link
    ]
    log("INFO", "Starting download via yt-dlp...")
    run_cmd(cmd)
    log("INFO", "yt-dlp download completed.")

def download_with_wget(url: str = None, download_dir: str = None):
    # Prompt for URL if not provided
    if not url:
        url = input("\nEnter URL to download: ").strip()
        if not url:
            handle_error("URL cannot be empty.")
    # Prompt for download directory if not provided
    if not download_dir:
        download_dir = input("Enter output directory: ").strip()
        if not download_dir:
            handle_error("Download directory cannot be empty.")
    ensure_directory(download_dir)
    # Build wget command
    cmd = ["wget", "-q", "-P", download_dir, url]
    log("INFO", "Starting download via wget...")
    run_cmd(cmd)
    log("INFO", "wget download completed.")

# ------------------------------------------------------------------------------
# INTERACTIVE MENU
# ------------------------------------------------------------------------------
def interactive_menu():
    print(f"\n{NORD8}=== Universal Downloader ==={NC}")
    print("Select Download Method:")
    print("  1) wget")
    print("  2) yt-dlp\n")
    choice = input("Enter your choice (1 or 2): ").strip()
    if choice == "1":
        log("INFO", "User selected wget.")
        download_with_wget()
    elif choice == "2":
        log("INFO", "User selected yt-dlp.")
        download_with_yt_dlp()
    else:
        handle_error("Invalid selection. Please run the script again and choose 1 or 2.", exit_code=1)

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Universal Downloader Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--method", choices=["wget", "yt-dlp"],
                        help="Download method to use.")
    parser.add_argument("--url", type=str, help="URL (or YouTube link) to download.")
    parser.add_argument("--dest", type=str, help="Target download directory.")
    parser.add_argument("--install-prereqs", action="store_true",
                        help="Install missing prerequisites using apt.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate downloads without executing commands.")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose (DEBUG) logging.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress console output.")
    parser.add_argument("--version", action="version", version="Universal Downloader v2.2")
    return parser.parse_args()

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    global DRY_RUN, LOG_LEVEL, QUIET_MODE
    args = parse_arguments()
    if args.verbose:
        LOG_LEVEL = "DEBUG"
    if args.quiet:
        QUIET_MODE = True
    if args.dry_run:
        DRY_RUN = True
        log("INFO", "Dry-run mode activated. No downloads will be executed.")
    if args.install_prereqs:
        install_prerequisites()
    # If method is provided non-interactively, use that
    if args.method:
        if args.method == "wget":
            log("INFO", "Using wget method (non-interactive).")
            download_with_wget(url=args.url, download_dir=args.dest)
        elif args.method == "yt-dlp":
            log("INFO", "Using yt-dlp method (non-interactive).")
            download_with_yt_dlp(yt_link=args.url, download_dir=args.dest)
    else:
        # Otherwise, run interactive menu
        interactive_menu()

if __name__ == "__main__":
    main()