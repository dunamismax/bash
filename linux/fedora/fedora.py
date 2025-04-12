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
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

OPERATION_TIMEOUT = 300
APP_NAME = "Fedora Server Setup & Hardening"
VERSION = "1.1.0" # Updated version for sync release

T = TypeVar("T")
setup_instance_global = None # For signal handler

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
            "bash", "zsh", "vim-enhanced", "nano", "micro", "tmux", "screen", "byobu",
            "bash-completion", "ncurses-term", "grc", "ranger", "mc", "multitail", "ccze",
            "colordiff", "progress", "pv", "rlwrap", "reptyr", "expect", "dialog",
            # Modern CLI Tools
            "ripgrep", "fd-find", "bat", "fzf", "tldr", "jq", "sd", "hexyl", "duf", "zoxide", "direnv",
            "neofetch",
            # System Monitoring & Performance
            "tree", "mtr", "iotop", "sysstat", "powertop", "htop", "atop", "glances", "ncdu",
            "dstat", "nmon", "iftop", "nethogs", "bmon", "btop", "stress-ng", "tuned", "chrony",
             "lsof", "psmisc", "lshw", "hwinfo", "dmidecode", "sysfsutils", "inxi", "usbutils", "pciutils",
            # Networking & Security
            "git", "openssh-server", "firewalld", "fail2ban", "fail2ban-firewalld", "curl",
            "wget", "rsync", "sudo", "net-tools", "nmap", "nmap-ncat", "tcpdump", "iptables",
            "nftables", "whois", "openssl", "lynis", "sshfs", "openvpn", "wireguard-tools",
            "ethtool", "ca-certificates", "gnupg2", "certbot", "python3-certbot-nginx",
            "python3-certbot-apache", "acl", "policycoreutils", "policycoreutils-python-utils",
            "setroubleshoot-server", "bind-utils", "NetworkManager-tui", "traceroute", "ipcalc",
            "socat", "bridge-utils", "nload", "oping", "arping", "httpie", "aria2", "dnsmasq",
            "mosh", "tcpflow", "tcpreplay", "tshark", "vnstat", "iptraf-ng", "mitmproxy", "lldpd",
            # Development & Build Tools (complementing group)
            "gcc", "gcc-c++", "make", "cmake", "python3", "python3-pip", "python3-devel",
            "openssl-devel", "ShellCheck", "libffi-devel", "zlib-devel", "readline-devel",
            "bzip2-devel", "ncurses-devel", "pkgconfig", "man-pages", "git-extras", "clang",
            "llvm", "golang", "rust", "cargo", "gdb", "strace", "ltrace", "valgrind",
            "autoconf", "automake", "libtool", "ansible-core",
            # Containers (Podman focus)
            "podman", "buildah", "skopeo",
            # Virtualization
            "qemu-kvm", "libvirt-daemon-kvm", "virt-manager", "virt-viewer", "virt-top",
            "virt-install", "libosinfo", "libguestfs-tools",
            # Filesystem & Archiving
            "unzip", "zip", "pigz", "lz4", "xz", "bzip2", "p7zip", "p7zip-plugins", "zstd",
            "cpio", "pax", "lrzip", "unrar", # unrar may require RPM Fusion repo
            "lzop", "logrotate", "logwatch", "smartmontools", "nvme-cli",
            # Database Clients
            "mariadb", "postgresql", "sqlite", "redis", # Provides redis-cli
            # Backup Tools
            "restic", "duplicity", "borgbackup", "rclone", "rsnapshot", "rdiff-backup",
            "syncthing", "unison", "timeshift",
            # Text Processing & Docs
            "gawk", "dos2unix", "wdiff", "pandoc", "highlight", "groff", "xmlstarlet",
            "html-xml-utils", "libxslt",
            # Web Servers & Proxies (optional basics)
            "nginx", "httpd-tools", "haproxy", "squid", "lighttpd",
            # Other Utils
            "parallel", "moreutils", "kbd", "rpm-devel", "dnf-utils",
            "cloud-init", # Useful for cloud/VM instances
        ]
    )
    SSH_CONFIG: Dict[str, str] = field(
        default_factory=lambda: {
            "PermitRootLogin": "no", "PasswordAuthentication": "yes",
            "X11Forwarding": "no", "MaxAuthTries": "3",
            "ClientAliveInterval": "300", "ClientAliveCountMax": "3",
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
            os.chown(log_file.parent, 0, 0)
            os.chmod(log_file.parent, 0o755)
    except Exception as e:
        print(f"Warning: Log dir setup error {log_file.parent}: {e}", file=sys.stderr)

    logger = logging.getLogger("fedora_setup")
    logger.setLevel(logging.DEBUG)
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        try:
            if not log_file.exists(): log_file.touch(mode=0o600)
            else: os.chmod(str(log_file), 0o600)
            if os.geteuid() == 0: os.chown(str(log_file), 0, 0)
        except Exception as e:
            logger.warning(f"Could not set log file perms {log_file}: {e}")
    except Exception as e:
        logger.error(f"Failed file logging setup {log_file}: {e}")
    return logger

def run_command(
    cmd: List[str], capture_output: bool = False, text: bool = True,
    check: bool = True, timeout: Optional[int] = OPERATION_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None, env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    logger = logging.getLogger("fedora_setup")
    cmd_str = " ".join(cmd)
    logger.debug(f"Running command: {cmd_str}" + (f" in {cwd}" if cwd else ""))
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=text, check=check,
            timeout=timeout, cwd=cwd, env=env, errors='replace'
        )
        if capture_output:
            if result.stdout and result.stdout.strip(): logger.debug(f"Cmd stdout: {result.stdout.strip()}")
            if result.stderr and result.stderr.strip(): logger.debug(f"Cmd stderr: {result.stderr.strip()}")
        logger.debug(f"Command finished successfully: {cmd_str}")
        return result
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds: {cmd_str}")
        raise TimeoutError(f"Command '{cmd_str}' timed out after {timeout} seconds.") from e
    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd[0]}. Ensure it is installed and in PATH.")
        raise e
    except subprocess.CalledProcessError as e:
        error_msg = f"Command '{cmd_str}' failed with code {e.returncode}."
        if e.stdout: error_msg += f"\nStdout: {e.stdout.strip()}"
        if e.stderr: error_msg += f"\nStderr: {e.stderr.strip()}"
        logger.error(error_msg)
        raise e # Re-raise the original error after logging
    except Exception as e:
        logger.error(f"Unexpected error running command '{cmd_str}': {e}")
        logger.exception(e)
        raise e

def command_exists(cmd: str) -> bool:
    logger = logging.getLogger("fedora_setup")
    exists = shutil.which(cmd)
    logger.debug(f"Command '{cmd}' found: {bool(exists)}")
    return bool(exists)

def run_task_with_logging(description: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    logger = logging.getLogger("fedora_setup")
    logger.info(f"Starting: {description}...")
    start = time.monotonic()
    try:
        result = func(*args, **kwargs)
        elapsed = time.monotonic() - start
        logger.info(f"✓ Finished: {description} (took {elapsed:.2f}s)")
        return result
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(f"✗ Failed: {description} (after {elapsed:.2f}s): {e}")
        logger.exception(e) # Log stack trace for failures
        raise # Re-raise exception to signal failure

class FedoraServerSetup:
    def __init__(self, config: Config = Config()):
        self.config = config
        self.logger = setup_logger(self.config.LOG_FILE)
        self.start_time = time.monotonic()
        self.perform_cleanup_on_exit = True # Flag for signal handler
        if os.geteuid() == 0:
            try:
                self.config.USER_HOME.mkdir(parents=True, exist_ok=True)
                user_info = pwd.getpwnam(self.config.USERNAME)
                os.chown(self.config.USER_HOME, user_info.pw_uid, user_info.pw_gid)
                self.logger.debug(f"Ensured user home dir {self.config.USER_HOME}")
            except KeyError: self.logger.error(f"User '{self.config.USERNAME}' not found.")
            except Exception as e: self.logger.warning(f"Could not create/chown {self.config.USER_HOME}: {e}")

    def print_section(self, title: str) -> None:
        self.logger.info("")
        self.logger.info(f"--- {title} ---")

    def backup_file(self, file_path: Union[str, Path]) -> Optional[str]:
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            self.logger.warning(f"Cannot backup non-file: {file_path}"); return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak.{timestamp}")
        try:
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Backed up '{file_path.name}' to '{backup_path.name}'")
            return str(backup_path)
        except Exception as e:
            self.logger.error(f"Failed backup {file_path} to {backup_path}: {e}"); return None

    def cleanup(self) -> None:
        if not self.perform_cleanup_on_exit: return
        self.logger.info("--- Performing Cleanup ---")
        try:
            tmp_dir = Path(tempfile.gettempdir()); prefix = "fedora_setup_"
            cleanup_count = 0
            for item in tmp_dir.glob(f"{prefix}*"):
                try:
                    if item.is_file() or item.is_symlink(): item.unlink()
                    elif item.is_dir(): shutil.rmtree(item)
                    self.logger.debug(f"Removed tmp item: {item}"); cleanup_count += 1
                except Exception as e: self.logger.warning(f"Failed cleanup {item}: {e}")
            self.logger.info(f"Removed {cleanup_count} tmp items.")
            try: self.rotate_logs()
            except Exception as e: self.logger.warning(f"Log rotation failed during cleanup: {e}")
            self.logger.info("Cleanup completed.")
        except Exception as e: self.logger.error(f"General cleanup failed: {e}")
        self.perform_cleanup_on_exit = False # Avoid duplicate cleanup

    def _compress_log(self, log_path: Path, rotated_path: Union[str, Path]) -> None:
        if not log_path.is_file() or log_path.stat().st_size == 0: return
        try:
            with open(log_path, "rb") as f_in, gzip.open(rotated_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            log_path.unlink()
        except FileNotFoundError: pass
        except Exception as e: print(f"Log compress error: {e}", file=sys.stderr); raise

    def rotate_logs(self, log_file: Optional[Union[str, Path]] = None) -> bool:
        if log_file is None: log_file = self.config.LOG_FILE
        log_path = Path(log_file).resolve()
        if not log_path.is_file() or log_path.stat().st_size == 0:
            self.logger.info(f"Log {log_path} empty/missing, no rotation."); return False
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_path = log_path.with_suffix(f".{timestamp}.gz")
        self.logger.info(f"Rotating log {log_path} to {rotated_path}...")
        try:
            for handler in self.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).resolve() == log_path:
                    handler.close(); self.logger.removeHandler(handler)
            self._compress_log(log_path, rotated_path)
            self.logger.info(f"Log rotated to {rotated_path}")
            setup_logger(self.config.LOG_FILE) # Re-create handlers for the original file
            return True
        except Exception as e:
            self.logger.error(f"Log rotation failed for {log_path}: {e}")
            setup_logger(self.config.LOG_FILE) # Still try to re-setup logger
            return False

    def has_internet_connection(self, host: str = "8.8.8.8", port: int = 53, timeout: int = 5) -> bool:
        self.logger.debug(f"Checking internet connection via {host}:{port}...")
        import socket
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            self.logger.debug("Internet connection successful.")
            return True
        except Exception as e:
            self.logger.warning(f"Internet check to {host}:{port} failed: {e}")
            return False

    def check_root(self) -> None:
        if os.geteuid() != 0: self.logger.critical("Must run as root."); sys.exit(1)
        self.logger.info("Root privileges confirmed.")

    def check_network(self) -> None:
        self.logger.info("Verifying network connectivity...")
        if self.has_internet_connection(): self.logger.info("Network verified.")
        else:
            self.logger.warning("Primary network check failed. Trying ping...")
            try: run_command(["ping", "-c", "1", "-W", "3", "8.8.8.8"], capture_output=True, check=True, timeout=5)
            except Exception: self.logger.critical("Network connectivity failed. Aborting."); sys.exit(1)

    def check_fedora(self) -> None:
        os_release = Path("/etc/os-release")
        try:
            if os_release.exists():
                content = os_release.read_text()
                data = {k.strip(): v.strip().strip('"') for k, v in (line.split("=", 1) for line in content.splitlines() if "=" in line)}
                dist_id = data.get("ID")
                if dist_id == "fedora": self.logger.info(f"Detected Fedora: {data.get('PRETTY_NAME', 'N/A')}")
                else: self.logger.warning(f"Not Fedora ({data.get('PRETTY_NAME', 'N/A')}). Proceeding cautiously.")
            else: self.logger.warning("/etc/os-release missing. Assuming Fedora-like.")
        except Exception as e: self.logger.error(f"Distro check failed: {e}. Proceeding cautiously.")

    def save_config_snapshot(self) -> Optional[str]:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("/var/backups/initial_setup")
        snapshot_file = backup_dir / f"fedora_config_snapshot_{timestamp}.tar.gz"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            if os.geteuid() == 0: os.chown(backup_dir, 0, 0); os.chmod(backup_dir, 0o700)
        except Exception as e: self.logger.error(f"Backup dir {backup_dir} setup failed: {e}"); return None
        paths = [ "/etc/dnf/dnf.conf", "/etc/dnf/protected.d", "/etc/yum.repos.d", "/etc/fstab",
                  "/etc/default/grub", "/etc/sysconfig/grub", "/etc/hosts", "/etc/ssh/sshd_config",
                  "/etc/ssh/ssh_config", "/etc/sysconfig/network-scripts/", "/etc/NetworkManager/system-connections/",
                  "/etc/firewalld/firewalld.conf", "/etc/firewalld/zones/", "/etc/selinux/config",
                  "/etc/sysconfig/selinux", ]
        self.logger.info(f"Creating config snapshot: {snapshot_file}...")
        added, missing = [], []
        try:
            with tarfile.open(snapshot_file, "w:gz") as tar:
                for item_str in paths:
                    item_path = Path(item_str)
                    if item_path.exists():
                        try: tar.add(str(item_path), arcname=str(item_path.relative_to(item_path.anchor)), recursive=True); added.append(item_str)
                        except Exception as e_tar: self.logger.warning(f"Could not add {item_path}: {e_tar}")
                    else: missing.append(item_str)
            if missing: self.logger.info(f"Snapshot missing paths: {', '.join(missing)}")
            if added:
                self.logger.info(f"Saved snapshot of {len(added)} items to {snapshot_file}")
                try:
                    if os.geteuid() == 0: os.chmod(snapshot_file, 0o600); os.chown(snapshot_file, 0, 0)
                except Exception as e_perm: self.logger.warning(f"Snapshot perm error {snapshot_file}: {e_perm}")
                return str(snapshot_file)
            else:
                self.logger.warning("No config files added to snapshot.");
                if snapshot_file.exists(): snapshot_file.unlink();
                return None
        except Exception as e:
            self.logger.error(f"Snapshot creation failed {snapshot_file}: {e}")
            if snapshot_file.exists(): try: snapshot_file.unlink(); except OSError: pass
            return None

    def check_updates(self) -> bool:
        self.logger.info("Checking DNF updates...")
        try:
            result = run_command(["dnf", "check-update"], check=False, capture_output=True)
            if result.returncode == 100: self.logger.info("Updates available.")
            elif result.returncode == 0: self.logger.info("System up-to-date.")
            else: self.logger.error(f"DNF check-update failed code {result.returncode}."); return False
            return True
        except Exception as e: self.logger.error(f"DNF check-update error: {e}"); return False

    def upgrade_system(self) -> bool:
        self.logger.info("Upgrading system packages (DNF)...")
        try: run_command(["dnf", "upgrade", "-y", "--refresh"]); return True
        except Exception as e: self.logger.error(f"System upgrade failed: {e}"); return False

    def is_package_installed(self, pkg_name: str) -> bool:
        try: run_command(["rpm", "-q", pkg_name], capture_output=True, check=True, timeout=10); return True
        except subprocess.CalledProcessError: return False
        except Exception as e: self.logger.warning(f"rpm -q check error {pkg_name}: {e}"); return False

    def install_packages(self) -> Tuple[List[str], List[str]]:
        self.logger.info("Processing package installs...")
        groups = [pkg for pkg in self.config.PACKAGES if pkg.startswith("@")]
        packages = [pkg for pkg in self.config.PACKAGES if not pkg.startswith("@")]
        installed, failed = set(), []

        if groups:
            self.logger.info(f"Installing groups: {', '.join(groups)}")
            try: run_command(["dnf", "groupinstall", "-y"] + groups); installed.update(groups)
            except Exception as e: self.logger.error(f"Failed group install: {e}"); failed.extend(groups)

        missing = [pkg for pkg in packages if not self.is_package_installed(pkg)]

        if missing:
            self.logger.info(f"Installing {len(missing)} individual packages...")
            batch_size = 30; batches = [missing[i : i + batch_size] for i in range(0, len(missing), batch_size)]
            for i, batch in enumerate(batches, 1):
                self.logger.info(f"Installing batch {i}/{len(batches)}...")
                try: run_command(["dnf", "install", "-y", "--setopt=install_weak_deps=False"] + batch); installed.update(batch)
                except Exception as e:
                    self.logger.error(f"Failed batch {i}: {e}. Trying individually...");
                    for pkg in batch:
                        if pkg not in installed and pkg not in failed:
                            try: run_command(["dnf", "install", "-y", "--setopt=install_weak_deps=False", pkg]); installed.add(pkg)
                            except Exception as e_s: self.logger.error(f"Failed install {pkg}: {e_s}"); failed.append(pkg)
        else: self.logger.info("All needed individual packages already installed.")

        self.logger.info("Running dnf autoremove...")
        try: run_command(["dnf", "autoremove", "-y"], check=False)
        except Exception as e: self.logger.warning(f"dnf autoremove failed: {e}")

        final_ok = list(installed); final_fail = list(set(failed))
        self.logger.info(f"Packages: {len(final_ok)} ok, {len(final_fail)} failed.")
        if final_fail: self.logger.warning(f"Failed packages: {', '.join(final_fail)}")
        return final_ok, final_fail

    def check_reboot_needed(self) -> None:
        if not command_exists("needs-restarting"):
            self.logger.info("'needs-restarting' missing (dnf-utils). Trying install...")
            try: run_command(["dnf", "install", "-y", "dnf-utils"], check=True, timeout=60)
            except Exception as e: self.logger.warning(f"dnf-utils install failed: {e}"); return
        if not command_exists("needs-restarting"): return
        try:
            result = run_command(["needs-restarting", "-r"], check=False, capture_output=True, timeout=30)
            if result.returncode == 1: self.logger.warning("--- REBOOT RECOMMENDED ---")
            elif result.returncode == 0: self.logger.info("No reboot required.")
            else: self.logger.warning(f"needs-restarting exited code {result.returncode}")
        except Exception as e: self.logger.error(f"Reboot check failed: {e}")

    def setup_repos(self) -> bool:
        try: user_info = pwd.getpwnam(self.config.USERNAME)
        except KeyError: self.logger.error(f"User {self.config.USERNAME} missing."); return False
        gh_dir = self.config.USER_HOME / "github"
        self.logger.info(f"Setting up repos in {gh_dir} for {self.config.USERNAME}")
        try: gh_dir.mkdir(parents=True, exist_ok=True); os.chown(gh_dir, user_info.pw_uid, user_info.pw_gid)
        except Exception as e: self.logger.error(f"Repo dir {gh_dir} setup failed: {e}"); return False
        ok = True
        repos = ["bash", "python"]
        for repo in repos:
            repo_dir = gh_dir / repo; repo_url = f"https://github.com/dunamismax/{repo}.git"
            try:
                if (repo_dir / ".git").is_dir():
                    self.logger.info(f"Pulling updates for {repo}..."); run_command(["git", "-C", str(repo_dir), "pull"])
                else:
                    self.logger.info(f"Cloning {repo}..."); run_command(["git", "clone", repo_url, str(repo_dir)])
                run_command(["chown", "-R", f"{user_info.pw_uid}:{user_info.pw_gid}", str(repo_dir)], check=False)
            except Exception as e:
                self.logger.error(f"Repo '{repo}' management failed: {e}"); ok = False
                if not (repo_dir / ".git").is_dir() and repo_dir.exists(): shutil.rmtree(repo_dir, ignore_errors=True)
        try: run_command(["chown", "-R", f"{user_info.pw_uid}:{user_info.pw_gid}", str(gh_dir)], check=False)
        except Exception as e: self.logger.warning(f"Final chown on {gh_dir} failed: {e}")
        return ok

    def copy_shell_configs(self) -> bool:
        base = self.config.USER_HOME / "github" / "bash" / "linux"
        prefs = [base / "fedora" / "dotfiles", base / "debian" / "dotfiles", base / "ubuntu" / "dotfiles", base / "generic" / "dotfiles"]
        src_dir = next((d for d in prefs if d.is_dir()), None)
        if not src_dir:
             found = list(base.glob("**/dotfiles"))
             if found: src_dir = found[0]; self.logger.warning(f"Using fallback dotfiles: {src_dir}")
             else: self.logger.error("No dotfiles source dir found."); return False
        dests = [self.config.USER_HOME, Path("/root")]
        files = [".bashrc", ".profile"]
        ok = True
        try: user_info = pwd.getpwnam(self.config.USERNAME); root_info = pwd.getpwuid(0)
        except KeyError: self.logger.error(f"User {self.config.USERNAME} not found."); return False

        for file in files:
            src = src_dir / file
            if not src.is_file(): self.logger.warning(f"Source {file} missing."); continue
            for dest_dir in dests:
                if not dest_dir.is_dir(): continue
                dest = dest_dir / file
                is_root = dest_dir == Path("/root")
                uid = root_info.pw_uid if is_root else user_info.pw_uid
                gid = root_info.pw_gid if is_root else user_info.pw_gid
                try:
                    identical = dest.is_file() and filecmp.cmp(str(src), str(dest), shallow=False)
                    if identical: self.logger.info(f"{dest} identical, skipping.")
                    else:
                        self.logger.info(f"Copying {src.name} to {dest}...")
                        if dest.exists(): self.backup_file(dest)
                        shutil.copy2(src, dest)
                        os.chown(dest, uid, gid); os.chmod(dest, 0o644)
                except Exception as e: self.logger.error(f"Failed copy {src.name} to {dest}: {e}"); ok = False
        return ok

    def set_bash_shell(self) -> bool:
        bash = "/bin/bash"; user = self.config.USERNAME
        if not command_exists(bash):
            self.logger.warning(f"{bash} missing. Installing...");
            try: run_command(["dnf", "install", "-y", "bash"]); assert command_exists(bash)
            except Exception as e: self.logger.error(f"Bash install failed: {e}"); return False
        shells = Path("/etc/shells")
        try:
            content = shells.read_text()
            if bash not in content.splitlines():
                self.logger.warning(f"{bash} not in {shells}. Adding..."); self.backup_file(shells)
                with shells.open("a") as f: f.write(f"\n{bash}\n")
        except Exception as e: self.logger.error(f"Shells file {shells} access failed: {e}"); return False
        self.logger.info(f"Setting default shell for {user} to {bash}...")
        try:
            run_command(["usermod", "--shell", bash, user])
            res = run_command(["getent", "passwd", user], capture_output=True, text=True)
            if res.stdout.strip().endswith(f":{bash}"): self.logger.info("Shell change verified.")
            else: self.logger.warning("Shell verification failed.")
            return True
        except Exception as e: self.logger.error(f"usermod failed for {user}: {e}"); return False

    def configure_ssh(self) -> bool:
        svc = "sshd"; cfg = Path("/etc/ssh/sshd_config")
        self.logger.info("Configuring SSH Server...")
        if not self.is_package_installed("openssh-server"):
             self.logger.warning("openssh-server missing. Installing...");
             try: run_command(["dnf", "install", "-y", "openssh-server"]); assert self.is_package_installed("openssh-server")
             except Exception as e: self.logger.error(f"SSH server install failed: {e}"); return False
        try:
            run_command(["systemctl", "enable", svc]); run_command(["systemctl", "start", svc])
            if run_command(["systemctl", "is-active", svc], check=False, capture_output=True, text=True).stdout.strip() != "active":
                 self.logger.warning(f"{svc} inactive. Restarting..."); run_command(["systemctl", "restart", svc]); time.sleep(1)
                 assert run_command(["systemctl", "is-active", svc], check=False, capture_output=True, text=True).stdout.strip() == "active"
        except Exception as e: self.logger.error(f"SSH service enable/start failed: {e}"); return False
        if not cfg.is_file(): self.logger.error(f"{cfg} missing."); return False
        backup = self.backup_file(cfg)
        try:
            orig_content = cfg.read_text(); lines = orig_content.splitlines()
            new_lines = []; modified = set()
            items = self.config.SSH_CONFIG.items()
            for line in lines:
                strip = line.strip()
                if not strip or strip.startswith("#"): new_lines.append(line); continue
                match = False
                for k, v in items:
                    if strip.lower().startswith(k.lower()+" ") or strip.lower().startswith(k.lower()+"\t"):
                        new = f"{k} {v}"
                        if strip != new: self.logger.info(f"SSH: '{strip}' -> '{new}'")
                        new_lines.append(new); modified.add(k); match = True; break
                if not match: new_lines.append(line)
            for k, v in items:
                if k not in modified: new = f"{k} {v}"; self.logger.info(f"SSH Adding: '{new}'"); new_lines.append(new)
            new_content = "\n".join(new_lines) + "\n"
            if new_content.strip() != orig_content.strip():
                 self.logger.info(f"Writing updated SSH config {cfg}"); cfg.write_text(new_content)
                 run_command(["sshd", "-t"]); run_command(["systemctl", "restart", svc])
            else: self.logger.info("No SSH config changes.")
            return True
        except Exception as e:
            self.logger.error(f"SSH config failed: {e}")
            if backup and Path(backup).exists():
                 self.logger.warning(f"Restoring SSH config from {backup}")
                 try: shutil.copy2(backup, cfg); run_command(["systemctl", "restart", svc])
                 except Exception as r_e: self.logger.error(f"SSH restore failed: {r_e}")
            return False

    def log_firewall_status(self, zone: str = "public"):
        try:
            self.logger.info(f"--- Firewall status (zone: {zone}) ---")
            result = run_command(["firewall-cmd", f"--zone={zone}", "--list-all"], capture_output=True, text=True)
            self.logger.info(result.stdout.strip())
        except Exception as e: self.logger.warning(f"Failed get firewall status {zone}: {e}")

    def configure_firewall(self) -> bool:
        svc = "firewalld"; self.logger.info("Configuring Firewall (firewalld)...")
        if not self.is_package_installed(svc):
            self.logger.warning("firewalld missing. Installing...");
            try: run_command(["dnf", "install", "-y", svc]); assert self.is_package_installed(svc)
            except Exception as e: self.logger.error(f"firewalld install failed: {e}"); return False
        try:
            run_command(["systemctl", "enable", svc]); run_command(["systemctl", "start", svc]); time.sleep(1)
            if run_command(["systemctl", "is-active", svc], check=False, capture_output=True, text=True).stdout.strip() != "active":
                 self.logger.warning(f"{svc} inactive. Restarting..."); run_command(["systemctl", "restart", svc]); time.sleep(2)
                 assert run_command(["systemctl", "is-active", svc], check=False, capture_output=True, text=True).stdout.strip() == "active"
        except Exception as e: self.logger.error(f"firewalld service enable/start failed: {e}"); return False
        self.logger.info("Applying firewall rules...")
        try:
            zone = "public"
            cur_svc = set(run_command(["firewall-cmd", f"--zone={zone}", "--list-services"], capture_output=True, text=True).stdout.strip().split())
            cur_port = set(run_command(["firewall-cmd", f"--zone={zone}", "--list-ports"], capture_output=True, text=True).stdout.strip().split())
            changed = False
            for rule in self.config.FIREWALL_RULES:
                typ, name = rule.get("type"), rule.get("name")
                if not typ or not name: continue
                cmd = ["firewall-cmd", "--permanent", f"--zone={zone}"]
                if typ == "service" and name not in cur_svc:
                     self.logger.info(f"Adding service '{name}' to zone {zone}"); run_command(cmd + [f"--add-service={name}"]); changed = True
                elif typ == "port" and name not in cur_port:
                     if "/" not in name or name.split("/")[1] not in ["tcp", "udp"]: self.logger.warning(f"Invalid port: {name}"); continue
                     self.logger.info(f"Adding port '{name}' to zone {zone}"); run_command(cmd + [f"--add-port={name}"]); changed = True
            if changed: self.logger.info("Reloading firewalld..."); run_command(["firewall-cmd", "--reload"])
            else: self.logger.info("No firewall rule changes.")
            self.log_firewall_status(zone); return True
        except Exception as e: self.logger.error(f"Firewall config failed: {e}"); return False

    def configure_fail2ban(self) -> bool:
        self.logger.info("Configuring Fail2ban...")
        pkgs = ["fail2ban", "fail2ban-firewalld"]
        if not all(self.is_package_installed(p) for p in pkgs):
            self.logger.warning("Fail2ban packages missing. Installing...");
            try: run_command(["dnf", "install", "-y"] + pkgs); assert all(self.is_package_installed(p) for p in pkgs)
            except Exception as e: self.logger.error(f"Fail2ban install failed: {e}"); return False
        cfg = Path("/etc/fail2ban/jail.local")
        content = ("[DEFAULT]\n"
                   "bantime=600\nfindtime=600\nmaxretry=5\n"
                   "backend=systemd\nbanaction=firewallcmd-ipset\n"
                   "ignoreip=127.0.0.1/8 ::1\n\n"
                   "[sshd]\nenabled=true\nport=ssh\n"
                   "logpath=%(sshd_log)s\nbackend=%(backend)s\nmaxretry=3\n")
        try:
            if cfg.exists(): self.backup_file(cfg)
            cfg.write_text(content); os.chmod(cfg, 0o600); os.chown(cfg, 0, 0)
            self.logger.info(f"Fail2ban config written {cfg}.")
        except Exception as e: self.logger.error(f"Fail2ban config write failed: {e}"); return False
        self.logger.info("Enabling/restarting Fail2ban service...")
        try:
            svc = "fail2ban"
            run_command(["systemctl", "enable", svc]); run_command(["systemctl", "restart", svc]); time.sleep(2)
            if run_command(["systemctl", "is-active", svc], check=False, capture_output=True, text=True).stdout.strip() == "active":
                self.logger.info("Fail2ban service active.")
                status = run_command(["fail2ban-client", "status"], capture_output=True, text=True)
                self.logger.info(f"Fail2ban status:\n{status.stdout.strip()}")
            else: self.logger.error("Fail2ban service failed start."); return False
            return True
        except Exception as e: self.logger.error(f"Fail2ban service control failed: {e}"); return False

    def configure_selinux(self) -> bool:
        self.logger.info("Checking SELinux Status...")
        pkg = "policycoreutils"
        if not self.is_package_installed(pkg):
             self.logger.warning(f"{pkg} missing. Installing...");
             try: run_command(["dnf", "install", "-y", pkg]); assert self.is_package_installed(pkg)
             except Exception as e: self.logger.error(f"policycoreutils install failed: {e}"); return False
        try:
            sestatus = run_command(["sestatus"], capture_output=True, text=True)
            self.logger.info("SELinux status (sestatus):\n" + "\n".join(f"  {l.strip()}" for l in sestatus.stdout.strip().splitlines()))
            mode = run_command(["getenforce"], capture_output=True, text=True).stdout.strip().lower()
            self.logger.info(f"Current mode (getenforce): {mode.capitalize()}")
            if mode == "enforcing": self.logger.info("SELinux is Enforcing.")
            elif mode == "permissive": self.logger.warning("SELinux is Permissive.")
            elif mode == "disabled": self.logger.error("SELinux is Disabled (Insecure).")
            cfg = Path("/etc/selinux/config")
            if cfg.exists():
                 content = cfg.read_text()
                 cfg_mode = next((l.split("=",1)[1].lower() for l in content.splitlines() if l.strip().startswith("SELINUX=")),"unknown")
                 self.logger.info(f"Configured mode ({cfg}): {cfg_mode.capitalize()}")
                 if cfg_mode != mode and mode != "disabled": self.logger.warning("Config/current modes differ. Reboot?")
            return True
        except Exception as e: self.logger.error(f"SELinux check failed: {e}"); return False

    def deploy_user_scripts(self) -> bool:
        self.logger.info("Deploying user scripts...")
        base = self.config.USER_HOME / "github" / "bash" / "linux"
        prefs = [base / "fedora" / "_scripts", base / "debian" / "_scripts", base / "ubuntu" / "_scripts", base / "generic" / "_scripts"]
        src_dir = next((d for d in prefs if d.is_dir()), None)
        if not src_dir:
             found = list(base.glob("**/_scripts"))
             if found: src_dir = found[0]; self.logger.warning(f"Using fallback scripts: {src_dir}")
             else: self.logger.info("No scripts dir found."); return True
        tgt_bin = self.config.USER_HOME / "bin"
        try:
            tgt_bin.mkdir(parents=True, exist_ok=True)
            user_info = pwd.getpwnam(self.config.USERNAME)
            os.chown(tgt_bin, user_info.pw_uid, user_info.pw_gid)
        except Exception as e: self.logger.error(f"Target bin {tgt_bin} setup failed: {e}"); return False
        if not command_exists("rsync"):
            self.logger.warning("rsync missing. Installing...");
            try: run_command(["dnf", "install", "-y", "rsync"]); assert command_exists("rsync")
            except Exception as e: self.logger.error(f"rsync install failed: {e}"); return False
        try:
            src = str(src_dir).rstrip("/") + "/"; dest = str(tgt_bin).rstrip("/") + "/"
            run_command(["rsync", "-ah", "--delete", "--checksum", "--no-owner", "--no-group", src, dest])
            self.logger.info(f"Scripts synced to {tgt_bin}. Setting perms/owner...")
            run_command(["find", str(tgt_bin), "-type", "f", "-exec", "chmod", "755", "{}", "+"])
            run_command(["chown", "-R", f"{user_info.pw_uid}:{user_info.pw_gid}", str(tgt_bin)])
            self.logger.info("User scripts deployed."); return True
        except Exception as e: self.logger.error(f"Script deploy failed: {e}"); return False

    def home_permissions(self) -> bool:
        self.logger.info("Configuring home directory permissions...")
        home = self.config.USER_HOME; user = self.config.USERNAME
        try: info = pwd.getpwnam(user)
        except KeyError: self.logger.error(f"User {user} missing."); return False
        if not home.is_dir():
             self.logger.warning(f"Home {home} missing. Creating...");
             try: home.mkdir(parents=True); os.chown(home, info.pw_uid, info.pw_gid); os.chmod(home, 0o750)
             except Exception as e: self.logger.error(f"Home create failed {home}: {e}"); return False
        try:
            self.logger.info(f"Setting permissions for {home}...")
            run_command(["chown", "-R", f"{info.pw_uid}:{info.pw_gid}", str(home)])
            run_command(["find", str(home), "-type", "d", "-exec", "chmod", "750", "{}", "+"])
            run_command(["find", str(home), "-type", "f", "-exec", "chmod", "640", "{}", "+"])
            run_command(["chmod", "750", str(home)]) # Ensure top level access
            self.logger.info("Standard permissions applied.")
        except Exception as e: self.logger.error(f"Home perm setting failed {home}: {e}"); return False # Make this critical
        if command_exists("setfacl"):
             self.logger.info("Setting default ACLs on home dir...")
             try:
                 run_command(["setfacl", "-bk", str(home)], check=False) # Clear existing
                 run_command([ "setfacl", "-R", "-m", f"d:u:{user}:rwx", "-m", f"d:g::{info.pw_gid}:r-x",
                     "-m", "d:o::---", "-m", "d:m::rwx", "-m", f"u:{user}:rwx", "-m", f"g::{info.pw_gid}:r-x",
                     "-m", "o::---", str(home)])
                 self.logger.info("Default ACLs applied.")
             except Exception as e: self.logger.warning(f"ACL setting failed: {e}") # Non-critical
        else: self.logger.info("ACL tools missing, skipping ACLs.")
        return True

    def final_cleanup(self) -> bool:
        self.logger.info("Running final DNF cleanup...")
        try:
            run_command(["dnf", "autoremove", "-y"])
            run_command(["dnf", "clean", "all"])
            self.logger.info("DNF cleanup complete."); return True
        except Exception as e: self.logger.error(f"DNF cleanup failed: {e}"); return False

    def get_final_info(self) -> Dict[str, Any]:
        self.logger.info("Gathering final system info...")
        info: Dict[str, Any] = {}
        def get_cmd(cmd: List[str]) -> Optional[str]:
            try: return run_command(cmd, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
            except Exception: return None
        info["hostname"] = get_cmd(["hostname"])
        info["kernel"] = get_cmd(["uname", "-r"])
        info["arch"] = get_cmd(["uname", "-m"])
        info["uptime"] = get_cmd(["uptime", "-p"])
        os_rel = get_cmd(["cat", "/etc/os-release"])
        if os_rel: try: info["distro"] = next((v.strip().strip('"') for k, v in (l.split("=", 1) for l in os_rel.splitlines() if "=" in l) if k.strip() == "PRETTY_NAME"), "N/A")
        except Exception: info["distro"] = "Parse Error"
        else: info["distro"] = "N/A"
        df = get_cmd(["df", "-h", "/"]); info["disk"] = df.splitlines()[-1] if df else "N/A"
        fr = get_cmd(["free", "-h"]); info["mem"] = next((l for l in fr.splitlines() if l.startswith("Mem:")),"N/A") if fr else "N/A"
        fw_act = get_cmd(["systemctl", "is-active", "firewalld"])
        fw_st = get_cmd(["firewall-cmd", "--state"]) if fw_act == "active" else None
        info["fw"] = f"Active ({fw_st})" if fw_st else ("Inactive" if fw_act == "inactive" else f"Unknown ({fw_act})")
        info["selinux"] = get_cmd(["getenforce"]) or "N/A"
        info["ssh"] = (get_cmd(["systemctl", "is-active", "sshd"]) or "N/A").capitalize()
        info["f2b"] = (get_cmd(["systemctl", "is-active", "fail2ban"]) or "N/A").capitalize()
        try: info["reboot"] = run_command(["needs-restarting", "-r"], check=False, timeout=10).returncode == 1
        except Exception: info["reboot"] = None
        return info

    def run_all_phases(self):
        self.logger.info(f"Starting {APP_NAME} v{VERSION}...")
        self.logger.info(f"Log file: {self.config.LOG_FILE}")

        tasks = [
            ("Pre-flight Checks", [self.check_root, self.check_network, self.check_fedora, self.save_config_snapshot]),
            ("System Update & Packages", [self.check_updates, self.upgrade_system, self.install_packages, self.check_reboot_needed]),
            ("Repo & Shell Setup", [self.setup_repos, self.copy_shell_configs, self.set_bash_shell]),
            ("Security Hardening", [self.configure_ssh, self.configure_firewall, self.configure_fail2ban, self.configure_selinux]),
            ("User Customization", [self.deploy_user_scripts]),
            ("Home Permissions", [self.home_permissions]),
            ("Final Cleanup", [self.final_cleanup]),
        ]

        all_passed = True
        for name, funcs in tasks:
            self.print_section(name)
            for func in funcs:
                try:
                    result = run_task_with_logging(func.__name__.replace('_', ' ').capitalize(), func)
                    # Check boolean results for failure indication where applicable
                    if isinstance(result, bool) and not result:
                       self.logger.warning(f"Task '{func.__name__}' indicated failure but did not raise Exception.")
                       all_passed = False # Treat explicit False as failure too
                except Exception as e:
                    self.logger.error(f"Phase '{name}' failed during task '{func.__name__}'.")
                    all_passed = False
                    # Decide whether to break or continue
                    # break # Uncomment this line to stop on first critical failure within a phase
            # if not all_passed: break # Uncomment this line to stop after the first failing phase

        # Final Summary Phase (always run)
        self.print_section("Final Summary")
        try:
             info = self.get_final_info()
             end_time = time.monotonic(); elapsed = end_time - self.start_time
             h, rem = divmod(elapsed, 3600); m, s = divmod(rem, 60)
             summary = [
                 f"{APP_NAME} v{VERSION} finished.", f"Total time: {int(h)}h {int(m)}m {int(s):.0f}s", "--- System Info ---",
                 f" Hostname: {info.get('hostname', 'N/A')}", f" Distro:   {info.get('distro', 'N/A')}",
                 f" Kernel:   {info.get('kernel', 'N/A')}", f" Arch:     {info.get('arch', 'N/A')}",
                 f" Uptime:   {info.get('uptime', 'N/A')}", "--- Resources ---",
                 f" Disk (/): {info.get('disk', 'N/A')}", f" Memory:   {info.get('mem', 'N/A')}", "--- Security ---",
                 f" Firewall: {info.get('fw', 'N/A')}", f" SELinux:  {info.get('selinux', 'N/A')}",
                 f" SSH:      {info.get('ssh', 'N/A')}", f" Fail2ban: {info.get('f2b', 'N/A')}", "--- Notes ---",
                 f" Log file: {self.config.LOG_FILE}",
                 "! REBOOT RECOMMENDED" if info.get('reboot') else ("- Reboot status check failed." if info.get('reboot') is None else "- No reboot required."),
                 "--- Setup Complete ---"
             ]
             self.logger.info("\n" + "=" * 70 + "\n" + "\n".join(summary) + "\n" + "=" * 70 + "\n")
        except Exception as e:
             self.logger.error(f"Failed to generate final summary: {e}")


        if all_passed: self.logger.info(f"{APP_NAME} script completed successfully.")
        else: self.logger.error(f"{APP_NAME} script finished with errors.")
        # Ensure cleanup runs even if phases failed, unless interrupted earlier
        self.cleanup()
        sys.exit(0 if all_passed else 1)


def signal_handler(signum: int, frame: Any) -> None:
    print(f"\nSignal {signum} received. Initiating cleanup...", file=sys.stderr)
    logger = logging.getLogger("fedora_setup")
    logger.error(f"Script interrupted by signal {signum}. Initiating cleanup.")
    if setup_instance_global:
        setup_instance_global.cleanup() # Call the synchronous cleanup
    exit_code = 128 + signum
    if signum == signal.SIGINT: exit_code = 130
    elif signum == signal.SIGTERM: exit_code = 143
    logger.info(f"Exiting with code {exit_code}.")
    sys.exit(exit_code)

def main() -> None:
    global setup_instance_global
    # Basic root check early
    if os.geteuid() != 0:
        print("Error: Must run as root.", file=sys.stderr)
        sys.exit(1)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)

    setup_instance = None # Local variable
    try:
        setup_instance = FedoraServerSetup()
        setup_instance_global = setup_instance # Assign to global for signal handler
        setup_instance.run_all_phases()
    except Exception as e:
        # Catch exceptions happening *outside* run_all_phases or if logger failed
        print(f"Critical error in main execution: {e}", file=sys.stderr)
        if setup_instance: setup_instance.logger.critical(f"Critical error in main: {e}", exc_info=True)
        else: import traceback; traceback.print_exc()
        # Attempt cleanup if instance exists
        if setup_instance: setup_instance.cleanup()
        sys.exit(1)
    # Note: sys.exit is called within run_all_phases or signal_handler

if __name__ == "__main__":
    main()