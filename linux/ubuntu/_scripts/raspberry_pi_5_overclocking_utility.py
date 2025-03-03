#!/usr/bin/env python3
"""
Raspberry Pi 5 Overclocking Utility
--------------------------------------------------

A comprehensive terminal interface for overclocking and managing the Raspberry Pi 5.
Features CPU frequency control, fan management, temperature monitoring, and system
configuration with elegant Nord-themed styling.

Usage:
  Run the script with root privileges and select options from the menu.
  - Option 1: Apply all settings at once
  - Option 2: Set CPU governor to performance mode
  - Option 3: Set fan to maximum speed
  - Option 4: Update boot configuration for overclocking
  - Option 5: Setup systemd service for persistence
  - Option 6: Monitor CPU temperature and frequency

Version: 1.0.0
"""

import atexit
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing required dependencies...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"], check=False)
    print("Please restart the script after installation.")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
APP_NAME: str = "Pi 5 Overclock"
APP_SUBTITLE: str = "System Performance Manager"
VERSION: str = "1.0.0"
HOSTNAME: str = platform.node()

# System paths and defaults
CONFIG_BOOT: str = "/boot/firmware/config.txt"
BACKUP_CONFIG: str = "/boot/firmware/config.txt.backup"
CONFIG_DIR: str = "/etc/pi5_overclock"
SYSTEMD_SERVICE_PATH: str = "/etc/systemd/system/pi5_overclock.service"
LOG_FILE: str = "/var/log/pi5_overclock.log"
TEMP_PATH: str = "/sys/class/thermal/thermal_zone0/temp"

# Performance settings
TARGET_FREQ_GHZ: float = 3.1
TARGET_FREQ: int = int(TARGET_FREQ_GHZ * 1000000)  # 3.1 GHz in Hz
DEFAULT_FREQ: int = 2400000  # Default frequency in Hz
FAN_MAX_SPEED: int = 255  # Maximum PWM value
CRITICAL_TEMP: int = 80  # Celsius
WARNING_TEMP: int = 75  # Celsius
OPERATION_TIMEOUT: int = 30  # seconds

# Terminal sizing
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT: int = min(shutil.get_terminal_size().lines, 30)


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red - errors
    ORANGE = "#D08770"  # Orange - warnings
    YELLOW = "#EBCB8B"  # Yellow - caution
    GREEN = "#A3BE8C"  # Green - success
    PURPLE = "#B48EAD"  # Purple - special/input


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with Nord styling.

    Returns:
        Panel containing the styled header
    """
    # List of compact but tech-looking fonts
    compact_fonts = ["small", "slant", "mini", "digital", "standard"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
 ____  _  ____     _____                      _            _    
|  _ \(_)|  _ \ _ / / _ \ __   _____ _ __ ___| | ___   ___| | __
| |_) | || |_) / | | | | |\ \ / / _ \ '__/ __| |/ _ \ / __| |/ /
|  __/| ||  __/| | | |_| | \ V /  __/ | | (__| | (_) | (__|   < 
|_|   |_||_|   | | |\___/   \_/ \___|_|  \___|_|\___/ \___|_|\_\\
              |_|                                              
        """

    # Clean up extra whitespace
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with the header
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


def print_info(message: str) -> None:
    """Display an informational message."""
    print_message(message, NordColors.FROST_3, "ℹ")


def print_success(message: str) -> None:
    """Display a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Display a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Display an error message."""
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    """Print a step description."""
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{title.center(TERM_WIDTH)}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")


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
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until the user presses Enter."""
    console.input(f"\n[{NordColors.PURPLE}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.PURPLE}]{prompt}[/]", default=default)


def get_user_confirmation(prompt: str, default: bool = False) -> bool:
    """Get a Yes/No confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.PURPLE}]{prompt}[/]", default=default)


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a table to display menu options."""
    table = Table(
        title=title,
        box=None,
        title_style=f"bold {NordColors.FROST_2}",
        title_justify="center",
        expand=True,
    )
    table.add_column(
        "Option", style=f"bold {NordColors.FROST_4}", justify="right", width=8
    )
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for key, desc in options:
        table.add_row(key, desc)

    return table


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Set up file logging for the utility."""
    import logging

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Could not set up logging: {e}")
        print_step("Continuing without file logging...")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
    """
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_step("Cleaning up resources...")


def signal_handler(signum: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nProcess interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# System Validation Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    """Return True if the script is running with root privileges."""
    return os.geteuid() == 0


def validate_system() -> bool:
    """
    Validate that the system is a Raspberry Pi 5 running Ubuntu 24.10.

    Returns:
        True if system validation passes, otherwise False
    """
    # Check for ARM architecture
    machine = platform.machine()
    if not machine.startswith(("aarch64", "arm")):
        print_error(
            f"Unsupported architecture: {machine}. This utility requires ARM architecture."
        )
        return False

    # Validate Raspberry Pi 5 model
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            if "Raspberry Pi 5" not in model:
                print_warning(
                    f"Model does not appear to be Raspberry Pi 5: {model.strip()}"
                )
                if not get_user_confirmation("Continue anyway?"):
                    return False
    except FileNotFoundError:
        print_warning(
            "Cannot determine Raspberry Pi model. This utility is designed for Pi 5."
        )
        if not get_user_confirmation("Continue anyway?"):
            return False

    # Validate OS version (Ubuntu 24.10)
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            os_info = f.read()
            if "Ubuntu" not in os_info or "24.10" not in os_info:
                print_warning("This utility is designed for Ubuntu 24.10.")
                print_info(f"Detected OS: {os_info.splitlines()[0]}")
                if not get_user_confirmation("Continue anyway?"):
                    return False
    else:
        print_warning(
            "Cannot determine OS version. This utility is designed for Ubuntu 24.10."
        )
        if not get_user_confirmation("Continue anyway?"):
            return False

    return True


# ----------------------------------------------------------------
# CPU and Cooling Management Functions
# ----------------------------------------------------------------
def read_current_cpu_freq() -> int:
    """
    Read the current CPU frequency in Hz.

    Returns:
        Current frequency in Hz, or 0 if reading fails
    """
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
            return int(f.read().strip())
    except Exception as e:
        print_error(f"Failed to read CPU frequency: {e}")
        return 0


def read_cpu_temp() -> float:
    """
    Read the current CPU temperature in Celsius.

    Returns:
        Current temperature in °C, or 0.0 if reading fails
    """
    try:
        with open(TEMP_PATH, "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception as e:
        print_error(f"Failed to read CPU temperature: {e}")
        return 0.0


def set_cpu_governor(governor: str = "performance") -> bool:
    """
    Set the CPU governor for all cores.

    Args:
        governor: The CPU governor to set ("performance", "powersave", etc.)

    Returns:
        True if successful, False otherwise
    """
    valid_governors = [
        "performance",
        "powersave",
        "userspace",
        "ondemand",
        "conservative",
        "schedutil",
    ]

    if governor not in valid_governors:
        print_error(f"Invalid governor: {governor}")
        return False

    success = True
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Setting CPU governor to {governor}"),
        console=console,
    ) as progress:
        task = progress.add_task("Working", total=4)  # 4 cores on Pi 5

        for cpu in range(4):  # Pi 5 has 4 cores
            cpu_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
            try:
                with open(cpu_path, "w") as f:
                    f.write(governor)
                progress.advance(task)
            except Exception as e:
                print_error(f"Failed to set governor for CPU{cpu}: {e}")
                success = False

    if success:
        print_success(f"CPU governor set to {governor} for all cores")

    return success


def set_fan_speed(speed: int = FAN_MAX_SPEED) -> bool:
    """
    Set the fan speed (0-255).

    Args:
        speed: Fan speed value between 0-255

    Returns:
        True if successful, False otherwise
    """
    try:
        # Find fan control paths using shell globbing
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Setting fan speed"),
            console=console,
        ) as progress:
            task = progress.add_task("Working", total=3)

            # Step 1: Find the fan control paths
            progress.update(task, description="Locating fan control paths")
            fan_control_actual = subprocess.getoutput(
                "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1"
            )
            fan_manual_actual = subprocess.getoutput(
                "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable"
            )
            progress.advance(task)

            # Step 2: Enable manual control
            progress.update(task, description="Enabling manual fan control")
            if not os.path.exists(fan_manual_actual):
                print_error(f"Fan control path not found: {fan_manual_actual}")
                return False

            with open(fan_manual_actual, "w") as f:
                f.write("1")  # Enable manual control
            progress.advance(task)

            # Step 3: Set the speed
            progress.update(
                task, description=f"Setting fan speed to {speed}/{FAN_MAX_SPEED}"
            )
            if not os.path.exists(fan_control_actual):
                print_error(f"Fan control path not found: {fan_control_actual}")
                return False

            validated_speed = max(0, min(speed, FAN_MAX_SPEED))
            with open(fan_control_actual, "w") as f:
                f.write(str(validated_speed))
            progress.advance(task)

        print_success(f"Fan speed set to {validated_speed}/{FAN_MAX_SPEED}")
        return True
    except Exception as e:
        print_error(f"Failed to set fan speed: {e}")
        return False


def backup_config_file() -> bool:
    """
    Backup the boot configuration file.

    Returns:
        True if backup was successful, False otherwise
    """
    if os.path.exists(CONFIG_BOOT):
        try:
            with Progress(
                SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
                TextColumn(
                    f"[bold {NordColors.FROST_2}]Creating backup of boot config"
                ),
                console=console,
            ) as progress:
                task = progress.add_task("Backing up", total=1)
                shutil.copy2(CONFIG_BOOT, BACKUP_CONFIG)
                progress.advance(task)

            print_success(f"Backup created: {CONFIG_BOOT} -> {BACKUP_CONFIG}")
            return True
        except Exception as e:
            print_error(f"Failed to backup config: {e}")
            return False
    else:
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False


def update_config_for_overclock() -> bool:
    """
    Update config.txt to enable overclocking to target frequency.

    Returns:
        True if config was updated successfully, False otherwise
    """
    if not os.path.exists(CONFIG_BOOT):
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False

    if not backup_config_file():
        if not get_user_confirmation("Continue without backup?"):
            return False

    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Updating boot configuration"),
            console=console,
        ) as progress:
            task = progress.add_task("Working", total=3)

            # Step 1: Read existing config
            progress.update(task, description="Reading current configuration")
            with open(CONFIG_BOOT, "r") as f:
                config_lines = f.readlines()
            progress.advance(task)

            # Step 2: Update or add overclock settings
            progress.update(task, description="Updating overclock parameters")
            arm_freq_found = False
            over_voltage_found = False
            force_turbo_found = False

            for i, line in enumerate(config_lines):
                if line.strip().startswith("arm_freq="):
                    config_lines[i] = f"arm_freq={int(TARGET_FREQ_GHZ * 1000)}\n"
                    arm_freq_found = True
                elif line.strip().startswith("over_voltage="):
                    config_lines[i] = "over_voltage=6\n"
                    over_voltage_found = True
                elif line.strip().startswith("force_turbo="):
                    config_lines[i] = "force_turbo=1\n"
                    force_turbo_found = True

            if not arm_freq_found:
                config_lines.append(f"arm_freq={int(TARGET_FREQ_GHZ * 1000)}\n")
            if not over_voltage_found:
                config_lines.append("over_voltage=6\n")
            if not force_turbo_found:
                config_lines.append("force_turbo=1\n")
            progress.advance(task)

            # Step 3: Write updated config
            progress.update(task, description="Writing updated configuration")
            with open(CONFIG_BOOT, "w") as f:
                f.writelines(config_lines)
            progress.advance(task)

        print_success(f"Updated {CONFIG_BOOT} with overclock settings")
        print_info("Changes will take effect after reboot")
        return True
    except Exception as e:
        print_error(f"Failed to update config: {e}")
        return False


def setup_systemd_service() -> bool:
    """
    Create and enable a systemd service to apply settings at boot.

    Returns:
        True if service was set up successfully, False otherwise
    """
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR)
        except Exception as e:
            print_error(f"Failed to create config directory: {e}")
            return False

    script_path = os.path.join(CONFIG_DIR, "pi5_overclock.py")

    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Setting up startup service"),
            console=console,
        ) as progress:
            task = progress.add_task("Working", total=4)

            # Step 1: Create the startup script
            progress.update(task, description="Creating startup script")
            with open(script_path, "w") as f:
                f.write(f"""#!/usr/bin/env python3
