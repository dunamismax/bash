#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Exit on error, on unset variables, and if any command in a pipeline fails
set -euo pipefail

# Variables
DOCKER_COMPOSE_DIR="/home/sawyer/docker_compose"
LOG_FILE="/var/log/docker-compose-up.log"

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to log messages with a timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Function to handle errors
handle_error() {
    log "An error occurred while bringing up the Docker containers. Check the log for details."
    exit 1
}

# Trap errors and execute handle_error
trap 'handle_error' ERR

# Function to bring up Docker containers
bring_up_containers() {
    cd "$DOCKER_COMPOSE_DIR"
    log "Running docker-compose up -d in $DOCKER_COMPOSE_DIR ..."
    docker-compose up -d >> "$LOG_FILE" 2>&1
    log "Docker containers started successfully."
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

# Ensure the log file exists and has the right permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting Docker Compose Up Script"

bring_up_containers

log "Script completed successfully on $(date)."
log "--------------------------------------"

exit 0
