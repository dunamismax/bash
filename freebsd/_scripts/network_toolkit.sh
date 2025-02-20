#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: advanced_network_toolkit.sh
# Description: An advanced, production‑grade network toolkit that performs common
#              and advanced network tests, diagnostics, performance measurements,
#              and penetration testing tasks on FreeBSD. This interactive tool
#              provides a Nord‑themed user interface to run connectivity tests,
#              view network configuration, perform port scanning, run performance
#              tests (speedtest, iperf), and execute various pen testing utilities.
#
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./advanced_network_toolkit.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark Background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light Gray (Text)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (Success/Info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (Headings)
NORD9='\033[38;2;129;161;193m'   # Blue (Debug)
NORD10='\033[38;2;94;129;172m'   # Purple (Highlight)
NORD11='\033[38;2;191;97;106m'   # Red (Errors)
NORD12='\033[38;2;208;135;112m'  # Orange (Warnings)
NORD13='\033[38;2;235;203;139m'  # Yellow (Labels)
NORD14='\033[38;2;163;190;140m'  # Green (OK)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING & ERROR HANDLING FUNCTIONS
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] "message"
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level
    upper_level=$(echo "$level" | tr '[:lower:]' '[:upper:]')
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local color="$NC"

    case "$upper_level" in
        INFO)   color="${NORD14}" ;;  # Info: green
        WARN|WARNING)
            upper_level="WARN"
            color="${NORD12}" ;;      # Warn: orange
        ERROR)  color="${NORD11}" ;;     # Error: red
        DEBUG)  color="${NORD9}"  ;;     # Debug: blue
        *)      color="$NC"     ;;
    esac
    echo -e "[$timestamp] [$upper_level] $message"
}

handle_error() {
    local error_message="${1:-"An unknown error occurred."}"
    local exit_code="${2:-1}"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# UI HELPER FUNCTIONS
# ------------------------------------------------------------------------------
print_header() {
    clear
    echo -e "${NORD8}============================================================${NC}"
    echo -e "${NORD8}          ADVANCED NETWORK TOOLKIT MENU                   ${NC}"
    echo -e "${NORD8}============================================================${NC}"
}

print_divider() {
    echo -e "${NORD8}------------------------------------------------------------${NC}"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# BASIC NETWORK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
show_network_interfaces() {
    print_header
    echo -e "${NORD14}Network Interfaces:${NC}"
    print_divider
    # FreeBSD: use ifconfig to list all interfaces
    ifconfig -a | sed "s/^/${NORD4}/; s/$/${NC}/"
    print_divider
    prompt_enter
}

show_routing_table() {
    print_header
    echo -e "${NORD14}Routing Table:${NC}"
    print_divider
    # FreeBSD: use netstat -rn to show routing table
    netstat -rn | sed "s/^/${NORD4}/; s/$/${NC}/"
    print_divider
    prompt_enter
}

show_arp_table() {
    print_header
    echo -e "${NORD14}ARP Table:${NC}"
    print_divider
    arp -a | sed "s/^/${NORD4}/; s/$/${NC}/"
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# CONNECTIVITY TEST FUNCTIONS
# ------------------------------------------------------------------------------
ping_test() {
    print_header
    read -rp "Enter target hostname or IP for ping test: " target
    read -rp "Enter count (default 5): " count
    count=${count:-5}
    print_divider
    echo -e "${NORD14}Pinging ${target} for ${count} packets...${NC}"
    print_divider
    ping -c "$count" "$target" | sed "s/^/${NORD4}/; s/$/${NC}/"
    print_divider
    prompt_enter
}

traceroute_test() {
    print_header
    read -rp "Enter target hostname or IP for traceroute: " target
    print_divider
    echo -e "${NORD14}Traceroute to ${target}:${NC}"
    print_divider
    if command -v traceroute &>/dev/null; then
        traceroute "$target" | sed "s/^/${NORD4}/; s/$/${NC}/"
    elif command -v tracepath &>/dev/null; then
        tracepath "$target" | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}Neither traceroute nor tracepath is installed.${NC}"
    fi
    print_divider
    prompt_enter
}

dns_lookup() {
    print_header
    read -rp "Enter domain for DNS lookup: " domain
    print_divider
    echo -e "${NORD14}DNS Lookup for ${domain}:${NC}"
    print_divider
    if command -v dig &>/dev/null; then
        dig "$domain" +short | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        nslookup "$domain" | sed "s/^/${NORD4}/; s/$/${NC}/"
    fi
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# PORT SCANNING & NETWORK DISCOVERY FUNCTIONS
# ------------------------------------------------------------------------------
port_scan() {
    print_header
    read -rp "Enter target IP/hostname for port scan: " target
    read -rp "Enter port range (e.g., 1-1024): " port_range
    print_divider
    echo -e "${NORD14}Performing port scan on ${target} (ports ${port_range})...${NC}"
    print_divider
    if command -v nmap &>/dev/null; then
        nmap -p "$port_range" "$target" | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}nmap is not installed. Please install nmap for advanced port scanning.${NC}"
    fi
    print_divider
    prompt_enter
}

local_network_scan() {
    print_header
    read -rp "Enter local subnet (e.g., 192.168.1.0/24): " subnet
    print_divider
    echo -e "${NORD14}Scanning local network on subnet ${subnet}...${NC}"
    print_divider
    if command -v nmap &>/dev/null; then
        nmap -sn "$subnet" | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}nmap is not installed. Please install nmap for network discovery.${NC}"
    fi
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# PERFORMANCE TEST FUNCTIONS
# ------------------------------------------------------------------------------
speed_test() {
    print_header
    echo -e "${NORD14}Running speed test...${NC}"
    print_divider
    if command -v speedtest-cli &>/dev/null; then
        speedtest-cli | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}speedtest-cli is not installed. Please install it for WAN performance tests.${NC}"
    fi
    print_divider
    prompt_enter
}

iperf_test() {
    print_header
    echo -e "${NORD14}Iperf Test:${NC}"
    read -rp "Enter iperf server address: " server
    print_divider
    if command -v iperf3 &>/dev/null; then
        iperf3 -c "$server" | sed "s/^/${NORD4}/; s/$/${NC}/"
    elif command -v iperf &>/dev/null; then
        iperf -c "$server" | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}iperf is not installed. Please install iperf3 for performance tests.${NC}"
    fi
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# ADVANCED / PENETRATION TESTING FUNCTIONS
# ------------------------------------------------------------------------------
syn_scan() {
    print_header
    read -rp "Enter target IP/hostname for SYN scan (requires hping3): " target
    read -rp "Enter target port (default 80): " port
    port=${port:-80}
    print_divider
    if command -v hping3 &>/dev/null; then
        echo -e "${NORD14}Performing SYN scan on ${target}:${port}...${NC}"
        hping3 -S -p "$port" "$target" -c 5 | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}hping3 is not installed. Please install it for advanced SYN scans.${NC}"
    fi
    print_divider
    prompt_enter
}

banner_grab() {
    print_header
    read -rp "Enter target IP/hostname for banner grab: " target
    read -rp "Enter target port (default 80): " port
    port=${port:-80}
    print_divider
    if command -v nc &>/dev/null; then
        echo -e "${NORD14}Grabbing banner from ${target}:${port}...${NC}"
        # FreeBSD's netcat supports -w for timeout
        nc -w 5 "$target" "$port" </dev/null | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}netcat (nc) is not installed. Please install it for banner grabbing.${NC}"
    fi
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# FIREWALL & WIFI TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
firewall_check() {
    print_header
    echo -e "${NORD14}Firewall Status:${NC}"
    print_divider
    if command -v pfctl &>/dev/null; then
        pfctl -s info | sed "s/^/${NORD4}/; s/$/${NC}/"
    else
        echo -e "${NORD12}pfctl is not installed or pf is not enabled.${NC}"
    fi
    print_divider
    prompt_enter
}

wifi_scan() {
    print_header
    echo -e "${NORD14}Scanning for WiFi networks:${NC}"
    print_divider
    # On FreeBSD, prompt for the wireless interface and use ifconfig to scan.
    read -rp "Enter wireless interface (e.g., wlan0): " iface
    ifconfig "$iface" scan 2>/dev/null | sed "s/^/${NORD4}/; s/$/${NC}/" || \
        echo -e "${NORD12}WiFi scan failed. Ensure '$iface' is a valid wireless interface.${NC}"
    print_divider
    prompt_enter
}

# ------------------------------------------------------------------------------
# MAIN MENU FUNCTIONS
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Select an option:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Basic Network Information"
        echo -e "${NORD8}[2]${NC} Connectivity Tests"
        echo -e "${NORD8}[3]${NC} Port Scanning & Network Discovery"
        echo -e "${NORD8}[4]${NC} Performance Tests"
        echo -e "${NORD8}[5]${NC} Advanced / Penetration Testing Tools"
        echo -e "${NORD8}[6]${NC} Firewall & WiFi Tools"
        echo -e "${NORD8}[q]${NC} Quit"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) basic_menu ;;
            2) connectivity_menu ;;
            3) scanning_menu ;;
            4) performance_menu ;;
            5) advanced_menu ;;
            6) extras_menu ;;
            q|Q)
                echo -e "${NORD14}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${NORD12}Invalid selection. Please choose a valid option.${NC}"
                sleep 1
                ;;
        esac
    done
}

basic_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Basic Network Information:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Show Network Interfaces"
        echo -e "${NORD8}[2]${NC} Show Routing Table"
        echo -e "${NORD8}[3]${NC} Show ARP Table"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) show_network_interfaces ;;
            2) show_routing_table ;;
            3) show_arp_table ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

connectivity_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Connectivity Tests:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Ping Test"
        echo -e "${NORD8}[2]${NC} Traceroute Test"
        echo -e "${NORD8}[3]${NC} DNS Lookup"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) ping_test ;;
            2) traceroute_test ;;
            3) dns_lookup ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

scanning_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Port Scanning & Network Discovery:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Port Scan"
        echo -e "${NORD8}[2]${NC} Local Network Scan"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) port_scan ;;
            2) local_network_scan ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

performance_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Performance Tests:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Speed Test (WAN)"
        echo -e "${NORD8}[2]${NC} Iperf Test"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) speed_test ;;
            2) iperf_test ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

advanced_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Advanced / Penetration Testing Tools:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} SYN Scan (hping3)"
        echo -e "${NORD8}[2]${NC} Banner Grabbing (netcat)"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) syn_scan ;;
            2) banner_grab ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

extras_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Firewall & WiFi Tools:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Check Firewall Status"
        echo -e "${NORD8}[2]${NC} Scan WiFi Networks"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " opt
        case "$opt" in
            1) firewall_check ;;
            2) wifi_scan ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ "$EUID" -ne 0 ]]; then
        echo -e "${NORD12}This script may require root privileges for some tests.${NC}"
    fi
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
