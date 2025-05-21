#!/usr/bin/env python3

import asyncio
import datetime
import filecmp
import gzip
import hashlib  # Added for hashing
import logging
import os
import pwd  # Added for UID/GID lookup
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field, asdict
from enum import Enum, auto  # Added for FileStatus
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, TypeVar

# --- Dependency Checks (from template) ---
# First, check if Nala is installed, and if not, install it
try:
    subprocess.check_call(
        ["which", "nala"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print("Nala is already installed.")
except subprocess.CalledProcessError:
    print("Nala not found. Installing Nala...")
    try:
        # Use apt-get for initial Nala install as apt might be more reliable initially
        subprocess.check_call(["apt-get", "update", "-y"])
        subprocess.check_call(["apt-get", "install", "nala", "-y"])
        print("Nala installed successfully.")
    except Exception as e:
        print(f"Error installing Nala: {e}")
        print("Continuing with apt instead of Nala.")
        # Define nala_cmd as apt if nala install fails
        nala_cmd = "apt"

# Define nala_cmd based on successful check/install
try:
    subprocess.check_call(
        ["which", "nala"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    nala_cmd = "nala"
except subprocess.CalledProcessError:
    nala_cmd = "apt"


try:
    import rich.console
    import rich.logging
    import rich.table  # Added for potential summary table
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.panel import Panel  # Keep Panel for potential summary
    from rich.text import Text  # Keep Text for potential summary
except ImportError:
    print("Required library 'rich' not found. Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print("Please install the required packages manually: pip install rich")
        sys.exit(1)

# --- Constants and Globals (from template) ---
console = Console()
OPERATION_TIMEOUT = 300  # default timeout in seconds
APP_NAME = "Ubuntu Script Deployer"  # Modified App Name
VERSION = "1.0.0"  # Modified Version

# --- Status Tracking (from template, adjusted) ---
SETUP_STATUS = {
    "preflight": {"status": "pending", "message": ""},
    "deploy_scripts": {"status": "pending", "message": ""},  # Focus of this script
    "final": {"status": "pending", "message": ""},
}

T = TypeVar("T")


# --- File Deployment Specific Enums and Dataclasses ---
class FileStatus(Enum):
    """Enum representing the possible status of a file during deployment."""

    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass
class FileInfo:
    """Information about a deployed file."""

    relative_path: str  # Renamed from filename for clarity
    status: FileStatus
    permission_changed: bool = False
    source_path: Path = field(default_factory=Path)
    dest_path: Path = field(default_factory=Path)
    error_message: str = ""


@dataclass
class DeploymentResult:
    """Results of a deployment operation."""

    new_files: int = 0
    updated_files: int = 0
    unchanged_files: int = 0
    failed_files: int = 0
    permission_changes: int = 0
    files: List[FileInfo] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def total_files(self) -> int:
        return (
            self.new_files
            + self.updated_files
            + self.unchanged_files
            + self.failed_files
        )

    @property
    def elapsed_time(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    def complete(self) -> None:
        self.end_time = time.time()

    def add_file(self, file_info: FileInfo) -> None:
        self.files.append(file_info)
        if file_info.status == FileStatus.NEW:
            self.new_files += 1
        elif file_info.status == FileStatus.UPDATED:
            self.updated_files += 1
        elif file_info.status == FileStatus.UNCHANGED:
            self.unchanged_files += 1
        elif file_info.status == FileStatus.FAILED:
            self.failed_files += 1
        if file_info.permission_changed:
            self.permission_changes += 1


# --- Configuration Dataclass (from template, adapted) ---
@dataclass
class Config:
    LOG_FILE: Path = field(
        default_factory=lambda: Path("/var/log/ubuntu_script_deployer.log")
    )  # Modified Log File Name
    USERNAME: str = (
        "sawyer"  # !! IMPORTANT: Still hardcoded, consider parameterizing !!
    )
    USER_HOME: Path = field(default_factory=lambda: Path(f"/home/{Config.USERNAME}"))

    # --- Script Deployment Specific Config ---
    # Updated Source Dir Logic: Prioritize Ubuntu, fallback to Debian/Fedora if needed.
    # This logic is now handled within the deploy phase itself.
    # SOURCE_DIR will be determined dynamically based on availability.
    DEST_DIR: Path = field(default_factory=lambda: Config.USER_HOME / "bin")
    OWNER_UID: Optional[int] = None
    OWNER_GID: Optional[int] = None
    FILE_PERMISSIONS: int = 0o755  # Scripts should typically be executable
    DIR_PERMISSIONS: int = 0o755  # Dirs usually match file executable status here

    # --- Performance Settings (optional, can be added if needed) ---
    # MAX_WORKERS: int = 4

    # --- Other Template Fields (kept for structure) ---
    PACKAGES: List[str] = field(
        default_factory=list
    )  # Not used in this specific script
    SSH_CONFIG: Dict[str, str] = field(default_factory=dict)  # Not used
    FIREWALL_PORTS: List[str] = field(default_factory=list)  # Not used

    def __post_init__(self) -> None:
        """Initialize derived settings."""
        # Resolve user ID and group ID for the target user
        try:
            pwd_entry = pwd.getpwnam(self.USERNAME)
            self.OWNER_UID = pwd_entry.pw_uid
            self.OWNER_GID = pwd_entry.pw_gid
            # Update USER_HOME based on potentially dynamic USERNAME if parameterization is added
            self.USER_HOME = Path(pwd_entry.pw_dir)
            # Update DEST_DIR based on actual home directory
            self.DEST_DIR = self.USER_HOME / "bin"
        except KeyError:
            # Log this issue later in the preflight check
            pass
        # Update LOG_FILE parent based on potential USER_HOME change
        # Decide where logs should *really* go. /var/log is standard for system services.
        # If this is a user tool, maybe ~/.local/share/ubuntu_script_deployer/logs ?
        # For now, stick to /var/log, requires root.
        pass  # Keep /var/log for now

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Logger Setup (from template) ---
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Try setting permissions early, requires root for /var/log
        if os.geteuid() == 0:
            os.chmod(log_file.parent, 0o755)  # Ensure parent is accessible if created
    except PermissionError:
        # Handle case where log dir creation fails due to permissions
        alt_log_dir = Path.home() / ".local/share/ubuntu_script_deployer/logs"
        alt_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = alt_log_dir / log_file.name
        print(f"Warning: No permission for {log_file.parent}. Logging to {alt_log_dir}")
    except Exception as e:
        print(f"Warning: Could not create/access log directory {log_file.parent}: {e}")
        # Fallback further? Maybe log to console only? For now, let it fail if alt dir fails too.

    logger = logging.getLogger("ubuntu_script_deployer")  # Modified logger name
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to prevent duplicate logs if re-initialized
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Console Handler (INFO level)
    console_handler = RichHandler(
        console=console, rich_tracebacks=True, show_path=False
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File Handler (DEBUG level)
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # Set log file permissions (best effort)
        try:
            os.chmod(str(log_file), 0o600)  # Read/Write for owner only
        except Exception as e:
            logger.warning(f"Could not set permissions on log file {log_file}: {e}")
    except Exception as e:
        logger.error(f"Failed to set up file logging to {log_file}: {e}")
        print(
            f"Error: Failed to initialize file logging to {log_file}. Check permissions."
        )

    return logger


# --- Async Utilities (from template) ---
async def run_command_async(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = False,
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,  # Added cwd parameter
) -> subprocess.CompletedProcess:
    logger = logging.getLogger("ubuntu_script_deployer")
    logger.debug(f"Running command: {' '.join(cmd)} (cwd: {cwd or os.getcwd()})")
    stdout_pipe = asyncio.subprocess.PIPE if capture_output else None
    stderr_pipe = asyncio.subprocess.PIPE if capture_output else None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            cwd=str(cwd) if cwd else None,  # Pass cwd to subprocess
        )
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        stdout_res = (
            stdout_data.decode("utf-8", errors="ignore")
            if text and stdout_data is not None
            else stdout_data
        )
        stderr_res = (
            stderr_data.decode("utf-8", errors="ignore")
            if text and stderr_data is not None
            else stderr_data
        )

        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_res if capture_output else None,
            stderr=stderr_res if capture_output else None,
        )
        if check and proc.returncode != 0:
            # Log stderr if available
            err_msg = (
                f"Command '{' '.join(cmd)}' failed with return code {proc.returncode}."
            )
            if stderr_res:
                err_msg += f"\nStderr:\n{stderr_res.strip()}"
            logger.error(err_msg)
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout_res, stderr=stderr_res
            )
        # Log successful command output at DEBUG level if captured
        if capture_output and stdout_res:
            logger.debug(f"Command output for '{' '.join(cmd)}':\n{stdout_res.strip()}")

        return result
    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        # Attempt to kill the process
        try:
            proc.kill()
            await proc.wait()  # Wait for kill to complete
        except ProcessLookupError:
            pass  # Process already finished
        except Exception as kill_e:
            logger.warning(
                f"Failed to kill timed-out process for command '{' '.join(cmd)}': {kill_e}"
            )
        raise TimeoutError(
            f"Command '{' '.join(cmd)}' timed out after {timeout} seconds."
        )
    except FileNotFoundError:
        logger.error(
            f"Command not found: {cmd[0]}. Ensure it is installed and in PATH."
        )
        raise
    except Exception as e:
        logger.error(f"Error running command {' '.join(cmd)}: {e}")
        raise  # Re-raise the exception after logging


async def run_with_progress_async(
    description: str,
    func: Callable[..., Any],
    *args: Any,
    task_name: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Runs a function (sync or async) with logging and status updates."""
    logger = logging.getLogger("ubuntu_script_deployer")
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description}...",
        }
    logger.info(f"Starting: {description}...")
    start = time.monotonic()  # Use monotonic clock for duration
    try:
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        elapsed = time.monotonic() - start
        success_msg = f"✓ {description} completed in {elapsed:.2f}s"
        logger.info(success_msg)
        if task_name:
            SETUP_STATUS[task_name] = {"status": "success", "message": success_msg}
        return result
    except Exception as e:
        elapsed = time.monotonic() - start
        # Log traceback for unexpected errors
        # logger.exception(f"Error during '{description}'", exc_info=e) # Provides full traceback to log file
        fail_msg = f"✗ {description} failed after {elapsed:.2f}s: {e}"
        logger.error(fail_msg)
        if task_name:
            SETUP_STATUS[task_name] = {"status": "failed", "message": fail_msg}
        raise  # Re-raise the exception so the caller knows it failed


# --- File Hashing and Listing (adapted from Fedora script) ---
async def get_file_hash_async(file_path: Path) -> str:
    """Calculates the MD5 hash of a file asynchronously."""
    loop = asyncio.get_running_loop()
    logger = logging.getLogger("ubuntu_script_deployer")
    logger.debug(f"Calculating MD5 hash for: {file_path}")
    try:
        # Use run_in_executor for the blocking file read operation
        file_hash = await loop.run_in_executor(None, _calculate_md5_sync, file_path)
        logger.debug(f"MD5 hash for {file_path}: {file_hash}")
        return file_hash
    except FileNotFoundError:
        logger.error(f"File not found while hashing: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        raise  # Re-raise to indicate failure


def _calculate_md5_sync(file_path: Path) -> str:
    """Synchronous helper for MD5 calculation."""
    md5_hash = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except OSError as e:
        # Log specific OS error
        logging.getLogger("ubuntu_script_deployer").error(
            f"OS error reading {file_path} for hashing: {e}"
        )
        raise
    except Exception as e:
        # Catch any other unexpected errors during hashing
        logging.getLogger("ubuntu_script_deployer").error(
            f"Unexpected error hashing {file_path}: {e}"
        )
        raise


async def list_all_files_async(directory: Path) -> List[Path]:
    """Lists all files relative to the base directory asynchronously."""
    loop = asyncio.get_running_loop()
    logger = logging.getLogger("ubuntu_script_deployer")
    logger.debug(f"Listing all files in directory: {directory}")
    if not directory.is_dir():
        logger.error(
            f"Source directory for listing files does not exist or is not a directory: {directory}"
        )
        return []
    try:
        # Use run_in_executor for the potentially blocking os.walk
        relative_files = await loop.run_in_executor(
            None, _walk_directory_sync, directory
        )
        logger.debug(f"Found {len(relative_files)} files in {directory}")
        return relative_files
    except Exception as e:
        logger.error(f"Failed to list files in {directory}: {e}")
        raise  # Re-raise to indicate failure


def _walk_directory_sync(directory: Path) -> List[Path]:
    """Synchronous helper for directory walking, returns relative Path objects."""
    relative_file_paths = []
    try:
        for root, _, files in os.walk(directory):
            root_path = Path(root)
            for f in files:
                full_path = root_path / f
                # Calculate relative path from the base directory
                try:
                    rel_path = full_path.relative_to(directory)
                    relative_file_paths.append(rel_path)
                except ValueError:
                    # This might happen if symlinks point outside the directory, log it
                    logging.getLogger("ubuntu_script_deployer").warning(
                        f"Could not determine relative path for {full_path} within {directory}. Skipping."
                    )

        # Sort for consistent processing order
        relative_file_paths.sort()
        return relative_file_paths
    except Exception as e:
        logging.getLogger("ubuntu_script_deployer").error(
            f"Error walking directory {directory}: {e}"
        )
        raise


# --- Signal Handling (from template) ---
async def signal_handler_async(signum: int, frame: Any) -> None:
    """Handles termination signals gracefully."""
    logger = logging.getLogger("ubuntu_script_deployer")
    try:
        sig_name = signal.Signals(signum).name
        logger.warning(f"Script interrupted by {sig_name}. Initiating cleanup...")
    except (ValueError, AttributeError):
        logger.warning(f"Script interrupted by signal {signum}. Initiating cleanup...")

    # Add any specific cleanup tasks here if needed (e.g., removing temp files)
    # Example:
    # if 'deployer_instance' in globals():
    #     await globals()['deployer_instance'].cleanup_temp_files_async()

    # Cancel running asyncio tasks
    try:
        loop = asyncio.get_running_loop()
        tasks = [
            task
            for task in asyncio.all_tasks(loop)
            if task is not asyncio.current_task()
        ]
        if tasks:
            logger.debug(f"Cancelling {len(tasks)} outstanding tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug("Tasks cancelled.")
        # Important: Stop the loop to allow main() to exit cleanly in some scenarios
        loop.stop()
    except RuntimeError:
        logger.debug("No running event loop or loop already stopped.")
    except Exception as e:
        logger.error(f"Error during task cancellation/cleanup: {e}")

    # Exit with appropriate code
    exit_code = 128 + signum
    logger.info(f"Exiting with code {exit_code}.")
    sys.exit(exit_code)


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Sets up asynchronous signal handlers."""
    logger = logging.getLogger("ubuntu_script_deployer")
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                signum,
                lambda sig=signum: asyncio.create_task(signal_handler_async(sig, None)),
            )
            logger.debug(f"Signal handler set up for {signal.Signals(signum).name}")
        except (ValueError, AttributeError):
            logger.debug(f"Signal handler set up for signal {signum}")
        except Exception as e:
            logger.error(f"Failed to set signal handler for signal {signum}: {e}")


# --- Main Deployment Class ---
class UbuntuScriptDeployer:
    def __init__(self, config: Config = Config()):
        self.config = config
        # Initialize logger early
        self.logger = setup_logger(self.config.LOG_FILE)
        # Check config post-init results
        if self.config.OWNER_UID is None or self.config.OWNER_GID is None:
            self.logger.warning(
                f"Could not determine UID/GID for user '{self.config.USERNAME}'. "
                f"Ownership setting will be skipped. Ensure user exists."
            )
        self.start_time = time.monotonic()
        self.deployment_result = DeploymentResult()  # Initialize result tracker

    async def print_section_async(self, title: str) -> None:
        """Logs a formatted section header."""
        self.logger.info(f"--- {title} ---")

    async def check_root_async(self) -> None:
        """Checks for root privileges."""
        if os.geteuid() != 0:
            self.logger.error(
                "Script must be run as root to set correct ownership "
                f"for target user '{self.config.USERNAME}' in '{self.config.DEST_DIR}' "
                f"and log to '{self.config.LOG_FILE.parent}'."
            )
            # Check if we are trying to deploy to the *current* user's dir without root
            try:
                current_user = pwd.getpwuid(os.getuid()).pw_name
                if (
                    current_user == self.config.USERNAME
                    and self.config.DEST_DIR.is_relative_to(Path.home())
                ):
                    self.logger.info(
                        "Running as target user and deploying to home directory. Root not strictly required but recommended for system-wide logging."
                    )
                    # Allow continuation if running as the target user for their own dir
                    return
            except Exception:
                pass  # Ignore errors in this non-critical check

            sys.exit(1)  # Exit if not root and not the special case above
        self.logger.info("Root privileges confirmed.")

    async def phase_preflight(self) -> bool:
        """Performs pre-flight checks."""
        await self.print_section_async("Pre-flight Checks")
        try:
            await run_with_progress_async(
                "Checking for root privileges",
                self.check_root_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Verifying target user existence",
                self.check_user_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Verifying destination directory",
                self._verify_destination_async,
                task_name="preflight",
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            SETUP_STATUS["preflight"] = {"status": "failed", "message": f"Failed: {e}"}
            return False

    async def check_user_async(self) -> None:
        """Verify the target user exists."""
        if self.config.OWNER_UID is None:
            raise ValueError(
                f"Target user '{self.config.USERNAME}' not found on the system."
            )
        self.logger.info(
            f"Target user '{self.config.USERNAME}' (UID: {self.config.OWNER_UID}) found."
        )

    async def _determine_source_dir_async(self) -> Optional[Path]:
        """Determine the correct source directory based on availability."""
        base_github_dir = self.config.USER_HOME / "github" / "bash" / "linux"
        potential_sources = [
            base_github_dir / "ubuntu" / "_scripts",
            base_github_dir / "debian" / "_scripts",
            base_github_dir / "fedora" / "_scripts",  # Original fallback
        ]

        for source_dir in potential_sources:
            # Check existence asynchronously (though disk checks are fast, consistency)
            loop = asyncio.get_running_loop()
            exists = await loop.run_in_executor(None, source_dir.is_dir)
            if exists:
                self.logger.info(f"Using source directory: {source_dir}")
                return source_dir

        self.logger.error(
            f"No suitable source script directory found under {base_github_dir}. Checked: {potential_sources}"
        )
        return None

    async def _verify_destination_async(self) -> None:
        """Verify destination directory exists and has correct base permissions."""
        dest = self.config.DEST_DIR
        self.logger.info(f"Verifying destination directory: {dest}")
        loop = asyncio.get_running_loop()
        try:
            # Check if it exists
            exists = await loop.run_in_executor(None, dest.exists)
            if not exists:
                self.logger.info(
                    f"Destination directory does not exist. Creating: {dest}"
                )
                await loop.run_in_executor(
                    None, lambda: dest.mkdir(parents=True, exist_ok=True)
                )
                # Set initial owner/group/permissions on the newly created directory
                await self._set_owner_group_perms_async(dest, is_directory=True)
            elif not await loop.run_in_executor(None, dest.is_dir):
                raise FileExistsError(
                    f"Destination path exists but is not a directory: {dest}"
                )
            else:
                # If it exists, ensure base permissions are okay
                self.logger.debug(
                    f"Destination directory exists. Verifying permissions..."
                )
                await self._set_owner_group_perms_async(dest, is_directory=True)

            self.logger.info(f"Destination directory verified: {dest}")
        except PermissionError as e:
            self.logger.error(
                f"Permission error verifying/creating destination {dest}: {e}. Ensure script has necessary rights."
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Failed to verify/create destination directory {dest}: {e}"
            )
            raise

    async def _set_owner_group_perms_async(
        self, path: Path, is_directory: bool
    ) -> bool:
        """Sets owner, group, and permissions asynchronously. Returns True if changed."""
        logger = self.logger
        config = self.config
        loop = asyncio.get_running_loop()
        path_changed = False

        if config.OWNER_UID is None or config.OWNER_GID is None:
            logger.warning(
                f"Skipping owner/group set for {path} (UID/GID unknown for {config.USERNAME})"
            )
            return False  # No change attempted

        target_perms = (
            config.DIR_PERMISSIONS if is_directory else config.FILE_PERMISSIONS
        )

        try:
            # Get current stats
            current_stat = await loop.run_in_executor(None, path.stat)

            # --- 1. Set Owner/Group ---
            if (
                current_stat.st_uid != config.OWNER_UID
                or current_stat.st_gid != config.OWNER_GID
            ):
                logger.debug(
                    f"Changing ownership of {path} to {config.OWNER_UID}:{config.OWNER_GID}"
                )
                try:
                    await loop.run_in_executor(
                        None, lambda: os.chown(path, config.OWNER_UID, config.OWNER_GID)
                    )
                    path_changed = True
                    logger.debug(f"Successfully changed ownership for {path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to set ownership on {path} to {config.OWNER_UID}:{config.OWNER_GID}: {e}"
                    )
                    # Don't raise here, maybe permissions can still be set

            # --- 2. Set Permissions ---
            current_perms = current_stat.st_mode & 0o777  # Extract permission bits
            if current_perms != target_perms:
                logger.debug(
                    f"Changing permissions of {path} from {oct(current_perms)} to {oct(target_perms)}"
                )
                try:
                    await loop.run_in_executor(None, lambda: path.chmod(target_perms))
                    path_changed = True
                    logger.debug(f"Successfully changed permissions for {path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to set permissions on {path} to {oct(target_perms)}: {e}"
                    )
                    # Don't raise, log the warning

            return path_changed  # Return True if owner OR perms changed

        except FileNotFoundError:
            logger.error(f"Cannot set permissions: File not found at {path}")
            raise  # This shouldn't happen if called after creation/copy
        except Exception as e:
            logger.error(
                f"Unexpected error setting permissions/ownership for {path}: {e}"
            )
            # Don't raise, but log the error
            return False  # Indicate failure or no change

    async def _process_single_file_async(
        self, relative_path: Path, source_base: Path
    ) -> FileInfo:
        """Processes a single file: copy, hash check, permissions."""
        source_path = source_base / relative_path
        dest_path = self.config.DEST_DIR / relative_path
        file_info = FileInfo(
            relative_path=str(relative_path),
            source_path=source_path,
            dest_path=dest_path,
            status=FileStatus.FAILED,
        )  # Default to failed
        perm_changed = False
        loop = asyncio.get_running_loop()
        logger = self.logger

        logger.debug(f"Processing file: {relative_path}")

        try:
            # Ensure parent directory exists in destination
            dest_parent = dest_path.parent
            if not await loop.run_in_executor(None, dest_parent.is_dir):
                logger.debug(f"Creating parent directory: {dest_parent}")
                await loop.run_in_executor(
                    None, lambda: dest_parent.mkdir(parents=True, exist_ok=True)
                )
                # Set permissions on newly created parent directory
                await self._set_owner_group_perms_async(dest_parent, is_directory=True)

            # Determine file status (New, Updated, Unchanged)
            dest_exists = await loop.run_in_executor(None, dest_path.is_file)

            if not dest_exists:
                file_info.status = FileStatus.NEW
                logger.info(f"Deploying NEW file: {relative_path}")
            else:
                # Compare hashes
                try:
                    source_hash = await get_file_hash_async(source_path)
                    dest_hash = await get_file_hash_async(dest_path)
                    if source_hash != dest_hash:
                        file_info.status = FileStatus.UPDATED
                        logger.info(
                            f"Deploying UPDATED file: {relative_path} (hash mismatch)"
                        )
                    else:
                        file_info.status = FileStatus.UNCHANGED
                        logger.debug(f"File UNCHANGED: {relative_path} (hash match)")
                except Exception as hash_e:
                    # If hashing fails (e.g., permission error on dest), assume update needed
                    logger.warning(
                        f"Hash comparison failed for {relative_path}: {hash_e}. Assuming update required."
                    )
                    file_info.status = FileStatus.UPDATED

            # Perform copy if New or Updated
            if file_info.status in (FileStatus.NEW, FileStatus.UPDATED):
                try:
                    await loop.run_in_executor(
                        None, lambda: shutil.copy2(source_path, dest_path)
                    )
                    logger.debug(f"Copied {source_path} to {dest_path}")
                except Exception as copy_e:
                    logger.error(f"Failed to copy {relative_path}: {copy_e}")
                    file_info.status = FileStatus.FAILED
                    file_info.error_message = str(copy_e)
                    return file_info  # Don't try to set permissions if copy failed

            # Set/Verify Permissions and Ownership (runs for New, Updated, and Unchanged)
            try:
                # Pass False for is_directory
                perm_changed = await self._set_owner_group_perms_async(
                    dest_path, is_directory=False
                )
                file_info.permission_changed = perm_changed
                if file_info.status == FileStatus.UNCHANGED and perm_changed:
                    logger.info(
                        f"Permissions UPDATED for unchanged file: {relative_path}"
                    )

            except Exception as perm_e:
                # Log error but don't necessarily mark file as failed if copy succeeded
                logger.warning(
                    f"Failed to set final permissions for {relative_path}: {perm_e}"
                )
                file_info.error_message = (
                    file_info.error_message + f"; Perms failed: {perm_e}"
                )
                # Optionally downgrade status if perms fail? Depends on strictness.
                # file_info.status = FileStatus.FAILED

        except Exception as e:
            logger.error(
                f"Critical error processing file {relative_path}: {e}", exc_info=True
            )
            file_info.status = FileStatus.FAILED
            file_info.error_message = str(e)

        return file_info

    async def phase_deploy_scripts(self) -> bool:
        """Copies scripts from source to destination, sets permissions."""
        await self.print_section_async("Script Deployment")

        # --- 1. Determine Source Directory ---
        source_dir = await self._determine_source_dir_async()
        if not source_dir:
            SETUP_STATUS["deploy_scripts"] = {
                "status": "failed",
                "message": "Source directory not found",
            }
            return False  # Cannot proceed without source

        # --- 2. List Source Files ---
        try:
            relative_files_to_deploy = await run_with_progress_async(
                f"Listing files in {source_dir}",
                list_all_files_async,
                source_dir,
                task_name="deploy_scripts",  # Update status during listing
            )
        except Exception as e:
            self.logger.error(f"Failed to list source files: {e}")
            return False  # Cannot proceed

        if not relative_files_to_deploy:
            self.logger.info(
                "No script files found in source directory. Nothing to deploy."
            )
            SETUP_STATUS["deploy_scripts"] = {
                "status": "success",
                "message": "No scripts found to deploy.",
            }
            return True

        # --- 3. Process Files Concurrently ---
        self.logger.info(
            f"Found {len(relative_files_to_deploy)} files. Starting deployment..."
        )
        self.deployment_result = DeploymentResult()  # Reset results for this run
        tasks = []
        # Limit concurrency? Use asyncio.Semaphore if needed, e.g., semaphore = asyncio.Semaphore(10)
        for rel_path in relative_files_to_deploy:
            # task = asyncio.create_task(self._process_single_file_async(rel_path, source_dir))
            # tasks.append(task)
            # Example with semaphore:
            # async def run_with_sem(rp, sd):
            #      async with semaphore:
            #           return await self._process_single_file_async(rp, sd)
            # tasks.append(asyncio.create_task(run_with_sem(rel_path, source_dir)))

            # Simpler sequential processing for debugging or fewer files:
            # file_result = await self._process_single_file_async(rel_path, source_dir)
            # self.deployment_result.add_file(file_result)

            # Concurrent processing:
            tasks.append(
                asyncio.create_task(
                    self._process_single_file_async(rel_path, source_dir)
                )
            )

        # Wait for all file processing tasks to complete
        try:
            file_results = await asyncio.gather(
                *tasks
            )  # Add timeout? e.g., asyncio.wait_for(asyncio.gather(*tasks), timeout=600)
        except asyncio.TimeoutError:
            self.logger.error("Deployment timed out while processing files.")
            SETUP_STATUS["deploy_scripts"] = {
                "status": "failed",
                "message": "Timeout during file processing.",
            }
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during file processing gather: {e}")
            SETUP_STATUS["deploy_scripts"] = {
                "status": "failed",
                "message": f"Error: {e}",
            }
            return False

        # --- 4. Collate Results ---
        for file_info in file_results:
            self.deployment_result.add_file(file_info)
        self.deployment_result.complete()

        # --- 5. Log Summary ---
        summary_msg = (
            f"Deployment finished in {self.deployment_result.elapsed_time:.2f}s. "
            f"Total: {self.deployment_result.total_files}, "
            f"New: {self.deployment_result.new_files}, "
            f"Updated: {self.deployment_result.updated_files}, "
            f"Unchanged: {self.deployment_result.unchanged_files}, "
            f"Failed: {self.deployment_result.failed_files}. "
            f"Permissions checked/set on ~{self.deployment_result.permission_changes} items."  # Approx due to dirs
        )
        if self.deployment_result.failed_files > 0:
            self.logger.error(summary_msg)
            SETUP_STATUS["deploy_scripts"] = {
                "status": "failed",
                "message": summary_msg,
            }
            # Log failed files details
            for f in self.deployment_result.files:
                if f.status == FileStatus.FAILED:
                    self.logger.warning(
                        f"  - Failed: {f.relative_path} (Error: {f.error_message})"
                    )
            return False
        else:
            self.logger.info(summary_msg)
            SETUP_STATUS["deploy_scripts"] = {
                "status": "success",
                "message": summary_msg,
            }
            return True

    async def phase_final_summary(self) -> bool:
        """Prints a final summary of the operation."""
        await self.print_section_async("Final Summary")
        elapsed = time.monotonic() - self.start_time
        hours, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        completion_time = f"{int(hours)}h {int(mins)}m {int(secs)}s"

        # Build summary using Rich Panel and Text for better formatting
        summary_text = Text()
        summary_text.append(
            f"Script Deployer completed in {completion_time}\n\n", style="bold"
        )

        # Overall status
        failed_phases = [
            k for k, v in SETUP_STATUS.items() if v.get("status") == "failed"
        ]
        if failed_phases:
            summary_text.append("Status: Failed\n", style="bold red")
            summary_text.append("Failed Phases:\n", style="red")
            for phase in failed_phases:
                summary_text.append(
                    f"  - {phase}: {SETUP_STATUS[phase].get('message', 'Unknown error')}\n",
                    style="red",
                )
        else:
            summary_text.append("Status: Success\n", style="bold green")

        # Deployment details (if deployment ran)
        if self.deployment_result.total_files > 0:
            res = self.deployment_result
            summary_text.append("\nDeployment Results:\n", style="bold")
            summary_text.append(
                f"  - Source: {getattr(self, '_last_source_dir', 'N/A')}\n"
            )  # Need to store source dir used
            summary_text.append(f"  - Destination: {self.config.DEST_DIR}\n")
            summary_text.append(f"  - Total Files Processed: {res.total_files}\n")
            summary_text.append(
                f"  - New: {res.new_files}\n",
                style="green" if res.new_files > 0 else "",
            )
            summary_text.append(
                f"  - Updated: {res.updated_files}\n",
                style="yellow" if res.updated_files > 0 else "",
            )
            summary_text.append(f"  - Unchanged: {res.unchanged_files}\n")
            if res.failed_files > 0:
                summary_text.append(
                    f"  - Failed: {res.failed_files}\n", style="bold red"
                )

        # Log the summary panel to console and file
        panel = Panel(
            summary_text, title="[bold]Deployment Report[/bold]", border_style="blue"
        )
        console.print(panel)  # Print directly to console for visibility
        self.logger.info(
            "Final Summary:\n" + summary_text.plain
        )  # Log plain text version

        return not bool(failed_phases)


# --- Main Execution Logic (from template) ---
async def main_async() -> None:
    deployer = None  # Initialize deployer to None
    try:
        # Instantiate the main class
        config = Config()
        deployer = UbuntuScriptDeployer(config)
        global deployer_instance  # Make it accessible to signal handler if needed
        deployer_instance = deployer

        deployer.logger.info(f"Starting {APP_NAME} v{VERSION}")

        # Execute phases
        if not await deployer.phase_preflight():
            sys.exit(1)

        # --- This is the core phase for this script ---
        await deployer.phase_deploy_scripts()
        # ---------------------------------------------

        # Final summary phase
        await deployer.phase_final_summary()

        # Check overall status
        failed_phases = [
            k for k, v in SETUP_STATUS.items() if v.get("status") == "failed"
        ]
        if failed_phases:
            deployer.logger.error("One or more phases failed. Check logs for details.")
            sys.exit(1)
        else:
            deployer.logger.info("All phases completed successfully.")

    except KeyboardInterrupt:
        # This is usually handled by the signal handler, but catch it here as a fallback
        print("\nOperation cancelled by user (KeyboardInterrupt).")
        if deployer:
            deployer.logger.warning("Operation cancelled by user (KeyboardInterrupt).")
            # Optionally call a specific cleanup method if needed
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        # Catchall for unexpected errors during execution
        console.print(
            f"\n[bold red]FATAL ERROR:[/bold red] An unexpected error occurred."
        )
        # Use rich traceback printing to console for immediate feedback
        console.print_exception(show_locals=True)
        if deployer:
            deployer.logger.critical(
                f"FATAL ERROR: {e}", exc_info=True
            )  # Log with traceback
        else:
            # If deployer failed to initialize, log to a basic logger or print
            logging.getLogger("ubuntu_script_deployer").critical(
                f"FATAL ERROR during initialization: {e}", exc_info=True
            )
        sys.exit(1)


def main() -> None:
    loop = None
    try:
        # Set up the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Set up signal handlers for graceful shutdown
        setup_signal_handlers(loop)

        # Run the main asynchronous function
        loop.run_until_complete(main_async())

    except Exception as e:
        # Catch errors during loop setup or final execution stages
        print(f"\nCritical error in main execution: {e}")
        # Print traceback if possible
        import traceback

        traceback.print_exc()
    finally:
        # Cleanup asyncio loop and tasks
        if loop:
            try:
                # Cancel all running tasks cleanly
                tasks = asyncio.all_tasks(loop)
                if tasks:
                    # Give tasks a moment to finish cancellation
                    # print("Cancelling pending tasks...")
                    for task in tasks:
                        task.cancel()
                    # Wait for tasks to finish cancelling
                    loop.run_until_complete(
                        asyncio.gather(*tasks, return_exceptions=True)
                    )

                # Shutdown async generators
                # print("Shutting down async generators...")
                loop.run_until_complete(loop.shutdown_asyncgens())

            except Exception as cleanup_err:
                print(f"Error during asyncio cleanup: {cleanup_err}")
            finally:
                if loop.is_running():
                    # print("Stopping event loop...")
                    loop.stop()  # Ensure loop stops if still running
                if not loop.is_closed():
                    # print("Closing event loop...")
                    loop.close()
                    # print("Event loop closed.")

        print(f"{APP_NAME} finished.")


if __name__ == "__main__":
    # Ensure the script is run with appropriate privileges early on
    # Note: The detailed check is inside phase_preflight, this is a basic guard
    # if os.geteuid() != 0:
    #      print("Error: This script needs to be run as root (or sudo) to manage permissions correctly.")
    #      sys.exit(1)

    main()
