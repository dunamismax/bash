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

# Exclusions
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

# --------------------------------------
# FUNCTIONS
# --------------------------------------

log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

perform_backup() {
    mkdir -p "$DESTINATION"

    # Implement sequential naming scheme
    BASE_NAME="backup-$DATE"
    EXT=".tar.gz"
    COUNTER=0
    while [[ -f "$DESTINATION/${BASE_NAME}_${COUNTER}${EXT}" ]]; do
        ((COUNTER++))
    done
    BACKUP_NAME="${BASE_NAME}_${COUNTER}${EXT}"

    log "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"

    # Compress and stream directly to the destination
    tar -I pigz --one-file-system -cf "$DESTINATION/$BACKUP_NAME" "${EXCLUDES_ARGS[@]}" -C / . >> "$LOG_FILE" 2>&1

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
