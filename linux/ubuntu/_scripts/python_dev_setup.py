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

  Interactive options during execution:
  - Choose components to install
  - Select Python version (latest stable or specific version)
  - Customize the development tools to install

Version: 2.1.0
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable, Set

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
    from rich.prompt import Prompt, Confirm
    from rich.live import Live
    from rich.columns import Columns
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
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.1.0"
APP_NAME = "PyDev Setup"
APP_SUBTITLE = "Development Environment Installer"

# Extra long timeouts for slow machines (in seconds)
DEFAULT_TIMEOUT = 3600  # 1 hour for most operations
PYTHON_BUILD_TIMEOUT = 7200  # 2 hours for Python compilation

# Determine the original (non-root) user when using sudo
ORIGINAL_USER = os.environ.get("SUDO_USER", getpass.getuser())
try:
    ORIGINAL_UID = int(
        subprocess.check_output(["id", "-u", ORIGINAL_USER]).decode().strip()
    )
    ORIGINAL_GID = int(
        subprocess.check_output(["id", "-g", ORIGINAL_USER]).decode().strip()
    )
except Exception:
    ORIGINAL_UID = os.getuid()
    ORIGINAL_GID = os.getgid()

# Determine home directory of the original user
if ORIGINAL_USER != "root":
    try:
        HOME_DIR = (
            subprocess.check_output(["getent", "passwd", ORIGINAL_USER])
            .decode()
            .split(":")[5]
        )
    except Exception:
        HOME_DIR = os.path.expanduser("~" + ORIGINAL_USER)
else:
    HOME_DIR = os.path.expanduser("~")

# Paths and configurations
PYENV_DIR = os.path.join(HOME_DIR, ".pyenv")
PYENV_BIN = os.path.join(PYENV_DIR, "bin", "pyenv")

# Lists of packages to install
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
    "poetry",
    "httpie",
]


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class SetupComponent:
    """
    Represents a component to be installed as part of the setup process.

    Attributes:
        name: The name of the component
        description: A short description of what the component does
        installed: Whether the component is already installed
        function: The function to call to install this component
        prerequisite: Optional function that must succeed before this component can be installed
    """

    name: str
    description: str
    installed: bool = False
    function: Callable[[], bool] = None
    prerequisite: Optional[Callable[[], bool]] = None


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
    compact_fonts = ["slant", "small", "standard", "digital", "big"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
             _   _                       _            
 _ __  _   _| |_| |__   ___  _ __     __| | _____   __
| '_ \| | | | __| '_ \ / _ \| '_ \   / _` |/ _ \ \ / /
| |_) | |_| | |_| | | | (_) | | | | | (_| |  __/\ V / 
| .__/ \__, |\__|_| |_|\___/|_| |_|  \__,_|\___| \_/  
|_|    |___/                                          
 ___  ___| |_ _   _ _ __                              
/ __|/ _ \ __| | | | '_ \                             
\__ \  __/ |_| |_| | |_) |                            
|___/\___|\__|\__,_| .__/                             
                   |_|                                
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
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

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
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
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
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
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd,
    shell=False,
    check=True,
    capture_output=True,
    timeout=DEFAULT_TIMEOUT,
    as_user=False,
    env=None,
):
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        shell: Whether to run as a shell command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        as_user: Whether to run as the original user
        env: Environment variables for the command

    Returns:
        CompletedProcess instance with command results
    """
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


def fix_ownership(path, recursive=True):
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


def check_command_available(command):
    """Return True if the command is available in the PATH."""
    return shutil.which(command) is not None


# ----------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------
def check_system():
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


def install_system_dependencies():
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


def install_pyenv():
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


def install_latest_python_with_pyenv():
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

        # Sort versions to get the latest
        latest_version = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])[
            -1
        ]

        # Create a selection of recent Python versions for the user to choose from
        recent_versions = sorted(
            versions, key=lambda v: [int(i) for i in v.split(".")]
        )[-5:]

        version_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            border_style=NordColors.FROST_3,
            title=f"[bold {NordColors.FROST_2}]Available Python Versions[/]",
            title_justify="center",
        )
        version_table.add_column(
            "#", style=f"bold {NordColors.FROST_4}", justify="right", width=4
        )
        version_table.add_column("Version", style=NordColors.SNOW_STORM_1)
        version_table.add_column("Status", style=f"bold {NordColors.FROST_2}")

        for i, version in enumerate(recent_versions, 1):
            status = "Latest" if version == latest_version else ""
            version_table.add_row(str(i), version, status)

        console.print(version_table)

        # Let user select a version
        selection = Prompt.ask(
            f"[bold {NordColors.FROST_2}]Select a Python version to install (1-{len(recent_versions)}, default: latest)[/]",
            default="1",
        )

        try:
            index = int(selection) - 1
            if 0 <= index < len(recent_versions):
                selected_version = recent_versions[index]
            else:
                print_warning(
                    f"Invalid selection. Installing latest version {latest_version}."
                )
                selected_version = latest_version
        except ValueError:
            print_warning(
                f"Invalid selection. Installing latest version {latest_version}."
            )
            selected_version = latest_version

        display_panel(
            f"Installing Python {selected_version}.\nThis process may take a long time (20-60 minutes) depending on your system.",
            style=NordColors.FROST_3,
            title="Python Installation",
        )

        # Install Python with extended timeout for slow machines
        install_cmd = pyenv_cmd + ["install", "--skip-existing", selected_version]
        with console.status(
            f"[bold blue]Building Python {selected_version} (this will take a while)...",
            spinner="dots",
        ):
            run_command(
                install_cmd,
                as_user=(ORIGINAL_USER != "root"),
                timeout=PYTHON_BUILD_TIMEOUT,
            )

        print_step("Setting as global Python version...")
        run_command(
            pyenv_cmd + ["global", selected_version], as_user=(ORIGINAL_USER != "root")
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


def install_pipx():
    """Ensure pipx is installed for the target user."""
    if check_command_available("pipx"):
        print_success("pipx is already installed.")
        return True

    try:
        with console.status("[bold blue]Installing pipx...", spinner="dots"):
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
        if os.path.exists(pipx_path) or check_command_available("pipx"):
            print_success("pipx installed successfully.")
            return True
        else:
            print_error("pipx installation could not be verified.")
            return False
    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools():
    """Install essential Python tools via pipx."""
    if not check_command_available("pipx"):
        print_step("Installing pipx via apt-get...")
        try:
            run_command(["apt-get", "install", "-y", "pipx"])
        except Exception as e:
            print_warning(f"Could not install pipx via apt: {e}")
            if not install_pipx():
                print_error("Failed to ensure pipx installation.")
                return False

    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        print_error("Could not find pipx executable.")
        return False

    # Let the user select tools to install
    tools_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Python Development Tools[/]",
        title_justify="center",
    )
    tools_table.add_column(
        "#", style=f"bold {NordColors.FROST_4}", justify="right", width=4
    )
    tools_table.add_column("Tool", style=f"bold {NordColors.FROST_2}")
    tools_table.add_column("Description", style=NordColors.SNOW_STORM_1)

    tools_info = {
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
    }

    for i, tool in enumerate(PIPX_TOOLS, 1):
        description = tools_info.get(tool, "")
        tools_table.add_row(str(i), tool, description)

    console.print(tools_table)

    # Ask user to select tools
    install_all = Confirm.ask(
        f"[bold {NordColors.FROST_2}]Install all tools?[/]", default=True
    )

    selected_tools = PIPX_TOOLS.copy()
    if not install_all:
        selection = Prompt.ask(
            f"[bold {NordColors.FROST_2}]Enter numbers of tools to install (comma-separated, or 'all')[/]",
            default="all",
        )

        if selection.lower() != "all":
            try:
                indices = [int(idx.strip()) - 1 for idx in selection.split(",")]
                selected_tools = [
                    PIPX_TOOLS[idx] for idx in indices if 0 <= idx < len(PIPX_TOOLS)
                ]
                if not selected_tools:
                    print_warning("No valid tools selected. Installing all tools.")
                    selected_tools = PIPX_TOOLS.copy()
            except ValueError:
                print_warning("Invalid selection. Installing all tools.")

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
        tools_task = progress.add_task("Installing", total=len(selected_tools))

        failed_tools = []
        for tool in selected_tools:
            try:
                # Try installing with apt first
                apt_pkg = f"python3-{tool.lower()}"
                try:
                    apt_check = run_command(["apt-cache", "show", apt_pkg], check=False)
                    if apt_check.returncode == 0:
                        run_command(["apt-get", "install", "-y", apt_pkg])
                        progress.advance(tools_task)
                        continue
                except Exception:
                    pass

                # Fall back to pipx
                run_command(
                    [pipx_cmd, "install", tool, "--force"], timeout=DEFAULT_TIMEOUT
                )
                progress.advance(tools_task)
            except Exception as e:
                print_warning(f"Failed to install {tool}: {e}")
                failed_tools.append(tool)
                progress.advance(tools_task)

    if failed_tools:
        print_warning(
            f"Failed to install the following tools: {', '.join(failed_tools)}"
        )
        return len(failed_tools) < len(selected_tools) / 2

    print_success("Python tools installation completed.")
    return True


# ----------------------------------------------------------------
# Interactive Menu
# ----------------------------------------------------------------
def show_interactive_menu():
    """Display an interactive menu for component selection."""
    components = [
        SetupComponent(
            name="System Dependencies",
            description="Essential libraries and build tools",
            function=install_system_dependencies,
        ),
        SetupComponent(
            name="pyenv",
            description="Python version manager",
            function=install_pyenv,
            prerequisite=lambda: check_command_available("git"),
        ),
        SetupComponent(
            name="Latest Python",
            description="Install latest Python version via pyenv",
            function=install_latest_python_with_pyenv,
            prerequisite=lambda: os.path.exists(PYENV_BIN),
        ),
        SetupComponent(
            name="pipx",
            description="Tool for installing Python apps in isolated environments",
            function=install_pipx,
        ),
        SetupComponent(
            name="Python Tools",
            description="Essential development tools (black, pytest, etc.)",
            function=install_pipx_tools,
            prerequisite=lambda: check_command_available("pipx"),
        ),
    ]

    # Check which components are already installed
    for comp in components:
        if comp.name == "System Dependencies":
            comp.installed = all(
                check_command_available(c) for c in ["gcc", "git", "curl"]
            )
        elif comp.name == "pyenv":
            comp.installed = os.path.exists(PYENV_BIN)
        elif comp.name == "Latest Python":
            comp.installed = os.path.exists(os.path.join(PYENV_DIR, "shims", "python"))
        elif comp.name == "pipx":
            comp.installed = check_command_available("pipx")
        elif comp.name == "Python Tools":
            # Check if at least some tools are installed
            sample_tools = ["black", "pytest", "ipython"]
            comp.installed = any(check_command_available(t) for t in sample_tools)

    # Create component selection table
    components_table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.FROST_3,
        title=f"[bold {NordColors.FROST_2}]Setup Components[/]",
        title_justify="center",
    )
    components_table.add_column(
        "#", style=f"bold {NordColors.FROST_4}", justify="right", width=4
    )
    components_table.add_column("Component", style=f"bold {NordColors.FROST_2}")
    components_table.add_column("Description", style=NordColors.SNOW_STORM_1)
    components_table.add_column("Status", style=f"bold {NordColors.GREEN}")

    for i, comp in enumerate(components, 1):
        status = "✓ Installed" if comp.installed else ""
        components_table.add_row(str(i), comp.name, comp.description, status)

    console.print(components_table)

    # Ask which components to install
    install_all = Confirm.ask(
        f"[bold {NordColors.FROST_2}]Install all components?[/]", default=True
    )

    if install_all:
        selected_indices = list(range(len(components)))
    else:
        selection = Prompt.ask(
            f"[bold {NordColors.FROST_2}]Enter numbers of components to install (comma-separated, or 'all')[/]",
            default="all",
        )

        if selection.lower() == "all":
            selected_indices = list(range(len(components)))
        else:
            try:
                selected_indices = [
                    int(idx.strip()) - 1 for idx in selection.split(",")
                ]
                selected_indices = [
                    idx for idx in selected_indices if 0 <= idx < len(components)
                ]
                if not selected_indices:
                    print_warning(
                        "No valid components selected. Installing all components."
                    )
                    selected_indices = list(range(len(components)))
            except ValueError:
                print_warning("Invalid selection. Installing all components.")
                selected_indices = list(range(len(components)))

    # Install selected components
    successes = []
    for idx in selected_indices:
        comp = components[idx]

        # Skip already installed components unless explicitly selected
        if comp.installed and install_all:
            print_success(f"{comp.name} is already installed. Skipping.")
            successes.append(comp.name)
            continue

        # Check prerequisite
        if comp.prerequisite and not comp.prerequisite():
            print_warning(f"Prerequisite for {comp.name} not met. Skipping.")
            continue

        print_step(f"Installing {comp.name}...")
        try:
            if comp.function():
                print_success(f"{comp.name} installed successfully.")
                successes.append(comp.name)
            else:
                print_error(f"Failed to install {comp.name}.")
        except Exception as e:
            print_error(f"Error installing {comp.name}: {e}")

    return successes


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
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Setup Process
# ----------------------------------------------------------------
def run_full_setup():
    """Run the full setup process with interactive menus."""
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

    if not check_system():
        print_error("System check failed. Aborting setup.")
        sys.exit(1)

    # Start interactive component selection
    display_panel(
        "Welcome to Python Development Environment Setup!\n\n"
        "This tool will help you set up a complete Python development environment "
        "including essential build tools, pyenv for Python version management, "
        "and development tools.",
        style=NordColors.FROST_3,
        title="Welcome",
    )

    # Show interactive menu and get installed components
    successes = show_interactive_menu()

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

    sys_deps_status = "✓ Installed" if check_command_available("gcc") else "× Failed"
    pyenv_status = "✓ Installed" if os.path.exists(PYENV_BIN) else "× Failed"
    python_installed = os.path.exists(os.path.join(PYENV_DIR, "shims", "python"))
    python_status = "✓ Installed" if python_installed else "× Failed"
    pipx_installed = check_command_available("pipx") or os.path.exists(
        os.path.join(HOME_DIR, ".local/bin/pipx")
    )
    pipx_status = "✓ Installed" if pipx_installed else "× Failed"
    tools_status = (
        "✓ Some tools installed" if "Python Tools" in successes else "× Not installed"
    )

    table.add_row("System Dependencies", sys_deps_status)
    table.add_row("pyenv", pyenv_status)
    table.add_row("Python (via pyenv)", python_status)
    table.add_row("pipx", pipx_status)
    table.add_row("Python Development Tools", tools_status)

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
# Main Entry Point
# ----------------------------------------------------------------
def main():
    """Main application entry point with error handling."""
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: sys.exit(128 + signum))

        if os.geteuid() != 0:
            print_error(
                "This script must be run with root privileges. Please run with sudo."
            )
            sys.exit(1)

        run_full_setup()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
