#!/usr/bin/env python3
"""
Raspberry Pi 5 Overclocking Utility
-----------------------------------

A utility for overclocking and managing the Raspberry Pi 5 CPU frequency and cooling.
This tool provides operations including:
  • CPU overclocking - Configure the Pi 5 to run at 3.1 GHz
  • CPU governor control - Set the CPU governor to performance mode
  • Cooling management - Set the fan to run at maximum speed
  • Temperature monitoring - Real-time monitoring of CPU temperature
  • Configuration persistence - Make settings persist across reboots

Note: This script requires root privileges and is designed specifically for
Raspberry Pi 5 running Ubuntu 24.10 on aarch64 architecture.

Version: 1.0.0
"""

import atexit
import datetime
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    import pyfiglet

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Rich library not available. Installing required packages...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"], check=False)
    print("Please restart the script after installation.")
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Pi 5 Overclock Utility"
VERSION = "1.0.0"
HOSTNAME = platform.node()
LOG_FILE = "/var/log/pi5_overclock.log"

# Config files
CONFIG_BOOT = "/boot/firmware/config.txt"
BACKUP_CONFIG = "/boot/firmware/config.txt.backup"
CONFIG_DIR = "/etc/pi5_overclock"
SYSTEMD_SERVICE_PATH = "/etc/systemd/system/pi5_overclock.service"

# Frequency settings
TARGET_FREQ_GHZ = 3.1
TARGET_FREQ = int(TARGET_FREQ_GHZ * 1000000)  # Convert to Hz
DEFAULT_FREQ = 2400000  # Default Pi 5 frequency in Hz

# Fan settings
FAN_CONTROL_PATH = "/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1"
FAN_MANUAL_ENABLE_PATH = "/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable"
FAN_MAX_SPEED = 255  # Max PWM value

# Temperature paths
TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
CRITICAL_TEMP = 80  # Celsius
WARNING_TEMP = 75  # Celsius

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()


class NordColors:
    """Nord theme color palette for consistent UI styling."""

    # Polar Night (dark/background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"

    # Snow Storm (light/text)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"

    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"

    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red (errors)
    NORD12 = "#D08770"  # Orange (warnings)
    NORD13 = "#EBCB8B"  # Yellow (caution)
    NORD14 = "#A3BE8C"  # Green (success)
    NORD15 = "#B48EAD"  # Purple (special)


# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style=f"bold {NordColors.NORD8}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]  {title.center(TERM_WIDTH - 4)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def pause() -> None:
    """Pause execution until user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")


def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)


def get_user_confirmation(prompt: str) -> bool:
    """Get confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")


def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a Rich table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")

    for key, description in options:
        table.add_row(key, description)

    return table


# ==============================
# Logging Setup
# ==============================
def setup_logging(log_file: str = LOG_FILE) -> None:
    """Configure basic logging for the script."""
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
        print_warning(f"Could not set up logging to {log_file}: {e}")
        print_step("Continuing without logging to file...")


# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Specific cleanup tasks can be added here if needed


atexit.register(cleanup)


def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


# ==============================
# System Validation Functions
# ==============================
def check_root() -> bool:
    """Check if script is running with elevated privileges."""
    return os.geteuid() == 0


def validate_system() -> bool:
    """Validate that we're running on a Raspberry Pi 5 with Ubuntu 24.10."""
    # Check for ARM architecture
    machine = platform.machine()
    if not machine.startswith(("aarch64", "arm")):
        print_error(
            f"Unsupported architecture: {machine}. This script requires ARM architecture."
        )
        return False

    # Check for Raspberry Pi 5
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            if "Raspberry Pi 5" not in model:
                print_warning(
                    f"This doesn't appear to be a Raspberry Pi 5: {model.strip()}"
                )
                if not get_user_confirmation("Continue anyway?"):
                    return False
    except FileNotFoundError:
        print_warning(
            "Cannot determine Raspberry Pi model. This script is designed for Pi 5."
        )
        if not get_user_confirmation("Continue anyway?"):
            return False

    # Check for Ubuntu 24.10
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            os_info = f.read()
            if "Ubuntu" not in os_info or "24.10" not in os_info:
                print_warning("This script is designed for Ubuntu 24.10.")
                print_info(f"Detected OS: {os_info.splitlines()[0]}")
                if not get_user_confirmation("Continue anyway?"):
                    return False
    else:
        print_warning("Cannot determine OS. This script is designed for Ubuntu 24.10.")
        if not get_user_confirmation("Continue anyway?"):
            return False

    return True


