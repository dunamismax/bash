#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: cron_manager.sh
# Description: An advanced interactive cron job manager that lets you list,
#              add, edit, and remove cron jobs via a user‑friendly, Nord‑themed
#              interface. The tool walks you through common scheduling options,
#              validates input, and updates your crontab accordingly.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./cron_manager.sh
#
# Note:
#   After making changes, reload your shell (e.g., source ~/.bashrc) if needed.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="$HOME/.cron_manager.log"
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISABLE_COLORS="${DISABLE_COLORS:-false}"
# Global array to hold non‑comment cron jobs (for editing/removal)
declare -a CRON_JOBS=()

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9 (text)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'
NORD8='\033[38;2;136;192;208m'   # Accent Blue (headings)
NORD9='\033[38;2;129;161;193m'
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD12='\033[38;2;208;135;112m'  # Orange (warnings)
NORD13='\033[38;2;235;203;139m'
NORD14='\033[38;2;163;190;140m'  # Green (success/info)
NORD15='\033[38;2;180;142;173m'
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
    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Success/Info
            WARN)  color="${NORD13}" ;;  # Warning
            ERROR) color="${NORD11}" ;;  # Error
            DEBUG) color="${NORD9}"  ;;  # Debug
            *)     color="$NC"       ;;
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
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # (Temporary files created within functions are removed after use.)
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
print_header() {
    clear
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
    printf "%b              Advanced Cron Manager                     %b\n" "${NORD8}" "${NC}"
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
}

# Basic validation: Check that the cron expression has exactly 5 fields.
validate_cron_expr() {
    local expr="$1"
    # Remove extra whitespace and split into fields.
    local fields
    fields=($(echo "$expr" | xargs))
    if [ "${#fields[@]}" -ne 5 ]; then
        return 1
    fi
    return 0
}

# ------------------------------------------------------------------------------
# FUNCTION: List Current Cron Jobs
# ------------------------------------------------------------------------------
list_cron_jobs() {
    CRON_JOBS=()  # Reset global array
    local cron_output
    cron_output=$(crontab -l 2>/dev/null || true)
    if [[ -z "$cron_output" ]]; then
        echo -e "${NORD12}No cron jobs found for user ${USER}.${NC}"
        return 1
    fi
    echo -e "${NORD14}Current Cron Jobs:${NC}"
    printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
    local counter=0
    while IFS= read -r line; do
        # Skip blank lines and comments.
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        ((counter++))
        CRON_JOBS+=("$line")
        printf "%b[%d]${NC} %b%s${NC}\n" "${NORD8}" "$counter" "${NORD4}" "$line"
    done <<< "$cron_output"
    printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
    return 0
}

# ------------------------------------------------------------------------------
# FUNCTION: Update Crontab from a Temporary File
# ------------------------------------------------------------------------------
update_crontab() {
    if crontab "$1"; then
        log INFO "Crontab updated successfully."
        echo -e "${NORD14}Crontab updated successfully.${NC}"
    else
        log ERROR "Failed to update crontab."
        echo -e "${NORD11}Failed to update crontab. Restoring previous settings.${NC}"
        return 1
    fi
}

# ------------------------------------------------------------------------------
# FUNCTION: Add a New Cron Job
# ------------------------------------------------------------------------------
add_cron_job() {
    echo -e "${NORD14}Select a schedule type:${NC}"
    echo -e "${NORD8}[1]${NC} Every minute"
    echo -e "${NORD8}[2]${NC} Every hour"
    echo -e "${NORD8}[3]${NC} Daily at specific time"
    echo -e "${NORD8}[4]${NC} Weekly at specific time"
    echo -e "${NORD8}[5]${NC} Monthly at specific time"
    echo -e "${NORD8}[6]${NC} Custom schedule"
    read -rp "Enter your choice (1-6): " sched_choice

    local cron_expr=""
    case "$sched_choice" in
        1)
            cron_expr="* * * * *"
            ;;
        2)
            cron_expr="0 * * * *"
            ;;
        3)
            read -rp "Enter time in HH:MM (24-hour format): " time_input
            IFS=: read hour minute <<< "$time_input"
            cron_expr="${minute:-0} ${hour:-0} * * *"
            ;;
        4)
            read -rp "Enter day of week (0-6, Sunday=0): " dow
            read -rp "Enter time in HH:MM (24-hour format): " time_input
            IFS=: read hour minute <<< "$time_input"
            cron_expr="${minute:-0} ${hour:-0} * * ${dow:-0}"
            ;;
        5)
            read -rp "Enter day of month (1-31): " dom
            read -rp "Enter time in HH:MM (24-hour format): " time_input
            IFS=: read hour minute <<< "$time_input"
            cron_expr="${minute:-0} ${hour:-0} ${dom:-1} * *"
            ;;
        6)
            read -rp "Enter custom cron expression (5 fields): " cron_expr
            if ! validate_cron_expr "$cron_expr"; then
                echo -e "${NORD11}Invalid cron expression. Must contain exactly 5 fields.${NC}"
                return 1
            fi
            ;;
        *)
            echo -e "${NORD12}Invalid selection.${NC}"
            return 1
            ;;
    esac

    read -rp "Enter the command to run: " job_command
    if [[ -z "$job_command" ]]; then
        echo -e "${NORD12}Command cannot be empty.${NC}"
        return 1
    fi

    local new_job="${cron_expr} ${job_command}"
    echo -e "${NORD14}New Cron Job:${NC} ${NORD4}${new_job}${NC}"
    read -rp "Confirm adding this job? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${NORD12}Operation cancelled.${NC}"
        return 1
    fi

    local tmpfile
    tmpfile=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true
    echo "$new_job" >> "$tmpfile"
    if update_crontab "$tmpfile"; then
        echo -e "${NORD14}New cron job added successfully.${NC}"
        log INFO "New cron job added: $new_job"
    else
        echo -e "${NORD11}Failed to add new cron job.${NC}"
    fi
    rm "$tmpfile"
}

# ------------------------------------------------------------------------------
# FUNCTION: Edit an Existing Cron Job
# ------------------------------------------------------------------------------
edit_cron_job() {
    if ! list_cron_jobs; then
        return 1
    fi
    read -rp "Enter the number of the cron job to edit (or 'b' to go back): " choice
    if [[ "$choice" == "b" ]]; then
        return 0
    fi
    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local idx=$((choice - 1))
    if (( idx < 0 || idx >= ${#CRON_JOBS[@]} )); then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi

    local selected_job="${CRON_JOBS[$idx]}"
    echo -e "${NORD14}Current Cron Job:${NC} ${NORD4}${selected_job}${NC}"
    echo -e "${NORD14}Enter new schedule and command for this job.${NC}"
    echo -e "${NORD14}Note: Provide a full cron expression (5 fields) followed by the command.${NC}"
    read -rp "New cron job line: " new_line
    if [[ -z "$new_line" ]]; then
        echo -e "${NORD12}Edit cancelled.${NC}"
        return 1
    fi
    # Validate the cron expression portion (first 5 fields).
    local new_cron_expr
    new_cron_expr=$(echo "$new_line" | awk '{print $1, $2, $3, $4, $5}')
    if ! validate_cron_expr "$new_cron_expr"; then
        echo -e "${NORD11}Invalid cron expression in new job.${NC}"
        return 1
    fi

    # Load the current crontab into a temporary file.
    local tmpfile new_tmp
    tmpfile=$(mktemp)
    new_tmp=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true

    # Replace the nth non-comment, non-blank line with the new_line.
    local non_comment_index=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            echo "$line" >> "$new_tmp"
        else
            ((non_comment_index++))
            if (( non_comment_index == choice )); then
                echo "$new_line" >> "$new_tmp"
            else
                echo "$line" >> "$new_tmp"
            fi
        fi
    done < "$tmpfile"

    if update_crontab "$new_tmp"; then
        echo -e "${NORD14}Cron job updated successfully.${NC}"
        log INFO "Cron job edited: Old: ${selected_job} New: ${new_line}"
    else
        echo -e "${NORD11}Failed to update cron job.${NC}"
    fi
    rm "$tmpfile" "$new_tmp"
}

# ------------------------------------------------------------------------------
# FUNCTION: Remove an Existing Cron Job
# ------------------------------------------------------------------------------
remove_cron_job() {
    if ! list_cron_jobs; then
        return 1
    fi
    read -rp "Enter the number of the cron job to remove (or 'b' to go back): " choice
    if [[ "$choice" == "b" ]]; then
        return 0
    fi
    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    read -rp "Are you sure you want to delete job number $choice? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${NORD12}Deletion cancelled.${NC}"
        return 0
    fi

    local tmpfile new_tmp
    tmpfile=$(mktemp)
    new_tmp=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true

    local non_comment_index=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            echo "$line" >> "$new_tmp"
        else
            ((non_comment_index++))
            if (( non_comment_index == choice )); then
                continue
            else
                echo "$line" >> "$new_tmp"
            fi
        fi
    done < "$tmpfile"

    if update_crontab "$new_tmp"; then
        echo -e "${NORD14}Cron job removed successfully.${NC}"
        log INFO "Cron job number $choice removed."
    else
        echo -e "${NORD11}Failed to remove cron job.${NC}"
    fi
    rm "$tmpfile" "$new_tmp"
}

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Advanced Cron Job Manager:${NC}"
        echo -e "${NORD8}[1]${NC} List Cron Jobs"
        echo -e "${NORD8}[2]${NC} Add New Cron Job"
        echo -e "${NORD8}[3]${NC} Edit Existing Cron Job"
        echo -e "${NORD8}[4]${NC} Remove Cron Job"
        echo -e "${NORD8}[q]${NC} Quit"
        printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                list_cron_jobs
                read -rp "Press Enter to continue..." dummy
                ;;
            2)
                add_cron_job
                read -rp "Press Enter to continue..." dummy
                ;;
            3)
                edit_cron_job
                read -rp "Press Enter to continue..." dummy
                ;;
            4)
                remove_cron_job
                read -rp "Press Enter to continue..." dummy
                ;;
            q)
                echo -e "${NORD14}Goodbye!${NC}"
                log INFO "Cron Manager terminated by user."
                exit 0
                ;;
            *)
                echo -e "${NORD12}Invalid selection. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    main_menu
}

# Invoke main() if this script is executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi