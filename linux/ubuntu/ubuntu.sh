#!/usr/bin/env bash
#
# ubuntu_setup.sh - Automated Ubuntu Setup and Hardening Script
#
# This script automates the initial configuration and hardening of an Ubuntu system.
# It performs system updates, installs essential packages, sets up users, configures
# the firewall and SSH, and deploys various additional services to streamline deployment.
#
# Usage: sudo ./ubuntu_setup.sh
#
# Note:
#   - Must be run as root.
#   - Log output is saved to /var/log/ubuntu_setup.log.
#
# Author: dunamismax | License: MIT | Version: 2.1
#

set -Eeuo pipefail

LOG_FILE="/var/log/ubuntu_setup.log"
USERNAME="sawyer"

# List of essential packages to be installed on Ubuntu.
PACKAGES=(
    bash
    vim
    nano
    mc
    screen
    tmux
    ninja-build
    meson
    intltool
    gettext
    build-essential
    cmake
    pigz
    openssh-server
    libtool
    pkg-config
    libssl-dev
    rfkill
    bzip2
    libbz2-dev
    libffi-dev
    zlib1g-dev
    libreadline-dev
    libsqlite3-dev
    tk-dev
    iw
    libpolkit-agent-1-dev
    xz-utils
    libncurses5-dev
    python3
    python3-dev
    python3-pip
    python3-venv
    libfreetype6-dev
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
    nmap
    tree
    fzf
    lynx
    which
    patch
    smartmontools
    ntfs-3g
    cups
    neovim
    libglib2.0-dev
    qemu-kvm
    libvirt-daemon-system
    libvirt-clients
    virtinst
    bridge-utils
    acpid
    fail2ban
    ffmpeg
    restic
    flameshot
    libgtk-3-dev
    libpolkit-gobject-1-dev
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
    libxcb-xkb-dev
    libpam0g-dev
)

# Nord Theme Colors (24-bit ANSI)
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                     # Reset to No Color

# Logging Functions
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local entry="[$timestamp] [${level^^}] $message"

    # Append log entry to file
    echo "$entry" >> "$LOG_FILE"

    # If stderr is a terminal, print with color; otherwise, print plain.
    if [ -t 2 ]; then
        case "${level^^}" in
            INFO)  printf "%b%s%b\n" "$NORD14" "$entry" "$NC" ;;
            WARN)  printf "%b%s%b\n" "$NORD13" "$entry" "$NC" ;;
            ERROR) printf "%b%s%b\n" "$NORD11" "$entry" "$NC" ;;
            DEBUG) printf "%b%s%b\n" "$NORD9"  "$entry" "$NC" ;;
            *)     printf "%s\n" "$entry" ;;
        esac
    else
        echo "$entry" >&2
    fi
}

log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

handle_error() {
    local msg="${1:-An unknown error occurred.}"
    local code="${2:-1}"
    log_error "$msg (Exit Code: $code)"
    log_error "Error encountered at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $msg (Exit Code: $code)${NC}" >&2
    exit "$code"
}

cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Add any cleanup commands here.
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# Utility Functions

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

check_network() {
    print_section "Network Connectivity Check"
    log_info "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        handle_error "No network connectivity. Please verify your network settings."
    fi
    log_info "Network connectivity verified."
}

update_system() {
    print_section "System Update & Upgrade"
    log_info "Updating package repositories..."
    if ! apt update -qq; then
        handle_error "Failed to update package repositories."
    fi

    log_info "Upgrading system packages..."
    if ! apt upgrade -y; then
        handle_error "Failed to upgrade packages."
    fi

    log_info "System update and upgrade complete."
}

ensure_user() {
    print_section "User Setup"

    if id -u "$USERNAME" >/dev/null 2>&1; then
        log_info "User '$USERNAME' already exists."
    else
        log_info "Creating user '$USERNAME'..."
        # Create the user non-interactively:
        #   --disabled-password prevents password login,
        #   --gecos "" provides empty GECOS fields,
        #   --shell /bin/bash sets the default shell.
        if ! adduser --disabled-password --gecos "" --shell /bin/bash "$USERNAME"; then
            handle_error "Failed to create user '$USERNAME'."
        fi

        # Explicitly lock the password to be extra sure no password login is possible.
        if ! passwd -l "$USERNAME" >/dev/null 2>&1; then
            log_warn "Failed to lock password for user '$USERNAME'."
        fi

        log_info "User '$USERNAME' created successfully."
    fi
}

configure_sudoers() {
    print_section "Sudoers Configuration"
    local SUDOERS_ENTRY_FILE="/etc/sudoers.d/${USERNAME}"

    # Ensure 'sudo' (and thus 'visudo') is available. On Ubuntu sudo is normally pre-installed.
    if ! command -v visudo &>/dev/null; then
        log_info "visudo not found. Installing the 'sudo' package..."
        apt install -y sudo || handle_error "Failed to install the 'sudo' package."
        log_info "'sudo' installed successfully."
    fi

    # Check if the sudoers file for the user already exists.
    if [ -f "$SUDOERS_ENTRY_FILE" ]; then
        log_info "Sudoers entry for '$USERNAME' already exists in $SUDOERS_ENTRY_FILE."
    else
        log_info "Creating sudoers entry for '$USERNAME' in $SUDOERS_ENTRY_FILE..."
        {
            echo "${USERNAME} ALL=(ALL:ALL) ALL"
        } > "$SUDOERS_ENTRY_FILE" || handle_error "Failed to create sudoers entry file for '$USERNAME'."

        # Set strict permissions to secure the sudoers file.
        chmod 0440 "$SUDOERS_ENTRY_FILE" || log_warn "Failed to set permissions on $SUDOERS_ENTRY_FILE."

        # Validate the syntax of the new sudoers file.
        if visudo -cf "$SUDOERS_ENTRY_FILE"; then
            log_info "Sudoers entry for '$USERNAME' created and validated successfully."
        else
            log_error "Syntax error detected in $SUDOERS_ENTRY_FILE. Please review the file."
            handle_error "Sudoers configuration failed due to syntax errors."
        fi
    fi

    log_info "Sudoers configuration complete."
}

install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    if ! apt install -y "${PACKAGES[@]}"; then
        handle_error "Failed to install one or more packages."
    fi
    log_info "Package installation complete."
}

configure_ssh() {
    print_section "SSH Configuration"
    log_info "Configuring OpenSSH Server..."

    # Ensure OpenSSH Server is installed.
    if ! dpkg -s openssh-server &>/dev/null; then
        log_info "openssh-server is not installed. Updating repository and installing..."
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log_info "OpenSSH Server installed successfully."
    else
        log_info "OpenSSH Server already installed."
    fi

    # Enable and start the SSH service.
    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."

    # Backup the existing sshd_config file.
    local sshd_config="/etc/ssh/sshd_config"
    if [ ! -f "$sshd_config" ]; then
        handle_error "SSHD configuration file not found: $sshd_config"
    fi
    local backup
    backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup $sshd_config"
    log_info "Backed up $sshd_config to $backup"

    # Define desired SSH settings for a hardened configuration.
    # Here we disable root login, disable password authentication (use keys only),
    # disallow empty passwords and challenge-response logins, and enforce protocol 2.
    declare -A ssh_settings=(
        ["Port"]="22"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="yes"
        ["PermitEmptyPasswords"]="no"
        ["ChallengeResponseAuthentication"]="no"
        ["Protocol"]="2"
        ["MaxAuthTries"]="5"
        ["ClientAliveInterval"]="600"
        ["ClientAliveCountMax"]="48"
    )

    # Update or add each setting in the sshd_config file.
    for key in "${!ssh_settings[@]}"; do
        if grep -qE "^${key}[[:space:]]" "$sshd_config"; then
            sed -i "s/^${key}[[:space:]].*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done

    # Restart the SSH service to apply the new configuration.
    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log_info "SSH configuration updated successfully."
}

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

install_plex() {
    print_section "Plex Media Server Installation"
    log_info "Installing Plex Media Server from downloaded .deb file..."

    # Ensure curl is available.
    if ! command -v curl >/dev/null; then
        handle_error "curl is required but not installed. Please install curl."
    fi

    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    local temp_deb="/tmp/plexmediaserver.deb"

    log_info "Downloading Plex Media Server package from ${plex_url}..."
    if ! curl -L -o "$temp_deb" "$plex_url"; then
        handle_error "Failed to download Plex Media Server .deb file."
    fi

    log_info "Installing Plex Media Server package..."
    if ! dpkg -i "$temp_deb"; then
        log_warn "dpkg encountered issues. Attempting to fix missing dependencies..."
        apt install -f -y || handle_error "Failed to install dependencies for Plex Media Server."
    fi

    # Configure Plex to run as the specified user.
    local PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        log_info "Configuring Plex to run as ${USERNAME}..."
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" || \
            log_warn "Failed to set Plex user in $PLEX_CONF"
    else
        log_warn "$PLEX_CONF not found; skipping user configuration."
    fi

    # Enable and restart Plex service.
    log_info "Enabling Plex Media Server service..."
    systemctl enable plexmediaserver || log_warn "Failed to enable Plex Media Server service."

    # Clean up the temporary .deb file.
    rm -f "$temp_deb"
    log_info "Plex Media Server installed successfully."
}

caddy_config() {
    print_section "Caddy Configuration"

    log_info "Releasing occupied network ports..."
    local tcp_ports=( "8080" "80" "443" "32400" "8324" "32469" )
    local udp_ports=( "80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415" )
    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log_info "Killing processes on TCP port $port: $pids"
            kill -9 $pids || log_warn "Failed to kill processes on TCP port $port"
        fi
    done
    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log_info "Killing processes on UDP port $port: $pids"
            kill -9 $pids || log_warn "Failed to kill processes on UDP port $port"
        fi
    done
    log_info "Port release process completed."

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

    log_info "Updating package lists..."
    apt update || handle_error "Failed to update package lists."

    log_info "Installing Caddy..."
    apt install -y caddy || handle_error "Failed to install Caddy."
    log_info "Caddy installed successfully."

    local CUSTOM_CADDYFILE="/home/sawyer/github/linux/dotfiles/Caddyfile"
    local DEST_CADDYFILE="/etc/caddy/Caddyfile"
    if [ -f "$CUSTOM_CADDYFILE" ]; then
        log_info "Copying custom Caddyfile from $CUSTOM_CADDYFILE to $DEST_CADDYFILE..."
        cp -f "$CUSTOM_CADDYFILE" "$DEST_CADDYFILE" || log_warn "Failed to copy custom Caddyfile."
    else
        log_warn "Custom Caddyfile not found at $CUSTOM_CADDYFILE"
    fi

    log_info "Enabling Caddy service..."
    systemctl enable caddy || log_warn "Failed to enable Caddy service."

    log_info "Restarting Caddy service..."
    systemctl restart caddy || log_warn "Failed to restart Caddy service."

    log_info "Caddy configuration completed successfully."
}

install_configure_zfs() {
    print_section "Install and configure ZFS and mount WD_BLACK"

    # Define local variables.
    local LOG_FILE="/var/log/install_configure_zfs.log"
    local ZPOOL_NAME="WD_BLACK"
    local LOG_DIR

    # Ensure log directory exists and secure the log file.
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || { log ERROR "Failed to create log directory: $LOG_DIR"; return 1; }
    fi
    touch "$LOG_FILE" || { log ERROR "Failed to create log file: $LOG_FILE"; return 1; }
    chmod 600 "$LOG_FILE" || { log ERROR "Failed to set permissions on $LOG_FILE"; return 1; }

    log INFO "ZFS installation and configuration started."

    # -- Update Package Lists and Install ZFS Packages --
    log INFO "Updating package lists..."
    apt update || { log ERROR "Failed to update package lists."; return 1; }

    log INFO "Installing prerequisites and ZFS packages..."
    # Install any necessary build and kernel header packages.
    apt install -y dpkg-dev linux-headers-generic linux-image-generic || { log ERROR "Failed to install prerequisites."; return 1; }
    # Install ZFS from Ubuntu's official repositories.
    DEBIAN_FRONTEND=noninteractive apt install -y zfs-dkms zfsutils-linux || { log ERROR "Failed to install ZFS packages."; return 1; }
    log INFO "ZFS packages installed successfully."

    # -- Enable ZFS Services --
    log INFO "Enabling ZFS auto-import and mount services..."
    systemctl enable zfs-import-cache.service || log WARN "Failed to enable zfs-import-cache.service."
    systemctl enable zfs-mount.service || log WARN "Failed to enable zfs-mount.service."

    # -- Configure and Mount ZFS Pool --
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import -f "$ZPOOL_NAME"; then
            log ERROR "Failed to import ZFS pool '$ZPOOL_NAME'."
            return 1
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already imported."
    fi

    if ! zfs set mountpoint=/media/"$ZPOOL_NAME" "$ZPOOL_NAME"; then
        log WARN "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log INFO "ZFS pool '$ZPOOL_NAME' mountpoint set to /media/$ZPOOL_NAME."
    fi

    log INFO "ZFS installation and configuration finished successfully."
}

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

docker_config() {
    print_section "Docker Configuration"
    log_info "Starting Docker installation and configuration..."

    # Install Docker if not already installed.
    if command -v docker &>/dev/null; then
        log_info "Docker is already installed."
    else
        log_info "Docker not found; updating package lists and installing Docker..."
        apt install -y docker.io || handle_error "Failed to install Docker."
        log_info "Docker installed successfully."
    fi

    # Add target user to the docker group if not already a member.
    if ! id -nG "$USERNAME" | grep -qw docker; then
        log_info "Adding user '$USERNAME' to the docker group..."
        usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to the docker group."
    else
        log_info "User '$USERNAME' is already in the docker group."
    fi

    # Configure Docker daemon.
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
    log_info "Docker daemon configuration updated."

    # Enable and restart Docker service.
    systemctl enable docker || log_warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log_info "Docker service is enabled and running."

    # Install Docker Compose if not installed.
    log_info "Starting Docker Compose installation..."
    if ! command -v docker-compose &>/dev/null; then
        local version="2.20.2"
        log_info "Docker Compose not found; downloading version ${version}..."
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log_info "Docker Compose installed successfully."
    else
        log_info "Docker Compose is already installed."
    fi
}

copy_shell_configs() {
    print_section "Updating Shell Configuration Files"
    local source_dir="/home/${USERNAME}/github/bash/linux/dotfiles"
    local dest_dir="/home/${USERNAME}"
    local files=(".bashrc" ".profile")

    # 1) Copy the specified dotfiles from source to destination.
    for file in "${files[@]}"; do
        local src="${source_dir}/${file}"
        local dest="${dest_dir}/${file}"
        if [ -f "$src" ]; then
            log_info "Copying ${src} to ${dest}..."
            cp -f "$src" "$dest" || log_warn "Failed to copy ${src} to ${dest}."
            chown "${USERNAME}:${USERNAME}" "$dest" || log_warn "Failed to set ownership for ${dest}."
        else
            log_warn "Source file ${src} not found; skipping."
        fi
    done

    # 2) Enable alias expansion in this script.
    shopt -s expand_aliases

    # 3) Source the new .bashrc so that aliases and functions become available now.
    #    Hard-coded to /home/sawyer/.bashrc:
    if [ -f "/home/sawyer/.bashrc" ]; then
        log_info "Sourcing /home/sawyer/.bashrc in the current script..."
        source /home/sawyer/.bashrc
    else
        log_warn "No .bashrc found at /home/sawyer/.bashrc; skipping source."
    fi

    log_info "Shell configuration files update completed (aliases/functions loaded)."
}

install_zig_binary() {
    print_section "Zig Installation"
    log_info "Installing Zig binary from the official release..."

    # Specify the desired Zig version.
    local ZIG_VERSION="0.12.1"
    local ZIG_TARBALL_URL="https://ziglang.org/download/${ZIG_VERSION}/zig-linux-x86_64-${ZIG_VERSION}.tar.xz"
    local ZIG_INSTALL_DIR="/opt/zig"
    local TEMP_DOWNLOAD="/tmp/zig.tar.xz"

    log_info "Ensuring required dependencies (curl, tar) are installed..."
    apt install -y curl tar || handle_error "Failed to install required dependencies."

    log_info "Downloading Zig ${ZIG_VERSION} binary from ${ZIG_TARBALL_URL}..."
    curl -L -o "${TEMP_DOWNLOAD}" "${ZIG_TARBALL_URL}" || handle_error "Failed to download Zig binary."

    log_info "Extracting Zig to ${ZIG_INSTALL_DIR}..."
    rm -rf "${ZIG_INSTALL_DIR}"  # Clean any previous installation.
    mkdir -p "${ZIG_INSTALL_DIR}" || handle_error "Failed to create ${ZIG_INSTALL_DIR}."
    tar -xf "${TEMP_DOWNLOAD}" -C "${ZIG_INSTALL_DIR}" --strip-components=1 || handle_error "Failed to extract Zig binary."

    log_info "Creating symlink for Zig in /usr/local/bin..."
    ln -sf "${ZIG_INSTALL_DIR}/zig" /usr/local/bin/zig || handle_error "Failed to create symlink for Zig."

    log_info "Cleaning up temporary files..."
    rm -f "${TEMP_DOWNLOAD}"

    if command -v zig &>/dev/null; then
        log_info "Zig installation completed successfully! Version: $(zig version)"
    else
        handle_error "Zig is not accessible from the command line."
    fi
}

install_ly() {
    print_section "Ly Display Manager Installation"
    log_info "Installing Ly Display Manager..."

    # Verify required commands are available.
    local required_cmds=(git zig systemctl)
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            handle_error "'$cmd' is not installed. Please install it and try again."
        fi
    done

    local LY_DIR="/opt/ly"

    # Clone or update the Ly repository.
    if [ ! -d "$LY_DIR" ]; then
        log_info "Cloning Ly repository into $LY_DIR..."
        git clone https://github.com/fairyglade/ly "$LY_DIR" || handle_error "Failed to clone the Ly repository."
    else
        log_info "Ly repository already exists in $LY_DIR. Updating..."
        cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
        git pull || handle_error "Failed to update the Ly repository."
    fi

    # Compile Ly using Zig.
    cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
    log_info "Compiling Ly with Zig..."
    zig build || handle_error "Compilation of Ly failed."

    # Install Ly's systemd service.
    log_info "Installing Ly systemd service..."
    zig build installsystemd || handle_error "Installation of Ly systemd service failed."

    # Disable any conflicting display managers.
    log_info "Disabling existing display managers (gdm, sddm, lightdm, lxdm)..."
    local dm_list=(gdm sddm lightdm lxdm)
    for dm in "${dm_list[@]}"; do
        if systemctl is-enabled "${dm}.service" &>/dev/null; then
            log_info "Disabling ${dm}.service..."
            systemctl disable --now "${dm}.service" || handle_error "Failed to disable ${dm}.service."
        fi
    done

    # Remove leftover display-manager symlink if it exists.
    if [ -L /etc/systemd/system/display-manager.service ]; then
        log_info "Removing leftover /etc/systemd/system/display-manager.service symlink..."
        rm /etc/systemd/system/display-manager.service || log_warn "Failed to remove display-manager.service symlink."
    fi

    # Enable Ly to start on next boot.
    log_info "Enabling ly.service for next boot..."
    systemctl enable ly.service || handle_error "Failed to enable ly.service."

    # Stop ly.service if it is currently active to avoid interrupting the current session.
    if systemctl is-active ly.service &>/dev/null; then
        log_info "Stopping active ly.service to avoid a blank screen..."
        systemctl stop ly.service || log_warn "Failed to stop ly.service."
    fi

    # Disable tty2 getty to prevent conflicts.
    log_info "Disabling getty@tty2.service..."
    systemctl disable getty@tty2.service || handle_error "Failed to disable getty@tty2.service."

    log_info "Ly has been installed and configured as the default login manager."
    log_info "Ly will take effect on next reboot, or you can start it now with: systemctl start ly.service"
}

deploy_user_scripts() {
    print_section "Deploying User Scripts"
    log_info "Starting deployment of user scripts..."

    # Use the target user's home directory from the global USERNAME variable.
    local SCRIPT_SOURCE="/home/${USERNAME}/github/bash/linux/_scripts"
    local SCRIPT_TARGET="/home/${USERNAME}/bin"
    local EXPECTED_OWNER="${USERNAME}"

    # Ensure the source directory exists.
    if [ ! -d "$SCRIPT_SOURCE" ]; then
        handle_error "Source directory '$SCRIPT_SOURCE' does not exist."
    fi

    # Verify that the source directory is owned by the expected user.
    local source_owner
    source_owner=$(stat -c %U "$SCRIPT_SOURCE") || handle_error "Failed to retrieve ownership details of '$SCRIPT_SOURCE'."
    if [ "$source_owner" != "$EXPECTED_OWNER" ]; then
        handle_error "Invalid script source ownership for '$SCRIPT_SOURCE' (Owner: $source_owner). Expected: $EXPECTED_OWNER"
    fi

    # Ensure the target directory exists.
    if [ ! -d "$SCRIPT_TARGET" ]; then
        log_info "Creating target directory '$SCRIPT_TARGET'..."
        mkdir -p "$SCRIPT_TARGET" || handle_error "Failed to create target directory '$SCRIPT_TARGET'."
        chown "${USERNAME}:${USERNAME}" "$SCRIPT_TARGET" || log_warn "Failed to set ownership for '$SCRIPT_TARGET'."
    fi

    # Perform a dry-run deployment with rsync.
    log_info "Performing dry-run for script deployment..."
    if ! rsync --dry-run -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/"; then
        handle_error "Dry-run failed for script deployment."
    fi

    # Execute the actual deployment.
    log_info "Deploying scripts from '$SCRIPT_SOURCE' to '$SCRIPT_TARGET'..."
    if ! rsync -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/"; then
        handle_error "Script deployment failed."
    fi

    # Set executable permissions on all files in the target directory.
    log_info "Setting executable permissions on deployed scripts..."
    if ! find "${SCRIPT_TARGET}" -type f -exec chmod 755 {} \;; then
        handle_error "Failed to update script permissions in '$SCRIPT_TARGET'."
    fi

    log_info "Script deployment completed successfully."
}

python_dev_setup() {
    local user_home
    user_home="$(eval echo ~"${USERNAME}")"

    # -------------------------------------------------------------------------
    # 1) Install System Dependencies
    # -------------------------------------------------------------------------
    print_section "APT Dependencies Installation"
    apt install -y build-essential git curl wget vim tmux unzip zip ca-certificates \
        libssl-dev libffi-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
        libncurses5-dev libgdbm-dev libnss3-dev liblzma-dev xz-utils libedit-dev libzstd-dev \
        libxml2-dev libxmlsec1-dev tk-dev llvm gnupg lsb-release jq || handle_error "Failed to install required dependencies."
    apt clean || log_warn "Failed to clean package caches."

    # -------------------------------------------------------------------------
    # 2) pyenv Installation/Update
    # -------------------------------------------------------------------------
    print_section "pyenv Installation/Update"
    if [ ! -d "${user_home}/.pyenv" ]; then
        git clone https://github.com/pyenv/pyenv.git "${user_home}/.pyenv" || handle_error "Failed to clone pyenv."

        # Append pyenv initialization to the target user's .bashrc if not already present.
        if ! grep -q 'export PYENV_ROOT' "${user_home}/.bashrc"; then
            cat << 'EOF' >> "${user_home}/.bashrc"

# >>> pyenv initialization >>>
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "$(pyenv init -)"
fi
# <<< pyenv initialization <<<
EOF
        fi
    else
        pushd "${user_home}/.pyenv" >/dev/null || handle_error "Failed to enter pyenv directory."
        git pull --ff-only || handle_error "Failed to update pyenv."
        popd >/dev/null
    fi

    # Ensure the user "sawyer" owns the entire .pyenv directory (fixes permissions).
    chown -R "${USERNAME}:${USERNAME}" "${user_home}/.pyenv"

    # Load pyenv into current environment.
    export PYENV_ROOT="${user_home}/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"

    # -------------------------------------------------------------------------
    # 3) Install Latest Python 3 via pyenv
    # -------------------------------------------------------------------------
    print_section "Python Installation via pyenv"
    local latest_py3
    latest_py3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')" \
        || handle_error "Failed to determine the latest Python version."
    if [ -z "$latest_py3" ]; then
        handle_error "Could not determine the latest Python 3.x version."
    fi

    local current_py3
    current_py3="$(pyenv global 2>/dev/null || true)"

    # Only install/upgrade if we're not already on the latest version.
    local new_python_installed=false
    if [ "$current_py3" != "$latest_py3" ]; then
        if ! pyenv versions --bare | grep -q "^${latest_py3}$"; then
            pyenv install "$latest_py3" || handle_error "Failed to install Python $latest_py3."
        fi
        pyenv global "$latest_py3" || handle_error "Failed to set Python $latest_py3 as global."
        new_python_installed=true
    fi
    eval "$(pyenv init -)"  # Re-init to pick up the newly installed version.

    # -------------------------------------------------------------------------
    # 4) pipx Installation and Global Tools
    # -------------------------------------------------------------------------
    print_section "pipx Installation and Tools Update"
    # Use the target user's home for --user installs.
    HOME="$user_home" python3 -m pip install --upgrade pip || handle_error "Failed to upgrade pip."
    HOME="$user_home" python3 -m pip install --user pipx || handle_error "Failed to install pipx."

    # Ensure .local/bin is in PATH via .bashrc if not already present.
    if ! grep -q 'export PATH=.*\.local/bin' "${user_home}/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${user_home}/.bashrc"
    fi
    export PATH="${user_home}/.local/bin:$PATH"

    pipx upgrade pipx || true
    if [ "$new_python_installed" = true ]; then
        pipx reinstall-all || true
    else
        pipx upgrade-all || true
    fi

    # Install/Upgrade a curated list of pipx-managed tools.
    local PIPX_TOOLS=( ansible-core black cookiecutter coverage flake8 isort ipython mypy pip-tools \
                       pylint pyupgrade pytest rich-cli tldr tox twine poetry pre-commit )
    local tool
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            pipx upgrade "$tool" || true
        else
            pipx install "$tool" || true
        fi
    done

    print_section "Python Development Setup Complete"
    log_info "SUCCESS! ${USERNAME}'s environment is now set up with the latest stable Python (via pyenv), pipx updated, and a curated set of CLI tools."

    # -------------------------------------------------------------------------
    # 5) Create Virtual Environments in Each Web Subdirectory
    # -------------------------------------------------------------------------
    print_section "VENV setup for FastAPI Applications"
    # If your script is not interactive, ensure we don't rely on alias expansions.
    shopt -s nullglob

    # Define the function that replaces the 'venv' alias from .bashrc
    setup_venv() {
        local venv_name=".venv"
        # Deactivate any existing venv in this shell
        if type deactivate &>/dev/null; then
            deactivate
        fi
        # Create venv if it doesn't exist
        if [ ! -d "$venv_name" ]; then
            echo "Creating virtual environment in $venv_name..."
            python3 -m venv "$venv_name"
        fi
        # Activate and install requirements
        source "$venv_name/bin/activate"
        [ -f "requirements.txt" ] && pip install -r requirements.txt
        [ -f "requirements-dev.txt" ] && pip install -r requirements-dev.txt
    }


    # Loop over each subdirectory in the web folder and create/activate a venv
    local base_dir="${user_home}/github/web"
    local dir
    for dir in "$base_dir"/*; do
        if [ -d "$dir" ]; then
            echo "Setting up virtual environment in: $dir"
            pushd "$dir" > /dev/null || { echo "Failed to enter directory: $dir"; continue; }
            setup_venv
            popd > /dev/null
        fi
    done
}

configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log_info "Configuring daily system maintenance tasks..."

    local CRON_FILE="/etc/cron.daily/ubuntu_maintenance"

    # Backup any existing maintenance script.
    if [ -f "$CRON_FILE" ]; then
        mv "$CRON_FILE" "${CRON_FILE}.bak.$(date +%Y%m%d%H%M%S)" && \
            log_info "Existing cron file backed up." || \
            log_warn "Failed to backup existing cron file at $CRON_FILE."
    fi

    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Ubuntu maintenance script (added by ubuntu_setup script)
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
EOF

    if chmod +x "$CRON_FILE"; then
        log_info "Daily maintenance script created and permissions set at $CRON_FILE."
    else
        log_warn "Failed to set execute permission on $CRON_FILE."
    fi
}

final_checks() {
    print_section "Final System Checks"
    log_info "Kernel version: $(uname -r)"
    log_info "System uptime: $(uptime -p)"
    log_info "Disk usage (root partition): $(df -h / | awk 'NR==2 {print $0}')"

    # Retrieve memory usage details.
    local mem_total mem_used mem_free
    read -r mem_total mem_used mem_free < <(free -h | awk '/^Mem:/{print $2, $3, $4}')
    log_info "Memory usage: Total: ${mem_total}, Used: ${mem_used}, Free: ${mem_free}"

    # Log CPU model.
    local cpu_model
    cpu_model=$(lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//')
    log_info "CPU: ${cpu_model}"

    # Log active network interfaces.
    log_info "Active network interfaces:"
    ip -brief address | while read -r iface; do
         log_info "  $iface"
    done

    # Log system load averages.
    local load_avg
    load_avg=$(awk '{print $1", "$2", "$3}' /proc/loadavg)
    log_info "Load averages (1, 5, 15 min): ${load_avg}"
}

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

main() {
    # Ensure the script is executed with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    # Ensure the log directory exists and set proper permissions.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log_info "Ubuntu setup script execution started."

    # Execute setup functions (ensure these are defined earlier in the script).
    check_root
    check_network
    update_system
    ensure_user
    configure_sudoers
    setup_repos
    copy_shell_configs
    install_packages
    configure_ssh
    configure_firewall
    configure_fail2ban
    install_plex
    #install_configure_zfs
    caddy_config
    docker_config
    install_zig_binary
    deploy_user_scripts
    python_dev_setup
    enable_dunamismax_services
    configure_periodic
    final_checks
    install_ly
    prompt_reboot
}

main "$@"