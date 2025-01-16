#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: example_script.sh
# Description: [Brief description of what the script does]
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./example_script.sh [options]
#   Options:
#     -h, --help    Display this help message and exit
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'log ERROR "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/example_script.log"
VERBOSE=2
# Define other global variables and arrays here
# Example: PACKAGES=(git curl wget)

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Define color codes
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'  # No Color

    # Validate log level and set color
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            ;;
        DEBUG)
            local color="${BLUE}"
            ;;
        *)
            local color="${NC}"
            level="INFO"
            ;;
    esac

    # Ensure the log file exists and is writable
    if [[ -z "${LOG_FILE:-}" ]]; then
        LOG_FILE="/var/log/example_script.log"
    fi
    if [[ ! -e "$LOG_FILE" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
    fi

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"

    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"

    # Output to console based on verbosity
    if [[ "$VERBOSE" -ge 2 ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    elif [[ "$VERBOSE" -ge 1 && "$level" == "ERROR" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
        log ERROR "This script must be run as root."
        exit 1
    fi
}

usage() {
    grep '^#' "$0" | sed 's/^#//'
    exit 0
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
    log INFO "Starting function_one..."
    # TODO: Add function_one logic here
    log INFO "Completed function_one."
}

function_two() {
    log INFO "Starting function_two..."
    # TODO: Add function_two logic here
    log INFO "Completed function_two."
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    # Parse input arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage
                ;;
            *) 
                log WARN "Unknown option: $1"
                usage
                ;;
        esac
    done

    check_root
    log INFO "Script execution started."

    # Call your main functions in order
    function_one
    function_two

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi