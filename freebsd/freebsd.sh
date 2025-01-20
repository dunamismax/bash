#!/usr/local/bin/bash
# =============================================================================
#                     FreeBSD System Configuration Script
# =============================================================================
#
# PURPOSE
# -------
# Automates the setup and hardening of a fresh FreeBSD installation with 
# security-focused defaults and essential development tools.
#
# FEATURES
# --------
# System Configuration:
#   • Updates system and package repositories
#   • Installs and configures core system utilities
#   • Implements security hardening measures
#   • Sets up logging and monitoring
#
# Security:
#   • Configures PF firewall with reasonable defaults
#   • Hardens SSH configuration
#   • Implements secure file permissions
#   • Sets up system auditing
#
# Development Environment:
#   • Installs development tools (Python, Go, Rust, Zig)
#   • Configures version control systems
#   • Sets up build environments
#   • Installs container tools
#
# PREREQUISITES
# ------------
# • Fresh FreeBSD 13.0+ installation
# • Root access or sudo privileges
# • Internet connectivity
# • Minimum 10GB free disk space
#
# USAGE
# -----
# 1. Review and adjust configuration variables:
#    USERNAME="sawyer"        # Primary user account
#    GITHUB_DIR="/home/${USERNAME}/github"
#    LOG_FILE="/var/log/freebsd_setup.log"
#    VERBOSE=2                # Logging detail (0=quiet, 1=normal, 2=debug)
#
# 2. Execute with root privileges:
#    # ./setup.sh             # As root
#    $ sudo ./setup.sh        # Via sudo
#
# LOGGING
# -------
# • All operations logged to /var/log/freebsd_setup.log
# • Log levels: INFO, WARN, ERROR, DEBUG
# • Console output controlled by VERBOSE setting
#
# ERROR HANDLING
# -------------
# • Strict error checking (set -euo pipefail)
# • Trapped errors with line number reporting
# • Automatic cleanup on script termination
# • Transaction logging for all operations
#
# RECOVERY
# --------
# • Configuration backups stored with .bak extension
# • Log file contains all executed operations
# • Safe to re-run on partial completion
#
# AUTHOR
# ------
# dunamismax <https://github.com/dunamismax>
#
# LICENSE
# -------
# MIT License
# Copyright (c) 2024 dunamismax
#
# =============================================================================

set -Eeuo pipefail

set -Eeuo pipefail

# Configuration
LOG_FILE="/var/log/freebsd_setup.log"
VERBOSE=2
USERNAME="sawyer"
GITHUB_DIR="/home/${USERNAME}/github"

# Check root
[[ $(id -u) -ne 0 ]] && { echo "Must run as root"; exit 1; }

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    
    # Colors - using declare -A for associative array
    declare -A colors
    colors=(
        [INFO]='\033[0;32m'
        [WARN]='\033[0;33m'
        [ERROR]='\033[0;31m'
        [DEBUG]='\033[0;34m'
    )
    local NC='\033[0m'
    
    [[ ! -e "$LOG_FILE" ]] && { mkdir -p "$(dirname "$LOG_FILE")"; touch "$LOG_FILE"; chmod 644 "$LOG_FILE"; }
    
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    [[ "$VERBOSE" -ge 2 ]] && printf "${colors[$level]:-$NC}[$timestamp] [$level] $message${NC}\n"
}

trap 'log ERROR "Script failed at line $LINENO"' ERR

install_pkgs() {
    local failed_packages=()
    local pkg_rc=0
    
    log INFO "Starting package installation process..."
    
    # Configure pkg for faster downloads
    local pkg_conf="/usr/local/etc/pkg.conf"
    if [[ -w "$pkg_conf" ]]; then
        log INFO "Optimizing pkg configuration..."
        sed -i '' -e 's/^#FETCH_RETRY = .*/FETCH_RETRY = 5/' \
                 -e 's/^#FETCH_TIMEOUT = .*/FETCH_TIMEOUT = 30/' \
                 -e 's/^#ASSUME_ALWAYS_YES = .*/ASSUME_ALWAYS_YES = true/' \
                 "$pkg_conf"
    fi
    
    # Update repository and upgrade existing packages
    log INFO "Updating package repository and upgrading existing packages..."
    if ! { pkg update -f && pkg upgrade -y; }; then
        log ERROR "Failed to update/upgrade packages"
        return 1
    fi
    
    # Define package groups
    declare -A PACKAGE_GROUPS
    PACKAGE_GROUPS=(
        ["Development tools"]="gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja meson gettext gmake valgrind doxygen ccache diffutils"
        ["Scripting and utilities"]="bash zsh fish nano screen tmate mosh htop iftop tree wget curl rsync unzip zip ca_root_nss sudo less neovim mc jq pigz fzf lynx smartmontools neofetch screenfetch ncdu dos2unix figlet toilet ripgrep"
        ["Libraries"]="libffi readline sqlite3 ncurses gdbm nss lzma libxml2"
        ["Networking tools"]="nmap netcat socat tcpdump wireshark aircrack-ng john hydra openvpn ipmitool bmon whois bind-tools"
        ["Languages"]="python39 go ruby perl5 rust"
        ["Containers"]="docker vagrant qemu"
        ["Web tools"]="nginx postgresql15-server postgresql15-client"
        ["Backup tools"]="rclone"
        ["Monitoring"]="syslog-ng grafana prometheus netdata"
        ["System tools"]="lsof bsdstats"
    )
    
    # Pre-fetch all packages in parallel
    log INFO "Pre-fetching packages..."
    local all_packages=""
    for group in "${!PACKAGE_GROUPS[@]}"; do
        all_packages+=" ${PACKAGE_GROUPS[$group]}"
    done
    pkg fetch -y ${all_packages} &>/dev/null &
    local fetch_pid=$!
    
    # Install packages by group
    local group package install_output
    for group in "${!PACKAGE_GROUPS[@]}"; do
        log INFO "Installing ${group}..."
        
        # Wait for pre-fetch to complete if it's still running
        if kill -0 $fetch_pid 2>/dev/null; then
            wait $fetch_pid
        fi
        
        # Install entire group at once
        if ! pkg install -y ${PACKAGE_GROUPS[$group]} >/dev/null 2>&1; then
            pkg_rc=$?
            log WARN "Group installation failed, falling back to individual installs for ${group}"
            
            # Fall back to individual installs for failed group
            for package in ${PACKAGE_GROUPS[$group]}; do
                log INFO "Installing package: ${package}"
                if ! pkg install -y "${package}" >/dev/null 2>&1; then
                    pkg_rc=$?
                    failed_packages+=("$package")
                    log WARN "Failed to install package: ${package} (exit code: ${pkg_rc})"
                fi
            done
        fi
    done
    
    # Clean up downloaded packages to free space
    pkg clean -y &>/dev/null
    
    # Report results
    if [ ${#failed_packages[@]} -eq 0 ]; then
        log INFO "All packages installed successfully"
        return 0
    else
        log ERROR "Failed to install the following packages:"
        printf '%s\n' "${failed_packages[@]}" | sed 's/^/  - /'
        log INFO "You can try installing these packages manually using: pkg install <package-name>"
        return 1
    fi
}

configure_ssh() {
    local config="/usr/local/etc/ssh/sshd_config"
    local service="sshd"
    local pkg="openssh-portable"
    local max_wait=30
    
    log INFO "Configuring SSH server..."

    # Install OpenSSH
    if ! pkg info "$pkg" >/dev/null 2>&1; then
        for ((i=1; i<=3; i++)); do
            log INFO "Installing OpenSSH (attempt $i/3)..."
            pkg install -y "$pkg" && break
            [[ $i < 3 ]] && sleep 5
        done
        [[ $i > 3 ]] && { log ERROR "OpenSSH install failed"; return 1; }
    fi

    # Setup directories and backup
    mkdir -p "/usr/local/etc/ssh" && chmod 755 "/usr/local/etc/ssh"
    [[ -f "$config" ]] && cp "$config" "${config}.bak.$(date +%Y%m%d%H%M%S)"

    # Generate config
    cat > "${config}.tmp" << 'EOF'
# SSH Server Configuration
Port 22
Protocol 2
AddressFamily any
ListenAddress 0.0.0.0

# Authentication
MaxAuthTries 3
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no
PubkeyAuthentication yes
AuthenticationMethods publickey

# Security
X11Forwarding no
AllowTcpForwarding no
PermitEmptyPasswords no
MaxSessions 2
LoginGraceTime 30

# Connection
ClientAliveInterval 300
ClientAliveCountMax 2
TCPKeepAlive yes

# Additional security measures
StrictModes yes
AllowAgentForwarding no
AllowStreamLocalForwarding no
GSSAPIAuthentication no
KerberosAuthentication no
HostbasedAuthentication no
IgnoreRhosts yes

# Logging
LogLevel VERBOSE
SyslogFacility AUTH
EOF

    # Apply configuration
    chmod 600 "${config}.tmp"
    mv "${config}.tmp" "$config"
    
    # Enable and start service
    sysrc "${service}_enable=YES"
    /usr/sbin/sshd -t -f "$config" || { log ERROR "Config test failed"; return 1; }
    service "$service" restart

    # Verify service
    for ((i=0; i<max_wait; i++)); do
        if service "$service" status >/dev/null 2>&1 && sockstat -4l | grep -q ":22"; then
            log INFO "SSH server running on port 22"
            return 0
        fi
        sleep 1
    done

    log ERROR "SSH service failed to start within ${max_wait}s"
    return 1
}

configure_pf() {
    local pf_conf="/etc/pf.conf"
    
    # Get external interface
    local ext_if=$(netstat -rn | grep '^default' | awk '{print $4}' | head -1)
    if [[ -z "$ext_if" ]]; then
        log ERROR "Could not detect external interface"
        return 1
    fi  # Fixed the extra curly brace here
    log INFO "Detected external interface: $ext_if"

    # Backup existing config if present
    if [[ -f "$pf_conf" ]]; then
        cp "$pf_conf" "${pf_conf}.bak.$(date +%Y%m%d)"
        log INFO "Created backup of existing PF configuration"
    fi

    # Generate simplified PF configuration
    cat > "$pf_conf" << EOF
# Interface
ext_if = "$ext_if"

# Options
set skip on lo0
set block-policy drop
set fingerprints "/etc/pf.os"

# Tables for blocking
table <bruteforce> persist
table <blacklist> persist

# Normalization
scrub in all fragment reassemble

# Default blocking
block in all
block out all

# Anti-spoofing
antispoof quick for \$ext_if inet

# Block known bad actors
block quick from <bruteforce>
block quick from <blacklist>

# Allow all outbound traffic
pass out quick on \$ext_if all keep state

# Allow inbound SSH with rate limiting
pass in on \$ext_if proto tcp to any port ssh \\
    keep state (max-src-conn 10, max-src-conn-rate 3/5, \\
    overload <bruteforce> flush global)

# Allow inbound HTTP/HTTPS
pass in on \$ext_if proto tcp to any port { http https } \\
    keep state (max-src-conn 100, max-src-conn-rate 15/5)

# Allow essential UDP services
pass in on \$ext_if proto udp to any port { domain ntp } keep state

# Allow ICMP for network diagnostics
pass in inet proto icmp icmp-type { echoreq unreach } keep state
EOF

    # Test configuration
    if ! pfctl -nf "$pf_conf"; then
        log ERROR "PF configuration test failed"
        return 1
    fi
    log INFO "PF configuration test passed"

    # Enable PF in rc.conf
    if ! sysrc pf_enable=YES; then
        log ERROR "Failed to enable PF in rc.conf"
        return 1
    fi  # Also fixed similar issue here

    log INFO "Enabled PF in rc.conf"

    # Load and activate the configuration
    if ! pfctl -ef "$pf_conf"; then
        log ERROR "Failed to load PF configuration"
        return 1
    fi
    log INFO "Successfully loaded and activated PF configuration"

    return 0
}

download_repos() {
    log INFO "Downloading repositories..."
    mkdir -p "$GITHUB_DIR"
    cd "$GITHUB_DIR" || exit 1
    
    local repos=("bash" "c" "religion" "windows" "hugo" "python")
    for repo in "${repos[@]}"; do
        [[ -d "$repo" ]] && rm -rf "$repo"
        git clone "https://github.com/dunamismax/${repo}.git"
    done
    
    # Set permissions
    chown -R www:www "${GITHUB_DIR}/hugo/dunamismax.com/public"
    chmod -R 755 "${GITHUB_DIR}/hugo/dunamismax.com/public"
    chown -R ${USERNAME}:${USERNAME} "$GITHUB_DIR"
}

fix_permissions() {
    local user_home="/home/${USERNAME}"
    local github_dir="${user_home}/github"
    local hugo_dir="${github_dir}/hugo"
    local hugo_public="${hugo_dir}/dunamismax.com/public"
    
    log INFO "Setting up permissions..."

    # Verify directories exist
    [[ ! -d "$github_dir" ]] && {
        log ERROR "GitHub directory not found: $github_dir"
        return 1
    }

    # Make shell scripts executable
    find "$github_dir" -type f -name "*.sh" -exec chmod +x {} \;

    # Set base ownership
    chown -R "${USERNAME}:${USERNAME}" "$user_home"
    chown -R "${USERNAME}:${USERNAME}" "$github_dir"

    # Set Hugo directory permissions
    if [[ -d "$hugo_dir" ]]; then
        # Hugo public directory
        chown -R www:www "$hugo_public"
        chmod -R 755 "$hugo_public"

        # Hugo main directory
        chown -R "${USERNAME}:${USERNAME}" "$hugo_dir"
        chmod o+rx "$user_home" "$github_dir" "$hugo_dir" "${hugo_dir}/dunamismax.com"
    fi

    # Set Git directory permissions
    find "$github_dir" -type d -name ".git" -print0 | while IFS= read -r -d '' git_dir; do
        log INFO "Securing Git directory: $git_dir"
        # Set strict permissions on .git directories
        chmod 700 "$git_dir"
        find "$git_dir" -type d -exec chmod 700 {} \;
        find "$git_dir" -type f -exec chmod 600 {} \;
    done

    log INFO "Permissions setup complete"
    return 0
}

setup_dotfiles() {
    # Base paths
    local user_home="/home/${USERNAME}"
    local dotfiles_dir="${user_home}/github/bash/dotfiles"
    local config_dir="${user_home}/.config"
    local local_dir="${user_home}/.local"
    
    log INFO "Setting up dotfiles..."

    # Verify source directory exists
    [[ ! -d "$dotfiles_dir" ]] && {
        log ERROR "Dotfiles directory not found: $dotfiles_dir"
        return 1
    }

    # Create necessary directories
    mkdir -p "$config_dir" "$local_dir/bin" || {
        log ERROR "Failed to create config directories"
        return 1
    }

    # Define files to copy (source:destination)
    local files=(
        "${dotfiles_dir}/.bash_profile:${user_home}/"
        "${dotfiles_dir}/.bashrc:${user_home}/"
        "${dotfiles_dir}/.profile:${user_home}/"
        "${dotfiles_dir}/Caddyfile:/usr/local/etc/"
    )

    # Define directories to copy (source:destination)
    local dirs=(
        "${dotfiles_dir}/bin:${local_dir}"
        "${dotfiles_dir}/alacritty:${config_dir}"
    )

    # Copy files
    for item in "${files[@]}"; do
        local src="${item%:*}"
        local dst="${item#*:}"
        if [[ -f "$src" ]]; then
            cp "$src" "$dst" || log WARN "Failed to copy: $src"
        else
            log WARN "Source file not found: $src"
        fi
    done

    # Copy directories
    for item in "${dirs[@]}"; do
        local src="${item%:*}"
        local dst="${item#*:}"
        if [[ -d "$src" ]]; then
            cp -r "$src" "$dst" || log WARN "Failed to copy: $src"
        else
            log WARN "Source directory not found: $src"
        fi
    done

    # Set permissions
    chown -R "${USERNAME}:${USERNAME}" "$user_home"
    chown "${USERNAME}:${USERNAME}" /usr/local/etc/Caddyfile 2>/dev/null

    log INFO "Dotfiles setup complete"
    return 0
}

finalize() {
    pkg upgrade -y
    log INFO "System information:"
    log INFO "Uptime: $(uptime)"
    log INFO "Disk Usage: $(df -h /)"
    log INFO "CPU Model: $(sysctl -n hw.model)"
    log INFO "Kernel: $(uname -r)"
}

main() {
    log INFO "Starting FreeBSD setup..."
    
    install_pkgs
    configure_ssh
    configure_pf
    download_repos
    fix_permissions
    setup_dotfiles
    finalize
    
    log INFO "Setup complete!"
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"