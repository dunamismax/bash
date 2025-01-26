#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: nordvpn-monitor.sh
# Description: Real-time monitor for NordVPN data transfer (received GiB/TiB)
# Author: Your Name | License: MIT
# Version: 1.1.0
# ------------------------------------------------------------------------------
# Usage:
#   ./nordvpn-monitor.sh
# ------------------------------------------------------------------------------

set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
REFRESH_INTERVAL=1  # Update interval in seconds

# ------------------------------------------------------------------------------
# ERROR HANDLING
# ------------------------------------------------------------------------------
handle_error() {
    printf "\nERROR: %s\n" "$1" >&2
    exit 1
}

# ------------------------------------------------------------------------------
# DATA EXTRACTION FUNCTION
# ------------------------------------------------------------------------------
get_received_data() {
    local transfer_line
    transfer_line=$(nordvpn status | grep -oP 'Transfer: \K.*(?= received)')
    
    if [[ "$transfer_line" =~ TiB ]]; then
        # Extract TiB value and convert to GiB
        tib_value=$(echo "$transfer_line" | grep -oP '[\d.]+(?= TiB)')
        echo "$tib_value TiB"
    elif [[ "$transfer_line" =~ GiB ]]; then
        # Extract GiB value
        gib_value=$(echo "$transfer_line" | grep -oP '[\d.]+(?= GiB)')
        echo "$gib_value GiB"
    else
        echo "0 GiB"
    fi
}

# ------------------------------------------------------------------------------
# MAIN SCRIPT
# ------------------------------------------------------------------------------
main() {
    # Check if nordvpn is installed
    if ! command -v nordvpn &> /dev/null; then
        handle_error "NordVPN CLI is not installed"
    fi

    # Check VPN connection status
    if ! nordvpn status | grep -q "Status: Connected"; then
        handle_error "Not connected to NordVPN"
    fi

    printf "Monitoring NordVPN data transfer... (Press Ctrl+C to exit)\n"

    # Continuous monitoring loop
    while true; do
        # Get and format received data
        received_data=$(get_received_data)
        
        # Print with carriage return to overwrite previous line
        printf "\rData Received: %-12s" "$received_data"
        
        # Wait for specified interval
        sleep "$REFRESH_INTERVAL"
    done
}

# Cleanup on exit
trap 'printf "\n"; exit 0' SIGINT

# Execute main function
main "$@"