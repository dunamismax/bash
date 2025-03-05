#!/usr/bin/env python3
"""
SSH Management Tool
-------------------

An advanced, production-grade terminal application for managing SSH keys and permissions
on the main Ubuntu server. This tool provides a Nord-themed, interactive menu with:

  • Dynamic ASCII banners with gradient styling via Pyfiglet (adapting to terminal width)
  • A fully interactive, numbered menu-driven interface with input validation
  • Rich library integration for panels, tables, spinners, and real-time progress tracking
  • Comprehensive error handling with color-coded messages and recovery suggestions
  • Signal handling for graceful termination (SIGINT, SIGTERM)
  • Type annotations and dataclasses for improved readability
  • Modular architecture with well-documented sections

Core Features:
  [1] Create a new SSH key on the main server
  [2] Push the SSH key to one or more client machines (using StrictHostKeyChecking=accept-new)
  [3] Fix permissions on the ~/.ssh folder
  [4] Exit gracefully

Usage:
  Run the script:
      ./ssh_manager.py
"""

import os
import sys
import pwd
import signal
import subprocess
import getpass
import shutil
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from pyfiglet import Figlet
from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

# ------------------------------
# 1. Nord-Themed Rich Console Setup
# ------------------------------
nord_theme = Theme(
    {
        "info": "#88C0D0",
        "warning": "#EBCB8B",
        "danger": "#BF616A",
        "success": "#A3BE8C",
        "primary": "#5E81AC",
        "banner": "#81A1C1",
        "frost1": "#8FBCBB",
        "frost2": "#88C0D0",
        "frost3": "#81A1C1",
        "frost4": "#5E81AC",
    }
)
console = Console(theme=nord_theme)


# ------------------------------
# 2. Dataclass for Script Parameters
# ------------------------------
@dataclass
class SSHManagerConfig:
    user: str
    home_dir: str = field(init=False)
    ssh_dir: str = field(init=False)
    key_path: str = field(init=False)

    def __post_init__(self) -> None:
        self.home_dir = f"/home/{self.user}"
        self.ssh_dir = os.path.join(self.home_dir, ".ssh")
        # Default key file is 'id_rsa'; this can be updated when a new key is created.
        self.key_path = os.path.join(self.ssh_dir, "id_rsa")


# ------------------------------
# 3. Signal Handling for Graceful Termination
# ------------------------------
def handle_signal(signum: int, frame) -> None:
    """
    Gracefully handle termination signals.
    """
    console.print(f"[danger]\nReceived signal {signum}. Exiting gracefully...[/danger]")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ------------------------------
# 4. Dynamic ASCII Banner with Gradient Styling
# ------------------------------
def print_banner() -> None:
    """
    Render a dynamic ASCII banner using Pyfiglet.
    The banner font is chosen based on terminal width, and each line is rendered in a gradient.
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    font = "slant" if term_width >= 80 else "small"
    fig = Figlet(font=font, width=term_width - 10)
    banner_text = fig.renderText("SSH Manager")
    frost_colors = ["frost1", "frost2", "frost3", "frost4"]
    banner_lines = banner_text.splitlines()
    styled_lines = []
    for i, line in enumerate(banner_lines):
        style = frost_colors[i % len(frost_colors)]
        styled_lines.append(Text(line, style=style))
    combined = Text("\n").join(styled_lines)
    panel = Panel(
        combined,
        border_style="banner",
        box=box.ROUNDED,
        padding=(1, 2),
        title=Text("v1.0.0", style="primary"),
        title_align="right",
    )
    console.print(panel)


# ------------------------------
# 5. Utility / Helper Functions
# ------------------------------
def get_user_ids(user: str) -> Optional[Tuple[int, int]]:
    """
    Retrieve the UID and GID for the specified user.
    """
    try:
        pw_record = pwd.getpwnam(user)
        return pw_record.pw_uid, pw_record.pw_gid
    except KeyError:
        console.print(f"[danger]User '{user}' not found.[/danger]")
        return None


def remove_acl(path: str) -> None:
    """
    Remove any extended ACL entries from a given file or directory.
    """
    try:
        subprocess.run(
            ["setfacl", "-b", path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        console.print(f"[success]Removed ACL from: {path}[/success]")
    except subprocess.CalledProcessError as e:
        console.print(f"[danger]Error removing ACL for {path}: {e}[/danger]")


def set_permissions_recursive(ssh_dir: str, uid: int, gid: int) -> None:
    """
    Recursively set the correct permissions for the .ssh directory and its contents.
      - Directories: 0700
      - Public key files (*.pub): 0644
      - Other files: 0600
    Also removes any ACL entries.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Fixing permissions...", total=None)
        try:
            os.chmod(ssh_dir, 0o700)
            os.chown(ssh_dir, uid, gid)
            remove_acl(ssh_dir)
        except Exception as e:
            console.print(
                f"[danger]Error setting permissions for {ssh_dir}: {e}[/danger]"
            )
        for root, dirs, files in os.walk(ssh_dir):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    os.chmod(dir_path, 0o700)
                    os.chown(dir_path, uid, gid)
                    remove_acl(dir_path)
                except Exception as e:
                    console.print(
                        f"[danger]Error setting permissions for directory {dir_path}: {e}[/danger]"
                    )
            for f in files:
                file_path = os.path.join(root, f)
                mode = 0o644 if f.endswith(".pub") else 0o600
                try:
                    os.chmod(file_path, mode)
                    os.chown(file_path, uid, gid)
                    remove_acl(file_path)
                except Exception as e:
                    console.print(
                        f"[danger]Error setting permissions for file {file_path}: {e}[/danger]"
                    )
        progress.update(task_id, description="Permissions fixed!")


# ------------------------------
# 6. Core SSH Key Management Functions
# ------------------------------
def create_ssh_key(cfg: SSHManagerConfig) -> None:
    """
    Interactively create a new SSH key for the specified user.
    """
    if not os.path.isdir(cfg.ssh_dir):
        try:
            os.makedirs(cfg.ssh_dir, mode=0o700, exist_ok=True)
            if (ids := get_user_ids(cfg.user)) is not None:
                os.chown(cfg.ssh_dir, *ids)
        except Exception as e:
            console.print(f"[danger]Failed to create {cfg.ssh_dir}: {e}[/danger]")
            return

    console.print(
        "[info]Enter a filename for the SSH key (press Enter for 'id_rsa'):[/info]"
    )
    key_name = console.input("> ").strip() or "id_rsa"
    key_full_path = os.path.join(cfg.ssh_dir, key_name)
    if os.path.exists(key_full_path):
        console.print(
            f"[warning]Key file {key_full_path} already exists. Overwrite? (y/n)[/warning]"
        )
        if console.input("> ").lower().strip() not in ["y", "yes"]:
            console.print("[info]Aborting key creation.[/info]")
            return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Generating SSH key...", total=None)
        cmd = ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_full_path, "-N", ""]
        try:
            subprocess.run(cmd, check=True)
            progress.update(task_id, description="Key generation completed!")
            console.print(f"[success]SSH key generated at {key_full_path}[/success]")
        except subprocess.CalledProcessError as e:
            console.print(f"[danger]Failed to generate SSH key: {e}[/danger]")
            return

    cfg.key_path = key_full_path


def push_ssh_key(cfg: SSHManagerConfig) -> None:
    """
    Push the current SSH key to one or more client machines using ssh-copy-id.
    Uses the SSH option StrictHostKeyChecking=accept-new to automatically accept new host keys.

    Note: If a password is required, the ssh-copy-id command will prompt interactively.
    Ensure the process is attached to a TTY so the prompt is visible.
    """
    if not os.path.isfile(cfg.key_path):
        console.print(
            f"[danger]No private key found at {cfg.key_path}. Please create a key first.[/danger]"
        )
        return

    console.print(
        "[info]Enter a comma-separated list of client hosts (e.g., host1, host2):[/info]"
    )
    hosts_input = console.input("> ").strip()
    if not hosts_input:
        console.print("[warning]No hosts provided. Aborting push.[/warning]")
        return
    hosts = [h.strip() for h in hosts_input.split(",") if h.strip()]

    console.print(
        "[info]Enter the remote user for these hosts (press Enter to use local username):[/info]"
    )
    remote_user = console.input("> ").strip() or cfg.user

    public_key_path = f"{cfg.key_path}.pub"
    if not os.path.isfile(public_key_path):
        console.print(
            f"[danger]No public key found at {public_key_path}. Aborting push.[/danger]"
        )
        return

    results_table = Table(
        title="Push SSH Key Results", box=box.ROUNDED, style="primary", show_lines=True
    )
    results_table.add_column("Host", justify="left")
    results_table.add_column("Status", justify="left")

    for host in hosts:
        full_target = f"{remote_user}@{host}"
        cmd = [
            "ssh-copy-id",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-i",
            public_key_path,
            full_target,
        ]
        console.print(f"[info]Pushing key to {full_target}...[/info]")
        try:
            # Run ssh-copy-id without redirecting input/output so that password prompts are visible.
            subprocess.run(cmd, check=True)
            results_table.add_row(host, "[success]Success[/success]")
        except subprocess.CalledProcessError as e:
            results_table.add_row(host, f"[danger]Failed: {e}[/danger]")
    console.print(results_table)


def fix_ssh_permissions(cfg: SSHManagerConfig) -> None:
    """
    Fix SSH folder permissions for the user's ~/.ssh directory.
    """
    if not os.path.isdir(cfg.ssh_dir):
        console.print(
            f"[danger]No .ssh directory found for user '{cfg.user}' at {cfg.ssh_dir}[/danger]"
        )
        return
    if (ids := get_user_ids(cfg.user)) is None:
        return
    uid, gid = ids
    set_permissions_recursive(cfg.ssh_dir, uid, gid)
    console.print(
        Panel(
            f"SSH folder permissions updated for user '{cfg.user}'.",
            title="Success",
            style="success",
        )
    )


# ------------------------------
# 7. Main Interactive Menu Loop
# ------------------------------
def main() -> None:
    """
    Main entry point presenting an interactive, numbered menu for:
      [1] Creating a new SSH key
      [2] Pushing the SSH key to client(s)
      [3] Fixing SSH folder permissions
      [4] Exiting the application
    """
    local_user = getpass.getuser()
    console.print(f"[info]Detected current user: {local_user}[/info]")
    console.print(
        "[info]Press Enter to use this user or type a different username:[/info]"
    )
    user_input = console.input("> ").strip()
    if user_input:
        local_user = user_input

    cfg = SSHManagerConfig(user=local_user)

    while True:
        console.clear()
        print_banner()
        menu_text = (
            "Please select an option:\n"
            "  [1] Create a new SSH key\n"
            "  [2] Push SSH key to client(s)\n"
            "  [3] Fix SSH permissions\n"
            "  [4] Exit\n"
        )
        menu_panel = Panel.fit(
            Text(menu_text, style="info"), title="Main Menu", style="primary"
        )
        console.print(menu_panel)
        choice = console.input("[info]Enter choice (1-4): [/info]").strip()
        if choice == "1":
            create_ssh_key(cfg)
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()
        elif choice == "2":
            push_ssh_key(cfg)
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()
        elif choice == "3":
            fix_ssh_permissions(cfg)
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()
        elif choice == "4":
            console.print("[warning]Exiting...[/warning]")
            sys.exit(0)
        else:
            console.print("[danger]Invalid choice. Please try again.[/danger]")
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"[danger]An unexpected error occurred: {e}[/danger]")
        sys.exit(1)
