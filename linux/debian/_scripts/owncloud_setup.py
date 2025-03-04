#!/usr/bin/env python3
"""
OwnCloud Automated Installation and Setup Script for Debian
-------------------------------------------------------------

This interactive script automates the process of downloading the OwnCloud
complete deb package, installing it using 'nala', and configuring OwnCloud
via its occ command. The script is purely interactive with a numbered
menu system, and uses Rich and Pyfiglet for an enhanced terminal UI.

Requirements:
  • Debian system with 'nala' installed
  • sudo privileges for package installation and configuration
  • Internet connectivity

Features:
  • A stylish ASCII banner at startup (Pyfiglet)
  • A fully interactive, menu-driven CLI (Rich)
  • Progress bars and spinners for download, installation, and configuration
  • Clear prompts for admin credentials and database settings
"""

import os
import sys
import time
import tempfile
import subprocess
import requests
from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TimeRemainingColumn,
)
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
import pyfiglet

# ----------------------------------------------------------------
# Nord Color Palette
# ----------------------------------------------------------------
NORD_POLAR_NIGHT = "#2E3440"
NORD_SNOW_STORM_1 = "#D8DEE9"
NORD_FROST_1 = "#8FBCBB"
NORD_FROST_2 = "#88C0D0"
NORD_FROST_3 = "#81A1C1"
NORD_FROST_4 = "#5E81AC"
NORD_GREEN = "#A3BE8C"
NORD_RED = "#BF616A"

# Create a Rich Console instance with default styling.
console = Console()


# ----------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------
def display_banner() -> None:
    """
    Display a stylish ASCII banner using Pyfiglet.
    """
    banner = pyfiglet.figlet_format("OwnCloud Setup", font="slant")
    console.print(Text(banner, style=f"bold {NORD_FROST_2}"))


def download_package(url: str, destination: str) -> None:
    """
    Download the OwnCloud deb package from the given URL and save it to 'destination'.
    A Rich progress bar displays the download progress.
    """
    console.print(f"[bold {NORD_FROST_2}]Starting download of OwnCloud package...[/]")
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_length = int(response.headers.get("content-length", 0))
            with (
                open(destination, "wb") as deb_file,
                Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    " • ",
                    DownloadColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress,
            ):
                task = progress.add_task("Downloading", total=total_length)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        deb_file.write(chunk)
                        progress.update(task, advance=len(chunk))
        console.print(f"[bold {NORD_GREEN}]Download completed successfully.[/]")
    except Exception as err:
        console.print(f"[bold {NORD_RED}]Download failed: {err}[/]")
        sys.exit(1)


def install_package(deb_path: str) -> None:
    """
    Install the downloaded OwnCloud deb package using 'nala'.
    A Rich spinner is displayed while the installation is in progress.
    """
    console.print(f"[bold {NORD_FROST_2}]Installing OwnCloud package...[/]")
    try:
        with console.status("[bold green]Installing package...[/]"):
            cmd = ["sudo", "nala", "install", "-y", deb_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                console.print(
                    f"[bold {NORD_RED}]Installation failed: {result.stderr}[/]"
                )
                sys.exit(1)
            time.sleep(2)  # Brief pause after installation
        console.print(f"[bold {NORD_GREEN}]OwnCloud package installed successfully.[/]")
    except Exception as err:
        console.print(f"[bold {NORD_RED}]Installation error: {err}[/]")
        sys.exit(1)


def configure_owncloud(
    admin_user: str,
    admin_pass: str,
    db_name: str,
    db_user: str,
    db_pass: str,
    db_type: str = "mysql",
) -> None:
    """
    Configure OwnCloud by running the occ command.
    Sets up the admin account and database configuration.
    """
    occ_path = "/var/www/owncloud/occ"
    if not os.path.exists(occ_path):
        console.print(
            f"[bold {NORD_RED}]occ command not found at {occ_path}. Ensure OwnCloud is installed correctly.[/]"
        )
        sys.exit(1)

    console.print(f"[bold {NORD_FROST_2}]Configuring OwnCloud...[/]")
    cmd = [
        "sudo",
        "-u",
        "www-data",
        "php",
        occ_path,
        "maintenance:install",
        "--database",
        db_type,
        "--database-name",
        db_name,
        "--database-user",
        db_user,
        "--database-pass",
        db_pass,
        "--admin-user",
        admin_user,
        "--admin-pass",
        admin_pass,
    ]
    try:
        with console.status("[bold green]Configuring OwnCloud...[/]"):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                console.print(
                    f"[bold {NORD_RED}]Configuration failed: {result.stderr}[/]"
                )
                sys.exit(1)
            time.sleep(2)
        console.print(f"[bold {NORD_GREEN}]OwnCloud configured successfully.[/]")
    except Exception as err:
        console.print(f"[bold {NORD_RED}]Configuration error: {err}[/]")
        sys.exit(1)


# ----------------------------------------------------------------
# Menu Functions
# ----------------------------------------------------------------
def show_menu() -> None:
    """
    Display a numbered menu system and process user selections.
    """
    # Constants for package URL and temporary download location
    PACKAGE_URL = (
        "https://download.opensuse.org/repositories/isv:/ownCloud:/server:/10/Debian_12/all/"
        "owncloud-complete-files_10.15.0-1+27.4_all.deb"
    )
    temp_dir = tempfile.gettempdir()
    deb_path = os.path.join(temp_dir, "owncloud.deb")

    while True:
        console.print(
            Panel.fit(
                "MAIN MENU", title="[bold]OwnCloud Setup", border_style=NORD_FROST_3
            )
        )
        console.print("[bold]1.[/] Download OwnCloud Package")
        console.print("[bold]2.[/] Install OwnCloud Package")
        console.print("[bold]3.[/] Configure OwnCloud")
        console.print("[bold]4.[/] Full Setup (Download, Install, Configure)")
        console.print("[bold]5.[/] Exit\n")

        choice = Prompt.ask(
            "[bold purple]Enter your choice[/]",
            choices=["1", "2", "3", "4", "5"],
            default="5",
        )

        if choice == "1":
            console.print(f"[bold {NORD_FROST_2}]Downloading package to {deb_path}[/]")
            download_package(PACKAGE_URL, deb_path)
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "2":
            if not os.path.exists(deb_path):
                console.print(
                    f"[bold {NORD_RED}]Deb package not found. Please download the package first.[/]"
                )
            else:
                install_package(deb_path)
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "3":
            console.print(
                f"[bold {NORD_FROST_2}]Proceeding to OwnCloud configuration...[/]"
            )
            admin_user = Prompt.ask(
                "[bold]Enter OwnCloud admin username[/]", default="admin"
            )
            admin_pass = Prompt.ask(
                "[bold]Enter OwnCloud admin password[/]", password=True
            )
            db_name = Prompt.ask("[bold]Enter database name[/]", default="owncloud")
            db_user = Prompt.ask("[bold]Enter database user[/]", default="ownclouduser")
            db_pass = Prompt.ask("[bold]Enter database password[/]", password=True)
            db_type = Prompt.ask(
                "[bold]Enter database type (mysql/postgres/sqlite)[/]",
                choices=["mysql", "postgres", "sqlite"],
                default="mysql",
            )
            configure_owncloud(
                admin_user, admin_pass, db_name, db_user, db_pass, db_type
            )
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "4":
            # Full setup: download, install, then configure OwnCloud
            console.print(f"[bold {NORD_FROST_2}]Starting full setup...[/]")
            download_package(PACKAGE_URL, deb_path)
            install_package(deb_path)
            console.print(
                f"[bold {NORD_FROST_2}]Proceeding to OwnCloud configuration...[/]"
            )
            admin_user = Prompt.ask(
                "[bold]Enter OwnCloud admin username[/]", default="admin"
            )
            admin_pass = Prompt.ask(
                "[bold]Enter OwnCloud admin password[/]", password=True
            )
            db_name = Prompt.ask("[bold]Enter database name[/]", default="owncloud")
            db_user = Prompt.ask("[bold]Enter database user[/]", default="ownclouduser")
            db_pass = Prompt.ask("[bold]Enter database password[/]", password=True)
            db_type = Prompt.ask(
                "[bold]Enter database type (mysql/postgres/sqlite)[/]",
                choices=["mysql", "postgres", "sqlite"],
                default="mysql",
            )
            configure_owncloud(
                admin_user, admin_pass, db_name, db_user, db_pass, db_type
            )
            Prompt.ask("\nPress Enter to return to the menu")
        elif choice == "5":
            console.print(
                Panel(
                    "[bold green]Exiting OwnCloud Setup. Goodbye![/]",
                    border_style=NORD_GREEN,
                )
            )
            sys.exit(0)
        else:
            console.print(f"[bold {NORD_RED}]Invalid selection. Please try again.[/]")


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function that displays the banner and launches the interactive menu.
    """
    console.clear()
    display_banner()
    show_menu()


if __name__ == "__main__":
    main()
