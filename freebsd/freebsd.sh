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
    if ! pkg update && pkg upgrade -y; then
        log ERROR "Failed to update/upgrade packages"
        return 1
    
    PACKAGES="\
        # Development tools
        gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja meson gettext \
        gmake valgrind doxygen ccache diffutils \
        \
        # Scripting and utilities
        bash zsh fish nano screen tmate mosh htop iftop \
        tree wget curl rsync unzip zip ca_root_nss sudo less neovim mc jq pigz fzf lynx \
        smartmontools neofetch screenfetch ncdu dos2unix figlet toilet ripgrep \
        \
        # Libraries for Python & C/C++ build
        libffi readline sqlite3 ncurses gdbm nss lzma libxml2 \
        \
        # Networking, system admin, and hacking utilities
        nmap netcat socat tcpdump wireshark aircrack-ng john hydra openvpn ipmitool bmon whois bind-tools \
        \
        # Languages and runtimes
        python39 go ruby perl5 rust \
        \
        # Containers and virtualization
        docker vagrant qemu \
        \
        # Web hosting tools
        nginx postgresql15-server postgresql15-client \
        \
        # File and backup management
        rclone \
        \
        # System monitoring and logging
        syslog-ng grafana prometheus netdata \
        \
        # Miscellaneous tools
        lsof bsdstats"

    if ! pkg install -y ${PACKAGES}; then
        log ERROR "Package installation failed"
        return 1
    }

    log INFO "Package installation completed successfully"
    return 0
}

configure_ssh() {
    local config="/usr/local/etc/ssh/sshd_config"
    local service="sshd"
    local pkg="openssh-portable"
    local max_wait=30
    local max_retries=3
    
    log INFO "Starting SSH server configuration..."

    # Install OpenSSH if needed
    if ! pkg info "$pkg" >/dev/null 2>&1; then
        local retry=0
        while [ $retry -lt $max_retries ]; do
            retry=$((retry + 1))
            log INFO "Installing OpenSSH (attempt $retry/$max_retries)"
            
            if pkg install -y "$pkg"; then
                log INFO "OpenSSH installed successfully"
                break
            fi
            
            if [ $retry -eq $max_retries ]; then
                log ERROR "Failed to install OpenSSH after $max_retries attempts"
                return 1
            fi
            
            log WARN "Installation failed, retrying in 5 seconds..."
            sleep 5
        done
    fi

    # Setup SSH directory
    log INFO "Creating SSH configuration directory"
    if ! mkdir -p "/usr/local/etc/ssh"; then
        log ERROR "Failed to create SSH directory"
        return 1
    fi
    
    if ! chmod 755 "/usr/local/etc/ssh"; then
        log ERROR "Failed to set SSH directory permissions"
        return 1
    fi

    # Backup existing config
    if [ -f "$config" ]; then
        local backup="${config}.bak.$(date +%Y%m%d%H%M%S)"
        log INFO "Backing up existing configuration to $backup"
        if ! cp "$config" "$backup"; then
            log ERROR "Failed to backup existing SSH config"
            return 1
        fi
    fi

    # Generate new config
    log INFO "Generating new SSH configuration"
    if ! cat > "${config}.tmp" << 'EOF'
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
    then
        log ERROR "Failed to write SSH configuration"
        return 1
    fi

    # Set config permissions and move to final location
    log INFO "Applying configuration file permissions"
    if ! chmod 600 "${config}.tmp"; then
        log ERROR "Failed to set config file permissions"
        rm -f "${config}.tmp"
        return 1
    fi

    if ! mv "${config}.tmp" "$config"; then
        log ERROR "Failed to move config file to final location"
        rm -f "${config}.tmp"
        return 1
    fi
    
    # Enable SSH service
    log INFO "Enabling SSH service"
    if ! sysrc "${service}_enable=YES"; then
        log ERROR "Failed to enable SSH service"
        return 1
    fi

    # Test configuration
    log INFO "Testing SSH configuration"
    if ! /usr/sbin/sshd -t -f "$config"; then
        log ERROR "SSH configuration test failed"
        return 1
    fi

    # Restart service
    log INFO "Restarting SSH service"
    if ! service "$service" restart; then
        log ERROR "Failed to restart SSH service"
        return 1
    }

    # Verify service is running
    log INFO "Verifying SSH service"
    local i=0
    while [ $i -lt $max_wait ]; do
        if service "$service" status >/dev/null 2>&1 && sockstat -4l | grep -q ":22"; then
            log INFO "SSH server successfully configured and running on port 22"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done

    log ERROR "SSH service failed to start within ${max_wait} seconds"
    return 1
}

configure_pf() {
    local pf_conf="/etc/pf.conf"
    local tables_dir="/etc/pf.tables"
    local ext_if
    
    log INFO "Starting PF firewall configuration..."
    
    # Get external interface
    log INFO "Detecting external interface..."
    ext_if=$(netstat -rn | awk '$1 == "default" {print $7; exit}')
    if [ -z "$ext_if" ]; then
        log ERROR "Failed to detect external interface - no default route found"
        return 1
    fi
    log INFO "Detected external interface: $ext_if"
    
    # Create and secure tables directory
    log INFO "Creating PF tables directory..."
    if ! mkdir -p "$tables_dir"; then
        log ERROR "Failed to create tables directory: $tables_dir"
        return 1
    fi
    
    if ! chmod 750 "$tables_dir"; then
        log ERROR "Failed to set permissions on tables directory"
        return 1
    fi
    
    # Initialize table files
    log INFO "Initializing PF table files..."
    for table in bruteforce flood scanners malware; do
        if ! touch "$tables_dir/$table"; then
            log ERROR "Failed to create table file: $table"
            return 1
        fi
        if ! chmod 600 "$tables_dir/$table"; then
            log ERROR "Failed to set permissions on table file: $table"
            return 1
        fi
        log INFO "Created and secured table: $table"
    done

    # Backup existing config
    if [ -f "$pf_conf" ]; then
        local backup="${pf_conf}.bak.$(date +%Y%m%d%H%M%S)"
        log INFO "Backing up existing PF configuration to: $backup"
        if ! cp "$pf_conf" "$backup"; then
            log ERROR "Failed to backup existing PF configuration"
            return 1
        fi
    fi

    # Generate temporary config file first
    local temp_conf="${pf_conf}.tmp"
    log INFO "Generating new PF configuration..."
    if ! cat > "$temp_conf" << EOF
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
pass in on \$ext_if inet proto tcp to any port ssh \\
    flags S/SA keep state \\
    (max-src-conn 5, max-src-conn-rate 3/60, overload <bruteforce> flush global)

pass in on \$ext_if inet proto tcp to any port \$tcp_services \\
    flags S/SA keep state \\
    (max-src-conn 100, max-src-conn-rate 15/5, overload <flood> flush global)

pass in on \$ext_if inet proto udp to any port \$udp_services keep state \\
    (max-src-states 100, max-src-conn-rate 10/5, overload <flood> flush global)

pass in inet proto icmp all icmp-type \$icmp_types keep state \\
    (max-src-conn-rate 10/10, overload <flood> flush global)

# Rate limiting for web traffic
pass in on \$ext_if proto tcp to port { http, https } \\
    flags S/SA keep state \\
    (max-src-conn 100, max-src-conn-rate 100/10, \\
     overload <flood> flush global)
EOF
    then
        log ERROR "Failed to generate PF configuration"
        rm -f "$temp_conf"
        return 1
    fi

    # Test configuration before applying
    log INFO "Testing PF configuration..."
    if ! pfctl -nf "$temp_conf"; then
        log ERROR "PF configuration validation failed"
        rm -f "$temp_conf"
        return 1
    fi

    # Move configuration to final location
    if ! mv "$temp_conf" "$pf_conf"; then
        log ERROR "Failed to move PF configuration to final location"
        rm -f "$temp_conf"
        return 1
    fi

    # Enable PF in rc.conf
    log INFO "Enabling PF in rc.conf..."
    if ! sysrc pf_enable=YES; then
        log ERROR "Failed to enable PF in rc.conf"
        return 1
    fi

    # Enable and load PF
    log INFO "Enabling and loading PF..."
    if ! pfctl -e; then
        log ERROR "Failed to enable PF"
        return 1
    fi

    if ! pfctl -f "$pf_conf"; then
        log ERROR "Failed to load PF configuration"
        return 1
    fi

    # Verify PF is running
    log INFO "Verifying PF status..."
    if ! pfctl -si | grep -q "Status: Enabled"; then
        log ERROR "PF verification failed - service not running"
        return 1
    fi

    log INFO "PF firewall configuration completed successfully"
    return 0
}

download_repos() {
    local max_retries=3
    local retry_delay=5
    
    log INFO "Starting repository downloads..."
    
    # Create GitHub directory
    if ! mkdir -p "$GITHUB_DIR"; then
        log ERROR "Failed to create directory: $GITHUB_DIR"
        return 1
    fi
    
    if ! cd "$GITHUB_DIR"; then
        log ERROR "Failed to change to directory: $GITHUB_DIR"
        return 1
    }
    
    # Use POSIX-compatible string for repos
    local repos="bash c religion windows hugo python"
    
    for repo in $repos; do
        log INFO "Processing repository: $repo"
        
        # Remove existing directory if present
        if [ -d "$repo" ]; then
            log INFO "Removing existing repository: $repo"
            if ! rm -rf "$repo"; then
                log ERROR "Failed to remove existing repository: $repo"
                return 1
            fi
        fi
        
        # Clone with retries
        local attempt=1
        while [ $attempt -le $max_retries ]; do
            log INFO "Cloning $repo (attempt $attempt/$max_retries)"
            if git clone --quiet "https://github.com/dunamismax/${repo}.git"; then
                log INFO "Successfully cloned: $repo"
                break
            fi
            
            attempt=$((attempt + 1))
            if [ $attempt -le $max_retries ]; then
                log WARN "Clone failed, retrying in $retry_delay seconds..."
                sleep $retry_delay
            else
                log ERROR "Failed to clone repository after $max_retries attempts: $repo"
                return 1
            fi
        done
    done
    
    # Set permissions
    log INFO "Setting up repository permissions..."
    
    local hugo_public="${GITHUB_DIR}/hugo/dunamismax.com/public"
    if [ -d "$hugo_public" ]; then
        if ! chown -R www:www "$hugo_public"; then
            log ERROR "Failed to set ownership on Hugo public directory"
            return 1
        fi
        if ! chmod -R 755 "$hugo_public"; then
            log ERROR "Failed to set permissions on Hugo public directory"
            return 1
        fi
    else
        log WARN "Hugo public directory not found: $hugo_public"
    fi
    
    if ! chown -R "${USERNAME}:${USERNAME}" "$GITHUB_DIR"; then
        log ERROR "Failed to set ownership on GitHub directory"
        return 1
    fi
    
    log INFO "Repository downloads and permissions completed successfully"
    return 0
}

fix_permissions() {
    local user_home="/home/${USERNAME}"
    local github_dir="${user_home}/github"
    local hugo_dir="${github_dir}/hugo"
    local hugo_public="${hugo_dir}/dunamismax.com/public"
    
    log INFO "Starting permissions setup..."

    # Verify directories exist
    if [ ! -d "$github_dir" ]; then
        log ERROR "GitHub directory not found: $github_dir"
        return 1
    }

    # Make shell scripts executable
    log INFO "Setting shell script permissions..."
    if ! find "$github_dir" -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null; then
        log WARN "Some shell scripts could not be made executable"
    fi

    # Set base ownership
    log INFO "Setting base directory ownership..."
    if ! chown -R "${USERNAME}:${USERNAME}" "$user_home"; then
        log ERROR "Failed to set user home directory ownership"
        return 1
    fi
    
    if ! chown -R "${USERNAME}:${USERNAME}" "$github_dir"; then
        log ERROR "Failed to set GitHub directory ownership"
        return 1
    }

    # Set Hugo directory permissions if it exists
    if [ -d "$hugo_dir" ]; then
        log INFO "Setting Hugo directory permissions..."
        
        # Hugo public directory
        if [ -d "$hugo_public" ]; then
            if ! chown -R www:www "$hugo_public"; then
                log ERROR "Failed to set Hugo public directory ownership"
                return 1
            fi
            if ! chmod -R 755 "$hugo_public"; then
                log ERROR "Failed to set Hugo public directory permissions"
                return 1
            fi
        else
            log WARN "Hugo public directory not found: $hugo_public"
        fi

        # Hugo main directory
        if ! chown -R "${USERNAME}:${USERNAME}" "$hugo_dir"; then
            log ERROR "Failed to set Hugo directory ownership"
            return 1
        fi
        
        local dirs="$user_home $github_dir $hugo_dir ${hugo_dir}/dunamismax.com"
        for dir in $dirs; do
            if [ -d "$dir" ]; then
                if ! chmod o+rx "$dir"; then
                    log ERROR "Failed to set read/execute permissions on: $dir"
                    return 1
                fi
            else
                log WARN "Directory not found: $dir"
            fi
        done
    fi

    # Set Git directory permissions
    log INFO "Securing Git directories..."
    find "$github_dir" -type d -name ".git" -print0 | while IFS= read -r -d '' git_dir; do
        log INFO "Securing Git directory: $git_dir"
        
        if ! chmod 700 "$git_dir"; then
            log ERROR "Failed to set Git directory permissions: $git_dir"
            return 1
        fi
        
        if ! find "$git_dir" -type d -exec chmod 700 {} \; 2>/dev/null; then
            log ERROR "Failed to set Git subdirectory permissions: $git_dir"
            return 1
        fi
        
        if ! find "$git_dir" -type f -exec chmod 600 {} \; 2>/dev/null; then
            log ERROR "Failed to set Git file permissions: $git_dir"
            return 1
        fi
    done

    log INFO "Permissions setup completed successfully"
    return 0
}

install_zig() {
    local version="0.14.0-dev.2847+db8ed730e"
    local install_dir="/usr/local/zig"
    local tarball="/tmp/zig.tar.xz"
    local url="https://ziglang.org/builds/zig-linux-x86_64-${version}.tar.xz"
    local max_retries=3
    
    log INFO "Starting Zig installation..."
    
    # Check if already installed
    if command -v zig >/dev/null 2>&1; then
        log INFO "Zig is already installed"
        return 0
    fi
    
    # Download with retries
    log INFO "Downloading Zig from: $url"
    local attempt=1
    while [ $attempt -le $max_retries ]; do
        if curl -L --fail "$url" -o "$tarball"; then
            log INFO "Download successful"
            break
        fi
        
        attempt=$((attempt + 1))
        if [ $attempt -le $max_retries ]; then
            log WARN "Download failed, attempt $attempt of $max_retries..."
            sleep 5
        else
            log ERROR "Failed to download Zig after $max_retries attempts"
            rm -f "$tarball"
            return 1
        fi
    done
    
    # Get extraction directory name
    log INFO "Preparing for extraction..."
    local extracted_dir
    extracted_dir="/tmp/$(tar -tf "$tarball" | head -1 | cut -f1 -d"/")" || {
        log ERROR "Failed to determine extraction directory"
        rm -f "$tarball"
        return 1
    }
    
    # Extract archive
    log INFO "Extracting Zig archive..."
    if ! tar xf "$tarball" -C /tmp/; then
        log ERROR "Failed to extract Zig archive"
        rm -f "$tarball"
        return 1
    fi
    
    # Verify extraction succeeded
    if [ ! -d "$extracted_dir" ]; then
        log ERROR "Extraction directory not found: $extracted_dir"
        rm -f "$tarball"
        return 1
    }
    
    # Install to final location
    log INFO "Installing Zig to: $install_dir"
    if [ -d "$install_dir" ]; then
        log INFO "Removing existing installation..."
        if ! rm -rf "$install_dir"; then
            log ERROR "Failed to remove existing Zig installation"
            rm -f "$tarball"
            return 1
        fi
    fi
    
    if ! mv "$extracted_dir" "$install_dir"; then
        log ERROR "Failed to move Zig to installation directory"
        rm -f "$tarball"
        rm -rf "$extracted_dir"
        return 1
    fi
    
    # Create symlink
    log INFO "Creating symlink..."
    if ! ln -sf "$install_dir/zig" /usr/local/bin/zig; then
        log ERROR "Failed to create Zig symlink"
        return 1
    fi
    
    if ! chmod +x /usr/local/bin/zig; then
        log ERROR "Failed to make Zig executable"
        return 1
    fi
    
    # Cleanup
    log INFO "Cleaning up temporary files..."
    rm -f "$tarball"
    
    # Verify installation
    if ! command -v zig >/dev/null 2>&1; then
        log ERROR "Zig installation verification failed"
        return 1
    fi
    
    log INFO "Zig installation completed successfully"
    return 0
}

setup_dotfiles() {
    local user_home="/home/${USERNAME}"
    local dotfiles_dir="${user_home}/github/bash/dotfiles"
    local config_dir="${user_home}/.config"
    local local_dir="${user_home}/.local"
    
    log INFO "Starting dotfiles setup..."

    # Verify source directory
    if [ ! -d "$dotfiles_dir" ]; then
        log ERROR "Dotfiles directory not found: $dotfiles_dir"
        return 1
    fi

    # Create directories
    log INFO "Creating configuration directories..."
    for dir in "$config_dir" "$local_dir/bin"; do
        if ! mkdir -p "$dir"; then
            log ERROR "Failed to create directory: $dir"
            return 1
        fi
    done

    # Define files using POSIX-compatible format
    local files="
        .bash_profile:${user_home}/
        .bashrc:${user_home}/
        .profile:${user_home}/
        Caddyfile:/usr/local/etc/"
    
    local dirs="
        bin:${local_dir}
        alacritty:${config_dir}"

    # Copy files
    log INFO "Copying dotfiles..."
    echo "$files" | while IFS=: read -r src_file dst_dir; do
        # Skip empty lines
        [ -z "$src_file" ] && continue
        
        src_file="$(echo "$src_file" | tr -d ' ')"
        dst_dir="$(echo "$dst_dir" | tr -d ' ')"
        
        local full_src="${dotfiles_dir}/${src_file}"
        if [ -f "$full_src" ]; then
            log INFO "Copying file: $src_file"
            if ! cp "$full_src" "$dst_dir"; then
                log ERROR "Failed to copy: $full_src to $dst_dir"
                return 1
            fi
        else
            log WARN "Source file not found: $full_src"
        fi
    done

    # Copy directories
    log INFO "Copying configuration directories..."
    echo "$dirs" | while IFS=: read -r src_dir dst_base; do
        # Skip empty lines
        [ -z "$src_dir" ] && continue
        
        src_dir="$(echo "$src_dir" | tr -d ' ')"
        dst_base="$(echo "$dst_base" | tr -d ' ')"
        
        local full_src="${dotfiles_dir}/${src_dir}"
        if [ -d "$full_src" ]; then
            log INFO "Copying directory: $src_dir"
            if ! cp -r "$full_src" "$dst_base"; then
                log ERROR "Failed to copy directory: $full_src to $dst_base"
                return 1
            fi
        else
            log WARN "Source directory not found: $full_src"
        fi
    done

    # Set permissions
    log INFO "Setting file permissions..."
    if ! chown -R "${USERNAME}:${USERNAME}" "$user_home"; then
        log ERROR "Failed to set ownership on user home directory"
        return 1
    fi

    # Set Caddyfile permissions (non-critical)
    if [ -f "/usr/local/etc/Caddyfile" ]; then
        if ! chown "${USERNAME}:${USERNAME}" /usr/local/etc/Caddyfile 2>/dev/null; then
            log WARN "Failed to set Caddyfile ownership"
        fi
    fi

    log INFO "Dotfiles setup completed successfully"
    return 0
}

finalize() {
    local log_file="/var/log/freebsd_setup_final.log"
    
    log INFO "Starting system finalization..."
    
    # Change to home directory
    if ! cd /home/${USERNAME}; then
        log WARN "Could not change to home directory"
    fi
    
    # Package upgrade
    log INFO "Upgrading installed packages..."
    if ! pkg upgrade -y; then
        log ERROR "Package upgrade failed"
        # Continue execution as this is not critical
    fi
    
    # System information collection
    log INFO "Collecting system information..."
    
    # Uptime check
    local uptime
    if ! uptime=$(uptime 2>/dev/null); then
        log WARN "Could not retrieve system uptime"
        uptime="Unknown"
    fi
    log INFO "System Uptime: $uptime"
    
    # Disk usage check
    local disk_usage
    if ! disk_usage=$(df -h / 2>/dev/null | tail -1); then
        log WARN "Could not retrieve disk usage"
        disk_usage="Unknown"
    fi
    log INFO "Disk Usage (root): $disk_usage"
    
    # Memory usage
    log INFO "Memory Usage Information:"
    if ! vmstat -s >> "$log_file" 2>/dev/null; then
        log WARN "Could not retrieve memory statistics"
    fi
    
    # CPU information
    local cpu_model
    if ! cpu_model=$(sysctl -n hw.model 2>/dev/null); then
        log WARN "Could not retrieve CPU model"
        cpu_model="Unknown"
    fi
    log INFO "CPU Model: $cpu_model"
    
    # Kernel version
    local kernel_version
    if ! kernel_version=$(uname -r 2>/dev/null); then
        log WARN "Could not retrieve kernel version"
        kernel_version="Unknown"
    fi
    log INFO "Kernel Version: $kernel_version"
    
    # Network configuration
    log INFO "Network Configuration:"
    if ! ifconfig -a >> "$log_file" 2>/dev/null; then
        log WARN "Could not retrieve network configuration"
    fi
    
    # Service status check
    log INFO "Checking critical services..."
    local services="sshd pf nginx postgresql"
    for service in $services; do
        if service "$service" status >/dev/null 2>&1; then
            log INFO "Service $service is running"
        else
            log WARN "Service $service is not running"
        fi
    done
    
    log INFO "System finalization completed"
}

main() {
    log INFO "Starting FreeBSD system setup..."
    
    local setup_steps=(
        "install_pkgs"
        "configure_ssh"
        "configure_pf"
        "install_zig"
        "download_repos"
        "fix_permissions"
        "setup_dotfiles"
        "finalize"
    )
    
    for step in "${setup_steps[@]}"; do
        log INFO "Starting step: $step"
        if ! "$step"; then
            log ERROR "Setup failed at step: $step"
            return 1
        fi
        log INFO "Completed step: $step"
    done
    
    log INFO "FreeBSD system setup completed successfully!"
    return 0
}

# Script entry point with error handling
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if ! main "$@"; then
        log ERROR "Setup script failed"
        exit 1
    fi
    exit 0
fi