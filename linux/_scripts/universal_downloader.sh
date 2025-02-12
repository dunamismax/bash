#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: universal_downloader.sh
# Description: Advanced auto download tool that lets the user choose between
#              downloading with wget or yt-dlp on Ubuntu. For yt-dlp, the script
#              prompts for a YouTube (video/playlist) link and a target download folder,
#              creating it if needed, and downloads the media in highest quality,
#              merging audio and video into an mp4 via ffmpeg. For wget, it downloads
#              the file into the specified directory.
#
# Author: Your Name | License: MIT
# Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage:
#   ./universal_downloader.sh
#
# Note:
#   Ensure that wget, yt-dlp, ffmpeg, and other dependencies are installed.
#   This script will attempt to install missing dependencies using apt.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE & ERROR TRAPPING
# ------------------------------------------------------------------------------
set -Eeuo pipefail

cleanup() {
    log INFO "Cleanup: Exiting script."
    # Add any additional cleanup tasks here.
}
trap cleanup EXIT
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/media_downloader.log"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
QUIET_MODE=false
DISABLE_COLORS="${DISABLE_COLORS:-false}"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (for success)
NORD8='\033[38;2;136;192;208m'   # Accent
NORD9='\033[38;2;129;161;193m'   # Blue (for debug)
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Red (for errors)
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'  # Yellow (for warnings)
NORD14='\033[38;2;163;190;140m'  # Green (for info)
NC='\033[0m'                    # Reset Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
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
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;      # Info: green
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD13}" ;;          # Warning: yellow
            ERROR) color="${NORD11}" ;;         # Error: red
            DEBUG) color="${NORD9}"  ;;         # Debug: blue
            *)     color="$NC"     ;;
        esac
    fi
    
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    if [[ "$QUIET_MODE" != true ]]; then
        printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
    fi
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# INSTALL PREREQUISITES FUNCTION
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
