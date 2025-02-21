#!/usr/local/bin/bash
# FreeBSD Server Setup Script v4.1
#
# Overview:
#   This script automates the initial configuration of a FreeBSD server.
#   It updates the system, installs essential packages concurrently,
#   hardens security settings, configures network services, and sets up various services,
#   including a Caddy reverse proxy.
#
# Author: dunamismax
# Version: 4.1
# Date: 2025-02-20

set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants and Configurations
#--------------------------------------------------
readonly LOG_FILE="/var/log/freebsd_setup.log"
readonly USERNAME="sawyer"
readonly USER_HOME="/home/${USERNAME}"

# Terminal color definitions
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[0;33m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_NC='\033[0m'  # No Color

# Ensure the log directory exists with secure permissions
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

#--------------------------------------------------
# Logging and Error Handling
#--------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local msg="$*"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)  color="${COLOR_GREEN}" ;;
        WARN|WARNING) color="${COLOR_YELLOW}"; level="WARN" ;;
        ERROR) color="${COLOR_RED}" ;;
        DEBUG) color="${COLOR_BLUE}" ;;
        *)     color="${COLOR_NC}" ; level="INFO" ;;
    esac
    local entry="[$ts] [${level^^}] $msg"
    echo "$entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "${color}" "$entry" "${COLOR_NC}" >&2
}

handle_error() {
    local msg="${1:-An error occurred.}"
    local exit_code="${2:-1}"
    log ERROR "Error on line ${BASH_LINENO[0]} in function ${FUNCNAME[1]:-main}: ${msg}"
    exit "$exit_code"
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
        handle_error "Script must be run as root."
    fi
}

check_network() {
    log INFO "Checking network connectivity..."
    if ! ping -c1 -t5 google.com &>/dev/null; then
        log WARN "Network connectivity seems unavailable."
    else
        log INFO "Network connectivity verified."
    fi
}

#--------------------------------------------------
# System Update and Package Installation
#--------------------------------------------------
update_system() {
    log INFO "Updating pkg repositories..."
    if ! pkg update; then
        log WARN "pkg update encountered issues."
    fi

    log INFO "Upgrading installed packages..."
    if ! pkg upgrade -y; then
        log WARN "pkg upgrade encountered issues."
    fi
}

install_packages() {
    log INFO "Installing essential packages concurrently..."
    local packages=(
        bash vim nano zsh screen tmux mc htop tree ncdu neofetch
        git curl wget rsync
        python3 gcc cmake ninja meson go gdb
        nmap lsof iftop iperf3 netcat tcpdump lynis
        john hydra aircrack-ng nikto
        postgresql14-client postgresql14-server mysql80-client mysql80-server redis
        ruby rust jq doas
    )
    local job_count=4
    if pkg install -y -j "$job_count" "${packages[@]}"; then
        log INFO "All packages installed successfully."
    else
        handle_error "Package installation encountered errors."
    fi
}

#--------------------------------------------------
# User and Timezone Configuration
#--------------------------------------------------
create_user() {
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        if pw useradd "$USERNAME" -m -s /usr/local/bin/bash -G wheel; then
            echo "changeme" | pw usermod "$USERNAME" -h 0
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
    log INFO "Configuring timezone to ${tz}..."
    if [ -f "/usr/share/zoneinfo/${tz}" ]; then
        cp "/usr/share/zoneinfo/${tz}" /etc/localtime
        echo "$tz" > /etc/timezone
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
        local src="${USER_HOME}/github/bash/freebsd/dotfiles/${file}"
        local dest="${USER_HOME}/${file}"
        if [ -f "$src" ]; then
            [ -f "$dest" ] && cp "$dest" "${dest}.bak"
            if cp -f "$src" "$dest"; then
                chown "${USERNAME}:${USERNAME}" "$dest"
                log INFO "Copied $src to $dest"
            else
                log WARN "Failed to copy $src"
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
    sysrc sshd_enable="YES"
    if ! service sshd restart; then
        log WARN "Failed to restart SSH service."
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
        if ! service sshd restart; then
            log WARN "Failed to restart SSH after changes."
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
    if pkg install -y plexmediaserver; then
        log INFO "Plex installed successfully."
    else
        log WARN "Plex Media Server installation failed."
    fi
}

#--------------------------------------------------
# Firewall Setup Using PF
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
    sysrc pf_enable="YES"
    if service pf status >/dev/null 2>&1; then
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
# Additional Server Setup Functions
#--------------------------------------------------
deploy_user_scripts() {
    local bin_dir="${USER_HOME}/bin"
    local src_dir="${USER_HOME}/github/bash/freebsd/_scripts/"
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
    log INFO "Starting cron service..."
    if ! service cron start; then
        log WARN "Cron service failed to start."
    fi
}

configure_periodic() {
    local cron_file="/etc/periodic/daily/freebsd_maintenance"
    log INFO "Configuring daily maintenance tasks..."
    [ -f "$cron_file" ] && {
        mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" &&
        log INFO "Backed up existing maintenance script."
    }
    cat <<'EOF' > "$cron_file"
#!/bin/sh
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
    chmod +x "$cron_file" && log INFO "Daily maintenance script created." || log WARN "Failed to set execute permission on maintenance script."
}

final_checks() {
    log INFO "Performing final system checks..."
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
    if pkg install -y fastfetch; then
        log INFO "Fastfetch installed successfully."
    else
        log WARN "Fastfetch installation failed."
    fi
}

set_bash_shell() {
    if ! command -v /usr/local/bin/bash &>/dev/null; then
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

install_and_configure_caddy_proxy() {
    log INFO "Installing Caddy reverse proxy..."
    if pkg install -y caddy; then
        log INFO "Caddy installed successfully."
    else
        handle_error "Failed to install Caddy."
    fi
    local caddyfile="/usr/local/etc/caddy/Caddyfile"
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
    sysrc caddy_enable="YES"
    if service caddy status >/dev/null 2>&1; then
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

configure_wifi() {
    local wlan_device wpa_conf rc_conf ssid psk

    # Detect the wireless adapter (select the first one if multiple)
    wlan_device=$(sysctl -n net.wlan.devices | awk '{print $1}')
    if [ -z "$wlan_device" ]; then
        log ERROR "No wireless adapter found."
        return 1
    fi
    log INFO "Detected wireless adapter: $wlan_device"

    # Load the corresponding driver module (if not already loaded)
    if ! kldload "if_${wlan_device}" 2>/dev/null; then
        log WARN "Module if_${wlan_device} may already be loaded."
    fi
    if ! kldstat | grep -q "if_${wlan_device}"; then
        log ERROR "Failed to load driver for $wlan_device."
        return 1
    fi
    log INFO "Driver for $wlan_device loaded."

    # Create the wlan0 interface using the detected device
    if ! ifconfig wlan0 create wlandev "$wlan_device"; then
        log ERROR "Failed to create wlan0 interface."
        return 1
    fi
    log INFO "wlan0 interface created."

    # Prompt for SSID and PSK credentials
    read -p "Enter SSID: " ssid
    if [ -z "$ssid" ]; then
        log ERROR "SSID cannot be empty."
        return 1
    fi
    read -s -p "Enter PSK (leave empty for open networks): " psk
    echo

    # Update /etc/wpa_supplicant.conf with network details
    wpa_conf="/etc/wpa_supplicant.conf"
    if [ ! -f "$wpa_conf" ]; then
        touch "$wpa_conf" && chmod 600 "$wpa_conf"
        log INFO "Created $wpa_conf with secure permissions."
    fi

    if grep -q "ssid=\"$ssid\"" "$wpa_conf"; then
        log INFO "Network '$ssid' already configured in $wpa_conf."
    else
        log INFO "Adding network '$ssid' configuration..."
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

    # Ensure configuration persists in /etc/rc.conf
    rc_conf="/etc/rc.conf"
    if ! grep -q "^wlans_${wlan_device}=" "$rc_conf"; then
        echo "wlans_${wlan_device}=\"wlan0\"" >> "$rc_conf"
        log INFO "Added wlans_${wlan_device} entry to $rc_conf."
    fi
    if ! grep -q "^ifconfig_wlan0=" "$rc_conf"; then
        echo "ifconfig_wlan0=\"WPA DHCP\"" >> "$rc_conf"
        log INFO "Added ifconfig_wlan0 entry to $rc_conf."
    fi

    # Restart the wlan0 interface
    if ! service netif restart wlan0; then
        log ERROR "Failed to restart wlan0 interface."
        return 1
    fi

    log INFO "Wi‑Fi configuration completed."
}

install_desktop_environment() {
    check_root
    update_system

    log INFO "Installing Xorg and xinit..."
    if ! pkg install -y xorg xinit; then
        handle_error "Failed to install Xorg and xinit."
    fi

    log INFO "Installing i3 window manager and addons..."
    local i3_packages=( i3 i3status i3lock dmenu i3blocks )
    if ! pkg install -y "${i3_packages[@]}"; then
        handle_error "Failed to install i3 packages."
    fi

    log INFO "Installing GNOME and GDM..."
    local gnome_packages=( gnome3 gdm )
    if ! pkg install -y "${gnome_packages[@]}"; then
        handle_error "Failed to install GNOME/GDM."
    fi

    log INFO "Enabling GNOME services..."
    sysrc dbus_enable="YES"
    sysrc gdm_enable="YES"
    sysrc gnome_enable="YES"

    log INFO "Starting dbus and gdm services..."
    service dbus start || handle_error "Failed to start dbus."
    service gdm start || handle_error "Failed to start gdm."

    log INFO "Desktop environment installation complete. A reboot is recommended."
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
        log INFO "Reboot canceled. Please reboot later to apply changes."
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
    configure_wifi
    install_desktop_environment
    prompt_reboot
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"