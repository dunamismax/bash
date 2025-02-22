#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: update_dns_records.sh
# Description: Updates Cloudflare DNS A records with the current public IP address
#              using the Cloudflare API. Designed for Debian.
# Author: Your Name | License: MIT | Version: 3.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./update_dns_records.sh [-h|--help]
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/update_dns_records.log by default.
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
readonly LOG_FILE="/var/log/update_dns_records.log"   # Log file path
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"      # Set to "true" to disable colored output
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"                 # Options: INFO, DEBUG, WARN, ERROR, CRITICAL
readonly QUIET_MODE=false

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'    # Bluish (DEBUG)
readonly NORD10='\033[38;2;94;129;172m'     # Accent Blue (section headers)
readonly NORD11='\033[38;2;191;97;106m'     # Reddish (ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'    # Yellowish (WARN)
readonly NORD14='\033[38;2;163;190;140m'    # Greenish (INFO)
readonly NC='\033[0m'                       # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W)echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL "message"
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    # Only output DEBUG messages when LOG_LEVEL is set to DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

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
    local error_message="${1:-"An unknown error occurred"}"
    local exit_code="${2:-1}"
    local lineno="${BASH_LINENO[0]:-${LINENO}}"
    local func="${FUNCNAME[1]:-main}"

    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Error in function '$func' at line $lineno."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

check_dependencies() {
    local dependencies=(curl jq)
    for cmd in "${dependencies[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            handle_error "Dependency '$cmd' is not installed. Please install it and try again."
        fi
    done
}

validate_config() {
    # Cloudflare API configuration must be provided via environment variables:
    #   CF_API_TOKEN and CF_ZONE_ID
    if [[ -z "${CF_API_TOKEN:-}" ]]; then
        handle_error "Environment variable 'CF_API_TOKEN' is not set. Please set it (e.g., in /etc/environment)."
    fi
    if [[ -z "${CF_ZONE_ID:-}" ]]; then
        handle_error "Environment variable 'CF_ZONE_ID' is not set. Please set it (e.g., in /etc/environment)."
    fi
}

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
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

get_public_ip() {
    local ip
    if ! ip=$(curl -sf4 https://api.ipify.org); then
        handle_error "Failed to retrieve public IP address."
    fi
    if [[ ! $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        handle_error "Invalid IPv4 address detected: $ip"
    fi
    echo "$ip"
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTION: Update DNS Records
# ------------------------------------------------------------------------------
update_dns_records() {
    print_section "Starting Cloudflare DNS Update"

    log INFO "Fetching current public IP address..."
    local current_ip
    current_ip="$(get_public_ip)"
    log INFO "Current public IP: $current_ip"

    log INFO "Fetching DNS records from Cloudflare..."
    local response
    if ! response=$(curl -sf -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records?type=A" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json"); then
        handle_error "Failed to fetch DNS records from Cloudflare."
    fi

    # Verify that the response contains a valid 'result' array
    if ! echo "$response" | jq -e '.result' &>/dev/null; then
        handle_error "Unexpected response from Cloudflare API."
    fi

    local errors=0
    while IFS= read -r record; do
        local record_id record_name record_type record_ip proxied update_response

        record_id=$(jq -r '.id' <<< "$record") || { ((errors++)); continue; }
        record_name=$(jq -r '.name' <<< "$record") || { ((errors++)); continue; }
        record_type=$(jq -r '.type' <<< "$record") || { ((errors++)); continue; }
        record_ip=$(jq -r '.content' <<< "$record") || { ((errors++)); continue; }
        proxied=$(jq -r '.proxied' <<< "$record") || { ((errors++)); continue; }

        # Update A records only if the IP address has changed
        if [[ "$record_type" == "A" && "$record_ip" != "$current_ip" ]]; then
            log INFO "Updating DNS record '$record_name': $record_ip → $current_ip"
            if ! update_response=$(curl -sf -X PUT \
                "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
                -H "Authorization: Bearer ${CF_API_TOKEN}" \
                -H "Content-Type: application/json" \
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
        else
            log DEBUG "No update needed for record '$record_name' (current IP: $record_ip)"
        fi
    done < <(jq -c '.result[]' <<< "$response")

    if (( errors )); then
        handle_error "DNS update completed with $errors error(s)"
    else
        log INFO "DNS update completed successfully"
    fi
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

    # Ensure the log directory exists and secure the log file.
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    update_dns_records

    log INFO "Script execution finished successfully."
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
