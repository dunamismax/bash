#!/usr/bin/env bash
################################################################################
# Backup Wizard - Automated Enterprise Backup Solution
################################################################################
# Centralized system/cloud backup management with maintenance features.
# Performs secure, compressed backups with retention policies and cloud sync.
#
# Key Features:
#   • Full system snapshots with XZ compression
#   • Plex-aware backups with service control
#   • Backblaze B2/Cloudflare integration
#   • Space verification and parallel execution
#   • Automated cleanup (7d local/30d cloud retention)
#
# Usage: sudo ./backup-wizard.sh [--dry-run]
# Config: Edit CONFIG[] array and SYSTEM_EXCLUDES at script start
#
# Requirements:
#   - Root privileges
#   - Ubuntu 22.04+/Debian 11+
#   - rclone, pigz, jq, and core utilities
#   - Backblaze/Cloudflare credentials
#
# Logs: /var/log/backup-wizard.log
# Author: dunamismax | License: MIT
# Repo: https://github.com/dunamismax/bash
################################################################################

set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?"' ERR
trap 'handle_signal' INT TERM

# ------------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ------------------------------------------------------------------------------
declare -A CONFIG=(
    # Backup Locations
    [FULL_SYSTEM_SOURCE]="/"
    [FULL_SYSTEM_DEST]="/media/WD_BLACK/BACKUP/ubuntu-backups"
    [FULL_SYSTEM_RETENTION]=7
    
    [BACKUP_SOURCE]="/media/WD_BLACK/BACKUP/"
    [BACKBLAZE_DEST]="Backblaze:sawyer-backups"
    [RCLONE_CONFIG]="/home/sawyer/.config/rclone/rclone.conf"
    [BACKBLAZE_RETENTION]=30
    
    [PLEX_SOURCE]="/var/lib/plexmediaserver/"
    [PLEX_DEST]="/media/WD_BLACK/BACKUP/plex-backups"
    [PLEX_RETENTION]=7

    # System Management
    [SCRIPT_SOURCE]="/home/sawyer/github/bash/linux/_scripts"
    [SCRIPT_TARGET]="/home/sawyer/bin"

    # Network Configuration
    [CF_ZONE_ID]="dc739d9b91869a4ff2c8002125f6836c"

    # Logging
    [LOG_FILE]="/var/log/backup-wizard.log"
    
    # Safety Margin (20% free space required)
    [MIN_FREE_SPACE]=20
)

declare -A SYSTEM_EXCLUDES=(
    ["proc"]=1 ["sys"]=1 ["dev"]=1 ["run"]=1 ["tmp"]=1
    ["mnt"]=1 ["media"]=1 ["swapfile"]=1 ["lost+found"]=1
    ["var/tmp"]=1 ["var/cache"]=1 ["var/log"]=1
    ["var/lib/lxcfs"]=1 ["var/lib/docker"]=1 ["root/.cache"]=1
    ["home/*/.cache"]=1 ["var/lib/plexmediaserver"]=1
    ["*.iso"]=1 ["*.tmp"]=1 ["*.swap.img"]=1
)

# ------------------------------------------------------------------------------
# LOGGING SYSTEM
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}" message="${*:2}"
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color_code=""
    
    if [ -t 2 ]; then
        declare -A LEVEL_COLORS=(
            [INFO]='\033[0;32m'  # Green
            [WARN]='\033[0;33m'  # Yellow
            [ERROR]='\033[0;31m' # Red
            [DEBUG]='\033[0;34m' # Blue
        )
        color_code="${LEVEL_COLORS[${level^^}]:-\033[0m}"
    fi
    
    echo "$timestamp [${level^^}] $message" >> "${CONFIG[LOG_FILE]}"
    printf "${color_code}%s [%s] %s\033[0m\n" "$timestamp" "${level^^}" "$message" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLER
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-Unknown error occurred}"
    log ERROR "$error_message"
    log DEBUG "Stack trace: $(printf "  %s\n" "${FUNCNAME[@]:2}")"
    
    if [[ -n "${BACKUP_FILE:-}" && -f "$BACKUP_FILE" ]]; then
        rm -f "$BACKUP_FILE"
        log INFO "Removed incomplete backup: $BACKUP_FILE"
    fi
    
    exit 1
}

handle_signal() {
    log WARN "Received termination signal - cleaning up"
    handle_error "Script interrupted by user"
}

# ------------------------------------------------------------------------------
# CORE FUNCTIONS
# ------------------------------------------------------------------------------
init_system() {
    # Redirect stdout and stderr to both the terminal and the log file
    exec 3>&1 4>&2
    trap 'exec 1>&3 2>&4' EXIT
    exec > >(tee -a "${CONFIG[LOG_FILE]}" >&3) 2> >(tee -a "${CONFIG[LOG_FILE]}" >&4)
    
    # Set secure permissions for the log file
    umask 077
    chmod 640 "${CONFIG[LOG_FILE]}"
    
    log INFO "Initializing Backup Wizard"
    log DEBUG "Script PID: $$"
}

check_free_space() {
    local path="$1" required="$2"
    local free_space total_space percent_free

    # Validate the path exists and is accessible
    if [[ ! -d "$path" ]]; then
        handle_error "Path $path does not exist or is inaccessible"
    fi

    # Calculate free space percentage
    free_space=$(df -P "$path" | awk 'NR==2 {print $4}')
    total_space=$(df -P "$path" | awk 'NR==2 {print $2}')
    percent_free=$((free_space * 100 / total_space))

    # Check if free space meets the requirement
    if (( percent_free < required )); then
        handle_error "Insufficient space in $path ($percent_free% < $required%)"
    else
        log DEBUG "Free space in $path: $percent_free% (required: $required%)"
    fi
}

# ------------------------------------------------------------------------------
# BACKUP MODULES
# ------------------------------------------------------------------------------
run_full_system_backup() {
    log INFO "Initializing full system backup"
    local timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
    BACKUP_FILE="${CONFIG[FULL_SYSTEM_DEST]}/system-backup-$timestamp.tar.gz"
    mkdir -p "${CONFIG[FULL_SYSTEM_DEST]}" || handle_error "Failed to create backup directory"
    
    check_free_space "${CONFIG[FULL_SYSTEM_DEST]}" "${CONFIG[MIN_FREE_SPACE]}"
    
    # Create a temporary file for exclusions
    exclude_file=$(mktemp) || handle_error "Failed to create temporary exclusion file"
    
    # Ensure the temporary file is cleaned up on exit
    cleanup() {
        if [[ -f "$exclude_file" ]]; then
            rm -f "$exclude_file"
            log DEBUG "Cleaned up temporary exclusion file: $exclude_file"
        fi
    }
    trap cleanup EXIT
    
    # Write exclusions to the temporary file
    printf "%s\n" "${!SYSTEM_EXCLUDES[@]}" > "$exclude_file"
    
    log INFO "Creating system archive..."
    tar --exclude-from="$exclude_file" --one-file-system \
        --use-compress-program="pigz -9 --rsyncable" \
        -cf "$BACKUP_FILE" -C / . || handle_error "Backup creation failed"
        
    log INFO "Verifying backup integrity..."
    tar -tPf "$BACKUP_FILE" >/dev/null || handle_error "Backup verification failed"
    
    log INFO "Applying retention policy (${CONFIG[FULL_SYSTEM_RETENTION]} days)"
    find "${CONFIG[FULL_SYSTEM_DEST]}" -name "system-backup-*.tar.gz" \
        -mtime +"${CONFIG[FULL_SYSTEM_RETENTION]}" -delete
    
    unset BACKUP_FILE
    log INFO "System backup completed successfully"
}

run_plex_backup() {
    log INFO "Initializing Plex backup"
    local plex_service="plexmediaserver"
    local was_running=false
    local backup_file
    local timestamp

    # Check if Plex service is running
    if systemctl is-active --quiet "$plex_service"; then
        log INFO "Plex service is running. Stopping it for backup..."
        if systemctl stop "$plex_service"; then
            was_running=true
            log INFO "Plex service stopped successfully"
        else
            handle_error "Failed to stop Plex service"
        fi
    else
        log INFO "Plex service is not running. Proceeding with backup..."
    fi

    # Create backup destination directory if it doesn't exist
    mkdir -p "${CONFIG[PLEX_DEST]}" || handle_error "Failed to create Plex backup directory: ${CONFIG[PLEX_DEST]}"

    # Generate timestamp and backup file name
    timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
    backup_file="${CONFIG[PLEX_DEST]}/plex-backup-$timestamp.tar.gz"

    # Perform the backup
    log INFO "Creating Plex backup archive: $backup_file"
    tar --use-compress-program=pigz -cf "$backup_file" \
        -C "${CONFIG[PLEX_SOURCE]}" . || handle_error "Plex backup creation failed"

    # Verify the backup archive
    log INFO "Verifying backup integrity..."
    if ! tar -tzf "$backup_file" >/dev/null; then
        handle_error "Backup verification failed for: $backup_file"
    fi

    # Restart Plex service if it was running
    if $was_running; then
        log INFO "Restarting Plex service..."
        if ! systemctl start "$plex_service"; then
            log ERROR "Failed to restart Plex service"
            handle_error "Plex service could not be restarted"
        else
            log INFO "Plex service restarted successfully"
        fi
    fi

    # Apply retention policy
    log INFO "Applying retention policy (${CONFIG[PLEX_RETENTION]} days)..."
    find "${CONFIG[PLEX_DEST]}" -name "plex-backup-*.tar.gz" \
        -mtime +"${CONFIG[PLEX_RETENTION]}" -delete

    log INFO "Plex backup completed successfully: $backup_file"
}

run_backblaze_backup() {
    log INFO "Starting Backblaze sync"
    
    # Validate backup source and rclone config
    if [[ ! -d "${CONFIG[BACKUP_SOURCE]}" ]]; then
        handle_error "Backup source directory missing: ${CONFIG[BACKUP_SOURCE]}"
    fi
    if [[ ! -f "${CONFIG[RCLONE_CONFIG]}" ]]; then
        handle_error "Rclone config file missing: ${CONFIG[RCLONE_CONFIG]}"
    fi

    # Log the sync operation details
    log INFO "Syncing ${CONFIG[BACKUP_SOURCE]} to Backblaze B2: ${CONFIG[BACKBLAZE_DEST]}"
    log DEBUG "Using rclone config: ${CONFIG[RCLONE_CONFIG]}"

    # Perform the sync with retries for transient failures
    local max_retries=3
    local retry_delay=30
    local attempt=1
    local success=false

    while [[ $attempt -le $max_retries ]]; do
        log INFO "Sync attempt $attempt of $max_retries"
        
        if rclone --config "${CONFIG[RCLONE_CONFIG]}" sync \
            --checksum --b2-hard-delete --transfers 4 \
            --progress --log-level INFO \
            "${CONFIG[BACKUP_SOURCE]}" "${CONFIG[BACKBLAZE_DEST]}"; then
            success=true
            break
        else
            log WARN "Sync attempt $attempt failed. Retrying in $retry_delay seconds..."
            sleep $retry_delay
            ((attempt++))
        fi
    done

    # Handle sync failure after retries
    if ! $success; then
        handle_error "Backblaze sync failed after $max_retries attempts"
    fi

    log INFO "Backblaze sync completed successfully"
}

# ------------------------------------------------------------------------------
# MAINTENANCE MODULES
# ------------------------------------------------------------------------------
deploy_user_scripts() {
    log INFO "Deploying system scripts"
    
    # Validate script source ownership
    if [[ "$(stat -c %U "${CONFIG[SCRIPT_SOURCE]}")" != "sawyer" ]]; then
        handle_error "Invalid script source ownership: ${CONFIG[SCRIPT_SOURCE]}"
    fi

    # Perform a dry-run to check for issues
    log INFO "Running dry-run for script deployment..."
    if ! rsync --dry-run -ah --delete "${CONFIG[SCRIPT_SOURCE]}/" "${CONFIG[SCRIPT_TARGET]}"; then
        handle_error "Dry-run failed for script deployment"
    fi

    # Perform the actual sync
    log INFO "Deploying scripts from ${CONFIG[SCRIPT_SOURCE]} to ${CONFIG[SCRIPT_TARGET]}..."
    if ! rsync -ah --delete "${CONFIG[SCRIPT_SOURCE]}/" "${CONFIG[SCRIPT_TARGET]}"; then
        handle_error "Script deployment failed"
    fi

    # Set executable permissions on deployed scripts
    log INFO "Setting executable permissions on deployed scripts..."
    if ! find "${CONFIG[SCRIPT_TARGET]}" -type f -exec chmod 755 {} \;; then
        handle_error "Failed to update script permissions"
    fi

    log INFO "Script deployment completed successfully"
}

update_dns_records() {
    log INFO "Starting DNS update process..."
    
    # Fetch the current public IP address
    local current_ip
    if ! current_ip=$(curl -sf4 https://api.ipify.org); then
        handle_error "Failed to detect current public IP address"
    fi
    if [[ ! $current_ip =~ ^[0-9.]+$ ]]; then
        handle_error "Invalid IPv4 address detected: $current_ip"
    fi
    log INFO "Current public IP: $current_ip"

    # Fetch DNS records from Cloudflare
    local response
    if ! response=$(curl -sf -X GET "https://api.cloudflare.com/client/v4/zones/${CONFIG[CF_ZONE_ID]}/dns_records" \
        -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json"); then
        handle_error "Failed to fetch DNS records from Cloudflare"
    fi

    # Process and update DNS records
    local errors=0
    while IFS= read -r record; do
        local record_id record_name record_type record_ip proxied update_response

        # Extract record details
        record_id=$(jq -r '.id' <<< "$record") || { ((errors++)); continue; }
        record_name=$(jq -r '.name' <<< "$record") || { ((errors++)); continue; }
        record_type=$(jq -r '.type' <<< "$record") || { ((errors++)); continue; }
        record_ip=$(jq -r '.content' <<< "$record") || { ((errors++)); continue; }
        proxied=$(jq -r '.proxied' <<< "$record") || { ((errors++)); continue; }

        # Update A records if the IP has changed
        if [[ "$record_type" == "A" && "$current_ip" != "$record_ip" ]]; then
            log INFO "Updating DNS record $record_name: $record_ip → $current_ip"
            if ! update_response=$(curl -sf -X PUT \
                "https://api.cloudflare.com/client/v4/zones/${CONFIG[CF_ZONE_ID]}/dns_records/$record_id" \
                -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
                --data "{\"type\":\"A\",\"name\":\"$record_name\",\"content\":\"$current_ip\",\"ttl\":1,\"proxied\":$proxied}"); then
                ((errors++))
                continue
            fi

            # Verify the update was successful
            if ! jq -e '.success' <<< "$update_response" &>/dev/null; then
                ((errors++))
            fi
        fi
    done < <(jq -c '.result[]' <<< "$response")

    # Handle errors
    if (( errors )); then
        handle_error "DNS update completed with $errors errors"
    else
        log INFO "DNS update completed successfully"
    fi
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------
backup_wizard() {
    init_system    
    
    log INFO "Starting Backup Wizard operations"
    
    # Run backups in parallel
    run_full_system_backup &
    run_plex_backup &
    wait
    
    # Run maintenance tasks in parallel
    run_backblaze_backup &
    deploy_user_scripts &
    update_dns_records &
    wait
    
    log INFO "All operations completed successfully"
}

# ------------------------------------------------------------------------------
# SCRIPT ENTRY POINT
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # Load environment variables (if any)
    source ~/.backup-wizard.env 2>/dev/null || true
    
    # Handle dry-run mode
    case "${1:-}" in
        --dry-run)
            log INFO "Dry run mode activated"
            CONFIG[LOG_FILE]="/dev/null"
            set -n
            ;;
        *) ;;
    esac
    
    # Execute the backup wizard
    backup_wizard
    exit 0
fi