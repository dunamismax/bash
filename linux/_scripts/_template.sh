This template is designed so that every Bash script you write using it will be robust, visually appealing, and extremely user‑friendly.

Enhanced Prompt Instructions

	Objective:
Create Bash scripts following a consistent and modern style. Use this template as a starting point. The script uses the Nord color palette for all terminal output and detailed logging. It also includes progress bars to visually indicate the progress of tasks.

	Requirements:
		1.	Structure & Organization:
	•	Organize the script into clear sections: configuration, logging, helper functions, main logic, and cleanup.
	•	Use functions for modularity (e.g. logging, error handling, progress display).
	2.	Styling & Formatting:
	•	Follow consistent indentation, spacing, and naming conventions (snake_case for variables and functions; UPPERCASE for constants).
	•	Use descriptive comments and section headers.
	3.	Nord Color Theme:
	•	Integrate the Nord color palette (with 24‑bit ANSI escapes) to provide clear, colorful feedback.
	•	Assign distinct Nord colors to different log levels and UI elements (e.g. progress bars, section headers).
	4.	Progress Bars:
	•	Include a function that renders a smooth progress bar with color feedback for any long‑running tasks.
	5.	Error Handling & Cleanup:
	•	Trap errors and perform cleanup tasks before exit.

	Confirmation:
I confirm that this enhanced template’s style, structure, and features (including Nord-themed color feedback and progress bars) will be used as the standard for all future Bash scripting assistance.

Bash Script Template below:

#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: enhanced_script.sh
# Description: A robust and visually engaging Bash script template using the Nord
#              color theme. This template provides detailed logging, progress bars,
#              and strict error handling to serve as a foundation for all future scripts.
# Author: dunamismax | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   sudo ./enhanced_script.sh [-d|--debug] [-q|--quiet]
#   sudo ./enhanced_script.sh -h|--help
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored in /var/log/enhanced_script.log by default.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/enhanced_script.log"  # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"   # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
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

    # Only log DEBUG messages when LOG_LEVEL is DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    # Select color based on log level (if colors are enabled)
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
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., deleting temporary files)
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

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
  A robust and visually engaging Bash script template using the Nord color theme.
  It offers detailed logging, progress bars, and strict error handling.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output (logs still written to file).
  -h, --help    Show this help message and exit.

Examples:
  sudo $SCRIPT_NAME --debug
  sudo $SCRIPT_NAME --quiet
  sudo $SCRIPT_NAME -h
EOF
}

# Print a styled section header using Nord accent colors
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# ------------------------------------------------------------------------------
# PROGRESS BAR FUNCTION
# ------------------------------------------------------------------------------
progress_bar() {
    # Usage: progress_bar "Message" [duration_in_seconds]
    local message="${1:-Processing...}"
    local duration="${2:-5}"
    local steps=50
    local sleep_time
    sleep_time=$(echo "$duration / $steps" | bc -l)
    local progress=0
    local filled=""
    local unfilled=""

    # Display the task message in Nord accent color
    if [[ "$DISABLE_COLORS" != true ]]; then
        printf "\n${NORD8}%s${NC}\n" "$message"
    else
        printf "\n%s\n" "$message"
    fi

    for (( i = 1; i <= steps; i++ )); do
        progress=$(( i * 100 / steps ))
        filled=$(printf "%-${i}s" | tr ' ' '█')
        unfilled=$(printf "%-$(( steps - i ))s" | tr ' ' '░')
        printf "\r${NORD8}[%s%s] %3d%%%s" "$filled" "$unfilled" "$progress" "$NC"
        sleep "$sleep_time"
    done
    printf "\n"
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
    print_section "Starting Function One"
    log INFO "Executing function_one tasks..."
    # Simulate work with a progress bar (duration is adjustable)
    progress_bar "Function One in progress..." 3
    sleep 1  # Replace with actual work
    log INFO "function_one completed successfully."
}

function_two() {
    print_section "Starting Function Two"
    log INFO "Executing function_two tasks..."
    progress_bar "Function Two in progress..." 3
    sleep 1  # Replace with actual work
    log INFO "function_two completed successfully."
}

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--debug)
                enable_debug
                ;;
            -q|--quiet)
                enable_quiet_mode
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log WARN "Unknown option: $1"
                ;;
        esac
        shift
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists and the log file is secured
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."
    parse_args "$@"

    # Execute main functions
    function_one
    function_two

    log INFO "Script execution finished successfully."
}

# Invoke main() if this script is executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

Use this enhanced template as the starting point for all future Bash scripts. It enforces a high standard for error handling, logging, and user feedback while showcasing the elegant Nord color theme. Now ask the user what you can assist them with do not give any feedback or produce any code yet.