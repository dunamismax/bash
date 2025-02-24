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

import atexit
import datetime
import filecmp
import logging
import os
import platform
import shutil
import subprocess
import sys

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
    # Shells, editors, and basic utilities
    "bash",
    "vim",
    "nano",
    "screen",
    "tmux",
    "mc",
    "zsh",
    "htop",
    "tree",
    "ncdu",
    "neofetch",
    # Development tools and build systems
    "build-essential",
    "cmake",
    "ninja-build",
    "meson",
    "gettext",
    "git",
    "pkg-config",
    # SSH, firewall, and system management
    "openssh-server",
    "ufw",
    "curl",
    "wget",
    "rsync",
    "sudo",
    "bash-completion",
    # Python and related libraries
    "python3",
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "libssl-dev",
    "libffi-dev",
    "zlib1g-dev",
    "libreadline-dev",
    "libbz2-dev",
    "tk-dev",
    "xz-utils",
    "libncurses5-dev",
    "libgdbm-dev",
    "libnss3-dev",
    "liblzma-dev",
    "libxml2-dev",
    "libxmlsec1-dev",
    # Certificate management and system tools
    "ca-certificates",
    "software-properties-common",
    "apt-transport-https",
    "gnupg",
    "lsb-release",
    # Compilers and low-level tools
    "clang",
    "llvm",
    "netcat-openbsd",
    "lsof",
    "unzip",
    "zip",
    # Xorg and GUI utilities (if needed)
    "xorg",
    "x11-xserver-utils",
    "xterm",
    "alacritty",
    "fonts-dejavu-core",
    # Networking and diagnostic tools
    "net-tools",
    "nmap",
    "iftop",
    "iperf3",
    "tcpdump",
    "lynis",
    "traceroute",
    "mtr",
    # System monitoring and performance tools
    "iotop",
    "glances",
    # Programming languages and debugging tools
    "golang-go",
    "gdb",
    "cargo",
    # Security tools and penetration testing utilities
    "john",
    "hydra",
    "aircrack-ng",
    "nikto",
    "fail2ban",
    "rkhunter",
    "chkrootkit",
    # Database clients and servers
    "postgresql-client",
    "mysql-client",
    "redis-server",
    # Scripting languages and additional utilities
    "ruby",
    "rustc",
    "jq",
    "yq",
    "certbot",
    # Archiving and compression
    "p7zip-full",
    # Virtualization and emulation (optional; useful for testing and development)
    "qemu-system",
    "libvirt-clients",
    "libvirt-daemon-system",
    "virt-manager",
    "qemu-user-static",
]

# Terminal color definitions (Nord theme)
NORD9 = "\033[38;2;129;161;193m"  # Debug messages
NORD10 = "\033[38;2;94;129;172m"  # Secondary info
NORD11 = "\033[38;2;191;97;106m"  # Error messages
NORD13 = "\033[38;2;235;203;139m"  # Warning messages
NORD14 = "\033[38;2;163;190;140m"  # Info messages
NC = "\033[0m"  # Reset color

# ----------------------------
# Logging Setup
# ----------------------------


