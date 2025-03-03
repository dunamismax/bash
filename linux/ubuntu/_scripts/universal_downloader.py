#!/usr/bin/env python3
"""
Universal Downloader
--------------------------------------------------

A powerful and beautiful terminal-based utility for downloading files and media
with real-time progress tracking, Nord-themed UI, and intelligent handling of
various content types.

Features:
  • Supports downloading files via wget
  • Downloads YouTube videos/playlists via yt-dlp
  • Real-time progress tracking with ETA and speed
  • Automatic dependency management
  • Beautiful Nord-themed terminal interface
  • Interactive and command-line modes

Usage:
  Run without arguments for interactive menu
  Or specify command: ./universal_downloader.py wget <url> [options]
  Or for YouTube: ./universal_downloader.py ytdlp <url> [options]

  Options:
    -o, --output-dir <dir>   Set download directory (default: ~/Downloads)
    -v, --verbose            Enable verbose output

Note: For full functionality (especially dependencies installation), run with root privileges.
Version: 3.3.0
"""

import atexit
import datetime
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable, Union

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Prompt, Confirm
    from rich.live import Live
    from rich.columns import Columns
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing them now...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"], check=True
        )
        print("Successfully installed required libraries. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Failed to install required libraries: {e}")
        print("Please install them manually: pip install rich pyfiglet")
        sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "3.3.0"
APP_NAME = "Universal Downloader"
APP_SUBTITLE = "Files & Media Download Tool"

HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/universal_downloader.log"
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")

# Define dependency groups
DEPENDENCIES = {
    "common": ["curl"],
    "wget": ["wget"],
    "yt-dlp": ["yt-dlp", "ffmpeg"],
}

# Progress display settings
SPINNER_INTERVAL = 0.1  # seconds between spinner updates
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
PROGRESS_WIDTH = min(50, TERM_WIDTH - 30)  # Adaptive progress bar width

# Command timeouts
DEFAULT_TIMEOUT = 300  # 5 minutes default timeout for commands
DOWNLOAD_TIMEOUT = 7200  # 2 hours timeout for downloads


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class DownloadSource:
    """
    Represents a source to download from.

    Attributes:
        url: The URL to download from
        name: A friendly name for display (filename or title)
        size: Size in bytes if known, otherwise 0
        is_video: Whether this is a video source
        is_playlist: Whether this is a playlist
    """

    url: str
    name: str = ""
    size: int = 0
    is_video: bool = False
    is_playlist: bool = False

    def __post_init__(self):
        if not self.name:
            self.name = self.get_filename_from_url()

    def get_filename_from_url(self) -> str:
        """Extract filename from URL, falling back to generic name if needed."""
        try:
            # Split on '?' to remove query parameters
            path = self.url.split("?")[0]
            # Get the last part of the path
            filename = os.path.basename(path)
            return filename if filename else "downloaded_file"
        except Exception:
            return "downloaded_file"


@dataclass
class DownloadStats:
    """
    Statistics about an ongoing or completed download.

    Attributes:
        bytes_downloaded: Number of bytes downloaded so far
        total_size: Total expected size in bytes
        start_time: When the download started
        end_time: When the download finished (or None if ongoing)
        rate_history: List of recent download rates for smoothing
    """

    bytes_downloaded: int = 0
    total_size: int = 0
    start_time: float = 0.0
    end_time: Optional[float] = None
    rate_history: List[float] = None

    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
        if self.rate_history is None:
            self.rate_history = []

    @property
    def is_complete(self) -> bool:
        """Return True if the download is complete."""
        return self.end_time is not None or (
            self.total_size > 0 and self.bytes_downloaded >= self.total_size
        )

    @property
    def progress_percentage(self) -> float:
        """Return the download progress as a percentage."""
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.bytes_downloaded / self.total_size) * 100)

    @property
    def elapsed_time(self) -> float:
        """Return the elapsed time in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def average_rate(self) -> float:
        """Return the average download rate in bytes per second."""
        if not self.rate_history:
            if self.elapsed_time > 0:
                return self.bytes_downloaded / self.elapsed_time
            return 0.0
        return sum(self.rate_history) / len(self.rate_history)

    @property
    def eta_seconds(self) -> float:
        """Return the estimated time remaining in seconds."""
        if self.is_complete or self.average_rate <= 0:
            return 0.0
        return (self.total_size - self.bytes_downloaded) / self.average_rate

    def update_progress(self, new_bytes: int) -> None:
        """Update download progress with newly downloaded bytes."""
        now = time.time()
        if self.bytes_downloaded > 0:
            # Calculate the download rate since the last update
            time_diff = now - (self.end_time or self.start_time)
            if time_diff > 0:
                rate = new_bytes / time_diff
                self.rate_history.append(rate)
                # Keep only the last 5 rate measurements for smoothing
                if len(self.rate_history) > 5:
                    self.rate_history.pop(0)

        self.bytes_downloaded += new_bytes
        self.end_time = now

        # If we've reached or exceeded the total, mark as complete
        if self.total_size > 0 and self.bytes_downloaded >= self.total_size:
            self.bytes_downloaded = self.total_size  # Cap at total


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "standard", "digital", "big"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
             _                          _                
 _   _ _ __ (_)_   _____ _ __ ___  __ _| |               
| | | | '_ \| \ \ / / _ \ '__/ __|/ _` | |               
| |_| | | | | |\ V /  __/ |  \__ \ (_| | |               
 \__,_|_| |_|_| \_/ \___|_|_ |___/\__,_|_|   _           
  __| | _____      ___ __ | | ___   __ _  __| | ___ _ __ 
 / _` |/ _ \ \ /\ / / '_ \| |/ _ \ / _` |/ _` |/ _ \ '__|
| (_| | (_) \ V  V /| | | | | (_) | (_| | (_| |  __/ |   
 \__,_|\___/ \_/\_/ |_| |_|_|\___/ \__,_|\__,_|\___|_|   
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure logging to file."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without file logging...")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print detailed information

    Returns:
        CompletedProcess instance with command results
    """
    try:
        cmd_str = " ".join(cmd)
        if verbose:
            print_step(f"Executing: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}")

        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout and verbose:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Network and File Helpers
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Return True if running as root, otherwise warn the user."""
    if os.geteuid() != 0:
        print_warning("Not running with root privileges. Some features may be limited.")
        return False
    return True


def check_dependencies(required: List[str]) -> bool:
    """Check that all required commands are available."""
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        print_warning(f"Missing dependencies: {', '.join(missing)}")
        return False
    return True


def install_dependencies(deps: List[str], verbose: bool = False) -> bool:
    """Attempt to install missing dependencies using apt."""
    print_step(f"Installing dependencies: {', '.join(deps)}")

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Installing dependencies"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        # First update package lists
        update_task = progress.add_task("Updating package lists", total=1)
        try:
            run_command(["apt", "update"], verbose=verbose, capture_output=not verbose)
            progress.update(update_task, completed=1)
        except Exception as e:
            print_error(f"Failed to update package lists: {e}")
            return False

        # Then install each dependency
        install_task = progress.add_task("Installing packages", total=len(deps))
        missing_after = []

        for dep in deps:
            try:
                run_command(
                    ["apt", "install", "-y", dep],
                    verbose=verbose,
                    capture_output=not verbose,
                )
                progress.advance(install_task)

                # Verify installation
                if not shutil.which(dep):
                    missing_after.append(dep)
            except Exception as e:
                print_error(f"Failed to install {dep}: {e}")
                missing_after.append(dep)
                progress.advance(install_task)

    if missing_after:
        print_error(f"Failed to install: {', '.join(missing_after)}")
        return False

    print_success(f"Successfully installed: {', '.join(deps)}")
    return True


def check_internet_connectivity() -> bool:
    """Check for internet connectivity by pinging a well-known host."""
    try:
        print_step("Checking internet connectivity...")
        result = run_command(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False, capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_directory(path: str) -> None:
    """Ensure that a directory exists, creating it if necessary."""
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        sys.exit(1)


def get_file_size(url: str) -> int:
    """
    Retrieve the file size in bytes using a HEAD request with curl.
    Returns 0 if the size cannot be determined.
    """
    try:
        result = run_command(["curl", "--silent", "--head", url], capture_output=True)
        for line in result.stdout.splitlines():
            if "content-length:" in line.lower():
                return int(line.split(":", 1)[1].strip())
        return 0
    except Exception as e:
        print_warning(f"Could not determine file size for {url}: {e}")
        return 0


def estimate_youtube_size(url: str) -> int:
    """
    Estimate the file size of a YouTube video using yt-dlp.
    Falls back to a default size if estimation fails.
    """
    try:
        result = run_command(
            ["yt-dlp", "--print", "filesize", url], capture_output=True, check=False
        )
        if result.stdout.strip().isdigit():
            return int(result.stdout.strip())

        # Try estimating based on video duration
        result = run_command(
            ["yt-dlp", "--print", "duration", url], capture_output=True, check=False
        )
        if result.stdout.strip().replace(".", "", 1).isdigit():
            duration = float(result.stdout.strip())
            # Rough estimate: Assume 10 MB per minute of video
            return int(duration * 60 * 10 * 1024)

        return 100 * 1024 * 1024  # Default 100MB
    except Exception as e:
        print_warning(f"Could not estimate video size: {e}")
        return 100 * 1024 * 1024


def get_youtube_info(url: str) -> Tuple[str, bool]:
    """
    Get basic info about a YouTube URL.

    Returns:
        Tuple of (title, is_playlist)
    """
    title = "Unknown video"
    is_playlist = False

    try:
        # First check if it's a playlist
        result = run_command(
            ["yt-dlp", "--flat-playlist", "--print", "playlist_id", url],
            capture_output=True,
            check=False,
        )
        is_playlist = bool(result.stdout.strip())

        # Then get the title
        if is_playlist:
            result = run_command(
                ["yt-dlp", "--flat-playlist", "--print", "playlist_title", url],
                capture_output=True,
                check=False,
            )
            if result.stdout.strip():
                title = result.stdout.strip()
        else:
            result = run_command(
                ["yt-dlp", "--print", "title", url], capture_output=True, check=False
            )
            if result.stdout.strip():
                title = result.stdout.strip()
    except Exception as e:
        print_warning(f"Could not get YouTube info: {e}")

    return title, is_playlist


# ----------------------------------------------------------------
# Download Functions
# ----------------------------------------------------------------
def download_with_wget(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a file using wget or urllib.

    Args:
        url: The URL to download from
        output_dir: Directory to save the file in
        verbose: Whether to show verbose output

    Returns:
        True if download was successful, False otherwise
    """
    try:
        # Create a DownloadSource object
        source = DownloadSource(url=url)
        source.size = get_file_size(url)
        filename = source.name

        # Ensure output directory exists
        ensure_directory(output_dir)
        output_path = os.path.join(output_dir, filename)

        print_step(f"Downloading: {url}")
        print_step(f"Destination: {output_path}")

        if source.size:
            print_step(f"File size: {format_size(source.size)}")
        else:
            print_warning("File size unknown; progress will be indeterminate.")

        # Download stats to track progress
        stats = DownloadStats(total_size=source.size)

        # Use Progress from rich for a nicer display
        if source.size > 0:
            with Progress(
                SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
                BarColumn(
                    bar_width=PROGRESS_WIDTH,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn(
                    f"[{NordColors.SNOW_STORM_1}]{{task.completed:.2f}}/{{task.total:.2f}} MB"
                ),
                TextColumn(f"[{NordColors.GREEN}]{{task.fields[rate]}}"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                download_task = progress.add_task(
                    "Downloading",
                    total=source.size / 1024 / 1024,  # Convert to MB
                    completed=0,
                    rate="0 KB/s",
                )

                def progress_callback(block_count, block_size, total_size):
                    current = block_count * block_size
                    # Only advance if we downloaded more data
                    if current > stats.bytes_downloaded:
                        new_bytes = current - stats.bytes_downloaded
                        stats.update_progress(new_bytes)
                        progress.update(
                            download_task,
                            completed=stats.bytes_downloaded / 1024 / 1024,  # MB
                            rate=f"{format_size(stats.average_rate)}/s",
                        )

                # Use urllib.request.urlretrieve with progress callback
                urllib.request.urlretrieve(
                    url, output_path, reporthook=progress_callback
                )
        else:
            # For unknown size, use a spinner with wget
            with Progress(
                SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Downloading {filename}"),
                TextColumn(f"[{NordColors.SNOW_STORM_1}]Time: {{task.elapsed:.1f}}s"),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading")
                run_command(["wget", "-q", "-O", output_path, url], verbose=verbose)

        # Check if download was successful
        if not os.path.exists(output_path):
            print_error("Download failed: Output file not found.")
            return False

        # Show final stats
        file_stats = os.stat(output_path)
        download_time = time.time() - stats.start_time
        download_speed = file_stats.st_size / max(download_time, 0.1)

        display_panel(
            f"Downloaded: {filename}\n"
            f"Size: {format_size(file_stats.st_size)}\n"
            f"Time: {format_time(download_time)}\n"
            f"Speed: {format_size(download_speed)}/s\n"
            f"Location: {output_path}",
            style=NordColors.GREEN,
            title="Download Complete",
        )
        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def download_with_yt_dlp(url: str, output_dir: str, verbose: bool = False) -> bool:
    """
    Download a YouTube video using yt-dlp.

    Args:
        url: YouTube URL to download from
        output_dir: Directory to save the video in
        verbose: Whether to show verbose output

    Returns:
        True if download was successful, False otherwise
    """
    try:
        # Ensure output directory exists
        ensure_directory(output_dir)

        # Get YouTube video information
        title, is_playlist = get_youtube_info(url)
        estimated_size = estimate_youtube_size(url) if not is_playlist else 0

        # Create DownloadSource
        source = DownloadSource(
            url=url,
            name=title,
            size=estimated_size,
            is_video=True,
            is_playlist=is_playlist,
        )

        # Show information panel
        content_type = "Playlist" if is_playlist else "Video"
        info_text = f"Title: {title}\nType: {content_type}\n"

        if not is_playlist and estimated_size:
            info_text += f"Estimated size: {format_size(estimated_size)}\n"

        info_text += f"Destination: {output_dir}"

        display_panel(info_text, style=NordColors.FROST_3, title="YouTube Download")

        # Prepare command
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-f",
            "bestvideo+bestaudio/best",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
        ]

        if verbose:
            cmd.append("--verbose")
        cmd.append(url)

        # For playlist or verbose mode, use simpler progress display
        if is_playlist or verbose:
            with Progress(
                SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Downloading {content_type}"),
                TextColumn(f"[{NordColors.SNOW_STORM_1}]Time: {{task.elapsed:.1f}}s"),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading")
                run_command(cmd, verbose=verbose, timeout=DOWNLOAD_TIMEOUT)
        else:
            # For single videos, parse output for progress information
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            with Progress(
                SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
                BarColumn(
                    bar_width=PROGRESS_WIDTH,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading Video", total=100)
                stage = "Preparing"

                # Parse yt-dlp output for progress
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break

                    # Update progress based on output
                    if "[download]" in line and "%" in line:
                        try:
                            parts = line.split()
                            for part in parts:
                                if "%" in part:
                                    pct_str = part.rstrip("%").rstrip(",")
                                    progress.update(task, completed=float(pct_str))
                                    break
                        except Exception:
                            pass
                    elif "Downloading video" in line:
                        stage = "Downloading video"
                        progress.update(task, description=stage)
                    elif "Downloading audio" in line:
                        stage = "Downloading audio"
                        progress.update(task, description=stage)
                    elif "Merging formats" in line:
                        stage = "Merging formats"
                        progress.update(task, completed=99, description=stage)

                process.wait()
                if process.returncode != 0:
                    print_error("Download failed.")
                    return False

        display_panel(
            f"Successfully downloaded: {title}\nLocation: {output_dir}",
            style=NordColors.GREEN,
            title="Download Complete",
        )
        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


# ----------------------------------------------------------------
# Command Functions
# ----------------------------------------------------------------
def cmd_wget(url: str, output_dir: str, verbose: bool) -> None:
    """Execute the wget download command after ensuring dependencies."""
    required = DEPENDENCIES["common"] + DEPENDENCIES["wget"]

    # Check and install dependencies if needed
    if not check_dependencies(required):
        if os.geteuid() == 0:
            if not install_dependencies(required, verbose):
                print_error("Failed to install dependencies.")
                sys.exit(1)
        else:
            print_error("Missing dependencies and not running as root to install them.")
            sys.exit(1)

    # Execute download
    success = download_with_wget(url, output_dir, verbose)
    sys.exit(0 if success else 1)


def cmd_ytdlp(url: str, output_dir: str, verbose: bool) -> None:
    """Execute the yt-dlp download command after ensuring dependencies."""
    required = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]

    # Check and install dependencies if needed
    if not check_dependencies(required):
        if os.geteuid() == 0:
            if not install_dependencies(required, verbose):
                print_error("Failed to install dependencies.")
                sys.exit(1)
        else:
            print_error("Missing dependencies and not running as root to install them.")
            sys.exit(1)

    # Execute download
    success = download_with_yt_dlp(url, output_dir, verbose)
    sys.exit(0 if success else 1)


# ----------------------------------------------------------------
# Interactive Menu Functions
# ----------------------------------------------------------------
def create_download_options_table() -> Table:
    """Create a table showing download options."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Download Options[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Type", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", style=f"bold {NordColors.GREEN}")

    # Check dependency status
    wget_status = (
        "✓ Available"
        if check_dependencies(DEPENDENCIES["wget"])
        else "× Missing dependencies"
    )
    ytdlp_status = (
        "✓ Available"
        if check_dependencies(DEPENDENCIES["yt-dlp"])
        else "× Missing dependencies"
    )

    table.add_row("1", "Standard File", "Download any file using wget", wget_status)
    table.add_row("2", "YouTube", "Download videos/playlists with yt-dlp", ytdlp_status)
    table.add_row("3", "Exit", "Quit the application", "")

    return table


def download_menu() -> None:
    """Interactive download menu for the Universal Downloader."""
    console.print(create_header())

    # Display system info
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]System: {platform.system()} {platform.release()}[/] | "
            f"[{NordColors.SNOW_STORM_1}]User: {os.environ.get('USER', 'unknown')}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
    )
    console.print()

    # Display download options
    console.print(create_download_options_table())

    while True:
        choice = Prompt.ask(
            f"\n[bold {NordColors.PURPLE}]Enter your choice",
            choices=["1", "2", "3"],
            default="1",
        )

        if choice == "1":  # Standard file download
            required = DEPENDENCIES["common"] + DEPENDENCIES["wget"]
            if not check_dependencies(required):
                if os.geteuid() == 0:
                    if not install_dependencies(required):
                        print_error("Failed to install dependencies.")
                        return
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    return

            url = Prompt.ask(f"[bold {NordColors.PURPLE}]Enter URL to download")
            if not url:
                print_error("URL cannot be empty.")
                return

            output_dir = Prompt.ask(
                f"[bold {NordColors.PURPLE}]Enter output directory",
                default=DEFAULT_DOWNLOAD_DIR,
            )

            verbose = Confirm.ask(
                f"[bold {NordColors.PURPLE}]Enable verbose output?", default=False
            )

            download_with_wget(url, output_dir, verbose)
            break

        elif choice == "2":  # YouTube download
            required = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]
            if not check_dependencies(required):
                if os.geteuid() == 0:
                    if not install_dependencies(required):
                        print_error("Failed to install dependencies.")
                        return
                else:
                    print_error(
                        "Missing dependencies and not running as root to install them."
                    )
                    return

            url = Prompt.ask(f"[bold {NordColors.PURPLE}]Enter YouTube URL")
            if not url:
                print_error("URL cannot be empty.")
                return

            output_dir = Prompt.ask(
                f"[bold {NordColors.PURPLE}]Enter output directory",
                default=DEFAULT_DOWNLOAD_DIR,
            )

            verbose = Confirm.ask(
                f"[bold {NordColors.PURPLE}]Enable verbose output?", default=False
            )

            download_with_yt_dlp(url, output_dir, verbose)
            break

        elif choice == "3":  # Exit
            print_step("Exiting...")
            return

        else:
            print_error("Invalid selection. Please choose 1-3.")


def parse_args() -> Dict[str, Any]:
    """Parse command-line arguments into a dictionary."""
    args: Dict[str, Any] = {}
    argv = sys.argv[1:]

    if not argv:
        return {"command": "menu"}

    command = argv[0]
    args["command"] = command

    if command in ["wget", "ytdlp"]:
        url = None
        output_dir = DEFAULT_DOWNLOAD_DIR
        verbose = False
        i = 1

        while i < len(argv):
            if argv[i] in ["-o", "--output-dir"] and i + 1 < len(argv):
                output_dir = argv[i + 1]
                i += 2
            elif argv[i] in ["-v", "--verbose"]:
                verbose = True
                i += 1
            elif argv[i].startswith("-"):
                i += 1
                if i < len(argv) and not argv[i].startswith("-"):
                    i += 1
            else:
                url = argv[i]
                i += 1

        args["url"] = url
        args["output_dir"] = output_dir
        args["verbose"] = verbose

    return args


def show_usage() -> None:
    """Display usage information for the script."""
    console.print(create_header())

    # Create a usage table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Usage Information[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("Command", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    table.add_row("./universal_downloader.py", "Start the interactive download menu")
    table.add_row(
        "./universal_downloader.py wget <url> [options]", "Download a file using wget"
    )
    table.add_row(
        "./universal_downloader.py ytdlp <url> [options]",
        "Download a YouTube video/playlist using yt-dlp",
    )
    table.add_row("./universal_downloader.py help", "Show this help information")

    console.print(table)

    # Options table
    options_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Options[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    options_table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    options_table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    options_table.add_row(
        "-o, --output-dir <dir>",
        f"Set the output directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )
    options_table.add_row("-v, --verbose", "Enable verbose output")

    console.print(options_table)

    # Examples
    examples_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Examples[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    examples_table.add_column(
        "Example", style=f"bold {NordColors.FROST_2}", no_wrap=True
    )
    examples_table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    examples_table.add_row("./universal_downloader.py", "Start the interactive menu")
    examples_table.add_row(
        "./universal_downloader.py wget https://example.com/file.zip -o /tmp",
        "Download a zip file to /tmp directory",
    )
    examples_table.add_row(
        "./universal_downloader.py ytdlp https://youtube.com/watch?v=abcdef -v",
        "Download a YouTube video with verbose output",
    )

    console.print(examples_table)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function: parses arguments, checks connectivity, and dispatches commands."""
    try:
        console.print(create_header())

        # Display system info
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]System: {platform.system()} {platform.release()}[/] | "
                f"[{NordColors.SNOW_STORM_1}]User: {os.environ.get('USER', 'unknown')}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
            )
        )
        console.print()

        setup_logging()

        if not check_internet_connectivity():
            print_error(
                "No internet connectivity detected. Please check your connection."
            )
            sys.exit(1)

        check_root_privileges()

        args = parse_args()
        command = args.get("command")

        if command == "menu" or command is None:
            download_menu()
        elif command == "wget":
            if not args.get("url"):
                print_error("URL is required for wget command.")
                show_usage()
                sys.exit(1)
            cmd_wget(args["url"], args["output_dir"], args.get("verbose", False))
        elif command == "ytdlp":
            if not args.get("url"):
                print_error("URL is required for ytdlp command.")
                show_usage()
                sys.exit(1)
            cmd_ytdlp(args["url"], args["output_dir"], args.get("verbose", False))
        elif command in ["help", "--help", "-h"]:
            show_usage()
        else:
            print_error(f"Unknown command: {command}")
            show_usage()
            sys.exit(1)
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
