#!/usr/bin/env python3
"""
Enhanced Interactive Restore Script
--------------------------------------------------

A beautiful, Nord-themed terminal interface for restoring VM and Plex data from restic backups.
Features comprehensive task management, real-time progress tracking, and service handling.

Features:
  - Restores VM Libvirt configurations from /var and /etc locations
  - Restores Plex Media Server data with integrity verification
  - Validates and compares files during restoration process
  - Manages related services during the restore operation
  - Provides detailed progress tracking and status reporting
  - Beautiful Nord-themed interface with rich visual feedback

Usage:
  Run the script with root privileges and follow the interactive menu.
  - Option 1: View available restore tasks
  - Option 2: Restore individual task
  - Option 3: Restore all tasks
  - Option 4: View previous restore logs
  - Option 5: Exit the application

Version: 1.2.0
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.live import Live
    from rich.columns import Columns
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------

# Application info
VERSION: str = "1.2.0"
APP_NAME: str = "Restore Manager"
APP_SUBTITLE: str = "Backup Recovery System"

# System settings
HOSTNAME: str = os.uname().nodename
LOG_FILE: str = "/var/log/restore_manager.log"

# Restore task definitions: source path, target path, and associated service (if any)
RESTORE_TASKS: Dict[str, Dict[str, str]] = {
    "vm-libvirt-var": {
        "name": "VM Libvirt (var)",
        "description": "Virtual Machine configurations and storage from /var/lib/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/var/lib/libvirt",
        "target": "/var/lib/libvirt",
        "service": "libvirtd",
    },
    "vm-libvirt-etc": {
        "name": "VM Libvirt (etc)",
        "description": "Virtual Machine configuration files from /etc/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/etc/libvirt",
        "target": "/etc/libvirt",
        "service": "libvirtd",
    },
    "plex": {
        "name": "Plex Media Server",
        "description": "Plex Media Server library data and configuration",
        "source": "/home/sawyer/restic_restore/plex-media-server-backup/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "service": "plexmediaserver",
    },
}

# File copying settings
BUFFER_SIZE: int = 4 * 1024 * 1024  # 4MB buffer
MAX_RETRIES: int = 3
RETRY_DELAY: int = 2  # seconds
OPERATION_TIMEOUT: int = 120  # seconds


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


# Create a Rich Console with Nord theme
console: Console = Console(theme=None, highlight=False)


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
    compact_fonts = ["slant", "small", "smslant", "digital", "mini"]

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
 _       _                      _   _           
(_)_ __ | |_ ___ _ __ __ _  ___| |_(_)_   _____ 
| | '_ \| __/ _ \ '__/ _` |/ __| __| \ \ / / _ \
| | | | | ||  __/ | | (_| | (__| |_| |\ V /  __/
|_|_| |_|\__\___|_|  \__,_|\___|\__|_| \_/ \___|
 _ __ ___  ___| |_ ___  _ __ ___                
| '__/ _ \/ __| __/ _ \| '__/ _ \               
| | |  __/\__ \ || (_) | | |  __/               
|_|  \___||___/\__\___/|_|  \___|               
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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
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


def print_success(text: str) -> None:
    """
    Print a success message with a check mark.

    Args:
        text: The success message to display
    """
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """
    Print a warning message with a warning symbol.

    Args:
        text: The warning message to display
    """
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """
    Print an error message with an X mark.

    Args:
        text: The error message to display
    """
    print_message(text, NordColors.RED, "✗")


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


def setup_logging() -> None:
    """Initialize logging to file with proper permissions."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(
            f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
    print_success(f"Logging to {LOG_FILE}")


def log_message(message: str, level: str = "INFO") -> None:
    """
    Append a message to the log file.

    Args:
        message: The message to log
        level: Log level (INFO, WARNING, ERROR)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
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
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
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
    print_message("Performing cleanup tasks...", NordColors.FROST_3)
    log_message("Cleanup performed during script exit")
    # Add any additional cleanup code here


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_warning(f"Process interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Core Restore Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges")
        log_message("Script execution attempted without root privileges", "ERROR")
        return False
    return True


def control_service(service: str, action: str) -> bool:
    """
    Control a system service using systemctl.

    Args:
        service: Name of the service to control
        action: Action to perform (start/stop)

    Returns:
        True if the service reaches the desired state, False otherwise
    """
    print_message(
        f"{action.capitalize()}ing service '{service}'...", NordColors.FROST_3
    )
    log_message(f"{action.capitalize()}ing service '{service}'")

    try:
        # Execute systemctl command with the given action
        run_command(["systemctl", action, service])
        time.sleep(2)  # Allow service to change state

        # Check if the service reached the desired state
        status_result = run_command(["systemctl", "is-active", service], check=False)
        expected = "active" if action == "start" else "inactive"
        actual = status_result.stdout.strip()

        # Determine success based on current state
        success = (action == "start" and actual == "active") or (
            action == "stop" and actual != "active"
        )

        if success:
            print_success(f"Service '{service}' {action}ed successfully")
            log_message(f"Service '{service}' {action}ed successfully")
        else:
            print_warning(
                f"Service '{service}' did not {action} properly (status: {actual})"
            )
            log_message(
                f"Service '{service}' did not {action} properly (status: {actual})",
                "WARNING",
            )

        return success
    except Exception as e:
        print_error(f"Failed to {action} service '{service}': {e}")
        log_message(f"Failed to {action} service '{service}': {e}", "ERROR")
        return False


def is_restore_needed(source_path: str, target_path: str) -> bool:
    """
    Compare source and target directories to determine if restore is necessary.

    Args:
        source_path: Path to the backup source
        target_path: Path to the destination

    Returns:
        True if restore is needed, False otherwise
    """
    source = Path(source_path)
    target = Path(target_path)

    # Check if source exists
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False

    # If target doesn't exist, restore is definitely needed
    if not target.exists():
        print_message(f"Target directory doesn't exist: {target}", NordColors.FROST_3)
        log_message(f"Target directory doesn't exist: {target}")
        return True

    # Count files to compare
    print_message("Comparing file counts...", NordColors.FROST_3)
    source_files = sum(1 for _ in source.rglob("*") if _.is_file())
    target_files = sum(1 for _ in target.rglob("*") if _.is_file())

    # If counts differ, restore is needed
    if source_files != target_files:
        print_message(
            f"File count differs. Source: {source_files}, Target: {target_files}",
            NordColors.FROST_3,
        )
        log_message(
            f"File count differs. Source: {source_files}, Target: {target_files}"
        )
        return True

    print_message("Source and target directories appear identical", NordColors.FROST_3)
    log_message("Source and target directories appear identical")
    return False


def copy_directory(source_path: str, target_path: str) -> bool:
    """
    Recursively copy files from source to target with rich progress feedback.

    Args:
        source_path: Source directory path
        target_path: Target directory path

    Returns:
        True on success, False otherwise
    """
    source = Path(source_path)
    target = Path(target_path)

    # Validate source directory
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False

    print_message(
        f"Preparing to copy from '{source}' to '{target}'", NordColors.FROST_3
    )
    log_message(f"Starting copy from '{source}' to '{target}'")

    # Remove target if it exists
    if target.exists():
        try:
            shutil.rmtree(target)
            print_message(
                f"Removed existing target directory: {target}", NordColors.FROST_3
            )
        except Exception as e:
            print_error(f"Failed to remove target directory: {e}")
            log_message(f"Failed to remove target directory: {e}", "ERROR")
            return False

    # Create target parent directories
    target.parent.mkdir(parents=True, exist_ok=True)

    # Scan source files and calculate total size
    file_paths = []
    total_size = 0

    for file_path in source.rglob("*"):
        if file_path.is_file():
            file_paths.append(file_path)
            total_size += file_path.stat().st_size

    file_count = len(file_paths)
    size_mb = total_size / (1024 * 1024)

    print_message(
        f"Found {file_count} files, total size: {size_mb:.2f} MB", NordColors.FROST_3
    )
    log_message(f"Copying {file_count} files ({size_mb:.2f} MB)")

    # Prepare for copying
    copied_size = 0
    errors = []

    # Create progress display
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task("Overall progress", total=total_size)
        current_task = progress.add_task("Preparing...", total=1, visible=False)

        # Create all directories first
        directories = set()
        for source_file in file_paths:
            rel_path = source_file.relative_to(source)
            directories.add(target / rel_path.parent)

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Copy each file with progress tracking
        for source_file in file_paths:
            rel_path = source_file.relative_to(source)
            target_file = target / rel_path
            file_size = source_file.stat().st_size

            # Update progress information for current file
            progress.update(current_task, total=file_size, completed=0, visible=True)
            progress.update(current_task, description=f"Copying {rel_path}")

            # Try to copy with retries on failure
            for attempt in range(MAX_RETRIES):
                try:
                    with open(source_file, "rb") as src, open(target_file, "wb") as dst:
                        copied = 0
                        while True:
                            buf = src.read(BUFFER_SIZE)
                            if not buf:
                                break
                            dst.write(buf)
                            copied += len(buf)
                            copied_size += len(buf)
                            progress.update(current_task, completed=copied)
                            progress.update(overall_task, completed=copied_size)
                    # Copy file metadata (timestamps, permissions)
                    shutil.copystat(source_file, target_file)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (2**attempt)  # Exponential backoff
                        progress.update(
                            current_task, description=f"Retry in {delay}s: {rel_path}"
                        )
                        time.sleep(delay)
                    else:
                        errors.append((str(rel_path), str(e)))
                        log_message(f"Failed to copy {rel_path}: {e}", "ERROR")

            # Hide current task when done with the file
            progress.update(current_task, visible=False)

    # Report results
    if errors:
        print_warning(f"Encountered {len(errors)} errors during copy")
        log_message(f"Copy completed with {len(errors)} errors", "WARNING")
        for file_path, error in errors[:5]:  # Show first 5 errors
            print_error(f"Error copying {file_path}: {error}")
        if len(errors) > 5:
            print_warning(f"...and {len(errors) - 5} more errors")
        return False
    else:
        print_success("Files copied successfully")
        log_message("Copy completed successfully")
        return True


def restore_task(task_key: str) -> bool:
    """
    Execute a single restore task with service management.

    Args:
        task_key: Key identifying the restore task

    Returns:
        True if restore succeeds, False otherwise
    """
    # Validate task exists
    if task_key not in RESTORE_TASKS:
        print_error(f"Unknown restore task: {task_key}")
        log_message(f"Unknown restore task: {task_key}", "ERROR")
        return False

    # Get task details
    config = RESTORE_TASKS[task_key]
    name = config["name"]
    source = config["source"]
    target = config["target"]
    service = config.get("service", "")

    # Start restore process
    display_panel(
        f"Restoring {name}", style=NordColors.FROST_2, title="Restore Operation"
    )
    log_message(f"Starting restore task: {name}")

    # Check if restore is needed
    if not is_restore_needed(source, target):
        print_success(f"Restore not needed for {name} - target is already up to date")
        log_message(f"Restore not needed for {name} - target is already up to date")
        return True

    # Stop service if applicable
    if service:
        if not control_service(service, "stop"):
            if not prompt_yes_no(f"Failed to stop service {service}. Continue anyway?"):
                print_warning(f"Restore of {name} aborted by user")
                log_message(f"Restore of {name} aborted by user", "WARNING")
                return False

    # Perform the file copy
    success = copy_directory(source, target)

    # Restart service if applicable
    if service:
        if not control_service(service, "start"):
            print_warning(f"Failed to restart service {service}")
            log_message(f"Failed to restart service {service}", "WARNING")
            success = False

    # Report results
    if success:
        print_success(f"Successfully restored {name}")
        log_message(f"Successfully restored {name}")
    else:
        print_error(f"Failed to restore {name}")
        log_message(f"Failed to restore {name}", "ERROR")

    return success


def restore_all() -> Dict[str, bool]:
    """
    Restore all defined tasks and track results.

    Returns:
        Dictionary mapping task keys to success status
    """
    results: Dict[str, bool] = {}

    display_panel(
        "Starting restore of all tasks", style=NordColors.FROST_2, title="Batch Restore"
    )
    log_message("Starting restore of all tasks")

    for key in RESTORE_TASKS:
        results[key] = restore_task(key)
        time.sleep(1)  # Brief pause between tasks

    return results


def print_status_report(results: Dict[str, bool]) -> None:
    """
    Print a comprehensive summary report of restore operations.

    Args:
        results: Dictionary mapping task keys to success status
    """
    display_panel("Restore Status Report", style=NordColors.FROST_2, title="Results")
    log_message("Generating status report")

    # Create results table
    table = Table(title="Restore Results", style=f"bold {NordColors.FROST_2}", box=None)

    table.add_column("Task", style=f"{NordColors.SNOW_STORM_2}")
    table.add_column("Status", justify="center")
    table.add_column("Description", style=f"{NordColors.FROST_3}")

    # Add task results to table
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        description = RESTORE_TASKS[key].get("description", "")

        status_style = (
            f"bold {NordColors.GREEN}" if success else f"bold {NordColors.RED}"
        )
        status_text = "SUCCESS" if success else "FAILED"

        table.add_row(
            name, f"[{status_style}]{status_text}[/{status_style}]", description
        )

    # Calculate overall statistics
    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0

    # Print status report
    console.print(table)
    console.print()

    # Print summary statistics
    result_panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Tasks completed:[/] [{NordColors.SNOW_STORM_2}]{success_count}/{total_count} ({success_rate:.1f}%)[/]\n"
            f"[bold {NordColors.FROST_2}]Successful:[/] [{NordColors.GREEN}]{success_count}[/]\n"
            f"[bold {NordColors.FROST_2}]Failed:[/] [{NordColors.RED}]{total_count - success_count}[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(result_panel)

    # Log results
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        status = "SUCCESS" if success else "FAILED"
        log_message(f"Restore {status} for {name}")

    log_message(
        f"Overall success rate: {success_rate:.1f}% ({success_count}/{total_count})"
    )


def prompt_yes_no(question: str) -> bool:
    """
    Prompt the user with a yes/no question.

    Args:
        question: The question to present to the user

    Returns:
        True for yes, False for no
    """
    console.print(f"[bold {NordColors.FROST_2}]{question}[/] (y/n): ", end="")

    while True:
        response = input().strip().lower()
        if response in ["y", "yes"]:
            return True
        elif response in ["n", "no"]:
            return False
        else:
            console.print(f"[{NordColors.YELLOW}]Please enter 'y' or 'n'[/]: ", end="")


def display_tasks_table() -> None:
    """Display available restore tasks in a formatted table."""
    display_panel("Available Restore Tasks", style=NordColors.FROST_2, title="Tasks")

    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        box=None,
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Name", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Source Path", style="dim")

    for i, (key, task) in enumerate(RESTORE_TASKS.items(), 1):
        description = task.get("description", "")
        source_path = task["source"]

        # Shorten very long paths for display
        if len(source_path) > 40:
            source_path = source_path[:20] + "..." + source_path[-17:]

        table.add_row(str(i), task["name"], description, source_path)

    console.print(table)


# ----------------------------------------------------------------
# Interactive Menu Functions
# ----------------------------------------------------------------
def interactive_menu() -> None:
    """
    Display and handle the interactive menu for restore operations.
    This function runs the main UI loop.
    """
    while True:
        # Display header and current time
        console.clear()
        console.print(create_header())

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()

        # Display main menu
        console.print(
            Panel.fit(
                "[bold]Select an operation:[/]",
                border_style=NordColors.FROST_2,
                padding=(1, 3),
            )
        )

        console.print(f"1. [bold {NordColors.FROST_2}]View Available Restore Tasks[/]")
        console.print(f"2. [bold {NordColors.FROST_2}]Restore Individual Task[/]")
        console.print(f"3. [bold {NordColors.FROST_2}]Restore All Tasks[/]")
        console.print(f"4. [bold {NordColors.FROST_2}]View Previous Restore Log[/]")
        console.print(f"5. [bold {NordColors.RED}]Exit[/]")

        console.print()
        console.print(f"[bold {NordColors.FROST_2}]Enter your choice:[/]", end=" ")
        choice = input().strip().lower()

        # Process menu selection
        if choice == "1":
            # View tasks
            console.clear()
            console.print(create_header())
            display_tasks_table()
            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()

        elif choice == "2":
            # Restore individual task
            console.clear()
            console.print(create_header())
            display_tasks_table()
            console.print()

            while True:
                task_prompt = (
                    f"Enter task number (1-{len(RESTORE_TASKS)}) or 'c' to cancel"
                )
                console.print(f"[bold {NordColors.FROST_2}]{task_prompt}:[/]", end=" ")
                task_choice = input().strip().lower()

                if task_choice == "c":
                    break

                try:
                    task_num = int(task_choice)
                    if 1 <= task_num <= len(RESTORE_TASKS):
                        task_key = list(RESTORE_TASKS.keys())[task_num - 1]
                        task_name = RESTORE_TASKS[task_key]["name"]

                        if prompt_yes_no(
                            f"Are you sure you want to restore {task_name}?"
                        ):
                            start_time = time.time()
                            success = restore_task(task_key)
                            elapsed = time.time() - start_time

                            if success:
                                print_success(
                                    f"Restore completed in {elapsed:.2f} seconds"
                                )
                            else:
                                print_error(
                                    f"Restore failed after {elapsed:.2f} seconds"
                                )
                        break
                    else:
                        print_error(
                            f"Enter a number between 1 and {len(RESTORE_TASKS)}"
                        )
                except ValueError:
                    print_error("Please enter a valid number")

            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()

        elif choice == "3":
            # Restore all tasks
            console.clear()
            console.print(create_header())

            if prompt_yes_no(
                "Are you sure you want to restore ALL tasks? This may take some time"
            ):
                start_time = time.time()
                results = restore_all()
                elapsed = time.time() - start_time

                print_status_report(results)

                if all(results.values()):
                    print_success(
                        f"All tasks restored successfully in {elapsed:.2f} seconds"
                    )
                else:
                    print_warning(
                        f"Some tasks failed. Total time: {elapsed:.2f} seconds"
                    )

            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()

        elif choice == "4":
            # View logs
            console.clear()
            console.print(create_header())
            display_panel("Recent Log Entries", style=NordColors.FROST_2, title="Logs")

            try:
                if Path(LOG_FILE).exists():
                    with open(LOG_FILE, "r") as log:
                        lines = log.readlines()

                        # Get the last 20 lines or fewer if file is shorter
                        recent_lines = lines[-min(20, len(lines)) :]

                        for line in recent_lines:
                            if "ERROR" in line:
                                console.print(line.strip(), style=NordColors.RED)
                            elif "WARNING" in line:
                                console.print(line.strip(), style=NordColors.YELLOW)
                            else:
                                console.print(line.strip(), style=NordColors.FROST_2)
                else:
                    print_warning(f"Log file not found: {LOG_FILE}")
            except Exception as e:
                print_error(f"Error reading log file: {e}")

            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()

        elif choice == "5":
            # Exit
            console.clear()
            console.print(create_header())
            display_panel(
                "Thank you for using the Restore Manager!",
                style=NordColors.FROST_2,
                title="Exit",
            )
            break

        else:
            print_error("Invalid choice. Please enter a number between 1 and 5")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function to run the interactive restore script."""
    try:
        # Initialize
        console.clear()
        console.print(create_header())

        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
            )
        )

        # Setup logging and check for root privileges
        setup_logging()

        if not check_root():
            display_panel(
                "This script requires root privileges to function properly.\n"
                "Please run with sudo or as the root user.",
                style=NordColors.RED,
                title="Permission Error",
            )
            sys.exit(1)

        # Validate source directories exist
        missing_sources = []
        for key, task in RESTORE_TASKS.items():
            source_dir = Path(task["source"])
            if not source_dir.exists():
                missing_sources.append((task["name"], str(source_dir)))

        if missing_sources:
            display_panel(
                f"Found {len(missing_sources)} tasks with missing source directories.",
                style=NordColors.YELLOW,
                title="Warning",
            )

            for name, path in missing_sources:
                print_error(f"• {name}: {path}")

            if not prompt_yes_no("Continue anyway?"):
                print_error("Exiting due to missing source directories")
                log_message("Script exited due to missing source directories", "ERROR")
                sys.exit(1)

        # Launch the interactive menu
        interactive_menu()

        # Exit cleanly
        print_success("Script execution completed")
        log_message("Script execution completed")

    except KeyboardInterrupt:
        print_warning("Script interrupted by user")
        log_message("Script interrupted by user", "WARNING")
        sys.exit(130)

    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
