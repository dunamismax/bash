#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Exit immediately if a command exits with a non-zero status,
# if any variable is unset, and if any command in a pipeline fails
set -euo pipefail

# Variables
SOURCE="/"
DESTINATION="/mnt/WD_BLACK/BACKUP/ubuntu-backups"
LOG_FILE="/var/log/ubuntu-backup.log"
RETENTION_DAYS=7

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

# Create a formatted exclusions string for rsync
EXCLUDES_STRING=""
for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_STRING+="--exclude=${EXCLUDE} "
done

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to log messages with timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Function to perform the backup
perform_backup() {
    local DATE=$(date +"%Y-%m-%d")
    local BACKUP_DIR="$DESTINATION/$DATE"

    log "Starting backup to $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"

    rsync -aAXv --delete $EXCLUDES_STRING "$SOURCE" "$BACKUP_DIR" >> "$LOG_FILE" 2>&1

    log "Backup completed to $BACKUP_DIR"
}

# Function to remove old backups
cleanup_backups() {
    log "Removing backups older than $RETENTION_DAYS days from $DESTINATION"
    find "$DESTINATION" -mindepth 1 -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \; >> "$LOG_FILE" 2>&1
    log "Old backups removed successfully."
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
log "Starting Ubuntu Backup Script"

# Step 1: Perform the backup
perform_backup

# Step 2: Remove old backups
cleanup_backups

log "Backup and cleanup completed successfully on $(date)."
log "--------------------------------------"

exit 0
