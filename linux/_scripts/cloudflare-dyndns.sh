#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: cloudflare-dyndns.sh
# Description: Updates Cloudflare DNS A records with the current public IP address.
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./cloudflare-dyndns.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
CF_API_TOKEN="_3zWgksLETucvKLN0ICn_Mbh7x-_Cooo_Anb2Dv4"  # Cloudflare API token
CF_ZONE_ID="dc739d9b91869a4ff2c8002125f6836c"            # Cloudflare Zone ID
LOG_FILE="/var/log/cloudflare-dyndns.log"                # Path to the log file

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

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
update_dns_records() {
    log INFO "--------------------------------------"
    log INFO "Starting DNS record update process..."

    # Get current public IP
    local current_ip
    current_ip=$(curl -s https://api.ipify.org) || handle_error "Failed to retrieve public IP."
    log INFO "Current public IP is: $current_ip"

    # Get all DNS records for the specified zone
    local dns_records
    dns_records=$(
        curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json"
    ) || handle_error "Failed to retrieve DNS records from Cloudflare."

    # Loop through each DNS record and update if necessary
    echo "$dns_records" | jq -c '.result[]' | while read -r record; do
        local record_id record_name record_type record_ip proxied
        record_id=$(echo "$record" | jq -r '.id') || handle_error "Failed to parse DNS record ID."
        record_name=$(echo "$record" | jq -r '.name') || handle_error "Failed to parse DNS record name."
        record_type=$(echo "$record" | jq -r '.type') || handle_error "Failed to parse DNS record type."
        record_ip=$(echo "$record" | jq -r '.content') || handle_error "Failed to parse DNS record IP."
        proxied=$(echo "$record" | jq -r '.proxied') || handle_error "Failed to parse DNS record proxied status."

        # Only update A records with a changed IP
        if [[ "$record_type" == "A" && "$current_ip" != "$record_ip" ]]; then
            log INFO "Updating $record_name (ID: $record_id) from $record_ip to $current_ip"
            curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records/$record_id" \
                -H "Authorization: Bearer $CF_API_TOKEN" \
                -H "Content-Type: application/json" \
                --data '{
                    "type": "A",
                    "name": "'"$record_name"'",
                    "content": "'"$current_ip"'",
                    "ttl": 1,
                    "proxied": '"$proxied"'
                }' >> "$LOG_FILE" 2>&1 || handle_error "Failed to update DNS record for $record_name."
        else
            log INFO "No update needed for $record_name (ID: $record_id)."
        fi
    done

    log INFO "DNS record update process completed."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run as root
    check_root

    # Ensure the log file exists and has appropriate permissions
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 644 "$LOG_FILE" || handle_error "Failed to set permissions for log file: $LOG_FILE"

    log INFO "Script execution started."

    # Call the main function to update DNS records
    update_dns_records

    log INFO "Script execution finished."
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi