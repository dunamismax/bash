#!/usr/bin/env python3
"""
Simple File Restore Utility

Restores files from a backup location to their original destinations.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time


class FileRestorer:
    """
    Utility for restoring files from a backup location.
    """

    def __init__(self, backup_base, verbose=False):
        """
        Initialize file restorer.

        Args:
            backup_base (str): Base path of backup data
            verbose (bool): Enable detailed output
        """
        self.backup_base = os.path.abspath(backup_base)
        self.verbose = verbose
        self.services = {
            "vm": {
                "name": "VM Configuration",
                "source": os.path.join(backup_base, "vm", "var", "lib", "libvirt"),
                "target": "/var/lib/libvirt",
                "service": "libvirtd",
            },
            "plex": {
                "name": "Plex Media Server",
                "source": os.path.join(
                    backup_base, "plex", "var", "lib", "plexmediaserver"
                ),
                "target": "/var/lib/plexmediaserver",
                "service": "plexmediaserver",
            },
        }

    def _run_command(self, cmd):
        """
        Run a shell command safely.

        Args:
            cmd (str): Command to execute

        Returns:
            str: Command output
        """
        try:
            if self.verbose:
                print(f"Running: {cmd}")

            result = subprocess.run(
                cmd, shell=True, check=True, capture_output=True, text=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {cmd}")
            print(f"Error: {e.stderr}")
            raise

    def _is_service_running(self, service):
        """
        Check if a service is running.

        Args:
            service (str): Name of the service

        Returns:
            bool: True if service is running, False otherwise
        """
        try:
            output = self._run_command(f"systemctl is-active {service}")
            return output == "active"
        except Exception:
            return False

    def _control_service(self, service, action):
        """
        Start or stop a system service.

        Args:
            service (str): Name of the service
            action (str): 'start' or 'stop'
        """
        try:
            self._run_command(f"systemctl {action} {service}")
            time.sleep(2)  # Wait for service state change
        except Exception as e:
            print(f"Failed to {action} service {service}: {e}")

    def restore_service(self, service_name):
        """
        Restore a specific service from backup.

        Args:
            service_name (str): Name of the service to restore
        """
        if service_name not in self.services:
            print(f"Unknown service: {service_name}")
            return False

        service_config = self.services[service_name]
        source = service_config["source"]
        target = service_config["target"]
        service = service_config["service"]

        print(f"\nRestoring {service_config['name']}...")

        # Check if source exists
        if not os.path.exists(source):
            print(f"Backup source not found: {source}")
            return False

        try:
            # Stop service if running
            if self._is_service_running(service):
                print(f"Stopping {service} service...")
                self._control_service(service, "stop")

            # Remove existing target contents
            if os.path.exists(target):
                shutil.rmtree(target)

            # Copy backup to target
            print(f"Copying files from {source} to {target}...")
            shutil.copytree(source, target)

            # Start service
            print(f"Starting {service} service...")
            self._control_service(service, "start")

            print(f"Successfully restored {service_config['name']}")
            return True

        except Exception as e:
            print(f"Error restoring {service_config['name']}: {e}")
            return False

    def restore_all_services(self):
        """
        Restore all configured services.
        """
        results = {}
        for service_name in self.services:
            results[service_name] = self.restore_service(service_name)
        return results


def main():
    """
    Main entry point for the file restore utility.
    """
    # Check root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Set up argument parser
    parser = argparse.ArgumentParser(description="File Restore Utility")
    parser.add_argument("backup_path", help="Base path of backup data")
    parser.add_argument(
        "-s",
        "--service",
        choices=["vm", "plex", "all"],
        default="all",
        help="Specific service to restore",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # Parse arguments
    args = parser.parse_args()

    # Create restorer instance
    try:
        restorer = FileRestorer(args.backup_path, verbose=args.verbose)

        # Perform restore based on service argument
        if args.service == "all":
            results = restorer.restore_all_services()

            # Check overall success
            if not all(results.values()):
                print("\nSome services failed to restore:")
                for service, success in results.items():
                    if not success:
                        print(f"  - {service}")
                sys.exit(1)
        else:
            # Restore specific service
            success = restorer.restore_service(args.service)
            if not success:
                sys.exit(1)

        print("\nRestore completed successfully.")

    except Exception as e:
        print(f"Restore failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
