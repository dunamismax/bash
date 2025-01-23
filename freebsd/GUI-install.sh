#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: freebsd_gui_setup.sh
# Description: Installs a minimal GUI environment on FreeBSD and sets up dotfiles.
# Author: Your Name | License: MIT
# Version: 1.0.0
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
LOG_FILE="/var/log/freebsd_gui_setup.log"  # Path to the log file
USERNAME="sawyer"  # Replace with the target username

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

    # Validate log level and set color
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

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"

    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"

    # Output to console
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"  # Default exit code is 1
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Log the error with additional context
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

    # Optionally, print the error to stderr for immediate visibility
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2

    # Exit with the specified exit code
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# ------------------------------------------------------------------------------
# FUNCTION: Install GUI
# ------------------------------------------------------------------------------
install_gui() {
    log INFO "--------------------------------------"
    log INFO "Starting GUI installation..."

    # Install required packages
    log INFO "Installing GUI packages..."
    pkg install -y xorg xinit xauth xrandr xset xsetroot i3 i3status i3lock dmenu feh picom alacritty pulseaudio pavucontrol flameshot clipmenu vlc dunst thunar firefox || handle_error "Failed to install GUI packages."

    log INFO "GUI installation completed successfully."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# FUNCTION: Load dotfiles
# ------------------------------------------------------------------------------
setup_dotfiles() {
    log INFO "--------------------------------------"
    log INFO "Starting dotfiles setup..."

    # Base paths
    local user_home="/home/${USERNAME}"
    local dotfiles_dir="${user_home}/github/bash/freebsd/dotfiles"
    local config_dir="${user_home}/.config"

    # Verify source directories exist
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    # Create necessary directories
    log INFO "Creating required directories..."
    if ! mkdir -p "$config_dir"; then
        handle_error "Failed to create config directory."
    fi

    # Define files to copy (source:destination)
    local files=(
        "${dotfiles_dir}/.xinitrc:${user_home}/"
    )

    # Define directories to copy (source:destination)
    local dirs=(
        "${dotfiles_dir}/alacritty:${config_dir}"
        "${dotfiles_dir}/i3:${config_dir}"
        "${dotfiles_dir}/picom:${config_dir}"
        "${dotfiles_dir}/i3status:${config_dir}"
    )

    # Copy files
    log INFO "Copying files..."
    for item in "${files[@]}"; do
        local src="${item%:*}"
        local dst="${item#*:}"
        if [[ -f "$src" ]]; then
            if ! cp "$src" "$dst"; then
                handle_error "Failed to copy file: $src"
            fi
            log INFO "Copied file: $src -> $dst"
        else
            log WARN "Source file not found: $src"
        fi
    done

    # Copy directories
    log INFO "Copying directories..."
    for item in "${dirs[@]}"; do
        local src="${item%:*}"
        local dst="${item#*:}"
        if [[ -d "$src" ]]; then
            if ! cp -r "$src" "$dst"; then
                handle_error "Failed to copy directory: $src"
            fi
            log INFO "Copied directory: $src -> $dst"
        else
            log WARN "Source directory not found: $src"
        fi
    done

    # Set ownership and permissions
    log INFO "Setting ownership and permissions..."
    if ! chown -R "${USERNAME}:${USERNAME}" "$user_home"; then
        handle_error "Failed to set ownership for $user_home."
    fi

    log INFO "Dotfiles setup completed successfully."
    log INFO "--------------------------------------"
    return 0
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

    # Ensure the script is run as root
    check_root

    # Ensure the log directory exists and is writable
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE"  # Restrict log file access to root only

    log INFO "Script execution started."

    # Call your main functions in order
    install_gui
    setup_dotfiles

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi