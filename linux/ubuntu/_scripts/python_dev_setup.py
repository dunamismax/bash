#!/usr/bin/env python3
"""
Python Dev Setup Script
--------------------------------------------------------
Description:
  A robust, visually engaging script that prepares an Ubuntu system with essential Python
  development tools:
    - Installs/updates APT dependencies
    - Installs/updates pyenv (for managing Python versions)
    - Installs the latest stable Python via pyenv
    - Installs uv package manager
    - Installs ruff linter

IMPORTANT: Do NOT run this script with sudo! It must be run as a standard non-root user.

Usage:
  ./python_dev_setup.py

Author: Your Name | License: MIT | Version: 2.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
HOME = os.path.expanduser("~")
LOG_FILE = os.path.join(HOME, ".python_dev_setup.log")
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# pyenv configuration
PYENV_ROOT = os.path.join(HOME, ".pyenv")

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
    """
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
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
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")

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
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


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
    cleanup()
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Execute cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Verify that required commands are available.
    """
    required_commands = ["curl", "git"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"Required command '{cmd}' not found in PATH. Please install it and try again."
            )
            sys.exit(1)


def check_non_root():
    """
    Ensure the script is run as a non-root user.
    """
    if os.geteuid() == 0:
        logging.error("This script must be run as a non-root user. Do not use sudo.")
        sys.exit(1)


def run_command(command, check=True, capture_output=False, shell=False, cwd=None):
    """
    Execute a shell command with error handling.
    """
    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
            shell=shell,
            cwd=cwd,
        )
        return result
    except subprocess.CalledProcessError as e:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        logging.error(f"Command failed: {cmd_str}")
        logging.error(f"Exit code: {e.returncode}")
        if capture_output and e.stderr:
            logging.error(f"Error output: {e.stderr}")
        if check:
            sys.exit(1)
        raise


# ------------------------------------------------------------------------------
# APT DEPENDENCIES INSTALLATION
# ------------------------------------------------------------------------------
def install_apt_dependencies():
    """
    Install and upgrade APT dependencies.
    """
    print_section("Installing APT Dependencies")

    logging.info("Refreshing package repositories...")
    run_with_progress(
        "Refreshing package repositories...",
        run_command,
        ["sudo", "apt-get", "update", "-qq"],
    )

    logging.info("Upgrading existing packages...")
    run_with_progress(
        "Upgrading packages...", run_command, ["sudo", "apt-get", "upgrade", "-y"]
    )

    logging.info("Installing required packages...")
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
    run_with_progress(
        "Installing packages...",
        run_command,
        ["sudo", "apt-get", "install", "-y"] + apt_packages,
    )

    logging.info("Cleaning up package caches...")
    run_with_progress("Cleaning up...", run_command, ["sudo", "apt-get", "clean"])


# ------------------------------------------------------------------------------
# PYENV INSTALLATION/UPDATE
# ------------------------------------------------------------------------------
def install_or_update_pyenv():
    """
    Install or update pyenv for Python version management.
    """
    print_section("Installing/Updating pyenv")

    if not os.path.isdir(PYENV_ROOT):
        logging.info("pyenv not found. Cloning pyenv repository...")
        run_with_progress(
            "Cloning pyenv...",
            run_command,
            ["git", "clone", "https://github.com/pyenv/pyenv.git", PYENV_ROOT],
        )

        # Append pyenv initialization to shell config if needed
        bashrc = os.path.join(HOME, ".bashrc")
        try:
            with open(bashrc, "r") as f:
                content = f.read()
        except Exception:
            content = ""
        if "export PYENV_ROOT" not in content:
            logging.info("Adding pyenv initialization to ~/.bashrc...")
            init_block = (
                "\n# >>> pyenv initialization >>>\n"
                'export PYENV_ROOT="$HOME/.pyenv"\n'
                'export PATH="$PYENV_ROOT/bin:$PATH"\n'
                "if command -v pyenv 1>/dev/null 2>&1; then\n"
                '    eval "$(pyenv init -)"\n'
                "fi\n"
                "# <<< pyenv initialization <<<\n"
            )
            try:
                with open(bashrc, "a") as f:
                    f.write(init_block)
                logging.info(
                    "Successfully updated ~/.bashrc with pyenv initialization."
                )
            except Exception as e:
                logging.warning(f"Failed to update ~/.bashrc: {e}")
    else:
        logging.info("pyenv is already installed. Pulling latest changes...")
        run_with_progress(
            "Updating pyenv...",
            run_command,
            ["git", "pull", "--ff-only"],
            cwd=PYENV_ROOT,
        )

    # Ensure current session has pyenv in PATH
    os.environ["PYENV_ROOT"] = PYENV_ROOT
    os.environ["PATH"] = (
        os.path.join(PYENV_ROOT, "bin") + os.pathsep + os.environ.get("PATH", "")
    )


# ------------------------------------------------------------------------------
# PYTHON INSTALLATION VIA PYENV
# ------------------------------------------------------------------------------
def install_latest_python():
    """
    Install the latest stable Python version via pyenv.
    """
    print_section("Installing Latest Python via pyenv")

    logging.info("Retrieving available Python versions from pyenv...")
    result = run_command(["pyenv", "install", "-l"], capture_output=True)
    versions = result.stdout.splitlines()
    latest_py3 = None
    pattern = re.compile(r"^\s*(3\.\d+\.\d+)$")
    for line in versions:
        match = pattern.match(line)
        if match:
            latest_py3 = match.group(1)  # The last matching version is the latest

    if not latest_py3:
        logging.error("Unable to determine the latest Python 3.x version from pyenv.")
        sys.exit(1)

    # Determine current global Python version
    try:
        current = run_command(["pyenv", "global"], capture_output=True).stdout.strip()
    except Exception:
        current = ""

    logging.info(f"Latest Python 3.x version available: {latest_py3}")
    logging.info(f"Current pyenv global version: {current if current else 'None'}")

    if current != latest_py3:
        # Check if the desired version is already installed
        try:
            result = run_command(["pyenv", "versions", "--bare"], capture_output=True)
            installed_versions = result.stdout.splitlines()
        except Exception:
            installed_versions = []

        if latest_py3 not in installed_versions:
            logging.info(f"Installing Python {latest_py3} via pyenv...")
            run_with_progress(
                f"Installing Python {latest_py3}...",
                run_command,
                ["pyenv", "install", latest_py3],
            )
        logging.info(f"Setting Python {latest_py3} as the global version...")
        run_command(["pyenv", "global", latest_py3])
        logging.info(f"Successfully configured Python {latest_py3}.")
    else:
        logging.info(f"Python {latest_py3} is already set as the global version.")

    # Refresh pyenv environment (if needed)
    try:
        run_command(["pyenv", "init", "-"])
    except Exception:
        pass


# ------------------------------------------------------------------------------
# UV PACKAGE MANAGER INSTALLATION
# ------------------------------------------------------------------------------
def install_uv():
    """
    Install the uv package manager.
    """
    print_section("Installing UV Package Manager")
    logging.info("Downloading and installing uv...")
    run_with_progress(
        "Installing uv...",
        run_command,
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        shell=True,
    )
    logging.info("UV package manager installation completed.")


# ------------------------------------------------------------------------------
# RUFF LINTER INSTALLATION
# ------------------------------------------------------------------------------
def install_ruff():
    """
    Install the ruff linter.
    """
    print_section("Installing Ruff Linter")
    logging.info("Downloading and installing ruff...")
    run_with_progress(
        "Installing ruff...",
        run_command,
        "curl -LsSf https://astral.sh/ruff/install.sh | sh",
        shell=True,
    )
    logging.info("Ruff linter installation completed.")


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the setup script.
    """
    setup_logging()
    check_dependencies()
    check_non_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PYTHON DEV SETUP STARTED AT {now}")
    logging.info("=" * 80)

    install_apt_dependencies()
    install_or_update_pyenv()
    install_latest_python()
    install_uv()
    install_ruff()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PYTHON DEV SETUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)
    logging.info("Your system is now configured with:")
    logging.info("  - Essential development packages")
    logging.info("  - The latest stable Python installed via pyenv")
    logging.info("  - UV package manager for Python dependencies")
    logging.info("  - Ruff linter for code quality")
    logging.info("")
    logging.info("NOTE: To apply pyenv changes to your current shell, run:")
    logging.info("  source ~/.bashrc")
    logging.info("")
    logging.info("Happy coding!")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
