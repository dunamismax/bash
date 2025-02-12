#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: install_configure_zfs.sh
# Description: Installs, configures, and enables ZFS on Ubuntu. This script
#              installs the required ZFS packages, imports the ZFS pool "WD_BLACK"
#              (if not already imported), sets its mountpoint to /media/WD_BLACK,
#              and enables auto‑mounting services.
#
# Author: YourName | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./install_configure_zfs.sh
#
# Requirements:
#   - Must be run as root.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/install_configure_zfs.log"  # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9
NORD5='\033[38;2;229;233;240m'   # #E5E9F0
NORD6='\033[38;2;236;239;244m'   # #ECEFF4
NORD7='\033[38;2;143;188;187m'   # #8FBCBB
NORD8='\033[38;2;136;192;208m'   # #88C0D0
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD10='\033[38;2;94;129;172m'   # #5E81AC
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD12='\033[38;2;208;135;112m'  # #D08770
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NORD15='\033[38;2;180;142;173m'  # #B48EAD
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log LEVEL message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
            *)     color="$NC"       ;;
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
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
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
# FUNCTION: Install ZFS Packages on Ubuntu
# ------------------------------------------------------------------------------
install_zfs() {
    print_section "Installing ZFS Packages"
    log INFO "Updating package lists..."
    apt update

    log INFO "Installing ZFS packages..."
    apt install -y zfsutils-linux

    log INFO "ZFS packages installed successfully."

    log INFO "Enabling ZFS auto-import and mount services..."
    systemctl enable zfs-import-cache.service || log WARN "Failed to enable zfs-import-cache.service."
    systemctl enable zfs-mount.service || log WARN "Failed to enable zfs-mount.service."
}

# ------------------------------------------------------------------------------
# FUNCTION: Configure and Mount ZFS Pool
# ------------------------------------------------------------------------------
configure_zfs() {
    print_section "ZFS Configuration"
    local ZPOOL_NAME="WD_BLACK"

    # Import the pool if not already imported
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import -f "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already imported."
    fi

    # Set the mountpoint to /media/WD_BLACK
    if ! zfs set mountpoint=/media/"$ZPOOL_NAME" "$ZPOOL_NAME"; then
        log WARN "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log INFO "ZFS pool '$ZPOOL_NAME' mountpoint set to /media/$ZPOOL_NAME."
    fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is executed with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists and secure the log file
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "ZFS installation and configuration started."

    # Install ZFS packages and dependencies
    install_zfs

    # Configure the ZFS pool and set the mountpoint
    configure_zfs

    log INFO "ZFS installation and configuration finished successfully."
}

# ------------------------------------------------------------------------------
# Invoke main() if this script is executed directly
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
