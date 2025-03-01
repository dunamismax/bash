#!/usr/bin/env python3
"""
Unattended Python Development Environment Setup for Ubuntu/Linux
----------------------------------------------------------------

This script automatically sets up a complete Python development environment
by installing required system packages, pyenv, latest Python version, and
essential development tools.

Features:
  • System dependency installation
  • pyenv installation and configuration
  • Latest Python version installation via pyenv
  • pipx installation and configuration
  • Essential Python tools installation

Run with sudo, no arguments needed.
"""

import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import getpass
from pathlib import Path

# ==============================
# Configuration & Constants
# ==============================
VERSION = "1.0.0"

# Get the original non-root user if the script is run with sudo
ORIGINAL_USER = os.environ.get("SUDO_USER", getpass.getuser())
ORIGINAL_UID = int(
    subprocess.check_output(["id", "-u", ORIGINAL_USER]).decode().strip()
)
ORIGINAL_GID = int(
    subprocess.check_output(["id", "-g", ORIGINAL_USER]).decode().strip()
)

# Get the original user's home directory
if ORIGINAL_USER != "root":
    HOME_DIR = (
        subprocess.check_output(["getent", "passwd", ORIGINAL_USER])
        .decode()
        .split(":")[5]
    )
else:
    HOME_DIR = os.path.expanduser("~")

PYENV_DIR = os.path.join(HOME_DIR, ".pyenv")
PYENV_BIN = os.path.join(PYENV_DIR, "bin", "pyenv")

# System packages
SYSTEM_DEPENDENCIES = [
    "build-essential",
    "libssl-dev",
    "zlib1g-dev",
    "libbz2-dev",
    "libreadline-dev",
    "libsqlite3-dev",
    "libncurses5-dev",
    "libncursesw5-dev",
    "python3-rich",
    "python3-pyfiglet",
    "xz-utils",
    "tk-dev",
    "libffi-dev",
    "liblzma-dev",
    "python3-dev",
    "git",
    "curl",
    "wget",
]

# Python tools to install with pipx
PIPX_TOOLS = [
    "black",
    "isort",
    "flake8",
    "mypy",
    "pytest",
    "pre-commit",
    "ipython",
    "cookiecutter",
    "pylint",
    "sphinx",
    "twine",
    "autopep8",
    "bandit",
    "poetry",
    "pydocstyle",
    "yapf",
    "httpie",
]


# ==============================
# Helper Functions
# ==============================
def print_step(message):
    """Print a step in the setup process."""
    print(f"[+] {message}")


def print_success(message):
    """Print a success message."""
    print(f"[✓] {message}")


def print_warning(message):
    """Print a warning message."""
    print(f"[!] {message}")


def print_error(message):
    """Print an error message."""
    print(f"[✗] {message}")


def run_command(
    cmd, shell=False, check=True, capture_output=True, timeout=300, as_user=False
):
    """
    Run a shell command and handle errors.

    If as_user is True, runs the command as the original non-root user
    when the script is run with sudo.
    """
    # If we need to run as the original user and the command isn't already prefixed
    if as_user and ORIGINAL_USER != "root" and not (cmd and cmd[0] == "sudo"):
        # Modify the command to run as the original user
        cmd = ["sudo", "-u", ORIGINAL_USER] + cmd

    try:
        # Execute the command
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        cmd_str = cmd if shell else " ".join(cmd)
        print_error(f"Command failed: {cmd_str}")
        if hasattr(e, "stdout") and e.stdout:
            print(f"Stdout: {e.stdout.strip()}")
        if hasattr(e, "stderr") and e.stderr:
            print(f"Error Output: {e.stderr.strip()}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise


def fix_ownership(path, recursive=True):
    """Fix ownership of files to be owned by the original user, not root."""
    if ORIGINAL_USER == "root":
        return  # No need to change if we're already running as root

    if recursive and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for d in dirs:
                os.chown(os.path.join(root, d), ORIGINAL_UID, ORIGINAL_GID)
            for f in files:
                os.chown(os.path.join(root, f), ORIGINAL_UID, ORIGINAL_GID)

    # Change the parent path itself
    if os.path.exists(path):
        os.chown(path, ORIGINAL_UID, ORIGINAL_GID)


def check_command_available(command):
    """Check if a command is available in PATH."""
    return shutil.which(command) is not None


# ==============================
# Core Setup Functions
# ==============================
def check_system():
    """Check system compatibility and required tools."""
    print_step("Checking system compatibility...")

    # Verify root privileges
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges (sudo).")
        sys.exit(1)

    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")
        print_warning("Continuing anyway, but some steps might fail.")

    # Print basic system information
    print(f"Python Version: {platform.python_version()}")
    print(f"Operating System: {platform.platform()}")
    print(f"Running as: root")
    print(f"Setting up for user: {ORIGINAL_USER}")
    print(f"User home directory: {HOME_DIR}")

    required_tools = ["git", "curl", "gcc"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]

    if missing:
        print_warning(
            f"Missing required tools: {', '.join(missing)}. These will be installed."
        )
    else:
        print_success("All basic required tools are present.")

    print_success("System check completed.")
    return True


def install_system_dependencies():
    """Install system-level dependencies using apt-get."""
    print_step("Installing system dependencies...")

    try:
        # Update package lists
        print_step("Updating package lists...")
        try:
            run_command(["apt-get", "update"])
            print_success("Package lists updated.")
        except Exception as e:
            print_error(f"Failed to update package lists: {e}")
            return False

        # Install system dependencies
        for package in SYSTEM_DEPENDENCIES:
            try:
                print_step(f"Installing {package}...")
                run_command(["apt-get", "install", "-y", package])
                print_success(f"{package} installed.")
            except Exception as e:
                print_error(f"Failed to install {package}: {e}")

        print_success("System dependencies installed successfully.")
        return True
    except Exception as e:
        print_error(f"Error installing system dependencies: {e}")
        return False


def install_pyenv():
    """Install pyenv for the target user."""
    print_step("Installing pyenv...")

    # Check if pyenv is already installed
    if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
        print_success("pyenv is already installed.")
        return True

    try:
        # Get the pyenv installer
        print_step("Downloading pyenv installer...")
        installer_script = "/tmp/pyenv_installer.sh"
        curl_cmd = ["curl", "-fsSL", "https://pyenv.run", "-o", installer_script]
        run_command(curl_cmd)

        # Make it executable
        os.chmod(installer_script, 0o755)

        print_step("Running pyenv installer...")

        # Run the installer as the original user
        if ORIGINAL_USER != "root":
            run_command(["sudo", "-u", ORIGINAL_USER, installer_script], as_user=True)
        else:
            run_command([installer_script])

        # Check if installation was successful
        if os.path.exists(PYENV_DIR) and os.path.isfile(PYENV_BIN):
            print_success("pyenv installed successfully.")

            # Setup shell integration
            print_step("Setting up shell configuration...")
            shell_rc_files = [
                os.path.join(HOME_DIR, ".bashrc"),
                os.path.join(HOME_DIR, ".zshrc"),
            ]

            pyenv_init_lines = [
                "\n# pyenv initialization",
                'export PYENV_ROOT="$HOME/.pyenv"',
                'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"',
                'eval "$(pyenv init -)"',
                'eval "$(pyenv virtualenv-init -)"',
                "",
            ]

            for rc_file in shell_rc_files:
                if os.path.exists(rc_file):
                    # Read the content
                    with open(rc_file, "r") as f:
                        content = f.read()

                    # Only add if not already there
                    if "pyenv init" not in content:
                        # Write as the original user
                        if ORIGINAL_USER != "root":
                            # Create a temp file with the content to append
                            temp_file = "/tmp/pyenv_init.txt"
                            with open(temp_file, "w") as f:
                                f.write("\n".join(pyenv_init_lines))

                            # Append it to the rc file as the original user
                            run_command(
                                [
                                    "sudo",
                                    "-u",
                                    ORIGINAL_USER,
                                    "bash",
                                    "-c",
                                    f"cat {temp_file} >> {rc_file}",
                                ],
                                as_user=True,
                            )
                            os.remove(temp_file)
                        else:
                            with open(rc_file, "a") as f:
                                f.write("\n".join(pyenv_init_lines))

                        print_success(f"Added pyenv initialization to {rc_file}")

            # Fix ownership of pyenv directory
            fix_ownership(PYENV_DIR)

            return True
        else:
            print_error("pyenv installation failed.")
            return False

    except Exception as e:
        print_error(f"Error installing pyenv: {e}")
        return False


def install_latest_python_with_pyenv():
    """Install the latest Python version using pyenv."""
    print_step("Installing latest Python with pyenv...")

    if not os.path.exists(PYENV_BIN):
        print_error("pyenv is not installed. Please install it first.")
        return False

    try:
        # Define command to run pyenv as the original user
        pyenv_cmd = [PYENV_BIN]
        if ORIGINAL_USER != "root":
            pyenv_cmd = ["sudo", "-u", ORIGINAL_USER, PYENV_BIN]

        # Update pyenv repository first
        print_step("Updating pyenv repository...")
        pyenv_root = os.path.dirname(os.path.dirname(PYENV_BIN))

        # Use git pull to update the pyenv repository
        if os.path.exists(os.path.join(pyenv_root, ".git")):
            if ORIGINAL_USER != "root":
                run_command(
                    ["sudo", "-u", ORIGINAL_USER, "git", "-C", pyenv_root, "pull"],
                    as_user=True,
                )
            else:
                run_command(["git", "-C", pyenv_root, "pull"])
        else:
            print_warning(
                "Could not update pyenv (not a git repository). Continuing anyway."
            )

        # Get latest Python version available
        print_step("Finding latest Python version...")
        latest_version_output = run_command(
            pyenv_cmd + ["install", "--list"], as_user=(ORIGINAL_USER != "root")
        ).stdout

        # Parse the output to find the latest stable Python version
        versions = re.findall(
            r"^\s*(\d+\.\d+\.\d+)$", latest_version_output, re.MULTILINE
        )
        if not versions:
            print_error("Could not find any Python versions to install.")
            return False

        # Sort versions and get the latest
        latest_version = sorted(versions, key=lambda v: [int(i) for i in v.split(".")])[
            -1
        ]

        print_step(
            f"Installing Python {latest_version} (this may take several minutes)..."
        )

        # Install the latest version
        run_command(
            pyenv_cmd + ["install", "--skip-existing", latest_version],
            as_user=(ORIGINAL_USER != "root"),
        )

        # Set as global Python version
        print_step("Setting as global Python version...")
        run_command(
            pyenv_cmd + ["global", latest_version], as_user=(ORIGINAL_USER != "root")
        )

        # Verify installation
        pyenv_python = os.path.join(PYENV_DIR, "shims", "python")
        if os.path.exists(pyenv_python):
            # Run the Python version check as the original user
            if ORIGINAL_USER != "root":
                python_version = run_command(
                    ["sudo", "-u", ORIGINAL_USER, pyenv_python, "--version"],
                    as_user=True,
                ).stdout
            else:
                python_version = run_command([pyenv_python, "--version"]).stdout

            print_success(f"Successfully installed {python_version.strip()}")
            return True
        else:
            print_error("Python installation with pyenv failed.")
            return False

    except Exception as e:
        print_error(f"Error installing Python with pyenv: {e}")
        return False


def install_pipx():
    """Ensure pipx is installed for the user."""
    print_step("Installing pipx...")

    # Check if pipx is available in PATH
    if check_command_available("pipx"):
        print_success("pipx is already installed.")
        return True

    try:
        # Try to get python executable
        if ORIGINAL_USER != "root":
            # Use the original user's Python if possible
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = "python3"

            # Install pipx as the original user
            print_step(f"Installing pipx for user {ORIGINAL_USER}...")
            run_command(
                [
                    "sudo",
                    "-u",
                    ORIGINAL_USER,
                    python_cmd,
                    "-m",
                    "pip",
                    "install",
                    "--user",
                    "pipx",
                ],
                as_user=True,
            )
            run_command(
                ["sudo", "-u", ORIGINAL_USER, python_cmd, "-m", "pipx", "ensurepath"],
                as_user=True,
            )
        else:
            # Running as actual root, install normally
            python_cmd = os.path.join(PYENV_DIR, "shims", "python")
            if not os.path.exists(python_cmd):
                python_cmd = shutil.which("python3") or shutil.which("python")

            if not python_cmd:
                print_error("Could not find a Python executable.")
                return False

            print_step("Installing pipx...")
            run_command([python_cmd, "-m", "pip", "install", "pipx"])
            run_command([python_cmd, "-m", "pipx", "ensurepath"])

        # Verify installation
        user_bin_dir = os.path.join(HOME_DIR, ".local", "bin")
        pipx_path = os.path.join(user_bin_dir, "pipx")

        if os.path.exists(pipx_path) or check_command_available("pipx"):
            print_success("pipx installed successfully.")
            return True
        else:
            print_error("pipx installation could not be verified.")
            return False

    except Exception as e:
        print_error(f"Error installing pipx: {e}")
        return False


def install_pipx_tools():
    """Install Python tools via pipx."""
    print_step("Installing Python tools via pipx...")

    # Make sure pipx is installed
    if not check_command_available("pipx"):
        # Install pipx system-wide first
        print_step("Installing pipx system-wide...")
        try:
            run_command(["apt-get", "install", "-y", "pipx"])
        except Exception as e:
            print_warning(f"Could not install pipx via apt: {e}")
            # If apt installation failed, fall back to pip
            if not install_pipx():
                print_error("Failed to ensure pipx installation.")
                return False

    # Determine pipx command
    pipx_cmd = shutil.which("pipx")
    if not pipx_cmd:
        print_error("Could not find pipx executable.")
        return False

    failed_tools = []

    # For each tool, figure out the best way to install it
    for tool in PIPX_TOOLS:
        try:
            print_step(f"Installing {tool}...")

            # First, try to install via apt if available
            apt_pkg = f"python3-{tool.lower()}"
            try:
                apt_check = run_command(["apt-cache", "show", apt_pkg], check=False)
                if apt_check.returncode == 0:
                    run_command(["apt-get", "install", "-y", apt_pkg])
                    print_success(f"Installed {tool} via apt.")
                    continue
            except Exception:
                pass  # If apt fails, continue to pipx

            # Try using pipx (which creates isolated environments)
            run_command([pipx_cmd, "install", tool, "--force"])
            print_success(f"Installed {tool} via pipx.")

        except Exception as e:
            print_warning(f"Failed to install {tool}: {e}")
            failed_tools.append(tool)

    if failed_tools:
        print_warning(
            f"Failed to install the following tools: {', '.join(failed_tools)}"
        )
        if len(failed_tools) < len(PIPX_TOOLS) / 2:  # If more than half succeeded
            return True
        return False

    print_success("Python tools installation completed.")
    return True


def install_rich_and_pyfiglet():
    """Install rich and pyfiglet using pip as the original non-root user with override flag."""
    print_step("Installing rich and pyfiglet as non-root user...")

    # Base command using the non-root user's Python, with the override flag.
    base_cmd = [
        "sudo",
        "-H",
        "-u",
        ORIGINAL_USER,
        "python3",
        "-m",
        "pip",
        "install",
        "--break-system-packages",
    ]

    # Install rich
    try:
        run_command(base_cmd + ["rich"], as_user=False)
        print_success("rich installed successfully.")
    except Exception as e:
        print_warning(f"Failed to install rich: {e}")

    # Install pyfiglet
    try:
        run_command(base_cmd + ["pyfiglet"], as_user=False)
        print_success("pyfiglet installed successfully.")
    except Exception as e:
        print_warning(f"Failed to install pyfiglet: {e}")


# ==============================
# Main Setup Process
# ==============================
def run_full_setup():
    """Run the complete unattended setup process."""
    print("\n" + "=" * 60)
    print(f"Python Development Environment Setup v{VERSION}")
    print("=" * 60 + "\n")

    print_step("Starting unattended setup...")

    if not check_system():
        print_error("System check failed. Aborting setup.")
        sys.exit(1)

    # Install system dependencies
    print_step("Installing system dependencies...")
    if not install_system_dependencies():
        print_warning("Some system dependencies may not have been installed.")
        # Continue anyway in unattended mode

    # Install pyenv
    print_step("Installing pyenv...")
    if not install_pyenv():
        print_warning("pyenv installation failed.")
        # Continue anyway in unattended mode

    # Install latest Python with pyenv
    print_step("Installing latest Python version with pyenv...")
    if not install_latest_python_with_pyenv():
        print_warning("Python installation with pyenv failed.")
        # Continue anyway in unattended mode

    # Install pipx and Python tools
    print_step("Installing pipx and Python tools...")
    if not install_pipx_tools():
        print_warning("Some Python tools may not have been installed.")

    # Final summary
    print("\n" + "=" * 60)
    print("Setup Summary")
    print("=" * 60)

    # Check system dependencies
    sys_deps_status = "✓ Installed" if check_command_available("gcc") else "× Failed"
    print(f"System Dependencies: {sys_deps_status}")

    # Check pyenv
    pyenv_status = "✓ Installed" if os.path.exists(PYENV_BIN) else "× Failed"
    print(f"pyenv: {pyenv_status}")

    # Check Python installation
    python_installed = os.path.exists(os.path.join(PYENV_DIR, "shims", "python"))
    python_status = "✓ Installed" if python_installed else "× Failed"
    print(f"Python (via pyenv): {python_status}")

    # Check pipx installation
    pipx_installed = check_command_available("pipx") or os.path.exists(
        os.path.join(HOME_DIR, ".local/bin/pipx")
    )
    pipx_status = "✓ Installed" if pipx_installed else "× Failed"
    print(f"pipx: {pipx_status}")

    # <<-- New function call to install rich and pyfiglet -->
    install_rich_and_pyfiglet()

    # Shell reloading instructions
    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
    print("\nNext Steps:")
    print(
        f"To fully apply all changes, {ORIGINAL_USER} should restart their terminal or run:"
    )
    print(f"source ~/.{shell_name}rc")

    print("\n✓ Setup process completed!")


# ==============================
# Main Entry Point
# ==============================
def main():
    """Main entry point for the script."""
    try:
        # Setup signal handlers for clean exits
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: sys.exit(128 + signum))

        # Check if running as root
        if os.geteuid() != 0:
            print_error("This script must be run with root privileges.")
            print_error("Please run it with sudo.")
            sys.exit(1)

        # Run the full unattended setup
        run_full_setup()

    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
