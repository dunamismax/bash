#!/usr/bin/env python3
"""
Interactive Script Deployment System

This utility deploys scripts from a source directory to a target directory
with comprehensive verification, dry run analysis, and permission enforcement.
It uses Rich for progress and status output and pyfiglet for a striking
ASCII art header. Designed for Ubuntu/Linux systems with a fully interactive
menu-driven interface.

Note: Run this script with root privileges.
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
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Prompt, Confirm
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
DEFAULT_SCRIPT_SOURCE: str = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
DEFAULT_SCRIPT_TARGET: str = "/home/sawyer/bin"
DEFAULT_EXPECTED_OWNER: str = "sawyer"
DEFAULT_LOG_FILE: str = "/var/log/deploy-scripts.log"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Nord palette examples: nord0: #2E3440, nord4: #D8DEE9, nord8: #88C0D0, nord10: #5E81AC, nord11: #BF616A
console = Console()


def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
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


# ------------------------------
# Command Execution Helper
# ------------------------------
def run_command(
    cmd: list[str], check: bool = True, timeout: int = 30
) -> subprocess.CompletedProcess:
    """
    Run a system command with error handling.

    Args:
        cmd (list[str]): Command to execute.
        check (bool): Raise exception on non-zero exit if True.
        timeout (int): Timeout in seconds.

    Returns:
        subprocess.CompletedProcess: The process result.
    """
    try:
        print_step(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, check=check, capture_output=True, text=True, timeout=timeout
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Error: {e.stderr.strip()}[/bold #BF616A]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_step("Performing cleanup tasks...")
    # Additional cleanup tasks could be added here if needed


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


# ------------------------------
# Deployment Status Tracking
# ------------------------------
class DeploymentStatus:
    """
    Tracks deployment steps and statistics.
    """

    def __init__(self) -> None:
        self.steps: Dict[str, Dict[str, str]] = {
            "ownership_check": {"status": "pending", "message": ""},
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
        """Update the status of a deployment step."""
        if step in self.steps:
            self.steps[step] = {"status": status, "message": message}

    def update_stats(self, **kwargs: Any) -> None:
        """Update deployment statistics."""
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value

    def reset(self) -> None:
        """Reset all status and statistics."""
        for step in self.steps:
            self.steps[step] = {"status": "pending", "message": ""}
        self.stats = {
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "start_time": None,
            "end_time": None,
        }


# ------------------------------
# Deployment Manager
# ------------------------------
class DeploymentManager:
    """
    Manages the deployment process.
    """

    def __init__(self) -> None:
        self.script_source: str = DEFAULT_SCRIPT_SOURCE
        self.script_target: str = DEFAULT_SCRIPT_TARGET
        self.expected_owner: str = DEFAULT_EXPECTED_OWNER
        self.log_file: str = DEFAULT_LOG_FILE
        self.status: DeploymentStatus = DeploymentStatus()

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        """Handle interrupt signals during deployment."""
        sig_name = f"signal {signum}"
        print_warning(f"Deployment interrupted by {sig_name}")
        self.print_status_report()
        sys.exit(130)

    def check_root(self) -> bool:
        """Ensure the script is run as root."""
        if os.geteuid() != 0:
            print_error("This script must be run as root.")
            return False
        print_success("Root privileges verified.")
        return True

    def check_dependencies(self) -> bool:
        """Verify required system commands are available."""
        required = ["rsync", "find"]
        missing = [cmd for cmd in required if not shutil.which(cmd)]
        if missing:
            print_error(f"Missing required commands: {', '.join(missing)}")
            return False
        print_success("All required dependencies are available.")
        return True

    def check_ownership(self) -> bool:
        """
        Verify that the source directory is owned by the expected owner.
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

    def perform_dry_run(self) -> bool:
        """
        Execute a dry run using rsync to report changes.
        """
        self.status.update_step("dry_run", "in_progress", "Performing dry run...")
        try:
            with Progress(
                SpinnerColumn(style="bold #81A1C1"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="bold #88C0D0"),
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
        Deploy the scripts using rsync with checksum verification to update modified files.
        """
        self.status.update_step("deployment", "in_progress", "Deploying scripts...")
        try:
            with Progress(
                SpinnerColumn(style="bold #81A1C1"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="bold #88C0D0"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Deploying scripts...", total=1)
                result = run_command(
                    [
                        "rsync",
                        "-avc",  # Added the checksum flag to detect modifications
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
        Set executable permissions on deployed files.
        """
        self.status.update_step(
            "permission_set", "in_progress", "Setting permissions..."
        )
        try:
            with Progress(
                SpinnerColumn(style="bold #81A1C1"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="bold #88C0D0"),
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

    def print_status_report(self) -> None:
        """Print a detailed deployment status report."""
        print_section("--- Deployment Status Report ---")
        icons: Dict[str, str] = {
            "success": "✓",
            "failed": "✗",
            "pending": "?",
            "in_progress": "⋯",
        }
        for step, data in self.status.steps.items():
            icon = icons.get(data["status"], "?")
            status_color = {
                "success": "#8FBCBB",
                "failed": "#BF616A",
                "pending": "#D8DEE9",
                "in_progress": "#81A1C1",
            }.get(data["status"], "#D8DEE9")

            console.print(
                f"[{status_color}]{icon}[/{status_color}] {step}: [bold {status_color}]{data['status'].upper()}[/bold {status_color}] - {data['message']}"
            )

        if self.status.stats["start_time"]:
            elapsed = (
                self.status.stats["end_time"] or time.time()
            ) - self.status.stats["start_time"]
            console.print("\n[bold #88C0D0]Deployment Statistics:[/bold #88C0D0]")
            console.print(
                f"  [#88C0D0]•[/#88C0D0] New Files: {self.status.stats['new_files']}"
            )
            console.print(
                f"  [#88C0D0]•[/#88C0D0] Updated Files: {self.status.stats['updated_files']}"
            )
            console.print(
                f"  [#88C0D0]•[/#88C0D0] Deleted Files: {self.status.stats['deleted_files']}"
            )
            console.print(f"  [#88C0D0]•[/#88C0D0] Total Time: {elapsed:.2f} seconds")

    def configure_deployment(self) -> None:
        """Configure deployment parameters interactively."""
        print_section("Configure Deployment Parameters")

        print_step("Current configuration:")
        console.print(f"  [#D8DEE9]•[/#D8DEE9] Source directory: {self.script_source}")
        console.print(f"  [#D8DEE9]•[/#D8DEE9] Target directory: {self.script_target}")
        console.print(
            f"  [#D8DEE9]•[/#D8DEE9] Expected source owner: {self.expected_owner}"
        )
        console.print(f"  [#D8DEE9]•[/#D8DEE9] Log file: {self.log_file}")

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

            print_success("Deployment parameters updated.")

            # Show the updated configuration
            print_step("Updated configuration:")
            console.print(
                f"  [#D8DEE9]•[/#D8DEE9] Source directory: {self.script_source}"
            )
            console.print(
                f"  [#D8DEE9]•[/#D8DEE9] Target directory: {self.script_target}"
            )
            console.print(
                f"  [#D8DEE9]•[/#D8DEE9] Expected source owner: {self.expected_owner}"
            )
            console.print(f"  [#D8DEE9]•[/#D8DEE9] Log file: {self.log_file}")
        else:
            print_step("Configuration unchanged.")

    def deploy(self) -> bool:
        """
        Execute the full deployment process.
        """
        # Setup signal handlers for graceful interruption.
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

        # Reset status tracking
        self.status.reset()
        self.status.stats["start_time"] = time.time()

        print_header("Script Deployment")

        # Create target directory if it doesn't exist
        try:
            os.makedirs(self.script_target, exist_ok=True)
        except Exception as e:
            print_error(f"Failed to create target directory: {e}")
            return False

        # Run deployment steps
        if not self.check_ownership():
            return False
        if not self.perform_dry_run():
            return False

        # Confirm before actual deployment
        if not Confirm.ask("\nProceed with deployment?", default=True):
            print_warning("Deployment cancelled by user.")
            return False

        if not self.execute_deployment():
            return False
        success = self.set_permissions()
        self.status.stats["end_time"] = time.time()
        return success

    def verify_paths(self) -> bool:
        """Verify that source and target paths are valid."""
        print_section("Verifying Paths")

        # Check source path
        source_path = Path(self.script_source)
        if not source_path.exists():
            print_error(f"Source directory does not exist: {self.script_source}")
            return False
        if not source_path.is_dir():
            print_error(f"Source path is not a directory: {self.script_source}")
            return False
        print_success(f"Source directory exists: {self.script_source}")

        # Check if we can create the target path if it doesn't exist
        target_path = Path(self.script_target)
        if not target_path.exists():
            print_step(f"Target directory does not exist: {self.script_target}")
            try:
                if Confirm.ask("Create target directory?", default=True):
                    target_path.mkdir(parents=True, exist_ok=True)
                    print_success(f"Created target directory: {self.script_target}")
                else:
                    print_warning("Target directory creation skipped.")
                    return False
            except Exception as e:
                print_error(f"Failed to create target directory: {e}")
                return False
        elif not target_path.is_dir():
            print_error(f"Target path is not a directory: {self.script_target}")
            return False
        else:
            print_success(f"Target directory exists: {self.script_target}")

        return True


# ------------------------------
# Interactive Menu
# ------------------------------
def interactive_menu() -> None:
    """Display and process the interactive menu."""
    manager = DeploymentManager()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    # Verify root privileges at startup
    if not manager.check_root():
        print_error("This script must be run as root (e.g., using sudo)")
        sys.exit(1)

    # Check dependencies at startup
    if not manager.check_dependencies():
        print_error("Missing required dependencies. Please install them and try again.")
        sys.exit(1)

    while True:
        print_header("Script Deployment System")
        console.print(
            f"Current Time: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
        )

        # Display menu options
        print_section("Main Menu")
        console.print("1. Configure Deployment Parameters")
        console.print("2. Verify Paths and Ownership")
        console.print("3. Run Dry Deployment (Analysis Only)")
        console.print("4. Full Deployment")
        console.print("5. View Deployment Status")
        console.print("6. Exit")

        # Get user choice
        choice = Prompt.ask(
            "Select an option", choices=["1", "2", "3", "4", "5", "6"], default="1"
        )

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
                print_success("Deployment completed successfully.")
            else:
                print_error("Deployment encountered errors.")
            manager.print_status_report()
        elif choice == "5":
            manager.print_status_report()
        elif choice == "6":
            print_header("Exiting")
            print_success("Thank you for using the Script Deployment System!")
            break

        if choice != "6":
            input("\nPress Enter to return to the menu...")


# ------------------------------
# Main Entry Point
# ------------------------------
def main() -> None:
    """Main entry point for the script."""
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print_warning("\nScript interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
