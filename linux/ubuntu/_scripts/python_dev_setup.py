#!/usr/bin/env python3
"""
Python Development Environment Setup
-----------------------------------

This script automatically sets up a complete Python development environment
by installing required system packages, pyenv, the latest Python version, and
essential development tools.

Features:
  • System dependency installation
  • pyenv installation and configuration
  • Latest Python version installation via pyenv
  • pipx installation and configuration
  • Essential Python tools installation

Run with sudo: sudo python3 setup.py
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
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable

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
    from rich.prompt import Prompt
    from rich.live import Live
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
VERSION = "2.0.0"
APP_NAME = "Python Dev Setup"
APP_SUBTITLE = "Development Environment Installer"

# Extra long timeouts for slow machines (in seconds)
# 1 hour for most operations, 2 hours for Python compilation
DEFAULT_TIMEOUT = 3600
PYTHON_BUILD_TIMEOUT = 7200

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

PYENV_DIR = os.path.join(HOME_DIR, ".pyenv")
PYENV_BIN = os.path.join(PYENV_DIR, "bin", "pyenv")

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
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Try different fonts
    fonts = ["slant", "big", "small", "standard", "digital"]

    # Try each font until we find one that works well
    for font_name in fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    ascii_lines = ascii_art.split("\n")
    for i, line in enumerate(ascii_lines):
        if line.strip():
            color = colors[i % len(colors)]
            styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text.rstrip() + "\n" + tech_border

    # Create a panel with sufficient padding
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

        print_step("Finding latest Python version...")
        latest_version_output = run_command(
            pyenv_cmd + ["install", "--list"], as_user=(ORIGINAL_USER != "root")
        ).stdout
        versions = re.findall(
            r"^\s*(\d+\.\d+\.\d+)$", latest_version_output, re.MULTILINE
        )
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False

        latest_version = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])[
            -1
        ]

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

        print_step("Setting as global Python version...")
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

        failed_tools = []
        for tool in PIPX_TOOLS:
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
        return len(failed_tools) < len(PIPX_TOOLS) / 2

    print_success("Python tools installation completed.")
    return True


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
    console.print("\n")
    console.print(create_header())
    console.print("\n")

    if not check_system():
        print_error("System check failed. Aborting setup.")
        sys.exit(1)

    print_step("Installing system dependencies...")
    if not install_system_dependencies():
        print_warning("Some system dependencies may not have been installed.")

    print_step("Installing pyenv...")
    if not install_pyenv():
        print_warning("pyenv installation failed.")

    print_step("Installing latest Python version with pyenv...")
    if not install_latest_python_with_pyenv():
        print_warning("Python installation with pyenv failed.")

    print_step("Installing pipx and Python tools...")
    if not install_pipx_tools():
        print_warning("Some Python tools may not have been installed.")

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

    table.add_row("System Dependencies", sys_deps_status)
    table.add_row("pyenv", pyenv_status)
    table.add_row("Python (via pyenv)", python_status)
    table.add_row("pipx", pipx_status)

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
