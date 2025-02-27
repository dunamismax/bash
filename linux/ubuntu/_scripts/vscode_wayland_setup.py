#!/usr/bin/env python3
"""
VS Code Wayland Setup Script

This script installs and configures Visual Studio Code with Wayland support.
It downloads the VS Code .deb package, installs it (attempting to fix dependencies if needed),
creates desktop entries with Wayland-specific options, and verifies the installation.

Usage:
  sudo python3 vscode_wayland_setup.py

Author: Anonymous | License: MIT | Version: 1.0.0
"""

import argparse
import datetime
import logging
import os
import shutil
import signal
import subprocess
import sys
import urllib.request
from typing import Optional

#####################################
# Configuration Constants
#####################################

# URL for the VS Code .deb package (update as needed)
VSCODE_URL = "https://vscode.download.prss.microsoft.com/dbazure/download/stable/e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
VSCODE_DEB_PATH = "/tmp/code.deb"

# Desktop entry paths
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")

# Log file
LOG_FILE = "/var/log/vscode_wayland_setup.log"

#####################################
# ANSI Colors (Nord-Themed)
#####################################


class Colors:
    """ANSI color codes for Nord themed output"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    ENDC = "\033[0m"


#####################################
# Helper Functions for UI
#####################################


def print_header(message: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {title}{Colors.ENDC}\n")


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging to both a file and the console.
    The log file is secured with appropriate permissions.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    # File handler for log file
    file_handler = logging.FileHandler(LOG_FILE, mode="a")
    file_handler.setFormatter(formatter)

    # Stream handler for console output
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[file_handler, stream_handler])

    # Secure log file permissions
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(
            f"{Colors.YELLOW}Could not set log file permissions: {e}{Colors.ENDC}"
        )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install and configure Visual Studio Code with Wayland support."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging output"
    )
    return parser.parse_args()


#####################################
# Validation and Environment Checks
#####################################


def check_root() -> None:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error(f"{Colors.RED}This script must be run as root.{Colors.ENDC}")
        sys.exit(1)


def check_dependencies() -> None:
    """Verify that required system commands are available."""
    required_commands = ["curl", "dpkg", "nala"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"{Colors.RED}Required command '{cmd}' is missing.{Colors.ENDC}"
            )
            sys.exit(1)


#####################################
# Progress Tracking for Download
#####################################


def download_progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    """
    Report hook for urllib.request.urlretrieve.

    Displays a dynamic progress bar using ANSI colors.
    """
    downloaded = block_num * block_size
    percent = downloaded / total_size * 100 if total_size > 0 else 0
    bar_length = 50
    filled_length = int(bar_length * downloaded // total_size) if total_size > 0 else 0
    bar = f"{Colors.GREEN}{'█' * filled_length}{Colors.ENDC}{'-' * (bar_length - filled_length)}"
    sys.stdout.write(
        f"\r{Colors.CYAN}Downloading:{Colors.ENDC} |{bar}| {percent:6.2f}%"
    )
    sys.stdout.flush()
    if downloaded >= total_size:
        sys.stdout.write("\n")


#####################################
# Installation Step Functions
#####################################


def download_vscode() -> bool:
    """
    Download the VS Code .deb package using urllib.

    Returns:
        bool: True if download succeeds, False otherwise.
    """
    print_section("Downloading Visual Studio Code")
    try:
        logging.info(f"Starting download from: {VSCODE_URL}")
        urllib.request.urlretrieve(
            VSCODE_URL, VSCODE_DEB_PATH, reporthook=download_progress_hook
        )
        if os.path.exists(VSCODE_DEB_PATH) and os.path.getsize(VSCODE_DEB_PATH) > 0:
            file_size_mb = os.path.getsize(VSCODE_DEB_PATH) / (1024 * 1024)
            logging.info(f"Download completed. File size: {file_size_mb:.2f} MB")
            return True
        else:
            logging.error(
                f"{Colors.RED}Downloaded file is empty or missing.{Colors.ENDC}"
            )
            return False
    except Exception as e:
        logging.error(f"{Colors.RED}Download failed: {e}{Colors.ENDC}")
        return False


def install_vscode() -> bool:
    """
    Install the downloaded VS Code .deb package.

    Returns:
        bool: True if installation (or dependency fix) succeeds, False otherwise.
    """
    print_section("Installing Visual Studio Code")
    try:
        subprocess.run(["dpkg", "-i", VSCODE_DEB_PATH], check=True)
        logging.info(f"{Colors.GREEN}VS Code installed successfully.{Colors.ENDC}")
        return True
    except subprocess.CalledProcessError:
        logging.warning(
            f"{Colors.YELLOW}Initial installation failed, attempting to fix dependencies...{Colors.ENDC}"
        )
        try:
            subprocess.run(["nala", "install", "-f", "-y"], check=True)
            logging.info(
                f"{Colors.GREEN}Dependencies fixed. VS Code installation should now be complete.{Colors.ENDC}"
            )
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"{Colors.RED}Failed to fix dependencies: {e}{Colors.ENDC}")
            return False


def create_wayland_desktop_file() -> bool:
    """
    Create and install desktop entries with Wayland support.

    Returns:
        bool: True if desktop entries are created successfully, False otherwise.
    """
    print_section("Configuring Desktop Entry")
    desktop_content = (
        "[Desktop Entry]\n"
        "Name=Visual Studio Code\n"
        "Comment=Code Editing. Redefined.\n"
        "GenericName=Text Editor\n"
        "Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
        "Icon=vscode\n"
        "Type=Application\n"
        "StartupNotify=false\n"
        "StartupWMClass=Code\n"
        "Categories=TextEditor;Development;IDE;\n"
        "MimeType=application/x-code-workspace;\n"
    )
    try:
        # Write system-wide desktop entry
        with open(SYSTEM_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)
        # Ensure the user desktop directory exists
        os.makedirs(USER_DESKTOP_DIR, exist_ok=True)
        # Copy system desktop file to user desktop directory
        shutil.copy2(SYSTEM_DESKTOP_PATH, USER_DESKTOP_PATH)
        logging.info(
            f"{Colors.GREEN}Desktop entries created successfully.{Colors.ENDC}"
        )
        return True
    except Exception as e:
        logging.error(f"{Colors.RED}Failed to create desktop entries: {e}{Colors.ENDC}")
        return False


def verify_installation() -> bool:
    """
    Verify that VS Code and the desktop entries have been installed.

    Returns:
        bool: True if all expected files are present, False otherwise.
    """
    print_section("Verifying Installation")
    checks = [
        ("/usr/share/code/code", "VS Code binary"),
        (SYSTEM_DESKTOP_PATH, "System desktop entry"),
        (USER_DESKTOP_PATH, "User desktop entry"),
    ]
    all_ok = True
    for path, description in checks:
        if os.path.exists(path):
            logging.info(f"{description} found at: {path}")
        else:
            logging.warning(
                f"{Colors.YELLOW}{description} not found at: {path}{Colors.ENDC}"
            )
            all_ok = False
    return all_ok


#####################################
# Signal Handling and Cleanup
#####################################


def setup_signal_handlers() -> None:
    """Setup handlers for graceful shutdown on SIGINT and SIGTERM."""
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(143))


def cleanup() -> None:
    """Remove temporary files created during installation."""
    try:
        if os.path.exists(VSCODE_DEB_PATH):
            os.unlink(VSCODE_DEB_PATH)
            logging.info("Cleaned up temporary files.")
    except Exception as e:
        logging.warning(f"Cleanup failed: {e}")


#####################################
# Main Execution Flow
#####################################


def main() -> None:
    """Main function to execute the VS Code Wayland setup workflow."""
    args = parse_arguments()
    setup_signal_handlers()
    check_root()
    setup_logging(verbose=args.verbose)
    check_dependencies()

    start_time = datetime.datetime.now()
    print_header("VS CODE WAYLAND SETUP")
    logging.info("=" * 60)
    logging.info(f"Setup started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 60)

    # Execute installation steps
    success = (
        download_vscode()
        and install_vscode()
        and create_wayland_desktop_file()
        and verify_installation()
    )

    end_time = datetime.datetime.now()
    logging.info("=" * 60)
    status = "COMPLETED" if success else "FAILED"
    logging.info(
        f"VS CODE WAYLAND SETUP {status} at {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info("=" * 60)

    cleanup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
