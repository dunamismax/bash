#!/usr/bin/env python3
"""
System Backup Script

Performs a comprehensive backup of the root filesystem to Backblaze B2 using restic.
This script provides detailed progress tracking, comprehensive error handling, and
clear status reporting throughout the backup process.

It excludes common directories not needed in backups such as /proc, /sys, temporary files,
and large binary files to ensure efficient and relevant backups.

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

# Repository path for system backup
REPOSITORY: str = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"

# Backup paths and exclusion patterns
BACKUP_PATHS: List[str] = ["/"]
BACKUP_EXCLUDES: List[str] = [
    "/proc/*",
    "/sys/*",
    "/dev/*",
    "/run/*",
    "/tmp/*",
    "/var/tmp/*",
    "/mnt/*",
    "/media/*",
    "/var/cache/*",
    "/var/log/*",
    "/home/*/.cache/*",
    "/swapfile",
    "/lost+found",
    "*.vmdk",
    "*.vdi",
    "*.qcow2",
    "*.img",
    "*.iso",
    "*.tmp",
    "*.swap.img",
    "/var/lib/docker/*",
    "/var/lib/lxc/*",
]

# Progress tracking and retention settings
PROGRESS_WIDTH: int = 50
CHUNK_SIZE: int = 1024 * 1024  # 1MB chunks
RETENTION_POLICY: str = "7d"  # Keep snapshots from last 7 days
MAX_WORKERS: int = min(32, (os.cpu_count() or 1) * 2)

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class NordColors:
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
        """Safely update the progress and refresh the display."""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_size(self, bytes_val: int) -> str:
        """Convert bytes to a human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}TB"

    def _display(self) -> None:
        """Display the progress bar with percentage, rate, and ETA."""
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
    """
    try:
        return subprocess.run(cmd, env=env, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"{NordColors.ERROR}Command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}{NordColors.RESET}")
        raise


def signal_handler(sig: int, frame) -> None:
    """Handle interrupt signals gracefully."""
    print(f"\n{NordColors.WARNING}Backup interrupted. Exiting...{NordColors.RESET}")
    sys.exit(1)


#####################################
# Environment and Dependency Checks
#####################################


def check_dependencies() -> bool:
    """Ensure that restic is installed."""
    if not shutil.which("restic"):
        print(
            f"{NordColors.ERROR}Error: Restic is not installed. Please install restic first.{NordColors.RESET}"
        )
        return False
    return True


def check_environment() -> bool:
    """Verify required environment variables for Backblaze B2 and restic."""
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


def get_disk_usage(path: str = "/") -> Tuple[int, int, float]:
    """
    Retrieve disk usage statistics.

    Returns:
        Tuple of total bytes, used bytes, and percent used.
    """
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bfree * stat.f_frsize
    used = total - free
    percent = (used / total) * 100
    return total, used, percent


#####################################
# Repository Management
#####################################


def initialize_repository() -> bool:
    """
    Initialize the restic repository if not already set up.
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
# Backup Size Estimation
#####################################


def _format_size(bytes_val: int) -> str:
    """Convert a byte count into a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


def estimate_backup_size() -> int:
    """
    Estimate the backup size by sampling disk usage and excluding specified paths.
    """
    print_header("Estimating Backup Size")
    total, used, percent = get_disk_usage("/")
    excluded_size = 0
    for exclude in BACKUP_EXCLUDES:
        if "*" not in exclude:
            path = exclude.rstrip("/*")
            try:
                if os.path.exists(path):
                    dir_size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(path)
                        for filename in filenames
                    )
                    excluded_size += dir_size
            except (PermissionError, OSError):
                pass
    estimated_size = max(used - excluded_size, 0)
    compression_factor = 0.7  # Assume restic's compression ratio
    estimated_backup_size = int(estimated_size * compression_factor)
    print(f"Total disk size: {_format_size(total)}")
    print(f"Used disk space: {_format_size(used)} ({percent:.1f}%)")
    print(f"Estimated backup size: {_format_size(estimated_backup_size)}")
    return estimated_backup_size


#####################################
# Backup Execution Functions
#####################################


def perform_backup() -> bool:
    """
    Execute the system backup using restic.
    """
    print_header("Starting System Backup")
    try:
        estimated_size = estimate_backup_size()
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )
        progress = ProgressBar(estimated_size, desc="Backup progress")
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
        # Parse output and update progress (approximate)
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if not line.strip():
                continue
            print(f"\r{' ' * (PROGRESS_WIDTH + 60)}\r", end="")
            print(line.strip())
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
            progress._display()
        process.wait()
        if process.returncode != 0:
            print(
                f"{NordColors.ERROR}Backup failed with return code {process.returncode}.{NordColors.RESET}"
            )
            return False
        print(
            f"{NordColors.SUCCESS}System backup completed successfully.{NordColors.RESET}"
        )
        return True
    except Exception as e:
        print(f"{NordColors.ERROR}Backup failed: {e}{NordColors.RESET}")
        return False


def perform_retention() -> bool:
    """
    Apply the retention policy to manage repository size.
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
    List all snapshots in the backup repository.
    """
    print_header("System Backup Snapshots")
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
    """Main function for the system backup workflow."""
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
    print_header("System Backup Script")
    print(f"Hostname: {HOSTNAME}")
    print(f"Platform: {platform.platform()}")
    print(f"Backup Repository: {REPOSITORY}")
    print(f"Backup Paths: {', '.join(BACKUP_PATHS)}")
    print(f"Number of Excludes: {len(BACKUP_EXCLUDES)}")
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
            f"{NordColors.SUCCESS}System backup completed successfully.{NordColors.RESET}"
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
