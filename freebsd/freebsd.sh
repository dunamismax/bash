#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# FreeBSD Automated System Configuration Script (Improved)
# ------------------------------------------------------------------------------
# Description:
#   This script automates the configuration of a fresh FreeBSD installation
#   to create a secure, optimized, and personalized environment. It performs:
#     • System updates/upgrades and full backups
#     • Installation of essential packages, development tools, and utilities
#     • SSH hardening and PF firewall configuration
#     • Fail2ban setup for intrusion prevention
#     • GitHub repository cloning and dotfiles deployment
#     • Deployment of user scripts and directory permission fixes
#     • Installation of Plex Media Server, VS Code CLI, minimal GUI, and FiraCode
#       Nerd Font
#     • Caddy web server installation and configuration
#     • Final system information logging, cache cleanup, and an optional reboot
#
# Usage:
#   Run as root (e.g., sudo ./freebsd_setup.sh). Adjust variables as needed.
#   All actions are logged to /var/log/freebsd_setup.log.
#
# Author: dunamismax | License: MIT
# Repository: https://github.com/dunamismax/bash
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Shell settings & error handling
# ------------------------------------------------------------------------------
set -Eeuo pipefail

trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
trap 'handle_error "Script interrupted at line $LINENO."' SIGINT SIGTERM

cleanup() {
    log_info "Cleanup tasks complete."
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
USER_HOME="/usr/home/${USERNAME}"
GITHUB_BASE="https://github.com/dunamismax"

# Packages to install (make sure these are available via pkg)
PACKAGES=(
  bash vim nano screen tmux mc rsync curl wget htop tree unzip zip
  gmake cmake ninja meson gettext git pkgconf openssl libffi nmap fail2ban
  python39 python39-pip python39-virtualenv less bind-tools ncdu gawk tcpdump
  lsof jq tzdata zlib readline bzip2 tk xz ncurses gdbm libxml2 clang llvm
)

# ------------------------------------------------------------------------------
# Logging Functions
# ------------------------------------------------------------------------------
# Color codes for log levels
NORD_DEBUG='\033[38;2;129;161;193m'
NORD_ERROR='\033[38;2;191;97;106m'
NORD_WARN='\033[38;2;235;203;139m'
NORD_INFO='\033[38;2;163;190;140m'
NC='\033[0m'

log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local upper_level="${level^^}"
    local color="$NC"
    case "$upper_level" in
        INFO)  color="${NORD_INFO}" ;;
        WARN|WARNING) color="${NORD_WARN}"; upper_level="WARN" ;;
        ERROR) color="${NORD_ERROR}" ;;
        DEBUG) color="${NORD_DEBUG}" ;;
        *)     color="$NC" ;;
    esac
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    if [ -t 2 ]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    else
        echo "$log_entry" >&2
    fi
}
log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

handle_error() {
    local err_msg="${1:-An unknown error occurred.}"
    local exit_code="${2:-1}"
    log_error "$err_msg (Exit Code: $exit_code)"
    log_error "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD_ERROR}ERROR: $err_msg (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# XDG Base Directory Setup
# ------------------------------------------------------------------------------
export XDG_CONFIG_HOME="${USER_HOME}/.config"
export XDG_DATA_HOME="${USER_HOME}/.local/share"
export XDG_CACHE_HOME="${USER_HOME}/.cache"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" || handle_error "Failed to create XDG directories."
log_info "XDG directories set: XDG_CONFIG_HOME=$XDG_CONFIG_HOME, XDG_DATA_HOME=$XDG_DATA_HOME, XDG_CACHE_HOME=$XDG_CACHE_HOME"

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "This script must be run as root."
    fi
    log_info "Running as root."
}

# ------------------------------------------------------------------------------
# System Update & Backup
# ------------------------------------------------------------------------------
initial_system_update() {
    log_info "Starting system update and upgrade..."
    pkg update -f || handle_error "Failed to update pkg repositories."
    pkg upgrade -y || handle_error "System upgrade failed."
    log_info "System update complete."
}

backup_system() {
    log_info "Starting system backup..."
    if ! command -v rsync &>/dev/null; then
        log_info "Installing rsync..."
        pkg install -y rsync || handle_error "Failed to install rsync."
    fi

    local SOURCE="/"
    local DESTINATION="${USER_HOME}/BACKUPS"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_FOLDER="${DESTINATION}/backup-${TIMESTAMP}"
    local RETENTION_DAYS=7

    # List of directories to exclude from backup
    local EXCLUDES=(
      "/dev/*" "/proc/*" "/tmp/*" "/var/tmp/*" "/var/run/*"
      "/var/log/*" "/var/cache/*" "/var/db/pkg/*" "/var/db/ports/*"
      "/var/db/portsnap/*" "/var/db/freebsd-update/*" "/mnt/*"
      "/media/*" "/swapfile" "/lost+found" "/root/.cache/*" "${DESTINATION}"
    )
    local EXCLUDES_ARGS=()
    for ex in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$ex")
    done

    mkdir -p "$BACKUP_FOLDER" || handle_error "Failed to create backup folder: $BACKUP_FOLDER"
    log_info "Performing backup with rsync..."
    rsync -aAXv --stats "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER" || handle_error "Backup failed."
    log_info "Backup completed: $BACKUP_FOLDER"

    log_info "Removing backups older than ${RETENTION_DAYS} days..."
    find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} + \
      && log_info "Old backups removed." || log_warn "Some old backups could not be removed."
}

# ------------------------------------------------------------------------------
# doas Configuration
# ------------------------------------------------------------------------------
configure_doas() {
    log_info "Installing and configuring doas..."

    # Install doas
    pkg install -y doas || handle_error "Failed to install doas."

    # Create the 'doas' group if it doesn't exist
    if ! pw groupshow doas &>/dev/null; then
        pw groupadd doas || handle_error "Failed to create doas group."
        log_info "Created doas group."
    else
        log_info "doas group already exists."
    fi

    # Add user to the doas group
    pw usermod "$USERNAME" -G doas || handle_error "Failed to add $USERNAME to doas group."
    log_info "User $USERNAME added to doas group."

    # Configure doas by creating or backing up the configuration file
    local DOAS_CONF="/usr/local/etc/doas.conf"
    if [ -f "$DOAS_CONF" ]; then
        cp "$DOAS_CONF" "${DOAS_CONF}.bak.$(date +%Y%m%d%H%M%S)" || log_warn "Could not backup existing doas.conf."
        log_info "Backed up existing doas.conf."
    fi

    cat <<EOF > "$DOAS_CONF"
# Doas configuration generated on $(date)
permit persist :doas
EOF

    chown root:wheel "$DOAS_CONF" || handle_error "Failed to set ownership on doas.conf."
    chmod 440 "$DOAS_CONF" || handle_error "Failed to set permissions on doas.conf."
    log_info "doas configuration written to $DOAS_CONF."

    # Optionally, enable doas in rc.conf if required
    if ! grep -q '^doas_enable="YES"' /etc/rc.conf; then
        echo 'doas_enable="YES"' >> /etc/rc.conf || handle_error "Failed to enable doas in rc.conf."
        log_info "doas enabled in rc.conf."
    else
        log_info "doas already enabled in rc.conf."
    fi

    log_info "doas installation and configuration completed successfully."
}

# ------------------------------------------------------------------------------
# Package Installation
# ------------------------------------------------------------------------------
install_packages() {
    log_info "Starting package installation..."
    pkg upgrade -y || handle_error "Package upgrade failed."
    log_info "Installing packages: ${PACKAGES[*]}"
    pkg install -y "${PACKAGES[@]}" || handle_error "Package installation failed."
    for pkg in bash sudo openssl python39 git; do
        pkg info -q "$pkg" || handle_error "Critical package $pkg is missing."
    done
    log_info "All packages installed successfully."
}

# ------------------------------------------------------------------------------
# SSH Configuration & Hardening
# ------------------------------------------------------------------------------
configure_ssh() {
    log_info "Configuring SSH service..."
    if ! grep -q '^sshd_enable="YES"' /etc/rc.conf; then
        echo 'sshd_enable="YES"' >> /etc/rc.conf || handle_error "Failed to enable sshd in rc.conf."
        log_info "Enabled sshd in rc.conf."
    fi
    service sshd restart 2>/dev/null || service sshd start || handle_error "Failed to start sshd."
    log_info "SSH service configured."
}

secure_ssh_config() {
    log_info "Hardening SSH configuration..."
    local sshd_config="/etc/ssh/sshd_config"
    if [ ! -f "$sshd_config" ]; then
        handle_error "sshd_config not found at $sshd_config."
    fi
    cp "$sshd_config" "${sshd_config}.bak.$(date +%Y%m%d%H%M%S)" || handle_error "Failed to backup sshd_config."
    log_info "Backed up sshd_config."
    sed -i '' 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$sshd_config" || handle_error "Failed to set PermitRootLogin."
    sed -i '' 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config" || handle_error "Failed to set PasswordAuthentication."
    sed -i '' 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config" || handle_error "Failed to set ChallengeResponseAuthentication."
    sed -i '' 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config" || handle_error "Failed to set X11Forwarding."
    grep -q "^PermitEmptyPasswords no" "$sshd_config" || echo "PermitEmptyPasswords no" >> "$sshd_config" || handle_error "Failed to set PermitEmptyPasswords."
    service sshd restart || handle_error "Failed to restart sshd after hardening."
    log_info "SSH configuration hardened."
}

# ------------------------------------------------------------------------------
# PF Firewall Configuration
# ------------------------------------------------------------------------------
configure_firewall() {
    log_info "Configuring PF firewall..."
    if ! grep -q '^pf_enable="YES"' /etc/rc.conf; then
        echo 'pf_enable="YES"' >> /etc/rc.conf || handle_error "Failed to enable PF in rc.conf."
        log_info "Enabled PF in rc.conf."
    fi
    local PF_CONF="/etc/pf.conf"
    local PF_BACKUP="/etc/pf.conf.bak.$(date +%Y%m%d%H%M%S)"
    if [ -f "$PF_CONF" ]; then
        cp "$PF_CONF" "$PF_BACKUP" || log_warn "Could not backup existing PF config."
        log_info "PF configuration backed up to $PF_BACKUP."
    else
        log_warn "No existing PF config to backup."
    fi

    log_info "Detecting active network interface..."
    local INTERFACE
    INTERFACE=$(route -n get default | awk '/interface:/ {print $2}')
    [ -z "$INTERFACE" ] && handle_error "Active network interface not found."
    log_info "Active interface: $INTERFACE"

    cat <<EOF > "$PF_CONF"
# PF configuration generated on $(date)
ext_if = "$INTERFACE"
set block-policy drop
block all
pass quick on lo0 all
pass out quick inet proto { tcp udp } from any to any keep state
pass in quick on \$ext_if proto tcp to (\$ext_if) port {22,80,443,32400} keep state
pass out all keep state
EOF

    pfctl -nf "$PF_CONF" || handle_error "PF configuration validation failed."
    pfctl -f "$PF_CONF" || handle_error "Failed to load PF configuration."
    if ! pfctl -s info | grep -q "Status: Enabled"; then
        pfctl -e || handle_error "Failed to enable PF."
    fi
    log_info "PF firewall configured."
}

# ------------------------------------------------------------------------------
# Fail2ban Configuration
# ------------------------------------------------------------------------------
configure_fail2ban() {
    if command -v fail2ban-client &>/dev/null; then
        log_info "Fail2ban is already installed. Skipping installation."
        return 0
    fi
    log_info "Installing Fail2ban..."
    pkg install -y fail2ban || handle_error "Failed to install Fail2ban."
    local jail_conf="/usr/local/etc/fail2ban/jail.local"
    if [ -f "$jail_conf" ]; then
        cp "$jail_conf" "${jail_conf}.bak" || log_warn "Could not backup existing jail.local."
        log_info "Backed up existing jail.local."
    else
        log_warn "No existing jail.local to backup."
    fi
    cat <<EOF > "$jail_conf"
[sshd]
enabled  = true
port     = 22
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 5
findtime = 600
bantime  = 3600
EOF
    if ! grep -q '^fail2ban_enable="YES"' /etc/rc.conf; then
        echo 'fail2ban_enable="YES"' >> /etc/rc.conf || log_warn "Failed to add fail2ban_enable to rc.conf."
    fi
    service fail2ban start || log_warn "Failed to start Fail2ban service."
    log_info "Fail2ban configured."
}

