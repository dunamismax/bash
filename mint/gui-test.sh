#!/bin/bash

LOG_FILE="/var/log/set_permissions.log"

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

# ------------------------------------------------------------------------------
# FIX DIRECTORY PERMISSIONS FUNCTION
# ------------------------------------------------------------------------------

# Configuration
GITHUB_DIR="/home/sawyer/github"
HUGO_PUBLIC_DIR="/home/sawyer/github/hugo/dunamismax.com/public"
HUGO_DIR="/home/sawyer/github/hugo"
SAWYER_HOME="/home/sawyer"
BASE_DIR="/home/sawyer/github"
DIR_PERMISSIONS="755"  # Directories: rwx for owner, rx for group/others
FILE_PERMISSIONS="644" # Files: rw for owner, r for group/others

# ------------------------------------------------------------------------------
# FUNCTION: fix_git_permissions
# ------------------------------------------------------------------------------
fix_git_permissions() {
    local git_dir="$1"
    echo "Setting permissions for $git_dir"
    chmod "$DIR_PERMISSIONS" "$git_dir"
    find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} \;
    find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} \;
    echo "Permissions fixed for $git_dir"
}

# ------------------------------------------------------------------------------
# MAIN FUNCTION: set_directory_permissions
# ------------------------------------------------------------------------------
set_directory_permissions() {
  # 1. Make all .sh files executable under GITHUB_DIR
  log INFO "Making all .sh files executable under $GITHUB_DIR"
  find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} \;

  # 2. Set ownership for directories
  log INFO "Setting ownership for /home/sawyer/github and /home/sawyer"
  chown -R sawyer:sawyer /home/sawyer/github
  chown -R sawyer:sawyer /home/sawyer/

  # 3. Set ownership and permissions for Hugo public directory
  log INFO "Setting ownership and permissions for Hugo public directory"
  chown -R www-data:www-data "$HUGO_PUBLIC_DIR"
  chmod -R 755 "$HUGO_PUBLIC_DIR"

  # 4. Set ownership and permissions for Hugo directory and related paths
  log INFO "Setting ownership and permissions for Hugo directory"
  chown -R caddy:caddy "$HUGO_DIR"
  chmod o+rx "$SAWYER_HOME"
  chmod o+rx "$GITHUB_DIR"
  chmod o+rx "$HUGO_DIR"
  chmod o+rx "/home/sawyer/github/hugo/dunamismax.com"

  # 5. Ensure BASE_DIR exists
  if [[ ! -d "$BASE_DIR" ]]; then
      echo "Error: Base directory $BASE_DIR does not exist."
      exit 1
  fi

  log INFO "Starting permission fixes in $BASE_DIR..."

  # 6. Find and fix .git directory permissions
  # Loop over each .git directory found within BASE_DIR
  while IFS= read -r -d '' git_dir; do
      fix_git_permissions "$git_dir"
  done < <(find "$BASE_DIR" -type d -name ".git" -print0)

  log INFO "Permission setting completed."
}

# To execute the function, simply call:
# set_directory_permissions

################################################################################
# Main
################################################################################
if [ "$(id -u)" -ne 0 ]; then
    log ERROR "This script must be run as root. Exiting."
    exit 1
fi

set_directory_permissions