#!/usr/bin/env python3
"""
Enhanced Script Deployment Tool
--------------------------------------------------

A powerful terminal-based utility for deploying scripts from a source directory
to a destination directory with proper permission handling.

Features:
  • Efficiently copies files by checking hashes and only updating what has changed
  • Makes Python and shell scripts executable after copying
  • Sets full ownership and permissions for user "sawyer"
  • Beautiful Nord-themed terminal interface with real-time progress tracking
  • Displays detailed statistics and deployment results

Usage:
  python3 deploy.py

Version: 2.0.0
"""

import atexit
import hashlib
import os
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable


# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
def install_missing_packages():
    """Install required Python packages if they're missing."""
    required_packages = ["rich", "pyfiglet"]
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing_packages,
                check=True,
                capture_output=True,
            )
            print("Successfully installed required packages. Restarting script...")
            # Restart the script to ensure imports work
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install required packages: {e}")
            print(
                "Please install them manually: pip install "
                + " ".join(missing_packages)
            )
            sys.exit(1)


# Try installing missing packages
install_missing_packages()

# Now import the installed packages
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
        TaskProgressColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.live import Live
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
except ImportError as e:
    print(f"Error importing required libraries: {e}")
    print("Please install them manually: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    """Application configuration settings."""

    VERSION = "2.0.0"
    APP_NAME = "Script Deployer"
    APP_SUBTITLE = "File Deployment & Permission Utility"

    # Deployment configuration
    SOURCE_DIR = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
    DEST_DIR = "/home/sawyer/bin"

    # User configuration
    OWNER_USER = "sawyer"

    # Try to get user information
    try:
        OWNER_UID = pwd.getpwnam(OWNER_USER).pw_uid
        OWNER_GID = pwd.getpwnam(OWNER_USER).pw_gid
    except KeyError:
        OWNER_UID = None
        OWNER_GID = None

    # Permission settings
    FILE_PERMISSIONS = 0o700  # rwx------
    DIR_PERMISSIONS = 0o700  # rwx------

    # Executable file extensions
    EXECUTABLE_EXTENSIONS = [".py", ".sh"]

    # Terminal settings
    try:
        TERM_WIDTH = shutil.get_terminal_size().columns
    except:
        TERM_WIDTH = 80
    PROGRESS_WIDTH = min(50, TERM_WIDTH - 30)

    # Command timeouts
    DEFAULT_TIMEOUT = 30  # seconds


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


# Create a Rich Console with Nord theme
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


# ----------------------------------------------------------------
# Custom Exception Classes
# ----------------------------------------------------------------
class DeploymentError(Exception):
    """Base exception for Script Deployer errors."""

    pass


class PathVerificationError(DeploymentError):
    """Raised when path verification fails."""

    pass


class PermissionError(DeploymentError):
    """Raised when permission operations fail."""

    pass


class FileOperationError(DeploymentError):
    """Raised when file operations fail."""

    pass


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class FileStatus:
    """Enumeration of possible file statuses during deployment."""

    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


class DeploymentResult:
    """Tracks the results of the deployment operation."""

    def __init__(self):
        self.new_files = 0
        self.updated_files = 0
        self.unchanged_files = 0
        self.failed_files = 0
        self.executable_files = 0
        self.permission_changes = 0
        self.file_details = []
        self.start_time = time.time()
        self.end_time = None

    @property
    def total_files(self) -> int:
        """Get the total number of files processed."""
        return self.new_files + self.updated_files + self.unchanged_files

    @property
    def elapsed_time(self) -> float:
        """Get the elapsed time in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def complete(self):
        """Mark the deployment as complete."""
        self.end_time = time.time()

    def add_file(
        self,
        filename: str,
        status: str,
        is_executable: bool = False,
        permission_changed: bool = False,
    ):
        """Add a file to the deployment results."""
        self.file_details.append(
            {
                "filename": filename,
                "status": status,
                "executable": is_executable,
                "permission_changed": permission_changed,
            }
        )

        if status == FileStatus.NEW:
            self.new_files += 1
        elif status == FileStatus.UPDATED:
            self.updated_files += 1
        elif status == FileStatus.UNCHANGED:
            self.unchanged_files += 1
        elif status == FileStatus.FAILED:
            self.failed_files += 1

        if is_executable:
            self.executable_files += 1

        if permission_changed:
            self.permission_changes += 1


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
            ascii_art = fig.renderText(AppConfig.APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
               _       _         _            _                       
 ___  ___ _ __(_)_ __ | |_    __| | ___ _ __ | | ___  _   _  ___ _ __ 
/ __|/ __| '__| | '_ \| __|  / _` |/ _ \ '_ \| |/ _ \| | | |/ _ \ '__|
\__ \ (__| |  | | |_) | |_  | (_| |  __/ |_) | | (_) | |_| |  __/ |   
|___/\___|_|  |_| .__/ \__|  \__,_|\___| .__/|_|\___/ \__, |\___|_|   
                |_|                    |_|            |___/           
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
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def create_section_header(title: str) -> Panel:
    """
    Create a styled section header panel.

    Args:
        title: The section title

    Returns:
        A styled panel for the section
    """
    return Panel(
        Text(title, style=f"bold {NordColors.FROST_1}"),
        border_style=Style(color=NordColors.FROST_3),
        padding=(0, 2),
    )


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
    sig_name = str(sig)
    if hasattr(signal, "Signals"):
        try:
            sig_name = signal.Signals(sig).name
        except ValueError:
            pass

    print_message(f"Process interrupted by signal {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers (if supported by platform)
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except (AttributeError, ValueError):
    # Some signals might not be available on all platforms
    pass
atexit.register(cleanup)


# ----------------------------------------------------------------
# File Operations
# ----------------------------------------------------------------
def get_file_hash(file_path: str) -> str:
    """
    Calculate the MD5 hash of a file's contents.

    Args:
        file_path: Path to the file

    Returns:
        MD5 hash string of the file contents
    """
    md5_hash = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            # Read and update hash in chunks for memory efficiency
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        return md5_hash.hexdigest()
    except Exception as e:
        raise FileOperationError(f"Failed to calculate hash for {file_path}: {e}")


def list_files(directory: str) -> List[str]:
    """
    List all files in a directory (non-recursively).

    Args:
        directory: Directory path to list files from

    Returns:
        List of filenames
    """
    try:
        if not os.path.exists(directory):
            return []

        return [
            f
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
        ]
    except Exception as e:
        raise FileOperationError(f"Failed to list files in {directory}: {e}")


def is_executable_file(filename: str) -> bool:
    """
    Check if a file should be made executable based on its extension.

    Args:
        filename: The name of the file to check

    Returns:
        True if file should be made executable, False otherwise
    """
    _, ext = os.path.splitext(filename)
    return ext.lower() in AppConfig.EXECUTABLE_EXTENSIONS


def make_executable(file_path: str) -> bool:
    """
    Make a file executable by setting the appropriate permissions.

    Args:
        file_path: Path to the file to make executable

    Returns:
        True if successful, False otherwise
    """
    try:
        # First make sure the file has the right ownership
        set_owner(file_path)

        # Set permissions to: User: rwx (7), Group: --- (0), Others: --- (0)
        os.chmod(file_path, AppConfig.FILE_PERMISSIONS | stat.S_IXUSR)
        return True
    except Exception as e:
        print_warning(f"Failed to set executable permissions on {file_path}: {e}")
        return False


def set_owner(path: str) -> bool:
    """
    Set the owner of a file or directory to the configured user.

    Args:
        path: Path to the file or directory

    Returns:
        True if successful, False otherwise
    """
    # Skip if uid/gid not available
    if AppConfig.OWNER_UID is None or AppConfig.OWNER_GID is None:
        return False

    try:
        # Check current ownership
        current_stat = os.stat(path)
        if (
            current_stat.st_uid == AppConfig.OWNER_UID
            and current_stat.st_gid == AppConfig.OWNER_GID
        ):
            return False  # No change needed

        # Change ownership
        os.chown(path, AppConfig.OWNER_UID, AppConfig.OWNER_GID)
        return True
    except Exception as e:
        print_warning(f"Failed to set ownership on {path}: {e}")
        return False


def set_permissions(path: str, is_directory: bool = False) -> bool:
    """
    Set permissions on a file or directory.

    Args:
        path: Path to the file or directory
        is_directory: Whether the path is a directory

    Returns:
        True if successful, False otherwise
    """
    try:
        # First make sure the file has the right ownership
        ownership_changed = set_owner(path)

        # Set proper permissions based on type
        if is_directory:
            os.chmod(path, AppConfig.DIR_PERMISSIONS)
        else:
            # For files, use basic file permissions (executable bit is added separately)
            os.chmod(path, AppConfig.FILE_PERMISSIONS)

        return True
    except Exception as e:
        print_warning(f"Failed to set permissions on {path}: {e}")
        return False


def verify_paths() -> bool:
    """
    Verify that source and destination directories exist or can be created.

    Returns:
        True if paths are valid, False otherwise
    """
    # Check source directory
    if not os.path.exists(AppConfig.SOURCE_DIR):
        print_error(f"Source directory does not exist: {AppConfig.SOURCE_DIR}")
        return False

    if not os.path.isdir(AppConfig.SOURCE_DIR):
        print_error(f"Source path is not a directory: {AppConfig.SOURCE_DIR}")
        return False

    # Check destination directory
    if not os.path.exists(AppConfig.DEST_DIR):
        try:
            os.makedirs(AppConfig.DEST_DIR, exist_ok=True)
            print_step(f"Created destination directory: {AppConfig.DEST_DIR}")

            # Set owner and permissions for the new directory
            set_permissions(AppConfig.DEST_DIR, is_directory=True)
        except Exception as e:
            print_error(f"Failed to create destination directory: {e}")
            return False

    if not os.path.isdir(AppConfig.DEST_DIR):
        print_error(f"Destination path is not a directory: {AppConfig.DEST_DIR}")
        return False

    # Always ensure permissions on the destination directory
    set_permissions(AppConfig.DEST_DIR, is_directory=True)

    return True


def deploy_files() -> DeploymentResult:
    """
    Deploy files from source to destination directory.

    Returns:
        DeploymentResult object with deployment statistics
    """
    result = DeploymentResult()

    try:
        source_files = list_files(AppConfig.SOURCE_DIR)
        dest_files = list_files(AppConfig.DEST_DIR)
    except FileOperationError as e:
        print_error(str(e))
        result.complete()
        return result

    # Track files to process
    files_to_process = []
    for file in source_files:
        source_path = os.path.join(AppConfig.SOURCE_DIR, file)
        dest_path = os.path.join(AppConfig.DEST_DIR, file)

        # Determine if file needs to be copied
        if file not in dest_files:
            # New file
            files_to_process.append((source_path, dest_path, FileStatus.NEW))
        else:
            # Existing file - check if content has changed
            try:
                source_hash = get_file_hash(source_path)
                dest_hash = get_file_hash(dest_path)

                if source_hash != dest_hash:
                    files_to_process.append(
                        (source_path, dest_path, FileStatus.UPDATED)
                    )
                else:
                    files_to_process.append(
                        (source_path, dest_path, FileStatus.UNCHANGED)
                    )
            except Exception as e:
                print_warning(f"Error comparing file {file}: {e}")
                files_to_process.append((source_path, dest_path, FileStatus.UPDATED))

    # Process files with progress bar
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Processing files"),
        BarColumn(
            bar_width=AppConfig.PROGRESS_WIDTH,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Deploying", total=len(files_to_process))

        for source_path, dest_path, status in files_to_process:
            filename = os.path.basename(source_path)
            is_executable = is_executable_file(filename)
            perm_changed = False

            if status in (FileStatus.NEW, FileStatus.UPDATED):
                try:
                    shutil.copy2(source_path, dest_path)

                    # Set permissions on the file
                    perm_changed = set_permissions(dest_path)

                    # Set executable permissions if needed
                    if is_executable:
                        make_executable(dest_path)

                    result.add_file(filename, status, is_executable, perm_changed)

                except Exception as e:
                    print_warning(f"Failed to copy file {filename}: {e}")
                    result.add_file(filename, FileStatus.FAILED)
            else:  # status == FileStatus.UNCHANGED
                # Check permissions and executable status
                perm_changed = set_permissions(dest_path)

                # Ensure executable if needed
                if is_executable and not os.access(dest_path, os.X_OK):
                    make_executable(dest_path)

                result.add_file(filename, status, is_executable, perm_changed)

            progress.advance(task)

    result.complete()
    return result


# ----------------------------------------------------------------
# Results Reporting
# ----------------------------------------------------------------
def display_deployment_details() -> None:
    """Display the deployment details in a panel."""
    current_user = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    is_root = os.geteuid() == 0

    # Create a warning if needed
    permission_warning = ""
    if not is_root and AppConfig.OWNER_USER != current_user:
        permission_warning = f"\n[bold {NordColors.YELLOW}]Warning: Not running as root. Permission changes may fail.[/]"

    panel_content = f"""
Source: [bold]{AppConfig.SOURCE_DIR}[/]
Target: [bold]{AppConfig.DEST_DIR}[/]
Owner: [bold]{AppConfig.OWNER_USER}[/] (UID: {AppConfig.OWNER_UID or "Unknown"})
Executable Extensions: [bold]{", ".join(AppConfig.EXECUTABLE_EXTENSIONS)}[/]
Permissions: [bold]Files: {oct(AppConfig.FILE_PERMISSIONS)[2:]}, Dirs: {oct(AppConfig.DIR_PERMISSIONS)[2:]}[/]
Running as: [bold]{current_user}[/] ({"root" if is_root else "non-root"})
{permission_warning}
"""

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
    """
    Create a table displaying deployment statistics.

    Args:
        result: DeploymentResult object

    Returns:
        Rich Table object
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Deployment Statistics[/]",
        title_justify="center",
    )

    table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    table.add_row("New Files", str(result.new_files))
    table.add_row("Updated Files", str(result.updated_files))
    table.add_row("Unchanged Files", str(result.unchanged_files))
    table.add_row("Failed Files", str(result.failed_files))
    table.add_row("Total Files", str(result.total_files))
    table.add_row("Executable Files", str(result.executable_files))
    table.add_row("Permission Changes", str(result.permission_changes))
    table.add_row("Elapsed Time", f"{result.elapsed_time:.2f} seconds")

    return table


def create_file_details_table(
    result: DeploymentResult, max_files: int = 20
) -> Optional[Table]:
    """
    Create a table displaying details of modified files.

    Args:
        result: DeploymentResult object
        max_files: Maximum number of files to display

    Returns:
        Rich Table object or None if no modified files
    """
    # Get modified files (new + updated)
    modified_files = [
        f
        for f in result.file_details
        if f["status"] in (FileStatus.NEW, FileStatus.UPDATED)
    ]

    if not modified_files:
        return None

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Modified Files[/]",
        title_justify="center",
    )

    table.add_column("Filename", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", justify="center")
    table.add_column("Permissions", justify="center")

    # Display up to max_files, prioritizing failures
    failed_files = [f for f in result.file_details if f["status"] == FileStatus.FAILED]
    display_files = failed_files + modified_files
    display_files = display_files[:max_files]

    for file_info in display_files:
        filename = file_info["filename"]

        if file_info["status"] == FileStatus.NEW:
            status_text = Text("✓ NEW", style=f"bold {NordColors.GREEN}")
        elif file_info["status"] == FileStatus.UPDATED:
            status_text = Text("↺ UPDATED", style=f"bold {NordColors.FROST_2}")
        elif file_info["status"] == FileStatus.FAILED:
            status_text = Text("✗ FAILED", style=f"bold {NordColors.RED}")
        else:
            status_text = Text("● UNCHANGED", style=NordColors.SNOW_STORM_1)

        permissions = []
        if file_info["executable"]:
            permissions.append("executable")
        if file_info["permission_changed"]:
            permissions.append("ownership")

        permission_text = ", ".join(permissions) if permissions else "standard"

        table.add_row(filename, status_text, permission_text)

    # Add a note if we truncated the list
    if len(modified_files) > max_files:
        table.add_row(f"... and {len(modified_files) - max_files} more files", "", "")

    return table


# ----------------------------------------------------------------
# Main Functions
# ----------------------------------------------------------------
def run_deployment() -> None:
    """Run the complete deployment process."""
    console.print(create_header())
    print_step(f"Starting deployment at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print()

    # Display deployment details
    display_deployment_details()
    console.print()

    # Step 1: Verify paths
    console.print(create_section_header("Path Verification"))
    if not verify_paths():
        display_panel(
            "Deployment failed due to path verification errors.",
            style=NordColors.RED,
            title="Error",
        )
        return
    print_success("Source and destination directories verified")
    console.print()

    # Step 2: Deploy files and set permissions
    console.print(create_section_header("File Deployment"))
    try:
        result = deploy_files()

        # Display statistics
        console.print(create_stats_table(result))
        console.print()

        # Display file details for modified files
        file_details_table = create_file_details_table(result)
        if file_details_table:
            console.print(file_details_table)
            console.print()

        # Final message
        if result.new_files > 0 or result.updated_files > 0:
            display_panel(
                f"Successfully deployed {result.new_files + result.updated_files} files.\n"
                f"Made {result.executable_files} files executable and changed permissions on {result.permission_changes} files/dirs.\n"
                f"User '{AppConfig.OWNER_USER}' now has full permissions on all deployed files.",
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
        # Display error
        display_panel(
            f"Deployment failed: {str(e)}", style=NordColors.RED, title="Error"
        )


def main() -> None:
    """Main entry point for the script."""
    try:
        run_deployment()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
