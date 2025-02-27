#!/usr/bin/env python3
"""
Unified Restic Backup Script

This script performs comprehensive backups of multiple system components:
  • System (root filesystem)
  • Virtual Machines (libvirt)
  • Plex Media Server

It uses restic to create efficient, incremental backups to Backblaze B2 storage with
detailed progress tracking, robust error handling, and clear status reporting.
The script handles each service independently, with appropriate exclusion patterns
and repository organization.

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
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository paths
REPOSITORIES = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup sources and excludes
BACKUP_CONFIGS = {
    "system": {
        "paths": ["/"],
        "excludes": [
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
        ],
        "name": "System",
        "description": "Root filesystem backup",
    },
    "vm": {
        "paths": ["/etc/libvirt", "/var/lib/libvirt"],
        "excludes": [],
        "name": "Virtual Machines",
        "description": "VM configuration and storage",
    },
    "plex": {
        "paths": ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"],
        "excludes": [
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
        ],
        "name": "Plex Media Server",
        "description": "Plex configuration and data",
    },
}

# Progress tracking settings
PROGRESS_WIDTH = 50
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
RETENTION_POLICY = "7d"  # Keep snapshots from last 7 days
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
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


#####################################
# Helper Functions
#####################################


def format_size(bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """Print formatted section header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {message}{Colors.ENDC}")


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


def check_service_status(service_name: str) -> Tuple[bool, str]:
    """
    Check if a service is running

    Args:
        service_name: Name of the service to check

    Returns:
        Tuple[bool, str]: (is_running, status_message)
    """
    try:
        result = run_command(["systemctl", "is-active", service_name], check=False)
        is_running = result.returncode == 0
        status = result.stdout.strip()

        if is_running:
            return True, "running"
        else:
            return False, status
    except Exception as e:
        return False, str(e)


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """Check if script is run with root privileges"""
    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}"
        )
        return False
    return True


def check_dependencies() -> bool:
    """Check if required tools are installed"""
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


def check_service_paths(service: str) -> bool:
    """
    Check if required paths for a service exist

    Args:
        service: Service name to check paths for

    Returns:
        bool: True if all critical paths exist, False otherwise
    """
    config = BACKUP_CONFIGS[service]

    if service == "system":
        # System backup always has valid root path
        return True

    elif service == "vm":
        if not os.path.exists("/etc/libvirt") or not os.path.exists("/var/lib/libvirt"):
            print(
                f"{Colors.RED}Error: VM directories not found. Is libvirt installed?{Colors.ENDC}"
            )
            return False
        return True

    elif service == "plex":
        if not os.path.exists("/var/lib/plexmediaserver"):
            print(
                f"{Colors.RED}Error: Plex Media Server installation not found.{Colors.ENDC}"
            )
            return False
        return True

    return False


#####################################
# Repository Management Functions
#####################################


def initialize_repository(service: str) -> bool:
    """
    Initialize repository for a service if not already initialized

    Args:
        service: Service name to initialize repository for

    Returns:
        bool: True if repository is initialized successfully, False otherwise
    """
    repo = REPOSITORIES[service]

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
            run_command(["restic", "--repo", repo, "snapshots"], env=env)
            print(f"{Colors.GREEN}Repository already initialized.{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError:
            # Repository doesn't exist, initialize it
            print("Repository not found. Initializing...")
            run_command(["restic", "--repo", repo, "init"], env=env)
            print(f"{Colors.GREEN}Repository initialized successfully.{Colors.ENDC}")
            return True

    except Exception as e:
        print(f"{Colors.RED}Failed to initialize repository: {e}{Colors.ENDC}")
        return False


#####################################
# Size Estimation Functions
#####################################


def estimate_system_backup_size() -> int:
    """
    Estimate the size of a system backup by sampling key directories

    Returns:
        int: Estimated backup size in bytes
    """
    # Get total system disk usage
    total, used, percent = get_disk_usage("/")

    # Sample key directories to estimate what percentage will be backed up
    excluded_size = 0
    excludes = BACKUP_CONFIGS["system"]["excludes"]

    for exclude in excludes:
        if "*" not in exclude:
            # This is a directory exclusion
            path = exclude.rstrip("/*")
            try:
                if os.path.exists(path):
                    dir_size = 0
                    try:
                        dir_size = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, _, filenames in os.walk(path)
                            for filename in filenames
                        )
                    except (PermissionError, OSError):
                        pass
                    excluded_size += dir_size
            except (PermissionError, OSError):
                pass

    # Estimate: Used space minus excluded size, with safety margin
    estimated_size = max(used - excluded_size, 0)

    # Apply a compression factor (restic uses compression)
    compression_factor = 0.7  # Assume 30% compression ratio
    estimated_backup_size = int(estimated_size * compression_factor)

    return estimated_backup_size


