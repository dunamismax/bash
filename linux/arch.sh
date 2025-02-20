#!/usr/bin/env bash
# Arch Linux System Setup Script
# Fully configures a clean install of Arch Linux with custom settings,
# essential applications, hardening, development tools, and additional
# functions for Plex, ZFS, Docker, Caddy, etc.
#
# Must be run as root.
#
# Author: dunamismax (rewritten for Arch) | License: MIT

set -Eeuo pipefail
IFS=$'\n\t'
export LC_ALL=C.UTF-8
export PATH="$PATH:/sbin:/usr/sbin"

#------------------------------------------------------------
# Color definitions for logging output
#------------------------------------------------------------
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'     # Error messages
NORD13='\033[38;2;235;203;139m'    # Warning messages
NORD14='\033[38;2;163;190;140m'    # Info messages
NC='\033[0m'                      # Reset to No Color

#------------------------------------------------------------
# Logging Setup
#------------------------------------------------------------
LOG_FILE="/var/log/arch_setup.log"
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
TIMEZONE="America/New_York"

# Merged PACKAGES list for Arch (using yay)
PACKAGES=(
  # Editors and Terminal Utilities
  bash vim nano screen tmux mc

  # Development tools and build systems
  base-devel cmake ninja meson gettext git pkgconf openssl libffi

  # Networking, system utilities, and debugging tools
  nmap openssh ufw curl wget rsync htop iptables ca-certificates \
    bash-completion openbsd-netcat gdb strace iftop tcpdump lsof jq iproute2 less bind-tools ncdu

  # Compression, text processing, and miscellaneous utilities
  zip unzip gawk ethtool tree universal-ctags the_silver_searcher ltrace

  # Python development tools
  python python-pip python-virtualenv tzdata

  # Essential libraries for building software
  zlib readline bzip2 tk xz ncurses gdbm nss liblzma libxml2 xmlsec1

  # Additional compilers and tools
  clang llvm

  # Common utilities and GUI components
  xorg-server xorg-xinit xorg-xrandr i3-wm i3status i3lock i3blocks dmenu \
    xterm alacritty feh ttf-dejavu picom

  # System services and logging
  chrony rsyslog cronie sudo
)

#------------------------------------------------------------
# Function to install yay (AUR helper)
#------------------------------------------------------------
install_yay() {
  if command -v yay &>/dev/null; then
    log_info "yay is already installed."
    return 0
  fi
  log_info "Installing yay..."
  pacman -S --noconfirm --needed git base-devel || handle_error "Failed to install git and base-devel." 1
  git clone https://aur.archlinux.org/yay.git /tmp/yay || handle_error "Failed to clone yay repository." 1
  (cd /tmp/yay && makepkg -si --noconfirm) || handle_error "Failed to build and install yay." 1
  log_info "yay installed successfully."
}

#------------------------------------------------------------
# Arch Linux Functions (adapted from Debian)
#------------------------------------------------------------
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    handle_error "Script must be run as root. Exiting." 1
  fi
  log_info "Running as root."
}

check_network() {
  log_info "Checking network connectivity..."
  if ! ping -c1 -W5 google.com &>/dev/null; then
    handle_error "No network connectivity detected." 1
  fi
  log_info "Network connectivity OK."
}

check_distribution() {
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [ "${ID:-}" != "arch" ]; then
      handle_error "This script is intended for Arch Linux systems. Detected: ${NAME:-Unknown}." 1
    fi
    log_info "Distribution confirmed: ${PRETTY_NAME:-Arch Linux}."
  else
    log_warn "/etc/os-release not found. Assuming Arch Linux."
  fi
}

update_system() {
  log_info "Updating system packages..."
  pacman -Syu --noconfirm || handle_error "Failed to update system packages." 1
  log_info "System update complete."
}

ensure_user() {
  log_info "Ensuring user '$USERNAME' exists..."
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' already exists."
  else
    log_info "User '$USERNAME' does not exist. Creating..."
    useradd -m -s /bin/bash "$USERNAME" || handle_error "Failed to create user '$USERNAME'." 1
    passwd -d "$USERNAME" || log_warn "Failed to remove password for user '$USERNAME'."
    log_info "User '$USERNAME' created successfully."
  fi
}

configure_timezone() {
  if [ -n "$TIMEZONE" ]; then
    log_info "Setting system timezone to $TIMEZONE..."
    timedatectl set-timezone "$TIMEZONE" || handle_error "Failed to set timezone to $TIMEZONE." 1
    log_info "Timezone set to $TIMEZONE."
  else
    log_info "TIMEZONE variable not set; skipping timezone configuration."
  fi
}

install_packages() {
  log_info "Installing essential packages..."
  yay -S --noconfirm --needed "${PACKAGES[@]}" || handle_error "Package installation failed." 1
  log_info "Package installation complete."
}

configure_sudo() {
  log_info "Configuring sudo privileges for user '$USERNAME'..."
  if id -nG "$USERNAME" | grep -qw "wheel"; then
    log_info "User '$USERNAME' is already in the wheel group. No changes needed."
  else
    log_info "Adding user '$USERNAME' to the wheel group..."
    usermod -aG wheel "$USERNAME" || handle_error "Failed to add user '$USERNAME' to the wheel group." 1
    log_info "User '$USERNAME' added to the wheel group successfully."
  fi
}

configure_time_sync() {
  log_info "Configuring time synchronization with chrony..."
  systemctl enable chronyd || handle_error "Failed to enable chronyd service." 1
  systemctl start chronyd || handle_error "Failed to start chronyd service." 1
  log_info "Chrony configured successfully."
}

setup_repos() {
  local repo_dir="/home/${USERNAME}/github"
  log_info "Setting up Git repositories in $repo_dir..."
  if [ -d "$repo_dir" ]; then
    log_info "Repository directory $repo_dir already exists. Skipping cloning."
  else
    mkdir -p "$repo_dir" || handle_error "Failed to create repository directory $repo_dir." 1
    for repo in bash windows web python go misc; do
      local target_dir="$repo_dir/$repo"
      if [ -d "$target_dir" ]; then
        log_info "Repository $repo already cloned. Skipping."
      else
        git clone "https://github.com/dunamismax/$repo.git" "$target_dir" || handle_error "Failed to clone repository: $repo" 1
        log_info "Cloned repository: $repo"
      fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo_dir" 1
  fi
}

configure_ssh() {
  log_info "Configuring SSH service..."
  systemctl enable sshd || handle_error "Failed to enable sshd service." 1
  systemctl restart sshd || handle_error "Failed to restart sshd service." 1
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
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$sshd_config" || handle_error "Failed to set PermitRootLogin." 1
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config" || handle_error "Failed to set PasswordAuthentication." 1
  sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config" || handle_error "Failed to set ChallengeResponseAuthentication." 1
  sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config" || handle_error "Failed to set X11Forwarding." 1
  if ! grep -q "^PermitEmptyPasswords no" "$sshd_config"; then
    echo "PermitEmptyPasswords no" >> "$sshd_config" || handle_error "Failed to set PermitEmptyPasswords." 1
  fi
  systemctl restart sshd || handle_error "Failed to restart SSH after hardening." 1
  log_info "SSH configuration hardened successfully."
}

configure_nftables_firewall() {
  log_info "Configuring firewall using nftables..."
  if ! command -v nft >/dev/null 2>&1; then
    log_info "nft command not found. Installing nftables package..."
    yay -S --noconfirm nftables || handle_error "Failed to install nftables." 1
  fi
  if [ -f /etc/nftables.conf ]; then
    cp /etc/nftables.conf /etc/nftables.conf.bak || handle_error "Failed to backup existing nftables config." 1
    log_info "Existing /etc/nftables.conf backed up to /etc/nftables.conf.bak."
  fi
  nft flush ruleset || handle_error "Failed to flush current nftables ruleset." 1
  cat << 'EOF' > /etc/nftables.conf
#!/usr/sbin/nft -f
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif "lo" accept
        ip protocol icmp accept
        tcp dport { 22, 80, 443, 32400 } accept
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
  if [ $? -ne 0 ]; then
    handle_error "Failed to write /etc/nftables.conf." 1
  fi
  log_info "New nftables configuration written to /etc/nftables.conf."
  nft -f /etc/nftables.conf || handle_error "Failed to load nftables rules." 1
  log_info "nftables rules loaded successfully."
  systemctl enable nftables.service || handle_error "Failed to enable nftables service." 1
  systemctl restart nftables.service || handle_error "Failed to restart nftables service." 1
  log_info "nftables service enabled and restarted; firewall configuration persisted."
}

disable_ipv6() {
  log_info "Disabling IPv6 for enhanced security..."
  local ipv6_conf="/etc/sysctl.d/99-disable-ipv6.conf"
  cat <<EOF > "$ipv6_conf"
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF
  sysctl --system || handle_error "Failed to reload sysctl settings." 1
  log_info "IPv6 disabled via $ipv6_conf."
}

configure_fail2ban() {
  if command -v fail2ban-server >/dev/null 2>&1; then
    log_info "Fail2ban is already installed. Skipping installation."
    return 0
  fi
  log_info "Installing Fail2ban..."
  yay -S --noconfirm fail2ban || handle_error "Failed to install Fail2ban." 1
  if [ -f /etc/fail2ban/jail.local ]; then
    cp /etc/fail2ban/jail.local /etc/fail2ban/jail.local.bak || log_warn "Failed to backup existing jail.local"
    log_info "Backed up /etc/fail2ban/jail.local to /etc/fail2ban/jail.local.bak."
  fi
  cat <<EOF >/etc/fail2ban/jail.local
[sshd]
enabled  = true
port     = 22
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 5
findtime = 600
bantime  = 3600
EOF
  systemctl enable fail2ban || log_warn "Failed to enable Fail2ban service."
  systemctl start fail2ban || log_warn "Failed to start Fail2ban service."
  log_info "Fail2ban installed and configured successfully."
}

deploy_user_scripts() {
  local bin_dir="/home/${USERNAME}/bin"
  local scripts_src="/home/${USERNAME}/github/bash/linux/_scripts/"
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
  local home_dir="/home/${USERNAME}"
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
  log_info "Ownership and permissions set successfully."
}

bash_dotfiles_load() {
  log_info "Copying dotfiles (.bashrc and .profile) to user and root home directories..."
  local source_dir="/home/${USERNAME}/github/bash/linux/arch/dotfiles"
  if [ ! -d "$source_dir" ]; then
    log_warn "Dotfiles source directory $source_dir does not exist. Skipping dotfiles copy."
    return 0
  fi
  local files=( ".bashrc" ".profile" )
  local targets=( "/home/${USERNAME}" "/root" )
  for file in "${files[@]}"; do
    for target in "${targets[@]}"; do
      if [ -f "${target}/${file}" ]; then
        cp "${target}/${file}" "${target}/${file}.bak" || handle_error "Failed to backup ${target}/${file}" 1
        log_info "Backed up ${target}/${file} to ${target}/${file}.bak."
      fi
      cp -f "${source_dir}/${file}" "${target}/${file}" || handle_error "Failed to copy ${source_dir}/${file} to ${target}/${file}" 1
      log_info "Copied ${file} to ${target}."
    done
  done
  log_info "Dotfiles copy complete."
}

set_default_shell() {
  local target_shell="/bin/bash"
  if [ ! -x "$target_shell" ]; then
    log_error "Bash not found or not executable at $target_shell. Cannot set default shell."
    return 1
  fi
  log_info "Setting default shell to $target_shell for user '$USERNAME' and root."
  if chsh -s "$target_shell" "$USERNAME"; then
    log_info "Set default shell for user '$USERNAME' to $target_shell."
  else
    log_error "Failed to set shell for user '$USERNAME'."
    return 1
  fi
  if chsh -s "$target_shell" root; then
    log_info "Set default shell for root to $target_shell."
  else
    log_error "Failed to set shell for root."
    return 1
  fi
  log_info "Default shell configuration complete."
}

install_and_configure_nala() {
  log_info "Nala is an APT-specific tool and is not applicable on Arch Linux. Skipping."
}

install_fastfetch() {
  if command -v fastfetch &>/dev/null; then
    log_info "fastfetch is already installed."
    return 0
  fi
  log_info "Installing fastfetch..."
  yay -S --noconfirm fastfetch || handle_error "Failed to install fastfetch." 1
  log_info "fastfetch installed successfully."
}

configure_unattended_upgrades() {
  log_info "Unattended-upgrades is not applicable on Arch Linux. Skipping."
}

apt_cleanup() {
  log_info "Cleaning up unnecessary packages and cache..."
  pacman -Rns $(pacman -Qtdq 2>/dev/null) --noconfirm || log_warn "No orphan packages to remove."
  yay -Sc --noconfirm || log_warn "Yay cache cleanup failed."
  log_info "Cleanup complete."
}

prompt_reboot() {
  read -rp "System setup is complete. Would you like to reboot now? (y/n): " answer
  case "$answer" in
    [Yy]* )
      log_info "Rebooting system as per user request."
      reboot
      ;;
    * )
      log_info "Reboot skipped. Please reboot manually to finalize changes."
      ;;
  esac
}

install_plex() {
  if command -v plexmediaserver &>/dev/null; then
    log_info "Plex Media Server is already installed."
    return 0
  fi
  log_info "Installing Plex Media Server..."
  yay -S --noconfirm plex-media-server || handle_error "Failed to install Plex Media Server." 1
  local PLEX_CONF="/etc/default/plexmediaserver"
  if [ -f "$PLEX_CONF" ]; then
    log_info "Configuring Plex to run as ${USERNAME}..."
    sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" || log_warn "Failed to set Plex user in $PLEX_CONF"
  else
    log_warn "$PLEX_CONF not found; skipping user configuration."
  fi
  systemctl enable plexmediaserver || log_warn "Failed to enable Plex Media Server service."
  log_info "Plex Media Server installed successfully."
}

caddy_config() {
  log_info "Releasing occupied network ports..."
  local tcp_ports=( "8080" "80" "443" "32400" "8324" "32469" )
  local udp_ports=( "80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415" )
  for port in "${tcp_ports[@]}"; do
    local pids
    pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
      log_info "Killing processes on TCP port $port: $pids"
      kill -9 $pids || log_warn "Failed to kill processes on TCP port $port"
    fi
  done
  for port in "${udp_ports[@]}"; do
    local pids
    pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
      log_info "Killing processes on UDP port $port: $pids"
      kill -9 $pids || log_warn "Failed to kill processes on UDP port $port"
    fi
  done
  log_info "Port release process completed."
  log_info "Installing Caddy..."
  yay -S --noconfirm caddy || handle_error "Failed to install Caddy." 1
  local CUSTOM_CADDYFILE="/home/${USERNAME}/github/linux/dotfiles/Caddyfile"
  local DEST_CADDYFILE="/etc/caddy/Caddyfile"
  if [ -f "$CUSTOM_CADDYFILE" ]; then
    log_info "Copying custom Caddyfile from $CUSTOM_CADDYFILE to $DEST_CADDYFILE..."
    cp -f "$CUSTOM_CADDYFILE" "$DEST_CADDYFILE" || log_warn "Failed to copy custom Caddyfile."
  else
    log_warn "Custom Caddyfile not found at $CUSTOM_CADDYFILE"
  fi
  systemctl enable caddy || log_warn "Failed to enable Caddy service."
  systemctl restart caddy || log_warn "Failed to restart Caddy service."
  log_info "Caddy configuration completed successfully."
}

install_configure_zfs() {
  local ZPOOL_NAME="WD_BLACK"
  local MOUNT_POINT="/media/${ZPOOL_NAME}"
  log_info "Installing prerequisites for ZFS..."
  yay -S --noconfirm linux-headers || handle_error "Failed to install linux-headers." 1
  log_info "Installing ZFS packages..."
  yay -S --noconfirm zfs-dkms zfs-utils || handle_error "Failed to install ZFS packages." 1
  log_info "ZFS packages installed successfully."
  systemctl enable zfs-import-cache.service || log_warn "Could not enable zfs-import-cache.service."
  systemctl enable zfs-mount.service || log_warn "Could not enable zfs-mount.service."
  if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
    log_info "Importing ZFS pool '$ZPOOL_NAME'..."
    zpool import -f "$ZPOOL_NAME" || { log_error "Failed to import ZFS pool '$ZPOOL_NAME'."; return 1; }
  else
    log_info "ZFS pool '$ZPOOL_NAME' is already imported."
  fi
  log_info "Setting mountpoint for ZFS pool '$ZPOOL_NAME' to '$MOUNT_POINT'..."
  if ! zfs set mountpoint="${MOUNT_POINT}" "$ZPOOL_NAME"; then
    log_warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
  else
    log_info "Mountpoint for pool '$ZPOOL_NAME' successfully set to '$MOUNT_POINT'."
  fi
  log_info "ZFS installation and configuration finished successfully."
}

docker_config() {
  log_info "Starting Docker installation and configuration..."
  if command -v docker &>/dev/null; then
    log_info "Docker is already installed."
  else
    log_info "Docker not found; installing Docker..."
    yay -S --noconfirm docker || handle_error "Failed to install Docker." 1
    log_info "Docker installed successfully."
  fi
  if ! id -nG "$USERNAME" | grep -qw "docker"; then
    log_info "Adding user '$USERNAME' to the docker group..."
    usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to the docker group."
  else
    log_info "User '$USERNAME' is already in the docker group."
  fi
  mkdir -p /etc/docker || handle_error "Failed to create /etc/docker directory."
  cat <<EOF >/etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
  log_info "Docker daemon configuration updated."
  systemctl enable docker || log_warn "Could not enable Docker service."
  systemctl restart docker || handle_error "Failed to restart Docker." 1
  log_info "Docker service is enabled and running."
  if ! command -v docker-compose &>/dev/null; then
    log_info "Docker Compose not found; installing Docker Compose..."
    yay -S --noconfirm docker-compose || handle_error "Failed to install Docker Compose." 1
    log_info "Docker Compose installed successfully."
  else
    log_info "Docker Compose is already installed."
  fi
}

install_zig_binary() {
  if command -v zig &>/dev/null; then
    log_info "Zig is already installed."
    return 0
  fi
  log_info "Installing Zig via yay..."
  yay -S --noconfirm zig || handle_error "Failed to install Zig." 1
  log_info "Zig installed successfully. Version: $(zig version)"
}

enable_dunamismax_services() {
  log_info "Enabling DunamisMax website services..."
  cat <<EOF >/etc/systemd/system/dunamismax-ai-agents.service
[Unit]
Description=DunamisMax AI Agents Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/ai_agents
Environment="PATH=/home/${USERNAME}/github/web/ai_agents/.venv/bin"
EnvironmentFile=/home/${USERNAME}/github/web/ai_agents/.env
ExecStart=/home/${USERNAME}/github/web/ai_agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  cat <<EOF >/etc/systemd/system/dunamismax-files.service
[Unit]
Description=DunamisMax File Converter Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/converter_service
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/${USERNAME}/github/web/converter_service/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8300
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  cat <<EOF >/etc/systemd/system/dunamismax-messenger.service
[Unit]
Description=DunamisMax Messenger
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/messenger
Environment="PATH=/home/${USERNAME}/github/web/messenger/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/messenger/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  cat <<EOF >/etc/systemd/system/dunamismax-notes.service
[Unit]
Description=DunamisMax Notes Page
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/notes
Environment="PATH=/home/${USERNAME}/github/web/notes/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/notes/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8500
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  cat <<EOF >/etc/systemd/system/dunamismax.service
[Unit]
Description=DunamisMax Main Website
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/dunamismax
Environment="PATH=/home/${USERNAME}/github/web/dunamismax/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/dunamismax/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable dunamismax-ai-agents.service
  systemctl enable dunamismax-files.service
  systemctl enable dunamismax-messenger.service
  systemctl enable dunamismax-notes.service
  systemctl enable dunamismax.service
  log_info "DunamisMax services enabled."
}

install_ly() {
  log_info "Installing Ly Display Manager..."
  yay -S --noconfirm git zig base-devel libpam libxcb xorg-server || handle_error "Failed to install Ly build dependencies." 1
  local LY_DIR="/opt/ly"
  if [ ! -d "$LY_DIR" ]; then
    log_info "Cloning Ly repository into $LY_DIR..."
    git clone https://github.com/fairyglade/ly "$LY_DIR" || handle_error "Failed to clone the Ly repository." 1
  else
    log_info "Ly repository already exists in $LY_DIR. Updating..."
    (cd "$LY_DIR" && git pull) || handle_error "Failed to update the Ly repository." 1
  fi
  (cd "$LY_DIR" && zig build) || handle_error "Compilation of Ly failed." 1
  (cd "$LY_DIR" && zig build installsystemd) || handle_error "Installation of Ly systemd service failed." 1
  local dm_list=(gdm sddm lightdm lxdm)
  for dm in "${dm_list[@]}"; do
    if systemctl is-enabled "${dm}.service" &>/dev/null; then
      log_info "Disabling ${dm}.service..."
      systemctl disable --now "${dm}.service" || handle_error "Failed to disable ${dm}.service." 1
    fi
  done
  if [ -L /etc/systemd/system/display-manager.service ]; then
    log_info "Removing leftover /etc/systemd/system/display-manager.service symlink..."
    rm /etc/systemd/system/display-manager.service || log_warn "Failed to remove display-manager.service symlink."
  fi
  systemctl enable ly.service || handle_error "Failed to enable ly.service." 1
  systemctl disable getty@tty2.service || handle_error "Failed to disable getty@tty2.service." 1
  log_info "Ly has been installed and configured as the default login manager."
  log_info "Ly will take effect on next reboot, or start it now with: systemctl start ly.service"
}

dotfiles_load() {
  log_info "Copying dotfiles configuration..."
  local source_dir="/home/${USERNAME}/bash/linux/arch/dotfiles"
  if [ ! -d "$source_dir" ]; then
    log_warn "Dotfiles source directory $source_dir does not exist. Skipping dotfiles copy."
    return 0
  fi
  log_info "Copying Alacritty configuration to ~/.config/alacritty..."
  mkdir -p "/home/${USERNAME}/.config/alacritty"
  rsync -a --delete "${source_dir}/alacritty/" "/home/${USERNAME}/.config/alacritty/" || handle_error "Failed to copy Alacritty configuration." 1
  log_info "Copying i3 configuration to ~/.config/i3..."
  mkdir -p "/home/${USERNAME}/.config/i3"
  rsync -a --delete "${source_dir}/i3/" "/home/${USERNAME}/.config/i3/" || handle_error "Failed to copy i3 configuration." 1
  log_info "Copying i3blocks configuration to ~/.config/i3blocks..."
  mkdir -p "/home/${USERNAME}/.config/i3blocks"
  rsync -a --delete "${source_dir}/i3blocks/" "/home/${USERNAME}/.config/i3blocks/" || handle_error "Failed to copy i3blocks configuration." 1
  log_info "Setting execute permissions for i3blocks scripts..."
  chmod -R +x "/home/${USERNAME}/.config/i3blocks/scripts" || log_warn "Failed to set execute permissions on i3blocks scripts."
  log_info "Copying picom configuration to ~/.config/picom..."
  mkdir -p "/home/${USERNAME}/.config/picom"
  rsync -a --delete "${source_dir}/picom/" "/home/${USERNAME}/.config/picom/" || handle_error "Failed to copy picom configuration." 1
  log_info "Dotfiles loaded successfully."
}

#------------------------------------------------------------
# Main Function: Execute Setup Steps in Order
#------------------------------------------------------------
main() {
  check_root
  install_yay
  check_network
  check_distribution
  update_system
  ensure_user
  configure_timezone
  install_packages
  configure_sudo
  configure_time_sync
  setup_repos
  configure_ssh
  secure_ssh_config
  configure_nftables_firewall
  disable_ipv6
  configure_fail2ban
  deploy_user_scripts
  home_permissions
  bash_dotfiles_load
  dotfiles_load
  set_default_shell
  install_and_configure_nala
  install_fastfetch
  install_plex
  install_configure_zfs
  caddy_config
  docker_config
  install_zig_binary
  enable_dunamismax_services
  install_ly
  prompt_reboot
  apt_cleanup
  log_info "Arch Linux system setup completed successfully."
}

main "$@"