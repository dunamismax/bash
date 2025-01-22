#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
BACKUP_SOURCE="/mnt/media/WD_BLACK/BACKUP/"
BACKUP_DEST="Backblaze:sawyer-backups"
LOG_FILE="/var/log/backblaze-b2-backup.log"
RCLONE_CONFIG="/home/sawyer/.config/rclone/rclone.conf"
RETENTION_DAYS=30

# --------------------------------------
# PRE-CHECKS & VALIDATIONS
# --------------------------------------

# Check if required commands exist
for cmd in rclone tee; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: Required command '$cmd' is not installed." >&2
        exit 1
    fi
done

# Check if BACKUP_SOURCE directory exists
if [ ! -d "$BACKUP_SOURCE" ]; then
    echo "Error: Backup source directory '$BACKUP_SOURCE' does not exist." >&2
    exit 1
fi

# Validate rclone configuration file existence
if [ ! -f "$RCLONE_CONFIG" ]; then
    echo "Error: rclone config file '$RCLONE_CONFIG' not found." >&2
    exit 1
fi

# Ensure the log file exists and has appropriate permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Redirect all output (stdout and stderr) to both console and log file for consistency
exec > >(tee -a "$LOG_FILE") 2>&1

# --------------------------------------
# FUNCTIONS
# --------------------------------------

log() {
    # Print timestamped messages
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

upload_backup() {
    log "Starting direct upload of $BACKUP_SOURCE to Backblaze B2: $BACKUP_DEST"
    # Upload using rclone with verbose output appended to LOG_FILE
    if rclone --config "$RCLONE_CONFIG" copy "$BACKUP_SOURCE" "$BACKUP_DEST" -vv; then
        log "Backup uploaded successfully."
    else
        log "Error: Failed to upload backup."
        return 1
    fi
}

cleanup_backups() {
    log "Removing old backups (older than ${RETENTION_DAYS} days) from Backblaze B2: $BACKUP_DEST"
    # Delete old backups using rclone
    if rclone --config "$RCLONE_CONFIG" delete "$BACKUP_DEST" --min-age "${RETENTION_DAYS}d" -vv; then
        log "Old backups removed successfully."
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
log "Starting Backblaze B2 Direct Upload Backup Script"

upload_backup
cleanup_backups

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
