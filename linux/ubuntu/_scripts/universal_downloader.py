#!/usr/bin/env python3
"""
Enhanced Universal Downloader Script
------------------------------------

This utility downloads files from the web using either wget (for general files)
or yt-dlp (for YouTube videos/playlists). It features real‑time progress tracking,
automatic dependency checking/installation, comprehensive error handling,
and a beautiful Nord‑themed terminal interface.

Note: Run this script with root privileges for full functionality.
Version: 3.1.0
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
HOSTNAME = socket.gethostname()
VERSION = "3.1.0"
LOG_FILE = "/var/log/universal_downloader.log"

DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")

DEPENDENCIES = {
    "common": ["curl"],
    "wget": ["wget"],
    "yt-dlp": ["yt-dlp", "ffmpeg"],
}

PROGRESS_WIDTH = 50
SPINNER_INTERVAL = 0.1  # seconds between spinner updates
MAX_RETRIES = 3
RATE_CALCULATION_WINDOW = 5  # seconds to average download rate
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# ------------------------------
# Nord‑Themed Colors & Console Setup
# ------------------------------
class Colors:
    """Nord-themed ANSI color codes for terminal output"""
    HEADER = "\033[38;5;81m"    # Blue (Nord9)
    GREEN = "\033[38;5;108m"    # Green (Nord14)
    YELLOW = "\033[38;5;179m"   # Yellow (Nord13)
    RED = "\033[38;5;174m"      # Red (Nord11)
    BLUE = "\033[38;5;67m"      # Deep Blue (Nord10)
    CYAN = "\033[38;5;110m"     # Light Blue (Nord8)
    MAGENTA = "\033[38;5;139m"  # Purple (Nord15)
    WHITE = "\033[38;5;253m"    # Light foreground (Nord4)
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ENDC = "\033[0m"

console = Console()

def print_header(message: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(message, font="slant")
    console.print(ascii_art, style=f"bold {Colors.HEADER}")

def print_section(message: str) -> None:
    """Print a formatted section header."""
    console.print(f"\n[bold {Colors.BLUE}]{message}[/bold {Colors.BLUE}]")

def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{Colors.CYAN}]{message}[/{Colors.CYAN}]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {Colors.GREEN}]✓ {message}[/{Colors.GREEN}]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {Colors.YELLOW}]⚠ {message}[/{Colors.YELLOW}]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {Colors.RED}]✗ {message}[/{Colors.RED}]")

def format_size(num_bytes: float) -> str:
    """Convert bytes to a human‑readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"

# ------------------------------
# Progress Tracking Classes
# ------------------------------
class ProgressBar:
    """Thread‑safe progress bar with transfer rate and ETA display."""
    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = max(1, total)
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_update_value = 0
        self.rates: List[float] = []
        self._lock = threading.Lock()
        self._display()

    def update(self, amount: int) -> None:
        with self._lock:
            self.current = min(self.current + amount, self.total)
            now = time.time()
            if now - self.last_update_time >= 0.5:
                delta = self.current - self.last_update_value
                rate = delta / (now - self.last_update_time)
                self.rates.append(rate)
                if len(self.rates) > 5:
                    self.rates.pop(0)
                self.last_update_time = now
                self.last_update_value = self.current
            self._display()

    def _display(self) -> None:
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100
        elapsed = time.time() - self.start_time
        avg_rate = sum(self.rates) / max(1, len(self.rates))
        eta = (self.total - self.current) / max(0.1, avg_rate) if avg_rate > 0 else 0
        if eta > 3600:
            eta_str = f"{eta / 3600:.1f}h"
        elif eta > 60:
            eta_str = f"{eta / 60:.1f}m"
        else:
            eta_str = f"{eta:.0f}s"
        status = (
            f"\r{Colors.CYAN}{self.desc}:{Colors.ENDC} |{Colors.BLUE}{bar}{Colors.ENDC}| "
            f"{Colors.WHITE}{percent:5.1f}%{Colors.ENDC} "
            f"({format_size(self.current)}/{format_size(self.total)}) "
            f"[{Colors.GREEN}{format_size(avg_rate)}/s{Colors.ENDC}] [ETA: {eta_str}]"
        )
        sys.stdout.write(status)
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write("\n")

class Spinner:
    """Thread‑safe spinner for indeterminate progress."""
    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = f"{elapsed:.1f}s"
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
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            if elapsed > 3600:
                time_str = f"{elapsed / 3600:.1f}h"
            elif elapsed > 60:
                time_str = f"{elapsed / 60:.1f}m"
            else:
                time_str = f"{elapsed:.1f}s"
            sys.stdout.write("\r" + " " * TERM_WIDTH + "\r")
            if success:
                sys.stdout.write(f"{Colors.GREEN}✓{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} {Colors.GREEN}completed{Colors.ENDC} in {time_str}\n")
            else:
                sys.stdout.write(f"{Colors.RED}✗{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} {Colors.RED}failed{Colors.ENDC} after {time_str}\n")
            sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)

