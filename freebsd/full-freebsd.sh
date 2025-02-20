#!/usr/local/bin/env bash
# FreeBSD System Setup Script
# Fully configures a clean install of FreeBSD with tools, hardening and development configurations.
# Additional functions from the Ubuntu setup script have been added where applicable.
#
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

install_zig_binary() {
  print_section "Zig Installation"
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
  print_section "PF Firewall Configuration"
  log_info "Configuring PF firewall..."
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
  sysrc pf_enable="YES"
  if pfctl -f "$pf_conf"; then
    log_info "PF rules loaded."
  else
    log_warn "Failed to load PF rules."
  fi
  service pf start || log_warn "Failed to start PF."
}

secure_sysctl() {
  print_section "Kernel Hardening via sysctl"
  log_info "Applying sysctl kernel hardening settings..."
  local sysctl_conf="/etc/sysctl.conf"
  [ -f "$sysctl_conf" ] && cp "$sysctl_conf" "${sysctl_conf}.bak"
  cat << 'EOF' >> "$sysctl_conf"
# Harden kernel parameters for FreeBSD
net.inet.tcp.blackhole=2
security.bsd.see_other_uids=0
EOF
  if sysctl -p; then
    log_info "sysctl settings applied."
  else
    log_warn "Failed to apply sysctl settings."
  fi
}

# On FreeBSD, ZFS is integrated. This function checks for a pool named "WD_BLACK" and sets its mountpoint.
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

dotfiles_load() {
  print_section "Loading Dotfiles"
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
  log_info "Dotfiles loaded successfully."
}

build_ly() {
  print_section "Ly Display Manager Installation"
  log_info "Building and installing Ly display manager..."
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

# Create rc.d scripts for DunamisMax services (adapted from the Ubuntu systemd units)
enable_dunamismax_services() {
  print_section "DunamisMax Services Setup"
  log_info "Setting up DunamisMax services..."
  # Define arrays with service details.
  local service_names=("dunamismax_ai_agents" "dunamismax_files" "dunamismax_messenger" "dunamismax_notes" "dunamismax")
  local ports=(8200 8300 8100 8500 8000)
  local directories=(
    "/usr/home/${USERNAME}/github/web/ai_agents"
    "/usr/home/${USERNAME}/github/web/converter_service"
    "/usr/home/${USERNAME}/github/web/messenger"
    "/usr/home/${USERNAME}/github/web/notes"
    "/usr/home/${USERNAME}/github/web/dunamismax"
  )
  local commands=(
    ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200"
    ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8300"
    ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100"
    ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8500"
    ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
  )
  for i in "${!service_names[@]}"; do
    local svc="${service_names[i]}"
    local workdir="${directories[i]}"
    local cmd="${commands[i]}"
    local rc_file="/usr/local/etc/rc.d/${svc}"
    log_info "Creating rc.d script for ${svc}..."
    cat <<EOF > "$rc_file"
#!/bin/sh
#
# PROVIDE: ${svc}
# REQUIRE: NETWORKING
# KEYWORD: shutdown
. /etc/rc.subr
name="${svc}"
rcvar=${svc}_enable
command="/bin/sh"
command_args="-c 'cd ${workdir} && su - ${USERNAME} -c \"${cmd}\"'"
start_cmd="${svc}_start"
${svc}_start() {
    echo "Starting ${svc}..."
    cd ${workdir} && su - ${USERNAME} -c "${cmd}" &
}
stop_cmd="${svc}_stop"
${svc}_stop() {
    echo "Stopping ${svc}..."
    pkill -f '${cmd}'
}
load_rc_config \$name
: \${${svc}_enable:=no}
EOF
    chmod +x "$rc_file"
    sysrc ${svc}_enable="YES"
    log_info "Enabled ${svc} service."
  done
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
  install_zig_binary
  configure_firewall
  secure_sysctl
  configure_zfs
  deploy_user_scripts
  setup_cron
  configure_periodic
  final_checks
  home_permissions
  dotfiles_load
  enable_dunamismax_services
  install_fastfetch
  build_ly
  prompt_reboot
}

main "$@"
