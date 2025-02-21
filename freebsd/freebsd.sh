#!/usr/local/bin/bash
# ==============================================================================
# FreeBSD Server Automation Script v4.2.2 (Improved)
#
# Overview:
#   This script automates the initial configuration of a FreeBSD server.
#   It updates the system, installs essential packages, sets up user accounts,
#   applies security hardening, and configures services such as SSH, PF firewall,
#   Caddy reverse proxy, Wi‑Fi networking, and a desktop environment.
#
# Features:
#   - Comprehensive logging with colored output.
#   - Modular functions for each configuration step.
#   - Automatic backups (via a centralized backup_file helper).
#   - Optional non‑interactive mode (with Wi‑Fi credentials supplied via options).
#
# Usage:
#   Run as root. For help:
#       $(basename "$0") --help
#
# Disclaimer:
#   THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY. USE AT YOUR OWN RISK.
#
# Author: dunamismax (adapted for FreeBSD)
# Version: 4.2.0
# Date: 2025-02-20
# ==============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants & Environment Setup
#--------------------------------------------------
readonly LOG_FILE="/var/log/freebsd_setup.log"
readonly USERNAME="sawyer"
readonly USER_HOME="/freebsd/${USERNAME}"

# Terminal color definitions
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[0;33m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_NC='\033[0m'  # No Color

# Create secure log file
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"
umask 077

# Global options (overridable via CLI)
NON_INTERACTIVE=0
WIFI_SSID=""
WIFI_PSK=""
NO_REBOOT=0

#--------------------------------------------------
# Logging and Error Handling Functions
#--------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local msg="$*"
    local ts color
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    case "${level^^}" in
        INFO)    color="${COLOR_GREEN}" ;;
        WARN|WARNING) color="${COLOR_YELLOW}"; level="WARN" ;;
        ERROR)   color="${COLOR_RED}" ;;
        DEBUG)   color="${COLOR_BLUE}" ;;
        *)       color="${COLOR_NC}" ; level="INFO" ;;
    esac
    local entry="[$ts] [${level^^}] $msg"
    echo "$entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "${color}" "$entry" "${COLOR_NC}" >&2
}

handle_error() {
    local msg="${1:-An unexpected error occurred.}"
    local exit_code="${2:-1}"
    local func="${FUNCNAME[1]:-main}"
    log ERROR "Error on line ${BASH_LINENO[0]} in function ${func}: ${msg}"
    exit "$exit_code"
}
trap 'handle_error "Unexpected error encountered."' ERR

# Utility: Check if a command exists
command_exists() {
    command -v "$1" &>/dev/null
}

# Centralized backup function for configuration files
backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup="${file}.bak.$(date +%Y%m%d%H%M%S)"
        if cp "$file" "$backup"; then
            log INFO "Backed up $file to $backup"
        else
            log WARN "Failed to backup $file"
        fi
    else
        log WARN "File $file not found; skipping backup."
    fi
}

#--------------------------------------------------
# Script Usage and Argument Parsing
#--------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

This script automates the setup and configuration of a FreeBSD server.

Options:
  -h, --help                Show this help message and exit.
  -n, --non-interactive     Run in non-interactive mode.
  -s, --wifi-ssid SSID      Specify Wi‑Fi SSID (non-interactive mode).
  -p, --wifi-psk PSK        Specify Wi‑Fi PSK (leave empty for open networks).
  -r, --no-reboot           Do not prompt for reboot at the end.
EOF
    exit 0
}

# Parse CLI options
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
                log WARN "Unknown option: $1"
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
        handle_error "Script must be run as root."
    fi
}

check_network() {
    log INFO "Verifying network connectivity..."
    if ! ping -c1 google.com &>/dev/null; then
        log WARN "Network connectivity appears unavailable."
    else
        log INFO "Network connectivity verified."
    fi
}

#--------------------------------------------------
# System Update & Package Installation
#--------------------------------------------------
update_system() {
    log INFO "Updating system using freebsd-update..."
    if command_exists freebsd-update; then
        freebsd-update fetch install && log INFO "freebsd-update completed." || log WARN "freebsd-update encountered issues."
    else
        log WARN "freebsd-update not available; skipping system updates."
    fi
}

install_packages() {
    log INFO "Installing essential packages..."
    local packages=(
        bash vim nano zsh screen tmux mc htop tree ncdu neofetch
        git curl wget rsync
        python3 gcc cmake ninja meson go gdb
        nmap lsof iftop iperf3 netcat tcpdump lynis
        john hydra aircrack-ng nikto
        postgresql-client postgresql mysql-client mysql redis
        ruby rust jq doas
    )
    for pkg in "${packages[@]}"; do
        if pkg info -e "$pkg" &>/dev/null; then
            log INFO "Package '$pkg' is already installed."
        else
            if pkg install -y "$pkg"; then
                log INFO "Installed package: $pkg"
            else
                log WARN "Failed to install package: $pkg"
            fi
        fi
    done
}

#--------------------------------------------------
# User and Timezone/NTP Configuration
#--------------------------------------------------
create_user() {
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        if pw useradd "$USERNAME" -m -s /usr/local/bin/bash; then
            echo "changeme" | passwd "$USERNAME"
            log INFO "User '$USERNAME' created with default password 'changeme'. (Change immediately!)"
        else
            log WARN "Failed to create user '$USERNAME'."
        fi
    else
        log INFO "User '$USERNAME' already exists."
    fi
}

configure_timezone() {
    local tz="America/New_York"
    log INFO "Setting timezone to ${tz}..."
    if [ -f "/usr/share/zoneinfo/${tz}" ]; then
        ln -sf "/usr/share/zoneinfo/${tz}" /etc/localtime
        log INFO "Timezone set to ${tz}."
    else
        log WARN "Timezone file for ${tz} not found."
    fi
}

configure_ntp() {
    log INFO "Configuring NTP using ntpd..."
    local ntp_conf="/etc/ntp.conf"
    if [ ! -f "$ntp_conf" ]; then
        cat <<'EOF' > "$ntp_conf"
# Minimal ntpd configuration
server 0.pool.ntp.org
server 1.pool.ntp.org
server 2.pool.ntp.org
server 3.pool.ntp.org
EOF
        log INFO "Created new ntp configuration at $ntp_conf."
    else
        log INFO "ntp configuration file exists at $ntp_conf."
    fi
    sysrc ntpd_enable="YES"
    if service ntpd start; then
        log INFO "ntpd started successfully."
    else
        log WARN "Failed to start ntpd."
    fi
}

#--------------------------------------------------
# Repository and Shell Setup
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
    log INFO "Deploying shell configuration files..."
    for file in .bashrc .profile; do
        local src="${USER_HOME}/github/bash/freebsd/dotfiles/${file}"
        local dest="${USER_HOME}/${file}"
        if [ -f "$src" ]; then
            [ -f "$dest" ] && cp "$dest" "${dest}.bak"
            if cp -f "$src" "$dest"; then
                chown "${USERNAME}:${USERNAME}" "$dest"
                log INFO "Copied $src to $dest"
            else
                log WARN "Failed to copy $src to $dest"
            fi
        else
            log WARN "Source file $src does not exist."
        fi
    done
}

set_bash_shell() {
    if ! command_exists /usr/local/bin/bash; then
        log INFO "Bash not found; installing..."
        if ! pkg install -y bash; then
            log WARN "Bash installation failed."
            return 1
        fi
    fi
    if ! grep -qxF "/usr/local/bin/bash" /etc/shells; then
        echo "/usr/local/bin/bash" >> /etc/shells
        log INFO "Added /usr/local/bin/bash to /etc/shells."
    fi
    if chsh -s /usr/local/bin/bash "$USERNAME"; then
        log INFO "Default shell for ${USERNAME} set to /usr/local/bin/bash."
    else
        log WARN "Failed to set default shell for ${USERNAME}."
    fi
}

#--------------------------------------------------
# SSH and Doas Security Configuration
#--------------------------------------------------
configure_ssh() {
    log INFO "Enabling SSH service..."
    if ! grep -q "^sshd_enable=" /etc/rc.conf; then
        sysrc sshd_enable="YES"
    fi
    if service sshd restart; then
        log INFO "SSHD restarted successfully."
    else
        log WARN "Failed to restart SSHD."
    fi
}

secure_ssh_config() {
    local sshd_config="/etc/ssh/sshd_config"
    backup_file "$sshd_config"
    if [ -f "$sshd_config" ]; then
        sed -i '' 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
        sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config"
        sed -i '' 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
        sed -i '' 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
        log INFO "Hardened SSH configuration."
        if service sshd restart; then
            log INFO "SSHD restarted after configuration changes."
        else
            log WARN "Failed to restart SSHD after changes."
        fi
    else
        log WARN "SSH configuration file not found."
    fi
}

setup_doas() {
    log INFO "Setting up doas configuration..."
    local doas_conf="/etc/doas.conf"
    [ -f "$doas_conf" ] && backup_file "$doas_conf"
    cat <<EOF > "$doas_conf"
# /etc/doas.conf - doas configuration file
permit persist ${USERNAME} as root
EOF
    chmod 600 "$doas_conf"
    log INFO "doas configuration updated and secured."
}

#--------------------------------------------------
# Firewall (PF) Configuration
#--------------------------------------------------
detect_ext_if() {
    local iface
    iface=$(route get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -z "$iface" ]; then
        handle_error "Unable to detect external interface."
    fi
    echo "$iface"
}

