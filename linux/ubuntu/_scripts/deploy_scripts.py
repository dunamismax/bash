#!/usr/bin/env python3
"""
Interactive Script Deployment System
--------------------------------------------------

A robust utility for deploying scripts from a source directory to a target directory
with comprehensive verification, dry-run analysis, and permission enforcement.
Features Nord-themed styling, real-time progress tracking, and a fully interactive
menu-driven interface.

Usage:
  Run the script with root privileges to access the interactive menu.
  - Option 1: Configure deployment parameters
  - Option 2: Verify paths and ownership
  - Option 3: Run a dry deployment (analysis only)
  - Option 4: Execute a full deployment
  - Option 5: View deployment status
  - Option 6: Exit the application

Version: 1.0.0
"""

import atexit
import os
import pwd
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.columns import Columns
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
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
# Configuration and Constants
# ----------------------------------------------------------------
VERSION: str = "1.0.0"
APP_NAME: str = "Script Deployment System"
APP_SUBTITLE: str = "Secure Script Deployment Manager"
OPERATION_TIMEOUT: int = 30  # seconds


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


# Create a Rich Console
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
    compact_fonts = ["slant", "small", "smslant", "digital", "times"]

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
        NordColors.FROST_2,
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
    Display a success message.

    Args:
        text: The message to display
    """
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """
    Display a warning message.

    Args:
        text: The message to display
    """
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """
    Display an error message.

    Args:
        text: The message to display
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
        print_message(f"Executing: {' '.join(cmd)}")
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
    print_message("Cleaning up resources...", NordColors.FROST_3)
    # Add any necessary cleanup logic here


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
# Deployment Status Tracking
# ----------------------------------------------------------------
class DeploymentStatus:
    """
    Tracks deployment steps and statistics.

    Attributes:
        steps: Dictionary of steps and their statuses
        stats: Dictionary of deployment statistics
    """

    def __init__(self) -> None:
        self.steps: Dict[str, Dict[str, str]] = {
            "ownership_check": {"status": "pending", "message": ""},
            "path_verification": {"status": "pending", "message": ""},
            "dry_run": {"status": "pending", "message": ""},
            "deployment": {"status": "pending", "message": ""},
            "permission_set": {"status": "pending", "message": ""},
        }
        self.stats: Dict[str, Any] = {
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "start_time": None,
            "end_time": None,
        }

    def update_step(self, step: str, status: str, message: str) -> None:
        """
        Update the status of a deployment step.

        Args:
            step: The step name
            status: The new status (pending, in_progress, success, failed)
            message: A descriptive message
        """
        if step in self.steps:
            self.steps[step] = {"status": status, "message": message}

    def update_stats(self, **kwargs: Any) -> None:
        """
        Update deployment statistics.

        Args:
            **kwargs: Key-value pairs of stats to update
        """
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value

    def reset(self) -> None:
        """Reset all status and statistics to default values."""
        for step in self.steps:
            self.steps[step] = {"status": "pending", "message": ""}
        self.stats = {
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "start_time": None,
            "end_time": None,
        }


# ----------------------------------------------------------------
# Deployment Manager
# ----------------------------------------------------------------
class DeploymentManager:
    """
    Manages the deployment process for scripts.

    This class handles all aspects of script deployment including
    configuration, verification, execution, and reporting.
    """

    def __init__(self) -> None:
        self.script_source: str = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
        self.script_target: str = "/home/sawyer/bin"
        self.expected_owner: str = "sawyer"
        self.log_file: str = "/var/log/deploy-scripts.log"
        self.status: DeploymentStatus = DeploymentStatus()

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        """
        Handle interruption during deployment.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        print_warning(f"Deployment interrupted (signal {signum}).")
        self.print_status_report()
        sys.exit(130)

    def check_root(self) -> bool:
        """
        Check if the script is running with root privileges.

        Returns:
            True if running as root, False otherwise
        """
        if os.geteuid() != 0:
            print_error("This script must be run as root.")
            return False
        print_success("Root privileges verified.")
        return True

    def check_dependencies(self) -> bool:
        """
        Check if all required external commands are available.

        Returns:
            True if all dependencies are available, False otherwise
        """
        required = ["rsync", "find"]
        missing = [cmd for cmd in required if not shutil.which(cmd)]
        if missing:
            print_error(f"Missing required commands: {', '.join(missing)}")
            return False
        print_success("All required dependencies are available.")
        return True

    def check_ownership(self) -> bool:
        """
        Check if the source directory has the expected owner.

        Returns:
            True if ownership is correct, False otherwise
        """
        self.status.update_step(
            "ownership_check", "in_progress", "Checking ownership..."
        )
        try:
            stat_info = os.stat(self.script_source)
            owner = pwd.getpwuid(stat_info.st_uid).pw_name
            if owner != self.expected_owner:
                msg = f"Source owned by '{owner}', expected '{self.expected_owner}'."
                self.status.update_step("ownership_check", "failed", msg)
                print_error(msg)
                return False
            msg = f"Source ownership verified as '{owner}'."
            self.status.update_step("ownership_check", "success", msg)
            print_success(msg)
            return True
        except Exception as e:
            msg = f"Error checking ownership: {e}"
            self.status.update_step("ownership_check", "failed", msg)
            print_error(msg)
            return False

    def verify_paths(self) -> bool:
        """
        Verify that source and target paths exist and are valid.

        Returns:
            True if paths are valid, False otherwise
        """
        self.status.update_step(
            "path_verification", "in_progress", "Verifying paths..."
        )

        # Check source path
        source_path = Path(self.script_source)
        if not source_path.exists():
            msg = f"Source directory does not exist: {self.script_source}"
            self.status.update_step("path_verification", "failed", msg)
            print_error(msg)
            return False
        if not source_path.is_dir():
            msg = f"Source path is not a directory: {self.script_source}"
            self.status.update_step("path_verification", "failed", msg)
            print_error(msg)
            return False
        print_success(f"Source directory exists: {self.script_source}")

        # Check target path
        target_path = Path(self.script_target)
        if not target_path.exists():
            print_message(
                f"Target directory does not exist: {self.script_target}",
                NordColors.YELLOW,
            )
            try:
                if Confirm.ask("Create target directory?", default=True):
                    target_path.mkdir(parents=True, exist_ok=True)
                    print_success(f"Created target directory: {self.script_target}")
                else:
                    msg = "Target directory creation skipped."
                    self.status.update_step("path_verification", "failed", msg)
                    print_warning(msg)
                    return False
            except Exception as e:
                msg = f"Failed to create target directory: {e}"
                self.status.update_step("path_verification", "failed", msg)
                print_error(msg)
                return False
        elif not target_path.is_dir():
            msg = f"Target path is not a directory: {self.script_target}"
            self.status.update_step("path_verification", "failed", msg)
            print_error(msg)
            return False
        else:
            print_success(f"Target directory exists: {self.script_target}")

        msg = "All paths verified successfully."
        self.status.update_step("path_verification", "success", msg)
        return True

    def perform_dry_run(self) -> bool:
        """
        Perform a dry run of the deployment to analyze changes.

        Returns:
            True if dry run succeeds, False otherwise
        """
        self.status.update_step("dry_run", "in_progress", "Performing dry run...")
        try:
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(
                    bar_width=None,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Running dry deployment...", total=1)
                result = run_command(
                    [
                        "rsync",
                        "--dry-run",
                        "-av",
                        "--delete",
                        "--itemize-changes",
                        f"{self.script_source.rstrip('/')}/",
                        self.script_target,
                    ]
                )
                progress.update(task, advance=1)

            changes = [
                line
                for line in result.stdout.splitlines()
                if line and not line.startswith(">")
            ]
            new_files = sum(1 for line in changes if line.startswith(">f+"))
            updated_files = sum(1 for line in changes if line.startswith(">f."))
            deleted_files = sum(1 for line in changes if line.startswith("*deleting"))
            self.status.update_stats(
                new_files=new_files,
                updated_files=updated_files,
                deleted_files=deleted_files,
            )
            msg = f"Dry run: {new_files} new, {updated_files} updated, {deleted_files} deletions."
            self.status.update_step("dry_run", "success", msg)
            print_success(msg)
            return True
        except Exception as e:
            msg = f"Dry run failed: {e}"
            self.status.update_step("dry_run", "failed", msg)
            print_error(msg)
            return False

    def execute_deployment(self) -> bool:
        """
        Execute the actual deployment of scripts.

        Returns:
            True if deployment succeeds, False otherwise
        """
        self.status.update_step("deployment", "in_progress", "Deploying scripts...")
        try:
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(
                    bar_width=None,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Deploying scripts...", total=1)
                result = run_command(
                    [
                        "rsync",
                        "-avc",  # checksum flag to detect modifications
                        "--delete",
                        "--itemize-changes",
                        f"{self.script_source.rstrip('/')}/",
                        self.script_target,
                    ]
                )
                progress.update(task, advance=1)

            changes = [
                line
                for line in result.stdout.splitlines()
                if line and not line.startswith(">")
            ]
            new_files = sum(1 for line in changes if line.startswith(">f+"))
            updated_files = sum(1 for line in changes if line.startswith(">f."))
            deleted_files = sum(1 for line in changes if line.startswith("*deleting"))
            self.status.update_stats(
                new_files=new_files,
                updated_files=updated_files,
                deleted_files=deleted_files,
            )
            msg = f"Deployment: {new_files} new, {updated_files} updated, {deleted_files} deleted."
            self.status.update_step("deployment", "success", msg)
            print_success(msg)
            return True
        except Exception as e:
            msg = f"Deployment failed: {e}"
            self.status.update_step("deployment", "failed", msg)
            print_error(msg)
            return False

    def set_permissions(self) -> bool:
        """
        Set appropriate permissions on deployed scripts.

        Returns:
            True if permissions are set successfully, False otherwise
        """
        self.status.update_step(
            "permission_set", "in_progress", "Setting permissions..."
        )
        try:
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(
                    bar_width=None,
                    style=NordColors.FROST_4,
                    complete_style=NordColors.FROST_2,
                ),
                console=console,
            ) as progress:
                task = progress.add_task("Setting file permissions...", total=1)
                run_command(
                    [
                        "find",
                        self.script_target,
                        "-type",
                        "f",
                        "-exec",
                        "chmod",
                        "755",
                        "{}",
                        ";",
                    ]
                )
                progress.update(task, advance=1)
            msg = "Permissions set successfully."
            self.status.update_step("permission_set", "success", msg)
            print_success(msg)
            return True
        except Exception as e:
            msg = f"Failed to set permissions: {e}"
            self.status.update_step("permission_set", "failed", msg)
            print_error(msg)
            return False

    def configure_deployment(self) -> None:
        """Configure deployment parameters through interactive prompts."""
        console.print(
            Panel(
                Text(
                    "Configure the parameters for script deployment",
                    style=f"bold {NordColors.FROST_2}",
                ),
                title="Configuration",
                border_style=Style(color=NordColors.FROST_1),
                padding=(1, 2),
            )
        )

        # Create a table to display current configuration
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            expand=True,
            title=f"[bold {NordColors.FROST_2}]Current Configuration[/]",
            border_style=NordColors.FROST_3,
            box=None,
        )

        table.add_column("Parameter", style=f"bold {NordColors.FROST_4}")
        table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

        table.add_row("Source Directory", self.script_source)
        table.add_row("Target Directory", self.script_target)
        table.add_row("Expected Owner", self.expected_owner)
        table.add_row("Log File", self.log_file)

        console.print(table)

        if Confirm.ask("\nWould you like to change these settings?", default=False):
            self.script_source = Prompt.ask(
                "Enter source directory path", default=self.script_source
            )
            self.script_target = Prompt.ask(
                "Enter target directory path", default=self.script_target
            )
            self.expected_owner = Prompt.ask(
                "Enter expected source owner", default=self.expected_owner
            )
            self.log_file = Prompt.ask("Enter log file path", default=self.log_file)

            # Create updated configuration table
            updated_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=True,
                title=f"[bold {NordColors.FROST_2}]Updated Configuration[/]",
                border_style=NordColors.FROST_3,
                box=None,
            )

            updated_table.add_column("Parameter", style=f"bold {NordColors.FROST_4}")
            updated_table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

            updated_table.add_row("Source Directory", self.script_source)
            updated_table.add_row("Target Directory", self.script_target)
            updated_table.add_row("Expected Owner", self.expected_owner)
            updated_table.add_row("Log File", self.log_file)

            console.print(updated_table)
            print_success("Deployment parameters updated.")
        else:
            print_message("Configuration unchanged.", NordColors.FROST_3)

    def deploy(self) -> bool:
        """
        Execute the full deployment process.

        Returns:
            True if deployment succeeds, False otherwise
        """
        # Setup interrupt signal handling for deployment
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

        self.status.reset()
        self.status.stats["start_time"] = time.time()

        console.clear()
        console.print(create_header())

        # Display a deployment panel
        deployment_panel = Panel(
            Text.from_markup(
                f"\n[bold {NordColors.FROST_2}]Source:[/] [{NordColors.SNOW_STORM_2}]{self.script_source}[/]\n"
                f"[bold {NordColors.FROST_2}]Target:[/] [{NordColors.SNOW_STORM_2}]{self.script_target}[/]\n"
                f"[bold {NordColors.FROST_2}]Owner:[/] [{NordColors.SNOW_STORM_2}]{self.expected_owner}[/]\n"
            ),
            title=f"[bold {NordColors.FROST_3}]Deployment Details[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
        console.print(deployment_panel)

        try:
            os.makedirs(self.script_target, exist_ok=True)
        except Exception as e:
            print_error(f"Failed to create target directory: {e}")
            return False

        # Perform verification steps
        if not self.verify_paths():
            return False

        if not self.check_ownership():
            return False

        if not self.perform_dry_run():
            return False

        if not Confirm.ask("\nProceed with deployment?", default=True):
            print_warning("Deployment cancelled by user.")
            return False

        if not self.execute_deployment():
            return False

        success = self.set_permissions()
        self.status.stats["end_time"] = time.time()
        return success

    def print_status_report(self) -> None:
        """Display a detailed report of the deployment status."""
        status_panel = Panel(
            Text(
                "Current deployment status and statistics",
                style=f"bold {NordColors.FROST_2}",
            ),
            title="Status Report",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
        console.print(status_panel)

        # Create a table for step statuses
        status_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            expand=True,
            title=f"[bold {NordColors.FROST_2}]Deployment Steps[/]",
            border_style=NordColors.FROST_3,
            box=None,
        )

        status_table.add_column("Step", style=f"bold {NordColors.FROST_4}")
        status_table.add_column("Status", justify="center")
        status_table.add_column("Details", style=f"{NordColors.SNOW_STORM_1}")

        # Status icons and colors
        icons = {"success": "✓", "failed": "✗", "pending": "?", "in_progress": "⋯"}
        colors = {
            "success": NordColors.GREEN,
            "failed": NordColors.RED,
            "pending": NordColors.SNOW_STORM_1,
            "in_progress": NordColors.FROST_3,
        }

        # Add rows for each step
        for step_name, step_data in self.status.steps.items():
            status = step_data["status"]
            icon = icons.get(status, "?")
            color = colors.get(status, NordColors.SNOW_STORM_1)
            status_text = Text(f"{icon} {status.upper()}", style=f"bold {color}")

            # Format step name for display (convert snake_case to Title Case)
            display_name = " ".join(word.capitalize() for word in step_name.split("_"))

            status_table.add_row(display_name, status_text, step_data["message"])

        console.print(status_table)

        # Only show statistics if a deployment has been started
        if self.status.stats["start_time"]:
            elapsed = (
                self.status.stats["end_time"] or time.time()
            ) - self.status.stats["start_time"]

            # Create a table for statistics
            stats_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=True,
                title=f"[bold {NordColors.FROST_2}]Deployment Statistics[/]",
                border_style=NordColors.FROST_3,
                box=None,
            )

            stats_table.add_column("Metric", style=f"bold {NordColors.FROST_4}")
            stats_table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

            stats_table.add_row("New Files", str(self.status.stats["new_files"]))
            stats_table.add_row(
                "Updated Files", str(self.status.stats["updated_files"])
            )
            stats_table.add_row(
                "Deleted Files", str(self.status.stats["deleted_files"])
            )
            stats_table.add_row(
                "Total Files",
                str(
                    self.status.stats["new_files"] + self.status.stats["updated_files"]
                ),
            )
            stats_table.add_row("Elapsed Time", f"{elapsed:.2f} seconds")

            console.print(stats_table)


# ----------------------------------------------------------------
# Interactive Menu
# ----------------------------------------------------------------
def display_menu() -> str:
    """
    Display the main menu and return the user's choice.

    Returns:
        The user's menu selection
    """
    menu_panel = Panel(
        Text.from_markup(
            "\n"
            f"[bold {NordColors.FROST_1}]1.[/] [bold {NordColors.FROST_2}]Configure Deployment Parameters[/]\n"
            f"[bold {NordColors.FROST_1}]2.[/] [bold {NordColors.FROST_2}]Verify Paths and Ownership[/]\n"
            f"[bold {NordColors.FROST_1}]3.[/] [bold {NordColors.FROST_2}]Run Dry Deployment (Analysis Only)[/]\n"
            f"[bold {NordColors.FROST_1}]4.[/] [bold {NordColors.FROST_2}]Full Deployment[/]\n"
            f"[bold {NordColors.FROST_1}]5.[/] [bold {NordColors.FROST_2}]View Deployment Status[/]\n"
            f"[bold {NordColors.FROST_1}]6.[/] [bold {NordColors.FROST_2}]Exit[/]\n"
        ),
        title=f"[bold {NordColors.FROST_3}]Main Menu[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(menu_panel)

    return Prompt.ask(
        "Select an option", choices=["1", "2", "3", "4", "5", "6"], default="1"
    )


def interactive_menu() -> None:
    """Display and process the interactive menu."""
    manager = DeploymentManager()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    if not manager.check_root():
        print_error("This script must be run as root (e.g., using sudo).")
        sys.exit(1)

    if not manager.check_dependencies():
        print_error("Missing required dependencies. Please install them and try again.")
        sys.exit(1)

    while True:
        console.clear()
        console.print(create_header())

        # Display current time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
        )
        console.print()

        choice = display_menu()

        if choice == "1":
            manager.configure_deployment()
        elif choice == "2":
            if manager.verify_paths():
                manager.check_ownership()
        elif choice == "3":
            if manager.verify_paths():
                manager.status.reset()
                manager.status.stats["start_time"] = time.time()
                manager.check_ownership()
                manager.perform_dry_run()
                manager.status.stats["end_time"] = time.time()
                manager.print_status_report()
        elif choice == "4":
            if manager.deploy():
                display_panel(
                    "Deployment completed successfully.",
                    style=NordColors.GREEN,
                    title="Success",
                )
            else:
                display_panel(
                    "Deployment encountered errors.",
                    style=NordColors.RED,
                    title="Error",
                )
            manager.print_status_report()
        elif choice == "5":
            manager.print_status_report()
        elif choice == "6":
            console.clear()
            console.print(create_header())
            console.print(
                Panel(
                    Text(
                        "Thank you for using the Script Deployment System!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            break

        if choice != "6":
            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main application function."""
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print_warning("\nScript interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
