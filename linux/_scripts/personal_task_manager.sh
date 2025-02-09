#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: personal_task_manager.sh
# Description: A simple command‑line task manager to add, view, edit, delete, and
#              complete to‑do items. Tasks are stored in a text file and operations
#              are performed using grep, sed, and awk. The output is styled with
#              the elegant Nord color theme.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   ./personal_task_manager.sh add "Buy milk"
#   ./personal_task_manager.sh list
#   ./personal_task_manager.sh complete 1
#   ./personal_task_manager.sh delete 2
#   ./personal_task_manager.sh edit 3 "Buy almond milk"
#   ./personal_task_manager.sh -h|--help
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
TASK_DIR="${HOME}/.task_manager"
TASK_FILE="${TASK_DIR}/tasks.txt"
LOG_FILE="${TASK_DIR}/task_manager.log"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
QUIET_MODE=false
DISABLE_COLORS="${DISABLE_COLORS:-false}"

# Ensure the task directory exists
mkdir -p "$TASK_DIR"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (for completed tasks)
NORD8='\033[38;2;136;192;208m'
NORD9='\033[38;2;129;161;193m'
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Red (for errors)
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'  # Yellow (for pending tasks)
NORD14='\033[38;2;163;190;140m'  # Green (for info)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
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
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Info: green
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD13}" ;;      # Warn: yellow
            ERROR) color="${NORD11}" ;;     # Error: red
            DEBUG) color="${NORD9}"  ;;     # Debug: blue
            *)     color="$NC"     ;;
        esac
    fi

    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    if [[ "$QUIET_MODE" != true ]]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# USAGE FUNCTION
# ------------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $0 [COMMAND] [OPTIONS]

Commands:
  add "task description"     Add a new task.
  list                       List all tasks.
  complete <task_id>         Mark a task as completed.
  delete <task_id>           Delete a task.
  edit <task_id> "new text"  Edit the description of a task.
  -h, --help                Display this help message.

Examples:
  $0 add "Buy milk"
  $0 list
  $0 complete 3
  $0 delete 2
  $0 edit 4 "Buy almond milk"

EOF
    exit 0
}

# ------------------------------------------------------------------------------
# TASK FILE INITIALIZATION
# ------------------------------------------------------------------------------
init_task_file() {
    if [[ ! -f "$TASK_FILE" ]]; then
        touch "$TASK_FILE" || handle_error "Failed to create task file: $TASK_FILE"
        chmod 600 "$TASK_FILE"
        log INFO "Task file created at $TASK_FILE"
    fi
}

# ------------------------------------------------------------------------------
# TASK MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
add_task() {
    local description="$*"
    if [[ -z "$description" ]]; then
        handle_error "Task description cannot be empty."
    fi

    # Determine the next task ID
    local next_id
    if [[ ! -s "$TASK_FILE" ]]; then
        next_id=1
    else
        next_id=$(awk -F'|' 'BEGIN {max=0} {if ($1>max) max=$1} END {print max+1}' "$TASK_FILE")
    fi

    echo "${next_id}|pending|${description}" >> "$TASK_FILE" || handle_error "Failed to add task."
    log INFO "Task added with ID $next_id"
}

list_tasks() {
    if [[ ! -s "$TASK_FILE" ]]; then
        echo -e "${NORD13}No tasks found.${NC}"
        return
    fi

    printf "\n%b%-5s %-10s %s%b\n" "${NORD8}" "ID" "Status" "Description" "${NC}"
    printf "%b%s%b\n" "${NORD8}" "----------------------------------------" "${NC}"

    while IFS='|' read -r id status description; do
        local status_color="$NORD13"  # pending: yellow
        if [[ "$status" == "done" ]]; then
            status_color="$NORD7"       # done: teal/green
        fi
        printf "%-5s %-10b %-s\n" "$id" "${status_color}$status${NC}" "$description"
    done < "$TASK_FILE"
    echo ""
}

complete_task() {
    local task_id="$1"
    if ! grep -q "^${task_id}|" "$TASK_FILE"; then
        handle_error "Task with ID $task_id does not exist."
    fi

    if grep -q "^${task_id}|done|" "$TASK_FILE"; then
        log WARN "Task $task_id is already marked as completed."
        return
    fi

    # Use sed to update the status field to "done"
    sed -i -E "s/^(${task_id})\|pending\|/\1|done|/" "$TASK_FILE" || handle_error "Failed to mark task as complete."
    log INFO "Task $task_id marked as complete."
}

delete_task() {
    local task_id="$1"
    if ! grep -q "^${task_id}|" "$TASK_FILE"; then
        handle_error "Task with ID $task_id does not exist."
    fi

    sed -i -E "/^${task_id}\|/d" "$TASK_FILE" || handle_error "Failed to delete task."
    log INFO "Task $task_id deleted."
}

edit_task() {
    local task_id="$1"
    shift
    local new_description="$*"
    if [[ -z "$new_description" ]]; then
        handle_error "New task description cannot be empty."
    fi

    if ! grep -q "^${task_id}|" "$TASK_FILE"; then
        handle_error "Task with ID $task_id does not exist."
    fi

    # Update the description while preserving ID and status.
    sed -i -E "s/^(${task_id}\|[^|]+\|).*/\1${new_description}/" "$TASK_FILE" || handle_error "Failed to edit task."
    log INFO "Task $task_id updated."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ $# -eq 0 ]]; then
        usage
    fi

    init_task_file

    local command="$1"
    shift

    case "$command" in
        add)
            add_task "$@"
            ;;
        list)
            list_tasks
            ;;
        complete)
            if [[ $# -ne 1 ]]; then
                handle_error "Usage: $0 complete <task_id>"
            fi
            complete_task "$1"
            ;;
        delete)
            if [[ $# -ne 1 ]]; then
                handle_error "Usage: $0 delete <task_id>"
            fi
            delete_task "$1"
            ;;
        edit)
            if [[ $# -lt 2 ]]; then
                handle_error "Usage: $0 edit <task_id> \"new task description\""
            fi
            edit_task "$@"
            ;;
        -h|--help)
            usage
            ;;
        *)
            usage
            ;;
    esac
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi