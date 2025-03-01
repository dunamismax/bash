#!/usr/bin/env python3
"""
Enhanced Python Development Environment Setup Tool
-------------------------------------------------

A beautiful, interactive terminal-based utility for setting up a Python development
environment on Ubuntu/Linux systems. This tool provides options to:
  • Perform system checks and install system-level dependencies
  • Install pyenv and the latest version of Python
  • Install pipx (if missing) and use it to install recommended Python tools

All functionality is menu-driven with an attractive Nord-themed interface.

Note: This script is designed to be run with root/sudo privileges.

Version: 3.0.0
"""

import atexit
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import getpass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, Set, Callable

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
    from rich.live import Live
    from rich.layout import Layout
    from rich.status import Status
    from rich import box
    import pyfiglet
except ImportError:
    # If Rich is not installed, install it first
    print("Installing required dependencies...")
    original_user = os.environ.get("SUDO_USER", None)
    if original_user:
        # Get the original user's home directory
        user_home = (
            subprocess.check_output(["getent", "passwd", original_user])
            .decode()
            .split(":")[5]
        )

        # Install pip packages as the original user, not as root
        cmd = [
            "sudo",
            "-u",
            original_user,
            "pip",
            "install",
            "--user",
            "rich",
            "pyfiglet",
        ]
        subprocess.run(cmd, check=True)
    else:
        # Fall back to system pip if not run with sudo
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"], check=True
        )

    # Then import again
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
    from rich.live import Live
    from rich.layout import Layout
    from rich.status import Status
    from rich import box
    import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Python Dev Setup"
VERSION = "3.0.0"

# Get the original non-root user if the script is run with sudo
ORIGINAL_USER = os.environ.get("SUDO_USER", getpass.getuser())
ORIGINAL_UID = int(
    subprocess.check_output(["id", "-u", ORIGINAL_USER]).decode().strip()
)
ORIGINAL_GID = int(
    subprocess.check_output(["id", "-g", ORIGINAL_USER]).decode().strip()
)

# Get the original user's home directory
if ORIGINAL_USER != "root":
    HOME_DIR = (
        subprocess.check_output(["getent", "passwd", ORIGINAL_USER])
        .decode()
        .split(":")[5]
    )
else:
    HOME_DIR = os.path.expanduser("~")

PYENV_DIR = os.path.join(HOME_DIR, ".pyenv")
PYENV_BIN = os.path.join(PYENV_DIR, "bin", "pyenv")

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

# Top Python tools to install with pipx
# Note: Rich is removed from this list as it's a library, not an application
PIPX_TOOLS = [
    "black",
    "isort",
    "flake8",
    "mypy",
    "pytest",
    "pre-commit",
    "ipython",
    "cookiecutter",
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

# User libraries to install with pip (not pipx)
USER_PIP_LIBRARIES = [
    "rich",
    "pyfiglet",
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
    console.print(
        Panel(
            ascii_art,
            style=f"bold {NordColors.NORD8}",
            border_style=f"bold {NordColors.NORD9}",
            expand=False,
        )
    )


def print_section(title: str) -> None:
    """Print a formatted section header."""
    console.print(
        Panel(
            title,
            style=f"bold {NordColors.NORD8}",
            border_style=f"bold {NordColors.NORD9}",
            expand=True,
        )
    )


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
    table = Table(
        title=title,
        box=box.ROUNDED,
        title_style=f"bold {NordColors.NORD8}",
        expand=True,
    )
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="center", width=8)
    table.add_column("Description", style=f"{NordColors.NORD4}")

    for key, description in options:
        table.add_row(key, description)

    return table


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_info("Performing cleanup tasks...")
    time.sleep(0.5)  # Give a visual indication of cleanup


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
# System Helper Functions
# ==============================
def run_command(
    cmd: List[str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = 300,  # Extended timeout for longer operations
    verbose: bool = False,
    as_user: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a shell command and handle errors.

    If as_user is True, runs the command as the original non-root user when
    the script is run with sudo.
    """
    # If we need to run as the original user and the command isn't already prefixed
    if as_user and ORIGINAL_USER != "root" and not (cmd and cmd[0] == "sudo"):
        # Modify the command to run as the original user
        cmd = ["sudo", "-u", ORIGINAL_USER] + cmd

    if verbose:
        if shell:
            print_step(f"Executing: {cmd}")
        else:
            print_step(f"Executing: {' '.join(cmd)}")

    try:
        # Execute the command
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
            console.print(
                Panel(
                    e.stderr.strip(),
                    title="Error Output",
                    border_style=f"bold {NordColors.NORD11}",
                )
            )
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


def fix_ownership(path, recursive=True):
    """Fix ownership of files to be owned by the original user, not root."""
    if ORIGINAL_USER == "root":
        return  # No need to change if we're already running as root

    if recursive and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for d in dirs:
                os.chown(os.path.join(root, d), ORIGINAL_UID, ORIGINAL_GID)
            for f in files:
                os.chown(os.path.join(root, f), ORIGINAL_UID, ORIGINAL_GID)

    # Change the parent path itself
    if os.path.exists(path):
        os.chown(path, ORIGINAL_UID, ORIGINAL_GID)


def check_command_available(command: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(command) is not None


# ==============================
# Core Functions
# ==============================
def check_system() -> bool:
    """Check system compatibility and required tools."""
    print_section("Checking System Compatibility")

    # Verify root privileges
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges (sudo).")
        return False

    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")
        if not get_user_confirmation("Continue anyway?"):
            return False

    # Create a table for system information
    table = Table(title="System Information", box=box.ROUNDED)
    table.add_column("Component", style=f"bold {NordColors.NORD9}")
    table.add_column("Value", style=f"{NordColors.NORD4}")

    table.add_row("Python Version", platform.python_version())
    table.add_row("Operating System", platform.platform())
    table.add_row("Running as", "root")
    table.add_row("Setting up for user", ORIGINAL_USER)
    table.add_row("User home directory", HOME_DIR)
    console.print(table)

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

    try:
        # Update package lists
        print_info("Updating package lists...")
        try:
            run_command(["apt-get", "update"])
            print_success("Package lists updated.")
        except Exception as e:
            print_error(f"Failed to update package lists: {e}")
            return False

        # Install system dependencies
        total_packages = len(SYSTEM_DEPENDENCIES)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            expand=True,
        ) as progress:
            task = progress.add_task(
                "[bold green]Installing system dependencies...", total=total_packages
            )

            for package in SYSTEM_DEPENDENCIES:
                try:
                    progress.update(
                        task, description=f"[bold green]Installing {package}..."
                    )
                    run_command(["apt-get", "install", "-y", package])
                    progress.update(task, advance=1)
                    print_success(f"{package} installed.")
                except Exception as e:
                    print_error(f"Failed to install {package}: {e}")
                    progress.update(task, advance=1)

        print_success("System dependencies installed successfully.")
        return True
    except Exception as e:
        print_error(f"Error installing system dependencies: {e}")
        return False


def install_pip_libraries_for_user() -> bool:
    """Install libraries like Rich for the user (not as root)."""
    print_section("Installing User Python Libraries")

    try:
        print_info(f"Installing Python libraries for user {ORIGINAL_USER}...")

        # Strategy 1: Try to use apt first (recommended for Debian/Ubuntu systems)
        apt_available = check_command_available("apt-get")
        apt_success = False

        if apt_available:
            print_info("Attempting to install libraries via apt...")
            try:
                for library in USER_PIP_LIBRARIES:
                    apt_pkg = f"python3-{library.lower()}"
                    print_step(f"Installing {apt_pkg} via apt...")
                    try:
                        run_command(["apt-get", "install", "-y", apt_pkg])
                        print_success(f"{library} installed via apt.")
                        apt_success = True
                    except:
                        print_info(
                            f"Package {apt_pkg} not available in apt repositories."
                        )
            except Exception as e:
                print_warning(f"Error using apt: {e}")

        # If apt failed or wasn't available, create a venv and install there
        if not apt_success:
            print_info("Setting up a virtual environment for Python libraries...")

            # Create a venv in /opt/pysetup
            venv_dir = "/opt/pysetup"
            if not os.path.exists(venv_dir):
                os.makedirs(venv_dir, exist_ok=True)

            # Create the virtual environment
            run_command(["python3", "-m", "venv", venv_dir])

            # Install libraries in the venv
            venv_pip = os.path.join(venv_dir, "bin", "pip")
            for library in USER_PIP_LIBRARIES:
                print_step(f"Installing {library} in virtual environment...")
                run_command([venv_pip, "install", library])
                print_success(f"{library} installed in virtual environment.")

            # Make it accessible to the user
            fix_ownership(venv_dir)

            # Create symlinks to the executables
            bin_dir = "/usr/local/bin"
            for library in USER_PIP_LIBRARIES:
                # Common patterns for executable names
                possible_execs = [
                    os.path.join(venv_dir, "bin", library),
                    os.path.join(venv_dir, "bin", library.lower()),
                ]

                for exec_path in possible_execs:
                    if os.path.exists(exec_path):
                        symlink_path = os.path.join(
                            bin_dir, os.path.basename(exec_path)
                        )
                        # Create the symlink if it doesn't exist
                        if not os.path.exists(symlink_path):
                            try:
                                os.symlink(exec_path, symlink_path)
                                print_success(
                                    f"Created symlink for {library} in {bin_dir}"
                                )
                            except Exception as e:
                                print_warning(f"Failed to create symlink: {e}")

            # Inform the user about the virtual environment
            print_info(f"Python libraries installed in virtual environment: {venv_dir}")
            print_info(f"To use this environment: source {venv_dir}/bin/activate")

        return True
    except Exception as e:
        print_error(f"Error installing user Python libraries: {e}")
        return False


def install_pyenv() -> bool:
    """Install pyenv for the target user."""
    print_section("Installing pyenv")

    # Check if pyenv is already installed
    if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
        print_success("pyenv is already installed.")
        return True

    print_step("Installing pyenv...")

    try:
        # Get the pyenv installer
        print_info("Downloading pyenv installer...")
        installer_script = "/tmp/pyenv_installer.sh"
        curl_cmd = ["curl", "-fsSL", "https://pyenv.run", "-o", installer_script]
        run_command(curl_cmd)

        # Make it executable
        os.chmod(installer_script, 0o755)

        print_info("Running pyenv installer...")

        # Run the installer as the original user
        if ORIGINAL_USER != "root":
            run_command(["sudo", "-u", ORIGINAL_USER, installer_script], as_user=True)
        else:
            run_command([installer_script])

        # Check if installation was successful
        if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
            print_success("pyenv installed successfully.")

            # Setup shell integration
            print_info("Setting up shell configuration...")
            shell_rc_files = [
                os.path.join(HOME_DIR, ".bashrc"),
                os.path.join(HOME_DIR, ".zshrc"),
            ]

            pyenv_init_lines = [
                "# pyenv initialization",
                'export PYENV_ROOT="$HOME/.pyenv"',
                'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"',
                'eval "$(pyenv init -)"',
                'eval "$(pyenv virtualenv-init -)"',
                "",
            ]

            for rc_file in shell_rc_files:
                if os.path.exists(rc_file):
                    # Read the content
                    with open(rc_file, "r") as f:
                        content = f.read()

                    # Only add if not already there
                    if "pyenv init" not in content:
                        # Write as the original user
                        if ORIGINAL_USER != "root":
                            # Create a temp file with the content to append
                            temp_file = "/tmp/pyenv_init.txt"
                            with open(temp_file, "w") as f:
                                f.write("\n" + "\n".join(pyenv_init_lines))

                            # Append it to the rc file as the original user
                            run_command(
                                [
                                    "sudo",
                                    "-u",
                                    ORIGINAL_USER,
                                    "bash",
                                    "-c",
                                    f"cat {temp_file} >> {rc_file}",
                                ],
                                as_user=True,
                            )
                            os.remove(temp_file)
                        else:
                            with open(rc_file, "a") as f:
                                f.write("\n" + "\n".join(pyenv_init_lines))

                        print_success(f"Added pyenv initialization to {rc_file}")

            # Fix ownership of pyenv directory
            fix_ownership(PYENV_DIR)

            return True
        else:
            print_error("pyenv installation failed.")
            return False

    except Exception as e:
        print_error(f"Error installing pyenv: {e}")
        return False


def install_latest_python_with_pyenv() -> bool:
    """Install the latest Python version using pyenv."""
    print_section("Installing Latest Python with pyenv")

    if not os.path.exists(PYENV_BIN):
        print_error("pyenv is not installed. Please install it first.")
        return False

    try:
        # Define command to run pyenv as the original user
        pyenv_cmd = [PYENV_BIN]
        if ORIGINAL_USER != "root":
            pyenv_cmd = ["sudo", "-u", ORIGINAL_USER, PYENV_BIN]

        # Update pyenv repository first (pyenv doesn't have an update command)
        print_info("Updating pyenv repository...")
        pyenv_root = os.path.dirname(os.path.dirname(PYENV_BIN))

        # Use git pull to update the pyenv repository
        if os.path.exists(os.path.join(pyenv_root, ".git")):
            if ORIGINAL_USER != "root":
                run_command(
                    ["sudo", "-u", ORIGINAL_USER, "git", "-C", pyenv_root, "pull"],
                    as_user=True,
                )
            else:
                run_command(["git", "-C", pyenv_root, "pull"])
        else:
            print_warning(
                "Could not update pyenv (not a git repository). Continuing anyway."
            )

        # Get latest Python version available
        print_info("Finding latest Python version...")
        latest_version_output = run_command(
            pyenv_cmd + ["install", "--list"], as_user=(ORIGINAL_USER != "root")
        ).stdout

        # Parse the output to find the latest stable Python version
        versions = re.findall(
            r"^\s*(\d+\.\d+\.\d+)$", latest_version_output, re.MULTILINE
        )
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False

        # Sort versions and get the latest
        latest_version = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])[
            -1
        ]

        console.print(
            f"Installing Python [bold]{latest_version}[/bold] (this may take several minutes)..."
        )

        # Install the latest version
        print_info(f"Running pyenv install for Python {latest_version}...")
        run_command(
            pyenv_cmd + ["install", "--skip-existing", latest_version],
            as_user=(ORIGINAL_USER != "root"),
        )

        # Set as global Python version
        print_info("Setting as global Python version...")
        run_command(
            pyenv_cmd + ["global", latest_version], as_user=(ORIGINAL_USER != "root")
        )

        # Verify installation
        pyenv_python = os.path.join(PYENV_DIR, "shims", "python")
        if os.path.exists(pyenv_python):
            # Run the Python version check as the original user
            if ORIGINAL_USER != "root":
                python_version = run_command(
                    ["sudo", "-u", ORIGINAL_USER, pyenv_python, "--version"],
                    as_user=True,
                ).stdout
            else:
                python_version = run_command([pyenv_python, "--version"]).stdout

            print_success(f"Successfully installed {python_version.strip()}")
            return True
        else:
            print_error("Python installation with pyenv failed.")
            return False

    except Exception as e:
        print_error(f"Error installing Python with pyenv: {e}")
        return False


def install_pipx() -> bool:
    """Ensure pipx is installed for the user."""
    print_section("Installing pipx")

    # Check if pipx is available in PATH
    if check_command_available("pipx"):
        print_success("pipx is already installed.")
        return True

    print_step("Installing pipx...")

    try:
        # Try to get python executable
        if ORIGINAL_USER != "root":
            # Use the original user's Python if possible
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = "python3"

            # Install pipx as the original user
            print_info(f"Installing pipx for user {ORIGINAL_USER}...")
            run_command(
                [
                    "sudo",
                    "-u",
                    ORIGINAL_USER,
                    python_cmd,
                    "-m",
                    "pip",
                    "install",
                    "--user",
                    "pipx",
                ],
                as_user=True,
            )
            run_command(
                ["sudo", "-u", ORIGINAL_USER, python_cmd, "-m", "pipx", "ensurepath"],
                as_user=True,
            )
        else:
            # Running as actual root, install normally
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = shutil.which("python3") or shutil.which("python")

            if not python_cmd:
                print_error("Could not find a Python executable.")
                return False

            print_info("Installing pipx...")
            run_command([python_cmd, "-m", "pip", "install", "pipx"])
            run_command([python_cmd, "-m", "pipx", "ensurepath"])

        # Verify installation
        user_bin_dir = os.path.join(HOME_DIR, ".local", "bin")
        pipx_path = os.path.join(user_bin_dir, "pipx")

        if os.path.exists(pipx_path) or check_command_available("pipx"):
            print_success("pipx installed successfully.")
            return True
        else:
            print_error("pipx installation could not be verified.")
            return False

    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools() -> bool:
    """Install Python tools via pipx."""
    print_section("Installing Python Tools via pipx")

    # Make sure pipx is installed
    if not check_command_available("pipx"):
        # Install pipx system-wide first
        print_info("Installing pipx system-wide...")
        try:
            run_command(["apt-get", "install", "-y", "pipx"])
        except Exception as e:
            print_warning(f"Could not install pipx via apt: {e}")
            # If apt installation failed, fall back to pip
            if not install_pipx():
                print_error("Failed to ensure pipx installation.")
                return False

    # Determine pipx command
    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        print_error("Could not find pipx executable.")
        return False

    print_info("Installing Python tools using pipx...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        expand=True,
    ) as progress:
        task = progress.add_task(
            "[bold green]Installing Python tools...", total=len(PIPX_TOOLS)
        )
        failed_tools = []

        # For each tool, figure out the best way to install it
        for tool in PIPX_TOOLS:
            try:
                progress.update(task, description=f"[bold green]Installing {tool}...")

                # First, try to install via apt if available
                apt_pkg = f"python3-{tool.lower()}"
                try:
                    apt_check = run_command(["apt-cache", "show", apt_pkg], check=False)
                    if apt_check.returncode == 0:
                        run_command(["apt-get", "install", "-y", apt_pkg])
                        print_success(f"Installed {tool} via apt.")
                        progress.update(task, advance=1)
                        continue
                except Exception:
                    pass  # If apt fails, continue to pipx

                # Try using pipx (which creates isolated environments)
                run_command([pipx_cmd, "install", tool, "--force"])
                progress.update(task, advance=1)
                print_success(f"Installed {tool} via pipx.")

            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)
                progress.update(task, advance=1)

        if failed_tools:
            print_warning(
                f"Failed to install the following tools: {', '.join(failed_tools)}"
            )
            if len(failed_tools) < len(PIPX_TOOLS) / 2:  # If more than half succeeded
                return True
            return False

        print_success("Python tools installation completed.")
        return True


# ==============================
# Menu System
# ==============================
def interactive_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)

        # System info panel
        info = Table.grid(padding=1)
        info.add_column(style=f"bold {NordColors.NORD9}")
        info.add_column(style=f"{NordColors.NORD4}")

        info.add_row("Version:", VERSION)
        info.add_row("System:", f"{platform.system()} {platform.release()}")
        info.add_row("Python:", platform.python_version())
        info.add_row("Target User:", ORIGINAL_USER)

        # Check if pyenv is installed
        pyenv_status = "Installed" if os.path.exists(PYENV_BIN) else "Not installed"
        info.add_row("pyenv:", pyenv_status)

        # Check if pipx is installed
        pipx_status = (
            "Installed" if check_command_available("pipx") else "Not installed"
        )
        info.add_row("pipx:", pipx_status)

        console.print(
            Panel(info, title="System Information", border_style=f"{NordColors.NORD9}")
        )

        # Main menu options
        menu_options = [
            ("1", "Check System Compatibility"),
            ("2", "Install System Dependencies"),
            ("3", "Install User Python Libraries (Rich, etc.)"),
            ("4", "Install pyenv"),
            ("5", "Install Latest Python with pyenv"),
            ("6", "Install pipx and Python Tools"),
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
            install_pip_libraries_for_user()
            pause()
        elif choice == "4":
            install_pyenv()
            pause()
        elif choice == "5":
            install_latest_python_with_pyenv()
            pause()
        elif choice == "6":
            install_pipx_tools()
            pause()
        elif choice == "7":
            run_full_setup()
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            console.print(
                Panel(
                    "Thank you for using the Python Dev Setup Tool.",
                    border_style=f"bold {NordColors.NORD14}",
                )
            )
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

    # Install system dependencies
    print_step("Installing system dependencies...")
    if not install_system_dependencies():
        print_warning("Some system dependencies may not have been installed.")
        if not get_user_confirmation("Continue with the setup process?"):
            print_warning("Setup aborted.")
            return

    # Install user Python libraries like Rich
    print_step("Installing user Python libraries...")
    if not install_pip_libraries_for_user():
        print_warning("Some user Python libraries may not have been installed.")
        if not get_user_confirmation("Continue with the setup process?"):
            print_warning("Setup aborted.")
            return

    # Install pyenv
    print_step("Installing pyenv...")
    if not install_pyenv():
        print_warning("pyenv installation failed.")
        if not get_user_confirmation("Continue without pyenv?"):
            print_warning("Setup aborted.")
            return

    # Install latest Python with pyenv
    print_step("Installing latest Python version with pyenv...")
    if not install_latest_python_with_pyenv():
        print_warning("Python installation with pyenv failed.")
        if not get_user_confirmation("Continue without latest Python?"):
            print_warning("Setup aborted.")
            return

    # Install pipx and Python tools
    print_step("Installing pipx and Python tools...")
    if not install_pipx_tools():
        print_warning("Some Python tools may not have been installed.")

    # Final summary
    print_section("Setup Summary")
    summary = Table(title="Installation Results", box=box.ROUNDED)
    summary.add_column("Component", style=f"bold {NordColors.NORD9}")
    summary.add_column("Status", style=f"{NordColors.NORD4}")

    summary.add_row(
        "System Dependencies",
        "[bold green]✓ Installed[/]"
        if check_command_available("gcc")
        else "[bold red]× Failed[/]",
    )

    summary.add_row(
        "User Python Libraries",
        "[bold green]✓ Installed[/]"
        if os.path.exists(
            os.path.join(HOME_DIR, ".local/lib/python*/site-packages/rich")
        )
        else "[bold yellow]⚠ Partial[/]",
    )

    summary.add_row(
        "pyenv",
        "[bold green]✓ Installed[/]"
        if os.path.exists(PYENV_BIN)
        else "[bold red]× Failed[/]",
    )

    python_installed = os.path.exists(os.path.join(PYENV_DIR, "shims", "python"))
    summary.add_row(
        "Python (via pyenv)",
        "[bold green]✓ Installed[/]" if python_installed else "[bold red]× Failed[/]",
    )

    pipx_installed = check_command_available("pipx") or os.path.exists(
        os.path.join(HOME_DIR, ".local/bin/pipx")
    )
    summary.add_row(
        "pipx",
        "[bold green]✓ Installed[/]" if pipx_installed else "[bold red]× Failed[/]",
    )

    console.print(summary)

    # Shell reloading instructions
    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
    console.print(
        Panel(
            f"To fully apply all changes, {ORIGINAL_USER} should restart their terminal or run:\n\nsource ~/.{shell_name}rc",
            title="Next Steps",
            border_style=f"bold {NordColors.NORD13}",
        )
    )

    print_success("Setup process completed!")


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal_handler)

        # Check if running as root
        if os.geteuid() != 0:
            console.print(
                Panel(
                    "This script must be run with root privileges.\n"
                    "Please run it with sudo.",
                    title="⚠️ Error",
                    border_style=f"bold {NordColors.NORD11}",
                )
            )
            sys.exit(1)

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
