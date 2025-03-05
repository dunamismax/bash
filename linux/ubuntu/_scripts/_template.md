# Advanced Terminal Application Script Generation Guidelines

This document provides comprehensive guidelines for generating sophisticated Python terminal applications with professional interfaces. These guidelines ensure all scripts maintain consistent structure, excellent user experience, and robust operational patterns aligned with the latest best practices.

## Core Interaction Principles

- **Professional Design Philosophy:** Create applications with an intuitive, visually appealing interface that guides users through complex operations with clarity.
- **User-Centric Experience:** Focus on responsive design, clear feedback, and graceful handling of user input and errors.
- **Operational Robustness:** Ensure applications can handle unexpected scenarios through comprehensive error handling and recovery mechanisms.
- **Visual Consistency:** Maintain consistent visual language with the Nord color theme and structured UI components.

## Technical Architecture Guidelines

When creating Python terminal applications, adhere to these structural patterns:

### 1. Modular Organization

- **Clearly Commented Sections:** Use standardized section delimiters (e.g., `# ----------------------------------------------------------------`) for improved readability.
- **Logical Function Grouping:** Organize related functions into cohesive groups (UI helpers, file operations, connection management).
- **Separation of Concerns:** Keep data structures, UI components, and business logic in distinct sections.
- **Progressive Flow:** Structure applications with clear initialization, interactive menu systems, and graceful termination.

### 2. Professional UI Implementation

- **Nord Color Theme:** Implement the complete Nord palette for consistent, visually appealing interfaces.
- **Dynamic ASCII Headers:** Use Pyfiglet with gradient styling that adapts to terminal width.
- **Rich Library Integration:** Utilize Panels, Tables, Progress bars, and styled text for sophisticated presentation.
- **Responsive Design:** Dynamically adjust display elements based on terminal dimensions using `shutil.get_terminal_size()`.
- **prompt_toolkit Integration:** Implement tab completion, command history, and styled prompts for enhanced user input.

### 3. Robust Error Handling

- **Comprehensive Try/Except Blocks:** Surround all external operations with appropriate error handling.
- **Color-Coded Messaging:** Use consistent color schemes for success, warning, and error messages.
- **User-Friendly Feedback:** Present errors with clear descriptions and potential solutions.
- **Graceful Recovery:** Provide fallback mechanisms and allow users to retry operations when possible.
- **Session Cleanup:** Ensure all resources are properly released even during abnormal termination.

### 4. Interactive Components

- **Rich Progress Tracking:** Implement visual progress indicators with real-time statistics during lengthy operations.
- **Confirmation Dialogs:** Use Rich's Confirm class for potentially destructive operations.
- **Numbered Menu Systems:** Create intuitive numbered menus with clear options and visual highlighting.
- **Enhanced Input Methods:** Integrate prompt_toolkit for path completion, command history, and styled input.
- **Contextual Help:** Provide clear instructions and help information throughout the application.

### 5. Data Structures & Management

- **Type Annotations:** Use Python type hints consistently for all function signatures and variables.
- **Dataclasses:** Employ dataclasses for structured data representation with appropriate defaults.
- **Constants Section:** Group configuration constants in a dedicated section at the beginning.
- **Global State Management:** Handle global state carefully with clear documentation.

### 6. Operational Robustness

- **Dependency Management:** Include automatic dependency detection and installation mechanisms.
- **Signal Handling:** Register appropriate signal handlers for graceful termination (SIGINT, SIGTERM).
- **Environment Awareness:** Detect and adapt to different user environments (admin/sudo contexts).

## Implementation Guidelines

When generating a terminal application for users:

1. Understand the core requirements completely before starting implementation.
2. Structure your code following the section order in the template:
   - Dependencies and imports
   - Configuration and constants
   - Data structures
   - UI helper functions
   - Core functionality
   - Main menu and control flow
   - Entry point
3. Maintain a consistent visual style throughout the application using the Nord theme.
4. Implement robust error handling for all operations that might fail.
5. Ensure comprehensive help and guidance is available within the application.
6. Create a responsive design that adapts to the user's terminal environment.
7. Include detailed docstrings for all functions, classes, and modules.

Remember to tailor the complexity to match user requirements while maintaining the professional structure and robust architecture demonstrated in the template. All scripts should be written to work on Ubuntu.

## Template / Example Script (Advanced Terminal Application standards)

```python
#!/usr/bin/env python3
"""
Automated Tailscale Reset Utility (Unattended Mode)
----------------------------------------------------

A fully autonomous terminal utility for automatically resetting Tailscale
on Ubuntu systems. The script performs the following steps sequentially:
  • Installs Nala (if not already installed) using apt and then uses Nala for all package operations.
  • Installs python3-pip, python3-rich, and python3-pyfiglet system wide via Nala.
  • Installs pipx (via Nala) and then uses pipx to install additional Python libraries
    (ensuring they are available system wide, even for root).
  • Uninstalls Tailscale (stopping/disabling tailscaled, removing packages and configuration).
  • Installs Tailscale via the official install script.
  • Enables and starts the tailscaled service.
  • Runs 'tailscale up' and checks the final status.

All operations run automatically with detailed visual feedback, logging,
and robust error & signal handling.

Version: 3.1.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import atexit
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Attempt to import required libraries; if missing, they will be installed automatically.
try:
    import pyfiglet
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.style import Style
except ImportError:
    pass

# Enable rich traceback for improved error reporting.
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Tailscale Reset Utility"
APP_SUBTITLE: str = "Automated System Management (Unattended)"
VERSION: str = "3.1.0"
HOSTNAME: str = socket.gethostname()
USERNAME: str = os.environ.get("USER", os.environ.get("USERNAME", "Unknown"))
OPERATION_TIMEOUT: int = 120  # seconds for command timeouts
TRANSITION_DELAY: float = 0.5  # delay between operations (seconds)
LOG_FILE: str = os.path.expanduser("~/tailscale_reset_logs/tailscale_reset.log")
TAILSCALE_INSTALL_URL: str = "https://tailscale.com/install.sh"
TAILSCALE_PATHS: List[str] = [
    "/var/lib/tailscale",
    "/etc/tailscale",
    "/usr/share/tailscale",
]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

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
    RED = "#BF616A"  # Critical errors
    ORANGE = "#D08770"  # Warnings
    YELLOW = "#EBCB8B"  # Cautions
    GREEN = "#A3BE8C"  # Success messages
    PURPLE = "#B48EAD"  # Special highlights


# Create a global Rich Console instance.
console: Console = Console()


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging() -> None:
    """Configure logging to file."""
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
        print_message(f"Logging setup failed: {e}", NordColors.YELLOW, "⚠")
        print_message("Continuing without file logging...", NordColors.FROST_3)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a dynamic ASCII art header with gradient styling using Pyfiglet.
    """
    fonts = ["slant", "small", "digital", "mini"]
    ascii_art: str = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = APP_NAME
    lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled: str = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 60 + "[/]"
    styled = border + "\n" + styled + border
    return Panel(
        Text.from_markup(styled),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message to the console and log it."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")
    logging.info(f"{prefix} {text}")


def print_section(title: str) -> None:
    """Print a decorated section header."""
    border = "═" * 60
    console.print("\n" + f"[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}[/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")
    logging.info(f"SECTION: {title}")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message in a styled Rich panel."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)
    logging.info(f"PANEL ({title if title else 'Untitled'}): {message}")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def display_system_info() -> None:
    """Display basic system information."""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sys_info = (
        f"[{NordColors.SNOW_STORM_1}]System: {platform.system()} {platform.release()}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/] | "
        f"[{NordColors.SNOW_STORM_1}]User: {USERNAME}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | "
        f"[{NordColors.SNOW_STORM_1}]Root: {'Yes' if check_root() else 'No'}[/]"
    )
    console.print(Align.center(sys_info))
    console.print()


# ----------------------------------------------------------------
# Logging and Signal Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exiting."""
    print_message("Cleaning up resources...", NordColors.FROST_3)
    logging.info("Cleanup complete.")


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals gracefully."""
    print_message(f"Process interrupted by signal {sig}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Progress and Spinner Classes
# ----------------------------------------------------------------
class ProgressManager:
    """
    Unified Rich progress tracking system.
    Ensures that only one live progress display is active at a time.
    """

    def __init__(self) -> None:
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[bold {task.percentage:>3.0f}]%"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self) -> "ProgressManager":
        self.progress.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"[{NordColors.FROST_3}]starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs: Any) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """
    Thread-safe spinner for indeterminate-duration operations.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = f"{elapsed:.1f}s"
            with self._lock:
                console.print(
                    f"\r[{NordColors.FROST_1}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_2}]{self.message}[/] [dim]elapsed: {time_str}[/dim]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self) -> None:
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            self.spinning = False
        if self.thread:
            self.thread.join()
        elapsed = time.time() - self.start_time
        time_str = f"{elapsed:.1f}s"
        console.print("\r" + " " * 80, end="\r")
        if success:
            console.print(
                f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] "
                f"[{NordColors.GREEN}]completed[/] in {time_str}"
            )
            logging.info(f"COMPLETED: {self.message} in {time_str}")
        else:
            console.print(
                f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] "
                f"[{NordColors.RED}]failed[/] after {time_str}"
            )
            logging.error(f"FAILED: {self.message} after {time_str}")

    def __enter__(self) -> "Spinner":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# System Helper Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """Return True if running with root privileges."""
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def ensure_root() -> bool:
    """Ensure the script is running as root."""
    if not check_root():
        print_message(
            "This utility requires root privileges. Please run with sudo.",
            NordColors.RED,
            "✗",
        )
        return False
    return True


def check_system_compatibility() -> bool:
    """
    Check if the system is Linux and that Nala is available.
    """
    if platform.system().lower() != "linux":
        print_message(
            f"Designed for Linux systems. Detected: {platform.system()}",
            NordColors.YELLOW,
            "⚠",
        )
        return False
    try:
        result = run_command(["which", "nala"], check=False)
        if result.returncode != 0:
            print_message("Nala not found.", NordColors.YELLOW, "⚠")
            return False
    except Exception:
        print_message(
            "Failed to verify package manager compatibility.", NordColors.YELLOW, "⚠"
        )
        return False
    return True


# ----------------------------------------------------------------
# Dependency Installation Functions
# ----------------------------------------------------------------
def run_command(
    cmd: Union[List[str], str],
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Execute a system command and return the CompletedProcess.
    """
    cmd_display = cmd if isinstance(cmd, str) else " ".join(cmd)
    if verbose:
        print_message(f"Executing: {cmd_display}", NordColors.FROST_3)
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_message(f"Command failed: {cmd_display}", NordColors.RED, "✗")
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


def install_nala() -> bool:
    """
    Install Nala if it is not already installed.
    Uses apt to install Nala system wide.
    """
    if shutil.which("nala"):
        print_message("Nala is already installed.", NordColors.GREEN, "✓")
        return True
    print_section("Installing Nala")
    try:
        run_command(["apt", "install", "nala", "-y"])
        if shutil.which("nala"):
            print_message("Nala installed successfully.", NordColors.GREEN, "✓")
            return True
        else:
            print_message("Nala installation failed.", NordColors.RED, "✗")
            return False
    except Exception as e:
        print_message(f"Error installing Nala: {e}", NordColors.RED, "✗")
        return False


def install_pip() -> bool:
    """
    Ensure python3-pip is installed using Nala.
    """
    if shutil.which("pip3"):
        print_message("pip3 is already installed.", NordColors.GREEN, "✓")
        return True
    print_section("Installing python3-pip")
    try:
        run_command(["nala", "install", "python3-pip", "-y"])
        if shutil.which("pip3"):
            print_message("pip3 installed successfully.", NordColors.GREEN, "✓")
            return True
        else:
            print_message("pip3 installation failed.", NordColors.RED, "✗")
            return False
    except Exception as e:
        print_message(f"Error installing pip3: {e}", NordColors.RED, "✗")
        return False


def install_python_dependencies_system() -> bool:
    """
    Install required Python dependencies system wide using Nala.
    """
    try:
        print_section("Installing Python Dependencies (System-wide via Nala)")
        cmd = ["nala", "install", "python3-rich", "python3-pyfiglet", "-y"]
        run_command(cmd)
        print_message(
            "System-wide Python dependencies installed.", NordColors.GREEN, "✓"
        )
        return True
    except Exception as e:
        print_message(
            f"Failed to install system Python dependencies: {e}", NordColors.RED, "✗"
        )
        return False


def install_pipx() -> bool:
    """
    Install pipx if not already available.
    """
    if shutil.which("pipx"):
        print_message("pipx is already installed.", NordColors.GREEN, "✓")
        return True
    print_section("Installing pipx")
    try:
        run_command(["nala", "install", "pipx", "-y"])
        if shutil.which("pipx"):
            print_message("pipx installed successfully.", NordColors.GREEN, "✓")
            return True
        else:
            print_message("pipx installation failed.", NordColors.RED, "✗")
            return False
    except Exception as e:
        print_message(f"Error installing pipx: {e}", NordColors.RED, "✗")
        return False


def install_system_dependencies() -> bool:
    """
    Install all necessary system dependencies: Nala, pip3, system Python packages,
    pipx, and then install Python libraries via pipx.
    """
    overall_success = True
    if not install_nala():
        overall_success = False
    if not install_pip():
        overall_success = False
    if not install_python_dependencies_system():
        overall_success = False
    if not install_pipx():
        overall_success = False
    return overall_success


# ----------------------------------------------------------------
# Tailscale Operation Functions (Using Nala)
# ----------------------------------------------------------------
def uninstall_tailscale() -> bool:
    """
    Stop tailscaled, disable its service, remove the Tailscale package using Nala,
    and delete configuration directories.
    """
    if not ensure_root():
        return False
    print_section("Uninstalling Tailscale")
    steps: List[Tuple[str, List[str]]] = [
        ("Stopping tailscaled service", ["systemctl", "stop", "tailscaled"]),
        ("Disabling tailscaled service", ["systemctl", "disable", "tailscaled"]),
        (
            "Removing tailscale package",
            ["nala", "remove", "--purge", "tailscale", "-y"],
        ),
        ("Autoremoving unused packages", ["nala", "autoremove", "-y"]),
    ]
    success = True
    for desc, cmd in steps:
        print_message(desc, NordColors.FROST_3)
        try:
            run_command(cmd, check=False)
        except Exception as e:
            print_message(f"Error during {desc}: {e}", NordColors.RED, "✗")
            success = False
        time.sleep(TRANSITION_DELAY)
    print_message("Removing configuration directories...", NordColors.FROST_3)
    for path in TAILSCALE_PATHS:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print_message(f"Removed {path}", NordColors.GREEN, "✓")
            except Exception as e:
                print_message(f"Failed to remove {path}: {e}", NordColors.YELLOW, "⚠")
                success = False
        else:
            print_message(f"Directory not found: {path}", NordColors.FROST_3)
        time.sleep(TRANSITION_DELAY)
    if success:
        print_message(
            "Tailscale uninstalled and cleaned up successfully.", NordColors.GREEN, "✓"
        )
    else:
        print_message(
            "Uninstallation completed with some issues.", NordColors.YELLOW, "⚠"
        )
    return success


def install_tailscale() -> bool:
    """
    Install Tailscale using the official install script.
    """
    if not ensure_root():
        return False
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
    """
    if not ensure_root():
        return False
    print_section("Starting Tailscale Service")
    steps: List[Tuple[str, List[str]]] = [
        ("Enabling tailscaled service", ["systemctl", "enable", "tailscaled"]),
        ("Starting tailscaled service", ["systemctl", "start", "tailscaled"]),
    ]
    success = True
    for desc, cmd in steps:
        print_message(desc, NordColors.FROST_3)
        try:
            run_command(cmd)
        except Exception as e:
            print_message(f"Error during {desc}: {e}", NordColors.RED, "✗")
            success = False
        time.sleep(TRANSITION_DELAY)
    if success:
        print_message(
            "Tailscale service enabled and started successfully.", NordColors.GREEN, "✓"
        )
    else:
        print_message(
            "Service configuration completed with issues.", NordColors.YELLOW, "⚠"
        )
    return success


def tailscale_up() -> bool:
    """
    Run 'tailscale up' to bring the daemon online.
    """
    if not ensure_root():
        return False
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


def check_tailscale_status() -> bool:
    """
    Check and display the current Tailscale status.
    """
    print_section("Tailscale Status")
    with Spinner("Checking Tailscale status") as spinner:
        try:
            result = run_command(["tailscale", "status"], check=False)
            if result.returncode == 0 and result.stdout.strip():
                spinner.stop(success=True)
                console.print(
                    Panel(
                        result.stdout.strip(),
                        title="Tailscale Status",
                        border_style=f"bold {NordColors.FROST_2}",
                    )
                )
                return True
            else:
                spinner.stop(success=False)
                print_message(
                    "No status information available. Tailscale may not be running.",
                    NordColors.YELLOW,
                    "⚠",
                )
                try:
                    svc_result = run_command(
                        ["systemctl", "status", "tailscaled"], check=False
                    )
                    if svc_result.stdout.strip():
                        console.print(
                            Panel(
                                svc_result.stdout.strip(),
                                title="tailscaled Service Status",
                                border_style=f"bold {NordColors.FROST_2}",
                            )
                        )
                except Exception:
                    print_message(
                        "Could not check tailscaled service status.",
                        NordColors.YELLOW,
                        "⚠",
                    )
                return False
        except Exception as e:
            spinner.stop(success=False)
            print_message(f"Failed to check status: {e}", NordColors.RED, "✗")
            return False


def reset_tailscale() -> bool:
    """
    Perform a complete reset of Tailscale by sequentially:
      1. Uninstalling Tailscale
      2. Installing Tailscale
      3. Starting the tailscaled service
      4. Running 'tailscale up'
      5. Checking final status
    """
    if not ensure_root():
        return False
    print_section("Complete Tailscale Reset")
    steps: List[Tuple[str, Any]] = [
        ("Uninstall", uninstall_tailscale),
        ("Install", install_tailscale),
        ("Service Start", start_tailscale_service),
        ("Tailscale Up", tailscale_up),
        ("Status Check", check_tailscale_status),
    ]
    overall_success = True
    results: List[Tuple[str, bool]] = []
    with ProgressManager() as progress:
        task = progress.add_task("Resetting Tailscale", total=len(steps))
        for label, func in steps:
            print_message(f"Step: {label}", NordColors.FROST_2)
            step_success = func()
            results.append((label, step_success))
            if step_success:
                progress.update(
                    task, advance=1, status=f"[{NordColors.GREEN}]{label} succeeded"
                )
            else:
                progress.update(
                    task, advance=1, status=f"[{NordColors.RED}]{label} failed"
                )
                overall_success = False
            time.sleep(TRANSITION_DELAY)
    print_section("Reset Process Summary")
    table = Table(
        title="Tailscale Reset Results",
        title_style=f"bold {NordColors.FROST_2}",
        border_style=NordColors.FROST_3,
        expand=True,
    )
    table.add_column("Operation", style=f"bold {NordColors.FROST_1}")
    table.add_column("Result", style=f"bold {NordColors.FROST_2}")
    for op, res in results:
        status = (
            f"[{NordColors.GREEN}]Success[/]" if res else f"[{NordColors.RED}]Failed[/]"
        )
        table.add_row(op, status)
    console.print(table)
    if overall_success:
        print_message(
            "Tailscale has been completely reset and is now running!",
            NordColors.GREEN,
            "✓",
        )
    else:
        print_message(
            "Tailscale reset completed with issues. Please check the logs.",
            NordColors.YELLOW,
            "⚠",
        )
    return overall_success


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function that performs all reset operations automatically.
    Installs system dependencies, checks compatibility, and then resets Tailscale.
    """
    try:
        clear_screen()
        console.print(create_header())
        display_system_info()
        setup_logging()

        print_section("System Dependency Installation")
        if not install_system_dependencies():
            print_message(
                "Dependency installation failed. Exiting.", NordColors.RED, "✗"
            )
            sys.exit(1)

        print_section("System Compatibility Check")
        if not check_system_compatibility():
            print_message(
                "System compatibility issues detected. Proceeding anyway.",
                NordColors.YELLOW,
                "⚠",
            )
        else:
            print_message("System compatibility check passed.", NordColors.GREEN, "✓")

        if not ensure_root():
            print_message(
                "This utility requires root privileges. Please run with sudo.",
                NordColors.RED,
                "✗",
            )
            sys.exit(1)

        print_message(
            "Beginning automated Tailscale reset process...", NordColors.FROST_2, "▶"
        )
        reset_success = reset_tailscale()
        if reset_success:
            display_panel(
                "Tailscale has been successfully reset and configured!",
                style=NordColors.GREEN,
                title="Operation Complete",
            )
        else:
            display_panel(
                "Tailscale reset completed with issues. Check the logs for details.",
                style=NordColors.YELLOW,
                title="Operation Partially Complete",
            )
    except KeyboardInterrupt:
        print_message("Process interrupted by user.", NordColors.YELLOW, "⚠")
        sys.exit(130)
    except Exception as e:
        print_message(f"Unexpected error: {e}", NordColors.RED, "✗")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## Final Guidelines for User Interaction

When creating terminal applications for users:

Understanding Requirements: Begin by thoroughly understanding the user's specific needs, technical level, and use case. Ask clarifying questions about functionality, platform requirements, and preferred interaction patterns before generating code.
Architecture-First Approach: Establish a clear application architecture following the template patterns, adapting complexity to match the user's requirements while maintaining robustness.
Progressive Enhancement: Start with core functionality, then layer in advanced features like tab completion, progress tracking, and styled UI elements. This allows for testing fundamental operations before enhancing the user experience.
User Experience Focus: Prioritize user interaction patterns with:

Intuitive menu navigation
Clear visual feedback for operations
Comprehensive error messages with recovery suggestions
Interactive confirmations for destructive operations
Responsive design that adapts to terminal dimensions

Documentation & Guidance: Ensure code includes thorough documentation with:

Descriptive docstrings for all components
Clear section delimiters and explanatory comments
Contextual help embedded within the application
Appropriate input validation with user guidance

By following these guidelines, you'll create terminal applications that combine professional architecture with exceptional user experience, adapted specifically to each user's requirements.
