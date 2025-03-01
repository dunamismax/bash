#!/usr/bin/env python3
"""
Python Development Environment Setup Tool

This utility sets up a Python development environment on Ubuntu/Linux:
  • Performs system checks and installs system-level dependencies.
  • Installs pipx (if missing) and uses pipx to install recommended Python tools.
  • Creates a Python virtual environment.
  • Installs common development tools via pip.
  • Generates a basic Python project template.

Note: Some operations require root privileges. Run with sudo if necessary.
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
from typing import List, Dict, Any, Optional, Union

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
DEFAULT_PROJECT_DIR = os.getcwd()
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
]

# Top 20 recommended Python libraries and tools
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

PIPX_TOOLS = TOP_PYTHON_TOOLS  # Tools to be installed via pipx

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
    cmd: List[str], capture_output: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Execute a command and handle errors appropriately."""
    try:
        print_step(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
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
    # Add any necessary cleanup steps here.


# ------------------------------
# Core Functions
# ------------------------------
def check_system() -> bool:
    """Check system compatibility and required tools."""
    print_section("Checking System Compatibility")

    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")

    print_step(f"Current Python version: {platform.python_version()}")

    required_tools = ["git", "curl", "gcc"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]

    if missing:
        print_error(
            f"Missing required tools: {', '.join(missing)}. Install these before continuing."
        )
        return False

    print_success("System check passed.")
    return True


def install_system_dependencies() -> bool:
    """Install system-level dependencies using apt-get."""
    print_section("Installing System Dependencies")

    if os.geteuid() != 0:
        print_warning("Root privileges required for system dependencies installation.")
        choice = input("Try using sudo? (y/n): ").strip().lower()
        if choice != "y":
            print_error("Skipping system dependencies installation.")
            return False

    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        try:
            # Update package lists
            task = progress.add_task("Updating package lists...", total=1)
            try:
                cmd = (
                    ["sudo", "apt-get", "update"]
                    if os.geteuid() != 0
                    else ["apt-get", "update"]
                )
                run_command(cmd)
                progress.advance(task)
                print_success("Package lists updated.")
            except Exception as e:
                print_error(f"Failed to update package lists: {e}")
                return False

            # Install system dependencies
            task = progress.add_task(
                "Installing system dependencies...", total=len(SYSTEM_DEPENDENCIES)
            )
            for package in SYSTEM_DEPENDENCIES:
                try:
                    cmd = (
                        ["sudo", "apt-get", "install", "-y", package]
                        if os.geteuid() != 0
                        else ["apt-get", "install", "-y", package]
                    )
                    run_command(cmd)
                    progress.advance(task)
                    print_success(f"{package} installed.")
                except Exception as e:
                    print_error(f"Failed to install {package}: {e}")

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

    try:
        with console.status("[bold #81A1C1]Installing pipx...", spinner="dots"):
            run_command(["python3", "-m", "pip", "install", "--user", "pipx"])
            run_command(["python3", "-m", "pipx", "ensurepath"])

        # Verify installation
        if shutil.which("pipx") is None:
            print_warning(
                "pipx installed but not in PATH. You may need to restart your shell."
            )
        else:
            print_success("pipx installed successfully.")

        return True
    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools() -> bool:
    """Install top Python tools system-wide via pipx."""
    print_section("Installing Python Tools via pipx")

    if not install_pipx():
        print_error("Failed to ensure pipx installation.")
        return False

    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Installing pipx packages", total=len(PIPX_TOOLS))
        failed_tools = []

        for tool in PIPX_TOOLS:
            try:
                print_step(f"Installing {tool} via pipx...")
                run_command(["pipx", "install", tool])
                print_success(f"Installed {tool} via pipx.")
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)

            progress.advance(task)

        if failed_tools:
            print_warning(
                f"Failed to install the following tools: {', '.join(failed_tools)}"
            )
            return False

        print_success("pipx tools installation completed.")
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

        with console.status(
            "[bold #81A1C1]Creating virtual environment...", spinner="dots"
        ):
            run_command(["python3", "-m", "venv", venv_path])

        print_success(f"Virtual environment created at: {venv_path}")

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
    """Install common Python development tools via pip."""
    print_section("Installing Development Tools via pip")

    dev_tools = [
        "pip",
        "setuptools",
        "wheel",
        "black",
        "isort",
        "mypy",
        "flake8",
        "pytest",
    ]

    try:
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Installing dev tools", total=len(dev_tools))

            pip_cmd = ["python3", "-m", "pip"]
            if venv_path:
                pip_cmd = [os.path.join(venv_path, "bin", "pip")]

            for tool in dev_tools:
                try:
                    print_step(f"Installing {tool}...")
                    run_command(pip_cmd + ["install", "--upgrade", tool])
                    print_success(f"{tool} installed.")
                except Exception as e:
                    print_warning(f"Failed to install {tool}: {e}")
                progress.advance(task)

            print_success("Development tools installed successfully.")
            return True
    except Exception as e:
        print_error(f"Error installing development tools: {e}")
        return False


