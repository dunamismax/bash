#!/bin/bash

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Exit immediately if a command exits with a non-zero status,
# if any variable is unset, and if any command in a pipeline fails
set -euo pipefail

# Variables
CF_API_TOKEN="_3zWgksLETucvKLN0ICn_Mbh7x-_Cooo_Anb2Dv4"
CF_ZONE_ID="dc739d9b91869a4ff2c8002125f6836c"
LOG_FILE="/var/log/cloudflare-dyndns.log"

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to log messages with timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Function to handle errors
handle_error() {
    log "An error occurred during the DNS update process. Check the log for details."
    exit 1
}

# Trap errors and execute handle_error
trap 'handle_error' ERR

# Function to update A records in Cloudflare if IP has changed
update_dns_records() {
    # Get current public IP
    local current_ip
    current_ip=$(curl -s https://api.ipify.org)
    log "Current public IP is: $current_ip"

    # Get all DNS records for the specified zone
    local dns_records
    dns_records=$(
        curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json"
    )

    # Loop through each DNS record and update if necessary
    echo "$dns_records" | jq -c '.result[]' | while read -r record; do
        local record_id record_name record_type record_ip proxied
        record_id=$(echo "$record" | jq -r '.id')
        record_name=$(echo "$record" | jq -r '.name')
        record_type=$(echo "$record" | jq -r '.type')
        record_ip=$(echo "$record" | jq -r '.content')
        proxied=$(echo "$record" | jq -r '.proxied')

        # Only update A records with a changed IP
        if [[ "$record_type" == "A" && "$current_ip" != "$record_ip" ]]; then
            log "Updating $record_name (ID: $record_id) from $record_ip to $current_ip"
            curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records/$record_id" \
                -H "Authorization: Bearer $CF_API_TOKEN" \
                -H "Content-Type: application/json" \
                --data '{
                    "type": "A",
                    "name": "'"$record_name"'",
                    "content": "'"$current_ip"'",
                    "ttl": 1,
                    "proxied": '"$proxied"'
                }' >> "$LOG_FILE" 2>&1
        else
            log "No update needed for $record_name (ID: $record_id)."
        fi
    done
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

# Ensure the log file exists and has appropriate permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting Cloudflare Dynamic DNS Update Script"

update_dns_records

log "DNS update process completed successfully on $(date)."
log "--------------------------------------"

exit 0
