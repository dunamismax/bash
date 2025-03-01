#!/usr/bin/env python3
"""
Python Development Environment Setup Tool

This utility sets up a Python development environment on Ubuntu/Linux:
  • Performs system checks and installs system-level dependencies.
  • Installs pipx (if missing) and uses pipx to install 20 recommended Python tools.
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

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
DEFAULT_PROJECT_DIR = os.getcwd()
SYSTEM_DEPENDENCIES = [
    "build-essential", "libssl-dev", "zlib1g-dev", "libbz2-dev", "libreadline-dev",
    "libsqlite3-dev", "libncurses5-dev", "libncursesw5-dev", "xz-utils", "tk-dev",
    "libffi-dev", "liblzma-dev", "python3-dev"
]
# Top 20 recommended Python libraries and tools (including our CLI dependencies)
TOP_PYTHON_TOOLS = [
    "rich", "click", "pyfiglet", "black", "isort", "flake8", "mypy", "pytest",
    "pre-commit", "ipython", "cookiecutter", "virtualenv", "pylint", "sphinx",
    "twine", "autopep8", "bandit", "poetry", "pydocstyle", "yapf"
]
PIPX_TOOLS = TOP_PYTHON_TOOLS  # Tools to be installed via pipx

# ------------------------------
# Nord‑Themed Styles & Console Setup
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
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    print_step("Performing cleanup tasks...")

atexit.register(cleanup)

def signal_handler(sig, frame) -> None:
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------
# Helper Functions for Command Execution
# ------------------------------
def run_command(cmd: list[str], capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    try:
        print_step(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=capture_output, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
        raise

# ------------------------------
# Core Functions
# ------------------------------
def check_system() -> None:
    """Check system compatibility and required tools."""
    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")
    print_step(f"Current Python version: {platform.python_version()}")
    required_tools = ["git", "curl", "gcc"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        print_error(f"Missing required tools: {', '.join(missing)}. Install these before continuing.")
        sys.exit(1)
    print_success("System check passed.")

def install_system_dependencies() -> None:
    """Install system-level dependencies using apt-get."""
    print_section("Installing System Dependencies")
    try:
        run_command(["sudo", "apt-get", "update"])
        run_command(["sudo", "apt-get", "install", "-y"] + SYSTEM_DEPENDENCIES)
        print_success("System dependencies installed successfully.")
    except Exception as e:
        print_error(f"Error installing system dependencies: {e}")
        sys.exit(1)

def install_pipx() -> None:
    """Ensure pipx is installed; install it using pip if missing."""
    print_section("Installing pipx")
    if shutil.which("pipx") is None:
        try:
            run_command(["python3", "-m", "pip", "install", "--user", "pipx"])
            run_command(["python3", "-m", "pipx", "ensurepath"])
            print_success("pipx installed successfully. You may need to restart your shell.")
        except Exception as e:
            print_error(f"Error installing pipx: {e}")
            sys.exit(1)
    else:
        print_success("pipx is already installed.")

def install_pipx_tools() -> None:
    """Install top Python tools system-wide via pipx."""
    print_section("Installing Python Tools via pipx")
    install_pipx()  # Ensure pipx is installed
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        console=console,
    ) as progress:
        task = progress.add_task("Installing pipx packages", total=len(PIPX_TOOLS))
        for tool in PIPX_TOOLS:
            try:
                run_command(["pipx", "install", tool])
                print_success(f"Installed {tool} via pipx.")
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
            progress.advance(task)
    print_success("pipx tools installation completed.")

def setup_virtual_environment(project_path: str = DEFAULT_PROJECT_DIR) -> None:
    """Create a Python virtual environment and an activation script."""
    print_section("Setting Up Virtual Environment")
    try:
        run_command(["python3", "-m", "venv", "--help"])
        venv_path = os.path.join(project_path, ".venv")
        run_command(["python3", "-m", "venv", venv_path])
        print_success(f"Virtual environment created at: {venv_path}")
        activate_script = os.path.join(project_path, "activate")
        with open(activate_script, "w") as f:
            f.write(f"""#!/bin/bash
# Activate Python virtual environment
source {venv_path}/bin/activate
""")
        os.chmod(activate_script, 0o755)
        print_success(f"Activation script created at: {activate_script}")
    except Exception as e:
        print_error(f"Error setting up virtual environment: {e}")
        sys.exit(1)

def install_development_tools() -> None:
    """Install common Python development tools via pip."""
    print_section("Installing Development Tools via pip")
    try:
        dev_tools = ["pip", "setuptools", "wheel", "black", "isort", "mypy", "flake8", "pytest"]
        run_command(["python3", "-m", "pip", "install", "--user", "--upgrade"] + dev_tools)
        print_success("Development tools installed successfully.")
    except Exception as e:
        print_error(f"Error installing development tools: {e}")
        sys.exit(1)

def create_project_template(project_name: str) -> None:
    """Create a basic Python project template with package and test directories."""
    print_section("Creating Project Template")
    try:
        project_path = os.path.join(os.getcwd(), project_name)
        os.makedirs(project_path, exist_ok=True)
        package_dir = os.path.join(project_path, project_name)
        tests_dir = os.path.join(project_path, "tests")
        os.makedirs(package_dir, exist_ok=True)
        os.makedirs(tests_dir, exist_ok=True)
        with open(os.path.join(package_dir, "__init__.py"), "w") as f:
            f.write("# Package initialization\n")
        with open(os.path.join(package_dir, "main.py"), "w") as f:
            f.write("def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n")
        with open(os.path.join(tests_dir, "test_main.py"), "w") as f:
            f.write("def test_main():\n    assert True  # Placeholder test\n")
        with open(os.path.join(project_path, "README.md"), "w") as f:
            f.write(f"# {project_name}\n\nA Python project.\n")
        with open(os.path.join(project_path, "requirements.txt"), "w") as f:
            f.write("# Add project dependencies here\n")
        setup_virtual_environment(project_path)
        print_success(f"Project template created at: {project_path}")
    except Exception as e:
        print_error(f"Error creating project template: {e}")
        sys.exit(1)

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.group()
@click.version_option("1.0.0")
def cli() -> None:
    """
    Python Development Environment Setup Tool - Nord Themed CLI

    This tool installs system dependencies, sets up pipx with top Python tools,
    creates a virtual environment, installs development tools, and builds a project template.
    """
    if os.geteuid() != 0:
        print_warning("Some operations may require root privileges. Use sudo if needed.")

@cli.command()
def system() -> None:
    """Install system-level dependencies."""
    print_header("System Dependency Installation")
    check_system()
    install_system_dependencies()

@cli.command()
def pipx_install() -> None:
    """Install pipx and top Python tools via pipx."""
    print_header("pipx and Tools Installation")
    install_pipx_tools()

@cli.command()
@click.option("--path", default=DEFAULT_PROJECT_DIR, help="Directory for the virtual environment")
def venv(path: str) -> None:
    """Create a Python virtual environment."""
    print_header("Virtual Environment Setup")
    setup_virtual_environment(path)

@cli.command()
def devtools() -> None:
    """Install development tools via pip."""
    print_header("Development Tools Installation")
    install_development_tools()

@cli.command()
@click.argument("project_name", required=True)
def project(project_name: str) -> None:
    """Create a new Python project template."""
    print_header("Project Template Creation")
    create_project_template(project_name)

if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        sys.exit(1)