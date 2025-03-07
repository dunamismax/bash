#!/usr/bin/env python3

"""
Script Deployer - A file deployment and permission utility.

This utility copies scripts from a source directory to a destination directory,
manages permissions, and sets ownership appropriately. It provides rich terminal
output with detailed progress information and deployment statistics.
"""

import asyncio
import atexit
import hashlib
import os
import pwd
import shutil
import signal
import stat
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, TypeVar, cast, Callable

# Third-party libraries
try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
    from rich.style import Style
except ImportError as e:
    print(f"Error importing required libraries: {e}")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Enable rich traceback for better debugging
install_rich_traceback(show_locals=True)


# Type variables for generic functions
T = TypeVar("T")


# =========================================================================
# Configuration and Constants
# =========================================================================


@dataclass
class AppConfig:
    """Application configuration settings."""

    VERSION: str = "2.1.0"
    APP_NAME: str = "Script Deployer"
    APP_SUBTITLE: str = "File Deployment & Permission Utility"

    SOURCE_DIR: str = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
    DEST_DIR: str = "/home/sawyer/bin"
    OWNER_USER: str = "sawyer"

    OWNER_UID: Optional[int] = None
    OWNER_GID: Optional[int] = None

    FILE_PERMISSIONS: int = 0o700
    DIR_PERMISSIONS: int = 0o700
    EXECUTABLE_EXTENSIONS: List[str] = field(default_factory=lambda: [".py", ".sh"])

    TERM_WIDTH: int = 80
    PROGRESS_WIDTH: int = 50
    DEFAULT_TIMEOUT: int = 30

    # Number of worker threads for file operations
    MAX_WORKERS: int = 4

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


@dataclass
class NordColors:
    """Nord color theme palette."""

    # Dark base colors (Polar Night)
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"

    # Light base colors (Snow Storm)
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"

    # Accent colors (Frost)
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"

    # Other colors
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


# =========================================================================
# Custom Exception Classes
# =========================================================================


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


# =========================================================================
# Enums and Data Models
# =========================================================================


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
    is_executable: bool = False
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
    executable_files: int = 0
    permission_changes: int = 0
    files: List[FileInfo] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def total_files(self) -> int:
        """Return the total number of files processed."""
        return self.new_files + self.updated_files + self.unchanged_files

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

        if file_info.is_executable:
            self.executable_files += 1
        if file_info.permission_changed:
            self.permission_changes += 1


# =========================================================================
# UI Components
# =========================================================================

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


