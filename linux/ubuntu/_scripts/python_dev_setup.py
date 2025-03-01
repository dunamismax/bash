#!/usr/bin/env python3
"""
Enhanced Python Development Environment Setup Tool
-------------------------------------------------

A beautiful, interactive terminal-based utility for setting up a Python development
environment on Ubuntu/Linux systems. This tool provides options to:
  • Install system-level prerequisites first (including Rich and Pyfiglet)
  • Perform system checks and install system-level dependencies
  • Install pipx (if missing) and use it to install recommended Python tools
  • Create a Python virtual environment
  • Install common development tools via pip
  • Generate a basic Python project template

All functionality is menu-driven with an attractive Nord-themed interface.

Note: Some operations require root privileges. Run with sudo if necessary.

Version: 2.0.0
"""

import atexit
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple

# ==============================
# Initial Package Installation
# ==============================
# First, we need to ensure the required packages are installed system-wide
# so they're available to the script itself


def ensure_script_dependencies() -> bool:
    """Install script dependencies system-wide so they're available to the script."""
    print("Setting up script dependencies...")

    # Check if we're running as root
    is_root = os.geteuid() == 0
    apt_cmd_prefix = [] if is_root else ["sudo"]

    # Required packages for the script itself
    script_dependencies = ["python3-pyfiglet", "python3-rich"]

    try:
        # Update package lists
        subprocess.run(apt_cmd_prefix + ["apt-get", "update"], check=True)

        # Install each dependency
        for package in script_dependencies:
            try:
                subprocess.run(
                    apt_cmd_prefix + ["apt-get", "install", "-y", package], check=True
                )
                print(f"✓ Installed {package}")
            except subprocess.CalledProcessError:
                print(f"✗ Failed to install {package}")
                return False

        print("✓ Script dependencies installed successfully")
        return True
    except Exception as e:
        print(f"✗ Error installing script dependencies: {e}")
        return False


# Try to install dependencies first
if not ensure_script_dependencies():
    print("Warning: Some script dependencies might be missing.")
    print("The script will attempt to continue, but might encounter errors.")

# Now we can import rich and pyfiglet
try:
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
        TaskID,
    )
    import pyfiglet
except ImportError as e:
    print(f"Failed to import required packages: {e}")
    print("Please install the missing packages and try again.")
    print(
        "You can install them manually with: sudo apt-get install python3-rich python3-pyfiglet"
    )
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Python Dev Setup"
VERSION = "2.0.0"
DEFAULT_PROJECT_DIR = os.getcwd()

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# System packages
SYSTEM_DEPENDENCIES = [
    "build-essential",
    "libssl-dev",
    "zlib1g-dev",
    "libbz2-dev",
    "libreadline-dev",
    "libsqlite3-dev",
    "libncurses5-dev",
    "libncursesw5-dev",
    "xz-utils",
    "tk-dev",
    "libffi-dev",
    "liblzma-dev",
    "python3-dev",
    "git",
    "curl",
    "wget",
]

# Top Python tools to install
TOP_PYTHON_TOOLS = [
    "rich",
    "pyfiglet",
    "black",
    "isort",
    "flake8",
    "mypy",
    "pytest",
    "pre-commit",
    "ipython",
    "cookiecutter",
    "virtualenv",
    "pylint",
    "sphinx",
    "twine",
    "autopep8",
    "bandit",
    "poetry",
    "pydocstyle",
    "yapf",
    "httpie",
]

# Tools to install via pipx
PIPX_TOOLS = TOP_PYTHON_TOOLS

# Basic development tools to install in venv
DEV_TOOLS = [
    "pip",
    "setuptools",
    "wheel",
    "black",
    "isort",
    "mypy",
    "flake8",
    "pytest",
]

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
        f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True
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
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add specific cleanup tasks here if needed


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
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
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.NORD8
    ) -> TaskID:
        """Add a new task to the progress manager."""
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
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


# ==============================
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 60,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command and handle errors."""
    if verbose:
        if shell:
            print_step(f"Executing: {cmd}")
        else:
            print_step(f"Executing: {' '.join(cmd)}")

    try:
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        if shell:
            print_error(f"Command failed: {cmd}")
        else:
            print_error(f"Command failed: {' '.join(cmd)}")

        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.NORD11}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


def check_root() -> bool:
    """Check if script is running with elevated privileges."""
    return os.geteuid() == 0


def ensure_root() -> None:
    """Ensure the script has root privileges or prompt for sudo."""
    if not check_root():
        print_warning("Some operations require root privileges.")
        if get_user_confirmation(
            "Try to continue using sudo for privileged operations?"
        ):
            return
        else:
            print_error("Please restart the script with sudo.")
            sys.exit(1)


# ==============================
# Core Functions
# ==============================
def check_system() -> bool:
    """Check system compatibility and required tools."""
    print_section("Checking System Compatibility")

    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")

    print_step(f"Current Python version: {platform.python_version()}")
    print_step(f"Current Operating System: {platform.platform()}")

    required_tools = ["git", "curl", "gcc"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]

    if missing:
        print_error(
            f"Missing required tools: {', '.join(missing)}. These will be installed."
        )
    else:
        print_success("All basic required tools are present.")

    print_success("System check completed.")
    return True


def install_system_dependencies() -> bool:
    """Install system-level dependencies using apt-get."""
    print_section("Installing System Dependencies")

    # Using sudo if not root
    apt_cmd_prefix = [] if check_root() else ["sudo"]

    with ProgressManager() as progress:
        try:
            # Update package lists
            task = progress.add_task("Updating package lists...", total=1)
            try:
                cmd = apt_cmd_prefix + ["apt-get", "update"]
                run_command(cmd)
                progress.update(
                    task, advance=1, status=f"[{NordColors.NORD14}]Complete"
                )
                print_success("Package lists updated.")
            except Exception as e:
                print_error(f"Failed to update package lists: {e}")
                progress.update(task, advance=1, status=f"[{NordColors.NORD11}]Failed")
                return False

            # Install system dependencies
            task = progress.add_task(
                "Installing system dependencies...", total=len(SYSTEM_DEPENDENCIES)
            )
            for package in SYSTEM_DEPENDENCIES:
                try:
                    cmd = apt_cmd_prefix + ["apt-get", "install", "-y", package]
                    run_command(cmd)
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD14}]Installed"
                    )
                    print_success(f"{package} installed.")
                except Exception as e:
                    print_error(f"Failed to install {package}: {e}")
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD11}]Failed"
                    )

            print_success("System dependencies installed successfully.")
            return True
        except Exception as e:
            print_error(f"Error installing system dependencies: {e}")
            return False


def install_pipx() -> bool:
    """Ensure pipx is installed; install it using pip if missing."""
    print_section("Installing pipx")

    if shutil.which("pipx") is not None:
        print_success("pipx is already installed.")
        return True

    print_step("Installing pipx...")
    try:
        # First try with apt
        apt_cmd_prefix = [] if check_root() else ["sudo"]
        try:
            run_command(apt_cmd_prefix + ["apt-get", "install", "-y", "python3-pipx"])
            if shutil.which("pipx") is not None:
                print_success("pipx installed successfully using apt.")
                return True
        except Exception:
            print_warning("Could not install pipx via apt. Trying with pip...")

        # If apt fails, try with pip
        run_command(["python3", "-m", "pip", "install", "--user", "pipx"])
        run_command(["python3", "-m", "pipx", "ensurepath"])

        # Verify installation
        if shutil.which("pipx") is None:
            print_warning(
                "pipx installed but not in PATH. You may need to restart your shell."
            )
            # Try to use direct path as fallback
            home = os.path.expanduser("~")
            pipx_path = os.path.join(home, ".local", "bin", "pipx")
            if os.path.exists(pipx_path):
                print_info(f"Found pipx at {pipx_path}")
                os.environ["PATH"] = (
                    f"{os.path.dirname(pipx_path)}:{os.environ['PATH']}"
                )
                print_success("Added pipx to PATH for this session.")
                return True
            return False
        else:
            print_success("pipx installed successfully via pip.")
            return True
    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools() -> bool:
    """Install Python tools system-wide via pipx."""
    print_section("Installing Python Tools via pipx")

    if not install_pipx():
        print_error("Failed to ensure pipx installation.")
        return False

    with ProgressManager() as progress:
        task = progress.add_task("Installing pipx packages", total=len(PIPX_TOOLS))
        failed_tools = []

        for tool in PIPX_TOOLS:
            try:
                print_step(f"Installing {tool} via pipx...")
                run_command(["pipx", "install", tool])
                progress.update(
                    task, advance=1, status=f"[{NordColors.NORD14}]Installed"
                )
                print_success(f"Installed {tool} via pipx.")
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)
                progress.update(task, advance=1, status=f"[{NordColors.NORD11}]Failed")

        if failed_tools:
            print_warning(
                f"Failed to install the following tools: {', '.join(failed_tools)}"
            )
            return False

        print_success("Python tools installation completed.")
        return True


def setup_virtual_environment(project_path: str = DEFAULT_PROJECT_DIR) -> bool:
    """Create a Python virtual environment and an activation script."""
    print_section("Setting Up Virtual Environment")

    try:
        # Check if venv module is available
        run_command(["python3", "-m", "venv", "--help"], capture_output=True)

        # Create virtual environment
        venv_path = os.path.join(project_path, ".venv")
        print_step(f"Creating virtual environment at: {venv_path}")

        # Create venv with progress indicator
        with ProgressManager() as progress:
            task = progress.add_task("Creating virtual environment", total=1)
            try:
                run_command(["python3", "-m", "venv", venv_path])
                progress.update(
                    task, advance=1, status=f"[{NordColors.NORD14}]Complete"
                )
                print_success(f"Virtual environment created at: {venv_path}")
            except Exception as e:
                print_error(f"Error creating virtual environment: {e}")
                progress.update(task, advance=1, status=f"[{NordColors.NORD11}]Failed")
                return False

        # Create activation script
        activate_script = os.path.join(project_path, "activate")
        print_step(f"Creating activation script at: {activate_script}")

        with open(activate_script, "w") as f:
            f.write(f"""#!/bin/bash
