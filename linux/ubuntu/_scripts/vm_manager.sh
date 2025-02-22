#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: vm_manager.sh
# Description: An advanced interactive virtual machine manager that allows you
#              to list, create, start, stop, delete, and monitor KVM/QEMU virtual
#              machines on Ubuntu. It uses virt‑install and virsh to guide you
#              through VM creation (including options for RAM, vCPUs, disk size,
#              and ISO download via wget) in a fully interactive, Nord‑themed
#              interface.
#
# Author: Your Name | License: MIT
# Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./vm_manager.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & ERROR TRAPPING
# ------------------------------------------------------------------------------
set -Eeuo pipefail

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Add any cleanup tasks here.
}
trap cleanup EXIT
trap 'echo -e "\n${NORD11}Operation interrupted. Returning to main menu...${NC}"' SIGINT
trap 'handle_error "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light Gray (text)
NORD7='\033[38;2;143;188;187m'   # Teal (success/info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (headings)
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD12='\033[38;2;208;135;112m'  # Orange (warnings)
NORD14='\033[38;2;163;190;140m'  # Green (labels/values)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES
# ------------------------------------------------------------------------------
VM_IMAGE_DIR="/var/lib/libvirt/images"   # Default location for VM disk images
ISO_DIR="/var/lib/libvirt/boot"            # Directory to store downloaded ISOs
mkdir -p "$ISO_DIR"
TMP_ISO="/tmp/vm_install.iso"              # Temporary ISO download location

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        echo -e "${NORD11}Error: This script must be run as root. Exiting.${NC}" >&2
        exit 1
    fi
}

print_header() {
    clear
    echo -e "${NORD8}============================================${NC}"
    echo -e "${NORD8}       Advanced VM Manager Tool             ${NC}"
    echo -e "${NORD8}============================================${NC}"
}

print_divider() {
    echo -e "${NORD8}--------------------------------------------${NC}"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

log() {
    # Usage: log [LEVEL] "message"
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local color="$NC"
    case "$upper_level" in
        INFO)  color="${NORD14}" ;;      # Info: green
        WARN|WARNING)
            upper_level="WARN"
            color="${NORD12}" ;;          # Warning: orange
        ERROR) color="${NORD11}" ;;         # Error: red
        DEBUG) color="${NORD3}"  ;;         # Debug: lighter blue
        *)     color="$NC"     ;;
    esac
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "/var/log/vm_manager.log"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
list_vms() {
    print_header
    echo -e "${NORD14}Current Virtual Machines:${NC}"
    print_divider
    # List all VMs (running and stopped)
    virsh list --all
    print_divider
    prompt_enter
}

start_vm() {
    print_header
    echo -e "${NORD14}Start a Virtual Machine:${NC}"
    list_vms
    read -rp "Enter the VM name to start: " vm_name
    if virsh start "$vm_name"; then
        echo -e "${NORD14}VM '$vm_name' started successfully.${NC}"
    else
        echo -e "${NORD11}Failed to start VM '$vm_name'.${NC}"
    fi
    prompt_enter
}

stop_vm() {
    print_header
    echo -e "${NORD14}Stop a Virtual Machine:${NC}"
    list_vms
    read -rp "Enter the VM name to stop (graceful shutdown): " vm_name
    if virsh shutdown "$vm_name"; then
        echo -e "${NORD14}Shutdown signal sent to VM '$vm_name'.${NC}"
    else
        echo -e "${NORD11}Failed to shutdown VM '$vm_name'.${NC}"
    fi
    prompt_enter
}

delete_vm() {
    print_header
    echo -e "${NORD14}Delete a Virtual Machine:${NC}"
    list_vms
    read -rp "Enter the VM name to delete: " vm_name
    read -rp "Are you sure you want to delete VM '$vm_name'? This will undefine the VM. (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${NORD12}Deletion cancelled.${NC}"
        prompt_enter
        return 0
    fi
    # Retrieve disk image path from VM XML before undefining the VM.
    local disk
    disk=$(virsh dumpxml "$vm_name" 2>/dev/null | grep -oP 'source file="\K[^"]+')
    # If the VM is running, force shutdown first.
    if virsh list --state-running | grep -qw "$vm_name"; then
        virsh destroy "$vm_name"
    fi
    if virsh undefine "$vm_name"; then
        echo -e "${NORD14}VM '$vm_name' undefined successfully.${NC}"
        if [[ -n "$disk" ]]; then
            read -rp "Do you want to remove its disk image at $disk? (y/n): " remove_disk
            if [[ "$remove_disk" =~ ^[Yy]$ ]]; then
                rm -f "$disk" && echo -e "${NORD14}Disk image removed.${NC}" || echo -e "${NORD12}Failed to remove disk image.${NC}"
            fi
        fi
    else
        echo -e "${NORD11}Failed to delete VM '$vm_name'.${NC}"
    fi
    prompt_enter
}

monitor_vm() {
    print_header
    echo -e "${NORD14}Monitor Virtual Machine Resource Usage:${NC}"
    list_vms
    read -rp "Enter the VM name to monitor: " vm_name
    echo -e "${NORD14}Press Ctrl+C to exit monitoring and return to the menu.${NC}"
    while true; do
        clear
        echo -e "${NORD8}Monitoring VM: ${NORD4}${vm_name}${NC}"
        echo -e "${NORD8}--------------------------------------------${NC}"
        virsh dominfo "$vm_name"
        echo -e "${NORD8}--------------------------------------------${NC}"
        sleep 5
    done
}

download_iso() {
    read -rp "Enter the URL for the installation ISO: " iso_url
    read -rp "Enter the desired filename (e.g., ubuntu.iso): " iso_filename
    local iso_path="${ISO_DIR}/${iso_filename}"
    echo -e "${NORD14}Downloading ISO to ${iso_path}...${NC}"
    if wget -O "$iso_path" "$iso_url"; then
        echo -e "${NORD14}ISO downloaded successfully.${NC}"
        echo "$iso_path"
    else
        echo -e "${NORD11}Failed to download ISO.${NC}"
        return 1
    fi
}

create_vm() {
    print_header
    echo -e "${NORD14}Create a New Virtual Machine:${NC}"
    read -rp "Enter VM name: " vm_name
    read -rp "Enter number of vCPUs: " vcpus
    read -rp "Enter RAM in MB: " ram
    read -rp "Enter disk size in GB: " disk_size

    # Ask user for ISO location.
    echo -e "${NORD14}Provide installation ISO:${NC}"
    echo -e "${NORD8}[1]${NC} Use existing ISO file"
    echo -e "${NORD8}[2]${NC} Download ISO via URL (wget)"
    read -rp "Enter your choice (1 or 2): " iso_choice
    local iso_path=""
    case "$iso_choice" in
        1)
            read -rp "Enter full path to ISO file: " iso_path
            if [[ ! -f "$iso_path" ]]; then
                echo -e "${NORD11}ISO file not found at $iso_path.${NC}"
                prompt_enter
                return 1
            fi
            ;;
        2)
            iso_path=$(download_iso) || return 1
            ;;
        *)
            echo -e "${NORD12}Invalid selection. Cancelling VM creation.${NC}"
            prompt_enter
            return 1
            ;;
    esac

    # Create a disk image for the VM.
    local disk_image="${VM_IMAGE_DIR}/${vm_name}.qcow2"
    echo -e "${NORD14}Creating disk image at ${disk_image}...${NC}"
    if ! qemu-img create -f qcow2 "$disk_image" "${disk_size}G"; then
        echo -e "${NORD11}Failed to create disk image.${NC}"
        prompt_enter
        return 1
    fi

    # Use virt-install to create the VM.
    echo -e "${NORD14}Starting VM installation using virt-install...${NC}"
    virt-install --name "$vm_name" \
        --ram "$ram" \
        --vcpus "$vcpus" \
        --disk path="$disk_image",size="$disk_size",format=qcow2 \
        --cdrom "$iso_path" \
        --os-type linux \
        --os-variant ubuntu20.04 \
        --graphics none \
        --console pty,target_type=serial \
        --noautoconsole

    if [[ $? -eq 0 ]]; then
        echo -e "${NORD14}VM '$vm_name' created successfully.${NC}"
    else
        echo -e "${NORD11}Failed to create VM '$vm_name'.${NC}"
    fi
    prompt_enter
}

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}[1]${NC} List Virtual Machines"
        echo -e "${NORD14}[2]${NC} Create Virtual Machine"
        echo -e "${NORD14}[3]${NC} Start Virtual Machine"
        echo -e "${NORD14}[4]${NC} Stop Virtual Machine"
        echo -e "${NORD14}[5]${NC} Delete Virtual Machine"
        echo -e "${NORD14}[6]${NC} Monitor Virtual Machine Resources"
        echo -e "${NORD14}[q]${NC} Quit"
        print_divider
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                list_vms
                ;;
            2)
                create_vm
                ;;
            3)
                start_vm
                ;;
            4)
                stop_vm
                ;;
            5)
                delete_vm
                ;;
            6)
                monitor_vm
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
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    check_root
    # Ensure required commands exist.
    for cmd in virsh virt-install qemu-img wget; do
        if ! command -v "$cmd" &>/dev/null; then
            echo -e "${NORD11}Error: Required command '$cmd' is not installed. Exiting.${NC}"
            exit 1
        fi
    done

    main_menu
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
