#!/usr/bin/env python3
import atexit, argparse, datetime, filecmp, gzip, json, logging, os, platform, shutil, socket, subprocess, sys, tarfile, tempfile, time, signal
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from rich.console import Console
from rich.theme import Theme
from rich.table import Table
from rich.panel import Panel
from rich.logging import RichHandler
import pyfiglet

USERNAME = "sawyer"
USER_HOME = f"/home/{USERNAME}"
BACKUP_DIR = "/var/backups"
TEMP_DIR = tempfile.gettempdir()
LOG_FILE = "/var/log/ubuntu_setup.log"
MAX_LOG_SIZE = 10 * 1024 * 1024
PLEX_VERSION = "1.41.4.9463-630c9f557"
PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_arm64.deb"
FASTFETCH_VERSION = "2.37.0"
FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-aarch64.deb"
CONFIG_FILES = [
    "/etc/ssh/sshd_config",
    "/etc/ufw/user.rules",
    "/etc/ntp.conf",
    "/etc/sysctl.conf",
    "/etc/environment",
    "/etc/fail2ban/jail.local",
    "/etc/docker/daemon.json",
    "/etc/caddy/Caddyfile",
]
ALLOWED_PORTS = ["22", "80", "443", "32400"]
PACKAGES = [
    "bash",
    "vim",
    "nano",
    "screen",
    "tmux",
    "mc",
    "zsh",
    "htop",
    "btop",
    "tree",
    "ncdu",
    "neofetch",
    "build-essential",
    "cmake",
    "git",
    "openssh-server",
    "ufw",
    "curl",
    "wget",
    "rsync",
    "sudo",
    "python3",
    "python3-dev",
    "python3-pip",
    "ca-certificates",
    "nala",
    "acl",
]
SETUP_STATUS: Dict[str, Dict[str, str]] = {
    "preflight": {"status": "pending", "message": ""},
    "nala_install": {"status": "pending", "message": ""},
    "system_update": {"status": "pending", "message": ""},
    "packages_install": {"status": "pending", "message": ""},
    "user_env": {"status": "pending", "message": ""},
    "security": {"status": "pending", "message": ""},
    "services": {"status": "pending", "message": ""},
    "maintenance": {"status": "pending", "message": ""},
    "tuning": {"status": "pending", "message": ""},
    "final": {"status": "pending", "message": ""},
}

nord_theme = Theme(
    {
        "header": "#2E3440 bold",
        "primary": "#88C0D0",
        "info": "#A3BE8C",
        "warning": "#EBCB8B",
        "error": "#BF616A",
    }
)
console = Console(theme=nord_theme)
logging.basicConfig(
    level=logging.DEBUG,
    format="[{asctime}] [{levelname}] {message}",
    style="{",
    handlers=[RichHandler(), logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger("ubuntu_setup")
if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        with (
            open(LOG_FILE, "rb") as f_in,
            gzip.open(f"{LOG_FILE}.{ts}.gz", "wb") as f_out,
        ):
            shutil.copyfileobj(f_in, f_out)
        open(LOG_FILE, "w").close()
    except Exception:
        pass


def print_header(msg: str) -> None:
    banner = pyfiglet.figlet_format(msg, font="slant")
    console.print(Panel(banner, style="header"))


def print_section(title: str) -> None:
    console.print(Panel(title, style="primary"))
    logger.info(f"--- {title} ---")


def run_with_progress(
    desc: str, func, *args, task_name: Optional[str] = None, **kwargs
):
    if task_name:
        SETUP_STATUS[task_name] = {
            "status": "in_progress",
            "message": f"{desc} in progress...",
        }
    console.print(f"[primary][*] {desc}...[/primary]")
    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as exe:
            result = exe.submit(func, *args, **kwargs).result()
        elapsed = time.time() - start
        console.print(f"[info][✓] {desc} completed in {elapsed:.2f}s[/info]")
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "success",
                "message": f"{desc} completed successfully.",
            }
        return result
    except Exception as e:
        elapsed = time.time() - start
        console.print(f"[error][✗] {desc} failed in {elapsed:.2f}s: {e}[/error]")
        if task_name:
            SETUP_STATUS[task_name] = {
                "status": "failed",
                "message": f"{desc} failed: {e}",
            }
        raise


def print_status_report() -> None:
    table = Table(title="Setup Status Report", style="primary")
    table.add_column("Task", style="primary")
    table.add_column("Status", style="info")
    table.add_column("Message", style="warning")
    descs = {
        "preflight": "Pre-flight Checks",
        "nala_install": "Nala Installation",
        "system_update": "System Update",
        "packages_install": "Package Installation",
        "user_env": "User Environment Setup",
        "security": "Security Hardening",
        "services": "Service Installations",
        "maintenance": "Maintenance Tasks",
        "tuning": "System Tuning",
        "final": "Final Checks & Cleanup",
    }
    for task, data in SETUP_STATUS.items():
        table.add_row(descs.get(task, task), data["status"].upper(), data["message"])
    console.print(table)


def cleanup() -> None:
    logger.info("Cleanup before exit")
    for f in os.listdir(tempfile.gettempdir()):
        if f.startswith("ubuntu_setup_"):
            try:
                os.remove(os.path.join(tempfile.gettempdir(), f))
            except Exception:
                pass
    if any(item["status"] != "pending" for item in SETUP_STATUS.values()):
        print_status_report()


def signal_handler(signum: int, frame: Optional[Any]) -> None:
    logger.error(f"Interrupted by signal {signum}")
    try:
        cleanup()
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    sys.exit(128 + signum)


for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal_handler)
atexit.register(cleanup)


