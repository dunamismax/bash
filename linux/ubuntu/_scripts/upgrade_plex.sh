#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: update_plex.sh
# Description: Downloads and installs the latest Plex Media Server package,
#              fixes dependency issues if any, cleans up temporary files, and
#              restarts the Plex service.
# Author: Your Name | License: MIT | Version: 1.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./update_plex.sh
#
# Notes:
#   - This script must be run as root.
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
readonly PLEX_URL="https://downloads.plex.tv/plex-media-server-new/1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
readonly TEMP_DEB="/tmp/plexmediaserver.deb"
readonly LOG_FILE="/var/log/update_plex.log"
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
readonly QUIET_MODE=false

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'    # Bluish (DEBUG)
readonly NORD10='\033[38;2;94;129;172m'     # Accent Blue (section headers)
readonly NORD11='\033[38;2;191;97;106m'     # Reddish (ERROR)
readonly NORD13='\033[38;2;235;203;139m'    # Yellowish (WARN)
readonly NORD14='\033[38;2;163;190;140m'    # Greenish (INFO)
readonly NC='\033[0m'                       # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W)echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL "message"
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;
            WARN)  color="${NORD13}" ;;
            ERROR) color="${NORD11}" ;;
            DEBUG) color="${NORD9}"  ;;
            *)     color="$NC"       ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    if [[ "$QUIET_MODE" != true ]]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An unknown error occurred"}"
    local exit_code="${2:-1}"
    local lineno="${BASH_LINENO[0]:-${LINENO}}"
    local func="${FUNCNAME[1]:-main}"

    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Error in function '$func' at line $lineno."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Cleaning up temporary files."
    rm -f "$TEMP_DEB"
}

trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# ------------------------------------------------------------------------------
# FUNCTION: Download Plex Package
# ------------------------------------------------------------------------------
download_plex() {
    print_section "Downloading Plex Media Server Package"
    log INFO "Downloading Plex Media Server package..."
    if ! curl -L -o "$TEMP_DEB" "$PLEX_URL"; then
        handle_error "Failed to download Plex package."
    fi
    log INFO "Plex package downloaded successfully."
}

# ------------------------------------------------------------------------------
# FUNCTION: Install Plex Package
# ------------------------------------------------------------------------------
install_plex() {
    print_section "Installing Plex Media Server"
    log INFO "Installing Plex Media Server..."
    if ! dpkg -i "$TEMP_DEB"; then
        log WARN "Dependency issues detected. Attempting to fix dependencies..."
        if ! apt-get install -f -y; then
            handle_error "Failed to resolve dependencies for Plex."
        fi
    fi
    log INFO "Plex Media Server installed successfully."
}

# ------------------------------------------------------------------------------
# FUNCTION: Restart Plex Service
# ------------------------------------------------------------------------------
restart_plex() {
    print_section "Restarting Plex Media Server Service"
    log INFO "Restarting Plex Media Server service..."
    if ! systemctl restart plexmediaserver; then
        handle_error "Failed to restart Plex Media Server service."
    fi
    log INFO "Plex Media Server service restarted successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists and secure the log file
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    download_plex
    install_plex
    restart_plex

    log INFO "Plex Media Server has been updated and restarted successfully."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
