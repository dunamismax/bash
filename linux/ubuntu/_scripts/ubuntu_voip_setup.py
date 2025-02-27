#!/usr/bin/env python3
"""
Enhanced Ubuntu VoIP Setup Utility

A comprehensive utility for setting up and configuring VoIP services on Ubuntu systems.
This script assists with:
  • System compatibility verification
  • Package installation and updates
  • Asterisk PBX configuration
  • Firewall rules management
  • Service configuration

The utility provides real-time progress tracking, robust error handling, and
clear status reporting throughout the setup process.

Note: Run this script with root privileges.
"""

import argparse
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, Callable

#####################################
# Configuration
#####################################

# System information
HOSTNAME = socket.gethostname()

# VoIP packages to install
VOIP_PACKAGES = [
    "asterisk",
    "asterisk-config",
    "mariadb-server",
    "mariadb-client",
    "ufw",
]

# Firewall ports to open
FIREWALL_RULES = [
    {"port": "5060", "protocol": "udp", "description": "SIP"},
    {"port": "16384:32767", "protocol": "udp", "description": "RTP Audio"},
]

# Asterisk configuration templates
ASTERISK_CONFIGS = {
    "sip_custom.conf": """[general]
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
""",
    "extensions_custom.conf": """[internal]
exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})
 same => n,Dial(SIP/${EXTEN},20)
 same => n,Hangup()

[default]
exten => s,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
""",
}

# Services to manage
SERVICES = ["asterisk", "mariadb"]

# Progress tracking settings
PROGRESS_WIDTH = 50
OPERATION_TIMEOUT = 300  # seconds

#####################################
# UI and Progress Tracking Classes
#####################################


class Colors:
    """Nord-themed ANSI color codes for terminal output"""

    HEADER = "\033[38;5;81m"  # Nord9 - Blue
    GREEN = "\033[38;5;108m"  # Nord14 - Green
    YELLOW = "\033[38;5;179m"  # Nord13 - Yellow
    RED = "\033[38;5;174m"  # Nord11 - Red
    BLUE = "\033[38;5;67m"  # Nord10 - Deep Blue
    CYAN = "\033[38;5;110m"  # Nord8 - Light Blue
    MAGENTA = "\033[38;5;139m"  # Nord15 - Purple
    WHITE = "\033[38;5;253m"  # Nord4 - Light foreground
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class ProgressBar:
    """Thread-safe progress bar with completion percentage"""

    def __init__(self, total: int, desc: str = "", width: int = PROGRESS_WIDTH):
        self.total = max(1, total)  # Avoid division by zero
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self._display()

    def update(self, amount: int = 1) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _display(self) -> None:
        """Display progress bar with percentage"""
        filled = int(self.width * self.current / self.total)
        bar = "■" * filled + "□" * (self.width - filled)
        percent = self.current / self.total * 100

        elapsed = time.time() - self.start_time
        eta = (
            (self.total - self.current) * (elapsed / max(1, self.current))
            if self.current > 0
            else 0
        )

        sys.stdout.write(
            f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| "
            f"{Colors.WHITE}{percent:>5.1f}%{Colors.ENDC} "
            f"[{Colors.DIM}ETA: {eta:.0f}s{Colors.ENDC}]"
        )
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")


class Spinner:
    """Thread-safe terminal spinner for operations without definite progress"""

    def __init__(self, desc: str = ""):
        self.desc = desc
        self.spinning = False
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx = 0
        self.spinner_thread = None
        self._lock = threading.Lock()

    def spin(self) -> None:
        """Display spinner animation"""
        with self._lock:
            sys.stdout.write(
                f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}{Colors.BLUE}{self.spinner_chars[self.spinner_idx]}{Colors.ENDC}"
            )
            sys.stdout.flush()
            self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)

    def _spin_thread(self) -> None:
        """Thread function to keep spinner going"""
        while self.spinning:
            self.spin()
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner in a separate thread"""
        if not self.spinning:
            self.spinning = True
            self.spinner_thread = threading.Thread(target=self._spin_thread)
            self.spinner_thread.daemon = True
            self.spinner_thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner and show result"""
        if self.spinning:
            self.spinning = False
            if self.spinner_thread:
                self.spinner_thread.join()

            # Clear the spinner line
            sys.stdout.write("\r" + " " * (len(self.desc) + 20) + "\r")

            # Print completion status
            if success:
                print(
                    f"{Colors.CYAN}{self.desc}: {Colors.GREEN}✓ Complete{Colors.ENDC}"
                )
            else:
                print(f"{Colors.CYAN}{self.desc}: {Colors.RED}✗ Failed{Colors.ENDC}")


