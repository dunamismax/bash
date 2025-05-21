#!/usr/bin/env python3

import asyncio
import datetime
import filecmp
import gzip
import logging
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, TypeVar

# First, check if Nala is installed, and if not, install it
try:
    subprocess.check_call(
        ["which", "nala"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print("Nala is already installed.")
except subprocess.CalledProcessError:
    print("Nala not found. Installing Nala...")
    try:
        subprocess.check_call(["apt", "install", "nala", "-y"])
        print("Nala installed successfully.")
    except Exception as e:
        print(f"Error installing Nala: {e}")
        print("Continuing with apt instead of Nala.")

try:
    import rich.console
    import rich.logging
    from rich.console import Console
    from rich.logging import RichHandler
except ImportError:
    print("Required libraries not found. Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
        print("Dependencies installed successfully. Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        print("Please install the required packages manually: pip install rich")
        sys.exit(1)

console = Console()
OPERATION_TIMEOUT = 300  # default timeout in seconds
APP_NAME = "Ubuntu Server Setup & Hardening"
VERSION = "1.0.0"

SETUP_STATUS = {
    "preflight": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "repo_shell": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "user_custom": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "certs_perf": {"status": "pending", "message": ""},
    "permissions": {"status": "pending", "message": ""},
    "cleanup_final": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}

T = TypeVar("T")


@dataclass
class Config:
    LOG_FILE: str = "/var/log/ubuntu_setup.log"
    USERNAME: str = "sawyer"
    USER_HOME: Path = field(default_factory=lambda: Path("/home/sawyer"))

    PACKAGES: List[str] = field(
        default_factory=lambda: [
            # Shells and editors
            "bash",
            "vim",
            "vim-nox",
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
            "ufw",
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
            "wireguard",
            "ethtool",
            "ca-certificates",
            "gnupg2",
            "gpg",
            "certbot",
            "acl",
            "apparmor-utils",
            # Core utilities
            "python3",
            "python3-pip",
            "python3-venv",
            "cron",
            "at",
            "parallel",
            "moreutils",
            "util-linux",
            "kbd",
            "debsums",
            "nala",
            "dnsutils",
            "apt-transport-https",
            "apt-file",
            "apt-utils",
            "debian-goodies",
            "locales",
            "systemd-timesyncd",
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
            "htop",
            "glances",
            "byobu",
            "zoxide",
            "direnv",
            "micro",
            "hexyl",
            "sd",
            "duf",
            # Development tools
            "gcc",
            "g++",
            "make",
            "cmake",
            "python3-dev",
            "libssl-dev",
            "shellcheck",
            "libffi-dev",
            "zlib1g-dev",
            "libreadline-dev",
            "libbz2-dev",
            "libncurses-dev",
            "build-essential",
            "pkg-config",
            "manpages-dev",
            "git-extras",
            "clang",
            "llvm",
            "golang",
            "rust-all",
            "cargo",
            "gdb",
            "strace",
            "ltrace",
            # Network utilities
            "traceroute",
            "mtr",
            "dnsutils",
            "iproute2",
            "iputils-ping",
            "whois",
            "dnsmasq",
            "wireguard",
            "nftables",
            "ipcalc",
            "netcat-openbsd",
            "socat",
            "bridge-utils",
            "nload",
            "oping",
            "arping",
            "httpie",
            "speedtest-cli",
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
            # Container and development
            "podman",
            "buildah",
            "skopeo",
            "nodejs",
            "npm",
            "autoconf",
            "automake",
            "libtool",
            "docker.io",
            "docker-compose",
            "lxc",
            "ansible",
            "cloud-init",
            # Debugging and development utilities
            "strace",
            "ltrace",
            "valgrind",
            "gdb",
            "lsof",
            "socat",
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
            "mariadb-client",
            "postgresql-client",
            "sqlite3",
            "redis-tools",
            "mysql-client",
            # Virtualization
            "qemu-kvm",
            "libvirt-daemon-system",
            "virt-manager",
            "virt-viewer",
            "virt-top",
            "bridge-utils",
            "virtinst",
            "libosinfo-bin",
            "libguestfs-tools",
            # File compression and archiving
            "unzip",
            "zip",
            "tar",
            "pigz",
            "lz4",
            "xz-utils",
            "bzip2",
            "p7zip-full",
            "zstd",
            "gzip",
            "cpio",
            "pax",
            "rzip",
            "arj",
            "unrar",
            "lzop",
            # Terminal multiplexers and utilities
            "mc",
            "ranger",
            "tmux",
            "byobu",
            "multitail",
            "ccze",
            "colordiff",
            "progress",
            "pv",
            "rlwrap",
            "reptyr",
            "expect",
            "dialog",
            # Text processing
            "jq",
            "yq",
            "csvkit",
            "gawk",
            "dos2unix",
            "wdiff",
            "colordiff",
            "diffutils",
            "pandoc",
            "highlight",
            "groff",
            "xmlstarlet",
            "html-xml-utils",
            "xsltproc",
            # Backup and sync
            "restic",
            "duplicity",
            "borgbackup",
            "rclone",
            "rsnapshot",
            "rdiff-backup",
            "syncthing",
            "unison",
            "backintime-common",
            "timeshift",
            # Monitoring and configuration management
            "prometheus-node-exporter",
            "collectd-core",
            "nagios-plugins-basic",
            "puppet-agent",
            "ansible",
            "cfengine3",
            # Web servers and proxies
            "nginx",
            "apache2-utils",
            "haproxy",
            "squid",
            "lighttpd",
            "tinyproxy",
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

    FIREWALL_PORTS: List[str] = field(default_factory=lambda: ["22", "80", "443"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def setup_logger(log_file: Union[str, Path]) -> logging.Logger:
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    console_handler = RichHandler(console=console, rich_tracebacks=True)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    try:
        os.chmod(str(log_file), 0o600)
    except Exception as e:
        logger.warning(f"Could not set permissions on log file {log_file}: {e}")
    return logger


async def signal_handler_async(signum: int, frame: Any) -> None:
    try:
        sig_name = (
            signal.Signals(signum).name
            if hasattr(signal, "Signals")
            else f"signal {signum}"
        )
        logger = logging.getLogger("ubuntu_setup")
        logger.error(f"Script interrupted by {sig_name}. Initiating cleanup.")
    except Exception as e:
        logger.error(f"Error during signal handling: {e}")

    try:
        if "setup_instance" in globals():
            await globals()["setup_instance"].cleanup_async()
    except Exception as e:
        logger.error(f"Error during cleanup after signal: {e}")
    try:
        loop = asyncio.get_running_loop()
        tasks = [
            task
            for task in asyncio.all_tasks(loop)
            if task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()
    except Exception as e:
        logger.error(f"Error stopping event loop: {e}")
    sys.exit(
        130
        if signum == signal.SIGINT
        else 143
        if signum == signal.SIGTERM
        else 128 + signum
    )


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(
            signum,
            lambda sig=signum: asyncio.create_task(signal_handler_async(sig, None)),
        )


async def download_file_async(
    url: str, dest: Union[str, Path], timeout: int = 300
) -> None:
    dest = Path(dest)
    logger = logging.getLogger("ubuntu_setup")
    if dest.exists():
        logger.info(f"File {dest} already exists; skipping download.")
        return
    logger.info(f"Downloading {url} to {dest}...")
    loop = asyncio.get_running_loop()
    try:
        if shutil.which("wget"):
            proc = await asyncio.create_subprocess_exec(
                "wget",
                "-q",
                "--show-progress",
                url,
                "-O",
                str(dest),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode != 0:
                raise Exception(f"wget failed with return code {proc.returncode}")
        elif shutil.which("curl"):
            proc = await asyncio.create_subprocess_exec(
                "curl",
                "-L",
                "-o",
                str(dest),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode != 0:
                raise Exception(f"curl failed with return code {proc.returncode}")
        else:
            import urllib.request

            await loop.run_in_executor(None, urllib.request.urlretrieve, url, dest)
        logger.info(f"Download complete: {dest}")
    except asyncio.TimeoutError:
        logger.error(f"Download timed out after {timeout} seconds")
        if dest.exists():
            dest.unlink()
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if dest.exists():
            dest.unlink()
        raise


async def run_with_progress_async(
    description: str,
    func: Callable[..., Any],
    *args: Any,
    task_name: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{description} in progress...",
        }
    logger = logging.getLogger("ubuntu_setup")
    logger.info(f"Starting: {description}")
    start = time.time()
    try:
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        elapsed = time.time() - start
        logger.info(f"✓ {description} completed in {elapsed:.2f}s")
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "success",
                "message": f"Completed in {elapsed:.2f}s",
            }
        return result
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"✗ {description} failed in {elapsed:.2f}s: {e}")
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "failed",
                "message": f"Failed after {elapsed:.2f}s: {str(e)}",
            }
        raise


async def run_command_async(
    cmd: List[str],
    capture_output: bool = False,
    text: bool = False,
    check: bool = True,
    timeout: Optional[int] = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    logger = logging.getLogger("ubuntu_setup")
    logger.debug(f"Running command: {' '.join(cmd)}")
    stdout = asyncio.subprocess.PIPE if capture_output else None
    stderr = asyncio.subprocess.PIPE if capture_output else None
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=stdout, stderr=stderr)
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        if text and stdout_data is not None:
            stdout_data = stdout_data.decode("utf-8")
        if text and stderr_data is not None:
            stderr_data = stderr_data.decode("utf-8")
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_data if capture_output else None,
            stderr=stderr_data if capture_output else None,
        )
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout_data, stderr=stderr_data
            )
        return result
    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise Exception(f"Command timed out: {' '.join(cmd)}")


async def command_exists_async(cmd: str) -> bool:
    try:
        await run_command_async(["which", cmd], check=True, capture_output=True)
        return True
    except Exception:
        return False


class UbuntuServerSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.time()
        self._current_task = None

    async def print_section_async(self, title: str) -> None:
        self.logger.info(f"--- {title} ---")

    async def backup_file_async(self, file_path: Union[str, Path]) -> Optional[str]:
        file_path = Path(file_path)
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = file_path.with_suffix(file_path.suffix + f".bak.{timestamp}")
        try:
            shutil.copy2(file_path, backup_path)
            self.logger.debug(f"Backed up {file_path} to {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.warning(f"Failed to backup {file_path}: {e}")
            return None

    async def cleanup_async(self) -> None:
        self.logger.info("Performing cleanup before exit...")
        try:
            tmp = Path(tempfile.gettempdir())
            for item in tmp.glob("ubuntu_setup_*"):
                try:
                    if item.is_file():
                        item.unlink()
                    else:
                        shutil.rmtree(item)
                except Exception as e:
                    self.logger.warning(f"Failed to clean up {item}: {e}")
            try:
                await self.rotate_logs_async()
            except Exception as e:
                self.logger.warning(f"Failed to rotate logs: {e}")
            self.logger.info("Cleanup completed.")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

    async def rotate_logs_async(self, log_file: Optional[str] = None) -> bool:
        if log_file is None:
            log_file = self.config.LOG_FILE
        log_path = Path(log_file)
        if not log_path.is_file():
            self.logger.warning(f"Log file {log_path} does not exist.")
            return False
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rotated = f"{log_path}.{timestamp}.gz"
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self._compress_log(log_path, rotated)
            )
            self.logger.info(f"Log rotated to {rotated}")
            return True
        except Exception as e:
            self.logger.warning(f"Log rotation failed: {e}")
            return False

    def _compress_log(self, log_path: Path, rotated_path: str) -> None:
        with open(log_path, "rb") as f_in, gzip.open(rotated_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        open(log_path, "w").close()

    async def has_internet_connection_async(self) -> bool:
        try:
            await run_command_async(
                ["ping", "-c", "1", "-W", "5", "8.8.8.8"],
                capture_output=True,
                check=False,
            )
            return True
        except Exception:
            return False

    async def phase_preflight(self) -> bool:
        await self.print_section_async("Pre-flight Checks & Backups")
        try:
            await run_with_progress_async(
                "Checking for root privileges",
                self.check_root_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Checking network connectivity",
                self.check_network_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Verifying Ubuntu distribution",
                self.check_ubuntu_async,
                task_name="preflight",
            )
            await run_with_progress_async(
                "Saving configuration snapshot",
                self.save_config_snapshot_async,
                task_name="preflight",
            )
            return True
        except Exception as e:
            self.logger.error(f"Pre-flight phase failed: {e}")
            return False

    async def check_root_async(self) -> None:
        if os.geteuid() != 0:
            self.logger.error("Script must be run as root.")
            sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    async def check_network_async(self) -> None:
        self.logger.info("Verifying network connectivity...")
        if await self.has_internet_connection_async():
            self.logger.info("Network connectivity verified.")
        else:
            self.logger.error("No network connectivity. Please check your settings.")
            sys.exit(1)

    async def check_ubuntu_async(self) -> None:
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    os_release = f.read()
                if "Ubuntu" in os_release:
                    try:
                        pretty_name = next(
                            (
                                line.split("=")[1].strip().strip('"')
                                for line in os_release.splitlines()
                                if line.startswith("PRETTY_NAME=")
                            ),
                            "Ubuntu",
                        )
                        self.logger.info(f"Detected Ubuntu: {pretty_name}")
                    except Exception:
                        self.logger.info("Detected Ubuntu")
                else:
                    self.logger.warning(
                        "This may not be an Ubuntu system. Some features may not work."
                    )
            else:
                self.logger.warning(
                    "This may not be an Ubuntu system. Some features may not work."
                )
        except Exception as e:
            self.logger.warning(f"Could not verify distribution: {e}")

    async def save_config_snapshot_async(self) -> Optional[str]:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = Path("/var/backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot_file = backup_dir / f"ubuntu_config_snapshot_{timestamp}.tar.gz"
        try:
            loop = asyncio.get_running_loop()
            files_added = []

            def create_archive():
                nonlocal files_added
                with tarfile.open(snapshot_file, "w:gz") as tar:
                    for config_path in [
                        "/etc/apt/sources.list.d",
                        "/etc/fstab",
                        "/etc/default/grub",
                        "/etc/hosts",
                        "/etc/ssh/sshd_config",
                    ]:
                        path = Path(config_path)
                        if path.exists():
                            tar.add(str(path), arcname=path.name)
                            files_added.append(str(path))

            await loop.run_in_executor(None, create_archive)
            if files_added:
                for path in files_added:
                    self.logger.info(f"Included {path} in snapshot.")
                self.logger.info(f"Configuration snapshot saved: {snapshot_file}")
                return str(snapshot_file)
            else:
                self.logger.warning("No configuration files found for snapshot.")
                return None
        except Exception as e:
            self.logger.warning(f"Failed to create config snapshot: {e}")
            return None

    async def phase_system_update(self) -> bool:
        await self.print_section_async("System Update & Basic Configuration")
        status = True
        if not await run_with_progress_async(
            "Updating package repositories",
            self.update_repos_async,
            task_name="system_update",
        ):
            status = False
        if not await run_with_progress_async(
            "Upgrading system packages",
            self.upgrade_system_async,
            task_name="system_update",
        ):
            status = False
        success, failed = await run_with_progress_async(
            "Installing required packages",
            self.install_packages_async,
            task_name="system_update",
        )
        if failed and len(failed) > len(self.config.PACKAGES) * 0.1:
            self.logger.error(
                f"Failed to install too many packages: {', '.join(failed)}"
            )
            status = False
        return status

    async def update_repos_async(self) -> bool:
        try:
            self.logger.info("Updating package repositories using nala...")
            await run_command_async(["nala", "update"])
            self.logger.info("Package repositories updated successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Repository update failed: {e}")
            return False

    async def upgrade_system_async(self) -> bool:
        try:
            self.logger.info("Upgrading system packages using nala...")
            await run_command_async(["nala", "upgrade", "-y"])
            self.logger.info("System upgrade complete.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System upgrade failed: {e}")
            return False

    # Inside the UbuntuServerSetup class
    async def install_packages_async(self) -> Tuple[List[str], List[str]]:
        """
        Install packages in batches to avoid dependency resolution errors.
        Returns:
            Tuple of (successful installs, failed installs)
        """
        self.logger.info("Checking for required packages...")
        missing, success, failed = [], [], []

        # First run cleanup and update operations
        await self._prepare_package_system()

        # Check which packages are already installed
        for pkg in self.config.PACKAGES:
            try:
                result = await run_command_async(
                    ["dpkg", "-s", pkg], check=False, capture_output=True
                )
                if (
                    result.returncode == 0
                    and b"Status: install ok installed" in result.stdout
                ):
                    self.logger.debug(f"Package already installed: {pkg}")
                    success.append(pkg)
                else:
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)

        if not missing:
            self.logger.info("All required packages are already installed.")
            return success, failed

        # Create smaller batches (5 packages at a time)
        batch_size = 5
        batches = [
            missing[i : i + batch_size] for i in range(0, len(missing), batch_size)
        ]
        self.logger.info(
            f"Installing {len(missing)} packages in {len(batches)} batches of up to {batch_size} packages each"
        )

        # Process each batch
        for batch_num, batch in enumerate(batches, 1):
            self.logger.info(
                f"Processing batch {batch_num}/{len(batches)}: {' '.join(batch)}"
            )

            # Run cleanup every 5 batches
            if batch_num % 5 == 0:
                await self._prepare_package_system()

            # Try to install the batch with nala
            try:
                self.logger.info(f"Installing batch with nala: {' '.join(batch)}")
                await run_command_async(
                    ["nala", "install", "-y", "--no-install-recommends"] + batch
                )
                for pkg in batch:
                    result = await run_command_async(
                        ["dpkg", "-s", pkg], check=False, capture_output=True
                    )
                    if (
                        result.returncode == 0
                        and b"Status: install ok installed" in result.stdout
                    ):
                        success.append(pkg)
                        self.logger.info(f"Successfully installed {pkg}")
                    else:
                        failed.append(pkg)
            except Exception as e:
                self.logger.warning(f"Batch installation failed with nala: {e}")
                # Try individual packages
                for pkg in batch:
                    if pkg not in success:
                        if await self._install_single_package_async(pkg):
                            success.append(pkg)
                        else:
                            failed.append(pkg)

            # Short pause between batches
            await asyncio.sleep(2)

        # Final cleanup
        await run_command_async(["nala", "autoremove", "-y"], check=False)

        # Log summary
        self.logger.info(f"Successfully installed {len(success)} packages.")
        if failed:
            self.logger.warning(
                f"Failed to install {len(failed)} packages: {', '.join(failed)}"
            )

        return success, failed

    async def _prepare_package_system(self) -> None:
        """
        Prepare the package system by cleaning up and fixing any issues,
        using the correct Nala commands and options
        """
        self.logger.info("Running package system cleanup and preparation...")
        try:
            # Fix broken packages
            await run_command_async(
                ["nala", "install", "--fix-broken", "-y"], check=False
            )

            # Configure any pending packages
            await run_command_async(["dpkg", "--configure", "-a"], check=False)

            # Clean package cache
            await run_command_async(["nala", "clean"], check=False)

            # Update package lists
            await run_command_async(["nala", "update"], check=False)

            self.logger.info("Package system preparation completed")
        except Exception as e:
            self.logger.warning(f"Package system preparation encountered issues: {e}")

    async def _install_single_package_async(self, pkg: str) -> bool:
        """
        Try to install a single package with multiple methods

        Args:
            pkg: Package to install

        Returns:
            True if installation was successful, False otherwise
        """
        # Check if already installed first
        result = await run_command_async(
            ["dpkg", "-s", pkg], check=False, capture_output=True
        )
        if result.returncode == 0 and b"Status: install ok installed" in result.stdout:
            self.logger.info(f"Package {pkg} is already installed")
            return True

        # Try different installation methods
        methods = [
            ["nala", "install", "-y", "--no-install-recommends", pkg],
            ["nala", "install", "-y", "--fix-broken", pkg],
            ["apt-get", "install", "-y", "--no-install-recommends", pkg],
            [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "--fix-missing",
                pkg,
            ],
        ]

        for method in methods:
            try:
                self.logger.info(
                    f"Trying to install {pkg} with command: {' '.join(method)}"
                )
                await run_command_async(method)

                # Verify installation
                result = await run_command_async(
                    ["dpkg", "-s", pkg], check=False, capture_output=True
                )
                if (
                    result.returncode == 0
                    and b"Status: install ok installed" in result.stdout
                ):
                    self.logger.info(f"Successfully installed {pkg} with {method[0]}")
                    return True

                # Fix dependencies if needed
                if "nala" in method[0]:
                    await run_command_async(
                        ["nala", "install", "--fix-broken", "-y"], check=False
                    )
                else:
                    await run_command_async(
                        ["apt-get", "--fix-broken", "install", "-y"], check=False
                    )

            except Exception as e:
                self.logger.warning(f"Failed to install {pkg} with {method[0]}: {e}")

                # Try to fix broken packages after each failed attempt
                try:
                    if "nala" in method[0]:
                        await run_command_async(
                            ["nala", "install", "--fix-broken", "-y"], check=False
                        )
                    else:
                        await run_command_async(
                            ["apt-get", "--fix-broken", "install", "-y"], check=False
                        )
                except Exception:
                    pass

        # Last resort: try to download the deb and install manually
        try:
            self.logger.info(
                f"Attempting to install {pkg} with apt-get download and dpkg"
            )

            # Create a temporary directory
            temp_dir = tempfile.mkdtemp(prefix="pkg_install_")
            try:
                # Download the package
                await run_command_async(
                    ["apt-get", "download", pkg], check=False, cwd=temp_dir
                )

                # Find the downloaded deb file
                deb_files = list(Path(temp_dir).glob("*.deb"))
                if deb_files:
                    # Install with dpkg
                    await run_command_async(
                        ["dpkg", "-i", "--force-depends", str(deb_files[0])],
                        check=False,
                    )
                    await run_command_async(
                        ["nala", "install", "--fix-broken", "-y"], check=False
                    )

                    # Verify installation
                    result = await run_command_async(
                        ["dpkg", "-s", pkg], check=False, capture_output=True
                    )
                    if (
                        result.returncode == 0
                        and b"Status: install ok installed" in result.stdout
                    ):
                        self.logger.info(f"Successfully installed {pkg} with dpkg")
                        return True
            finally:
                # Clean up
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            self.logger.warning(f"Failed last-resort install of {pkg}: {e}")

        self.logger.error(f"All installation methods failed for {pkg}")
        return False

    async def phase_repo_shell_setup(self) -> bool:
        await self.print_section_async("Repository & Shell Setup")
        status = True
        if not await run_with_progress_async(
            "Setting up GitHub repositories",
            self.setup_repos_async,
            task_name="repo_shell",
        ):
            status = False
        if not await run_with_progress_async(
            "Copying shell configurations",
            self.copy_shell_configs_async,
            task_name="repo_shell",
        ):
            status = False
        if not await run_with_progress_async(
            "Setting default shell to bash",
            self.set_bash_shell_async,
            task_name="repo_shell",
        ):
            status = False
        return status

    async def setup_repos_async(self) -> bool:
        gh_dir = self.config.USER_HOME / "github"
        gh_dir.mkdir(exist_ok=True)
        all_success = True
        repos = ["bash", "python"]
        for repo in repos:
            repo_dir = gh_dir / repo
            if (repo_dir / ".git").is_dir():
                self.logger.info(f"Repository '{repo}' exists; pulling updates...")
                try:
                    await run_command_async(["git", "-C", str(repo_dir), "pull"])
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to update repository '{repo}'.")
                    all_success = False
            else:
                self.logger.info(f"Cloning repository '{repo}'...")
                try:
                    await run_command_async(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            str(repo_dir),
                        ]
                    )
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Failed to clone repository '{repo}'.")
                    all_success = False
        try:
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(gh_dir),
                ]
            )
        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to set ownership of {gh_dir}.")
            all_success = False
        return all_success

    async def copy_shell_configs_async(self) -> bool:
        source_dir = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "ubuntu" / "dotfiles"
        )
        if not source_dir.is_dir():
            debian_dir = (
                self.config.USER_HOME
                / "github"
                / "bash"
                / "linux"
                / "debian"
                / "dotfiles"
            )
            if debian_dir.is_dir():
                source_dir = debian_dir
                self.logger.info(f"Using Debian dotfiles from {source_dir}.")
            else:
                fallback_dir = (
                    self.config.USER_HOME
                    / "github"
                    / "bash"
                    / "linux"
                    / "fedora"
                    / "dotfiles"
                )
                if not fallback_dir.is_dir():
                    self.logger.error(f"No suitable dotfiles found.")
                    return False
                source_dir = fallback_dir
                self.logger.info(
                    f"Using Fedora dotfiles as fallback from {source_dir}."
                )

        destination_dirs = [self.config.USER_HOME, Path("/root")]
        overall = True
        for file_name in [".bashrc", ".profile"]:
            src = source_dir / file_name
            if not src.is_file():
                self.logger.warning(f"Source file {src} not found; skipping.")
                continue
            for dest_dir in destination_dirs:
                dest = dest_dir / file_name
                loop = asyncio.get_running_loop()
                files_identical = dest.is_file() and await loop.run_in_executor(
                    None, lambda: filecmp.cmp(src, dest)
                )
                if dest.is_file() and files_identical:
                    self.logger.info(f"File {dest} is already up-to-date.")
                else:
                    try:
                        if dest.is_file():
                            await self.backup_file_async(dest)
                        await loop.run_in_executor(
                            None, lambda: shutil.copy2(src, dest)
                        )
                        owner = (
                            f"{self.config.USERNAME}:{self.config.USERNAME}"
                            if dest_dir == self.config.USER_HOME
                            else "root:root"
                        )
                        await run_command_async(["chown", owner, str(dest)])
                        self.logger.info(f"Copied {src} to {dest}.")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy {src} to {dest}: {e}")
                        overall = False
        return overall

    async def set_bash_shell_async(self) -> bool:
        if not await command_exists_async("bash"):
            self.logger.info("Bash not found; installing...")
            try:
                await run_command_async(["nala", "install", "-y", "bash"])
            except subprocess.CalledProcessError:
                self.logger.warning("Bash installation failed.")
                return False
        shells_file = Path("/etc/shells")
        loop = asyncio.get_running_loop()
        try:
            if shells_file.exists():
                content = await loop.run_in_executor(None, shells_file.read_text)
                if "/bin/bash" not in content:
                    await loop.run_in_executor(
                        None, lambda: shells_file.open("a").write("/bin/bash\n")
                    )
                    self.logger.info("Added /bin/bash to /etc/shells.")
            else:
                await loop.run_in_executor(
                    None, lambda: shells_file.write_text("/bin/bash\n")
                )
                self.logger.info("Created /etc/shells with /bin/bash.")
        except Exception as e:
            self.logger.warning(f"Failed to update /etc/shells: {e}")
            return False
        try:
            await run_command_async(["chsh", "-s", "/bin/bash", self.config.USERNAME])
            self.logger.info(
                f"Default shell for {self.config.USERNAME} set to /bin/bash."
            )
            return True
        except subprocess.CalledProcessError:
            self.logger.warning(
                f"Failed to set default shell for {self.config.USERNAME}."
            )
            return False

    async def phase_security_hardening(self) -> bool:
        await self.print_section_async("Security Hardening")
        status = True
        if not await run_with_progress_async(
            "Configuring SSH", self.configure_ssh_async, task_name="security"
        ):
            status = False
        if not await run_with_progress_async(
            "Configuring firewall", self.configure_firewall_async, task_name="security"
        ):
            status = False
        if not await run_with_progress_async(
            "Configuring Fail2ban", self.configure_fail2ban_async, task_name="security"
        ):
            status = False
        if not await run_with_progress_async(
            "Configuring AppArmor", self.configure_apparmor_async, task_name="security"
        ):
            status = False
        return status

    async def configure_ssh_async(self) -> bool:
        try:
            result = await run_command_async(
                ["dpkg", "-l", "openssh-server"], check=False, capture_output=True
            )
            if result.returncode != 0:
                self.logger.info("openssh-server not installed. Installing...")
                try:
                    await run_command_async(["nala", "install", "-y", "openssh-server"])
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install OpenSSH Server.")
                    return False
        except Exception:
            self.logger.error("Failed to check for OpenSSH Server installation.")
            return False
        try:
            await run_command_async(["systemctl", "enable", "--now", "ssh"])
        except subprocess.CalledProcessError:
            self.logger.error("Failed to enable/start SSH service.")
            return False
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.is_file():
            self.logger.error(f"SSHD configuration file not found: {sshd_config}")
            return False
        await self.backup_file_async(sshd_config)
        try:
            loop = asyncio.get_running_loop()
            lines = await loop.run_in_executor(
                None, lambda: sshd_config.read_text().splitlines()
            )
            for key, val in self.config.SSH_CONFIG.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {val}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key} {val}")
            await loop.run_in_executor(
                None, lambda: sshd_config.write_text("\n".join(lines) + "\n")
            )
            await run_command_async(["systemctl", "restart", "ssh"])
            self.logger.info("SSH configuration updated and service restarted.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update SSH configuration: {e}")
            return False

    async def configure_firewall_async(self) -> bool:
        if not await command_exists_async("ufw"):
            self.logger.error("ufw not found. Installing ufw...")
            try:
                await run_command_async(["nala", "install", "-y", "ufw"])
                if not await command_exists_async("ufw"):
                    self.logger.error("ufw installation failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to install ufw: {e}")
                return False
        try:
            await run_command_async(["ufw", "default", "deny", "incoming"])
            await run_command_async(["ufw", "default", "allow", "outgoing"])
            for port in self.config.FIREWALL_PORTS:
                await run_command_async(["ufw", "allow", port])
                self.logger.info(f"Allowed TCP port {port}.")
            await run_command_async(["ufw", "--force", "enable"])
            self.logger.info("ufw enabled and configured.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to configure firewall: {e}")
            return False

    async def configure_fail2ban_async(self) -> bool:
        # Install fail2ban if not already installed
        try:
            result = await run_command_async(
                ["dpkg", "-l", "fail2ban"], check=False, capture_output=True
            )
            if result.returncode != 0:
                self.logger.info("fail2ban not installed. Installing...")
                try:
                    await run_command_async(["nala", "install", "-y", "fail2ban"])
                except subprocess.CalledProcessError:
                    self.logger.error("Failed to install fail2ban.")
                    return False
        except Exception:
            self.logger.error("Failed to check for fail2ban installation.")
            return False

        jail_local = Path("/etc/fail2ban/jail.local")
        jail_local.parent.mkdir(parents=True, exist_ok=True)
        config_content = (
            "[DEFAULT]\n"
            "bantime  = 600\n"
            "findtime = 600\n"
            "maxretry = 3\n"
            "backend  = systemd\n"
            "usedns   = warn\n\n"
            "[sshd]\n"
            "enabled  = true\n"
            "port     = ssh\n"
            "logpath  = /var/log/auth.log\n"
            "maxretry = 3\n"
        )
        try:
            if jail_local.is_file():
                await self.backup_file_async(jail_local)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: jail_local.write_text(config_content)
            )
            self.logger.info("Fail2ban configuration written.")
            await run_command_async(["systemctl", "enable", "fail2ban"])
            await run_command_async(["systemctl", "restart", "fail2ban"])
            self.logger.info("Fail2ban service enabled and restarted.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to configure Fail2ban: {e}")
            return False

    async def configure_apparmor_async(self) -> bool:
        try:
            self.logger.info("Checking AppArmor status...")
            # Install AppArmor if not already installed
            try:
                result = await run_command_async(
                    ["dpkg", "-l", "apparmor"], check=False, capture_output=True
                )
                if result.returncode != 0:
                    self.logger.info("AppArmor not installed. Installing...")
                    try:
                        await run_command_async(
                            ["nala", "install", "-y", "apparmor", "apparmor-utils"]
                        )
                    except subprocess.CalledProcessError:
                        self.logger.error("Failed to install AppArmor.")
                        return False
            except Exception:
                self.logger.error("Failed to check for AppArmor installation.")
                return False

            # Check AppArmor status
            result = await run_command_async(
                ["aa-status"], capture_output=True, text=True, check=False
            )
            apparmor_status = result.stdout.strip()
            self.logger.info(f"Current AppArmor status: {apparmor_status}")

            # Ensure AppArmor is enabled and running
            await run_command_async(["systemctl", "enable", "--now", "apparmor"])
            self.logger.info("AppArmor enabled and active.")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to configure AppArmor: {e}")
            return False

    async def phase_user_customization(self) -> bool:
        await self.print_section_async("User Customization & Script Deployment")
        status = True
        if not await run_with_progress_async(
            "Deploying user scripts",
            self.deploy_user_scripts_async,
            task_name="user_custom",
        ):
            status = False
        return status

    async def deploy_user_scripts_async(self) -> bool:
        src = (
            self.config.USER_HOME / "github" / "bash" / "linux" / "ubuntu" / "_scripts"
        )
        if not src.is_dir():
            debian_src = (
                self.config.USER_HOME
                / "github"
                / "bash"
                / "linux"
                / "debian"
                / "_scripts"
            )
            if debian_src.is_dir():
                src = debian_src
                self.logger.info(f"Using Debian scripts from {src}.")
            else:
                fedora_src = (
                    self.config.USER_HOME
                    / "github"
                    / "bash"
                    / "linux"
                    / "fedora"
                    / "_scripts"
                )
                if not fedora_src.is_dir():
                    self.logger.error(f"Script source directory not found.")
                    return False
                src = fedora_src
                self.logger.info(f"Using Fedora scripts as fallback from {src}.")

        target = self.config.USER_HOME / "bin"
        target.mkdir(exist_ok=True)
        try:
            await run_command_async(
                ["rsync", "-ah", "--delete", f"{src}/", f"{target}/"]
            )
            await run_command_async(
                ["find", str(target), "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(target),
                ]
            )
            self.logger.info("User scripts deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Script deployment failed: {e}")
            return False

    async def phase_permissions(self) -> bool:
        await self.print_section_async("Permissions Setup")
        status = True
        if not await run_with_progress_async(
            "Configuring home directory permissions",
            self.home_permissions_async,
            task_name="permissions",
        ):
            status = False
        return status

    async def home_permissions_async(self) -> bool:
        try:
            await run_command_async(
                [
                    "chown",
                    "-R",
                    f"{self.config.USERNAME}:{self.config.USERNAME}",
                    str(self.config.USER_HOME),
                ]
            )
            self.logger.info(
                f"Ownership of {self.config.USER_HOME} set to {self.config.USERNAME}."
            )
        except subprocess.CalledProcessError:
            self.logger.error(f"Failed to change ownership of {self.config.USER_HOME}.")
            return False
        try:
            await run_command_async(
                [
                    "find",
                    str(self.config.USER_HOME),
                    "-type",
                    "d",
                    "-exec",
                    "chmod",
                    "g+s",
                    "{}",
                    ";",
                ]
            )
            self.logger.info("Setgid bit applied on home directories.")
        except subprocess.CalledProcessError:
            self.logger.warning("Failed to set setgid bit.")
        if await command_exists_async("setfacl"):
            try:
                await run_command_async(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{self.config.USERNAME}:rwx",
                        str(self.config.USER_HOME),
                    ]
                )
                self.logger.info("Default ACLs applied on home directory.")
            except subprocess.CalledProcessError:
                self.logger.warning("Failed to apply default ACLs.")
        else:
            self.logger.warning("setfacl not found; skipping ACL configuration.")
        return True

    async def phase_additional_apps(self) -> bool:
        await self.print_section_async("Additional Applications & Tools")
        self.logger.info("No additional applications to install.")
        return True

    async def phase_cleanup_final(self) -> bool:
        await self.print_section_async("Cleanup & Final Configurations")
        status = True
        try:
            await run_command_async(["nala", "autoremove", "-y"])
            await run_command_async(["nala", "clean"])
            self.logger.info("System cleanup completed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System cleanup failed: {e}")
            status = False
        return status

    async def phase_final_checks(self) -> bool:
        await self.print_section_async("Final System Checks")
        info = await self.final_checks_async()
        elapsed = time.time() - self.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        summary = (
            f"Ubuntu Server Setup & Hardening completed in {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
            f"Kernel Version: {info.get('kernel', 'Unknown')}\n"
            f"Distribution: {info.get('distribution', 'Unknown')}\n"
            f"No automatic reboot is scheduled."
        )
        self.logger.info(summary)
        return True

    async def final_checks_async(self) -> Dict[str, str]:
        info = {}
        try:
            kernel = await run_command_async(
                ["uname", "-r"], capture_output=True, text=True
            )
            self.logger.info(f"Kernel version: {kernel.stdout.strip()}")
            info["kernel"] = kernel.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get kernel version: {e}")
        try:
            pretty_name = "Unknown"
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        pretty_name = line.split("=")[1].strip().strip('"')
                        break
            self.logger.info(f"Distribution: {pretty_name}")
            info["distribution"] = pretty_name
        except Exception as e:
            self.logger.warning(f"Failed to get distribution info: {e}")
            try:
                os_release = await run_command_async(
                    ["cat", "/etc/os-release"], capture_output=True, text=True
                )
                pretty_name = next(
                    (
                        line.split("=")[1].strip().strip('"')
                        for line in os_release.stdout.splitlines()
                        if line.startswith("PRETTY_NAME=")
                    ),
                    "Unknown",
                )
                self.logger.info(f"Distribution from os-release: {pretty_name}")
                info["distribution"] = pretty_name
            except Exception as e2:
                self.logger.warning(f"Failed to get distribution from os-release: {e2}")
                info["distribution"] = "Unknown"
        try:
            uptime = await run_command_async(
                ["uptime", "-p"], capture_output=True, text=True
            )
            self.logger.info(f"System uptime: {uptime.stdout.strip()}")
            info["uptime"] = uptime.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Failed to get uptime: {e}")
        try:
            df_output = await run_command_async(
                ["df", "-h", "/"], capture_output=True, text=True
            )
            df_line = df_output.stdout.splitlines()[1]
            self.logger.info(f"Disk usage (root): {df_line}")
            info["disk_usage"] = df_line
        except Exception as e:
            self.logger.warning(f"Failed to get disk usage: {e}")
        try:
            free_output = await run_command_async(
                ["free", "-h"], capture_output=True, text=True
            )
            mem_line = next(
                (l for l in free_output.stdout.splitlines() if l.startswith("Mem:")), ""
            )
            self.logger.info(f"Memory usage: {mem_line}")
            info["memory"] = mem_line
        except Exception as e:
            self.logger.warning(f"Failed to get memory usage: {e}")
        return info


async def main_async() -> None:
    try:
        setup = UbuntuServerSetup()
        global setup_instance
        setup_instance = setup
        await setup.check_root_async()
        if not await setup.phase_preflight():
            sys.exit(1)
        await setup.phase_system_update()
        await setup.phase_repo_shell_setup()
        await setup.phase_security_hardening()
        await setup.phase_user_customization()
        await setup.phase_permissions()
        await setup.phase_additional_apps()
        await setup.phase_cleanup_final()
        await setup.phase_final_checks()
    except KeyboardInterrupt:
        console.print("\nSetup interrupted by user.")
        try:
            await setup_instance.cleanup_async()
        except Exception as e:
            console.print(f"Cleanup after interruption failed: {e}")
        sys.exit(130)
    except Exception as e:
        console.print(f"Fatal error: {e}")
        try:
            if "setup_instance" in globals():
                await setup_instance.cleanup_async()
        except Exception as cleanup_error:
            console.print(f"Cleanup after error failed: {cleanup_error}")
        sys.exit(1)


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        global setup_instance
        setup_instance = None
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print("Received keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        try:
            loop = asyncio.get_event_loop()
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print(f"Error during shutdown: {e}")


if __name__ == "__main__":
    main()
