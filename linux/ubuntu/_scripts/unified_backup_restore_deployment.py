#!/usr/bin/env python3
"""
Streamlined File Restore Script
Restores files to correct locations with proper permissions.
"""

import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configuration
RESTORE_BASE = Path("/home/sawyer/restic_backup_restore_data")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress tracking
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)

class Colors:
    """ANSI color codes"""
    HEADER = '\033[95m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Service configurations
SERVICES = {
    "vm": {
        "name": "VM Configuration",
        "user": "libvirt-qemu",
        "group": "libvirt",
        "source": RESTORE_BASE / "vm/var/lib/libvirt",
        "target": Path("/var/lib/libvirt"),
        "service": "libvirtd",
        "permissions": "0755"
    },
    "plex": {
        "name": "Plex Media Server",
        "user": "plex",
        "group": "plex",
        "source": RESTORE_BASE / "plex/var/lib/plexmediaserver/Library/Application Support/Plex Media Server",
        "target": Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"),
        "service": "plexmediaserver",
        "permissions": "0755"
    }
}

class ProgressBar:
    """Thread-safe progress bar with transfer rate display"""
    def __init__(self, total: int, desc: str = "", width: int = 50):
        self.total = total
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def update(self, amount: int) -> None:
        """Update progress safely"""
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_size(self, bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"

    def _display(self) -> None:
        """Display progress bar with transfer rate"""
        filled = int(self.width * self.current / self.total)
        bar = '=' * filled + '-' * (self.width - filled)
        percent = self.current / self.total * 100
        
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        eta = (self.total - self.current) / rate if rate > 0 else 0
        
        sys.stdout.write(
            f"\r{self.desc}: |{bar}| {percent:>5.1f}% "
            f"({self._format_size(self.current)}/{self._format_size(self.total)}) "
            f"[{self._format_size(rate)}/s] [ETA: {eta:.0f}s]"
        )
        sys.stdout.flush()
        
        if self.current >= self.total:
            sys.stdout.write('\n')

def print_header(message: str) -> None:
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}")
    print(message.center(80))
    print(f"{'='*80}{Colors.ENDC}\n")

def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run command with error handling"""
    try:
        return subprocess.run(
            cmd,
            shell=True,
            check=check,
            text=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}Command failed: {cmd}")
        print(f"Error: {e.stderr}{Colors.ENDC}")
        raise

def service_control(name: str, action: str) -> bool:
    """Control system service"""
    try:
        run_command(f"systemctl {action} {name}")
        time.sleep(2)  # Wait for service state change
        return True
    except Exception as e:
        print(f"{Colors.RED}Failed to {action} service {name}: {e}{Colors.ENDC}")
        return False

def calculate_directory_size(path: Path) -> Tuple[int, int]:
    """Calculate total size and count of files"""
    total_size = 0
    file_count = 0
    
    for p in path.rglob("*"):
        if p.is_file():
            total_size += p.stat().st_size
            file_count += 1
            
    return total_size, file_count

def copy_with_progress(
    src: Path,
    dst: Path,
    progress: Optional[ProgressBar] = None
) -> bool:
    """Copy file with progress tracking"""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            while True:
                chunk = fsrc.read(CHUNK_SIZE)
                if not chunk:
                    break
                fdst.write(chunk)
                if progress:
                    progress.update(len(chunk))
        return True
    except Exception as e:
        print(f"{Colors.RED}Failed to copy {src} to {dst}: {e}{Colors.ENDC}")
        return False

def restore_service(name: str, config: Dict) -> bool:
    """Restore a single service"""
    print_header(f"Restoring {config['name']}")
    
    try:
        # Stop service if running
        print(f"Stopping {config['service']}...")
        service_control(config['service'], "stop")
        
        # Calculate files to restore
        total_size, file_count = calculate_directory_size(config['source'])
        print(f"Preparing to restore {file_count} files "
              f"({total_size / (1024*1024):.1f} MB)")
        
        # Restore files with progress tracking
        progress = ProgressBar(total_size, desc="Restore progress")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for src_path in config['source'].rglob("*"):
                if src_path.is_file():
                    rel_path = src_path.relative_to(config['source'])
                    dst_path = config['target'] / rel_path
                    futures.append(
                        executor.submit(
                            copy_with_progress,
                            src_path,
                            dst_path,
                            progress
                        )
                    )
            
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
        service_control(config['service'], "start")
        
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
        print(f"{Colors.RED}Error: This script must be run with root privileges.{Colors.ENDC}")
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
            results.append((config['name'], success))
        
        # Print final summary
        print_header("Restore Summary")
        for name, success in results:
            status = f"{Colors.GREEN}SUCCESS{Colors.ENDC}" if success else f"{Colors.RED}FAILED{Colors.ENDC}"
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
