#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: install_firacode_nerd_font.sh
# Description: This script installs the FiraCode Nerd Font on Ubuntu using the Nord
#              color theme, with strict error handling, log‑level filtering, and
#              graceful signal traps.
# Author: Your Name | License: MIT | Version: 3.2
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./install_firacode_nerd_font.sh [OPTIONS]
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/install_firacode_nerd_font.log by default.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & SET IFS
# ------------------------------------------------------------------------------
set -Eeuo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
readonly LOG_FILE="/var/log/install_firacode_nerd_font.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"           # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels (case-insensitive): VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'    # Bluish (for DEBUG)
readonly NORD10='\033[38;2;94;129;172m'    # Accent Blue
readonly NORD11='\033[38;2;191;97;106m'    # Reddish (for ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'   # Yellowish (for WARN)
readonly NORD14='\033[38;2;163;190;140m'   # Greenish (for INFO)
readonly NC='\033[0m'                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL message
# Example: log INFO "Starting process..."
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"

    local msg_level
    msg_level=$(get_log_level_num "$upper_level")
    local current_level
    current_level=$(get_log_level_num "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}")
    if (( msg_level < current_level )); then
        return 0
    fi

    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)   color="${NORD9}" ;;
            INFO)    color="${NORD14}" ;;
            WARN)    color="${NORD13}" ;;
            ERROR|CRITICAL) color="${NORD11}" ;;
            *)       color="${NC}" ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"
    local lineno="${BASH_LINENO[0]:-${LINENO}}"
    local func="${FUNCNAME[1]:-main}"

    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $lineno in function '$func'."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Add any necessary cleanup tasks here.
}

trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
usage() {
    cat << EOF
Usage: sudo $(basename "$0") [OPTIONS]

This script installs the FiraCode Nerd Font on Ubuntu.

Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# Prints a styled section header using Nord accent colors
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
install_font() {
    print_section "Installing FiraCode Nerd Font"
    local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local font_dir="/usr/local/share/fonts/nerd-fonts"
    local font_file="FiraCodeNerdFont-Regular.ttf"

    log INFO "Starting FiraCode Nerd Font installation..."

    if [[ ! -d "$font_dir" ]]; then
        log INFO "Creating font directory: $font_dir"
        mkdir -p "$font_dir" || handle_error "Failed to create font directory: $font_dir"
    fi

    log INFO "Setting permissions for the font directory..."
    chmod 755 "$font_dir" || handle_error "Failed to set permissions for the font directory."

    log INFO "Downloading font from $font_url..."
    curl -L -o "$font_dir/$font_file" "$font_url" || handle_error "Failed to download font from $font_url."
    log INFO "Font downloaded successfully."

    if [[ ! -f "$font_dir/$font_file" ]]; then
        handle_error "Font file not found after download: $font_dir/$font_file"
    fi

    log INFO "Setting permissions for the font file..."
    chmod 644 "$font_dir/$font_file" || handle_error "Failed to set permissions for the font file."

    log INFO "Setting ownership for the font file..."
    chown root:root "$font_dir/$font_file" || handle_error "Failed to set ownership for the font file."

    log INFO "Refreshing font cache..."
    fc-cache -fv >/dev/null 2>&1 || handle_error "Failed to refresh font cache."
    log INFO "Font cache refreshed successfully."

    log INFO "Verifying font installation..."
    if ! fc-list | grep -qi "FiraCode"; then
        log ERROR "Font verification failed. FiraCode Nerd Font is not available in the system."
        log INFO "Font directory contents:" && ls -l "$font_dir"
        log INFO "Font cache refresh output:" && fc-cache -fv
        log INFO "Font list output:" && fc-list | grep -i "FiraCode"
        handle_error "Font verification failed. FiraCode Nerd Font is not available in the system."
    fi

    log INFO "FiraCode Nerd Font installation completed successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
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

    local log_dir
    log_dir=$(dirname "$LOG_FILE")
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
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
