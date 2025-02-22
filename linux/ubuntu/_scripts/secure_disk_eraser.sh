#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: secure_disk_eraser.sh
# Description: An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
#              This script installs required tools, lists attached disks with
#              details, detects whether a disk is an HDD, SSD, or NVMe, and lets
#              the user choose from several secure erasure methods (using hdparm,
#              nvme-cli, or shred) with full interactive prompts and double‑check
#              confirmations, all with Nord‑themed color output.
#
# Requirements:
#   • Must be run as root.
#   • Works on Ubuntu/Debian.
#
# Tools used:
#   • hdparm   – for ATA Secure Erase.
#   • nvme-cli – for NVMe formatting.
#   • shred    – for multiple overwrites (suitable for HDDs).
#
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & SET ERROR TRAPPING
# ------------------------------------------------------------------------------
set -Eeuo pipefail

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Add any cleanup tasks if needed.
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO in function ${FUNCNAME[1]:-main}."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'      # For errors
YELLOW='\033[38;2;235;203;139m'   # For warnings/labels
GREEN='\033[38;2;163;190;140m'    # For success/info
BLUE='\033[38;2;94;129;172m'      # For debug/highlights
CYAN='\033[38;2;136;192;208m'     # For headings/accent
GRAY='\033[38;2;216;222;233m'     # Light gray text
NC='\033[0m'                     # Reset Color

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/secure_disk_eraser.log"
DEBIAN_FRONTEND=noninteractive
TOOLS=(hdparm nvme-cli coreutils)  # coreutils provides shred

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log LEVEL message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)   color="${GREEN}" ;;
        WARN|WARNING) color="${YELLOW}" ;;
        ERROR)  color="${RED}" ;;
        DEBUG)  color="${BLUE}" ;;
        *)      color="${NC}" ;;
    esac
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

handle_error() {
    local error_message="${1:-"An error occurred. See log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo -e "${RED}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${CYAN}${border}${NC}"
    log INFO "${CYAN}  $title${NC}"
    log INFO "${CYAN}${border}${NC}"
}

# ------------------------------------------------------------------------------
# INSTALL PREREQUISITES FUNCTION
# ------------------------------------------------------------------------------
install_prerequisites() {
    print_section "Installing Required Tools"
    log INFO "Updating package repositories..."
    apt update || { log ERROR "Failed to update repositories."; exit 1; }
    log INFO "Installing hdparm, nvme-cli, and coreutils (for shred)..."
    apt install -y hdparm nvme-cli coreutils || { log ERROR "Failed to install prerequisites."; exit 1; }
    log INFO "Required tools installed."
}

# ------------------------------------------------------------------------------
# LIST ATTACHED DISKS
# ------------------------------------------------------------------------------
list_disks() {
    lsblk -d -o NAME,SIZE,TYPE,ROTA,MODEL | grep "disk"
}

# ------------------------------------------------------------------------------
# DETECT DISK TYPE FUNCTION
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
# PROMPT USER FOR DISK SELECTION
# ------------------------------------------------------------------------------
select_disk() {
    log INFO "Scanning for attached disks..."
    local disks
    disks=$(list_disks)
    if [[ -z "$disks" ]]; then
        log ERROR "No disks found on the system."
        exit 1
    fi
    echo -e "${CYAN}Attached Disks:${NC}"
    echo -e "${CYAN}--------------------------------------------------${NC}"
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
        printf "${CYAN}[%d]${NC} /dev/%s - Size: %s, Type: %s, Model: %s\n" "$i" "$name" "$size" "$disk_type" "$model"
        disk_map["$i"]="$name"
        ((i++))
    done <<< "$disks"
    echo -e "${CYAN}--------------------------------------------------${NC}"
    while true; do
        read -rp "Enter the number of the disk to erase (or 'q' to quit): " choice
        if [[ "$choice" == "q" ]]; then
            echo -e "${GREEN}Exiting...${NC}"
            exit 0
        elif [[ -n "${disk_map[$choice]:-}" ]]; then
            local selected_disk="/dev/${disk_map[$choice]}"
            echo -e "${GREEN}Selected disk: ${selected_disk}${NC}"
            echo "$selected_disk"
            return 0
        else
            echo -e "${YELLOW}Invalid selection. Please try again.${NC}"
        fi
    done
}

# ------------------------------------------------------------------------------
# SECURE ERASE USING HDPARM (for ATA drives and some SSDs)
# ------------------------------------------------------------------------------
secure_erase_hdparm() {
    local disk="$1"
    echo -e "${GREEN}Preparing to securely erase ${disk} using hdparm...${NC}"
    read -rp "Enter a temporary security password (this will be cleared): " sec_pass
    echo -e "${YELLOW}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    hdparm --user-master u --security-set-pass "$sec_pass" "$disk" || handle_error "Failed to set security password on $disk."
    hdparm --user-master u --security-erase "$sec_pass" "$disk" || handle_error "Secure Erase command failed on $disk."
    echo -e "${GREEN}Secure Erase via hdparm completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# SECURE ERASE FOR NVME USING NVME-CLI
# ------------------------------------------------------------------------------
nvme_secure_erase() {
    local disk="$1"
    echo -e "${GREEN}Preparing to format NVMe drive ${disk} using nvme-cli...${NC}"
    echo -e "${YELLOW}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    nvme format "$disk" || handle_error "nvme format failed on $disk."
    echo -e "${GREEN}NVMe format completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# WIPE DISK USING SHRED
# ------------------------------------------------------------------------------
shred_wipe() {
    local disk="$1"
    read -rp "Enter number of overwrites (recommended 3): " num_overwrites
    if ! [[ "$num_overwrites" =~ ^[0-9]+$ ]]; then
        echo -e "${YELLOW}Invalid number; defaulting to 3 overwrites.${NC}"
        num_overwrites=3
    fi
    echo -e "${GREEN}Preparing to wipe ${disk} using shred with ${num_overwrites} passes...${NC}"
    echo -e "${YELLOW}WARNING: This operation is irreversible and may take a long time.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    shred -n "$num_overwrites" -z -v "$disk" || handle_error "shred failed on $disk."
    echo -e "${GREEN}Disk wipe with shred completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# DISK ERASER MENU
# ------------------------------------------------------------------------------
disk_eraser_menu() {
    local selected_disk disk disk_type
    selected_disk=$(select_disk)
    disk=$(basename "$selected_disk")
    disk_type=$(detect_disk_type "$disk")
    echo -e "${CYAN}Detected disk type: ${disk_type}${NC}"
    echo -e "${CYAN}Select the erasure method:${NC}"
    if [[ "$disk_type" == "nvme" ]]; then
        echo -e "${CYAN}[1]${NC} NVMe Format (nvme-cli)"
        echo -e "${CYAN}[3]${NC} Shred Wipe (use with caution on SSDs)"
    elif [[ "$disk_type" == "ssd" ]]; then
        echo -e "${CYAN}[1]${NC} Secure Erase (hdparm) [Works on some SSDs]"
        echo -e "${CYAN}[3]${NC} Shred Wipe (Not recommended for SSDs)"
    elif [[ "$disk_type" == "hdd" ]]; then
        echo -e "${CYAN}[1]${NC} Secure Erase (hdparm)"
        echo -e "${CYAN}[3]${NC} Shred Wipe (multiple overwrites)"
    else
        echo -e "${CYAN}[1]${NC} Secure Erase (hdparm)"
        echo -e "${CYAN}[3]${NC} Shred Wipe"
    fi
    echo -e "${CYAN}[0]${NC} Return to Main Menu"
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
            echo -e "${YELLOW}Invalid selection. Returning to main menu.${NC}"
            return 1
            ;;
    esac
    prompt_enter
}

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${CYAN}============================================${NC}"
        echo -e "${CYAN}         Secure HDD/SSD Eraser Tool         ${NC}"
        echo -e "${CYAN}============================================${NC}"
        echo -e "${GREEN}[1]${NC} List Attached Disks"
        echo -e "${GREEN}[2]${NC} Erase a Disk"
        echo -e "${GREEN}[q]${NC} Quit"
        echo -e "${CYAN}--------------------------------------------${NC}"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                echo -e "${GREEN}Attached Disks:${NC}"
                list_disks
                prompt_enter
                ;;
            2)
                disk_eraser_menu
                ;;
            q)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${YELLOW}Invalid selection. Please try again.${NC}"
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash and as root.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${RED}ERROR: Please run this script with bash.${NC}" >&2
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