# ------------------------------------------------------------------------------
# GitHub Repositories Setup
# ------------------------------------------------------------------------------
setup_repos() {
    local repo_dir="${USER_HOME}/github"
    log_info "Setting up Git repositories in $repo_dir..."
    if [ -d "$repo_dir" ]; then
        log_info "Repository directory exists. Skipping cloning."
    else
        mkdir -p "$repo_dir" || handle_error "Failed to create directory: $repo_dir"
        for repo in bash windows web python go misc; do
            local target_dir="${repo_dir}/${repo}"
            if [ -d "$target_dir" ]; then
                log_info "Repository '$repo' already exists. Skipping."
            else
                git clone "${GITHUB_BASE}/${repo}.git" "$target_dir" || handle_error "Failed to clone repository '$repo'."
                log_info "Cloned repository: $repo"
            fi
        done
        chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo_dir."
    fi
}

# ------------------------------------------------------------------------------
# Directory Permissions & User Script Deployment
# ------------------------------------------------------------------------------
set_directory_permissions() {
    local github_dir="${USER_HOME}/github"
    log_info "Setting ownership and permissions in $github_dir and $USER_HOME..."
    chown -R "${USERNAME}:${USERNAME}" "$github_dir" "$USER_HOME" || handle_error "Failed to set ownership."
    find "$github_dir" -type f -name "*.sh" -exec chmod +x {} + || handle_error "Failed to set execute permission for .sh files."
    log_info "Directory permissions updated."
}

deploy_user_scripts() {
    local bin_dir="${USER_HOME}/bin"
    local scripts_src="${USER_HOME}/github/bash/freebsd/_scripts/"
    log_info "Deploying user scripts from $scripts_src to $bin_dir..."
    mkdir -p "$bin_dir" || handle_error "Failed to create directory: $bin_dir"
    if rsync -ah --delete "$scripts_src" "$bin_dir"; then
        find "$bin_dir" -type f -exec chmod 755 {} \; || handle_error "Failed to set execute permissions in $bin_dir."
        log_info "User scripts deployed successfully."
    else
        handle_error "Failed to deploy user scripts."
    fi
}

# ------------------------------------------------------------------------------
# Dotfiles Deployment (Unified)
# ------------------------------------------------------------------------------
setup_dotfiles() {
    log_info "Deploying dotfiles..."
    local dotfiles_source="${USER_HOME}/github/bash/freebsd/dotfiles"
    if [ ! -d "$dotfiles_source" ]; then
        log_warn "Dotfiles directory not found: $dotfiles_source. Skipping dotfiles deployment."
        return 0
    fi

    # Files to deploy (will be copied to both user and root home)
    local files=( ".bashrc" ".profile" ".xinitrc" )
    local targets=( "$USER_HOME" "/root" )

    for file in "${files[@]}"; do
        for target in "${targets[@]}"; do
            if [ -f "${target}/${file}" ]; then
                cp "${target}/${file}" "${target}/${file}.bak" && log_info "Backed up ${target}/${file}."
            fi
            cp -f "${dotfiles_source}/${file}" "${target}/${file}" || handle_error "Failed to copy ${file} to ${target}."
            log_info "Copied ${file} to ${target}."
        done
    done

    # Deploy configuration directories (e.g. i3, alacritty, picom, etc.)
    local config_dir="${USER_HOME}/.config"
    mkdir -p "$config_dir" || handle_error "Failed to create configuration directory: $config_dir"
    local dirs=( "alacritty" "i3" "picom" "i3status" )
    for dir in "${dirs[@]}"; do
        if [ -d "${dotfiles_source}/${dir}" ]; then
            cp -r "${dotfiles_source}/${dir}" "$config_dir" || handle_error "Failed to copy directory ${dir}."
            log_info "Copied directory ${dir} to ${config_dir}."
        else
            log_warn "Source directory ${dotfiles_source}/${dir} not found. Skipping."
        fi
    done

    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME" || handle_error "Failed to set ownership for $USER_HOME."
    log_info "Dotfiles deployment completed."
}

# ------------------------------------------------------------------------------
# Set Default Shell for User and Root
# ------------------------------------------------------------------------------
set_default_shell() {
    local target_shell="/usr/local/bin/bash"
    if [ ! -x "$target_shell" ]; then
        log_error "Bash not found or not executable at $target_shell."
        return 1
    fi
    log_info "Setting default shell to $target_shell for $USERNAME and root."
    chsh -s "$target_shell" "$USERNAME" || handle_error "Failed to set default shell for $USERNAME."
    chsh -s "$target_shell" root || handle_error "Failed to set default shell for root."
    log_info "Default shell set to $target_shell."
}

# ------------------------------------------------------------------------------
# Plex Media Server Installation
# ------------------------------------------------------------------------------
install_plex_media_server() {
    log_info "Installing Plex Media Server..."
    pkg install -y plexmediaserver-plexpass || handle_error "Failed to install Plex Media Server."
    sysrc plexmediaserver_plexpass_enable="YES" || handle_error "Failed to enable Plex on boot."
    service plexmediaserver-plexpass start || handle_error "Failed to start Plex service."
    log_info "Plex Media Server installed and started. Access via http://localhost:32400/web"
}

# ------------------------------------------------------------------------------
# VS Code CLI Installation
# ------------------------------------------------------------------------------
install_vscode_cli() {
    log_info "Installing Visual Studio Code CLI..."
    if ! command -v node &>/dev/null; then
        handle_error "Node.js is not installed. Please install Node.js first."
    fi
    local node_bin
    node_bin=$(which node) || handle_error "Node.js binary not found."
    [ -e "/usr/local/node" ] && rm -f "/usr/local/node"
    ln -s "$node_bin" /usr/local/node || handle_error "Failed to create Node.js symlink."
    log_info "Node.js symlink created at /usr/local/node."

    local vscode_cli_url="https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64"
    local vscode_cli_tarball="vscode_cli.tar.gz"
    curl -Lk "$vscode_cli_url" --output "$vscode_cli_tarball" || handle_error "Failed to download VS Code CLI."
    log_info "Downloaded VS Code CLI tarball."
    tar -xf "$vscode_cli_tarball" || handle_error "Failed to extract VS Code CLI."
    rm -f "$vscode_cli_tarball" || log_warn "Failed to remove VS Code CLI tarball."
    if [ ! -f "./code" ]; then
        handle_error "VS Code CLI binary not found after extraction."
    fi
    chmod +x ./code || handle_error "Failed to set executable permissions for VS Code CLI."
    log_info "VS Code CLI installed successfully. Run './code tunnel --name freebsd-server' to start."
}

# ------------------------------------------------------------------------------
# Minimal GUI Installation
# ------------------------------------------------------------------------------
install_gui() {
    log_info "Starting minimal GUI installation..."
    if pkg install -y \
        xorg xinit xauth xrandr xset xsetroot \
        i3 i3status i3lock \
        drm-kmod dmenu feh picom alacritty \
        pulseaudio pavucontrol flameshot clipmenu \
        vlc dunst thunar firefox; then
        log_info "GUI packages installed successfully."
    else
        handle_error "Failed to install one or more GUI packages."
    fi
    log_info "Minimal GUI installation completed."
}

# ------------------------------------------------------------------------------
# FiraCode Nerd Font Installation
# ------------------------------------------------------------------------------
install_font() {
    log_info "Installing FiraCode Nerd Font..."
    local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local font_dir="/usr/local/share/fonts/nerd-fonts"
    local font_file="FiraCodeNerdFont-Regular.ttf"
    mkdir -p "$font_dir" || handle_error "Failed to create font directory: $font_dir"
    chmod 755 "$font_dir" || handle_error "Failed to set permissions on $font_dir."
    curl -L -o "$font_dir/$font_file" "$font_url" || handle_error "Failed to download FiraCode Nerd Font."
    log_info "Font downloaded to $font_dir/$font_file."
    chmod 644 "$font_dir/$font_file" || handle_error "Failed to set permissions on font file."
    chown root:wheel "$font_dir/$font_file" || handle_error "Failed to set ownership on font file."
    fc-cache -fv >/dev/null 2>&1 || handle_error "Failed to refresh font cache."
    if ! fc-list | grep -qi "FiraCode"; then
        log_error "Font verification failed. FiraCode Nerd Font not available."
        handle_error "FiraCode Nerd Font verification failed."
    fi
    log_info "FiraCode Nerd Font installed successfully."
}

# ------------------------------------------------------------------------------
# Caddy Web Server Installation & Configuration
# ------------------------------------------------------------------------------
install_and_configure_caddy() {
    log_info "Installing Caddy..."
    pkg install -y www/caddy || handle_error "Failed to install Caddy."
    mkdir -p /usr/local/etc/caddy || handle_error "Failed to create Caddy config directory."
    local caddyfile_src="${USER_HOME}/github/bash/freebsd/dotfiles/caddy/Caddyfile"
    local caddyfile_dst="/usr/local/etc/caddy/Caddyfile"
    cp "$caddyfile_src" "$caddyfile_dst" || handle_error "Failed to copy Caddyfile."
    chown root:wheel "$caddyfile_dst" || handle_error "Failed to set ownership on Caddyfile."
    chmod 644 "$caddyfile_dst" || handle_error "Failed to set permissions on Caddyfile."
    sysrc caddy_enable="YES" || handle_error "Failed to enable Caddy in rc.conf."
    service caddy start || handle_error "Failed to start Caddy service."
    service caddy status || handle_error "Caddy service is not running."
    log_info "Caddy installed and configured."
}

# ------------------------------------------------------------------------------
# Final System Configuration & Cleanup
# ------------------------------------------------------------------------------
finalize_configuration() {
    log_info "Finalizing system configuration..."
    cd "$USER_HOME" || handle_error "Cannot change to home directory: $USER_HOME"
    pkg upgrade -y && log_info "Packages upgraded." || handle_error "Package upgrade failed."
    log_info "System Uptime: $(uptime)"
    log_info "Disk Usage (root): $(df -h / | tail -1)"
    log_info "Memory and Swap Usage:"
    vmstat -s
    log_info "CPU Model: $(sysctl -n hw.model 2>/dev/null || echo 'Unknown')"
    log_info "Kernel Version: $(uname -r)"
    log_info "Network Configuration:"
    ifconfig -a
    log_info "System configuration finalized."
}

cleanup_packages() {
    log_info "Cleaning up unused packages and cache..."
    pkg autoremove -y || log_warn "Orphan package removal failed."
    pkg clean -a -y || log_warn "Pkg cache cleanup failed."
    log_info "Cleanup complete."
}

prompt_reboot() {
    read -rp "Setup complete. Reboot now? (y/n): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_info "Rebooting system..."
        reboot
    else
        log_info "Reboot skipped. Please reboot manually later."
    fi
}

# ------------------------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------------------------
main() {
    log_info "Starting FreeBSD system setup."
    check_root
    initial_system_update
    backup_system
    configure_doas
    install_packages
    configure_ssh
    secure_ssh_config
    configure_firewall
    configure_fail2ban
    setup_repos
    set_directory_permissions
    deploy_user_scripts
    setup_dotfiles
    set_default_shell
    install_plex_media_server
    install_vscode_cli
    install_gui
    install_font
    install_and_configure_caddy
    finalize_configuration
    cleanup_packages
    log_info "FreeBSD system setup completed successfully. Enjoy FreeBSD!"
}

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    prompt_reboot
fi
