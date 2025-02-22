#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: advanced_file_tool.sh
# Description: An advanced file encryption, decryption, compression, and file
#              management toolkit for Ubuntu. This interactive tool offers a
#              Nord‑themed menu for performing a wide range of operations:
#              file copy, move, delete, advanced search, multicore compression
#              (via pigz), password‑based encryption/decryption (via OpenSSL), and
#              interactive PGP operations (key management, message encryption/decryption,
#              signing, and verification).
#
# Author: Your Name | License: MIT
# Version: 3.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./advanced_file_tool.sh
#
# Notes:
#   - Some operations require root privileges.
#   - Logs are stored in /var/log/advanced_file_tool.log by default.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/advanced_file_tool.log"
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background (#2E3440)
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light gray text (#D8DEE9)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal for success/info (#8FBCBB)
NORD8='\033[38;2;136;192;208m'   # Accent blue for headings (#88C0D0)
NORD9='\033[38;2;129;161;193m'   # Blue for debug (#81A1C1)
NORD10='\033[38;2;94;129;172m'   # Purple for highlights (#5E81AC)
NORD11='\033[38;2;191;97;106m'   # Red for errors (#BF616A)
NORD12='\033[38;2;208;135;112m'  # Orange for warnings (#D08770)
NORD13='\033[38;2;235;203;139m'  # Yellow for labels (#EBCB8B)
NORD14='\033[38;2;163;190;140m'  # Green for OK messages (#A3BE8C)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log LEVEL "message"
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Green for info
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD12}" ;;      # Orange for warnings
            ERROR) color="${NORD11}" ;;     # Red for errors
            DEBUG) color="${NORD9}"  ;;     # Blue for debug
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
    local error_message="${1:-"An unknown error occurred."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Place any necessary cleanup commands here (e.g., temporary file removal)
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO in function ${FUNCNAME[1]:-main}."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# Clear the screen and print a styled header
print_header() {
    clear
    local border
    border=$(printf '─%.0s' {1..60})
    printf "%b%s%b\n" "${NORD8}" "$border" "${NC}"
    printf "%b  Advanced File & Security Operations Tool  %b\n" "${NORD8}" "${NC}"
    printf "%b%s%b\n" "${NORD8}" "$border" "${NC}"
}

print_divider() {
    printf "%b%s%b\n" "${NORD8}" "------------------------------------------------------------" "${NC}"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# FILE OPERATIONS FUNCTIONS
# ------------------------------------------------------------------------------
file_copy() {
    log INFO "Initiating file copy operation."
    read -rp "Enter source file/directory: " src
    read -rp "Enter destination path: " dest
    if [[ ! -e "$src" ]]; then
        handle_error "Source '$src' does not exist."
    fi
    cp -r "$src" "$dest" && log INFO "Copy completed successfully." || handle_error "Copy failed."
}

file_move() {
    log INFO "Initiating file move operation."
    read -rp "Enter source file/directory: " src
    read -rp "Enter destination path: " dest
    if [[ ! -e "$src" ]]; then
        handle_error "Source '$src' does not exist."
    fi
    mv "$src" "$dest" && log INFO "Move completed successfully." || handle_error "Move failed."
}

file_delete() {
    log INFO "Initiating file deletion operation."
    read -rp "Enter file/directory to delete: " target
    if [[ ! -e "$target" ]]; then
        handle_error "Target '$target' does not exist."
    fi
    read -rp "Are you sure you want to delete '$target'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf "$target" && log INFO "Deletion completed successfully." || handle_error "Deletion failed."
    else
        log WARN "Deletion cancelled by user."
        echo -e "${NORD13}Deletion cancelled.${NC}"
    fi
}

file_search() {
    log INFO "Initiating advanced file search."
    read -rp "Enter directory to search in: " search_dir
    read -rp "Enter filename pattern (e.g., *.txt): " pattern
    if [[ ! -d "$search_dir" ]]; then
        handle_error "Directory '$search_dir' does not exist."
    fi
    echo -e "${NORD14}Search results:${NC}"
    find "$search_dir" -type f -name "$pattern"
    prompt_enter
}

# ------------------------------------------------------------------------------
# COMPRESSION / DECOMPRESSION FUNCTIONS (using pigz)
# ------------------------------------------------------------------------------
compress_file() {
    log INFO "Initiating compression operation."
    read -rp "Enter file or directory to compress: " target
    if [[ ! -e "$target" ]]; then
        handle_error "Target '$target' does not exist."
    fi
    read -rp "Enter output archive name (e.g., archive.tar.gz): " outfile
    tar -cf - "$target" | pigz > "$outfile" && log INFO "Compression completed successfully." || handle_error "Compression failed."
}

decompress_file() {
    log INFO "Initiating decompression operation."
    read -rp "Enter compressed file (e.g., archive.tar.gz): " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output directory: " outdir
    mkdir -p "$outdir" || handle_error "Failed to create output directory."
    pigz -dc "$infile" | tar -xf - -C "$outdir" && log INFO "Decompression completed successfully." || handle_error "Decompression failed."
}

# ------------------------------------------------------------------------------
# FILE ENCRYPTION / DECRYPTION (PASSWORD-BASED using OpenSSL)
# ------------------------------------------------------------------------------
encrypt_file() {
    log INFO "Initiating file encryption."
    read -rp "Enter file to encrypt: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output encrypted file name: " outfile
    read -rsp "Enter password: " password; echo ""
    openssl enc -aes-256-cbc -salt -in "$infile" -out "$outfile" -pass pass:"$password" \
        && log INFO "File encrypted successfully." || handle_error "Encryption failed."
}

decrypt_file() {
    log INFO "Initiating file decryption."
    read -rp "Enter file to decrypt: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output decrypted file name: " outfile
    read -rsp "Enter password: " password; echo ""
    openssl enc -d -aes-256-cbc -in "$infile" -out "$outfile" -pass pass:"$password" \
        && log INFO "File decrypted successfully." || handle_error "Decryption failed."
}

# ------------------------------------------------------------------------------
# PGP OPERATIONS FUNCTIONS (using gpg)
# ------------------------------------------------------------------------------
pgp_create_key() {
    log INFO "Starting interactive PGP key generation."
    gpg --gen-key && log INFO "PGP key generation completed." || handle_error "PGP key generation failed."
}

pgp_encrypt_message() {
    log INFO "Initiating PGP message encryption."
    read -rp "Enter recipient's email or key ID: " recipient
    echo -e "${NORD14}Enter the message to encrypt. End input with a single '.' on a new line.${NC}"
    local msg=""
    while IFS= read -r line; do
        [[ "$line" == "." ]] && break
        msg+="$line"$'\n'
    done
    echo "$msg" | gpg --encrypt --armor -r "$recipient" \
        && log INFO "Message encrypted successfully." || handle_error "PGP encryption failed."
}

pgp_decrypt_message() {
    log INFO "Initiating PGP message decryption."
    read -rp "Enter file containing the PGP encrypted message: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    gpg --decrypt "$infile" && log INFO "PGP decryption completed." || handle_error "PGP decryption failed."
}

pgp_sign_message() {
    log INFO "Initiating message signing with PGP."
    echo -e "${NORD14}Enter the message to sign. End input with a single '.' on a new line.${NC}"
    local msg=""
    while IFS= read -r line; do
        [[ "$line" == "." ]] && break
        msg+="$line"$'\n'
    done
    echo "$msg" | gpg --clearsign \
        && log INFO "Message signed successfully." || handle_error "PGP signing failed."
}

pgp_verify_signature() {
    log INFO "Initiating PGP signature verification."
    read -rp "Enter the signed file to verify: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    gpg --verify "$infile" && log INFO "Signature verified successfully." || handle_error "Signature verification failed."
}

# ------------------------------------------------------------------------------
# ADDITIONAL TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
calculate_checksum() {
    log INFO "Starting checksum calculation."
    read -rp "Enter file to calculate checksum: " file
    if [[ ! -f "$file" ]]; then
        handle_error "File '$file' does not exist."
    fi
    echo -e "${NORD14}Select checksum type:${NC}"
    echo -e "${NORD8}[1]${NC} MD5"
    echo -e "${NORD8}[2]${NC} SHA256"
    read -rp "Enter choice (1 or 2): " type
    case "$type" in
        1)
            md5sum "$file" || handle_error "MD5 checksum calculation failed."
            ;;
        2)
            sha256sum "$file" || handle_error "SHA256 checksum calculation failed."
            ;;
        *)
            log WARN "Invalid checksum type selection."
            echo -e "${NORD12}Invalid selection.${NC}"
            ;;
    esac
    prompt_enter
}

# ------------------------------------------------------------------------------
# INTERACTIVE MENUS
# ------------------------------------------------------------------------------
file_operations_menu() {
    while true; do
        print_header
        echo -e "${NORD14}File Operations:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Copy File/Directory"
        echo -e "${NORD8}[2]${NC} Move File/Directory"
        echo -e "${NORD8}[3]${NC} Delete File/Directory"
        echo -e "${NORD8}[4]${NC} Advanced Search"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) file_copy; prompt_enter ;;
            2) file_move; prompt_enter ;;
            3) file_delete; prompt_enter ;;
            4) file_search ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

compression_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Compression / Decompression (using pigz):${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Compress File/Directory"
        echo -e "${NORD8}[2]${NC} Decompress File"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) compress_file; prompt_enter ;;
            2) decompress_file; prompt_enter ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

encryption_menu() {
    while true; do
        print_header
        echo -e "${NORD14}File Encryption / Decryption (Password-based):${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Encrypt a File"
        echo -e "${NORD8}[2]${NC} Decrypt a File"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) encrypt_file; prompt_enter ;;
            2) decrypt_file; prompt_enter ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

pgp_menu() {
    while true; do
        print_header
        echo -e "${NORD14}PGP Operations:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Create PGP Key"
        echo -e "${NORD8}[2]${NC} Encrypt Message"
        echo -e "${NORD8}[3]${NC} Decrypt Message"
        echo -e "${NORD8}[4]${NC} Sign Message"
        echo -e "${NORD8}[5]${NC} Verify Signature"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) pgp_create_key; prompt_enter ;;
            2) pgp_encrypt_message; prompt_enter ;;
            3) pgp_decrypt_message; prompt_enter ;;
            4) pgp_sign_message; prompt_enter ;;
            5) pgp_verify_signature; prompt_enter ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

additional_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Additional Tools:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} Calculate File Checksum"
        echo -e "${NORD8}[0]${NC} Return to Main Menu"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) calculate_checksum ;;
            0) break ;;
            *) echo -e "${NORD12}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
}

main_menu() {
    while true; do
        print_header
        echo -e "${NORD14}Main Menu:${NC}"
        print_divider
        echo -e "${NORD8}[1]${NC} File Operations"
        echo -e "${NORD8}[2]${NC} Compression / Decompression"
        echo -e "${NORD8}[3]${NC} File Encryption/Decryption (Password)"
        echo -e "${NORD8}[4]${NC} PGP Operations"
        echo -e "${NORD8}[5]${NC} Additional Tools"
        echo -e "${NORD8}[q]${NC} Quit"
        print_divider
        read -rp "Enter your choice: " choice
        case "$choice" in
            1) file_operations_menu ;;
            2) compression_menu ;;
            3) encryption_menu ;;
            4) pgp_menu ;;
            5) additional_menu ;;
            q|Q) log INFO "User exited the tool. Goodbye!"; echo -e "${NORD14}Goodbye!${NC}"; exit 0 ;;
            *) echo -e "${NORD12}Invalid selection. Please choose a valid option.${NC}"; sleep 1 ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure script is run with Bash and root privileges
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    check_root

    # Ensure log directory exists and secure the log file
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."
    main_menu
}

# ------------------------------------------------------------------------------
# INVOKE MAIN FUNCTION IF SCRIPT IS EXECUTED DIRECTLY
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
