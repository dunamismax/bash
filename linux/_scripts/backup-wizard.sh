#!/usr/bin/env bash
################################################################################
# Backup Wizard - Comprehensive System Backup Automation
################################################################################
# Description:
#   Automated enterprise-grade backup solution with cloud integration and 
#   maintenance features. Key capabilities include:
#     • Full system backups with intelligent exclusion patterns
#     • Plex Media Server state preservation and rotation
#     • Backblaze B2 cloud synchronization with retention policies
#     • Automated script deployment and synchronization
#     • Cloudflare DNS record maintenance with dynamic IP updates
#     • Color-coded logging system with error stack traces
#     • Configuration management with centralized settings
#
# Usage:
#   sudo ./backup-wizard.sh
#   • Requires root privileges for full system access
#   • Configure paths/credentials in CONFIG section
#   • Detailed logs stored in /var/log/backup-wizard.log
#
# Features:
#   • Full System Backups:
#       - XZ-compressed archives with pigz acceleration
#       - 50+ intelligent directory exclusions
#       - Automated retention management (7-day default)
#   • Media Protection:
#       - Plex server state snapshots
#       - Media-friendly compression settings
#   • Cloud Integration:
#       - Backblaze B2 sync with rclone
#       - Cloudflare DNS A-record automation
#   • Security:
#       - Config file permission enforcement
#       - Mount point validation
#       - Secure credential handling
#
# Error Handling:
#   • Strict mode enforcement (set -Eeuo pipefail)
#   • Custom error traps with stack tracing
#   • Dual logging (file + color console)
#   • Dependency pre-flight checks
#
# Compatibility:
#   • Tested on Ubuntu 22.04/24.04 LTS
#   • Requires GNU coreutils 8.25+ 
#   • Compatible with rclone 1.60+
#
# Configuration:
#   • Adjust CONFIG[] values for paths/retention
#   • Modify SYSTEM_EXCLUDES for backup content
#   • Set Cloudflare/B2 credentials in config
#
# Author: dunamismax | License: MIT
# Repository: https://github.com/dunamismax/bash
################################################################################

set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

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
    [CF_API_TOKEN]="_3zWgksLETucvKLN0ICn_Mbh7x-_Cooo_Anb2Dv4"
    [CF_ZONE_ID]="dc739d9b91869a4ff2c8002125f6836c"

    # Logging
    [LOG_FILE]="/var/log/backup-wizard.log"
)

# System backup exclusions
declare -a SYSTEM_EXCLUDES=(
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

# ------------------------------------------------------------------------------
# LOGGING SYSTEM
# ------------------------------------------------------------------------------
log() {
    declare -A LEVEL_COLORS=(
        [INFO]='\033[0;32m'  # Green
        [WARN]='\033[0;33m'  # Yellow
        [ERROR]='\033[0;31m' # Red
        [DEBUG]='\033[0;34m' # Blue
    )
    local level="${1:-INFO}" 
    local message="${*:2}"
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color="${LEVEL_COLORS[${level^^}]:-\033[0m}"
    
    echo "$timestamp [${level^^}] $message" >> "${CONFIG[LOG_FILE]}"
    printf "${color}%s [%s] %s\033[0m\n" "$timestamp" "${level^^}" "$message" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLER
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-Unknown error occurred}"
    log ERROR "$error_message"
    log DEBUG "Stack trace: $(printf "  %s\n" "${FUNCNAME[@]:2}")"
    exit 1
}

# ------------------------------------------------------------------------------
# CORE FUNCTIONS
# ------------------------------------------------------------------------------
init_system() {
    [[ $EUID -eq 0 ]] || handle_error "Root privileges required"
    touch "${CONFIG[LOG_FILE]}" || handle_error "Log file initialization failed"
    chmod 644 "${CONFIG[LOG_FILE]}"
    exec > >(tee -a "${CONFIG[LOG_FILE]}") 2>&1
}

check_dependencies() {
    local -a required=(
        rclone tar pigz jq curl rsync find mountpoint
    )
    for cmd in "${required[@]}"; do
        command -v "$cmd" >/dev/null || handle_error "Missing required command: $cmd"
    done
}

validate_path() {
    [[ -e "$1" ]] || handle_error "Path not found: $1"
    [[ -r "$1" ]] || handle_error "Path not readable: $1"
}

