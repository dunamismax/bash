#!/usr/bin/env python3
"""
SFTP Toolkit
--------------------------------------------------
A fully interactive, menu-driven SFTP toolkit that allows you to perform
all the most important SFTP file transfer operations. Enjoy a beautiful
and robust CLI experience powered by Rich and Pyfiglet.

Features:
  • Fully interactive, menu-driven CLI with Rich styling
  • Stylish ASCII banner using Pyfiglet at startup
  • SFTP operations: connect, list directory, upload, download, delete,
    rename, create and delete remote directories
  • Predefined device lists (Tailscale and local) for quick connection setup
  • Progress tracking with Rich spinners and progress bars during transfers
  • Clean, optimized, and well-documented code for maintainability
"""

import os
import sys
import time
import socket
import getpass
from dataclasses import dataclass
from typing import List

import paramiko
import pyfiglet
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeRemainingColumn,
    DownloadColumn,
)

# ----------------------------------------------------------------
# Global Variables and Console Initialization
# ----------------------------------------------------------------
console = Console()

# Global variables to hold the SFTP connection objects
sftp = None
transport = None


# ----------------------------------------------------------------
# Helper Functions for User & SSH Key Handling
# ----------------------------------------------------------------
def get_default_username() -> str:
    """
    Return the default username.
    If the script is run with sudo, return the original user's username;
    otherwise, use getpass.getuser().
    """
    return os.getenv("SUDO_USER") or getpass.getuser()


def load_private_key():
    """
    Attempt to load the default SSH private key from ~/.ssh/id_rsa.
    If the key is encrypted, prompt the user for the passphrase.
    """
    key_path = os.path.expanduser("~/.ssh/id_rsa")
    try:
        key = paramiko.RSAKey.from_private_key_file(key_path)
        return key
    except paramiko.PasswordRequiredException:
        passphrase = Prompt.ask(
            "[bold purple]Enter passphrase for SSH key[/]", password=True
        )
        try:
            key = paramiko.RSAKey.from_private_key_file(key_path, password=passphrase)
            return key
        except Exception as e:
            console.print(
                f"[bold red]Error loading private key with passphrase: {e}[/]"
            )
            return None
    except Exception as e:
        console.print(f"[bold red]Error loading private key: {e}[/]")
        return None


# ----------------------------------------------------------------
# Device Data Structures and Functions
# ----------------------------------------------------------------
@dataclass
class Device:
    name: str
    ip_address: str
    description: str


def load_tailscale_devices() -> List[Device]:
    return [
        Device(
            name="ubuntu-server",
            ip_address="100.109.43.88",
            description="Primary Ubuntu Server",
        ),
        Device(
            name="ubuntu-lenovo",
            ip_address="100.66.213.7",
            description="Development Laptop",
        ),
        Device(
            name="raspberrypi-5",
            ip_address="100.105.117.18",
            description="Raspberry Pi 5",
        ),
        Device(
            name="raspberrypi-3",
            ip_address="100.116.191.42",
            description="Raspberry Pi 3",
        ),
        Device(
            name="ubuntu-server-vm-01",
            ip_address="100.84.119.114",
            description="Ubuntu VM 1",
        ),
        Device(
            name="ubuntu-server-vm-02",
            ip_address="100.122.237.56",
            description="Ubuntu VM 2",
        ),
        Device(
            name="ubuntu-server-vm-03",
            ip_address="100.97.229.120",
            description="Ubuntu VM 3",
        ),
        Device(
            name="ubuntu-server-vm-04",
            ip_address="100.73.171.7",
            description="Ubuntu VM 4",
        ),
        Device(
            name="ubuntu-lenovo-vm-01",
            ip_address="100.107.79.81",
            description="Lenovo VM 1",
        ),
        Device(
            name="ubuntu-lenovo-vm-02",
            ip_address="100.78.101.2",
            description="Lenovo VM 2",
        ),
        Device(
            name="ubuntu-lenovo-vm-03",
            ip_address="100.95.115.62",
            description="Lenovo VM 3",
        ),
        Device(
            name="ubuntu-lenovo-vm-04",
            ip_address="100.92.31.94",
            description="Lenovo VM 4",
        ),
    ]


def load_local_devices() -> List[Device]:
    return [
        Device(
            name="ubuntu-server",
            ip_address="192.168.0.73",
            description="Primary Server (LAN)",
        ),
        Device(
            name="ubuntu-lenovo",
            ip_address="192.168.0.31",
            description="Development Laptop (LAN)",
        ),
        Device(
            name="raspberrypi-5",
            ip_address="192.168.0.40",
            description="Raspberry Pi 5 (LAN)",
        ),
        Device(
            name="raspberrypi-3",
            ip_address="192.168.0.100",
            description="Raspberry Pi 3 (LAN)",
        ),
    ]


def select_device_menu() -> Device:
    """
    Display a device selection menu allowing the user to choose
    from Tailscale or local devices.
    """
    console.print(Panel("[bold cyan]Select Device Type[/]", expand=False))
    device_type = Prompt.ask(
        "[bold purple]Choose device type[/]",
        choices=["tailscale", "local"],
        default="tailscale",
    )
    devices = (
        load_tailscale_devices() if device_type == "tailscale" else load_local_devices()
    )

    table = Table(
        title=f"Available {device_type.capitalize()} Devices",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("No.", style="bold", width=4)
    table.add_column("Name", style="bold")
    table.add_column("IP Address", style="bold green")
    table.add_column("Description", style="italic")

    for idx, device in enumerate(devices, start=1):
        table.add_row(str(idx), device.name, device.ip_address, device.description)
    console.print(table)

    choice = IntPrompt.ask(
        "[bold purple]Select device number[/]",
        choices=[str(i) for i in range(1, len(devices) + 1)],
    )
    selected_device = devices[choice - 1]
    console.print(
        f"[bold green]Selected device:[/] {selected_device.name} ({selected_device.ip_address})"
    )
    return selected_device


# ----------------------------------------------------------------
# Application Configuration
# ----------------------------------------------------------------
class AppConfig:
    """Application configuration and constants."""

    SFTP_DEFAULT_PORT = 22


# ----------------------------------------------------------------
# Helper Functions for SFTP Operations
# ----------------------------------------------------------------
def connect_sftp():
    """
    Establish an SFTP connection using key-based authentication.
    Prompts for hostname, port, and username (defaulting to the current user).
    """
    global sftp, transport
    console.print(Panel("[bold cyan]SFTP Connection Setup[/]", expand=False))
    hostname = Prompt.ask("[bold purple]Enter SFTP Hostname[/]")
    port = IntPrompt.ask(
        "[bold purple]Enter Port[/]", default=AppConfig.SFTP_DEFAULT_PORT
    )
    username = Prompt.ask(
        "[bold purple]Enter Username[/]", default=get_default_username()
    )

    key = load_private_key()
    if key is None:
        console.print(
            "[bold red]Could not load SSH private key. Connection aborted.[/]"
        )
        return

    try:
        transport = paramiko.Transport((hostname, port))
        transport.connect(username=username, pkey=key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        console.print(
            "[bold green]Successfully connected to SFTP server using key-based authentication.[/]"
        )
    except Exception as e:
        console.print(f"[bold red]Error connecting to SFTP server: {e}[/]")
        sftp = None
        transport = None


def connect_sftp_device(device: Device):
    """
    Establish an SFTP connection using a predefined device.
    The device's IP address is used as the hostname and key-based authentication is used.
    """
    global sftp, transport
    console.print(
        Panel(
            f"[bold cyan]Connecting to {device.name} ({device.ip_address})[/]",
            expand=False,
        )
    )
    port = IntPrompt.ask(
        "[bold purple]Enter Port[/]", default=AppConfig.SFTP_DEFAULT_PORT
    )
    username = Prompt.ask(
        "[bold purple]Enter Username[/]", default=get_default_username()
    )

    key = load_private_key()
    if key is None:
        console.print(
            "[bold red]Could not load SSH private key. Connection aborted.[/]"
        )
        return

    try:
        transport = paramiko.Transport((device.ip_address, port))
        transport.connect(username=username, pkey=key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        console.print(
            f"[bold green]Successfully connected to {device.name} using key-based authentication.[/]"
        )
    except Exception as e:
        console.print(f"[bold red]Error connecting to {device.name}: {e}[/]")
        sftp = None
        transport = None


def disconnect_sftp():
    """Close the SFTP and transport connections if they exist."""
    global sftp, transport
    if sftp:
        sftp.close()
        sftp = None
    if transport:
        transport.close()
        transport = None
    console.print("[bold yellow]Disconnected from SFTP server.[/]")


def list_remote_directory():
    """List the contents of a remote directory."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    remote_path = Prompt.ask("[bold purple]Enter remote directory path[/]", default=".")
    try:
        file_list = sftp.listdir_attr(remote_path)
        table = Table(
            title=f"Contents of {remote_path}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Name", style="bold")
        table.add_column("Size", justify="right")
        table.add_column("Modified Time")
        for item in file_list:
            mod_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.st_mtime))
            table.add_row(item.filename, f"{item.st_size} bytes", mod_time)
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Failed to list directory: {e}[/]")


def upload_file():
    """Upload a local file to the remote SFTP server with progress tracking."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    local_path = Prompt.ask("[bold purple]Enter the local file path to upload[/]")
    if not os.path.isfile(local_path):
        console.print("[bold red]Local file does not exist.[/]")
        return

    remote_path = Prompt.ask("[bold purple]Enter the remote destination path[/]")
    file_size = os.path.getsize(local_path)

    def progress_callback(transferred, total):
        progress.update(task, completed=transferred)

    try:
        with Progress(
            SpinnerColumn("dots", style="bold cyan"),
            TextColumn("[bold green]Uploading..."),
            BarColumn(),
            DownloadColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("upload", total=file_size)
            sftp.put(local_path, remote_path, callback=progress_callback)
        console.print(f"[bold green]Upload completed: {local_path} -> {remote_path}[/]")
    except Exception as e:
        console.print(f"[bold red]Upload failed: {e}[/]")


def download_file():
    """Download a remote file from the SFTP server with progress tracking."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    remote_path = Prompt.ask("[bold purple]Enter the remote file path to download[/]")
    local_path = Prompt.ask(
        "[bold purple]Enter the local destination directory[/]", default=os.getcwd()
    )

    try:
        file_size = sftp.stat(remote_path).st_size
    except Exception as e:
        console.print(f"[bold red]Could not retrieve file size: {e}[/]")
        return

    def progress_callback(transferred, total):
        progress.update(task, completed=transferred)

    try:
        with Progress(
            SpinnerColumn("dots", style="bold cyan"),
            TextColumn("[bold green]Downloading..."),
            BarColumn(),
            DownloadColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("download", total=file_size)
            sftp.get(
                remote_path,
                os.path.join(local_path, os.path.basename(remote_path)),
                callback=progress_callback,
            )
        console.print(
            f"[bold green]Download completed: {remote_path} -> {local_path}[/]"
        )
    except Exception as e:
        console.print(f"[bold red]Download failed: {e}[/]")


def delete_remote_file():
    """Delete a remote file from the SFTP server."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    remote_path = Prompt.ask("[bold purple]Enter the remote file path to delete[/]")
    if Confirm.ask(
        "[bold yellow]Are you sure you want to delete this file?[/]", default=False
    ):
        try:
            sftp.remove(remote_path)
            console.print(f"[bold green]Deleted remote file: {remote_path}[/]")
        except Exception as e:
            console.print(f"[bold red]Failed to delete file: {e}[/]")


def rename_remote_file():
    """Rename a remote file on the SFTP server."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    old_name = Prompt.ask("[bold purple]Enter the current remote file path[/]")
    new_name = Prompt.ask("[bold purple]Enter the new remote file name/path[/]")
    try:
        sftp.rename(old_name, new_name)
        console.print(f"[bold green]Renamed remote file to: {new_name}[/]")
    except Exception as e:
        console.print(f"[bold red]Failed to rename file: {e}[/]")


def create_remote_directory():
    """Create a new directory on the SFTP server."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    remote_dir = Prompt.ask("[bold purple]Enter the remote directory to create[/]")
    try:
        sftp.mkdir(remote_dir)
        console.print(f"[bold green]Created remote directory: {remote_dir}[/]")
    except Exception as e:
        console.print(f"[bold red]Failed to create directory: {e}[/]")


def delete_remote_directory():
    """Delete a directory on the SFTP server."""
    if not sftp:
        console.print("[bold red]Not connected. Please connect first.[/]")
        return

    remote_dir = Prompt.ask("[bold purple]Enter the remote directory to delete[/]")
    if Confirm.ask(
        "[bold yellow]Are you sure you want to delete this directory?[/]", default=False
    ):
        try:
            sftp.rmdir(remote_dir)
            console.print(f"[bold green]Deleted remote directory: {remote_dir}[/]")
        except Exception as e:
            console.print(f"[bold red]Failed to delete directory: {e}[/]")


# ----------------------------------------------------------------
# Menu and UI Functions
# ----------------------------------------------------------------
def display_banner():
    """Display an ASCII art banner using Pyfiglet."""
    fonts = ["slant", "big", "digital"]
    ascii_banner = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font)
            ascii_banner = fig.renderText("SFTP Toolkit")
            if ascii_banner.strip():
                break
        except Exception:
            continue
    banner_panel = Panel(ascii_banner, style="bold cyan", border_style="cyan")
    console.print(banner_panel)


def main_menu():
    """
    Display the interactive menu for the SFTP Toolkit.
    Loops until the user chooses to exit.
    """
    while True:
        console.print("\n[bold magenta]SFTP Toolkit Menu[/]")
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Option", style="bold", width=4)
        table.add_column("Description", style="bold")
        table.add_row("1", "Connect to SFTP Server (manual)")
        table.add_row("2", "Connect to SFTP Server (select device)")
        table.add_row("3", "List Remote Directory")
        table.add_row("4", "Upload File")
        table.add_row("5", "Download File")
        table.add_row("6", "Delete Remote File")
        table.add_row("7", "Rename Remote File")
        table.add_row("8", "Create Remote Directory")
        table.add_row("9", "Delete Remote Directory")
        table.add_row("A", "Disconnect from SFTP Server")
        table.add_row("0", "Exit")
        console.print(table)

        choice = Prompt.ask(
            "[bold purple]Enter your choice[/]",
            choices=[str(i) for i in list(range(1, 10))] + ["A", "0"],
            default="0",
        )

        if choice == "1":
            connect_sftp()
        elif choice == "2":
            device = select_device_menu()
            connect_sftp_device(device)
        elif choice == "3":
            list_remote_directory()
        elif choice == "4":
            upload_file()
        elif choice == "5":
            download_file()
        elif choice == "6":
            rename_remote_file()
        elif choice == "7":
            create_remote_directory()
        elif choice == "8":
            delete_remote_directory()
        elif choice == "9":
            delete_remote_file()
        elif choice.upper() == "A":
            disconnect_sftp()
        elif choice == "0":
            if sftp:
                disconnect_sftp()
            console.print("[bold yellow]Exiting SFTP Toolkit. Goodbye![/]")
            sys.exit(0)
        else:
            console.print("[bold red]Invalid selection, please try again.[/]")
        # Brief pause before re-displaying the menu
        time.sleep(1)


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main():
    """Main function: display banner and launch the interactive menu."""
    console.clear()
    display_banner()
    main_menu()


if __name__ == "__main__":
    main()
