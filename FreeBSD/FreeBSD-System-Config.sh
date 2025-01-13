#!/usr/local/bin/bash
#===============================================================================
# FreeBSD Automated System Configuration Script (Refactored)
#===============================================================================
# This script configures a FreeBSD installation following simplified requirements:
#
#   • Bootstraps and updates the pkg system, then installs a collection of
#     essential packages for system management, development, and utilities.
#   • Identifies the primary network adapter for DHCP configuration (if possible).
#   • Configures system settings in /etc/rc.conf.
#   • Updates DNS settings ( /etc/resolv.conf ) with default or custom nameservers.
#   • Grants sudo privileges to the hard-coded user "sawyer".
#   • Sets Bash as the default shell for "sawyer" and configures environment files.
#   • Hardens SSH configuration by disabling root login and limiting auth attempts.
#   • Sets up and enables the PF firewall with simple SSH rate-limiting.
#   • Performs package upgrades, cleans caches, and enables configured services.
#
# Logging:
#   • All output is appended directly to the log file.
#   • No error handling or traps are present—this script does not exit on failures.
#
# Usage:
#   • Run as root on a fresh FreeBSD install to bootstrap and configure the system.
#   • Modify variables as needed to suit your environment.
#
#===============================================================================

# --------------------------------------
# CONFIGURATION
# --------------------------------------

LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"  # Hard-coded username
PRIMARY_IFACE=""   # Will be detected automatically, if possible

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
  # Virtualization and VM Support
  "qemu" "libvirt" "virt-manager" "vm-bhyve" "bhyve-firmware" "grub2-bhyve"
)

# --------------------------------------
# LOGGING (simplified)
# --------------------------------------
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

# --------------------------------------
# IDENTIFY PRIMARY NETWORK INTERFACE
# --------------------------------------
identify_primary_iface() {
  log "Identifying primary network adapter..."

  # Attempt to determine the primary interface using 'route'
  if command -v route >/dev/null; then
    PRIMARY_IFACE=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -n "$PRIMARY_IFACE" ]; then
      log "Primary network adapter found using 'route': $PRIMARY_IFACE"
      return
    fi
    log "Failed to identify with 'route'. Trying netstat..."
  fi

  # Fallback: netstat
  if command -v netstat >/dev/null; then
    PRIMARY_IFACE=$(netstat -rn | awk '/^default/ {print $NF}' | head -n 1)
    if [ -n "$PRIMARY_IFACE" ]; then
      log "Primary network adapter found using 'netstat': $PRIMARY_IFACE"
      return
    fi
    log "Failed to identify with 'netstat'. Trying ifconfig..."
  fi

  # Fallback: ifconfig
  local active_iface
  active_iface=$(ifconfig | awk '/status: active/{getline; print $1}' | head -n 1)
  if [ -n "$active_iface" ]; then
    PRIMARY_IFACE="$active_iface"
    log "Active network adapter found using 'ifconfig': $PRIMARY_IFACE"
    return
  fi

  # If all methods fail, leave PRIMARY_IFACE blank
  log "No primary network interface was detected."
}

# --------------------------------------
# BOOTSTRAP AND INSTALL PACKAGES
# --------------------------------------
bootstrap_and_install_pkgs() {
  log "Bootstrapping pkg and installing packages..."

  # If pkg is missing, bootstrap it
  if ! command -v pkg >/dev/null; then
    log "pkg not found. Bootstrapping pkg..."
    env ASSUME_ALWAYS_YES=yes pkg bootstrap >> "$LOG_FILE" 2>&1
    log "pkg bootstrap process finished."
  fi

  # Force-update the package database
  pkg update -f >> "$LOG_FILE" 2>&1
  log "pkg update -f completed."

  # Install packages
  for pkg in "${PACKAGES[@]}"; do
    if ! pkg info -q "$pkg"; then
      log "Installing package: $pkg"
      pkg install -y "$pkg" >> "$LOG_FILE" 2>&1
      log "Finished attempt to install $pkg"
    else
      log "Package $pkg is already installed."
    fi
  done

  log "Package installation process completed."
}

# --------------------------------------
# CONFIGURE /etc/rc.conf
# --------------------------------------
configure_rc_conf() {
  log "Configuring /etc/rc.conf..."
  local rc_conf="/etc/rc.conf"
  local hostname="freebsd"

  # Apply some common rc.conf settings
  sysrc clear_tmp_enable="YES"          >> "$LOG_FILE" 2>&1
  sysrc hostname="$hostname"            >> "$LOG_FILE" 2>&1
  sysrc local_unbound_enable="YES"      >> "$LOG_FILE" 2>&1
  sysrc sshd_enable="YES"               >> "$LOG_FILE" 2>&1
  sysrc moused_enable="NO"              >> "$LOG_FILE" 2>&1
  sysrc ntpd_enable="YES"               >> "$LOG_FILE" 2>&1
  sysrc powerd_enable="YES"             >> "$LOG_FILE" 2>&1
  sysrc dumpdev="AUTO"                  >> "$LOG_FILE" 2>&1
  sysrc zfs_enable="YES"                >> "$LOG_FILE" 2>&1

  # Configure the primary network interface for DHCP
  if [ -n "$PRIMARY_IFACE" ]; then
    sysrc ifconfig_"$PRIMARY_IFACE"="DHCP" >> "$LOG_FILE" 2>&1
    log "Set DHCP for $PRIMARY_IFACE in /etc/rc.conf."
  else
    log "No primary network interface set. Skipping interface config."
  fi

  log "/etc/rc.conf configuration complete."
}

# --------------------------------------
# CONFIGURE DNS
# --------------------------------------
configure_dns() {
  log "Configuring DNS..."
  local resolv_conf="/etc/resolv.conf"
  local nameservers=("1.1.1.1" "9.9.9.9")

  # Remove existing nameserver lines
  sed -i '' '/^\s*nameserver\s/d' "$resolv_conf" >> "$LOG_FILE" 2>&1

  for ns in "${nameservers[@]}"; do
    echo "nameserver $ns" >> "$resolv_conf"
    log "Added nameserver $ns to $resolv_conf"
  done

  log "DNS configuration complete."
}

# --------------------------------------
# CONFIGURE SUDOERS (for $USERNAME)
# --------------------------------------
configure_sudoers() {
  log "Configuring sudoers for $USERNAME..."
  local sudoers_file="/usr/local/etc/sudoers"
  local sudo_rule="%wheel ALL=(ALL) ALL"

  # Ensure wheel rule
  if ! grep -q "^%wheel" "$sudoers_file" 2>/dev/null; then
    echo "$sudo_rule" >> "$sudoers_file"
    log "Added wheel group rule to sudoers."
  else
    log "Wheel group rule exists in sudoers."
  fi

  # Add user to wheel group
  pw usermod "$USERNAME" -G wheel >> "$LOG_FILE" 2>&1
  log "User $USERNAME added to wheel (or already present)."
}

# --------------------------------------
# CONFIGURE SSH
# --------------------------------------
configure_ssh() {
  log "Configuring SSH..."
  local sshd_config="/etc/ssh/sshd_config"

  # Basic SSH settings
  sed -i '' 's/^#\?\s*Port .*/Port 22/'  "$sshd_config" >> "$LOG_FILE" 2>&1
  sed -i '' 's/^#\?\s*AddressFamily .*/AddressFamily any/' "$sshd_config" >> "$LOG_FILE" 2>&1
  sed -i '' 's/^#\?\s*ListenAddress .*/ListenAddress 0.0.0.0/' "$sshd_config" >> "$LOG_FILE" 2>&1
  sed -i '' 's/^#\?\s*MaxAuthTries .*/MaxAuthTries 6/' "$sshd_config" >> "$LOG_FILE" 2>&1
  sed -i '' 's/^#\?\s*MaxSessions .*/MaxSessions 10/' "$sshd_config" >> "$LOG_FILE" 2>&1
  sed -i '' 's/^#\?\s*PermitRootLogin .*/PermitRootLogin no/' "$sshd_config" >> "$LOG_FILE" 2>&1

  chown root:wheel "$sshd_config"
  chmod 644 "$sshd_config"

  service sshd restart >> "$LOG_FILE" 2>&1
  log "SSH configuration and restart complete."
}

# --------------------------------------
# CONFIGURE PF FIREWALL
# --------------------------------------
configure_pf() {
  log "Configuring PF firewall..."
  local pf_conf="/etc/pf.conf"

  # Write minimal pf.conf
  cat <<EOF > "$pf_conf"
# /etc/pf.conf - Minimal pf ruleset with SSH rate-limiting
set skip on lo0
set loginterface $PRIMARY_IFACE
scrub in all
block in log all
pass out on $PRIMARY_IFACE all keep state

# SSH rate-limiting
table <ssh_limited> persist
block in quick on $PRIMARY_IFACE proto tcp to port 22
pass in quick on $PRIMARY_IFACE proto tcp to port 22 keep state \
    (max-src-conn 10, max-src-conn-rate 15/5, overload <ssh_limited> flush global)

# Plex (example)
pass in quick on $PRIMARY_IFACE proto tcp to port 32400 keep state
pass in quick on $PRIMARY_IFACE proto udp to port 32400 keep state
EOF

  # Enable PF and declare rules
  sysrc pf_enable="YES"   >> "$LOG_FILE" 2>&1
  sysrc pf_rules="/etc/pf.conf" >> "$LOG_FILE" 2>&1
  service pf enable       >> "$LOG_FILE" 2>&1
  service pf restart      >> "$LOG_FILE" 2>&1

  log "PF firewall configuration complete."
}

# --------------------------------------
# SET BASH AS DEFAULT SHELL + ENV
# --------------------------------------
set_default_shell_and_env() {
  log "Setting Bash as default shell for $USERNAME..."
  local bash_path="/usr/local/bin/bash"

  # Ensure bash is in /etc/shells
  if ! grep -qx "$bash_path" /etc/shells; then
    echo "$bash_path" >> /etc/shells
    log "Added $bash_path to /etc/shells."
  fi

  # Change shell for $USERNAME
  chsh -s "$bash_path" "$USERNAME" >> "$LOG_FILE" 2>&1

  # Configure environment files in $USERNAME's home
  local user_home
  user_home=$(eval echo "~$USERNAME")
  local bashrc_file="$user_home/.bashrc"
  local bash_profile_file="$user_home/.bash_profile"

  # .bashrc
  cat <<'EOF' > "$bashrc_file"
#!/usr/local/bin/bash
# ~/.bashrc: executed by bash(1) for interactive shells.

case $- in
    *i*) ;;
    *) return ;;
esac

PS1='\[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ '
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

alias ls='ls -lah --color=auto'
alias grep='grep --color=auto'

export HISTCONTROL=ignoredups:erasedups
export HISTSIZE=1000
export HISTFILESIZE=2000
shopt -s histappend

export PAGER='less -R'
export LESS='-R'

if [ -f /usr/local/etc/bash_completion ]; then
    . /usr/local/etc/bash_completion
fi
EOF

  # .bash_profile
  cat <<'EOF' > "$bash_profile_file"
#!/usr/local/bin/bash
# ~/.bash_profile: executed by bash(1) for login shells.

if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
EOF

  chown "$USERNAME":"$USERNAME" "$bashrc_file" "$bash_profile_file"
  chmod 644 "$bashrc_file" "$bash_profile_file"

  log "Shell and environment configured for $USERNAME."
}

# --------------------------------------
# FINALIZE CONFIGURATION
# --------------------------------------
finalize_configuration() {
  log "Finalizing configuration (pkg upgrade, clean)..."

  pkg upgrade -y >> "$LOG_FILE" 2>&1
  pkg clean -y   >> "$LOG_FILE" 2>&1

  # Example: enable and start Plex
  sysrc plexmediaserver_enable="YES" >> "$LOG_FILE" 2>&1
  service plexmediaserver start      >> "$LOG_FILE" 2>&1

  log "Final configuration completed."
}

# --------------------------------------
# SCRIPT EXECUTION
# --------------------------------------
log "Starting FreeBSD system configuration (Refactored)."

# Identify primary network interface
identify_primary_iface

# Bootstrap pkg + install packages
bootstrap_and_install_pkgs

# Configure rc.conf
configure_rc_conf

# Configure DNS
configure_dns

# Configure sudoers for $USERNAME
configure_sudoers

# Set Bash as default for $USERNAME
set_default_shell_and_env

# SSH Hardening
configure_ssh

# PF Firewall
configure_pf

# Finalize with package upgrade and cleaning
finalize_configuration

log "Configuration script finished."
exit 0
