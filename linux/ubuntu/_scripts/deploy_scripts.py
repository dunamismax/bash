#!/usr/bin/env python3
"""
Script Name: deploy_scripts.py
--------------------------------------------------------
Description:
  Enhanced script for deploying user scripts from a source directory to a target
  directory on Ubuntu Linux. Features include comprehensive ownership verification,
  file integrity checks, detailed deployment statistics, and a Nord-themed interface
  with rich progress indicators. Provides robust error handling, detailed logging,
  and graceful signal management for reliable script deployment.

Usage:
  sudo ./deploy_scripts.py

Author: Your Name | License: MIT | Version: 3.1.0
"""

import atexit
import json
import logging
import os
import pwd
import signal
import subprocess
import sys
import shutil
import hashlib
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    BarColumn,
)
from rich.panel import Panel
from rich.table import Table

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/deploy-scripts.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Deployment-specific configuration
SCRIPT_SOURCE = "/home/sawyer/github/bash/linux/ubuntu/_scripts"
SCRIPT_TARGET = "/home/sawyer/bin"
EXPECTED_OWNER = "sawyer"

# Global status tracking
DEPLOYMENT_STATUS = {
    "ownership_check": {"status": "pending", "message": ""},
    "dry_run": {"status": "pending", "message": ""},
    "deployment": {"status": "pending", "message": ""},
    "permission_set": {"status": "pending", "message": ""},
}

# Statistics tracking
DEPLOYMENT_STATS = {
    "total_files": 0,
    "new_files": 0,
    "updated_files": 0,
    "deleted_files": 0,
    "unchanged_files": 0,
    "errors": 0,
    "start_time": None,
    "end_time": None,
}

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD2 = "\033[38;2;67;76;94m"  # Polar Night (darker than NORD1)
NORD3 = "\033[38;2;76;86;106m"  # Polar Night (darker than NORD2)
NORD4 = "\033[38;2;216;222;233m"  # Snow Storm (lightest)
NORD5 = "\033[38;2;229;233;240m"  # Snow Storm (middle)
NORD6 = "\033[38;2;236;239;244m"  # Snow Storm (darkest)
NORD7 = "\033[38;2;143;188;187m"  # Frost
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD12 = "\033[38;2;208;135;112m"  # Aurora (orange)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NORD15 = "\033[38;2;180;142;173m"  # Purple
NC = "\033[0m"  # Reset / No Color

# Create a console instance for rich formatting
console = Console()


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom formatter to apply Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers using the Nord color theme.
    Rotates log files if they exceed 10MB in size.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (plain text) with log rotation
    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")

        file_formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord-themed styling.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")

    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before script exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    if any(item["status"] != "pending" for item in DEPLOYMENT_STATUS.values()):
        print_status_report()


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Verify required commands are available and display their versions.
    """
    required_commands = ["rsync", "find"]
    missing = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing:
        logging.error(f"Missing required dependencies: {', '.join(missing)}")
        sys.exit(1)

    # Log the versions of key tools
    try:
        result = subprocess.run(
            ["rsync", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        version_line = (
            result.stdout.splitlines()[0] if result.stdout else "Unknown version"
        )
        logging.info(f"Using {version_line.strip()}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not determine rsync version: {e}")


def check_root():
    """
    Ensure the script is executed with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a progress spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            try:
                return future.result()
            except Exception as e:
                logging.error(f"Operation failed: {e}")
                raise


# ------------------------------------------------------------------------------
# FILE OPERATIONS
# ------------------------------------------------------------------------------
def calculate_file_hash(filepath: str) -> str:
    """
    Calculate MD5 hash of a file for integrity verification.
    """
    try:
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logging.warning(f"Failed to calculate hash for {filepath}: {e}")
        return ""


def verify_file_integrity(source_file: str, target_file: str) -> bool:
    """
    Verify file integrity by comparing MD5 hashes.
    """
    if not os.path.exists(target_file):
        return False

    source_hash = calculate_file_hash(source_file)
    target_hash = calculate_file_hash(target_file)

    return source_hash == target_hash


def get_directory_stats(directory: str) -> Dict[str, Any]:
    """
    Get statistics about files in a directory.
    """
    stats = {
        "file_count": 0,
        "total_size": 0,
        "newest_file": None,
        "newest_timestamp": 0,
    }

    try:
        for root, _, files in os.walk(directory):
            for file in files:
                filepath = os.path.join(root, file)
                file_stat = os.stat(filepath)
                stats["file_count"] += 1
                stats["total_size"] += file_stat.st_size

                if file_stat.st_mtime > stats["newest_timestamp"]:
                    stats["newest_timestamp"] = file_stat.st_mtime
                    stats["newest_file"] = filepath

        if stats["newest_timestamp"] > 0:
            stats["newest_time"] = datetime.fromtimestamp(
                stats["newest_timestamp"]
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            stats["newest_time"] = "N/A"

        stats["total_size_formatted"] = format_size(stats["total_size"])
    except Exception as e:
        logging.warning(f"Failed to get directory stats for {directory}: {e}")

    return stats


def format_size(size_bytes: int) -> str:
    """
    Format byte size into human-readable format.
    """
    if size_bytes == 0:
        return "0 B"
    size_names = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"


# ------------------------------------------------------------------------------
# DEPLOYMENT FUNCTIONS
# ------------------------------------------------------------------------------
def check_ownership() -> bool:
    """
    Check ownership of the source directory.
    """
    DEPLOYMENT_STATUS["ownership_check"] = {
        "status": "in_progress",
        "message": "Checking ownership...",
    }

    try:
        stat_info = os.stat(SCRIPT_SOURCE)
        source_owner = pwd.getpwuid(stat_info.st_uid).pw_name

        if source_owner != EXPECTED_OWNER:
            msg = (
                f"Source directory '{SCRIPT_SOURCE}' ownership is '{source_owner}' "
                f"but expected '{EXPECTED_OWNER}'."
            )
            logging.error(msg)
            DEPLOYMENT_STATUS["ownership_check"] = {"status": "failed", "message": msg}
            return False

        msg = f"Source directory ownership verified as '{source_owner}'."
        logging.info(msg)
        DEPLOYMENT_STATUS["ownership_check"] = {"status": "success", "message": msg}
        return True
    except Exception as e:
        msg = f"Failed to get status of source directory '{SCRIPT_SOURCE}': {e}"
        logging.error(msg)
        DEPLOYMENT_STATUS["ownership_check"] = {"status": "failed", "message": msg}
        return False


def perform_dry_run() -> Tuple[bool, Optional[str]]:
    """
    Perform a dry-run deployment to preview changes.
    """
    DEPLOYMENT_STATUS["dry_run"] = {
        "status": "in_progress",
        "message": "Performing dry run...",
    }

    dry_run_cmd = [
        "rsync",
        "--dry-run",
        "-av",
        "--delete",
        "--itemize-changes",
        f"{SCRIPT_SOURCE.rstrip('/')}/",
        SCRIPT_TARGET,
    ]

    try:

        def run_dry_run():
            return subprocess.run(
                dry_run_cmd, check=True, capture_output=True, text=True
            )

        result = run_with_progress("Dry-run rsync...", run_dry_run)

        # Parse the dry run output to get stats
        changes = []
        for line in result.stdout.splitlines():
            if line.startswith(">"):
                continue
            if len(line) > 10 and line[0] in "<>chst.d":
                changes.append(line)

        new_files = sum(1 for line in changes if line.startswith(">f+"))
        updated_files = sum(1 for line in changes if line.startswith(">f."))
        deleted_files = sum(1 for line in changes if line.startswith("*deleting"))

        DEPLOYMENT_STATS["new_files"] = new_files
        DEPLOYMENT_STATS["updated_files"] = updated_files
        DEPLOYMENT_STATS["deleted_files"] = deleted_files

        msg = f"Dry-run complete: {new_files} new, {updated_files} updated, {deleted_files} to delete"
        logging.info(msg)
        DEPLOYMENT_STATUS["dry_run"] = {"status": "success", "message": msg}

        return True, result.stdout
    except subprocess.CalledProcessError as e:
        msg = f"Dry-run failed: {e.stderr}"
        logging.error(msg)
        DEPLOYMENT_STATUS["dry_run"] = {"status": "failed", "message": msg}
        return False, None


def execute_deployment() -> bool:
    """
    Execute the actual deployment of scripts.
    """
    DEPLOYMENT_STATUS["deployment"] = {
        "status": "in_progress",
        "message": "Deploying scripts...",
    }

    deploy_cmd = [
        "rsync",
        "-av",
        "--delete",
        "--itemize-changes",
        f"{SCRIPT_SOURCE.rstrip('/')}/",
        SCRIPT_TARGET,
    ]

    try:

        def run_deploy():
            return subprocess.run(
                deploy_cmd, check=True, capture_output=True, text=True
            )

        result = run_with_progress("Deploying scripts...", run_deploy)

        # Track deployment changes
        changes = []
        for line in result.stdout.splitlines():
            if line.startswith(">"):
                continue
            if len(line) > 10 and line[0] in "<>chst.d":
                changes.append(line)

        new_files = sum(1 for line in changes if line.startswith(">f+"))
        updated_files = sum(1 for line in changes if line.startswith(">f."))
        deleted_files = sum(1 for line in changes if line.startswith("*deleting"))

        # Update actual numbers based on real deployment
        DEPLOYMENT_STATS["new_files"] = new_files
        DEPLOYMENT_STATS["updated_files"] = updated_files
        DEPLOYMENT_STATS["deleted_files"] = deleted_files

        source_stats = get_directory_stats(SCRIPT_SOURCE)
        DEPLOYMENT_STATS["total_files"] = source_stats["file_count"]
        DEPLOYMENT_STATS["unchanged_files"] = (
            DEPLOYMENT_STATS["total_files"]
            - DEPLOYMENT_STATS["new_files"]
            - DEPLOYMENT_STATS["updated_files"]
        )

        msg = f"Deployment complete: {new_files} new, {updated_files} updated, {deleted_files} deleted"
        logging.info(msg)
        DEPLOYMENT_STATUS["deployment"] = {"status": "success", "message": msg}

        return True
    except subprocess.CalledProcessError as e:
        msg = f"Deployment failed: {e.stderr}"
        logging.error(msg)
        DEPLOYMENT_STATUS["deployment"] = {"status": "failed", "message": msg}
        return False


def set_permissions() -> bool:
    """
    Set executable permissions on deployed scripts.
    """
    DEPLOYMENT_STATUS["permission_set"] = {
        "status": "in_progress",
        "message": "Setting permissions...",
    }

    try:

        def run_chmod():
            # More robust find command with better error handling
            find_cmd = [
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
            return subprocess.run(find_cmd, check=True, capture_output=True, text=True)

        result = run_with_progress("Setting permissions...", run_chmod)

        msg = "Permissions set successfully on all scripts."
        logging.info(msg)
        DEPLOYMENT_STATUS["permission_set"] = {"status": "success", "message": msg}

        # Verify a few random files have correct permissions
        for root, _, files in os.walk(SCRIPT_TARGET):
            for file in files[:5]:  # Check up to 5 files
                filepath = os.path.join(root, file)
                permissions = oct(os.stat(filepath).st_mode)[-3:]
                if permissions != "755":
                    logging.warning(
                        f"File {filepath} has unexpected permissions: {permissions}"
                    )

        return True
    except subprocess.CalledProcessError as e:
        msg = f"Failed to set permissions: {e.stderr if e.stderr else str(e)}"
        logging.error(msg)
        DEPLOYMENT_STATUS["permission_set"] = {"status": "failed", "message": msg}
        return False


def deploy_user_scripts():
    """
    Deploy user scripts from the source to the target directory.
    """
    print_section("Deploying User Scripts")
    logging.info("Starting deployment of user scripts...")

    DEPLOYMENT_STATS["start_time"] = time.time()

    # Check that target directory exists
    if not os.path.exists(SCRIPT_TARGET):
        try:
            os.makedirs(SCRIPT_TARGET, exist_ok=True)
            logging.info(f"Created target directory: {SCRIPT_TARGET}")
        except Exception as e:
            logging.error(f"Failed to create target directory '{SCRIPT_TARGET}': {e}")
            sys.exit(1)

    # 1. Check ownership
    if not check_ownership():
        sys.exit(1)

    # 2. Perform a dry-run deployment
    success, dry_run_output = perform_dry_run()
    if not success:
        sys.exit(1)

    # 3. Execute actual deployment
    if not execute_deployment():
        sys.exit(1)

    # 4. Set executable permissions on deployed scripts
    if not set_permissions():
        logging.warning(
            "Permission setting had issues, but deployment may still be usable."
        )

    DEPLOYMENT_STATS["end_time"] = time.time()
    logging.info("Script deployment completed successfully.")


# ------------------------------------------------------------------------------
# STATUS REPORTING
# ------------------------------------------------------------------------------
def print_status_report():
    """
    Print a detailed status report of the deployment.
    """
    print_section("Deployment Status Report")

    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "skipped": "⏭" if not DISABLE_COLORS else "[SKIPPED]",
    }

    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
        "skipped": NORD9,
    }

    descriptions = {
        "ownership_check": "Source Ownership Verification",
        "dry_run": "Deployment Dry Run",
        "deployment": "Script Deployment",
        "permission_set": "Permission Setting",
    }

    for task, data in DEPLOYMENT_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)

        if not DISABLE_COLORS:
            icon = icons[status]
            color = colors[status]
            logging.info(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")
        else:
            logging.info(f"{icons[status]} {task_desc}: {status.upper()} - {msg}")

    # Print deployment statistics if deployment was attempted
    if DEPLOYMENT_STATS["start_time"] is not None:
        elapsed_time = (DEPLOYMENT_STATS["end_time"] or time.time()) - DEPLOYMENT_STATS[
            "start_time"
        ]

        logging.info("\nDeployment Statistics:")
        logging.info(f"  • Total Files: {DEPLOYMENT_STATS['total_files']}")
        logging.info(f"  • New Files: {DEPLOYMENT_STATS['new_files']}")
        logging.info(f"  • Updated Files: {DEPLOYMENT_STATS['updated_files']}")
        logging.info(f"  • Deleted Files: {DEPLOYMENT_STATS['deleted_files']}")
        logging.info(f"  • Unchanged Files: {DEPLOYMENT_STATS['unchanged_files']}")
        logging.info(f"  • Total Time: {elapsed_time:.2f} seconds")


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for script execution.
    """
    # Ensure the log directory exists.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"Failed to create log directory '{log_dir}': {e}")
            sys.exit(1)

    # Initialize logging first
    setup_logging()

    try:
        # Check requirements
        check_root()
        check_dependencies()

        start_time = time.time()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info("=" * 80)
        logging.info(f"SCRIPT DEPLOYMENT STARTED AT {now}")
        logging.info("=" * 80)

        print_section("System Information")
        logging.info(f"Hostname: {os.uname().nodename}")
        logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
        logging.info(f"Python version: {sys.version.split()[0]}")

        # Source and target information
        source_stats = get_directory_stats(SCRIPT_SOURCE)
        if os.path.exists(SCRIPT_TARGET):
            target_stats = get_directory_stats(SCRIPT_TARGET)
            logging.info(
                f"Source directory: {SCRIPT_SOURCE} ({source_stats['file_count']} files, {source_stats['total_size_formatted']})"
            )
            logging.info(
                f"Target directory: {SCRIPT_TARGET} ({target_stats['file_count']} files, {target_stats['total_size_formatted']})"
            )
        else:
            logging.info(
                f"Source directory: {SCRIPT_SOURCE} ({source_stats['file_count']} files, {source_stats['total_size_formatted']})"
            )
            logging.info(f"Target directory: {SCRIPT_TARGET} (does not exist yet)")

        # Execute the deployment
        deploy_user_scripts()

        # Print final status report
        print_status_report()

        elapsed = time.time() - start_time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        all_success = all(
            data["status"] == "success" for data in DEPLOYMENT_STATUS.values()
        )
        if all_success:
            summary = "SUCCESS"
        else:
            failures = sum(
                1 for data in DEPLOYMENT_STATUS.values() if data["status"] == "failed"
            )
            summary = (
                "PARTIAL SUCCESS" if failures < len(DEPLOYMENT_STATUS) else "FAILED"
            )

        logging.info("=" * 80)
        logging.info(
            f"SCRIPT DEPLOYMENT COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)"
        )
        logging.info("=" * 80)

    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        if "logging" in sys.modules:
            logging.error(f"Unhandled exception: {ex}")
        else:
            print(f"Unhandled exception: {ex}")
        sys.exit(1)