def calculate_directory_size(
    paths: List[str], excludes: List[str] = None
) -> Tuple[int, int]:
    """
    Calculate the total size and file count for given paths with exclusions

    Args:
        paths: List of paths to calculate size for
        excludes: List of exclude patterns

    Returns:
        Tuple[int, int]: (total_size_bytes, file_count)
    """
    total_size = 0
    file_count = 0

    # Create a list of excluded path prefixes
    exclude_prefixes = []
    if excludes:
        exclude_prefixes = [
            exclude.rstrip("*") for exclude in excludes if "*" in exclude
        ]

    # Process each backup path
    for path in paths:
        # Skip if path doesn't exist
        if not os.path.exists(path):
            print(
                f"{Colors.YELLOW}Warning: Path {path} does not exist, skipping.{Colors.ENDC}"
            )
            continue

        for root, dirs, files in os.walk(path):
            # Check if this directory should be excluded
            skip = False
            for exclude_prefix in exclude_prefixes:
                if root.startswith(exclude_prefix):
                    skip = True
                    break

            if skip:
                continue

            # Process files in this directory
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    # Check if file matches any exclude pattern
                    file_skip = False
                    if excludes:
                        for exclude in excludes:
                            if "*." in exclude:
                                ext = exclude.split("*.")[-1]
                                if file.endswith(f".{ext}"):
                                    file_skip = True
                                    break

                    if file_skip:
                        continue

                    stat = os.stat(file_path)
                    total_size += stat.st_size
                    file_count += 1
                except (FileNotFoundError, PermissionError, OSError):
                    pass

    return total_size, file_count


#####################################
# Backup Execution Functions
#####################################


def perform_backup(service: str) -> bool:
    """
    Perform a backup for a specific service

    Args:
        service: Service name to backup

    Returns:
        bool: True if backup succeeded, False otherwise
    """
    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    print_header(f"Starting {config['name']} Backup")

    try:
        # Estimate backup size for progress tracking
        print_section("Calculating Backup Size")

        if service == "system":
            estimated_size = estimate_system_backup_size()
            file_count = 0  # We don't count files for system backup
            print(f"Estimated backup size: {format_size(estimated_size)}")
        else:
            total_size, file_count = calculate_directory_size(
                config["paths"], config["excludes"]
            )
            estimated_size = total_size
            print(f"Found {file_count} files totaling {format_size(estimated_size)}")

        if estimated_size == 0:
            print(
                f"{Colors.YELLOW}Warning: No files found to backup for {config['name']}.{Colors.ENDC}"
            )
            return False

        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": RESTIC_PASSWORD,
                "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
                "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
            }
        )

        print_section("Executing Backup")

        # Start a progress monitor
        progress = ProgressBar(estimated_size, desc="Backup progress")

        # Construct backup command
        backup_cmd = ["restic", "--repo", repo, "backup"]

        # Add paths
        backup_cmd.extend(config["paths"])

        # Add excludes
        for exclude in config["excludes"]:
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

        print(
            f"{Colors.GREEN}{config['name']} backup completed successfully.{Colors.ENDC}"
        )
        return True

    except Exception as e:
        print(f"{Colors.RED}Backup failed: {str(e)}{Colors.ENDC}")
        return False


def perform_retention(service: str) -> bool:
    """
    Apply retention policy to keep the repository size manageable

    Args:
        service: Service name to apply retention policy for

    Returns:
        bool: True if retention succeeded, False otherwise
    """
    repo = REPOSITORIES[service]
    config = BACKUP_CONFIGS[service]

    print_section("Applying Retention Policy")

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
            repo,
            "forget",
            "--prune",
            "--keep-within",
            RETENTION_POLICY,  # Keep snapshots from last 7 days
        ]

        print(f"Applying retention policy: keeping snapshots within {RETENTION_POLICY}")

        # Run retention command
        result = run_command(retention_cmd, env=env)

        print(f"{Colors.GREEN}Retention policy applied successfully.{Colors.ENDC}")

        return True

    except Exception as e:
        print(f"{Colors.RED}Failed to apply retention policy: {str(e)}{Colors.ENDC}")
        return False


def list_snapshots(service: str) -> bool:
    """
    List all snapshots in the repository for a service

    Args:
        service: Service name to list snapshots for

    Returns:
        bool: True if listing succeeded, False otherwise
    """
    repo = REPOSITORIES[service]
    config = BACKUP_CONFIGS[service]

    print_section("Listing Snapshots")

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
        result = run_command(["restic", "--repo", repo, "snapshots"], env=env)

        if result.stdout.strip():
            print(result.stdout)
        else:
            print(f"{Colors.YELLOW}No snapshots found in the repository.{Colors.ENDC}")

        return True

    except Exception as e:
        print(f"{Colors.RED}Failed to list snapshots: {str(e)}{Colors.ENDC}")
        return False


#####################################
# Service-Specific Functions
#####################################


def backup_service(service: str) -> bool:
    """
    Execute the full backup workflow for a specific service

    Args:
        service: Service name to backup

    Returns:
        bool: True if all steps succeeded, False otherwise
    """
    if service not in BACKUP_CONFIGS:
        print(f"{Colors.RED}Error: Unknown service '{service}'.{Colors.ENDC}")
        return False

    config = BACKUP_CONFIGS[service]

    print_header(f"Processing {config['name']} Backup")
    print(f"Description: {config['description']}")
    print(f"Repository: {REPOSITORIES[service]}")
    print(f"Paths: {', '.join(config['paths'])}")
    print(f"Excludes: {len(config['excludes'])} patterns")

    # Check service-specific dependencies
    if not check_service_paths(service):
        return False

    # Check service status if applicable
    if service == "vm":
        vm_status, status_text = check_service_status("libvirtd")
        print(f"libvirtd Service Status: {status_text}")
    elif service == "plex":
        plex_status, status_text = check_service_status("plexmediaserver")
        print(f"Plex Service Status: {status_text}")

    # Initialize repository
    if not initialize_repository(service):
        return False

    # Perform backup
    if not perform_backup(service):
        return False

    # Apply retention policy
    if not perform_retention(service):
        print(
            f"{Colors.YELLOW}Warning: Failed to apply retention policy, but backup was successful.{Colors.ENDC}"
        )

    # List snapshots
    list_snapshots(service)

    return True


def backup_all_services() -> Dict[str, bool]:
    """
    Backup all configured services

    Returns:
        Dict[str, bool]: Results of each service backup
    """
    results = {}

    for service in BACKUP_CONFIGS:
        print_header(f"--- {BACKUP_CONFIGS[service]['name']} Backup ---")
        results[service] = backup_service(service)

    return results


#####################################
# Main Function
#####################################


def main() -> None:
    """Main execution function"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check root privileges
    if not check_root_privileges():
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check environment
    if not check_environment():
        sys.exit(1)

    print_header("Unified Restic Backup Script")
    print(f"Hostname: {HOSTNAME}")
    print(f"Platform: {platform.platform()}")
    print(f"Backup bucket: {B2_BUCKET}")
    print(f"Retention policy: {RETENTION_POLICY}")
    print(f"Available services: {', '.join(BACKUP_CONFIGS.keys())}")

    # Prompt for service selection
    print(f"\nSelect service to backup:")
    for i, service in enumerate(BACKUP_CONFIGS.keys(), 1):
        config = BACKUP_CONFIGS[service]
        print(f"{i}. {config['name']} - {config['description']}")
    print(f"{len(BACKUP_CONFIGS) + 1}. All Services")

    try:
        choice = input("\nEnter your choice (1-4): ")
        choice = int(choice.strip())

        services = list(BACKUP_CONFIGS.keys())

        if choice < 1 or choice > len(services) + 1:
            print(f"{Colors.RED}Invalid choice. Exiting.{Colors.ENDC}")
            sys.exit(1)

        start_time = time.time()

        if choice <= len(services):
            # Single service backup
            service = services[choice - 1]
            success = backup_service(service)

            if not success:
                print(
                    f"{Colors.RED}Backup of {BACKUP_CONFIGS[service]['name']} failed.{Colors.ENDC}"
                )
                sys.exit(1)
        else:
            # All services
            results = backup_all_services()

            # Check for failures
            failures = [service for service, success in results.items() if not success]

            if failures:
                print_header("Backup Summary - FAILURES DETECTED")
                print(
                    f"{Colors.RED}The following services failed to backup:{Colors.ENDC}"
                )
                for service in failures:
                    print(f"  • {BACKUP_CONFIGS[service]['name']}")
                sys.exit(1)

        # Calculate elapsed time
        end_time = time.time()
        elapsed = end_time - start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Print final summary
        print_header("Backup Summary")
        print(f"{Colors.GREEN}Backup completed successfully.{Colors.ENDC}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Backup interrupted by user{Colors.ENDC}")
        sys.exit(130)
    except ValueError:
        print(f"{Colors.RED}Invalid input. Please enter a number.{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Backup failed: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
