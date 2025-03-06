#!/usr/bin/env python3
"""
git commander
----------------------------------

A production-grade terminal application providing a feature-rich Git CLI toolkit.
This interactive CLI automatically scans for Git repositories in the user's GitHub
folder (/home/sawyer/github) and displays them in a menu. Once a repository is selected,
you can execute a range of Git commands such as status, pull, add, commit, push, and branch
management – all with dynamic ASCII banners, progress tracking, and comprehensive error handling.

Usage:
  Run the script and follow the interactive menu options.

Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import os
import sys
import signal
import subprocess
import time
import shutil
import json
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Any, Callable

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

# Enable rich traceback for debugging
install_rich_traceback(show_locals=True)
console: Console = Console()

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "git commander"
APP_SUBTITLE = "Your Interactive Git Toolkit"
VERSION = "1.0.0"
GITHUB_DIR = "/home/sawyer/github"  # Base directory for Git repositories
OPERATION_TIMEOUT = 30  # seconds for git command operations


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord theme color palette for consistent styling."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Return a gradient of frost colors for dynamic banner styling."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Repo:
    """
    Represents a Git repository with its name and file system path.

    Attributes:
        name: The repository name.
        path: The full file system path to the repository.
    """

    name: str
    path: str


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """
    Create a dynamic ASCII banner header using Pyfiglet.
    The banner adapts to terminal width and applies a Nord-themed frost gradient.
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts = ["slant", "small", "mini", "digital"]
    font_to_use = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]
    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    text_lines = []
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        text_lines.append(Text(line, style=f"bold {color}"))
    combined_text = Text()
    for i, line in enumerate(text_lines):
        combined_text.append(line)
        if i < len(text_lines) - 1:
            combined_text.append("\n")
    return Panel(
        combined_text,
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message with a given prefix and style."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print an error message in red."""
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    """Print a success message in green."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    print_message(message, NordColors.YELLOW, "⚠")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display a formatted panel with a title and message."""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Core Functionality
# ----------------------------------------------------------------
def find_git_repositories(base_dir: str) -> List[Repo]:
    """
    Scan the base directory for Git repositories.

    Args:
        base_dir: The directory in which to search for repositories.

    Returns:
        A list of Repo objects representing Git repositories.
    """
    repos: List[Repo] = []
    if not os.path.exists(base_dir):
        print_warning(f"Base directory {base_dir} does not exist.")
        return repos
    try:
        for entry in os.listdir(base_dir):
            repo_path = os.path.join(base_dir, entry)
            if os.path.isdir(repo_path) and os.path.exists(
                os.path.join(repo_path, ".git")
            ):
                repos.append(Repo(name=entry, path=repo_path))
    except Exception as e:
        print_error(f"Error scanning repositories: {e}")
    return repos


def run_git_command(repo: Repo, args: List[str]) -> Tuple[int, str]:
    """
    Execute a git command in the context of the given repository.

    Args:
        repo: The repository in which to run the command.
        args: List of git command arguments.

    Returns:
        A tuple containing (exit_code, output).

    Raises:
        Exception: If the command fails or times out.
    """
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=repo.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OPERATION_TIMEOUT,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception("Git command timed out.")


def git_status(repo: Repo) -> None:
    """Display the current git status for the repository."""
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching status...", total=None)
            code, output = run_git_command(repo, ["status"])
            progress.update(task, completed=100)
        display_panel("Git Status", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Status command failed: {e}")
        console.print_exception()


def git_pull(repo: Repo) -> None:
    """Pull the latest changes from the remote repository."""
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task("Pulling changes...", total=None)
            code, output = run_git_command(repo, ["pull"])
            progress.update(task, completed=100)
        print_success("Pull completed successfully.")
        display_panel("Git Pull", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Pull command failed: {e}")
        console.print_exception()


def git_add(repo: Repo) -> None:
    """Stage changes for commit."""
    try:
        choice = Confirm.ask("Add all changes?", default=True)
        if choice:
            args = ["add", "--all"]
        else:
            file_name = Prompt.ask("Enter the filename to add")
            args = ["add", file_name]
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task("Staging changes...", total=None)
            code, output = run_git_command(repo, args)
            progress.update(task, completed=100)
        print_success("Files staged successfully.")
    except Exception as e:
        print_error(f"Add command failed: {e}")
        console.print_exception()


def git_commit(repo: Repo) -> None:
    """Commit staged changes with a user-provided message."""
    try:
        commit_message = Prompt.ask("Enter commit message")
        if not commit_message.strip():
            print_warning("Empty commit message. Aborting commit.")
            return
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task("Committing changes...", total=None)
            code, output = run_git_command(repo, ["commit", "-m", commit_message])
            progress.update(task, completed=100)
        print_success("Commit successful.")
        display_panel("Git Commit", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Commit command failed: {e}")
        console.print_exception()


def git_push(repo: Repo) -> None:
    """Push committed changes to the remote repository."""
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task("Pushing changes...", total=None)
            code, output = run_git_command(repo, ["push"])
            progress.update(task, completed=100)
        print_success("Push completed successfully.")
        display_panel("Git Push", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Push command failed: {e}")
        console.print_exception()


def git_branch(repo: Repo) -> None:
    """List and optionally switch branches."""
    try:
        code, output = run_git_command(repo, ["branch"])
        display_panel("Git Branches", output, NordColors.FROST_2)
        if Confirm.ask("Switch branch?", default=False):
            branch_name = Prompt.ask("Enter branch name")
            with Progress(
                SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                TextColumn("[bold]{task.description}[/bold]"),
                console=console,
            ) as progress:
                task = progress.add_task("Switching branch...", total=None)
                code, out = run_git_command(repo, ["checkout", branch_name])
                progress.update(task, completed=100)
            print_success(f"Switched to branch {branch_name}.")
    except Exception as e:
        print_error(f"Branch operation failed: {e}")
        console.print_exception()


def git_log(repo: Repo) -> None:
    """Display the commit log."""
    try:
        code, output = run_git_command(
            repo, ["log", "--oneline", "--graph", "--decorate"]
        )
        display_panel("Git Log", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Log command failed: {e}")
        console.print_exception()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup operations before exiting."""
    try:
        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig, frame) -> None:
    """Gracefully handle termination signals (SIGINT, SIGTERM)."""
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ----------------------------------------------------------------
# Interactive Menu and Control Flow
# ----------------------------------------------------------------
def repo_menu(repo: Repo) -> None:
    """
    Display the Git command menu for a selected repository and process user input.

    Args:
        repo: The selected Git repository.
    """
    while True:
        clear_screen()
        console.print(create_header())
        display_panel("Repository", f"Path: {repo.path}", NordColors.FROST_3)
        console.print("Select a Git operation:")
        console.print("[1] Status")
        console.print("[2] Pull")
        console.print("[3] Add")
        console.print("[4] Commit")
        console.print("[5] Push")
        console.print("[6] Branch")
        console.print("[7] Log")
        console.print("[B] Back to Repository Selection")
        console.print("[Q] Quit")
        choice = Prompt.ask("Enter your choice").strip().lower()

        if choice in ("q", "quit", "exit"):
            clear_screen()
            console.print(
                Panel(
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                )
            )
            sys.exit(0)
        elif choice in ("b", "back"):
            break
        elif choice == "1":
            git_status(repo)
        elif choice == "2":
            git_pull(repo)
        elif choice == "3":
            git_add(repo)
        elif choice == "4":
            git_commit(repo)
        elif choice == "5":
            git_push(repo)
        elif choice == "6":
            git_branch(repo)
        elif choice == "7":
            git_log(repo)
        else:
            print_error("Invalid choice. Please try again.")
        Prompt.ask("Press Enter to continue")


def main_menu() -> None:
    """
    Display the main menu with the list of Git repositories
    and process user selection.
    """
    repos = find_git_repositories(GITHUB_DIR)
    if not repos:
        print_warning(
            "No Git repositories found. Please ensure repositories exist in your GitHub folder."
        )
        Prompt.ask("Press Enter to exit")
        sys.exit(0)

    while True:
        clear_screen()
        console.print(create_header())
        display_panel(
            "Repository Selection",
            f"Scanning Git repositories in {GITHUB_DIR}",
            NordColors.FROST_3,
        )
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_1}", box=box.ROUNDED
        )
        table.add_column(
            "#", style=f"bold {NordColors.FROST_4}", width=3, justify="right"
        )
        table.add_column(
            "Repository Name", style=f"bold {NordColors.FROST_2}", width=30
        )
        table.add_column("Path", style=NordColors.SNOW_STORM_1)

        for idx, repo in enumerate(repos, 1):
            table.add_row(str(idx), repo.name, repo.path)
        console.print(table)
        console.print(
            "\nSelect a repository by number, or type [B] to refresh, [Q] to quit."
        )
        choice = Prompt.ask("Enter your choice").strip().lower()
        if choice in ("q", "quit", "exit"):
            clear_screen()
            console.print(
                Panel(
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                )
            )
            sys.exit(0)
        elif choice in ("b", "back", "refresh"):
            repos = find_git_repositories(GITHUB_DIR)
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(repos):
                repo_menu(repos[idx])
            else:
                print_error("Invalid repository number.")
                Prompt.ask("Press Enter to continue")
        except ValueError:
            print_error("Invalid input. Please enter a valid number.")
            Prompt.ask("Press Enter to continue")


# ----------------------------------------------------------------
# Entry Point with Error Handling
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for git commander."""
    try:
        main_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
