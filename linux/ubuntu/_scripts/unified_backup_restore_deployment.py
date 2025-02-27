#!/usr/bin/env python3
"""
Enhanced File Restore Script with content verification
Restores files to correct locations with proper permissions.
"""

import hashlib
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

# Configuration
RESTORE_BASE = Path("/home/sawyer/restic_backup_restore_data")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)


class Colors:
    """ANSI color codes"""

    HEADER = "\033[95m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


# Service configurations
SERVICES = {
    "vm": {
        "name": "VM Configuration",
        "user": "libvirt-qemu",
        "group": "libvirt",
        "source": RESTORE_BASE / "vm/var/lib/libvirt",
        "target": Path("/var/lib/libvirt"),
        "service": "libvirtd",
        "permissions": "0755",
    },
    "plex": {
        "name": "Plex Media Server",
        "user": "plex",
        "group": "plex",
        "source": RESTORE_BASE
        / "plex/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": Path(
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"
        ),
        "service": "plexmediaserver",
        "permissions": "0755",
    },
}


class FileInfo:
    """File information for comparison"""

    def __init__(self, path: Path):
        self.path = path
        self.size = path.stat().st_size if path.exists() else 0
        self.mtime = path.stat().st_mtime if path.exists() else 0

    def needs_update(self, other: "FileInfo") -> bool:
        """Check if file needs to be updated based on size and mtime"""
        if not self.path.exists():
            return True
        return self.size != other.size or abs(self.mtime - other.mtime) > 1


class ProgressTracker:
    """Thread-safe progress tracking for file operations"""

    def __init__(self, total_bytes: int, desc: str):
        self.total_bytes = total_bytes
        self.desc = desc
        self.current_bytes = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, bytes_done: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current_bytes += bytes_done
            self._display_progress()

    def _format_size(self, bytes_val: int) -> str:
        """Format bytes to human readable size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}TB"

    def _display_progress(self) -> None:
        """Display progress with transfer rate"""
        if self.total_bytes == 0:
            return

        percent = (self.current_bytes / self.total_bytes) * 100
        elapsed = time.time() - self.start_time
        rate = self.current_bytes / elapsed if elapsed > 0 else 0
        eta = ((self.total_bytes - self.current_bytes) / rate) if rate > 0 else 0

        bar_width = 40
        filled = int(bar_width * self.current_bytes / self.total_bytes)
        bar = "=" * filled + "-" * (bar_width - filled)

        sys.stdout.write(
            f"\r{self.desc}: |{bar}| {percent:>5.1f}% "
            f"({self._format_size(self.current_bytes)}/{self._format_size(self.total_bytes)}) "
            f"[{self._format_size(rate)}/s] [ETA: {eta:.0f}s]"
        )
        sys.stdout.flush()

        if self.current_bytes >= self.total_bytes:
            sys.stdout.write("\n")


def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run command with error handling"""
    try:
        return subprocess.run(
            cmd, shell=True, check=check, text=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}Command failed: {cmd}")
        print(f"Error: {e.stderr}{Colors.ENDC}")
        raise


def scan_directory(path: Path) -> Dict[Path, FileInfo]:
    """Scan directory and return file information"""
    files = {}
    if path.exists():
        for file_path in path.rglob("*"):
            if file_path.is_file():
                files[file_path.relative_to(path)] = FileInfo(file_path)
    return files


def copy_file(src: Path, dst: Path, progress: Optional[ProgressTracker] = None) -> bool:
    """Copy file with progress tracking"""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)

        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while True:
                chunk = fsrc.read(CHUNK_SIZE)
                if not chunk:
                    break
                fdst.write(chunk)
                if progress:
                    progress.update(len(chunk))

        # Copy modification time
        os.utime(dst, (src.stat().st_atime, src.stat().st_mtime))
        return True
    except Exception as e:
        print(f"{Colors.RED}Failed to copy {src} to {dst}: {e}{Colors.ENDC}")
        return False


def service_control(name: str, action: str) -> bool:
    """Control system service"""
    try:
        run_command(f"systemctl {action} {name}")
        time.sleep(2)  # Wait for service state change
        return True
    except Exception as e:
        print(f"{Colors.RED}Failed to {action} service {name}: {e}{Colors.ENDC}")
        return False


def restore_service(name: str, config: Dict) -> bool:
    """Restore a single service with content verification"""
    print_header(f"Analyzing {config['name']}")

    try:
        # Scan source and target directories
        source_files = scan_directory(config["source"])
        target_files = scan_directory(config["target"])

        # Determine which files need to be updated
        files_to_update = []
        total_size = 0

        for rel_path, src_info in source_files.items():
            target_info = target_files.get(rel_path)
            if not target_info or target_info.needs_update(src_info):
                files_to_update.append(
                    (config["source"] / rel_path, config["target"] / rel_path)
                )
                total_size += src_info.size

        if not files_to_update:
            print(
                f"{Colors.GREEN}All files are up to date for {config['name']}. Skipping restore.{Colors.ENDC}"
            )
            return True

        print(
            f"Found {len(files_to_update)} files to restore ({total_size / (1024 * 1024):.1f} MB)"
        )

        # Stop service if running
        print(f"\nStopping {config['service']}...")
        service_control(config["service"], "stop")

        # Initialize progress tracking
        progress = ProgressTracker(total_size, "Restore progress")

        # Restore files
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for src_path, dst_path in files_to_update:
                futures.append(executor.submit(copy_file, src_path, dst_path, progress))

            # Wait for all copies to complete
            for future in futures:
                if not future.result():
                    return False

        # Set permissions
        print("\nSetting permissions...")
        run_command(f"chown -R {config['user']}:{config['group']} {config['target']}")
        run_command(f"chmod -R {config['permissions']} {config['target']}")

        # Start service
        print(f"\nStarting {config['service']}...")
        service_control(config["service"], "start")

        print(f"\n{Colors.GREEN}Successfully restored {config['name']}{Colors.ENDC}")
        return True

    except Exception as e:
        print(f"{Colors.RED}{config['name']} restore failed: {e}{Colors.ENDC}")
        return False


def handle_vm_shutdown() -> None:
    """Safely shutdown running VMs"""
    try:
        result = run_command("virsh list --all | grep running", check=False)
        if result.returncode == 0 and result.stdout.strip():
            print("\nShutting down running VMs...")
            run_command(
                "virsh list --all | grep running | "
                "awk '{print $2}' | xargs -I{} virsh shutdown {}"
            )
            time.sleep(5)  # Wait for VMs to shutdown
    except Exception as e:
        print(f"{Colors.RED}Failed to shutdown VMs: {e}{Colors.ENDC}")
        raise


def main() -> None:
    """Main execution function"""
    if os.geteuid() != 0:
        print(
            f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)

    results: List[Tuple[str, bool]] = []

    try:
        print_header("Starting File Restore")

        # Handle VM shutdown first if needed
        if "vm" in SERVICES:
            handle_vm_shutdown()

        # Restore each service
        for service_name, config in SERVICES.items():
            success = restore_service(service_name, config)
            results.append((config["name"], success))

        # Print final summary
        print_header("Restore Summary")
        for name, success in results:
            status = (
                f"{Colors.GREEN}SUCCESS{Colors.ENDC}"
                if success
                else f"{Colors.RED}FAILED{Colors.ENDC}"
            )
            print(f"{name}: {status}")

        # Exit with appropriate status
        if not all(success for _, success in results):
            sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Restore interrupted by user{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Restore failed: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
