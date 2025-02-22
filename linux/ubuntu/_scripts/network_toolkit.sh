#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: advanced_network_toolkit.sh
# Description: An advanced, production‑grade network toolkit that performs common
#              and advanced network tests, diagnostics, performance measurements,
#              and penetration testing tasks on Debian. This interactive tool
#              provides a Nord‑themed user interface using strict error handling,
#              detailed logging with log‑level filtering, and graceful signal traps.
# Author: Your Name | License: MIT | Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./advanced_network_toolkit.sh
#
# Notes:
#   - This script requires root privileges for some tests.
#   - Logs are stored at /var/log/advanced_network_toolkit.log by default.
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
readonly LOG_FILE="/var/log/advanced_network_toolkit.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"          # Set to "true" to disable colored output
readonly DEFAULT_LOG_LEVEL="INFO"                           # Default log level (VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL)

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'   # Bluish (DEBUG)
readonly NORD10='\033[38;2;94;129;172m'   # Accent Blue (Section Headers)
readonly NORD11='\033[38;2;191;97;106m'   # Reddish (ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'  # Yellowish (WARN)
readonly NORD14='\033[38;2;163;190;140m'  # Greenish (INFO)
readonly NC='\033[0m'                     # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"  # uppercase
    case "$lvl" in
        VERBOSE|V)    echo 0 ;;
        DEBUG|D)      echo 1 ;;
        INFO|I)       echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)      echo 4 ;;
        CRITICAL|C)   echo 5 ;;
        *)            echo 2 ;;  # default to INFO
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
    local msg_level current_level
    msg_level=$(get_log_level_num "$upper_level")
    current_level=$(get_log_level_num "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}")
    if (( msg_level < current_level )); then
        return 0
    fi

    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)   color="${NORD9}"  ;;  # Bluish
            INFO)    color="${NORD14}" ;;  # Greenish
            WARN)    color="${NORD13}" ;;  # Yellowish
            ERROR|CRITICAL) color="${NORD11}" ;;  # Reddish
            *)       color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
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
    # Add any cleanup tasks here (e.g., remove temporary files)
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

# Prints a styled section header using Nord accent colors
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# Pause for user input
prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# Clear the screen and print header (for interactive menus)
print_header() {
    clear
    print_section "ADVANCED NETWORK TOOLKIT MENU"
}

# ------------------------------------------------------------------------------
# BASIC NETWORK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
show_network_interfaces() {
    print_section "Network Interfaces"
    log INFO "Displaying network interfaces..."
    ip addr show | sed "s/^/${NORD14}/; s/$/${NC}/"
    prompt_enter
}

show_routing_table() {
    print_section "Routing Table"
    log INFO "Displaying routing table..."
    ip route | sed "s/^/${NORD14}/; s/$/${NC}/"
    prompt_enter
}

show_arp_table() {
    print_section "ARP Table"
    log INFO "Displaying ARP table..."
    arp -a | sed "s/^/${NORD14}/; s/$/${NC}/"
    prompt_enter
}

# ------------------------------------------------------------------------------
# CONNECTIVITY TEST FUNCTIONS
# ------------------------------------------------------------------------------
ping_test() {
    print_section "Ping Test"
    read -rp "Enter target hostname or IP for ping test: " target
    read -rp "Enter count (default 5): " count
    count=${count:-5}
    log INFO "Pinging ${target} for ${count} packets..."
    ping -c "$count" "$target" | sed "s/^/${NORD14}/; s/$/${NC}/"
    prompt_enter
}

traceroute_test() {
    print_section "Traceroute Test"
    read -rp "Enter target hostname or IP for traceroute: " target
    log INFO "Performing traceroute to ${target}..."
    if command -v traceroute &>/dev/null; then
        traceroute "$target" | sed "s/^/${NORD14}/; s/$/${NC}/"
    elif command -v tracepath &>/dev/null; then
        tracepath "$target" | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "Neither traceroute nor tracepath is installed."
        echo -e "${NORD13}Warning: Neither traceroute nor tracepath is installed.${NC}"
    fi
    prompt_enter
}

