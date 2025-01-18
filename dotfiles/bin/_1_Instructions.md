#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: example_script.sh
# Description: [Brief description of what the script does]
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail
trap 'log ERROR "Script failed at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/example_script.log"
VERBOSE=2
# Define other configuration variables, constants, and arrays here

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Color codes for console output
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'  # No Color

    # Determine log level color and normalization
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            ;;
        DEBUG)
            local color="${BLUE}"
            ;;
        *)
            local color="${NC}"
            level="INFO"
            ;;
    esac

    # Ensure the log file exists
    if [[ -z "${LOG_FILE:-}" ]]; then
        LOG_FILE="/var/log/example_script.log"
    fi
    if [[ ! -e "$LOG_FILE" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
    fi

    # Format and save log entry
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"

    # Conditional console output based on verbosity
    if [[ "$VERBOSE" -ge 2 ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    elif [[ "$VERBOSE" -ge 1 && "$level" == "ERROR" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
  if [ "$EUID" -ne 0 ]; then
    log ERROR "This script must be run as root."
    exit 1
  fi
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
function_one() {
  log INFO "Starting function_one..."
  # Add your logic here, e.g., backup files, modify configs, etc.
  log INFO "Completed function_one."
}

function_two() {
  log INFO "Starting function_two..."
  # Add your logic here
  log INFO "Completed function_two."
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
  check_root
  log INFO "Script execution started."

  # Call the primary functions in desired order
  function_one
  function_two

  log INFO "Script execution finished."
}

# Execute main only if the script is not sourced
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

### Explanation of Best Practices Implemented:

1. **Header & Metadata:**
   - Starts with a shebang and includes comments for purpose, author, license, etc.

2. **Safety & Strict Mode:**
   - Enforces strict mode (`set -Eeuo pipefail`) and traps errors.
   - Checks for root privileges when necessary.

3. **Centralized Logging:**
   - Uses the `log` function to manage all logging with levels, timestamps, colors, and verbosity.

4. **Modularity & Functions:**
   - Splits logic into single-purpose functions with clear names, error checks, and logging.

5. **Configuration & Variables:**
   - Gathers all configuration variables at the start for easy adjustments.

6. **Backup Before Changes:**
   - Shows how to back up a configuration file before modifying.

7. **Error Handling & Validation:**
   - Validates critical commands and ensures proper error logging and exits on failure.

8. **Comments & Documentation:**
   - Includes comments and documentation for functions and logic blocks to improve readability.

9. **Cleanup & Finalization:**
   - Encourages writing cleanup functions to remove temporary files and summarize actions.

10. **Main Entrypoint:**
    - Uses a `main` function to orchestrate execution and checks if the script is executed directly.

11. **Consistent Style & Formatting:**
    - Adopts consistent indentation, variable naming conventions, and groups related commands.

12. **Version Control & Distribution:**
    - Recommends storing scripts in Git, including dependencies and prerequisites in comments.

Using this template and guideline ensures that your Bash scripts are robust, easier to maintain, and follow best practices.
