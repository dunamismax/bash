#!/usr/bin/env python3

import os
import subprocess
import sys
from typing import List, Tuple

# Configuration constants (matching the installation script)
DEFAULT_INSTALL_DIR = "/var/www/nextcloud"
DEFAULT_DATA_DIR = "/var/www/nextcloud/data"
DEFAULT_DB_NAME = "nextcloud"
DEFAULT_DB_USER = "nextcloud"
DEFAULT_WEB_USER = "www-data"


def print_step(message: str) -> None:
    """Print a step in the uninstallation process."""
    print(f"→ {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"✗ {message}")


def run_command(cmd: List[str], sudo: bool = False) -> Tuple[int, str, str]:
    """Run a command and return the return code, stdout, and stderr."""
    try:
        if sudo and os.geteuid() != 0:
            cmd = ["sudo"] + cmd

        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        print_error(f"Command failed: {e}")
        return 1, "", str(e)


def confirm(message: str) -> bool:
    """Confirm an action with the user."""
    response = input(f"{message} (y/n): ").lower()
    return response == "y" or response == "yes"


def remove_nextcloud_files() -> bool:
    """Remove Nextcloud files and data directory."""
    print_step("Removing Nextcloud files...")

    # Check if directories exist
    install_dir = (
        input(f"Enter Nextcloud installation directory [{DEFAULT_INSTALL_DIR}]: ")
        or DEFAULT_INSTALL_DIR
    )
    data_dir = (
        input(f"Enter Nextcloud data directory [{DEFAULT_DATA_DIR}]: ")
        or DEFAULT_DATA_DIR
    )

    if not os.path.exists(install_dir) and not os.path.exists(data_dir):
        print_error("Nextcloud directories not found. Nothing to remove.")
        return False

    if confirm(
        f"This will permanently delete all Nextcloud files in {install_dir} and data in {data_dir}. Continue?"
    ):
        # Remove installation directory
        if os.path.exists(install_dir):
            returncode, _, stderr = run_command(["rm", "-rf", install_dir], sudo=True)
            if returncode != 0:
                print_error(f"Failed to remove installation directory: {stderr}")
                return False
            print_success(f"Removed Nextcloud installation directory: {install_dir}")

        # Remove data directory if it's different from the installation directory
        if (
            os.path.exists(data_dir)
            and data_dir != install_dir
            and not data_dir.startswith(install_dir)
        ):
            returncode, _, stderr = run_command(["rm", "-rf", data_dir], sudo=True)
            if returncode != 0:
                print_error(f"Failed to remove data directory: {stderr}")
                return False
            print_success(f"Removed Nextcloud data directory: {data_dir}")

        return True
    return False


def drop_database() -> bool:
    """Drop the Nextcloud database and user."""
    print_step("Removing Nextcloud database...")

    db_name = (
        input(f"Enter database name to remove [{DEFAULT_DB_NAME}]: ") or DEFAULT_DB_NAME
    )
    db_user = (
        input(f"Enter database user to remove [{DEFAULT_DB_USER}]: ") or DEFAULT_DB_USER
    )

    if confirm(
        f"This will permanently delete the database '{db_name}' and user '{db_user}'. Continue?"
    ):
        # Drop database
        drop_db_cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-c",
            f"DROP DATABASE IF EXISTS {db_name};",
        ]
        returncode, _, stderr = run_command(drop_db_cmd)
        if returncode != 0 and "does not exist" not in stderr:
            print_error(f"Failed to drop database: {stderr}")
            return False
        print_success(f"Removed database: {db_name}")

        # Drop user
        drop_user_cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-c",
            f"DROP USER IF EXISTS {db_user};",
        ]
        returncode, _, stderr = run_command(drop_user_cmd)
        if returncode != 0 and "does not exist" not in stderr:
            print_error(f"Failed to drop database user: {stderr}")
            return False
        print_success(f"Removed database user: {db_user}")

        return True
    return False


def remove_config_files() -> bool:
    """Remove Nextcloud configuration files."""
    print_step("Removing Nextcloud configuration files...")

    # Remove config directory
    config_dir = os.path.expanduser("~/.config/nextcloud_setup")
    if os.path.exists(config_dir):
        returncode, _, stderr = run_command(["rm", "-rf", config_dir])
        if returncode != 0:
            print_error(f"Failed to remove config directory: {stderr}")
            return False
        print_success(f"Removed Nextcloud setup configuration: {config_dir}")

    return True


def main() -> None:
    """Main function to run the uninstallation process."""
    print("\n=== Nextcloud Uninstaller ===\n")

    if os.geteuid() != 0:
        print(
            "Note: Some operations require sudo privileges. You may be prompted for your password."
        )

    # Confirm uninstallation
    if not confirm("This will uninstall Nextcloud from your system. Continue?"):
        print("Uninstallation cancelled.")
        sys.exit(0)

    # Remove Nextcloud files
    remove_nextcloud_files()

    # Drop database and user
    drop_database()

    # Remove configuration files
    remove_config_files()

    print("\n=== Nextcloud Uninstallation Complete ===")
    print("Note: Dependencies and the Caddy web server were not removed as requested.")
    print("You may want to restart Caddy service with: sudo systemctl restart caddy")


if __name__ == "__main__":
    main()
