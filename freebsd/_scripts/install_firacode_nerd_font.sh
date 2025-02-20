#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: install_firacode_nerd_font.sh
# Description: This script installs the FiraCode Nerd Font on FreeBSD.
# Author: Your Name | License: MIT | Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./install_firacode_nerd_font.sh
#
# ------------------------------------------------------------------------------

set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/install_firacode_nerd_font.log"  # Path to the log file

usage() {
    cat << EOF
Usage: sudo $(basename "$0") [OPTIONS]

This script installs the FiraCode Nerd Font on FreeBSD.

Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

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

    # Select color based on log level
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
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2
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

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
install_font() {
    local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local font_dir="/usr/local/share/fonts/nerd-fonts"
    local font_file="FiraCodeNerdFont-Regular.ttf"

    log INFO "--------------------------------------"
    log INFO "Starting FiraCode Nerd Font installation..."

    # Create the font directory if it doesn't exist
    if [[ ! -d "$font_dir" ]]; then
        log INFO "Creating font directory: $font_dir"
        if ! mkdir -p "$font_dir"; then
            handle_error "Failed to create font directory: $font_dir"
        fi
    fi

    # Set correct permissions on the font directory
    log INFO "Setting permissions for the font directory..."
    if ! chmod 755 "$font_dir"; then
        handle_error "Failed to set permissions for the font directory."
    fi

    # Download the font
    log INFO "Downloading font from $font_url..."
    if ! curl -L -o "$font_dir/$font_file" "$font_url"; then
        handle_error "Failed to download font from $font_url."
    fi
    log INFO "Font downloaded successfully."

    # Verify the font file was downloaded
    if [[ ! -f "$font_dir/$font_file" ]]; then
        handle_error "Font file not found after download: $font_dir/$font_file"
    fi

    # Set appropriate permissions for the font file
    log INFO "Setting permissions for the font file..."
    if ! chmod 644 "$font_dir/$font_file"; then
        handle_error "Failed to set permissions for the font file."
    fi

    # Set ownership to root:wheel (the default on FreeBSD)
    log INFO "Setting ownership for the font file..."
    if ! chown root:wheel "$font_dir/$font_file"; then
        handle_error "Failed to set ownership for the font file."
    fi

    # Refresh the font cache
    log INFO "Refreshing font cache..."
    if ! fc-cache -fv >/dev/null 2>&1; then
        handle_error "Failed to refresh font cache."
    fi
    log INFO "Font cache refreshed successfully."

    # Verify the font is available in the system
    log INFO "Verifying font installation..."
    if ! fc-list | grep -qi "FiraCode"; then
        log ERROR "Font verification failed. FiraCode Nerd Font is not available in the system."
        log INFO "Font directory contents:"
        ls -l "$font_dir"
        log INFO "Font cache refresh output:"
        fc-cache -fv
        log INFO "Font list output:"
        fc-list | grep -i "FiraCode"
        handle_error "Font verification failed. FiraCode Nerd Font is not available in the system."
    fi

    log INFO "FiraCode Nerd Font installation completed successfully."
    log INFO "--------------------------------------"
    return 0
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
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

    # Ensure the log directory exists and is writable
    local LOG_DIR
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."
    install_font
    log INFO "Script execution finished."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi