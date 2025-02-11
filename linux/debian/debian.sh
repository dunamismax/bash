#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: debian_setup.sh
# Description: Automated Debian setup and hardening script with robust error
#              handling and improved logging. This script configures system
#              updates, user setup, firewall rules, SSH hardening, package
#              installation, and additional services.
# Author: Your Name | License: MIT
# Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./debian_setup.sh
#
# Notes:
#   - This script must be run as root.
#   - Log output is saved to /var/log/debian_setup.log.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/debian_setup.log"
USERNAME="sawyer"

# List of essential packages to be installed.
PACKAGES=(
    bash
    vim
    nano
    mc
    screen
    tmux
    nodejs
    npm
    ninja-build
    meson
    fonts-font-awesome
    intltool
    gettext
    build-essential
    cmake
    hugo
    pigz
    exim4
    openssh-server
    libtool
    pkg-config
    libssl-dev
    rfkill
    fonts-ubuntu
    bzip2
    libbz2-dev
    libffi-dev
    zlib1g-dev
    libreadline-dev
    libsqlite3-dev
    tk-dev
    iw
    fonts-hack
    libpolkit-agent-1-dev
    xz-utils
    libncurses5-dev
    python3
    python3-dev
    python3-pip
    python3-venv
    libfreetype6-dev
    flatpak
    xfce4-dev-tools
    git
    ufw
    perl
    curl
    wget
    tcpdump
    rsync
    htop
    passwd
    bash-completion
    neofetch
    tig
    jq
    fonts-dejavu-core
    fonts-firacode
    nmap
    tree
    fzf
    lynx
    which
    patch
    smartmontools
    ntfs-3g
    ubuntu-restricted-extras
    cups
    neovim
    libglib2.0-dev
    qemu-kvm
    libvirt-daemon-system
    libvirt-clients
    virtinst
    bridge-utils
    acpid
    policykit-1
    papirus-icon-theme
    chrony
    fail2ban
    ffmpeg
    restic
    fonts-dejavu
    flameshot
    libxfce4ui-2-dev
    libxfce4util-dev
    libgtk-3-dev
    libpolkit-gobject-1-dev
    gnome-keyring
    seahorse
    thunar
    dmenu
    i3
    i3status
    feh
    alacritty
    picom
    zsh
    fish
    emacs
    gcc
    make
    sudo
    logrotate
    dnsutils
    mtr
    netcat-openbsd
    socat
    vnstat
    lsof
    gdisk
    ncdu
    unzip
    zip
    gawk
    expect
    fd-find
    bat
    ripgrep
    hyperfine
    mpv
    nnn
    newsboat
    irssi
    taskwarrior
    cowsay
    figlet
    aircrack-ng
    reaver
    hydra
    john
    sqlmap
    gobuster
    dirb
    wfuzz
    netdiscover
    arp-scan
    ettercap-text-only
    tshark
    hashcat
    recon-ng
    crunch
    iotop
    iftop
    sysstat
    traceroute
    whois
    strace
    ltrace
    iperf3
    binwalk
    foremost
    steghide
    hashid
    g++
    clang
    ca-certificates
    software-properties-common
    apt-transport-https
    gnupg
    lsb-release
    libncursesw5-dev
    libgdbm-dev
    libnss3-dev
    liblzma-dev
    libxml2-dev
    libxmlsec1-dev
    gdb
    llvm
)

# ------------------------------------------------------------------------------
# COLOR CONSTANTS (Nord theme; 24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background color
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'
NORD8='\033[38;2;136;192;208m'
NORD9='\033[38;2;129;161;193m'   # Bluish for DEBUG messages
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Reddish for ERROR messages
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'  # Yellowish for WARN messages
NORD14='\033[38;2;163;190;140m'  # Greenish for INFO messages
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTIONS
# ------------------------------------------------------------------------------
# log <LEVEL> <message>
# Logs the provided message with a timestamp and level both to the log file
# and (if outputting to a terminal) to stderr with a themed color.
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [${level^^}] $message"

    # Append the log entry to the log file.
    echo "$log_entry" >> "$LOG_FILE"

    # If stderr is a terminal, add color.
    if [ -t 2 ]; then
        case "${level^^}" in
            INFO)  printf "%b%s%b\n" "$NORD14" "$log_entry" "$NC" ;;
            WARN)  printf "%b%s%b\n" "$NORD13" "$log_entry" "$NC" ;;
            ERROR) printf "%b%s%b\n" "$NORD11" "$log_entry" "$NC" ;;
            DEBUG) printf "%b%s%b\n" "$NORD9"  "$log_entry" "$NC" ;;
            *)     printf "%s\n" "$log_entry" ;;
        esac
    else
        echo "$log_entry" >&2
    fi
}

log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

# handle_error <error_message> [exit_code]
# Logs an error message and terminates the script with the provided exit code.
handle_error() {
    local error_message="${1:-"An unknown error occurred."}"
    local exit_code="${2:-1}"
    log_error "$error_message (Exit Code: $exit_code)"
    log_error "Error encountered at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# cleanup
# This function is executed upon script exit to perform any necessary cleanup.
cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Insert any necessary cleanup commands here.
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------------------------

# print_section <title>
# Logs a formatted section header.
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

# check_root
# Exits with an error if the script is not executed as root.
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

# check_network
# Tests network connectivity by pinging a well-known host.
check_network() {
    print_section "Network Connectivity Check"
    log_info "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        handle_error "No network connectivity. Please verify your network settings."
    fi
    log_info "Network connectivity verified."
}

# update_system
# Updates package repository information and upgrades installed packages.
update_system() {
    print_section "System Update & Upgrade"
    log_info "Updating package repositories..."
    if ! apt-get update -qq; then
        handle_error "Failed to update package repositories."
    fi

    log_info "Upgrading system packages..."
    if ! apt-get upgrade -y; then
        handle_error "Failed to upgrade packages."
    fi

    log_info "System update and upgrade complete."
}

# ensure_user
# Creates the specified user and a corresponding group if they do not already exist.
ensure_user() {
    print_section "User Setup"

    if id -u "$USERNAME" >/dev/null 2>&1; then
        log_info "User '$USERNAME' already exists."
    else
        # Check if the group exists; if not, create it.
        if ! getent group "$USERNAME" >/dev/null 2>&1; then
            log_info "Creating group '$USERNAME'..."
            if ! groupadd "$USERNAME"; then
                handle_error "Failed to create group '$USERNAME'."
            fi
        else
            log_info "Group '$USERNAME' already exists."
        fi

        log_info "Creating user '$USERNAME' with primary group '$USERNAME'..."
        if ! useradd -m -s /bin/bash -g "$USERNAME" "$USERNAME"; then
            handle_error "Failed to create user '$USERNAME'."
        fi

        # Lock the password to prevent direct login.
        if ! passwd -l "$USERNAME" >/dev/null 2>&1; then
            log_warn "Failed to lock password for user '$USERNAME'."
        fi

        log_info "User '$USERNAME' created successfully."
    fi
}

# configure_sudoers
# Ensures that the specified user has sudo privileges by creating a dedicated
# sudoers file in /etc/sudoers.d/.
configure_sudoers() {
    print_section "Sudoers Configuration"
    local SUDOERS_ENTRY_FILE="/etc/sudoers.d/${USERNAME}"

    if [ -f "$SUDOERS_ENTRY_FILE" ]; then
        log_info "Sudoers entry for '$USERNAME' already exists in $SUDOERS_ENTRY_FILE."
    else
        log_info "Creating sudoers entry for '$USERNAME' in $SUDOERS_ENTRY_FILE..."
        echo "${USERNAME} ALL=(ALL) ALL" > "$SUDOERS_ENTRY_FILE" || handle_error "Failed to create sudoers entry file for '$USERNAME'."

        # Set strict permissions to secure the sudoers file.
        chmod 0440 "$SUDOERS_ENTRY_FILE" || log_warn "Failed to set permissions on $SUDOERS_ENTRY_FILE."

        # Validate the syntax of the newly created sudoers file.
        if visudo -cf "$SUDOERS_ENTRY_FILE"; then
            log_info "Sudoers entry for '$USERNAME' created and validated successfully."
        else
            log_error "Syntax error detected in $SUDOERS_ENTRY_FILE. Please review the file."
            handle_error "Sudoers configuration failed due to syntax errors."
        fi
    fi

    log_info "Sudoers configuration complete."
}

# install_packages
# Installs a list of essential system packages.
install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    if ! apt-get install -y "${PACKAGES[@]}"; then
        handle_error "Failed to install one or more packages."
    fi
    log_info "Package installation complete."
}

# configure_ssh
# Hardens the SSH server by disabling root login and password authentication.
configure_ssh() {
    print_section "SSH Configuration"
    log_info "Configuring OpenSSH Server..."

    # Ensure OpenSSH Server is installed.
    if ! dpkg -l | grep -qw openssh-server; then
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log_info "OpenSSH Server installed."
    else
        log_info "OpenSSH Server already installed."
    fi

    # Enable and start SSH service.
    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."

    # Backup the sshd_config file with a timestamp.
    local sshd_config="/etc/ssh/sshd_config"
    local backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup sshd_config."
    log_info "Backed up sshd_config to $backup."

    # Define SSH settings with best practices.
    # Note: PasswordAuthentication is set to "yes" to allow password login.
    # ClientAliveInterval is set to "0" to disable timeout (keeping sessions alive indefinitely).
    declare -A ssh_settings=(
        ["Port"]="22"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="yes"
        ["Protocol"]="2"
        ["MaxAuthTries"]="4"
        ["ClientAliveInterval"]="0"
    )

    for key in "${!ssh_settings[@]}"; do
        if grep -q "^${key}[[:space:]]" "$sshd_config"; then
            sed -i "s/^${key}[[:space:]].*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done

    # Optional: Remove any ClientAliveCountMax setting so that no idle timeout is enforced.
    sed -i '/^ClientAliveCountMax/d' "$sshd_config"

    # Restart SSH service to apply changes.
    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log_info "SSH configuration updated successfully."
}

# configure_firewall
# Configures the Uncomplicated Firewall (ufw) with default rules and enables it.
configure_firewall() {
    print_section "Firewall Configuration"
    log_info "Configuring firewall with ufw..."
    local ufw_cmd="/usr/sbin/ufw"
    if [ ! -x "$ufw_cmd" ]; then
        handle_error "ufw command not found at $ufw_cmd. Please install ufw."
    fi

    "$ufw_cmd" default deny incoming || log_warn "Failed to set default deny incoming"
    "$ufw_cmd" default allow outgoing || log_warn "Failed to set default allow outgoing"
    "$ufw_cmd" allow 22/tcp || log_warn "Failed to allow SSH"
    "$ufw_cmd" allow 80/tcp || log_warn "Failed to allow HTTP"
    "$ufw_cmd" allow 443/tcp || log_warn "Failed to allow HTTPS"
    "$ufw_cmd" allow 32400/tcp || log_warn "Failed to allow Plex Media Server port"
    "$ufw_cmd" --force enable || handle_error "Failed to enable ufw firewall"
    systemctl enable ufw || log_warn "Failed to enable ufw service"
    systemctl start ufw || log_warn "Failed to start ufw service"
    log_info "Firewall configured and enabled."
}

# configure_fail2ban
# Enables and starts the fail2ban service for intrusion prevention.
configure_fail2ban() {
    print_section "fail2ban Configuration"
    log_info "Enabling fail2ban service..."
    if ! systemctl enable fail2ban; then
        log_warn "Failed to enable fail2ban service."
    fi
    if ! systemctl start fail2ban; then
        log_warn "Failed to start fail2ban service."
    else
        log_info "fail2ban service started successfully."
    fi
}

# install_plex
# Downloads and installs the Plex Media Server package, then configures it to
# run under the specified user account.
install_plex() {
    print_section "Plex Media Server Installation"
    log_info "Ensuring required system utilities are available..."
    export PATH="$PATH:/sbin:/usr/sbin"
    if ! command -v ldconfig >/dev/null; then
        handle_error "ldconfig command not found. Please install libc-bin or fix your PATH."
    fi
    if ! command -v start-stop-daemon >/dev/null; then
        handle_error "start-stop-daemon command not found. Please install dpkg or fix your PATH."
    fi
    log_info "Downloading Plex Media Server deb file..."
    local plex_deb="/tmp/plexmediaserver.deb"
    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    if ! wget -q -O "$plex_deb" "$plex_url"; then
        handle_error "Failed to download Plex Media Server deb file."
    fi
    log_info "Installing Plex Media Server from deb file..."
    if ! dpkg -i "$plex_deb"; then
        log_warn "dpkg installation encountered errors, attempting to fix dependencies..."
        if ! apt-get install -f -y; then
            handle_error "Failed to install Plex Media Server due to unresolved dependencies."
        fi
    fi
    local PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" \
            || log_warn "Failed to set Plex user in $PLEX_CONF"
    else
        echo "PLEX_MEDIA_SERVER_USER=${USERNAME}" > "$PLEX_CONF" \
            || log_warn "Failed to create $PLEX_CONF"
    fi
    if ! systemctl enable plexmediaserver; then
        log_warn "Failed to enable Plex Media Server service."
    fi
    if ! systemctl start plexmediaserver; then
        log_warn "Plex Media Server failed to start."
    else
        log_info "Plex Media Server installed and started."
    fi
}

