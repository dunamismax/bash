#!/usr/bin/env bash
# Alpine Linux System Setup Script
# Fully configures a clean install of Alpine with all needed
# tools and configurations for hardening and security and dev.
set -Eeuo pipefail
IFS=$'\n\t'

NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                     # Reset to No Color

LOG_FILE="/var/log/alpine_setup.log"
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

# Configuration Variables
USERNAME="sawyer"
TIMEZONE="America/New_York"

# Zig installation (adjust URL/architecture as needed)
ZIG_URL="https://ziglang.org/download/0.12.1/zig-linux-armv7a-0.12.1.tar.xz"
ZIG_DIR="/opt/zig"
ZIG_BIN="/usr/local/bin/zig"

PACKAGES=(
  bash vim nano screen tmux mc
  build-base cmake ninja meson gettext git
  openssh curl wget rsync htop sudo python3 py3-pip tzdata
  iptables ca-certificates bash-completion openrc
  go gdb strace man
  xorg-server xinit dmenu xterm feh ttf-dejavu
  i3wm i3blocks picom alacritty
)

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_error "Script must be run as root. Exiting."
    exit 1
  fi
}

check_network() {
  log_info "Checking network connectivity..."
  if ! ping -c1 -W5 google.com &>/dev/null; then
    log_warn "No network connectivity detected."
  else
    log_info "Network connectivity OK."
  fi
}

update_system() {
  log_info "Updating package repositories..."
  apk update && apk upgrade || log_warn "System update/upgrade encountered issues."
}

install_packages() {
  log_info "Installing essential packages..."
  if ! apk add --no-cache "${PACKAGES[@]}"; then
    log_warn "One or more packages failed to install."
  else
    log_info "Package installation complete."
  fi
}

create_user() {
  if ! id "$USERNAME" &>/dev/null; then
    log_info "Creating user '$USERNAME'..."
    adduser -D "$USERNAME" || log_warn "Failed to create user '$USERNAME'."
    echo "$USERNAME:changeme" | chpasswd || log_warn "Failed to set password for '$USERNAME'."
    if ! grep -q "^$USERNAME" /etc/sudoers; then
      echo "$USERNAME ALL=(ALL) ALL" >> /etc/sudoers
    fi
  else
    log_info "User '$USERNAME' already exists."
  fi
}

configure_timezone() {
  log_info "Setting timezone to $TIMEZONE..."
  if [ -f "/usr/share/zoneinfo/${TIMEZONE}" ]; then
    cp "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
    echo "$TIMEZONE" > /etc/timezone
  else
    log_warn "Timezone file for $TIMEZONE not found."
  fi
}

setup_repos() {
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
  log_info "Copying shell configuration files..."
  for file in .bashrc .profile; do
    local src="/home/${USERNAME}/github/bash/linux/dotfiles/$file"
    local dest="/home/${USERNAME}/$file"
    if [ -f "$src" ]; then
      [ -f "$dest" ] && cp "$dest" "${dest}.bak"
      cp -f "$src" "$dest" || log_warn "Failed to copy $src to $dest."
      chown "${USERNAME}:${USERNAME}" "$dest"
      log_info "Copied $src to $dest."
    else
      log_warn "Source file $src not found."
    fi
  done
}

configure_ssh() {
  log_info "Configuring SSH..."
  if ! command -v rc-service &>/dev/null; then
    apk add --no-cache openrc || log_warn "Failed to install openrc."
  fi
  rc-update add sshd default || log_warn "Failed to add sshd to default runlevel."
  rc-service sshd restart || log_warn "Failed to restart sshd."
}

secure_ssh_config() {
  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="/etc/ssh/sshd_config.bak"
  if [ -f "$sshd_config" ]; then
    cp "$sshd_config" "$backup_file"
    log_info "Backed up SSH config to $backup_file."
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$sshd_config"
    sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
    sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config"
    log_info "SSH configuration hardened."
    rc-service sshd restart || log_warn "Failed to restart sshd after hardening."
  else
    log_warn "SSHD configuration file not found."
  fi
}

