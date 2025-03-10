#!/usr/bin/env python3
"""
Fedora Script Deployer
—————————————————
An automated file deployment utility that copies scripts from a source
directory to a destination directory and manages permissions appropriately.

Features:
  • Fully automated deployment without user prompts
  • Fast file copying with MD5 hash comparison to avoid unnecessary updates
  • Rich terminal output with detailed progress information
  • Proper permission management for Fedora environment
  • Comprehensive deployment statistics and reporting

This script is designed specifically for Fedora Linux.
Version: 1.0.0
"""

# -—————————————————————
# Dependency Check and Imports
# -—————————————————————
import atexit
import asyncio
import hashlib
import os
import pwd
import sys
import shutil
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, TypeVar, cast, Callable


def install_dependencies():
    """Install required dependencies using DNF and pip for Fedora."""
    required_packages = ["paramiko", "rich", "pyfiglet", "prompt_toolkit"]
    user = os.environ.get("SUDO_USER", os.environ.get("USER"))

    print("Checking and installing required dependencies...")

    # Try to install system dependencies with DNF if running as root
    if os.geteuid() == 0:
        try:
            print("Installing python3-pip via DNF...")
            subprocess.check_call(["dnf", "install", "-y", "python3-pip"])
        except subprocess.CalledProcessError:
            print(
                "Failed to install python3-pip with DNF. Continuing with existing pip..."
            )

    # Install Python dependencies with pip
    try:
        if os.geteuid() == 0 and user:
            # Install for the actual user when run with sudo
            subprocess.check_call(
                ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
                + required_packages
            )
        else:
            # Regular user install
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + required_packages
            )
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install Python dependencies: {e}")
        print("Please install the required packages manually:")
        print("pip install paramiko rich pyfiglet prompt_toolkit")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        DownloadColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    install_dependencies()
    print("Restarting script with dependencies installed...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Enable rich traceback for better debugging
install_rich_traceback(show_locals=True)


# -—————————————————————
# Configuration & Constants
# -—————————————————————
@dataclass
class AppConfig:
    """Application configuration settings."""

    # App information
    VERSION: str = "1.0.0"
    APP_NAME: str = "Fedora Script Deployer"
    APP_SUBTITLE: str = "File Deployment Utility for Fedora"

    # Directory paths
    SOURCE_DIR: str = "/home/sawyer/github/bash/linux/fedora/_scripts"
    DEST_DIR: str = "/home/sawyer/bin"
    OWNER_USER: str = "sawyer"

    # Permission settings
    OWNER_UID: Optional[int] = None
    OWNER_GID: Optional[int] = None
    FILE_PERMISSIONS: int = 0o644  # Read/write for owner, read for group/others
    DIR_PERMISSIONS: int = 0o755  # RWX for owner, RX for group/others

    # Performance settings
    MAX_WORKERS: int = 4
    DEFAULT_TIMEOUT: int = 30

    # UI settings
    TERM_WIDTH: int = 80
    PROGRESS_WIDTH: int = 50

    def __post_init__(self) -> None:
        """Initialize derived settings after dataclass instantiation."""
        # Get terminal width
        try:
            self.TERM_WIDTH = shutil.get_terminal_size().columns
        except Exception:
            pass  # Keep default value

        self.PROGRESS_WIDTH = min(50, self.TERM_WIDTH - 30)

        # Resolve user ID and group ID
        try:
            pwd_entry = pwd.getpwnam(self.OWNER_USER)
            self.OWNER_UID = pwd_entry.pw_uid
            self.OWNER_GID = pwd_entry.pw_gid
        except KeyError:
            pass  # Keep as None if user not found


# -—————————————————————
# Nord-Themed Colors
# -—————————————————————
class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Return a list of frost colors for gradients."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# -—————————————————————
# Custom Exception Classes
# -—————————————————————
class DeploymentError(Exception):
    """Base exception for all deployment-related errors."""

    pass


class PathVerificationError(DeploymentError):
    """Exception raised for errors related to path verification."""

    pass


class PermissionOperationError(DeploymentError):
    """Exception raised for errors related to permission operations."""

    pass


class FileOperationError(DeploymentError):
    """Exception raised for errors related to file operations."""

    pass


# -—————————————————————
# Data Structures
# -—————————————————————
class FileStatus(str, Enum):
    """Enum representing the possible status of a file during deployment."""

    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass
class FileInfo:
    """Information about a deployed file."""

    filename: str
    status: FileStatus
    permission_changed: bool = False
    source_path: str = ""
    dest_path: str = ""
    error_message: str = ""


@dataclass
class DeploymentResult:
    """Results of a deployment operation."""

    new_files: int = 0
    updated_files: int = 0
    unchanged_files: int = 0
    failed_files: int = 0
    permission_changes: int = 0
    files: List[FileInfo] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def total_files(self) -> int:
        """Return the total number of files processed."""
        return (
            self.new_files
            + self.updated_files
            + self.unchanged_files
            + self.failed_files
        )

    @property
    def elapsed_time(self) -> float:
        """Return the elapsed time of the deployment."""
        return (self.end_time or time.time()) - self.start_time

    def complete(self) -> None:
        """Mark the deployment as complete."""
        self.end_time = time.time()

    def add_file(self, file_info: FileInfo) -> None:
        """Add a file to the deployment result."""
        self.files.append(file_info)

        if file_info.status == FileStatus.NEW:
            self.new_files += 1
        elif file_info.status == FileStatus.UPDATED:
            self.updated_files += 1
        elif file_info.status == FileStatus.UNCHANGED:
            self.unchanged_files += 1
        elif file_info.status == FileStatus.FAILED:
            self.failed_files += 1

        if file_info.permission_changed:
            self.permission_changes += 1


# Create console with custom theme
console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
            "filename": f"italic {NordColors.FROST_1}",
        }
    )
)


# -—————————————————————
# UI Helper Functions
# -—————————————————————
def create_header() -> Panel:
    """Create a stylish header panel with the app name."""
    config = AppConfig()
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""

    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(config.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border

    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{config.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{config.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message with a checkmark prefix."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message with a warning prefix."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message with an X prefix."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step message with an arrow prefix."""
    print_message(message, NordColors.FROST_2, "→")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a styled panel with a message."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def create_section_header(title: str) -> Panel:
    """Create a section header panel."""
    return Panel(
        Text(title, style=f"bold {NordColors.FROST_1}"),
        border_style=Style(color=NordColors.FROST_3),
        padding=(0, 2),
    )


# -—————————————————————
# Signal Handling and Cleanup
# -—————————————————————
def cleanup() -> None:
    """Clean up resources before exit."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle signals for graceful shutdown."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# -—————————————————————
# Core Functionality
# -—————————————————————
async def get_file_hash(file_path: str) -> str:
    """
    Calculate the MD5 hash of a file asynchronously.

    Args:
        file_path: Path to the file

    Returns:
        MD5 hash of the file
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _calculate_hash, file_path)
    except Exception as e:
        raise FileOperationError(f"Failed to calculate hash for {file_path}: {e}")


def _calculate_hash(file_path: str) -> str:
    """Synchronous helper for file hash calculation."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


async def list_all_files(directory: str) -> List[str]:
    """
    List all files in a directory and its subdirectories asynchronously.

    Args:
        directory: Path to the directory

    Returns:
        List of relative file paths
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _walk_directory, directory)
    except Exception as e:
        raise FileOperationError(f"Failed to list files in {directory}: {e}")


def _walk_directory(directory: str) -> List[str]:
    """Synchronous helper for directory walking."""
    file_paths = []
    for root, _, files in os.walk(directory):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, directory)
            file_paths.append(rel_path)
    return sorted(file_paths)  # Sort for consistent processing order


async def set_owner(path: str, config: AppConfig) -> bool:
    """
    Set the owner of a file or directory asynchronously.

    Args:
        path: Path to the file or directory
        config: Application configuration

    Returns:
        True if ownership was changed, False otherwise
    """
    if config.OWNER_UID is None or config.OWNER_GID is None:
        return False

    loop = asyncio.get_running_loop()
    try:
        # Check current ownership
        stat_info = await loop.run_in_executor(None, os.stat, path)
        if (
            stat_info.st_uid == config.OWNER_UID
            and stat_info.st_gid == config.OWNER_GID
        ):
            return False  # No change needed

        # Set new ownership
        await loop.run_in_executor(
            None, lambda: os.chown(path, config.OWNER_UID, config.OWNER_GID)
        )
        return True
    except Exception as e:
        print_warning(f"Failed to set ownership on {path}: {e}")
        return False


async def set_permissions(
    path: str, config: AppConfig, is_directory: bool = False
) -> bool:
    """
    Set permissions on a file or directory asynchronously.

    Args:
        path: Path to the file or directory
        config: Application configuration
        is_directory: True if the path is a directory

    Returns:
        True if permissions were set successfully, False otherwise
    """
    loop = asyncio.get_running_loop()
    try:
        # Set owner first
        owner_changed = await set_owner(path, config)

        # Set permissions
        permissions = (
            config.DIR_PERMISSIONS if is_directory else config.FILE_PERMISSIONS
        )
        await loop.run_in_executor(None, lambda: os.chmod(path, permissions))

        return owner_changed or True
    except Exception as e:
        print_warning(f"Failed to set permissions on {path}: {e}")
        return False


async def verify_paths(config: AppConfig) -> bool:
    """
    Verify that source and destination directories exist and are valid.

    Args:
        config: Application configuration

    Returns:
        True if paths are valid, False otherwise
    """
    # Check source directory
    if not os.path.exists(config.SOURCE_DIR) or not os.path.isdir(config.SOURCE_DIR):
        print_error(f"Source directory invalid: {config.SOURCE_DIR}")
        return False

    # Check/create destination directory
    if not os.path.exists(config.DEST_DIR):
        try:
            os.makedirs(config.DEST_DIR, exist_ok=True)
            print_step(f"Created destination directory: {config.DEST_DIR}")
            await set_permissions(config.DEST_DIR, config, is_directory=True)
        except Exception as e:
            print_error(f"Failed to create destination directory: {e}")
            return False
    elif not os.path.isdir(config.DEST_DIR):
        print_error(f"Destination path is not a directory: {config.DEST_DIR}")
        return False

    # Set permissions on destination directory
    await set_permissions(config.DEST_DIR, config, is_directory=True)
    return True


async def process_file(
    rel_path: str,
    config: AppConfig,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None,
) -> FileInfo:
    """
    Process a single file during deployment.

    Args:
        rel_path: Relative path of the file
        config: Application configuration
        progress: Progress bar instance
        task_id: ID of the task in the progress bar

    Returns:
        FileInfo object with the result of the operation
    """
    source_path = os.path.join(config.SOURCE_DIR, rel_path)
    dest_path = os.path.join(config.DEST_DIR, rel_path)
    filename = os.path.basename(source_path)
    perm_changed = False

    # Update progress if provided
    if progress and task_id is not None:
        progress.update(task_id, description=f"Processing {filename}")

    # Create destination directory if needed
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # Determine file status
    if not os.path.exists(dest_path):
        status = FileStatus.NEW
    else:
        try:
            source_hash = await get_file_hash(source_path)
            dest_hash = await get_file_hash(dest_path)
            status = (
                FileStatus.UPDATED if source_hash != dest_hash else FileStatus.UNCHANGED
            )
        except Exception as e:
            print_warning(f"Error comparing file {filename}: {e}")
            status = FileStatus.UPDATED

    # Process the file based on its status
    if status in (FileStatus.NEW, FileStatus.UPDATED):
        try:
            # Use run_in_executor for file operations
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: shutil.copy2(source_path, dest_path)
            )

            # Set permissions
            perm_changed = await set_permissions(dest_path, config)

        except Exception as e:
            print_warning(f"Failed to copy file {filename}: {e}")
            return FileInfo(
                filename=rel_path,
                status=FileStatus.FAILED,
                source_path=source_path,
                dest_path=dest_path,
                error_message=str(e),
            )
    else:
        # For unchanged files, just verify permissions
        perm_changed = await set_permissions(dest_path, config)

    # Advance progress if provided
    if progress and task_id is not None:
        progress.advance(task_id)

    return FileInfo(
        filename=rel_path,
        status=status,
        permission_changed=perm_changed,
        source_path=source_path,
        dest_path=dest_path,
    )


async def deploy_files(config: AppConfig) -> DeploymentResult:
    """
    Deploy files from source to destination.

    Args:
        config: Application configuration

    Returns:
        DeploymentResult object with deployment statistics
    """
    result = DeploymentResult()

    try:
        # List all files in the source directory
        source_files = await list_all_files(config.SOURCE_DIR)
        if not source_files:
            print_warning("No files found in source directory")
            result.complete()
            return result
    except FileOperationError as e:
        print_error(str(e))
        result.complete()
        return result

    # Create progress bar
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(
            bar_width=config.PROGRESS_WIDTH,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        # Add task to progress bar
        task = progress.add_task("Deploying files", total=len(source_files))

        # Process files with limited concurrency
        tasks = []
        semaphore = asyncio.Semaphore(config.MAX_WORKERS)

        async def process_with_semaphore(file_path: str) -> FileInfo:
            """Process a file with the semaphore to limit concurrency."""
            async with semaphore:
                return await process_file(file_path, config, progress, task)

        # Create tasks for all files
        for file_path in source_files:
            tasks.append(asyncio.create_task(process_with_semaphore(file_path)))

        # Wait for all tasks to complete
        file_results = await asyncio.gather(*tasks)

        # Add results to deployment result
        for file_info in file_results:
            result.add_file(file_info)

    result.complete()
    return result


# -—————————————————————
# Reporting Functions
# -—————————————————————
def display_deployment_details(config: AppConfig) -> None:
    """Display detailed information about the deployment configuration."""
    current_user = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False

    # Create warning about permissions if needed
    permission_warning = ""
    if not is_root and config.OWNER_USER != current_user:
        permission_warning = f"\n[bold {NordColors.YELLOW}]Warning: Not running as root. Permission changes may fail.[/]"

    # Build panel content
    panel_content = f"""
Source: [bold]{config.SOURCE_DIR}[/]
Target: [bold]{config.DEST_DIR}[/]
Owner: [bold]{config.OWNER_USER}[/] (UID: {config.OWNER_UID or "Unknown"})
Permissions: [bold]Files: {oct(config.FILE_PERMISSIONS)[2:]}, Dirs: {oct(config.DIR_PERMISSIONS)[2:]}[/]
Running as: [bold]{current_user}[/] ({"root" if is_root else "non-root"})
{permission_warning}
"""

    # Display the panel
    console.print(
        Panel(
            Text.from_markup(panel_content),
            title=f"[bold {NordColors.FROST_2}]Deployment Details[/]",
            border_style=NordColors.FROST_3,
            padding=(1, 2),
            expand=True,
        )
    )


def create_stats_table(result: DeploymentResult) -> Table:
    """Create a table showing deployment statistics."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Deployment Statistics[/]",
        title_justify="center",
    )

    # Add columns
    table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    # Add rows with statistics
    table.add_row("New Files", str(result.new_files))
    table.add_row("Updated Files", str(result.updated_files))
    table.add_row("Unchanged Files", str(result.unchanged_files))
    table.add_row("Failed Files", str(result.failed_files))
    table.add_row("Total Files", str(result.total_files))
    table.add_row("Permission Changes", str(result.permission_changes))
    table.add_row("Elapsed Time", f"{result.elapsed_time:.2f} seconds")

    return table


def create_file_details_table(result: DeploymentResult, max_files: int = 20) -> Table:
    """Create a table showing details of modified files."""
    # Filter for modified files
    modified_files = [
        f for f in result.files if f.status in (FileStatus.NEW, FileStatus.UPDATED)
    ]

    # Create table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Modified Files[/]",
        title_justify="center",
    )

    # Add columns
    table.add_column("Filename", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", justify="center")
    table.add_column("Permissions", justify="center")

    # Limit the number of files displayed
    display_files = modified_files[:max_files]

    # Add rows for each file
    for file_info in display_files:
        # Create status text with appropriate styling
        if file_info.status == FileStatus.NEW:
            status_text = Text("✓ NEW", style=f"bold {NordColors.GREEN}")
        elif file_info.status == FileStatus.UPDATED:
            status_text = Text("↺ UPDATED", style=f"bold {NordColors.FROST_2}")
        elif file_info.status == FileStatus.FAILED:
            status_text = Text("✗ FAILED", style=f"bold {NordColors.RED}")
        else:
            status_text = Text("● UNCHANGED", style=NordColors.SNOW_STORM_1)

        # Create permissions text
        permission_text = "changed" if file_info.permission_changed else "standard"

        # Add row to table
        table.add_row(file_info.filename, status_text, permission_text)

    # Add a row for additional files if there are more than max_files
    if len(modified_files) > max_files:
        table.add_row(f"... and {len(modified_files) - max_files} more files", "", "")

    return table


# -—————————————————————
# Main Application Flow
# -—————————————————————
async def run_deployment() -> None:
    """Run the deployment process."""
    # Create configuration
    config = AppConfig()

    # Display header and start message
    console.print(create_header())
    print_step(f"Starting deployment at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print()

    # Display deployment details
    display_deployment_details(config)

    # Verify paths
    console.print(create_section_header("Path Verification"))
    if not await verify_paths(config):
        display_panel(
            "Deployment failed due to path verification errors.",
            style=NordColors.RED,
            title="Error",
        )
        sys.exit(1)
    print_success("Source and destination directories verified")
    console.print()

    # Deploy files
    console.print(create_section_header("File Deployment"))
    try:
        result = await deploy_files(config)
        console.print(create_stats_table(result))
        console.print()

        # Show detailed report
        if result.new_files or result.updated_files:
            console.print(create_file_details_table(result))
            console.print()
            display_panel(
                f"Successfully deployed {result.new_files + result.updated_files} files.\n"
                f"Changed permissions on {result.permission_changes} files/dirs.\n"
                f"User '{config.OWNER_USER}' now has appropriate permissions on all deployed files.",
                style=NordColors.GREEN,
                title="Deployment Successful",
            )
        else:
            display_panel(
                f"No files needed updating. All files are already up to date.\n"
                f"Verified permissions on {result.permission_changes} files/dirs.",
                style=NordColors.FROST_3,
                title="Deployment Complete",
            )
    except Exception as e:
        display_panel(
            f"Deployment failed: {str(e)}", style=NordColors.RED, title="Error"
        )
        console.print_exception()
        sys.exit(1)


# -—————————————————————
# Entry Point
# -—————————————————————
def main() -> None:
    """Main entry point of the application."""
    try:
        # Create and set up the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the deployment
        loop.run_until_complete(run_deployment())
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
    finally:
        try:
            # Get all tasks and cancel them
            loop = asyncio.get_event_loop()
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()

            # Allow cancelled tasks to complete
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            # Close the loop
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")

        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
