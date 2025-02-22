#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: backblaze_b2_backup.sh
# Description: Backup script for uploading data to Backblaze B2 with retention.
#              Uploads data from the WD drive (mounted at /mnt/WD_BLACK/BACKUP/)
#              to Backblaze B2 and deletes backups older than a specified age.
# Author: Your Name | License: MIT | Version: 3.2
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./backblaze_b2_backup.sh
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/backblaze-b2-backup.log by default.
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
readonly BACKUP_SOURCE="/mnt/WD_BLACK/BACKUP/"
readonly BACKUP_DEST="Backblaze:sawyer-backups"
readonly LOG_FILE="/var/log/backblaze-b2-backup.log"
readonly RCLONE_CONFIG="/home/sawyer/.config/rclone/rclone.conf"
readonly RETENTION_DAYS=30

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
# Example: log INFO "Starting upload..."
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
upload_backup() {
    print_section "Uploading Backup to Backblaze B2"
    log INFO "Starting direct upload of $BACKUP_SOURCE to Backblaze B2: $BACKUP_DEST"

    # Upload using rclone with verbose output.
    if rclone --config "$RCLONE_CONFIG" copy "$BACKUP_SOURCE" "$BACKUP_DEST" -vv; then
        log INFO "Backup uploaded successfully."
    else
        handle_error "Failed to upload backup."
    fi
}

cleanup_backups() {
    print_section "Cleaning Up Old Backups on Backblaze B2"
    log INFO "Removing old backups (older than ${RETENTION_DAYS} days) from Backblaze B2: $BACKUP_DEST"

    # Delete old backups using rclone.
    if rclone --config "$RCLONE_CONFIG" delete "$BACKUP_DEST" --min-age "${RETENTION_DAYS}d" -vv; then
        log INFO "Old backups removed successfully."
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

    # Validate backup source directory.
    if [[ ! -d "$BACKUP_SOURCE" ]]; then
        handle_error "Backup source directory '$BACKUP_SOURCE' does not exist."
    fi

    # Validate rclone configuration file.
    if [[ ! -f "$RCLONE_CONFIG" ]]; then
        handle_error "rclone config file '$RCLONE_CONFIG' not found."
    fi

    upload_backup
    cleanup_backups

    log INFO "Script execution finished."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
