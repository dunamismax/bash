#!/bin/bash

LOG_FILE="/var/log/testgui.log"

################################################################################
# Function: logging function
################################################################################
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Define color codes
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'  # No Color

    # Validate log level and set color
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            ;;
        DEBUG)
            local color="${BLUE}"
            ;;
        *)
            local color="${NC}"
            level="INFO"
            ;;
    esac

    # Ensure the log file exists and is writable
    if [[ -z "${LOG_FILE:-}" ]]; then
        LOG_FILE="/var/log/example_script.log"
    fi
    if [[ ! -e "$LOG_FILE" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
    fi

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"

    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"

    # Output to console based on verbosity
    if [[ "$VERBOSE" -ge 2 ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    elif [[ "$VERBOSE" -ge 1 && "$level" == "ERROR" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

################################################################################
# Function: Install GUI
################################################################################
install_gui() {
    log INFO "Starting installation of GUI components..."

    # Ensure non-interactive environment
    export DEBIAN_FRONTEND=noninteractive

    # Step 1: Update package lists
    log INFO "Updating package lists..."
    if apt update -y; then
        log INFO "Successfully updated package lists."
    else
        log ERROR "Failed to update package lists. Exiting."
        exit 10
    fi

    # Step 2: Install GNOME Desktop, GNOME Tweaks, and additional fonts
    log INFO "Installing GNOME Desktop, GNOME Tweaks, and additional fonts..."
    if apt install -y gnome gnome-tweaks gnome-shell-extensions gnome-software \
       gnome-terminal gnome-control-center fonts-cantarell fonts-dejavu \
       fonts-ubuntu adwaita-icon-theme-full ttf-mscorefonts-installer \
       gnome-shell-extension-prefs \
       fonts-roboto fonts-open-sans fonts-droid-fallback fonts-liberation \
       fonts-powerline; then
        log INFO "Successfully installed GUI components and additional fonts."
    else
        log ERROR "Failed to install GUI components. Exiting."
        exit 20
    fi

    # Step 3: Clean up unnecessary packages
    log INFO "Cleaning up unnecessary packages..."
    if apt autoremove -y && apt autoclean -y; then
        log INFO "System cleanup complete."
    else
        log WARN "System cleanup encountered issues. Proceeding anyway."
    fi

    # Completion message
    log INFO "Installation of GUI components and fonts complete."
    log INFO "Consider restarting the system with 'reboot' or restarting the display manager with 'systemctl restart gdm'."
}

################################################################################
# Main
################################################################################
if [ "$(id -u)" -ne 0 ]; then
    log ERROR "This script must be run as root. Exiting."
    exit 1
fi

install_gui