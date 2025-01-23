#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: system_backup.sh
# Description: Creates a compressed backup of the entire Ubuntu system (excluding unnecessary directories).
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./system_backup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
SOURCE="/"
DESTINATION="/media/WD_BLACK/BACKUP/ubuntu-backups"
LOG_FILE="/var/log/ubuntu-backup.log"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="backup-$TIMESTAMP.tar.gz"

# Exclusions for tar backup
EXCLUDES=(
    "./proc/*"
    "./sys/*"
    "./dev/*"
    "./run/*"
    "./tmp/*"
    "./mnt/*"
    "./media/*"
    "./swapfile"
    "./lost+found"
    "./var/tmp/*"
    "./var/cache/*"
    "./var/log/*"
    "./var/lib/lxcfs/*"
    "./var/lib/docker/*"
    "./root/.cache/*"
    "./home/*/.cache/*"
    "./var/lib/plexmediaserver/*"
    "*.iso"
    "*.tmp"
    "*.swap.img"
)

# Create exclusion string for tar
EXCLUDES_ARGS=()
for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
done

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

check_commands() {
    local required_commands=("tar" "pigz" "find" "tee" "df" "mountpoint")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            handle_error "Required command '$cmd' is not installed."
        fi
    done
}

validate_destination() {
    # Create destination directory if it doesn't exist
    mkdir -p "$DESTINATION" || handle_error "Failed to create destination directory: $DESTINATION"

    # Check if the destination is on a mounted filesystem
    local mounted_parent
    mounted_parent=$(df --output=target "$DESTINATION" | tail -1)
    if [ -z "$mounted_parent" ] || ! mountpoint -q "$mounted_parent"; then
        handle_error "Destination mount point for '$DESTINATION' is not available."
    fi
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
perform_backup() {
    log INFO "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"

    # Compress and stream directly to the destination using pigz for speed, applying exclusions.
    if tar -I pigz --one-file-system -cf "$DESTINATION/$BACKUP_NAME" \
        "${EXCLUDES_ARGS[@]}" -C / .; then
        log INFO "Backup and compression completed: $DESTINATION/$BACKUP_NAME"
    else
        handle_error "Backup process failed."
    fi
}

cleanup_backups() {
    log INFO "Removing old backups from $DESTINATION older than $RETENTION_DAYS days"
    # Find and remove files older than RETENTION_DAYS
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -exec rm -f {} \;; then
        log INFO "Old backups removed."
    else
        log WARN "Failed to remove some old backups."
    fi
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    log INFO "--------------------------------------"
    log INFO "Starting Ubuntu Backup Script"

    # Ensure the script is run as root
    check_root

    # Check for required commands
    check_commands

    # Validate the destination directory and mount point
    validate_destination

    # Ensure the log file exists and has proper permissions
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 644 "$LOG_FILE"

    # Redirect all output (stdout and stderr) to both console and log file
    exec > >(tee -a "$LOG_FILE") 2>&1

    # Perform the backup and cleanup
    perform_backup
    cleanup_backups

    log INFO "Backup and cleanup completed successfully on $(date)."
    log INFO "--------------------------------------"
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi