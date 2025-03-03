#!/usr/bin/env python3
"""
Automated Nord-Themed Hello World
--------------------------------------------------

A streamlined terminal application that automatically displays stylish 'Hello, World!'
messages with a sophisticated Nord dark theme, dynamic ASCII art headers,
and animated terminal effects.

This version runs completely unattended with no user interaction required.
It sequentially demonstrates various text effects using the Nord color palette.

Version: 2.0.0
"""

import atexit
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Callable

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
VERSION: str = "2.0.0"
APP_NAME: str = "Hello World"
APP_SUBTITLE: str = "Nord-Themed Terminal Art"
DEFAULT_TEXT: str = "Hello, World!"
ANIMATION_DURATION: float = 2.0
EFFECT_DURATION: float = 3.0  # How long to show each effect


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
        apply_func: The function that applies this effect
    """

    name: str
    description: str
    color: str
    apply_func: Callable[[str], None]


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
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "standard", "big", "doom"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(text)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails (kept small and tech-looking)
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
 _   _      _ _         __        __         _     _ _ 
| | | | ___| | | ___    \ \      / /__  _ __| | __| | |
| |_| |/ _ \ | |/ _ \    \ \ /\ / / _ \| '__| |/ _` | |
|  _  |  __/ | | (_) |    \ V  V / (_) | |  | | (_| |_|
|_| |_|\___|_|_|\___/      \_/\_/ \___/|_|  |_|\__,_(_)
        """

    # Create a high-tech gradient effect with Nord colors
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

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding
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
        SpinnerColumn("dots", style=f"bold {spinner_style}"),
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


def glitch_effect(text: str) -> None:
    """
    Display text with a glitch effect.

    Args:
        text: The text to apply the glitch effect to
    """
    # Simulate digital glitches
    glitch_chars = "!@#$%^&*()_+-=[]\\{}|;':\",./<>?"
    for i in range(6):  # More glitch iterations
        glitched_text = "".join(
            random.choice(glitch_chars) if random.random() < 0.3 else char
            for char in text
        )
        console.print(f"[bold {NordColors.RED}]{glitched_text}[/]", end="\r")
        time.sleep(0.15)
    console.print(f"[bold {NordColors.RED}]{text}[/]")


def pulsing_effect(text: str) -> None:
    """
    Display text with a pulsing effect.

    Args:
        text: The text to apply the pulsing effect to
    """
    # Improved pulsing effect with more variation
    opacities = [100, 80, 60, 40, 20, 40, 60, 80, 100, 80, 60, 80, 100]
    for opacity in opacities:
        console.print(
            Align.center(f"[bold {NordColors.PURPLE} opacity({opacity})]{text}[/]"),
            end="\r",
        )
        time.sleep(0.15)
    console.print(Align.center(f"[bold {NordColors.PURPLE}]{text}[/]"))


def matrix_effect(text: str) -> None:
    """
    Display text with a matrix-like falling effect.

    Args:
        text: The text to apply the matrix effect to
    """
    lines = []
    for i in range(5):  # Number of animation frames
        line = ""
        for j, char in enumerate(text):
            if char.strip():
                # Gradually reveal characters
                if j <= i * 2:
                    line += f"[bold {NordColors.GREEN}]{char}[/]"
                else:
                    line += " "
            else:
                line += " "
        lines.append(line)

    for line in lines:
        console.print(Align.center(line), end="\r")
        time.sleep(0.2)

    # Final reveal
    console.print(Align.center(f"[bold {NordColors.GREEN}]{text}[/]"))


# ----------------------------------------------------------------
# Effect Registry
# ----------------------------------------------------------------
def get_text_effects() -> List[TextEffect]:
    """
    Get the list of available text effects.

    Returns:
        List of TextEffect objects
    """
    effects = [
        TextEffect(
            name="Standard",
            description="Classic Hello World display",
            color=NordColors.FROST_2,
            apply_func=lambda text: display_message(text, NordColors.FROST_2),
        ),
        TextEffect(
            name="Rainbow",
            description="Colorful text using Nord Aurora colors",
            color=NordColors.YELLOW,
            apply_func=display_rainbow_text,
        ),
        TextEffect(
            name="Typewriter",
            description="Character-by-character animation",
            color=NordColors.GREEN,
            apply_func=typewriter_effect,
        ),
        TextEffect(
            name="Glitch",
            description="Text with simulated digital glitches",
            color=NordColors.RED,
            apply_func=glitch_effect,
        ),
        TextEffect(
            name="Pulsing",
            description="Text that pulses with changing intensity",
            color=NordColors.PURPLE,
            apply_func=pulsing_effect,
        ),
        TextEffect(
            name="Matrix",
            description="Matrix-inspired falling character effect",
            color=NordColors.GREEN,
            apply_func=matrix_effect,
        ),
    ]
    return effects


# ----------------------------------------------------------------
# Main Application Functions
# ----------------------------------------------------------------
def demonstrate_effects(text: str) -> None:
    """
    Automatically demonstrate all available text effects.

    Args:
        text: The text to display with various effects
    """
    effects = get_text_effects()

    for effect in effects:
        # Display effect info
        console.print(f"\n[bold {effect.color}]Demonstrating: {effect.name}[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]{effect.description}[/]")

        # Apply the effect
        with Progress(
            SpinnerColumn("dots", style=f"bold {effect.color}"),
            TextColumn(
                f"[{NordColors.SNOW_STORM_1}]Applying {effect.name} effect...[/]"
            ),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            time.sleep(0.7)  # Brief delay before showing effect

        # Show the effect
        effect.apply_func(text)

        # Pause between effects
        time.sleep(EFFECT_DURATION)


# ----------------------------------------------------------------
# Main Application Loop
# ----------------------------------------------------------------
def main() -> None:
    """
    Main application function that handles the automated flow.
    """
    try:
        console.clear()

        # Initial loading animation
        loading_animation(1.5)

        # Display header with app name
        console.print(create_header())

        # Display welcome message with spinner
        display_spinner_art(
            "Initializing terminal art presentation...", 1.5, NordColors.FROST_1
        )

        # Welcome panel
        welcome_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.SNOW_STORM_1}]Welcome to the Automated Nord-Themed Hello World App![/]"
            ),
            border_style=Style(color=NordColors.FROST_2),
            padding=(1, 2),
        )
        console.print(welcome_panel)

        # Display sequence progress
        with Progress(
            TextColumn(f"[bold {NordColors.FROST_3}]Preparing demonstration sequence"),
            BarColumn(
                bar_width=40,
                style=NordColors.POLAR_NIGHT_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
            console=console,
        ) as progress:
            demo_task = progress.add_task("Preparing", total=100)
            for i in range(100):
                time.sleep(0.01)
                progress.update(demo_task, completed=i + 1)

        console.print()
        console.print(
            Align.center(
                f"[bold {NordColors.FROST_2}]Automatic demonstration of text effects[/]"
            )
        )
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Each effect will be shown for {EFFECT_DURATION} seconds[/]"
            )
        )
        console.print()

        # Demonstrate the header with custom text
        console.print(f"[bold {NordColors.FROST_3}]Custom Header Demonstration:[/]")
        console.print(create_header(DEFAULT_TEXT))
        time.sleep(EFFECT_DURATION)

        # Run the effect demonstrations
        demonstrate_effects(DEFAULT_TEXT)

        # Final loading and exit
        display_spinner_art("Finalizing demonstration...", 1.0, NordColors.FROST_4)

        # Exit message
        farewell_panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]Thank you for using the Automated Nord-Themed Hello World App![/]"
            ),
            border_style=Style(color=NordColors.GREEN),
            padding=(1, 2),
        )
        console.print(farewell_panel)

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
