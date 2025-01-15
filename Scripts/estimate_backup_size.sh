#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
SOURCE="/"
LOG_FILE="/var/log/backup-size-estimation.log"

# Exclusions
EXCLUDES=(
    "/proc/*"
    "/sys/*"
    "/dev/*"
    "/run/*"
    "/tmp/*"
    "/mnt/*"
    "/media/*"
    "/swapfile"
    "/lost+found"
    "/var/tmp/*"
    "/var/cache/*"
    "/var/log/*"
    "/var/lib/lxcfs/*"
    "/var/lib/docker/*"
    "/root/.cache/*"
    "/home/*/.cache/*"
    "*.iso"
    "*.tmp"
)

# Create exclusion string for du
EXCLUDES_ARGS=()
for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
done

# --------------------------------------
# FUNCTIONS
# --------------------------------------

estimate_backup_size() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Estimating backup size for $SOURCE..." | tee -a "$LOG_FILE"

    # Build the `du` command with exclusions
    du_command=(du -sh "${SOURCE}")
    for EXCLUDE in "${EXCLUDES[@]}"; do
        du_command+=(--exclude="$EXCLUDE")
    done

    # Run the `du` command
    SIZE=$("${du_command[@]}" | awk '{print $1}')
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Estimated backup size: $SIZE" | tee -a "$LOG_FILE"
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

echo "--------------------------------------" | tee -a "$LOG_FILE"
estimate_backup_size
echo "--------------------------------------" | tee -a "$LOG_FILE"

exit 0
