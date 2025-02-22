#!/usr/bin/env bash
# ==============================================================================
# Ubuntu Server Automation Script v6.0 (Master)
#
# Overview:
#   This master script automates initial configuration and hardening of an
#   Ubuntu system. It updates the system, installs essential packages,
#   configures time settings, SSH, firewall, and additional services such as
#   Plex, Caddy, ZFS, Docker, Zig/LY, XFCE, GitHub repositories, and various
#   custom services. It also includes backup, logging, periodic maintenance,
#   and system health functions.
#
# Usage:
#   Run as root.
#
# Disclaimer:
#   THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY. USE AT YOUR OWN RISK.
#
# Author: dunamismax (rewritten and improved)
# Version: 6.0
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

# Terminal color definitions (Nord theme)
readonly NORD9='\033[38;2;129;161;193m'    # Debug messages
readonly NORD10='\033[38;2;94;129;172m'
readonly NORD11='\033[38;2;191;97;106m'      # Error messages
readonly NORD13='\033[38;2;235;203;139m'     # Warning messages
readonly NORD14='\033[38;2;163;190;140m'     # Info messages
readonly NC='\033[0m'                        # Reset

# Ensure log directory exists with secure permissions
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
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
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
    log_error "Error at line ${BASH_LINENO[0]:-${LINENO}} in function ${FUNCNAME[1]:-main}."
    exit "$code"
}
trap 'handle_error "An unexpected error occurred at line ${LINENO}."' ERR

cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Place any cleanup commands here.
}
trap cleanup EXIT

#--------------------------------------------------
# Utility Functions
#--------------------------------------------------
command_exists() {
    command -v "$1" &>/dev/null
}

backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup="${file}.bak.$(date +%Y%m%d%H%M%S)"
        if cp -a "$file" "$backup"; then
            log_info "Backed up $file to $backup"
        else
            log_warn "Failed to backup $file"
        fi
    else
        log_warn "File $file not found; skipping backup."
    fi
}

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

#--------------------------------------------------
# Pre-requisites and System Checks
#--------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

check_network() {
    print_section "Network Connectivity Check"
    log_info "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com &>/dev/null; then
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
    apt update -qq || handle_error "Failed to update package repositories."
    log_info "Upgrading system packages..."
    apt upgrade -y || handle_error "Failed to upgrade packages."
    log_info "System update and upgrade complete."
}

install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    apt install -y "${PACKAGES[@]}" || handle_error "Failed to install one or more packages."
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
# Minimal NTP configuration
server 0.pool.ntp.org iburst
server 1.pool.ntp.org iburst
server 2.pool.ntp.org iburst
server 3.pool.ntp.org iburst
EOF
        log_info "Created new NTP configuration at $ntp_conf."
    else
        log_info "NTP configuration exists at $ntp_conf."
    fi
    systemctl enable ntp
    systemctl restart ntp && log_info "NTP service restarted successfully." || log_warn "Failed to restart NTP service."
}

#--------------------------------------------------
# Repository and Shell Setup
#--------------------------------------------------
setup_repos() {
    print_section "GitHub Repositories Setup"
    log_info "Setting up GitHub repositories for user '$USERNAME'..."
    local GH_DIR="/home/${USERNAME}/github"
    mkdir -p "$GH_DIR" || handle_error "Failed to create GitHub directory at $GH_DIR."
    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"
        [ -d "$REPO_DIR" ] && { log_info "Removing existing repository '$repo' directory..."; rm -rf "$REPO_DIR"; }
        log_info "Cloning repository '$repo' into '$REPO_DIR'..."
        git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR" && \
            log_info "Repository '$repo' cloned successfully." || log_warn "Failed to clone repository '$repo'."
    done
    chown -R "$USERNAME:$USERNAME" "$GH_DIR" && log_info "Ownership of '$GH_DIR' set to '$USERNAME'."
}

copy_shell_configs() {
    print_section "Shell Configuration Update"
    local source_dir="/home/${USERNAME}/github/bash/linux/dotfiles"
    local dest_dir="/home/${USERNAME}"
    for file in ".bashrc" ".profile"; do
        local src="${source_dir}/${file}"
        local dest="${dest_dir}/${file}"
        if [ -f "$src" ]; then
            log_info "Copying ${src} to ${dest}..."
            cp -f "$src" "$dest" && chown "${USERNAME}:${USERNAME}" "$dest" || log_warn "Failed to copy ${src}."
        else
            log_warn "Source file ${src} not found; skipping."
        fi
    done
    # Source the updated .bashrc if available
    [ -f "${dest_dir}/.bashrc" ] && { log_info "Sourcing ${dest_dir}/.bashrc..."; source "${dest_dir}/.bashrc"; } || \
        log_warn "No .bashrc found in ${dest_dir}; skipping source."
}

set_bash_shell() {
    print_section "Default Shell Configuration"
    if ! command_exists bash; then
        log_info "Bash not found; installing..."
        apt install -y bash || { log_warn "Bash installation failed."; return 1; }
    fi
    grep -qxF "/bin/bash" /etc/shells || echo "/bin/bash" >> /etc/shells && log_info "Added /bin/bash to /etc/shells."
    chsh -s /bin/bash "$USERNAME" && log_info "Default shell for ${USERNAME} set to /bin/bash." || \
        log_warn "Failed to set default shell for ${USERNAME}."
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
        log_info "OpenSSH Server installed."
    fi
    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."
    local sshd_config="/etc/ssh/sshd_config"
    [ -f "$sshd_config" ] || handle_error "SSHD configuration file not found: $sshd_config"
    backup_file "$sshd_config"
    declare -A ssh_settings=(
        [Port]=22
        [PermitRootLogin]="no"
        [PasswordAuthentication]="yes"
        [PermitEmptyPasswords]="no"
        [ChallengeResponseAuthentication]="no"
        [Protocol]=2
        [MaxAuthTries]=5
        [ClientAliveInterval]=600
        [ClientAliveCountMax]=48
    )
    for key in "${!ssh_settings[@]}"; do
        if grep -qE "^${key}[[:space:]]" "$sshd_config"; then
            sed -i "s/^${key}[[:space:]].*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done
    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log_info "SSH configuration updated."
}

setup_sudoers() {
    print_section "Sudo Configuration"
    log_info "Ensuring user ${USERNAME} has sudo privileges..."
    if id -nG "$USERNAME" | grep -qw sudo; then
        log_info "User ${USERNAME} is already in the sudo group."
    else
        usermod -aG sudo "$USERNAME" && log_info "User ${USERNAME} added to sudo group." || \
            log_warn "Failed to add ${USERNAME} to sudo group."
    fi
}

#--------------------------------------------------
# Firewall (UFW) Configuration
#--------------------------------------------------
configure_firewall() {
    print_section "Firewall Configuration"
    log_info "Configuring firewall with ufw..."
    local ufw_cmd="/usr/sbin/ufw"
    [ -x "$ufw_cmd" ] || handle_error "ufw command not found. Please install ufw."
    "$ufw_cmd" default deny incoming || log_warn "Failed to set default deny incoming."
    "$ufw_cmd" default allow outgoing || log_warn "Failed to set default allow outgoing."
    "$ufw_cmd" allow 22/tcp || log_warn "Failed to allow SSH."
    "$ufw_cmd" allow 80/tcp || log_warn "Failed to allow HTTP."
    "$ufw_cmd" allow 443/tcp || log_warn "Failed to allow HTTPS."
    "$ufw_cmd" allow 32400/tcp || log_warn "Failed to allow Plex port."
    "$ufw_cmd" --force enable || handle_error "Failed to enable ufw firewall."
    systemctl enable ufw || log_warn "Failed to enable ufw service."
    systemctl start ufw || log_warn "Failed to start ufw service."
    log_info "Firewall configured and enabled."
}

#--------------------------------------------------
# Service Installation and Configuration
#--------------------------------------------------
install_plex() {
    print_section "Plex Media Server Installation"
    log_info "Installing Plex Media Server..."
    command_exists curl || handle_error "curl is required but not installed."
    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    local temp_deb="/tmp/plexmediaserver.deb"
    curl -L -o "$temp_deb" "$plex_url" || handle_error "Failed to download Plex Media Server .deb file."
    dpkg -i "$temp_deb" || {
        log_warn "dpkg encountered issues. Attempting to fix missing dependencies..."
        apt install -f -y || handle_error "Failed to install dependencies for Plex."
    }
    local plex_conf="/etc/default/plexmediaserver"
    if [ -f "$plex_conf" ]; then
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$plex_conf" \
            && log_info "Configured Plex to run as ${USERNAME}." || log_warn "Failed to set Plex user in $plex_conf"
    else
        log_warn "$plex_conf not found; skipping user configuration."
    fi
    systemctl enable plexmediaserver || log_warn "Failed to enable Plex service."
    rm -f "$temp_deb"
    log_info "Plex Media Server installed successfully."
}

caddy_config() {
    print_section "Caddy Configuration"
    log_info "Releasing occupied network ports..."
    local tcp_ports=(80 443 8080 32400 8324 32469)
    local udp_ports=(80 443 1900 5353 32410 32411 32412 32413 32414 32415)
    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        [ -n "$pids" ] && { log_info "Killing processes on TCP port $port: $pids"; kill -9 $pids || log_warn "Failed to kill processes on TCP port $port"; }
    done
    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        [ -n "$pids" ] && { log_info "Killing processes on UDP port $port: $pids"; kill -9 $pids || log_warn "Failed to kill processes on UDP port $port"; }
    done
    log_info "Installing dependencies for Caddy..."
    apt install -y debian-keyring debian-archive-keyring apt-transport-https curl || \
        handle_error "Failed to install dependencies for Caddy."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg || \
        handle_error "Failed to add Caddy GPG key."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
        tee /etc/apt/sources.list.d/caddy-stable.list || handle_error "Failed to add Caddy repository."
    apt update || handle_error "Failed to update package lists."
    apt install -y caddy || handle_error "Failed to install Caddy."
    log_info "Caddy installed successfully."
    local custom_caddyfile="/home/${USERNAME}/github/linux/dotfiles/Caddyfile"
    local dest_caddyfile="/etc/caddy/Caddyfile"
    if [ -f "$custom_caddyfile" ]; then
        cp -f "$custom_caddyfile" "$dest_caddyfile" && log_info "Copied custom Caddyfile." || log_warn "Failed to copy custom Caddyfile."
    else
        log_warn "Custom Caddyfile not found at $custom_caddyfile."
    fi
    systemctl enable caddy || log_warn "Failed to enable Caddy service."
    systemctl restart caddy || log_warn "Failed to restart Caddy service."
    log_info "Caddy configuration completed."
}

install_fastfetch() {
    print_section "Fastfetch Installation"
    local fastfetch_url="https://github.com/fastfetch-cli/fastfetch/releases/download/2.36.1/fastfetch-linux-amd64.deb"
    local temp_deb="/tmp/fastfetch-linux-amd64.deb"
    curl -L -o "$temp_deb" "$fastfetch_url" || handle_error "Failed to download fastfetch deb file."
    dpkg -i "$temp_deb" || {
        log_warn "fastfetch installation issues; fixing dependencies..."
        apt install -f -y || handle_error "Failed to fix dependencies for fastfetch."
    }
    rm -f "$temp_deb"
    log_info "Fastfetch installed successfully."
}

install_configure_zfs() {
    print_section "ZFS Installation and Configuration"
    local zpool_name="WD_BLACK"
    local mount_point="/media/${zpool_name}"
    apt update || { log_error "Failed to update package lists."; return 1; }
    apt install -y dpkg-dev linux-headers-generic linux-image-generic || { log_error "Failed to install prerequisites."; return 1; }
    DEBIAN_FRONTEND=noninteractive apt install -y zfs-dkms zfsutils-linux || { log_error "Failed to install ZFS packages."; return 1; }
    systemctl enable zfs-import-cache.service || log_warn "Could not enable zfs-import-cache.service."
    systemctl enable zfs-mount.service || log_warn "Could not enable zfs-mount.service."
    if ! zpool list "$zpool_name" &>/dev/null; then
        zpool import -f "$zpool_name" && log_info "Imported ZFS pool '$zpool_name'." || { log_error "Failed to import ZFS pool '$zpool_name'."; return 1; }
    else
        log_info "ZFS pool '$zpool_name' is already imported."
    fi
    zfs set mountpoint="${mount_point}" "$zpool_name" && log_info "Mountpoint for pool '$zpool_name' set to '$mount_point'." || log_warn "Failed to set mountpoint for ZFS pool '$zpool_name'."
}

docker_config() {
    print_section "Docker Configuration"
    log_info "Installing Docker..."
    if command_exists docker; then
        log_info "Docker is already installed."
    else
        apt install -y docker.io || handle_error "Failed to install Docker."
        log_info "Docker installed successfully."
    fi
    if ! id -nG "$USERNAME" | grep -qw docker; then
        usermod -aG docker "$USERNAME" && log_info "Added user '$USERNAME' to docker group." || log_warn "Failed to add $USERNAME to docker group."
    fi
    mkdir -p /etc/docker || handle_error "Failed to create /etc/docker."
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
    log_info "Docker is running."
    if ! command_exists docker-compose; then
        local version="2.20.2"
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
    local zig_version="0.12.1"
    local zig_tarball_url="https://ziglang.org/download/${zig_version}/zig-linux-x86_64-${zig_version}.tar.xz"
    local zig_install_dir="/opt/zig"
    local temp_download="/tmp/zig.tar.xz"
    apt install -y curl tar || handle_error "Failed to install required dependencies."
    curl -L -o "${temp_download}" "${zig_tarball_url}" || handle_error "Failed to download Zig binary."
    rm -rf "${zig_install_dir}"
    mkdir -p "${zig_install_dir}" || handle_error "Failed to create ${zig_install_dir}."
    tar -xf "${temp_download}" -C "${zig_install_dir}" --strip-components=1 || handle_error "Failed to extract Zig binary."
    ln -sf "${zig_install_dir}/zig" /usr/local/bin/zig || handle_error "Failed to create symlink for Zig."
    rm -f "${temp_download}"
    if command_exists zig; then
        log_info "Zig installed successfully! Version: $(zig version)"
    else
        handle_error "Zig is not accessible from the command line."
    fi
}

install_ly() {
    print_section "Ly Display Manager Installation"
    for cmd in git zig systemctl; do
        command_exists "$cmd" || handle_error "'$cmd' is required but not installed."
    done
    apt update || handle_error "Failed to update package lists."
    apt install -y build-essential libpam0g-dev libxcb-xkb-dev libxcb-randr0-dev libxcb-xinerama0-dev libxcb-xrm-dev libxkbcommon-dev libxkbcommon-x11-dev \
        || handle_error "Failed to install Ly build dependencies."
    local ly_dir="/opt/ly"
    if [ ! -d "$ly_dir" ]; then
        git clone https://github.com/fairyglade/ly "$ly_dir" || handle_error "Failed to clone the Ly repository."
    else
        cd "$ly_dir" || handle_error "Failed to change directory to $ly_dir."
        git pull || handle_error "Failed to update the Ly repository."
    fi
    cd "$ly_dir" || handle_error "Failed to change directory to $ly_dir."
    zig build || handle_error "Compilation of Ly failed."
    zig build installsystemd || handle_error "Installation of Ly systemd service failed."
    for dm in gdm sddm lightdm lxdm; do
        systemctl is-enabled "${dm}.service" &>/dev/null && {
            systemctl disable --now "${dm}.service" && log_info "Disabled ${dm}.service." || handle_error "Failed to disable ${dm}.service."
        }
    done
    [ -L /etc/systemd/system/display-manager.service ] && rm /etc/systemd/system/display-manager.service && log_info "Removed display-manager.service symlink."
    systemctl enable ly.service || handle_error "Failed to enable ly.service."
    systemctl disable getty@tty2.service || handle_error "Failed to disable getty@tty2.service."
    log_info "Ly installed and configured as the default login manager."
}

install_xfce_desktop() {
    print_section "XFCE Desktop Installation"
    log_info "Installing XFCE desktop environment and addons..."
    local xfce_packages=(xfce4-session xfce4-panel xfce4-appfinder xfce4-settings xfce4-terminal xfdesktop xfwm4 thunar mousepad xfce4-whiskermenu-plugin)
    for pkg in "${xfce_packages[@]}"; do
        if dpkg -s "$pkg" &>/dev/null; then
            log_info "XFCE package '$pkg' is already installed."
        else
            apt install -y "$pkg" && log_info "Installed XFCE package: $pkg" || log_warn "Failed to install XFCE package: $pkg"
        fi
    done
    log_info "XFCE desktop installation complete."
}

deploy_user_scripts() {
    print_section "Deploying User Scripts"
    local script_source="/home/${USERNAME}/github/bash/linux/_scripts"
    local script_target="/home/${USERNAME}/bin"
    [ -d "$script_source" ] || handle_error "Source directory '$script_source' does not exist."
    [ -d "$script_target" ] || { mkdir -p "$script_target" && chown "${USERNAME}:${USERNAME}" "$script_target"; }
    rsync --dry-run -ah --delete "${script_source}/" "${script_target}/" || handle_error "Dry-run failed for script deployment."
    rsync -ah --delete "${script_source}/" "${script_target}/" || handle_error "Script deployment failed."
    find "${script_target}" -type f -exec chmod 755 {} \; || handle_error "Failed to update script permissions."
    log_info "User scripts deployed successfully."
}

dotfiles_load() {
    print_section "Loading Dotfiles"
    local config_base="/home/${USERNAME}/.config"
    declare -A dotfiles_dirs=(
        [alacritty]="/home/${USERNAME}/github/bash/linux/dotfiles/alacritty"
        [i3]="$(printf '%s\n' "/home/${USERNAME}/github/bash/linux/dotfiles/i3")"
        [i3blocks]="$(printf '%s\n' "/home/${USERNAME}/github/bash/linux/dotfiles/i3blocks")"
        [picom]="/home/${USERNAME}/github/bash/linux/dotfiles/picom"
    )
    for dir in "${!dotfiles_dirs[@]}"; do
        local src="${dotfiles_dirs[$dir]}"
        local dest="${config_base}/${dir}"
        mkdir -p "$dest"
        rsync -a --delete "$src/" "$dest/" && log_info "Loaded ${dir} configuration." || handle_error "Failed to copy ${dir} configuration."
    done
    chmod -R +x "/home/${USERNAME}/.config/i3blocks/scripts" || log_warn "Failed to set execute permissions on i3blocks scripts."
}

configure_periodic() {
    print_section "Periodic Maintenance Setup"
    local cron_file="/etc/cron.daily/ubuntu_maintenance"
    [ -f "$cron_file" ] && mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" && log_info "Existing cron file backed up."
    cat <<'EOF' > "$cron_file"
#!/bin/sh
# Ubuntu maintenance script
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
EOF
    chmod +x "$cron_file" && log_info "Daily maintenance script created at $cron_file." || log_warn "Failed to set execute permission on $cron_file."
}

backup_configs() {
    print_section "Configuration Backups"
    local backup_dir="/var/backups/ubuntu_config_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    for file in /etc/ssh/sshd_config /etc/ufw/user.rules /etc/ntp.conf; do
        [ -f "$file" ] && cp "$file" "$backup_dir" && log_info "Backed up $file" || log_warn "File $file not found; skipping."
    done
}

backup_databases() {
    print_section "Database Backups"
    local backup_dir="/var/backups/db_backups_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    if command_exists pg_dumpall; then
        pg_dumpall -U postgres | gzip > "$backup_dir/postgres_backup.sql.gz" && log_info "PostgreSQL backup completed." || log_warn "PostgreSQL backup failed."
    else
        log_warn "pg_dumpall not found; skipping PostgreSQL backup."
    fi
    if command_exists mysqldump; then
        mysqldump --all-databases | gzip > "$backup_dir/mysql_backup.sql.gz" && log_info "MySQL backup completed." || log_warn "MySQL backup failed."
    else
        log_warn "mysqldump not found; skipping MySQL backup."
    fi
}

rotate_logs() {
    print_section "Log Rotation"
    if [ -f "$LOG_FILE" ]; then
        local rotated_file="${LOG_FILE}.$(date +%Y%m%d%H%M%S).gz"
        gzip -c "$LOG_FILE" > "$rotated_file" && :> "$LOG_FILE" && log_info "Log rotated to $rotated_file." || log_warn "Log rotation failed."
    else
        log_warn "Log file $LOG_FILE does not exist."
    fi
}

system_health_check() {
    print_section "System Health Check"
    log_info "Uptime: $(uptime)"
    log_info "Disk Usage:"; df -h / | while read -r line; do log_info "$line"; done
    log_info "Memory Usage:"; free -h | while read -r line; do log_info "$line"; done
}

run_security_audit() {
    print_section "Security Audit"
    if command_exists lynis; then
        local audit_log="/var/log/lynis_audit_$(date +%Y%m%d%H%M%S).log"
        lynis audit system --quiet | tee "$audit_log" && log_info "Lynis audit completed. Log saved to $audit_log." || log_warn "Lynis audit encountered issues."
    else
        log_warn "Lynis not installed; skipping security audit."
    fi
}

verify_firewall_rules() {
    print_section "Firewall Rules Verification"
    for port in 22 80 443 32400; do
        nc -z -w3 127.0.0.1 "$port" &>/dev/null && log_info "Port $port is accessible." || log_warn "Port $port is not accessible. Check ufw rules."
    done
}

update_ssl_certificates() {
    print_section "SSL Certificates Update"
    if ! command_exists certbot; then
        apt install -y certbot && log_info "certbot installed successfully." || { log_warn "Failed to install certbot."; return 1; }
    fi
    certbot renew && log_info "SSL certificates updated successfully." || log_warn "Failed to update SSL certificates."
}

tune_system() {
    print_section "Performance Tuning"
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
    log_info "Performance tuning applied."
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
    log_info "Active network interfaces:"; ip -brief address | while read -r iface; do log_info "  $iface"; done
    local load_avg
    load_avg=$(awk '{print $1", "$2", "$3}' /proc/loadavg)
    log_info "Load averages (1, 5, 15 min): ${load_avg}"
}

home_permissions() {
    print_section "Home Directory Permissions"
    chown -R "$USERNAME:$USERNAME" "${USER_HOME}" && log_info "Ownership of ${USER_HOME} set to ${USERNAME}." || handle_error "Failed to change ownership of ${USER_HOME}."
    find "${USER_HOME}" -type d -exec chmod g+s {} \; || log_warn "Failed to set setgid bit on some directories."
    if command_exists setfacl; then
        setfacl -R -d -m u:"$USERNAME":rwx "${USER_HOME}" && log_info "Default ACLs applied on ${USER_HOME}." || log_warn "Failed to apply default ACLs."
    else
        log_warn "setfacl not found; skipping default ACL configuration."
    fi
}

#--------------------------------------------------
# Prompt for Reboot
#--------------------------------------------------
prompt_reboot() {
    print_section "Reboot Prompt"
    # In non-interactive environments, you might skip prompting.
    read -rp "Would you like to reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_info "Rebooting system now..."
        shutdown -r now
    else
        log_info "Reboot canceled. Please reboot later for all changes to take effect."
    fi
}

#--------------------------------------------------
# Main Execution Flow
#--------------------------------------------------
main() {
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

    deploy_user_scripts
    dotfiles_load

    configure_periodic

    backup_configs
    backup_databases
    rotate_logs

    system_health_check
    run_security_audit
    verify_firewall_rules
    update_ssl_certificates
    tune_system

    final_checks
    home_permissions

    prompt_reboot
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main