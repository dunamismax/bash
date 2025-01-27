#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: python_dev_setup.sh
# Description: Prepares an Ubuntu system with essential tools, pyenv, Python,
#              and pipx-managed CLI tools.
#
# Usage:
#   sudo ./python_dev_setup.sh
#
# Requirements:
#   - Root privileges
#   - Bash 4+
#
# Author: Your Name | License: MIT
# Version: 1.0.1
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# For more information, see:
#   https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-"An error occurred. Check the log for details."}"
    local exit_code="${2:-1}"

    log ERROR "$error_message"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."
    exit "$exit_code"
}

trap 'handle_error "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES (CONFIGURATION)
# ------------------------------------------------------------------------------
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
# COLOR CONSTANTS (Used for Logging)
# ------------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    # Usage:
    #   log [LEVEL] "Message text"
    #
    # Example:
    #   log INFO "Installing apt dependencies..."
    # ----------------------------------------------------------------------------

    local level="${1:-INFO}"
    shift
    local message="$*"

    # Get timestamp
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"

    # Determine color based on level
    local upper_level="${level^^}"
    local color_code="$NC"
    case "$upper_level" in
        INFO)   color_code="$GREEN"  ;;
        WARN|WARNING)
            upper_level="WARN"
            color_code="$YELLOW"
            ;;
        ERROR)  color_code="$RED"    ;;
        DEBUG)  color_code="$BLUE"   ;;
        *)      upper_level="INFO"   ;;
    esac

    # Construct log entry
    local log_entry="[$timestamp] [$upper_level] $message"

    # Print to console (stderr) with color
    printf "%b%s%b\n" "$color_code" "$log_entry" "$NC" >&2
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    # Ensure script is run as root
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

command_exists() {
    # Check if a command is available on the PATH
    command -v "$1" >/dev/null 2>&1
}

# ------------------------------------------------------------------------------
# MAIN LOGIC FUNCTIONS
# ------------------------------------------------------------------------------
install_apt_dependencies() {
    log INFO "Updating apt caches..."
    apt update -y

    log INFO "Upgrading existing packages..."
    apt upgrade -y

    log INFO "Installing apt-based dependencies..."
    apt install -y --no-install-recommends \
        build-essential \
        make \
        git \
        curl \
        wget \
        vim \
        tmux \
        unzip \
        zip \
        ca-certificates \
        libssl-dev \
        libffi-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncursesw5-dev \
        libgdbm-dev \
        libnss3-dev \
        liblzma-dev \
        xz-utils \
        libxml2-dev \
        libxmlsec1-dev \
        tk-dev \
        llvm \
        software-properties-common \
        apt-transport-https \
        gnupg \
        lsb-release \
        jq

    log INFO "Cleaning up unused packages..."
    apt autoremove -y
    apt clean
}

install_or_update_pyenv() {
    # Install or update pyenv
    if [[ ! -d "${PYENV_ROOT}" ]]; then
        log INFO "Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${PYENV_ROOT}"

        # Update shell config
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
        log INFO "Updating pyenv..."
        pushd "${PYENV_ROOT}" >/dev/null
        git pull --ff-only
        popd >/dev/null
    fi

    # Ensure pyenv is available in this session
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
}

install_latest_python() {
    # Determine the latest stable Python 3.x version and install if needed
    log INFO "Finding the latest stable Python 3.x version via pyenv..."
    local latest_py3
    latest_py3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')"

    if [[ -z "$latest_py3" ]]; then
        handle_error "Could not determine the latest Python 3.x version from pyenv."
    fi

    local current_py3
    current_py3="$(pyenv global || true)"  # might be empty if not set

    log INFO "Latest Python 3.x version is $latest_py3"
    log INFO "Currently active pyenv Python is $current_py3"

    local install_new_python=false
    if [[ "$current_py3" != "$latest_py3" ]]; then
        if ! pyenv versions --bare | grep -q "^${latest_py3}\$"; then
            log INFO "Installing Python $latest_py3 via pyenv..."
            pyenv install "$latest_py3"
        fi
        log INFO "Setting Python $latest_py3 as global..."
        pyenv global "$latest_py3"
        install_new_python=true
    else
        log INFO "Python $latest_py3 is already installed and set as global."
    fi

    # Refresh the shell environment with the new global
    eval "$(pyenv init -)"

    # Return an indicator if we installed a new version
    if [[ "$install_new_python" == true ]]; then
        return 0
    else
        return 1
    fi
}

install_or_upgrade_pipx_and_tools() {
    local new_python_installed="${1:-false}"

    # Install pipx if not present
    if ! command_exists pipx; then
        log INFO "Installing pipx..."
        python -m pip install --upgrade pip  # ensure pip is up-to-date
        python -m pip install --user pipx
    fi

    # Ensure ~/.local/bin is in PATH
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        log INFO "Adding ~/.local/bin to PATH in ~/.bashrc..."
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    # Upgrade pipx itself
    log INFO "Upgrading pipx..."
    pipx upgrade pipx || true

    # If we installed a new Python version, pipx reinstall-all
    if [[ "$new_python_installed" == true ]]; then
        log INFO "New Python version detected; running pipx reinstall-all..."
        pipx reinstall-all
    else
        log INFO "Upgrading all pipx packages..."
        pipx upgrade-all || true
    fi

    # Ensure all tools in PIPX_TOOLS are installed/upgraded
    log INFO "Ensuring pipx-managed tools are up to date..."
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            pipx upgrade "$tool" || true
        else
            pipx install "$tool" || true
        fi
    done
}

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
main() {
    log INFO "Starting Ubuntu setup script..."

    # Check if running as root
    check_root

    # 1. Install apt-based dependencies
    install_apt_dependencies

    # 2. Install or update pyenv
    install_or_update_pyenv

    # 3. Install the latest Python version if needed
    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi

    log INFO "================================================="
    log INFO " SUCCESS! Your system is now prepared with:"
    log INFO "   - The latest stable Python (via pyenv)"
    log INFO "   - pipx (re)installed and updated"
    log INFO "   - A curated set of pipx CLI tools"
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
