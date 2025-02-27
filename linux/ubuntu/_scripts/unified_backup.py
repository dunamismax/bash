#!/usr/bin/env python3
"""
Simple Restic Backup Script

Performs system, VM, and Plex backups using restic to Backblaze B2.
"""

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime


class BackupManager:
    """
    Manage backup operations for different system components using restic.
    """

    def __init__(self, verbose=False):
        """
        Initialize backup manager.

        Args:
            verbose (bool): Enable detailed output
        """
        self.verbose = verbose

        # Restic configuration
        self.hostname = socket.gethostname()

        # Backblaze B2 Configuration
        self.b2_account_id = os.environ.get(
            "B2_ACCOUNT_ID",
            "12345678",  # Default placeholder
        )
        self.b2_account_key = os.environ.get(
            "B2_ACCOUNT_KEY",
            "12345678",  # Default placeholder
        )
        self.b2_bucket = os.environ.get(
            "B2_BUCKET",
            "sawyer-backups",  # Default bucket name
        )
        self.restic_password = os.environ.get(
            "RESTIC_PASSWORD",
            "12345678",  # Default placeholder
        )

        # Repository paths
        self.repos = {
            "system": f"b2:{self.b2_bucket}:{self.hostname}/ubuntu-system-backup",
            "vm": f"b2:{self.b2_bucket}:{self.hostname}/vm-backups",
            "plex": f"b2:{self.b2_bucket}:{self.hostname}/plex-media-server-backup",
        }

        # Backup sources and excludes
        self.backup_sources = {
            "system": {
                "paths": ["/"],
                "excludes": [
                    "/proc/*",
                    "/sys/*",
                    "/dev/*",
                    "/run/*",
                    "/tmp/*",
                    "/var/tmp/*",
                    "/mnt/*",
                    "/media/*",
                    "/var/cache/*",
                    "/var/log/*",
                    "/home/*/.cache/*",
                    "/swapfile",
                    "/lost+found",
                    "*.vmdk",
                    "*.vdi",
                    "*.qcow2",
                    "*.img",
                    "*.iso",
                    "*.tmp",
                    "*.swap.img",
                    "/var/lib/docker/*",
                    "/var/lib/lxc/*",
                ],
            },
            "vm": {"paths": ["/etc/libvirt", "/var/lib/libvirt"], "excludes": []},
            "plex": {
                "paths": ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"],
                "excludes": [
                    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
                    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
                    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
                    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
                ],
            },
        }

    def _run_restic_command(
        self, repo: str, command: list
    ) -> subprocess.CompletedProcess:
        """
        Run a restic command with environment variables.

        Args:
            repo (str): Restic repository
            command (list): Restic command and arguments

        Returns:
            subprocess.CompletedProcess: Command execution result
        """
        # Prepare environment with restic credentials
        env = os.environ.copy()
        env.update(
            {
                "RESTIC_PASSWORD": self.restic_password,
                "B2_ACCOUNT_ID": self.b2_account_id,
                "B2_ACCOUNT_KEY": self.b2_account_key,
            }
        )

        # Build full command
        full_cmd = ["restic", "--repo", repo] + command

        try:
            if self.verbose:
                print(f"Running: {' '.join(full_cmd)}")

            result = subprocess.run(
                full_cmd, env=env, capture_output=True, text=True, check=True
            )

            if self.verbose:
                print("Command output:")
                print(result.stdout)

            return result

        except subprocess.CalledProcessError as e:
            print(f"Restic command failed: {' '.join(full_cmd)}")
            print(f"Error output: {e.stderr}")
            raise

    def backup_service(self, service: str) -> bool:
        """
        Backup a specific service using restic.

        Args:
            service (str): Service to backup

        Returns:
            bool: True if backup succeeded, False otherwise
        """
        if service not in self.backup_sources:
            print(f"Unknown service: {service}")
            return False

        config = self.backup_sources[service]
        repo = self.repos[service]

        print(f"Starting backup for {service}...")

        try:
            # Construct backup command
            backup_cmd = ["backup"]

            # Add paths
            backup_cmd.extend(config["paths"])

            # Add excludes
            for exclude in config["excludes"]:
                backup_cmd.extend(["--exclude", exclude])

            # Run backup
            self._run_restic_command(repo, backup_cmd)

            # Perform retention/cleanup
            retention_cmd = [
                "forget",
                "--prune",
                "--keep-within",
                "7d",  # Keep snapshots from last 7 days
            ]
            self._run_restic_command(repo, retention_cmd)

            print(f"Backup of {service} completed successfully.")
            return True

        except Exception as e:
            print(f"Backup of {service} failed: {e}")
            return False

    def backup_all_services(self) -> dict:
        """
        Backup all configured services.

        Returns:
            dict: Backup results for each service
        """
        results = {}
        for service in self.backup_sources:
            results[service] = self.backup_service(service)
        return results


def main():
    """
    Main entry point for backup script.
    """
    # Check root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Check restic installation
    if not shutil.which("restic"):
        print("Restic is not installed. Please install restic first.")
        sys.exit(1)

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Restic Backup Utility")
    parser.add_argument(
        "-s",
        "--service",
        choices=["system", "vm", "plex", "all"],
        default="all",
        help="Specific service to backup",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # Parse arguments
    args = parser.parse_args()

    # Create backup manager
    try:
        backup_manager = BackupManager(verbose=args.verbose)

        # Print startup info
        print("Restic Backup Utility")
        print(f"Hostname: {backup_manager.hostname}")
        print(f"Platform: {platform.platform()}")
        print(f"Backup Bucket: {backup_manager.b2_bucket}")

        # Perform backup based on service argument
        if args.service == "all":
            results = backup_manager.backup_all_services()

            # Check overall success
            if not all(results.values()):
                print("\nSome services failed to backup:")
                for service, success in results.items():
                    if not success:
                        print(f"  - {service}")
                sys.exit(1)
        else:
            # Backup specific service
            success = backup_manager.backup_service(args.service)
            if not success:
                sys.exit(1)

        print("\nBackup completed successfully.")

    except Exception as e:
        print(f"Backup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
