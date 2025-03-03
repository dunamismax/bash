#!/usr/bin/env python3
"""
Unattended Python Development Environment Setup for Ubuntu/Linux
----------------------------------------------------------------

This script automatically sets up a complete Python development environment
by installing required system packages, pyenv, the latest Python version, and
essential development tools.

Features:
  • System dependency installation
  • pyenv installation and configuration
  • Latest Python version installation via pyenv
  • pipx installation and configuration
  • Essential Python tools installation

Run with sudo, no arguments needed.
"""

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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
import pyfiglet

# ----------------------------------------------------------------------
# Global Console & Header Functions
# ----------------------------------------------------------------------
console = Console()

def print_header(text: str) -> None:
    """Display a header using pyfiglet and a rich Panel."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    panel = Panel(ascii_art, style="bold cyan")
    console.print(panel)

def print_step(message: str) -> None:
    """Print a step description."""
    console.print(f"[bold blue]➜ {message}[/bold blue]")

def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓ {message}[/bold green]")

def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠ {message}[/bold yellow]")

def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗ {message}[/bold red]")

# ----------------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------------
VERSION = "1.0.0"

# Determine the original (non-root) user when using sudo
ORIGINAL_USER = os.environ.get("SUDO_USER", getpass.getuser())
try:
    ORIGINAL_UID = int(
        subprocess.check_output(["id", "-u", ORIGINAL_USER]).decode().strip()
    )
    ORIGINAL_GID = int(
        subprocess.check_output(["id", "-g", ORIGINAL_USER]).decode().strip()
    )
except Exception as e:
    print_error("Failed to determine UID/GID for the original user.")
    sys.exit(1)

if ORIGINAL_USER != "root":
    try:
        HOME_DIR = subprocess.check_output(["getent", "passwd", ORIGINAL_USER]).decode().split(":")[5]
    except Exception:
        HOME_DIR = os.path.expanduser("~")
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
    "python3-rich",
    "python3-pyfiglet",
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
    "autopep8",
    "bandit",
    "poetry",
    "pydocstyle",
    "yapf",
    "httpie",
]

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def run_command(cmd, shell=False, check=True, capture_output=True, timeout=30000, as_user=False):
    """
    Run a shell command and handle errors.
    
    If as_user is True, the command is run as the original non-root user.
    """
    if as_user and ORIGINAL_USER != "root" and not (cmd and cmd[0] == "sudo"):
        cmd = ["sudo", "-u", ORIGINAL_USER] + cmd
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
        cmd_str = " ".join(cmd) if not shell else cmd
        print_error(f"Command failed: {cmd_str}")
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold red]Error Output: {e.stderr.strip()}[/bold red]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise

def fix_ownership(path, recursive=True):
    """Fix ownership of a given path to the original (non-root) user."""
    if ORIGINAL_USER == "root":
        return
    if recursive and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for d in dirs:
                os.chown(os.path.join(root, d), ORIGINAL_UID, ORIGINAL_GID)
            for f in files:
                os.chown(os.path.join(root, f), ORIGINAL_UID, ORIGINAL_GID)
    if os.path.exists(path):
        os.chown(path, ORIGINAL_UID, ORIGINAL_GID)

def check_command_available(command):
    """Return True if the command is available in the PATH."""
    return shutil.which(command) is not None

# ----------------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------------
def check_system():
    """Check system compatibility and basic required tools."""
    print_step("Checking system compatibility...")
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges (sudo).")
        sys.exit(1)
    
    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")
    
    console.print(f"Python Version: {platform.python_version()}")
    console.print(f"Operating System: {platform.platform()}")
    console.print(f"Running as: root")
    console.print(f"Setting up for user: {ORIGINAL_USER}")
    console.print(f"User home directory: {HOME_DIR}")
    
    required_tools = ["git", "curl", "gcc"]
    missing = [tool for tool in required_tools if not check_command_available(tool)]
    if missing:
        print_warning(f"Missing required tools: {', '.join(missing)}. They will be installed.")
    else:
        print_success("All basic required tools are present.")
    
    print_success("System check completed.")
    return True

def install_system_dependencies():
    """Install required system packages using apt-get."""
    print_step("Installing system dependencies...")
    try:
        print_step("Updating package lists...")
        run_command(["apt-get", "update"])
        print_success("Package lists updated.")
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False

    for package in SYSTEM_DEPENDENCIES:
        try:
            print_step(f"Installing {package}...")
            run_command(["apt-get", "install", "-y", package])
            print_success(f"{package} installed.")
        except Exception as e:
            print_error(f"Failed to install {package}: {e}")
    
    print_success("System dependencies installed successfully.")
    return True

def install_pyenv():
    """Install pyenv for managing Python versions."""
    print_step("Installing pyenv...")
    if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
        print_success("pyenv is already installed.")
        return True

    try:
        print_step("Downloading pyenv installer...")
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
            print_step("Setting up shell configuration for pyenv...")
            shell_rc_files = [os.path.join(HOME_DIR, ".bashrc"), os.path.join(HOME_DIR, ".zshrc")]
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
                                ["sudo", "-u", ORIGINAL_USER, "bash", "-c", f"cat {temp_file} >> {rc_file}"],
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
    print_step("Installing latest Python with pyenv...")
    if not os.path.exists(PYENV_BIN):
        print_error("pyenv is not installed. Please install it first.")
        return False

    try:
        pyenv_cmd = [PYENV_BIN]
        if ORIGINAL_USER != "root":
            pyenv_cmd = ["sudo", "-u", ORIGINAL_USER, PYENV_BIN]
        
        print_step("Updating pyenv repository...")
        pyenv_root = os.path.dirname(os.path.dirname(PYENV_BIN))
        if os.path.exists(os.path.join(pyenv_root, ".git")):
            if ORIGINAL_USER != "root":
                run_command(["sudo", "-u", ORIGINAL_USER, "git", "-C", pyenv_root, "pull"], as_user=True)
            else:
                run_command(["git", "-C", pyenv_root, "pull"])
        else:
            print_warning("pyenv repository not a git repository. Skipping update.")
        
        print_step("Finding latest Python version...")
        latest_version_output = run_command(pyenv_cmd + ["install", "--list"], as_user=(ORIGINAL_USER != "root")).stdout
        versions = re.findall(r"^\s*(\d+\.\d+\.\d+)$", latest_version_output, re.MULTILINE)
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False
        
        latest_version = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])[-1]
        print_step(f"Installing Python {latest_version} (this may take several minutes)...")
        run_command(pyenv_cmd + ["install", "--skip-existing", latest_version], as_user=(ORIGINAL_USER != "root"))
        
        print_step("Setting as global Python version...")
        run_command(pyenv_cmd + ["global", latest_version], as_user=(ORIGINAL_USER != "root"))
        
        pyenv_python = os.path.join(PYENV_DIR, "shims", "python")
        if os.path.exists(pyenv_python):
            if ORIGINAL_USER != "root":
                python_version = run_command(["sudo", "-u", ORIGINAL_USER, pyenv_python, "--version"], as_user=True).stdout
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
    print_step("Installing pipx...")
    if check_command_available("pipx"):
        print_success("pipx is already installed.")
        return True

    try:
        if ORIGINAL_USER != "root":
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = "python3"
            print_step(f"Installing pipx for user {ORIGINAL_USER}...")
            run_command(
                ["sudo", "-u", ORIGINAL_USER, python_cmd, "-m", "pip", "install", "--user", "pipx"],
                as_user=True,
            )
            run_command(
                ["sudo", "-u", ORIGINAL_USER, python_cmd, "-m", "pipx", "ensurepath"],
                as_user=True,
            )
        else:
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = shutil.which("python3") or shutil.which("python")
            if not python_cmd:
                print_error("Could not find a Python executable.")
                return False
            print_step("Installing pipx...")
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
    """Install essential Python tools via pipx (or via apt if available)."""
    print_step("Installing Python tools via pipx...")
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

    failed_tools = []
    for tool in PIPX_TOOLS:
        try:
            print_step(f"Installing {tool}...")
            apt_pkg = f"python3-{tool.lower()}"
            try:
                apt_check = run_command(["apt-cache", "show", apt_pkg], check=False)
                if apt_check.returncode == 0:
                    run_command(["apt-get", "install", "-y", apt_pkg])
                    print_success(f"Installed {tool} via apt.")
                    continue
            except Exception:
                pass
            run_command([pipx_cmd, "install", tool, "--force"])
            print_success(f"Installed {tool} via pipx.")
        except Exception as e:
            print_warning(f"Failed to install {tool}: {e}")
            failed_tools.append(tool)

    if failed_tools:
        print_warning(f"Failed to install the following tools: {', '.join(failed_tools)}")
        if len(failed_tools) < len(PIPX_TOOLS) / 2:
            return True
        return False

    print_success("Python tools installation completed.")
    return True

def install_rich_and_pyfiglet():
    """Install rich and pyfiglet using pip as the non-root user."""
    print_step("Installing rich and pyfiglet...")
    base_cmd = ["sudo", "-H", "-u", ORIGINAL_USER, "python3", "-m", "pip", "install", "--break-system-packages"]
    try:
        run_command(base_cmd + ["rich"], as_user=False)
        print_success("rich installed successfully.")
    except Exception as e:
        print_warning(f"Failed to install rich: {e}")
    try:
        run_command(base_cmd + ["pyfiglet"], as_user=False)
        print_success("pyfiglet installed successfully.")
    except Exception as e:
        print_warning(f"Failed to install pyfiglet: {e}")

# ----------------------------------------------------------------------
# Main Setup Process
# ----------------------------------------------------------------------
def run_full_setup():
    console.print("\n" + "=" * 60)
    console.print(f"[bold]Python Development Environment Setup v{VERSION}[/bold]")
    console.print("=" * 60 + "\n")

    print_step("Starting unattended setup...")

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

    console.print("\n" + "=" * 60)
    console.print("[bold]Setup Summary[/bold]")
    console.print("=" * 60)
    
    sys_deps_status = "✓ Installed" if check_command_available("gcc") else "× Failed"
    console.print(f"System Dependencies: {sys_deps_status}")
    
    pyenv_status = "✓ Installed" if os.path.exists(PYENV_BIN) else "× Failed"
    console.print(f"pyenv: {pyenv_status}")
    
    python_installed = os.path.exists(os.path.join(PYENV_DIR, "shims", "python"))
    python_status = "✓ Installed" if python_installed else "× Failed"
    console.print(f"Python (via pyenv): {python_status}")
    
    pipx_installed = check_command_available("pipx") or os.path.exists(os.path.join(HOME_DIR, ".local/bin/pipx"))
    pipx_status = "✓ Installed" if pipx_installed else "× Failed"
    console.print(f"pipx: {pipx_status}")

    install_rich_and_pyfiglet()

    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
    console.print("\n[bold]Next Steps:[/bold]")
    console.print(f"To fully apply all changes, {ORIGINAL_USER} should restart their terminal or run:")
    console.print(f"source ~/.{shell_name}rc")

    console.print("\n[bold green]✓ Setup process completed![/bold green]")

# ----------------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------------
def main():
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: sys.exit(128 + signum))
        
        if os.geteuid() != 0:
            print_error("This script must be run with root privileges. Please run with sudo.")
            sys.exit(1)
        
        run_full_setup()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print_header("Python Dev Setup")
    main()