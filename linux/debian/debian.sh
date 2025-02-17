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
  bash vim nano screen tmux mc
  build-essential cmake ninja-build meson gettext git nmap
  openssh-server curl wget rsync htop python3 tzdata
  iptables ca-certificates bash-completion
  gdb strace iftop tcpdump lsof jq iproute2 less
  dnsutils ncdu zip unzip gawk ethtool
  chrony rsyslog cron sudo
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
# prompt_for_password
#    Prompts the administrator to enter a password twice for user $USERNAME.
#------------------------------------------------------------
prompt_for_password() {
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
}

#------------------------------------------------------------
# create_user
#    Creates the user (if not already present) and adds them to the sudo group.
#------------------------------------------------------------
create_user() {
  if id "$USERNAME" &>/dev/null; then
    log_info "User '$USERNAME' already exists. Skipping user creation."
  else
    log_info "Creating user '$USERNAME' with home directory..."
    if ! useradd -m -s /bin/bash "$USERNAME"; then
      handle_error "Failed to create user '$USERNAME'." 1
    fi
    prompt_for_password
    log_info "User '$USERNAME' created successfully."
  fi

  if id -nG "$USERNAME" | grep -qw "sudo"; then
    log_info "User '$USERNAME' is already in the sudo group. Skipping group addition."
  else
    log_info "Adding user '$USERNAME' to sudo group..."
    if ! usermod -aG sudo "$USERNAME"; then
      handle_error "Failed to add user '$USERNAME' to sudo group." 1
    fi
    log_info "User '$USERNAME' added to sudo group successfully."
  fi
}

#------------------------------------------------------------
# configure_timezone
#    Installs chrony, enables and starts its systemd service.
#------------------------------------------------------------
configure_timezone() {
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
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config" || handle_error "Failed to set PasswordAuthentication." 1
  sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config" || handle_error "Failed to set ChallengeResponseAuthentication." 1
  sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' "$sshd_config" || handle_error "Failed to set X11Forwarding." 1
  if ! systemctl restart ssh; then
    handle_error "Failed to restart SSH after hardening." 1
  fi
  log_info "SSH configuration hardened successfully."
}

#------------------------------------------------------------
# configure_firewall
#    Configures iptables with secure default policies.
#------------------------------------------------------------
configure_firewall() {
  log_info "Configuring firewall (iptables)..."
  iptables -P INPUT DROP || handle_error "Could not set default INPUT policy." 1
  iptables -P FORWARD DROP || handle_error "Could not set default FORWARD policy." 1
  iptables -P OUTPUT ACCEPT || handle_error "Could not set default OUTPUT policy." 1

  iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || \
    handle_error "Failed to allow established connections." 1

  iptables -A INPUT -i lo -j ACCEPT || \
    handle_error "Failed to allow loopback traffic." 1

  iptables -A INPUT -p icmp -j ACCEPT || \
    handle_error "Failed to allow ICMP traffic." 1

  for port in 22 80 443 32400; do
    iptables -A INPUT -p tcp --dport "$port" -j ACCEPT || \
      handle_error "Failed to allow TCP port $port." 1
  done

  log_info "Firewall rules configured successfully."
}

#------------------------------------------------------------
# persist_firewall
#    Saves current iptables rules to a persistent file.
#------------------------------------------------------------
persist_firewall() {
  log_info "Persisting firewall rules..."
  mkdir -p /etc/iptables || handle_error "Failed to create /etc/iptables directory." 1
  if iptables-save > /etc/iptables/rules.v4; then
    log_info "Firewall rules saved to /etc/iptables/rules.v4."
  else
    handle_error "Failed to save iptables rules." 1
  fi
}

#------------------------------------------------------------
# configure_systemd_firewall_restore
#    Creates a systemd unit to restore firewall rules at boot.
#------------------------------------------------------------
configure_systemd_firewall_restore() {
  log_info "Configuring systemd service for firewall restoration..."
  local unit_file="/etc/systemd/system/iptables-restore.service"
  if [ -f "$unit_file" ]; then
    log_info "Systemd firewall restore service already exists. Skipping."
  else
    cat << 'EOF' > "$unit_file"
[Unit]
Description=Restore iptables rules
Before=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
ExecStart=/sbin/iptables-restore /etc/iptables/rules.v4
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    chmod 644 "$unit_file" || handle_error "Failed to set permissions for $unit_file." 1
    systemctl daemon-reload || handle_error "Failed to reload systemd daemon." 1
    systemctl enable iptables-restore.service || handle_error "Failed to enable iptables restore service." 1
    log_info "Systemd firewall restore service configured successfully."
  fi
}

#------------------------------------------------------------
# configure_system_services
#    Ensures that system services like rsyslog and cron are enabled and running.
#------------------------------------------------------------
configure_system_services() {
  log_info "Ensuring system services are enabled..."
  if ! systemctl is-enabled --quiet rsyslog; then
    systemctl enable rsyslog || handle_error "Failed to enable rsyslog." 1
    systemctl start rsyslog || handle_error "Failed to start rsyslog." 1
    log_info "Rsyslog service enabled and started."
  else
    log_info "Rsyslog service already enabled."
  fi

  if ! systemctl is-enabled --quiet cron; then
    systemctl enable cron || handle_error "Failed to enable cron." 1
    systemctl start cron || handle_error "Failed to start cron." 1
    log_info "Cron service enabled and started."
  else
    log_info "Cron service already enabled."
  fi
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
# setup_cron
#    Starts the cron service (redundant if already started by system services).
#------------------------------------------------------------
setup_cron() {
  log_info "Starting cron service..."
  if systemctl restart cron; then
    log_info "Cron service restarted successfully."
  else
    handle_error "Failed to restart cron service." 1
  fi
}

#------------------------------------------------------------
# secure_sysctl
#    Applies kernel hardening settings via sysctl.
#------------------------------------------------------------
secure_sysctl() {
  log_info "Applying sysctl kernel hardening settings..."
  local sysctl_conf="/etc/sysctl.conf"
  if grep -q "net.ipv4.tcp_syncookies" "$sysctl_conf" 2>/dev/null; then
    log_info "Sysctl settings already applied. Skipping."
    return 0
  fi
  if [ -f "$sysctl_conf" ]; then
    cp "$sysctl_conf" "${sysctl_conf}.bak" || handle_error "Failed to backup $sysctl_conf" 1
    log_info "Backed up existing sysctl.conf to ${sysctl_conf}.bak."
  else
    log_info "No existing sysctl.conf found; creating a new one."
  fi
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
  if sysctl -p; then
    log_info "Sysctl settings applied successfully."
  else
    handle_error "Failed to apply sysctl settings." 1
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
#    Sets /bin/bash as the default shell for user $USERNAME and root.
#------------------------------------------------------------
set_default_shell() {
  local target_shell="/bin/bash"
  if [ ! -x "$target_shell" ]; then
    log_error "Bash not found or not executable at $target_shell. Cannot set default shell."
    return 1
  fi
  log_info "Setting default shell to $target_shell for user '$USERNAME' and root."
  if grep -q "^$USERNAME:.*$target_shell\$" /etc/passwd; then
    log_info "User '$USERNAME' already has $target_shell as default shell. Skipping."
  elif grep -q "^$USERNAME:" /etc/passwd; then
    sed -i -E "s|^($USERNAME:[^:]*:[^:]*:[^:]*:[^:]*:[^:]*):[^:]*\$|\1:$target_shell|" /etc/passwd && \
      log_info "Set default shell for user '$USERNAME' to $target_shell." || \
      { log_error "Failed to set shell for user '$USERNAME'."; return 1; }
  else
    log_warn "User '$USERNAME' not found in /etc/passwd. Skipping user shell update."
  fi
  if grep -q "^root:.*$target_shell\$" /etc/passwd; then
    log_info "Root already uses $target_shell as default shell. Skipping."
  elif grep -q "^root:" /etc/passwd; then
    sed -i -E "s|^(root:[^:]*:[^:]*:[^:]*:[^:]*:[^:]*):[^:]*\$|\1:$target_shell|" /etc/passwd && \
      log_info "Set default shell for root to $target_shell." || \
      { log_error "Failed to set shell for root."; return 1; }
  else
    log_warn "Root entry not found in /etc/passwd. Skipping root shell update."
  fi
  log_info "Default shell configuration complete."
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
  create_user
  configure_timezone
  setup_repos
  configure_ssh
  secure_ssh_config
  configure_firewall
  persist_firewall
  configure_systemd_firewall_restore
  secure_sysctl
  deploy_user_scripts
  setup_cron
  configure_system_services
  home_permissions
  dotfiles_load
  set_default_shell
  log_info "Debian system setup completed successfully."
}

main "$@"
