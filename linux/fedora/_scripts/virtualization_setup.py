#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup for Fedora
------------------------------------------------------
A fully unattended terminal utility for automatically setting up a complete
virtualization environment on Fedora. This script updates package caches,
installs required virtualization packages, manages services, configures
the default NAT network, fixes storage permissions, configures user groups,
sets up and starts virtual machines, verifies the setup, and installs a
systemd service to maintain configuration.

Version: 2.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import datetime
import grp
import os
import platform
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional


def install_missing_packages() -> None:
    """Install required packages if missing."""
    required_packages = ["rich", "pyfiglet", "prompt_toolkit"]
    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("Packages installed. Restarting script...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Failed to install packages: {e}")
            sys.exit(1)


install_missing_packages()

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
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
    from rich.theme import Theme
    from prompt_toolkit import prompt as pt_prompt
except ImportError as e:
    print(f"Error importing libraries: {e}")
    sys.exit(1)

install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Application Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    VERSION: str = "2.0.0"
    APP_NAME: str = "VirtSetup"
    APP_SUBTITLE: str = "Enhanced Virtualization Environment"
    OS_TARGET: str = "Fedora"
    try:
        HOSTNAME: str = socket.gethostname()
    except Exception:
        HOSTNAME = "Unknown"
    try:
        TERM_WIDTH: int = shutil.get_terminal_size().columns
    except Exception:
        TERM_WIDTH = 80
    DEFAULT_TIMEOUT: int = 300  # seconds for command operations

    # Virtualization settings for Fedora
    VIRTUALIZATION_PACKAGES: List[str] = [
        "qemu-kvm",
        "libvirt",
        "virt-install",
        "virt-manager",
        "bridge-utils",
        "ovmf",
        "virtinst",
        "libguestfs-tools",
        "virt-top",
    ]
    VIRTUALIZATION_SERVICES: List[str] = ["libvirtd", "virtlogd"]
    VM_STORAGE_PATHS: List[str] = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]
    # On Fedora the VM images are typically accessed by the 'qemu' group
    VM_OWNER: str = "root"
    VM_GROUP: str = "qemu"
    VM_DIR_MODE: int = 0o2770
    VM_FILE_MODE: int = 0o0660
    LIBVIRT_USER_GROUP: str = "libvirt"
    DEFAULT_NETWORK_XML: str = """<network>
  <name>default</name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.2' end='192.168.122.254'/>
    </dhcp>
  </ip>
</network>
"""
    SERVICE_PATH: Path = Path("/etc/systemd/system/virtualization_setup.service")
    SERVICE_CONTENT: str = """[Unit]
Description=Virtualization Setup Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {script_path}
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


def check_os() -> bool:
    """Verify that the operating system is Fedora."""
    try:
        with open("/etc/os-release") as f:
            data = f.read().lower()
        return "fedora" in data
    except Exception:
        return False


# ----------------------------------------------------------------
# Nord-Themed Colors and Console Setup
# ----------------------------------------------------------------
class NordColors:
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


console = Console(
    theme=Theme(
        {
            "info": f"bold {NordColors.FROST_2}",
            "warning": f"bold {NordColors.YELLOW}",
            "error": f"bold {NordColors.RED}",
            "success": f"bold {NordColors.GREEN}",
        }
    )
)


# ----------------------------------------------------------------
# Custom Exception Classes
# ----------------------------------------------------------------
class VirtualizationSetupError(Exception):
    pass


class CommandError(VirtualizationSetupError):
    pass


# ----------------------------------------------------------------
# Data Structures for Virtualization State
# ----------------------------------------------------------------
class VMState(Enum):
    RUNNING = auto()
    IDLE = auto()
    PAUSED = auto()
    SHUTDOWN = auto()
    CRASHED = auto()
    UNKNOWN = auto()

    @classmethod
    def from_libvirt_state(cls, state_str: str) -> "VMState":
        mapping = {
            "running": cls.RUNNING,
            "idle": cls.IDLE,
            "paused": cls.PAUSED,
            "shut off": cls.SHUTDOWN,
            "crashed": cls.CRASHED,
        }
        for key, state in mapping.items():
            if key in state_str.lower():
                return state
        return cls.UNKNOWN


@dataclass
class VirtualMachine:
    id: str
    name: str
    state_text: str
    autostart: Optional[bool] = None
    state: VMState = field(init=False)

    def __post_init__(self) -> None:
        self.state = VMState.from_libvirt_state(self.state_text)

    @property
    def is_running(self) -> bool:
        return self.state == VMState.RUNNING


@dataclass
class TaskResult:
    name: str
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Generate a dynamic ASCII art header using Pyfiglet.
    """
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=AppConfig.TERM_WIDTH - 10)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = AppConfig.APP_NAME
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (AppConfig.TERM_WIDTH - 4)}[/]"
    styled_text = border + "\n" + styled_text + border
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )
    return header_panel