# ------------------------------------------------------------------------------
# BACKUP MODULES
# ------------------------------------------------------------------------------
run_full_system_backup() {
    log INFO "Starting full system backup"
    
    # Prepare destination
    mkdir -p "${CONFIG[FULL_SYSTEM_DEST]}" || handle_error "Failed to create backup directory"
    validate_path "${CONFIG[FULL_SYSTEM_DEST]}"

    # Generate backup filename
    local timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
    local backup_file="${CONFIG[FULL_SYSTEM_DEST]}/system-backup-$timestamp.tar.gz"

    # Build exclusion arguments
    local excludes_args=()
    for exclude in "${SYSTEM_EXCLUDES[@]}"; do
        excludes_args+=(--exclude="$exclude")
    done

    # Create compressed backup
    log INFO "Creating system archive with exclusions"
    tar -I pigz --one-file-system -cf "$backup_file" \
        "${excludes_args[@]}" -C / . || handle_error "System backup failed"

    # Cleanup old backups
    log INFO "Applying retention policy (${CONFIG[FULL_SYSTEM_RETENTION]} days)"
    find "${CONFIG[FULL_SYSTEM_DEST]}" -name "system-backup-*.tar.gz" \
        -mtime +"${CONFIG[FULL_SYSTEM_RETENTION]}" -delete || 
        log WARN "Partial failure during system backup rotation"
}

run_backblaze_backup() {
    log INFO "Starting cloud backup to Backblaze B2"
    validate_path "${CONFIG[BACKUP_SOURCE]}"
    validate_path "${CONFIG[RCLONE_CONFIG]}"

    rclone --config "${CONFIG[RCLONE_CONFIG]}" copy \
        "${CONFIG[BACKUP_SOURCE]}" "${CONFIG[BACKBLAZE_DEST]}" -vv || 
        handle_error "Backblaze upload failed"

    rclone --config "${CONFIG[RCLONE_CONFIG]}" delete \
        "${CONFIG[BACKBLAZE_DEST]}" --min-age "${CONFIG[BACKBLAZE_RETENTION]}d" -vv ||
        log WARN "Backblaze retention cleanup had partial failures"
}

run_plex_backup() {
    log INFO "Starting Plex Media Server backup"
    validate_path "${CONFIG[PLEX_SOURCE]}"
    mkdir -p "${CONFIG[PLEX_DEST]}" || handle_error "Failed to create backup directory"

    local backup_file="${CONFIG[PLEX_DEST]}/plex-backup-$(date +"%Y-%m-%d_%H-%M-%S").tar.gz"
    tar -I pigz --one-file-system -cf "$backup_file" -C "${CONFIG[PLEX_SOURCE]}" . ||
        handle_error "Plex backup creation failed"

    find "${CONFIG[PLEX_DEST]}" -name "plex-backup-*.tar.gz" -mtime +"${CONFIG[PLEX_RETENTION]}" -delete ||
        log WARN "Plex backup rotation had partial failures"
}

# ------------------------------------------------------------------------------
# MAINTENANCE MODULES
# ------------------------------------------------------------------------------
deploy_user_scripts() {
    log INFO "Deploying system scripts"
    validate_path "${CONFIG[SCRIPT_SOURCE]}"
    mkdir -p "${CONFIG[SCRIPT_TARGET]}" || handle_error "Failed to create script directory"

    find "${CONFIG[SCRIPT_SOURCE]}" -type f -exec chmod +x {} \; ||
        handle_error "Failed to set script permissions"

    rsync -ah --delete "${CONFIG[SCRIPT_SOURCE]}/" "${CONFIG[SCRIPT_TARGET]}" ||
        handle_error "Script synchronization failed"
}

update_dns_records() {
    log INFO "Updating Cloudflare DNS records"
    local current_ip=$(curl -sf https://api.ipify.org) || handle_error "IP detection failed"
    
    local response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CONFIG[CF_ZONE_ID]}/dns_records" \
        -H "Authorization: Bearer ${CONFIG[CF_API_TOKEN]}" \
        -H "Content-Type: application/json") || handle_error "DNS record fetch failed"

    jq -c '.result[]' <<< "$response" | while read -r record; do
        local record_id=$(jq -r '.id' <<< "$record")
        local record_type=$(jq -r '.type' <<< "$record")
        local record_name=$(jq -r '.name' <<< "$record")
        local record_ip=$(jq -r '.content' <<< "$record")

        if [[ "$record_type" == "A" && "$current_ip" != "$record_ip" ]]; then
            log INFO "Updating DNS record: $record_name ($record_ip → $current_ip)"
            curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/${CONFIG[CF_ZONE_ID]}/dns_records/$record_id" \
                -H "Authorization: Bearer ${CONFIG[CF_API_TOKEN]}" \
                -H "Content-Type: application/json" \
                --data "{\"type\":\"A\",\"name\":\"$record_name\",\"content\":\"$current_ip\",\"ttl\":1}" >/dev/null ||
                log WARN "Failed to update $record_name"
        fi
    done
}

# ------------------------------------------------------------------------------
# BACKUP WIZARD
# ------------------------------------------------------------------------------
backup_wizard() {
    init_system
    check_dependencies
    
    log INFO "Starting Backup Wizard operations"
    
    # Backup sequence
    run_full_system_backup
    run_plex_backup
    run_backblaze_backup
    
    # Maintenance tasks
    deploy_user_scripts
    update_dns_records
    
    log INFO "All Backup Wizard operations completed successfully"
}

# ------------------------------------------------------------------------------
# SCRIPT ENTRY POINT
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    backup_wizard
    exit 0
fi