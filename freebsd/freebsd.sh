#!/usr/local/bin/bash
#
# FreeBSD Server Setup Script v1.0
#
# Overview:
#   This script streamlines the initial configuration of a FreeBSD server by automating
#   a wide range of setup tasks. It not only updates the system and installs essential
#   command-line tools, but also enhances security, configures network services, and 
#   implements robust backup routines.
#
# Features:
#   - System updates and package installations using pkg
#   - Automated creation of a new user account with secure default settings (password to be changed immediately)
#   - Comprehensive SSH configuration and hardening for enhanced security
#   - Dynamic firewall configuration using PF, with automatic backup of previous settings
#   - Scheduled system and Plex Media Server backups with retention management
#   - Deployment and configuration of a Caddy reverse proxy to manage HTTPS traffic
#
# Usage:
#   Run this script as root (e.g., via sudo) to fully configure your FreeBSD server.
#
# Prerequisites:
#   - A FreeBSD system with the pkg package manager installed.
#
# Author: dunamismax
# Version: 1.0
# Date: 02/20/2025

set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants and Variables
#--------------------------------------------------
readonly LOG_FILE="/var/log/freebsd_setup.log"
readonly USERNAME="sawyer"
readonly USER_HOME="/home/${USERNAME}"

# Color definitions for logging output
readonly RED='\033[0;31m'
readonly YELLOW='\033[0;33m'
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'  # No Color

# Ensure the log directory exists with proper permissions
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

#--------------------------------------------------
# Error Handling Function
#--------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"
    log ERROR "${error_message} (Exit Code: ${exit_code})"
    log ERROR "Script failed at line ${LINENO} in function ${FUNCNAME[1]:-main}."
    echo "ERROR: ${error_message} (Exit Code: ${exit_code})" >&2
    exit "${exit_code}"
}

# Trap any error and call handle_error
trap 'handle_error "Script failed at line ${LINENO} with exit code $?"' ERR

#--------------------------------------------------
# Logging Function
#--------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Set log color based on the log level (converted to uppercase)
    case "${level^^}" in
        INFO)   local color="${GREEN}" ;;
        WARN|WARNING) local color="${YELLOW}"; level="WARN" ;;
        ERROR)  local color="${RED}" ;;
        DEBUG)  local color="${BLUE}" ;;
        *)      local color="${NC}" ; level="INFO" ;;
    esac

    local log_entry="[$timestamp] [${level^^}] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

#--------------------------------------------------
# Display Script Usage Information
#--------------------------------------------------
usage() {
    cat <<EOF
Usage: sudo $(basename "$0") [OPTIONS]
This script automates the setup and configuration of a FreeBSD server.
Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

#--------------------------------------------------
# Pre-Execution Checks
#--------------------------------------------------
# Ensure the script is executed as root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root."
    fi
}

# Verify basic network connectivity by pinging an external host
check_network() {
    log INFO "Checking network connectivity..."
    if ! ping -c1 -t5 google.com &>/dev/null; then
        log WARN "No network connectivity detected."
    else
        log INFO "Network connectivity OK."
    fi
}

#--------------------------------------------------
# System Update and Package Installation
#--------------------------------------------------
update_system() {
    log INFO "Updating pkg repository..."
    if ! pkg update; then
        log WARN "pkg update encountered issues."
    fi
    log INFO "Upgrading installed packages..."
    if ! pkg upgrade -y; then
        log WARN "pkg upgrade encountered issues."
    fi
}

install_packages() {
    log INFO "Installing essential CLI packages..."
    local PACKAGES=(
        bash vim nano zsh screen tmux mc htop tree ncdu neofetch
        git curl wget rsync
        python3 gcc cmake ninja meson go gdb
        nmap lsof iftop iperf3 netcat tcpdump lynis
        john hydra aircrack-ng nikto
        postgresql14-client postgresql14-server mysql80-client mysql80-server redis
        ruby rust
        jq doas
    )
    for pkg in "${PACKAGES[@]}"; do
        if ! pkg install -y "$pkg"; then
            log WARN "Package $pkg failed to install."
        else
            log INFO "Installed package: $pkg"
        fi
    done
}

#--------------------------------------------------
# User and Timezone Configuration
#--------------------------------------------------
create_user() {
    # Create a new user if it does not already exist
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        if ! pw useradd "$USERNAME" -m -s /usr/local/bin/bash -G wheel; then
            log WARN "Failed to create user '$USERNAME'."
        else
            # Set default password (should be changed immediately)
            echo "changeme" | pw usermod "$USERNAME" -h 0
            log INFO "User '$USERNAME' created with default password 'changeme'."
        fi
    else
        log INFO "User '$USERNAME' already exists."
    fi
}

configure_timezone() {
    local TIMEZONE="America/New_York"
    log INFO "Setting timezone to ${TIMEZONE}..."
    if [ -f "/usr/share/zoneinfo/${TIMEZONE}" ]; then
        cp "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
        echo "$TIMEZONE" > /etc/timezone
        log INFO "Timezone set to ${TIMEZONE}."
    else
        log WARN "Timezone file for ${TIMEZONE} not found."
    fi
}

#--------------------------------------------------
# Repository and Shell Configuration
#--------------------------------------------------
setup_repos() {
    # Clone repositories to the user's github directory
    local repo_dir="${USER_HOME}/github"
    log INFO "Cloning repositories into ${repo_dir}..."
    mkdir -p "$repo_dir"
    for repo in bash windows web python go misc; do
        local target_dir="${repo_dir}/${repo}"
        rm -rf "$target_dir"
        if ! git clone "https://github.com/dunamismax/${repo}.git" "$target_dir"; then
            log WARN "Failed to clone repository: ${repo}"
        else
            log INFO "Cloned repository: ${repo}"
        fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir"
}

copy_shell_configs() {
    # Copy basic shell configuration files (.bashrc, .profile)
    log INFO "Copying shell configuration files..."
    for file in .bashrc .profile; do
        local src="${USER_HOME}/github/bash/freebsd/dotfiles/${file}"
        local dest="${USER_HOME}/${file}"
        if [ -f "$src" ]; then
            [ -f "$dest" ] && cp "$dest" "${dest}.bak"
            if ! cp -f "$src" "$dest"; then
                log WARN "Failed to copy ${src} to ${dest}."
            else
                chown "${USERNAME}:${USERNAME}" "$dest"
                log INFO "Copied ${src} to ${dest}."
            fi
        else
            log WARN "Source file ${src} not found."
        fi
    done
}

#--------------------------------------------------
# SSH and Security Configuration
#--------------------------------------------------
configure_ssh() {
    # Enable SSH daemon via rc.conf if not already enabled
    log INFO "Configuring SSH..."
    if sysrc sshd_enable >/dev/null 2>&1; then
        log INFO "sshd_enable already set."
    else
        sysrc sshd_enable="YES"
        log INFO "sshd_enable set to YES."
    fi
    if ! service sshd restart; then
        log WARN "Failed to restart sshd."
    fi
}

secure_ssh_config() {
    # Harden SSH configuration settings
    local sshd_config="/etc/ssh/sshd_config"
    local backup_file="/etc/ssh/sshd_config.bak"
    if [ -f "$sshd_config" ]; then
        cp "$sshd_config" "$backup_file"
        log INFO "Backed up SSH config to ${backup_file}."
        sed -i '' 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
        sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config"
        sed -i '' 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
        sed -i '' 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
        log INFO "SSH configuration hardened."
        if ! service sshd restart; then
            log WARN "Failed to restart sshd after hardening."
        fi
    else
        log WARN "SSHD configuration file not found."
    fi
}

#--------------------------------------------------
# Plex Media Server Installation
#--------------------------------------------------
install_plex() {
    log INFO "Installing Plex Media Server..."
    if pkg install -y plexmediaserver; then
        log INFO "Plex Media Server installed successfully."
    else
        log WARN "Failed to install Plex Media Server."
    fi
}

#--------------------------------------------------
# Backup Functions for System and Plex Data
#--------------------------------------------------
freebsd_perform_backup() {
    log INFO "Starting backup and compression to ${DESTINATION}/${BACKUP_NAME}"
    if tar -I pigz -cf "${DESTINATION}/${BACKUP_NAME}" "${EXCLUDES_ARGS[@]}" -C / .; then
        log INFO "Backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Backup process failed."
    fi
}

freebsd_cleanup_backups() {
    log INFO "Removing backups in ${DESTINATION} older than ${RETENTION_DAYS} days"
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +"${RETENTION_DAYS}" -delete; then
        log INFO "Old backups removed."
    else
        log WARN "Failed to remove some old backups."
    fi
}

backup_freebsd_system() {
    local SOURCE="/"
    local DESTINATION="/mnt/WD_BLACK/BACKUP/freebsd-backups"
    local RETENTION_DAYS=7
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_NAME="backup-${TIMESTAMP}.tar.gz"

    # Build exclusion arguments to omit directories that should not be backed up
    local EXCLUDES=( "./proc/*" "./sys/*" "./dev/*" "./run/*" "./tmp/*" "./mnt/*" "./media/*" "./swapfile" "./lost+found" "./var/tmp/*" "./var/cache/*" "./var/log/*" "*.iso" "*.tmp" "*.swap.img" )
    local EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="${EXCLUDE}")
    done

    freebsd_perform_backup
    freebsd_cleanup_backups
}

plex_perform_backup() {
    log INFO "Starting on-the-fly Plex backup and compression to ${DESTINATION}/${BACKUP_NAME}"
    if tar -I pigz --one-file-system -cf "${DESTINATION}/${BACKUP_NAME}" -C "$SOURCE" .; then
        log INFO "Plex backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Plex backup process failed."
    fi
}

plex_cleanup_backups() {
    log INFO "Removing Plex backups older than ${RETENTION_DAYS} days from ${DESTINATION}"
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +"${RETENTION_DAYS}" -delete; then
        log INFO "Old Plex backups removed."
    else
        log WARN "Failed to remove some old Plex backups."
    fi
}

backup_plex_data() {
    local SOURCE="/usr/local/plexdata/Library/Application Support/Plex Media Server/"
    local DESTINATION="/mnt/WD_BLACK/BACKUP/plex-backups"
    local RETENTION_DAYS=7
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_NAME="plex-backup-${TIMESTAMP}.tar.gz"

    if [[ ! -d "$SOURCE" ]]; then
        handle_error "Plex source directory '${SOURCE}' does not exist."
    fi
    mkdir -p "$DESTINATION" || handle_error "Failed to create destination directory: ${DESTINATION}"
    if ! mount | grep -q "$DESTINATION"; then
        handle_error "Destination mount point for '${DESTINATION}' is not available."
    fi

    plex_perform_backup
    plex_cleanup_backups
}

#--------------------------------------------------
# Firewall Setup Functions using PF
#--------------------------------------------------
backup_pf_conf() {
    local pf_conf="/etc/pf.conf"
    if [ -f "$pf_conf" ]; then
        local backup="/etc/pf.conf.backup.$(date +%Y%m%d%H%M%S)"
        cp "$pf_conf" "$backup"
        log INFO "Existing pf.conf backed up to ${backup}"
    else
        log INFO "No existing /etc/pf.conf found. Continuing."
    fi
}

detect_ext_if() {
    # Detect the external network interface by checking the default route
    local iface
    iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -z "$iface" ]; then
        log ERROR "Could not determine the external interface. Please set it manually."
        exit 1
    fi
    echo "$iface"
}

generate_pf_conf() {
    local ext_if="$1"
    local pf_conf="/etc/pf.conf"
    log INFO "Generating new ${pf_conf} with external interface: ${ext_if}"
    cat <<EOF > "$pf_conf"
#
# pf.conf generated on $(date)
#
ext_if = "${ext_if}"
set skip on lo
scrub in all
block in all
pass out all keep state
pass in on \$ext_if proto tcp from any to (\$ext_if) port { 22, 80, 443 } flags S/SA keep state
pass in on \$ext_if proto tcp from any to (\$ext_if) port 32400 keep state
pass in on \$ext_if proto udp from any to (\$ext_if) port { 1900, 32410, 32412, 32413, 32414 } keep state
EOF
    log INFO "New pf.conf generated."
}

enable_and_reload_pf() {
    if ! sysrc -n pf_enable 2>/dev/null | grep -q "YES"; then
        sysrc pf_enable="YES"
        log INFO "Set pf_enable to YES in rc.conf."
    fi
    if ! service pf status >/dev/null 2>&1; then
        service pf start
        log INFO "PF service started."
    else
        pfctl -f /etc/pf.conf && log INFO "PF configuration reloaded successfully."
    fi
}

configure_firewall() {
    check_root
    backup_pf_conf
    local ext_if
    ext_if=$(detect_ext_if)
    generate_pf_conf "$ext_if"
    enable_and_reload_pf
    log INFO "Firewall configuration complete."
}

#--------------------------------------------------
# Additional Server Setup Functions
#--------------------------------------------------
deploy_user_scripts() {
    # Copy custom user scripts into the user's bin directory
    local bin_dir="${USER_HOME}/bin"
    local scripts_src="${USER_HOME}/github/bash/freebsd/_scripts/"
    log INFO "Deploying user scripts from ${scripts_src} to ${bin_dir}..."
    mkdir -p "$bin_dir"
    if rsync -ah --delete "$scripts_src" "$bin_dir"; then
        find "$bin_dir" -type f -exec chmod 755 {} \;
        log INFO "User scripts deployed successfully."
    else
        log WARN "Failed to deploy user scripts."
    fi
}

setup_cron() {
    # Start the cron service for scheduled tasks
    log INFO "Starting cron service..."
    if ! service cron start; then
        log WARN "Failed to start cron."
    fi
}

