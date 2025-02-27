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

import os
import sys
import grp
import pwd

# Default folder to fix permissions for
DEFAULT_FOLDERS = ["/var/lib/libvirt/images"]

# Desired settings:
# - Owner: root
# - Group: libvirt-qemu (this is the group typically used by QEMU processes on Ubuntu)
# - Directories: mode 2770 (rwxrws---)
# - Files: mode 0660 (rw-rw----)
OWNER = "root"
GROUP = "libvirt-qemu"
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


def ensure_libvirt_membership() -> None:
    """
    Ensure that the invoking user (via SUDO_USER) is a member of the 'libvirt' group.

    If not, attempt to add the user to the group.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print(
            "Warning: SUDO_USER not found; cannot determine invoking user. Skipping group membership check."
        )
        return

    try:
        user_info = pwd.getpwnam(sudo_user)
    except KeyError:
        print(f"User {sudo_user} not found. Skipping group membership check.")
        return

    # Build a list of groups the user is a member of
    groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary_group = grp.getgrgid(user_info.pw_gid).gr_name
    if primary_group not in groups:
        groups.append(primary_group)

    # virt-manager typically requires membership in the 'libvirt' group.
    target_group = "libvirt"
    if target_group in groups:
        print(f"{sudo_user} is already a member of the '{target_group}' group.")
    else:
        print(
            f"{sudo_user} is not a member of the '{target_group}' group. Attempting to add..."
        )
        result = os.system(f"usermod -a -G {target_group} {sudo_user}")
        if result == 0:
            print(f"Successfully added {sudo_user} to the '{target_group}' group.")
        else:
            print(
                f"Failed to add {sudo_user} to the '{target_group}' group. Please add manually."
            )


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

    # Ensure the invoking user is in the libvirt group for management access
    ensure_libvirt_membership()

    print(
        "\nPermissions have been fixed. Ensure that users running virt-manager are in the 'libvirt' group for management access."
    )


if __name__ == "__main__":
    main()
