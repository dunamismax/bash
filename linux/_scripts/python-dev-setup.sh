#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: python_dev_setup.sh
# Description: Prepares an OpenSUSE system with essential development tools,
#              installs/updates pyenv, the latest stable Python, and pipx‑managed
#              CLI tools using a robust Nord‑themed enhanced template.
# Author: Your Name | License: MIT
# Version: 2.0
# ------------------------------------------------------------------------------
#
# Usage Examples:
#   sudo ./python_dev_setup.sh [-d|--debug] [-q|--quiet]
#   sudo ./python_dev_setup.sh -h|--help
#
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/python_dev_setup.log"      # Log file path
SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"                  # Options: INFO, DEBUG, WARN, ERROR
QUIET_MODE=false                                # When true, suppress console output
DISABLE_COLORS="${DISABLE_COLORS:-false}"       # Set to true to disable colored output

# pyenv configuration
PYENV_ROOT="${HOME}/.pyenv"

# List of pipx-managed tools to install/upgrade
PIPX_TOOLS=(
    ansible-core
    black
    cookiecutter
    coverage
    flake8
    isort
    ipython
    mypy
    pip-tools
    pylint
    pyupgrade
    pytest
    rich-cli
    tldr
    tox
    twine
    yt-dlp
    poetry
    pre-commit
)

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # #2E3440
NORD1='\033[38;2;59;66;82m'      # #3B4252
NORD2='\033[38;2;67;76;94m'      # #434C5E
NORD3='\033[38;2;76;86;106m'     # #4C566A
NORD4='\033[38;2;216;222;233m'   # #D8DEE9
NORD5='\033[38;2;229;233;240m'   # #E5E9F0
NORD6='\033[38;2;236;239;244m'   # #ECEFF4
NORD7='\033[38;2;143;188;187m'   # #8FBCBB
NORD8='\033[38;2;136;192;208m'   # #88C0D0
NORD9='\033[38;2;129;161;193m'   # #81A1C1
NORD10='\033[38;2;94;129;172m'   # #5E81AC
NORD11='\033[38;2;191;97;106m'   # #BF616A
NORD12='\033[38;2;208;135;112m'  # #D08770
NORD13='\033[38;2;235;203;139m'  # #EBCB8B
NORD14='\033[38;2;163;190;140m'  # #A3BE8C
NORD15='\033[38;2;180;142;173m'  # #B48EAD
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

    # Only log DEBUG messages when LOG_LEVEL is DEBUG
    if [[ "$upper_level" == "DEBUG" && "${LOG_LEVEL^^}" != "DEBUG" ]]; then
        return 0
    fi

    local color="$NC"
    if [[ "$DISABLE_COLORS" != true ]]; then
        case "$upper_level" in
            INFO)   color="${NORD14}" ;;  # Greenish
            WARN)   color="${NORD13}" ;;  # Yellowish
            ERROR)  color="${NORD11}" ;;  # Reddish
            DEBUG)  color="${NORD9}"  ;;  # Bluish
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
    log ERROR "Script encountered an error at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

cleanup() {
    log INFO "Performing cleanup tasks before exit."
    # Insert any necessary cleanup tasks here (e.g., removing temporary files)
}

trap cleanup EXIT
trap 'handle_error "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

enable_debug() {
    LOG_LEVEL="DEBUG"
    log DEBUG "Debug mode enabled: Verbose logging activated."
}

enable_quiet_mode() {
    QUIET_MODE=true
    log INFO "Quiet mode enabled: Console output suppressed."
}

show_help() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Description:
  Prepares an OpenSUSE system with essential development tools,
  installs/updates pyenv, the latest stable Python, and pipx-managed CLI tools.
  Uses a Nord‑themed enhanced template for robust error handling and logging.

Options:
  -d, --debug   Enable debug (verbose) logging.
  -q, --quiet   Suppress console output.
  -h, --help    Show this help message and exit.

Examples:
  sudo $SCRIPT_NAME --debug
  sudo $SCRIPT_NAME --quiet
  sudo $SCRIPT_NAME -h
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--debug)
                enable_debug
                ;;
            -q|--quiet)
                enable_quiet_mode
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log WARN "Unknown option: $1"
                ;;
        esac
        shift
    done
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

# ------------------------------------------------------------------------------
# FUNCTION: Install Zypper-based Dependencies
# ------------------------------------------------------------------------------
install_zypper_dependencies() {
    print_section "Zypper Dependencies Installation"
    log INFO "Refreshing package repositories..."
    zypper --non-interactive refresh || handle_error "Failed to refresh repositories."

    log INFO "Upgrading existing packages..."
    zypper --non-interactive update || handle_error "Failed to update packages."

    log INFO "Installing required dependencies..."
    zypper --non-interactive install \
        gcc gcc-c++ make git curl wget vim tmux unzip zip ca-certificates \
        libopenssl-devel libffi-devel zlib-devel bzip2-devel readline-devel \
        sqlite3-devel ncurses-devel gdbm-devel nss-devel xz-devel xz \
        libxml2-devel libxmlsec1-devel tk-devel llvm gnupg lsb-release jq || \
        handle_error "Failed to install required dependencies."

    log INFO "Cleaning up package caches..."
    zypper clean --all || log WARN "Failed to clean package caches."
}

# ------------------------------------------------------------------------------
# FUNCTION: Install or Update pyenv
# ------------------------------------------------------------------------------
install_or_update_pyenv() {
    print_section "pyenv Installation/Update"
    if [[ ! -d "${PYENV_ROOT}" ]]; then
        log INFO "pyenv not found. Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${PYENV_ROOT}" || handle_error "Failed to clone pyenv."
        # Append pyenv initialization to ~/.bashrc if not present
        if ! grep -q 'export PYENV_ROOT' "${HOME}/.bashrc"; then
            log INFO "Adding pyenv initialization to ~/.bashrc..."
            cat << 'EOF' >> "${HOME}/.bashrc"

# >>> pyenv initialization >>>
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "$(pyenv init -)"
fi
# <<< pyenv initialization <<<
EOF
        fi
    else
        log INFO "pyenv is already installed. Updating pyenv..."
        pushd "${PYENV_ROOT}" >/dev/null || handle_error "Failed to enter pyenv directory."
        git pull --ff-only || handle_error "Failed to update pyenv."
        popd >/dev/null
    fi

    # Ensure pyenv is available in this session
    export PYENV_ROOT="${HOME}/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
}

# ------------------------------------------------------------------------------
# FUNCTION: Install the Latest Stable Python via pyenv
# ------------------------------------------------------------------------------
install_latest_python() {
    print_section "Python Installation via pyenv"
    log INFO "Searching for the latest stable Python 3.x version via pyenv..."
    local latest_py3
    latest_py3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')" || \
        handle_error "Failed to determine the latest Python version."

    if [[ -z "$latest_py3" ]]; then
        handle_error "Could not determine the latest Python 3.x version from pyenv."
    fi

    local current_py3
    current_py3="$(pyenv global 2>/dev/null || true)"  # may be empty if not set

    log INFO "Latest Python 3.x version available: $latest_py3"
    log INFO "Currently active pyenv Python version: ${current_py3:-None}"

    local install_new_python=false
    if [[ "$current_py3" != "$latest_py3" ]]; then
        if ! pyenv versions --bare | grep -q "^${latest_py3}\$"; then
            log INFO "Installing Python $latest_py3 via pyenv..."
            pyenv install "$latest_py3" || handle_error "Failed to install Python $latest_py3."
        fi
        log INFO "Setting Python $latest_py3 as the global version..."
        pyenv global "$latest_py3" || handle_error "Failed to set Python $latest_py3 as global."
        install_new_python=true
    else
        log INFO "Python $latest_py3 is already installed and set as global."
    fi

    # Refresh the shell environment with the new global Python
    eval "$(pyenv init -)"
    
    # Return indicator if a new Python version was installed
    if [[ "$install_new_python" == true ]]; then
        return 0
    else
        return 1
    fi
}

# ------------------------------------------------------------------------------
# FUNCTION: Install or Upgrade pipx and Its Managed Tools
# ------------------------------------------------------------------------------
install_or_upgrade_pipx_and_tools() {
    print_section "pipx Installation and Tools Update"
    local new_python_installed="${1:-false}"

    # Install pipx if it does not exist
    if ! command_exists pipx; then
        log INFO "pipx not found. Installing pipx..."
        python -m pip install --upgrade pip || handle_error "Failed to upgrade pip."
        python -m pip install --user pipx || handle_error "Failed to install pipx."
    fi

    # Ensure ~/.local/bin is in PATH; update ~/.bashrc if necessary
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        log INFO "Adding ~/.local/bin to PATH in ~/.bashrc..."
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    log INFO "Upgrading pipx..."
    pipx upgrade pipx || true

    if [[ "$new_python_installed" == true ]]; then
        log INFO "New Python version detected; running pipx reinstall-all..."
        pipx reinstall-all || true
    else
        log INFO "Upgrading all pipx packages..."
        pipx upgrade-all || true
    fi

    log INFO "Ensuring pipx-managed tools are installed and up to date..."
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            log INFO "Upgrading $tool..."
            pipx upgrade "$tool" || true
        else
            log INFO "Installing $tool..."
            pipx install "$tool" || true
        fi
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log INFO "${NORD10}${border}${NC}"
    log INFO "${NORD10}  $title${NC}"
    log INFO "${NORD10}${border}${NC}"
}

main() {
    # Ensure the script is executed with Bash
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    parse_args "$@"
    check_root

    log INFO "Starting OpenSUSE development setup script..."

    # 1. Install Zypper-based dependencies
    install_zypper_dependencies

    # 2. Install or update pyenv
    install_or_update_pyenv

    # 3. Install the latest Python version via pyenv (if needed) and update pipx tools
    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi

    log INFO "================================================="
    log INFO " SUCCESS! Your system is now prepared with:"
    log INFO "   - The latest stable Python (via pyenv)"
    log INFO "   - pipx (re)installed and updated"
    log INFO "   - A curated set of pipx-managed CLI tools"
    log INFO "================================================="
    log INFO "Happy coding!"
}

# ------------------------------------------------------------------------------
# SCRIPT INVOCATION CHECK
# ------------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
    exit 0
fi