#####################################
# Helper Functions
#####################################


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def print_section(message: str) -> None:
    """Print formatted section header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {message}{Colors.ENDC}")


def print_step(message: str) -> None:
    """Print step message"""
    print(f"{Colors.CYAN}• {message}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.ENDC}")


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    verbose: bool = False,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run command with error handling"""
    if verbose:
        print_step(f"Running command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            print(f"{Colors.DIM}Stdout: {e.stdout.strip()}{Colors.ENDC}")
        if e.stderr:
            print(f"{Colors.RED}Stderr: {e.stderr.strip()}{Colors.ENDC}")
        raise


def signal_handler(sig, frame) -> None:
    """Handle interrupt signals gracefully"""
    print(
        f"\n{Colors.YELLOW}Setup interrupted. Cleaning up and exiting...{Colors.ENDC}"
    )
    # Perform any necessary cleanup here
    sys.exit(1)


def get_system_info() -> Dict[str, str]:
    """
    Get system information

    Returns:
        Dict[str, str]: Dictionary with system information
    """
    info = {
        "hostname": HOSTNAME,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "user": os.environ.get("USER", "unknown"),
    }

    # Get Ubuntu version
    try:
        result = run_command(["lsb_release", "-a"])
        for line in result.stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                info[key.strip().lower().replace(" ", "_")] = value.strip()
    except Exception:
        info["ubuntu_version"] = "Unknown"

    return info


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> bool:
    """Check if script is run with root privileges"""
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_step("Try running with sudo: sudo python3 voip_setup.py")
        return False
    return True


def check_dependencies() -> bool:
    """Check if required tools are installed"""
    # Check for apt-get
    if not shutil.which("apt-get"):
        print_error("apt-get is not available. This script requires Ubuntu.")
        return False

    # Check for systemd
    if not shutil.which("systemctl"):
        print_error("systemctl is not available. This script requires systemd.")
        return False

    return True


def check_internet_connectivity() -> bool:
    """Check if system has internet connectivity"""
    try:
        # Try to connect to a reliable host
        result = run_command(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"], check=False, capture_output=True
        )
        if result.returncode == 0:
            return True
        else:
            print_error("No internet connectivity detected.")
            return False
    except Exception as e:
        print_error(f"Failed to check internet connectivity: {e}")
        return False


#####################################
# System Operations
#####################################


def update_system(verbose: bool = False) -> bool:
    """
    Update system packages

    Args:
        verbose: Enable verbose output

    Returns:
        bool: True if successful, False otherwise
    """
    print_section("Updating System Packages")

    try:
        # Start the spinner for apt update
        update_spinner = Spinner("Updating package lists")
        update_spinner.start()

        try:
            # Update package lists
            result = run_command(
                ["apt-get", "update"], verbose=verbose, capture_output=not verbose
            )
            update_spinner.stop(True)
        except Exception as e:
            update_spinner.stop(False)
            print_error(f"Failed to update package lists: {e}")
            return False

        # Start progress bar for upgrade
        print_step("Upgrading installed packages...")

        # First get the number of upgradable packages
        try:
            upgradable = run_command(
                ["apt", "list", "--upgradable"], verbose=verbose, capture_output=True
            )
            package_count = (
                len(upgradable.stdout.splitlines()) - 1
            )  # Subtract header line
            package_count = max(1, package_count)  # Ensure at least 1
        except Exception:
            package_count = 10  # Fallback value

        progress = ProgressBar(package_count, "Upgrading packages")

        try:
            # Run upgrade in non-interactive mode
            process = subprocess.Popen(
                ["apt-get", "upgrade", "-y"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            count = 0
            while True:
                line = process.stdout.readline()
                if not line:
                    break

                # Update progress on certain markers
                if "Unpacking" in line or "Setting up" in line:
                    count += 1
                    progress.update(1)

                if verbose:
                    print(line.strip())

            # Wait for process to complete
            process.wait()

            # Ensure progress bar completes
            progress.current = progress.total
            progress._display()

            if process.returncode != 0:
                print_error("System upgrade failed.")
                return False

            print_success("System packages updated successfully.")
            return True

        except Exception as e:
            print_error(f"Error upgrading system: {e}")
            return False

    except Exception as e:
        print_error(f"Failed during system update: {e}")
        return False


def install_packages(packages: List[str], verbose: bool = False) -> bool:
    """
    Install specified packages

    Args:
        packages: List of packages to install
        verbose: Enable verbose output

    Returns:
        bool: True if successful, False otherwise
    """
    if not packages:
        return True

    print_section(f"Installing Packages")
    print_step(f"Packages to install: {', '.join(packages)}")

    try:
        # Create a progress bar
        progress = ProgressBar(len(packages), "Installing packages")

        # Run installation with progress tracking
        process = subprocess.Popen(
            ["apt-get", "install", "-y"] + packages,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Track installed packages
        installed_packages = set()

        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Update progress when a package is unpacked or set up
            if "Unpacking" in line:
                # Extract package name
                parts = line.split("Unpacking", 1)[1].strip().split(" ", 1)
                if parts and parts[0] not in installed_packages:
                    installed_packages.add(parts[0])
                    progress.update(1)

            if verbose:
                print(line.strip())

        # Wait for process to complete
        process.wait()

        # Ensure progress bar completes
        progress.current = progress.total
        progress._display()

        if process.returncode != 0:
            print_error("Package installation failed.")
            return False

        print_success(f"Successfully installed {len(packages)} package(s).")
        return True

    except Exception as e:
        print_error(f"Failed to install packages: {e}")
        return False


#####################################
# VoIP Setup Functions
#####################################


def configure_firewall(rules: List[Dict[str, str]], verbose: bool = False) -> bool:
    """
    Configure UFW firewall rules for VoIP

    Args:
        rules: List of firewall rules to apply
        verbose: Enable verbose output

    Returns:
        bool: True if successful, False otherwise
    """
    print_section("Configuring Firewall")

    try:
        # Check if UFW is installed
        if not shutil.which("ufw"):
            print_warning("UFW firewall not found. Installing...")
            if not install_packages(["ufw"], verbose):
                return False

        # Create a progress bar
        progress = ProgressBar(len(rules) + 2, "Configuring firewall")

        # Ensure UFW is enabled
        try:
            # First, get UFW status
            status_result = run_command(["ufw", "status"], check=False)
            if "Status: inactive" in status_result.stdout:
                print_step("Enabling UFW firewall...")
                run_command(["ufw", "--force", "enable"])

            progress.update(1)
        except Exception as e:
            print_error(f"Failed to enable UFW: {e}")
            return False

        # Add each firewall rule
        for rule in rules:
            rule_desc = f"{rule['port']}/{rule['protocol']} ({rule['description']})"
            try:
                print_step(f"Adding rule for {rule_desc}")
                run_command(
                    ["ufw", "allow", f"{rule['port']}/{rule['protocol']}"],
                    verbose=verbose,
                )
                progress.update(1)
            except Exception as e:
                print_error(f"Failed to add firewall rule for {rule_desc}: {e}")
                return False

        # Reload UFW to apply changes
        run_command(["ufw", "reload"], verbose=verbose)
        progress.update(1)

        print_success("Firewall configuration completed.")
        return True

    except Exception as e:
        print_error(f"Firewall configuration failed: {e}")
        return False


def create_asterisk_config(configs: Dict[str, str], verbose: bool = False) -> bool:
    """
    Create Asterisk configuration files

    Args:
        configs: Dictionary mapping filenames to content
        verbose: Enable verbose output

    Returns:
        bool: True if successful, False otherwise
    """
    print_section("Creating Asterisk Configuration")

    try:
        config_dir = "/etc/asterisk"

        # Ensure directory exists
        os.makedirs(config_dir, exist_ok=True)

        # Create a progress bar
        progress = ProgressBar(len(configs), "Creating config files")

        # Create each configuration file
        for filename, content in configs.items():
            file_path = os.path.join(config_dir, filename)
            try:
                print_step(f"Creating {filename}")

                # Check if file exists already
                backup_path = None
                if os.path.exists(file_path):
                    backup_path = f"{file_path}.bak.{int(time.time())}"
                    shutil.copy2(file_path, backup_path)
                    if verbose:
                        print(f"  - Backed up existing file to {backup_path}")

                # Write the new configuration
                with open(file_path, "w") as f:
                    f.write(content)

                progress.update(1)

                if backup_path:
                    print_step(
                        f"Original file backed up to {os.path.basename(backup_path)}"
                    )

            except Exception as e:
                print_error(f"Failed to create {filename}: {e}")
                return False

        print_success("Asterisk configuration files created successfully.")
        return True

    except Exception as e:
        print_error(f"Failed to create Asterisk configuration: {e}")
        return False


def manage_services(
    services: List[str], action: str = "restart", verbose: bool = False
) -> bool:
    """
    Manage system services (start/stop/restart/enable)

    Args:
        services: List of service names to manage
        action: Action to perform (start, stop, restart, enable)
        verbose: Enable verbose output

    Returns:
        bool: True if successful, False otherwise
    """
    valid_actions = ["start", "stop", "restart", "enable", "disable"]
    if action not in valid_actions:
        print_error(f"Invalid service action: {action}")
        return False

    print_section(f"{action.capitalize()}ing Services")

    # Create a progress bar
    progress = ProgressBar(len(services), f"{action.capitalize()}ing services")

    # Process each service
    for service in services:
        try:
            spinner = Spinner(f"{action.capitalize()}ing {service}")
            spinner.start()

            result = run_command(
                ["systemctl", action, service], verbose=verbose, check=False
            )

            if result.returncode != 0:
                spinner.stop(False)
                print_error(f"Failed to {action} {service}: {result.stderr.strip()}")
                return False

            spinner.stop(True)
            progress.update(1)

        except Exception as e:
            print_error(f"Failed to {action} {service}: {e}")
            return False

    print_success(f"Successfully {action}ed all services.")
    return True


def verify_installation(verbose: bool = False) -> bool:
    """
    Perform final verification of the VoIP setup

    Args:
        verbose: Enable verbose output

    Returns:
        bool: True if verification passed, False otherwise
    """
    print_section("Verifying Installation")
    verification_results = {}

    try:
        # Check Asterisk installation
        try:
            print_step("Checking Asterisk version")
            asterisk_version = run_command(["asterisk", "-V"], capture_output=True)
            version_str = asterisk_version.stdout.strip()
            verification_results["asterisk_version"] = {
                "status": True,
                "message": version_str,
            }
            print(f"  {Colors.GREEN}✓{Colors.ENDC} {version_str}")
        except Exception as e:
            verification_results["asterisk_version"] = {
                "status": False,
                "message": str(e),
            }
            print(f"  {Colors.RED}✗{Colors.ENDC} Failed to check Asterisk version: {e}")

        # Check each service status
        print_step("Checking service status")
        for service in SERVICES:
            try:
                status_result = run_command(
                    ["systemctl", "is-active", service],
                    check=False,
                    capture_output=True,
                )

                status = status_result.stdout.strip()
                is_active = status == "active"

                verification_results[f"{service}_status"] = {
                    "status": is_active,
                    "message": status,
                }

                status_symbol = (
                    f"{Colors.GREEN}✓{Colors.ENDC}"
                    if is_active
                    else f"{Colors.RED}✗{Colors.ENDC}"
                )
                status_color = Colors.GREEN if is_active else Colors.RED
                print(
                    f"  {status_symbol} {service}: {status_color}{status}{Colors.ENDC}"
                )

            except Exception as e:
                verification_results[f"{service}_status"] = {
                    "status": False,
                    "message": str(e),
                }
                print(
                    f"  {Colors.RED}✗{Colors.ENDC} Failed to check {service} status: {e}"
                )

        # Check if firewall is configured correctly
        print_step("Checking firewall configuration")
        try:
            ufw_status = run_command(["ufw", "status"], capture_output=True)
            is_configured = all(
                f"{rule['port']}/{rule['protocol']}" in ufw_status.stdout
                for rule in FIREWALL_RULES
            )

            verification_results["firewall_status"] = {
                "status": is_configured,
                "message": "Correctly configured" if is_configured else "Missing rules",
            }

            if is_configured:
                print(
                    f"  {Colors.GREEN}✓{Colors.ENDC} Firewall rules correctly configured"
                )
            else:
                print(
                    f"  {Colors.YELLOW}⚠{Colors.ENDC} Some firewall rules may be missing"
                )

        except Exception as e:
            verification_results["firewall_status"] = {
                "status": False,
                "message": str(e),
            }
            print(f"  {Colors.RED}✗{Colors.ENDC} Failed to check firewall: {e}")

        # Check configuration files
        print_step("Checking configuration files")
        configs_exist = True
        for config_file in ASTERISK_CONFIGS.keys():
            file_path = f"/etc/asterisk/{config_file}"
            if os.path.exists(file_path):
                print(f"  {Colors.GREEN}✓{Colors.ENDC} {config_file} exists")
            else:
                configs_exist = False
                print(f"  {Colors.RED}✗{Colors.ENDC} {config_file} is missing")

        verification_results["config_files"] = {
            "status": configs_exist,
            "message": "All configuration files exist"
            if configs_exist
            else "Missing configuration files",
        }

        # Overall verification status
        all_passed = all(result["status"] for result in verification_results.values())

        if all_passed:
            print_success(
                "Verification completed successfully. VoIP setup is properly configured."
            )
        else:
            print_warning(
                "Verification completed with some issues. Please review the findings above."
            )

        return all_passed

    except Exception as e:
        print_error(f"Verification process failed: {e}")
        return False


#####################################
# VoIP Setup Orchestration
#####################################


def perform_voip_setup(verbose: bool = False) -> bool:
    """
    Perform the full VoIP setup workflow

    Args:
        verbose: Enable verbose output

    Returns:
        bool: True if setup succeeded, False otherwise
    """
    start_time = time.time()

    print_header("Ubuntu VoIP Setup Utility")

    # Log system information
    system_info = get_system_info()
    print(f"Hostname: {system_info['hostname']}")
    print(f"Platform: {system_info['platform']}")
    if "description" in system_info:
        print(f"Distribution: {system_info['description']}")
    print(f"Python Version: {system_info['python_version']}")
    print(f"Setup starting at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check prerequisites
    print_section("Checking Prerequisites")

    if not check_root_privileges():
        return False

    if not check_dependencies():
        return False

    if not check_internet_connectivity():
        print_warning("No internet connectivity detected. Setup may fail.")
        choice = input(f"{Colors.YELLOW}Continue anyway? (y/N): {Colors.ENDC}").lower()
        if choice != "y":
            print_error("Setup aborted by user.")
            return False

    # Update system
    if not update_system(verbose):
        print_warning("System update failed. Continuing with installation...")

    # Install VoIP packages
    if not install_packages(VOIP_PACKAGES, verbose):
        print_error("Failed to install required packages. Aborting setup.")
        return False

    # Configure firewall
    if not configure_firewall(FIREWALL_RULES, verbose):
        print_warning("Firewall configuration failed. Continuing with setup...")

    # Create Asterisk configuration
    if not create_asterisk_config(ASTERISK_CONFIGS, verbose):
        print_error("Failed to create Asterisk configuration. Aborting setup.")
        return False

    # Start and enable services
    if not manage_services(SERVICES, "enable", verbose):
        print_warning("Failed to enable services. Continuing...")

    if not manage_services(SERVICES, "restart", verbose):
        print_warning("Failed to restart services. Continuing...")

    # Verify installation
    verification_result = verify_installation(verbose)

    # Calculate elapsed time
    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)

    # Print summary
    print_header("Setup Summary")
    if verification_result:
        print_success("VoIP setup completed successfully.")
    else:
        print_warning("VoIP setup completed with warnings or errors.")

    print(f"Elapsed time: {int(minutes)}m {int(seconds)}s")
    print(f"Completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Print next steps
    print_section("Next Steps")
    print("1. Review the Asterisk configuration files in /etc/asterisk/")
    print("2. Set up SIP clients using the credentials provided in the configuration")
    print("3. Test calling between extensions 6001 and 6002")
    print("4. Consider setting up secure SIP using TLS for production use")

    return verification_result


#####################################
# Main Function
#####################################


def main() -> None:
    """Main execution function"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Enhanced Ubuntu VoIP Setup Utility",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "--check", action="store_true", help="Check system compatibility only"
    )

    parser.add_argument(
        "--update", action="store_true", help="Update system packages only"
    )

    parser.add_argument(
        "--install-packages", action="store_true", help="Install VoIP packages only"
    )

    parser.add_argument(
        "--configure-firewall",
        action="store_true",
        help="Configure firewall rules only",
    )

    parser.add_argument(
        "--configure-asterisk", action="store_true", help="Configure Asterisk only"
    )

    parser.add_argument(
        "--verify", action="store_true", help="Verify installation only"
    )

    parser.add_argument(
        "--full-setup", action="store_true", help="Perform full VoIP setup (all steps)"
    )

    # Parse arguments
    args = parser.parse_args()

    try:
        if args.check:
            # System compatibility check only
            print_header("System Compatibility Check")

            is_root = check_root_privileges()
            has_deps = check_dependencies()
            has_internet = check_internet_connectivity()

            system_info = get_system_info()

            print_section("Results")
            print(f"Root privileges: {'Yes' if is_root else 'No'}")
            print(f"Required dependencies: {'Available' if has_deps else 'Missing'}")
            print(
                f"Internet connectivity: {'Available' if has_internet else 'Missing'}"
            )

            print_section("System Information")
            for key, value in system_info.items():
                print(f"{key.replace('_', ' ').title()}: {value}")

            if is_root and has_deps and has_internet:
                print_success("System is compatible with VoIP setup.")
            else:
                print_warning(
                    "System has compatibility issues. Please address them before proceeding."
                )

        elif args.update:
            # Update system only
            if not check_root_privileges():
                sys.exit(1)
            update_system(args.verbose)

        elif args.install_packages:
            # Install VoIP packages only
            if not check_root_privileges():
                sys.exit(1)
            install_packages(VOIP_PACKAGES, args.verbose)

        elif args.configure_firewall:
            # Configure firewall only
            if not check_root_privileges():
                sys.exit(1)
            configure_firewall(FIREWALL_RULES, args.verbose)

        elif args.configure_asterisk:
            # Configure Asterisk only
            if not check_root_privileges():
                sys.exit(1)
            create_asterisk_config(ASTERISK_CONFIGS, args.verbose)

        elif args.verify:
            # Verify installation only
            if not check_root_privileges():
                sys.exit(1)
            verify_installation(args.verbose)

        elif args.full_setup:
            # Full setup process
            perform_voip_setup(verbose=args.verbose)

        else:
            # No specific action, show available operations
            print_header("Ubuntu VoIP Setup Utility")
            print("Available Operations:")
            print()
            print("1. Check system compatibility")
            print("2. Update system packages")
            print("3. Install VoIP packages")
            print("4. Configure firewall")
            print("5. Configure Asterisk")
            print("6. Verify installation")
            print("7. Full VoIP setup (all steps)")
            print()

            try:
                choice = input("Enter your choice (1-7) or 'q' to quit: ")

                if choice.lower() == "q":
                    print("Exiting...")
                    sys.exit(0)

                choice = int(choice.strip())

                if choice < 1 or choice > 7:
                    print_error("Invalid choice.")
                    sys.exit(1)

                if not check_root_privileges():
                    sys.exit(1)

                if choice == 1:
                    # System compatibility check
                    check_root_privileges()
                    check_dependencies()
                    check_internet_connectivity()
                    system_info = get_system_info()
                    print_section("System Information")
                    for key, value in system_info.items():
                        print(f"{key.replace('_', ' ').title()}: {value}")

                elif choice == 2:
                    # Update system
                    update_system(args.verbose)

                elif choice == 3:
                    # Install VoIP packages
                    install_packages(VOIP_PACKAGES, args.verbose)

                elif choice == 4:
                    # Configure firewall
                    configure_firewall(FIREWALL_RULES, args.verbose)

                elif choice == 5:
                    # Configure Asterisk
                    create_asterisk_config(ASTERISK_CONFIGS, args.verbose)

                elif choice == 6:
                    # Verify installation
                    verify_installation(args.verbose)

                elif choice == 7:
                    # Full setup process
                    perform_voip_setup(verbose=args.verbose)

            except ValueError:
                print_error("Invalid input. Please enter a number.")
                sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup interrupted by user.{Colors.ENDC}")
        sys.exit(130)

    except Exception as e:
        print(f"\n{Colors.RED}Setup failed: {e}{Colors.ENDC}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
