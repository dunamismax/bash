#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# FreeBSD Automated System Configuration Script
# ------------------------------------------------------------------------------
# Description:
#   Automates setup of a fresh FreeBSD system for a secure, optimized, and
#   personalized environment. Features include:
#     • System updates, backups, and user configuration.
#     • Installation of development tools, languages, and utilities.
#     • Secure SSH and PF firewall setup.
#     • GitHub repository cloning, VS Code CLI, and FiraCode font installation.
#     • Dotfiles deployment and directory permission management.
#     • Collection of system info and optional reboot.
#
# Usage:
#   Run as root (or via sudo). Adjust variables (e.g., USERNAME, PACKAGES)
#   as needed. Logs actions to /var/log/freebsd_setup.log.
#
# Author: dunamismax | License: MIT
# Repository: https://github.com/dunamismax/bash
# ------------------------------------------------------------------------------
 
# Enable strict error handling
set -Eeuo pipefail
 
# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
# FreeBSD home directory is typically /home/<username>
USER_HOME="/home/${USERNAME}"
 
# Set Bash as the default shell for the target user
set_shell() {
    log INFO "Setting Bash as the default shell for user $USERNAME..."
    if ! pw usermod "$USERNAME" -s /usr/local/bin/bash; then
        handle_error "Failed to set Bash as default shell for user $USERNAME."
    fi
    log INFO "Default shell set to Bash for user $USERNAME."
}
 
# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
 
    # Nord theme color definitions
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'
 
    # Choose color based on log level
    case "${level^^}" in
        INFO)  local color="${GREEN}" ;;
        WARN|WARNING) local color="${YELLOW}"; level="WARN" ;;
        ERROR) local color="${RED}" ;;
        DEBUG) local color="${BLUE}" ;;
        *)     local color="${NC}"; level="INFO" ;;
    esac
 
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "${color}%s${NC}\n" "$log_entry" >&2
}
 
# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    exit "$exit_code"
}
 
# Trap errors to log additional context
trap 'log ERROR "Script failed in function ${FUNCNAME[0]} at line $LINENO. See above for details."' ERR
 
# ------------------------------------------------------------------------------
# XDG BASE DIRECTORY SETUP
# ------------------------------------------------------------------------------
export XDG_CONFIG_HOME="${USER_HOME}/.config"
export XDG_DATA_HOME="${USER_HOME}/.local/share"
export XDG_CACHE_HOME="${USER_HOME}/.cache"
 
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" || \
    handle_error "Failed to create XDG directories."
log INFO "XDG directories configured:"
log INFO "  - XDG_CONFIG_HOME: $XDG_CONFIG_HOME"
log INFO "  - XDG_DATA_HOME: $XDG_DATA_HOME"
log INFO "  - XDG_CACHE_HOME: $XDG_CACHE_HOME"
 
# ------------------------------------------------------------------------------
# INITIAL CHECKS
# ------------------------------------------------------------------------------
if [[ $(id -u) -ne 0 ]]; then
    handle_error "This script must be run as root (e.g., sudo $0)."
fi
 
LOG_DIR=$(dirname "$LOG_FILE")
mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"
 
if ! ping -c 1 google.com &>/dev/null; then
    handle_error "No network connectivity. Please check your network settings."
fi
 
# ------------------------------------------------------------------------------
# SYSTEM UPDATE
# ------------------------------------------------------------------------------
initial_system_update() {
    log INFO "--------------------------------------"
    log INFO "Starting system update and upgrade..."
 
    log INFO "Updating pkg repositories..."
    pkg update -f || handle_error "Failed to update pkg repositories."
    log INFO "Upgrading installed packages..."
    pkg upgrade -y || handle_error "Failed to upgrade packages."
    log INFO "System update and upgrade completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# SYSTEM BACKUP
# ------------------------------------------------------------------------------
backup_system() {
    log INFO "--------------------------------------"
    log INFO "Starting system backup process..."
 
    if ! command -v rsync &>/dev/null; then
        log INFO "Installing rsync..."
        pkg install -y rsync || handle_error "Failed to install rsync."
    fi
 
    local SOURCE="/"
    local DESTINATION="${USER_HOME}/BACKUPS"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_FOLDER="${DESTINATION}/backup-${TIMESTAMP}"
    local RETENTION_DAYS=7
 
    local EXCLUDES=(
        "/dev/*" "/proc/*" "/tmp/*" "/var/tmp/*"
        "/var/run/*" "/var/log/*" "/var/cache/*"
        "/var/db/pkg/*" "/var/db/ports/*" "/var/db/portsnap/*"
        "/var/db/freebsd-update/*" "/mnt/*" "/media/*"
        "/swapfile" "/lost+found" "/root/.cache/*"
        "${DESTINATION}"
    )
 
    local EXCLUDES_ARGS=()
    for ex in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$ex")
    done
 
    mkdir -p "$BACKUP_FOLDER" || handle_error "Failed to create backup folder: $BACKUP_FOLDER"
    log INFO "Starting backup with rsync..."
    rsync -aAXv --stats "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER" || handle_error "Backup failed."
    log INFO "Backup completed successfully: $BACKUP_FOLDER"
 
    log INFO "Cleaning up backups older than ${RETENTION_DAYS} days..."
    find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} + \
        && log INFO "Old backups removed." \
        || log WARN "Some old backups could not be removed."
    log INFO "System backup process completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# SUDO ACCESS CONFIGURATION
# ------------------------------------------------------------------------------
configure_sudo_access() {
    log INFO "--------------------------------------"
    log INFO "Configuring sudo access for user: $USERNAME"
 
    if ! id "$USERNAME" &>/dev/null; then
        handle_error "User $USERNAME does not exist."
    fi
 
    log INFO "Adding $USERNAME to 'wheel' group..."
    pw usermod "$USERNAME" -G wheel || handle_error "Failed to add user to wheel group."
 
    if ! grep -q '^%wheel ALL=(ALL) ALL' /usr/local/etc/sudoers; then
        echo "%wheel ALL=(ALL) ALL" >> /usr/local/etc/sudoers || handle_error "Failed to update sudoers file."
        log INFO "Added 'wheel' group to sudoers."
    else
        log INFO "'wheel' group already present in sudoers."
    fi
    log INFO "Sudo access configured for user: $USERNAME"
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# PACKAGE INSTALLATION
# ------------------------------------------------------------------------------
install_pkgs() {
    log INFO "--------------------------------------"
    log INFO "Starting package installation..."
 
    pkg upgrade -y || handle_error "Package upgrade failed."
 
    PACKAGES=(
        gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja
        meson gettext gmake valgrind doxygen ccache diffutils alacritty node npm
        bash zsh fish nano screen tmate mosh htop iftop tree wget curl rsync
        unzip zip ca_root_nss sudo less neovim mc jq pigz fzf lynx smartmontools
        neofetch screenfetch ncdu dos2unix figlet toilet ripgrep python39 go ruby perl5
        rust docker vagrant qemu bhyve-firmware vm-bhyve nginx postgresql15-server
        postgresql15-client rclone syslog-ng grafana prometheus netdata lsof bsdstats
        lzip zstd fusefs-ntfs drm-kmod
    )
 
    log INFO "Installing packages: ${PACKAGES[*]}"
    pkg install -y "${PACKAGES[@]}" || handle_error "Failed to install packages."
 
    CRITICAL_PACKAGES=("bash" "sudo" "openssl" "python39" "git")
    for pkg in "${CRITICAL_PACKAGES[@]}"; do
        pkg info -q "$pkg" || handle_error "Critical package $pkg is missing."
    done
    log INFO "All packages installed successfully."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# SSH CONFIGURATION
# ------------------------------------------------------------------------------
configure_ssh_settings() {
    log INFO "--------------------------------------"
    log INFO "Starting SSH configuration..."
    local sshd_config="/usr/local/etc/ssh/sshd_config"
    local sshd_service="sshd"
    local pkg_name="openssh-portable"
    local TIMEOUT=30
    local retry_count=0
    local max_retries=3
 
    export LC_ALL=C
 
    if ! pkg info "$pkg_name" >/dev/null 2>&1; then
        while [ $retry_count -lt $max_retries ]; do
            log INFO "Installing OpenSSH Server (attempt $((retry_count+1))/$max_retries)..."
            pkg install -y "$pkg_name" && break
            retry_count=$((retry_count+1))
            [ $retry_count -lt $max_retries ] && sleep 5
        done
        [ $retry_count -eq $max_retries ] && handle_error "Failed to install OpenSSH Server after $max_retries attempts."
    else
        log INFO "OpenSSH Server is already installed."
    fi
 
    [ ! -d "/usr/local/etc/ssh" ] && mkdir -p "/usr/local/etc/ssh" && chmod 755 "/usr/local/etc/ssh"
 
    if [ -f "$sshd_config" ]; then
        local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$sshd_config" "$backup_file" || handle_error "Failed to backup sshd_config."
        log INFO "Backed up sshd_config to $backup_file"
    fi
 
    log INFO "Generating new SSH configuration..."
    local temp_file
    temp_file=$(mktemp) || handle_error "Failed to create temporary SSH config file."
    {
        printf "# SSH Configuration generated on %s\n\n" "$(date)"
        printf "Port 22\nProtocol 2\nAddressFamily inet\nListenAddress 0.0.0.0\n\n"
        printf "MaxAuthTries 3\nPermitRootLogin no\nPasswordAuthentication yes\n"
        printf "ChallengeResponseAuthentication no\nUsePAM no\nPubkeyAuthentication yes\n"
        printf "AuthenticationMethods publickey\n\n"
        printf "X11Forwarding no\nAllowTcpForwarding no\nPermitEmptyPasswords no\n"
        printf "MaxSessions 2\nLoginGraceTime 30\nAllowAgentForwarding no\nPermitTunnel no\nStrictModes yes\n\n"
        printf "ClientAliveInterval 300\nClientAliveCountMax 2\nTCPKeepAlive no\n\n"
        printf "LogLevel VERBOSE\nSyslogFacility AUTH\n"
    } > "$temp_file"
 
    chmod 600 "$temp_file" || handle_error "Failed to set permissions on SSH config."
    mv "$temp_file" "$sshd_config" || handle_error "Failed to install new SSH configuration."
 
    sysrc "${sshd_service}_enable=YES" || handle_error "Failed to enable SSH service in rc.conf."
    /usr/sbin/sshd -t -f "$sshd_config" || handle_error "SSH configuration test failed."
    service "$sshd_service" restart || handle_error "Failed to restart SSH service."
 
    retry_count=0
    while [ $retry_count -lt $TIMEOUT ]; do
        if service "$sshd_service" status >/dev/null 2>&1 && sockstat -4l | grep -q ":22"; then
            log INFO "SSH server is running on port 22."
            break
        fi
        retry_count=$((retry_count+1))
        sleep 1
    done
    [ $retry_count -eq $TIMEOUT ] && handle_error "SSH service failed to start within $TIMEOUT seconds."
 
    log INFO "SSH configuration completed successfully."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# PF FIREWALL CONFIGURATION
# ------------------------------------------------------------------------------
configure_pf() {
    log INFO "--------------------------------------"
    log INFO "Starting PF firewall configuration..."
 
    local PF_CONF="/etc/pf.conf"
    local BACKUP_CONF="/etc/pf.conf.bak.$(date +%Y%m%d%H%M%S)"
 
    if [[ -f "$PF_CONF" ]]; then
        log INFO "Backing up existing PF configuration to $BACKUP_CONF..."
        cp "$PF_CONF" "$BACKUP_CONF" || handle_error "Failed to backup PF configuration."
    fi
 
    log INFO "Detecting active network interface..."
    local INTERFACE
    INTERFACE=$(route -n get default | awk '/interface:/ {print $2}')
    [[ -z "$INTERFACE" ]] && handle_error "Unable to detect active network interface."
    log INFO "Active interface detected: $INTERFACE"
 
    log INFO "Generating new PF configuration..."
    cat <<EOF > "$PF_CONF"
# PF configuration generated on $(date)
ext_if = "$INTERFACE"
set block-policy drop
block all
pass quick on lo0 all
pass out quick inet proto { tcp udp } from any to any keep state
pass in quick on \$ext_if proto tcp to (\$ext_if) port 22 keep state
pass in quick on \$ext_if proto tcp to (\$ext_if) port { 80 443 } keep state
pass out all keep state
EOF
 
    [[ ! -f "$PF_CONF" ]] && handle_error "Failed to create new PF configuration."
 
    if ! kldstat | grep -q pf; then
        log INFO "Loading PF kernel module..."
        kldload pf || handle_error "Failed to load PF kernel module."
        echo 'pf_load="YES"' >> /boot/loader.conf
        log INFO "PF kernel module configured to load at boot."
    else
        log INFO "PF kernel module is already loaded."
    fi
 
    if ! grep -q '^pf_enable="YES"' /etc/rc.conf; then
        log INFO "Enabling PF in rc.conf..."
        sysrc pf_enable="YES" || handle_error "Failed to enable PF in rc.conf."
    fi
 
    [[ ! -c /dev/pf ]] && handle_error "/dev/pf missing. Ensure PF kernel module is loaded."
 
    log INFO "Validating new PF configuration..."
    pfctl -nf "$PF_CONF" || handle_error "PF configuration validation failed."
    pfctl -f "$PF_CONF" || handle_error "Failed to load new PF configuration."
    log INFO "PF configuration loaded successfully."
 
    if pfctl -s info | grep -q "Status: Enabled"; then
        log INFO "PF is already active."
    else
        log INFO "Enabling PF..."
        pfctl -e || handle_error "Failed to enable PF."
        log INFO "PF enabled."
    fi
 
    log INFO "PF firewall configuration completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# PLEX MEDIA SERVER INSTALLATION
# ------------------------------------------------------------------------------
install_plex_media_server() {
    log INFO "--------------------------------------"
    log INFO "Starting Plex Media Server installation..."
 
    log INFO "Installing plexmediaserver-plexpass..."
    pkg install -y plexmediaserver-plexpass || handle_error "Failed to install Plex Media Server."
 
    log INFO "Enabling Plex Media Server to start on boot..."
    sysrc plexmediaserver_plexpass_enable="YES" || handle_error "Failed to enable Plex on boot."
 
    log INFO "Starting Plex Media Server..."
    service plexmediaserver_plexpass start || handle_error "Failed to start Plex service."
    log INFO "Plex Media Server started successfully."
    log INFO "Access Plex Web Interface at: http://localhost:32400/web"
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# VS CODE CLI INSTALLATION
# ------------------------------------------------------------------------------
install_vscode_cli() {
    log INFO "--------------------------------------"
    log INFO "Starting Visual Studio Code CLI installation..."
 
    if ! command -v node &>/dev/null; then
        handle_error "Node.js is not installed. Install Node.js first."
    fi
 
    log INFO "Creating symbolic link for Node.js..."
    local node_bin
    node_bin=$(which node)
    [ -z "$node_bin" ] && handle_error "Node.js binary not found."
    [[ -e "/usr/local/node" ]] && rm -f "/usr/local/node"
    ln -s "$node_bin" /usr/local/node || handle_error "Failed to create Node.js symlink."
    log INFO "Node.js symlink created at /usr/local/node."
 
    log INFO "Downloading VS Code CLI..."
    local vscode_cli_url="https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64"
    local vscode_cli_tarball="vscode_cli.tar.gz"
    curl -Lk "$vscode_cli_url" --output "$vscode_cli_tarball" || handle_error "Failed to download VS Code CLI."
    log INFO "Downloaded VS Code CLI tarball."
 
    log INFO "Extracting VS Code CLI..."
    tar -xf "$vscode_cli_tarball" || handle_error "Failed to extract VS Code CLI."
    log INFO "Extraction completed."
 
    rm -f "$vscode_cli_tarball" || log WARN "Failed to remove VS Code CLI tarball."
 
    if [[ ! -f "./code" ]]; then
        handle_error "VS Code CLI binary not found after extraction."
    fi
 
    chmod +x ./code || handle_error "Failed to set executable permissions for VS Code CLI."
    log INFO "VS Code CLI installed successfully. Run './code tunnel --name freebsd-server' to start."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# FIRA CODE FONT INSTALLATION
# ------------------------------------------------------------------------------
install_font() {
    local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local font_dir="/usr/local/share/fonts/nerd-fonts"
    local font_file="FiraCodeNerdFont-Regular.ttf"
 
    log INFO "--------------------------------------"
    log INFO "Starting FiraCode Nerd Font installation..."
 
    if [[ ! -d "$font_dir" ]]; then
        log INFO "Creating font directory: $font_dir"
        mkdir -p "$font_dir" || handle_error "Failed to create font directory."
    fi
 
    chmod 755 "$font_dir" || handle_error "Failed to set permissions on font directory."
 
    log INFO "Downloading FiraCode Nerd Font..."
    curl -L -o "$font_dir/$font_file" "$font_url" || handle_error "Failed to download FiraCode Nerd Font."
    log INFO "Font downloaded successfully."
 
    [[ ! -f "$font_dir/$font_file" ]] && handle_error "Font file not found after download."
 
    chmod 644 "$font_dir/$font_file" || handle_error "Failed to set permissions on font file."
    chown root:wheel "$font_dir/$font_file" || handle_error "Failed to set ownership on font file."
 
    fc-cache -fv >/dev/null 2>&1 || handle_error "Failed to refresh font cache."
    log INFO "Font cache refreshed successfully."
 
    if ! fc-list | grep -qi "FiraCode"; then
        log ERROR "FiraCode Nerd Font verification failed."
        ls -l "$font_dir"
        fc-cache -fv
        fc-list | grep -i "FiraCode"
        handle_error "FiraCode Nerd Font is not available."
    fi
 
    log INFO "FiraCode Nerd Font installation completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# GITHUB REPOSITORIES DOWNLOAD
# ------------------------------------------------------------------------------
download_repositories() {
    log INFO "--------------------------------------"
    log INFO "Starting GitHub repositories download..."
 
    local github_dir="/home/${USERNAME}/github"
    log INFO "Creating GitHub directory at $github_dir"
    mkdir -p "$github_dir" || handle_error "Failed to create GitHub directory."
 
    cd "$github_dir" || handle_error "Failed to change to GitHub directory."
 
    local repos=( "bash" "c" "religion" "windows" "hugo" "python" )
    for repo in "${repos[@]}"; do
        local repo_url="https://github.com/dunamismax/${repo}.git"
        local repo_dir="${github_dir}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            log INFO "Updating repository: $repo"
            git -C "$repo_dir" pull || handle_error "Failed to update $repo."
        else
            log INFO "Cloning repository: $repo"
            git clone "$repo_url" "$repo_dir" || handle_error "Failed to clone $repo."
        fi
    done
 
    log INFO "GitHub repositories downloaded/updated successfully."
    cd "$USER_HOME" || handle_error "Failed to return to home directory."
}
 
# ------------------------------------------------------------------------------
# DIRECTORY PERMISSIONS
# ------------------------------------------------------------------------------
set_directory_permissions() {
    local github_dir="/home/${USERNAME}/github"
    local hugo_public_dir="${github_dir}/hugo/dunamismax.com/public"
    local hugo_dir="${github_dir}/hugo"
    local BASE_DIR="$github_dir"
 
    local DIR_PERMISSIONS="700"
    local FILE_PERMISSIONS="600"
 
    log INFO "--------------------------------------"
    log INFO "Starting directory permission updates..."
 
    log INFO "Making all .sh files executable in $github_dir"
    find "$github_dir" -type f -name "*.sh" -exec chmod +x {} + || handle_error "Failed to set .sh file permissions."
 
    log INFO "Setting ownership for $github_dir and $USER_HOME"
    chown -R "${USERNAME}:${USERNAME}" "$github_dir" "$USER_HOME" || handle_error "Failed to set ownership."
 
    if [[ -d "$hugo_public_dir" ]]; then
        log INFO "Setting ownership and permissions for Hugo public directory"
        chown -R www:www "$hugo_public_dir" || handle_error "Failed to set ownership for Hugo public directory."
        chmod -R 755 "$hugo_public_dir" || handle_error "Failed to set permissions for Hugo public directory."
    else
        log WARN "Hugo public directory not found: $hugo_public_dir"
    fi
 
    if [[ -d "$hugo_dir" ]]; then
        log INFO "Setting ownership and permissions for Hugo directory"
        chown -R "${USERNAME}:${USERNAME}" "$hugo_dir" || handle_error "Failed to set ownership for Hugo directory."
        chmod o+rx "$USER_HOME" "$github_dir" "$hugo_dir" "${hugo_dir}/dunamismax.com" \
            || handle_error "Failed to set permissions for Hugo directory."
    else
        log WARN "Hugo directory not found: $hugo_dir"
    fi
 
    for repo in bash c python religion windows; do
        local repo_dir="${github_dir}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            log INFO "Setting ownership for repository: $repo"
            chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo."
        else
            log WARN "Repository not found: $repo_dir"
        fi
    done
 
    if [[ ! -d "$BASE_DIR" ]]; then
        handle_error "Base directory does not exist: $BASE_DIR"
    fi
 
    log INFO "Fixing .git directory permissions in $BASE_DIR..."
    while IFS= read -r -d '' git_dir; do
        [[ -d "$git_dir" ]] && {
            log INFO "Setting permissions for $git_dir"
            chmod "$DIR_PERMISSIONS" "$git_dir" || handle_error "Failed to set permissions for $git_dir"
            find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} + || handle_error "Failed to set directory permissions for $git_dir"
            find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} + || handle_error "Failed to set file permissions for $git_dir"
        } || log WARN ".git directory not found: $git_dir"
    done < <(find "$BASE_DIR" -type d -name ".git" -print0)
 
    log INFO "Directory permission updates completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# CADDY INSTALLATION AND CONFIGURATION
# ------------------------------------------------------------------------------
install_and_configure_caddy() {
    log INFO "--------------------------------------"
    log INFO "Starting Caddy installation and configuration..."
 
    log INFO "Installing Caddy..."
    pkg install -y www/caddy || handle_error "Failed to install Caddy."
    log INFO "Caddy installed."
 
    log INFO "Creating Caddy configuration directory..."
    mkdir -p /usr/local/etc/caddy || handle_error "Failed to create Caddy config directory."
    log INFO "Caddy config directory: /usr/local/etc/caddy"
 
    local caddyfile_src="/home/${USERNAME}/github/bash/freebsd/dotfiles/caddy/Caddyfile"
    local caddyfile_dst="/usr/local/etc/caddy/Caddyfile"
 
    log INFO "Copying Caddyfile from $caddyfile_src to $caddyfile_dst..."
    cp "$caddyfile_src" "$caddyfile_dst" || handle_error "Failed to copy Caddyfile."
    log INFO "Caddyfile copied."
 
    log INFO "Setting ownership and permissions for Caddyfile..."
    chown root:wheel "$caddyfile_dst" || handle_error "Failed to set ownership for Caddyfile."
    chmod 644 "$caddyfile_dst" || handle_error "Failed to set permissions for Caddyfile."
 
    log INFO "Enabling Caddy service..."
    sysrc caddy_enable="YES" || handle_error "Failed to enable Caddy service."
    log INFO "Starting Caddy service..."
    service caddy start || handle_error "Failed to start Caddy service."
    service caddy status || handle_error "Caddy service is not running."
    log INFO "Caddy installation and configuration completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# DOTFILES SETUP
# ------------------------------------------------------------------------------
setup_dotfiles() {
    log INFO "--------------------------------------"
    log INFO "Starting dotfiles setup..."
 
    local user_home="$USER_HOME"
    local scripts_dir="${user_home}/github/bash/freebsd/_scripts"
    local dotfiles_dir="${user_home}/github/bash/freebsd/dotfiles"
    local config_dir="${user_home}/.config"
    local local_bin_dir="${user_home}/.local/bin"
 
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi
    if [[ ! -d "$scripts_dir" ]]; then
        handle_error "Scripts directory not found: $scripts_dir"
    fi
 
    log INFO "Creating required directories..."
    mkdir -p "$config_dir" "$local_bin_dir" || handle_error "Failed to create config or local bin directories."
 
    local files=(
        "${dotfiles_dir}/.bashrc:${user_home}/"
        "${dotfiles_dir}/.profile:${user_home}/"
    )
    log INFO "Copying dotfiles..."
    for item in "${files[@]}"; do
        local src="${item%:*}"
        local dst="${item#*:}"
        if [[ -f "$src" ]]; then
            cp "$src" "$dst" || handle_error "Failed to copy $src"
            log INFO "Copied file: $src -> $dst"
        else
            log WARN "Source file not found: $src"
        fi
    done
 
    log INFO "Copying scripts to local bin..."
    for script in "$scripts_dir"/*; do
        [[ -f "$script" ]] && {
            cp "$script" "$local_bin_dir" || handle_error "Failed to copy $script"
            log INFO "Copied script: $script -> $local_bin_dir"
        }
    done
 
    log INFO "Setting ownership for $user_home..."
    chown -R "${USERNAME}:${USERNAME}" "$user_home" || handle_error "Failed to set ownership."
    chmod -R u=rwX,g=rX,o=rX "$local_bin_dir" || handle_error "Failed to set permissions for local bin."
 
    log INFO "Dotfiles setup completed."
    log INFO "--------------------------------------"
    return 0
}
 
# ------------------------------------------------------------------------------
# FINALIZE SYSTEM CONFIGURATION
# ------------------------------------------------------------------------------
finalize_configuration() {
    log INFO "--------------------------------------"
    log INFO "Finalizing system configuration..."
 
    cd "$USER_HOME" || handle_error "Failed to change to home directory: $USER_HOME"
 
    log INFO "Upgrading installed packages..."
    pkg upgrade -y && log INFO "Packages upgraded." || handle_error "Package upgrade failed."
 
    log INFO "Collecting system information..."
    log INFO "Uptime: $(uptime)"
    log INFO "Disk Usage (root): $(df -h / | tail -1)"
    log INFO "Memory and Swap Usage:"
    vmstat -s
    log INFO "CPU Model: $(sysctl -n hw.model 2>/dev/null || echo 'Unknown')"
    log INFO "Kernel Version: $(uname -r)"
    log INFO "Network Configuration:" 
    ifconfig -a
    log INFO "System information logged."
    log INFO "Final configuration completed."
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------------------------
main() {
    log INFO "--------------------------------------"
    log INFO "Starting FreeBSD Automated System Configuration Script"
 
    local functions=(
        initial_system_update
        backup_system
        configure_sudo_access
        install_pkgs
        configure_ssh_settings
        configure_pf
        download_repositories
        set_directory_permissions
        install_plex_media_server
        install_vscode_cli
        install_font
        install_and_configure_caddy
        setup_dotfiles
        finalize_configuration
    )
 
    for func in "${functions[@]}"; do
        log INFO "Running function: $func"
        $func || handle_error "Function $func failed."
    done
 
    log INFO "Configuration script finished successfully."
    log INFO "Enjoy FreeBSD!"
    log INFO "--------------------------------------"
}
 
# ------------------------------------------------------------------------------
# Reboot Prompt
# ------------------------------------------------------------------------------
prompt_reboot() {
    log INFO "Setup complete. A reboot is recommended to apply all changes."
    read -p "Reboot now? (y/n): " REBOOT
    if [[ "$REBOOT" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot skipped. Please reboot manually when convenient."
    fi
}
 
# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    prompt_reboot
fi
