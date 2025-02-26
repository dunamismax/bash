#!/usr/bin/env python3
"""
Enhanced Python Development Environment Setup
--------------------------------------------------------
Description:
  A robust, visually engaging script that prepares an Ubuntu system with essential Python
  development tools:
    - Installs/updates APT dependencies
    - Installs/updates pyenv (for managing Python versions)
    - Installs the latest stable Python via pyenv
    - Installs uv package manager
    - Installs ruff linter
    - Sets up proper configuration in shell profiles

IMPORTANT: Do NOT run this script with sudo! It must be run as a standard non-root user.

Usage:
  ./python_dev_setup.py

Author: Your Name | License: MIT | Version: 3.0.0
"""

import atexit
import json
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    BarColumn,
)
from rich.table import Table

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
HOME = os.path.expanduser("~")
LOG_FILE = os.path.join(HOME, ".python_dev_setup.log")
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Rich console for better output formatting
console = Console()

# pyenv configuration
PYENV_ROOT = os.path.join(HOME, ".pyenv")
PYENV_BIN = os.path.join(PYENV_ROOT, "bin", "pyenv")

# Shell configuration files
SHELL_CONFIG_FILES = [
    os.path.join(HOME, ".bashrc"),
    os.path.join(HOME, ".zshrc"),
    os.path.join(HOME, ".profile"),
]

# Tool status tracker
INSTALLATION_STATUS = {
    "apt_dependencies": {"status": "pending", "version": "", "message": ""},
    "pyenv": {"status": "pending", "version": "", "message": ""},
    "python": {"status": "pending", "version": "", "message": ""},
    "uv": {"status": "pending", "version": "", "message": ""},
    "ruff": {"status": "pending", "version": "", "message": ""},
}

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARNING)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color


# ------------------------------------------------------------------------------
# CUSTOM LOGGING SETUP
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    A custom logging formatter that applies the Nord color theme.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Configure logging with both console and file handlers using Nord colors.
    Rotates log files when they exceed 5MB.
    """
    log_level = getattr(logging, DEFAULT_LOG_LEVEL)

    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (plain text)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        # Rotate logs if they're larger than 5MB
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.debug(f"Rotated previous log to {backup_log}")

        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)  # Secure the log file
    except Exception as e:
        console.print(f"[yellow]Warning:[/] Failed to set up log file {LOG_FILE}: {e}")
        console.print("[yellow]Continuing with console logging only[/]")

    return logger


def print_section(title: str):
    """
    Print a section header styled with the Nord theme.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function in a background thread while displaying a progress spinner.

    Args:
        description: Text describing the task
        func: The function to run
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The return value from the function
    """
    max_retries = kwargs.pop("max_retries", 1) if "max_retries" in kwargs else 1
    retry_delay = kwargs.pop("retry_delay", 2) if "retry_delay" in kwargs else 2

    with ThreadPoolExecutor(max_workers=1) as executor:
        for attempt in range(max_retries):
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    transient=True,
                ) as progress:
                    task = progress.add_task(description, total=None)
                    future = executor.submit(func, *args, **kwargs)

                    while not future.done():
                        time.sleep(0.1)
                        progress.update(task)

                    return future.result()
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(
                        f"Task failed: {description}. Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    logging.error(
                        f"Task failed after {max_retries} attempts: {description}"
                    )
                    logging.error(f"Error: {str(e)}")
                    raise


def run_command(
    command, check=True, capture_output=False, shell=False, cwd=None, env=None
):
    """
    Execute a shell command with error handling.

    Args:
        command: Command to execute (list or string)
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        shell: Whether to run through shell
        cwd: Working directory
        env: Environment variables

    Returns:
        CompletedProcess instance
    """
    cmd_str = command if isinstance(command, str) else " ".join(command)
    logging.debug(f"Running command: {cmd_str}")

    merged_env = None
    if env:
        merged_env = os.environ.copy()
        merged_env.update(env)

    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
            shell=shell,
            cwd=cwd,
            env=merged_env,
        )
        logging.debug(f"Command completed with exit code: {result.returncode}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {cmd_str}")
        logging.error(f"Exit code: {e.returncode}")
        if capture_output and e.stderr:
            logging.error(f"Error output: {e.stderr}")
        if check:
            raise
        else:
            return e


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Gracefully handle termination signals.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")

    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")

    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Execute cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    print_status_report()


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Verify that required commands are available and the system is compatible.
    """
    # Check if we're on a supported platform
    os_info = platform.platform().lower()
    if "ubuntu" not in os_info and "debian" not in os_info:
        logging.warning(
            f"This script is designed for Ubuntu/Debian but you're running: {os_info}"
        )
        logging.warning("Some functionality may not work as expected.")

    # Check for required commands
    required_commands = ["curl", "git", "sudo"]
    missing = []

    for cmd in required_commands:
        if not shutil.which(cmd):
            missing.append(cmd)

    if missing:
        logging.error(f"Required commands not found: {', '.join(missing)}")
        logging.error("Please install these packages and try again.")

        # Suggest installation command
        if "apt-get" in os.environ.get("PATH", ""):
            logging.info(
                f"You can install them with: sudo apt-get install {' '.join(missing)}"
            )
        sys.exit(1)

    # Check internet connectivity
    try:
        result = run_command(
            ["curl", "-s", "--connect-timeout", "5", "https://www.google.com"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            logging.warning(
                "Internet connectivity check failed. This script requires internet access."
            )
    except Exception:
        logging.warning(
            "Internet connectivity check failed. This script requires internet access."
        )


def check_non_root():
    """
    Ensure the script is run as a non-root user.
    """
    if os.geteuid() == 0:
        logging.error("This script must be run as a non-root user. Do not use sudo.")
        logging.error(
            "The script will use sudo when needed for system-wide installations."
        )
        sys.exit(1)

    # Check sudo access
    try:
        run_command(["sudo", "-v"], capture_output=True)
        logging.debug("Sudo access confirmed.")
    except Exception:
        logging.warning("You don't seem to have sudo access. Some operations may fail.")


# ------------------------------------------------------------------------------
# APT DEPENDENCIES INSTALLATION
# ------------------------------------------------------------------------------
def install_apt_dependencies():
    """
    Install and upgrade APT dependencies required for Python development.
    """
    print_section("Installing APT Dependencies")
    INSTALLATION_STATUS["apt_dependencies"]["status"] = "in_progress"

    # List of packages required for Python development
    apt_packages = [
        "build-essential",
        "git",
        "curl",
        "wget",
        "vim",
        "tmux",
        "unzip",
        "zip",
        "ca-certificates",
        "libssl-dev",
        "libffi-dev",
        "zlib1g-dev",
        "libbz2-dev",
        "libreadline-dev",
        "libsqlite3-dev",
        "libncurses5-dev",
        "libgdbm-dev",
        "libnss3-dev",
        "liblzma-dev",
        "xz-utils",
        "libxml2-dev",
        "libxmlsec1-dev",
        "tk-dev",
        "llvm",
        "gnupg",
        "lsb-release",
        "jq",
    ]

    # Check which packages are already installed
    installed_packages = []
    try:
        result = run_command(
            "dpkg-query -W -f='${Package}\\n' | sort",
            shell=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            installed_packages = result.stdout.splitlines()
    except Exception as e:
        logging.warning(f"Failed to check installed packages: {e}")

    # Filter to packages that need installation
    packages_to_install = [pkg for pkg in apt_packages if pkg not in installed_packages]

    if not packages_to_install:
        logging.info("All required APT packages are already installed.")
        INSTALLATION_STATUS["apt_dependencies"] = {
            "status": "success",
            "version": "latest",
            "message": "All packages already installed",
        }
        return
    else:
        logging.info(
            f"Need to install {len(packages_to_install)} packages: {', '.join(packages_to_install)}"
        )

    # Always update package lists first
    logging.info("Refreshing package repositories...")
    try:
        run_with_progress(
            "Refreshing package repositories...",
            run_command,
            ["sudo", "apt-get", "update", "-qq"],
            max_retries=3,
        )
    except Exception as e:
        logging.error(f"Failed to update package repositories: {e}")
        INSTALLATION_STATUS["apt_dependencies"] = {
            "status": "failed",
            "version": "",
            "message": f"Failed to update repositories: {str(e)}",
        }
        return

    # Install packages
    if packages_to_install:
        try:
            run_with_progress(
                "Installing packages...",
                run_command,
                ["sudo", "apt-get", "install", "-y"] + packages_to_install,
                max_retries=2,
            )
            msg = f"Successfully installed {len(packages_to_install)} packages"
            logging.info(msg)
            INSTALLATION_STATUS["apt_dependencies"] = {
                "status": "success",
                "version": "latest",
                "message": msg,
            }
        except Exception as e:
            logging.error(f"Failed to install APT packages: {e}")
            INSTALLATION_STATUS["apt_dependencies"] = {
                "status": "failed",
                "version": "",
                "message": f"Failed to install packages: {str(e)}",
            }
            return

    # Cleaning up
    logging.info("Cleaning up package caches...")
    try:
        run_with_progress("Cleaning up...", run_command, ["sudo", "apt-get", "clean"])
    except Exception as e:
        logging.warning(f"Failed to clean package caches (non-critical): {e}")


# ------------------------------------------------------------------------------
# PYENV INSTALLATION/UPDATE
# ------------------------------------------------------------------------------
def install_or_update_pyenv():
    """
    Install or update pyenv for Python version management.
    Handles shell configuration and environment setup.
    """
    print_section("Installing/Updating pyenv")
    INSTALLATION_STATUS["pyenv"]["status"] = "in_progress"

    # Check if pyenv is already in PATH
    pyenv_in_path = shutil.which("pyenv")
    current_version = ""

    if os.path.isdir(PYENV_ROOT):
        logging.info(f"pyenv is already installed at {PYENV_ROOT}")

        # Get current version before update
        try:
            if os.path.exists(PYENV_BIN):
                result = run_command([PYENV_BIN, "--version"], capture_output=True)
                current_version = result.stdout.strip()
                logging.info(f"Current pyenv version: {current_version}")
                INSTALLATION_STATUS["pyenv"]["version"] = current_version
        except Exception as e:
            logging.warning(f"Could not determine current pyenv version: {e}")

        # Update pyenv
        logging.info("Updating pyenv to the latest version...")
        try:
            run_with_progress(
                "Updating pyenv...",
                run_command,
                ["git", "pull", "--ff-only"],
                cwd=PYENV_ROOT,
            )

            # Get new version after update
            try:
                result = run_command([PYENV_BIN, "--version"], capture_output=True)
                new_version = result.stdout.strip()
                if new_version != current_version:
                    logging.info(f"Updated pyenv to: {new_version}")
                    INSTALLATION_STATUS["pyenv"] = {
                        "status": "success",
                        "version": new_version,
                        "message": f"Updated from {current_version} to {new_version}",
                    }
                else:
                    logging.info("pyenv is already at the latest version")
                    INSTALLATION_STATUS["pyenv"] = {
                        "status": "success",
                        "version": new_version,
                        "message": "Already at latest version",
                    }
            except Exception as e:
                logging.warning(f"Could not determine updated pyenv version: {e}")
                INSTALLATION_STATUS["pyenv"] = {
                    "status": "success",
                    "version": current_version,
                    "message": "Updated successfully but couldn't verify version",
                }
        except Exception as e:
            logging.error(f"Failed to update pyenv: {e}")
            INSTALLATION_STATUS["pyenv"] = {
                "status": "failed",
                "version": current_version,
                "message": f"Update failed: {str(e)}",
            }
            return
    else:
        logging.info("pyenv not found. Installing...")
        try:
            # Create parent directory if needed
            os.makedirs(os.path.dirname(PYENV_ROOT), exist_ok=True)

            # Clone pyenv repository
            run_with_progress(
                "Cloning pyenv...",
                run_command,
                ["git", "clone", "https://github.com/pyenv/pyenv.git", PYENV_ROOT],
            )

            # Verify installation
            try:
                result = run_command([PYENV_BIN, "--version"], capture_output=True)
                version = result.stdout.strip()
                logging.info(f"Successfully installed pyenv: {version}")
                INSTALLATION_STATUS["pyenv"] = {
                    "status": "success",
                    "version": version,
                    "message": "Freshly installed",
                }
            except Exception as e:
                logging.warning(f"Installed pyenv but couldn't verify version: {e}")
                INSTALLATION_STATUS["pyenv"] = {
                    "status": "partial",
                    "version": "unknown",
                    "message": "Installed but couldn't verify version",
                }
        except Exception as e:
            logging.error(f"Failed to install pyenv: {e}")
            INSTALLATION_STATUS["pyenv"] = {
                "status": "failed",
                "version": "",
                "message": f"Installation failed: {str(e)}",
            }
            return

    # Configure shell initialization
    init_block = (
        "\n# >>> pyenv initialization >>>\n"
        'export PYENV_ROOT="$HOME/.pyenv"\n'
        'export PATH="$PYENV_ROOT/bin:$PATH"\n'
        "if command -v pyenv 1>/dev/null 2>&1; then\n"
        '    eval "$(pyenv init -)"\n'
        "fi\n"
        "# <<< pyenv initialization <<<\n"
    )

    # Check and update each shell config file
    shell_configs_updated = False
    for config_file in SHELL_CONFIG_FILES:
        if not os.path.exists(config_file):
            continue

        try:
            with open(config_file, "r") as f:
                content = f.read()

            if "pyenv init" not in content:
                logging.info(f"Adding pyenv initialization to {config_file}")
                with open(config_file, "a") as f:
                    f.write(init_block)
                shell_configs_updated = True
                logging.info(f"Successfully updated {config_file}")
        except Exception as e:
            logging.warning(f"Failed to update {config_file}: {e}")

    if shell_configs_updated:
        logging.info("Shell configuration files have been updated.")
        logging.info(
            "You'll need to restart your shell or run 'source ~/.bashrc' (or equivalent) to use pyenv."
        )
    elif not pyenv_in_path and not shell_configs_updated:
        logging.warning("Could not find any shell configuration files to update.")
        logging.warning("You may need to manually add pyenv to your PATH.")
        logging.info("Add the following to your shell configuration file:")
        logging.info(init_block.strip())

    # Ensure current session has pyenv in PATH
    os.environ["PYENV_ROOT"] = PYENV_ROOT
    bin_path = os.path.join(PYENV_ROOT, "bin")
    os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")


# ------------------------------------------------------------------------------
# PYTHON INSTALLATION VIA PYENV
# ------------------------------------------------------------------------------
def install_latest_python():
    """
    Install the latest stable Python version via pyenv.
    Also sets it as the global Python version.
    """
    print_section("Installing Latest Python via pyenv")
    INSTALLATION_STATUS["python"]["status"] = "in_progress"

    # Get available Python versions
    logging.info("Retrieving available Python versions from pyenv...")
    try:
        result = run_command([PYENV_BIN, "install", "-l"], capture_output=True)
        versions = result.stdout.splitlines()
    except Exception as e:
        logging.error(f"Failed to list available Python versions: {e}")
        INSTALLATION_STATUS["python"] = {
            "status": "failed",
            "version": "",
            "message": f"Failed to list versions: {str(e)}",
        }
        return

    # Find latest stable Python 3.x version
    latest_py3 = None
    pattern = re.compile(r"^\s*(3\.\d+\.\d+)$")
    for line in versions:
        match = pattern.match(line)
        if match:
            latest_py3 = match.group(1)  # The last matching version is the latest

    if not latest_py3:
        logging.error("Unable to determine the latest Python 3.x version from pyenv.")
        INSTALLATION_STATUS["python"] = {
            "status": "failed",
            "version": "",
            "message": "Couldn't determine latest Python version",
        }
        return

    # Get current Python version from pyenv
    try:
        result = run_command([PYENV_BIN, "global"], capture_output=True)
        current = result.stdout.strip()
    except Exception:
        current = ""
        logging.warning("Could not determine current pyenv global Python version")

    logging.info(f"Latest Python 3.x version available: {latest_py3}")
    if current:
        logging.info(f"Current pyenv global version: {current}")

    # Check if the version is already installed
    try:
        result = run_command([PYENV_BIN, "versions", "--bare"], capture_output=True)
        installed_versions = result.stdout.splitlines()
    except Exception:
        installed_versions = []
        logging.warning("Could not determine currently installed Python versions")

    # Install the latest version if needed
    if latest_py3 in installed_versions:
        logging.info(f"Python {latest_py3} is already installed.")
        already_installed = True
    else:
        logging.info(f"Installing Python {latest_py3}...")
        try:
            run_with_progress(
                f"Installing Python {latest_py3} (this may take several minutes)...",
                run_command,
                [PYENV_BIN, "install", latest_py3],
                max_retries=1,
            )
            logging.info(f"Successfully installed Python {latest_py3}")
            already_installed = False
        except Exception as e:
            logging.error(f"Failed to install Python {latest_py3}: {e}")
            INSTALLATION_STATUS["python"] = {
                "status": "failed",
                "version": "",
                "message": f"Installation failed: {str(e)}",
            }
            return

    # Set as global version if needed
    if current != latest_py3:
        logging.info(f"Setting Python {latest_py3} as the global version...")
        try:
            run_command([PYENV_BIN, "global", latest_py3])
            logging.info(
                f"Successfully configured Python {latest_py3} as global version."
            )

            if already_installed:
                INSTALLATION_STATUS["python"] = {
                    "status": "success",
                    "version": latest_py3,
                    "message": f"Already installed, set as global version",
                }
            else:
                INSTALLATION_STATUS["python"] = {
                    "status": "success",
                    "version": latest_py3,
                    "message": f"Installed and set as global version",
                }
        except Exception as e:
            logging.error(f"Failed to set Python {latest_py3} as global version: {e}")
            if already_installed:
                INSTALLATION_STATUS["python"] = {
                    "status": "partial",
                    "version": latest_py3,
                    "message": f"Already installed, but failed to set as global: {str(e)}",
                }
            else:
                INSTALLATION_STATUS["python"] = {
                    "status": "partial",
                    "version": latest_py3,
                    "message": f"Installed, but failed to set as global: {str(e)}",
                }
    else:
        logging.info(f"Python {latest_py3} is already set as the global version.")
        INSTALLATION_STATUS["python"] = {
            "status": "success",
            "version": latest_py3,
            "message": "Already installed and set as global",
        }

    # Verify Python installation
    try:
        # Initialize pyenv shims in the current shell
        run_command([PYENV_BIN, "init", "-"], check=False)

        # Use the full path to the Python executable
        python_exe = os.path.join(PYENV_ROOT, "shims", "python")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(
                PYENV_ROOT, "versions", latest_py3, "bin", "python"
            )

        result = run_command([python_exe, "--version"], capture_output=True)
        logging.info(f"Python verification: {result.stdout.strip()}")
    except Exception as e:
        logging.warning(f"Python installation verification failed (non-critical): {e}")
        logging.info(
            "You may need to restart your shell to use the new Python version."
        )


# ------------------------------------------------------------------------------
# UV PACKAGE MANAGER INSTALLATION
# ------------------------------------------------------------------------------
def install_uv():
    """
    Install the uv package manager for Python dependencies.
    """
    print_section("Installing UV Package Manager")
    INSTALLATION_STATUS["uv"]["status"] = "in_progress"

    # Check if uv is already installed
    uv_path = shutil.which("uv")
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    cargo_uv = os.path.join(cargo_bin, "uv")

    if uv_path:
        try:
            result = run_command(["uv", "--version"], capture_output=True)
            version = result.stdout.strip()
            logging.info(f"UV package manager is already installed: {version}")
            INSTALLATION_STATUS["uv"] = {
                "status": "success",
                "version": version,
                "message": "Already installed",
            }
            return
        except Exception:
            logging.info(
                "UV package manager seems to be installed but not working correctly."
            )
    elif os.path.exists(cargo_uv):
        try:
            result = run_command([cargo_uv, "--version"], capture_output=True)
            version = result.stdout.strip()
            logging.info(f"UV package manager is installed at {cargo_uv}: {version}")
            logging.info(f"Adding {cargo_bin} to PATH")
            os.environ["PATH"] += os.pathsep + cargo_bin
            INSTALLATION_STATUS["uv"] = {
                "status": "success",
                "version": version,
                "message": f"Already installed at {cargo_uv}",
            }
            return
        except Exception:
            logging.info(f"Found uv at {cargo_uv} but it's not working correctly.")

    logging.info("Downloading and installing uv...")
    install_script = "curl -LsSf https://astral.sh/uv/install.sh | sh"

    try:
        run_with_progress(
            "Installing uv...", run_command, install_script, shell=True, max_retries=2
        )

        # Check all possible locations
        uv_path = shutil.which("uv")
        if not uv_path and os.path.exists(cargo_uv):
            logging.info(f"UV installed at {cargo_uv} but not in PATH")
            os.environ["PATH"] += os.pathsep + cargo_bin
            uv_path = cargo_uv

        # Verify installation
        if uv_path:
            try:
                result = run_command([uv_path, "--version"], capture_output=True)
                version = result.stdout.strip()
                logging.info(f"UV package manager successfully installed: {version}")
                INSTALLATION_STATUS["uv"] = {
                    "status": "success",
                    "version": version,
                    "message": "Newly installed",
                }
            except Exception as e:
                logging.warning(f"UV installation verification failed: {e}")
                INSTALLATION_STATUS["uv"] = {
                    "status": "partial",
                    "version": "unknown",
                    "message": f"Installed but verification failed: {str(e)}",
                }
        else:
            logging.warning("UV installed but couldn't find executable in PATH")
            INSTALLATION_STATUS["uv"] = {
                "status": "partial",
                "version": "unknown",
                "message": "Installed but executable not found in PATH",
            }
    except Exception as e:
        logging.error(f"Failed to install UV package manager: {e}")
        INSTALLATION_STATUS["uv"] = {
            "status": "failed",
            "version": "",
            "message": f"Installation failed: {str(e)}",
        }


# ------------------------------------------------------------------------------
# RUFF LINTER INSTALLATION
# ------------------------------------------------------------------------------
def install_ruff():
    """
    Install the ruff linter for Python code quality.
    """
    print_section("Installing Ruff Linter")
    INSTALLATION_STATUS["ruff"]["status"] = "in_progress"

    # Check if ruff is already installed
    ruff_path = shutil.which("ruff")
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    cargo_ruff = os.path.join(cargo_bin, "ruff")

    if ruff_path:
        try:
            result = run_command(["ruff", "--version"], capture_output=True)
            version = result.stdout.strip()
            logging.info(f"Ruff linter is already installed: {version}")
            INSTALLATION_STATUS["ruff"] = {
                "status": "success",
                "version": version,
                "message": "Already installed",
            }
            return
        except Exception:
            logging.info("Ruff linter seems to be installed but not working correctly.")
    elif os.path.exists(cargo_ruff):
        try:
            result = run_command([cargo_ruff, "--version"], capture_output=True)
            version = result.stdout.strip()
            logging.info(f"Ruff linter is installed at {cargo_ruff}: {version}")
            logging.info(f"Adding {cargo_bin} to PATH")
            os.environ["PATH"] += os.pathsep + cargo_bin
            INSTALLATION_STATUS["ruff"] = {
                "status": "success",
                "version": version,
                "message": f"Already installed at {cargo_ruff}",
            }
            return
        except Exception:
            logging.info(f"Found ruff at {cargo_ruff} but it's not working correctly.")

    logging.info("Downloading and installing ruff...")
    install_script = "curl -LsSf https://astral.sh/ruff/install.sh | sh"

    try:
        run_with_progress(
            "Installing ruff...", run_command, install_script, shell=True, max_retries=2
        )

        # Check all possible locations
        ruff_path = shutil.which("ruff")
        if not ruff_path and os.path.exists(cargo_ruff):
            logging.info(f"Ruff installed at {cargo_ruff} but not in PATH")
            os.environ["PATH"] += os.pathsep + cargo_bin
            ruff_path = cargo_ruff

        # Verify installation
        if ruff_path:
            try:
                result = run_command([ruff_path, "--version"], capture_output=True)
                version = result.stdout.strip()
                logging.info(f"Ruff linter successfully installed: {version}")
                INSTALLATION_STATUS["ruff"] = {
                    "status": "success",
                    "version": version,
                    "message": "Newly installed",
                }
            except Exception as e:
                logging.warning(f"Ruff installation verification failed: {e}")
                INSTALLATION_STATUS["ruff"] = {
                    "status": "partial",
                    "version": "unknown",
                    "message": f"Installed but verification failed: {str(e)}",
                }
        else:
            logging.warning("Ruff installed but couldn't find executable in PATH")
            INSTALLATION_STATUS["ruff"] = {
                "status": "partial",
                "version": "unknown",
                "message": "Installed but executable not found in PATH",
            }
    except Exception as e:
        logging.error(f"Failed to install Ruff linter: {e}")
        INSTALLATION_STATUS["ruff"] = {
            "status": "failed",
            "version": "",
            "message": f"Installation failed: {str(e)}",
        }


# ------------------------------------------------------------------------------
# STATUS REPORTING
# ------------------------------------------------------------------------------
def print_status_report():
    """
    Print a detailed status report of all installed components.
    """
    print_section("Installation Status Report")

    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "partial": "⚠" if not DISABLE_COLORS else "[PARTIAL]",
    }
    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
        "partial": NORD13,
    }
    descriptions = {
        "apt_dependencies": "APT Dependencies",
        "pyenv": "pyenv Version Manager",
        "python": "Python (via pyenv)",
        "uv": "UV Package Manager",
        "ruff": "Ruff Linter",
    }

    for tool, data in INSTALLATION_STATUS.items():
        status = data["status"]
        msg = data["message"]
        version = data["version"]
        tool_desc = descriptions.get(tool, tool)

        if not DISABLE_COLORS:
            icon = icons[status]
            color = colors[status]
            version_str = f" {version}" if version else ""
            logging.info(
                f"{color}{icon} {tool_desc}{version_str}: {status.upper()}{NC} - {msg}"
            )
        else:
            version_str = f" {version}" if version else ""
            logging.info(
                f"{icons[status]} {tool_desc}{version_str}: {status.upper()} - {msg}"
            )


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the setup script.
    """
    setup_logging()

    # Print welcome banner
    welcome = "Enhanced Python Development Environment Setup"
    border = "=" * len(welcome)
    logging.info(border)
    logging.info(welcome)
    logging.info(border)
    logging.info(
        "This script will prepare your system with essential Python development tools"
    )

    # Initial checks
    check_dependencies()
    check_non_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PYTHON DEV SETUP STARTED AT {now}")
    logging.info("=" * 80)

    # Main installation steps
    try:
        install_apt_dependencies()
        install_or_update_pyenv()
        install_latest_python()
        install_uv()
        install_ruff()

        # Print final status report
        print_status_report()

        elapsed = time.time() - start_time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info("=" * 80)
        logging.info(
            f"PYTHON DEV SETUP COMPLETED SUCCESSFULLY IN {elapsed:.2f} SECONDS AT {now}"
        )
        logging.info("=" * 80)

        # Final instructions
        logging.info("")
        logging.info("To apply all changes to your current shell, run:")
        logging.info("  source ~/.bashrc  # or ~/.zshrc if using zsh")
        logging.info("")
        logging.info("Your system is now configured with:")
        logging.info("  - Essential development packages")
        logging.info("  - The latest stable Python installed via pyenv")
        logging.info("  - UV package manager for Python dependencies")
        logging.info("  - Ruff linter for code quality")
        logging.info("")
        logging.info("Happy coding!")

    except Exception as ex:
        elapsed = time.time() - start_time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.error("=" * 80)
        logging.error(f"PYTHON DEV SETUP FAILED AFTER {elapsed:.2f} SECONDS AT {now}")
        logging.error(f"Error: {ex}")
        logging.error("=" * 80)
        print_status_report()  # Show what succeeded and what failed
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
