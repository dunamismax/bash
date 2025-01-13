#!/usr/local/bin/bash
#===============================================================================
# FreeBSD Automated System Configuration Script
#===============================================================================
# This script fully configures a new FreeBSD installation based on predefined
# system policies and best practices. It performs a comprehensive setup that
# includes:
#   • Bootstrapping and updating the pkg system, then installing a suite of
#     essential packages.
#   • Dynamically identifying the primary network adapter for Internet access
#     and configuring DHCP settings automatically.
#   • Configuring system settings via /etc/rc.conf to enable essential services,
#     improve system performance, and enhance security.
#   • Updating DNS settings in /etc/resolv.conf with specified nameservers or
#     enabling local_unbound for dynamic DNS resolution.
#   • Granting sudo privileges to designated users by adding them to the wheel
#     group and configuring sudoers with secure defaults.
#   • Hardening SSH by updating /etc/ssh/sshd_config with secure parameters,
#     such as disabling root login and limiting authentication attempts.
#   • Setting up and configuring PF firewall with custom rules, including stateful
#     connections, SSH rate-limiting, and logging of blocked inbound traffic.
#   • Automating the creation and population of user environment files
#     (.bashrc, .bash_profile) with optimized settings and aliases.
#   • Employing robust error handling, dynamic configuration backups, and
#     detailed logging throughout the process to /var/log/freebsd_setup.log.
#   • Enabling and configuring graphical environments with X11, SLiM, and i3,
#     including post-setup configurations for desktop environments.
#   • Finalizing the setup by upgrading installed packages, cleaning caches,
#     and validating configurations for stability.
#
# Usage: Execute this script as root on a fresh FreeBSD install to automate the
#        initial system configuration process or to reapply system policies.
#
# Notes:
#   • This script assumes a basic FreeBSD installation with network access.
#   • Review and customize variables and settings before execution to align
#     with specific system requirements and preferences.
#===============================================================================

set -euo pipefail
IFS=$'\n\t'

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Global Variables
LOG_FILE="/var/log/freebsd_setup.log"
PACKAGES=(
  # Essential Shells and Editors
  "vim" "bash" "zsh" "tmux" "mc" "nano" "fish" "screen"
  # Version Control and Scripting
  "git" "perl5" "python3"
  # Network and Internet Utilities
  "curl" "wget" "netcat" "tcpdump" "rsync" "rsnapshot" "samba"
  # System Monitoring and Management
  "htop" "sudo" "bash-completion" "zsh-completions" "neofetch" "tig" "bat" "exa"
  "fd" "jq" "iftop" "nmap" "tree" "fzf" "lynx" "curlie" "ncdu" "fail2ban"
  "gcc" "make" "lighttpd" "smartmontools" "zfs-auto-snapshot"
  # Database and Media Services
  "plexmediaserver" "postgresql" "caddy" "go"
  # System Tools and Backup
  "duplicity" "ffmpeg" "restic" "syslog-ng"
  # X11 and Window Management
  "xorg" "i3" "SLiM"
  # Virtualization and VM Support
  "qemu" "libvirt" "virt-manager" "vm-bhyve" "bhyve-firmware" "grub2-bhyve"
)

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Logging function with timestamp and log levels
log() {
  local level="${1:-INFO}"  # Default log level is INFO
  local msg="${2:-}"        # Log message
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

  # Validate log level
  case "$level" in
    INFO|WARN|ERROR|DEBUG) ;;
    *) level="INFO" ;;  # Default to INFO for unknown levels
  esac

  # Format log message
  local formatted_msg="[$timestamp] [$level] $msg"

  # Output to console and log file
  if [[ -n "$LOG_FILE" ]]; then
    echo "$formatted_msg" | tee -a "$LOG_FILE" >/dev/null
  else
    echo "$formatted_msg"
  fi
}

# Function to handle errors and exit
error_exit() {
  local msg="${1:-"An unknown error occurred."}"  # Default error message
  local exit_code="${2:-1}"                       # Default exit code is 1

  # Log the error with level ERROR
  log "ERROR" "$msg"

  # Perform cleanup if necessary
  cleanup

  # Exit with the specified code
  exit "$exit_code"
}

# Cleanup function to handle temporary files or revert partial changes
cleanup() {
  log "INFO" "Performing cleanup tasks."

  # Example: Remove temporary files or revert changes
  if [[ -n "${temp_file:-}" && -f "$temp_file" ]]; then
    rm -f "$temp_file"
    log "INFO" "Temporary file $temp_file removed."
  fi

  log "INFO" "Cleanup completed."
}

# Trap setup
trap error_exit ERR
trap "log 'WARN' 'Script interrupted by user.'; cleanup; exit 1" INT

# Ensure script is run as root
check_root() {
  log "Checking if the script is running as root."

  # Use EUID or fallback to id command for environments without EUID
  if [[ -n "${EUID:-}" && "$EUID" -ne 0 ]] || [[ -z "${EUID:-}" && "$(id -u)" -ne 0 ]]; then
    error_exit "This script must be run as root. Current user: $(id -un). Please rerun as root or use 'sudo'."
  fi

  log "Script is running as root. Continuing."
}

# Identify primary network adapter
identify_primary_iface() {
  log "Identifying primary network adapter for Internet connection."

  # Attempt to determine the primary interface using `route`
  if command -v route &>/dev/null; then
    primary_iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [[ -n "$primary_iface" ]]; then
      log "Primary network adapter identified using route: $primary_iface"
      export primary_iface
      return
    else
      log "Failed to identify primary interface using route. Falling back to alternate methods."
    fi
  else
    log "Command 'route' not found. Skipping primary interface detection using route."
  fi

  # Fallback: Attempt to identify using `netstat`
  if command -v netstat &>/dev/null; then
    primary_iface=$(netstat -rn | awk '/^default/ {print $NF}' | head -n 1)
    if [[ -n "$primary_iface" ]]; then
      log "Primary network adapter identified using netstat: $primary_iface"
      export primary_iface
      return
    else
      log "Failed to identify primary interface using netstat."
    fi
  else
    log "Command 'netstat' not found. Skipping netstat-based detection."
  fi

  # Fallback to a default interface (if specified)
  local default_iface="${1:-}"
  if [[ -n "$default_iface" ]]; then
    log "Falling back to the default interface: $default_iface"
    primary_iface="$default_iface"
    export primary_iface
  else
    error_exit "Primary network interface not found. Aborting configuration."
  fi
}

# Bootstrap pkg and install packages
bootstrap_and_install_pkgs() {
  log "Bootstrapping pkg and installing base packages."

  # Default package list if none provided
  local packages=("${PACKAGES[@]}")
  if [[ $# -gt 0 ]]; then
    packages=("$@")
    log "Using custom package list: ${packages[*]}"
  else
    log "Using default package list."
  fi

  # Check if pkg is available; bootstrap if not
  if ! command -v pkg &>/dev/null; then
    log "pkg not found. Bootstrapping pkg..."
    env ASSUME_ALWAYS_YES=yes pkg bootstrap || error_exit "Failed to bootstrap pkg."
  fi

  # Force-update the package database
  pkg update -f || error_exit "pkg update failed."

  # Install packages dynamically
  log "Installing packages if not already installed."
  local failed_packages=()
  for pkg in "${packages[@]}"; do
    if ! pkg info -q "$pkg"; then
      log "Installing package: $pkg"
      if pkg install -y "$pkg"; then
        log "Successfully installed $pkg."
      else
        log "Failed to install $pkg."
        failed_packages+=("$pkg")
      fi
    else
      log "Package $pkg is already installed, skipping."
    fi
  done

  # Check for failed installations
  if [[ ${#failed_packages[@]} -gt 0 ]]; then
    log "The following packages failed to install: ${failed_packages[*]}"
    return 1
  fi

  log "Package installation process completed successfully."
}

# Configure /etc/rc.conf settings
configure_rc_conf() {
  log "Configuring /etc/rc.conf with system settings."
  local rc_conf="/etc/rc.conf"
  local hostname="${1:-freebsd}"   # Default to 'freebsd' if no hostname is provided
  local interfaces=("${2:-${primary_iface}}") # Use primary_iface if no interfaces are specified

  # Backup rc.conf if it exists and no backup is present
  if [[ -f "$rc_conf" && ! -f "${rc_conf}.bak" ]]; then
    cp "$rc_conf" "${rc_conf}.bak" || error_exit "Failed to backup rc.conf."
    log "Backup of rc.conf created at ${rc_conf}.bak."
  elif [[ ! -f "$rc_conf" ]]; then
    log "No existing rc.conf found. A new file will be created."
  else
    log "Backup of rc.conf already exists. Skipping backup."
  fi

  # Update rc.conf settings
  declare -A settings=(
    ["clear_tmp_enable"]="YES"
    ["hostname"]="$hostname"
    ["local_unbound_enable"]="YES"
    ["sshd_enable"]="YES"
    ["moused_enable"]="NO"
    ["ntpd_enable"]="YES"
    ["powerd_enable"]="YES"
    ["dumpdev"]="AUTO"
    ["zfs_enable"]="YES"
  )

  # Apply general settings
  for key in "${!settings[@]}"; do
    sysrc "$key=${settings[$key]}" || log "Failed to set $key=${settings[$key]} in rc.conf."
  done

  # Configure network interfaces
  if [[ -n "${interfaces[*]}" ]]; then
    for iface in "${interfaces[@]}"; do
      sysrc "ifconfig_${iface}=DHCP" \
        && log "Configured network interface $iface with DHCP." \
        || log "Failed to configure network interface $iface."
    done
  else
    log "No network interfaces provided or detected. Skipping network configuration."
  fi

  log "/etc/rc.conf has been updated with the new settings."
}

# Configure DNS settings
configure_dns() {
  log "Configuring DNS settings in /etc/resolv.conf."
  local resolv_conf="/etc/resolv.conf"
  local nameservers=("1.1.1.1" "9.9.9.9") # Default nameservers

  # Check if custom nameservers are provided as arguments
  if [[ $# -gt 0 ]]; then
    nameservers=("$@")
    log "Using custom nameservers: ${nameservers[*]}"
  else
    log "Using default nameservers: ${nameservers[*]}"
  fi

  # Backup resolv.conf if it exists and is not empty
  if [[ -f "$resolv_conf" && -s "$resolv_conf" ]]; then
    if [[ ! -f "${resolv_conf}.bak" ]]; then
      cp "$resolv_conf" "${resolv_conf}.bak" || log "Failed to backup resolv.conf."
      log "Backup of resolv.conf created at ${resolv_conf}.bak."
    else
      log "Backup of resolv.conf already exists. Skipping backup."
    fi
  else
    log "No existing resolv.conf found or file is empty. Skipping backup."
  fi

  # Clear existing nameserver entries
  sed -i '' '/^\s*nameserver\s/d' "$resolv_conf" || log "Failed to clean old nameservers from resolv.conf."

  # Add new nameserver entries
  for ns in "${nameservers[@]}"; do
    if ! grep -q "^\s*nameserver\s\+$ns" "$resolv_conf"; then
      echo "nameserver $ns" >> "$resolv_conf" \
        && log "Added nameserver $ns to resolv.conf." \
        || log "Failed to add nameserver $ns to resolv.conf."
    else
      log "Nameserver $ns is already present in resolv.conf. Skipping."
    fi
  done

  log "/etc/resolv.conf has been successfully updated with new nameserver entries."
}

# Grant sudo privileges to a user
configure_sudoers() {
  local user="${1:-sawyer}"     # Default to 'sawyer' if no user is provided
  local sudoers_file="/usr/local/etc/sudoers"
  local nopasswd="${2:-false}"  # Default is to require a password

  # Ensure the user exists
  if ! pw usershow "$user" > /dev/null 2>&1; then
    log "User '$user' does not exist. Aborting sudo configuration."
    return 1
  fi

  # Add user to the wheel group if not already a member
  if pw groupshow wheel | grep -qw "$user"; then
    log "User '$user' is already a member of the wheel group. Skipping group modification."
  else
    if pw usermod "$user" -G wheel; then
      log "User '$user' added to the wheel group for sudo privileges."
    else
      log "Failed to add user '$user' to the wheel group."
      return 1
    fi
  fi

  # Ensure the sudoers file exists
  if [[ ! -f "$sudoers_file" ]]; then
    log "Sudoers file not found at $sudoers_file. Aborting."
    return 1
  fi

  # Enable wheel group in sudoers
  if ! grep -q "^%wheel" "$sudoers_file"; then
    log "Enabling wheel group in sudoers."
    local sudo_rule="%wheel ALL=(ALL) ALL"
    if [[ "$nopasswd" == "true" ]]; then
      sudo_rule="%wheel ALL=(ALL) NOPASSWD: ALL"
    fi
    if echo "$sudo_rule" >> "$sudoers_file"; then
      log "Sudoers file updated to grant wheel group privileges (${nopasswd:+NOPASSWD})."
    else
      log "Failed to update sudoers file for wheel group."
      return 1
    fi
  else
    log "Wheel group privileges are already configured in sudoers. Skipping."
  fi
}

# Hardening SSH configuration
configure_ssh() {
  log "Updating SSH configuration for security and specific settings."
  local sshd_config="/etc/ssh/sshd_config"
  declare -A sshd_settings=(
    ["Port"]="22"
    ["AddressFamily"]="any"
    ["ListenAddress"]="0.0.0.0"
    ["MaxAuthTries"]="6"
    ["MaxSessions"]="10"
    ["PermitRootLogin"]="no"
  )

  # Backup sshd_config if not already backed up
  if [[ ! -f "${sshd_config}.bak" ]]; then
    cp "$sshd_config" "${sshd_config}.bak" || log "Failed to backup sshd_config."
    log "Backup of sshd_config created at ${sshd_config}.bak."
  fi

  # Update or add settings dynamically
  for setting in "${!sshd_settings[@]}"; do
    local value="${sshd_settings[$setting]}"
    if grep -Eq "^\s*${setting}\s" "$sshd_config"; then
      sed -i '' "s|^\s*${setting}\s.*|${setting} ${value}|" "$sshd_config" \
        && log "Updated ${setting} to ${value}." \
        || log "Failed to update ${setting}."
    else
      echo "${setting} ${value}" >> "$sshd_config" \
        && log "Added ${setting} ${value}." \
        || log "Failed to add ${setting} ${value}."
    fi
  done

  # Ensure ownership and permissions are correct
  chown root:wheel "$sshd_config" || log "Failed to set ownership for $sshd_config."
  chmod 600 "$sshd_config" || log "Failed to set permissions for $sshd_config."

  # Restart the SSH service
  if service sshd restart; then
    log "SSH service restarted with updated configuration."
  else
    log "Failed to restart SSH service."
  fi
}

# Configure PF firewall
configure_pf() {
  log "Configuring PF firewall."
  local pf_conf="/etc/pf.conf"

  # Ensure primary_iface is set
  if [[ -z "${primary_iface:-}" ]]; then
    log "Primary interface not set. Attempting to identify primary interface."
    identify_primary_iface
  fi

  if [[ -z "${primary_iface:-}" ]]; then
    error_exit "Failed to identify the primary network interface. Cannot configure PF."
  fi

  # Backup existing pf.conf if it exists
  if [[ -f "$pf_conf" ]]; then
    cp "$pf_conf" "${pf_conf}.bak" || log "Failed to backup pf.conf."
    log "Backup of pf.conf created at ${pf_conf}.bak."
  else
    log "No existing pf.conf found. Creating a new one."
  fi

  # Write new rules to pf.conf
  cat <<EOF > "$pf_conf"
# /etc/pf.conf - Minimal pf ruleset with SSH rate-limiting

# Skip filtering on the loopback interface
set skip on lo0

# Normalize and scrub incoming packets
scrub in all

# Enable logging on primary interface
set loginterface ${primary_iface}

# Block all inbound traffic by default and log blocked packets
block in log all

# Allow all outbound traffic on the primary interface, keeping stateful connections
pass out on ${primary_iface} all keep state

# Rate-limiting for SSH: Max 10 connections per 5 seconds, burstable to 15
table <ssh_limited> persist
block in quick on ${primary_iface} proto tcp to port 22
pass in quick on ${primary_iface} proto tcp to port 22 keep state \\
    (max-src-conn 10, max-src-conn-rate 15/5, overload <ssh_limited> flush global)

# Allow PlexMediaServer traffic
pass in quick on ${primary_iface} proto tcp to port 32400 keep state
pass in quick on ${primary_iface} proto udp to port 32400 keep state
EOF

  # Validate the new PF rules before applying them
  if ! pfctl -n -f "$pf_conf"; then
    error_exit "Failed to validate PF rules. Aborting."
  fi

  # Enable and restart PF service
  sysrc pf_enable="YES" || log "Failed to enable pf in rc.conf."
  sysrc pf_rules="/etc/pf.conf" || log "Failed to set pf_rules in rc.conf."
  service pf enable || log "Failed to enable pf service."
  service pf restart || log "Failed to restart pf service."

  log "PF firewall configured and restarted with custom rules."
}

# Set Bash as default shell and configure user environment
set_default_shell_and_env() {
  log "Setting Bash as the default shell and configuring user environments."
  local bash_path="/usr/local/bin/bash"
  local users=("$@")  # Accept user list as arguments
  [[ ${#users[@]} -eq 0 ]] && users=("root" "sawyer")  # Default users if none provided

  # Ensure Bash is listed in /etc/shells
  if ! grep -qF "$bash_path" /etc/shells; then
    echo "$bash_path" >> /etc/shells \
      && log "Added $bash_path to /etc/shells." \
      || error_exit "Failed to add $bash_path to /etc/shells."
  else
    log "$bash_path already exists in /etc/shells."
  fi

  # Process each user
  for user in "${users[@]}"; do
    if pw usershow "$user" &>/dev/null; then
      log "Processing user: $user"

      # Set Bash as the default shell if not already set
      if [[ "$(pw usershow "$user" | awk -F: '{print $7}')" != "$bash_path" ]]; then
        chsh -s "$bash_path" "$user" \
          && log "Set Bash as default shell for user $user." \
          || log "Failed to set Bash as default shell for user $user."
      else
        log "Bash is already the default shell for user $user. Skipping."
      fi

      # Configure user's environment files
      local user_home
      user_home=$(eval echo "~$user")
      if [[ -d "$user_home" ]]; then
        configure_user_env "$user_home"
      else
        log "Home directory for user $user not found. Skipping environment setup."
      fi
    else
      log "User $user does not exist. Skipping."
    fi
  done
}

# Helper function to configure user's environment files
configure_user_env() {
  local home_dir="$1"
  local bashrc_file="$home_dir/.bashrc"
  local bash_profile_file="$home_dir/.bash_profile"

  # Configure .bashrc
  if [[ -f "$bashrc_file" ]]; then
    mv "$bashrc_file" "${bashrc_file}.bak" \
      && log "Backup of existing .bashrc created for $home_dir." \
      || log "Failed to create backup of existing .bashrc for $home_dir."
  fi
  cat <<'EOF' > "$bashrc_file"
#!/usr/local/bin/bash
# ~/.bashrc: executed by bash(1) for interactive shells.

# --------------------------------------
# Basic Settings and Environment Setup
# --------------------------------------

# Check if the shell is interactive
case $- in
    *i*) ;;
      *) return;;
esac

# Set a colorful prompt: [user@host current_directory]$
PS1='\[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ '

# Ensure PATH includes common FreeBSD binary directories
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Enable color support for 'ls' and grep
alias ls='ls -lah --color=auto'
alias grep='grep --color=auto'

# --------------------------------------
# History Configuration
# --------------------------------------

# Avoid duplicate entries and set history sizes
export HISTCONTROL=ignoredups:erasedups
export HISTSIZE=1000
export HISTFILESIZE=2000

# Append rather than overwrite history on shell exit
shopt -s histappend

# --------------------------------------
# Pager and Less Configuration
# --------------------------------------

export PAGER='less -R'
export LESS='-R'

# --------------------------------------
# Bash Completion
# --------------------------------------

# Source Bash completion if available
if [ -f /usr/local/etc/bash_completion ]; then
    . /usr/local/etc/bash_completion
fi

# --------------------------------------
# Custom Aliases and Functions
# --------------------------------------

# Common shortcuts
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'

# Add more aliases or functions below as needed

# --------------------------------------
# End of .bashrc
# --------------------------------------
EOF
  chmod +x "$bashrc_file" \
    && log "Populated and set execute permissions for $bashrc_file." \
    || log "Failed to set permissions for $bashrc_file."

  # Configure .bash_profile
  if [[ -f "$bash_profile_file" ]]; then
    mv "$bash_profile_file" "${bash_profile_file}.bak" \
      && log "Backup of existing .bash_profile created for $home_dir." \
      || log "Failed to create backup of existing .bash_profile for $home_dir."
  fi
  cat <<'EOF' > "$bash_profile_file"
#!/usr/local/bin/bash
# ~/.bash_profile: executed by bash(1) for login shells.

# Source the .bashrc if it exists
if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
EOF
  chmod +x "$bash_profile_file" \
    && log "Populated and set execute permissions for $bash_profile_file." \
    || log "Failed to set permissions for $bash_profile_file."
}

# Finalizing configuration
finalize_configuration() {
  log "Finalizing system configuration."

  # Upgrade installed packages
  log "Upgrading installed packages."
  if pkg upgrade -y; then
    log "Package upgrade completed successfully."
  else
    log "Package upgrade failed. Please check the logs for details."
    return 1
  fi

  # Clean up package cache
  log "Cleaning up package cache."
  if pkg clean -y; then
    log "Package cache cleaned successfully."
  else
    log "Package clean failed. Continuing with the next steps."
  fi

  # Enable and start services
  local services=("plexmediaserver") # Add more services to this list as needed
  for service in "${services[@]}"; do
    log "Enabling and starting $service service."
    if sysrc "${service}_enable=YES"; then
      log "$service service enabled in rc.conf."
    else
      log "Failed to enable $service service in rc.conf."
      return 1
    fi

    if service "$service" start; then
      log "$service service started successfully."
    else
      log "Failed to start $service service. Please check the logs for details."
      return 1
    fi
  done

  log "System configuration finalized successfully."
}

# Configure X11, i3, and SLiM
configure_graphical_env() {
  local user="${1:-sawyer}"             # Default to 'sawyer' if no user is specified
  local home_dir
  home_dir=$(eval echo "~$user")        # Get user's home directory
  local xinitrc_file="$home_dir/.xinitrc"

  log "Enabling and configuring SLiM for X11 and i3 session."

  # Enable SLiM in rc.conf
  if sysrc slim_enable="YES"; then
    log "SLiM enabled in rc.conf."
  else
    log "Failed to enable SLiM in rc.conf."
    return 1
  fi

  # Ensure required packages are installed
  local required_pkgs=("xorg" "i3" "slim")
  for pkg in "${required_pkgs[@]}"; do
    if ! pkg info -q "$pkg"; then
      log "Required package $pkg is not installed. Installing now."
      if ! pkg install -y "$pkg"; then
        log "Failed to install required package $pkg. Aborting."
        return 1
      fi
    fi
  done

  # Configure .xinitrc for the user
  log "Configuring .xinitrc to start i3 for user $user."
  if [[ -f "$xinitrc_file" ]]; then
    log ".xinitrc already exists for user $user. Creating a backup."
    mv "$xinitrc_file" "${xinitrc_file}.bak" || {
      log "Failed to create backup of existing .xinitrc for user $user."
      return 1
    }
  fi

  # Create a new .xinitrc
  cat <<'EOF' > "$xinitrc_file"
#!/usr/local/bin/bash
exec i3
EOF
  chmod +x "$xinitrc_file" || {
    log "Failed to set execute permission on $xinitrc_file."
    return 1
  }
  log ".xinitrc created and configured to start i3 for user $user."

  # Start the SLiM service
  if service slim start; then
    log "SLiM service started successfully."
  else
    log "Failed to start SLiM service."
    return 1
  fi

  log "SLiM, Xorg, and i3 have been successfully enabled and configured for user $user."
}

# --------------------------------------
# SCRIPT EXECUTION
# --------------------------------------

check_root
log "Starting FreeBSD system configuration script."

# Main configuration steps
identify_primary_iface
bootstrap_and_install_pkgs
configure_rc_conf
configure_dns
configure_sudoers
set_default_shell_and_env
configure_ssh
configure_pf
finalize_configuration
configure_graphical_env

# Cleanup and successful exit
cleanup
log "FreeBSD system configuration completed successfully."
exit 0
