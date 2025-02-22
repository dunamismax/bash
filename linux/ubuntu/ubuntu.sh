#!/usr/bin/env bash
# ==============================================================================
# Ubuntu Server Automation Script v5.0 (Master)
#
# Overview:
#   This master script automates the initial configuration and hardening of an
#   Ubuntu system. It updates the system, installs a comprehensive list of
#   essential packages, configures users, time settings, network (including Wi‑Fi),
#   SSH, firewall, and additional services such as Plex, Caddy, ZFS, Docker,
#   Zig/LY, desktop environments (i3 and XFCE), GitHub repositories, and various
#   custom services. It also includes backup, logging, periodic maintenance,
#   and system health functions.
#
# Usage:
#   Run as root. For help:
#       sudo $(basename "$0") --help
#
# Disclaimer:
#   THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY. USE AT YOUR OWN RISK.
#
# Author: dunamismax (combined & improved)
# Version: 5.0
# Date: 2025-02-22
# ==============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants & Environment Setup
#--------------------------------------------------
LOG_FILE="/var/log/ubuntu_setup.log"
USERNAME="sawyer"
USER_HOME="/home/${USERNAME}"

# Combined package list (duplicates removed)
PACKAGES=(
  bash vim nano screen tmux mc zsh htop tree ncdu neofetch
  build-essential cmake ninja-build meson gettext git
  openssh-server ufw curl wget rsync sudo bash-completion
  python3 python3-dev python3-pip python3-venv
  libssl-dev libffi-dev zlib1g-dev libreadline-dev libbz2-dev tk-dev xz-utils libncurses5-dev libgdbm-dev libnss3-dev liblzma-dev libxml2-dev libxmlsec1-dev
  ca-certificates software-properties-common apt-transport-https gnupg lsb-release
  clang llvm netcat-openbsd lsof unzip zip
  xorg x11-xserver-utils i3-wm i3status i3lock i3blocks dmenu xterm alacritty feh fonts-dejavu-core picom
  net-tools nmap iftop iperf3 tcpdump lynis
  golang-go gdb
  john hydra aircrack-ng nikto
  postgresql-client mysql-client redis-server
  ruby rustc jq certbot
)

# Global options (overridable via CLI)
NON_INTERACTIVE=0
WIFI_SSID=""
WIFI_PSK=""
NO_REBOOT=0

# Terminal color definitions (Nord theme)
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                     # Reset to No Color

# Ensure log directory and file exist
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

#--------------------------------------------------
# Logging and Error Handling Functions
#--------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local entry="[$timestamp] [${level^^}] $message"
    echo "$entry" >> "$LOG_FILE"
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
    log_error "Error encountered at line ${BASH_LINENO[0]:-${LINENO}} in function ${FUNCNAME[1]:-main}."
    exit "$code"
}

cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Add any cleanup commands here.
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line ${LINENO}."' ERR

#--------------------------------------------------
# Utility Functions
#--------------------------------------------------
command_exists() {
    command -v "$1" &>/dev/null
}

# Backup a file (if it exists) with a timestamp appended.
backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup="${file}.bak.$(date +%Y%m%d%H%M%S)"
        if cp "$file" "$backup"; then
            log_info "Backed up $file to $backup"
        else
            log_warn "Failed to backup $file"
        fi
    else
        log_warn "File $file not found; skipping backup."
    fi
}

# Print a section header for clarity.
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

#--------------------------------------------------
# Script Usage and Argument Parsing
#--------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

This script automates the setup and configuration of an Ubuntu server.

Options:
  -h, --help                Show this help message and exit.
  -n, --non-interactive     Run in non-interactive mode.
  -s, --wifi-ssid SSID      Specify Wi‑Fi SSID (non-interactive mode).
  -p, --wifi-psk PSK        Specify Wi‑Fi PSK (leave empty for open networks).
  -r, --no-reboot           Do not prompt for reboot at the end.
EOF
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage ;;
            -n|--non-interactive)
                NON_INTERACTIVE=1 ;;
            -s|--wifi-ssid)
                WIFI_SSID="$2"
                shift ;;
            -p|--wifi-psk)
                WIFI_PSK="$2"
                shift ;;
            -r|--no-reboot)
                NO_REBOOT=1 ;;
            *)
                log_warn "Unknown option: $1"
                usage ;;
        esac
        shift
    done
}

#--------------------------------------------------
# Pre-requisites
#--------------------------------------------------
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

#--------------------------------------------------
# System Update & Package Installation
#--------------------------------------------------
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

install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    if ! apt install -y "${PACKAGES[@]}"; then
        handle_error "Failed to install one or more packages."
    fi
    log_info "Package installation complete."
}

#--------------------------------------------------
# Timezone and NTP Configuration
#--------------------------------------------------
configure_timezone() {
    print_section "Timezone Configuration"
    local tz="America/New_York"
    log_info "Setting timezone to ${tz}..."
    if [ -f "/usr/share/zoneinfo/${tz}" ]; then
        ln -sf "/usr/share/zoneinfo/${tz}" /etc/localtime
        log_info "Timezone set to ${tz}."
    else
        log_warn "Timezone file for ${tz} not found."
    fi
}

configure_ntp() {
    print_section "NTP Configuration"
    log_info "Configuring NTP service..."
    local ntp_conf="/etc/ntp.conf"
    if [ ! -f "$ntp_conf" ]; then
        cat <<'EOF' > "$ntp_conf"
# Minimal ntp configuration
server 0.pool.ntp.org iburst
server 1.pool.ntp.org iburst
server 2.pool.ntp.org iburst
server 3.pool.ntp.org iburst
EOF
        log_info "Created new NTP configuration at $ntp_conf."
    else
        log_info "NTP configuration file exists at $ntp_conf."
    fi
    systemctl enable ntp
    if systemctl restart ntp; then
        log_info "NTP service restarted successfully."
    else
        log_warn "Failed to restart NTP service."
    fi
}

#--------------------------------------------------
# Repository and Shell Setup
#--------------------------------------------------
setup_repos() {
    print_section "GitHub Repositories Setup"
    log_info "Setting up GitHub repositories for user '$USERNAME'..."
    local GH_DIR="/home/$USERNAME/github"
    mkdir -p "$GH_DIR" || handle_error "Failed to create GitHub directory at $GH_DIR."
    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"
        if [ -d "$REPO_DIR" ]; then
            log_info "Removing existing repository directory for '$repo'..."
            rm -rf "$REPO_DIR" || log_warn "Failed to remove existing directory '$REPO_DIR'."
        fi
        log_info "Cloning repository '$repo' into '$REPO_DIR'..."
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            log_warn "Failed to clone repository '$repo'."
        else
            log_info "Repository '$repo' cloned successfully."
        fi
    done
    log_info "Setting ownership of '$GH_DIR' to '$USERNAME'..."
    chown -R "$USERNAME:$USERNAME" "$GH_DIR" || log_warn "Failed to set ownership for '$GH_DIR'."
}

copy_shell_configs() {
    print_section "Updating Shell Configuration Files"
    local source_dir="/home/${USERNAME}/github/bash/linux/dotfiles"
    local dest_dir="/home/${USERNAME}"
    local files=(".bashrc" ".profile")
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
    shopt -s expand_aliases
    if [ -f "/home/${USERNAME}/.bashrc" ]; then
        log_info "Sourcing /home/${USERNAME}/.bashrc..."
        source "/home/${USERNAME}/.bashrc"
    else
        log_warn "No .bashrc found at /home/${USERNAME}/.bashrc; skipping source."
    fi
}

set_bash_shell() {
    print_section "Default Shell Configuration"
    if ! command_exists bash; then
        log_info "Bash not found; installing..."
        if ! apt install -y bash; then
            log_warn "Bash installation failed."
            return 1
        fi
    fi
    if ! grep -qxF "/bin/bash" /etc/shells; then
        echo "/bin/bash" >> /etc/shells
        log_info "Added /bin/bash to /etc/shells."
    fi
    if chsh -s /bin/bash "$USERNAME"; then
        log_info "Default shell for ${USERNAME} set to /bin/bash."
    else
        log_warn "Failed to set default shell for ${USERNAME}."
    fi
}

