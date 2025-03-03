#!/usr/bin/env python3
"""
Unified Restic Backup Manager
--------------------------------------------------

A streamlined terminal interface for managing Restic backups with Backblaze B2 integration.
Features include backup management for system, virtual machines, and Plex Media Server
with real-time progress tracking, snapshot management, and retention policy application.

This utility provides a comprehensive solution for managing incremental backups using
Restic's powerful snapshot system, with all data securely stored in Backblaze B2.

Usage:
  Run the script with root privileges and select an option from the interactive menu.
  - System Backup: Backs up root filesystem with appropriate exclusions
  - VM Backup: Backs up libvirt configurations and storage
  - Plex Backup: Backs up Plex Media Server configuration and data
  - All: Runs all configured backup services
  - Snapshots: Lists and manages existing snapshots

Run this script with root privileges on Linux/Ubuntu.

Version: 1.0.0
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
from typing import Dict, List, Optional, Any, Tuple, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    import shutil
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich', 'pyfiglet', and other libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
VERSION: str = "1.0.0"
APP_NAME: str = "Restic Backup Manager"
APP_SUBTITLE: str = "Secure Backup Solution"

# Backblaze B2 credentials and bucket name (used by Restic's B2 backend)
B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"

# RESTIC_PASSWORD is now baked into the script.
RESTIC_PASSWORD: str = "12345678"

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

# Retention policy: keep snapshots from the last 7 days
RETENTION_POLICY: str = "7d"

# Logging configuration
LOG_DIR: str = "/var/log/backup"
LOG_FILE: str = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini", "digital"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
               _   _        _                _                
 _ __ ___  ___| |_(_) ___  | |__   __ _  ___| | ___   _ _ __  
| '__/ _ \/ __| __| |/ __| | '_ \ / _` |/ __| |/ / | | | '_ \ 
| | |  __/\__ \ |_| | (__  | |_) | (_| | (__|   <| |_| | |_) |
|_|  \___||___/\__|_|\___| |_.__/ \__,_|\___|_|\_\\__,_| .__/ 
                                                       |_|     
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(text: str) -> None:
    """
    Print a success message.

    Args:
        text: The success message to display
    """
    print_message(text, NordColors.GREEN, "✓")


def print_warning(text: str) -> None:
    """
    Print a warning message.

    Args:
        text: The warning message to display
    """
    print_message(text, NordColors.YELLOW, "⚠")


def print_error(text: str) -> None:
    """
    Print an error message.

    Args:
        text: The error message to display
    """
    print_message(text, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def setup_logging() -> None:
    """Initialize logging to a file."""
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as log_file:
            log_file.write(
                f"\n--- Backup session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )
        print_success(f"Logging to {LOG_FILE}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")


def log_message(message: str, level: str = "INFO") -> None:
    """
    Append a log message to the log file.

    Args:
        message: The message to log
        level: Log level (INFO, WARNING, ERROR)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{timestamp} - {level} - {message}\n")
    except Exception:
        pass


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """
    Executes a system command with robust error handling.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
    """
    try:
        print_message(f"Running: {' '.join(cmd)}")
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
            console.print(
                f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/bold {NordColors.RED}]"
            )
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)
    log_message("Cleanup performed")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}")
    log_message(f"Process interrupted by {sig_name}", "WARNING")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# B2 CLI Functions (Bucket Management)
# ----------------------------------------------------------------
def install_b2_cli() -> bool:
    """
    Ensure the B2 CLI tool is installed.
    This function attempts a pip3 install if b2 is not found.

    Returns:
        True if installation successful or already installed, False otherwise
    """
    if shutil.which("b2"):
        print_success("B2 CLI tool already installed")
        return True

    print_warning("B2 CLI tool not found. Attempting to install via pip3...")
    try:
        run_command(["pip3", "install", "--upgrade", "b2"])
        b2_path = shutil.which("b2")
        if b2_path:
            run_command(["chmod", "+x", b2_path])
            print_success("B2 CLI tool installed successfully")
            return True
        else:
            print_error(
                "B2 CLI tool installation failed: command not found after installation"
            )
            return False
    except Exception as e:
        print_error(f"B2 CLI installation failed: {e}")
        return False


def authorize_b2() -> bool:
    """
    Authorize the B2 CLI tool using the provided account ID and key.

    Returns:
        True if authorization successful, False otherwise
    """
    try:
        run_command(["b2", "authorize-account", B2_ACCOUNT_ID, B2_ACCOUNT_KEY])
        print_success("B2 CLI tool authorized successfully")
        log_message("B2 CLI tool authorized successfully")
        return True
    except Exception as e:
        print_error(f"B2 authorization failed: {e}")
        log_message(f"B2 authorization failed: {e}", "ERROR")
        return False


