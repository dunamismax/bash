#!/usr/bin/env python3
"""
Cool Hello World App
---------------------
A simple interactive terminal application that displays a cool 'Hello, World!' message using Rich and Pyfiglet.
"""

import sys
import time

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.align import Align
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Create a Rich Console
console = Console()


def create_header(text: str) -> Panel:
    """
    Create a dynamic ASCII art header using Pyfiglet and wrap it in a Rich Panel.

    Args:
        text: The text to render as ASCII art.

    Returns:
        A Rich Panel containing the rendered ASCII art.
    """
    # Generate ASCII art using Pyfiglet
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    # Create a panel with centered ASCII art and a border
    header_panel = Panel(
        Align.center(ascii_art),
        border_style="cyan",
        title="Cool App",
        subtitle="Hello, World!",
    )
    return header_panel


def main() -> None:
    """
    Main function to display the cool hello world message.
    """
    console.clear()

    # Display the header
    header = create_header("Hello World")
    console.print(header)

    # Add a welcoming message below the header
    console.print("\n[bold green]Welcome to the Cool Hello World App![/bold green]\n")

    # Pause for a moment to let the user enjoy the view
    time.sleep(2)

    # Prompt user to exit
    console.print("[dim]Press Enter to exit...[/dim]")
    input()


if __name__ == "__main__":
    main()
