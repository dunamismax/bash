#!/usr/bin/env bash
################################################################################
# Fedora Automated Setup & Hardening Script
#
# Description:
#   This script fully automates the configuration of a fresh Fedora server,
#   creating a secure, optimized, and personalized environment suitable for
#   headless deployments.
#
# Author : sawyer (adapted for Fedora)
# License: MIT
################################################################################

# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?"' ERR

# Log file path
LOG_FILE="/var/log/fedora_setup.log"

# Default username to configure
USERNAME="sawyer"

# -------------------------------------------------------------------------------
# Essential Package List (CLI-only environment, Fedora)
# -------------------------------------------------------------------------------
PACKAGES=(
    # Shells & Terminal Multiplexers
    bash zsh fish vim nano emacs mc neovim screen tmux

    # Development & Build Tools
    gcc gcc-c++ make cmake meson intltool gettext pigz libtool pkg-config 
    bzip2 xz git hugo

    # System & Network Services
    openssh-server acpid chrony fail2ban sudo bash-completion logrotate 
    net-tools firewalld

    # Virtualization & Containers
    qemu-kvm libvirt-daemon virt-install bridge-utils podman podman-compose

    # Networking & Hardware Tools
    curl wget tcpdump rsync nmap lynx bind-utils iftop mtr iw rfkill 
    nc socat speedtest-cli

    # Monitoring & Diagnostics
    htop neofetch tig jq vnstat tree fzf which smartmontools lsof dstat 
    sysstat iotop inotify-tools pv nethogs strace ltrace atop

    # Filesystem & Disk Utilities
    gdisk ntfs-3g ncdu unzip zip parted lvm2 btrfs-progs

    # Scripting & Productivity Tools
    perl patch bc gawk expect

    # Code Navigation & Developer Tools
    fd-find bat ripgrep hyperfine

    # Multimedia & Backup Applications
    ffmpeg restic mpv

    # Terminal Enhancements
    byobu ranger nnn

    # Communication & Productivity
    mutt newsboat irssi weechat httpie yt-dlp thefuck

    # Task & Calendar Management
    task calcurse

    # Fun & Miscellaneous
    cowsay figlet
)

# Color definitions (Nord Theme)
RED='\033[38;2;191;97;106m'
YELLOW='\033[38;2;235;203;139m'
GREEN='\033[38;2;163;190;140m'
BLUE='\033[38;2;94;129;172m'
CYAN='\033[38;2;136;192;208m'
MAGENTA='\033[38;2;180;142;173m'
GRAY='\033[38;2;216;222;233m'
NC='\033[0m'

# ==============================================================================
# 2. UTILITY & LOGGING FUNCTIONS
# ==============================================================================
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO)    color="${GREEN}" ;;
        WARN|WARNING) color="${YELLOW}" ;;
        ERROR)   color="${RED}" ;;
        DEBUG)   color="${BLUE}" ;;
        *)       color="${NC}" ;;
    esac
    local log_entry="[$timestamp] [$level] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "%b%s%b\n" "$color" "$log_entry" "$NC" >&2
}

warn() {
    log WARN "$@"
}

handle_error() {
    local error_message="${1:-"An error occurred. See the log for details."}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    exit "$exit_code"
}

# ==============================================================================
# 3. SYSTEM PREPARATION FUNCTIONS
# ==============================================================================
ensure_user() {
    if id "$USERNAME" &>/dev/null; then
        log INFO "User '$USERNAME' already exists."
    else
        log INFO "Creating user and group '$USERNAME'..."
        useradd -m -s /bin/bash "$USERNAME" || handle_error "Failed to create user $USERNAME"
        log INFO "User '$USERNAME' created successfully."
    fi
}

check_network() {
    if ! ping -c 1 google.com &>/dev/null; then
        handle_error "No network connectivity. Please check your network settings."
    else
        log INFO "Network connectivity verified."
    fi
}

update_system() {
    log INFO "Refreshing repositories and updating system..."
    dnf check-update || true
    dnf upgrade -y || handle_error "Failed to upgrade packages"
    log INFO "System update completed successfully."
}

