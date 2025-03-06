#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import shutil
import json
import asyncio
import atexit
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast

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

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "git commander"
APP_SUBTITLE: str = "Your Interactive Git Toolkit"
VERSION: str = "1.0.0"
GITHUB_DIR: str = os.path.expanduser("~/github")  # Base directory for Git repositories
OPERATION_TIMEOUT: int = 30  # seconds for git command operations

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/git_commander")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")


class NordColors:
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


@dataclass
class Repo:
    """
    Represents a Git repository with its name and file system path.

    Attributes:
        name: The repository name.
        path: The full file system path to the repository.
        status: Current Git status information (lazily loaded).
        branch: Current branch name (lazily loaded).
    """

    name: str
    path: str
    status: Optional[str] = None
    branch: Optional[str] = None
    last_checked: float = field(default_factory=time.time)


T = TypeVar("T")


@dataclass
class AppConfig:
    github_dir: str = GITHUB_DIR
    default_push_flags: List[str] = field(default_factory=lambda: [])
    default_pull_flags: List[str] = field(default_factory=lambda: ["--rebase"])
    last_used_repos: List[str] = field(default_factory=list)
    favorite_repos: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Global variables to track async tasks
_background_task = None


# UI Helper Functions
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "mini", "digital"]
    font_to_use: str = fonts[0]
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
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")

    # Add subtitle with spacing
    if APP_SUBTITLE:
        combined_text.append("\n")
        combined_text.append(Text(APP_SUBTITLE, style=f"italic {NordColors.FROST_2}"))

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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# Core Functionality
def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


def run_command(args: List[str], cwd: Optional[str] = None) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OPERATION_TIMEOUT,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception("Command timed out.")


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

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]{task.description}[/bold]"),
        console=console,
    ) as progress:
        scan_task = progress.add_task(
            f"[{NordColors.FROST_2}]Scanning for repositories...", total=None
        )

        try:
            # First-level scan - direct subdirectories
            for entry in os.listdir(base_dir):
                entry_path = os.path.join(base_dir, entry)
                progress.update(
                    scan_task, description=f"[{NordColors.FROST_2}]Checking {entry}..."
                )

                if os.path.isdir(entry_path):
                    git_dir = os.path.join(entry_path, ".git")
                    if os.path.exists(git_dir) and os.path.isdir(git_dir):
                        repos.append(Repo(name=entry, path=entry_path))
                    else:
                        # Also scan one level deeper for organization directories
                        try:
                            for subentry in os.listdir(entry_path):
                                subentry_path = os.path.join(entry_path, subentry)
                                if os.path.isdir(subentry_path):
                                    git_dir = os.path.join(subentry_path, ".git")
                                    if os.path.exists(git_dir) and os.path.isdir(
                                        git_dir
                                    ):
                                        # Use org/repo naming
                                        repo_name = f"{entry}/{subentry}"
                                        repos.append(
                                            Repo(name=repo_name, path=subentry_path)
                                        )
                        except Exception:
                            # Skip if we can't access a subdirectory
                            pass
        except Exception as e:
            print_error(f"Error scanning repositories: {e}")

        progress.update(
            scan_task,
            description=f"[{NordColors.FROST_2}]Found {len(repos)} repositories",
            completed=100,
        )
        time.sleep(0.5)  # Give user a moment to see results

    return repos


async def async_check_git_branch(repo: Repo) -> None:
    """Asynchronously get the current branch for a repository."""
    try:
        cmd = ["git", "-C", repo.path, "branch", "--show-current"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            repo.branch = stdout.decode().strip()
    except Exception:
        repo.branch = None


async def async_check_git_repos(repos: List[Repo]) -> None:
    """Asynchronously update the status of multiple repositories."""
    tasks = [async_check_git_branch(repo) for repo in repos]
    await asyncio.gather(*tasks)


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
    return run_command(cmd, repo.path)


def git_status(repo: Repo) -> None:
    """Display the current git status for the repository."""
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Fetching status...", total=100
            )

            # First get branch info
            for step, pct in [
                (f"[{NordColors.FROST_2}]Checking branch information...", 20),
                (f"[{NordColors.FROST_2}]Reading status...", 60),
            ]:
                time.sleep(0.2)
                progress.update(task, description=step, completed=pct)

            code, output = run_git_command(repo, ["status"])
            time.sleep(0.2)
            progress.update(
                task, description=f"[{NordColors.GREEN}]Status retrieved", completed=100
            )

        # Save status for later reference
        repo.status = output
        repo.last_checked = time.time()

        display_panel("Git Status", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Status command failed: {e}")
        console.print_exception()


def git_pull(repo: Repo) -> None:
    """Pull the latest changes from the remote repository."""
    config = load_config()

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Pulling changes...", total=100
            )

            for step, pct in [
                (f"[{NordColors.FROST_2}]Fetching remote changes...", 30),
                (f"[{NordColors.FROST_2}]Merging remote changes...", 70),
            ]:
                time.sleep(0.3)
                progress.update(task, description=step, completed=pct)

            # Use configured pull flags
            args = ["pull"] + config.default_pull_flags
            code, output = run_git_command(repo, args)

            time.sleep(0.3)
            progress.update(
                task, description=f"[{NordColors.GREEN}]Pull completed", completed=100
            )

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
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Staging changes...", total=100
            )

            for step, pct in [
                (f"[{NordColors.FROST_2}]Analyzing changes...", 30),
                (f"[{NordColors.FROST_2}]Updating index...", 70),
            ]:
                time.sleep(0.2)
                progress.update(task, description=step, completed=pct)

            code, output = run_git_command(repo, args)

            time.sleep(0.2)
            progress.update(
                task, description=f"[{NordColors.GREEN}]Changes staged", completed=100
            )

        print_success("Files staged successfully.")
        # Show status after adding
        time.sleep(0.5)
        git_status(repo)
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
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Committing changes...", total=100
            )

            for step, pct in [
                (f"[{NordColors.FROST_2}]Preparing commit...", 30),
                (f"[{NordColors.FROST_2}]Applying changes...", 70),
            ]:
                time.sleep(0.3)
                progress.update(task, description=step, completed=pct)

            code, output = run_git_command(repo, ["commit", "-m", commit_message])

            time.sleep(0.3)
            progress.update(
                task, description=f"[{NordColors.GREEN}]Commit complete", completed=100
            )

        print_success("Commit successful.")
        display_panel("Git Commit", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Commit command failed: {e}")
        console.print_exception()


def git_push(repo: Repo) -> None:
    """Push committed changes to the remote repository."""
    config = load_config()

    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Pushing changes...", total=100
            )

            # Use a more detailed progress sequence for push
            for step, pct in [
                (f"[{NordColors.FROST_2}]Checking remote repository...", 15),
                (f"[{NordColors.FROST_2}]Compressing objects...", 35),
                (f"[{NordColors.FROST_2}]Counting objects...", 50),
                (f"[{NordColors.FROST_2}]Sending data...", 75),
                (f"[{NordColors.FROST_2}]Finalizing...", 90),
            ]:
                time.sleep(0.3)
                progress.update(task, description=step, completed=pct)

            # Use configured push flags
            args = ["push"] + config.default_push_flags
            code, output = run_git_command(repo, args)

            time.sleep(0.3)
            progress.update(
                task, description=f"[{NordColors.GREEN}]Push complete", completed=100
            )

        print_success("Push completed successfully.")
        display_panel("Git Push", output, NordColors.FROST_2)

        # Update last used repos in config
        config = load_config()
        if repo.path in config.last_used_repos:
            config.last_used_repos.remove(repo.path)
        config.last_used_repos.insert(0, repo.path)  # Add to front
        config.last_used_repos = config.last_used_repos[:5]  # Keep only 5 most recent
        save_config(config)

    except Exception as e:
        print_error(f"Push command failed: {e}")
        console.print_exception()


def git_branch(repo: Repo) -> None:
    """List and optionally switch branches."""
    try:
        code, output = run_git_command(repo, ["branch"])
        display_panel("Git Branches", output, NordColors.FROST_2)

        branch_options = ["Switch to existing branch", "Create new branch", "Cancel"]
        choice_idx = Prompt.ask(
            "Select an option", choices=["1", "2", "3"], default="3"
        )

        choice = int(choice_idx)
        if choice == 3:  # Cancel
            return

        if choice == 1:  # Switch branch
            branch_name = Prompt.ask("Enter branch name to switch to")
            args = ["checkout", branch_name]
            action_desc = f"Switching to branch {branch_name}"
        else:  # Create branch
            branch_name = Prompt.ask("Enter new branch name")
            args = ["checkout", "-b", branch_name]
            action_desc = f"Creating and switching to branch {branch_name}"

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]{action_desc}...", total=100
            )

            for step, pct in [
                (f"[{NordColors.FROST_2}]Preparing workspace...", 30),
                (f"[{NordColors.FROST_2}]Updating HEAD reference...", 70),
            ]:
                time.sleep(0.3)
                progress.update(task, description=step, completed=pct)

            code, output = run_git_command(repo, args)

            time.sleep(0.3)
            progress.update(
                task,
                description=f"[{NordColors.GREEN}]Branch operation complete",
                completed=100,
            )

        print_success(f"{action_desc} successful.")

        # Update repo branch information
        repo.branch = branch_name

    except Exception as e:
        print_error(f"Branch operation failed: {e}")
        console.print_exception()


def git_log(repo: Repo) -> None:
    """Display the commit log."""
    try:
        # First ask for options
        print_section("Log Options")
        console.print("[1] Simple log (default)")
        console.print("[2] Detailed log with dates and authors")
        console.print("[3] Graph view with branches")

        option = Prompt.ask("Select log format", choices=["1", "2", "3"], default="1")

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{NordColors.FROST_2}]Fetching log...", total=None
            )

            if option == "1":
                args = ["log", "--oneline", "--max-count=10"]
            elif option == "2":
                args = ["log", "--pretty=format:%h - %an, %ar : %s", "--max-count=10"]
            else:
                args = [
                    "log",
                    "--oneline",
                    "--graph",
                    "--decorate",
                    "--all",
                    "--max-count=15",
                ]

            code, output = run_git_command(repo, args)
            progress.update(task, completed=100)

        display_panel("Git Log", output, NordColors.FROST_2)
    except Exception as e:
        print_error(f"Log command failed: {e}")
        console.print_exception()


def repo_menu(repo: Repo) -> None:
    """
    Display the Git command menu for a selected repository and process user input.

    Args:
        repo: The selected Git repository.
    """
    while True:
        clear_screen()
        console.print(create_header())

        # Show repository info in a detailed panel
        repo_info = Text()
        repo_info.append(f"Path: {repo.path}\n")

        if repo.branch:
            repo_info.append(f"Current Branch: ", style=f"bold {NordColors.FROST_3}")
            repo_info.append(f"{repo.branch}\n", style=f"bold {NordColors.FROST_1}")

        display_panel(f"Repository: {repo.name}", repo_info, NordColors.FROST_3)

        console.print("Select a Git operation:")
        console.print("[1] Status")
        console.print("[2] Pull")
        console.print("[3] Add")
        console.print("[4] Commit")
        console.print("[5] Push")
        console.print("[6] Branch")
        console.print("[7] Log")
        console.print("[8] Add to favorites")
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
        elif choice == "8":
            # Add to favorites
            config = load_config()
            if repo.path not in config.favorite_repos:
                config.favorite_repos.append(repo.path)
                save_config(config)
                print_success(f"Added {repo.name} to favorites.")
            else:
                print_warning(f"{repo.name} is already in favorites.")
        else:
            print_error("Invalid choice. Please try again.")

        # Wait for user before returning to menu
        Prompt.ask("Press Enter to continue")


# Signal Handling and Cleanup
def cleanup() -> None:
    """Perform cleanup operations before exiting."""
    try:
        # Cancel any pending asyncio tasks
        for task in asyncio.all_tasks(asyncio.get_event_loop_policy().get_event_loop()):
            if not task.done():
                task.cancel()

        print_message("Cleaning up resources...", NordColors.FROST_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current event loop if one exists
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule the cleanup to run properly in the loop
            loop.call_soon_threadsafe(cleanup)
            # Give a moment for cleanup to run
            time.sleep(0.2)
        else:
            cleanup()
    except Exception:
        # If we can't get the loop or it's closed already, just attempt cleanup directly
        cleanup()

    sys.exit(128 + sig)


def proper_shutdown():
    """Clean up resources at exit, specifically asyncio tasks."""
    global _background_task

    # Cancel any pending asyncio tasks
    try:
        if _background_task and not _background_task.done():
            _background_task.cancel()

        # Get the current event loop and cancel all tasks
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()

                # Run the loop briefly to process cancellations
                if tasks and loop.is_running():
                    pass  # Loop is already running, let it process cancellations
                elif tasks:
                    loop.run_until_complete(asyncio.sleep(0.1))

                # Close the loop
                loop.close()
        except Exception:
            pass  # Loop might already be closed

    except Exception as e:
        print_error(f"Error during shutdown: {e}")


def create_repo_table(repos: List[Repo], title: str) -> Table:
    """Create a formatted table of repositories."""
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=title,
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Repository Name", style=f"bold {NordColors.FROST_2}", width=30)
    table.add_column("Branch", style=f"{NordColors.FROST_3}", width=15)
    table.add_column("Path", style=NordColors.SNOW_STORM_1)

    for idx, repo in enumerate(repos, 1):
        branch_display = repo.branch or "—"
        table.add_row(str(idx), repo.name, branch_display, repo.path)
    return table


def main_menu() -> None:
    """
    Display the main menu with the list of Git repositories
    and process user selection.
    """
    config = load_config()
    repos = find_git_repositories(config.github_dir)

    # Sort alphabetically by default
    repos.sort(key=lambda r: r.name.lower())

    if not repos:
        print_warning(
            f"No Git repositories found in {config.github_dir}. Please check the directory."
        )
        if Confirm.ask("Would you like to change the GitHub directory?", default=False):
            new_dir = Prompt.ask(
                "Enter new GitHub directory path",
                default=os.path.expanduser("~/github"),
            )
            if os.path.exists(new_dir):
                config.github_dir = new_dir
                save_config(config)
                repos = find_git_repositories(config.github_dir)
            else:
                print_error(f"Directory {new_dir} does not exist.")

        if not repos:
            print_error("No repositories found. Exiting.")
            Prompt.ask("Press Enter to exit")
            sys.exit(0)

    # Start background task to get branch information
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Initialize branch information
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            console=console,
        ) as progress:
            progress.add_task(
                f"[{NordColors.FROST_2}]Loading repository information...", total=None
            )
            loop.run_until_complete(async_check_git_repos(repos))
    except Exception as e:
        print_error(f"Error loading repository information: {e}")

    # Favorites and recent repos for quick access
    favorites: List[Repo] = []
    recent_repos: List[Repo] = []

    for repo_path in config.favorite_repos:
        for repo in repos:
            if repo.path == repo_path:
                favorites.append(repo)
                break

    for repo_path in config.last_used_repos:
        for repo in repos:
            if repo.path == repo_path and repo not in recent_repos:
                recent_repos.append(repo)
                break

    while True:
        clear_screen()
        console.print(create_header())

        # Show favorites if any
        if favorites:
            console.print(create_repo_table(favorites, "Favorite Repositories"))
            console.print()

        # Show recent repos if any
        if recent_repos:
            console.print(create_repo_table(recent_repos, "Recently Used Repositories"))
            console.print()

        # Show all repos
        console.print(create_repo_table(repos, "All Git Repositories"))

        console.print("""
Select a repository by number, or use one of these commands:
[F#] Select from Favorites (e.g., F1)
[R#] Select from Recent (e.g., R2)
[S] Search repositories by name
[B] Refresh repository list
[Q] Quit
""")

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
            repos = find_git_repositories(config.github_dir)
            repos.sort(key=lambda r: r.name.lower())

            # Update favorites and recent lists with refreshed repos
            favorites = []
            recent_repos = []
            for repo_path in config.favorite_repos:
                for repo in repos:
                    if repo.path == repo_path:
                        favorites.append(repo)
                        break

            for repo_path in config.last_used_repos:
                for repo in repos:
                    if repo.path == repo_path and repo not in recent_repos:
                        recent_repos.append(repo)
                        break

            # Refresh branch information
            try:
                loop.run_until_complete(async_check_git_repos(repos))
            except Exception:
                pass
            continue
        elif choice.startswith("f") and len(choice) > 1:
            # Handle favorite selection
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(favorites):
                    repo_menu(favorites[idx])
                else:
                    print_error(f"Invalid favorite number: {choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
                Prompt.ask("Press Enter to continue")
        elif choice.startswith("r") and len(choice) > 1:
            # Handle recent selection
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(recent_repos):
                    repo_menu(recent_repos[idx])
                else:
                    print_error(f"Invalid recent number: {choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
                Prompt.ask("Press Enter to continue")
        elif choice.startswith("s"):
            # Search functionality
            search_term = Prompt.ask("Enter search term").lower()
            search_results = [
                repo for repo in repos if search_term in repo.name.lower()
            ]

            if not search_results:
                print_warning(f"No repositories found matching '{search_term}'")
                Prompt.ask("Press Enter to continue")
                continue

            console.print(
                create_repo_table(search_results, f"Search Results for '{search_term}'")
            )

            search_choice = Prompt.ask(
                "Select a repository by number or [B] to go back"
            )
            if search_choice.lower() in ("b", "back"):
                continue

            try:
                idx = int(search_choice) - 1
                if 0 <= idx < len(search_results):
                    repo_menu(search_results[idx])
                else:
                    print_error(f"Invalid repository number: {search_choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {search_choice}")
                Prompt.ask("Press Enter to continue")
        else:
            # Handle regular repo selection
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(repos):
                    # Add to recent list
                    selected_repo = repos[idx]
                    if selected_repo.path in config.last_used_repos:
                        config.last_used_repos.remove(selected_repo.path)
                    config.last_used_repos.insert(0, selected_repo.path)
                    config.last_used_repos = config.last_used_repos[:5]  # Keep only 5
                    save_config(config)

                    # Update recent repos list
                    recent_repos = []
                    for repo_path in config.last_used_repos:
                        for repo in repos:
                            if repo.path == repo_path and repo not in recent_repos:
                                recent_repos.append(repo)
                                break

                    repo_menu(selected_repo)
                else:
                    print_error(f"Invalid repository number: {choice}")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                print_error(f"Invalid choice: {choice}")
                Prompt.ask("Press Enter to continue")


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    """Main entry point for git commander."""
    try:
        # Register the proper shutdown function
        atexit.register(proper_shutdown)

        # Create configuration directory if needed
        ensure_config_directory()

        # Start the main menu
        main_menu()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