# Automatically generated by {APP_NAME} Utility v{VERSION}
# Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
import os
import time
import glob
import logging

# Setup logging
logging.basicConfig(
    filename="{LOG_FILE}",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def set_cpu_governor():
    for cpu in range(4):
        gov_path = f"/sys/devices/system/cpu/cpufreq/cpu{{cpu}}/scaling_governor"
        try:
            with open(gov_path, 'w') as f:
                f.write("performance")
            logging.info(f"Set CPU{{cpu}} governor to performance")
        except Exception as e:
            logging.error(f"Failed to set CPU{{cpu}} governor: {{e}}")

def set_fan_speed():
    try:
        fan_control_paths = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1")
        fan_manual_paths = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable")
        
        if not fan_control_paths or not fan_manual_paths:
            logging.error("Fan control paths not found")
            return
            
        fan_control = fan_control_paths[0]
        fan_manual = fan_manual_paths[0]
        
        with open(fan_manual, 'w') as f:
            f.write("1")
        with open(fan_control, 'w') as f:
            f.write("255")
        logging.info("Set fan speed to 255")
    except Exception as e:
        logging.error(f"Failed to set fan speed: {{e}}")

if __name__ == "__main__":
    logging.info("Pi 5 Overclock service starting")
    # Wait for system to fully initialize
    time.sleep(5)
    set_cpu_governor()
    set_fan_speed()
    logging.info("Pi 5 Overclock service completed")
""")
            os.chmod(script_path, 0o755)
            progress.advance(task)

            # Step 2: Create the systemd service file
            progress.update(task, description="Creating systemd service file")
            service_content = f"""[Unit]
Description=Raspberry Pi 5 Overclock Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {script_path}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
            with open(SYSTEMD_SERVICE_PATH, "w") as f:
                f.write(service_content)
            progress.advance(task)

            # Step 3: Reload systemd and enable the service
            progress.update(task, description="Reloading systemd and enabling service")
            run_command(["systemctl", "daemon-reload"])
            run_command(["systemctl", "enable", "pi5_overclock.service"])
            progress.advance(task)

            # Step 4: Start the service
            progress.update(task, description="Starting the service")
            run_command(["systemctl", "start", "pi5_overclock.service"])
            progress.advance(task)

        print_success("Created and enabled systemd service for startup")
        return True
    except Exception as e:
        print_error(f"Failed to setup systemd service: {e}")
        return False


def monitor_temperature_and_frequency(duration: int = 60) -> None:
    """
    Monitor CPU temperature and frequency for a specified duration.

    Args:
        duration: Monitoring duration in seconds
    """
    print_section("Temperature and Frequency Monitor")
    print_info(f"Monitoring for {duration} seconds. Press Ctrl+C to stop.")
    print_info(
        f"Target frequency: {TARGET_FREQ_GHZ} GHz | Critical temperature: {CRITICAL_TEMP}°C"
    )

    # Create a styled table header
    header = Text()
    header.append("Time", style=f"bold {NordColors.FROST_2}")
    header.append(" | ", style="dim")
    header.append("Temperature", style=f"bold {NordColors.FROST_2}")
    header.append(" | ", style="dim")
    header.append("Frequency", style=f"bold {NordColors.FROST_2}")
    header.append(" | ", style="dim")
    header.append("Status", style=f"bold {NordColors.FROST_2}")

    console.print(header)
    console.print("─" * 60)

    # Record min, max, and average values
    min_temp = float("inf")
    max_temp = float("-inf")
    min_freq = float("inf")
    max_freq = float("-inf")
    temp_sum = 0
    freq_sum = 0
    samples = 0

    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            current_temp = read_cpu_temp()
            current_freq = read_current_cpu_freq()
            current_freq_ghz = current_freq / 1000000

            # Update statistics
            min_temp = min(min_temp, current_temp)
            max_temp = max(max_temp, current_temp)
            min_freq = min(min_freq, current_freq_ghz)
            max_freq = max(max_freq, current_freq_ghz)
            temp_sum += current_temp
            freq_sum += current_freq_ghz
            samples += 1

            # Determine status and colors
            if current_temp >= CRITICAL_TEMP:
                status = Text("CRITICAL", style=f"bold {NordColors.RED}")
                temp_color = NordColors.RED
            elif current_temp >= WARNING_TEMP:
                status = Text("WARNING", style=f"bold {NordColors.YELLOW}")
                temp_color = NordColors.YELLOW
            elif current_freq >= TARGET_FREQ - 100000:  # within 100MHz
                status = Text("OPTIMAL", style=f"bold {NordColors.GREEN}")
                temp_color = NordColors.GREEN
            else:
                status = Text("OK", style=f"{NordColors.SNOW_STORM_1}")
                temp_color = NordColors.FROST_1

            timestamp = datetime.now().strftime("%H:%M:%S")

            # Create a styled line
            line = Text()
            line.append(timestamp, style=f"{NordColors.SNOW_STORM_1}")
            line.append(" | ", style="dim")
            line.append(f"{current_temp:.1f}°C", style=f"{temp_color}")
            line.append(" | ", style="dim")
            line.append(f"{current_freq_ghz:.2f} GHz", style=f"{NordColors.FROST_1}")
            line.append(" | ", style="dim")
            line.append(status)

            console.print(line)
            time.sleep(1)
    except KeyboardInterrupt:
        print_warning("\nMonitoring stopped by user.")
    finally:
        # Calculate averages
        if samples > 0:
            avg_temp = temp_sum / samples
            avg_freq = freq_sum / samples

            # Print statistics summary
            print_section("Monitoring Statistics")
            stats_table = Table(box=None, expand=True)
            stats_table.add_column("Metric", style=f"bold {NordColors.FROST_2}")
            stats_table.add_column("Minimum", style=f"{NordColors.SNOW_STORM_1}")
            stats_table.add_column("Average", style=f"{NordColors.SNOW_STORM_1}")
            stats_table.add_column("Maximum", style=f"{NordColors.SNOW_STORM_1}")

            stats_table.add_row(
                "Temperature",
                f"{min_temp:.1f}°C",
                f"{avg_temp:.1f}°C",
                f"{max_temp:.1f}°C",
            )
            stats_table.add_row(
                "Frequency",
                f"{min_freq:.2f} GHz",
                f"{avg_freq:.2f} GHz",
                f"{max_freq:.2f} GHz",
            )

            console.print(stats_table)


def apply_all_settings() -> bool:
    """
    Apply overclocking, CPU governor, and fan settings.

    Returns:
        True if all settings were applied successfully, False otherwise
    """
    print_section("Applying All Settings")

    success = True
    steps = [
        (
            "Setting CPU governor to performance mode",
            lambda: set_cpu_governor("performance"),
        ),
        ("Setting fan to maximum speed", lambda: set_fan_speed(FAN_MAX_SPEED)),
        ("Updating boot configuration for overclocking", update_config_for_overclock),
        ("Setting up startup service", setup_systemd_service),
    ]

    for description, func in steps:
        print_step(description)
        if not func():
            success = False

    if success:
        print_success("All settings applied successfully!")
        panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]Successfully configured Pi 5 for {TARGET_FREQ_GHZ} GHz operation![/]\n\n"
                f"• CPU governor: [bold]performance[/]\n"
                f"• Fan speed: [bold]maximum[/]\n"
                f"• Boot config: [bold]updated[/]\n"
                f"• Startup service: [bold]enabled[/]\n\n"
                f"[bold {NordColors.YELLOW}]A system reboot is required for all changes to take effect.[/]"
            ),
            title=f"[bold {NordColors.FROST_2}]Configuration Complete[/]",
            border_style=Style(color=NordColors.FROST_1),
            padding=(1, 2),
        )
        console.print(panel)

        if get_user_confirmation("Reboot now?"):
            print_info("Rebooting system...")
            subprocess.run(["reboot"])
    else:
        print_warning("Some settings failed to apply. See errors above.")

    return success


