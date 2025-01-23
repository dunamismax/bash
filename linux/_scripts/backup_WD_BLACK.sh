#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: rsync_backup.sh
# Description: Backup files and folders recursively using rsync with progress and error handling.
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./rsync_backup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/rsync_backup.log"  # Path to the log file
SOURCE_DIR="/media/WD_BLACK/Entertainment"  # Source directory
DEST_DIR="/media/WD_Elements/Stephen-WD_BLACK-Backup"  # Destination directory

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
# RSYNC BACKUP FUNCTION
# ------------------------------------------------------------------------------
perform_backup() {
    log INFO "--------------------------------------"
    log INFO "Starting backup process..."

    # Check if source directory exists
    if [[ ! -d "$SOURCE_DIR" ]]; then
        handle_error "Source directory does not exist: $SOURCE_DIR"
    fi

    # Check if destination directory exists, create if not
    if [[ ! -d "$DEST_DIR" ]]; then
        log INFO "Destination directory does not exist. Creating: $DEST_DIR"
        mkdir -p "$DEST_DIR" || handle_error "Failed to create destination directory: $DEST_DIR"
    fi

    # Perform rsync with progress and error handling
    log INFO "Starting rsync from $SOURCE_DIR to $DEST_DIR..."
    rsync -av --progress --stats "$SOURCE_DIR/" "$DEST_DIR/" || handle_error "rsync failed."

    log INFO "Backup completed successfully."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# MAIN
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

    # Perform the backup
    perform_backup

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi