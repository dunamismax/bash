#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# NetBSD Automated Setup Script
# ------------------------------------------------------------------------------
# Automates fresh system configuration:
#  • Updates repositories, installs/upgrades essential software.
#  • Backs up and customizes key configuration files for security and performance.
#  • Sets up user "sawyer" with sudo privileges and a configured shell environment.
#  • Enables/configures services: SSH, NTP, etc.
#  • Installs optional tools: Caddy, Python, Go, Rust, Zig, etc.
#
# Usage:
#  • Run as root or via sudo.
#  • Adjust variables (USERNAME, PACKAGES, etc.) as needed.
#  • Logs actions/errors to /var/log/netbsd_setup.log with timestamps.
#
# Author: dunamismax | Adapted for NetBSD | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Check if script is run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (e.g., sudo $0). Exiting."
  exit 1
fi

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/netbsd_setup.log"
VERBOSE=2
USERNAME="sawyer"

PACKAGES=(
  bash zsh fish vim nano mc screen tmux node npm ninja meson 
  fonts-font-awesome gettext 
  cmake git curl wget tcpdump rsync htop passwd bash-completion neofetch tig jq
  nmap tree fzf lynx which patch smartmontools ntfs-3g
  cups neovim libglade libtool pkgconf libssl
  xz python python%3 python3-pip python3-venv
  # Add any additional NetBSD-specific packages here
)

# ------------------------------------------------------------------------------
# Function: logging function
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
    local NC='\033[0m'

    case "${level^^}" in
        INFO) local color="${GREEN}" ;;
        WARN|WARNING) local color="${YELLOW}" level="WARN" ;;
        ERROR) local color="${RED}" ;;
        DEBUG) local color="${BLUE}" ;;
        *) local color="${NC}" level="INFO" ;;
    esac

    # Ensure the log file exists
    if [[ ! -e "$LOG_FILE" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
    fi

    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"

    if [[ "$VERBOSE" -ge 2 ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    elif [[ "$VERBOSE" -ge 1 && "$level" == "ERROR" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

handle_error() {
  log ERROR "An error occurred. Check the log for details."
}

trap 'log ERROR "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# Function: backup_system
# ------------------------------------------------------------------------------
backup_system() {
    if ! command -v rsync >/dev/null 2>&1; then
      pkgin install -y rsync
    fi

    local SOURCE="/"                       
    local DESTINATION="/home/$USERNAME/BACKUPS"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_FOLDER="$DESTINATION/backup-$TIMESTAMP"
    local RETENTION_DAYS=7
    local EXCLUDES=(
        "/proc/*" "/sys/*" "/dev/*" "/run/*" "/tmp/*" "/mnt/*"
        "/media/*" "/swapfile" "/lost+found" "/var/tmp/*" "/var/cache/*"
        "/var/log/*" "$DESTINATION"
    )
    local EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
    done

    mkdir -p "$BACKUP_FOLDER"
    log INFO "Starting system backup to $BACKUP_FOLDER"
    if rsync -aAXv "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"; then
        log INFO "Backup completed successfully: $BACKUP_FOLDER"
    else
        log ERROR "Error: Backup process failed."
        exit 1
    fi

    log INFO "Cleaning up old backups older than $RETENTION_DAYS days."
    find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} \;
}

# ------------------------------------------------------------------------------
# Function: configure_ssh_settings
# ------------------------------------------------------------------------------
configure_ssh_settings() {
  log INFO "Installing OpenSSH Server..."

  if ! pkg_info | grep -qw openssh; then
    pkgin install -y openssh
    log INFO "OpenSSH installed."
  else
    log INFO "OpenSSH is already installed."
  fi

  # Enable sshd in /etc/rc.conf.local
  if ! grep -q "^sshd=YES" /etc/rc.conf.local 2>/dev/null; then
    echo 'sshd=YES' >> /etc/rc.conf.local
  fi

  service sshd start || log WARN "sshd may already be running."

  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$sshd_config" "$backup_file" && log INFO "Backup created at $backup_file."

  declare -A sshd_settings=(
    ["Port"]="22"
    ["MaxAuthTries"]="8"
    ["MaxSessions"]="6"
    ["PermitRootLogin"]="no"
    ["Protocol"]="2"
  )

  for setting in "${!sshd_settings[@]}"; do
    if grep -q "^${setting} " "$sshd_config"; then
      sed -i "s/^${setting} .*/${setting} ${sshd_settings[$setting]}/" "$sshd_config"
    else
      echo "${setting} ${sshd_settings[$setting]}" >> "$sshd_config"
    fi
  done

  log INFO "SSH server configuration updated. Restarting sshd..."
  service sshd restart || log ERROR "Failed to restart sshd."
}

# ------------------------------------------------------------------------------
# Function: bootstrap_and_install_pkgs
# ------------------------------------------------------------------------------
bootstrap_and_install_pkgs() {
  log INFO "Updating package repository..."
  pkgin update

  log INFO "Upgrading existing packages..."
  pkgin full-upgrade -y || true

  local packages_to_install=()
  for pkg in "${PACKAGES[@]}"; do
    if ! pkg_info | grep -qw "^$pkg-"; then
      packages_to_install+=("$pkg")
    else
      log INFO "Package '$pkg' is already installed."
    fi
  done

  if [ ${#packages_to_install[@]} -gt 0 ]; then
    log INFO "Installing packages: ${packages_to_install[*]}"
    pkgin install -y "${packages_to_install[@]}"
  else
    log INFO "All listed packages are already installed. No action needed."
  fi

  log INFO "Package installation process completed."
}

# ------------------------------------------------------------------------------
# Function: configure_timezone
# ------------------------------------------------------------------------------
configure_timezone() {
  local tz="${1:-UTC}"
  log INFO "Configuring timezone to '${tz}'..."
  cp /usr/share/zoneinfo/"$tz" /etc/localtime
  echo "$tz" > /etc/timezone 2>/dev/null || true
  log INFO "Timezone set to $tz."
}

# ------------------------------------------------------------------------------
# Function: fail2ban
# ------------------------------------------------------------------------------
fail2ban() {
  log INFO "Attempting to install fail2ban..."
  if pkg_info | grep -qw fail2ban; then
    log INFO "fail2ban already installed."
  else
    pkgin install -y fail2ban || log WARN "fail2ban not available on NetBSD."
  fi
}

# ------------------------------------------------------------------------------
# Function: configure_ntp
# ------------------------------------------------------------------------------
configure_ntp() {
  log INFO "Configuring NTP (ntpd)..."
  if ! pkg_info | grep -qw ntp; then
    pkgin install -y ntp
  fi

  if ! grep -q "^ntpd=YES" /etc/rc.conf.local 2>/dev/null; then
    echo 'ntpd=YES' >> /etc/rc.conf.local
  fi
  service ntpd start || log WARN "ntpd may already be running."
  log INFO "NTP (ntpd) configuration complete."
}

# ------------------------------------------------------------------------------
# Function: install_all_build_dependencies
# ------------------------------------------------------------------------------
install_all_build_dependencies() {
    log INFO "Installing build dependencies..."
    pkgin install -y base-devel git curl wget vim tmux unzip zip ca_root_nss pkgconf \
        openssl-devel bzip2 libffi zlib readline sqlite tk ncurses gdb llvm
    if ! command -v rustc >/dev/null 2>&1; then
      log INFO "Installing Rust toolchain via rustup..."
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
      export PATH="$HOME/.cargo/bin:$PATH"
    else
      log INFO "Rust toolchain is already installed."
    fi

    log INFO "Installing Go..."
    pkgin install -y go

    log INFO "Build dependencies installed successfully."
}

# ------------------------------------------------------------------------------
# Function: install_caddy
# ------------------------------------------------------------------------------
install_caddy() {
  log INFO "Installing Caddy..."
  if pkg_info | grep -qw caddy; then
    log INFO "Caddy is already installed."
  else
    pkgin install -y caddy || log WARN "Caddy package not found."
  fi
}

# ------------------------------------------------------------------------------
# Function: install_zig
# ------------------------------------------------------------------------------
install_zig() {
  if command -v zig &>/dev/null; then
    log INFO "Zig is already installed. Skipping."
    return
  fi

  log INFO "Installing Zig..."
  if pkg_info | grep -qw zig; then
    pkgin install -y zig
  else
    log WARN "Zig package not available. Manual installation may be required."
  fi
}

# ------------------------------------------------------------------------------
# Function: download_repositories
# ------------------------------------------------------------------------------
download_repositories() {
  log INFO "Downloading GitHub repositories..."

  local GH_DIR="/home/$USERNAME/github"
  mkdir -p "$GH_DIR"
  cd "$GH_DIR" || exit 1

  repos=( "bash" "c" "religion" "windows" "hugo" "python" )

  for repo in "${repos[@]}"; do
    [ -d "$repo" ] && { log INFO "Removing existing $repo"; rm -rf "$repo"; }
    log INFO "Cloning repository: $repo"
    git clone "https://github.com/dunamismax/${repo}.git"
  done

  log INFO "Repositories downloaded."
  cd ~
}

# ------------------------------------------------------------------------------
# Function: fix_git_permissions
# ------------------------------------------------------------------------------
fix_git_permissions() {
    local git_dir="$1"
    log INFO "Setting stricter permissions for $git_dir"
    chmod 700 "$git_dir"
    find "$git_dir" -type d -exec chmod 700 {} \;
    find "$git_dir" -type f -exec chmod 600 {} \;
    log INFO "Permissions fixed for $git_dir"
}

# ------------------------------------------------------------------------------
# Function: set_directory_permissions
# ------------------------------------------------------------------------------
set_directory_permissions() {
  local GITHUB_DIR="/home/$USERNAME/github"
  local HUGO_PUBLIC_DIR="/home/$USERNAME/github/hugo/dunamismax.com/public"
  local HUGO_DIR="/home/$USERNAME/github/hugo"
  local SAWYER_HOME="/home/$USERNAME"
  local BASE_DIR="/home/$USERNAME/github"
  local DIR_PERMISSIONS="700"
  local FILE_PERMISSIONS="600"

  log INFO "Making all .sh files executable under $GITHUB_DIR"
  find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} \;

  log INFO "Setting ownership for /home/$USERNAME/github and /home/$USERNAME"
  chown -R "$USERNAME":"$USERNAME" "/home/$USERNAME/github"
  chown -R "$USERNAME":"$USERNAME" "/home/$USERNAME/"

  # If Hugo directories exist, set permissions
  if [[ -d "$HUGO_PUBLIC_DIR" ]]; then
    log INFO "Setting ownership and permissions for Hugo public directory"
    chmod -R 755 "$HUGO_PUBLIC_DIR"
    chown -R www:www "$HUGO_PUBLIC_DIR" 2>/dev/null || true
  fi

  if [[ -d "$HUGO_DIR" ]]; then
    log INFO "Setting ownership and permissions for Hugo directory"
    chown -R caddy:caddy "$HUGO_DIR" 2>/dev/null || true
    chmod o+rx "$SAWYER_HOME" "$GITHUB_DIR" "$HUGO_DIR" || true
  fi

  if [[ ! -d "$BASE_DIR" ]]; then
      log ERROR "Error: Base directory $BASE_DIR does not exist."
      exit 1
  fi

  log INFO "Starting permission fixes in $BASE_DIR..."
  while IFS= read -r -d '' git_dir; do
      fix_git_permissions "$git_dir"
  done < <(find "$BASE_DIR" -type d -name ".git" -print0)

  log INFO "Permission setting completed."
}

# ------------------------------------------------------------------------------
# Function: dotfiles_load
# ------------------------------------------------------------------------------
dotfiles_load() {
  log INFO "Creating necessary directories..."
  mkdir -p /home/$USERNAME/.config

  log INFO "Copying dotfiles to /home/$USERNAME..."
  cp /home/$USERNAME/github/bash/dotfiles/.bash_profile        /home/$USERNAME/ 2>/dev/null || true
  cp /home/$USERNAME/github/bash/dotfiles/.bashrc              /home/$USERNAME/ 2>/dev/null || true
  cp /home/$USERNAME/github/bash/dotfiles/.fehbg               /home/$USERNAME/ 2>/dev/null || true
  cp /home/$USERNAME/github/bash/dotfiles/.profile             /home/$USERNAME/ 2>/dev/null || true
  cp /home/$USERNAME/github/bash/dotfiles/chrony.conf          /etc/chrony/ 2>/dev/null || true
  cp /home/$USERNAME/github/bash/dotfiles/Caddyfile            /etc/caddy/ 2>/dev/null || true

  log INFO "Copying config directories to /home/$USERNAME/..."
  cp -r /home/$USERNAME/github/bash/dotfiles/bin        /home/$USERNAME/.local/ 2>/dev/null || true
  cp -r /home/$USERNAME/github/bash/dotfiles/i3         /home/$USERNAME/.config/ 2>/dev/null || true
  cp -r /home/$USERNAME/github/bash/dotfiles/rofi       /home/$USERNAME/.config/ 2>/dev/null || true
  cp -r /home/$USERNAME/github/bash/dotfiles/alacritty  /home/$USERNAME/.config/ 2>/dev/null || true

  chown -R "$USERNAME":"$USERNAME" "/home/$USERNAME/"
  chown caddy:caddy /etc/caddy/Caddyfile 2>/dev/null || true

  log INFO "Dotfiles copied successfully."
}

# ------------------------------------------------------------------------------
# Function: finalize_configuration
# ------------------------------------------------------------------------------
finalize_configuration() {
  log INFO "Finalizing system configuration..."

  cd /home/$USERNAME

  log INFO "Upgrading installed packages..."
  pkgin full-upgrade -y || true

  log INFO "Cleaning up package cache..."
  pkgin clean-cache || true

  log INFO "Collecting system information..."
  log INFO "System Uptime: $(uptime)"
  log INFO "Disk Usage (root): $(df -h / | tail -1)"
  # Memory and CPU info differ on BSD; use sysctl where applicable.
  log INFO "Memory Usage: $(sysctl hw.physmem hw.usermem 2>/dev/null || echo 'N/A')"
  log INFO "Kernel Version: $(uname -r)"
  log INFO "Network Configuration: $(ifconfig -a)"
  log INFO "System information logged."

  log INFO "System configuration finalized."
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
  log INFO "--------------------------------------"
  log INFO "Starting NetBSD Automated System Configuration Script"

  backup_system
  configure_ssh_settings
  bootstrap_and_install_pkgs
  configure_timezone "America/New_York"
  configure_ntp
  fail2ban
  install_all_build_dependencies
  install_zig
  install_caddy
  download_repositories
  set_directory_permissions
  dotfiles_load
  finalize_configuration

  log INFO "Configuration script finished successfully."
  log INFO "Enjoy NetBSD!"
  log INFO "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi