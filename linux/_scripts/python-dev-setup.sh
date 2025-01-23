#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: ubuntu_setup.sh
# Description: Prepares an Ubuntu system with essential tools, pyenv, Python, and pipx-managed CLI tools.
# Author: Your Name | License: MIT
# Version: 1.0.0
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./ubuntu_setup.sh
#
# ------------------------------------------------------------------------------

# Enable strict mode: exit on error, undefined variables, or command pipeline failures
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
PYENV_ROOT="${HOME}/.pyenv"
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
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
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

    # Output to console
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

# ------------------------------------------------------------------------------
# ERROR HANDLING FUNCTION
# ------------------------------------------------------------------------------
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"  # Default exit code is 1

    # Log the error with additional context
    log ERROR "$error_message"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

    # Exit with the specified exit code
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
install_apt_dependencies() {
    log INFO "Updating apt caches..."
    sudo apt update -y

    log INFO "Upgrading existing packages..."
    sudo apt upgrade -y

    log INFO "Installing apt-based dependencies..."
    sudo apt install -y --no-install-recommends \
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
    sudo apt autoremove -y
    sudo apt clean
}

install_or_update_pyenv() {
    if [[ ! -d "${PYENV_ROOT}" ]]; then
        log INFO "Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${PYENV_ROOT}"

        # Update shell config to load pyenv automatically
        if ! grep -q 'export PYENV_ROOT' "${HOME}/.bashrc"; then
            log INFO "Adding pyenv initialization to ~/.bashrc..."
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
        pushd "${PYENV_ROOT}" >/dev/null
        git pull --ff-only
        popd >/dev/null
    fi

    # Make sure pyenv is available in the current shell
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

    CURRENT_PY3="$(pyenv global || true)"   # might be empty if not set

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

    # Refresh shell environment with the new global
    eval "$(pyenv init -)"

    # Return an indicator if we installed a new version
    if $INSTALL_NEW_PYTHON; then
        return 0
    else
        return 1
    fi
}

install_or_upgrade_pipx_and_tools() {
    local new_python_installed="${1:-false}"

    # If pipx is not installed, install it with the current Python version
    if ! command_exists pipx; then
        log INFO "Installing pipx with current Python version..."
        python -m pip install --upgrade pip  # ensure pip is up to date
        python -m pip install --user pipx
    fi

    # Ensure pipx is on PATH
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        log INFO "Adding ~/.local/bin to PATH in ~/.bashrc..."
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    # Upgrade pipx
    log INFO "Upgrading pipx..."
    pipx upgrade pipx || true

    # Reinstall all pipx tools if Python version changed
    if [[ "$new_python_installed" == "true" ]]; then
        log INFO "Python version changed; performing pipx reinstall-all to avoid breakage..."
        pipx reinstall-all
    else
        log INFO "Upgrading all pipx packages to ensure they’re current..."
        pipx upgrade-all || true
    fi

    # Install or upgrade each tool in PIPX_TOOLS
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
    log INFO "Starting Ubuntu setup script..."

    install_apt_dependencies
    install_or_update_pyenv

    # install_latest_python returns 0 if new Python was installed, 1 if not
    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi

    log INFO "================================================="
    log INFO " SUCCESS! Your system is now prepared with:"
    log INFO "   - The latest stable Python (managed via pyenv)"
    log INFO "   - pipx (re)installed and updated"
    log INFO "   - A curated set of pipx CLI tools"
    log INFO "================================================="
    log INFO "Happy coding!"
}

# Execute main if this script is run directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi