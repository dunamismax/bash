#!/usr/bin/env python3
"""
Reset Tailscale on Ubuntu

This script:
  1. Stops and disables the tailscale service.
  2. Uninstalls tailscale and removes all configuration/data files.
  3. Reinstalls tailscale using the official install script.
  4. Enables and starts the tailscale service.
  5. Runs "tailscale up" to bring the daemon up.

All steps are displayed with colorful output, progress bars, and spinners.
Run this script as root.
"""

import os
import sys
import subprocess
import time
import shutil
import threading
from datetime import datetime


# ANSI colors for output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


# Simple progress bar class
class ProgressBar:
    def __init__(self, total, desc="", width=50):
        self.total = max(total, 1)
        self.desc = desc
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self._display()

    def update(self, amount=1):
        with self._lock:
            self.current = min(self.current + amount, self.total)
            self._display()

    def _format_time(self, seconds):
        if seconds < 60:
            return f"{seconds:.1f}s"
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"

    def _display(self):
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = (self.current / self.total) * 100
        elapsed = time.time() - self.start_time
        sys.stdout.write(
            f"\r{Colors.CYAN}{self.desc}:{Colors.ENDC} |{Colors.BLUE}{bar}{Colors.ENDC}| {percent:5.1f}% ({self.current}/{self.total}) [Elapsed: {self._format_time(elapsed)}]"
        )
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()


# Simple spinner for indeterminate progress
class Spinner:
    spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message):
        self.message = message
        self.spinning = False
        self.current = 0
        self._lock = threading.Lock()

    def _spin(self):
        start = time.time()
        while self.spinning:
            elapsed = time.time() - start
            time_str = f"{elapsed:.1f}s"
            with self._lock:
                sys.stdout.write(
                    f"\r{Colors.BLUE}{self.spinner_chars[self.current]}{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} [{Colors.DIM}Elapsed: {time_str}{Colors.ENDC}]"
                )
                sys.stdout.flush()
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self):
        self.spinning = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, success=True):
        self.spinning = False
        self.thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        status = (
            f"{Colors.GREEN}completed{Colors.ENDC}"
            if success
            else f"{Colors.RED}failed{Colors.ENDC}"
        )
        print(
            f"{Colors.GREEN if success else Colors.RED}{'✓' if success else '✗'}{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} {status}"
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop(exc_type is None)


def run_command(cmd, shell=False, check=True, capture_output=True):
    try:
        result = subprocess.run(
            cmd, shell=shell, check=check, capture_output=capture_output, text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(
            f"{Colors.RED}Command failed: {' '.join(cmd) if not shell else cmd}{Colors.ENDC}"
        )
        if e.stdout:
            print(f"{Colors.DIM}Stdout: {e.stdout.strip()}{Colors.ENDC}")
        if e.stderr:
            print(f"{Colors.RED}Stderr: {e.stderr.strip()}{Colors.ENDC}")
        raise


def print_header(msg):
    print(
        f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}\n{msg.center(80)}\n{'=' * 80}{Colors.ENDC}\n"
    )


def print_step(msg):
    print(f"{Colors.CYAN}• {msg}{Colors.ENDC}")


def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.ENDC}")


def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.ENDC}")


# Check for root privileges
def check_root():
    if os.geteuid() != 0:
        print_error("This script must be run as root (e.g., with sudo).")
        sys.exit(1)


# Uninstall tailscale completely
def uninstall_tailscale():
    print_header("Uninstalling Tailscale")
    steps = [
        ("Stopping tailscaled service", ["systemctl", "stop", "tailscaled"]),
        ("Disabling tailscaled service", ["systemctl", "disable", "tailscaled"]),
        (
            "Removing tailscale package",
            ["apt-get", "remove", "--purge", "tailscale", "-y"],
        ),
        ("Autoremoving unused packages", ["apt-get", "autoremove", "-y"]),
    ]
    progress = ProgressBar(len(steps), "Uninstall progress")
    for desc, cmd in steps:
        print_step(desc)
        with Spinner(desc) as spinner:
            run_command(cmd)
        progress.update(1)
    # Remove tailscale configuration and data directories
    paths = ["/var/lib/tailscale", "/etc/tailscale", "/usr/share/tailscale"]
    for path in paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print_success(f"Removed {path}")
            except Exception as e:
                print_warning(f"Could not remove {path}: {e}")
    print_success("Tailscale uninstalled and cleaned up.")


# Install tailscale via official install script
def install_tailscale():
    print_header("Installing Tailscale")
    # Download and run the install script from tailscale.com
    install_cmd = "curl -fsSL https://tailscale.com/install.sh | sh"
    print_step("Running tailscale install script")
    with Spinner("Installing tailscale"):
        run_command(install_cmd, shell=True)
    print_success("Tailscale installed.")


# Enable and start tailscale service
def start_tailscale_service():
    print_header("Enabling and Starting Tailscale Service")
    steps = [
        ("Enabling tailscaled service", ["systemctl", "enable", "tailscaled"]),
        ("Starting tailscaled service", ["systemctl", "start", "tailscaled"]),
    ]
    progress = ProgressBar(len(steps), "Service progress")
    for desc, cmd in steps:
        print_step(desc)
        with Spinner(desc):
            run_command(cmd)
        progress.update(1)
    print_success("Tailscale service enabled and started.")


# Run "tailscale up" and show output
def tailscale_up():
    print_header("Running 'tailscale up'")
    with Spinner("Executing tailscale up"):
        result = run_command(["tailscale", "up"])
    print_success("Tailscale is up!")
    print(f"\n{Colors.BOLD}tailscale up output:{Colors.ENDC}\n{result.stdout}")


def main():
    check_root()
    print_header("Tailscale Reset Script")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # Uninstall tailscale fully
    uninstall_tailscale()
    time.sleep(2)
    # Install tailscale
    install_tailscale()
    time.sleep(2)
    # Enable and start the service
    start_tailscale_service()
    time.sleep(2)
    # Bring tailscale up
    tailscale_up()
    print_header("Tailscale Reset Complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operation interrupted by user.{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
