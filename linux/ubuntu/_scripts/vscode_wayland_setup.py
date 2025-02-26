#!/usr/bin/env python3
"""
Script Name: vscode_wayland_setup.py
--------------------------------------------------------
Description:
  A robust, visually engaging script to install/update Visual Studio Code Stable
  and modify its desktop shortcut for Wayland support. The script will:
  
  - Download the latest VS Code stable .deb package
  - Install the package (fixing dependencies if necessary)
  - Configure VS Code to run natively on Wayland by modifying desktop entries
  - Create a local user copy of the desktop entry to survive updates

Usage:
  sudo ./vscode_wayland_setup.py

Author: YourName | License: MIT | Version: 1.0.0
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
LOG_FILE = "/var/log/vscode_wayland_setup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# VS Code Configuration
VSCODE_URL = "https://vscode.download.prss.microsoft.com/dbazure/download/stable/e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
VSCODE_DEB_PATH = "/tmp/code.deb"
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0  = '\033[38;2;46;52;64m'     # Polar Night (dark)
NORD1  = '\033[38;2;59;66;82m'     # Polar Night (darker than NORD0)
NORD8  = '\033[38;2;136;192;208m'  # Frost (light blue)
NORD9  = '\033[38;2;129;161;193m'  # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'   # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'   # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'  # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

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

        if levelname == 'DEBUG':
            return f"{NORD9}{msg}{NC}"
        elif levelname == 'INFO':
            return f"{NORD14}{msg}{NC}"
        elif levelname == 'WARNING':
            return f"{NORD13}{msg}{NC}"
        elif levelname in ('ERROR', 'CRITICAL'):
            return f"{NORD11}{msg}{NC}"
        return msg

def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
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
    # Remove the temporary .deb file if it exists
    if os.path.exists(VSCODE_DEB_PATH):
        try:
            os.remove(VSCODE_DEB_PATH)
            logging.debug(f"Removed temporary file: {VSCODE_DEB_PATH}")
        except Exception as e:
            logging.warning(f"Failed to remove temporary file {VSCODE_DEB_PATH}: {e}")

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------

def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["curl", "dpkg", "apt"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(f"The '{cmd}' command is not found in your PATH. Please install it and try again.")
            sys.exit(1)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------

def check_root():
    """
    Ensure the script is run with root privileges for system-wide changes.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root for system-wide installation.")
        sys.exit(1)

def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    """
    Execute a shell command with proper logging.
    
    Args:
        cmd: Command to execute (list or string)
        check: Whether to check return code
        capture_output: Whether to capture stdout/stderr
        text: Whether to return text or bytes
        **kwargs: Additional arguments for subprocess.run
        
    Returns:
        CompletedProcess object
    """
    command_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    logging.debug(f"Executing command: {command_str}")
    
    try:
        result = subprocess.run(
            cmd, 
            check=check, 
            capture_output=capture_output, 
            text=text, 
            **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e}")
        if check:
            raise
        return e

# ------------------------------------------------------------------------------
# VS CODE INSTALLATION AND CONFIGURATION FUNCTIONS
# ------------------------------------------------------------------------------

def download_vscode():
    """
    Download the Visual Studio Code .deb package.
    """
    print_section("Downloading Visual Studio Code")
    logging.info(f"Downloading VS Code from: {VSCODE_URL}")
    
    try:
        run_command(["curl", "-L", "-o", VSCODE_DEB_PATH, VSCODE_URL])
        logging.info("Download completed successfully.")
        
        # Verify file exists and has content
        if os.path.exists(VSCODE_DEB_PATH) and os.path.getsize(VSCODE_DEB_PATH) > 0:
            file_size_mb = os.path.getsize(VSCODE_DEB_PATH) / (1024 * 1024)
            logging.info(f"Downloaded file size: {file_size_mb:.2f} MB")
            return True
        else:
            logging.error("Downloaded file is empty or doesn't exist.")
            return False
    except Exception as e:
        logging.error(f"Failed to download VS Code: {e}")
        return False

def install_vscode():
    """
    Install the downloaded Visual Studio Code .deb package.
    """
    print_section("Installing Visual Studio Code")
    logging.info("Installing VS Code package...")
    
    try:
        run_command(["dpkg", "-i", VSCODE_DEB_PATH])
        logging.info("VS Code installed successfully with dpkg.")
        return True
    except subprocess.CalledProcessError:
        logging.warning("Initial installation failed. Attempting to fix dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
            logging.info("Dependencies fixed. VS Code should now be installed.")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to fix dependencies: {e}")
            return False

def create_system_desktop_file():
    """
    Create or update the system-wide desktop entry for VS Code with Wayland support.
    """
    print_section("Configuring System Desktop Entry")
    logging.info(f"Creating system-wide desktop file at: {SYSTEM_DESKTOP_PATH}")
    
    desktop_content = """[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
GenericName=Text Editor
Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=TextEditor;Development;IDE;
MimeType=application/x-code-workspace;
Actions=new-empty-window;
Keywords=vscode;

[Desktop Action new-empty-window]
Name=New Empty Window
Name[de]=Neues leeres Fenster
Name[es]=Nueva ventana vacía
Name[fr]=Nouvelle fenêtre vide
Name[it]=Nuova finestra vuota
Name[ja]=新しい空のウィンドウ
Name[ko]=새 빈 창
Name[ru]=Новое пустое окно
Name[zh_CN]=新建空窗口
Name[zh_TW]=開新空視窗
Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
"""
    
    try:
        with open(SYSTEM_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)
        logging.info("System desktop entry created/updated successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to create system desktop entry: {e}")
        return False

def create_user_desktop_file():
    """
    Create a user-local copy of the desktop entry to survive system updates.
    """
    print_section("Creating User Desktop Entry")
    logging.info(f"Creating user-local desktop file at: {USER_DESKTOP_PATH}")
    
    # Create local applications directory if it doesn't exist
    try:
        os.makedirs(USER_DESKTOP_DIR, exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create local applications directory: {e}")
        return False
    
    # Copy system desktop file to user directory
    try:
        shutil.copy2(SYSTEM_DESKTOP_PATH, USER_DESKTOP_PATH)
        logging.info("Desktop file copied to user directory.")
    except Exception as e:
        logging.error(f"Failed to copy desktop file to user directory: {e}")
        return False
    
    # Modify the local desktop file
    try:
        with open(USER_DESKTOP_PATH, "r") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if line.startswith("Exec="):
                if "new-window" in line:
                    new_lines.append("Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n")
                else:
                    new_lines.append("Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n")
            elif line.startswith("StartupWMClass="):
                new_lines.append("StartupWMClass=code\n")
            else:
                new_lines.append(line)
        
        with open(USER_DESKTOP_PATH, "w") as f:
            f.writelines(new_lines)
        
        # Set proper permissions
        os.chmod(USER_DESKTOP_PATH, 0o644)
        
        logging.info("User desktop entry modified for Wayland compatibility.")
        return True
    except Exception as e:
        logging.error(f"Failed to modify user desktop entry: {e}")
        return False

def verify_installation():
    """
    Verify that VS Code is installed and properly configured.
    """
    print_section("Verifying Installation")
    
    # Check if VS Code binary exists
    vscode_binary = "/usr/share/code/code"
    if not os.path.exists(vscode_binary):
        logging.warning(f"VS Code binary not found at expected path: {vscode_binary}")
        return False
    
    # Check if desktop files exist
    if not os.path.exists(SYSTEM_DESKTOP_PATH):
        logging.warning(f"System desktop entry not found at: {SYSTEM_DESKTOP_PATH}")
    else:
        logging.info(f"System desktop entry exists at: {SYSTEM_DESKTOP_PATH}")
    
    if not os.path.exists(USER_DESKTOP_PATH):
        logging.warning(f"User desktop entry not found at: {USER_DESKTOP_PATH}")
    else:
        logging.info(f"User desktop entry exists at: {USER_DESKTOP_PATH}")
    
    # Check if the Wayland flags are in the desktop file
    if os.path.exists(USER_DESKTOP_PATH):
        try:
            with open(USER_DESKTOP_PATH, "r") as f:
                content = f.read()
            
            if "--ozone-platform=wayland" in content:
                logging.info("Wayland flags correctly set in desktop entry.")
            else:
                logging.warning("Wayland flags not found in desktop entry.")
        except Exception as e:
            logging.warning(f"Could not verify desktop entry content: {e}")
    
    logging.info("VS Code with Wayland support should now be installed and configured.")
    return True

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for the script.
    """
    # Ensure the script is run with the right permissions
    check_root()
    
    # Setup logging
    setup_logging()
    check_dependencies()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"VS CODE WAYLAND SETUP STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main functions
    if download_vscode():
        if install_vscode():
            create_system_desktop_file()
            create_user_desktop_file()
            verify_installation()
        else:
            logging.error("VS Code installation failed. Cannot continue with configuration.")
            sys.exit(1)
    else:
        logging.error("Failed to download VS Code. Cannot continue with installation.")
        sys.exit(1)
    
    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"VS CODE WAYLAND SETUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)
    logging.info("You can now launch VS Code from your application menu.")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)