# ==============================================================================
# 4. CORE CONFIGURATION FUNCTIONS
# ==============================================================================
configure_ssh() {
    log INFO "Configuring OpenSSH Server..."
    if ! rpm -q openssh-server &>/dev/null; then
        dnf install -y openssh-server || handle_error "Failed to install OpenSSH Server"
    fi

    systemctl enable --now sshd || handle_error "Failed to enable/start SSH service"

    local sshd_config="/etc/ssh/sshd_config"
    local backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup sshd_config"

    declare -A ssh_settings=(
        ["Port"]="22"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="no"
        ["Protocol"]="2"
        ["MaxAuthTries"]="4"
    )
    for key in "${!ssh_settings[@]}"; do
        if grep -q "^${key} " "$sshd_config"; then
            sed -i "s/^${key} .*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done

    systemctl restart sshd || handle_error "Failed to restart SSH service"
    log INFO "SSH configuration updated successfully."
}

install_packages() {
    log INFO "Installing essential packages..."
    dnf install -y epel-release || handle_error "Failed to install EPEL repository"
    
    # Enable RPM Fusion repositories
    dnf install -y \
        https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
        https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm \
        || warn "Failed to install RPM Fusion repositories"

    for pkg in "${PACKAGES[@]}"; do
        if ! rpm -q "$pkg" &>/dev/null; then
            dnf install -y "$pkg" || warn "Failed to install package: $pkg"
        else
            log INFO "Package $pkg is already installed."
        fi
    done
}

configure_firewall() {
    log INFO "Configuring firewalld..."
    
    if ! systemctl is-active --quiet firewalld; then
        systemctl enable --now firewalld || handle_error "Failed to enable/start firewalld"
    fi

    # Set default zone to public
    firewall-cmd --set-default-zone=public || warn "Failed to set default zone"

    # Add basic services
    local services=("ssh" "http" "https")
    for service in "${services[@]}"; do
        firewall-cmd --permanent --add-service="$service" || warn "Failed to add service: $service"
    done

    # Add custom port for Plex
    firewall-cmd --permanent --add-port=32400/tcp || warn "Failed to add Plex port"

    firewall-cmd --reload || warn "Failed to reload firewall configuration"
    log INFO "Firewall configuration completed."
}

configure_selinux() {
    log INFO "Configuring SELinux..."
    
    # Install SELinux utilities
    dnf install -y policycoreutils policycoreutils-python-utils setools-console \
        || handle_error "Failed to install SELinux utilities"

    # Set SELinux to enforcing mode
    setenforce 1 || warn "Failed to set SELinux to enforcing mode"
    sed -i 's/^SELINUX=.*/SELINUX=enforcing/' /etc/selinux/config \
        || warn "Failed to update SELinux config"

    log INFO "SELinux configuration completed."
}

install_docker() {
    log INFO "Installing Podman (Docker alternative for Fedora)..."
    dnf install -y podman podman-compose || handle_error "Failed to install Podman"
    
    # Create docker compatibility symlink
    ln -sf /usr/bin/podman /usr/bin/docker || warn "Failed to create Docker compatibility symlink"
    
    # Add user to podman group
    usermod -aG podman "$USERNAME" || warn "Failed to add $USERNAME to podman group"
    
    log INFO "Podman installation and configuration completed."
}

release_ports() {
    log INFO "Releasing occupied network ports..."
    local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
    local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")
    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on TCP port $port: $pids"
            kill -9 $pids || warn "Failed to kill processes on TCP port $port"
        fi
    done
    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log INFO "Killing processes on UDP port $port: $pids"
            kill -9 $pids || warn "Failed to kill processes on UDP port $port"
        fi
    done
    log INFO "Port release process completed."
}

