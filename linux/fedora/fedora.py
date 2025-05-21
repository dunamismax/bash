#!/usr/bin/env python3

import datetime
import filecmp
import gzip
import logging
import os
import pwd
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Try to import rich, install if missing
try:
    import rich.console
    import rich.logging
    from rich.console import Console
    from rich.logging import RichHandler
except ImportError:
    print("Required 'rich' library not found. Attempting to install...")
    try:
        # Ensure pip is available
        subprocess.check_call([sys.executable, "-m", "ensurepip"])
        # Install rich
        subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
        print("Rich installed successfully. Restarting script...")
        # Re-execute the script
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing 'rich': {e}", file=sys.stderr)
        print("Please install it manually: pip install rich", file=sys.stderr)
        sys.exit(1)

# --- Globals ---
console = Console()
OPERATION_TIMEOUT = 300  # default timeout in seconds
APP_NAME = "Fedora Server Setup & Hardening"
VERSION = "1.0.0"
# Global instance for signal handler cleanup
setup_instance = None

# Simplified status tracking
SETUP_STATUS = {
    "preflight": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "repo_shell": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},  # Retained key, but less relevant now
    "user_custom": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},  # Retained key, but less relevant now
    "certs_perf": {"status": "pending", "message": ""},  # Retained key, but less relevant now
    "permissions": {"status": "pending", "message": ""},
    "cleanup_final": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}


# --- Configuration ---
@dataclass
class Config:
    LOG_FILE: str = "/var/log/fedora_setup.log"
    # Attempt to get the primary non-root user, fallback to 'fedora'
    USERNAME: str = field(default_factory=lambda: os.getenv("SUDO_USER", "fedora"))
    USER_HOME: Path = field(
        default_factory=lambda: Path(os.path.expanduser(f"~{os.getenv('SUDO_USER', 'fedora')}"))
    )

    # --- Fedora Package Equivalents (Best Effort) ---
    # Note: This list needs careful review for your specific Fedora version and needs.
    # Some Ubuntu packages might not have direct Fedora equivalents or might be part of larger groups.
    PACKAGES: List[str] = field(
        default_factory=lambda: [
            # Shells and editors
            "bash",
            "vim-enhanced",
            "nano",
            "tmux",
            "screen",
            "zsh",
            # System monitoring and performance analysis
            "tree",
            "mtr",
            "iotop",
            "sysstat",
            "powertop",
            "htop",
            "atop",
            "glances",
            "ncdu",
            "dstat",
            "nmon",
            "iftop",
            "nethogs",
            "bmon",
            "bpytop",
            "btop",
            "stress-ng",
            # Network and security
            "git",
            "openssh-server",
            "firewalld",
            "fail2ban",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "bash-completion",
            "net-tools",
            "nmap",
            "tcpdump",
            "iptables",
            "whois",
            "nftables",
            "openssl",
            "lynis",
            "sshfs",
            "openvpn",
            "wireguard-tools",
            "ethtool",
            "ca-certificates",
            "gnupg2",
            "gpg",
            "certbot",
            "acl",
            "policycoreutils-python-utils",  # for semanage, part of SELinux tools
            # Core utilities
            "python3",
            "python3-pip",
            "python3-venv",
            "cronie",
            "at",
            "parallel",
            "moreutils",
            "util-linux",
            "kbd",
            "rpmdevtools",  # debsums equivalent concept
            "dnf-utils",
            "bind-utils",  # dnsutils equivalent
            "dnf-plugins-core",  # provides config-manager
            "glibc-langpack-en",  # locales equivalent (install specific langpacks as needed)
            "systemd-timesyncd",  # Usually part of systemd
            # Modern shell utilities
            "ripgrep",
            "fd-find",
            "bat",
            "fzf",
            "tldr",
            "jq",
            "ncurses-term",
            "grc",
            "ranger",
            "thefuck",
            "neofetch",
            "byobu",
            "zoxide",
            "direnv",
            "micro",
            "hexyl",
            "sd",
            "duf",
            # Development tools
            "gcc",
            "gcc-c++",
            "make",
            "cmake",
            "python3-devel",
            "openssl-devel",
            "ShellCheck",
            "libffi-devel",
            "zlib-devel",
            "readline-devel",
            "bzip2-devel",
            "ncurses-devel",
            "pkgconfig",
            "man-pages",
            "git-extras",
            "clang",
            "llvm",
            "golang",
            "rust",
            "cargo",
            "gdb",
            "strace",
            "ltrace",
            # Network utilities
            "traceroute",
            "iproute",
            "iputils",
            "dnsmasq",
            "ipcalc",
            "nmap-ncat",  # netcat-openbsd equivalent
            "socat",
            "bridge-utils",
            "nload",
            "oping",
            "arping",
            "httpie",
            "speedtest-cli",
            "aria2",
            "mosh",
            "tcpflow",
            "tcpreplay",
            "wireshark-cli",  # tshark
            "vnstat",
            "iptraf-ng",
            "mitmproxy",
            "lldpad",  # lldpd equivalent
            # Container and development
            "podman",
            "buildah",
            "skopeo",
            "nodejs",
            "npm",
            "autoconf",
            "automake",
            "libtool",
            "docker-ce",
            "docker-compose-plugin",  # Use Docker's repo for latest docker.io/compose
            "lxc",
            "ansible-core",
            "cloud-init",
            # Debugging and development utilities
            "valgrind",
            "lsof",
            "psmisc",
            "pv",
            "lshw",
            "hwinfo",
            "dmidecode",
            "sysfsutils",
            "inxi",
            "logrotate",
            "logwatch",
            "smartmontools",
            "nvme-cli",
            # Database clients
            "mariadb",
            "postgresql",
            "sqlite",
            "redis",  # redis-tools merged
            "mysql-community-client",  # From MySQL repo typically
            # Virtualization
            "qemu-kvm",
            "libvirt-daemon-kvm",
            "virt-manager",
            "virt-viewer",
            "virt-top",
            "libosinfo",
            "libguestfs-tools",
            # File compression and archiving
            "unzip",
            "zip",
            "tar",
            "pigz",
            "lz4",
            "xz",
            "bzip2",
            "p7zip",
            "p7zip-plugins",
            "zstd",
            "gzip",
            "cpio",
            "pax",
            "rzip",
            "arj",
            "unrar",
            "lrzip",  # lzop alternative/superset
            # Terminal multiplexers and utilities
            "mc",
            "multitail",
            "ccze",
            "colordiff",
            "progress",
            "rlwrap",
            "reptyr",
            "expect",
            "dialog",
            # Text processing
            "yq",
            "csvkit",
            "gawk",
            "dos2unix",
            "wdiff",
            "diffutils",
            "pandoc",
            "highlight",
            "groff",
            "xmlstarlet",
            "html-xml-utils",
            "libxslt",  # xsltproc
            # Backup and sync
            "restic",
            "duplicity",
            "borgbackup",
            "rclone",
            "rsnapshot",
            "rdiff-backup",
            "syncthing",
            "unison",
            "backintime",
            "timeshift",
            # Monitoring and configuration management
            "prometheus-node_exporter",
            "collectd",
            "nagios-plugins-all",
            "puppet-agent",
            "cfengine",
            # Web servers and proxies
            "nginx",
            "httpd-tools",  # apache2-utils equivalent
            "haproxy",
            "squid",
            "lighttpd",
            "tinyproxy",
        ]
    )

    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "PermitRootLogin": "no",
            "PasswordAuthentication": "yes",  # Consider changing to 'no' if using keys
            "X11Forwarding": "no",
            "MaxAuthTries": "3",
            "ClientAliveInterval": "300",
            "ClientAliveCountMax": "3",
            "UsePAM": "yes",  # Common default on Fedora
            "Subsystem": "sftp /usr/libexec/openssh/sftp-server",  # Fedora path
        }
    )

    FIREWALL_SERVICES: List[str] = field(
        default_factory=lambda: ["ssh", "http", "https"]  # Use firewalld service names
    )
    # FIREWALL_PORTS: List[str] = field(default_factory=lambda: ["22/tcp", "80/tcp", "443/tcp"]) # Alternative if services aren't defined

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Logging Setup ---
def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fedora_setup")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplication if re-run
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Console Handler (Rich)
    console_handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Set log file permissions (best effort)
    try:
        # Get current owner/group of parent dir, default to root:root
        stat_info = log_file.parent.stat()
        uid = stat_info.st_uid
        gid = stat_info.st_gid
        os.chown(log_file, uid, gid)
        os.chmod(log_file, 0o640)  # Read/Write for owner, Read for group
    except Exception as e:
        logger.warning(f"Could not set permissions/owner on log file {log_file}: {e}")

    return logger


# --- Synchronous Helper Functions ---
def run_command(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = True,  # Default to text=True for easier handling
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Runs a command synchronously using subprocess.run."""
    logger = logging.getLogger("fedora_setup")
    logger.debug(f"Running command: {' '.join(cmd)}")
    try:
        process = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            check=check,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        if process.stdout and capture_output:
            logger.debug(f"Command stdout: {process.stdout.strip()}")
        if process.stderr and capture_output:
            logger.debug(f"Command stderr: {process.stderr.strip()}")
        return process
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            logger.error(f"Stdout: {e.stdout.strip()}")
        if e.stderr:
            logger.error(f"Stderr: {e.stderr.strip()}")
        if check:  # Only raise if check=True, otherwise return the failed process
            raise
        else:
            # Return the CompletedProcess object even on failure if check=False
            return subprocess.CompletedProcess(
                args=e.args,
                returncode=e.returncode,
                stdout=e.stdout,
                stderr=e.stderr,
            )
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise Exception(f"Command timed out: {' '.join(cmd)}") from e
    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd[0]} - {e}")
        raise
    except Exception as e:
        logger.error(f"Error running command {' '.join(cmd)}: {e}")
        raise


def command_exists(cmd: str) -> bool:
    """Checks if a command exists using shutil.which."""
    return shutil.which(cmd) is not None


def download_file(url: str, dest: Union[str, Path], timeout: int = 300) -> None:
    """Downloads a file using wget, curl, or fallback to urllib."""
    dest = Path(dest)
    logger = logging.getLogger("fedora_setup")
    if dest.exists():
        logger.info(f"File {dest} already exists; skipping download.")
        return

    logger.info(f"Downloading {url} to {dest}...")
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        if command_exists("wget"):
            run_command(
                [
                    "wget",
                    "-q",
                    "--show-progress",
                    "-T",
                    str(timeout),
                    "--tries=3",
                    url,
                    "-O",
                    str(dest),
                ],
                check=True,
                timeout=timeout + 10,  # Give a bit more time for the process itself
            )
        elif command_exists("curl"):
            run_command(
                [
                    "curl",
                    "-L",
                    "--connect-timeout",
                    str(timeout),
                    "--retry",
                    "3",
                    "-o",
                    str(dest),
                    url,
                ],
                check=True,
                timeout=timeout + 10,
            )
        else:
            logger.info("wget/curl not found, using Python's urllib...")

            # Basic progress reporting for urllib
            def report_hook(block_num, block_size, total_size):
                downloaded = block_num * block_size
                if total_size > 0:
                    percent = downloaded * 100 / total_size
                    print(f"  Download progress: {min(percent, 100):.1f}%", end="\r")
                else:
                    print(f"  Downloaded: {downloaded / 1024:.1f} KB", end="\r")

            urllib.request.urlretrieve(url, str(dest), reporthook=report_hook)
            print()  # Newline after progress
        logger.info(f"Download complete: {dest}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"Download failed: {e}")
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass  # Ignore errors during cleanup
        raise


def run_with_progress(
    description: str,
    func: callable,
    *args: Any,
    task_name: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Runs a synchronous function, logs progress, and updates status."""
    if task_name and task_name in SETUP_STATUS:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }
    logger = logging.getLogger("fedora_setup")
    logger.info(f"Starting: {description}")
    start = time.time()
    try:
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"✓ {description} completed in {elapsed:.2f}s")
        if task_name and task_name in SETUP_STATUS:
            SETUP_STATUS[task_name] = {
                "status": "success",
                "message": f"Completed in {elapsed:.2f}s",
            }
        return result
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"✗ {description} failed in {elapsed:.2f}s: {e}")
        if task_name and task_name in SETUP_STATUS:
            SETUP_STATUS[task_name] = {
                "status": "failed",
                "message": f"Failed after {elapsed:.2f}s: {str(e)}",
            }
        raise  # Re-raise the exception to potentially halt the script


# --- Main Setup Class ---
class FedoraServerSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        # Ensure USER_HOME exists and get logger
        try:
            self.config.USER_HOME.mkdir(parents=True, exist_ok=True)
            # Ensure correct ownership if run as root with SUDO_USER
            if os.geteuid() == 0 and os.getenv("SUDO_USER"):
                try:
                    user_info = pwd.getpwnam(os.getenv("SUDO_USER"))
                    os.chown(self.config.USER_HOME, user_info.pw_uid, user_info.pw_gid)
                except (KeyError, OSError) as e:
                    print(
                        f"Warning: Could not set owner for {self.config.USER_HOME}: {e}",
                        file=sys.stderr,
                    )
        except OSError as e:
            print(
                f"Error creating or accessing user home {self.config.USER_HOME}: {e}",
                file=sys.stderr,
            )
            # Log file might not be setup yet, so print to stderr

        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self.logger.info(f"Using Username: {self.config.USERNAME}")
        self.logger.info(f"Using User Home: {self.config.USER_HOME}")
        if not self.config.USER_HOME.is_dir():
            self.logger.error(
                f"User home directory {self.config.USER_HOME} does not exist or is not accessible."
            )
            # Consider exiting if home dir is crucial and non-existent

    def print_section(self, title: str) -> None:
        """Prints a formatted section header to the log."""
        self.logger.info(f"--- {title} ---")

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Creates a timestamped backup of a file."""
        file_path = Path(file_path)
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = file_path.with_suffix(file_path.suffix + f".bak.{timestamp}")
        try:
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Backed up {file_path} to {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.warning(f"Failed to backup {file_path}: {e}")
            return None

    def _compress_log(self, log_path: Path, rotated_path: str) -> None:
        """Compresses the log file using gzip."""
        try:
            with open(log_path, "rb") as f_in, gzip.open(rotated_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            # Clear the original log file after successful compression
            open(log_path, "w").close()
            self.logger.info(f"Log compressed to {rotated_path}")
            # Set permissions on rotated log (best effort)
            try:
                os.chmod(rotated_path, 0o640)
            except OSError as e:
                self.logger.warning(f"Could not set permissions on {rotated_path}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to compress log {log_path} to {rotated_path}: {e}")

    def rotate_logs(self, log_file: Optional[str] = None) -> bool:
        """Rotates and compresses the main log file."""
        if log_file is None:
            log_file = self.config.LOG_FILE
        log_path = Path(log_file)
        if not log_path.is_file() or log_path.stat().st_size == 0:
            self.logger.info(f"Log file {log_path} is empty or does not exist. Skipping rotation.")
            return False

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated_path = f"{log_path}.{timestamp}.gz"
        self.logger.info(f"Attempting to rotate log file to {rotated_path}")

        # Close all handlers associated with the logger before rotating
        for handler in self.logger.handlers[:]:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path:
                handler.close()
                self.logger.removeHandler(handler)

        try:
            self._compress_log(log_path, rotated_path)
            # Re-add the file handler to the logger so logging can continue
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            # Attempt to re-add handler even if rotation failed
            try:
                file_handler = logging.FileHandler(log_path)
                file_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter(
                    "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception as he:
                self.logger.error(f"Failed to re-add log handler after rotation error: {he}")
            return False

    def cleanup(self) -> None:
        """Performs cleanup actions before exiting."""
        self.logger.info("Performing cleanup...")
        try:
            tmp = Path(tempfile.gettempdir())
            for item in tmp.glob("fedora_setup_*"):
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    self.logger.warning(f"Failed to clean up temporary item {item}: {e}")

            # Rotate logs as the last step
            self.rotate_logs()

            self.logger.info("Cleanup completed.")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

    def has_internet_connection(self) -> bool:
        """Checks for internet connectivity by pinging Google's DNS."""
        try:
            # Use -W 1 for a 1-second timeout per ping attempt
            run_command(
                ["ping", "-c", "1", "-W", "1", "8.8.8.8"],
                capture_output=True,
                check=True,
                timeout=5,  # Overall timeout for the command
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            # Try pinging Fedora's website as a fallback
            try:
                run_command(
                    ["ping", "-c", "1", "-W", "1", "fedoraproject.org"],
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                self.logger.warning("Could not reach 8.8.8.8 or fedoraproject.org via ping.")
                return False
        except Exception as e:
            self.logger.error(f"Unexpected error during network check: {e}")
            return False

    # --- Phase Methods ---

    def phase_preflight(self) -> bool:
        """Runs initial checks and backups."""
        self.print_section("Pre-flight Checks & Backups")
        try:
            run_with_progress(
                "Checking for root privileges", self.check_root, task_name="preflight"
            )
            run_with_progress(
                "Checking network connectivity", self.check_network, task_name="preflight"
            )
            run_with_progress(
                "Verifying Fedora distribution", self.check_fedora, task_name="preflight"
            )
            run_with_progress(
                "Saving configuration snapshot", self.save_config_snapshot, task_name="preflight"
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            SETUP_STATUS["preflight"]["status"] = "failed"
            SETUP_STATUS["preflight"]["message"] = f"Failed: {e}"
            return False

    def check_root(self) -> None:
        """Ensures the script is run as root."""
        if os.geteuid() != 0:
            self.logger.critical("Script must be run as root (e.g., using sudo).")
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    def check_network(self) -> None:
        """Verifies internet connectivity."""
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity detected. Cannot proceed.")
            raise ConnectionError("Network connection check failed.")

    def check_fedora(self) -> None:
        """Checks if the system is Fedora."""
        try:
            if Path("/etc/os-release").is_file():
                with open("/etc/os-release", "r") as f:
                    os_release_content = f.read()
                if "ID=fedora" in os_release_content:
                    pretty_name = "Fedora Linux"
                    for line in os_release_content.splitlines():
                        if line.startswith("PRETTY_NAME="):
                            pretty_name = line.split("=", 1)[1].strip('"')
                            break
                    self.logger.info(f"Detected Fedora: {pretty_name}")
                else:
                    self.logger.warning(
                        "This does not appear to be a Fedora system. Functionality may be affected."
                    )
            else:
                self.logger.warning("/etc/os-release not found. Cannot verify distribution.")
        except Exception as e:
            self.logger.warning(f"Could not verify distribution: {e}")

    def save_config_snapshot(self) -> Optional[str]:
        """Creates a backup tarball of important configuration files."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups/fedora_setup_snapshot")
        backup_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = backup_dir / f"fedora_config_snapshot_{timestamp}.tar.gz"
        files_to_backup = [
            "/etc/dnf/dnf.conf",
            "/etc/fstab",
            "/etc/default/grub",  # Check if still relevant or if /etc/grub2.cfg /etc/grub.d/ is better
            "/etc/sysconfig/grub",  # Older Fedora?
            "/etc/hosts",
            "/etc/ssh/sshd_config",
            "/etc/sysconfig/network-scripts/",  # If using traditional networking
            "/etc/NetworkManager/system-connections/",  # If using NetworkManager
            "/etc/firewalld/firewalld.conf",
            "/etc/firewalld/zones/",
            "/etc/selinux/config",
            "/etc/fail2ban/jail.conf",
            "/etc/fail2ban/jail.local",  # If exists
            "/etc/fail2ban/jail.d/",
        ]
        files_added_count = 0
        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                for config_path_str in files_to_backup:
                    config_path = Path(config_path_str)
                    if config_path.exists():
                        try:
                            tar.add(
                                str(config_path),
                                arcname=config_path.relative_to("/"),
                                recursive=True,
                            )
                            self.logger.debug(f"Added {config_path} to snapshot.")
                            files_added_count += 1
                        except Exception as tar_e:
                            self.logger.warning(f"Could not add {config_path} to snapshot: {tar_e}")
                    else:
                        self.logger.debug(f"Skipping non-existent path for snapshot: {config_path}")

            if files_added_count > 0:
                self.logger.info(
                    f"Configuration snapshot saved: {snapshot_file} ({files_added_count} items included)"
                )
                return str(snapshot_file)
            else:
                self.logger.warning("No configuration files found or added for snapshot.")
                # Clean up empty tar file
                if snapshot_file.exists():
                    snapshot_file.unlink()
                return None
        except Exception as e:
            self.logger.error(f"Failed to create config snapshot: {e}")
            # Clean up potentially broken tar file
            if snapshot_file.exists():
                snapshot_file.unlink()
            return None

    def phase_system_update(self) -> bool:
        """Updates repositories, upgrades packages, and installs configured packages."""
        self.print_section("System Update & Package Installation")
        status = True
        try:
            run_with_progress(
                "Checking for DNF updates", self.check_updates, task_name="system_update"
            )
            run_with_progress(
                "Upgrading system packages", self.upgrade_system, task_name="system_update"
            )
            success, failed = run_with_progress(
                "Installing required packages", self.install_packages, task_name="system_update"
            )
            if failed:
                self.logger.warning(
                    f"{len(failed)} package(s) failed to install: {', '.join(failed)}"
                )
                # Decide if this is critical
                if len(failed) > len(self.config.PACKAGES) * 0.2:  # Example: fail if > 20% failed
                    self.logger.error(
                        "Too many packages failed to install. Aborting further package-dependent steps might be necessary."
                    )
                    # status = False # Optionally mark the phase as failed
        except Exception as e:
            self.logger.error(f"System update phase failed: {e}")
            status = False
        return status

    def check_updates(self) -> bool:
        """Runs dnf check-update."""
        try:
            # dnf check-update exits with 100 if updates are available, 0 if not, 1 on error.
            # We don't use check=True here for that reason.
            result = run_command(["dnf", "check-update"], check=False, capture_output=True)
            if result.returncode == 0:
                self.logger.info("System is up-to-date.")
            elif result.returncode == 100:
                self.logger.info("Updates are available.")
            else:
                self.logger.error(
                    f"Failed to check for updates (Exit Code: {result.returncode}). Stderr: {result.stderr.strip()}"
                )
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error checking DNF updates: {e}")
            return False

    def upgrade_system(self) -> bool:
        """Upgrades system packages using dnf."""
        try:
            self.logger.info("Upgrading system packages using DNF...")
            run_command(["dnf", "upgrade", "-y"], timeout=1800)  # Longer timeout for upgrades
            self.logger.info("System upgrade complete.")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"System upgrade failed: {e}")
            return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
        """Installs the configured list of packages using dnf."""
        self.logger.info("Checking and installing required packages...")
        installed_count = 0
        missing = []
        already_installed = []
        failed = []

        # Check installed status
        for pkg in self.config.PACKAGES:
            try:
                # rpm -q exits 0 if installed, non-zero otherwise
                run_command(["rpm", "-q", pkg], capture_output=True, check=True)
                already_installed.append(pkg)
                installed_count += 1
            except subprocess.CalledProcessError:
                missing.append(pkg)
            except Exception as e:
                self.logger.warning(f"Could not check status of package {pkg}: {e}")
                missing.append(pkg)  # Assume missing if check fails

        self.logger.info(f"{installed_count} packages already installed.")

        if not missing:
            self.logger.info("All required packages are already installed.")
            return already_installed, []

        # Install missing packages in batches
        batch_size = 20  # DNF handles larger batches better than apt typically
        batches = [missing[i : i + batch_size] for i in range(0, len(missing), batch_size)]
        self.logger.info(
            f"Attempting to install {len(missing)} packages in {len(batches)} batches..."
        )

        success = list(already_installed)  # Start success list with already installed

        for i, batch in enumerate(batches):
            self.logger.info(f"Installing batch {i + 1}/{len(batches)}: {' '.join(batch)}")
            try:
                # --setopt=install_weak_deps=False is similar to --no-install-recommends
                run_command(
                    ["dnf", "install", "-y", "--setopt=install_weak_deps=False"] + batch,
                    timeout=600,  # Timeout per batch
                )
                # Assume success for the batch if dnf didn't raise error
                success.extend(batch)
                self.logger.info(f"Batch {i + 1} installed successfully.")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.logger.warning(
                    f"Failed to install batch {i + 1}: {e}. Attempting individual installs for this batch."
                )
                # Try installing packages individually within the failed batch
                for pkg in batch:
                    try:
                        self.logger.info(f"Attempting individual install: {pkg}")
                        run_command(
                            ["dnf", "install", "-y", "--setopt=install_weak_deps=False", pkg],
                            timeout=120,
                        )
                        success.append(pkg)
                        self.logger.info(f"Successfully installed {pkg} individually.")
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as ie:
                        self.logger.error(f"Failed to install package {pkg} individually: {ie}")
                        failed.append(pkg)
            except Exception as e:
                self.logger.error(f"Unexpected error installing batch {i + 1}: {e}")
                # Assume all in batch failed on unexpected error
                failed.extend(batch)

            # Optional: Small pause between batches
            # time.sleep(1)

        self.logger.info(
            f"Package installation summary: {len(success)} succeeded, {len(failed)} failed."
        )
        if failed:
            self.logger.warning(f"Failed packages: {', '.join(failed)}")
        return success, failed

    def phase_repo_shell_setup(self) -> bool:
        """Clones Git repos and sets up shell configurations."""
        self.print_section("Repository & Shell Setup")
        status = True
        try:
            run_with_progress(
                "Setting up GitHub repositories", self.setup_repos, task_name="repo_shell"
            )
            run_with_progress(
                "Copying shell configurations", self.copy_shell_configs, task_name="repo_shell"
            )
            run_with_progress(
                "Setting default shell to bash", self.set_bash_shell, task_name="repo_shell"
            )
        except Exception as e:
            self.logger.error(f"Repo & Shell setup phase failed: {e}")
            status = False
        return status

    def _get_user_credentials(self) -> Tuple[Optional[int], Optional[int]]:
        """Gets UID and GID for the configured user."""
        try:
            user_info = pwd.getpwnam(self.config.USERNAME)
            return user_info.pw_uid, user_info.pw_gid
        except KeyError:
            self.logger.error(f"User '{self.config.USERNAME}' not found.")
            return None, None

    def setup_repos(self) -> bool:
        """Clones or updates specific Git repositories."""
        gh_dir = self.config.USER_HOME / "github"
        uid, gid = self._get_user_credentials()
        if uid is None or gid is None:
            self.logger.error("Cannot setup repos without valid user credentials.")
            return False

        try:
            # Create github dir owned by user
            gh_dir.mkdir(exist_ok=True)
            os.chown(gh_dir, uid, gid)
        except OSError as e:
            self.logger.error(f"Failed to create or set ownership for {gh_dir}: {e}")
            return False

        all_success = True
        repos = ["bash", "python"]  # Add other repo names if needed

        for repo in repos:
            repo_dir = gh_dir / repo
            repo_url = f"https://github.com/dunamismax/{repo}.git"  # Adjust username if needed

            # Run git operations as the target user if possible (more robust for permissions)
            # This requires sudo config to allow running git as the user, or running the script as the user initially (not root)
            # Simplified approach: run as root and chown afterwards
            git_env = os.environ.copy()
            git_env["HOME"] = str(self.config.USER_HOME)  # Help git find user's config if needed

            try:
                if (repo_dir / ".git").is_dir():
                    self.logger.info(f"Repository '{repo}' exists; pulling updates...")
                    # Try pulling as the user first, then root as fallback? complex. Stick to root + chown.
                    run_command(["git", "pull"], check=True, cwd=repo_dir, env=git_env)
                else:
                    self.logger.info(f"Cloning repository '{repo}' from {repo_url}...")
                    run_command(["git", "clone", repo_url, str(repo_dir)], check=True, env=git_env)
                    # Chown after clone
                    run_command(
                        ["chown", "-R", f"{uid}:{gid}", str(repo_dir)], check=False
                    )  # Best effort chown

            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ) as e:
                self.logger.warning(f"Failed git operation for repository '{repo}': {e}")
                all_success = False
            except Exception as e:
                self.logger.error(f"Unexpected error setting up repo {repo}: {e}")
                all_success = False

        # Final chown on the whole directory just in case
        try:
            run_command(["chown", "-R", f"{uid}:{gid}", str(gh_dir)], check=False)
        except Exception as e:
            self.logger.warning(f"Final chown on {gh_dir} failed: {e}")
            # Don't mark as overall failure for just the final chown

        return all_success

    def copy_shell_configs(self) -> bool:
        """Copies dotfiles (.bashrc, .profile) to user and root homes."""
        # Define potential source directories in order of preference
        source_base = self.config.USER_HOME / "github" / "bash" / "linux"
        potential_sources = [
            source_base / "fedora" / "dotfiles",
            source_base / "debian" / "dotfiles",  # Fallback
            source_base / "dotfiles",  # Generic fallback
        ]

        source_dir = None
        for src in potential_sources:
            if src.is_dir():
                self.logger.info(f"Using dotfiles source: {src}")
                source_dir = src
                break

        if not source_dir:
            self.logger.error(f"No suitable dotfiles source directory found under {source_base}.")
            return False

        # Get user credentials
        user_uid, user_gid = self._get_user_credentials()
        if user_uid is None or user_gid is None:
            self.logger.error("Cannot copy shell configs without valid user credentials.")
            return False

        destination_map = {
            self.config.USER_HOME: (user_uid, user_gid),
            Path("/root"): (0, 0),  # Root user UID/GID
        }
        overall_success = True

        for file_name in [".bashrc", ".profile"]:
            src_file = source_dir / file_name
            if not src_file.is_file():
                self.logger.warning(f"Source file {src_file} not found; skipping.")
                continue

            for dest_dir, (dest_uid, dest_gid) in destination_map.items():
                dest_file = dest_dir / file_name
                try:
                    # Check if update is needed
                    needs_copy = True
                    if dest_file.is_file():
                        if filecmp.cmp(str(src_file), str(dest_file), shallow=False):
                            self.logger.info(f"File {dest_file} is already up-to-date.")
                            needs_copy = False
                        else:
                            # Backup existing file before overwriting
                            self.backup_file(dest_file)

                    if needs_copy:
                        shutil.copy2(src_file, dest_file)
                        os.chown(dest_file, dest_uid, dest_gid)
                        # Set basic permissions (e.g., 644)
                        os.chmod(dest_file, 0o644)
                        self.logger.info(f"Copied {src_file.name} to {dest_file}")

                except Exception as e:
                    self.logger.warning(f"Failed to copy {src_file.name} to {dest_file}: {e}")
                    overall_success = False

        return overall_success

    def set_bash_shell(self) -> bool:
        """Sets the default shell to /bin/bash for the configured user."""
        bash_path = "/bin/bash"
        if not command_exists("bash"):
            self.logger.info("Bash not found; attempting to install...")
            try:
                run_command(["dnf", "install", "-y", "bash"], check=True)
                if not Path(bash_path).is_file():
                    self.logger.error(
                        "Bash installation reported success, but not found at /bin/bash."
                    )
                    return False
            except Exception as e:
                self.logger.error(f"Bash installation failed: {e}")
                return False

        # Ensure bash is listed in /etc/shells
        shells_file = Path("/etc/shells")
        try:
            if shells_file.is_file():
                content = shells_file.read_text()
                if f"{bash_path}\n" not in content:
                    self.logger.info(f"Adding {bash_path} to {shells_file}")
                    with shells_file.open("a") as f:
                        f.write(f"{bash_path}\n")
            else:
                self.logger.warning(f"{shells_file} not found. Creating it.")
                shells_file.write_text(f"{bash_path}\n")
        except Exception as e:
            self.logger.warning(f"Failed to update {shells_file}: {e}. Shell change might fail.")
            # Don't necessarily return False here, let chsh try

        # Change the user's shell
        try:
            run_command(["chsh", "-s", bash_path, self.config.USERNAME], check=True)
            self.logger.info(f"Default shell for user '{self.config.USERNAME}' set to {bash_path}.")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to set default shell for '{self.config.USERNAME}': {e}")
            return False

    def phase_security_hardening(self) -> bool:
        """Configures SSH, Firewall (firewalld), Fail2ban, and checks SELinux."""
        self.print_section("Security Hardening")
        status = True
        try:
            run_with_progress("Configuring SSH", self.configure_ssh, task_name="security")
            run_with_progress(
                "Configuring Firewall (firewalld)", self.configure_firewall, task_name="security"
            )
            run_with_progress("Configuring Fail2ban", self.configure_fail2ban, task_name="security")
            run_with_progress("Checking SELinux Status", self.check_selinux, task_name="security")
        except Exception as e:
            self.logger.error(f"Security hardening phase failed: {e}")
            status = False
        return status

    def _ensure_service_enabled(self, service_name: str) -> bool:
        """Ensures a systemd service is enabled and running."""
        try:
            self.logger.info(f"Ensuring service '{service_name}' is enabled and active...")
            run_command(["systemctl", "enable", service_name], check=True)
            # Use restart to ensure latest config is loaded, start if not running
            run_command(["systemctl", "restart", service_name], check=True)
            # Verify it's active
            run_command(["systemctl", "is-active", "--quiet", service_name], check=True)
            self.logger.info(f"Service '{service_name}' is active.")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to enable/start/verify service '{service_name}': {e}")
            # Check status for more details
            run_command(["systemctl", "status", service_name], check=False, capture_output=True)
            return False

    def configure_ssh(self) -> bool:
        """Configures the SSH daemon."""
        ssh_service = "sshd"  # Service name on Fedora
        # Ensure OpenSSH server is installed
        if not command_exists("sshd"):
            self.logger.info("openssh-server not found. Installing...")
            try:
                run_command(["dnf", "install", "-y", "openssh-server"], check=True)
            except Exception as e:
                self.logger.error(f"Failed to install openssh-server: {e}")
                return False

        # Ensure service is running
        if not self._ensure_service_enabled(ssh_service):
            self.logger.warning("SSH service is not running after attempting enable/start.")
            # Continue to config update, restart will be attempted again

        sshd_config_path = Path("/etc/ssh/sshd_config")
        if not sshd_config_path.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config_path}")
            return False

        self.backup_file(sshd_config_path)

        try:
            # Read existing config
            lines = sshd_config_path.read_text().splitlines()
            new_lines = []
            config_keys_updated = set()

            # Update existing lines or comment them out if we provide a new value
            for line in lines:
                stripped_line = line.strip()
                updated = False
                if not stripped_line or stripped_line.startswith("#"):
                    new_lines.append(line)  # Keep comments and blank lines
                    continue

                parts = stripped_line.split(None, 1)
                key = parts[0]

                if key in self.config.SSH_CONFIG:
                    new_value = f"{key} {self.config.SSH_CONFIG[key]}"
                    if stripped_line != new_value:
                        self.logger.info(f"Updating SSH config: '{stripped_line}' -> '{new_value}'")
                        new_lines.append(new_value)
                        config_keys_updated.add(key)
                    else:
                        new_lines.append(line)  # Keep unchanged line
                        config_keys_updated.add(key)  # Mark as handled
                    updated = True

                if not updated:
                    new_lines.append(line)  # Keep lines not in our config

            # Add any keys from our config that were not found in the file
            for key, value in self.config.SSH_CONFIG.items():
                if key not in config_keys_updated:
                    new_line = f"{key} {value}"
                    self.logger.info(f"Adding SSH config: '{new_line}'")
                    new_lines.append(new_line)

            # Write the modified config back
            sshd_config_path.write_text("\n".join(new_lines) + "\n")

            # Check syntax before restarting
            self.logger.info("Checking SSH configuration syntax...")
            run_command(["sshd", "-t"], check=True)

            # Restart SSH service to apply changes
            self.logger.info("Restarting SSH service...")
            run_command(["systemctl", "restart", ssh_service], check=True)

            self.logger.info("SSH configuration updated and service restarted.")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, IOError) as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            self.logger.warning("Restoring SSH config from backup might be necessary.")
            # Optional: Attempt to restore backup automatically? Risky.
            return False

    def configure_firewall(self) -> bool:
        """Configures firewalld."""
        fw_service = "firewalld"
        if not command_exists("firewall-cmd"):
            self.logger.info("firewalld not found. Installing...")
            try:
                run_command(["dnf", "install", "-y", "firewalld"], check=True)
            except Exception as e:
                self.logger.error(f"Failed to install firewalld: {e}")
                return False

        if not self._ensure_service_enabled(fw_service):
            self.logger.error("Firewalld service could not be started. Cannot configure firewall.")
            return False

        try:
            self.logger.info("Configuring firewalld rules (using default public zone)...")
            # Add services permanently
            for service in self.config.FIREWALL_SERVICES:
                self.logger.info(f"Allowing service: {service}")
                run_command(["firewall-cmd", "--permanent", "--add-service", service], check=True)

            # Add specific ports permanently (if FIREWALL_PORTS is used)
            # for port in self.config.FIREWALL_PORTS:
            #     self.logger.info(f"Allowing port: {port}")
            #     run_command(["firewall-cmd", "--permanent", "--add-port", port], check=True)

            # Reload firewalld to apply permanent rules
            self.logger.info("Reloading firewalld configuration...")
            run_command(["firewall-cmd", "--reload"], check=True)

            # Log current rules (optional)
            self.logger.info("Current firewalld rules (public zone):")
            run_command(
                ["firewall-cmd", "--list-all"], check=False, capture_output=True
            )  # Log output

            self.logger.info("Firewalld configured successfully.")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to configure firewalld: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        """Configures and enables Fail2ban."""
        f2b_service = "fail2ban"
        if not command_exists("fail2ban-client"):
            self.logger.info("Fail2ban not found. Installing...")
            try:
                run_command(
                    ["dnf", "install", "-y", "fail2ban", "fail2ban-systemd"], check=True
                )  # Include systemd backend support
            except Exception as e:
                self.logger.error(f"Failed to install Fail2ban: {e}")
                return False

        jail_local_path = Path("/etc/fail2ban/jail.local")
        jail_d_dir = Path("/etc/fail2ban/jail.d")
        sshd_conf_path = jail_d_dir / "sshd.local"  # Use jail.d for overrides

        # Create jail.d directory if it doesn't exist
        jail_d_dir.mkdir(parents=True, exist_ok=True)

        # Basic configuration for SSH in sshd.local
        # References /var/log/secure for Fedora's SSH logs
        # Uses systemd backend
        sshd_config_content = (
            "[sshd]\n"
            "enabled = true\n"
            "port = ssh\n"
            # "logpath = %(sshd_log)s\n" # Uses defaults which should find /var/log/secure
            "backend = systemd\n"  # Explicitly use systemd backend
            "maxretry = 3\n"
            "bantime = 10m\n"  # Example: 10 minutes
            "findtime = 10m\n"
        )

        # Optionally create a general jail.local for DEFAULT settings if needed
        # jail_local_content = (
        #     "[DEFAULT]\n"
        #     "bantime = 600\n"
        #     "findtime = 600\n"
        #     "maxretry = 5\n"
        #     # Add other defaults here if desired
        # )
        # if not jail_local_path.exists():
        #      self.logger.info(f"Creating default {jail_local_path}")
        #      jail_local_path.write_text(jail_local_content)

        try:
            if sshd_conf_path.exists():
                self.backup_file(sshd_conf_path)
            self.logger.info(f"Writing Fail2ban SSH configuration to {sshd_conf_path}")
            sshd_conf_path.write_text(sshd_config_content)

            # Enable and restart Fail2ban
            if self._ensure_service_enabled(f2b_service):
                self.logger.info("Fail2ban configured and service started/restarted.")
                # Check status briefly
                run_command(["fail2ban-client", "status"], check=False, capture_output=True)
                run_command(["fail2ban-client", "status", "sshd"], check=False, capture_output=True)
                return True
            else:
                self.logger.error("Fail2ban service failed to start after configuration.")
                return False

        except (IOError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to configure Fail2ban: {e}")
            return False

    def check_selinux(self) -> bool:
        """Checks the status of SELinux."""
        self.logger.info("Checking SELinux status...")
        if not command_exists("sestatus"):
            self.logger.warning(
                "SELinux status command 'sestatus' not found. Trying to install policycoreutils..."
            )
            try:
                run_command(["dnf", "install", "-y", "policycoreutils"], check=True)
                if not command_exists("sestatus"):
                    self.logger.error(
                        "Failed to install policycoreutils. Cannot check SELinux status."
                    )
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install policycoreutils: {e}")
                return False

        try:
            result = run_command(["sestatus"], check=True, capture_output=True)
            status_output = result.stdout
            self.logger.info(f"SELinux Status:\n{status_output.strip()}")

            if (
                "SELinux status:\s+enabled" in status_output
                and "Current mode:\s+enforcing" in status_output
            ):
                self.logger.info("SELinux is enabled and enforcing.")
            elif (
                "SELinux status:\s+enabled" in status_output
                and "Current mode:\s+permissive" in status_output
            ):
                self.logger.warning("SELinux is enabled but in permissive mode.")
                # Optionally suggest how to change it: sudo setenforce 1 && sudo sed -i 's/^SELINUX=permissive/SELINUX=enforcing/' /etc/selinux/config
            else:
                self.logger.warning("SELinux is not enabled or not enforcing.")
                # Optionally suggest how to enable it: sudo sed -i 's/^SELINUX=disabled/SELINUX=enforcing/' /etc/selinux/config # and reboot

            return True  # Report status, don't fail phase unless command fails
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to get SELinux status: {e}")
            return False

    def phase_user_customization(self) -> bool:
        """Deploys user scripts."""
        self.print_section("User Customization & Script Deployment")
        status = True
        try:
            run_with_progress(
                "Deploying user scripts", self.deploy_user_scripts, task_name="user_custom"
            )
        except Exception as e:
            self.logger.error(f"User customization phase failed: {e}")
            status = False
        return status

    def deploy_user_scripts(self) -> bool:
        """Copies scripts from the Git repo to the user's ~/bin directory."""
        # Define potential source directories in order of preference
        source_base = self.config.USER_HOME / "github" / "bash" / "linux"
        potential_sources = [
            source_base / "fedora" / "_scripts",
            source_base / "debian" / "_scripts",  # Fallback
            source_base / "_scripts",  # Generic fallback
        ]
        script_source_dir = None
        for src in potential_sources:
            if src.is_dir():
                self.logger.info(f"Using script source: {src}")
                script_source_dir = src
                break

        if not script_source_dir:
            self.logger.warning(
                f"Script source directory not found under {source_base}. Skipping script deployment."
            )
            return True  # Not necessarily an error if no scripts are expected

        target_bin_dir = self.config.USER_HOME / "bin"
        target_bin_dir.mkdir(exist_ok=True)

        # Get user credentials
        user_uid, user_gid = self._get_user_credentials()
        if user_uid is None or user_gid is None:
            self.logger.error("Cannot deploy user scripts without valid user credentials.")
            return False

        try:
            # Ensure target directory ownership first
            os.chown(target_bin_dir, user_uid, user_gid)

            # Use rsync to copy scripts
            # Run as root, then chown everything afterwards
            rsync_cmd = ["rsync", "-ah", "--delete", f"{script_source_dir}/", f"{target_bin_dir}/"]
            self.logger.info(f"Running rsync: {' '.join(rsync_cmd)}")
            run_command(rsync_cmd, check=True)

            # Make scripts executable and set ownership
            self.logger.info(
                f"Setting permissions and ownership for scripts in {target_bin_dir}..."
            )
            # Find and chmod +x (safer than blanket chmod on dir)
            find_exec_cmd = [
                "find",
                str(target_bin_dir),
                "-type",
                "f",
                "-exec",
                "chmod",
                "755",
                "{}",
                "+",
            ]
            run_command(find_exec_cmd, check=False)  # Best effort chmod

            # Chown the entire directory contents
            chown_cmd = ["chown", "-R", f"{user_uid}:{user_gid}", str(target_bin_dir)]
            run_command(chown_cmd, check=True)

            self.logger.info(f"User scripts deployed successfully to {target_bin_dir}.")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            self.logger.error(f"Script deployment failed: {e}")
            return False

    def phase_permissions(self) -> bool:
        """Sets up home directory permissions."""
        self.print_section("Permissions Setup")
        status = True
        try:
            run_with_progress(
                "Configuring home directory permissions",
                self.home_permissions,
                task_name="permissions",
            )
        except Exception as e:
            self.logger.error(f"Permissions setup phase failed: {e}")
            status = False
        return status

    def home_permissions(self) -> bool:
        """Sets ownership and basic permissions for the user's home directory."""
        user_uid, user_gid = self._get_user_credentials()
        if user_uid is None or user_gid is None:
            self.logger.error("Cannot set home permissions without valid user credentials.")
            return False

        home_dir = self.config.USER_HOME
        if not home_dir.is_dir():
            self.logger.error(
                f"Home directory {home_dir} does not exist. Skipping permissions setup."
            )
            return False  # Cannot proceed if home doesn't exist

        overall_success = True
        try:
            self.logger.info(
                f"Setting ownership of {home_dir} to {self.config.USERNAME} ({user_uid}:{user_gid})..."
            )
            # Use chown -R carefully, ensure it's the right directory
            run_command(["chown", "-R", f"{user_uid}:{user_gid}", str(home_dir)], check=True)
            self.logger.info(f"Ownership set for {home_dir}.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Failed to change ownership of {home_dir}: {e}")
            overall_success = False  # This is critical

        # Set base permissions (e.g., 750 or 700 for home dir, 640/600 for files)
        try:
            self.logger.info(
                f"Setting base permissions for {home_dir} (directory: 750, files: 640)..."
            )
            # Set directory permissions (u=rwx, g=rx, o=)
            run_command(["chmod", "750", str(home_dir)], check=False)  # Dirs first
            # Set file permissions (u=rw, g=r, o=) - find can be slow on large homes
            # Consider skipping file chmod if not strictly needed or doing it more selectively
            run_command(
                ["find", str(home_dir), "-type", "f", "-exec", "chmod", "640", "{}", "+"],
                check=False,
            )
        except Exception as e:
            self.logger.warning(f"Failed to set base permissions on {home_dir}: {e}")
            # Non-critical warning usually

        # Setgid bit on directories (optional, depends on group collaboration needs)
        # try:
        #     self.logger.info("Applying setgid bit to directories within home...")
        #     run_command(["find", str(home_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"], check=False)
        # except Exception as e:
        #     self.logger.warning(f"Failed to set setgid bit: {e}")

        # ACLs (optional, requires 'acl' package)
        if command_exists("setfacl"):
            # Ensure acl package is installed
            try:
                run_command(["rpm", "-q", "acl"], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                self.logger.info("ACL package not found, installing...")
                try:
                    run_command(["dnf", "install", "-y", "acl"], check=True)
                except Exception as e:
                    self.logger.warning(f"Failed to install acl package: {e}. Skipping ACL config.")
                    return overall_success  # Return based on chown success

            # Apply default ACLs if acl installed
            if command_exists("setfacl"):
                try:
                    self.logger.info(
                        f"Applying default ACLs for user {self.config.USERNAME} on {home_dir}..."
                    )
                    # Example: Give user full control, group read/execute, others none by default
                    run_command(
                        [
                            "setfacl",
                            "-R",
                            "-d",
                            "-m",
                            f"u:{self.config.USERNAME}:rwx,g::rx,o::---",
                            str(home_dir),
                        ],
                        check=False,
                    )
                    # Apply immediate ACLs as well (optional, might conflict with chmod)
                    # run_command(["setfacl", "-R", "-m", f"u:{self.config.USERNAME}:rwx,g::rx,o::---", str(home_dir)], check=False)
                    self.logger.info("Default ACLs applied.")
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    self.logger.warning(f"Failed to apply default ACLs: {e}")
        else:
            self.logger.info("setfacl command not found; skipping ACL configuration.")

        return overall_success

    def phase_additional_apps(self) -> bool:
        """Placeholder for installing additional non-packaged applications."""
        self.print_section("Additional Applications & Tools")
        self.logger.info("No additional application installations configured in this script.")
        # Example: Add logic here to download/install tools like Docker CE from official repos
        # self.install_docker_ce() # Example function call
        return True

    # Example placeholder function
    # def install_docker_ce(self) -> bool:
    #     self.logger.info("Attempting to install Docker CE...")
    #     # Add commands to setup docker repo and install docker-ce, docker-ce-cli, containerd.io etc.
    #     # See https://docs.docker.com/engine/install/fedora/
    #     # Remember to handle errors and return True/False
    #     self.logger.warning("Docker CE installation logic not implemented.")
    #     return True

    def phase_cleanup_final(self) -> bool:
        """Performs final system cleanup."""
        self.print_section("Cleanup & Final Configurations")
        status = True
        try:
            self.logger.info("Running final system cleanup (dnf autoremove, dnf clean)...")
            # Remove unused packages that were installed as dependencies
            run_command(["dnf", "autoremove", "-y"], check=False)  # Non-critical if fails
            # Clean DNF cache
            run_command(["dnf", "clean", "all"], check=False)  # Non-critical if fails
            self.logger.info("System cleanup completed.")
        except Exception as e:
            # Catch potential exceptions from run_command if check=True was used
            self.logger.error(f"System cleanup failed: {e}")
            status = False
        return status

    def phase_final_checks(self) -> bool:
        """Runs final checks and prints a summary."""
        self.print_section("Final System Checks")
        status = True
        try:
            info = self.final_checks()
            elapsed = time.time() - self.start_time
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)

            summary = (
                f"{APP_NAME} completed in {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
                f"  Kernel: {info.get('kernel', 'Unknown')}\n"
                f"  Distribution: {info.get('distribution', 'Unknown')}\n"
                f"  SELinux: {info.get('selinux', 'Unknown')}\n"
                f"  Uptime: {info.get('uptime', 'Unknown')}\n"
                f"  Disk Usage (/): {info.get('disk_usage', 'Unknown')}\n"
                f"  Memory Usage: {info.get('memory', 'Unknown')}\n"
                f"Log file: {self.config.LOG_FILE}\n"
                "Review the log file for detailed information and any warnings/errors.\n"
                "A system reboot may be required for some changes (like kernel updates) to take full effect."
            )
            self.logger.info(f"--- Run Summary ---\n{summary}")
            SETUP_STATUS["final"] = {"status": "success", "message": "Setup complete."}
        except Exception as e:
            self.logger.error(f"Final checks phase failed: {e}")
            SETUP_STATUS["final"] = {"status": "failed", "message": f"Final checks failed: {e}"}
            status = False
        return status

    def final_checks(self) -> Dict[str, str]:
        """Gathers final system information."""
        info = {}
        self.logger.info("Gathering final system information...")

        # Kernel Version
        try:
            result = run_command(["uname", "-r"], capture_output=True, check=True)
            info["kernel"] = result.stdout.strip()
            self.logger.info(f"Kernel: {info['kernel']}")
        except Exception as e:
            self.logger.warning(f"Failed to get kernel version: {e}")
            info["kernel"] = "Error"

        # Distribution Info
        try:
            if Path("/etc/os-release").is_file():
                with open("/etc/os-release", "r") as f:
                    content = f.read()
                pretty_name = "Unknown Fedora"
                for line in content.splitlines():
                    if line.startswith("PRETTY_NAME="):
                        pretty_name = line.split("=", 1)[1].strip('"')
                        break
                info["distribution"] = pretty_name
                self.logger.info(f"Distribution: {info['distribution']}")
            else:
                info["distribution"] = "Unknown (os-release missing)"
                self.logger.warning("Cannot read /etc/os-release")
        except Exception as e:
            self.logger.warning(f"Failed to get distribution info: {e}")
            info["distribution"] = "Error"

        # SELinux Status
        try:
            result = run_command(
                ["sestatus"], capture_output=True, check=False
            )  # Don't fail script if sestatus fails
            if result.returncode == 0:
                status_line = "Unknown"
                mode_line = "Unknown"
                for line in result.stdout.splitlines():
                    if "SELinux status:" in line:
                        status_line = line.split(":", 1)[1].strip()
                    elif "Current mode:" in line:
                        mode_line = line.split(":", 1)[1].strip()
                info["selinux"] = f"Status: {status_line}, Mode: {mode_line}"
            else:
                info["selinux"] = f"Error checking (sestatus exit code {result.returncode})"
            self.logger.info(f"SELinux Info: {info['selinux']}")
        except Exception as e:
            self.logger.warning(f"Failed to get SELinux status via sestatus: {e}")
            info["selinux"] = "Error"

        # Uptime
        try:
            result = run_command(["uptime", "-p"], capture_output=True, check=True)
            info["uptime"] = result.stdout.strip()
            self.logger.info(f"Uptime: {info['uptime']}")
        except Exception:
            # Fallback to simple uptime if 'uptime -p' fails
            try:
                result = run_command(["uptime"], capture_output=True, check=True)
                info["uptime"] = result.stdout.strip()
                self.logger.info(f"Uptime (standard): {info['uptime']}")
            except Exception as e2:
                self.logger.warning(f"Failed to get uptime: {e2}")
                info["uptime"] = "Error"

        # Disk Usage (Root filesystem)
        try:
            result = run_command(["df", "-h", "/"], capture_output=True, check=True)
            lines = result.stdout.strip().splitlines()
            if len(lines) > 1:
                info["disk_usage"] = lines[1]  # Second line contains the data
                self.logger.info(f"Disk Usage (/): {info['disk_usage']}")
            else:
                info["disk_usage"] = "Error parsing df output"
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
            info["disk_usage"] = "Error"

        # Memory Usage
        try:
            result = run_command(["free", "-h"], capture_output=True, check=True)
            mem_line = "Unknown"
            for line in result.stdout.splitlines():
                if line.startswith("Mem:"):
                    mem_line = line
                    break
            info["memory"] = mem_line
            self.logger.info(f"Memory Usage: {info['memory']}")
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
            info["memory"] = "Error"

        return info


# --- Signal Handling ---
def signal_handler(signum: int, frame: Any) -> None:
    """Handles termination signals gracefully."""
    sig_name = signal.Signals(signum).name
    print(f"\nSignal {sig_name} ({signum}) received. Initiating cleanup...", file=sys.stderr)
    logger = logging.getLogger("fedora_setup")
    logger.error(f"Script interrupted by {sig_name}. Initiating cleanup.")

    if setup_instance:
        try:
            setup_instance.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup after signal: {e}")
            print(f"Error during cleanup: {e}", file=sys.stderr)
    else:
        logger.warning("Setup instance not found during signal handling.")

    # Exit with appropriate code (128 + signal number)
    sys.exit(128 + signum)


# --- Main Execution ---
def main() -> None:
    """Main function to orchestrate the setup process."""
    # Setup signal handlers early
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
    signal.signal(signal.SIGHUP, signal_handler)  # Hangup signal

    global setup_instance
    setup = None  # Initialize setup to None

    try:
        # Initialize configuration and logger
        config = Config()
        setup = FedoraServerSetup(config)
        setup_instance = setup  # Assign to global for signal handler

        setup.logger.info(f"Starting {APP_NAME} v{VERSION}")

        # Execute phases sequentially
        if not setup.phase_preflight():
            raise Exception("Pre-flight checks failed. Aborting.")
        if not setup.phase_system_update():
            # Decide if script should continue if updates/installs fail partially
            setup.logger.warning("System update phase encountered errors. Continuing cautiously.")
        if not setup.phase_repo_shell_setup():
            setup.logger.warning("Repo & shell setup phase encountered errors.")
        if not setup.phase_security_hardening():
            setup.logger.warning("Security hardening phase encountered errors.")
        if not setup.phase_user_customization():
            setup.logger.warning("User customization phase encountered errors.")
        if not setup.phase_permissions():
            setup.logger.warning("Permissions setup phase encountered errors.")
        if not setup.phase_additional_apps():
            setup.logger.warning("Additional apps phase encountered errors.")
        if not setup.phase_cleanup_final():
            setup.logger.warning("Final cleanup phase encountered errors.")
        if not setup.phase_final_checks():
            setup.logger.error("Final checks phase failed.")

        # Final summary is logged within phase_final_checks

    except KeyboardInterrupt:
        # Already handled by signal handler, but good practice to have
        print("\nOperation cancelled by user.", file=sys.stderr)
        if setup:  # If setup was initialized
            setup.logger.warning("Operation cancelled by user (KeyboardInterrupt).")
        sys.exit(130)  # Exit code for Ctrl+C

    except Exception as e:
        console.print(f"\n[bold red]FATAL ERROR:[/bold red] {e}")
        if setup and setup.logger:  # Check if logger was initialized
            setup.logger.critical(f"Fatal error encountered: {e}", exc_info=True)
        else:
            print(f"Fatal error encountered before logger initialization: {e}", file=sys.stderr)
        # Cleanup is called in finally block
        sys.exit(1)

    finally:
        if setup_instance:
            # Perform final cleanup, even if errors occurred (unless cancelled by signal)
            # Signal handler already calls cleanup, avoid double cleanup
            current_signals = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
            called_by_signal = False
            # This check is tricky, might not reliably detect if signal handler ran.
            # A more robust way might be a flag set by the signal handler.
            # For simplicity, we assume if we reach finally without sys.exit in signal handler,
            # cleanup might be needed.
            # However, the current signal_handler *does* call sys.exit.
            # So, if we reach here, it's likely due to normal completion or an exception,
            # not an handled signal. Let's assume cleanup is needed here.
            print("Executing final cleanup...")
            try:
                setup_instance.cleanup()
            except Exception as cleanup_e:
                print(f"Error during final cleanup: {cleanup_e}", file=sys.stderr)
                if setup and setup.logger:
                    setup.logger.error(f"Error during final cleanup: {cleanup_e}")

        # Final status message
        all_ok = all(
            v["status"] == "success" or v["status"] == "pending"
            for k, v in SETUP_STATUS.items()
            if k != "final"
        )
        final_status = SETUP_STATUS.get("final", {}).get("status", "unknown")

        if final_status == "success" and all_ok:
            print("\nFedora setup script completed successfully.")
        elif final_status == "success" and not all_ok:
            print(
                "\nFedora setup script completed, but some non-critical steps may have warnings/errors. Please review the log."
            )
        else:
            print("\nFedora setup script finished with errors. Please review the log file.")


if __name__ == "__main__":
    main()
