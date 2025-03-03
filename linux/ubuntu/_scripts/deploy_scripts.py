#!/usr/bin/env python3
"""
Script Deployment Tool
--------------------------------------------------

A tool for deploying scripts from a source directory to a destination directory.
The tool checks for file changes and copies only what has been modified.

Usage:
  python3 deploy.py

Version: 1.0.0
"""

import os
import sys
import shutil
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple

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
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing them now...")
    try:
        import subprocess

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
VERSION: str = "1.0.0"
APP_NAME: str = "Script Deployer"
APP_SUBTITLE: str = "File Deployment Utility"

# Deployment configuration
SOURCE_DIR: str = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
DEST_DIR: str = "/home/sawyer/bin"


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1: str = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4: str = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1: str = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2: str = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1: str = "#8FBCBB"  # Light cyan
    FROST_2: str = "#88C0D0"  # Light blue
    FROST_3: str = "#81A1C1"  # Medium blue
    FROST_4: str = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED: str = "#BF616A"  # Red
    ORANGE: str = "#D08770"  # Orange
    YELLOW: str = "#EBCB8B"  # Yellow
    GREEN: str = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a styled ASCII art header for the application.

    Returns:
        Panel containing the styled header
    """
    try:
        # Try to create ASCII art with pyfiglet
        fig = pyfiglet.Figlet(font="slant", width=60)
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        # Fallback ASCII art if pyfiglet fails
        ascii_art = """
 ____            _       _     ____             _                       
/ ___|  ___ _ __(_)_ __ | |_  |  _ \  ___ _ __ | | ___  _   _  ___ _ __ 
\___ \ / __| '__| | '_ \| __| | | | |/ _ \ '_ \| |/ _ \| | | |/ _ \ '__|
 ___) | (__| |  | | |_) | |_  | |_| |  __/ |_) | | (_) | |_| |  __/ |   
|____/ \___|_|  |_| .__/ \__| |____/ \___| .__/|_|\___/ \__, |\___|_|   
                  |_|                    |_|            |___/           
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Apply styling with Nord colors
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

    # Add decorative border
    border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = border + "\n" + styled_text + border

    # Create a panel
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
    """Print a styled message."""
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
    """Display a message in a styled panel."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


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
    with open(file_path, "rb") as f:
        # Read and update hash in chunks for memory efficiency
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    return md5_hash.hexdigest()


def list_files(directory: str) -> List[str]:
    """
    List all files in a directory (non-recursively).

    Args:
        directory: Directory path to list files from

    Returns:
        List of filenames
    """
    if not os.path.exists(directory):
        return []

    return [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]


def verify_paths() -> bool:
    """
    Verify that source and destination directories exist or can be created.

    Returns:
        True if paths are valid, False otherwise
    """
    # Check source directory
    if not os.path.exists(SOURCE_DIR):
        print_error(f"Source directory does not exist: {SOURCE_DIR}")
        return False

    if not os.path.isdir(SOURCE_DIR):
        print_error(f"Source path is not a directory: {SOURCE_DIR}")
        return False

    # Check destination directory
    if not os.path.exists(DEST_DIR):
        try:
            os.makedirs(DEST_DIR, exist_ok=True)
            print_step(f"Created destination directory: {DEST_DIR}")
        except Exception as e:
            print_error(f"Failed to create destination directory: {e}")
            return False

    if not os.path.isdir(DEST_DIR):
        print_error(f"Destination path is not a directory: {DEST_DIR}")
        return False

    return True


def deploy_files() -> Tuple[int, int, int]:
    """
    Deploy files from source to destination directory.

    Returns:
        Tuple containing (new_files, updated_files, same_files)
    """
    new_files = 0
    updated_files = 0
    same_files = 0

    source_files = list_files(SOURCE_DIR)
    dest_files = list_files(DEST_DIR)

    # Track files to process
    files_to_process = []
    for file in source_files:
        source_path = os.path.join(SOURCE_DIR, file)
        dest_path = os.path.join(DEST_DIR, file)

        # Determine if file needs to be copied
        if file not in dest_files:
            # New file
            files_to_process.append((source_path, dest_path, "new"))
        else:
            # Existing file - check if content has changed
            try:
                source_hash = get_file_hash(source_path)
                dest_hash = get_file_hash(dest_path)

                if source_hash != dest_hash:
                    files_to_process.append((source_path, dest_path, "update"))
                else:
                    files_to_process.append((source_path, dest_path, "same"))
            except Exception as e:
                print_warning(f"Error comparing file {file}: {e}")
                files_to_process.append((source_path, dest_path, "update"))

    # Process files with progress bar
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Processing files"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Deploying", total=len(files_to_process))

        for source_path, dest_path, status in files_to_process:
            filename = os.path.basename(source_path)

            if status == "new":
                try:
                    shutil.copy2(source_path, dest_path)
                    new_files += 1
                except Exception as e:
                    print_warning(f"Failed to copy new file {filename}: {e}")
            elif status == "update":
                try:
                    shutil.copy2(source_path, dest_path)
                    updated_files += 1
                except Exception as e:
                    print_warning(f"Failed to update file {filename}: {e}")
            else:  # status == "same"
                same_files += 1

            progress.advance(task)

    return new_files, updated_files, same_files


# ----------------------------------------------------------------
# Main Functions
# ----------------------------------------------------------------
def display_deployment_details() -> None:
    """Display the deployment details in a panel."""
    panel_content = f"""

Source: {SOURCE_DIR}
Target: {DEST_DIR}
Owner: {os.path.basename(os.path.expanduser("~"))}

"""

    console.print(
        Panel(
            Text.from_markup(panel_content),
            title=f"[bold {NordColors.FROST_2}]Deployment Details[/]",
            border_style=NordColors.FROST_3,
            padding=(2, 3),
            expand=True,
        )
    )


def create_status_table(steps: List[Tuple[str, str, str]]) -> Table:
    """
    Create a table displaying the status of deployment steps.

    Args:
        steps: List of (step_name, status, details) tuples

    Returns:
        Rich Table object
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        expand=True,
        title=f"[bold {NordColors.SNOW_STORM_2}]Deployment Steps[/]",
        title_justify="center",
    )

    table.add_column("Step", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", justify="center")
    table.add_column("Details", style=NordColors.SNOW_STORM_1)

    for step, status, details in steps:
        if status == "SUCCESS":
            status_text = Text("✓ SUCCESS", style=f"bold {NordColors.GREEN}")
        elif status == "FAILED":
            status_text = Text("✗ FAILED", style=f"bold {NordColors.RED}")
        elif status == "PENDING":
            status_text = Text("○ PENDING", style=f"dim {NordColors.POLAR_NIGHT_4}")
        elif status == "SKIPPED":
            status_text = Text("⊘ SKIPPED", style=f"dim {NordColors.YELLOW}")
        else:
            status_text = Text(status, style=NordColors.SNOW_STORM_1)

        table.add_row(step, status_text, details)

    return table


def create_stats_table(
    new_files: int, updated_files: int, same_files: int, elapsed_time: float
) -> Table:
    """
    Create a table displaying deployment statistics.

    Args:
        new_files: Number of new files copied
        updated_files: Number of files updated
        same_files: Number of files unchanged
        elapsed_time: Time taken for deployment

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

    table.add_row("New Files", str(new_files))
    table.add_row("Updated Files", str(updated_files))
    table.add_row("Unchanged Files", str(same_files))
    table.add_row("Total Files", str(new_files + updated_files + same_files))
    table.add_row("Elapsed Time", f"{elapsed_time:.2f} seconds")

    return table


def run_deployment() -> None:
    """Run the complete deployment process."""
    console.print(create_header())

    # Display deployment details
    display_deployment_details()

    # Initialize steps
    steps = [
        ("Path Verification", "PENDING", ""),
        ("File Deployment", "PENDING", ""),
    ]

    # Step 1: Verify paths
    if verify_paths():
        steps[0] = (
            "Path Verification",
            "SUCCESS",
            "Source and destination directories verified",
        )
    else:
        steps[0] = (
            "Path Verification",
            "FAILED",
            f"Source directory does not exist: {SOURCE_DIR}",
        )
        console.print(create_status_table(steps))
        display_panel(
            "Deployment failed due to path verification errors.",
            style=NordColors.RED,
            title="Error",
        )
        return

    # Step 2: Deploy files
    start_time = time.time()
    try:
        new_files, updated_files, same_files = deploy_files()
        elapsed_time = time.time() - start_time

        steps[1] = (
            "File Deployment",
            "SUCCESS",
            f"Copied {new_files} new files, updated {updated_files} files",
        )

        # Display results
        console.print(create_status_table(steps))
        console.print(
            create_stats_table(new_files, updated_files, same_files, elapsed_time)
        )

        # Final message
        if new_files > 0 or updated_files > 0:
            display_panel(
                f"Successfully deployed {new_files + updated_files} files from source to destination.",
                style=NordColors.GREEN,
                title="Success",
            )
        else:
            display_panel(
                "No files needed updating. All files are already up to date.",
                style=NordColors.FROST_3,
                title="Information",
            )

    except Exception as e:
        elapsed_time = time.time() - start_time
        steps[1] = ("File Deployment", "FAILED", str(e))

        # Display results
        console.print(create_status_table(steps))

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
