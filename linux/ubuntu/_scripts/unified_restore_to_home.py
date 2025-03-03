#!/usr/bin/env python3
"""
Unified Restore Script
--------------------------------------------------

A streamlined terminal interface for restoring data from Backblaze B2 using Restic.
Features repository discovery, status monitoring, and secure restoration process with Nord theme styling.

This script scans the specified Backblaze B2 bucket for all restic repositories (even nested ones),
displays a numbered list of available repositories, and allows the user to select one or more for restore.
Each selected repository is restored into its own subfolder under the restore base directory.

Usage:
  Run the script with root privileges to ensure proper restoration of all file permissions.
  - Option 1: Scan for Repositories - Automatically discover repositories in your B2 bucket
  - Option 2: Enter Repository Path Manually - Directly specify a repository path
  - Option 3: Exit - Quit the application

Version: 1.0.0
"""

import atexit
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set, Any, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
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
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
# Path to the B2 CLI tool – update this if necessary
B2_CLI: str = "/home/sawyer/.local/bin/b2"

# B2 & Restic configuration
B2_ACCOUNT_ID: str = "12345678"
B2_ACCOUNT_KEY: str = "12345678"
B2_BUCKET: str = "sawyer-backups"
RESTIC_PASSWORD: str = "12345678"  # Restic password baked into the script

# Restore base directory (each repository will be restored into its own subfolder here)
RESTORE_BASE: Path = Path("/home/sawyer/restic_restore")

# Retry settings for restic commands
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds

# Logging configuration
LOG_FILE: str = "/var/log/unified_restore.log"

# Application information
VERSION: str = "1.0.0"
APP_NAME: str = "Unified Restore"
APP_SUBTITLE: str = "B2 & Restic Recovery Tool"


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
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Repository:
    """
    Represents a Restic repository with its details.

    Attributes:
        name: The repository name or identifier
        path: Full repository path for Restic operations
        has_snapshots: Whether the repository has any snapshots
    """

    name: str
    path: str
    has_snapshots: Optional[bool] = (
        None  # True if has snapshots, False if none, None if unknown
    )


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
             _  __ _          _                 _                 
 _   _ _ __ (_)/ _(_) ___  __| |  _ __ ___  ___| |_ ___  _ __ ___ 
| | | | '_ \| | |_| |/ _ \/ _` | | '__/ _ \/ __| __/ _ \| '__/ _ \
| |_| | | | | |  _| |  __/ (_| | | | |  __/\__ \ || (_) | | |  __/
 \__,_|_| |_|_|_| |_|\___|\__,_| |_|  \___||___/\__\___/|_|  \___|
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

    # Add decorative tech elements (shorter than before)
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),  # Reduced padding
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
    """Set up logging to file."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(
            f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
    print_message(f"Logging to {LOG_FILE}", NordColors.FROST_1)


def log_message(message: str, level: str = "INFO") -> None:
    """Append a log message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")


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
    Executes a system command and returns the CompletedProcess.

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
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)
    log_message("Cleanup initiated")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    log_message(f"Process interrupted by signal {sig_name}", "WARNING")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Repository Operations
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        True if the script is running as root, False otherwise
    """
    if os.geteuid() != 0:
        display_panel(
            "This script must be run with root privileges to ensure proper restoration of file permissions.",
            style=NordColors.RED,
            title="Insufficient Privileges",
        )
        log_message("Script not running with root privileges", "ERROR")
        return False
    return True


def scan_for_repos() -> Dict[int, Repository]:
    """
    Recursively scan the B2 bucket for restic repositories.
    A repository is identified by the presence of a 'config' file.

    Returns:
        A dictionary mapping menu numbers to Repository objects.
    """
    display_panel(
        f"Scanning B2 bucket '{B2_BUCKET}' for restic repositories...",
        style=NordColors.FROST_3,
        title="Repository Discovery",
    )

    repos: Dict[int, Repository] = {}
    seen: Set[str] = set()

    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Scanning bucket for repositories"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]Scanning..."),
            console=console,
        ) as progress:
            scan_task = progress.add_task("Scanning", total=None)

            cmd = [B2_CLI, "ls", B2_BUCKET, "--recursive"]
            result = run_command(cmd)

            for line in result.stdout.splitlines():
                line = line.strip()
                parts = line.split("/")
                if parts[-1] == "config" and len(parts) > 1:
                    repo_folder = "/".join(parts[:-1])
                    if repo_folder in seen:
                        continue
                    seen.add(repo_folder)
                    repo_name = repo_folder.split("/")[-1]
                    # Construct repository path in Restic format
                    repo_path = f"b2:{B2_BUCKET}:{repo_folder}"
                    repos[len(repos) + 1] = Repository(name=repo_name, path=repo_path)

                    # Update progress for visual feedback
                    progress.update(
                        scan_task,
                        description=f"[bold {NordColors.FROST_2}]Found {len(repos)} repositories",
                    )

            # Final progress update
            progress.update(
                scan_task, description=f"[bold {NordColors.FROST_2}]Scan complete"
            )

        if repos:
            print_message(
                f"Found {len(repos)} restic repositories", NordColors.GREEN, "✓"
            )
            log_message(f"Found {len(repos)} repositories in bucket {B2_BUCKET}")
        else:
            print_message(
                f"No restic repositories found in bucket {B2_BUCKET}",
                NordColors.YELLOW,
                "⚠",
            )
            log_message(f"No repositories found in bucket {B2_BUCKET}", "WARNING")
    except Exception as e:
        display_panel(
            f"Error scanning B2 bucket: {e}",
            style=NordColors.RED,
            title="Scan Error",
        )
        log_message(f"Error scanning B2 bucket: {e}", "ERROR")

    return repos


def run_restic(
    repo: str, args: List[str], capture_output: bool = True
) -> subprocess.CompletedProcess:
    """
    Run a restic command with the appropriate environment variables.
    Retries the command up to MAX_RETRIES on transient errors.

    Args:
        repo: Repository path
        args: Restic command arguments
        capture_output: Whether to capture command output

    Returns:
        CompletedProcess instance with command results
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + args
    log_message(f"Running restic command: {' '.join(cmd)}")

    retries = 0
    while retries <= MAX_RETRIES:
        try:
            return run_command(cmd, env=env, capture_output=capture_output)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                print_message(
                    f"Transient error; retrying in {delay} seconds (attempt {retries}/{MAX_RETRIES})",
                    NordColors.YELLOW,
                    "⚠",
                )
                log_message(
                    f"Transient error in restic command; retrying in {delay} seconds (attempt {retries}/{MAX_RETRIES})",
                    "WARNING",
                )
                time.sleep(delay)
            else:
                display_panel(
                    f"Restic command failed: {error_msg}",
                    style=NordColors.RED,
                    title="Command Error",
                )
                log_message(f"Restic command failed: {error_msg}", "ERROR")
                raise

    error_msg = f"Max retries ({MAX_RETRIES}) exceeded in run_restic"
    display_panel(error_msg, style=NordColors.RED, title="Error")
    log_message(error_msg, "ERROR")
    raise RuntimeError(error_msg)


def get_latest_snapshot(repo: str) -> Optional[str]:
    """
    Retrieve the ID of the latest snapshot from the given repository.

    Args:
        repo: Repository path

    Returns:
        The snapshot ID as a string, or None if no snapshots are found.
    """
    try:
        print_message(
            f"Retrieving latest snapshot for {repo}...", NordColors.FROST_2, ">"
        )

        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Retrieving snapshots..."),
            console=console,
        ) as progress:
            task = progress.add_task("Retrieving", total=None)
            result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
            snapshots = json.loads(result.stdout) if result.stdout else []

        if not snapshots:
            print_message(
                f"No snapshots found in repository: {repo}", NordColors.YELLOW, "⚠"
            )
            log_message(f"No snapshots found in repository: {repo}", "WARNING")
            return None

        latest = max(snapshots, key=lambda s: s.get("time", ""))
        snap_id = latest.get("id")
        snap_date = latest.get("time", "").split("T")[0]
        print_message(
            f"Latest snapshot: {snap_id} from {snap_date}", NordColors.GREEN, "✓"
        )
        log_message(f"Latest snapshot for {repo} is {snap_id} from {snap_date}")
        return snap_id

    except Exception as e:
        display_panel(
            f"Error retrieving snapshots for {repo}: {e}",
            style=NordColors.RED,
            title="Snapshot Error",
        )
        log_message(f"Error retrieving snapshots for {repo}: {e}", "ERROR")
        return None


def restore_repo(repo: str, target: Path) -> bool:
    """
    Restore the latest snapshot from the given repository into the target directory.

    Args:
        repo: Repository path
        target: Target directory for restoration

    Returns:
        True if restoration was successful, False otherwise
    """
    display_panel(
        f"Restoring from repository: {repo}",
        style=NordColors.FROST_3,
        title="Restore Operation",
    )
    log_message(f"Starting restore of repository {repo} into {target}")

    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        display_panel(
            f"Cannot restore {repo} - no snapshots found.",
            style=NordColors.RED,
            title="Restore Error",
        )
        log_message(f"Skipping restore for {repo} – no snapshot found.", "ERROR")
        return False

    target.mkdir(parents=True, exist_ok=True)
    print_message(
        f"Restoring snapshot {snap_id} into {target}...", NordColors.FROST_2, ">"
    )
    log_message(f"Restoring snapshot {snap_id} into {target}")

    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Restoring data"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]Please wait..."),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            restore_task = progress.add_task("Restoring", total=None)

            # Run the restore operation
            run_restic(
                repo, ["restore", snap_id, "--target", str(target)], capture_output=True
            )

            # Check if anything was restored
            if not any(target.iterdir()):
                display_panel(
                    f"Restore failed: {target} is empty after restore operation.",
                    style=NordColors.RED,
                    title="Restore Failed",
                )
                log_message(
                    f"Restore failed: {target} is empty after restore.", "ERROR"
                )
                return False

            display_panel(
                f"Successfully restored repository into {target}",
                style=NordColors.GREEN,
                title="Restore Complete",
            )
            log_message(f"Successfully restored {repo} into {target}.")
            return True

    except Exception as e:
        display_panel(
            f"Restore failed for {repo}: {e}",
            style=NordColors.RED,
            title="Restore Error",
        )
        log_message(f"Restore failed for {repo}: {e}", "ERROR")
        return False


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_repo_table(repos: Dict[int, Repository]) -> Table:
    """
    Create a table displaying repository information.

    Args:
        repos: Dictionary of repositories

    Returns:
        A Rich Table object containing the repository information
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Available Restic Repositories[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=4)
    table.add_column("Repository Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Path", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column("Status", justify="center", width=10)

    for idx, repo in repos.items():
        # Create status indicator
        if repo.has_snapshots is True:
            status = Text("● READY", style=f"bold {NordColors.GREEN}")
        elif repo.has_snapshots is False:
            status = Text("● EMPTY", style=f"bold {NordColors.YELLOW}")
        else:
            status = Text("○ UNKNOWN", style=f"dim {NordColors.POLAR_NIGHT_4}")

        table.add_row(str(idx), repo.name, repo.path, status)

    return table


def display_repos(repos: Dict[int, Repository]) -> None:
    """
    Display available repositories in a styled table.

    Args:
        repos: Dictionary of repositories
    """
    if not repos:
        display_panel(
            "No repositories found. Try entering a repository path manually.",
            style=NordColors.YELLOW,
            title="No Repositories",
        )
        return

    console.print(create_repo_table(repos))


def check_snapshot_status(repos: Dict[int, Repository]) -> Dict[int, Repository]:
    """
    Check which repositories have snapshots available.

    Args:
        repos: Dictionary of repositories

    Returns:
        Updated dictionary with snapshot availability information
    """
    display_panel(
        "Checking snapshot availability for repositories...",
        style=NordColors.FROST_3,
        title="Snapshot Verification",
    )

    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Checking repository"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking", total=len(repos))

        for idx, repo in repos.items():
            # Update the progress description to show which repo we're checking
            progress.update(
                task, description=f"[bold {NordColors.FROST_2}]Checking {repo.name}"
            )

            try:
                # Try to get snapshots but just check if any exist
                result = run_restic(
                    repo.path, ["snapshots", "--json"], capture_output=True
                )
                snapshots = json.loads(result.stdout) if result.stdout else []
                repo.has_snapshots = len(snapshots) > 0
            except Exception:
                # If there's an error, we just mark as unknown
                repo.has_snapshots = None

            # Advance the progress bar
            progress.advance(task)

    return repos


def select_repos(repos: Dict[int, Repository]) -> Dict[int, Repository]:
    """
    Prompt the user to select repositories for restore.

    Args:
        repos: Dictionary of available repositories

    Returns:
        Dictionary of selected repositories
    """
    if not repos:
        return {}

    # Check which repositories have snapshots
    repos = check_snapshot_status(repos)

    # Display the repos with their snapshot status
    display_repos(repos)

    while True:
        console.print(
            f"\n[bold {NordColors.FROST_2}]Enter repository numbers to restore (space-separated) or 'all':[/]",
            end=" ",
        )
        selection = input().strip().lower()

        if not selection:
            print_message(
                "No selection made. Please try again.", NordColors.YELLOW, "⚠"
            )
            continue

        if selection == "all":
            print_message("All repositories selected.", NordColors.GREEN, "✓")
            return repos

        try:
            choices = [int(num) for num in selection.split()]
            invalid = [num for num in choices if num not in repos]

            if invalid:
                print_message(
                    f"Invalid selections: {', '.join(map(str, invalid))}",
                    NordColors.RED,
                    "✗",
                )
                continue

            selected = {num: repos[num] for num in choices}

            if not selected:
                print_message(
                    "No valid repositories selected. Please try again.",
                    NordColors.YELLOW,
                    "⚠",
                )
                continue

            print_message(
                f"Selected {len(selected)} repositories for restore.",
                NordColors.GREEN,
                "✓",
            )
            return selected

        except ValueError:
            print_message(
                "Invalid input. Please enter valid numbers separated by spaces.",
                NordColors.RED,
                "✗",
            )


def single_repo_input() -> Dict[int, Repository]:
    """
    Prompt the user to manually enter a complete restic repository path.

    Returns:
        Dictionary with one repository entry
    """
    display_panel(
        "Manually specify a Restic repository path to restore from.",
        style=NordColors.FROST_3,
        title="Manual Repository Input",
    )

    console.print(
        f"[bold {NordColors.FROST_2}]Enter a complete repository path (e.g., 'b2:{B2_BUCKET}:some/repo'):[/]"
    )
    repo_path = input("> ").strip()

    if not repo_path:
        print_message("No repository path provided.", NordColors.RED, "✗")
        return {}

    # Extract a reasonable name from the path
    repo_name = (
        repo_path.split(":")[-1].split("/")[-1] if ":" in repo_path else "manual-repo"
    )

    return {1: Repository(name=repo_name, path=repo_path)}


def print_summary(results: Dict[str, bool], total_time: float) -> None:
    """
    Print a summary of the restore operations.

    Args:
        results: Dictionary mapping repository names to success status
        total_time: Total time taken for the restore operations
    """
    display_panel(
        "Restore Operations Summary", style=NordColors.FROST_1, title="Summary"
    )

    if not results:
        print_message("No repositories were restored.", NordColors.YELLOW, "⚠")
        return

    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful

    # Create a summary table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_3,
    )

    table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

    table.add_row("Total repositories", str(len(results)))
    table.add_row("Successfully restored", f"[bold {NordColors.GREEN}]{successful}[/]")
    table.add_row("Failed to restore", f"[bold {NordColors.RED}]{failed}[/]")
    table.add_row("Total restore time", f"{total_time:.2f} seconds")

    console.print(table)

    # Repository results
    console.print(f"\n[bold {NordColors.FROST_2}]Repository Results:[/]")

    repo_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        border_style=NordColors.FROST_4,
    )

    repo_table.add_column("Repository", style=f"{NordColors.FROST_2}")
    repo_table.add_column("Status", justify="center")

    for repo_name, success in results.items():
        status_text = "[bold green]SUCCESS[/]" if success else "[bold red]FAILED[/]"
        repo_table.add_row(repo_name, status_text)

    console.print(repo_table)

    log_message(
        f"Restore summary: {successful} successful, {failed} failed, {total_time:.2f} seconds"
    )


# ----------------------------------------------------------------
# Interactive Menu
# ----------------------------------------------------------------
def interactive_menu() -> None:
    """
    Display the interactive menu and process user input.
    """
    while True:
        console.clear()
        console.print(create_header())

        # Display the current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Base Restore Directory: {RESTORE_BASE}[/]"
            )
        )
        console.print()

        # Menu options
        menu_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.FROST_2}]1.[/] [bold {NordColors.SNOW_STORM_1}]Scan for Repositories[/]\n"
                f"[bold {NordColors.FROST_2}]2.[/] [bold {NordColors.SNOW_STORM_1}]Enter Repository Path Manually[/]\n"
                f"[bold {NordColors.FROST_2}]3.[/] [bold {NordColors.SNOW_STORM_1}]Exit[/]"
            ),
            border_style=Style(color=NordColors.FROST_3),
            title=f"[bold {NordColors.FROST_2}]Menu Options[/]",
            padding=(1, 2),
        )
        console.print(menu_panel)

        console.print(f"[bold {NordColors.FROST_2}]Select an option (1-3):[/]", end=" ")
        choice = input().strip()

        if choice == "1":
            # Scan for repositories
            available_repos = scan_for_repos()
            if not available_repos:
                display_panel(
                    f"No restic repositories found in bucket {B2_BUCKET}.",
                    style=NordColors.YELLOW,
                    title="No Repositories Found",
                )
                input(
                    f"\n[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
                )
                continue

            selected_repos = select_repos(available_repos)
            if selected_repos:
                start_time = time.time()
                results = {}

                for _, repo in selected_repos.items():
                    target_dir = RESTORE_BASE / repo.name
                    result = restore_repo(repo.path, target_dir)
                    results[repo.name] = result

                total_time = time.time() - start_time
                print_summary(results, total_time)

            input(
                f"\n[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )

        elif choice == "2":
            # Manual repository input
            selected_repo = single_repo_input()
            if selected_repo:
                start_time = time.time()
                results = {}

                for _, repo in selected_repo.items():
                    target_dir = RESTORE_BASE / repo.name
                    result = restore_repo(repo.path, target_dir)
                    results[repo.name] = result

                total_time = time.time() - start_time
                print_summary(results, total_time)

            input(
                f"\n[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )

        elif choice == "3":
            # Exit
            display_panel(
                "Thank you for using the Unified Restore Script!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break

        else:
            print_message(
                "Invalid selection, please try again.", NordColors.YELLOW, "⚠"
            )
            time.sleep(1)


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main application function that handles the UI flow and user interaction.
    """
    console.clear()
    console.print(create_header())

    # Display the current date and time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/]")
    )
    console.print()

    # Setup logging
    setup_logging()

    # Check for root privileges
    if not check_root():
        input(f"\n[{NordColors.SNOW_STORM_1}]Press Enter to exit...[/]")
        sys.exit(1)

    # Ensure restore base directory exists
    if not RESTORE_BASE.exists():
        try:
            RESTORE_BASE.mkdir(parents=True, exist_ok=True)
            print_message(
                f"Created restore base directory: {RESTORE_BASE}", NordColors.GREEN, "✓"
            )
        except Exception as e:
            display_panel(
                f"Failed to create restore directory {RESTORE_BASE}: {e}",
                style=NordColors.RED,
                title="Directory Error",
            )
            log_message(
                f"Failed to create restore directory {RESTORE_BASE}: {e}", "ERROR"
            )
            input(f"\n[{NordColors.SNOW_STORM_1}]Press Enter to exit...[/]")
            sys.exit(1)

    # Run the interactive menu
    interactive_menu()

    print_message("Script execution completed.", NordColors.GREEN, "✓")
    log_message("Script execution completed.")


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel(
            "Operation cancelled by user", style=NordColors.YELLOW, title="Cancelled"
        )
        log_message("Script interrupted by user.", "WARNING")
        sys.exit(130)
    except Exception as e:
        display_panel(f"Unhandled error: {str(e)}", style=NordColors.RED, title="Error")
        console.print_exception()
        log_message(f"Unhandled error: {e}", "ERROR")
        sys.exit(1)
