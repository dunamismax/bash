#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: secure_disk_eraser.sh
# Description: An advanced, interactive HDD/SSD eraser tool for Ubuntu/Debian.
#              It installs required tools, lists attached disks with details,
#              detects whether a disk is an HDD or SSD, and lets the user choose
#              from several secure erasure methods (using hdparm, nvme-cli, or shred)
#              with full interactive prompts, double-check confirmations, and Nord‑themed
#              color output and progress bars.
#
# Requirements:
#   • Must be run as root.
#   • Works on Ubuntu/Debian.
#
# Tools used:
#   • hdparm – for ATA Secure Erase.
#   • nvme-cli – for NVMe formatting.
#   • shred – for multiple overwrites (suitable for HDDs).
#
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'echo -e "\n${RED}An error occurred at line ${LINENO}.${NC}"; exit 1' ERR

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'      # For errors
YELLOW='\033[38;2;235;203;139m'   # For warnings/labels
GREEN='\033[38;2;163;190;140m'    # For success/info
BLUE='\033[38;2;94;129;172m'      # For debug/highlights
CYAN='\033[38;2;136;192;208m'     # For headings/accent
GRAY='\033[38;2;216;222;233m'     # Light gray text
NC='\033[0m'                     # Reset Color

# ------------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/secure_disk_eraser.log"
DEBIAN_FRONTEND=noninteractive
TOOLS=(hdparm nvme-cli coreutils)  # coreutils provides shred

# ------------------------------------------------------------------------------
# Logging Function
# ------------------------------------------------------------------------------
log() {
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
# Progress Bar Function
# ------------------------------------------------------------------------------
progress_bar() {
    # Usage: progress_bar "Message" duration_in_seconds
    local message="$1"
    local duration="${2:-3}"
    local steps=50
    local sleep_time
    sleep_time=$(echo "$duration / $steps" | bc -l)
    printf "\n${CYAN}%s [" "$message"
    for ((i=1; i<=steps; i++)); do
        printf "█"
        sleep "$sleep_time"
    done
    printf "]${NC}\n"
}

# ------------------------------------------------------------------------------
# Install Prerequisites Function
# ------------------------------------------------------------------------------
install_prerequisites() {
    log INFO "Installing required tools..."
    progress_bar "Installing required tools" 8
    # Update repositories
    apt update || handle_error "Failed to update repositories."
    # Install hdparm and nvme-cli
    apt install -y hdparm nvme-cli coreutils || handle_error "Failed to install prerequisites."
    log INFO "Required tools installed."
}

# ------------------------------------------------------------------------------
# List Attached Disks Function
# ------------------------------------------------------------------------------
list_disks() {
    # Use lsblk to list disks and get rotational info
    # Output columns: NAME, SIZE, TYPE, ROTA (1 = HDD, 0 = SSD)
    lsblk -d -o NAME,SIZE,TYPE,ROTA,MODEL | grep "disk"
}

# ------------------------------------------------------------------------------
# Detect Disk Type Function
# ------------------------------------------------------------------------------
detect_disk_type() {
    local disk="$1"  # e.g., sda or nvme0n1
    local rota
    # For NVMe drives, assume SSD
    if [[ "$disk" == nvme* ]]; then
        echo "nvme"
    else
        # Read rotational flag from sysfs
        if [[ -f "/sys/block/${disk}/queue/rotational" ]]; then
            rota=$(cat /sys/block/"$disk"/queue/rotational)
            if [[ "$rota" -eq 1 ]]; then
                echo "hdd"
            else
                echo "ssd"
            fi
        else
            echo "unknown"
        fi
    fi
}

# ------------------------------------------------------------------------------
# Prompt User for Disk Selection
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
        # Each line: NAME SIZE TYPE ROTA MODEL
        local name size type rota model
        name=$(echo "$line" | awk '{print $1}')
        size=$(echo "$line" | awk '{print $2}')
        type=$(echo "$line" | awk '{print $3}')
        rota=$(echo "$line" | awk '{print $4}')
        model=$(echo "$line" | cut -d' ' -f5-)
        local disk_type
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
# Secure Erase using hdparm
# ------------------------------------------------------------------------------
secure_erase_hdparm() {
    local disk="$1"
    echo -e "${GREEN}Preparing to securely erase $disk using hdparm...${NC}"
    read -rp "Enter a temporary security password (will be erased after): " sec_pass
    echo -e "${YELLOW}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    progress_bar "Setting security password" 3
    hdparm --user-master u --security-set-pass "$sec_pass" "$disk" || handle_error "Failed to set security password on $disk."
    progress_bar "Issuing Secure Erase" 10
    hdparm --user-master u --security-erase "$sec_pass" "$disk" || handle_error "Secure Erase command failed on $disk."
    echo -e "${GREEN}Secure Erase via hdparm completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# Secure Erase for NVMe using nvme-cli
# ------------------------------------------------------------------------------
nvme_secure_erase() {
    local disk="$1"
    echo -e "${GREEN}Preparing to format NVMe drive $disk using nvme-cli...${NC}"
    echo -e "${YELLOW}WARNING: This operation is irreversible.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    progress_bar "Issuing NVMe format command" 10
    nvme format "$disk" || handle_error "nvme format failed on $disk."
    echo -e "${GREEN}NVMe format completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# Wipe Disk using shred
# ------------------------------------------------------------------------------
shred_wipe() {
    local disk="$1"
    read -rp "Enter number of overwrites (recommended 3): " num_overwrites
    if ! [[ "$num_overwrites" =~ ^[0-9]+$ ]]; then
        echo -e "${YELLOW}Invalid number; defaulting to 3 overwrites.${NC}"
        num_overwrites=3
    fi
    echo -e "${GREEN}Preparing to wipe $disk using shred with $num_overwrites passes...${NC}"
    echo -e "${YELLOW}WARNING: This operation is irreversible and very time-consuming.${NC}"
    read -rp "Type 'ERASE' to confirm and proceed: " confirm
    if [[ "$confirm" != "ERASE" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    progress_bar "Wiping disk with shred" 15
    shred -n "$num_overwrites" -z -v "$disk" || handle_error "shred failed on $disk."
    echo -e "${GREEN}Disk wipe with shred completed successfully on $disk.${NC}"
}

# ------------------------------------------------------------------------------
# Disk Eraser Menu
# ------------------------------------------------------------------------------
disk_eraser_menu() {
    local disk selected_disk disk_type
    selected_disk=$(select_disk)
    disk=$(basename "$selected_disk")
    disk_type=$(detect_disk_type "$disk")
    echo -e "${CYAN}Detected disk type: ${disk_type}${NC}"
    echo -e "${CYAN}Select the erasure method:${NC}"
    if [[ "$disk_type" == "nvme" ]]; then
        echo -e "${CYAN}[1]${NC} NVMe Format (nvme-cli)"
        echo -e "${CYAN}[3]${NC} Shred Wipe (use with caution on SSDs)"
        # hdparm typically doesn't work on NVMe.
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
# Main Interactive Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${CYAN}============================================${NC}"
        echo -e "${CYAN}        Secure HDD/SSD Eraser Tool          ${NC}"
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
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    log INFO "Starting Secure Disk Eraser Tool..."
    install_prerequisites
    main_menu
}

# Execute main if the script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
