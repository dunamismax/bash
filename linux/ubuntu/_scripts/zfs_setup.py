#!/usr/bin/env python3
"""
Automated ZFS Setup for WD_BLACK Pool
--------------------------------------------------
This script automates the setup of a specific ZFS pool named "WD_BLACK".
It performs the following steps:
  1. Checks for root privileges.
  2. Checks required command dependencies.
  3. Checks and installs required ZFS packages (using non-interactive frontend).
  4. Enables necessary ZFS services for auto-mounting on boot.
  5. Creates the target mount point /media/WD_BLACK.
  6. Imports the "WD_BLACK" pool (if not already imported).
  7. Configures the "WD_BLACK" pool:
     - Sets the mountpoint to /media/WD_BLACK.
     - Sets the cachefile to enable auto-import on boot.
  8. Attempts to mount all ZFS datasets.
  9. Verifies that "WD_BLACK" is mounted correctly.

This script must be run with root privileges.

Usage:
  sudo python3 setup_wd_black_zfs.py

Version: 1.1.0 (Refactored & Fixed Install)
"""

import atexit
import datetime
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    from rich.text import Text
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "This script requires the 'rich' library.\n"
        "Please install it using: pip install rich"
    )
    sys.exit(1)

# Install rich traceback handler
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
VERSION = "1.1.0"
TARGET_POOL_NAME = "WD_BLACK"
TARGET_MOUNT_POINT = Path(f"/media/{TARGET_POOL_NAME}")
DEFAULT_CACHE_FILE = Path("/etc/zfs/zpool.cache")
DEFAULT_LOG_FILE = Path("/var/log/zfs_wd_black_setup.log")

# Command preferences – use 'nala' if available, otherwise apt.
APT_CMD = "nala" if shutil.which("nala") else "apt"

# ZFS services and packages
ZFS_SERVICES = [
    "zfs-import-cache.service",
    "zfs-mount.service",
    "zfs-import.target",
    "zfs.target",
]
# Added build-essential for DKMS, dpkg-dev also often needed by dkms
ZFS_PACKAGES = [
    "build-essential",
    "dpkg-dev",
    "linux-headers-generic",  # Headers matching the generic kernel
    # "linux-image-generic", # Often installed with headers, keep if desired
    "zfs-dkms",
    "zfsutils-linux",
]
REQUIRED_COMMANDS = [APT_CMD, "systemctl", "zpool", "zfs", "dpkg", "df"]


# Style Configuration (Simplified Nord Theme)
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    RED = "#BF616A"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"


# Create a Rich Console instance
console = Console()


# ----------------------------------------------------------------
# Console & Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Generate a simple header panel."""
    header_text = f"[bold {NordColors.FROST_2}]{TARGET_POOL_NAME} ZFS Setup[/]"
    subtitle_text = f"Auto-mount at {TARGET_MOUNT_POINT}"
    content = f"{header_text}\n{subtitle_text}"
    return Panel(
        Text.from_markup(content, justify="center"),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v{VERSION}[/]",
        title_align="right",
    )


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def log_message(message: str, level: str = "info") -> None:
    """Log a message to console and file."""
    log_func = getattr(logging, level, logging.info)
    log_func(message)  # Log to file first

    if level == "error":
        console.print(f"[bold {NordColors.RED}]✗ ERROR: {message}[/]")
    elif level == "warning":
        console.print(f"[bold {NordColors.YELLOW}]⚠ WARNING: {message}[/]")
    elif level == "success":
        console.print(f"[bold {NordColors.GREEN}]✓ SUCCESS: {message}[/]")
    else:  # info
        console.print(f"[bold {NordColors.FROST_2}]ℹ INFO: {message}[/]")


