#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: example_script.sh
# Description: [Brief description of what the script does]
# Author: dunamismax | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./example_script.sh [options]
#
# Options:
#   -h, --help    Show this help message and exit.
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."
    
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}." >&2
    exit "$exit_code"
}

trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/example_script.log"  # Path to the log file

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
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

    local color=""
    case "${level^^}" in
        INFO)
            color="${GREEN}"
            ;;
        WARN|WARNING)
            color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            color="${RED}"
            ;;
        DEBUG)
            color="${BLUE}"
            ;;
        *)
            color="${NC}"
            level="INFO"
            ;;
    esac

    local log_entry="[$timestamp] [$level] $message"
    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"
    # Output to console (stderr)
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

# ------------------------------------------------------------------------------
# USAGE FUNCTION
# ------------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: sudo $0 [options]

Options:
  -h, --help    Show this help message and exit.

Description:
  [Insert a brief description of what the script does.]

EOF
    exit 0
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
    log INFO "--------------------------------------"
    log INFO "Starting function_one..."
    # TODO: Add function_one logic here
    log INFO "Completed function_one."
    log INFO "--------------------------------------"
}

function_two() {
    log INFO "--------------------------------------"
    log INFO "Starting function_two..."
    # TODO: Add function_two logic here
    log INFO "Completed function_two."
    log INFO "--------------------------------------"
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
        shift
    done

    # Ensure the script is run as root
    check_root

    # Ensure the log directory exists and is writable
    local LOG_DIR
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE"  # Restrict log file access

    log INFO "Script execution started."

    # Execute main functions in order
    function_one
    function_two

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi