#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: advanced_git_manager.sh
# Description: Advanced interactive Git management tool that scans the user's
#              home directory for Git repositories and presents an interactive
#              menu to perform common Git operations. The interface is styled
#              with the elegant Nord color theme.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   ./advanced_git_manager.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light gray
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (Success)
NORD8='\033[38;2;136;192;208m'   # Accent Blue
NORD9='\033[38;2;129;161;193m'
NORD10='\033[38;2;94;129;172m'   # Purple (Highlight)
NORD11='\033[38;2;191;97;106m'   # Red (Errors)
NORD12='\033[38;2;208;135;112m'  # Orange/Warning
NORD13='\033[38;2;235;203;139m'  # Yellow (Info)
NORD14='\033[38;2;163;190;140m'  # Green (OK)
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
            INFO)   color="${NORD13}" ;;  # Info: Yellow
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD12}" ;;      # Warn: Orange
            ERROR)  color="${NORD11}" ;;     # Error: Red
            DEBUG)  color="${NORD9}"  ;;     # Debug: Blue
            *)      color="$NC"     ;;
        esac
    fi

    local log_entry="[$timestamp] [$upper_level] $message"
    echo -e "$log_entry"
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# HELPERS FOR INTERACTIVE UI
# ------------------------------------------------------------------------------
print_divider() {
    echo -e "${NORD8}------------------------------------------------------------${NC}"
}

print_header() {
    clear
    echo -e "${NORD8}============================================================${NC}"
    echo -e "${NORD8}            Advanced Git Management Tool                  ${NC}"
    echo -e "${NORD8}============================================================${NC}"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# SEARCH FOR GIT REPOSITORIES IN THE USER'S HOME DIRECTORY
# ------------------------------------------------------------------------------
search_git_repos() {
    echo -e "${NORD14}Scanning your home directory for Git repositories...${NC}"
    # Find directories named ".git" and return their parent directories (unique)
    # Exclude potential permission errors by redirecting errors.
    mapfile -t repo_paths < <(find "$HOME" -type d -name ".git" 2>/dev/null | sed 's/\/.git$//' | sort -u)
    if [[ ${#repo_paths[@]} -eq 0 ]]; then
        handle_error "No Git repositories found in your home directory."
    fi
    echo "${repo_paths[@]}"
}

# ------------------------------------------------------------------------------
# DISPLAY THE LIST OF FOUND REPOSITORIES AND ALLOW USER TO SELECT ONE
# ------------------------------------------------------------------------------
select_repository() {
    local repos=("$@")
    echo -e "\n${NORD14}Found the following Git repositories:${NC}"
    print_divider
    local idx=1
    for repo in "${repos[@]}"; do
        echo -e "${NORD8}[${idx}]${NC} ${NORD4}${repo}${NC}"
        ((idx++))
    done
    print_divider

    local choice
    while true; do
        read -rp "Enter the number of the repository to manage (or 'q' to quit): " choice
        if [[ "$choice" == "q" ]]; then
            echo -e "${NORD14}Exiting...${NC}"
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

# ------------------------------------------------------------------------------
# INTERACTIVE REPOSITORY MENU
# ------------------------------------------------------------------------------
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
    print_header
    # Search for Git repositories in the user's home directory.
    mapfile -t repos < <(search_git_repos)
    
    while true; do
        echo -e "\n${NORD14}Repository Selection:${NC}"
        selected_repo=$(select_repository "${repos[@]}")
        # Enter the repository management menu.
        repo_menu "$selected_repo"
        # Ask if the user wants to manage another repository.
        read -rp "Do you want to manage another repository? (y/n): " answer
        if [[ "$answer" =~ ^[Nn]$ ]]; then
            echo -e "${NORD14}Goodbye!${NC}"
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