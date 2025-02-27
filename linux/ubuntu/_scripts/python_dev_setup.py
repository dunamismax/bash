#!/usr/bin/env python3
"""
Simple Python Development Environment Setup

This script sets up basic Python development environment components:
  • System checks and dependency verification
  • Installation of system-level dependencies
  • Virtual environment creation with an activation script
  • Installation of common Python development tools via pip
  • Creation of a basic Python project template

Usage:
  python3 python_dev_setup.py [OPTIONS]

Example:
  python3 python_dev_setup.py --setup-deps --dev-tools --new-project MyProject
"""

import argparse
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

#####################################
# Nord Themed ANSI Colors for CLI Output
#####################################


class NordColors:
    """
    Nord-themed ANSI color codes.
    """

    HEADER = "\033[38;2;216;222;233m"  # Light gray
    INFO = "\033[38;2;136;192;208m"  # Light blue
    SUCCESS = "\033[38;2;163;190;140m"  # Green
    WARNING = "\033[38;2;235;203;139m"  # Yellow
    ERROR = "\033[38;2;191;97;106m"  # Red
    RESET = "\033[0m"
    BOLD = "\033[1m"


#####################################
# Logging Setup with Colors
#####################################


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: NordColors.INFO,
        logging.INFO: NordColors.INFO,
        logging.WARNING: NordColors.WARNING,
        logging.ERROR: NordColors.ERROR,
        logging.CRITICAL: NordColors.ERROR,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, NordColors.RESET)
        record.msg = f"{color}{record.msg}{NordColors.RESET}"
        return super().format(record)


def setup_logging(log_file: str) -> logging.Logger:
    """
    Configure logging with console and file handlers.

    Args:
        log_file (str): Path to the log file.

    Returns:
        logging.Logger: Configured logger.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter_str = "[%(asctime)s] [%(levelname)s] %(message)s"
    datefmt_str = "%Y-%m-%d %H:%M:%S"

    # Console handler with color formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColorFormatter(fmt=formatter_str, datefmt=datefmt_str)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler without ANSI codes
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            backup = log_file + f".{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.move(log_file, backup)
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(fmt=formatter_str, datefmt=datefmt_str)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(log_file, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {e}")

    return logger


#####################################
# Python Development Environment Setup Class
#####################################


class PythonDevSetup:
    """
    Manages the setup of a Python development environment.
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize the setup with optional verbose mode.

        Args:
            verbose (bool): Enable detailed output.
        """
        self.verbose = verbose
        self.home: str = os.path.expanduser("~")
        self.config_dir: str = os.path.join(self.home, ".python_dev_setup")
        self.log_file: str = os.path.join(self.config_dir, "setup.log")
        self.logger = setup_logging(self.log_file)

        # Register signal handlers for graceful interruption.
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        """
        Handle interrupt signals gracefully.
        """
        self.logger.warning("Setup interrupted by signal.")
        sys.exit(130)

    def _run_command(
        self, cmd: List[str], capture_output: bool = True, check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a shell command with error handling.

        Args:
            cmd (List[str]): Command to execute.
            capture_output (bool): Capture command output.
            check (bool): Raise exception on non-zero exit status.

        Returns:
            subprocess.CompletedProcess: Result of command execution.
        """
        try:
            if self.verbose:
                self.logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=capture_output, text=True, check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {' '.join(cmd)}")
            self.logger.error(f"Stdout: {e.stdout}")
            self.logger.error(f"Stderr: {e.stderr}")
            raise

    def check_system(self) -> None:
        """
        Check system compatibility and essential requirements.
        """
        os_name = platform.system().lower()
        if os_name != "linux":
            self.logger.warning(f"This script is designed for Linux, not {os_name}.")
        py_version = platform.python_version()
        self.logger.info(f"Current Python version: {py_version}")
        required_tools = ["git", "curl", "gcc"]
        missing_tools = [tool for tool in required_tools if not shutil.which(tool)]
        if missing_tools:
            self.logger.error(
                f"Missing required tools: {', '.join(missing_tools)}. Install these before continuing."
            )
            sys.exit(1)

    def install_system_dependencies(self) -> None:
        """
        Install system-level dependencies for Python development.
        """
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
            self._run_command(["sudo", "apt-get", "update"])
            self._run_command(["sudo", "apt-get", "install", "-y"] + dependencies)
            self.logger.info("System dependencies installed successfully.")
        except Exception as e:
            self.logger.error(f"Error installing system dependencies: {e}")
            sys.exit(1)

    def setup_virtual_environment(self, project_path: Optional[str] = None) -> None:
        """
        Set up a Python virtual environment in the specified project path.

        Args:
            project_path (Optional[str]): Directory for the virtual environment.
                Defaults to the current working directory.
        """
        if not project_path:
            project_path = os.getcwd()
        try:
            # Verify that the venv module is available.
            self._run_command(["python3", "-m", "venv", "--help"])
            venv_path = os.path.join(project_path, ".venv")
            self._run_command(["python3", "-m", "venv", venv_path])
            self.logger.info(f"Virtual environment created at: {venv_path}")

            # Create an activation script.
            activate_script = os.path.join(project_path, "activate")
            with open(activate_script, "w") as f:
                f.write(f"""#!/bin/bash
# Activate Python virtual environment
source {venv_path}/bin/activate
""")
            os.chmod(activate_script, 0o755)
            self.logger.info(f"Activation script created at: {activate_script}")
        except Exception as e:
            self.logger.error(f"Error setting up virtual environment: {e}")
            sys.exit(1)

    def install_development_tools(self) -> None:
        """
        Install common Python development tools via pip.
        """
        try:
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
            self._run_command(
                ["python3", "-m", "pip", "install", "--user", "--upgrade"] + tools
            )
            self.logger.info("Development tools installed successfully.")
        except Exception as e:
            self.logger.error(f"Error installing development tools: {e}")
            sys.exit(1)

    def create_project_template(self, project_name: str) -> None:
        """
        Create a basic Python project template.

        Args:
            project_name (str): Name of the new project.
        """
        try:
            project_path = os.path.join(os.getcwd(), project_name)
            os.makedirs(project_path, exist_ok=True)
            # Create package and test directories.
            package_dir = os.path.join(project_path, project_name)
            tests_dir = os.path.join(project_path, "tests")
            os.makedirs(package_dir, exist_ok=True)
            os.makedirs(tests_dir, exist_ok=True)

            # Create initial files.
            init_file = os.path.join(package_dir, "__init__.py")
            main_file = os.path.join(package_dir, "main.py")
            test_file = os.path.join(tests_dir, "test_main.py")
            readme_file = os.path.join(project_path, "README.md")
            requirements_file = os.path.join(project_path, "requirements.txt")

            with open(init_file, "w") as f:
                f.write("# Package initialization\n")
            with open(main_file, "w") as f:
                f.write(
                    "def main():\n"
                    "    print('Hello, World!')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                )
            with open(test_file, "w") as f:
                f.write("def test_main():\n    assert True  # Placeholder test\n")
            with open(readme_file, "w") as f:
                f.write(f"# {project_name}\n\nA Python project.\n")
            with open(requirements_file, "w") as f:
                f.write("# Add project dependencies here\n")

            # Set up a virtual environment within the project.
            self.setup_virtual_environment(project_path)
            self.logger.info(f"Project template created at: {project_path}")
        except Exception as e:
            self.logger.error(f"Error creating project template: {e}")
            sys.exit(1)


#####################################
# Main Function and Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Setup a Python development environment with system checks, "
        "virtual environment creation, and project templating."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--setup-deps", action="store_true", help="Install system dependencies"
    )
    parser.add_argument(
        "--venv", type=str, help="Create a virtual environment in the specified path"
    )
    parser.add_argument(
        "--dev-tools", action="store_true", help="Install development tools via pip"
    )
    parser.add_argument(
        "--new-project",
        type=str,
        help="Create a new Python project template with the given name",
    )
    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the Python development environment setup.
    """
    args = parse_arguments()
    setup = PythonDevSetup(verbose=args.verbose)

    if args.setup_deps:
        setup.check_system()
        setup.install_system_dependencies()

    if args.venv:
        setup.setup_virtual_environment(args.venv)

    if args.dev_tools:
        setup.install_development_tools()

    if args.new_project:
        setup.create_project_template(args.new_project)

    # If no arguments are provided, display help.
    if not any(vars(args).values()):
        parser = argparse.ArgumentParser(
            description="Setup a Python development environment."
        )
        parser.print_help()


if __name__ == "__main__":
    main()
