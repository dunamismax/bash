#!/usr/bin/env python3
"""
Fail2Ban Toolkit CLI Application
----------------------------------

A professional-grade terminal application for managing Fail2Ban with a
Nord-themed interface. This interactive CLI allows you to view Fail2Ban jails,
inspect banned IPs, unban IPs, restart the Fail2Ban service, and check overall
status—all with dynamic ASCII banners, progress tracking, and comprehensive error
handling for a production-grade user experience.

Features:
- Asynchronous execution for improved responsiveness
- Rich terminal UI with Nord color theme
- Comprehensive error handling and graceful shutdowns
- Type-annotated codebase for better maintainability

Usage:
  Run the script and follow the interactive menu options.

Version: 1.1.0
"""

# ----------------------------------------------------------------
# Dependencies and Imports
# ----------------------------------------------------------------
import os
import signal
import subprocess
import sys
import time
import shutil
import asyncio
import atexit
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Any, Callable, Union, TypeVar, cast

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

# Enable rich traceback for debugging
install_rich_traceback(show_locals=True)
console: Console = Console()


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """
    Nord color palette for consistent UI styling.
    https://www.nordtheme.com/docs/colors-and-palettes
    """

    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"
    RED: str = "#BF616A"
    ORANGE: str = "#D08770"
    YELLOW: str = "#EBCB8B"
    GREEN: str = "#A3BE8C"
    PURPLE: str = "#B48EAD"

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """
        Return a gradient of frost colors for dynamic banner styling.

        Args:
            steps: Number of color steps to return (max 4)

        Returns:
            List of color hex codes forming a gradient
        """
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Fail2Ban Toolkit"
APP_SUBTITLE: str = "Advanced CLI for Fail2Ban Management"
VERSION: str = "1.1.0"
OPERATION_TIMEOUT: int = 30  # seconds
DEFAULT_PROGRESS_DELAY: float = 1.0  # seconds, for smoother UX


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class Jail:
    """
    Represents a Fail2Ban jail and its banned IP list.

    Attributes:
        name: The jail's name.
        banned_ips: A list of banned IP addresses.
        enabled: Whether the jail is currently enabled.
        total_banned: Total number of IPs banned since jail started.
    """

    name: str
    banned_ips: List[str] = field(default_factory=list)
    enabled: bool = True
    total_banned: int = 0


T = TypeVar("T")


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """
    Create a dynamic ASCII banner header using Pyfiglet.
    The banner adapts to terminal width and applies a Nord-themed gradient.

    Returns:
        A Rich Panel containing the styled application header
    """
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "mini", "digital"]
    font_to_use: str = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]
    try:
        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")
    return Panel(
        combined_text,
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a formatted message with a given prefix and style.

    Args:
        text: The message to print
        style: The color/style to use
        prefix: The character prefix before the message
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """
    Print an error message in red.

    Args:
        message: The error message to display
    """
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    """
    Print a success message in green.

    Args:
        message: The success message to display
    """
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """
    Print a warning message in yellow.

    Args:
        message: The warning message to display
    """
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    """
    Print a step message in frost blue.

    Args:
        message: The step message to display
    """
    print_message(message, NordColors.FROST_2, "→")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """
    Display a formatted panel with a title and message.

    Args:
        title: The panel title
        message: The panel content
        style: The color/style for the panel border
    """
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


async def async_prompt(message: str, choices: Optional[List[str]] = None) -> str:
    """
    Async wrapper for Rich's Prompt.ask to maintain async flow.

    Args:
        message: The prompt message
        choices: Optional list of valid choices

    Returns:
        The user's input string
    """
    loop = asyncio.get_running_loop()
    if choices:
        return await loop.run_in_executor(
            None, lambda: Prompt.ask(message, choices=choices)
        )
    return await loop.run_in_executor(None, lambda: Prompt.ask(message))


async def async_confirm(message: str, default: bool = False) -> bool:
    """
    Async wrapper for Rich's Confirm.ask to maintain async flow.

    Args:
        message: The confirmation message
        default: Default value if user just presses Enter

    Returns:
        True if confirmed, False otherwise
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: Confirm.ask(message, default=default)
    )


# ----------------------------------------------------------------
# Fail2Ban Interaction Functions
# ----------------------------------------------------------------
async def run_command_async(cmd: List[str]) -> Tuple[int, str]:
    """
    Execute a shell command asynchronously and return its exit code and output.

    Args:
        cmd: List of command and arguments to execute

    Returns:
        Tuple of (return_code, stdout_output)

    Raises:
        Exception: If the command fails or times out
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            text=True,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=OPERATION_TIMEOUT
        )

        if proc.returncode != 0:
            raise Exception(stderr.strip())

        return proc.returncode, stdout.strip()
    except asyncio.TimeoutError:
        raise Exception(f"Command timed out after {OPERATION_TIMEOUT} seconds.")
    except Exception as e:
        raise Exception(f"Failed to execute command: {e}")


