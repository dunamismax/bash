#!/usr/bin/env bash
################################################################################
# Debian Automated Setup Script
################################################################################
# Description:
#   This script automates the configuration of a fresh Debian server system,
#   creating a secure, optimized, and personalized environment. Key features include:
#     • System updates/upgrades and package installation.
#     • Secure SSH configuration and UFW firewall setup.
#     • Installation and configuration of essential security tools (fail2ban),
#       build dependencies, and various optional services (Caddy, Plex Media Server,
#       VSCode CLI).
#     • Repository and dotfiles setup for a personalized development environment.
#     • Final system cleanup and logging of system information.
#
# Usage:
#   Run as root (or with sudo). Customize configuration variables (e.g., USERNAME,
#   PACKAGES) as needed. All actions and errors are logged to /var/log/debian_setup.log.
#
# Compatibility:
#   Designed for Debian. Adjust as needed for your specific Debian version.
#
# Author: dunamismax | License: MIT
# Repository: https://github.com/dunamismax/bash
################################################################################

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# Environment Setup
# ------------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive

# ------------------------------------------------------------------------------
# Configuration Variables
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/debian_setup.log"  # Log file path
USERNAME="sawyer"                     # Default username to configure (change as needed)

# Define packages to install (adjusted for Debian; removed Ubuntu-specific packages)
PACKAGES=(
  bash vim nano mc screen tmux nodejs npm ninja-build meson fonts-font-awesome intltool gettext
  build-essential cmake hugo pigz exim4 openssh-server libtool pkg-config libssl-dev rfkill linux-headers-amd64
  bzip2 libbz2-dev libffi-dev zlib1g-dev libreadline-dev libsqlite3-dev tk-dev iw fonts-hack stable-backports
  xz-utils libncurses5-dev python3 python3-dev python3-pip python3-venv libfreetype6-dev flatpak zfsutils-linux
  xfce4-dev-tools git ufw perl curl wget tcpdump rsync htop passwd bash-completion neofetch tig jq gdisk vnstat
  fonts-dejavu-core fonts-firacode nmap tree fzf lynx which patch smartmontools ntfs-3g cups neovim debootstrap
  libglib2.0-dev qemu-kvm libvirt-daemon-system libvirt-clients virtinst bridge-utils acpid policykit-1
  papirus-icon-theme chrony fail2ban ffmpeg restic fonts-dejavu flameshot libxfce4ui-2-dev libxfce4util-dev
  libgtk-3-dev libpolkit-gobject-1-dev gnome-keyring seahorse thunar dmenu i3 i3status feh alacritty picom
)

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'      # For error messages
YELLOW='\033[38;2;235;203;139m'   # For warnings/labels
GREEN='\033[38;2;163;190;140m'    # For success/info
BLUE='\033[38;2;94;129;172m'      # For debug/highlights
CYAN='\033[38;2;136;192;208m'     # For headings/accent
GRAY='\033[38;2;216;222;233m'     # Light gray text
NC='\033[0m'                    # Reset color

# ------------------------------------------------------------------------------
# Logging Function
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color

    case "${level^^}" in
        INFO)
            color="${GREEN}" ;;
        WARN|WARNING)
            color="${YELLOW}" ;;
        ERROR)
            color="${RED}" ;;
        DEBUG)
            color="${BLUE}" ;;
        *)
            color="${NC}" ;;
    esac

    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# Error Handling Function
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An error occurred. Check the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# Progress Bar Function
# ------------------------------------------------------------------------------
progress_bar() {
    # Usage: progress_bar "Message" duration_in_seconds
    local message="$1"
    local duration="${2:-3}"
    local steps=50
    local sleep_time
    sleep_time=$(echo "$duration / $steps" | bc -l)
    printf "\n${CYAN}%s [" "$message"
    for ((i=1; i<=steps; i++)); do
        printf "█"
        sleep "$sleep_time"
    done
    printf "]${NC}\n"
}

# ------------------------------------------------------------------------------
# Initial Checks and Setup
# ------------------------------------------------------------------------------
# Ensure script is run as root
if [[ $(id -u) -ne 0 ]]; then
    handle_error "This script must be run as root. Please use sudo."
fi

# Ensure log directory exists and is writable
LOG_DIR=$(dirname "$LOG_FILE")
if [[ ! -d "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
fi
touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
chmod 600 "$LOG_FILE"

# Check network connectivity
if ! ping -c 1 google.com &>/dev/null; then
    handle_error "No network connectivity. Please check your network settings."
fi

# ------------------------------------------------------------------------------
# Function: Initial System Update and Upgrade
# ------------------------------------------------------------------------------
initial_system_update() {
    log INFO "Starting system update and upgrade..."
    progress_bar "Updating package repositories" 5
    apt update || handle_error "Failed to update package repositories."
    progress_bar "Upgrading installed packages" 10
    apt upgrade -y || handle_error "Failed to upgrade packages."
    log INFO "System update and upgrade completed successfully."
}

# ------------------------------------------------------------------------------
# Function: Configure SSH for Security
# ------------------------------------------------------------------------------
configure_ssh() {
    log INFO "Configuring OpenSSH Server..."
    if ! dpkg -l | grep -qw openssh-server; then
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log INFO "OpenSSH Server installed."
    else
        log INFO "OpenSSH Server already installed."
    fi

    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."

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

    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log INFO "SSH configuration updated successfully."
}

# ------------------------------------------------------------------------------
# Function: Install Essential Packages
# ------------------------------------------------------------------------------
install_packages() {
    log INFO "Installing essential packages..."
    apt update || handle_error "Failed to update package repositories."
    apt upgrade -y || handle_error "Failed to upgrade packages."

    local to_install=()
    for pkg in "${PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            to_install+=("$pkg")
        else
            log INFO "Package $pkg is already installed."
        fi
    done

    if [ ${#to_install[@]} -gt 0 ]; then
        log INFO "Installing packages: ${to_install[*]}"
        progress_bar "Installing packages" 10
        apt install -y "${to_install[@]}" || handle_error "Failed to install packages."
    else
        log INFO "All essential packages are already installed."
    fi
}

# ------------------------------------------------------------------------------
# Function: Configure UFW Firewall
# ------------------------------------------------------------------------------
configure_ufw() {
    log INFO "Configuring UFW firewall..."
    systemctl enable ufw || handle_error "Failed to enable UFW."
    systemctl start ufw || handle_error "Failed to start UFW."
    ufw --force enable || handle_error "Failed to activate UFW."

    local rules=(
        "allow ssh"
        "allow http"
        "allow https"
        "allow 32400/tcp"  # Plex Media Server
    )
    for rule in "${rules[@]}"; do
        ufw $rule || log WARN "Could not apply UFW rule: $rule"
        log INFO "Applied UFW rule: $rule"
    done

    log INFO "UFW firewall configuration completed."
}

# ------------------------------------------------------------------------------
# Function: Force Release Occupied Ports
# ------------------------------------------------------------------------------
release_ports() {
    log INFO "Releasing occupied network ports..."
    local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
    local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")

    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on TCP port $port: $pids"
            kill -9 $pids || log WARN "Failed to kill processes on TCP port $port"
        fi
    done

    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on UDP port $port: $pids"
            kill -9 $pids || log WARN "Failed to kill processes on UDP port $port"
        fi
    done

    log INFO "Port release process completed."
}

# ------------------------------------------------------------------------------
# Function: Install and Configure Fail2ban
# ------------------------------------------------------------------------------
configure_fail2ban() {
    log INFO "Installing and configuring fail2ban..."
    if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
        apt install -y fail2ban || handle_error "Failed to install fail2ban."
        log INFO "fail2ban installed successfully."
    else
        log INFO "fail2ban is already installed."
    fi

    systemctl enable fail2ban || handle_error "Failed to enable fail2ban."
    systemctl start fail2ban || handle_error "Failed to start fail2ban."
    log INFO "fail2ban configured successfully."
}

# ------------------------------------------------------------------------------
# Function: Install Build Dependencies (Python, C/C++, Rust, Go)
# ------------------------------------------------------------------------------
install_build_dependencies() {
    log INFO "Installing build dependencies..."
    apt update || handle_error "Failed to update repositories."
    apt upgrade -y || handle_error "Failed to upgrade packages."

    local deps=(
        build-essential make gcc g++ clang cmake git curl wget vim tmux unzip zip
        ca-certificates software-properties-common apt-transport-https gnupg lsb-release
        jq pkg-config libssl-dev libbz2-dev libffi-dev zlib1g-dev libreadline-dev
        libsqlite3-dev tk-dev libncurses5-dev libncursesw5-dev libgdbm-dev libnss3-dev
        liblzma-dev xz-utils libxml2-dev libxmlsec1-dev gdb llvm
    )
    progress_bar "Installing build dependencies" 10
    apt install -y --no-install-recommends "${deps[@]}" || handle_error "Failed to install build dependencies."

    log INFO "Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || handle_error "Rust toolchain installation failed."
    export PATH="$HOME/.cargo/bin:$PATH"
    log INFO "Rust toolchain installed successfully."

    log INFO "Installing Go..."
    apt install -y golang-go || handle_error "Failed to install Go."
    log INFO "Build dependencies installed successfully."
}

# ------------------------------------------------------------------------------
# Function: Install and Configure Caddy Web Server
# ------------------------------------------------------------------------------
install_caddy() {
    log INFO "Installing Caddy web server..."
    # For Debian, use debian-archive-keyring instead of ubuntu-keyring.
    apt install -y debian-archive-keyring apt-transport-https curl || handle_error "Failed to install prerequisites for Caddy."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
        || handle_error "Failed to add Caddy GPG key."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list || handle_error "Failed to add Caddy repository."
    apt update || handle_error "Failed to update repositories after adding Caddy repository."
    apt install -y caddy || handle_error "Failed to install Caddy."
    log INFO "Caddy web server installed successfully."
}

# ------------------------------------------------------------------------------
# Function: Install and Enable Plex Media Server
# ------------------------------------------------------------------------------
install_plex() {
    log INFO "Installing Plex Media Server..."
    if dpkg -s plexmediaserver >/dev/null 2>&1; then
        log INFO "Plex Media Server is already installed."
        return
    fi

    apt install -y curl || handle_error "Failed to install curl for Plex."
    local VERSION="1.41.3.9314-a0bfb8370"
    local DEB_PACKAGE="plexmediaserver_${VERSION}_amd64.deb"
    local DEB_URL="https://downloads.plex.tv/plex-media-server-new/${VERSION}/debian/${DEB_PACKAGE}"
    progress_bar "Downloading Plex package" 10
    curl -LO "${DEB_URL}" || handle_error "Failed to download Plex package."
    progress_bar "Installing Plex" 10
    dpkg -i "${DEB_PACKAGE}" || { apt install -f -y && dpkg -i "${DEB_PACKAGE}" || handle_error "Failed to install Plex Media Server."; }
    dpkg --configure -a || log WARN "Some packages failed to configure; continuing..."
    systemctl enable plexmediaserver || handle_error "Failed to enable Plex service."
    systemctl start plexmediaserver || handle_error "Failed to start Plex service."
    log INFO "Plex Media Server installed and running successfully."
}

# ------------------------------------------------------------------------------
# Function: Install Visual Studio Code CLI
# ------------------------------------------------------------------------------
install_vscode_cli() {
    log INFO "Installing Visual Studio Code CLI..."
    if [ -e "/usr/local/node" ]; then
        rm -f "/usr/local/node" || handle_error "Failed to remove existing /usr/local/node."
    fi
    ln -s "$(which node)" /usr/local/node || handle_error "Failed to create symbolic link for Node.js."
    progress_bar "Downloading VSCode CLI" 10
    curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz \
        || handle_error "Failed to download VSCode CLI."
    tar -xf vscode_cli.tar.gz || handle_error "Failed to extract VSCode CLI."
    rm -f vscode_cli.tar.gz || log WARN "Failed to remove VSCode CLI tarball."
    log INFO "Visual Studio Code CLI installed successfully. Run './code tunnel --name debian-server' to start the tunnel."
}

# ------------------------------------------------------------------------------
# Function: Setup Repositories and Dotfiles
# ------------------------------------------------------------------------------
setup_repos_and_dotfiles() {
    log INFO "Setting up GitHub repositories and dotfiles..."
    local GITHUB_DIR="/home/${USERNAME}/github"
    local USER_HOME="/home/${USERNAME}"
    mkdir -p "$GITHUB_DIR" || handle_error "Failed to create GitHub directory: $GITHUB_DIR"
    cd "$GITHUB_DIR" || handle_error "Failed to change directory to $GITHUB_DIR"

    local repos=("bash" "c" "religion" "windows" "hugo" "python")
    for repo in "${repos[@]}"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        local repo_url="https://github.com/dunamismax/${repo}.git"
        rm -rf "$repo_dir" 2>/dev/null
        git clone "$repo_url" "$repo_dir" || handle_error "Failed to clone repository: $repo"
        log INFO "Cloned repository: $repo"
    done

    # Configure permissions for Hugo directories
    local HUGO_PUBLIC_DIR="${GITHUB_DIR}/hugo/dunamismax.com/public"
    local HUGO_DIR="${GITHUB_DIR}/hugo"
    if [[ -d "$HUGO_PUBLIC_DIR" ]]; then
        chown -R www-data:www-data "$HUGO_PUBLIC_DIR" || handle_error "Failed to set ownership for Hugo public directory."
        chmod -R 755 "$HUGO_PUBLIC_DIR" || handle_error "Failed to set permissions for Hugo public directory."
    else
        log WARN "Hugo public directory not found: $HUGO_PUBLIC_DIR"
    fi

    if [[ -d "$HUGO_DIR" ]]; then
        chown -R caddy:caddy "$HUGO_DIR" || handle_error "Failed to set ownership for Hugo directory."
        chmod o+rx "$USER_HOME" "$GITHUB_DIR" "$HUGO_DIR" "${HUGO_DIR}/dunamismax.com" \
            || handle_error "Failed to set permissions for Hugo directory."
    else
        log WARN "Hugo directory not found: $HUGO_DIR"
    fi

    for repo in bash c python religion windows; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for repository: $repo"
        else
            log WARN "Repository directory not found: $repo_dir"
        fi
    done

    # Make all .sh files executable
    find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} + || handle_error "Failed to set executable permissions for .sh files."

    # Secure .git directories
    local DIR_PERMISSIONS="700"
    local FILE_PERMISSIONS="600"
    while IFS= read -r -d '' git_dir; do
        chmod "$DIR_PERMISSIONS" "$git_dir" || handle_error "Failed to set permissions for $git_dir"
        find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} + || handle_error "Failed to set directory permissions for $git_dir"
        find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} + || handle_error "Failed to set file permissions for $git_dir"
    done < <(find "$GITHUB_DIR" -type d -name ".git" -print0)

    # Load dotfiles from repository
    local dotfiles_dir="${USER_HOME}/github/bash/linux/dotfiles"
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    local config_dir="${USER_HOME}/.config"
    local local_bin_dir="${USER_HOME}/.local/bin"
    mkdir -p "$config_dir" "$local_bin_dir" || handle_error "Failed to create config directories."

    for file in .bashrc .profile .fehbg; do
        cp "${dotfiles_dir}/${file}" "${USER_HOME}/${file}" || log WARN "Failed to copy ${file}."
    done

    cp "${dotfiles_dir}/Caddyfile" /etc/caddy/Caddyfile || handle_error "Failed to copy Caddyfile."
    for dir in i3 i3status alacritty picom; do
        cp -r "${dotfiles_dir}/${dir}" "$config_dir/" || log WARN "Failed to copy configuration directory: $dir"
    done

    cp -r "${dotfiles_dir}/bin" "$local_bin_dir" || log WARN "Failed to copy bin directory."

    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME" || handle_error "Failed to set ownership for $USER_HOME."
    chown caddy:caddy /etc/caddy/Caddyfile || handle_error "Failed to set ownership for Caddyfile."
    chmod -R u=rwX,g=rX,o=rX "$local_bin_dir" || handle_error "Failed to set permissions for $local_bin_dir."

    log INFO "Repositories and dotfiles setup completed successfully."
    cd ~ || handle_error "Failed to return to home directory."
}

# ------------------------------------------------------------------------------
# Function: Finalize System Configuration and Cleanup
# ------------------------------------------------------------------------------
finalize_configuration() {
    log INFO "Finalizing system configuration..."
    cd "/home/${USERNAME}" || handle_error "Failed to change to user home directory."

    # Add Flatpak flathub repository if not present
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo \
        || handle_error "Failed to add Flatpak flathub repository."

    apt update && apt upgrade -y || handle_error "Failed to upgrade packages during finalization."
    flatpak update -y || handle_error "Failed to update Flatpak applications."

    # Remove Snap handling (not applicable for Debian)
    log INFO "Skipping Snap refresh on Debian."

    apt clean || handle_error "Failed to clean package cache."

    # ------------------------------------------------------------------------------
    # Log System Information
    # ------------------------------------------------------------------------------
    log INFO "Collecting system information..."
    log INFO "Uptime: $(uptime -p)"
    log INFO "Disk Usage (root): $(df -h / | tail -1)"
    log INFO "Memory Usage: $(free -h | grep Mem)"
    local cpu_model
    cpu_model=$(grep 'model name' /proc/cpuinfo | uniq | awk -F': ' '{print $2}')
    log INFO "CPU Model: ${cpu_model:-Unknown}"
    log INFO "Kernel Version: $(uname -r)"
    log INFO "Network Configuration:"
    ip addr show | sed "s/^/    /"
    log INFO "System information collection completed."
    log INFO "Finalization of system configuration complete."
}

# ------------------------------------------------------------------------------
# Function: Prompt for Reboot
# ------------------------------------------------------------------------------
prompt_reboot() {
    log INFO "Setup complete. A system reboot is recommended to apply all changes."
    read -p "Reboot now? (y/n): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot skipped. Please reboot manually when convenient."
    fi
}

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    log INFO "======================================"
    log INFO "Starting Debian Automated Setup Script"
    log INFO "======================================"

    initial_system_update
    configure_ssh
    install_packages
    configure_ufw
    release_ports
    configure_fail2ban
    install_build_dependencies
    install_plex
    install_vscode_cli
    install_caddy
    setup_repos_and_dotfiles
    finalize_configuration

    log INFO "Debian system setup completed successfully."
    prompt_reboot
}

# ------------------------------------------------------------------------------
# Execute Main if Script is Run Directly
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi