#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: secure_disk_eraser.sh
# Description: An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
#              This script installs required tools, lists attached disks with
#              details, detects whether a disk is an HDD, SSD, or NVMe, and lets
#              the user choose from several secure erasure methods (using hdparm,
#              nvme-cli, or shred) with full interactive prompts and double‑check
#              confirmations, all with Nord‑themed color output.
# Author: Your Name | License: MIT | Version: 1.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./secure_disk_eraser.sh
#
# Notes:
#   - This script must be run as root.
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
readonly LOG_FILE="/var/log/secure_disk_eraser.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"     # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels (case-insensitive): VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"
LOG_LEVEL="${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}"
readonly DEBIAN_FRONTEND=noninteractive
# Tools required by the script.
readonly TOOLS=(hdparm nvme-cli coreutils)  # coreutils provides shred

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
# Using Nord palette from our standard template:
readonly NORD9='\033[38;2;129;161;193m'   # Bluish (DEBUG)
readonly NORD10='\033[38;2;94;129;172m'    # Accent Blue (section headers)
readonly NORD11='\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'   # Yellowish (WARN/labels)
readonly NORD14='\033[38;2;163;190;140m'   # Greenish (INFO/success)
readonly NC='\033[0m'                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W)echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL message
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    
    local msg_level
    msg_level=$(get_log_level_num "$upper_level")
    local current_level
    current_level=$(get_log_level_num "$LOG_LEVEL")
    if (( msg_level < current_level )); then
        return 0
    fi

    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)         color="${NORD9}"  ;;
            INFO)          color="${NORD14}" ;;
            WARN|WARNING)  color="${NORD13}" ;;
            ERROR|CRITICAL)color="${NORD11}" ;;
            *)             color="${NC}"     ;;
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
    local error_message="${1:-"An error occurred. See log for details."}"
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
    # Add any additional cleanup tasks if needed.
}

trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
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
# FUNCTION: Install Prerequisites
# ------------------------------------------------------------------------------
install_prerequisites() {
    print_section "Installing Required Tools"
    log INFO "Updating package repositories..."
    apt update || handle_error "Failed to update repositories."
    log INFO "Installing required tools: hdparm, nvme-cli, and coreutils (for shred)..."
    apt install -y hdparm nvme-cli coreutils || handle_error "Failed to install prerequisites."
    log INFO "Required tools installed."
}

# ------------------------------------------------------------------------------
# FUNCTION: List Attached Disks
# ------------------------------------------------------------------------------
list_disks() {
    lsblk -d -o NAME,SIZE,TYPE,ROTA,MODEL | grep "disk"
}

# ------------------------------------------------------------------------------
# FUNCTION: Detect Disk Type
# ------------------------------------------------------------------------------
detect_disk_type() {
    local disk="$1"
    if [[ "$disk" == nvme* ]]; then
        echo "nvme"
    elif [[ -f "/sys/block/${disk}/queue/rotational" ]]; then
        local rota
        rota=$(cat "/sys/block/$disk/queue/rotational")
        if [[ "$rota" -eq 1 ]]; then
            echo "hdd"
        else
            echo "ssd"
        fi
    else
        echo "unknown"
    fi
}

# ------------------------------------------------------------------------------
# FUNCTION: Prompt User for Disk Selection
# ------------------------------------------------------------------------------
select_disk() {
    log INFO "Scanning for attached disks..."
    local disks
    disks=$(list_disks)
    if [[ -z "$disks" ]]; then
        log ERROR "No disks found on the system."
        exit 1
    fi
    echo -e "${NORD10}Attached Disks:${NC}"
    echo -e "${NORD10}--------------------------------------------------${NC}"
    local i=1
    declare -A disk_map
    while IFS= read -r line; do
        local name size type rota model disk_type
        name=$(echo "$line" | awk '{print $1}')
        size=$(echo "$line" | awk '{print $2}')
        type=$(echo "$line" | awk '{print $3}')
        rota=$(echo "$line" | awk '{print $4}')
        model=$(echo "$line" | cut -d' ' -f5-)
        disk_type=$(detect_disk_type "$name")
        printf "${NORD10}[%d]${NC} /dev/%s - Size: %s, Type: %s, Model: %s\n" "$i" "$name" "$size" "$disk_type" "$model"
        disk_map["$i"]="$name"
        ((i++))
    done <<< "$disks"
    echo -e "${NORD10}--------------------------------------------------${NC}"
    while true; do
        read -rp "Enter the number of the disk to erase (or 'q' to quit): " choice
        if [[ "$choice" == "q" ]]; then
            echo -e "${NORD14}Exiting...${NC}"
            exit 0
        elif [[ -n "${disk_map[$choice]:-}" ]]; then
            local selected_disk="/dev/${disk_map[$choice]}"
            echo -e "${NORD14}Selected disk: ${selected_disk}${NC}"
            echo "$selected_disk"
            return 0
        else
            echo -e "${NORD13}Invalid selection. Please try again.${NC}"
        fi
    done
}

