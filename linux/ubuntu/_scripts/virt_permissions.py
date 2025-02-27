#!/usr/bin/env python3
"""
Fix Virtual Machine Folder Permissions and Ensure Correct Group Membership for virt-manager on Ubuntu

This script recursively fixes the permissions on common virtual machine folders so that
QEMU/libvirt can access storage files by setting ownership to root:libvirt-qemu, with directories
at mode 2770 (setgid bit included) and files at mode 0660. Additionally, it checks whether the
invoking user (via SUDO_USER) is a member of the 'libvirt' group. If not, it attempts to add the user
to that group.

Usage:
    Run this script as root.
    Optionally, pass one or more folder paths as arguments.
    If no paths are provided, the default folder '/var/lib/libvirt/images' is used.
"""

import argparse
import logging
import os
import sys
import grp
import pwd
import signal
from typing import List

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    """Nord-themed ANSI color codes."""

    HEADER = "\033[38;5;81m"  # Nord9
    GREEN = "\033[38;5;82m"  # Nord14
    YELLOW = "\033[38;5;226m"  # Nord13
    RED = "\033[38;5;196m"  # Nord11
    BLUE = "\033[38;5;39m"  # Nord8
    BOLD = "\033[1m"
    ENDC = "\033[0m"


def print_header(title: str) -> None:
    """Print a formatted header."""
    border = f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}"
    logging.info(border)
    logging.info(f"{Colors.BOLD}{title}{Colors.ENDC}")
    logging.info(border)


#####################################
# Configuration
#####################################

DEFAULT_FOLDERS: List[str] = ["/var/lib/libvirt/images"]

OWNER: str = "root"
GROUP: str = "libvirt-qemu"
DIR_MODE: int = 0o2770  # Directories: rwxrws---
FILE_MODE: int = 0o0660  # Files: rw-rw----

#####################################
# Logging Setup
#####################################


def setup_logging() -> None:
    """Configure logging to the console with Nord-themed ANSI colors."""
    logging.basicConfig(
        level=logging.INFO,
        format=f"{Colors.BOLD}[%(asctime)s] [%(levelname)s]{Colors.ENDC} %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


#####################################
# Signal Handling
#####################################


def handle_signal(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Received {sig_name}. Exiting gracefully.")
    sys.exit(1)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, handle_signal)

#####################################
# Helper Functions
#####################################


def check_root() -> None:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def get_uid(username: str) -> int:
    """Return the UID for the given username."""
    try:
        return pwd.getpwnam(username).pw_uid
    except KeyError:
        logging.error(f"User '{username}' not found.")
        sys.exit(1)


def get_gid(groupname: str) -> int:
    """Return the GID for the given group name."""
    try:
        return grp.getgrnam(groupname).gr_gid
    except KeyError:
        logging.error(f"Group '{groupname}' not found.")
        sys.exit(1)


def fix_permissions(path: str, uid: int, gid: int) -> None:
    """
    Recursively fix ownership and permissions on the given path.

    Directories are set to DIR_MODE and files to FILE_MODE.
    Ownership is set to uid:gid.
    """
    if not os.path.exists(path):
        logging.error(f"Path not found: {path}")
        return

    for root, dirs, files in os.walk(path):
        try:
            os.chown(root, uid, gid)
            os.chmod(root, DIR_MODE)
            logging.info(f"Fixed directory: {root}")
        except Exception as e:
            logging.error(f"Error processing directory {root}: {e}")
        for name in files:
            file_path = os.path.join(root, name)
            try:
                os.chown(file_path, uid, gid)
                os.chmod(file_path, FILE_MODE)
                logging.info(f"Fixed file: {file_path}")
            except Exception as e:
                logging.error(f"Error processing file {file_path}: {e}")


def ensure_libvirt_membership() -> None:
    """
    Ensure that the invoking user (via SUDO_USER) is a member of the 'libvirt' group.
    If not, attempt to add the user to that group.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        logging.warning(
            "SUDO_USER not found; cannot determine invoking user. Skipping group membership check."
        )
        return

    try:
        user_info = pwd.getpwnam(sudo_user)
    except KeyError:
        logging.warning(
            f"User '{sudo_user}' not found. Skipping group membership check."
        )
        return

    # Build a list of groups the user is a member of
    groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary_group = grp.getgrgid(user_info.pw_gid).gr_name
    if primary_group not in groups:
        groups.append(primary_group)

    target_group = "libvirt"
    if target_group in groups:
        logging.info(f"{sudo_user} is already a member of the '{target_group}' group.")
    else:
        logging.info(
            f"{sudo_user} is not a member of the '{target_group}' group. Attempting to add..."
        )
        result = os.system(f"usermod -a -G {target_group} {sudo_user}")
        if result == 0:
            logging.info(
                f"Successfully added {sudo_user} to the '{target_group}' group."
            )
        else:
            logging.error(
                f"Failed to add {sudo_user} to the '{target_group}' group. Please add manually."
            )


#####################################
# Main Execution Flow
#####################################


def main() -> None:
    setup_logging()
    check_root()
    uid: int = get_uid(OWNER)
    gid: int = get_gid(GROUP)

    # Parse folder arguments; default to DEFAULT_FOLDERS if none provided.
    parser = argparse.ArgumentParser(
        description="Fix VM Folder Permissions and Ensure libvirt Group Membership for virt-manager."
    )
    parser.add_argument(
        "folders",
        nargs="*",
        default=DEFAULT_FOLDERS,
        help=f"Folder paths to fix permissions (default: {DEFAULT_FOLDERS})",
    )
    args = parser.parse_args()

    logging.info("Starting permission fixes on virtual machine folders...\n")
    for folder in args.folders:
        logging.info(f"Processing folder: {folder}")
        fix_permissions(folder, uid, gid)

    # Ensure the invoking user is in the 'libvirt' group for proper management access.
    ensure_libvirt_membership()

    logging.info(
        "\nPermissions have been fixed. Ensure that users running virt-manager are in the 'libvirt' group for management access."
    )


if __name__ == "__main__":
    main()