async def list_jails_async() -> List[Jail]:
    """
    Retrieve a list of Fail2Ban jails using 'fail2ban-client status'.

    Returns:
        A list of Jail objects with their names and banned IP lists.
    """
    try:
        _, output = await run_command_async(["fail2ban-client", "status"])
        # Example output:
        # Status
        # |- Number of jail:  2
        # `- Jail list:   sshd, apache
        jail_line = ""
        for line in output.splitlines():
            if "Jail list:" in line:
                jail_line = line.split("Jail list:")[1]
                break
        if not jail_line:
            return []
        jail_names = [j.strip() for j in jail_line.split(",")]

        # Create tasks for getting banned IPs for each jail
        tasks = [get_banned_ips_async(name) for name in jail_names]
        banned_ips_results = await asyncio.gather(*tasks, return_exceptions=True)

        jails = []
        for i, name in enumerate(jail_names):
            banned_ips = []
            if isinstance(banned_ips_results[i], list):  # Not an exception
                banned_ips = banned_ips_results[i]
            jails.append(Jail(name=name, banned_ips=banned_ips))

        return jails
    except Exception as e:
        print_error(f"Error listing jails: {str(e)}")
        return []


async def get_banned_ips_async(jail_name: str) -> List[str]:
    """
    Retrieve the list of banned IPs for a given jail using 'fail2ban-client status <jail>'.

    Args:
        jail_name: The name of the jail.

    Returns:
        A list of banned IP addresses.
    """
    try:
        _, output = await run_command_async(["fail2ban-client", "status", jail_name])
        banned_line = ""
        for line in output.splitlines():
            if "Banned IP list:" in line:
                banned_line = line.split("Banned IP list:")[1]
                break
        if not banned_line:
            return []
        ips = [ip.strip() for ip in banned_line.split()]
        return ips
    except Exception as e:
        print_error(f"Error getting banned IPs for {jail_name}: {str(e)}")
        return []


async def unban_ip_async(jail_name: str, ip: str) -> bool:
    """
    Unban an IP address from a specified jail using 'fail2ban-client set <jail> unbanip <IP>'.

    Args:
        jail_name: The name of the jail.
        ip: The IP address to unban.

    Returns:
        True if the unban operation succeeded, otherwise False.
    """
    try:
        await run_command_async(["fail2ban-client", "set", jail_name, "unbanip", ip])
        print_success(f"Unbanned IP {ip} from jail {jail_name}.")
        return True
    except Exception as e:
        print_error(f"Error unbanning IP {ip} from {jail_name}: {str(e)}")
        return False


async def restart_fail2ban_async() -> bool:
    """
    Restart the Fail2Ban service using 'systemctl restart fail2ban'.

    Returns:
        True if the service restarted successfully, otherwise False.
    """
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]Restarting Fail2Ban service...[/]"),
            console=console,
        ) as progress:
            task = progress.add_task("Restarting", total=None)
            await run_command_async(["sudo", "systemctl", "restart", "fail2ban"])

            # Add a slight delay to make the spinner visible
            await asyncio.sleep(DEFAULT_PROGRESS_DELAY)

        print_success("Fail2Ban service restarted successfully.")
        return True
    except Exception as e:
        print_error(f"Error restarting Fail2Ban: {str(e)}")
        return False


async def show_fail2ban_status_async() -> None:
    """
    Display the overall Fail2Ban status using 'fail2ban-client status'.
    """
    try:
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]Retrieving Fail2Ban status...[/]"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading", total=None)
            _, output = await run_command_async(["fail2ban-client", "status"])

            # Add a slight delay to make the spinner visible
            await asyncio.sleep(DEFAULT_PROGRESS_DELAY)

        display_panel("Fail2Ban Status", output)
    except Exception as e:
        print_error(f"Error retrieving Fail2Ban status: {str(e)}")


# ----------------------------------------------------------------
# UI Components for Fail2Ban Toolkit
# ----------------------------------------------------------------
def display_jails_table(jails: List[Jail]) -> None:
    """
    Display a table of Fail2Ban jails with the number of banned IPs.

    Args:
        jails: A list of Jail objects.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title="Fail2Ban Jails",
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Jail Name", style=f"bold {NordColors.FROST_1}", width=20)
    table.add_column(
        "Banned IPs", style=f"{NordColors.SNOW_STORM_1}", width=15, justify="center"
    )
    for idx, jail in enumerate(jails, 1):
        table.add_row(str(idx), jail.name, str(len(jail.banned_ips)))
    console.print(table)


def display_banned_ips_table(jail: Jail) -> None:
    """
    Display a table of banned IPs for a specified jail.

    Args:
        jail: A Jail object.
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=f"Banned IPs in Jail: {jail.name}",
        padding=(0, 1),
    )
    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Banned IP", style=f"{NordColors.SNOW_STORM_1}")
    for idx, ip in enumerate(jail.banned_ips, 1):
        table.add_row(str(idx), ip)
    console.print(table)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
async def async_cleanup() -> None:
    """Perform cleanup operations before exiting."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def cleanup() -> None:
    """Synchronous wrapper for the async cleanup function."""
    try:
        # Check if there's a running loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If a loop is already running, we can't run a new one
                print_warning("Event loop already running during shutdown")
                return
        except RuntimeError:
            # No event loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async cleanup
        loop.run_until_complete(async_cleanup())
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


async def signal_handler_async(sig: int, frame: Any) -> None:
    """
    Handle signals in an async-friendly way.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    # Get the current running loop
    loop = asyncio.get_running_loop()

    # Cancel all tasks except the current one
    for task in asyncio.all_tasks(loop):
        if task is not asyncio.current_task():
            task.cancel()

    # Clean up resources
    await async_cleanup()

    # Stop the loop
    loop.stop()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """
    Set up signal handlers that work with the main event loop.

    Args:
        loop: The asyncio event loop to use
    """
    # Use asyncio's built-in signal handling
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


# ----------------------------------------------------------------
# Main Interactive Menu
# ----------------------------------------------------------------
async def main_menu_async() -> None:
    """Display the main menu and process user input asynchronously."""
    while True:
        clear_screen()
        console.print(create_header())
        console.print(
            Align.center(Text(APP_SUBTITLE, style=f"bold {NordColors.SNOW_STORM_2}"))
        )
        console.print()
        console.print("[bold]Main Menu:[/]")
        console.print("[bold]1.[/] List Fail2Ban Jails")
        console.print("[bold]2.[/] Show Fail2Ban Status")
        console.print("[bold]3.[/] Show Banned IPs in a Jail")
        console.print("[bold]4.[/] Unban an IP from a Jail")
        console.print("[bold]5.[/] Restart Fail2Ban Service")
        console.print("[bold]6.[/] Exit")
        console.print()

        choice = await async_prompt(
            "Enter your choice", choices=["1", "2", "3", "4", "5", "6"]
        )

        if choice == "1":
            await list_jails_menu_async()
        elif choice == "2":
            await show_fail2ban_status_async()
            await async_prompt("Press Enter to return to the main menu")
        elif choice == "3":
            await show_banned_ips_menu_async()
        elif choice == "4":
            await unban_ip_menu_async()
        elif choice == "5":
            await restart_fail2ban_async()
            await async_prompt("Press Enter to return to the main menu")
        elif choice == "6":
            clear_screen()
            console.print(
                Panel(
                    Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                    border_style=NordColors.FROST_1,
                )
            )
            break


