#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: backblaze_b2_backup.sh
# Description: Uploads a local directory to Backblaze B2 and cleans up old backups.
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./backblaze_b2_backup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
BACKUP_SOURCE="/mnt/media/WD_BLACK/BACKUP/"
BACKUP_DEST="Backblaze:sawyer-backups"
LOG_FILE="/var/log/backblaze-b2-backup.log"
RCLONE_CONFIG="/home/sawyer/.config/rclone/rclone.conf"
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

    # Log the error with additional context
    log ERROR "$error_message"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

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

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

validate_source() {
    if [ ! -d "$BACKUP_SOURCE" ]; then
        handle_error "Backup source directory '$BACKUP_SOURCE' does not exist."
    fi
}

validate_rclone_config() {
    if [ ! -f "$RCLONE_CONFIG" ]; then
        handle_error "rclone config file '$RCLONE_CONFIG' not found."
    fi
}

setup_log_file() {
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 644 "$LOG_FILE"
    exec > >(tee -a "$LOG_FILE") 2>&1
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
upload_backup() {
    log INFO "Starting direct upload of $BACKUP_SOURCE to Backblaze B2: $BACKUP_DEST"
    if rclone --config "$RCLONE_CONFIG" copy "$BACKUP_SOURCE" "$BACKUP_DEST" -vv; then
        log INFO "Backup uploaded successfully."
    else
        handle_error "Failed to upload backup."
    fi
}

cleanup_backups() {
    log INFO "Removing old backups (older than ${RETENTION_DAYS} days) from Backblaze B2: $BACKUP_DEST"
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
    log INFO "--------------------------------------"
    log INFO "Starting Backblaze B2 Direct Upload Backup Script"

    # Ensure the script is run as root
    check_root

    # Check for required commands
    for cmd in rclone tee; do
        if ! command_exists "$cmd"; then
            handle_error "Required command '$cmd' is not installed."
        fi
    done

    # Validate source directory and rclone config
    validate_source
    validate_rclone_config

    # Ensure the log file exists and has proper permissions
    setup_log_file

    # Perform the backup and cleanup
    upload_backup
    cleanup_backups

    log INFO "Backup and cleanup completed successfully on $(date)."
    log INFO "--------------------------------------"
}

# Execute main if this script is run directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi