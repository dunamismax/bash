#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: vm_manager.sh
# Description: An advanced interactive virtual machine manager for Ubuntu,
#              built on a robust Bash script template with Nord-themed color
#              feedback, detailed logging, strict error handling, and graceful
#              signal traps.
# Author: Your Name | License: MIT | Version: 2.1
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & SET IFS
# ------------------------------------------------------------------------------
set -Eeuo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
readonly LOG_FILE="/var/log/ultimate_script.log"  # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels: VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"

# Additional global variables for VM management
readonly VM_IMAGE_DIR="/var/lib/libvirt/images"   # Default location for VM disk images
readonly ISO_DIR="/var/lib/libvirt/boot"            # Directory to store downloaded ISOs
readonly TMP_ISO="/tmp/vm_install.iso"              # Temporary ISO download location

# Ensure ISO_DIR exists
mkdir -p "$ISO_DIR"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'   # Bluish (for DEBUG)
readonly NORD10='\033[38;2;94;129;172m'    # Accent Blue (for section headers)
readonly NORD11='\033[38;2;191;97;106m'    # Reddish (for ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'   # Yellowish (for WARN)
readonly NORD14='\033[38;2;163;190;140m'   # Greenish (for INFO and labels)
readonly NC='\033[0m'                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
get_log_level_num() {
    local lvl="${1^^}"
    case "$lvl" in
        VERBOSE|V)      echo 0 ;;
        DEBUG|D)        echo 1 ;;
        INFO|I)         echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)        echo 4 ;;
        CRITICAL|C)     echo 5 ;;
        *)              echo 2 ;;  # Default to INFO
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL "message"
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"

    local msg_level
    msg_level=$(get_log_level_num "$upper_level")
    local current_level
    current_level=$(get_log_level_num "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}")
    if (( msg_level < current_level )); then
        return 0
    fi

    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)          color="${NORD9}"  ;;  # Bluish
            INFO)           color="${NORD14}" ;;  # Greenish
            WARN)           color="${NORD13}" ;;  # Yellowish
            ERROR|CRITICAL) color="${NORD11}" ;;  # Reddish
            *)              color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    # Append plain log entry to log file
    echo "$log_entry" >> "$LOG_FILE"
    # Print colorized log entry to stderr
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An unknown error occurred"}"
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
    # Add any additional cleanup tasks here.
}

# Trap signals and errors for graceful handling
trap cleanup EXIT
trap 'handle_error "Script interrupted by user." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
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

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# Clears the screen and prints a header for the VM Manager
print_header() {
    clear
    print_section "Advanced VM Manager Tool"
}

# ------------------------------------------------------------------------------
# VM MANAGEMENT FUNCTIONS
# ------------------------------------------------------------------------------
list_vms() {
    print_header
    log INFO "Current Virtual Machines:"
    echo "--------------------------------------------"
    virsh list --all || handle_error "Failed to list VMs."
    echo "--------------------------------------------"
    prompt_enter
}

start_vm() {
    print_header
    log INFO "Start a Virtual Machine:"
    list_vms
    read -rp "Enter the VM name to start: " vm_name
    if virsh start "$vm_name"; then
        log INFO "VM '$vm_name' started successfully."
    else
        log ERROR "Failed to start VM '$vm_name'."
    fi
    prompt_enter
}

stop_vm() {
    print_header
    log INFO "Stop a Virtual Machine:"
    list_vms
    read -rp "Enter the VM name to stop (graceful shutdown): " vm_name
    if virsh shutdown "$vm_name"; then
        log INFO "Shutdown signal sent to VM '$vm_name'."
    else
        log ERROR "Failed to shutdown VM '$vm_name'."
    fi
    prompt_enter
}

delete_vm() {
    print_header
    log INFO "Delete a Virtual Machine:"
    list_vms
    read -rp "Enter the VM name to delete: " vm_name
    read -rp "Are you sure you want to delete VM '$vm_name'? This will undefine the VM. (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log WARN "Deletion cancelled."
        prompt_enter
        return 0
    fi
    # Retrieve disk image path from VM XML
    local disk
    disk=$(virsh dumpxml "$vm_name" 2>/dev/null | grep -oP 'source file="\K[^"]+')
    # Force shutdown if VM is running
    if virsh list --state-running | grep -qw "$vm_name"; then
        virsh destroy "$vm_name"
    fi
    if virsh undefine "$vm_name"; then
        log INFO "VM '$vm_name' undefined successfully."
        if [[ -n "$disk" ]]; then
            read -rp "Do you want to remove its disk image at $disk? (y/n): " remove_disk
            if [[ "$remove_disk" =~ ^[Yy]$ ]]; then
                if rm -f "$disk"; then
                    log INFO "Disk image removed."
                else
                    log WARN "Failed to remove disk image."
                fi
            fi
        fi
    else
        log ERROR "Failed to delete VM '$vm_name'."
    fi
    prompt_enter
}

monitor_vm() {
    print_header
    log INFO "Monitor Virtual Machine Resource Usage:"
    list_vms
    read -rp "Enter the VM name to monitor: " vm_name
    log INFO "Press Ctrl+C to exit monitoring and return to the menu."
    while true; do
        clear
        echo -e "${NORD10}Monitoring VM: ${NORD14}${vm_name}${NC}"
        echo -e "${NORD10}--------------------------------------------${NC}"
        virsh dominfo "$vm_name"
        echo -e "${NORD10}--------------------------------------------${NC}"
        sleep 5
    done
}

download_iso() {
    read -rp "Enter the URL for the installation ISO: " iso_url
    read -rp "Enter the desired filename (e.g., ubuntu.iso): " iso_filename
    local iso_path="${ISO_DIR}/${iso_filename}"
    log INFO "Downloading ISO to ${iso_path}..."
    if wget -O "$iso_path" "$iso_url"; then
        log INFO "ISO downloaded successfully."
        echo "$iso_path"
    else
        log ERROR "Failed to download ISO."
        return 1
    fi
}

create_vm() {
    print_header
    log INFO "Create a New Virtual Machine:"
    read -rp "Enter VM name: " vm_name
    read -rp "Enter number of vCPUs: " vcpus
    read -rp "Enter RAM in MB: " ram
    read -rp "Enter disk size in GB: " disk_size

    echo -e "${NORD14}Provide installation ISO:${NC}"
    echo -e "${NORD10}[1] Use existing ISO file${NC}"
    echo -e "${NORD10}[2] Download ISO via URL (wget)${NC}"
    read -rp "Enter your choice (1 or 2): " iso_choice
    local iso_path=""
    case "$iso_choice" in
        1)
            read -rp "Enter full path to ISO file: " iso_path
            if [[ ! -f "$iso_path" ]]; then
                log ERROR "ISO file not found at $iso_path."
                prompt_enter
                return 1
            fi
            ;;
        2)
            iso_path=$(download_iso) || return 1
            ;;
        *)
            log WARN "Invalid selection. Cancelling VM creation."
            prompt_enter
            return 1
            ;;
    esac

    local disk_image="${VM_IMAGE_DIR}/${vm_name}.qcow2"
    log INFO "Creating disk image at ${disk_image}..."
    if ! qemu-img create -f qcow2 "$disk_image" "${disk_size}G"; then
        log ERROR "Failed to create disk image."
        prompt_enter
        return 1
    fi

    log INFO "Starting VM installation using virt-install..."
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
        log INFO "VM '$vm_name' created successfully."
    else
        log ERROR "Failed to create VM '$vm_name'."
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
        echo -e "--------------------------------------------"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1) list_vms ;;
            2) create_vm ;;
            3) start_vm ;;
            4) stop_vm ;;
            5) delete_vm ;;
            6) monitor_vm ;;
            q)
                log INFO "Goodbye!"
                exit 0
                ;;
            *)
                log WARN "Invalid selection. Please try again."
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

    # Ensure log directory exists; create if missing.
    local log_dir
    log_dir="$(dirname "$LOG_FILE")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    fi

    # Ensure the log file exists and set secure permissions.
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    # Check for required commands.
    for cmd in virsh virt-install qemu-img wget; do
        if ! command -v "$cmd" &>/dev/null; then
            handle_error "Required command '$cmd' is not installed. Exiting."
        fi
    done

    log INFO "Script execution started."
    main_menu
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
