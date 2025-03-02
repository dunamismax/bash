#!/usr/bin/env python3
"""
Unified Restic Backup Script with B2 CLI Support
-------------------------------------------------
This script performs incremental backups using Restic for:
  • System (root filesystem)
  • Virtual Machines (libvirt)
  • Plex Media Server

Backups are stored in Backblaze B2 via Restic’s B2 backend.
The script uses the B2 CLI tool only for bucket management functions
(such as verifying or creating the target bucket).

Run this script with root privileges on Linux/Ubuntu.
"""

import atexit
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pyfiglet
import shutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

# ====================================================
# Configuration & Constants
# ====================================================

HOSTNAME = socket.gethostname()

# Backblaze B2 credentials and bucket name (used by Restic’s B2 backend)
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"

# RESTIC_PASSWORD is now baked into the script.
RESTIC_PASSWORD = "12345678"

# Restic repository configuration per service – the repository URL uses the b2 backend.
REPOSITORIES: Dict[str, str] = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup configurations per service:
BACKUP_CONFIGS: Dict[str, Dict] = {
    "system": {
        "paths": ["/"],
        "excludes": [
            "/proc/*", "/sys/*", "/dev/*", "/run/*", "/tmp/*", "/var/tmp/*",
            "/mnt/*", "/media/*", "/var/cache/*", "/var/log/*", "/home/*/.cache/*",
            "/swapfile", "/lost+found", "*.vmdk", "*.vdi", "*.qcow2", "*.img",
            "*.iso", "*.tmp", "*.swap.img", "/var/lib/docker/*", "/var/lib/lxc/*",
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

# Retention policy: keep snapshots from the last 7 days
RETENTION_POLICY = "7d"

# Logging configuration
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ====================================================
# Nord-Themed UI & Logging Helpers
# ====================================================

console = Console()

def print_header(text: str) -> None:
    """Print an ASCII art header."""
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
    """Initialize logging to a file."""
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"\n--- Backup session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        print_success(f"Logging to {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")

def log_message(message: str, level: str = "INFO") -> None:
    """Append a log message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{timestamp} - {level} - {message}\n")
    except Exception:
        pass

def run_command(cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True,
                capture_output: bool = True, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a command with robust error handling."""
    try:
        print_step(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, env=env or os.environ.copy(), check=check,
                                text=True, capture_output=capture_output, timeout=timeout)
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

def signal_handler(sig, frame) -> None:
    """Handle SIGINT/SIGTERM signals gracefully."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)

def cleanup() -> None:
    """Perform any necessary cleanup tasks."""
    print_step("Performing cleanup tasks...")
    # Add additional cleanup steps if needed

atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ====================================================
# B2 CLI Functions (Bucket Management)
# ====================================================

def install_b2_cli() -> bool:
    """
    Ensure the B2 CLI tool is installed.
    This function attempts a pip3 install if b2 is not found.
    """
    if shutil.which("b2"):
        print_success("B2 CLI tool already installed.")
        return True

    print_warning("B2 CLI tool not found. Attempting to install via pip3...")
    try:
        run_command(["pip3", "install", "--upgrade", "b2"])
        b2_path = shutil.which("b2")
        if b2_path:
            run_command(["chmod", "+x", b2_path])
            print_success("B2 CLI tool installed successfully.")
            return True
        else:
            print_error("B2 CLI tool installation failed: command not found after installation.")
            return False
    except Exception as e:
        print_error(f"B2 CLI installation failed: {e}")
        return False

def authorize_b2() -> bool:
    """
    Authorize the B2 CLI tool using the provided account ID and key.
    """
    try:
        run_command(["b2", "authorize-account", B2_ACCOUNT_ID, B2_ACCOUNT_KEY])
        print_success("B2 CLI tool authorized successfully.")
        log_message("B2 CLI tool authorized successfully")
        return True
    except Exception as e:
        print_error(f"B2 authorization failed: {e}")
        log_message(f"B2 authorization failed: {e}", "ERROR")
        return False

def ensure_bucket_exists(bucket: str) -> bool:
    """
    Ensure the target bucket exists in B2. If not, create it.
    """
    try:
        result = run_command(["b2", "list-buckets"])
        if bucket in result.stdout:
            print_success(f"Bucket '{bucket}' exists.")
            log_message(f"Bucket '{bucket}' exists.")
            return True
        else:
            print_warning(f"Bucket '{bucket}' not found. Creating it...")
            run_command(["b2", "create-bucket", bucket, "allPrivate"])
            print_success(f"Bucket '{bucket}' created.")
            log_message(f"Bucket '{bucket}' created.")
            return True
    except Exception as e:
        print_error(f"Error ensuring bucket exists: {e}")
        log_message(f"Error ensuring bucket exists: {e}", "ERROR")
        return False

# ====================================================
# Restic Backup Functions
# ====================================================

def initialize_repository(service: str) -> bool:
    """
    Initialize the Restic repository for the given service if not already initialized.
    The repository URL is defined in REPOSITORIES.
    """
    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD
    })
    print_section("Repository Initialization")
    print_step(f"Checking repository: {repo}")
    log_message(f"Checking repository for {service}: {repo}")
    try:
        # Try listing snapshots to check if repository exists
        run_command(["restic", "--repo", repo, "snapshots"], env=env)
        print_success("Repository already initialized.")
        log_message(f"Repository for {service} already initialized")
        return True
    except subprocess.CalledProcessError:
        print_warning("Repository not found. Initializing...")
        log_message(f"Repository for {service} not found, initializing")
        try:
            run_command(["restic", "--repo", repo, "init"], env=env)
            print_success("Repository initialized successfully.")
            log_message(f"Repository for {service} initialized successfully")
            return True
        except Exception as e:
            print_error(f"Failed to initialize repository: {e}")
            log_message(f"Failed to initialize repository for {service}: {e}", "ERROR")
            return False
    except Exception as e:
        print_error(f"Error during repository initialization: {e}")
        log_message(f"Error during repository initialization for {service}: {e}", "ERROR")
        return False

def perform_backup(service: str) -> bool:
    """
    Perform a backup for the specified service using Restic.
    The backup command uses the configured paths and excludes.
    """
    if service not in BACKUP_CONFIGS:
        print_error(f"Unknown service '{service}'")
        log_message(f"Unknown service '{service}'", "ERROR")
        return False

    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]
    print_section(f"{config['name']} Backup")
    log_message(f"Starting backup for {config['name']}")

    # Check service-specific paths (for vm and plex)
    if service == "vm":
        for path in ["/etc/libvirt", "/var/lib/libvirt"]:
            if not Path(path).exists():
                print_error(f"Required path {path} not found. Is libvirt installed?")
                log_message(f"Path {path} not found for VM backup", "ERROR")
                return False
    elif service == "plex":
        for path in ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]:
            if not Path(path).exists():
                print_error(f"Required path {path} not found. Is Plex installed?")
                log_message(f"Path {path} not found for Plex backup", "ERROR")
                return False

    # Initialize repository if needed
    if not initialize_repository(service):
        return False

    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD
    })

    # Build the restic backup command
    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config.get("excludes", []):
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.append("--verbose")

    print_step(f"Starting backup for {config['name']} ...")
    log_message(f"Executing backup command for {service}: {' '.join(backup_cmd)}")
    try:
        # Run backup command and stream output
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Running backup...", total=100)
            process = subprocess.Popen(backup_cmd, env=env,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       text=True, bufsize=1)
            for line in process.stdout:
                console.print(line.strip(), style="#D8DEE9")
                # (Optional: update progress based on output parsing)
            process.wait()
            if process.returncode != 0:
                print_error(f"Backup failed with return code {process.returncode}.")
                log_message(f"Backup failed for {service} with return code {process.returncode}", "ERROR")
                return False
        print_success(f"{config['name']} backup completed successfully.")
        log_message(f"{config['name']} backup completed successfully")
        return True
    except Exception as e:
        print_error(f"Backup error: {e}")
        log_message(f"Backup error for {service}: {e}", "ERROR")
        return False

def apply_retention(service: str) -> bool:
    """
    Apply the retention policy for the given service using Restic.
    This runs the 'restic forget --prune' command with the retention parameters.
    """
    repo = REPOSITORIES[service]
    print_section(f"Applying Retention Policy for {BACKUP_CONFIGS[service]['name']}")
    print_step(f"Keeping snapshots within {RETENTION_POLICY}")
    log_message(f"Applying retention for {service}: {RETENTION_POLICY}")

    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD
    })

    retention_cmd = ["restic", "--repo", repo, "forget", "--prune", "--keep-within", RETENTION_POLICY]
    try:
        result = run_command(retention_cmd, env=env)
        console.print(result.stdout.strip(), style="#D8DEE9")
        print_success("Retention policy applied successfully.")
        log_message("Retention policy applied successfully")
        return True
    except Exception as e:
        print_error(f"Retention policy application failed: {e}")
        log_message(f"Retention policy application failed for {service}: {e}", "ERROR")
        return False

def list_snapshots(service: str) -> bool:
    """
    List snapshots for the given service using Restic.
    """
    repo = REPOSITORIES[service]
    print_section(f"{BACKUP_CONFIGS[service]['name']} Snapshots")
    log_message(f"Listing snapshots for {service}")
    env = os.environ.copy()
    env.update({
        "RESTIC_PASSWORD": RESTIC_PASSWORD
    })
    try:
        result = run_command(["restic", "--repo", repo, "snapshots", "--json"], env=env)
        snapshots = json.loads(result.stdout)
        if snapshots:
            console.print(f"\n[bold #D8DEE9]ID         Date                 Paths[/bold #D8DEE9]")
            console.print("-" * 60, style="#D8DEE9")
            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
                paths = ", ".join(snap.get("paths", []))
                console.print(f"{sid:<10} {time_str:<20} {paths}", style="#D8DEE9")
            console.print("-" * 60, style="#D8DEE9")
            log_message(f"Found {len(snapshots)} snapshots for {service}")
        else:
            print_warning("No snapshots found.")
            log_message("No snapshots found", "WARNING")
        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {e}")
        log_message(f"Failed to list snapshots for {service}: {e}", "ERROR")
        return False

def backup_all_services() -> Dict[str, bool]:
    """
    Run backups for all configured services sequentially.
    """
    results: Dict[str, bool] = {}
    print_header("Starting Backup for All Services")
    log_message("Starting backup for all services")
    for svc in BACKUP_CONFIGS.keys():
        print_header(f"Service: {BACKUP_CONFIGS[svc]['name']}")
        results[svc] = backup_service(svc)
    print_header("Overall Backup Summary")
    for svc, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        color = "#8FBCBB" if success else "#BF616A"
        console.print(f"{BACKUP_CONFIGS[svc]['name']}: [bold {color}]{status}[/bold {color}]")
    return results

# ====================================================
# Interactive Menu Functions
# ====================================================

def show_system_info() -> None:
    """Display system and configuration information."""
    print_section("System Information")
    console.print(f"[#88C0D0]Hostname: [#D8DEE9]{HOSTNAME}[/#D8DEE9]")
    console.print(f"[#88C0D0]Platform: [#D8DEE9]{platform.platform()}[/#D8DEE9]")
    console.print(f"[#88C0D0]Python Version: [#D8DEE9]{platform.python_version()}[/#D8DEE9]")
    console.print(f"[#88C0D0]B2 Bucket: [#D8DEE9]{B2_BUCKET}[/#D8DEE9]")
    console.print(f"[#88C0D0]Retention Policy: [#D8DEE9]{RETENTION_POLICY}[/#D8DEE9]")
    console.print(f"[#88C0D0]Available Backup Services:[/#88C0D0]")
    for key, config in BACKUP_CONFIGS.items():
        console.print(f"  • [#D8DEE9]{config['name']} - {config['description']}[/#D8DEE9]")

def interactive_menu() -> None:
    """Display the interactive menu and handle user input."""
    while True:
        print_header("Backup Menu")
        console.print("1. Backup System")
        console.print("2. Backup Virtual Machines")
        console.print("3. Backup Plex Media Server")
        console.print("4. Backup All Services")
        console.print("5. List Snapshots (per service)")
        console.print("6. List All Snapshots")
        console.print("7. Exit")
        choice = input("\nSelect an option (1-7): ").strip()
        if choice == "1":
            backup_service("system")
        elif choice == "2":
            backup_service("vm")
        elif choice == "3":
            backup_service("plex")
        elif choice == "4":
            backup_all_services()
        elif choice == "5":
            svc = input("Enter service (system/vm/plex): ").strip().lower()
            list_snapshots(svc)
        elif choice == "6":
            for svc in BACKUP_CONFIGS.keys():
                list_snapshots(svc)
        elif choice == "7":
            print_header("Exiting")
            break
        else:
            print_warning("Invalid selection, please try again.")
        input("\nPress Enter to return to the menu...")

# ====================================================
# Main Entry Point
# ====================================================

def main() -> None:
    """Main function to run the backup script."""
    print_header("Unified Restic Backup")
    console.print(f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")
    setup_logging()

    # Install and authorize B2 CLI, and ensure the bucket exists.
    if not install_b2_cli():
        sys.exit(1)
    if not authorize_b2():
        sys.exit(1)
    if not ensure_bucket_exists(B2_BUCKET):
        sys.exit(1)

    show_system_info()
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