#!/usr/bin/env python3
"""
Simple Ubuntu VoIP Setup Utility

Assists in basic setup of VoIP services on Ubuntu.
"""

import argparse
import os
import subprocess
import sys
import time


class VoIPSetup:
    """
    Utility for setting up VoIP services on Ubuntu.
    """

    def __init__(self, verbose=False):
        """
        Initialize VoIP setup.

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

    def check_system(self):
        """
        Verify system compatibility and requirements.
        """
        # Check Ubuntu version
        try:
            dist_info = self._run_command(["lsb_release", "-a"])
            print("System Information:")
            print(dist_info.stdout)
        except Exception as e:
            print(f"Error checking system information: {e}")

    def update_system(self):
        """
        Update system packages.
        """
        print("Updating system packages...")
        try:
            # Update package lists
            self._run_command(["apt-get", "update"])

            # Upgrade packages
            self._run_command(["apt-get", "upgrade", "-y"])

            print("System packages updated successfully.")
        except Exception as e:
            print(f"Error updating system: {e}")

    def install_voip_packages(self):
        """
        Install VoIP-related packages.
        """
        packages = [
            "asterisk",
            "asterisk-config",
            "mariadb-server",
            "mariadb-client",
            "ufw",
        ]

        print(f"Installing VoIP packages: {', '.join(packages)}")
        try:
            self._run_command(["apt-get", "install", "-y"] + packages)
            print("VoIP packages installed successfully.")
        except Exception as e:
            print(f"Error installing packages: {e}")

    def configure_firewall(self):
        """
        Configure UFW firewall for VoIP traffic.
        """
        print("Configuring firewall for VoIP...")
        try:
            # Allow SIP traffic
            self._run_command(["ufw", "allow", "5060/udp"])

            # Allow RTP traffic range
            self._run_command(["ufw", "allow", "16384:32767/udp"])

            print("Firewall rules added successfully.")
        except Exception as e:
            print(f"Error configuring firewall: {e}")

    def create_asterisk_config(self):
        """
        Create basic Asterisk configuration.
        """
        config_dir = "/etc/asterisk"
        os.makedirs(config_dir, exist_ok=True)

        # SIP configuration
        sip_conf_path = os.path.join(config_dir, "sip_custom.conf")
        sip_conf_content = """[general]
disallow=all
allow=g722

[6001]
type=friend
context=internal
host=dynamic
secret=changeme6001
callerid=Phone 6001 <6001>
disallow=all
allow=g722

[6002]
type=friend
context=internal
host=dynamic
secret=changeme6002
callerid=Phone 6002 <6002>
disallow=all
allow=g722
"""

        # Extensions configuration
        ext_conf_path = os.path.join(config_dir, "extensions_custom.conf")
        ext_conf_content = """[internal]
exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})
 same => n,Dial(SIP/${EXTEN},20)
 same => n,Hangup()

[default]
exten => s,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
"""

        try:
            # Write SIP configuration
            with open(sip_conf_path, "w") as f:
                f.write(sip_conf_content)
            print(f"Created SIP configuration: {sip_conf_path}")

            # Write extensions configuration
            with open(ext_conf_path, "w") as f:
                f.write(ext_conf_content)
            print(f"Created extensions configuration: {ext_conf_path}")

        except Exception as e:
            print(f"Error creating Asterisk configuration: {e}")

    def start_services(self):
        """
        Start and enable VoIP-related services.
        """
        services = ["asterisk", "mariadb"]

        for service in services:
            try:
                # Enable service
                self._run_command(["systemctl", "enable", service])

                # Start service
                self._run_command(["systemctl", "start", service])

                print(f"Service {service} started and enabled.")
            except Exception as e:
                print(f"Error managing {service} service: {e}")

    def verify_installation(self):
        """
        Perform final verification of the VoIP setup.
        """
        print("\nVerification:")

        # Check Asterisk version
        try:
            asterisk_version = self._run_command(
                ["asterisk", "-V"], capture_output=True
            )
            print(f"Asterisk Version: {asterisk_version.stdout.strip()}")
        except Exception as e:
            print(f"Could not verify Asterisk: {e}")

        # Check service status
        services = ["asterisk", "mariadb"]
        for service in services:
            try:
                status = self._run_command(
                    ["systemctl", "is-active", service], capture_output=True
                )
                print(f"{service.capitalize()} Status: {status.stdout.strip()}")
            except Exception as e:
                print(f"Could not check {service} status: {e}")


def main():
    """
    Main entry point for VoIP setup.
    """
    # Check for root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Ubuntu VoIP Setup Utility")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check system compatibility"
    )
    parser.add_argument("--update", action="store_true", help="Update system packages")
    parser.add_argument(
        "--full-setup", action="store_true", help="Perform full VoIP setup"
    )

    # Parse arguments
    args = parser.parse_args()

    # Create VoIP setup instance
    setup = VoIPSetup(verbose=args.verbose)

    # Perform requested operations
    if args.check:
        setup.check_system()

    if args.update:
        setup.update_system()

    if args.full_setup:
        try:
            # Comprehensive VoIP setup
            setup.check_system()
            setup.update_system()
            setup.install_voip_packages()
            setup.configure_firewall()
            setup.create_asterisk_config()
            setup.start_services()
            setup.verify_installation()

            print("\nVoIP setup completed successfully.")
            print("Please review the configuration and test your VoIP services.")

        except Exception as e:
            print(f"VoIP setup failed: {e}")
            sys.exit(1)

    # If no specific action, show help
    if not any(vars(args).values()):
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
        sys.exit(1)