generate_pf_conf() {
    local ext_if="$1"
    local pf_conf="/etc/pf.conf"
    log INFO "Generating pf.conf using external interface: ${ext_if}"
    cat <<EOF > "$pf_conf"
#
# pf.conf generated on $(date)
#
ext_if = "${ext_if}"
set skip on lo0
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
    if service pf status &>/dev/null; then
        if pfctl -f /etc/pf.conf; then
            log INFO "PF configuration reloaded."
        else
            log WARN "Failed to reload PF configuration."
        fi
    else
        if service pf start; then
            log INFO "PF service started."
        else
            handle_error "Failed to start PF service."
        fi
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
# Service Installation and Configuration
#--------------------------------------------------
install_plex() {
    log INFO "Installing Plex Media Server..."
    if pkg install -y plexmediaserver; then
        log INFO "Plex installed successfully."
    else
        log WARN "Plex Media Server installation failed or is not available on FreeBSD."
    fi
}

install_and_configure_caddy_proxy() {
    log INFO "Installing Caddy reverse proxy..."
    if pkg install -y caddy; then
        log INFO "Caddy installed successfully."
    else
        handle_error "Failed to install Caddy."
    fi
    local caddy_dir="/usr/local/etc/caddy"
    local caddyfile="${caddy_dir}/Caddyfile"
    mkdir -p "$caddy_dir"
    [ -f "$caddyfile" ] && backup_file "$caddyfile"
    log INFO "Writing new Caddyfile configuration..."
    cat <<'EOF' > "$caddyfile"
{
    # Global options block
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
    if service caddy status &>/dev/null; then
        if service caddy reload; then
            log INFO "Caddy reloaded successfully."
        else
            if service caddy start; then
                log INFO "Caddy started successfully."
            else
                handle_error "Failed to start or reload Caddy."
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

install_fastfetch() {
    log INFO "Installing Fastfetch..."
    if pkg install -y fastfetch; then
        log INFO "Fastfetch installed successfully."
    else
        log WARN "Fastfetch installation failed or is not available on FreeBSD."
    fi
}

#--------------------------------------------------
# Cron and Periodic Maintenance
#--------------------------------------------------
setup_cron() {
    log INFO "Enabling and starting cron service..."
    sysrc cron_enable="YES"
    if service cron start; then
        log INFO "Cron service started."
    else
        log WARN "Cron service failed to start."
    fi
}

configure_periodic() {
    local cron_file="/etc/periodic/daily/freebsd_maintenance"
    log INFO "Configuring daily maintenance tasks..."
    [ -f "$cron_file" ] && backup_file "$cron_file"
    cat <<'EOF' > "$cron_file"
#!/bin/sh
# Daily package update maintenance task
pkg install -yu
EOF
    if chmod +x "$cron_file"; then
        log INFO "Daily maintenance script created and made executable."
    else
        log WARN "Failed to set execute permission on maintenance script."
    fi
}

#--------------------------------------------------
# Wi‑Fi Network Configuration
#--------------------------------------------------
configure_wifi() {
    log INFO "Configuring Wi‑Fi interfaces..."
    local devices
    devices=$(ifconfig -l | tr ' ' '\n' | grep -E '^(ath|iwn|iwm)')
    if [ -z "$devices" ]; then
        log ERROR "No wireless adapters detected."
        return 1
    fi

    for device in $devices; do
        log INFO "Bringing up wireless interface: $device"
        if ifconfig "$device" up; then
            log INFO "Interface $device is up."
        else
            log WARN "Failed to bring up interface $device."
        fi
    done

    local primary_iface
    primary_iface=$(echo "$devices" | head -n 1)
    local ssid psk

    # Use provided Wi‑Fi credentials if in non-interactive mode
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        if [ -z "$WIFI_SSID" ]; then
            log ERROR "Non-interactive mode: Wi‑Fi SSID not provided."
            return 1
        fi
        ssid="$WIFI_SSID"
        psk="$WIFI_PSK"
        log INFO "Using provided Wi‑Fi credentials for interface $primary_iface."
    else
        read -r -p "Enter SSID for primary Wi‑Fi ($primary_iface): " ssid
        if [ -z "$ssid" ]; then
            log ERROR "SSID cannot be empty."
            return 1
        fi
        read -s -r -p "Enter PSK (leave empty for open networks): " psk
        echo
    fi

    local wpa_conf="/etc/wpa_supplicant.conf"
    if [ ! -f "$wpa_conf" ]; then
        touch "$wpa_conf" && chmod 600 "$wpa_conf"
        log INFO "Created $wpa_conf with secure permissions."
    else
        backup_file "$wpa_conf"
    fi

    if grep -q "ssid=\"$ssid\"" "$wpa_conf"; then
        log INFO "Network '$ssid' is already configured in $wpa_conf."
    else
        log INFO "Adding network '$ssid' configuration to $wpa_conf."
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

    if ifconfig "$primary_iface" down && ifconfig "$primary_iface" up; then
        log INFO "Restarted interface $primary_iface."
    else
        log ERROR "Failed to restart interface $primary_iface."
        return 1
    fi

    log INFO "Wi‑Fi configuration completed for all detected devices."
}

#--------------------------------------------------
# Desktop Environment & Additional Tools
#--------------------------------------------------
install_i3_ly_and_tools() {
    log INFO "Installing desktop environment components (i3, Xorg, Zig, ly, XFCE)..."
    local i3_packages=(i3 i3status i3lock dmenu i3blocks feh xorg xinit)
    for pkg in "${i3_packages[@]}"; do
        if pkg info -e "$pkg" &>/dev/null; then
            log INFO "Package '$pkg' is already installed."
        else
            if pkg install -y "$pkg"; then
                log INFO "Installed package: $pkg"
            else
                log WARN "Failed to install package: $pkg"
            fi
        fi
    done

    # Install Zig (FreeBSD binary)
    local zig_url="https://ziglang.org/download/0.12.1/zig-freebsd-x86_64-0.12.1.tar.xz"
    local zig_src_dir="/usr/local/src"
    local zig_tar="${zig_src_dir}/zig-0.12.1.tar.xz"
    local zig_dir="${zig_src_dir}/zig-0.12.1"

    mkdir -p "$zig_src_dir"
    log INFO "Downloading Zig from ${zig_url}..."
    if fetch -o "$zig_tar" "$zig_url"; then
        log INFO "Zig tarball downloaded."
    else
        log ERROR "Failed to download Zig tarball."
        return 1
    fi

    log INFO "Extracting Zig..."
    if tar -xJf "$zig_tar" -C "$zig_src_dir"; then
        log INFO "Zig extracted to ${zig_dir}."
    else
        log ERROR "Failed to extract Zig."
        return 1
    fi

    if [ -x "${zig_dir}/zig" ]; then
        ln -sf "${zig_dir}/zig" /usr/local/bin/zig
        log INFO "Zig binary symlinked to /usr/local/bin/zig."
    else
        log ERROR "Zig binary not found in ${zig_dir}."
        return 1
    fi

    # Clone and build ly display manager using Zig
    local ly_src="${zig_src_dir}/ly"
    [ -d "$ly_src" ] && { log INFO "Removing existing ly source directory..."; rm -rf "$ly_src"; }
    log INFO "Cloning ly repository..."
    if git clone https://github.com/fairyglade/ly.git "$ly_src"; then
        log INFO "ly repository cloned."
    else
        log ERROR "Failed to clone ly repository."
        return 1
    fi

    cd "$ly_src" || { log ERROR "Cannot change directory to ly source."; return 1; }
    log INFO "Building ly with Zig..."
    if zig build; then
        log INFO "ly built successfully."
    else
        log ERROR "ly build failed."
        return 1
    fi

    log INFO "Installing ly..."
    if zig build install; then
        log INFO "ly installed successfully."
    else
        log ERROR "ly installation failed."
        return 1
    fi

    # Create rc.d script for ly (FreeBSD uses rc.d)
    local rc_script="/usr/local/etc/rc.d/ly"
    log INFO "Creating rc.d startup script for ly..."
    cat <<'EOF' > "$rc_script"
#!/bin/sh
#
# PROVIDE: ly
# REQUIRE: DAEMON
# KEYWORD: shutdown
. /etc/rc.subr

name="ly"
rcvar=ly_enable
command="/usr/local/bin/ly"
start_cmd=":; /usr/local/bin/ly &"
stop_cmd=":"

load_rc_config $name
: ${ly_enable:=no}
run_rc_command "$1"
EOF
    chmod +x "$rc_script"
    log INFO "ly rc.d script created. Enable it at boot by adding 'ly_enable=yes' to /etc/rc.conf."
    
    # Install XFCE desktop environment and addons
    log INFO "Installing XFCE desktop environment and addons..."
    local xfce_packages=(xfce4-session xfce4-panel xfce4-appfinder xfce4-settings xfce4-terminal xfdesktop xfwm4 thunar mousepad xfce4-whiskermenu-plugin)
    for pkg in "${xfce_packages[@]}"; do
        if pkg info -e "$pkg" &>/dev/null; then
            log INFO "XFCE package '$pkg' is already installed."
        else
            if pkg install -y "$pkg"; then
                log INFO "Installed XFCE package: $pkg"
            else
                log WARN "Failed to install XFCE package: $pkg"
            fi
        fi
    done

    log INFO "Desktop environment installation complete."
}

#--------------------------------------------------
# Backups and Log Maintenance
#--------------------------------------------------
backup_configs() {
    local backup_dir="/var/backups/freebsd_config_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    log INFO "Backing up key configuration files to $backup_dir..."
    local files_to_backup=(
        "/etc/ssh/sshd_config"
        "/etc/pf.conf"
        "/etc/doas.conf"
        "/etc/ntp.conf"
        "/etc/rc.conf"
    )
    for file in "${files_to_backup[@]}"; do
        if [ -f "$file" ]; then
            if cp "$file" "$backup_dir"; then
                log INFO "Backed up $file"
            else
                log WARN "Failed to backup $file"
            fi
        else
            log WARN "File $file not found; skipping backup."
        fi
    done
}

backup_databases() {
    local backup_dir="/var/backups/db_backups_$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    log INFO "Starting automated database backups to $backup_dir..."
    if command_exists pg_dumpall; then
        if pg_dumpall -U postgres | gzip > "$backup_dir/postgres_backup.sql.gz"; then
            log INFO "PostgreSQL backup completed."
        else
            log WARN "PostgreSQL backup failed."
        fi
    else
        log WARN "pg_dumpall not found; skipping PostgreSQL backup."
    fi
    if command_exists mysqldump; then
        if mysqldump --all-databases | gzip > "$backup_dir/mysql_backup.sql.gz"; then
            log INFO "MySQL backup completed."
        else
            log WARN "MySQL backup failed."
        fi
    else
        log WARN "mysqldump not found; skipping MySQL backup."
    fi
}

rotate_logs() {
    if [ -f "$LOG_FILE" ]; then
        local rotated_file="${LOG_FILE}.$(date +%Y%m%d%H%M%S).gz"
        log INFO "Rotating log file: $LOG_FILE -> $rotated_file"
        if gzip -c "$LOG_FILE" > "$rotated_file" && :> "$LOG_FILE"; then
            log INFO "Log rotation successful."
        else
            log WARN "Log rotation failed."
        fi
    else
        log WARN "Log file $LOG_FILE does not exist."
    fi
}

#--------------------------------------------------
# System Health, Security Audit, and Service Checks
#--------------------------------------------------
system_health_check() {
    log INFO "Performing system health check..."
    log INFO "Uptime: $(uptime)"
    log INFO "Disk Usage:"
    df -h / | while read -r line; do log INFO "$line"; done
    log INFO "Memory Usage:"
    vmstat -s | while read -r line; do log INFO "$line"; done
    log INFO "Load Average: $(sysctl -n kern.boottime)"
}

run_security_audit() {
    log INFO "Running security audit with Lynis..."
    if command_exists lynis; then
        local audit_log="/var/log/lynis_audit_$(date +%Y%m%d%H%M%S).log"
        if lynis audit system --quiet | tee "$audit_log"; then
            log INFO "Lynis audit completed. Log saved to $audit_log."
        else
            log WARN "Lynis audit encountered issues."
        fi
    else
        log WARN "Lynis is not installed; skipping security audit."
    fi
}

check_services() {
    log INFO "Checking status of key services..."
    local services=("sshd" "pf" "cron" "caddy" "ntpd")
    for service_name in "${services[@]}"; do
        if service "$service_name" status &>/dev/null; then
            log INFO "Service $service_name is running."
        else
            log WARN "Service $service_name is not running; attempting restart..."
            if service "$service_name" restart; then
                log INFO "Service $service_name restarted successfully."
            else
                log ERROR "Failed to restart service $service_name."
            fi
        fi
    done
}

verify_firewall_rules() {
    log INFO "Verifying firewall rules..."
    local ports=(22 80 443 32400)
    local host="127.0.0.1"
    for port in "${ports[@]}"; do
        if nc -z -w3 "$host" "$port" 2>/dev/null; then
            log INFO "Port $port on $host is accessible."
        else
            log WARN "Port $port on $host is not accessible. Check PF rules."
        fi
    done
}

update_ssl_certificates() {
    log INFO "Updating SSL/TLS certificates using acme-client..."
    if ! command_exists acme-client; then
        if pkg install -y acme-client; then
            log INFO "acme-client installed successfully."
        else
            log WARN "Failed to install acme-client."
            return 1
        fi
    fi
    if [ -f /etc/acme-client.conf ]; then
        if acme-client -v; then
            log INFO "SSL certificates updated successfully."
        else
            log WARN "Failed to update SSL certificates with acme-client."
        fi
    else
        log WARN "acme-client configuration file not found. Configure /etc/acme-client.conf."
    fi
}

#--------------------------------------------------
# Bhyve Guest Setup
#--------------------------------------------------
setup_vmm_guest() {
    local guest_name="freebsd_guest"
    local guest_img="/usr/local/share/freebsd_guest.img"
    log INFO "Setting up a bhyve guest named $guest_name..."
    if [ ! -f "$guest_img" ]; then
        log WARN "Guest image $guest_img not found. Please provide a valid image."
        return 1
    fi
    local vm_conf="/usr/local/etc/${guest_name}.conf"
    cat <<EOF > "$vm_conf"
# bhyve guest configuration for $guest_name
name=$guest_name
cpu=2
memory=1024M
disk=$guest_img
net_bridge=bridge0
EOF
    log INFO "VM configuration written to $vm_conf."
    if bhyve -c 2 -m 1024M -A -H -P -s 0:0,hostbridge -s 1:0,virtio-net,tap0 -s 2:0,ahci-hd,"$guest_img" -s 31,lpc -l com1,stdio; then
        log INFO "bhyve guest $guest_name started successfully."
    else
        log WARN "Failed to start bhyve guest $guest_name."
    fi
}

#--------------------------------------------------
# Performance Tuning and Final Checks
#--------------------------------------------------
tune_system() {
    log INFO "Applying performance tuning and system optimizations..."
    local sysctl_conf="/etc/sysctl.conf"
    [ -f "$sysctl_conf" ] && backup_file "$sysctl_conf"
    cat <<'EOF' >> "$sysctl_conf"
# Performance tuning settings
net.inet.tcp.delayed_ack=1
kern.ipc.somaxconn=128
net.inet.tcp.recvspace=65536
net.inet.tcp.sendspace=65536
EOF
    sysctl -w net.inet.tcp.delayed_ack=1
    sysctl -w kern.ipc.somaxconn=128
    sysctl -w net.inet.tcp.recvspace=65536
    sysctl -w net.inet.tcp.sendspace=65536
    log INFO "Performance tuning applied. Review $sysctl_conf for details."
}

final_checks() {
    log INFO "Performing final system checks..."
    echo "Kernel: $(uname -r)"
    echo "Uptime: $(uptime)"
    df -h /
}

home_permissions() {
    log INFO "Setting ownership and permissions for ${USER_HOME}..."
    chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}"
    find "${USER_HOME}" -type d -exec chmod g+s {} \;
}

#--------------------------------------------------
# Prompt for Reboot
#--------------------------------------------------
prompt_reboot() {
    if [ "$NO_REBOOT" -eq 1 ]; then
        log INFO "Reboot prompt suppressed (no-reboot flag set). Please reboot later to apply changes."
        return
    fi
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        log INFO "Non-interactive mode; skipping reboot prompt."
        return
    fi
    read -r -p "Reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot canceled. Please reboot later to apply changes."
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

    create_user
    configure_timezone
    configure_ntp

    setup_repos
    copy_shell_configs
    set_bash_shell

    configure_ssh
    secure_ssh_config
    setup_doas

    install_plex
    install_and_configure_caddy_proxy
    install_fastfetch

    configure_firewall

    setup_cron
    configure_periodic

    configure_wifi

    install_i3_ly_and_tools

    backup_configs
    backup_databases

    update_ssl_certificates

    run_security_audit
    tune_system
    system_health_check
    check_services
    verify_firewall_rules
    rotate_logs

    setup_vmm_guest

    final_checks
    home_permissions

    prompt_reboot
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"