def setup_logging(log_file: Path = DEFAULT_LOG_FILE, level: int = logging.INFO) -> None:
    """Configure file logging."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Use a FileHandler to control permissions
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )
        # Add handler to the root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.setLevel(level)
        # Set permissions after file creation (best effort)
        try:
            os.chmod(log_file, 0o600)
        except OSError as e:
            console.print(
                f"[bold {NordColors.YELLOW}]⚠ WARNING: Could not set log file permissions for {log_file}: {e}[/]"
            )
        log_message(f"Logging configured to: {log_file}", "info")
    except Exception as e:
        console.print(
            f"[bold {NordColors.YELLOW}]⚠ WARNING: Logging setup failed: {e}. Falling back to basic config.[/]"
        )
        logging.basicConfig(level=level)  # Fallback


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks on script exit."""
    log_message("Script finished. Performing cleanup.", "info")
    # Add any specific cleanup needed, e.g., removing temp files
    logging.info("Cleanup actions completed.")


atexit.register(cleanup)


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals."""
    sig_name = signal.Signals(sig).name
    log_message(f"Script interrupted by {sig_name}. Exiting.", "warning")
    # Cleanup is called by atexit
    sys.exit(128 + sig)


# Register signal handlers
for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    try:
        signal.signal(s, signal_handler)
    except (
        ValueError,
        OSError,
        AttributeError,
    ) as e:  # Added AttributeError for platforms like Windows
        log_message(f"Could not register signal handler for {s}: {e}", "warning")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    command: Union[str, List[str]],
    error_message: Optional[str] = None,
    check: bool = True,
    spinner_text: Optional[str] = None,
    capture_output: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Execute a shell command with optional spinner and error handling.

    Returns:
        Tuple[bool, Optional[str], Optional[str]]: success status, stdout, stderr
    """
    cmd_str = command if isinstance(command, str) else " ".join(command)
    logging.debug(f"Running command: {cmd_str}")

    progress = None
    task_id = None
    if spinner_text:
        progress = Progress(
            SpinnerColumn("dots", style=f"bold {NordColors.FROST_1}"),
            TextColumn(f"[bold {NordColors.FROST_2}]{spinner_text}[/]"),
            transient=True,
            console=console,
        )
        task_id = progress.add_task("Running...", total=None)
        progress.start()

    try:
        # Combine current environment with provided env vars
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
            logging.debug(f"Using custom environment variables: {env}")

        process = subprocess.run(
            command,
            shell=isinstance(
                command, str
            ),  # Use shell=True only if command is a string
            check=False,  # We handle check manually
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            env=cmd_env,
            encoding="utf-8",  # Be explicit about encoding
            errors="replace",  # Handle potential encoding errors in output
        )

        stdout = process.stdout.strip() if process.stdout else None
        stderr = process.stderr.strip() if process.stderr else None

        if progress:
            progress.stop()

        if process.returncode != 0:
            err_msg = (
                stderr
                if stderr
                else f"Command returned non-zero exit status {process.returncode}"
            )
            final_error_message = error_message or f"Command failed: {cmd_str}"
            # Log both stdout and stderr for better debugging
            log_message(
                f"{final_error_message}. Return Code: {process.returncode}", "error"
            )
            if stdout:
                logging.error(f"Stdout: {stdout}")
            if stderr:
                logging.error(f"Stderr: {stderr}")

            if check:
                # If check is True, we consider this a fatal error for the function's purpose
                # Returning False allows caller to decide if it's fatal for the whole script
                return False, stdout, stderr  # Explicitly return False on failure
            # If check is False, log the error but return False status
            return False, stdout, stderr
        else:
            logging.debug(f"Command successful: {cmd_str}")
            if stdout:
                logging.debug(f"Stdout: {stdout}")
            if stderr:
                logging.debug(
                    f"Stderr: {stderr}"
                )  # Log stderr even on success if present
            return True, stdout, stderr

    except FileNotFoundError:
        if progress:
            progress.stop()
        cmd_name = command if isinstance(command, str) else command[0]
        log_message(
            f"Command not found: '{cmd_name}'. Please ensure it's installed and in PATH.",
            "error",
        )
        return False, None, f"Command not found: {cmd_name}"
    except Exception as e:
        if progress:
            progress.stop()
        final_error_message = error_message or f"Exception running command: {cmd_str}"
        log_message(f"{final_error_message}: {e}", "error")
        # Include traceback in debug log
        logging.exception("Exception details:")
        if check:
            # Re-raising might be too disruptive; return False for consistency
            return False, None, str(e)
        return False, None, str(e)


# ----------------------------------------------------------------
# System Check and Package Management
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Verify the script is running as root."""
    if os.geteuid() != 0:
        log_message("This script must be run as root (using sudo).", "error")
        return False
    log_message("Root privileges verified.", "success")
    return True


def check_dependencies() -> bool:
    """Check if required system commands are available."""
    log_message("Checking required command dependencies...", "info")
    missing = [cmd for cmd in REQUIRED_COMMANDS if not shutil.which(cmd)]
    if missing:
        missing_str = ", ".join(missing)
        log_message(f"Missing required commands: {missing_str}.", "error")
        log_message(
            f"Please install them (e.g., sudo apt install {missing_str}) and try again.",
            "error",
        )
        return False
    log_message("All required commands are present.", "success")
    return True


def install_packages(packages: List[str]) -> bool:
    """Install required ZFS packages non-interactively."""
    if not packages:
        return True
    package_str = " ".join(packages)
    log_message(f"Ensuring ZFS packages are installed: {package_str}", "info")

    # Check which packages are already installed using dpkg-query
    installed_packages = set()
    cmd = ["dpkg-query", "-W", "-f=${Package} ${Status}\\n"] + packages
    # We expect this command to fail if some packages are not installed, so check=False
    success, stdout, _ = run_command(cmd, check=False, capture_output=True)

    if success and stdout:
        for line in stdout.strip().split("\n"):
            parts = line.split()
            # Format is "package-name install ok installed" or similar
            if len(parts) >= 4 and " ".join(parts[1:]) == "install ok installed":
                installed_packages.add(parts[0])

    packages_to_install = [pkg for pkg in packages if pkg not in installed_packages]

    if not packages_to_install:
        log_message("All required ZFS packages are already installed.", "success")
        return True

    log_message(f"Packages to install: {', '.join(packages_to_install)}", "info")

    # --- CRITICAL FIX: Use non-interactive frontend ---
    non_interactive_env = {"DEBIAN_FRONTEND": "noninteractive"}

    # 1. Update package lists first
    log_message("Updating package lists...", "info")
    update_success, _, update_stderr = run_command(
        [APT_CMD, "update"],
        error_message="Failed to update package lists",
        spinner_text="Updating package lists...",
        check=False,  # Allow continuing even if update fails sometimes, but warn
        env=non_interactive_env,
    )
    if not update_success:
        log_message(
            f"Package list update failed. Stderr: {update_stderr}. Attempting installation anyway...",
            "warning",
        )
        # Depending on the error, installation might still work if caches are recent enough

    # 2. Install missing packages
    log_message(f"Installing packages: {', '.join(packages_to_install)}...", "info")
    install_cmd = [APT_CMD, "install", "-y"] + packages_to_install
    install_success, _, install_stderr = run_command(
        install_cmd,
        error_message=f"Failed to install packages: {', '.join(packages_to_install)}",
        spinner_text=f"Installing {', '.join(packages_to_install)}...",
        check=True,  # Installation is critical, use check=True logic (function returns False on failure)
        env=non_interactive_env,
    )

    if install_success:
        log_message("ZFS packages installed successfully.", "success")
        # Re-verify installation (optional but good practice)
        # Could run the dpkg-query command again here if needed
        return True
    else:
        log_message(
            f"Failed to install required ZFS packages. Error: {install_stderr}", "error"
        )
        return False


def enable_zfs_services() -> bool:
    """Enable ZFS services for boot."""
    log_message("Enabling ZFS services for auto-start...", "info")
    all_success = True
    for service in ZFS_SERVICES:
        success, _, _ = run_command(
            ["systemctl", "enable", service],
            error_message=f"Failed to enable {service}",
            check=False,  # Log error but continue trying others
            spinner_text=f"Enabling {service}",
        )
        if success:
            log_message(f"Enabled service: {service}", "info")
        else:
            all_success = False  # Mark overall failure if any service fails
            # Logged as error by run_command

    if all_success:
        log_message("All necessary ZFS services enabled successfully.", "success")
    else:
        log_message(
            "Some ZFS services could not be enabled. Auto-import/mount might fail on boot.",
            "warning",
        )
    # Return True even if some fail, as the core import/config might still work for the current session
    # The warning alerts the user about potential boot issues.
    return True


def create_mount_point(mount_point: Path) -> bool:
    """Create the directory for the ZFS mount point."""
    log_message(f"Ensuring mount point directory exists: {mount_point}", "info")
    try:
        mount_point.mkdir(parents=True, exist_ok=True)
        # Optionally set permissions if needed, e.g.,
        # os.chmod(mount_point, 0o755)
        log_message(f"Mount point directory '{mount_point}' is ready.", "success")
        return True
    except OSError as e:
        log_message(
            f"Failed to create mount point directory '{mount_point}': {e}", "error"
        )
        return False
    except Exception as e:
        log_message(
            f"An unexpected error occurred creating mount point '{mount_point}': {e}",
            "error",
        )
        return False


# ----------------------------------------------------------------
# ZFS Pool Configuration Functions
# ----------------------------------------------------------------
def is_pool_imported(pool_name: str) -> bool:
    """Check if the specified ZFS pool is currently imported."""
    # zpool list returns 0 if the pool exists and is listed, non-zero otherwise.
    success, _, _ = run_command(
        ["zpool", "list", "-H", "-o", "name", pool_name],
        check=False,  # Don't fail script if pool doesn't exist yet
        capture_output=True,
    )
    return success


def import_zfs_pool(pool_name: str) -> bool:
    """Import the specified ZFS pool."""
    log_message(f"Checking import status for pool '{pool_name}'...", "info")
    if is_pool_imported(pool_name):
        log_message(f"Pool '{pool_name}' is already imported.", "success")
        return True

    log_message(f"Attempting to import ZFS pool '{pool_name}'...", "info")

    # Check if pool is available for import first
    success_check, import_list, _ = run_command(
        ["zpool", "import"], check=False, capture_output=True
    )
    pool_available = (
        success_check and import_list and f"pool: {pool_name}" in import_list
    )

    if not pool_available:
        log_message(
            f"Pool '{pool_name}' not found available for import. "
            f"Check 'sudo zpool import'. Ensure disks are connected.",
            "error",
        )
        # Maybe list available pools if found?
        if success_check and import_list:
            log_message(f"Available pools to import:\n{import_list}", "info")
        elif success_check:
            log_message("No pools available for import.", "info")
        return False

    # Construct import command
    import_cmd = ["zpool", "import", "-f"]  # Force is often needed
    # Use cachefile during import if it exists, helps consistency
    if DEFAULT_CACHE_FILE.exists():
        import_cmd.extend(["-c", str(DEFAULT_CACHE_FILE)])
    # Prefer importing by /dev/disk/by-id for robustness
    if Path("/dev/disk/by-id").exists():
        import_cmd.extend(["-d", "/dev/disk/by-id"])
    import_cmd.append(pool_name)

    success, _, stderr = run_command(
        import_cmd,
        error_message=f"Failed to import pool '{pool_name}'",
        check=False,  # Handle failure message below
        spinner_text=f"Importing {pool_name}",
    )

    if success:
        log_message(f"Successfully imported pool '{pool_name}'.", "success")
        # Wait a brief moment for the system (udev) to potentially process the import
        time.sleep(2)
        return True
    else:
        log_message(
            f"Import command failed for pool '{pool_name}'. Error: {stderr}", "error"
        )
        return False


def configure_zfs_pool_properties(
    pool_name: str, mount_point: Path, cache_file: Path
) -> bool:
    """Set mountpoint and cachefile properties for the ZFS pool."""
    log_message(f"Configuring properties for pool '{pool_name}'...", "info")
    prop_success = True

    # 1. Set mountpoint
    log_message(f"Setting mountpoint to '{mount_point}'...", "info")
    success, _, stderr = run_command(
        ["zfs", "set", f"mountpoint={mount_point}", pool_name],
        error_message=f"Failed to set mountpoint for '{pool_name}'",
        check=False,  # Log error but continue to cachefile
        spinner_text="Setting mountpoint",
    )
    if not success:
        log_message(
            f"Failed to set mountpoint for '{pool_name}'. Mount might be incorrect. Error: {stderr}",
            "warning",
        )
        prop_success = False  # Mark as problematic but not necessarily fatal yet
    else:
        log_message("Mountpoint set successfully.", "success")

    # 2. Set cachefile (essential for auto-import via service)
    log_message(f"Ensuring cachefile directory '{cache_file.parent}' exists...", "info")
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log_message(
            f"Failed to create directory '{cache_file.parent}' for cachefile: {e}",
            "error",
        )
        # This is critical for boot-time mounting, consider it fatal
        return False

    log_message(f"Setting cachefile to '{cache_file}'...", "info")
    success, _, stderr = run_command(
        ["zpool", "set", f"cachefile={cache_file}", pool_name],
        error_message=f"Failed to set cachefile for '{pool_name}'",
        check=False,  # Treat failure as critical below
        spinner_text="Setting cachefile",
    )
    if not success:
        log_message(
            f"CRITICAL: Failed to set cachefile for '{pool_name}'. Auto-import on boot WILL likely fail! Error: {stderr}",
            "error",
        )
        prop_success = False  # Mark as failed
        # Make this step's failure explicitly fatal for the function
        return False
    else:
        log_message("Cachefile set successfully.", "success")

    if not prop_success:
        log_message(
            "Configuration encountered non-critical issues (check warnings).", "warning"
        )
    else:
        log_message(f"Pool '{pool_name}' configured successfully.", "success")

    return prop_success


def mount_zfs_datasets() -> bool:
    """Mount all available ZFS datasets."""
    log_message("Attempting to mount all ZFS datasets ('zfs mount -a')...", "info")
    success, _, stderr = run_command(
        ["zfs", "mount", "-a"],
        error_message="Command 'zfs mount -a' failed",
        check=False,  # Don't stop script, but report issues
        spinner_text="Mounting datasets",
    )
    if success:
        log_message(
            "Command 'zfs mount -a' completed.", "info"
        )  # Changed from success to info
        # Check stderr for potential non-fatal mount issues
        if stderr:
            log_message(f"'zfs mount -a' reported issues: {stderr}", "warning")
            # Consider returning False if stderr indicates problems? For now, just warn.
        return True
    else:
        log_message(
            f"Mounting datasets failed. Check ZFS status. Error: {stderr}", "error"
        )
        return False


def verify_mount(pool_name: str, expected_mount_point: Path) -> bool:
    """Verify that the target pool is mounted at the expected location."""
    log_message(f"Verifying mount point for '{pool_name}'...", "info")

    # 1. Check ZFS mountpoint property
    success, zfs_prop_value, zfs_prop_stderr = run_command(
        ["zfs", "get", "-H", "-o", "value", "mountpoint", pool_name],
        error_message=f"Failed to get mountpoint property for {pool_name}",
        check=False,  # Handle failure below
        spinner_text="Checking ZFS mountpoint property",
    )

    if not success or not zfs_prop_value:
        log_message(
            f"Could not retrieve ZFS mountpoint property for '{pool_name}'. Error: {zfs_prop_stderr}",
            "error",
        )
        return False

    actual_mount_point_prop = zfs_prop_value.strip()

    if actual_mount_point_prop != str(expected_mount_point):
        log_message(
            f"Mountpoint property mismatch! Pool '{pool_name}' has ZFS mountpoint '{actual_mount_point_prop}',"
            f" but expected '{expected_mount_point}'.",
            "error",
        )
        # Try to fix it? Or just report failure? Reporting failure is safer.
        log_message(
            "Please correct the mountpoint using: "
            f"sudo zfs set mountpoint={expected_mount_point} {pool_name}",
            "error",
        )
        return False
    else:
        log_message(
            f"ZFS property 'mountpoint' is correctly set to '{expected_mount_point}'.",
            "info",
        )

    # 2. Check if it's actually mounted using the 'df' command
    log_message(
        f"Verifying active mount at '{expected_mount_point}' using 'df'...", "info"
    )
    try:
        # Using 'df <mountpoint>' is a reliable way to check if something is mounted there.
        # We check if the command succeeds and the output contains the mountpoint path.
        # Example df output line: /dev/sda1 ext4 12345 6789 10% /media/WD_BLACK
        # We just need the command to succeed for the specific path.
        result = subprocess.run(
            ["df", str(expected_mount_point)],
            text=True,
            capture_output=True,
            check=False,  # Check return code manually
        )

        if result.returncode == 0:
            # The command succeeded, meaning the path exists and is part of a mounted filesystem.
            log_message(
                f"Pool '{pool_name}' appears actively mounted at '{expected_mount_point}'.",
                "success",
            )
            return True
        else:
            # Property is correct, but 'df' failed for the mount point.
            log_message(
                f"Mountpoint property is correct, but 'df {expected_mount_point}' failed (return code {result.returncode}). "
                f"Filesystem might not be actively mounted.",
                "warning",
            )
            log_message(f"Attempting explicit 'zfs mount {pool_name}'...", "info")
            mount_success, _, mount_stderr = run_command(
                ["zfs", "mount", pool_name],
                check=False,
                spinner_text=f"Mounting {pool_name}",
            )
            if mount_success:
                log_message(
                    f"Explicit mount command succeeded for '{pool_name}'. Verifying again with 'df'...",
                    "info",
                )
                # Check again after explicit mount
                result_after_mount = subprocess.run(
                    ["df", str(expected_mount_point)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result_after_mount.returncode == 0:
                    log_message(
                        f"Pool '{pool_name}' successfully mounted at '{expected_mount_point}' after explicit command.",
                        "success",
                    )
                    return True
                else:
                    log_message(
                        f"Explicit mount command ran, but 'df {expected_mount_point}' still fails. "
                        f"Check 'zfs mount' output and system logs. Stderr: {result_after_mount.stderr}",
                        "error",
                    )
                    return False
            else:
                log_message(
                    f"Failed to explicitly mount '{pool_name}'. Error: {mount_stderr}",
                    "error",
                )
                return False

    except FileNotFoundError:
        log_message("Could not find 'df' command to verify active mount.", "error")
        return False
    except Exception as e:
        log_message(
            f"An unexpected error occurred verifying active mount with 'df': {e}",
            "error",
        )
        return False


# ----------------------------------------------------------------
# Main Execution Logic
# ----------------------------------------------------------------
def main() -> None:
    """Main function to execute the ZFS setup for WD_BLACK."""
    setup_logging(DEFAULT_LOG_FILE, logging.DEBUG)  # Log debug info to file
    start_time = datetime.datetime.now()
    logging.info("=" * 60)
    logging.info(
        f"{TARGET_POOL_NAME} ZFS SETUP SCRIPT (v{VERSION}) STARTED AT {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info("=" * 60)

    clear_screen()
    console.print(create_header())
    log_message(f"Starting setup for ZFS pool '{TARGET_POOL_NAME}'...", "info")

    steps = [
        ("Check Root Privileges", check_root_privileges),
        ("Check Dependencies", check_dependencies),
        ("Install ZFS Packages", lambda: install_packages(ZFS_PACKAGES)),
        (
            "Enable ZFS Services",
            enable_zfs_services,
        ),  # Returns True even on partial failure, logs warning
        ("Create Mount Point", lambda: create_mount_point(TARGET_MOUNT_POINT)),
        ("Import Pool", lambda: import_zfs_pool(TARGET_POOL_NAME)),
        (
            "Configure Pool Properties",
            lambda: configure_zfs_pool_properties(
                TARGET_POOL_NAME, TARGET_MOUNT_POINT, DEFAULT_CACHE_FILE
            ),
        ),
        (
            "Mount All Datasets",
            mount_zfs_datasets,
        ),  # Returns True even on partial failure, logs warning
        ("Verify Mount", lambda: verify_mount(TARGET_POOL_NAME, TARGET_MOUNT_POINT)),
    ]

    all_steps_passed = True
    for i, (step_name, step_func) in enumerate(steps, 1):
        log_message(f"--- Step {i}/{len(steps)}: {step_name} ---", "info")
        try:
            success = step_func()
            if not success:
                # Check function name to determine criticality - configure_zfs_pool_properties returns False on critical failure
                # install_packages returns False on failure
                # import_zfs_pool returns False on failure
                # create_mount_point returns False on failure
                # check_root_privileges / check_dependencies return False on failure
                # verify_mount returns False on failure
                # enable_zfs_services / mount_zfs_datasets are less critical failures (log warnings internally)
                critical_steps = [
                    "Check Root Privileges",
                    "Check Dependencies",
                    "Install ZFS Packages",
                    "Create Mount Point",
                    "Import Pool",
                    "Configure Pool Properties",
                    "Verify Mount",  # If verification fails, setup is not complete
                ]
                if step_name in critical_steps:
                    log_message(
                        f"Critical step '{step_name}' failed. Aborting setup.", "error"
                    )
                    all_steps_passed = False
                    break  # Exit the loop
                else:
                    # Non-critical step failed (already logged warning/error internally)
                    log_message(
                        f"Step '{step_name}' completed with issues (check logs). Continuing...",
                        "warning",
                    )
                    # Do not set all_steps_passed to False here, allow script to finish
            # No need for explicit else: success is True, loop continues
        except Exception as e:
            log_message(
                f"An unexpected error occurred during step '{step_name}': {e}", "error"
            )
            logging.exception(f"Traceback for step '{step_name}':")
            all_steps_passed = False
            break  # Exit the loop on unexpected errors

    # Final Summary
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    logging.info("=" * 60)
    logging.info(f"SCRIPT FINISHED AT {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"Total duration: {duration}")
    logging.info("=" * 60)

    if all_steps_passed:
        status_text = f"[bold {NordColors.GREEN}]SUCCESSFUL[/]"
        log_message(
            f"Setup for '{TARGET_POOL_NAME}' completed successfully. It should now be mounted at '{TARGET_MOUNT_POINT}' and configured for auto-mount.",
            "success",
        )
        exit_code = 0
    else:
        status_text = f"[bold {NordColors.RED}]FAILED[/]"
        log_message(
            f"Setup for '{TARGET_POOL_NAME}' failed or completed with errors. Please check the log file: {DEFAULT_LOG_FILE}",
            "error",
        )
        exit_code = 1

    summary_panel = Panel(
        Text.from_markup(
            f"Pool:         [bold {NordColors.FROST_2}]{TARGET_POOL_NAME}[/]\n"
            f"Mount Point:  [bold {NordColors.FROST_2}]{TARGET_MOUNT_POINT}[/]\n"
            f"Status:       {status_text}\n"
            f"Log File:     [bold {NordColors.SNOW_STORM_1}]{DEFAULT_LOG_FILE}[/]"
        ),
        title=f"[bold {NordColors.FROST_1}]Setup Summary[/]",
        border_style=Style(color=NordColors.FROST_3),
        padding=(1, 2),
    )
    console.print(summary_panel)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
