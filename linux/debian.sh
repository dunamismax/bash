#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: debian_setup.sh
# Description: Automated Debian Setup & Hardening Script with enhanced logging,
#              Nord‑themed color output, progress bars, and robust error handling.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./debian_setup.sh
#
# Notes:
#   - This script must be run as root.
#   - Logs are stored in /var/log/debian_setup.log.
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

# Essential Package List (space‑delimited)
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

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9
NORD5='\033[38;2;229;233;240m'   # #E5E9F0
NORD6='\033[38;2;236;239;244m'   # #ECEFF4
NORD7='\033[38;2;143;188;187m'   # #8FBCBB
NORD8='\033[38;2;136;192;208m'   # #88C0D0
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD10='\033[38;2;94;129;172m'   # #5E81AC
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD12='\033[38;2;208;135;112m'  # #D08770
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NORD15='\033[38;2;180;142;173m'  # #B48EAD
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    case "$upper_level" in
        INFO)  color="${NORD14}" ;;  # Greenish
        WARN)  color="${NORD13}" ;;  # Yellowish
        ERROR) color="${NORD11}" ;;  # Reddish
        DEBUG) color="${NORD9}"  ;;  # Bluish
        *)     color="$NC"     ;;
    esac

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

warn() {
    log WARN "$@"
}

handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup commands here
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# PROGRESS BAR FUNCTION
# ------------------------------------------------------------------------------
progress_bar() {
    # Usage: progress_bar "Message" [duration_in_seconds]
    local message="${1:-Processing...}"
    local duration="${2:-5}"
    local steps=50
    local sleep_time
    sleep_time=$(echo "$duration / $steps" | bc -l)
    local progress=0
    local filled=""
    local unfilled=""

    printf "\n${NORD8}%s${NC}\n" "$message"

    for (( i = 1; i <= steps; i++ )); do
        progress=$(( i * 100 / steps ))
        filled=$(printf "%-${i}s" | tr ' ' '█')
        unfilled=$(printf "%-$(( steps - i ))s" | tr ' ' '░')
        printf "\r${NORD8}[%s%s] %3d%%%s" "$filled" "$unfilled" "$progress" "$NC"
        sleep "$sleep_time"
    done
    printf "\n"
}

# ------------------------------------------------------------------------------
# SECTION HEADER FUNCTION
# ------------------------------------------------------------------------------
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# ------------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------------------------

# Ensure the script is run as root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

# Check for network connectivity by pinging a reliable host
check_network() {
    print_section "Network Connectivity Check"
    log INFO "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        handle_error "No network connectivity. Please verify your network settings."
    fi
    log INFO "Network connectivity verified."
}

# Update package repositories and upgrade system packages
update_system() {
    print_section "System Update & Upgrade"
    log INFO "Updating package repositories..."
    if ! apt-get update -qq; then
        handle_error "Failed to update package repositories."
    fi

    log INFO "Upgrading system packages..."
    if ! apt-get upgrade -y; then
        handle_error "Failed to upgrade packages."
    fi

    progress_bar "System update complete..." 3
}

# Create the specified user if it does not already exist
ensure_user() {
    print_section "User Setup"
    if id -u "$USERNAME" >/dev/null 2>&1; then
        log INFO "User '$USERNAME' already exists."
    else
        log INFO "Creating user '$USERNAME'..."
        if ! useradd -m -s /bin/bash "$USERNAME"; then
            handle_error "Failed to create user '$USERNAME'."
        fi
        if ! passwd -l "$USERNAME" >/dev/null 2>&1; then
            warn "Failed to lock password for user '$USERNAME'."
        fi
        log INFO "User '$USERNAME' created successfully."
    fi
}

# Configure the sudoers file for the specified user
configure_sudoers() {
    print_section "Sudoers Configuration"
    local SUDOERS_FILE="/etc/sudoers"

    # Backup sudoers file if a backup does not already exist.
    if [ ! -f "${SUDOERS_FILE}.bak" ]; then
        cp "$SUDOERS_FILE" "${SUDOERS_FILE}.bak" || warn "Unable to create backup of sudoers file"
        log INFO "Backup of sudoers file created at ${SUDOERS_FILE}.bak"
    fi

    # Append entry for the user if it does not exist.
    if grep -Eq "^[[:space:]]*${USERNAME}[[:space:]]+ALL=\(ALL\)[[:space:]]+ALL" "$SUDOERS_FILE"; then
        log INFO "Sudoers entry for '${USERNAME}' already exists."
    else
        echo "${USERNAME} ALL=(ALL) ALL" >> "$SUDOERS_FILE" || warn "Failed to append sudoers entry for '${USERNAME}'"
        log INFO "Added sudoers entry for '${USERNAME}'."
    fi

    # Validate sudoers file syntax.
    if ! visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
        handle_error "Sudoers file syntax error! Please review ${SUDOERS_FILE}."
    fi

    log INFO "Sudoers configuration complete."
}

# Apply kernel performance tuning parameters
configure_sysctl() {
    print_section "Kernel Performance Tuning"
    local SYSCTL_CONF="/etc/sysctl.conf"
    local BACKUP_CONF="/etc/sysctl.conf.bak"

    if [ ! -f "$BACKUP_CONF" ]; then
        cp "$SYSCTL_CONF" "$BACKUP_CONF" || warn "Unable to create a backup of $SYSCTL_CONF"
        log INFO "Backup of sysctl.conf created at $BACKUP_CONF"
    else
        log INFO "Backup already exists at $BACKUP_CONF"
    fi

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

    if sysctl -p; then
        log INFO "Kernel parameters reloaded successfully."
    else
        warn "Failed to reload sysctl parameters. Please review $SYSCTL_CONF for errors."
    fi
}

# Install essential system packages
install_packages() {
    print_section "Essential Package Installation"
    log INFO "Installing packages..."
    if ! apt-get install -y ${PACKAGES}; then
        handle_error "Failed to install one or more packages."
    fi
    progress_bar "Package installation complete..." 3
}

# Install the Zig programming language
install_zig() {
    print_section "Zig Installation"
    log INFO "Installing Zig programming language..."
    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig is already installed at $(command -v zig). Skipping installation."
        return 0
    fi

    if ! apt-get install -y zig; then
        handle_error "Failed to install Zig."
    fi

    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig installed successfully and is available at $(command -v zig)."
    else
        handle_error "Zig installation completed but binary not found in PATH."
    fi
}

# Install i3 window manager and configure ly display manager via Zig
i3_config() {
    print_section "i3 & LY Configuration"
    log INFO "Installing i3 and its addons..."
    if ! apt-get install -y i3 i3status i3lock dmenu i3blocks; then
        handle_error "Failed to install i3 and its addons."
    fi

    log INFO "Cloning and installing ly login manager from GitHub using Zig..."
    local LY_SRC="/usr/local/src/ly"
    local LY_REPO="https://github.com/fairyglade/ly.git"

    if [ -d "${LY_SRC}/ly" ]; then
        log INFO "Updating existing ly repository in ${LY_SRC}/ly..."
        cd "${LY_SRC}/ly" || handle_error "Cannot change directory to ${LY_SRC}/ly"
        if ! git pull; then
            warn "Failed to update ly repository; continuing with existing code."
        fi
    else
        log INFO "Cloning ly repository into ${LY_SRC}..."
        mkdir -p "${LY_SRC}" || handle_error "Failed to create directory ${LY_SRC}"
        cd "${LY_SRC}" || handle_error "Cannot change directory to ${LY_SRC}"
        if ! git clone "$LY_REPO"; then
            handle_error "Failed to clone ly repository from ${LY_REPO}"
        fi
        cd ly || handle_error "Cannot change directory to ly"
    fi

    log INFO "Compiling ly using Zig..."
    if ! zig build; then
        handle_error "zig build for ly failed."
    fi

    log INFO "Installing ly using Zig..."
    if ! zig build install; then
        handle_error "zig build install for ly failed."
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
# CORE CONFIGURATION FUNCTIONS
# ------------------------------------------------------------------------------

# Harden and configure the SSH server
configure_ssh() {
    print_section "SSH Hardening"
    log INFO "Configuring SSH server..."
    local SSH_CONFIG="/etc/ssh/sshd_config"
    if [ -f "$SSH_CONFIG" ]; then
        cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"
        log INFO "Backup of SSH config saved as ${SSH_CONFIG}.bak"
        sed -i -e 's/^#\?PermitRootLogin.*/PermitRootLogin no/' \
               -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
               -e 's/^#\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' "$SSH_CONFIG"
        if ! systemctl restart ssh; then
            handle_error "Failed to restart SSH service."
        fi
        log INFO "SSH configuration updated and service restarted."
    else
        warn "SSH configuration file not found at $SSH_CONFIG."
    fi
}

# Configure the firewall using ufw
configure_firewall() {
    print_section "Firewall Configuration"
    log INFO "Configuring firewall with ufw..."
    ufw default deny incoming || warn "Failed to set default deny incoming"
    ufw default allow outgoing || warn "Failed to set default allow outgoing"
    ufw allow 22/tcp || warn "Failed to allow SSH"
    ufw allow 80/tcp || warn "Failed to allow HTTP"
    ufw allow 443/tcp || warn "Failed to allow HTTPS"
    ufw allow 32400/tcp || warn "Failed to allow Plex Media Server port"
    ufw --force enable || handle_error "Failed to enable ufw firewall"
    log INFO "Firewall configured and enabled."
}

# Enable and start the fail2ban service
configure_fail2ban() {
    print_section "fail2ban Configuration"
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
# STORAGE & SERVICES CONFIGURATION
# ------------------------------------------------------------------------------

# Install and configure Plex Media Server
install_plex() {
    print_section "Plex Media Server Installation"
    log INFO "Installing Plex Media Server..."
    if ! apt-get install -y plexmediaserver; then
        handle_error "Plex Media Server installation failed."
    fi

    local PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" \
            || warn "Failed to set Plex user in $PLEX_CONF"
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

# Configure ZFS: import pool and set mountpoint
configure_zfs() {
    print_section "ZFS Configuration"
    local ZPOOL_NAME="WD_BLACK"
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
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
    print_section "GitHub Repositories Setup"
    log INFO "Setting up GitHub repositories for user '$USERNAME'..."
    local GH_DIR="/home/$USERNAME/github"
    if ! mkdir -p "$GH_DIR"; then
        handle_error "Failed to create GitHub directory at $GH_DIR."
    fi

    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"
        if [ -d "$REPO_DIR" ]; then
            log INFO "Removing existing directory for repository '$repo'."
            rm -rf "$REPO_DIR"
        fi
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            warn "Failed to clone repository '$repo'."
        else
            chown -R "$USERNAME:$USERNAME" "$REPO_DIR"
            log INFO "Repository '$repo' cloned successfully."
        fi
    done
}

# Configure periodic system maintenance tasks via cron
configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log INFO "Configuring periodic system maintenance tasks..."
    local CRON_FILE="/etc/cron.daily/debian_maintenance"
    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Debian maintenance script (added by debian_setup script)
apt-get update -qq && apt-get upgrade -y && apt-get autoremove -y
EOF
    chmod +x "$CRON_FILE" || warn "Failed to set execute permission on $CRON_FILE"
    log INFO "Periodic maintenance script created at $CRON_FILE."
}

# ------------------------------------------------------------------------------
# FINALIZATION FUNCTIONS
# ------------------------------------------------------------------------------

# Log final system status
final_checks() {
    print_section "Final System Checks"
    log INFO "Kernel version: $(uname -r)"
    log INFO "Disk usage: $(df -h /)"
    log INFO "Physical memory: $(free -h | awk '/^Mem:/{print $2}')"
}

# Prompt for system reboot with a countdown progress bar
prompt_reboot() {
    print_section "Reboot Prompt"
    log INFO "Setup complete. The system will reboot shortly. Press Ctrl+C to cancel."
    progress_bar "Rebooting in 10 seconds..." 10
    shutdown -r now
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is executed with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    # Ensure log directory exists and set proper permissions
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Debian setup script execution started."
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