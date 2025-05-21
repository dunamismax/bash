#!/usr/bin/env python3

import os
import signal
import sys
import time
import shutil
import subprocess
import json
import asyncio
import atexit
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any, Tuple

try:
    import pyfiglet
    from rich import box
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
    import requests
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet requests"
    )
    sys.exit(1)

install_rich_traceback(show_locals=True)
console: Console = Console()

# Configuration and Constants
APP_NAME: str = "Ubuntu Downloader"
VERSION: str = "1.0.1"
DEFAULT_DOWNLOAD_DIR: str = os.path.join(os.path.expanduser("~"), "Downloads")
CONFIG_DIR: str = os.path.expanduser("~/.config/ubuntu_downloader")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
DOWNLOAD_TIMEOUT: int = 3600  # 1 hour timeout for downloads
DEFAULT_TIMEOUT: int = 120  # 2 minutes default timeout for commands


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

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]


class DownloadType(Enum):
    FILE = "file"
    YOUTUBE = "youtube"


@dataclass
class DownloadSource:
    url: str
    download_type: DownloadType = DownloadType.FILE
    name: str = ""
    size: int = 0

    def __post_init__(self):
        if not self.name:
            self.name = self.get_filename_from_url()

    def get_filename_from_url(self) -> str:
        try:
            path = self.url.split("?")[0]
            filename = os.path.basename(path)
            return filename if filename else "downloaded_file"
        except Exception:
            return "downloaded_file"


@dataclass
class DownloadStats:
    bytes_downloaded: int = 0
    total_size: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    rate_history: List[float] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.end_time is not None or (
            self.total_size > 0 and self.bytes_downloaded >= self.total_size
        )

    @property
    def progress_percentage(self) -> float:
        if self.total_size <= 0:
            return 0.0
        return min(100.0, (self.bytes_downloaded / self.total_size) * 100)

    @property
    def elapsed_time(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def average_rate(self) -> float:
        if not self.rate_history:
            if self.elapsed_time > 0:
                return self.bytes_downloaded / self.elapsed_time
            return 0.0
        return sum(self.rate_history) / len(self.rate_history)

    def update_progress(self, new_bytes: int) -> None:
        now = time.time()
        if self.bytes_downloaded > 0:
            time_diff = now - (self.end_time or self.start_time)
            if time_diff > 0:
                rate = new_bytes / time_diff
                self.rate_history.append(rate)
                if len(self.rate_history) > 5:
                    self.rate_history.pop(0)

        self.bytes_downloaded += new_bytes
        self.end_time = now

        if self.total_size > 0 and self.bytes_downloaded >= self.total_size:
            self.bytes_downloaded = self.total_size


@dataclass
class Dependency:
    name: str
    command: str
    install_command: List[str]
    installed: bool = False

    def check_installed(self) -> bool:
        self.installed = bool(shutil.which(self.command))
        return self.installed


@dataclass
class AppConfig:
    default_download_dir: str = DEFAULT_DOWNLOAD_DIR
    recent_downloads: List[str] = field(default_factory=list)


# UI Helper Functions
def clear_screen() -> None:
    console.clear()


def create_header() -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "mini"]
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
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


def format_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# Core Functionality
def ensure_config_directory() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.__dict__, f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig(**data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
    return AppConfig()


def run_command(
    cmd: List[str],
    check: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if verbose and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def get_file_size(url: str) -> int:
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit():
            return int(content_length)
        return 0
    except Exception as e:
        print_warning(f"Could not determine file size: {e}")
        return 0


async def download_file_with_progress(url: str, output_path: str) -> bool:
    source = DownloadSource(url=url)
    source.size = get_file_size(url)

    try:
        # Make sure the URL is safely encoded
        safe_url = urllib.parse.quote(url, safe=":/?&=")

        # Create stats object to track progress
        stats = DownloadStats(total_size=source.size)

        # Start a progress bar
        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]Downloading"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            download_task = progress.add_task(
                "Downloading", total=source.size if source.size > 0 else None
            )

            # Use requests to stream the download
            with requests.get(
                safe_url, stream=True, timeout=DOWNLOAD_TIMEOUT
            ) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            # Update progress
                            chunk_size = len(chunk)
                            stats.update_progress(chunk_size)
                            progress.update(
                                download_task,
                                completed=stats.bytes_downloaded,
                                description=f"Downloading {format_size(stats.average_rate)}/s",
                            )

                            # For unknown size, use fake progress
                            if source.size <= 0:
                                progress.update(download_task, advance=0.5)

        return True
    except Exception as e:
        print_error(f"Download failed: {e}")
        return False


def ensure_directory(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print_error(f"Failed to create directory '{path}': {e}")
        raise


def download_file(url: str, output_dir: str, verbose: bool = False) -> bool:
    try:
        # Ensure output directory exists
        ensure_directory(output_dir)

        # Get filename from URL
        source = DownloadSource(url=url)
        filename = source.name
        output_path = os.path.join(output_dir, filename)

        print_step(f"Downloading: {url}")
        print_step(f"Destination: {output_path}")

        # Start download
        start_time = time.time()

        # Create event loop for async download
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(download_file_with_progress(url, output_path))

        if success and os.path.exists(output_path):
            file_stats = os.stat(output_path)
            download_time = time.time() - start_time
            download_speed = file_stats.st_size / max(download_time, 0.1)

            display_panel(
                "Download Complete",
                f"Downloaded: {filename}\n"
                f"Size: {format_size(file_stats.st_size)}\n"
                f"Time: {format_time(download_time)}\n"
                f"Speed: {format_size(download_speed)}/s\n"
                f"Location: {output_path}",
                NordColors.GREEN,
            )
            return True
        else:
            print_error("Download failed or file not created")
            return False
    except Exception as e:
        print_error(f"Download failed: {e}")
        console.print_exception()
        return False


def download_youtube(
    url: str, output_dir: str, quality: str = "best", verbose: bool = False
) -> bool:
    try:
        # Ensure output directory exists
        ensure_directory(output_dir)

        # Prepare output template
        output_template = "%(title)s.%(ext)s"
        output_path = os.path.join(output_dir, output_template)

        # Display download info
        print_step(f"Downloading YouTube video: {url}")
        print_step(f"Quality: {quality}")
        print_step(f"Destination: {output_dir}")

        # Build the yt-dlp command
        cmd = ["yt-dlp"]

        # Add format selection based on quality
        if quality == "audio":
            cmd.extend(["-x", "--audio-format", "mp3"])
        elif quality == "best":
            cmd.append("-f best")
        elif quality == "720p":
            cmd.append("-f 'bestvideo[height<=720]+bestaudio/best[height<=720]'")
        elif quality == "1080p":
            cmd.append("-f 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'")

        # Add output path
        cmd.extend(["-o", output_path])

        # Add verbose flag if requested
        if verbose:
            cmd.append("-v")

        # Add URL
        cmd.append(url)

        with Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}"),
            BarColumn(style=NordColors.FROST_4, complete_style=NordColors.FROST_2),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            download_task = progress.add_task(
                "Starting YouTube download...", total=None
            )

            # Execute the command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Track output
            while True:
                # Check if process has ended
                if process.poll() is not None:
                    break

                # Read stdout for progress
                stdout_line = process.stdout.readline()
                if stdout_line:
                    # Update progress description based on output
                    if "[download]" in stdout_line and "%" in stdout_line:
                        progress.update(download_task, description=stdout_line.strip())
                    elif "Downloading video" in stdout_line:
                        progress.update(
                            download_task, description="Downloading video..."
                        )
                    elif "Downloading audio" in stdout_line:
                        progress.update(
                            download_task, description="Downloading audio..."
                        )
                    elif "Merging formats" in stdout_line:
                        progress.update(download_task, description="Merging formats...")

                time.sleep(0.1)

            # Get return code
            return_code = process.wait()

        if return_code == 0:
            # Try to find the downloaded file
            files = os.listdir(output_dir)
            downloaded_file = None
            newest_time = 0

            for file in files:
                file_path = os.path.join(output_dir, file)
                file_time = os.path.getmtime(file_path)
                if file_time > newest_time:
                    newest_time = file_time
                    downloaded_file = file

            if downloaded_file:
                display_panel(
                    "Download Complete",
                    f"Downloaded: {downloaded_file}\nLocation: {output_dir}",
                    NordColors.GREEN,
                )
                return True
            else:
                print_warning("Download may have succeeded but file not found")
                return True
        else:
            print_error("YouTube download failed")
            return False
    except Exception as e:
        print_error(f"YouTube download failed: {e}")
        console.print_exception()
        return False


# Signal Handling and Cleanup
def cleanup() -> None:
    config = load_config()
    save_config(config)
    print_message("Cleaning up resources...", NordColors.FROST_3)


def signal_handler(sig: int, frame: Any) -> None:
    try:
        sig_name = signal.Signals(sig).name
        print_warning(f"Process interrupted by {sig_name}")
    except Exception:
        print_warning(f"Process interrupted by signal {sig}")

    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# Menu functions
def create_menu_table(title: str, options: List[Tuple[str, str, str]]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        box=box.ROUNDED,
        title=title,
        padding=(0, 1),
    )

    table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3, justify="right")
    table.add_column("Option", style=f"bold {NordColors.FROST_1}")
    table.add_column("Description", style=f"{NordColors.SNOW_STORM_1}")

    for option in options:
        table.add_row(*option)

    return table


def file_download_menu() -> None:
    clear_screen()
    console.print(create_header())

    display_panel("File Download", "Download any file from the web", NordColors.FROST_2)

    url = Prompt.ask("Enter the URL to download")
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return

    config = load_config()
    output_dir = Prompt.ask(
        "Enter the output directory", default=config.default_download_dir
    )

    verbose = Confirm.ask("Enable verbose mode?", default=False)

    success = download_file(url, output_dir, verbose)

    # Update config with recent downloads if successful
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            # Keep only the last 5 downloads
            config.recent_downloads = config.recent_downloads[:5]
        save_config(config)

    Prompt.ask("Press Enter to return to the main menu")


def youtube_download_menu() -> None:
    clear_screen()
    console.print(create_header())

    display_panel(
        "YouTube Download", "Download videos or audio from YouTube", NordColors.FROST_2
    )

    # Check if yt-dlp is installed
    if not shutil.which("yt-dlp"):
        print_error("yt-dlp is not installed")
        print_step("Install it with: pip install yt-dlp")
        Prompt.ask("Press Enter to return to the main menu")
        return

    url = Prompt.ask("Enter the YouTube URL")
    if not url:
        print_error("URL cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return

    config = load_config()
    output_dir = Prompt.ask(
        "Enter the output directory", default=config.default_download_dir
    )

    # Quality options
    quality_options = [
        ("1", "Best", "Best available quality"),
        ("2", "1080p", "Full HD (1080p)"),
        ("3", "720p", "HD (720p)"),
        ("4", "Audio", "Audio only (MP3)"),
    ]

    console.print(create_menu_table("Quality Options", quality_options))

    quality_choice = Prompt.ask(
        "Select quality option", choices=["1", "2", "3", "4"], default="1"
    )

    quality_map = {"1": "best", "2": "1080p", "3": "720p", "4": "audio"}
    quality = quality_map[quality_choice]
    verbose = Confirm.ask("Enable verbose mode?", default=False)

    success = download_youtube(url, output_dir, quality, verbose)

    # Update config with recent downloads if successful
    if success:
        if url not in config.recent_downloads:
            config.recent_downloads.insert(0, url)
            # Keep only the last 5 downloads
            config.recent_downloads = config.recent_downloads[:5]
        save_config(config)

    Prompt.ask("Press Enter to return to the main menu")


def settings_menu() -> None:
    clear_screen()
    console.print(create_header())

    display_panel("Settings", "Configure application settings", NordColors.FROST_2)

    config = load_config()

    # Settings options
    settings_options = [
        ("1", "Change Default Download Directory", config.default_download_dir),
        ("2", "View Recent Downloads", f"{len(config.recent_downloads)} downloads"),
        ("3", "Check Dependencies", ""),
        ("4", "Return to Main Menu", ""),
    ]

    console.print(create_menu_table("Settings Options", settings_options))

    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")

    if choice == "1":
        new_dir = Prompt.ask(
            "Enter new default download directory", default=config.default_download_dir
        )

        if os.path.isdir(new_dir) or Confirm.ask(
            f"Directory '{new_dir}' doesn't exist. Create it?", default=True
        ):
            try:
                ensure_directory(new_dir)
                config.default_download_dir = new_dir
                save_config(config)
                print_success(f"Default download directory updated to: {new_dir}")
            except Exception as e:
                print_error(f"Failed to set directory: {e}")
        else:
            print_warning("Directory change canceled")

    elif choice == "2":
        if config.recent_downloads:
            recent_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                box=box.ROUNDED,
                title="Recent Downloads",
            )

            recent_table.add_column("#", style=f"bold {NordColors.FROST_4}", width=3)
            recent_table.add_column("URL", style=f"{NordColors.SNOW_STORM_1}")

            for i, url in enumerate(config.recent_downloads, 1):
                recent_table.add_row(str(i), url)

            console.print(recent_table)
        else:
            print_warning("No recent downloads found")

    elif choice == "3":
        # Define the dependencies
        dependencies = {
            "curl": Dependency(
                name="curl",
                command="curl",
                install_command=["apt", "install", "-y", "curl"],
            ),
            "wget": Dependency(
                name="wget",
                command="wget",
                install_command=["apt", "install", "-y", "wget"],
            ),
            "yt-dlp": Dependency(
                name="yt-dlp",
                command="yt-dlp",
                install_command=["pip", "install", "yt-dlp"],
            ),
            "ffmpeg": Dependency(
                name="ffmpeg",
                command="ffmpeg",
                install_command=["apt", "install", "-y", "ffmpeg"],
            ),
        }

        # Check dependencies
        dep_table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            box=box.ROUNDED,
            title="Dependency Status",
        )

        dep_table.add_column("Dependency", style=f"bold {NordColors.FROST_1}")
        dep_table.add_column("Status", style=f"{NordColors.SNOW_STORM_1}")

        missing_deps = {}
        for name, dep in dependencies.items():
            installed = dep.check_installed()
            status_text = "Installed" if installed else "Missing"
            status_style = NordColors.GREEN if installed else NordColors.RED
            dep_table.add_row(name, f"[{status_style}]{status_text}[/]")

            if not installed:
                missing_deps[name] = dep

        console.print(dep_table)

        # Install missing dependencies if any
        if missing_deps:
            if Confirm.ask("Install missing dependencies?", default=True):
                with Progress(
                    SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
                    TextColumn("[bold]{task.description}"),
                    BarColumn(
                        style=NordColors.FROST_4, complete_style=NordColors.FROST_2
                    ),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    install_task = progress.add_task(
                        "Installing", total=len(missing_deps)
                    )

                    for name, dep in missing_deps.items():
                        progress.update(
                            install_task, description=f"Installing {name}..."
                        )

                        # Check if we need sudo
                        cmd = dep.install_command
                        if cmd[0] in ["apt", "apt-get"] and os.geteuid() != 0:
                            cmd = ["sudo"] + cmd

                        try:
                            run_command(cmd, check=False, verbose=True)
                            if dep.check_installed():
                                print_success(f"Installed {name}")
                            else:
                                print_error(f"Failed to install {name}")
                        except Exception as e:
                            print_error(f"Error installing {name}: {e}")

                        progress.advance(install_task)

            else:
                print_warning("Dependency installation skipped")
        else:
            print_success("All dependencies are installed")

    Prompt.ask("Press Enter to return to the main menu")


def main() -> None:
    try:
        # Ensure config directory exists
        ensure_config_directory()

        while True:
            clear_screen()
            console.print(create_header())

            # Main menu options
            main_options = [
                ("1", "Download File", "Download any file from the web"),
                ("2", "Download YouTube", "Download video or audio from YouTube"),
                ("3", "Settings", "Configure application settings"),
                ("4", "Exit", "Exit the application"),
            ]

            console.print(create_menu_table("Main Menu", main_options))

            choice = Prompt.ask(
                "Select an option", choices=["1", "2", "3", "4"], default="4"
            )

            if choice == "1":
                file_download_menu()
            elif choice == "2":
                youtube_download_menu()
            elif choice == "3":
                settings_menu()
            elif choice == "4":
                clear_screen()
                console.print(
                    Panel(
                        Text("Goodbye!", style=f"bold {NordColors.FROST_2}"),
                        border_style=NordColors.FROST_1,
                    )
                )
                break

    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        console.print_exception()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