dns_lookup() {
    print_section "DNS Lookup"
    read -rp "Enter domain for DNS lookup: " domain
    log INFO "Performing DNS lookup for ${domain}..."
    if command -v dig &>/dev/null; then
        dig "$domain" +short | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        nslookup "$domain" | sed "s/^/${NORD14}/; s/$/${NC}/"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# PORT SCANNING & NETWORK DISCOVERY FUNCTIONS
# ------------------------------------------------------------------------------
port_scan() {
    print_section "Port Scan"
    read -rp "Enter target IP/hostname for port scan: " target
    read -rp "Enter port range (e.g., 1-1024): " port_range
    log INFO "Scanning ${target} for ports in range ${port_range}..."
    if command -v nmap &>/dev/null; then
        nmap -p "$port_range" "$target" | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "nmap is not installed. Please install nmap for port scanning."
        echo -e "${NORD13}Warning: nmap is not installed.${NC}"
    fi
    prompt_enter
}

local_network_scan() {
    print_section "Local Network Scan"
    read -rp "Enter local subnet (e.g., 192.168.1.0/24): " subnet
    log INFO "Scanning local network on subnet ${subnet}..."
    if command -v nmap &>/dev/null; then
        nmap -sn "$subnet" | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "nmap is not installed. Please install nmap for network discovery."
        echo -e "${NORD13}Warning: nmap is not installed.${NC}"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# PERFORMANCE TEST FUNCTIONS
# ------------------------------------------------------------------------------
speed_test() {
    print_section "Speed Test"
    log INFO "Running WAN speed test..."
    if command -v speedtest-cli &>/dev/null; then
        speedtest-cli | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "speedtest-cli is not installed. Please install it for WAN performance tests."
        echo -e "${NORD13}Warning: speedtest-cli is not installed.${NC}"
    fi
    prompt_enter
}

iperf_test() {
    print_section "Iperf Test"
    read -rp "Enter iperf server address: " server
    log INFO "Running iperf test against ${server}..."
    if command -v iperf3 &>/dev/null; then
        iperf3 -c "$server" | sed "s/^/${NORD14}/; s/$/${NC}/"
    elif command -v iperf &>/dev/null; then
        iperf -c "$server" | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "iperf is not installed. Please install iperf3 for performance tests."
        echo -e "${NORD13}Warning: iperf is not installed.${NC}"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# ADVANCED / PENETRATION TESTING FUNCTIONS
# ------------------------------------------------------------------------------
syn_scan() {
    print_section "SYN Scan"
    read -rp "Enter target IP/hostname for SYN scan (requires hping3): " target
    read -rp "Enter target port (default 80): " port
    port=${port:-80}
    log INFO "Performing SYN scan on ${target}:${port}..."
    if command -v hping3 &>/dev/null; then
        hping3 -S -p "$port" "$target" -c 5 | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "hping3 is not installed. Please install hping3 for SYN scanning."
        echo -e "${NORD13}Warning: hping3 is not installed.${NC}"
    fi
    prompt_enter
}

banner_grab() {
    print_section "Banner Grab"
    read -rp "Enter target IP/hostname for banner grab: " target
    read -rp "Enter target port (default 80): " port
    port=${port:-80}
    log INFO "Grabbing banner from ${target}:${port}..."
    if command -v nc &>/dev/null; then
        timeout 5 nc "$target" "$port" </dev/null | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "netcat (nc) is not installed. Please install it for banner grabbing."
        echo -e "${NORD13}Warning: netcat (nc) is not installed.${NC}"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# FIREWALL & WIFI TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
firewall_check() {
    print_section "Firewall Status"
    log INFO "Checking firewall status..."
    if command -v ufw &>/dev/null; then
        ufw status verbose | sed "s/^/${NORD14}/; s/$/${NC}/"
    elif command -v iptables &>/dev/null; then
        iptables -L -n | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "No firewall tool detected."
        echo -e "${NORD13}Warning: No firewall tool detected.${NC}"
    fi
    prompt_enter
}

wifi_scan() {
    print_section "WiFi Scan"
    log INFO "Scanning for WiFi networks..."
    if command -v nmcli &>/dev/null; then
        nmcli device wifi list | sed "s/^/${NORD14}/; s/$/${NC}/"
    else
        log WARN "nmcli is not installed. Please install NetworkManager CLI for WiFi scanning."
        echo -e "${NORD13}Warning: nmcli is not installed.${NC}"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# MAIN MENU FUNCTIONS
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        log INFO "Select an option:"
        echo -e "${NORD10}[1]${NC} Basic Network Information"
        echo -e "${NORD10}[2]${NC} Connectivity Tests"
        echo -e "${NORD10}[3]${NC} Port Scanning & Network Discovery"
        echo -e "${NORD10}[4]${NC} Performance Tests"
        echo -e "${NORD10}[5]${NC} Advanced / Penetration Testing Tools"
        echo -e "${NORD10}[6]${NC} Firewall & WiFi Tools"
        echo -e "${NORD10}[q]${NC} Quit"
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) basic_menu ;;
            2) connectivity_menu ;;
            3) scanning_menu ;;
            4) performance_menu ;;
            5) advanced_menu ;;
            6) extras_menu ;;
            q|Q)
                log INFO "Exiting. Goodbye!"
                exit 0
                ;;
            *)
                log WARN "Invalid selection. Please choose a valid option."
                sleep 1
                ;;
        esac
    done
}

