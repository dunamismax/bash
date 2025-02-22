This template is designed so that every Bash script you write using it will be robust, visually appealing, and extremely user‑friendly.

────────────────────────────────────────────
Enhanced Prompt Instructions

Objective:
Create Ubuntu Bash scripts following a consistent and modern style. Use this template as a starting point. The script uses the Nord color palette for all terminal output and detailed logging.

Requirements:
	1.	Structure & Organization:
	•	Organize the script into clear sections: configuration, logging, helper functions, main logic, and cleanup.
	•	Use functions for modularity (e.g., logging, error handling).
	2.	Styling & Formatting:
	•	Follow consistent indentation, spacing, and naming conventions (snake_case for variables and functions; UPPERCASE for constants).
	•	Use descriptive comments and section headers.
	3.	Nord Color Theme:
	•	Integrate the Nord color palette (with 24‑bit ANSI escapes) to provide clear, colorful feedback.
	•	Assign distinct Nord colors to different log levels and UI elements (e.g., section headers).
	4.	Error Handling & Cleanup:
	•	Trap errors and perform cleanup tasks before exit.

Confirmation:
I confirm that this enhanced template’s style, structure, and features (including Nord-themed color feedback) will be used as the standard for all future Bash scripting assistance.

Ubuntu Bash Script Template below:

#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: ultimate_script.sh
# Description: A robust, visually engaging Bash script template using the Nord
#              color theme, optimized for Ubuntu Linux. This template includes
#              detailed logging, strict error handling, and graceful signal traps.
# Author: YourName | License: MIT | Version: 3.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./ultimate_script.sh
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/ultimate_script.log by default.
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
readonly LOG_FILE="/var/log/ultimate_script.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'   # #81A1C1 (Bluish)
readonly NORD10='\033[38;2;94;129;172m'   # #5E81AC
readonly NORD11='\033[38;2;191;97;106m'   # #BF616A (Reddish)
readonly NORD13='\033[38;2;235;203;139m'  # #EBCB8B (Yellowish)
readonly NORD14='\033[38;2;163;190;140m'  # #A3BE8C (Greenish)
readonly NC='\033[0m'                     # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="${NC}"

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
            *)     color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    # Append log entry to log file
    echo "$log_entry" >> "$LOG_FILE"
    # Output colored log entry to stderr
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An unknown error occurred"}"
    local exit_code="${2:-1}"
    # Using BASH_LINENO for more precise error location
    local lineno="${BASH_LINENO[0]:-${LINENO}}"
    local func="${FUNCNAME[1]:-main}"

    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Error in function '$func' at line $lineno."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

# Trap EXIT for cleanup and signals for graceful error handling
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

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
    print_section "Starting Function One"
    log INFO "Executing tasks in function_one..."
    sleep 1  # Replace with actual work
    log INFO "function_one completed successfully."
}

function_two() {
    print_section "Starting Function Two"
    log INFO "Executing tasks in function_two..."
    sleep 1  # Replace with actual work
    log INFO "function_two completed successfully."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists; create if missing
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi

    # Ensure the log file exists and set secure permissions
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Execute main functions
    function_one
    function_two

    log INFO "Script execution finished successfully."
}

# Invoke main() if this script is executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

Use this refined template as the foundation for all future Bash scripts. It establishes a robust standard for error handling, logging, and user feedback while showcasing the elegant Nord color theme. Now ask the user what further assistance they require—do not provide any feedback or produce any code yet.