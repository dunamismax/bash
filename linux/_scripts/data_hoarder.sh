#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: data_hoarder.sh
# Description: An advanced interactive data hoarding and management tool for OpenSUSE.
#              This tool installs required tools, configures Kiwix for offline Wikipedia
#              (and other ZIM files), allows interactive downloading of large data files,
#              and configures remote access via a Caddy reverse proxy. All downloaded files,
#              configurations, and data are stored under a central root directory:
#              /media/WD_BLACK/data_hoarding/
#
# Features:
#   • Installs required tools with progress bars and enhanced logging.
#   • Installs and configures Kiwix (downloads the kiwix-tools tarball and extracts it).
#   • Downloads ZIM files (e.g., Wikipedia) interactively.
#   • Creates a systemd service to run kiwix-serve.
#   • Configures remote access by updating the Caddyfile and allowing the port via firewalld.
#
# Requirements:
#   • Must be run as root on OpenSUSE.
#
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/data_hoarder.log"     # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"            # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                          # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"  # Set to true to disable colored output

# Define the user under which the Kiwix service will run.
# If run with sudo, use SUDO_USER; otherwise, default to root.
KIWIX_USER="${SUDO_USER:-root}"

# Root directory for all data and downloads
DATA_ROOT="/media/WD_BLACK/data_hoarding"
mkdir -p "$DATA_ROOT" || { echo -e "ERROR: Failed to create DATA_ROOT directory: $DATA_ROOT"; exit 1; }

# Directories for Kiwix tools and ZIM files under DATA_ROOT
KIWIX_DIR="${DATA_ROOT}/kiwix-tools"
ZIM_DIR="${DATA_ROOT}/kiwix-zims"
mkdir -p "$KIWIX_DIR" "$ZIM_DIR" || { echo -e "ERROR: Failed to create required subdirectories under ${DATA_ROOT}"; exit 1; }

# Systemd service file for Kiwix and Caddy configuration file location
SERVICE_FILE="/etc/systemd/system/kiwix.service"
CADDYFILE="/etc/caddy/Caddyfile"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'   # Light text
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'
NORD8='\033[38;2;136;192;208m'   # Headings / Accent
NORD9='\033[38;2;129;161;193m'   # Debug messages
NORD10='\033[38;2;94;129;172m'   # Section headers
NORD11='\033[38;2;191;97;106m'   # Errors
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'  # Warnings
NORD14='\033[38;2;163;190;140m'  # Info / Success
NORD15='\033[38;2;180;142;173m'
NC='\033[0m'                    # Reset color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage: log [LEVEL] message
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"
    local color="$NC"

    # Only log DEBUG messages when LOG_LEVEL is DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)   color="${NORD14}" ;;  # Info / Success
            WARN|WARNING)
                upper_level="WARN"
                color="${NORD13}" ;;       # Warning
            ERROR)  color="${NORD11}" ;;  # Error
            DEBUG)  color="${NORD9}"  ;;  # Debug
            *)      color="$NC"     ;;
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
    local error_message="${1:-"An error occurred. Check the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

handle_signal() {
    log WARN "Termination signal received."
    handle_error "Script interrupted by user" 130
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Add any necessary cleanup tasks here (e.g., remove temporary files)
}

trap cleanup EXIT
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR
trap 'handle_signal' INT TERM

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# Print a styled section header using Nord accent colors
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

# A simple progress bar function (duration in seconds)
progress_bar() {
    # Usage: progress_bar "Message" duration_in_seconds
    local message="$1"
    local duration="${2:-3}"
    local steps=50
    local sleep_time
    sleep_time=$(echo "$duration / $steps" | bc -l)
    printf "\n${NORD8}%s [" "$message"
    for ((i=1; i<=steps; i++)); do
        printf "█"
        sleep "$sleep_time"
    done
    printf "]${NC}\n"
}

prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# FUNCTION: Install Required Tools and Prerequisites
# ------------------------------------------------------------------------------
install_prerequisites() {
    log INFO "Installing required tools..."
    progress_bar "Installing required tools" 8
    zypper refresh || handle_error "Failed to refresh repositories."
    zypper --non-interactive install wget tar curl firewalld || handle_error "Failed to install core prerequisites."
    systemctl enable --now firewalld || handle_error "Failed to enable firewalld."

    # Install Caddy if not already installed
    if ! command -v caddy &>/dev/null; then
        log INFO "Caddy not found. Installing Caddy..."
        zypper --non-interactive install caddy || handle_error "Failed to install Caddy."
    else
        log INFO "Caddy is already installed."
    fi
    log INFO "Required tools installed successfully."
}

# ------------------------------------------------------------------------------
# FUNCTION: Install and Configure Kiwix Tools
# ------------------------------------------------------------------------------
install_kiwix() {
    log INFO "Installing/updating Kiwix tools..."
    progress_bar "Installing Kiwix tools" 8
    pushd "$KIWIX_DIR" >/dev/null || handle_error "Failed to change directory to $KIWIX_DIR."
    local tarball_url="https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64.tar.gz"
    wget -O kiwix-tools.tar.gz "$tarball_url" || handle_error "Failed to download Kiwix tools."
    tar -xvf kiwix-tools.tar.gz || handle_error "Failed to extract Kiwix tools."
    rm -f kiwix-tools.tar.gz
    popd >/dev/null
    log INFO "Kiwix tools installed in $KIWIX_DIR."
}

# ------------------------------------------------------------------------------
# FUNCTION: Download ZIM File (e.g., Wikipedia)
# ------------------------------------------------------------------------------
download_zim() {
    mkdir -p "$ZIM_DIR" || handle_error "Failed to create ZIM directory: $ZIM_DIR."
    echo -e "${NORD8}Enter the URL for the ZIM file to download:${NC}"
    echo -e "${NORD8}Example: https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2023-12.zim${NC}"
    read -rp "URL (or press Enter for default): " zim_url
    if [[ -z "$zim_url" ]]; then
        zim_url="https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2023-12.zim"
    fi
    read -rp "Enter desired filename (e.g., wikipedia_en_all_maxi_2023-12.zim): " zim_filename
    if [[ -z "$zim_filename" ]]; then
        zim_filename=$(basename "$zim_url")
    fi
    local zim_path="${ZIM_DIR}/${zim_filename}"
    progress_bar "Downloading ZIM file" 15
    wget -O "$zim_path" "$zim_url" || handle_error "Failed to download ZIM file."
    log INFO "ZIM file downloaded to $zim_path."
    echo "$zim_path"
}

# ------------------------------------------------------------------------------
# FUNCTION: Configure Kiwix as a Systemd Service
# ------------------------------------------------------------------------------
configure_kiwix_service() {
    echo -e "${NORD8}Configuring Kiwix as a systemd service...${NC}"
    read -rp "Enter the full path to your ZIM file: " zim_file
    if [[ ! -f "$zim_file" ]]; then
        handle_error "ZIM file not found at $zim_file."
    fi
    read -rp "Enter desired port for Kiwix server (default 8080): " kiwix_port
    if [[ -z "$kiwix_port" ]]; then
        kiwix_port=8080
    fi

    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Kiwix Server
After=network.target

[Service]
ExecStart=${KIWIX_DIR}/kiwix-serve --port=${kiwix_port} ${zim_file}
Restart=always
User=${KIWIX_USER}

[Install]
WantedBy=multi-user.target
EOF

    progress_bar "Configuring Kiwix service" 5
    systemctl daemon-reload || handle_error "Failed to reload systemd daemon."
    systemctl enable kiwix || handle_error "Failed to enable Kiwix service."
    systemctl start kiwix || handle_error "Failed to start Kiwix service."
    log INFO "Kiwix service configured and started on port ${kiwix_port}."
}

