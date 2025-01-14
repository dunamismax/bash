#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Debian/Ubuntu Automated System Configuration Script + Python/pyenv/pipx Setup
# ------------------------------------------------------------------------------
# Description:
#   This script automates the configuration of a fresh Debian or Ubuntu system by:
#     1) Updating apt (and performing upgrades), then installing essential packages.
#     2) Backing up and replacing select system config files (e.g. 'etc/ssh/sshd_config').
#     3) Granting sudo privileges to the user "sawyer" and setting Bash as that user’s
#        default shell.
#     4) Installing pyenv + pipx, along with the latest stable Python 3.x and a curated set
#        of Python CLI tools.
#
# Notes:
#   • All logs are appended to /var/log/debian_setup.log for consistency.
#   • The script uses "set -euo pipefail" and a trap on ERR to handle unexpected errors.
#   • Must be run as root (or via sudo) on a fresh Debian/Ubuntu system.
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Trap any error and output a helpful message
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/debian_setup.log"
USERNAME="sawyer"

# Optionally used later if you wish to detect the primary network interface
PRIMARY_IFACE=""

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
  util-linux-user

  # Virtualization (optional; remove if not needed)
  qemu-kvm
  libvirt-daemon-system
  libvirt-clients
  virtinst
  bridge-utils

  # Optional tools
  chrony          # For time synchronization
  firewalld       # Firewall management
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
  exit 1
}

################################################################################
# Function: identify_primary_iface
# Identify the primary network interface on Debian
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
# Function: configure_sudoers
# Configure user in the sudo group (typical on Debian)
################################################################################
configure_sudoers() {
  log "Configuring sudoers for $USERNAME..."

  # Add user to the 'sudo' group
  usermod -aG sudo "$USERNAME"

  # Ensure /etc/sudoers has a rule for %sudo
  local sudoers_file="/etc/sudoers"
  local sudo_rule="%sudo ALL=(ALL) ALL"

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
# Function: enable_extra_debian_repos
# Description:
#   Enables common additional repositories on Debian-based systems
################################################################################
enable_extra_debian_repos() {
  log "Enabling extra Debian repositories (contrib, non-free)..."

  local sources_list="/etc/apt/sources.list"
  local debian_codename
  debian_codename="$(lsb_release -cs 2>/dev/null || echo "stable")"

  # Backup original sources.list
  cp "$sources_list" "${sources_list}.bak.$(date +%Y%m%d%H%M%S)"
  log "Backed up $sources_list to ${sources_list}.bak.$(date +%Y%m%d%H%M%S)"

  # Enable contrib and non-free if not already enabled
  # (Runs a simple check and appends if missing)
  if ! grep -Eq "(^|\s)(contrib|non-free)" "$sources_list"; then
    log "Adding 'contrib' and 'non-free' components to $sources_list."
    sed -i "s/^\(deb .*${debian_codename}\s\+main\)/\1 contrib non-free/" "$sources_list"
    sed -i "s/^\(deb-src .*${debian_codename}\s\+main\)/\1 contrib non-free/" "$sources_list"
  else
    log "Contrib and non-free repos appear to be already enabled."
  fi

  # Update package list
  apt update 2>&1 | tee -a "$LOG_FILE"

  log "Extra Debian repositories are now enabled."
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
# Function: manage_service
# Description:
#   Enables, disables, or restarts a systemd service. Optionally checks for
#   valid actions before proceeding.
#
# Usage:
#   manage_service <service_name> <enable|disable|start|stop|restart|status>
#
# Examples:
#   manage_service "firewalld" "enable"
#   manage_service "firewalld" "start"
#
# Note:
#   - Logs all output to $LOG_FILE (assumes 'log' and 'LOG_FILE' exist).
#   - Returns non-zero if systemctl is unavailable or usage is incorrect.
################################################################################
manage_service() {
  local service_name="$1"
  local action="$2"

  # Check that systemctl is available
  if ! command -v systemctl &>/dev/null; then
    log "[ERROR] systemctl not found on this system. Exiting..."
    return 1
  fi

  # Validate parameters
  if [[ -z "$service_name" || -z "$action" ]]; then
    log "[ERROR] Usage: manage_service <service_name> <enable|disable|start|stop|restart|status>"
    return 1
  fi

  # Validate action against a known set of possible actions
  local valid_actions=("enable" "disable" "start" "stop" "restart" "status")
  if [[ ! " ${valid_actions[*]} " =~ " $action " ]]; then
    log "[ERROR] Invalid action '$action'. Valid actions: ${valid_actions[*]}"
    return 1
  fi

  log "Managing service '${service_name}' with action '${action}'..."
  if ! systemctl "${action}" "${service_name}" 2>&1 | tee -a "$LOG_FILE"; then
    log "[ERROR] Failed to '${action}' service '${service_name}'. Check logs above for details."
    return 1
  fi

  # Optionally, you can add a success message
  log "Successfully executed '${action}' on service '${service_name}'."
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
    apt update -y 2>&1 | tee -a "$LOG_FILE"
    apt install -y fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl enable fail2ban 2>&1 | tee -a "$LOG_FILE"
    systemctl start fail2ban 2>&1 | tee -a "$LOG_FILE"
  else
    log "fail2ban is already installed."
  fi

  # 3) Install or update AIDE for file integrity monitoring
  if ! dpkg-query -W -f='${Status}' aide 2>/dev/null | grep -q "install ok installed"; then
    log "Installing AIDE..."
    apt update -y 2>&1 | tee -a "$LOG_FILE"
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
  apt update 2>&1 | tee -a "$LOG_FILE"
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
# Function to install Caddy: install_caddy
################################################################################
install_caddy() {
    log "Installing Caddy"
    apt install caddy
    systemctl enable caddy
    systemctl start caddy
    log "Caddy Installed!"
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
# Function: install_container_engine
# Description:
#   Installs Docker Engine (Docker CE) and related tools on Debian-based systems.
#   Removes older Docker packages if present, adds the Docker APT repo, installs
#   Docker, then enables and starts the Docker service. Optionally adds $USERNAME
#   to the 'docker' group to allow non-root access to Docker commands.
################################################################################
install_container_engine() {
  log "Starting container engine installation for Debian..."

  # Remove any older Docker packages that may conflict
  log "Removing older Docker packages if present..."
  apt purge docker docker-engine docker.io containerd runc 2>&1 | tee -a "$LOG_FILE"

  log "Updating APT and installing prerequisite packages for Docker repo..."
  apt update 2>&1 | tee -a "$LOG_FILE"
  apt install ca-certificates curl gnupg lsb-release 2>&1 | tee -a "$LOG_FILE"

  # Add Docker’s official GPG key
  log "Adding Docker’s official GPG key..."
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg \
    | gpg --dearmor \
    | tee /etc/apt/keyrings/docker.gpg >/dev/null 2>&1

  # Set up the stable Docker repository
  log "Setting up the Docker APT repository..."
  local arch
  arch="$(dpkg --print-architecture)"
  local codename
  codename="$(lsb_release -cs)"

  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian \
${codename} stable" \
    | tee /etc/apt/sources.list.d/docker.list >/dev/null

  # Update package index and install Docker Engine
  log "Installing Docker Engine and related packages..."
  apt update 2>&1 | tee -a "$LOG_FILE"
  apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1 | tee -a "$LOG_FILE"

  # Enable and start Docker
  log "Enabling and starting Docker service..."
  systemctl enable docker 2>&1 | tee -a "$LOG_FILE"
  systemctl start docker 2>&1 | tee -a "$LOG_FILE"

  # Optionally add your user to the 'docker' group for non-root usage
  if id "$USERNAME" &>/dev/null; then
    log "Adding '$USERNAME' to the 'docker' group..."
    usermod -aG docker "$USERNAME"
  else
    log "User '$USERNAME' does not exist or is not passed in. Skipping 'docker' group addition."
  fi

  log "Docker installation completed successfully."
}

################################################################################
# Function: system_cleanup
# Description:
#   Performs RPM-based package cleanup to remove unneeded packages,
#   orphaned dependencies, and clean the cache.
################################################################################
system_cleanup() {
  log "Performing system cleanup..."

  # Remove orphaned dependencies and old kernels if any
  apt autoremove
  apt clean

  log "System cleanup completed."
}

################################################################################
# Function: apt_and_settings
# Description:
#   1) Configure APT to enable some preferable defaults (e.g., assume "yes",
#      keep downloaded packages, etc.).
#   2) Clean the APT cache.
#   3) Update the system.
#   4) Optionally enable extra repositories (similar to RPM Fusion on RHEL/Fedora),
#      here we demonstrate adding the Debian Multimedia Repository (if desired).  
#   5) Perform a “dist-upgrade” (somewhat analogous to a group update of "core").  
#   6) Add Flatpak (Flathub) remote for installing Flatpak apps.
#
# Notes:
#   - You must run this function as root (or with sudo).
################################################################################
apt_and_settings() {
  log "==== Starting apt_and_settings routine ===="

  ##############################################################################
  # 1) APT Configuration
  ##############################################################################
  log "Configuring APT to enable preferable defaults..."

  # Create a new APT config file under /etc/apt/apt.conf.d/ if it doesn't exist
  local apt_config_file="/etc/apt/apt.conf.d/99custom"
  if [ ! -f "$apt_config_file" ]; then
    touch "$apt_config_file"
    log "Created $apt_config_file for custom APT settings."
  fi

  # Backup any old version of our custom file
  cp "$apt_config_file" "${apt_config_file}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true

  # Overwrite with desired defaults
  cat <<EOF > "$apt_config_file"
// Custom APT configuration
APT::Get::Assume-Yes "true";
APT::Get::force-yes "false";  // Only set to 'true' if you absolutely trust repos
APT::Keep-Downloaded-Packages "true";
// Uncomment or add additional lines for parallel downloads (apt 2.0+), e.g.:
// Acquire::Queue-Mode "access";
// Acquire::Retries "3";
EOF

  log "APT configuration updated at $apt_config_file."

  ##############################################################################
  # 2) Clean the APT cache
  ##############################################################################
  log "Cleaning the APT cache..."
  apt clean

  ##############################################################################
  # 3) System Update
  ##############################################################################
  log "Updating package lists and upgrading installed packages..."
  apt update 2>&1 | tee -a "$LOG_FILE"
  apt upgrade 2>&1 | tee -a "$LOG_FILE"

  ##############################################################################
  # 4) Perform a “dist-upgrade” (somewhat analogous to a group update of "core")
  ##############################################################################
  log "Performing a dist-upgrade to handle any dependency changes..."
  apt dist-upgrade 2>&1 | tee -a "$LOG_FILE"

  ##############################################################################
  # 5) Add Flatpak (Flathub) remote for installing Flatpak apps
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
# Function: create_user
# Description:
#   Creates or updates a user account passed as the first argument. If the user
#   doesn't exist, it creates one with a home directory and Bash shell. Prompts
#   the admin to enter and confirm a new password for the user. SSH key
#   configuration is intentionally omitted to allow password-based SSH.
#
# Usage:
#   create_user "username"
#
# Example:
#   create_user "sawyer"
################################################################################
create_user() {
  local username="$1"
  if [[ -z "$username" ]]; then
    echo "[ERROR] Usage: create_user <username>"
    return 1
  fi

  # 1) Check if user exists, otherwise create
  if ! id "$username" &>/dev/null; then
    useradd -m -s /bin/bash "$username"
    echo "[INFO] Created user '$username'."
  else
    echo "[INFO] User '$username' already exists. Proceeding to set new password..."
  fi

  # 2) Prompt for password (hidden input)
  local user_password
  read -s -p "Enter a new password for '$username': " user_password
  echo
  read -s -p "Confirm the new password for '$username': " confirm_password
  echo

  # 3) Validate that both entries match
  if [[ "$user_password" != "$confirm_password" ]]; then
    echo "[ERROR] Passwords did not match. Aborting."
    return 1
  fi

  # 4) Set the password for the user non-interactively
  echo -e "${user_password}\n${user_password}" | passwd "$username" &>/dev/null
  if [[ $? -eq 0 ]]; then
    echo "[INFO] Password successfully set for user '$username'."
  else
    echo "[ERROR] Failed to set password for user '$username'."
    return 1
  fi

  return 0
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
    apt update -y 2>&1 | tee -a "$LOG_FILE"
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
# Function: finalize_configuration
# apt upgrade
################################################################################
finalize_configuration() {
  log "Finalizing system configuration..."

  apt update 2>&1 | tee -a "$LOG_FILE"
  apt upgrade 2>&1 | tee -a "$LOG_FILE"
  apt autoremove 2>&1 | tee -a "$LOG_FILE"
  apt clean all 2>&1 | tee -a "$LOG_FILE"

  log "Final configuration steps completed."
}

setup_pyenv_and_python_tools_for_user() {
  local NORMAL_USER="$1"
  if [[ -z "$NORMAL_USER" ]]; then
    log "[ERROR] No user provided to setup_pyenv_and_python_tools_for_user."
    return 1
  fi

  local USER_HOME
  USER_HOME="$(eval echo "~$NORMAL_USER")"
  local PYENV_ROOT="$USER_HOME/.pyenv"
  local BASHRC_FILE="$USER_HOME/.bashrc"

  log "----- Setting up pyenv + pipx for user '$NORMAL_USER' in $PYENV_ROOT -----"

  ##############################################################################
  # 1) Install Debian build dependencies for Python (as root)
  #    These packages are required to compile Python if you plan on building
  #    different versions from source with pyenv.
  ##############################################################################
  log "Installing system build dependencies (as root)..."
  apt update 2>&1 | tee -a "$LOG_FILE"
  apt install -y \
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
    libxmlsec1-dev 2>&1 | tee -a "$LOG_FILE"

  apt -y autoremove 2>&1 | tee -a "$LOG_FILE"
  apt clean 2>&1 | tee -a "$LOG_FILE"
  log "System build dependencies installed."

  ##############################################################################
  # 2) Clone or update pyenv in /home/<user>/.pyenv (not in root’s home!)
  ##############################################################################
  if [[ ! -d "$PYENV_ROOT" ]]; then
    log "pyenv not found in $PYENV_ROOT. Cloning from GitHub..."
    sudo -u "$NORMAL_USER" -H git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT" 2>&1 | tee -a "$LOG_FILE"
  else
    log "pyenv already exists in $PYENV_ROOT. Updating..."
    pushd "$PYENV_ROOT" >/dev/null || return 1
    sudo -u "$NORMAL_USER" -H git pull --ff-only 2>&1 | tee -a "$LOG_FILE"
    popd >/dev/null || return 1
  fi

  ##############################################################################
  # 3) Ensure pyenv is initialized in the normal user’s .bashrc
  ##############################################################################
  if ! sudo -u "$NORMAL_USER" grep -q 'export PYENV_ROOT' "$BASHRC_FILE" 2>/dev/null; then
    log "Adding pyenv init lines to $BASHRC_FILE..."
    cat <<EOF | sudo -u "$NORMAL_USER" tee -a "$BASHRC_FILE" >/dev/null

# >>> pyenv initialization >>>
export PYENV_ROOT="$HOME/.pyenv"
export PATH="\$PYENV_ROOT/bin:\$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "\$(pyenv init -)"
fi
# <<< pyenv initialization <<<
EOF
  else
    log "pyenv init lines already found in $BASHRC_FILE. No changes made."
  fi

  # Make sure permissions are correct
  chown "$NORMAL_USER":"$NORMAL_USER" -R "$PYENV_ROOT"
  chown "$NORMAL_USER":"$NORMAL_USER" "$BASHRC_FILE"

  ##############################################################################
  # 4) Install or upgrade the latest Python 3.x with pyenv (as the normal user)
  ##############################################################################
  log "Finding and installing the latest stable Python 3.x via pyenv..."
  local LATEST_PY3
  # The sudo command includes a bash -c, so we can source the .bashrc
  # and run pyenv commands reliably.
  LATEST_PY3="$(sudo -u "$NORMAL_USER" -i bash -c '
    source ~/.bashrc
    pyenv install -l 2>/dev/null | awk "/^[[:space:]]*3\\.[0-9]+\\.[0-9]+\$/{ latest=\$1 }END{ print latest }"
  ')"

  if [[ -z "$LATEST_PY3" ]]; then
    log "[ERROR] Could not detect the latest Python 3.x version with pyenv."
    return 1
  fi

  # Check if user’s pyenv already has that version
  local ALREADY_INSTALLED
  ALREADY_INSTALLED="$(sudo -u "$NORMAL_USER" -i bash -c "
    source ~/.bashrc
    pyenv versions --bare | grep '^${LATEST_PY3}\$' || true
  ")"

  if [[ -z "$ALREADY_INSTALLED" ]]; then
    log "Installing Python $LATEST_PY3 for user $NORMAL_USER..."
    sudo -u "$NORMAL_USER" -i bash -c "
      source ~/.bashrc
      pyenv install '$LATEST_PY3'
      pyenv global '$LATEST_PY3'
      pyenv rehash
    "
  else
    log "Python $LATEST_PY3 is already installed. Setting pyenv global to $LATEST_PY3."
    sudo -u "$NORMAL_USER" -i bash -c "
      source ~/.bashrc
      pyenv global '$LATEST_PY3'
      pyenv rehash
    "
  fi

  ##############################################################################
  # 5) Install pipx and some global Python tools for the normal user
  ##############################################################################
  log "Checking and installing pipx for user $NORMAL_USER..."
  sudo -u "$NORMAL_USER" -i bash -c '
    source ~/.bashrc
    if ! command -v pipx &>/dev/null; then
      python -m pip install --upgrade --user pipx
      # Ensure ~/.local/bin is in PATH
      if ! grep -q "$HOME/.local/bin" ~/.bashrc; then
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc
      fi
    else
      pipx upgrade pipx || true
    fi
  '

  # Define a set of CLI tools for pipx
  local PIPX_TOOLS=(
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

  log "Installing/upgrading pipx tools for user $NORMAL_USER..."
  for tool in "${PIPX_TOOLS[@]}"; do
    sudo -u "$NORMAL_USER" -i bash -c "
      source ~/.bashrc
      if pipx list | grep -q '${tool}'; then
        pipx upgrade '${tool}' || true
      else
        pipx install '${tool}' || true
      fi
    "
  done

  log "pyenv + pipx installation for user '$NORMAL_USER' completed."
  log "-------------------------------------------------------------------"
}

################################################################################
# MAIN
################################################################################
main() {
  log "--------------------------------------"
  log "Starting Debian Automated System Configuration Script"

  identify_primary_iface
  apt_and_settings
  create_user "sawyer"
  install_caddy
  bootstrap_and_install_pkgs
  overwrite_sshd_config
  configure_sudoers
  set_default_shell_and_env
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
  enable_extra_debian_repos
  configure_timezone "America/New_York"
  set_hostname "debian"
  configure_automatic_updates
  install_container_engine
  basic_security_hardening
  manage_service "firewalld" "enable"
  manage_service "firewalld" "start"
  create_caddyfile
  manage_service "caddy" "enable"
  manage_service "caddy" "start"
  setup_pyenv_and_python_tools_for_user "$USERNAME"
  finalize_configuration
  system_cleanup

  log "Configuration script finished successfully."
  log "--------------------------------------"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi