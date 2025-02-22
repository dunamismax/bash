#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: plex_backup.sh
# Description: Backup script for Plex Media Server data with compression and
#              retention on Ubuntu, storing backups on a WD drive mounted at
#              /mnt/WD_BLACK.
# Author: Your Name | License: MIT | Version: 3.2
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./plex_backup.sh
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/plex-backup.log by default.
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
# Adjust SOURCE if Plex data is located elsewhere.
readonly SOURCE="/usr/local/plexdata/Library/Application Support/Plex Media Server/"
readonly DESTINATION="/mnt/WD_BLACK/BACKUP/plex-backups"
readonly LOG_FILE="/var/log/plex-backup.log"
readonly RETENTION_DAYS=7
readonly TIMESTAMP
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
readonly BACKUP_NAME="plex-backup-${TIMESTAMP}.tar.gz"

readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"
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
# Example: log INFO "Starting backup process..."
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
check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# Prints a styled section header using Nord accent colors.
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
perform_backup() {
    print_section "Performing Plex Backup"
    log INFO "Starting on-the-fly backup and compression to ${DESTINATION}/${BACKUP_NAME}"

    # Compress and stream directly to the destination using pigz.
    # The --one-file-system flag prevents crossing filesystem boundaries.
    if tar -I pigz --one-file-system -cf "${DESTINATION}/${BACKUP_NAME}" -C "$SOURCE" .; then
        log INFO "Backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Backup process failed."
    fi
}

cleanup_backups() {
    print_section "Cleaning Up Old Backups"
    log INFO "Removing backups older than ${RETENTION_DAYS} days from ${DESTINATION}"
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +${RETENTION_DAYS} -delete; then
        log INFO "Old backups removed."
    else
        log WARN "Failed to remove some old backups."
    fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    check_root

    # Ensure the log directory exists and is writable.
    local log_dir
    log_dir=$(dirname "$LOG_FILE")
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Verify that the Plex data source directory exists.
    if [[ ! -d "$SOURCE" ]]; then
        handle_error "Source directory '$SOURCE' does not exist."
    fi

    # Create destination directory if it doesn't exist.
    mkdir -p "$DESTINATION" || handle_error "Failed to create destination directory: $DESTINATION"

    # Check if the destination mount point is available.
    if ! mount | grep -q "$DESTINATION"; then
        handle_error "Destination mount point for '$DESTINATION' is not available."
    fi

    perform_backup
    cleanup_backups

    log INFO "Script execution finished."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