# ------------------------------------------------------------------------------
# FUNCTION: Secure Erase using hdparm (for ATA drives and some SSDs)
# ------------------------------------------------------------------------------
secure_erase_hdparm() {
    local disk="$1"
    echo -e "${NORD14}Preparing to securely erase ${disk} using hdparm...${NC}"
    read -rp "Enter a temporary security password (this will be cleared): " sec_pass
    echo -e "${NORD13}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${NORD13}Operation cancelled.${NC}"
        return 1
    fi
    hdparm --user-master u --security-set-pass "$sec_pass" "$disk" || handle_error "Failed to set security password on $disk."
    hdparm --user-master u --security-erase "$sec_pass" "$disk" || handle_error "Secure Erase command failed on $disk."
    echo -e "${NORD14}Secure Erase via hdparm completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# FUNCTION: Secure Erase for NVMe using nvme-cli
# ------------------------------------------------------------------------------
nvme_secure_erase() {
    local disk="$1"
    echo -e "${NORD14}Preparing to format NVMe drive ${disk} using nvme-cli...${NC}"
    echo -e "${NORD13}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${NORD13}Operation cancelled.${NC}"
        return 1
    fi
    nvme format "$disk" || handle_error "nvme format failed on $disk."
    echo -e "${NORD14}NVMe format completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# FUNCTION: Wipe Disk using shred
# ------------------------------------------------------------------------------
shred_wipe() {
    local disk="$1"
    read -rp "Enter number of overwrites (recommended 3): " num_overwrites
    if ! [[ "$num_overwrites" =~ ^[0-9]+$ ]]; then
        echo -e "${NORD13}Invalid number; defaulting to 3 overwrites.${NC}"
        num_overwrites=3
    fi
    echo -e "${NORD14}Preparing to wipe ${disk} using shred with ${num_overwrites} passes...${NC}"
    echo -e "${NORD13}WARNING: This operation is irreversible and may take a long time.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${NORD13}Operation cancelled.${NC}"
        return 1
    fi
    shred -n "$num_overwrites" -z -v "$disk" || handle_error "shred failed on $disk."
    echo -e "${NORD14}Disk wipe with shred completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# FUNCTION: Disk Eraser Menu
# ------------------------------------------------------------------------------
disk_eraser_menu() {
    local selected_disk disk disk_type
    selected_disk=$(select_disk)
    disk=$(basename "$selected_disk")
    disk_type=$(detect_disk_type "$disk")
    echo -e "${NORD10}Detected disk type: ${disk_type}${NC}"
    echo -e "${NORD10}Select the erasure method:${NC}"
    if [[ "$disk_type" == "nvme" ]]; then
        echo -e "${NORD10}[1]${NC} NVMe Format (nvme-cli)"
        echo -e "${NORD10}[3]${NC} Shred Wipe (use with caution on SSDs)"
    elif [[ "$disk_type" == "ssd" ]]; then
        echo -e "${NORD10}[1]${NC} Secure Erase (hdparm) [Works on some SSDs]"
        echo -e "${NORD10}[3]${NC} Shred Wipe (Not recommended for SSDs)"
    elif [[ "$disk_type" == "hdd" ]]; then
        echo -e "${NORD10}[1]${NC} Secure Erase (hdparm)"
        echo -e "${NORD10}[3]${NC} Shred Wipe (multiple overwrites)"
    else
        echo -e "${NORD10}[1]${NC} Secure Erase (hdparm)"
        echo -e "${NORD10}[3]${NC} Shred Wipe"
    fi
    echo -e "${NORD10}[0]${NC} Return to Main Menu"
    read -rp "Enter your choice: " method_choice
    case "$method_choice" in
        1)
            if [[ "$disk_type" == "nvme" ]]; then
                nvme_secure_erase "$selected_disk"
            else
                secure_erase_hdparm "$selected_disk"
            fi
            ;;
        3)
            shred_wipe "$selected_disk"
            ;;
        0)
            return 0
            ;;
        *)
            echo -e "${NORD13}Invalid selection. Returning to main menu.${NC}"
            return 1
            ;;
    esac
    prompt_enter
}

# ------------------------------------------------------------------------------
# FUNCTION: Main Interactive Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${NORD10}============================================${NC}"
        echo -e "${NORD10}       Secure HDD/SSD Eraser Tool           ${NC}"
        echo -e "${NORD10}============================================${NC}"
        echo -e "${NORD14}[1]${NC} List Attached Disks"
        echo -e "${NORD14}[2]${NC} Erase a Disk"
        echo -e "${NORD14}[q]${NC} Quit"
        echo -e "${NORD10}--------------------------------------------${NC}"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                echo -e "${NORD14}Attached Disks:${NC}"
                list_disks
                prompt_enter
                ;;
            2)
                disk_eraser_menu
                ;;
            q)
                echo -e "${NORD14}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${NORD13}Invalid selection. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with Bash.${NC}" >&2
        exit 1
    fi
    check_root
    log INFO "Starting Secure Disk Eraser Tool..."
    install_prerequisites
    main_menu
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
