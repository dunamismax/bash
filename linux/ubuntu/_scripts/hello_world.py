#!/usr/bin/env python3
"""
Nord Themed Hello World App
---------------------------
An interactive terminal application that displays a 'Hello, World!' message with a Nord dark theme, dynamic ASCII art, and rich spinners as artistic accents.
"""

import sys
import time

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.align import Align
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)


# Define Nord dark theme colors
class NordColors:
    BACKGROUND = "#2E3440"  # Dark background
    PANEL_BORDER = "#81A1C1"  # Accent blue
    ACCENT = "#88C0D0"  # Lighter blue for accents
    TEXT = "#D8DEE9"  # Light text
    SUCCESS = "#A3BE8C"  # Greenish for success
    WARNING = "#EBCB8B"  # Warm accent


# Create a Rich Console
console = Console()


def create_header(text: str) -> Panel:
    """
    Create a dynamic ASCII art header using Pyfiglet and wrap it in a Rich Panel with Nord styling.

    Args:
        text: The text to render as ASCII art.

    Returns:
        A Rich Panel containing the rendered ASCII art.
    """
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    header_panel = Panel(
        Align.center(ascii_art),
        border_style=NordColors.PANEL_BORDER,
        title=f"[bold {NordColors.ACCENT}]Nord Hello World App[/]",
        subtitle=f"[bold {NordColors.TEXT}]Hello, World![/]",
        padding=(1, 2),
    )
    return header_panel


def display_spinner_art(duration: float = 2.0) -> None:
    """
    Display spinners as dynamic art across the screen using Rich spinners.

    Args:
        duration: Duration in seconds to display the spinner art.
    """
    spinner_message = f"[bold {NordColors.ACCENT}]Loading Nord Art...[/]"
    with Progress(
        SpinnerColumn(style=NordColors.ACCENT),
        TextColumn(spinner_message, style=NordColors.TEXT),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(0.1)


def main() -> None:
    """
    Main function to display the Nord themed hello world message with enhanced rich spinner art.
    """
    console.clear()

    # Display introductory spinner art
    display_spinner_art(2.5)

    # Display the header with dynamic ASCII art
    header = create_header("Hello World")
    console.print(header)

    # Display additional spinner art below the header
    display_spinner_art(1.5)

    # Show a welcoming message with Nord styling
    console.print(
        f"\n[bold {NordColors.SUCCESS}]Welcome to the Nord Themed Python Hello World App![/]\n"
    )

    # Use a spinner to simulate a final processing effect before exit
    with Progress(
        SpinnerColumn(style=NordColors.ACCENT),
        TextColumn(f"[dim {NordColors.TEXT}]Preparing to exit...[/]"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        time.sleep(2)

    # Prompt user to exit
    console.print(f"[dim {NordColors.TEXT}]Press Enter to exit...[/]")
    input()


if __name__ == "__main__":
    main()
