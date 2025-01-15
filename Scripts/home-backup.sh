#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Exit immediately if a command exits with a non-zero status,
# if any variable is unset, and if any command in a pipeline fails
set -euo pipefail

# Variables
export RESTIC_REPOSITORY="/mnt/media/WD_BLACK/BACKUPS/ubuntu-home-backups"
export RESTIC_PASSWORD_FILE="/root/.restic-password"
SOURCE_DIR="/home/sawyer"
LOG_FILE="/var/log/home-backup.log"
RETENTION_DAYS=30
SNAPSHOT_TAG="Home-$(date +"%Y-%m-%d")"

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to log messages with timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Function to perform the backup
perform_backup() {
    log "Starting Restic backup for: $SOURCE_DIR"

    # Check if Restic repository is initialized
    if ! restic snapshots &>/dev/null; then
        log "Restic repository is not initialized. Initializing now..."
        restic init
        log "Restic repository initialized."
    fi

    # Perform the backup with snapshot tagging
    restic backup "$SOURCE_DIR" --tag "$SNAPSHOT_TAG" --verbose >> "$LOG_FILE" 2>&1
    log "Backup completed successfully."
}

# Function to prune old snapshots
prune_snapshots() {
    log "Pruning snapshots older than $RETENTION_DAYS days."

    restic forget --prune --keep-within "${RETENTION_DAYS}d" --tag "$SNAPSHOT_TAG" >> "$LOG_FILE" 2>&1
    log "Prune operation completed successfully."
}

# Function to handle errors
handle_error() {
    log "An error occurred during the backup process. Check the log for details."
    exit 1
}

# Trap errors and execute handle_error
trap 'handle_error' ERR

# --------------------------------------
# SCRIPT START
# --------------------------------------

# Ensure the log file exists and has appropriate permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting Home Restic Backup Script"

# Step 1: Perform the backup
perform_backup

# Step 2: Prune old snapshots
prune_snapshots

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
