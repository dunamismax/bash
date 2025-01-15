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
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="backup-$TIMESTAMP.tar.gz"

# Redirect all output (stdout and stderr) to both console and log file
exec > >(tee -a "$LOG_FILE") 2>&1

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
    # Print timestamped messages. They are automatically logged due to global redirection.
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

perform_backup() {
    mkdir -p "$DESTINATION"

    log "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"

    # Compress and stream directly to the destination. Socket warnings will be logged.
    tar -I pigz --one-file-system -cf "$DESTINATION/$BACKUP_NAME" \
        "${EXCLUDES_ARGS[@]}" -C / .

    log "Backup and compression completed: $DESTINATION/$BACKUP_NAME"
}

cleanup_backups() {
    log "Removing old backups from $DESTINATION older than $RETENTION_DAYS days"
    find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -exec rm -f {} \;
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

# Ensure log file exists and has proper permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting Ubuntu Backup Script"

perform_backup
cleanup_backups

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
