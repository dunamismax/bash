#!/usr/bin/env python3
"""
Metasploit Framework Installer and Setup Script for Ubuntu
------------------------------------------------------------
This script installs the Metasploit Framework on Ubuntu by:
  1. Downloading the Metasploit installer.
  2. Making it executable.
  3. Running the installer.
After installation, the script launches msfconsole so you can follow the
interactive prompts to configure the database.
"""

import os
import sys
import subprocess
import time

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

console = Console()


def print_header():
    """Display a dynamic ASCII art header using pyfiglet and Rich."""
    ascii_art = pyfiglet.figlet_format("Metasploit Installer", font="slant")
    header = Panel(ascii_art, style="bold cyan", title="[bold]Metasploit Setup[/bold]")
    console.print(header)


def run_command(command_list, use_shell=False):
    """
    Executes a command and prints its output.
    Exits the script if the command fails.
    """
    try:
        result = subprocess.run(
            command_list,
            shell=use_shell,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.stdout:
            console.print(result.stdout)
    except subprocess.CalledProcessError as err:
        console.print(f"[red]Error:[/red] {err.stderr}")
        sys.exit(1)


def install_metasploit():
    """Download and execute the Metasploit installer."""
    console.print(
        "[bold green]Starting Metasploit Framework installation...[/bold green]"
    )

    # Step 1: Download the installer
    download_cmd = [
        "curl",
        "https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb",
        "-o",
        "msfinstall",
    ]
    run_command(download_cmd)

    # Step 2: Make the installer executable
    run_command(["chmod", "755", "msfinstall"])

    # Step 3: Run the installer
    run_command(["./msfinstall"])

    console.print("[bold green]Installation complete.[/bold green]")


def launch_msfconsole():
    """Launch msfconsole to continue the setup and interactive configuration."""
    console.print("\n[bold green]Launching msfconsole...[/bold green]")
    console.print(
        "If prompted, type [bold]y[/bold] or [bold]yes[/bold] to configure a new database.\n"
        "Once started, you can run [bold]db_status[/bold] to verify the database connection."
    )
    time.sleep(2)  # Pause briefly before launching
    # Replace the current process with msfconsole (searches PATH)
    os.execvp("msfconsole", ["msfconsole"])


def main():
    print_header()
    console.print(
        "[bold]This script will install and set up the Metasploit Framework on Ubuntu.[/bold]\n"
        "It will download the installer, set the proper permissions, run the installer, "
        "and then launch msfconsole for further configuration.\n"
    )

    if not Confirm.ask("Do you want to proceed with the installation?", default=True):
        console.print("[red]Installation aborted by user.[/red]")
        sys.exit(0)

    install_metasploit()

    # After the installer runs, launch msfconsole to begin interactive setup.
    launch_msfconsole()


if __name__ == "__main__":
    main()