configure_fail2ban() {
    log INFO "Installing and configuring fail2ban..."
    if ! rpm -q fail2ban &>/dev/null; then
        dnf install -y fail2ban || handle_error "Failed to install fail2ban"
    fi

    # Create a custom jail configuration
    cat <<EOF >/etc/fail2ban/jail.local
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
maxretry = 3
EOF

    systemctl enable --now fail2ban || handle_error "Failed to enable/start fail2ban"
    log INFO "fail2ban configured successfully."
}

configure_journald() {
    log INFO "Configuring systemd journal for persistent logging..."
    mkdir -p /var/log/journal || handle_error "Failed to create /var/log/journal directory"
    
    # Set storage to persistent
    sed -i 's/#Storage=auto/Storage=persistent/' /etc/systemd/journald.conf

    # Set reasonable size limits
    cat <<EOF >>/etc/systemd/journald.conf
SystemMaxUse=1G
SystemKeepFree=1G
EOF

    systemctl restart systemd-journald || warn "Failed to restart systemd-journald"
    log INFO "Persistent journaling is now configured."
}

install_build_dependencies() {
    log INFO "Installing build dependencies..."
    local deps=(
        gcc gcc-c++ make cmake git curl wget vim tmux unzip zip
        ca-certificates redhat-lsb-core gnupg2 jq pkgconfig
        openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel
        sqlite-devel tk-devel ncurses-devel gdbm-devel xz-devel gdb llvm
    )
    dnf install -y "${deps[@]}" || handle_error "Failed to install build dependencies"

    log INFO "Installing Rust toolchain..."
    if ! command -v rustc &>/dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || handle_error "Rust toolchain installation failed"
        export PATH="$HOME/.cargo/bin:$PATH"
    fi

    log INFO "Installing Go..."
    dnf install -y golang || handle_error "Failed to install Go"
    
    log INFO "Build dependencies installed successfully."
}

install_caddy() {
    log INFO "Installing Caddy web server..."
    if ! rpm -q caddy &>/dev/null; then
        # Add Caddy repository
        dnf copr enable -y @caddy/caddy || handle_error "Failed to enable Caddy repository"
        dnf install -y caddy || handle_error "Failed to install Caddy"
    fi
    
    systemctl enable --now caddy || warn "Failed to enable/start Caddy service"
    log INFO "Caddy web server installed successfully."
}

install_plex() {
    log INFO "Installing Plex Media Server..."

    if rpm -q plexmediaserver &>/dev/null; then
        log INFO "Plex Media Server is already installed."
        return
    fi

    # Add Plex repository
    cat <<EOF >/etc/yum.repos.d/plex.repo
[PlexRepo]
name=Plex Repository
baseurl=https://downloads.plex.tv/repo/rpm/\$basearch/
enabled=1
gpgkey=https://downloads.plex.tv/plex-keys/PlexSign.key
gpgcheck=1
EOF

    dnf install -y plexmediaserver || handle_error "Failed to install Plex Media Server"

    # Create plex group if it doesn't exist
    if ! getent group plex &>/dev/null; then
        groupadd plex || handle_error "Failed to create plex group"
    fi

    # Create plex user if it doesn't exist
    if ! id plex &>/dev/null; then
        useradd -r -g plex -d /var/lib/plexmediaserver -s /sbin/nologin plex || handle_error "Failed to create plex user"
    fi

    # Set up directories and permissions
    if [ -d /var/lib/plexmediaserver ]; then
        chown -R plex:plex /var/lib/plexmediaserver || warn "Failed to change ownership for /var/lib/plexmediaserver"
        chmod g+w /var/lib/plexmediaserver || warn "Failed to add group write permission to /var/lib/plexmediaserver"
    fi

    # Configure SELinux for Plex
    setsebool -P domain_can_mmap_files 1 || warn "Failed to set SELinux boolean for Plex"

    # Enable and start Plex service
    systemctl enable --now plexmediaserver || warn "Failed to enable/start Plex Media Server service"

    log INFO "Plex Media Server installed and configured successfully."
}

install_and_mount_zfs() {
    local pool_name="WD_BLACK"
    local mount_point="/media/WD_BLACK"

    log INFO "Starting ZFS installation and mount procedure for pool ${pool_name}..."

    # Install ZFS repository
    if ! rpm -q zfs-fuse &>/dev/null; then
        dnf install -y https://zfsonlinux.org/fedora/zfs-release-2-1$(rpm --eval "%{dist}").noarch.rpm || handle_error "Failed to install ZFS repository"
        dnf install -y zfs || handle_error "Failed to install ZFS packages"
    fi

    # Load ZFS kernel module
    if ! lsmod | grep -q "^zfs"; then
        modprobe zfs || handle_error "Failed to load ZFS kernel module"
    fi

    # Enable ZFS services
    systemctl enable --now zfs-import-cache zfs-import.target zfs-mount || warn "Failed to enable ZFS services"

    # Import pool if not already imported
    if ! zpool list 2>/dev/null | grep -q "^${pool_name}"; then
        zpool import "${pool_name}" || handle_error "Failed to import ZFS pool ${pool_name}"
    fi

    # Set mountpoint
    local current_mount
    current_mount=$(zfs get -H -o value mountpoint "${pool_name}")
    if [[ "$current_mount" != "$mount_point" ]]; then
        zfs set mountpoint="${mount_point}" "${pool_name}" || handle_error "Failed to set mountpoint for ${pool_name}"
    fi

    # Mount pool if not already mounted
    if ! zfs mount | grep -q "^${pool_name}"; then
        zfs mount "${pool_name}" || handle_error "Failed to mount ZFS pool ${pool_name}"
    fi

    log INFO "ZFS pool ${pool_name} is now mounted at ${mount_point}."
}

setup_repos_and_dotfiles() {
    log INFO "Setting up GitHub repositories and dotfiles..."
    local GITHUB_DIR="/home/${USERNAME}/github"
    local USER_HOME="/home/${USERNAME}"

    mkdir -p "$GITHUB_DIR" || handle_error "Failed to create GitHub directory: $GITHUB_DIR"
    cd "$GITHUB_DIR" || handle_error "Failed to change directory to $GITHUB_DIR"

    local repos=("bash" "windows" "web" "python" "go" "misc")
    for repo in "${repos[@]}"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        local repo_url="https://github.com/dunamismax/${repo}.git"
        rm -rf "$repo_dir" 2>/dev/null
        git clone "$repo_url" "$repo_dir" || handle_error "Failed to clone repository: $repo"
        log INFO "Cloned repository: $repo"
    done

    # Set ownership and permissions
    chown -R "${USERNAME}:${USERNAME}" "$GITHUB_DIR" || warn "Failed to set ownership for GitHub directory"

    # Set up dotfiles
    local dotfiles_dir="${USER_HOME}/github/bash/linux/dotfiles"
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    local config_dir="${USER_HOME}/.config"
    local local_bin_dir="${USER_HOME}/.local/bin"
    mkdir -p "$config_dir" "$local_bin_dir" || handle_error "Failed to create config directories"

    # Copy dotfiles
    for file in .bashrc .profile .fehbg; do
        cp "${dotfiles_dir}/${file}" "${USER_HOME}/${file}" || warn "Failed to copy ${file}"
    done

    # Set up Caddy configuration
    if [[ -f "${dotfiles_dir}/Caddyfile" ]]; then
        cp "${dotfiles_dir}/Caddyfile" /etc/caddy/Caddyfile || handle_error "Failed to copy Caddyfile"
        chown caddy:caddy /etc/caddy/Caddyfile || handle_error "Failed to set ownership for Caddyfile"
    fi

    # Set permissions
    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME"
    chmod -R u=rwX,g=rX,o=rX "$local_bin_dir"

    log INFO "Repositories and dotfiles setup completed successfully."
}

enable_dunamismax_services() {
    log INFO "Enabling DunamisMax website services..."

    # Create service files with SELinux context
    cat <<EOF >/etc/systemd/system/dunamismax-ai-agents.service
[Unit]
Description=DunamisMax AI Agents Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/ai_agents
Environment="PATH=/home/${USERNAME}/github/web/ai_agents/.venv/bin"
EnvironmentFile=/home/${USERNAME}/github/web/ai_agents/.env
ExecStart=/home/${USERNAME}/github/web/ai_agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200
Restart=always
SELinuxContext=system_u:system_r:dunamismax_t:s0

[Install]
WantedBy=multi-user.target
EOF

    # Similar services with SELinux context...
    [Additional service definitions would go here]

    # Reload systemd and enable services
    systemctl daemon-reload
    
    local services=(
        "dunamismax-ai-agents"
        "dunamismax-files"
        "dunamismax-messenger"
        "dunamismax-notes"
        "dunamismax"
    )

    for service in "${services[@]}"; do
        systemctl enable "$service.service" || warn "Failed to enable $service"
    done

    # Create SELinux policy module for services
    cat <<EOF >dunamismax.te
module dunamismax 1.0;

require {
    type httpd_t;
    type unreserved_port_t;
    class tcp_socket name_bind;
}

allow httpd_t unreserved_port_t:tcp_socket name_bind;
EOF

    checkmodule -M -m -o dunamismax.mod dunamismax.te || warn "Failed to compile SELinux module"
    semodule_package -o dunamismax.pp -m dunamismax.mod || warn "Failed to package SELinux module"
    semodule -i dunamismax.pp || warn "Failed to install SELinux module"

    log INFO "DunamisMax services enabled with SELinux policies."
}

configure_automatic_updates() {
    log INFO "Configuring automatic system updates via systemd timer..."
    
    # Install dnf-automatic
    dnf install -y dnf-automatic || handle_error "Failed to install dnf-automatic"

    # Configure automatic updates
    sed -i 's/^apply_updates.*/apply_updates = yes/' /etc/dnf/automatic.conf

    # Enable and start the timer
    systemctl enable --now dnf-automatic.timer || warn "Could not enable automatic update timer"

    log INFO "Automatic updates configured via dnf-automatic."
}

system_hardening() {
    log INFO "Applying additional system hardening..."
    
    # Apply sysctl hardening
    cat <<EOF >/etc/sysctl.d/99-hardening.conf
# Disable packet forwarding
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Disable ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Enable TCP SYN cookies
net.ipv4.tcp_syncookies = 1

# Enable reverse path filtering
net.ipv4.conf.all.rp_filter = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Additional Fedora-specific hardening
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
net.ipv4.conf.all.log_martians = 1
EOF
    sysctl --system || warn "Failed to reload sysctl settings"

    # Configure crypto policies
    update-crypto-policies --set DEFAULT:NO-SHA1 || warn "Failed to update crypto policies"

    log INFO "System hardening applied."
}

cleanup_system() {
    log INFO "Cleaning up system..."
    
    # Clean DNF cache
    dnf clean all || warn "Failed to clean DNF cache"
    
    # Remove temporary files
    rm -rf /tmp/* /var/tmp/* || warn "Failed to clean temporary files"
    
    log INFO "System cleanup completed."
}

# ==============================================================================
# 8. MAIN EXECUTION FLOW
# ==============================================================================
main() {
    # Ensure log directory exists
    local log_dir
    log_dir=$(dirname "$LOG_FILE")
    mkdir -p "$log_dir" || handle_error "Failed to create log directory: $log_dir"
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE"

    log INFO "======================================"
    log INFO "Starting Fedora Automated Setup Script"
    log INFO "======================================"

    if [[ $(id -u) -ne 0 ]]; then
        handle_error "This script must be run as root. Please use sudo."
    fi

    check_network
    update_system
    ensure_user
    configure_ssh
    install_packages
    configure_firewall
    configure_selinux
    install_docker
    release_ports
    configure_fail2ban
    configure_journald
    install_build_dependencies
    #install_caddy
    #install_plex
    #install_and_mount_zfs
    setup_repos_and_dotfiles
    #enable_dunamismax_services
    configure_automatic_updates
    system_hardening
    cleanup_system
    finalize_configuration

    log INFO "Fedora system setup completed successfully."
    prompt_reboot
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi