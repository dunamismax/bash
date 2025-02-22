#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: ubuntu_voip_setup.sh
# Description: A robust, visually engaging Ubuntu VoIP setup script using the Nord
#              color theme, with strict error handling, log-level filtering,
#              colorized output, and graceful signal traps.
# Author: YourName | License: MIT | Version: 3.2
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./ubuntu_voip_setup.sh
#
# Notes:
#   - This script requires root privileges.
#   - Logs are stored at /var/log/ubuntu_voip_setup.log by default.
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
readonly LOG_FILE="/var/log/ubuntu_voip_setup.log"   # Log file path
readonly DISABLE_COLORS="${DISABLE_COLORS:-false}"     # Set to "true" to disable colored output
# Default log level is INFO. Allowed levels (case-insensitive): VERBOSE, DEBUG, INFO, WARN, ERROR, CRITICAL.
readonly DEFAULT_LOG_LEVEL="INFO"
# Users can override via environment variable LOG_LEVEL.

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
readonly NORD9='\033[38;2;129;161;193m'    # Bluish (for DEBUG)
readonly NORD10='\033[38;2;94;129;172m'    # Accent Blue
readonly NORD11='\033[38;2;191;97;106m'    # Reddish (for ERROR/CRITICAL)
readonly NORD13='\033[38;2;235;203;139m'   # Yellowish (for WARN)
readonly NORD14='\033[38;2;163;190;140m'   # Greenish (for INFO)
readonly NC='\033[0m'                      # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION FUNCTION
# ------------------------------------------------------------------------------
# Converts log level string to a numeric value.
get_log_level_num() {
    local lvl="${1^^}"  # uppercase
    case "$lvl" in
        VERBOSE|V)     echo 0 ;;
        DEBUG|D)       echo 1 ;;
        INFO|I)        echo 2 ;;
        WARN|WARNING|W) echo 3 ;;
        ERROR|E)       echo 4 ;;
        CRITICAL|C)    echo 5 ;;
        *)             echo 2 ;;  # default to INFO if unknown
    esac
}

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
# Usage: log LEVEL message
# Example: log INFO "Starting process..."
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local upper_level="${level^^}"

    # Determine numeric log level of this message and current threshold.
    local msg_level
    msg_level=$(get_log_level_num "$upper_level")
    local current_level
    current_level=$(get_log_level_num "${LOG_LEVEL:-$DEFAULT_LOG_LEVEL}")
    if (( msg_level < current_level )); then
        return 0  # Skip messages below current log threshold.
    fi

    # Choose color (only for interactive stderr output).
    local color="${NC}"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            DEBUG)   color="${NORD9}"  ;;  # Bluish
            INFO)    color="${NORD14}" ;;  # Greenish
            WARN)    color="${NORD13}" ;;  # Yellowish
            ERROR|CRITICAL) color="${NORD11}" ;;  # Reddish
            *)       color="${NC}"   ;;
        esac
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"

    # Append plain log entry to log file (no color codes)
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
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
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

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
check_network() {
    print_section "Checking Network Connectivity"
    log INFO "Verifying network connectivity..."
    if ! ping -c1 -W5 google.com &>/dev/null; then
        handle_error "No network connectivity detected. Exiting."
    else
        log INFO "Network connectivity OK."
    fi
}

update_system() {
    print_section "Updating System"
    log INFO "Updating package repository..."
    apt-get update -y || log WARN "apt-get update encountered issues."
    log INFO "Upgrading installed packages..."
    apt-get upgrade -y || log WARN "apt-get upgrade encountered issues."
}

install_packages() {
    print_section "Installing Required Packages"
    local packages=(
        bash vim nano git curl wget sudo screen tmux htop
        asterisk asterisk-config
        mariadb-server mariadb-client
    )
    log INFO "Installing required packages for the VoIP system..."
    apt-get install -y "${packages[@]}" || log WARN "One or more packages failed to install."

    log INFO "Enabling and starting Asterisk and MariaDB services..."
    systemctl enable asterisk || log WARN "Failed to enable Asterisk service."
    systemctl start asterisk || log WARN "Failed to start Asterisk service."
    systemctl enable mariadb || log WARN "Failed to enable MariaDB service."
    systemctl start mariadb || log WARN "Failed to start MariaDB service."
}

create_asterisk_user() {
    print_section "Creating Asterisk User"
    if ! id asterisk &>/dev/null; then
        log INFO "Creating 'asterisk' user..."
        useradd -m -s /bin/bash asterisk || log WARN "Failed to create 'asterisk' user."
    else
        log INFO "'asterisk' user already exists."
    fi
}

configure_asterisk() {
    print_section "Configuring Asterisk"
    log INFO "Configuring Asterisk for G.722 wideband audio..."

    local ast_config_dir="/etc/asterisk"
    mkdir -p "${ast_config_dir}" || handle_error "Failed to create Asterisk config directory: ${ast_config_dir}"

    # Create custom SIP configuration to allow only G.722 (and optionally ulaw)
    local sip_conf="${ast_config_dir}/sip_custom.conf"
    cat << 'EOF' > "$sip_conf"
[general]
; Disable all codecs first
disallow=all
; Allow high-quality wideband G.722 codec
allow=g722
; (Optional fallback: allow ulaw for legacy endpoints)
; allow=ulaw
EOF
    log INFO "Created SIP configuration at $sip_conf."

    # Create a basic dialplan in extensions_custom.conf
    local ext_conf="${ast_config_dir}/extensions_custom.conf"
    cat << 'EOF' > "$ext_conf"
[internal]
; Simple dialplan: dial a SIP endpoint (assumes endpoints are named by extension number)
exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})
 same => n,Dial(SIP/${EXTEN},20)
 same => n,Hangup()

[default]
; Fallback context plays a greeting message
exten => s,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
EOF
    log INFO "Created basic dialplan at $ext_conf."

    # Append sample SIP endpoints to the SIP configuration
    cat << 'EOF' >> "$sip_conf"

[6001]
type=friend
context=internal
host=dynamic
secret=changeme6001
callerid=Phone 6001 <6001>
disallow=all
allow=g722

[6002]
type=friend
context=internal
host=dynamic
secret=changeme6002
callerid=Phone 6002 <6002>
disallow=all
allow=g722
EOF
    log INFO "Added sample SIP endpoints to $sip_conf."

    # Reload Asterisk configuration (assumes Asterisk is running)
    if asterisk -rx "core reload" ; then
        log INFO "Asterisk configuration reloaded successfully."
    else
        log WARN "Failed to reload Asterisk configuration."
    fi
}

configure_ufw() {
    print_section "Configuring UFW Firewall"
    log INFO "Setting UFW firewall rules for SIP and RTP..."
    ufw allow 5060/udp || log WARN "Failed to allow SIP traffic on UFW."
    ufw allow 16384:32767/udp || log WARN "Failed to allow RTP traffic on UFW."
    ufw reload || log WARN "Failed to reload UFW firewall."
    log INFO "UFW firewall rules updated for SIP and RTP."
}

final_checks() {
    print_section "Final System Checks"
    log INFO "Performing final system checks..."
    log INFO "Ubuntu version: $(lsb_release -d | cut -f2)"
    log INFO "Asterisk status:" && systemctl status asterisk --no-pager
    log INFO "MariaDB status:" && systemctl status mariadb --no-pager
    df -h /
}

auto_reboot() {
    print_section "Auto Reboot"
    log INFO "Rebooting system now to apply all changes..."
    reboot
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is run with Bash.
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

    log INFO "Script execution started."

    check_network
    update_system
    install_packages
    create_asterisk_user
    configure_asterisk
    configure_ufw
    final_checks
    auto_reboot

    log INFO "Script execution finished successfully."
}

# Invoke main() if the script is executed directly.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
