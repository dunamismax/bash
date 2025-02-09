#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: cron_manager.sh
# Description: An advanced interactive cron job manager that lets you list,
#              add, edit, and remove cron jobs via a user‐friendly, Nord‑themed
#              interface. The tool walks you through common scheduling options,
#              validates input, and updates your crontab accordingly.
#
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./advanced_cron_manager.sh
#
# Note:
#   After making changes, reload your shell (e.g., source ~/.bashrc) if needed.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'echo -e "\n${NORD11}An unexpected error occurred at line $LINENO.${NC}" >&2; exit 1' ERR

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD8='\033[38;2;136;192;208m'   # Accent Blue (headings)
NORD14='\033[38;2;163;190;140m'  # Green (success/info)
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD12='\033[38;2;208;135;112m'  # Orange (warnings)
NORD4='\033[38;2;216;222;233m'   # Light gray (text)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------------
CRON_FILE_TEMP="$(mktemp)"
BASHRC_FILE="$HOME/.bashrc"
# (The script manages the current user's crontab.)
# No special marker for cron jobs is needed here.

# ------------------------------------------------------------------------------
# Helper Function: Print Header
# ------------------------------------------------------------------------------
print_header() {
    clear
    echo -e "${NORD8}============================================${NC}"
    echo -e "${NORD8}         Advanced Cron Manager            ${NC}"
    echo -e "${NORD8}============================================${NC}"
}

# ------------------------------------------------------------------------------
# Helper Function: Validate a Cron Expression (basic check for 5 fields)
# ------------------------------------------------------------------------------
validate_cron_expr() {
    local expr="$1"
    # Remove extra whitespace and split into fields
    local fields
    fields=($(echo "$expr" | xargs))
    if [ "${#fields[@]}" -ne 5 ]; then
        return 1
    fi
    return 0
}

# ------------------------------------------------------------------------------
# Function: List Current Cron Jobs
# ------------------------------------------------------------------------------
list_cron_jobs() {
    local cron_output
    cron_output=$(crontab -l 2>/dev/null || echo "")
    if [[ -z "$cron_output" ]]; then
        echo -e "${NORD12}No cron jobs found for user $USER.${NC}"
        return 1
    fi
    echo -e "${NORD14}Current Cron Jobs:${NC}"
    echo -e "${NORD8}--------------------------------------------${NC}"
    local i=1
    while IFS= read -r line; do
        # Ignore blank lines and comments.
        if [[ -z "$line" || "$line" =~ ^# ]]; then
            continue
        fi
        printf "${NORD8}[%d]${NC} ${NORD4}%s${NC}\n" "$i" "$line"
        cron_jobs_array[i]="$line"
        ((i++))
    done <<< "$cron_output"
    echo -e "${NORD8}--------------------------------------------${NC}"
    return 0
}

# ------------------------------------------------------------------------------
# Function: Update Crontab from a Temporary File
# ------------------------------------------------------------------------------
update_crontab() {
    if crontab "$1"; then
        echo -e "${NORD14}Crontab updated successfully.${NC}"
    else
        echo -e "${NORD11}Failed to update crontab. Restoring previous settings.${NC}"
        return 1
    fi
}

# ------------------------------------------------------------------------------
# Function: Add a New Cron Job
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

    # Save current crontab to a temp file (if none exists, create empty file)
    local tmpfile
    tmpfile=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true
    echo "$new_job" >> "$tmpfile"
    if update_crontab "$tmpfile"; then
        echo -e "${NORD14}New cron job added successfully.${NC}"
    else
        echo -e "${NORD11}Failed to add new cron job.${NC}"
    fi
    rm "$tmpfile"
}

# ------------------------------------------------------------------------------
# Function: Edit an Existing Cron Job
# ------------------------------------------------------------------------------
edit_cron_job() {
    local cron_jobs_array=()
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

    # Get the selected cron job from the temporary file.
    local selected_line
    selected_line=$(sed -n "${choice}p" "$ALIAS_TEMP_FILE" 2>/dev/null || true)
    # If ALIAS_TEMP_FILE is not available, re-read crontab.
    if [[ -z "$selected_line" ]]; then
        selected_line=$(crontab -l | sed -n "${choice}p")
    fi

    echo -e "${NORD14}Current Cron Job:${NC} ${NORD4}${selected_line}${NC}"
    echo -e "${NORD14}Enter new schedule and command for this job.${NC}"
    echo -e "${NORD14}Note: Provide a full cron expression (5 fields) followed by the command.${NC}"
    read -rp "New cron job line: " new_line
    if [[ -z "$new_line" ]]; then
        echo -e "${NORD12}Edit cancelled.${NC}"
        return 1
    fi
    if ! validate_cron_expr "$(echo "$new_line" | awk '{print $1,$2,$3,$4,$5}')"; then
        echo -e "${NORD11}Invalid cron expression in new job.${NC}"
        return 1
    fi

    # Save current crontab to a temp file
    local tmpfile
    tmpfile=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true

    # Replace the selected line with the new line.
    sed -i "${choice}s/.*/$new_line/" "$tmpfile"
    if update_crontab "$tmpfile"; then
        echo -e "${NORD14}Cron job updated successfully.${NC}"
    else
        echo -e "${NORD11}Failed to update cron job.${NC}"
    fi
    rm "$tmpfile"
}

# ------------------------------------------------------------------------------
# Function: Remove an Existing Cron Job
# ------------------------------------------------------------------------------
remove_cron_job() {
    local cron_jobs_array=()
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

    local tmpfile
    tmpfile=$(mktemp)
    crontab -l 2>/dev/null > "$tmpfile" || true
    # Remove the chosen line from the temporary crontab file.
    sed -i "${choice}d" "$tmpfile"
    if update_crontab "$tmpfile"; then
        echo -e "${NORD14}Cron job removed successfully.${NC}"
    else
        echo -e "${NORD11}Failed to remove cron job.${NC}"
    fi
    rm "$tmpfile"
}

# ------------------------------------------------------------------------------
# Main Interactive Menu
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
        echo -e "${NORD8}--------------------------------------------${NC}"
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
# Script Entry Point
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main_menu
fi