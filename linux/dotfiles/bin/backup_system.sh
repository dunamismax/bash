#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
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

# --------------------------------------
# PRE-CHECKS & VALIDATIONS
# --------------------------------------

# Check if required commands exist
for cmd in tar pigz find tee df mountpoint; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: Required command '$cmd' is not installed." >&2
        exit 1
    fi
done

# Create destination directory before checking mount
mkdir -p "$DESTINATION"

# Check for the nearest mounted parent directory of DESTINATION
mounted_parent=$(df --output=target "$DESTINATION" | tail -1)
if [ -z "$mounted_parent" ] || ! mountpoint -q "$mounted_parent"; then
    echo "Error: Destination mount point for '$DESTINATION' is not available." >&2
    exit 1
fi

# Ensure log file exists and has proper permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Redirect all output (stdout and stderr) to both console and log file
exec > >(tee -a "$LOG_FILE") 2>&1

# --------------------------------------
# FUNCTIONS
# --------------------------------------

log() {
    # Print timestamped messages.
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

perform_backup() {
    log "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"

    # Compress and stream directly to the destination using pigz for speed, applying exclusions.
    if tar -I pigz --one-file-system -cf "$DESTINATION/$BACKUP_NAME" \
        "${EXCLUDES_ARGS[@]}" -C / .; then
        log "Backup and compression completed: $DESTINATION/$BACKUP_NAME"
    else
        log "Error: Backup process failed."
        return 1
    fi
}

cleanup_backups() {
    log "Removing old backups from $DESTINATION older than $RETENTION_DAYS days"
    # Find and remove files older than RETENTION_DAYS
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -exec rm -f {} \;; then
        log "Old backups removed."
    else
        log "Warning: Failed to remove some old backups."
    fi
}

handle_error() {
    log "An error occurred during the backup process. Check the log for details."
    exit 1
}

trap 'handle_error' ERR

# --------------------------------------
# SCRIPT START
# --------------------------------------

log "--------------------------------------"
log "Starting Ubuntu Backup Script"

perform_backup
cleanup_backups

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
