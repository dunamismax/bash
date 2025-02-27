#!/usr/bin/env python3
"""
Plex Media Server Backup Script

This script creates a complete backup of Plex Media Server configuration and data
using restic and uploads it to Backblaze B2. It automatically excludes unnecessary
cache files, logs, and temporary data for an efficient backup. It provides detailed
progress tracking, robust error handling, and clear status reporting.

Note: Run this script with root privileges.
"""

import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#####################################
# Configuration Constants
#####################################

HOSTNAME: str = socket.gethostname()

# Backblaze B2 and restic configuration
B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"
RESTIC_PASSWORD: str = "12345678"

# Repository path for Plex backup
REPOSITORY: str = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# Plex backup paths and exclusion patterns
BACKUP_PATHS: List[str] = ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]
BACKUP_EXCLUDES: List[str] = [
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
]

# Progress tracking settings
PROGRESS_WIDTH: int = 50
CHUNK_SIZE: int = 1024 * 1024  # 1MB chunks for progress tracking
RETENTION_POLICY: str = "7d"  # Keep snapshots from last 7 days
MAX_WORKERS: int = min(32, (os.cpu_count() or 1) * 2)

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class NordColors:
    """Nord-themed ANSI color codes."""

    HEADER: str = "\033[38;2;216;222;233m"  # Light gray
    INFO: str = "\033[38;2;136;192;208m"  # Light blue
    SUCCESS: str = "\033[38;2;163;190;140m"  # Green
    WARNING: str = "\033[38;2;235;203;139m"  # Yellow
    ERROR: str = "\033[38;2;191;97;106m"  # Red
    RESET: str = "\033[0m"
    BOLD: str = "\033[1m"


#####################################
# Progress Tracking Class
#####################################


class ProgressBar:
    """
    Thread-safe progress bar with transfer rate display.
    """

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH) -> None:
        self.total: int = total
        self.desc: str = desc
        self.width: int = width
        self.current: int = 0
        self.start_time: float = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Safely update progress and refresh the display."""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_size(self, bytes_val: int) -> str:
        """Convert bytes to a human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}TB"

    def _display(self) -> None:
        """Display the progress bar with percentage, transfer rate, and ETA."""
        filled = int(self.width * self.current / self.total)
        bar = "=" * filled + "-" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0

        sys.stdout.write(
            f"\r{self.desc}: |{bar}| {percent:>5.1f}% "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{self._format_size(int(rate))}/s] [ETA: {int(eta)}s]"
        )
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write("\n")


#####################################
# UI Helper Functions
#####################################


def print_header(message: str) -> None:
    """Print a formatted header using Nord-themed colors."""
    print(f"\n{NordColors.HEADER}{NordColors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{NordColors.RESET}\n")


#####################################
# Command Execution and Signal Handling
#####################################


def run_command(
    cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True
) -> subprocess.CompletedProcess:
    """
    Execute a system command with error handling.

    Args:
        cmd (List[str]): The command and arguments.
        env (Optional[Dict[str, str]]): Environment variables.
        check (bool): Whether to raise an exception on failure.

    Returns:
        subprocess.CompletedProcess: The result of the executed command.
    """
    try:
        return subprocess.run(cmd, env=env, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"{NordColors.ERROR}Command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}{NordColors.RESET}")
        raise


def signal_handler(sig: int, frame) -> None:
    """Gracefully handle interrupt signals."""
    print(f"\n{NordColors.WARNING}Backup interrupted. Exiting...{NordColors.RESET}")
    sys.exit(1)


#####################################
# Environment and Dependency Checks
#####################################


def check_dependencies() -> bool:
    """Ensure required tools (restic) are installed."""
    if not shutil.which("restic"):
        print(
            f"{NordColors.ERROR}Error: Restic is not installed. Please install restic first.{NordColors.RESET}"
        )
        return False
    return True


def check_environment() -> bool:
    """
    Verify that required environment variables are set.

    Returns:
        bool: True if all variables are set; False otherwise.
    """
    missing_vars = []
    if not B2_ACCOUNT_ID:
        missing_vars.append("B2_ACCOUNT_ID")
    if not B2_ACCOUNT_KEY:
        missing_vars.append("B2_ACCOUNT_KEY")
    if not RESTIC_PASSWORD:
        missing_vars.append("RESTIC_PASSWORD")
    if missing_vars:
        print(
            f"{NordColors.ERROR}Error: The following environment variables are not set:{NordColors.RESET}"
        )
        for var in missing_vars:
            print(f"  - {var}")
        return False
    return True


def check_plex_installed() -> bool:
    """Check if Plex Media Server is installed."""
    if not os.path.exists("/var/lib/plexmediaserver"):
        print(
            f"{NordColors.ERROR}Error: Plex Media Server installation not found.{NordColors.RESET}"
        )
        print("Expected path: /var/lib/plexmediaserver")
        return False
    return True


def check_plex_service() -> Tuple[bool, str]:
    """
    Check the status of the Plex Media Server service.

    Returns:
        Tuple[bool, str]: (is_running, status_message)
    """
    try:
        result = run_command(["systemctl", "is-active", "plexmediaserver"], check=False)
        is_running = result.returncode == 0
        status = result.stdout.strip()
        return (True, "running") if is_running else (False, status)
    except Exception as e:
        return (False, str(e))


#####################################
# Repository Management Functions
#####################################


def initialize_repository() -> bool:
    """
    Initialize the restic repository if it does not already exist.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    print_header("Checking Repository")
    try:
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )
        try:
            run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)
            print(
                f"{NordColors.SUCCESS}Repository already initialized.{NordColors.RESET}"
            )
            return True
        except subprocess.CalledProcessError:
            print("Repository not found. Initializing...")
            run_command(["restic", "--repo", REPOSITORY, "init"], env=env)
            print(
                f"{NordColors.SUCCESS}Repository initialized successfully.{NordColors.RESET}"
            )
            return True
    except Exception as e:
        print(
            f"{NordColors.ERROR}Failed to initialize repository: {e}{NordColors.RESET}"
        )
        return False


#####################################
# Backup Size Estimation Functions
#####################################


def _format_size(bytes_val: int) -> str:
    """Convert a byte count into a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


def calculate_plex_backup_size() -> Tuple[int, int]:
    """
    Calculate the total size and file count for the Plex backup.

    Returns:
        Tuple[int, int]: (total_size_bytes, file_count)
    """
    print_header("Calculating Backup Size")
    total_size: int = 0
    file_count: int = 0
    exclude_prefixes: List[str] = [exclude.rstrip("*") for exclude in BACKUP_EXCLUDES]

    # For progress tracking on large directories
    progress: Optional[ProgressBar] = None
    progress_step: int = 0

    for path in BACKUP_PATHS:
        if not os.path.exists(path):
            print(
                f"{NordColors.WARNING}Warning: Path {path} does not exist, skipping.{NordColors.RESET}"
            )
            continue

        print(f"Scanning {path}...")
        if path == "/var/lib/plexmediaserver":
            progress = ProgressBar(total=100, desc="Scanning Plex data")
            progress_step = 0

        for root, dirs, files in os.walk(path):
            # Skip directories that match any excluded prefix
            if any(root.startswith(prefix) for prefix in exclude_prefixes):
                continue

            if path == "/var/lib/plexmediaserver" and progress:
                progress_step += 1
                if progress_step % 100 == 0:
                    progress.update(1)

            for file in files:
                file_path = os.path.join(root, file)
                try:
                    stat_info = os.stat(file_path)
                    total_size += stat_info.st_size
                    file_count += 1
                except (FileNotFoundError, PermissionError):
                    pass

    print(f"\nFound {file_count} files totaling {_format_size(total_size)}")
    return total_size, file_count


#####################################
# Backup Execution Functions
#####################################


def perform_backup() -> bool:
    """
    Execute the Plex backup using restic.

    Returns:
        bool: True if backup succeeded; False otherwise.
    """
    print_header("Starting Plex Backup")
    try:
        total_size, file_count = calculate_plex_backup_size()
        if total_size == 0:
            print(
                f"{NordColors.WARNING}Warning: No files found to backup. Plex may not be properly installed.{NordColors.RESET}"
            )
            return False

        print(f"Preparing to backup {file_count} files ({_format_size(total_size)})")

        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        progress = ProgressBar(total_size, desc="Backup progress")

        backup_cmd: List[str] = ["restic", "--repo", REPOSITORY, "backup"]
        backup_cmd.extend(BACKUP_PATHS)
        for exclude in BACKUP_EXCLUDES:
            backup_cmd.extend(["--exclude", exclude])
        backup_cmd.append("--verbose")

        process = subprocess.Popen(
            backup_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Parse restic output and update progress.
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if not line.strip():
                continue

            # Clear line for clean progress display.
            print(f"\r{' ' * (PROGRESS_WIDTH + 60)}\r", end="")
            print(line.strip())

            # Update progress if line indicates file addition.
            if "added to the repository" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.endswith("B") and i > 0 and parts[i - 1].isdigit():
                            bytes_str = parts[i - 1] + part
                            for unit, multiplier in {
                                "B": 1,
                                "KiB": 1024,
                                "MiB": 1024**2,
                                "GiB": 1024**3,
                            }.items():
                                if unit in bytes_str:
                                    size = float(bytes_str.replace(unit, "").strip())
                                    progress.update(int(size * multiplier))
                                    break
                except Exception:
                    progress.update(CHUNK_SIZE)
            if progress:
                progress._display()

        process.wait()
        if process.returncode != 0:
            print(
                f"{NordColors.ERROR}Backup failed with return code {process.returncode}.{NordColors.RESET}"
            )
            return False

        print(
            f"{NordColors.SUCCESS}Plex backup completed successfully.{NordColors.RESET}"
        )
        return True

    except Exception as e:
        print(f"{NordColors.ERROR}Backup failed: {e}{NordColors.RESET}")
        return False


def perform_retention() -> bool:
    """
    Apply the retention policy to the repository.

    Returns:
        bool: True if retention succeeded; False otherwise.
    """
    print_header("Applying Retention Policy")
    try:
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )
        retention_cmd: List[str] = [
            "restic",
            "--repo",
            REPOSITORY,
            "forget",
            "--prune",
            "--keep-within",
            RETENTION_POLICY,
        ]
        print(f"Applying retention policy: keeping snapshots within {RETENTION_POLICY}")
        result = run_command(retention_cmd, env=env)
        print(
            f"{NordColors.SUCCESS}Retention policy applied successfully.{NordColors.RESET}"
        )
        print(result.stdout)
        return True
    except Exception as e:
        print(
            f"{NordColors.ERROR}Failed to apply retention policy: {e}{NordColors.RESET}"
        )
        return False


def list_snapshots() -> bool:
    """
    List all snapshots in the repository.

    Returns:
        bool: True if snapshots were listed successfully; False otherwise.
    """
    print_header("Plex Backup Snapshots")
    try:
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )
        result = run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)
        if result.stdout.strip():
            print(result.stdout)
        else:
            print(
                f"{NordColors.WARNING}No snapshots found in the repository.{NordColors.RESET}"
            )
        return True
    except Exception as e:
        print(f"{NordColors.ERROR}Failed to list snapshots: {e}{NordColors.RESET}")
        return False


#####################################
# Main Execution Flow
#####################################


def main() -> None:
    """Main function for executing the Plex backup workflow."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if os.geteuid() != 0:
        print(
            f"{NordColors.ERROR}Error: This script must be run with root privileges.{NordColors.RESET}"
        )
        sys.exit(1)

    if not check_dependencies():
        sys.exit(1)
    if not check_environment():
        sys.exit(1)
    if not check_plex_installed():
        sys.exit(1)

    is_running, plex_status = check_plex_service()

    print_header("Plex Media Server Backup Script")
    print(f"Hostname: {HOSTNAME}")
    print(f"Platform: {platform.platform()}")
    print(f"Backup Repository: {REPOSITORY}")
    print(f"Plex Service Status: {plex_status}")

    start_time = time.time()

    try:
        if not initialize_repository():
            sys.exit(1)
        if not perform_backup():
            sys.exit(1)
        if not perform_retention():
            print(
                f"{NordColors.WARNING}Warning: Failed to apply retention policy, but backup was successful.{NordColors.RESET}"
            )
        list_snapshots()

        end_time = time.time()
        elapsed = end_time - start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        print_header("Backup Summary")
        print(
            f"{NordColors.SUCCESS}Plex Media Server backup completed successfully.{NordColors.RESET}"
        )
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    except KeyboardInterrupt:
        print(f"\n{NordColors.WARNING}Backup interrupted by user{NordColors.RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{NordColors.ERROR}Backup failed: {e}{NordColors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
