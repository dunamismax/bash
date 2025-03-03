#!/usr/bin/env python3
"""
Enhanced Tailscale Reset Utility
--------------------------------------------------

A beautiful, interactive terminal-based utility for managing Tailscale on Ubuntu systems.
Features comprehensive management options for Tailscale including:
  • Complete reset workflow (uninstall, reinstall, restart)
  • Service management (stop, disable, enable, start)
  • Package handling (uninstall, clean configuration, install)
  • Status monitoring and reporting
  • Interactive menu with Nord theme styling

Note: Most operations require root privileges and will prompt accordingly.

Usage:
  Run the script and select options from the interactive menu.
  - Option 1: Complete Tailscale Reset
  - Option 2: Uninstall Tailscale
  - Option 3: Install Tailscale
  - Option 4: Start Tailscale Service
  - Option 5: Run 'tailscale up'
  - Option 6: Check Tailscale Status
  - Option 0: Exit

Version: 2.0.0
"""

import atexit
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.prompt import Prompt, Confirm
    from rich.live import Live
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
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
APP_NAME: str = "Tailscale Reset Utility"
APP_SUBTITLE: str = "System Management Tool"
VERSION: str = "2.0.0"
HOSTNAME: str = socket.gethostname()
USERNAME: str = os.environ.get("USER", os.environ.get("USERNAME", "Unknown"))
OPERATION_TIMEOUT: int = 120  # seconds
TRANSITION_DELAY: float = 0.5  # seconds between operations
LOG_FILE: str = os.path.expanduser("~/tailscale_reset_logs/tailscale_reset.log")
TAILSCALE_INSTALL_URL: str = "https://tailscale.com/install.sh"

# Terminal dimensions
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT: int = min(shutil.get_terminal_size().lines, 30)

# Tailscale paths for cleanup
TAILSCALE_PATHS: List[str] = [
    "/var/lib/tailscale",
    "/etc/tailscale",
    "/usr/share/tailscale",
]


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
    RED = "#BF616A"  # Red - Errors and critical issues
    ORANGE = "#D08770"  # Orange - Warnings
    YELLOW = "#EBCB8B"  # Yellow - Cautions and notices
    GREEN = "#A3BE8C"  # Green - Success and positive indicators
    PURPLE = "#B48EAD"  # Purple - Special operations and highlights


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure basic logging for the utility."""
    import logging

    try:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        print_message(f"Logging configured to: {LOG_FILE}", NordColors.FROST_3)
    except Exception as e:
        print_message(
            f"Could not set up logging to {LOG_FILE}: {e}", NordColors.YELLOW, "⚠"
        )
        print_message("Continuing without logging to file...", NordColors.FROST_3)


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
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
 _____     _ _               _      _____                _   
|_   _|_ _(_) |___  ___ __ _| |___ | ____|___ ___ ___ _| |_ 
  | |/ _` | | / __|/ __/ _` | / -_)|  _| (_-</ -_) -_) |  _|
  |_|\\__,_|_|_\\__ \\__\\__,_|_\\___||_| |_/__/\\___\\___\\_|\\__|
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


def print_section(title: str) -> None:
    """
    Print a section header with a decorative border.

    Args:
        title: The section title to display
    """
    border = "═" * min(TERM_WIDTH, 80)
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]")
    console.print()


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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until the user presses Enter."""
    console.print()
    console.input(f"[{NordColors.PURPLE}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """
    Get input from the user with a styled prompt.

    Args:
        prompt: The prompt text to display
        default: Default value if user enters nothing

    Returns:
        User input string
    """
    return Prompt.ask(f"[bold {NordColors.FROST_2}]{prompt}[/]", default=default)


def get_user_choice(prompt: str, choices: List[str]) -> str:
    """
    Prompt the user to choose from a list of options.

    Args:
        prompt: The prompt text to display
        choices: List of valid choices

    Returns:
        User's selected choice
    """
    return Prompt.ask(
        f"[bold {NordColors.FROST_2}]{prompt}[/]", choices=choices, show_choices=True
    )


def get_user_confirmation(prompt: str) -> bool:
    """
    Get a yes/no confirmation from the user.

    Args:
        prompt: The prompt text to display

    Returns:
        True if user confirms, False otherwise
    """
    return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """
    Create a table to display menu options.

    Args:
        title: The menu title
        options: List of (key, description) tuples for menu options

    Returns:
        A Rich Table object with formatted menu options
    """
    table = Table(
        title=title,
        title_style=f"bold {NordColors.FROST_2}",
        border_style=NordColors.FROST_3,
        box=None,
        expand=True,
        title_justify="center",
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", justify="right", width=3)
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for key, desc in options:
        table.add_row(key, desc)

    return table


def format_time(seconds: float) -> str:
    """
    Format seconds into a human-readable time string.

    Args:
        seconds: Time duration in seconds

    Returns:
        Formatted time string (e.g., "1.5s", "2.3m", "1.2h")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        shell: Whether to run command in a shell
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        verbose: Whether to print the command before execution

    Returns:
        CompletedProcess instance with command results
    """
    if verbose:
        print_message(
            f"Executing: {cmd if isinstance(cmd, str) else ' '.join(cmd)}",
            NordColors.FROST_3,
        )

    try:
        return subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        print_message(
            f"Command failed: {cmd if isinstance(cmd, str) else ' '.join(cmd)}",
            NordColors.RED,
            "✗",
        )
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
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


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """
    Unified progress tracking system using Rich Progress.
    Provides a consistent way to show operation progress.
    """

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        """
        Add a task to the progress tracker.

        Args:
            description: Task description
            total: Total units of work
            color: Color for task description

        Returns:
            Task ID for referencing this task
        """
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"[{NordColors.FROST_3}]starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        """
        Update task progress.

        Args:
            task_id: Task identifier
            advance: Units of work to add to progress
            **kwargs: Additional task fields to update
        """
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """
    Thread-safe spinner for indeterminate progress.
    Shows an animated spinner during operations with unknown duration.
    """

    def __init__(self, message: str):
        """
        Initialize a new spinner.

        Args:
            message: Text to display next to the spinner
        """
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Animation loop for the spinner."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.FROST_1}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_2}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation."""
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        """
        Stop the spinner animation.

        Args:
            success: Whether the operation completed successfully
        """
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()

            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            # Clear the spinner line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            if success:
                console.print(
                    f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.GREEN}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.RED}]failed[/] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# System Helper Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        True if running as root, False otherwise
    """
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def ensure_root() -> None:
    """Exit if not running with root privileges."""
    if not check_root():
        print_message("This operation requires root privileges.", NordColors.RED, "✗")
        print_message("Please run the script with sudo.", NordColors.FROST_3)
        sys.exit(1)


def check_system_compatibility() -> bool:
    """
    Check if the system is compatible with this utility.

    Returns:
        True if system is compatible, False otherwise
    """
    system = platform.system().lower()

    if system != "linux":
        print_message(
            f"This utility is designed for Linux systems, detected: {system}",
            NordColors.YELLOW,
            "⚠",
        )
        return False

    # Check if we're on a Debian-based system (for apt commands)
    try:
        result = run_command(["which", "apt-get"], check=False)
        if result.returncode != 0:
            print_message(
                "This utility requires apt-get, which was not found.",
                NordColors.YELLOW,
                "⚠",
            )
            return False
    except Exception:
        print_message(
            "Could not verify package manager compatibility.", NordColors.YELLOW, "⚠"
        )
        return False

    return True


# ----------------------------------------------------------------
# Tailscale Operation Functions
# ----------------------------------------------------------------
def uninstall_tailscale() -> bool:
    """
    Stop and disable tailscaled, uninstall tailscale, and remove config/data directories.

    Returns:
        True if successful, False if errors occurred
    """
    ensure_root()
    print_section("Uninstalling Tailscale")

    steps = [
        ("Stopping tailscaled service", ["systemctl", "stop", "tailscaled"]),
        ("Disabling tailscaled service", ["systemctl", "disable", "tailscaled"]),
        (
            "Removing tailscale package",
            ["apt-get", "remove", "--purge", "tailscale", "-y"],
        ),
        ("Autoremoving unused packages", ["apt-get", "autoremove", "-y"]),
    ]

    success = True

    with ProgressManager() as progress:
        task = progress.add_task(
            "Uninstalling Tailscale", total=len(steps) + len(TAILSCALE_PATHS)
        )

        for desc, cmd in steps:
            print_message(desc, NordColors.FROST_3)
            try:
                run_command(cmd, check=False)
                progress.update(
                    task, advance=1, status=f"[{NordColors.GREEN}]Completed"
                )
            except Exception as e:
                print_message(f"Error during {desc}: {e}", NordColors.RED, "✗")
                if not get_user_confirmation("Continue with remaining steps?"):
                    print_message("Uninstallation aborted.", NordColors.YELLOW, "⚠")
                    return False
                progress.update(task, advance=1, status=f"[{NordColors.RED}]Failed")
                success = False

        print_message("Removing configuration directories...", NordColors.FROST_3)
        for path in TAILSCALE_PATHS:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    print_message(f"Removed {path}", NordColors.GREEN, "✓")
                    progress.update(
                        task, advance=1, status=f"[{NordColors.GREEN}]Removed"
                    )
                except Exception as e:
                    print_message(
                        f"Failed to remove {path}: {e}", NordColors.YELLOW, "⚠"
                    )
                    progress.update(
                        task, advance=1, status=f"[{NordColors.YELLOW}]Failed"
                    )
                    success = False
            else:
                print_message(f"Directory not found: {path}", NordColors.FROST_3)
                progress.update(
                    task, advance=1, status=f"[{NordColors.FROST_3}]Skipped"
                )

    if success:
        print_message(
            "Tailscale uninstalled and cleaned up successfully.", NordColors.GREEN, "✓"
        )
    else:
        print_message(
            "Tailscale uninstallation completed with some issues.",
            NordColors.YELLOW,
            "⚠",
        )

    return success


def install_tailscale() -> bool:
    """
    Install tailscale using the official install script.

    Returns:
        True if successful, False if errors occurred
    """
    ensure_root()
    print_section("Installing Tailscale")

    print_message("Running Tailscale install script", NordColors.FROST_3)
    install_cmd = f"curl -fsSL {TAILSCALE_INSTALL_URL} | sh"

    with Spinner("Installing Tailscale") as spinner:
        try:
            result = run_command(install_cmd, shell=True)
            if result.returncode == 0:
                spinner.stop(success=True)
                print_message(
                    "Tailscale installed successfully.", NordColors.GREEN, "✓"
                )
                return True
            else:
                spinner.stop(success=False)
                print_message(
                    "Tailscale installation may have issues.", NordColors.YELLOW, "⚠"
                )
                return False
        except Exception as e:
            spinner.stop(success=False)
            print_message(f"Installation failed: {e}", NordColors.RED, "✗")
            return False


def start_tailscale_service() -> bool:
    """
    Enable and start the tailscaled service.

    Returns:
        True if successful, False if errors occurred
    """
    ensure_root()
    print_section("Enabling and Starting Tailscale Service")

    steps = [
        ("Enabling tailscaled service", ["systemctl", "enable", "tailscaled"]),
        ("Starting tailscaled service", ["systemctl", "start", "tailscaled"]),
    ]

    success = True

    with ProgressManager() as progress:
        task = progress.add_task("Configuring Tailscale Service", total=len(steps))

        for desc, cmd in steps:
            print_message(desc, NordColors.FROST_3)
            try:
                run_command(cmd)
                progress.update(
                    task, advance=1, status=f"[{NordColors.GREEN}]Completed"
                )
            except Exception as e:
                print_message(f"Error during {desc}: {e}", NordColors.RED, "✗")
                progress.update(task, advance=1, status=f"[{NordColors.RED}]Failed")
                success = False
                if not get_user_confirmation("Continue with remaining steps?"):
                    print_message(
                        "Service configuration aborted.", NordColors.YELLOW, "⚠"
                    )
                    return False

    if success:
        print_message(
            "Tailscale service enabled and started successfully.", NordColors.GREEN, "✓"
        )
    else:
        print_message(
            "Tailscale service configuration completed with issues.",
            NordColors.YELLOW,
            "⚠",
        )

    return success


def tailscale_up() -> bool:
    """
    Run 'tailscale up' to bring up the daemon.

    Returns:
        True if successful, False if errors occurred
    """
    ensure_root()
    print_section("Running 'tailscale up'")

    with Spinner("Executing tailscale up") as spinner:
        try:
            result = run_command(["tailscale", "up"])
            spinner.stop(success=True)
            print_message("Tailscale is up!", NordColors.GREEN, "✓")

            if result.stdout.strip():
                display_panel(
                    result.stdout.strip(),
                    style=NordColors.FROST_3,
                    title="Tailscale Up Output",
                )
            return True
        except Exception as e:
            spinner.stop(success=False)
            print_message(f"Failed to bring Tailscale up: {e}", NordColors.RED, "✗")
            return False


def check_tailscale_status() -> None:
    """Check and display the current Tailscale status."""
    print_section("Tailscale Status")

    with Spinner("Checking Tailscale status") as spinner:
        try:
            result = run_command(["tailscale", "status"], check=False)
            spinner.stop(success=result.returncode == 0)

            if result.returncode == 0 and result.stdout.strip():
                console.print(
                    Panel(
                        result.stdout.strip(),
                        title="Tailscale Status",
                        border_style=f"bold {NordColors.FROST_2}",
                    )
                )
            else:
                print_message(
                    "No status information available. Tailscale may not be running.",
                    NordColors.YELLOW,
                    "⚠",
                )

                # Try to check service status as well
                try:
                    service_result = run_command(
                        ["systemctl", "status", "tailscaled"], check=False
                    )
                    if service_result.stdout.strip():
                        console.print(
                            Panel(
                                service_result.stdout.strip(),
                                title="Tailscaled Service Status",
                                border_style=f"bold {NordColors.FROST_2}",
                            )
                        )
                except Exception:
                    print_message(
                        "Could not check tailscaled service status.",
                        NordColors.YELLOW,
                        "⚠",
                    )
        except Exception as e:
            spinner.stop(success=False)
            print_message(f"Failed to check Tailscale status: {e}", NordColors.RED, "✗")
            print_message(
                "Tailscale may not be installed or running.", NordColors.FROST_3
            )


def reset_tailscale() -> bool:
    """
    Perform a complete reset of Tailscale: uninstall, install, start, and run 'tailscale up'.

    Returns:
        True if successful, False if errors occurred
    """
    ensure_root()
    print_section("Complete Tailscale Reset")

    if not get_user_confirmation("This will completely reset Tailscale. Continue?"):
        print_message("Reset cancelled.", NordColors.FROST_3)
        return False

    steps = [
        "Uninstalling Tailscale",
        "Installing Tailscale",
        "Starting Tailscale Service",
        "Running 'tailscale up'",
    ]

    success = True

    with ProgressManager() as progress:
        task = progress.add_task("Complete Tailscale Reset", total=len(steps))

        # Step 1: Uninstall
        print_message("Step 1: Uninstalling Tailscale", NordColors.FROST_2)
        if uninstall_tailscale():
            progress.update(task, advance=1, status=f"[{NordColors.GREEN}]Uninstalled")
        else:
            progress.update(
                task, advance=1, status=f"[{NordColors.YELLOW}]Partial uninstall"
            )
            success = False
            if not get_user_confirmation("Continue with installation?"):
                print_message("Reset process aborted.", NordColors.YELLOW, "⚠")
                return False

        time.sleep(TRANSITION_DELAY)

        # Step 2: Install
        print_message("Step 2: Installing Tailscale", NordColors.FROST_2)
        if install_tailscale():
            progress.update(task, advance=1, status=f"[{NordColors.GREEN}]Installed")
        else:
            progress.update(task, advance=1, status=f"[{NordColors.RED}]Install failed")
            print_message(
                "Reset process failed at installation step.", NordColors.RED, "✗"
            )
            return False

        time.sleep(TRANSITION_DELAY)

        # Step 3: Start service
        print_message("Step 3: Starting Tailscale Service", NordColors.FROST_2)
        if start_tailscale_service():
            progress.update(
                task, advance=1, status=f"[{NordColors.GREEN}]Service started"
            )
        else:
            progress.update(
                task, advance=1, status=f"[{NordColors.YELLOW}]Service issues"
            )
            success = False
            if not get_user_confirmation("Continue with 'tailscale up'?"):
                print_message("Reset process aborted.", NordColors.YELLOW, "⚠")
                return False

        time.sleep(TRANSITION_DELAY)

        # Step 4: Run 'tailscale up'
        print_message("Step 4: Running 'tailscale up'", NordColors.FROST_2)
        if tailscale_up():
            progress.update(
                task, advance=1, status=f"[{NordColors.GREEN}]Up and running"
            )
        else:
            progress.update(task, advance=1, status=f"[{NordColors.RED}]Up failed")
            success = False

    if success:
        print_message(
            "Tailscale has been completely reset and is now running!",
            NordColors.GREEN,
            "✓",
        )
    else:
        print_message(
            "Tailscale reset completed with some issues.", NordColors.YELLOW, "⚠"
        )
        print_message(
            "Check the status to verify everything is working correctly.",
            NordColors.FROST_3,
        )

    return success


# ----------------------------------------------------------------
# Menu System
# ----------------------------------------------------------------
def display_system_info() -> None:
    """Display system information in the main menu."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_info = (
        f"[{NordColors.SNOW_STORM_1}]System: {platform.system()} {platform.release()}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/] | "
        f"[{NordColors.SNOW_STORM_1}]User: {USERNAME}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Root: {'Yes' if check_root() else 'No'}[/]"
    )
    console.print(Align.center(system_info))
    console.print()


def main_menu() -> None:
    """Display the main menu and handle user selections."""
    while True:
        clear_screen()
        console.print(create_header())
        display_system_info()

        menu_options = [
            ("1", "Complete Tailscale Reset (uninstall, reinstall, restart)"),
            ("2", "Uninstall Tailscale"),
            ("3", "Install Tailscale"),
            ("4", "Start Tailscale Service"),
            ("5", "Run 'tailscale up'"),
            ("6", "Check Tailscale Status"),
            ("0", "Exit"),
        ]

        menu_table = create_menu_table("Main Menu", menu_options)
        console.print(
            Panel(
                menu_table,
                border_style=Style(color=NordColors.FROST_3),
                padding=(1, 2),
                title=f"[bold {NordColors.FROST_1}]Tailscale Management Options[/]",
                title_align="center",
            )
        )

        console.print()
        choice = get_user_input("Enter your choice (0-6):")

        # Handle commands
        if choice == "1":
            reset_tailscale()
            pause()
        elif choice == "2":
            uninstall_tailscale()
            pause()
        elif choice == "3":
            install_tailscale()
            pause()
        elif choice == "4":
            start_tailscale_service()
            pause()
        elif choice == "5":
            tailscale_up()
            pause()
        elif choice == "6":
            check_tailscale_status()
            pause()
        elif choice == "0":
            clear_screen()
            console.print(create_header())
            display_panel(
                message="Thank you for using the Tailscale Reset Utility!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            time.sleep(1)
            sys.exit(0)
        else:
            print_message(
                f"Invalid selection: {choice}. Please try again.", NordColors.RED, "✗"
            )
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the Tailscale Reset Utility."""
    try:
        # Setup logging
        setup_logging()

        # Check system compatibility
        if not check_system_compatibility():
            if not get_user_confirmation("Continue anyway?"):
                print_message(
                    "Exiting due to system compatibility concerns.",
                    NordColors.YELLOW,
                    "⚠",
                )
                sys.exit(1)
            print_message(
                "Continuing despite compatibility concerns.", NordColors.YELLOW, "⚠"
            )

        # Display main menu
        main_menu()
    except KeyboardInterrupt:
        print_message("\nProcess interrupted by user.", NordColors.YELLOW, "⚠")
        sys.exit(130)
    except Exception as e:
        print_message(f"Unexpected error: {e}", NordColors.RED, "✗")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