async def list_jails_menu_async() -> None:
    """Menu option to list Fail2Ban jails asynchronously."""
    clear_screen()
    console.print(create_header())
    console.print("[bold]Listing Fail2Ban Jails...[/]")

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]Retrieving jails...[/]"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading", total=None)
        jails = await list_jails_async()

        # Add a slight delay to make the spinner visible
        await asyncio.sleep(DEFAULT_PROGRESS_DELAY)

    if jails:
        display_jails_table(jails)
    else:
        print_warning("No jails found.")

    await async_prompt("Press Enter to return to the main menu")


async def show_banned_ips_menu_async() -> None:
    """Menu option to display banned IPs for a selected jail asynchronously."""
    clear_screen()
    console.print(create_header())

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]Retrieving jail information...[/]"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading", total=None)
        jails = await list_jails_async()

        # Add a slight delay to make the spinner visible
        await asyncio.sleep(DEFAULT_PROGRESS_DELAY)

    if not jails:
        print_warning("No jails available.")
        await async_prompt("Press Enter to return to the main menu")
        return

    display_jails_table(jails)
    jail_choice = await async_prompt("Enter the number of the jail to view banned IPs")

    try:
        idx = int(jail_choice) - 1
        if 0 <= idx < len(jails):
            selected_jail = jails[idx]
            if not selected_jail.banned_ips:
                print_warning(f"No banned IPs in the '{selected_jail.name}' jail.")
            else:
                display_banned_ips_table(selected_jail)
        else:
            print_error("Invalid jail selection.")
    except ValueError:
        print_error("Invalid input. Please enter a number.")

    await async_prompt("Press Enter to return to the main menu")


async def unban_ip_menu_async() -> None:
    """Menu option to unban an IP from a selected jail asynchronously."""
    clear_screen()
    console.print(create_header())

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("[bold]Retrieving jail information...[/]"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading", total=None)
        jails = await list_jails_async()

        # Add a slight delay to make the spinner visible
        await asyncio.sleep(DEFAULT_PROGRESS_DELAY)

    if not jails:
        print_warning("No jails available.")
        await async_prompt("Press Enter to return to the main menu")
        return

    display_jails_table(jails)
    jail_choice = await async_prompt("Enter the number of the jail to unban an IP from")

    try:
        idx = int(jail_choice) - 1
        if 0 <= idx < len(jails):
            selected_jail = jails[idx]
            if not selected_jail.banned_ips:
                print_warning(f"No banned IPs in the '{selected_jail.name}' jail.")
                await async_prompt("Press Enter to return to the main menu")
                return

            display_banned_ips_table(selected_jail)
            ip_choice = await async_prompt("Enter the number of the IP to unban")

            try:
                ip_idx = int(ip_choice) - 1
                if 0 <= ip_idx < len(selected_jail.banned_ips):
                    ip_to_unban = selected_jail.banned_ips[ip_idx]
                    if await async_confirm(
                        f"Are you sure you want to unban {ip_to_unban}?"
                    ):
                        with Progress(
                            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                            TextColumn(f"[bold]Unbanning {ip_to_unban}...[/]"),
                            console=console,
                        ) as progress:
                            task = progress.add_task("Unbanning", total=None)
                            result = await unban_ip_async(
                                selected_jail.name, ip_to_unban
                            )

                            # Add a slight delay to make the spinner visible
                            await asyncio.sleep(DEFAULT_PROGRESS_DELAY)
                else:
                    print_error("Invalid IP selection.")
            except ValueError:
                print_error("Invalid input. Please enter a number.")
        else:
            print_error("Invalid jail selection.")
    except ValueError:
        print_error("Invalid input. Please enter a number.")

    await async_prompt("Press Enter to return to the main menu")


async def main_async() -> None:
    """Main async entry point for the Fail2Ban Toolkit CLI application."""
    try:
        # Register cleanup handler using atexit
        atexit.register(cleanup)

        # Run the main menu
        await main_menu_async()
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    """Main entry point for the Fail2Ban Toolkit CLI application."""
    try:
        # Create and get a reference to the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers with the specific loop
        setup_signal_handlers(loop)

        # Run the main async function
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Received keyboard interrupt, shutting down...")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        loop = asyncio.get_event_loop()
        try:
            # Cancel all remaining tasks
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()

            # Allow cancelled tasks to complete
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            # Close the loop
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")

        print_message("Application terminated.", NordColors.FROST_3)


if __name__ == "__main__":
    main()
