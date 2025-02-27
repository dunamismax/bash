#!/usr/bin/env python3
"""
Enhanced File Operations Toolkit

A comprehensive command-line tool for file management and system operations that provides
robust functionality, user-friendly progress tracking, and clear feedback. This toolkit
offers the following operations:

Operations:
  • copy     - Copy files or directories with progress tracking
  • move     - Move files or directories with progress tracking
  • delete   - Delete files or directories with confirmation
  • find     - Search for files with pattern matching and metadata display
  • compress - Compress files or directories with compression ratio feedback
  • checksum - Calculate file checksums with multiple algorithm support
  • du       - Disk usage analysis with visualization and insights

Features:
  • Thread-safe progress bars for all operations
  • Nord-themed color output for better readability
  • Comprehensive error handling with clear feedback
  • Signal handling for graceful interruption
  • Resource monitoring during operations

Note: Some operations may require root privileges depending on file permissions.
"""

import argparse
import datetime
import hashlib
import os
import shutil
import signal
import stat
import sys
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

#####################################
# Configuration
#####################################

# Operation-specific settings
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
DEFAULT_BUFFER_SIZE = 8192  # Buffer size for file operations
PROGRESS_WIDTH = 50  # Width of progress bar
COMPRESSION_LEVEL = 9  # Compression level for tar.gz (1-9)
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)  # Maximum worker threads

# File extensions categories
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"}
CODE_EXTENSIONS = {".py", ".js", ".java", ".c", ".cpp", ".h", ".php", ".html", ".css"}

# Time thresholds (in days)
RECENT_ACCESS_THRESHOLD = 30  # Files accessed within this many days are "recent"
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB

# Checksum algorithms
CHECKSUM_ALGORITHMS = ["md5", "sha1", "sha256", "sha512"]

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """
    Nord-themed ANSI color codes for terminal output.
    Based on the Nord color palette (https://www.nordtheme.com/)
    """

    # Nord palette
    POLAR_NIGHT_1 = "\033[38;2;46;52;64m"  # Dark base color
    POLAR_NIGHT_2 = "\033[38;2;59;66;82m"  # Lighter dark base color
    SNOW_STORM_1 = "\033[38;2;216;222;233m"  # Light base color
    SNOW_STORM_2 = "\033[38;2;229;233;240m"  # Lighter base color
    FROST_1 = "\033[38;2;143;188;187m"  # Light blue / cyan
    FROST_2 = "\033[38;2;136;192;208m"  # Blue
    FROST_3 = "\033[38;2;129;161;193m"  # Dark blue
    FROST_4 = "\033[38;2;94;129;172m"  # Navy blue
    AURORA_RED = "\033[38;2;191;97;106m"  # Red
    AURORA_ORANGE = "\033[38;2;208;135;112m"  # Orange
    AURORA_YELLOW = "\033[38;2;235;203;139m"  # Yellow
    AURORA_GREEN = "\033[38;2;163;190;140m"  # Green
    AURORA_PURPLE = "\033[38;2;180;142;173m"  # Purple

    # Functional color aliases
    HEADER = FROST_4
    INFO = FROST_2
    SUCCESS = AURORA_GREEN
    WARNING = AURORA_YELLOW
    ERROR = AURORA_RED
    PROCESSING = FROST_3
    DETAIL = SNOW_STORM_1
    EMPHASIS = AURORA_PURPLE
    MUTED = POLAR_NIGHT_2

    # Text styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"

    # Background colors
    BG_DARK = "\033[48;2;46;52;64m"
    BG_LIGHT = "\033[48;2;216;222;233m"


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def set_current(self, value: int) -> None:
        """Set current progress value"""
        with self._lock:
            self.current = min(value, self.total)
            self._display()

    def _format_size(self, bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total) if self.total > 0 else 0
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100 if self.total > 0 else 0

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0

        sys.stdout.write(
            f"\r{Colors.INFO}{self.desc}: {Colors.ENDC}|{Colors.FROST_2}{bar}{Colors.ENDC}| "
            f"{Colors.EMPHASIS}{percent:>5.1f}%{Colors.ENDC} "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{Colors.SUCCESS}{self._format_size(rate)}/s{Colors.ENDC}] "
            f"[ETA: {Colors.DETAIL}{eta:.0f}s{Colors.ENDC}]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


class ConsoleSpinner:
    """Simple text-based spinner for console output"""

    def __init__(self, message: str = "Processing"):
        self.message = message
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.running = False
        self.spinner_thread = None
        self.counter = 0
        self.start_time = None

    def spin(self) -> None:
        """Display the spinner animation"""
        while self.running:
            frame = self.frames[self.counter % len(self.frames)]
            elapsed = time.time() - self.start_time if self.start_time else 0
            sys.stdout.write(
                f"\r{Colors.PROCESSING}{frame} {self.message} "
                f"{Colors.DETAIL}({elapsed:.1f}s){Colors.ENDC}"
            )
            sys.stdout.flush()
            self.counter += 1
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation in a separate thread"""
        self.running = True
        self.start_time = time.time()
        self.spinner_thread = threading.Thread(target=self.spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()

    def stop(self, message: Optional[str] = None) -> None:
        """Stop the spinner animation"""
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
        if message:
            # Clear the line and print the message
            sys.stdout.write("\r" + " " * 80)  # Clear the line
            sys.stdout.write(f"\r{message}\n")
        else:
            sys.stdout.write("\r" + " " * 80)  # Clear the line
            sys.stdout.write("\r")
        sys.stdout.flush()


#####################################
# Helper Functions
#####################################


def format_size(bytes: int) -> str:
    """
    Format bytes to human readable size.

    Args:
        bytes: Size in bytes

    Returns:
        Formatted string representation of the size
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def print_header(message: str) -> None:
    """
    Print formatted header.

    Args:
        message: Header message to display
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """
    Print formatted section header.

    Args:
        message: Section header message to display
    """
    print(f"\n{Colors.INFO}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def format_time(seconds: float) -> str:
    """
    Format time in seconds to a human-readable format.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"


def get_file_category(filename: str) -> str:
    """
    Determine the category of a file based on its extension.

    Args:
        filename: Name of the file

    Returns:
        Category of the file
    """
    ext = os.path.splitext(filename)[1].lower()
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
    else:
        return "other"


def format_date(timestamp: float) -> str:
    """
    Format a timestamp to a human-readable date string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted date string
    """
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def signal_handler(sig, frame) -> None:
    """
    Handle interrupt signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    print(f"\n{Colors.WARNING}Operation interrupted. Cleaning up...{Colors.ENDC}")
    # You could add additional cleanup logic here if needed
    sys.exit(1)


def get_file_count_and_size(path: str) -> Tuple[int, int]:
    """
    Get the total number of files and size of a directory or file.

    Args:
        path: Path to directory or file

    Returns:
        Tuple containing (file_count, total_size)
    """
    spinner = ConsoleSpinner("Calculating size and file count")
    spinner.start()

    try:
        total_size = 0
        file_count = 0

        if os.path.isfile(path):
            file_count = 1
            total_size = os.path.getsize(path)
        else:
            for root, dirs, files in os.walk(path):
                file_count += len(files)
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)

        spinner.stop(
            f"{Colors.SUCCESS}Found {file_count} files, total size: {format_size(total_size)}{Colors.ENDC}"
        )
        return file_count, total_size
    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error calculating size: {e}{Colors.ENDC}")
        return 0, 0


def run_with_spinner(func: Callable, message: str, *args, **kwargs) -> Any:
    """
    Run a function with a spinner animation.

    Args:
        func: Function to run
        message: Message to display during execution
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function
    """
    spinner = ConsoleSpinner(message)
    spinner.start()

    try:
        result = func(*args, **kwargs)
        spinner.stop()
        return result
    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error: {e}{Colors.ENDC}")
        raise


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """
    Check if script is run with root privileges when needed.

    Returns:
        True if running as root or root not needed, False otherwise
    """
    if os.geteuid() == 0:
        print(f"{Colors.INFO}Running with root privileges{Colors.ENDC}")
        return True

    print(
        f"{Colors.WARNING}Running without root privileges. Some operations may be restricted.{Colors.ENDC}"
    )
    return (
        True  # Return True to continue without root for operations that don't need it
    )


def is_path_writable(path: str) -> bool:
    """
    Check if a path is writable.

    Args:
        path: Path to check

    Returns:
        True if writable, False otherwise
    """
    if os.path.exists(path):
        return os.access(path, os.W_OK)

    # Path doesn't exist, check if the parent directory is writable
    parent = os.path.dirname(path) or "."
    return os.access(parent, os.W_OK)


def validate_paths(paths: List[str], check_existence: bool = True) -> bool:
    """
    Validate that paths exist and are accessible.

    Args:
        paths: List of paths to validate
        check_existence: Whether to check if the paths exist

    Returns:
        True if all paths are valid, False otherwise
    """
    for path in paths:
        if check_existence and not os.path.exists(path):
            print(f"{Colors.ERROR}Path does not exist: {path}{Colors.ENDC}")
            return False

        # Check if the path is readable
        if os.path.exists(path) and not os.access(path, os.R_OK):
            print(f"{Colors.ERROR}No read permission for: {path}{Colors.ENDC}")
            return False

    return True


#####################################
# File Operation Functions
#####################################


def copy_item(src: str, dest: str, follow_symlinks: bool = True) -> bool:
    """
    Copy a file or directory with progress tracking.

    Args:
        src: Source file or directory path
        dest: Destination file or directory path
        follow_symlinks: Whether to follow symbolic links

    Returns:
        True if copy succeeded, False otherwise
    """
    print_section(f"Copying {os.path.basename(src)}")

    if not validate_paths([src], check_existence=True):
        return False

    if not is_path_writable(dest):
        print(f"{Colors.ERROR}No write permission for destination: {dest}{Colors.ENDC}")
        return False

    try:
        if os.path.isdir(src):
            # Count files and size for progress tracking
            file_count, total_size = get_file_count_and_size(src)

            if file_count == 0:
                print(f"{Colors.WARNING}No files to copy in {src}{Colors.ENDC}")
                return True

            # Create a progress bar
            progress = ProgressBar(total_size, desc=f"Copying {file_count} files")

            # Create a custom copy function to track progress
            def copy_with_progress(src_file, dst_file, buffer_size=DEFAULT_BUFFER_SIZE):
                with open(src_file, "rb") as fsrc, open(dst_file, "wb") as fdst:
                    while True:
                        buf = fsrc.read(buffer_size)
                        if not buf:
                            break
                        fdst.write(buf)
                        progress.update(len(buf))

            # Create a custom copy2 function that uses copy_with_progress
            def custom_copy2(src_file, dst_file):
                shutil.copystat(src_file, dst_file)
                copy_with_progress(src_file, dst_file)

            # Start copying files
            start_time = time.time()

            # Mirror the directory structure
            for root, dirs, files in os.walk(src):
                # Compute the new root directory
                rel_path = os.path.relpath(root, src)
                if rel_path == ".":
                    target_dir = dest
                else:
                    target_dir = os.path.join(dest, rel_path)

                # Create the target directory if it doesn't exist
                os.makedirs(target_dir, exist_ok=True)

                # Copy all the files in the current directory
                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    try:
                        if os.path.islink(src_file) and not follow_symlinks:
                            linkto = os.readlink(src_file)
                            os.symlink(linkto, dst_file)
                        else:
                            custom_copy2(src_file, dst_file)
                    except Exception as e:
                        print(
                            f"{Colors.ERROR}Error copying {src_file}: {e}{Colors.ENDC}"
                        )

            elapsed = time.time() - start_time
            print(
                f"{Colors.SUCCESS}Successfully copied {file_count} files ({format_size(total_size)}) in {format_time(elapsed)}{Colors.ENDC}"
            )

        else:
            # Single file copy
            file_size = os.path.getsize(src)
            progress = ProgressBar(file_size, desc=f"Copying {os.path.basename(src)}")

            # Custom copy function to track progress
            def copy_with_progress(fsrc, fdst, buffer_size=DEFAULT_BUFFER_SIZE):
                while True:
                    buf = fsrc.read(buffer_size)
                    if not buf:
                        break
                    fdst.write(buf)
                    progress.update(len(buf))

            # Start copying
            start_time = time.time()
            with open(src, "rb") as fsrc, open(dest, "wb") as fdst:
                copy_with_progress(fsrc, fdst)

            # Copy metadata
            shutil.copystat(src, dest)

            elapsed = time.time() - start_time
            print(
                f"{Colors.SUCCESS}Successfully copied {os.path.basename(src)} ({format_size(file_size)}) in {format_time(elapsed)}{Colors.ENDC}"
            )

        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error copying {src}: {e}{Colors.ENDC}")
        return False


def move_item(src: str, dest: str) -> bool:
    """
    Move a file or directory with progress tracking.

    Args:
        src: Source file or directory path
        dest: Destination file or directory path

    Returns:
        True if move succeeded, False otherwise
    """
    print_section(f"Moving {os.path.basename(src)}")

    if not validate_paths([src], check_existence=True):
        return False

    if not is_path_writable(dest):
        print(f"{Colors.ERROR}No write permission for destination: {dest}{Colors.ENDC}")
        return False

    # Check if source and destination are on the same filesystem
    src_device = os.stat(src).st_dev
    dest_device = os.stat(os.path.dirname(dest) or ".").st_dev

    # If they're on the same filesystem, we can do a fast rename
    if src_device == dest_device:
        try:
            print(f"{Colors.INFO}Fast move (rename) operation{Colors.ENDC}")
            start_time = time.time()
            os.rename(src, dest)
            elapsed = time.time() - start_time
            print(
                f"{Colors.SUCCESS}Successfully moved {src} to {dest} in {format_time(elapsed)}{Colors.ENDC}"
            )
            return True
        except Exception as e:
            print(f"{Colors.ERROR}Error moving {src}: {e}{Colors.ENDC}")
            return False

    # Different filesystems, need to copy and delete
    print(f"{Colors.INFO}Cross-filesystem move (copy and delete){Colors.ENDC}")

    # First copy the file/directory
    if not copy_item(src, dest):
        return False

    # Then delete the source
    try:
        print_section(f"Removing source {os.path.basename(src)}")

        spinner = ConsoleSpinner("Deleting source")
        spinner.start()

        if os.path.isdir(src):
            shutil.rmtree(src)
        else:
            os.remove(src)

        spinner.stop(f"{Colors.SUCCESS}Successfully removed source {src}{Colors.ENDC}")
        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error removing source {src}: {e}{Colors.ENDC}")
        print(
            f"{Colors.WARNING}Files were copied to {dest} but source couldn't be removed{Colors.ENDC}"
        )
        return False


def delete_item(path: str, force: bool = False) -> bool:
    """
    Delete a file or directory with confirmation.

    Args:
        path: Path of file or directory to delete
        force: Whether to force deletion without confirmation

    Returns:
        True if deletion succeeded, False otherwise
    """
    print_section(f"Deleting {os.path.basename(path)}")

    if not validate_paths([path], check_existence=True):
        return False

    if not is_path_writable(path):
        print(f"{Colors.ERROR}No write permission for: {path}{Colors.ENDC}")
        return False

    # Get file count and size for directories
    if os.path.isdir(path):
        file_count, total_size = get_file_count_and_size(path)
        print(
            f"Will delete directory containing {file_count} files ({format_size(total_size)})"
        )
    else:
        print(f"Will delete file: {path} ({format_size(os.path.getsize(path))})")

    # Confirm deletion
    if not force:
        confirmation = input(
            f"{Colors.WARNING}Are you sure you want to delete? [y/N]: {Colors.ENDC}"
        )
        if confirmation.lower() != "y":
            print(f"{Colors.INFO}Deletion cancelled{Colors.ENDC}")
            return False

    try:
        start_time = time.time()

        if os.path.isdir(path):
            spinner = ConsoleSpinner(f"Deleting directory")
            spinner.start()
            shutil.rmtree(path)
            elapsed = time.time() - start_time
            spinner.stop(
                f"{Colors.SUCCESS}Successfully deleted directory {path} in {format_time(elapsed)}{Colors.ENDC}"
            )
        else:
            os.remove(path)
            elapsed = time.time() - start_time
            print(
                f"{Colors.SUCCESS}Successfully deleted {path} in {format_time(elapsed)}{Colors.ENDC}"
            )

        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error deleting {path}: {e}{Colors.ENDC}")
        return False


def find_files(directory: str, pattern: str, show_details: bool = False) -> List[str]:
    """
    Find files matching a pattern in a directory with metadata display.

    Args:
        directory: Directory to search in
        pattern: File name pattern to search for
        show_details: Whether to show detailed file information

    Returns:
        List of matched file paths
    """
    print_section(f"Searching for files matching '{pattern}' in {directory}")

    if not validate_paths([directory], check_existence=True):
        return []

    matches = []
    pattern = pattern.lower()
    use_glob = "*" in pattern or "?" in pattern

    spinner = ConsoleSpinner("Searching")
    spinner.start()

    try:
        for root, _, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)

                # Pattern matching
                match = False
                if pattern == "*":
                    match = True
                elif use_glob:
                    # Simple glob-like matching (not full regex)
                    match_pattern = pattern.replace("*", ".*").replace("?", ".")
                    import re

                    match = bool(re.search(match_pattern, filename.lower()))
                else:
                    match = pattern.lower() in filename.lower()

                if match:
                    matches.append(filepath)

        spinner.stop(
            f"{Colors.SUCCESS}Found {len(matches)} matching files{Colors.ENDC}"
        )

        # Display results
        if matches:
            if show_details:
                print(
                    f"\n{Colors.BOLD}{'File Path':<50} {'Size':<10} {'Type':<10} {'Modified':<20}{Colors.ENDC}"
                )
                print("=" * 90)

                for match in matches:
                    try:
                        stat_info = os.stat(match)
                        size = format_size(stat_info.st_size)
                        modified = format_date(stat_info.st_mtime)
                        file_type = get_file_category(match)
                        rel_path = os.path.relpath(match, directory)

                        # Add color based on file type
                        if file_type == "document":
                            type_color = Colors.FROST_3
                        elif file_type == "image":
                            type_color = Colors.AURORA_GREEN
                        elif file_type == "video":
                            type_color = Colors.AURORA_PURPLE
                        elif file_type == "audio":
                            type_color = Colors.AURORA_YELLOW
                        elif file_type == "archive":
                            type_color = Colors.AURORA_ORANGE
                        elif file_type == "code":
                            type_color = Colors.FROST_2
                        else:
                            type_color = Colors.DETAIL

                        print(
                            f"{rel_path:<50} {size:<10} {type_color}{file_type:<10}{Colors.ENDC} {modified:<20}"
                        )
                    except Exception as e:
                        print(f"{Colors.ERROR}Error reading {match}: {e}{Colors.ENDC}")
            else:
                for match in matches:
                    print(match)
        else:
            print("No files found matching the pattern.")

        return matches

    except Exception as e:
        spinner.stop(f"{Colors.ERROR}Error searching for files: {e}{Colors.ENDC}")
        return []


def compress_files(src: str, dest: str) -> bool:
    """
    Compress files or directories using tar with progress tracking.

    Args:
        src: Source file or directory to compress
        dest: Destination tar file path

    Returns:
        True if compression succeeded, False otherwise
    """
    print_section(f"Compressing {os.path.basename(src)}")

    if not validate_paths([src], check_existence=True):
        return False

    if not is_path_writable(os.path.dirname(dest) or "."):
        print(f"{Colors.ERROR}No write permission for destination: {dest}{Colors.ENDC}")
        return False

    # Add .tar.gz extension if not specified
    if not dest.endswith((".tar.gz", ".tgz")):
        dest = f"{dest}.tar.gz"

    # Get file count and size for progress tracking
    file_count, total_size = get_file_count_and_size(src)

    if file_count == 0:
        print(f"{Colors.WARNING}No files to compress in {src}{Colors.ENDC}")
        return True

    # Create a progress bar
    progress = ProgressBar(total_size, desc=f"Compressing {file_count} files")

    try:
        # Custom filter to track progress
        class ProgressFileObj:
            def __init__(self, fileobj):
                self.fileobj = fileobj
                self.processed = 0

            def write(self, data):
                self.processed += len(data)
                progress.set_current(self.processed)
                return self.fileobj.write(data)

            def close(self):
                return self.fileobj.close()

            def flush(self):
                return self.fileobj.flush()

        # Start compressing
        start_time = time.time()

        with open(dest, "wb") as f_out:
            wrapped_file = ProgressFileObj(f_out)

            with tarfile.open(
                fileobj=wrapped_file, mode=f"w:gz", compresslevel=COMPRESSION_LEVEL
            ) as tar:
                if os.path.isdir(src):
                    # Add directory contents
                    base_dir = os.path.basename(src)
                    for root, dirs, files in os.walk(src):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.join(
                                base_dir, os.path.relpath(file_path, src)
                            )
                            tar.add(file_path, arcname=arcname)
                else:
                    # Add single file
                    tar.add(src, arcname=os.path.basename(src))

        elapsed = time.time() - start_time
        output_size = os.path.getsize(dest)
        compression_ratio = (
            (total_size - output_size) / total_size * 100 if total_size > 0 else 0
        )

        print(f"{Colors.SUCCESS}Successfully compressed to {dest}{Colors.ENDC}")
        print(f"Original size: {format_size(total_size)}")
        print(f"Compressed size: {format_size(output_size)}")
        print(f"Compression ratio: {compression_ratio:.1f}% space saved")
        print(f"Time taken: {format_time(elapsed)}")

        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error compressing {src}: {e}{Colors.ENDC}")
        # Clean up incomplete file
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except:
                pass
        return False


def calculate_checksum(path: str, algorithm: str = "md5") -> bool:
    """
    Calculate file checksum with progress tracking.

    Args:
        path: Path to the file
        algorithm: Hash algorithm to use (md5, sha1, sha256, sha512)

    Returns:
        True if checksum calculation succeeded, False otherwise
    """
    print_section(
        f"Calculating {algorithm.upper()} checksum for {os.path.basename(path)}"
    )

    if not validate_paths([path], check_existence=True):
        return False

    if os.path.isdir(path):
        print(
            f"{Colors.ERROR}Cannot calculate checksum for a directory. Please specify a file.{Colors.ENDC}"
        )
        return False

    try:
        file_size = os.path.getsize(path)
        hash_func = hashlib.new(algorithm)
        progress = ProgressBar(file_size, desc=f"Reading file")

        start_time = time.time()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                hash_func.update(chunk)
                progress.update(len(chunk))

        checksum = hash_func.hexdigest()
        elapsed = time.time() - start_time

        print(
            f"{Colors.SUCCESS}{algorithm.upper()} Checksum: {Colors.EMPHASIS}{checksum}{Colors.ENDC}"
        )
        print(f"Time taken: {format_time(elapsed)}")

        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error calculating checksum: {e}{Colors.ENDC}")
        return False


def disk_usage(directory: str, threshold: int = LARGE_FILE_THRESHOLD) -> bool:
    """
    Analyze disk usage in a directory with visualization.

    Args:
        directory: Directory to analyze
        threshold: Size threshold for large files in bytes

    Returns:
        True if analysis succeeded, False otherwise
    """
    print_section(f"Analyzing disk usage in {directory}")

    if not validate_paths([directory], check_existence=True):
        return False

    def sizeof_fmt(num):
        """Convert bytes to human-readable format."""
        return format_size(num)

    total_size = 0
    file_count = 0
    dir_count = 0
    recently_accessed = []
    rarely_accessed = []
    large_files = []
    now = datetime.datetime.now()
    file_type_totals = {}

    try:
        spinner = ConsoleSpinner("Analyzing disk usage")
        spinner.start()

        for root, dirs, files in os.walk(directory):
            dir_count += len(dirs)

            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_stat = os.stat(file_path)
                    file_count += 1
                    size = file_stat.st_size
                    total_size += size

                    # Categorize file by type
                    file_type = get_file_category(file)
                    if file_type not in file_type_totals:
                        file_type_totals[file_type] = 0
                    file_type_totals[file_type] += size

                    # Check last access time
                    last_access = datetime.datetime.fromtimestamp(file_stat.st_atime)
                    days_since_access = (now - last_access).days

                    if days_since_access <= RECENT_ACCESS_THRESHOLD:
                        recently_accessed.append((file_path, days_since_access, size))
                    else:
                        rarely_accessed.append((file_path, days_since_access, size))

                    # Check for large files
                    if size >= threshold:
                        large_files.append((file_path, size))

                except Exception as e:
                    print(
                        f"{Colors.ERROR}Could not process {file_path}: {e}{Colors.ENDC}"
                    )

        spinner.stop()

        # Print summary
        print(
            f"\n{Colors.HEADER}{Colors.BOLD}Disk Usage Summary for {directory}{Colors.ENDC}"
        )
        print(
            f"{Colors.INFO}Total Size: {Colors.EMPHASIS}{sizeof_fmt(total_size)}{Colors.ENDC}"
        )
        print(
            f"{Colors.INFO}Total Directories: {Colors.DETAIL}{dir_count}{Colors.ENDC}"
        )
        print(f"{Colors.INFO}Total Files: {Colors.DETAIL}{file_count}{Colors.ENDC}")

        # File type breakdown
        if file_type_totals:
            print(f"\n{Colors.FROST_3}{Colors.BOLD}File Type Breakdown:{Colors.ENDC}")

            # Sort file types by size (largest first)
            sorted_types = sorted(
                file_type_totals.items(), key=lambda x: x[1], reverse=True
            )

            # Calculate percentages and create bar chart
            for file_type, size in sorted_types:
                percentage = (size / total_size) * 100 if total_size > 0 else 0
                bar_length = int((size / total_size) * 40) if total_size > 0 else 0

                # Color code by file type
                if file_type == "document":
                    type_color = Colors.FROST_3
                elif file_type == "image":
                    type_color = Colors.AURORA_GREEN
                elif file_type == "video":
                    type_color = Colors.AURORA_PURPLE
                elif file_type == "audio":
                    type_color = Colors.AURORA_YELLOW
                elif file_type == "archive":
                    type_color = Colors.AURORA_ORANGE
                elif file_type == "code":
                    type_color = Colors.FROST_2
                else:
                    type_color = Colors.DETAIL

                bar = "█" * bar_length
                print(
                    f"{type_color}{file_type:<10}{Colors.ENDC} {sizeof_fmt(size):<10} "
                    f"{percentage:>5.1f}% {Colors.FROST_2}{bar}{Colors.ENDC}"
                )

        # Large files
        if large_files:
            print(f"\n{Colors.AURORA_ORANGE}{Colors.BOLD}Largest Files:{Colors.ENDC}")

            # Sort by size, largest first, and take top 10
            for file_path, size in sorted(
                large_files, key=lambda x: x[1], reverse=True
            )[:10]:
                rel_path = os.path.relpath(file_path, directory)
                print(f"{Colors.DETAIL}{rel_path}:{Colors.ENDC} {sizeof_fmt(size)}")

        # Recently accessed files
        if recently_accessed:
            print(
                f"\n{Colors.AURORA_GREEN}{Colors.BOLD}Recently Accessed Files (last {RECENT_ACCESS_THRESHOLD} days):{Colors.ENDC}"
            )

            # Sort by access time, most recent first, and take top 5
            for file_path, days, size in sorted(recently_accessed, key=lambda x: x[1])[
                :5
            ]:
                rel_path = os.path.relpath(file_path, directory)
                print(
                    f"{Colors.DETAIL}{rel_path}{Colors.ENDC} ({sizeof_fmt(size)}) "
                    f"- Last accessed {days} days ago"
                )

        # Rarely accessed files
        if rarely_accessed:
            print(
                f"\n{Colors.AURORA_RED}{Colors.BOLD}Rarely Accessed Files (over {RECENT_ACCESS_THRESHOLD} days):{Colors.ENDC}"
            )

            # Calculate total size of rarely accessed files
            rarely_accessed_size = sum(size for _, _, size in rarely_accessed)
            saved_percentage = (
                (rarely_accessed_size / total_size) * 100 if total_size > 0 else 0
            )

            print(
                f"Found {len(rarely_accessed)} rarely accessed files "
                f"({sizeof_fmt(rarely_accessed_size)}, {saved_percentage:.1f}% of total)"
            )

            # Sort by last access time, oldest first, and take top 5
            for file_path, days, size in sorted(
                rarely_accessed, key=lambda x: x[1], reverse=True
            )[:5]:
                rel_path = os.path.relpath(file_path, directory)
                print(
                    f"{Colors.DETAIL}{rel_path}{Colors.ENDC} ({sizeof_fmt(size)}) "
                    f"- Last accessed {days} days ago"
                )

        return True

    except Exception as e:
        print(f"{Colors.ERROR}Error analyzing disk usage: {e}{Colors.ENDC}")
        return False


#####################################
# Main Function
#####################################


def main() -> None:
    """Main entry point for the file toolkit."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description="Enhanced File Operations Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Copy a file:
    python toolkit.py copy source.txt destination.txt
  
  Move a directory:
    python toolkit.py move /source/dir /destination/dir
  
  Delete files:
    python toolkit.py delete file1.txt file2.txt
  
  Find files:
    python toolkit.py find /home/user -p "*.jpg" --details
  
  Compress files:
    python toolkit.py compress /source/dir archive.tar.gz
  
  Calculate checksum:
    python toolkit.py checksum file.iso -a sha256
  
  Analyze disk usage:
    python toolkit.py du /home/user
""",
    )

    parser.add_argument(
        "operation",
        choices=["copy", "move", "delete", "find", "compress", "checksum", "du"],
        help="Operation to perform",
    )

    parser.add_argument("paths", nargs="+", help="Paths for the operation")

    # Optional arguments
    parser.add_argument(
        "-p", "--pattern", default="*", help="Pattern for find operation (default: *)"
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        default="md5",
        choices=CHECKSUM_ALGORITHMS,
        help="Checksum algorithm (default: md5)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force operation without confirmation",
    )
    parser.add_argument(
        "-d", "--details", action="store_true", help="Show detailed information"
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=LARGE_FILE_THRESHOLD,
        help=f"Size threshold for large files in MB (default: {LARGE_FILE_THRESHOLD // 1024 // 1024})",
    )

    args = parser.parse_args()

    # Print header
    print_header("Enhanced File Operations Toolkit")

    # Check privileges
    check_root_privileges()

    try:
        # Set threshold in bytes
        threshold = args.threshold * 1024 * 1024

        # Execute the requested operation
        if args.operation == "copy":
            if len(args.paths) < 2:
                raise ValueError("Copy requires source and destination paths")

            # Handle multiple sources with destination directory
            if len(args.paths) > 2:
                dest_dir = args.paths[-1]
                if not os.path.isdir(dest_dir):
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)
                    else:
                        raise ValueError(
                            f"When copying multiple sources, destination must be a directory: {dest_dir}"
                        )

                success = True
                for src in args.paths[:-1]:
                    dest_path = os.path.join(dest_dir, os.path.basename(src))
                    if not copy_item(src, dest_path):
                        success = False

                if not success:
                    sys.exit(1)
            else:
                if not copy_item(args.paths[0], args.paths[1]):
                    sys.exit(1)

        elif args.operation == "move":
            if len(args.paths) < 2:
                raise ValueError("Move requires source and destination paths")

            # Handle multiple sources with destination directory
            if len(args.paths) > 2:
                dest_dir = args.paths[-1]
                if not os.path.isdir(dest_dir):
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)
                    else:
                        raise ValueError(
                            f"When moving multiple sources, destination must be a directory: {dest_dir}"
                        )

                success = True
                for src in args.paths[:-1]:
                    dest_path = os.path.join(dest_dir, os.path.basename(src))
                    if not move_item(src, dest_path):
                        success = False

                if not success:
                    sys.exit(1)
            else:
                if not move_item(args.paths[0], args.paths[1]):
                    sys.exit(1)

        elif args.operation == "delete":
            success = True
            for path in args.paths:
                if not delete_item(path, args.force):
                    success = False

            if not success:
                sys.exit(1)

        elif args.operation == "find":
            if len(args.paths) != 1:
                raise ValueError("Find requires exactly one directory path")

            find_files(args.paths[0], args.pattern, args.details)

        elif args.operation == "compress":
            if len(args.paths) < 2:
                raise ValueError("Compress requires source and destination paths")

            if not compress_files(args.paths[0], args.paths[1]):
                sys.exit(1)

        elif args.operation == "checksum":
            success = True
            for path in args.paths:
                if not calculate_checksum(path, args.algorithm):
                    success = False

            if not success:
                sys.exit(1)

        elif args.operation == "du":
            success = True
            for path in args.paths:
                if not disk_usage(path, threshold):
                    success = False

            if not success:
                sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Operation interrupted by user{Colors.ENDC}")
        sys.exit(130)

    except ValueError as e:
        print(f"{Colors.ERROR}Error: {e}{Colors.ENDC}")
        parser.print_help()
        sys.exit(1)

    except Exception as e:
        print(f"{Colors.ERROR}Unexpected error: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
