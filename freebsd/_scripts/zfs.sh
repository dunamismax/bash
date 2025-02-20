#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: configure_zfs_freebsd.sh
# Description: A robust script to configure auto mounting for a WD external ZFS
#              pool on FreeBSD using the Nord color theme with detailed logging,
#              strict error handling, and graceful signal traps.
# Author: YourName | License: MIT | Version: 1.1.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./configure_zfs_freebsd.sh
#
# Notes:
#   - This script requires root privileges.
#   - Assumes ZFS is already installed and enabled.
#   - Logs are stored at /var/log/ultimate_script.log by default.
#
# ------------------------------------------------------------------------------

# Enable strict mode & set IFS
set -Eeuo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
readonly LOG_FILE="/var/log/ultimate_script.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'   # Bluish
readonly NORD10='\033[38;2;94;129;172m'   # Accent Bluish
readonly NORD11='\033[38;2;191;97;106m'   # Reddish
readonly NORD13='\033[38;2;235;203;139m'  # Yellowish
readonly NORD14='\033[38;2;163;190;140m'  # Greenish
readonly NC='\033[0m'                     # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="${NC}"

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
            *)     color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    # Append log entry to log file and output to stderr with color
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
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
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here
}

trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
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
# MAIN FUNCTION: Configure and Mount WD External ZFS Pool
# ------------------------------------------------------------------------------
configure_zfs_pool() {
    print_section "Configuring WD External ZFS Pool on FreeBSD"

    local ZPOOL_NAME="WD_BLACK"
    # Set desired mount point (using /mnt on FreeBSD)
    local MOUNT_POINT="/mnt/${ZPOOL_NAME}"

    # Ensure the mount point directory exists
    if [[ ! -d "$MOUNT_POINT" ]]; then
        log INFO "Creating mount point directory: $MOUNT_POINT"
        mkdir -p "$MOUNT_POINT" || handle_error "Failed to create mount point directory: $MOUNT_POINT"
    fi

    # Check if the pool is already imported; if not, import it
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import -f "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already imported."
    fi

    # Check and set the pool's mountpoint if necessary
    local current_mountpoint
    current_mountpoint=$(zfs get -H -o value mountpoint "$ZPOOL_NAME")
    if [[ "$current_mountpoint" != "$MOUNT_POINT" ]]; then
        log INFO "Setting mountpoint for pool '$ZPOOL_NAME' to '$MOUNT_POINT'..."
        if ! zfs set mountpoint="$MOUNT_POINT" "$ZPOOL_NAME"; then
            handle_error "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "Mountpoint for pool '$ZPOOL_NAME' is already set to '$MOUNT_POINT'."
    fi

    # Ensure the pool is mounted
    if ! mount | grep -q "on ${MOUNT_POINT} "; then
        log INFO "Mounting ZFS pool '$ZPOOL_NAME'..."
        if ! zfs mount "$ZPOOL_NAME"; then
            handle_error "Failed to mount ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already mounted on '$MOUNT_POINT'."
    fi

    # Verify auto-mounting is enabled (FreeBSD uses /etc/rc.conf)
    if ! grep -q '^zfs_enable="YES"' /etc/rc.conf; then
        log WARN "zfs_enable is not set to YES in /etc/rc.conf. Auto-mounting at boot may not work."
        log INFO "To enable auto-mounting, add the following line to /etc/rc.conf:"
        log INFO '  zfs_enable="YES"'
    else
        log INFO "Auto-mounting is enabled in /etc/rc.conf."
    fi

    log INFO "WD External ZFS Pool configuration completed successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure the log directory exists; create it if missing
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi

    # Ensure the log file exists and set secure permissions
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Execute the configuration function
    configure_zfs_pool

    log INFO "Script execution finished successfully."
}

# Execute main() if the script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi