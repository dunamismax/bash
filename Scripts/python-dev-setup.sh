#!/usr/bin/env bash
#
# This script installs or updates pyenv for a non-root user, installs the latest
# Python 3.x (via pyenv), and manages pipx plus a set of Python CLI tools.
#
# Usage:
#   sudo ./install_python_setup.sh <username>
#
# Note:
#   - This script is intended for Debian/Ubuntu systems (uses apt-get).
#   - Must be run as root (e.g., via sudo).
#   - You must supply a valid username as the argument.
#
# Example:
#   sudo ./install_python_setup.sh myuser

set -euo pipefail

################################################################################
# Globals & Helper Functions
################################################################################

usage() {
  echo "Usage: sudo $0 <username>"
  exit 1
}

# Check if a command exists on the system
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

################################################################################
# Function: install_or_update_pyenv
# Description:
#   Installs or updates Pyenv for the specified non-root user. Any needed
#   system-level packages are installed via sudo apt-get.
################################################################################
install_or_update_pyenv() {
  local user_home
  user_home=$(eval echo "~${USERNAME}")
  local pyenv_dir="${user_home}/.pyenv"

  # 1) Ensure Git is installed (root action)
  if ! command_exists git; then
    echo "[INFO] Installing 'git' using apt-get..."
    apt-get update -y
    apt-get install -y git
  fi

  # 2) Install or update pyenv as the non-root user
  sudo -u "$USERNAME" -H bash -c "
    set -e

    if [[ ! -d '${pyenv_dir}' ]]; then
      echo '[INFO] Installing pyenv for ${USERNAME}...'
      git clone https://github.com/pyenv/pyenv.git '${pyenv_dir}'

      # If you want pyenv-virtualenv, uncomment:
      # git clone https://github.com/pyenv/pyenv-virtualenv.git \
      #     '${pyenv_dir}/plugins/pyenv-virtualenv'

      # Append pyenv init lines to .bashrc if not present
      if [[ -f '${user_home}/.bashrc' && \$(grep -c 'export PYENV_ROOT' '${user_home}/.bashrc') -eq 0 ]]; then
        cat <<'EOF' >> '${user_home}/.bashrc'

# >>> pyenv initialization >>>
export PYENV_ROOT="\$HOME/.pyenv"
export PATH="\$PYENV_ROOT/bin:\$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "\$(pyenv init -)"
fi
# <<< pyenv initialization <<<
EOF
      fi

    else
      echo '[INFO] Updating pyenv for ${USERNAME}...'
      pushd '${pyenv_dir}' >/dev/null
      git pull --ff-only
      popd >/dev/null
    fi

    # Initialize pyenv in this subshell
    export PYENV_ROOT='${pyenv_dir}'
    export PATH=\"\$PYENV_ROOT/bin:\$PATH\"
    eval \"\$(pyenv init -)\"

    echo '[INFO] pyenv installation/update complete for ${USERNAME}.'
  "
}

################################################################################
# Function: install_latest_python
# Description:
#   Uses pyenv to find and install the latest stable Python 3.x for the user,
#   then sets it globally in pyenv. Returns 0 if a new version is installed or
#   changed, otherwise 1 (no change).
################################################################################
install_latest_python() {
  # We run this as the non-root user because pyenv is installed in that user's home.
  sudo -u "$USERNAME" -H bash -c "
    set -e

    local pyenv_dir=\"\${HOME}/.pyenv\"
    export PYENV_ROOT=\"\${pyenv_dir}\"
    export PATH=\"\${PYENV_ROOT}/bin:\$PATH\"
    eval \"\$(pyenv init -)\"

    echo '[INFO] Looking up latest stable Python 3.x via pyenv...'
    LATEST_PY3=\"\$(pyenv install -l | awk '/^[[:space:]]*3\\.[0-9]+\\.[0-9]+\$/ {latest=\$1} END{print latest}')\"

    if [[ -z \"\$LATEST_PY3\" ]]; then
      echo '[ERROR] Could not determine the latest Python 3.x version from pyenv.' >&2
      exit 1
    fi

    CURRENT_PY3=\"\$(pyenv global || true)\"
    echo '[INFO] Latest Python 3.x version is: '\$LATEST_PY3
    echo '[INFO] Currently active pyenv Python is: '\$CURRENT_PY3

    if [[ \"\$CURRENT_PY3\" != \"\$LATEST_PY3\" ]]; then
      if ! pyenv versions --bare | grep -q \"^\${LATEST_PY3}\$\"; then
        echo '[INFO] Installing Python '\$LATEST_PY3' via pyenv...'
        pyenv install \"\$LATEST_PY3\"
      fi
      echo '[INFO] Setting Python '\$LATEST_PY3' as global...'
      pyenv global \"\$LATEST_PY3\"
      exit 0  # Indicate a new version was installed
    else
      echo '[INFO] Python '\$LATEST_PY3' is already installed and set as global.'
      exit 1  # Indicate no change
    fi
  "
}

################################################################################
# Function: install_or_upgrade_pipx_and_tools
# Description:
#   Installs or upgrades pipx if missing, and manages a curated list of CLI tools.
#   If the Python version changed, pipx reinstall-all is used; otherwise, upgrades.
################################################################################
install_or_upgrade_pipx_and_tools() {
  local python_changed="$1"

  sudo -u "$USERNAME" -H bash -c "
    set -e

    # Helper to check commands in the user context
    function command_exists() {
      command -v \"\$1\" >/dev/null 2>&1
    }

    # Ensure pipx is installed
    if ! command_exists pipx; then
      echo '[INFO] Installing pipx using pip (user install)...'
      python -m pip install --upgrade pip
      python -m pip install --user pipx

      # Update PATH if ~/.local/bin is not present
      if [[ -f \"\$HOME/.bashrc\" && \$(grep -c 'export PATH=.*\\.local/bin' \"\$HOME/.bashrc\") -eq 0 ]]; then
        echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> \"\$HOME/.bashrc\"
      fi
      export PATH=\"\$HOME/.local/bin:\$PATH\"
    fi

    echo '[INFO] Upgrading pipx (if already installed)...'
    pipx upgrade pipx || true

    # List of pipx-managed tools
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

    if [[ \"\$python_changed\" == \"true\" ]]; then
      echo '[INFO] Python version changed; performing a pipx reinstall-all...'
      pipx reinstall-all
    else
      echo '[INFO] Upgrading all pipx packages...'
      pipx upgrade-all || true
    fi

    echo '[INFO] Ensuring each tool is installed/upgraded...'
    for tool in \"\${PIPX_TOOLS[@]}\"; do
      if pipx list | grep -q \"\$tool\"; then
        pipx upgrade \"\$tool\" || true
      else
        pipx install \"\$tool\" || true
      fi
    done

    echo '[INFO] pipx tools installation/upgrade complete.'
  "
}

################################################################################
# Main Script
################################################################################
main() {
  # Confirm the script is run as root
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "[ERROR] This script must be run as root (e.g., via sudo)."
    exit 1
  fi

  # Check for exactly one argument (the username)
  if [[ $# -ne 1 ]]; then
    usage
  fi

  USERNAME="$1"

  # Verify the user exists on the system
  if ! id "$USERNAME" &>/dev/null; then
    echo "[ERROR] User '$USERNAME' does not exist on this system."
    exit 1
  fi

  echo "[INFO] Installing/updating Python setup for user: $USERNAME"

  # 1) Install or update pyenv
  install_or_update_pyenv

  # 2) Install the latest Python 3.x (returns 0 if changed, 1 if no change)
  echo "[INFO] Installing the latest stable Python 3.x..."
  if install_latest_python; then
    python_changed=true
  else
    python_changed=false
  fi

  # 3) Install or upgrade pipx & CLI tools
  echo "[INFO] Installing/upgrading pipx and Python tools using pipx..."
  install_or_upgrade_pipx_and_tools "$python_changed"

  echo "[INFO] Done! Please have '$USERNAME' re-login or source their ~/.bashrc."
}

main "$@"