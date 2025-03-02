#!/usr/bin/env python3
"""
Enhanced Interactive Restore Script
-------------------------------------
This utility restores files for VM and Plex data from previously created restic backups.
It provides a beautiful, Nord‑themed interactive menu to select and execute restore tasks.
The script handles dependencies, manages services, and provides detailed progress feedback.

Features:
  • Restores VM Libvirt configurations from /var and /etc
  • Restores Plex Media Server data
  • Validates and compares files during restoration
  • Manages related services during restore process
  • Provides detailed progress and status information

Note: Run this script with root privileges.
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

import pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

# ====================================================
# Configuration & Constants
# ====================================================

# Restore task definitions: source path, target path, and associated service (if any)
RESTORE_TASKS: Dict[str, Dict[str, str]] = {
    "vm-libvirt-var": {
        "name": "VM Libvirt (var)",
        "description": "Virtual Machine configurations and storage from /var/lib/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/var/lib/libvirt",
        "target": "/var/lib/libvirt",
        "service": "libvirtd",
    },
    "vm-libvirt-etc": {
        "name": "VM Libvirt (etc)",
        "description": "Virtual Machine configuration files from /etc/libvirt",
        "source": "/home/sawyer/restic_restore/vm-backups/etc/libvirt",
        "target": "/etc/libvirt",
        "service": "libvirtd",
    },
    "plex": {
        "name": "Plex Media Server",
        "description": "Plex Media Server library data and configuration",
        "source": "/home/sawyer/restic_restore/plex-media-server-backup/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "service": "plexmediaserver",
    },
}

# File copying settings
BUFFER_SIZE = 4 * 1024 * 1024  # 4MB buffer
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Logging configuration
LOG_FILE = "/var/log/restore_script.log"

# ====================================================
# Nord‑Themed UI & Logging Helpers
# ====================================================

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

def setup_logging() -> None:
    """Initialize logging to file."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    print_success(f"Logging to {LOG_FILE}")

def log_message(message: str, level: str = "INFO") -> None:
    """Append a message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")

# ====================================================
# Command Execution Helper
# ====================================================

def run_command(cmd: List[str], env=None, check=True, capture_output=True, timeout=None):
    """Execute a command and handle errors appropriately."""
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

# ====================================================
# Signal Handling & Cleanup
# ====================================================

def signal_handler(sig, frame):
    """Handle SIGINT and SIGTERM signals gracefully."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)

def cleanup():
    """Perform any necessary cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    log_message("Cleanup performed during script exit")
    # Additional cleanup steps can be added here

atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ====================================================
# Core Restore Functions
# ====================================================

def check_root() -> bool:
    """Check if the script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        return False
    return True

def control_service(service: str, action: str) -> bool:
    """
    Stop or start a service using systemctl.
    Returns True if the service reaches the desired state.
    """
    print_step(f"{action.capitalize()}ing service '{service}'...")
    log_message(f"{action.capitalize()}ing service '{service}'")
    try:
        run_command(["systemctl", action, service])
        time.sleep(2)
        status_result = run_command(["systemctl", "is-active", service], check=False)
        expected = "active" if action == "start" else "inactive"
        actual = status_result.stdout.strip()
        if (action == "start" and actual == "active") or (action == "stop" and actual != "active"):
            print_success(f"Service '{service}' {action}ed successfully")
            log_message(f"Service '{service}' {action}ed successfully")
            return True
        else:
            print_warning(f"Service '{service}' did not {action} properly (status: {actual})")
            log_message(f"Service '{service}' did not {action} properly (status: {actual})", "WARNING")
            return False
    except Exception as e:
        print_error(f"Failed to {action} service '{service}': {e}")
        log_message(f"Failed to {action} service '{service}': {e}", "ERROR")
        return False

def is_restore_needed(source_path: str, target_path: str) -> bool:
    """
    Compare source and target directories.
    Returns True if target is missing or differs from source.
    """
    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False
    if not target.exists():
        print_step(f"Target directory doesn't exist: {target}")
        log_message(f"Target directory doesn't exist: {target}")
        return True
    source_files = sum(1 for _ in source.rglob("*") if _.is_file())
    target_files = sum(1 for _ in target.rglob("*") if _.is_file())
    if source_files != target_files:
        print_step(f"File count differs. Source: {source_files}, Target: {target_files}")
        log_message(f"File count differs. Source: {source_files}, Target: {target_files}")
        return True
    print_step("Source and target directories appear identical")
    log_message("Source and target directories appear identical")
    return False

def copy_directory(source_path: str, target_path: str) -> bool:
    """
    Recursively copy files from source to target with progress feedback.
    Returns True on success, False otherwise.
    """
    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        print_error(f"Source directory not found: {source}")
        log_message(f"Source directory not found: {source}", "ERROR")
        return False
    print_step(f"Copying from '{source}' to '{target}'")
    log_message(f"Starting copy from '{source}' to '{target}'")
    if target.exists():
        try:
            shutil.rmtree(target)
            print_step(f"Removed existing target directory: {target}")
        except Exception as e:
            print_error(f"Failed to remove target directory: {e}")
            log_message(f"Failed to remove target directory: {e}", "ERROR")
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0
    total_size = 0
    for file_path in source.rglob("*"):
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size
    print_step(f"Found {file_count} files, total size: {total_size / (1024*1024):.2f} MB")
    copied_size = 0
    errors = []
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task("Overall progress", total=total_size)
        current_task = progress.add_task("Copying file", total=1, visible=False)
        for source_file in source.rglob("*"):
            if source_file.is_dir():
                (target / source_file.relative_to(source)).mkdir(parents=True, exist_ok=True)
                continue
            rel_path = source_file.relative_to(source)
            target_file = target / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            file_size = source_file.stat().st_size
            progress.update(current_task, total=file_size, completed=0, visible=True)
            progress.update(current_task, description=f"Copying {rel_path}")
            for attempt in range(MAX_RETRIES):
                try:
                    with open(source_file, "rb") as src, open(target_file, "wb") as dst:
                        copied = 0
                        while True:
                            buf = src.read(BUFFER_SIZE)
                            if not buf:
                                break
                            dst.write(buf)
                            copied += len(buf)
                            copied_size += len(buf)
                            progress.update(current_task, completed=copied)
                            progress.update(overall_task, completed=copied_size)
                    shutil.copystat(source_file, target_file)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (2 ** attempt)
                        progress.update(current_task, description=f"Retry in {delay}s: {rel_path}")
                        time.sleep(delay)
                    else:
                        errors.append((str(rel_path), str(e)))
                        log_message(f"Failed to copy {rel_path}: {e}", "ERROR")
            progress.update(current_task, visible=False)
    if errors:
        print_warning(f"Encountered {len(errors)} errors during copy.")
        log_message(f"Copy completed with {len(errors)} errors", "WARNING")
        for file_path, error in errors[:5]:
            print_error(f"Error copying {file_path}: {error}")
        if len(errors) > 5:
            print_warning(f"...and {len(errors)-5} more errors")
        return False
    else:
        print_success("Files copied successfully.")
        log_message("Copy completed successfully")
        return True

def restore_task(task_key: str) -> bool:
    """
    Restore a single task defined in RESTORE_TASKS.
    Stops the associated service, copies files from the backup restore folder to the live location,
    and restarts the service.
    """
    if task_key not in RESTORE_TASKS:
        print_error(f"Unknown restore task: {task_key}")
        log_message(f"Unknown restore task: {task_key}", "ERROR")
        return False
    config = RESTORE_TASKS[task_key]
    name = config["name"]
    source = config["source"]
    target = config["target"]
    service = config.get("service", "")
    print_section(f"Restoring {name}")
    log_message(f"Starting restore task: {name}")
    if not is_restore_needed(source, target):
        print_success(f"Restore not needed for {name} - target is already up to date")
        log_message(f"Restore not needed for {name} - target is already up to date")
        return True
    if service:
        if not control_service(service, "stop"):
            if not prompt_yes_no(f"Failed to stop service {service}. Continue anyway?"):
                print_warning(f"Restore of {name} aborted by user")
                log_message(f"Restore of {name} aborted by user", "WARNING")
                return False
    success = copy_directory(source, target)
    if service:
        if not control_service(service, "start"):
            print_warning(f"Failed to restart service {service}")
            log_message(f"Failed to restart service {service}", "WARNING")
            success = False
    if success:
        print_success(f"Successfully restored {name}")
        log_message(f"Successfully restored {name}")
    else:
        print_error(f"Failed to restore {name}")
        log_message(f"Failed to restore {name}", "ERROR")
    return success

def restore_all() -> Dict[str, bool]:
    """
    Restore all tasks defined in RESTORE_TASKS.
    Returns a dictionary mapping task keys to their restore success status.
    """
    results: Dict[str, bool] = {}
    print_section("Starting restore of all tasks")
    log_message("Starting restore of all tasks")
    for key in RESTORE_TASKS:
        results[key] = restore_task(key)
        time.sleep(1)
    return results

def print_status_report(results: Dict[str, bool]) -> None:
    """Print a summary report of the restore statuses."""
    print_section("Restore Status Report")
    log_message("Generating status report")
    table = Table(title="Restore Results", style="bold #88C0D0")
    table.add_column("Task", style="#D8DEE9")
    table.add_column("Status", justify="center")
    table.add_column("Description", style="#81A1C1")
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        description = RESTORE_TASKS[key].get("description", "")
        status_style = "bold #8FBCBB" if success else "bold #BF616A"
        status_text = "SUCCESS" if success else "FAILED"
        table.add_row(name, f"[{status_style}]{status_text}[/{status_style}]", description)
    console.print(table)
    for key, success in results.items():
        name = RESTORE_TASKS[key]["name"]
        status = "SUCCESS" if success else "FAILED"
        log_message(f"Restore {status} for {name}")

def prompt_yes_no(question: str) -> bool:
    """Prompt the user with a yes/no question and return True for yes."""
    while True:
        response = input(f"{question} (y/n): ").strip().lower()
        if response in ["y", "yes"]:
            return True
        elif response in ["n", "no"]:
            return False
        else:
            print_warning("Please enter 'y' or 'n'.")

def display_tasks_table() -> None:
    """Display available restore tasks in a formatted table."""
    print_section("Available Restore Tasks")
    table = Table(style="bold #88C0D0")
    table.add_column("#", justify="right", style="#81A1C1")
    table.add_column("Name", style="#D8DEE9")
    table.add_column("Description", style="#81A1C1")
    table.add_column("Source Path", style="dim")
    for i, (key, task) in enumerate(RESTORE_TASKS.items(), 1):
        description = task.get("description", "")
        source_path = task["source"]
        if len(source_path) > 40:
            source_path = source_path[:20] + "..." + source_path[-17:]
        table.add_row(str(i), task["name"], description, source_path)
    console.print(table)

# ====================================================
# Interactive Menu Functions
# ====================================================

def interactive_menu() -> None:
    """Display and handle the interactive menu for restore operations."""
    while True:
        print_header("Restore Menu")
        console.print(Panel.fit("[bold #D8DEE9]Select an option:[/]", border_style="#88C0D0"))
        console.print("1. [bold #88C0D0]View Available Restore Tasks[/]")
        console.print("2. [bold #88C0D0]Restore Individual Task[/]")
        console.print("3. [bold #88C0D0]Restore All Tasks[/]")
        console.print("4. [bold #88C0D0]View Previous Restore Log[/]")
        console.print("5. [bold #BF616A]Exit[/]")
        choice = input("\n[?] Enter your choice (1-5): ").strip()
        if choice == "1":
            display_tasks_table()
            input("\nPress Enter to return to the menu...")
        elif choice == "2":
            display_tasks_table()
            while True:
                task_choice = input(f"\n[?] Enter task number (1-{len(RESTORE_TASKS)}) or 'c' to cancel: ").strip().lower()
                if task_choice == "c":
                    break
                try:
                    task_num = int(task_choice)
                    if 1 <= task_num <= len(RESTORE_TASKS):
                        task_key = list(RESTORE_TASKS.keys())[task_num - 1]
                        task_name = RESTORE_TASKS[task_key]["name"]
                        if prompt_yes_no(f"Are you sure you want to restore {task_name}?"):
                            start_time = time.time()
                            success = restore_task(task_key)
                            elapsed = time.time() - start_time
                            if success:
                                print_success(f"Restore completed in {elapsed:.2f} seconds")
                            else:
                                print_error(f"Restore failed after {elapsed:.2f} seconds")
                        break
                    else:
                        print_error(f"Enter a number between 1 and {len(RESTORE_TASKS)}")
                except ValueError:
                    print_error("Please enter a valid number")
            input("\nPress Enter to return to the menu...")
        elif choice == "3":
            if prompt_yes_no("Are you sure you want to restore ALL tasks? This may take some time."):
                start_time = time.time()
                results = restore_all()
                elapsed = time.time() - start_time
                print_status_report(results)
                if all(results.values()):
                    print_success(f"All tasks restored successfully in {elapsed:.2f} seconds")
                else:
                    print_warning(f"Some tasks failed. Total time: {elapsed:.2f} seconds")
            input("\nPress Enter to return to the menu...")
        elif choice == "4":
            try:
                if Path(LOG_FILE).exists():
                    print_section("Recent Log Entries")
                    with open(LOG_FILE, "r") as log:
                        lines = log.readlines()
                        for line in lines[-20:]:
                            if "ERROR" in line:
                                console.print(line.strip(), style="#BF616A")
                            elif "WARNING" in line:
                                console.print(line.strip(), style="#5E81AC")
                            else:
                                console.print(line.strip(), style="#88C0D0")
                else:
                    print_warning(f"Log file not found: {LOG_FILE}")
            except Exception as e:
                print_error(f"Error reading log file: {e}")
            input("\nPress Enter to return to the menu...")
        elif choice == "5":
            print_header("Exiting")
            break
        else:
            print_error("Invalid choice. Please enter a number between 1 and 5.")
            time.sleep(1)

# ====================================================
# Main Entry Point
# ====================================================

def main() -> None:
    """Main function to run the interactive restore script."""
    print_header("Enhanced Restore Script")
    console.print(f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")
    setup_logging()
    if not check_root():
        sys.exit(1)
    # Validate that all source directories exist
    missing_sources = []
    for key, task in RESTORE_TASKS.items():
        source_dir = Path(task["source"])
        if not source_dir.exists():
            missing_sources.append((task["name"], str(source_dir)))
    if missing_sources:
        print_warning(f"Found {len(missing_sources)} tasks with missing source directories:")
        for name, path in missing_sources:
            print_error(f"• {name}: {path}")
        if not prompt_yes_no("Continue anyway?"):
            print_error("Exiting due to missing source directories")
            log_message("Script exited due to missing source directories", "ERROR")
            sys.exit(1)
    interactive_menu()
    print_success("Script execution completed")
    log_message("Script execution completed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Script interrupted by user")
        log_message("Script interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)