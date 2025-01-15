#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
SOURCE="/"
DESTINATION="/mnt/WD_BLACK/BACKUP/ubuntu-backups"
LOG_FILE="/var/log/ubuntu-backup.log"
RETENTION_DAYS=7
DATE=$(date +"%Y-%m-%d")
BACKUP_NAME="backup-$DATE.tar.gz"

# Exclusions
EXCLUDES=(
    "/proc/*"         # Kernel and process-related virtual filesystem
    "/sys/*"          # Kernel-related virtual filesystem
    "/dev/*"          # Device files
    "/run/*"          # Runtime state files
    "/tmp/*"          # Temporary files
    "/mnt/*"          # Mounted filesystems
    "/media/*"        # Removable media
    "/swapfile"       # Swap file
    "/lost+found"     # Directory for recovered files after filesystem checks
    "/var/tmp/*"      # Temporary files that persist across reboots
    "/var/cache/*"    # Cached data (e.g., package downloads)
    "/var/log/*"      # Log files (consider excluding or trimming logs for sensitive data)
    "/var/lib/lxcfs/*" # LXCFS-related files (if using containers)
    "/var/lib/docker/*" # Docker runtime files (if Docker is installed)
    "/root/.cache/*"  # Root user cache files
    "/home/*/.cache/*" # User-specific cache files
    "*.iso"           # ISO files (large files often unnecessary in backups)
    "*.tmp"           # Temporary files
)

# Create exclusion string for tar
EXCLUDES_ARGS=()
for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
done

# --------------------------------------
# FUNCTIONS
# --------------------------------------

log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

perform_backup() {
    log "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"
    mkdir -p "$DESTINATION"

    # Compress and stream directly to the destination
    tar -I pigz -cf "$DESTINATION/$BACKUP_NAME" "${EXCLUDES_ARGS[@]}" -C / . >> "$LOG_FILE" 2>&1

    log "Backup and compression completed: $DESTINATION/$BACKUP_NAME"
}

cleanup_backups() {
    log "Removing old backups from $DESTINATION older than $RETENTION_DAYS days"
    find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -exec rm -f {} \; >> "$LOG_FILE" 2>&1
    log "Old backups removed."
}

handle_error() {
    log "An error occurred during the backup process. Check the log for details."
    exit 1
}

trap 'handle_error' ERR

# --------------------------------------
# SCRIPT START
# --------------------------------------

touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting Ubuntu Backup Script"

perform_backup
cleanup_backups

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
