#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Debian System Setup & Hardening Script
#
# This comprehensive script automates the initial configuration of a clean
# Debian installation. It installs essential applications, development tools,
# and implements advanced system hardening measures to secure your system.
#
# Key Features:
#   • System Update & Upgrade: Refreshes repositories and performs a full
#     system upgrade.
#   • User & Shell Configuration: Creates a designated user, sets default
#     shells, and deploys custom dotfiles for both user and root.
#   • Security Enhancements: Harden SSH settings, disable IPv6, and configure
#     a robust firewall using nftables along with Fail2ban for intrusion prevention.
#   • Development Environment: Installs a wide range of packages including
#     build essentials, Git, Docker (with Docker Compose), and more.
#   • Custom Repository Setup: Clones essential GitHub repositories for
#     utilities and scripts.
#   • Automated Maintenance: Configures unattended upgrades and cleans up
#     unnecessary packages and cache.
#
# Prerequisites:
#   • Must be run as the root user.
#   • Designed for Debian-based systems (including derivatives with Debian-like
#     characteristics).
#
# Usage:
#   Run the script with root privileges:
#       sudo ./debian.sh
#
# Author: dunamismax
# License: MIT
# -----------------------------------------------------------------------------

set -Eeuo pipefail
IFS=$'\n\t'
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C.UTF-8
export PATH="$PATH:/sbin:/usr/sbin"


NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'     # Error messages
NORD13='\033[38;2;235;203;139m'    # Warning messages
NORD14='\033[38;2;163;190;140m'    # Info messages
NC='\033[0m'                      # Reset to No Color


LOG_FILE="/var/log/debian_setup.log"
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


USERNAME="sawyer"
TIMEZONE="America/New_York"


# Packages list
PACKAGES=(
  # Editors and Terminal Utilities
  bash vim nano screen tmux mc

  # Development tools and build systems
  build-essential cmake ninja-build meson gettext git pkg-config libssl-dev libffi-dev

  # Networking, system utilities, and debugging tools
  nmap openssh-server ufw curl wget rsync htop iptables ca-certificates bash-completion netcat-openbsd gdb strace iftop tcpdump lsof jq iproute2 less dnsutils ncdu

  # Compression, text processing, and miscellaneous utilities
  zip unzip gawk ethtool tree exuberant-ctags silversearcher-ag ltrace

  # Python development tools
  python3 python3-dev python3-pip python3-venv tzdata

  # Essential libraries for building software
  zlib1g-dev libreadline-dev libbz2-dev tk-dev xz-utils libncurses5-dev libgdbm-dev libnss3-dev liblzma-dev libxml2-dev libxmlsec1-dev

  # System and package management utilities
  software-properties-common apt-transport-https gnupg lsb-release

  # Additional compilers and tools
  clang llvm

  # System services and logging
  chrony rsyslog cron sudo
)


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
    if [ "${ID:-}" != "debian" ] && [[ ! "${ID_LIKE:-}" =~ debian ]]; then
      handle_error "This script is intended for Debian systems. Detected: ${NAME:-Unknown}." 1
    fi
    log_info "Distribution confirmed: ${PRETTY_NAME:-Debian-based}."
  else
    log_warn "/etc/os-release not found. Assuming Debian-based distro."
  fi
}


update_system() {
  log_info "Updating package repositories..."
  if ! apt-get update; then
    handle_error "Failed to update package repositories." 1
  fi

  log_info "Upgrading system packages (dist-upgrade)..."
  if ! apt-get dist-upgrade -y; then
    handle_error "Failed to upgrade system." 1
  fi

  log_info "System update and upgrade complete."
}


ensure_user() {
  log_info "Ensuring user '$USERNAME' exists..."
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' already exists."
  else
    log_info "User '$USERNAME' does not exist. Creating..."
    adduser --disabled-password --gecos "" "$USERNAME" || handle_error "Failed to create user '$USERNAME'." 1
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
  apt-get install -y "${PACKAGES[@]}" || handle_error "Package installation failed." 1
  log_info "Package installation complete."
}


configure_sudo() {
  log_info "Configuring sudo privileges for user '$USERNAME'..."
  if id -nG "$USERNAME" | grep -qw "sudo"; then
    log_info "User '$USERNAME' is already in the sudo group. No changes needed."
  else
    log_info "Adding user '$USERNAME' to the sudo group..."
    /usr/sbin/usermod -aG sudo "$USERNAME" || handle_error "Failed to add user '$USERNAME' to the sudo group." 1
    log_info "User '$USERNAME' added to the sudo group successfully."
  fi
}


configure_time_sync() {
  log_info "Configuring time synchronization with chrony..."
  if ! systemctl is-active --quiet chrony; then
    systemctl enable chrony || handle_error "Failed to enable chrony service." 1
    systemctl start chrony || handle_error "Failed to start chrony service." 1
  else
    log_info "Chrony is already active. Skipping."
  fi
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
  if ! systemctl is-enabled --quiet ssh; then
    systemctl enable ssh || handle_error "Failed to enable SSH service." 1
  fi
  systemctl restart ssh || handle_error "Failed to restart SSH service." 1
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
  systemctl restart ssh || handle_error "Failed to restart SSH after hardening." 1
  log_info "SSH configuration hardened successfully."
}


configure_nftables_firewall() {
  log_info "Configuring firewall using nftables..."
  if ! command -v nft >/dev/null 2>&1; then
    log_info "nft command not found. Installing nftables package..."
    apt-get update || handle_error "Failed to update APT package index." 1
    apt-get install -y nftables || handle_error "Failed to install nftables." 1
  fi
  if [ -f /etc/nftables.conf ]; then
    cp /etc/nftables.conf /etc/nftables.conf.bak || handle_error "Failed to backup existing nftables config." 1
    log_info "Existing /etc/nftables.conf backed up to /etc/nftables.conf.bak."
  fi
  /usr/sbin/nft flush ruleset || handle_error "Failed to flush current nftables ruleset." 1
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
  /usr/sbin/nft -f /etc/nftables.conf || handle_error "Failed to load nftables rules." 1
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
  if ! apt-get install -y fail2ban; then
    handle_error "Failed to install Fail2ban." 1
  fi
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
  local source_dir="/home/${USERNAME}/github/bash/linux/debian/dotfiles"
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
  if command -v nala >/dev/null 2>&1; then
    log_info "Nala is already installed. Skipping installation."
    return 0
  fi
  log_info "Installing Nala using the Volian Scar repository installation script..."
  curl -fsSL https://gitlab.com/volian/volian-archive/-/raw/main/install-nala.sh | bash || handle_error "Failed to install Nala using the Volian Scar installation script." 1
  if ! command -v nala >/dev/null 2>&1; then
    handle_error "Nala installation did not complete successfully." 1
  fi
  log_info "Nala installed successfully."
}


install_fastfetch() {
  local url="https://github.com/fastfetch-cli/fastfetch/releases/download/2.36.1/fastfetch-linux-amd64.deb"
  local deb_file="/tmp/fastfetch-linux-amd64.deb"
  log_info "Downloading fastfetch from $url..."
  if ! curl -fsSL -o "$deb_file" "$url"; then
    handle_error "Failed to download fastfetch from $url." 1
  fi
  log_info "Installing fastfetch..."
  if ! dpkg -i "$deb_file"; then
    log_warn "dpkg installation failed. Attempting to fix dependencies..."
    if ! apt-get update && apt-get -f install -y; then
      handle_error "Failed to install fastfetch and fix dependencies." 1
    fi
  fi
  rm -f "$deb_file"
  log_info "fastfetch installed successfully."
}


docker_config() {
  log_info "Starting Docker installation and configuration..."
  if command -v docker &>/dev/null; then
    log_info "Docker is already installed."
  else
    log_info "Docker not found; installing Docker..."
    apt install -y docker.io || handle_error "Failed to install Docker."
    log_info "Docker installed successfully."
  fi
  if ! id -nG "$USERNAME" | grep -qw docker; then
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
  systemctl restart docker || handle_error "Failed to restart Docker."
  log_info "Docker service is enabled and running."
  log_info "Starting Docker Compose installation..."
  if ! command -v docker-compose &>/dev/null; then
    local version="2.20.2"
    log_info "Docker Compose not found; downloading version ${version}..."
    curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
      -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
    chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
    log_info "Docker Compose installed successfully."
  else
    log_info "Docker Compose is already installed."
  fi
}


configure_unattended_upgrades() {
  log_info "Installing and configuring unattended-upgrades..."
  apt-get install -y unattended-upgrades || handle_error "Failed to install unattended-upgrades." 1
  dpkg-reconfigure -plow unattended-upgrades || log_warn "Failed to reconfigure unattended-upgrades."
  log_info "Unattended-upgrades configured successfully."
}


apt_cleanup() {
  log_info "Cleaning up unnecessary packages and cache..."
  apt-get autoremove -y || log_warn "apt-get autoremove failed."
  apt-get clean || log_warn "apt-get clean failed."
  log_info "Apt cleanup complete."
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


#------------------------------------------------------------
# Main Function: Execute Setup Steps in Order
#------------------------------------------------------------
main() {
  check_root
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
  set_default_shell
  install_and_configure_nala
  docker_config
  install_fastfetch
  bash_dotfiles_load
  configure_unattended_upgrades
  apt_cleanup
  log_info "Debian system setup completed successfully."
  prompt_reboot
}

main "$@"
