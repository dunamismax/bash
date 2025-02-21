#!/usr/local/bin/bash
# ==============================================================================
# OpenBSD Server Automation Script v4.2
#
# Overview:
#   This script automates the initial configuration of an OpenBSD server.
#   It performs system updates, sequentially installs essential packages,
#   applies security hardening measures, configures network services (including
#   SSH and PF firewall), and sets up various utilities such as a Caddy reverse
#   proxy, Wi‑Fi networking, and an X11/i3/ly desktop environment.
#
# Features:
#   - Comprehensive logging with colored terminal output.
#   - Non-interactive and interactive configuration components.
#   - Automatic backups of key configuration files before changes.
#   - Modular design for easy customization and maintenance.
#
# Usage:
#   Run this script as root. For help:
#       $(basename "$0") --help
#
# Disclaimer:
#   THIS SCRIPT IS PROVIDED "AS IS" WITHOUT ANY WARRANTY, EXPRESS OR IMPLIED.
#   THE AUTHOR IS NOT RESPONSIBLE FOR ANY DAMAGE CAUSED BY ITS USE.
#   USE AT YOUR OWN RISK.
#
# Author: dunamismax (adapted for OpenBSD)
# Version: 4.2
# Date: 2025-02-20
# ==============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants and Configurations
#--------------------------------------------------
readonly LOG_FILE="/var/log/openbsd_setup.log"
readonly USERNAME="sawyer"
readonly USER_HOME="/home/${USERNAME}"

# Terminal color definitions
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[0;33m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_NC='\033[0m'  # No Color

# Ensure log directory exists and log file is secure
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

# Optionally, set a secure umask for new files
umask 077

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
        INFO)   color="${COLOR_GREEN}" ;;
        WARN|WARNING) color="${COLOR_YELLOW}"; level="WARN" ;;
        ERROR)  color="${COLOR_RED}" ;;
        DEBUG)  color="${COLOR_BLUE}" ;;
        *)      color="${COLOR_NC}" ; level="INFO" ;;
    esac
    local entry="[$ts] [${level^^}] $msg"
    echo "$entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "${color}" "$entry" "${COLOR_NC}" >&2
}

handle_error() {
    local msg="${1:-An unexpected error occurred.}"
    local exit_code="${2:-1}"
    log ERROR "Error on line ${BASH_LINENO[0]} in function ${FUNCNAME[1]:-main}: ${msg}"
    exit "$exit_code"
}

trap 'handle_error "Unexpected error encountered."' ERR

#--------------------------------------------------
# Utility and Help Functions
#--------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

This script automates the setup and configuration of an OpenBSD server.

Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root."
    fi
}

check_network() {
    log INFO "Checking network connectivity..."
    if ! ping -c1 google.com &>/dev/null; then
        log WARN "Network connectivity appears to be unavailable."
    else
        log INFO "Network connectivity verified."
    fi
}

#--------------------------------------------------
# System Update and Package Installation
#--------------------------------------------------
update_system() {
    log INFO "Running syspatch for system updates..."
    if command -v syspatch &>/dev/null; then
        syspatch && log INFO "syspatch completed." || log WARN "syspatch encountered issues."
    else
        log WARN "syspatch not available; skipping system updates."
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
        postgresql-client postgresql-server mysql-client mysql-server redis
        ruby rust jq doas
    )
    for pkg in "${packages[@]}"; do
        if pkg_info "$pkg" &>/dev/null; then
            log INFO "Package '$pkg' is already installed."
        else
            if pkg_add "$pkg"; then
                log INFO "Installed package: $pkg"
            else
                log WARN "Failed to install package: $pkg"
            fi
        fi
    done
}

#--------------------------------------------------
# User and Timezone Configuration
#--------------------------------------------------
create_user() {
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        if useradd -m -s /usr/local/bin/bash "$USERNAME"; then
            echo "changeme" | passwd "$USERNAME"
            log INFO "User '$USERNAME' created with default password 'changeme'."
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
    log INFO "Deploying shell configuration files..."
    for file in .bashrc .profile; do
        local src="${USER_HOME}/github/bash/openbsd/dotfiles/${file}"
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

#--------------------------------------------------
# SSH and Security Configuration
#--------------------------------------------------
configure_ssh() {
    log INFO "Enabling SSH service..."
    # Ensure SSH flags are set in rc.conf.local
    if ! grep -q "^sshd_flags=" /etc/rc.conf.local; then
        echo 'sshd_flags=""' >> /etc/rc.conf.local
    fi
    rcctl enable sshd
    if rcctl restart sshd; then
        log INFO "SSHD restarted successfully."
    else
        log WARN "Failed to restart SSHD."
    fi
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
        if rcctl restart sshd; then
            log INFO "SSHD restarted after configuration changes."
        else
            log WARN "Failed to restart SSHD after changes."
        fi
    else
        log WARN "SSH configuration file not found."
    fi
}

#--------------------------------------------------
# Plex Media Server Installation
#--------------------------------------------------
install_plex() {
    log INFO "Installing Plex Media Server..."
    if pkg_add plexmediaserver; then
        log INFO "Plex installed successfully."
    else
        log WARN "Plex Media Server installation failed or is not available on OpenBSD."
    fi
}

#--------------------------------------------------
# PF Firewall Configuration
#--------------------------------------------------
detect_ext_if() {
    local iface
    iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
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
    rcctl enable pf
    if rcctl check pf &>/dev/null; then
        if pfctl -f /etc/pf.conf; then
            log INFO "PF configuration reloaded."
        else
            log WARN "Failed to reload PF configuration."
        fi
    else
        if rcctl start pf; then
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
# Additional Server Setup Functions
#--------------------------------------------------
deploy_user_scripts() {
    local bin_dir="${USER_HOME}/bin"
    local src_dir="${USER_HOME}/github/bash/openbsd/_scripts/"
    mkdir -p "$bin_dir"
    log INFO "Deploying user scripts from ${src_dir} to ${bin_dir}..."
    if rsync -ah --delete "$src_dir" "$bin_dir"; then
        find "$bin_dir" -type f -exec chmod 755 {} \;
        log INFO "User scripts deployed successfully."
    else
        log WARN "Failed to deploy user scripts."
    fi
}

setup_cron() {
    log INFO "Enabling and starting cron service..."
    rcctl enable cron
    if rcctl start cron; then
        log INFO "Cron service started."
    else
        log WARN "Cron service failed to start."
    fi
}

configure_periodic() {
    local cron_file="/etc/periodic/daily/openbsd_maintenance"
    log INFO "Configuring daily maintenance tasks..."
    [ -f "$cron_file" ] && {
        mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" &&
        log INFO "Backed up existing maintenance script."
    }
    cat <<'EOF' > "$cron_file"
#!/bin/sh
# Daily package update maintenance task
pkg_add -u
EOF
    chmod +x "$cron_file" && log INFO "Daily maintenance script created." || log WARN "Failed to set execute permission on maintenance script."
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

install_fastfetch() {
    log INFO "Installing Fastfetch..."
    if pkg_add fastfetch; then
        log INFO "Fastfetch installed successfully."
    else
        log WARN "Fastfetch installation failed or is not available on OpenBSD."
    fi
}

set_bash_shell() {
    if ! command -v /usr/local/bin/bash &>/dev/null; then
        log INFO "Bash not found; installing..."
        if ! pkg_add bash; then
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

install_and_configure_caddy_proxy() {
    log INFO "Installing Caddy reverse proxy..."
    if pkg_add caddy; then
        log INFO "Caddy installed successfully."
    else
        handle_error "Failed to install Caddy."
    fi
    local caddy_dir="/usr/local/etc/caddy"
    local caddyfile="${caddy_dir}/Caddyfile"
    mkdir -p "$caddy_dir"
    [ -f "$caddyfile" ] && cp "$caddyfile" "${caddyfile}.backup.$(date +%Y%m%d%H%M%S)" && log INFO "Backed up existing Caddyfile."
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
    rcctl enable caddy
    if rcctl check caddy &>/dev/null; then
        if rcctl reload caddy; then
            log INFO "Caddy reloaded successfully."
        else
            if rcctl start caddy; then
                log INFO "Caddy started successfully."
            else
                handle_error "Failed to start or reload Caddy."
            fi
        fi
    else
        if rcctl start caddy; then
            log INFO "Caddy started successfully."
        else
            handle_error "Failed to start Caddy service."
        fi
    fi
}

configure_wifi() {
    log INFO "Configuring Wi‑Fi interfaces..."
    # Detect wireless interfaces (common prefixes: ath, iwn, iwm)
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
    read -r -p "Enter SSID for primary Wi‑Fi ($primary_iface): " ssid
    if [ -z "$ssid" ]; then
        log ERROR "SSID cannot be empty."
        return 1
    fi
    read -s -r -p "Enter PSK (leave empty for open networks): " psk
    echo

    local wpa_conf="/etc/wpa_supplicant.conf"
    if [ ! -f "$wpa_conf" ]; then
        touch "$wpa_conf" && chmod 600 "$wpa_conf"
        log INFO "Created $wpa_conf with secure permissions."
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

install_i3_ly_and_tools() {
    log INFO "Installing i3, Xorg/X11, Zig, and ly display manager..."

    # 1. Install i3 and related packages
    local packages=(i3 i3status i3lock dmenu i3blocks feh xorg xinit)
    for pkg in "${packages[@]}"; do
        if pkg_info "$pkg" &>/dev/null; then
            log INFO "Package '$pkg' is already installed."
        else
            if pkg_add "$pkg"; then
                log INFO "Installed package: $pkg"
            else
                log WARN "Failed to install package: $pkg"
            fi
        fi
    done

    # 2. Install Zig from source
    local zig_url="https://ziglang.org/download/0.12.1/zig-linux-x86_64-0.12.1.tar.xz"
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

    # 3. Clone and compile ly display manager with Zig
    local ly_src="${zig_src_dir}/ly"
    if [ -d "$ly_src" ]; then
        log INFO "Removing existing ly source directory..."
        rm -rf "$ly_src"
    fi
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
    if zig build installsystemd; then
        log INFO "ly installed successfully."
    else
        log ERROR "ly installation failed."
        return 1
    fi

    # 4. Create an rc.d script for ly (OpenBSD alternative to systemd)
    local rc_script="/etc/rc.d/ly"
    log INFO "Creating rc.d startup script for ly..."
    cat <<'EOF' > "$rc_script"
#!/bin/sh
#
# PROVIDE: ly
# REQUIRE: DAEMON
# KEYWORD: shutdown
. /etc/rc.d/rc.subr

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
    log INFO "ly rc.d script created. To enable ly at boot, add 'ly_enable=yes' to /etc/rc.conf.local."
    log INFO "Installation of i3, Xorg/X11, Zig, and ly is complete."
}

#--------------------------------------------------
# Prompt for Reboot
#--------------------------------------------------
prompt_reboot() {
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
    # Process command-line options
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
    configure_wifi
    install_i3_ly_and_tools
    prompt_reboot
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"