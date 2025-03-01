#!/usr/bin/env python3
"""
Unified Restore Script (B2 CLI Version with Recursive Scan)

This script uses the B2 CLI tool to scan the sawyer-backups bucket for all restic
repositories (even nested ones). It displays a numbered list of available backups and prompts the user
to select one or more repositories to restore (multiple selections allowed via space‑separated numbers).
Each selected repository is restored into its own subfolder under the restore base directory.

Note: Run this script with root privileges.
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
from typing import Dict, List, Optional, Tuple, Any, Set

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

# ------------------------------
# Configuration
# ------------------------------
# Full path to the B2 CLI tool – update this path if necessary.
B2_CLI = "/home/sawyer/.local/bin/b2"

# B2 & Restic configuration
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Restore base directory (each repo will restore into its own subfolder here)
RESTORE_BASE = Path("/home/sawyer/restic_restore")

# Retry settings for restic commands
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Logging configuration
LOG_FILE = "/var/log/unified_restore.log"

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
    cmd: List[str], env=None, check=True, capture_output=True, timeout=None
):
    """Execute a command and handle errors appropriately."""
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
def signal_handler(sig, frame):
    """Handle signals like SIGINT and SIGTERM."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


def cleanup():
    """Perform cleanup tasks before exiting."""
    print_step("Performing cleanup tasks...")
    # Add any necessary cleanup steps here


# ------------------------------
# Logging Setup
# ------------------------------
def setup_logging() -> None:
    """Set up logging to file and console."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    with open(LOG_FILE, "a") as log_file:
        log_file.write(
            f"\n--- Restore session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )

    print_success(f"Logging to {LOG_FILE}")


def log_message(message: str, level: str = "INFO") -> None:
    """Log a message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log_file:
        log_file.write(f"{timestamp} - {level} - {message}\n")


# ------------------------------
# Core Functions
# ------------------------------
def check_root() -> bool:
    """Check if script is running with root privileges."""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        return False
    return True


def scan_for_repos() -> Dict[int, Tuple[str, str]]:
    """
    Recursively scan the B2 bucket for restic repositories.
    A repository is identified by the presence of a 'config' file.

    Returns:
        Dictionary mapping menu numbers to (repo_name, repo_path)
    """
    print_section("Scanning for Restic Repositories")
    repos: Dict[int, Tuple[str, str]] = {}
    seen: Set[str] = set()

    try:
        print_step(f"Scanning bucket {B2_BUCKET} for repositories...")
        with console.status("[bold #81A1C1]Scanning bucket...", spinner="dots"):
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
                    repo_path = f"b2:{B2_BUCKET}:{repo_folder}"
                    repos[len(repos) + 1] = (repo_name, repo_path)

        if repos:
            print_success(f"Found {len(repos)} restic repositories.")
            log_message(f"Found {len(repos)} repositories in bucket {B2_BUCKET}")
        else:
            print_warning(f"No restic repositories found in bucket {B2_BUCKET}.")
            log_message(f"No repositories found in bucket {B2_BUCKET}", "WARNING")

    except Exception as e:
        print_error(f"Error scanning B2 bucket: {e}")
        log_message(f"Error scanning B2 bucket: {e}", "ERROR")

    return repos


def run_restic(
    repo: str, args: List[str], capture_output: bool = False
) -> subprocess.CompletedProcess:
    """Run a restic command with retries on transient errors."""
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd = ["restic", "--repo", repo] + args
    log_message(f"Running command: {' '.join(cmd)}")

    retries = 0
    while retries <= MAX_RETRIES:
        try:
            return run_command(cmd, env=env, capture_output=capture_output)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                print_warning(
                    f"Transient error; retrying in {delay} seconds (attempt {retries}/{MAX_RETRIES})."
                )
                log_message(
                    f"Transient error in restic command; retrying in {delay} seconds (attempt {retries}/{MAX_RETRIES})",
                    "WARNING",
                )
                time.sleep(delay)
            else:
                print_error(f"Restic command failed: {error_msg}")
                log_message(f"Restic command failed: {error_msg}", "ERROR")
                raise

    error_msg = f"Max retries ({MAX_RETRIES}) exceeded in run_restic"
    print_error(error_msg)
    log_message(error_msg, "ERROR")
    raise RuntimeError(error_msg)


def get_latest_snapshot(repo: str) -> Optional[str]:
    """Retrieve the ID of the latest snapshot in the given repository."""
    try:
        print_step(f"Retrieving latest snapshot for {repo}...")
        with console.status("[bold #81A1C1]Retrieving snapshots...", spinner="dots"):
            result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
            snapshots = json.loads(result.stdout) if result.stdout else []

        if not snapshots:
            print_warning(f"No snapshots found in repository: {repo}")
            log_message(f"No snapshots found in repository: {repo}", "WARNING")
            return None

        latest = max(snapshots, key=lambda s: s.get("time", ""))
        snap_id = latest.get("id")
        snap_time = latest.get("time", "").split("T")[0]  # Just the date part

        print_success(f"Latest snapshot found: {snap_id} from {snap_time}")
        log_message(f"Latest snapshot for {repo} is {snap_id} from {snap_time}")
        return snap_id

    except Exception as e:
        print_error(f"Error retrieving snapshots for {repo}: {e}")
        log_message(f"Error retrieving snapshots for {repo}: {e}", "ERROR")
        return None


def restore_repo(repo: str, target: Path) -> bool:
    """Restore the latest snapshot from the given repository into the target directory."""
    print_section(f"Restoring Repository: {repo}")
    log_message(f"Starting restore of repository {repo} into {target}")

    # Get the latest snapshot
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        print_error(f"Skipping restore for {repo} – no snapshot found.")
        log_message(f"Skipping restore for {repo} – no snapshot found.", "ERROR")
        return False

    # Create target directory
    target.mkdir(parents=True, exist_ok=True)
    print_step(f"Restoring snapshot {snap_id} into {target}...")
    log_message(f"Restoring snapshot {snap_id} into {target}")

    try:
        # Perform the restore
        with console.status(f"[bold #81A1C1]Restoring from {repo}...", spinner="dots"):
            run_restic(
                repo, ["restore", snap_id, "--target", str(target)], capture_output=True
            )

        # Verify restore
        if not any(target.iterdir()):
            print_error(f"Restore failed: {target} is empty after restore.")
            log_message(f"Restore failed: {target} is empty after restore.", "ERROR")
            return False

        print_success(f"Successfully restored {repo} into {target}.")
        log_message(f"Successfully restored {repo} into {target}.")
        return True

    except Exception as e:
        print_error(f"Restore failed for {repo}: {e}")
        log_message(f"Restore failed for {repo}: {e}", "ERROR")
        return False


def display_repos(repos: Dict[int, Tuple[str, str]]) -> None:
    """Display the available repositories in a formatted table."""
    if not repos:
        print_warning("No repositories found.")
        return

    print_section("Available Restic Repositories")

    # Calculate column widths
    max_num_width = len(str(max(repos.keys())))
    max_name_width = max(len(name) for num, (name, _) in repos.items())

    # Print header
    console.print(
        f"  {'#'.ljust(max_num_width)}  {'Repository Name'.ljust(max_name_width)}  {'Path'}"
    )
    console.print(f"  {'-' * max_num_width}  {'-' * max_name_width}  {'-' * 30}")

    # Print repositories
    for num, (name, path) in repos.items():
        console.print(
            f"  {str(num).ljust(max_num_width)}  {name.ljust(max_name_width)}  {path}"
        )


def select_repos(repos: Dict[int, Tuple[str, str]]) -> Dict[int, Tuple[str, str]]:
    """Prompt user to select repositories for restore."""
    if not repos:
        return {}

    display_repos(repos)

    while True:
        console.print(
            "\nEnter the numbers of the repositories to restore (separated by spaces):"
        )
        console.print("Example: '1 3 5' or 'all' for all repositories")
        selection = input("> ").strip().lower()

        if not selection:
            print_warning("No selection made. Please try again.")
            continue

        # Check for "all" option
        if selection == "all":
            print_success("All repositories selected.")
            return repos

        # Parse individual selections
        try:
            choices = [int(num) for num in selection.split()]

            # Validate choices
            invalid = [num for num in choices if num not in repos]
            if invalid:
                print_error(f"Invalid selections: {', '.join(map(str, invalid))}")
                continue

            selected = {num: repos[num] for num in choices}

            if not selected:
                print_warning("No valid repositories selected. Please try again.")
                continue

            print_success(f"Selected {len(selected)} repositories for restore.")
            return selected

        except ValueError:
            print_error(
                "Invalid input. Please enter valid numbers separated by spaces."
            )


def single_repo_input() -> Dict[int, Tuple[str, str]]:
    """Get a single repository path from user input."""
    print_section("Manual Repository Input")
    print_step("Enter a complete restic repository path.")
    print_step("Example: 'b2:sawyer-backups:some/repo'")

    repo_path = input("Repository path: ").strip()

    if not repo_path:
        print_error("No repository path provided.")
        return {}

    # Extract a reasonable name from the path
    if ":" in repo_path:
        parts = repo_path.split(":")
        repo_name = parts[-1].split("/")[-1] if "/" in parts[-1] else parts[-1]
    else:
        repo_name = "CustomRepo"

    return {1: (repo_name, repo_path)}


def interactive_menu() -> None:
    """Display and handle the interactive menu."""
    while True:
        print_header("Unified Restore")
        console.print("1. Scan for Repositories")
        console.print("2. Enter Repository Path Manually")
        console.print("3. Exit")

        choice = input("\nSelect an option (1-3): ").strip()

        if choice == "1":
            # Scan and restore from found repositories
            available_repos = scan_for_repos()

            if not available_repos:
                print_error(f"No restic repositories found in bucket {B2_BUCKET}.")
                input("\nPress Enter to return to the menu...")
                continue

            selected_repos = select_repos(available_repos)

            if selected_repos:
                start_time = time.time()
                results = {}

                # Process each selected repository
                for _, (repo_name, repo_path) in selected_repos.items():
                    target_dir = RESTORE_BASE / repo_name
                    result = restore_repo(repo_path, target_dir)
                    results[repo_name] = result

                # Display summary
                total_time = time.time() - start_time
                print_summary(results, total_time)

            input("\nPress Enter to return to the menu...")

        elif choice == "2":
            # Manual repository input
            selected_repo = single_repo_input()

            if selected_repo:
                start_time = time.time()
                results = {}

                for _, (repo_name, repo_path) in selected_repo.items():
                    target_dir = RESTORE_BASE / repo_name
                    result = restore_repo(repo_path, target_dir)
                    results[repo_name] = result

                total_time = time.time() - start_time
                print_summary(results, total_time)

            input("\nPress Enter to return to the menu...")

        elif choice == "3":
            print_header("Exiting")
            break

        else:
            print_warning("Invalid selection, please try again.")


def print_summary(results: Dict[str, bool], total_time: float) -> None:
    """Print a summary of the restore operations."""
    print_header("Restore Summary")

    if not results:
        print_warning("No repositories were restored.")
        return

    # Calculate success/failure counts
    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful

    console.print(f"\n[bold #D8DEE9]Restore Statistics:[/bold #D8DEE9]")
    console.print(f"Total repositories: {len(results)}")
    console.print(f"Successfully restored: {successful}")
    console.print(f"Failed to restore: {failed}")
    console.print(f"Total restore time: {total_time:.2f} seconds")

    # Print individual results
    print_section("Repository Results")
    for repo_name, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        color = "#8FBCBB" if success else "#BF616A"
        console.print(f"{repo_name}: [bold {color}]{status}[/bold {color}]")

    # Log the summary
    log_message(
        f"Restore summary: {successful} successful, {failed} failed, {total_time:.2f} seconds"
    )


def main() -> None:
    # Setup signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_header("Unified Restore Script")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )

    setup_logging()

    if not check_root():
        sys.exit(1)

    # Make sure the restore base directory exists
    if not RESTORE_BASE.exists():
        try:
            RESTORE_BASE.mkdir(parents=True, exist_ok=True)
            print_success(f"Created restore base directory: {RESTORE_BASE}")
        except Exception as e:
            print_error(f"Failed to create restore directory {RESTORE_BASE}: {e}")
            sys.exit(1)

    interactive_menu()

    print_success("Script execution completed.")
    log_message("Script execution completed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Script interrupted by user.")
        log_message("Script interrupted by user.", "WARNING")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        log_message(f"Unhandled error: {e}", "ERROR")
        import traceback

        traceback.print_exc()
        sys.exit(1)
