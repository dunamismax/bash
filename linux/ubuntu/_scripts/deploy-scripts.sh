#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: deploy-scripts.sh
# Description: Deploys user scripts from a source directory to a target directory
#              on Ubuntu Linux. Ensures proper ownership, performs a dry‑run, and
#              sets executable permissions using a Nord‑themed template for robust
#              error handling and logging.
# Author: Your Name | License: MIT | Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   sudo ./deploy-scripts.sh [-d|--debug] [-q|--quiet]
#   sudo ./deploy-scripts.sh -h|--help
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/deploy-scripts.log by default.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & SET IFS
# ------------------------------------------------------------------------------
set -Eeuo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
readonly LOG_FILE="/var/log/deploy-scripts.log"   # Log file path
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"                     # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                                   # When true, suppress console output
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# Deployment‑specific configuration
readonly SCRIPT_SOURCE="/home/sawyer/github/bash/linux/_scripts"  # Source directory for scripts
readonly SCRIPT_TARGET="/home/sawyer/bin"                           # Target deployment directory
readonly EXPECTED_OWNER="sawyer"                                    # Expected owner of source directory

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD0='\033[38;2;46;52;64m'
readonly NORD1='\033[38;2;59;66;82m'
readonly NORD2='\033[38;2;67;76;94m'
readonly NORD3='\033[38;2;76;86;106m'
readonly NORD4='\033[38;2;216;222;233m'
readonly NORD5='\033[38;2;229;233;240m'
readonly NORD6='\033[38;2;236;239;244m'
readonly NORD7='\033[38;2;143;188;187m'
readonly NORD8='\033[38;2;136;192;208m'
readonly NORD9='\033[38;2;129;161;193m'
readonly NORD10='\033[38;2;94;129;172m'
readonly NORD11='\033[38;2;191;97;106m'
readonly NORD12='\033[38;2;208;135;112m'
readonly NORD13='\033[38;2;235;203;139m'
readonly NORD14='\033[38;2;163;190;140m'
readonly NORD15='\033[38;2;180;142;173m'
readonly NC='\033[0m'  # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log [LEVEL] message
# Example: log INFO "Deployment started..."
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    # Only output DEBUG messages if LOG_LEVEL is DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)   color="${NORD14}" ;;  # Greenish
            WARN)   color="${NORD13}" ;;  # Yellowish
            ERROR)  color="${NORD11}" ;;  # Reddish
            DEBUG)  color="${NORD9}"  ;;  # Bluish
            *)      color="$NC"     ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    if [[ "$QUIET_MODE" != true ]]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., deleting temporary files)
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

enable_debug() {
    LOG_LEVEL="DEBUG"
    log DEBUG "Debug mode enabled: Verbose logging activated."
}

enable_quiet_mode() {
    QUIET_MODE=true
    log INFO "Quiet mode enabled: Console output suppressed."
}

show_help() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Description:
  Deploys user scripts from a source directory to a target directory on Ubuntu.
  Ensures proper ownership, performs a dry‑run, and sets executable permissions.
  Uses a Nord‑themed enhanced template for robust error handling and logging.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output.
  -h, --help    Show this help message and exit.

Examples:
  sudo $SCRIPT_NAME --debug
  sudo $SCRIPT_NAME --quiet
  sudo $SCRIPT_NAME -h
EOF
}

# Prints a styled section header using Nord accent colors.
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# ------------------------------------------------------------------------------
# DEPLOYMENT FUNCTION
# ------------------------------------------------------------------------------
deploy_user_scripts() {
    print_section "Deploying User Scripts"
    log INFO "Starting deployment of user scripts..."

    # 1. Check ownership of source directory.
    local source_owner
    source_owner="$(stat -c %U "$SCRIPT_SOURCE")" || handle_error "Failed to stat source directory: $SCRIPT_SOURCE"
    if [[ "$source_owner" != "$EXPECTED_OWNER" ]]; then
        handle_error "Invalid script source ownership for '$SCRIPT_SOURCE' (Owner: $source_owner). Expected: $EXPECTED_OWNER"
    fi

    # 2. Perform a dry‑run deployment.
    log INFO "Performing dry‑run for script deployment..."
    if ! rsync --dry-run -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}"; then
        handle_error "Dry‑run failed for script deployment."
    fi

    # 3. Actual deployment.
    log INFO "Deploying scripts from '$SCRIPT_SOURCE' to '$SCRIPT_TARGET'..."
    if ! rsync -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}"; then
        handle_error "Script deployment failed."
    fi

    # 4. Set executable permissions on deployed scripts.
    log INFO "Setting executable permissions on deployed scripts..."
    if ! find "${SCRIPT_TARGET}" -type f -exec chmod 755 {} \;; then
        handle_error "Failed to update script permissions in '$SCRIPT_TARGET'."
    fi

    log INFO "Script deployment completed successfully."
}

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--debug)
                enable_debug
                ;;
            -q|--quiet)
                enable_quiet_mode
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log WARN "Unknown option: $1"
                ;;
        esac
        shift
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure the log directory exists and secure the log file.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Starting script deployment process..."
    parse_args "$@"
    deploy_user_scripts
    log INFO "Script deployment process completed."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
