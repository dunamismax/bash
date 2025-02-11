#!/usr/bin/env bash
################################################################################
# Arch Linux Automated Setup & Hardening Script
#
# Description:
#   This script fully automates the configuration of a fresh Arch Linux server,
#   creating a secure, optimized, and personalized environment suitable for
#   headless deployments. Key features include:
#
#     • System Preparation:
#         - Network connectivity verification
#         - Full system update and package manager configuration
#
#     • Package Installation:
#         - Comprehensive package installation from core/community
#         - Development tools and programming language support
#
#     • Security Enhancements:
#         - SSH server hardening
#         - Firewalld configuration with zone management
#         - Fail2ban deployment with custom jails
#         - Kernel parameter tuning via sysctl
#         - Secure journald configuration
#
#     • Containerization & Services:
#         - Docker and Docker Compose installation
#         - Custom service deployment for web applications
#         - ZFS filesystem support
#
#     • Automation & Maintenance:
#         - Systemd timer for automatic updates
#         - Resource monitoring and log management
#
# Usage:
#   Run as root after fresh Arch install. Internet connection required.
#
# Author: sawyer (adapted for Arch Linux)
# License: MIT
################################################################################

# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?"' ERR

LOG_FILE="/var/log/arch_setup.log"
USERNAME="sawyer"

# -------------------------------------------------------------------------------
# Package List (Core/Community)
# -------------------------------------------------------------------------------
CORE_PACKAGES=(
  base base-devel linux linux-firmware grub efibootmgr intel-ucode amd-ucode
  networkmanager openssh firewalld fail2ban zsh fish tmux neovim git
  docker docker-compose qemu libvirt virt-manager dnsmasq bridge-utils
  htop neofetch jq rsync tree fzf lsof smartmontools sysstat iotop
  inotify-tools strace nmap tcpdump wget curl rsync openssl-1.1
)

# -------------------------------------------------------------------------------
# Nord Color Theme
# -------------------------------------------------------------------------------
RED='\033[38;2;191;97;106m'
YELLOW='\033[38;2;235;203;139m'
GREEN='\033[38;2;163;190;140m'
BLUE='\033[38;2;94;129;172m'
CYAN='\033[38;2;136;192;208m'
MAGENTA='\033[38;2;180;142;173m'
GRAY='\033[38;2;216;222;233m'
NC='\033[0m'

# ==============================================================================
# 2. UTILITY FUNCTIONS
# ==============================================================================
log() {
    local level="${1:-INFO}" message="$2" timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local color
    case "${level^^}" in
        INFO) color="${GREEN}" ;;
        WARN) color="${YELLOW}" ;;
        ERROR) color="${RED}" ;;
        *) color="${NC}" ;;
    esac
    echo -e "${color}[${timestamp}] [${level^^}] ${message}${NC}" >&2
    echo "[${timestamp}] [${level^^}] ${message}" >> "$LOG_FILE"
}

handle_error() {
    local msg="$1" code="${2:-1}"
    log ERROR "$msg"
    exit "$code"
}

# ==============================================================================
# 3. SYSTEM PREPARATION
# ==============================================================================
init_arch() {
    log INFO "Initializing Arch Linux system"
    
    # Verify boot mode
    [[ -d /sys/firmware/efi/efivars ]] || handle_error "UEFI mode required"
    
    # Network check
    if ! ping -c 1 archlinux.org &>/dev/null; then
        log WARN "Network not available, starting NetworkManager"
        systemctl start NetworkManager && nmcli device connect eth0
        sleep 5
    fi

    # Update keyring first
    pacman -Sy --noconfirm archlinux-keyring || handle_error "Keyring update failed"
}

create_user() {
    if id "$USERNAME" &>/dev/null; then
        log INFO "User $USERNAME exists"
        return
    fi
    
    useradd -m -G wheel -s /bin/bash "$USERNAME" || handle_error "User creation failed"
    log INFO "Created user $USERNAME"
    
    # Set sudo permissions
    echo "%wheel ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/wheel
    chmod 440 /etc/sudoers.d/wheel
}

# ==============================================================================
# 4. PACKAGE MANAGEMENT
# ==============================================================================
install_packages() {
    log INFO "Installing core packages"
    pacman -Syu --noconfirm --needed "${CORE_PACKAGES[@]}" || handle_error "Core package install failed"

# ==============================================================================
# 5. SECURITY CONFIGURATION
# ==============================================================================
harden_ssh() {
    local cfg="/etc/ssh/sshd_config"
    cp "$cfg" "${cfg}.bak"
    
    declare -A settings=(
        ["Port"]="2222"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="no"
        ["Protocol"]="2"
        ["X11Forwarding"]="no"
        ["MaxAuthTries"]="4"
    )
    
    for key in "${!settings[@]}"; do
        sed -i "s/^#*${key}.*/${key} ${settings[$key]}/" "$cfg"
    done
    
    systemctl restart sshd || handle_error "SSH restart failed"
    log INFO "SSH hardened"
}

configure_firewall() {
    local zones=("public" "internal") services=(http https ssh)
    
    systemctl enable --now firewalld || handle_error "Firewalld activation failed"
    
    for zone in "${zones[@]}"; do
        firewall-cmd --permanent --new-zone="$zone"
        firewall-cmd --permanent --zone="$zone" --set-target=DROP
    done
    
    firewall-cmd --permanent --zone=public --add-service=ssh
    firewall-cmd --permanent --zone=internal --add-service={http,https,ssh}
    
    firewall-cmd --reload
    log INFO "Firewalld configured"
}

setup_fail2ban() {
    systemctl enable --now fail2ban
    cat <<EOF > /etc/fail2ban/jail.d/arch.conf
[sshd]
enabled = true
port = 2222
maxretry = 3
bantime = 1h
EOF
    systemctl restart fail2ban
    log INFO "Fail2ban configured"
}

# ==============================================================================
# 6. SYSTEM OPTIMIZATION
# ==============================================================================
configure_journald() {
    mkdir -p /var/log/journal
    sed -i 's/#Storage=auto/Storage=persistent/' /etc/systemd/journald.conf
    systemctl restart systemd-journald
    log INFO "Persistent journal enabled"
}

tune_kernel() {
    cat <<EOF > /etc/sysctl.d/99-arch.conf
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
vm.swappiness = 10
vm.vfs_cache_pressure = 50
EOF
    sysctl --system
    log INFO "Kernel parameters tuned"
}

# ==============================================================================
# 7. SERVICE DEPLOYMENT
# ==============================================================================
setup_zfs() {
    local pool="WD_BLACK" mount="/media/WD_BLACK"
    
    modprobe zfs || handle_error "ZFS module load failed"
    systemctl enable zfs-import-cache zfs-mount zfs-zed
    
    if ! zpool list | grep -q "$pool"; then
        zpool import "$pool" || handle_error "ZFS pool import failed"
    fi
    
    zfs set mountpoint="$mount" "$pool"
    log INFO "ZFS pool $pool mounted at $mount"
}

deploy_services() {
    local services=(
        dunamismax-ai-agents dunamismax-files 
        dunamismax-messenger dunamismax-notes dunamismax-main
    )
    
    for service in "${services[@]}"; do
        cat <<EOF > "/etc/systemd/system/${service}.service"
[Unit]
Description=DunamisMax $service
After=network.target

[Service]
User=$USERNAME
Group=$USERNAME
WorkingDirectory=/home/$USERNAME/github/web/$service
Environment=PATH=/home/$USERNAME/.local/bin:/usr/local/bin:/usr/bin
ExecStart=/usr/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
        systemctl enable "$service"
    done
    
    systemctl daemon-reload
    log INFO "DunamisMax services deployed"
}

# ==============================================================================
# 8. AUTOMATION & FINALIZATION
# ==============================================================================
enable_updates() {
    cat <<EOF > /etc/systemd/system/arch-update.service
[Unit]
Description=Arch Linux Update

[Service]
Type=oneshot
ExecStart=/usr/bin/pacman -Syu --noconfirm
EOF

    cat <<EOF > /etc/systemd/system/arch-update.timer
[Unit]
Description=Daily System Update

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl enable --now arch-update.timer
    log INFO "Automatic updates enabled"
}

finalize() {
    log INFO "Cleaning package cache"
    paccache -rk 2
    
    log INFO "System Information:"
    free -h | awk '/Mem/{print "Memory: " $3 "/" $2}'
    df -h / | awk 'NR==2{print "Disk: " $3 "/" $2}'
    ip -br addr | awk '{print "Network: " $1 ": " $3}'
    
    log INFO "Setup completed successfully"
    echo -e "${GREEN}System ready for reboot${NC}"
}

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
main() {
    [[ $(id -u) -eq 0 ]] || handle_error "Must run as root"
    
    init_arch
    create_user
    install_packages
    
    harden_ssh
    configure_firewall
    setup_fail2ban
    
    configure_journald
    tune_kernel
    
    setup_zfs
    deploy_services
    enable_updates
    
    finalize
}

main "$@"