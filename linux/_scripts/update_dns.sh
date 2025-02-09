#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: update_dns_records.sh
# Description: Updates Cloudflare DNS A records with the current public IP address
#              using a robust Nord‑themed enhanced template with detailed logging
#              and error handling.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   sudo ./update_dns_records.sh [-h|--help]
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/update_dns_records.log"  # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"               # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                            # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"     # Set to true to disable colored output

# Cloudflare API configuration must be provided via environment variables:
#   CF_API_TOKEN and CF_ZONE_ID

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
    local error_message="${1:-"An error occurred. Check the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here.
}

# Set traps for cleanup and error handling
trap cleanup EXIT

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

check_dependencies() {
    local dependencies=("curl" "jq")
    for cmd in "${dependencies[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            handle_error "Dependency '$cmd' is not installed. Please install it and try again."
        fi
    done
}

validate_config() {
    if [[ -z "${CF_API_TOKEN:-}" ]]; then
        handle_error "Environment variable 'CF_API_TOKEN' is not set. Please set it in /etc/environment."
    fi
    if [[ -z "${CF_ZONE_ID:-}" ]]; then
        handle_error "Environment variable 'CF_ZONE_ID' is not set. Please set it in /etc/environment."
    fi
}

usage() {
    cat <<EOF
Usage: sudo $SCRIPT_NAME [OPTIONS]

Description:
  Updates Cloudflare DNS A records with the current public IP address.
  Ensure that CF_API_TOKEN and CF_ZONE_ID are set in your environment (e.g., /etc/environment).

Options:
  -h, --help    Show this help message and exit.

Examples:
  sudo $SCRIPT_NAME --help
EOF
    exit 0
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTION
# ------------------------------------------------------------------------------
update_dns_records() {
    log INFO "Starting DNS update process..."

    local errors=0

    # Fetch the current public IP address
    local current_ip
    if ! current_ip=$(curl -sf4 https://api.ipify.org); then
        handle_error "Failed to detect current public IP address"
    fi
    if [[ ! $current_ip =~ ^[0-9.]+$ ]]; then
        handle_error "Invalid IPv4 address detected: $current_ip"
    fi
    log INFO "Current public IP: $current_ip"

    # Fetch DNS records from Cloudflare
    local response
    if ! response=$(curl -sf -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records?type=A" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json"); then
        handle_error "Failed to fetch DNS records from Cloudflare"
    fi

    # Verify the response contains a 'result' array
    if ! echo "$response" | jq -e '.result' &>/dev/null; then
        handle_error "Unexpected response from Cloudflare API"
    fi

    # Process each DNS record
    while IFS= read -r record; do
        local record_id record_name record_type record_ip proxied update_response

        record_id=$(jq -r '.id' <<< "$record") || { ((errors++)); continue; }
        record_name=$(jq -r '.name' <<< "$record") || { ((errors++)); continue; }
        record_type=$(jq -r '.type' <<< "$record") || { ((errors++)); continue; }
        record_ip=$(jq -r '.content' <<< "$record") || { ((errors++)); continue; }
        proxied=$(jq -r '.proxied' <<< "$record") || { ((errors++)); continue; }

        # Update A records only if the IP address has changed
        if [[ "$record_type" == "A" && "$current_ip" != "$record_ip" ]]; then
            log INFO "Updating DNS record '$record_name': $record_ip → $current_ip"
            if ! update_response=$(curl -sf -X PUT \
                "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/$record_id" \
                -H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json" \
                --data "{\"type\":\"A\",\"name\":\"$record_name\",\"content\":\"$current_ip\",\"ttl\":1,\"proxied\":$proxied}"); then
                log WARN "Failed to update DNS record '$record_name'"
                ((errors++))
                continue
            fi

            if ! jq -e '.success' <<< "$update_response" &>/dev/null; then
                log WARN "Cloudflare API reported failure for DNS record '$record_name'"
                ((errors++))
            else
                log INFO "Successfully updated DNS record '$record_name'"
            fi
        fi
    done < <(jq -c '.result[]' <<< "$response")

    if (( errors )); then
        handle_error "DNS update completed with $errors error(s)"
    else
        log INFO "DNS update completed successfully"
    fi
}

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
parse_args() {
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
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    parse_args "$@"
    check_root
    check_dependencies
    validate_config

    # Ensure the log directory exists and secure the log file
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    update_dns_records

    log INFO "Script execution finished."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi