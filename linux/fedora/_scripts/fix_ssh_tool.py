#!/usr/bin/env python3
"""
SSH Management Tool
-------------------

An advanced, production-grade terminal application for managing SSH keys and permissions
on Ubuntu. This tool provides a Nord-themed, interactive menu with:

  • Dynamic ASCII banners with gradient styling via Pyfiglet (adapting to terminal width)
  • A fully interactive, numbered menu-driven interface with input validation
  • Rich library integration for panels, tables, spinners, and real-time progress tracking
  • Comprehensive error handling with color-coded messages and recovery suggestions
  • Signal handling for graceful termination (SIGINT, SIGTERM)
  • Type annotations and dataclasses for improved readability
  • Modular architecture with well-documented sections

Core Features:
  [1] Create a new SSH key on the local machine
  [2] Push the SSH key to one or more client machines (using StrictHostKeyChecking=accept-new)
  [3] Fix permissions on the ~/.ssh folder
  [4] Establish Mutual SSH Trust (bidirectional key exchange)
  [5] Enable Key Authentication (disable password auth) on Ubuntu
  [6] Exit gracefully

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
    console.print(f"[danger]\nReceived signal {signum}. Exiting gracefully...[/danger]")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ------------------------------
# 4. Dynamic ASCII Banner with Gradient Styling
# ------------------------------
def print_banner() -> None:
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
    try:
        pw_record = pwd.getpwnam(user)
        return pw_record.pw_uid, pw_record.pw_gid
    except KeyError:
        console.print(f"[danger]User '{user}' not found.[/danger]")
        return None


def remove_acl(path: str) -> None:
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
            subprocess.run(cmd, check=True)
            results_table.add_row(host, "[success]Success[/success]")
        except subprocess.CalledProcessError as e:
            results_table.add_row(host, f"[danger]Failed: {e}[/danger]")
    console.print(results_table)


def fix_ssh_permissions(cfg: SSHManagerConfig) -> None:
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


def establish_mutual_ssh_trust(cfg: SSHManagerConfig) -> None:
    """
    Establish reciprocal SSH trust between the local machine and a remote machine.
    Revised for better handling on machines (such as your Lenovo) where repeated password prompts may trigger fail2ban.
    Steps:
      1. Ensure local SSH key exists (and create one if missing).
      2. Push the local public key to the remote host (password prompt allowed once).
      3. Test passwordless connection using BatchMode to avoid repeated prompts.
      4. If successful, retrieve the remote public key (using BatchMode so it fails fast if not allowed).
      5. Append the remote public key to the local authorized_keys if not already present.
    """
    # Step 1: Ensure local key exists
    if not os.path.isfile(cfg.key_path):
        console.print("[info]Local SSH key not found. Generating one...[/info]")
        create_ssh_key(cfg)
        if not os.path.isfile(cfg.key_path):
            console.print("[danger]Failed to create local SSH key. Aborting.[/danger]")
            return

    console.print("[info]Enter the remote host for mutual SSH trust:[/info]")
    remote_host = console.input("> ").strip()
    if not remote_host:
        console.print(
            "[warning]No remote host provided. Aborting mutual trust setup.[/warning]"
        )
        return

    console.print(
        "[info]Enter the remote user (press Enter to use local username):[/info]"
    )
    remote_user = console.input("> ").strip() or cfg.user

    console.print(
        "[warning]Note: The local key will be pushed first; if passwordless login fails, mutual trust cannot be established automatically.[/warning]"
    )

    # Step 2: Push local key to remote
    public_key_path = f"{cfg.key_path}.pub"
    if not os.path.isfile(public_key_path):
        console.print(
            f"[danger]Local public key not found at {public_key_path}. Aborting.[/danger]"
        )
        return

    console.print(f"[info]Pushing local key to {remote_user}@{remote_host}...[/info]")
    try:
        push_cmd = [
            "ssh-copy-id",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-i",
            public_key_path,
            f"{remote_user}@{remote_host}",
        ]
        subprocess.run(push_cmd, check=True)
        console.print(
            f"[success]Local key pushed to {remote_user}@{remote_host} successfully.[/success]"
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[danger]Failed to push local key: {e}[/danger]")
        return

    # Step 3: Test passwordless connection (fail fast if not yet accepted)
    console.print(
        f"[info]Testing passwordless SSH connection to {remote_user}@{remote_host}...[/info]"
    )
    try:
        test_cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{remote_user}@{remote_host}",
            "echo CONNECTION_OK",
        ]
        result = subprocess.run(test_cmd, capture_output=True, text=True, check=True)
        if "CONNECTION_OK" not in result.stdout:
            raise subprocess.CalledProcessError(1, test_cmd)
        console.print("[success]Passwordless SSH connection verified.[/success]")
    except subprocess.CalledProcessError:
        console.print(
            "[danger]Passwordless SSH connection failed. Ensure your key was correctly pushed and that remote host allows key authentication.[/danger]"
        )
        return

    # Step 4: Retrieve remote public key using BatchMode to avoid extra password prompts
    console.print(
        f"[info]Retrieving remote public key from {remote_user}@{remote_host}...[/info]"
    )
    try:
        # We assume that once key authentication is working, the remote public key is in ~/.ssh/id_rsa.pub
        remote_cmd = "cat ~/.ssh/id_rsa.pub"
        get_key_cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{remote_user}@{remote_host}",
            remote_cmd,
        ]
        result = subprocess.run(get_key_cmd, capture_output=True, text=True, check=True)
        remote_pub_key = result.stdout.strip()
        if not remote_pub_key:
            console.print(
                "[danger]No remote public key retrieved. Aborting mutual trust setup.[/danger]"
            )
            return
        console.print("[success]Remote public key retrieved successfully.[/success]")
    except subprocess.CalledProcessError as e:
        console.print(f"[danger]Error retrieving remote public key: {e}[/danger]")
        return

    # Step 5: Add remote public key to local authorized_keys
    local_auth_keys = os.path.join(cfg.ssh_dir, "authorized_keys")
    if not os.path.isdir(cfg.ssh_dir):
        os.makedirs(cfg.ssh_dir, mode=0o700, exist_ok=True)
    if not os.path.isfile(local_auth_keys):
        open(local_auth_keys, "a").close()

    try:
        with open(local_auth_keys, "r") as f:
            keys = f.read()
    except Exception as e:
        console.print(f"[danger]Error reading {local_auth_keys}: {e}[/danger]")
        return

    if remote_pub_key in keys:
        console.print(
            "[info]Remote public key is already in local authorized_keys.[/info]"
        )
    else:
        try:
            with open(local_auth_keys, "a") as f:
                f.write("\n" + remote_pub_key + "\n")
            os.chmod(local_auth_keys, 0o600)
            console.print(
                "[success]Remote public key added to local authorized_keys successfully.[/success]"
            )
        except Exception as e:
            console.print(f"[danger]Failed to update {local_auth_keys}: {e}[/danger]")
            return

    console.print("[success]Mutual SSH trust established successfully![/success]")


def configure_sshd_for_key_auth() -> None:
    if os.geteuid() != 0:
        console.print(
            "[danger]Root privileges are required to modify sshd configuration. Please run this function as root or use sudo.[/danger]"
        )
        return

    config_file = "/etc/ssh/sshd_config"
    backup_file = "/etc/ssh/sshd_config.bak"
    try:
        shutil.copy2(config_file, backup_file)
        console.print(f"[info]Backup of sshd_config created at {backup_file}.[/info]")
    except Exception as e:
        console.print(f"[danger]Failed to backup sshd_config: {e}[/danger]")
        return

    try:
        with open(config_file, "r") as f:
            lines = f.readlines()
    except Exception as e:
        console.print(f"[danger]Failed to read sshd_config: {e}[/danger]")
        return

    new_lines = []
    password_set = False
    pubkey_set = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("PasswordAuthentication"):
            new_lines.append("PasswordAuthentication no\n")
            password_set = True
        elif stripped.startswith("PubkeyAuthentication"):
            new_lines.append("PubkeyAuthentication yes\n")
            pubkey_set = True
        else:
            new_lines.append(line)

    if not password_set:
        new_lines.append("PasswordAuthentication no\n")
    if not pubkey_set:
        new_lines.append("PubkeyAuthentication yes\n")

    try:
        with open(config_file, "w") as f:
            f.writelines(new_lines)
        console.print("[success]sshd_config updated successfully.[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to update sshd_config: {e}[/danger]")
        return

    try:
        subprocess.run(["systemctl", "restart", "ssh"], check=True)
        console.print("[success]SSH service restarted successfully.[/success]")
    except subprocess.CalledProcessError as e:
        console.print(f"[danger]Failed to restart SSH service: {e}[/danger]")


# ------------------------------
# 7. Main Interactive Menu Loop
# ------------------------------
def main() -> None:
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
            "  [4] Establish Mutual SSH Trust\n"
            "  [5] Enable Key Authentication (disable password auth)\n"
            "  [6] Exit\n"
        )
        menu_panel = Panel.fit(
            Text(menu_text, style="info"), title="Main Menu", style="primary"
        )
        console.print(menu_panel)
        choice = console.input("[info]Enter choice (1-6): [/info]").strip()
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
            establish_mutual_ssh_trust(cfg)
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()
        elif choice == "5":
            configure_sshd_for_key_auth()
            console.print("[info]Press Enter to return to the menu[/info]")
            console.input()
        elif choice == "6":
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