install_zig_binary() {
  log_info "Installing Zig binary..."
  apk add --no-cache curl tar || log_warn "Failed to install curl and tar."
  rm -rf "$ZIG_DIR"
  mkdir -p "$ZIG_DIR"
  if curl -L -o /tmp/zig.tar.xz "$ZIG_URL"; then
    if tar -xf /tmp/zig.tar.xz -C "$ZIG_DIR" --strip-components=1; then
      ln -sf "$ZIG_DIR/zig" "$ZIG_BIN"
      rm -f /tmp/zig.tar.xz
      if ! "$ZIG_BIN" version &>/dev/null; then
        log_error "Zig installation failed."
      else
        log_info "Zig installed successfully."
      fi
    else
      log_warn "Failed to extract Zig tarball."
    fi
  else
    log_error "Failed to download Zig."
  fi
}

configure_firewall() {
  log_info "Configuring firewall (iptables)..."
  iptables -P INPUT DROP || log_warn "Could not set default INPUT policy."
  iptables -P FORWARD DROP || log_warn "Could not set default FORWARD policy."
  iptables -P OUTPUT ACCEPT || log_warn "Could not set default OUTPUT policy."
  iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || log_warn "Failed to allow established connections."
  iptables -A INPUT -i lo -j ACCEPT || log_warn "Failed to allow loopback."
  iptables -A INPUT -p icmp -j ACCEPT || log_warn "Failed to allow ICMP."
  for port in 22 80 443 32400; do
    iptables -A INPUT -p tcp --dport "$port" -j ACCEPT || log_warn "Failed to allow TCP port $port."
  done
}

persist_firewall() {
  log_info "Saving current iptables rules for persistence..."
  if command -v iptables-save &>/dev/null; then
    mkdir -p /etc/iptables
    iptables-save > /etc/iptables/rules.v4 || log_warn "Failed to save iptables rules."
    log_info "Firewall rules saved to /etc/iptables/rules.v4."
  else
    log_warn "iptables-save not found; skipping firewall persistence."
  fi
}

configure_openrc_local() {
  log_info "Configuring OpenRC local service for firewall persistence..."
  local local_script="/etc/local.d/firewall.start"
  cat << 'EOF' > "$local_script"
#!/bin/sh
# Restore saved iptables rules if they exist
if [ -f /etc/iptables/rules.v4 ]; then
  iptables-restore < /etc/iptables/rules.v4
fi
EOF
  chmod +x "$local_script" || log_warn "Failed to make $local_script executable."
  if rc-update add local default; then
    log_info "Local OpenRC service added to default runlevel."
  else
    log_warn "Failed to add local service to default runlevel."
  fi
}

configure_busybox_services() {
  log_info "Ensuring BusyBox services are enabled..."
  if ! rc-update show | grep -q '^syslog'; then
    rc-update add syslog default && log_info "Syslog service added to default runlevel." || log_warn "Failed to add syslog service."
  else
    log_info "Syslog service already enabled."
  fi
  if ! rc-update show | grep -q '^crond'; then
    rc-update add crond default && log_info "Crond service added to default runlevel." || log_warn "Failed to add crond service."
  else
    log_info "Crond service already enabled."
  fi
}

deploy_user_scripts() {
  local bin_dir="/home/${USERNAME}/bin"
  local scripts_src="/home/${USERNAME}/github/bash/linux/_scripts/"
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
  log_info "Starting crond service..."
  if command -v crond &>/dev/null; then
    rc-service crond start || log_warn "Failed to start crond."
  else
    log_warn "crond not found; skipping cron setup."
  fi
}

secure_sysctl() {
  log_info "Applying sysctl kernel hardening settings..."
  local sysctl_conf="/etc/sysctl.conf"
  [ -f "$sysctl_conf" ] && cp "$sysctl_conf" "${sysctl_conf}.bak"
  cat << 'EOF' >> "$sysctl_conf"
# Harden network parameters
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_rfc1337 = 1
EOF
  sysctl -p &>/dev/null && log_info "sysctl settings applied." || log_warn "Failed to apply sysctl settings."
}

final_checks() {
  log_info "Performing final system checks:"
  echo "Kernel: $(uname -r)"
  echo "Uptime: $(uptime -p)"
  df -h /
  free -h || true
}

home_permissions() {
  local home_dir="/home/${USERNAME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir"
  find "$home_dir" -type d -exec chmod g+s {} \;
}

dotfiles_load() {
  log_info "Loading dotfiles configuration..."
  local config_dirs=( "alacritty" "i3" "i3blocks" "picom" )
  for dir in "${config_dirs[@]}"; do
    mkdir -p "/home/${USERNAME}/.config/$dir"
  done
  rsync -a --delete "/home/${USERNAME}/github/bash/linux/dotfiles/alacritty/" "/home/${USERNAME}/.config/alacritty/" || log_warn "Failed to sync alacritty config."
  rsync -a --delete "/home/${USERNAME}/github/bash/linux/dotfiles/i3/" "/home/${USERNAME}/.config/i3/" || log_warn "Failed to sync i3 config."
  rsync -a --delete "/home/${USERNAME}/github/bash/linux/dotfiles/i3blocks/" "/home/${USERNAME}/.config/i3blocks/" || log_warn "Failed to sync i3blocks config."
  chmod -R +x "/home/${USERNAME}/.config/i3blocks/scripts" 2>/dev/null || log_warn "Failed to set execute permissions on i3blocks scripts."
  rsync -a --delete "/home/${USERNAME}/github/bash/linux/dotfiles/picom/" "/home/${USERNAME}/.config/picom/" || log_warn "Failed to sync picom config."
}

build_ly() {
  log_info "Building and installing Ly display manager..."
  apk add --no-cache linux-pam-dev libxcb-dev xcb-util-dev xcb-util-keysyms-dev \
    xcb-util-wm-dev xcb-util-cursor-dev libxkbcommon-dev libxkbcommon-x11-dev || \
    log_warn "One or more Ly build dependencies failed to install."

  local LY_DIR="/opt/ly"
  rm -rf "$LY_DIR"
  if ! git clone https://github.com/fairyglade/ly.git "$LY_DIR"; then
    log_error "Failed to clone Ly repository."
    return 1
  fi

  cd "$LY_DIR" || { log_error "Failed to change directory to $LY_DIR."; return 1; }

  log_info "Compiling Ly with Zig..."
  if ! zig build; then
    log_error "Compilation of Ly failed."
    return 1
  fi

  if cp ./ly /usr/local/bin/ly; then
    chmod +x /usr/local/bin/ly
    log_info "Ly installed to /usr/local/bin/ly."
  else
    log_warn "Failed to copy the Ly binary."
  fi

  cat << 'EOF' > /etc/init.d/ly
#!/sbin/openrc-run
description="Ly Display Manager"
command="/usr/local/bin/ly"
command_background=true
pidfile="/run/ly.pid"
depend() {
    need localmount
    before login
}
EOF
  chmod +x /etc/init.d/ly
  if rc-update add ly default; then
    log_info "Ly service added to default runlevel."
  else
    log_warn "Failed to add ly to default runlevel."
  fi

  log_info "Ly display manager has been built and configured. (Disable conflicting gettys manually if necessary.)"
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
  install_zig_binary
  configure_firewall
  persist_firewall
  secure_sysctl
  deploy_user_scripts
  setup_cron
  configure_openrc_local
  configure_busybox_services
  final_checks
  home_permissions
  dotfiles_load
  build_ly
  prompt_reboot
}

main "$@"