# ----------------------------------------------------------------
# Menu Systems
# ----------------------------------------------------------------
def show_system_info() -> Panel:
    """
    Create a panel with system information.

    Returns:
        Panel containing system info
    """
    current_temp = read_cpu_temp()
    current_freq = read_current_cpu_freq() / 1000000

    # Determine temperature status and color
    if current_temp >= CRITICAL_TEMP:
        temp_status = f"[bold {NordColors.RED}]CRITICAL[/]"
    elif current_temp >= WARNING_TEMP:
        temp_status = f"[bold {NordColors.YELLOW}]WARNING[/]"
    else:
        temp_status = f"[bold {NordColors.GREEN}]NORMAL[/]"

    # Determine frequency status
    if current_freq >= TARGET_FREQ_GHZ - 0.1:  # Within 100 MHz
        freq_status = f"[bold {NordColors.GREEN}]OVERCLOCKED[/]"
    elif current_freq >= 2.9:  # High but not target
        freq_status = f"[bold {NordColors.YELLOW}]HIGH[/]"
    else:
        freq_status = f"[bold {NordColors.SNOW_STORM_1}]STANDARD[/]"

    # Create and return the panel
    system_info = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]System:[/] [{NordColors.SNOW_STORM_1}]{platform.system()} {platform.release()}[/]\n"
            f"[bold {NordColors.FROST_2}]Architecture:[/] [{NordColors.SNOW_STORM_1}]{platform.machine()}[/]\n"
            f"[bold {NordColors.FROST_2}]Hostname:[/] [{NordColors.SNOW_STORM_1}]{HOSTNAME}[/]\n"
            f"[bold {NordColors.FROST_2}]Date/Time:[/] [{NordColors.SNOW_STORM_1}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]\n\n"
            f"[bold {NordColors.FROST_2}]CPU Temperature:[/] [{NordColors.SNOW_STORM_1}]{current_temp:.1f}°C[/] {temp_status}\n"
            f"[bold {NordColors.FROST_2}]CPU Frequency:[/] [{NordColors.SNOW_STORM_1}]{current_freq:.2f} GHz[/] {freq_status}\n"
            f"[bold {NordColors.FROST_2}]Target Frequency:[/] [{NordColors.SNOW_STORM_1}]{TARGET_FREQ_GHZ} GHz[/]"
        ),
        title=f"[bold {NordColors.FROST_2}]System Information[/]",
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
    )

    return system_info


