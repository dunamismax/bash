#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: create_user_alpine.sh
# Description: Standalone Alpine Linux Bash script to create a user,
#              add the user to the wheel group, install and configure doas.
#              Uses robust error handling, detailed logging, and the Nord
#              color theme for visually appealing terminal output.
# Author: YourName | License: MIT
# Version: 1.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./create_user_alpine.sh <username>
#
# Notes:
#   - This script must be run as root.
#   - Logs are stored in /var/log/create_user_alpine.log.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/create_user_alpine.log"
SCRIPT_NAME="$(basename "$0")"
DISABLE_COLORS="${DISABLE_COLORS:-false}"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NC='\033[0m'                    # No Color

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
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)  color="${NORD14}" ;;  # Greenish
            WARN)  color="${NORD13}" ;;  # Yellowish
            ERROR) color="${NORD11}" ;;  # Reddish
            DEBUG) color="${NORD9}"  ;;  # Bluish
            *)     color="$NC"       ;;
        esac
    fi
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [$upper_level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

# Convenience wrapper for informational messages.
log_info() {
    log INFO "$@"
}

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"Unknown error occurred"}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here.
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

# ------------------------------------------------------------------------------
# CREATE USER FUNCTION
# ------------------------------------------------------------------------------
create_user() {
  # Check if the user already exists.
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' already exists. Skipping user creation."
  else
    log_info "Creating user '$USERNAME'..."
    # Create a new user with the default home directory and ash as shell.
    if ! adduser -D "$USERNAME"; then
      handle_error "Failed to create user '$USERNAME'." 1
    fi
    # Set a default password (change 'changeme' as needed).
    if ! echo "$USERNAME:changeme" | chpasswd; then
      handle_error "Failed to set password for '$USERNAME'." 1
    fi
    log_info "User '$USERNAME' created successfully."
  fi

  # Ensure the user is in the 'wheel' group for admin privileges.
  if id -nG "$USERNAME" | grep -qw "wheel"; then
    log_info "User '$USERNAME' is already in the wheel group. Skipping group addition."
  else
    log_info "Adding user '$USERNAME' to wheel group..."
    if ! adduser "$USERNAME" wheel; then
      handle_error "Failed to add user '$USERNAME' to wheel group." 1
    fi
    log_info "User '$USERNAME' added to wheel group successfully."
  fi

  # Install doas if not already installed.
  if ! command -v doas &>/dev/null; then
    log_info "Installing doas..."
    if ! apk add --no-cache doas; then
      handle_error "Failed to install doas." 1
    fi
    log_info "doas installed successfully."
  fi

  # Configure doas for the wheel group.
  local doas_conf_dir="/etc/doas.d"
  local doas_conf_file="${doas_conf_dir}/doas.conf"
  if [ ! -d "$doas_conf_dir" ]; then
    log_info "Creating directory $doas_conf_dir..."
    if ! mkdir -p "$doas_conf_dir"; then
      handle_error "Failed to create directory $doas_conf_dir." 1
    fi
  fi

  # If doas.conf exists and already contains a permit rule for wheel, skip.
  if [ -f "$doas_conf_file" ] && grep -q -E '^permit( +nopass)?( +persist)? +:wheel' "$doas_conf_file"; then
    log_info "doas configuration for wheel group already exists. Skipping doas configuration."
  else
    log_info "Configuring doas for wheel group..."
    echo "permit persist :wheel" > "$doas_conf_file" || handle_error "Failed to write doas configuration to $doas_conf_file." 1
    # Ensure proper permissions for doas.conf.
    chmod 0400 "$doas_conf_file" || handle_error "Failed to set permissions for $doas_conf_file." 1
    log_info "doas configured successfully."
  fi
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    check_root

    # Ensure a username is provided as an argument.
    if [ "$#" -ne 1 ]; then
      echo -e "${NORD11}Usage: $SCRIPT_NAME <username>${NC}"
      exit 1
    fi

    USERNAME="$1"

    # Ensure log directory exists and create the log file if needed.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
      mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
}