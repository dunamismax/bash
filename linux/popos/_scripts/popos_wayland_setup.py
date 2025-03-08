#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import time
import shutil
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Any, Callable, Union
from pathlib import Path

try:
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
except ImportError:
    print(
        "Required libraries not found. Installing them using pip...\npip install rich"
    )
    subprocess.run([sys.executable, "-m", "pip", "install", "rich"], check=True)
    print("Dependencies installed. Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Initialize rich
install_rich_traceback(show_locals=True)
console: Console = Console()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("wayland_installer.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("wayland-installer")

# Configuration and Constants
APP_NAME: str = "PopOS Wayland Installer"
VERSION: str = "1.0.0"
VSCODE_DEB_URL: str = (
    "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"
)
VSCODE_DEB_PATH: str = "/tmp/vscode_latest.deb"
SYSTEM_DESKTOP_PATH: str = "/usr/share/applications/code.desktop"
USER_DESKTOP_PATH: str = os.path.expanduser("~/.local/share/applications/code.desktop")
GDM_CUSTOM_CONF: str = "/etc/gdm/custom.conf"


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


# UI Helper Functions
def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def create_header() -> Panel:
    """Create a header panel with the app name."""
    return Panel(
        Text(APP_NAME, style=f"bold {NordColors.FROST_2}"),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a formatted message to the console."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    """Print an error message to the console."""
    print_message(message, NordColors.RED, "✗")
    logger.error(message)


def print_success(message: str) -> None:
    """Print a success message to the console."""
    print_message(message, NordColors.GREEN, "✓")
    logger.info(message)


def print_warning(message: str) -> None:
    """Print a warning message to the console."""
    print_message(message, NordColors.YELLOW, "⚠")
    logger.warning(message)


def print_info(message: str) -> None:
    """Print an info message to the console."""
    print_message(message, NordColors.FROST_3, "ℹ")
    logger.info(message)


def print_step(message: str) -> None:
    """Print a step message to the console."""
    print_message(message, NordColors.FROST_2, "→")
    logger.info(message)


def print_section(title: str) -> None:
    """Print a section header to the console."""
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


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
            print_info(f"Command output: {result.stdout.strip()}")
        if result.stderr:
            print_warning(f"Command error output: {result.stderr.strip()}")

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
        print_info(f"Running command asynchronously: {' '.join(cmd)}")

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
                stdout_str = stdout.decode("utf-8")
                print_info(f"Command output: {stdout_str.strip()}")
            if stderr:
                stderr_str = stderr.decode("utf-8")
                print_warning(f"Command error output: {stderr_str.strip()}")

        if check and process.returncode != 0:
            error_message = f"Command failed with return code {process.returncode}"
            if capture_output and stderr:
                error_message += f": {stderr.decode('utf-8').strip()}"
            raise subprocess.CalledProcessError(
                process.returncode,
                cmd,
                stdout.decode("utf-8") if stdout else None,
                stderr.decode("utf-8") if stderr else None,
            )

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout.decode("utf-8") if stdout else None,
            stderr=stderr.decode("utf-8") if stderr else None,
        )

    except asyncio.TimeoutError:
        try:
            process.terminate()
            await asyncio.sleep(0.5)
            process.kill()
        except:
            pass
        raise TimeoutError(
            f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        )


async def install_nala(config: AppConfig) -> bool:
    """Install nala package manager."""
    print_section("Installing Nala Package Manager")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating apt cache", total=3.0)

            # Update apt cache
            await run_command_async(
                ["apt-get", "update"], capture_output=True, verbose=config.verbose
            )
            progress.update(task_id, advance=1.0, status="")

            # Install nala
            progress.update(task_id, description="Installing nala", status="")
            await run_command_async(
                ["apt-get", "install", "-y", "nala"],
                capture_output=True,
                verbose=config.verbose,
            )
            progress.update(task_id, advance=1.0, status="")

            # Update nala cache
            progress.update(task_id, description="Updating nala cache", status="")
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


async def install_wayland_packages(config: AppConfig) -> bool:
    """Install necessary Wayland packages."""
    print_section("Installing Wayland Packages")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Installing Wayland packages", total=1.0)

            # Install packages with nala
            package_list = " ".join(config.wayland_packages)
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
    """Configure GDM to use Wayland by default."""
    print_section("Configuring GDM for Wayland")
    gdm_conf_path = Path(config.gdm_custom_conf)

    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating GDM configuration", total=1.0)

            if gdm_conf_path.exists():
                # Read current config
                with open(gdm_conf_path, "r") as f:
                    content = f.read()

                # Check for WaylandEnable
                if "WaylandEnable=false" in content:
                    # Replace with true
                    content = content.replace(
                        "WaylandEnable=false", "WaylandEnable=true"
                    )
                    updated = True
                else:
                    # Check if we need to add the setting
                    if "WaylandEnable=true" not in content:
                        # Find daemon section or add it
                        if "[daemon]" in content:
                            content = content.replace(
                                "[daemon]", "[daemon]\nWaylandEnable=true"
                            )
                        else:
                            content += "\n[daemon]\nWaylandEnable=true\n"
                        updated = True
                    else:
                        updated = False

                # Check for DefaultSession
                if "DefaultSession=" in content:
                    # Find and replace any DefaultSession line
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if line.strip().startswith("DefaultSession="):
                            lines[i] = "DefaultSession=gnome-wayland.desktop"
                            updated = True
                    content = "\n".join(lines)
                else:
                    # Add DefaultSession to daemon section
                    if "[daemon]" in content:
                        content = content.replace(
                            "[daemon]", "[daemon]\nDefaultSession=gnome-wayland.desktop"
                        )
                    else:
                        content += "\n[daemon]\nDefaultSession=gnome-wayland.desktop\n"
                    updated = True

                # Write updated config if changes were made
                if updated:
                    with open(gdm_conf_path, "w") as f:
                        f.write(content)
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
                # Create new config file
                content = "[daemon]\nWaylandEnable=true\nDefaultSession=gnome-wayland.desktop\n"
                with open(gdm_conf_path, "w") as f:
                    f.write(content)
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Created"
                )
                print_success(f"Created new GDM configuration at {gdm_conf_path}")

        return True
    except Exception as e:
        print_error(f"Failed to configure GDM: {e}")
        return False


async def configure_wayland_environment(config: AppConfig) -> bool:
    """Configure Wayland environment variables."""
    print_section("Configuring Wayland Environment Variables")
    etc_env = Path("/etc/environment")

    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Updating environment variables", total=1.0)

            # Read current environment file
            if etc_env.is_file():
                current = etc_env.read_text()
            else:
                current = ""

            # Parse variables
            vars_current = {}
            for line in current.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    vars_current[key.strip()] = val.strip()

            # Update Wayland variables
            updated = False
            for key, val in config.wayland_env_vars.items():
                # Check if quotes are needed
                if " " in val and not (val.startswith('"') and val.endswith('"')):
                    val = f'"{val}"'

                if vars_current.get(key) != val:
                    vars_current[key] = val
                    updated = True

            # Write updated environment file if needed
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
    """Download VS Code .deb package."""
    print_section("Downloading Visual Studio Code")
    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Downloading VS Code", total=1.0)

            # Download VS Code using curl
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
    """Install the downloaded VS Code .deb package."""
    print_section("Installing Visual Studio Code")
    if not os.path.exists(config.vscode_deb_path):
        print_error("VS Code package not found. Aborting installation.")
        return False

    try:
        with ProgressManager() as progress:
            task_id = progress.add_task("Installing package", total=1.0)

            # Install using nala
            await run_command_async(
                ["nala", "install", "-y", config.vscode_deb_path],
                verbose=config.verbose,
                check=False,  # Don't check return code, we'll handle errors manually
            )

            # Check if VS Code binary exists
            if os.path.exists("/usr/bin/code"):
                progress.update(
                    task_id, advance=1.0, status=f"[{NordColors.GREEN}]Complete"
                )
                print_success("VS Code installed successfully")
                return True
            else:
                # Try to fix with nala
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
    """Create desktop entries with Wayland support."""
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

        # Create system desktop entry
        try:
            with open(config.system_desktop_path, "w") as f:
                f.write(desktop_content)
            print_success(
                f"System desktop entry created at {config.system_desktop_path}"
            )
            progress.update(task_id, advance=1.0, status="")
        except Exception as e:
            print_error(f"Failed to create system desktop entry: {e}")
            success = False
            progress.update(task_id, advance=1.0, status=f"[{NordColors.RED}]Failed")

        # Create user desktop entry
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
    """Verify that everything is correctly installed and configured."""
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

    # Check Wayland configuration in GDM
    if os.path.exists(config.gdm_custom_conf):
        with open(config.gdm_custom_conf, "r") as f:
            gdm_content = f.read()
            if "WaylandEnable=true" in gdm_content:
                print_success("GDM configured to enable Wayland")
            else:
                print_warning("Wayland not explicitly enabled in GDM configuration")
                all_ok = False

    # Check desktop entry for Wayland flags
    if os.path.exists(config.system_desktop_path):
        with open(config.system_desktop_path, "r") as f:
            if "--ozone-platform=wayland" in f.read():
                print_success("VS Code desktop entry configured for Wayland")
            else:
                print_warning("Wayland flags missing in VS Code desktop entry")
                all_ok = False

    # Check environment variables
    if os.path.exists("/etc/environment"):
        env_content = Path("/etc/environment").read_text()
        env_vars_found = all(
            f"{key}=" in env_content for key in config.wayland_env_vars.keys()
        )
        if env_vars_found:
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


async def apply_system_updates(config: AppConfig) -> bool:
    """Apply any pending system updates."""
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


async def main_async() -> None:
    """Main async function to run the installation process."""
    try:
        # Start installation
        clear_screen()
        console.print(create_header())
        print_info(f"Starting Wayland installation for PopOS")

        # Create config
        config = AppConfig()

        # Check if running as root
        if os.geteuid() != 0:
            print_error("This script must be run as root. Please use sudo.")
            sys.exit(1)

        # Install nala first
        if not await install_nala(config):
            print_error("Failed to install nala. Aborting.")
            sys.exit(1)

        # Apply system updates
        await apply_system_updates(config)

        # Install Wayland packages
        if not await install_wayland_packages(config):
            print_error("Failed to install Wayland packages. Aborting.")
            sys.exit(1)

        # Configure GDM
        if not await configure_gdm_for_wayland(config):
            print_warning("Failed to configure GDM. Continuing with other steps.")

        # Configure Wayland environment variables
        if not await configure_wayland_environment(config):
            print_warning(
                "Failed to configure Wayland environment variables. Continuing with other steps."
            )

        # Download VS Code
        if not await download_vscode(config):
            print_error("Failed to download VS Code. Skipping VS Code installation.")
        else:
            # Install VS Code
            if await install_vscode(config):
                # Create VS Code Wayland desktop entry
                await create_wayland_desktop_file(config)
            else:
                print_error(
                    "Failed to install VS Code. Skipping desktop entry creation."
                )

        # Verify installation
        await verify_installation(config)

        # Final message
        print_section("Installation Complete")
        print_success("Wayland has been successfully installed and configured!")
        print_info("Please reboot your system to apply all changes: sudo reboot")

    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        logger.exception("Unexpected error during installation")
        sys.exit(1)


def main() -> None:
    """Main entry point of the application."""
    try:
        # Create and get a reference to the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the main async function
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Installation interrupted by user.")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        logger.exception("Unexpected error in main function")
    finally:
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


if __name__ == "__main__":
    main()
