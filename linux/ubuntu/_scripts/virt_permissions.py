#!/usr/bin/env python3
"""
Fix Virtual Machine Folder Permissions for virt-manager on Ubuntu

This script fixes the permissions on common virtual machine folders so that
virt-manager (when run by users in the 'libvirt' group) has full access.
It recursively changes the ownership to root:libvirt and sets directory and file
permissions appropriately.

Usage:
    Run this script as root.
    Optionally, pass one or more folder paths as arguments.
    If no paths are provided, the default folder '/var/lib/libvirt/images' is used.
"""

import os
import sys
import grp
import pwd
import stat

DEFAULT_FOLDERS = ["/var/lib/libvirt/images"]

# Desired settings:
# - Owner: root (uid 0)
# - Group: libvirt
# - Directories: set to 2770 (setgid bit included)
# - Files: set to 0660
OWNER = "root"
GROUP = "libvirt"
DIR_MODE = 0o2770
FILE_MODE = 0o0660


def check_root() -> None:
    """Ensure the script is run with root privileges."""
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)


def get_uid(username: str) -> int:
    """Return the UID for the given username."""
    try:
        return pwd.getpwnam(username).pw_uid
    except KeyError:
        print(f"User '{username}' not found.")
        sys.exit(1)


def get_gid(groupname: str) -> int:
    """Return the GID for the given group name."""
    try:
        return grp.getgrnam(groupname).gr_gid
    except KeyError:
        print(f"Group '{groupname}' not found.")
        sys.exit(1)


def fix_permissions(path: str, uid: int, gid: int) -> None:
    """
    Recursively fix ownership and permissions on the given path.

    Directories are set to DIR_MODE and files to FILE_MODE.
    Ownership is set to uid:gid.
    """
    if not os.path.exists(path):
        print(f"Path not found: {path}")
        return

    for root, dirs, files in os.walk(path):
        try:
            os.chown(root, uid, gid)
            os.chmod(root, DIR_MODE)
            print(f"Fixed directory: {root}")
        except Exception as e:
            print(f"Error processing directory {root}: {e}")

        for name in files:
            file_path = os.path.join(root, name)
            try:
                os.chown(file_path, uid, gid)
                os.chmod(file_path, FILE_MODE)
                print(f"Fixed file: {file_path}")
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")


def main() -> None:
    check_root()

    uid = get_uid(OWNER)
    gid = get_gid(GROUP)

    # Use command-line arguments if provided, else default folder(s)
    folders = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_FOLDERS

    print("Starting permission fixes on virtual machine folders...\n")
    for folder in folders:
        print(f"Processing folder: {folder}")
        fix_permissions(folder, uid, gid)

    print(
        "\nPermissions have been fixed. Ensure that users running virt-manager are in the 'libvirt' group for full access."
    )


if __name__ == "__main__":
    main()