# ------------------------------------------------------------------------------
# FUNCTION: Configure Remote Access via Caddy Reverse Proxy
# ------------------------------------------------------------------------------
configure_remote_access() {
    if [[ ! -f "$CADDYFILE" ]]; then
        handle_error "Caddyfile not found at $CADDYFILE."
    fi
    echo -e "${NORD8}Configuring remote access for Kiwix via Caddy...${NC}"
    read -rp "Enter the external port you want to use (e.g., 9090): " external_port
    if [[ -z "$external_port" ]]; then
        handle_error "External port cannot be empty."
    fi
    read -rp "Enter the internal Kiwix port (default 8080): " kiwix_port
    if [[ -z "$kiwix_port" ]]; then
        kiwix_port=8080
    fi

    local caddy_block
    caddy_block=$(cat <<EOF

# Kiwix Reverse Proxy
:${external_port} {
    reverse_proxy localhost:${kiwix_port}
}
EOF
)
    echo -e "${NORD8}The following block will be appended to ${CADDYFILE}:${NC}"
    echo -e "${NORD4}${caddy_block}${NC}"
    read -rp "Type 'YES' to confirm and append: " confirm
    if [[ "$confirm" != "YES" ]]; then
        echo -e "${NORD13}Operation cancelled.${NC}"
        return 1
    fi
    echo "$caddy_block" >> "$CADDYFILE"
    systemctl reload caddy || handle_error "Failed to reload Caddy."
    firewall-cmd --permanent --add-port="${external_port}/tcp" || handle_error "Failed to update firewall rules."
    firewall-cmd --reload || handle_error "Failed to reload firewall configuration."
    log INFO "Remote access configured on external port ${external_port} (Kiwix internal port: ${kiwix_port})."
}

# ------------------------------------------------------------------------------
# FUNCTION: Display Current Configuration Info
# ------------------------------------------------------------------------------
show_config() {
    echo -e "${NORD8}Current Data Hoarder Configuration:${NC}"
    echo -e "${NORD8}--------------------------------------------${NC}"
    echo -e "${NORD14}Data Root Directory:${NC} ${NORD4}${DATA_ROOT}${NC}"
    echo -e "${NORD14}Kiwix Tools Directory:${NC} ${NORD4}${KIWIX_DIR}${NC}"
    echo -e "${NORD14}ZIM Files Directory:${NC} ${NORD4}${ZIM_DIR}${NC}"
    if systemctl is-active --quiet kiwix; then
        echo -e "${NORD14}Kiwix Service:${NC} Active"
    else
        echo -e "${NORD13}Kiwix Service:${NC} Inactive"
    fi
    if grep -q "Kiwix Reverse Proxy" "$CADDYFILE"; then
        echo -e "${NORD14}Caddy Reverse Proxy:${NC} Configured"
    else
        echo -e "${NORD13}Caddy Reverse Proxy:${NC} Not Configured"
    fi
    echo -e "${NORD8}--------------------------------------------${NC}"
    prompt_enter
}

# ------------------------------------------------------------------------------
# MAIN INTERACTIVE MENU
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${NORD8}============================================${NC}"
        echo -e "${NORD8}         Data Hoarder & Kiwix Manager       ${NC}"
        echo -e "${NORD8}============================================${NC}"
        echo -e "${NORD14}[1]${NC} Install/Update Kiwix Tools"
        echo -e "${NORD14}[2]${NC} Download a ZIM File (e.g., Wikipedia)"
        echo -e "${NORD14}[3]${NC} Configure and Enable Kiwix as a Service"
        echo -e "${NORD14}[4]${NC} Configure Remote Access (Caddy Reverse Proxy)"
        echo -e "${NORD14}[5]${NC} Show Current Configuration"
        echo -e "${NORD14}[q]${NC} Quit"
        echo -e "${NORD8}--------------------------------------------${NC}"
        read -rp "Enter your choice: " choice
        case "${choice,,}" in
            1)
                install_kiwix
                prompt_enter
                ;;
            2)
                download_zim && prompt_enter
                ;;
            3)
                configure_kiwix_service
                prompt_enter
                ;;
            4)
                configure_remote_access
                prompt_enter
                ;;
            5)
                show_config
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
    check_root
    log INFO "Starting Data Hoarder and Kiwix Manager..."
    install_prerequisites
    main_menu
}

# Execute main if this script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
