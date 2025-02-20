#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: backblaze_b2_backup.sh
# Description: Backup script for uploading data to Backblaze B2 with retention.
#              Uploads data from the WD drive (mounted at /mnt/WD_BLACK/BACKUP/)
#              to Backblaze B2 and deletes backups older than a specified age.
# Author: Your Name | License: MIT | Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./backblaze_b2_backup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
BACKUP_SOURCE="/mnt/WD_BLACK/BACKUP/"
BACKUP_DEST="Backblaze:sawyer-backups"
LOG_FILE="/var/log/backblaze-b2-backup.log"
RCLONE_CONFIG="/usr/home/sawyer/.config/rclone/rclone.conf"
RETENTION_DAYS=30

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
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
upload_backup() {
    log INFO "Starting direct upload of $BACKUP_SOURCE to Backblaze B2: $BACKUP_DEST"
    # Upload using rclone with verbose output
    if rclone --config "$RCLONE_CONFIG" copy "$BACKUP_SOURCE" "$BACKUP_DEST" -vv; then
        log INFO "Backup uploaded successfully."
    else
        handle_error "Failed to upload backup."
    fi
}

cleanup_backups() {
    log INFO "Removing old backups (older than ${RETENTION_DAYS} days) from Backblaze B2: $BACKUP_DEST"
    # Delete old backups using rclone
    if rclone --config "$RCLONE_CONFIG" delete "$BACKUP_DEST" --min-age "${RETENTION_DAYS}d" -vv; then
        log INFO "Old backups removed successfully."
    else
        log WARN "Failed to remove some old backups."
    fi
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run as root
    check_root

    # Ensure the log directory exists and is writable
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Check if BACKUP_SOURCE directory exists
    if [[ ! -d "$BACKUP_SOURCE" ]]; then
        handle_error "Backup source directory '$BACKUP_SOURCE' does not exist."
    fi

    # Validate rclone configuration file existence
    if [[ ! -f "$RCLONE_CONFIG" ]]; then
        handle_error "rclone config file '$RCLONE_CONFIG' not found."
    fi

    # Perform backup upload and cleanup of old backups
    upload_backup
    cleanup_backups

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
