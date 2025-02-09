#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: live_log_analyzer.sh
# Description: An advanced, interactive, real‑time log analyzer that lets you
#              monitor various log files and systemd service logs with a beautiful
#              Nord‑themed interface. The script scans pre‐configured log
#              categories (e.g., Website, System, Application, Security) and also
#              allows you to monitor any custom log file. While tailing, new log
#              entries stream from the bottom. Pressing Ctrl+C returns you to the
#              main menu; from the main menu, press Ctrl+C or type "q" to quit.
#
#              Additionally, you can monitor systemd service logs by entering the
#              service name (with suggestions).
#
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./live_log_analyzer.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light gray (for log text)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (for success/info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (for headings)
NORD9='\033[38;2;129;161;193m'   # Blue (for debug)
NORD10='\033[38;2;94;129;172m'   # Purple (for highlights)
NORD11='\033[38;2;191;97;106m'   # Red (for errors)
NORD12='\033[38;2;208;135;112m'  # Orange (for warnings)
NORD13='\033[38;2;235;203;139m'  # Yellow (for labels)
NORD14='\033[38;2;163;190;140m'  # Green (for success)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING & ERROR HANDLING FUNCTIONS
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] "message"
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local color="$NC"
    case "$upper_level" in
        INFO)  color="${NORD14}" ;;  # Info: green
        WARN|WARNING)
            upper_level="WARN"
            color="${NORD12}" ;;      # Warn: orange
        ERROR) color="${NORD11}" ;;     # Error: red
        DEBUG) color="${NORD9}"  ;;     # Debug: blue
        *)     color="$NC"     ;;
    esac
    echo -e "[$timestamp] [$upper_level] $message" >> /dev/null  # (Optional log file output)
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
print_divider() {
    echo -e "${NORD8}------------------------------------------------------------${NC}"
}

print_header() {
    clear
    echo -e "${NORD8}============================================================${NC}"
    echo -e "${NORD8}             LIVE REAL‑TIME LOG ANALYZER                    ${NC}"
    echo -e "${NORD8}============================================================${NC}"
}

print_help_hint() {
    echo -e "${NORD13}Hint:${NC} Press Ctrl+C while tailing to return to the main menu."
    echo -e "${NORD13}Hint:${NC} In the main menu, type 'q' or press Ctrl+C to quit."
}

# ------------------------------------------------------------------------------
# PRE-CONFIGURED LOG CATEGORIES & FILES
# ------------------------------------------------------------------------------
# Website Logs (Caddy)
WEBSITE_LOGS=(
    "/var/log/caddy/ai_agents_access.log"
    "/var/log/caddy/caddy.log"
    "/var/log/caddy/dunamismax_access.log"
    "/var/log/caddy/file_converter_access.log"
    "/var/log/caddy/messenger_access.log"
    "/var/log/caddy/notes_access.log"
)

# System Logs (Ubuntu common)
SYSTEM_LOGS=(
    "/var/log/syslog"
    "/var/log/kern.log"
    "/var/log/auth.log"
    "/var/log/daemon.log"
    "/var/log/boot.log"
)

# Application Logs (Web servers)
APPLICATION_LOGS=(
    "/var/log/apache2/access.log"
    "/var/log/apache2/error.log"
    "/var/log/nginx/access.log"
    "/var/log/nginx/error.log"
)

# Security Logs
SECURITY_LOGS=(
    "/var/log/auth.log"
    "/var/log/audit/audit.log"
)

# ------------------------------------------------------------------------------
# TAIL FUNCTIONS
# ------------------------------------------------------------------------------
tail_log() {
    local logfile="$1"
    if [[ ! -f "$logfile" ]]; then
        echo -e "${NORD12}Log file not found: $logfile${NC}"
        sleep 2
        return
    fi
    clear
    echo -e "${NORD8}Now monitoring log file:${NC} ${NORD4}$logfile${NC}"
    print_help_hint
    # Trap Ctrl+C to break out of tailing and return to menu.
    trap 'kill $! 2>/dev/null; return 0' SIGINT
    tail -n 50 -F "$logfile" | sed "s/^/${NORD4}/; s/$/${NC}/"
    trap - SIGINT
}

tail_systemd_service() {
    local service="$1"
    clear
    echo -e "${NORD8}Now monitoring systemd service:${NC} ${NORD4}$service${NC}"
    print_help_hint
    trap 'kill $! 2>/dev/null; return 0' SIGINT
    journalctl -fu "$service" --no-pager --lines=50 --color=always | sed "s/^/${NORD4}/; s/$/${NC}/"
    trap - SIGINT
}

# ------------------------------------------------------------------------------
# SYSTEMD SERVICE SELECTION WITH SUGGESTIONS
# ------------------------------------------------------------------------------
select_systemd_service() {
    local input service
    read -rp "Enter systemd service name (or partial): " input
    # Get matching services
    local matches
    matches=$(systemctl list-units --type=service --all | awk '{print $1}' | grep -i "$input")
    if [[ -z "$matches" ]]; then
        echo -e "${NORD12}No matching services found.${NC}"
        return 1
    fi
    echo -e "${NORD8}Matching services:${NC}"
    local i=1
    declare -a services_arr
    while read -r line; do
        services_arr+=("$line")
        echo -e "${NORD8}[${i}]${NC} ${NORD4}$line${NC}"
        ((i++))
    done <<< "$matches"
    local choice
    read -rp "Select a service by number: " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice < i )); then
        service="${services_arr[$((choice-1))]}"
        echo "$service"
        return 0
    else
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
}

# ------------------------------------------------------------------------------
# CATEGORY MENU FUNCTION
# ------------------------------------------------------------------------------
list_category_logs() {
    # Arguments: array name
    local array_name="$1"
    local -n logs_array="$array_name"
    local available=()
    local idx=1
    for logfile in "${logs_array[@]}"; do
        if [[ -f "$logfile" ]]; then
            available+=("$logfile")
            echo -e "${NORD8}[${idx}]${NC} ${NORD4}$logfile${NC}"
            ((idx++))
        fi
    done
    if (( ${#available[@]} == 0 )); then
        echo -e "${NORD12}No available log files found in this category.${NC}"
        return 1
    fi
    SELECTED_LOGS=("${available[@]}")
    return 0
}

# ------------------------------------------------------------------------------
# MAIN MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Select an option:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Monitor Website Logs (/var/log/caddy)"
        echo -e "${NORD8}[2]${NC} Monitor System Logs (Ubuntu)"
        echo -e "${NORD8}[3]${NC} Monitor Application Logs (Apache/Nginx)"
        echo -e "${NORD8}[4]${NC} Monitor Security Logs"
        echo -e "${NORD8}[5]${NC} Monitor systemd Service Logs"
        echo -e "${NORD8}[6]${NC} Monitor a Custom Log File"
        echo -e "${NORD8}[q]${NC} Quit"
        print_divider
        read -rp "Enter your choice: " main_choice
        case "$main_choice" in
            1)  category_menu "Website Logs" WEBSITE_LOGS ;;
            2)  category_menu "System Logs" SYSTEM_LOGS ;;
            3)  category_menu "Application Logs" APPLICATION_LOGS ;;
            4)  category_menu "Security Logs" SECURITY_LOGS ;;
            5)  monitor_systemd_service ;;
            6)  monitor_custom_log ;;
            q|Q)
                echo -e "${NORD14}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${NORD12}Invalid choice. Please select a valid option.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# CATEGORY MENU HANDLER
# ------------------------------------------------------------------------------
category_menu() {
    local category_name="$1"
    local array_name="$2"
    print_header
    echo -e "${NORD14}${category_name}:${NC}"
    print_divider
    if ! list_category_logs "$array_name"; then
        echo -e "${NORD12}Returning to main menu...${NC}"
        sleep 2
        return
    fi
    echo ""
    read -rp "Select a log file by number (or 'b' to go back): " choice
    if [[ "$choice" == "b" || "$choice" == "B" ]]; then
        return
    elif [[ "$choice" =~ ^[0-9]+$ ]]; then
        if (( choice < 1 || choice > ${#SELECTED_LOGS[@]} )); then
            echo -e "${NORD12}Invalid selection. Returning to main menu.${NC}"
            sleep 2
            return
        fi
        local selected_log="${SELECTED_LOGS[$((choice-1))]}"
        tail_log "$selected_log"
    else
        echo -e "${NORD12}Invalid input. Returning to main menu.${NC}"
        sleep 2
    fi
}

# ------------------------------------------------------------------------------
# MONITOR SYSTEMD SERVICE HANDLER
# ------------------------------------------------------------------------------
monitor_systemd_service() {
    print_header
    echo -e "${NORD14}Monitor systemd service logs${NC}"
    print_divider
    local service
    service=$(select_systemd_service) || { sleep 2; return; }
    tail_systemd_service "$service"
}

# ------------------------------------------------------------------------------
# MONITOR CUSTOM LOG FILE HANDLER
# ------------------------------------------------------------------------------
monitor_custom_log() {
    print_header
    echo -e "${NORD14}Monitor a Custom Log File${NC}"
    print_divider
    read -rp "Enter full path to log file: " custom_log
    if [[ ! -f "$custom_log" ]]; then
        echo -e "${NORD12}File does not exist: $custom_log${NC}"
        sleep 2
        return
    fi
    tail_log "$custom_log"
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Catch Ctrl+C in the main menu to exit gracefully.
    trap 'echo -e "\n${NORD14}Exiting...${NC}"; exit 0' SIGINT
    main_menu
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi