#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: universal_downloader.sh
# Description: Advanced auto download tool that lets the user choose between
#              downloading with wget or yt-dlp. For yt-dlp, the script will ask
#              for a YouTube (video/playlist) link, a target download folder (creating
#              it if needed), and then download the media in highest quality, merging
#              audio and video into an mp4 via ffmpeg. For wget, it downloads the file
#              into the specified directory. Both options display a beautiful Nord‑
#              themed progress bar.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   ./media_downloader.sh
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/media_downloader.log"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
QUIET_MODE=false
DISABLE_COLORS="${DISABLE_COLORS:-false}"
REFRESH_INTERVAL=0.1   # Progress bar refresh interval

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escapes)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Background Dark
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'   # Teal (for success messages)
NORD8='\033[38;2;136;192;208m'   # Accent
NORD9='\033[38;2;129;161;193m'
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Red (for errors)
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'
NORD14='\033[38;2;163;190;140m'  # Green (for info)
NC='\033[0m'                    # No Color

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
            INFO)  color="${NORD14}" ;;  # Info: green
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD13}" ;;      # Warn: yellow
            ERROR) color="${NORD11}" ;;     # Error: red
            DEBUG) color="${NORD9}"  ;;     # Debug: blue
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
# PROGRESS BAR FUNCTION
# ------------------------------------------------------------------------------
# run_with_progress runs a given command in the background and displays a Nord‑
# themed progress bar until the command completes.
run_with_progress() {
    local cmd="$1"
    local message="$2"
    
    # Start the command in background.
    eval "$cmd" &
    local pid=$!
    
    local steps=50
    local progress=0
    # Display initial message.
    printf "\n${NORD8}%s [%s] 0%%%s" "$message" "$(printf '%0.s░' $(seq 1 $steps))" "${NC}"
    
    # Loop until the process ends.
    while kill -0 "$pid" 2>/dev/null; do
        progress=$(( (progress + 1) % (steps+1) ))
        local filled=$(printf '%0.s█' $(seq 1 $progress))
        local unfilled=$(printf '%0.s░' $(seq 1 $((steps - progress))))
        local percent=$(( progress * 100 / steps ))
        printf "\r${NORD8}%s [%s%s] %3d%%%s" "$message" "$filled" "$unfilled" "$percent" "${NC}"
        sleep "$REFRESH_INTERVAL"
    done
    wait "$pid"
    # Ensure the progress bar is complete.
    printf "\r${NORD8}%s [%s] 100%%%s\n" "$message" "$(printf '%0.s█' $(seq 1 $steps))" "${NC}"
}

# ------------------------------------------------------------------------------
# DOWNLOAD FUNCTIONS
# ------------------------------------------------------------------------------
download_with_yt_dlp() {
    # Prompt for YouTube link.
    read -rp $'\n'"Enter YouTube link (video or playlist): " yt_link
    if [[ -z "$yt_link" ]]; then
        handle_error "YouTube link cannot be empty."
    fi

    # Prompt for download directory.
    read -rp "Enter download directory: " download_dir
    if [[ -z "$download_dir" ]]; then
        handle_error "Download directory cannot be empty."
    fi

    # Create directory if it doesn't exist.
    if [[ ! -d "$download_dir" ]]; then
        mkdir -p "$download_dir" || handle_error "Failed to create directory: $download_dir"
        log INFO "Created directory: $download_dir"
    fi

    # Build yt-dlp command:
    # -f bestvideo+bestaudio selects best quality video and audio.
    # --merge-output-format mp4 combines them into a single mp4.
    # -o specifies output directory and filename pattern.
    local cmd="yt-dlp -f bestvideo+bestaudio --merge-output-format mp4 -o '${download_dir}/%(title)s.%(ext)s' '${yt_link}'"
    log INFO "Starting download via yt-dlp..."
    run_with_progress "$cmd" "Downloading with yt-dlp"
    log INFO "Download completed with yt-dlp."
}

download_with_wget() {
    # Prompt for URL.
    read -rp $'\n'"Enter URL to download: " url
    if [[ -z "$url" ]]; then
        handle_error "URL cannot be empty."
    fi

    # Prompt for output directory.
    read -rp "Enter output directory: " download_dir
    if [[ -z "$download_dir" ]]; then
        handle_error "Download directory cannot be empty."
    fi

    # Create directory if it doesn't exist.
    if [[ ! -d "$download_dir" ]]; then
        mkdir -p "$download_dir" || handle_error "Failed to create directory: $download_dir"
        log INFO "Created directory: $download_dir"
    fi

    # Build wget command.
    # -q disables default output; we rely on our progress bar.
    # --show-progress is disabled to let our custom progress bar be shown.
    local cmd="wget -q -P '${download_dir}' '${url}'"
    log INFO "Starting download via wget..."
    run_with_progress "$cmd" "Downloading with wget"
    log INFO "Download completed with wget."
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Display welcome banner.
    printf "\n%s%s%s\n" "${NORD8}" "=== Media Downloader ===" "${NC}"
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
    main "$@"
    exit 0
fi