def setup_logging():
    """Configure logging to both file and console with color support."""
    if not os.path.exists(os.path.dirname(LOG_FILE)):
        os.makedirs(os.path.dirname(LOG_FILE), mode=0o700, exist_ok=True)

    logger = logging.getLogger("ubuntu_setup")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    # File handler for logging
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler with color support if output is tty
    class ColorFormatter(logging.Formatter):
        COLORS = {
            "DEBUG": NORD9,
            "INFO": NORD14,
            "WARNING": NORD13,
            "ERROR": NORD11,
            "CRITICAL": NORD11,
        }

        def format(self, record):
            color = self.COLORS.get(record.levelname, "")
            message = super().format(record)
            return f"{color}{message}{NC}"

    if sys.stderr.isatty():
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(
            ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
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


def save_config_snapshot() -> None:
    """
    Create a compressed archive of key configuration files as a snapshot backup
    before making any changes. This function packages files such as SSH, firewall,
    system tuning, and other critical configuration files into a tar.gz archive.
    """
    print_section("Configuration Snapshot Backup")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = "/var/backups"
    snapshot_file = os.path.join(backup_dir, f"config_snapshot_{timestamp}.tar.gz")
    os.makedirs(backup_dir, exist_ok=True)

    # List of configuration files to include in the snapshot.
    config_files = [
        "/etc/ssh/sshd_config",
        "/etc/ufw/user.rules",
        "/etc/ntp.conf",
        "/etc/sysctl.conf",
        "/etc/environment",
        "/etc/fail2ban/jail.local",
        "/etc/docker/daemon.json",
        "/etc/caddy/Caddyfile",
    ]

    try:
        import tarfile

        with tarfile.open(snapshot_file, "w:gz") as tar:
            for cfg in config_files:
                if os.path.isfile(cfg):
                    # Add file with its basename so the archive is not cluttered with full paths.
                    tar.add(cfg, arcname=os.path.basename(cfg))
                    log_info(f"Included {cfg} in snapshot.")
                else:
                    log_warn(f"Configuration file {cfg} not found; skipping.")
        log_info(f"Configuration snapshot saved as {snapshot_file}.")
    except Exception as e:
        log_warn(f"Failed to create configuration snapshot: {e}")


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
                stderr=subprocess.DEVNULL,
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
        subprocess.run(
            ["dpkg", "-s", "openssh-server"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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


def configure_firewall() -> None:
    """
    Configure the UFW firewall.

    This function sets default policies, allows specific TCP ports,
    checks if UFW is active, and if not, enables it. It also ensures
    the UFW service is enabled and started via systemctl.
    """
    print_section("Firewall Configuration")
    log_info("Configuring firewall using UFW...")

    ufw_cmd = "/usr/sbin/ufw"
    # Verify that the ufw command exists and is executable
    if not (os.path.isfile(ufw_cmd) and os.access(ufw_cmd, os.X_OK)):
        handle_error("UFW command not found. Please install UFW.")

    # Set default policies
    default_commands = [
        ([ufw_cmd, "default", "deny", "incoming"], "set default deny for incoming traffic"),
        ([ufw_cmd, "default", "allow", "outgoing"], "set default allow for outgoing traffic"),
    ]
    for cmd, description in default_commands:
        try:
            run_command(cmd)
            log_info(f"Successfully {description}.")
        except subprocess.CalledProcessError:
            log_warn(f"Failed to {description}.")

    # Allow necessary ports (TCP only)
    allowed_ports = ["22", "80", "443", "32400"]
    for port in allowed_ports:
        try:
            run_command([ufw_cmd, "allow", f"{port}/tcp"])
            log_info(f"Allowed TCP port {port}.")
        except subprocess.CalledProcessError:
            log_warn(f"Failed to allow TCP port {port}.")

    # Check UFW status and enable if inactive
    try:
        # Ensure text output for reliable string comparison
        result = run_command([ufw_cmd, "status"], capture_output=True, text=True)
        if "inactive" in result.stdout.lower():
            try:
                run_command([ufw_cmd, "--force", "enable"])
                log_info("UFW firewall has been enabled.")
            except subprocess.CalledProcessError:
                handle_error("Failed to enable UFW firewall.")
        else:
            log_info("UFW firewall is already active.")
    except subprocess.CalledProcessError:
        handle_error("Failed to retrieve UFW status.")

    # Ensure ufw service is enabled and started via systemctl
    service_commands = [
        (["systemctl", "enable", "ufw"], "enable ufw service"),
        (["systemctl", "start", "ufw"], "start ufw service"),
    ]
    for cmd, description in service_commands:
        try:
            run_command(cmd)
            log_info(f"Successfully executed: {' '.join(cmd)}.")
        except subprocess.CalledProcessError:
            log_warn(f"Failed to {description}.")

    log_info("Firewall configuration completed successfully.")


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
        subprocess.run(
            ["dpkg", "-s", "plexmediaserver"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
        subprocess.run(
            ["dpkg", "-s", "fastfetch"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
            subprocess.run(
                ["nc", "-z", "-w3", "127.0.0.1", port],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
            run_command(["sysctl", "-w", "net.ipv4.tcp_rmem=4096 87380 6291456"])
            run_command(["sysctl", "-w", "net.ipv4.tcp_wmem=4096 16384 4194304"])
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
    Install and configure ZFS for external pool 'WD_BLACK' with mount point '/media/WD_BLACK'.

    This function:
      - Updates package lists and installs prerequisites and ZFS packages.
      - Enables the ZFS import and mount services.
      - Creates the desired mount point directory.
      - Imports the ZFS pool (if not already imported).
      - Sets the mountpoint property on the pool.
      - Updates the pool cachefile property to ensure auto-import at boot.
      - Attempts to mount all ZFS datasets and verifies the mount.
    """
    print_section("ZFS Installation and Configuration")
    zpool_name = "WD_BLACK"
    mount_point = f"/media/{zpool_name}"
    cache_file = "/etc/zfs/zpool.cache"

    # Update package lists and install prerequisites
    try:
        run_command(["apt", "update"])
        run_command(
            ["apt", "install", "-y", "dpkg-dev", "linux-headers-generic", "linux-image-generic"]
        )
        run_command(["apt", "install", "-y", "zfs-dkms", "zfsutils-linux"], check=True)
        log_info("Prerequisites and ZFS packages installed successfully.")
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to install prerequisites or ZFS packages: {e}")
        return

    # Enable ZFS services (import and mount)
    for service in ["zfs-import-cache.service", "zfs-mount.service"]:
        try:
            run_command(["systemctl", "enable", service])
            log_info(f"Enabled {service}.")
        except subprocess.CalledProcessError:
            log_warn(f"Could not enable {service}.")

    # Ensure the mount point directory exists
    if not os.path.isdir(mount_point):
        try:
            os.makedirs(mount_point, exist_ok=True)
            log_info(f"Created mount point directory: {mount_point}")
        except Exception as e:
            log_warn(f"Failed to create mount point directory {mount_point}: {e}")

    # Import the pool if it is not already imported
    pool_imported = False
    try:
        subprocess.run(
            ["zpool", "list", zpool_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log_info(f"ZFS pool '{zpool_name}' is already imported.")
        pool_imported = True
    except subprocess.CalledProcessError:
        try:
            run_command(["zpool", "import", "-f", zpool_name])
            log_info(f"Imported ZFS pool '{zpool_name}'.")
            pool_imported = True
        except subprocess.CalledProcessError:
            log_warn(f"ZFS pool '{zpool_name}' not found or failed to import.")

    if not pool_imported:
        log_warn(f"ZFS pool '{zpool_name}' could not be imported. Skipping further configuration.")
        return

    # Set the mountpoint property on the pool/dataset
    try:
        run_command(["zfs", "set", f"mountpoint={mount_point}", zpool_name])
        log_info(f"Set mountpoint for pool '{zpool_name}' to '{mount_point}'.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to set mountpoint for ZFS pool '{zpool_name}': {e}")

    # Update the pool cachefile so it is recorded for auto-import at boot
    try:
        run_command(["zpool", "set", f"cachefile={cache_file}", zpool_name])
        log_info(f"Updated cachefile for pool '{zpool_name}' to '{cache_file}'.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to update cachefile for ZFS pool '{zpool_name}': {e}")

    # Attempt to mount all ZFS datasets
    try:
        run_command(["zfs", "mount", "-a"])
        log_info("Mounted all ZFS datasets.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to mount ZFS datasets: {e}")

    # Verify that the pool is mounted at the desired mount point
    try:
        mounts = subprocess.check_output(["zfs", "list", "-o", "name,mountpoint", "-H"], text=True)
        if any(mount_point in line for line in mounts.splitlines()):
            log_info(f"ZFS pool '{zpool_name}' is successfully mounted at '{mount_point}'.")
        else:
            log_warn(
                f"ZFS pool '{zpool_name}' is not mounted at '{mount_point}'. Please check manually."
            )
    except Exception as e:
        log_warn(f"Error verifying mount status for ZFS pool '{zpool_name}': {e}")


def configure_fail2ban() -> None:
    """
    Configure and enable fail2ban with a secure basic default configuration.

    This function creates (or backs up and overwrites) the /etc/fail2ban/jail.local file
    with settings that protect SSH by default, then enables and restarts the fail2ban service.
    """
    print_section("Fail2ban Configuration")
    jail_local = "/etc/fail2ban/jail.local"
    config_content = """[DEFAULT]
# Ban IPs for 10 minutes after reaching max retries
bantime  = 600
# Look for failed attempts within 10 minutes
findtime = 600
# Ban an IP after 3 failed login attempts
maxretry = 3
# Use systemd for reading logs on modern systems
backend  = systemd
# Resolve DNS only if necessary; warn if issues occur
usedns   = warn

[sshd]
enabled  = true
port     = ssh
logpath  = /var/log/auth.log
maxretry = 3
"""
    # Backup existing configuration if present
    if os.path.isfile(jail_local):
        backup_file(jail_local)

    try:
        with open(jail_local, "w") as f:
            f.write(config_content)
        log_info("Fail2ban configuration written to /etc/fail2ban/jail.local.")
    except Exception as e:
        log_warn(f"Failed to write Fail2ban configuration: {e}")

    # Enable and restart fail2ban service to apply the new configuration
    try:
        run_command(["systemctl", "enable", "fail2ban"])
        run_command(["systemctl", "restart", "fail2ban"])
        log_info("Fail2ban service enabled and restarted successfully.")
    except subprocess.CalledProcessError:
        log_warn("Failed to enable or restart the Fail2ban service.")


def configure_wayland() -> None:
    """
    Configure environment variables to enable Wayland for default applications.

    This function updates the system-wide environment file (/etc/environment)
    and creates a user-specific environment file at ~/.config/environment.d/myenvvars.conf
    with the following variables:
      - GDK_BACKEND=wayland
      - QT_QPA_PLATFORM=wayland
      - SDL_VIDEODRIVER=wayland

    These settings ensure that GUI applications using GTK, Qt, or SDL default to Wayland.
    """
    print_section("Wayland Environment Configuration")

    # Desired environment variables for Wayland support
    env_vars = {
        "GDK_BACKEND": "wayland",
        "QT_QPA_PLATFORM": "wayland",
        "SDL_VIDEODRIVER": "wayland",
    }

    # ----------------------------
    # Update /etc/environment
    # ----------------------------
    etc_env_file = "/etc/environment"
    try:
        # Read existing content, or use empty list if file doesn't exist
        if os.path.isfile(etc_env_file):
            backup_file(etc_env_file)
            with open(etc_env_file, "r") as f:
                lines = f.readlines()
        else:
            lines = []

        # Build a dictionary from existing assignments (if any)
        current_vars = {}
        for line in lines:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                current_vars[key] = val

        # Flag to determine if we need to write the file back
        updated = False

        # Update or append each desired variable
        for key, value in env_vars.items():
            desired_assignment = f"{key}={value}"
            if key in current_vars:
                if current_vars[key] != value:
                    # Update the assignment in the list
                    for i, line in enumerate(lines):
                        if line.strip().startswith(f"{key}="):
                            lines[i] = desired_assignment + "\n"
                    log_info(f"Updated {key} in {etc_env_file}.")
                    updated = True
                else:
                    log_info(f"{key} already set to {value} in {etc_env_file}.")
            else:
                lines.append(desired_assignment + "\n")
                log_info(f"Added {key} to {etc_env_file}.")
                updated = True

        if updated:
            with open(etc_env_file, "w") as f:
                f.writelines(lines)
            log_info(f"{etc_env_file} updated with Wayland environment variables.")
        else:
            log_info(f"No changes needed for {etc_env_file}.")
    except Exception as e:
        log_warn(f"Failed to update {etc_env_file}: {e}")

    # ----------------------------
    # Create/Update User-Specific Environment File
    # ----------------------------
    user_env_dir = os.path.join(USER_HOME, ".config", "environment.d")
    user_env_file = os.path.join(user_env_dir, "myenvvars.conf")
    try:
        os.makedirs(user_env_dir, exist_ok=True)
        # Build the desired content string
        content_lines = [f"{key}={value}\n" for key, value in env_vars.items()]
        desired_content = "".join(content_lines)

        if os.path.isfile(user_env_file):
            with open(user_env_file, "r") as f:
                current_content = f.read()
            if current_content.strip() == desired_content.strip():
                log_info(f"{user_env_file} already contains the desired Wayland settings.")
            else:
                backup_file(user_env_file)
                with open(user_env_file, "w") as f:
                    f.write(desired_content)
                log_info(f"Updated {user_env_file} with Wayland environment variables.")
        else:
            with open(user_env_file, "w") as f:
                f.write(desired_content)
            log_info(f"Created {user_env_file} with Wayland environment variables.")

        # Ensure proper ownership for the user-specific file
        run_command(["chown", f"{USERNAME}:{USERNAME}", user_env_file])
    except Exception as e:
        log_warn(f"Failed to update user environment file {user_env_file}: {e}")


def install_brave_browser() -> None:
    """
    Install the Brave browser on Ubuntu.

    This function downloads and executes the Brave installation script from:
      https://dl.brave.com/install.sh

    It uses the following command:
      curl -fsS https://dl.brave.com/install.sh | sh

    Logs progress and handles errors accordingly.
    """
    print_section("Brave Browser Installation")
    log_info("Installing Brave browser...")

    try:
        # Execute the Brave install script using sh
        run_command(["sh", "-c", "curl -fsS https://dl.brave.com/install.sh | sh"])
        log_info("Brave browser installed successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to install Brave browser: {e}")


def install_flatpak_and_apps() -> None:
    """
    Install Flatpak and the GNOME Software Flatpak plugin, add the Flathub repository,
    and then install a list of Flatpak applications from Flathub.

    Steps performed:
      1. Install Flatpak: sudo apt install flatpak
      2. Install GNOME Software Flatpak plugin: sudo apt install gnome-software-plugin-flatpak
      3. Add the Flathub repository:
             flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
      4. Install the list of Flatpak apps listed below

    Uses the run_command(), print_section(), log_info(), log_warn(), and handle_error()
    functions from the master script.
    """
    # Print section header for clarity
    print_section("Flatpak Installation and Setup")

    # Install Flatpak
    log_info("Installing Flatpak...")
    try:
        run_command(["apt", "install", "-y", "flatpak"])
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to install Flatpak: {e}")

    # Install GNOME Software Flatpak plugin
    log_info("Installing GNOME Software Flatpak plugin...")
    try:
        run_command(["apt", "install", "-y", "gnome-software-plugin-flatpak"])
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to install GNOME Software Flatpak plugin: {e}")

    # Add the Flathub repository
    log_info("Adding Flathub repository...")
    try:
        run_command(
            [
                "flatpak",
                "remote-add",
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ]
        )
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to add Flathub repository: {e}")

    # List of Flatpak apps to install from Flathub
    flatpak_apps = [
        "com.discordapp.Discord",
        "com.usebottles.bottles",
        "com.valvesoftware.Steam",
        "com.spotify.Client",
        "org.videolan.VLC",
        "org.libretro.RetroArch",
        "com.obsproject.Studio",
        "com.github.tchx84.Flatseal",
        "net.lutris.Lutris",
        "net.davidotek.pupgui2",
        "org.gimp.GIMP",
        "org.qbittorrent.qBittorrent",
        "com.github.Matoking.protontricks",
        "md.obsidian.Obsidian",
        "org.prismlauncher.PrismLauncher",
        "com.bitwarden.desktop",
        "org.kde.kdenlive",
        "org.signal.Signal",
        "org.gnome.Boxes",
        "com.stremio.Stremio",
        "org.blender.Blender",
        "org.localsend.localsend_app",
        "fr.handbrake.ghb",
        "org.remmina.Remmina",
        "org.audacityteam.Audacity",
        "com.rustdesk.RustDesk",
        "com.getpostman.Postman",
        "io.github.aandrew_me.ytdn",
        "org.shotcut.Shotcut",
        "com.calibre_ebook.calibre",
        "tv.plex.PlexDesktop",
        "org.filezillaproject.Filezilla",
        "com.github.k4zmu2a.spacecadetpinball",
        "org.virt_manager.virt-manager",
        "org.raspberrypi.rpi-imager",
    ]

    # Install each Flatpak app
    log_info("Installing Flatpak applications from Flathub...")
    for app in flatpak_apps:
        log_info(f"Installing {app}...")
        try:
            run_command(["flatpak", "install", "--assumeyes", "flathub", app])
            log_info(f"{app} installed successfully.")
        except subprocess.CalledProcessError as e:
            log_warn(f"Failed to install {app}: {e}")


def install_configure_caddy() -> None:
    """
    Install and configure the Caddy web server.

    Steps performed:
      1. Download the Caddy deb package from:
         https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb
      2. Install Caddy using dpkg and fix dependency issues if necessary.
      3. Remove the temporary deb file.
      4. Copy the custom Caddyfile from /home/sawyer/github/linux/ubuntu/dotfiles/Caddyfile
         to the default location (/etc/caddy/Caddyfile), backing up any existing file.
      5. Enable the Caddy service and restart it.
    """
    print_section("Caddy Installation and Configuration")
    log_info("Installing Caddy web server...")

    # Define URLs and paths
    caddy_deb_url = (
        "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_linux_amd64.deb"
    )
    temp_deb = "/tmp/caddy_2.9.1_linux_amd64.deb"

    # Download the Caddy package
    try:
        run_command(["curl", "-L", "-o", temp_deb, caddy_deb_url])
        log_info("Caddy package downloaded successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to download Caddy package: {e}")

    # Install the Caddy package
    try:
        run_command(["dpkg", "-i", temp_deb])
    except subprocess.CalledProcessError:
        log_warn("Dependency issues encountered during Caddy installation. Attempting to fix...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError as e:
            handle_error(f"Failed to resolve dependencies for Caddy: {e}")
    log_info("Caddy installed successfully.")

    # Remove the temporary deb package file
    try:
        os.remove(temp_deb)
        log_info("Removed temporary Caddy package file.")
    except Exception as e:
        log_warn(f"Failed to remove temporary file {temp_deb}: {e}")

    # Copy the custom Caddyfile
    source_caddyfile = "/home/sawyer/github/linux/ubuntu/dotfiles/Caddyfile"
    dest_caddyfile = "/etc/caddy/Caddyfile"
    if not os.path.isfile(source_caddyfile):
        log_warn(
            f"Source Caddyfile not found at {source_caddyfile}. Skipping Caddyfile configuration."
        )
    else:
        if os.path.exists(dest_caddyfile):
            backup_file(dest_caddyfile)
        try:
            shutil.copy2(source_caddyfile, dest_caddyfile)
            log_info(f"Copied {source_caddyfile} to {dest_caddyfile}.")
        except Exception as e:
            log_warn(f"Failed to copy Caddyfile: {e}")

    # Enable the Caddy service
    try:
        run_command(["systemctl", "enable", "caddy"])
        log_info("Caddy service enabled.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to enable Caddy service: {e}")

    # Start (or restart) the Caddy service
    try:
        run_command(["systemctl", "restart", "caddy"])
        log_info("Caddy service started successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to start Caddy service: {e}")


def install_and_configure_timeshift() -> None:
    """
    Install Timeshift, create an initial system snapshot, and configure automated daily snapshots.

    This function installs Timeshift via apt, runs a scripted command to create an initial snapshot,
    and then writes a cron job in /etc/cron.daily to perform daily snapshots.
    """
    print_section("Timeshift Installation and Snapshot Configuration")

    # Install Timeshift
    try:
        run_command(["apt", "install", "-y", "timeshift"])
        log_info("Timeshift installed successfully.")
    except subprocess.CalledProcessError:
        handle_error("Failed to install Timeshift.")

    # Create an initial snapshot using Timeshift
    try:
        run_command(
            [
                "timeshift",
                "--create",
                "--comments",
                "Initial system snapshot",
                "--tags",
                "D",
                "--scripted",
            ]
        )
        log_info("Initial system snapshot created successfully using Timeshift.")
    except subprocess.CalledProcessError:
        log_warn("Failed to create initial system snapshot with Timeshift.")

    # Configure auto snapshots via a daily cron job.
    cron_file = "/etc/cron.daily/timeshift_auto_snapshot"
    cron_content = """#!/bin/sh
# Timeshift Auto Snapshot - Daily Snapshot
timeshift --create --scripted --comments "Automated daily snapshot" --tags D
"""
    try:
        with open(cron_file, "w") as f:
            f.write(cron_content)
        os.chmod(cron_file, 0o755)
        log_info(f"Auto snapshot cron job created at {cron_file}.")
    except Exception as e:
        log_warn(f"Failed to create auto snapshot cron job: {e}")


def configure_unattended_upgrades() -> None:
    """
    Install and configure unattended-upgrades for automatic security updates.
    """
    print_section("Unattended Upgrades Configuration")
    try:
        run_command(["apt", "install", "-y", "unattended-upgrades"])
        # You could also copy or write a custom configuration file to /etc/apt/apt.conf.d/50unattended-upgrades
        log_info(
            "Unattended-upgrades installed. Please review /etc/apt/apt.conf.d/50unattended-upgrades for customization."
        )
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to install unattended-upgrades: {e}")


def cleanup_system() -> None:
    """
    Clean up temporary files, remove unused packages, and clear apt cache.
    """
    print_section("System Cleanup")
    try:
        run_command(["apt", "autoremove", "-y"])
        run_command(["apt", "clean"])
        log_info("System cleanup completed: unused packages removed and apt cache cleared.")
    except subprocess.CalledProcessError as e:
        log_warn(f"System cleanup failed: {e}")


def configure_apparmor() -> None:
    """
    Install and enable AppArmor along with its utilities.
    """
    print_section("AppArmor Configuration")
    try:
        run_command(["apt", "install", "-y", "apparmor", "apparmor-utils"])
        run_command(["systemctl", "enable", "apparmor"])
        run_command(["systemctl", "start", "apparmor"])
        log_info("AppArmor installed and started successfully.")
    except subprocess.CalledProcessError as e:
        log_warn(f"Failed to install or start AppArmor: {e}")


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
    save_config_snapshot()
    install_and_configure_timeshift()
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
    configure_fail2ban()
    install_configure_zfs()
    install_brave_browser()
    install_flatpak_and_apps()
    install_configure_caddy()
    configure_unattended_upgrades()
    configure_apparmor()
    cleanup_system()
    configure_wayland()
    final_checks()

    prompt_reboot()


if __name__ == "__main__":
    main()
