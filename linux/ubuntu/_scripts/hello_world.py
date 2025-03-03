#!/usr/bin/env python3
"""
Nord-Themed Hello World App
--------------------------------------------------

An interactive terminal application that displays stylish 'Hello, World!'
messages with a sophisticated Nord dark theme, dynamic ASCII art headers,
and animated terminal effects.

Usage:
  Run the script and follow the on-screen prompts to interact with the application.
  - Enter text to see it displayed as ASCII art
  - Press Enter with no input to use default text
  - Type 'q' or 'quit' to exit the application

Version: 1.0.0
"""

import atexit
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, List, Optional

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.align import Align
    from rich.live import Live
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION: str = "1.0.0"
APP_NAME: str = "Hello World"
APP_SUBTITLE: str = "Nord-Themed Terminal Art"
DEFAULT_TEXT: str = "Hello, World!"
ANIMATION_DURATION: float = 2.0


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_2 = "#3B4252"  # Dark background shade
    POLAR_NIGHT_3 = "#434C5E"  # Medium background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color
    SNOW_STORM_3 = "#ECEFF4"  # Lightest text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green
    PURPLE = "#B48EAD"  # Purple


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class TextEffect:
    """
    Represents a text effect with its display properties.

    Attributes:
        name: The name of the effect
        description: A brief description of what the effect does
        color: The Nord color to use for this effect
    """

    name: str
    description: str
    color: str


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header(text: str = APP_NAME) -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Args:
        text: The text to convert to ASCII art (defaults to APP_NAME)

    Returns:
        Panel containing the styled header
    """
    # Try different fonts for the best aesthetics
    fonts = ["slant", "small", "standard", "big", "doom"]

    # Try each font until we find one that works well
    for font_name in fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name)
            ascii_art = fig.renderText(text)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Create gradient effects with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_art.split("\n")):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Create a decorative tech border
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text.strip() + "\n" + tech_border

    # Create a panel with good padding
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def display_spinner_art(
    message: str, duration: float, style: str = NordColors.FROST_2
) -> None:
    """
    Display spinners as dynamic art across the screen.

    Args:
        message: The message to display alongside the spinner
        duration: Duration in seconds to display the spinner
        style: The color style to use
    """
    spinner_style = style
    text_style = NordColors.SNOW_STORM_1

    with Progress(
        SpinnerColumn(style=spinner_style),
        TextColumn(f"[{text_style}]{message}[/]"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(0.1)


def display_message(message: str, style: str = NordColors.FROST_2) -> Panel:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use

    Returns:
        The created panel object
    """
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
    )
    console.print(panel)
    return panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform any cleanup tasks before exit."""
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name = signal.Signals(sig).name
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Animation and Visual Effects
# ----------------------------------------------------------------
def loading_animation(duration: float = 2.0) -> None:
    """
    Display a loading bar animation.

    Args:
        duration: Duration in seconds for the animation
    """
    total_steps = 100
    step_time = duration / total_steps

    with Progress(
        TextColumn(f"[bold {NordColors.FROST_3}]Loading"),
        BarColumn(
            bar_width=40,
            style=NordColors.POLAR_NIGHT_4,
            complete_style=NordColors.FROST_2,
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Loading", total=total_steps)

        for _ in range(total_steps):
            time.sleep(step_time)
            progress.advance(task)


def display_rainbow_text(text: str) -> None:
    """
    Display text with rainbow colors using Nord palette.

    Args:
        text: The text to display with rainbow colors
    """
    colors = [
        NordColors.RED,
        NordColors.ORANGE,
        NordColors.YELLOW,
        NordColors.GREEN,
        NordColors.FROST_1,
        NordColors.FROST_3,
        NordColors.PURPLE,
    ]

    rainbow_text = ""
    for i, char in enumerate(text):
        if char.strip():
            color = colors[i % len(colors)]
            rainbow_text += f"[bold {color}]{char}[/]"
        else:
            rainbow_text += " "

    console.print(Align.center(rainbow_text))


def typewriter_effect(text: str, delay: float = 0.05) -> None:
    """
    Display text with a typewriter effect.

    Args:
        text: The text to display with typewriter effect
        delay: Delay between characters in seconds
    """
    for char in text:
        console.print(char, end="", highlight=False)
        console.file.flush()
        time.sleep(delay)
    console.print()


# ----------------------------------------------------------------
# Main Application Functions
# ----------------------------------------------------------------
def get_available_effects() -> List[TextEffect]:
    """
    Get a list of available text effects.

    Returns:
        List of TextEffect objects
    """
    effects = [
        TextEffect(
            name="Standard",
            description="Classic Hello World display",
            color=NordColors.FROST_2,
        ),
        TextEffect(
            name="Rainbow",
            description="Colorful text using Nord Aurora colors",
            color=NordColors.YELLOW,
        ),
        TextEffect(
            name="Typewriter",
            description="Character-by-character animation",
            color=NordColors.GREEN,
        ),
        TextEffect(
            name="Glitch",
            description="Text with simulated digital glitches",
            color=NordColors.RED,
        ),
        TextEffect(
            name="Pulsing",
            description="Text that pulses with changing intensity",
            color=NordColors.PURPLE,
        ),
    ]
    return effects


def apply_effect(text: str, effect: TextEffect) -> None:
    """
    Apply a text effect to the given text.

    Args:
        text: The text to apply the effect to
        effect: The TextEffect to apply
    """
    console.print(f"\n[bold {effect.color}]Applying {effect.name} effect:[/]")
    time.sleep(0.5)

    if effect.name == "Standard":
        display_message(text, effect.color)
    elif effect.name == "Rainbow":
        display_rainbow_text(text)
    elif effect.name == "Typewriter":
        typewriter_effect(text)
    elif effect.name == "Glitch":
        # Simulate digital glitches
        glitch_chars = "!@#$%^&*()_+-=[]\\{}|;':\",./<>?"
        for _ in range(3):
            glitched_text = "".join(
                random.choice(glitch_chars) if random.random() < 0.2 else char
                for char in text
            )
            console.print(f"[bold {NordColors.RED}]{glitched_text}[/]", end="\r")
            time.sleep(0.2)
        console.print(f"[bold {effect.color}]{text}[/]")
    elif effect.name == "Pulsing":
        # Simulate pulsing effect
        for opacity in [100, 70, 40, 70, 100, 70, 40, 70, 100]:
            console.print(
                f"[bold {effect.color} opacity({opacity})]{text}[/]", end="\r"
            )
            time.sleep(0.2)
        console.print(f"[bold {effect.color}]{text}[/]")


def run_demo_mode(text: str) -> None:
    """
    Run a demo mode showing various text effects.

    Args:
        text: The text to use for the demo
    """
    console.print(Align.center(f"[bold {NordColors.FROST_1}]Demo Mode[/]"))
    console.print()

    effects = get_available_effects()

    for effect in effects:
        apply_effect(text, effect)
        time.sleep(1)


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main application function that handles the UI flow and user interaction.
    """
    try:
        console.clear()

        # Display loading animation
        loading_animation(1.5)

        # Display header
        console.print(create_header())

        # Display welcome message
        welcome_text = "Welcome to the Nord-Themed Hello World App!"
        display_spinner_art("Initializing terminal art...", 1.0)
        console.print(Align.center(f"[bold {NordColors.FROST_1}]{welcome_text}[/]"))
        console.print()

        while True:
            # Get user input
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Enter text to display (or press Enter for default, 'd' for demo, 'q' to quit):[/] ",
                end="",
            )
            user_input = input().strip()

            # Handle exit command
            if user_input.lower() in ("q", "quit", "exit"):
                break

            # Handle demo mode
            if user_input.lower() == "d":
                run_demo_mode(DEFAULT_TEXT)
                continue

            # Use default text if no input
            display_text = user_input if user_input else DEFAULT_TEXT

            # Create header with user text
            console.print(create_header(display_text))

            # Show effects options
            effects = get_available_effects()
            console.print(f"\n[bold {NordColors.FROST_3}]Choose an effect:[/]")

            for i, effect in enumerate(effects, 1):
                console.print(
                    f"[{NordColors.FROST_2}]{i}.[/] [{effect.color}]{effect.name}[/] - {effect.description}"
                )

            console.print(
                f"\n[{NordColors.SNOW_STORM_1}]Enter effect number (1-{len(effects)}):[/] ",
                end="",
            )
            effect_choice = input().strip()

            try:
                effect_index = int(effect_choice) - 1
                if 0 <= effect_index < len(effects):
                    apply_effect(display_text, effects[effect_index])
                else:
                    print_message(
                        "Invalid effect number. Please try again.", NordColors.RED, "!"
                    )
            except ValueError:
                # Default to standard effect if invalid input
                apply_effect(display_text, effects[0])

            console.print()

        # Display exit message
        display_spinner_art("Preparing to exit...", 1.0, NordColors.FROST_4)
        console.print(
            Align.center(
                f"[bold {NordColors.GREEN}]Thank you for using the Nord-Themed Hello World App![/]"
            )
        )

    except KeyboardInterrupt:
        print_message("\nOperation cancelled by user", NordColors.YELLOW, "⚠")
        sys.exit(0)
    except Exception as e:
        print_message(f"An error occurred: {str(e)}", NordColors.RED, "✗")
        console.print_exception()
        sys.exit(1)


# ----------------------------------------------------------------
# Program Entry Point
# ----------------------------------------------------------------
if __name__ == "__main__":
    main()
