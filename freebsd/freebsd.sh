#!/usr/local/bin/bash
# FreeBSD Automated Setup Script
# Author: dunamismax | License: MIT

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
    
    # Colors
    local colors=([INFO]='\033[0;32m' [WARN]='\033[0;33m' [ERROR]='\033[0;31m' [DEBUG]='\033[0;34m')
    local NC='\033[0m'
    
    [[ ! -e "$LOG_FILE" ]] && { mkdir -p "$(dirname "$LOG_FILE")"; touch "$LOG_FILE"; chmod 644 "$LOG_FILE"; }
    
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    [[ "$VERBOSE" -ge 2 ]] && printf "${colors[$level]:-$NC}[$timestamp] [$level] $message${NC}\n"
}

trap 'log ERROR "Script failed at line $LINENO"' ERR

install_pkgs() {
    log INFO "Installing packages..."
    
    # Update and upgrade existing packages
    if ! pkg update && pkg upgrade -y; then
        log ERROR "Failed to update/upgrade packages"
        return 1
    fi

    # Define package list
    local PACKAGES=(
        # Development tools
        gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja meson gettext
        gmake valgrind doxygen ccache diffutils

        # Scripting and utilities
        bash zsh fish nano screen tmate mosh htop iftop
        tree wget curl rsync unzip zip ca_root_nss sudo less neovim mc jq pigz fzf lynx
        smartmontools neofetch screenfetch ncdu dos2unix figlet toilet ripgrep

        # Libraries for Python & C/C++ build
        libffi readline sqlite3 ncurses gdbm nss lzma libxml2

        # Networking and admin utilities
        nmap netcat socat tcpdump wireshark aircrack-ng john hydra openvpn ipmitool bmon whois bind-tools

        # Languages and runtimes
        python39 go ruby perl5 rust

        # Containers and virtualization
        docker vagrant qemu

        # Web hosting tools
        nginx postgresql15-server postgresql15-client

        # File and backup management
        rclone

        # System monitoring and logging
        syslog-ng grafana prometheus netdata

        # Miscellaneous tools
        lsof bsdstats
    )

    # Install packages
    if ! pkg install -y "${PACKAGES[@]}"; then
        log ERROR "Package installation failed"
        return 1
    fi

    log INFO "Package installation completed successfully"
    return 0
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
    local tables_dir="/etc/pf.tables"
    local ext_if
    
    log INFO "Configuring PF firewall..."
    
    # Get external interface
    ext_if=$(netstat -rn | awk '$1 == "default" {print $7; exit}') || {
        log ERROR "Failed to detect external interface"
        return 1
    }
    
    # Create and secure tables directory
    mkdir -p "$tables_dir" && chmod 750 "$tables_dir"
    
    # Initialize table files
    for table in bruteforce flood scanners malware; do
        touch "$tables_dir/$table"
        chmod 600 "$tables_dir/$table"
    done

    # Backup existing config
    [[ -f "$pf_conf" ]] && cp "$pf_conf" "${pf_conf}.bak.$(date +%Y%m%d%H%M%S)"

    # Generate PF configuration
    cat > "$pf_conf" << EOF
# PF Firewall Configuration - Generated $(date)
# Interface and Tables
ext_if = "$ext_if"
table <bruteforce> persist file "$tables_dir/bruteforce"
table <flood> persist file "$tables_dir/flood"
table <scanners> persist file "$tables_dir/scanners"
table <malware> persist file "$tables_dir/malware"

# Services
tcp_services = "{ ssh, http, https, smtp, imaps }"
udp_services = "{ domain, ntp }"
icmp_types = "{ echoreq, unreach }"

# Protected Networks
internal_net = "{ 10/8, 172.16/12, 192.168/16 }"

# Optimization
set limit { states 100000, frags 50000 }
set optimization aggressive
set block-policy drop
set fingerprints "/etc/pf.os"
set state-policy if-bound

# Security
scrub in on \$ext_if all fragment reassemble min-ttl 15 max-mss 1440
block in all
block out all
block quick from <bruteforce>
block quick from <flood>
block quick from <scanners>
block quick from <malware>

# Anti-spoofing
antispoof quick for \$ext_if inet

# Traffic Rules
pass out quick on \$ext_if all modulate state
pass in on \$ext_if inet proto tcp to any port ssh \
    flags S/SA keep state \
    (max-src-conn 5, max-src-conn-rate 3/60, overload <bruteforce> flush global)

pass in on \$ext_if inet proto tcp to any port \$tcp_services \
    flags S/SA keep state \
    (max-src-conn 100, max-src-conn-rate 15/5, overload <flood> flush global)

pass in on \$ext_if inet proto udp to any port \$udp_services keep state \
    (max-src-states 100, max-src-conn-rate 10/5, overload <flood> flush global)

pass in inet proto icmp all icmp-type \$icmp_types keep state \
    (max-src-conn-rate 10/10, overload <flood> flush global)
EOF

    # Test and apply configuration
    if ! pfctl -nf "$pf_conf"; then
        log ERROR "PF configuration validation failed"
        return 1
    fi

    # Enable PF in rc.conf if not already enabled
    sysrc pf_enable=YES

    # Enable and load PF
    pfctl -e && pfctl -f "$pf_conf" || {
        log ERROR "Failed to enable/load PF"
        return 1
    }

    # Verify PF is running
    if ! pfctl -si | grep -q "Status: Enabled"; then
        log ERROR "PF failed to start"
        return 1
    fi

    log INFO "PF firewall configured successfully"
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

install_zig() {
    local version="0.14.0-dev.2847+db8ed730e"
    local install_dir="/usr/local/zig"
    local tarball="/tmp/zig.tar.xz"
    local url="https://ziglang.org/builds/zig-linux-x86_64-${version}.tar.xz"
    
    log INFO "Installing Zig..."
    
    # Skip if already installed
    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig already installed"
        return 0
    fi
    
    # Download and extract
    curl -L "$url" -o "$tarball" || {
        log ERROR "Failed to download Zig"
        return 1
    }
    
    # Get extracted directory name and extract
    local extracted_dir="/tmp/$(tar -tf "$tarball" | head -1 | cut -f1 -d"/")"
    tar xf "$tarball" -C /tmp/ || {
        log ERROR "Failed to extract Zig"
        rm -f "$tarball"
        return 1
    }
    
    # Install
    rm -rf "$install_dir"
    mv "$extracted_dir" "$install_dir" || {
        log ERROR "Failed to install Zig"
        rm -f "$tarball"
        return 1
    }
    
    # Create symlink and set permissions
    ln -sf "$install_dir/zig" /usr/local/bin/zig
    chmod +x /usr/local/bin/zig
    
    # Cleanup
    rm -f "$tarball"
    
    log INFO "Zig installation complete"
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
    install_zig
    download_repos
    fix_permissions
    setup_dotfiles
    finalize
    
    log INFO "Setup complete!"
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"