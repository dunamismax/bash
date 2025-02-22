# AI Prompt for Ubuntu Bash Script Generation

This enhanced prompt instructs you to generate Ubuntu Bash scripts that are robust, visually appealing, and extremely user‑friendly by following a standardized template. The template uses the Nord color palette for all terminal output, detailed logging with log-level filtering, strict error handling, and graceful signal traps.

---

## Enhanced Prompt Instructions

### Objective

Create Ubuntu Bash scripts using a consistent and modern style. Use the provided template as the foundation. The script must:

- Utilize the Nord color palette for clear, colorful feedback.
- Include detailed logging with log-level filtering.
- Employ strict error handling and proper cleanup.

### Requirements

1. **Structure & Organization**
   - **Sections:** Organize the script into clear sections for configuration, logging, helper functions, main logic, and cleanup.
   - **Modularity:** Use functions (e.g., for logging and error handling) to promote modularity.

2. **Styling & Formatting**
   - **Indentation & Spacing:** Follow consistent indentation and spacing throughout the script.
   - **Naming Conventions:** Use `snake_case` for variables and function names, and `UPPERCASE` for constants.
   - **Comments:** Include descriptive comments and clear section headers to document each part of the script.

3. **Nord Color Theme**
   - **Color Integration:** Integrate the Nord color palette (using 24‑bit ANSI escape sequences) to provide visually engaging output.
   - **Log Levels & UI Elements:** Assign distinct Nord colors to different log levels (e.g., DEBUG, INFO, WARN, ERROR, CRITICAL) and to UI elements such as section headers.

4. **Error Handling & Cleanup**
   - **Signal Traps:** Trap errors and signals to handle unexpected issues gracefully.
   - **Cleanup Tasks:** Ensure that cleanup tasks are performed before the script exits.

### Confirmation

I confirm that the enhanced template’s style, structure, and features—including the Nord-themed color feedback—will serve as the standard for all future Bash scripting assistance.

---

## Ubuntu Bash Script Template

Use the following template as the foundation for your Bash scripts. **Do not change any part of this template.**

```bash
#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: ultimate_script.sh
# Description: A robust, visually engaging Bash script template using the Nord
#              color theme, with strict error handling, log-level filtering,
#              colorized output, and graceful signal traps.
# Author: YourName | License: MIT | Version: 3.2
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
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels (case-insensitive): VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"
# Users can override via environment variable LOG_LEVEL.

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'   # Bluish (for DEBUG)
readonly NORD10='\033[38;2;94;129;172m'   # Accent Blue
readonly NORD11='\033[38;2;191;97;106m'   # Reddish (for ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'  # Yellowish (for WARN)
readonly NORD14='\033[38;2;163;190;140m'  # Greenish (for INFO)
readonly NC='\033[0m'                     # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
# Converts log level string to a numeric value.
get_log_level_num() {
    local lvl="${1^^}"  # uppercase
    case "$lvl" in
        VERBOSE|V)    echo 0 ;;
        DEBUG|D)      echo 1 ;;
        INFO|I)       echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)      echo 4 ;;
        CRITICAL|C)   echo 5 ;;
        *)            echo 2 ;;  # default to INFO if unknown
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL message
# Example: log INFO "Starting process..."
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"

    # Determine numeric log level of this message and current threshold.
    local msg_level
    msg_level=$(get_log_level_num "$upper_level")
    local current_level
    current_level=$(get_log_level_num "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}")
    if (( msg_level < current_level )); then
        return 0  # Skip messages below current log threshold.
    fi

    # Choose color (only for interactive stderr output).
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

    # Append plain log entry to log file (no color codes)
    echo "$log_entry" >> "$LOG_FILE"
    # Print colorized log entry to stderr
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
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

# Trap signals and errors for graceful handling
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
    # Ensure the script is run with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists; create if missing.
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi

    # Ensure the log file exists and set secure permissions.
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    # Execute main functions.
    function_one
    function_two

    log INFO "Script execution finished successfully."
}

# Invoke main() if the script is executed directly.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
```

---

## Final Instruction

Use this refined template as the foundation for all future Bash scripts. It establishes a robust standard for error handling, logging, and user feedback while showcasing the elegant Nord color theme.

Before generating any code, please ask the user what further assistance they require. **Do not provide any additional feedback or produce any code yet.**
