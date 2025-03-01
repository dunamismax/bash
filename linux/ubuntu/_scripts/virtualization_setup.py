#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup Script

This utility sets up a virtualization environment on Ubuntu. It:
  • Updates package lists and installs virtualization packages
  • Manages virtualization services
  • Configures and recreates the default NAT network
  • Fixes storage permissions and user group settings
  • Updates VM network settings, autostart, and starts VMs
  • Verifies the overall setup

Note: Run this script with root privileges.
"""

import atexit
import os
import pwd
import grp
import signal
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.spinner import Spinner
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
HOSTNAME = socket.gethostname()
OPERATION_TIMEOUT = 600  # seconds

VM_STORAGE_PATHS = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]
VIRTUALIZATION_PACKAGES = [
    "qemu-kvm",
    "qemu-utils",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virt-manager",
    "bridge-utils",
    "cpu-checker",
    "ovmf",
    "virtinst",
    "libguestfs-tools",
    "virt-top",
]
VIRTUALIZATION_SERVICES = ["libvirtd", "virtlogd"]

VM_OWNER = "root"
VM_GROUP = "libvirt-qemu"
VM_DIR_MODE = 0o2770
VM_FILE_MODE = 0o0660
LIBVIRT_USER_GROUP = "libvirt"

DEFAULT_NETWORK_XML = """<network>
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

# ------------------------------
# Nord-Themed Styles & Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")


def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #5E81AC]⚠ {text}[/bold #5E81AC]")


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")


# ------------------------------
# Command Execution Helper
# ------------------------------
def run_command(cmd, env=None, check=True, capture_output=True, timeout=None):
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
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def signal_handler(sig, frame):
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)


def cleanup():
    print_step("Performing cleanup tasks...")
    # Add any necessary cleanup steps here.


# ------------------------------
# Core Functions
# ------------------------------
def update_system_packages() -> bool:
    print_section("Updating Package Lists")
    try:
        with console.status("[bold #81A1C1]Updating package lists...", spinner="dots"):
            run_command(["apt-get", "update"])
        print_success("Package lists updated")
        return True
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False


def install_virtualization_packages(packages) -> bool:
    print_section("Installing Virtualization Packages")
    if not packages:
        print_warning("No packages specified")
        return True
    total = len(packages)
    print_step(f"Installing {total} packages: {', '.join(packages)}")
    failed = []
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Installing packages", total=total)
        for pkg in packages:
            print_step(f"Installing: {pkg}")
            try:
                proc = subprocess.Popen(
                    ["apt-get", "install", "-y", pkg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in iter(proc.stdout.readline, ""):
                    if "Unpacking" in line or "Setting up" in line:
                        console.print("  " + line.strip(), style="#D8DEE9")
                proc.wait()
                if proc.returncode != 0:
                    print_error(f"Failed to install {pkg}")
                    failed.append(pkg)
                else:
                    print_success(f"{pkg} installed")
            except Exception as e:
                print_error(f"Error installing {pkg}: {e}")
                failed.append(pkg)
            progress.advance(task)
    if failed:
        print_warning(f"Failed to install: {', '.join(failed)}")
        return False
    print_success("All packages installed")
    return True


def manage_virtualization_services(services) -> bool:
    print_section("Managing Virtualization Services")
    if not services:
        print_warning("No services specified")
        return True
    total = len(services) * 2
    failed = []
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Managing services", total=total)
        for svc in services:
            for action, cmd in [
                ("enable", ["systemctl", "enable", svc]),
                ("start", ["systemctl", "start", svc]),
            ]:
                print_step(f"{action.capitalize()} service: {svc}")
                try:
                    run_command(cmd)
                    print_success(f"{svc} {action}d")
                except Exception as e:
                    print_error(f"Failed to {action} {svc}: {e}")
                    failed.append(f"{svc} ({action})")
                progress.advance(task)
    if failed:
        print_warning(f"Issues with: {', '.join(failed)}")
        return False
    print_success("Services managed successfully")
    return True


def recreate_default_network() -> bool:
    print_section("Recreating Default Network")
    try:
        result = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "default" in result.stdout:
            print_step("Removing existing default network")
            run_command(["virsh", "net-destroy", "default"], check=False)
            autostart_path = Path("/etc/libvirt/qemu/networks/autostart/default.xml")
            if autostart_path.exists() or autostart_path.is_symlink():
                autostart_path.unlink()
            run_command(["virsh", "net-undefine", "default"], check=False)
        net_xml_path = Path("/tmp/default_network.xml")
        net_xml_path.write_text(DEFAULT_NETWORK_XML)
        print_step("Defining new default network")
        run_command(["virsh", "net-define", str(net_xml_path)])
        run_command(["virsh", "net-start", "default"])
        run_command(["virsh", "net-autostart", "default"])
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        if "default" in net_list.stdout and "active" in net_list.stdout:
            print_success("Default network is active")
            return True
        print_error("Default network not running")
        return False
    except Exception as e:
        print_error(f"Error recreating network: {e}")
        return False


def configure_default_network() -> bool:
    print_section("Configuring Default Network")
    try:
        net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)
        if "default" in net_list.stdout:
            print_step("Default network exists")
            if "active" not in net_list.stdout:
                print_step("Starting default network")
                try:
                    run_command(["virsh", "net-start", "default"])
                    print_success("Default network started")
                except Exception as e:
                    print_error(f"Start failed: {e}")
                    return recreate_default_network()
        else:
            print_step("Default network missing, creating it")
            return recreate_default_network()
        try:
            net_info = run_command(
                ["virsh", "net-info", "default"], capture_output=True
            )
            if "Autostart:      yes" not in net_info.stdout:
                print_step("Setting autostart")
                autostart_path = Path(
                    "/etc/libvirt/qemu/networks/autostart/default.xml"
                )
                if autostart_path.exists() or autostart_path.is_symlink():
                    autostart_path.unlink()
                run_command(["virsh", "net-autostart", "default"])
                print_success("Autostart enabled")
            else:
                print_success("Autostart already enabled")
        except Exception as e:
            print_warning(f"Autostart not set: {e}")
        return True
    except Exception as e:
        print_error(f"Network configuration error: {e}")
        return False


def get_virtual_machines():
    vms = []
    try:
        result = run_command(["virsh", "list", "--all"], capture_output=True)
        lines = result.stdout.strip().splitlines()
        sep = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("----")), -1
        )
        if sep < 0:
            return []
        for line in lines[sep + 1 :]:
            parts = line.split()
            if len(parts) >= 3:
                vms.append(
                    {"id": parts[0], "name": parts[1], "state": " ".join(parts[2:])}
                )
        return vms
    except Exception as e:
        print_error(f"Error retrieving VMs: {e}")
        return []


def set_vm_autostart(vms) -> bool:
    print_section("Configuring VM Autostart")
    if not vms:
        print_warning("No VMs found")
        return True
    failed = []
    with Progress(
        SpinnerColumn(style="bold #81A1C1"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="bold #88C0D0"),
        console=console,
    ) as progress:
        task = progress.add_task("Setting VM autostart", total=len(vms))
        for vm in vms:
            name = vm["name"]
            try:
                print_step(f"Setting autostart for {name}")
                info = run_command(["virsh", "dominfo", name], capture_output=True)
                if "Autostart:        yes" in info.stdout:
                    print_success(f"{name} already set")
                else:
                    run_command(["virsh", "autostart", name])
                    print_success(f"{name} set to autostart")
            except Exception as e:
                print_error(f"Autostart failed for {name}: {e}")
                failed.append(name)
            progress.advance(task)
    if failed:
        print_warning(f"Autostart failed for: {', '.join(failed)}")
        return False
    return True


def start_virtual_machines(vms) -> bool:
    print_section("Starting Virtual Machines")
    if not vms:
        print_warning("No VMs found")
        return True
    to_start = [vm for vm in vms if vm["state"].lower() != "running"]
    if not to_start:
        print_success("All VMs are running")
        return True
    if not ensure_network_active_before_vm_start():
        print_error("Default network not active")
        return False
    failed = []
    for vm in to_start:
        name = vm["name"]
        print_step(f"Starting {name}")
        attempt = 0
        success = False
        while attempt < 3 and not success:
            attempt += 1
            print_step(f"Attempt {attempt} for {name}")
            try:
                with console.status(
                    f"[bold #81A1C1]Starting {name}...", spinner="dots"
                ):
                    result = run_command(["virsh", "start", name], check=False)
                if result.returncode == 0:
                    print_success(f"{name} started")
                    success = True
                else:
                    if "Only one live display may be active at once" in (
                        result.stderr or ""
                    ):
                        print_warning(
                            f"{name} failed to start due to active live display. Waiting before retrying..."
                        )
                        time.sleep(5)
                    else:
                        print_error(f"Failed to start {name}: {result.stderr}")
                        break
            except Exception as e:
                print_error(f"Error starting {name}: {e}")
                break
        if not success:
            failed.append(name)
        time.sleep(5)
    if failed:
        print_warning(f"Failed to start: {', '.join(failed)}")
        return False
    return True


def ensure_network_active_before_vm_start() -> bool:
    print_step("Verifying default network before starting VMs")
    try:
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        for line in net_list.stdout.splitlines():
            if "default" in line and "active" in line:
                print_success("Default network is active")
                return True
        print_warning("Default network inactive; attempting restart")
        return recreate_default_network()
    except Exception as e:
        print_error(f"Network verification error: {e}")
        return False


def fix_storage_permissions(paths) -> bool:
    print_section("Fixing VM Storage Permissions")
    if not paths:
        print_warning("No storage paths specified")
        return True
    try:
        uid = pwd.getpwnam(VM_OWNER).pw_uid
        gid = grp.getgrnam(VM_GROUP).gr_gid
    except KeyError as e:
        print_error(f"User/group not found: {e}")
        return False

    for path_str in paths:
        path = Path(path_str)
        print_step(f"Processing {path}")
        if not path.exists():
            print_warning(f"{path} does not exist; creating")
            path.mkdir(mode=VM_DIR_MODE, parents=True, exist_ok=True)
        total_items = sum(
            1 + len(dirs) + len(files) for _, dirs, files in os.walk(str(path))
        )
        with Progress(
            SpinnerColumn(style="bold #81A1C1"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="bold #88C0D0"),
            console=console,
        ) as progress:
            task = progress.add_task("Updating permissions", total=total_items)
            try:
                os.chown(str(path), uid, gid)
                os.chmod(str(path), VM_DIR_MODE)
                progress.advance(task)
                for root, dirs, files in os.walk(str(path)):
                    for d in dirs:
                        dpath = Path(root) / d
                        try:
                            os.chown(str(dpath), uid, gid)
                            os.chmod(str(dpath), VM_DIR_MODE)
                        except Exception as e:
                            print_warning(f"Error on {dpath}: {e}")
                        progress.advance(task)
                    for f in files:
                        fpath = Path(root) / f
                        try:
                            os.chown(str(fpath), uid, gid)
                            os.chmod(str(fpath), VM_FILE_MODE)
                        except Exception as e:
                            print_warning(f"Error on {fpath}: {e}")
                        progress.advance(task)
            except Exception as e:
                print_error(f"Failed on {path}: {e}")
                return False
    print_success("Storage permissions updated")
    return True


def configure_user_groups() -> bool:
    print_section("Configuring User Group Membership")
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print_warning("SUDO_USER not set; skipping group config")
        return True
    try:
        pwd.getpwnam(sudo_user)
        grp.getgrnam(LIBVIRT_USER_GROUP)
    except KeyError as e:
        print_error(f"User or group error: {e}")
        return False
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary = grp.getgrgid(pwd.getpwnam(sudo_user).pw_gid).gr_name
    if primary not in user_groups:
        user_groups.append(primary)
    if LIBVIRT_USER_GROUP in user_groups:
        print_success(f"{sudo_user} already in {LIBVIRT_USER_GROUP}")
        return True
    try:
        print_step(f"Adding {sudo_user} to {LIBVIRT_USER_GROUP}")
        run_command(["usermod", "-a", "-G", LIBVIRT_USER_GROUP, sudo_user])
        print_success(
            f"User {sudo_user} added to {LIBVIRT_USER_GROUP}. Please log out/in."
        )
        return True
    except Exception as e:
        print_error(f"Failed to add user: {e}")
        return False


def verify_virtualization_setup() -> bool:
    print_section("Verifying Virtualization Setup")
    passed = True
    try:
        svc = run_command(["systemctl", "is-active", "libvirtd"], check=False)
        if svc.stdout.strip() == "active":
            print_success("libvirtd is active")
        else:
            print_error("libvirtd is not active")
            passed = False
    except Exception as e:
        print_error(f"Error checking libvirtd: {e}")
        passed = False

    try:
        net = run_command(["virsh", "net-list"], capture_output=True, check=False)
        if "default" in net.stdout and "active" in net.stdout:
            print_success("Default network is active")
        else:
            print_error("Default network inactive")
            passed = False
    except Exception as e:
        print_error(f"Network check error: {e}")
        passed = False

    try:
        lsmod = run_command(["lsmod"], capture_output=True)
        if "kvm" in lsmod.stdout:
            print_success("KVM modules loaded")
        else:
            print_error("KVM modules missing")
            passed = False
    except Exception as e:
        print_error(f"KVM check error: {e}")
        passed = False

    for path_str in VM_STORAGE_PATHS:
        path = Path(path_str)
        if path.exists():
            print_success(f"Storage exists: {path}")
        else:
            print_error(f"Storage missing: {path}")
            try:
                path.mkdir(mode=VM_DIR_MODE, parents=True, exist_ok=True)
                print_success(f"Created storage: {path}")
            except Exception as e:
                print_error(f"Failed to create {path}: {e}")
                passed = False
    if passed:
        print_success("All verification checks passed!")
    else:
        print_warning("Some verification checks failed.")
    return passed


def install_and_enable_service() -> bool:
    """
    Installs the virtualization_setup.service systemd unit file,
    reloads the systemd daemon, enables the service, and starts it.
    """
    service_path = Path("/etc/systemd/system/virtualization_setup.service")
    service_content = """[Unit]
Description=Virtualization Setup Service
After=network.target

[Service]
Type=simple
ExecStart=/home/sawyer/.pyenv/versions/3.13.2/bin/python /home/sawyer/bin/virtualization_setup.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
    try:
        print_section("Installing systemd service")
        # Write the service file
        service_path.write_text(service_content)
        print_success(f"Service file installed to {service_path}")

        # Reload systemd to pick up the new service file
        run_command(["systemctl", "daemon-reload"])
        print_success("Systemd daemon reloaded")

        # Enable the service to start on boot
        run_command(["systemctl", "enable", "virtualization_setup.service"])
        print_success("Service enabled")

        # Optionally, start the service immediately
        run_command(["systemctl", "start", "virtualization_setup.service"])
        print_success("Service started")
        return True
    except Exception as e:
        print_error(f"Failed to install and enable systemd service: {e}")
        return False


# ------------------------------
# Main Execution Flow (Non-Interactive)
# ------------------------------
def main() -> None:
    # Setup signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_header("Enhanced Virt Setup")
    console.print(f"Hostname: [bold #D8DEE9]{HOSTNAME}[/bold #D8DEE9]")
    console.print(
        f"Timestamp: [bold #D8DEE9]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]"
    )

    if os.geteuid() != 0:
        print_error("Run this script as root (e.g., using sudo)")
        sys.exit(1)

    # Execute tasks sequentially
    if not update_system_packages():
        print_warning("Package list update failed")

    if not install_virtualization_packages(VIRTUALIZATION_PACKAGES):
        print_error("Package installation issues encountered")

    if not manage_virtualization_services(VIRTUALIZATION_SERVICES):
        print_warning("Service management issues encountered")

    if not install_and_enable_service():
        print_warning("Failed to install or enable the virtualization_setup service")

    for attempt in range(1, 4):
        print_step(f"Network configuration attempt {attempt}")
        if configure_default_network():
            break
        time.sleep(2)
    else:
        print_error("Failed to configure network after multiple attempts")
        recreate_default_network()

    fix_storage_permissions(VM_STORAGE_PATHS)
    configure_user_groups()

    vms = get_virtual_machines()
    if vms:
        print_success(f"Found {len(vms)} VMs")
        set_vm_autostart(vms)
        ensure_network_active_before_vm_start()
        start_virtual_machines(vms)
    else:
        print_step("No VMs found")

    verify_virtualization_setup()

    print_header("Setup Complete")
    print_success("Virtualization environment setup complete!")
    print_step(
        "Next steps: log out/in for group changes, run 'virt-manager', and check logs with 'journalctl -u libvirtd'."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Setup interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
