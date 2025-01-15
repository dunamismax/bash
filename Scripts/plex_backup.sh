#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
SOURCE="/var/lib/plexmediaserver/"
DESTINATION="/mnt/WD_BLACK/BACKUP/plex-backups"
LOG_FILE="/var/log/plex-backup.log"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="plex-backup-$TIMESTAMP.tar.gz"

# --------------------------------------
# PRE-CHECKS & VALIDATIONS
# --------------------------------------

# Check if required commands exist
for cmd in tar pigz find tee; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: Required command '$cmd' is not installed." >&2
        exit 1
    fi
done

# Check if SOURCE directory exists
if [ ! -d "$SOURCE" ]; then
    echo "Error: Source directory '$SOURCE' does not exist." >&2
    exit 1
fi

# Check if DESTINATION mount is available
if ! mountpoint -q "$(dirname "$DESTINATION")"; then
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
    # Print timestamped messages. They are automatically logged due to global redirection.
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

perform_backup() {
    mkdir -p "$DESTINATION"

    log "Starting on-the-fly backup and compression to $DESTINATION/$BACKUP_NAME"

    # Compress and stream directly to the destination using pigz for speed
    if tar -I pigz --one-file-system -cf "$DESTINATION/$BACKUP_NAME" -C "$SOURCE" .; then
        log "Backup and compression completed: $DESTINATION/$BACKUP_NAME"
    else
        log "Error: Backup process failed."
        return 1
    fi
}

cleanup_backups() {
    log "Removing backups older than $RETENTION_DAYS days from $DESTINATION"
    # Use find to locate and remove old backups
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -exec rm -f {} \;; then
        log "Old backups removed."
    else
        log "Warning: Failed to remove some old backups."
    fi
}

handle_error() {
    log "An unexpected error occurred. Exiting script."
    exit 1
}

# Trap errors and termination signals
trap handle_error ERR
trap 'log "Script terminated prematurely by signal."; exit 1' SIGINT SIGTERM

# --------------------------------------
# SCRIPT START
# --------------------------------------

log "--------------------------------------"
log "Starting Plex Backup Script"

if perform_backup; then
    cleanup_backups
    log "Backup and cleanup completed successfully on $(date)."
else
    log "Backup failed. Cleanup skipped."
fi

log "--------------------------------------"
exit 0
