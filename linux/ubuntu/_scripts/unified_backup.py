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
import logging
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

RETENTION_POLICY = "7d"  # e.g., keep snapshots from last 7 days

# Logging configuration
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Nord color palette examples: #2E3440, #3B4252, #88C0D0, #8FBCBB, #BF616A
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
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


def cleanup() -> None:
    print_step("Performing cleanup tasks...")
    # Add any necessary cleanup steps here.


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
    except Exception as e:
        print_warning(f"Could not determine restic version: {e}")
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
                return False
        return True
    elif service == "plex":
        for path in ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]:
            if not Path(path).exists():
                print_error(f"Path {path} not found. Is Plex installed?")
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


def setup_logging() -> None:
    """Setup logging to file and console."""
    try:
        log_dir_path = Path(LOG_DIR)
        log_dir_path.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
        )
        logging.info(f"Logging initialized. Log file: {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")
        logging.basicConfig(
            level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT
        )


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
    try:
        run_command(["restic", "--repo", repo, "snapshots"], env=env)
        print_success("Repository already initialized.")
        return True
    except subprocess.CalledProcessError:
        print_warning("Repository not found. Initializing...")
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing repository", total=None)
            try:
                run_command(["restic", "--repo", repo, "init"], env=env)
                progress.update(task, advance=1)
            except Exception as e:
                print_error(f"Failed to initialize repository: {e}")
                return False
        print_success("Repository initialized successfully.")
        return True
    except Exception as e:
        print_error(f"Error during repository initialization: {e}")
        return False


def estimate_backup_size(service: str) -> int:
    """
    Estimate the backup size for the given service.
    For the system, use an approximate calculation;
    for others, walk the paths and sum file sizes.
    """
    if service == "system":
        total, used, _ = get_disk_usage("/")
        estimated = int(used * 0.8)  # approximate estimate
        console.print(f"Estimated backup size: [bold]{estimated} bytes[/bold]")
        return estimated
    else:
        total_size = 0
        for path in BACKUP_CONFIGS[service]["paths"]:
            for root, _, files in os.walk(path):
                for file in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except Exception:
                        pass
        console.print(f"Calculated backup size: [bold]{total_size} bytes[/bold]")
        return total_size


def perform_backup(service: str) -> bool:
    """
    Execute the restic backup command for the given service,
    displaying real‑time progress using Rich.
    """
    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]
    print_header(f"Starting {config['name']} Backup")
    print_section("Calculating Backup Size")
    estimated_size = estimate_backup_size(service)
    if estimated_size == 0:
        print_warning(f"No files to backup for {config['name']}.")
        return False

    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    print_section("Executing Backup")
    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config["excludes"]:
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.append("--verbose")

    # Use Rich progress to track the backup process.
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
        while True:
            line = process.stdout.readline()
            if not line:
                break
            console.print(line.strip(), style="#D8DEE9")
            # Update progress (here we approximate by a fixed chunk size of 1MB)
            progress.advance(task, 1024 * 1024)
        process.wait()
        if process.returncode != 0:
            print_error(f"Backup failed with return code {process.returncode}.")
            return False
    print_success(f"{config['name']} backup completed successfully.")
    return True


def perform_retention(service: str) -> bool:
    """
    Apply the retention policy to the restic repository for the given service.
    """
    repo = REPOSITORIES[service]
    print_section("Applying Retention Policy")
    console.print(f"Keeping snapshots within [bold]{RETENTION_POLICY}[/bold]")
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
            run_command(retention_cmd, env=env)
            progress.update(task, advance=1)
        except Exception as e:
            print_error(f"Retention policy application failed: {e}")
            return False
    print_success("Retention policy applied successfully.")
    return True


def list_snapshots(service: str) -> bool:
    """
    List available snapshots from the repository in a formatted output.
    """
    repo = REPOSITORIES[service]
    print_section("Listing Snapshots")
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )
    try:
        result = run_command(["restic", "--repo", repo, "snapshots", "--json"], env=env)
        snapshots = json.loads(result.stdout)
        if snapshots:
            console.print(f"\n[bold]ID         Date                 Size[/bold]")
            console.print("-" * 40)
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
            console.print("-" * 40)
            console.print(f"Total snapshots: {len(snapshots)}")
        else:
            print_warning("No snapshots found.")
        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {e}")
        return False


def backup_service(service: str) -> bool:
    """
    Backup a specific service by checking prerequisites, initializing the repository,
    performing the backup, applying retention policy, and listing snapshots.
    """
    if service not in BACKUP_CONFIGS:
        print_error(f"Unknown service '{service}'.")
        return False
    config = BACKUP_CONFIGS[service]
    print_header(f"{config['name']} Backup")
    console.print(f"[#88C0D0]Description: [#D8DEE9]{config['description']}[/#D8DEE9]")
    console.print(f"[#88C0D0]Repository: [#D8DEE9]{REPOSITORIES[service]}[/#D8DEE9]")
    console.print(f"[#88C0D0]Paths: [#D8DEE9]{', '.join(config['paths'])}[/#D8DEE9]")
    console.print(
        f"[#88C0D0]Excludes: [#D8DEE9]{len(config['excludes'])} patterns[/#D8DEE9]"
    )
    if not check_service_paths(service):
        return False
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
    if not initialize_repository(service):
        return False
    start_time = time.time()
    if not perform_backup(service):
        return False
    if not perform_retention(service):
        print_warning("Retention policy application failed.")
    list_snapshots(service)
    elapsed = time.time() - start_time
    print_section("Service Backup Summary")
    console.print(
        f"[bold #8FBCBB]Backup completed in {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s[/bold #8FBCBB]"
    )
    return True


def backup_all_services() -> Dict[str, bool]:
    """
    Backup all configured services sequentially and report an overall summary.
    """
    results: Dict[str, bool] = {}
    print_header("Starting Backup for All Services")
    start_time = time.time()
    for service in BACKUP_CONFIGS:
        print_header(f"Service: {BACKUP_CONFIGS[service]['name']}")
        results[service] = backup_service(service)
    elapsed = time.time() - start_time
    print_header("Overall Backup Summary")
    console.print(
        f"[bold #8FBCBB]Total elapsed time: {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s[/bold #8FBCBB]"
    )
    return results


# ------------------------------
# Main CLI Entry Point with click
# ------------------------------
@click.command()
@click.option(
    "--service",
    type=click.Choice(list(BACKUP_CONFIGS.keys()) + ["all"]),
    help="Service to backup (system, vm, plex, or all)",
)
@click.option(
    "--non-interactive", is_flag=True, help="Run without prompts (requires --service)"
)
@click.option(
    "--retention", default=RETENTION_POLICY, help="Retention policy (e.g., 7d)"
)
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(
    service: Optional[str], non_interactive: bool, retention: str, debug: bool
) -> None:
    """Enhanced Unified Restic Backup Script"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    setup_logging()
    global RETENTION_POLICY
    RETENTION_POLICY = retention

    print_header("Unified Restic Backup Script")
    console.print(f"Hostname: [bold #D8DEE9]{HOSTNAME}[/bold #D8DEE9]")
    console.print(f"Platform: [bold #D8DEE9]{platform.platform()}[/bold #D8DEE9]")
    console.print(f"Backup bucket: [bold #D8DEE9]{B2_BUCKET}[/bold #D8DEE9]")
    console.print(f"Retention policy: [bold #D8DEE9]{RETENTION_POLICY}[/bold #D8DEE9]")
    console.print(
        f"Available services: [bold #D8DEE9]{', '.join(BACKUP_CONFIGS.keys())}[/bold #D8DEE9]"
    )

    if not (check_root_privileges() and check_dependencies() and check_environment()):
        sys.exit(1)

    if non_interactive and service:
        start_time = time.time()
        if service == "all":
            results = backup_all_services()
            if not all(results.values()):
                sys.exit(1)
        else:
            if not backup_service(service):
                sys.exit(1)
        elapsed = time.time() - start_time
    else:
        print_section("Select a service to backup:")
        services_list = list(BACKUP_CONFIGS.keys())
        for i, svc in enumerate(services_list, 1):
            conf = BACKUP_CONFIGS[svc]
            console.print(
                f"{i}. {conf['name']} - {conf['description']}", style="#D8DEE9"
            )
        console.print(f"{len(services_list) + 1}. All Services", style="#D8DEE9")
        try:
            choice = int(click.prompt("Enter your choice", type=int))
            start_time = time.time()
            if choice <= len(services_list):
                if not backup_service(services_list[choice - 1]):
                    sys.exit(1)
            else:
                results = backup_all_services()
                if not all(results.values()):
                    sys.exit(1)
            elapsed = time.time() - start_time
        except (ValueError, KeyboardInterrupt):
            print_error("Invalid input or interrupted. Exiting.")
            sys.exit(1)

    print_header("Final Backup Summary")
    console.print(
        f"[bold #8FBCBB]Backup completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #8FBCBB]"
    )
    console.print(
        f"Total elapsed time: {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s",
        style="#8FBCBB",
    )
    console.print(f"Log file: [bold #D8DEE9]{LOG_FILE}[/bold #D8DEE9]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Backup interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
