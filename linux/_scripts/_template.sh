Hello! I would like you to assist me with Bash scripting by following a specific style and structure. Below, I will provide you with a template Bash script. Please perform the following tasks:

1. **Analyze the Script:**
   - **Structure & Organization:** Examine how the script is organized, including the order of functions, main execution flow, and any modular components.
   - **Layout & Formatting:** Note the indentation style, line spacing, and overall readability.
   - **Naming Conventions:** Observe how variables, functions, and constants are named (e.g., snake_case, UPPERCASE).
   - **Commenting Style:** Pay attention to how comments are written, their placement, and the level of detail provided.
   - **Error Handling:** Look at how the script handles errors and exceptions.
   - **Best Practices:** Identify any best practices or patterns used in the script.

2. **Adopt the Style:**
   - **Consistency:** Ensure that all future Bash scripts you help me create follow the same structural and stylistic guidelines identified in the template.
   - **Customization:** If there are any specific preferences or unique styles in the template, make sure to incorporate them consistently.
   - **Flexibility:** While maintaining the established style, adapt to any specific requirements I might mention for individual scripts.

3. **Confirmation:**
   - After analyzing the script, please confirm that you have understood and will adhere to its structure, layout, and style in all future Bash scripting assistance.

**Here is the template Bash script:**

#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: example_script.sh
# Description: [Brief description of what the script does]
# Author: Your Name | License: MIT
# Version: 1.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   sudo ./example_script.sh [-d|--debug] [-q|--quiet]
#   sudo ./example_script.sh -h|--help
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored in /var/log/example_script.log by default.
#
# ------------------------------------------------------------------------------
# Enable strict mode (exit on error, unset variable usage, pipeline errors)
# For more information, see:
#   https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES (CONFIGURATION)
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/example_script.log"  # Path to the log file
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# You can set LOG_LEVEL to control the verbosity of logs:
#   INFO, DEBUG, WARN, ERROR (default: INFO)
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# When QUIET_MODE=true, no console output will be shown (logs still go to file)
QUIET_MODE=false

# ------------------------------------------------------------------------------
# COLOR CONSTANTS (Used for Logging)
# ------------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# If you wish to disable colors entirely, set DISABLE_COLORS=true
DISABLE_COLORS="${DISABLE_COLORS:-false}"

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage:
    #   log [LEVEL] message
    # Example:
    #   log INFO "This is an informational message."
    #
    # LOG_LEVEL environment variable determines whether DEBUG messages are shown.

    local level="${1:-INFO}"
    shift
    local message="$*"

    # Convert level to uppercase for consistency
    local upper_level
    upper_level="${level^^}"

    # Compare levels (basic approach: only logs DEBUG if LOG_LEVEL is DEBUG)
    # If needed, you can expand to allow numeric priority checks.
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        # If script is not in debug mode, ignore debug messages
        return 0
    fi

    # Determine the correct color based on the log level
    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="$GREEN"  ;;
            WARN)  color="$YELLOW" ;;
            ERROR) color="$RED"    ;;
            DEBUG) color="$BLUE"   ;;
            *)     color="$NC"     ;;
        esac
    fi

    # Timestamp for log entry
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"

    # Final log entry format
    local log_entry="[$timestamp] [$upper_level] $message"

    # Always append to the log file (uncolored)
    echo "$log_entry" >> "$LOG_FILE"

    # Only print to console if QUIET_MODE is false
    if [[ "$QUIET_MODE" != true ]]; then
        # Print in color (if colors are enabled)
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"

    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

    # Print error to stderr for immediate visibility
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2

    exit "$exit_code"
}

# Trap any uncaught errors and call handle_error
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    # Ensure the script is run as root; otherwise, exit
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

enable_debug() {
    # Turn on debug-level logging
    LOG_LEVEL="DEBUG"
    log DEBUG "Debug mode enabled: Verbose logging turned on."
}

enable_quiet_mode() {
    # Suppress console output; logs still go to file
    QUIET_MODE=true
    log INFO "Quiet mode enabled: Console output suppressed."
}

# ------------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
show_help() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Description:
  [Provide a more detailed description of what the script does here.]

Options:
  -d, --debug   Enable debug (verbose) logging
  -q, --quiet   Suppress console output (logs still written to file)
  -h, --help    Show this help message and exit

Examples:
  sudo $SCRIPT_NAME --debug
  sudo $SCRIPT_NAME --quiet
  sudo $SCRIPT_NAME -h
EOF
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
    log INFO "--------------------------------------"
    log INFO "Starting function_one..."
    # TODO: Add function_one logic here
    sleep 1  # Placeholder for actual work
    log INFO "Completed function_one."
    log INFO "--------------------------------------"
}

function_two() {
    log INFO "--------------------------------------"
    log INFO "Starting function_two..."
    # TODO: Add function_two logic here
    sleep 1  # Placeholder for actual work
    log INFO "Completed function_two."
    log INFO "--------------------------------------"
}

# ------------------------------------------------------------------------------
# ARGUMENT PARSING
# ------------------------------------------------------------------------------
parse_args() {
    # Parse command-line arguments; if none are provided, defaults apply
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
    # 1. Check if the script is running under bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo "ERROR: Please run this script with bash, not sh or another shell." >&2
        exit 1
    fi

    # 2. Check if root privileges are required
    check_root

    # 3. Prepare the log directory and file
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"

    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi

    # If the log file doesn't exist, create it; then set secure permissions
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # 4. Parse script arguments
    parse_args "$@"

    # 5. Execute main logic
    function_one
    function_two

    # 6. Final message
    log INFO "Script execution finished."
}

# ------------------------------------------------------------------------------
# INVOKE MAIN IF RUNNING AS PRIMARY SCRIPT
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
