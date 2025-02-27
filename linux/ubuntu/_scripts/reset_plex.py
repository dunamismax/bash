#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import time

# ------------------------------------------------------------------------------
# Plex Reset Script
# ------------------------------------------------------------------------------
PLEX_DATA_DIR = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"
PLEX_SERVICE = "plexmediaserver"


def run_command(cmd: str) -> str:
    """
    Run a shell command and return its output.
    Exits the script if an error occurs.
    """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command '{cmd}': {result.stderr}")
        sys.exit(result.returncode)
    return result.stdout.strip()


def control_service(service: str, action: str) -> None:
    """
    Stop or start a given service.
    """
    print(f"{action.capitalize()}ing service '{service}'...")
    run_command(f"systemctl {action} {service}")
    time.sleep(2)


def delete_directory(path: str) -> None:
    """
    Delete the specified directory if it exists.
    """
    if os.path.exists(path):
        print(f"Deleting directory: {path}")
        shutil.rmtree(path)
    else:
        print(f"Directory not found (skipping deletion): {path}")


def reset_plex() -> None:
    """
    Reset Plex by stopping its service, deleting its data directory, and then restarting the service.
    """
    print("Starting Plex reset procedure...")

    # Stop Plex service
    control_service(PLEX_SERVICE, "stop")

    # Delete the Plex data directory
    delete_directory(PLEX_DATA_DIR)

    # Start Plex service
    control_service(PLEX_SERVICE, "start")

    print("Plex Media Server has been reset successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset Plex Media Server by deleting its data directory and restarting its service"
    )
    # No additional arguments needed but you could add options here if desired
    args = parser.parse_args()

    print("Initiating Plex reset operations...")
    start_time = time.time()

    reset_plex()

    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f} seconds")


if __name__ == "__main__":
    # Ensure the script is run as root.
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)
    main()
