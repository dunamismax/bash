#!/usr/bin/env python3
"""
Simple Python Development Environment Setup

Sets up basic Python development environment components.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import json
from pathlib import Path


class PythonDevSetup:
    """
    Manages Python development environment setup.
    """

    def __init__(self, verbose=False):
        """
        Initialize setup with optional verbose mode.

        Args:
            verbose (bool): Enable detailed output
        """
        self.verbose = verbose
        self.home = os.path.expanduser("~")
        self.config_dir = os.path.join(self.home, ".python_dev_setup")
        self.log_file = os.path.join(self.config_dir, "setup.log")

    def _run_command(self, cmd, capture_output=True, check=True):
        """
        Run a shell command with optional output capture.

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
        Check system compatibility and requirements.
        """
        # Check operating system
        os_name = platform.system().lower()
        if os_name != "linux":
            print(f"Warning: This script is designed for Linux, not {os_name}")

        # Check Python version
        py_version = platform.python_version()
        print(f"Current Python version: {py_version}")

        # Check for essential tools
        required_tools = ["git", "curl", "gcc"]
        missing_tools = [tool for tool in required_tools if not shutil.which(tool)]

        if missing_tools:
            print(f"Missing tools: {', '.join(missing_tools)}")
            print("Please install these tools before continuing.")
            sys.exit(1)

    def install_system_dependencies(self):
        """
        Install system-level dependencies for Python development.
        """
        # List of typical build dependencies
        dependencies = [
            "build-essential",
            "libssl-dev",
            "zlib1g-dev",
            "libbz2-dev",
            "libreadline-dev",
            "libsqlite3-dev",
            "libncurses5-dev",
            "libncursesw5-dev",
            "xz-utils",
            "tk-dev",
            "libffi-dev",
            "liblzma-dev",
            "python3-dev",
        ]

        try:
            # Update package lists
            self._run_command(["sudo", "apt-get", "update"])

            # Install dependencies
            self._run_command(["sudo", "apt-get", "install", "-y"] + dependencies)

            print("System dependencies installed successfully.")
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)

    def setup_virtual_environment(self, project_path=None):
        """
        Set up a Python virtual environment.

        Args:
            project_path (str, optional): Path to create virtual environment
        """
        if not project_path:
            project_path = os.getcwd()

        try:
            # Ensure venv is available
            self._run_command(["python3", "-m", "venv", "--help"])

            # Create virtual environment
            venv_path = os.path.join(project_path, ".venv")
            self._run_command(["python3", "-m", "venv", venv_path])

            print(f"Virtual environment created at: {venv_path}")

            # Create activation script
            activate_script = os.path.join(project_path, "activate")
            with open(activate_script, "w") as f:
                f.write(f"""#!/bin/bash
# Activate Python virtual environment
source {venv_path}/bin/activate
""")
            os.chmod(activate_script, 0o755)

            print(f"Activation script created: {activate_script}")
        except Exception as e:
            print(f"Error setting up virtual environment: {e}")
            sys.exit(1)

    def install_development_tools(self):
        """
        Install common Python development tools via pip.
        """
        try:
            # Use pip to install development tools
            tools = [
                "pip",
                "setuptools",
                "wheel",
                "black",
                "isort",
                "mypy",
                "flake8",
                "pytest",
            ]

            # Install tools in user space to avoid system-wide changes
            self._run_command(
                ["python3", "-m", "pip", "install", "--user", "--upgrade"] + tools
            )

            print("Development tools installed successfully.")
        except Exception as e:
            print(f"Error installing development tools: {e}")
            sys.exit(1)

    def create_project_template(self, project_name):
        """
        Create a basic Python project template.

        Args:
            project_name (str): Name of the project
        """
        try:
            # Create project directory
            project_path = os.path.join(os.getcwd(), project_name)
            os.makedirs(project_path, exist_ok=True)

            # Create project structure
            os.makedirs(os.path.join(project_path, project_name), exist_ok=True)
            os.makedirs(os.path.join(project_path, "tests"), exist_ok=True)

            # Create initial files
            init_file = os.path.join(project_path, project_name, "__init__.py")
            main_file = os.path.join(project_path, project_name, "main.py")
            test_file = os.path.join(project_path, "tests", "test_main.py")
            readme_file = os.path.join(project_path, "README.md")
            requirements_file = os.path.join(project_path, "requirements.txt")

            # Write initial content
            with open(init_file, "w") as f:
                f.write("# Package initialization\n")

            with open(main_file, "w") as f:
                f.write("""def main():
    print("Hello, World!")

if __name__ == '__main__':
    main()
""")

            with open(test_file, "w") as f:
                f.write("""def test_main():
    assert True  # Placeholder test
""")

            with open(readme_file, "w") as f:
                f.write(f"# {project_name}\n\nA Python project.\n")

            with open(requirements_file, "w") as f:
                f.write("# Add project dependencies here\n")

            # Setup virtual environment for the project
            self.setup_virtual_environment(project_path)

            print(f"Project template created: {project_path}")
        except Exception as e:
            print(f"Error creating project template: {e}")
            sys.exit(1)


def main():
    """
    Main entry point for the Python development setup script.
    """
    parser = argparse.ArgumentParser(description="Python Development Environment Setup")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--setup-deps", action="store_true", help="Install system dependencies"
    )
    parser.add_argument(
        "--venv", type=str, help="Create virtual environment in specified path"
    )
    parser.add_argument(
        "--dev-tools", action="store_true", help="Install development tools"
    )
    parser.add_argument(
        "--new-project", type=str, help="Create a new Python project template"
    )

    args = parser.parse_args()

    # Instantiate setup
    setup = PythonDevSetup(verbose=args.verbose)

    # Run selected operations
    if args.setup_deps:
        setup.check_system()
        setup.install_system_dependencies()

    if args.venv:
        setup.setup_virtual_environment(args.venv)

    if args.dev_tools:
        setup.install_development_tools()

    if args.new_project:
        setup.create_project_template(args.new_project)

    # If no arguments, show help
    if not any(vars(args).values()):
        parser.print_help()


if __name__ == "__main__":
    main()
