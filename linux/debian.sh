#!/usr/bin/env bash
################################################################################
# Debian Automated Setup & Hardening Script
################################################################################

# Exit immediately if a command fails or if an undefined variable is used.
set -eu

# ------------------------------------------------------------------------------
# 1. CONFIGURATION & GLOBAL VARIABLES
# ------------------------------------------------------------------------------

LOG_FILE="/var/log/debian_setup.log"
USERNAME="sawyer"

# Essential Package List (space-delimited)
PACKAGES="bash zsh fish vim nano emacs mc neovim screen tmux \
gcc make cmake meson intltool gettext pigz libtool pkg-config bzip2 git \
chrony sudo bash-completion logrotate \
curl wget tcpdump rsync nmap lynx dnsutils mtr netcat-openbsd socat \
htop neofetch tig jq vnstat tree fzf smartmontools lsof \
gdisk ntfs-3g ncdu unzip zip \
patch gawk expect \
fd-find bat ripgrep hyperfine cheat \
ffmpeg restic mpv nnn \
newsboat irssi \
taskwarrior calcurse \
cowsay figlet \
zfsutils-linux ufw fail2ban"

# Nord Color Theme (for logging)
RED='\033[38;2;191;97;106m'
YELLOW='\033[38;2;235;203;139m'
GREEN='\033[38;2;163;190;140m'
BLUE='\033[38;2;94;129;172m'
NC='\033[0m'

# ------------------------------------------------------------------------------
# 2. UTILITY & LOGGING FUNCTIONS
# ------------------------------------------------------------------------------

log() {
    local level message timestamp color
    level=$(echo "$1" | tr '[:lower:]' '[:upper:]')
    shift
    message="$*"
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    case "$level" in
        INFO)  color="${GREEN}" ;;
        WARN*) color="${YELLOW}" ;;
        ERROR) color="${RED}" ;;
        *)     color="${NC}" ;;
    esac
    # Log to both terminal and file
    printf "%b[%s] [%s] %s%b\n" "$color" "$timestamp" "$level" "$message" "$NC" | tee -a "$LOG_FILE"
}

warn() {
    log WARN "$@"
}

die() {
    log ERROR "$@"
    exit 1
}

# ------------------------------------------------------------------------------
# 3. SYSTEM PREPARATION FUNCTIONS
# ------------------------------------------------------------------------------

# Ensure the script is run as root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "Script must be run as root. Exiting."
    fi
}

# Check for network connectivity by pinging a reliable host
check_network() {
    log INFO "Checking network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        die "No network connectivity. Please verify your network settings."
    fi
    log INFO "Network connectivity verified."
}

# Update package repositories and upgrade system packages
update_system() {
    log INFO "Updating package repositories..."
    if ! apt-get update -qq; then
        die "Failed to update package repositories."
    fi

    log INFO "Upgrading system packages..."
    if ! apt-get upgrade -y; then
        die "Failed to upgrade packages."
    fi
}

# Create the specified user if it does not already exist
ensure_user() {
    if id -u "$USERNAME" >/dev/null 2>&1; then
        log INFO "User '$USERNAME' already exists."
    else
        log INFO "Creating user '$USERNAME'..."
        if ! useradd -m -s /bin/bash "$USERNAME"; then
            die "Failed to create user '$USERNAME'."
        fi
        # Lock the account password to disable direct login (optional)
        passwd -l "$USERNAME" >/dev/null 2>&1 || warn "Failed to lock password for user '$USERNAME'."
    fi
}

configure_sudoers() {
    log INFO "Configuring sudoers file for user '${USERNAME}'..."

    SUDOERS_FILE="/etc/sudoers"

    # Backup the sudoers file if a backup does not already exist.
    if [ ! -f "${SUDOERS_FILE}.bak" ]; then
        cp "$SUDOERS_FILE" "${SUDOERS_FILE}.bak" || warn "Unable to create backup of sudoers file"
        log INFO "Backup of sudoers file created at ${SUDOERS_FILE}.bak"
    fi

    # Check if an entry for $USERNAME already exists
    if grep -Eq "^[[:space:]]*${USERNAME}[[:space:]]+ALL=\(ALL\)[[:space:]]+ALL" "$SUDOERS_FILE"; then
        log INFO "Sudoers entry for '${USERNAME}' already exists."
    else
        echo "${USERNAME} ALL=(ALL) ALL" >> "$SUDOERS_FILE" || warn "Failed to append sudoers entry for '${USERNAME}'"
        log INFO "Added sudoers entry for '${USERNAME}'."
    fi

    # Validate the syntax of the sudoers file
    if ! visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
        die "Sudoers file syntax error! Please review ${SUDOERS_FILE}."
    fi

    log INFO "Sudoers configuration complete."
}

configure_sysctl() {
    log INFO "Applying kernel performance tuning parameters..."

    SYSCTL_CONF="/etc/sysctl.conf"
    BACKUP_CONF="/etc/sysctl.conf.bak"

    # Create a backup of the sysctl configuration if one doesn't already exist.
    if [ ! -f "$BACKUP_CONF" ]; then
        cp "$SYSCTL_CONF" "$BACKUP_CONF" || warn "Unable to create a backup of $SYSCTL_CONF"
        log INFO "Backup of sysctl.conf created at $BACKUP_CONF"
    else
        log INFO "Backup already exists at $BACKUP_CONF"
    fi

    # Append the custom performance tuning parameters if they haven't been added before.
    if ! grep -q "## Debian Performance Tuning" "$SYSCTL_CONF"; then
        cat <<'EOF' >> "$SYSCTL_CONF"

## Debian Performance Tuning (added by debian_setup script)
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 10
EOF
        log INFO "Performance tuning parameters appended to $SYSCTL_CONF"
    else
        log INFO "Performance tuning parameters already exist in $SYSCTL_CONF"
    fi

    # Reload the sysctl settings to apply the new parameters.
    if sysctl -p; then
        log INFO "Kernel parameters reloaded successfully."
    else
        warn "Failed to reload sysctl parameters. Please review $SYSCTL_CONF for errors."
    fi
}

# Install essential system packages
install_packages() {
    log INFO "Installing essential packages..."
    if ! apt-get install -y ${PACKAGES}; then
        die "Failed to install one or more packages."
    fi
}

install_zig() {
    log INFO "Installing Zig programming language..."
    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig is already installed at $(command -v zig). Skipping installation."
        return 0
    fi

    if ! apt-get install -y zig; then
        die "Failed to install Zig."
    fi

    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig installed successfully and is available at $(command -v zig)."
    else
        die "Zig installation completed but the binary is not found in PATH. Please check your installation."
    fi
}

i3_config() {
    log INFO "Installing i3 window manager and its addons..."

    if ! apt-get install -y i3 i3status i3lock dmenu i3blocks; then
        die "Failed to install i3 and its addons."
    fi

    log INFO "Cloning and installing ly login manager from GitHub using Zig..."

    LY_SRC="/usr/local/src/ly"
    LY_REPO="https://github.com/fairyglade/ly.git"

    if [ -d "${LY_SRC}/ly" ]; then
        log INFO "Updating existing ly repository in ${LY_SRC}/ly..."
        cd "${LY_SRC}/ly" || die "Cannot change directory to ${LY_SRC}/ly"
        if ! git pull; then
            warn "Failed to update ly repository; continuing with existing code."
        fi
    else
        log INFO "Cloning ly repository into ${LY_SRC}..."
        mkdir -p "${LY_SRC}" || die "Failed to create directory ${LY_SRC}"
        cd "${LY_SRC}" || die "Cannot change directory to ${LY_SRC}"
        if ! git clone "$LY_REPO"; then
            die "Failed to clone ly repository from ${LY_REPO}"
        fi
        cd ly || die "Cannot change directory to ly"
    fi

    log INFO "Compiling ly using Zig..."
    if ! zig build; then
        die "zig build for ly failed."
    fi

    log INFO "Installing ly using Zig..."
    if ! zig build install; then
        die "zig build install for ly failed."
    fi

    log INFO "Enabling ly display manager service..."
    if ! systemctl enable ly.service; then
        warn "Failed to enable ly service."
    else
        log INFO "ly service enabled."
    fi

    log INFO "Starting ly display manager..."
    if ! systemctl start ly.service; then
        warn "Failed to start ly service."
    else
        log INFO "ly service started."
    fi

    log INFO "i3 and ly configuration complete. You can now choose your desktop session at login."
}

# ------------------------------------------------------------------------------
# 4. CORE CONFIGURATION FUNCTIONS
# ------------------------------------------------------------------------------

# Harden and configure the SSH server
configure_ssh() {
    log INFO "Configuring SSH server..."

    SSH_CONFIG="/etc/ssh/sshd_config"
    if [ -f "$SSH_CONFIG" ]; then
        cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"
        log INFO "Backup of SSH config saved as ${SSH_CONFIG}.bak"
        sed -i -e 's/^#\?PermitRootLogin.*/PermitRootLogin no/' \
               -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
               -e 's/^#\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' "$SSH_CONFIG"
        if ! systemctl restart ssh; then
            die "Failed to restart SSH service."
        fi
        log INFO "SSH configuration updated and service restarted."
    else
        warn "SSH configuration file not found at $SSH_CONFIG."
    fi
}

# Configure the firewall using ufw
configure_firewall() {
    log INFO "Configuring firewall with ufw..."
    # Set default policies
    ufw default deny incoming || warn "Failed to set default deny incoming"
    ufw default allow outgoing || warn "Failed to set default allow outgoing"
    # Allow SSH, HTTP, HTTPS, and Plex Media Server
    ufw allow 22/tcp || warn "Failed to allow SSH"
    ufw allow 80/tcp || warn "Failed to allow HTTP"
    ufw allow 443/tcp || warn "Failed to allow HTTPS"
    ufw allow 32400/tcp || warn "Failed to allow Plex Media Server port"
    # Enable ufw without prompt
    ufw --force enable || die "Failed to enable ufw firewall"
    log INFO "Firewall configured and enabled."
}

# Enable and start the fail2ban service
configure_fail2ban() {
    log INFO "Enabling fail2ban service..."
    if ! systemctl enable fail2ban; then
        warn "Failed to enable fail2ban service."
    fi
    if ! systemctl start fail2ban; then
        warn "Failed to start fail2ban service."
    else
        log INFO "fail2ban service started successfully."
    fi
}

# ------------------------------------------------------------------------------
# 5. STORAGE & SERVICES CONFIGURATION
# ------------------------------------------------------------------------------

# Install and configure Plex Media Server
install_plex() {
    log INFO "Installing Plex Media Server..."
    if ! apt-get install -y plexmediaserver; then
        die "Plex Media Server installation failed."
    fi

    # Set the Plex Media Server user in its configuration (if applicable)
    PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" || warn "Failed to set Plex user in $PLEX_CONF"
    else
        echo "PLEX_MEDIA_SERVER_USER=${USERNAME}" > "$PLEX_CONF" || warn "Failed to create $PLEX_CONF"
    fi

    if ! systemctl enable plexmediaserver; then
        warn "Failed to enable Plex Media Server service."
    fi
    if ! systemctl start plexmediaserver; then
        warn "Plex Media Server failed to start."
    else
        log INFO "Plex Media Server installed and started."
    fi
}

# Configure ZFS: load module, enable at boot, and import pool if necessary
configure_zfs() {
    ZPOOL_NAME="WD_BLACK"
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import "$ZPOOL_NAME"; then
            die "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    fi

    if ! zfs set mountpoint=/media/"$ZPOOL_NAME" "$ZPOOL_NAME"; then
        warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log INFO "ZFS pool '$ZPOOL_NAME' mountpoint set to /media/$ZPOOL_NAME."
    fi
}

# Clone GitHub repositories into the user's home directory
setup_repos() {
    log INFO "Setting up GitHub repositories for user '$USERNAME'..."
    GH_DIR="/home/$USERNAME/github"
    if ! mkdir -p "$GH_DIR"; then
        die "Failed to create GitHub directory at $GH_DIR."
    fi

    for repo in bash windows web python go misc; do
        REPO_DIR="$GH_DIR/$repo"
        [ -d "$REPO_DIR" ] && {
            log INFO "Removing existing directory for repository '$repo'."
            rm -rf "$REPO_DIR"
        }
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            warn "Failed to clone repository '$repo'."
        else
            chown -R "$USERNAME:$USERNAME" "$REPO_DIR"
            log INFO "Repository '$repo' cloned successfully."
        fi
    done
}

# ------------------------------------------------------------------------------
# 7. FINALIZATION
# ------------------------------------------------------------------------------

# Configure periodic system maintenance tasks using cron
configure_periodic() {
    log INFO "Configuring periodic system maintenance tasks..."
    CRON_FILE="/etc/cron.daily/debian_maintenance"
    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Debian maintenance script (added by debian_setup script)
apt-get update -qq && apt-get upgrade -y && apt-get autoremove -y
EOF
    chmod +x "$CRON_FILE" || warn "Failed to set execute permission on $CRON_FILE"
    log INFO "Periodic maintenance script created at $CRON_FILE."
}

# Log final system status
final_checks() {
    log INFO "Performing final system checks..."
    log INFO "Kernel version: $(uname -r)"
    log INFO "Disk usage: $(df -h /)"
    log INFO "Physical memory: $(free -h | awk '/^Mem:/{print $2}')"
}

# Prompt for system reboot after a brief delay
prompt_reboot() {
    log INFO "Setup complete. The system will reboot in 10 seconds. Press Ctrl+C to cancel."
    sleep 10
    shutdown -r now
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------

main() {
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
    configure_periodic
    configure_sysctl
    install_zig
    i3_config
    final_checks
    prompt_reboot
}

main "$@"