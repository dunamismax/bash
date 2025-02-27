#!/usr/bin/env python3
"""
Install Virtualization Packages for Ubuntu

This script installs common virtualization packages (QEMU/KVM, libvirt, virt-manager, etc.)
on Ubuntu. It uses only the standard library and provides clear progress tracking,
ANSI color-coded output, and error handling.

Note: Run this script with root privileges.
"""

import os
import signal
import subprocess
import sys
import time
from typing import List


# ANSI color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


# List of virtualization packages to install
PACKAGES: List[str] = [
    "qemu-kvm",
    "qemu-utils",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virt-manager",
    "bridge-utils",
    "cpu-checker",
    "ovmf",
    "virtinst",
]


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully."""
    print(f"\n{Colors.YELLOW}Installation interrupted. Exiting...{Colors.ENDC}")
    sys.exit(1)


def run_command(cmd: List[str]) -> bool:
    """
    Run a shell command and stream its output.

    Args:
        cmd: A list of command arguments.

    Returns:
        True if command succeeds, False otherwise.
    """
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        # Stream output line by line
        while True:
            line = process.stdout.readline()
            if not line:
                break
            sys.stdout.write(line)
        process.wait()
        if process.returncode != 0:
            print(
                f"{Colors.RED}Command {' '.join(cmd)} failed with exit code {process.returncode}.{Colors.ENDC}"
            )
            return False
        return True
    except Exception as e:
        print(f"{Colors.RED}Error running command {' '.join(cmd)}: {e}{Colors.ENDC}")
        return False


def print_header(message: str) -> None:
    """Print a formatted header message."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def install_packages(packages: List[str]) -> None:
    """Install each package individually with progress tracking."""
    total = len(packages)
    for idx, pkg in enumerate(packages, start=1):
        print_header(f"Installing package {idx} of {total}: {pkg}")
        cmd = ["apt-get", "install", "-y", pkg]
        if not run_command(cmd):
            print(
                f"{Colors.RED}Failed to install {pkg}. Aborting installation.{Colors.ENDC}"
            )
            sys.exit(1)
        else:
            print(f"{Colors.GREEN}Successfully installed {pkg}.{Colors.ENDC}")
        time.sleep(1)  # Short delay for readability


def main() -> None:
    """Main execution function."""
    # Setup signal handling for graceful termination
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check for root privileges
    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)

    print_header("Updating package lists")
    if not run_command(["apt-get", "update"]):
        print(f"{Colors.RED}Failed to update package lists. Aborting.{Colors.ENDC}")
        sys.exit(1)

    print_header("Starting installation of virtualization packages")
    install_packages(PACKAGES)

    print_header("Installation Complete")
    print(
        f"{Colors.GREEN}All virtualization packages were installed successfully.{Colors.ENDC}"
    )


if __name__ == "__main__":
    main()
