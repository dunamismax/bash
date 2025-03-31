#!/usr/bin/env python3
"""
Automated ZFS Setup for WD_BLACK Pool
--------------------------------------------------
This script automates the setup of a specific ZFS pool named "WD_BLACK".
It performs the following steps:
  1. Checks for root privileges.
  2. Checks and installs required ZFS packages (zfsutils-linux, zfs-dkms).
  3. Enables necessary ZFS services for auto-mounting on boot.
  4. Creates the target mount point /media/WD_BLACK.
  5. Imports the "WD_BLACK" pool (if not already imported).
  6. Configures the "WD_BLACK" pool:
     - Sets the mountpoint to /media/WD_BLACK.
     - Sets the cachefile to enable auto-import on boot.
  7. Attempts to mount all ZFS datasets.
  8. Verifies that "WD_BLACK" is mounted correctly.

This script must be run with root privileges.

Usage:
  sudo python3 setup_wd_black_zfs.py

Version: 1.0.0 (Simplified)
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
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
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
VERSION = "1.0.0"
TARGET_POOL_NAME = "WD_BLACK"
TARGET_MOUNT_POINT = f"/media/{TARGET_POOL_NAME}"
DEFAULT_CACHE_FILE = "/etc/zfs/zpool.cache"
DEFAULT_LOG_FILE = "/var/log/zfs_wd_black_setup.log"

# Command preferences – use 'nala' if available, otherwise apt.
APT_CMD = "nala" if shutil.which("nala") else "apt"

# ZFS services and packages
ZFS_SERVICES = [
    "zfs-import-cache.service",
    "zfs-mount.service",
    "zfs-import.target",
    "zfs.target",
]
# Keeping headers as they are often needed for DKMS
ZFS_PACKAGES = [
    "dpkg-dev",
    "linux-headers-generic",
    "linux-image-generic",
    "zfs-dkms",
    "zfsutils-linux",
]
REQUIRED_COMMANDS = [APT_CMD, "systemctl", "zpool", "zfs"]


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
    header_panel = Panel(
        Text.from_markup(content, justify="center"),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_1}]v{VERSION}[/]",
        title_align="right",
    )
    return header_panel


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


def setup_logging(log_file: str = DEFAULT_LOG_FILE, level: int = logging.INFO) -> None:
    """Configure file logging."""
    try:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
        # Use a FileHandler to control permissions
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )
        logging.getLogger().addHandler(file_handler)
        logging.getLogger().setLevel(level)
        # Set permissions after file creation
        os.chmod(log_file, 0o600)
        log_message(f"Logging configured to: {log_file}", "info")
    except Exception as e:
        console.print(
            f"[bold {NordColors.YELLOW}]⚠ WARNING: Logging setup failed: {e}[/]"
        )
        # Don't log this message itself to avoid loops if logging fails early
        logging.basicConfig(level=level)  # Fallback to basic config if file setup fails


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks on script exit."""
    log_message("Cleanup actions finished.", "info")


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
    except (ValueError, OSError) as e:
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
    """Execute a shell command with optional spinner and error handling."""
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
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)

        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            check=False,  # We handle check manually based on the flag
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            env=cmd_env,
        )

        stdout = result.stdout.strip() if result.stdout else None
        stderr = result.stderr.strip() if result.stderr else None

        if progress:
            progress.stop()

        if result.returncode != 0:
            err_msg = (
                stderr
                if stderr
                else f"Command returned non-zero exit status {result.returncode}"
            )
            final_error_message = error_message or f"Command failed: {cmd_str}"
            log_message(f"{final_error_message}: {err_msg}", "error")
            if check:
                # Raising an exception might be too aggressive for some steps,
                # returning False allows the caller to decide how to proceed.
                # For simplicity here, we log error and return False.
                pass
            return False, stdout, stderr
        else:
            logging.debug(f"Command successful: {cmd_str}")
            logging.debug(f"Stdout: {stdout}")
            return True, stdout, stderr

    except Exception as e:
        if progress:
            progress.stop()
        final_error_message = error_message or f"Exception running command: {cmd_str}"
        log_message(f"{final_error_message}: {e}", "error")
        if check:
            raise  # Re-raise if check=True for critical failures
        return False, None, str(e)


# ----------------------------------------------------------------
# System Check and Package Management
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    """Verify the script is running as root."""
    if os.geteuid() != 0:
        log_message("This script must be run as root (using sudo).", "error")
        return False
    log_message("Root privileges verified.", "info")
    return True


def check_dependencies() -> bool:
    """Check if required system commands are available."""
    log_message("Checking required command dependencies...", "info")
    missing = [cmd for cmd in REQUIRED_COMMANDS if not shutil.which(cmd)]
    if missing:
        log_message(f"Missing required commands: {', '.join(missing)}.", "error")
        log_message(
            f"Please install them (e.g., apt install {' '.join(missing)}) and try again.",
            "error",
        )
        return False
    log_message("All required commands are present.", "success")
    return True


def install_packages(packages: List[str]) -> bool:
    """Install required ZFS packages."""
    if not packages:
        return True
    package_str = " ".join(packages)
    log_message(f"Ensuring ZFS packages are installed: {package_str}", "info")

    # Check which packages are already installed
    try:
        result = subprocess.run(
            ["dpkg", "-s"] + packages,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        installed_packages = set()
        if result.stdout:
            for line in result.stdout.split("\n\n"):
                if "Package: " in line and "Status: install ok installed" in line:
                    pkg_name = line.split("Package: ")[1].split("\n")[0]
                    installed_packages.add(pkg_name)
        packages_to_install = [pkg for pkg in packages if pkg not in installed_packages]
    except FileNotFoundError:
        # dpkg not found - check_dependencies should have caught this, but handle anyway
        log_message(
            "dpkg command not found. Cannot check installed packages.", "warning"
        )
        packages_to_install = packages  # Assume none are installed

    if not packages_to_install:
        log_message("All required ZFS packages are already installed.", "success")
        return True

    log_message(f"Packages to install: {', '.join(packages_to_install)}", "info")

    # Update package lists first
    success, _, _ = run_command(
        f"{APT_CMD} update -qq",
        error_message="Failed to update package lists",
        spinner_text="Updating package lists...",
        check=False,  # Allow continuing even if update fails sometimes
    )
    if not success:
        log_message(
            "Package list update failed. Attempting installation anyway...", "warning"
        )

    # Install missing packages
    install_cmd = f"{APT_CMD} install -y {' '.join(packages_to_install)}"
    success, _, _ = run_command(
        install_cmd,
        error_message="Failed to install ZFS packages",
        spinner_text=f"Installing {', '.join(packages_to_install)}...",
        check=True,  # Installation is critical
    )

    if success:
        log_message("ZFS packages installed successfully.", "success")
        return True
    else:
        log_message("Failed to install required ZFS packages.", "error")
        return False


def enable_zfs_services() -> bool:
    """Enable ZFS services for boot."""
    log_message("Enabling ZFS services for auto-start...", "info")
    all_success = True
    for service in ZFS_SERVICES:
        success, _, _ = run_command(
            f"systemctl enable {service}",
            error_message=f"Failed to enable {service}",
            check=False,  # Log error but continue trying others
            spinner_text=f"Enabling {service}",
        )
        if success:
            log_message(f"Enabled service: {service}", "info")
        else:
            all_success = False  # Mark overall failure if any service fails
            log_message(
                f"Failed to enable service: {service}", "warning"
            )  # Log as warning, not fatal error yet

    if all_success:
        log_message("All necessary ZFS services enabled successfully.", "success")
    else:
        log_message(
            "Some ZFS services could not be enabled. Auto-import/mount might fail.",
            "warning",
        )
    return all_success  # Return status based on whether all services enabled


def create_mount_point(mount_point: str) -> bool:
    """Create the directory for the ZFS mount point."""
    log_message(f"Ensuring mount point directory exists: {mount_point}", "info")
    try:
        path = Path(mount_point)
        path.mkdir(parents=True, exist_ok=True)
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
    success, _, _ = run_command(
        f"zpool list -H -o name {pool_name}",
        error_message=f"Error checking import status for pool '{pool_name}'",  # Error message if command fails
        check=False,  # Don't raise exception if pool doesn't exist
        capture_output=True,  # We need to know if it ran successfully, even if output is empty
    )
    # Success means the command ran and found the pool (or didn't error looking for it)
    # and the return code was 0. If the pool doesn't exist, zpool list returns non-zero.
    return success


def import_zfs_pool(pool_name: str) -> bool:
    """Import the specified ZFS pool."""
    log_message(f"Checking import status for pool '{pool_name}'...", "info")
    if is_pool_imported(pool_name):
        log_message(f"Pool '{pool_name}' is already imported.", "success")
        return True

    log_message(f"Attempting to import ZFS pool '{pool_name}'...", "info")
    # Use -f (force) as it's often needed if disks were moved or uncleanly exported
    # Use -c to specify the standard cache file location during import
    # Use -d /dev/disk/by-id if available for more robust imports (optional, but good practice)
    import_dirs = ""
    if os.path.exists("/dev/disk/by-id"):
        import_dirs = "-d /dev/disk/by-id"

    success, _, stderr = run_command(
        f"zpool import -f -c {DEFAULT_CACHE_FILE} {import_dirs} {pool_name}",
        error_message=f"Failed to import pool '{pool_name}'",
        check=False,  # We handle the failure message below
        spinner_text=f"Importing {pool_name}",
    )

    if success:
        log_message(f"Successfully imported pool '{pool_name}'.", "success")
        # Wait a brief moment for the system to recognize the import fully
        time.sleep(2)
        return True
    else:
        # Check if the pool is available to import at all
        import_output, _, _ = run_command(
            "zpool import", check=False, capture_output=True
        )
        if import_output and f"pool: {pool_name}" in import_output:
            log_message(
                f"Pool '{pool_name}' is available but import failed. Error: {stderr}",
                "error",
            )
        else:
            log_message(
                f"Pool '{pool_name}' could not be found or imported. Ensure disks are connected and pool exists.",
                "error",
            )
        return False


def configure_zfs_pool_properties(
    pool_name: str, mount_point: str, cache_file: str
) -> bool:
    """Set mountpoint and cachefile properties for the ZFS pool."""
    log_message(f"Configuring properties for pool '{pool_name}'...", "info")
    all_success = True

    # 1. Set mountpoint
    log_message(f"Setting mountpoint to '{mount_point}'...", "info")
    success, _, stderr = run_command(
        f"zfs set mountpoint={mount_point} {pool_name}",
        error_message=f"Failed to set mountpoint for '{pool_name}'",
        check=False,  # Log error but continue
        spinner_text="Setting mountpoint",
    )
    if not success:
        log_message(
            f"Failed to set mountpoint for '{pool_name}'. Mount might be incorrect.",
            "warning",
        )
        all_success = False
    else:
        log_message("Mountpoint set successfully.", "success")

    # 2. Set cachefile (essential for auto-import via service)
    log_message(f"Setting cachefile to '{cache_file}'...", "info")
    cache_dir = os.path.dirname(cache_file)
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            log_message(f"Created directory for cachefile: {cache_dir}", "info")
        except OSError as e:
            log_message(
                f"Failed to create directory '{cache_dir}' for cachefile: {e}", "error"
            )
            # This is critical, so mark failure and maybe return early
            return False

    success, _, stderr = run_command(
        f"zpool set cachefile={cache_file} {pool_name}",
        error_message=f"Failed to set cachefile for '{pool_name}'",
        check=False,  # Log error but consider it potentially critical
        spinner_text="Setting cachefile",
    )
    if not success:
        log_message(
            f"Failed to set cachefile for '{pool_name}'. Auto-import on boot may fail!",
            "error",
        )
        all_success = False  # This is important, mark as overall failure
    else:
        log_message("Cachefile set successfully.", "success")

    if not all_success:
        log_message("Configuration encountered issues.", "warning")
    else:
        log_message(f"Pool '{pool_name}' configured successfully.", "success")

    return all_success


def mount_zfs_datasets() -> bool:
    """Mount all available ZFS datasets."""
    log_message("Attempting to mount all ZFS datasets ('zfs mount -a')...", "info")
    success, stdout, stderr = run_command(
        "zfs mount -a",
        error_message="Command 'zfs mount -a' failed",
        check=False,  # Don't stop script, but report issues
        spinner_text="Mounting datasets",
    )
    if success:
        log_message("Command 'zfs mount -a' completed successfully.", "success")
        # Even if the command succeeds, check stderr for potential mount issues
        if stderr:
            log_message(f"Mounting process reported issues: {stderr}", "warning")
            # Consider returning False if stderr indicates problems, but for now, just warn
        return True
    else:
        log_message(
            f"Mounting datasets failed. Check ZFS status. Error: {stderr}", "error"
        )
        return False


def verify_mount(pool_name: str, expected_mount_point: str) -> bool:
    """Verify that the target pool is mounted at the expected location."""
    log_message(f"Verifying mount point for '{pool_name}'...", "info")
    success, stdout, stderr = run_command(
        f"zfs get -H -o value mountpoint {pool_name}",
        error_message=f"Failed to get mountpoint property for {pool_name}",
        check=False,
        spinner_text="Checking mountpoint property",
    )

    if not success or not stdout:
        log_message(
            f"Could not retrieve mountpoint property for '{pool_name}'.", "error"
        )
        return False

    actual_mount_point = stdout.strip()

    if actual_mount_point == expected_mount_point:
        log_message(
            f"ZFS property 'mountpoint' is correctly set to '{expected_mount_point}'.",
            "info",
        )

        # Now check if it's actually mounted using the 'mount' command or df
        try:
            # Using 'df' might be more reliable than parsing 'mount' output
            result = subprocess.run(
                ["df", "--output=target", expected_mount_point],
                text=True,
                capture_output=True,
            )
            if result.returncode == 0 and expected_mount_point in result.stdout:
                log_message(
                    f"Pool '{pool_name}' is actively mounted at '{expected_mount_point}'.",
                    "success",
                )
                return True
            else:
                # Property is correct, but not mounted? Try mounting again.
                log_message(
                    f"Mountpoint property is correct, but '{expected_mount_point}' is not listed as an active mount point. Attempting 'zfs mount {pool_name}'...",
                    "warning",
                )
                mount_success, _, _ = run_command(
                    f"zfs mount {pool_name}",
                    check=False,
                    spinner_text=f"Mounting {pool_name}",
                )
                if mount_success:
                    # Check again after explicit mount
                    result_after_mount = subprocess.run(
                        ["df", "--output=target", expected_mount_point],
                        text=True,
                        capture_output=True,
                    )
                    if (
                        result_after_mount.returncode == 0
                        and expected_mount_point in result_after_mount.stdout
                    ):
                        log_message(
                            f"Pool '{pool_name}' successfully mounted at '{expected_mount_point}' after explicit command.",
                            "success",
                        )
                        return True
                    else:
                        log_message(
                            f"Explicit mount command succeeded, but still not mounted at '{expected_mount_point}'. Check system logs.",
                            "error",
                        )
                        return False
                else:
                    log_message(f"Failed to explicitly mount '{pool_name}'.", "error")
                    return False

        except FileNotFoundError:
            log_message(
                "Could not find 'df' command to verify active mount.", "warning"
            )
            # Fallback or assume failure? For simplicity, log warning and maybe proceed based on ZFS property alone.
            log_message(
                "Verification based only on ZFS property: Mountpoint is set correctly.",
                "warning",
            )
            # Let's be strict: if we can't verify active mount, return False.
            return False
        except Exception as e:
            log_message(f"Error verifying active mount with 'df': {e}", "error")
            return False

    else:
        log_message(
            f"Mountpoint mismatch! Pool '{pool_name}' has mountpoint set to '{actual_mount_point}', but expected '{expected_mount_point}'.",
            "error",
        )
        return False


# ----------------------------------------------------------------
# Main Execution Logic
# ----------------------------------------------------------------
def main() -> None:
    """Main function to execute the ZFS setup for WD_BLACK."""
    setup_logging(DEFAULT_LOG_FILE, logging.INFO)  # Use INFO level for file logging
    start_time = datetime.datetime.now()
    logging.info("=" * 60)
    logging.info(
        f"WD_BLACK ZFS SETUP SCRIPT (v{VERSION}) STARTED AT {start_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info("=" * 60)

    clear_screen()
    console.print(create_header())
    log_message(f"Starting setup for ZFS pool '{TARGET_POOL_NAME}'...", "info")

    # 1. Check Root Privileges
    if not check_root_privileges():
        sys.exit(1)

    # 2. Check Dependencies
    if not check_dependencies():
        sys.exit(1)

    # 3. Install ZFS Packages
    if not install_packages(ZFS_PACKAGES):
        log_message(
            "Setup cannot continue due to package installation failure.", "error"
        )
        sys.exit(1)

    # 4. Enable ZFS Services (Important for auto-mount)
    # Allow script to continue even if some services fail, but log warning.
    enable_zfs_services()

    # 5. Create Mount Point Directory
    if not create_mount_point(TARGET_MOUNT_POINT):
        log_message("Setup cannot continue without the mount point directory.", "error")
        sys.exit(1)

    # 6. Import the Pool
    if not import_zfs_pool(TARGET_POOL_NAME):
        log_message(
            f"Failed to import the target pool '{TARGET_POOL_NAME}'. Please check connections and 'zpool import' manually.",
            "error",
        )
        sys.exit(1)

    # 7. Configure Pool Properties (Mountpoint & Cachefile)
    if not configure_zfs_pool_properties(
        TARGET_POOL_NAME, TARGET_MOUNT_POINT, DEFAULT_CACHE_FILE
    ):
        log_message(
            "Pool configuration failed. Auto-mount might not work correctly.", "error"
        )
        # Decide if this is fatal. Setting cachefile is crucial for boot mount.
        sys.exit(1)

    # 8. Mount All Datasets (includes the target pool if properties are set)
    if not mount_zfs_datasets():
        log_message(
            "Attempted to mount datasets, but issues were encountered.", "warning"
        )
        # Don't necessarily exit, verification step will confirm the target pool mount

    # 9. Verify Mount
    final_verification_passed = verify_mount(TARGET_POOL_NAME, TARGET_MOUNT_POINT)

    # 10. Final Summary
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    logging.info("=" * 60)
    logging.info(f"SCRIPT FINISHED AT {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"Total duration: {duration}")
    logging.info("=" * 60)

    if final_verification_passed:
        status_text = f"[bold {NordColors.GREEN}]SUCCESSFUL[/]"
        log_message(
            f"Setup for '{TARGET_POOL_NAME}' completed successfully. It should now auto-mount at '{TARGET_MOUNT_POINT}'.",
            "success",
        )
        exit_code = 0
    else:
        status_text = f"[bold {NordColors.RED}]FAILED[/]"
        log_message(
            f"Setup for '{TARGET_POOL_NAME}' failed or could not be fully verified. Please check the log file: {DEFAULT_LOG_FILE}",
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