def main_menu() -> None:
    """Display the main menu and process user selections."""
    while True:
        clear_screen()
        console.print(create_header())
        console.print(show_system_info())

        menu_options = [
            ("1", "Apply All Settings - Overclock, set governor, and max fan speed"),
            ("2", "Set CPU Governor - Set governor to performance mode"),
            ("3", "Max Fan Speed - Set fan to maximum speed"),
            ("4", "Update Boot Config - Update config.txt for overclocking"),
            ("5", "Setup Startup Service - Create systemd service for startup"),
            ("6", "Monitor System - Monitor temperature and frequency"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))
        choice = get_user_input("Enter your choice (0-6):", "0")

        if choice == "1":
            apply_all_settings()
            pause()
        elif choice == "2":
            set_cpu_governor("performance")
            pause()
        elif choice == "3":
            set_fan_speed(FAN_MAX_SPEED)
            pause()
        elif choice == "4":
            update_config_for_overclock()
            pause()
        elif choice == "5":
            setup_systemd_service()
            pause()
        elif choice == "6":
            duration = 60
            try:
                duration_input = get_user_input("Monitoring duration in seconds", "60")
                if duration_input:
                    duration = int(duration_input)
            except ValueError:
                print_error("Invalid duration. Using default of 60 seconds.")
            monitor_temperature_and_frequency(duration)
            pause()
        elif choice == "0":
            clear_screen()
            goodbye_panel = Panel(
                Text.from_markup(
                    f"[bold {NordColors.FROST_2}]Thank you for using the Pi 5 Overclock Utility![/]\n\n"
                    f"[{NordColors.SNOW_STORM_1}]Developed with ❤️ for Raspberry Pi 5[/]"
                ),
                title=f"[bold {NordColors.FROST_2}]Goodbye![/]",
                border_style=Style(color=NordColors.FROST_1),
                padding=(1, 2),
            )
            console.print(goodbye_panel)
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main entry point for the utility."""
    try:
        # Welcome animation
        clear_screen()
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Initializing {APP_NAME} Utility"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing", total=3)

            time.sleep(0.5)
            progress.update(task, description="Setting up logging")
            setup_logging()
            progress.advance(task)

            time.sleep(0.5)
            progress.update(task, description="Checking privileges")
            if not check_root():
                clear_screen()
                console.print(create_header())
                panel = Panel(
                    Text.from_markup(
                        f"[bold {NordColors.RED}]This script requires root privileges.[/]\n\n"
                        f"Please run with: [bold {NordColors.SNOW_STORM_1}]sudo python3 pi5_overclock.py[/]"
                    ),
                    title=f"[bold {NordColors.RED}]Permission Error[/]",
                    border_style=Style(color=NordColors.RED),
                    padding=(1, 2),
                )
                console.print(panel)
                sys.exit(1)
            progress.advance(task)

            time.sleep(0.5)
            progress.update(task, description="Validating system")
            if not validate_system():
                clear_screen()
                console.print(create_header())
                panel = Panel(
                    Text.from_markup(
                        f"[bold {NordColors.RED}]System validation failed.[/]\n\n"
                        f"This utility is designed for Raspberry Pi 5 running Ubuntu 24.10."
                    ),
                    title=f"[bold {NordColors.RED}]System Error[/]",
                    border_style=Style(color=NordColors.RED),
                    padding=(1, 2),
                )
                console.print(panel)
                sys.exit(1)
            progress.advance(task)

        # Launch the main menu
        main_menu()
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
