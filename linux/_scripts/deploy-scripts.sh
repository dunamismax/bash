#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: deploy-scripts.sh
# Description: Deploys user scripts from a source directory to a target directory.
#              Ensures proper ownership, performs a dry-run, and sets executable
#              permissions.
#
# Usage:
#   sudo ./deploy-scripts.sh
#
# Requirements:
#   - Root privileges
#   - rsync, find, and core utilities
#
# Logs:
#   /var/log/deploy-scripts.log
#
# Author: Your Name | License: MIT
# Version: 1.0.1
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# For more information, see:
#   https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"

    log ERROR "$error_message"
    log DEBUG "Stack trace (most recent call last):"
    # Print a brief stack trace for debugging
    local i
    for (( i=${#FUNCNAME[@]}-1 ; i>1 ; i-- )); do
        log DEBUG "  [${BASH_SOURCE[$i]}:${BASH_LINENO[$((i-1))]}] in ${FUNCNAME[$i]}"
    done

    exit "$exit_code"
}

trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES (CONFIGURATION)
# ------------------------------------------------------------------------------
declare -A CONFIG=(
    # Paths
    [SCRIPT_SOURCE]="/home/sawyer/github/bash/linux/_scripts" # Source directory
    [SCRIPT_TARGET]="/home/sawyer/bin"                        # Deployment directory

    # Logging
    [LOG_FILE]="/var/log/deploy-scripts.log"
)

# ------------------------------------------------------------------------------
# COLOR CONSTANTS (OPTIONAL FOR LOGGING)
# ------------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage:
    #   log [LEVEL] "Message text"
    #
    # Example:
    #   log INFO "Beginning deployment..."
    # ----------------------------------------------------------------------------

    local level="${1:-INFO}"
    shift
    local message="$*"

    # Convert level to uppercase
    local upper_level="${level^^}"

    # Get timestamp
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"

    # Determine color based on level
    local color_code="$NC"
    case "$upper_level" in
        INFO)
            color_code="$GREEN"
            ;;
        WARN|WARNING)
            upper_level="WARN"
            color_code="$YELLOW"
            ;;
        ERROR)
            color_code="$RED"
            ;;
        DEBUG)
            color_code="$BLUE"
            ;;
    esac

    # Construct log entry
    local log_entry="[$timestamp] [$upper_level] $message"

    # Always write uncolored log entry to file
    echo "$log_entry" >> "${CONFIG[LOG_FILE]}"

    # Write to console (stderr) with color if terminal is interactive
    if [[ -t 2 ]]; then
        printf "%b%s%b\n" "$color_code" "$log_entry" "$NC" >&2
    else
        echo "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# DEPLOYMENT FUNCTIONS
# ------------------------------------------------------------------------------
deploy_user_scripts() {
    log INFO "Deploying system scripts..."

    # 1. Check ownership of source directory
    local source_owner
    source_owner="$(stat -c %U "${CONFIG[SCRIPT_SOURCE]}")" || handle_error "Failed to stat source directory"
    if [[ "$source_owner" != "sawyer" ]]; then
        handle_error "Invalid script source ownership: ${CONFIG[SCRIPT_SOURCE]} (Owner: $source_owner)"
    fi

    # 2. Dry-run deployment
    log INFO "Running dry-run for script deployment..."
    if ! rsync --dry-run -ah --delete "${CONFIG[SCRIPT_SOURCE]}/" "${CONFIG[SCRIPT_TARGET]}"; then
        handle_error "Dry-run failed for script deployment"
    fi

    # 3. Actual deployment
    log INFO "Deploying scripts from '${CONFIG[SCRIPT_SOURCE]}' to '${CONFIG[SCRIPT_TARGET]}'..."
    if ! rsync -ah --delete "${CONFIG[SCRIPT_SOURCE]}/" "${CONFIG[SCRIPT_TARGET]}"; then
        handle_error "Script deployment failed"
    fi

    # 4. Set executable permissions
    log INFO "Setting executable permissions on deployed scripts..."
    if ! find "${CONFIG[SCRIPT_TARGET]}" -type f -exec chmod 755 {} \;; then
        handle_error "Failed to update script permissions"
    fi

    log INFO "Script deployment completed successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Set secure permissions on log file
    umask 077
    touch "${CONFIG[LOG_FILE]}" || handle_error "Failed to create log file: ${CONFIG[LOG_FILE]}"
    chmod 640 "${CONFIG[LOG_FILE]}"

    log INFO "Starting script deployment process..."
    deploy_user_scripts
    log INFO "Script deployment process completed."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    exit 0
fi
