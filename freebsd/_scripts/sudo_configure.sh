#!/usr/local/bin/bash
#
# FreeBSD Sudo Setup Script
#
# This script installs sudo via pkg, ensures that it is available, and
# configures the sudoers file to grant the user "sawyer" full sudo privileges.
#
# Usage: Run as root.
#
set -Eeuo pipefail
IFS=$'\n\t'

# Simple logging function
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$timestamp] [$level] $message"
}

# Ensure the script is run as root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log ERROR "This script must be run as root. Exiting."
        exit 1
    fi
}

# Install sudo if it is not already installed
install_sudo() {
    if ! command -v sudo &>/dev/null; then
        log INFO "sudo not found. Installing sudo..."
        pkg update && pkg install sudo || {
            log ERROR "Failed to install sudo via pkg."
            exit 1
        }
        log INFO "sudo installed successfully."
    else
        log INFO "sudo is already installed."
    fi
}

# Backup the current sudoers file
backup_sudoers() {
    local sudoers_file="/usr/local/etc/sudoers"
    if [ -f "$sudoers_file" ]; then
        local backup="/usr/local/etc/sudoers.backup.$(date +%Y%m%d%H%M%S)"
        cp "$sudoers_file" "$backup"
        log INFO "Backed up existing sudoers file to $backup."
    else
        log WARN "sudoers file not found at /usr/local/etc/sudoers. A new one will be created."
    fi
}

# Configure the sudoers file to grant user "sawyer" full privileges
configure_sudoers() {
    local sudoers_file="/usr/local/etc/sudoers"
    local entry="sawyer ALL=(ALL) ALL"
    
    # Use visudo to check the syntax after modification
    if grep -q "^${entry}$" "$sudoers_file" 2>/dev/null; then
        log INFO "User 'sawyer' is already configured in sudoers."
    else
        log INFO "Adding 'sawyer' to the sudoers file."
        echo "$entry" >> "$sudoers_file"
        
        # Validate the syntax using visudo in check mode
        if visudo -c -f "$sudoers_file" &>/dev/null; then
            log INFO "sudoers file syntax is valid."
        else
            log ERROR "sudoers file syntax error. Restoring backup and exiting."
            backup_file=$(ls -t /usr/local/etc/sudoers.backup.* 2>/dev/null | head -n1)
            if [ -n "$backup_file" ]; then
                cp "$backup_file" "$sudoers_file"
                log INFO "Restored sudoers from backup $backup_file."
            fi
            exit 1
        fi
    fi
}

main() {
    check_root
    install_sudo
    backup_sudoers
    configure_sudoers
    log INFO "Sudo installation and configuration complete."
}

main "$@"