#!/usr/bin/env python3
"""
Enhanced Universal Downloader Script
------------------------------------

A robust command-line utility for downloading files from the web with powerful features:
  • Support for wget (general file downloads)
  • Support for yt-dlp (YouTube video/playlist downloads)
  • Real-time progress tracking with transfer rates and ETA
  • Automatic dependency installation
  • Comprehensive error handling and recovery
  • Beautiful Nord-themed terminal output

The script provides an interactive menu for download method selection and handles
all the complexities of download configuration, ensuring files are saved correctly
and with the highest quality for media downloads.

Note: Run this script with root privileges for full functionality.
"""

import argparse
import atexit
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# Script version
VERSION = "3.1.0"

# Logging configuration
LOG_FILE = "/var/log/universal_downloader.log"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Default download locations
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")

# Dependencies required for each download method
DEPENDENCIES = {
    "common": ["curl"],
    "wget": ["wget"],
    "yt-dlp": ["yt-dlp", "ffmpeg"],
}

# Progress tracking settings
PROGRESS_WIDTH = 50
SPINNER_INTERVAL = 0.1  # seconds between spinner updates
MAX_RETRIES = 3
RATE_CALCULATION_WINDOW = 5  # seconds to average download rate

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """Nord-themed ANSI color codes for terminal output"""

    # Nord theme colors
    HEADER = "\033[38;5;81m"  # Nord9 - Blue
    GREEN = "\033[38;5;108m"  # Nord14 - Green
    YELLOW = "\033[38;5;179m"  # Nord13 - Yellow
    RED = "\033[38;5;174m"  # Nord11 - Red
    BLUE = "\033[38;5;67m"  # Nord10 - Deep Blue
    CYAN = "\033[38;5;110m"  # Nord8 - Light Blue
    MAGENTA = "\033[38;5;139m"  # Nord15 - Purple
    WHITE = "\033[38;5;253m"  # Nord4 - Light foreground
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        """
        Initialize a progress bar.

        Args:
            total: Total number of units to track
            desc: Description to display alongside the progress bar
            width: Width of the progress bar in characters
        """
        self.total = max(1, total)  # Avoid division by zero
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_update_value = 0
        self.rates = []
        self._lock = threading.Lock()
        self._display()

    def update(self, amount: int) -> None:
        """
        Update progress safely

        Args:
            amount: Increment amount to add to current progress
        """
        with self._lock:
            self.current = min(self.current + amount, self.total)

            # Calculate rate
            now = time.time()
            time_diff = now - self.last_update_time
            if time_diff >= 0.5:  # Only update rate every 0.5 seconds
                value_diff = self.current - self.last_update_value
                rate = value_diff / time_diff

                # Store rate for averaging
                self.rates.append(rate)
                if len(self.rates) > 5:
                    self.rates.pop(0)

                self.last_update_time = now
                self.last_update_value = self.current

            self._display()

    def _format_size(self, bytes: int) -> str:
        """
        Format bytes to human readable size

        Args:
            bytes: Size in bytes

        Returns:
            Human-readable size string
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} PB"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        avg_rate = sum(self.rates) / max(1, len(self.rates))
        eta = (self.total - self.current) / max(0.1, avg_rate) if avg_rate > 0 else 0

        # Format ETA nicely
        if eta > 3600:
            eta_str = f"{eta / 3600:.1f}h"
        elif eta > 60:
            eta_str = f"{eta / 60:.1f}m"
        else:
            eta_str = f"{eta:.0f}s"

        # Format output
        status = (
            f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| "
            f"{Colors.WHITE}{percent:>5.1f}%{Colors.ENDC} "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{Colors.GREEN}{self._format_size(avg_rate)}/s{Colors.ENDC}] "
            f"[ETA: {eta_str}]"
        )

        # Truncate if too long for terminal
        max_len = TERM_WIDTH - 1
        if len(status) > max_len:
            status = status[:max_len]

        sys.stdout.write(status)
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


class Spinner:
    """Thread-safe spinner for operations with unknown progress"""

    def __init__(self, message: str):
        """
        Initialize a spinner.

        Args:
            message: Message to display alongside the spinner
        """
        self.message = message
        self.spinning = False
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.thread = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Animation loop for the spinner"""
        while self.spinning:
            elapsed = time.time() - self.start_time
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            elif minutes > 0:
                time_str = f"{int(minutes)}m {int(seconds)}s"
            else:
                time_str = f"{seconds:.1f}s"

            with self._lock:
                sys.stdout.write(
                    f"\r{Colors.BLUE}{self.spinner_chars[self.current]}{Colors.ENDC} "
                    f"{Colors.CYAN}{self.message}{Colors.ENDC} "
                    f"[{Colors.DIM}elapsed: {time_str}{Colors.ENDC}]"
                )
                sys.stdout.flush()
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(SPINNER_INTERVAL)

    def start(self) -> None:
        """Start the spinner animation"""
        with self._lock:
            if not self.spinning:
                self.spinning = True
                self.start_time = time.time()
                self.thread = threading.Thread(target=self._spin)
                self.thread.daemon = True
                self.thread.start()

    def stop(self, success: bool = True) -> None:
        """
        Stop the spinner animation

        Args:
            success: Whether the operation was successful
        """
        with self._lock:
            if self.spinning:
                self.spinning = False
                if self.thread:
                    self.thread.join()

                # Calculate elapsed time
                elapsed = time.time() - self.start_time
                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours > 0:
                    time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                elif minutes > 0:
                    time_str = f"{int(minutes)}m {int(seconds)}s"
                else:
                    time_str = f"{seconds:.1f}s"

                # Clear the line
                sys.stdout.write("\r" + " " * TERM_WIDTH + "\r")

                # Print completion message
                if success:
                    sys.stdout.write(
                        f"{Colors.GREEN}✓{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} "
                        f"{Colors.GREEN}completed{Colors.ENDC} in {time_str}\n"
                    )
                else:
                    sys.stdout.write(
                        f"{Colors.RED}✗{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} "
                        f"{Colors.RED}failed{Colors.ENDC} after {time_str}\n"
                    )
                sys.stdout.flush()

    def __enter__(self):
        """Start the spinner when used as a context manager"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the spinner when exiting context manager"""
        self.stop(exc_type is None)


#####################################
# Helper Functions
#####################################


def format_size(bytes: int) -> str:
    """
    Format bytes to human readable size

    Args:
        bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def print_header(message: str) -> None:
    """
    Print formatted header

    Args:
        message: Header message
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * TERM_WIDTH}")
    print(message.center(TERM_WIDTH))
    print(f"{'=' * TERM_WIDTH}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """
    Print formatted section header

    Args:
        message: Section header message
    """
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def print_step(message: str) -> None:
    """
    Print step message

    Args:
        message: Step message
    """
    print(f"{Colors.CYAN}• {message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """
    Print success message

    Args:
        message: Success message
    """
    print(f"{Colors.GREEN}✓ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """
    Print warning message

    Args:
        message: Warning message
    """
    print(f"{Colors.YELLOW}⚠ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """
    Print error message

    Args:
        message: Error message
    """
    print(f"{Colors.RED}✗ {message}{Colors.ENDC}")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = False,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run command with error handling

    Args:
        cmd: Command to execute as list of strings
        env: Environment variables dictionary
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        verbose: Whether to print verbose output

    Returns:
        CompletedProcess instance with execution results
    """
    if verbose:
        print_step(f"Executing: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stdout") and e.stdout:
            print(f"{Colors.DIM}Stdout: {e.stdout.strip()}{Colors.ENDC}")
        if hasattr(e, "stderr") and e.stderr:
            print(f"{Colors.RED}Stderr: {e.stderr.strip()}{Colors.ENDC}")
        raise


def signal_handler(sig, frame) -> None:
    """
    Handle interrupt signals gracefully

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print(
        f"\n{Colors.YELLOW}Process interrupted by {sig_name}. Cleaning up...{Colors.ENDC}"
    )
    cleanup()
    sys.exit(128 + sig)


def ensure_directory(path: str) -> None:
    """
    Ensure that a directory exists, creating it if necessary

    Args:
        path: Directory path to ensure
    """
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        sys.exit(1)


def get_file_size(url: str) -> int:
    """
    Get the size of a remote file

    Args:
        url: URL of the file

    Returns:
        Size in bytes or 0 if unknown
    """
    try:
        # Use curl to get content-length header
        result = run_command(["curl", "--silent", "--head", url], capture_output=True)

        # Parse content-length from headers
        for line in result.stdout.splitlines():
            if "content-length:" in line.lower():
                size = int(line.split(":", 1)[1].strip())
                return size

        # If content-length not found, return a default size
        return 0
    except Exception as e:
        print_warning(f"Could not determine file size for {url}: {e}")
        return 0


def estimate_youtube_size(url: str) -> int:
    """
    Estimate the size of a YouTube video

    Args:
        url: YouTube URL

    Returns:
        Estimated size in bytes
    """
    try:
        # Get video info from yt-dlp
        result = run_command(
            ["yt-dlp", "--print", "filesize", url], capture_output=True, check=False
        )

        # Parse filesize from output
        if result.stdout.strip() and result.stdout.strip().isdigit():
            return int(result.stdout.strip())

        # If filesize not available, get duration and estimate
        result = run_command(
            ["yt-dlp", "--print", "duration", url], capture_output=True, check=False
        )

        if (
            result.stdout.strip()
            and result.stdout.strip().replace(".", "", 1).isdigit()
        ):
            duration = float(result.stdout.strip())
            # Rough estimate: ~10MB per minute for high quality
            return int(duration * 60 * 10 * 1024 * 1024)

        # Default fallback estimate
        return 100 * 1024 * 1024  # 100MB default estimate
    except Exception as e:
        print_warning(f"Could not estimate video size: {e}")
        return 100 * 1024 * 1024  # 100MB default estimate


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """
    Check if script is run with root privileges

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_warning("This script is not running with root privileges.")
        print_step("Some features may require root access.")
        return False
    return True


def check_dependencies(required: List[str]) -> bool:
    """
    Check if required tools are installed

    Args:
        required: List of required dependencies

    Returns:
        True if all dependencies are installed, False otherwise
    """
    missing = [cmd for cmd in required if not shutil.which(cmd)]

    if missing:
        print_warning(f"Missing dependencies: {', '.join(missing)}")
        return False
    return True


def check_internet_connectivity() -> bool:
    """
    Check if system has internet connectivity

    Returns:
        True if internet is available, False otherwise
    """
    try:
        # Try to connect to Google's DNS
        result = run_command(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False, capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


#####################################
# Download Functions
#####################################


def install_dependencies(dependencies: List[str], verbose: bool = False) -> bool:
    """
    Install missing dependencies

    Args:
        dependencies: List of packages to install
        verbose: Whether to show verbose output

    Returns:
        True if successful, False otherwise
    """
    print_section(f"Installing Dependencies: {', '.join(dependencies)}")

    try:
        with Spinner("Updating package lists") as spinner:
            run_command(["apt", "update"], verbose=verbose, capture_output=not verbose)

        with Spinner(f"Installing {len(dependencies)} packages") as spinner:
            run_command(
                ["apt", "install", "-y"] + dependencies,
                verbose=verbose,
                capture_output=not verbose,
            )

        # Verify installation
        missing = [cmd for cmd in dependencies if not shutil.which(cmd)]
        if missing:
            print_error(f"Failed to install: {', '.join(missing)}")
            return False

        print_success(f"Successfully installed: {', '.join(dependencies)}")
        return True
    except Exception as e:
        print_error(f"Failed to install dependencies: {e}")
        return False


def download_with_wget(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a file using wget

    Args:
        url: URL to download
        output_dir: Directory to save the file
        verbose: Whether to show verbose output

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the file size for progress tracking
        file_size = get_file_size(url)

        # Get filename from URL
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = "downloaded_file"

        # Ensure the output directory exists
        ensure_directory(output_dir)

        # Full output path
        output_path = os.path.join(output_dir, filename)

        print_step(f"Downloading {url}")
        print_step(f"Destination: {output_path}")

        if file_size:
            print_step(f"File size: {format_size(file_size)}")
        else:
            print_warning("File size unknown. Progress will be indeterminate.")

        # Start the download
        if file_size > 0:
            # Use progress bar for known size
            progress = ProgressBar(file_size, "Downloading")

            # Download with curl showing progress
            def progress_callback(
                block_count: int, block_size: int, total_size: int
            ) -> None:
                downloaded = block_count * block_size
                progress.update(block_size)

            import urllib.request

            urllib.request.urlretrieve(url, output_path, reporthook=progress_callback)

        else:
            # Use spinner for unknown size
            with Spinner(f"Downloading {filename}") as spinner:
                run_command(["wget", "-q", "-O", output_path, url], verbose=verbose)

        # Verify download
        if not os.path.exists(output_path):
            print_error("Download failed: Output file not found.")
            return False

        file_stats = os.stat(output_path)
        print_success(f"Downloaded {format_size(file_stats.st_size)} to {output_path}")
        return True

    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def download_with_yt_dlp(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a video using yt-dlp

    Args:
        url: YouTube URL to download
        output_dir: Directory to save the video
        verbose: Whether to show verbose output

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure the output directory exists
        ensure_directory(output_dir)

        # Estimate video size
        estimated_size = estimate_youtube_size(url)

        if estimated_size > 0:
            print_step(f"Estimated size: {format_size(estimated_size)}")

        # Get video title
        try:
            result = run_command(
                ["yt-dlp", "--print", "title", url], capture_output=True
            )
            video_title = result.stdout.strip()
            print_step(f"Video title: {video_title}")
        except Exception:
            video_title = "Unknown video"

        # Format output template
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

        # Prepare command
        cmd = [
            "yt-dlp",
            "-f",
            "bestvideo+bestaudio",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
        ]

        if verbose:
            cmd.append("--verbose")

        cmd.append(url)

        # Start download with progress tracking
        if verbose:
            # Run directly with verbose output
            with Spinner(f"Downloading {video_title}") as spinner:
                run_command(cmd, verbose=True)
        else:
            # Run with progress tracking
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            progress = None
            current_action = None

            while True:
                line = process.stdout.readline()
                if not line:
                    break

                # Clear current line
                sys.stdout.write("\r" + " " * TERM_WIDTH + "\r")

                # Parse progress information
                if "[download]" in line and "%" in line:
                    try:
                        percent_str = line.split()[1].rstrip(",")
                        percent = float(percent_str.rstrip("%"))

                        if progress is None and estimated_size > 0:
                            progress = ProgressBar(100, "Downloading")

                        if progress is not None:
                            # Update to current percentage
                            progress.current = percent
                            progress._display()

                        current_action = "Downloading"

                    except (ValueError, IndexError):
                        pass

                elif "Downloading video" in line or "Downloading audio" in line:
                    current_action = line.strip()
                    if progress is not None:
                        progress.desc = current_action
                        progress._display()

                elif "Merging formats" in line:
                    # Video and audio download complete, now merging
                    if progress is not None:
                        progress.current = 100
                        progress._display()

                    sys.stdout.write("\n")
                    with Spinner("Merging audio and video") as spinner:
                        # Wait for merge to complete
                        while True:
                            line = process.stdout.readline()
                            if not line:
                                break
                    break

            # Wait for process to complete
            process.wait()

            if process.returncode != 0:
                print_error("Download failed.")
                return False

        print_success(f"Successfully downloaded {video_title}")
        return True

    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


#####################################
# Cleanup Functions
#####################################


def cleanup() -> None:
    """Perform cleanup before exit"""
    # Any specific cleanup tasks can be added here
    pass


#####################################
# Main Function
#####################################


def download_menu() -> None:
    """Display and handle the download method selection menu"""
    print_header("Universal Downloader")

    print(f"{Colors.CYAN}Select download method:{Colors.ENDC}")
    print(f"  {Colors.BOLD}1){Colors.ENDC} wget  - Download files from the web")
    print(f"  {Colors.BOLD}2){Colors.ENDC} yt-dlp - Download YouTube videos/playlists")
    print(f"  {Colors.BOLD}q){Colors.ENDC} Quit")
    print()

    while True:
        choice = (
            input(f"{Colors.BOLD}Enter your choice (1, 2, or q):{Colors.ENDC} ")
            .strip()
            .lower()
        )

        if choice == "1":
            # Check wget dependencies
            deps = DEPENDENCIES["common"] + DEPENDENCIES["wget"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install required dependencies.")
                        return
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    return

            # Prompt for URL and directory
            url = input(f"\n{Colors.BOLD}Enter URL to download:{Colors.ENDC} ").strip()
            if not url:
                print_error("URL cannot be empty.")
                return

            output_dir = input(
                f"{Colors.BOLD}Enter output directory [{DEFAULT_DOWNLOAD_DIR}]:{Colors.ENDC} "
            ).strip()
            if not output_dir:
                output_dir = DEFAULT_DOWNLOAD_DIR

            # Download the file
            download_with_wget(url, output_dir)
            break

        elif choice == "2":
            # Check yt-dlp dependencies
            deps = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install required dependencies.")
                        return
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    return

            # Prompt for YouTube URL and directory
            url = input(
                f"\n{Colors.BOLD}Enter YouTube URL (video or playlist):{Colors.ENDC} "
            ).strip()
            if not url:
                print_error("URL cannot be empty.")
                return

            output_dir = input(
                f"{Colors.BOLD}Enter output directory [{DEFAULT_DOWNLOAD_DIR}]:{Colors.ENDC} "
            ).strip()
            if not output_dir:
                output_dir = DEFAULT_DOWNLOAD_DIR

            # Download the video
            download_with_yt_dlp(url, output_dir)
            break

        elif choice in ("q", "quit", "exit"):
            print_step("Exiting...")
            return

        else:
            print_error("Invalid selection. Please choose 1, 2, or q.")


def main() -> None:
    """Main execution function"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Register cleanup handler
    atexit.register(cleanup)

    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Enhanced Universal Downloader Script",
        epilog="Run without arguments for interactive mode",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--version", action="version", version=f"Universal Downloader v{VERSION}"
    )

    # Download method subcommands
    subparsers = parser.add_subparsers(dest="command", help="Download method")

    # wget subcommand
    wget_parser = subparsers.add_parser("wget", help="Download with wget")
    wget_parser.add_argument("url", help="URL to download")
    wget_parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )

    # yt-dlp subcommand
    ytdlp_parser = subparsers.add_parser("yt-dlp", help="Download YouTube videos")
    ytdlp_parser.add_argument("url", help="YouTube URL (video or playlist)")
    ytdlp_parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )

    # Parse arguments
    args = parser.parse_args()

    # Print welcome banner
    print_header("Enhanced Universal Downloader v" + VERSION)
    print(f"System: {platform.system()} {platform.release()}")
    print(f"User: {os.environ.get('USER', 'unknown')}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Working directory: {os.getcwd()}")

    # Check internet connectivity
    if not check_internet_connectivity():
        print_error("No internet connectivity detected. Please check your connection.")
        sys.exit(1)

    # Check root privileges (warning only)
    has_root = check_root_privileges()

    try:
        # Process commands
        if args.command == "wget":
            # Check wget dependencies
            deps = DEPENDENCIES["common"] + DEPENDENCIES["wget"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install required dependencies.")
                        sys.exit(1)
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    sys.exit(1)

            # Download with wget
            success = download_with_wget(args.url, args.output_dir, args.verbose)
            sys.exit(0 if success else 1)

        elif args.command == "yt-dlp":
            # Check yt-dlp dependencies
            deps = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install required dependencies.")
                        sys.exit(1)
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    sys.exit(1)

            # Download with yt-dlp
            success = download_with_yt_dlp(args.url, args.output_dir, args.verbose)
            sys.exit(0 if success else 1)

        else:
            # Interactive mode
            download_menu()

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Process interrupted by user.{Colors.ENDC}")
        sys.exit(130)

    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)

    # Print goodbye message
    print_section("Download Operations Completed")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
