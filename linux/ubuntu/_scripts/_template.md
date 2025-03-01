# **Guidelines for Creating Interactive Python Scripts with Rich and Pyfiglet**

## **Objective**

When writing Python scripts, please follow these guidelines to create well-structured, user-friendly programs with beautiful terminal interfaces. All scripts should be fully interactive and menu-driven by default, with no command-line argument parsing. Use the external libraries **Rich** and **pyfiglet** to provide robust functionality, user-friendly progress tracking, and clear, Nord-themed interactive feedback. All scripts should be modular, maintainable, and follow best practices in error handling, resource cleanup, and consistent code styling.

## **Core Structure Requirements**

- **Organization and Style**
  - Implement a clear, hierarchical menu system for all functionality
  - Separate configuration variables, helper functions, and the main execution flow with descriptive comments
  - Place all configuration and constants at the top of the script
  - Follow consistent formatting with clear variable names and descriptive docstrings
  - Use type hints where appropriate
  - Implement comprehensive try/except blocks for error handling
  - Include proper signal handling for clean program interruption
  - Ensure proper resource cleanup

- **Interface Requirements**
  - Make all scripts fully interactive with intuitive menu-driven navigation
  - Use **pyfiglet** to generate attractive ASCII art headers for menus and sections
  - Use **Rich** with Nord-themed hex color values (`#88C0D0`, `#81A1C1`, `#A3BE8C`, `#EBCB8B`, `#BF616A`, etc.)
  - Implement progress bars and status spinners for time-consuming operations
  - Apply consistent color coding: green for success, yellow for warnings, red for errors, blue variants for information
  - Create hierarchical menu structures for complex functionality
  - Use numbered menu options for user selection
  - Include confirmation prompts for potentially destructive operations

## **Standard Features**

- Interactive menus as the primary interface for all functionality
- Appropriate privilege verification when needed
- Clear error messages that explain both what happened and potential next steps
- Status tracking during long-running operations
- User-friendly interactive menus with numbered options
- Consistent visual styling throughout the interface

## **Color Palette Reference (Nord Theme)**

- Polar Night (dark/background): `#2E3440`, `#3B4252`, `#434C5E`, `#4C566A`
- Snow Storm (light/text): `#D8DEE9`, `#E5E9F0`, `#ECEFF4`
- Frost (blue accents): `#8FBCBB`, `#88C0D0`, `#81A1C1`, `#5E81AC`
- Aurora (status indicators): 
  - Red (errors): `#BF616A`
  - Orange (warnings): `#D08770`
  - Yellow (caution): `#EBCB8B`
  - Green (success): `#A3BE8C`
  - Purple (special): `#B48EAD`

## **Template Structure**

```python
#!/usr/bin/env python3
"""
Universal Python Utility Template
---------------------------------

A beautiful, interactive terminal-based utility template with comprehensive
error handling, real-time progress tracking, and an intuitive menu system.
All functionality is menu-driven with an attractive Nord-themed interface.

This template provides a foundation for creating any type of Python utility
with a focus on user experience and robust implementation.

Version: 1.0.0
"""

import atexit
import datetime
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TaskID
)
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Universal Utility"
VERSION = "1.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.expanduser("~/app_logs/utility.log")
DEFAULT_WORK_DIR = os.path.expanduser("~/Documents")

# Terminal dimensions
import shutil
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()

# Nord Theme Color Definitions
class NordColors:
    """Nord theme color palette for consistent UI styling."""
    # Polar Night (dark/background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"
    
    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"
    
    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"
    
    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)

# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")
    
def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")

def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")

def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")

def format_size(num_bytes: float) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"

def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"

def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()

def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")

def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)

def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Get a choice from the user with a styled prompt."""
    return Prompt.ask(
        f"[bold {NordColors.NORD15}]{prompt}[/]", 
        choices=choices,
        show_choices=True
    )

def get_user_confirmation(prompt: str) -> bool:
    """Get confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")

def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")
    
    for key, description in options:
        table.add_row(key, description)
    
    return table

# ==============================
# Logging Setup
# ==============================
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")

# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add cleanup tasks here

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)

# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ==============================
# Progress Tracking Classes
# ==============================
class ProgressManager:
    """Unified progress tracking system with multiple display options."""
    
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True
        )
    
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()
    
    def add_task(self, description: str, total: float, color: str = NordColors.NORD8) -> TaskID:
        """Add a new task to the progress manager."""
        return self.progress.add_task(
            description, 
            total=total,
            color=color,
            status=f"{NordColors.NORD9}starting"
        )
        
    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        """Update a task's progress."""
        self.progress.update(task_id, advance=advance, **kwargs)
        
    def start(self):
        """Start displaying the progress bar."""
        self.progress.start()
        
    def stop(self):
        """Stop displaying the progress bar."""
        self.progress.stop()

class Spinner:
    """Thread-safe spinner for indeterminate progress."""

    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        """Internal method to update the spinner."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)  # Spinner update interval

    def start(self) -> None:
        """Start the spinner."""
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner and display completion message."""
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)

            # Clear the line
            console.print("\r" + " " * TERM_WIDTH, end="\r")

            if success:
                console.print(
                    f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD14}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] "
                    f"[{NordColors.NORD11}]failed[/] after {time_str}"
                )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit."""
        self.stop(success=exc_type is None)

# ==============================
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = False,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
    if verbose:
        print_step(f"Executing: {' '.join(cmd)}")
    try:
        return subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if hasattr(e, "stderr") and e.stderr:
            print_error(f"Error details: {e.stderr.strip()}")
        raise

def check_privileges() -> bool:
    """Check if script is running with elevated privileges."""
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:  # Unix/Linux/Mac
            return os.geteuid() == 0
    except:
        return False

def ensure_directory(path: str) -> bool:
    """Create directory if it doesn't exist."""
    try:
        os.makedirs(path, exist_ok=True)
        print_step(f"Directory ensured: {path}")
        return True
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        return False

def check_dependency(cmd: str) -> bool:
    """Check if a command is available in the system."""
    return shutil.which(cmd) is not None

# ==============================
# Example Task Functions
# ==============================
def task_with_progress_bar() -> None:
    """Example task that uses a progress bar."""
    print_section("Progress Bar Demo")
    
    total_steps = 100
    print_info(f"Simulating task with {total_steps} steps")
    
    with ProgressManager() as progress:
        task_id = progress.add_task("Processing", total=total_steps)
        progress.start()
        
        for i in range(total_steps):
            # Simulate work
            time.sleep(0.05)
            # Update progress
            status_text = f"[{NordColors.NORD9}]Step {i+1}/{total_steps}"
            progress.update(task_id, advance=1, status=status_text)
    
    print_success("Task completed successfully!")

def task_with_spinner() -> None:
    """Example task that uses a spinner for indeterminate progress."""
    print_section("Spinner Demo")
    
    print_info("Starting process with unknown duration")
    
    with Spinner("Processing data") as spinner:
        # Simulate work that takes a variable amount of time
        time.sleep(3)
    
    print_success("Process completed successfully!")

def task_with_multiple_progress_bars() -> None:
    """Example task with multiple concurrent progress bars."""
    print_section("Multiple Progress Bars Demo")
    
    print_info("Starting multiple concurrent tasks")
    
    with ProgressManager() as progress:
        # Add multiple tasks
        task1 = progress.add_task("Downloading", total=100, color=NordColors.NORD8)
        task2 = progress.add_task("Processing", total=50, color=NordColors.NORD9)
        task3 = progress.add_task("Uploading", total=75, color=NordColors.NORD10)
        
        progress.start()
        
        # Task 1 progress
        for i in range(100):
            time.sleep(0.02)
            progress.update(task1, advance=1, status=f"[{NordColors.NORD9}]{i+1}%")
            
            # Update other tasks at different rates
            if i % 2 == 0 and i < 100:
                progress.update(task2, advance=1, status=f"[{NordColors.NORD9}]Step {(i//2)+1}")
            
            if i % 4 == 0 and i < 300:
                progress.update(task3, advance=1, status=f"[{NordColors.NORD9}]File {(i//4)+1}")
    
    print_success("All tasks completed successfully!")

def task_file_operations() -> None:
    """Example task demonstrating file operations with progress tracking."""
    print_section("File Operations Demo")
    
    # Get source and destination directories
    source_dir = get_user_input("Enter source directory:", os.path.expanduser("~"))
    dest_dir = get_user_input("Enter destination directory:", DEFAULT_WORK_DIR)
    
    # Ensure destination directory exists
    if not ensure_directory(dest_dir):
        print_error("Failed to create destination directory")
        return
    
    # List files in source directory
    try:
        files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]
        
        if not files:
            print_warning(f"No files found in {source_dir}")
            return
        
        print_info(f"Found {len(files)} files in {source_dir}")
        
        # Ask for confirmation
        if not get_user_confirmation(f"Copy {len(files)} files to {dest_dir}?"):
            print_info("Operation cancelled")
            return
        
        # Copy files with progress bar
        with ProgressManager() as progress:
            task_id = progress.add_task(f"Copying files", total=len(files))
            progress.start()
            
            for i, file in enumerate(files):
                src_path = os.path.join(source_dir, file)
                dst_path = os.path.join(dest_dir, file)
                
                try:
                    # Show current file
                    progress.update(
                        task_id, 
                        advance=0,  # Don't advance yet
                        status=f"[{NordColors.NORD9}]{file}"
                    )
                    
                    # Simulate file copy (replace with actual file operations)
                    time.sleep(0.2)  # Simulate copy taking time
                    
                    # Update progress
                    progress.update(task_id, advance=1)
                    
                except Exception as e:
                    print_error(f"Error copying {file}: {e}")
            
        print_success(f"Successfully processed {len(files)} files")
        
    except Exception as e:
        print_error(f"Error accessing directory: {e}")

def task_system_info() -> None:
    """Display detailed system information."""
    print_section("System Information")
    
    # Create a table for system info
    table = Table(title="System Information", box=None)
    table.add_column("Property", style=f"{NordColors.NORD9}")
    table.add_column("Value", style=f"{NordColors.NORD4}")
    
    # System details
    table.add_row("Hostname", HOSTNAME)
    table.add_row("Platform", platform.system())
    table.add_row("Platform Version", platform.version())
    table.add_row("Architecture", platform.machine())
    table.add_row("Processor", platform.processor())
    
    # Python details
    table.add_row("Python Version", platform.python_version())
    table.add_row("Python Implementation", platform.python_implementation())
    
    # User details
    table.add_row("Username", os.environ.get('USER', os.environ.get('USERNAME', 'Unknown')))
    table.add_row("Home Directory", os.path.expanduser("~"))
    table.add_row("Current Directory", os.getcwd())
    
    # Time details
    table.add_row("Current Time", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    table.add_row("Timezone", time.tzname[0])
    
    console.print(table)
    
    # Memory information
    try:
        import psutil
        memory = psutil.virtual_memory()
        
        print_section("Memory Information")
        mem_table = Table(box=None)
        mem_table.add_column("Metric", style=f"{NordColors.NORD9}")
        mem_table.add_column("Value", style=f"{NordColors.NORD4}")
        
        mem_table.add_row("Total Memory", format_size(memory.total))
        mem_table.add_row("Available Memory", format_size(memory.available))
        mem_table.add_row("Used Memory", format_size(memory.used))
        mem_table.add_row("Memory Percentage", f"{memory.percent}%")
        
        console.print(mem_table)
    except ImportError:
        print_info("Install psutil package for memory information")

# ==============================
# Menu System
# ==============================
def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'Unknown'))}")
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Main menu options
        menu_options = [
            ("1", "Progress Bar Demo"),
            ("2", "Spinner Demo"),
            ("3", "Multiple Progress Bars Demo"),
            ("4", "File Operations Demo"),
            ("5", "System Information"),
            ("0", "Exit")
        ]
        
        console.print(create_menu_table("Main Menu", menu_options))
        
        # Get user selection
        choice = get_user_input("Enter your choice (0-5):")
        
        if choice == "1":
            task_with_progress_bar()
            pause()
        elif choice == "2":
            task_with_spinner()
            pause()
        elif choice == "3":
            task_with_multiple_progress_bars()
            pause()
        elif choice == "4":
            task_file_operations()
            pause()
        elif choice == "5":
            task_system_info()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Universal Utility.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)

# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Initial setup
        setup_logging()
        
        # Launch the main menu
        main_menu()
        
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## **Implementation Checklist**

When writing any Python script, make sure to:

1. Create a fully interactive, menu-driven interface with no command-line arguments
2. Organize your code with configuration at the top, helper functions in the middle, and main functions at the end
3. Structure the script around a hierarchical menu system that guides users through all functionality
4. Use Rich for all console output with Nord theme colors
5. Implement proper error handling and resource cleanup
6. Ensure all user interaction flows through intuitive, numbered menu options
7. Use pyfiglet for ASCII art headers in menus and key sections
8. Add progress indicators (bars and spinners) for all time-consuming operations
9. Include confirmation prompts for potentially destructive actions
10. Apply consistent color coding throughout the interface
11. Make scripts modular and maintainable with clear documentation
12. Implement status tracking for long-running operations with real-time feedback
13. Use appropriate visual elements (tables, panels, etc.) to organize information
14. Add graceful handling of interruptions and cleanup on exit

The template script I've created demonstrates all these principles in action. It provides a foundation for any interactive Python utility with a beautiful, Nord-themed terminal interface, complete with progress tracking, spinners, and a comprehensive menu system. The script is organized for maximum readability and maintainability, with proper error handling throughout.
