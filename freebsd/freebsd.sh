#!/usr/bin/env bash
# FreeBSD System Setup Script
# Fully configures a clean install of FreeBSD with tools, hardening, and development configurations.
# Note:
#   - Must be run as root.
#   - Log output is saved to /var/log/freebsd_setup.log.

set -Eeuo pipefail
IFS=$'\n\t'

# Color definitions for logging
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                     # Reset to No Color

LOG_FILE="/var/log/freebsd_setup.log"
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

# Logging functions
log() {
  local level="${1:-INFO}"
  shift
  local message="$*"
  local timestamp
  timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
  local entry="[$timestamp] [${level^^}] $message"
  echo "$entry" >> "$LOG_FILE"
  if [ -t 2 ]; then
    case "${level^^}" in
      INFO)  printf "%b%s%b\n" "$NORD14" "$entry" "$NC" ;;
      WARN)  printf "%b%s%b\n" "$NORD13" "$entry" "$NC" ;;
      ERROR) printf "%b%s%b\n" "$NORD11" "$entry" "$NC" ;;
      DEBUG) printf "%b%s%b\n" "$NORD9"  "$entry" "$NC" ;;
      *)     printf "%s\n" "$entry" ;;
    esac
  else
    echo "$entry" >&2
  fi
}
log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

handle_error() {
  local msg="${1:-An unknown error occurred.}"
  local code="${2:-1}"
  log_error "$msg (Exit Code: $code)"
  log_error "Error encountered at line $LINENO in function ${FUNCNAME[1]:-main}."
  echo -e "${NORD11}ERROR: $msg (Exit Code: $code)${NC}" >&2
  exit "$code"
}

cleanup() {
  log_info "Cleanup tasks complete."
}
trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# Utility function to print section headers
print_section() {
  local title="$1"
  local border
  border=$(printf '─%.0s' {1..60})
  log_info "${NORD14}${border}${NC}"
  log_info "${NORD14}  $title${NC}"
  log_info "${NORD14}${border}${NC}"
}

# Configuration Variables
USERNAME="sawyer"
TIMEZONE="America/New_York"

# Zig installation configuration (FreeBSD build)
ZIG_URL="https://ziglang.org/builds/zig-freebsd-x86_64-0.14.0-dev.3224+5ab511307.tar.xz"
ZIG_DIR="/opt/zig"
ZIG_BIN="/usr/local/bin/zig"

# List of packages (adjust package names as available in pkg)
PACKAGES=(bash vim nano zsh screen tmux mc htop tree ncdu neofetch
          git curl wget rsync sudo python3 py38-pip tzdata gcc cmake
          ninja meson gettext openssh go gdb strace man)

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_error "Script must be run as root. Exiting."
    exit 1
  fi
}

check_network() {
  print_section "Network Connectivity Check"
  log_info "Checking network connectivity..."
  if ! ping -c1 -t5 google.com &>/dev/null; then
    log_warn "No network connectivity detected."
  else
    log_info "Network connectivity OK."
  fi
}

update_system() {
  print_section "System Update & Upgrade"
  log_info "Updating pkg repository..."
  if ! pkg update; then
    log_warn "pkg update encountered issues."
  fi
  log_info "Upgrading installed packages..."
  if ! pkg upgrade -y; then
    log_warn "pkg upgrade encountered issues."
  fi
}

install_packages() {
  print_section "Essential Package Installation"
  log_info "Installing essential packages..."
  if ! pkg install -y "${PACKAGES[@]}"; then
    log_warn "One or more packages failed to install."
  else
    log_info "Package installation complete."
  fi
}

create_user() {
  print_section "User Creation"
  if ! id "$USERNAME" &>/dev/null; then
    log_info "Creating user '$USERNAME'..."
    if ! pw useradd "$USERNAME" -m -s /usr/local/bin/bash -G wheel; then
      log_warn "Failed to create user '$USERNAME'."
    else
      echo "changeme" | pw usermod "$USERNAME" -h 0
      log_info "User '$USERNAME' created with default password 'changeme'."
    fi
  else
    log_info "User '$USERNAME' already exists."
  fi
}

configure_timezone() {
  print_section "Timezone Configuration"
  log_info "Setting timezone to $TIMEZONE..."
  if [ -f "/usr/share/zoneinfo/${TIMEZONE}" ]; then
    cp "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
    echo "$TIMEZONE" > /etc/timezone
    log_info "Timezone set to $TIMEZONE."
  else
    log_warn "Timezone file for $TIMEZONE not found."
  fi
}

setup_repos() {
  print_section "GitHub Repositories Setup"
  local repo_dir="/usr/home/${USERNAME}/github"
  log_info "Cloning repositories into $repo_dir..."
  mkdir -p "$repo_dir"
  for repo in bash windows web python go misc; do
    local target_dir="$repo_dir/$repo"
    rm -rf "$target_dir"
    if ! git clone "https://github.com/dunamismax/$repo.git" "$target_dir"; then
      log_warn "Failed to clone repository: $repo"
    else
      log_info "Cloned repository: $repo"
    fi
  done
  chown -R "${USERNAME}:${USERNAME}" "$repo_dir"
}

copy_shell_configs() {
  print_section "Shell Configuration Files"
  log_info "Copying shell configuration files..."
  for file in .bashrc .profile; do
    local src="/usr/home/${USERNAME}/github/bash/freebsd/dotfiles/$file"
    local dest="/usr/home/${USERNAME}/$file"
    if [ -f "$src" ]; then
      [ -f "$dest" ] && cp "$dest" "${dest}.bak"
      if ! cp -f "$src" "$dest"; then
        log_warn "Failed to copy $src to $dest."
      else
        chown "${USERNAME}:${USERNAME}" "$dest"
        log_info "Copied $src to $dest."
      fi
    else
      log_warn "Source file $src not found."
    fi
  done
}