class Utils:
    @staticmethod
    def run_command(
        cmd: Union[List[str], str],
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        c = " ".join(cmd) if isinstance(cmd, list) else cmd
        logger.debug(f"Executing: {c}")
        try:
            return subprocess.run(
                cmd, check=check, capture_output=capture_output, text=text, **kwargs
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {c} (exit {e.returncode})")
            logger.debug(f"Error: {getattr(e, 'stderr', 'N/A')}")
            raise

    @staticmethod
    def command_exists(cmd: str) -> bool:
        return shutil.which(cmd) is not None

    @staticmethod
    def backup_file(path: str) -> Optional[str]:
        if os.path.isfile(path):
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            bkp = f"{path}.bak.{ts}"
            try:
                shutil.copy2(path, bkp)
                logger.info(f"Backed up {path} to {bkp}")
                return bkp
            except Exception as e:
                logger.warning(f"Backup failed for {path}: {e}")
                return None
        logger.warning(f"{path} not found; skipping backup")
        return None

    @staticmethod
    def ensure_directory(
        path: str, owner: Optional[str] = None, mode: int = 0o755
    ) -> bool:
        try:
            os.makedirs(path, mode=mode, exist_ok=True)
            if owner:
                Utils.run_command(["chown", owner, path])
            logger.debug(f"Ensured {path} exists")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure {path}: {e}")
            return False

    @staticmethod
    def verify_arm_architecture() -> bool:
        try:
            m = platform.machine().lower()
            if any(a in m for a in ["arm", "aarch"]):
                logger.info(f"ARM detected: {m}")
                return True
            logger.warning(f"Non-ARM: {m}")
            return False
        except Exception as e:
            logger.error(f"Arch check failed: {e}")
            return False


class PreflightChecker:
    def check_root(self) -> None:
        if os.geteuid() != 0:
            console.print("[error]Run as root (e.g. sudo ./script.py)[/error]")
            sys.exit(1)
        logger.info("Root confirmed")

    def check_network(self) -> bool:
        logger.info("Checking network")
        for host in ["google.com", "cloudflare.com", "1.1.1.1"]:
            try:
                res = Utils.run_command(
                    ["ping", "-c", "1", "-W", "5", host],
                    check=False,
                    capture_output=True,
                )
                if res.returncode == 0:
                    logger.info(f"Network OK via {host}")
                    return True
            except Exception as e:
                logger.debug(f"Ping {host} failed: {e}")
        logger.error("No network connectivity")
        return False

    def check_os_version(self) -> Optional[Tuple[str, str]]:
        logger.info("Checking OS version")
        if not os.path.isfile("/etc/os-release"):
            logger.warning("Missing /etc/os-release")
            return None
        os_info = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_info[k] = v.strip('"')
        if os_info.get("ID") != "ubuntu":
            logger.warning(f"Non-Ubuntu: {os_info.get('ID', 'unknown')}")
            return None
        ver = os_info.get("VERSION_ID", "").strip('"')
        logger.info(f"OS: {os_info.get('PRETTY_NAME', 'Unknown')}")
        if ver not in ["20.04", "22.04", "24.04"]:
            logger.warning(f"Ubuntu {ver} not officially supported")
        return ("ubuntu", ver)

    def check_architecture(self) -> bool:
        logger.info("Checking architecture")
        return Utils.verify_arm_architecture()

    def save_config_snapshot(self) -> Optional[str]:
        logger.info("Saving config snapshot")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        snap = os.path.join(BACKUP_DIR, f"config_snapshot_{ts}.tar.gz")
        try:
            with tarfile.open(snap, "w:gz") as tar:
                for cfg in CONFIG_FILES:
                    if os.path.isfile(cfg):
                        tar.add(cfg, arcname=os.path.basename(cfg))
                        logger.info(f"Added {cfg}")
                    else:
                        logger.debug(f"Skipped {cfg}")
            logger.info(f"Snapshot saved to {snap}")
            return snap
        except Exception as e:
            logger.warning(f"Snapshot failed: {e}")
            return None


class SystemUpdater:
    def fix_package_issues(self) -> bool:
        logger.info("Fixing package issues")
        try:
            dpkg = Utils.run_command(
                ["dpkg", "--configure", "-a"],
                check=False,
                capture_output=True,
                text=True,
            )
            if dpkg.returncode != 0:
                logger.warning(f"dpkg issues: {dpkg.stderr}")
                Utils.run_command(["dpkg", "--configure", "-a"])
            held = Utils.run_command(
                ["apt-mark", "showhold"], check=False, capture_output=True, text=True
            )
            if held.stdout.strip():
                for pkg in held.stdout.strip().split("\n"):
                    if pkg.strip():
                        try:
                            Utils.run_command(
                                ["apt-mark", "unhold", pkg.strip()], check=False
                            )
                            logger.info(f"Unheld {pkg}")
                        except Exception as e:
                            logger.warning(f"Unhold failed for {pkg}: {e}")
            Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
            Utils.run_command(["apt", "clean"], check=False)
            Utils.run_command(["apt", "autoclean", "-y"], check=False)
            chk = Utils.run_command(
                ["apt-get", "check"], check=False, capture_output=True, text=True
            )
            if chk.returncode != 0:
                logger.warning(f"Package status issue: {chk.stderr}")
                Utils.run_command(["apt", "--fix-missing", "update"], check=False)
                Utils.run_command(["apt", "--fix-broken", "install", "-y"], check=False)
            logger.info("Package issues fixed")
            return True
        except Exception as e:
            logger.error(f"Fix packages failed: {e}")
            return False

    def update_system(self, full_upgrade: bool = False) -> bool:
        logger.info("Updating system with Nala")
        try:
            self.fix_package_issues()
            try:
                Utils.run_command(["nala", "update"])
            except Exception:
                logger.warning("Nala update failed; using apt")
                Utils.run_command(["apt", "update"])
            upg = (
                ["nala", "full-upgrade", "-y"]
                if full_upgrade
                else ["nala", "upgrade", "-y"]
            )
            try:
                Utils.run_command(upg)
            except Exception as e:
                logger.warning(f"Upgrade failed: {e}; retrying...")
                self.fix_package_issues()
                Utils.run_command(upg)
            logger.info("System updated")
            return True
        except Exception as e:
            logger.error(f"System update failed: {e}")
            return False

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        logger.info("Installing packages")
        packages = packages or PACKAGES
        missing = []
        for pkg in packages:
            try:
                subprocess.run(
                    ["dpkg", "-s", pkg],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                missing.append(pkg)
        if not missing:
            logger.info("All packages installed")
            return True
        try:
            Utils.run_command(["nala", "install", "-y"] + missing)
            logger.info("Packages installed")
            return True
        except Exception as e:
            logger.error(f"Bulk install failed: {e}")
            return False

    def configure_timezone(self, timezone: str = "America/New_York") -> bool:
        logger.info(f"Setting timezone to {timezone}")
        tzf = f"/usr/share/zoneinfo/{timezone}"
        if not os.path.isfile(tzf):
            logger.warning(f"Timezone {timezone} not found")
            return False
        try:
            if Utils.command_exists("timedatectl"):
                Utils.run_command(["timedatectl", "set-timezone", timezone])
            else:
                if os.path.exists("/etc/localtime"):
                    os.remove("/etc/localtime")
                os.symlink(tzf, "/etc/localtime")
                with open("/etc/timezone", "w") as f:
                    f.write(f"{timezone}\n")
            logger.info("Timezone set")
            return True
        except Exception as e:
            logger.error(f"Timezone config failed: {e}")
            return False

    def configure_locale(self, locale: str = "en_US.UTF-8") -> bool:
        logger.info(f"Setting locale to {locale}")
        try:
            Utils.run_command(["locale-gen", locale])
            Utils.run_command(["update-locale", f"LANG={locale}", f"LC_ALL={locale}"])
            env_file = "/etc/environment"
            locale_added = False
            lines = []
            if os.path.isfile(env_file):
                with open(env_file) as f:
                    lines = f.readlines()
                new_lines = []
                for line in lines:
                    if line.strip().startswith("LANG="):
                        new_lines.append(f"LANG={locale}\n")
                        locale_added = True
                    else:
                        new_lines.append(line)
                if not locale_added:
                    new_lines.append(f"LANG={locale}\n")
                with open(env_file, "w") as f:
                    f.writelines(new_lines)
            logger.info("Locale set")
            return True
        except Exception as e:
            logger.error(f"Locale config failed: {e}")
            return False


class UserEnvironment:
    def setup_repos(self) -> bool:
        logger.info(f"Setting up GitHub repos for {USERNAME}")
        gh_dir = os.path.join(USER_HOME, "github")
        Utils.ensure_directory(gh_dir, owner=f"{USERNAME}:{USERNAME}")
        repos = ["bash", "windows", "web", "python", "go", "misc"]
        all_ok = True
        for repo in repos:
            repo_dir = os.path.join(gh_dir, repo)
            if os.path.isdir(os.path.join(repo_dir, ".git")):
                try:
                    Utils.run_command(["git", "-C", repo_dir, "pull"], check=False)
                except Exception:
                    logger.warning(f"Update failed for {repo}")
                    all_ok = False
            else:
                try:
                    Utils.run_command(
                        [
                            "git",
                            "clone",
                            f"https://github.com/dunamismax/{repo}.git",
                            repo_dir,
                        ],
                        check=False,
                    )
                except Exception:
                    logger.warning(f"Clone failed for {repo}")
                    all_ok = False
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", gh_dir])
        except Exception:
            logger.warning(f"Chown failed for {gh_dir}")
            all_ok = False
        return all_ok

    def copy_shell_configs(self) -> bool:
        logger.info("Updating shell configs")
        files = [".bashrc", ".profile"]
        src_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        if not os.path.isdir(src_dir):
            logger.warning(f"{src_dir} not found")
            return False
        dest_dirs = [USER_HOME, "/root"]
        all_ok = True
        for f in files:
            src = os.path.join(src_dir, f)
            if not os.path.isfile(src):
                logger.debug(f"{src} not found")
                continue
            for d in dest_dirs:
                dest = os.path.join(d, f)
                copy_needed = True
                if os.path.isfile(dest) and filecmp.cmp(src, dest):
                    logger.info(f"{dest} up-to-date")
                    copy_needed = False
                if copy_needed and os.path.isfile(dest):
                    Utils.backup_file(dest)
                if copy_needed:
                    try:
                        shutil.copy2(src, dest)
                        owner = (
                            f"{USERNAME}:{USERNAME}" if d == USER_HOME else "root:root"
                        )
                        Utils.run_command(["chown", owner, dest])
                        logger.info(f"Copied {src} to {dest}")
                    except Exception as e:
                        logger.warning(f"Copy failed for {src} to {dest}: {e}")
                        all_ok = False
        return all_ok

    def copy_config_folders(self) -> bool:
        logger.info("Copying config folders")
        src_dir = os.path.join(
            USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles"
        )
        dest_dir = os.path.join(USER_HOME, ".config")
        Utils.ensure_directory(dest_dir, owner=f"{USERNAME}:{USERNAME}")
        ok = True
        try:
            for item in os.listdir(src_dir):
                sp = os.path.join(src_dir, item)
                if os.path.isdir(sp):
                    dp = os.path.join(dest_dir, item)
                    os.makedirs(dp, exist_ok=True)
                    Utils.run_command(["rsync", "-a", "--update", sp + "/", dp + "/"])
                    Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", dp])
                    logger.info(f"Copied {item} to {dp}")
            return ok
        except Exception as e:
            logger.error(f"Error in copying from {src_dir}: {e}")
            return False

    def set_bash_shell(self) -> bool:
        logger.info("Setting default shell to /bin/bash")
        if not Utils.command_exists("bash"):
            if not SystemUpdater().install_packages(["bash"]):
                logger.warning("Bash install failed")
                return False
        try:
            with open("/etc/shells") as f:
                shells = f.read()
            if "/bin/bash" not in shells:
                with open("/etc/shells", "a") as f:
                    f.write("/bin/bash\n")
                logger.info("Added /bin/bash to shells")
            cur = (
                subprocess.check_output(["getent", "passwd", USERNAME], text=True)
                .strip()
                .split(":")[-1]
            )
            if cur != "/bin/bash":
                Utils.run_command(["chsh", "-s", "/bin/bash", USERNAME])
                logger.info(f"Set default shell for {USERNAME}")
            else:
                logger.info(f"{USERNAME}'s shell already /bin/bash")
            return True
        except Exception as e:
            logger.error(f"Setting shell failed for {USERNAME}: {e}")
            return False


class SecurityHardener:
    def configure_ssh(self, port: int = 22) -> bool:
        logger.info("Configuring SSH")
        try:
            Utils.run_command(["systemctl", "enable", "--now", "ssh"])
        except Exception as e:
            logger.error(f"SSH enable failed: {e}")
            return False
        sshd = "/etc/ssh/sshd_config"
        if not os.path.isfile(sshd):
            logger.error(f"{sshd} not found")
            return False
        Utils.backup_file(sshd)
        ssh_settings = {
            "Port": str(port),
            "PermitRootLogin": "no",
            "PasswordAuthentication": "no",
            "PermitEmptyPasswords": "no",
            "ChallengeResponseAuthentication": "no",
            "Protocol": "2",
            "MaxAuthTries": "5",
            "ClientAliveInterval": "600",
            "ClientAliveCountMax": "48",
            "X11Forwarding": "no",
            "PermitUserEnvironment": "no",
            "DebianBanner": "no",
            "Banner": "none",
            "LogLevel": "VERBOSE",
            "StrictModes": "yes",
            "AllowAgentForwarding": "yes",
            "AllowTcpForwarding": "yes",
        }
        try:
            with open(sshd) as f:
                lines = f.readlines()
            for key, value in ssh_settings.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("#"):
                        continue
                    if line.strip().startswith(key):
                        lines[i] = f"{key} {value}\n"
                        found = True
                        break
                if not found:
                    lines.append(f"{key} {value}\n")
            with open(sshd, "w") as f:
                f.writelines(lines)
        except Exception as e:
            logger.error(f"SSH config update failed: {e}")
            return False
        try:
            Utils.run_command(["systemctl", "restart", "ssh"])
            logger.info("SSH restarted")
            return True
        except Exception as e:
            logger.error(f"SSH restart failed: {e}")
            return False

    def setup_sudoers(self) -> bool:
        logger.info(f"Configuring sudoers for {USERNAME}")
        try:
            Utils.run_command(["id", USERNAME], capture_output=True)
        except Exception:
            logger.error(f"User {USERNAME} missing")
            return False
        try:
            groups = (
                subprocess.check_output(["id", "-nG", USERNAME], text=True)
                .strip()
                .split()
            )
            if "sudo" not in groups:
                Utils.run_command(["usermod", "-aG", "sudo", USERNAME])
                logger.info(f"Added {USERNAME} to sudo")
            else:
                logger.info(f"{USERNAME} already in sudo")
        except Exception as e:
            logger.error(f"Adding sudo failed for {USERNAME}: {e}")
            return False
        sudoers_file = f"/etc/sudoers.d/99-{USERNAME}"
        try:
            with open(sudoers_file, "w") as f:
                f.write(
                    f"{USERNAME} ALL=(ALL:ALL) ALL\nDefaults timestamp_timeout=15\nDefaults requiretty\n"
                )
            os.chmod(sudoers_file, 0o440)
            logger.info(f"Sudoers config created for {USERNAME}")
            Utils.run_command(["visudo", "-c"], check=True)
            logger.info("Sudoers syntax OK")
            return True
        except Exception as e:
            logger.error(f"Sudoers config failed: {e}")
            return False

    def configure_firewall(self) -> bool:
        logger.info("Configuring UFW")
        ufw_cmd = "/usr/sbin/ufw"
        if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
            logger.info("UFW missing; installing")
            if not SystemUpdater().install_packages(["ufw"]):
                logger.error("UFW install failed")
                return False
        try:
            Utils.run_command([ufw_cmd, "reset", "--force"], check=False)
            logger.info("UFW reset")
        except Exception:
            logger.warning("UFW reset failed")
        for cmd in [
            [ufw_cmd, "default", "deny", "incoming"],
            [ufw_cmd, "default", "allow", "outgoing"],
        ]:
            try:
                Utils.run_command(cmd)
                logger.info(f"Executed: {' '.join(cmd)}")
            except Exception:
                logger.warning(f"Command failed: {' '.join(cmd)}")
        for port in ALLOWED_PORTS:
            try:
                Utils.run_command([ufw_cmd, "allow", f"{port}/tcp"])
                logger.info(f"Allowed port {port}")
            except Exception:
                logger.warning(f"Allow failed for port {port}")
        try:
            status = Utils.run_command(
                [ufw_cmd, "status"], capture_output=True, text=True
            )
            if "inactive" in status.stdout.lower():
                Utils.run_command([ufw_cmd, "--force", "enable"])
                logger.info("UFW enabled")
            else:
                logger.info("UFW active")
        except Exception:
            logger.error("UFW status failed")
            return False
        try:
            Utils.run_command([ufw_cmd, "logging", "on"])
            logger.info("UFW logging on")
        except Exception:
            logger.warning("UFW logging failed")
        try:
            Utils.run_command(["systemctl", "enable", "ufw"])
            Utils.run_command(["systemctl", "restart", "ufw"])
            logger.info("UFW service restarted")
            return True
        except Exception as e:
            logger.error(f"UFW service error: {e}")
            return False

    def configure_fail2ban(self) -> bool:
        logger.info("Configuring Fail2ban")
        if not Utils.command_exists("fail2ban-server"):
            logger.info("Fail2ban missing; installing")
            if not SystemUpdater().install_packages(["fail2ban"]):
                logger.error("Fail2ban install failed")
                return False
        jail_local = "/etc/fail2ban/jail.local"
        config = (
            "[DEFAULT]\nbantime  = 3600\nfindtime = 600\nmaxretry = 3\nbackend  = systemd\nusedns   = warn\n\n"
            "[sshd]\nenabled  = true\nport     = ssh\nfilter   = sshd\nlogpath  = /var/log/auth.log\nmaxretry = 3\n"
        )
        if os.path.isfile(jail_local):
            Utils.backup_file(jail_local)
        try:
            with open(jail_local, "w") as f:
                f.write(config)
            logger.info("Fail2ban config written")
            Utils.run_command(["systemctl", "enable", "fail2ban"])
            Utils.run_command(["systemctl", "restart", "fail2ban"])
            status = Utils.run_command(
                ["systemctl", "is-active", "fail2ban"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Fail2ban active")
                return True
            logger.warning("Fail2ban may not be running")
            return False
        except Exception as e:
            logger.error(f"Fail2ban config failed: {e}")
            return False

    def configure_apparmor(self) -> bool:
        logger.info("Configuring AppArmor")
        try:
            if not SystemUpdater().install_packages(["apparmor", "apparmor-utils"]):
                logger.error("AppArmor install failed")
                return False
            Utils.run_command(["systemctl", "enable", "apparmor"])
            Utils.run_command(["systemctl", "start", "apparmor"])
            status = Utils.run_command(
                ["systemctl", "is-active", "apparmor"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("AppArmor active")
                if Utils.command_exists("aa-update-profiles"):
                    try:
                        Utils.run_command(["aa-update-profiles"], check=False)
                        logger.info("AppArmor profiles updated")
                    except Exception as e:
                        logger.warning(f"Profile update failed: {e}")
                return True
            logger.warning("AppArmor may not be running")
            return False
        except Exception as e:
            logger.error(f"AppArmor config failed: {e}")
            return False


class ServiceInstaller:
    def install_fastfetch(self) -> bool:
        logger.info("Installing Fastfetch")
        if not Utils.verify_arm_architecture():
            logger.warning("Non-ARM; Fastfetch may not work")
        if Utils.command_exists("fastfetch"):
            logger.info("Fastfetch already installed")
            return True
        temp_deb = os.path.join(TEMP_DIR, "fastfetch-linux-aarch64.deb")
        try:
            Utils.run_command(["curl", "-L", "-o", temp_deb, FASTFETCH_URL])
            Utils.run_command(["dpkg", "-i", temp_deb])
            Utils.run_command(["apt", "install", "-f", "-y"])
            if os.path.exists(temp_deb):
                os.remove(temp_deb)
            if Utils.command_exists("fastfetch"):
                logger.info("Fastfetch installed")
                return True
            logger.error("Fastfetch verification failed")
            return False
        except Exception as e:
            logger.error(f"Fastfetch install failed: {e}")
            return False

    def docker_config(self) -> bool:
        logger.info("Configuring Docker")
        if not Utils.command_exists("docker"):
            try:
                script = os.path.join(TEMP_DIR, "get-docker.sh")
                Utils.run_command(
                    ["curl", "-fsSL", "https://get.docker.com", "-o", script]
                )
                os.chmod(script, 0o755)
                Utils.run_command([script], check=True)
                os.remove(script)
                logger.info("Docker installed")
            except Exception as e:
                logger.error(f"Docker install failed: {e}")
                if not SystemUpdater().install_packages(["docker.io"]):
                    logger.error("Alternate Docker install failed")
                    return False
        try:
            groups = (
                subprocess.check_output(["id", "-nG", USERNAME], text=True)
                .strip()
                .split()
            )
            if "docker" not in groups:
                Utils.run_command(["usermod", "-aG", "docker", USERNAME])
                logger.info(f"Added {USERNAME} to docker")
            else:
                logger.info(f"{USERNAME} already in docker")
        except Exception as e:
            logger.warning(f"Adding {USERNAME} to docker failed: {e}")
        daemon_json = "/etc/docker/daemon.json"
        os.makedirs(os.path.dirname(daemon_json), exist_ok=True)
        desired = (
            "{\n"
            '    "log-driver": "json-file",\n'
            '    "log-opts": {"max-size": "10m", "max-file": "3"},\n'
            '    "exec-opts": ["native.cgroupdriver=systemd"],\n'
            '    "storage-driver": "overlay2",\n'
            '    "features": {"buildkit": true},\n'
            '    "default-address-pools": [{"base": "172.17.0.0/16", "size": 24}]\n'
            "}\n"
        )
        update_needed = True
        if os.path.isfile(daemon_json):
            try:
                with open(daemon_json) as f:
                    existing = json.load(f)
                if existing == json.loads(desired):
                    logger.info("Docker daemon config up-to-date")
                    update_needed = False
                else:
                    Utils.backup_file(daemon_json)
            except Exception as e:
                logger.warning(f"Reading {daemon_json} failed: {e}")
        if update_needed:
            try:
                with open(daemon_json, "w") as f:
                    f.write(desired)
                logger.info("Docker daemon config updated")
            except Exception as e:
                logger.warning(f"Writing {daemon_json} failed: {e}")
        try:
            Utils.run_command(["systemctl", "enable", "docker"])
            Utils.run_command(["systemctl", "restart", "docker"])
            logger.info("Docker restarted")
        except Exception as e:
            logger.error(f"Docker service error: {e}")
            return False
        if not Utils.command_exists("docker-compose"):
            try:
                Utils.run_command(["nala", "install", "docker-compose-plugin"])
                logger.info("Docker Compose plugin installed")
            except Exception as e:
                logger.error(f"Docker Compose plugin failed: {e}")
                return False
        else:
            logger.info("Docker Compose already installed")
        try:
            Utils.run_command(["docker", "info"], capture_output=True)
            logger.info("Docker running")
            return True
        except Exception:
            logger.error("Docker inaccessible")
            return False

    def install_configure_caddy(self) -> bool:
        logger.info("Installing Caddy")
        if Utils.command_exists("caddy"):
            logger.info("Caddy already installed")
            caddy_installed = True
        else:
            try:
                Utils.run_command(
                    [
                        "nala",
                        "install",
                        "-y",
                        "debian-keyring",
                        "debian-archive-keyring",
                        "apt-transport-https",
                        "curl",
                    ]
                )
                Utils.run_command(
                    "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg",
                    shell=True,
                )
                Utils.run_command(
                    "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list",
                    shell=True,
                )
                Utils.run_command(["nala", "update"])
                Utils.run_command(["nala", "install", "caddy"])
                logger.info("Caddy installed via repo")
                caddy_installed = True
            except Exception as e:
                logger.error(f"Caddy install failed: {e}")
                return False
        try:
            Utils.ensure_directory("/etc/caddy", "root:root", 0o755)
            Utils.ensure_directory("/var/log/caddy", "caddy:caddy", 0o755)
            src = os.path.join(
                USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles", "Caddyfile"
            )
            dest = "/etc/caddy/Caddyfile"
            if os.path.isfile(src):
                if os.path.isfile(dest):
                    Utils.backup_file(dest)
                shutil.copy2(src, dest)
                logger.info(f"Copied Caddyfile from {src}")
            else:
                if not os.path.isfile(dest):
                    with open(dest, "w") as f:
                        f.write("""# Default Caddy configuration
:80 {
    root * /var/www/html
    file_server
    log {
        output file /var/log/caddy/access.log
        format console
    }
}
""")
                    logger.info("Created default Caddyfile")
            Utils.run_command(["chown", "root:caddy", dest])
            Utils.run_command(["chmod", "644", dest])
            Utils.ensure_directory("/var/www/html", "caddy:caddy", 0o755)
            index = "/var/www/html/index.html"
            if not os.path.isfile(index):
                with open(index, "w") as f:
                    server = socket.gethostname()
                    f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Server: {server}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; }}
        h1 {{ color: #2c3e50; }}
    </style>
</head>
<body>
    <h1>Welcome to {server}</h1>
    <p>Configured on {datetime.datetime.now().strftime("%Y-%m-%d")}.</p>
</body>
</html>""")
                logger.info("Created index.html")
            Utils.run_command(["chown", "caddy:caddy", index])
            Utils.run_command(["chmod", "644", index])
            Utils.run_command(["systemctl", "enable", "caddy"])
            Utils.run_command(["systemctl", "restart", "caddy"])
            status = Utils.run_command(
                ["systemctl", "is-active", "caddy"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Caddy running")
                return True
            logger.warning("Caddy may not be running")
            return False
        except Exception as e:
            logger.error(f"Caddy config failed: {e}")
            return caddy_installed

    def install_nala(self) -> bool:
        logger.info("Installing Nala")
        if Utils.command_exists("nala"):
            logger.info("Nala already installed")
            return True
        try:
            Utils.run_command(["nala", "update"])
            Utils.run_command(["nala", "upgrade", "-y"])
            Utils.run_command(["apt", "--fix-broken", "install", "-y"])
            Utils.run_command(["apt", "install", "nala", "-y"])
            if Utils.command_exists("nala"):
                try:
                    Utils.run_command(["nala", "fetch", "--auto", "-y"], check=False)
                    logger.info("Configured mirrors with Nala")
                except Exception:
                    logger.warning("Mirror config failed")
                return True
            logger.error("Nala verification failed")
            return False
        except Exception as e:
            logger.error(f"Nala install failed: {e}")
            return False

    def install_enable_tailscale(self) -> bool:
        logger.info("Installing Tailscale")
        if Utils.command_exists("tailscale"):
            logger.info("Tailscale already installed")
            tailscale_installed = True
        else:
            try:
                Utils.run_command(
                    ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"]
                )
                tailscale_installed = Utils.command_exists("tailscale")
                if tailscale_installed:
                    logger.info("Tailscale installed")
                else:
                    logger.error("Tailscale install failed")
                    return False
            except Exception as e:
                logger.error(f"Tailscale install error: {e}")
                return False
        try:
            Utils.run_command(["systemctl", "enable", "tailscaled"])
            Utils.run_command(["systemctl", "start", "tailscaled"])
            status = Utils.run_command(
                ["systemctl", "is-active", "tailscaled"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Tailscale running. To authenticate, run: tailscale up")
                return True
            logger.warning("Tailscale may not be running")
            return tailscale_installed
        except Exception as e:
            logger.error(f"Tailscale enable/start failed: {e}")
            return tailscale_installed

    def deploy_user_scripts(self) -> bool:
        logger.info("Deploying user scripts")
        src = os.path.join(USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts")
        tgt = os.path.join(USER_HOME, "bin")
        if not os.path.isdir(src):
            logger.warning(f"{src} does not exist")
            return False
        Utils.ensure_directory(tgt, owner=f"{USERNAME}:{USERNAME}")
        try:
            Utils.run_command(["rsync", "-ah", "--update", f"{src}/", f"{tgt}/"])
            Utils.run_command(
                ["find", tgt, "-type", "f", "-exec", "chmod", "755", "{}", ";"]
            )
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", tgt])
            logger.info("User scripts deployed")
            return True
        except Exception as e:
            logger.error(f"Script deployment failed: {e}")
            return False


class MaintenanceManager:
    def configure_periodic(self) -> bool:
        logger.info("Setting daily maintenance cron job")
        cron_file = "/etc/cron.daily/ubuntu_maintenance"
        marker = "# Ubuntu maintenance script"
        if os.path.isfile(cron_file):
            with open(cron_file) as f:
                if marker in f.read():
                    logger.info("Cron job already configured")
                    return True
            Utils.backup_file(cron_file)
        content = f"""#!/bin/sh
{marker}
LOG="/var/log/daily_maintenance.log"
echo "--- Daily Maintenance $(date) ---" >> $LOG
nala update -qq >> $LOG 2>&1
nala upgrade -y >> $LOG 2>&1
nala autoremove -y >> $LOG 2>&1
nala clean >> $LOG 2>&1
df -h / >> $LOG 2>&1
echo "Daily maintenance completed at $(date)" >> $LOG
"""
        try:
            with open(cron_file, "w") as f:
                f.write(content)
            os.chmod(cron_file, 0o755)
            logger.info(f"Cron job created at {cron_file}")
            return True
        except Exception as e:
            logger.error(f"Cron job creation failed: {e}")
            return False

    def backup_configs(self) -> bool:
        logger.info("Backing up configs")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        bdir = os.path.join(BACKUP_DIR, f"ubuntu_config_{ts}")
        os.makedirs(bdir, exist_ok=True)
        success = True
        for f in CONFIG_FILES:
            if os.path.isfile(f):
                try:
                    shutil.copy2(f, os.path.join(bdir, os.path.basename(f)))
                    logger.info(f"Backed up {f}")
                except Exception as e:
                    logger.warning(f"Backup failed for {f}: {e}")
                    success = False
            else:
                logger.debug(f"{f} not found; skipping")
        try:
            with open(os.path.join(bdir, "MANIFEST.txt"), "w") as f:
                f.write("Ubuntu Configuration Backup\n")
                f.write(f"Created: {datetime.datetime.now()}\n")
                f.write(f"Hostname: {socket.gethostname()}\n\nFiles included:\n")
                for f in CONFIG_FILES:
                    if os.path.isfile(os.path.join(bdir, os.path.basename(f))):
                        f.write(f"- {f}\n")
            logger.info(f"Backups saved to {bdir}")
        except Exception as e:
            logger.warning(f"Manifest creation failed: {e}")
        return success

    def update_ssl_certificates(self) -> bool:
        logger.info("Updating SSL certificates via certbot")
        if not Utils.command_exists("certbot"):
            logger.info("certbot not installed; installing")
            if not SystemUpdater().install_packages(["certbot"]):
                logger.warning("certbot install failed")
                return False
        try:
            output = Utils.run_command(
                ["certbot", "renew", "--dry-run"], capture_output=True, text=True
            ).stdout
            logger.info("certbot dry-run complete")
            if "No renewals were attempted" in output:
                logger.info("No certificates need renewal")
            else:
                Utils.run_command(["certbot", "renew"])
                logger.info("Certificates updated")
            return True
        except Exception as e:
            logger.warning(f"SSL update failed: {e}")
            return False

    def configure_unattended_upgrades(self) -> bool:
        logger.info("Configuring unattended upgrades")
        try:
            if not SystemUpdater().install_packages(
                ["unattended-upgrades", "apt-listchanges"]
            ):
                logger.error("Unattended-upgrades install failed")
                return False
            auto_file = "/etc/apt/apt.conf.d/20auto-upgrades"
            auto_content = (
                'APT::Periodic::Update-Package-Lists "1";\n'
                'APT::Periodic::Unattended-Upgrade "1";\n'
                'APT::Periodic::AutocleanInterval "7";\n'
                'APT::Periodic::Download-Upgradeable-Packages "1";\n'
            )
            with open(auto_file, "w") as f:
                f.write(auto_content)
            logger.info(f"Auto-upgrades config written to {auto_file}")
            unattended_file = "/etc/apt/apt.conf.d/50unattended-upgrades"
            if os.path.isfile(unattended_file):
                Utils.backup_file(unattended_file)
            unattended_content = (
                "Unattended-Upgrade::Allowed-Origins {\n"
                '    "${distro_id}:${distro_codename}";\n'
                '    "${distro_id}:${distro_codename}-security";\n'
                "};\n\n"
                'Unattended-Upgrade::Automatic-Reboot "false";\n'
                'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";\n'
            )
            with open(unattended_file, "w") as f:
                f.write(unattended_content)
            logger.info(f"Unattended-upgrades config written to {unattended_file}")
            Utils.run_command(["systemctl", "enable", "unattended-upgrades"])
            Utils.run_command(["systemctl", "restart", "unattended-upgrades"])
            status = Utils.run_command(
                ["systemctl", "is-active", "unattended-upgrades"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status.stdout.strip() == "active":
                logger.info("Unattended upgrades active")
                return True
            logger.warning("Unattended upgrades may not be running")
            return False
        except Exception as e:
            logger.error(f"Unattended upgrades config failed: {e}")
            return False


class SystemTuner:
    def tune_system(self) -> bool:
        logger.info("Applying system tuning")
        sysctl_conf = "/etc/sysctl.conf"
        if os.path.isfile(sysctl_conf):
            Utils.backup_file(sysctl_conf)
        tuning = {
            "net.core.somaxconn": "1024",
            "net.core.netdev_max_backlog": "5000",
            "net.ipv4.tcp_max_syn_backlog": "8192",
            "net.ipv4.tcp_slow_start_after_idle": "0",
            "net.ipv4.tcp_tw_reuse": "1",
            "net.ipv4.ip_local_port_range": "1024 65535",
            "net.ipv4.tcp_rmem": "4096 87380 16777216",
            "net.ipv4.tcp_wmem": "4096 65536 16777216",
            "fs.file-max": "2097152",
            "vm.swappiness": "10",
            "vm.dirty_ratio": "60",
            "vm.dirty_background_ratio": "2",
            "kernel.sysrq": "0",
            "net.ipv4.conf.default.rp_filter": "1",
            "net.ipv4.conf.all.rp_filter": "1",
        }
        try:
            with open(sysctl_conf) as f:
                content = f.read()
            marker = "# Performance tuning settings for Ubuntu"
            if marker in content:
                content = content.split(marker)[0]
            content += f"\n{marker}\n"
            for k, v in tuning.items():
                content += f"{k} = {v}\n"
            with open(sysctl_conf, "w") as f:
                f.write(content)
            Utils.run_command(["sysctl", "-p"])
            logger.info("Tuning applied")
            return True
        except Exception as e:
            logger.error(f"Tuning failed: {e}")
            return False

    def home_permissions(self) -> bool:
        logger.info("Configuring home permissions")
        if not Utils.command_exists("setfacl"):
            logger.info("setfacl not found; installing acl")
            if not SystemUpdater().install_packages(["acl"]):
                logger.warning("ACL install failed; skipping ACLs")
        try:
            Utils.run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", USER_HOME])
            Utils.run_command(["chmod", "750", USER_HOME])
            for d in [
                os.path.join(USER_HOME, ".ssh"),
                os.path.join(USER_HOME, ".gnupg"),
                os.path.join(USER_HOME, ".config"),
            ]:
                if os.path.isdir(d):
                    Utils.run_command(["chmod", "700", d])
                    logger.info(f"Set permissions on {d}")
            Utils.run_command(
                ["find", USER_HOME, "-type", "d", "-exec", "chmod", "g+s", "{}", ";"]
            )
            if Utils.command_exists("setfacl"):
                Utils.run_command(
                    [
                        "setfacl",
                        "-R",
                        "-d",
                        "-m",
                        f"u:{USERNAME}:rwX,g:{USERNAME}:r-X,o::---",
                        USER_HOME,
                    ]
                )
                logger.info(f"Default ACLs applied on {USER_HOME}")
            else:
                logger.warning("setfacl missing; skipping ACLs")
            logger.info(f"Home permissions for {USERNAME} set")
            return True
        except Exception as e:
            logger.error(f"Home permissions failed: {e}")
            return False


class FinalChecker:
    def system_health_check(self) -> Dict[str, Any]:
        logger.info("Performing health check")
        health: Dict[str, Any] = {}
        try:
            uptime = subprocess.check_output(["uptime"], text=True).strip()
            logger.info(f"Uptime: {uptime}")
            health["uptime"] = uptime
        except Exception as e:
            logger.warning(f"Uptime failed: {e}")
        try:
            df_out = subprocess.check_output(["df", "-h", "/"], text=True).splitlines()
            if len(df_out) >= 2:
                data = df_out[1].split()
                logger.info(f"Disk: {data[4]} used ({data[2]} of {data[1]})")
                health["disk"] = {
                    "total": data[1],
                    "used": data[2],
                    "available": data[3],
                    "percent_used": data[4],
                }
            else:
                logger.warning("Unexpected df output")
        except Exception as e:
            logger.warning(f"Disk usage failed: {e}")
        try:
            for line in subprocess.check_output(["free", "-h"], text=True).splitlines():
                logger.info(line)
                if line.startswith("Mem:"):
                    parts = line.split()
                    health["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "free": parts[3],
                    }
        except Exception as e:
            logger.warning(f"Memory usage failed: {e}")
        try:
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]
            logger.info(f"Load: {', '.join(load)}")
            health["load"] = {
                "1min": float(load[0]),
                "5min": float(load[1]),
                "15min": float(load[2]),
            }
        except Exception as e:
            logger.warning(f"Load averages failed: {e}")
        try:
            dmesg = subprocess.check_output(
                ["dmesg", "--level=err,crit,alert,emerg"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if dmesg:
                logger.warning("Recent kernel errors:")
                for line in dmesg.splitlines()[-5:]:
                    logger.warning(line)
                health["kernel_errors"] = True
            else:
                logger.info("No kernel errors")
                health["kernel_errors"] = False
        except Exception as e:
            logger.warning(f"Kernel errors check failed: {e}")
        try:
            updates = subprocess.check_output(
                ["apt", "list", "--upgradable"], text=True, stderr=subprocess.DEVNULL
            ).splitlines()
            total = len(updates) - 1 if updates else 0
            if total > 0:
                logger.info(f"Updates available: {total}")
                health["updates"] = {"total": total}
            else:
                logger.info("System up to date")
                health["updates"] = {"total": 0}
        except Exception as e:
            logger.warning(f"Updates check failed: {e}")
        return health

    def verify_firewall_rules(self) -> bool:
        logger.info("Verifying firewall rules")
        all_ok = True
        try:
            ufw_status = subprocess.check_output(["ufw", "status"], text=True).strip()
            logger.info("UFW status:")
            for line in ufw_status.splitlines()[:10]:
                logger.info(line)
            if "inactive" in ufw_status.lower():
                logger.warning("UFW inactive!")
                return False
        except Exception as e:
            logger.warning(f"UFW status failed: {e}")
            all_ok = False
        for port in ALLOWED_PORTS:
            try:
                res = subprocess.run(
                    ["nc", "-z", "-w3", "127.0.0.1", port],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if res.returncode != 0:
                    logger.warning(f"Port {port} closed")
                    all_ok = False
                else:
                    logger.info(f"Port {port} open")
            except Exception as e:
                logger.warning(f"Port {port} check failed: {e}")
                all_ok = False
        return all_ok

    def cleanup_system(self) -> bool:
        logger.info("Performing system cleanup")
        try:
            if Utils.command_exists("nala"):
                Utils.run_command(["nala", "autoremove", "-y"])
                Utils.run_command(["nala", "clean"])
            else:
                Utils.run_command(["apt", "autoremove", "-y"])
                Utils.run_command(["apt", "clean"])
            logger.info("Cleanup completed")
            return True
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return False

    def prompt_reboot(self) -> None:
        logger.info("Prompting reboot")
        console.print("[info]Setup completed! Reboot is recommended.[/info]")
        if input("Reboot now? [y/N]: ").strip().lower() == "y":
            logger.info("Rebooting")
            try:
                Utils.run_command(["shutdown", "-r", "now"])
            except Exception as e:
                logger.warning(f"Reboot failed: {e}")
        else:
            logger.info("Reboot canceled")

    def final_checks(self) -> bool:
        logger.info("Performing final checks")
        all_pass = True
        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
            logger.info(f"Kernel: {kernel}")
            df_line = subprocess.check_output(
                ["df", "-h", "/"], text=True
            ).splitlines()[1]
            logger.info(f"Disk usage: {df_line}")
            disk_percent = int(df_line.split()[4].strip("%"))
            if disk_percent > 90:
                logger.warning("Disk usage over 90%!")
                all_pass = False
            free_line = next(
                (
                    line
                    for line in subprocess.check_output(
                        ["free", "-h"], text=True
                    ).splitlines()
                    if line.startswith("Mem:")
                ),
                "",
            )
            logger.info(f"Memory: {free_line}")
            interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
            logger.info("Network interfaces:")
            for line in interfaces.splitlines():
                logger.info(line)
            load_avg = open("/proc/loadavg").read().split()[:3]
            logger.info(f"Load averages: {', '.join(load_avg)}")
            return all_pass
        except Exception as e:
            logger.error(f"Final checks error: {e}")
            return False


class UbuntuServerSetup:
    def __init__(self):
        self.logger = logger
        self.success = True
        self.start_time = time.time()
        self.preflight = PreflightChecker()
        self.updater = SystemUpdater()
        self.user_env = UserEnvironment()
        self.security = SecurityHardener()
        self.services = ServiceInstaller()
        self.maintenance = MaintenanceManager()
        self.tuner = SystemTuner()
        self.final_checker = FinalChecker()

    def run_full_setup(self) -> int:
        print_header("Ubuntu Server Setup v6.0.0 (ARM)")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"[primary]Start Time: {now}[/primary]")
        logger.info(f"Started at {now}")
        print_section("Phase 1: Pre-flight Checks")
        run_with_progress(
            "Running Pre-flight Checks",
            self.preflight.check_root,
            task_name="preflight",
        )
        if not self.preflight.check_network():
            logger.error("Network check failed. Aborting.")
            SETUP_STATUS["preflight"] = {
                "status": "failed",
                "message": "Network check failed",
            }
            sys.exit(1)
        self.preflight.check_os_version()
        self.preflight.check_architecture()
        run_with_progress(
            "Saving configuration snapshot", self.preflight.save_config_snapshot
        )
        SETUP_STATUS["preflight"] = {
            "status": "success",
            "message": "Pre-flight checks completed",
        }
        print_section("Phase 2: System Update & Basic Configuration")
        if not run_with_progress(
            "Updating system", self.updater.update_system, task_name="system_update"
        ):
            logger.warning("System update failed; proceeding with caution.")
            self.success = False
        if not run_with_progress(
            "Installing packages",
            self.updater.install_packages,
            task_name="packages_install",
        ):
            logger.warning("Package installation issues encountered.")
            self.success = False
        if not run_with_progress(
            "Configuring timezone", self.updater.configure_timezone
        ):
            logger.warning("Timezone config failed.")
            self.success = False
        if not run_with_progress("Configuring locale", self.updater.configure_locale):
            logger.warning("Locale config failed.")
            self.success = False
        print_section("Phase 3: User Environment Setup")
        env_ok = True
        if not run_with_progress(
            "Setting up user repositories",
            self.user_env.setup_repos,
            task_name="user_env",
        ):
            logger.warning("Repo setup failed.")
            env_ok = False
        if not run_with_progress(
            "Copying shell configs", self.user_env.copy_shell_configs
        ):
            logger.warning("Shell config update failed.")
            env_ok = False
        if not run_with_progress(
            "Copying config folders", self.user_env.copy_config_folders
        ):
            logger.warning("Config folders copy failed.")
            env_ok = False
        if not run_with_progress("Setting default shell", self.user_env.set_bash_shell):
            logger.warning("Default shell update failed.")
            env_ok = False
        SETUP_STATUS["user_env"] = {
            "status": "success" if env_ok else "partial",
            "message": "User environment setup completed",
        }
        print_section("Phase 4: Security & Access Hardening")
        sec_ok = True
        if not run_with_progress(
            "Configuring SSH", self.security.configure_ssh, task_name="security"
        ):
            logger.warning("SSH config failed.")
            sec_ok = False
        if not run_with_progress("Configuring sudoers", self.security.setup_sudoers):
            logger.warning("Sudoers config failed.")
            sec_ok = False
        if not run_with_progress(
            "Configuring firewall", self.security.configure_firewall
        ):
            logger.warning("Firewall config failed.")
            sec_ok = False
        if not run_with_progress(
            "Configuring Fail2ban", self.security.configure_fail2ban
        ):
            logger.warning("Fail2ban config failed.")
            sec_ok = False
        if not run_with_progress(
            "Configuring AppArmor", self.security.configure_apparmor
        ):
            logger.warning("AppArmor config failed.")
            sec_ok = False
        SETUP_STATUS["security"] = {
            "status": "success" if sec_ok else "partial",
            "message": "Security hardening completed",
        }
        print_section("Phase 5: Service Installations")
        serv_ok = True
        if not run_with_progress(
            "Installing Fastfetch",
            self.services.install_fastfetch,
            task_name="services",
        ):
            logger.warning("Fastfetch install failed.")
            serv_ok = False
        if not run_with_progress("Configuring Docker", self.services.docker_config):
            logger.warning("Docker config failed.")
            serv_ok = False
        if not run_with_progress(
            "Installing Tailscale", self.services.install_enable_tailscale
        ):
            logger.warning("Tailscale install failed.")
            serv_ok = False
        if not run_with_progress(
            "Installing Caddy", self.services.install_configure_caddy
        ):
            logger.warning("Caddy install failed.")
            serv_ok = False
        if not run_with_progress(
            "Deploying user scripts", self.services.deploy_user_scripts
        ):
            logger.warning("User scripts deployment failed.")
            serv_ok = False
        SETUP_STATUS["services"] = {
            "status": "success" if serv_ok else "partial",
            "message": "Service installations completed",
        }
        print_section("Phase 6: Maintenance Tasks")
        maint_ok = True
        if not run_with_progress(
            "Configuring periodic maintenance",
            self.maintenance.configure_periodic,
            task_name="maintenance",
        ):
            logger.warning("Periodic maintenance config failed.")
            maint_ok = False
        if not run_with_progress(
            "Configuring unattended upgrades",
            self.maintenance.configure_unattended_upgrades,
        ):
            logger.warning("Unattended upgrades config failed.")
            maint_ok = False
        if not run_with_progress(
            "Backing up configurations", self.maintenance.backup_configs
        ):
            logger.warning("Configuration backup failed.")
            maint_ok = False
        if not run_with_progress(
            "Updating SSL certificates", self.maintenance.update_ssl_certificates
        ):
            logger.warning("SSL certificate update failed.")
            maint_ok = False
        SETUP_STATUS["maintenance"] = {
            "status": "success" if maint_ok else "partial",
            "message": "Maintenance tasks completed",
        }
        print_section("Phase 7: System Tuning & Permissions")
        tune_ok = True
        if not run_with_progress(
            "Applying system tuning", self.tuner.tune_system, task_name="tuning"
        ):
            logger.warning("System tuning failed.")
            tune_ok = False
        if not run_with_progress(
            "Setting home permissions", self.tuner.home_permissions
        ):
            logger.warning("Home permissions config failed.")
            tune_ok = False
        SETUP_STATUS["tuning"] = {
            "status": "success" if tune_ok else "partial",
            "message": "System tuning completed",
        }
        print_section("Phase 8: Final Checks & Cleanup")
        SETUP_STATUS["final"] = {
            "status": "in_progress",
            "message": "Running final checks...",
        }
        self.final_checker.system_health_check()
        if not self.final_checker.verify_firewall_rules():
            logger.warning("Firewall verification failed.")
        final_result = self.final_checker.final_checks()
        self.final_checker.cleanup_system()
        duration = time.time() - self.start_time
        m, s = divmod(duration, 60)
        if self.success and final_result:
            logger.info(f"Setup completed successfully in {int(m)}m {int(s)}s.")
            SETUP_STATUS["final"] = {
                "status": "success",
                "message": f"Completed in {int(m)}m {int(s)}s.",
            }
        else:
            logger.warning(f"Setup completed with warnings in {int(m)}m {int(s)}s.")
            SETUP_STATUS["final"] = {
                "status": "partial",
                "message": f"Completed with warnings in {int(m)}m {int(s)}s.",
            }
        print_status_report()
        self.final_checker.prompt_reboot()
        return 0 if self.success and final_result else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ubuntu Server Initialization & Hardening Utility for Raspberry Pi (ARM)"
    )
    p.add_argument(
        "--phase",
        type=str,
        choices=["full"],
        default="full",
        help="Select phase to run (default: full)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_instance = UbuntuServerSetup()
    if args.phase == "full":
        return setup_instance.run_full_setup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
