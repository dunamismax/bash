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

Version: 2.0.0
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable, Union

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
        TaskProgressColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.prompt import Prompt, Confirm
except ImportError:
    print("This script requires several Python libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
VERSION: str = "2.0.0"
APP_NAME: str = "Restic Backup Manager"
APP_SUBTITLE: str = "Secure Backup Solution"

# Configuration that should be customized per installation
# In a production environment, these should be loaded from a config file
# or environment variables rather than hardcoded
B2_ACCOUNT_ID: str = "YOUR_B2_ACCOUNT_ID"
B2_ACCOUNT_KEY: str = "YOUR_B2_ACCOUNT_KEY"
B2_BUCKET: str = "your-backup-bucket"
RESTIC_PASSWORD: str = "YOUR_RESTIC_PASSWORD"

# Restic repository configuration per service
REPOSITORIES: Dict[str, str] = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup configurations per service
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

# Command execution defaults
OPERATION_TIMEOUT: int = 300  # 5 minutes default timeout for long operations
COMMAND_TIMEOUT: int = 30  # 30 seconds for standard commands


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

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
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console with Nord theme
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and UI Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with Nord theme styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "mini", "digital", "banner3"]

    # Try each font until we find one that works well
    ascii_art = None
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
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
        NordColors.FROST_4,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border_top = f"[{NordColors.FROST_3}]╭" + "─" * 58 + "╮[/]"
    tech_border_bottom = f"[{NordColors.FROST_3}]╰" + "─" * 58 + "╯[/]"
    styled_text = tech_border_top + "\n" + styled_text + tech_border_bottom

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•", log: bool = True
) -> None:
    """
    Print a styled message and optionally log it.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
        log: Whether to also log this message
    """
    message = f"{prefix} {text}"
    console.print(f"[{style}]{message}[/{style}]")

    if log:
        log_message(text)


def print_success(text: str, log: bool = True) -> None:
    """
    Print a success message.

    Args:
        text: The success message to display
        log: Whether to also log this message
    """
    print_message(text, NordColors.GREEN, "✓", log)


def print_warning(text: str, log: bool = True) -> None:
    """
    Print a warning message.

    Args:
        text: The warning message to display
        log: Whether to also log this message
    """
    print_message(text, NordColors.YELLOW, "⚠", log)
    if log:
        log_message(text, "WARNING")


def print_error(text: str, log: bool = True) -> None:
    """
    Print an error message.

    Args:
        text: The error message to display
        log: Whether to also log this message
    """
    print_message(text, NordColors.RED, "✗", log)
    if log:
        log_message(text, "ERROR")


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
        print_success(f"Logging to {LOG_FILE}", log=False)
    except Exception as e:
        print_warning(f"Could not set up logging: {e}", log=False)


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
        pass  # Silent failure if logging is not possible


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """
    Get input from the user with a styled prompt.

    Args:
        prompt: The prompt to display
        default: Optional default value

    Returns:
        User input as string
    """
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]{prompt}[/]",
        default=default,
        console=console,
    )


def get_user_confirmation(prompt: str, default: bool = True) -> bool:
    """
    Get confirmation from the user with a styled prompt.

    Args:
        prompt: The prompt to display
        default: Default value (True/False)

    Returns:
        User confirmation as boolean
    """
    return Confirm.ask(
        f"[bold {NordColors.FROST_2}]{prompt}[/]",
        default=default,
        console=console,
    )


def wait_for_enter() -> None:
    """Wait for the user to press Enter."""
    console.print(
        f"[{NordColors.SNOW_STORM_1}]Press Enter to continue...[/]",
        end="",
    )
    input()


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = COMMAND_TIMEOUT,
    silent: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command with robust error handling.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        silent: Whether to suppress command output

    Returns:
        CompletedProcess instance with command results
    """
    try:
        if not silent:
            print_message(f"Running: {' '.join(cmd)}", log=False)

        # Create a clean environment if not provided
        command_env = env if env is not None else os.environ.copy()

        result = subprocess.run(
            cmd,
            env=command_env,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        if not silent:
            print_error(f"Command failed: {' '.join(cmd)}", log=False)
            if e.stdout and len(e.stdout.strip()) > 0:
                console.print(f"[dim]{e.stdout.strip()}[/dim]")
            if e.stderr and len(e.stderr.strip()) > 0:
                console.print(f"[bold {NordColors.RED}]{e.stderr.strip()}[/]")

        log_message(f"Command failed: {' '.join(cmd)}", "ERROR")
        if e.stdout:
            log_message(f"Command stdout: {e.stdout.strip()}", "ERROR")
        if e.stderr:
            log_message(f"Command stderr: {e.stderr.strip()}", "ERROR")

        raise
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        if not silent:
            print_error(error_msg, log=False)
        log_message(error_msg, "ERROR")
        raise
    except Exception as e:
        error_msg = f"Error executing command: {' '.join(cmd)}\nDetails: {str(e)}"
        if not silent:
            print_error(error_msg, log=False)
        log_message(error_msg, "ERROR")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3, log=False)
    log_message("Cleanup performed")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    try:
        sig_name = signal.Signals(sig).name
    except (ValueError, AttributeError):
        sig_name = f"Signal {sig}"

    print_warning(f"Process interrupted by {sig_name}", log=False)
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
def check_root_privileges() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    if os.name == "posix":  # Linux/macOS
        return os.geteuid() == 0
    elif os.name == "nt":  # Windows
        try:
            # This will raise an error if not admin
            subprocess.check_output(
                "net session", shell=True, stderr=subprocess.DEVNULL
            )
            return True
        except:
            return False

    return False


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
        print_error(f"B2 CLI installation failed: {str(e)}")
        return False


def install_restic() -> bool:
    """
    Ensure Restic is installed.
    This function checks for Restic and attempts to install it if not found.

    Returns:
        True if installation successful or already installed, False otherwise
    """
    if shutil.which("restic"):
        print_success("Restic already installed")
        return True

    print_warning("Restic not found. Attempting to install...")

    try:
        # For Debian/Ubuntu based systems
        if shutil.which("apt"):
            run_command(["apt", "update"])
            run_command(["apt", "install", "-y", "restic"])
        # For Red Hat based systems
        elif shutil.which("dnf"):
            run_command(["dnf", "install", "-y", "restic"])
        # For macOS with Homebrew
        elif shutil.which("brew"):
            run_command(["brew", "install", "restic"])
        else:
            print_error("No supported package manager found to install Restic")
            return False

        if shutil.which("restic"):
            print_success("Restic installed successfully")
            return True
        else:
            print_error(
                "Restic installation failed: command not found after installation"
            )
            return False
    except Exception as e:
        print_error(f"Restic installation failed: {str(e)}")
        return False


def authorize_b2() -> bool:
    """
    Authorize the B2 CLI tool using the provided account ID and key.

    Returns:
        True if authorization successful, False otherwise
    """
    try:
        # Check if credentials are valid
        if (
            B2_ACCOUNT_ID == "YOUR_B2_ACCOUNT_ID"
            or B2_ACCOUNT_KEY == "YOUR_B2_ACCOUNT_KEY"
        ):
            print_error(
                "B2 credentials are not configured. Please update the script with your actual credentials."
            )
            return False

        run_command(["b2", "authorize-account", B2_ACCOUNT_ID, B2_ACCOUNT_KEY])
        print_success("B2 CLI tool authorized successfully")
        return True
    except Exception as e:
        print_error(f"B2 authorization failed: {str(e)}")
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
            return True
        else:
            print_warning(f"Bucket '{bucket}' not found. Creating it...")
            run_command(["b2", "create-bucket", bucket, "allPrivate"])
            print_success(f"Bucket '{bucket}' created")
            return True
    except Exception as e:
        print_error(f"Error ensuring bucket exists: {str(e)}")
        return False


# ----------------------------------------------------------------
# Restic Backup Functions
# ----------------------------------------------------------------
def check_restic_password() -> bool:
    """
    Check if the Restic password is properly configured.

    Returns:
        True if password is configured, False otherwise
    """
    if RESTIC_PASSWORD == "YOUR_RESTIC_PASSWORD":
        print_error(
            "Restic password is not configured. Please update the script with your actual password."
        )
        return False
    return True


def initialize_repository(service: str) -> bool:
    """
    Initialize the Restic repository for the given service if not already initialized.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if repository is ready, False on error
    """
    if not check_restic_password():
        return False

    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update({"RESTIC_PASSWORD": RESTIC_PASSWORD})

    display_panel(
        "Repository Initialization", style=NordColors.FROST_3, title=service.upper()
    )

    print_message(f"Checking repository: {repo}")

    try:
        # Try listing snapshots to check if repository exists
        run_command(["restic", "--repo", repo, "snapshots"], env=env, silent=True)
        print_success("Repository already initialized")
        return True
    except subprocess.CalledProcessError:
        print_warning("Repository not found. Initializing...")
        try:
            run_command(["restic", "--repo", repo, "init"], env=env)
            print_success("Repository initialized successfully")
            return True
        except Exception as e:
            print_error(f"Failed to initialize repository: {str(e)}")
            return False
    except Exception as e:
        print_error(f"Error during repository initialization: {str(e)}")
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
        return False

    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]

    display_panel(
        f"{config['name']} Backup", style=NordColors.FROST_2, title="Backup Operation"
    )
    log_message(f"Starting backup for {config['name']}")

    # Check service-specific paths
    all_paths_exist = True
    for path in config["paths"]:
        if not Path(path).exists():
            print_error(f"Required path {path} not found for {config['name']} backup.")
            log_message(f"Path {path} not found for {config['name']} backup", "ERROR")
            all_paths_exist = False

    if not all_paths_exist:
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
    log_message(f"Executing backup command for {service}")

    try:
        # Run backup command with enhanced progress display
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
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
                universal_newlines=True,
            )

            # Create a buffer to store the last few lines for debugging
            output_buffer = []
            max_buffer_size = 10

            # Update progress bar based on output
            progress_pattern = re.compile(r"(\d+\.\d+)% done")
            files_pattern = re.compile(r"Files:\s+(\d+) new,\s+(\d+) changed")

            for line in iter(process.stdout.readline, ""):
                # Keep the output buffer updated
                output_buffer.append(line.strip())
                if len(output_buffer) > max_buffer_size:
                    output_buffer.pop(0)

                # Try to extract progress percentage from Restic output
                match = progress_pattern.search(line)
                if match:
                    percent = float(match.group(1))
                    progress.update(backup_task, completed=percent)

                # Update the task description with file stats if available
                files_match = files_pattern.search(line)
                if files_match:
                    new_files = files_match.group(1)
                    changed_files = files_match.group(2)
                    progress.update(
                        backup_task,
                        description=f"Backing up {config['name']}... ({new_files} new, {changed_files} changed files)",
                    )

            # Wait for process to complete
            exit_code = process.wait()

            if exit_code != 0:
                print_error(f"Backup failed with exit code {exit_code}")
                log_message(f"Backup failed with exit code {exit_code}", "ERROR")
                log_message(f"Last output: {' | '.join(output_buffer)}", "ERROR")
                return False

        print_success(f"{config['name']} backup completed successfully")
        log_message(f"{config['name']} backup completed successfully")
        return True
    except Exception as e:
        print_error(f"Backup error: {str(e)}")
        log_message(f"Backup error for {service}: {str(e)}", "ERROR")
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
        result = run_command(retention_cmd, env=env, timeout=OPERATION_TIMEOUT)
        console.print(result.stdout.strip(), style=f"{NordColors.SNOW_STORM_1}")
        print_success("Retention policy applied successfully")
        return True
    except Exception as e:
        print_error(f"Retention policy application failed: {str(e)}")
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
        # First check if repository exists
        try:
            run_command(
                ["restic", "--repo", repo, "snapshots", "--compact"],
                env=env,
                silent=True,
            )
        except subprocess.CalledProcessError:
            print_warning(f"No repository found for {BACKUP_CONFIGS[service]['name']}")
            return False

        # Get the snapshots in JSON format for detailed processing
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
            table.add_column("Size", style=f"{NordColors.SNOW_STORM_1}")
            table.add_column("Paths", style=f"{NordColors.SNOW_STORM_1}")

            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

                # Format size if available
                size_str = "N/A"
                if "summary" in snap and "total_size" in snap["summary"]:
                    size_bytes = snap["summary"]["total_size"]
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes / 1024:.2f} KB"
                    elif size_bytes < 1024 * 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
                    else:
                        size_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

                paths = ", ".join(snap.get("paths", []))
                table.add_row(sid, time_str, size_str, paths)

            console.print(table)
            log_message(f"Found {len(snapshots)} snapshots for {service}")
        else:
            print_warning("No snapshots found")
            log_message("No snapshots found", "WARNING")

        return True
    except Exception as e:
        print_error(f"Failed to list snapshots: {str(e)}")
        return False


def backup_service(service: str) -> bool:
    """
    Execute a full backup workflow for a service: backup and apply retention.

    Args:
        service: Service identifier (system, vm, plex)

    Returns:
        True if all operations completed successfully, False otherwise
    """
    config = BACKUP_CONFIGS.get(service)
    if not config:
        print_error(f"Unknown service: {service}")
        return False

    print_message(f"Starting {config['name']} backup workflow...")
    log_message(f"Starting {service} backup workflow")

    # Perform backup
    if not perform_backup(service):
        return False

    # Apply retention policy
    if not apply_retention(service):
        print_warning("Backup was successful but retention policy application failed")
        return False

    # List snapshots after backup
    if not list_snapshots(service):
        print_warning(
            "Backup and retention were successful but listing snapshots failed"
        )

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
        print_message(f"Processing {BACKUP_CONFIGS[svc]['name']}...")
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

    # Log summary
    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)
    log_message(
        f"Completed backup of all services: {success_count}/{total_count} successful"
    )

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
    table.add_row("Restic Version", get_restic_version())
    table.add_row("B2 Bucket", B2_BUCKET)
    table.add_row("Retention Policy", RETENTION_POLICY)
    table.add_row("Log File", LOG_FILE)

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


def get_restic_version() -> str:
    """
    Get the installed Restic version.

    Returns:
        Version string or "Not installed"
    """
    try:
        result = run_command(["restic", "version"], silent=True)
        version_line = result.stdout.strip()
        # Extract version from output like "restic 0.12.1 compiled with go1.16.3 on darwin/amd64"
        match = re.search(r"restic (\d+\.\d+\.\d+)", version_line)
        if match:
            return match.group(1)
        return version_line
    except Exception:
        return "Not installed"


def create_menu_panel() -> Panel:
    """
    Create a styled panel containing the menu options.

    Returns:
        Panel containing formatted menu options
    """
    menu_text = Text()

    # Main operations
    menu_text.append("┌── ", style=f"{NordColors.FROST_3}")
    menu_text.append("Backup Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ───────────────┐\n", style=f"{NordColors.FROST_3}")

    menu_text.append("  1. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup System\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("  2. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Virtual Machines\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("  3. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup Plex Media Server\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("  4. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Backup All Services\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append(
        "└─────────────────────────────────────┘\n", style=f"{NordColors.FROST_3}"
    )
    menu_text.append("\n")

    # Snapshot operations
    menu_text.append("┌── ", style=f"{NordColors.FROST_3}")
    menu_text.append("Snapshot Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ─────────────────┐\n", style=f"{NordColors.FROST_3}")

    menu_text.append("  5. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append(
        "List Snapshots (per service)\n", style=f"{NordColors.SNOW_STORM_1}"
    )

    menu_text.append("  6. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("List All Snapshots\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append(
        "└─────────────────────────────────────┘\n", style=f"{NordColors.FROST_3}"
    )
    menu_text.append("\n")

    # System operations
    menu_text.append("┌── ", style=f"{NordColors.FROST_3}")
    menu_text.append("System Operations", style=f"bold {NordColors.FROST_2}")
    menu_text.append(" ──────────────────┐\n", style=f"{NordColors.FROST_3}")

    menu_text.append("  7. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Show System Information\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append("  8. ", style=f"bold {NordColors.FROST_1}")
    menu_text.append("Exit\n", style=f"{NordColors.SNOW_STORM_1}")

    menu_text.append(
        "└─────────────────────────────────────┘", style=f"{NordColors.FROST_3}"
    )

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

        choice = get_user_input("Select an option (1-8)", "8")

        if choice == "1":
            backup_service("system")
        elif choice == "2":
            backup_service("vm")
        elif choice == "3":
            backup_service("plex")
        elif choice == "4":
            backup_all_services()
        elif choice == "5":
            select_service_for_snapshots()
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
            show_system_info()
        elif choice == "8":
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

        wait_for_enter()


def select_service_for_snapshots() -> None:
    """Display a menu to select a service for listing snapshots."""
    console.clear()
    console.print(create_header())
    display_panel("Select Service", style=NordColors.FROST_2, title="Service Selection")

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
    service_table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for i, (svc, config) in enumerate(BACKUP_CONFIGS.items(), 1):
        service_table.add_row(str(i), config["name"], config["description"])

    console.print(service_table)
    console.print()

    svc_choice = get_user_input(f"Enter service number (1-{len(BACKUP_CONFIGS)})", "1")

    try:
        svc_idx = int(svc_choice) - 1
        if 0 <= svc_idx < len(BACKUP_CONFIGS):
            service = list(BACKUP_CONFIGS.keys())[svc_idx]
            list_snapshots(service)
        else:
            print_error(f"Invalid selection: {svc_choice}")
    except ValueError:
        print_error(f"Invalid input: {svc_choice}")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function to run the backup script."""
    console.clear()
    console.print(create_header())

    # Check if running as root (required for system backups)
    if not check_root_privileges():
        display_panel(
            "Warning: This script is not running with administrator privileges.\n"
            "Some backup operations, especially system backups, may fail due to permission issues.",
            style=NordColors.YELLOW,
            title="Permission Warning",
        )
        if not get_user_confirmation("Continue anyway?", True):
            display_panel(
                "Exiting as requested. Please restart with appropriate privileges.",
                style=NordColors.FROST_2,
                title="Exit",
            )
            sys.exit(0)

    display_panel(
        f"Starting Unified Restic Backup Manager\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        style=NordColors.FROST_2,
        title="Initialization",
    )

    setup_logging()

    # Check configuration
    if (
        B2_ACCOUNT_ID == "YOUR_B2_ACCOUNT_ID"
        or B2_ACCOUNT_KEY == "YOUR_B2_ACCOUNT_KEY"
        or RESTIC_PASSWORD == "YOUR_RESTIC_PASSWORD"
    ):
        display_panel(
            "The script is using default placeholder values for credentials.\n"
            "Please update the script with your actual B2 and Restic credentials before running backups.",
            style=NordColors.YELLOW,
            title="Configuration Warning",
        )
        wait_for_enter()

    # Install and authorize B2 CLI, and ensure the bucket exists
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        console=console,
    ) as progress:
        task = progress.add_task("Setting up backup environment...", total=4)

        # Install Restic
        if not install_restic():
            print_error(
                "Failed to install or locate Restic. Some functions may not work."
            )
        progress.advance(task)

        # Install B2 CLI
        if not install_b2_cli():
            print_error(
                "Failed to install or locate B2 CLI. Some functions may not work."
            )
        progress.advance(task)

        # Only proceed with B2 setup if credentials are configured
        if (
            B2_ACCOUNT_ID != "YOUR_B2_ACCOUNT_ID"
            and B2_ACCOUNT_KEY != "YOUR_B2_ACCOUNT_KEY"
        ):
            if not authorize_b2():
                print_error("B2 authorization failed. Cloud backups may not work.")
            progress.advance(task)

            if not ensure_bucket_exists(B2_BUCKET):
                print_error(
                    "Failed to ensure B2 bucket exists. Cloud backups may not work."
                )
            progress.advance(task)
        else:
            print_warning("Skipping B2 setup due to missing credentials")
            progress.advance(task, 2)  # Skip 2 steps

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