def create_section_header(title: str) -> Panel:
    """Return a styled panel to serve as a section header."""
    return Panel(
        Text(title, style=f"bold {NordColors.FROST_1}"),
        border_style=Style(color=NordColors.FROST_3),
        padding=(0, 2),
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """Display a message panel with an optional title."""
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def wait_for_key() -> None:
    """Wait for the user to press Enter before continuing."""
    pt_prompt("Press Enter to exit...", style="bold " + NordColors.FROST_2)


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = AppConfig.DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """
    Execute a command and return the CompletedProcess object.
    Raises CommandError on failure.
    """
    try:
        if verbose:
            print_message(f"Executing: {' '.join(cmd)}", NordColors.FROST_3, "➜")
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
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        raise CommandError(f"Command failed: {' '.join(cmd)}")
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out: {' '.join(cmd)}", NordColors.RED, "✗")
        raise CommandError(f"Timeout: {' '.join(cmd)}")
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise CommandError(f"Error: {' '.join(cmd)}")


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup before exiting."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle interruption signals gracefully."""
    try:
        sig_name = signal.Signals(sig).name
    except Exception:
        sig_name = str(sig)
    print_message(f"Interrupted by signal {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


for s in [signal.SIGINT, signal.SIGTERM]:
    try:
        signal.signal(s, signal_handler)
    except Exception:
        pass
atexit.register(cleanup)


# ----------------------------------------------------------------
# Virtualization Setup Functions
# ----------------------------------------------------------------
def update_system_packages() -> TaskResult:
    console.print(create_section_header("Updating Package Cache"))
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Updating package cache...", spinner="dots"
        ):
            run_command(["dnf", "makecache"])
        print_message("Package cache updated successfully", NordColors.GREEN, "✓")
        return TaskResult(
            name="package_update", success=True, message="Package cache updated"
        )
    except Exception as e:
        print_message(f"Failed to update package cache: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="package_update", success=False, message=f"Update failed: {e}"
        )


def install_virtualization_packages(packages: List[str]) -> TaskResult:
    console.print(create_section_header("Installing Virtualization Packages"))
    if not packages:
        print_message("No packages specified", NordColors.YELLOW)
        return TaskResult(
            name="package_install", success=True, message="No packages specified"
        )
    total = len(packages)
    failed = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Installing packages", total=total)
        for pkg in packages:
            progress.update(task, description=f"Installing {pkg}")
            try:
                proc = subprocess.Popen(
                    ["dnf", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in iter(proc.stdout.readline, ""):
                    if any(x in line for x in ["Installing", "Complete"]):
                        console.print(
                            "  " + line.strip(), style=NordColors.SNOW_STORM_1
                        )
                proc.wait()
                if proc.returncode != 0:
                    print_message(f"Failed to install {pkg}", NordColors.RED, "✗")
                    failed.append(pkg)
                else:
                    print_message(f"{pkg} installed", NordColors.GREEN, "✓")
            except Exception as e:
                print_message(f"Error installing {pkg}: {e}", NordColors.RED, "✗")
                failed.append(pkg)
            progress.advance(task)
    if failed:
        return TaskResult(
            name="package_install",
            success=False,
            message=f"Failed to install {len(failed)} of {total} packages",
            details={"failed_packages": failed},
        )
    return TaskResult(
        name="package_install", success=True, message=f"Installed {total} packages"
    )


def manage_virtualization_services(services: List[str]) -> TaskResult:
    console.print(create_section_header("Managing Virtualization Services"))
    if not services:
        print_message("No services specified", NordColors.YELLOW)
        return TaskResult(
            name="services", success=True, message="No services specified"
        )
    total = len(services) * 2
    failed = []
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Managing services", total=total)
        for svc in services:
            for action, cmd in [
                ("enable", ["systemctl", "enable", svc]),
                ("start", ["systemctl", "start", svc]),
            ]:
                progress.update(task, description=f"{action.capitalize()}ing {svc}")
                try:
                    run_command(cmd)
                    print_message(f"{svc} {action}d", NordColors.GREEN, "✓")
                except Exception as e:
                    print_message(f"Failed to {action} {svc}: {e}", NordColors.RED, "✗")
                    failed.append(f"{svc} ({action})")
                progress.advance(task)
    if failed:
        return TaskResult(
            name="services",
            success=False,
            message=f"Issues with {len(failed)} service operations",
            details={"failed_services": failed},
        )
    return TaskResult(
        name="services", success=True, message=f"Managed {len(services)} services"
    )


def recreate_default_network() -> TaskResult:
    console.print(create_section_header("Recreating Default Network"))
    try:
        result = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "default" in result.stdout:
            print_message("Removing existing default network", NordColors.FROST_3)
            run_command(["virsh", "net-destroy", "default"], check=False)
            autostart_path = Path("/etc/libvirt/qemu/networks/autostart/default.xml")
            if autostart_path.exists() or autostart_path.is_symlink():
                autostart_path.unlink()
                print_message("Removed autostart link", NordColors.FROST_3)
            run_command(["virsh", "net-undefine", "default"], check=False)
            print_message("Undefined old network", NordColors.FROST_3)
        net_xml_path = Path("/tmp/default_network.xml")
        net_xml_path.write_text(AppConfig.DEFAULT_NETWORK_XML)
        print_message("Created network definition file", NordColors.FROST_3)
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Configuring network", total=3)
            progress.update(task, description="Defining network")
            run_command(["virsh", "net-define", str(net_xml_path)])
            progress.advance(task)
            progress.update(task, description="Starting network")
            run_command(["virsh", "net-start", "default"])
            progress.advance(task)
            progress.update(task, description="Setting autostart")
            run_command(["virsh", "net-autostart", "default"])
            progress.advance(task)
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        if "default" in net_list.stdout and "active" in net_list.stdout:
            print_message("Default network is active", NordColors.GREEN, "✓")
            return TaskResult(
                name="network_recreation",
                success=True,
                message="Default network recreated and active",
            )
        print_message(
            "Default network not active after recreation", NordColors.RED, "✗"
        )
        return TaskResult(
            name="network_recreation",
            success=False,
            message="Default network not active after recreation",
        )
    except Exception as e:
        print_message(f"Error recreating network: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="network_recreation", success=False, message=f"Network error: {e}"
        )


def configure_default_network() -> TaskResult:
    console.print(create_section_header("Configuring Default Network"))
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Checking network status...", spinner="dots"
        ):
            net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)
        if "default" in net_list.stdout:
            print_message("Default network exists", NordColors.FROST_3)
            if "active" not in net_list.stdout:
                print_message(
                    "Default network inactive, starting it", NordColors.FROST_3
                )
                try:
                    run_command(["virsh", "net-start", "default"])
                    print_message("Default network started", NordColors.GREEN, "✓")
                except Exception as e:
                    print_message(f"Network start failed: {e}", NordColors.RED, "✗")
                    return recreate_default_network()
        else:
            print_message("Default network missing, creating it", NordColors.FROST_3)
            return recreate_default_network()
        try:
            net_info = run_command(
                ["virsh", "net-info", "default"], capture_output=True
            )
            if "Autostart:      yes" not in net_info.stdout:
                print_message(
                    "Setting autostart for default network", NordColors.FROST_3
                )
                run_command(["virsh", "net-autostart", "default"])
                print_message("Network autostart enabled", NordColors.GREEN, "✓")
            else:
                print_message(
                    "Network autostart already enabled", NordColors.GREEN, "✓"
                )
        except Exception as e:
            print_message(f"Autostart configuration issue: {e}", NordColors.YELLOW, "⚠")
        return TaskResult(
            name="network_configuration",
            success=True,
            message="Default network configured",
        )
    except Exception as e:
        print_message(f"Network configuration error: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="network_configuration",
            success=False,
            message=f"Network configuration error: {e}",
        )


def get_virtual_machines() -> List[VirtualMachine]:
    """Retrieve virtual machine list using virsh."""
    vms = []
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Retrieving VM information...", spinner="dots"
        ):
            result = run_command(["virsh", "list", "--all"], capture_output=True)
            lines = result.stdout.strip().splitlines()
            sep_index = next(
                (i for i, line in enumerate(lines) if line.strip().startswith("----")),
                -1,
            )
            if sep_index < 0:
                return vms
            for line in lines[sep_index + 1 :]:
                parts = line.split()
                if len(parts) >= 3:
                    vm = VirtualMachine(
                        id=parts[0], name=parts[1], state_text=" ".join(parts[2:])
                    )
                    try:
                        info = run_command(
                            ["virsh", "dominfo", vm.name], capture_output=True
                        )
                        vm.autostart = "Autostart:      yes" in info.stdout
                    except Exception:
                        vm.autostart = None
                    vms.append(vm)
        return vms
    except Exception as e:
        print_message(f"Error retrieving VMs: {e}", NordColors.RED, "✗")
        return vms


def set_vm_autostart(vms: List[VirtualMachine]) -> TaskResult:
    console.print(create_section_header("Configuring VM Autostart"))
    if not vms:
        print_message("No VMs found", NordColors.YELLOW)
        return TaskResult(name="vm_autostart", success=True, message="No VMs found")
    failed = []
    success_count = 0
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Setting VM autostart", total=len(vms))
        for vm in vms:
            progress.update(task, description=f"Configuring {vm.name}")
            try:
                if vm.autostart:
                    print_message(
                        f"{vm.name} already set to autostart", NordColors.GREEN, "✓"
                    )
                    success_count += 1
                else:
                    run_command(["virsh", "autostart", vm.name])
                    vm.autostart = True
                    print_message(f"{vm.name} set to autostart", NordColors.GREEN, "✓")
                    success_count += 1
            except Exception as e:
                print_message(
                    f"Autostart failed for {vm.name}: {e}", NordColors.RED, "✗"
                )
                failed.append(vm.name)
            progress.advance(task)
    if failed:
        return TaskResult(
            name="vm_autostart",
            success=False,
            message=f"Autostart failed for {len(failed)} of {len(vms)} VMs",
            details={"failed_vms": failed},
        )
    return TaskResult(
        name="vm_autostart",
        success=True,
        message=f"Configured autostart for {success_count} VMs",
    )


def ensure_network_active_before_vm_start() -> bool:
    print_message("Verifying network status before starting VMs", NordColors.FROST_3)
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Checking network...", spinner="dots"
        ):
            net_list = run_command(["virsh", "net-list"], capture_output=True)
        for line in net_list.stdout.splitlines():
            if "default" in line and "active" in line:
                print_message("Default network is active", NordColors.GREEN, "✓")
                return True
        print_message(
            "Default network inactive; attempting recreation", NordColors.YELLOW, "⚠"
        )
        return recreate_default_network().success
    except Exception as e:
        print_message(f"Network verification error: {e}", NordColors.RED, "✗")
        return False


def start_virtual_machines(vms: List[VirtualMachine]) -> TaskResult:
    console.print(create_section_header("Starting Virtual Machines"))
    if not vms:
        print_message("No VMs found", NordColors.YELLOW)
        return TaskResult(
            name="vm_start", success=True, message="No VMs found to start"
        )
    to_start = [vm for vm in vms if not vm.is_running]
    if not to_start:
        print_message("All VMs are already running", NordColors.GREEN, "✓")
        return TaskResult(
            name="vm_start", success=True, message="All VMs already running"
        )
    if not ensure_network_active_before_vm_start():
        print_message(
            "Default network not active; VM start may fail", NordColors.RED, "✗"
        )
    failed = []
    success_count = 0
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting VMs", total=len(to_start))
        for vm in to_start:
            progress.update(task, description=f"Starting {vm.name}")
            success = False
            for attempt in range(1, 4):
                try:
                    result = run_command(["virsh", "start", vm.name], check=False)
                    if result.returncode == 0:
                        print_message(
                            f"{vm.name} started successfully", NordColors.GREEN, "✓"
                        )
                        vm.state = VMState.RUNNING
                        vm.state_text = "running"
                        success = True
                        success_count += 1
                        break
                    else:
                        if (
                            result.stderr
                            and "Only one live display may be active" in result.stderr
                        ):
                            print_message(
                                f"{vm.name} display conflict; retrying...",
                                NordColors.YELLOW,
                                "⚠",
                            )
                            time.sleep(5)
                        else:
                            print_message(
                                f"Failed to start {vm.name}: {result.stderr}",
                                NordColors.RED,
                                "✗",
                            )
                            break
                except Exception as e:
                    print_message(f"Error starting {vm.name}: {e}", NordColors.RED, "✗")
                    break
            if not success:
                failed.append(vm.name)
            progress.advance(task)
            time.sleep(2)
    if failed:
        return TaskResult(
            name="vm_start",
            success=False,
            message=f"Failed to start {len(failed)} of {len(to_start)} VMs",
            details={"failed_vms": failed},
        )
    return TaskResult(
        name="vm_start",
        success=True,
        message=f"Successfully started {success_count} VMs",
    )


def fix_storage_permissions(paths: List[str]) -> TaskResult:
    console.print(create_section_header("Fixing VM Storage Permissions"))
    if not paths:
        print_message("No storage paths specified", NordColors.YELLOW)
        return TaskResult(
            name="storage", success=True, message="No storage paths specified"
        )
    try:
        uid = pwd.getpwnam(AppConfig.VM_OWNER).pw_uid
        gid = grp.getgrnam(AppConfig.VM_GROUP).gr_gid
    except KeyError as e:
        print_message(f"User/group not found: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="storage", success=False, message=f"User/group error: {e}"
        )
    fixed_paths = []
    failed_paths = []
    for path_str in paths:
        path = Path(path_str)
        print_message(f"Processing {path}", NordColors.FROST_3)
        if not path.exists():
            print_message(
                f"{path} does not exist; creating directory", NordColors.YELLOW
            )
            try:
                path.mkdir(mode=AppConfig.VM_DIR_MODE, parents=True, exist_ok=True)
            except Exception as e:
                print_message(f"Failed to create {path}: {e}", NordColors.RED, "✗")
                failed_paths.append(str(path))
                continue
        total_items = sum(
            1 + len(dirs) + len(files) for _, dirs, files in os.walk(str(path))
        )
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Updating permissions for {path.name}", total=total_items
            )
            try:
                os.chown(str(path), uid, gid)
                os.chmod(str(path), AppConfig.VM_DIR_MODE)
                progress.advance(task)
                errors = False
                for root, dirs, files in os.walk(str(path)):
                    for d in dirs:
                        dpath = Path(root) / d
                        progress.update(task, description=f"Directory: {dpath.name}")
                        try:
                            os.chown(str(dpath), uid, gid)
                            os.chmod(str(dpath), AppConfig.VM_DIR_MODE)
                        except Exception as e:
                            print_message(
                                f"Error on {dpath}: {e}", NordColors.YELLOW, "⚠"
                            )
                            errors = True
                        progress.advance(task)
                    for f in files:
                        fpath = Path(root) / f
                        progress.update(task, description=f"File: {fpath.name}")
                        try:
                            os.chown(str(fpath), uid, gid)
                            os.chmod(str(fpath), AppConfig.VM_FILE_MODE)
                        except Exception as e:
                            print_message(
                                f"Error on {fpath}: {e}", NordColors.YELLOW, "⚠"
                            )
                            errors = True
                        progress.advance(task)
                if errors:
                    print_message(
                        f"Some permissions could not be set on {path}",
                        NordColors.YELLOW,
                        "⚠",
                    )
                else:
                    fixed_paths.append(str(path))
            except Exception as e:
                print_message(
                    f"Failed to update permissions on {path}: {e}", NordColors.RED, "✗"
                )
                failed_paths.append(str(path))
    if failed_paths:
        return TaskResult(
            name="storage",
            success=False,
            message=f"Fixed {len(fixed_paths)} paths, failed on {len(failed_paths)}",
            details={"fixed_paths": fixed_paths, "failed_paths": failed_paths},
        )
    print_message("Storage permissions updated successfully", NordColors.GREEN, "✓")
    return TaskResult(
        name="storage",
        success=True,
        message=f"Updated permissions on {len(fixed_paths)} paths",
    )


