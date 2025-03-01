#!/usr/bin/env python3
"""
VM Backup Script

Performs VM backups using restic to Backblaze B2 with robust progress tracking,
error handling, and clear user feedback. This script focuses exclusively on backing
up virtual machine configurations and storage.

Note: Run this script with root privileges.
"""

import atexit
import logging
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet
import shutil

# ------------------------------
# Configuration
# ------------------------------
HOSTNAME = socket.gethostname()

# Backblaze B2 and restic configuration
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository path for VM backups
REPOSITORY = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"

# VM backup paths and exclusion patterns
VM_BACKUP_PATHS: List[str] = ["/etc/libvirt", "/var/lib/libvirt"]
VM_BACKUP_EXCLUDES: List[str] = []  # No excludes by default

# Progress and retention settings
CHUNK_SIZE = 1024 * 1024  # 1MB
RETENTION_POLICY = "7d"   # Keep snapshots from last 7 days

# Logging configuration
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/vm_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Example Nord colors: #2E3440, #3B4252, #88C0D0, #8FBCBB, #BF616A
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
# Command Execution Helper
# ------------------------------
def run_command(
    cmd: List[str],
    env: Optional[dict] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Execute a system command with robust error handling."""
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
    # Add cleanup tasks if necessary.

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
    """Ensure that restic is installed."""
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
    """Verify that required environment variables are set."""
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

# ------------------------------
# Repository Management
# ------------------------------
def initialize_repository() -> bool:
    """
    Initialize the restic repository for VM backups if not already initialized.
    """
    print_header("Checking Repository")
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD,
        "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
        "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
    })
    try:
        try:
            run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)
            print_success("Repository already initialized.")
            return True
        except subprocess.CalledProcessError:
            print_warning("Repository not found. Initializing...")
            run_command(["restic", "--repo", REPOSITORY, "init"], env=env)
            print_success("Repository initialized successfully.")
            return True
    except Exception as e:
        print_error(f"Failed to initialize repository: {e}")
        return False

# ------------------------------
# Backup Size Estimation
# ------------------------------
def _format_size(bytes_val: int) -> str:
    """Convert a byte count into a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"

def estimate_backup_size() -> Tuple[int, int]:
    """
    Estimate the total backup size and file count for VM backups.

    Returns:
        Tuple[int, int]: (total_size_in_bytes, file_count)
    """
    print_section("Estimating Backup Size")
    total_size = 0
    file_count = 0
    # Use a Rich progress bar for scanning VM backup paths.
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning VM backup directories", total=len(VM_BACKUP_PATHS))
        for path in VM_BACKUP_PATHS:
            for root, dirs, files in os.walk(path):
                for file in files:
                    try:
                        total_size += os.stat(os.path.join(root, file)).st_size
                        file_count += 1
                    except (FileNotFoundError, PermissionError):
                        continue
            progress.advance(task)
    console.print(f"Found [bold]{file_count}[/bold] files totaling [bold]{_format_size(total_size)}[/bold]")
    return total_size, file_count

# ------------------------------
# Backup Execution
# ------------------------------
def perform_backup() -> bool:
    """
    Perform the VM backup using restic with interactive progress tracking.
    """
    print_header("Starting VM Backup")
    total_size, file_count = estimate_backup_size()
    console.print(f"Preparing to backup [bold]{file_count}[/bold] files ({_format_size(total_size)}) from VM configuration", style="#D8DEE9")
    
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD,
        "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
        "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
    })
    
    backup_cmd: List[str] = ["restic", "--repo", REPOSITORY, "backup"]
    backup_cmd.extend(VM_BACKUP_PATHS)
    for exclude in VM_BACKUP_EXCLUDES:
        backup_cmd.extend(["--exclude", exclude])
    backup_cmd.append("--verbose")
    
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("VM Backup Progress", total=total_size)
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
            # Try to parse file size from output; fallback to a fixed chunk increment.
            if "added to the repository" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.endswith("B") and i > 0 and parts[i - 1].isdigit():
                            bytes_str = parts[i - 1] + part
                            for unit, multiplier in {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}.items():
                                if unit in bytes_str:
                                    size = float(bytes_str.replace(unit, "").strip())
                                    progress.advance(task, int(size * multiplier))
                                    break
                except Exception:
                    progress.advance(task, CHUNK_SIZE)
            else:
                progress.advance(task, CHUNK_SIZE)
        process.wait()
        if process.returncode != 0:
            print_error(f"Backup failed with return code {process.returncode}.")
            return False
    print_success("VM backup completed successfully.")
    return True

def perform_retention() -> bool:
    """
    Apply the retention policy to keep the repository size manageable.
    """
    print_header("Applying Retention Policy")
    console.print(f"Keeping snapshots within [bold]{RETENTION_POLICY}[/bold]", style="#D8DEE9")
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD,
        "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
        "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
    })
    retention_cmd: List[str] = [
        "restic", "--repo", REPOSITORY, "forget", "--prune", "--keep-within", RETENTION_POLICY
    ]
    try:
        run_command(retention_cmd, env=env)
        print_success("Retention policy applied successfully.")
        return True
    except Exception as e:
        print_error(f"Failed to apply retention policy: {e}")
        return False

def list_snapshots() -> bool:
    """
    List all snapshots in the VM backup repository.
    """
    print_header("VM Backup Snapshots")
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD,
        "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
        "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
    })
    try:
        result = run_command(["restic", "--repo", REPOSITORY, "snapshots"], env=env)
        if result.stdout.strip():
            console.print(result.stdout.strip(), style="#D8DEE9")
        else:
            print_warning("No snapshots found in the repository.")
        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {e}")
        return False

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.option("--non-interactive", is_flag=True, help="Run without prompts")
@click.option("--retention", default=RETENTION_POLICY, help="Retention policy (e.g., 7d)")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(non_interactive: bool, retention: str, debug: bool) -> None:
    """VM Backup Script"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
        )
        logging.info(f"Logging initialized. Log file: {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")
    
    global RETENTION_POLICY
    RETENTION_POLICY = retention

    print_header("VM Backup Script")
    console.print(f"Hostname: [bold #D8DEE9]{HOSTNAME}[/bold #D8DEE9]")
    console.print(f"Platform: [bold #D8DEE9]{platform.platform()}[/bold #D8DEE9]")
    console.print(f"Backup Repository: [bold #D8DEE9]{REPOSITORY}[/bold #D8DEE9]")
    console.print(f"Backup Paths: [bold #D8DEE9]{', '.join(VM_BACKUP_PATHS)}[/bold #D8DEE9]")

    if not (check_root_privileges() and check_dependencies() and check_environment()):
        sys.exit(1)
    
    try:
        if not initialize_repository():
            sys.exit(1)
        if not perform_backup():
            sys.exit(1)
        if not perform_retention():
            print_warning("Failed to apply retention policy, but backup was successful.")
        list_snapshots()
        print_header("Backup Summary")
        console.print(f"[bold #8FBCBB]VM backup completed successfully.[/bold #8FBCBB]")
        console.print(f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")
    except KeyboardInterrupt:
        print_warning("Backup interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Backup failed: {e}")
        sys.exit(1)

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