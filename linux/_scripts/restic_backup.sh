#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: restic-backup.sh
# Description: Automated backup solution using Restic with a Backblaze B2 backend.
#              This script performs system and Plex backups, initializes the
#              repository if necessary, and runs maintenance to prune old snapshots.
#              Hardcoded credentials are used for demonstration purposes.
# Author: dunamismax | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Instructions:
#   List specific backups:
#     - List only system backups:
#         restic snapshots --tag system-backup
#     - List only Plex backups:
#         restic snapshots --tag plex-backup
#
#   Restore specific backups:
#     - Restore latest system backup:
#         restic restore latest --tag system-backup
#     - Restore latest Plex backup:
#         restic restore latest --tag plex-backup
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
trap 'handle_signal' INT TERM

# ------------------------------------------------------------------------------
# ENVIRONMENT VARIABLES (HARD-CODED)
# ------------------------------------------------------------------------------
export RESTIC_PASSWORD="j57z66Mwc^2A%Cf5!iAG^n&c&%wJ"
export B2_ACCOUNT_ID="005531878ffff660000000001"
export B2_ACCOUNT_KEY="K005oVgYPouP1DMQa5jhGfRBiX33Kns"
export RESTIC_REPOSITORY="b2:sawyer-backups:ubuntu-backup"

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES (CONFIGURATION)
# ------------------------------------------------------------------------------
declare -A CONFIG=(
    [LOG_FILE]="/var/log/restic-backup.log"
    [RETENTION_DAYS]=7
    [PLEX_SOURCE]="/var/lib/plexmediaserver/"
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
    ["lost+found"]=1
    ["var/tmp"]=1
    ["var/cache"]=1
    ["var/log"]=1
    ["var/lib/lxcfs"]=1
    ["var/lib/docker"]=1
    ["root/.cache"]=1
    ["home/*/.cache"]=1
    ["home/*/.local/share/Trash"]=1
    ["*.iso"]=1
    ["*.tmp"]=1
    ["*.swap.img"]=1
    [snap]=1
    ["var/lib/snapd"]=1
    ["var/lib/apt/lists"]=1
    ["var/spool"]=1
    ["var/lib/systemd/coredump"]=1
    ["var/lib/update-notifier"]=1
    ["var/lib/NetworkManager"]=1
    ["lib/modules"]=1
    ["lib/firmware"]=1
    ["var/lib/libvirt/images"]=1
    ["home/*/VirtualBox VMs"]=1
    ["var/lib/plexmediaserver"]=1
)

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9
NORD5='\033[38;2;229;233;240m'   # #E5E9F0
NORD6='\033[38;2;236;239;244m'   # #ECEFF4
NORD7='\033[38;2;143;188;187m'   # #8FBCBB
NORD8='\033[38;2;136;192;208m'   # #88C0D0
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD10='\033[38;2;94;129;172m'   # #5E81AC
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD12='\033[38;2;208;135;112m'  # #D08770
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NORD15='\033[38;2;180;142;173m'  # #B48EAD
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"

    local color_code="$NC"
    case "$upper_level" in
        INFO)  color_code="${NORD14}" ;;  # Info: greenish
        WARN|WARNING)
            upper_level="WARN"
            color_code="${NORD13}" ;;      # Warning: yellowish
        ERROR) color_code="${NORD11}" ;;      # Error: reddish
        DEBUG) color_code="${NORD9}" ;;       # Debug: bluish
    esac

    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "${CONFIG[LOG_FILE]}"
    if [[ -t 2 ]]; then
        printf "%b%s%b\n" "$color_code" "$log_entry" "$NC" >&2
    else
        echo "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & SIGNAL FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log DEBUG "Stack trace (most recent call last):"
    for (( i=${#FUNCNAME[@]}-1; i>1; i-- )); do
        log DEBUG "  [${BASH_SOURCE[$i]}:${BASH_LINENO[$((i-1))]}] in ${FUNCNAME[$i]}"
    done
    exit "$exit_code"
}

handle_signal() {
    log WARN "Termination signal received."
    handle_error "Script interrupted by user" 130
}

trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
trap 'handle_signal' INT TERM

# ------------------------------------------------------------------------------
# INITIALIZATION FUNCTIONS
# ------------------------------------------------------------------------------
init_system() {
    # Duplicate file descriptors to capture log output
    exec 3>&1 4>&2
    trap 'exec 1>&3 2>&4' EXIT
    exec > >(tee -a "${CONFIG[LOG_FILE]}" >&3) 2> >(tee -a "${CONFIG[LOG_FILE]}" >&4)

    umask 077
    touch "${CONFIG[LOG_FILE]}" || handle_error "Failed to create log file: ${CONFIG[LOG_FILE]}"
    chmod 640 "${CONFIG[LOG_FILE]}" || handle_error "Failed to set permissions on log file"

    log INFO "Restic Backup initialization started..."
    log DEBUG "Script PID: $$"
}

print_divider() {
    log INFO "------------------------------------------------------------------------"
}

# ------------------------------------------------------------------------------
# BACKUP FUNCTIONS
# ------------------------------------------------------------------------------
init_repository() {
    print_divider
    log INFO "Checking/Initializing Restic repository..."
    if ! restic snapshots &>/dev/null; then
        log INFO "Repository not initialized. Initializing now..."
        restic init || handle_error "Failed to initialize repository"
        log INFO "Repository initialized successfully."
    else
        log INFO "Repository already initialized."
    fi
}

create_excludes_file() {
    local exclude_file
    exclude_file=$(mktemp) || handle_error "Failed to create temporary exclusion file"
    for pattern in "${!SYSTEM_EXCLUDES[@]}"; do
        echo "$pattern"
    done > "$exclude_file"
    echo "$exclude_file"
}

run_system_backup() {
    print_divider
    log INFO "Starting System Backup..."
    local exclude_file
    exclude_file=$(create_excludes_file)
    log INFO "Running Restic backup for system (excluding specified paths)..."
    restic backup \
        --exclude-file="$exclude_file" \
        --one-file-system \
        --tag system-backup \
        / || handle_error "System backup failed"
    rm -f "$exclude_file"
    log INFO "System Backup completed successfully."
}

run_plex_backup() {
    print_divider
    log INFO "Starting Plex Backup..."
    log INFO "Stopping Plex service..."
    systemctl stop plexmediaserver || handle_error "Failed to stop Plex service"
    log INFO "Running Restic backup for Plex..."
    restic backup \
        --tag plex-backup \
        "${CONFIG[PLEX_SOURCE]}" || handle_error "Plex backup failed"
    log INFO "Starting Plex service..."
    systemctl start plexmediaserver || handle_error "Failed to start Plex service"
    log INFO "Plex Backup completed successfully."
}

run_maintenance() {
    print_divider
    log INFO "Running repository maintenance..."
    log INFO "Removing snapshots older than ${CONFIG[RETENTION_DAYS]} days..."
    restic forget --keep-within "${CONFIG[RETENTION_DAYS]}d" --prune || handle_error "Failed to remove old snapshots"
    log INFO "Checking repository integrity..."
    restic check || handle_error "Repository check failed"
    log INFO "Maintenance completed successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    init_system
    log INFO "======================"
    log INFO "  RESTIC BACKUP START "
    log INFO "======================"
    init_repository
    run_system_backup
    run_plex_backup
    run_maintenance
    log INFO "======================"
    log INFO "  RESTIC BACKUP END   "
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