configure_ssh() {
  print_section "SSH Configuration"
  log_info "Configuring SSH..."
  if sysrc sshd_enable >/dev/null 2>&1; then
    log_info "sshd_enable already set."
  else
    sysrc sshd_enable="YES"
    log_info "sshd_enable set to YES."
  fi
  service sshd restart || log_warn "Failed to restart sshd."
}

secure_ssh_config() {
  print_section "SSH Hardening"
  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="/etc/ssh/sshd_config.bak"
  if [ -f "$sshd_config" ]; then
    cp "$sshd_config" "$backup_file"
    log_info "Backed up SSH config to $backup_file."
    sed -i '' 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
    sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config"
    sed -i '' 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
    sed -i '' 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
    log_info "SSH configuration hardened."
    service sshd restart || log_warn "Failed to restart sshd after hardening."
  else
    log_warn "SSHD configuration file not found."
  fi
}

install_plex() {
  print_section "Plex Media Server Installation"
  log_info "Installing Plex Media Server..."
  if pkg install -y plexmediaserver; then
    log_info "Plex Media Server installed successfully."
  else
    log_warn "Failed to install Plex Media Server."
  fi
}

configure_zfs() {
  print_section "ZFS Configuration"
  log_info "Configuring ZFS pool..."
  local ZPOOL_NAME="WD_BLACK"
  local MOUNT_POINT="/mnt/${ZPOOL_NAME}"
  if ! zpool list "$ZPOOL_NAME" &>/dev/null; then
    log_info "ZFS pool '$ZPOOL_NAME' not found. Skipping import."
  else
    log_info "ZFS pool '$ZPOOL_NAME' found."
    if zfs set mountpoint="${MOUNT_POINT}" "$ZPOOL_NAME"; then
      log_info "Mountpoint for pool '$ZPOOL_NAME' set to '$MOUNT_POINT'."
    else
      log_warn "Failed to set mountpoint for $ZPOOL_NAME."
    fi
  fi
}

deploy_user_scripts() {
  print_section "Deploying User Scripts"
  local bin_dir="/usr/home/${USERNAME}/bin"
  local scripts_src="/usr/home/${USERNAME}/github/bash/freebsd/_scripts/"
  log_info "Deploying user scripts from $scripts_src to $bin_dir..."
  mkdir -p "$bin_dir"
  if rsync -ah --delete "$scripts_src" "$bin_dir"; then
    find "$bin_dir" -type f -exec chmod 755 {} \;
    log_info "User scripts deployed successfully."
  else
    log_warn "Failed to deploy user scripts."
  fi
}

setup_cron() {
  print_section "Cron Service Setup"
  log_info "Starting cron service..."
  service cron start || log_warn "Failed to start cron."
}

configure_periodic() {
  print_section "Periodic Maintenance Setup"
  log_info "Configuring daily system maintenance tasks..."
  local cron_file="/etc/periodic/daily/freebsd_maintenance"
  if [ -f "$cron_file" ]; then
    mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" && \
      log_info "Existing periodic script backed up." || \
      log_warn "Failed to backup existing periodic script."
  fi
  cat << 'EOF' > "$cron_file"
#!/bin/sh
# FreeBSD maintenance script
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
  if chmod +x "$cron_file"; then
    log_info "Daily maintenance script created at $cron_file."
  else
    log_warn "Failed to set execute permission on $cron_file."
  fi
}

install_fastfetch() {
  print_section "Fastfetch Installation"
  log_info "Installing Fastfetch..."
  local FASTFETCH_URL="https://github.com/fastfetch-cli/fastfetch/releases/download/2.36.1/fastfetch-freebsd-amd64.tar.xz"
  local tmp_tar="/tmp/fastfetch.tar.xz"
  if curl -L -o "$tmp_tar" "$FASTFETCH_URL"; then
    if tar -xf "$tmp_tar" -C /usr/local/bin; then
      chmod +x /usr/local/bin/fastfetch
      rm -f "$tmp_tar"
      if command -v fastfetch &>/dev/null; then
        log_info "Fastfetch installed successfully."
      else
        log_error "Fastfetch is not accessible."
      fi
    else
      log_error "Failed to extract fastfetch."
      rm -f "$tmp_tar"
    fi
  else
    log_error "Failed to download Fastfetch."
  fi
}

final_checks() {
  print_section "Final System Checks"
  log_info "Performing final system checks:"
  echo "Kernel: $(uname -r)"
  echo "Uptime: $(uptime)"
  df -h /
  swapinfo -h || true
}

home_permissions() {
  print_section "Home Directory Permissions"
  local home_dir="/usr/home/${USERNAME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir"
  find "$home_dir" -type d -exec chmod g+s {} \;
}

prompt_reboot() {
  print_section "Reboot Prompt"
  read -rp "Reboot now? [y/N]: " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    log_info "Rebooting system..."
    reboot
  else
    log_info "Reboot canceled. Please reboot later to apply all changes."
  fi
}

main() {
  check_root
  check_network
  update_system
  install_packages
  create_user
  configure_timezone
  setup_repos
  copy_shell_configs
  configure_ssh
  secure_ssh_config
  install_plex
  configure_zfs
  deploy_user_scripts
  setup_cron
  configure_periodic
  final_checks
  home_permissions
  install_fastfetch
  prompt_reboot
}

main "$@"
