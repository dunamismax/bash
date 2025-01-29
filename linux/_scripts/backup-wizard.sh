#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: backup-wizard.sh
# Description: Simplified incremental backup solution using rsync and rclone.
# Author: dunamismax | License: MIT
# Version: 1.0.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./backup-wizard.sh
#
# Notes:
#   - Ensure you have rsync, rclone, and systemd (for Plex service handling).
#   - Adjust CONFIG values, directories, and excludes as needed.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# For more information, see:
#   https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"

    log ERROR "$error_message"
    log DEBUG "Stack trace (most recent call last):"

    # Print a stack trace for easier debugging
    local i
    for (( i=${#FUNCNAME[@]}-1 ; i>1 ; i-- )); do
        log DEBUG "  [${BASH_SOURCE[$i]}:${BASH_LINENO[$((i-1))]}] in ${FUNCNAME[$i]}"
    done

    exit "$exit_code"
}

handle_signal() {
    log WARN "Termination signal received."
    handle_error "Script interrupted by user" 130
}

# Trap any uncaught errors and signals
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
trap 'handle_signal' INT TERM

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES (CONFIGURATION)
# ------------------------------------------------------------------------------
declare -A CONFIG=(
    # ----------------------------------------------------------------------------
    # Backup Locations
    # ----------------------------------------------------------------------------
    [FULL_SYSTEM_SOURCE]="/"
    [FULL_SYSTEM_DEST]="/media/WD_BLACK/backup/ubuntu-backups"
    [FULL_SYSTEM_RETENTION]=7

    [PLEX_SOURCE]="/var/lib/plexmediaserver/"
    [PLEX_DEST]="/media/WD_BLACK/backup/plex-backups"
    [PLEX_RETENTION]=7

    [BACKUP_SOURCE]="/media/WD_BLACK/backup/"
    [BACKBLAZE_DEST]="Backblaze:sawyer-backups"
    [RCLONE_CONFIG]="/home/sawyer/.config/rclone/rclone.conf"
    [BACKBLAZE_RETENTION]=30

    # ----------------------------------------------------------------------------
    # Logging
    # ----------------------------------------------------------------------------
    [LOG_FILE]="/var/log/backup-wizard.log"

    # ----------------------------------------------------------------------------
    # Safety Margin (20% free space required)
    # ----------------------------------------------------------------------------
    [MIN_FREE_SPACE]=20

    # ----------------------------------------------------------------------------
    # Network Configuration (example placeholder)
    # ----------------------------------------------------------------------------
    [CF_ZONE_ID]="dc739d9b91869a4ff2c8002125f6836c"
)

declare -A SYSTEM_EXCLUDES=(
  [proc]=1
  [sys]=1
  [dev]=1
  [run]=1
  [tmp]=1
  [mnt]=1
  [media]=1
  [swapfile]=1
  [lost+found]=1
  [var/tmp]=1
  [var/cache]=1
  [var/log]=1
  [var/lib/lxcfs]=1
  [var/lib/docker]=1
  [root/.cache]=1
  [home/*/.cache]=1
  [home/*/.local/share/Trash]=1
  [*.iso]=1
  [*.tmp]=1
  [*.swap.img]=1

  # Snap
  [snap]=1
  [var/lib/snapd]=1

  # Apt lists
  [var/lib/apt/lists]=1

  # Additional ephemeral
  [var/spool]=1
  [var/lib/systemd/coredump]=1
  [var/lib/update-notifier]=1
  [var/lib/NetworkManager]=1

  # If you don’t need kernel modules or firmware:
  [lib/modules]=1
  [lib/firmware]=1

  # If you want to skip VMs
  [var/lib/libvirt/images]=1

  # If you use VirtualBox and want to exclude VMs
  [home/*/VirtualBox VMs]=1

  # If you want to exclude Plex’s own data (already in your script as /var/lib/plexmediaserver):
  [var/lib/plexmediaserver]=1
)

# ------------------------------------------------------------------------------
# COLOR CONSTANTS (Used for Logging)
# ------------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage:
    #   log [LEVEL] "Message text"
    #
    # Example:
    #   log INFO "Starting backup..."
    # ----------------------------------------------------------------------------

    local level="${1:-INFO}"
    shift
    local message="$*"

    # Convert level to uppercase
    local upper_level="${level^^}"

    # Get timestamp
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"

    # Determine the color based on level
    local color_code="$NC"
    case "$upper_level" in
        INFO)   color_code="$GREEN" ;;
        WARN|WARNING)
            upper_level="WARN"
            color_code="$YELLOW"
            ;;
        ERROR)  color_code="$RED" ;;
        DEBUG)  color_code="$BLUE" ;;
    esac

    # Construct log entry
    local log_entry="[$timestamp] [$upper_level] $message"

    # Always write to log file (uncolored)
    echo "$log_entry" >> "${CONFIG[LOG_FILE]}"

    # Write to console (stderr) with color if terminal is interactive
    if [[ -t 2 ]]; then
        printf "%b%s%b\n" "$color_code" "$log_entry" "$NC" >&2
    else
        echo "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
init_system() {
    # Send stdout and stderr to both terminal and log file
    exec 3>&1 4>&2
    trap 'exec 1>&3 2>&4' EXIT
    exec > >(tee -a "${CONFIG[LOG_FILE]}" >&3) 2> >(tee -a "${CONFIG[LOG_FILE]}" >&4)

    # Secure log file permissions
    umask 077
    chmod 640 "${CONFIG[LOG_FILE]}"

    log INFO "Backup Wizard initialization started..."
    log DEBUG "Script PID: $$"
}

check_free_space() {
    # Ensures a given directory has at least MIN_FREE_SPACE% free
    #
    # Usage:
    #   check_free_space "/some/path" MIN_PERCENT
    # ----------------------------------------------------------------------------
    local path="$1"
    local required="$2"

    # Ensure directory exists
    if [[ ! -d "$path" ]]; then
        handle_error "Path $path does not exist or is inaccessible"
    fi

    # Gather disk usage info
    local free_space total_space percent_free
    free_space=$(df -P "$path" | awk 'NR==2 {print $4}')
    total_space=$(df -P "$path" | awk 'NR==2 {print $2}')
    percent_free=$((free_space * 100 / total_space))

    # Check threshold
    if (( percent_free < required )); then
        handle_error "Insufficient space in $path ($percent_free% < $required%)"
    else
        log DEBUG "Free space in $path: $percent_free% (Required: $required%)"
    fi
}

print_divider() {
    # Simple separator for readability
    log INFO "------------------------------------------------------------------------"
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS (BACKUP MODULES)
# ------------------------------------------------------------------------------
run_full_system_backup() {
    print_divider
    log INFO "Starting Full System Backup..."

    # 1. Check free space
    check_free_space "${CONFIG[FULL_SYSTEM_DEST]}" "${CONFIG[MIN_FREE_SPACE]}"

    # 2. Build exclusion file
    local exclude_file
    exclude_file="$(mktemp)" || handle_error "Failed to create temporary exclusion file"

    cleanup() {
        if [[ -f "$exclude_file" ]]; then
            rm -f "$exclude_file"
            log DEBUG "Cleaned up temporary exclusion file: $exclude_file"
        fi
    }
    trap cleanup EXIT

    # Populate the exclusion file
    printf "%s\n" "${!SYSTEM_EXCLUDES[@]}" > "$exclude_file"

    # 3. Perform rsync
    log INFO "Running rsync for system backup..."
    rsync -aAXv --exclude-from="$exclude_file" --delete \
        "${CONFIG[FULL_SYSTEM_SOURCE]}" "${CONFIG[FULL_SYSTEM_DEST]}" \
        || handle_error "Full system backup failed"

    log INFO "Full System Backup completed successfully."
    print_divider
}

run_plex_backup() {
    print_divider
    log INFO "Starting Plex Backup..."

    local plex_service="plexmediaserver"
    local was_running=false

    # 1. Stop Plex if running
    if systemctl is-active --quiet "$plex_service"; then
        log INFO "Plex is running; stopping service for backup."
        if systemctl stop "$plex_service"; then
            was_running=true
            log INFO "Plex service stopped."
        else
            handle_error "Failed to stop Plex service"
        fi
    else
        log INFO "Plex service is already stopped; proceeding."
    fi

    # 2. Ensure Plex destination exists
    mkdir -p "${CONFIG[PLEX_DEST]}" || handle_error \
        "Failed to create Plex backup directory: ${CONFIG[PLEX_DEST]}"

    # 3. Perform rsync
    log INFO "Running rsync for Plex backup..."
    rsync -aAXv --delete \
        "${CONFIG[PLEX_SOURCE]}" "${CONFIG[PLEX_DEST]}" \
        || handle_error "Plex backup failed"

    # 4. Restart Plex if it was running
    if $was_running; then
        log INFO "Restarting Plex service..."
        if ! systemctl start "$plex_service"; then
            log ERROR "Failed to restart Plex service"
            handle_error "Plex service could not be restarted"
        else
            log INFO "Plex service restarted successfully."
        fi
    fi

    log INFO "Plex Backup completed successfully."
    print_divider
}

run_backblaze_backup() {
    print_divider
    log INFO "Starting Backblaze Sync..."

    # 1. Validate source and config
    if [[ ! -d "${CONFIG[BACKUP_SOURCE]}" ]]; then
        handle_error "Backup source directory is missing: ${CONFIG[BACKUP_SOURCE]}"
    fi
    if [[ ! -f "${CONFIG[RCLONE_CONFIG]}" ]]; then
        handle_error "Rclone config file missing: ${CONFIG[RCLONE_CONFIG]}"
    fi

    log INFO "Syncing from '${CONFIG[BACKUP_SOURCE]}' to '${CONFIG[BACKBLAZE_DEST]}'"
    log DEBUG "Using rclone config: ${CONFIG[RCLONE_CONFIG]}"

    # 2. Retry logic
    local max_retries=3
    local retry_delay=30
    local attempt=1
    local success=false

    while (( attempt <= max_retries )); do
        log INFO "Rclone sync attempt $attempt of $max_retries..."

        if rclone --config "${CONFIG[RCLONE_CONFIG]}" sync \
            --checksum --b2-hard-delete --transfers 4 \
            --progress --log-level INFO \
            "${CONFIG[BACKUP_SOURCE]}" "${CONFIG[BACKBLAZE_DEST]}"; then
            success=true
            break
        else
            log WARN "Sync attempt $attempt failed; retrying in $retry_delay seconds..."
            sleep "$retry_delay"
            ((attempt++))
        fi
    done

    # 3. Final check
    if ! $success; then
        handle_error "Backblaze sync failed after $max_retries attempts"
    fi

    log INFO "Backblaze Sync completed successfully."
    print_divider
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    init_system
    log INFO "======================"
    log INFO "  BACKUP WIZARD START "
    log INFO "======================"

    run_full_system_backup
    run_plex_backup
    run_backblaze_backup

    log INFO "======================"
    log INFO " BACKUP WIZARD FINISH "
    log INFO "======================"
    log INFO "All operations completed successfully."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    exit 0
fi
