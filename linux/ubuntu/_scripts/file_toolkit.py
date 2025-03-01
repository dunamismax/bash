#!/usr/bin/env python3
"""
Enhanced File Operations Toolkit

This utility provides a comprehensive command‑line tool for file management and system operations.
It supports the following operations:

  • copy     - Copy files or directories with progress tracking
  • move     - Move files or directories with progress tracking
  • delete   - Delete files or directories with confirmation
  • find     - Search for files with pattern matching and metadata display
  • compress - Compress files or directories with compression ratio feedback
  • checksum - Calculate file checksums with multiple algorithm support
  • du       - Disk usage analysis with visualization and insights

Note: Some operations may require root privileges.
"""

import atexit
import datetime
import hashlib
import os
import re
import shutil
import signal
import stat
import sys
import tarfile
import time
from pathlib import Path
from typing import List, Tuple

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file read/write
DEFAULT_BUFFER_SIZE = 8192  # Buffer size for copying
COMPRESSION_LEVEL = 9  # tar.gz compression level
RECENT_ACCESS_THRESHOLD = 30  # days
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"}
CODE_EXTENSIONS = {".py", ".js", ".java", ".c", ".cpp", ".h", ".php", ".html", ".css"}
CHECKSUM_ALGORITHMS = ["md5", "sha1", "sha256", "sha512"]

# ------------------------------
# Nord-Themed Styles & Console Setup
# ------------------------------
# Nord color palette:
#   nord0:  #2E3440, nord1:  #3B4252, nord4:  #D8DEE9, nord7:  #8FBCBB,
#   nord8:  #88C0D0, nord11: #BF616A, and others.
console = Console()


def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #5E81AC]⚠ {text}[/bold #5E81AC]")


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")


def cleanup() -> None:
    """Perform any necessary cleanup tasks."""
    print_step("Cleaning up resources...")


def signal_handler(sig, frame) -> None:
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Received {sig_name}. Exiting gracefully...")
    cleanup()
    sys.exit(128 + sig)


atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ------------------------------
# Helper Functions
# ------------------------------
def format_size(num_bytes: float) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"


def format_time(seconds: float) -> str:
    """Format seconds to a human-readable time string."""
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
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def check_root_privileges() -> None:
    """Warn if not run as root (but continue)."""
    if os.geteuid() != 0:
        print_warning(
            "Running without root privileges. Some operations may be restricted."
        )


# ------------------------------
# File Operation Functions
# ------------------------------
def copy_item(src: str, dest: str) -> bool:
    """Copy a file or directory with progress tracking."""
    print_section(f"Copying {Path(src).name}")

    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False

    try:
        if Path(src).is_dir():
            # Calculate total size for progress tracking.
            total_size = sum(
                f.stat().st_size for f in Path(src).rglob("*") if f.is_file()
            )
            if total_size == 0:
                print_warning("No files to copy.")
                return True

            start_time = time.time()
            with Progress(
                SpinnerColumn(style="bold #81A1C1"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="bold #88C0D0"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Copying files", total=total_size)
                # Walk directory and copy files.
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
            # Single file copy with progress.
            file_size = Path(src).stat().st_size
            start_time = time.time()
            with Progress(
                SpinnerColumn(style="bold #81A1C1"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="bold #88C0D0"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
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
    """Move a file or directory with progress tracking."""
    print_section(f"Moving {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False
    try:
        # If on the same filesystem, rename; otherwise, copy then delete.
        if os.stat(src).st_dev == os.stat(os.path.dirname(dest) or ".").st_dev:
            start_time = time.time()
            os.rename(src, dest)
            elapsed = time.time() - start_time
            print_success(f"Moved {src} to {dest} in {format_time(elapsed)}")
        else:
            print_step("Cross-filesystem move: performing copy then delete")
            if not copy_item(src, dest):
                return False
            if Path(src).is_dir():
                shutil.rmtree(src)
            else:
                os.remove(src)
            print_success(f"Moved {src} to {dest} by copying and deleting source")
        return True
    except Exception as e:
        print_error(f"Error moving {src}: {e}")
        return False


def delete_item(path: str, force: bool = False) -> bool:
    """Delete a file or directory with confirmation."""
    print_section(f"Deleting {Path(path).name}")
    if not Path(path).exists():
        print_error(f"Path not found: {path}")
        return False
    if not force:
        confirmation = input("Are you sure you want to delete? [y/N]: ")
        if confirmation.lower() != "y":
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


def find_files(directory: str, pattern: str, details: bool) -> List[str]:
    """Search for files matching a pattern with optional detailed metadata."""
    print_section(f"Searching for files in {directory}")
    if not Path(directory).exists():
        print_error(f"Directory not found: {directory}")
        return []
    matches = []
    regex = re.compile(pattern.replace("*", ".*").replace("?", "."))
    for root, _, files in os.walk(directory):
        for file in files:
            if regex.search(file.lower()):
                matches.append(str(Path(root) / file))
    print_success(f"Found {len(matches)} matching files")
    if details and matches:
        console.print(
            f"[bold #88C0D0]{'File Path':<50} {'Size':<10} {'Modified':<20}[/bold #88C0D0]"
        )
        console.print("-" * 90)
        for match in matches:
            try:
                p = Path(match)
                size = format_size(p.stat().st_size)
                modified = format_date(p.stat().st_mtime)
                console.print(f"{str(p):<50} {size:<10} {modified:<20}")
            except Exception as e:
                print_error(f"Error reading {match}: {e}")
    elif not details:
        for match in matches:
            console.print(match)
    return matches


def compress_files(src: str, dest: str) -> bool:
    """Compress a file or directory into a tar.gz archive with progress tracking."""
    print_section(f"Compressing {Path(src).name}")
    if not Path(src).exists():
        print_error(f"Source not found: {src}")
        return False
    if not dest.endswith((".tar.gz", ".tgz")):
        dest = f"{dest}.tar.gz"
    total_size = 0
    if Path(src).is_dir():
        total_size = sum(f.stat().st_size for f in Path(src).rglob("*") if f.is_file())
    else:
        total_size = Path(src).stat().st_size
    if total_size == 0:
        print_warning("No files to compress.")
        return True
    start_time = time.time()
    try:
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Compressing files", total=total_size)
            with open(dest, "wb") as f_out:
                with tarfile.open(
                    fileobj=f_out, mode="w:gz", compresslevel=COMPRESSION_LEVEL
                ) as tar:
                    # Define a filter to update progress as files are added.
                    def filter_func(tarinfo):
                        if tarinfo.size:
                            progress.update(task, advance=tarinfo.size)
                        return tarinfo

                    tar.add(src, arcname=Path(src).name, filter=filter_func)
        elapsed = time.time() - start_time
        out_size = Path(dest).stat().st_size
        ratio = (total_size - out_size) / total_size * 100 if total_size > 0 else 0
        print_success(f"Compressed to {dest} in {format_time(elapsed)}")
        console.print(f"Original size: {format_size(total_size)}")
        console.print(f"Compressed size: {format_size(out_size)}")
        console.print(f"Compression ratio: {ratio:.1f}% space saved")
        return True
    except Exception as e:
        print_error(f"Error compressing {src}: {e}")
        if Path(dest).exists():
            try:
                Path(dest).unlink()
            except Exception:
                pass
        return False


def calculate_checksum(path: str, algorithm: str) -> bool:
    """Calculate and display the checksum of a file using the specified algorithm."""
    print_section(f"Calculating {algorithm.upper()} checksum for {Path(path).name}")
    if not Path(path).exists() or Path(path).is_dir():
        print_error("Please specify an existing file for checksum calculation.")
        return False
    try:
        file_size = Path(path).stat().st_size
        hash_func = hashlib.new(algorithm)
        start_time = time.time()
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
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
        print_success(
            f"{algorithm.upper()} Checksum: [bold #8FBCBB]{checksum}[/bold #8FBCBB]"
        )
        console.print(f"Time taken: {format_time(elapsed)}")
        return True
    except Exception as e:
        print_error(f"Error calculating checksum: {e}")
        return False


def disk_usage(directory: str, threshold: int) -> bool:
    """Analyze disk usage in a directory and display summary information."""
    print_section(f"Analyzing disk usage in {directory}")
    if not Path(directory).exists():
        print_error(f"Directory not found: {directory}")
        return False
    total_size = 0
    file_count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            try:
                fp = Path(root) / file
                total_size += fp.stat().st_size
                file_count += 1
            except Exception:
                continue
    print_success(f"Total files: {file_count}")
    console.print(f"Total size: [bold #8FBCBB]{format_size(total_size)}[/bold #8FBCBB]")
    if total_size >= threshold:
        console.print(
            f"[bold #BF616A]Warning:[/bold #BF616A] Directory size exceeds threshold."
        )
    return True


# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.argument(
    "operation",
    type=click.Choice(
        ["copy", "move", "delete", "find", "compress", "checksum", "du"],
        case_sensitive=False,
    ),
)
@click.argument("paths", nargs=-1)
@click.option(
    "-p",
    "--pattern",
    default=".*",
    help="Pattern for find operation (regex style, default: .*)",
)
@click.option(
    "-a",
    "--algorithm",
    default="md5",
    type=click.Choice(CHECKSUM_ALGORITHMS),
    help="Checksum algorithm (default: md5)",
)
@click.option(
    "-f", "--force", is_flag=True, help="Force operation without confirmation"
)
@click.option(
    "-d", "--details", is_flag=True, help="Show detailed information (for find)"
)
@click.option(
    "-t",
    "--threshold",
    default=LARGE_FILE_THRESHOLD // (1024 * 1024),
    help="Threshold for disk usage analysis in MB (default: 100)",
)
def main(
    operation: str,
    paths: List[str],
    pattern: str,
    algorithm: str,
    force: bool,
    details: bool,
    threshold: int,
) -> None:
    """Enhanced File Operations Toolkit"""
    print_header("File Toolkit")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )
    check_root_privileges()

    try:
        # Convert threshold to bytes
        threshold_bytes = threshold * 1024 * 1024

        if operation.lower() == "copy":
            if len(paths) < 2:
                raise ValueError("Copy requires source and destination paths")
            # If multiple sources, last argument must be a directory.
            if len(paths) > 2:
                dest_dir = paths[-1]
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                success = True
                for src in paths[:-1]:
                    dest_path = str(Path(dest_dir) / Path(src).name)
                    if not copy_item(src, dest_path):
                        success = False
                if not success:
                    sys.exit(1)
            else:
                if not copy_item(paths[0], paths[1]):
                    sys.exit(1)

        elif operation.lower() == "move":
            if len(paths) < 2:
                raise ValueError("Move requires source and destination paths")
            if len(paths) > 2:
                dest_dir = paths[-1]
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                success = True
                for src in paths[:-1]:
                    dest_path = str(Path(dest_dir) / Path(src).name)
                    if not move_item(src, dest_path):
                        success = False
                if not success:
                    sys.exit(1)
            else:
                if not move_item(paths[0], paths[1]):
                    sys.exit(1)

        elif operation.lower() == "delete":
            success = True
            for path in paths:
                if not delete_item(path, force):
                    success = False
            if not success:
                sys.exit(1)

        elif operation.lower() == "find":
            if len(paths) != 1:
                raise ValueError("Find operation requires exactly one directory path")
            find_files(paths[0], pattern, details)

        elif operation.lower() == "compress":
            if len(paths) < 2:
                raise ValueError("Compress requires source and destination paths")
            if not compress_files(paths[0], paths[1]):
                sys.exit(1)

        elif operation.lower() == "checksum":
            success = True
            for path in paths:
                if not calculate_checksum(path, algorithm):
                    success = False
            if not success:
                sys.exit(1)

        elif operation.lower() == "du":
            success = True
            for path in paths:
                if not disk_usage(path, threshold_bytes):
                    success = False
            if not success:
                sys.exit(1)

        print_header("Operation Complete")
        print_success("File operations completed successfully!")
    except ValueError as ve:
        print_error(f"Error: {ve}")
        sys.exit(1)
    except KeyboardInterrupt:
        print_warning("Operation interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
