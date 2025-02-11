#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: advanced_git_manager.sh
# Description: Advanced interactive Git management tool that scans the user's
#              home directory for Git repositories and presents an interactive
#              menu to perform common Git operations. The interface is styled
#              with the elegant Nord color theme, optimized for Debian Linux.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./advanced_git_manager.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
# For non‑root usage, the log file is stored in the user's home directory.
LOG_FILE="$HOME/.advanced_git_manager.log"
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISABLE_COLORS="${DISABLE_COLORS:-false}"

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
    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
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
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        log WARN "This script is not running as root. Some operations may fail."
        # Uncomment the next line if root privileges are required:
        # handle_error "This script must be run as root."
    fi
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

# Print a divider for UI separation
print_divider() {
    printf "%b------------------------------------------------------------%b\n" "${NORD8}" "${NC}"
}

# Clear the screen and print a header for the interactive UI
print_header() {
    clear
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
    printf "%b            Advanced Git Management Tool                  %b\n" "${NORD8}" "${NC}"
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
}

# Prompt the user to press Enter to continue
prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# GIT MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
# Search for Git repositories in the user's home directory
search_git_repos() {
    log INFO "Scanning your home directory for Git repositories..."
    # Find directories named ".git" and return their parent directories (unique)
    mapfile -t repo_paths < <(find "$HOME" -type d -name ".git" 2>/dev/null | sed 's/\/.git$//' | sort -u)
    if [[ ${#repo_paths[@]} -eq 0 ]]; then
        handle_error "No Git repositories found in your home directory."
    fi
    # Output each repository path on its own line
    for repo in "${repo_paths[@]}"; do
        echo "$repo"
    done
}

# Display the list of found repositories and allow the user to select one
select_repository() {
    local repos=("$@")
    echo -e "\n${NORD14}Found the following Git repositories:${NC}"
    print_divider
    local idx=1
    for repo in "${repos[@]}"; do
        printf "%b[%d]%b %b%s%b\n" "${NORD8}" "$idx" "${NC}" "${NORD4}" "$repo" "${NC}"
        ((idx++))
    done
    print_divider

    local choice
    while true; do
        read -rp "Enter the number of the repository to manage (or 'q' to quit): " choice
        if [[ "$choice" == "q" ]]; then
            log INFO "Exiting..."
            exit 0
        elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice < idx )); then
            local selected_repo="${repos[$((choice-1))]}"
            echo -e "${NORD14}Selected Repository:${NC} ${NORD4}${selected_repo}${NC}"
            break
        else
            echo -e "${NORD12}Invalid selection. Please enter a valid number.${NC}"
        fi
    done
    echo "$selected_repo"
}

# Interactive repository management menu
repo_menu() {
    local repo_path="$1"
    cd "$repo_path" || handle_error "Failed to change directory to $repo_path"
    local choice

    while true; do
        print_header
        echo -e "${NORD14}Repository:${NC} ${NORD4}$repo_path${NC}"
        echo -e "${NORD14}Current Branch:${NC} $(git branch --show-current 2>/dev/null)"
        echo -e "${NORD14}Status:${NC}"
        git status --short
        print_divider
        echo -e "${NORD8}Select an action:${NC}"
        echo -e "${NORD8}[1]${NC} View full git status"
        echo -e "${NORD8}[2]${NC} Add files"
        echo -e "${NORD8}[3]${NC} Commit changes"
        echo -e "${NORD8}[4]${NC} Pull from remote"
        echo -e "${NORD8}[5]${NC} Push to remote"
        echo -e "${NORD8}[6]${NC} List branches"
        echo -e "${NORD8}[7]${NC} Checkout branch"
        echo -e "${NORD8}[8]${NC} Create new branch"
        echo -e "${NORD8}[9]${NC} Merge branch into current"
        echo -e "${NORD8}[10]${NC} View git log"
        echo -e "${NORD8}[0]${NC} Return to repository selection"
        print_divider

        read -rp "Enter your choice: " choice
        case "$choice" in
            1)
                print_divider
                echo -e "${NORD14}Full Git Status:${NC}"
                git status
                print_divider
                prompt_enter
                ;;
            2)
                read -rp "Add all files? (y/n): " add_all
                if [[ "$add_all" =~ ^[Yy]$ ]]; then
                    git add -A || handle_error "git add failed"
                else
                    read -rp "Enter file(s) to add (separated by space): " files
                    git add $files || handle_error "git add failed"
                fi
                log INFO "Files added."
                prompt_enter
                ;;
            3)
                read -rp "Enter commit message: " commit_msg
                if [[ -z "$commit_msg" ]]; then
                    echo -e "${NORD12}Commit message cannot be empty.${NC}"
                else
                    git commit -m "$commit_msg" || handle_error "git commit failed"
                    log INFO "Changes committed."
                fi
                prompt_enter
                ;;
            4)
                git pull || handle_error "git pull failed"
                log INFO "Pulled latest changes."
                prompt_enter
                ;;
            5)
                git push || handle_error "git push failed"
                log INFO "Pushed changes to remote."
                prompt_enter
                ;;
            6)
                print_divider
                echo -e "${NORD14}Branches:${NC}"
                git branch -a
                print_divider
                prompt_enter
                ;;
            7)
                read -rp "Enter branch name to checkout: " branch_name
                if [[ -z "$branch_name" ]]; then
                    echo -e "${NORD12}Branch name cannot be empty.${NC}"
                else
                    git checkout "$branch_name" || handle_error "git checkout failed"
                    log INFO "Checked out branch $branch_name."
                fi
                prompt_enter
                ;;
            8)
                read -rp "Enter new branch name: " new_branch
                if [[ -z "$new_branch" ]]; then
                    echo -e "${NORD12}Branch name cannot be empty.${NC}"
                else
                    git checkout -b "$new_branch" || handle_error "Failed to create branch"
                    log INFO "Created and switched to new branch $new_branch."
                fi
                prompt_enter
                ;;
            9)
                read -rp "Enter branch name to merge into current branch: " merge_branch
                if [[ -z "$merge_branch" ]]; then
                    echo -e "${NORD12}Branch name cannot be empty.${NC}"
                else
                    git merge "$merge_branch" || handle_error "Merge failed"
                    log INFO "Merged branch $merge_branch into current branch."
                fi
                prompt_enter
                ;;
            10)
                print_divider
                echo -e "${NORD14}Git Log (last 10 commits):${NC}"
                git log --oneline -n 10
                print_divider
                prompt_enter
                ;;
            0)
                echo -e "${NORD14}Returning to repository selection...${NC}"
                break
                ;;
            *)
                echo -e "${NORD12}Invalid choice. Please select a valid option.${NC}"
                prompt_enter
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Optionally check for root privileges (not required for this script)
    check_root

    # Ensure the log file directory exists
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Advanced Git Manager started."

    print_header
    # Search for Git repositories in the user's home directory.
    mapfile -t repos < <(search_git_repos)
    
    while true; do
        echo -e "\n${NORD14}Repository Selection:${NC}"
        local selected_repo
        selected_repo=$(select_repository "${repos[@]}")
        # Enter the repository management menu.
        repo_menu "$selected_repo"
        # Ask if the user wants to manage another repository.
        read -rp "Do you want to manage another repository? (y/n): " answer
        if [[ "$answer" =~ ^[Nn]$ ]]; then
            echo -e "${NORD14}Goodbye!${NC}"
            log INFO "Advanced Git Manager terminated by user."
            exit 0
        fi
    done
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi