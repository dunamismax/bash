#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: nordvpn-monitor.sh
# Description: Real-time monitor for NordVPN data transfer (received GiB/TiB).
# Author: Your Name | License: MIT
# Version: 1.1.1
# ------------------------------------------------------------------------------
#
# Usage:
#   ./nordvpn-monitor.sh
#
# Notes:
#   - Displays the total data received via NordVPN in real-time.
#   - Requires NordVPN CLI to be installed and actively connected.
#
# Requirements:
#   - NordVPN CLI
#   - Bash 4+
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# For more information, see:
#   https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"

    printf "\nERROR: %s\n" "$error_message" >&2
    exit "$exit_code"
}

# Trap any uncaught errors
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# Trap SIGINT (Ctrl+C) for a cleaner exit
trap 'printf "\n"; exit 0' SIGINT

# ------------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ------------------------------------------------------------------------------
REFRESH_INTERVAL=1  # Update interval (in seconds)

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
get_received_data() {
    # Extract the line containing 'Transfer: X received' from `nordvpn status`
    local transfer_line
    transfer_line="$(nordvpn status | grep -oP 'Transfer:\s+\K.*(?=\s+received)')"

    if [[ "$transfer_line" =~ TiB ]]; then
        # If the line indicates TiB, extract numeric value and display in TiB
        local tib_value
        tib_value="$(echo "$transfer_line" | grep -oP '[\d.]+(?=\s*TiB)')"
        echo "${tib_value} TiB"
    elif [[ "$transfer_line" =~ GiB ]]; then
        # If the line indicates GiB, extract numeric value and display in GiB
        local gib_value
        gib_value="$(echo "$transfer_line" | grep -oP '[\d.]+(?=\s*GiB)')"
        echo "${gib_value} GiB"
    else
        # Default to 0 GiB if neither TiB nor GiB is detected
        echo "0 GiB"
    fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # 1. Check if the NordVPN CLI is installed
    if ! command -v nordvpn &>/dev/null; then
        handle_error "NordVPN CLI is not installed"
    fi

    # 2. Ensure NordVPN is connected
    if ! nordvpn status | grep -q "Status: Connected"; then
        handle_error "Not connected to NordVPN"
    fi

    printf "Monitoring NordVPN data transfer... (Press Ctrl+C to exit)\n"

    # 3. Continuous monitoring loop
    while true; do
        local received_data
        received_data="$(get_received_data)"
        # Use carriage return (\r) to overwrite the same line
        printf "\rData Received: %-12s" "$received_data"
        sleep "$REFRESH_INTERVAL"
    done
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    exit 0
fi
