#!/usr/local/bin/env bash
# FreeBSD System Setup Script
# Fully configures a clean install of FreeBSD with tools, hardening and development configurations.

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

# Check for required commands
command_exists() {
  if ! command -v "$1" &>/dev/null; then
    log_error "Required command '$1' not found. Exiting."
    exit 1
  fi
}

for cmd in pkg git rsync curl tar; do
  command_exists "$cmd"
done

# Configuration Variables
USERNAME="sawyer"
TIMEZONE="America/New_York"

# Zig installation configuration (FreeBSD build)
# (Ensure the URL is for a FreeBSD x86_64 build)
ZIG_URL="https://ziglang.org/builds/zig-freebsd-x86_64-0.14.0-dev.3224+5ab511307.tar.xz"
ZIG_DIR="/opt/zig"
ZIG_BIN="/usr/local/bin/zig"

# List of packages (adjust package names as available in pkg)
PACKAGES=(
  bash vim nano screen tmux mc
  git curl wget rsync htop sudo python3 py38-pip tzdata
  gcc cmake ninja meson gettext
  openssh go gdb strace man
  xorg xinit dmenu xterm feh ttf-dejavu
  i3 i3blocks picom alacritty
)

check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_error "Script must be run as root. Exiting."
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
  log_info "Installing essential packages..."
  if ! pkg install -y "${PACKAGES[@]}"; then
    log_warn "One or more packages failed to install."
  else
    log_info "Package installation complete."
  fi
}

create_user() {
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
  log_info "Configuring SSH..."
  # Ensure sshd is enabled via rc.conf using sysrc
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
    # Harden SSH settings
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

install_zig_binary() {
  log_info "Installing Zig binary..."
  if ! pkg install -y curl tar; then
    log_warn "Failed to install curl and tar."
  fi
  rm -rf "$ZIG_DIR"
  mkdir -p "$ZIG_DIR"
  local tmp_tar="/tmp/zig.tar.xz"
  if curl -L -o "$tmp_tar" "$ZIG_URL"; then
    if tar -xf "$tmp_tar" -C "$ZIG_DIR" --strip-components=1; then
      ln -sf "$ZIG_DIR/zig" "$ZIG_BIN"
      rm -f "$tmp_tar"
      if ! "$ZIG_BIN" version &>/dev/null; then
        log_error "Zig installation failed."
      else
        log_info "Zig installed successfully."
      fi
    else
      log_warn "Failed to extract Zig tarball."
      rm -f "$tmp_tar"
    fi
  else
    log_error "Failed to download Zig."
  fi
}

configure_firewall() {
  log_info "Configuring PF firewall..."
  # Create a basic /etc/pf.conf if it doesn't exist or back it up
  local pf_conf="/etc/pf.conf"
  if [ -f "$pf_conf" ]; then
    cp "$pf_conf" "${pf_conf}.bak"
    log_info "Backed up existing pf.conf to ${pf_conf}.bak."
  fi
  cat << 'EOF' > "$pf_conf"
# Minimal PF configuration for FreeBSD
set block-policy drop
set loginterface egress
block in all
pass out all keep state
pass quick on lo
EOF
  log_info "New pf.conf written."
  # Enable PF via rc.conf
  sysrc pf_enable="YES"
  # Load the new ruleset
  pfctl -f "$pf_conf" && log_info "PF rules loaded." || log_warn "Failed to load PF rules."
  service pf start || log_warn "Failed to start PF."
}

secure_sysctl() {
  log_info "Applying sysctl kernel hardening settings..."
  local sysctl_conf="/etc/sysctl.conf"
  [ -f "$sysctl_conf" ] && cp "$sysctl_conf" "${sysctl_conf}.bak"
  cat << 'EOF' >> "$sysctl_conf"
# Harden kernel parameters for FreeBSD
net.inet.tcp.blackhole=2
security.bsd.see_other_uids=0
EOF
  # Apply new sysctl settings immediately
  sysctl -p && log_info "sysctl settings applied." || log_warn "Failed to apply sysctl settings."
}

deploy_user_scripts() {
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
  log_info "Starting cron service..."
  service cron start || log_warn "Failed to start cron."
}

final_checks() {
  log_info "Performing final system checks:"
  echo "Kernel: $(uname -r)"
  echo "Uptime: $(uptime)"
  df -h /
  swapinfo -h || true
}

home_permissions() {
  local home_dir="/usr/home/${USERNAME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir"
  find "$home_dir" -type d -exec chmod g+s {} \;
}

dotfiles_load() {
  log_info "Loading dotfiles configuration..."
  local config_dirs=( "alacritty" "i3" "i3blocks" "picom" )
  for dir in "${config_dirs[@]}"; do
    mkdir -p "/usr/home/${USERNAME}/.config/$dir"
  done
  rsync -a --delete "/usr/home/${USERNAME}/github/bash/freebsd/dotfiles/alacritty/" "/usr/home/${USERNAME}/.config/alacritty/" || log_warn "Failed to sync alacritty config."
  rsync -a --delete "/usr/home/${USERNAME}/github/bash/freebsd/dotfiles/i3/" "/usr/home/${USERNAME}/.config/i3/" || log_warn "Failed to sync i3 config."
  rsync -a --delete "/usr/home/${USERNAME}/github/bash/freebsd/dotfiles/i3blocks/" "/usr/home/${USERNAME}/.config/i3blocks/" || log_warn "Failed to sync i3blocks config."
  chmod -R +x "/usr/home/${USERNAME}/.config/i3blocks/scripts" 2>/dev/null || log_warn "Failed to set execute permissions on i3blocks scripts."
  rsync -a --delete "/usr/home/${USERNAME}/github/bash/freebsd/dotfiles/picom/" "/usr/home/${USERNAME}/.config/picom/" || log_warn "Failed to sync picom config."
}

build_ly() {
  log_info "Building and installing Ly display manager..."
  # Install dependencies (adjust package names as needed)
  if ! pkg install -y libxcb xcb-util xcb-util-keysyms xcb-util-wm xcb-util-cursor libxkbcommon libxkbcommon-x11; then
    log_warn "One or more Ly build dependencies failed to install."
  fi

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

  # Create a FreeBSD-style rc.d script for ly in /usr/local/etc/rc.d
  local ly_rc="/usr/local/etc/rc.d/ly"
  cat << 'EOF' > "$ly_rc"
#!/bin/sh
#
# PROVIDE: ly
# REQUIRE: LOGIN
# KEYWORD: shutdown
. /etc/rc.subr
name="ly"
rcvar="ly_enable"
command="/usr/local/bin/ly"
start_cmd="ly_start"
ly_start() {
    echo "Starting Ly display manager..."
    ${command} &
}
load_rc_config ${name}
run_rc_command "$1"
EOF
  chmod +x "$ly_rc" || log_warn "Failed to make $ly_rc executable."
  if sysrc ly_enable="YES" >/dev/null 2>&1; then
    log_info "Ly service enabled in rc.conf."
  else
    log_warn "Failed to enable Ly service in rc.conf."
  fi

  log_info "Ly display manager built and configured."
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
  secure_sysctl
  deploy_user_scripts
  setup_cron
  final_checks
  home_permissions
  dotfiles_load
  build_ly
  prompt_reboot
}

main "$@"