# Activate Python virtual environment
source {venv_path}/bin/activate
""")

        os.chmod(activate_script, 0o755)
        print_success(f"Activation script created at: {activate_script}")

        return True
    except Exception as e:
        print_error(f"Error setting up virtual environment: {e}")
        return False


def install_development_tools(venv_path: Optional[str] = None) -> bool:
    """Install common Python development tools in virtual environment."""
    print_section("Installing Development Tools")

    try:
        # Determine pip command based on venv
        if venv_path:
            pip_path = os.path.join(venv_path, "bin", "pip")
            pip_cmd = [pip_path]
        else:
            pip_cmd = ["python3", "-m", "pip"]

        # Upgrade pip first
        print_step("Upgrading pip...")
        try:
            run_command(pip_cmd + ["install", "--upgrade", "pip"])
            print_success("pip upgraded.")
        except Exception as e:
            print_warning(f"Failed to upgrade pip: {e}")

        # Install development tools
        with ProgressManager() as progress:
            task = progress.add_task(
                "Installing development tools", total=len(DEV_TOOLS)
            )

            for tool in DEV_TOOLS:
                try:
                    print_step(f"Installing {tool}...")
                    run_command(pip_cmd + ["install", "--upgrade", tool])
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD14}]Installed"
                    )
                    print_success(f"{tool} installed.")
                except Exception as e:
                    print_warning(f"Failed to install {tool}: {e}")
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD11}]Failed"
                    )

        print_success("Development tools installation completed.")
        return True
    except Exception as e:
        print_error(f"Error installing development tools: {e}")
        return False


def create_project_template() -> bool:
    """Create a basic Python project template with package and test directories."""
    print_section("Creating Project Template")

    try:
        project_name = get_user_input("Enter project name:")
        if not project_name:
            print_error("Project name cannot be empty.")
            return False

        project_path = os.path.join(os.getcwd(), project_name)
        if os.path.exists(project_path):
            if not get_user_confirmation(
                f"Project directory {project_path} already exists. Overwrite?"
            ):
                print_warning("Project creation aborted.")
                return False

        print_step(f"Creating project structure at {project_path}")

        # Create directories
        package_dir = os.path.join(project_path, project_name)
        tests_dir = os.path.join(project_path, "tests")
        os.makedirs(package_dir, exist_ok=True)
        os.makedirs(tests_dir, exist_ok=True)

        # Create project files
        with ProgressManager() as progress:
            files_to_create = [
                (
                    os.path.join(package_dir, "__init__.py"),
                    "# Package initialization\n",
                ),
                (
                    os.path.join(package_dir, "main.py"),
                    """def main():
    print('Hello, World!')

if __name__ == '__main__':
    main()
""",
                ),
                (
                    os.path.join(tests_dir, "test_main.py"),
                    """def test_main():
    assert True  # Placeholder test
""",
                ),
                (
                    os.path.join(project_path, "README.md"),
                    f"# {project_name}\n\nA Python project.\n",
                ),
                (
                    os.path.join(project_path, "requirements.txt"),
                    "# Add project dependencies here\n",
                ),
                (
                    os.path.join(project_path, "setup.py"),
                    f"""from setuptools import setup, find_packages

setup(
    name="{project_name}",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # Add dependencies here
    ],
    entry_points={{
        'console_scripts': [
            '{project_name}={project_name}.main:main',
        ],
    }},
)
""",
                ),
            ]

            task = progress.add_task(
                "Creating project files", total=len(files_to_create)
            )

            for filepath, content in files_to_create:
                try:
                    with open(filepath, "w") as f:
                        f.write(content)
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD14}]Created"
                    )
                except Exception as e:
                    print_error(f"Failed to create {filepath}: {e}")
                    progress.update(
                        task, advance=1, status=f"[{NordColors.NORD11}]Failed"
                    )

        # Ask about creating a virtual environment
        if get_user_confirmation("Create a virtual environment for this project?"):
            setup_virtual_environment(project_path)

            # Ask about installing dev tools in the new venv
            if get_user_confirmation(
                "Install development tools in the virtual environment?"
            ):
                venv_path = os.path.join(project_path, ".venv")
                install_development_tools(venv_path)

        print_success(f"Project template created at: {project_path}")
        return True
    except Exception as e:
        print_error(f"Error creating project template: {e}")
        return False


# ==============================
# Menu System
# ==============================
def interactive_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"Python: {platform.python_version()}")
        print_info(f"Running as root: {'Yes' if check_root() else 'No'}")

        # Main menu options
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Install System Dependencies"),
            ("3", "Install pipx and Python Tools"),
            ("4", "Set Up Virtual Environment"),
            ("5", "Install Development Tools"),
            ("6", "Create Project Template"),
            ("7", "Run Full Setup"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-7):")

        if choice == "1":
            check_system()
            pause()
        elif choice == "2":
            install_system_dependencies()
            pause()
        elif choice == "3":
            install_pipx_tools()
            pause()
        elif choice == "4":
            project_path = get_user_input(
                "Enter directory path for virtual environment (or press Enter for current directory):",
                DEFAULT_PROJECT_DIR,
            )
            setup_virtual_environment(project_path)
            pause()
        elif choice == "5":
            venv_path = get_user_input(
                "Enter virtual environment path (or press Enter to install globally):"
            )
            if venv_path:
                install_development_tools(venv_path)
            else:
                install_development_tools()
            pause()
        elif choice == "6":
            create_project_template()
            pause()
        elif choice == "7":
            run_full_setup()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Python Dev Setup Tool.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


def run_full_setup() -> None:
    """Run the complete setup process."""
    print_section("Full Python Dev Setup")

    if not check_system():
        print_error("System check failed. Please resolve issues before continuing.")
        return

    print_step("Starting full setup process...")

    # Install system dependencies
    if not install_system_dependencies():
        print_warning("Some system dependencies may not have been installed.")
        if not get_user_confirmation("Continue with the setup process?"):
            print_warning("Setup aborted.")
            return

    # Install pipx and Python tools
    if not install_pipx_tools():
        print_warning("Some Python tools may not have been installed.")
        if not get_user_confirmation("Continue with the setup process?"):
            print_warning("Setup aborted.")
            return

    # Ask about virtual environment
    if get_user_confirmation("Create a virtual environment?"):
        venv_path = get_user_input(
            "Enter directory path (or press Enter for current directory):",
            DEFAULT_PROJECT_DIR,
        )
        if not setup_virtual_environment(venv_path):
            print_warning("Virtual environment setup failed.")
        else:
            # Install dev tools in the venv
            if get_user_confirmation(
                "Install development tools in the virtual environment?"
            ):
                venv_full_path = os.path.join(venv_path, ".venv")
                if not install_development_tools(venv_full_path):
                    print_warning("Development tools installation failed.")

    # Create project template
    if get_user_confirmation("Create a project template?"):
        if not create_project_template():
            print_warning("Project template creation failed.")

    print_success("Setup process completed!")


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Setup signal handlers and cleanup
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(cleanup)

        # Launch the interactive menu
        interactive_menu()

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Setup interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
