#!/usr/bin/env python3
"""
Media Conversion Toolkit
--------------------------------------------------
A fully interactive, menu-driven toolkit for performing
media file conversion, remuxing, and audio extraction
operations with a production-grade, polished CLI that
integrates prompt_toolkit for auto-completion, Rich for
stylish output, and Pyfiglet for dynamic ASCII banners.

Features:
  • Interactive, menu-driven interface with dynamic ASCII banners.
  • Conversion operations including video transcoding, audio extraction,
    remuxing, subtitle management, and batch processing.
  • Intelligent format detection and codec selection.
  • Comprehensive format support via FFmpeg backend.
  • Real-time progress tracking with elegant spinners during conversions.
  • Enhanced path auto-completion with trailing slashes for directories.
  • Robust error handling and cross-platform compatibility.
  • Nord-themed color styling throughout the application.

This script is adapted for Fedora Linux.
Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import atexit
import os
import sys
import time
import socket
import getpass
import platform
import signal
import subprocess
import shutil
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, Set, Union
from pathlib import Path


# Function to install dependencies for non-root user when script is run with sudo
def install_dependencies():
    """Install required dependencies for the non-root user when run with sudo."""
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "ffmpeg-python"]

    user = os.environ.get("SUDO_USER", os.environ.get("USER", getpass.getuser()))
    if os.geteuid() != 0:
        print(f"Installing dependencies for user: {user}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user"] + required_packages
        )
        return

    print(f"Running as sudo. Installing dependencies for user: {user}")
    real_user_home = os.path.expanduser(f"~{user}")
    try:
        subprocess.check_call(
            ["sudo", "-u", user, sys.executable, "-m", "pip", "install", "--user"]
            + required_packages
        )
        print(f"Successfully installed dependencies for user: {user}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


# Function to check if ffmpeg is installed and install it if it's not
def check_ffmpeg():
    """Check if ffmpeg is installed and install it if not."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("FFmpeg not found. Installing FFmpeg...")
        try:
            if platform.system() == "Linux":
                # Check for Fedora first
                if os.path.exists("/usr/bin/dnf"):
                    # Use DNF on Fedora
                    if os.geteuid() == 0:
                        subprocess.check_call(["dnf", "install", "-y", "ffmpeg"])
                    else:
                        subprocess.check_call(
                            ["sudo", "dnf", "install", "-y", "ffmpeg"]
                        )
                # Then check for nala (PopOS or other Debian derivatives)
                elif os.path.exists("/usr/bin/nala"):
                    if os.geteuid() == 0:
                        subprocess.check_call(["nala", "update"])
                        subprocess.check_call(["nala", "install", "-y", "ffmpeg"])
                    else:
                        subprocess.check_call(["sudo", "nala", "update"])
                        subprocess.check_call(
                            ["sudo", "nala", "install", "-y", "ffmpeg"]
                        )
                else:
                    # Fallback to apt or other package managers
                    if os.path.exists("/usr/bin/apt"):
                        if os.geteuid() == 0:
                            subprocess.check_call(["apt", "update"])
                            subprocess.check_call(["apt", "install", "-y", "ffmpeg"])
                        else:
                            subprocess.check_call(["sudo", "apt", "update"])
                            subprocess.check_call(
                                ["sudo", "apt", "install", "-y", "ffmpeg"]
                            )
                    else:
                        print(
                            "No supported package manager found. Please install FFmpeg manually."
                        )
                        return False
            elif platform.system() == "Darwin":  # macOS
                subprocess.check_call(["brew", "install", "ffmpeg"])
            else:
                print("Please install FFmpeg manually for your system.")
                return False
            print("FFmpeg installed successfully!")
            return True
        except subprocess.SubprocessError as e:
            print(f"Failed to install FFmpeg: {e}")
            print("Please install FFmpeg manually using your system's package manager.")
            return False


try:
    import ffmpeg
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
        DownloadColumn,
        FileSizeColumn,
        TransferSpeedColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.columns import Columns
    from rich.traceback import install as install_rich_traceback
    from rich.markup import escape
    from rich.live import Live
    from rich.tree import Tree

    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import PathCompleter, Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style as PtStyle
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.document import Document
    from prompt_toolkit.completion import CompleteEvent

except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        if os.geteuid() != 0:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--user",
                    "rich",
                    "pyfiglet",
                    "prompt_toolkit",
                    "ffmpeg-python",
                ]
            )
        else:
            install_dependencies()

        print("Dependencies installed successfully. Checking for FFmpeg...")
        check_ffmpeg()

        print("Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print("Please install the required packages manually:")
        print("pip install rich pyfiglet prompt_toolkit ffmpeg-python")
        print("Also ensure FFmpeg is installed on your system.")
        sys.exit(1)

if not check_ffmpeg():
    print("Warning: FFmpeg is required but could not be installed automatically.")
    print("The script will continue, but functionality may be limited.")

install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
HOSTNAME: str = socket.gethostname()
DEFAULT_USERNAME: str = (
    os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
)
VERSION: str = "1.0.0"
APP_NAME: str = "Media Conversion Toolkit"
APP_SUBTITLE: str = "Advanced FFmpeg Frontend for Fedora"

if os.environ.get("SUDO_USER"):
    DEFAULT_INPUT_FOLDER = os.path.expanduser(
        f"~{os.environ.get('SUDO_USER')}/Downloads"
    )
    DEFAULT_OUTPUT_FOLDER = os.path.expanduser(
        f"~{os.environ.get('SUDO_USER')}/Downloads/Converted"
    )
else:
    DEFAULT_INPUT_FOLDER = os.path.expanduser("~/Downloads")
    DEFAULT_OUTPUT_FOLDER = os.path.expanduser("~/Downloads/Converted")

# Create output directory if it doesn't exist
os.makedirs(DEFAULT_OUTPUT_FOLDER, exist_ok=True)

HISTORY_DIR = os.path.expanduser(
    f"~{os.environ.get('SUDO_USER', DEFAULT_USERNAME)}/.media_converter"
)
os.makedirs(HISTORY_DIR, exist_ok=True)
COMMAND_HISTORY = os.path.join(HISTORY_DIR, "command_history")
PATH_HISTORY = os.path.join(HISTORY_DIR, "path_history")
CONFIG_FILE = os.path.join(HISTORY_DIR, "config.json")
for history_file in [COMMAND_HISTORY, PATH_HISTORY]:
    if not os.path.exists(history_file):
        with open(history_file, "w") as f:
            pass

# ----------------------------------------------------------------
# Format Definitions
# ----------------------------------------------------------------

# Video Containers
VIDEO_CONTAINERS = {
    "mp4": "MPEG-4 Part 14 (.mp4)",
    "mkv": "Matroska (.mkv)",
    "avi": "Audio Video Interleave (.avi)",
    "mov": "QuickTime (.mov)",
    "webm": "WebM (.webm)",
    "flv": "Flash Video (.flv)",
    "wmv": "Windows Media Video (.wmv)",
    "m4v": "MPEG-4 Video (.m4v)",
    "ts": "MPEG Transport Stream (.ts)",
    "mts": "AVCHD (.mts)",
    "m2ts": "Blu-ray BDAV (.m2ts)",
    "3gp": "3GPP (.3gp)",
    "ogv": "Ogg Video (.ogv)",
    "asf": "Advanced Systems Format (.asf)",
    "vob": "DVD Video Object (.vob)",
    "divx": "DivX (.divx)",
    "mpg": "MPEG-1/2 (.mpg)",
    "mpeg": "MPEG-1/2 (.mpeg)",
}

# Audio Containers
AUDIO_CONTAINERS = {
    "mp3": "MPEG Audio Layer III (.mp3)",
    "aac": "Advanced Audio Coding (.aac)",
    "flac": "Free Lossless Audio Codec (.flac)",
    "wav": "Waveform Audio (.wav)",
    "ogg": "Ogg Vorbis (.ogg)",
    "m4a": "MPEG-4 Audio (.m4a)",
    "wma": "Windows Media Audio (.wma)",
    "opus": "Opus (.opus)",
    "alac": "Apple Lossless Audio Codec (.alac)",
    "aiff": "Audio Interchange File Format (.aiff)",
    "ac3": "Dolby Digital (.ac3)",
    "dts": "DTS Coherent Acoustics (.dts)",
    "amr": "Adaptive Multi-Rate (.amr)",
    "ape": "Monkey's Audio (.ape)",
    "mka": "Matroska Audio (.mka)",
    "pcm": "Pulse Code Modulation (.pcm)",
    "tta": "True Audio (.tta)",
    "ra": "RealAudio (.ra)",
}

# Video Codecs
VIDEO_CODECS = {
    "h264": "H.264 / AVC",
    "h265": "H.265 / HEVC",
    "vp9": "VP9",
    "av1": "AV1",
    "mpeg2": "MPEG-2",
    "mpeg4": "MPEG-4 Part 2",
    "vp8": "VP8",
    "theora": "Theora",
    "prores": "Apple ProRes",
    "mjpeg": "Motion JPEG",
    "vc1": "VC-1",
    "dnxhd": "DNxHD",
    "gif": "GIF",
}

# Audio Codecs
AUDIO_CODECS = {
    "aac": "Advanced Audio Coding",
    "mp3": "MP3 (MPEG Layer 3)",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "flac": "FLAC (Free Lossless Audio Codec)",
    "alac": "ALAC (Apple Lossless)",
    "pcm_s16le": "PCM 16-bit",
    "pcm_s24le": "PCM 24-bit",
    "pcm_s32le": "PCM 32-bit",
    "ac3": "Dolby Digital (AC-3)",
    "eac3": "Dolby Digital Plus (E-AC-3)",
    "dts": "DTS",
    "truehd": "Dolby TrueHD",
    "wma": "Windows Media Audio",
}

# Common Presets
PRESETS = {
    "ultrafast": "Ultrafast (lowest quality, fastest)",
    "superfast": "Superfast",
    "veryfast": "Very Fast",
    "faster": "Faster",
    "fast": "Fast",
    "medium": "Medium (balanced)",
    "slow": "Slow",
    "slower": "Slower",
    "veryslow": "Very Slow (highest quality, slowest)",
}

# Video Quality Presets (CRF values for H.264)
VIDEO_QUALITY = {
    "0": "Lossless",
    "18": "Visually Lossless (High Quality)",
    "23": "Default (Good Quality)",
    "28": "Standard (Medium Quality)",
    "32": "Low Quality",
}

# Audio Quality Presets
AUDIO_QUALITY = {
    "16": "Very Low (16 kbps)",
    "32": "Low (32 kbps)",
    "64": "Medium Low (64 kbps)",
    "96": "Medium (96 kbps)",
    "128": "Standard (128 kbps)",
    "192": "High (192 kbps)",
    "256": "Very High (256 kbps)",
    "320": "Extreme (320 kbps)",
}

# Extensions to format types mapping
EXTENSION_TO_TYPE = {
    **{ext: "video" for ext in VIDEO_CONTAINERS},
    **{ext: "audio" for ext in AUDIO_CONTAINERS},
    "srt": "subtitle",
    "sub": "subtitle",
    "ass": "subtitle",
    "ssa": "subtitle",
    "vtt": "subtitle",
}


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
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


console: Console = Console()


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class MediaFile:
    """
    Represents a media file with its properties
    """

    path: str
    file_type: str = "unknown"  # video, audio, subtitle
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    bitrate: int = 0
    size_bytes: int = 0

    def get_file_info(self) -> str:
        """Returns a formatted description of the file."""
        info = []
        if self.file_type != "unknown":
            info.append(f"Type: {self.file_type.capitalize()}")

        if self.container:
            info.append(f"Container: {self.container}")

        if self.video_codec and self.file_type == "video":
            info.append(f"Video: {self.video_codec}")
            if self.width and self.height:
                info.append(f"Resolution: {self.width}x{self.height}")

        if self.audio_codec:
            info.append(f"Audio: {self.audio_codec}")

        if self.duration > 0:
            mins, secs = divmod(self.duration, 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                info.append(f"Duration: {int(hours)}:{int(mins):02d}:{int(secs):02d}")
            else:
                info.append(f"Duration: {int(mins):02d}:{int(secs):02d}")

        if self.bitrate > 0:
            info.append(f"Bitrate: {self.bitrate / 1000:.0f} kbps")

        if self.size_bytes > 0:
            size_mb = self.size_bytes / (1024 * 1024)
            if size_mb < 1000:
                info.append(f"Size: {size_mb:.2f} MB")
            else:
                info.append(f"Size: {size_mb / 1024:.2f} GB")

        return " | ".join(info)


@dataclass
class ConversionJob:
    """
    Represents a file conversion job
    """

    input_file: MediaFile
    output_path: str
    output_format: str
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    video_quality: Optional[str] = None
    audio_quality: Optional[str] = None
    preset: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    extract_audio: bool = False
    extract_subtitles: bool = False
    remux_only: bool = False
    additional_options: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0
    error_message: Optional[str] = None


@dataclass
class Config:
    """
    Application configuration
    """

    default_input_dir: str = DEFAULT_INPUT_FOLDER
    default_output_dir: str = DEFAULT_OUTPUT_FOLDER
    default_video_codec: str = "h264"
    default_audio_codec: str = "aac"
    default_video_quality: str = "23"
    default_audio_quality: str = "128"
    default_preset: str = "medium"
    recent_files: List[str] = field(default_factory=list)
    recent_outputs: List[str] = field(default_factory=list)
    favorite_formats: List[str] = field(default_factory=list)

    def save(self):
        """Save config to file"""
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {
                    "default_input_dir": self.default_input_dir,
                    "default_output_dir": self.default_output_dir,
                    "default_video_codec": self.default_video_codec,
                    "default_audio_codec": self.default_audio_codec,
                    "default_video_quality": self.default_video_quality,
                    "default_audio_quality": self.default_audio_quality,
                    "default_preset": self.default_preset,
                    "recent_files": self.recent_files[-10:],  # Keep only last 10
                    "recent_outputs": self.recent_outputs[-10:],  # Keep only last 10
                    "favorite_formats": self.favorite_formats,
                },
                f,
                indent=2,
            )

    @classmethod
    def load(cls):
        """Load config from file"""
        if not os.path.exists(CONFIG_FILE):
            return cls()

        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return cls(
                    default_input_dir=data.get(
                        "default_input_dir", DEFAULT_INPUT_FOLDER
                    ),
                    default_output_dir=data.get(
                        "default_output_dir", DEFAULT_OUTPUT_FOLDER
                    ),
                    default_video_codec=data.get("default_video_codec", "h264"),
                    default_audio_codec=data.get("default_audio_codec", "aac"),
                    default_video_quality=data.get("default_video_quality", "23"),
                    default_audio_quality=data.get("default_audio_quality", "128"),
                    default_preset=data.get("default_preset", "medium"),
                    recent_files=data.get("recent_files", []),
                    recent_outputs=data.get("recent_outputs", []),
                    favorite_formats=data.get("favorite_formats", []),
                )
        except Exception as e:
            console.print(
                f"[bold {NordColors.YELLOW}]Warning: Failed to load config: {e}[/]"
            )
            return cls()


# Global configuration
config = Config.load()


# ----------------------------------------------------------------
# Enhanced Spinner Progress Manager
# ----------------------------------------------------------------
class SpinnerProgressManager:
    """Manages Rich spinners with consistent styling and features."""

    def __init__(self, title: str = "", auto_refresh: bool = True):
        self.title = title
        self.progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
            TextColumn("[{task.fields[status]}]"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            auto_refresh=auto_refresh,
            console=console,
        )
        self.live = None
        self.tasks = {}
        self.start_times = {}
        self.total_sizes = {}
        self.completed_sizes = {}
        self.is_started = False

    def start(self):
        """Start the progress display."""
        if not self.is_started:
            self.live = Live(self.progress, console=console, refresh_per_second=10)
            self.live.start()
            self.is_started = True

    def stop(self):
        """Stop the progress display."""
        if self.is_started and self.live:
            self.live.stop()
            self.is_started = False

    def add_task(self, description: str, total_size: Optional[int] = None) -> str:
        """Add a new task with a unique ID."""
        task_id = f"task_{len(self.tasks)}"
        self.start_times[task_id] = time.time()

        if total_size is not None:
            self.total_sizes[task_id] = total_size
            self.completed_sizes[task_id] = 0

        self.tasks[task_id] = self.progress.add_task(
            description,
            status=f"[{NordColors.FROST_3}]Starting...",
            eta="Calculating...",
            total=100,
        )
        return task_id

    def update_task(self, task_id: str, status: str, completed: Optional[int] = None):
        """Update a task's status and progress."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        self.progress.update(task, status=status)

        if completed is not None and task_id in self.total_sizes:
            self.completed_sizes[task_id] = completed
            percentage = min(100, int(100 * completed / self.total_sizes[task_id]))
            self.progress.update(task, completed=percentage)

            # Calculate ETA
            elapsed = time.time() - self.start_times[task_id]
            if percentage > 0:
                total_time = elapsed * 100 / percentage
                remaining = total_time - elapsed
                eta_str = f"[{NordColors.FROST_4}]ETA: {format_time(remaining)}"

                # Show transfer speed
                if elapsed > 0:
                    speed = completed / elapsed
                    speed_str = format_bytes(speed) + "/s"
                    eta_str += f" • {speed_str}"
            else:
                eta_str = f"[{NordColors.FROST_4}]Calculating..."

            # Format status with percentage
            status_with_percentage = (
                f"[{NordColors.FROST_3}]{status} [{NordColors.GREEN}]{percentage}%[/]"
            )
            self.progress.update(task, status=status_with_percentage, eta=eta_str)
        elif completed is not None:
            # Update the progress bar when we have a percentage
            self.progress.update(task, completed=min(100, completed))

    def complete_task(self, task_id: str, success: bool = True):
        """Mark a task as complete with success or failure indication."""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        status_color = NordColors.GREEN if success else NordColors.RED
        status_text = "COMPLETED" if success else "FAILED"

        if task_id in self.total_sizes:
            self.completed_sizes[task_id] = self.total_sizes[task_id]
            self.progress.update(task, completed=100)

        elapsed = time.time() - self.start_times[task_id]
        elapsed_str = format_time(elapsed)

        status_msg = f"[bold {status_color}]{status_text}[/] in {elapsed_str}"
        if task_id in self.total_sizes and success:
            speed = self.total_sizes[task_id] / max(elapsed, 0.1)
            speed_str = format_bytes(speed) + "/s"
            status_msg += f" • {speed_str}"

        self.progress.update(task, status=status_msg)


# ----------------------------------------------------------------
# Custom Path Completer with Trailing Slashes
# ----------------------------------------------------------------
class EnhancedPathCompleter(PathCompleter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if os.path.isdir(os.path.expanduser(text)):
            # If we're already at a directory but missing the trailing slash,
            # add the trailing slash as the only completion
            if not text.endswith("/"):
                dir_with_slash = text + "/"
                yield Completion(
                    dir_with_slash,
                    start_position=-len(text),
                    style=f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.GREEN}",
                )
                return

        # Get the normal completions from parent class
        completions = list(super().get_completions(document, complete_event))
        for completion in completions:
            # Get the full path by combining input and completion
            if text.endswith("/"):
                full_path = os.path.expanduser(text + completion.text)
            else:
                last_slash_index = text.rfind("/")
                if last_slash_index < 0:
                    full_path = os.path.expanduser(completion.text)
                else:
                    dir_part = text[: last_slash_index + 1]
                    full_path = os.path.expanduser(dir_part + completion.text)

            # Check if it's a directory
            if os.path.isdir(full_path) and not completion.text.endswith("/"):
                # Replace completion with one that has trailing slash
                yield Completion(
                    completion.text + "/",
                    start_position=completion.start_position,
                    style=f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.GREEN}",
                )
            else:
                # For files, use different color based on file type
                extension = os.path.splitext(full_path)[1].lower().lstrip(".")
                if extension in VIDEO_CONTAINERS:
                    style = f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.FROST_2}"
                elif extension in AUDIO_CONTAINERS:
                    style = f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.FROST_4}"
                else:
                    style = (
                        f"bg:{NordColors.POLAR_NIGHT_2} fg:{NordColors.SNOW_STORM_1}"
                    )

                yield Completion(
                    completion.text,
                    start_position=completion.start_position,
                    style=style,
                )


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def format_bytes(size: float) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_time(seconds: float) -> str:
    """Format seconds to human-readable time string."""
    if seconds < 1:
        return "less than a second"
    elif seconds < 60:
        return f"{seconds:.1f}s"

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds)}s"

    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)
    fonts = ["slant", "big", "digital", "standard", "small"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=adjusted_width)
            ascii_art = fig.renderText(APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_4,
    ]
    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"
    border = f"[{NordColors.FROST_3}]{'━' * (adjusted_width - 6)}[/]"
    styled_text = border + "\n" + styled_text + border
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


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


def show_help() -> None:
    help_text = f"""
[bold]Available Commands:[/]

[bold {NordColors.FROST_2}]1-9, 0[/]:      Menu selection numbers
[bold {NordColors.FROST_2}]Tab[/]:         Auto-complete file paths with trailing slashes for directories
[bold {NordColors.FROST_2}]Up/Down[/]:     Navigate command history
[bold {NordColors.FROST_2}]Ctrl+C[/]:      Cancel current operation
[bold {NordColors.FROST_2}]h[/]:           Show this help screen

[bold]Supported Formats:[/]

[bold {NordColors.FROST_3}]Video containers[/]: {", ".join(sorted(VIDEO_CONTAINERS.keys()))}
[bold {NordColors.FROST_3}]Audio containers[/]: {", ".join(sorted(AUDIO_CONTAINERS.keys()))}
[bold {NordColors.FROST_3}]Video codecs[/]: {", ".join(sorted(VIDEO_CODECS.keys()))}
[bold {NordColors.FROST_3}]Audio codecs[/]: {", ".join(sorted(AUDIO_CODECS.keys()))}
"""
    console.print(
        Panel(
            Text.from_markup(help_text),
            title=f"[bold {NordColors.FROST_1}]Help & Commands[/]",
            border_style=Style(color=NordColors.FROST_3),
            padding=(1, 2),
        )
    )


def get_prompt_style() -> PtStyle:
    return PtStyle.from_dict({"prompt": f"bold {NordColors.PURPLE}"})


def wait_for_key() -> None:
    pt_prompt(
        "Press Enter to continue...",
        style=PtStyle.from_dict({"prompt": f"{NordColors.FROST_2}"}),
    )


def display_status_bar() -> None:
    ffmpeg_version = "Unknown"
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        match = re.search(r"ffmpeg version (\S+)", result.stdout)
        if match:
            ffmpeg_version = match.group(1)
    except Exception:
        pass

    console.print(
        Panel(
            Text.from_markup(
                f"[bold {NordColors.GREEN}]FFmpeg Version: {ffmpeg_version}[/] | "
                f"[dim]Default Output: {config.default_output_dir}[/]"
            ),
            border_style=NordColors.FROST_4,
            padding=(0, 2),
        )
    )


# ----------------------------------------------------------------
# Media Analysis Functions
# ----------------------------------------------------------------
def analyze_media_file(file_path: str) -> MediaFile:
    """
    Analyze a media file and return its properties
    """
    try:
        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            print_error(f"File not found: {file_path}")
            return MediaFile(path=file_path)

        size_bytes = os.path.getsize(file_path)

        # Get file extension and determine type
        _, ext = os.path.splitext(file_path.lower())
        ext = ext.lstrip(".")
        file_type = EXTENSION_TO_TYPE.get(ext, "unknown")

        try:
            # Use ffprobe to get media info
            probe = ffmpeg.probe(file_path)

            # Initialize media file with basic info
            media_file = MediaFile(
                path=file_path,
                file_type=file_type,
                container=ext,
                size_bytes=size_bytes,
            )

            # Get stream info
            if "format" in probe and "duration" in probe["format"]:
                media_file.duration = float(probe["format"]["duration"])

            if "format" in probe and "bit_rate" in probe["format"]:
                try:
                    media_file.bitrate = int(probe["format"]["bit_rate"])
                except ValueError:
                    pass

            for stream in probe.get("streams", []):
                codec_type = stream.get("codec_type", "")

                if codec_type == "video":
                    media_file.video_codec = stream.get("codec_name", "")
                    media_file.width = stream.get("width", 0)
                    media_file.height = stream.get("height", 0)

                elif codec_type == "audio":
                    media_file.audio_codec = stream.get("codec_name", "")

            return media_file

        except ffmpeg.Error as e:
            console.print(
                f"[bold {NordColors.RED}]Error analyzing file: {e.stderr.decode() if e.stderr else str(e)}[/]"
            )
            return MediaFile(path=file_path, file_type=file_type, size_bytes=size_bytes)

    except Exception as e:
        console.print(
            f"[bold {NordColors.RED}]Unexpected error analyzing file: {str(e)}[/]"
        )
        return MediaFile(path=file_path)


def get_optimal_output_settings(
    input_file: MediaFile, output_format: str
) -> Dict[str, Any]:
    """
    Determine optimal conversion settings based on input file and desired output format
    """
    settings = {
        "video_codec": config.default_video_codec,
        "audio_codec": config.default_audio_codec,
        "video_quality": config.default_video_quality,
        "audio_quality": config.default_audio_quality,
        "preset": config.default_preset,
    }

    # Adjust video codec based on output format
    if output_format in VIDEO_CONTAINERS:
        if output_format == "mp4":
            settings["video_codec"] = "h264"
            settings["audio_codec"] = "aac"
        elif output_format == "mkv":
            settings["video_codec"] = "h264"
            settings["audio_codec"] = "aac"
        elif output_format == "webm":
            settings["video_codec"] = "vp9"
            settings["audio_codec"] = "opus"
        elif output_format == "avi":
            settings["video_codec"] = "mpeg4"
            settings["audio_codec"] = "mp3"

    # Adjust audio codec based on output format
    elif output_format in AUDIO_CONTAINERS:
        settings["video_codec"] = None  # No video for audio-only outputs
        if output_format == "mp3":
            settings["audio_codec"] = "mp3"
        elif output_format == "ogg":
            settings["audio_codec"] = "vorbis"
        elif output_format == "flac":
            settings["audio_codec"] = "flac"
        elif output_format == "wav":
            settings["audio_codec"] = "pcm_s16le"
        elif output_format == "opus":
            settings["audio_codec"] = "opus"
        elif output_format == "m4a":
            settings["audio_codec"] = "aac"

    return settings


# ----------------------------------------------------------------
# Conversion Functions
# ----------------------------------------------------------------
def create_conversion_job(
    input_path: str, output_format: str, custom_options: Dict[str, Any] = None
) -> Optional[ConversionJob]:
    """
    Create a conversion job from input file and output format
    """
    try:
        input_file = analyze_media_file(input_path)

        if input_file.file_type == "unknown":
            print_warning(f"Unknown file type: {input_path}")
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Attempt conversion anyway?[/]",
                default=False,
            ):
                return None

        # Add to recent files list
        if input_path not in config.recent_files:
            config.recent_files.insert(0, input_path)
            if len(config.recent_files) > 10:
                config.recent_files = config.recent_files[:10]
            config.save()

        # Determine output path
        original_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(original_name)[0]
        output_name = f"{name_without_ext}.{output_format}"
        output_path = os.path.join(config.default_output_dir, output_name)

        # Check if output file already exists
        if os.path.exists(output_path):
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Output file already exists. Overwrite?[/]",
                default=False,
            ):
                # Suggest an alternative name
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                output_name = f"{name_without_ext}_{timestamp}.{output_format}"
                output_path = os.path.join(config.default_output_dir, output_name)
                print_step(f"Using alternative output path: {output_path}")

        # Get optimal settings for the conversion
        settings = get_optimal_output_settings(input_file, output_format)

        # Override with custom options if provided
        if custom_options:
            settings.update(custom_options)

        # Determine if this is a remux-only job (changing container without re-encoding)
        remux_only = False
        if (
            input_file.file_type == "video"
            and output_format in VIDEO_CONTAINERS
            and input_file.video_codec == settings["video_codec"]
            and input_file.audio_codec == settings["audio_codec"]
        ):
            if Confirm.ask(
                f"[bold {NordColors.GREEN}]Input and output codecs match. Use remuxing to avoid re-encoding?[/]",
                default=True,
            ):
                remux_only = True
                print_step("Using remuxing mode (faster, no quality loss)")

        # Create the conversion job
        job = ConversionJob(
            input_file=input_file,
            output_path=output_path,
            output_format=output_format,
            video_codec=settings["video_codec"],
            audio_codec=settings["audio_codec"],
            video_quality=settings["video_quality"],
            audio_quality=settings["audio_quality"],
            preset=settings["preset"],
            remux_only=remux_only,
            extract_audio=input_file.file_type == "video"
            and output_format in AUDIO_CONTAINERS,
        )

        return job

    except Exception as e:
        print_error(f"Error creating conversion job: {e}")
        return None


def execute_conversion_job(job: ConversionJob) -> bool:
    """
    Execute a conversion job using ffmpeg
    """
    try:
        job.status = "running"

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(job.output_path), exist_ok=True)

        # Setup FFmpeg command
        input_stream = ffmpeg.input(job.input_file.path)

        # Prepare arguments for FFmpeg
        output_args = {}

        if job.remux_only:
            # For remuxing, copy audio and video streams without re-encoding
            output_args.update({"c:v": "copy", "c:a": "copy"})
            print_step("Using stream copy mode (remuxing)")
        else:
            # Normal conversion with encoding

            # Video options
            if job.video_codec and not job.extract_audio:
                output_args.update({"c:v": job.video_codec})

                # Apply video quality settings (CRF for h264/h265)
                if job.video_codec in ["h264", "h265", "libx264", "libx265"]:
                    output_args.update({"crf": job.video_quality})

                # Apply encoding preset if available
                if job.preset and job.video_codec in [
                    "h264",
                    "h265",
                    "libx264",
                    "libx265",
                ]:
                    output_args.update({"preset": job.preset})

            elif job.extract_audio:
                # Video disabled for audio extraction
                output_args.update({"vn": None})

            # Audio options
            if job.audio_codec:
                output_args.update({"c:a": job.audio_codec})

                # Apply audio bitrate if specified
                if job.audio_quality and job.audio_codec not in [
                    "flac",
                    "pcm_s16le",
                    "pcm_s24le",
                ]:
                    output_args.update({"b:a": f"{job.audio_quality}k"})

            # Apply time seeking if specified
            if job.start_time is not None:
                output_args.update({"ss": job.start_time})

            if job.end_time is not None:
                output_args.update({"to": job.end_time})

            # Add any additional options
            output_args.update(job.additional_options)

        # Get total duration for progress calculation
        total_duration = job.input_file.duration
        if job.start_time is not None and job.end_time is not None:
            total_duration = job.end_time - job.start_time
        elif job.start_time is not None:
            total_duration = total_duration - job.start_time
        elif job.end_time is not None:
            total_duration = job.end_time

        if total_duration <= 0:
            total_duration = 60  # Default to 1 minute if duration unknown

        # Create progress callback
        progress_regex = re.compile(r"time=(\d+):(\d+):(\d+)\.\d+")

        def progress_callback(line):
            match = progress_regex.search(line)
            if match:
                hours, minutes, seconds = map(int, match.groups())
                time_seconds = hours * 3600 + minutes * 60 + seconds
                progress_percentage = min(100, time_seconds / total_duration * 100)
                job.progress = progress_percentage
                return progress_percentage
            return None

        # Create spinner progress manager
        spinner_progress = SpinnerProgressManager("Conversion Operation")
        task_id = spinner_progress.add_task(
            f"Converting {os.path.basename(job.input_file.path)} → {os.path.basename(job.output_path)}"
        )

        try:
            spinner_progress.start()

            # Run ffmpeg command with progress updates
            process = (
                ffmpeg.output(input_stream, job.output_path, **output_args)
                .global_args("-progress", "pipe:1")
                .overwrite_output()
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )

            # Process stdout for progress updates
            while True:
                line = process.stdout.readline().decode("utf-8", errors="ignore")
                if not line:
                    break

                percent = progress_callback(line)
                if percent is not None:
                    spinner_progress.update_task(task_id, "Converting", percent)

            # Wait for process to complete
            process.wait()

            # Check if process completed successfully
            if process.returncode != 0:
                error_message = process.stderr.read().decode("utf-8", errors="ignore")
                job.status = "failed"
                job.error_message = error_message
                spinner_progress.complete_task(task_id, False)
                print_error(f"Conversion failed: {error_message}")
                return False

            # Mark as completed
            job.status = "completed"
            job.progress = 100
            spinner_progress.complete_task(task_id, True)

            # Add to recent outputs
            if job.output_path not in config.recent_outputs:
                config.recent_outputs.insert(0, job.output_path)
                if len(config.recent_outputs) > 10:
                    config.recent_outputs = config.recent_outputs[:10]
                config.save()

            print_success(f"Conversion completed: {job.output_path}")
            return True

        finally:
            spinner_progress.stop()

    except ffmpeg.Error as e:
        error_message = (
            e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        )
        job.status = "failed"
        job.error_message = error_message
        print_error(f"FFmpeg error: {error_message}")
        return False

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        print_error(f"Conversion error: {e}")
        return False


def check_media_info() -> None:
    """
    Display detailed media information for a file
    """
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter media file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    print_step(f"Analyzing {input_path}...")

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Retrieving media information...")

    try:
        spinner.start()
        # Full ffprobe output
        probe = ffmpeg.probe(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        # Create table for file information
        console.print(f"[bold {NordColors.FROST_3}]Media Information:[/]")

        # Format info
        format_info = probe.get("format", {})
        format_table = Table(
            title="Container Information",
            show_header=True,
            header_style=f"bold {NordColors.FROST_3}",
        )
        format_table.add_column("Property", style="bold")
        format_table.add_column("Value")

        format_table.add_row("Filename", os.path.basename(input_path))
        format_table.add_row("Format", format_info.get("format_name", "Unknown"))
        format_table.add_row(
            "Duration", f"{float(format_info.get('duration', 0)):.2f} seconds"
        )

        size_bytes = format_info.get("size", 0)
        if size_bytes:
            size_mb = int(size_bytes) / (1024 * 1024)
            if size_mb < 1000:
                format_table.add_row("Size", f"{size_mb:.2f} MB")
            else:
                format_table.add_row("Size", f"{size_mb / 1024:.2f} GB")

        bit_rate = format_info.get("bit_rate", 0)
        if bit_rate:
            format_table.add_row("Bitrate", f"{int(bit_rate) / 1000:.0f} kbps")

        console.print(format_table)

        # Stream info
        for i, stream in enumerate(probe.get("streams", [])):
            stream_type = stream.get("codec_type", "unknown").capitalize()
            stream_table = Table(
                title=f"{stream_type} Stream #{i}",
                show_header=True,
                header_style=f"bold {NordColors.FROST_3}",
            )
            stream_table.add_column("Property", style="bold")
            stream_table.add_column("Value")

            # Add basic stream info
            stream_table.add_row("Codec", stream.get("codec_name", "Unknown"))
            stream_table.add_row(
                "Codec Description", stream.get("codec_long_name", "Unknown")
            )

            # Add stream-specific properties
            if stream_type.lower() == "video":
                stream_table.add_row(
                    "Resolution", f"{stream.get('width', 0)}x{stream.get('height', 0)}"
                )
                stream_table.add_row(
                    "Frame Rate", f"{eval(stream.get('avg_frame_rate', '0/1')):.2f} fps"
                )
                stream_table.add_row("Pixel Format", stream.get("pix_fmt", "Unknown"))
                if "bit_rate" in stream:
                    stream_table.add_row(
                        "Video Bitrate", f"{int(stream['bit_rate']) / 1000:.0f} kbps"
                    )

            elif stream_type.lower() == "audio":
                stream_table.add_row(
                    "Sample Rate", f"{stream.get('sample_rate', 0)} Hz"
                )
                stream_table.add_row("Channels", str(stream.get("channels", 0)))
                if "bit_rate" in stream:
                    stream_table.add_row(
                        "Audio Bitrate", f"{int(stream['bit_rate']) / 1000:.0f} kbps"
                    )

            elif stream_type.lower() == "subtitle":
                stream_table.add_row(
                    "Language", stream.get("tags", {}).get("language", "Unknown")
                )

            console.print(stream_table)

    except ffmpeg.Error as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(
            f"Error analyzing media: {e.stderr.decode() if e.stderr else str(e)}"
        )
    except Exception as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error: {e}")


def batch_convert_directory() -> None:
    """
    Convert all files in a directory to a specified format
    """
    path_completer = EnhancedPathCompleter(only_directories=True, expanduser=True)
    input_dir = pt_prompt(
        "Enter directory containing files to convert: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.isdir(os.path.expanduser(input_dir)):
        print_error(f"Directory not found: {input_dir}")
        return

    # Get target format
    formats = sorted(list(VIDEO_CONTAINERS.keys()) + list(AUDIO_CONTAINERS.keys()))
    format_table = Table(title="Available Output Formats", show_header=True)
    format_table.add_column("Category", style=f"bold {NordColors.FROST_3}")
    format_table.add_column("Formats", style=f"{NordColors.FROST_2}")

    format_table.add_row("Video", ", ".join(sorted(VIDEO_CONTAINERS.keys())))
    format_table.add_row("Audio", ", ".join(sorted(AUDIO_CONTAINERS.keys())))

    console.print(format_table)

    output_format = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Enter target format[/]",
        choices=formats,
        default="mp4" if "mp4" in formats else formats[0],
    )

    # Get filter options
    filter_option = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Convert[/]",
        choices=["all", "video", "audio"],
        default="all",
    )

    # Scan directory
    input_dir = os.path.expanduser(input_dir)
    spinner = SpinnerProgressManager("Directory Scan")
    scan_task = spinner.add_task(f"Scanning directory {input_dir}...")

    try:
        spinner.start()

        files = []
        for filename in os.listdir(input_dir):
            file_path = os.path.join(input_dir, filename)
            if os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower().lstrip(".")
                if (
                    filter_option == "all"
                    or (filter_option == "video" and ext in VIDEO_CONTAINERS)
                    or (filter_option == "audio" and ext in AUDIO_CONTAINERS)
                ):
                    files.append(file_path)

        spinner.update_task(scan_task, f"Found {len(files)} files")
        spinner.complete_task(scan_task, True)
        spinner.stop()

        if not files:
            print_warning(f"No matching files found in {input_dir}")
            return

        # Show files to be converted
        file_table = Table(
            title=f"Files to Convert ({len(files)} files)", show_header=True
        )
        file_table.add_column("#", style="bold", width=4)
        file_table.add_column("Filename", style="bold")
        file_table.add_column("Type", style=NordColors.FROST_3)
        file_table.add_column("Size", justify="right")

        for i, file_path in enumerate(files, 1):
            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            file_type = (
                "Video"
                if ext in VIDEO_CONTAINERS
                else "Audio"
                if ext in AUDIO_CONTAINERS
                else "Other"
            )
            size_bytes = os.path.getsize(file_path)
            size_mb = size_bytes / (1024 * 1024)

            if size_mb < 1000:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_str = f"{size_mb / 1024:.2f} GB"

            file_table.add_row(str(i), filename, file_type, size_str)

        console.print(file_table)

        if not Confirm.ask(
            f"[bold {NordColors.YELLOW}]Convert these {len(files)} files to {output_format}?[/]",
            default=False,
        ):
            print_warning("Batch conversion canceled")
            return

        # Set conversion options
        settings = get_optimal_output_settings(
            MediaFile(path="dummy.mp4", file_type="video"), output_format
        )

        if output_format in VIDEO_CONTAINERS:
            # Let user choose video codec
            video_codec = Prompt.ask(
                f"[bold {NordColors.PURPLE}]Video codec[/]",
                choices=sorted(VIDEO_CODECS.keys()),
                default=settings["video_codec"],
            )
            settings["video_codec"] = video_codec

            # Let user choose preset
            preset = Prompt.ask(
                f"[bold {NordColors.PURPLE}]Encoding preset[/]",
                choices=sorted(PRESETS.keys()),
                default=settings["preset"],
            )
            settings["preset"] = preset

        # Let user choose audio codec
        audio_codec = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Audio codec[/]",
            choices=sorted(AUDIO_CODECS.keys()),
            default=settings["audio_codec"],
        )
        settings["audio_codec"] = audio_codec

        # Process each file
        success_count = 0
        failed_files = []

        for i, file_path in enumerate(files, 1):
            filename = os.path.basename(file_path)
            console.rule(
                f"[bold {NordColors.FROST_3}]Converting file {i}/{len(files)}: {filename}[/]"
            )

            job = create_conversion_job(file_path, output_format, settings)
            if job:
                if execute_conversion_job(job):
                    success_count += 1
                else:
                    failed_files.append(filename)
            else:
                failed_files.append(filename)

        # Show summary
        console.rule(f"[bold {NordColors.FROST_3}]Batch Conversion Complete[/]")
        if success_count == len(files):
            print_success(f"All {len(files)} files converted successfully!")
        else:
            print_warning(f"Converted {success_count} of {len(files)} files")
            if failed_files:
                print_error(f"Failed to convert: {', '.join(failed_files)}")

        # Update configuration with the last used settings
        config.default_video_codec = settings["video_codec"]
        config.default_audio_codec = settings["audio_codec"]
        config.default_preset = settings["preset"]
        config.save()

    except Exception as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(scan_task, False)
            spinner.stop()
        print_error(f"Error during batch conversion: {e}")


def extract_audio_from_video() -> None:
    """
    Extract audio track from a video file
    """
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter video file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Analyzing video file...")

    try:
        spinner.start()
        media_file = analyze_media_file(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        if media_file.file_type != "video":
            print_error(f"Not a video file: {input_path}")
            return

        if not media_file.audio_codec:
            print_warning(f"No audio stream detected in: {input_path}")
            if not Confirm.ask(
                f"[bold {NordColors.YELLOW}]Continue anyway?[/]",
                default=False,
            ):
                return

        # Display file information
        console.print(f"[bold {NordColors.FROST_3}]Video Information:[/]")
        console.print(f"[{NordColors.FROST_2}]{media_file.get_file_info()}[/]")
        console.print()

        # Select output audio format
        audio_formats = sorted(AUDIO_CONTAINERS.keys())
        format_table = Table(title="Available Audio Formats", show_header=True)
        format_table.add_column("Format", style="bold")
        format_table.add_column("Description", style=NordColors.FROST_2)

        for fmt, desc in sorted(AUDIO_CONTAINERS.items()):
            format_table.add_row(fmt, desc)

        console.print(format_table)

        output_format = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select output audio format[/]",
            choices=audio_formats,
            default="mp3",
        )

        # Select audio codec
        audio_codec = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select audio codec[/]",
            choices=sorted(AUDIO_CODECS.keys()),
            default=get_optimal_output_settings(media_file, output_format)[
                "audio_codec"
            ],
        )

        # Select audio quality
        audio_quality = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select audio quality (kbps)[/]",
            choices=sorted(AUDIO_QUALITY.keys()),
            default=config.default_audio_quality,
        )

        # Create job with extraction settings
        job = create_conversion_job(
            input_path,
            output_format,
            {
                "video_codec": None,
                "audio_codec": audio_codec,
                "audio_quality": audio_quality,
                "extract_audio": True,
            },
        )

        if job:
            if execute_conversion_job(job):
                print_success(f"Audio extracted to: {job.output_path}")
                # Update config
                config.default_audio_codec = audio_codec
                config.default_audio_quality = audio_quality
                config.save()

    except Exception as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error extracting audio: {e}")


def trim_media_file() -> None:
    """
    Trim a media file (extract a portion)
    """
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter media file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Analyzing media file...")

    try:
        spinner.start()
        media_file = analyze_media_file(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        # Show file information
        duration = media_file.duration
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)

        console.print(f"[bold {NordColors.FROST_3}]File Information:[/]")
        console.print(f"[{NordColors.FROST_2}]{media_file.get_file_info()}[/]")
        console.print(
            f"Duration: [bold]{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}[/]"
        )

        # Get trim start and end times
        def parse_time(time_str: str) -> float:
            """Convert time string (HH:MM:SS or MM:SS or seconds) to seconds"""
            if ":" in time_str:
                parts = time_str.split(":")
                if len(parts) == 3:  # HH:MM:SS
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:  # MM:SS
                    return int(parts[0]) * 60 + float(parts[1])
            return float(time_str)  # Seconds

        while True:
            start_time_str = pt_prompt(
                "Enter start time (HH:MM:SS, MM:SS, or seconds): ",
                default="00:00:00",
                style=get_prompt_style(),
            )

            try:
                start_time = parse_time(start_time_str)
                if start_time < 0 or start_time >= duration:
                    print_error(
                        f"Start time must be between 0 and {duration:.2f} seconds"
                    )
                    continue
                break
            except ValueError:
                print_error("Invalid time format. Use HH:MM:SS, MM:SS, or seconds")

        while True:
            end_time_str = pt_prompt(
                "Enter end time (HH:MM:SS, MM:SS, or seconds): ",
                default=f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}",
                style=get_prompt_style(),
            )

            try:
                end_time = parse_time(end_time_str)
                if end_time <= start_time or end_time > duration:
                    print_error(
                        f"End time must be between {start_time:.2f} and {duration:.2f} seconds"
                    )
                    continue
                break
            except ValueError:
                print_error("Invalid time format. Use HH:MM:SS, MM:SS, or seconds")

        # Calculate segment duration
        segment_duration = end_time - start_time
        seg_hours, remainder = divmod(segment_duration, 3600)
        seg_minutes, seg_seconds = divmod(remainder, 60)

        console.print(
            f"[bold {NordColors.FROST_2}]Segment duration: "
            f"{int(seg_hours):02d}:{int(seg_minutes):02d}:{int(seg_seconds):02d}[/]"
        )

        # Ask for output format
        _, ext = os.path.splitext(input_path)
        ext = ext.lstrip(".").lower()

        if ext in VIDEO_CONTAINERS:
            output_formats = list(VIDEO_CONTAINERS.keys())
            default_format = ext
        elif ext in AUDIO_CONTAINERS:
            output_formats = list(AUDIO_CONTAINERS.keys())
            default_format = ext
        else:
            output_formats = list(VIDEO_CONTAINERS.keys()) + list(
                AUDIO_CONTAINERS.keys()
            )
            default_format = "mp4"

        output_format = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select output format[/]",
            choices=sorted(output_formats),
            default=default_format,
        )

        # Create and execute job
        job = create_conversion_job(input_path, output_format)
        if job:
            # Update job with trim times
            job.start_time = start_time
            job.end_time = end_time

            # Add trimming indicator to filename
            base_name = os.path.splitext(os.path.basename(job.output_path))[0]
            trim_indicator = f"_trim_{int(start_time)}s-{int(end_time)}s"
            new_name = f"{base_name}{trim_indicator}.{output_format}"
            job.output_path = os.path.join(os.path.dirname(job.output_path), new_name)

            if execute_conversion_job(job):
                print_success(f"Trimmed file saved to: {job.output_path}")

    except Exception as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error trimming media file: {e}")


def configure_settings() -> None:
    """
    Configure application settings
    """
    console.print(
        Panel(f"[bold {NordColors.FROST_2}]Configuration Settings[/]", expand=False)
    )

    # Directory settings
    print_section("Directory Settings")

    new_input_dir = pt_prompt(
        "Default input directory: ",
        default=config.default_input_dir,
        completer=EnhancedPathCompleter(only_directories=True, expanduser=True),
        style=get_prompt_style(),
    )

    if os.path.isdir(os.path.expanduser(new_input_dir)):
        config.default_input_dir = new_input_dir
    else:
        print_warning(f"Directory doesn't exist: {new_input_dir}")
        if Confirm.ask(
            f"[bold {NordColors.YELLOW}]Create this directory?[/]",
            default=True,
        ):
            os.makedirs(os.path.expanduser(new_input_dir), exist_ok=True)
            config.default_input_dir = new_input_dir

    new_output_dir = pt_prompt(
        "Default output directory: ",
        default=config.default_output_dir,
        completer=EnhancedPathCompleter(only_directories=True, expanduser=True),
        style=get_prompt_style(),
    )

    if os.path.isdir(os.path.expanduser(new_output_dir)):
        config.default_output_dir = new_output_dir
    else:
        print_warning(f"Directory doesn't exist: {new_output_dir}")
        if Confirm.ask(
            f"[bold {NordColors.YELLOW}]Create this directory?[/]",
            default=True,
        ):
            os.makedirs(os.path.expanduser(new_output_dir), exist_ok=True)
            config.default_output_dir = new_output_dir

    # Codec settings
    print_section("Default Codec Settings")

    # Video codec
    video_table = Table(title="Available Video Codecs", show_header=True)
    video_table.add_column("Codec", style="bold")
    video_table.add_column("Description", style=NordColors.FROST_2)

    for codec, desc in sorted(VIDEO_CODECS.items()):
        video_table.add_row(codec, desc)

    console.print(video_table)

    config.default_video_codec = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default video codec[/]",
        choices=sorted(VIDEO_CODECS.keys()),
        default=config.default_video_codec,
    )

    # Audio codec
    audio_table = Table(title="Available Audio Codecs", show_header=True)
    audio_table.add_column("Codec", style="bold")
    audio_table.add_column("Description", style=NordColors.FROST_2)

    for codec, desc in sorted(AUDIO_CODECS.items()):
        audio_table.add_row(codec, desc)

    console.print(audio_table)

    config.default_audio_codec = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default audio codec[/]",
        choices=sorted(AUDIO_CODECS.keys()),
        default=config.default_audio_codec,
    )

    # Quality settings
    print_section("Quality Settings")

    # Video quality
    quality_table = Table(title="Video Quality Presets (CRF values)", show_header=True)
    quality_table.add_column("CRF", style="bold")
    quality_table.add_column("Description", style=NordColors.FROST_2)

    for crf, desc in sorted(
        VIDEO_QUALITY.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 100
    ):
        quality_table.add_row(crf, desc)

    console.print(quality_table)

    config.default_video_quality = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default video quality (CRF value)[/]",
        choices=sorted(VIDEO_QUALITY.keys()),
        default=config.default_video_quality,
    )

    # Audio quality
    audio_quality_table = Table(title="Audio Bitrate Presets", show_header=True)
    audio_quality_table.add_column("Bitrate", style="bold")
    audio_quality_table.add_column("Description", style=NordColors.FROST_2)

    for bitrate, desc in sorted(AUDIO_QUALITY.items(), key=lambda x: int(x[0])):
        audio_quality_table.add_row(bitrate, desc)

    console.print(audio_quality_table)

    config.default_audio_quality = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default audio bitrate (kbps)[/]",
        choices=sorted(AUDIO_QUALITY.keys()),
        default=config.default_audio_quality,
    )

    # Preset
    preset_table = Table(title="Encoding Presets", show_header=True)
    preset_table.add_column("Preset", style="bold")
    preset_table.add_column("Description", style=NordColors.FROST_2)

    for preset, desc in PRESETS.items():
        preset_table.add_row(preset, desc)

    console.print(preset_table)

    config.default_preset = Prompt.ask(
        f"[bold {NordColors.PURPLE}]Default encoding preset[/]",
        choices=sorted(PRESETS.keys()),
        default=config.default_preset,
    )

    # Save config
    config.save()
    print_success("Configuration saved successfully")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_message("Cleaning up session resources...", NordColors.FROST_3)
    # Add any cleanup tasks here


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Program Control
# ----------------------------------------------------------------
def convert_media_file() -> None:
    """
    Convert a single media file with custom options
    """
    path_completer = EnhancedPathCompleter(only_directories=False, expanduser=True)
    input_path = pt_prompt(
        "Enter media file path: ",
        completer=path_completer,
        default=config.default_input_dir,
        history=FileHistory(PATH_HISTORY),
        auto_suggest=AutoSuggestFromHistory(),
        style=get_prompt_style(),
    )

    if not os.path.exists(os.path.expanduser(input_path)):
        print_error(f"File not found: {input_path}")
        return

    spinner = SpinnerProgressManager("Media Analysis")
    task_id = spinner.add_task("Analyzing media file...")

    try:
        spinner.start()
        media_file = analyze_media_file(input_path)
        spinner.update_task(task_id, "Analysis complete")
        spinner.complete_task(task_id, True)
        spinner.stop()

        # Display file info
        console.print(f"[bold {NordColors.FROST_3}]File Information:[/]")
        console.print(f"[{NordColors.FROST_2}]{media_file.get_file_info()}[/]")
        console.print()

        # Get output format
        formats = []
        if media_file.file_type == "video":
            formats = list(VIDEO_CONTAINERS.keys())
            default_format = "mp4"
        elif media_file.file_type == "audio":
            formats = list(AUDIO_CONTAINERS.keys())
            default_format = "mp3"
        else:
            formats = list(VIDEO_CONTAINERS.keys()) + list(AUDIO_CONTAINERS.keys())
            default_format = "mp4"

        output_format = Prompt.ask(
            f"[bold {NordColors.PURPLE}]Select output format[/]",
            choices=sorted(formats),
            default=default_format,
        )

        # Get conversion settings
        custom_options = {}

        if output_format in VIDEO_CONTAINERS and media_file.file_type == "video":
            # Video settings
            if Confirm.ask(
                f"[bold {NordColors.FROST_3}]Configure video settings?[/]",
                default=True,
            ):
                video_codec = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Video codec[/]",
                    choices=sorted(VIDEO_CODECS.keys()),
                    default=config.default_video_codec,
                )
                custom_options["video_codec"] = video_codec

                video_quality = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Video quality (CRF value)[/]",
                    choices=sorted(VIDEO_QUALITY.keys()),
                    default=config.default_video_quality,
                )
                custom_options["video_quality"] = video_quality

                preset = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Encoding preset[/]",
                    choices=sorted(PRESETS.keys()),
                    default=config.default_preset,
                )
                custom_options["preset"] = preset

        # Audio settings
        if (
            output_format in VIDEO_CONTAINERS and media_file.file_type == "video"
        ) or output_format in AUDIO_CONTAINERS:
            if Confirm.ask(
                f"[bold {NordColors.FROST_3}]Configure audio settings?[/]",
                default=True,
            ):
                audio_codec = Prompt.ask(
                    f"[bold {NordColors.PURPLE}]Audio codec[/]",
                    choices=sorted(AUDIO_CODECS.keys()),
                    default=config.default_audio_codec,
                )
                custom_options["audio_codec"] = audio_codec

                if audio_codec not in ["flac", "pcm_s16le", "pcm_s24le"]:
                    audio_quality = Prompt.ask(
                        f"[bold {NordColors.PURPLE}]Audio bitrate (kbps)[/]",
                        choices=sorted(AUDIO_QUALITY.keys()),
                        default=config.default_audio_quality,
                    )
                    custom_options["audio_quality"] = audio_quality

        # Create and execute job
        job = create_conversion_job(input_path, output_format, custom_options)
        if job:
            if execute_conversion_job(job):
                print_success(f"Conversion completed: {job.output_path}")

                # Update config with last used settings
                if "video_codec" in custom_options:
                    config.default_video_codec = custom_options["video_codec"]
                if "audio_codec" in custom_options:
                    config.default_audio_codec = custom_options["audio_codec"]
                if "video_quality" in custom_options:
                    config.default_video_quality = custom_options["video_quality"]
                if "audio_quality" in custom_options:
                    config.default_audio_quality = custom_options["audio_quality"]
                if "preset" in custom_options:
                    config.default_preset = custom_options["preset"]
                config.save()

    except Exception as e:
        if "spinner" in locals() and spinner.is_started:
            spinner.complete_task(task_id, False)
            spinner.stop()
        print_error(f"Error converting media file: {e}")


def display_recent_files() -> None:
    """Display recent files in a formatted table"""
    if not config.recent_files:
        return

    recent_table = Table(
        title="Recent Files",
        show_header=True,
        header_style=f"bold {NordColors.FROST_3}",
    )
    recent_table.add_column("#", style="bold", width=3)
    recent_table.add_column("Filename", style="bold")
    recent_table.add_column("Path", style=f"{NordColors.FROST_4}")

    for i, file_path in enumerate(config.recent_files[:5], 1):
        filename = os.path.basename(file_path)
        directory = os.path.dirname(file_path)
        recent_table.add_row(str(i), filename, directory)

    console.print(recent_table)


def main_menu() -> None:
    menu_options = [
        ("1", "Convert Media File", lambda: convert_media_file()),
        ("2", "Extract Audio from Video", lambda: extract_audio_from_video()),
        ("3", "Batch Convert Directory", lambda: batch_convert_directory()),
        ("4", "Trim Media File", lambda: trim_media_file()),
        ("5", "Media Information", lambda: check_media_info()),
        ("6", "Configure Settings", lambda: configure_settings()),
        ("H", "Help", lambda: show_help()),
        ("0", "Exit", lambda: None),
    ]

    while True:
        console.clear()
        console.print(create_header())
        display_status_bar()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {HOSTNAME}[/]"
            )
        )
        console.print()
        console.print(f"[bold {NordColors.PURPLE}]Media Conversion Menu[/]")
        table = Table(
            show_header=True, header_style=f"bold {NordColors.FROST_3}", expand=True
        )
        table.add_column("Option", style="bold", width=8)
        table.add_column("Description", style="bold")
        for option, description, _ in menu_options:
            table.add_row(option, description)
        console.print(table)

        # Show recent files if any
        if config.recent_files:
            display_recent_files()

        command_history = FileHistory(COMMAND_HISTORY)
        choice = pt_prompt(
            "Enter your choice: ",
            history=command_history,
            auto_suggest=AutoSuggestFromHistory(),
            style=get_prompt_style(),
        ).upper()

        if choice == "0":
            console.print()
            console.print(
                Panel(
                    Text(
                        f"Thank you for using the Media Conversion Toolkit!",
                        style=f"bold {NordColors.FROST_2}",
                    ),
                    border_style=Style(color=NordColors.FROST_1),
                    padding=(1, 2),
                )
            )
            sys.exit(0)
        else:
            for option, _, func in menu_options:
                if choice == option:
                    func()
                    wait_for_key()
                    break
            else:
                print_error(f"Invalid selection: {choice}")
                wait_for_key()


def main() -> None:
    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        console.print_exception()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)