def ensure_bucket_exists(bucket: str) -> bool:
    """
    Ensure the target bucket exists in B2. If not, create it.

    Args:
        bucket: The B2 bucket name to check/create

    Returns:
        True if bucket exists or was created, False on error
    """
    try:
        result = run_command(["b2", "list-buckets"])
        if bucket in result.stdout:
            print_success(f"Bucket '{bucket}' exists")
            log_message(f"Bucket '{bucket}' exists")
            return True
        else:
            print_warning(f"Bucket '{bucket}' not found. Creating it...")
            run_command(["b2", "create-bucket", bucket, "allPrivate"])
            print_success(f"Bucket '{bucket}' created")
            log_message(f"Bucket '{bucket}' created")
            return True
    except Exception as e:
        print_error(f"Error ensuring bucket exists: {e}")
        log_message(f"Error ensuring bucket exists: {e}", "ERROR")
        return False


# ----------------------------------------------------------------
# Restic Backup Functions
# ----------------------------------------------------------------
def initialize_repository(service: str) -> bool:
    """
    Initialize the Restic repository for the given service if not already initialized.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if repository is ready, False on error
    """
    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    display_panel(
        "Repository Initialization", style=NordColors.FROST_3, title=service.upper()
    )

    print_message(f"Checking repository: {repo}")
    log_message(f"Checking repository for {service}: {repo}")

    try:
        # Try listing snapshots to check if repository exists
        run_command(["restic", "--repo", repo, "snapshots"], env=env)
        print_success("Repository already initialized")
        log_message(f"Repository for {service} already initialized")
        return True
    except subprocess.CalledProcessError:
        print_warning("Repository not found. Initializing...")
        log_message(f"Repository for {service} not found, initializing")
        try:
            run_command(["restic", "--repo", repo, "init"], env=env)
            print_success("Repository initialized successfully")
            log_message(f"Repository for {service} initialized successfully")
            return True
        except Exception as e:
            print_error(f"Failed to initialize repository: {e}")
            log_message(f"Failed to initialize repository for {service}: {e}", "ERROR")
            return False
    except Exception as e:
        print_error(f"Error during repository initialization: {e}")
        log_message(
            f"Error during repository initialization for {service}: {e}", "ERROR"
        )
        return False


def perform_backup(service: str) -> bool:
    """
    Perform a backup for the specified service using Restic.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if backup completed successfully, False on error
    """
    if service not in BACKUP_CONFIGS:
        print_error(f"Unknown service '{service}'")
        log_message(f"Unknown service '{service}'", "ERROR")
        return False

    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    display_panel(
        f"{config['name']} Backup", style=NordColors.FROST_2, title="Backup Operation"
    )
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
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    # Build the restic backup command
    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config.get("excludes", []):
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.append("--verbose")

    print_message(f"Starting backup for {config['name']}...")
    log_message(f"Executing backup command for {service}: {' '.join(backup_cmd)}")

    try:
        # Run backup command with progress animation
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            backup_task = progress.add_task(
                f"Backing up {config['name']}...", total=100
            )

            process = subprocess.Popen(
                backup_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Update progress bar based on output
            progress_pattern = re.compile(r"(\d+\.\d+)% done")
            for line in process.stdout:
                # Try to extract progress percentage from Restic output
                match = progress_pattern.search(line)
                if match:
                    percent = float(match.group(1))
                    progress.update(backup_task, completed=percent)

                console.print(line.strip(), style=f"{NordColors.SNOW_STORM_1}")

            process.wait()
            if process.returncode != 0:
                print_error(f"Backup failed with return code {process.returncode}")
                log_message(
                    f"Backup failed for {service} with return code {process.returncode}",
                    "ERROR",
                )
                return False

        print_success(f"{config['name']} backup completed successfully")
        log_message(f"{config['name']} backup completed successfully")
        return True
    except Exception as e:
        print_error(f"Backup error: {e}")
        log_message(f"Backup error for {service}: {e}", "ERROR")
        return False


def apply_retention(service: str) -> bool:
    """
    Apply the retention policy for the given service using Restic.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if retention policy applied successfully, False on error
    """
    repo = REPOSITORIES[service]

    display_panel(
        f"Applying Retention Policy for {BACKUP_CONFIGS[service]['name']}",
        style=NordColors.FROST_3,
        title="Snapshot Management",
    )

    print_message(f"Keeping snapshots within {RETENTION_POLICY}")
    log_message(f"Applying retention for {service}: {RETENTION_POLICY}")

    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    retention_cmd = [
        "restic",
        "--repo",
        repo,
        "forget",
        "--prune",
        "--keep-within",
        RETENTION_POLICY,
    ]

    try:
        result = run_command(retention_cmd, env=env)
        console.print(result.stdout.strip(), style=f"{NordColors.SNOW_STORM_1}")
        print_success("Retention policy applied successfully")
        log_message("Retention policy applied successfully")
        return True
    except Exception as e:
        print_error(f"Retention policy application failed: {e}")
        log_message(f"Retention policy application failed for {service}: {e}", "ERROR")
        return False


def list_snapshots(service: str) -> bool:
    """
    List snapshots for the given service using Restic.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if snapshots listed successfully, False on error
    """
    repo = REPOSITORIES[service]

    display_panel(
        f"{BACKUP_CONFIGS[service]['name']} Snapshots",
        style=NordColors.FROST_2,
        title="Snapshot List",
    )

    log_message(f"Listing snapshots for {service}")
    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    try:
        result = run_command(["restic", "--repo", repo, "snapshots", "--json"], env=env)
        snapshots = json.loads(result.stdout)

        if snapshots:
            # Create a table for snapshots
            table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=True,
                title=f"[bold {NordColors.FROST_2}]{BACKUP_CONFIGS[service]['name']} Snapshots[/]",
                border_style=NordColors.FROST_3,
            )

            table.add_column("ID", style=f"bold {NordColors.FROST_4}", no_wrap=True)
            table.add_column("Date", style=f"{NordColors.SNOW_STORM_1}")
            table.add_column("Paths", style=f"{NordColors.SNOW_STORM_1}")

            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
                paths = ", ".join(snap.get("paths", []))
                table.add_row(sid, time_str, paths)

            console.print(table)
            log_message(f"Found {len(snapshots)} snapshots for {service}")
        else:
            print_warning("No snapshots found")
            log_message("No snapshots found", "WARNING")

        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {e}")
        log_message(f"Failed to list snapshots for {service}: {e}", "ERROR")
        return False


def backup_service(service: str) -> bool:
    """
    Execute a full backup workflow for a service: backup and apply retention.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if all operations completed successfully, False otherwise
    """
    # Perform backup
    if not perform_backup(service):
        return False

    # Apply retention policy
    if not apply_retention(service):
        print_warning("Backup was successful but retention policy application failed")
        return False

    # List snapshots after backup
    list_snapshots(service)
    return True


def backup_all_services() -> Dict[str, bool]:
    """
    Run backups for all configured services sequentially.

    Returns:
        Dictionary mapping service names to success status
    """
    results: Dict[str, bool] = {}

    console.clear()
    console.print(create_header())

    display_panel(
        "Starting Backup for All Services",
        style=NordColors.FROST_2,
        title="Unified Backup",
    )

    log_message("Starting backup for all services")

    for svc in BACKUP_CONFIGS.keys():
        results[svc] = backup_service(svc)

    # Show summary
    console.print("\n")
    display_panel(
        "Backup Results Summary", style=NordColors.FROST_3, title="Completion Status"
    )

    # Create summary table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )

    table.add_column("Service", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center")

    for svc, success in results.items():
        status_style = NordColors.GREEN if success else NordColors.RED
        status_text = "✓ SUCCESS" if success else "✗ FAILED"
        table.add_row(
            BACKUP_CONFIGS[svc]["name"],
            BACKUP_CONFIGS[svc]["description"],
            f"[bold {status_style}]{status_text}[/]",
        )

    console.print(table)

    return results


# ----------------------------------------------------------------
# Interactive Menu Functions
# ----------------------------------------------------------------
def show_system_info() -> None:
    """Display system and configuration information."""
    display_panel("System Information", style=NordColors.FROST_3, title="Configuration")

    # Create a table for system info
    table = Table(
        show_header=False,
        expand=False,
        border_style=NordColors.FROST_4,
        box=None,
    )

    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    table.add_row("Hostname", HOSTNAME)
    table.add_row("Platform", platform.platform())
    table.add_row("Python Version", platform.python_version())
    table.add_row("B2 Bucket", B2_BUCKET)
    table.add_row("Retention Policy", RETENTION_POLICY)

    console.print(table)

    # Create table for backup services
    service_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Backup Services[/]",
        border_style=NordColors.FROST_3,
    )

    service_table.add_column("Service", style=f"bold {NordColors.FROST_2}")
    service_table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")
    service_table.add_column("Paths", style=f"{NordColors.SNOW_STORM_1}")

    for key, config in BACKUP_CONFIGS.items():
        service_table.add_row(
            config["name"], config["description"], ", ".join(config["paths"])
        )

    console.print(service_table)


def create_menu_panel() -> Panel:
    """
    Create a styled panel containing the menu options.

    Returns:
        Panel containing formatted menu options
    """
    menu_text = Text()
    menu_text.append("1. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup System\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("2. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Virtual Machines\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("3. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Plex Media Server\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("4. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup All Services\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("5. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append(
        "List Snapshots (per service)\n", style=f"{NordColors.SNOW_STORM_1}"
    )

    menu_text.append("6. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("List All Snapshots\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("7. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Exit", style=f"{NordColors.SNOW_STORM_1}")

    return Panel(
        menu_text,
        border_style=Style(color=NordColors.FROST_2),
        padding=(1, 2),
        title=f"[bold {NordColors.FROST_3}]Menu Options[/]",
        title_align="center",
    )


def interactive_menu() -> None:
    """Display the interactive menu and handle user input."""
    while True:
        console.clear()
        console.print(create_header())

        # Display current time and timestamp
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()

        console.print(create_menu_panel())
        console.print()
        console.print(f"[bold {NordColors.FROST_2}]Select an option (1-7):[/]", end=" ")
        choice = input().strip()

        if choice == "1":
            backup_service("system")
        elif choice == "2":
            backup_service("vm")
        elif choice == "3":
            backup_service("plex")
        elif choice == "4":
            backup_all_services()
        elif choice == "5":
            console.clear()
            console.print(create_header())
            display_panel(
                "Select Service", style=NordColors.FROST_2, title="Service Selection"
            )

            # Create service selection table
            service_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=False,
                border_style=NordColors.FROST_3,
            )

            service_table.add_column(
                "Option", style=f"bold {NordColors.FROST_4}", justify="center"
            )
            service_table.add_column("Service", style=f"bold {NordColors.FROST_2}")

            for i, (svc, config) in enumerate(BACKUP_CONFIGS.items(), 1):
                service_table.add_row(str(i), config["name"])

            console.print(service_table)
            console.print()
            console.print(
                f"[bold {NordColors.FROST_2}]Enter service number (1-{len(BACKUP_CONFIGS)}):[/]",
                end=" ",
            )

            svc_choice = input().strip()
            try:
                svc_idx = int(svc_choice) - 1
                if 0 <= svc_idx < len(BACKUP_CONFIGS):
                    service = list(BACKUP_CONFIGS.keys())[svc_idx]
                    list_snapshots(service)
                else:
                    print_error(f"Invalid selection: {svc_choice}")
            except ValueError:
                print_error(f"Invalid input: {svc_choice}")
        elif choice == "6":
            console.clear()
            console.print(create_header())
            display_panel(
                "All Snapshots", style=NordColors.FROST_2, title="Snapshot Overview"
            )

            for svc in BACKUP_CONFIGS.keys():
                list_snapshots(svc)
        elif choice == "7":
            console.clear()
            console.print(create_header())
            display_panel(
                "Thank you for using Restic Backup Manager!",
                style=NordColors.FROST_2,
                title="Exit",
            )
            break
        else:
            print_warning("Invalid selection, please try again")

        console.print()
        console.print(
            f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
        )
        input()


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function to run the backup script."""
    console.clear()
    console.print(create_header())

    display_panel(
        f"Starting Unified Restic Backup Manager\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        style=NordColors.FROST_2,
        title="Initialization",
    )

    setup_logging()

    # Install and authorize B2 CLI, and ensure the bucket exists
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        console=console,
    ) as progress:
        task = progress.add_task("Setting up B2 integration...", total=3)

        if not install_b2_cli():
            sys.exit(1)
        progress.advance(task)

        if not authorize_b2():
            sys.exit(1)
        progress.advance(task)

        if not ensure_bucket_exists(B2_BUCKET):
            sys.exit(1)
        progress.advance(task)

    show_system_info()
    interactive_menu()
    print_success("Backup operations completed")
    log_message("Script execution completed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Backup interrupted by user")
        log_message("Backup interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        console.print_exception()
        sys.exit(1)
