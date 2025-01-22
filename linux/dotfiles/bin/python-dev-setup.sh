#!/usr/bin/env bash
set -Eeuo pipefail

################################################################################
# Trap: If something fails unexpectedly, we'll output a friendly message.
################################################################################
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

################################################################################
# Helper: Check if a command exists
################################################################################
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

################################################################################
# 0. Basic System Update & Core Packages
################################################################################
install_apt_dependencies() {
    echo "[INFO] Updating apt caches..."
    sudo apt update -y

    # Optional: If you want to also upgrade existing packages:
    sudo apt upgrade -y

    echo "[INFO] Installing apt-based dependencies..."
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

    # Optionally remove automatically installed packages no longer needed
    sudo apt autoremove -y
    sudo apt clean
}

################################################################################
# 1. Install or Update pyenv
################################################################################
install_or_update_pyenv() {
    if [[ ! -d "${HOME}/.pyenv" ]]; then
        echo "[INFO] Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${HOME}/.pyenv"
        # Optionally clone pyenv-virtualenv if you want that plugin
        # git clone https://github.com/pyenv/pyenv-virtualenv.git "${HOME}/.pyenv/plugins/pyenv-virtualenv"

        # Update your shell config to load pyenv automatically (for bash)
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
        echo "[INFO] Updating pyenv..."
        pushd "${HOME}/.pyenv" >/dev/null
        git pull --ff-only
        popd >/dev/null
    fi

    # Make sure pyenv is available in the current shell
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
}

################################################################################
# 2. Ensure We Have the Latest Python 3.x Version
################################################################################
install_latest_python() {
    echo "[INFO] Finding the latest stable Python 3.x version via pyenv..."
    LATEST_PY3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')"

    if [[ -z "$LATEST_PY3" ]]; then
        echo "[ERROR] Could not determine the latest Python 3.x version from pyenv." >&2
        exit 1
    fi

    CURRENT_PY3="$(pyenv global || true)"   # might be empty if not set

    echo "[INFO] Latest Python 3.x version is $LATEST_PY3"
    echo "[INFO] Currently active pyenv Python is $CURRENT_PY3"

    INSTALL_NEW_PYTHON=false
    if [[ "$CURRENT_PY3" != "$LATEST_PY3" ]]; then
        if ! pyenv versions --bare | grep -q "^${LATEST_PY3}\$"; then
            echo "[INFO] Installing Python $LATEST_PY3 via pyenv..."
            pyenv install "$LATEST_PY3"
        fi
        echo "[INFO] Setting Python $LATEST_PY3 as global..."
        pyenv global "$LATEST_PY3"
        INSTALL_NEW_PYTHON=true
    else
        echo "[INFO] Python $LATEST_PY3 is already installed and set as global."
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

################################################################################
# 3. pipx & Python Tooling
################################################################################
install_or_upgrade_pipx_and_tools() {
    # If pipx is not installed, install it with the current Python version
    if ! command_exists pipx; then
        echo "[INFO] Installing pipx with current Python version."
        python -m pip install --upgrade pip  # ensure pip is up to date
        python -m pip install --user pipx
    fi

    # Ensure pipx is on PATH
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    # Now that pipx is installed, ensure it’s upgraded
    pipx upgrade pipx || true

    # A list of pipx-managed tools
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

    # Detect if a new Python version was installed by checking install_latest_python()’s return code
    if [[ "${1:-false}" == "true" ]]; then
        echo "[INFO] Python version changed; performing pipx reinstall-all to avoid breakage..."
        pipx reinstall-all
    else
        echo "[INFO] Upgrading all pipx packages to ensure they’re current..."
        pipx upgrade-all || true
    fi

    # Make sure each specific tool is installed (or upgraded if present)
    echo
    echo "[INFO] Ensuring each tool in PIPX_TOOLS is installed/upgraded..."
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            pipx upgrade "$tool" || true
        else
            pipx install "$tool" || true
        fi
    done
}

################################################################################
# Main
################################################################################
main() {
    install_apt_dependencies
    install_or_update_pyenv

    # install_latest_python returns 0 if new Python was installed, 1 if not
    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi

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

# Execute main if this script is run directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi