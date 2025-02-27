#!/usr/bin/env python3
"""
Simple Disk Eraser Tool

Allows listing and basic erasing of disk devices.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time


class DiskEraser:
    """
    Utility for managing disk erasure operations.
    """

    def __init__(self, verbose=False):
        """
        Initialize disk eraser.

        Args:
            verbose (bool): Enable detailed output
        """
        self.verbose = verbose

    def _run_command(self, cmd, capture_output=True, check=True):
        """
        Run a shell command safely.

        Args:
            cmd (list): Command to execute
            capture_output (bool): Capture command output
            check (bool): Raise exception on non-zero exit

        Returns:
            subprocess.CompletedProcess: Command execution result
        """
        try:
            if self.verbose:
                print(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=capture_output, text=True, check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            raise

    def list_disks(self):
        """
        List all block devices.

        Returns:
            list: Disk information
        """
        try:
            output = self._run_command(
                ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MODEL,MOUNTPOINT"]
            )
            return output.stdout.splitlines()
        except Exception as e:
            print(f"Error listing disks: {e}")
            return []

    def detect_disk_type(self, disk):
        """
        Detect disk type (HDD, SSD, NVMe).

        Args:
            disk (str): Disk device name

        Returns:
            str: Disk type
        """
        try:
            # Check if NVMe
            if disk.startswith("nvme"):
                return "NVMe"

            # Check if rotational (HDD)
            rotational_path = f"/sys/block/{disk}/queue/rotational"
            if os.path.exists(rotational_path):
                with open(rotational_path, "r") as f:
                    return "HDD" if f.read().strip() == "1" else "SSD"

            return "Unknown"
        except Exception:
            return "Unknown"

    def is_mounted(self, disk):
        """
        Check if a disk is currently mounted.

        Args:
            disk (str): Disk device path

        Returns:
            bool: True if mounted, False otherwise
        """
        try:
            output = self._run_command(["mount"])
            return disk in output.stdout
        except Exception:
            return False

    def shred_disk(self, disk, passes=3):
        """
        Securely erase a disk using shred.

        Args:
            disk (str): Disk device path
            passes (int): Number of overwrite passes
        """
        # Safety checks
        if not os.path.exists(disk):
            print(f"Error: Disk {disk} does not exist.")
            return False

        if self.is_mounted(disk):
            print(f"Warning: {disk} is currently mounted!")
            confirm = input("Are you sure you want to continue? (y/N): ").lower()
            if confirm != "y":
                print("Disk erasure cancelled.")
                return False

        # Confirm erasure
        print(f"WARNING: This will permanently erase {disk}")
        print(f"Number of passes: {passes}")
        confirm = input("Type 'YES' to confirm: ")

        if confirm != "YES":
            print("Disk erasure cancelled.")
            return False

        try:
            # Perform secure erase
            print(f"Starting secure erase of {disk} with {passes} passes...")
            self._run_command(
                [
                    "shred",
                    "-n",
                    str(passes),  # Number of passes
                    "-z",  # Final pass with zeros
                    "-v",  # Verbose mode
                    disk,
                ]
            )
            print(f"Secure erase of {disk} completed successfully.")
            return True
        except Exception as e:
            print(f"Error during disk erasure: {e}")
            return False


def main():
    """
    Main entry point for the disk eraser tool.
    """
    # Check root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Simple Disk Eraser Tool")
    parser.add_argument(
        "-l", "--list", action="store_true", help="List available disks"
    )
    parser.add_argument(
        "-e", "--erase", type=str, help="Erase specified disk device (e.g., /dev/sdb)"
    )
    parser.add_argument(
        "-p",
        "--passes",
        type=int,
        default=3,
        help="Number of overwrite passes (default: 3)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # Parse arguments
    args = parser.parse_args()

    # Create disk eraser instance
    eraser = DiskEraser(verbose=args.verbose)

    # List disks if requested
    if args.list:
        print("Available Disks:")
        for disk in eraser.list_disks():
            print(disk)
        return

    # Erase disk if specified
    if args.erase:
        disk_type = eraser.detect_disk_type(os.path.basename(args.erase))
        print(f"Disk Type: {disk_type}")
        eraser.shred_disk(args.erase, args.passes)
        return

    # If no arguments provided, show interactive menu
    while True:
        print("\nDisk Eraser Menu:")
        print("1. List Disks")
        print("2. Erase Disk")
        print("3. Exit")

        choice = input("Enter your choice: ").strip()

        if choice == "1":
            print("\nAvailable Disks:")
            for disk in eraser.list_disks():
                print(disk)

        elif choice == "2":
            disk = input("Enter disk device to erase (e.g., /dev/sdb): ").strip()
            passes = input("Number of passes (default 3): ").strip()
            passes = int(passes) if passes.isdigit() else 3

            disk_type = eraser.detect_disk_type(os.path.basename(disk))
            print(f"Disk Type: {disk_type}")
            eraser.shred_disk(disk, passes)

        elif choice == "3":
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
