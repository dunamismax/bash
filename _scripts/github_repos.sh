#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

set -euo pipefail

# Variables
GITHUB_DIR="$HOME/github"
HUGO_PUBLIC_DIR="/home/sawyer/github/hugo/dunamismax.com/public"
HUGO_DIR="/home/sawyer/github/hugo"
SAWYER_HOME="/home/sawyer"

# Log function for timestamped messages
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

# --------------------------------------
# FUNCTIONS
# --------------------------------------

update_repositories() {
    log "Creating directory $GITHUB_DIR if it doesn't exist"
    mkdir -p "$GITHUB_DIR"

    log "Changing to directory $GITHUB_DIR"
    cd "$GITHUB_DIR"

    # Clone repositories if they do not already exist
    repos=(
        "https://github.com/dunamismax/bash.git"
        "https://github.com/dunamismax/c.git"
        "https://github.com/dunamismax/religion.git"
        "https://github.com/dunamismax/windows.git"
        "https://github.com/dunamismax/hugo.git"
        "https://github.com/dunamismax/python.git"
    )

    for repo in "${repos[@]}"; do
        repo_name=$(basename "$repo" .git)
        if [ ! -d "$repo_name" ]; then
            log "Cloning repository $repo"
            git clone "$repo"
        else
            log "Repository $repo_name already exists, skipping clone"
        fi
    done

    # Set permissions and ownership for the Hugo directory
    log "Setting ownership and permissions for Hugo public directory"
    sudo chown -R www-data:www-data "$HUGO_PUBLIC_DIR"
    sudo chmod -R 755 "$HUGO_PUBLIC_DIR"

    log "Setting ownership and permissions for Hugo directory"
    sudo chown -R caddy:caddy "$HUGO_DIR"
    sudo chmod o+rx "$SAWYER_HOME"
    sudo chmod o+rx "$GITHUB_DIR"
    sudo chmod o+rx "$HUGO_DIR"
    sudo chmod o+rx "/home/sawyer/github/hugo/dunamismax.com"

    log "Update repositories and permissions completed."
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

update_repositories
