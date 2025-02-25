#!/usr/bin/env python3
"""
Standalone script to install Nala (an apt front-end) on Ubuntu.

This script checks if Nala is installed. If not, it updates the apt repositories
and installs Nala using apt. It prints informational messages to the console.
"""

import os
import subprocess
import sys
from shutil import which

def print_section(title: str) -> None:
    border = "=" * 60
    print("\n" + border)
    print(title)
    print(border + "\n")

def command_exists(cmd: str) -> bool:
    return which(cmd) is not None

def run_command(cmd, check=True, capture_output=False, text=True):
    print(f"[INFO] Running command: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)

def log_info(message: str) -> None:
    print(f"[INFO] {message}")

def log_warn(message: str) -> None:
    print(f"[WARNING] {message}")

def handle_error(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}")
    sys.exit(code)

def install_nala() -> None:
    """
    Install Nala (an apt front-end) if it is not already installed.
    """
    print_section("Nala Installation")
    
    if not command_exists("nala"):
        log_info("Nala is not installed. Installing Nala...")
        try:
            # Update package repositories and install Nala using sudo.
            run_command(["sudo", "apt", "update"])
            run_command(["sudo", "apt", "install", "-y", "nala"])
            log_info("Nala installed successfully.")
        except subprocess.CalledProcessError as e:
            handle_error(f"Failed to install Nala: {e}")
    else:
        log_info("Nala is already installed.")

def main() -> None:
    install_nala()

if __name__ == "__main__":
    main()