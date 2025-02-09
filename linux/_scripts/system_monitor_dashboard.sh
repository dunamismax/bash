#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: system_monitor_dashboard.sh
# Description: Displays a real‑time system monitoring dashboard with key metrics
#              such as CPU usage, memory consumption, disk usage (with emphasis on
#              the /media/WD_BLACK drive), network activity, uptime, load average,
#              and process count. The dashboard is formatted using the Nord color
#              theme for a visually engaging display.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   ./system_monitor_dashboard.sh [-d|--debug] [-q|--quiet]
#   ./system_monitor_dashboard.sh -h|--help
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
LOG_FILE="/var/log/system_monitor_dashboard.log"  # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"                   # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                                # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"         # Set to true to disable colored output
REFRESH_INTERVAL=2                              # Dashboard refresh interval (in seconds)

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
    
    # Only log DEBUG messages if LOG_LEVEL is DEBUG
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
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Exiting System Monitoring Dashboard..."
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
enable_debug() {
    LOG_LEVEL="DEBUG"
    log DEBUG "Debug mode enabled: Verbose logging activated."
}

enable_quiet_mode() {
    QUIET_MODE=true
    log INFO "Quiet mode enabled: Console output suppressed."
}

show_help() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Description:
  Displays a real‑time system monitoring dashboard with metrics including CPU usage,
  memory consumption, disk usage (with details for /media/WD_BLACK), network activity,
  uptime, load average, and process count. The dashboard refreshes every $REFRESH_INTERVAL
  seconds.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output (logs still written to file).
  -h, --help    Show this help message and exit.

Examples:
  $SCRIPT_NAME --debug
  $SCRIPT_NAME --quiet
  $SCRIPT_NAME -h
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--debug)
                enable_debug ;;
            -q|--quiet)
                enable_quiet_mode ;;
            -h|--help)
                show_help
                exit 0 ;;
            *)
                log WARN "Unknown option: $1"
                show_help
                exit 1 ;;
        esac
        shift
    done
}

# ------------------------------------------------------------------------------
# DASHBOARD SECTION HEADER
# ------------------------------------------------------------------------------
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    printf "\n%b%s%b\n" "${NORD10}" "$border" "${NC}"
    printf "%b  %s  %b\n" "${NORD10}" "$title" "${NC}"
    printf "%b%s%b\n" "${NORD10}" "$border" "${NC}\n"
}

# ------------------------------------------------------------------------------
# SYSTEM METRICS FUNCTIONS
# ------------------------------------------------------------------------------
get_uptime_info() {
    # Retrieve uptime and load average details
    local uptime_info
    uptime_info=$(uptime -p)
    local load_average
    load_average=$(uptime | awk -F'load average:' '{ print $2 }' | sed 's/^[ \t]*//')
    echo "$uptime_info | Load Average: $load_average"
}

get_cpu_usage() {
    # Parse CPU usage from top (non-interactive batch mode)
    local cpu_line
    cpu_line=$(top -bn1 | grep "Cpu(s)")
    # Calculate usage by subtracting idle percentage from 100
    local cpu_usage
    cpu_usage=$(echo "$cpu_line" | awk -F',' '{usage=100-$4; printf "%.1f%%", usage}')
    echo "$cpu_usage"
}

get_memory_usage() {
    # Extract memory usage from free command (human-readable)
    local mem_usage
    mem_usage=$(free -h | awk '/^Mem:/ {print $3 " / " $2 " used (" int($3/$2*100) "%)"}')
    echo "$mem_usage"
}

get_disk_usage() {
    # Get disk usage for root and /media/WD_BLACK
    local root_usage
    root_usage=$(df -h / | awk 'NR==2 {print $3 " / " $2 " (" $5 " used)"}')
    local wd_usage
    wd_usage=$(df -h /media/WD_BLACK 2>/dev/null | awk 'NR==2 {print $3 " / " $2 " (" $5 " used)"}')
    if [[ -z "$wd_usage" ]]; then
        wd_usage="Drive /media/WD_BLACK not found or inaccessible"
    fi
    echo "Root: $root_usage"
    echo "/media/WD_BLACK: $wd_usage"
}

get_network_activity() {
    # Use vnstat to capture current network activity (traffic in 1 second)
    local net_activity
    net_activity=$(vnstat -tr 1 2>/dev/null | grep -i "rx" | head -n 1)
    if [[ -z "$net_activity" ]]; then
        net_activity="Network activity data unavailable"
    fi
    echo "$net_activity"
}

get_process_info() {
    # Count the total number of running processes
    local proc_count
    proc_count=$(ps aux --no-heading | wc -l)
    echo "$proc_count processes running"
}

# ------------------------------------------------------------------------------
# DASHBOARD DISPLAY FUNCTION
# ------------------------------------------------------------------------------
print_dashboard() {
    clear
    # Header with system name, timestamp, and hostname
    printf "%b\n" "${NORD8}       SYSTEM MONITORING DASHBOARD       ${NC}"
    printf "%b%s%b\n" "${NORD8}" "$(date +"%Y-%m-%d %H:%M:%S")" "${NC}"
    printf "%b%s%b\n" "${NORD8}" "$(hostname)" "${NC}"
    printf "\n"

    # System Overview Section
    print_section "System Overview"
    printf "Uptime & Load: %s\n" "$(get_uptime_info)"
    printf "Processes: %s\n" "$(get_process_info)"
    printf "\n"

    # CPU Usage Section
    print_section "CPU Usage"
    printf "CPU Usage: %s\n" "$(get_cpu_usage)"
    printf "\n"

    # Memory Usage Section
    print_section "Memory Usage"
    printf "Memory: %s\n" "$(get_memory_usage)"
    printf "\n"

    # Disk Usage Section
    print_section "Disk Usage"
    printf "%s\n" "$(get_disk_usage)"
    printf "\n"

    # Network Activity Section
    print_section "Network Activity"
    printf "Traffic: %s\n" "$(get_network_activity)"
    printf "\n"
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    parse_args "$@"

    # Verify required commands exist
    local dependencies=("uptime" "top" "free" "df" "ps" "vnstat" "clear")
    for dep in "${dependencies[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            handle_error "Dependency '$dep' is not installed."
        fi
    done

    log INFO "Starting System Monitoring Dashboard..."

    # Continuous refresh loop for the dashboard
    while true; do
        print_dashboard
        sleep "$REFRESH_INTERVAL"
    done
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi