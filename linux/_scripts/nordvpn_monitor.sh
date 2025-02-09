#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: nordvpn-monitor.sh
# Description: Real‑time monitor for NordVPN data transfer (received GiB/TiB) using
#              the Nord‑themed enhanced template for robust logging and error handling.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   ./nordvpn-monitor.sh [-d|--debug] [-q|--quiet]
#   ./nordvpn-monitor.sh -h|--help
#
# Notes:
#   - Displays the total data received via NordVPN in real‑time.
#   - Requires NordVPN CLI to be installed and actively connected.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/nordvpn-monitor.log"   # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"              # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                           # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"    # Set to true to disable colored output

# Refresh interval (in seconds)
REFRESH_INTERVAL=1

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9
NORD5='\033[38;2;229;233;240m'   # #E5E9F0
NORD6='\033[38;2;236;239;244m'   # #ECEFF4
NORD7='\033[38;2;143;188;187m'   # #8FBCBB
NORD8='\033[38;2;136;192;208m'   # #88C0D0
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD10='\033[38;2;94;129;172m'   # #5E81AC
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD12='\033[38;2;208;135;112m'  # #D08770
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NORD15='\033[38;2;180;142;173m'  # #B48EAD
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"

    # Only log DEBUG messages when LOG_LEVEL is DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
            *)     color="$NC"     ;;
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
    log INFO "Exiting nordvpn-monitor..."
    # Insert any necessary cleanup tasks here
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR
# Trap SIGINT (Ctrl+C) for a graceful exit
trap 'printf "\n"; exit 0' SIGINT

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
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
  Real‑time monitor for NordVPN data transfer (GiB/TiB) using a Nord‑themed enhanced
  template for robust logging and error handling.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output (logs still written to file).
  -h, --help    Show this help message and exit.

Examples:
  $SCRIPT_NAME --debug
  $SCRIPT_NAME --quiet
  $SCRIPT_NAME -h
EOF
}

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
# FUNCTION: get_received_data
# ------------------------------------------------------------------------------
get_received_data() {
    # Extract the portion of the NordVPN status output that indicates transfer data.
    local transfer_line
    transfer_line="$(nordvpn status | grep -oP 'Transfer:\s+\K.*(?=\s+received)')"

    if [[ "$transfer_line" =~ TiB ]]; then
        local tib_value
        tib_value="$(echo "$transfer_line" | grep -oP '[\d.]+(?=\s*TiB)')"
        echo "${tib_value} TiB"
    elif [[ "$transfer_line" =~ GiB ]]; then
        local gib_value
        gib_value="$(echo "$transfer_line" | grep -oP '[\d.]+(?=\s*GiB)')"
        echo "${gib_value} GiB"
    else
        echo "0 GiB"
    fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    parse_args "$@"

    # 1. Check if NordVPN CLI is installed
    if ! command -v nordvpn &>/dev/null; then
        handle_error "NordVPN CLI is not installed"
    fi

    # 2. Ensure NordVPN is connected
    if ! nordvpn status | grep -q "Status: Connected"; then
        handle_error "Not connected to NordVPN"
    fi

    log INFO "Starting NordVPN data transfer monitoring..."
    printf "\nMonitoring NordVPN data transfer... (Press Ctrl+C to exit)\n"

    # 3. Continuous monitoring loop
    while true; do
        local received_data
        received_data="$(get_received_data)"
        # Overwrite the same line with updated data using carriage return
        printf "\r${NORD8}Data Received: %-12s${NC}" "$received_data"
        sleep "$REFRESH_INTERVAL"
    done
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi