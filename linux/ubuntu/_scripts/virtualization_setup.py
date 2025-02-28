#!/usr/bin/env python3
"""
Enhanced Virtualization Environment Setup Script

This utility sets up a virtualization environment on Ubuntu. It:
  • Updates package lists and installs virtualization packages
  • Manages virtualization services
  • Configures and recreates the default NAT network
  • Fixes storage permissions and user group settings
  • Updates VM network settings, autostart, and starts VMs
  • Verifies the overall setup

Note: Run this script with root privileges.
"""

import atexit, argparse, os, pwd, grp, signal, shutil, socket, subprocess, sys, threading, time, xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ------------------------------
# Configuration
# ------------------------------
HOSTNAME = socket.gethostname()
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 2)
OPERATION_TIMEOUT = 600  # seconds

VM_STORAGE_PATHS = ["/var/lib/libvirt/images", "/var/lib/libvirt/boot"]
VIRTUALIZATION_PACKAGES = [
    "qemu-kvm",
    "qemu-utils",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virt-manager",
    "bridge-utils",
    "cpu-checker",
    "ovmf",
    "virtinst",
    "libguestfs-tools",
    "virt-top",
]
VIRTUALIZATION_SERVICES = ["libvirtd", "virtlogd"]

VM_OWNER = "root"
VM_GROUP = "libvirt-qemu"
VM_DIR_MODE = 0o2770
VM_FILE_MODE = 0o0660
LIBVIRT_USER_GROUP = "libvirt"

DEFAULT_NETWORK_XML = """<network>
  <name>default</name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.2' end='192.168.122.254'/>
    </dhcp>
  </ip>
</network>
"""


# ANSI color codes
class Colors:
    HEADER = "\033[38;5;81m"
    GREEN = "\033[38;5;108m"
    YELLOW = "\033[38;5;179m"
    RED = "\033[38;5;174m"
    BLUE = "\033[38;5;67m"
    CYAN = "\033[38;5;110m"
    WHITE = "\033[38;5;253m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


# ------------------------------
# UI Helpers
# ------------------------------
def print_header(msg):
    print(
        f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}\n{msg.center(80)}\n{'=' * 80}{Colors.ENDC}\n"
    )


def print_section(msg):
    print(f"\n{Colors.BLUE}{Colors.BOLD}▶ {msg}{Colors.ENDC}")


def print_step(msg):
    print(f"{Colors.CYAN}• {msg}{Colors.ENDC}")


def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.ENDC}")


def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.ENDC}")


# ------------------------------
# Progress & Spinner Classes
# ------------------------------
class ProgressBar:
    def __init__(self, total, desc="", width=50):
        self.total = max(1, total)
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
        if m < 60:
            return f"{m:.0f}m {s:.0f}s"
        h, m = divmod(m, 60)
        return f"{h:.0f}h {m:.0f}m"

    def _display(self):
        filled = int(self.width * self.current / self.total)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = self.current / self.total * 100
        elapsed = time.time() - self.start_time
        rate = self.current / max(elapsed, 0.001)
        eta = (self.total - self.current) / max(rate, 0.001)
        sys.stdout.write(
            f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| {Colors.WHITE}{percent:>5.1f}%{Colors.ENDC} ({self.current}/{self.total}) [ETA: {self._format_time(eta)}]"
        )
        sys.stdout.flush()
        if self.current >= self.total:
            sys.stdout.write(
                f"\r{Colors.CYAN}{self.desc}: {Colors.ENDC}|{Colors.BLUE}{bar}{Colors.ENDC}| {Colors.GREEN}Complete!{Colors.ENDC} (Took: {self._format_time(elapsed)})\n"
            )
            sys.stdout.flush()


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
                    f"\r{Colors.BLUE}{self.spinner_chars[self.current]}{Colors.ENDC} {Colors.CYAN}{self.message}{Colors.ENDC} [{Colors.DIM}elapsed: {time_str}{Colors.ENDC}]"
                )
                sys.stdout.flush()
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def start(self):
        if not self.spinning:
            self.spinning = True
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success=True):
        self.spinning = False
        if hasattr(self, "thread"):
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


# ------------------------------
# Command Execution Helper
# ------------------------------
def run_command(cmd, env=None, check=True, capture_output=True, timeout=None):
    try:
        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            print(f"{Colors.DIM}Stdout: {e.stdout.strip()}{Colors.ENDC}")
        if e.stderr:
            print(f"{Colors.RED}Stderr: {e.stderr.strip()}{Colors.ENDC}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except Exception as e:
        print_error(f"Error executing command: {' '.join(cmd)}\nDetails: {e}")
        raise


def run_command_with_spinner(cmd, desc, check=True, env=None):
    with Spinner(desc) as spinner:
        try:
            result = run_command(cmd, env=env, check=check)
            return True, result
        except Exception as e:
            spinner.stop(False)
            print_error(f"Command failed: {e}")
            return False, None


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def signal_handler(sig, frame):
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print(
        f"\n{Colors.YELLOW}Process interrupted by {sig_name}. Cleaning up...{Colors.ENDC}"
    )
    cleanup()
    sys.exit(128 + sig)


def cleanup():
    print_step("Performing cleanup tasks...")


# ------------------------------
# Core Functions
# ------------------------------
def update_system_packages():
    print_section("Updating Package Lists")
    try:
        with Spinner("Updating package lists"):
            run_command(["apt-get", "update"])
        print_success("Package lists updated")
        return True
    except Exception as e:
        print_error(f"Failed to update package lists: {e}")
        return False


def install_virtualization_packages(packages):
    print_section("Installing Virtualization Packages")
    if not packages:
        print_warning("No packages specified")
        return True
    total = len(packages)
    print_step(f"Installing {total} packages: {', '.join(packages)}")
    progress = ProgressBar(total, "Package installation")
    failed = []
    for i, pkg in enumerate(packages, 1):
        print_step(f"Installing ({i}/{total}): {pkg}")
        try:
            proc = subprocess.Popen(
                ["apt-get", "install", "-y", pkg],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                if "Unpacking" in line or "Setting up" in line:
                    print("  " + line.strip())
            proc.wait()
            if proc.returncode != 0:
                print_error(f"Failed to install {pkg}")
                failed.append(pkg)
            else:
                print_success(f"{pkg} installed")
        except Exception as e:
            print_error(f"Error installing {pkg}: {e}")
            failed.append(pkg)
        progress.update(1)
    if failed:
        print_warning(f"Failed to install: {', '.join(failed)}")
        return False
    print_success("All packages installed")
    return True


def manage_virtualization_services(services):
    print_section("Managing Virtualization Services")
    if not services:
        print_warning("No services specified")
        return True
    progress = ProgressBar(len(services) * 2, "Service management")
    failed = []
    for svc in services:
        for action in [
            ("enable", ["systemctl", "enable", svc]),
            ("start", ["systemctl", "start", svc]),
        ]:
            print_step(f"{action[0].capitalize()} service: {svc}")
            try:
                run_command(action[1])
                print_success(f"{svc} {action[0]}d")
            except Exception as e:
                print_error(f"Failed to {action[0]} {svc}: {e}")
                failed.append(f"{svc} ({action[0]})")
            progress.update(1)
    if failed:
        print_warning(f"Issues with: {', '.join(failed)}")
        return False
    print_success("Services managed successfully")
    return True


def recreate_default_network():
    print_section("Recreating Default Network")
    try:
        result = run_command(
            ["virsh", "net-list", "--all"], capture_output=True, check=False
        )
        if "default" in result.stdout:
            print_step("Removing existing default network")
            run_command(["virsh", "net-destroy", "default"], check=False)
            autostart_path = "/etc/libvirt/qemu/networks/autostart/default.xml"
            if os.path.exists(autostart_path) or os.path.islink(autostart_path):
                os.remove(autostart_path)
            run_command(["virsh", "net-undefine", "default"], check=False)
        net_xml_path = "/tmp/default_network.xml"
        with open(net_xml_path, "w") as f:
            f.write(DEFAULT_NETWORK_XML)
        print_step("Defining new default network")
        run_command(["virsh", "net-define", net_xml_path])
        run_command(["virsh", "net-start", "default"])
        run_command(["virsh", "net-autostart", "default"])
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        if "default" in net_list.stdout and "active" in net_list.stdout:
            print_success("Default network is active")
            return True
        print_error("Default network not running")
        return False
    except Exception as e:
        print_error(f"Error recreating network: {e}")
        return False


def configure_default_network():
    print_section("Configuring Default Network")
    try:
        net_list = run_command(["virsh", "net-list", "--all"], capture_output=True)
        if "default" in net_list.stdout:
            print_step("Default network exists")
            if "active" not in net_list.stdout:
                print_step("Starting default network")
                try:
                    run_command(["virsh", "net-start", "default"])
                    print_success("Default network started")
                except Exception as e:
                    print_error(f"Start failed: {e}")
                    return recreate_default_network()
        else:
            print_step("Default network missing, creating it")
            return recreate_default_network()
        try:
            net_info = run_command(
                ["virsh", "net-info", "default"], capture_output=True
            )
            if "Autostart:      yes" not in net_info.stdout:
                print_step("Setting autostart")
                autostart_path = "/etc/libvirt/qemu/networks/autostart/default.xml"
                if os.path.exists(autostart_path) or os.path.islink(autostart_path):
                    os.remove(autostart_path)
                run_command(["virsh", "net-autostart", "default"])
                print_success("Autostart enabled")
            else:
                print_success("Autostart already enabled")
        except Exception as e:
            print_warning(f"Autostart not set: {e}")
        return True
    except Exception as e:
        print_error(f"Network configuration error: {e}")
        return False


def get_virtual_machines():
    vms = []
    try:
        result = run_command(["virsh", "list", "--all"], capture_output=True)
        lines = result.stdout.strip().splitlines()
        sep = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("----")), -1
        )
        if sep < 0:
            return []
        for line in lines[sep + 1 :]:
            parts = line.split()
            if len(parts) >= 3:
                vms.append(
                    {"id": parts[0], "name": parts[1], "state": " ".join(parts[2:])}
                )
        return vms
    except Exception as e:
        print_error(f"Error retrieving VMs: {e}")
        return []


def set_vm_autostart(vms):
    print_section("Configuring VM Autostart")
    if not vms:
        print_warning("No VMs found")
        return True
    progress = ProgressBar(len(vms), "VM autostart")
    failed = []
    for vm in vms:
        name = vm["name"]
        try:
            print_step(f"Setting autostart for {name}")
            info = run_command(["virsh", "dominfo", name], capture_output=True)
            if "Autostart:        yes" in info.stdout:
                print_success(f"{name} already set")
            else:
                run_command(["virsh", "autostart", name])
                print_success(f"{name} set to autostart")
        except Exception as e:
            print_error(f"Autostart failed for {name}: {e}")
            failed.append(name)
        progress.update(1)
    if failed:
        print_warning(f"Autostart failed for: {', '.join(failed)}")
        return False
    return True


def start_virtual_machines(vms):
    print_section("Starting Virtual Machines")
    if not vms:
        print_warning("No VMs found")
        return True
    to_start = [vm for vm in vms if vm["state"].lower() != "running"]
    if not to_start:
        print_success("All VMs are running")
        return True
    if not ensure_network_active_before_vm_start():
        print_error("Default network not active")
        return False
    progress = ProgressBar(len(to_start), "VM startup")
    failed = []
    for vm in to_start:
        name = vm["name"]
        try:
            print_step(f"Starting {name}")
            with Spinner(f"Starting {name}"):
                result = run_command(["virsh", "start", name], check=False)
                if result.returncode != 0:
                    print_error(f"Failed to start {name}: {result.stderr}")
                    failed.append(name)
                else:
                    print_success(f"{name} started")
            time.sleep(3)  # Delay between VM starts
        except Exception as e:
            print_error(f"Error starting {name}: {e}")
            failed.append(name)
        progress.update(1)
    if failed:
        print_warning(f"Failed to start: {', '.join(failed)}")
        return False
    return True


def ensure_network_active_before_vm_start():
    print_step("Verifying default network before starting VMs")
    try:
        net_list = run_command(["virsh", "net-list"], capture_output=True)
        for line in net_list.stdout.splitlines():
            if "default" in line and "active" in line:
                print_success("Default network is active")
                return True
        print_warning("Default network inactive; attempting restart")
        return recreate_default_network()
    except Exception as e:
        print_error(f"Network verification error: {e}")
        return False


def fix_storage_permissions(paths):
    print_section("Fixing VM Storage Permissions")
    if not paths:
        print_warning("No storage paths specified")
        return True
    try:
        uid = pwd.getpwnam(VM_OWNER).pw_uid
        gid = grp.getgrnam(VM_GROUP).gr_gid
    except KeyError as e:
        print_error(f"User/group not found: {e}")
        return False
    for path in paths:
        print_step(f"Processing {path}")
        if not os.path.exists(path):
            print_warning(f"{path} does not exist; creating")
            os.makedirs(path, mode=VM_DIR_MODE, exist_ok=True)
        total_items = sum(
            [1 + len(dirs) + len(files) for r, dirs, files in os.walk(path)]
        )
        progress = ProgressBar(total_items, "Updating permissions")
        try:
            os.chown(path, uid, gid)
            os.chmod(path, VM_DIR_MODE)
            progress.update(1)
            for root, dirs, files in os.walk(path):
                for d in dirs:
                    dpath = os.path.join(root, d)
                    try:
                        os.chown(dpath, uid, gid)
                        os.chmod(dpath, VM_DIR_MODE)
                    except Exception as e:
                        print_warning(f"Error on {dpath}: {e}")
                    progress.update(1)
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        os.chown(fpath, uid, gid)
                        os.chmod(fpath, VM_FILE_MODE)
                    except Exception as e:
                        print_warning(f"Error on {fpath}: {e}")
                    progress.update(1)
        except Exception as e:
            print_error(f"Failed on {path}: {e}")
            return False
    print_success("Storage permissions updated")
    return True


def configure_user_groups():
    print_section("Configuring User Group Membership")
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user:
        print_warning("SUDO_USER not set; skipping group config")
        return True
    try:
        pwd.getpwnam(sudo_user)
        grp.getgrnam(LIBVIRT_USER_GROUP)
    except KeyError as e:
        print_error(f"User or group error: {e}")
        return False
    user_groups = [g.gr_name for g in grp.getgrall() if sudo_user in g.gr_mem]
    primary = grp.getgrgid(pwd.getpwnam(sudo_user).pw_gid).gr_name
    if primary not in user_groups:
        user_groups.append(primary)
    if LIBVIRT_USER_GROUP in user_groups:
        print_success(f"{sudo_user} already in {LIBVIRT_USER_GROUP}")
        return True
    try:
        print_step(f"Adding {sudo_user} to {LIBVIRT_USER_GROUP}")
        run_command(["usermod", "-a", "-G", LIBVIRT_USER_GROUP, sudo_user])
        print_success(f"User {sudo_user} added. Please log out/in.")
        return True
    except Exception as e:
        print_error(f"Failed to add user: {e}")
        return False


def verify_virtualization_setup():
    print_section("Verifying Virtualization Setup")
    passed = True
    try:
        svc = run_command(["systemctl", "is-active", "libvirtd"], check=False)
        if svc.stdout.strip() == "active":
            print_success("libvirtd is active")
        else:
            print_error("libvirtd is not active")
            passed = False
    except Exception as e:
        print_error(f"Error checking libvirtd: {e}")
        passed = False

    try:
        net = run_command(["virsh", "net-list"], capture_output=True, check=False)
        if "default" in net.stdout and "active" in net.stdout:
            print_success("Default network is active")
        else:
            print_error("Default network inactive")
            passed = False
    except Exception as e:
        print_error(f"Network check error: {e}")
        passed = False

    try:
        lsmod = run_command(["lsmod"], capture_output=True)
        if "kvm" in lsmod.stdout:
            print_success("KVM modules loaded")
        else:
            print_error("KVM modules missing")
            passed = False
    except Exception as e:
        print_error(f"KVM check error: {e}")
        passed = False

    for path in VM_STORAGE_PATHS:
        key = path
        if os.path.exists(path):
            print_success(f"Storage exists: {path}")
        else:
            print_error(f"Storage missing: {path}")
            try:
                os.makedirs(path, mode=VM_DIR_MODE, exist_ok=True)
                print_success(f"Created storage: {path}")
            except Exception as e:
                print_error(f"Failed to create {path}: {e}")
                passed = False
    if passed:
        print_success("All verification checks passed!")
    else:
        print_warning("Some verification checks failed.")
    return passed


# ------------------------------
# Main Function & Argument Parsing
# ------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Enhanced Virtualization Environment Setup Script",
        epilog="""Examples:
  sudo python3 virt_setup.py             # Run full setup
  sudo python3 virt_setup.py --network   # Only configure network
  sudo python3 virt_setup.py --fix       # Troubleshoot issues
  sudo python3 virt_setup.py --verify    # Verify setup
        """,
    )
    parser.add_argument("--packages", action="store_true", help="Only install packages")
    parser.add_argument("--network", action="store_true", help="Only configure network")
    parser.add_argument(
        "--permissions", action="store_true", help="Only fix storage permissions"
    )
    parser.add_argument(
        "--autostart", action="store_true", help="Only set VM autostart"
    )
    parser.add_argument("--start", action="store_true", help="Only start VMs")
    parser.add_argument("--verify", action="store_true", help="Only verify setup")
    parser.add_argument("--fix", action="store_true", help="Troubleshoot common issues")
    return parser.parse_args()


def main():
    args = parse_arguments()
    run_specific = any(
        [
            args.packages,
            args.network,
            args.permissions,
            args.autostart,
            args.start,
            args.verify,
            args.fix,
        ]
    )
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_header("Enhanced Virtualization Environment Setup")
    print(f"Hostname: {HOSTNAME}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if os.geteuid() != 0:
        print_error("Run this script as root (e.g., using sudo)")
        sys.exit(1)

    if args.fix:
        verify_virtualization_setup()
        sys.exit(0)
    elif args.verify:
        verify_virtualization_setup()
        sys.exit(0)

    if not run_specific or args.packages:
        if not update_system_packages():
            print_warning("Package list update failed")
        if not install_virtualization_packages(VIRTUALIZATION_PACKAGES):
            print_error("Package installation issues encountered")
        if not manage_virtualization_services(VIRTUALIZATION_SERVICES):
            print_warning("Service management issues encountered")

    if not run_specific or args.network:
        for attempt in range(1, 4):
            print_step(f"Network configuration attempt {attempt}")
            if configure_default_network():
                break
            time.sleep(2)
        else:
            print_error("Failed to configure network after multiple attempts")
            recreate_default_network()

    if not run_specific or args.permissions:
        fix_storage_permissions(VM_STORAGE_PATHS)
        configure_user_groups()

    if not run_specific or args.autostart or args.start:
        vms = get_virtual_machines()
        if vms:
            print_success(f"Found {len(vms)} VMs")
            if not run_specific:
                # Optionally update VM network settings here
                pass
            if not run_specific or args.autostart:
                set_vm_autostart(vms)
            if not run_specific or args.start:
                ensure_network_active_before_vm_start()
                start_virtual_machines(vms)
        else:
            print_step("No VMs found")

    if not run_specific:
        verify_virtualization_setup()

    print_header("Setup Complete")
    print_success("Virtualization environment setup complete!")
    print_step(
        "Next steps: log out/in for group changes, run 'virt-manager', and check logs with 'journalctl -u libvirtd'."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup interrupted by user.{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Unhandled error: {e}{Colors.ENDC}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