#--------------------------------------------------
# SSH and Sudo Security Configuration
#--------------------------------------------------
configure_ssh() {
    print_section "SSH Configuration"
    log_info "Configuring OpenSSH Server..."
    if ! dpkg -s openssh-server &>/dev/null; then
        log_info "openssh-server not installed. Installing..."
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log_info "OpenSSH Server installed successfully."
    else
        log_info "OpenSSH Server already installed."
    fi
    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."
    local sshd_config="/etc/ssh/sshd_config"
    if [ ! -f "$sshd_config" ]; then
        handle_error "SSHD configuration file not found: $sshd_config"
    fi
    backup_file "$sshd_config"
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
    for key in "${!ssh_settings[@]}"; do
        if grep -qE "^${key}[[:space:]]" "$sshd_config"; then
            sed -i "s/^${key}[[:space:]].*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done
    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log_info "SSH configuration updated successfully."
}

setup_sudoers() {
    print_section "Sudo Configuration"
    log_info "Ensuring ${USERNAME} has sudo privileges..."
    if id -nG "$USERNAME" | grep -qw sudo; then
        log_info "User ${USERNAME} is already in the sudo group."
    else
        if usermod -aG sudo "$USERNAME"; then
            log_info "User ${USERNAME} added to sudo group."
        else
            log_warn "Failed to add ${USERNAME} to sudo group."
        fi
    fi
}

#--------------------------------------------------
# Firewall (UFW) Configuration
#--------------------------------------------------
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
    "$ufw_cmd" allow 32400/tcp || log_warn "Failed to allow Plex port"
    "$ufw_cmd" --force enable || handle_error "Failed to enable ufw firewall"
    systemctl enable ufw || log_warn "Failed to enable ufw service"
    systemctl start ufw || log_warn "Failed to start ufw service"
    log_info "Firewall configured and enabled."
}

#--------------------------------------------------
# Service Installation and Configuration
#--------------------------------------------------
install_plex() {
    print_section "Plex Media Server Installation"
    log_info "Installing Plex Media Server..."
    if ! command_exists curl; then
        handle_error "curl is required but not installed."
    fi
    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    local temp_deb="/tmp/plexmediaserver.deb"
    log_info "Downloading Plex from ${plex_url}..."
    if ! curl -L -o "$temp_deb" "$plex_url"; then
        handle_error "Failed to download Plex Media Server .deb file."
    fi
    log_info "Installing Plex package..."
    if ! dpkg -i "$temp_deb"; then
        log_warn "dpkg encountered issues. Attempting to fix missing dependencies..."
        apt install -f -y || handle_error "Failed to install dependencies for Plex."
    fi
    local PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        log_info "Configuring Plex to run as ${USERNAME}..."
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" || log_warn "Failed to set Plex user in $PLEX_CONF"
    else
        log_warn "$PLEX_CONF not found; skipping user configuration."
    fi
    systemctl enable plexmediaserver || log_warn "Failed to enable Plex service."
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
    local CUSTOM_CADDYFILE="/home/${USERNAME}/github/linux/dotfiles/Caddyfile"
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

install_fastfetch() {
    print_section "Fastfetch Installation"
    local FASTFETCH_URL="https://github.com/fastfetch-cli/fastfetch/releases/download/2.36.1/fastfetch-linux-amd64.deb"
    local TEMP_DEB="/tmp/fastfetch-linux-amd64.deb"
    log_info "Downloading fastfetch from ${FASTFETCH_URL}..."
    if ! curl -L -o "$TEMP_DEB" "$FASTFETCH_URL"; then
        handle_error "Failed to download fastfetch deb file."
    fi
    log_info "Installing fastfetch..."
    if ! dpkg -i "$TEMP_DEB"; then
        log_warn "fastfetch installation encountered issues; attempting to fix dependencies..."
        apt install -f -y || handle_error "Failed to fix dependencies for fastfetch."
    fi
    rm -f "$TEMP_DEB"
    log_info "Fastfetch installed successfully."
}

install_configure_zfs() {
    print_section "ZFS Installation and Configuration"
    local ZPOOL_NAME="WD_BLACK"
    local MOUNT_POINT="/media/${ZPOOL_NAME}"
    log_info "Updating package lists..."
    apt update || { log_error "Failed to update package lists."; return 1; }
    log_info "Installing prerequisites for ZFS..."
    apt install -y dpkg-dev linux-headers-generic linux-image-generic || { log_error "Failed to install prerequisites."; return 1; }
    log_info "Installing ZFS packages..."
    DEBIAN_FRONTEND=noninteractive apt install -y zfs-dkms zfsutils-linux || { log_error "Failed to install ZFS packages."; return 1; }
    log_info "Enabling ZFS auto-import and mount services..."
    systemctl enable zfs-import-cache.service || log_warn "Could not enable zfs-import-cache.service."
    systemctl enable zfs-mount.service || log_warn "Could not enable zfs-mount.service."
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log_info "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import -f "$ZPOOL_NAME"; then
            log_error "Failed to import ZFS pool '$ZPOOL_NAME'."
            return 1
        fi
    else
        log_info "ZFS pool '$ZPOOL_NAME' is already imported."
    fi
    log_info "Setting mountpoint for ZFS pool '$ZPOOL_NAME' to '$MOUNT_POINT'..."
    if ! zfs set mountpoint="${MOUNT_POINT}" "$ZPOOL_NAME"; then
        log_warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log_info "Mountpoint for pool '$ZPOOL_NAME' successfully set."
    fi
    log_info "ZFS installation and configuration finished successfully."
}

docker_config() {
    print_section "Docker Configuration"
    log_info "Starting Docker installation and configuration..."
    if command_exists docker; then
        log_info "Docker is already installed."
    else
        log_info "Installing Docker..."
        apt install -y docker.io || handle_error "Failed to install Docker."
        log_info "Docker installed successfully."
    fi
    if ! id -nG "$USERNAME" | grep -qw docker; then
        log_info "Adding user '$USERNAME' to docker group..."
        usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to docker group."
    else
        log_info "User '$USERNAME' is already in the docker group."
    fi
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
    systemctl enable docker || log_warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log_info "Docker service is enabled and running."
    log_info "Installing Docker Compose..."
    if ! command_exists docker-compose; then
        local version="2.20.2"
        log_info "Downloading Docker Compose version ${version}..."
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log_info "Docker Compose installed successfully."
    else
        log_info "Docker Compose is already installed."
    fi
}

install_zig_binary() {
    print_section "Zig Installation"
    log_info "Installing Zig binary from the official release..."
    local ZIG_VERSION="0.12.1"
    local ZIG_TARBALL_URL="https://ziglang.org/download/${ZIG_VERSION}/zig-linux-x86_64-${ZIG_VERSION}.tar.xz"
    local ZIG_INSTALL_DIR="/opt/zig"
    local TEMP_DOWNLOAD="/tmp/zig.tar.xz"
    log_info "Ensuring required dependencies (curl, tar) are installed..."
    apt install -y curl tar || handle_error "Failed to install required dependencies."
    log_info "Downloading Zig ${ZIG_VERSION} from ${ZIG_TARBALL_URL}..."
    curl -L -o "${TEMP_DOWNLOAD}" "${ZIG_TARBALL_URL}" || handle_error "Failed to download Zig binary."
    log_info "Extracting Zig to ${ZIG_INSTALL_DIR}..."
    rm -rf "${ZIG_INSTALL_DIR}"
    mkdir -p "${ZIG_INSTALL_DIR}" || handle_error "Failed to create ${ZIG_INSTALL_DIR}."
    tar -xf "${TEMP_DOWNLOAD}" -C "${ZIG_INSTALL_DIR}" --strip-components=1 || handle_error "Failed to extract Zig binary."
    ln -sf "${ZIG_INSTALL_DIR}/zig" /usr/local/bin/zig || handle_error "Failed to create symlink for Zig."
    rm -f "${TEMP_DOWNLOAD}"
    if command_exists zig; then
        log_info "Zig installation completed successfully! Version: $(zig version)"
    else
        handle_error "Zig is not accessible from the command line."
    fi
}

install_ly() {
    print_section "Ly Display Manager Installation"
    log_info "Installing Ly Display Manager..."
    for cmd in git zig systemctl; do
        if ! command_exists "$cmd"; then
            handle_error "'$cmd' is not installed. Please install it and try again."
        fi
    done
    log_info "Installing Ly build dependencies..."
    apt update || handle_error "Failed to update package lists."
    apt install -y build-essential libpam0g-dev libxcb-xkb-dev libxcb-randr0-dev libxcb-xinerama0-dev libxcb-xrm-dev libxkbcommon-dev libxkbcommon-x11-dev || handle_error "Failed to install Ly build dependencies."
    local LY_DIR="/opt/ly"
    if [ ! -d "$LY_DIR" ]; then
        log_info "Cloning Ly repository into $LY_DIR..."
        git clone https://github.com/fairyglade/ly "$LY_DIR" || handle_error "Failed to clone the Ly repository."
    else
        log_info "Ly repository already exists in $LY_DIR. Updating..."
        cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
        git pull || handle_error "Failed to update the Ly repository."
    fi
    cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
    log_info "Compiling Ly with Zig..."
    zig build || handle_error "Compilation of Ly failed."
    log_info "Installing Ly systemd service..."
    zig build installsystemd || handle_error "Installation of Ly systemd service failed."
    log_info "Disabling conflicting display managers..."
    for dm in gdm sddm lightdm lxdm; do
        if systemctl is-enabled "${dm}.service" &>/dev/null; then
            log_info "Disabling ${dm}.service..."
            systemctl disable --now "${dm}.service" || handle_error "Failed to disable ${dm}.service."
        fi
    done
    if [ -L /etc/systemd/system/display-manager.service ]; then
        log_info "Removing leftover display-manager.service symlink..."
        rm /etc/systemd/system/display-manager.service || log_warn "Failed to remove display-manager.service symlink."
    fi
    log_info "Enabling ly.service for next boot..."
    systemctl enable ly.service || handle_error "Failed to enable ly.service."
    log_info "Disabling getty@tty2.service..."
    systemctl disable getty@tty2.service || handle_error "Failed to disable getty@tty2.service."
    log_info "Ly has been installed and configured as the default login manager."
    log_info "To start ly immediately, run: systemctl start ly.service"
}

# Optional: Install XFCE desktop environment (unique from Script #1)
install_xfce_desktop() {
    print_section "XFCE Desktop Installation"
    log_info "Installing XFCE desktop environment and addons..."
    local xfce_packages=(xfce4-session xfce4-panel xfce4-appfinder xfce4-settings xfce4-terminal xfdesktop xfwm4 thunar mousepad xfce4-whiskermenu-plugin)
    for pkg in "${xfce_packages[@]}"; do
        if dpkg -s "$pkg" &>/dev/null; then
            log_info "XFCE package '$pkg' is already installed."
        else
            if apt install -y "$pkg"; then
                log_info "Installed XFCE package: $pkg"
            else
                log_warn "Failed to install XFCE package: $pkg"
            fi
        fi
    done
    log_info "XFCE desktop installation complete."
}

enable_dunamismax_services() {
    print_section "DunamisMax Services Setup"
    log_info "Enabling DunamisMax website services..."
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
    log_info "DunamisMax services enabled."
}

deploy_user_scripts() {
    print_section "Deploying User Scripts"
    log_info "Starting deployment of user scripts..."
    local SCRIPT_SOURCE="/home/${USERNAME}/github/bash/linux/_scripts"
    local SCRIPT_TARGET="/home/${USERNAME}/bin"
    if [ ! -d "$SCRIPT_SOURCE" ]; then
        handle_error "Source directory '$SCRIPT_SOURCE' does not exist."
    fi
    if [ ! -d "$SCRIPT_TARGET" ]; then
        log_info "Creating target directory '$SCRIPT_TARGET'..."
        mkdir -p "$SCRIPT_TARGET" || handle_error "Failed to create target directory '$SCRIPT_TARGET'."
        chown "${USERNAME}:${USERNAME}" "$SCRIPT_TARGET" || log_warn "Failed to set ownership for '$SCRIPT_TARGET'."
    fi
    log_info "Performing dry-run for script deployment..."
    rsync --dry-run -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/" || handle_error "Dry-run failed for script deployment."
    log_info "Deploying scripts from '$SCRIPT_SOURCE' to '$SCRIPT_TARGET'..."
    rsync -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/" || handle_error "Script deployment failed."
    log_info "Setting executable permissions on deployed scripts..."
    find "${SCRIPT_TARGET}" -type f -exec chmod 755 {} \; || handle_error "Failed to update script permissions in '$SCRIPT_TARGET'."
    log_info "Script deployment completed successfully."
}

dotfiles_load() {
    print_section "Loading Dotfiles"
    log_info "Copying Alacritty configuration to ~/.config/alacritty..."
    mkdir -p "/home/$USERNAME/.config/alacritty"
    rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/alacritty/" "/home/$USERNAME/.config/alacritty/" || handle_error "Failed to copy Alacritty configuration."
    log_info "Copying i3 configuration to ~/.config/i3..."
    mkdir -p "/home/$USERNAME/.config/i3"
    rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/i3/" "/home/$USERNAME/.config/i3/" || handle_error "Failed to copy i3 configuration."
    log_info "Copying i3blocks configuration to ~/.config/i3blocks..."
    mkdir -p "/home/$USERNAME/.config/i3blocks"
    rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/i3blocks/" "/home/$USERNAME/.config/i3blocks/" || handle_error "Failed to copy i3blocks configuration."
    log_info "Setting execute permissions for i3blocks scripts..."
    chmod -R +x "/home/$USERNAME/.config/i3blocks/scripts" || log_warn "Failed to set execute permissions on i3blocks scripts."
    log_info "Copying picom configuration to ~/.config/picom..."
    mkdir -p "/home/$USERNAME/.config/picom"
    rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/picom/" "/home/$USERNAME/.config/picom/" || handle_error "Failed to copy picom configuration."
    log_info "Dotfiles loaded successfully."
}

configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log_info "Configuring daily system maintenance tasks..."
    local CRON_FILE="/etc/cron.daily/ubuntu_maintenance"
    if [ -f "$CRON_FILE" ]; then
        mv "$CRON_FILE" "${CRON_FILE}.bak.$(date +%Y%m%d%H%M%S)" && log_info "Existing cron file backed up." || log_warn "Failed to backup existing cron file at $CRON_FILE."
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

backup_configs() {
    print_section "Configuration Backups"
    local backup_dir="/var/backups/ubuntu_config_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    log_info "Backing up key configuration files to $backup_dir..."
    local files_to_backup=( "/etc/ssh/sshd_config" "/etc/ufw/user.rules" "/etc/ntp.conf" )
    for file in "${files_to_backup[@]}"; do
        if [ -f "$file" ]; then
            if cp "$file" "$backup_dir"; then
                log_info "Backed up $file"
            else
                log_warn "Failed to backup $file"
            fi
        else
            log_warn "File $file not found; skipping backup."
        fi
    done
}

backup_databases() {
    print_section "Database Backups"
    local backup_dir="/var/backups/db_backups_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    log_info "Starting automated database backups to $backup_dir..."
    if command_exists pg_dumpall; then
        if pg_dumpall -U postgres | gzip > "$backup_dir/postgres_backup.sql.gz"; then
            log_info "PostgreSQL backup completed."
        else
            log_warn "PostgreSQL backup failed."
        fi
    else
        log_warn "pg_dumpall not found; skipping PostgreSQL backup."
    fi
    if command_exists mysqldump; then
        if mysqldump --all-databases | gzip > "$backup_dir/mysql_backup.sql.gz"; then
            log_info "MySQL backup completed."
        else
            log_warn "MySQL backup failed."
        fi
    else
        log_warn "mysqldump not found; skipping MySQL backup."
    fi
}

rotate_logs() {
    print_section "Log Rotation"
    if [ -f "$LOG_FILE" ]; then
        local rotated_file="${LOG_FILE}.$(date +%Y%m%d%H%M%S).gz"
        log_info "Rotating log file: $LOG_FILE -> $rotated_file"
        if gzip -c "$LOG_FILE" > "$rotated_file" && :> "$LOG_FILE"; then
            log_info "Log rotation successful."
        else
            log_warn "Log rotation failed."
        fi
    else
        log_warn "Log file $LOG_FILE does not exist."
    fi
}

system_health_check() {
    print_section "System Health Check"
    log_info "Performing system health check..."
    log_info "Uptime: $(uptime)"
    log_info "Disk Usage:"
    df -h / | while read -r line; do log_info "$line"; done
    log_info "Memory Usage:"
    free -h | while read -r line; do log_info "$line"; done
}

run_security_audit() {
    print_section "Security Audit"
    log_info "Running security audit with Lynis..."
    if command_exists lynis; then
        local audit_log="/var/log/lynis_audit_$(date +%Y%m%d%H%M%S).log"
        if lynis audit system --quiet | tee "$audit_log"; then
            log_info "Lynis audit completed. Log saved to $audit_log."
        else
            log_warn "Lynis audit encountered issues."
        fi
    else
        log_warn "Lynis is not installed; skipping security audit."
    fi
}

check_services() {
    print_section "Service Status Check"
    log_info "Checking status of key services..."
    local services=("ssh" "ufw" "cron" "caddy" "ntp")
    for service_name in "${services[@]}"; do
        if systemctl is-active --quiet "$service_name"; then
            log_info "Service $service_name is running."
        else
            log_warn "Service $service_name is not running; attempting restart..."
            if systemctl restart "$service_name"; then
                log_info "Service $service_name restarted successfully."
            else
                log_error "Failed to restart service $service_name."
            fi
        fi
    done
}

verify_firewall_rules() {
    print_section "Firewall Rules Verification"
    log_info "Verifying firewall rules..."
    local ports=(22 80 443 32400)
    local host="127.0.0.1"
    for port in "${ports[@]}"; do
        if nc -z -w3 "$host" "$port" 2>/dev/null; then
            log_info "Port $port on $host is accessible."
        else
            log_warn "Port $port on $host is not accessible. Check ufw rules."
        fi
    done
}

update_ssl_certificates() {
    print_section "SSL Certificates Update"
    log_info "Updating SSL/TLS certificates using certbot..."
    if ! command_exists certbot; then
        if apt install -y certbot; then
            log_info "certbot installed successfully."
        else
            log_warn "Failed to install certbot."
            return 1
        fi
    fi
    if certbot renew; then
        log_info "SSL certificates updated successfully."
    else
        log_warn "Failed to update SSL certificates with certbot. Please check configuration."
    fi
}

tune_system() {
    print_section "Performance Tuning"
    log_info "Applying performance tuning and system optimizations..."
    local sysctl_conf="/etc/sysctl.conf"
    [ -f "$sysctl_conf" ] && backup_file "$sysctl_conf"
    cat <<'EOF' >> "$sysctl_conf"
# Performance tuning settings for Ubuntu
net.core.somaxconn=128
net.ipv4.tcp_rmem=4096 87380 6291456
net.ipv4.tcp_wmem=4096 16384 4194304
EOF
    sysctl -w net.core.somaxconn=128
    sysctl -w net.ipv4.tcp_rmem="4096 87380 6291456"
    sysctl -w net.ipv4.tcp_wmem="4096 16384 4194304"
    log_info "Performance tuning applied. Review $sysctl_conf for details."
}

final_checks() {
    print_section "Final System Checks"
    log_info "Kernel version: $(uname -r)"
    log_info "System uptime: $(uptime -p)"
    log_info "Disk usage (root partition): $(df -h / | awk 'NR==2 {print $0}')"
    local mem_total mem_used mem_free
    read -r mem_total mem_used mem_free < <(free -h | awk '/^Mem:/{print $2, $3, $4}')
    log_info "Memory usage: Total: ${mem_total}, Used: ${mem_used}, Free: ${mem_free}"
    local cpu_model
    cpu_model=$(lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//')
    log_info "CPU: ${cpu_model}"
    log_info "Active network interfaces:"
    ip -brief address | while read -r iface; do
         log_info "  $iface"
    done
    local load_avg
    load_avg=$(awk '{print $1", "$2", "$3}' /proc/loadavg)
    log_info "Load averages (1, 5, 15 min): ${load_avg}"
}

home_permissions() {
    print_section "Home Directory Permissions"
    log_info "Setting ownership of ${USER_HOME} and its contents to ${USERNAME}..."
    if ! chown -R "$USERNAME:$USERNAME" "${USER_HOME}"; then
        handle_error "Failed to change ownership of ${USER_HOME}."
    fi
    log_info "Setting the setgid bit on all directories in ${USER_HOME}..."
    find "${USER_HOME}" -type d -exec chmod g+s {} \; || log_warn "Failed to set the setgid bit on some directories."
    if command_exists setfacl; then
        log_info "Applying default ACLs on ${USER_HOME}..."
        setfacl -R -d -m u:"$USERNAME":rwx "${USER_HOME}" || log_warn "Failed to apply default ACLs."
    else
        log_warn "setfacl not found; skipping default ACL configuration."
    fi
    log_info "Home directory permissions updated."
}

#--------------------------------------------------
# Wi‑Fi Network Configuration
#--------------------------------------------------
configure_wifi() {
    print_section "Wi‑Fi Configuration"
    log_info "Configuring Wi‑Fi interfaces..."
    local devices
    devices=$(iw dev | awk '$1=="Interface"{print $2}')
    if [ -z "$devices" ]; then
        log_error "No wireless adapters detected."
        return 1
    fi
    for device in $devices; do
        log_info "Bringing up wireless interface: $device"
        if ip link set "$device" up; then
            log_info "Interface $device is up."
        else
            log_warn "Failed to bring up interface $device."
        fi
    done
    local primary_iface
    primary_iface=$(echo "$devices" | head -n 1)
    local ssid psk
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        if [ -z "$WIFI_SSID" ]; then
            log_error "Non-interactive mode: Wi‑Fi SSID not provided."
            return 1
        fi
        ssid="$WIFI_SSID"
        psk="$WIFI_PSK"
        log_info "Using provided Wi‑Fi credentials for interface $primary_iface."
    else
        read -r -p "Enter SSID for primary Wi‑Fi ($primary_iface): " ssid
        if [ -z "$ssid" ]; then
            log_error "SSID cannot be empty."
            return 1
        fi
        read -s -r -p "Enter PSK (leave empty for open networks): " psk
        echo
    fi
    local wpa_conf="/etc/wpa_supplicant.conf"
    if [ ! -f "$wpa_conf" ]; then
        touch "$wpa_conf" && chmod 600 "$wpa_conf"
        log_info "Created $wpa_conf with secure permissions."
    else
        backup_file "$wpa_conf"
    fi
    if grep -q "ssid=\"$ssid\"" "$wpa_conf"; then
        log_info "Network '$ssid' is already configured in $wpa_conf."
    else
        log_info "Adding network '$ssid' configuration to $wpa_conf."
        {
            echo "network={"
            echo "    ssid=\"$ssid\""
            if [ -n "$psk" ]; then
                echo "    psk=\"$psk\""
            else
                echo "    key_mgmt=NONE"
            fi
            echo "}"
        } >> "$wpa_conf"
    fi
    if ip link set "$primary_iface" down && ip link set "$primary_iface" up; then
        log_info "Restarted interface $primary_iface."
    else
        log_error "Failed to restart interface $primary_iface."
        return 1
    fi
    log_info "Wi‑Fi configuration completed for all detected devices."
}

#--------------------------------------------------
# Prompt for Reboot
#--------------------------------------------------
prompt_reboot() {
    print_section "Reboot Prompt"
    if [ "$NO_REBOOT" -eq 1 ]; then
        log_info "Reboot prompt suppressed (no-reboot flag set). Please reboot later."
        return
    fi
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        log_info "Non-interactive mode; skipping reboot prompt."
        return
    fi
    read -rp "Would you like to reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_info "Rebooting system now..."
        shutdown -r now
    else
        log_info "Reboot canceled. Please remember to reboot later for all changes to take effect."
    fi
}

#--------------------------------------------------
# Main Execution Flow
#--------------------------------------------------
main() {
    parse_args "$@"
    check_root
    check_network

    update_system
    install_packages

    configure_timezone
    configure_ntp

    setup_repos
    copy_shell_configs
    set_bash_shell

    configure_ssh
    setup_sudoers
    configure_firewall

    install_plex
    caddy_config
    install_fastfetch

    install_configure_zfs
    docker_config

    install_zig_binary
    install_ly
    install_xfce_desktop

    enable_dunamismax_services
    deploy_user_scripts
    dotfiles_load

    configure_periodic

    backup_configs
    backup_databases
    rotate_logs

    system_health_check
    run_security_audit
    check_services
    verify_firewall_rules
    update_ssl_certificates
    tune_system

    final_checks
    home_permissions

    configure_wifi

    prompt_reboot
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"