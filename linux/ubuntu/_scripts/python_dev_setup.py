#!/usr/bin/env python3
"""
Python Dev Setup Script
------------------------
Prepares an Ubuntu system with essential development tools:
  - Installs/updates APT dependencies.
  - Installs/updates pyenv (for managing Python versions).
  - Installs the latest stable Python via pyenv.

IMPORTANT: Do NOT run this script with sudo! It must be run as a standard non‑root user.
Usage Examples:
  ./python_dev_setup.py [-d|--debug] [-q|--quiet]
  ./python_dev_setup.py -h|--help

Author: Your Name | License: MIT | Version: 1.0
"""

import os
import sys
import subprocess
import signal
import atexit
import re
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
HOME = os.path.expanduser("~")
LOG_FILE = os.path.join(HOME, ".python_dev_setup.log")  # Log file in user's home directory
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)
SCRIPT_NAME = os.path.basename(sys.argv[0])
SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
QUIET_MODE = False  # When true, suppress console output

# pyenv configuration
PYENV_ROOT = os.path.join(HOME, ".pyenv")

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
def get_log_level_num(level: str) -> int:
    level = level.upper()
    if level in ("VERBOSE", "V"):
        return 0
    elif level in ("DEBUG", "D"):
        return 1
    elif level in ("INFO", "I"):
        return 2
    elif level in ("WARN", "WARNING", "W"):
        return 3
    elif level in ("ERROR", "E"):
        return 4
    elif level in ("CRITICAL", "C"):
        return 5
    else:
        return 2  # default to INFO if unknown

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
def log(level: str, message: str):
    global QUIET_MODE
    upper_level = level.upper()
    msg_level = get_log_level_num(upper_level)
    current_level = get_log_level_num(LOG_LEVEL)
    if msg_level < current_level:
        return

    color = NC
    if not DISABLE_COLORS:
        if upper_level == "DEBUG":
            color = NORD9
        elif upper_level == "INFO":
            color = NORD14
        elif upper_level in ("WARN", "WARNING"):
            color = NORD13
        elif upper_level in ("ERROR", "CRITICAL"):
            color = NORD11

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{upper_level}] {message}"

    # Append plain log entry to log file (without color codes)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write to log file: {e}\n")

    # Print colorized log entry to stderr if not in quiet mode
    if not QUIET_MODE:
        sys.stderr.write(f"{color}{log_entry}{NC}\n")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An unknown error occurred", exit_code=1, lineno=None, func="main"):
    lineno = lineno if lineno is not None else sys._getframe().f_lineno
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    log("ERROR", f"Error in function '{func}' at line {lineno}.")
    sys.stderr.write(f"{NORD11}ERROR: {error_message} (Exit Code: {exit_code}){NC}\n")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")
    # Insert any necessary cleanup tasks here

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum == signal.SIGINT:
        handle_error("Script interrupted by user.", 130, func="signal_handler")
    elif signum == signal.SIGTERM:
        handle_error("Script terminated.", 143, func="signal_handler")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_non_root():
    # Ensure the script is run as a non-root user.
    if os.geteuid() == 0:
        handle_error("Do NOT run this script as root. Please run as your normal user.")

def enable_debug():
    global LOG_LEVEL
    LOG_LEVEL = "DEBUG"
    log("DEBUG", "Debug mode enabled: Verbose logging activated.")

def enable_quiet_mode():
    global QUIET_MODE
    QUIET_MODE = True
    log("INFO", "Quiet mode enabled: Console output suppressed.")

def show_help():
    help_text = f"""Usage: {SCRIPT_NAME} [OPTIONS]

Description:
  Prepares an Ubuntu system with essential development tools,
  installs/updates pyenv, and installs the latest stable Python.
  IMPORTANT: Do NOT run this script with sudo.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output.
  -h, --help    Show this help message and exit.

Examples:
  {SCRIPT_NAME} --debug
  {SCRIPT_NAME} --quiet
  {SCRIPT_NAME} -h
"""
    print(help_text)

def parse_args(args):
    # A simple manual parser for command‑line options.
    while args:
        arg = args.pop(0)
        if arg in ("-d", "--debug"):
            enable_debug()
        elif arg in ("-q", "--quiet"):
            enable_quiet_mode()
        elif arg in ("-h", "--help"):
            show_help()
            sys.exit(0)
        else:
            log("WARN", f"Unknown option: {arg}")

# ------------------------------------------------------------------------------
# FUNCTION: Install APT-based Dependencies (using sudo where required)
# ------------------------------------------------------------------------------
def install_apt_dependencies():
    print_section("APT Dependencies Installation")
    log("INFO", "Refreshing package repositories...")
    try:
        subprocess.run(["sudo", "apt-get", "update", "-qq"], check=True)
    except subprocess.CalledProcessError:
        handle_error("Failed to refresh package repositories.")

    log("INFO", "Upgrading existing packages...")
    try:
        subprocess.run(["sudo", "apt-get", "upgrade", "-y"], check=True)
    except subprocess.CalledProcessError:
        handle_error("Failed to upgrade packages.")

    log("INFO", "Installing required dependencies...")
    apt_install_cmd = [
        "sudo", "apt-get", "install", "-y", "build-essential", "git", "curl",
        "wget", "vim", "tmux", "unzip", "zip", "ca-certificates",
        "libssl-dev", "libffi-dev", "zlib1g-dev", "libbz2-dev", "libreadline-dev",
        "libsqlite3-dev", "libncurses5-dev", "libgdbm-dev", "libnss3-dev",
        "liblzma-dev", "xz-utils", "libxml2-dev", "libxmlsec1-dev", "tk-dev",
        "llvm", "gnupg", "lsb-release", "jq"
    ]
    try:
        subprocess.run(apt_install_cmd, check=True)
    except subprocess.CalledProcessError:
        handle_error("Failed to install required dependencies.")

    log("INFO", "Cleaning up package caches...")
    try:
        subprocess.run(["sudo", "apt-get", "clean"], check=True)
    except subprocess.CalledProcessError:
        log("WARN", "Failed to clean package caches.")

# ------------------------------------------------------------------------------
# FUNCTION: Install or Update pyenv
# ------------------------------------------------------------------------------
def install_or_update_pyenv():
    print_section("pyenv Installation/Update")
    if not os.path.isdir(PYENV_ROOT):
        log("INFO", "pyenv not found. Installing pyenv...")
        try:
            subprocess.run(["git", "clone", "https://github.com/pyenv/pyenv.git", PYENV_ROOT], check=True)
        except subprocess.CalledProcessError:
            handle_error("Failed to clone pyenv.")

        bashrc = os.path.join(HOME, ".bashrc")
        try:
            with open(bashrc, "r") as f:
                content = f.read()
        except Exception:
            content = ""
        if "export PYENV_ROOT" not in content:
            log("INFO", "Adding pyenv initialization to ~/.bashrc...")
            init_block = (
                "\n# >>> pyenv initialization >>>\n"
                'export PYENV_ROOT="$HOME/.pyenv"\n'
                'export PATH="$PYENV_ROOT/bin:$PATH"\n'
                'if command -v pyenv 1>/dev/null 2>&1; then\n'
                '    eval "$(pyenv init -)"\n'
                'fi\n'
                "# <<< pyenv initialization <<<\n"
            )
            try:
                with open(bashrc, "a") as f:
                    f.write(init_block)
            except Exception as e:
                log("WARN", f"Failed to update ~/.bashrc: {e}")
    else:
        log("INFO", "pyenv is already installed. Updating pyenv...")
        try:
            subprocess.run(["git", "pull", "--ff-only"], cwd=PYENV_ROOT, check=True)
        except subprocess.CalledProcessError:
            handle_error("Failed to update pyenv.")

    # Ensure pyenv is available in this session.
    os.environ["PYENV_ROOT"] = PYENV_ROOT
    os.environ["PATH"] = os.path.join(PYENV_ROOT, "bin") + os.pathsep + os.environ.get("PATH", "")

# ------------------------------------------------------------------------------
# FUNCTION: Install the Latest Stable Python via pyenv
# ------------------------------------------------------------------------------
def install_latest_python() -> bool:
    print_section("Python Installation via pyenv")
    log("INFO", "Searching for the latest stable Python 3.x version via pyenv...")
    try:
        result = subprocess.run(["pyenv", "install", "-l"], capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
    except subprocess.CalledProcessError:
        handle_error("Failed to determine available Python versions from pyenv.")

    latest_py3 = None
    pattern = re.compile(r"^\s*(3\.\d+\.\d+)$")
    for line in lines:
        match = pattern.match(line)
        if match:
            latest_py3 = match.group(1)  # the last matching version
    if not latest_py3:
        handle_error("Could not determine the latest Python 3.x version from pyenv.")

    try:
        result = subprocess.run(["pyenv", "global"], capture_output=True, text=True)
        current_py3 = result.stdout.strip()
    except Exception:
        current_py3 = ""

    log("INFO", f"Latest Python 3.x version available: {latest_py3}")
    log("INFO", f"Currently active pyenv Python version: {current_py3 if current_py3 else 'None'}")

    new_python_installed = False
    if current_py3 != latest_py3:
        try:
            result = subprocess.run(["pyenv", "versions", "--bare"], capture_output=True, text=True, check=True)
            versions = result.stdout.splitlines()
        except subprocess.CalledProcessError:
            versions = []
        if latest_py3 not in versions:
            log("INFO", f"Installing Python {latest_py3} via pyenv...")
            try:
                subprocess.run(["pyenv", "install", latest_py3], check=True)
            except subprocess.CalledProcessError:
                handle_error(f"Failed to install Python {latest_py3}.")
        log("INFO", f"Setting Python {latest_py3} as the global version...")
        try:
            subprocess.run(["pyenv", "global", latest_py3], check=True)
        except subprocess.CalledProcessError:
            handle_error(f"Failed to set Python {latest_py3} as global.")
        new_python_installed = True
    else:
        log("INFO", f"Python {latest_py3} is already installed and set as global.")

    # Refresh shell environment (if needed)
    try:
        subprocess.run(["pyenv", "init", "-"], check=True)
    except subprocess.CalledProcessError:
        pass

    return new_python_installed

# ------------------------------------------------------------------------------
# Print a styled section header using Nord accent colors
# ------------------------------------------------------------------------------
def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    parse_args(sys.argv[1:])
    check_non_root()

    log("INFO", "Starting Ubuntu Python setup script...")

    # 1. Install APT-based dependencies.
    install_apt_dependencies()

    # 2. Install or update pyenv.
    install_or_update_pyenv()

    # 3. Install the latest Python via pyenv (if needed).
    new_python_installed = install_latest_python()

    log("INFO", "=================================================")
    log("INFO", " SUCCESS! Your system is now configured with:")
    log("INFO", "   - The latest stable Python installed via pyenv")
    log("INFO", "=================================================")
    log("INFO", "Happy coding!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        handle_error(f"Unhandled exception: {e}", exit_code=1, func="main")