# ==============================
# CPU and Cooling Management
# ==============================
def read_current_cpu_freq() -> int:
    """Read the current CPU frequency in Hz."""
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
            return int(f.read().strip())
    except Exception as e:
        print_error(f"Failed to read current CPU frequency: {e}")
        return 0


def read_cpu_temp() -> float:
    """Read the current CPU temperature in Celsius."""
    try:
        with open(TEMP_PATH, "r") as f:
            # Temperature is stored in millidegrees Celsius
            return float(f.read().strip()) / 1000.0
    except Exception as e:
        print_error(f"Failed to read CPU temperature: {e}")
        return 0.0


def set_cpu_governor(governor: str = "performance") -> bool:
    """Set the CPU governor to control frequency scaling."""
    if governor not in [
        "performance",
        "powersave",
        "userspace",
        "ondemand",
        "conservative",
        "schedutil",
    ]:
        print_error(f"Invalid governor: {governor}")
        return False

    success = True
    for cpu in range(4):  # Pi 5 has 4 cores
        cpu_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
        try:
            with open(cpu_path, "w") as f:
                f.write(governor)
        except Exception as e:
            print_error(f"Failed to set governor for CPU{cpu}: {e}")
            success = False

    if success:
        print_success(f"CPU governor set to {governor} for all cores")
    return success


def set_fan_speed(speed: int = FAN_MAX_SPEED) -> bool:
    """Set the fan speed (0-255)."""
    # First, make sure manual control is enabled
    try:
        # Find the actual fan control path
        fan_control_actual = subprocess.getoutput(
            "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1"
        )
        fan_manual_actual = subprocess.getoutput(
            "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable"
        )

        if not os.path.exists(fan_manual_actual):
            print_error(f"Fan control path not found: {fan_manual_actual}")
            return False

        # Enable manual control (1 = manual)
        with open(fan_manual_actual, "w") as f:
            f.write("1")

        # Set the fan speed
        if not os.path.exists(fan_control_actual):
            print_error(f"Fan control path not found: {fan_control_actual}")
            return False

        with open(fan_control_actual, "w") as f:
            # Ensure speed is within valid range
            validated_speed = max(0, min(speed, FAN_MAX_SPEED))
            f.write(str(validated_speed))

        print_success(f"Fan speed set to {validated_speed}/{FAN_MAX_SPEED}")
        return True
    except Exception as e:
        print_error(f"Failed to set fan speed: {e}")
        return False


def backup_config_file() -> bool:
    """Create a backup of the config.txt file."""
    if os.path.exists(CONFIG_BOOT):
        try:
            shutil.copy2(CONFIG_BOOT, BACKUP_CONFIG)
            print_success(f"Created backup of {CONFIG_BOOT} to {BACKUP_CONFIG}")
            return True
        except Exception as e:
            print_error(f"Failed to create backup: {e}")
            return False
    else:
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False


def update_config_for_overclock() -> bool:
    """Update the config.txt file to enable overclocking to 3.1GHz."""
    if not os.path.exists(CONFIG_BOOT):
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False

    # Create a backup before modifying
    if not backup_config_file():
        if not get_user_confirmation("Continue without backup?"):
            return False

    try:
        # Read the current config
        with open(CONFIG_BOOT, "r") as f:
            config_lines = f.readlines()

        # Track if we've found and updated existing overclock settings
        arm_freq_found = False
        over_voltage_found = False
        force_turbo_found = False

        # Look for existing settings to update
        for i, line in enumerate(config_lines):
            if line.strip().startswith("arm_freq="):
                config_lines[i] = f"arm_freq={int(TARGET_FREQ_GHZ * 1000)}\n"
                arm_freq_found = True
            elif line.strip().startswith("over_voltage="):
                config_lines[i] = "over_voltage=6\n"  # Recommended for 3.1GHz
                over_voltage_found = True
            elif line.strip().startswith("force_turbo="):
                config_lines[i] = "force_turbo=1\n"
                force_turbo_found = True

        # Add settings if they weren't found
        if not arm_freq_found:
            config_lines.append(f"arm_freq={int(TARGET_FREQ_GHZ * 1000)}\n")
        if not over_voltage_found:
            config_lines.append("over_voltage=6\n")
        if not force_turbo_found:
            config_lines.append("force_turbo=1\n")

        # Write the updated config
        with open(CONFIG_BOOT, "w") as f:
            f.writelines(config_lines)

        print_success(f"Updated {CONFIG_BOOT} with overclock settings")
        print_info("Changes will take effect after reboot")
        return True
    except Exception as e:
        print_error(f"Failed to update config for overclocking: {e}")
        return False


def setup_systemd_service() -> bool:
    """Create a systemd service to set CPU governor and fan speed at boot."""
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR)
        except Exception as e:
            print_error(f"Failed to create config directory: {e}")
            return False

    # Create the script that will be executed by systemd
    script_path = os.path.join(CONFIG_DIR, "pi5_overclock.py")
    try:
        with open(script_path, "w") as f:
            f.write(f"""#!/usr/bin/env python3
# Automatically generated by Pi 5 Overclock Utility
import os
import time

def set_cpu_governor():
    for cpu in range(4):
        gov_path = f"/sys/devices/system/cpu/cpu{{cpu}}/cpufreq/scaling_governor"
        try:
            with open(gov_path, 'w') as f:
                f.write("performance")
        except Exception:
            pass

def set_fan_speed():
    try:
        # Find fan control paths
        import glob
        fan_control = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1")[0]
        fan_manual = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable")[0]
        
        # Enable manual control
        with open(fan_manual, 'w') as f:
            f.write("1")
        
        # Set max speed
        with open(fan_control, 'w') as f:
            f.write("255")
    except Exception:
        pass

if __name__ == "__main__":
    # Give system time to initialize
    time.sleep(5)
    set_cpu_governor()
    set_fan_speed()
""")
        os.chmod(script_path, 0o755)  # Make the script executable
    except Exception as e:
        print_error(f"Failed to create startup script: {e}")
        return False

    # Create the systemd service file
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

    try:
        with open(SYSTEMD_SERVICE_PATH, "w") as f:
            f.write(service_content)

        # Enable and start the service
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "pi5_overclock.service"], check=True)
        subprocess.run(["systemctl", "start", "pi5_overclock.service"], check=True)

        print_success("Created and enabled systemd service for startup")
        return True
    except Exception as e:
        print_error(f"Failed to setup systemd service: {e}")
        return False


def monitor_temperature_and_frequency(duration: int = 60) -> None:
    """Monitor CPU temperature and frequency for a specified duration in seconds."""
    print_section("Temperature and Frequency Monitor")
    print_info(f"Monitoring for {duration} seconds. Press Ctrl+C to stop.")
    print_info(
        f"Target frequency: {TARGET_FREQ_GHZ} GHz | Critical temperature: {CRITICAL_TEMP}°C"
    )

    # Setup table for display
    console.print(
        f"[bold]{'Time':<12} {'Temperature':<20} {'Frequency':<15} {'Status':<10}[/bold]"
    )
    console.print("─" * 60)

    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            current_temp = read_cpu_temp()
            current_freq = read_current_cpu_freq()
            current_freq_ghz = current_freq / 1000000

            # Determine status based on temperature and frequency
            if current_temp >= CRITICAL_TEMP:
                status = f"[bold {NordColors.NORD11}]CRITICAL[/]"
            elif current_temp >= WARNING_TEMP:
                status = f"[bold {NordColors.NORD13}]WARNING[/]"
            elif current_freq >= TARGET_FREQ - 100000:  # Within 100MHz of target
                status = f"[bold {NordColors.NORD14}]OPTIMAL[/]"
            else:
                status = f"[{NordColors.NORD4}]OK[/]"

            # Temperature color based on value
            if current_temp >= CRITICAL_TEMP:
                temp_color = NordColors.NORD11
            elif current_temp >= WARNING_TEMP:
                temp_color = NordColors.NORD13
            else:
                temp_color = NordColors.NORD14

            # Format the output
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            console.print(
                f"{timestamp:<12} "
                f"[{temp_color}]{current_temp:.1f}°C[/]{'':10} "
                f"{current_freq_ghz:.2f} GHz{'':5} "
                f"{status}"
            )

            time.sleep(1)

    except KeyboardInterrupt:
        print_warning("\nMonitoring stopped by user.")


def apply_all_settings() -> bool:
    """Apply all overclocking and cooling settings."""
    print_section("Applying All Settings")

    # Track overall success
    success = True

    # Step 1: Set CPU governor to performance
    print_step("Setting CPU governor to performance mode...")
    if not set_cpu_governor("performance"):
        success = False

    # Step 2: Set fan to maximum speed
    print_step("Setting fan to maximum speed...")
    if not set_fan_speed(FAN_MAX_SPEED):
        success = False

    # Step 3: Update config.txt for overclocking
    print_step("Updating boot configuration for overclocking...")
    if not update_config_for_overclock():
        success = False

    # Step 4: Setup startup service
    print_step("Setting up startup service...")
    if not setup_systemd_service():
        success = False

    if success:
        print_success("All settings applied successfully!")
        print_warning(
            "A system reboot is required for overclocking changes to take effect."
        )
        if get_user_confirmation("Would you like to reboot now?"):
            print_info("Rebooting system...")
            subprocess.run(["reboot"])
    else:
        print_warning("Some settings could not be applied. See errors above.")

    return success


# ==============================
# Menu Systems
# ==============================
def main_menu() -> None:
    """Display the main menu and handle user selection."""
    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        print_info(f"System: {platform.system()} {platform.release()}")
        print_info(f"Architecture: {platform.machine()}")
        print_info(f"Host: {HOSTNAME}")
        print_info(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Current CPU Temp: {read_cpu_temp():.1f}°C")
        print_info(f"Current CPU Freq: {read_current_cpu_freq() / 1000000:.2f} GHz")
        print_info(f"Target CPU Freq: {TARGET_FREQ_GHZ} GHz")

        # Main menu options
        menu_options = [
            (
                "1",
                "Apply All Settings - Configure overclocking, CPU governor, and cooling",
            ),
            ("2", "Set CPU Governor - Set CPU governor to performance mode"),
            ("3", "Max Fan Speed - Set fan to maximum speed"),
            ("4", "Update Boot Config - Configure boot settings for overclocking"),
            ("5", "Setup Startup Service - Create service to apply settings at boot"),
            ("6", "Monitor System - Real-time temperature and frequency monitoring"),
            ("0", "Exit"),
        ]

        console.print(create_menu_table("Main Menu", menu_options))

        # Get user selection
        choice = get_user_input("Enter your choice (0-6):")

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
                duration_input = get_user_input(
                    "Monitoring duration in seconds (default: 60)"
                )
                if duration_input:
                    duration = int(duration_input)
            except ValueError:
                print_error("Invalid duration. Using default of 60 seconds.")
            monitor_temperature_and_frequency(duration)
            pause()
        elif choice == "0":
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Pi 5 Overclock Utility.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)


# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the script."""
    try:
        # Initial setup
        setup_logging()

        # Check if running as root
        if not check_root():
            print_error("This script requires root privileges.")
            print_info("Please run with: sudo python3 pi5_overclock.py")
            sys.exit(1)

        # Validate that we're running on the correct system
        if not validate_system():
            print_error("System validation failed.")
            sys.exit(1)

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
