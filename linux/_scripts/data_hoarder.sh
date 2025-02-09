#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: data_hoarder.sh
# Description: An advanced interactive data hoarding and management tool for Debian/Ubuntu.
#              This tool installs required tools, configures Kiwix for offline Wikipedia
#              (and other ZIM files), allows interactive downloading of large data files,
#              and configures remote access via Caddy reverse proxy. All downloaded files,
#              configurations, and data are stored under a central root directory:
#              /media/WD_BLACK/data_hoarding/
#
# Features:
#   • Installs required tools with progress bars and enhanced logging.
#   • Installs and configures Kiwix (downloads the kiwix-tools tarball and extracts it).
#   • Downloads ZIM files (e.g., Wikipedia) interactively.
#   • Creates a systemd service to run kiwix-serve.
#   • Configures remote access by updating the Caddyfile and allowing the port in UFW.
#
# Requirements:
#   • Must be run as root on Debian/Ubuntu.
#
# Author: Your Name | License: MIT
# ------------------------------------------------------------------------------
set -Eeuo pipefail
trap 'echo -e "\n${RED}An error occurred at line ${LINENO}.${NC}"; exit 1' ERR

# ------------------------------------------------------------------------------
# Nord Color Theme Constants (24-bit ANSI escapes)
# ------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'      # For errors
YELLOW='\033[38;2;235;203;139m'   # For warnings/labels
GREEN='\033[38;2;163;190;140m'    # For success/info
BLUE='\033[38;2;94;129;172m'      # For debug/highlights
CYAN='\033[38;2;136;192;208m'     # For headings/accent
GRAY='\033[38;2;216;222;233m'     # Light gray text
NC='\033[0m'                     # Reset color

# ------------------------------------------------------------------------------
# Global Variables and Directories
# ------------------------------------------------------------------------------
# Root directory for all data and downloads
DATA_ROOT="/media/WD_BLACK/data_hoarding"
mkdir -p "$DATA_ROOT" || { echo -e "${RED}Failed to create DATA_ROOT directory: $DATA_ROOT${NC}"; exit 1; }

# Directories for Kiwix tools and ZIM files under DATA_ROOT
KIWIX_DIR="${DATA_ROOT}/kiwix-tools"
ZIM_DIR="${DATA_ROOT}/kiwix-zims"

# Ensure these directories exist
mkdir -p "$KIWIX_DIR" "$ZIM_DIR" || { echo -e "${RED}Failed to create required subdirectories under ${DATA_ROOT}.${NC}"; exit 1; }

# Systemd service file for Kiwix
SERVICE_FILE="/etc/systemd/system/kiwix.service"
# Caddy configuration file location
CADDYFILE="/etc/caddy/Caddyfile"

# Log file for the script
LOG_FILE="/var/log/data_hoarder.log"

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
# Error Handling Function
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An error occurred. Check the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo -e "${RED}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
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
# Prompt function for Enter key
# ------------------------------------------------------------------------------
prompt_enter() {
    read -rp "Press Enter to continue..." dummy
}

# ------------------------------------------------------------------------------
# Function: Install Required Tools and Prerequisites
# ------------------------------------------------------------------------------
install_prerequisites() {
    log INFO "Installing required tools..."
    progress_bar "Installing required tools" 8
    apt update || handle_error "Failed to update repositories."
    apt install -y wget tar ufw curl || handle_error "Failed to install core prerequisites."
    # Install Caddy if not already installed
    if ! command -v caddy &>/dev/null; then
        log INFO "Caddy not found. Installing Caddy..."
        apt install -y debian-archive-keyring apt-transport-https || handle_error "Failed to install keyring prerequisites."
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
            | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
            || handle_error "Failed to add Caddy GPG key."
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
            | tee /etc/apt/sources.list.d/caddy-stable.list || handle_error "Failed to add Caddy repository."
        apt update || handle_error "Failed to update repositories after adding Caddy repository."
        apt install -y caddy || handle_error "Failed to install Caddy."
    else
        log INFO "Caddy is already installed."
    fi
    log INFO "Required tools installed successfully."
}

# ------------------------------------------------------------------------------
# Function: Install and Configure Kiwix Tools
# ------------------------------------------------------------------------------
install_kiwix() {
    log INFO "Installing/updating Kiwix tools..."
    progress_bar "Installing Kiwix tools" 8
    pushd "$KIWIX_DIR" >/dev/null
    local tarball_url="https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64.tar.gz"
    wget -O kiwix-tools.tar.gz "$tarball_url" || handle_error "Failed to download Kiwix tools."
    tar -xvf kiwix-tools.tar.gz || handle_error "Failed to extract Kiwix tools."
    rm -f kiwix-tools.tar.gz
    popd >/dev/null
    log INFO "Kiwix tools installed in $KIWIX_DIR."
}

# ------------------------------------------------------------------------------
# Function: Download ZIM File (e.g., Wikipedia)
# ------------------------------------------------------------------------------
download_zim() {
    mkdir -p "$ZIM_DIR"
    echo -e "${CYAN}Enter the URL for the ZIM file to download:${NC}"
    echo -e "${CYAN}Example: https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2023-12.zim${NC}"
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
# Function: Configure Kiwix as a Systemd Service
# ------------------------------------------------------------------------------
configure_kiwix_service() {
    echo -e "${CYAN}Configuring Kiwix as a systemd service...${NC}"
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
User=${USERNAME}

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
# Function: Configure Remote Access via Caddy Reverse Proxy
# ------------------------------------------------------------------------------
configure_remote_access() {
    if [[ ! -f "$CADDYFILE" ]]; then
        handle_error "Caddyfile not found at $CADDYFILE."
    fi
    echo -e "${CYAN}Configuring remote access for Kiwix via Caddy...${NC}"
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
    echo -e "${CYAN}The following block will be appended to ${CADDYFILE}:${NC}"
    echo -e "${GRAY}${caddy_block}${NC}"
    read -rp "Type 'YES' to confirm and append: " confirm
    if [[ "$confirm" != "YES" ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        return 1
    fi
    echo "$caddy_block" >> "$CADDYFILE"
    systemctl reload caddy || handle_error "Failed to reload Caddy."
    ufw allow "$external_port" || handle_error "Failed to update UFW rules."
    log INFO "Remote access configured on external port ${external_port} (Kiwix internal port: ${kiwix_port})."
}

# ------------------------------------------------------------------------------
# Function: Display Current Configuration Info
# ------------------------------------------------------------------------------
show_config() {
    echo -e "${CYAN}Current Data Hoarder Configuration:${NC}"
    echo -e "${CYAN}--------------------------------------------${NC}"
    echo -e "${GREEN}Data Root Directory:${NC} ${GRAY}${DATA_ROOT}${NC}"
    echo -e "${GREEN}Kiwix Tools Directory:${NC} ${GRAY}${KIWIX_DIR}${NC}"
    echo -e "${GREEN}ZIM Files Directory:${NC} ${GRAY}${ZIM_DIR}${NC}"
    if systemctl is-active --quiet kiwix; then
        echo -e "${GREEN}Kiwix Service:${NC} Active"
    else
        echo -e "${YELLOW}Kiwix Service:${NC} Inactive"
    fi
    if grep -q "Kiwix Reverse Proxy" "$CADDYFILE"; then
        echo -e "${GREEN}Caddy Reverse Proxy:${NC} Configured"
    else
        echo -e "${YELLOW}Caddy Reverse Proxy:${NC} Not Configured"
    fi
    echo -e "${CYAN}--------------------------------------------${NC}"
    prompt_enter
}

# ------------------------------------------------------------------------------
# Main Interactive Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        echo -e "${CYAN}============================================${NC}"
        echo -e "${CYAN}         Data Hoarder & Kiwix Manager       ${NC}"
        echo -e "${CYAN}============================================${NC}"
        echo -e "${GREEN}[1]${NC} Install/Update Kiwix Tools"
        echo -e "${GREEN}[2]${NC} Download a ZIM File (e.g., Wikipedia)"
        echo -e "${GREEN}[3]${NC} Configure and Enable Kiwix as a Service"
        echo -e "${GREEN}[4]${NC} Configure Remote Access (Caddy Reverse Proxy)"
        echo -e "${GREEN}[5]${NC} Show Current Configuration"
        echo -e "${GREEN}[q]${NC} Quit"
        echo -e "${CYAN}--------------------------------------------${NC}"
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
    log INFO "Starting Data Hoarder and Kiwix Manager..."
    install_prerequisites
    main_menu
}

# Execute main if the script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
