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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

OPERATION_TIMEOUT = 300
APP_NAME = "Fedora Server Setup & Hardening"
VERSION = "1.2.0"  # Updated version for style fixes

setup_instance_global = None  # For signal handler


@dataclass
class Config:
    LOG_FILE: str = "/var/log/fedora_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path(f"/home/{Config.USERNAME}"))
    PACKAGES: List[str] = field(
        default_factory=lambda: [
            # Groups
            "@development-tools",
            # Shells & Terminal Utils
            "bash",
            "zsh",
            "vim-enhanced",
            "nano",
            "micro",
            "tmux",
            "screen",
            "byobu",
            "bash-completion",
            "ncurses-term",
            "grc",
            "ranger",
            "mc",
            "multitail",
            "ccze",
            "colordiff",
            "progress",
            "pv",
            "rlwrap",
            "reptyr",
            "expect",
            "dialog",
            # Modern CLI Tools
            "ripgrep",
            "fd-find",
            "bat",
            "fzf",
            "tldr",
            "jq",
            "sd",
            "hexyl",
            "duf",
            "zoxide",
            "direnv",
            "neofetch",
            # System Monitoring & Performance
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
            "btop",
            "stress-ng",
            "tuned",
            "chrony",
            "lsof",
            "psmisc",
            "lshw",
            "hwinfo",
            "dmidecode",
            "sysfsutils",
            "inxi",
            "usbutils",
            "pciutils",
            # Networking & Security
            "git",
            "openssh-server",
            "firewalld",
            "fail2ban",
            "fail2ban-firewalld",
            "curl",
            "wget",
            "rsync",
            "sudo",
            "net-tools",
            "nmap",
            "nmap-ncat",
            "tcpdump",
            "iptables",
            "nftables",
            "whois",
            "openssl",
            "lynis",
            "sshfs",
            "openvpn",
            "wireguard-tools",
            "ethtool",
            "ca-certificates",
            "gnupg2",
            "certbot",
            "python3-certbot-nginx",
            "python3-certbot-apache",
            "acl",
            "policycoreutils",
            "policycoreutils-python-utils",
            "setroubleshoot-server",
            "bind-utils",
            "NetworkManager-tui",
            "traceroute",
            "ipcalc",
            "socat",
            "bridge-utils",
            "nload",
            "oping",
            "arping",
            "httpie",
            "aria2",
            "dnsmasq",
            "mosh",
            "tcpflow",
            "tcpreplay",
            "tshark",
            "vnstat",
            "iptraf-ng",
            "mitmproxy",
            "lldpd",
            # Development & Build Tools (complementing group)
            "gcc",
            "gcc-c++",
            "make",
            "cmake",
            "python3",
            "python3-pip",
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
            "valgrind",
            "autoconf",
            "automake",
            "libtool",
            "ansible-core",
            # Containers (Podman focus)
            "podman",
            "buildah",
            "skopeo",
            # Virtualization
            "qemu-kvm",
            "libvirt-daemon-kvm",
            "virt-manager",
            "virt-viewer",
            "virt-top",
            "virt-install",
            "libosinfo",
            "libguestfs-tools",
            # Filesystem & Archiving
            "unzip",
            "zip",
            "pigz",
            "lz4",
            "xz",
            "bzip2",
            "p7zip",
            "p7zip-plugins",
            "zstd",
            "cpio",
            "pax",
            "lrzip",
            "unrar",  # unrar may require RPM Fusion repo
            "lzop",
            "logrotate",
            "logwatch",
            "smartmontools",
            "nvme-cli",
            # Database Clients
            "mariadb",
            "postgresql",
            "sqlite",
            "redis",  # Provides redis-cli
            # Backup Tools
            "restic",
            "duplicity",
            "borgbackup",
            "rclone",
            "rsnapshot",
            "rdiff-backup",
            "syncthing",
            "unison",
            "timeshift",
            # Text Processing & Docs
            "gawk",
            "dos2unix",
            "wdiff",
            "pandoc",
            "highlight",
            "groff",
            "xmlstarlet",
            "html-xml-utils",
            "libxslt",
            # Web Servers & Proxies (optional basics)
            "nginx",
            "httpd-tools",
            "haproxy",
            "squid",
            "lighttpd",
            # Other Utils
            "parallel",
            "moreutils",
            "kbd",
            "rpm-devel",
            "dnf-utils",
            "cloud-init",  # Useful for cloud/VM instances
        ]
    )
    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "PermitRootLogin": "no",
            "PasswordAuthentication": "yes",
            "X11Forwarding": "no",
            "MaxAuthTries": "3",
            "ClientAliveInterval": "300",
            "ClientAliveCountMax": "3",
        }
    )
    FIREWALL_RULES: List[Dict[str, str]] = field(
        default_factory=lambda: [
            {"type": "service", "name": "ssh"},
            {"type": "service", "name": "http"},
            {"type": "service", "name": "https"},
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            os.chown(log_file.parent, 0, 0)  # user: root
            os.chmod(log_file.parent, 0o755)  # permissions: rwxr-xr-x
    except OSError as e:
        print(f"Warning: Log directory setup error {log_file.parent}: {e}", file=sys.stderr)
    except Exception as e:  # Catch other potential errors like permission denied during chown/chmod
        print(f"Warning: Log directory setup error {log_file.parent}: {e}", file=sys.stderr)

    logger = logging.getLogger("fedora_setup")
    logger.setLevel(logging.DEBUG)
    # Remove existing handlers to prevent duplication if called again
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console Handler (INFO level, stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler (DEBUG level)
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        # Set log file permissions after handler creation
        try:
            # Ensure file exists before chmod/chown
            if not log_file.exists():
                # Create file with restrictive permissions initially if possible
                # FileHandler likely creates it, but touch ensures it for perms
                log_file.touch(mode=0o600)
            else:
                os.chmod(str(log_file), 0o600)  # rw-------

            if os.geteuid() == 0:
                os.chown(str(log_file), 0, 0)  # owner: root, group: root
        except OSError as e:
            logger.warning(f"Could not set permissions on log file {log_file}: {e}")
        except Exception as e:  # Catch other potential errors
            logger.warning(f"Could not set permissions on log file {log_file}: {e}")

    except OSError as e:  # Catch potential errors during FileHandler creation (e.g., permissions)
        logger.error(f"Failed to set up file logging to {log_file}: {e}")
    except Exception as e:
        logger.error(f"Failed to set up file logging to {log_file}: {e}")

    return logger


def run_command(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = True,
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Runs a command synchronously, handling errors and logging."""
    logger = logging.getLogger("fedora_setup")
    cmd_str = " ".join(cmd)
    log_cwd = f" in {cwd}" if cwd else ""
    logger.debug(f"Running command: {cmd_str}{log_cwd}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            check=check,  # If True, raises CalledProcessError on non-zero exit
            timeout=timeout,
            cwd=cwd,
            env=env,
            errors="replace",  # Handle potential decoding errors
        )

        # Log output if captured (even for successful commands at DEBUG level)
        if capture_output:
            if result.stdout and result.stdout.strip():
                logger.debug(f"Cmd stdout: {result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                # Log stderr at DEBUG level for success, will be logged at ERROR if check fails
                logger.debug(f"Cmd stderr: {result.stderr.strip()}")

        logger.debug(f"Command finished successfully: {cmd_str}")
        return result

    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds: {cmd_str}")
        # Raise a standard TimeoutError for consistency if needed by caller
        raise TimeoutError(f"Command '{cmd_str}' timed out after {timeout} seconds.") from e
    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd[0]}. Ensure it is installed and in PATH.")
        raise e  # Re-raise the specific error
    except subprocess.CalledProcessError as e:
        # This is caught only if check=True and the command returns non-zero
        error_msg = f"Command '{cmd_str}' failed with return code {e.returncode}."
        # Append stdout/stderr if available, helps debugging
        if e.stdout:
            error_msg += f"\nStdout: {e.stdout.strip()}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr.strip()}"
        logger.error(error_msg)
        raise e  # Re-raise the original error after logging
    except Exception as e:
        # Catch any other unexpected exceptions during subprocess.run
        logger.error(f"An unexpected error occurred while running command '{cmd_str}': {e}")
        logger.exception(e)  # Log the full traceback for unexpected errors
        raise e  # Re-raise the original error


def command_exists(cmd: str) -> bool:
    """Checks if a command exists using shutil.which."""
    logger = logging.getLogger("fedora_setup")
    found_path = shutil.which(cmd)
    if found_path:
        logger.debug(f"Command '{cmd}' found at: {found_path}")
        return True
    else:
        logger.debug(f"Command '{cmd}' not found in PATH.")
        return False


def run_task_with_logging(
    description: str, func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Runs a function, logging start/end/failure and timing."""
    logger = logging.getLogger("fedora_setup")
    logger.info(f"Starting: {description}...")
    start_time = time.monotonic()
    try:
        result = func(*args, **kwargs)
        elapsed_time = time.monotonic() - start_time
        logger.info(f"✓ Finished: {description} (took {elapsed_time:.2f}s)")
        return result
    except Exception as e:
        elapsed_time = time.monotonic() - start_time
        # Log the failure message AND the exception details
        logger.error(f"✗ Failed: {description} (after {elapsed_time:.2f}s): {e}")
        logger.exception(e)  # Log stack trace for failures
        raise  # Re-raise exception to signal failure up the call stack


class FedoraServerSetup:
    """Orchestrates the Fedora server setup and hardening process."""

    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.monotonic()
        self.perform_cleanup_on_exit = True  # Flag for signal handler

        # Ensure user home directory exists and has initial ownership (if root)
        if os.geteuid() == 0:
            try:
                self.config.USER_HOME.mkdir(parents=True, exist_ok=True)
                user_info = pwd.getpwnam(self.config.USERNAME)
                os.chown(self.config.USER_HOME, user_info.pw_uid, user_info.pw_gid)
                self.logger.debug(f"Ensured user home directory exists: {self.config.USER_HOME}")
            except KeyError:
                self.logger.error(
                    f"User '{self.config.USERNAME}' not found. Cannot set home directory ownership."
                )
                # This could be critical depending on subsequent steps
            except OSError as e:
                self.logger.warning(
                    f"Could not create or chown user home directory {self.config.USER_HOME}: {e}"
                )
            except Exception as e:
                self.logger.warning(
                    f"Unexpected error setting up user home {self.config.USER_HOME}: {e}"
                )

    def print_section(self, title: str) -> None:
        """Prints a formatted section header to the log."""
        self.logger.info("")  # Blank line before header
        self.logger.info(f"--- {title} ---")
        self.logger.info("")  # Blank line after header

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Creates a timestamped backup of a file."""
        file_path = Path(file_path).resolve()  # Ensure absolute path
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent or non-file: {file_path}")
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Simple backup in the same directory
        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak.{timestamp}")

        try:
            shutil.copy2(file_path, backup_path)  # copy2 preserves metadata
            self.logger.info(f"Backed up '{file_path.name}' to '{backup_path.name}'")
            return str(backup_path)
        except OSError as e:
            self.logger.error(f"Failed to backup {file_path} to {backup_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during backup of {file_path}: {e}")
            return None

    def cleanup(self) -> None:
        """Performs cleanup tasks like removing temp files and rotating logs."""
        # This check prevents cleanup running multiple times if called directly
        # after being triggered by a signal.
        if not self.perform_cleanup_on_exit:
            return

        self.logger.info("--- Performing Cleanup ---")
        try:
            # Clean specific temporary files created by this script (if any pattern)
            tmp_dir = Path(tempfile.gettempdir())
            prefix = "fedora_setup_"  # Example prefix
            cleanup_count = 0
            for item in tmp_dir.glob(f"{prefix}*"):
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                        self.logger.debug(f"Removed temporary file: {item}")
                        cleanup_count += 1
                    elif item.is_dir():
                        shutil.rmtree(item)
                        self.logger.debug(f"Removed temporary directory: {item}")
                        cleanup_count += 1
                except OSError as e:
                    self.logger.warning(f"Failed to clean up temporary item {item}: {e}")
                except Exception as e:
                    self.logger.warning(f"Failed to clean up temporary item {item}: {e}")

            self.logger.info(f"Removed {cleanup_count} temporary items matching prefix '{prefix}'.")

            # Rotate logs as the final cleanup step
            try:
                self.rotate_logs()
            except Exception as e:
                self.logger.warning(f"Log rotation failed during cleanup: {e}")

            self.logger.info("Cleanup completed.")

        except Exception as e:
            self.logger.error(f"General cleanup process failed: {e}")
            self.logger.exception(e)  # Log traceback for cleanup errors

        # Ensure cleanup doesn't run again automatically on exit
        self.perform_cleanup_on_exit = False

    def _compress_log(self, log_path: Path, rotated_path: Union[str, Path]) -> None:
        """Synchronous helper to compress the log file."""
        # Check again if file exists and has content before compressing
        if not log_path.is_file() or log_path.stat().st_size == 0:
            self.logger.debug(f"Log {log_path} empty or removed before compression.")
            return  # Nothing to compress
        try:
            with open(log_path, "rb") as f_in, gzip.open(rotated_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            # After successful compression, remove the original log file
            log_path.unlink()
            self.logger.debug(f"Compressed {log_path} to {rotated_path} and removed original.")
        except FileNotFoundError:
            # File might have been removed between check and open, ignore.
            self.logger.debug(f"Log {log_path} disappeared before compression could start.")
            pass
        except OSError as e:
            # Log error but allow main process to potentially continue
            # Use print as logger might be closed/inaccessible during rotation issues
            print(f"Error during log compression for {log_path}: {e}", file=sys.stderr)
            raise  # Re-raise to be caught by the calling method

    def rotate_logs(self, log_file: Optional[Union[str, Path]] = None) -> bool:
        """Rotates the main log file by compressing it with a timestamp."""
        if log_file is None:
            log_file = self.config.LOG_FILE
        log_path = Path(log_file).resolve()

        if not log_path.is_file() or log_path.stat().st_size == 0:
            self.logger.info(f"Log file {log_path} empty or non-existent. No rotation needed.")
            return False

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_path = log_path.with_suffix(f".{timestamp}.gz")
        self.logger.info(f"Attempting to rotate log file {log_path} to {rotated_path}...")

        try:
            # Ensure the log handlers release the file before rotation
            # Need to operate on the *current* logger instance's handlers
            current_logger = logging.getLogger("fedora_setup")
            file_handler_found = False
            for handler in current_logger.handlers[:]:
                # Check if it's a FileHandler and its baseFilename matches our log file
                if isinstance(handler, logging.FileHandler):
                    try:
                        # Resolve handler's filename to handle relative paths etc.
                        handler_base_path = Path(handler.baseFilename).resolve()
                        if handler_base_path == log_path:
                            handler.close()
                            current_logger.removeHandler(handler)
                            file_handler_found = True
                            self.logger.debug(f"Closed and removed handler for {log_path}")
                            break  # Assume only one handler for this file
                    except Exception as e:
                        self.logger.warning(f"Error processing log handler for {log_path}: {e}")

            if not file_handler_found:
                self.logger.warning(f"Could not find active file handler for {log_path} to close.")

            # Perform compression
            self._compress_log(log_path, rotated_path)
            self.logger.info(f"Log successfully rotated to {rotated_path}")

            # Re-initialize logger handlers to start logging to the (now empty/new) original file
            setup_logger(self.config.LOG_FILE)

            return True
        except Exception as e:
            self.logger.error(f"Log rotation failed for {log_path}: {e}")
            self.logger.exception(e)
            # Attempt to re-add file handler even if rotation failed, so logging can continue
            setup_logger(self.config.LOG_FILE)
            return False

    def has_internet_connection(
        self, host: str = "8.8.8.8", port: int = 53, timeout: int = 5
    ) -> bool:
        """Checks internet connectivity via TCP connection."""
        self.logger.debug(f"Checking internet connection via {host}:{port}...")
        import socket

        try:
            # Set a default timeout for socket operations
            socket.setdefaulttimeout(timeout)
            # Create a socket, connect, and immediately close
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((host, port))
            self.logger.debug("Internet connection successful.")
            return True
        except socket.timeout:
            self.logger.warning(f"Connection to {host}:{port} timed out after {timeout}s.")
            return False
        except OSError as e:
            # Catches connection refused, network unreachable, etc.
            self.logger.warning(f"Connection to {host}:{port} failed: {e}")
            return False
        except Exception as e:
            # Catch any other unexpected errors
            self.logger.error(f"Unexpected error checking internet connection: {e}")
            return False

    # --- Task Methods ---

    def check_root(self) -> None:
        """Ensures script is run as root."""
        if os.geteuid() != 0:
            self.logger.critical("This script must be run as root (or using sudo).")
            sys.exit(1)  # Exit immediately if not root
        self.logger.info("Root privileges confirmed.")

    def check_network(self) -> None:
        """Verifies network connectivity, trying ping as fallback."""
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.warning(
                "Primary network connectivity check failed. Attempting fallback ping..."
            )
            try:
                run_command(
                    ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                self.logger.info("Fallback ping check successful.")
            except TimeoutError:
                self.logger.critical("Fallback ping check timed out. Aborting.")
                sys.exit(1)
            except subprocess.CalledProcessError:
                self.logger.critical("Fallback ping check failed (host unreachable?). Aborting.")
                sys.exit(1)
            except Exception as e:
                self.logger.critical(f"Fallback ping check failed unexpectedly: {e}. Aborting.")
                sys.exit(1)

    def check_fedora(self) -> None:
        """Verifies the system is Fedora."""
        os_release_path = Path("/etc/os-release")
        try:
            if os_release_path.exists():
                content = os_release_path.read_text()
                os_release_data = {
                    k.strip(): v.strip().strip('"')
                    for k, v in (line.split("=", 1) for line in content.splitlines() if "=" in line)
                }
                dist_id = os_release_data.get("ID")
                dist_name = os_release_data.get("PRETTY_NAME", "Unknown")

                if dist_id == "fedora":
                    self.logger.info(f"Detected Fedora system: {dist_name}")
                else:
                    self.logger.warning(
                        f"System identified as '{dist_name}' (ID: {dist_id}), not Fedora."
                        " Script may not work as expected."
                    )
            else:
                self.logger.warning(
                    f"{os_release_path} not found. Cannot verify distribution."
                    " Assuming Fedora-like system, but proceed with caution."
                )
        except OSError as e:
            self.logger.error(f"Could not read {os_release_path}: {e}")
            self.logger.warning("Proceeding, but distribution check failed.")
        except Exception as e:
            self.logger.error(f"Could not parse {os_release_path}: {e}")
            self.logger.warning("Proceeding, but distribution check failed.")

    def save_config_snapshot(self) -> Optional[str]:
        """Saves a compressed tarball of important configuration files."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("/var/backups/initial_setup")
        snapshot_file = backup_dir / f"fedora_config_snapshot_{timestamp}.tar.gz"

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            if os.geteuid() == 0:
                os.chown(backup_dir, 0, 0)  # root:root
                os.chmod(backup_dir, 0o700)  # drwx------
        except OSError as e:
            self.logger.error(f"Failed to create or secure backup directory {backup_dir}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to create or secure backup directory {backup_dir}: {e}")
            return None

        config_paths_to_backup = [
            "/etc/dnf/dnf.conf",
            "/etc/dnf/protected.d",
            "/etc/yum.repos.d",
            "/etc/fstab",
            "/etc/default/grub",
            "/etc/sysconfig/grub",
            "/etc/hosts",
            "/etc/ssh/sshd_config",
            "/etc/ssh/ssh_config",
            "/etc/sysconfig/network-scripts/",
            "/etc/NetworkManager/system-connections/",
            "/etc/firewalld/firewalld.conf",
            "/etc/firewalld/zones/",
            "/etc/selinux/config",
            "/etc/sysconfig/selinux",
        ]

        self.logger.info(f"Creating configuration snapshot: {snapshot_file}...")
        files_added = []
        files_missing = []

        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                for item_path_str in config_paths_to_backup:
                    item_path = Path(item_path_str)
                    if item_path.exists():
                        try:
                            # Add file/directory to tar, arcname relative to root '/'
                            arcname = str(item_path.relative_to(item_path.anchor))
                            tar.add(str(item_path), arcname=arcname, recursive=True)
                            files_added.append(str(item_path))
                            self.logger.debug(f"Added to snapshot: {item_path}")
                        except Exception as e_tar:
                            # Log error adding specific file but continue
                            self.logger.warning(f"Could not add {item_path} to snapshot: {e_tar}")
                    else:
                        files_missing.append(str(item_path))
                        self.logger.debug(f"Skipping missing config path: {item_path}")

            if files_missing:
                self.logger.info(
                    f"Note: The following configured paths were not found for backup: {', '.join(files_missing)}"
                )

            if files_added:
                self.logger.info(
                    f"Successfully saved snapshot of {len(files_added)} items to {snapshot_file}"
                )
                try:
                    # Secure the backup file (readable only by root)
                    if os.geteuid() == 0:
                        os.chmod(snapshot_file, 0o600)
                        os.chown(snapshot_file, 0, 0)  # root:root
                except OSError as e_perm:
                    self.logger.warning(
                        f"Could not set permissions on snapshot file {snapshot_file}: {e_perm}"
                    )
                except Exception as e_perm:
                    self.logger.warning(
                        f"Could not set permissions on snapshot file {snapshot_file}: {e_perm}"
                    )
                return str(snapshot_file)
            else:
                self.logger.warning("No configuration files found or added to the snapshot.")
                # Clean up empty archive file if created
                if snapshot_file.exists():
                    try:
                        snapshot_file.unlink()
                    except OSError as e:
                        self.logger.warning(f"Could not remove empty snapshot {snapshot_file}: {e}")
                return None
        except tarfile.TarError as e:
            self.logger.error(f"Failed to create tar snapshot {snapshot_file}: {e}")
        except OSError as e:
            self.logger.error(f"OS error during snapshot creation {snapshot_file}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error creating snapshot {snapshot_file}: {e}")

        # Cleanup partial/corrupt archive on failure
        if snapshot_file.exists():
            try:
                snapshot_file.unlink()
                self.logger.debug(f"Removed incomplete snapshot file: {snapshot_file}")
            except OSError as e_unlink:
                self.logger.warning(
                    f"Could not remove failed snapshot file {snapshot_file}: {e_unlink}"
                )
        return None

    def check_updates(self) -> bool:
        """Checks for DNF updates (updates metadata). Returns True, logs status."""
        self.logger.info("Checking for DNF package updates...")
        try:
            # dnf check-update exits 100 if updates available, 0 if none, non-zero on error
            result = run_command(["dnf", "check-update"], check=False, capture_output=True)
            if result.returncode == 100:
                self.logger.info("Updates are available.")
            elif result.returncode == 0:
                self.logger.info("System is up-to-date.")
            else:
                # Treat actual command failure as an error, but don't stop script necessarily
                self.logger.error(
                    f"DNF check-update command failed with return code {result.returncode}."
                )
                if result.stderr:
                    self.logger.error(f"Stderr: {result.stderr.strip()}")
            return (
                True  # Task itself succeeded, even if updates found or command had non-0/100 code
            )
        except Exception as e:
            # Catch command execution errors (timeout, file not found, etc.)
            self.logger.error(f"Error during DNF check-update execution: {e}")
            return False  # Indicate task failure

    def upgrade_system(self) -> bool:
        """Performs DNF system upgrade."""
        self.logger.info("Upgrading system packages using DNF...")
        try:
            # Use --refresh to ensure metadata is current
            run_command(["dnf", "upgrade", "-y", "--refresh"])
            self.logger.info("System upgrade completed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            # Log specific error from DNF
            self.logger.error(f"System upgrade failed with code {e.returncode}.")
            # Error details already logged by run_command
            return False
        except Exception as e:
            # Catch other errors like timeout
            self.logger.error(f"An unexpected error occurred during system upgrade: {e}")
            return False

    def is_package_installed(self, pkg_name: str) -> bool:
        """Checks if a package is installed using rpm -q."""
        try:
            # Run rpm -q, don't capture output, just check return code
            run_command(["rpm", "-q", pkg_name], capture_output=True, check=True, timeout=10)
            return True
        except subprocess.CalledProcessError:
            # Expected if package is not installed
            return False
        except FileNotFoundError:
            self.logger.error("rpm command not found, cannot check package status.")
            return False  # Treat as not installed if tool is missing
        except Exception as e:
            # Log unexpected errors during check
            self.logger.warning(f"Error checking package {pkg_name} with rpm -q: {e}")
            return False  # Assume not installed on error

    def install_packages(self) -> Tuple[List[str], List[str]]:
        """Installs packages from config list using DNF."""
        self.logger.info("Processing package installation list...")
        groups_to_install = [pkg for pkg in self.config.PACKAGES if pkg.startswith("@")]
        packages_to_install = [pkg for pkg in self.config.PACKAGES if not pkg.startswith("@")]

        installed_pkgs = set()
        failed_pkgs = []

        # --- Install Groups ---
        if groups_to_install:
            group_str = ", ".join(groups_to_install)
            self.logger.info(f"Installing package groups: {group_str}")
            try:
                run_command(["dnf", "groupinstall", "-y"] + groups_to_install)
                self.logger.info(f"Successfully installed groups: {group_str}")
                installed_pkgs.update(groups_to_install)  # Add group names conceptually
            except Exception as e:
                self.logger.error(f"Failed to install package groups: {group_str} - {e}")
                failed_pkgs.extend(groups_to_install)  # Mark groups as failed

        # --- Check and Install Individual Packages ---
        self.logger.info("Checking status of individual packages...")
        missing_pkgs = []
        if packages_to_install:
            for pkg in packages_to_install:
                # Avoid checking if already installed via a successful group or previously
                if pkg not in installed_pkgs and pkg not in failed_pkgs:
                    if self.is_package_installed(pkg):
                        self.logger.debug(f"Package already installed: {pkg}")
                        installed_pkgs.add(pkg)
                    else:
                        self.logger.debug(f"Package needs installation: {pkg}")
                        missing_pkgs.append(pkg)

        if not missing_pkgs:
            self.logger.info(
                "All required individual packages are already installed or handled by groups."
            )
        else:
            self.logger.info(
                f"Attempting to install {len(missing_pkgs)} missing individual packages..."
            )
            # Install missing packages in batches
            batch_size = 30  # DNF handles larger batches well
            batches = [
                missing_pkgs[i : i + batch_size] for i in range(0, len(missing_pkgs), batch_size)
            ]

            for i, batch in enumerate(batches, 1):
                batch_str = " ".join(batch)
                self.logger.info(f"Installing batch {i}/{len(batches)}: {batch_str}")
                try:
                    # --setopt=install_weak_deps=False mimics --no-install-recommends
                    # Use allowerasing potentially needed if conflicts arise, but use cautiously
                    run_command(
                        ["dnf", "install", "-y", "--setopt=install_weak_deps=False"] + batch
                    )
                    self.logger.info(f"Successfully installed batch {i}.")
                    installed_pkgs.update(batch)  # Mark batch as successful
                except Exception as e:
                    self.logger.error(f"Failed to install batch {i}: {batch_str} - {e}")
                    self.logger.info(
                        "Attempting to install packages from failed batch individually..."
                    )
                    # Try installing packages from the failed batch one by one
                    for pkg in batch:
                        # Check if already installed or failed to avoid retries
                        if pkg not in installed_pkgs and pkg not in failed_pkgs:
                            try:
                                run_command(
                                    [
                                        "dnf",
                                        "install",
                                        "-y",
                                        "--setopt=install_weak_deps=False",
                                        pkg,
                                    ]
                                )
                                self.logger.info(
                                    f"Successfully installed individual package: {pkg}"
                                )
                                installed_pkgs.add(pkg)
                            except Exception as e_single:
                                self.logger.error(
                                    f"Failed to install individual package {pkg}: {e_single}"
                                )
                                failed_pkgs.append(pkg)  # Add to final failed list

        # --- Final Cleanup ---
        self.logger.info("Running final package cleanup (autoremove)...")
        try:
            run_command(["dnf", "autoremove", "-y"], check=False)  # Run even if installs failed
        except Exception as e:
            self.logger.warning(f"dnf autoremove failed: {e}")

        # Compile final lists
        final_successful = list(installed_pkgs)
        final_failed = list(set(failed_pkgs))  # Deduplicate failures

        self.logger.info(
            f"Package installation summary: {len(final_successful)} succeeded, {len(final_failed)} failed."
        )
        if final_failed:
            self.logger.warning(f"Failed packages: {', '.join(final_failed)}")

        return final_successful, final_failed

    def check_reboot_needed(self) -> None:
        """Checks if a reboot is recommended using dnf needs-restarting."""
        needs_restarting_cmd = "needs-restarting"
        if not command_exists(needs_restarting_cmd):
            self.logger.info(
                f"'{needs_restarting_cmd}' command not found (from dnf-utils). "
                "Attempting to install..."
            )
            try:
                run_command(["dnf", "install", "-y", "dnf-utils"], check=True, timeout=60)
                if not command_exists(needs_restarting_cmd):
                    self.logger.warning(
                        f"Failed to install dnf-utils or '{needs_restarting_cmd}' still not found. "
                        "Skipping reboot check."
                    )
                    return
            except Exception as e:
                self.logger.warning(f"Failed to install dnf-utils: {e}. Skipping reboot check.")
                return

        try:
            # needs-restarting exits 1 if reboot is needed, 0 otherwise.
            result = run_command(
                [needs_restarting_cmd, "-r"], check=False, capture_output=True, timeout=30
            )
            if result.returncode == 1:
                self.logger.warning("--- REBOOT RECOMMENDED ---")
                self.logger.warning(
                    "A system reboot is recommended due to updated core components (kernel, systemd, etc.)."
                )
            elif result.returncode == 0:
                self.logger.info("No reboot required according to needs-restarting.")
            else:
                self.logger.warning(
                    f"'{needs_restarting_cmd} -r' command finished with unexpected code {result.returncode}. "
                    "Cannot determine reboot status."
                )
                if result.stderr:
                    self.logger.warning(f"Stderr: {result.stderr.strip()}")

        except TimeoutError:
            self.logger.error(
                f"'{needs_restarting_cmd} -r' timed out. Cannot determine reboot status."
            )
        except Exception as e:
            self.logger.error(f"Error checking if reboot is needed: {e}")

    def setup_repos(self) -> bool:
        """Clones or updates specified GitHub repositories for the user."""
        try:
            user_info = pwd.getpwnam(self.config.USERNAME)
            user_uid = user_info.pw_uid
            user_gid = user_info.pw_gid
        except KeyError:
            self.logger.error(
                f"User '{self.config.USERNAME}' does not exist. Cannot setup repositories."
            )
            return False
        except Exception as e:
            self.logger.error(f"Could not get user info for {self.config.USERNAME}: {e}")
            return False

        gh_dir = self.config.USER_HOME / "github"
        self.logger.info(f"Setting up repositories in {gh_dir} for user {self.config.USERNAME}")

        try:
            gh_dir.mkdir(parents=True, exist_ok=True)
            # Ensure the github directory itself is owned by the user
            os.chown(gh_dir, user_uid, user_gid)
        except OSError as e:
            self.logger.error(f"Failed to create or set ownership on directory {gh_dir}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to create or set ownership on directory {gh_dir}: {e}")
            return False

        all_success = True
        # Specify the repositories to clone/update
        repos_to_manage = ["bash", "python"]  # Add other repo names as needed

        for repo_name in repos_to_manage:
            repo_dir = gh_dir / repo_name
            # Assuming dunamismax GitHub user structure
            repo_url = f"https://github.com/dunamismax/{repo_name}.git"

            try:
                if (repo_dir / ".git").is_dir():
                    self.logger.info(f"Repository '{repo_name}' exists. Pulling updates...")
                    # Run git pull
                    run_command(["git", "-C", str(repo_dir), "pull"])
                else:
                    self.logger.info(f"Cloning repository '{repo_name}' from {repo_url}...")
                    run_command(["git", "clone", repo_url, str(repo_dir)])

                # Ensure ownership after pull/clone
                self.logger.debug(f"Setting ownership for {repo_dir}...")
                run_command(
                    ["chown", "-R", f"{user_uid}:{user_gid}", str(repo_dir)],
                    check=False,  # Log warning if chown fails, but don't fail phase
                )

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed git operation for repository '{repo_name}': {e}")
                all_success = False
                # Clean up partially cloned directory? Only if clone likely failed.
                if not (repo_dir / ".git").is_dir() and repo_dir.exists():
                    self.logger.info(f"Removing potentially incomplete clone: {repo_dir}")
                    try:
                        shutil.rmtree(repo_dir)
                    except Exception as rm_e:
                        self.logger.warning(f"Could not remove incomplete clone {repo_dir}: {rm_e}")
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred while managing repo '{repo_name}': {e}"
                )
                all_success = False

        # Final check on overall github directory ownership (redundant but safe)
        try:
            run_command(
                ["chown", "-R", f"{user_uid}:{user_gid}", str(gh_dir)],
                check=False,
            )
        except Exception as e:
            self.logger.warning(f"Final chown on {gh_dir} failed: {e}")

        return all_success

    def copy_shell_configs(self) -> bool:
        """Copies dotfiles (.bashrc, .profile) from repo to user and root homes."""
        base_repo_dir = self.config.USER_HOME / "github" / "bash" / "linux"

        # Define potential source directories in order of preference
        source_dirs_prefs = [
            base_repo_dir / "fedora" / "dotfiles",
            base_repo_dir / "debian" / "dotfiles",  # Fallback 1
            base_repo_dir / "ubuntu" / "dotfiles",  # Fallback 2
            base_repo_dir / "generic" / "dotfiles",  # Fallback 3 (if exists)
        ]

        source_dir = next((d for d in source_dirs_prefs if d.is_dir()), None)

        if not source_dir:
            # Try to find ANY dotfiles dir as last resort
            self.logger.warning("No preferred dotfiles source directory found. Searching...")
            found_dotfiles = list(base_repo_dir.glob("**/dotfiles"))
            if found_dotfiles:
                source_dir = found_dotfiles[0]  # Use the first one found
                self.logger.warning(f"Using fallback dotfiles directory found at: {source_dir}")
            else:
                self.logger.error(
                    "Could not find any 'dotfiles' directory. Cannot copy shell configs."
                )
                return False
        else:
            self.logger.info(f"Using dotfiles source directory: {source_dir}")

        # Destinations: User's home and root's home
        destination_dirs = [self.config.USER_HOME, Path("/root")]
        files_to_copy = [".bashrc", ".profile"]  # Add other dotfiles as needed

        overall_success = True
        try:
            user_info = pwd.getpwnam(self.config.USERNAME)
            root_info = pwd.getpwuid(0)  # Get root user info by UID 0
        except KeyError:
            self.logger.error(
                f"User {self.config.USERNAME} or root not found. Cannot set ownership."
            )
            return False
        except Exception as e:
            self.logger.error(f"Could not get user info: {e}")
            return False

        for file_name in files_to_copy:
            src_file = source_dir / file_name
            if not src_file.is_file():
                self.logger.warning(
                    f"Source file '{file_name}' not found in {source_dir}. Skipping."
                )
                continue

            for dest_dir in destination_dirs:
                # Ensure destination directory exists
                if not dest_dir.is_dir():
                    self.logger.warning(
                        f"Destination directory {dest_dir} does not exist. Skipping copy."
                    )
                    continue

                dest_file = dest_dir / file_name
                is_root_dest = dest_dir == Path("/root")
                target_uid = root_info.pw_uid if is_root_dest else user_info.pw_uid
                target_gid = root_info.pw_gid if is_root_dest else user_info.pw_gid

                try:
                    # Check if files are identical before copying
                    files_identical = False
                    if dest_file.is_file():
                        # Use filecmp for reliable comparison
                        files_identical = filecmp.cmp(str(src_file), str(dest_file), shallow=False)

                    if files_identical:
                        self.logger.info(f"File {dest_file} is identical to source. Skipping copy.")
                    else:
                        self.logger.info(f"Copying '{src_file.name}' to {dest_file}...")
                        # Backup existing file before overwrite
                        if dest_file.exists():
                            self.backup_file(dest_file)  # backup_file handles errors

                        # Copy file using shutil.copy2 to preserve metadata
                        shutil.copy2(src_file, dest_file)

                        # Set ownership and permissions (conservative: 644)
                        os.chown(dest_file, target_uid, target_gid)
                        os.chmod(dest_file, 0o644)  # rw-r--r--
                        self.logger.info(f"Successfully copied and secured {dest_file}.")

                except OSError as e:
                    self.logger.error(f"OS error copying '{src_file.name}' to {dest_file}: {e}")
                    overall_success = False
                except filecmp.Error as e:
                    self.logger.error(f"Error comparing '{src_file.name}' and '{dest_file}': {e}")
                    overall_success = (
                        False  # Treat comparison error as needing action? Maybe copy anyway?
                    )
                except Exception as e:
                    self.logger.error(
                        f"Unexpected error copying '{src_file.name}' to {dest_file}: {e}"
                    )
                    self.logger.exception(e)
                    overall_success = False

        return overall_success

    def set_bash_shell(self) -> bool:
        """Sets /bin/bash as the default login shell for the configured user."""
        bash_path = "/bin/bash"
        username = self.config.USERNAME

        # 1. Verify bash exists, install if necessary
        if not command_exists(bash_path):
            self.logger.warning(
                f"Bash executable not found at {bash_path}. Attempting to install 'bash'..."
            )
            try:
                run_command(["dnf", "install", "-y", "bash"])
                if not command_exists(bash_path):
                    self.logger.error("Bash installation failed or bash still not found.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install bash: {e}")
                return False

        # 2. Verify the shell is listed in /etc/shells
        shells_file = Path("/etc/shells")
        self.logger.info(f"Verifying '{bash_path}' is listed in {shells_file}...")
        try:
            content = shells_file.read_text()
            # Check if the exact path is present on its own line
            if f"\n{bash_path}\n" not in f"\n{content}\n":  # Add newlines for exact match
                self.logger.warning(
                    f"'{bash_path}' not found in {shells_file}. Attempting to add it."
                )
                # Backup the file first
                backup_path = self.backup_file(shells_file)
                if not backup_path:
                    self.logger.warning("Could not backup /etc/shells. Proceeding without backup.")
                # Append the shell path (ensure newline before and after)
                with shells_file.open("a") as f:
                    f.write(f"\n{bash_path}\n")
                self.logger.info(f"Added '{bash_path}' to {shells_file}.")
            else:
                self.logger.info(f"'{bash_path}' is already listed in {shells_file}.")
        except FileNotFoundError:
            self.logger.error(f"{shells_file} not found. Cannot verify or add shell.")
            return False
        except OSError as e:
            self.logger.error(f"Failed to read or update {shells_file}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to read or update {shells_file}: {e}")
            return False

        # 3. Set the user's default shell using 'usermod'
        self.logger.info(f"Setting default shell for user '{username}' to '{bash_path}'...")
        try:
            # usermod -s requires root privileges (checked at script start)
            run_command(["usermod", "--shell", bash_path, username])
            self.logger.info(f"Successfully set default shell for '{username}' to '{bash_path}'.")

            # Verify change using getent (optional but good)
            try:
                result = run_command(["getent", "passwd", username], capture_output=True, text=True)
                user_entry = result.stdout.strip()
                if user_entry.endswith(f":{bash_path}"):
                    self.logger.info("Shell change verified successfully.")
                else:
                    self.logger.warning(f"Verification failed. User entry: {user_entry}")
            except Exception as e_verify:
                self.logger.warning(f"Could not verify shell change with getent: {e_verify}")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to set default shell for '{username}' using usermod: {e}")
            # Error details logged by run_command
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while setting default shell: {e}")
            return False

    def configure_ssh(self) -> bool:
        """Configures the OpenSSH server (sshd)."""
        sshd_service = "sshd"
        sshd_config_path = Path("/etc/ssh/sshd_config")
        self.logger.info("Configuring SSH Server (sshd)...")

        # 1. Ensure openssh-server package is installed
        if not self.is_package_installed("openssh-server"):
            self.logger.warning("openssh-server package not found. Attempting installation...")
            try:
                run_command(["dnf", "install", "-y", "openssh-server"])
                if not self.is_package_installed("openssh-server"):
                    self.logger.error("Failed to install openssh-server. Cannot configure SSH.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install openssh-server: {e}")
                return False
        else:
            self.logger.debug("openssh-server package confirmed.")

        # 2. Ensure SSH service is enabled and running
        self.logger.info(f"Ensuring {sshd_service} service is enabled and active...")
        try:
            run_command(["systemctl", "enable", sshd_service])
            run_command(["systemctl", "start", sshd_service])
            # Check status after start attempt
            result = run_command(
                ["systemctl", "is-active", sshd_service],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() != "active":
                self.logger.warning(
                    f"{sshd_service} service is not active (status: {result.stdout.strip()}). "
                    "Attempting restart..."
                )
                run_command(["systemctl", "restart", sshd_service])
                time.sleep(1)  # Give it a moment
                result = run_command(
                    ["systemctl", "is-active", sshd_service],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip() != "active":
                    self.logger.error(
                        f"{sshd_service} failed to start. Check logs ('journalctl -u {sshd_service}')."
                    )
                    return False  # Service failing to start is critical for SSH config
            self.logger.info(f"{sshd_service} service is active.")

        except Exception as e:
            self.logger.error(f"Failed to enable or start {sshd_service} service: {e}")
            return False

        # 3. Apply configuration changes from self.config.SSH_CONFIG
        self.logger.info(f"Applying SSH configuration changes to {sshd_config_path}...")
        if not sshd_config_path.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config_path}")
            return False

        # Backup the original config file
        backup_path = self.backup_file(sshd_config_path)
        if not backup_path:
            # Continue if backup fails, but log a strong warning
            self.logger.warning(f"Failed to backup {sshd_config_path}. Proceeding with caution.")

        try:
            original_content = sshd_config_path.read_text()
            lines = original_content.splitlines()
            new_lines = []
            modified_keys = set()
            ssh_config_items = self.config.SSH_CONFIG.items()

            # Process existing lines
            for line in lines:
                stripped_line = line.strip()
                # Skip empty lines and comments
                if not stripped_line or stripped_line.startswith("#"):
                    new_lines.append(line)
                    continue

                # Check if the line configures one of our keys
                matched = False
                for key, value in ssh_config_items:
                    # Match key (case-insensitive) followed by space/tab
                    # Check if stripped_line starts with the key and a whitespace separator
                    if stripped_line.lower().startswith(key.lower()):
                        parts = stripped_line.split(None, 1)  # Split into key and rest
                        if len(parts) > 0 and parts[0].lower() == key.lower():
                            new_setting = f"{key} {value}"
                            # Compare stripped line content for change detection
                            if stripped_line == new_setting:
                                self.logger.debug(f"SSH config '{key}' already set correctly.")
                                new_lines.append(
                                    line
                                )  # Keep original line (preserves comments etc)
                            else:
                                self.logger.info(
                                    f"Updating SSH config: '{stripped_line}' to '{new_setting}'"
                                )
                                new_lines.append(new_setting)  # Add the new setting line
                            modified_keys.add(key)
                            matched = True
                            break  # Move to next line once key is matched

                if not matched:
                    new_lines.append(line)  # Keep lines not related to our config

            # Add any keys from config that were not found in the file
            for key, value in ssh_config_items:
                if key not in modified_keys:
                    new_setting = f"{key} {value}"
                    self.logger.info(f"Adding missing SSH config: '{new_setting}'")
                    new_lines.append(new_setting)

            # Write the modified configuration back
            new_content = "\n".join(new_lines) + "\n"  # Ensure trailing newline

            # Only write and restart if content has actually changed
            # Compare stripped content to ignore pure whitespace/newline differences
            if new_content.strip() != original_content.strip():
                self.logger.info(f"Writing updated configuration to {sshd_config_path}")
                sshd_config_path.write_text(new_content)

                # 4. Validate configuration and reload/restart service
                self.logger.info("Validating new SSH configuration...")
                run_command(["sshd", "-t"])  # sshd -t validates config, raises error if invalid

                self.logger.info(f"Restarting {sshd_service} to apply changes...")
                run_command(["systemctl", "restart", sshd_service])
                self.logger.info("SSH configuration updated and service restarted.")
            else:
                self.logger.info("No SSH configuration changes needed.")

            return True

        except subprocess.CalledProcessError as e:
            # sshd -t failed validation or systemctl restart failed
            self.logger.error(f"Failed during SSH configuration or restart: {e}")
            # Attempt to restore backup if validation/restart failed
            if backup_path and Path(backup_path).exists():
                self.logger.warning(f"Attempting to restore SSH config from backup: {backup_path}")
                try:
                    shutil.copy2(backup_path, sshd_config_path)
                    # Try restarting again after restore
                    run_command(["systemctl", "restart", sshd_service])
                    self.logger.info("SSH config restored from backup and service restarted.")
                except Exception as restore_e:
                    self.logger.error(
                        f"Failed to restore SSH config from backup or restart after restore: {restore_e}. "
                        "Manual intervention required!"
                    )
            return False  # Indicate failure
        except OSError as e:
            self.logger.error(f"OS error during SSH configuration: {e}")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during SSH configuration: {e}")
            self.logger.exception(e)
            return False

    def log_firewall_status(self, zone: str = "public"):
        """Logs the current firewalld status for the specified zone."""
        try:
            self.logger.info(f"--- Current firewalld status (zone: {zone}) ---")
            # firewall-cmd might not be available if installation failed
            if not command_exists("firewall-cmd"):
                self.logger.warning("firewall-cmd not found, cannot check status.")
                return
            result = run_command(
                ["firewall-cmd", f"--zone={zone}", "--list-all"], capture_output=True, text=True
            )
            self.logger.info(result.stdout.strip())
            self.logger.info("------------------------------------------")
        except Exception as e:
            self.logger.warning(f"Could not retrieve firewalld status for zone {zone}: {e}")

    def configure_firewall(self) -> bool:
        """Configures the firewall using firewalld."""
        firewalld_service = "firewalld"
        self.logger.info("Configuring Firewall (firewalld)...")

        # 1. Ensure firewalld package is installed
        if not self.is_package_installed(firewalld_service):
            self.logger.warning("firewalld package not found. Attempting installation...")
            try:
                run_command(["dnf", "install", "-y", firewalld_service])
                if not self.is_package_installed(firewalld_service):
                    self.logger.error("Failed to install firewalld. Cannot configure firewall.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install firewalld: {e}")
                return False
        else:
            self.logger.debug("firewalld package confirmed.")

        # 2. Ensure firewalld service is enabled and running
        self.logger.info(f"Ensuring {firewalld_service} service is enabled and active...")
        try:
            run_command(["systemctl", "enable", firewalld_service])
            run_command(["systemctl", "start", firewalld_service])
            time.sleep(1)  # Give service a moment to start
            result = run_command(
                ["systemctl", "is-active", firewalld_service],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() != "active":
                self.logger.warning(f"{firewalld_service} inactive. Restarting...")
                run_command(["systemctl", "restart", firewalld_service])
                time.sleep(2)  # More time after restart
                result = run_command(
                    ["systemctl", "is-active", firewalld_service],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip() != "active":
                    self.logger.error(
                        f"{firewalld_service} failed to start. Check logs ('journalctl -u {firewalld_service}')."
                    )
                    return False
            self.logger.info(f"{firewalld_service} service is active.")
        except Exception as e:
            self.logger.error(f"Failed to enable or start {firewalld_service} service: {e}")
            return False

        # 3. Apply firewall rules from config
        self.logger.info("Applying firewall rules (permanent)...")
        try:
            # Use the default zone unless specified otherwise
            zone = "public"  # Make this configurable if needed

            # Get currently allowed services/ports to avoid duplicates and report changes
            current_services_cmd = run_command(
                ["firewall-cmd", f"--zone={zone}", "--list-services"],
                capture_output=True,
                text=True,
            )
            current_services = set(current_services_cmd.stdout.strip().split())
            current_ports_cmd = run_command(
                ["firewall-cmd", f"--zone={zone}", "--list-ports"], capture_output=True, text=True
            )
            current_ports = set(current_ports_cmd.stdout.strip().split())

            changes_made = False
            for rule in self.config.FIREWALL_RULES:
                rule_type = rule.get("type")
                rule_name = rule.get("name")

                if not rule_type or not rule_name:
                    self.logger.warning(f"Skipping invalid firewall rule: {rule}")
                    continue

                # Construct base command for permanent rules in the target zone
                cmd_base = ["firewall-cmd", "--permanent", f"--zone={zone}"]

                if rule_type == "service":
                    if rule_name not in current_services:
                        self.logger.info(
                            f"Adding firewall service '{rule_name}' to zone '{zone}'..."
                        )
                        run_command(cmd_base + [f"--add-service={rule_name}"])
                        changes_made = True
                    else:
                        self.logger.debug(
                            f"Firewall service '{rule_name}' already allowed in zone '{zone}'."
                        )
                elif rule_type == "port":
                    # Ensure port format is correct (e.g., 8080/tcp, 1234/udp)
                    if "/" not in rule_name or rule_name.split("/")[-1] not in ["tcp", "udp"]:
                        self.logger.warning(
                            f"Skipping invalid port rule format: {rule_name}. Use 'port/protocol'."
                        )
                        continue
                    if rule_name not in current_ports:
                        self.logger.info(f"Adding firewall port '{rule_name}' to zone '{zone}'...")
                        run_command(cmd_base + [f"--add-port={rule_name}"])
                        changes_made = True
                    else:
                        self.logger.debug(
                            f"Firewall port '{rule_name}' already allowed in zone '{zone}'."
                        )
                else:
                    self.logger.warning(f"Skipping unknown firewall rule type: {rule_type}")

            # 4. Reload firewalld if changes were made to the permanent config
            if changes_made:
                self.logger.info("Reloading firewalld to apply permanent changes...")
                # Use --reload for permanent changes
                run_command(["firewall-cmd", "--reload"])
                self.logger.info("Firewall rules applied and reloaded.")
            else:
                self.logger.info("No firewall rule changes needed.")

            # Log final active rules for confirmation
            self.log_firewall_status(zone)

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to configure firewall using firewall-cmd: {e}")
            # Error details logged by run_command
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during firewall configuration: {e}")
            self.logger.exception(e)
            return False

    def configure_fail2ban(self) -> bool:
        """Installs and configures Fail2ban."""
        self.logger.info("Configuring Fail2ban...")
        required_pkgs = ["fail2ban", "fail2ban-firewalld"]  # Need firewalld integration

        # Check if packages are installed, attempt install if missing
        installed_all = True
        missing_pkgs = [pkg for pkg in required_pkgs if not self.is_package_installed(pkg)]

        if missing_pkgs:
            pkg_str = ", ".join(missing_pkgs)
            self.logger.warning(f"Fail2ban packages missing: {pkg_str}. Attempting installation...")
            try:
                # Install all required packages if any are missing
                run_command(["dnf", "install", "-y"] + required_pkgs)
                # Re-verify *all* required packages after install attempt
                if not all(self.is_package_installed(pkg) for pkg in required_pkgs):
                    self.logger.error("Failed to install all required Fail2ban packages.")
                    installed_all = False
                else:
                    self.logger.info("Successfully installed required Fail2ban packages.")
            except Exception as e:
                self.logger.error(f"Failed to install Fail2ban packages: {e}")
                installed_all = False

        if not installed_all:
            return False  # Cannot configure if packages are missing

        # 2. Create local configuration file (jail.local)
        # This overrides defaults in jail.conf without modifying the original
        jail_local_path = Path("/etc/fail2ban/jail.local")
        # jail_conf_path = Path("/etc/fail2ban/jail.conf") # Reference default if needed

        self.logger.info(f"Configuring Fail2ban via {jail_local_path}...")

        # Basic configuration content (adjust as needed)
        config_content = (
            "[DEFAULT]\n"
            "# Ban time in seconds (e.g., 1 hour)\n"
            "bantime = 3600\n"
            "# Time window for retries in seconds (e.g., 10 minutes)\n"
            "findtime = 600\n"
            "# Number of failures before banning\n"
            "maxretry = 5\n"
            "# Backend to use (systemd is preferred on modern systems)\n"
            "backend = systemd\n"
            "# Action to use (firewallcmd-ipset is often efficient with firewalld)\n"
            "banaction = firewallcmd-ipset\n"
            "# Whitelist localhost and potentially other trusted IPs\n"
            "ignoreip = 127.0.0.1/8 ::1\n"
            "\n"
            "[sshd]\n"
            "enabled = true\n"
            "# port can be 'ssh' or the specific port number\n"
            "port = ssh\n"
            "# Fedora/RHEL typically use /var/log/secure for sshd logs\n"
            "logpath = %(sshd_log)s\n"  # Uses fail2ban's default path definition
            "backend = %(backend)s\n"  # Inherit default backend
            "maxretry = 3\n"  # Stricter retry limit for SSH
            "\n"
            # Add other jails as needed (e.g., for nginx, postfix)
            # "[nginx-http-auth]\n"
            # "enabled = true\n"
            # ...
        )

        try:
            # Backup existing jail.local if it exists
            if jail_local_path.exists():
                self.backup_file(jail_local_path)  # Handles errors internally

            # Write the new configuration
            jail_local_path.write_text(config_content)
            self.logger.info(f"Fail2ban configuration written to {jail_local_path}.")

            # Ensure permissions are secure (readable by root only)
            if os.geteuid() == 0:
                os.chmod(jail_local_path, 0o600)  # rw-------
                os.chown(jail_local_path, 0, 0)  # root:root
            else:
                self.logger.warning(
                    "Running as non-root, cannot set secure permissions on jail.local."
                )

        except OSError as e:
            self.logger.error(f"Failed to write or secure Fail2ban config {jail_local_path}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to write or secure Fail2ban config {jail_local_path}: {e}")
            return False

        # 3. Enable and restart Fail2ban service
        self.logger.info("Enabling and restarting Fail2ban service...")
        try:
            fail2ban_service = "fail2ban"
            run_command(["systemctl", "enable", fail2ban_service])
            run_command(["systemctl", "restart", fail2ban_service])

            # Check status after restart attempt
            time.sleep(2)  # Give service time to start
            result = run_command(
                ["systemctl", "is-active", fail2ban_service],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() == "active":
                self.logger.info("Fail2ban service enabled and restarted successfully.")
                # Check client status for enabled jails (optional but useful)
                try:
                    status_result = run_command(
                        ["fail2ban-client", "status"], capture_output=True, text=True
                    )
                    self.logger.info(f"Fail2ban status:\n{status_result.stdout.strip()}")
                except Exception as client_e:
                    self.logger.warning(f"Could not get fail2ban-client status: {client_e}")
            else:
                self.logger.error(
                    f"Fail2ban service failed to start (status: {result.stdout.strip()}). "
                    f"Check logs ('journalctl -u {fail2ban_service}')."
                )
                return False  # Service failing to start is an issue

            return True
        except Exception as e:
            self.logger.error(f"Failed to enable or restart Fail2ban service: {e}")
            return False

    def configure_selinux(self) -> bool:
        """Checks and reports the status of SELinux."""
        self.logger.info("Checking SELinux Status...")
        # Commands needed: sestatus, getenforce
        # policycoreutils provides these

        selinux_utils_pkg = "policycoreutils"
        if not self.is_package_installed(selinux_utils_pkg):
            self.logger.warning(f"'{selinux_utils_pkg}' not found. Attempting installation...")
            try:
                run_command(["dnf", "install", "-y", selinux_utils_pkg])
                if not self.is_package_installed(selinux_utils_pkg):
                    self.logger.error(
                        f"Failed to install {selinux_utils_pkg}. Cannot reliably check SELinux."
                    )
                    return False  # Consider this a failure if tools can't be installed
            except Exception as e:
                self.logger.error(
                    f"Failed to install {selinux_utils_pkg}: {e}. Cannot check SELinux."
                )
                return False

        # Check if commands exist after potential install attempt
        if not command_exists("sestatus") or not command_exists("getenforce"):
            self.logger.error(
                "SELinux commands (sestatus/getenforce) still not found. Cannot check status."
            )
            return False

        try:
            # 2. Check SELinux status using sestatus
            sestatus_result = run_command(["sestatus"], capture_output=True, text=True)
            self.logger.info("SELinux status report (sestatus):")
            # Log each line of the status output for clarity
            for line in sestatus_result.stdout.strip().splitlines():
                self.logger.info(f"  {line.strip()}")

            # 3. Explicitly check current mode (getenforce)
            mode_result = run_command(["getenforce"], capture_output=True, text=True)
            current_mode = mode_result.stdout.strip().lower()
            self.logger.info(f"Current SELinux mode (getenforce): {current_mode.capitalize()}")

            # 4. Report based on mode
            if current_mode == "enforcing":
                self.logger.info("SELinux is running in Enforcing mode (recommended).")
            elif current_mode == "permissive":
                self.logger.warning(
                    "SELinux is running in Permissive mode. Violations logged but not blocked."
                )
                self.logger.warning(
                    "Consider changing to Enforcing mode in /etc/selinux/config and rebooting."
                )
            elif current_mode == "disabled":
                self.logger.error("SELinux is Disabled.")
                self.logger.error(
                    "This significantly reduces system security. Enabling SELinux is strongly recommended."
                )
            else:
                self.logger.warning(f"Unrecognized SELinux mode reported: {current_mode}")

            # Check config file status as well
            selinux_config_path = Path("/etc/selinux/config")
            if selinux_config_path.is_file():
                try:
                    content = selinux_config_path.read_text()
                    config_mode = "unknown"
                    for line in content.splitlines():
                        line = line.strip()
                        if line.startswith("SELINUX=") and not line.startswith("#"):
                            config_mode = line.split("=", 1)[1].lower()
                            break  # Found the relevant line
                    self.logger.info(
                        f"SELinux mode configured in {selinux_config_path}: {config_mode.capitalize()}"
                    )
                    # Compare configured vs current mode (ignoring if currently disabled)
                    if config_mode != current_mode and current_mode != "disabled":
                        self.logger.warning(
                            f"Configured mode ({config_mode}) differs from current mode ({current_mode}). "
                            "A reboot may be required for changes to take effect."
                        )
                except OSError as e:
                    self.logger.warning(f"Could not read {selinux_config_path}: {e}")
                except Exception as e:
                    self.logger.warning(f"Error parsing {selinux_config_path}: {e}")
            else:
                self.logger.warning(f"SELinux configuration file {selinux_config_path} not found.")

            # This phase primarily reports status; return True unless commands fail badly
            return True

        except FileNotFoundError:  # Should be caught earlier, but double-check
            self.logger.error("SELinux commands missing unexpectedly.")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running SELinux status commands: {e}")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while checking SELinux status: {e}")
            self.logger.exception(e)
            return False

    def deploy_user_scripts(self) -> bool:
        """Copies user scripts from the repo to the user's ~/bin directory."""
        self.logger.info("Deploying user scripts...")
        base_repo_dir = self.config.USER_HOME / "github" / "bash" / "linux"

        # Define potential source directories in order of preference
        script_dirs_prefs = [
            base_repo_dir / "fedora" / "_scripts",
            base_repo_dir / "debian" / "_scripts",
            base_repo_dir / "ubuntu" / "_scripts",
            base_repo_dir / "generic" / "_scripts",
        ]
        source_scripts_dir = next((d for d in script_dirs_prefs if d.is_dir()), None)

        if not source_scripts_dir:
            self.logger.warning("No preferred scripts source directory found. Searching...")
            found_scripts = list(base_repo_dir.glob("**/_scripts"))
            if found_scripts:
                source_scripts_dir = found_scripts[0]
                self.logger.warning(
                    f"Using fallback scripts directory found at: {source_scripts_dir}"
                )
            else:
                self.logger.info(
                    "No scripts directory found in repository structure. Skipping script deployment."
                )
                # Not an error if no scripts are expected
                return True
        else:
            self.logger.info(f"Using scripts source directory: {source_scripts_dir}")

        target_bin_dir = self.config.USER_HOME / "bin"
        self.logger.info(f"Deploying scripts from {source_scripts_dir} to {target_bin_dir}...")

        # Ensure target directory exists and is owned by the user
        try:
            target_bin_dir.mkdir(parents=True, exist_ok=True)
            user_info = pwd.getpwnam(self.config.USERNAME)
            os.chown(target_bin_dir, user_info.pw_uid, user_info.pw_gid)
        except KeyError:
            self.logger.error(
                f"User {self.config.USERNAME} not found. Cannot create/chown {target_bin_dir}."
            )
            return False
        except OSError as e:
            self.logger.error(f"Failed to create or set ownership on {target_bin_dir}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to create or set ownership on {target_bin_dir}: {e}")
            return False

        # Ensure rsync is installed
        if not command_exists("rsync"):
            self.logger.warning("rsync command not found. Attempting to install...")
            try:
                run_command(["dnf", "install", "-y", "rsync"])
                if not command_exists("rsync"):
                    self.logger.error("Failed to install rsync. Cannot deploy scripts effectively.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install rsync: {e}. Cannot deploy scripts.")
                return False

        try:
            # Add trailing slash to source for rsync to copy contents, not the dir itself
            rsync_src = str(source_scripts_dir).rstrip("/") + "/"
            rsync_dest = str(target_bin_dir).rstrip("/") + "/"

            # Run rsync command
            # -a: archive (recursive, perms, etc.) -v: verbose -h: human-readable
            # --delete: remove files in dest not in src
            # --checksum: safer sync basis than mod-time/size
            # --no-owner --no-group: let subsequent chown handle final ownership explicitly
            rsync_cmd = [
                "rsync",
                "-ah",
                "--delete",
                "--checksum",
                "--no-owner",
                "--no-group",
                rsync_src,
                rsync_dest,
            ]
            run_command(rsync_cmd)
            self.logger.info(f"Scripts synchronized to {target_bin_dir} using rsync.")

            # Set permissions: make all files executable (755) - adjust if needed
            self.logger.info(f"Setting permissions (755) for files in {target_bin_dir}...")
            # Use find to apply only to files
            run_command(
                ["find", str(target_bin_dir), "-type", "f", "-exec", "chmod", "755", "{}", "+"]
            )

            # Set ownership for the entire target directory recursively
            self.logger.info(f"Setting ownership ({self.config.USERNAME}) for {target_bin_dir}...")
            run_command(
                ["chown", "-R", f"{user_info.pw_uid}:{user_info.pw_gid}", str(target_bin_dir)]
            )

            self.logger.info("User scripts deployed and configured successfully.")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Script deployment using rsync/find/chmod/chown failed: {e}")
            # Error details logged by run_command
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during script deployment: {e}")
            self.logger.exception(e)
            return False

    def home_permissions(self) -> bool:
        """Sets ownership and basic permissions for the user's home directory."""
        self.logger.info("Configuring home directory permissions...")
        user_home = self.config.USER_HOME
        username = self.config.USERNAME

        # 1. Get user info needed for ownership/ACLs
        try:
            user_info = pwd.getpwnam(username)
            user_uid = user_info.pw_uid
            user_gid = user_info.pw_gid
        except KeyError:
            self.logger.error(f"User '{username}' not found. Cannot configure home directory.")
            return False
        except Exception as e:
            self.logger.error(f"Could not get user info for {username}: {e}")
            return False

        # 2. Ensure home directory exists and has correct base ownership
        self.logger.info(f"Verifying ownership and base permissions for {user_home}...")
        if not user_home.is_dir():
            self.logger.warning(f"Home directory {user_home} does not exist. Attempting to create.")
            try:
                user_home.mkdir(parents=True)  # exist_ok=True implied if using parents=True
                os.chown(user_home, user_uid, user_gid)
                # Start with reasonably secure base perms (rwxr-x---) or stricter (rwx------)
                os.chmod(user_home, 0o700)  # Example: rwx------
                self.logger.info(f"Created and set initial ownership/permissions for {user_home}.")
            except OSError as e:
                self.logger.error(
                    f"Failed to create or set initial permissions for {user_home}: {e}"
                )
                return False  # Cannot proceed if home dir creation fails
            except Exception as e:
                self.logger.error(
                    f"Failed to create or set initial permissions for {user_home}: {e}"
                )
                return False

        # 3. Set recursive ownership (ensure everything inside is owned by the user)
        self.logger.info(
            f"Setting recursive ownership for {user_home} to '{username}:{username}'..."
        )
        try:
            run_command(["chown", "-R", f"{user_uid}:{user_gid}", str(user_home)])
            self.logger.info(f"Recursive ownership set for {user_home}.")
        except Exception as e:
            self.logger.error(f"Failed to set recursive ownership for {user_home}: {e}")
            return False  # This is generally critical

        # 4. Set directory permissions (e.g., 700) and file permissions (e.g., 600)
        # This is opinionated; 700/600 is private. 750/640 allows group read.
        # Let's aim for private by default: 700 for dirs, 600 for files.
        self.logger.info(
            "Setting standard permissions (dirs: 700, files: 600) within home directory..."
        )
        try:
            # Set directory permissions (find -type d ...)
            run_command(["find", str(user_home), "-type", "d", "-exec", "chmod", "700", "{}", "+"])
            # Set file permissions (find -type f ...)
            run_command(["find", str(user_home), "-type", "f", "-exec", "chmod", "600", "{}", "+"])
            # Ensure the top-level home directory itself has correct permissions (set above)
            # Re-apply just in case find missed it or changed it (unlikely but safe)
            run_command(["chmod", "700", str(user_home)])
            self.logger.info("Standard directory (700) and file (600) permissions applied.")
        except Exception as e:
            # Log as warning, maybe not critical failure depending on script goal
            self.logger.warning(f"Failed to set standard permissions within {user_home}: {e}")
            # Don't return False here, but log clearly.

        # 5. Optional: Configure default ACLs if needed (requires 'acl' package)
        self.logger.info("Checking for ACL tools...")
        if command_exists("setfacl"):
            # Example: Set default ACLs ensuring user always has rwx, group has rx, others none
            self.logger.info(
                "Setting default ACLs on home directory (user:rwx, group:r-x, other:---)..."
            )
            try:
                # Remove existing default ACLs first to start clean
                # -b removes base ACLs, -k removes default ACLs
                run_command(["setfacl", "-Rbk", str(user_home)], check=False)

                # Set new default ACLs for subdirectories/files
                # And set access ACLs for the home directory itself
                run_command(
                    [
                        "setfacl",
                        "-R",  # Recursive (applies to existing items too)
                        # Default ACLs for new items:
                        "-m",
                        f"d:u:{username}:rwx",  # Default User owner
                        "-m",
                        f"d:g::{user_gid}:r-x",  # Default Primary group (read/execute)
                        "-m",
                        "d:o::---",  # Default Others
                        "-m",
                        "d:m::rwx",  # Default Mask (adjust if needed)
                        # Access ACLs for the home directory itself:
                        "-m",
                        f"u:{username}:rwx",
                        "-m",
                        f"g::{user_gid}:r-x",
                        "-m",
                        "o::---",
                        str(user_home),
                    ]
                )
                self.logger.info("Default ACLs applied successfully.")
            except Exception as e:
                self.logger.warning(f"Failed to apply default ACLs: {e}")
                # Log details if available from run_command
                if hasattr(e, "stderr") and e.stderr:
                    self.logger.warning(f"Stderr: {e.stderr.strip()}")
        else:
            self.logger.info(
                "'setfacl' command not found (package 'acl'). Skipping ACL configuration."
            )

        # Return True even if optional ACL step had warnings, unless a critical step failed
        return True

    def final_cleanup(self) -> bool:
        """Performs final DNF cleanup."""
        self.logger.info("Running final DNF cleanup (autoremove, clean all)...")
        try:
            # Remove packages installed as dependencies that are no longer needed
            run_command(["dnf", "autoremove", "-y"])
            # Remove cached package files and metadata
            run_command(["dnf", "clean", "all"])
            self.logger.info("DNF cleanup completed.")
            return True
        except Exception as e:
            self.logger.error(f"DNF cleanup failed: {e}")
            return False  # Consider cleanup failure an error

    def get_final_info(self) -> Dict[str, Any]:
        """Gathers various pieces of system information for the final summary."""
        self.logger.info("Gathering final system information...")
        info: Dict[str, Any] = {}

        # Helper to run command and return stripped stdout or None on error
        def get_cmd_output(cmd: List[str]) -> Optional[str]:
            try:
                # Use check=True for most informational commands
                result = run_command(cmd, capture_output=True, text=True, check=True, timeout=10)
                return result.stdout.strip()
            except FileNotFoundError:
                self.logger.warning(f"Command '{cmd[0]}' not found for final checks.")
                return "N/A (Cmd Missing)"
            except subprocess.TimeoutExpired:
                self.logger.warning(f"Command '{' '.join(cmd)}' timed out.")
                return "N/A (Timeout)"
            except subprocess.CalledProcessError:
                # Already logged by run_command
                return "N/A (Cmd Error)"
            except Exception as e:
                self.logger.warning(f"Failed running command '{' '.join(cmd)}': {e}")
                return "N/A (Error)"

        # --- Gather Info ---
        info["hostname"] = get_cmd_output(["hostname"])
        info["kernel"] = get_cmd_output(["uname", "-r"])
        info["arch"] = get_cmd_output(["uname", "-m"])
        info["uptime"] = get_cmd_output(["uptime", "-p"])

        # Distribution Info
        os_release_content = get_cmd_output(["cat", "/etc/os-release"])
        if os_release_content and not os_release_content.startswith("N/A"):
            try:
                os_data = {
                    k.strip(): v.strip().strip('"')
                    for k, v in (
                        line.split("=", 1)
                        for line in os_release_content.splitlines()
                        if "=" in line
                    )
                }
                info["distro"] = os_data.get("PRETTY_NAME", "Unknown")
            except Exception:
                info["distro"] = "N/A (Parse Error)"
        else:
            info["distro"] = os_release_content  # Will be "N/A (Cmd Missing)" or similar

        # Disk Usage (Root filesystem)
        df_output = get_cmd_output(["df", "-h", "/"])
        if df_output and not df_output.startswith("N/A"):
            try:
                # Get the last line which contains the filesystem info
                info["disk"] = df_output.splitlines()[-1]
            except IndexError:
                info["disk"] = "N/A (Parse Error)"
        else:
            info["disk"] = df_output  # Assign N/A string

        # Memory Usage
        free_output = get_cmd_output(["free", "-h"])
        if free_output and not free_output.startswith("N/A"):
            try:
                mem_line = next(
                    (line for line in free_output.splitlines() if line.startswith("Mem:")), None
                )
                info["mem"] = mem_line if mem_line else "N/A (Mem line missing)"
            except Exception:
                info["mem"] = "N/A (Parse Error)"
        else:
            info["mem"] = free_output  # Assign N/A string

        # Firewall Status
        firewall_active = get_cmd_output(["systemctl", "is-active", "firewalld"])
        if firewall_active == "active":
            firewall_state = get_cmd_output(["firewall-cmd", "--state"])
            info["fw"] = (
                f"Active ({firewall_state})"
                if firewall_state and not firewall_state.startswith("N/A")
                else "Active (State N/A)"
            )
        elif firewall_active == "inactive":
            info["fw"] = "Inactive"
        else:  # Failed, unknown, activating, etc. or N/A
            info["fw"] = f"Unknown ({firewall_active})"

        # SELinux Status
        info["selinux"] = get_cmd_output(["getenforce"])

        # Service Status (SSH, Fail2ban)
        info["ssh"] = (get_cmd_output(["systemctl", "is-active", "sshd"]) or "N/A").capitalize()
        info["f2b"] = (get_cmd_output(["systemctl", "is-active", "fail2ban"]) or "N/A").capitalize()

        # Check Reboot Status again
        try:
            # Use check=False as return code indicates status, not error
            result = run_command(["needs-restarting", "-r"], check=False, timeout=10)
            info["reboot"] = result.returncode == 1
        except FileNotFoundError:
            info["reboot"] = None  # Indicate check couldn't run
            self.logger.warning("'needs-restarting' command not found for final reboot check.")
        except subprocess.TimeoutExpired:
            info["reboot"] = None
            self.logger.warning("'needs-restarting' check timed out in final summary.")
        except Exception as e:
            info["reboot"] = None  # Indicate check failed for other reason
            self.logger.warning(f"'needs-restarting' check failed in final summary: {e}")

        return info

    def run_all_phases(self):
        """Executes all setup phases sequentially."""
        self.logger.info(f"Starting {APP_NAME} v{VERSION}...")
        self.logger.info(f"Log file: {self.config.LOG_FILE}")

        # Define tasks grouped by logical phase
        tasks_by_phase = [
            (
                "Pre-flight Checks",
                [self.check_root, self.check_network, self.check_fedora, self.save_config_snapshot],
            ),
            (
                "System Update & Packages",
                [
                    self.check_updates,  # Informational, doesn't stop flow
                    self.upgrade_system,
                    self.install_packages,
                    self.check_reboot_needed,  # Informational
                ],
            ),
            (
                "Repo & Shell Setup",
                [self.setup_repos, self.copy_shell_configs, self.set_bash_shell],
            ),
            (
                "Security Hardening",
                [
                    self.configure_ssh,
                    self.configure_firewall,
                    self.configure_fail2ban,
                    self.configure_selinux,  # Informational / Warning
                ],
            ),
            ("User Customization", [self.deploy_user_scripts]),
            ("Home Permissions", [self.home_permissions]),
            ("Final Cleanup", [self.final_cleanup]),
        ]

        overall_success = True
        for phase_name, task_functions in tasks_by_phase:
            self.print_section(phase_name)
            phase_success = True
            for task_func in task_functions:
                try:
                    # Use run_task_with_logging to wrap each function call
                    result = run_task_with_logging(
                        task_func.__name__.replace("_", " ").capitalize(), task_func
                    )
                    # Some functions might return False explicitly on non-critical failure
                    if result is False:
                        self.logger.warning(
                            f"Task '{task_func.__name__}' completed but indicated non-critical failure."
                        )
                        # Decide if non-critical failure stops the script
                        # phase_success = False # Uncomment if False return should fail phase
                except Exception:
                    # Exception already logged by run_task_with_logging
                    self.logger.error(
                        f"Phase '{phase_name}' failed during task '{task_func.__name__}'."
                    )
                    phase_success = False
                    overall_success = False
                    # Option: Stop processing further tasks in this phase
                    break
            # Option: Stop processing further phases if this one failed
            # if not phase_success:
            #     break

        # --- Final Summary ---
        self.print_section("Final Summary")
        final_info = {}
        try:
            final_info = self.get_final_info()
            end_time = time.monotonic()
            elapsed_seconds = end_time - self.start_time
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            reboot_status_msg = "- No reboot required."
            if final_info.get("reboot") is True:
                reboot_status_msg = "! REBOOT RECOMMENDED"
            elif final_info.get("reboot") is None:
                reboot_status_msg = "- Reboot status check failed or inconclusive."

            summary_lines = [
                f"{APP_NAME} v{VERSION} finished.",
                f"Total execution time: {int(hours)}h {int(minutes)}m {int(seconds):.0f}s",
                "--- System Information ---",
                f" Hostname: {final_info.get('hostname', 'N/A')}",
                f" Distro:   {final_info.get('distro', 'N/A')}",
                f" Kernel:   {final_info.get('kernel', 'N/A')}",
                f" Arch:     {final_info.get('arch', 'N/A')}",
                f" Uptime:   {final_info.get('uptime', 'N/A')}",
                "--- Resource Usage ---",
                f" Disk (/): {final_info.get('disk', 'N/A')}",
                f" Memory:   {final_info.get('mem', 'N/A')}",
                "--- Security Status ---",
                f" Firewall: {final_info.get('fw', 'N/A')}",
                f" SELinux:  {final_info.get('selinux', 'N/A')}",
                f" SSH:      {final_info.get('ssh', 'N/A')}",
                f" Fail2ban: {final_info.get('f2b', 'N/A')}",
                "--- Important Notes ---",
                f" Log file: {self.config.LOG_FILE}",
                reboot_status_msg,
                "--- Setup Complete ---",
            ]
            self.logger.info(
                "\n" + "=" * 70 + "\n" + "\n".join(summary_lines) + "\n" + "=" * 70 + "\n"
            )
        except Exception as e:
            # Log error if summary generation itself fails
            self.logger.error(f"Failed to gather or generate final summary: {e}")
            self.logger.exception(e)

        # --- Final Outcome ---
        if overall_success:
            self.logger.info(f"{APP_NAME} script completed successfully.")
        else:
            self.logger.error(f"{APP_NAME} script finished with errors.")

        # Ensure cleanup runs even if phases failed, unless interrupted earlier
        self.cleanup()

        # Exit with appropriate status code
        sys.exit(0 if overall_success else 1)


# --- Signal Handling & Main Execution ---


def signal_handler(signum: int, frame: Any) -> None:
    """Handles termination signals for graceful shutdown."""
    # Use print as logger might be unavailable during shutdown sequence
    print(
        f"\nSignal {signum} ({signal.Signals(signum).name}) received. Initiating cleanup...",
        file=sys.stderr,
    )
    logger = logging.getLogger("fedora_setup")  # Try to get logger
    logger.error(f"Script interrupted by signal {signum}. Initiating cleanup.")

    # Access the global instance for cleanup
    if setup_instance_global and setup_instance_global.perform_cleanup_on_exit:
        try:
            setup_instance_global.cleanup()  # Call the synchronous cleanup
        except Exception as e:
            print(f"Error during cleanup after signal: {e}", file=sys.stderr)
            logger.error(f"Error during cleanup after signal: {e}", exc_info=True)

    # Determine appropriate exit code based on signal
    exit_code = 128 + signum
    if signum == signal.SIGINT:
        exit_code = 130
    elif signum == signal.SIGTERM:
        exit_code = 143

    logger.info(f"Exiting with code {exit_code} due to signal.")
    sys.exit(exit_code)


def main() -> None:
    """Main entry point for the script."""
    global setup_instance_global  # Allow assignment to the global variable

    # Basic root check early before setting up logger or instance
    if os.geteuid() != 0:
        print("Error: This script must be run as root or with sudo.", file=sys.stderr)
        sys.exit(1)

    # Setup signal handlers immediately
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)  # Catch hangup signal too

    setup_instance = None  # Local variable for safety
    try:
        # Initialize the main class (which sets up logging)
        setup_instance = FedoraServerSetup()
        setup_instance_global = setup_instance  # Make instance available to signal handler

        # Start the main process
        setup_instance.run_all_phases()
        # Note: run_all_phases now calls sys.exit itself

    except Exception as e:
        # Catch exceptions happening *outside* run_all_phases
        # (e.g., during __init__, logger setup, or unexpected issues)
        print(
            f"Critical error during script initialization or very early execution: {e}",
            file=sys.stderr,
        )
        # Try to log if logger might exist, otherwise just print traceback
        if setup_instance and hasattr(setup_instance, "logger"):
            setup_instance.logger.critical(
                f"Critical error in main execution block: {e}", exc_info=True
            )
        else:
            import traceback

            traceback.print_exc()

        # Attempt cleanup if instance exists, even if initialization partially failed
        if setup_instance:
            print("Attempting cleanup after critical error...", file=sys.stderr)
            setup_instance.cleanup()

        sys.exit(1)  # Exit with error code


if __name__ == "__main__":
    main()
