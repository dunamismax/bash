#!/usr/bin/env bash
# FreeBSD System Setup Script
# Fully configures a clean FreeBSD install with custom settings,
# essential applications, system hardening, and development tools.
#
# Must be run as root.
#
# Adapted from an AlmaLinux script | License: MIT

set -Eeuo pipefail

#------------------------------------------------------------
# Color definitions for logging output
#------------------------------------------------------------
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
RED='\033[0;31m'                 # Red (for reminders)
NC='\033[0m'                     # Reset

#------------------------------------------------------------
# Logging Setup
#------------------------------------------------------------
LOG_FILE="/var/log/freebsd_setup.log"
mkdir -p "$(dirname "$LOG_FILE")" || { echo "Cannot create log directory"; exit 1; }
touch "$LOG_FILE" || { echo "Cannot create log file"; exit 1; }
chmod 600 "$LOG_FILE" || { echo "Cannot set log file permissions"; exit 1; }

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

#------------------------------------------------------------
# Error Handling & Cleanup
#------------------------------------------------------------
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

#------------------------------------------------------------
# Global Configuration Variables
#------------------------------------------------------------
USERNAME="sawyer"
# On FreeBSD, user home directories are typically in /usr/home.
USER_HOME="/usr/home/${USERNAME}"
GITHUB_BASE="https://github.com/dunamismax"
# List of packages to install using pkg.
# (Some Linux-specific packages have been removed or replaced.)
PACKAGES=(
  bash vim nano screen tmux mc rsync curl wget htop tree unzip zip
  gmake cmake ninja-build meson gettext git pkgconf openssl libffi
  nmap fail2ban
  python3 python3-pip python3-virtualenv
  less bind-tools ncdu gawk tcpdump lsof jq
  tzdata zlib readline bzip2 tk xz ncurses gdbm libxml2
  clang llvm
)

#------------------------------------------------------------
# Essential Functions
#------------------------------------------------------------

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    handle_error "Script must be run as root. Exiting." 1
  fi
  log_info "Running as root."
}

update_system() {
  log_info "Updating package repository and upgrading system packages..."
  pkg update -f || handle_error "Failed to update package repository." 1
  pkg upgrade -y || handle_error "System upgrade failed." 1
  log_info "System update complete."
}

install_packages() {
  log_info "Installing essential packages..."
  pkg install -y "${PACKAGES[@]}" || handle_error "Package installation failed." 1
  log_info "Package installation complete."
}

setup_repos() {
  local repo_dir="${USER_HOME}/github"
  log_info "Setting up Git repositories in $repo_dir..."
  if [ -d "$repo_dir" ]; then
    log_info "Repository directory exists. Skipping cloning."
  else
    mkdir -p "$repo_dir" || handle_error "Failed to create directory $repo_dir." 1
    for repo in bash windows web python go misc; do
      local target_dir="$repo_dir/$repo"
      if [ -d "$target_dir" ]; then
        log_info "Repository '$repo' already cloned. Skipping."
      else
        git clone "${GITHUB_BASE}/${repo}.git" "$target_dir" || handle_error "Failed to clone '$repo'." 1
        log_info "Cloned repository: $repo"
      fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo_dir." 1
  fi
}

configure_ssh() {
  log_info "Configuring SSH service..."
  # Enable sshd in /etc/rc.conf if not already enabled
  if ! grep -q '^sshd_enable="YES"' /etc/rc.conf; then
    echo 'sshd_enable="YES"' >> /etc/rc.conf || handle_error "Failed to enable sshd in /etc/rc.conf." 1
    log_info "Added sshd_enable to /etc/rc.conf."
  fi
  # Restart or start sshd
  if ! service sshd restart 2>/dev/null; then
    service sshd start || handle_error "Failed to start sshd service." 1
  fi
  log_info "SSH service configured successfully."
}

secure_ssh_config() {
  log_info "Hardening SSH configuration..."
  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="/etc/ssh/sshd_config.bak"
  if [ ! -f "$sshd_config" ]; then
    handle_error "SSHD configuration file not found at $sshd_config." 1
  fi
  if grep -q "^PermitRootLogin no" "$sshd_config"; then
    log_info "SSH configuration already hardened. Skipping."
    return 0
  fi
  cp "$sshd_config" "$backup_file" || handle_error "Failed to backup SSH config." 1
  log_info "Backed up SSH config to $backup_file."
  # Use FreeBSD-compatible sed (with an empty backup suffix)
  sed -i '' 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$sshd_config" || handle_error "Failed to set PermitRootLogin." 1
  sed -i '' 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config" || handle_error "Failed to set PasswordAuthentication." 1
  sed -i '' 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config" || handle_error "Failed to set ChallengeResponseAuthentication." 1
  sed -i '' 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config" || handle_error "Failed to set X11Forwarding." 1
  if ! grep -q "^PermitEmptyPasswords no" "$sshd_config"; then
    echo "PermitEmptyPasswords no" >> "$sshd_config" || handle_error "Failed to set PermitEmptyPasswords." 1
  fi
  service sshd restart || handle_error "Failed to restart SSH after hardening." 1
  log_info "SSH configuration hardened successfully."
}

configure_firewall() {
  log_info "Configuring firewall using pf..."
  # Enable pf in /etc/rc.conf if not already enabled
  if ! grep -q '^pf_enable="YES"' /etc/rc.conf; then
    echo 'pf_enable="YES"' >> /etc/rc.conf || handle_error "Failed to enable pf in /etc/rc.conf." 1
    log_info "Added pf_enable to /etc/rc.conf."
  fi
  # Backup existing pf configuration
  local pf_conf="/etc/pf.conf"
  local pf_backup="/etc/pf.conf.bak"
  if [ -f "$pf_conf" ]; then
    cp "$pf_conf" "$pf_backup" || handle_error "Failed to backup $pf_conf." 1
    log_info "Backed up pf configuration to $pf_backup."
  fi
  # Append rules to allow common ports if not already present.
  if ! grep -q "pass in quick proto tcp from any to any port" "$pf_conf"; then
    echo "pass in quick proto tcp from any to any port {22,80,443,32400}" >> "$pf_conf" || handle_error "Failed to add firewall rules." 1
    log_info "Added firewall rules to $pf_conf."
  else
    log_info "Firewall rules already exist. Skipping rule addition."
  fi
  # Reload pf configuration
  pfctl -f "$pf_conf" || handle_error "Failed to reload pf configuration." 1
  # Restart pf service
  if ! service pf restart 2>/dev/null; then
    service pf start || handle_error "Failed to start pf service." 1
  fi
  log_info "pf firewall configured successfully."
}

configure_fail2ban() {
  if command -v fail2ban-client &>/dev/null; then
    log_info "Fail2ban is already installed. Skipping."
    return 0
  fi
  log_info "Installing Fail2ban..."
  pkg install -y fail2ban || handle_error "Failed to install Fail2ban." 1
  # On FreeBSD, Fail2ban configuration typically resides in /usr/local/etc/fail2ban.
  local jail_conf="/usr/local/etc/fail2ban/jail.local"
  if [ -f "$jail_conf" ]; then
    cp "$jail_conf" "${jail_conf}.bak" || log_warn "Failed to backup existing jail.local."
    log_info "Backed up existing Fail2ban jail.local."
  fi
  cat <<EOF > "$jail_conf"
[sshd]
enabled  = true
port     = 22
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 5
findtime = 600
bantime  = 3600
EOF
  # Enable fail2ban in rc.conf if not already set.
  if ! grep -q '^fail2ban_enable="YES"' /etc/rc.conf; then
    echo 'fail2ban_enable="YES"' >> /etc/rc.conf || log_warn "Failed to add fail2ban_enable to /etc/rc.conf."
    log_info "Enabled Fail2ban in /etc/rc.conf."
  fi
  service fail2ban start || log_warn "Failed to start Fail2ban service."
  log_info "Fail2ban installed and configured."
}

deploy_user_scripts() {
  local bin_dir="${USER_HOME}/bin"
  # Adjust the source path for FreeBSD scripts (if available)
  local scripts_src="${USER_HOME}/github/bash/freebsd/_scripts/"
  log_info "Deploying user scripts from $scripts_src to $bin_dir..."
  mkdir -p "$bin_dir" || handle_error "Failed to create directory $bin_dir." 1
  if rsync -ah --delete "$scripts_src" "$bin_dir"; then
    find "$bin_dir" -type f -exec chmod 755 {} \; || handle_error "Failed to set execute permissions in $bin_dir." 1
    log_info "User scripts deployed successfully."
  else
    handle_error "Failed to deploy user scripts from $scripts_src to $bin_dir." 1
  fi
}

home_permissions() {
  local home_dir="${USER_HOME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir" || handle_error "Failed to set ownership for $home_dir." 1
  chmod 700 "$home_dir" || handle_error "Failed to set permissions for $home_dir." 1
  find "$home_dir" -mindepth 1 -type d -exec chmod g+s {} \; || handle_error "Failed to set group sticky bit on directories in $home_dir." 1
  local nano_hist="${home_dir}/.nano_history"
  touch "$nano_hist" || log_warn "Failed to create $nano_hist."
  chown "${USERNAME}:$(id -gn "$home_dir")" "$nano_hist" || log_warn "Failed to set ownership for $nano_hist."
  chmod 600 "$nano_hist" || log_warn "Failed to set permissions for $nano_hist."
  local nano_data_dir="${home_dir}/.local/share/nano"
  mkdir -p "$nano_data_dir" || log_warn "Failed to create directory $nano_data_dir."
  chown "${USERNAME}:$(id -gn "$home_dir")" "$nano_data_dir" || log_warn "Failed to set ownership for $nano_data_dir."
  chmod 700 "$nano_data_dir" || log_warn "Failed to set permissions for $nano_data_dir."
  log_info "Home directory permissions set successfully."
}

bash_dotfiles_load() {
  log_info "Copying dotfiles (.bashrc and .profile) to user and root home directories..."
  # Adjust the source directory for FreeBSD dotfiles (if available)
  local source_dir="${USER_HOME}/github/bash/freebsd/dotfiles"
  if [ ! -d "$source_dir" ]; then
    log_warn "Dotfiles source directory $source_dir does not exist. Skipping."
    return 0
  fi
  local files=( ".bashrc" ".profile" )
  local targets=( "$USER_HOME" "/root" )
  for file in "${files[@]}"; do
    for target in "${targets[@]}"; do
      if [ -f "${target}/${file}" ]; then
        cp "${target}/${file}" "${target}/${file}.bak" || handle_error "Failed to backup ${target}/${file}." 1
        log_info "Backed up ${target}/${file} to ${target}/${file}.bak."
      fi
      cp -f "${source_dir}/${file}" "${target}/${file}" || handle_error "Failed to copy ${source_dir}/${file} to ${target}/${file}." 1
      log_info "Copied ${file} to ${target}."
    done
  done
  log_info "Dotfiles copy complete."
}

set_default_shell() {
  local target_shell="/usr/local/bin/bash"
  if [ ! -x "$target_shell" ]; then
    log_error "Bash not found or not executable at $target_shell. Cannot set default shell."
    return 1
  fi
  log_info "Setting default shell to $target_shell for user '$USERNAME' and root."
  if chsh -s "$target_shell" "$USERNAME"; then
    log_info "Default shell for user '$USERNAME' set to $target_shell."
  else
    log_error "Failed to set default shell for user '$USERNAME'."
    return 1
  fi
  if chsh -s "$target_shell" root; then
    log_info "Default shell for root set to $target_shell."
  else
    log_error "Failed to set default shell for root."
    return 1
  fi
  log_info "Default shell configuration complete."
}

cleanup_packages() {
  log_info "Cleaning up unused packages and cache..."
  pkg autoremove -y || log_warn "No orphan packages to remove or autoremove failed."
  pkg clean -a -y || log_warn "pkg cache cleanup failed."
  log_info "Cleanup complete."
}

prompt_reboot() {
  read -rp "System setup is complete. Reboot now? (y/n): " answer
  case "$answer" in
    [Yy]* )
      log_info "Rebooting system as requested."
      reboot
      ;;
    * )
      log_info "Reboot skipped. Please reboot manually later."
      ;;
  esac
}

#------------------------------------------------------------
# Main Function: Execute Setup Steps in Order
#------------------------------------------------------------
main() {
  log_info "Starting FreeBSD system setup."
  check_root
  update_system
  install_packages
  setup_repos
  configure_ssh
  secure_ssh_config
  configure_firewall
  configure_fail2ban
  deploy_user_scripts
  home_permissions
  bash_dotfiles_load
  set_default_shell
  cleanup_packages
  echo -e "${RED}Reminder: ${USERNAME}, please install any additional software (e.g., Plex, Caddy, ZFS) as needed.${NC}"
  prompt_reboot
  log_info "FreeBSD system setup completed successfully."
}

main "$@"