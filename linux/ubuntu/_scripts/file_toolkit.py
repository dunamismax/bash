#!/usr/bin/env python3
"""
Enhanced File Operations Toolkit
--------------------------------------------------

An interactive terminal-based utility for comprehensive file management.
This tool provides a streamlined interface for common file operations with
advanced progress tracking and visual feedback using Nord-themed styling.

Features:
  • Copying files/directories with real-time progress tracking
  • Moving files/directories with smart cross-device detection
  • Deleting files/directories with interactive confirmation
  • Finding files with pattern matching and detailed listings
  • Compressing files/directories with compression ratio feedback
  • Calculating file checksums (MD5, SHA1, SHA256, SHA512)
  • Analyzing disk usage with visual summary tables
  • Batch operations for efficient workflows

Usage:
  Run the script and select an operation from the interactive menu.
  Follow the prompts to perform file operations with visual feedback.

Note: Some operations may require root privileges.
Version: 2.0.0
"""

import atexit
import datetime
import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import threading
from datetime import datetime as dt
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any, Union, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.live import Live
    from rich.columns import Columns
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "File Operations Toolkit"
APP_SUBTITLE = "Advanced File Management System"
VERSION = "2.0.0"
HOSTNAME = (
    os.uname().nodename
    if hasattr(os, "uname")
    else os.environ.get("COMPUTERNAME", "Unknown")
)

# Buffer sizes and thresholds
CHUNK_SIZE = 1024 * 1024  # 1 MB for file checksum/compression progress
DEFAULT_BUFFER_SIZE = 8192  # Buffer size for copying operations
COMPRESSION_LEVEL = 9  # tar.gz compression level
RECENT_ACCESS_THRESHOLD = 30  # days threshold
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB
OPERATION_TIMEOUT = 30  # seconds

# File categories by extension
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"}
CODE_EXTENSIONS = {".py", ".js", ".java", ".c", ".cpp", ".h", ".php", ".html", ".css"}
CHECKSUM_ALGORITHMS = ["md5", "sha1", "sha256", "sha512"]

# Terminal dimensions
TERM_WIDTH = shutil.get_terminal_size().columns


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

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
console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class FileOperation:
    """
    Base class for file operations with progress tracking.

    Attributes:
        name: Operation name
        description: Operation description
        source: Source path
        destination: Destination path (if applicable)
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.start_time = 0
        self.end_time = 0

    def start(self) -> None:
        """Mark the start of the operation."""
        self.start_time = time.time()

    def end(self) -> None:
        """Mark the end of the operation."""
        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        """Return the elapsed time of the operation."""
        if self.end_time > 0:
            return self.end_time - self.start_time
        elif self.start_time > 0:
            return time.time() - self.start_time
        return 0


# ----------------------------------------------------------------
# Console and UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
  __ _ _        _              _ _    _ _   
 / _(_) | ___  | |_ ___   ___ | | | _(_) |_ 
| |_| | |/ _ \ | __/ _ \ / _ \| | |/ / | __|
|  _| | |  __/ | || (_) | (_) | |   <| | |_ 
|_| |_|_|\___|  \__\___/ \___/|_|_|\_\_|\__|
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * min(60, TERM_WIDTH - 10) + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding
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


def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.FROST_2}")


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


def print_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold {NordColors.GREEN}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold {NordColors.YELLOW}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold {NordColors.RED}]✗ {message}[/]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.FROST_2}]• {text}[/{NordColors.FROST_2}]")


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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause until user presses Enter."""
    console.input(f"\n[{NordColors.PURPLE}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Prompt user for input with Nord styling."""
    return Prompt.ask(f"[bold {NordColors.FROST_2}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Prompt user for a choice with Nord styling."""
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """Prompt user for yes/no confirmation with Nord styling."""
    return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a table for menu options with Nord styling."""
    table = Table(
        title=title,
        title_style=f"bold {NordColors.FROST_1}",
        box=None,
        expand=True,
        highlight=True,
        show_header=False,
        border_style=NordColors.FROST_3,
    )

    table.add_column(
        "Option", style=f"bold {NordColors.FROST_3}", justify="right", width=4
    )
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for key, desc in options:
        table.add_row(key, desc)

    return table


def create_info_panel() -> Panel:
    """Create an information panel with system details."""
    content = Text.assemble(
        ("System: ", f"bold {NordColors.FROST_2}"),
        (f"{HOSTNAME}\n", f"{NordColors.SNOW_STORM_1}"),
        ("Time: ", f"bold {NordColors.FROST_2}"),
        (f"{dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n", f"{NordColors.SNOW_STORM_1}"),
        ("Root: ", f"bold {NordColors.FROST_2}"),
        (f"{'Yes' if check_root_privileges() else 'No'}", f"{NordColors.SNOW_STORM_1}"),
    )

    return Panel(
        content,
        title=f"[bold {NordColors.FROST_1}]System Info[/]",
        border_style=Style(color=NordColors.FROST_4),
        padding=(1, 2),
    )


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking system with Nord styling."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=None,
                complete_style=NordColors.FROST_2,
                finished_style=NordColors.GREEN,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"{NordColors.FROST_3}starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self) -> None:
        self.progress.start()

    def stop(self) -> None:
        self.progress.stop()


class Spinner:
    """Thread-safe spinner for indeterminate progress with Nord styling."""

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
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.FROST_1}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_2}]{self.message}[/] [[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

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
            time_str = format_time(elapsed)
            console.print("\r" + " " * TERM_WIDTH, end="\r")
            if success:
                console.print(
                    f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.GREEN}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.RED}]failed[/] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def format_size(num_bytes: float) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def get_file_category(filename: str) -> str:
    """Determine file category based on extension."""
    ext = Path(filename).suffix.lower()
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    elif ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in VIDEO_EXTENSIONS:
        return "video"
    elif ext in AUDIO_EXTENSIONS:
        return "audio"
    elif ext in ARCHIVE_EXTENSIONS:
        return "archive"
    elif ext in CODE_EXTENSIONS:
        return "code"
    return "other"


def format_date(timestamp: float) -> str:
    """Return formatted date string from timestamp."""
    return dt.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def check_root_privileges() -> bool:
    """Check if running as root."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        # Windows systems don't have geteuid
        return False


def ensure_root() -> None:
    """Warn if not running with root privileges."""
    if not check_root_privileges():
        print_warning("Some operations may require root privileges.")
        print_info("Consider running with sudo for full functionality.")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
    """
    try:
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
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_message("Performing cleanup tasks...", NordColors.FROST_3)
    # Add any additional cleanup steps here


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal_handler)

# Register cleanup function
atexit.register(cleanup)


# ----------------------------------------------------------------
# File Operation Functions
# ----------------------------------------------------------------
def copy_item(src: str, dest: str) -> bool:
    """
    Copy a file or directory with progress tracking.

    Args:
        src: Source path
        dest: Destination path

    Returns:
        True if copy was successful, False otherwise
    """
    print_section(f"Copying {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False

    try:
        if Path(src).is_dir():
            # Copy directory
            total_size = sum(
                f.stat().st_size for f in Path(src).rglob("*") if f.is_file()
            )
            if total_size == 0:
                print_warning("No files to copy.")
                return True

            start_time = time.time()
            with ProgressManager() as progress:
                task = progress.add_task("Copying files", total=total_size)

                for root, dirs, files in os.walk(src):
                    rel_path = os.path.relpath(root, src)
                    target_dir = (
                        Path(dest) / rel_path if rel_path != "." else Path(dest)
                    )
                    target_dir.mkdir(parents=True, exist_ok=True)

                    for file in files:
                        src_file = Path(root) / file
                        dest_file = target_dir / file

                        with src_file.open("rb") as fsrc, dest_file.open("wb") as fdst:
                            while True:
                                buf = fsrc.read(DEFAULT_BUFFER_SIZE)
                                if not buf:
                                    break
                                fdst.write(buf)
                                progress.update(task, advance=len(buf))

                        shutil.copystat(src_file, dest_file)

            elapsed = time.time() - start_time
            print_success(
                f"Copied directory ({format_size(total_size)}) in {format_time(elapsed)}"
            )

        else:
            # Copy file
            file_size = Path(src).stat().st_size
            start_time = time.time()

            with ProgressManager() as progress:
                task = progress.add_task(f"Copying {Path(src).name}", total=file_size)

                with open(src, "rb") as fsrc, open(dest, "wb") as fdst:
                    while True:
                        buf = fsrc.read(DEFAULT_BUFFER_SIZE)
                        if not buf:
                            break
                        fdst.write(buf)
                        progress.update(task, advance=len(buf))

            shutil.copystat(src, dest)
            elapsed = time.time() - start_time
            print_success(
                f"Copied file ({format_size(file_size)}) in {format_time(elapsed)}"
            )

        return True

    except Exception as e:
        print_error(f"Error copying {src}: {e}")
        return False


def move_item(src: str, dest: str) -> bool:
    """
    Move a file or directory with progress tracking.

    Args:
        src: Source path
        dest: Destination path

    Returns:
        True if move was successful, False otherwise
    """
    print_section(f"Moving {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False

    try:
        # Check if source and destination are on the same filesystem
        same_filesystem = (
            os.stat(src).st_dev == os.stat(os.path.dirname(dest) or ".").st_dev
        )

        if same_filesystem:
            # Simple rename operation if on same filesystem
            start_time = time.time()
            os.rename(src, dest)
            elapsed = time.time() - start_time
            print_success(f"Moved {src} to {dest} in {format_time(elapsed)}")

        else:
            # Cross-filesystem move: copy then delete
            print_step("Cross-filesystem move: performing copy then delete")

            if not copy_item(src, dest):
                return False

            # Delete source after successful copy
            if Path(src).is_dir():
                shutil.rmtree(src)
            else:
                os.remove(src)

            print_success(f"Moved {src} to {dest} by copying then deleting source")

        return True

    except Exception as e:
        print_error(f"Error moving {src}: {e}")
        return False


def delete_item(path: str, force: bool = False) -> bool:
    """
    Delete a file or directory with confirmation.

    Args:
        path: Path to delete
        force: Skip confirmation if True

    Returns:
        True if deletion was successful, False otherwise
    """
    print_section(f"Deleting {Path(path).name}")
    if not Path(path).exists():
        print_error(f"Path not found: {path}")
        return False

    if not force and not get_user_confirmation(
        f"Are you sure you want to delete {path}?"
    ):
        print_step("Deletion cancelled")
        return False

    try:
        start_time = time.time()

        if Path(path).is_dir():
            shutil.rmtree(path)
        else:
            os.remove(path)

        elapsed = time.time() - start_time
        print_success(f"Deleted {path} in {format_time(elapsed)}")
        return True

    except Exception as e:
        print_error(f"Error deleting {path}: {e}")
        return False


def find_files() -> None:
    """Search for files matching a pattern with optional details."""
    directory = get_user_input("Enter directory to search")
    if not directory:
        print_error("Directory path cannot be empty")
        return

    pattern = get_user_input("Enter search pattern (wildcards allowed)", ".*")
    details = get_user_confirmation("Show detailed file information?")

    print_section(f"Searching for files in {directory}")
    if not Path(directory).exists():
        print_error(f"Directory not found: {directory}")
        return

    matches = []
    regex = re.compile(pattern.replace("*", ".*").replace("?", "."), re.IGNORECASE)

    with Spinner("Searching for files") as spinner:
        for root, _, files in os.walk(directory):
            for file in files:
                if regex.search(file):
                    matches.append(str(Path(root) / file))

    print_success(f"Found {len(matches)} matching files")

    if details and matches:
        table = Table(
            title="Search Results",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
            highlight=True,
        )

        table.add_column("File Path", style=f"{NordColors.SNOW_STORM_1}")
        table.add_column("Size", style=f"{NordColors.FROST_2}", justify="right")
        table.add_column("Modified", style=f"{NordColors.FROST_1}")
        table.add_column("Type", style=f"{NordColors.FROST_3}")

        for match in matches[:100]:  # Limit to first 100 results
            try:
                p = Path(match)
                size = format_size(p.stat().st_size)
                modified = format_date(p.stat().st_mtime)
                ftype = get_file_category(match)
                table.add_row(str(p), size, modified, ftype)
            except Exception as e:
                print_error(f"Error reading {match}: {e}")

        console.print(table)

        if len(matches) > 100:
            print_warning(f"Showing first 100 of {len(matches)} matches")

    elif not details:
        # Simple list view
        for match in matches[:100]:
            console.print(
                f"[{NordColors.SNOW_STORM_1}]{match}[/{NordColors.SNOW_STORM_1}]"
            )

        if len(matches) > 100:
            print_warning(f"Showing first 100 of {len(matches)} matches")


def compress_files() -> bool:
    """
    Compress a file or directory into a tar.gz archive with progress tracking.

    Returns:
        True if compression was successful, False otherwise
    """
    src = get_user_input("Enter source file/directory to compress")
    if not src:
        print_error("Source path cannot be empty")
        return False

    dest = get_user_input("Enter destination archive path (without extension)")
    if not dest:
        print_error("Destination path cannot be empty")
        return False

    if not dest.endswith((".tar.gz", ".tgz")):
        dest = f"{dest}.tar.gz"

    print_section(f"Compressing {Path(src).name}")

    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False

    # Calculate total size
    total_size = 0
    if Path(src).is_dir():
        with Spinner("Calculating total size") as spinner:
            total_size = sum(
                f.stat().st_size for f in Path(src).rglob("*") if f.is_file()
            )
    else:
        total_size = Path(src).stat().st_size

    if total_size == 0:
        print_warning("No files to compress.")
        return True

    start_time = time.time()

    try:
        with ProgressManager() as progress:
            task = progress.add_task("Compressing files", total=total_size)

            with open(dest, "wb") as f_out:
                with tarfile.open(
                    fileobj=f_out, mode="w:gz", compresslevel=COMPRESSION_LEVEL
                ) as tar:

                    def filter_func(tarinfo):
                        if tarinfo.size:
                            progress.update(task, advance=tarinfo.size)
                        return tarinfo

                    tar.add(src, arcname=Path(src).name, filter=filter_func)

        elapsed = time.time() - start_time
        out_size = Path(dest).stat().st_size
        ratio = (total_size - out_size) / total_size * 100 if total_size > 0 else 0

        result_panel = Panel(
            Text.from_markup(
                f"[{NordColors.SNOW_STORM_1}]Original size: {format_size(total_size)}[/]\n"
                f"[{NordColors.SNOW_STORM_1}]Compressed size: {format_size(out_size)}[/]\n"
                f"[bold {NordColors.FROST_2}]Compression ratio: {ratio:.1f}% space saved[/]"
            ),
            title=f"[bold {NordColors.GREEN}]Compression Complete[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )

        print_success(f"Compressed to {dest} in {format_time(elapsed)}")
        console.print(result_panel)

        return True

    except Exception as e:
        print_error(f"Error compressing {src}: {e}")

        # Clean up failed archive
        if Path(dest).exists():
            try:
                Path(dest).unlink()
            except Exception:
                pass

        return False


def calculate_checksum() -> bool:
    """
    Calculate and display the checksum of a file using a selected algorithm.

    Returns:
        True if checksum calculation was successful, False otherwise
    """
    path = get_user_input("Enter file path for checksum calculation")
    if not path:
        print_error("File path cannot be empty")
        return False

    # Create algorithm selection menu
    algorithm_options = [
        (str(i + 1), algo.upper()) for i, algo in enumerate(CHECKSUM_ALGORITHMS)
    ]
    console.print(create_menu_table("Select Checksum Algorithm", algorithm_options))

    choice = get_user_input("Select algorithm (1-4)", "1")

    try:
        algorithm = CHECKSUM_ALGORITHMS[int(choice) - 1]
    except (ValueError, IndexError):
        print_error("Invalid selection. Using MD5 as default.")
        algorithm = "md5"

    print_section(f"Calculating {algorithm.upper()} checksum for {Path(path).name}")

    if not Path(path).exists() or Path(path).is_dir():
        print_error("Please specify an existing file for checksum calculation.")
        return False

    try:
        file_size = Path(path).stat().st_size
        hash_func = hashlib.new(algorithm)
        start_time = time.time()

        with ProgressManager() as progress:
            task = progress.add_task("Reading file", total=file_size)

            with open(path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    hash_func.update(chunk)
                    progress.update(task, advance=len(chunk))

        checksum = hash_func.hexdigest()
        elapsed = time.time() - start_time

        result_panel = Panel(
            Text.from_markup(f"[bold {NordColors.FROST_2}]{checksum}[/]"),
            title=f"[bold {NordColors.FROST_1}]{algorithm.upper()} Checksum[/]",
            border_style=Style(color=NordColors.GREEN),
            padding=(1, 2),
        )

        console.print(result_panel)
        console.print(f"Time taken: {format_time(elapsed)}")

        return True

    except Exception as e:
        print_error(f"Error calculating checksum: {e}")
        return False


def disk_usage() -> bool:
    """
    Analyze disk usage of a directory and display summary information.

    Returns:
        True if analysis was successful, False otherwise
    """
    directory = get_user_input("Enter directory to analyze")
    if not directory:
        print_error("Directory path cannot be empty")
        return False

    threshold_mb = get_user_input("Size threshold in MB (highlight if exceeded)", "100")

    try:
        threshold = int(threshold_mb) * 1024 * 1024
    except ValueError:
        print_warning("Invalid threshold value. Using default (100 MB)")
        threshold = LARGE_FILE_THRESHOLD

    print_section(f"Analyzing disk usage in {directory}")

    if not Path(directory).exists():
        print_error(f"Directory not found: {directory}")
        return False

    total_size = 0
    file_count = 0
    large_files = []
    category_sizes: Dict[str, int] = {}

    with Spinner("Analyzing directory") as spinner:
        for root, _, files in os.walk(directory):
            for file in files:
                try:
                    fp = Path(root) / file
                    size = fp.stat().st_size
                    total_size += size
                    file_count += 1

                    category = get_file_category(file)
                    category_sizes[category] = category_sizes.get(category, 0) + size

                    if size > threshold:
                        large_files.append((str(fp), size))
                except Exception:
                    continue

    # Create summary tables with Nord styling
    summary_table = Table(
        title="Disk Usage Summary",
        title_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
    )

    summary_table.add_column("Metric", style=f"{NordColors.FROST_2}")
    summary_table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    summary_table.add_row("Total files", str(file_count))
    summary_table.add_row("Total size", format_size(total_size))
    summary_table.add_row(
        "Large files (>" + format_size(threshold) + ")", str(len(large_files))
    )

    console.print(summary_table)

    # Create category table
    if category_sizes:
        category_table = Table(
            title="Size by File Type",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
        )

        category_table.add_column("Category", style=f"{NordColors.FROST_2}")
        category_table.add_column(
            "Size", style=f"{NordColors.SNOW_STORM_1}", justify="right"
        )
        category_table.add_column(
            "Percentage", style=f"{NordColors.FROST_1}", justify="right"
        )

        for category, size in sorted(
            category_sizes.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (size / total_size * 100) if total_size > 0 else 0
            category_table.add_row(
                category.capitalize(), format_size(size), f"{percentage:.1f}%"
            )

        console.print(category_table)

    # Create large files table
    if large_files:
        large_files.sort(key=lambda x: x[1], reverse=True)

        large_file_table = Table(
            title=f"Large Files (>{format_size(threshold)})",
            title_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
        )

        large_file_table.add_column("File", style=f"{NordColors.SNOW_STORM_1}")
        large_file_table.add_column("Size", style=f"{NordColors.RED}", justify="right")

        for file_path, size in large_files[:10]:
            large_file_table.add_row(file_path, format_size(size))

        console.print(large_file_table)

        if len(large_files) > 10:
            print_info(f"Showing top 10 of {len(large_files)} large files")

    return True


def print_section(title: str) -> None:
    """Print a formatted section header with Nord styling."""
    border = "═" * min(TERM_WIDTH - 4, 80)
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")


def print_info(message: str) -> None:
    """Display an informational message with Nord styling."""
    console.print(f"[{NordColors.FROST_2}]ℹ {message}[/{NordColors.FROST_2}]")


# ----------------------------------------------------------------
# Menu System Functions
# ----------------------------------------------------------------
def copy_menu() -> None:
    """Handle file copy operations with interactive prompts."""
    clear_screen()
    console.print(create_header())
    print_header("Copy Files")

    src = get_user_input("Enter source file/directory path")
    if not src or not Path(src).exists():
        print_error("Invalid source path")
        return

    dest = get_user_input("Enter destination path")
    if not dest:
        print_error("Destination path cannot be empty")
        return

    # Create parent directory if necessary
    if Path(src).is_file() and not Path(dest).parent.exists():
        if get_user_confirmation(f"Create parent directory {Path(dest).parent}?"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)

    # If destination is a directory, append source filename
    if Path(dest).is_dir():
        dest = str(Path(dest) / Path(src).name)
        print_info(f"Full destination path: {dest}")

    # Perform the copy operation
    if not copy_item(src, dest):
        print_error("Copy operation failed")
    else:
        print_success("Copy operation completed successfully")


def move_menu() -> None:
    """Handle file move operations with interactive prompts."""
    clear_screen()
    console.print(create_header())
    print_header("Move Files")

    src = get_user_input("Enter source file/directory path")
    if not src or not Path(src).exists():
        print_error("Invalid source path")
        return

    dest = get_user_input("Enter destination path")
    if not dest:
        print_error("Destination path cannot be empty")
        return

    # Create parent directory if necessary
    if Path(src).is_file() and not Path(dest).parent.exists():
        if get_user_confirmation(f"Create parent directory {Path(dest).parent}?"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)

    # If destination is a directory, append source filename
    if Path(dest).is_dir():
        dest = str(Path(dest) / Path(src).name)
        print_info(f"Full destination path: {dest}")

    # Perform the move operation
    if not move_item(src, dest):
        print_error("Move operation failed")
    else:
        print_success("Move operation completed successfully")


def delete_menu() -> None:
    """Handle file deletion operations with interactive prompts."""
    clear_screen()
    console.print(create_header())
    print_header("Delete Files")

    path = get_user_input("Enter file/directory path to delete")
    if not path or not Path(path).exists():
        print_error("Invalid path")
        return

    force = get_user_confirmation("Skip confirmation for deletion?")

    # Perform the delete operation
    if not delete_item(path, force):
        print_error("Delete operation failed or cancelled")
    else:
        print_success("Delete operation completed successfully")


def batch_operation_menu() -> None:
    """Handle batch file operations with interactive prompts."""
    clear_screen()
    console.print(create_header())
    print_header("Batch Operations")

    print_section("Select Operation Type")
    options = [
        ("1", "Batch Copy"),
        ("2", "Batch Move"),
        ("3", "Batch Delete"),
        ("0", "Back to Main Menu"),
    ]
    console.print(create_menu_table("Operations", options))

    choice = get_user_input("Select operation type (0-3)", "0")
    if choice == "0":
        return

    # Collect source paths
    sources = []
    print_section("Add Source Paths (enter empty line to finish)")

    while True:
        src = get_user_input("Enter source path")
        if not src:
            break

        if not Path(src).exists():
            print_warning(f"Path not found: {src} (skipping)")
            continue

        sources.append(src)

    if not sources:
        print_error("No valid source paths provided")
        return

    # Handle different batch operations
    if choice in ("1", "2"):  # Copy or Move
        dest = get_user_input("Enter destination directory")
        if not dest:
            print_error("Destination path cannot be empty")
            return

        # Create destination directory if necessary
        if not Path(dest).exists():
            if get_user_confirmation(f"Create destination directory {dest}?"):
                Path(dest).mkdir(parents=True, exist_ok=True)
            else:
                return

        # Process each source
        for src in sources:
            target = str(Path(dest) / Path(src).name)
            if choice == "1":  # Copy
                if not copy_item(src, target):
                    print_warning(f"Failed to copy {src}")
            else:  # Move
                if not move_item(src, target):
                    print_warning(f"Failed to move {src}")

    elif choice == "3":  # Delete
        force = get_user_confirmation("Skip confirmation for each file?")

        # Process each source for deletion
        for src in sources:
            if not delete_item(src, force):
                print_warning(f"Failed to delete {src}")

    print_success("Batch operation completed")


def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        console.print(create_header())

        # Display system information
        console.print(create_info_panel())

        # Main menu options
        options = [
            ("1", "Copy Files/Directories"),
            ("2", "Move Files/Directories"),
            ("3", "Delete Files/Directories"),
            ("4", "Find Files"),
            ("5", "Compress Files/Directories"),
            ("6", "Calculate File Checksum"),
            ("7", "Analyze Disk Usage"),
            ("8", "Batch Operations"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", options))
        choice = get_user_input("Enter your choice (0-8):", "0")

        # Handle menu selection
        if choice == "1":
            copy_menu()
            pause()
        elif choice == "2":
            move_menu()
            pause()
        elif choice == "3":
            delete_menu()
            pause()
        elif choice == "4":
            find_files()
            pause()
        elif choice == "5":
            compress_files()
            pause()
        elif choice == "6":
            calculate_checksum()
            pause()
        elif choice == "7":
            disk_usage()
            pause()
        elif choice == "8":
            batch_operation_menu()
            pause()
        elif choice == "0":
            clear_screen()

            # Farewell message
            farewell_panel = Panel(
                Text.from_markup(
                    f"[bold {NordColors.FROST_2}]Thank you for using the File Operations Toolkit.[/]\n"
                    f"[{NordColors.SNOW_STORM_1}]Version {VERSION}[/]"
                ),
                border_style=Style(color=NordColors.FROST_1),
                padding=(1, 2),
                title=f"[bold {NordColors.FROST_1}]Goodbye![/]",
            )

            console.print(farewell_panel)
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main application entry point with error handling."""
    try:
        # Check for any prerequisites
        ensure_root()
        main_menu()
    except KeyboardInterrupt:
        print_warning("\nScript interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
