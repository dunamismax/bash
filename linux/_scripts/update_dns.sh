#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: update_dns_records.sh
# Description: Updates Cloudflare DNS A records with the current public IP address.
# Author: Your Name | License: MIT
# Version: 1.0.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./update_dns_records.sh
#
# ------------------------------------------------------------------------------
 
# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
 
# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/update_dns_records.log"  # Path to the log file

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
 
    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"
 
    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"
 
    # Output to console
    printf "${color}%s${NC}\n" "$log_entry" >&2
}
 
# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"  # Default exit code is 1
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
 
    # Log the error with additional context
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."
 
    # Optionally, print the error to stderr for immediate visibility
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2
 
    # Exit with the specified exit code
    exit "$exit_code"
}
 
# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
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
    # Check if CF_API_TOKEN is set
    if [[ -z "${CF_API_TOKEN:-}" ]]; then
        handle_error "Environment variable 'CF_API_TOKEN' is not set. Please set it in /etc/environment."
    fi

    # Check if CF_ZONE_ID is set
    if [[ -z "${CF_ZONE_ID:-}" ]]; then
        handle_error "Environment variable 'CF_ZONE_ID' is not set. Please set it in /etc/environment."
    fi
}
 
# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
update_dns_records() {
    log INFO "Starting DNS update process..."

    # Initialize errors as local
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

    # Check if response contains 'result'
    if ! echo "$response" | jq -e '.result' &>/dev/null; then
        handle_error "Unexpected response from Cloudflare API"
    fi

    # Process and update DNS records
    while IFS= read -r record; do
        local record_id record_name record_type record_ip proxied update_response

        # Extract record details
        record_id=$(jq -r '.id' <<< "$record") || { ((errors++)); continue; }
        record_name=$(jq -r '.name' <<< "$record") || { ((errors++)); continue; }
        record_type=$(jq -r '.type' <<< "$record") || { ((errors++)); continue; }
        record_ip=$(jq -r '.content' <<< "$record") || { ((errors++)); continue; }
        proxied=$(jq -r '.proxied' <<< "$record") || { ((errors++)); continue; }

        # Update A records if the IP has changed
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

            # Verify the update was successful
            if ! jq -e '.success' <<< "$update_response" &>/dev/null; then
                log WARN "Cloudflare API reported failure for DNS record '$record_name'"
                ((errors++))
            else
                log INFO "Successfully updated DNS record '$record_name'"
            fi
        fi
    done < <(jq -c '.result[]' <<< "$response")

    # Handle errors
    if (( errors )); then
        handle_error "DNS update completed with $errors error(s)"
    else
        log INFO "DNS update completed successfully"
    fi
}
 
# ------------------------------------------------------------------------------
# USAGE FUNCTION
# ------------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: sudo $0 [OPTIONS]

Options:
  -h, --help      Show this help message and exit

Description:
  This script updates Cloudflare DNS A records with the current public IP address.
  Ensure that CF_API_TOKEN and CF_ZONE_ID are set in /etc/environment before running.

EOF
    exit 0
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

    # Check for required dependencies
    check_dependencies

    # Validate configuration
    validate_config

    # Ensure the log directory exists and is writable
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE"  # Restrict log file access to root only

    log INFO "Script execution started."

    # Call the main function to update DNS records
    update_dns_records

    log INFO "Script execution finished."
}
 
# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
