#!/usr/bin/env python3
"""
Enhanced Unified Restic Backup Script

This script performs backups for multiple system components:
  • System (root filesystem)
  • Virtual Machines (libvirt)
  • Plex Media Server

It uses restic to create incremental backups to Backblaze B2 storage with
robust progress tracking, error handling, and clear status reporting.
Designed for Ubuntu/Linux systems, run this script with root privileges.
"""

import atexit
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.spinner import Spinner
import pyfiglet
import shutil

# ------------------------------
# Configuration
# ------------------------------
HOSTNAME = socket.gethostname()

# Restic and Backblaze B2 configuration
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository paths per service
REPOSITORIES: Dict[str, str] = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup configuration per service
BACKUP_CONFIGS: Dict[str, Dict] = {
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

# Default retention policy
RETENTION_POLICY = "7d"  # e.g., keep snapshots from last 7 days

# Logging configuration
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ------------------------------
# Nord-Themed Styles & Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet."""
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
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a command with robust error handling."""
    try:
        print_step(f"Running command: {' '.join(cmd)}")
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
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
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
def signal_handler(sig, frame) -> None:
    """Handle signals like SIGINT and SIGTERM."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_step("Performing cleanup tasks...")
    # Add any necessary cleanup steps here.


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    """Setup logging to file."""
    try:
        log_dir_path = Path(LOG_DIR)
        log_dir_path.mkdir(parents=True, exist_ok=True)

        with open(LOG_FILE, "a") as log_file:
            log_file.write(
                f"\n--- Backup session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )

        print_success(f"Logging to {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")


def log_message(message: str, level: str = "INFO") -> None:
    """Log a message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{timestamp} - {level} - {message}\n")
    except Exception:
        pass  # Silently fail if logging isn't available


# ------------------------------
# Helper Functions
# ------------------------------
def check_root_privileges() -> bool:
    """Verify that the script is run as root."""
    if os.geteuid() != 0:
        print_error("This script must be run as root (e.g., using sudo).")
        return False
    return True


def check_dependencies() -> bool:
    """Ensure restic is installed."""
    if not shutil.which("restic"):
        print_error("Restic is not installed. Please install restic first.")
        return False
    try:
        result = run_command(["restic", "version"])
        version = result.stdout.strip()
        print_success(f"Restic version: {version}")
        log_message(f"Restic version: {version}")
    except Exception as e:
        print_warning(f"Could not determine restic version: {e}")
        log_message(f"Could not determine restic version: {e}", "WARNING")
    return True


def check_environment() -> bool:
    """Ensure that necessary environment variables are set."""
    missing_vars = []
    if not B2_ACCOUNT_ID:
        missing_vars.append("B2_ACCOUNT_ID")
    if not B2_ACCOUNT_KEY:
        missing_vars.append("B2_ACCOUNT_KEY")
    if not RESTIC_PASSWORD:
        missing_vars.append("RESTIC_PASSWORD")

    if missing_vars:
        print_error(f"Missing environment variables: {', '.join(missing_vars)}")
        log_message(
            f"Missing environment variables: {', '.join(missing_vars)}", "ERROR"
        )
        return False
    return True


def check_service_paths(service: str) -> bool:
    """Check that required paths exist for the given service."""
    if service == "system":
        return True
    elif service == "vm":
        for path in ["/etc/libvirt", "/var/lib/libvirt"]:
            if not Path(path).exists():
                print_error(f"Path {path} not found. Is libvirt installed?")
                log_message(f"Path {path} not found for VM backup", "ERROR")
                return False
        return True
    elif service == "plex":
        for path in ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]:
            if not Path(path).exists():
                print_error(f"Path {path} not found. Is Plex installed?")
                log_message(f"Path {path} not found for Plex backup", "ERROR")
                return False
        return True
    return False


def get_disk_usage(path: str = "/") -> Tuple[int, int, float]:
    """Return total, used, and percentage used for the given path."""
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bfree * stat.f_frsize
    used = total - free
    percent = (used / total) * 100 if total > 0 else 0
    return total, used, percent


def format_bytes(size: int) -> str:
    """Convert bytes to a human-readable format."""
    power = 2**10
    n = 0
    power_labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def format_time(seconds: float) -> str:
    """Format seconds into hours, minutes, seconds."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"


# ------------------------------
# Repository and Backup Functions
# ------------------------------
def initialize_repository(service: str) -> bool:
    """
    Initialize the restic repository for the given service if not already initialized.
    """
    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    print_section("Repository Initialization")
    print_step(f"Checking repository: {repo}")
    log_message(f"Checking repository for {service}: {repo}")

    try:
        # Try to access the repository
        with console.status("[bold #81A1C1]Checking repository...", spinner="dots"):
            run_command(["restic", "--repo", repo, "snapshots"], env=env)
        print_success("Repository already initialized.")
        log_message(f"Repository for {service} already initialized")
        return True
    except subprocess.CalledProcessError:
        # Repository doesn't exist, initialize it
        print_warning("Repository not found. Initializing...")
        log_message(f"Repository for {service} not found, initializing")
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing repository", total=None)
            try:
                run_command(["restic", "--repo", repo, "init"], env=env)
                progress.update(task, completed=True)
                print_success("Repository initialized successfully.")
                log_message(f"Repository for {service} initialized successfully")
                return True
            except Exception as e:
                print_error(f"Failed to initialize repository: {e}")
                log_message(
                    f"Failed to initialize repository for {service}: {e}", "ERROR"
                )
                return False
    except Exception as e:
        print_error(f"Error during repository initialization: {e}")
        log_message(
            f"Error during repository initialization for {service}: {e}", "ERROR"
        )
        return False


def estimate_backup_size(service: str) -> int:
    """
    Estimate the backup size for the given service.
    For the system, use an approximate calculation;
    for others, walk the paths and sum file sizes.
    """
    print_section("Backup Size Estimation")
    print_step(f"Estimating backup size for {BACKUP_CONFIGS[service]['name']}...")

    if service == "system":
        total, used, _ = get_disk_usage("/")
        estimated = int(used * 0.8)  # approximate estimate
        print_success(f"Estimated backup size: {format_bytes(estimated)}")
        log_message(f"Estimated system backup size: {format_bytes(estimated)}")
        return estimated
    else:
        total_size = 0
        paths = BACKUP_CONFIGS[service]["paths"]

        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Calculating size for {len(paths)} paths", total=len(paths)
            )

            for path in paths:
                path_size = 0
                try:
                    for root, _, files in os.walk(path):
                        for file in files:
                            try:
                                path_size += os.path.getsize(os.path.join(root, file))
                            except Exception:
                                pass
                    total_size += path_size
                    progress.advance(task)
                except Exception as e:
                    print_warning(f"Error calculating size for {path}: {e}")

        print_success(f"Calculated backup size: {format_bytes(total_size)}")
        log_message(f"Calculated backup size for {service}: {format_bytes(total_size)}")
        return total_size


def perform_backup(service: str) -> bool:
    """
    Execute the restic backup command for the given service,
    displaying real‑time progress using Rich.
    """
    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    print_section("Backup Execution")
    log_message(f"Starting backup for {config['name']}")

    # Estimate backup size
    estimated_size = estimate_backup_size(service)
    if estimated_size == 0:
        print_warning(f"No files to backup for {config['name']}.")
        log_message(f"No files to backup for {config['name']}", "WARNING")
        return False

    # Prepare environment
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    # Prepare backup command
    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config["excludes"]:
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.append("--verbose")

    print_step(f"Starting backup of {config['name']}...")
    print_step(f"Paths: {', '.join(config['paths'])}")
    print_step(f"Excludes: {len(config['excludes'])} patterns")
    log_message(f"Executing backup command for {service}")

    # Execute backup with progress tracking
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running backup", total=estimated_size)

        process = subprocess.Popen(
            backup_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Track backup progress
        bytes_processed = 0
        increment = max(
            1024 * 1024, estimated_size // 100
        )  # 1MB or 1% of total, whichever is larger

        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Update the console with backup output
            console.print(line.strip(), style="#D8DEE9")

            # Look for progress indicators in output
            if "Files:" in line or "Added" in line:
                # Update progress bar
                bytes_processed += increment
                progress.update(task, completed=min(bytes_processed, estimated_size))

        process.wait()
        if process.returncode != 0:
            print_error(f"Backup failed with return code {process.returncode}.")
            log_message(
                f"Backup failed for {service} with return code {process.returncode}",
                "ERROR",
            )
            return False

    print_success(f"{config['name']} backup completed successfully.")
    log_message(f"{config['name']} backup completed successfully")
    return True


def perform_retention(service: str) -> bool:
    """
    Apply the retention policy to the restic repository for the given service.
    """
    repo = REPOSITORIES[service]
    print_section("Retention Policy Application")
    print_step(f"Applying retention policy: keep snapshots within {RETENTION_POLICY}")
    log_message(f"Applying retention policy for {service}: {RETENTION_POLICY}")

    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    retention_cmd = [
        "restic",
        "--repo",
        repo,
        "forget",
        "--prune",
        "--keep-within",
        RETENTION_POLICY,
    ]

    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Pruning snapshots", total=None)
        try:
            result = run_command(retention_cmd, env=env)
            progress.update(task, completed=True)

            # Print the output for visibility
            for line in result.stdout.splitlines():
                if any(
                    keyword in line for keyword in ["keeping", "removing", "unused"]
                ):
                    console.print(line, style="#D8DEE9")

            print_success("Retention policy applied successfully.")
            log_message("Retention policy applied successfully")
            return True
        except Exception as e:
            print_error(f"Retention policy application failed: {e}")
            log_message(f"Retention policy application failed: {e}", "ERROR")
            return False


def list_snapshots(service: str) -> bool:
    """
    List available snapshots from the repository in a formatted output.
    """
    repo = REPOSITORIES[service]
    print_section("Available Snapshots")
    log_message(f"Listing snapshots for {service}")

    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    try:
        with console.status("[bold #81A1C1]Retrieving snapshots...", spinner="dots"):
            result = run_command(
                ["restic", "--repo", repo, "snapshots", "--json"], env=env
            )

        snapshots = json.loads(result.stdout)
        if snapshots:
            console.print(
                "\n[bold #D8DEE9]ID         Date                 Size[/bold #D8DEE9]"
            )
            console.print("-" * 40, style="#D8DEE9")

            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

                size = snap.get("stats", {}).get("total_size_formatted", "-")
                console.print(f"{sid:<10} {time_str:<20} {size:<10}", style="#D8DEE9")

            console.print("-" * 40, style="#D8DEE9")
            console.print(f"Total snapshots: {len(snapshots)}", style="#D8DEE9")
            log_message(f"Found {len(snapshots)} snapshots for {service}")
        else:
            print_warning("No snapshots found.")
            log_message("No snapshots found", "WARNING")

        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {e}")
        log_message(f"Failed to list snapshots: {e}", "ERROR")
        return False


def backup_service(service: str) -> bool:
    """
    Backup a specific service by checking prerequisites, initializing the repository,
    performing the backup, applying retention policy, and listing snapshots.
    """
    if service not in BACKUP_CONFIGS:
        print_error(f"Unknown service '{service}'.")
        log_message(f"Unknown service '{service}'", "ERROR")
        return False

    config = BACKUP_CONFIGS[service]
    print_header(f"{config['name']} Backup")
    log_message(f"Starting backup process for {config['name']}")

    # Display service information
    console.print(f"[#88C0D0]Description: [#D8DEE9]{config['description']}[/#D8DEE9]")
    console.print(f"[#88C0D0]Repository: [#D8DEE9]{REPOSITORIES[service]}[/#D8DEE9]")
    console.print(f"[#88C0D0]Paths: [#D8DEE9]{', '.join(config['paths'])}[/#D8DEE9]")
    console.print(
        f"[#88C0D0]Excludes: [#D8DEE9]{len(config['excludes'])} patterns[/#D8DEE9]"
    )

    # Check service-specific paths
    if not check_service_paths(service):
        return False

    # Check service status if applicable
    if service == "vm":
        status = run_command(
            ["systemctl", "is-active", "libvirtd"], check=False
        ).stdout.strip()
        console.print(f"[#88C0D0]libvirtd Status: [#D8DEE9]{status}[/#D8DEE9]")
    elif service == "plex":
        status = run_command(
            ["systemctl", "is-active", "plexmediaserver"], check=False
        ).stdout.strip()
        console.print(f"[#88C0D0]Plex Status: [#D8DEE9]{status}[/#D8DEE9]")

    # Initialize repository
    if not initialize_repository(service):
        return False

    # Start backup process
    start_time = time.time()
    backup_success = perform_backup(service)

    if not backup_success:
        return False

    # Apply retention policy
    if not perform_retention(service):
        print_warning("Retention policy application failed.")
        log_message("Retention policy application failed", "WARNING")

    # List available snapshots
    list_snapshots(service)

    # Display summary
    elapsed = time.time() - start_time
    print_section("Service Backup Summary")
    print_success(f"Backup completed in {format_time(elapsed)}")
    log_message(f"Backup for {config['name']} completed in {format_time(elapsed)}")

    return True


def backup_all_services() -> Dict[str, bool]:
    """
    Backup all configured services sequentially and report an overall summary.
    """
    results: Dict[str, bool] = {}
    print_header("Starting Backup for All Services")
    log_message("Starting backup for all services")

    start_time = time.time()

    for service in BACKUP_CONFIGS:
        print_header(f"Service: {BACKUP_CONFIGS[service]['name']}")
        results[service] = backup_service(service)

    elapsed = time.time() - start_time

    print_header("Overall Backup Summary")
    console.print(
        f"[bold #8FBCBB]Total elapsed time: {format_time(elapsed)}[/bold #8FBCBB]"
    )

    # Print individual results
    for service, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        color = "#8FBCBB" if success else "#BF616A"
        console.print(
            f"{BACKUP_CONFIGS[service]['name']}: [bold {color}]{status}[/bold {color}]"
        )

    # Log summary
    successful = sum(1 for success in results.values() if success)
    log_message(
        f"Completed backup of all services: {successful}/{len(results)} successful, elapsed time: {format_time(elapsed)}"
    )

    return results


# ------------------------------
# Interactive Menu Functions
# ------------------------------
def show_system_info() -> None:
    """Display system information."""
    print_section("System Information")

    # Get system info
    console.print(f"[#88C0D0]Hostname: [#D8DEE9]{HOSTNAME}[/#D8DEE9]")
    console.print(f"[#88C0D0]Platform: [#D8DEE9]{platform.platform()}[/#D8DEE9]")
    console.print(
        f"[#88C0D0]Python Version: [#D8DEE9]{platform.python_version()}[/#D8DEE9]"
    )

    # Get disk usage
    total, used, percent = get_disk_usage("/")
    console.print(
        f"[#88C0D0]Disk Usage: [#D8DEE9]{format_bytes(used)}/{format_bytes(total)} ({percent:.1f}%)[/#D8DEE9]"
    )

    # Display B2 configuration
    console.print(f"[#88C0D0]B2 Bucket: [#D8DEE9]{B2_BUCKET}[/#D8DEE9]")
    console.print(f"[#88C0D0]Retention Policy: [#D8DEE9]{RETENTION_POLICY}[/#D8DEE9]")

    # Display available services
    console.print(f"[#88C0D0]Available Backup Services:[/#88C0D0]")
    for key, config in BACKUP_CONFIGS.items():
        console.print(
            f"  • [#D8DEE9]{config['name']} - {config['description']}[/#D8DEE9]"
        )


def configure_retention() -> None:
    """Configure retention policy."""
    global RETENTION_POLICY

    print_section("Configure Retention Policy")
    console.print(
        f"Current retention policy: [bold #D8DEE9]{RETENTION_POLICY}[/bold #D8DEE9]"
    )
    console.print("Retention policy controls how long snapshots are kept.")
    console.print(
        "Examples: '7d' (7 days), '4w' (4 weeks), '6m' (6 months), '1y' (1 year)"
    )

    new_policy = input(
        "Enter new retention policy (or press Enter to keep current): "
    ).strip()

    if new_policy:
        RETENTION_POLICY = new_policy
        print_success(f"Retention policy updated to: {RETENTION_POLICY}")
        log_message(f"Retention policy updated to: {RETENTION_POLICY}")
    else:
        print_step("Retention policy unchanged.")


def interactive_menu() -> None:
    """Display and handle the interactive menu."""
    while True:
        print_header("Backup Menu")
        console.print("1. System Information")
        console.print("2. Configure Retention Policy")
        console.print("3. Backup System")
        console.print("4. Backup Virtual Machines")
        console.print("5. Backup Plex Media Server")
        console.print("6. Backup All Services")
        console.print("7. List Snapshots")
        console.print("8. Exit")

        choice = input("\nSelect an option (1-8): ").strip()

        if choice == "1":
            show_system_info()
        elif choice == "2":
            configure_retention()
        elif choice == "3":
            backup_service("system")
        elif choice == "4":
            backup_service("vm")
        elif choice == "5":
            backup_service("plex")
        elif choice == "6":
            backup_all_services()
        elif choice == "7":
            list_snapshots_menu()
        elif choice == "8":
            print_header("Exiting")
            break
        else:
            print_warning("Invalid selection, please try again.")

        input("\nPress Enter to return to the menu...")


def list_snapshots_menu() -> None:
    """Menu for listing snapshots from different services."""
    print_header("List Snapshots")
    console.print("1. System Snapshots")
    console.print("2. Virtual Machines Snapshots")
    console.print("3. Plex Media Server Snapshots")
    console.print("4. Return to Main Menu")

    choice = input("\nSelect an option (1-4): ").strip()

    if choice == "1":
        list_snapshots("system")
    elif choice == "2":
        list_snapshots("vm")
    elif choice == "3":
        list_snapshots("plex")
    elif choice == "4":
        return
    else:
        print_warning("Invalid selection.")


def main() -> None:
    """Main function to run the script."""
    # Setup signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_header("Unified Restic Backup")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )

    # Setup logging
    setup_logging()

    # Check prerequisites
    if not check_root_privileges():
        sys.exit(1)

    if not check_dependencies():
        sys.exit(1)

    if not check_environment():
        sys.exit(1)

    # Display system information
    show_system_info()

    # Start interactive menu
    interactive_menu()

    print_success("Backup operations completed.")
    log_message("Script execution completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Backup interrupted by user.")
        log_message("Backup interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        import traceback

        traceback.print_exc()
        sys.exit(1)
