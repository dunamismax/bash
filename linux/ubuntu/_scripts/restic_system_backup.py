#!/usr/bin/env python3
"""
System Backup Script

Performs a comprehensive backup of the root filesystem to Backblaze B2 using restic.
This script provides detailed progress tracking, comprehensive error handling, and
clear status reporting throughout the backup process.

The script excludes common directories not needed in backups such as /proc, /sys,
temporary files, and large binary files to ensure efficient and relevant backups.

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
from typing import Dict, List, Optional, Tuple, Any, Union

# Configuration
HOSTNAME = socket.gethostname()

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository path
REPOSITORY = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"

# System backup paths and excludes
BACKUP_PATHS = ["/"]
BACKUP_EXCLUDES = [
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

# Progress tracking settings
PROGRESS_WIDTH = 50
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
RETENTION_POLICY = "7d"  # Keep snapshots from last 7 days
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)


class Colors:
    """ANSI color codes"""

    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_size(self, bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = "=" * filled + "-" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0

        sys.stdout.write(
            f"\r{self.desc}: |{bar}| {percent:>5.1f}% "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{self._format_size(rate)}/s] [ETA: {eta:.0f}s]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def run_command(
    cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True
) -> subprocess.CompletedProcess:
    """Run command with error handling"""
    try:
        return subprocess.run(cmd, env=env, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}Command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}{Colors.ENDC}")
        raise


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully"""
    print(f"\n{Colors.YELLOW}Backup interrupted. Exiting...{Colors.ENDC}")
    sys.exit(1)


def check_dependencies() -> bool:
    """Check if restic is installed"""
    if not shutil.which("restic"):
        print(
            f"{Colors.RED}Error: Restic is not installed. Please install restic first.{Colors.ENDC}"
        )
        return False
    return True


def check_environment() -> bool:
    """Check if required environment variables are set"""
    missing_vars = []

    if not B2_ACCOUNT_ID:
        missing_vars.append("B2_ACCOUNT_ID")
    if not B2_ACCOUNT_KEY:
        missing_vars.append("B2_ACCOUNT_KEY")
    if not RESTIC_PASSWORD:
        missing_vars.append("RESTIC_PASSWORD")

    if missing_vars:
        print(
            f"{Colors.RED}Error: The following environment variables are not set:{Colors.ENDC}"
        )
        for var in missing_vars:
            print(f"  - {var}")
        return False

    return True


def get_disk_usage(path: str = "/") -> Tuple[int, int, float]:
    """
    Get disk usage statistics

    Args:
        path: The path to check

    Returns:
        Tuple[int, int, float]: (total_bytes, used_bytes, percent_used)
    """
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bfree * stat.f_frsize
    used = total - free
    percent = (used / total) * 100

    return total, used, percent


def initialize_repository() -> bool:
    """Initialize repository if not already initialized"""
    print_header("Checking Repository")

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Check if repository exists
        try:
            run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)
            print(f"{Colors.GREEN}Repository already initialized.{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError:
            # Repository doesn't exist, initialize it
            print("Repository not found. Initializing...")
            run_command(["restic", "--repo", REPOSITORY, "init"], env=env)
            print(f"{Colors.GREEN}Repository initialized successfully.{Colors.ENDC}")
            return True

    except Exception as e:
        print(f"{Colors.RED}Failed to initialize repository: {e}{Colors.ENDC}")
        return False


def estimate_backup_size() -> int:
    """
    Estimate the size of a system backup by sampling key directories

    This uses a sampling approach rather than full calculation because
    counting all files on a system could take too long.

    Returns:
        int: Estimated backup size in bytes
    """
    print_header("Estimating Backup Size")

    # Get total system disk usage
    total, used, percent = get_disk_usage("/")

    # Sample key directories to estimate what percentage will be backed up
    excluded_size = 0
    for exclude in BACKUP_EXCLUDES:
        if "*" not in exclude:
            # This is a directory exclusion
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

    # Estimate: Used space minus excluded size, with safety margin
    estimated_size = max(used - excluded_size, 0)

    # Apply a compression factor (restic uses compression)
    compression_factor = 0.7  # Assume 30% compression ratio
    estimated_backup_size = int(estimated_size * compression_factor)

    print(f"Total disk size: {_format_size(total)}")
    print(f"Used disk space: {_format_size(used)} ({percent:.1f}%)")
    print(f"Estimated backup size: {_format_size(estimated_backup_size)}")

    return estimated_backup_size


def _format_size(bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def perform_backup() -> bool:
    """
    Perform the system backup using restic

    Returns:
        bool: True if backup succeeded, False otherwise
    """
    print_header("Starting System Backup")

    try:
        # Estimate backup size for progress tracking
        estimated_size = estimate_backup_size()

        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Start a progress monitor
        progress = ProgressBar(estimated_size, desc="Backup progress")

        # Construct backup command
        backup_cmd = ["restic", "--repo", REPOSITORY, "backup"]

        # Add paths
        backup_cmd.extend(BACKUP_PATHS)

        # Add excludes
        for exclude in BACKUP_EXCLUDES:
            backup_cmd.extend(["--exclude", exclude])

        # Add progress monitoring
        backup_cmd.append("--verbose")

        # Run backup command with progress tracking
        process = subprocess.Popen(
            backup_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Parse output to update progress
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Skip empty lines
            if not line.strip():
                continue

            # Print verbose output in a way that doesn't interfere with progress bar
            print(f"\r{' ' * (PROGRESS_WIDTH + 60)}\r", end="")
            print(line.strip())

            # Update progress based on processed files (this is approximate)
            if "added to the repository" in line:
                try:
                    # Extract bytes processed
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.endswith("B") and i > 0 and parts[i - 1].isdigit():
                            bytes_str = parts[i - 1] + part

                            # Convert to bytes for progress
                            for unit, multiplier in {
                                "B": 1,
                                "KiB": 1024,
                                "MiB": 1024**2,
                                "GiB": 1024**3,
                            }.items():
                                if unit in bytes_str:
                                    size = float(bytes_str.replace(unit, "").strip())
                                    bytes_processed = int(size * multiplier)
                                    progress.update(bytes_processed)
                                    break
                except Exception:
                    # If parsing fails, just update with a small increment
                    progress.update(CHUNK_SIZE)

            # Ensure progress bar is redrawn
            progress._display()

        # Wait for process to complete
        process.wait()

        # Check if backup was successful
        if process.returncode != 0:
            print(
                f"{Colors.RED}Backup failed with return code {process.returncode}.{Colors.ENDC}"
            )
            return False

        print(f"{Colors.GREEN}System backup completed successfully.{Colors.ENDC}")
        return True

    except Exception as e:
        print(f"{Colors.RED}Backup failed: {str(e)}{Colors.ENDC}")
        return False


def perform_retention() -> bool:
    """
    Apply retention policy to keep the repository size manageable

    Returns:
        bool: True if retention succeeded, False otherwise
    """
    print_header("Applying Retention Policy")

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Construct retention command
        retention_cmd = [
            "restic",
            "--repo",
            REPOSITORY,
            "forget",
            "--prune",
            "--keep-within",
            RETENTION_POLICY,  # Keep snapshots from last 7 days
        ]

        print(f"Applying retention policy: keeping snapshots within {RETENTION_POLICY}")

        # Run retention command
        result = run_command(retention_cmd, env=env)

        print(f"{Colors.GREEN}Retention policy applied successfully.{Colors.ENDC}")
        print(result.stdout)

        return True

    except Exception as e:
        print(f"{Colors.RED}Failed to apply retention policy: {str(e)}{Colors.ENDC}")
        return False


def list_snapshots() -> bool:
    """
    List all snapshots in the repository

    Returns:
        bool: True if listing succeeded, False otherwise
    """
    print_header("System Backup Snapshots")

    try:
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        # Run snapshots command
        result = run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)

        if result.stdout.strip():
            print(result.stdout)
        else:
            print(f"{Colors.YELLOW}No snapshots found in the repository.{Colors.ENDC}")

        return True

    except Exception as e:
        print(f"{Colors.RED}Failed to list snapshots: {str(e)}{Colors.ENDC}")
        return False


def main() -> None:
    """Main execution function"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check root privileges
    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check environment
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
        # Initialize repository
        if not initialize_repository():
            sys.exit(1)

        # Perform backup
        if not perform_backup():
            sys.exit(1)

        # Apply retention policy
        if not perform_retention():
            print(
                f"{Colors.YELLOW}Warning: Failed to apply retention policy, but backup was successful.{Colors.ENDC}"
            )

        # List snapshots
        list_snapshots()

        # Calculate elapsed time
        end_time = time.time()
        elapsed = end_time - start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Print final summary
        print_header("Backup Summary")
        print(f"{Colors.GREEN}System backup completed successfully.{Colors.ENDC}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Backup interrupted by user{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Backup failed: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