configure_periodic() {
    # Create or update a daily maintenance script in /etc/periodic/daily/
    local cron_file="/etc/periodic/daily/freebsd_maintenance"
    log INFO "Configuring daily system maintenance tasks..."
    if [ -f "$cron_file" ]; then
        mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" && \
          log INFO "Existing periodic script backed up." || \
          log WARN "Failed to backup existing periodic script."
    fi
    cat <<'EOF' > "$cron_file"
#!/bin/sh
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
    if chmod +x "$cron_file"; then
        log INFO "Daily maintenance script created at ${cron_file}."
    else
        log WARN "Failed to set execute permission on ${cron_file}."
    fi
}

final_checks() {
    # Output final system details for verification
    log INFO "Performing final system checks:"
    echo "Kernel: $(uname -r)"
    echo "Uptime: $(uptime)"
    df -h /
    swapinfo -h || true
}

home_permissions() {
    # Ensure proper ownership and group settings for the user's home directory
    log INFO "Setting ownership and permissions for ${USER_HOME}..."
    chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}"
    find "${USER_HOME}" -type d -exec chmod g+s {} \;
}

install_fastfetch() {
    log INFO "Installing Fastfetch (system information tool)..."
    if pkg install -y fastfetch; then
        log INFO "Fastfetch installed successfully."
    else
        log WARN "Failed to install Fastfetch."
    fi
}

set_bash_shell() {
    # Ensure bash is installed and set as the default shell for the new user
    if [ "$(id -u)" -ne 0 ]; then
        log WARN "set_bash_shell requires root privileges."
        return 1
    fi
    if [ ! -x /usr/local/bin/bash ]; then
        log INFO "Bash not found. Installing via pkg..."
        if ! pkg install -y bash; then
            log WARN "Failed to install Bash."
            return 1
        fi
    fi
    if ! grep -Fxq "/usr/local/bin/bash" /etc/shells; then
        echo "/usr/local/bin/bash" >> /etc/shells
        log INFO "Added /usr/local/bin/bash to /etc/shells."
    fi
    chsh -s /usr/local/bin/bash "$USERNAME"
    log INFO "Default shell for ${USERNAME} changed to /usr/local/bin/bash."
}

install_and_configure_caddy_proxy() {
    # Install and configure Caddy as a reverse proxy service
    log INFO "Installing Caddy reverse proxy..."
    if ! pkg install -y caddy; then
        handle_error "Failed to install Caddy."
    fi

    local caddyfile="/usr/local/etc/caddy/Caddyfile"
    if [ -f "$caddyfile" ]; then
        cp "$caddyfile" "${caddyfile}.backup.$(date +%Y%m%d%H%M%S)"
        log INFO "Backed up existing Caddyfile."
    fi

    log INFO "Writing new Caddyfile configuration for reverse proxy..."
    cat <<'EOF' > "$caddyfile"
{
    # Global options block (customize as needed)
    # Uncomment and set your email for automatic HTTPS certificates:
    # email your-email@example.com
}

# Redirect all HTTP traffic to HTTPS
http:// {
    redir https://{host}{uri} permanent
}

# Reverse proxy configuration for HTTPS
https://dunamismax.com, https://www.dunamismax.com {
    reverse_proxy 127.0.0.1:80
}
EOF

    log INFO "Enabling Caddy service..."
    sysrc caddy_enable="YES"

    if service caddy status >/dev/null 2>&1; then
        if service caddy reload; then
            log INFO "Caddy reloaded successfully."
        else
            log WARN "Failed to reload Caddy. Attempting to start Caddy..."
            if ! service caddy start; then
                handle_error "Failed to start Caddy service."
            fi
        fi
    else
        if service caddy start; then
            log INFO "Caddy started successfully."
        else
            handle_error "Failed to start Caddy service."
        fi
    fi
}

#--------------------------------------------------
# Prompt for Reboot
#--------------------------------------------------
prompt_reboot() {
    read -rp "Reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot canceled. Please reboot later to apply all changes."
    fi
}

#--------------------------------------------------
# Main Execution Flow
#--------------------------------------------------
main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage ;;
            *) log WARN "Unknown option: $1"; usage ;;
        esac
        shift
    done

    check_root
    check_network
    update_system
    install_packages
    create_user
    configure_timezone
    setup_repos
    copy_shell_configs
    configure_ssh
    secure_ssh_config
    install_plex
    install_and_configure_caddy_proxy
    configure_firewall
    backup_freebsd_system
    backup_plex_data
    deploy_user_scripts
    setup_cron
    configure_periodic
    install_fastfetch
    set_bash_shell
    final_checks
    home_permissions
    prompt_reboot
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi