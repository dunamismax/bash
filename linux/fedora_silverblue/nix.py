#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import shutil
import subprocess
import atexit
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict, Union
from datetime import datetime
import re


# Check for Fedora Silverblue
def is_fedora_silverblue():
    try:
        with open('/etc/os-release', 'r') as f:
            content = f.read()
            return 'Silverblue' in content or 'Kinoite' in content
    except FileNotFoundError:
        return False


if not is_fedora_silverblue():
    print("This script is tailored for Fedora Silverblue. Exiting.")
    sys.exit(1)


def install_dependencies():
    required_packages = ["rich", "pyfiglet", "prompt_toolkit", "requests"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + required_packages)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)


try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn,
        TimeRemainingColumn, TransferSpeedColumn, MofNCompleteColumn
    )
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from rich.box import ROUNDED, HEAVY
    from rich.style import Style
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style as PTStyle
    import requests
except ImportError:
    install_dependencies()
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console = Console()

APP_NAME = "Fedora Silverblue Nix Manager"
VERSION = "1.0.0"
USER_HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(USER_HOME, ".fedora_nix_manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
DEFAULT_TIMEOUT = 120
NIX_PROFILE = "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"


class SilverBlueColors:
    # Fedora Blue/Grey theme colors
    BLUE_1 = "#3C6EB4"
    BLUE_2 = "#294172"
    BLUE_3 = "#1F336B"
    BLUE_4 = "#0F1A35"
    GREY_1 = "#ECEFF4"
    GREY_2 = "#D8DEE9"
    GREY_3 = "#9DA3AF"
    GREY_4 = "#4D5567"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"

    SUCCESS = Style(color=GREEN, bold=True)
    ERROR = Style(color=RED, bold=True)
    WARNING = Style(color=YELLOW, bold=True)
    INFO = Style(color=BLUE_1, bold=True)
    HEADER = Style(color=BLUE_2, bold=True)
    SUBHEADER = Style(color=BLUE_3, bold=True)
    ACCENT = Style(color=BLUE_4, bold=True)
    SILVERBLUE_BOX = ROUNDED

    @classmethod
    def get_blue_gradient(cls, steps=4):
        return [cls.BLUE_1, cls.BLUE_2, cls.BLUE_3, cls.BLUE_4][:steps]

    @classmethod
    def get_grey_gradient(cls, steps=4):
        return [cls.GREY_1, cls.GREY_2, cls.GREY_3, cls.GREY_4][:steps]

    @classmethod
    def get_progress_columns(cls):
        return [
            SpinnerColumn(spinner_name="dots", style=f"bold {cls.BLUE_1}"),
            TextColumn(f"[bold {cls.BLUE_2}]{{task.description}}[/]"),
            BarColumn(bar_width=None, style=cls.GREY_3, complete_style=cls.BLUE_2, finished_style=cls.GREEN),
            TaskProgressColumn(style=cls.GREY_1),
            MofNCompleteColumn(),
            TransferSpeedColumn(style=cls.BLUE_3),
            TimeRemainingColumn(compact=True),
        ]


@dataclass
class Package:
    name: str
    description: str = ""
    version: str = ""
    installed: bool = False
    install_date: Optional[str] = None


@dataclass
class AppConfig:
    nix_installed: bool = False
    package_mirror: str = "nixpkgs.org"
    last_update_check: Optional[str] = None
    installed_packages: List[str] = field(default_factory=list)
    recent_searches: List[str] = field(default_factory=list)

    def save(self):
        ensure_config_directory()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.__dict__, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save configuration: {e}")

    @classmethod
    def load(cls):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                return cls(**data)
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
        return cls()


@dataclass
class PackageHistory:
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def add_entry(self, package_name, action, success, message=""):
        entry = {
            "package": package_name,
            "action": action,
            "success": success,
            "message": message,
            "date": datetime.now().isoformat()
        }
        self.entries.insert(0, entry)
        self.entries = self.entries[:50]  # Keep only the most recent 50 entries
        self.save()

    def save(self):
        ensure_config_directory()
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump({"history": self.entries}, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save history: {e}")

    @classmethod
    def load(cls):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    data = json.load(f)
                return cls(entries=data.get("history", []))
        except Exception as e:
            print_error(f"Failed to load history: {e}")
        return cls()


def clear_screen():
    console.clear()


def create_header():
    term_width = shutil.get_terminal_size().columns
    adjusted_width = min(term_width - 4, 80)

    fonts = ["slant", "small_slant", "standard", "big", "digital", "small"]
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
    blue_colors = SilverBlueColors.get_blue_gradient(min(len(ascii_lines), 4))

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = blue_colors[i % len(blue_colors)]
        escaped_line = line.replace("[", "\\[").replace("]", "\\]")
        styled_text += f"[bold {color}]{escaped_line}[/]\n"

    border_style = SilverBlueColors.BLUE_3
    border_char = "═"
    border_line = f"[{border_style}]{border_char * (adjusted_width - 8)}[/]"

    styled_text = border_line + "\n" + styled_text + border_line

    panel = Panel(
        Text.from_markup(styled_text),
        border_style=SilverBlueColors.BLUE_1,
        box=SilverBlueColors.SILVERBLUE_BOX,
        padding=(1, 2),
        title=f"[bold {SilverBlueColors.GREY_1}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {SilverBlueColors.GREY_1}]Nix Package Manager for Fedora Silverblue[/]",
        subtitle_align="center",
    )

    return panel


def print_message(text, style=SilverBlueColors.INFO, prefix="•"):
    if isinstance(style, str):
        console.print(f"[{style}]{prefix} {text}[/{style}]")
    else:
        console.print(f"{prefix} {text}", style=style)


def print_error(message):
    print_message(message, SilverBlueColors.ERROR, "✗")


def print_success(message):
    print_message(message, SilverBlueColors.SUCCESS, "✓")


def print_warning(message):
    print_message(message, SilverBlueColors.WARNING, "⚠")


def print_step(message):
    print_message(message, SilverBlueColors.INFO, "→")


def print_info(message):
    print_message(message, SilverBlueColors.INFO, "ℹ")


def display_panel(title, message, style=SilverBlueColors.INFO):
    if isinstance(style, str):
        panel = Panel(
            Text.from_markup(message),
            title=title,
            border_style=style,
            box=SilverBlueColors.SILVERBLUE_BOX,
            padding=(1, 2)
        )
    else:
        panel = Panel(
            Text(message),
            title=title,
            border_style=style,
            box=SilverBlueColors.SILVERBLUE_BOX,
            padding=(1, 2)
        )
    console.print(panel)


def create_menu_table(title, options):
    table = Table(
        show_header=True,
        header_style=SilverBlueColors.HEADER,
        box=ROUNDED,
        title=title,
        border_style=SilverBlueColors.BLUE_3,
        padding=(0, 1),
        expand=True,
    )

    table.add_column("#", style=SilverBlueColors.ACCENT, width=3, justify="right")
    table.add_column("Option", style=SilverBlueColors.BLUE_1)
    table.add_column("Description", style=SilverBlueColors.GREY_1)

    for opt in options:
        table.add_row(*opt)

    return table


def ensure_config_directory():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def run_command(cmd, check=True, timeout=DEFAULT_TIMEOUT, verbose=False, shell=False, env=None):
    try:
        if verbose:
            print_step(f"Executing: {' '.join(cmd) if isinstance(cmd, list) else cmd}")

        with Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {SilverBlueColors.BLUE_1}"),
                TextColumn(f"[bold {SilverBlueColors.BLUE_2}]Running command..."),
                console=console
        ) as progress:
            task = progress.add_task("", total=None)

            if env is None:
                env = os.environ.copy()

            result = subprocess.run(
                cmd,
                check=check,
                text=True,
                capture_output=True,
                timeout=timeout,
                shell=shell,
                env=env
            )

        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        if verbose and e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {SilverBlueColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        print_error(f"Error executing command: {e}")
        raise


def get_nix_env():
    """Get environment with Nix variables properly set"""
    env = os.environ.copy()

    # Check if Nix profile is already sourced
    if not env.get('NIX_PROFILES'):
        # Try to source nix profile
        try:
            if os.path.exists(NIX_PROFILE):
                # Extract environment variables from the profile script
                cmd = f"source {NIX_PROFILE} && env"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                for line in result.stdout.splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env[key] = value
        except Exception as e:
            print_warning(f"Could not source Nix profile: {e}")

    return env


def is_nix_installed():
    """Check if Nix is installed on the system."""
    return os.path.exists("/nix/var/nix/profiles/default")


def install_nix(verbose=False):
    """Installs Nix using the Determinate Nix installer."""
    try:
        display_panel(
            "Installing Nix",
            "This will install the Nix package manager using the Determinate Nix installer.\n"
            "You may be asked to enter your password for sudo access.",
            SilverBlueColors.BLUE_2
        )

        with Progress(
                *SilverBlueColors.get_progress_columns(),
                console=console
        ) as progress:
            install_task = progress.add_task("Downloading installer...", total=100)

            # First, download the installer script
            progress.update(install_task, completed=10, description="Downloading installer...")
            temp_script = "/tmp/install-nix.sh"
            download_cmd = [
                "curl", "--proto", "=https", "--tlsv1.2", "-sSf", "-L",
                "https://install.determinate.systems/nix",
                "-o", temp_script
            ]

            try:
                run_command(download_cmd, verbose=verbose)
                # Make the script executable
                os.chmod(temp_script, 0o755)
                progress.update(install_task, completed=30, description="Running installer...")

                # Run the installer
                install_cmd = [temp_script, "--install"]
                result = run_command(install_cmd, verbose=verbose)

                progress.update(install_task, completed=90, description="Completing installation...")
                time.sleep(1)
                progress.update(install_task, completed=100, description="Installation complete!")

                config = AppConfig.load()
                config.nix_installed = True
                config.save()

                return True
            except Exception as e:
                print_error(f"Failed to install Nix: {e}")
                if verbose:
                    console.print_exception()
                return False
            finally:
                # Clean up
                if os.path.exists(temp_script):
                    os.unlink(temp_script)
    except Exception as e:
        print_error(f"Error installing Nix: {e}")
        if verbose:
            console.print_exception()
        return False


def search_nix_packages(query, verbose=False):
    """Searches for Nix packages using the Nix search tool."""
    if not query:
        print_warning("Empty search query")
        return []

    try:
        env = get_nix_env()

        with Progress(
                *SilverBlueColors.get_progress_columns(),
                console=console
        ) as progress:
            search_task = progress.add_task(f"Searching for '{query}'...", total=100)

            cmd = ["nix", "search", "nixpkgs", query]
            result = run_command(cmd, check=False, verbose=verbose, env=env)

            progress.update(search_task, completed=100)

            if result.returncode != 0:
                print_error(f"Search failed with code {result.returncode}")
                if verbose:
                    console.print(f"Error details: {result.stderr}")
                return []

            # Add the search query to recent searches
            config = AppConfig.load()
            if query not in config.recent_searches:
                config.recent_searches.insert(0, query)
                config.recent_searches = config.recent_searches[:10]  # Keep only 10 most recent
                config.save()

            # Parse the search results
            packages = []
            current_pkg = None

            for line in result.stdout.splitlines():
                # Skip empty lines
                if not line.strip():
                    continue

                # Package line format: "* nixpkgs.packagename (version)"
                if line.startswith("* "):
                    if current_pkg:
                        packages.append(current_pkg)

                    # Extract package name and version
                    match = re.search(r"\* nixpkgs\.([^ ]+)(?: \(([^)]+)\))?", line)
                    if match:
                        name = match.group(1)
                        version = match.group(2) or ""
                        current_pkg = Package(name=name, version=version)

                # Description line
                elif current_pkg and line.strip() and not line.startswith("*"):
                    current_pkg.description = line.strip()

            # Add the last package
            if current_pkg:
                packages.append(current_pkg)

            # Check which packages are installed
            installed_pkgs = get_installed_packages(verbose=verbose)
            for pkg in packages:
                pkg.installed = pkg.name in installed_pkgs

            return packages
    except Exception as e:
        print_error(f"Error searching for packages: {e}")
        if verbose:
            console.print_exception()
        return []


def get_installed_packages(verbose=False):
    """Get list of installed Nix packages."""
    try:
        env = get_nix_env()
        cmd = ["nix-env", "--query", "--installed"]
        result = run_command(cmd, check=False, verbose=verbose, env=env)

        if result.returncode != 0:
            if verbose:
                print_warning(f"Could not get installed packages: {result.stderr}")
            return []

        installed = []
        for line in result.stdout.splitlines():
            if line.strip():
                # Format is typically: name-version
                pkg_name = line.strip().split('-')[0]
                installed.append(pkg_name)

        return installed
    except Exception as e:
        print_warning(f"Error getting installed packages: {e}")
        return []


def install_package(package_name, verbose=False):
    """Installs a Nix package."""
    try:
        env = get_nix_env()

        display_panel(
            "Package Installation",
            f"Installing package: {package_name}\n"
            "This may take some time depending on the package size.",
            SilverBlueColors.BLUE_2
        )

        with Progress(
                *SilverBlueColors.get_progress_columns(),
                console=console
        ) as progress:
            install_task = progress.add_task(f"Installing {package_name}...", total=100)
            progress.update(install_task, completed=10)

            cmd = ["nix-env", "-iA", f"nixpkgs.{package_name}"]
            start_time = time.time()

            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            output_lines = []
            while True:
                if process.poll() is not None:
                    break

                line = process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                output_lines.append(line.strip())

                # Update progress based on output
                if "building" in line.lower():
                    progress.update(install_task, completed=30, description=f"Building {package_name}...")
                elif "installing" in line.lower():
                    progress.update(install_task, completed=70, description=f"Installing {package_name}...")

                if verbose:
                    console.log(line.strip(), style="dim")

            return_code = process.wait()
            end_time = time.time()

            if return_code == 0:
                progress.update(install_task, completed=100, description=f"Installed {package_name}")

                # Update config
                config = AppConfig.load()
                if package_name not in config.installed_packages:
                    config.installed_packages.append(package_name)
                    config.save()

                # Update history
                history = PackageHistory.load()
                history.add_entry(
                    package_name=package_name,
                    action="install",
                    success=True,
                    message=f"Installed in {round(end_time - start_time, 2)} seconds"
                )

                display_panel(
                    "Installation Complete",
                    f"✅ Package [bold]{package_name}[/] installed successfully.\n"
                    f"⏱️ Installation time: {round(end_time - start_time, 2)} seconds",
                    SilverBlueColors.GREEN
                )
                return True
            else:
                error_message = "\n".join(output_lines[-5:]) if output_lines else "Unknown error"

                # Update history
                history = PackageHistory.load()
                history.add_entry(
                    package_name=package_name,
                    action="install",
                    success=False,
                    message=error_message
                )

                display_panel(
                    "Installation Failed",
                    f"❌ Failed to install [bold]{package_name}[/]\n"
                    f"Error: {error_message}",
                    SilverBlueColors.RED
                )
                return False
    except Exception as e:
        print_error(f"Error installing package: {e}")

        # Update history
        history = PackageHistory.load()
        history.add_entry(
            package_name=package_name,
            action="install",
            success=False,
            message=str(e)
        )

        if verbose:
            console.print_exception()
        return False


def uninstall_package(package_name, verbose=False):
    """Uninstalls a Nix package."""
    try:
        env = get_nix_env()

        display_panel(
            "Package Removal",
            f"Removing package: {package_name}",
            SilverBlueColors.BLUE_2
        )

        with Progress(
                *SilverBlueColors.get_progress_columns(),
                console=console
        ) as progress:
            uninstall_task = progress.add_task(f"Uninstalling {package_name}...", total=100)

            cmd = ["nix-env", "-e", package_name]
            start_time = time.time()
            result = run_command(cmd, check=False, verbose=verbose, env=env)
            end_time = time.time()

            if result.returncode == 0:
                progress.update(uninstall_task, completed=100)

                # Update config
                config = AppConfig.load()
                if package_name in config.installed_packages:
                    config.installed_packages.remove(package_name)
                    config.save()

                # Update history
                history = PackageHistory.load()
                history.add_entry(
                    package_name=package_name,
                    action="uninstall",
                    success=True,
                    message=f"Uninstalled in {round(end_time - start_time, 2)} seconds"
                )

                display_panel(
                    "Uninstallation Complete",
                    f"✅ Package [bold]{package_name}[/] removed successfully.\n"
                    f"⏱️ Uninstallation time: {round(end_time - start_time, 2)} seconds",
                    SilverBlueColors.GREEN
                )
                return True
            else:
                error_message = result.stderr if result.stderr else "Unknown error"

                # Update history
                history = PackageHistory.load()
                history.add_entry(
                    package_name=package_name,
                    action="uninstall",
                    success=False,
                    message=error_message
                )

                display_panel(
                    "Uninstallation Failed",
                    f"❌ Failed to remove [bold]{package_name}[/]\n"
                    f"Error: {error_message}",
                    SilverBlueColors.RED
                )
                return False
    except Exception as e:
        print_error(f"Error uninstalling package: {e}")

        # Update history
        history = PackageHistory.load()
        history.add_entry(
            package_name=package_name,
            action="uninstall",
            success=False,
            message=str(e)
        )

        if verbose:
            console.print_exception()
        return False


def cleanup():
    try:
        config = AppConfig.load()
        config.save()
        print_message("Cleaning up resources...", SilverBlueColors.BLUE_3)
    except Exception as e:
        print_error(f"Error during cleanup: {e}")


def signal_handler(sig, frame):
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


def package_search_menu():
    clear_screen()
    console.print(create_header())
    display_panel(
        "Package Search",
        "Search for Nix packages to install on your Fedora Silverblue system.",
        SilverBlueColors.BLUE_2
    )

    config = AppConfig.load()
    history = FileHistory(os.path.join(CONFIG_DIR, "search_history.txt"))
    completer = WordCompleter(config.recent_searches, sentence=True)

    search_query = pt_prompt(
        "Enter search query: ",
        history=history,
        completer=completer,
        style=PTStyle.from_dict({'prompt': f'bold {SilverBlueColors.BLUE_2}', })
    )

    if not search_query:
        print_error("Search query cannot be empty")
        Prompt.ask("Press Enter to return to the main menu")
        return

    verbose = Confirm.ask("Enable verbose mode?", default=False)

    results = search_nix_packages(search_query, verbose=verbose)

    if not results:
        display_panel(
            "Search Results",
            f"No packages found matching '[bold]{search_query}[/]'",
            SilverBlueColors.WARNING
        )
        Prompt.ask("Press Enter to return to the main menu")
        return

    # Display results
    results_table = Table(
        show_header=True,
        header_style=SilverBlueColors.HEADER,
        box=ROUNDED,
        title=f"Search Results for '{search_query}'",
        border_style=SilverBlueColors.BLUE_3,
        expand=True
    )

    results_table.add_column("#", style=SilverBlueColors.ACCENT, width=3)
    results_table.add_column("Package", style=SilverBlueColors.BLUE_1)
    results_table.add_column("Version", style=SilverBlueColors.GREY_3)
    results_table.add_column("Description", style=SilverBlueColors.GREY_1)
    results_table.add_column("Status", style=SilverBlueColors.BLUE_4)

    for i, pkg in enumerate(results[:20], 1):  # Limit to 20 results
        status = "[green]Installed[/green]" if pkg.installed else "[grey]Not installed[/grey]"
        results_table.add_row(
            str(i),
            pkg.name,
            pkg.version,
            pkg.description[:50] + ("..." if len(pkg.description) > 50 else ""),
            status
        )

    console.print(results_table)

    if len(results) > 20:
        print_info(f"Showing 20 of {len(results)} results. Refine your search for more specific results.")

    # Package actions
    selected = Prompt.ask(
        "Enter package number to install (or 0 to return to main menu)",
        choices=["0"] + [str(i) for i in range(1, min(21, len(results) + 1))],
        default="0"
    )

    if selected == "0":
        return

    selected_pkg = results[int(selected) - 1]

    if selected_pkg.installed:
        if Confirm.ask(f"Package {selected_pkg.name} is already installed. Reinstall?", default=False):
            install_package(selected_pkg.name, verbose=verbose)
    else:
        if Confirm.ask(f"Install package {selected_pkg.name}?", default=True):
            install_package(selected_pkg.name, verbose=verbose)

    Prompt.ask("Press Enter to return to the main menu")


def manage_packages_menu():
    clear_screen()
    console.print(create_header())
    display_panel(
        "Package Management",
        "Manage your installed Nix packages.",
        SilverBlueColors.BLUE_2
    )

    verbose = Confirm.ask("Enable verbose mode?", default=False)

    with Progress(
            *SilverBlueColors.get_progress_columns(),
            console=console
    ) as progress:
        task = progress.add_task("Loading installed packages...", total=100)
        progress.update(task, completed=50)

        installed_pkgs = get_installed_packages(verbose=verbose)
        progress.update(task, completed=100)

    if not installed_pkgs:
        display_panel(
            "Installed Packages",
            "No Nix packages are currently installed.",
            SilverBlueColors.WARNING
        )
        Prompt.ask("Press Enter to return to the main menu")
        return

    # Display installed packages
    installed_table = Table(
        show_header=True,
        header_style=SilverBlueColors.HEADER,
        box=ROUNDED,
        title="Installed Packages",
        border_style=SilverBlueColors.BLUE_3,
        expand=True
    )

    installed_table.add_column("#", style=SilverBlueColors.ACCENT, width=3)
    installed_table.add_column("Package", style=SilverBlueColors.BLUE_1)

    for i, pkg in enumerate(installed_pkgs, 1):
        installed_table.add_row(str(i), pkg)

    console.print(installed_table)

    # Package actions
    options = [
        ("1", "Uninstall Package", "Remove a package"),
        ("2", "Update All Packages", "Update all installed packages"),
        ("3", "Return to Main Menu", "")
    ]

    console.print(create_menu_table("Package Actions", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        selected = Prompt.ask(
            "Enter package number to uninstall (or 0 to cancel)",
            choices=["0"] + [str(i) for i in range(1, len(installed_pkgs) + 1)],
            default="0"
        )

        if selected != "0":
            pkg_name = installed_pkgs[int(selected) - 1]
            if Confirm.ask(f"Uninstall package {pkg_name}?", default=False):
                uninstall_package(pkg_name, verbose=verbose)

    elif choice == "2":
        if Confirm.ask("Update all installed packages?", default=True):
            try:
                env = get_nix_env()

                display_panel(
                    "Package Update",
                    "Updating all installed packages.\nThis may take some time.",
                    SilverBlueColors.BLUE_2
                )

                with Progress(
                        *SilverBlueColors.get_progress_columns(),
                        console=console
                ) as progress:
                    update_task = progress.add_task("Updating packages...", total=100)
                    progress.update(update_task, completed=10)

                    cmd = ["nix-env", "-u", "--always"]
                    start_time = time.time()
                    result = run_command(cmd, check=False, verbose=verbose, env=env)
                    end_time = time.time()

                    if result.returncode == 0:
                        progress.update(update_task, completed=100)

                        display_panel(
                            "Update Complete",
                            f"✅ All packages updated successfully.\n"
                            f"⏱️ Update time: {round(end_time - start_time, 2)} seconds",
                            SilverBlueColors.GREEN
                        )
                    else:
                        error_message = result.stderr if result.stderr else "Unknown error"

                        display_panel(
                            "Update Failed",
                            f"❌ Failed to update packages\n"
                            f"Error: {error_message}",
                            SilverBlueColors.RED
                        )
            except Exception as e:
                print_error(f"Error updating packages: {e}")
                if verbose:
                    console.print_exception()

    Prompt.ask("Press Enter to return to the main menu")


def view_history_menu():
    clear_screen()
    console.print(create_header())
    history = PackageHistory.load()

    if not history.entries:
        display_panel("Package History", "No package history found.", SilverBlueColors.BLUE_3)
        Prompt.ask("Press Enter to return to the main menu")
        return

    table = Table(
        show_header=True,
        header_style=SilverBlueColors.HEADER,
        box=ROUNDED,
        title="Package History",
        border_style=SilverBlueColors.BLUE_3,
        expand=True
    )

    table.add_column("#", style=SilverBlueColors.ACCENT, width=3)
    table.add_column("Date", style=SilverBlueColors.BLUE_2)
    table.add_column("Package", style=SilverBlueColors.GREY_1)
    table.add_column("Action", style=SilverBlueColors.BLUE_3)
    table.add_column("Status", style=SilverBlueColors.BLUE_4)

    for i, entry in enumerate(history.entries[:15], 1):
        date_str = datetime.fromisoformat(entry["date"]).strftime("%Y-%m-%d %H:%M")
        status = "[green]Success[/green]" if entry["success"] else "[red]Failed[/red]"
        action = entry["action"].capitalize()
        table.add_row(str(i), date_str, entry["package"], action, status)

    console.print(table)

    options = [
        ("1", "View Details", "See details for a specific entry"),
        ("2", "Clear History", "Delete all package history"),
        ("3", "Return to Main Menu", "")
    ]

    console.print(create_menu_table("History Options", options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")

    if choice == "1":
        entry_num = Prompt.ask(
            "Enter entry number to view details",
            choices=[str(i) for i in range(1, min(16, len(history.entries) + 1))],
            show_choices=False
        )

        entry = history.entries[int(entry_num) - 1]
        display_panel(
            f"History Details: {entry['package']}",
            f"Package: {entry['package']}\n"
            f"Action: {entry['action'].capitalize()}\n"
            f"Status: {'Successful' if entry['success'] else 'Failed'}\n"
            f"Date: {datetime.fromisoformat(entry['date']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Message: {entry['message']}",
            SilverBlueColors.BLUE_2
        )

    elif choice == "2":
        if Confirm.ask("Are you sure you want to clear all package history?", default=False):
            history.entries = []
            history.save()
            print_success("Package history cleared")

    if choice != "3":
        view_history_menu()


def settings_menu():
    clear_screen()
    console.print(create_header())
    display_panel("Settings", "Configure application settings and preferences.", SilverBlueColors.BLUE_2)

    settings_options = [
        ("1", "View System Information", "Display system and Nix information"),
        ("2", "Check Nix Installation", "Verify Nix is properly installed"),
        ("3", "Clear Search History", "Delete recent search history"),
        ("4", "Return to Main Menu", "")
    ]

    console.print(create_menu_table("Settings Options", settings_options))
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")

    if choice == "1":
        system_info = {
            "App Version": VERSION,
            "Python Version": platform.python_version(),
            "Fedora Version": get_fedora_version(),
            "Architecture": platform.machine(),
            "User": os.environ.get("USER", "Unknown"),
            "Home Directory": os.path.expanduser("~"),
            "Config Directory": CONFIG_DIR,
            "Nix Installed": "Yes" if is_nix_installed() else "No",
        }

        info_content = "\n".join([f"{k}: {v}" for k, v in system_info.items()])
        display_panel("System Information", info_content, SilverBlueColors.BLUE_2)

    elif choice == "2":
        if is_nix_installed():
            print_success("Nix is installed and properly configured.")

            # Perform a quick check of nix functionality
            try:
                env = get_nix_env()
                result = run_command(["nix", "--version"], check=False, env=env)
                if result.returncode == 0:
                    print_success(f"Nix version: {result.stdout.strip()}")
                else:
                    print_warning("Nix is installed but not functioning correctly.")

                    if Confirm.ask("Would you like to reinitialize Nix?", default=True):
                        # Try to fix the Nix installation
                        if os.path.exists(NIX_PROFILE):
                            env = get_nix_env()
                            print_step("Reinitializing Nix environment...")

                            # Run a simple command to verify
                            test_result = run_command(["nix-env", "--version"], check=False, env=env)
                            if test_result.returncode == 0:
                                print_success("Nix environment reinitialized successfully.")
                            else:
                                print_error("Could not reinitialize Nix environment.")
                                print_warning("You may need to restart your system or manually source the Nix profile.")
            except Exception as e:
                print_error(f"Error checking Nix: {e}")
        else:
            print_warning("Nix is not installed.")
            if Confirm.ask("Would you like to install Nix now?", default=True):
                verbose = Confirm.ask("Enable verbose mode?", default=False)
                install_nix(verbose=verbose)

    elif choice == "3":
        config = AppConfig.load()
        if Confirm.ask("Clear search history?", default=False):
            config.recent_searches = []
            config.save()
            print_success("Search history cleared")

    Prompt.ask("Press Enter to continue" if choice != "4" else "Press Enter to return to the main menu")
    if choice != "4":
        settings_menu()


def get_fedora_version():
    try:
        with open('/etc/os-release', 'r') as f:
            content = f.read()
            for line in content.splitlines():
                if line.startswith('VERSION_ID='):
                    return line.split('=')[1].strip('"')
        return "Unknown"
    except Exception:
        return "Unknown"


def main():
    try:
        clear_screen()
        console.print(create_header())

        with Progress(
                SpinnerColumn(spinner_name="dots", style=f"bold {SilverBlueColors.BLUE_1}"),
                TextColumn(f"[bold {SilverBlueColors.BLUE_2}]Starting Fedora Silverblue Nix Manager..."),
                console=console
        ) as progress:
            task = progress.add_task("", total=100)
            ensure_config_directory()
            progress.update(task, completed=30, description="Checking configuration...")

            config = AppConfig.load()
            progress.update(task, completed=60, description="Loading settings...")

            # Check if Nix is installed
            config.nix_installed = is_nix_installed()
            config.save()

            progress.update(task, completed=90, description="Verifying Nix installation...")

            if not config.nix_installed:
                progress.update(task, completed=100, description="Nix not installed!")
                time.sleep(0.5)

                display_panel(
                    "Nix Not Installed",
                    "The Nix package manager is not installed on your system.\n"
                    "Install Nix to continue.",
                    SilverBlueColors.WARNING
                )

                if Confirm.ask("Install Nix now?", default=True):
                    verbose = Confirm.ask("Enable verbose mode?", default=False)
                    if not install_nix(verbose=verbose):
                        print_error("Failed to install Nix. Please install manually and try again.")
                        return
                else:
                    print_warning("Nix is required for this application to function.")
                    return
            else:
                progress.update(task, completed=100, description="Ready!")
                time.sleep(0.5)

        main_menu()
    except KeyboardInterrupt:
        print_warning("Operation cancelled by user")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        if Confirm.ask("Show detailed error information?", default=False):
            console.print_exception(show_locals=True)
        print_step("The application will now exit.")
    finally:
        cleanup()


def main_menu():
    while True:
        clear_screen()
        console.print(create_header())

        main_options = [
            ("1", "Search Packages", "Search for Nix packages to install"),
            ("2", "Manage Packages", "View and manage installed packages"),
            ("3", "View Package History", "View package installation history"),
            ("4", "Settings", "Configure application preferences"),
            ("5", "Exit", "Exit the application")
        ]

        console.print(create_menu_table("Main Menu", main_options))

        config = AppConfig.load()
        history = PackageHistory.load()

        stats_panel = Panel(
            Text.from_markup(
                f"Nix Status: [bold]{'Installed' if config.nix_installed else 'Not Installed'}[/]\n"
                f"Recent Searches: [bold]{len(config.recent_searches)}[/]\n"
                f"Installed Packages: [bold]{len(config.installed_packages)}[/]\n"
                f"Package Actions: [bold]{len(history.entries)}[/]\n"
            ),
            title="Quick Stats",
            border_style=SilverBlueColors.BLUE_3,
            box=ROUNDED,
            padding=(1, 2)
        )

        console.print(stats_panel)
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5"], default="5")

        if choice == "1":
            package_search_menu()
        elif choice == "2":
            manage_packages_menu()
        elif choice == "3":
            view_history_menu()
        elif choice == "4":
            settings_menu()
        elif choice == "5":
            clear_screen()
            console.print(
                Panel(
                    Text.from_markup(
                        "[bold]Thank you for using Fedora Silverblue Nix Manager![/]\n\n"
                        "Developed for seamless Nix package management on Fedora Silverblue."
                    ),
                    title="Goodbye!",
                    title_align="center",
                    border_style=SilverBlueColors.BLUE_2,
                    box=HEAVY,
                    padding=(2, 4)
                )
            )
            break


if __name__ == "__main__":
    main()