def create_header() -> Panel:
    """Create a stylish header panel with the app name."""
    fonts = ["slant", "small", "standard", "digital", "big"]
    ascii_art = ""

    # Try different fonts until one works
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art and ascii_art.strip():
                break
        except Exception:
            continue

    # Fallback if no font works
    if not ascii_art or not ascii_art.strip():
        ascii_art = f"  {AppConfig.APP_NAME}  "

    # Style the ASCII art with a gradient
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = NordColors.get_frost_gradient(min(len(ascii_lines), 4))

    styled_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            styled_text.append("\n")

    # Return the final panel
    return Panel(
        Align.center(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_step(message: str) -> None:
    """Print a step message with an arrow prefix."""
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    """Print a success message with a checkmark prefix."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message with a warning prefix."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message with an X prefix."""
    print_message(message, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: str = ""
) -> None:
    """Display a styled panel with a message."""
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
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


# =========================================================================
# Core Functionality
# =========================================================================


async def get_file_hash(file_path: str) -> str:
    """
    Calculate the MD5 hash of a file asynchronously.

    Args:
        file_path: Path to the file

    Returns:
        MD5 hash of the file

    Raises:
        FileOperationError: If the hash calculation fails
    """
    loop = asyncio.get_running_loop()
    try:
        # Run the hash calculation in a thread pool to avoid blocking
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

    Raises:
        FileOperationError: If the directory listing fails
    """
    loop = asyncio.get_running_loop()
    try:
        # Run the directory walk in a thread pool
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


def is_executable_file(filename: str, config: AppConfig) -> bool:
    """Check if a file should be made executable based on its extension."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in config.EXECUTABLE_EXTENSIONS


async def set_owner(path: str, config: AppConfig) -> bool:
    """
    Set the owner of a file or directory asynchronously.

    Args:
        path: Path to the file or directory
        config: Application configuration

    Returns:
        True if ownership was changed, False otherwise

    Raises:
        PermissionOperationError: If setting the owner fails
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

        return True
    except Exception as e:
        print_warning(f"Failed to set permissions on {path}: {e}")
        return False


async def make_executable(file_path: str, config: AppConfig) -> bool:
    """
    Make a file executable asynchronously.

    Args:
        file_path: Path to the file
        config: Application configuration

    Returns:
        True if the file was made executable, False otherwise
    """
    loop = asyncio.get_running_loop()
    try:
        # Set owner first
        await set_owner(file_path, config)

        # Set executable bit
        permissions = config.FILE_PERMISSIONS | stat.S_IXUSR
        await loop.run_in_executor(None, lambda: os.chmod(file_path, permissions))

        return True
    except Exception as e:
        print_warning(f"Failed to set executable permissions on {file_path}: {e}")
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
    is_exec = is_executable_file(filename, config)
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
            if is_exec:
                await make_executable(dest_path, config)

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
        if is_exec and not os.access(dest_path, os.X_OK):
            await make_executable(dest_path, config)

    # Advance progress if provided
    if progress and task_id is not None:
        progress.advance(task_id)

    return FileInfo(
        filename=rel_path,
        status=status,
        is_executable=is_exec,
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


# =========================================================================
# Reporting Functions
# =========================================================================


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
Executable Extensions: [bold]{", ".join(config.EXECUTABLE_EXTENSIONS)}[/]
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
    table.add_row("Executable Files", str(result.executable_files))
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
        permissions = []
        if file_info.is_executable:
            permissions.append("executable")
        if file_info.permission_changed:
            permissions.append("ownership")
        permission_text = ", ".join(permissions) if permissions else "standard"

        # Add row to table
        table.add_row(file_info.filename, status_text, permission_text)

    # Add a row for additional files if there are more than max_files
    if len(modified_files) > max_files:
        table.add_row(f"... and {len(modified_files) - max_files} more files", "", "")

    return table


# =========================================================================
# Application Flow
# =========================================================================


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
                f"Made {result.executable_files} files executable and changed permissions on {result.permission_changes} files/dirs.\n"
                f"User '{config.OWNER_USER}' now has full permissions on all deployed files.",
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


# =========================================================================
# Signal Handling and Cleanup
# =========================================================================


async def async_cleanup() -> None:
    """Perform async cleanup operations."""
    print_message("Cleaning up resources...", NordColors.FROST_3)

    # Cancel all remaining tasks except our own
    current_task = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is not current_task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def cleanup() -> None:
    """Synchronous cleanup handler registered with atexit."""
    print_message("Cleaning up...", NordColors.FROST_3)


async def signal_handler_async(sig: int, frame: Any) -> None:
    """Async signal handler."""
    sig_name = str(sig)
    if hasattr(signal, "Signals"):
        try:
            sig_name = signal.Signals(sig).name
        except ValueError:
            pass

    print_message(f"Process interrupted by signal {sig_name}", NordColors.YELLOW, "⚠")
    await async_cleanup()

    # Get the running loop and stop it
    loop = asyncio.get_running_loop()
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(signal_handler_async(s, None))
        )


# =========================================================================
# Main Entry Point
# =========================================================================


async def main_async() -> None:
    """Main async entry point."""
    try:
        await run_deployment()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
        await async_cleanup()
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        await async_cleanup()
        sys.exit(1)


def main() -> None:
    """Main entry point of the application."""
    try:
        # Create and set up the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Set up signal handling
        setup_signal_handlers(loop)

        # Register cleanup on exit
        atexit.register(cleanup)

        # Run the main async function
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
    finally:
        try:
            # Get all tasks and cancel them
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
