#!/usr/local/bin/bash
#
# FreeBSD Desktop Setup Script v1.0
#
# Overview:
#   This script installs and configures a complete desktop environment on FreeBSD.
#   It installs Xorg (X11), the i3 window manager (plus useful i3 addons), and GNOME
#   with GDM. After installation, it enables the GNOME Display Manager (GDM) so that
#   you can log in graphically.
#
# Features:
#   - Updates pkg repositories
#   - Installs Xorg and xinit for the X11 environment
#   - Installs i3 and related packages: i3, i3status, i3lock, dmenu, and i3blocks
#   - Installs GNOME (gnome3) and GDM
#   - Enables necessary services for GNOME (dbus, gdm, gnome)
#
# Usage:
#   Run this script as root (or with sudo) to install and configure your FreeBSD desktop.
#
# Author: Your Name (improved by ChatGPT)
# Version: 1.0
# Date: 02/20/2025

set -Eeuo pipefail
IFS=$'\n\t'

#--------------------------------------------------
# Global Constants
#--------------------------------------------------
readonly LOG_FILE="/var/log/freebsd_desktop_setup.log"

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
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)  color='\033[0;32m' ;;       # Green
        WARN|WARNING) color='\033[0;33m' ;;   # Yellow
        ERROR) color='\033[0;31m' ;;          # Red
        DEBUG) color='\033[0;34m' ;;          # Blue
        *)     color='\033[0m' ;;
    esac
    local log_entry="[$timestamp] [${level^^}] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "${color}%s\033[0m\n" "$log_entry" >&2
}

handle_error() {
    local err_msg="${1:-An error occurred.}"
    local exit_code="${2:-1}"
    log ERROR "$err_msg (Exit Code: ${exit_code})"
    exit "$exit_code"
}

trap 'handle_error "Unexpected error at line ${LINENO}."' ERR

#--------------------------------------------------
# Utility Functions
#--------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "This script must be run as root."
    fi
}

update_system() {
    log INFO "Updating pkg repositories..."
    pkg update || log WARN "pkg update encountered issues."
}

#--------------------------------------------------
# Installation Functions
#--------------------------------------------------
install_xorg() {
    log INFO "Installing Xorg and xinit for X11 support..."
    pkg install -y xorg xinit || handle_error "Failed to install Xorg."
}

install_i3() {
    log INFO "Installing i3 window manager and addons..."
    local packages=( i3 i3status i3lock dmenu i3blocks )
    pkg install -y "${packages[@]}" || handle_error "Failed to install i3 packages."
}

install_gnome() {
    log INFO "Installing GNOME (gnome3) and GDM..."
    local packages=( gnome3 gdm )
    pkg install -y "${packages[@]}" || handle_error "Failed to install GNOME/GDM."
}

#--------------------------------------------------
# Service Enablement Functions
#--------------------------------------------------
enable_gdm() {
    log INFO "Enabling GNOME Display Manager (GDM) and required services..."
    sysrc dbus_enable="YES" || handle_error "Failed to enable dbus."
    sysrc gdm_enable="YES" || handle_error "Failed to enable gdm."
    sysrc gnome_enable="YES" || handle_error "Failed to enable gnome."
    log INFO "Starting dbus service..."
    service dbus start || handle_error "Failed to start dbus."
    log INFO "Starting gdm service..."
    service gdm start || handle_error "Failed to start gdm."
}

#--------------------------------------------------
# Main Execution Flow
#--------------------------------------------------
main() {
    check_root
    update_system
    install_xorg
    install_i3
    install_gnome
    enable_gdm
    log INFO "Desktop environment installation complete."
    log INFO "Please reboot your system to start the graphical environment."
}

main "$@"
