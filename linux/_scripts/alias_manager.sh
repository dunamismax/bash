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
#   ./advanced_alias_manager.sh
#
# Notes:
#   • After making changes, reload your shell (source ~/.bashrc) to apply updates.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark Background
NORD4='\033[38;2;216;222;233m'   # Light Gray (Text)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (Headings)
NORD11='\033[38;2;191;97;106m'   # Red (Errors)
NORD12='\033[38;2;208;135;112m'  # Orange (Warnings)
NORD14='\033[38;2;163;190;140m'  # Green (Success/Info)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------------
BASHRC_FILE="$HOME/.bashrc"
BIN_DIR="$HOME/bin"
CUSTOM_ALIAS_MARKER="# Custom Aliases (Managed by advanced_alias_manager.sh)"
ALIAS_TEMP_FILE="$(mktemp)"

# ------------------------------------------------------------------------------
# Helper Function: Print Header
# ------------------------------------------------------------------------------
print_header() {
    clear
    echo -e "${NORD8}============================================${NC}"
    echo -e "${NORD8}       Advanced Alias Manager Tool          ${NC}"
    echo -e "${NORD8}============================================${NC}"
}

# ------------------------------------------------------------------------------
# Helper Function: Ensure Custom Alias Section Exists in .bashrc
# ------------------------------------------------------------------------------
ensure_custom_alias_section() {
    if ! grep -qF "$CUSTOM_ALIAS_MARKER" "$BASHRC_FILE"; then
        echo -e "\n$CUSTOM_ALIAS_MARKER" >> "$BASHRC_FILE"
        echo -e "# End of custom aliases" >> "$BASHRC_FILE"
    fi
}

# ------------------------------------------------------------------------------
# Function: List Existing Aliases from .bashrc
# ------------------------------------------------------------------------------
list_aliases() {
    # Extract lines that begin with "alias " (ignoring system aliases)
    grep '^alias ' "$BASHRC_FILE" > "$ALIAS_TEMP_FILE"
    if [[ ! -s "$ALIAS_TEMP_FILE" ]]; then
        echo -e "${NORD12}No aliases found in ${BASHRC_FILE}.${NC}"
        return 1
    fi

    echo -e "${NORD14}Existing Aliases:${NC}"
    echo -e "${NORD8}--------------------------------------------${NC}"
    local i=1
    while IFS= read -r line; do
        # Remove the "alias " prefix and split at the '=' character.
        local alias_name
        alias_name=$(echo "$line" | sed -E "s/^alias ([^=]+)=.*/\1/")
        local alias_cmd
        alias_cmd=$(echo "$line" | sed -E "s/^alias [^=]+=['\"](.*)['\"]/\\1/")
        printf "${NORD8}[%d]${NC} ${NORD4}%s${NC} => ${NORD14}%s${NC}\n" "$i" "$alias_name" "$alias_cmd"
        ((i++))
    done < "$ALIAS_TEMP_FILE"
    echo -e "${NORD8}--------------------------------------------${NC}"
    return 0
}

# ------------------------------------------------------------------------------
# Function: Edit an Alias
# ------------------------------------------------------------------------------
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

    # Use sed to replace the alias line in .bashrc.
    sed -i.bak -E "s/^alias ${alias_name}=.*/alias ${alias_name}='${new_cmd}'/" "$BASHRC_FILE" \
        && echo -e "${NORD14}Alias '${alias_name}' updated successfully.${NC}" \
        || echo -e "${NORD11}Failed to update alias.${NC}"
}

# ------------------------------------------------------------------------------
# Function: Rename an Alias
# ------------------------------------------------------------------------------
rename_alias() {
    local alias_line="$1"
    local old_name
    old_name=$(echo "$alias_line" | sed -E "s/^alias ([^=]+)=.*/\1/")
    local cmd_part
    cmd_part=$(echo "$alias_line" | sed -E "s/^alias [^=]+=(.*)/\1/")
    echo -e "${NORD14}Renaming alias '${old_name}':${NC}"
    read -rp "Enter new alias name (leave blank to cancel): " new_name
    if [[ -z "$new_name" ]]; then
        echo -e "${NORD12}Rename cancelled.${NC}"
        return 1
    fi

    sed -i.bak -E "s/^alias ${old_name}=/alias ${new_name}=/" "$BASHRC_FILE" \
        && echo -e "${NORD14}Alias renamed from '${old_name}' to '${new_name}' successfully.${NC}" \
        || echo -e "${NORD11}Failed to rename alias.${NC}"
}

# ------------------------------------------------------------------------------
# Function: Delete an Alias
# ------------------------------------------------------------------------------
delete_alias() {
    local alias_line="$1"
    local alias_name
    alias_name=$(echo "$alias_line" | sed -E "s/^alias ([^=]+)=.*/\1/")
    read -rp "Are you sure you want to delete alias '${alias_name}'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        sed -i.bak "/^alias ${alias_name}=/d" "$BASHRC_FILE" \
            && echo -e "${NORD14}Alias '${alias_name}' deleted successfully.${NC}" \
            || echo -e "${NORD11}Failed to delete alias.${NC}"
    else
        echo -e "${NORD12}Deletion cancelled.${NC}"
    fi
}

# ------------------------------------------------------------------------------
# Function: Manage an Existing Alias
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# Function: Create New Alias from a Script in ~/bin
# ------------------------------------------------------------------------------
create_alias_from_script() {
    # Ensure ~/bin exists
    if [[ ! -d "$BIN_DIR" ]]; then
        mkdir -p "$BIN_DIR" || { echo -e "${NORD11}Failed to create $BIN_DIR${NC}"; return 1; }
    fi

    echo -e "${NORD14}Available Scripts in ${BIN_DIR}:${NC}"
    local scripts=()
    local i=1
    while IFS= read -r -d $'\0' file; do
        scripts+=("$file")
        local script_name
        script_name=$(basename "$file")
        printf "${NORD8}[%d]${NC} %s\n" "$i" "$script_name"
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
        && echo -e "${NORD14}Alias '${new_alias}' created successfully.${NC}" \
        || echo -e "${NORD11}Failed to create alias.${NC}"
}

# ------------------------------------------------------------------------------
# Function: Create New Alias Manually
# ------------------------------------------------------------------------------
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
        && echo -e "${NORD14}Alias '${new_alias}' created successfully.${NC}" \
        || echo -e "${NORD11}Failed to create alias.${NC}"
}

# ------------------------------------------------------------------------------
# Main Interactive Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Advanced Alias Manager Menu:${NC}"
        echo -e "${NORD8}[1]${NC} List and Manage Existing Aliases"
        echo -e "${NORD8}[2]${NC} Create New Alias from a Script (~/bin)"
        echo -e "${NORD8}[3]${NC} Create New Alias Manually"
        echo -e "${NORD8}[q]${NC} Quit"
        echo -e "${NORD8}--------------------------------------------${NC}"
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
                break
                ;;
            *)
                echo -e "${NORD12}Invalid selection. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# Main Script Execution
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main_menu
fi