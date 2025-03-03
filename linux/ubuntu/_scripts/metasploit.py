#!/usr/bin/env python3
"""
Metasploit Framework Installer
------------------------------

An automated installer and configuration tool for the Metasploit Framework.
Features clean installation, database setup, and interactive configuration.

Features:
  • Downloads and installs the latest Metasploit Framework
  • Configures PostgreSQL database for Metasploit
  • Verifies system requirements and dependencies
  • Provides a streamlined setup experience

Run with: sudo python3 metasploit_installer.py
"""

import atexit
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from typing import List, Dict, Optional, Any, Tuple

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.prompt import Confirm
    from rich.live import Live
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing them now...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"], check=True
        )
        print("Successfully installed required libraries. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Failed to install required libraries: {e}")
        print("Please install them manually: pip install rich pyfiglet")
        sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "2.0.0"
APP_NAME = "Metasploit Installer"
APP_SUBTITLE = "Framework Setup & Configuration"

# Command timeouts (in seconds)
DEFAULT_TIMEOUT = 300
INSTALLATION_TIMEOUT = 1200  # 20 minutes for installation on slow machines

# Installer URL
INSTALLER_URL = "https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb"
INSTALLER_PATH = "/tmp/msfinstall"

# System dependencies that might be needed
SYSTEM_DEPENDENCIES = [
    "build-essential",
    "libpq-dev",
    "postgresql",
    "postgresql-contrib",
    "curl",
    "git",
    "nmap",
]


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Try different fonts
    fonts = ["slant", "big", "small", "standard", "digital"]

    # Try each font until we find one that works well
    for font_name in fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    ascii_lines = ascii_art.split("\n")
    for i, line in enumerate(ascii_lines):
        if line.strip():
            color = colors[i % len(colors)]
            styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 50 + "[/]"
    styled_text = tech_border + "\n" + styled_text.rstrip() + "\n" + tech_border

    # Create a panel with sufficient padding
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_3, "➜")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        shell: Whether to run the command in a shell

    Returns:
        CompletedProcess instance with command results
    """
    try:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        print_message(
            f"Running: {cmd_str[:80]}{'...' if len(cmd_str) > 80 else ''}",
            NordColors.SNOW_STORM_1,
            "→",
        )

        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            shell=shell,
        )
        return result
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        print_error(f"Command failed: {cmd_str}")
        if hasattr(e, "stdout") and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if hasattr(e, "stderr") and e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def check_command_available(command):
    """Return True if the command is available in the PATH."""
    return shutil.which(command) is not None


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up temporary files...", NordColors.FROST_3)
    if os.path.exists(INSTALLER_PATH):
        try:
            os.remove(INSTALLER_PATH)
            print_success(f"Removed temporary installer at {INSTALLER_PATH}")
        except Exception as e:
            print_warning(f"Failed to remove temporary installer: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Core Setup Functions
# ----------------------------------------------------------------
def check_system():
    """Check system compatibility and required tools."""
    print_step("Checking system compatibility...")

    # Check OS
    os_name = platform.system().lower()
    if os_name != "linux":
        print_warning(f"This script is designed for Linux, not {os_name}.")

    # Check if we're on Ubuntu/Debian
    is_ubuntu = False
    is_debian = False
    try:
        with open("/etc/os-release", "r") as f:
            os_release = f.read().lower()
            is_ubuntu = "ubuntu" in os_release
            is_debian = "debian" in os_release
    except FileNotFoundError:
        pass

    if not (is_ubuntu or is_debian):
        print_warning(
            "This script is optimized for Ubuntu/Debian. It may not work correctly on your system."
        )

    # Check root privileges
    if os.geteuid() != 0:
        print_error("This script must be run with root privileges.")
        print_message(
            "Please run with: sudo python3 metasploit_installer.py", NordColors.YELLOW
        )
        return False

    # Create a system info table
    table = Table(
        show_header=False,
        box=None,
        border_style=NordColors.FROST_3,
        padding=(0, 2),
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)

    table.add_row("Python Version", platform.python_version())
    table.add_row("Operating System", platform.platform())
    table.add_row(
        "Distribution", "Ubuntu/Debian" if (is_ubuntu or is_debian) else "Unknown"
    )

    console.print(
        Panel(
            table,
            title="[bold]System Information[/bold]",
            border_style=NordColors.FROST_1,
            padding=(1, 2),
        )
    )

    # Check for required tools
    required_tools = ["curl", "git"]
    missing = [tool for tool in required_tools if not check_command_available(tool)]
    if missing:
        print_error(f"Missing required tools: {', '.join(missing)}")
        print_step("Installing missing tools...")
        try:
            run_command(["apt-get", "update"])
            for tool in missing:
                run_command(["apt-get", "install", "-y", tool])
            print_success("Required tools installed successfully.")
        except Exception as e:
            print_error(f"Failed to install required tools: {e}")
            return False
    else:
        print_success("All required tools are available.")

    return True


def install_system_dependencies():
    """Install system dependencies that might be needed by Metasploit."""
    print_step("Installing system dependencies...")

    try:
        with console.status("[bold blue]Updating package lists...", spinner="dots"):
            run_command(["apt-get", "update"])

        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Installing dependencies"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Installing", total=len(SYSTEM_DEPENDENCIES))

            for package in SYSTEM_DEPENDENCIES:
                try:
                    run_command(["apt-get", "install", "-y", package], check=False)
                    progress.advance(task)
                except Exception as e:
                    print_warning(f"Failed to install {package}: {e}")
                    progress.advance(task)

        print_success("System dependencies installed.")
        return True
    except Exception as e:
        print_error(f"Failed to install system dependencies: {e}")
        return False


def download_metasploit_installer():
    """Download the Metasploit installer script."""
    print_step("Downloading Metasploit installer...")

    try:
        with console.status("[bold blue]Downloading installer...", spinner="dots"):
            run_command(["curl", "-sSL", INSTALLER_URL, "-o", INSTALLER_PATH])

        if os.path.exists(INSTALLER_PATH):
            os.chmod(INSTALLER_PATH, 0o755)  # Make executable
            print_success("Metasploit installer downloaded and made executable.")
            return True
        else:
            print_error("Failed to download Metasploit installer.")
            return False
    except Exception as e:
        print_error(f"Error downloading installer: {e}")
        return False


def run_metasploit_installer():
    """Run the Metasploit installer script."""
    print_step("Running Metasploit installer...")

    display_panel(
        "Installing Metasploit Framework. This may take several minutes.\n"
        "The installer will download and set up all necessary components.",
        style=NordColors.FROST_3,
        title="Installation",
    )

    try:
        with console.status(
            "[bold blue]Installing Metasploit (this may take a while)...",
            spinner="dots",
        ):
            result = run_command([INSTALLER_PATH], timeout=INSTALLATION_TIMEOUT)

        print_success("Metasploit Framework installed successfully.")
        return True
    except Exception as e:
        print_error(f"Error during Metasploit installation: {e}")
        return False


def configure_postgresql():
    """Configure PostgreSQL for Metasploit if needed."""
    print_step("Configuring PostgreSQL for Metasploit...")

    try:
        # Check if PostgreSQL is running
        pg_status = run_command(["systemctl", "status", "postgresql"], check=False)
        if pg_status.returncode != 0:
            print_step("Starting PostgreSQL service...")
            run_command(["systemctl", "start", "postgresql"])
            run_command(["systemctl", "enable", "postgresql"])

        print_success("PostgreSQL is running.")
        return True
    except Exception as e:
        print_warning(f"PostgreSQL configuration error: {e}")
        print_message(
            "You may need to configure PostgreSQL manually later.", NordColors.YELLOW
        )
        return False


def check_installation():
    """Verify that Metasploit was installed correctly."""
    print_step("Verifying installation...")

    # Look for msfconsole in common locations
    possible_paths = [
        "/usr/bin/msfconsole",
        "/opt/metasploit-framework/bin/msfconsole",
        "/usr/local/bin/msfconsole",
    ]

    msfconsole_path = None
    for path in possible_paths:
        if os.path.exists(path):
            msfconsole_path = path
            break

    # Try PATH as a last resort
    if not msfconsole_path and check_command_available("msfconsole"):
        msfconsole_path = "msfconsole"

    if not msfconsole_path:
        print_error("Could not locate msfconsole. Installation might have failed.")
        return False

    try:
        with console.status(
            "[bold blue]Checking Metasploit version...", spinner="dots"
        ):
            version_result = run_command([msfconsole_path, "-v"], timeout=30)

        if (
            version_result.returncode == 0
            and "metasploit" in version_result.stdout.lower()
        ):
            # Extract and display the version
            version_lines = version_result.stdout.strip().split("\n")
            version_info = next(
                (line for line in version_lines if "Framework" in line), ""
            )

            print_success(f"Metasploit Framework installed successfully!")
            console.print(f"[{NordColors.FROST_1}]{version_info}[/]")

            # Display path information
            console.print(f"[{NordColors.FROST_2}]Location: {msfconsole_path}[/]")
            return msfconsole_path
        else:
            print_error("Metasploit verification failed.")
            return False
    except Exception as e:
        print_error(f"Error verifying Metasploit installation: {e}")
        return False


def launch_msfconsole(msfconsole_path):
    """Launch msfconsole for interactive configuration."""
    print_step("Launching Metasploit console for configuration...")

    display_panel(
        "Metasploit console will now start.\n\n"
        "If prompted, type 'yes' to set up the database.\n"
        "Once started, you can verify the database connection with the command:\n"
        "[bold]db_status[/]\n\n"
        "If the database is not connected, you can initialize it with:\n"
        "[bold]msfdb init[/]",
        style=NordColors.GREEN,
        title="Next Steps",
    )

    console.print()
    print_message(
        "Press Enter to continue to Metasploit console...", NordColors.FROST_2
    )
    input()

    try:
        # Replace the current process with msfconsole
        os.execvp(msfconsole_path, [msfconsole_path])
    except Exception as e:
        print_error(f"Failed to launch msfconsole: {e}")
        sys.exit(1)


# ----------------------------------------------------------------
# Main Setup Process
# ----------------------------------------------------------------
def run_full_setup():
    """Run the complete Metasploit setup process."""
    console.print(create_header())
    console.print()

    display_panel(
        "This script will install and configure the Metasploit Framework.\n\n"
        "The process includes:\n"
        "1. Checking system compatibility\n"
        "2. Installing required dependencies\n"
        "3. Downloading and running the Metasploit installer\n"
        "4. Configuring PostgreSQL database\n"
        "5. Verifying the installation\n"
        "6. Launching msfconsole for interactive configuration",
        style=NordColors.FROST_2,
        title="Setup Process",
    )

    console.print()

    if not Confirm.ask("Do you want to proceed with the installation?", default=True):
        print_warning("Installation aborted by user.")
        sys.exit(0)

    console.print()

    # Step 1: Check system
    if not check_system():
        print_error("System check failed. Installation cannot proceed.")
        sys.exit(1)

    # Step 2: Install dependencies
    if not install_system_dependencies():
        print_warning("Some dependencies could not be installed. Continuing anyway.")

    # Step 3: Download installer
    if not download_metasploit_installer():
        print_error("Failed to download Metasploit installer. Cannot proceed.")
        sys.exit(1)

    # Step 4: Run installer
    if not run_metasploit_installer():
        print_error("Metasploit installation failed.")
        sys.exit(1)

    # Step 5: Configure PostgreSQL
    configure_postgresql()

    # Step 6: Verify installation
    msfconsole_path = check_installation()
    if not msfconsole_path:
        print_error(
            "Metasploit verification failed but installation might still be successful."
        )
        print_message(
            "You can try running 'msfconsole' manually later.", NordColors.YELLOW
        )
        sys.exit(1)

    # Step 7: Launch msfconsole
    launch_msfconsole(msfconsole_path)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main():
    try:
        # Auto-install dependencies if not found (handled at import time)

        # Check if running with proper permissions
        if os.geteuid() != 0:
            print_error("This script must be run with root privileges.")
            print_message(
                "Please run with: sudo python3 metasploit_installer.py",
                NordColors.YELLOW,
            )
            sys.exit(1)

        run_full_setup()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
