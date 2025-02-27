#!/usr/bin/env python3
"""
Script Deployment System

Deploys scripts from source to target directory with comprehensive verification.

Usage:
  sudo python3 deploy_scripts.py
"""

import os
import sys
import pwd
import logging
import subprocess
import shutil
import hashlib
import signal
import time
from datetime import datetime


# Configuration Constants
SCRIPT_SOURCE = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
SCRIPT_TARGET = "/home/sawyer/bin"
EXPECTED_OWNER = "sawyer"
LOG_FILE = "/var/log/deploy-scripts.log"


class DeploymentStatus:
    """Track deployment progress and statistics"""

    def __init__(self):
        self.steps = {
            "ownership_check": {"status": "pending", "message": ""},
            "dry_run": {"status": "pending", "message": ""},
            "deployment": {"status": "pending", "message": ""},
            "permission_set": {"status": "pending", "message": ""},
        }
        self.stats = {
            "total_files": 0,
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "unchanged_files": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
        }

    def update_step(self, step, status, message):
        """Update step status and message"""
        if step in self.steps:
            self.steps[step] = {"status": status, "message": message}

    def update_stats(self, **kwargs):
        """Update deployment statistics"""
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value


def setup_logging():
    """Configure logging with console and file handlers"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        # Create log directory if needed
        log_dir = os.path.dirname(LOG_FILE)
        os.makedirs(log_dir, exist_ok=True)

        # Rotate log if over 10MB
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup)

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Set secure permissions on log file
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to setup file logging: {e}")

    return logger


def run_command(cmd, check=True, timeout=30):
    """Run system command with error handling"""
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


class DeploymentManager:
    """Manage script deployment process"""

    def __init__(self):
        self.status = DeploymentStatus()
        self.logger = logging.getLogger()

        # Signal handling
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals"""
        sig_name = (
            signal.Signals(signum).name
            if hasattr(signal, "Signals")
            else f"signal {signum}"
        )
        logging.warning(f"Deployment interrupted by {sig_name}")
        self.print_status_report()
        sys.exit(130)

    def check_root(self):
        """Verify root privileges"""
        if os.geteuid() != 0:
            logging.error("This script must be run as root")
            sys.exit(1)

    def check_dependencies(self):
        """Verify required system commands"""
        required = ["rsync", "find"]
        missing = [cmd for cmd in required if not shutil.which(cmd)]
        if missing:
            logging.error(f"Missing required commands: {', '.join(missing)}")
            sys.exit(1)

    def check_ownership(self):
        """Verify source directory ownership"""
        self.status.update_step(
            "ownership_check", "in_progress", "Checking ownership..."
        )

        try:
            stat_info = os.stat(SCRIPT_SOURCE)
            owner = pwd.getpwuid(stat_info.st_uid).pw_name

            if owner != EXPECTED_OWNER:
                msg = (
                    f"Source directory owned by '{owner}', expected '{EXPECTED_OWNER}'"
                )
                self.status.update_step("ownership_check", "failed", msg)
                return False

            msg = f"Source directory ownership verified as '{owner}'"
            self.status.update_step("ownership_check", "success", msg)
            return True

        except Exception as e:
            msg = f"Failed to check ownership: {e}"
            self.status.update_step("ownership_check", "failed", msg)
            return False

    def perform_dry_run(self):
        """Perform deployment dry run"""
        self.status.update_step("dry_run", "in_progress", "Performing dry run...")

        try:
            result = run_command(
                [
                    "rsync",
                    "--dry-run",
                    "-av",
                    "--delete",
                    "--itemize-changes",
                    f"{SCRIPT_SOURCE.rstrip('/')}/",
                    SCRIPT_TARGET,
                ]
            )

            # Parse output for changes
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

            msg = f"Dry run complete: {new_files} new, {updated_files} updated, {deleted_files} to delete"
            self.status.update_step("dry_run", "success", msg)
            return True

        except Exception as e:
            msg = f"Dry run failed: {e}"
            self.status.update_step("dry_run", "failed", msg)
            return False

    def execute_deployment(self):
        """Execute actual deployment"""
        self.status.update_step("deployment", "in_progress", "Deploying scripts...")

        try:
            result = run_command(
                [
                    "rsync",
                    "-av",
                    "--delete",
                    "--itemize-changes",
                    f"{SCRIPT_SOURCE.rstrip('/')}/",
                    SCRIPT_TARGET,
                ]
            )

            # Count actual changes
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

            msg = f"Deployment complete: {new_files} new, {updated_files} updated, {deleted_files} deleted"
            self.status.update_step("deployment", "success", msg)
            return True

        except Exception as e:
            msg = f"Deployment failed: {e}"
            self.status.update_step("deployment", "failed", msg)
            return False

    def set_permissions(self):
        """Set correct permissions on deployed files"""
        self.status.update_step(
            "permission_set", "in_progress", "Setting permissions..."
        )

        try:
            run_command(
                [
                    "find",
                    SCRIPT_TARGET,
                    "-type",
                    "f",
                    "-exec",
                    "chmod",
                    "755",
                    "{}",
                    ";",
                ]
            )

            msg = "Permissions set successfully"
            self.status.update_step("permission_set", "success", msg)
            return True

        except Exception as e:
            msg = f"Failed to set permissions: {e}"
            self.status.update_step("permission_set", "failed", msg)
            return False

    def print_status_report(self):
        """Print deployment status report"""
        logging.info("\n--- Deployment Status Report ---")

        # Status indicators
        icons = {"success": "✓", "failed": "✗", "pending": "?", "in_progress": "⋯"}

        # Print step statuses
        for step, data in self.status.steps.items():
            status = data["status"]
            msg = data["message"]
            icon = icons.get(status, "?")
            logging.info(f"{icon} {step}: {status.upper()} - {msg}")

        # Print statistics if deployment was attempted
        if self.status.stats["start_time"]:
            elapsed = time.time() - self.status.stats["start_time"]
            logging.info("\nDeployment Statistics:")
            logging.info(f"  • Total Files: {self.status.stats['total_files']}")
            logging.info(f"  • New Files: {self.status.stats['new_files']}")
            logging.info(f"  • Updated Files: {self.status.stats['updated_files']}")
            logging.info(f"  • Deleted Files: {self.status.stats['deleted_files']}")
            logging.info(f"  • Unchanged Files: {self.status.stats['unchanged_files']}")
            logging.info(f"  • Total Time: {elapsed:.2f} seconds")

    def deploy(self):
        """Execute full deployment process"""
        logging.info("--- Starting Script Deployment ---")
        self.status.stats["start_time"] = time.time()

        # Create target directory if needed
        os.makedirs(SCRIPT_TARGET, exist_ok=True)

        # Run deployment steps
        if not self.check_ownership():
            return False

        if not self.perform_dry_run():
            return False

        if not self.execute_deployment():
            return False

        success = self.set_permissions()

        self.status.stats["end_time"] = time.time()
        return success


def main():
    """Main entry point"""
    # Setup logging
    logger = setup_logging()
    logger.info("Starting script deployment")

    try:
        # Initialize deployment manager
        manager = DeploymentManager()

        # Verify requirements
        manager.check_root()
        manager.check_dependencies()

        # Execute deployment
        success = manager.deploy()

        # Print final status
        manager.print_status_report()

        if not success:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
