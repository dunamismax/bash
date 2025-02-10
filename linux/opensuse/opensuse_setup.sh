#!/usr/bin/env bash
################################################################################
# OpenSUSE Automated Setup & Hardening Script
#
# Description:
#   This script fully automates the configuration of a fresh OpenSUSE server,
#   creating a secure, optimized, and personalized environment suitable for
#   headless deployments. Its comprehensive functions include:
#
#     • System Preparation:
#         - Verifies network connectivity.
#         - Refreshes repositories and updates installed packages.
#
#     • Package Installation:
#         - Installs essential system utilities, shells, editors, and CLI tools.
#         - Deploys development and build dependencies (compilers, libraries,
#           build systems, etc.) along with additional productivity utilities.
#
#     • Security Enhancements:
#         - Configures and hardens the OpenSSH server (custom port, disabled
#           root login and password authentication).
#         - Enables and configures firewalld with permanent rules for key services.
#         - Installs and configures fail2ban to protect against brute-force attacks.
#         - Applies kernel parameter tuning (via sysctl) for system hardening.
#         - Enables persistent systemd journaling for improved log management.
#         - Sets up automatic system updates via a custom systemd timer.
#
#     • Containerization & Third-Party Services:
#         - Installs and configures Docker and Docker Compose, including daemon
#           settings and user group modifications.
#         - Installs the Visual Studio Code CLI.
#
#     • Repository and Dotfiles Setup:
#         - Clones designated GitHub repositories and applies custom dotfiles.
#         - Sets correct permissions and secures configuration directories.
#
#     • Custom Service Deployment:
#         - Creates and enables custom systemd services for managing various
#           DunamisMax web applications (e.g., AI Agents, File Converter,
#           Messenger, Notes, and the Main Website).
#
#     • Finalization & Cleanup:
#         - Cleans up package caches and logs critical system information.
#         - Prompts for a system reboot to ensure all changes take effect.
#
# Usage:
#   Run this script as root (or via sudo). Adjust configuration variables
#   at the top of the script as needed to match your environment.
#
# Author : sawyer
# License: MIT
################################################################################

# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?"' ERR

# Log file path (ensure the directory is writable)
LOG_FILE="/var/log/opensuse_setup.log"

# Default username to configure; if not present, it will be created.
USERNAME="sawyer"

# -------------------------------------------------------------------------------
# Essential Package List (CLI-only environment, OpenSUSE)
# -------------------------------------------------------------------------------
PACKAGES=(
  # Shells & Terminal Multiplexers
  bash
  zsh
  fish
  vim
  nano
  emacs
  mc
  neovim
  screen
  tmux

  # Development & Build Tools
  gcc
  gcc-c++
  make
  cmake
  meson
  intltool
  gettext
  pigz
  libtool
  pkg-config
  bzip2
  xz
  git
  hugo

  # System & Network Services
  openssh
  acpid
  chrony
  fail2ban
  sudo
  bash-completion
  logrotate
  net-tools
  firewalld

  # Virtualization, Storage & Containers
  qemu-kvm
  libvirt
  virt-install
  bridge-utils
  docker
  docker-compose

  # Networking & Hardware Tools
  curl
  wget
  tcpdump
  rsync
  nmap
  lynx
  bind-utils
  iftop
  mtr
  iw
  rfkill
  netcat
  socat
  speedtest-cli

  # Monitoring & Diagnostics
  htop
  neofetch
  tig
  jq
  vnstat
  tree
  fzf
  which
  smartmontools
  lsof
  dstat
  sysstat
  iotop
  inotify-tools
  pv
  nethogs
  strace
  ltrace
  atop

  # Filesystem, Disk & Compression Utilities
  gdisk
  ntfs-3g
  ncdu
  unzip
  zip
  parted
  lvm2
  btrfs-progs

  # Scripting & Productivity Tools
  perl
  patch
  bc
  gawk
  expect

  # Code Navigation & Developer Productivity
  fd
  bat
  ripgrep
  hyperfine
  cheat

  # Multimedia & Backup Applications
  ffmpeg
  restic
  mpv

  # Terminal Enhancements & File Management
  byobu
  ranger
  nnn

  # Communication & Productivity
  mutt
  newsboat
  irssi
  weechat
  httpie
  youtube-dl
  thefuck

  # Task & Calendar Management
  taskwarrior
  calcurse

  # Code & Text Processing Enhancements
  asciinema

  # Fun & Miscellaneous
  cowsay
  figlet
)

# -------------------------------------------------------------------------------
# Nord Color Theme (Enhanced)
# -------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'
YELLOW='\033[38;2;235;203;139m'
GREEN='\033[38;2;163;190;140m'
BLUE='\033[38;2;94;129;172m'
CYAN='\033[38;2;136;192;208m'
MAGENTA='\033[38;2;180;142;173m'
GRAY='\033[38;2;216;222;233m'
NC='\033[0m'

# ==============================================================================
# 2. UTILITY & LOGGING FUNCTIONS
# ==============================================================================
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)    color="${GREEN}" ;;
        WARN|WARNING) color="${YELLOW}" ;;
        ERROR)   color="${RED}" ;;
        DEBUG)   color="${BLUE}" ;;
        *)       color="${NC}" ;;
    esac
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

warn() {
    log WARN "$@"
}

handle_error() {
    local error_message="${1:-"An error occurred. See the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    exit "$exit_code"
}

# ==============================================================================
# 3. SYSTEM PREPARATION FUNCTIONS
# ==============================================================================
ensure_user() {
    if id "$USERNAME" &>/dev/null; then
        log INFO "User '$USERNAME' already exists."
    else
        log INFO "User '$USERNAME' does not exist. Creating user..."
        useradd -m -s /bin/bash "$USERNAME" || handle_error "Failed to create user $USERNAME."
        log INFO "User '$USERNAME' created successfully."
    fi
}

check_network() {
    if ! ping -c 1 google.com &>/dev/null; then
        handle_error "No network connectivity. Please check your network settings."
    else
        log INFO "Network connectivity verified."
    fi
}

update_system() {
    log INFO "Refreshing repositories..."
    zypper --non-interactive refresh || handle_error "Failed to refresh repositories."
    log INFO "Updating installed packages..."
    zypper --non-interactive update || handle_error "Failed to update packages."
    log INFO "System update completed successfully."
}

# ==============================================================================
# 4. CORE CONFIGURATION FUNCTIONS
# ==============================================================================
configure_ssh() {
    log INFO "Configuring OpenSSH Server..."
    if ! rpm -q openssh &>/dev/null; then
        zypper --non-interactive install openssh || handle_error "Failed to install OpenSSH Server."
        log INFO "OpenSSH Server installed."
    else
        log INFO "OpenSSH Server is already installed."
    fi

    systemctl enable --now sshd || handle_error "Failed to enable/start SSH service."

    local sshd_config="/etc/ssh/sshd_config"
    local backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup sshd_config."
    log INFO "Backed up sshd_config to $backup."

    declare -A ssh_settings=(
        ["Port"]="22"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="no"
        ["Protocol"]="2"
        ["MaxAuthTries"]="4"
    )
    for key in "${!ssh_settings[@]}"; do
        if grep -q "^${key} " "$sshd_config"; then
            sed -i "s/^${key} .*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done

    systemctl restart sshd || handle_error "Failed to restart SSH service."
    log INFO "SSH configuration updated successfully."
}

install_packages() {
    log INFO "Installing essential packages..."
    local to_install=()
    for pkg in "${PACKAGES[@]}"; do
        if ! rpm -q "$pkg" &>/dev/null; then
            to_install+=("$pkg")
        else
            log INFO "Package $pkg is already installed."
        fi
    done
    if [ "${#to_install[@]}" -gt 0 ]; then
        log INFO "Installing packages: ${to_install[*]}"
        zypper --non-interactive install "${to_install[@]}" || handle_error "Failed to install essential packages."
    else
        log INFO "All essential packages are already installed."
    fi
}

# -------------------------------------------------------------------------------
# Configure firewalld (instead of UFW)
# -------------------------------------------------------------------------------
configure_firewalld() {
    log INFO "Configuring firewalld firewall..."
    if ! rpm -q firewalld &>/dev/null; then
        zypper --non-interactive install firewalld || handle_error "Failed to install firewalld."
    fi
    systemctl enable --now firewalld || handle_error "Failed to enable/start firewalld."
    # Open ports for ssh, http, https and Plex (if applicable)
    for service in ssh http https; do
        firewall-cmd --permanent --add-service="$service" || warn "Could not add service: $service"
        log INFO "Added firewall service: $service"
    done
    # Example of adding a specific TCP port (e.g., Plex at 32400)
    firewall-cmd --permanent --add-port=32400/tcp || warn "Could not open port 32400/tcp"
    firewall-cmd --reload || warn "Failed to reload firewall configuration."
    log INFO "firewalld configuration completed."
}

release_ports() {
    log INFO "Releasing occupied network ports..."
    local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
    local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")
    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on TCP port $port: $pids"
            kill -9 $pids || warn "Failed to kill processes on TCP port $port"
        fi
    done
    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on UDP port $port: $pids"
            kill -9 $pids || warn "Failed to kill processes on UDP port $port"
        fi
    done
    log INFO "Port release process completed."
}

configure_fail2ban() {
    log INFO "Installing and configuring fail2ban..."
    if ! rpm -q fail2ban &>/dev/null; then
        zypper --non-interactive install fail2ban || handle_error "Failed to install fail2ban."
        log INFO "fail2ban installed successfully."
    else
        log INFO "fail2ban is already installed."
    fi
    systemctl enable --now fail2ban || handle_error "Failed to enable/start fail2ban."
    log INFO "fail2ban configured successfully."
}

configure_journald() {
    log INFO "Configuring systemd journal for persistent logging..."
    mkdir -p /var/log/journal || handle_error "Failed to create /var/log/journal directory."
    systemctl restart systemd-journald || warn "Failed to restart systemd-journald."
    log INFO "Persistent journaling is now configured."
}

install_build_dependencies() {
    log INFO "Installing build dependencies..."
    local deps=(
        gcc gcc-c++ make cmake git curl wget vim tmux unzip zip
        ca-certificates lsb-release gnupg jq pkg-config
        libopenssl-devel libbz2-devel libffi-devel zlib-devel readline-devel
        sqlite3-devel tk-devel ncurses-devel gdbm-devel xz-devel gdb llvm
    )
    zypper --non-interactive install "${deps[@]}" || handle_error "Failed to install build dependencies."
    log INFO "Installing Rust toolchain..."
    if ! command -v rustc &>/dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || handle_error "Rust toolchain installation failed."
        export PATH="$HOME/.cargo/bin:$PATH"
        log INFO "Rust toolchain installed successfully."
    else
        log INFO "Rust toolchain is already installed."
    fi
    log INFO "Installing Go..."
    zypper --non-interactive install golang || handle_error "Failed to install Go."
    log INFO "Build dependencies installed successfully."
}

install_caddy() {
    log INFO "Installing Caddy web server..."
    if rpm -q caddy &>/dev/null; then
        log INFO "Caddy is already installed."
    else
        zypper --non-interactive install caddy || handle_error "Failed to install Caddy."
    fi
    log INFO "Caddy web server installed successfully."
}

install_plex() {
    log INFO "Installing Plex Media Server..."

    # Check if Plex is already installed.
    if rpm -q plexmediaserver &>/dev/null; then
        log INFO "Plex Media Server is already installed."
        return
    fi

    # Ensure curl is installed (required to download the RPM).
    if ! command -v curl &>/dev/null; then
        zypper --non-interactive install curl || handle_error "Failed to install curl required for Plex."
    fi

    # Import Plex GPG key so that signature verification passes.
    log INFO "Importing Plex GPG key..."
    rpm --import https://downloads.plex.tv/plex-keys/PlexSign.key || handle_error "Failed to import Plex GPG key."

    # Hard-coded URL for the Plex RPM (RedHat version).
    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/redhat/plexmediaserver-1.41.3.9314-a0bfb8370.x86_64.rpm"
    local plex_rpm="plexmediaserver-1.41.3.9314-a0bfb8370.x86_64.rpm"

    log INFO "Downloading Plex package from $plex_url..."
    curl -LO "$plex_url" || handle_error "Failed to download Plex package."

    log INFO "Installing Plex Media Server RPM..."
    if ! zypper --non-interactive install "$plex_rpm"; then
        # If normal installation fails, attempt forcing resolution.
        zypper --non-interactive install --force-resolution "$plex_rpm" || handle_error "Failed to install Plex Media Server."
    fi

    # After installation, the RPM installs a repository configuration file.
    # Enable the Plex repository by modifying the repo file.
    if [ -f /etc/zypp/repos.d/plex.repo ]; then
        log INFO "Enabling Plex repository in /etc/zypp/repos.d/plex.repo..."
        sed -i 's/enabled=0/enabled=1/' /etc/zypp/repos.d/plex.repo
    elif [ -f /etc/yum.repos.d/plex.repo ]; then
        log INFO "Enabling Plex repository in /etc/yum.repos.d/plex.repo..."
        sed -i 's/enabled=0/enabled=1/' /etc/yum.repos.d/plex.repo
    else
        warn "Plex repository file not found. Please enable PlexRepo manually in your Software Repositories."
    fi

    # Refresh repositories so that PlexRepo becomes active.
    zypper --non-interactive refresh

    # Create the 'plex' group if it does not exist.
    if ! getent group plex &>/dev/null; then
        log INFO "Creating plex group..."
        groupadd plex || handle_error "Failed to create plex group."
    fi

    # Ensure that a 'plex' user exists. If not, create a system user with no login.
    if ! id plex &>/dev/null; then
        log INFO "Creating plex user..."
        useradd -r -g plex -d /var/lib/plexmediaserver -s /sbin/nologin plex || handle_error "Failed to create plex user."
    fi

    # Adjust ownership and permissions on the Plex library directory.
    if [ -d /var/lib/plexmediaserver ]; then
        log INFO "Setting group ownership and write permissions on /var/lib/plexmediaserver..."
        chown :plex /var/lib/plexmediaserver || warn "Failed to change group ownership for /var/lib/plexmediaserver."
        chmod g+w /var/lib/plexmediaserver || warn "Failed to add group write permission to /var/lib/plexmediaserver."
    else
        warn "/var/lib/plexmediaserver directory not found."
    fi

    # Workaround: Add a cron job to start Plex a minute after reboot.
    log INFO "Adding cron job to start Plex Media Server after boot..."
    if ! crontab -l 2>/dev/null | grep -q "systemctl start plexmediaserver.service"; then
        (crontab -l 2>/dev/null; echo "@reboot sleep 60; systemctl start plexmediaserver.service") | crontab - \
            || warn "Failed to add Plex service activation cron job."
    fi

    # Enable and restart the Plex service.
    systemctl enable plexmediaserver || warn "Failed to enable Plex Media Server service."
    systemctl restart plexmediaserver || warn "Failed to start Plex Media Server service."

    log INFO "Plex Media Server installed and configured successfully."

    # Clean up the downloaded RPM file.
    rm -f "$plex_rpm" || warn "Failed to remove Plex RPM package file."
}

setup_repos_and_dotfiles() {
    log INFO "Setting up GitHub repositories and dotfiles..."
    local GITHUB_DIR="/home/${USERNAME}/github"
    local USER_HOME="/home/${USERNAME}"

    mkdir -p "$GITHUB_DIR" || handle_error "Failed to create GitHub directory: $GITHUB_DIR"
    cd "$GITHUB_DIR" || handle_error "Failed to change directory to $GITHUB_DIR"

    # Define the six repositories to clone
    local repos=("bash" "windows" "web" "python" "go" "misc")
    for repo in "${repos[@]}"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        local repo_url="https://github.com/dunamismax/${repo}.git"
        rm -rf "$repo_dir" 2>/dev/null
        git clone "$repo_url" "$repo_dir" || handle_error "Failed to clone repository: $repo"
        log INFO "Cloned repository: $repo"
    done

    # Set ownership for each repository; warn (not exit) if this fails.
    for repo in "bash" "windows" "web" "python" "go" "misc"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || warn "Failed to set ownership for repository: $repo"
        else
            warn "Repository directory not found: $repo_dir"
        fi
    done

    # Make all .sh files executable.
    find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} + || handle_error "Failed to set executable permissions for .sh files."

    # Secure .git directories.
    local DIR_PERMISSIONS="700"
    local FILE_PERMISSIONS="600"
    while IFS= read -r -d '' git_dir; do
        chmod "$DIR_PERMISSIONS" "$git_dir" || handle_error "Failed to set permissions for $git_dir"
        find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} + || handle_error "Failed to set directory permissions for $git_dir"
        find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} + || handle_error "Failed to set file permissions for $git_dir"
    done < <(find "$GITHUB_DIR" -type d -name ".git" -print0)

    # Load dotfiles from the bash repository.
    local dotfiles_dir="${USER_HOME}/github/bash/linux/dotfiles"
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    local config_dir="${USER_HOME}/.config"
    local local_bin_dir="${USER_HOME}/.local/bin"
    mkdir -p "$config_dir" "$local_bin_dir" || handle_error "Failed to create config directories."

    for file in .bashrc .profile .fehbg; do
        cp "${dotfiles_dir}/${file}" "${USER_HOME}/${file}" || warn "Failed to copy ${file}."
    done

    # Copy Caddyfile if it exists in the dotfiles.
    if [[ -f "${dotfiles_dir}/Caddyfile" ]]; then
        cp "${dotfiles_dir}/Caddyfile" /etc/caddy/Caddyfile || handle_error "Failed to copy Caddyfile."
        chown caddy:caddy /etc/caddy/Caddyfile || handle_error "Failed to set ownership for Caddyfile."
    else
        warn "Caddyfile not found in ${dotfiles_dir}"
    fi

    # Attempt to set ownership for the entire home directory;
    # warn if it fails instead of exiting.
    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME" || warn "Failed to set ownership for $USER_HOME."
    chmod -R u=rwX,g=rX,o=rX "$local_bin_dir" || handle_error "Failed to set permissions for $local_bin_dir."

    log INFO "Repositories and dotfiles setup completed successfully."

    # --- Additional Functionality: Copy _scripts .sh files to /home/sawyer/bin ---
    local scripts_src="/home/${USERNAME}/github/linux/_scripts"
    local scripts_dest="/home/${USERNAME}/bin"
    if [[ -d "$scripts_src" ]]; then
        mkdir -p "$scripts_dest" || warn "Failed to create destination directory: $scripts_dest"
        cp "$scripts_src"/*.sh "$scripts_dest"/ || warn "Failed to copy .sh files from $scripts_src to $scripts_dest"
        chmod +x "$scripts_dest"/*.sh || warn "Failed to set executable permissions on .sh files in $scripts_dest"
        log INFO "Copied and set executable permissions for .sh scripts from $scripts_src to $scripts_dest"
    else
        warn "Scripts source directory not found: $scripts_src"
    fi
    # --- End of additional functionality ---

    cd ~ || handle_error "Failed to return to home directory."
}

enable_dunamismax_services() {
    log INFO "Enabling DunamisMax website services..."

    cat <<EOF >/etc/systemd/system/dunamismax-ai-agents.service
[Unit]
Description=DunamisMax AI Agents Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/ai_agents
Environment="PATH=/home/${USERNAME}/github/web/ai_agents/.venv/bin"
EnvironmentFile=/home/${USERNAME}/github/web/ai_agents/.env
ExecStart=/home/${USERNAME}/github/web/ai_agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat <<EOF >/etc/systemd/system/dunamismax-files.service
[Unit]
Description=DunamisMax File Converter Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/converter_service
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/${USERNAME}/github/web/converter_service/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8300
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat <<EOF >/etc/systemd/system/dunamismax-messenger.service
[Unit]
Description=DunamisMax Messenger
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/messenger
Environment="PATH=/home/${USERNAME}/github/web/messenger/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/messenger/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat <<EOF >/etc/systemd/system/dunamismax-notes.service
[Unit]
Description=DunamisMax Notes Page
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/notes
Environment="PATH=/home/${USERNAME}/github/web/notes/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/notes/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8500
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat <<EOF >/etc/systemd/system/dunamismax.service
[Unit]
Description=DunamisMax Main Website
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/dunamismax
Environment="PATH=/home/${USERNAME}/github/web/dunamismax/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/dunamismax/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable dunamismax-ai-agents.service
    systemctl enable dunamismax-files.service
    systemctl enable dunamismax-messenger.service
    systemctl enable dunamismax-notes.service
    systemctl enable dunamismax.service
    log INFO "DunamisMax services enabled."
}

# ==============================================================================
# 5. ADDITIONAL SECURITY & AUTOMATION FUNCTIONS
# ==============================================================================
# Set up automatic updates using a systemd timer
configure_automatic_updates() {
    log INFO "Configuring automatic system updates via systemd timer..."
    cat <<EOF >/etc/systemd/system/opensuse-auto-update.service
[Unit]
Description=OpenSUSE Automatic Update Service

[Service]
Type=oneshot
ExecStart=/usr/bin/zypper --non-interactive refresh && /usr/bin/zypper --non-interactive update
EOF

    cat <<EOF >/etc/systemd/system/opensuse-auto-update.timer
[Unit]
Description=Daily OpenSUSE Automatic Update Timer

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable --now opensuse-auto-update.timer || warn "Could not enable automatic update timer."
    log INFO "Automatic updates configured via systemd timer."
}

system_hardening() {
    log INFO "Applying additional system hardening..."
    cat <<EOF >/etc/sysctl.d/99-harden.conf
# Disable packet forwarding by default
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Disable ICMP redirects and source routing
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Enable TCP SYN cookies to protect against SYN flood attacks
net.ipv4.tcp_syncookies = 1

# Enable reverse path filtering
net.ipv4.conf.all.rp_filter = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1
EOF
    sysctl --system || warn "Failed to reload sysctl settings."
    log INFO "System hardening applied."
}

# ==============================================================================
# 6. DOCKER INSTALLATION & CONFIGURATION
# ==============================================================================
install_docker() {
    log INFO "Installing Docker..."
    if command -v docker &>/dev/null; then
        log INFO "Docker is already installed."
    else
        zypper --non-interactive install docker || handle_error "Failed to install Docker."
        log INFO "Docker installed successfully."
    fi
    usermod -aG docker "$USERNAME" || warn "Failed to add $USERNAME to the docker group."
    mkdir -p /etc/docker
    cat <<EOF >/etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
    systemctl enable docker || warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log INFO "Docker configuration completed."
}

install_docker_compose() {
    log INFO "Installing Docker Compose..."
    if ! command -v docker-compose &>/dev/null; then
        local version="2.20.2"
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log INFO "Docker Compose installed successfully."
    else
        log INFO "Docker Compose is already installed."
    fi
}

# ==============================================================================
# 7. FINALIZATION & CLEANUP
# ==============================================================================
cleanup_system() {
    log INFO "Cleaning up package caches..."
    zypper clean --all || warn "Failed to clean package cache."
    log INFO "System cleanup completed."
}

finalize_configuration() {
    log INFO "Finalizing system configuration and cleanup..."
    cleanup_system
    cd "/home/${USERNAME}" || handle_error "Failed to change to user home directory."
    log INFO "Collecting system information..."
    log INFO "Uptime: $(uptime -p)"
    log INFO "Disk Usage (root): $(df -h / | tail -1)"
    log INFO "Memory Usage: $(free -h | grep Mem)"
    local cpu_model
    cpu_model=$(grep 'model name' /proc/cpuinfo | head -1 | awk -F': ' '{print $2}')
    log INFO "CPU Model: ${cpu_model:-Unknown}"
    log INFO "Kernel Version: $(uname -r)"
    log INFO "Network Configuration:"
    ip addr show | sed "s/^/    /"
    log INFO "Final system configuration completed."
}

prompt_reboot() {
    log INFO "Setup complete. A system reboot is recommended to apply all changes."
    read -rp "Reboot now? (y/n): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot skipped. Please reboot manually when convenient."
    fi
}

# ==============================================================================
# 8. MAIN EXECUTION FLOW
# ==============================================================================
main() {
    # Ensure log directory exists
    local log_dir
    log_dir=$(dirname "$LOG_FILE")
    mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE"

    log INFO "======================================"
    log INFO "Starting OpenSUSE Automated Setup Script"
    log INFO "======================================"

    if [[ $(id -u) -ne 0 ]]; then
        handle_error "This script must be run as root. Please use sudo."
    fi

    check_network
    update_system
    ensure_user
    configure_ssh
    install_packages
    configure_firewalld
    configure_journald
    release_ports
    configure_fail2ban
    install_build_dependencies
    install_caddy
    install_plex
    setup_repos_and_dotfiles
    enable_dunamismax_services
    configure_automatic_updates
    system_hardening
    install_docker
    install_docker_compose

    finalize_configuration
    log INFO "OpenSUSE system setup completed successfully."
    prompt_reboot
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
