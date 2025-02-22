#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: universal_downloader.sh
# Description: Advanced auto download tool that lets the user choose between
#              downloading with wget or yt-dlp on Ubuntu. For yt-dlp, the script
#              prompts for a YouTube (video/playlist) link and a target download folder,
#              creating it if needed, and downloads the media in highest quality,
#              merging audio and video into an mp4 via ffmpeg. For wget, it downloads
#              the file into the specified directory.
# Author: Your Name | License: MIT | Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage:
#   ./universal_downloader.sh
#
# Notes:
#   - Ensure that wget, yt-dlp, ffmpeg, and other dependencies are installed.
#     This script will attempt to install missing dependencies using apt.
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
readonly LOG_FILE="/var/log/media_downloader.log"   # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"    # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels: VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"
LOG_LEVEL="${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}"
readonly QUIET_MODE=false                            # Set to true to suppress console output

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD8='\033[38;2;136;192;208m'   # Accent (for banner)
readonly NORD9='\033[38;2;129;161;193m'   # Blue (DEBUG)
readonly NORD11='\033[38;2;191;97;106m'   # Red (ERROR)
readonly NORD13='\033[38;2;235;203;139m'  # Yellow (WARN)
readonly NORD14='\033[38;2;163;190;140m'  # Green (INFO)
readonly NC='\033[0m'                     # Reset / No Color

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
# Usage: log LEVEL "message"
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
    if [[ "$QUIET_MODE" != true ]]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    exit "$exit_code"
}

cleanup() {
    log INFO "Cleanup: Exiting script."
    # Add any additional cleanup tasks here.
}

trap cleanup EXIT
trap 'handle_error "Script interrupted at line ${BASH_LINENO[0]:-${LINENO}}." 130' SIGINT
trap 'handle_error "Script terminated." 143' SIGTERM
trap 'handle_error "An unexpected error occurred at line ${BASH_LINENO[0]:-${LINENO}}." "$?"' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
install_prerequisites() {
    log INFO "Installing required tools..."
    sudo apt update || handle_error "Failed to update repositories."
    sudo apt install -y wget yt-dlp ffmpeg || handle_error "Failed to install prerequisites."
    log INFO "Required tools installed."
}

# ------------------------------------------------------------------------------
# DOWNLOAD FUNCTIONS
# ------------------------------------------------------------------------------
download_with_yt_dlp() {
    # Prompt for a YouTube (video/playlist) link.
    read -rp $'\n'"Enter YouTube link (video or playlist): " yt_link
    if [[ -z "$yt_link" ]]; then
        handle_error "YouTube link cannot be empty."
    fi

    # Prompt for a target download directory.
    read -rp "Enter download directory: " download_dir
    if [[ -z "$download_dir" ]]; then
        handle_error "Download directory cannot be empty."
    fi

    # Create the directory if it doesn't exist.
    if [[ ! -d "$download_dir" ]]; then
        mkdir -p "$download_dir" || handle_error "Failed to create directory: $download_dir"
        log INFO "Created directory: $download_dir"
    fi

    # Build and run the yt-dlp command:
    # -f bestvideo+bestaudio selects highest quality video and audio.
    # --merge-output-format mp4 merges them into an mp4 file.
    # -o specifies the output path and filename pattern.
    local cmd="yt-dlp -f bestvideo+bestaudio --merge-output-format mp4 -o '${download_dir}/%(title)s.%(ext)s' '${yt_link}'"
    log INFO "Starting download via yt-dlp..."
    eval "$cmd" || handle_error "yt-dlp download failed."
    log INFO "Download completed with yt-dlp."
}

download_with_wget() {
    # Prompt for a URL to download.
    read -rp $'\n'"Enter URL to download: " url
    if [[ -z "$url" ]]; then
        handle_error "URL cannot be empty."
    fi

    # Prompt for an output directory.
    read -rp "Enter output directory: " download_dir
    if [[ -z "$download_dir" ]]; then
        handle_error "Download directory cannot be empty."
    fi

    # Create the directory if it doesn't exist.
    if [[ ! -d "$download_dir" ]]; then
        mkdir -p "$download_dir" || handle_error "Failed to create directory: $download_dir"
        log INFO "Created directory: $download_dir"
    fi

    # Build and run the wget command.
    local cmd="wget -q -P '${download_dir}' '${url}'"
    log INFO "Starting download via wget..."
    eval "$cmd" || handle_error "wget download failed."
    log INFO "Download completed with wget."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Display a welcome banner.
    printf "\n%s%s%s\n" "${NORD8}" "=== Universal Downloader ===" "${NC}"
    echo "Select Download Method:"
    echo "  1) wget"
    echo "  2) yt-dlp"
    echo ""
    read -rp "Enter your choice (1 or 2): " choice

    case "$choice" in
        1)
            log INFO "User selected wget."
            download_with_wget
            ;;
        2)
            log INFO "User selected yt-dlp."
            download_with_yt_dlp
            ;;
        *)
            handle_error "Invalid selection. Please run the script again and choose 1 or 2." 1
            ;;
    esac
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    install_prerequisites
    main "$@"
    exit 0
fi
