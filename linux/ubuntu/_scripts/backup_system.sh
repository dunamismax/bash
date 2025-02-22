#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: ubuntu_backup.sh
# Description: Backup script for Ubuntu systems with compression and retention,
#              using the WD drive mounted at /mnt/WD_BLACK. Logs are stored at
#              /var/log/ubuntu_backup.log.
# Author: Your Name | License: MIT | Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./ubuntu_backup.sh
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/ubuntu_backup.log by default.
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
readonly LOG_FILE="/var/log/ubuntu_backup.log"            # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"         # Set to "true" to disable colored output
readonly DEFAULT_LOG_LEVEL="INFO"                          # Default log level (VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL)

# Backup configuration
readonly SOURCE="/"                                       # Source directory for backup
readonly DESTINATION="/mnt/WD_BLACK/BACKUP/ubuntu-backups" # Destination directory for backups
readonly RETENTION_DAYS=7                                  # Days to retain old backups
readonly TIMESTAMP
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
readonly BACKUP_NAME="backup-$TIMESTAMP.tar.gz"            # Backup archive name

# Exclusion patterns for tar
readonly EXCLUDES=(
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
    "*.iso"
    "*.tmp"
    "*.swap.img"
)
# Build exclusion arguments for tar
EXCLUDES_ARGS=()
for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
done

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
    local lvl="${1^^}"  # uppercase
    case "$lvl" in
        VERBOSE|V)      echo 0 ;;
        DEBUG|D)        echo 1 ;;
        INFO|I)         echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)        echo 4 ;;
        CRITICAL|C)     echo 5 ;;
        *)              echo 2 ;;  # default to INFO if unknown
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL message
# Example: log INFO "Starting process..."
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
        return 0  # Skip messages below current log threshold.
    fi

    # Choose color (only for interactive stderr output).
    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)   color="${NORD9}"  ;;  # Bluish
            INFO)    color="${NORD14}" ;;  # Greenish
            WARN)    color="${NORD13}" ;;  # Yellowish
            ERROR|CRITICAL) color="${NORD11}" ;;  # Reddish
            *)       color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    # Append plain log entry to log file (no color codes)
    echo "$log_entry" >> "$LOG_FILE"
    # Print colorized log entry to stderr
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An unknown error occurred}"
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
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

# Trap signals and errors for graceful handling
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
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
perform_backup() {
    print_section "Starting Backup Process"
    log INFO "Creating backup archive ${DESTINATION}/${BACKUP_NAME}"
    
    # Create the backup archive with exclusions, compressing via pigz.
    if tar -I pigz -cf "${DESTINATION}/${BACKUP_NAME}" "${EXCLUDES_ARGS[@]}" -C "$SOURCE" .; then
        log INFO "Backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Backup process failed."
    fi
}

cleanup_backups() {
    print_section "Cleaning Up Old Backups"
    log INFO "Removing backups in ${DESTINATION} older than ${RETENTION_DAYS} days"
    # Find and remove files older than RETENTION_DAYS days.
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -delete; then
        log INFO "Old backups removed successfully."
    else
        log WARN "Failed to remove some old backups."
    fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure the log directory exists; create if missing.
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Create the destination directory if it doesn't exist.
    mkdir -p "$DESTINATION" || handle_error "Failed to create destination directory: $DESTINATION"

    # Check if the destination mount point is active.
    if ! mount | grep -q "$DESTINATION"; then
        handle_error "Destination mount point '$DESTINATION' is not available."
    fi

    # Execute backup and cleanup functions.
    perform_backup
    cleanup_backups

    log INFO "Script execution finished successfully."
}

# Invoke main() if the script is executed directly.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
