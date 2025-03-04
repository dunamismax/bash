#!/usr/bin/env python3
"""
Automated Nord-Themed Hello World
--------------------------------------------------

A streamlined terminal application that automatically displays a stylish
'Hello, World!' demonstration using dynamic ASCII art headers, animated
text effects, and real-time progress indicators. All actions run unattended.

Version: 2.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, List

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
# Configuration & Constants
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

    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"

    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"

    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"

    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"


# Create a Rich Console with no additional theme (colors come from our palette)
console: Console = Console(highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class TextEffect:
    """
    Represents a text effect with display properties.

    Attributes:
        name: The name of the effect.
        description: A brief description of what the effect does.
        color: The Nord color to use for this effect.
        apply_func: Function that applies this effect to the text.
    """

    name: str
    description: str
    color: str
    apply_func: Callable[[str], None]


# ----------------------------------------------------------------
# Fallback ASCII Art Configuration
# ----------------------------------------------------------------
# Define your fallback ASCII art here.
# To customize, just replace the text within the triple quotes below.
FALLBACK_ASCII_ART = r"""
 _          _ _                            _     _ _ 
| |__   ___| | | ___   __      _____  _ __| | __| | |
| '_ \ / _ \ | |/ _ \  \ \ /\ / / _ \| '__| |/ _` | |
| | | |  __/ | | (_) |  \ V  V / (_) | |  | | (_| |_|
|_| |_|\___|_|_|\___/    \_/\_/ \___/|_|  |_|\__,_(_)
"""


# ----------------------------------------------------------------
# Console and UI Helper Functions
# ----------------------------------------------------------------
def create_header(text: str = APP_NAME) -> Panel:
    """
    Create a dynamic ASCII art header with Nord-themed styling.

    Args:
        text: The text to render as ASCII art.

    Returns:
        A Rich Panel containing the styled header.
    """
    compact_fonts = ["slant", "small", "standard", "big", "doom"]
    ascii_art = ""
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)
            ascii_art = fig.renderText(text)
            if ascii_art.strip():
                break
        except Exception:
            continue

    # If ascii_art is empty, use the fallback ASCII art defined above.
    if not ascii_art.strip():
        ascii_art = FALLBACK_ASCII_ART

    # Create a gradient effect using selected Nord Frost colors.
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_art.splitlines()):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = f"{tech_border}\n{styled_text}{tech_border}"
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


def display_spinner(
    message: str, duration: float, style: str = NordColors.FROST_2
) -> None:
    """
    Display a Rich spinner with a message for a set duration.

    Args:
        message: The message to display.
        duration: Duration in seconds.
        style: The color style for the spinner.
    """
    with Progress(
        SpinnerColumn("dots", style=f"bold {style}"),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{message}[/]"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(0.1)


def display_panel(message: str, style: str = NordColors.FROST_2) -> None:
    """
    Display a message in a styled Rich panel.

    Args:
        message: The message to display.
        style: The border and text style.
    """
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
    )
    console.print(panel)


def print_log(message: str, style: str = NordColors.FROST_2, prefix: str = "•") -> None:
    """
    Print a log message with styling.

    Args:
        message: The message to print.
        style: The text style.
        prefix: A prefix symbol.
    """
    console.print(f"[{style}]{prefix} {message}[/{style}]")


# ----------------------------------------------------------------
# Animation and Visual Effects
# ----------------------------------------------------------------
def loading_animation(duration: float = ANIMATION_DURATION) -> None:
    """
    Display a loading bar animation.

    Args:
        duration: Duration in seconds for the animation.
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
    Display text with a rainbow effect using Nord accent colors.

    Args:
        text: The text to display.
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
            rainbow_text += f"[bold {colors[i % len(colors)]}]{char}[/]"
        else:
            rainbow_text += " "
    console.print(Align.center(rainbow_text))


def typewriter_effect(text: str, delay: float = 0.05) -> None:
    """
    Display text with a typewriter effect.

    Args:
        text: The text to display.
        delay: Delay between characters.
    """
    output = ""
    for char in text:
        output += char
        console.print(Align.center(output), end="\r")
        time.sleep(delay)
    console.print(Align.center(text))


def glitch_effect(text: str) -> None:
    """
    Display text with a simulated glitch effect.

    Args:
        text: The text to display.
    """
    glitch_chars = "!@#$%^&*()_+-=[]\\{}|;':\",./<>?"
    for _ in range(6):
        glitched = "".join(
            random.choice(glitch_chars) if random.random() < 0.3 else char
            for char in text
        )
        console.print(Align.center(f"[bold {NordColors.RED}]{glitched}[/]"), end="\r")
        time.sleep(0.15)
    console.print(Align.center(f"[bold {NordColors.RED}]{text}[/]"))


def pulsing_effect(text: str) -> None:
    """
    Display text with a pulsing effect.

    Args:
        text: The text to display.
    """
    opacities = [100, 80, 60, 40, 20, 40, 60, 80, 100]
    for opacity in opacities:
        # Note: Rich does not support dynamic opacity,
        # so we simulate pulsing by printing repeatedly.
        console.print(Align.center(f"[bold {NordColors.PURPLE}]{text}[/]"), end="\r")
        time.sleep(0.15)
    console.print(Align.center(f"[bold {NordColors.PURPLE}]{text}[/]"))


def matrix_effect(text: str) -> None:
    """
    Display text with a Matrix-inspired falling effect.

    Args:
        text: The text to display.
    """
    frames = []
    for i in range(5):
        frame = ""
        for j, char in enumerate(text):
            if char.strip():
                frame += f"[bold {NordColors.GREEN}]{char}[/]" if j <= i * 2 else " "
            else:
                frame += " "
        frames.append(frame)
    for frame in frames:
        console.print(Align.center(frame), end="\r")
        time.sleep(0.2)
    console.print(Align.center(f"[bold {NordColors.GREEN}]{text}[/]"))


# ----------------------------------------------------------------
# Effect Registry
# ----------------------------------------------------------------
def get_text_effects() -> List[TextEffect]:
    """
    Retrieve the list of text effects to demonstrate.

    Returns:
        A list of TextEffect objects.
    """
    return [
        TextEffect(
            "Standard",
            "Classic display",
            NordColors.FROST_2,
            lambda text: display_panel(text, NordColors.FROST_2),
        ),
        TextEffect(
            "Rainbow",
            "Colorful text with Nord accents",
            NordColors.YELLOW,
            display_rainbow_text,
        ),
        TextEffect(
            "Typewriter",
            "Character-by-character animation",
            NordColors.GREEN,
            typewriter_effect,
        ),
        TextEffect(
            "Glitch", "Simulated digital glitches", NordColors.RED, glitch_effect
        ),
        TextEffect(
            "Pulsing", "Pulsing intensity effect", NordColors.PURPLE, pulsing_effect
        ),
        TextEffect(
            "Matrix", "Matrix-inspired falling effect", NordColors.GREEN, matrix_effect
        ),
    ]


def demonstrate_effects(text: str) -> None:
    """
    Sequentially demonstrate all available text effects.

    Args:
        text: The text to apply effects to.
    """
    effects = get_text_effects()
    for effect in effects:
        console.print(f"\n[bold {effect.color}]Demonstrating: {effect.name}[/]")
        console.print(f"[{NordColors.SNOW_STORM_1}]{effect.description}[/]")
        with Progress(
            SpinnerColumn("dots", style=f"bold {effect.color}"),
            TextColumn(
                f"[{NordColors.SNOW_STORM_1}]Applying {effect.name} effect...[/]"
            ),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            time.sleep(0.7)
        effect.apply_func(text)
        time.sleep(EFFECT_DURATION)


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_log("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle termination signals gracefully.

    Args:
        sig: Signal number.
        frame: Current stack frame.
    """
    sig_name = signal.Signals(sig).name
    print_log(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Application Flow
# ----------------------------------------------------------------
def main() -> None:
    """
    Main function that runs the automated demonstration sequence.
    """
    try:
        console.clear()
        # Initial animations and header display
        loading_animation(1.5)
        console.print(create_header())
        display_spinner(
            "Initializing terminal art presentation...", 1.5, NordColors.FROST_1
        )

        # Welcome message
        welcome = (
            "[bold {0}]Welcome to the Automated Nord-Themed Hello World App![/]".format(
                NordColors.SNOW_STORM_1
            )
        )
        display_panel(welcome, NordColors.FROST_2)

        # Preparation progress bar
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
            task = progress.add_task("Preparing", total=100)
            for i in range(100):
                time.sleep(0.01)
                progress.update(task, completed=i + 1)

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

        # Demonstrate header with custom text and run text effects
        console.print(f"[bold {NordColors.FROST_3}]Custom Header Demonstration:[/]")
        console.print(create_header(DEFAULT_TEXT))
        time.sleep(EFFECT_DURATION)
        demonstrate_effects(DEFAULT_TEXT)

        # Finalize demonstration
        display_spinner("Finalizing demonstration...", 1.0, NordColors.FROST_4)
        farewell = "[bold {0}]Thank you for using the Automated Nord-Themed Hello World App![/]".format(
            NordColors.GREEN
        )
        display_panel(farewell, NordColors.GREEN)
    except KeyboardInterrupt:
        print_log("Operation cancelled by user", NordColors.YELLOW, "⚠")
        sys.exit(0)
    except Exception as e:
        print_log(f"An error occurred: {str(e)}", NordColors.RED, "✗")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
