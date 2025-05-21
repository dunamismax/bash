#!/usr/bin/env python3
"""
Automated Ubuntu VoIP Setup Utility
--------------------------------------------------

A powerful, fully unattended terminal-based utility that automatically sets up and configures VoIP services on Ubuntu systems.
This script performs the following operations:
  • Verifies system compatibility and prerequisites
  • Updates system packages
  • Installs required VoIP packages (Asterisk, MariaDB, ufw)
  • Configures firewall rules for SIP and RTP
  • Creates or updates Asterisk configuration files (backing up existing ones)
  • Manages services (enabling and restarting Asterisk and MariaDB)
  • Verifies the overall setup

Note: This script requires root privileges.
Usage: sudo python3 voip_setup.py

Version: 3.0.0
"""

import atexit
import datetime
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
        TaskID,
    )
    from rich.style import Style
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "This script requires the 'rich' and 'pyfiglet' libraries.\nPlease install them using: pip install rich pyfiglet"
    )
    sys.exit(1)

# Install rich traceback for detailed error output.
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME = "VoIP Setup"
APP_SUBTITLE = "Automated VoIP Service Configuration"
VERSION = "3.0.0"
HOSTNAME = socket.gethostname()
LOG_FILE = "/var/log/voip_setup.log"
OPERATION_TIMEOUT = 300  # seconds

# Detect system and OS type
IS_LINUX = sys.platform.startswith("linux")
IS_UBUNTU = False
if IS_LINUX:
    try:
        with open("/etc/os-release") as f:
            if "ubuntu" in f.read().lower():
                IS_UBUNTU = True
    except Exception:
        pass

# Terminal dimensions
TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)

# VoIP packages and configuration
VOIP_PACKAGES = [
    "asterisk",
    "asterisk-config",
    "mariadb-server",
    "mariadb-client",
    "ufw",
]

FIREWALL_RULES = [
    {"port": "5060", "protocol": "udp", "description": "SIP"},
    {"port": "5061", "protocol": "tcp", "description": "SIP/TLS"},
    {"port": "16384:32767", "protocol": "udp", "description": "RTP Audio"},
]

ASTERISK_CONFIGS = {
    "sip_custom.conf": """[general]
disallow=all
allow=g722
context=internal
bindport=5060
bindaddr=0.0.0.0
transport=udp,tcp
alwaysauthreject=yes
directmedia=no
nat=force_rport,comedia

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

SERVICES = ["asterisk", "mariadb"]


# ----------------------------------------------------------------
# Nord-Themed Colors for Rich Styling
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# Create a global Rich Console instance
console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ServiceStatus:
    name: str
    active: Optional[bool] = None
    enabled: Optional[bool] = None
    version: Optional[str] = None


@dataclass
class FirewallRule:
    port: str
    protocol: str
    description: str
    active: Optional[bool] = None


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with gradient Nord colors.
    """
    fonts = ["slant", "small", "smslant", "digital", "mini"]
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
        ascii_art = APP_NAME

    # Build gradient styled text
    lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    final_text = f"{border}\n{styled_text}{border}"
    return Panel(
        Text.from_markup(final_text),
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
    logging.info(f"{prefix} {text}")


def print_info(msg: str) -> None:
    print_message(msg, NordColors.FROST_3, "ℹ")


def print_success(msg: str) -> None:
    print_message(msg, NordColors.GREEN, "✓")


def print_warning(msg: str) -> None:
    print_message(msg, NordColors.YELLOW, "⚠")
    logging.warning(msg)


def print_error(msg: str) -> None:
    print_message(msg, NordColors.RED, "✗")
    logging.error(msg)


def print_step(msg: str) -> None:
    print_message(msg, NordColors.FROST_2, "→")


def print_section(title: str) -> None:
    border = "━" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.FROST_3}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]  {title}  [/]")
    console.print(f"[bold {NordColors.FROST_3}]{border}[/]\n")
    logging.info(f"SECTION: {title}")


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
def setup_logging(log_file: str = LOG_FILE) -> None:
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
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(console_handler)
        print_step(f"Logging configured to: {log_file}")
    except Exception as e:
        print_warning(f"Logging setup failed: {e}")
        logging.basicConfig(level=logging.INFO)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_step("Performing cleanup tasks...")
    logging.info("Cleanup completed.")


def signal_handler(sig: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"\nScript interrupted by {sig_name}.")
    logging.warning(f"Interrupted by {sig_name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
    silent: bool = False,
) -> subprocess.CompletedProcess:
    cmd_str = " ".join(cmd)
    if not silent:
        print_step(f"Running: {cmd_str}")
    logging.info(f"Executing command: {cmd_str}")
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=False,  # manual error handling below
            text=True,
            capture_output=capture_output,
            timeout=timeout or OPERATION_TIMEOUT,
        )
        if result.returncode != 0 and check:
            if not silent:
                print_error(f"Command failed ({result.returncode}): {cmd_str}")
                if result.stdout.strip():
                    console.print(f"[dim]{result.stdout.strip()}[/dim]")
                if result.stderr.strip():
                    console.print(f"[bold {NordColors.RED}]{result.stderr.strip()}[/]")
            logging.error(f"Command failed: {cmd_str}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        else:
            if not silent and result.stdout.strip() and len(result.stdout) < 1000:
                console.print(f"[dim]{result.stdout.strip()}[/dim]")
        return result
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out: {cmd_str}")
        logging.error(f"Timeout: {cmd_str}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {cmd_str}\nDetails: {e}")
        logging.error(f"Execution error: {cmd_str}\n{e}")
        raise


# ----------------------------------------------------------------
# Progress Tracking Manager
# ----------------------------------------------------------------
class ProgressManager:
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TextColumn("{task.fields[status]}"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> TaskID:
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"[{NordColors.FROST_3}]starting",
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


# ----------------------------------------------------------------
# System Check Functions
# ----------------------------------------------------------------
def check_privileges() -> bool:
    try:
        if os.name == "nt":
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False


def check_system_compatibility() -> bool:
    print_section("System Compatibility Check")
    compatible = True
    if not check_privileges():
        print_error("Root privileges are required. Please run with sudo.")
        compatible = False
    else:
        print_success("Root privileges confirmed")
    if not IS_LINUX:
        print_error("This script is designed for Linux systems.")
        compatible = False
    else:
        print_success("Linux system detected")
    if not IS_UBUNTU:
        print_warning("Non-Ubuntu Linux detected. Some features might be affected.")
    else:
        print_success("Ubuntu system detected")
    if not shutil.which("apt-get"):
        print_error("apt-get not found. This script requires Ubuntu/Debian.")
        compatible = False
    else:
        print_success("apt-get is available")
    # Memory check
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
            mem_total = (
                int(
                    [line for line in meminfo.splitlines() if "MemTotal" in line][
                        0
                    ].split()[1]
                )
                // 1024
            )
            if mem_total < 512:
                print_warning(f"Low memory: {mem_total}MB (min recommended: 1GB)")
            else:
                print_success(f"Memory check: {mem_total}MB available")
    except Exception:
        print_warning("Could not determine system memory")
    # Internet connectivity
    print_step("Checking internet connectivity...")
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Testing connectivity"),
            console=console,
        ) as progress:
            task = progress.add_task("Ping test", total=1)
            result = run_command(["ping", "-c", "1", "-W", "2", "8.8.8.8"], silent=True)
            progress.update(task, completed=1)
        if result.returncode == 0:
            print_success("Internet connectivity confirmed")
        else:
            print_warning("Internet connectivity issues detected")
            compatible = False
    except Exception as e:
        print_error(f"Connectivity check failed: {e}")
        compatible = False
    if compatible:
        print_success("System is compatible with VoIP setup")
    else:
        print_warning("Some system compatibility issues detected")
    return compatible


# ----------------------------------------------------------------
# VoIP Setup Task Functions
# ----------------------------------------------------------------
def update_system() -> bool:
    print_section("Updating System Packages")
    try:
        with Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Updating package lists"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Updating", total=1)
            run_command(["apt-get", "update"], silent=True)
            progress.update(task, completed=1)
        print_success("Package lists updated")
        # Determine upgrade count for progress reporting
        try:
            result = run_command(
                ["apt", "list", "--upgradable"], capture_output=True, silent=True
            )
            lines = result.stdout.splitlines()
            package_count = max(1, len(lines) - 1)
            print_info(f"{package_count} packages are upgradable")
        except Exception:
            package_count = 10
            print_warning("Could not determine package upgrade count")
        with ProgressManager() as progress:
            task = progress.add_task("Upgrading packages", total=package_count)
            process = subprocess.Popen(
                ["apt-get", "upgrade", "-y"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in iter(process.stdout.readline, ""):
                if "Unpacking" in line or "Setting up" in line:
                    progress.update(task, advance=1)
                status = f"[{NordColors.FROST_3}]{line.strip()[:40]}"
                progress.update(task, status=status)
            process.wait()
            if process.returncode != 0:
                print_error("System upgrade failed")
                return False
        print_success("System upgraded successfully")
        return True
    except Exception as e:
        print_error(f"Update failed: {e}")
        return False


def install_packages(packages: List[str]) -> bool:
    print_section("Installing VoIP Packages")
    print_info(f"Installing: {', '.join(packages)}")
    failed = []
    with ProgressManager() as progress:
        task = progress.add_task("Installing packages", total=len(packages))
        for pkg in packages:
            print_step(f"Installing {pkg}")
            try:
                env = os.environ.copy()
                env["DEBIAN_FRONTEND"] = "noninteractive"
                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                for line in iter(proc.stdout.readline, ""):
                    status = f"[{NordColors.FROST_3}]{line.strip()[:40]}"
                    progress.update(task, status=status)
                proc.wait()
                if proc.returncode != 0:
                    print_error(f"Installation failed: {pkg}")
                    failed.append(pkg)
                else:
                    print_success(f"{pkg} installed")
            except Exception as e:
                print_error(f"Error installing {pkg}: {e}")
                failed.append(pkg)
            progress.update(task, advance=1)
    if failed:
        print_warning(f"Failed to install: {', '.join(failed)}")
        return False
    print_success("All packages installed")
    return True


def configure_firewall(rules: List[Dict[str, str]]) -> bool:
    print_section("Configuring Firewall")
    try:
        if not shutil.which("ufw"):
            print_warning("ufw not found; installing ufw...")
            if not install_packages(["ufw"]):
                return False
        with ProgressManager() as progress:
            task = progress.add_task("Configuring firewall", total=len(rules) + 2)
            status_result = run_command(["ufw", "status"], silent=True)
            if "Status: inactive" in status_result.stdout:
                print_step("Enabling ufw")
                run_command(["ufw", "--force", "enable"])
            progress.update(task, advance=1)
            for rule in rules:
                desc = f"{rule['port']}/{rule['protocol']} ({rule['description']})"
                print_step(f"Adding rule: {desc}")
                run_command(["ufw", "allow", f"{rule['port']}/{rule['protocol']}"])
                progress.update(task, advance=1)
            print_step("Reloading ufw")
            run_command(["ufw", "reload"])
            progress.update(task, advance=1)
        print_success("Firewall configured")
        return True
    except Exception as e:
        print_error(f"Firewall configuration failed: {e}")
        return False


def create_asterisk_config(configs: Dict[str, str]) -> bool:
    print_section("Creating Asterisk Configuration Files")
    try:
        config_dir = Path("/etc/asterisk")
        if not config_dir.exists():
            print_step(f"Creating directory: {config_dir}")
            config_dir.mkdir(parents=True, exist_ok=True)
        with ProgressManager() as progress:
            task = progress.add_task("Creating config files", total=len(configs))
            for filename, content in configs.items():
                file_path = config_dir / filename
                print_step(f"Processing {filename}")
                if file_path.exists():
                    backup = file_path.with_suffix(f".bak.{int(time.time())}")
                    shutil.copy2(file_path, backup)
                    print_info(f"Backup created: {backup.name}")
                file_path.write_text(content)
                print_success(f"{filename} written")
                progress.update(task, advance=1)
        print_success("Asterisk configuration complete")
        return True
    except Exception as e:
        print_error(f"Asterisk config failed: {e}")
        return False


def manage_services(services: List[str], action: str) -> bool:
    valid_actions = ["enable", "start", "restart", "stop"]
    if action not in valid_actions:
        print_error(f"Invalid service action: {action}")
        return False
    print_section(f"{action.capitalize()}ing Services")
    failed = []
    with ProgressManager() as progress:
        task = progress.add_task(
            f"{action.capitalize()}ing services", total=len(services)
        )
        for service in services:
            print_step(f"{action.capitalize()}ing {service}")
            try:
                run_command(["systemctl", action, service])
                print_success(f"{service} {action}ed")
            except Exception as e:
                print_error(f"Failed to {action} {service}: {e}")
                failed.append(service)
            progress.update(task, advance=1)
    if failed:
        print_warning(f"Services failed to {action}: {', '.join(failed)}")
        return False
    print_success(f"All services {action}ed")
    return True


def verify_installation() -> bool:
    print_section("Verifying VoIP Setup")
    verification_checks = []
    verification_checks.append(
        ("Asterisk Installation", lambda: bool(shutil.which("asterisk")))
    )
    verification_checks.append(
        ("MariaDB Installation", lambda: bool(shutil.which("mysql")))
    )
    for svc in SERVICES:
        verification_checks.append(
            (
                f"{svc.capitalize()} Service",
                lambda s=svc: run_command(
                    ["systemctl", "is-active", s], check=False, silent=True
                ).stdout.strip()
                == "active",
            )
        )
    config_dir = Path("/etc/asterisk")
    for filename in ASTERISK_CONFIGS.keys():
        verification_checks.append(
            (f"{filename} exists", lambda f=filename: (config_dir / f).exists())
        )
    try:
        ufw_status = run_command(
            ["ufw", "status"], capture_output=True, silent=True
        ).stdout
        for rule in FIREWALL_RULES:
            rule_str = f"{rule['port']}/{rule['protocol']}"
            verification_checks.append(
                (f"Firewall rule {rule_str}", lambda r=rule_str: r in ufw_status)
            )
    except Exception:
        pass

    passed = []
    failed = []
    with ProgressManager() as progress:
        task = progress.add_task(
            "Verifying installation", total=len(verification_checks)
        )
        for name, check_func in verification_checks:
            print_step(f"Verifying: {name}")
            try:
                if check_func():
                    print_success(f"{name}: Passed")
                    passed.append(name)
                else:
                    print_error(f"{name}: Failed")
                    failed.append(name)
            except Exception as e:
                print_error(f"Error verifying {name}: {e}")
                failed.append(name)
            progress.update(task, advance=1)
    print_section("Verification Summary")
    console.print(
        f"Passed: [bold {NordColors.GREEN}]{len(passed)}/{len(verification_checks)}[/]"
    )
    console.print(
        f"Failed: [bold {NordColors.RED}]{len(failed)}/{len(verification_checks)}[/]"
    )
    if failed:
        print_warning("The following checks failed:")
        for item in failed:
            console.print(f"[{NordColors.RED}]• {item}[/]")
    if len(passed) == len(verification_checks):
        print_success("VoIP setup verified successfully!")
        return True
    else:
        print_warning("Some verification checks failed.")
        return False


# ----------------------------------------------------------------
# Main Execution Flow (Fully Unattended)
# ----------------------------------------------------------------
def main() -> None:
    start_time = time.time()
    console.clear()
    console.print(create_header())
    setup_logging()
    console.print(
        Align.center(
            f"[{NordColors.FROST_3}]Hostname:[/] [{NordColors.SNOW_STORM_1}]{HOSTNAME}[/]    "
            f"[{NordColors.FROST_3}]System:[/] [{NordColors.SNOW_STORM_1}]{platform.system()} {platform.release()}[/]    "
            f"[{NordColors.FROST_3}]Time:[/] [{NordColors.SNOW_STORM_1}]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
    )
    console.print()
    if not check_privileges():
        print_error("Root privileges are required. Exiting.")
        sys.exit(1)
    system_ok = check_system_compatibility()
    if not system_ok:
        print_warning("Compatibility issues detected. Proceeding with caution.")
    tasks = [
        ("Update system packages", update_system),
        ("Install VoIP packages", lambda: install_packages(VOIP_PACKAGES)),
        ("Configure firewall", lambda: configure_firewall(FIREWALL_RULES)),
        (
            "Create Asterisk configuration",
            lambda: create_asterisk_config(ASTERISK_CONFIGS),
        ),
        ("Enable services", lambda: manage_services(SERVICES, "enable")),
        ("Restart services", lambda: manage_services(SERVICES, "restart")),
        ("Verify installation", verify_installation),
    ]
    overall_success = True
    failed_tasks = []
    with ProgressManager() as progress:
        overall = progress.add_task("Overall Setup Progress", total=len(tasks))
        for task_name, task_func in tasks:
            print_section(f"Task: {task_name}")
            try:
                if not task_func():
                    print_warning(f"Task '{task_name}' encountered issues")
                    failed_tasks.append(task_name)
                    overall_success = False
                else:
                    print_success(f"Task '{task_name}' completed successfully")
            except Exception as e:
                print_error(f"Task '{task_name}' failed: {e}")
                failed_tasks.append(task_name)
                overall_success = False
            progress.update(overall, advance=1)
    elapsed = time.time() - start_time
    minutes, seconds = divmod(elapsed, 60)
    print_section("Setup Summary")
    print_success(f"Elapsed time: {int(minutes)}m {int(seconds)}s")
    if overall_success:
        print_success("VoIP setup completed successfully!")
    else:
        print_warning("VoIP setup completed with errors in the following tasks:")
        for task in failed_tasks:
            console.print(f"[{NordColors.RED}]• {task}[/]")
    print_section("Next Steps")
    console.print(
        f"[{NordColors.SNOW_STORM_1}]1. Review the Asterisk configuration files in /etc/asterisk/[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]2. Configure your SIP clients using the credentials defined in sip_custom.conf[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]3. Test calls between extensions (e.g., 6001 and 6002)[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]4. Secure your SIP traffic with TLS for production deployments[/]"
    )
    console.print(
        f"[{NordColors.SNOW_STORM_1}]5. Consider additional configuration for voicemail and call routing[/]"
    )
    logging.info("VoIP setup execution completed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.exception("Unexpected error occurred")
        sys.exit(1)