# caddy_config
# Downloads and installs Caddy and enables service
caddy_config() {
    print_section "Caddy Configuration"

    # ---------------------------------------------------------------------------
    # Step 1: Release occupied network ports.
    # ---------------------------------------------------------------------------
    log_info "Starting port release process for Caddy installation..."
    release_ports

    # ---------------------------------------------------------------------------
    # Step 2: Install required dependencies and add the Caddy repository.
    # ---------------------------------------------------------------------------
    log_info "Installing dependencies for Caddy..."
    apt install -y debian-keyring debian-archive-keyring apt-transport-https curl || \
        handle_error "Failed to install dependencies for Caddy."

    log_info "Adding Caddy GPG key..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg || \
        handle_error "Failed to add Caddy GPG key."

    log_info "Adding Caddy repository..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
        tee /etc/apt/sources.list.d/caddy-stable.list || \
        handle_error "Failed to add Caddy repository."

    # ---------------------------------------------------------------------------
    # Step 3: Update package lists and install Caddy.
    # ---------------------------------------------------------------------------
    log_info "Updating package lists..."
    apt update || handle_error "Failed to update package lists."

    log_info "Installing Caddy..."
    apt install -y caddy || handle_error "Failed to install Caddy."

    log_info "Caddy installed successfully."

    # ---------------------------------------------------------------------------
    # Step 4: Copy custom Caddyfile.
    # ---------------------------------------------------------------------------
    local CUSTOM_CADDYFILE="/home/sawyer/github/linux/dotfiles/Caddyfile"
    local DEST_CADDYFILE="/etc/caddy/Caddyfile"
    if [ -f "$CUSTOM_CADDYFILE" ]; then
        log_info "Copying custom Caddyfile from $CUSTOM_CADDYFILE to $DEST_CADDYFILE..."
        cp -f "$CUSTOM_CADDYFILE" "$DEST_CADDYFILE" || log_warn "Failed to copy custom Caddyfile."
    else
        log_warn "Custom Caddyfile not found at $CUSTOM_CADDYFILE"
    fi

    # ---------------------------------------------------------------------------
    # Step 5: Enable and start (restart) the Caddy service.
    # ---------------------------------------------------------------------------
    log_info "Enabling Caddy service..."
    systemctl enable caddy || log_warn "Failed to enable Caddy service."

    log_info "Restarting Caddy service to apply new configuration..."
    systemctl restart caddy || log_warn "Failed to restart Caddy service."

    log_info "Caddy configuration completed successfully."
}

# configure_zfs
# Imports a ZFS pool (if not already imported) and sets its mountpoint.
configure_zfs() {
    print_section "ZFS Configuration"
    local ZPOOL_NAME="WD_BLACK"
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log_info "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    fi

    if ! zfs set mountpoint=/media/"$ZPOOL_NAME" "$ZPOOL_NAME"; then
        log_warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log_info "ZFS pool '$ZPOOL_NAME' mountpoint set to /media/$ZPOOL_NAME."
    fi
}

# setup_repos
# Clones several GitHub repositories into a dedicated directory in the user's
# home folder.
setup_repos() {
    print_section "GitHub Repositories Setup"
    log_info "Setting up GitHub repositories for user '$USERNAME'..."
    local GH_DIR="/home/$USERNAME/github"
    if ! mkdir -p "$GH_DIR"; then
        handle_error "Failed to create GitHub directory at $GH_DIR."
    fi

    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"
        if [ -d "$REPO_DIR" ]; then
            log_info "Removing existing directory for repository '$repo'."
            rm -rf "$REPO_DIR"
        fi
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            log_warn "Failed to clone repository '$repo'."
        else
            chown -R "$USERNAME:$USERNAME" "$REPO_DIR"
            log_info "Repository '$repo' cloned successfully."
        fi
    done
}

# enable_dunamismax_services
# Creates and enables and starts the systemsd service files for FastAPI website
enable_dunamismax_services() {
    print_section "DunamisMax Services Setup"
    log_info "Enabling DunamisMax website services..."

    # DunamisMax AI Agents Service
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

    # DunamisMax File Converter Service
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

    # DunamisMax Messenger Service
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

    # DunamisMax Notes Service
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

    # DunamisMax Main Website Service
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

    # Reload systemd configuration and enable the services
    systemctl daemon-reload
    systemctl enable dunamismax-ai-agents.service
    systemctl enable dunamismax-files.service
    systemctl enable dunamismax-messenger.service
    systemctl enable dunamismax-notes.service
    systemctl enable dunamismax.service

    log_info "DunamisMax services enabled."
}

# docker_config
# Installs and enables Docker and Docker Compose
docker_config() {
    print_section "Docker Configuration"
    log_info "Starting Docker installation and configuration..."

    # -------------------------------
    # Install Docker (using apt-get)
    # -------------------------------
    if command -v docker &>/dev/null; then
        log_info "Docker is already installed."
    else
        log_info "Docker is not installed. Installing Docker..."
        apt-get update || handle_error "Failed to update package lists."
        apt-get install -y docker.io || handle_error "Failed to install Docker."
        log_info "Docker installed successfully."
    fi

    # Add the user to the docker group
    usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to the docker group."

    # Create or update Docker daemon configuration
    mkdir -p /etc/docker || handle_error "Failed to create /etc/docker directory."
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

    # Enable and restart the Docker service
    systemctl enable docker || log_warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log_info "Docker configuration completed."

    # -------------------------------
    # Install Docker Compose
    # -------------------------------
    log_info "Starting Docker Compose installation..."
    if ! command -v docker-compose &>/dev/null; then
        local version="2.20.2"
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log_info "Docker Compose installed successfully."
    else
        log_info "Docker Compose is already installed."
    fi
}

# copy_shell_configs
# Copies .bashrc and .profile into place from Git repo
copy_shell_configs() {
    print_section "Shell Configuration Files Update"

    local source_dir="/home/$USERNAME/github/linux/dotfiles"
    local dest_dir="/home/$USERNAME"
    local files=(".bashrc" ".profile")

    for file in "${files[@]}"; do
        local src="${source_dir}/${file}"
        local dest="${dest_dir}/${file}"
        if [ -f "$src" ]; then
            log_info "Copying ${src} to ${dest}..."
            cp -f "$src" "$dest" || log_warn "Failed to copy ${src} to ${dest}."
            chown "$USERNAME":"$USERNAME" "$dest" || log_warn "Failed to set ownership for ${dest}."
        else
            log_warn "Source file ${src} not found; skipping."
        fi
    done

    log_info "Shell configuration files update completed."
}

# configure_periodic
# Sets up a daily cron job for system maintenance including update, upgrade,
# autoremove, and autoclean.
configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log_info "Configuring daily system maintenance tasks..."

    local CRON_FILE="/etc/cron.daily/debian_maintenance"

    # Backup any existing cron file.
    if [ -f "$CRON_FILE" ]; then
        mv "$CRON_FILE" "${CRON_FILE}.bak.$(date +%Y%m%d%H%M%S)" \
            && log_info "Existing cron file backed up." \
            || log_warn "Failed to backup existing cron file at $CRON_FILE."
    fi

    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Debian maintenance script (added by debian_setup script)
apt-get update -qq && apt-get upgrade -y && apt-get autoremove -y && apt-get autoclean -y
EOF

    if chmod +x "$CRON_FILE"; then
        log_info "Daily maintenance script created and permissions set at $CRON_FILE."
    else
        log_warn "Failed to set execute permission on $CRON_FILE."
    fi
}

# final_checks
# Logs detailed final system information for confirmation.
final_checks() {
    print_section "Final System Checks"
    log_info "Kernel version: $(uname -r)"
    log_info "System uptime: $(uptime -p)"
    log_info "Disk usage (root partition): $(df -h / | awk 'NR==2 {print $0}')"

    # Detailed memory usage: total, used, and available.
    local mem_total mem_used mem_free
    read -r mem_total mem_used mem_free < <(free -h | awk '/^Mem:/{print $2, $3, $4}')
    log_info "Memory usage: Total: ${mem_total}, Used: ${mem_used}, Free: ${mem_free}"

    # Log CPU model info.
    local cpu_model
    cpu_model=$(lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//')
    log_info "CPU: ${cpu_model}"

    # Log a summary of active network interfaces.
    log_info "Active network interfaces:"
    ip -brief address | while read -r iface; do
         log_info "  $iface"
    done

    # Log system load averages.
    local load_avg
    load_avg=$(awk '{print $1", "$2", "$3}' /proc/loadavg)
    log_info "Load averages (1, 5, 15 min): ${load_avg}"
}

# prompt_reboot
# Prompts the user to reboot the system now or later.
prompt_reboot() {
    print_section "Reboot Prompt"
    log_info "Setup complete."
    read -rp "Would you like to reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_info "Rebooting system now..."
        shutdown -r now
    else
        log_info "Reboot canceled. Please remember to reboot later for all changes to take effect."
    fi
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is being executed with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    # Ensure that the log directory exists and has the proper permissions.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log_info "Debian setup script execution started."

    check_root
    check_network
    update_system
    ensure_user
    configure_sudoers
    install_packages
    configure_ssh
    configure_firewall
    configure_fail2ban
    install_plex
    configure_zfs
    setup_repos
    caddy_config
    copy_shell_configs
    enable_dunamismax_services
    docker_config
    configure_periodic
    final_checks
    prompt_reboot
}

main "$@"