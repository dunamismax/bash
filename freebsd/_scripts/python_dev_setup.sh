#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# Script Name: python-dev-setup.sh
# Description: Sets up a Python development environment on FreeBSD with pyenv,
#              pipx, and essential tools.
# Author: Your Name | License: MIT | Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./python-dev-setup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/python-dev-setup.log"  # Path to the log file

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
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

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"  # Default exit code is 1
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Log the error with additional context
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2
    exit "$exit_code"
}

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
        handle_error "This script must be run as root."
    fi
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ------------------------------------------------------------------------------
# MAIN FUNCTIONS
# ------------------------------------------------------------------------------
install_pkg_dependencies() {
    log INFO "Updating pkg caches..."
    pkg update -f

    log INFO "Upgrading existing packages..."
    pkg upgrade -y

    log INFO "Installing pkg-based dependencies..."
    pkg install -y \
        git \
        curl \
        wget \
        vim \
        tmux \
        unzip \
        zip \
        ca_root_nss \
        libffi \
        readline \
        sqlite3 \
        ncurses \
        xz \
        llvm \
        gmake \
        python3 \
        py39-pip

    log INFO "Cleaning up pkg cache..."
    pkg clean -y
}

install_or_update_pyenv() {
    if [[ ! -d "${HOME}/.pyenv" ]]; then
        log INFO "Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${HOME}/.pyenv"

        # Append pyenv initialization to ~/.bashrc if not present
        if ! grep -q 'export PYENV_ROOT' "${HOME}/.bashrc"; then
            cat <<'EOF' >> "${HOME}/.bashrc"

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
        pushd "${HOME}/.pyenv" >/dev/null
        git pull --ff-only
        popd >/dev/null
    fi

    # Ensure pyenv is available in the current shell
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
}

install_latest_python() {
    log INFO "Finding the latest stable Python 3.x version via pyenv..."
    LATEST_PY3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')"
    if [[ -z "$LATEST_PY3" ]]; then
        handle_error "Could not determine the latest Python 3.x version from pyenv."
    fi

    CURRENT_PY3="$(pyenv global || true)"   # May be empty if not set

    log INFO "Latest Python 3.x version is $LATEST_PY3"
    log INFO "Currently active pyenv Python is $CURRENT_PY3"

    INSTALL_NEW_PYTHON=false
    if [[ "$CURRENT_PY3" != "$LATEST_PY3" ]]; then
        if ! pyenv versions --bare | grep -q "^${LATEST_PY3}\$"; then
            log INFO "Installing Python $LATEST_PY3 via pyenv..."
            pyenv install "$LATEST_PY3"
        fi
        log INFO "Setting Python $LATEST_PY3 as global..."
        pyenv global "$LATEST_PY3"
        INSTALL_NEW_PYTHON=true
    else
        log INFO "Python $LATEST_PY3 is already installed and set as global."
    fi

    # Refresh shell environment with the new global version
    eval "$(pyenv init -)"

    # Return an indicator if a new version was installed
    if $INSTALL_NEW_PYTHON; then
        return 0
    else
        return 1
    fi
}

install_or_upgrade_pipx_and_tools() {
    # Install pipx if not present
    if ! command_exists pipx; then
        log INFO "Installing pipx with current Python version."
        python -m pip install --upgrade pip
        python -m pip install --user pipx
    fi

    # Ensure pipx is on PATH
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    # Upgrade pipx itself
    pipx upgrade pipx || true

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

    # If a new Python version was installed, perform a full pipx reinstall
    if [[ "${1:-false}" == "true" ]]; then
        log INFO "Python version changed; performing pipx reinstall-all to avoid breakage..."
        pipx reinstall-all
    else
        log INFO "Upgrading all pipx packages to ensure they’re current..."
        pipx upgrade-all || true
    fi

    log INFO "Ensuring each tool in PIPX_TOOLS is installed/upgraded..."
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            pipx upgrade "$tool" || true
        else
            pipx install "$tool" || true
        fi
    done
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    check_root

    # Ensure the log directory exists and is writable
    LOG_DIR=$(dirname "$LOG_FILE")
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log INFO "Script execution started."

    install_pkg_dependencies
    install_or_update_pyenv

    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi

    log INFO "Script execution finished."

    echo
    echo "================================================="
    echo " SUCCESS! Your system is now prepared with:"
    echo "   - The latest stable Python (managed via pyenv)"
    echo "   - pipx (re)installed and updated"
    echo "   - A curated set of pipx CLI tools"
    echo "================================================="
    echo
    echo "Happy coding!"
    echo
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
