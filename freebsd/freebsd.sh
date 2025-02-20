#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

LOG_FILE="/var/log/freebsd_setup.log"
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() {
  local level="${1:-INFO}"
  shift
  local message="$*"
  local timestamp
  timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
  local entry="[$timestamp] [${level^^}] $message"
  echo "$entry" >> "$LOG_FILE"
  echo "$entry"
}
log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_warn "Script must be run as root. Exiting."
    exit 1
  fi
}

check_network() {
  log_info "Checking network connectivity..."
  if ! ping -c1 -t5 google.com &>/dev/null; then
    log_warn "No network connectivity detected."
  else
    log_info "Network connectivity OK."
  fi
}

update_system() {
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
  PACKAGES=(
    bash vim nano zsh screen tmux mc htop tree ncdu neofetch
    git curl wget rsync sudo python3 py38-pip tzdata gcc cmake
    ninja meson gettext openssh go gdb strace man
    xorg i3 sddm alacritty dmenu i3blocks
  )
  
  log_info "Installing essential packages..."
  if ! pkg install -y "${PACKAGES[@]}"; then
    log_warn "One or more packages failed to install."
  else
    log_info "Package installation complete."
  fi

  # Enable necessary services
  sysrc dbus_enable="YES"
  sysrc sddm_enable="YES"

  # Start services
  service dbus start
  service sddm start
}

create_user() {
  USERNAME="sawyer"
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
  TIMEZONE="America/New_York"
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
  USERNAME="sawyer"
  local repo_dir="/home/${USERNAME}/github"
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
  USERNAME="sawyer"
  log_info "Copying shell configuration files..."
  for file in .bashrc .profile; do
    local src="/home/${USERNAME}/github/bash/freebsd/dotfiles/$file"
    local dest="/home/${USERNAME}/$file"
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
  log_info "Installing Plex Media Server..."
  if pkg install -y plexmediaserver; then
    log_info "Plex Media Server installed successfully."
  else
    log_warn "Failed to install Plex Media Server."
  fi
}

configure_zfs() {
  local ZPOOL_NAME="WD_BLACK"
  local MOUNT_POINT="/mnt/${ZPOOL_NAME}"
  log_info "Configuring ZFS pool..."
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
  USERNAME="sawyer"
  local bin_dir="/home/${USERNAME}/bin"
  local scripts_src="/home/${USERNAME}/github/bash/freebsd/_scripts/"
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
  log_info "Starting cron service..."
  service cron start || log_warn "Failed to start cron."
}

configure_periodic() {
  local cron_file="/etc/periodic/daily/freebsd_maintenance"
  log_info "Configuring daily system maintenance tasks..."
  if [ -f "$cron_file" ]; then
    mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" && \
      log_info "Existing periodic script backed up." || \
      log_warn "Failed to backup existing periodic script."
  fi
  cat << 'EOF' > "$cron_file"
#!/bin/sh
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
  if chmod +x "$cron_file"; then
    log_info "Daily maintenance script created at $cron_file."
  else
    log_warn "Failed to set execute permission on $cron_file."
  fi
}

install_fastfetch() {
  log_info "Installing Fastfetch..."
  pkg install fastfetch && log_info "fastfetch installed." || log_warn "Failed to install fastfetch."
}

final_checks() {
  log_info "Performing final system checks:"
  echo "Kernel: $(uname -r)"
  echo "Uptime: $(uptime)"
  df -h /
  swapinfo -h || true
}

home_permissions() {
  USERNAME="sawyer"
  local home_dir="/home/${USERNAME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir"
  find "$home_dir" -type d -exec chmod g+s {} \;
}

set_bash_shell() {
  local target_user="sawyer"
  if [ "$(id -u)" -ne 0 ]; then
    log_warn "This function requires root privileges."
    return 1
  fi
  if [ ! -x /usr/local/bin/bash ]; then
    log_info "Bash not found. Installing via pkg..."
    pkg install -y bash || { log_warn "Failed to install Bash."; return 1; }
  fi
  if ! grep -Fxq "/usr/local/bin/bash" /etc/shells; then
    echo "/usr/local/bin/bash" >> /etc/shells
    log_info "Added /usr/local/bin/bash to /etc/shells."
  fi
  chsh -s /usr/local/bin/bash "$target_user"
  log_info "Default shell for $target_user changed to /usr/local/bin/bash."
}

prompt_reboot() {
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
  set_bash_shell
  prompt_reboot
}

main "$@"