basic_menu() {
    while true; do
        print_header
        log INFO "Basic Network Information:"
        echo -e "${NORD10}[1]${NC} Show Network Interfaces"
        echo -e "${NORD10}[2]${NC} Show Routing Table"
        echo -e "${NORD10}[3]${NC} Show ARP Table"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) show_network_interfaces ;;
            2) show_routing_table ;;
            3) show_arp_table ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

connectivity_menu() {
    while true; do
        print_header
        log INFO "Connectivity Tests:"
        echo -e "${NORD10}[1]${NC} Ping Test"
        echo -e "${NORD10}[2]${NC} Traceroute Test"
        echo -e "${NORD10}[3]${NC} DNS Lookup"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) ping_test ;;
            2) traceroute_test ;;
            3) dns_lookup ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

scanning_menu() {
    while true; do
        print_header
        log INFO "Port Scanning & Network Discovery:"
        echo -e "${NORD10}[1]${NC} Port Scan"
        echo -e "${NORD10}[2]${NC} Local Network Scan"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) port_scan ;;
            2) local_network_scan ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

performance_menu() {
    while true; do
        print_header
        log INFO "Performance Tests:"
        echo -e "${NORD10}[1]${NC} Speed Test (WAN)"
        echo -e "${NORD10}[2]${NC} Iperf Test"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) speed_test ;;
            2) iperf_test ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

advanced_menu() {
    while true; do
        print_header
        log INFO "Advanced / Penetration Testing Tools:"
        echo -e "${NORD10}[1]${NC} SYN Scan (hping3)"
        echo -e "${NORD10}[2]${NC} Banner Grabbing (netcat)"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) syn_scan ;;
            2) banner_grab ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

extras_menu() {
    while true; do
        print_header
        log INFO "Firewall & WiFi Tools:"
        echo -e "${NORD10}[1]${NC} Check Firewall Status"
        echo -e "${NORD10}[2]${NC} Scan WiFi Networks"
        echo -e "${NORD10}[0]${NC} Return to Main Menu"
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) firewall_check ;;
            2) wifi_scan ;;
            0) break ;;
            *)
                log WARN "Invalid selection."
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists and file is created with secure permissions.
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Advanced Network Toolkit execution started."

    # Loop the main menu
    while true; do
        main_menu
    done
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
