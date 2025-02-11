#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: file_encryption_toolkit.sh
# Description: An advanced file encryption, decryption, compression, and file
#              management tool that supports a wide array of operations including
#              copying, moving, deleting, advanced search, compressing/decompressing
#              files using pigz (for multicore performance), password‑based file
#              encryption/decryption, and interactive PGP operations (key creation,
#              message encryption/decryption, signing, and verification). All of these
#              functions are accessible via an interactive, Nord‑themed menu.
#
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage:
#   ./advanced_file_tool.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light gray (text)
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (success/info)
NORD8='\033[38;2;136;192;208m'   # Accent Blue (headings)
NORD9='\033[38;2;129;161;193m'   # Blue (debug)
NORD10='\033[38;2;94;129;172m'   # Purple (highlight)
NORD11='\033[38;2;191;97;106m'   # Red (errors)
NORD12='\033[38;2;208;135;112m'  # Orange (warnings)
NORD13='\033[38;2;235;203;139m'  # Yellow (labels)
NORD14='\033[38;2;163;190;140m'  # Green (OK)
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING & ERROR HANDLING FUNCTIONS
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

    case "$upper_level" in
        INFO)   color="${NORD14}" ;;  # Info: green
        WARN|WARNING)
            upper_level="WARN"
            color="${NORD12}" ;;      # Warn: orange
        ERROR)  color="${NORD11}" ;;     # Error: red
        DEBUG)  color="${NORD9}"  ;;     # Debug: blue
        *)      color="$NC"     ;;
    esac
    echo -e "[$timestamp] [$upper_level] $message"
}

handle_error() {
    local error_message="${1:-"An unknown error occurred."}"
    local exit_code="${2:-1}"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# UI HELPER FUNCTIONS
# ------------------------------------------------------------------------------
print_header() {
    clear
    echo -e "${NORD8}============================================================${NC}"
    echo -e "${NORD8}         Advanced File & Security Operations Tool          ${NC}"
    echo -e "${NORD8}============================================================${NC}"
}

print_divider() {
    echo -e "${NORD8}------------------------------------------------------------${NC}"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# FILE OPERATIONS FUNCTIONS
# ------------------------------------------------------------------------------
file_copy() {
    read -rp "Enter source file/directory: " src
    read -rp "Enter destination path: " dest
    if [[ ! -e "$src" ]]; then
        handle_error "Source '$src' does not exist."
    fi
    cp -r "$src" "$dest" && echo -e "${NORD14}Copy completed successfully.${NC}" || handle_error "Copy failed."
}

file_move() {
    read -rp "Enter source file/directory: " src
    read -rp "Enter destination path: " dest
    if [[ ! -e "$src" ]]; then
        handle_error "Source '$src' does not exist."
    fi
    mv "$src" "$dest" && echo -e "${NORD14}Move completed successfully.${NC}" || handle_error "Move failed."
}

file_delete() {
    read -rp "Enter file/directory to delete: " target
    if [[ ! -e "$target" ]]; then
        handle_error "Target '$target' does not exist."
    fi
    read -rp "Are you sure you want to delete '$target'? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf "$target" && echo -e "${NORD14}Deletion completed successfully.${NC}" || handle_error "Deletion failed."
    else
        echo -e "${NORD13}Deletion cancelled.${NC}"
    fi
}

file_search() {
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
    read -rp "Enter file or directory to compress: " target
    if [[ ! -e "$target" ]]; then
        handle_error "Target '$target' does not exist."
    fi
    read -rp "Enter output file name (e.g., archive.tar.gz): " outfile
    tar -cf - "$target" | pigz > "$outfile" && echo -e "${NORD14}Compression completed successfully.${NC}" || handle_error "Compression failed."
}

decompress_file() {
    read -rp "Enter compressed file (e.g., archive.tar.gz): " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output directory: " outdir
    mkdir -p "$outdir"
    pigz -dc "$infile" | tar -xf - -C "$outdir" && echo -e "${NORD14}Decompression completed successfully.${NC}" || handle_error "Decompression failed."
}

# ------------------------------------------------------------------------------
# FILE ENCRYPTION / DECRYPTION WITH PASSWORD (using openssl)
# ------------------------------------------------------------------------------
encrypt_file() {
    read -rp "Enter file to encrypt: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output encrypted file name: " outfile
    read -rsp "Enter password: " password; echo ""
    openssl enc -aes-256-cbc -salt -in "$infile" -out "$outfile" -pass pass:"$password" \
        && echo -e "${NORD14}File encrypted successfully.${NC}" \
        || handle_error "Encryption failed."
}

decrypt_file() {
    read -rp "Enter file to decrypt: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    read -rp "Enter output decrypted file name: " outfile
    read -rsp "Enter password: " password; echo ""
    openssl enc -d -aes-256-cbc -in "$infile" -out "$outfile" -pass pass:"$password" \
        && echo -e "${NORD14}File decrypted successfully.${NC}" \
        || handle_error "Decryption failed."
}

# ------------------------------------------------------------------------------
# PGP OPERATIONS FUNCTIONS (using gpg)
# ------------------------------------------------------------------------------
pgp_create_key() {
    echo -e "${NORD14}Launching interactive PGP key generation...${NC}"
    gpg --gen-key || handle_error "PGP key generation failed."
}

pgp_encrypt_message() {
    read -rp "Enter recipient's email or key ID: " recipient
    echo -e "${NORD14}Enter the message to encrypt. End input with a single '.' on a new line.${NC}"
    local msg=""
    while IFS= read -r line; do
        [[ "$line" == "." ]] && break
        msg+="$line"$'\n'
    done
    echo "$msg" | gpg --encrypt --armor -r "$recipient" \
        && echo -e "${NORD14}Message encrypted successfully.${NC}" \
        || handle_error "PGP encryption failed."
}

pgp_decrypt_message() {
    read -rp "Enter file containing PGP encrypted message: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    gpg --decrypt "$infile" || handle_error "PGP decryption failed."
}

pgp_sign_message() {
    echo -e "${NORD14}Enter the message to sign. End input with a single '.' on a new line.${NC}"
    local msg=""
    while IFS= read -r line; do
        [[ "$line" == "." ]] && break
        msg+="$line"$'\n'
    done
    echo "$msg" | gpg --clearsign \
        && echo -e "${NORD14}Message signed successfully.${NC}" \
        || handle_error "Signing failed."
}

pgp_verify_signature() {
    read -rp "Enter the signed file to verify: " infile
    if [[ ! -f "$infile" ]]; then
        handle_error "File '$infile' does not exist."
    fi
    gpg --verify "$infile" \
        && echo -e "${NORD14}Signature verified successfully.${NC}" \
        || handle_error "Signature verification failed."
}

# ------------------------------------------------------------------------------
# ADDITIONAL TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
calculate_checksum() {
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

# ------------------------------------------------------------------------------
# MAIN MENU
# ------------------------------------------------------------------------------
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
            q|Q) echo -e "${NORD14}Goodbye!${NC}"; exit 0 ;;
            *) echo -e "${NORD12}Invalid selection. Please choose a valid option.${NC}"; sleep 1 ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    main_menu
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
