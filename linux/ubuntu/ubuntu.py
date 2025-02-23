#!/usr/bin/env python3
"""
Ubuntu System Initialization & Hardening Script

This production-ready automation script bootstraps, configures, and hardens an Ubuntu server.
It performs a comprehensive set of system configuration tasks including:
  - System update and essential package installation
  - Timezone configuration
  - GitHub repository setup and shell configuration updates
  - SSH hardening and sudo configuration
  - Firewall (ufw) setup and verification
  - Installation and configuration of services (Plex, Fastfetch, Docker)
  - Deployment of user scripts and dotfiles
  - Periodic maintenance tasks and performance tuning
  - ZFS pool configuration and final system health checks

Usage:
  Run this script as root to fully initialize and secure your Ubuntu system:
      sudo ./ubuntu_setup.py

Disclaimer:
  THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY. USE AT YOUR OWN RISK.

Author: dunamismax
Version: 4.2.0
Date: 2025-02-22
"""

import os
import sys
import subprocess
import shutil
import datetime
import logging
import filecmp
import atexit
import platform

# ----------------------------
# Global Variables & Constants
# ----------------------------

# Software versions and download URLs
PLEX_VERSION = "1.41.3.9314-a0bfb8370"
PLEX_URL = f"https://downloads.plex.tv/plex-media-server-new/{PLEX_VERSION}/debian/plexmediaserver_{PLEX_VERSION}_amd64.deb"

FASTFETCH_VERSION = "2.36.1"
FASTFETCH_URL = f"https://github.com/fastfetch-cli/fastfetch/releases/download/{FASTFETCH_VERSION}/fastfetch-linux-amd64.deb"

DOCKER_COMPOSE_VERSION = "2.20.2"
uname = platform.uname()
DOCKER_COMPOSE_URL = f"https://github.com/docker/compose/releases/download/v{DOCKER_COMPOSE_VERSION}/docker-compose-{uname.system}-{uname.machine}"

# Logging and user configuration
LOG_FILE = "/var/log/ubuntu_setup.log"
USERNAME = "sawyer"
USER_HOME = f"/home/{USERNAME}"

# List of essential packages to install
PACKAGES = [
    "bash", "vim", "nano", "screen", "tmux", "mc", "zsh", "htop", "tree", "ncdu", "neofetch",
    "build-essential", "cmake", "ninja-build", "meson", "gettext", "git",
    "openssh-server", "ufw", "curl", "wget", "rsync", "sudo", "bash-completion",
    "python3", "python3-dev", "python3-pip", "python3-venv",
    "libssl-dev", "libffi-dev", "zlib1g-dev", "libreadline-dev", "libbz2-dev", "tk-dev", "xz-utils",
    "libncurses5-dev", "libgdbm-dev", "libnss3-dev", "liblzma-dev", "libxml2-dev", "libxmlsec1-dev",
    "ca-certificates", "software-properties-common", "apt-transport-https", "gnupg", "lsb-release",
    "clang", "llvm", "netcat-openbsd", "lsof", "unzip", "zip",
    "xorg", "x11-xserver-utils", "xterm", "alacritty", "fonts-dejavu-core",
    "net-tools", "nmap", "iftop", "iperf3", "tcpdump", "lynis",
    "golang-go", "gdb",
    "john", "hydra", "aircrack-ng", "nikto",
    "postgresql-client", "mysql-client", "redis-server",
    "ruby", "rustc", "jq", "certbot",
]

# Terminal color definitions (Nord theme)
NORD9  = '\033[38;2;129;161;193m'    # Debug messages
NORD10 = '\033[38;2;94;129;172m'     # Secondary info
NORD11 = '\033[38;2;191;97;106m'     # Error messages
NORD13 = '\033[38;2;235;203;139m'    # Warning messages
NORD14 = '\033[38;2;163;190;140m'    # Info messages
NC     = '\033[0m'                  # Reset color

# ----------------------------
# Logging Setup
# ----------------------------

def setup_logging():
    """Configure logging to both file and console with color support."""
    if not os.path.exists(os.path.dirname(LOG_FILE)):
        os.makedirs(os.path.dirname(LOG_FILE), mode=0o700, exist_ok=True)
    
    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S")

    # File handler for logging
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler with color support if output is tty
    class ColorFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': NORD9,
            'INFO': NORD14,
            'WARNING': NORD13,
            'ERROR': NORD11,
            'CRITICAL': NORD11,
        }
        def format(self, record):
            color = self.COLORS.get(record.levelname, '')
            message = super().format(record)
            return f"{color}{message}{NC}"

    if sys.stderr.isatty():
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(ColorFormatter('[%(asctime)s] [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(ch)
    return logger

logger = setup_logging()

def log_info(message: str) -> None:
    logger.info(message)

def log_warn(message: str) -> None:
    logger.warning(message)

def log_error(message: str) -> None:
    logger.error(message)

def log_debug(message: str) -> None:
    logger.debug(message)

# ----------------------------
# Utility Functions
# ----------------------------

def run_command(cmd, check=True, capture_output=False, text=True, **kwargs):
    """
    Execute a shell command.
    
    :param cmd: Command to execute as a list or string.
    :param check: If True, raise CalledProcessError on non-zero exit.
    :param capture_output: Capture stdout and stderr if True.
    :param text: Return output as text.
    :return: CompletedProcess instance.
    """
    log_debug(f"Executing command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text, **kwargs)

def command_exists(cmd: str) -> bool:
    """Check if a command exists in the system's PATH."""
    return shutil.which(cmd) is not None

def backup_file(file_path: str) -> None:
    """
    Create a backup of a file with a timestamp suffix.
    
    :param file_path: Path of the file to backup.
    """
    if os.path.isfile(file_path):
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup = f"{file_path}.bak.{timestamp}"
        try:
            shutil.copy2(file_path, backup)
            log_info(f"Backed up {file_path} to {backup}")
        except Exception as e:
            log_warn(f"Failed to backup {file_path}: {e}")
    else:
        log_warn(f"File {file_path} not found; skipping backup.")

def print_section(title: str) -> None:
    """
    Log a section header to improve readability of log output.
    
    :param title: Section title.
    """
    border = "─" * 60
    log_info(f"{NORD10}{border}{NC}")
    log_info(f"{NORD10}  {title}{NC}")
    log_info(f"{NORD10}{border}{NC}")

def handle_error(msg: str, code: int = 1) -> None:
    """
    Log an error message and exit the script.
    
    :param msg: Error message to log.
    :param code: Exit code.
    """
    log_error(f"{msg} (Exit Code: {code})")
    sys.exit(code)

def cleanup() -> None:
    """Perform any necessary cleanup tasks before the script exits."""
    log_info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here.

atexit.register(cleanup)

# ----------------------------
# Pre-requisites and System Checks
# ----------------------------

def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        handle_error("Script must be run as root. Exiting.")

def check_network() -> None:
    """Verify network connectivity by pinging a reliable host."""
    print_section("Network Connectivity Check")
    log_info("Verifying network connectivity...")
    try:
        run_command(["ping", "-c", "1", "-W", "5", "google.com"], check=True, capture_output=True)
        log_info("Network connectivity verified.")
    except subprocess.CalledProcessError:
        handle_error("No network connectivity. Please verify your network settings.")

# ----------------------------
# System Update & Package Installation
# ----------------------------

def update_system() -> None:
    """Update package repositories and upgrade installed packages."""
    print_section("System Update & Upgrade")
    log_info("Updating package repositories...")
    try:
        run_command(["apt", "update", "-qq"])
    except subprocess.CalledProcessError:
        handle_error("Failed to update package repositories.")
    
    log_info("Upgrading system packages...")
    try:
        run_command(["apt", "upgrade", "-y"])
    except subprocess.CalledProcessError:
        handle_error("Failed to upgrade packages.")
    
    log_info("System update and upgrade complete.")

def install_packages() -> None:
    """Install all missing essential packages (and their recommended packages) in a single batch."""
    print_section("Essential Package Installation")
    log_info("Checking for required packages...")
    
    missing_packages = []
    for pkg in PACKAGES:
        try:
            subprocess.run(
                ["dpkg", "-s", pkg],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log_info(f"Package already installed: {pkg}")
        except subprocess.CalledProcessError:
            missing_packages.append(pkg)
    
    if missing_packages:
        log_info(f"Installing missing packages: {' '.join(missing_packages)}")
        try:
            # Removed the --install-suggests flag to only install recommended packages.
            run_command(["apt", "install", "-y"] + missing_packages)
            log_info("All missing packages installed successfully.")
        except subprocess.CalledProcessError:
            handle_error("Failed to install one or more packages.")
    else:
        log_info("All required packages are already installed.")

# ----------------------------
# Timezone and NTP Configuration
# ----------------------------

def configure_timezone() -> None:
    """
    Configure the system timezone.
    
    This function sets the timezone to a specified value by creating a symbolic link to the appropriate timezone file.
    """
    print_section("Timezone Configuration")
    tz = "America/New_York"  # Modify as needed
    log_info(f"Setting timezone to {tz}...")
    tz_file = f"/usr/share/zoneinfo/{tz}"
    if os.path.isfile(tz_file):
        try:
            if os.path.islink("/etc/localtime") or os.path.exists("/etc/localtime"):
                os.remove("/etc/localtime")
            os.symlink(tz_file, "/etc/localtime")
            log_info(f"Timezone set to {tz}.")
        except Exception as e:
            log_warn(f"Failed to set timezone: {e}")
    else:
        log_warn(f"Timezone file for {tz} not found.")

# ----------------------------
# Repository and Shell Setup
# ----------------------------

def setup_repos() -> None:
    """
    Set up GitHub repositories in the user's home directory.
    
    Clones or updates a predefined list of repositories.
    """
    print_section("GitHub Repositories Setup")
    log_info(f"Setting up GitHub repositories for user '{USERNAME}'...")
    gh_dir = os.path.join(USER_HOME, "github")
    os.makedirs(gh_dir, exist_ok=True)
    repos = ["bash", "windows", "web", "python", "go", "misc"]
    for repo in repos:
        repo_dir = os.path.join(gh_dir, repo)
        if os.path.isdir(os.path.join(repo_dir, ".git")):
            log_info(f"Repository '{repo}' already exists. Pulling latest changes...")
            try:
                run_command(["git", "-C", repo_dir, "pull"])
            except subprocess.CalledProcessError:
                log_warn(f"Failed to update repository '{repo}'.")
        else:
            log_info(f"Cloning repository '{repo}' into '{repo_dir}'...")
            try:
                run_command(["git", "clone", f"https://github.com/dunamismax/{repo}.git", repo_dir])
                log_info(f"Repository '{repo}' cloned successfully.")
            except subprocess.CalledProcessError:
                log_warn(f"Failed to clone repository '{repo}'.")
    try:
        run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", gh_dir])
        log_info(f"Ownership of '{gh_dir}' set to '{USERNAME}'.")
    except subprocess.CalledProcessError:
        log_warn(f"Failed to set ownership of '{gh_dir}'.")

def copy_shell_configs() -> None:
    """
    Update the user's shell configuration files (.bashrc and .profile) from a repository source.
    
    Performs a backup if needed and applies new configurations.
    """
    print_section("Shell Configuration Update")
    source_dir = os.path.join(USER_HOME, "github", "bash", "linux", "ubuntu", "dotfiles")
    dest_dir = USER_HOME
    for file in [".bashrc", ".profile"]:
        src = os.path.join(source_dir, file)
        dest = os.path.join(dest_dir, file)
        if os.path.isfile(src):
            copy = True
            if os.path.isfile(dest) and filecmp.cmp(src, dest):
                log_info(f"File {dest} is already up-to-date.")
                copy = False
            if copy:
                try:
                    shutil.copy2(src, dest)
                    run_command(["chown", f"{USERNAME}:{USERNAME}", dest])
                    log_info(f"Copied {src} to {dest}.")
                except Exception as e:
                    log_warn(f"Failed to copy {src}: {e}")
        else:
            log_warn(f"Source file {src} not found; skipping.")
    if os.path.isfile(os.path.join(dest_dir, ".bashrc")):
        log_info(f"Sourcing {os.path.join(dest_dir, '.bashrc')} is not applicable in Python.")
    else:
        log_warn(f"No .bashrc found in {dest_dir}; skipping source.")

def set_bash_shell() -> None:
    """
    Ensure that /bin/bash is set as the default shell for the specified user.
    
    Installs bash if not present and updates /etc/shells.
    """
    print_section("Default Shell Configuration")
    if not command_exists("bash"):
        log_info("Bash not found; installing...")
        try:
            run_command(["apt", "install", "-y", "bash"])
        except subprocess.CalledProcessError:
            log_warn("Bash installation failed.")
            return
    try:
        with open("/etc/shells", "r") as f:
            shells = f.read()
        if "/bin/bash" not in shells:
            with open("/etc/shells", "a") as f:
                f.write("/bin/bash\n")
            log_info("Added /bin/bash to /etc/shells.")
        else:
            log_info("/bin/bash is already present in /etc/shells.")
    except Exception as e:
        log_warn(f"Failed to update /etc/shells: {e}")
    try:
        run_command(["chsh", "-s", "/bin/bash", USERNAME])
        log_info(f"Default shell for {USERNAME} set to /bin/bash.")
    except subprocess.CalledProcessError:
        log_warn(f"Failed to set default shell for {USERNAME}.")

# ----------------------------
# SSH and Sudo Security Configuration
# ----------------------------

def configure_ssh() -> None:
    """
    Configure and secure the OpenSSH server.
    
    Installs OpenSSH server if not present, backs up and updates the sshd_config file, and restarts SSH.
    """
    print_section("SSH Configuration")
    log_info("Configuring OpenSSH Server...")
    try:
        subprocess.run(["dpkg", "-s", "openssh-server"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        log_info("openssh-server not installed. Installing...")
        try:
            run_command(["apt", "install", "-y", "openssh-server"])
            log_info("OpenSSH Server installed.")
        except subprocess.CalledProcessError:
            handle_error("Failed to install OpenSSH Server.")
    try:
        run_command(["systemctl", "enable", "--now", "ssh"])
    except subprocess.CalledProcessError:
        handle_error("Failed to enable/start SSH service.")
    sshd_config = "/etc/ssh/sshd_config"
    if not os.path.isfile(sshd_config):
        handle_error(f"SSHD configuration file not found: {sshd_config}")
    backup_file(sshd_config)
    ssh_settings = {
        "Port": "22",
        "PermitRootLogin": "no",
        "PasswordAuthentication": "yes",
        "PermitEmptyPasswords": "no",
        "ChallengeResponseAuthentication": "no",
        "Protocol": "2",
        "MaxAuthTries": "5",
        "ClientAliveInterval": "600",
        "ClientAliveCountMax": "48",
    }
    try:
        with open(sshd_config, "r") as f:
            lines = f.readlines()
        for key, value in ssh_settings.items():
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith(key):
                    lines[i] = f"{key} {value}\n"
                    found = True
                    break
            if not found:
                lines.append(f"{key} {value}\n")
        with open(sshd_config, "w") as f:
            f.writelines(lines)
    except Exception as e:
        log_warn(f"Failed to update SSH configuration: {e}")
    try:
        run_command(["systemctl", "restart", "ssh"])
        log_info("SSH configuration updated.")
    except subprocess.CalledProcessError:
        handle_error("Failed to restart SSH service.")

def setup_sudoers() -> None:
    """
    Ensure the specified user has sudo privileges.
    
    Checks the user's groups and adds them to the sudo group if necessary.
    """
    print_section("Sudo Configuration")
    log_info(f"Ensuring user {USERNAME} has sudo privileges...")
    try:
        result = subprocess.run(["id", "-nG", USERNAME], capture_output=True, text=True, check=True)
        if "sudo" in result.stdout.split():
            log_info(f"User {USERNAME} is already in the sudo group.")
        else:
            run_command(["usermod", "-aG", "sudo", USERNAME])
            log_info(f"User {USERNAME} added to sudo group.")
    except subprocess.CalledProcessError:
        log_warn(f"Failed to add {USERNAME} to sudo group.")

# ----------------------------
# Firewall (UFW) Configuration
# ----------------------------

def configure_firewall() -> None:
    """
    Configure the UFW firewall.
    
    Sets default policies, allows specific ports, and enables the firewall.
    """
    print_section("Firewall Configuration")
    log_info("Configuring firewall with ufw...")
    ufw_cmd = "/usr/sbin/ufw"
    if not os.path.isfile(ufw_cmd) or not os.access(ufw_cmd, os.X_OK):
        handle_error("ufw command not found. Please install ufw.")
    try:
        run_command([ufw_cmd, "default", "deny", "incoming"])
    except subprocess.CalledProcessError:
        log_warn("Failed to set default deny incoming.")
    try:
        run_command([ufw_cmd, "default", "allow", "outgoing"])
    except subprocess.CalledProcessError:
        log_warn("Failed to set default allow outgoing.")
    for port in ["22", "80", "443", "32400"]:
        try:
            run_command([ufw_cmd, "allow", f"{port}/tcp"])
        except subprocess.CalledProcessError:
            log_warn(f"Failed to allow port {port}.")
    try:
        result = run_command([ufw_cmd, "status"], capture_output=True)
        if "inactive" in result.stdout:
            run_command([ufw_cmd, "--force", "enable"])
        else:
            log_info("ufw firewall is already enabled.")
    except subprocess.CalledProcessError:
        handle_error("Failed to check/enable ufw firewall.")
    try:
        run_command(["systemctl", "enable", "ufw"])
    except subprocess.CalledProcessError:
        log_warn("Failed to enable ufw service.")
    try:
        run_command(["systemctl", "start", "ufw"])
    except subprocess.CalledProcessError:
        log_warn("Failed to start ufw service.")
    log_info("Firewall configured and enabled.")

# ----------------------------
# Service Installation and Configuration
# ----------------------------

def install_plex() -> None:
    """
    Install and configure Plex Media Server.
    
    Downloads the Plex .deb package, installs it, configures the service to run as the specified user,
    and enables the service.
    """
    print_section("Plex Media Server Installation")
    log_info("Installing Plex Media Server...")
    if not command_exists("curl"):
        handle_error("curl is required but not installed.")
    temp_deb = "/tmp/plexmediaserver.deb"
    try:
        subprocess.run(["dpkg", "-s", "plexmediaserver"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_info("Plex Media Server is already installed; skipping download and installation.")
        return
    except subprocess.CalledProcessError:
        pass
    try:
        run_command(["curl", "-L", "-o", temp_deb, PLEX_URL])
    except subprocess.CalledProcessError:
        handle_error("Failed to download Plex Media Server .deb file.")
    try:
        run_command(["dpkg", "-i", temp_deb])
    except subprocess.CalledProcessError:
        log_warn("dpkg encountered issues. Attempting to fix missing dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError:
            handle_error("Failed to install dependencies for Plex.")
    plex_conf = "/etc/default/plexmediaserver"
    if os.path.isfile(plex_conf):
        try:
            with open(plex_conf, "r") as f:
                conf = f.read()
            if f"PLEX_MEDIA_SERVER_USER={USERNAME}" in conf:
                log_info(f"Plex user is already configured as {USERNAME}.")
            else:
                new_conf = []
                for line in conf.splitlines():
                    if line.startswith("PLEX_MEDIA_SERVER_USER="):
                        new_conf.append(f"PLEX_MEDIA_SERVER_USER={USERNAME}")
                    else:
                        new_conf.append(line)
                with open(plex_conf, "w") as f:
                    f.write("\n".join(new_conf) + "\n")
                log_info(f"Configured Plex to run as {USERNAME}.")
        except Exception as e:
            log_warn(f"Failed to set Plex user in {plex_conf}: {e}")
    else:
        log_warn(f"{plex_conf} not found; skipping user configuration.")
    try:
        run_command(["systemctl", "enable", "plexmediaserver"])
    except subprocess.CalledProcessError:
        log_warn("Failed to enable Plex service.")
    try:
        os.remove(temp_deb)
    except Exception:
        pass
    log_info("Plex Media Server installed successfully.")

def install_fastfetch() -> None:
    """
    Install Fastfetch, a system information tool.
    
    Downloads the Fastfetch .deb package, installs it, and fixes dependencies if necessary.
    """
    print_section("Fastfetch Installation")
    temp_deb = "/tmp/fastfetch-linux-amd64.deb"
    try:
        subprocess.run(["dpkg", "-s", "fastfetch"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_info("Fastfetch is already installed; skipping.")
        return
    except subprocess.CalledProcessError:
        pass
    try:
        run_command(["curl", "-L", "-o", temp_deb, FASTFETCH_URL])
    except subprocess.CalledProcessError:
        handle_error("Failed to download fastfetch deb file.")
    try:
        run_command(["dpkg", "-i", temp_deb])
    except subprocess.CalledProcessError:
        log_warn("fastfetch installation issues; fixing dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError:
            handle_error("Failed to fix dependencies for fastfetch.")
    try:
        os.remove(temp_deb)
    except Exception:
        pass
    log_info("Fastfetch installed successfully.")

def docker_config() -> None:
    """
    Install and configure Docker and Docker Compose.
    
    Installs Docker if not present, adds the user to the docker group, updates Docker daemon configuration,
    and installs Docker Compose.
    """
    print_section("Docker Configuration")
    log_info("Installing Docker...")
    if command_exists("docker"):
        log_info("Docker is already installed.")
    else:
        try:
            run_command(["apt", "install", "-y", "docker.io"])
            log_info("Docker installed successfully.")
        except subprocess.CalledProcessError:
            handle_error("Failed to install Docker.")
    try:
        result = subprocess.run(["id", "-nG", USERNAME], capture_output=True, text=True, check=True)
        if "docker" not in result.stdout.split():
            run_command(["usermod", "-aG", "docker", USERNAME])
            log_info(f"Added user '{USERNAME}' to docker group.")
        else:
            log_info(f"User '{USERNAME}' is already in docker group.")
    except subprocess.CalledProcessError:
        log_warn(f"Failed to add {USERNAME} to docker group.")
    try:
        os.makedirs("/etc/docker", exist_ok=True)
    except Exception as e:
        handle_error(f"Failed to create /etc/docker: {e}")
    desired_daemon_json = """{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "exec-opts": ["native.cgroupdriver=systemd"]
}
"""
    daemon_json_path = "/etc/docker/daemon.json"
    write_config = True
    if os.path.isfile(daemon_json_path):
        try:
            with open(daemon_json_path, "r") as f:
                existing = f.read()
            if existing.strip() == desired_daemon_json.strip():
                log_info("Docker daemon configuration is already up-to-date.")
                write_config = False
            else:
                backup_file(daemon_json_path)
        except Exception as e:
            log_warn(f"Failed to read {daemon_json_path}: {e}")
    if write_config:
        try:
            with open(daemon_json_path, "w") as f:
                f.write(desired_daemon_json)
            log_info("Docker daemon configuration updated/created.")
        except Exception as e:
            log_warn(f"Failed to write {daemon_json_path}: {e}")
    try:
        run_command(["systemctl", "enable", "docker"])
    except subprocess.CalledProcessError:
        log_warn("Could not enable Docker service.")
    try:
        run_command(["systemctl", "restart", "docker"])
    except subprocess.CalledProcessError:
        handle_error("Failed to restart Docker.")
    log_info("Docker is running.")
    if not command_exists("docker-compose"):
        try:
            run_command(["curl", "-L", DOCKER_COMPOSE_URL, "-o", "/usr/local/bin/docker-compose"])
            os.chmod("/usr/local/bin/docker-compose", 0o755)
            log_info("Docker Compose installed successfully.")
        except subprocess.CalledProcessError:
            handle_error("Failed to download Docker Compose.")
    else:
        log_info("Docker Compose is already installed.")

def deploy_user_scripts() -> None:
    """
    Deploy user scripts from the repository to the user's bin directory.
    
    Uses rsync to synchronize scripts and sets executable permissions.
    """
    print_section("Deploying User Scripts")
    script_source = os.path.join(USER_HOME, "github", "bash", "linux", "ubuntu", "_scripts")
    script_target = os.path.join(USER_HOME, "bin")
    if not os.path.isdir(script_source):
        handle_error(f"Source directory '{script_source}' does not exist.")
    os.makedirs(script_target, exist_ok=True)
    try:
        run_command(["rsync", "-ah", "--delete", f"{script_source}/", f"{script_target}/"])
        run_command(["find", script_target, "-type", "f", "-exec", "chmod", "755", "{}", ";"])
        log_info("User scripts deployed successfully.")
    except subprocess.CalledProcessError:
        handle_error("Script deployment failed.")

def configure_periodic() -> None:
    """
    Set up a daily cron job for system maintenance.
    
    Creates a cron script that updates and cleans the system.
    """
    print_section("Periodic Maintenance Setup")
    cron_file = "/etc/cron.daily/ubuntu_maintenance"
    marker = "# Ubuntu maintenance script"
    if os.path.isfile(cron_file):
        with open(cron_file, "r") as f:
            if marker in f.read():
                log_info("Daily maintenance cron job already configured.")
                return
        backup_file(cron_file)
    content = """#!/bin/sh
# Ubuntu maintenance script
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
"""
    try:
        with open(cron_file, "w") as f:
            f.write(content)
        os.chmod(cron_file, 0o755)
        log_info(f"Daily maintenance script created at {cron_file}.")
    except Exception as e:
        log_warn(f"Failed to set execute permission on {cron_file}: {e}")

def backup_configs() -> None:
    """
    Backup critical system configuration files.
    
    Copies configuration files to a timestamped backup directory.
    """
    print_section("Configuration Backups")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = f"/var/backups/ubuntu_config_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    for file in ["/etc/ssh/sshd_config", "/etc/ufw/user.rules", "/etc/ntp.conf"]:
        if os.path.isfile(file):
            try:
                shutil.copy2(file, backup_dir)
                log_info(f"Backed up {file}")
            except Exception as e:
                log_warn(f"Failed to backup {file}: {e}")
        else:
            log_warn(f"File {file} not found; skipping.")

def rotate_logs() -> None:
    """
    Rotate the log file by compressing it and truncating the original.
    """
    print_section("Log Rotation")
    if os.path.isfile(LOG_FILE):
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        rotated_file = f"{LOG_FILE}.{timestamp}.gz"
        try:
            with open(LOG_FILE, "rb") as f_in, open(rotated_file, "wb") as f_out:
                import gzip
                with gzip.GzipFile(fileobj=f_out, mode="wb") as gz:
                    shutil.copyfileobj(f_in, gz)
            open(LOG_FILE, "w").close()
            log_info(f"Log rotated to {rotated_file}.")
        except Exception as e:
            log_warn(f"Log rotation failed: {e}")
    else:
        log_warn(f"Log file {LOG_FILE} does not exist.")

def system_health_check() -> None:
    """
    Perform basic system health checks and log the results.
    
    Checks uptime, disk usage, memory usage, and logs CPU and network interface details.
    """
    print_section("System Health Check")
    try:
        uptime = subprocess.check_output(["uptime"], text=True).strip()
        log_info(f"Uptime: {uptime}")
    except Exception as e:
        log_warn(f"Failed to get uptime: {e}")
    try:
        df_output = subprocess.check_output(["df", "-h", "/"], text=True).strip()
        for line in df_output.splitlines():
            log_info(line)
    except Exception as e:
        log_warn(f"Failed to get disk usage: {e}")
    try:
        free_output = subprocess.check_output(["free", "-h"], text=True).strip()
        for line in free_output.splitlines():
            log_info(line)
    except Exception as e:
        log_warn(f"Failed to get memory usage: {e}")

def verify_firewall_rules() -> None:
    """
    Verify that specific ports are accessible as expected.
    
    Uses netcat to check connectivity on predefined ports.
    """
    print_section("Firewall Rules Verification")
    for port in ["22", "80", "443", "32400"]:
        try:
            subprocess.run(["nc", "-z", "-w3", "127.0.0.1", port], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_info(f"Port {port} is accessible.")
        except subprocess.CalledProcessError:
            log_warn(f"Port {port} is not accessible. Check ufw rules.")

def update_ssl_certificates() -> None:
    """
    Update SSL certificates using certbot.
    
    Installs certbot if necessary and renews certificates.
    """
    print_section("SSL Certificates Update")
    if not command_exists("certbot"):
        try:
            run_command(["apt", "install", "-y", "certbot"])
            log_info("certbot installed successfully.")
        except subprocess.CalledProcessError:
            log_warn("Failed to install certbot.")
            return
    try:
        run_command(["certbot", "renew"])
        log_info("SSL certificates updated successfully.")
    except subprocess.CalledProcessError:
        log_warn("Failed to update SSL certificates.")

def tune_system() -> None:
    """
    Apply performance tuning settings to the system.
    
    Updates /etc/sysctl.conf with network performance parameters and applies them immediately.
    """
    print_section("Performance Tuning")
    sysctl_conf = "/etc/sysctl.conf"
    if os.path.isfile(sysctl_conf):
        backup_file(sysctl_conf)
    marker = "# Performance tuning settings for Ubuntu"
    try:
        with open(sysctl_conf, "r") as f:
            content = f.read()
    except Exception:
        content = ""
    if marker not in content:
        tuning = f"""
{marker}
net.core.somaxconn=128
net.ipv4.tcp_rmem=4096 87380 6291456
net.ipv4.tcp_wmem=4096 16384 4194304
"""
        try:
            with open(sysctl_conf, "a") as f:
                f.write(tuning)
            run_command(["sysctl", "-w", "net.core.somaxconn=128"])
            run_command(["sysctl", "-w", 'net.ipv4.tcp_rmem=4096 87380 6291456'])
            run_command(["sysctl", "-w", 'net.ipv4.tcp_wmem=4096 16384 4194304'])
            log_info("Performance tuning applied.")
        except Exception as e:
            log_warn(f"Failed to apply performance tuning: {e}")
    else:
        log_info(f"Performance tuning settings already exist in {sysctl_conf}.")

def final_checks() -> None:
    """
    Perform final system checks and log system information.
    
    Verifies kernel version, uptime, disk usage, memory usage, CPU details, network interfaces, and load averages.
    """
    print_section("Final System Checks")
    try:
        kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
        log_info(f"Kernel version: {kernel}")
    except Exception as e:
        log_warn(f"Failed to get kernel version: {e}")
    try:
        uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
        log_info(f"System uptime: {uptime}")
    except Exception as e:
        log_warn(f"Failed to get system uptime: {e}")
    try:
        disk_line = subprocess.check_output(["df", "-h", "/"], text=True).splitlines()[1]
        log_info(f"Disk usage (root partition): {disk_line}")
    except Exception as e:
        log_warn(f"Failed to get disk usage: {e}")
    try:
        free_out = subprocess.check_output(["free", "-h"], text=True).splitlines()
        mem_line = next((line for line in free_out if line.startswith("Mem:")), "")
        log_info(f"Memory usage: {mem_line}")
    except Exception as e:
        log_warn(f"Failed to get memory usage: {e}")
    try:
        cpu_model = subprocess.check_output(["lscpu"], text=True)
        for line in cpu_model.splitlines():
            if "Model name" in line:
                log_info(f"CPU: {line.split(':', 1)[1].strip()}")
                break
    except Exception as e:
        log_warn(f"Failed to get CPU info: {e}")
    try:
        interfaces = subprocess.check_output(["ip", "-brief", "address"], text=True)
        log_info("Active network interfaces:")
        for line in interfaces.splitlines():
            log_info(f"  {line}")
    except Exception as e:
        log_warn(f"Failed to get network interfaces: {e}")
    try:
        with open("/proc/loadavg", "r") as f:
            load_avg = f.read().split()[:3]
            log_info(f"Load averages (1, 5, 15 min): {', '.join(load_avg)}")
    except Exception as e:
        log_warn(f"Failed to get load averages: {e}")

def home_permissions() -> None:
    """
    Ensure correct ownership and permissions for the user's home directory.
    
    Sets ownership, applies the setgid bit to directories, and applies default ACLs if setfacl is available.
    """
    print_section("Home Directory Permissions")
    try:
        run_command(["chown", "-R", f"{USERNAME}:{USERNAME}", USER_HOME])
        log_info(f"Ownership of {USER_HOME} set to {USERNAME}.")
    except subprocess.CalledProcessError:
        handle_error(f"Failed to change ownership of {USER_HOME}.")
    try:
        run_command(["find", USER_HOME, "-type", "d", "-exec", "chmod", "g+s", "{}", ";"])
    except subprocess.CalledProcessError:
        log_warn("Failed to set setgid bit on some directories.")
    if command_exists("setfacl"):
        try:
            run_command(["setfacl", "-R", "-d", "-m", f"u:{USERNAME}:rwx", USER_HOME])
            log_info(f"Default ACLs applied on {USER_HOME}.")
        except subprocess.CalledProcessError:
            log_warn("Failed to apply default ACLs.")
    else:
        log_warn("setfacl not found; skipping default ACL configuration.")

def install_configure_zfs() -> None:
    """
    Install and configure ZFS.

    Installs required packages, enables ZFS services, attempts to import an existing ZFS pool,
    and sets the mount point if the pool is available. If the pool (WD_BLACK) is not found or
    fails to mount, the function logs a warning and skips the mountpoint configuration.
    """
    print_section("ZFS Installation and Configuration")
    zpool_name = "WD_BLACK"
    mount_point = f"/media/{zpool_name}"

    # Update package lists and install prerequisites
    try:
        run_command(["apt", "update"])
    except subprocess.CalledProcessError:
        log_error("Failed to update package lists. Skipping ZFS configuration.")
        return
    try:
        run_command(["apt", "install", "-y", "dpkg-dev", "linux-headers-generic", "linux-image-generic"])
    except subprocess.CalledProcessError:
        log_error("Failed to install prerequisites. Skipping ZFS configuration.")
        return
    try:
        run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"], check=True)
    except subprocess.CalledProcessError:
        log_error("Failed to install ZFS packages. Skipping ZFS configuration.")
        return

    # Enable ZFS services; continue even if these steps fail
    try:
        run_command(["systemctl", "enable", "zfs-import-cache.service"])
    except subprocess.CalledProcessError:
        log_warn("Could not enable zfs-import-cache.service.")
    try:
        run_command(["systemctl", "enable", "zfs-mount.service"])
    except subprocess.CalledProcessError:
        log_warn("Could not enable zfs-mount.service.")

    # Attempt to list or import the ZFS pool
    pool_imported = False
    try:
        subprocess.run(["zpool", "list", zpool_name],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_info(f"ZFS pool '{zpool_name}' is already imported.")
        pool_imported = True
    except subprocess.CalledProcessError:
        try:
            run_command(["zpool", "import", "-f", zpool_name])
            log_info(f"Imported ZFS pool '{zpool_name}'.")
            pool_imported = True
        except subprocess.CalledProcessError:
            log_warn(f"ZFS pool '{zpool_name}' not found or failed to import. Skipping mountpoint configuration.")

    # Set the mount point if the pool was imported successfully
    if pool_imported:
        try:
            run_command(["zfs", "set", f"mountpoint={mount_point}", zpool_name])
            log_info(f"Mountpoint for pool '{zpool_name}' set to '{mount_point}'.")
        except subprocess.CalledProcessError:
            log_warn(f"Failed to set mountpoint for ZFS pool '{zpool_name}'.")

def prompt_reboot() -> None:
    """
    Prompt the user for a system reboot to apply changes.
    
    If the user confirms, the system will be rebooted.
    """
    print_section("Reboot Prompt")
    answer = input("Would you like to reboot now? [y/N]: ").strip().lower()
    if answer == "y":
        log_info("Rebooting system now...")
        try:
            run_command(["shutdown", "-r", "now"])
        except subprocess.CalledProcessError:
            log_warn("Failed to reboot system.")
    else:
        log_info("Reboot canceled. Please reboot later for all changes to take effect.")

# ----------------------------
# Main Execution Flow
# ----------------------------

def main() -> None:
    """Main function executing the entire setup process."""
    check_root()
    check_network()

    update_system()
    install_packages()

    configure_timezone()

    setup_repos()
    copy_shell_configs()
    set_bash_shell()

    configure_ssh()
    setup_sudoers()
    configure_firewall()

    install_plex()
    install_fastfetch()

    docker_config()

    deploy_user_scripts()

    configure_periodic()

    backup_configs()
    rotate_logs()

    system_health_check()
    verify_firewall_rules()
    update_ssl_certificates()
    tune_system()

    home_permissions()
    install_configure_zfs()
    final_checks()

    prompt_reboot()

if __name__ == "__main__":
    main()