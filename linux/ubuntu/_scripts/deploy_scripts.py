#!/usr/bin/env python3
"""
Script Deployment System

Deploys scripts from a source directory to a target directory with comprehensive
verification, dry run analysis, and permission enforcement. Designed for Ubuntu/Linux
systems and built using only the Python standard library.

Usage:
  sudo ./deploy_scripts.py [--source PATH] [--target PATH] [--owner NAME] [--log-file PATH]
"""

import argparse
import datetime
import hashlib
import logging
import os
import pwd
import shutil
import signal
import subprocess
import sys
import time
from logging import Logger
from typing import Any, Dict, Optional, Tuple

#####################################
# Nord Themed ANSI Colors for CLI Output
#####################################


class NordColors:
    """
    Nord themed ANSI color codes.
    Colors chosen approximate the Nord palette.
    """

    HEADER = "\033[38;2;216;222;233m"  # Nord4 (light gray)
    INFO = "\033[38;2;136;192;208m"  # Nord8 (light blue)
    SUCCESS = "\033[38;2;163;190;140m"  # Nord14 (green)
    WARNING = "\033[38;2;235;203;139m"  # Nord13 (yellow)
    ERROR = "\033[38;2;191;97;106m"  # Nord11 (red)
    RESET = "\033[0m"
    BOLD = "\033[1m"


#####################################
# Configuration (Default Values)
#####################################

DEFAULT_SCRIPT_SOURCE: str = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
DEFAULT_SCRIPT_TARGET: str = "/home/sawyer/bin"
DEFAULT_EXPECTED_OWNER: str = "sawyer"
DEFAULT_LOG_FILE: str = "/var/log/deploy-scripts.log"


#####################################
# Custom Logging Formatter with Colors
#####################################


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS: Dict[int, str] = {
        logging.DEBUG: NordColors.INFO,
        logging.INFO: NordColors.INFO,
        logging.WARNING: NordColors.WARNING,
        logging.ERROR: NordColors.ERROR,
        logging.CRITICAL: NordColors.ERROR,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, NordColors.RESET)
        record.msg = f"{color}{record.msg}{NordColors.RESET}"
        return super().format(record)


def setup_logging(log_file: str) -> Logger:
    """
    Set up logging with both console (colored) and file handlers.
    Rotates the log file if it exceeds 10MB and ensures secure file permissions.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter_str = "[%(asctime)s] [%(levelname)s] %(message)s"
    datefmt_str = "%Y-%m-%d %H:%M:%S"

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColorFormatter(fmt=formatter_str, datefmt=datefmt_str)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors)
    try:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

        # Rotate log if over 10MB
        if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{log_file}.{timestamp}"
            shutil.move(log_file, backup_log)

        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(fmt=formatter_str, datefmt=datefmt_str)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Secure file permissions
        os.chmod(log_file, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {e}")

    return logger


#####################################
# Helper Functions
#####################################


def run_command(
    cmd: list, check: bool = True, timeout: int = 30
) -> subprocess.CompletedProcess:
    """
    Run a system command with error handling.

    Args:
        cmd: Command list to execute.
        check: Whether to raise an exception on non-zero exit.
        timeout: Command timeout in seconds.

    Returns:
        subprocess.CompletedProcess: Process result.
    """
    try:
        return subprocess.run(
            cmd, check=check, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd)}")
        logging.error(f"Error: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {' '.join(cmd)}")
        raise


#####################################
# Deployment Status and Tracking Classes
#####################################


class DeploymentStatus:
    """
    Tracks the deployment steps and statistics.
    """

    def __init__(self) -> None:
        self.steps: Dict[str, Dict[str, str]] = {
            "ownership_check": {"status": "pending", "message": ""},
            "dry_run": {"status": "pending", "message": ""},
            "deployment": {"status": "pending", "message": ""},
            "permission_set": {"status": "pending", "message": ""},
        }
        self.stats: Dict[str, Any] = {
            "total_files": 0,
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "unchanged_files": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
        }

    def update_step(self, step: str, status: str, message: str) -> None:
        """Update step status and message."""
        if step in self.steps:
            self.steps[step] = {"status": status, "message": message}

    def update_stats(self, **kwargs: Any) -> None:
        """Update deployment statistics."""
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value


#####################################
# Deployment Manager Class
#####################################


class DeploymentManager:
    """
    Manages the deployment process.
    """

    def __init__(self, source: str, target: str, expected_owner: str) -> None:
        self.script_source: str = source
        self.script_target: str = target
        self.expected_owner: str = expected_owner
        self.status: DeploymentStatus = DeploymentStatus()
        self.logger: Logger = logging.getLogger()

        # Register signal handlers for graceful interruption
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        """Handle interrupt signals gracefully."""
        sig_name = (
            getattr(signal, "Signals", lambda x: x)(signum).name
            if hasattr(signal, "Signals")
            else f"signal {signum}"
        )
        logging.warning(f"Deployment interrupted by {sig_name}")
        self.print_status_report()
        sys.exit(130)

    def check_root(self) -> None:
        """Ensure the script is run with root privileges."""
        if os.geteuid() != 0:
            logging.error("This script must be run as root.")
            sys.exit(1)

    def check_dependencies(self) -> None:
        """Verify required system commands are available."""
        required = ["rsync", "find"]
        missing = [cmd for cmd in required if not shutil.which(cmd)]
        if missing:
            logging.error(f"Missing required commands: {', '.join(missing)}")
            sys.exit(1)

    def check_ownership(self) -> bool:
        """
        Verify the ownership of the source directory.

        Returns:
            bool: True if ownership is as expected, False otherwise.
        """
        self.status.update_step(
            "ownership_check", "in_progress", "Checking directory ownership..."
        )
        try:
            stat_info = os.stat(self.script_source)
            owner = pwd.getpwuid(stat_info.st_uid).pw_name
            if owner != self.expected_owner:
                msg = f"Source owned by '{owner}', expected '{self.expected_owner}'."
                self.status.update_step("ownership_check", "failed", msg)
                return False
            msg = f"Source ownership verified as '{owner}'."
            self.status.update_step("ownership_check", "success", msg)
            return True
        except Exception as e:
            msg = f"Failed to check ownership: {e}"
            self.status.update_step("ownership_check", "failed", msg)
            return False

    def perform_dry_run(self) -> bool:
        """
        Execute a dry run of the deployment to report changes.

        Returns:
            bool: True if dry run succeeded, False otherwise.
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
            logging.info(msg)
            return True
        except Exception as e:
            msg = f"Dry run failed: {e}"
            self.status.update_step("dry_run", "failed", msg)
            logging.error(msg)
            return False

    def execute_deployment(self) -> bool:
        """
        Perform the actual deployment using rsync.

        Returns:
            bool: True if deployment succeeded, False otherwise.
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
            logging.info(msg)
            return True
        except Exception as e:
            msg = f"Deployment failed: {e}"
            self.status.update_step("deployment", "failed", msg)
            logging.error(msg)
            return False

    def set_permissions(self) -> bool:
        """
        Set executable permissions on the deployed files.

        Returns:
            bool: True if permissions were set successfully, False otherwise.
        """
        self.status.update_step(
            "permission_set", "in_progress", "Setting file permissions..."
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
            logging.info(msg)
            return True
        except Exception as e:
            msg = f"Failed to set permissions: {e}"
            self.status.update_step("permission_set", "failed", msg)
            logging.error(msg)
            return False

    def print_status_report(self) -> None:
        """Print a formatted deployment status report."""
        logging.info("\n--- Deployment Status Report ---")
        icons: Dict[str, str] = {
            "success": "✓",
            "failed": "✗",
            "pending": "?",
            "in_progress": "⋯",
        }
        for step, data in self.status.steps.items():
            icon = icons.get(data["status"], "?")
            logging.info(f"{icon} {step}: {data['status'].upper()} - {data['message']}")
        if self.status.stats["start_time"]:
            elapsed = time.time() - self.status.stats["start_time"]
            logging.info("\nDeployment Statistics:")
            logging.info(f"  • New Files: {self.status.stats['new_files']}")
            logging.info(f"  • Updated Files: {self.status.stats['updated_files']}")
            logging.info(f"  • Deleted Files: {self.status.stats['deleted_files']}")
            logging.info(f"  • Total Time: {elapsed:.2f} seconds")

    def deploy(self) -> bool:
        """
        Execute the full deployment process.

        Returns:
            bool: True if the full deployment succeeds, False otherwise.
        """
        logging.info(
            f"{NordColors.HEADER}{NordColors.BOLD}--- Starting Script Deployment ---{NordColors.RESET}"
        )
        self.status.stats["start_time"] = time.time()

        # Ensure target directory exists
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


#####################################
# Main Function and Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Deploy scripts from source to target directory with verification."
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SCRIPT_SOURCE,
        help="Directory containing the source scripts.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=DEFAULT_SCRIPT_TARGET,
        help="Directory to deploy the scripts to.",
    )
    parser.add_argument(
        "--owner",
        type=str,
        default=DEFAULT_EXPECTED_OWNER,
        help="Expected owner of the source directory.",
    )
    parser.add_argument(
        "--log-file", type=str, default=DEFAULT_LOG_FILE, help="Path to the log file."
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the deployment system."""
    args = parse_arguments()
    logger = setup_logging(args.log_file)
    logger.info("Starting script deployment process.")

    try:
        manager = DeploymentManager(
            source=args.source, target=args.target, expected_owner=args.owner
        )
        manager.check_root()
        manager.check_dependencies()
        if not manager.deploy():
            manager.print_status_report()
            sys.exit(1)
        manager.print_status_report()
        logger.info(
            f"{NordColors.SUCCESS}Deployment completed successfully.{NordColors.RESET}"
        )
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
