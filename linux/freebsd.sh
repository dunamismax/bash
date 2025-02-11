Here's the FreeBSD-adapted version of the script with equivalent functionality:

```bash
#!/usr/bin/env sh
################################################################################
# FreeBSD Automated Setup & Hardening Script
################################################################################

# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
set -e
LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"

# Essential Package List (FreeBSD-specific)
PACKAGES="
bash zsh fish vim nano emacs mc neovim screen tmux
gcc gmake cmake meson intltool gettext pigz libtool pkgconf bzip2 xz git hugo
acpid chrony fail2ban sudo bash-completion logrotate net-tools
curl wget tcpdump rsync nmap lynx bind-tools mtr netcat socat
htop neofetch tig jq vnstat tree fzf smartmontools lsof sysstat
gdisk fusefs-ntfs ncdu unzip zip parted lvm2
perl patch bc gawk expect
fd-find bat ripgrep hyperfine cheat
ffmpeg restic mpv
ranger nnn
muttr newsboat irssi weechat httpie youtube_dl
taskwarrior calcurse
asciinema
cowsay figlet
"

# Nord Color Theme (Enhanced)
RED='\033[38;2;191;97;106m'
YELLOW='\033[38;2;235;203;139m'
GREEN='\033[38;2;163;190;140m'
BLUE='\033[38;2;94;129;172m'
NC='\033[0m'

# ==============================================================================
# 2. UTILITY & LOGGING FUNCTIONS
# ==============================================================================
log() {
    level=$(echo "$1" | tr '[:lower:]' '[:upper:]')
    shift
    message="$*"
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    case "$level" in
        INFO) color="${GREEN}" ;;
        WARN*) color="${YELLOW}" ;;
        ERROR) color="${RED}" ;;
        *) color="${NC}" ;;
    esac
    printf "%b[%s] [%s] %s%b\n" "$color" "$timestamp" "$level" "$message" "$NC" | tee -a "$LOG_FILE"
}

warn() { log WARN "$@"; }
die() { log ERROR "$@"; exit 1; }

# ==============================================================================
# 3. SYSTEM PREPARATION FUNCTIONS
# ==============================================================================
ensure_user() {
    if pw usershow "$USERNAME" >/dev/null 2>&1; then
        log INFO "User '$USERNAME' exists"
    else
        log INFO "Creating user '$USERNAME'"
        pw useradd -n "$USERNAME" -m -s /bin/sh -w no || die "Failed to create user"
    fi
}

check_network() {
    if ! ping -c 1 google.com >/dev/null 2>&1; then
        die "No network connectivity"
    else
        log INFO "Network verified"
    fi
}

update_system() {
    log INFO "Updating package repository"
    pkg update -q || die "Failed to update repositories"
    
    log INFO "Upgrading system packages"
    pkg upgrade -y || die "Failed to upgrade packages"
}

# ==============================================================================
# 4. CORE CONFIGURATION FUNCTIONS
# ==============================================================================
configure_ssh() {
    log INFO "Configuring SSH server"
    sysrc sshd_enable=YES
    
    log INFO "Hardening SSH configuration"
    sed -i.bak -e 's/^#PermitRootLogin.*/PermitRootLogin no/' \
               -e 's/^#PasswordAuthentication.*/PasswordAuthentication no/' \
               -e 's/^#PermitEmptyPasswords.*/PermitEmptyPasswords no/' \
               /etc/ssh/sshd_config
    
    service sshd restart || die "Failed to restart SSH"
}

configure_pf() {
    log INFO "Configuring PF firewall"
    sysrc pf_enable=YES
    sysrc pflog_enable=YES
    
    cat > /etc/pf.conf <<EOF
# Public interface
ext_if = "vtnet0"

# Trusted hosts
trusted = "{ 192.168.1.0/24 }"

# Default policies
block all
pass out quick keep state

# SSH
pass in proto tcp to \$ext_if port 22

# Web services
pass in proto tcp to \$ext_if port { 80, 443 }

# Plex Media Server
pass in proto tcp to \$ext_if port 32400
EOF
    
    service pf start || die "Failed to start PF"
}

configure_fail2ban() {
    log INFO "Configuring fail2ban"
    sysrc fail2ban_enable=YES
    service fail2ban start || die "Failed to start fail2ban"
}

install_packages() {
    log INFO "Installing system packages"
    pkg install -y $PACKAGES || die "Failed to install packages"
}

# ==============================================================================
# 5. STORAGE & SERVICES CONFIGURATION
# ==============================================================================
install_plex() {
    log INFO "Installing Plex Media Server"
    pkg install -y plexmediaserver || die "Failed to install Plex"
    
    sysrc plexmediaserver_uid="$USERNAME"
    sysrc plexmediaserver_enable=YES
    service plexmediaserver start || warn "Failed to start Plex"
}

configure_zfs() {
    log INFO "Configuring ZFS"
    kldload zfs || die "Failed to load ZFS kernel module"
    sysrc zfs_enable=YES
    
    if ! zpool list WD_BLACK >/dev/null 2>&1; then
        log INFO "Importing ZFS pool"
        zpool import WD_BLACK || die "Failed to import ZFS pool"
    fi
    
    zfs set mountpoint=/media/WD_BLACK WD_BLACK || warn "Failed to set mountpoint"
}

setup_repos() {
    log INFO "Setting up repositories"
    gh_dir="/home/$USERNAME/github"
    mkdir -p "$gh_dir" || die "Failed to create GitHub directory"
    
    for repo in bash windows web python go misc; do
        repo_dir="$gh_dir/$repo"
        [ -d "$repo_dir" ] && rm -rf "$repo_dir"
        git clone "https://github.com/dunamismax/$repo.git" "$repo_dir" || warn "Failed to clone $repo"
        chown -R "$USERNAME:$USERNAME" "$repo_dir"
    done
}

# ==============================================================================
# 6. DOCKER CONFIGURATION
# ==============================================================================
install_docker() {
    log INFO "Installing Docker"
    pkg install -y docker docker-compose || die "Failed to install Docker"
    
    sysrc docker_enable=YES
    service docker start || die "Failed to start Docker"
    
    pw groupmod docker -m "$USERNAME" || warn "Failed to add user to docker group"
}

# ==============================================================================
# 7. FINALIZATION
# ==============================================================================
configure_periodic() {
    log INFO "Configuring automatic updates"
    echo 'daily_system_updates_enable="YES"' >> /etc/periodic.conf
    echo 'daily_status_security_enable="YES"' >> /etc/periodic.conf
}

final_checks() {
    log INFO "Final system checks"
    log INFO "Kernel version: $(uname -r)"
    log INFO "Storage: $(df -h /)"
    log INFO "Memory: $(sysctl -n hw.physmem)"
}

prompt_reboot() {
    log INFO "Setup complete. Rebooting..."
    shutdown -r now
}

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
main() {
    [ "$(id -u)" -ne 0 ] && die "Must run as root"
    check_network
    update_system
    ensure_user
    install_packages
    configure_ssh
    configure_pf
    configure_fail2ban
    install_plex
    configure_zfs
    setup_repos
    install_docker
    configure_periodic
    final_checks
    prompt_reboot
}

main "$@"
```

Key differences and FreeBSD-specific adaptations:

1. **Package Management**:
   - Replaced `apt` with `pkg`
   - Adjusted package names to FreeBSD conventions (e.g., `docker` instead of `docker.io`)

2. **Firewall**:
   - Replaced `ufw` with PF firewall
   - Added PF configuration with stateful filtering

3. **Service Management**:
   - Using `sysrc` and `service` instead of `systemctl`
   - FreeBSD init system configuration in `/etc/rc.conf`

4. **ZFS**:
   - Native ZFS support with kernel module loading
   - Persistent configuration via rc.conf

5. **Security**:
   - Removed systemd-specific configurations (journald)
   - Used FreeBSD's periodic(8) system for automatic updates

6. **Network Configuration**:
   - Adjusted network interface names (`vtnet0` instead of `eth0`)

7. **User Management**:
   - Using `pw` instead of Linux useradd/groupadd

8. **Kernel Modules**:
   - Explicit ZFS kernel module loading

9. **Logging**:
   - Removed journald configuration in favor of syslogd

10. **Package Selection**:
    - Removed Linux-specific packages (e.g., libvirt-daemon-system)
    - Added FreeBSD equivalents where available

The script maintains the core functionality while adapting to FreeBSD's unique environment. Features like ZFS management, Docker installation, and service configuration have been adjusted to use FreeBSD's native tools and conventions.