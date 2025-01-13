#!/usr/local/bin/bash
#===============================================================================
# FreeBSD Automated System Configuration Script
#===============================================================================
# This script configures a FreeBSD installation with the following steps:
#
#   1) Bootstraps and updates the pkg system, then installs essential packages.
#   2) Identifies the primary network adapter and stores it in PRIMARY_IFACE.
#   3) Backs up and overwrites the following config files with known-good contents:
#         • /etc/pf.conf
#         • /etc/rc.conf
#         • /etc/resolv.conf
#         • /etc/ssh/sshd_config
#      while replacing "hn0" and "${primary_iface}" (where needed) with the detected interface.
#   4) Grants sudo privileges to the hard-coded user "sawyer."
#   5) Sets Bash as the default shell for "sawyer" and configures ~/.bashrc + ~/.bash_profile.
#   6) Performs final tasks (pkg upgrade, cache cleanup, enables Plex).
#
# Notes:
#   • Logs are appended to /var/log/freebsd_setup.log.
#   • This script does not exit on failures (no error handling or traps).
#   • Run as root on a fresh FreeBSD install or from a snapshot to repeatedly test.
#===============================================================================

# --------------------------------------
# CONFIGURATION
# --------------------------------------
LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
PRIMARY_IFACE=""    # Will be detected automatically, if possible

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
# OVERWRITE /etc/pf.conf
# --------------------------------------
overwrite_pf_conf() {
  log "Backing up and overwriting /etc/pf.conf with known-good contents."

  local pf_conf="/etc/pf.conf"
  if [ -f "$pf_conf" ]; then
    mv "$pf_conf" "${pf_conf}.bak"
    log "Backed up existing $pf_conf to ${pf_conf}.bak"
  fi

  # Write the known-good file
  cat <<'EOF' > "$pf_conf"
# /etc/pf.conf - Minimal pf ruleset

# Skip filtering on the loopback interface
set skip on lo0

# Normalize and scrub incoming packets
scrub in all

# Block all inbound traffic by default
block in all

# Allow all outbound traffic, keeping stateful connections
pass out all keep state

# Allow incoming SSH connections on your primary interface hn0
pass in quick on hn0 proto tcp to port 22 keep state

# Allow PlexMediaServer traffic
pass in quick on ${primary_iface} proto tcp to port 32400 keep state
pass in quick on ${primary_iface} proto udp to port 32400 keep state
EOF

  # If the script successfully identified the interface, replace "hn0" and "${primary_iface}"
  if [ -n "$PRIMARY_IFACE" ]; then
    # Replace hn0 with actual interface
    sed -i '' "s/hn0/$PRIMARY_IFACE/g" "$pf_conf"
    # Replace ${primary_iface} with actual interface
    sed -i '' "s/\${primary_iface}/$PRIMARY_IFACE/g" "$pf_conf"
    log "Replaced 'hn0' and '\${primary_iface}' with $PRIMARY_IFACE in /etc/pf.conf."
  else
    log "PRIMARY_IFACE is empty. /etc/pf.conf references hn0 or \${primary_iface} unchanged."
  fi

  log "Completed overwriting /etc/pf.conf."
}

# --------------------------------------
# OVERWRITE /etc/rc.conf
# --------------------------------------
overwrite_rc_conf() {
  log "Backing up and overwriting /etc/rc.conf with known-good contents."

  local rc_conf="/etc/rc.conf"
  if [ -f "$rc_conf" ]; then
    mv "$rc_conf" "${rc_conf}.bak"
    log "Backed up existing $rc_conf to ${rc_conf}.bak"
  fi

  # Write the known-good file
  cat <<'EOF' > "$rc_conf"
clear_tmp_enable="YES"
hostname="freebsd"
ifconfig_hn0="DHCP"
local_unbound_enable="NO"
sshd_enable="YES"
moused_enable="NO"
ntpd_enable="YES"
powerd_enable="YES"
# Set dumpdev to "AUTO" to enable crash dumps, "NO" to disable
dumpdev="AUTO"
zfs_enable="YES"
pf_enable="YES"
pf_rules="/etc/pf.conf"
pflog_enable="YES"
EOF

  # If the script successfully identified the interface, replace "hn0" with the actual interface
  if [ -n "$PRIMARY_IFACE" ]; then
    sed -i '' "s/hn0/$PRIMARY_IFACE/g" "$rc_conf"
    log "Replaced 'hn0' with $PRIMARY_IFACE in /etc/rc.conf."
  else
    log "PRIMARY_IFACE is empty. 'hn0' in /etc/rc.conf remains unchanged."
  fi

  log "Completed overwriting /etc/rc.conf."
}

# --------------------------------------
# OVERWRITE /etc/resolv.conf
# --------------------------------------
overwrite_resolv_conf() {
  log "Backing up and overwriting /etc/resolv.conf with known-good contents."

  local resolv_conf="/etc/resolv.conf"
  if [ -f "$resolv_conf" ]; then
    mv "$resolv_conf" "${resolv_conf}.bak"
    log "Backed up existing $resolv_conf to ${resolv_conf}.bak"
  fi

  cat <<'EOF' > "$resolv_conf"
# Generated by resolvconf

nameserver 1.1.1.1
nameserver 9.9.9.9

nameserver 127.0.0.1
options edns0
EOF

  log "Completed overwriting /etc/resolv.conf."
}

# --------------------------------------
# OVERWRITE /etc/ssh/sshd_config
# --------------------------------------
overwrite_sshd_config() {
  log "Backing up and overwriting /etc/ssh/sshd_config with known-good contents."

  local sshd_config="/etc/ssh/sshd_config"
  if [ -f "$sshd_config" ]; then
    mv "$sshd_config" "${sshd_config}.bak"
    log "Backed up existing $sshd_config to ${sshd_config}.bak"
  fi

  cat <<'EOF' > "$sshd_config"
#       $OpenBSD: sshd_config,v 1.104 2021/07/02 05:11:21 dtucker Exp $

# This is the sshd server system-wide configuration file.  See
# sshd_config(5) for more information.

# This sshd was compiled with PATH=/usr/bin:/bin:/usr/sbin:/sbin

# The strategy used for options in the default sshd_config shipped with
# OpenSSH is to specify options with their default value where
# possible, but leave them commented.  Uncommented options override the
# default value.

# Note that some of FreeBSD's defaults differ from OpenBSD's, and
# FreeBSD has a few additional options.

Port 22
AddressFamily any
ListenAddress 0.0.0.0
#ListenAddress ::

#HostKey /etc/ssh/ssh_host_rsa_key
#HostKey /etc/ssh/ssh_host_ecdsa_key
#HostKey /etc/ssh/ssh_host_ed25519_key

# Ciphers and keying
#RekeyLimit default none

# Logging
#SyslogFacility AUTH
#LogLevel INFO

# Authentication:

#LoginGraceTime 2m
PermitRootLogin no
#StrictModes yes
MaxAuthTries 6
MaxSessions 10

#PubkeyAuthentication yes

# The default is to check both .ssh/authorized_keys and .ssh/authorized_keys2
# but this is overridden so installations will only check .ssh/authorized_keys
AuthorizedKeysFile      .ssh/authorized_keys

#AuthorizedPrincipalsFile none

#AuthorizedKeysCommand none
#AuthorizedKeysCommandUser nobody

# For this to work you will also need host keys in /etc/ssh/ssh_known_hosts
#HostbasedAuthentication no
# Change to yes if you don't trust ~/.ssh/known_hosts for
# HostbasedAuthentication
#IgnoreUserKnownHosts no
# Don't read the user's ~/.rhosts and ~/.shosts files
IgnoreRhosts yes

# Change to yes to enable built-in password authentication.
# Note that passwords may also be accepted via KbdInteractiveAuthentication.
PasswordAuthentication yes
#PermitEmptyPasswords no

# Change to no to disable PAM authentication
KbdInteractiveAuthentication no

# Kerberos options
#KerberosAuthentication no
#KerberosOrLocalPasswd yes
#KerberosTicketCleanup yes
#KerberosGetAFSToken no

# GSSAPI options
#GSSAPIAuthentication no
#GSSAPICleanupCredentials yes

# Set this to 'no' to disable PAM authentication, account processing,
# and session processing. If this is enabled, PAM authentication will
# be allowed through the KbdInteractiveAuthentication and
# PasswordAuthentication.  Depending on your PAM configuration,
# PAM authentication via KbdInteractiveAuthentication may bypass
# the setting of "PermitRootLogin prohibit-password".
# If you just want the PAM account and session checks to run without
# PAM authentication, then enable this but set PasswordAuthentication
# and KbdInteractiveAuthentication to 'no'.
UsePAM no

#AllowAgentForwarding yes
#AllowTcpForwarding yes
#GatewayPorts no
#X11Forwarding no
#X11DisplayOffset 10
#X11UseLocalhost yes
PermitTTY yes
#PrintMotd yes
#PrintLastLog yes
#TCPKeepAlive yes
#PermitUserEnvironment no
#Compression delayed
ClientAliveInterval 300
ClientAliveCountMax 3
#UseDNS yes
#PidFile /var/run/sshd.pid
#MaxStartups 10:30:100
#PermitTunnel no
#ChrootDirectory none
#UseBlacklist no
#VersionAddendum FreeBSD-20240806

# no default banner path
#Banner none

# override default of no subsystems
Subsystem       sftp    /usr/libexec/sftp-server

# Example of overriding settings on a per-user basis
#Match User anoncvs
#       X11Forwarding no
#       AllowTcpForwarding no
#       PermitTTY no
#       ForceCommand cvs server
EOF

  # Fix ownership and permissions
  chown root:wheel "$sshd_config"
  chmod 644 "$sshd_config"

  log "Completed overwriting /etc/ssh/sshd_config. Restarting sshd..."
  service sshd restart >> "$LOG_FILE" 2>&1
}

# --------------------------------------
# CONFIGURE SUDO FOR $USERNAME
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
    log "Wheel group rule already exists in sudoers."
  fi

  pw usermod "$USERNAME" -G wheel >> "$LOG_FILE" 2>&1
  log "User $USERNAME added to wheel group (if not already)."
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
log "Starting FreeBSD system configuration."

# 1. Identify the primary network interface
identify_primary_iface

# 2. Bootstrap pkg + install packages
bootstrap_and_install_pkgs

# 3. Overwrite key config files
overwrite_pf_conf
overwrite_rc_conf
overwrite_resolv_conf
overwrite_sshd_config

# 4. Configure sudo for $USERNAME
configure_sudoers

# 5. Set Bash as default shell for $USERNAME
set_default_shell_and_env

# 6. Finalize config (upgrade, clean, enable Plex)
finalize_configuration

log "Configuration script finished."
exit 0