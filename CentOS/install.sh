#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# CentOS Stream Automated System Configuration Script + Python/pyenv/pipx Setup
# ------------------------------------------------------------------------------
# Description:
#   This script automates the configuration of a fresh CentOS Stream installation by:
#
#   1) Updating DNF/YUM and installing essential packages (including epel-release).
#   2) Overwriting selected configuration files (/etc/resolv.conf, /etc/ssh/sshd_config)
#      and backing up the originals.
#   3) Granting sudo privileges to the user "dowdy" and configuring Bash as the default shell.
#   4) Adding Python environment setup (pyenv + pipx) for the latest stable Python 3.x
#      plus a curated set of Python CLI tools.
#
# Notes:
#   • All log output is appended to /var/log/centos_setup.log.
#   • This script uses set -euo pipefail, along with a trap handler to catch unexpected errors.
#   • Run as root on a new CentOS Stream installation (or from a clean snapshot for testing).
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Trap errors and print a friendly message
trap 'echo "[ERROR] Script failed at line $LINENO. See above for details." >&2' ERR

# --------------------------------------
# CONFIGURATION
# --------------------------------------

LOG_FILE="/var/log/centos_setup.log"
USERNAME="dowdy"
PRIMARY_IFACE=""    # Will be detected automatically, if possible

# List of packages to install for the core system configuration
# (Ensure epel-release is near the top so dnf can install from EPEL-enabled repos.)
PACKAGES=(
  # Repos / plugin for enabling CRB, etc.
  epel-release
  dnf-plugins-core

  # Shells and terminal utilities
  bash zsh fish
  vim nano mc screen tmux

  # Basic dev tools
  gcc make gcc-c++ autoconf automake cmake libtool pkgconfig \
  openssl-devel bzip2 bzip2-devel libffi-devel zlib-devel \
  readline-devel sqlite-devel tk-devel xz xz-devel ncurses-devel \
  python3-devel freetype-devel

  # Generic system utilities
  git perl python3 python3-pip curl wget
  tcpdump rsync
  htop sudo bash-completion neofetch tig jq nmap tree fzf lynx
  which patch smartmontools util-linux-user

  # For virtualization
  qemu-kvm libvirt libvirt-devel virt-install bridge-utils

  # Add chrony for NTP (if you want it in the same pass)
  chrony

  # Firewalld
  firewalld

  # For SELinux administration
  policycoreutils-python-utils

  # (Optional) fail2ban if you want it installed here:
  fail2ban

  # (Optional) dnf-automatic for autoupdates
  dnf-automatic

  # Multimedia tooling from RPM Fusion
  ffmpeg

  # restic also from EPEL or RPM Fusion
  restic
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
################################################################################
handle_error() {
  log "An error occurred. Check the log for details."
  exit 1
}

################################################################################
# Function: identify_primary_iface
# Identify the primary network interface on CentOS
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
# dnf update and install our base PACKAGES
################################################################################
bootstrap_and_install_pkgs() {
  log "Updating DNF database and upgrading existing packages..."
  dnf -y update 2>&1 | tee -a "$LOG_FILE"

  local packages_to_install=()
  for pkg in "${PACKAGES[@]}"; do
    # If not installed, queue it up for installation
    if ! rpm -q "$pkg" &>/dev/null; then
      packages_to_install+=("$pkg")
    else
      log "Package '$pkg' is already installed."
    fi
  done

  if [ ${#packages_to_install[@]} -gt 0 ]; then
    log "Installing packages: ${packages_to_install[*]}"
    dnf -y install "${packages_to_install[@]}" 2>&1 | tee -a "$LOG_FILE"
  else
    log "All listed packages are already installed. No action needed."
  fi

  dnf -y autoremove 2>&1 | tee -a "$LOG_FILE"
  dnf clean all 2>&1 | tee -a "$LOG_FILE"

  log "Package installation process completed."
}

################################################################################
# Function: overwrite_resolv_conf
# Overwrite /etc/resolv.conf
################################################################################
overwrite_resolv_conf() {
  log "Backing up and overwriting /etc/resolv.conf..."

  local resolv_conf="/etc/resolv.conf"

  # Remove symlink if present
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
# Basic CentOS SSHD Configuration

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
# Configure user in the wheel group (typical on CentOS)
################################################################################
configure_sudoers() {
  log "Configuring sudoers for $USERNAME..."

  # Add user to the wheel group
  usermod -aG wheel "$USERNAME"

  # Ensure /etc/sudoers has a rule for %wheel
  local sudoers_file="/etc/sudoers"
  local sudo_rule="%wheel ALL=(ALL) ALL"

  if ! grep -q "^%wheel" "$sudoers_file"; then
    echo "$sudo_rule" >> "$sudoers_file"
    log "Added group 'wheel' rule to /etc/sudoers."
  else
    log "Group 'wheel' rule already exists in /etc/sudoers."
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
# Function: configure_firewalld
# Description:
#   1) Enables and starts firewalld.
#   2) Accepts any number of firewall-cmd arguments as parameters.
#   3) Applies each rule using --permanent, then reloads firewalld.
#
# Example usage:
#   configure_firewalld \
#       "--add-service=ssh" \
#       "--add-port=8080/tcp"
################################################################################
configure_firewalld() {
  log "Enabling and starting firewalld..."
  systemctl enable firewalld
  systemctl start firewalld

  if [ $# -eq 0 ]; then
    log "No firewall rules provided. Firewalld is running but no new rules were added."
  else
    for rule in "$@"; do
      log "Applying firewall rule: firewall-cmd --permanent $rule"
      firewall-cmd --permanent $rule 2>&1 | tee -a "$LOG_FILE"
    done
    log "Reloading firewalld to apply changes..."
    firewall-cmd --reload 2>&1 | tee -a "$LOG_FILE"
  fi
}

################################################################################
# Function: configure_ntp
# Installs and configures chrony for time synchronization
################################################################################
configure_ntp() {
  log "Installing and configuring chrony for time sync..."

  dnf -y install chrony
  systemctl enable chronyd
  systemctl start chronyd

  # Optional: Modify /etc/chrony.conf if you have preferred NTP servers
  # sed -i 's/^pool .*/pool your.ntp.server iburst/g' /etc/chrony.conf

  systemctl restart chronyd
  log "Time sync service configured."
}

################################################################################
# Function: enable_epel_and_crb
# Description:
#   Installs and enables EPEL repository and CodeReady Builder (CRB, a.k.a. PowerTools).
################################################################################
enable_epel_and_crb() {
  log "Enabling EPEL and CRB repositories..."

  # EPEL is often in your PACKAGES list already, but just in case:
  if ! rpm -q epel-release &>/dev/null; then
    dnf -y install epel-release
  fi

  # Enable CodeReady Builder (or 'PowerTools' depending on CentOS version)
  # On CentOS Stream 8, it's 'crb'. For older CentOS 8 it was 'PowerTools'.
  # On CentOS Stream 9, it may be slightly different naming.
  dnf config-manager --set-enabled crb || true
  # dnf config-manager --set-enabled powertools || true

  dnf clean all
  dnf -y update

  log "EPEL and CRB repositories are now enabled."
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
  dnf -y install tzdata

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
#   Applies a minimal set of security best practices:
#     - Disables root SSH login
#     - Sets up a fail2ban-like mechanism (optional)
#     - Installs or updates AIDE (file integrity monitoring)
################################################################################
basic_security_hardening() {
  log "Applying basic security hardening..."

  # 1) Disable root login in sshd_config
  sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  systemctl restart sshd

  # 2) Install fail2ban (not always in default repos; might need EPEL)
  if ! rpm -q fail2ban &>/dev/null; then
    dnf -y install fail2ban
    systemctl enable fail2ban
    systemctl start fail2ban
  fi

  # 3) Optional – Install AIDE
  if ! rpm -q aide &>/dev/null; then
    dnf -y install aide
    aide --init
    mv /var/lib/aide/aide.db.new.gz /var/lib/aide/aide.db.gz
  fi

  log "Security hardening steps completed."
}

################################################################################
# Function: configure_automatic_updates
# Description:
#   Installs and configures the dnf-automatic service to run nightly reboots or
#   updates automatically. Adjust the config as needed (e.g., security-only).
################################################################################
configure_automatic_updates() {
  log "Configuring dnf-automatic for nightly updates..."

  dnf -y install dnf-automatic

  # Basic config adjustments:
  sed -i 's/^apply_updates.*/apply_updates = yes/' /etc/dnf/automatic.conf
  sed -i 's/^emit_via.*/emit_via = email/' /etc/dnf/automatic.conf
  # Optionally set up your smtp_server, email_from, email_to, etc.

  systemctl enable dnf-automatic.timer
  systemctl start dnf-automatic.timer

  log "Automatic updates have been enabled."
}

################################################################################
# Function to install Caddy: install_caddy
################################################################################
install_caddy() {
    log "Installing Caddy"
    dnf install 'dnf-command(copr)'
    dnf copr enable @caddy/caddy
    dnf install caddy
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
    root * /home/dowdy/GitHub/Hugo/dunamismax.com/public
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
# Function: configure_selinux
# Description:
#   Configures SELinux mode (e.g., enforcing, permissive, or disabled) and optionally
#   sets certain SELinux booleans that are common in web server or dev scenarios.
################################################################################
configure_selinux() {
  local selinux_mode="${1:-enforcing}"  # Defaults to "enforcing"

  log "Setting SELinux to '${selinux_mode}' mode..."

  # Modify /etc/selinux/config
  sed -i "s/^SELINUX=.*/SELINUX=${selinux_mode}/g" /etc/selinux/config

  # Apply immediately (only if changing from/to 'enforcing' or 'permissive';
  # for 'disabled', a reboot is required)
  if [[ "$selinux_mode" == "enforcing" || "$selinux_mode" == "permissive" ]]; then
    setenforce "$selinux_mode" 2>/dev/null || true
  fi

  # Example: Setting specific SELinux booleans if needed
  # setsebool -P httpd_can_network_connect 1

  log "SELinux configuration updated to '${selinux_mode}'. A reboot may be required if you set it to disabled."
}

################################################################################
# Function: install_container_engine
# Description:
#   Installs either Docker or Podman on CentOS Stream, enables and starts it.
#   Adjust the function to your preference.
################################################################################
install_container_engine() {
  local engine="${1:-docker}"

  case "$engine" in
    "docker")
      log "Installing Docker CE..."
      # Setup Docker repo
      dnf -y install dnf-plugins-core
      dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
      dnf -y install docker-ce docker-ce-cli containerd.io

      systemctl enable docker
      systemctl start docker
      log "Docker installed and running."
      ;;
    "podman")
      log "Installing Podman..."
      dnf -y install podman
      log "Podman installed."
      ;;
    *)
      log "[ERROR] Unknown container engine: $engine"
      return 1
      ;;
  esac
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
  dnf -y autoremove

  # Clean dnf caches
  dnf clean all

  log "System cleanup completed."
}

################################################################################
# Function: dnf_and_settings
# Description:
#   1) Configure /etc/dnf/dnf.conf to enable fastest mirror, parallel downloads,
#      default "yes" behavior, and keepcache.
#   2) Clean the DNF cache.
#   3) Update the system.
#   4) Enable RPM Fusion (free/nonfree) repositories.
#   5) Perform a group update of "core".
#   6) Add Flatpak (Flathub) remote for installing Flatpak apps.
#
# Notes:
#   - You must run this function as root (or with sudo).
#   - Adjust logging or environment variable references as needed.
################################################################################
dnf_and_settings() {

  # 1) DNF Configuration
  echo "[INFO] Configuring /etc/dnf/dnf.conf..."
  if [ ! -f /etc/dnf/dnf.conf ]; then
    touch /etc/dnf/dnf.conf
  fi

  # Backup the existing config just in case
  cp /etc/dnf/dnf.conf /etc/dnf/dnf.conf.bak.$(date +%Y%m%d%H%M%S)

  # Overwrite /etc/dnf/dnf.conf with desired config
  cat <<EOF > /etc/dnf/dnf.conf
[main]
fastestmirror=True
max_parallel_downloads=10
defaultyes=True
keepcache=True
EOF

  echo "[INFO] DNF configuration updated."

  # Clear DNF cache (dbcache or all)
  echo "[INFO] Clearing DNF cache..."
  dnf clean all

  # 2) System Update
  echo "[INFO] System update in progress. This may take a while..."
  dnf -y update

  # 3) Enable RPM Fusion
  echo "[INFO] Enabling RPM Fusion (free and nonfree)..."

  # Adjust for your RHEL version if needed
  dnf -y install \
  https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm \
  https://mirrors.rpmfusion.org/nonfree/el/rpmfusion-nonfree-release-$(rpm -E %rhel).noarch.rpm

  # 4) Adding Flatpaks (Flathub)
  echo "[INFO] Ensuring flatpak is installed and adding Flathub remote..."
  # Install flatpak if it's not present
  if ! command -v flatpak &>/dev/null; then
    dnf -y install flatpak
  fi

  # Add the Flathub remote if not already set
  flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

  # 5) Install Media Codecs
  echo "[INFO] Installing multimedia codecs..."
  dnf -y groupupdate multimedia --setop="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin
  dnf -y groupupdate sound-and-video

  echo "[INFO] dnf_and_settings routine completed successfully."
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
#   create_user "dowdy"
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
# Function: finalize_configuration
# dnf upgrade
################################################################################
finalize_configuration() {
  log "Finalizing system configuration..."

  dnf -y update 2>&1 | tee -a "$LOG_FILE"
  dnf -y upgrade 2>&1 | tee -a "$LOG_FILE"
  dnf -y autoremove 2>&1 | tee -a "$LOG_FILE"
  dnf clean all 2>&1 | tee -a "$LOG_FILE"

  log "Final configuration steps completed."
}

# ---------------------------------------------------------------------------
# Python environment setup (pyenv + pipx + curated CLI tools)
# We'll wrap that portion into a function "setup_pyenv_and_python_tools"
# and call it at the end of our main flow.
#
# If you need extra details about pyenv usage, see:
#   https://github.com/pyenv/pyenv
# ---------------------------------------------------------------------------

################################################################################
# Additional Script: setup_pyenv_and_python_tools
################################################################################
setup_pyenv_and_python_tools() {

  echo "[INFO] Running integrated pyenv+pipx setup..."

  install_centos_dependencies() {
      echo "[INFO] Updating dnf caches..."
      sudo dnf -y update
      sudo dnf -y install \
          make \
          git \
          curl \
          wget \
          vim \
          tmux \
          unzip \
          zip \
          ca-certificates \
          openssl-devel \
          bzip2-devel \
          libffi-devel \
          zlib-devel \
          readline-devel \
          sqlite-devel \
          ncurses-devel \
          xz \
          xz-devel \
          tk-devel \
          llvm \
          jq \
          gnupg \
          libxml2-devel \
          libxmlsec1-devel

      # Group install "Development Tools" if you want a full GCC toolchain, etc.
      # sudo dnf -y groupinstall "Development Tools"

      sudo dnf -y autoremove
      sudo dnf clean all
  }

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

  local_python_env_main() {
      # Optionally uncomment to apply dnf-based dependencies explicitly:
      # install_centos_dependencies

      install_or_update_pyenv
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

  local_python_env_main
}

################################################################################
# MAIN
################################################################################
main() {
  log "--------------------------------------"
  log "Starting CentOS Stream Automated System Configuration Script"

  identify_primary_iface
  dnf_and_settings
  create_user "dowdy"
  install_caddy
  bootstrap_and_install_pkgs
  overwrite_resolv_conf
  overwrite_sshd_config
  configure_sudoers
  set_default_shell_and_env
  configure_firewalld \
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
  enable_epel_and_crb
  configure_timezone "America/New_York"
  set_hostname "centos-hyperscale"
  configure_automatic_updates
  configure_selinux
  install_container_engine
  basic_security_hardening
  manage_service "firewalld" "enable"
  manage_service "firewalld" "start"
  create_caddyfile
  manage_service "caddy" "enable"
  manage_service "caddy" "start"
  setup_pyenv_and_python_tools
  finalize_configuration
  system_cleanup

  log "Configuration script finished successfully."
  log "--------------------------------------"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi