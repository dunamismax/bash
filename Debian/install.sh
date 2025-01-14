#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Debian/Ubuntu Automated System Configuration Script
# ------------------------------------------------------------------------------
# Description:
#   This script automates the initial configuration of a fresh Debian or Ubuntu
#   system. Its primary tasks include:
#
#     1) Updating the package repository cache, performing system upgrades,
#        and installing essential packages (like build tools, curl, git, etc.).
#
#     2) Safely backing up and replacing select system configuration files,
#        such as '/etc/ssh/sshd_config', to enforce recommended security settings
#        and other custom configurations.
#
#     3) Creating or configuring a user account (by default "sawyer") with:
#         • Sudo privileges for administrative tasks.
#         • Bash set as the default shell.
#
# Usage & Requirements:
#   • Must be executed as root or via 'sudo'—otherwise, it cannot modify
#     system-level packages or configuration files.
#   • Compatible with both Debian and Ubuntu releases. May function on derivatives as well,
#     but YMMV (your mileage may vary).
#   • Before running, ensure you are comfortable with overwriting certain system files.
#     All replaced files will be backed up with a timestamp in the same directory.
#
# Logging:
#   • The script logs its operations and any error messages to '/var/log/debian_setup.log'
#     to help with troubleshooting or future review.
#
# Error Handling:
#   • Uses 'set -euo pipefail' to abort on errors, unbound variables, or failed pipes.
#   • Traps on 'ERR' to catch unexpected failures and exit gracefully.
#
# Disclaimer:
#   • While this script aims to streamline initial setup, always review the source
#     and test in a safe environment before using it in production.
#   • The provided configurations are opinionated defaults; adjust them to match
#     your security/compliance needs.
#
# Author & License:
#   • Author: dunamismax.
#   • License: MIT.
#
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Trap any error and output a helpful message
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/debian_setup.log"
USERNAME="sawyer"

# Essential Debian/Ubuntu packages for a baseline system
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
# Function: install and enable sudo
################################################################################
enable_sudo() {
  log "Enabling sudo."
  apt install sudo -y
  usermod -aG sudo sawyer
  log "User 'sawyer' has been added to the sudo group. Log out and back in for the changes to take effect."
}

################################################################################
# Function: bootstrap_and_install_pkgs
# apt update/upgrade and install our base PACKAGES
################################################################################
bootstrap_and_install_pkgs() {
  log "Updating apt package list and upgrading existing packages..."
  apt update 2>&1 | tee -a "$LOG_FILE"
  apt upgrade 2>&1 | tee -a "$LOG_FILE"

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
    apt install "${packages_to_install[@]}" 2>&1 | tee -a "$LOG_FILE"
  else
    log "All listed packages are already installed. No action needed."
  fi

  apt autoremove 2>&1 | tee -a "$LOG_FILE"
  apt clean 2>&1 | tee -a "$LOG_FILE"

  log "Package installation process completed."
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
# Basic Debian SSHD Configuration

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
Subsystem       sftp    /usr/libexec/openssh/sftp-server
EOF

  chown root:root "$sshd_config"
  chmod 644 "$sshd_config"
  log "Completed overwriting /etc/ssh/sshd_config. Restarting sshd..."
  systemctl restart sshd 2>&1 | tee -a "$LOG_FILE"
}

################################################################################
# Function: set_default_shell_and_env (Revised)
# Description:
#   Deletes (overwrites) and recreates ~/.bash_profile and ~/.bashrc for $USERNAME.
################################################################################
set_default_shell_and_env() {
  log "Recreating .bashrc and .bash_profile for $USERNAME..."

  # Dynamically determine the user's home directory
  local user_home
  user_home=$(eval echo "~$USERNAME")

  # File paths
  local bashrc_file="$user_home/.bashrc"
  local bash_profile_file="$user_home/.bash_profile"

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

  # Overwrite the .bashrc file
  log "Creating $bashrc_file with default content..."
  cat << 'EOF' > "$bashrc_file"
# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples


# >>> pyenv initialization >>>
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "$(pyenv init -)"
fi
# <<< pyenv initialization <<<

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# don't put duplicate lines or lines starting with space in the history.
# See bash(1) for more options
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=10000
HISTFILESIZE=20000

# Add timestamps to each history line for auditing
HISTTIMEFORMAT="%F %T "

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# make less more friendly for non-text input files, see lesspipe(1)
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in (used in the prompt below)
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# set a fancy prompt (non-color, unless we know we "want" color)
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

# uncomment for a colored prompt, if the terminal has the capability; turned
# off by default to not distract the user: the focus in a terminal window
# should be on the output of commands, not on the prompt
#force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        # We have color support; assume it's compliant with Ecma-48
        # (ISO/IEC-6429). (Lack of such support is extremely rare, and such
        # a case would tend to support setf rather than setaf.)
        color_prompt=yes
    else
        color_prompt=
    fi
fi

if [ "$color_prompt" = yes ]; then
    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm set the title to user@host:dir
case "$TERM" in
xterm*|rxvt*)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

# enable color support of ls and also add handy aliases
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    #alias dir='dir --color=auto'
    #alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# some more ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Add an "alert" alias for long running commands.  Use like so:
#   sleep 10; alert
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" "$(history|tail -n1|sed -e '\''s/^\s*[0-9]\+\s*//;s/[;&|]\s*alert$//'\'')"'

# If you want separate user-defined aliases, you can place them in ~/.bash_aliases
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# enable programmable completion features
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi

# -------------------
# Custom user additions:
# -------------------

alias r="ranger"
alias venv="setup_venv"
alias v="enable_venv"

export PATH="$PATH:$HOME/.local/bin"

# Function to re-enable a virtual environment
enable_venv() {
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

# Function to set up Python virtual environment
setup_venv() {
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
EOF

  chown "$USERNAME":"$USERNAME" "$bashrc_file" "$bash_profile_file"
  chmod 644 "$bashrc_file" "$bash_profile_file"

  log "Bash configuration files have been recreated for $USERNAME."
}

################################################################################
# Function: configure_ufw
# Description:
#   1) Enables and starts ufw as a systemd service.
#   2) Accepts any number of arguments in the style of:
#        --add-service=ssh
#        --add-port=8080/tcp
#      Then parses these to run the equivalent “ufw allow” commands.
#   3) Reloads ufw after adding all specified rules.
#
# Example usage:
#   configure_ufw \
#       "--add-service=ssh" \
#       "--add-port=8080/tcp"
################################################################################
configure_ufw() {
  log "Enabling ufw systemd service..."
  # Ensure ufw starts on boot, then start it now
  systemctl enable ufw 2>&1 | tee -a "$LOG_FILE"
  systemctl start ufw  2>&1 | tee -a "$LOG_FILE"

  log "Activating ufw (will allow pre-configured rules)..."
  # --force ensures it doesn’t prompt for confirmation
  ufw --force enable 2>&1 | tee -a "$LOG_FILE"

  if [ $# -eq 0 ]; then
    log "No firewall rules provided. ufw is enabled, but no new rules were added."
  else
    for rule in "$@"; do
      # Check if the user provided something like --add-service=ssh
      if [[ "$rule" == --add-service=* ]]; then
        local service="${rule#*=}"
        log "Allowing service: $service"
        ufw allow "$service" 2>&1 | tee -a "$LOG_FILE"

      # Check if the user provided something like --add-port=8080/tcp
      elif [[ "$rule" == --add-port=* ]]; then
        local port_proto="${rule#*=}"
        log "Allowing port/protocol: $port_proto"
        ufw allow "$port_proto" 2>&1 | tee -a "$LOG_FILE"

      else
        log "[WARNING] Unrecognized rule format: '$rule'"
      fi
    done

    log "Reloading ufw to apply the new rules..."
    ufw reload 2>&1 | tee -a "$LOG_FILE"
  fi
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
  apt install tzdata

  # Timedatectl sets both system clock and hardware clock
  timedatectl set-timezone "$tz" 2>&1 | tee -a "$LOG_FILE"

  log "Timezone set to $tz."
}

################################################################################
# Function: basic_security_hardening
# Description:
#   Applies a minimal set of security best practices on Debian-based systems:
#     1) Disables root SSH login
#     2) Installs fail2ban if not already installed
#     3) Installs or updates AIDE (file integrity monitoring)
################################################################################
basic_security_hardening() {
  log "Applying basic Debian security hardening..."

  # 1) Disable root login in sshd_config
  sed -i 's/^\s*#*\s*PermitRootLogin\s.*/PermitRootLogin no/' /etc/ssh/sshd_config
  systemctl restart sshd 2>&1 | tee -a "$LOG_FILE"

  # 2) Install fail2ban (from Debian repositories)
  if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
    log "Installing fail2ban..."
    apt install -y fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl enable fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl start fail2ban 2>&1 | tee -a "$LOG_FILE"
  else
    log "fail2ban is already installed."
  fi

  # 3) Install or update AIDE for file integrity monitoring
  if ! dpkg-query -W -f='${Status}' aide 2>/dev/null | grep -q "install ok installed"; then
    log "Installing AIDE..."
    apt install -y aide 2>&1 | tee -a "$LOG_FILE"
    aide --init 2>&1 | tee -a "$LOG_FILE"
    mv /var/lib/aide/aide.db.new.gz /var/lib/aide/aide.db.gz
    log "AIDE initialization complete."
  else
    log "AIDE is already installed."
  fi

  log "Security hardening steps completed."
}

################################################################################
# Function: configure_automatic_updates
# Description:
#   Installs and configures the unattended-upgrades package on Debian to perform
#   automatic updates. Adjust the config as needed (e.g., security-only).
################################################################################
configure_automatic_updates() {
  log "Configuring unattended-upgrades for automatic updates..."

  # Update package lists and install unattended-upgrades
  apt install unattended-upgrades 2>&1 | tee -a "$LOG_FILE"

  # Optionally configure /etc/apt/apt.conf.d/50unattended-upgrades
  # Add or adjust settings for automatic reboots, email notifications, etc.
  # For example:
  # sed -i 's|//Unattended-Upgrade::Mail ""|Unattended-Upgrade::Mail "root"|g' /etc/apt/apt.conf.d/50unattended-upgrades
  # sed -i 's|//Unattended-Upgrade::Automatic-Reboot "false"|Unattended-Upgrade::Automatic-Reboot "true"|g' /etc/apt/apt.conf.d/50unattended-upgrades

  # Enable automatic updates by configuring a basic auto-upgrades file
  cat <<EOF >/etc/apt/apt.conf.d/20auto-upgrades
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

  # Enable and start the relevant systemd timers for unattended-upgrades
  systemctl enable unattended-upgrades.service && systemctl start unattended-upgrades.service

  log "Automatic updates have been enabled via unattended-upgrades."
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
  apt install flatpak 2>&1 | tee -a "$LOG_FILE"

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
#   Installs and configures NTP service on Debian-based systems using chrony.
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
pool 2.debian.pool.ntp.org iburst
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

################################################################################
# Function: enable_gui
# Description:
#   Installs the GNOME desktop environment (with Xorg/Wayland/GDM3) plus extras
#   and tweaks, and also installs AwesomeWM on a Debian/Ubuntu system. Afterwards,
#   it sets the system to boot into a graphical session by default.
#
# Usage:
#   enable_gui
################################################################################
enable_gui() {
  echo "[INFO] Enabling GUI environment..."

  echo "[INFO] Installing GNOME, GDM, AwesomeWM, and related packages..."
  apt -y install \
    gnome \
    gnome-shell \
    gnome-tweaks \
    xorg \
    wayland-protocols \
    gdm3 \
    awesome

  echo "[INFO] Setting default target to graphical..."
  systemctl set-default graphical.target

  echo "[INFO] Enabling and starting GDM3..."
  systemctl enable gdm3
  systemctl start gdm3

  echo "[INFO] GNOME desktop environment and AwesomeWM installation complete."
  echo "[INFO] The system will now boot to the graphical login screen by default."
}

# Function to install build dependencies for compiling Python via pyenv
install_python_build_deps() {
    LOG_FILE="/var/log/python_build_deps_install.log" # Define the log file location

    log "Installing system build dependencies..." | tee -a "$LOG_FILE"

    # Update package lists
    if ! apt-get update -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to update package lists. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Install required packages
    if ! apt-get install -y \
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
    if ! apt-get autoremove -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to autoremove unnecessary packages." | tee -a "$LOG_FILE"
    fi

    if ! apt-get clean 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to clean package cache." | tee -a "$LOG_FILE"
    fi

    log "System build dependencies installed." | tee -a "$LOG_FILE"
}

# Function to install build dependencies for C, C++, Rust, and Go
install_dev_build_deps() {
    LOG_FILE="/var/log/dev_build_deps_install.log" # Define the log file location

    log "Installing system build dependencies for C, C++, Rust, and Go..." | tee -a "$LOG_FILE"

    # Update package lists
    if ! apt-get update -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to update package lists. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Install required packages
    if ! apt-get install -y \
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
    if ! apt-get install -y \
        golang-go 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to install Go programming environment. Exiting." | tee -a "$LOG_FILE"
        return 1
    fi

    # Clean up unnecessary packages and caches
    if ! apt-get autoremove -y 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to autoremove unnecessary packages." | tee -a "$LOG_FILE"
    fi

    if ! apt-get clean 2>&1 | tee -a "$LOG_FILE"; then
        log "Failed to clean package cache." | tee -a "$LOG_FILE"
    fi

    log "System build dependencies for C, C++, Rust, and Go installed." | tee -a "$LOG_FILE"
}

################################################################################
# Function: install_caddy
################################################################################
install_caddy() {
  log "Installing and enabling Caddy..."
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --batch --yes --dearmor \
       -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update -y
apt install -y caddy
  log "Caddy installed."
}

################################################################################
# Function: finalize_configuration
################################################################################
finalize_configuration() {
  log "Finalizing system configuration..."

  apt update 2>&1 | tee -a "$LOG_FILE"
  apt upgrade 2>&1 | tee -a "$LOG_FILE"
  apt autoremove 2>&1 | tee -a "$LOG_FILE"
  apt clean all 2>&1 | tee -a "$LOG_FILE"

  log "Performing system cleanup..."
  # Remove orphaned dependencies and old kernels if any
  apt autoremove
  apt clean
  log "System cleanup completed."

  log "Final configuration steps completed."
}

################################################################################
# MAIN
################################################################################
main() {
  log "--------------------------------------"
  log "Starting Debian Automated System Configuration Script"

  # --------------------------------------------------------
  # 1) Basic System Preparation
  # --------------------------------------------------------
  enable_sudo
  apt_and_settings   # Run apt updates/upgrades, custom APT config, etc.
  configure_timezone "America/New_York"
  set_hostname "debian"

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
  enable_gui                  # Installs GNOME desktop environment & AwesomeWM

  # --------------------------------------------------------
  # 5) Security and Hardening
  # --------------------------------------------------------
  overwrite_sshd_config
  configure_ufw \
    "--add-service=ssh" \
    "--add-service=http" \
    "--add-port=8080/tcp" \
    "--add-port=80/tcp" \
    "--add-port=80/udp" \
    "--add-port=443/tcp" \
    "--add-port=443/udp"  \
    "--add-port=32400/tcp" \
    "--add-port=1900/udp" \
    "--add-port=5353/udp" \
    "--add-port=8324/tcp" \
    "--add-port=32410-32415/udp" \
    "--add-port=32469/tcp"
  configure_ntp
  configure_automatic_updates
  basic_security_hardening

  # --------------------------------------------------------
  # 6) Dev Setup
  # --------------------------------------------------------
  install_python_build_deps
  install_dev_build_deps

  # --------------------------------------------------------
  # 7) Finalization
  # --------------------------------------------------------
  finalize_configuration

  log "Configuration script finished successfully."
  log "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi