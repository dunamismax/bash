#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: freebsd_gui_setup.sh
# Description: Installs a minimal GUI environment on FreeBSD and sets up dotfiles.
#              This script installs Xorg, a window manager (i3), and various
#              essential tools, then deploys user dotfiles.
# Author: Your Name | License: MIT | Version: 1.1.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./freebsd_gui_setup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/freebsd_gui_setup.log"  # Log file path
USERNAME="sawyer"                           # Target username
# For FreeBSD, the home directory is typically located at /home/USERNAME
USER_HOME="/home/${USERNAME}"

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Define color codes
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'  # No Color

    # Set color based on log level
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            ;;
        DEBUG)
            local color="${BLUE}"
            ;;
        *)
            local color="${NC}"
            level="INFO"
            ;;
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

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

usage() {
    cat <<EOF
Usage: sudo $(basename "$0") [OPTIONS]

This script installs a minimal GUI environment on FreeBSD and deploys dotfiles.
It will install Xorg, i3, and various utilities, then copy your dotfiles from
your GitHub repository to your user configuration directories.

Options:
  -h, --help    Show this help message and exit.

EOF
    exit 0
}

# ------------------------------------------------------------------------------
# FUNCTION: Install Minimal GUI Environment
# ------------------------------------------------------------------------------
install_gui() {
    log INFO "--------------------------------------"
    log INFO "Starting minimal GUI installation..."

    log INFO "Installing required GUI packages..."
    if pkg install -y \
        xorg xinit xauth xrandr xset xsetroot \
        i3 i3status i3lock \
        drm-kmod dmenu feh picom alacritty \
        pulseaudio pavucontrol flameshot clipmenu \
        vlc dunst thunar firefox; then
        log INFO "GUI packages installed successfully."
    else
        handle_error "Failed to install one or more GUI packages."
    fi

    log INFO "Minimal GUI installation completed."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# FUNCTION: Set Up Dotfiles
# ------------------------------------------------------------------------------
setup_dotfiles() {
    log INFO "--------------------------------------"
    log INFO "Starting dotfiles setup..."

    # Define source and target directories
    local dotfiles_dir="${USER_HOME}/github/bash/freebsd/dotfiles"
    local config_dir="${USER_HOME}/.config"

    # Verify dotfiles source exists
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    log INFO "Ensuring configuration directory exists at: $config_dir"
    mkdir -p "$config_dir" || handle_error "Failed to create config directory at $config_dir."

    # Define files to copy (format: source:destination)
    local files=(
        "${dotfiles_dir}/.xinitrc:${USER_HOME}/"
    )

    # Define directories to copy (format: source:destination)
    local dirs=(
        "${dotfiles_dir}/alacritty:${config_dir}"
        "${dotfiles_dir}/i3:${config_dir}"
        "${dotfiles_dir}/picom:${config_dir}"
        "${dotfiles_dir}/i3status:${config_dir}"
    )

    log INFO "Copying dotfiles (files)..."
    for mapping in "${files[@]}"; do
        local src="${mapping%%:*}"
        local dst="${mapping#*:}"
        if [[ -f "$src" ]]; then
            cp "$src" "$dst" || handle_error "Failed to copy file: $src to $dst"
            log INFO "Copied file: $src -> $dst"
        else
            log WARN "Source file not found, skipping: $src"
        fi
    done

    log INFO "Copying dotfiles (directories)..."
    for mapping in "${dirs[@]}"; do
        local src="${mapping%%:*}"
        local dst="${mapping#*:}"
        if [[ -d "$src" ]]; then
            cp -r "$src" "$dst" || handle_error "Failed to copy directory: $src to $dst"
            log INFO "Copied directory: $src -> $dst"
        else
            log WARN "Source directory not found, skipping: $src"
        fi
    done

    log INFO "Setting ownership for all files under $USER_HOME..."
    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME" || handle_error "Failed to set ownership for $USER_HOME."

    log INFO "Dotfiles setup completed successfully."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------------------------
main() {
    # Parse input arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage
                ;;
            *)
                log WARN "Unknown option: $1"
                usage
                ;;
        esac
        shift
    done

    check_root

    # Ensure log directory exists and is writable
    local LOG_DIR
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."
    install_gui
    setup_dotfiles
    log INFO "Script execution finished."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
