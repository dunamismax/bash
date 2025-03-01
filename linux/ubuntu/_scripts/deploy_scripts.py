#!/usr/bin/env python3
"""
Script Deployment System

This utility deploys scripts from a source directory to a target directory
with comprehensive verification, dry run analysis, and permission enforcement.
It uses Rich for progress and status output, Click for argument parsing, and
pyfiglet for a striking ASCII art header. Designed for Ubuntu/Linux systems.

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
from typing import Any, Dict

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
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    print_step("Performing cleanup tasks...")


atexit.register(cleanup)


def signal_handler(sig, frame) -> None:
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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
        if e.stderr:
            console.print(f"[bold #BF616A]Error: {e.stderr.strip()}[/bold #BF616A]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out: {' '.join(cmd)}")
        raise


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
        if step in self.steps:
            self.steps[step] = {"status": status, "message": message}

    def update_stats(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value


# ------------------------------
# Deployment Manager
# ------------------------------
class DeploymentManager:
    """
    Manages the deployment process.
    """

    def __init__(self, source: str, target: str, expected_owner: str) -> None:
        self.script_source: str = source
        self.script_target: str = target
        self.expected_owner: str = expected_owner
        self.status: DeploymentStatus = DeploymentStatus()

        # Register signal handlers for graceful interruption.
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        sig_name = f"signal {signum}"
        print_warning(f"Deployment interrupted by {sig_name}")
        self.print_status_report()
        sys.exit(130)

    def check_root(self) -> None:
        """Ensure the script is run as root."""
        if os.geteuid() != 0:
            print_error("This script must be run as root.")
            sys.exit(1)
        print_success("Root privileges verified.")

    def check_dependencies(self) -> None:
        """Verify required system commands are available."""
        required = ["rsync", "find"]
        missing = [cmd for cmd in required if not shutil.which(cmd)]
        if missing:
            print_error(f"Missing required commands: {', '.join(missing)}")
            sys.exit(1)
        print_success("All required dependencies are available.")

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
        Deploy the scripts using rsync.
        """
        self.status.update_step("deployment", "in_progress", "Deploying scripts...")
        try:
            result = run_command(
                [
                    "rsync",
                    "-av",
                    "--delete",
                    "--itemize-changes",
                    f"{self.script_source.rstrip('/')}/",
                    self.script_target,
                ]
            )
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
            console.print(
                f"{icon} {step}: [bold]{data['status'].upper()}[/bold] - {data['message']}"
            )
        if self.status.stats["start_time"]:
            elapsed = time.time() - self.status.stats["start_time"]
            console.print("\n[bold]Deployment Statistics:[/bold]")
            console.print(f"  • New Files: {self.status.stats['new_files']}")
            console.print(f"  • Updated Files: {self.status.stats['updated_files']}")
            console.print(f"  • Deleted Files: {self.status.stats['deleted_files']}")
            console.print(f"  • Total Time: {elapsed:.2f} seconds")

    def deploy(self) -> bool:
        """
        Execute the full deployment process.
        """
        print_header("Script Deployment")
        self.status.stats["start_time"] = time.time()
        os.makedirs(self.script_target, exist_ok=True)

        if not self.check_ownership():
            return False
        if not self.perform_dry_run():
            return False
        if not self.execute_deployment():
            return False
        success = self.set_permissions()
        self.status.stats["end_time"] = time.time()
        return success


# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.option(
    "--source",
    type=click.Path(exists=True),
    default=DEFAULT_SCRIPT_SOURCE,
    help="Directory containing the source scripts.",
)
@click.option(
    "--target",
    type=click.Path(),
    default=DEFAULT_SCRIPT_TARGET,
    help="Directory to deploy the scripts to.",
)
@click.option(
    "--owner",
    default=DEFAULT_EXPECTED_OWNER,
    help="Expected owner of the source directory.",
)
@click.option(
    "--log-file",
    type=click.Path(),
    default=DEFAULT_LOG_FILE,
    help="Path to the log file.",
)
def main(source: str, target: str, owner: str, log_file: str) -> None:
    """
    Deploy scripts from a source directory to a target directory with verification,
    dry run analysis, and permission enforcement.
    """
    print_header("Script Deployment System")
    # (Optional) Setup file logging here if required.
    manager = DeploymentManager(source=source, target=target, expected_owner=owner)
    manager.check_root()
    manager.check_dependencies()
    if not manager.deploy():
        manager.print_status_report()
        print_error("Deployment encountered errors. Exiting.")
        sys.exit(1)
    manager.print_status_report()
    print_success("Deployment completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        sys.exit(1)