def configure_user_groups() -> TaskResult:
    console.print(create_section_header("Configuring User Group Membership"))
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print_message(
            "SUDO_USER not set; skipping group configuration", NordColors.YELLOW
        )
        return TaskResult(
            name="user_groups", success=True, message="SUDO_USER not set; skipping"
        )
    try:
        pwd.getpwnam(sudo_user)
        grp.getgrnam(AppConfig.LIBVIRT_USER_GROUP)
    except KeyError as e:
        print_message(f"User/group error: {e}", NordColors.RED, "✗")
        return TaskResult(name="user_groups", success=False, message=f"Error: {e}")
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary = grp.getgrgid(pwd.getpwnam(sudo_user).pw_gid).gr_name
    if primary not in user_groups:
        user_groups.append(primary)
    if AppConfig.LIBVIRT_USER_GROUP in user_groups:
        print_message(
            f"User '{sudo_user}' is already in group '{AppConfig.LIBVIRT_USER_GROUP}'",
            NordColors.GREEN,
            "✓",
        )
        return TaskResult(
            name="user_groups",
            success=True,
            message=f"User '{sudo_user}' is already in group",
        )
    try:
        with console.status(
            f"[bold {NordColors.FROST_3}]Adding user to group...", spinner="dots"
        ):
            run_command(
                ["usermod", "-a", "-G", AppConfig.LIBVIRT_USER_GROUP, sudo_user]
            )
        print_message(
            f"User '{sudo_user}' added to group '{AppConfig.LIBVIRT_USER_GROUP}'",
            NordColors.GREEN,
            "✓",
        )
        return TaskResult(
            name="user_groups",
            success=True,
            message=f"User '{sudo_user}' added (logout required)",
        )
    except Exception as e:
        print_message(f"Failed to add user to group: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="user_groups", success=False, message=f"Failed to add user: {e}"
        )


def verify_virtualization_setup() -> TaskResult:
    console.print(create_section_header("Verifying Virtualization Setup"))
    checks = [
        ("libvirtd Service", "systemctl is-active libvirtd", "active"),
        ("KVM Modules", "lsmod | grep kvm", "kvm"),
        ("Default Network", "virsh net-list", "default"),
    ]
    results = []
    details: Dict[str, Any] = {}
    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Running verification checks",
            total=len(checks) + len(AppConfig.VM_STORAGE_PATHS),
        )
        for name, cmd, expected in checks:
            progress.update(task, description=f"Checking {name}")
            try:
                if "|" in cmd:
                    parts = cmd.split("|")
                    p1 = subprocess.Popen(
                        parts[0].strip().split(), stdout=subprocess.PIPE
                    )
                    p2 = subprocess.Popen(
                        parts[1].strip().split(),
                        stdin=p1.stdout,
                        stdout=subprocess.PIPE,
                        text=True,
                    )
                    p1.stdout.close()
                    output = p2.communicate()[0]
                    result_check = expected in output
                else:
                    result_obj = run_command(
                        cmd.split(), check=False, capture_output=True
                    )
                    result_check = expected in (result_obj.stdout or "")
                if result_check:
                    print_message(f"{name}: OK", NordColors.GREEN, "✓")
                    results.append(True)
                    details[name] = "OK"
                else:
                    print_message(f"{name}: FAILED", NordColors.RED, "✗")
                    results.append(False)
                    details[name] = "FAILED"
            except Exception as e:
                print_message(f"{name} check error: {e}", NordColors.RED, "✗")
                results.append(False)
                details[name] = f"ERROR: {e}"
            progress.advance(task)
        for path_str in AppConfig.VM_STORAGE_PATHS:
            path = Path(path_str)
            progress.update(task, description=f"Checking storage: {path.name}")
            if path.exists():
                print_message(f"Storage exists: {path}", NordColors.GREEN, "✓")
                results.append(True)
                details[f"Storage {path}"] = "OK"
            else:
                print_message(f"Storage missing: {path}", NordColors.RED, "✗")
                try:
                    path.mkdir(mode=AppConfig.VM_DIR_MODE, parents=True, exist_ok=True)
                    print_message(
                        f"Created storage directory: {path}", NordColors.GREEN, "✓"
                    )
                    results.append(True)
                    details[f"Storage {path}"] = "Created"
                except Exception as e:
                    print_message(f"Failed to create {path}: {e}", NordColors.RED, "✗")
                    results.append(False)
                    details[f"Storage {path}"] = f"FAILED: {e}"
            progress.advance(task)
    if all(results):
        display_panel(
            "All verification checks passed! Your virtualization environment is ready.",
            NordColors.GREEN,
            "Verification Complete",
        )
        return TaskResult(
            name="verification",
            success=True,
            message="All checks passed",
            details=details,
        )
    else:
        failed_count = results.count(False)
        display_panel(
            f"{failed_count} verification check(s) failed. See details above.",
            NordColors.YELLOW,
            "Verification Issues",
        )
        return TaskResult(
            name="verification",
            success=False,
            message=f"{failed_count} check(s) failed",
            details=details,
        )


def install_and_enable_service() -> TaskResult:
    console.print(create_section_header("Installing Systemd Service"))
    current_script = Path(sys.argv[0]).resolve()
    service_content = AppConfig.SERVICE_CONTENT.format(script_path=str(current_script))
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Setting up service", total=4)
            progress.update(task, description="Installing service file")
            AppConfig.SERVICE_PATH.write_text(service_content)
            print_message(
                f"Service file installed to {AppConfig.SERVICE_PATH}",
                NordColors.GREEN,
                "✓",
            )
            progress.advance(task)
            progress.update(task, description="Reloading systemd")
            run_command(["systemctl", "daemon-reload"])
            print_message("Systemd daemon reloaded", NordColors.GREEN, "✓")
            progress.advance(task)
            progress.update(task, description="Enabling service")
            run_command(["systemctl", "enable", "virtualization_setup.service"])
            print_message("Service enabled", NordColors.GREEN, "✓")
            progress.advance(task)
            progress.update(task, description="Starting service")
            run_command(["systemctl", "start", "virtualization_setup.service"])
            print_message("Service started", NordColors.GREEN, "✓")
            progress.advance(task)
        return TaskResult(
            name="systemd_service",
            success=True,
            message="Service installed, enabled, and started successfully",
        )
    except Exception as e:
        print_message(f"Failed to install and enable service: {e}", NordColors.RED, "✗")
        return TaskResult(
            name="systemd_service", success=False, message=f"Service error: {e}"
        )


# ----------------------------------------------------------------
# Main Execution Flow
# ----------------------------------------------------------------
def main() -> None:
    console.clear()
    # Check OS is Fedora
    if not check_os():
        display_panel(
            "This script is designed to run on Fedora. Exiting.",
            NordColors.RED,
            "OS Error",
        )
        sys.exit(1)

    # Display header and status
    console.print(create_header())
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Hostname: {AppConfig.HOSTNAME}[/] | "
            f"[{NordColors.SNOW_STORM_1}]Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]"
        )
    )
    console.print()

    # Ensure script is run as root
    if os.geteuid() != 0:
        display_panel(
            "This script must be run as root (e.g., using sudo)",
            NordColors.RED,
            "Permission Error",
        )
        sys.exit(1)

    # Overview Panel (no user input required)
    display_panel(
        "This utility will automatically set up a complete virtualization environment on Fedora.\n"
        "It will install packages, configure networks, fix permissions, and start VMs.\n"
        "The process runs unattended and may take several minutes.",
        NordColors.FROST_2,
        "Setup Overview",
    )
    console.print()

    results: List[TaskResult] = []
    results.append(update_system_packages())
    results.append(install_virtualization_packages(AppConfig.VIRTUALIZATION_PACKAGES))
    results.append(manage_virtualization_services(AppConfig.VIRTUALIZATION_SERVICES))
    results.append(install_and_enable_service())

    net_result: Optional[TaskResult] = None
    for attempt in range(1, 4):
        print_message(f"Network configuration attempt {attempt}", NordColors.FROST_3)
        net_result = configure_default_network()
        if net_result.success:
            break
        time.sleep(2)
    if not (net_result and net_result.success):
        print_message(
            "Failed to configure network after multiple attempts", NordColors.RED, "✗"
        )
        net_result = recreate_default_network()
    results.append(net_result)

    results.append(fix_storage_permissions(AppConfig.VM_STORAGE_PATHS))
    results.append(configure_user_groups())

    vms = get_virtual_machines()
    if vms:
        print_message(f"Found {len(vms)} virtual machine(s)", NordColors.GREEN, "✓")
        results.append(set_vm_autostart(vms))
        results.append(start_virtual_machines(vms))
    else:
        print_message("No virtual machines found", NordColors.FROST_3)
        results.append(
            TaskResult(name="vm_autostart", success=True, message="No VMs found")
        )
        results.append(
            TaskResult(name="vm_start", success=True, message="No VMs found")
        )

    results.append(verify_virtualization_setup())
    console.print()

    # Display summary table
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]Setup Summary[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )
    table.add_column("Task", style=f"bold {NordColors.FROST_4}")
    table.add_column("Status", justify="center")
    table.add_column("Message", style=f"{NordColors.SNOW_STORM_1}")
    for res in results:
        status = (
            Text("✓ Success", style=f"bold {NordColors.GREEN}")
            if res.success
            else Text("✗ Failed", style=f"bold {NordColors.RED}")
        )
        table.add_row(res.name.replace("_", " ").title(), status, res.message)
    console.print(
        Panel(table, border_style=Style(color=NordColors.FROST_4), padding=(0, 1))
    )

    success_count = sum(1 for res in results if res.success)
    total_tasks = len(results)
    if success_count == total_tasks:
        display_panel(
            "Virtualization environment setup completed successfully!\n\n"
            "Next steps:\n"
            "• Log out and log back in for group changes to take effect\n"
            "• Use 'virt-manager' to manage VMs\n"
            "• Check logs with 'journalctl -u libvirtd'\n"
            "• The systemd service is installed to maintain configuration",
            NordColors.GREEN,
            "Setup Complete",
        )
    else:
        display_panel(
            f"Setup completed with {total_tasks - success_count} issue(s).\n"
            "Review the warnings and errors above for details.\n"
            "Manual intervention may be required.",
            NordColors.YELLOW,
            "Setup Complete with Issues",
        )
    wait_for_key()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        display_panel("Setup interrupted by user", NordColors.YELLOW, "Cancelled")
        sys.exit(130)
    except Exception as e:
        display_panel(f"Unhandled error: {e}", NordColors.RED, "Error")
        console.print_exception()
        sys.exit(1)
