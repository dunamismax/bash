#!/usr/bin/env bash
# Arch Linux System Setup Script
# Fully configures a clean Arch Linux install with custom settings,
# essential applications, system hardening, development tools, and
# additional functions for Plex, ZFS, Docker, Caddy, etc.
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
NC='\033[0m'                      # Reset

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

# Merged list of packages to install (using yay)
PACKAGES=(
  # Essential Shell, Editors, and Terminal Utilities
  bash vim nano screen tmux mc

  # Development Tools and Build Systems
  base-devel cmake ninja meson gettext git pkgconf openssl libffi

  # Networking, System Utilities, and Debugging Tools
  nmap openssh ufw curl wget rsync htop iptables ca-certificates \
    bash-completion openbsd-netcat gdb strace iftop tcpdump lsof jq \
    iproute2 less bind-tools ncdu

  # Compression, File Archiving, and Text Processing Utilities
  zip unzip p7zip gawk ethtool tree universal-ctags the_silver_searcher ltrace

  # Python Development Tools
  python python-pip python-virtualenv tzdata

  # Essential Libraries for Building Software
  zlib readline bzip2 tk xz ncurses gdbm nss liblzma libxml2 xmlsec1

  # Additional Compilers and Toolchains
  clang llvm
)

#------------------------------------------------------------
# Distribution & User Checks
#------------------------------------------------------------
check_distribution() {
  if [ -f /etc/arch-release ]; then
    log_info "Arch Linux distribution confirmed."
  else
    log_warn "This script is intended for Arch Linux. Proceed with caution."
  fi
}

ensure_user() {
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' exists."
  else
    log_info "User '$USERNAME' not found. Creating..."
    useradd -m -s /bin/bash "$USERNAME" || handle_error "Failed to create user '$USERNAME'." 1
    log_info "User '$USERNAME' created successfully."
  fi
}

#------------------------------------------------------------
# Function to install yay (AUR helper)
#------------------------------------------------------------
install_yay() {
  if command -v yay &>/dev/null; then
    log_info "yay is already installed."
    return 0
  fi
  log_info "Installing yay..."
  pacman -S --noconfirm --needed git base-devel || handle_error "Failed to install prerequisites." 1
  git clone https://aur.archlinux.org/yay.git /tmp/yay || handle_error "Failed to clone yay repository." 1
  (cd /tmp/yay && makepkg -si --noconfirm) || handle_error "Failed to build and install yay." 1
  log_info "yay installed successfully."
}

#------------------------------------------------------------
# Arch Linux Functions
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

update_system() {
  log_info "Updating system packages..."
  pacman -Syu --noconfirm || handle_error "System update failed." 1
  log_info "System update complete."
}

install_packages() {
  log_info "Installing essential packages..."
  pacman -S --noconfirm --needed "${PACKAGES[@]}" || handle_error "Package installation failed." 1
  log_info "Package installation complete."
}

setup_repos() {
  local repo_dir="/home/${USERNAME}/github"
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
        git clone "https://github.com/dunamismax/$repo.git" "$target_dir" || handle_error "Failed to clone '$repo'." 1
        log_info "Cloned repository: $repo"
      fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo_dir." 1
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
  log_info "Configuring nftables firewall..."
  if ! command -v nft &>/dev/null; then
    log_info "nft command not found. Installing nftables via yay..."
    pacman -S --noconfirm nftables || handle_error "Failed to install nftables." 1
  fi
  if [ -f /etc/nftables.conf ]; then
    cp /etc/nftables.conf /etc/nftables.conf.bak || handle_error "Failed to backup existing nftables config." 1
    log_info "Backed up /etc/nftables.conf to /etc/nftables.conf.bak."
  fi
  nft flush ruleset || handle_error "Failed to flush nftables ruleset." 1
  cat << 'EOF' > /etc/nftables.conf
#!/usr/bin/nft -f
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
  log_info "New nftables configuration written."
  nft -f /etc/nftables.conf || handle_error "Failed to load nftables rules." 1
  log_info "nftables rules loaded successfully."
  systemctl enable nftables.service || handle_error "Failed to enable nftables service." 1
  systemctl restart nftables.service || handle_error "Failed to restart nftables service." 1
  log_info "nftables service enabled and restarted."
}

configure_fail2ban() {
  if command -v fail2ban-server &>/dev/null; then
    log_info "Fail2ban is already installed. Skipping."
    return 0
  fi
  log_info "Installing Fail2ban..."
  yay -S --noconfirm fail2ban || handle_error "Failed to install Fail2ban." 1
  if [ -f /etc/fail2ban/jail.local ]; then
    cp /etc/fail2ban/jail.local /etc/fail2ban/jail.local.bak || log_warn "Failed to backup existing jail.local."
    log_info "Backed up /etc/fail2ban/jail.local."
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
  log_info "Fail2ban installed and configured."
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
  log_info "Home directory permissions set successfully."
}

bash_dotfiles_load() {
  log_info "Copying dotfiles (.bashrc and .profile) to user and root home directories..."
  local source_dir="/home/${USERNAME}/github/bash/linux/arch/dotfiles"
  if [ ! -d "$source_dir" ]; then
    log_warn "Dotfiles source directory $source_dir does not exist. Skipping."
    return 0
  fi
  local files=( ".bashrc" ".profile" )
  local targets=( "/home/${USERNAME}" "/root" )
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
  local target_shell="/bin/bash"
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

install_fastfetch() {
  if command -v fastfetch &>/dev/null; then
    log_info "fastfetch is already installed."
    return 0
  fi
  log_info "Installing fastfetch..."
  pacman -S --noconfirm fastfetch || handle_error "Failed to install fastfetch." 1
  log_info "fastfetch installed successfully."
}

install_plex() {
  if command -v plexmediaserver &>/dev/null; then
    log_info "Plex Media Server is already installed."
    return 0
  fi
  log_info "Installing Plex Media Server..."
  yay -S --noconfirm plex-media-server || handle_error "Failed to install Plex Media Server." 1
  local plex_conf="/etc/default/plexmediaserver"
  if [ -f "$plex_conf" ]; then
    log_info "Configuring Plex to run as ${USERNAME}..."
    sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$plex_conf" || log_warn "Failed to set Plex user in $plex_conf."
  else
    log_warn "$plex_conf not found; skipping Plex user configuration."
  fi
  systemctl enable plexmediaserver || log_warn "Failed to enable Plex service."
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
  pacman -S --noconfirm caddy || handle_error "Failed to install Caddy." 1
  local custom_caddyfile="/home/${USERNAME}/github/linux/dotfiles/Caddyfile"
  local dest_caddyfile="/etc/caddy/Caddyfile"
  if [ -f "$custom_caddyfile" ]; then
    log_info "Copying custom Caddyfile from $custom_caddyfile to $dest_caddyfile..."
    cp -f "$custom_caddyfile" "$dest_caddyfile" || log_warn "Failed to copy custom Caddyfile."
  else
    log_warn "Custom Caddyfile not found at $custom_caddyfile."
  fi
  systemctl enable caddy || log_warn "Failed to enable Caddy service."
  systemctl restart caddy || log_warn "Failed to restart Caddy service."
  log_info "Caddy configuration completed successfully."
}

install_configure_zfs() {
  local zpool_name="WD_BLACK"
  local mount_point="/media/${zpool_name}"
  log_info "Installing prerequisites for ZFS..."
  yay -S --noconfirm linux-headers || handle_error "Failed to install linux-headers." 1
  log_info "Installing ZFS packages..."
  pacman -S --noconfirm zfs-dkms zfs-utils || handle_error "Failed to install ZFS packages." 1
  log_info "ZFS packages installed successfully."
  systemctl enable zfs-import-cache.service || log_warn "Could not enable zfs-import-cache.service."
  systemctl enable zfs-mount.service || log_warn "Could not enable zfs-mount.service."
  if ! zpool list "$zpool_name" &>/dev/null; then
    log_info "Importing ZFS pool '$zpool_name'..."
    zpool import -f "$zpool_name" || { log_error "Failed to import ZFS pool '$zpool_name'."; return 1; }
  else
    log_info "ZFS pool '$zpool_name' is already imported."
  fi
  log_info "Setting mountpoint for ZFS pool '$zpool_name' to '$mount_point'..."
  if ! zfs set mountpoint="${mount_point}" "$zpool_name"; then
    log_warn "Failed to set mountpoint for ZFS pool '$zpool_name'."
  else
    log_info "Mountpoint for pool '$zpool_name' set to '$mount_point'."
  fi
  log_info "ZFS installation and configuration complete."
}

docker_config() {
  log_info "Starting Docker installation and configuration..."
  if command -v docker &>/dev/null; then
    log_info "Docker is already installed."
  else
    log_info "Docker not found; installing..."
    yay -S --noconfirm docker || handle_error "Failed to install Docker." 1
    log_info "Docker installed successfully."
  fi
  if ! id -nG "$USERNAME" | grep -qw "docker"; then
    log_info "Adding user '$USERNAME' to docker group..."
    usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to docker group."
  else
    log_info "User '$USERNAME' is already in docker group."
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
    log_info "Docker Compose not found; installing..."
    pacman -S --noconfirm docker-compose || handle_error "Failed to install Docker Compose." 1
    log_info "Docker Compose installed successfully."
  else
    log_info "Docker Compose is already installed."
  fi
}

#------------------------------------------------------------
# Cleanup Packages Function
#------------------------------------------------------------
cleanup_packages() {
  log_info "Cleaning up orphan packages and cache..."
  pacman -Rns $(pacman -Qtdq 2>/dev/null) --noconfirm || log_warn "No orphan packages to remove."
  yay -Sc --noconfirm || log_warn "Yay cache cleanup failed."
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
  check_root
  #check_distribution
  #ensure_user
  #install_yay
  #check_network
  update_system
  install_packages
  setup_repos
  configure_ssh
  secure_ssh_config
  configure_nftables_firewall
  configure_fail2ban
  deploy_user_scripts
  home_permissions
  bash_dotfiles_load
  set_default_shell
  #install_fastfetch
  #install_plex
  #install_configure_zfs
  #caddy_config
  #docker_config
  cleanup_packages
  prompt_reboot
  log_info "Arch Linux system setup completed successfully."
}

main "$@"