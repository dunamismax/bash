#!/usr/bin/env python3
"""
SSH Management Tool
-------------------

An advanced, production-grade terminal application for managing SSH keys and permissions
on the main Ubuntu server. This script offers a Nord-themed, interactive menu system with:

  1. A professional UI and dynamic ASCII banners via Pyfiglet
  2. Rich library integration for panels, tables, spinners, and real-time progress
  3. Fully interactive, menu-driven interface with numbered options and validation
  4. Comprehensive error handling with color-coded messages and recovery mechanisms
  5. Signal handling for graceful termination (SIGINT, SIGTERM)
  6. Type annotations & dataclasses for readability
  7. Modular architecture with well-documented sections

Core Features:
  • Create a new SSH key on this main server
  • Push the key to one or more client machines
  • Fix permissions on the ~/.ssh folder
  • Exit gracefully

Usage:
  Simply run:
      ./ssh_manager.py
"""

import os
import sys
import pwd
import signal
import subprocess
import getpass
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box
from pyfiglet import Figlet


# ------------------------------
# 1. Nord-Themed Rich Console
# ------------------------------
nord_theme = Theme(
    {
        "info": "#88C0D0",
        "warning": "#EBCB8B",
        "danger": "#BF616A",
        "success": "#A3BE8C",
        "primary": "#5E81AC",
        "banner": "#81A1C1",
    }
)
console = Console(theme=nord_theme)


# ------------------------------------
# 2. Dataclass for Script Parameters
# ------------------------------------
@dataclass
class SSHManagerConfig:
    user: str
    home_dir: str = field(init=False)
    ssh_dir: str = field(init=False)
    key_path: str = field(init=False)

    def __post_init__(self) -> None:
        """Set derived attributes after initialization."""
        self.home_dir = f"/home/{self.user}"
        self.ssh_dir = os.path.join(self.home_dir, ".ssh")
        # By default, use id_rsa for the new key path
        self.key_path = os.path.join(self.ssh_dir, "id_rsa")


# ------------------------------
# 3. Signal Handling
# ------------------------------
def handle_signal(signum: int, frame) -> None:
    """
    Graceful signal handler for SIGINT and SIGTERM.
    """
    console.print(
        f"[bold red]\nReceived signal {signum}. Exiting gracefully...[/bold red]"
    )
    sys.exit(0)


# Register the signal handlers
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ------------------------------
# 4. Utility / Helper Functions
# ------------------------------
def print_banner() -> None:
    """
    Print a dynamic ASCII banner using Pyfiglet, styled with Nord-like colors.
    """
    fig = Figlet(font="slant")
    banner_text = fig.renderText("SSH Manager")
    # Simple approach: color the entire banner with a Nord color
    console.print(Text(banner_text, style="banner"))


def get_user_ids(user: str) -> Optional[Tuple[int, int]]:
    """
    Retrieve the UID and GID for the specified user.
    """
    try:
        pw_record = pwd.getpwnam(user)
        return pw_record.pw_uid, pw_record.pw_gid
    except KeyError:
        console.print(f"[bold red]User '{user}' not found.[/bold red]")
        return None


def remove_acl(path: str) -> None:
    """
    Remove any extended ACL entries from the given file or directory.
    """
    try:
        subprocess.run(["setfacl", "-b", path], check=True)
        console.print(f"[success]Removed ACL from: {path}[/success]")
    except subprocess.CalledProcessError as e:
        console.print(f"[danger]Error removing ACL for {path}: {e}[/danger]")


def set_permissions_recursive(ssh_dir: str, uid: int, gid: int) -> None:
    """
    Recursively set the correct permissions for the .ssh directory and its contents.

    Directories are set to 0700.
    Files ending with '.pub' are set to 0644.
    All other files are set to 0600.
    Also removes any ACL entries that could leave permissions more open.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Fixing permissions...", total=None)

        # Set permissions for the .ssh directory itself
        try:
            os.chmod(ssh_dir, 0o700)
            os.chown(ssh_dir, uid, gid)
            remove_acl(ssh_dir)
        except Exception as e:
            console.print(
                f"[danger]Error setting permissions for {ssh_dir}: {e}[/danger]"
            )

        # Walk through the directory recursively
        for root, dirs, files in os.walk(ssh_dir):
            for directory in dirs:
                dir_path = os.path.join(root, directory)
                try:
                    os.chmod(dir_path, 0o700)
                    os.chown(dir_path, uid, gid)
                    remove_acl(dir_path)
                except Exception as e:
                    console.print(
                        f"[danger]Error setting permissions for directory {dir_path}: {e}[/danger]"
                    )
            for filename in files:
                file_path = os.path.join(root, filename)
                mode = 0o644 if filename.endswith(".pub") else 0o600
                try:
                    os.chmod(file_path, mode)
                    os.chown(file_path, uid, gid)
                    remove_acl(file_path)
                except Exception as e:
                    console.print(
                        f"[danger]Error setting permissions for file {file_path}: {e}[/danger]"
                    )

        progress.update(task_id, description="Permissions fixed!")


def create_ssh_key(cfg: SSHManagerConfig) -> None:
    """
    Interactively create a new SSH key for the specified user.
    """
    # Confirm existence of ~/.ssh directory
    if not os.path.isdir(cfg.ssh_dir):
        try:
            os.makedirs(cfg.ssh_dir, mode=0o700, exist_ok=True)
            os.chown(cfg.ssh_dir, *get_user_ids(cfg.user))
        except Exception as e:
            console.print(f"[danger]Failed to create {cfg.ssh_dir}: {e}[/danger]")
            return

    # Ask for a key filename (optional)
    console.print(
        "[info]Enter a filename for the SSH key (press Enter for 'id_rsa'):[/info]"
    )
    key_name = console.input("> ").strip()
    if key_name == "":
        key_name = "id_rsa"
    key_full_path = os.path.join(cfg.ssh_dir, key_name)

    # If file exists, confirm overwrite
    if os.path.exists(key_full_path):
        console.print(
            f"[warning]Key file {key_full_path} already exists. Overwrite? (y/n)[/warning]"
        )
        overwrite = console.input("> ").lower().strip()
        if overwrite not in ["y", "yes"]:
            console.print("[info]Aborting key creation.[/info]")
            return

    # Actually generate the key
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Generating SSH key...", total=None)

        cmd = [
            "ssh-keygen",
            "-t",
            "rsa",
            "-b",
            "4096",
            "-f",
            key_full_path,
            "-N",
            "",
        ]
        try:
            subprocess.run(cmd, check=True)
            progress.update(task_id, description="Key generation completed!")
            console.print(f"[success]SSH key generated at {key_full_path}[/success]")
        except subprocess.CalledProcessError as e:
            console.print(f"[danger]Failed to generate SSH key: {e}[/danger]")
            return

    # Update config to point to newly created key
    cfg.key_path = key_full_path


def push_ssh_key(cfg: SSHManagerConfig) -> None:
    """
    Push the current SSH key to one or more client machines using ssh-copy-id.
    """
    if not os.path.isfile(cfg.key_path):
        console.print(
            f"[danger]No private key found at {cfg.key_path}. Please create a key first.[/danger]"
        )
        return

    # Ask for a comma-separated list of client hosts
    console.print(
        "[info]Enter a comma-separated list of client hosts (e.g., host1, host2):[/info]"
    )
    hosts_input = console.input("> ").strip()
    if not hosts_input:
        console.print("[warning]No hosts provided. Aborting push.[/warning]")
        return
    hosts = [h.strip() for h in hosts_input.split(",") if h.strip()]

    # Optionally ask for the remote user if different from the local user
    console.print(
        "[info]Enter the remote user for these hosts (press Enter to use same local username):[/info]"
    )
    remote_user = console.input("> ").strip()
    if not remote_user:
        remote_user = cfg.user

    # We assume the .pub file has the same name as the private key, plus ".pub"
    public_key_path = f"{cfg.key_path}.pub"
    if not os.path.isfile(public_key_path):
        console.print(
            f"[danger]No public key found at {public_key_path}. Aborting push.[/danger]"
        )
        return

    # Use a table to display results
    results_table = Table(
        title="Push SSH Key Results",
        box=box.ROUNDED,
        style="primary",
        show_lines=True,
    )
    results_table.add_column("Host", justify="left")
    results_table.add_column("Status", justify="left")

    # Push the key with a progress spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Pushing keys...", total=len(hosts))

        for host in hosts:
            full_target = f"{remote_user}@{host}"
            cmd = ["ssh-copy-id", "-i", public_key_path, full_target]
            try:
                subprocess.run(cmd, check=True)
                results_table.add_row(host, "[success]Success[/success]")
            except subprocess.CalledProcessError as e:
                results_table.add_row(host, f"[danger]Failed: {e}[/danger]")
            progress.advance(task_id, 1)

    console.print(results_table)


def fix_ssh_permissions(cfg: SSHManagerConfig) -> None:
    """
    Wrapper to fix SSH permissions for the user's ~/.ssh directory.
    """
    if not os.path.isdir(cfg.ssh_dir):
        console.print(
            f"[danger]No .ssh directory found for user '{cfg.user}' at {cfg.ssh_dir}[/danger]"
        )
        return

    ids = get_user_ids(cfg.user)
    if ids is None:
        return
    uid, gid = ids
    set_permissions_recursive(cfg.ssh_dir, uid, gid)
    console.print(
        Panel(
            f"SSH folder permissions have been updated for user '{cfg.user}'",
            title="Success",
            style="success",
        )
    )


# ------------------------------
# 5. Main Interactive Menu Loop
# ------------------------------
def main() -> None:
    """
    Main entry point:
      - Presents an interactive menu for:
         1) Creating a new SSH key
         2) Pushing the SSH key to client(s)
         3) Fixing permissions on the .ssh folder
         4) Exiting the application
      - Implements the core logic in modular functions.
    """
    # Detect or ask for the local user
    local_user = getpass.getuser()
    console.print(f"[info]Detected current user: {local_user}[/info]")
    console.print(
        "[info]Press Enter to use this user, or type another username:[/info]"
    )
    user_input = console.input("> ").strip()
    if user_input:
        local_user = user_input

    cfg = SSHManagerConfig(user=local_user)

    while True:
        console.clear()
        print_banner()

        menu_panel = Panel.fit(
            Text(
                "Please select an option:\n"
                "  [1] Create a new SSH key\n"
                "  [2] Push SSH key to client(s)\n"
                "  [3] Fix SSH permissions\n"
                "  [4] Exit\n",
                style="info",
            ),
            title="Main Menu",
            style="primary",
        )
        console.print(menu_panel)
        choice = console.input("[info]Enter choice (1-4): [/info]").strip()

        if choice == "1":
            create_ssh_key(cfg)
            console.print("[info]Press Enter to return to menu[/info]")
            console.input()
        elif choice == "2":
            push_ssh_key(cfg)
            console.print("[info]Press Enter to return to menu[/info]")
            console.input()
        elif choice == "3":
            fix_ssh_permissions(cfg)
            console.print("[info]Press Enter to return to menu[/info]")
            console.input()
        elif choice == "4":
            console.print("[warning]Exiting...[/warning]")
            sys.exit(0)
        else:
            console.print("[danger]Invalid choice. Please try again.[/danger]")
            console.print("[info]Press Enter to return to menu[/info]")
            console.input()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[danger]An unexpected error occurred: {e}[/danger]")
        sys.exit(1)