# ------------------------------
# Helper Functions
# ------------------------------
def run_command(cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True,
                capture_output: bool = False, verbose: bool = False) -> subprocess.CompletedProcess:
    if verbose:
        print_step(f"Executing: {' '.join(cmd)}")
    try:
        return subprocess.run(cmd, env=env or os.environ.copy(), check=check, text=True, capture_output=capture_output)
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stderr") and e.stderr:
            print_error(f"Error details: {e.stderr.strip()}")
        raise

def ensure_directory(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        sys.exit(1)

def get_file_size(url: str) -> int:
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
    try:
        result = run_command(["yt-dlp", "--print", "filesize", url], capture_output=True, check=False)
        if result.stdout.strip() and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
        result = run_command(["yt-dlp", "--print", "duration", url], capture_output=True, check=False)
        if result.stdout.strip() and result.stdout.strip().replace(".", "", 1).isdigit():
            duration = float(result.stdout.strip())
            return int(duration * 60 * 10 * 1024 * 1024)
        return 100 * 1024 * 1024
    except Exception as e:
        print_warning(f"Could not estimate video size: {e}")
        return 100 * 1024 * 1024

def check_root_privileges() -> bool:
    if os.geteuid() != 0:
        print_warning("This script is not running with root privileges.")
        print_step("Some features may require root access.")
        return False
    return True

def check_dependencies(required: List[str]) -> bool:
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        print_warning(f"Missing dependencies: {', '.join(missing)}")
        return False
    return True

def install_dependencies(deps: List[str], verbose: bool = False) -> bool:
    print_section(f"Installing Dependencies: {', '.join(deps)}")
    try:
        with Spinner("Updating package lists") as spinner:
            run_command(["apt", "update"], verbose=verbose, capture_output=not verbose)
        with Spinner(f"Installing {len(deps)} packages") as spinner:
            run_command(["apt", "install", "-y"] + deps, verbose=verbose, capture_output=not verbose)
        missing = [cmd for cmd in deps if not shutil.which(cmd)]
        if missing:
            print_error(f"Failed to install: {', '.join(missing)}")
            return False
        print_success(f"Successfully installed: {', '.join(deps)}")
        return True
    except Exception as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def check_internet_connectivity() -> bool:
    try:
        result = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False, capture_output=True)
        return result.returncode == 0
    except Exception:
        return False

# ------------------------------
# Download Functions
# ------------------------------
def download_with_wget(url: str, output_dir: str, verbose: bool = False) -> bool:
    try:
        file_size = get_file_size(url)
        filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
        ensure_directory(output_dir)
        output_path = os.path.join(output_dir, filename)
        print_step(f"Downloading: {url}")
        print_step(f"Destination: {output_path}")
        if file_size:
            print_step(f"File size: {format_size(file_size)}")
        else:
            print_warning("File size unknown. Progress will be indeterminate.")
        if file_size > 0:
            progress = ProgressBar(file_size, "Downloading")
            def progress_callback(block_count: int, block_size: int, total_size: int) -> None:
                progress.update(block_size)
            import urllib.request
            urllib.request.urlretrieve(url, output_path, reporthook=progress_callback)
        else:
            with Spinner(f"Downloading {filename}") as spinner:
                run_command(["wget", "-q", "-O", output_path, url], verbose=verbose)
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
    try:
        ensure_directory(output_dir)
        estimated_size = estimate_youtube_size(url)
        if estimated_size:
            print_step(f"Estimated size: {format_size(estimated_size)}")
        try:
            result = run_command(["yt-dlp", "--print", "title", url], capture_output=True)
            video_title = result.stdout.strip()
            print_step(f"Video title: {video_title}")
        except Exception:
            video_title = "Unknown video"
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-f", "bestvideo+bestaudio",
            "--merge-output-format", "mp4",
            "-o", output_template,
        ]
        if verbose:
            cmd.append("--verbose")
        cmd.append(url)
        if verbose:
            with Spinner(f"Downloading {video_title}") as spinner:
                run_command(cmd, verbose=True)
        else:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True
            )
            progress = None
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                sys.stdout.write("\r" + " " * TERM_WIDTH + "\r")
                if "[download]" in line and "%" in line:
                    try:
                        pct = float(line.split()[1].rstrip(",").rstrip("%"))
                        if progress is None and estimated_size > 0:
                            progress = ProgressBar(100, "Downloading")
                        if progress is not None:
                            progress.current = pct
                            progress._display()
                    except Exception:
                        pass
                elif "Downloading video" in line or "Downloading audio" in line:
                    if progress is not None:
                        progress.desc = line.strip()
                        progress._display()
            process.wait()
            if process.returncode != 0:
                print_error("Download failed.")
                return False
        print_success(f"Successfully downloaded {video_title}")
        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False

