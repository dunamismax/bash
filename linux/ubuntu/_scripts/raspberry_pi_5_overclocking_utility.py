#!/usr/bin/env python3
"""
Raspberry Pi 5 Overclocking Utility
-----------------------------------

A utility for overclocking and managing the Raspberry Pi 5 CPU frequency and cooling.
This tool supports:
  • CPU overclocking – Configure the Pi 5 to run at 3.1 GHz
  • CPU governor control – Set the CPU governor to performance mode
  • Cooling management – Run the fan at maximum speed
  • Temperature monitoring – Real-time monitoring of CPU temperature
  • Configuration persistence – Update boot settings and enable a startup service

Note: This script requires root privileges and is designed for Raspberry Pi 5 running Ubuntu 24.10 on aarch64.
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
from typing import List, Tuple

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    import pyfiglet
except ImportError:
    print("Rich and pyfiglet libraries are required. Installing now...")
    subprocess.run(["pip3", "install", "rich", "pyfiglet"], check=False)
    print("Installation complete. Please restart the script.")
    sys.exit(1)

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Pi 5 Overclock Utility"
VERSION = "1.0.0"
HOSTNAME = platform.node()
LOG_FILE = "/var/log/pi5_overclock.log"

# Boot configuration and systemd service paths
CONFIG_BOOT = "/boot/firmware/config.txt"
BACKUP_CONFIG = "/boot/firmware/config.txt.backup"
CONFIG_DIR = "/etc/pi5_overclock"
SYSTEMD_SERVICE_PATH = "/etc/systemd/system/pi5_overclock.service"

# Frequency settings (in Hz)
TARGET_FREQ_GHZ = 3.1
TARGET_FREQ = int(TARGET_FREQ_GHZ * 1000000)  # 3.1 GHz in Hz
DEFAULT_FREQ = 2400000  # Default frequency (Hz)

# Fan settings
FAN_MAX_SPEED = 255  # Maximum PWM value

# Temperature settings
TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
CRITICAL_TEMP = 80  # Celsius
WARNING_TEMP = 75   # Celsius

# Terminal dimensions
import shutil
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()

class NordColors:
    """Nord theme color palette."""
    NORD0 = "#2E3440"  # Dark background
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"
    NORD4 = "#D8DEE9"  # Light text
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"
    NORD7 = "#8FBCBB"  # Blue accents
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"
    NORD11 = "#BF616A"  # Red – errors
    NORD12 = "#D08770"  # Orange – warnings
    NORD13 = "#EBCB8B"  # Yellow – caution
    NORD14 = "#A3BE8C"  # Green – success
    NORD15 = "#B48EAD"  # Purple – special

# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Display a striking header using pyfiglet in a Rich panel."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    panel = Panel(ascii_art, style=f"bold {NordColors.NORD8}", border_style=NordColors.NORD8)
    console.print(panel)

def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]{title.center(TERM_WIDTH)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")

def print_info(message: str) -> None:
    """Display an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")

def print_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")

def print_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")

def print_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")

def print_step(message: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {message}[/]")

def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()

def pause() -> None:
    """Pause execution until the user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")

def get_user_input(prompt: str, default: str = "") -> str:
    """Get input from the user with a styled prompt."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)

def get_user_confirmation(prompt: str) -> bool:
    """Get a Yes/No confirmation from the user."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")

def create_menu_table(title: str, options: List[Tuple[str, str]]) -> Table:
    """Create a table to display menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")
    for key, desc in options:
        table.add_row(key, desc)
    return table

# ==============================
# Logging Setup
# ==============================
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

# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Additional cleanup tasks can be added here

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ==============================
# System Validation Functions
# ==============================
def check_root() -> bool:
    """Return True if the script is running with root privileges."""
    return os.geteuid() == 0

def validate_system() -> bool:
    """Validate that the system is a Raspberry Pi 5 running Ubuntu 24.10."""
    # Check for ARM architecture
    machine = platform.machine()
    if not machine.startswith(("aarch64", "arm")):
        print_error(f"Unsupported architecture: {machine}. This utility requires ARM architecture.")
        return False
    # Validate Raspberry Pi 5 model
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            if "Raspberry Pi 5" not in model:
                print_warning(f"Model does not appear to be Raspberry Pi 5: {model.strip()}")
                if not get_user_confirmation("Continue anyway?"):
                    return False
    except FileNotFoundError:
        print_warning("Cannot determine Raspberry Pi model. This utility is designed for Pi 5.")
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
        print_warning("Cannot determine OS version. This utility is designed for Ubuntu 24.10.")
        if not get_user_confirmation("Continue anyway?"):
            return False
    return True

# ==============================
# CPU and Cooling Management
# ==============================
def read_current_cpu_freq() -> int:
    """Read the current CPU frequency (Hz)."""
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
            return int(f.read().strip())
    except Exception as e:
        print_error(f"Failed to read CPU frequency: {e}")
        return 0

def read_cpu_temp() -> float:
    """Read the current CPU temperature (°C)."""
    try:
        with open(TEMP_PATH, "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception as e:
        print_error(f"Failed to read CPU temperature: {e}")
        return 0.0

def set_cpu_governor(governor: str = "performance") -> bool:
    """Set the CPU governor for all cores."""
    valid_governors = ["performance", "powersave", "userspace", "ondemand", "conservative", "schedutil"]
    if governor not in valid_governors:
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
    """Set the fan speed (0–255)."""
    try:
        # Find fan control paths using shell globbing
        fan_control_actual = subprocess.getoutput("ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1")
        fan_manual_actual = subprocess.getoutput("ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable")
        if not os.path.exists(fan_manual_actual):
            print_error(f"Fan control path not found: {fan_manual_actual}")
            return False
        with open(fan_manual_actual, "w") as f:
            f.write("1")  # Enable manual control
        if not os.path.exists(fan_control_actual):
            print_error(f"Fan control path not found: {fan_control_actual}")
            return False
        with open(fan_control_actual, "w") as f:
            validated_speed = max(0, min(speed, FAN_MAX_SPEED))
            f.write(str(validated_speed))
        print_success(f"Fan speed set to {validated_speed}/{FAN_MAX_SPEED}")
        return True
    except Exception as e:
        print_error(f"Failed to set fan speed: {e}")
        return False

def backup_config_file() -> bool:
    """Backup the boot configuration file."""
    if os.path.exists(CONFIG_BOOT):
        try:
            shutil.copy2(CONFIG_BOOT, BACKUP_CONFIG)
            print_success(f"Backup created: {CONFIG_BOOT} -> {BACKUP_CONFIG}")
            return True
        except Exception as e:
            print_error(f"Failed to backup config: {e}")
            return False
    else:
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False

def update_config_for_overclock() -> bool:
    """Update config.txt to enable overclocking to 3.1 GHz."""
    if not os.path.exists(CONFIG_BOOT):
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False
    if not backup_config_file():
        if not get_user_confirmation("Continue without backup?"):
            return False
    try:
        with open(CONFIG_BOOT, "r") as f:
            config_lines = f.readlines()
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
        with open(CONFIG_BOOT, "w") as f:
            f.writelines(config_lines)
        print_success(f"Updated {CONFIG_BOOT} with overclock settings")
        print_info("Changes will take effect after reboot")
        return True
    except Exception as e:
        print_error(f"Failed to update config: {e}")
        return False

def setup_systemd_service() -> bool:
    """Create and enable a systemd service to apply settings at boot."""
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR)
        except Exception as e:
            print_error(f"Failed to create config directory: {e}")
            return False
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
        import glob
        fan_control = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1")[0]
        fan_manual = glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable")[0]
        with open(fan_manual, 'w') as f:
            f.write("1")
        with open(fan_control, 'w') as f:
            f.write("255")
    except Exception:
        pass

if __name__ == "__main__":
    time.sleep(5)
    set_cpu_governor()
    set_fan_speed()
""")
        os.chmod(script_path, 0o755)
    except Exception as e:
        print_error(f"Failed to create startup script: {e}")
        return False
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
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "pi5_overclock.service"], check=True)
        subprocess.run(["systemctl", "start", "pi5_overclock.service"], check=True)
        print_success("Created and enabled systemd service for startup")
        return True
    except Exception as e:
        print_error(f"Failed to setup systemd service: {e}")
        return False

def monitor_temperature_and_frequency(duration: int = 60) -> None:
    """Monitor CPU temperature and frequency for a specified duration."""
    print_section("Temperature and Frequency Monitor")
    print_info(f"Monitoring for {duration} seconds. Press Ctrl+C to stop.")
    print_info(f"Target frequency: {TARGET_FREQ_GHZ} GHz | Critical temperature: {CRITICAL_TEMP}°C")
    console.print(f"[bold]{'Time':<12} {'Temperature':<20} {'Frequency':<15} {'Status':<10}[/bold]")
    console.print("─" * 60)
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            current_temp = read_cpu_temp()
            current_freq = read_current_cpu_freq()
            current_freq_ghz = current_freq / 1000000
            if current_temp >= CRITICAL_TEMP:
                status = f"[bold {NordColors.NORD11}]CRITICAL[/]"
            elif current_temp >= WARNING_TEMP:
                status = f"[bold {NordColors.NORD13}]WARNING[/]"
            elif current_freq >= TARGET_FREQ - 100000:  # within 100MHz
                status = f"[bold {NordColors.NORD14}]OPTIMAL[/]"
            else:
                status = f"[{NordColors.NORD4}]OK[/]"
            temp_color = NordColors.NORD11 if current_temp >= CRITICAL_TEMP else (NordColors.NORD13 if current_temp >= WARNING_TEMP else NordColors.NORD14)
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            console.print(f"{timestamp:<12} [{temp_color}]{current_temp:.1f}°C[/] {'':10} {current_freq_ghz:.2f} GHz {'':5} {status}")
            time.sleep(1)
    except KeyboardInterrupt:
        print_warning("\nMonitoring stopped by user.")

def apply_all_settings() -> bool:
    """Apply overclocking, CPU governor, and fan settings."""
    print_section("Applying All Settings")
    success = True
    print_step("Setting CPU governor to performance mode...")
    if not set_cpu_governor("performance"):
        success = False
    print_step("Setting fan to maximum speed...")
    if not set_fan_speed(FAN_MAX_SPEED):
        success = False
    print_step("Updating boot configuration for overclocking...")
    if not update_config_for_overclock():
        success = False
    print_step("Setting up startup service...")
    if not setup_systemd_service():
        success = False
    if success:
        print_success("All settings applied successfully!")
        print_warning("A system reboot is required for changes to take effect.")
        if get_user_confirmation("Reboot now?"):
            print_info("Rebooting system...")
            subprocess.run(["reboot"])
    else:
        print_warning("Some settings failed to apply. See errors above.")
    return success

# ==============================
# Menu Systems
# ==============================
def main_menu() -> None:
    """Display the main menu and process user selections."""
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
                duration_input = get_user_input("Monitoring duration in seconds (default: 60)")
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
    """Main entry point for the utility."""
    try:
        setup_logging()
        if not check_root():
            print_error("This script requires root privileges.")
            print_info("Please run with: sudo python3 pi5_overclock.py")
            sys.exit(1)
        if not validate_system():
            print_error("System validation failed.")
            sys.exit(1)
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