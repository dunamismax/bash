# AI Prompt for Python Script Generation with Rich Integration

This enhanced prompt instructs you to generate Python scripts that are robust, visually engaging, and extremely user-friendly. Every generated script must include progress indicators and user feedback via the rich library. Use the unified backup script provided below as the foundation and exemplar.

---

## Enhanced Prompt Instructions

### Objective

Create Python scripts with a modern, consistent style that integrates the rich library for progress spinners and formatted output. The scripts must follow a standardized template that uses the Nord color palette for terminal feedback, detailed logging with log-level filtering, strict error handling, and graceful signal handling.

### Requirements

1. **Structure & Organization**
   - **Sections:** Divide the script into clear sections for configuration, logging, helper functions, main logic, and cleanup.
   - **Modularity:** Structure the code with functions dedicated to logging, error handling, and core functionality to encourage reuse and clarity.
   - **Docstrings & Comments:** Provide comprehensive docstrings for functions and classes. Add descriptive comments and section headers throughout the code.

2. **Styling & Formatting**
   - **PEP 8:** Follow PEP 8 guidelines for indentation, spacing, and naming conventions (e.g., snake_case for variables and functions, CamelCase for classes, UPPERCASE for constants).
   - **Nord Color Palette:** Utilize the Nord color palette (using 24-bit ANSI escape sequences) to deliver visually engaging output. Use different Nord colors for various log levels (DEBUG, INFO, WARN, ERROR, CRITICAL) and UI elements like section headers.

3. **Rich Library Integration**
   - **Progress Indicators:** All long-running tasks (backups, cleanup operations, etc.) must display progress spinners or progress bars using the rich library.
   - **Formatted Output:** Use rich’s styling features to format terminal output for user notifications, errors, and status reports.
   - **Consistency:** Ensure that every generated script uses rich consistently for both progress feedback and aesthetic output.

4. **Error Handling & Cleanup**
   - **Signal Handlers:** Implement signal handlers to manage interrupts and termination signals gracefully.
   - **Cleanup Tasks:** Use atexit or equivalent cleanup routines to guarantee that necessary cleanup operations are performed before the script exits.
   - **Exception Management:** Rigorously use try/except blocks for error handling, ensuring that errors are logged with sufficient context and that the script exits gracefully on failures.

### Confirmation

I confirm that the above template and style—featuring robust error handling, rich library progress indicators, comprehensive logging, and Nord-themed output—will serve as the standard for all future Python scripting assistance.

---

## Python Script Template

Use the following unified backup script as the foundation for your Python scripts. **Do not modify any part of this template.** It exemplifies the integration of the rich library for progress spinners and detailed, colorized output.

```python
#!/usr/bin/env python3
"""
Comprehensive Unified Backup Script
-----------------------------------
Description:
  A unified backup solution that performs three types of backups to Backblaze B2:
    1. System Backup - Backs up the entire system (/)
    2. VM Backup - Backs up libvirt virtual machine configurations and disk images
    3. Plex Backup - Backs up Plex Media Server configuration and application data

  Each backup is stored in a separate repository within the same B2 bucket.
  All repositories are named with the hostname prefix for organization.
  The script automatically initializes repositories as needed, forces unlocks before backup,
  and enforces retention policies.

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 3.2.1
"""

import atexit
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "005531878ffff660000000001"
B2_ACCOUNT_KEY = "K005oVgYPouP1DMQa5jhGfRBiX33Kns"
B2_BUCKET = "sawyer-backups"

HOSTNAME = socket.gethostname()

# Restic repository strings for B2 (format: b2:bucket:directory)
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

RESTIC_PASSWORD = "j57z66Mwc^2A%Cf5!iAG^n&c&%wJ"

# Backup Source Directories and Exclusions
SYSTEM_SOURCE = "/"  # Entire system
SYSTEM_EXCLUDES = [
    "/proc/*", "/sys/*", "/dev/*", "/run/*", "/tmp/*", "/var/tmp/*",
    "/mnt/*", "/media/*", "/var/cache/*", "/var/log/*",
    "/home/*/.cache/*", "/swapfile", "/lost+found",
    "*.vmdk", "*.vdi", "*.qcow2", "*.img", "*.iso", "*.tmp", "*.swap.img",
    "/var/lib/docker/*", "/var/lib/lxc/*",
]

VM_SOURCES = ["/etc/libvirt", "/var/lib/libvirt"]
VM_EXCLUDES = []  # Customize if needed

PLEX_SOURCES = [
    "/var/lib/plexmediaserver",
    "/etc/default/plexmediaserver",
]
PLEX_EXCLUDES = [
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
]

RETENTION_DAYS = 7
STALE_LOCK_HOURS = 2
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds

# Global backup status for reporting
BACKUP_STATUS = {
    "system": {"status": "pending", "message": ""},
    "vm": {"status": "pending", "message": ""},
    "plex": {"status": "pending", "message": ""},
    "cleanup_system": {"status": "pending", "message": ""},
    "cleanup_vm": {"status": "pending", "message": ""},
    "cleanup_plex": {"status": "pending", "message": ""},
}

# Logging Configuration
LOG_FILE = "/var/log/unified_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# Nord color theme for logging output (ANSI escape sequences)
NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg

def setup_logging():
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        log_path = Path(LOG_FILE)
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_log = f"{LOG_FILE}.{timestamp}"
            shutil.move(LOG_FILE, backup_log)
            logging.info(f"Rotated previous log to {backup_log}")
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logging.warning("Continuing with console logging only")
    return logger

def print_section(title: str):
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)

# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else f"signal {signum}"
    logging.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    if any(item["status"] != "pending" for item in BACKUP_STATUS.values()):
        print_status_report()

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY & PRIVILEGE CHECKS
# ------------------------------------------------------------------------------
def check_dependencies():
    dependencies = ["restic"]
    missing = [dep for dep in dependencies if not shutil.which(dep)]
    if missing:
        logging.error(f"Missing required dependencies: {', '.join(missing)}")
        sys.exit(1)
    try:
        result = subprocess.run(
            ["restic", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logging.info(f"Using {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not determine restic version: {e}")

def check_root():
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")

# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """Run a blocking function in a background thread while displaying a progress spinner."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      TimeElapsedColumn(), transient=True) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()

# ------------------------------------------------------------------------------
# REPOSITORY & RESTIC OPERATIONS
# ------------------------------------------------------------------------------
def run_restic(repo: str, password: str, *args, check=True, capture_output=False, max_retries=MAX_RETRIES):
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running: {' '.join(cmd)}")
    retries = 0
    last_error = None
    while retries <= max_retries:
        try:
            if capture_output:
                result = subprocess.run(cmd, check=check, env=env,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
                return result
            else:
                subprocess.run(cmd, check=check, env=env)
                return None
        except subprocess.CalledProcessError as e:
            last_error = e
            err_msg = e.stderr or str(e)
            transient = any(term in err_msg.lower() for term in [
                "connection reset by peer", "unexpected eof", "timeout",
                "connection refused", "network error", "429 too many requests",
                "500 internal server error", "503 service unavailable",
                "temporarily unavailable"
            ])
            if "init" in args and "already initialized" in err_msg:
                logging.info("Repository already initialized, continuing.")
                return None
            if transient and retries < max_retries:
                retries += 1
                delay = RETRY_DELAY_BASE * (2 ** (retries - 1))
                logging.warning(f"Transient error detected, retrying in {delay} seconds "
                                f"({retries}/{max_retries})...")
                time.sleep(delay)
                continue
            else:
                if retries > 0:
                    logging.error(f"Command failed after {retries} retries.")
                raise e
    if last_error:
        raise last_error

def is_repo_initialized(repo: str, password: str) -> bool:
    logging.info(f"Checking repository '{repo}'...")
    try:
        run_restic(repo, password, "snapshots", "--no-lock", "--json", capture_output=True)
        logging.info(f"Repository '{repo}' is initialized.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if any(msg in err_msg for msg in ["already initialized", "repository master key"]):
            logging.info(f"Repository '{repo}' is initialized but had access issues.")
            return True
        logging.info(f"Repository '{repo}' is not initialized.")
        return False

def ensure_repo_initialized(repo: str, password: str):
    logging.info(f"Ensuring repository '{repo}' is initialized...")
    if is_repo_initialized(repo, password):
        return True
    try:
        run_restic(repo, password, "init")
        logging.info(f"Repository '{repo}' successfully initialized.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if "already initialized" in err_msg:
            logging.info(f"Repository '{repo}' is already initialized (during init).")
            return True
        logging.error(f"Failed to initialize repository: {err_msg}")
        raise RuntimeError(f"Repo init failed: {err_msg}")

def force_unlock_repo(repo: str, password: str) -> bool:
    logging.warning(f"Forcing unlock of repository '{repo}'")
    try:
        if not is_repo_initialized(repo, password):
            logging.warning(f"Repo '{repo}' is not initialized; cannot unlock.")
            return False
        run_restic(repo, password, "unlock", "--remove-all")
        logging.info("Repository unlocked successfully.")
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if "no locks to remove" in err_msg:
            logging.info("Repository was already unlocked.")
            return True
        logging.error(f"Failed to unlock repository: {err_msg}")
        return False

def get_repo_stats(repo: str, password: str):
    stats = {"snapshots": 0, "total_size": "unknown", "latest_snapshot": "never"}
    if not is_repo_initialized(repo, password):
        return stats
    try:
        result = run_restic(repo, password, "snapshots", "--json", capture_output=True)
        snapshots = json.loads(result.stdout) if result and result.stdout else []
        stats["snapshots"] = len(snapshots)
        if snapshots:
            latest = sorted(snapshots, key=lambda s: s.get("time", ""), reverse=True)[0]
            stats["latest_snapshot"] = latest.get("time", "unknown")[:19]
    except Exception as e:
        logging.warning(f"Could not get snapshot info: {e}")
    try:
        result = run_restic(repo, password, "stats", "--json", capture_output=True)
        repo_stats = json.loads(result.stdout) if result and result.stdout else {}
        total = repo_stats.get("total_size", 0)
        stats["total_size"] = format_size(total)
    except Exception as e:
        logging.warning(f"Could not get repo size info: {e}")
    return stats

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(names)-1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {names[i]}"

# ------------------------------------------------------------------------------
# BACKUP & CLEANUP OPERATIONS (with progress spinners)
# ------------------------------------------------------------------------------
def backup_repo(repo: str, password: str, source, excludes: list = None, task_name: str = None) -> bool:
    if excludes is None:
        excludes = []
    if task_name:
        BACKUP_STATUS[task_name] = {"status": "in_progress", "message": "Backup in progress..."}
    try:
        ensure_repo_initialized(repo, password)
    except Exception as e:
        msg = f"Repo init failed: {e}"
        logging.error(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
        return False
    if not force_unlock_repo(repo, password):
        msg = "Failed to unlock repository before backup."
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
        return False

    cmd_args = ["backup"]
    if isinstance(source, list):
        cmd_args.extend(source)
    else:
        cmd_args.append(source)
    for pattern in excludes:
        cmd_args.extend(["--exclude", pattern])

    start = time.time()
    try:
        result = run_with_progress("Performing backup...", run_restic,
                                   repo, password, *cmd_args, capture_output=True)
        elapsed = time.time() - start
        msg = f"Backup completed in {elapsed:.1f} seconds."
        logging.info(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "success", "message": msg}
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(x in line for x in ["Files:", "Added to the", "processed", "snapshot"]):
                    logging.info(f"Summary: {line.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"
        if "repository is already locked" in err_output:
            logging.warning("Backup failed due to lock. Retrying after force unlock...")
            if force_unlock_repo(repo, password):
                try:
                    result = run_with_progress("Retrying backup...", run_restic,
                                               repo, password, *cmd_args, capture_output=True)
                    total = time.time() - start
                    msg = f"Backup completed after retry in {total:.1f} seconds."
                    logging.info(msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {"status": "success", "message": msg}
                    return True
                except Exception as retry_e:
                    msg = f"Backup failed after retry: {retry_e}"
                    logging.error(msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
                    return False
            else:
                msg = f"Failed to unlock repo after {elapsed:.1f} seconds."
                logging.error(msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
                return False
        else:
            msg = f"Backup failed after {elapsed:.1f} seconds: {err_output}"
            logging.error(msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
            return False

def cleanup_repo(repo: str, password: str, retention_days: int, task_name: str = None) -> bool:
    if task_name:
        BACKUP_STATUS[task_name] = {"status": "in_progress", "message": "Cleanup in progress..."}
    try:
        if not is_repo_initialized(repo, password):
            msg = f"Repo '{repo}' not initialized. Skipping cleanup."
            logging.warning(msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "skipped", "message": msg}
            return False
    except Exception as e:
        msg = f"Repo check failed for cleanup: {e}"
        logging.error(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
        return False

    if not force_unlock_repo(repo, password):
        msg = "Failed to unlock repository before cleanup."
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
        return False

    start = time.time()
    try:
        result = run_with_progress("Performing cleanup...", run_restic,
                                   repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d",
                                   capture_output=True)
        elapsed = time.time() - start
        msg = f"Cleanup completed in {elapsed:.1f} seconds."
        logging.info(msg)
        if task_name:
            BACKUP_STATUS[task_name] = {"status": "success", "message": msg}
        if result and result.stdout:
            for line in result.stdout.splitlines():
                if any(x in line for x in ["snapshots", "removing", "remaining", "deleted"]):
                    logging.info(f"Cleanup: {line.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        err_output = e.stderr or "Unknown error"
        if "repository is already locked" in err_output:
            logging.warning("Cleanup failed due to lock. Retrying after force unlock...")
            if force_unlock_repo(repo, password):
                try:
                    result = run_with_progress("Retrying cleanup...", run_restic,
                                               repo, password, "forget", "--prune", "--keep-within", f"{retention_days}d",
                                               capture_output=True)
                    total = time.time() - start
                    msg = f"Cleanup completed after retry in {total:.1f} seconds."
                    logging.info(msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {"status": "success", "message": msg}
                    return True
                except Exception as retry_e:
                    msg = f"Cleanup failed after retry: {retry_e}"
                    logging.error(msg)
                    if task_name:
                        BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
                    return False
            else:
                msg = f"Failed to unlock repo for cleanup after {elapsed:.1f} seconds."
                logging.error(msg)
                if task_name:
                    BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
                return False
        else:
            msg = f"Cleanup failed after {elapsed:.1f} seconds: {err_output}"
            logging.error(msg)
            if task_name:
                BACKUP_STATUS[task_name] = {"status": "failed", "message": msg}
            return False

# ------------------------------------------------------------------------------
# STATUS REPORTING
# ------------------------------------------------------------------------------
def print_status_report():
    print_section("Backup Status Report")
    icons = {
        "success": "✓" if not DISABLE_COLORS else "[SUCCESS]",
        "failed": "✗" if not DISABLE_COLORS else "[FAILED]",
        "pending": "?" if not DISABLE_COLORS else "[PENDING]",
        "in_progress": "⋯" if not DISABLE_COLORS else "[IN PROGRESS]",
        "skipped": "⏭" if not DISABLE_COLORS else "[SKIPPED]",
    }
    colors = {
        "success": NORD14,
        "failed": NORD11,
        "pending": NORD13,
        "in_progress": NORD8,
        "skipped": NORD9,
    }
    descriptions = {
        "system": "System Backup",
        "vm": "Virtual Machine Backup",
        "plex": "Plex Media Server Backup",
        "cleanup_system": "System Backup Cleanup",
        "cleanup_vm": "VM Backup Cleanup",
        "cleanup_plex": "Plex Backup Cleanup",
    }
    for task, data in BACKUP_STATUS.items():
        status = data["status"]
        msg = data["message"]
        task_desc = descriptions.get(task, task)
        if not DISABLE_COLORS:
            icon = icons[status]
            color = colors[status]
            logging.info(f"{color}{icon} {task_desc}: {status.upper()}{NC} - {msg}")
        else:
            logging.info(f"{icons[status]} {task_desc}: {status.upper()} - {msg}")

def print_repository_info():
    print_section("Repository Information")
    repos = [("System", B2_REPO_SYSTEM),
             ("VM", B2_REPO_VM),
             ("Plex", B2_REPO_PLEX)]
    for name, repo in repos:
        try:
            stats = get_repo_stats(repo, RESTIC_PASSWORD)
            logging.info(f"{name} Repository: {repo}")
            if stats["snapshots"] > 0:
                logging.info(f"  • Snapshots: {stats['snapshots']}")
                logging.info(f"  • Size: {stats['total_size']}")
                logging.info(f"  • Latest snapshot: {stats['latest_snapshot']}")
            else:
                logging.info("  • No snapshots found")
        except Exception as e:
            logging.warning(f"Could not get info for {name} repo: {e}")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    setup_logging()
    check_dependencies()
    check_root()

    start_time = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)

    print_section("System Information")
    logging.info(f"Hostname: {HOSTNAME}")
    logging.info(f"Running as user: {os.environ.get('USER', 'unknown')}")
    logging.info(f"Python version: {sys.version.split()[0]}")
    print_repository_info()

    print_section("Force Unlocking All Repositories")
    force_unlock_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_VM, RESTIC_PASSWORD)
    force_unlock_repo(B2_REPO_PLEX, RESTIC_PASSWORD)

    print_section("System Backup to Backblaze B2")
    system_success = backup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD, SYSTEM_SOURCE, SYSTEM_EXCLUDES, "system")

    print_section("VM Backup to Backblaze B2")
    vm_success = backup_repo(B2_REPO_VM, RESTIC_PASSWORD, VM_SOURCES, VM_EXCLUDES, "vm")

    print_section("Plex Media Server Backup to Backblaze B2")
    plex_success = backup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, PLEX_SOURCES, PLEX_EXCLUDES, "plex")

    print_section("Cleaning Up Old Snapshots (Retention Policy)")
    logging.info("Cleaning System Backup Repository")
    cleanup_repo(B2_REPO_SYSTEM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_system")
    logging.info("Cleaning VM Backup Repository")
    cleanup_repo(B2_REPO_VM, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_vm")
    logging.info("Cleaning Plex Backup Repository")
    cleanup_repo(B2_REPO_PLEX, RESTIC_PASSWORD, RETENTION_DAYS, "cleanup_plex")

    print_status_report()
    elapsed = time.time() - start_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "success")
    failed_count = sum(1 for v in BACKUP_STATUS.values() if v["status"] == "failed")
    summary = "SUCCESS" if failed_count == 0 else "PARTIAL SUCCESS" if success_count > 0 else "FAILED"
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP COMPLETED WITH {summary} AT {now} (took {elapsed:.1f} seconds)")
    logging.info("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
```

---

## Final Instruction

Before generating any code, **ask the user what further assistance they require**. Do not provide any additional feedback or produce any code until the user clarifies their request.