def create_project_template() -> bool:
    """Create a basic Python project template with package and test directories."""
    print_section("Creating Project Template")

    try:
        project_name = input("Enter project name: ").strip()
        if not project_name:
            print_error("Project name cannot be empty.")
            return False

        project_path = os.path.join(os.getcwd(), project_name)
        if os.path.exists(project_path):
            overwrite = (
                input(
                    f"Project directory {project_path} already exists. Overwrite? (y/n): "
                )
                .lower()
                .strip()
            )
            if overwrite != "y":
                print_warning("Project creation aborted.")
                return False

        print_step(f"Creating project structure at {project_path}")

        # Create directories
        package_dir = os.path.join(project_path, project_name)
        tests_dir = os.path.join(project_path, "tests")
        os.makedirs(package_dir, exist_ok=True)
        os.makedirs(tests_dir, exist_ok=True)

        # Create package files
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating project files", total=5)

            # Create __init__.py
            with open(os.path.join(package_dir, "__init__.py"), "w") as f:
                f.write("# Package initialization\n")
            progress.advance(task)

            # Create main.py
            with open(os.path.join(package_dir, "main.py"), "w") as f:
                f.write("""def main():
    print('Hello, World!')

if __name__ == '__main__':
    main()
""")
            progress.advance(task)

            # Create test file
            with open(os.path.join(tests_dir, "test_main.py"), "w") as f:
                f.write("""def test_main():
    assert True  # Placeholder test
""")
            progress.advance(task)

            # Create README.md
            with open(os.path.join(project_path, "README.md"), "w") as f:
                f.write(f"# {project_name}\n\nA Python project.\n")
            progress.advance(task)

            # Create requirements.txt
            with open(os.path.join(project_path, "requirements.txt"), "w") as f:
                f.write("# Add project dependencies here\n")
            progress.advance(task)

        # Create virtual environment
        setup_virtual_environment(project_path)

        print_success(f"Project template created at: {project_path}")
        return True
    except Exception as e:
        print_error(f"Error creating project template: {e}")
        return False


def check_root_permissions() -> bool:
    """Check if script is running with root permissions."""
    if os.geteuid() != 0:
        print_warning(
            "Some operations may require root privileges. Consider running with sudo."
        )
        return False
    return True


def interactive_menu() -> None:
    """Display the interactive menu and process user selections."""
    while True:
        print_header("Python Dev Setup")
        console.print("1. Check System Compatibility")
        console.print("2. Install System Dependencies")
        console.print("3. Install pipx and Python Tools")
        console.print("4. Set Up Virtual Environment")
        console.print("5. Install Development Tools")
        console.print("6. Create Project Template")
        console.print("7. Run Full Setup")
        console.print("8. Exit")

        choice = input("\nSelect an option (1-8): ").strip()

        if choice == "1":
            check_system()
        elif choice == "2":
            install_system_dependencies()
        elif choice == "3":
            install_pipx_tools()
        elif choice == "4":
            project_path = input(
                "Enter directory path for virtual environment (or press Enter for current directory): "
            ).strip()
            if not project_path:
                project_path = DEFAULT_PROJECT_DIR
            setup_virtual_environment(project_path)
        elif choice == "5":
            install_development_tools()
        elif choice == "6":
            create_project_template()
        elif choice == "7":
            run_full_setup()
        elif choice == "8":
            print_header("Exiting Setup")
            break
        else:
            print_warning("Invalid selection, please try again.")

        input("\nPress Enter to return to the menu...")


def run_full_setup() -> None:
    """Run the complete setup process."""
    print_header("Full Python Dev Setup")

    if not check_system():
        print_error("System check failed. Please resolve issues before continuing.")
        return

    if not install_system_dependencies():
        print_warning("Some system dependencies may not have been installed.")

    if not install_pipx_tools():
        print_warning("Some Python tools may not have been installed.")

    default_path = DEFAULT_PROJECT_DIR
    create_venv = input("Create a virtual environment? (y/n): ").strip().lower()
    if create_venv == "y":
        custom_path = input(
            "Enter directory path (or press Enter for current directory): "
        ).strip()
        if custom_path:
            default_path = custom_path
        if not setup_virtual_environment(default_path):
            print_warning("Virtual environment setup failed.")

    install_tools = input("Install development tools? (y/n): ").strip().lower()
    if install_tools == "y":
        if not install_development_tools():
            print_warning("Development tools installation failed.")

    create_project = input("Create a project template? (y/n): ").strip().lower()
    if create_project == "y":
        if not create_project_template():
            print_warning("Project template creation failed.")

    print_success("Setup process completed!")


def main() -> None:
    # Setup signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_header("Python Dev Setup")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )
    console.print(f"Python: [bold #D8DEE9]{platform.python_version()}[/bold #D8DEE9]")

    check_root_permissions()
    interactive_menu()


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
