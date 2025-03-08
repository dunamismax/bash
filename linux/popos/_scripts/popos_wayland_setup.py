#!/usr/bin/env python3
"""
PopOS Wayland Installer
--------------------------------------------------
This script installs and configures the Wayland protocols on PopOS,
enabling Wayland as the default session and applying high‑DPI settings
(for example, for a 27″ 4K monitor). It also downloads and installs Visual Studio Code
with a desktop entry configured for Wayland.
--------------------------------------------------
Version: 1.0.0
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import os
import sys
import time
import signal
import shutil
import asyncio
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict

# Try to import required libraries and install if missing
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
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    from prompt_toolkit import prompt as pt_prompt
except ImportError:
    print("Required libraries not found. Installing them using pip...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyfiglet", "rich", "prompt_toolkit"],
        check=True,
    )
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

install_rich_traceback(show_locals=True)
console: Console = Console()

# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("wayland_installer.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("wayland-installer")

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "PopOS Wayland Installer"
VERSION: str = "1.0.0"

# Paths and URLs for VS Code installation (if desired)
VSCODE_DEB_URL: str = (
    "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"
)
VSCODE_DEB_PATH: str = "/tmp/vscode_latest.deb"
SYSTEM_DESKTOP_PATH: str = "/usr/share/applications/code.desktop"
USER_DESKTOP_PATH: str = os.path.expanduser("~/.local/share/applications/code.desktop")
GDM_CUSTOM_CONF: str = "/etc/gdm/custom.conf"


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


# ----------------------------------------------------------------
# Application Configuration Data Class
# ----------------------------------------------------------------
@dataclass
class AppConfig:
    """Configuration for the Wayland installer."""

    verbose: bool = False
    vscode_deb_url: str = VSCODE_DEB_URL
    vscode_deb_path: str = VSCODE_DEB_PATH
    system_desktop_path: str = SYSTEM_DESKTOP_PATH
    user_desktop_path: str = USER_DESKTOP_PATH
    gdm_custom_conf: str = GDM_CUSTOM_CONF
    wayland_packages: List[str] = field(
        default_factory=lambda: [
            "gnome-session-wayland",
            "mutter",
            "gnome-control-center",
            "gnome-shell",
            "gnome-terminal",
            "libwayland-client0",
            "libwayland-cursor0",
            "libwayland-egl1",
            "libwayland-server0",
            "xwayland",
            "wayland-protocols",
            "qt6-wayland",
            "qt5-wayland",
            "libqt5waylandclient5",
            "libqt5waylandcompositor5",
            "wayland-utils",
        ]
    )
    wayland_env_vars: Dict[str, str] = field(
        default_factory=lambda: {
            "GDK_BACKEND": "wayland",
            "QT_QPA_PLATFORM": "wayland",
            "SDL_VIDEODRIVER": "wayland",
            "MOZ_ENABLE_WAYLAND": "1",
            "CLUTTER_BACKEND": "wayland",
            "_JAVA_AWT_WM_NONREPARENTING": "1",
        }
    )
    # High DPI configuration for 27" 4K monitors
    high_dpi_enabled: bool = True
    high_dpi_scale: float = 1.5
    text_scaling_factor: float = 1.5


# ----------------------------------------------------------------
# UI Helper Functions
# ----------------------------------------------------------------
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """Create a dynamic ASCII banner header."""
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
        styled_text += f"[bold {color}]{line}[/]\n"
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        box=box.ROUNDED,
    )
    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, NordColors.RED, "✗")
    logger.error(message)


def print_success(message: str) -> None:
    print_message(message, NordColors.GREEN, "✓")
    logger.info(message)


def print_warning(message: str) -> None:
    print_message(message, NordColors.YELLOW, "⚠")
    logger.warning(message)


def print_info(message: str) -> None:
    print_message(message, NordColors.FROST_3, "ℹ")
    logger.info(message)


def print_step(message: str) -> None:
    print_message(message, NordColors.FROST_2, "→")
    logger.info(message)


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")
    console.print()


# ----------------------------------------------------------------
# Progress Manager
# ----------------------------------------------------------------
class ProgressManager:
    """Context manager for progress bars."""

    def __init__(self) -> None:
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(
                bar_width=40,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TextColumn("{task.fields[status]}"),
            console=console,
        )

    def __enter__(self) -> Progress:
        self.progress.start()
        return self.progress

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.progress.stop()


# ----------------------------------------------------------------
# Command Execution Helpers
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    capture_output: bool = False,
    verbose: bool = False,
    check: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run a command and handle its output."""
    if verbose:
        print_info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, capture_output=capture_output, text=True, check=check, **kwargs
    )
    if verbose and capture_output:
        if result.stdout:
            print_info(f"Output: {result.stdout.strip()}")
        if result.stderr:
            print_warning(f"Error Output: {result.stderr.strip()}")
    return result


async def run_command_async(
    cmd: List[str],
    capture_output: bool = False,
    verbose: bool = False,
    check: bool = True,
    timeout: int = 600,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run a command asynchronously."""
    if verbose:
        print_info(f"Running async command: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE if capture_output else None,
        stderr=asyncio.subprocess.PIPE if capture_output else None,
        **kwargs,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if verbose and capture_output:
            if stdout:
                print_info(f"Output: {stdout.decode().strip()}")
            if stderr:
                print_warning(f"Error Output: {stderr.decode().strip()}")
        if check and process.returncode != 0:
            err_msg = f"Command failed with exit code {process.returncode}"
            if capture_output and stderr:
                err_msg += f": {stderr.decode().strip()}"
            raise subprocess.CalledProcessError(
                process.returncode,
                cmd,
                stdout.decode() if stdout else None,
                stderr.decode() if stderr else None,
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout.decode() if stdout else None,
            stderr=stderr.decode() if stderr else None,
        )
    except asyncio.TimeoutError:
        try:
            process.terminate()
            await asyncio.sleep(0.5)
            process.kill()
        except Exception:
            pass
        raise TimeoutError(
            f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        )


# ----------------------------------------------------------------
# Installation and Configuration Functions
# ----------------------------------------------------------------
async def install_nala(config: AppConfig) -> bool:
    """Install Nala package manager."""
    print_section("Installing Nala Package Manager")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating apt cache", total=3.0)
            await run_command_async(
                ["apt-get", "update"], capture_output=True, verbose=config.verbose
            )
            progress.update(task_id, advance=1.0)
            progress.update(task_id, description="Installing nala")
            await run_command_async(
                ["apt-get", "install", "-y", "nala"],
                capture_output=True,
                verbose=config.verbose,
            )
            progress.update(task_id, advance=1.0)
            progress.update(task_id, description="Updating nala cache")
            await run_command_async(
                ["nala", "update"], capture_output=True, verbose=config.verbose
            )
            progress.update(
                task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
            )
        print_success("Nala package manager installed successfully")
        return True
    except Exception as e:
        print_error(f"Failed to install nala: {e}")
        return False


async def apply_system_updates(config: AppConfig) -> bool:
    """Apply pending system updates."""
    print_section("Applying System Updates")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating system packages", total=1.0)
            await run_command_async(["nala", "upgrade", "-y"], verbose=config.verbose)
            progress.update(
                task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
            )
        print_success("System updates applied successfully")
        return True
    except Exception as e:
        print_error(f"Failed to apply system updates: {e}")
        return False


async def install_wayland_packages(config: AppConfig) -> bool:
    """Install required Wayland packages."""
    print_section("Installing Wayland Packages")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Installing Wayland packages", total=1.0)
            await run_command_async(
                ["nala", "install", "-y"] + config.wayland_packages,
                verbose=config.verbose,
            )
            progress.update(
                task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
            )
        print_success("Wayland packages installed successfully")
        return True
    except Exception as e:
        print_error(f"Failed to install Wayland packages: {e}")
        return False


async def configure_gdm_for_wayland(config: AppConfig) -> bool:
    """Configure GDM to enable Wayland by default."""
    print_section("Configuring GDM for Wayland")
    gdm_conf_path = Path(config.gdm_custom_conf)
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating GDM configuration", total=1.0)
            if gdm_conf_path.exists():
                content = gdm_conf_path.read_text()
                updated = False
                if "WaylandEnable=false" in content:
                    content = content.replace(
                        "WaylandEnable=false", "WaylandEnable=true"
                    )
                    updated = True
                elif "WaylandEnable=true" not in content:
                    if "[daemon]" in content:
                        content = content.replace(
                            "[daemon]", "[daemon]\nWaylandEnable=true"
                        )
                    else:
                        content += "\n[daemon]\nWaylandEnable=true\n"
                    updated = True

                if "DefaultSession=" in content:
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if line.strip().startswith("DefaultSession="):
                            lines[i] = "DefaultSession=gnome-wayland.desktop"
                            updated = True
                    content = "\n".join(lines)
                else:
                    if "[daemon]" in content:
                        content = content.replace(
                            "[daemon]", "[daemon]\nDefaultSession=gnome-wayland.desktop"
                        )
                    else:
                        content += "\n[daemon]\nDefaultSession=gnome-wayland.desktop\n"
                    updated = True

                if updated:
                    gdm_conf_path.write_text(content)
                    progress.update(
                        task_id, advance=1.0, status=f"[{NordColors.GREEN}]Updated"
                    )
                    print_success(f"GDM configuration updated at {gdm_conf_path}")
                else:
                    progress.update(
                        task_id,
                        advance=1.0,
                        status=f"[{NordColors.GREEN}]Already configured",
                    )
                    print_info("GDM is already configured for Wayland")
            else:
                content = "[daemon]\nWaylandEnable=true\nDefaultSession=gnome-wayland.desktop\n"
                gdm_conf_path.write_text(content)
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Created"
                )
                print_success(f"Created new GDM configuration at {gdm_conf_path}")
        return True
    except Exception as e:
        print_error(f"Failed to configure GDM: {e}")
        return False


async def configure_wayland_environment(config: AppConfig) -> bool:
    """Configure Wayland environment variables in /etc/environment."""
    print_section("Configuring Wayland Environment Variables")
    etc_env = Path("/etc/environment")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating environment variables", total=1.0)
            current = etc_env.read_text() if etc_env.is_file() else ""
            vars_current = {}
            for line in current.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    vars_current[key.strip()] = val.strip()
            updated = False
            for key, val in config.wayland_env_vars.items():
                if " " in val and not (val.startswith('"') and val.endswith('"')):
                    val = f'"{val}"'
                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True
            if updated:
                new_content = (
                    "\n".join(f"{k}={v}" for k, v in vars_current.items()) + "\n"
                )
                etc_env.write_text(new_content)
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Updated"
                )
                print_success(f"Environment variables updated in {etc_env}")
            else:
                progress.update(
                    task_id,
                    advance=1.0,
                    status=f"[{NordColors.GREEN}]Already configured",
                )
                print_info(f"No changes needed in {etc_env}")
        return True
    except Exception as e:
        print_error(f"Failed to update environment variables: {e}")
        return False


async def download_vscode(config: AppConfig) -> bool:
    """Download the VS Code .deb package."""
    print_section("Downloading Visual Studio Code")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Downloading VS Code", total=1.0)
            await run_command_async(
                ["curl", "-L", config.vscode_deb_url, "-o", config.vscode_deb_path],
                verbose=config.verbose,
            )
            if os.path.exists(config.vscode_deb_path):
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
                )
                print_success(f"VS Code downloaded to {config.vscode_deb_path}")
                return True
            else:
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.RED}]Failed"
                )
                print_error("Download failed: file not found")
                return False
    except Exception as e:
        print_error(f"Failed to download VS Code: {e}")
        return False


async def install_vscode(config: AppConfig) -> bool:
    """Install the downloaded VS Code package."""
    print_section("Installing Visual Studio Code")
    if not os.path.exists(config.vscode_deb_path):
        print_error("VS Code package not found. Aborting installation.")
        return False
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Installing VS Code", total=1.0)
            await run_command_async(
                ["nala", "install", "-y", config.vscode_deb_path],
                verbose=config.verbose,
                check=False,
            )
            if os.path.exists("/usr/bin/code"):
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
                )
                print_success("VS Code installed successfully")
                return True
            else:
                progress.update(task_id, description="Fixing dependencies", status="")
                await run_command_async(
                    ["nala", "--fix-broken", "install", "-y"], verbose=config.verbose
                )
                if os.path.exists("/usr/bin/code"):
                    progress.update(
                        task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
                    )
                    print_success("Dependencies fixed. VS Code installation complete.")
                    return True
                else:
                    progress.update(
                        task_id, advance=1.0, status=f"[{NordColors.RED}]Failed"
                    )
                    print_error("VS Code installation failed")
                    return False
    except Exception as e:
        print_error(f"Installation error: {e}")
        return False


async def create_wayland_desktop_file(config: AppConfig) -> bool:
    """Create desktop entries for VS Code with Wayland support."""
    print_section("Configuring Desktop Entry")
    desktop_content = (
        "[Desktop Entry]\n"
        "Name=Visual Studio Code\n"
        "Comment=Code Editing. Redefined.\n"
        "GenericName=Text Editor\n"
        "Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n"
        "Icon=vscode\n"
        "Type=Application\n"
        "StartupNotify=false\n"
        "StartupWMClass=Code\n"
        "Categories=TextEditor;Development;IDE;\n"
        "MimeType=text/plain;application/x-code-workspace;\n"
    )
    success = True
    with ProgressManager() as progress:
        task_id = progress.add_task("Creating desktop entries", total=2.0)
        try:
            with open(config.system_desktop_path, "w") as f:
                f.write(desktop_content)
            print_success(
                f"System desktop entry created at {config.system_desktop_path}"
            )
            progress.update(task_id, advance=1.0)
        except Exception as e:
            print_error(f"Failed to create system desktop entry: {e}")
            success = False
            progress.update(task_id, advance=1.0, status=f"[{NordColors.RED}]Failed")
        try:
            os.makedirs(os.path.dirname(config.user_desktop_path), exist_ok=True)
            with open(config.user_desktop_path, "w") as f:
                f.write(desktop_content)
            print_success(f"User desktop entry created at {config.user_desktop_path}")
            progress.update(
                task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
            )
        except Exception as e:
            print_error(f"Failed to create user desktop entry: {e}")
            success = False
            progress.update(task_id, advance=1.0, status=f"[{NordColors.RED}]Failed")
    return success


async def verify_installation(config: AppConfig) -> bool:
    """Verify that the installation and configuration succeeded."""
    print_section("Verifying Installation")
    all_ok = True
    checks = [
        ("/usr/bin/code", "VS Code binary"),
        (config.system_desktop_path, "System desktop entry"),
        (config.user_desktop_path, "User desktop entry"),
        (config.gdm_custom_conf, "GDM configuration"),
        ("/etc/environment", "Wayland environment variables"),
    ]
    with ProgressManager() as progress:
        task_id = progress.add_task("Verifying components", total=len(checks))
        for path, desc in checks:
            if os.path.exists(path):
                print_success(f"{desc} found at {path}")
            else:
                print_error(f"{desc} missing at {path}")
                all_ok = False
            progress.update(task_id, advance=1.0)
    if os.path.exists(config.gdm_custom_conf):
        content = Path(config.gdm_custom_conf).read_text()
        if "WaylandEnable=true" in content:
            print_success("GDM configured to enable Wayland")
        else:
            print_warning("Wayland not explicitly enabled in GDM configuration")
            all_ok = False
    if os.path.exists(config.system_desktop_path):
        with open(config.system_desktop_path, "r") as f:
            if "--ozone-platform=wayland" in f.read():
                print_success("VS Code desktop entry configured for Wayland")
            else:
                print_warning("Wayland flags missing in VS Code desktop entry")
                all_ok = False
    if os.path.exists("/etc/environment"):
        env_content = Path("/etc/environment").read_text()
        if all(f"{key}=" in env_content for key in config.wayland_env_vars.keys()):
            print_success("Wayland environment variables configured")
        else:
            print_warning("Some Wayland environment variables not configured")
            all_ok = False
    if all_ok:
        print_success(
            "All components verified. Wayland and VS Code are successfully configured!"
        )
    else:
        print_warning("Some components are missing or misconfigured.")
    return all_ok


async def configure_high_dpi_settings(config: AppConfig) -> bool:
    """Configure high DPI scaling settings using gsettings."""
    print_section("Configuring High DPI Settings")
    if not config.high_dpi_enabled:
        print_info("High DPI settings are disabled in the configuration.")
        return True
    try:
        # Set the scaling factor (integer value) and text scaling factor (fractional)
        await run_command_async(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.interface",
                "scaling-factor",
                str(int(config.high_dpi_scale)),
            ],
            verbose=config.verbose,
        )
        await run_command_async(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.interface",
                "text-scaling-factor",
                str(config.text_scaling_factor),
            ],
            verbose=config.verbose,
        )
        print_success(
            f"High DPI settings applied: scaling-factor {int(config.high_dpi_scale)}, text-scaling-factor {config.text_scaling_factor}"
        )
        return True
    except Exception as e:
        print_error(f"Failed to configure High DPI settings: {e}")
        return False


# ----------------------------------------------------------------
# Main Installation Process
# ----------------------------------------------------------------
async def main_async() -> None:
    try:
        clear_screen()
        console.print(create_header())
        print_info("Starting Wayland installation for PopOS")
        config = AppConfig()
        # Must be run as root
        if os.geteuid() != 0:
            print_error("This script must be run as root. Please use sudo.")
            sys.exit(1)
        if not await install_nala(config):
            print_error("Failed to install nala. Aborting.")
            sys.exit(1)
        await apply_system_updates(config)
        if not await install_wayland_packages(config):
            print_error("Failed to install Wayland packages. Aborting.")
            sys.exit(1)
        if not await configure_gdm_for_wayland(config):
            print_warning("Failed to configure GDM. Continuing with other steps.")
        if not await configure_wayland_environment(config):
            print_warning(
                "Failed to update environment variables. Continuing with other steps."
            )
        # Configure high DPI settings for 4K display
        if not await configure_high_dpi_settings(config):
            print_warning(
                "High DPI configuration failed. You may need to configure it manually."
            )
        # VS Code installation (optional)
        if not await download_vscode(config):
            print_error("Failed to download VS Code. Skipping VS Code installation.")
        else:
            if await install_vscode(config):
                await create_wayland_desktop_file(config)
            else:
                print_error(
                    "Failed to install VS Code. Skipping desktop entry creation."
                )
        await verify_installation(config)
        print_section("Installation Complete")
        print_success("Wayland has been successfully installed and configured!")
        print_info("Please reboot your system to apply all changes: sudo reboot")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        logger.exception("Unexpected error during installation")
        sys.exit(1)


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Installation interrupted by user.")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        logger.exception("Unexpected error in main function")
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    main()
