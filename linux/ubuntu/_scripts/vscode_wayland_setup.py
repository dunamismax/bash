#!/usr/bin/env python3
"""
VS Code Wayland Setup Script

Installs and configures Visual Studio Code with Wayland support.

Usage:
  sudo python3 vscode_wayland_setup.py

Author: Anonymous | License: MIT | Version: 1.0.0
"""

import os
import sys
import logging
import urllib.request
import subprocess
import shutil
import signal
import tempfile
from datetime import datetime


# Configuration Constants
VSCODE_URL = "https://vscode.download.prss.microsoft.com/dbazure/download/stable/e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
VSCODE_DEB_PATH = "/tmp/code.deb"
SYSTEM_DESKTOP_PATH = "/usr/share/applications/code.desktop"
USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
USER_DESKTOP_PATH = os.path.join(USER_DESKTOP_DIR, "code.desktop")
LOG_FILE = "/var/log/vscode_wayland_setup.log"


def setup_logging():
    """Configure logging to console and file."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Secure log file permissions
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


def print_section(title):
    """Print a section header."""
    logging.info("-" * 60)
    logging.info(f"  {title}")
    logging.info("-" * 60)


def check_root():
    """Verify script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def check_dependencies():
    """Check for required system commands."""
    required_commands = ["curl", "dpkg", "apt"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(f"Required command '{cmd}' is missing.")
            sys.exit(1)


def download_vscode():
    """Download VS Code .deb package."""
    print_section("Downloading Visual Studio Code")
    try:
        logging.info(f"Downloading from: {VSCODE_URL}")
        urllib.request.urlretrieve(VSCODE_URL, VSCODE_DEB_PATH)

        if os.path.exists(VSCODE_DEB_PATH) and os.path.getsize(VSCODE_DEB_PATH) > 0:
            file_size_mb = os.path.getsize(VSCODE_DEB_PATH) / (1024 * 1024)
            logging.info(f"Download completed. File size: {file_size_mb:.2f} MB")
            return True
        else:
            logging.error("Downloaded file is empty or missing.")
            return False
    except Exception as e:
        logging.error(f"Download failed: {e}")
        return False


def install_vscode():
    """Install VS Code .deb package."""
    print_section("Installing Visual Studio Code")
    try:
        # Attempt initial installation
        subprocess.run(["dpkg", "-i", VSCODE_DEB_PATH], check=True)
        logging.info("VS Code installed successfully.")
        return True
    except subprocess.CalledProcessError:
        try:
            # Try to fix dependencies
            logging.warning("Fixing dependencies...")
            subprocess.run(["apt", "install", "-f", "-y"], check=True)
            logging.info("Dependencies fixed. VS Code should now be installed.")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to fix dependencies: {e}")
            return False


def create_wayland_desktop_file():
    """Create desktop entry with Wayland support."""
    print_section("Configuring Desktop Entry")

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
"""

    try:
        # Create system-wide desktop entry
        with open(SYSTEM_DESKTOP_PATH, "w") as f:
            f.write(desktop_content)

        # Ensure local applications directory exists
        os.makedirs(USER_DESKTOP_DIR, exist_ok=True)

        # Copy to user desktop directory
        shutil.copy2(SYSTEM_DESKTOP_PATH, USER_DESKTOP_PATH)

        logging.info("Desktop entries created successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to create desktop entries: {e}")
        return False


def verify_installation():
    """Verify VS Code installation and configuration."""
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
            logging.warning(f"{description} not found at: {path}")
            all_ok = False

    return all_ok


def main():
    """Main script execution."""
    # Set up signal handling
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(130))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(143))

    # Initialization
    check_root()
    setup_logging()
    check_dependencies()

    # Log start time
    start_time = datetime.now()
    logging.info("=" * 60)
    logging.info(f"VS CODE WAYLAND SETUP STARTED AT {start_time}")
    logging.info("=" * 60)

    # Perform installation steps
    success = (
        download_vscode()
        and install_vscode()
        and create_wayland_desktop_file()
        and verify_installation()
    )

    # Log completion
    end_time = datetime.now()
    logging.info("=" * 60)
    logging.info(
        f"VS CODE WAYLAND SETUP {'COMPLETED' if success else 'FAILED'} AT {end_time}"
    )
    logging.info("=" * 60)

    # Clean up temporary file
    try:
        os.unlink(VSCODE_DEB_PATH)
    except Exception:
        pass

    # Exit with appropriate status
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
