#!/usr/local/bin/bash
#
# FreeBSD Server Setup Script v4.0
#
# Overview:
#   This script automates the initial configuration of a FreeBSD server. It updates the system,
#   installs essential packages in parallel, hardens security settings, configures network services,
#   and sets up a Caddy reverse proxy.
#
# Features:
#   - System update and package installations using pkg (all packages installed concurrently)
#   - Automated creation of a new user account with secure default settings (default password "changeme")
#   - Enhanced SSH configuration and security hardening
#   - Dynamic PF firewall configuration
#   - Deployment and configuration of a Caddy reverse proxy for HTTPS traffic
#
# Usage:
#   Run this script as root (e.g., via sudo) to fully configure your FreeBSD server.
#
# Author: dunamismax (improved by ChatGPT)
# Version: 4.0
# Date: 02/20/2025

set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants
#--------------------------------------------------
readonly LOG_FILE="/var/log/freebsd_setup.log"
readonly USERNAME="sawyer"
readonly USER_HOME="/home/${USERNAME}"

# Terminal color definitions for logging output
readonly RED='\033[0;31m'
readonly YELLOW='\033[0;33m'
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'  # No Color

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

#--------------------------------------------------
# Logging and Error Handling Functions
#--------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local msg="$*"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)  color="${GREEN}" ;;
        WARN|WARNING) color="${YELLOW}"; level="WARN" ;;
        ERROR) color="${RED}" ;;
        DEBUG) color="${BLUE}" ;;
        *)     color="${NC}" ; level="INFO" ;;
    esac
    local entry="[$ts] [${level^^}] $msg"
    echo "$entry" >> "$LOG_FILE"
    printf "${color}%s${NC}\n" "$entry" >&2
}

handle_error() {
    local msg="${1:-An error occurred.}"
    local code="${2:-1}"
    log ERROR "$msg (Exit code: ${code})"
    log ERROR "Failure at line ${BASH_LINENO[0]} in function ${FUNCNAME[1]:-main}"
    exit "$code"
}

trap 'handle_error "Unexpected error encountered."' ERR

#--------------------------------------------------
# Utility Functions
#--------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]
Automates FreeBSD server setup and configuration.

Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "This script must be run as root."
    fi
}

check_network() {
    log INFO "Verifying network connectivity..."
    if ! ping -c1 -t5 google.com &>/dev/null; then
        log WARN "Network connectivity appears to be unavailable."
    else
        log INFO "Network connectivity verified."
    fi
}

#--------------------------------------------------
# System Update and Package Installation
#--------------------------------------------------
update_system() {
    log INFO "Updating pkg repositories..."
    pkg update || log WARN "pkg update encountered issues."
    log INFO "Upgrading installed packages..."
    pkg upgrade -y || log WARN "pkg upgrade encountered issues."
}

install_packages() {
    log INFO "Installing essential packages in parallel..."
    local packages=(
        bash vim nano zsh screen tmux mc htop tree ncdu neofetch
        git curl wget rsync
        python3 gcc cmake ninja meson go gdb
        nmap lsof iftop iperf3 netcat tcpdump lynis
        john hydra aircrack-ng nikto
        postgresql14-client postgresql14-server mysql80-client mysql80-server redis
        ruby rust jq doas
    )
    # Use 4 parallel jobs during installation with the "-j" flag.
    local job_count=4
    pkg install -y -j "$job_count" "${packages[@]}" \
        && log INFO "All packages installed successfully." \
        || handle_error "Package installation encountered errors."
}

#--------------------------------------------------
# User and Timezone Configuration
#--------------------------------------------------
create_user() {
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        pw useradd "$USERNAME" -m -s /usr/local/bin/bash -G wheel \
            || log WARN "Failed to create user '$USERNAME'."
        echo "changeme" | pw usermod "$USERNAME" -h 0
        log INFO "User '$USERNAME' created with default password 'changeme'."
    else
        log INFO "User '$USERNAME' already exists."
    fi
}

configure_timezone() {
    local tz="America/New_York"
    log INFO "Setting timezone to ${tz}..."
    if [ -f "/usr/share/zoneinfo/${tz}" ]; then
        cp "/usr/share/zoneinfo/${tz}" /etc/localtime
        echo "$tz" > /etc/timezone
        log INFO "Timezone configured to ${tz}."
    else
        log WARN "Timezone file for ${tz} not found."
    fi
}

#--------------------------------------------------
# Repository and Shell Configuration
#--------------------------------------------------
setup_repos() {
    local repo_dir="${USER_HOME}/github"
    log INFO "Setting up repositories in ${repo_dir}..."
    mkdir -p "$repo_dir"
    for repo in bash windows web python go misc; do
        local target_dir="${repo_dir}/${repo}"
        rm -rf "$target_dir"
        if git clone "https://github.com/dunamismax/${repo}.git" "$target_dir"; then
            log INFO "Cloned repository: $repo"
        else
            log WARN "Failed to clone repository: $repo"
        fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir"
}

copy_shell_configs() {
    log INFO "Copying shell configuration files..."
    for file in .bashrc .profile; do
        local src="${USER_HOME}/github/bash/freebsd/dotfiles/${file}"
        local dest="${USER_HOME}/${file}"
        if [ -f "$src" ]; then
            [ -f "$dest" ] && cp "$dest" "${dest}.bak"
            cp -f "$src" "$dest" \
                && { chown "${USERNAME}:${USERNAME}" "$dest"; log INFO "Copied $src to $dest"; } \
                || log WARN "Failed to copy $src"
        else
            log WARN "Source file $src does not exist."
        fi
    done
}

#--------------------------------------------------
# SSH and Security Configuration
#--------------------------------------------------
configure_ssh() {
    log INFO "Configuring SSH..."
    sysrc sshd_enable="YES"
    service sshd restart || log WARN "Failed to restart SSH service."
}

secure_ssh_config() {
    local sshd_config="/etc/ssh/sshd_config"
    local backup_file="/etc/ssh/sshd_config.bak.$(date +%Y%m%d%H%M%S)"
    if [ -f "$sshd_config" ]; then
        cp "$sshd_config" "$backup_file"
        log INFO "Backed up SSH config to $backup_file."
        sed -i '' 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
        sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config"
        sed -i '' 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
        sed -i '' 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
        log INFO "Hardened SSH configuration."
        service sshd restart || log WARN "Failed to restart SSH after configuration."
    else
        log WARN "SSH configuration file not found."
    fi
}

#--------------------------------------------------
# Plex Media Server Installation
#--------------------------------------------------
install_plex() {
    log INFO "Installing Plex Media Server..."
    pkg install -y plexmediaserver \
        && log INFO "Plex installed successfully." \
        || log WARN "Failed to install Plex Media Server."
}

#--------------------------------------------------
# Firewall Setup Using PF
#--------------------------------------------------
detect_ext_if() {
    local iface
    iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -z "$iface" ]; then
        handle_error "Unable to detect the external interface."
    fi
    echo "$iface"
}

generate_pf_conf() {
    local ext_if="$1"
    local pf_conf="/etc/pf.conf"
    log INFO "Generating pf.conf with external interface: ${ext_if}"
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
    log INFO "pf.conf generated."
}

enable_and_reload_pf() {
    sysrc pf_enable="YES"
    if service pf status >/dev/null 2>&1; then
        pfctl -f /etc/pf.conf \
            && log INFO "PF configuration reloaded." \
            || log WARN "PF reload failed."
    else
        service pf start \
            && log INFO "PF service started." \
            || handle_error "Failed to start PF service."
    fi
}

configure_firewall() {
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
    local bin_dir="${USER_HOME}/bin"
    local src_dir="${USER_HOME}/github/bash/freebsd/_scripts/"
    mkdir -p "$bin_dir"
    log INFO "Deploying user scripts from ${src_dir} to ${bin_dir}..."
    rsync -ah --delete "$src_dir" "$bin_dir" \
        && { find "$bin_dir" -type f -exec chmod 755 {} \; ; log INFO "User scripts deployed."; } \
        || log WARN "Failed to deploy user scripts."
}

setup_cron() {
    log INFO "Starting cron service..."
    service cron start || log WARN "Cron service failed to start."
}

configure_periodic() {
    local cron_file="/etc/periodic/daily/freebsd_maintenance"
    log INFO "Configuring daily maintenance tasks..."
    [ -f "$cron_file" ] && mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" \
        && log INFO "Existing maintenance script backed up."
    cat <<'EOF' > "$cron_file"
#!/bin/sh
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
    chmod +x "$cron_file" && log INFO "Daily maintenance script created." || log WARN "Failed to set execute permission on maintenance script."
}

final_checks() {
    log INFO "Performing final system checks:"
    echo "Kernel: $(uname -r)"
    echo "Uptime: $(uptime)"
    df -h /
    swapinfo -h || true
}

home_permissions() {
    log INFO "Setting ownership and permissions for ${USER_HOME}..."
    chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}"
    find "${USER_HOME}" -type d -exec chmod g+s {} \;
}

install_fastfetch() {
    log INFO "Installing Fastfetch..."
    pkg install -y fastfetch \
        && log INFO "Fastfetch installed successfully." \
        || log WARN "Fastfetch installation failed."
}

set_bash_shell() {
    if ! command -v /usr/local/bin/bash &>/dev/null; then
        log INFO "Bash not found; installing..."
        pkg install -y bash || { log WARN "Bash installation failed."; return 1; }
    fi
    if ! grep -qxF "/usr/local/bin/bash" /etc/shells; then
        echo "/usr/local/bin/bash" >> /etc/shells
        log INFO "Added /usr/local/bin/bash to /etc/shells."
    fi
    chsh -s /usr/local/bin/bash "$USERNAME" && log INFO "Default shell for ${USERNAME} set to /usr/local/bin/bash."
}

install_and_configure_caddy_proxy() {
    log INFO "Installing Caddy reverse proxy..."
    pkg install -y caddy || handle_error "Failed to install Caddy."
    local caddyfile="/usr/local/etc/caddy/Caddyfile"
    [ -f "$caddyfile" ] && cp "$caddyfile" "${caddyfile}.backup.$(date +%Y%m%d%H%M%S)" && log INFO "Backed up existing Caddyfile."
    log INFO "Writing new Caddyfile configuration..."
    cat <<'EOF' > "$caddyfile"
{
    # Global options block (customize as needed)
    # email your-email@example.com
}

# Redirect HTTP to HTTPS
http:// {
    redir https://{host}{uri} permanent
}

# Reverse proxy configuration for HTTPS
https://dunamismax.com, https://www.dunamismax.com {
    reverse_proxy 127.0.0.1:80
}
EOF
    sysrc caddy_enable="YES"
    if service caddy status >/dev/null 2>&1; then
        service caddy reload && log INFO "Caddy reloaded successfully." || {
            service caddy start && log INFO "Caddy started successfully." || handle_error "Failed to start/reload Caddy."
        }
    else
        service caddy start && log INFO "Caddy started successfully." || handle_error "Failed to start Caddy service."
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
    deploy_user_scripts
    setup_cron
    configure_periodic
    install_fastfetch
    set_bash_shell
    final_checks
    home_permissions
    prompt_reboot
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi