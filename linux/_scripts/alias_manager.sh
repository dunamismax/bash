#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: alias_manager.sh
# Description: An advanced interactive alias manager for your terminal. This
#              script scans your ~/.bashrc for custom aliases, lets you view,
#              edit, delete, or rename them, and also allows you to create new
#              aliases linked to scripts in your ~/bin directory or custom commands.
#              All modifications are appended to a designated "Custom Aliases"
#              section at the bottom of your ~/.bashrc.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./alias_manager.sh
#
# Notes:
#   • After making changes, reload your shell (source ~/.bashrc) to apply updates.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="$HOME/.alias_manager.log"
BASHRC_FILE="$HOME/.bashrc"
BIN_DIR="$HOME/bin"
CUSTOM_ALIAS_MARKER="# Custom Aliases (Managed by alias_manager.sh)"
ALIAS_TEMP_FILE="$(mktemp)"
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISABLE_COLORS="${DISABLE_COLORS:-false}"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark Background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light Gray (Text)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'
NORD8='\033[38;2;136;192;208m'   # Accent Blue (Headings)
NORD9='\033[38;2;129;161;193m'
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Red (Errors)
NORD12='\033[38;2;208;135;112m'  # Orange (Warnings)
NORD13='\033[38;2;235;203;139m'
NORD14='\033[38;2;163;190;140m'  # Green (Success/Info)
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
            INFO)  color="${NORD14}" ;;
            WARN)  color="${NORD13}" ;;
            ERROR) color="${NORD11}" ;;
            DEBUG) color="${NORD9}"  ;;
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
    rm -f "$ALIAS_TEMP_FILE"
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
print_header() {
    clear
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
    printf "%b         Advanced Alias Manager Tool                      %b\n" "${NORD8}" "${NC}"
    printf "%b============================================================%b\n" "${NORD8}" "${NC}"
}

ensure_custom_alias_section() {
    if ! grep -qF "$CUSTOM_ALIAS_MARKER" "$BASHRC_FILE"; then
        {
            echo -e "\n$CUSTOM_ALIAS_MARKER"
            echo -e "# End of custom aliases"
        } >> "$BASHRC_FILE" || handle_error "Failed to append custom alias section to $BASHRC_FILE"
        log INFO "Custom alias section added to $BASHRC_FILE."
    fi
}

list_aliases() {
    grep '^alias ' "$BASHRC_FILE" > "$ALIAS_TEMP_FILE"
    if [[ ! -s "$ALIAS_TEMP_FILE" ]]; then
        echo -e "${NORD12}No aliases found in ${BASHRC_FILE}.${NC}"
        return 1
    fi

    echo -e "${NORD14}Existing Aliases:${NC}"
    printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
    local i=1
    while IFS= read -r line; do
        local alias_name
        alias_name=$(echo "$line" | sed -E "s/^alias ([^=]+)=.*/\1/")
        local alias_cmd
        alias_cmd=$(echo "$line" | sed -E "s/^alias [^=]+=['\"](.*)['\"]/\\1/")
        printf "%b[%d]%b %b%s%b => %b%s%b\n" "${NORD8}" "$i" "${NC}" "${NORD4}" "$alias_name" "${NORD14}" "$alias_cmd" "${NC}"
        ((i++))
    done < "$ALIAS_TEMP_FILE"
    printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
    return 0
}

edit_alias() {
    local alias_line="$1"
    local alias_name
    alias_name=$(echo "$alias_line" | sed -E "s/^alias ([^=]+)=.*/\1/")
    local current_cmd
    current_cmd=$(echo "$alias_line" | sed -E "s/^alias [^=]+=['\"](.*)['\"]/\\1/")

    echo -e "${NORD14}Editing alias '${alias_name}':${NC}"
    echo -e "Current command: ${NORD4}${current_cmd}${NC}"
    read -rp "Enter new command (leave blank to cancel): " new_cmd
    if [[ -z "$new_cmd" ]]; then
        echo -e "${NORD12}Edit cancelled.${NC}"
        return 1
    fi

    sed -i.bak -E "s/^alias ${alias_name}=.*/alias ${alias_name}='${new_cmd}'/" "$BASHRC_FILE" \
        && { echo -e "${NORD14}Alias '${alias_name}' updated successfully.${NC}"; log INFO "Alias '${alias_name}' updated."; } \
        || { echo -e "${NORD11}Failed to update alias.${NC}"; log ERROR "Failed to update alias '${alias_name}'."; }
}

rename_alias() {
    local alias_line="$1"
    local old_name
    old_name=$(echo "$alias_line" | sed -E "s/^alias ([^=]+)=.*/\1/")
    echo -e "${NORD14}Renaming alias '${old_name}':${NC}"
    read -rp "Enter new alias name (leave blank to cancel): " new_name
    if [[ -z "$new_name" ]]; then
        echo -e "${NORD12}Rename cancelled.${NC}"
        return 1
    fi

    sed -i.bak -E "s/^alias ${old_name}=/alias ${new_name}=/" "$BASHRC_FILE" \
        && { echo -e "${NORD14}Alias renamed from '${old_name}' to '${new_name}' successfully.${NC}"; log INFO "Alias renamed from '${old_name}' to '${new_name}'."; } \
        || { echo -e "${NORD11}Failed to rename alias.${NC}"; log ERROR "Failed to rename alias '${old_name}'."; }
}

delete_alias() {
    local alias_line="$1"
    local alias_name
    alias_name=$(echo "$alias_line" | sed -E "s/^alias ([^=]+)=.*/\1/")
    read -rp "Are you sure you want to delete alias '${alias_name}'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        sed -i.bak "/^alias ${alias_name}=/d" "$BASHRC_FILE" \
            && { echo -e "${NORD14}Alias '${alias_name}' deleted successfully.${NC}"; log INFO "Alias '${alias_name}' deleted."; } \
            || { echo -e "${NORD11}Failed to delete alias.${NC}"; log ERROR "Failed to delete alias '${alias_name}'."; }
    else
        echo -e "${NORD12}Deletion cancelled.${NC}"
    fi
}

manage_alias() {
    list_aliases || return
    read -rp "Enter the number of the alias to manage (or 'b' to go back): " choice
    if [[ "$choice" == "b" ]]; then
        return
    fi
    local total
    total=$(wc -l < "$ALIAS_TEMP_FILE")
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > total )); then
        echo -e "${NORD12}Invalid selection.${NC}"
        return
    fi
    local selected_alias
    selected_alias=$(sed -n "${choice}p" "$ALIAS_TEMP_FILE")

    echo -e "${NORD14}Selected alias:${NC} ${NORD4}${selected_alias}${NC}"
    echo -e "${NORD8}[1]${NC} Edit Command"
    echo -e "${NORD8}[2]${NC} Rename Alias"
    echo -e "${NORD8}[3]${NC} Delete Alias"
    echo -e "${NORD8}[0]${NC} Cancel"
    read -rp "Enter your choice: " action
    case "$action" in
        1)
            edit_alias "$selected_alias"
            ;;
        2)
            rename_alias "$selected_alias"
            ;;
        3)
            delete_alias "$selected_alias"
            ;;
        0)
            echo -e "${NORD12}Operation cancelled.${NC}"
            ;;
        *)
            echo -e "${NORD12}Invalid choice.${NC}"
            ;;
    esac
}

create_alias_from_script() {
    if [[ ! -d "$BIN_DIR" ]]; then
        mkdir -p "$BIN_DIR" || handle_error "Failed to create $BIN_DIR"
    fi

    echo -e "${NORD14}Available Scripts in ${BIN_DIR}:${NC}"
    local scripts=()
    local i=1
    while IFS= read -r -d $'\0' file; do
        scripts+=("$file")
        local script_name
        script_name=$(basename "$file")
        printf "%b[%d]%b %s\n" "${NORD8}" "$i" "${NC}" "$script_name"
        ((i++))
    done < <(find "$BIN_DIR" -maxdepth 1 -type f -executable -print0)

    if (( ${#scripts[@]} == 0 )); then
        echo -e "${NORD12}No executable scripts found in ${BIN_DIR}.${NC}"
        return 1
    fi

    read -rp "Select a script by number (or 'b' to go back): " choice
    if [[ "$choice" == "b" ]]; then
        return
    fi
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#scripts[@]} )); then
        echo -e "${NORD12}Invalid selection.${NC}"
        return 1
    fi
    local selected_script="${scripts[$((choice-1))]}"
    local script_basename
    script_basename=$(basename "$selected_script")

    read -rp "Enter alias name to create for '${script_basename}': " new_alias
    if [[ -z "$new_alias" ]]; then
        echo -e "${NORD12}Alias name cannot be empty.${NC}"
        return 1
    fi

    ensure_custom_alias_section
    echo "alias ${new_alias}='${BIN_DIR}/${script_basename}'" >> "$BASHRC_FILE" \
        && { echo -e "${NORD14}Alias '${new_alias}' created successfully.${NC}"; log INFO "Alias '${new_alias}' created for script '${script_basename}'."; } \
        || { echo -e "${NORD11}Failed to create alias.${NC}"; log ERROR "Failed to create alias '${new_alias}'."; }
}

create_alias_manually() {
    read -rp "Enter alias name: " new_alias
    if [[ -z "$new_alias" ]]; then
        echo -e "${NORD12}Alias name cannot be empty.${NC}"
        return 1
    fi
    read -rp "Enter command for alias '${new_alias}': " alias_command
    if [[ -z "$alias_command" ]]; then
        echo -e "${NORD12}Command cannot be empty.${NC}"
        return 1
    fi

    ensure_custom_alias_section
    echo "alias ${new_alias}='${alias_command}'" >> "$BASHRC_FILE" \
        && { echo -e "${NORD14}Alias '${new_alias}' created successfully.${NC}"; log INFO "Alias '${new_alias}' created with command '${alias_command}'."; } \
        || { echo -e "${NORD11}Failed to create alias.${NC}"; log ERROR "Failed to create alias '${new_alias}'."; }
}

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Advanced Alias Manager Menu:${NC}"
        echo -e "${NORD8}[1]${NC} List and Manage Existing Aliases"
        echo -e "${NORD8}[2]${NC} Create New Alias from a Script (~/bin)"
        echo -e "${NORD8}[3]${NC} Create New Alias Manually"
        echo -e "${NORD8}[q]${NC} Quit"
        printf "%b--------------------------------------------%b\n" "${NORD8}" "${NC}"
        read -rp "Enter your choice: " choice
        case "$choice" in
            1)
                manage_alias
                read -rp "Press Enter to return to the main menu..." dummy
                ;;
            2)
                create_alias_from_script
                read -rp "Press Enter to return to the main menu..." dummy
                ;;
            3)
                create_alias_manually
                read -rp "Press Enter to return to the main menu..." dummy
                ;;
            q|Q)
                echo -e "${NORD14}Exiting Advanced Alias Manager. Goodbye!${NC}"
                log INFO "Alias Manager terminated by user."
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