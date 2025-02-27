#!/usr/bin/env python3
"""
Enhanced Unified Restic Backup Script

This script performs backups for multiple system components:
  • System (root filesystem)
  • Virtual Machines (libvirt)
  • Plex Media Server

It uses restic to create incremental backups to Backblaze B2 storage with
clean progress tracking, robust error handling, and clear status reporting.
Designed for Ubuntu/Linux systems, run this script with root privileges.
"""

import argparse
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#####################################
# Configuration
#####################################

HOSTNAME = socket.gethostname()

# Restic and B2 configuration
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Repository paths per service
REPOSITORIES: Dict[str, str] = {
    "system": f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup",
    "vm": f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups",
    "plex": f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup",
}

# Backup configuration per service
BACKUP_CONFIGS: Dict[str, Dict] = {
    "system": {
        "paths": ["/"],
        "excludes": [
            "/proc/*",
            "/sys/*",
            "/dev/*",
            "/run/*",
            "/tmp/*",
            "/var/tmp/*",
            "/mnt/*",
            "/media/*",
            "/var/cache/*",
            "/var/log/*",
            "/home/*/.cache/*",
            "/swapfile",
            "/lost+found",
            "*.vmdk",
            "*.vdi",
            "*.qcow2",
            "*.img",
            "*.iso",
            "*.tmp",
            "*.swap.img",
            "/var/lib/docker/*",
            "/var/lib/lxc/*",
        ],
        "name": "System",
        "description": "Root filesystem backup",
    },
    "vm": {
        "paths": ["/etc/libvirt", "/var/lib/libvirt"],
        "excludes": [],
        "name": "Virtual Machines",
        "description": "VM configuration and storage",
    },
    "plex": {
        "paths": ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"],
        "excludes": [
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Cache/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Codecs/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Crash Reports/*",
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/*",
        ],
        "name": "Plex Media Server",
        "description": "Plex configuration and data",
    },
}

RETENTION_POLICY = "7d"  # e.g., keep snapshots from last 7 days

# Progress tracking settings
PROGRESS_WIDTH = 50
CHUNK_SIZE = 1024 * 1024  # 1MB

# Logging configuration
LOG_DIR = "/var/log/backup"
LOG_FILE = f"{LOG_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#####################################
# Nord Themed Colors
#####################################


class NordColors:
    HEADER = "\033[38;2;180;142;173m"  # Purple
    GREEN = "\033[38;2;163;190;140m"  # Green
    YELLOW = "\033[38;2;235;203;139m"  # Yellow
    RED = "\033[38;2;191;97;106m"  # Red
    BLUE = "\033[38;2;129;161;193m"  # Blue
    SNOW = "\033[38;2;216;222;233m"  # Light foreground
    BOLD = "\033[1m"
    ENDC = "\033[0m"


#####################################
# UI and Progress Tracking
#####################################


class ProgressBar:
    """
    Simple thread-safe progress bar supporting determinate and indeterminate modes.
    """

    def __init__(
        self, total: Optional[int] = None, desc: str = "", determinate: bool = True
    ):
        self.total = total if total is not None else 100
        self.desc = desc
        self.determinate = determinate
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self._spinner = ["|", "/", "-", "\\"]
        self._spinner_index = 0

    def update(self, amount: int = 0) -> None:
        with self._lock:
            if self.determinate:
                self.current = min(self.current + amount, self.total)
            else:
                self._spinner_index = (self._spinner_index + 1) % len(self._spinner)
            self._display()

    def _format_size(self, bytes_value: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_value < 1024:
                return f"{bytes_value:.1f}{unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f}TB"

    def _format_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s"

    def _display(self) -> None:
        elapsed = time.time() - self.start_time
        if self.determinate:
            percent = (self.current / self.total) * 100
            filled = int(PROGRESS_WIDTH * self.current / self.total)
            bar = "█" * filled + "░" * (PROGRESS_WIDTH - filled)
            eta = (
                (self.total - self.current) / (self.current / elapsed)
                if self.current
                else 0
            )
            sys.stdout.write(
                f"\r{NordColors.BOLD}{self.desc}{NordColors.ENDC}: |{bar}| {percent:5.1f}% "
                f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
                f"[ETA: {self._format_time(eta)}]"
            )
        else:
            spinner = self._spinner[self._spinner_index]
            sys.stdout.write(
                f"\r{NordColors.BOLD}{self.desc}{NordColors.ENDC}: {spinner} "
                f"[Elapsed: {self._format_time(elapsed)}]"
            )
        sys.stdout.flush()
        if self.determinate and self.current >= self.total:
            sys.stdout.write("\n")


#####################################
# Helper Functions
#####################################


def print_header(message: str) -> None:
    print(f"\n{NordColors.BOLD}{NordColors.HEADER}{'═' * 80}")
    print(message.center(80))
    print(f"{'═' * 80}{NordColors.ENDC}\n")


def print_section(message: str) -> None:
    print(f"\n{NordColors.BOLD}{NordColors.BLUE}▶ {message}{NordColors.ENDC}")


def run_command(
    cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True
) -> subprocess.CompletedProcess:
    try:
        logging.debug(f"Running command: {' '.join(cmd)}")
        return subprocess.run(cmd, env=env, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {' '.join(cmd)}\nError: {e.stderr or str(e)}"
        logging.error(error_msg)
        print(f"{NordColors.RED}{error_msg}{NordColors.ENDC}")
        raise


def signal_handler(sig, frame) -> None:
    print(f"\n{NordColors.YELLOW}Backup interrupted. Exiting...{NordColors.ENDC}")
    sys.exit(1)


def get_disk_usage(path: str = "/") -> Tuple[int, int, float]:
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bfree * stat.f_frsize
    used = total - free
    percent = (used / total) * 100 if total > 0 else 0
    return total, used, percent


def check_service_status(service_name: str) -> Tuple[bool, str]:
    try:
        result = run_command(["systemctl", "is-active", service_name], check=False)
        is_running = result.returncode == 0
        status = result.stdout.strip()
        return (True, "running") if is_running else (False, status)
    except Exception as e:
        return (False, f"unknown (error: {e})")


def format_size(bytes_value: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} PB"


def check_root_privileges() -> bool:
    if os.geteuid() != 0:
        print(
            f"{NordColors.RED}Error: This script must be run as root.{NordColors.ENDC}"
        )
        return False
    return True


def check_dependencies() -> bool:
    if not shutil.which("restic"):
        print(
            f"{NordColors.RED}Error: Restic is not installed. Please install restic first.{NordColors.ENDC}"
        )
        return False
    try:
        result = run_command(["restic", "version"])
        version = result.stdout.strip()
        print(f"{NordColors.GREEN}Restic version: {version}{NordColors.ENDC}")
    except Exception as e:
        print(
            f"{NordColors.YELLOW}Warning: Could not determine restic version: {e}{NordColors.ENDC}"
        )
    return True


def check_environment() -> bool:
    missing_vars = []
    if not B2_ACCOUNT_ID:
        missing_vars.append("B2_ACCOUNT_ID")
    if not B2_ACCOUNT_KEY:
        missing_vars.append("B2_ACCOUNT_KEY")
    if not RESTIC_PASSWORD:
        missing_vars.append("RESTIC_PASSWORD")
    if missing_vars:
        print(
            f"{NordColors.RED}Error: Missing environment variables: {', '.join(missing_vars)}{NordColors.ENDC}"
        )
        return False
    return True


def check_service_paths(service: str) -> bool:
    config = BACKUP_CONFIGS.get(service, {})
    if service == "system":
        return True
    elif service == "vm":
        for path in ["/etc/libvirt", "/var/lib/libvirt"]:
            if not os.path.exists(path):
                print(
                    f"{NordColors.RED}Error: Path {path} not found. Is libvirt installed?{NordColors.ENDC}"
                )
                return False
        return True
    elif service == "plex":
        for path in ["/var/lib/plexmediaserver", "/etc/default/plexmediaserver"]:
            if not os.path.exists(path):
                print(
                    f"{NordColors.RED}Error: Path {path} not found. Is Plex installed?{NordColors.ENDC}"
                )
                return False
        return True
    return False


def setup_logging() -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
        )
        logging.info(f"Logging initialized. Log file: {LOG_FILE}")
    except Exception as e:
        print(
            f"{NordColors.RED}Warning: Could not set up logging: {e}{NordColors.ENDC}"
        )
        logging.basicConfig(
            level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT
        )


#####################################
# Repository and Backup Functions
#####################################


def initialize_repository(service: str) -> bool:
    repo = REPOSITORIES[service]
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )
    try:
        run_command(["restic", "--repo", repo, "snapshots"], env=env)
        print(f"{NordColors.GREEN}Repository already initialized.{NordColors.ENDC}")
        return True
    except subprocess.CalledProcessError:
        print(
            f"{NordColors.YELLOW}Repository not found. Initializing...{NordColors.ENDC}"
        )
        progress = ProgressBar(desc="Initializing repository", determinate=False)
        thread = threading.Thread(
            target=lambda: run_command(["restic", "--repo", repo, "init"], env=env)
        )
        thread.start()
        while thread.is_alive():
            progress.update()
            time.sleep(0.1)
        thread.join()
        print(
            f"{NordColors.GREEN}Repository initialized successfully.{NordColors.ENDC}"
        )
        return True
    except Exception as e:
        print(f"{NordColors.RED}Failed to initialize repository: {e}{NordColors.ENDC}")
        return False


def estimate_backup_size(service: str) -> int:
    """
    Simple estimation of backup size based on disk usage.
    """
    if service == "system":
        total, used, _ = get_disk_usage("/")
        # Subtract an estimated excluded size (e.g., 20% of used space)
        estimated = int(used * 0.8)
        print(f"Estimated backup size: {format_size(estimated)}")
        return estimated
    else:
        total_size = 0
        for path in BACKUP_CONFIGS[service]["paths"]:
            for root, _, files in os.walk(path):
                for file in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except Exception:
                        pass
        print(f"Calculated backup size: {format_size(total_size)}")
        return total_size


def perform_backup(service: str) -> bool:
    config = BACKUP_CONFIGS[service]
    repo = REPOSITORIES[service]
    print_header(f"Starting {config['name']} Backup")
    print_section("Calculating Backup Size")
    estimated_size = estimate_backup_size(service)
    if estimated_size == 0:
        print(
            f"{NordColors.YELLOW}Warning: No files to backup for {config['name']}.{NordColors.ENDC}"
        )
        return False

    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )

    print_section("Executing Backup")
    progress = ProgressBar(
        total=estimated_size, desc="Backup progress", determinate=True
    )

    backup_cmd = ["restic", "--repo", repo, "backup"] + config["paths"]
    for excl in config["excludes"]:
        backup_cmd.extend(["--exclude", excl])
    backup_cmd.extend(["--verbose"])

    process = subprocess.Popen(
        backup_cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    while True:
        line = process.stdout.readline()
        if not line:
            break
        # Print output for logging/debugging
        print(line.strip())
        # Update progress by a fixed chunk (approximation)
        progress.update(CHUNK_SIZE)
    process.wait()
    if process.returncode != 0:
        print(
            f"{NordColors.RED}Backup failed with return code {process.returncode}.{NordColors.ENDC}"
        )
        return False
    print(
        f"{NordColors.GREEN}{config['name']} backup completed successfully.{NordColors.ENDC}"
    )
    return True


def perform_retention(service: str) -> bool:
    repo = REPOSITORIES[service]
    print_section("Applying Retention Policy")
    print(f"Keeping snapshots within {RETENTION_POLICY}")
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )
    retention_cmd = [
        "restic",
        "--repo",
        repo,
        "forget",
        "--prune",
        "--keep-within",
        RETENTION_POLICY,
    ]
    progress = ProgressBar(desc="Pruning snapshots", determinate=False)
    thread = threading.Thread(target=lambda: run_command(retention_cmd, env=env))
    thread.start()
    while thread.is_alive():
        progress.update()
        time.sleep(0.1)
    thread.join()
    print(f"{NordColors.GREEN}Retention policy applied successfully.{NordColors.ENDC}")
    return True


def list_snapshots(service: str) -> bool:
    repo = REPOSITORIES[service]
    print_section("Listing Snapshots")
    env = os.environ.copy()
    env.update(
        {
            "RESTIC_PASSWORD": RESTIC_PASSWORD,
            "B2_ACCOUNT_ID": B2_ACCOUNT_ID,
            "B2_ACCOUNT_KEY": B2_ACCOUNT_KEY,
        }
    )
    try:
        result = run_command(["restic", "--repo", repo, "snapshots", "--json"], env=env)
        snapshots = json.loads(result.stdout)
        if snapshots:
            print(f"\n{'ID':<10} {'Date':<20} {'Size':<10}")
            print("-" * 40)
            for snap in snapshots:
                sid = snap.get("short_id", "unknown")
                time_str = snap.get("time", "")
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
                size = snap.get("stats", {}).get("total_size_formatted", "-")
                print(f"{sid:<10} {time_str:<20} {size:<10}")
            print("-" * 40)
            print(f"Total snapshots: {len(snapshots)}")
        else:
            print(f"{NordColors.YELLOW}No snapshots found.{NordColors.ENDC}")
        return True
    except Exception as e:
        print(f"{NordColors.RED}Failed to list snapshots: {e}{NordColors.ENDC}")
        return False


def backup_service(service: str) -> bool:
    if service not in BACKUP_CONFIGS:
        print(f"{NordColors.RED}Error: Unknown service '{service}'.{NordColors.ENDC}")
        return False
    config = BACKUP_CONFIGS[service]
    print_header(f"{config['name']} Backup")
    print(f"{NordColors.BLUE}Description:{NordColors.ENDC} {config['description']}")
    print(f"{NordColors.BLUE}Repository:{NordColors.ENDC} {REPOSITORIES[service]}")
    print(f"{NordColors.BLUE}Paths:{NordColors.ENDC} {', '.join(config['paths'])}")
    print(
        f"{NordColors.BLUE}Excludes:{NordColors.ENDC} {len(config['excludes'])} patterns"
    )
    if not check_service_paths(service):
        return False
    if service == "vm":
        status = check_service_status("libvirtd")[1]
        print(f"{NordColors.BLUE}libvirtd Status:{NordColors.ENDC} {status}")
    elif service == "plex":
        status = check_service_status("plexmediaserver")[1]
        print(f"{NordColors.BLUE}Plex Status:{NordColors.ENDC} {status}")
    if not initialize_repository(service):
        return False
    start_time = time.time()
    if not perform_backup(service):
        return False
    if not perform_retention(service):
        print(
            f"{NordColors.YELLOW}Warning: Retention policy application failed.{NordColors.ENDC}"
        )
    list_snapshots(service)
    elapsed = time.time() - start_time
    print_section("Service Backup Summary")
    print(
        f"{NordColors.GREEN}Backup completed in {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s{NordColors.ENDC}"
    )
    return True


def backup_all_services() -> Dict[str, bool]:
    results: Dict[str, bool] = {}
    print_header("Starting Backup for All Services")
    start_time = time.time()
    for service in BACKUP_CONFIGS:
        print_header(f"Service: {BACKUP_CONFIGS[service]['name']}")
        results[service] = backup_service(service)
    elapsed = time.time() - start_time
    print_header("Overall Backup Summary")
    print(
        f"{NordColors.GREEN}Total elapsed time: {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s{NordColors.ENDC}"
    )
    return results


#####################################
# Main Function and CLI
#####################################


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified Restic Backup Script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--service",
        choices=list(BACKUP_CONFIGS.keys()) + ["all"],
        help="Service to backup (system, vm, plex, or all)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (requires --service)",
    )
    parser.add_argument(
        "--retention", default=RETENTION_POLICY, help="Retention policy (e.g., 7d)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    setup_logging()
    global RETENTION_POLICY
    RETENTION_POLICY = args.retention
    if (
        not check_root_privileges()
        or not check_dependencies()
        or not check_environment()
    ):
        sys.exit(1)
    print_header("Unified Restic Backup Script")
    print(f"{NordColors.BLUE}Hostname:{NordColors.ENDC} {HOSTNAME}")
    print(f"{NordColors.BLUE}Platform:{NordColors.ENDC} {platform.platform()}")
    print(f"{NordColors.BLUE}Backup bucket:{NordColors.ENDC} {B2_BUCKET}")
    print(f"{NordColors.BLUE}Retention policy:{NordColors.ENDC} {RETENTION_POLICY}")
    print(
        f"{NordColors.BLUE}Available services:{NordColors.ENDC} {', '.join(BACKUP_CONFIGS.keys())}"
    )
    if args.non_interactive and args.service:
        start_time = time.time()
        if args.service == "all":
            results = backup_all_services()
            if not all(results.values()):
                sys.exit(1)
        else:
            if not backup_service(args.service):
                sys.exit(1)
        elapsed = time.time() - start_time
    else:
        print("\nSelect a service to backup:")
        services = list(BACKUP_CONFIGS.keys())
        for i, svc in enumerate(services, 1):
            conf = BACKUP_CONFIGS[svc]
            print(f"{i}. {conf['name']} - {conf['description']}")
        print(f"{len(services) + 1}. All Services")
        try:
            choice = int(
                input(f"\nEnter your choice (1-{len(services) + 1}): ").strip()
            )
            start_time = time.time()
            if choice <= len(services):
                if not backup_service(services[choice - 1]):
                    sys.exit(1)
            else:
                results = backup_all_services()
                if not all(results.values()):
                    sys.exit(1)
            elapsed = time.time() - start_time
        except (ValueError, KeyboardInterrupt):
            print(
                f"{NordColors.RED}Invalid input or interrupted. Exiting.{NordColors.ENDC}"
            )
            sys.exit(1)
    print_header("Final Backup Summary")
    print(
        f"{NordColors.GREEN}Backup completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{NordColors.ENDC}"
    )
    print(
        f"Total elapsed time: {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"
    )
    print(f"Log file: {LOG_FILE}")


if __name__ == "__main__":
    main()
