#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: pomodoro_timer.sh
# Description: An advanced, interactive Pomodoro timer for managing work and break
#              intervals to boost productivity. The script features customizable
#              session lengths, cycle counts, and provides both visual and audible
#              notifications using the Nord color theme.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./pomodoro_timer.sh
#
# Requirements:
#   • Bash, sleep, date, and optionally notify-send and paplay for alerts.
#
# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
set -Eeuo pipefail
trap "echo -e '\n${NORD11}Exiting...${NC}'; exit 0" SIGINT SIGTERM

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD4='\033[38;2;216;222;233m'   # Light gray (text)
NORD7='\033[38;2;143;188;187m'   # Teal (success/info)
NORD8='\033[38;2;136;192;208m'   # Accent blue (headings)
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD14='\033[38;2;163;190;140m'  # Green (labels/values)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# Global Variables: Default durations (in minutes) and cycle count
# ------------------------------------------------------------------------------
WORK_DURATION=25      # Default work session length in minutes
BREAK_DURATION=5      # Default break session length in minutes
DEFAULT_CYCLES=4      # Default number of Pomodoro cycles

# ------------------------------------------------------------------------------
# Function: alert
# Description: Provide audible and visual notification.
# ------------------------------------------------------------------------------
alert() {
    local message="$1"
    # Send a desktop notification if available
    if command -v notify-send &>/dev/null; then
        notify-send "Pomodoro Timer" "$message"
    fi
    # Play a sound alert if paplay is available (using a standard sound)
    if command -v paplay &>/dev/null; then
        paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null
    else
        # Fallback: Terminal bell
        echo -ne "\007"
    fi
}

# ------------------------------------------------------------------------------
# Function: countdown
# Description: Displays a dynamic countdown timer in mm:ss format.
# Arguments:
#   $1 - Total seconds for countdown.
#   $2 - Label for the session (e.g., "Work", "Break").
# ------------------------------------------------------------------------------
countdown() {
    local total_seconds=$1
    local label="$2"
    while (( total_seconds > 0 )); do
        local minutes=$(( total_seconds / 60 ))
        local seconds=$(( total_seconds % 60 ))
        # Print on the same line using carriage return
        printf "\r${NORD14}%s Session: %02d:%02d remaining...${NC}" "$label" "$minutes" "$seconds"
        sleep 1
        (( total_seconds-- ))
    done
    echo ""  # Newline after countdown finishes
}

# ------------------------------------------------------------------------------
# Function: pomodoro_session
# Description: Runs one full Pomodoro cycle: work session followed by break.
# ------------------------------------------------------------------------------
pomodoro_session() {
    alert "Work session started! Focus for ${WORK_DURATION} minutes."
    countdown $(( WORK_DURATION * 60 )) "Work"
    alert "Work session complete! Time for a ${BREAK_DURATION}-minute break."
    countdown $(( BREAK_DURATION * 60 )) "Break"
    alert "Break session complete! Ready to get back to work."
}

# ------------------------------------------------------------------------------
# Function: start_pomodoro
# Description: Runs the Pomodoro timer for the specified number of cycles.
# ------------------------------------------------------------------------------
start_pomodoro() {
    local cycles
    read -rp "Enter number of cycles (0 for indefinite, default: ${DEFAULT_CYCLES}): " cycles_input
    if [[ -z "$cycles_input" ]]; then
        cycles=$DEFAULT_CYCLES
    else
        cycles=$cycles_input
    fi

    if [[ "$cycles" -eq 0 ]]; then
        echo -e "${NORD14}Starting indefinite Pomodoro sessions. Press Ctrl+C to stop.${NC}"
        while true; do
            pomodoro_session
        done
    else
        for (( i=1; i<=cycles; i++ )); do
            echo -e "\n${NORD8}--- Pomodoro Cycle $i of $cycles ---${NC}"
            pomodoro_session
        done
    fi
    echo -e "${NORD14}All Pomodoro cycles completed. Great job!${NC}"
}

# ------------------------------------------------------------------------------
# Function: configure_durations
# Description: Allow user to customize work and break durations.
# ------------------------------------------------------------------------------
configure_durations() {
    read -rp "Enter work session length in minutes (current: ${WORK_DURATION}): " work_input
    if [[ -n "$work_input" && "$work_input" =~ ^[0-9]+$ ]]; then
        WORK_DURATION=$work_input
        echo -e "${NORD14}Work session duration updated to ${WORK_DURATION} minutes.${NC}"
    else
        echo -e "${NORD12}Invalid input. Work duration remains ${WORK_DURATION} minutes.${NC}"
    fi

    read -rp "Enter break session length in minutes (current: ${BREAK_DURATION}): " break_input
    if [[ -n "$break_input" && "$break_input" =~ ^[0-9]+$ ]]; then
        BREAK_DURATION=$break_input
        echo -e "${NORD14}Break session duration updated to ${BREAK_DURATION} minutes.${NC}"
    else
        echo -e "${NORD12}Invalid input. Break duration remains ${BREAK_DURATION} minutes.${NC}"
    fi

    sleep 1
}

# ------------------------------------------------------------------------------
# Function: main_menu
# Description: Displays the main interactive menu.
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${NORD8}============================================${NC}"
        echo -e "${NORD8}           Pomodoro Timer Menu              ${NC}"
        echo -e "${NORD8}============================================${NC}"
        echo -e "${NORD14}[1]${NC} Start Pomodoro Timer"
        echo -e "${NORD14}[2]${NC} Configure Timer Durations"
        echo -e "${NORD14}[q]${NC} Quit"
        echo -e "${NORD8}--------------------------------------------${NC}"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                start_pomodoro
                read -rp "Press Enter to return to the main menu..." dummy
                ;;
            2)
                configure_durations
                read -rp "Press Enter to return to the main menu..." dummy
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
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    main_menu
}

# ------------------------------------------------------------------------------
# Execute Main if Script is Run Directly
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi