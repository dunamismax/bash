#!/usr/bin/env python3
"""
Python Development Environment Setup
--------------------------------------------------

A comprehensive tool for automatically setting up a complete Python development
environment with Nord-themed visual interface. This script handles installation of:

- System dependencies for Python development
- pyenv for Python version management
- Latest Python version via pyenv
- pipx for isolated tool installation
- Essential development tools and utilities

Usage:
  Run with sudo: sudo python3 setup.py

Version: 2.3.0
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
from typing import List, Dict, Optional, Any, Union

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing them now...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"], check=True
        )
        print("Successfully installed required libraries. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Failed to install required libraries: {e}")
        print("Please install them manually: pip install rich pyfiglet")
        sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION: str = "2.3.0"
APP_NAME: str = "PyDev Setup"
APP_SUBTITLE: str = "Development Environment Installer"

# Timeouts for operations (in seconds)
DEFAULT_TIMEOUT: int = 3600  # 1 hour for most operations
PYTHON_BUILD_TIMEOUT: int = 7200  # 2 hours for Python compilation

# Determine the original (non-root) user when using sudo
ORIGINAL_USER: str = os.environ.get("SUDO_USER", getpass.getuser())
try:
    ORIGINAL_UID: int = int(
        subprocess.check_output(["id", "-u", ORIGINAL_USER]).decode().strip()
    )
    ORIGINAL_GID: int = int(
        subprocess.check_output(["id", "-g", ORIGINAL_USER]).decode().strip()
    )
except Exception:
    ORIGINAL_UID: int = os.getuid()
    ORIGINAL_GID: int = os.getgid()

# Determine home directory of the original user
if ORIGINAL_USER != "root":
    try:
        HOME_DIR: str = (
            subprocess.check_output(["getent", "passwd", ORIGINAL_USER])
            .decode()
            .split(":")[5]
        )
    except Exception:
        HOME_DIR: str = os.path.expanduser("~" + ORIGINAL_USER)
else:
    HOME_DIR: str = os.path.expanduser("~")

# Paths and configurations
PYENV_DIR: str = os.path.join(HOME_DIR, ".pyenv")
PYENV_BIN: str = os.path.join(PYENV_DIR, "bin", "pyenv")


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1: str = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4: str = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1: str = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2: str = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1: str = "#8FBCBB"  # Light cyan
    FROST_2: str = "#88C0D0"  # Light blue
    FROST_3: str = "#81A1C1"  # Medium blue
    FROST_4: str = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED: str = "#BF616A"  # Red
    ORANGE: str = "#D08770"  # Orange
    YELLOW: str = "#EBCB8B"  # Yellow
    GREEN: str = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


SYSTEM_DEPENDENCIES: List[str] = [
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
    "python3-rich",
    "python3-pyfiglet",
]

PIPX_TOOLS: List[str] = [
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
    "poetry",
    "httpie",
    "ruff",
    "yt-dlp",
    "bandit",
    "pipenv",
    "pip-audit",
    "nox",
    "awscli",
    "dvc",
    "uv",
    "thefuck",
    "pyupgrade",
    "watchfiles",
    "bump2version",
]

# Tool descriptions for display
TOOL_DESCRIPTIONS: Dict[str, str] = {
    "black": "Code formatter that adheres to PEP 8",
    "isort": "Import statement organizer",
    "flake8": "Style guide enforcement tool",
    "mypy": "Static type checker",
    "pytest": "Testing framework",
    "pre-commit": "Git hook manager",
    "ipython": "Enhanced interactive Python shell",
    "cookiecutter": "Project template renderer",
    "pylint": "Code analysis tool",
    "sphinx": "Documentation generator",
    "twine": "Package upload utility",
    "poetry": "Dependency management and packaging",
    "httpie": "Command-line HTTP client",
    "ruff": "Fast Python linter",
    "yt-dlp": "Advanced video downloader with support for many sites",
    "bandit": "Security linter for detecting vulnerabilities in Python code",
    "pipenv": "Dependency management and virtual environment tool",
    "pip-audit": "Scans Python environments for vulnerable dependencies",
    "nox": "Automation tool for running tests in multiple Python environments",
    "awscli": "Official AWS command-line interface",
    "dvc": "Data version control tool for ML and data projects",
    "uv": "An extremely fast and unified Python package manager written in Rust, replacing pip, pip-tools, pipx, and more",
    "thefuck": "Corrects mistyped commands in your shell",
    "pyupgrade": "Automatically upgrades your Python code to newer syntax",
    "watchfiles": "Monitors file changes and can trigger actions",
    "bump2version": "Automates version bumping for your projects",
}


# Tool descriptions for display
TOOL_DESCRIPTIONS: Dict[str, str] = {
    "black": "Code formatter that adheres to PEP 8",
    "isort": "Import statement organizer",
    "flake8": "Style guide enforcement tool",
    "mypy": "Static type checker",
    "pytest": "Testing framework",
    "pre-commit": "Git hook manager",
    "ipython": "Enhanced interactive Python shell",
    "cookiecutter": "Project template renderer",
    "pylint": "Code analysis tool",
    "sphinx": "Documentation generator",
    "twine": "Package upload utility",
    "poetry": "Dependency management and packaging",
    "httpie": "Command-line HTTP client",
    "ruff": "Fast Python linter",
    "yt-dlp": "Advanced video downloader with support for various websites",
    "ffmpeg": "Comprehensive multimedia framework for processing audio and video",
    "bandit": "Security linter for detecting vulnerabilities in Python code",
    "pipenv": "Dependency management and virtual environment tool",
    "pip-audit": "Utility to scan for vulnerabilities in Python packages",
    "nox": "Automation tool for running tests in multiple Python environments",
    "jupyter": "Interactive computing environment for notebooks",
    "awscli": "Official AWS command-line interface",
    "dvc": "Data version control tool for managing data and ML pipelines",
}


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a styled ASCII art header for the application.

    Returns:
        Panel containing the styled header
    """
    try:
        # Try to create ASCII art with pyfiglet
        fig = pyfiglet.Figlet(font="slant", width=60)
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        # Fallback ASCII art if pyfiglet fails
        ascii_art = """
             _   _                                   
 _ __  _   _| |_| |__   ___  _ __     ___ _ ____   __
| '_ \| | | | __| '_ \ / _ \| '_ \   / _ \ '_ \ \ / /
| |_) | |_| | |_| | | | (_) | | | | |  __/ | | \ V / 
| .__/ \__, |\__|_| |_|\___/|_| |_|  \___|_| |_|\_/  
|_|    |___/                                         
 ___  ___| |_ _   _ _ __                             
/ __|/ _ \ __| | | | '_ \                            
\__ \  __/ |_| |_| | |_) |                           
|___/\___|\__|\__,_| .__/                            
                   |_|                               
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Apply styling with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative border
    border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = border + "\n" + styled_text + border

    # Create a panel
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message in a styled panel."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: Union[List[str], str],
    shell: bool = False,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    as_user: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Execute a system command and return the result."""
    if (
        as_user
        and ORIGINAL_USER != "root"
        and not (isinstance(cmd, list) and cmd and cmd[0] == "sudo")
    ):
        cmd = ["sudo", "-u", ORIGINAL_USER] + (cmd if isinstance(cmd, list) else [cmd])

    try:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        if not shell:
            print_message(
                f"Running: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}",
                NordColors.SNOW_STORM_1,
                "→",
            )

        result = subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            env=env or os.environ.copy(),
        )
        return result
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        print_error(f"Command failed: {cmd_str}")
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def fix_ownership(path: str, recursive: bool = True) -> None:
    """Fix ownership of a given path to the original (non-root) user."""
    if ORIGINAL_USER == "root":
        return

    try:
        if recursive and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    os.chown(os.path.join(root, d), ORIGINAL_UID, ORIGINAL_GID)
                for f in files:
                    os.chown(os.path.join(root, f), ORIGINAL_UID, ORIGINAL_GID)
        if os.path.exists(path):
            os.chown(path, ORIGINAL_UID, ORIGINAL_GID)
    except Exception as e:
        print_warning(f"Failed to fix ownership of {path}: {e}")


def check_command_available(command: str) -> bool:
    """Return True if the command is available in the PATH."""
    return shutil.which(command) is not None


# ----------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------
def check_system() -> bool:
    """Check system compatibility and basic required tools."""
    with console.status("[bold blue]Checking system compatibility...", spinner="dots"):
        if os.geteuid() != 0:
            print_error("This script must be run with root privileges (sudo).")
            return False

        os_name = platform.system().lower()
        if os_name != "linux":
            print_warning(f"This script is designed for Linux, not {os_name}.")

        # Create a system info table
        table = Table(
            show_header=False,
            box=None,
            border_style=NordColors.FROST_3,
            padding=(0, 2),
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)

        table.add_row("Python Version", platform.python_version())
        table.add_row("Operating System", platform.platform())
        table.add_row("Running as", "root")
        table.add_row("Setting up for user", ORIGINAL_USER)
        table.add_row("User home directory", HOME_DIR)

        console.print(
            Panel(
                table,
                title="[bold]System Information[/bold]",
                border_style=NordColors.FROST_1,
                padding=(1, 2),
            )
        )

        required_tools = ["git", "curl", "gcc"]
        missing = [tool for tool in required_tools if not check_command_available(tool)]
        if missing:
            print_warning(
                f"Missing required tools: {', '.join(missing)}. They will be installed."
            )
        else:
            print_success("All basic required tools are present.")

        print_success("System check completed.")
        return True


def install_system_dependencies() -> bool:
    """Install required system packages using apt-get."""
    try:
        with console.status("[bold blue]Updating package lists...", spinner="dots"):
            run_command(["apt-get", "update"])
            print_success("Package lists updated.")

        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing system packages"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            install_task = progress.add_task(
                "Installing", total=len(SYSTEM_DEPENDENCIES)
            )

            for package in SYSTEM_DEPENDENCIES:
                try:
                    run_command(["apt-get", "install", "-y", package], check=False)
                    progress.advance(install_task)
                except Exception as e:
                    print_warning(f"Error installing {package}: {e}")

        print_success("System dependencies installed successfully.")
        return True
    except Exception as e:
        print_error(f"Failed to install system dependencies: {e}")
        return False


def install_pyenv() -> bool:
    """Install pyenv for managing Python versions."""
    if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
        print_success("pyenv is already installed.")
        return True

    try:
        with console.status(
            "[bold blue]Downloading pyenv installer...", spinner="dots"
        ):
            installer_script = "/tmp/pyenv_installer.sh"
            run_command(["curl", "-fsSL", "https://pyenv.run", "-o", installer_script])
            os.chmod(installer_script, 0o755)

        print_step("Running pyenv installer...")
        if ORIGINAL_USER != "root":
            run_command(["sudo", "-u", ORIGINAL_USER, installer_script], as_user=True)
        else:
            run_command([installer_script])

        if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
            print_success("pyenv installed successfully.")

            with console.status(
                "[bold blue]Setting up shell configuration for pyenv...", spinner="dots"
            ):
                shell_rc_files = [
                    os.path.join(HOME_DIR, ".bashrc"),
                    os.path.join(HOME_DIR, ".zshrc"),
                ]
                pyenv_init_lines = [
                    "\n# pyenv initialization",
                    'export PYENV_ROOT="$HOME/.pyenv"',
                    'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"',
                    'eval "$(pyenv init -)"',
                    'eval "$(pyenv virtualenv-init -)"',
                    "",
                ]

                for rc_file in shell_rc_files:
                    if os.path.exists(rc_file):
                        with open(rc_file, "r") as f:
                            content = f.read()
                        if "pyenv init" not in content:
                            if ORIGINAL_USER != "root":
                                temp_file = "/tmp/pyenv_init.txt"
                                with open(temp_file, "w") as f:
                                    f.write("\n".join(pyenv_init_lines))
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
                                    f.write("\n".join(pyenv_init_lines))
                            print_success(f"Added pyenv initialization to {rc_file}")

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
    if not os.path.exists(PYENV_BIN):
        print_error("pyenv is not installed. Please install it first.")
        return False

    try:
        pyenv_cmd = [PYENV_BIN]
        if ORIGINAL_USER != "root":
            pyenv_cmd = ["sudo", "-u", ORIGINAL_USER, PYENV_BIN]

        with console.status("[bold blue]Updating pyenv repository...", spinner="dots"):
            pyenv_root = os.path.dirname(os.path.dirname(PYENV_BIN))
            if os.path.exists(os.path.join(pyenv_root, ".git")):
                if ORIGINAL_USER != "root":
                    run_command(
                        ["sudo", "-u", ORIGINAL_USER, "git", "-C", pyenv_root, "pull"],
                        as_user=True,
                    )
                else:
                    run_command(["git", "-C", pyenv_root, "pull"])
            else:
                print_warning("pyenv repository not a git repository. Skipping update.")

        print_step("Finding available Python versions...")
        latest_version_output = run_command(
            pyenv_cmd + ["install", "--list"], as_user=(ORIGINAL_USER != "root")
        ).stdout
        versions = re.findall(
            r"^\s*(\d+\.\d+\.\d+)$", latest_version_output, re.MULTILINE
        )
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False

        # Sort versions to get the latest (properly sorting by version components)
        sorted_versions = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])
        latest_version = sorted_versions[-1]

        # Display information about the selected version
        print_success(f"Found latest Python version: {latest_version}")

        display_panel(
            f"Installing Python {latest_version}.\nThis process may take a long time (20-60 minutes) depending on your system.",
            style=NordColors.FROST_3,
            title="Python Installation",
        )

        # Install Python with extended timeout for slow machines
        install_cmd = pyenv_cmd + ["install", "--skip-existing", latest_version]
        with console.status(
            f"[bold blue]Building Python {latest_version} (this will take a while)...",
            spinner="dots",
        ):
            run_command(
                install_cmd,
                as_user=(ORIGINAL_USER != "root"),
                timeout=PYTHON_BUILD_TIMEOUT,
            )

        print_step(f"Setting Python {latest_version} as global default...")
        run_command(
            pyenv_cmd + ["global", latest_version], as_user=(ORIGINAL_USER != "root")
        )

        pyenv_python = os.path.join(PYENV_DIR, "shims", "python")
        if os.path.exists(pyenv_python):
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
    """Ensure pipx is installed for the target user."""
    if check_command_available("pipx"):
        print_success("pipx is already installed.")
        return True

    try:
        with console.status("[bold blue]Installing pipx...", spinner="dots"):
            # First try to install via apt
            try:
                run_command(["apt-get", "install", "-y", "pipx"], check=False)
                if check_command_available("pipx"):
                    print_success("pipx installed via apt.")
                    return True
            except Exception:
                print_warning("Failed to install pipx via apt, trying pip...")

            # If apt fails, use pip
            if ORIGINAL_USER != "root":
                python_cmd = os.path.join(PYENV_DIR, "shims", "python")
                if not os.path.exists(python_cmd):
                    python_cmd = "python3"
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
                    [
                        "sudo",
                        "-u",
                        ORIGINAL_USER,
                        python_cmd,
                        "-m",
                        "pipx",
                        "ensurepath",
                    ],
                    as_user=True,
                )
            else:
                python_cmd = os.path.join(PYENV_DIR, "shims", "python")
                if not os.path.exists(python_cmd):
                    python_cmd = shutil.which("python3") or shutil.which("python")
                if not python_cmd:
                    print_error("Could not find a Python executable.")
                    return False
                run_command([python_cmd, "-m", "pip", "install", "pipx"])
                run_command([python_cmd, "-m", "pipx", "ensurepath"])

        user_bin_dir = os.path.join(HOME_DIR, ".local", "bin")
        pipx_path = os.path.join(user_bin_dir, "pipx")

        # Make sure pipx is in PATH
        if ORIGINAL_USER != "root":
            new_path = f"{user_bin_dir}:$PATH"
            run_command(
                [
                    "sudo",
                    "-u",
                    ORIGINAL_USER,
                    "bash",
                    "-c",
                    f'export PATH="{new_path}" && pipx --version',
                ],
                as_user=True,
                check=False,
            )

        if os.path.exists(pipx_path) or check_command_available("pipx"):
            print_success("pipx installed successfully.")
            return True
        else:
            # It might be installed but not in PATH yet
            print_warning(
                "pipx installation completed but may not be in PATH until shell is restarted."
            )
            return True
    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools() -> bool:
    """Install essential Python tools via pipx."""
    # Locate pipx executable
    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        user_bin_dir = os.path.join(HOME_DIR, ".local", "bin")
        pipx_path = os.path.join(user_bin_dir, "pipx")
        if os.path.exists(pipx_path):
            pipx_cmd = pipx_path
        else:
            print_error("Could not find pipx executable.")
            return False

    # Display tools to be installed
    display_panel(
        f"Installing {len(PIPX_TOOLS)} Python development tools automatically.",
        style=NordColors.FROST_3,
        title="Development Tools",
    )

    # Set up environment with pipx in PATH
    env = os.environ.copy()
    if ORIGINAL_USER != "root":
        user_bin_dir = os.path.join(HOME_DIR, ".local", "bin")
        env["PATH"] = f"{user_bin_dir}:{env.get('PATH', '')}"

    # Install tools with progress bar
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Installing Python tools"),
        BarColumn(
            bar_width=40, style=NordColors.FROST_4, complete_style=NordColors.FROST_2
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        tools_task = progress.add_task("Installing", total=len(PIPX_TOOLS))

        installed_tools = []
        failed_tools = []

        for tool in PIPX_TOOLS:
            try:
                if ORIGINAL_USER != "root":
                    # For non-root users, run pipx as the user
                    result = run_command(
                        [
                            "sudo",
                            "-u",
                            ORIGINAL_USER,
                            pipx_cmd,
                            "install",
                            tool,
                            "--force",
                        ],
                        as_user=True,
                        check=False,
                        env=env,
                    )
                else:
                    # For root user, run pipx directly
                    result = run_command(
                        [pipx_cmd, "install", tool, "--force"], check=False, env=env
                    )

                if result.returncode == 0:
                    installed_tools.append(tool)
                else:
                    failed_tools.append(tool)
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)
            finally:
                progress.advance(tools_task)

    # Report results
    if installed_tools:
        print_success(f"Successfully installed {len(installed_tools)} tools")

    if failed_tools:
        print_warning(
            f"Failed to install {len(failed_tools)} tools: {', '.join(failed_tools)}"
        )

    # Create a table of installed tools
    tools_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Installed Python Tools[/]",
        title_justify="center",
    )
    tools_table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
    tools_table.add_column("Status", style=NordColors.SNOW_STORM_1)
    tools_table.add_column("Description", style=NordColors.SNOW_STORM_1)

    for tool in PIPX_TOOLS:
        status = (
            "[green]✓ Installed[/]" if tool in installed_tools else "[red]× Failed[/]"
        )
        description = TOOL_DESCRIPTIONS.get(tool, "")
        tools_table.add_row(tool, status, description)

    console.print(tools_table)

    return len(installed_tools) > 0


# ----------------------------------------------------------------
# Main Setup Functions
# ----------------------------------------------------------------
def run_setup_components() -> List[str]:
    """Run all setup components and return list of successful installations."""
    components = [
        ("System Dependencies", install_system_dependencies),
        ("pyenv", install_pyenv),
        ("Latest Python", install_latest_python_with_pyenv),
        ("pipx", install_pipx),
        ("Python Tools", install_pipx_tools),
    ]

    successes = []

    for name, func in components:
        print_step(f"Installing {name}...")
        try:
            if func():
                print_success(f"{name} installed successfully.")
                successes.append(name)
            else:
                print_error(f"Failed to install {name}.")
        except Exception as e:
            print_error(f"Error installing {name}: {e}")

    return successes


def display_summary(successes: List[str]) -> None:
    """Display a summary of installed components."""
    # Create a summary table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title="[bold]Setup Summary[/]",
        title_style=f"bold {NordColors.FROST_2}",
        title_justify="center",
        expand=True,
    )

    table.add_column("Component", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=NordColors.SNOW_STORM_1)

    components = [
        "System Dependencies",
        "pyenv",
        "Latest Python",
        "pipx",
        "Python Tools",
    ]

    for component in components:
        status = (
            "[green]✓ Installed[/]" if component in successes else "[red]× Failed[/]"
        )
        table.add_row(component, status)

    console.print("\n")
    console.print(Panel(table, border_style=NordColors.FROST_1, padding=(1, 2)))

    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))

    console.print("\n[bold]Next Steps:[/bold]")
    console.print(
        f"To fully apply all changes, {ORIGINAL_USER} should restart their terminal or run:"
    )
    console.print(f"[bold {NordColors.FROST_3}]source ~/.{shell_name}rc[/]")

    console.print("\n[bold green]✓ Setup process completed![/bold green]")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle process termination signals gracefully."""
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main application entry point with error handling."""
    try:
        console.print("\n")
        console.print(create_header())

        # Display current datetime and hostname
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hostname = platform.node()
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {hostname}[/]"
            )
        )
        console.print("\n")

        if os.geteuid() != 0:
            print_error(
                "This script must be run with root privileges. Please run with sudo."
            )
            sys.exit(1)

        if not check_system():
            print_error("System check failed. Aborting setup.")
            sys.exit(1)

        # Display welcome message
        display_panel(
            "Welcome to Python Development Environment Setup!\n\n"
            "This automated tool will set up a complete Python development environment "
            "including essential build tools, pyenv for Python version management, "
            "the latest Python version, and development tools.",
            style=NordColors.FROST_3,
            title="Welcome",
        )

        # Run all setup components
        successes = run_setup_components()

        # Display summary
        display_summary(successes)

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