# ------------------------------
# Interactive Menu
# ------------------------------
def download_menu() -> None:
    print_header("Universal Downloader")
    console.print(f"[{Colors.CYAN}]Select download method:[/{Colors.CYAN}]")
    console.print(f"  [bold]{Colors.BOLD}1){Colors.ENDC} wget  - Download files from the web")
    console.print(f"  [bold]{Colors.BOLD}2){Colors.ENDC} yt-dlp - Download YouTube videos/playlists")
    console.print(f"  [bold]{Colors.BOLD}q){Colors.ENDC} Quit\n")
    while True:
        choice = input(f"{Colors.BOLD}Enter your choice (1, 2, or q): {Colors.ENDC}").strip().lower()
        if choice == "1":
            deps = DEPENDENCIES["common"] + DEPENDENCIES["wget"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install dependencies.")
                        return
                else:
                    print_error("Missing dependencies and not running as root to install them.")
                    return
            url = input(f"\n{Colors.BOLD}Enter URL to download: {Colors.ENDC}").strip()
            if not url:
                print_error("URL cannot be empty.")
                return
            output_dir = input(f"{Colors.BOLD}Enter output directory [{DEFAULT_DOWNLOAD_DIR}]: {Colors.ENDC}").strip()
            if not output_dir:
                output_dir = DEFAULT_DOWNLOAD_DIR
            download_with_wget(url, output_dir)
            break
        elif choice == "2":
            deps = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]
            if not check_dependencies(deps):
                if os.geteuid() == 0:
                    if not install_dependencies(deps):
                        print_error("Failed to install dependencies.")
                        return
                else:
                    print_error("Missing dependencies and not running as root to install them.")
                    return
            url = input(f"\n{Colors.BOLD}Enter YouTube URL: {Colors.ENDC}").strip()
            if not url:
                print_error("URL cannot be empty.")
                return
            output_dir = input(f"{Colors.BOLD}Enter output directory [{DEFAULT_DOWNLOAD_DIR}]: {Colors.ENDC}").strip()
            if not output_dir:
                output_dir = DEFAULT_DOWNLOAD_DIR
            download_with_yt_dlp(url, output_dir)
            break
        elif choice in ("q", "quit", "exit"):
            print_step("Exiting...")
            return
        else:
            print_error("Invalid selection. Please choose 1, 2, or q.")

# ------------------------------
# Cleanup & Signal Handling
# ------------------------------
def cleanup() -> None:
    """Cleanup tasks before exit."""
    pass

atexit.register(lambda: console.print("[dim]Cleaning up resources...[/dim]"))
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(128 + sig))

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.group()
def cli() -> None:
    """Enhanced Universal Downloader Script"""
    print_header(f"Universal Downloader v{VERSION}")
    console.print(f"System: [bold {Colors.CYAN}]{platform.system()} {platform.release()}[/{Colors.CYAN}]")
    console.print(f"User: [bold {Colors.CYAN}]{os.environ.get('USER', 'unknown')}[/{Colors.CYAN}]")
    console.print(f"Time: [bold {Colors.CYAN}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/{Colors.CYAN}]")
    console.print(f"Working directory: [bold {Colors.CYAN}]{os.getcwd()}[/{Colors.CYAN}]")
    if not check_internet_connectivity():
        print_error("No internet connectivity detected. Please check your connection.")
        sys.exit(1)
    # Root privileges are recommended but not forced for downloads
    check_root_privileges()

@cli.command()
@click.argument("url")
@click.option("-o", "--output-dir", default=DEFAULT_DOWNLOAD_DIR, help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
def wget(url: str, output_dir: str, verbose: bool) -> None:
    """Download a file using wget."""
    deps = DEPENDENCIES["common"] + DEPENDENCIES["wget"]
    if not check_dependencies(deps):
        if os.geteuid() == 0:
            if not install_dependencies(deps, verbose):
                print_error("Failed to install dependencies.")
                sys.exit(1)
        else:
            print_error("Missing dependencies and not running as root to install them.")
            sys.exit(1)
    success = download_with_wget(url, output_dir, verbose)
    sys.exit(0 if success else 1)

@cli.command()
@click.argument("url")
@click.option("-o", "--output-dir", default=DEFAULT_DOWNLOAD_DIR, help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
def ytdlp(url: str, output_dir: str, verbose: bool) -> None:
    """Download a video/playlist using yt-dlp."""
    deps = DEPENDENCIES["common"] + DEPENDENCIES["yt-dlp"]
    if not check_dependencies(deps):
        if os.geteuid() == 0:
            if not install_dependencies(deps, verbose):
                print_error("Failed to install dependencies.")
                sys.exit(1)
        else:
            print_error("Missing dependencies and not running as root to install them.")
            sys.exit(1)
    success = download_with_yt_dlp(url, output_dir, verbose)
    sys.exit(0 if success else 1)

@cli.command()
def menu() -> None:
    """Interactive download menu."""
    download_menu()

def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()