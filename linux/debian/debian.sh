#!/usr/bin/env bash
# Debian System Setup Script
# Fully configures a clean install of Debian with all needed tools and configurations
# for hardening, security, and development.

set -Eeuo pipefail
IFS=$'\n\t'

#------------------------------------------------------------
# Color definitions for logging output
#------------------------------------------------------------
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                      # Reset to No Color

LOG_FILE="/var/log/debian_setup.log"
mkdir -p "$(dirname "$LOG_FILE")" || { echo "Cannot create log directory"; exit 1; }
touch "$LOG_FILE" || { echo "Cannot create log file"; exit 1; }
chmod 600 "$LOG_FILE" || { echo "Cannot set log file permissions"; exit 1; }

#------------------------------------------------------------
# Logging Functions
#------------------------------------------------------------
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
PACKAGES=(
  # Editors and Terminal Utilities
  vim nano screen tmux mc

  # Development tools and build systems
  build-essential cmake ninja-build meson gettext git pkg-config libssl-dev

  # Networking and system exploration
  nmap openssh-server curl wget rsync htop iptables ca-certificates bash-completion
  gdb strace iftop tcpdump lsof jq iproute2 less dnsutils ncdu

  # Compression, text processing, and miscellaneous utilities
  zip unzip gawk ethtool tree exuberant-ctags silversearcher-ag ltrace iperf3

  # Python development tools
  python3 python3-pip python3-venv tzdata

  # System services and logging
  chrony rsyslog cron sudo software-properties-common
)

#------------------------------------------------------------
# check_root
#    Ensures the script is run as root.
#------------------------------------------------------------
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    handle_error "Script must be run as root. Exiting." 1
  fi
  log_info "Running as root."
}

#------------------------------------------------------------
# check_network
#    Verifies network connectivity by pinging google.com.
#------------------------------------------------------------
check_network() {
  log_info "Checking network connectivity..."
  if ! ping -c1 -W5 google.com &>/dev/null; then
    handle_error "No network connectivity detected." 1
  fi
  log_info "Network connectivity OK."
}

#------------------------------------------------------------
# update_system
#    Updates package repositories and upgrades the system.
#------------------------------------------------------------
update_system() {
  log_info "Updating package repositories..."
  if ! apt-get update; then
    handle_error "Failed to update package repositories." 1
  fi
  if ! apt-get upgrade -y; then
    handle_error "Failed to upgrade system." 1
  fi
  log_info "System update and upgrade complete."
}

#------------------------------------------------------------
# install_packages
#    Installs essential packages via apt.
#------------------------------------------------------------
install_packages() {
  log_info "Installing essential packages..."
  if ! apt-get install -y "${PACKAGES[@]}"; then
    handle_error "Package installation failed." 1
  fi
  log_info "Package installation complete."
}

#------------------------------------------------------------
# apt_cleanup
#    Removes unnecessary packages and cleans up the apt cache.
#------------------------------------------------------------
apt_cleanup() {
  log_info "Cleaning up unnecessary packages and cache..."
  apt-get autoremove -y || log_warn "apt-get autoremove failed."
  apt-get clean || log_warn "apt-get clean failed."
  log_info "Apt cleanup complete."
}

#------------------------------------------------------------
# create_or_update_user
#    Creates the user (if not already present) and prompts for a
#    password, then ensures the user is added to the sudo group.
#------------------------------------------------------------
create_or_update_user() {
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' already exists. Skipping creation and proceeding to sudo group addition."
  else
    log_info "Creating user '$USERNAME' with home directory..."
    if ! useradd -m -s /bin/bash "$USERNAME"; then
      handle_error "Failed to create user '$USERNAME'." 1
    fi
    # Prompt for password
    local pass1 pass2
    read -s -p "Enter password for user $USERNAME: " pass1 || handle_error "Failed to read password" 1
    echo
    read -s -p "Retype password for user $USERNAME: " pass2 || handle_error "Failed to read password confirmation" 1
    echo
    if [ "$pass1" != "$pass2" ]; then
      handle_error "Passwords do not match." 1
    fi
    if ! echo "$USERNAME:$pass1" | chpasswd; then
      handle_error "Failed to set password for '$USERNAME'." 1
    fi
    log_info "User '$USERNAME' created successfully."
  fi

  # Add the user to the sudo group if not already a member
  if id -nG "$USERNAME" | grep -qw "sudo"; then
    log_info "User '$USERNAME' is already in the sudo group. Skipping group addition."
  else
    log_info "Adding user '$USERNAME' to sudo group..."
    if ! /usr/sbin/usermod -aG sudo "$USERNAME"; then
      handle_error "Failed to add user '$USERNAME' to sudo group." 1
    fi
    log_info "User '$USERNAME' added to sudo group successfully."
  fi
}

#------------------------------------------------------------
# configure_time_sync
#    Configures time synchronization using chrony.
#------------------------------------------------------------
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

#------------------------------------------------------------
# setup_repos
#    Clones required Git repositories into the user’s Git directory.
#------------------------------------------------------------
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
        if ! git clone "https://github.com/dunamismax/$repo.git" "$target_dir"; then
          handle_error "Failed to clone repository: $repo" 1
        fi
        log_info "Cloned repository: $repo"
      fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for $repo_dir" 1
  fi
}

#------------------------------------------------------------
# configure_ssh
#    Enables and restarts the OpenSSH service.
#------------------------------------------------------------
configure_ssh() {
  log_info "Configuring SSH service..."
  if ! systemctl is-enabled --quiet ssh; then
    systemctl enable ssh || handle_error "Failed to enable SSH service." 1
  fi
  if ! systemctl restart ssh; then
    handle_error "Failed to restart SSH service." 1
  fi
  log_info "SSH service configured successfully."
}

#------------------------------------------------------------
# secure_ssh_config
#    Backs up and hardens the SSH daemon configuration.
#------------------------------------------------------------
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
  # Disable password authentication in favor of key-based auth
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config" || handle_error "Failed to set PasswordAuthentication." 1
  sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config" || handle_error "Failed to set ChallengeResponseAuthentication." 1
  sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config" || handle_error "Failed to set X11Forwarding." 1
  # Ensure empty passwords are not allowed
  if ! grep -q "^PermitEmptyPasswords no" "$sshd_config"; then
    echo "PermitEmptyPasswords no" >> "$sshd_config" || handle_error "Failed to set PermitEmptyPasswords." 1
  fi
  if ! systemctl restart ssh; then
    handle_error "Failed to restart SSH after hardening." 1
  fi
  log_info "SSH configuration hardened successfully."
}

#------------------------------------------------------------
# configure_nftables_firewall
#    Enables and sets the Firewall configuration using nftables.
#------------------------------------------------------------
configure_nftables_firewall() {
  log_info "Configuring firewall using nftables..."

  # Backup existing configuration if present
  if [ -f /etc/nftables.conf ]; then
    cp /etc/nftables.conf /etc/nftables.conf.bak || handle_error "Failed to backup existing nftables config." 1
    log_info "Existing /etc/nftables.conf backed up to /etc/nftables.conf.bak."
  fi

  # Flush any current ruleset
  nft flush ruleset || handle_error "Failed to flush current nftables ruleset." 1

  # Write new nftables configuration (persisted to /etc/nftables.conf)
  cat << 'EOF' > /etc/nftables.conf
#!/usr/sbin/nft -f
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        # Allow established and related connections
        ct state established,related accept
        # Allow loopback traffic
        iif "lo" accept
        # Allow ICMP (ping)
        ip protocol icmp accept
        # Allow TCP connections on essential ports
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

  # Load the new nftables rules
  nft -f /etc/nftables.conf || handle_error "Failed to load nftables rules." 1
  log_info "nftables rules loaded successfully."

  # Enable and restart the nftables service so that rules persist across reboots
  systemctl enable nftables.service || handle_error "Failed to enable nftables service." 1
  systemctl restart nftables.service || handle_error "Failed to restart nftables service." 1
  log_info "nftables service enabled and restarted; firewall configuration persisted."
}

#------------------------------------------------------------
# deploy_user_scripts
#    Deploys user scripts from the repository to the user’s bin directory.
#------------------------------------------------------------
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

#------------------------------------------------------------
# home_permissions
#    Ensures that the user’s home directory has the correct ownership and permissions.
#------------------------------------------------------------
home_permissions() {
  local home_dir="/home/${USERNAME}"
  log_info "Setting ownership and permissions for $home_dir..."
  chown -R "${USERNAME}:${USERNAME}" "$home_dir" || handle_error "Failed to set ownership for $home_dir." 1
  find "$home_dir" -type d -exec chmod g+s {} \; || handle_error "Failed to set group sticky bit on directories in $home_dir." 1
  log_info "Ownership and permissions set successfully."
}

#------------------------------------------------------------
# dotfiles_load
#    Copies .bashrc and .profile from the dotfiles repository into the user’s and root’s home directories.
#------------------------------------------------------------
dotfiles_load() {
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

#------------------------------------------------------------
# set_default_shell
#    Sets /bin/bash as the default shell for user $USERNAME and root using chsh.
#------------------------------------------------------------
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

#------------------------------------------------------------
# install_and_configure_nala
#    Installs Nala on Debian using the Volian Scar repo installation
#    script. This command sets up the repository and installs Nala.
#------------------------------------------------------------
install_and_configure_nala() {
  if command -v nala >/dev/null 2>&1; then
    log_info "Nala is already installed. Skipping installation."
    return 0
  fi

  log_info "Installing Nala using the Volian Scar repository installation script..."
  if ! curl -fsSL https://gitlab.com/volian/volian-archive/-/raw/main/install-nala.sh | bash; then
    handle_error "Failed to install Nala using the Volian Scar installation script." 1
  fi

  if ! command -v nala >/dev/null 2>&1; then
    handle_error "Nala installation did not complete successfully." 1
  fi

  log_info "Nala installed successfully."
}

#------------------------------------------------------------
# main
#    Calls all setup functions in the required order.
#------------------------------------------------------------
main() {
  check_root
  check_network
  update_system
  install_packages
  create_or_update_user
  configure_time_sync
  setup_repos
  configure_ssh
  secure_ssh_config
  configure_nftables_firewall
  deploy_user_scripts
  home_permissions
  dotfiles_load
  set_default_shell
  install_and_configure_nala
  apt_cleanup
  log_info "Debian system setup completed successfully."
}

main "$@"
