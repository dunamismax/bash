#!/usr/bin/env python3
"""
Fedora Server Setup & Hardening Utility (Unattended)
-------------------------------------------------------

This fully automated utility performs:
  • Pre-flight checks & backups (including snapshot backups if available)
  • System update & basic configuration (timezone, packages)
  • Repository & shell setup (cloning GitHub repos, updating shell configs)
  • Security hardening (SSH, sudoers, firewall using firewalld, Fail2ban)
  • User customization & script deployment
  • Permissions & advanced storage configuration (home permissions)
  • Automatic updates & further security (unattended upgrades, AppArmor - placeholder)
  • Final system checks & no automatic reboot

Run this script with root privileges.
"""

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
import asyncio
import atexit
import datetime
import filecmp
import gzip
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, TypeVar

try:
    import pyfiglet
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.logging import RichHandler

    # Only import the spinner and text column to avoid flashing progress bars
    from rich.progress import SpinnerColumn, TextColumn
    from rich.align import Align
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "rich", "pyfiglet"]
        )
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print(
            "Please install the required packages manually: pip install rich pyfiglet"
        )
        sys.exit(1)

install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Nord-Themed Colors and Theme Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette definitions for consistent UI styling."""

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


nord_theme = Theme(
    {
        "banner": f"bold {NordColors.FROST_2}",
        "header": f"bold {NordColors.FROST_2}",
        "info": NordColors.GREEN,
        "warning": NordColors.YELLOW,
        "error": NordColors.RED,
        "debug": NordColors.POLAR_NIGHT_3,
        "success": NordColors.GREEN,
    }
)
console = Console(theme=nord_theme)

# ----------------------------------------------------------------
# Global Configuration & Status Tracking
# ----------------------------------------------------------------
APP_NAME: str = "Fedora Server Setup & Hardening"  # Changed from Desktop
VERSION: str = "1.0.0"
OPERATION_TIMEOUT: int = 300  # default timeout for operations in seconds

SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "repo_shell": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "user_custom": {"status": "pending", "message": ""},  # Removed 'services' for now
    "permissions_storage": {"status": "pending", "message": ""},
    "additional_tools": {
        "status": "pending",
        "message": "",
    },  # Renamed from additional_apps
    "cleanup_final": {
        "status": "pending",
        "message": "",
    },  # Removed 'auto_updates' for now
    "final": {"status": "pending", "message": ""},
}

T = TypeVar("T")


# ----------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------
@dataclass
class Config:
    """Configuration for the Fedora Server setup process.

    This class defines paths, system package lists (for dnf/rpm installs),
    and SSH/firewall settings tailored for a server environment.
    """

    LOG_FILE: str = "/var/log/fedora_server_setup.log"  # Changed log file name
    USERNAME: str = "sawyer"  # Keep username configurable
    USER_HOME: Path = field(
        default_factory=lambda: Path(f"/home/{Config.USERNAME}")
    )  # Dynamic user home

    # Essential system packages for Fedora Server
    PACKAGES: List[str] = field(
        default_factory=lambda: [
            # Shells and core editors
            "bash",
            "vim",
            "nano",
            "screen",
            "tmux",
            "neovim",
            # System monitoring & diagnostics
            "htop",
            "btop",
            "tree",
            "iftop",
            "mtr",
            "iotop",
            "glances",
            "sysstat",
            "atop",
            "powertop",
            "nmon",
            "dstat",
            # Network and security essentials
            "git",
            "openssh-server",
            "firewalld",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "bash-completion",
            "net-tools",
            "nmap",
            "tcpdump",
            "fail2ban",
            "netcat",
            "arp-scan",
            "clamav",
            "lynis",
            "rkhunter",
            "aide",  # Added more security tools
            # Core utilities
            "python3",
            "python3-pip",
            "ca-certificates",
            "dnf-plugins-core",
            "gnupg2",
            "gnupg",
            "pinentry",  # Pinentry for GPG
            # Development tools (optional, but often useful on servers)
            "gcc",
            "gcc-c++",
            "make",
            "cmake",
            "ninja-build",
            "meson",
            "gettext",
            "pkgconf",
            "python3-devel",
            "openssl-devel",
            "libffi-devel",
            "zlib-devel",
            "readline-devel",
            "bzip2-devel",
            "ncurses-devel",
            "gdbm-devel",
            "nss-devel",
            "libxml2-devel",
            "xmlsec1-openssl-devel",
            "clang",
            "llvm",
            "golang",
            "gdb",
            "cargo",
            "rust",
            "jq",
            "yq",
            "yamllint",
            "shellcheck",
            "patch",
            "diffstat",
            "flex",
            "bison",
            "ctags",
            "cscope",
            "perf",
            # Network utilities
            "traceroute",
            "bind-utils",
            "iproute",
            "iputils",
            "restic",
            "whois",
            "dnsmasq",
            "openvpn",
            "wireguard-tools",
            "nftables",
            "ipcalc",
            "socat",
            "lsof",
            "psmisc",
            # Enhanced CLI tools
            "zsh",
            "fzf",
            "bat",
            "ripgrep",
            "ncdu",
            "fd-find",
            "autojump",
            "direnv",
            "zoxide",
            "progress",
            "pv",
            "tmux-powerline",
            "the_silver_searcher",
            # Container tools (common on servers)
            "docker",
            "docker-compose",
            "podman",
            "buildah",
            "skopeo",
            "nodejs",
            "npm",
            "yarn",
            "autoconf",
            "automake",
            "libtool",
            # Debugging utilities
            "strace",
            "ltrace",
            "valgrind",
            "tig",
            "colordiff",
            "tmate",
            "iperf3",
            "httpie",
            "ngrep",
            "gron",
            "entr",
            # Database clients (CLI)
            "mariadb",
            "postgresql",
            "sqlite",
            "redis",  # Removed pgadmin4
            # Virtualization host tools
            "qemu-kvm",
            "libvirt",
            "libvirt-client",  # Removed virt-manager GUI
            # File compression and archiving
            "p7zip",
            "p7zip-plugins",
            "unrar",
            "unzip",
            "zip",
            "tar",
            "pigz",
            "lbzip2",
            "lz4",
            # TUI File managers
            "mc",
            "ranger",
            "nnn",
            "vifm",  # Removed GUI ones
            # System backup tools
            "duplicity",
            "borgbackup",
            "rclone",
            "syncthing",  # Removed GUI Timeshift/Backintime
        ]
    )

    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "PermitRootLogin": "no",
            "PasswordAuthentication": "yes",  # Consider changing to 'no' post-setup for key-only auth
            "X11Forwarding": "no",  # Changed from yes to no
            "MaxAuthTries": "3",
            "ClientAliveInterval": "300",
            "ClientAliveCountMax": "3",
            "ChallengeResponseAuthentication": "no",  # Added for clarity
            "UsePAM": "yes",  # Ensure PAM is used
            "PrintMotd": "no",  # Optional: disable default motd if custom is used
            "AcceptEnv": "LANG LC_*",  # Limit accepted env vars
        }
    )

    FIREWALL_PORTS: List[str] = field(
        default_factory=lambda: ["22", "80", "443"]
    )  # Common server ports

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------
# UI Helper Functions (Keep for nice CLI output)
# ----------------------------------------------------------------
def clear_screen() -> None:
    console.clear()


def create_header(title: str = APP_NAME) -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    fonts: List[str] = ["slant", "small", "digital", "mini", "smslant"]
    font_to_use: str = fonts[0]
    if term_width < 60:
        font_to_use = fonts[1]
    elif term_width < 40:
        font_to_use = fonts[2]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=min(term_width - 10, 120))
            ascii_art = fig.renderText(title)
            if ascii_art.strip():
                break
        except Exception:
            continue  # Try next font if one fails
    if not ascii_art.strip():  # Fallback if all fonts fail
        ascii_art = title

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))
    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")
    return Panel(
        Align.center(combined_text),
        border_style=NordColors.FROST_1,
        padding=(1, 2),
        title=Text(f"{APP_NAME} v{VERSION}", style=f"bold {NordColors.SNOW_STORM_2}"),
        title_align="right",
        subtitle=Text(
            "Unattended Server Mode", style=f"bold {NordColors.SNOW_STORM_1}"
        ),  # Updated subtitle
        subtitle_align="center",
    )


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


def print_section(title: str) -> None:
    console.print()
    console.print(f"[bold {NordColors.FROST_3}]{title}[/]")
    console.print(f"[{NordColors.FROST_3}]{'─' * len(title)}[/]")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[{style}]{message}[/]"),
        border_style=style,
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def print_status_report() -> None:
    table = Table(title="Setup Status Report", style="banner")
    table.add_column("Task", style="header")
    table.add_column("Status", style="info")
    table.add_column("Message", style="info")
    for key, data in SETUP_STATUS.items():
        status_color = {
            "pending": "debug",
            "in_progress": "warning",
            "success": "success",
            "failed": "error",
        }.get(data["status"].lower(), "info")
        table.add_row(
            key.replace("_", " ").title(),
            f"[{status_color}]{data['status'].upper()}[/{status_color}]",
            data["message"],
        )
    console.print(
        Panel(
            table,
            title="[banner]Fedora Server Setup Status[/banner]",  # Updated title
            border_style=NordColors.FROST_3,
        )
    )


# ----------------------------------------------------------------
# Logger Setup
# ----------------------------------------------------------------
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fedora_server_setup")  # Changed logger name
    logger.setLevel(logging.DEBUG)
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    # Keep RichHandler for nice console output on server CLI
    console_handler = RichHandler(
        console=console, rich_tracebacks=True, show_path=False
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    # File Handler for detailed logging
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    try:
        os.chmod(str(log_file), 0o600)  # Secure log file permissions
    except Exception as e:
        logger.warning(f"Could not set permissions on log file {log_file}: {e}")
    return logger


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
async def signal_handler_async(signum: int, frame: Any) -> None:
    sig = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logger = logging.getLogger("fedora_server_setup")
    logger.error(f"Script interrupted by {sig}. Initiating cleanup.")
    try:
        if "setup_instance" in globals() and globals()["setup_instance"]:
            await globals()["setup_instance"].cleanup_async()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")
    try:
        loop = asyncio.get_running_loop()
        tasks = [
            task
            for task in asyncio.all_tasks(loop)
            if task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()
    except Exception as e:
        logger.error(f"Error stopping event loop: {e}")
    sys.exit(
        130
        if signum == signal.SIGINT
        else 143
        if signum == signal.SIGTERM
        else 128 + signum
    )


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig, None))
        )


# ----------------------------------------------------------------
# Download Helper
# ----------------------------------------------------------------
async def download_file_async(
    url: str, dest: Union[str, Path], timeout: int = 300
) -> None:
    dest = Path(dest)
    logger = logging.getLogger("fedora_server_setup")
    if dest.exists():
        logger.info(f"File {dest} already exists; skipping download.")
        return
    logger.info(f"Downloading {url} to {dest}...")
    loop = asyncio.get_running_loop()
    try:
        # Prioritize curl or wget if available (better progress/resume)
        cmd = None
        if shutil.which("curl"):
            cmd = ["curl", "-fL", "-o", str(dest), url, "--progress-bar"]
        elif shutil.which("wget"):
            cmd = ["wget", "-q", "--show-progress", "-O", str(dest), url]

        if cmd:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            if proc.returncode != 0:
                stderr_str = (
                    stderr_data.decode("utf-8", errors="ignore") if stderr_data else ""
                )
                raise Exception(
                    f"{cmd[0]} failed with return code {proc.returncode}. Stderr: {stderr_str.strip()}"
                )
        else:
            # Fallback to urllib if curl/wget not found
            import urllib.request

            logger.warning("curl/wget not found, using basic Python download.")
            await loop.run_in_executor(None, urllib.request.urlretrieve, url, dest)
        logger.info(f"Download complete: {dest}")
    except asyncio.TimeoutError:
        logger.error(f"Download timed out after {timeout} seconds for {url}")
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise


# ----------------------------------------------------------------
# Progress Utility: Run Function with Spinner Indicator
# ----------------------------------------------------------------
async def run_with_progress_async(
    description: str,
    func: Callable[..., Any],
    *args: Any,
    task_name: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    if task_name and task_name in SETUP_STATUS:
        SETUP_STATUS[task_name]["status"] = "in_progress"
        SETUP_STATUS[task_name]["message"] = f"{description} in progress..."
    else:
        logger = logging.getLogger("fedora_server_setup")
        logger.warning(f"Task name '{task_name}' not found in SETUP_STATUS.")

    from rich.progress import (
        Progress,
    )  # Keep import local to avoid potential issues if rich fails early

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn("{task.description}"),
        console=console,
        transient=True,  # Spinner disappears on completion
    ) as progress:
        task_id = progress.add_task(description, total=None)  # Indeterminate progress
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                loop = asyncio.get_running_loop()
                # Run synchronous functions in an executor thread
                result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            elapsed = time.time() - start
            progress.update(task_id, completed=100)  # Mark as complete visually
            console.print(
                f"[success]✓ {description} completed in {elapsed:.2f}s[/success]"
            )
            if task_name and task_name in SETUP_STATUS:
                SETUP_STATUS[task_name]["status"] = "success"
                SETUP_STATUS[task_name]["message"] = f"Completed in {elapsed:.2f}s"
            return result
        except Exception as e:
            elapsed = time.time() - start
            progress.update(
                task_id, completed=100
            )  # Mark as complete visually even on failure
            console.print(
                f"[error]✗ {description} failed in {elapsed:.2f}s: {e}[/error]"
            )
            if task_name and task_name in SETUP_STATUS:
                SETUP_STATUS[task_name]["status"] = "failed"
                SETUP_STATUS[task_name]["message"] = (
                    f"Failed after {elapsed:.2f}s: {str(e)}"
                )
            # Re-raise the exception so the main loop knows something failed
            raise


# ----------------------------------------------------------------
# Command Execution Utilities
# ----------------------------------------------------------------
async def run_command_async(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = True,  # Default to text=True for easier handling
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    logger = logging.getLogger("fedora_server_setup")
    cmd_str = " ".join(cmd)
    logger.debug(f"Running command: {cmd_str}")
    stdout_pipe = asyncio.subprocess.PIPE if capture_output else None
    stderr_pipe = asyncio.subprocess.PIPE if capture_output else None

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=stdout_pipe, stderr=stderr_pipe, env=process_env
        )
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        # Decode output if requested and data exists
        stdout_res = (
            stdout_data.decode("utf-8", errors="ignore")
            if capture_output and stdout_data and text
            else stdout_data
        )
        stderr_res = (
            stderr_data.decode("utf-8", errors="ignore")
            if capture_output and stderr_data and text
            else stderr_data
        )

        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_res if capture_output else None,
            stderr=stderr_res if capture_output else None,
        )

        if check and proc.returncode != 0:
            # Log error output if available
            error_message = (
                f"Command '{cmd_str}' failed with return code {proc.returncode}."
            )
            if capture_output and stderr_res:
                error_message += f"\nStderr:\n{stderr_res.strip()}"
            elif capture_output and stdout_res:  # Sometimes errors go to stdout
                error_message += f"\nStdout:\n{stdout_res.strip()}"
            logger.error(error_message)
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout_res, stderr=stderr_res
            )

        # Log successful command output at DEBUG level if captured
        if capture_output and stdout_res:
            logger.debug(f"Command '{cmd_str}' stdout:\n{stdout_res.strip()}")
        if capture_output and stderr_res:  # Log stderr even on success if non-empty
            logger.debug(f"Command '{cmd_str}' stderr:\n{stderr_res.strip()}")

        return result
    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout} seconds: {cmd_str}")
        # Try to kill the process if possible
        if "proc" in locals() and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()  # Wait briefly for kill confirmation
            except ProcessLookupError:
                pass  # Process already finished
            except Exception as kill_e:
                logger.warning(f"Failed to kill timed-out process {proc.pid}: {kill_e}")
        raise TimeoutError(f"Command '{cmd_str}' timed out after {timeout} seconds.")
    except FileNotFoundError:
        logger.error(
            f"Command not found: {cmd[0]}. Ensure it is installed and in PATH."
        )
        raise
    except Exception as e:
        logger.error(f"Error executing command '{cmd_str}': {e}")
        raise


async def command_exists_async(cmd: str) -> bool:
    try:
        # Use 'command -v' for better shell builtin/alias handling vs 'which'
        await run_command_async(["command", "-v", cmd], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ----------------------------------------------------------------
# Main Setup Class for Fedora Server
# ----------------------------------------------------------------
class FedoraServerSetup:  # Renamed class
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self._current_task = None  # Keep track for potential detailed status later

    async def print_section_async(self, title: str) -> None:
        # Use the existing UI helper, but log the section start too
        print_section(title)
        self.logger.info(f"--- Starting Phase: {title} ---")

    async def backup_file_async(self, file_path: Union[str, Path]) -> Optional[str]:
        file_path = Path(file_path)
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Place backups in a dedicated subdir if possible
        backup_dir = file_path.parent / ".backups"
        try:
            backup_dir.mkdir(
                exist_ok=True, mode=0o700
            )  # Create if needed, restricted access
            backup_path = backup_dir / f"{file_path.name}.bak.{timestamp}"
            # Use run_in_executor for file IO
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: shutil.copy2(file_path, backup_path)
            )
            self.logger.info(f"Backed up {file_path} to {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.error(f"Failed to backup {file_path}: {e}")
            # Fallback to same directory if subdir fails
            try:
                backup_path_fallback = file_path.with_suffix(
                    file_path.suffix + f".bak.{timestamp}"
                )
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, lambda: shutil.copy2(file_path, backup_path_fallback)
                )
                self.logger.info(
                    f"Backed up {file_path} to {backup_path_fallback} (fallback location)"
                )
                return str(backup_path_fallback)
            except Exception as fallback_e:
                self.logger.error(
                    f"Fallback backup for {file_path} also failed: {fallback_e}"
                )
                return None

    async def cleanup_async(self) -> None:
        self.logger.info("Performing cleanup before exit...")
        try:
            tmp = Path(tempfile.gettempdir())
            # Be specific about what to remove to avoid deleting unrelated files
            for item in tmp.glob(
                "fedora_server_setup_*"
            ):  # Use a unique prefix if needed
                try:
                    if item.is_file():
                        item.unlink()
                        self.logger.debug(f"Cleaned up temporary file: {item}")
                    elif item.is_dir():
                        shutil.rmtree(item)
                        self.logger.debug(f"Cleaned up temporary directory: {item}")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to clean up temporary item {item}: {e}"
                    )
            # Rotate logs on exit
            try:
                await self.rotate_logs_async()
            except Exception as e:
                self.logger.warning(f"Failed to rotate logs during cleanup: {e}")
            self.logger.info("Cleanup completed.")
        except Exception as e:
            self.logger.error(f"General cleanup process failed: {e}")

    async def rotate_logs_async(self, log_file: Optional[str] = None) -> bool:
        if log_file is None:
            log_file = self.config.LOG_FILE
        log_path = Path(log_file)
        if not log_path.is_file() or log_path.stat().st_size == 0:
            self.logger.info(
                f"Log file {log_path} does not exist or is empty. Skipping rotation."
            )
            return False
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_path = log_path.parent / f"{log_path.stem}.{timestamp}.log.gz"
            loop = asyncio.get_running_loop()
            # Perform compression in executor thread
            await loop.run_in_executor(
                None, self._compress_log, log_path, str(rotated_path)
            )
            self.logger.info(f"Log rotated to {rotated_path}")
            # Optionally truncate the original log file after rotation
            await loop.run_in_executor(None, lambda: open(log_path, "w").close())
            return True
        except Exception as e:
            self.logger.error(f"Log rotation failed for {log_path}: {e}")
            return False

    def _compress_log(self, log_path: Path, rotated_path: str) -> None:
        # This runs in an executor thread
        try:
            with open(log_path, "rb") as f_in:
                with gzip.open(rotated_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Set permissions on the rotated log
            os.chmod(rotated_path, 0o600)
        except Exception as e:
            # Log error here as well, as it might be missed otherwise
            logging.error(
                f"Error during log compression from {log_path} to {rotated_path}: {e}"
            )
            raise  # Re-raise to be caught by the caller

    async def has_internet_connection_async(
        self, host: str = "8.8.8.8", port: int = 53, timeout: int = 5
    ) -> bool:
        # Try connecting to Google DNS (or other reliable host) on port 53 (DNS)
        # This avoids relying on ICMP (ping) which might be blocked
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            self.logger.debug(f"Successfully connected to {host}:{port}.")
            return True
        except (asyncio.TimeoutError, OSError) as e:
            self.logger.warning(f"Network check failed for {host}:{port}: {e}")
            # Fallback: Try ping if connectivity check failed
            try:
                await run_command_async(
                    ["ping", "-c", "1", "-W", "3", host],
                    capture_output=True,
                    check=True,
                )
                self.logger.debug(f"Successfully pinged {host}.")
                return True
            except Exception:
                self.logger.warning(f"Ping check also failed for {host}.")
                return False

    # ----------------------------------------------------------------
    # Phase 0: Pre-Flight Checks
    # ----------------------------------------------------------------
    async def phase_preflight(self) -> bool:
        await self.print_section_async("Pre-flight Checks & Backups")
        try:
            # Combine checks for efficiency, fail fast
            await run_with_progress_async(
                "Checking prerequisites (root, network, OS)",
                self.run_prerequisite_checks_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Saving configuration snapshot",
                self.save_config_snapshot_async,
                task_name="preflight",
            )
            self.logger.info("Pre-flight checks passed.")
            SETUP_STATUS["preflight"]["status"] = "success"
            SETUP_STATUS["preflight"]["message"] = (
                "All checks passed, config snapshot created."
            )
            return True
        except Exception as e:
            self.logger.critical(f"Pre-flight phase failed critically: {e}")
            SETUP_STATUS["preflight"]["status"] = "failed"
            SETUP_STATUS["preflight"]["message"] = f"Failed: {str(e)}"
            # No point continuing if pre-flight fails
            return False  # Signal failure to the main loop

    async def run_prerequisite_checks_async(self) -> None:
        """Combines root, network, and Fedora checks."""
        # 1. Root Check
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root or with sudo.")
            raise PermissionError("Root privileges are required.")
        self.logger.info("Root privileges confirmed.")

        # 2. Network Check
        self.logger.info("Verifying network connectivity...")
        if not await self.has_internet_connection_async():
            self.logger.error(
                "No network connectivity detected. Please check network settings and DNS."
            )
            raise ConnectionError("Network connectivity check failed.")
        self.logger.info("Network connectivity verified.")

        # 3. Fedora Check
        self.logger.info("Verifying Fedora distribution...")
        try:
            # Check /etc/os-release for a reliable check
            release_file = Path("/etc/os-release")
            if release_file.exists():
                content = release_file.read_text()
                os_vars = dict(
                    line.split("=", 1) for line in content.splitlines() if "=" in line
                )
                os_id = os_vars.get("ID", "").strip('"')
                version_id = os_vars.get("VERSION_ID", "Unknown").strip('"')
                pretty_name = os_vars.get("PRETTY_NAME", "Unknown OS").strip('"')
                if os_id.lower() == "fedora":
                    self.logger.info(
                        f"Fedora Linux detected. Version: {version_id} ({pretty_name})"
                    )
                else:
                    self.logger.warning(
                        f"System identified as '{pretty_name}'. This script is designed for Fedora; proceed with caution."
                    )
                    # Decide if this should be a fatal error for a server script
                    # raise OSError(f"Expected Fedora, but found {pretty_name}")
            else:
                # Fallback to lsb_release if os-release isn't present (unlikely on modern Fedora)
                result = await run_command_async(
                    ["lsb_release", "-si"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0 and "Fedora" in result.stdout:
                    version_result = await run_command_async(
                        ["lsb_release", "-sr"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    version = (
                        version_result.stdout.strip()
                        if version_result.returncode == 0
                        else "Unknown"
                    )
                    self.logger.info(
                        f"Fedora Linux detected (via lsb_release). Version: {version}"
                    )
                else:
                    self.logger.warning(
                        "Could not definitively verify Fedora distribution. /etc/os-release missing and lsb_release failed or didn't report Fedora."
                    )
                    # raise OSError("Could not verify Fedora distribution.")
        except Exception as e:
            self.logger.warning(
                f"Error during OS verification: {e}. Proceeding cautiously."
            )

    async def save_config_snapshot_async(self) -> Optional[str]:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(
            "/var/backups/initial_setup_snapshots"
        )  # More specific directory
        try:
            backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            self.logger.error(
                f"Failed to create snapshot directory {backup_dir}: {e}. Cannot create snapshot."
            )
            return None

        snapshot_file = backup_dir / f"fedora_server_config_snapshot_{timestamp}.tar.gz"
        # List of important server config files/dirs
        config_paths_to_backup = [
            "/etc/dnf/dnf.conf",
            "/etc/yum.repos.d",
            "/etc/fstab",
            "/etc/default/grub",
            "/etc/hosts",
            "/etc/hostname",
            "/etc/resolv.conf",
            "/etc/sysconfig/network",
            "/etc/sysconfig/network-scripts",  # NetworkManager usually preferred, but include legacy
            "/etc/ssh/sshd_config",
            "/etc/ssh/ssh_config",
            "/etc/firewalld/firewalld.conf",
            "/etc/firewalld/zones",
            "/etc/selinux/config",  # Important for server security
            "/etc/sudoers",
            "/etc/sudoers.d",
            "/etc/security/limits.conf",
            "/etc/sysctl.conf",
            "/etc/sysctl.d",
            # Add more service-specific configs if known defaults are modified
        ]

        try:
            loop = asyncio.get_running_loop()
            files_added_count = 0
            total_size = 0

            # Define the archiving function to run in executor
            def create_archive():
                nonlocal files_added_count, total_size
                added_paths = []
                with tarfile.open(snapshot_file, "w:gz") as tar:
                    for config_path_str in config_paths_to_backup:
                        path = Path(config_path_str)
                        if path.exists():
                            try:
                                # Add to tar, handle potential permission errors during read gracefully
                                tar.add(
                                    str(path),
                                    arcname=str(path).lstrip("/"),
                                    recursive=True,
                                )
                                added_paths.append(str(path))
                                if path.is_file():
                                    total_size += path.stat().st_size
                                # Note: Calculating dir size accurately is complex here, skip for simplicity
                            except PermissionError:
                                self.logger.warning(
                                    f"Permission denied reading {path} for snapshot. Skipping."
                                )
                            except Exception as tar_e:
                                self.logger.warning(
                                    f"Error adding {path} to snapshot: {tar_e}. Skipping."
                                )
                        else:
                            self.logger.debug(
                                f"Path {path} not found, skipping for snapshot."
                            )
                files_added_count = len(added_paths)
                return added_paths  # Return list of actually added paths

            # Run the blocking tar operation in a thread
            added_files = await loop.run_in_executor(None, create_archive)

            if files_added_count > 0:
                # Secure the snapshot file
                os.chmod(snapshot_file, 0o600)
                size_mb = total_size / (1024 * 1024)
                self.logger.info(
                    f"Configuration snapshot saved: {snapshot_file} ({files_added_count} paths included, size approx {size_mb:.2f} MB)"
                )
                for path_str in added_files:  # Log which files were actually added
                    self.logger.debug(f"Included in snapshot: {path_str}")
                return str(snapshot_file)
            else:
                self.logger.warning(
                    "No configuration files found or added to the snapshot."
                )
                # Clean up empty archive file
                snapshot_file.unlink(missing_ok=True)
                return None
        except Exception as e:
            self.logger.error(f"Failed to create config snapshot: {e}")
            # Clean up potentially partial archive file
            snapshot_file.unlink(missing_ok=True)
            return None

    # ----------------------------------------------------------------
    # Phase 1: System Update & Basic Configuration
    # ----------------------------------------------------------------
    async def phase_system_update(self) -> bool:
        await self.print_section_async("System Update & Base Package Installation")
        status = True
        try:
            await run_with_progress_async(
                "Updating package repositories (dnf makecache)",
                self.update_repos_async,
                task_name="system_update",
            )
            await run_with_progress_async(
                "Upgrading system packages (dnf upgrade)",
                self.upgrade_system_async,
                task_name="system_update",
            )
            success_count, failed_list = await run_with_progress_async(
                "Installing required server packages",
                self.install_packages_async,
                task_name="system_update",
            )

            if failed_list:
                self.logger.error(
                    f"Failed to install {len(failed_list)} packages: {', '.join(failed_list)}"
                )
                # Decide if failure is critical (e.g., core tools like sshd, firewalld)
                critical_failures = [
                    pkg
                    for pkg in failed_list
                    if pkg in ["openssh-server", "firewalld", "sudo", "dnf"]
                ]
                if critical_failures:
                    self.logger.critical(
                        f"Critical package installation failed: {', '.join(critical_failures)}. Aborting further setup."
                    )
                    status = False
                else:
                    self.logger.warning(
                        "Some non-critical packages failed to install. Continuing setup."
                    )
            else:
                self.logger.info(
                    f"Successfully installed/verified {success_count} packages."
                )

            # Add basic config like timezone here if needed
            # await run_with_progress_async("Setting system timezone", self.set_timezone_async, task_name="system_update")

        except Exception as e:
            self.logger.error(f"System update phase encountered an error: {e}")
            status = False  # Mark phase as failed

        # Update overall status based on intermediate results
        if status:
            SETUP_STATUS["system_update"]["status"] = "success"
            SETUP_STATUS["system_update"]["message"] = (
                "System updated and base packages installed."
            )
        else:
            SETUP_STATUS["system_update"]["status"] = "failed"
            if not SETUP_STATUS["system_update"][
                "message"
            ]:  # Add generic message if specific one wasn't set
                SETUP_STATUS["system_update"]["message"] = (
                    "Failed during update or package installation."
                )

        return status

    async def update_repos_async(self) -> bool:
        """Updates dnf repository cache."""
        try:
            self.logger.info("Updating package repositories using 'dnf makecache'...")
            # Use --timer option for potentially faster metadata download on slow connections
            await run_command_async(
                ["dnf", "makecache", "--timer"], check=True, timeout=600
            )  # Increased timeout
            self.logger.info("Package repository cache updated successfully.")
            return True
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.error(f"Repository cache update failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during repo update: {e}")
            return False

    async def upgrade_system_async(self) -> bool:
        """Performs a full system upgrade using dnf."""
        try:
            self.logger.info("Upgrading system packages using 'dnf upgrade -y'...")
            # Note: -y assumes acceptance of all prompts.
            await run_command_async(
                ["dnf", "upgrade", "-y"], check=True, timeout=1800
            )  # Long timeout for upgrades
            self.logger.info("System upgrade completed successfully.")
            # Check if reboot is required after upgrade (e.g., kernel update)
            needs_reboot = Path("/run/reboot-required").exists()
            if needs_reboot:
                self.logger.warning(
                    "A system reboot is recommended after the upgrade (kernel or core libraries updated)."
                )
                # Optionally create a flag file or log this prominently
            return True
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.error(f"System upgrade failed: {e}")
            # Check dnf logs (/var/log/dnf.log) for more details if needed.
            return False
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred during system upgrade: {e}"
            )
            return False

    async def install_packages_async(self) -> Tuple[int, List[str]]:
        """Installs required packages, checking which are already present."""
        self.logger.info("Checking and installing required server packages...")
        packages_to_install = []
        already_installed_count = 0
        failed_packages = []
        total_requested = len(self.config.PACKAGES)

        # Efficiently check multiple packages at once
        try:
            rpm_check_cmd = ["rpm", "-q"] + self.config.PACKAGES
            # Run rpm -q, don't check return code as it fails if *any* package is missing
            result = await run_command_async(
                rpm_check_cmd, capture_output=True, check=False, text=True
            )

            installed_status = {}
            # Parse output: "package <name> is not installed" or "name-version-release"
            for line in result.stdout.splitlines():
                parts = line.split()
                if "is not installed" in line:
                    pkg_name = parts[1]
                    installed_status[pkg_name] = False
                elif len(parts) >= 1:
                    # Extract package name (might have epoch like 1:...)
                    # rpm output is typically 'name-version-release.arch'
                    # We need to match this back to the original requested name
                    # This is complex, simpler approach: assume any non-"not installed" means installed for this check.
                    # A more robust check might compare against `dnf list --installed` output.
                    # For now, we identify the *missing* ones accurately.
                    pass  # Assume installed if no "not installed" message

            # Identify which requested packages were marked as not installed
            for pkg in self.config.PACKAGES:
                if (
                    installed_status.get(pkg, True) is False
                ):  # If explicitly marked False, it's missing
                    packages_to_install.append(pkg)
                elif pkg not in installed_status:
                    # If a package wasn't in the output *at all*, rpm might have errored?
                    # Or it could be installed. Re-check individually if needed, or assume needs install.
                    # Let's assume it needs installation for safety, dnf will skip if present.
                    self.logger.debug(
                        f"Package '{pkg}' not found in initial rpm -q output, adding to install list."
                    )
                    packages_to_install.append(pkg)

            already_installed_count = total_requested - len(packages_to_install)
            self.logger.info(f"{already_installed_count} packages already installed.")

        except Exception as e:
            self.logger.warning(
                f"Initial package check failed: {e}. Will attempt to install all packages."
            )
            packages_to_install = list(
                self.config.PACKAGES
            )  # Install all if check fails
            already_installed_count = 0

        if packages_to_install:
            self.logger.info(
                f"Attempting to install {len(packages_to_install)} missing/uncertain packages..."
            )
            try:
                # Install missing packages
                await run_command_async(
                    ["dnf", "install", "-y"] + packages_to_install,
                    check=True,
                    timeout=1800,
                )
                self.logger.info(
                    f"Successfully installed {len(packages_to_install)} packages."
                )
                # Verify installation (optional, but good practice)
                verification_cmd = ["rpm", "-q"] + packages_to_install
                verify_result = await run_command_async(
                    verification_cmd, capture_output=True, check=False, text=True
                )
                for line in verify_result.stdout.splitlines():
                    if "is not installed" in line:
                        failed_pkg = line.split()[1]
                        failed_packages.append(failed_pkg)
                        self.logger.error(
                            f"Verification failed for package: {failed_pkg}"
                        )

            except (subprocess.CalledProcessError, TimeoutError) as e:
                self.logger.error(f"Failed to install packages: {e}")
                # Try to determine which packages failed from dnf output (complex)
                # For simplicity, assume all in packages_to_install might have failed
                # A better approach is to parse dnf logs or stderr
                self.logger.warning(
                    "Could not reliably determine which packages failed. Check logs."
                )
                failed_packages = list(
                    packages_to_install
                )  # Mark all as potentially failed
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred during package installation: {e}"
                )
                failed_packages = list(packages_to_install)

        else:
            self.logger.info("All required packages were already installed.")

        successful_count = total_requested - len(failed_packages)
        return successful_count, failed_packages

    # ----------------------------------------------------------------
    # Phase 2: Repository & Shell Setup
    # ----------------------------------------------------------------
    async def phase_repo_shell_setup(self) -> bool:
        await self.print_section_async("User Repository & Shell Configuration")
        status = True
        try:
            # Ensure the target user exists before proceeding
            if not await self._check_user_exists_async(self.config.USERNAME):
                self.logger.error(
                    f"User '{self.config.USERNAME}' not found. Cannot proceed with user-specific setup."
                )
                raise ValueError(f"User {self.config.USERNAME} does not exist.")

            await run_with_progress_async(
                "Cloning/updating GitHub repositories",
                self.setup_repos_async,
                task_name="repo_shell",
            )
            await run_with_progress_async(
                "Copying shell configuration files (.bashrc, .profile)",
                self.copy_shell_configs_async,
                task_name="repo_shell",
            )
            await run_with_progress_async(
                "Copying user config directories (.config/*)",
                self.copy_config_folders_async,
                task_name="repo_shell",
            )
            await run_with_progress_async(
                "Setting default shell to bash for user",
                self.set_bash_shell_async,
                task_name="repo_shell",
            )

        except Exception as e:
            self.logger.error(f"Repo & Shell setup phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["repo_shell"]["status"] = "success"
            SETUP_STATUS["repo_shell"]["message"] = (
                "User repositories cloned and shell configured."
            )
        else:
            SETUP_STATUS["repo_shell"]["status"] = "failed"
            if not SETUP_STATUS["repo_shell"]["message"]:
                SETUP_STATUS["repo_shell"]["message"] = (
                    "Failed during repository or shell configuration."
                )

        return status

    async def _check_user_exists_async(self, username: str) -> bool:
        """Checks if a local user exists."""
        try:
            await run_command_async(
                ["id", "-u", username], capture_output=True, check=True
            )
            self.logger.debug(f"User '{username}' found.")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.debug(f"User '{username}' not found.")
            return False
        except Exception as e:
            self.logger.error(f"Error checking for user '{username}': {e}")
            return False  # Assume not found if error occurs

    async def setup_repos_async(self) -> bool:
        """Clones or updates specified GitHub repositories for the user."""
        # Ensure git is installed
        if not await command_exists_async("git"):
            self.logger.error(
                "'git' command not found. Cannot clone repositories. Please install git."
            )
            return False

        gh_base_dir = self.config.USER_HOME / "github"
        target_uid, target_gid = await self._get_user_uid_gid(self.config.USERNAME)
        if target_uid is None or target_gid is None:
            self.logger.error(
                f"Could not get UID/GID for user {self.config.USERNAME}. Aborting repo setup."
            )
            return False

        try:
            # Create base directory if it doesn't exist, owned by the user
            if not gh_base_dir.exists():
                gh_base_dir.mkdir(exist_ok=True)
                os.chown(gh_base_dir, target_uid, target_gid)
                self.logger.info(f"Created base GitHub directory: {gh_base_dir}")
            elif not os.stat(gh_base_dir).st_uid == target_uid:
                # Correct ownership if it exists but is wrong
                self.logger.warning(
                    f"Correcting ownership of existing directory: {gh_base_dir}"
                )
                os.chown(gh_base_dir, target_uid, target_gid)

        except Exception as e:
            self.logger.error(
                f"Failed to create or set ownership on {gh_base_dir}: {e}"
            )
            return False

        all_success = True
        repos_to_clone = ["bash", "python"]  # Define repositories to manage
        for repo_name in repos_to_clone:
            repo_dir = gh_base_dir / repo_name
            repo_url = f"https://github.com/dunamismax/{repo_name}.git"  # Assuming this structure

            try:
                if (repo_dir / ".git").is_dir():
                    self.logger.info(
                        f"Repository '{repo_name}' exists at {repo_dir}. Pulling updates..."
                    )
                    # Run git pull as the target user
                    await run_command_async(
                        [
                            "sudo",
                            "-u",
                            self.config.USERNAME,
                            "--",
                            "git",
                            "-C",
                            str(repo_dir),
                            "pull",
                        ],
                        check=True,
                        timeout=120,
                    )
                    self.logger.info(f"Successfully updated repository '{repo_name}'.")
                else:
                    self.logger.info(
                        f"Cloning repository '{repo_name}' from {repo_url} into {repo_dir}..."
                    )
                    # Run git clone as the target user
                    await run_command_async(
                        [
                            "sudo",
                            "-u",
                            self.config.USERNAME,
                            "--",
                            "git",
                            "clone",
                            repo_url,
                            str(repo_dir),
                        ],
                        check=True,
                        timeout=300,
                    )
                    self.logger.info(f"Successfully cloned repository '{repo_name}'.")

                # Ensure correct ownership recursively after clone/pull (git might create files as user)
                # Use os.chown recursively in executor for potentially large dirs
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, self._recursive_chown, repo_dir, target_uid, target_gid
                )

            except (subprocess.CalledProcessError, TimeoutError, OSError) as e:
                self.logger.error(f"Failed to process repository '{repo_name}': {e}")
                all_success = False
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred processing repository '{repo_name}': {e}"
                )
                all_success = False

        return all_success

    async def _get_user_uid_gid(
        self, username: str
    ) -> Tuple[Optional[int], Optional[int]]:
        """Gets UID and GID for a given username."""
        try:
            result = await run_command_async(
                ["id", "-u", username], capture_output=True, check=True, text=True
            )
            uid = int(result.stdout.strip())
            result = await run_command_async(
                ["id", "-g", username], capture_output=True, check=True, text=True
            )
            gid = int(result.stdout.strip())
            return uid, gid
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
            self.logger.error(f"Failed to get UID/GID for user '{username}': {e}")
            return None, None

    def _recursive_chown(self, path: Path, uid: int, gid: int):
        """Recursively chowns a path. Runs in executor."""
        try:
            os.chown(path, uid, gid)
            if path.is_dir():
                for item in path.iterdir():
                    self._recursive_chown(item, uid, gid)  # Recurse
        except Exception as e:
            # Log error but continue if possible
            logging.warning(f"Could not chown {path}: {e}")

    async def copy_shell_configs_async(self) -> bool:
        """Copies essential shell config files (.bashrc, .profile) for user and root."""
        source_base_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "fedora" / "dotfiles"
        )
        if not source_base_dir.is_dir():
            self.logger.error(
                f"Source directory for dotfiles not found: {source_base_dir}. Skipping shell config copy."
            )
            return False

        target_user_uid, target_user_gid = await self._get_user_uid_gid(
            self.config.USERNAME
        )
        if target_user_uid is None or target_user_gid is None:
            self.logger.error(
                f"Cannot get UID/GID for {self.config.USERNAME}. Skipping shell config copy."
            )
            return False

        # Files to copy and their destinations (user home, root home)
        files_to_copy = {
            ".bashrc": [self.config.USER_HOME, Path("/root")],
            ".profile": [self.config.USER_HOME, Path("/root")],
            # Add other relevant dotfiles here if needed, e.g., .inputrc
            ".inputrc": [self.config.USER_HOME, Path("/root")],
        }

        overall_success = True
        loop = asyncio.get_running_loop()

        for file_name, dest_dirs in files_to_copy.items():
            src_path = source_base_dir / file_name
            if not src_path.is_file():
                self.logger.warning(f"Source file {src_path} not found; skipping.")
                continue

            for dest_dir in dest_dirs:
                dest_path = dest_dir / file_name
                is_root_dest = dest_dir == Path("/root")

                try:
                    # Check if file exists and is identical
                    should_copy = True
                    if dest_path.is_file():
                        # Use run_in_executor for file comparison
                        files_identical = await loop.run_in_executor(
                            None, filecmp.cmp, src_path, dest_path, shallow=False
                        )
                        if files_identical:
                            self.logger.info(
                                f"File {dest_path} already exists and is identical. Skipping copy."
                            )
                            should_copy = False
                        else:
                            self.logger.info(
                                f"File {dest_path} exists but differs. Backing up before overwrite."
                            )
                            await self.backup_file_async(dest_path)

                    if should_copy:
                        # Use run_in_executor for file copy
                        await loop.run_in_executor(
                            None, lambda: shutil.copy2(src_path, dest_path)
                        )
                        self.logger.info(f"Copied {src_path} to {dest_path}.")

                        # Set ownership and permissions
                        target_uid = 0 if is_root_dest else target_user_uid
                        target_gid = 0 if is_root_dest else target_user_gid
                        # Use run_in_executor for os calls
                        await loop.run_in_executor(
                            None, lambda: os.chown(dest_path, target_uid, target_gid)
                        )
                        await loop.run_in_executor(
                            None, lambda: os.chmod(dest_path, 0o644)
                        )  # Standard permissions for dotfiles
                        self.logger.debug(
                            f"Set ownership ({target_uid}:{target_gid}) and permissions (644) for {dest_path}."
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to copy or set permissions for {dest_path}: {e}"
                    )
                    overall_success = False

        return overall_success

    async def copy_config_folders_async(self) -> bool:
        """Copies configuration folders (e.g., .config/*) from source to user's home."""
        source_config_dir = (
            self.config.USER_HOME
            / "github"
            / "bash"
            / "linux"
            / "fedora"
            / "dotfiles"
            / ".config"
        )
        if not source_config_dir.is_dir():
            self.logger.warning(
                f"Source .config directory not found at {source_config_dir}. Skipping config folder copy."
            )
            # This might not be an error if no .config overrides are intended
            return True  # Return True as it's not necessarily a failure state

        dest_config_dir = self.config.USER_HOME / ".config"
        target_uid, target_gid = await self._get_user_uid_gid(self.config.USERNAME)
        if target_uid is None or target_gid is None:
            self.logger.error(
                f"Cannot get UID/GID for {self.config.USERNAME}. Skipping config folder copy."
            )
            return False

        try:
            # Ensure destination .config directory exists and has correct base ownership
            if not dest_config_dir.exists():
                dest_config_dir.mkdir(exist_ok=True)
                os.chown(dest_config_dir, target_uid, target_gid)
            elif not os.stat(dest_config_dir).st_uid == target_uid:
                os.chown(
                    dest_config_dir, target_uid, target_gid
                )  # Correct base dir ownership

            loop = asyncio.get_running_loop()

            # Use rsync for efficient copying (if available)
            if await command_exists_async("rsync"):
                # Ensure source path ends with / for rsync content copy behaviour
                rsync_src = str(source_config_dir) + "/"
                # Run rsync as root, but chown later might be safer depending on content
                rsync_cmd = [
                    "rsync",
                    "-avh",  # archive, verbose, human-readable
                    "--no-owner",
                    "--no-group",  # Don't preserve source owner/group
                    "--chown",
                    f"{target_uid}:{target_gid}",  # Set destination ownership directly
                    rsync_src,
                    str(dest_config_dir),
                ]
                self.logger.info(
                    f"Using rsync to copy config folders from {source_config_dir} to {dest_config_dir}"
                )
                await run_command_async(rsync_cmd, check=True, timeout=300)
                self.logger.info("rsync completed for config folders.")
                # Permissions might need adjustment after rsync if specific modes are needed beyond 'a' flag defaults

            else:
                # Fallback to Python's copytree if rsync isn't available
                self.logger.warning(
                    "rsync not found. Falling back to slower Python copytree."
                )

                # copytree needs to run in executor
                def copytree_action():
                    shutil.copytree(
                        source_config_dir,
                        dest_config_dir,
                        dirs_exist_ok=True,
                        copy_function=shutil.copy2,
                    )
                    # Manually set ownership after copytree
                    self._recursive_chown(dest_config_dir, target_uid, target_gid)

                await loop.run_in_executor(None, copytree_action)
                self.logger.info("Fallback copytree completed for config folders.")

            # Final verification of top-level ownership
            await loop.run_in_executor(
                None, lambda: os.chown(dest_config_dir, target_uid, target_gid)
            )

            self.logger.info(
                f"Successfully copied configuration folders to {dest_config_dir}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Error copying config folders from {source_config_dir} to {dest_config_dir}: {e}"
            )
            return False

    async def set_bash_shell_async(self) -> bool:
        """Sets /bin/bash as the default shell for the specified user."""
        target_username = self.config.USERNAME
        bash_path = "/bin/bash"

        # 1. Check if bash exists
        if not Path(bash_path).is_file() or not os.access(bash_path, os.X_OK):
            self.logger.error(
                f"Bash executable not found or not executable at {bash_path}. Cannot set as default shell."
            )
            # Try to install bash if missing? Assumes it's in PACKAGES list already.
            if "bash" not in self.config.PACKAGES:
                self.logger.warning("Consider adding 'bash' to the PACKAGES list.")
            return False

        # 2. Check if bash is listed in /etc/shells
        shells_file = Path("/etc/shells")
        try:
            loop = asyncio.get_running_loop()
            content = ""
            if shells_file.is_file():
                content = await loop.run_in_executor(None, shells_file.read_text)

            if bash_path not in content.splitlines():
                self.logger.warning(
                    f"{bash_path} not found in {shells_file}. Attempting to add it."
                )
                # Backup before modifying system file
                await self.backup_file_async(shells_file)
                try:
                    # Append bash path to /etc/shells
                    async def append_to_shells():
                        with open(shells_file, "a") as f:
                            # Add newline if file doesn't end with one
                            if content and not content.endswith("\n"):
                                f.write("\n")
                            f.write(f"{bash_path}\n")

                    await loop.run_in_executor(None, append_to_shells)
                    self.logger.info(f"Added {bash_path} to {shells_file}.")
                except Exception as add_e:
                    self.logger.error(
                        f"Failed to add {bash_path} to {shells_file}: {add_e}"
                    )
                    # Decide if this is fatal. chsh might still work if system allows unlisted shells.
                    # return False # Make it fatal
                    self.logger.warning(
                        "Continuing attempt to set shell despite /etc/shells update failure."
                    )

        except Exception as e:
            self.logger.error(f"Error checking or updating {shells_file}: {e}")
            return False  # Fail if we can't read/write /etc/shells safely

        # 3. Get current shell
        try:
            getent_cmd = ["getent", "passwd", target_username]
            result = await run_command_async(
                getent_cmd, capture_output=True, check=True, text=True
            )
            current_shell = result.stdout.strip().split(":")[-1]
            self.logger.info(
                f"Current shell for user '{target_username}' is '{current_shell}'."
            )
        except (subprocess.CalledProcessError, IndexError) as e:
            self.logger.error(
                f"Failed to get current shell for user '{target_username}': {e}"
            )
            # Continue, maybe chsh will work anyway? Or return False?
            return False  # Fail if we cannot determine current state reliably

        # 4. Change shell if needed
        if current_shell == bash_path:
            self.logger.info(
                f"User '{target_username}' already has {bash_path} as default shell."
            )
            return True
        else:
            self.logger.info(
                f"Changing default shell for user '{target_username}' to {bash_path}..."
            )
            try:
                chsh_cmd = ["chsh", "-s", bash_path, target_username]
                await run_command_async(chsh_cmd, check=True)
                self.logger.info(
                    f"Successfully set default shell for '{target_username}' to {bash_path}."
                )

                # Verify the change
                verify_result = await run_command_async(
                    ["getent", "passwd", target_username],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                new_shell = verify_result.stdout.strip().split(":")[-1]
                if new_shell == bash_path:
                    self.logger.info("Shell change verified.")
                    return True
                else:
                    self.logger.error(
                        f"Shell change verification failed! Current shell is still '{new_shell}'."
                    )
                    return False

            except (subprocess.CalledProcessError, TimeoutError) as e:
                self.logger.error(
                    f"Failed to set default shell for '{target_username}' using chsh: {e}"
                )
                return False
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred while setting shell: {e}"
                )
                return False

    # ----------------------------------------------------------------
    # Phase 3: Security Hardening
    # ----------------------------------------------------------------
    async def phase_security_hardening(self) -> bool:
        await self.print_section_async("Security Hardening (SSH, Firewall, Fail2ban)")
        status = True
        try:
            ssh_ok = await run_with_progress_async(
                "Configuring SSH Server (sshd)",
                self.configure_ssh_async,
                task_name="security",
            )
            if not ssh_ok:
                status = False  # Propagate failure

            firewall_ok = await run_with_progress_async(
                "Configuring Firewall (firewalld)",
                self.configure_firewall_async,
                task_name="security",
            )
            if not firewall_ok:
                status = False

            fail2ban_ok = await run_with_progress_async(
                "Configuring Fail2ban",
                self.configure_fail2ban_async,
                task_name="security",
            )
            if not fail2ban_ok:
                status = False

            # Add other hardening steps here:
            # - Configure sudoers (limit commands, add users?)
            # - Configure SELinux (ensure enforcing, check policies?) -> Complex
            # - Run Lynis/Rkhunter/AIDE setup? -> Can be long running, maybe separate phase
            # - System limits (ulimit, /etc/security/limits.conf)
            # - Kernel parameters (/etc/sysctl.conf)

        except Exception as e:
            self.logger.error(f"Security hardening phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["security"]["status"] = "success"
            SETUP_STATUS["security"]["message"] = "SSH, Firewall, Fail2ban configured."
        else:
            SETUP_STATUS["security"]["status"] = "failed"
            if not SETUP_STATUS["security"]["message"]:
                SETUP_STATUS["security"]["message"] = (
                    "Failed during security configuration."
                )

        return status

    async def configure_ssh_async(self) -> bool:
        """Configures the OpenSSH server (sshd)."""
        sshd_config_path = Path("/etc/ssh/sshd_config")
        sshd_service_name = "sshd"  # Or sshd.service

        # 1. Ensure openssh-server package is installed (should be from phase 1)
        if not await command_exists_async("sshd"):
            if "openssh-server" in self.config.PACKAGES:
                self.logger.error(
                    "openssh-server should have been installed but 'sshd' command not found. Installation might have failed."
                )
            else:
                self.logger.error(
                    "openssh-server is not listed in packages. Cannot configure SSH."
                )
            return False

        # 2. Ensure config file exists
        if not sshd_config_path.is_file():
            self.logger.error(
                f"SSHD configuration file not found: {sshd_config_path}. Cannot configure SSH."
            )
            # Maybe try dnf reinstall openssh-server?
            return False

        # 3. Backup original config
        backup_path = await self.backup_file_async(sshd_config_path)
        if not backup_path:
            self.logger.warning(
                f"Failed to backup {sshd_config_path}. Proceeding with caution."
            )

        # 4. Apply configurations
        try:
            loop = asyncio.get_running_loop()
            current_config_lines = await loop.run_in_executor(
                None, lambda: sshd_config_path.read_text().splitlines()
            )
            new_config_lines = []
            applied_keys = set()

            # Process existing lines, updating or commenting out defaults if needed
            for line in current_config_lines:
                stripped_line = line.strip()
                # Skip empty lines and comments immediately
                if not stripped_line or stripped_line.startswith("#"):
                    new_config_lines.append(line)  # Keep original comments/spacing
                    continue

                parts = stripped_line.split(maxsplit=1)
                if len(parts) == 2:
                    key, current_value = parts
                    if key in self.config.SSH_CONFIG:
                        desired_value = self.config.SSH_CONFIG[key]
                        if current_value != desired_value:
                            new_line = f"{key} {desired_value}"
                            new_config_lines.append(new_line)
                            self.logger.debug(
                                f"SSH Config: Updated '{key}' from '{current_value}' to '{desired_value}'"
                            )
                        else:
                            new_config_lines.append(line)  # Keep existing correct line
                        applied_keys.add(key)
                    else:
                        # Keep lines not managed by our config
                        new_config_lines.append(line)
                else:
                    # Keep malformed or unusual lines
                    new_config_lines.append(line)

            # Add any keys from our config that weren't found in the file
            for key, desired_value in self.config.SSH_CONFIG.items():
                if key not in applied_keys:
                    new_line = f"{key} {desired_value}"
                    new_config_lines.append(new_line)
                    self.logger.debug(f"SSH Config: Added '{key} {desired_value}'")

            # Write the modified config back
            new_config_content = (
                "\n".join(new_config_lines) + "\n"
            )  # Ensure trailing newline
            await loop.run_in_executor(
                None, lambda: sshd_config_path.write_text(new_config_content)
            )
            self.logger.info(
                f"Successfully updated SSH configuration in {sshd_config_path}."
            )

            # 5. Validate the new configuration
            self.logger.info("Validating SSH configuration using 'sshd -t'...")
            await run_command_async(["sshd", "-t"], check=True)
            self.logger.info("SSH configuration validation successful.")

            # 6. Enable and restart the service
            self.logger.info(f"Enabling and restarting {sshd_service_name} service...")
            # Use enable --now to start if not running, or restart if already running
            await run_command_async(
                ["systemctl", "enable", "--now", sshd_service_name], check=True
            )
            # Explicit restart might be needed if it was already running to apply config changes reliably
            await run_command_async(
                ["systemctl", "restart", sshd_service_name], check=True
            )
            self.logger.info(f"{sshd_service_name} service enabled and restarted.")

            # 7. Check service status
            status_result = await run_command_async(
                ["systemctl", "is-active", sshd_service_name],
                capture_output=True,
                check=False,
                text=True,
            )
            if status_result.stdout.strip() == "active":
                self.logger.info(f"{sshd_service_name} service is active.")
                return True
            else:
                self.logger.error(
                    f"{sshd_service_name} service failed to start or is not active after restart. Check logs: journalctl -u {sshd_service_name}"
                )
                # Optionally try to restore backup?
                return False

        except subprocess.CalledProcessError as e:
            if e.cmd and e.cmd[0] == "sshd" and e.cmd[1] == "-t":
                self.logger.error(
                    f"SSH configuration validation failed (sshd -t). Check {sshd_config_path} for errors."
                )
                self.logger.error(f"Stderr:\n{e.stderr}")
                # Restore backup automatically? Risky.
                self.logger.warning(f"Consider restoring the backup: {backup_path}")
            else:
                self.logger.error(
                    f"Error during SSH configuration or service management: {e}"
                )
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during SSH configuration: {e}")
            return False

    async def configure_firewall_async(self) -> bool:
        """Configures firewalld with specified ports."""
        firewall_cmd = "firewall-cmd"
        firewalld_service = "firewalld"

        # 1. Check if firewalld is installed and command exists
        if not await command_exists_async(firewall_cmd):
            if "firewalld" in self.config.PACKAGES:
                self.logger.error(
                    "firewalld should have been installed but 'firewall-cmd' not found. Installation might have failed."
                )
            else:
                self.logger.error(
                    "firewalld is not listed in packages. Cannot configure firewall."
                )
            return False

        # 2. Ensure firewalld service is enabled and running
        try:
            # Enable should be idempotent
            await run_command_async(
                ["systemctl", "enable", firewalld_service], check=True
            )
            # Start if not running
            status_result = await run_command_async(
                ["systemctl", "is-active", firewalld_service],
                capture_output=True,
                check=False,
                text=True,
            )
            if status_result.stdout.strip() != "active":
                self.logger.info(f"{firewalld_service} is not active. Starting it...")
                await run_command_async(
                    ["systemctl", "start", firewalld_service], check=True
                )
                # Verify start
                status_result = await run_command_async(
                    ["systemctl", "is-active", firewalld_service],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                if status_result.stdout.strip() != "active":
                    raise ChildProcessError(f"Failed to start {firewalld_service}")
            self.logger.info(f"{firewalld_service} service is enabled and active.")
        except (subprocess.CalledProcessError, ChildProcessError, TimeoutError) as e:
            self.logger.error(
                f"Failed to enable or start {firewalld_service}: {e}. Cannot configure firewall rules."
            )
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error managing {firewalld_service}: {e}")
            return False

        # 3. Set default zone (optional, but good practice)
        default_zone = "public"  # Common default
        try:
            self.logger.info(f"Setting default firewall zone to '{default_zone}'...")
            await run_command_async(
                [firewall_cmd, "--set-default-zone=" + default_zone], check=True
            )
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.warning(
                f"Failed to set default zone to '{default_zone}': {e}. Using current default."
            )
        except Exception as e:
            self.logger.warning(f"Unexpected error setting default zone: {e}")

        # 4. Configure ports in the permanent configuration
        self.logger.info(
            f"Configuring firewall ports in zone '{default_zone}' (permanent): {self.config.FIREWALL_PORTS}"
        )
        current_ports = set()
        try:
            list_ports_cmd = [
                firewall_cmd,
                "--permanent",
                f"--zone={default_zone}",
                "--list-ports",
            ]
            result = await run_command_async(
                list_ports_cmd, capture_output=True, check=True, text=True
            )
            current_ports.update(p.strip() for p in result.stdout.split() if p.strip())
            self.logger.debug(
                f"Current permanent ports in zone '{default_zone}': {current_ports}"
            )
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.warning(
                f"Could not list current ports for zone '{default_zone}': {e}. Proceeding to add specified ports."
            )
        except Exception as e:
            self.logger.warning(f"Unexpected error listing ports: {e}")

        overall_success = True
        ports_to_add = []
        # Assuming format "port/protocol", default to tcp if not specified
        for port_spec in self.config.FIREWALL_PORTS:
            port_proto = (
                f"{port_spec}/tcp" if "/" not in str(port_spec) else str(port_spec)
            )
            if port_proto not in current_ports:
                ports_to_add.append(port_proto)

        if ports_to_add:
            self.logger.info(f"Adding ports to zone '{default_zone}': {ports_to_add}")
            # Use --add-port batching if firewall-cmd supports it well, otherwise loop
            # Looping is safer for compatibility
            for port_proto in ports_to_add:
                try:
                    add_cmd = [
                        firewall_cmd,
                        "--permanent",
                        f"--zone={default_zone}",
                        f"--add-port={port_proto}",
                    ]
                    await run_command_async(add_cmd, check=True)
                    self.logger.info(
                        f"Added port {port_proto} to zone '{default_zone}' (permanent)."
                    )
                except (subprocess.CalledProcessError, TimeoutError) as e:
                    self.logger.error(
                        f"Failed to add port {port_proto} to zone '{default_zone}': {e}"
                    )
                    overall_success = False
                except Exception as e:
                    self.logger.error(f"Unexpected error adding port {port_proto}: {e}")
                    overall_success = False
        else:
            self.logger.info(
                f"All specified ports are already configured in zone '{default_zone}'."
            )

        # 5. Reload firewall to apply permanent changes to runtime config
        if (
            ports_to_add or not overall_success
        ):  # Reload if changes were made or if errors occurred (to ensure state)
            try:
                self.logger.info("Reloading firewall configuration...")
                await run_command_async(
                    [firewall_cmd, "--reload"], check=True, timeout=60
                )
                self.logger.info("Firewall reloaded successfully.")
            except (subprocess.CalledProcessError, TimeoutError) as e:
                self.logger.error(
                    f"Failed to reload firewall: {e}. Runtime configuration might be out of sync."
                )
                overall_success = False  # Mark failure if reload fails
            except Exception as e:
                self.logger.error(f"Unexpected error reloading firewall: {e}")
                overall_success = False

        # Optionally verify runtime configuration matches permanent
        # E.g., run `firewall-cmd --zone={default_zone} --list-ports` (without --permanent)

        return overall_success

    async def configure_fail2ban_async(self) -> bool:
        """Installs and configures Fail2ban with a basic SSH jail."""
        fail2ban_service = (
            "fail2ban"  # service name might vary slightly, check systemd unit
        )
        jail_local_path = Path("/etc/fail2ban/jail.local")
        jail_conf_path = Path("/etc/fail2ban/jail.conf")  # Base config

        # 1. Check if Fail2ban is installed
        if not await command_exists_async("fail2ban-client"):
            if "fail2ban" in self.config.PACKAGES:
                self.logger.error(
                    "fail2ban should have been installed but 'fail2ban-client' not found. Installation might have failed."
                )
            else:
                self.logger.error(
                    "fail2ban is not listed in packages. Cannot configure Fail2ban."
                )
            return False

        # 2. Ensure base config exists (fail2ban package should provide this)
        if not jail_conf_path.is_file():
            self.logger.error(
                f"Base Fail2ban config {jail_conf_path} not found. Cannot create local override."
            )
            return False

        # 3. Create jail.local configuration
        # Basic config targeting SSHd. Customize bantime, findtime, maxretry as needed.
        # Using 'backend = systemd' is often preferred on modern Fedora.
        # Logpath might need adjustment based on system logging setup (e.g., journal vs /var/log/secure)
        # Check sshd logs (`journalctl -u sshd`) to see where auth failures are logged.
        config_content = f"""
[DEFAULT]
# Ban time in seconds
bantime = 1h
# Time window to detect attacks
findtime = 10m
# Number of failures before banning
maxretry = 5
# Backend to use (auto, systemd, polling) - systemd is often good on Fedora
backend = systemd
# Whitelist local IPs and common private ranges (adjust as needed)
ignoreip = 127.0.0.1/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16

# Action to take (e.g., firewalld blocking)
# Default uses iptables, need to ensure firewalld actions are used if firewalld is active
# Check available actions in /etc/fail2ban/action.d/
# Example using firewalld:
banaction = firewallcmd-ipset
# Action for specific ports:
# banaction_allports = firewallcmd-ipset

[sshd]
enabled = true
# port = ssh # Uses service name 'ssh' (usually port 22)
# filter = sshd # Uses filter defined in filter.d/sshd.conf
# logpath = %(sshd_log)s # Uses system-specific log path variable
maxretry = 3 # Override default maxretry specifically for SSH
bantime = 2h # Longer ban for SSH?
"""
        try:
            self.logger.info(
                f"Creating/updating Fail2ban local configuration: {jail_local_path}"
            )
            # Backup existing jail.local if it exists
            if jail_local_path.exists():
                await self.backup_file_async(jail_local_path)

            # Write the new config
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: jail_local_path.write_text(config_content)
            )
            # Ensure permissions are secure (readable only by root)
            await loop.run_in_executor(None, lambda: os.chmod(jail_local_path, 0o600))

            self.logger.info("Fail2ban jail.local configuration written.")

            # 4. Enable and restart Fail2ban service
            self.logger.info(f"Enabling and restarting {fail2ban_service} service...")
            await run_command_async(
                ["systemctl", "enable", "--now", fail2ban_service], check=True
            )
            await run_command_async(
                ["systemctl", "restart", fail2ban_service], check=True
            )
            self.logger.info(f"{fail2ban_service} service enabled and restarted.")

            # 5. Check service status
            status_result = await run_command_async(
                ["systemctl", "is-active", fail2ban_service],
                capture_output=True,
                check=False,
                text=True,
            )
            if status_result.stdout.strip() == "active":
                self.logger.info(f"{fail2ban_service} service is active.")
                # Optionally check active jails: fail2ban-client status sshd
                try:
                    await run_command_async(
                        ["fail2ban-client", "status", "sshd"],
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                    self.logger.info("Fail2ban sshd jail is active.")
                except (subprocess.CalledProcessError, TimeoutError) as status_e:
                    self.logger.warning(
                        f"Could not confirm sshd jail status via fail2ban-client: {status_e}"
                    )
                return True
            else:
                self.logger.error(
                    f"{fail2ban_service} service failed to start or is not active. Check logs: journalctl -u {fail2ban_service}"
                )
                return False

        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.error(f"Error configuring or managing Fail2ban: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Fail2ban configuration: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 4: User Customization & Script Deployment
    # ----------------------------------------------------------------
    async def phase_user_customization(self) -> bool:
        await self.print_section_async("User Customization & Script Deployment")
        status = True
        try:
            # Ensure user exists first
            if not await self._check_user_exists_async(self.config.USERNAME):
                self.logger.error(
                    f"User '{self.config.USERNAME}' not found. Skipping user script deployment."
                )
                raise ValueError(f"User {self.config.USERNAME} does not exist.")

            script_ok = await run_with_progress_async(
                "Deploying user scripts to ~/bin",
                self.deploy_user_scripts_async,
                task_name="user_custom",
            )
            if not script_ok:
                status = False

            # No GUI appearance settings for server

        except Exception as e:
            self.logger.error(f"User customization phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["user_custom"]["status"] = "success"
            SETUP_STATUS["user_custom"]["message"] = "User scripts deployed."
        else:
            SETUP_STATUS["user_custom"]["status"] = "failed"
            if not SETUP_STATUS["user_custom"]["message"]:
                SETUP_STATUS["user_custom"]["message"] = (
                    "Failed during user customization."
                )

        return status

    async def deploy_user_scripts_async(self) -> bool:
        """Copies user scripts from the cloned repo to the user's ~/bin directory."""
        src_scripts_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "fedora" / "_scripts"
        )
        target_bin_dir = self.config.USER_HOME / "bin"

        # 1. Check if source directory exists
        if not src_scripts_dir.is_dir():
            self.logger.warning(
                f"Script source directory {src_scripts_dir} does not exist. No scripts to deploy."
            )
            # Not necessarily an error if no scripts are intended
            return True

        # 2. Get user UID/GID
        target_uid, target_gid = await self._get_user_uid_gid(self.config.USERNAME)
        if target_uid is None or target_gid is None:
            self.logger.error(
                f"Cannot get UID/GID for {self.config.USERNAME}. Skipping script deployment."
            )
            return False

        # 3. Create target ~/bin directory if needed
        try:
            if not target_bin_dir.exists():
                target_bin_dir.mkdir(exist_ok=True)
                os.chown(target_bin_dir, target_uid, target_gid)
                self.logger.info(f"Created user bin directory: {target_bin_dir}")
            elif not os.stat(target_bin_dir).st_uid == target_uid:
                os.chown(target_bin_dir, target_uid, target_gid)  # Correct ownership

            # Ensure ~/bin is in the user's PATH (usually handled by .profile/.bashrc)
            # Could add a check here or rely on the copied dotfiles.

        except Exception as e:
            self.logger.error(
                f"Failed to create or set ownership on {target_bin_dir}: {e}"
            )
            return False

        # 4. Copy scripts using rsync if available, else Python copy
        try:
            loop = asyncio.get_running_loop()
            if await command_exists_async("rsync"):
                rsync_src = str(src_scripts_dir) + "/"
                rsync_cmd = [
                    "rsync",
                    "-avh",
                    "--no-owner",
                    "--no-group",  # Don't copy source ownership
                    "--chown",
                    f"{target_uid}:{target_gid}",  # Set destination ownership
                    "--chmod=Du=rwx,Dgo=rx,Fu=rwx,Fgo=rx",  # Set executable perms (u=rwx,go=rx)
                    "--delete",  # Remove files in dest that are not in src
                    rsync_src,
                    str(target_bin_dir),
                ]
                self.logger.info(
                    f"Using rsync to deploy scripts from {src_scripts_dir} to {target_bin_dir}"
                )
                await run_command_async(rsync_cmd, check=True, timeout=120)
                self.logger.info("rsync deployment of scripts completed.")

            else:
                # Fallback to Python copy (less efficient, no delete)
                self.logger.warning(
                    "rsync not found. Falling back to basic Python copy for scripts."
                )

                def copy_scripts_action():
                    copied_count = 0
                    for item in src_scripts_dir.iterdir():
                        dest_item = target_bin_dir / item.name
                        try:
                            if item.is_file():
                                shutil.copy2(item, dest_item)
                                os.chown(dest_item, target_uid, target_gid)
                                os.chmod(
                                    dest_item, 0o755
                                )  # Make scripts executable (rwxr-xr-x)
                                copied_count += 1
                            elif item.is_dir():
                                # Handle subdirs if necessary, potentially recursively
                                self.logger.warning(
                                    f"Skipping subdirectory in scripts source: {item}"
                                )
                                pass
                        except Exception as copy_e:
                            self.logger.error(
                                f"Failed to copy script {item.name}: {copy_e}"
                            )
                            # Continue with others?
                    self.logger.info(
                        f"Fallback copy completed for {copied_count} script files."
                    )

                await loop.run_in_executor(None, copy_scripts_action)

            self.logger.info(f"User scripts deployed to {target_bin_dir}.")
            return True

        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.error(f"Script deployment using rsync failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during script deployment: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 5: Permissions & Advanced Storage Setup
    # ----------------------------------------------------------------
    async def phase_permissions_storage(self) -> bool:
        await self.print_section_async("Home Permissions Setup")  # Modified title
        status = True
        try:
            perm_ok = await run_with_progress_async(
                "Configuring user home directory permissions",
                self.home_permissions_async,
                task_name="permissions_storage",
            )
            if not perm_ok:
                status = False

            # ZFS setup removed
            self.logger.info("Skipping optional ZFS configuration.")

        except Exception as e:
            self.logger.error(f"Permissions/Storage phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["permissions_storage"]["status"] = "success"
            SETUP_STATUS["permissions_storage"]["message"] = (
                "Home directory permissions set."  # Modified message
            )
        else:
            SETUP_STATUS["permissions_storage"]["status"] = "failed"
            if not SETUP_STATUS["permissions_storage"]["message"]:
                SETUP_STATUS["permissions_storage"]["message"] = (
                    "Failed during permission setup."  # Modified message
                )

        return status

    async def home_permissions_async(self) -> bool:
        """Sets base ownership and permissions for the user's home directory."""
        home_dir = self.config.USER_HOME
        username = self.config.USERNAME

        # 1. Ensure home directory exists
        if not home_dir.is_dir():
            self.logger.error(
                f"Home directory {home_dir} for user {username} not found. Cannot set permissions."
            )
            # Should the script create it? Depends on policy. Assume useradd created it.
            return False

        # 2. Get user UID/GID
        target_uid, target_gid = await self._get_user_uid_gid(username)
        if target_uid is None or target_gid is None:
            self.logger.error(
                f"Cannot get UID/GID for {username}. Skipping home permissions."
            )
            return False

        overall_success = True
        loop = asyncio.get_running_loop()

        # 3. Set ownership recursively
        try:
            self.logger.info(
                f"Setting ownership of {home_dir} to {username}:{username} ({target_uid}:{target_gid})..."
            )
            # Use run_in_executor for recursive chown
            await loop.run_in_executor(
                None, self._recursive_chown, home_dir, target_uid, target_gid
            )
            self.logger.info(f"Ownership set for {home_dir}.")
        except Exception as e:
            self.logger.error(
                f"Failed to recursively set ownership for {home_dir}: {e}"
            )
            overall_success = False
            # This is likely a critical failure, might need to stop?

        # 4. Set base permissions for home directory itself (e.g., 700 or 750)
        target_mode = 0o700  # rwx------ (secure default)
        # target_mode = 0o750 # rwxr-x--- (allow group read/execute) - choose based on policy
        try:
            self.logger.info(
                f"Setting permissions for {home_dir} to {oct(target_mode)}..."
            )
            await loop.run_in_executor(None, lambda: os.chmod(home_dir, target_mode))
            self.logger.info(f"Base permissions set for {home_dir}.")
        except Exception as e:
            self.logger.error(f"Failed to set permissions on {home_dir}: {e}")
            overall_success = False

        # 5. Optional: Setgid bit on directories (if group collaboration intended)
        apply_setgid = False  # Set to True if needed
        if apply_setgid:
            try:
                self.logger.info(
                    "Applying setgid bit recursively on directories within home..."
                )
                # Use find command for efficiency
                find_cmd = [
                    "find",
                    str(home_dir),
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    "+",
                ]
                await run_command_async(find_cmd, check=True)
                self.logger.info("Setgid bit applied on directories.")
            except (subprocess.CalledProcessError, TimeoutError) as e:
                self.logger.warning(f"Failed to apply setgid bit: {e}")
                # Non-critical usually, so don't set overall_success = False

        # 6. Optional: ACLs (requires 'acl' package installed and filesystem support)
        apply_acls = False  # Set to True if needed
        if apply_acls and await command_exists_async("setfacl"):
            if "acl" not in self.config.PACKAGES:
                self.logger.warning(
                    "ACL package not listed, ensure it's installed for setfacl."
                )
            try:
                # Example: Set default ACLs for the user
                acl_cmd = [
                    "setfacl",
                    "-R",
                    "-d",
                    "-m",
                    f"u:{username}:rwx",
                    str(home_dir),
                ]
                self.logger.info(
                    f"Applying default ACLs for user {username} on {home_dir}..."
                )
                await run_command_async(acl_cmd, check=True)
                self.logger.info("Default ACLs applied.")
            except (subprocess.CalledProcessError, TimeoutError) as e:
                self.logger.warning(f"Failed to apply default ACLs: {e}")
        elif apply_acls:
            self.logger.warning(
                "setfacl command not found; skipping ACL configuration."
            )

        return overall_success

    # ----------------------------------------------------------------
    # Phase 6: Additional Server Tools
    # ----------------------------------------------------------------
    async def phase_additional_tools(self) -> bool:
        await self.print_section_async("Additional Server Tools Setup")
        status = True
        try:
            # Example: Install and enable SomethingElse (if needed)
            # something_ok = await run_with_progress_async("Installing SomethingElse", self.install_something_else_async, task_name="additional_tools")
            # if not something_ok:
            #     self.logger.warning("Failed to install SomethingElse.")
            # status = False # Uncomment if failure should fail the phase
            self.logger.info(
                "No additional server tools configured in this phase."
            )  # Placeholder message

        except Exception as e:
            self.logger.error(f"Additional tools phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["additional_tools"]["status"] = "success"
            SETUP_STATUS["additional_tools"]["message"] = (
                "Additional tools setup completed."
            )
        else:
            SETUP_STATUS["additional_tools"]["status"] = "failed"
            if not SETUP_STATUS["additional_tools"]["message"]:
                SETUP_STATUS["additional_tools"]["message"] = (
                    "Failed during additional tools setup."
                )

        return status

    # ----------------------------------------------------------------
    # Phase 7: Cleanup & Final Configurations
    # ----------------------------------------------------------------
    async def phase_cleanup_final(self) -> bool:
        await self.print_section_async("System Cleanup")
        status = True
        try:
            await run_with_progress_async(
                "Removing unused packages (dnf autoremove)",
                self.dnf_autoremove_async,
                task_name="cleanup_final",
            )
            await run_with_progress_async(
                "Cleaning dnf cache (dnf clean all)",
                self.dnf_clean_async,
                task_name="cleanup_final",
            )

            # Add any other final configuration tweaks here
            # e.g., disable unwanted services, final sysctl apply?

        except Exception as e:
            self.logger.error(f"Cleanup phase encountered an error: {e}")
            status = False

        # Update overall status
        if status:
            SETUP_STATUS["cleanup_final"]["status"] = "success"
            SETUP_STATUS["cleanup_final"]["message"] = "System cleanup performed."
        else:
            SETUP_STATUS["cleanup_final"]["status"] = "failed"
            if not SETUP_STATUS["cleanup_final"]["message"]:
                SETUP_STATUS["cleanup_final"]["message"] = (
                    "Failed during system cleanup."
                )

        return status

    async def dnf_autoremove_async(self) -> bool:
        """Runs dnf autoremove to remove orphaned dependencies."""
        self.logger.info("Running 'dnf autoremove -y'...")
        try:
            await run_command_async(
                ["dnf", "autoremove", "-y"], check=True, timeout=600
            )
            self.logger.info("dnf autoremove completed successfully.")
            return True
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.warning(f"dnf autoremove failed: {e}")
            return False  # Non-critical failure usually
        except Exception as e:
            self.logger.warning(f"Unexpected error during dnf autoremove: {e}")
            return False

    async def dnf_clean_async(self) -> bool:
        """Runs dnf clean all to remove cached package data."""
        self.logger.info("Running 'dnf clean all'...")
        try:
            await run_command_async(["dnf", "clean", "all"], check=True, timeout=120)
            self.logger.info("dnf clean all completed successfully.")
            return True
        except (subprocess.CalledProcessError, TimeoutError) as e:
            self.logger.warning(f"dnf clean all failed: {e}")
            return False  # Non-critical
        except Exception as e:
            self.logger.warning(f"Unexpected error during dnf clean: {e}")
            return False

    # ----------------------------------------------------------------
    # Phase 8: Final Checks
    # ----------------------------------------------------------------
    async def phase_final_checks(self) -> bool:
        await self.print_section_async("Final System Checks & Summary")
        info = {}
        try:
            info = await run_with_progress_async(
                "Performing final system status checks",
                self.final_checks_async,
                task_name="final",
            )
        except Exception as e:
            self.logger.error(f"Final checks encountered an error: {e}")
            SETUP_STATUS["final"]["status"] = "failed"
            SETUP_STATUS["final"]["message"] = f"Failed: {str(e)}"
            return False  # Mark phase as failed

        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Check if reboot is recommended based on /run/reboot-required
        reboot_recommended = Path("/run/reboot-required").exists()
        reboot_msg = (
            "[bold yellow]⚠ A system reboot is recommended to apply all changes (e.g., kernel updates).[/bold yellow]"
            if reboot_recommended
            else "[info]No immediate reboot required, but recommended after major changes.[/info]"
        )

        summary = f"""
✅ [bold green]Fedora Server Setup & Hardening completed![/bold green]

⏱️ Total runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s

System Information:
  Distribution: {info.get("distribution", "Unknown")}
  Kernel Version: {info.get("kernel", "Unknown")}
  Hostname: {info.get("hostname", "Unknown")}
  Uptime: {info.get("uptime", "Unknown")}
  Root Disk Usage: {info.get("disk_usage", "Unknown")}
  Memory Usage: {info.get("memory", "Unknown")}

{reboot_msg}

Review the log file for details: {self.config.LOG_FILE}
"""
        display_panel(summary, style=NordColors.GREEN, title="Setup Complete")
        print_status_report()  # Show final status table
        self.logger.info("Final system checks completed. Setup finished.")
        SETUP_STATUS["final"]["status"] = "success"
        SETUP_STATUS["final"]["message"] = "Setup finished. Reboot recommended: " + str(
            reboot_recommended
        )
        return True

    async def final_checks_async(self) -> Dict[str, str]:
        """Gathers final system state information."""
        info = {}
        checks = {
            "kernel": ["uname", "-r"],
            "distribution": [
                "lsb_release",
                "-ds",
            ],  # Fallback if /etc/os-release check failed earlier
            "hostname": ["hostname"],
            "uptime": ["uptime", "-p"],
            # Use simpler df/free output capture
            "disk_usage": ["df", "-h", "/"],
            "memory": ["free", "-h"],
        }

        # Try getting distro from os-release first
        try:
            release_file = Path("/etc/os-release")
            if release_file.exists():
                content = release_file.read_text()
                os_vars = dict(
                    line.split("=", 1) for line in content.splitlines() if "=" in line
                )
                info["distribution"] = os_vars.get("PRETTY_NAME", "Unknown OS").strip(
                    '"'
                )
            elif "distribution" in checks:  # Use lsb_release as fallback
                result = await run_command_async(
                    checks["distribution"], capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    info["distribution"] = result.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get distribution info: {e}")
            info["distribution"] = "Unknown"
        if "distribution" in checks:
            del checks["distribution"]  # Remove if handled

        for key, cmd in checks.items():
            try:
                result = await run_command_async(
                    cmd, capture_output=True, text=True, check=True
                )
                output = result.stdout.strip()
                if key == "disk_usage":
                    # Extract relevant line from df output
                    lines = output.splitlines()
                    info[key] = lines[1] if len(lines) > 1 else output
                elif key == "memory":
                    # Extract relevant line from free output
                    lines = output.splitlines()
                    mem_line = next(
                        (line for line in lines if line.startswith("Mem:")), None
                    )
                    swap_line = next(
                        (line for line in lines if line.startswith("Swap:")), None
                    )
                    info[key] = (mem_line if mem_line else "") + (
                        " | " + swap_line if swap_line else ""
                    )
                else:
                    info[key] = output
                self.logger.info(f"Final Check - {key.capitalize()}: {info[key]}")
            except Exception as e:
                self.logger.warning(f"Failed to get final check info for '{key}': {e}")
                info[key] = "Unknown"

        return info


# ----------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------
async def main_async() -> None:
    console.print(create_header(APP_NAME))  # Show header early
    setup_instance = None  # Initialize before try block
    try:
        config = Config()
        setup_instance = FedoraServerSetup(config)
        # Make instance globally accessible for signal handler (if needed, though direct access is better)
        globals()["setup_instance"] = setup_instance

        setup_instance.logger.info(f"--- {APP_NAME} v{VERSION} Started ---")
        setup_instance.logger.info(f"Log file: {config.LOG_FILE}")
        setup_instance.logger.info(f"Target user: {config.USERNAME}")

        # Execute phases sequentially, stopping if a critical phase fails
        if not await setup_instance.phase_preflight():
            raise SystemExit(
                "Pre-flight checks failed. Aborting."
            )  # Use SystemExit for cleaner exit code handling

        if not await setup_instance.phase_system_update():
            raise SystemExit(
                "System update phase failed. Aborting."
            )  # Critical failure

        if not await setup_instance.phase_repo_shell_setup():
            # Decide if this is critical. Maybe just warn?
            setup_instance.logger.error(
                "Repository & Shell setup phase failed. Continuing with potential issues..."
            )
            # raise SystemExit("Repository & Shell setup phase failed. Aborting.")

        if not await setup_instance.phase_security_hardening():
            # Security is usually critical
            raise SystemExit("Security hardening phase failed. Aborting.")

        if not await setup_instance.phase_user_customization():
            setup_instance.logger.warning(
                "User customization phase failed. Continuing..."
            )

        if not await setup_instance.phase_permissions_storage():
            setup_instance.logger.warning(
                "Permissions & Storage phase failed. Continuing..."
            )

        if not await setup_instance.phase_additional_tools():
            setup_instance.logger.warning(
                "Additional tools phase failed. Continuing..."
            )

        if not await setup_instance.phase_cleanup_final():
            setup_instance.logger.warning("Cleanup phase failed. Continuing...")

        if not await setup_instance.phase_final_checks():
            setup_instance.logger.error("Final checks phase failed.")
            # Don't abort here, just report the failure

        # If we reach here, all critical phases passed.
        setup_instance.logger.info(f"--- {APP_NAME} Finished ---")

    except SystemExit as exit_e:
        console.print(f"\n[error]Setup aborted: {exit_e}[/error]")
        if setup_instance:
            setup_instance.logger.critical(f"Setup aborted: {exit_e}")
            print_status_report()  # Show status even on abort
        sys.exit(1)  # Exit with error code
    except KeyboardInterrupt:
        console.print("\n[warning]Setup interrupted by user (Ctrl+C).[/warning]")
        if setup_instance:
            setup_instance.logger.warning("Setup interrupted by user.")
            print_status_report()
            # Cleanup is handled by the signal handler now
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        console.print(f"\n[bold red]--- A critical error occurred ---[/bold red]")
        console.print_exception(
            show_locals=False
        )  # Show traceback for unexpected errors
        if setup_instance:
            setup_instance.logger.critical(
                f"Fatal error during setup: {e}", exc_info=True
            )
            print_status_report()
            # Cleanup handled by signal handler/atexit potentially, or add explicit call here if needed
        sys.exit(1)
    finally:
        # Optional: Final cleanup actions regardless of success/failure
        if setup_instance:
            # Ensure logs are flushed if using buffered handlers
            logging.shutdown()
            # No automatic cleanup call here, rely on signal handler or let it finish naturally


def main() -> None:
    loop = None
    setup_instance_ref = None  # Use a local var to pass to cleanup if needed
    try:
        # Use try/finally to ensure loop closure
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers for graceful shutdown on INT/TERM
        setup_signal_handlers(loop)

        # Run the main async function
        # Keep a reference accessible for signal handler cleanup
        global setup_instance
        setup_instance = None  # Ensure it's None initially

        loop.run_until_complete(main_async())

        # Store reference for final cleanup if needed after loop completes normally
        setup_instance_ref = setup_instance

    except KeyboardInterrupt:
        # This might be caught inside main_async already, but handle here as fallback
        print_warning("\nKeyboard interrupt received during main execution setup.")
    except Exception as e:
        # Catch errors during loop setup/run_until_complete itself
        print_error(f"An unexpected error occurred in the main loop driver: {e}")
        console.print_exception(show_locals=False)
    finally:
        # --- Cleanup ---
        if loop:
            try:
                # Call async cleanup if instance exists and loop is running
                if setup_instance_ref and loop.is_running():
                    # This is tricky because the signal handler might have already cleaned up.
                    # Avoid double cleanup. Signal handler is preferred.
                    # loop.run_until_complete(setup_instance_ref.cleanup_async())
                    pass

                # Cancel any remaining tasks (important!)
                tasks = asyncio.all_tasks(loop)
                if tasks:
                    print_debug(f"Cancelling {len(tasks)} outstanding tasks...")
                    for task in tasks:
                        task.cancel()
                    # Wait for tasks to finish cancelling
                    loop.run_until_complete(
                        asyncio.gather(*tasks, return_exceptions=True)
                    )
                    print_debug("Tasks cancelled.")

                # Shutdown async generators
                loop.run_until_complete(loop.shutdown_asyncgens())

            except Exception as cleanup_error:
                print_error(f"Error during event loop cleanup: {cleanup_error}")
            finally:
                # Ensure loop is closed
                if not loop.is_closed():
                    loop.close()
                    print_debug("Event loop closed.")

        print_message("Application terminated.", NordColors.FROST_3)


# Add a wrapper for print_debug that uses the console if available
def print_debug(msg: str):
    if "console" in globals():
        console.print(f"[debug]DBG: {msg}[/debug]")
    else:
        print(f"DBG: {msg}")


if __name__ == "__main__":
    # Ensure script is run as root before even starting async loop
    if os.geteuid() != 0:
        print("Error: This script must be run as root or with sudo.", file=sys.stderr)
        sys.exit(1)
    main()
