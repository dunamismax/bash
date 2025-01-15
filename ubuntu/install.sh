#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Ubuntu Automated System Configuration Script
# ------------------------------------------------------------------------------
# DESCRIPTION:
#   Automates the initial setup of a fresh Ubuntu system by:
#     1) Syncing package repositories and installing/updating core packages
#        (e.g., build tools, curl, git).
#     2) Backing up, then overwriting certain system configs
#        (e.g., '/etc/ssh/ssh_config') to apply recommended security and
#        custom settings.
#     3) Creating or configuring a user account (default: "sawyer") with:
#         - Sudo privileges
#         - Bash as the default shell
#
# USAGE & REQUIREMENTS:
#   - Change all instances of "sawyer" in the code to whatever your username is before running.
#   - Run as root or via 'sudo'; non-root execution lacks necessary privileges.
#   - Works on Ubuntu (may also function on derivative distros).
#   - Review all overwriting steps before use; backups of replaced files are
#     stored with timestamps in the same directory.
#
# LOGGING:
#   - All operations and errors are logged to '/var/log/ubuntu_setup.log'
#     for troubleshooting.
#
# ERROR HANDLING:
#   - 'set -euo pipefail' aborts on errors, unbound variables, or failed pipes.
#   - Trapped 'ERR' ensures a graceful exit on unexpected failures.
#
# AUTHOR & LICENSE:
#   - Author: dunamismax
#   - License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Trap any error and output a helpful message
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/ubuntu_setup.log"
USERNAME="sawyer"

# Essential Ubuntu packages for a baseline system
# (You can expand or refine this list according to your needs.)
PACKAGES=(
  # Shells and terminal utilities
  bash
  zsh
  fish
  vim
  nano
  mc
  screen
  tmux

  # Basic development tools
  build-essential
  cmake
  exim4
  openssh-server
  libtool
  pkg-config
  libssl-dev
  bzip2
  libbz2-dev
  libffi-dev
  zlib1g-dev
  libreadline-dev
  libsqlite3-dev
  tk-dev
  xz-utils
  libncurses5-dev
  python3
  python3-dev
  python3-pip
  python3-venv
  libfreetype6-dev

  # Generic system utilities
  git
  ufw
  perl
  curl
  wget
  tcpdump
  rsync
  htop
  sudo
  passwd
  bash-completion
  neofetch
  tig
  jq
  nmap
  tree
  fzf
  lynx
  which
  patch
  smartmontools
  ntfs-3g

  # Virtualization (optional; remove if not needed)
  qemu-kvm
  libvirt-daemon-system
  libvirt-clients
  virtinst
  bridge-utils

  # Optional tools
  chrony          # For time synchronization
  fail2ban        # Intrusion prevention
  ffmpeg          # Multimedia processing
  restic          # Backup tool
)

# Ensure the main log file exists and is world-readable
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# ------------------------------------------------------------------------------
# MAIN SCRIPT START
# You can add functions below (e.g., apt updates, config overwrites) and then
# call them in your "main" block at the end.
# ------------------------------------------------------------------------------

################################################################################
# Function: log
# Simple timestamped logger
################################################################################
log() {
  local message="$1"
  echo "[$(date +"%Y-%m-%d %H:%M:%S")] $message" | tee -a "$LOG_FILE"
}

################################################################################
# Function: handle_error
################################################################################
handle_error() {
  log "An error occurred. Check the log for details."
}

################################################################################
# enable_non_free_firmware_only
# Description:
#   1) Backs up /etc/apt/sources.list
#   2) Adds "restricted multiverse non-free-firmware" (and nothing else) to
#      existing lines referencing Ubuntu in /etc/apt/sources.list, skipping duplicates.
#   3) Updates package lists.
################################################################################

enable_non_free_firmware_only() {
  echo "[INFO] Backing up /etc/apt/sources.list to /etc/apt/sources.list.bak"
  cp -a /etc/apt/sources.list /etc/apt/sources.list.bak

  echo "[INFO] Ensuring 'restricted multiverse non-free-firmware' is added to Ubuntu lines without duplicating."
  sed -i '/^deb .*ubuntu/ {/restricted/! s/$/ restricted/;};
          /^deb .*ubuntu/ {/multiverse/! s/$/ multiverse/;};
          /^deb .*ubuntu/ {/non-free-firmware/! s/$/ non-free-firmware/;}' /etc/apt/sources.list

  echo "[INFO] Updating package lists..."
  apt update

  echo "[INFO] Done. You may reboot or reload necessary modules for the changes to take effect."
}

################################################################################
# Function: install and enable sudo
################################################################################
enable_sudo() {
  export PATH=$PATH:/usr/sbin
  log "Enabling sudo."
  apt install -y sudo
  apt install -y net-tools
  usermod -aG sudo $USERNAME
  log "User '$USERNAME' has been added to the sudo group. Log out and back in for the changes to take effect."
}

################################################################################
# Function: bootstrap_and_install_pkgs
# apt update/upgrade and install our base PACKAGES
################################################################################
bootstrap_and_install_pkgs() {
  log "Updating apt package list and upgrading existing packages..."
  apt update -y 2>&1 | tee -a "$LOG_FILE"
  apt upgrade -y 2>&1 | tee -a "$LOG_FILE"

  local packages_to_install=()
  for pkg in "${PACKAGES[@]}"; do
    # If not installed, queue it up for installation
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
      packages_to_install+=("$pkg")
    else
      log "Package '$pkg' is already installed."
    fi
  done

  if [ ${#packages_to_install[@]} -gt 0 ]; then
    log "Installing packages: ${packages_to_install[*]}"
    apt install -y "${packages_to_install[@]}" 2>&1 | tee -a "$LOG_FILE"
  else
    log "All listed packages are already installed. No action needed."
  fi

  apt autoremove -y 2>&1 | tee -a "$LOG_FILE"
  apt clean -y 2>&1 | tee -a "$LOG_FILE"

  log "Package installation process completed."
}

################################################################################
# Function: configure_sudo_access
# Description:
#   1) Installs the sudo package if missing.
#   2) Ensures $USERNAME is in the 'sudo' group.
################################################################################
configure_sudo_access() {
  # 1) Ensure sudo is installed
  echo "[INFO] Installing sudo package (if not already installed)..."
  apt-get update -y
  apt-get install -y sudo

  # 2) Add the user to the 'sudo' group
  echo "[INFO] Adding '$USERNAME' to the sudo group..."
  if id "$USERNAME" &>/dev/null; then
    usermod -aG sudo "$USERNAME"
  else
    echo "[WARNING] User '$USERNAME' does not exist. Please create the user before configuring sudo."
    return 1
  fi
}

################################################################################
# Function: overwrite_ssh_config
# Overwrite /etc/ssh/ssh_config
################################################################################
overwrite_ssh_config() {
  log "Backing up and overwriting /etc/ssh/ssh_config..."

  local ssh_config="/etc/ssh/ssh_config"
  if [ -f "$ssh_config" ]; then
    cp "$ssh_config" "${ssh_config}.bak"
    log "Backed up existing $ssh_config to ${ssh_config}.bak"
  fi

  cat << 'EOF' > "$ssh_config"
# Basic Ubuntu SSH Configuration

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

  chown root:root "$ssh_config"
  chmod 644 "$ssh_config"
  log "Completed overwriting /etc/ssh/ssh_config. Restarting ssh service..."

  # Restart the service using Ubuntu's service name
  systemctl restart ssh 2>&1 | tee -a "$LOG_FILE"
}

################################################################################
# Function: set_default_shell_and_env
# Description:
#   Deletes (overwrites) and recreates ~/.profile, ~/.bash_profile, and ~/.bashrc
#   for $USERNAME.
################################################################################
set_default_shell_and_env() {
  log "Recreating .profile, .bash_profile, and .bashrc for $USERNAME..."

  # Dynamically determine the user's home directory
  local user_home
  user_home=$(eval echo "~$USERNAME")

  # File paths
  local bashrc_file="$user_home/.bashrc"
  local bash_profile_file="$user_home/.bash_profile"
  local profile_file="$user_home/.profile"

  # Overwrite the .bash_profile file with the specified contents
  log "Creating $bash_profile_file with default content..."
  cat << 'EOF' > "$bash_profile_file"
# ~/.bash_profile
# Always source ~/.bashrc to ensure consistent shell environment setup
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi
EOF

  # Set ownership and permissions for the .bash_profile file
  chown "$USERNAME":"$USERNAME" "$bash_profile_file"
  chmod 644 "$bash_profile_file"
  log ".bash_profile created successfully."

  # Overwrite the .profile file with the specified contents (like .bash_profile)
  log "Creating $profile_file with default content..."
  cat << 'EOF' > "$profile_file"
# ~/.profile
# Always source ~/.bashrc to ensure consistent shell environment setup
if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
EOF

  # Set ownership and permissions for the .profile file
  chown "$USERNAME":"$USERNAME" "$profile_file"
  chmod 644 "$profile_file"
  log ".profile created successfully."

  # Overwrite the .bashrc file
  log "Creating $bashrc_file with default content..."
  cat << 'EOF' > "$bashrc_file"
# ~/.bashrc: executed by bash(1) for non-login shells.
# ------------------------------------------------------------------------------
# Purpose:
#   This file configures your interactive Bash shell, defining environment
#   variables, initializing pyenv, setting up command history preferences,
#   enabling a fancy prompt, providing helpful aliases, and defining functions
#   for Python virtual environment management.
#
#   It also handles bash-completion (if available), making commands more
#   convenient to type.
#
# Note:
#   - This file is read for interactive non-login shells. For login shells,
#     ~/.bash_profile or ~/.profile typically point here if you want the same
#     configuration (depending on your distribution).
#   - If you have separate user-defined aliases, you can place them in
#     ~/.bash_aliases, which is sourced at the end of this file (if it exists).
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# 1. Early return if not running interactively
# ------------------------------------------------------------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# ------------------------------------------------------------------------------
# 2. Environment variables
# ------------------------------------------------------------------------------
# Add your local bin directory to PATH.
export PATH="$PATH:$HOME/.local/bin"

# ------------------------------------------------------------------------------
# 3. pyenv initialization
# ------------------------------------------------------------------------------
# Adjust these lines according to your Python environment needs.
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if command -v pyenv 1>/dev/null 2>&1; then
    # Initialize pyenv so that it can manage your Python versions and virtualenvs.
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# ------------------------------------------------------------------------------
# 4. History preferences
# ------------------------------------------------------------------------------
# Do not store duplicate lines or lines that start with a space in the history.
HISTCONTROL=ignoreboth

# Allow appending to the history file (instead of overwriting it).
shopt -s histappend

# Set history limits (number of lines in memory / on disk).
HISTSIZE=10000
HISTFILESIZE=20000

# Add timestamps to each command in history (for auditing).
HISTTIMEFORMAT="%F %T "

# Re-check window size after each command, updating LINES and COLUMNS if needed.
shopt -s checkwinsize

# ------------------------------------------------------------------------------
# 5. Less (pager) setup
# ------------------------------------------------------------------------------
# Make 'less' more friendly for non-text input files, see lesspipe(1).
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# ------------------------------------------------------------------------------
# 6. Bash prompt (PS1)
# ------------------------------------------------------------------------------
# Identify if we are in a Ubuntu chroot environment and set ubuntu_chroot.
if [ -z "${ubuntu_chroot:-}" ] && [ -r /etc/ubuntu_chroot ]; then
    ubuntu_chroot=$(cat /etc/ubuntu_chroot)
fi

# If terminal supports color, enable a colored prompt.
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

# Uncomment the line below if you always want a color prompt (if supported).
# force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        # We have color support; assume it's compliant with Ecma-48 (ISO/IEC-6429).
        color_prompt=yes
    else
        color_prompt=
    fi
fi

# Choose a colored or plain prompt.
if [ "$color_prompt" = yes ]; then
    PS1='${ubuntu_chroot:+($ubuntu_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
else
    PS1='${ubuntu_chroot:+($ubuntu_chroot)}\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm or rxvt terminal, set the window title to user@host:dir.
case "$TERM" in
    xterm*|rxvt*)
        PS1="\[\e]0;${ubuntu_chroot:+($ubuntu_chroot)}\u@\h: \w\a\]$PS1"
        ;;
    *)
        ;;
esac

# ------------------------------------------------------------------------------
# 7. Color support for common commands
# ------------------------------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    # alias dir='dir --color=auto'
    # alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# ------------------------------------------------------------------------------
# 8. Handy aliases
# ------------------------------------------------------------------------------
# Basic ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Launch ranger file manager
alias r='ranger'

# Alert alias for long running commands (use: sleep 10; alert)
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" \
"$(history|tail -n1|sed -e '\''s/^\s*[0-9]\+\s*//;s/[;&|]\s*alert$//'\'')"'

# ------------------------------------------------------------------------------
# 9. Python virtual environment functions and aliases
# ------------------------------------------------------------------------------
# Alias to quickly set up a new Python virtual environment
alias venv='setup_venv'
# Alias to quickly re-enable an existing Python virtual environment
alias v='enable_venv'

# Function to set up a new Python virtual environment in the current directory
setup_venv() {
    # If there's already a venv active, deactivate it first
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
    fi

    echo "Creating a new virtual environment in $(pwd)/.venv..."
    python -m venv .venv

    echo "Activating the virtual environment..."
    source .venv/bin/activate

    if [ -f requirements.txt ]; then
        echo "Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    else
        echo "No requirements.txt found. Skipping pip install."
    fi

    echo "Virtual environment setup complete."
}

# Function to re-enable an existing Python virtual environment in the current directory
enable_venv() {
    # If there's already a venv active, deactivate it first
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
    fi

    echo "Activating the virtual environment..."
    source .venv/bin/activate

    if [ -f requirements.txt ]; then
        echo "Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    else
        echo "No requirements.txt found. Skipping pip install."
    fi

    echo "Virtual environment setup complete."
}

# ------------------------------------------------------------------------------
# 10. Load user-defined aliases from ~/.bash_aliases (if it exists)
# ------------------------------------------------------------------------------
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# ------------------------------------------------------------------------------
# 11. Bash completion
# ------------------------------------------------------------------------------
# Enable programmable completion features if not in POSIX mode.
# (Examples: git completion, docker completion, etc.)
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------
EOF

  chown "$USERNAME":"$USERNAME" "$bashrc_file" "$bash_profile_file" "$profile_file"
  chmod 644 "$bashrc_file" "$bash_profile_file" "$profile_file"

  log "Bash configuration files (.profile, .bash_profile, and .bashrc) have been recreated for $USERNAME."
}

###############################################################################
# Enable and configure ufw.
###############################################################################
configure_ufw() {
  log "Enabling ufw systemd service..."
  # Ensure ufw starts on boot, then start it now
  systemctl enable ufw 2>&1 | tee -a "$LOG_FILE"
  systemctl start ufw  2>&1 | tee -a "$LOG_FILE"

  log "Activating ufw (will allow pre-configured rules)..."
  # --force ensures it doesn’t prompt for confirmation
  ufw --force enable 2>&1 | tee -a "$LOG_FILE"

  log "Configuring ufw rules..."
  ufw allow ssh
  ufw allow http
  ufw allow 8080/tcp
  ufw allow 80/tcp
  ufw allow 80/udp
  ufw allow 443/tcp
  ufw allow 443/udp
  ufw allow 32400/tcp
  ufw allow 1900/udp
  ufw allow 5353/udp
  ufw allow 8324/tcp
  ufw allow 32410/udp
  ufw allow 32411/udp
  ufw allow 32412/udp
  ufw allow 32413/udp
  ufw allow 32414/udp
  ufw allow 32415/udp
  ufw allow 32469/tcp

  log "UFW configuration complete."
}

###############################################################################
# Function: force_release_ports
# Description:
#   1) Removes Apache2 and Caddy (if present), then performs system cleanup.
#   2) Installs net-tools if not present.
#   3) Checks which processes are listening on the listed ports (TCP/UDP).
#   4) Immediately terminates those processes by sending SIGKILL (-9).
###############################################################################
force_release_ports() {
  # Step 1: Remove Apache and Caddy, then autoremove
  echo "Removing apache2 and caddy..."
  apt purge -y apache2
  apt purge -y caddy
  apt autoremove -y

  # Step 2: Install net-tools if not present
  echo "Installing net-tools..."
  apt install -y net-tools

  # Step 3: Define ports to kill (TCP and UDP separately)
  local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
  local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")

  echo "Killing any processes listening on the specified ports..."

  # Kill TCP processes
  for p in "${tcp_ports[@]}"; do
    # lsof -t: print only the process IDs
    # -i TCP:$p: match TCP port
    # -sTCP:LISTEN: only processes in LISTEN state
    pids="$(lsof -t -i TCP:"$p" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "Killing processes on TCP port $p: $pids"
      kill -9 $pids
    fi
  done

  # Kill UDP processes
  for p in "${udp_ports[@]}"; do
    # -i UDP:$p: match UDP port
    pids="$(lsof -t -i UDP:"$p" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "Killing processes on UDP port $p: $pids"
      kill -9 $pids
    fi
  done

  echo "Ports have been forcibly released."
}

################################################################################
# Function: set_hostname
# Description:
#   Sets and persists the system hostname.
################################################################################
set_hostname() {
  local new_hostname="$1"
  if [ -z "$new_hostname" ]; then
    log "No hostname specified; skipping."
    return
  fi

  log "Setting system hostname to '${new_hostname}'..."
  hostnamectl set-hostname "$new_hostname" 2>&1 | tee -a "$LOG_FILE"
  log "Hostname set to ${new_hostname}."
}

################################################################################
# Function: configure_timezone
# Description:
#   Installs common timezone data (if not present), then sets the system timezone
#   and ensures that the hardware clock is synced to localtime or UTC.
################################################################################
configure_timezone() {
  local tz="${1:-UTC}"  # Default to UTC if not specified
  log "Configuring timezone to '${tz}'..."

  # Ensure tzdata is present (usually installed by default, but just in case)
  apt install -y tzdata

  # Timedatectl sets both system clock and hardware clock
  timedatectl set-timezone "$tz" 2>&1 | tee -a "$LOG_FILE"

  log "Timezone set to $tz."
}

################################################################################
# Function: basic_security_hardening
# Description:
#   Applies a minimal set of security best practices on Ubuntu-based systems:
#     1) Disables root SSH login
#     2) Installs fail2ban if not already installed
################################################################################
basic_security_hardening() {
  log "Applying basic Ubuntu security hardening..."

  # 1) Disable root login in ssh_config
  sed -i 's/^\s*#*\s*PermitRootLogin\s.*/PermitRootLogin no/' /etc/ssh/ssh_config
  systemctl restart ssh 2>&1 | tee -a "$LOG_FILE"

  # 2) Install fail2ban (from Ubuntu repositories)
  if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
    log "Installing fail2ban..."
    apt install -y fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl enable fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl start fail2ban 2>&1 | tee -a "$LOG_FILE"
  else
    log "fail2ban is already installed."
  fi

  log "Security hardening steps completed."
}

################################################################################
# Function: create_caddyfile
# Description:
#   Creates (or overwrites) /etc/caddy/Caddyfile with the specified contents:
#     - Global email setting
#     - Global logging
#     - www.dunamismax.com redirect
#     - Main Hugo site at dunamismax.com
#     - Nextcloud reverse proxy at cloud.dunamismax.com
################################################################################
create_caddyfile() {
  log "Creating /etc/caddy/Caddyfile..."

  install_caddy

  local caddyfile_path="/etc/caddy/Caddyfile"
  local caddyfile_dir
  caddyfile_dir=$(dirname "$caddyfile_path")

  # Ensure caddy directory exists
  if [ ! -d "$caddyfile_dir" ]; then
    mkdir -p "$caddyfile_dir"
    log "Created directory $caddyfile_dir"
  fi

  # Write out the Caddyfile
  cat << 'EOF' > "$caddyfile_path"
{
    # Use this email for Let's Encrypt notifications
    email dunamismax@tutamail.com

    # Global logging: captures all events (including errors during startup)
    log {
        output file /var/log/caddy/caddy.log
    }
}

# Redirect www to non-www
www.dunamismax.com {
    redir https://dunamismax.com{uri}
}

# Main website
dunamismax.com {
    # Serve the static files from your Hugo output folder
    root * /home/sawyer/GitHub/Hugo/dunamismax.com/public
    file_server

    # Deny hidden files (dotfiles like .git, .htaccess, etc.)
    @hiddenFiles {
        path_regexp hiddenFiles ^/\.
    }
    respond @hiddenFiles 404

    # Per-site logging: captures site-specific access and error logs
    log {
        output file /var/log/caddy/dunamismax_access.log
    }
}

# Nextcloud
cloud.dunamismax.com {
    reverse_proxy 127.0.0.1:8080
}
EOF

  chown root:root "$caddyfile_path"
  chmod 644 "$caddyfile_path"

  log "Caddyfile created at $caddyfile_path"

  systemctl enable caddy
  systemctl start caddy

  # Optionally reload or restart Caddy to apply changes
  if command -v systemctl &>/dev/null; then
    log "Reloading Caddy to apply new configuration..."
    systemctl reload caddy 2>&1 | tee -a "$LOG_FILE" || {
      log "Reload failed, attempting restart..."
      systemctl restart caddy 2>&1 | tee -a "$LOG_FILE"
    }
  fi
}

################################################################################
# Function: apt_and_settings
#  1) Add Flatpak (Flathub) remote for installing Flatpak apps.
################################################################################
apt_and_settings() {
  log "==== Starting apt_and_settings routine ===="

  ##############################################################################
  # 1) Add Flatpak (Flathub) remote for installing Flatpak apps
  ##############################################################################
  log "Installing flatpak and configuring Flathub remote..."
  apt install -y flatpak 2>&1 | tee -a "$LOG_FILE"

  # Add the Flathub remote if not already added
  if ! flatpak remote-list | grep -q 'flathub'; then
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    log "Flathub remote added for Flatpak."
  else
    log "Flathub remote already exists."
  fi

  log "==== apt_and_settings routine completed successfully. ===="
}

################################################################################
# Function: configure_ntp
# Description:
#   Installs and configures NTP service on Ubuntu-based systems using chrony.
#   1) Installs chrony if not already installed.
#   2) Backs up the existing /etc/chrony/chrony.conf (if present).
#   3) Writes a basic chrony.conf with recommended upstream NTP servers.
#   4) Enables and starts chrony.
################################################################################
configure_ntp() {
  log "Configuring NTP (chrony)..."

  # 1) Install chrony if it is not already installed
  if ! dpkg-query -W -f='${Status}' chrony 2>/dev/null | grep -q "install ok installed"; then
    log "Installing chrony..."
    apt install -y chrony 2>&1 | tee -a "$LOG_FILE"
  else
    log "chrony is already installed."
  fi

  # 2) Backup existing chrony config and overwrite
  local chrony_conf="/etc/chrony/chrony.conf"
  if [ -f "$chrony_conf" ]; then
    cp "$chrony_conf" "${chrony_conf}.bak.$(date +%Y%m%d%H%M%S)"
    log "Backed up existing $chrony_conf to ${chrony_conf}.bak.$(date +%Y%m%d%H%M%S)"
  fi

  # 3) Write a basic chrony.conf (using global NTP servers for demonstration)
  cat << 'EOF' > "$chrony_conf"
# /etc/chrony/chrony.conf - basic configuration

# Pool-based time servers:
pool 2.ubuntu.pool.ntp.org iburst
pool time.google.com iburst
pool pool.ntp.org iburst

# Allow only localhost by default
allow 127.0.0.1
allow ::1

# Record the rate at which the system clock gains/losses time.
driftfile /var/lib/chrony/chrony.drift

# Save NTS keys and cookies.
ntsdumpdir /var/lib/chrony

# Enable kernel synchronization of the hardware clock
rtcsync

# Enable hardware timestamping on all interfaces that support it
hwtimestamp *

# Increase logging for debugging, comment out in production
log tracking measurements statistics
EOF

  log "Wrote a new chrony.conf at $chrony_conf."

  # 4) Enable and start chrony
  systemctl enable chrony 2>&1 | tee -a "$LOG_FILE"
  systemctl restart chrony 2>&1 | tee -a "$LOG_FILE"

  log "NTP (chrony) configuration complete."
}

# Function to install build dependencies for compiling Python via pyenv
install_python_build_deps() {
    LOG_FILE="/var/log/python_build_deps_install.log" # Define the log file location

    log "Installing system build dependencies..." | tee -a "$LOG_FILE"

    # Update package lists
    if ! apt update -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to update package lists. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Install required packages
    if ! apt install -y \
        build-essential \
        git \
        curl \
        wget \
        ca-certificates \
        libssl-dev \
        libbz2-dev \
        libffi-dev \
        zlib1g-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncurses5-dev \
        libncursesw5-dev \
        xz-utils \
        liblzma-dev \
        tk-dev \
        llvm \
        jq \
        gnupg \
        libxml2-dev \
        libxmlsec1-dev \
        --no-install-recommends 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to install build dependencies. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Clean up unnecessary packages and caches
    if ! apt autoremove -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to autoremove unnecessary packages." | tee -a "$LOG_FILE"
    fi

    if ! apt clean -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to clean package cache." | tee -a "$LOG_FILE"
    fi

    log "System build dependencies installed." | tee -a "$LOG_FILE"
}

# Function to install build dependencies for C, C++, Rust, and Go
install_dev_build_deps() {
    LOG_FILE="/var/log/dev_build_deps_install.log" # Define the log file location

    log "Installing system build dependencies for C, C++, Rust, and Go..." | tee -a "$LOG_FILE"

    # Update package lists
    if ! apt update -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to update package lists. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Install required packages
    if ! apt install -y \
        build-essential \
        gcc \
        g++ \
        clang \
        cmake \
        git \
        curl \
        wget \
        ca-certificates \
        make \
        llvm \
        gdb \
        libssl-dev \
        libbz2-dev \
        libffi-dev \
        zlib1g-dev \
        pkg-config \
        jq \
        gnupg \
        libxml2-dev \
        libxmlsec1-dev \
        --no-install-recommends 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to install build dependencies for C and C++. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Install Rust toolchain
    if ! curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y >>"$LOG_FILE" 2>&1; then
        log "Failed to install Rust toolchain. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Add Rust binaries to PATH (for current session)
    export PATH="$HOME/.cargo/bin:$PATH"

    # Install Go (use apt for simplicity, but better alternatives exist)
    if ! apt install -y \
        golang-go 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to install Go programming environment. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Clean up unnecessary packages and caches
    if ! apt autoremove -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to autoremove unnecessary packages." | tee -a "$LOG_FILE"
    fi

    if ! apt clean -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to clean package cache." | tee -a "$LOG_FILE"
    fi

    log "System build dependencies for C, C++, Rust, and Go installed." | tee -a "$LOG_FILE"
}

################################################################################
# 0. Basic System Update & Core Packages
################################################################################
install_apt_dependencies() {
    echo "[INFO] Updating apt caches..."
    sudo apt-get update -y

    # Optional: If you want to also upgrade existing packages:
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
        jq

    # Optionally remove automatically installed packages no longer needed
    sudo apt-get autoremove -y
    sudo apt-get clean
}

################################################################################
# Function: install_caddy
################################################################################
install_caddy() {
  log "Installing and enabling Caddy..."

  apt update -y
  apt install -y ubuntu-keyring apt-transport-https curl

  # Add the official Caddy GPG key
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --batch --yes --dearmor \
         -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

  # Add the Caddy stable repository
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list

  apt update -y
  apt install -y caddy

  log "Caddy installed."
}

################################################################################
# disable_sleep_and_set_performance
# Description:
#   1) Masks (disables) system sleep targets so the system never suspends.
#   2) Installs cpufrequtils (if not present) and sets all CPU cores to
#      "performance" governor.
################################################################################
disable_sleep_and_set_performance() {
  # Ensure we run as root/sudo
  if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] This function must be run as root or with sudo privileges."
    exit 1
  fi

  echo "[INFO] Disabling system sleep, suspend, hibernate, and hybrid-sleep..."
  systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
  # Optionally stop them if currently active
  systemctl stop sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

  echo "[INFO] Installing cpufrequtils if not already installed..."
  if ! command -v cpufreq-set &>/dev/null; then
    apt-get update -y
    apt-get install -y cpufrequtils
  fi

  echo "[INFO] Checking available CPU governor(s)..."
  # It's useful to ensure "performance" is a valid governor before setting it.
  # This might vary on certain virtualized environments.
  if ! cpufreq-info | grep -q "performance"; then
    echo "[WARNING] 'performance' governor not found. Your system may not support it."
    echo "          Attempting to continue..."
  fi

  echo "[INFO] Setting CPU governor to 'performance' for all CPU cores..."
  for cpu_gov in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
    if [ -w "$cpu_gov" ]; then
      echo performance > "$cpu_gov"
    else
      echo "[WARNING] Unable to set performance governor for $(dirname "$cpu_gov")"
    fi
  done

  echo "[INFO] Done. Your system should no longer suspend and CPU frequency is set to performance."
  echo "[INFO] If you want to persist governor settings across reboots, edit /etc/default/cpufrequtils."
}

################################################################################
# Function: install_and_enable_plex
# Description:
#   This function installs Plex Media Server on Ubuntu using the official
#   .deb package if it is not already installed. If it is already installed,
#   the function skips the installation and proceeds. Then it enables and
#   starts the plexmediaserver service to ensure Plex runs on system boot.
#   Finally, it displays how to access the Plex Web UI.
#
# Usage:
#   1. Adjust the VERSION variable below as necessary.
#   2. Call install_and_enable_plex.
#   3. Access the Plex Web UI on http://127.0.0.1:32400/web from the same
#      machine running Plex.
################################################################################
install_and_enable_plex() {
  set -e  # Exit immediately if a command exits with a non-zero status

  echo "Checking if Plex Media Server is already installed..."
  if dpkg -s plexmediaserver >/dev/null 2>&1; then
    echo "Plex Media Server is already installed. Skipping installation."
    return
  fi

  echo "Updating apt package index..."
  sudo apt-get update -y

  echo "Installing prerequisites (curl) if not already installed..."
  if ! dpkg -s curl >/dev/null 2>&1; then
    sudo apt-get install -y curl
  fi

  # Change this to match the latest Plex version you want to install
  local VERSION="1.41.3.9314-a0bfb8370"
  local DEB_PACKAGE="plexmediaserver_${VERSION}_amd64.deb"
  local DEB_URL="https://downloads.plex.tv/plex-media-server-new/${VERSION}/debian/${DEB_PACKAGE}"

  echo "Downloading Plex Media Server package from Plex..."
  curl -LO "${DEB_URL}"

  echo "Installing Plex Media Server..."
  if ! sudo dpkg -i "${DEB_PACKAGE}"; then
    echo "Resolving missing dependencies..."
    sudo apt-get install -f -y
    sudo dpkg -i "${DEB_PACKAGE}"
  fi

  echo "Configuring any partially installed packages..."
  sudo dpkg --configure -a

  echo "Enabling and starting plexmediaserver service..."
  sudo systemctl enable plexmediaserver
  sudo systemctl start plexmediaserver

  echo "Plex Media Server installation complete!"
  echo "To configure Plex, open a browser on the same machine and go to:"
  echo "  http://127.0.0.1:32400/web"
}

# ------------------------------------------------------------------------------
# install_x11_and_ly
#   Installs Zig (from official upstream tarball) on Ubuntu, then proceeds to
#   install X11/GUI dependencies, Ly, and Regolith. This script does NOT install
#   i3 or i3-related tools (e.g., i3-gaps, i3lock-color, etc.).
#
#   After successful installation, you can choose to log in via Ly, then select
#   Regolith as your session if desired.
# ------------------------------------------------------------------------------
install_x11_and_ly() {
  set -euo pipefail
  echo "[INFO] Starting installation process for X11, Ly, and Regolith..."

  # 1) Ensure standard prerequisites are installed
  echo "[INFO] Installing base prerequisites..."
  sudo apt-get update -y
  sudo apt-get install -y wget apt-transport-https software-properties-common \
                          build-essential git curl file gpg

  # 2) (Optional) If you need PowerShell on Ubuntu
  echo "[INFO] Installing PowerShell (if supported)..."
  wget -q https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb
  sudo dpkg -i packages-microsoft-prod.deb || true
  rm -f packages-microsoft-prod.deb
  sudo apt-get update -y
  sudo apt-get install -y powershell || true

  # 3) Download and install Zig from the official source tarball
  echo "[INFO] Downloading Zig from official upstream..."
  ZIG_URL="https://ziglang.org/download/0.12.0/zig-linux-x86_64-0.12.0.tar.xz"
  ZIG_TARBALL="zig-linux-x86_64-0.12.0.tar.xz"

  wget -O "$ZIG_TARBALL" "$ZIG_URL"

  echo "[INFO] Extracting Zig tarball..."
  tar xf "$ZIG_TARBALL"

  # After extracting, you will get a directory named "zig-linux-x86_64-0.12.0"
  ZIG_EXTRACTED="zig-linux-x86_64-0.12.0"

  echo "[INFO] Installing Zig into /usr/local/zig..."
  sudo rm -rf /usr/local/zig
  sudo cp -r "$ZIG_EXTRACTED" /usr/local/zig

  echo "[INFO] Creating symlink /usr/local/bin/zig..."
  sudo rm -f /usr/local/bin/zig
  sudo ln -sf /usr/local/zig/zig /usr/local/bin/zig
  sudo chmod +x /usr/local/bin/zig

  # Optionally remove the downloaded tarball and extracted folder
  rm -f "$ZIG_TARBALL"
  rm -rf "$ZIG_EXTRACTED"

  # 4) Install X11 dependencies
  echo "[INFO] Installing X11 dependencies..."
  sudo apt-get update -y
  sudo apt-get install -y \
    xserver-xorg \
    xinit \
    x11-xserver-utils \
    libpam0g-dev \
    libxcb-xkb-dev

  # 5) Install Regolith
  echo "[INFO] Installing Regolith Desktop..."
  # Register the Regolith public key
  wget -qO - https://regolith-desktop.org/regolith.key \
    | gpg --dearmor \
    | sudo tee /usr/share/keyrings/regolith-archive-keyring.gpg > /dev/null

  # Add the Regolith repository to apt
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/regolith-archive-keyring.gpg] \
https://regolith-desktop.org/release-3_2-ubuntu-noble-amd64 noble main" \
  | sudo tee /etc/apt/sources.list.d/regolith.list

  # Update apt and install Regolith
  sudo apt update
  sudo apt install -y regolith-desktop regolith-session-flashback regolith-look-lascaille

  # 6) Clone and build Ly if not already present
  echo "[INFO] Cloning Ly repository..."
  if [ -d "ly" ]; then
    echo "[INFO] 'ly' directory already exists; skipping clone."
    cd ly || exit
  else
    git clone https://github.com/fairyglade/ly.git
    cd ly
  fi

  echo "[INFO] Compiling Ly using Zig..."
  zig build

  # 7) Install Ly and systemd service
  echo "[INFO] Installing Ly with systemd support..."
  sudo zig build installsystemd

  # 8) Enable Ly service
  echo "[INFO] Enabling Ly systemd service..."
  sudo systemctl enable ly.service

  echo "[INFO] Done! Reboot or switch to TTY2 to use Ly."
  echo "[INFO] Regolith Desktop has been installed. Once Ly is running,"
  echo "[INFO] you can select a Regolith session from the Ly interface."
}

################################################################################
# Function: finalize_configuration
################################################################################
finalize_configuration() {
  log "Finalizing system configuration..."

  # Update and upgrade packages
  if ! apt update -y 2>&1 | tee -a "$LOG_FILE"; then
    log "Error: Failed to update package lists."
    return 1
  fi

  if ! apt upgrade -y 2>&1 | tee -a "$LOG_FILE"; then
    log "Error: Failed to upgrade packages."
    return 1
  fi

  # Remove unused dependencies
  log "Performing system cleanup..."
  if ! apt autoremove -y 2>&1 | tee -a "$LOG_FILE"; then
    log "Error: Failed to remove unused dependencies."
  fi

  # Clean up local package cache
  if ! apt clean 2>&1 | tee -a "$LOG_FILE"; then
    log "Error: Failed to clean package cache."
  fi

  log "System cleanup completed."
  log "Final configuration steps completed successfully."
}

################################################################################
# MAIN
################################################################################
main() {
  log "--------------------------------------"
  log "Starting Ubuntu Automated System Configuration Script"

  # --------------------------------------------------------
  # 1) Basic System Preparation
  # --------------------------------------------------------
  force_release_ports
  enable_sudo
  configure_sudo_access
  enable_non_free_firmware_only
  apt_and_settings   # Run apt updates/upgrades, custom APT config, etc.
  configure_timezone "America/New_York"
  set_hostname "ubuntu"
  disable_sleep_and_set_performance

  # --------------------------------------------------------
  # 2) User Creation and Environment
  # --------------------------------------------------------
  set_default_shell_and_env

  # --------------------------------------------------------
  # 3) Install Caddy and create caddyfile
  # --------------------------------------------------------
  create_caddyfile

  # --------------------------------------------------------
  # 4) Software Installation
  # --------------------------------------------------------
  bootstrap_and_install_pkgs  # Installs essential system packages

  # --------------------------------------------------------
  # 5) Security and Hardening
  # --------------------------------------------------------
  overwrite_ssh_config
  configure_ufw
  configure_ntp

  basic_security_hardening

  # --------------------------------------------------------
  # 6) Dev Setup
  # --------------------------------------------------------
  install_python_build_deps
  install_dev_build_deps
  install_apt_dependencies

  # --------------------------------------------------------
  # 7) Finalization
  # --------------------------------------------------------
  install_and_enable_plex
  install_x11_and_ly
  finalize_configuration

  log "Configuration script finished successfully."
  log "Enjoy Ubuntu!"
  log "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi