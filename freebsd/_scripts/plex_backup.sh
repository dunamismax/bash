#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: plex_backup.sh
# Description: Backup script for Plex Media Server data with compression and
#              retention on FreeBSD, storing backups on a WD drive mounted at
#              /mnt/WD_BLACK.
# Author: Your Name | License: MIT | Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./plex_backup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
# Adjust SOURCE as needed if Plex data is located elsewhere on your FreeBSD system.
SOURCE="/usr/local/plexdata/Library/Application Support/Plex Media Server/"
DESTINATION="/mnt/WD_BLACK/BACKUP/plex-backups"
LOG_FILE="/var/log/plex-backup.log"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="plex-backup-$TIMESTAMP.tar.gz"

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
    echo "$log_entry" >> "$LOG_FILE"
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
perform_backup() {
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
    log INFO "Removing backups older than ${RETENTION_DAYS} days from ${DESTINATION}"
    # Use find to locate and remove files older than RETENTION_DAYS.
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -delete; then
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
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
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

    # Perform backup and cleanup.
    perform_backup
    cleanup_backups

    log INFO "Script execution finished."
}

# Execute main function if script is run directly.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi