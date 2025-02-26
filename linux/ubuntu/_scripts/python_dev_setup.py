#!/usr/bin/env python3
"""
Python Dev Setup Script
--------------------------------------------------------
Description:
  A robust, visually engaging script that prepares an Ubuntu system
  with essential Python development tools:
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
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
HOME = os.path.expanduser("~")
LOG_FILE = os.path.join(HOME, ".python_dev_setup.log")
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# pyenv configuration
PYENV_ROOT = os.path.join(HOME, ".pyenv")

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NC = "\033[0m"  # Reset / No Color

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------


class NordColorFormatter(logging.Formatter):
    """
    A custom formatter that applies Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)

        if not self.use_colors:
            return msg

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir) and log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord theme styling.
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------


def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["curl", "git"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"The '{cmd}' command is not found in your PATH. Please install it and try again."
            )
            sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def check_non_root():
    """
    Ensure the script is run as a non-root user.
    """
    if os.geteuid() == 0:
        logging.error(
            "This script must be run as a non-root user. Please do not use sudo."
        )
        sys.exit(1)


def run_command(command, check=True, capture_output=False, shell=False, cwd=None):
    """
    Run a shell command with proper error handling.

    Args:
        command: Command to run (list or string)
        check: Whether to check for non-zero exit code
        capture_output: Whether to capture command output
        shell: Whether to run command in shell
        cwd: Directory to run command in

    Returns:
        CompletedProcess instance

    Raises:
        SystemExit on command failure if check=True
    """
    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=capture_output,
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
    Install required APT dependencies.
    """
    print_section("Installing APT Dependencies")

    logging.info("Refreshing package repositories...")
    run_command(["sudo", "apt-get", "update", "-qq"])

    logging.info("Upgrading existing packages...")
    run_command(["sudo", "apt-get", "upgrade", "-y"])

    logging.info("Installing required dependencies...")
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
    run_command(["sudo", "apt-get", "install", "-y"] + apt_packages)

    logging.info("Cleaning up package caches...")
    run_command(["sudo", "apt-get", "clean"])


# ------------------------------------------------------------------------------
# PYENV INSTALLATION
# ------------------------------------------------------------------------------


def install_or_update_pyenv():
    """
    Install or update pyenv for Python version management.
    """
    print_section("Installing/Updating pyenv")

    if not os.path.isdir(PYENV_ROOT):
        logging.info("pyenv not found. Installing pyenv...")
        run_command(["git", "clone", "https://github.com/pyenv/pyenv.git", PYENV_ROOT])

        # Add pyenv to bashrc if not already present
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
                logging.info("Successfully updated ~/.bashrc with pyenv initialization")
            except Exception as e:
                logging.warning(f"Failed to update ~/.bashrc: {e}")
    else:
        logging.info("pyenv is already installed. Updating pyenv...")
        run_command(["git", "pull", "--ff-only"], cwd=PYENV_ROOT)

    # Ensure pyenv is available in this session
    os.environ["PYENV_ROOT"] = PYENV_ROOT
    os.environ["PATH"] = (
        os.path.join(PYENV_ROOT, "bin") + os.pathsep + os.environ.get("PATH", "")
    )


# ------------------------------------------------------------------------------
# PYTHON INSTALLATION
# ------------------------------------------------------------------------------


def install_latest_python():
    """
    Install the latest stable Python version via pyenv.
    """
    print_section("Installing Latest Python via pyenv")

    logging.info("Searching for the latest stable Python 3.x version...")
    result = run_command(["pyenv", "install", "-l"], capture_output=True)
    lines = result.stdout.splitlines()

    # Find the latest Python 3 version
    latest_py3 = None
    pattern = re.compile(r"^\s*(3\.\d+\.\d+)$")
    for line in lines:
        match = pattern.match(line)
        if match:
            latest_py3 = match.group(1)  # The last matching version will be stored

    if not latest_py3:
        logging.error("Could not determine the latest Python 3.x version from pyenv.")
        sys.exit(1)

    # Check current Python version
    try:
        result = run_command(["pyenv", "global"], capture_output=True)
        current_py3 = result.stdout.strip()
    except Exception:
        current_py3 = ""

    logging.info(f"Latest Python 3.x version available: {latest_py3}")
    logging.info(
        f"Currently active pyenv Python version: {current_py3 if current_py3 else 'None'}"
    )

    # Install if needed
    if current_py3 != latest_py3:
        try:
            result = run_command(["pyenv", "versions", "--bare"], capture_output=True)
            versions = result.stdout.splitlines()
        except Exception:
            versions = []

        if latest_py3 not in versions:
            logging.info(f"Installing Python {latest_py3} via pyenv...")
            run_command(["pyenv", "install", latest_py3])

        logging.info(f"Setting Python {latest_py3} as the global version...")
        run_command(["pyenv", "global", latest_py3])
        logging.info(f"Successfully installed and configured Python {latest_py3}")
    else:
        logging.info(f"Python {latest_py3} is already installed and set as global.")

    # Refresh shell environment
    try:
        run_command(["pyenv", "init", "-"])
    except Exception:
        pass


# ------------------------------------------------------------------------------
# UV INSTALLATION
# ------------------------------------------------------------------------------


def install_uv():
    """
    Install the uv package manager.
    """
    print_section("Installing UV Package Manager")

    logging.info("Downloading and installing uv...")
    run_command("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
    logging.info("UV package manager installation completed.")


# ------------------------------------------------------------------------------
# RUFF INSTALLATION
# ------------------------------------------------------------------------------


def install_ruff():
    """
    Install the ruff linter.
    """
    print_section("Installing Ruff Linter")

    logging.info("Downloading and installing ruff...")
    run_command("curl -LsSf https://astral.sh/ruff/install.sh | sh", shell=True)
    logging.info("Ruff linter installation completed.")


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()
    check_non_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"PYTHON DEV SETUP STARTED AT {now}")
    logging.info("=" * 80)

    # Install APT dependencies
    install_apt_dependencies()

    # Install or update pyenv
    install_or_update_pyenv()

    # Install the latest Python version
    install_latest_python()

    # Install uv package manager
    install_uv()

    # Install ruff linter
    install_ruff()

    # Finish up
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
