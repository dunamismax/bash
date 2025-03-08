#!/usr/bin/env python3
"""
Raspberry Pi 5 Overclocking Utility
--------------------------------------------------

A comprehensive utility for overclocking and managing the Raspberry Pi 5.
This unattended script automatically applies CPU frequency control,
fan management, boot configuration updates for overclocking, and sets up
a systemd service for persistence.

Version: 1.0.0
"""

import atexit
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from typing import Any


# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Installing required dependencies...")
    subprocess.run(["pip", "install", "rich", "pyfiglet"], check=False)
    print("Please restart the script after installation.")
    sys.exit(1)

# Enable rich traceback for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
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
TARGET_FREQ: int = int(TARGET_FREQ_GHZ * 1000000)  # in Hz
DEFAULT_FREQ: int = 2400000  # Default frequency in Hz
FAN_MAX_SPEED: int = 255  # Maximum PWM value
CRITICAL_TEMP: int = 80  # °C
WARNING_TEMP: int = 75  # °C
OPERATION_TIMEOUT: int = 30  # seconds

# Terminal sizing (clamped)
import shutil

TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming."""

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Console Helpers and UI Components
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with Nord styling.
    Returns:
        A Panel containing the styled header.
    """
    fonts = ["small", "slant", "mini", "digital", "standard"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=60)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = f"{APP_NAME}\n"
    # Apply a gradient effect
    lines = [line for line in ascii_art.split("\n") if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        styled_text += f"[bold {colors[i % len(colors)]}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    styled_text = f"{border}\n{styled_text}{border}"
    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_info(message: str) -> None:
    print_message(message, NordColors.FROST_3, "ℹ")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{title.center(TERM_WIDTH)}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def clear_screen() -> None:
    console.clear()


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
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
    print_step("Cleaning up resources...")


def signal_handler(signum: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    print_warning(f"\nProcess interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# System Validation Functions
# ----------------------------------------------------------------
def check_root() -> bool:
    return os.geteuid() == 0


def validate_system() -> bool:
    machine = platform.machine()
    if not machine.startswith(("aarch64", "arm")):
        print_error(f"Unsupported architecture: {machine}. Requires ARM.")
        return False

    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            if "Raspberry Pi 5" not in model:
                print_warning(f"Model is not Raspberry Pi 5: {model.strip()}")
                # In unattended mode, we log a warning and continue
    except FileNotFoundError:
        print_warning("Cannot determine Raspberry Pi model. Continuing anyway.")

    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            os_info = f.read()
            if "Ubuntu" not in os_info or "24.10" not in os_info:
                print_warning(
                    "This utility is designed for Ubuntu 24.10. Detected OS may differ."
                )
                # Continue in unattended mode
    else:
        print_warning("Cannot determine OS version. Continuing anyway.")

    return True


# ----------------------------------------------------------------
# CPU and Cooling Management Functions
# ----------------------------------------------------------------
def read_current_cpu_freq() -> int:
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
            return int(f.read().strip())
    except Exception as e:
        print_error(f"Failed to read CPU frequency: {e}")
        return 0


def read_cpu_temp() -> float:
    try:
        with open(TEMP_PATH, "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception as e:
        print_error(f"Failed to read CPU temperature: {e}")
        return 0.0


def set_cpu_governor(governor: str = "performance") -> bool:
    valid = [
        "performance",
        "powersave",
        "userspace",
        "ondemand",
        "conservative",
        "schedutil",
    ]
    if governor not in valid:
        print_error(f"Invalid governor: {governor}")
        return False
    success = True
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]Setting CPU governor to {governor}"),
        console=console,
    ) as progress:
        task = progress.add_task("Working", total=4)
        for cpu in range(4):  # Assuming 4 cores for Pi 5
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
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Setting fan speed"),
            console=console,
        ) as progress:
            task = progress.add_task("Working", total=3)
            progress.update(task, description="Locating fan control paths")
            fan_control = subprocess.getoutput(
                "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1"
            )
            fan_manual = subprocess.getoutput(
                "ls -1 /sys/devices/platform/cooling_fan/hwmon/hwmon*/pwm1_enable"
            )
            progress.advance(task)
            progress.update(task, description="Enabling manual fan control")
            if not os.path.exists(fan_manual):
                print_error(f"Fan control path not found: {fan_manual}")
                return False
            with open(fan_manual, "w") as f:
                f.write("1")
            progress.advance(task)
            progress.update(
                task, description=f"Setting fan speed to {speed}/{FAN_MAX_SPEED}"
            )
            if not os.path.exists(fan_control):
                print_error(f"Fan control path not found: {fan_control}")
                return False
            validated_speed = max(0, min(speed, FAN_MAX_SPEED))
            with open(fan_control, "w") as f:
                f.write(str(validated_speed))
            progress.advance(task)
        print_success(f"Fan speed set to {validated_speed}/{FAN_MAX_SPEED}")
        return True
    except Exception as e:
        print_error(f"Failed to set fan speed: {e}")
        return False


def backup_config_file() -> bool:
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
            print_warning(f"Failed to backup config: {e}")
            # Continue automatically even if backup fails
            return False
    else:
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False


def update_config_for_overclock() -> bool:
    if not os.path.exists(CONFIG_BOOT):
        print_error(f"Config file not found: {CONFIG_BOOT}")
        return False
    # In unattended mode, proceed even if backup fails.
    backup_config_file()
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Updating boot configuration"),
            console=console,
        ) as progress:
            task = progress.add_task("Working", total=3)
            progress.update(task, description="Reading current configuration")
            with open(CONFIG_BOOT, "r") as f:
                config_lines = f.readlines()
            progress.advance(task)
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
            progress.update(task, description="Creating startup script")
            with open(script_path, "w") as f:
                f.write(f"""#!/usr/bin/env python3
# Automatically generated by {APP_NAME} Utility v{VERSION}
# Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
import os
import time
import glob
import logging

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
        with open(fan_manual_paths[0], 'w') as f:
            f.write("1")
        with open(fan_control_paths[0], 'w') as f:
            f.write("255")
        logging.info("Set fan speed to 255")
    except Exception as e:
        logging.error(f"Failed to set fan speed: {{e}}")

if __name__ == "__main__":
    logging.info("Pi 5 Overclock service starting")
    time.sleep(5)
    set_cpu_governor()
    set_fan_speed()
    logging.info("Pi 5 Overclock service completed")
""")
            os.chmod(script_path, 0o755)
            progress.advance(task)
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
            progress.update(task, description="Reloading systemd and enabling service")
            run_command(["systemctl", "daemon-reload"])
            run_command(["systemctl", "enable", "pi5_overclock.service"])
            progress.advance(task)
            progress.update(task, description="Starting the service")
            run_command(["systemctl", "start", "pi5_overclock.service"])
            progress.advance(task)
        print_success("Created and enabled systemd service for startup")
        return True
    except Exception as e:
        print_error(f"Failed to setup systemd service: {e}")
        return False


# ----------------------------------------------------------------
# Automated Application of Settings
# ----------------------------------------------------------------
def apply_all_settings() -> bool:
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
        display_panel(
            f"[bold {NordColors.GREEN}]Successfully configured Pi 5 for {TARGET_FREQ_GHZ} GHz operation![/]\n\n"
            "• CPU governor: performance\n"
            "• Fan speed: maximum\n"
            "• Boot config: updated\n"
            "• Startup service: enabled\n\n"
            f"[bold {NordColors.YELLOW}]A system reboot is required for changes to take effect.[/]",
            style=NordColors.FROST_2,
            title="Configuration Complete",
        )
    else:
        print_warning("Some settings failed to apply. Check errors above.")
    return success


# ----------------------------------------------------------------
# Main Entry Point (Automated Mode)
# ----------------------------------------------------------------
def main() -> None:
    try:
        clear_screen()
        console.print(create_header())
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
                display_panel(
                    f"[bold {NordColors.RED}]This script requires root privileges.[/]\n\n"
                    f"Please run with: sudo python3 {Path(__file__).name}",
                    style=NordColors.RED,
                    title="Permission Error",
                )
                sys.exit(1)
            progress.advance(task)
            time.sleep(0.5)
            progress.update(task, description="Validating system")
            if not validate_system():
                clear_screen()
                console.print(create_header())
                display_panel(
                    f"[bold {NordColors.RED}]System validation failed.[/]\n\n"
                    "This utility is designed for Raspberry Pi 5 running Ubuntu 24.10.",
                    style=NordColors.RED,
                    title="System Error",
                )
                sys.exit(1)
            progress.advance(task)
        # Apply settings automatically
        if apply_all_settings():
            # In unattended mode, wait briefly then reboot automatically.
            print_info("Rebooting system in 5 seconds...")
            time.sleep(5)
            subprocess.run(["reboot"])
        else:
            print_warning(
                "Configuration did not complete successfully. Aborting reboot."
            )
            sys.exit(1)
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
