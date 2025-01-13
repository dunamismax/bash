#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Ubuntu Automated System Configuration Script + Python/pyenv/pipx Setup
# ------------------------------------------------------------------------------
# Description:
#   This combined script automates the configuration of a fresh Ubuntu installation by:
#
#   1) Updating APT and installing essential packages (including firewall setup with UFW).
#   2) Overwriting selected configuration files (/etc/resolv.conf, /etc/ssh/sshd_config)
#      and backing up the originals.
#   3) Granting sudo privileges to the user "sawyer" and configuring Bash as the default shell.
#   4) Configuring Plex Media Server.
#   5) Adding Python environment setup (pyenv + pipx) for the latest stable Python 3.x
#      plus a curated set of Python CLI tools.
#
# Notes:
#   • All log output is appended to /var/log/ubuntu_setup.log.
#   • This script uses set -euo pipefail, along with a trap handler to catch unexpected errors.
#   • Run as root on a new Ubuntu installation or a rollback snapshot for testing.
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Trap errors and print a friendly message
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# --------------------------------------
# CONFIGURATION
# --------------------------------------

LOG_FILE="/var/log/ubuntu_setup.log"
USERNAME="sawyer"
PRIMARY_IFACE=""    # Will be detected automatically, if possible

# List of packages to install for the core system configuration
PACKAGES=(
  vim bash zsh tmux mc nano fish screen
  git perl python3 python3-pip
  curl wget tcpdump rsync rsnapshot
  htop sudo bash-completion zsh-common neofetch tig bat fd-find jq iftop nmap tree fzf lynx
  gcc build-essential lighttpd smartmontools
  duplicity ffmpeg restic
  qemu-kvm libvirt-daemon-system libvirt-clients virt-manager
)

# Ensure that our log file exists and is world-readable (harmless but helpful)
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

################################################################################
# Function: log
# Simple timestamped logger
################################################################################
log() {
  echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

################################################################################
# Function: handle_error
# Just an extra message (though we’ve already set a trap at the top)
################################################################################
handle_error() {
  log "An error occurred. Check the log for details."
  exit 1
}

################################################################################
# Function: identify_primary_iface
# Identify the primary network interface on Ubuntu
################################################################################
identify_primary_iface() {
  log "Identifying primary network interface..."

  if command -v ip &>/dev/null; then
    PRIMARY_IFACE=$(ip route show default 2>/dev/null | awk '/default via/ {print $5}' | head -n1)
    if [ -n "$PRIMARY_IFACE" ]; then
      log "Primary network interface found: $PRIMARY_IFACE"
      return
    fi
  fi

  log "No primary network interface was detected."
}

################################################################################
# Function: bootstrap_and_install_pkgs
# apt-get update and install our base PACKAGES
################################################################################
bootstrap_and_install_pkgs() {
  log "Updating APT database and upgrading existing packages..."
  apt-get update -y 2>&1 | tee -a "$LOG_FILE"
  apt-get upgrade -y 2>&1 | tee -a "$LOG_FILE"

  local packages_to_install=()
  for pkg in "${PACKAGES[@]}"; do
    # If not installed, queue it up for installation
    if ! dpkg -s "$pkg" &>/dev/null; then
      packages_to_install+=("$pkg")
    else
      log "Package '$pkg' is already installed."
    fi
  done

  if [ ${#packages_to_install[@]} -gt 0 ]; then
    log "Installing packages: ${packages_to_install[*]}"
    apt-get install -y "${packages_to_install[@]}" 2>&1 | tee -a "$LOG_FILE"
  else
    log "All listed packages are already installed. No action needed."
  fi

  apt-get autoremove -y 2>&1 | tee -a "$LOG_FILE"
  apt-get autoclean -y 2>&1 | tee -a "$LOG_FILE"

  log "Package installation process completed."
}

################################################################################
# Function: configure_firewall
# Basic UFW firewall
################################################################################
configure_firewall() {
  log "Configuring UFW firewall..."

  # Enable UFW if not active
  if ! ufw status | grep -q "Status: active"; then
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    # Allow Plex inbound
    ufw allow 32400/tcp
    ufw allow 32400/udp
    ufw --force enable
    log "UFW is now enabled with SSH and Plex allowed."
  else
    log "UFW is already active. Skipping initial setup."
  fi
}

################################################################################
# Function: overwrite_resolv_conf
# Overwrite /etc/resolv.conf
################################################################################
overwrite_resolv_conf() {
  log "Backing up and overwriting /etc/resolv.conf..."

  local resolv_conf="/etc/resolv.conf"

  # Remove symlink if systemd-resolved
  if [ -L "$resolv_conf" ]; then
    rm -f "$resolv_conf"
    log "Removed symlink at /etc/resolv.conf."
  elif [ -f "$resolv_conf" ]; then
    mv "$resolv_conf" "${resolv_conf}.bak"
    log "Backed up existing $resolv_conf to ${resolv_conf}.bak."
  fi

  cat << 'EOF' > "$resolv_conf"
# Manually configured resolv.conf
nameserver 1.1.1.1
nameserver 9.9.9.9
nameserver 127.0.0.53
options edns0
EOF

  log "Completed overwriting /etc/resolv.conf."
}

################################################################################
# Function: overwrite_sshd_config
# Overwrite /etc/ssh/sshd_config
################################################################################
overwrite_sshd_config() {
  log "Backing up and overwriting /etc/ssh/sshd_config..."

  local sshd_config="/etc/ssh/sshd_config"
  if [ -f "$sshd_config" ]; then
    cp "$sshd_config" "${sshd_config}.bak"
    log "Backed up existing $sshd_config to ${sshd_config}.bak"
  fi

  cat << 'EOF' > "$sshd_config"
# Basic Ubuntu SSHD Configuration

Port 22
AddressFamily any
ListenAddress 0.0.0.0
PermitRootLogin no
MaxAuthTries 6
MaxSessions 10
AuthorizedKeysFile      .ssh/authorized_keys
IgnoreRhosts yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
UsePAM yes
ClientAliveInterval 300
ClientAliveCountMax 3
Subsystem       sftp    /usr/lib/openssh/sftp-server
EOF

  chown root:root "$sshd_config"
  chmod 644 "$sshd_config"
  log "Completed overwriting /etc/ssh/sshd_config. Restarting sshd..."
  systemctl restart ssh 2>&1 | tee -a "$LOG_FILE"
}

################################################################################
# Function: configure_sudoers
# Configure user in the sudo group
################################################################################
configure_sudoers() {
  log "Configuring sudoers for $USERNAME..."

  # Ensure user exists
  if ! id "$USERNAME" &>/dev/null; then
    useradd -m -s /bin/bash "$USERNAME"
    log "Created user '$USERNAME'."
  fi

  # Add user to the sudo group
  usermod -aG sudo "$USERNAME"

  # Ensure /etc/sudoers has a rule for %sudo
  local sudoers_file="/etc/sudoers"
  local sudo_rule="%sudo ALL=(ALL:ALL) ALL"

  if ! grep -q "^%sudo" "$sudoers_file"; then
    echo "$sudo_rule" >> "$sudoers_file"
    log "Added group 'sudo' rule to /etc/sudoers."
  else
    log "Group 'sudo' rule already exists in /etc/sudoers."
  fi
}

################################################################################
# Function: set_default_shell_and_env
# Bash as default shell for the user, plus a sample .bashrc / .bash_profile
################################################################################
set_default_shell_and_env() {
  log "Setting Bash as default shell for $USERNAME..."
  local bash_path="/bin/bash"

  if ! id "$USERNAME" &>/dev/null; then
    log "User '$USERNAME' not found. Exiting..."
    exit 1
  fi

  chsh -s "$bash_path" "$USERNAME" 2>&1 | tee -a "$LOG_FILE" || true

  local user_home
  user_home=$(eval echo "~$USERNAME")
  local bashrc_file="$user_home/.bashrc"
  local bash_profile_file="$user_home/.bash_profile"

  cat << 'EOF' > "$bashrc_file"
#!/bin/bash
# ~/.bashrc: executed by bash(1) for interactive shells.

case $- in
    *i*) ;;
    *) return ;;
esac

PS1='\[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ '
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

alias ls='ls -lah --color=auto'
alias grep='grep --color=auto'

export HISTCONTROL=ignoredups:erasedups
export HISTSIZE=1000
export HISTFILESIZE=2000
shopt -s histappend

export PAGER='less -R'
export LESS='-R'

if [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
fi
EOF

  cat << 'EOF' > "$bash_profile_file"
#!/bin/bash
# ~/.bash_profile: executed by bash(1) for login shells.

if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
EOF

  chown "$USERNAME":"$USERNAME" "$bashrc_file" "$bash_profile_file"
  chmod 644 "$bashrc_file" "$bash_profile_file"

  log "Shell and environment configured for $USERNAME."
}

################################################################################
# Function: finalize_configuration
# apt-get full-upgrade, enable and start Plex
################################################################################
finalize_configuration() {
  log "Finalizing configuration (apt-get full-upgrade, clean, etc.)..."

  apt-get update -y 2>&1 | tee -a "$LOG_FILE"
  apt-get full-upgrade -y 2>&1 | tee -a "$LOG_FILE"
  apt-get autoremove -y 2>&1 | tee -a "$LOG_FILE"
  apt-get autoclean -y 2>&1 | tee -a "$LOG_FILE"

  systemctl enable plexmediaserver
  systemctl start plexmediaserver

  log "Final configuration steps completed."
}

# ---------------------------------------------------------------------------
# NOW: Incorporate the new script that sets up pyenv + pipx + Python toolchain
# We'll wrap that script content into a function "setup_pyenv_and_python_tools"
# and call it at the end of our main run.
# ---------------------------------------------------------------------------

################################################################################
# Additional Script: setup_pyenv_and_python_tools
################################################################################

setup_pyenv_and_python_tools() {

  echo "[INFO] Running integrated pyenv+pipx setup..."

  # 0. Basic System Update & Core Packages (our script already does apt-get update/upgrade,
  #    but we’ll keep the logic from the snippet in case someone runs this part stand-alone.)

  install_apt_dependencies() {
      echo "[INFO] Updating apt caches..."
      sudo apt-get update -y
      sudo apt-get upgrade -y

      echo "[INFO] Installing apt-based dependencies..."
      sudo apt-get install -y --no-install-recommends \
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
          jq \
          nginx

      sudo apt-get autoremove -y
      sudo apt-get clean
  }

  # 1. Install or Update pyenv
  install_or_update_pyenv() {
      if [[ ! -d "${HOME}/.pyenv" ]]; then
          echo "[INFO] Installing pyenv..."
          git clone https://github.com/pyenv/pyenv.git "${HOME}/.pyenv"

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

      export PYENV_ROOT="$HOME/.pyenv"
      export PATH="$PYENV_ROOT/bin:$PATH"
      eval "$(pyenv init -)"
  }

  # 2. Ensure We Have the Latest Python 3.x Version
  install_latest_python() {
      echo "[INFO] Finding the latest stable Python 3.x version via pyenv..."
      LATEST_PY3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')"

      if [[ -z "$LATEST_PY3" ]]; then
          echo "[ERROR] Could not determine the latest Python 3.x version from pyenv." >&2
          exit 1
      fi

      CURRENT_PY3="$(pyenv global || true)"
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

      eval "$(pyenv init -)"

      if $INSTALL_NEW_PYTHON; then
          return 0
      else
          return 1
      fi
  }

  # 3. pipx & Python Tooling
  command_exists() {
      command -v "$1" >/dev/null 2>&1
  }

  install_or_upgrade_pipx_and_tools() {
      if ! command_exists pipx; then
          echo "[INFO] Installing pipx with current Python version."
          python -m pip install --upgrade pip
          python -m pip install --user pipx
      fi

      if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
          echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
      fi
      export PATH="$HOME/.local/bin:$PATH"

      pipx upgrade pipx || true

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

      if [[ "${1:-false}" == "true" ]]; then
          echo "[INFO] Python version changed; performing pipx reinstall-all..."
          pipx reinstall-all
      else
          echo "[INFO] Upgrading all pipx packages..."
          pipx upgrade-all || true
      fi

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

  # We'll define a "main" flow for Python environment setup
  local_python_env_main() {
      # (We’ll skip calling install_apt_dependencies() by default here because
      #  the main ubuntu config script portion already calls apt-get update/upgrade
      #  plus installs many packages. If you want, you can uncomment below line.)
      # install_apt_dependencies

      install_or_update_pyenv

      # If install_latest_python returns 0 => new Python installed
      if install_latest_python; then
          install_or_upgrade_pipx_and_tools "true"
      else
          install_or_upgrade_pipx_and_tools "false"
      fi

      echo
      echo "================================================="
      echo " Python + pyenv + pipx Setup Complete"
      echo "================================================="
      echo
  }

  # Execute the local main
  local_python_env_main
}

################################################################################
# MAIN
################################################################################
main() {
  log "--------------------------------------"
  log "Starting Ubuntu Automated System Configuration Script"

  identify_primary_iface
  bootstrap_and_install_pkgs
  configure_firewall
  overwrite_resolv_conf
  overwrite_sshd_config
  configure_sudoers
  set_default_shell_and_env
  finalize_configuration

  # Now integrate our new Python environment setup
  setup_pyenv_and_python_tools

  log "Configuration script finished successfully."
  log "--------------------------------------"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi