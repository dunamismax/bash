#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# FreeBSD Automated System Configuration Script
# ------------------------------------------------------------------------------
# Description:
#   This script automates the configuration of a fresh FreeBSD installation by:
#       1) Bootstrapping and updating the pkg system, then installing essential
#          packages.
#       2) Detecting the primary network interface (stored in PRIMARY_IFACE).
#       3) Backing up and overwriting selected configuration files (/etc/pf.conf,
#          /etc/rc.conf, /etc/resolv.conf, /etc/ssh/sshd_config) with known-good
#          contents, substituting "hn0" and "${primary_iface}" with the detected
#          interface if applicable.
#       4) Granting sudo privileges to the user "sawyer" and configuring Bash
#          (as the default shell), ~/.bashrc, and ~/.bash_profile for that user.
#       5) Completing final tasks (e.g., pkg upgrade, cleaning caches, and
#          enabling Plex).
#       6) Installing and configuring GNOME with Wayland support.
#
# Notes:
#   • All log output is appended to /var/log/freebsd_setup.log.
#   • This script does not exit on individual failures. There is no robust
#     error handling or traps.
#   • Run as root on a new FreeBSD install or rollback snapshot for testing.
# ------------------------------------------------------------------------------

# --------------------------------------
# CONFIGURATION
# --------------------------------------

# Exit immediately if a command exits with a non-zero status,
# if any variable is unset, and if any command in a pipeline fails
set -euo pipefail

# Trap errors and execute handle_error
trap 'handle_error' ERR

# Variables
LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
PRIMARY_IFACE=""    # Will be detected automatically, if possible

PACKAGES=(
    # Essential Shells and Editors
    "vim" "bash" "zsh" "tmux" "mc" "nano" "fish" "screen"
    # Version Control and Scripting
    "git" "perl5" "lang/python"        # Install "lang/python" so "python" -> latest python3
    # Network and Internet Utilities
    "curl" "wget" "netcat" "tcpdump" "rsync" "rsnapshot"
    # System Monitoring and Management
    "htop" "sudo" "bash-completion" "zsh-completions" "neofetch" "tig" "bat" "exa"
    "fd" "jq" "iftop" "nmap" "tree" "fzf" "lynx" "curlie" "ncdu"
    "gcc" "lighttpd" "smartmontools"
    # Database and Media Services
    "plexmediaserver" "caddy" "go"
    # System Tools and Backup
    "duplicity" "ffmpeg" "restic" "syslog-ng"
    # Virtualization and VM Support
    "qemu" "libvirt" "virt-manager" "vm-bhyve" "bhyve-firmware" "grub2-bhyve"
)

# --------------------------------------
# FUNCTIONS
# --------------------------------------

# Function to log messages with timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

# Function to handle errors
handle_error() {
    log "An error occurred. Check the log for details."
    exit 1
}

# Function to identify the primary network interface
identify_primary_iface() {
    log "Identifying primary network adapter..."

    if command -v route >/dev/null 2>&1; then
        PRIMARY_IFACE=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
        if [ -n "$PRIMARY_IFACE" ]; then
            log "Primary network adapter found using 'route': $PRIMARY_IFACE"
            return
        fi
        log "Failed to identify with 'route'. Trying netstat..."
    fi

    if command -v netstat >/dev/null 2>&1; then
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

    log "No primary network interface was detected."
}

bootstrap_and_install_pkgs() {
    log "Bootstrapping pkg and installing packages..."

    if ! command -v pkg >/dev/null 2>&1; then
        log "pkg not found. Bootstrapping pkg..."
        env ASSUME_ALWAYS_YES=yes pkg bootstrap 2>&1 | tee -a "$LOG_FILE"
        log "pkg bootstrap process finished."
    fi

    # Force-update the package database
    pkg update -f 2>&1 | tee -a "$LOG_FILE"
    log "pkg update -f completed."

    # Gather packages not yet installed
    local packages_to_install=()
    for pkg in "${PACKAGES[@]}"; do
        if ! pkg info -q "$pkg"; then
            packages_to_install+=("$pkg")
        else
            log "Package $pkg is already installed."
        fi
    done

    # Install all missing packages in one batch if any
    if [ ${#packages_to_install[@]} -gt 0 ]; then
        log "Installing packages: ${packages_to_install[*]}"
        pkg install -y "${packages_to_install[@]}" 2>&1 | tee -a "$LOG_FILE"
    else
        log "All packages already installed. No action needed."
    fi

    log "Package installation process completed."
}

# Function to overwrite /etc/pf.conf
overwrite_pf_conf() {
    log "Backing up and overwriting /etc/pf.conf with known-good contents."

    local pf_conf="/etc/pf.conf"
    if [ -f "$pf_conf" ]; then
        mv "$pf_conf" "${pf_conf}.bak"
        log "Backed up existing $pf_conf to ${pf_conf}.bak"
    fi

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

    # Replace interface placeholders if we identified PRIMARY_IFACE
    if [ -n "$PRIMARY_IFACE" ]; then
        sed -i '' "s/hn0/$PRIMARY_IFACE/g" "$pf_conf"
        sed -i '' "s/\${primary_iface}/$PRIMARY_IFACE/g" "$pf_conf"
        log "Replaced 'hn0' and '\${primary_iface}' with $PRIMARY_IFACE in /etc/pf.conf."
    else
        log "PRIMARY_IFACE is empty; references to 'hn0' and '\${primary_iface}' remain unchanged."
    fi

    log "Completed overwriting /etc/pf.conf."
}

# Function to overwrite /etc/rc.conf
overwrite_rc_conf() {
    log "Backing up and overwriting /etc/rc.conf with known-good contents."

    local rc_conf="/etc/rc.conf"
    if [ -f "$rc_conf" ]; then
        mv "$rc_conf" "${rc_conf}.bak"
        log "Backed up existing $rc_conf to ${rc_conf}.bak"
    fi

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

    if [ -n "$PRIMARY_IFACE" ]; then
        sed -i '' "s/hn0/$PRIMARY_IFACE/g" "$rc_conf"
        log "Replaced 'hn0' with $PRIMARY_IFACE in /etc/rc.conf."
    else
        log "PRIMARY_IFACE is empty; 'hn0' remains unchanged in /etc/rc.conf."
    fi

    log "Completed overwriting /etc/rc.conf."
}

# Function to overwrite /etc/resolv.conf
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

# Function to overwrite /etc/ssh/sshd_config
overwrite_sshd_config() {
    log "Backing up and overwriting /etc/ssh/sshd_config with known-good contents."

    local sshd_config="/etc/ssh/sshd_config"
    if [ -f "$sshd_config" ]; then
        mv "$sshd_config" "${sshd_config}.bak"
        log "Backed up existing $sshd_config to ${sshd_config}.bak"
    fi

    cat <<'EOF' > "$sshd_config"
#       $OpenBSD: sshd_config,v 1.104 2021/07/02 05:11:21 dtucker Exp $
# This is the sshd server system-wide configuration file.

Port 22
AddressFamily any
ListenAddress 0.0.0.0
PermitRootLogin no
MaxAuthTries 6
MaxSessions 10
AuthorizedKeysFile      .ssh/authorized_keys
IgnoreRhosts yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
UsePAM no
PermitTTY yes
ClientAliveInterval 300
ClientAliveCountMax 3
Subsystem       sftp    /usr/libexec/sftp-server
EOF

    # Fix ownership and permissions
    chown root:wheel "$sshd_config"
    chmod 644 "$sshd_config"

    log "Completed overwriting /etc/ssh/sshd_config. Restarting sshd..."
    service sshd restart 2>&1 | tee -a "$LOG_FILE"
}

# Function to configure sudoers
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

    pw usermod "$USERNAME" -G wheel 2>&1 | tee -a "$LOG_FILE"
    log "User $USERNAME added to wheel group (if not already)."
}

# Function to set Bash as default shell and configure user env
set_default_shell_and_env() {
    log "Setting Bash as default shell for $USERNAME..."
    local bash_path="/usr/local/bin/bash"

    # Ensure bash is in /etc/shells
    if ! grep -qx "$bash_path" /etc/shells; then
        echo "$bash_path" >> /etc/shells
        log "Added $bash_path to /etc/shells."
    fi

    # Change shell for $USERNAME
    chsh -s "$bash_path" "$USERNAME" 2>&1 | tee -a "$LOG_FILE"

    # Configure environment files
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
# CONFIGURE VIRTUALIZATION
# --------------------------------------
configure_virtualization() {
    echo "[INFO] Configuring virtualization and bhyve..."

    # 1) Enable and start libvirtd
    sysrc libvirtd_enable=YES
    service libvirtd start

    # 2) Add your user to relevant groups for KVM, polkit, etc.
    pw groupmod operator -m "$USERNAME"

    # 3) Enable and configure vm-bhyve to use a standard directory instead of ZFS
    sysrc vm_enable=YES
    # Use a normal directory path, e.g. /vm
    sysrc vm_dir="/vm"

    # Create the directory if it doesn't already exist
    [ ! -d "/vm" ] && mkdir -p /vm

    # 4) Initialize vm-bhyve (create /vm/.config, /vm/.templates, etc.)
    echo "[INFO] Running vm init..."
    vm init

    echo "[INFO] Virtualization configuration complete."
}

# ------------------------------------------------------
# Configure and enable Caddy on FreeBSD
# ------------------------------------------------------
configure_caddy() {
    echo "[INFO] Enabling and configuring Caddy..."

    # 1) Enable Caddy at system startup
    sysrc caddy_enable="YES"

    # 2) Create/update the main config file at /usr/local/etc/caddy/Caddyfile
    [ ! -d /usr/local/etc/caddy ] && mkdir -p /usr/local/etc/caddy

    cat << 'EOF' > /usr/local/etc/caddy/Caddyfile
# The Caddyfile is an easy way to configure your Caddy web server.
#
# Unless the file starts with a global options block, the first
# uncommented line is always the address of your site.
#
# To use your own domain name (with automatic HTTPS), first make
# sure your domain's A/AAAA DNS records are properly pointed to
# this machine's public IP, then replace ":80" below with your
# domain name.

{
    # Use this email for Let's Encrypt notifications
    email dunamismax@tutamail.com

    # Global logging: captures all events (including errors during startup)
    log {
        output file /var/log/caddy/caddy.log
    }
}

# Redirect www to non-www
www.dunamismax.com {
    redir https://dunamismax.com{uri}
}

# Main website
dunamismax.com {
    # Serve the static files from your Hugo output folder
    root * /home/sawyer/GitHub/Hugo/dunamismax.com/public
    file_server

    # Deny hidden files (dotfiles like .git, .htaccess, etc.)
    @hiddenFiles {
        path_regexp hiddenFiles ^/\.
    }
    respond @hiddenFiles 404

    # Per-site logging: captures site-specific access and error logs
    log {
        output file /var/log/caddy/dunamismax_access.log
    }
}

# Nextcloud
cloud.dunamismax.com {
    reverse_proxy 127.0.0.1:8080
}

# Refer to the Caddy docs for more information:
# https://caddyserver.com/docs/caddyfile
EOF

    # 3) Optionally create the log directory if it doesn't exist
    [ ! -d /var/log/caddy ] && mkdir -p /var/log/caddy

    # 4) Start the Caddy service
    service caddy start

    echo "[INFO] Caddy has been enabled and started."
}

# Function to finalize configuration
finalize_configuration() {
    log "Finalizing configuration (pkg upgrade, clean)..."

    pkg upgrade -y 2>&1 | tee -a "$LOG_FILE"
    pkg clean -y   2>&1 | tee -a "$LOG_FILE"

    # Example: enable and start Plex
    sysrc plexmediaserver_enable="YES" 2>&1 | tee -a "$LOG_FILE"
    service plexmediaserver start 2>&1 | tee -a "$LOG_FILE"

    log "Final configuration completed."
}

# ------------------------------------------------------
# Configure GNOME and Wayland
# ------------------------------------------------------
configure_gnome_wayland() {
    log "Installing GNOME, Wayland, and related packages..."
    pkg install -y wayland xwayland gnome gnome-tweaks gnome-shell-extensions gnome-games gnome-system-monitor

    log "Enabling required services for GNOME..."
    sysrc gdm_enable="YES"
    sysrc gnome_enable="YES"
    sysrc dbus_enable="YES"
    sysrc hald_enable="YES"

    log "Configuring /etc/ttys for GDM..."
    # Replace or set ttyv8 line to run GDM
    if grep -q '^ttyv8' /etc/ttys; then
        sed -i '' 's|^ttyv8.*|ttyv8 "/usr/local/sbin/gdm" xterm on secure|' /etc/ttys
    else
        echo 'ttyv8 "/usr/local/sbin/gdm" xterm on secure' >> /etc/ttys
    fi

    log "Optional: Starting GNOME services now..."
    service dbus start
    service hald start
    service gdm start

    log "GNOME with Wayland setup complete. A reboot is recommended."
    log "After reboot, at the GDM login screen, click the gear icon and choose 'GNOME on Wayland'."
}

# --------------------------------------
# SCRIPT START
# --------------------------------------

# Ensure the log file exists and has appropriate permissions
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

log "--------------------------------------"
log "Starting FreeBSD Automated System Configuration Script"

# 1. Identify the primary network interface
identify_primary_iface

# 2. Bootstrap pkg + install packages
bootstrap_and_install_pkgs

# ------------------------------------------------
# 2a. Install and configure GNOME with Wayland
# ------------------------------------------------
configure_gnome_wayland

# 3. Overwrite key config files
overwrite_pf_conf
overwrite_rc_conf
overwrite_resolv_conf
overwrite_sshd_config

# 4. Configure sudo for $USERNAME
configure_sudoers

# 5. Set Bash as default shell for $USERNAME
set_default_shell_and_env

# 6. Configure and enable Virtualization
configure_virtualization

# 7 Configure and enable Caddy
configure_caddy

# 8. Finalize config (upgrade, clean, enable Plex)
finalize_configuration

log "Configuration script finished successfully."
log "--------------------------------------"
exit 0