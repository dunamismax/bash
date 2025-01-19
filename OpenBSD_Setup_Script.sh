#!/bin/sh
# ------------------------------------------------------------------------------
# Enhanced OpenBSD Automated Setup Script
# ------------------------------------------------------------------------------
# Comprehensive system configuration and hardening:
#  • Full system update and package management
#  • Advanced security hardening and monitoring
#  • Complete development environment setup
#  • Enhanced system service configuration
#  • Desktop environment setup (optional)
#  • Extensive logging and monitoring
#
# Usage:
#  • Run as root: # sh setup.sh [options]
#  • Options: -d for desktop environment setup
#
# Compatibility:
#  • Tested on OpenBSD 7.4
#
# Author: dunamismax | License: MIT
# ------------------------------------------------------------------------------

set -eu

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/setup.log"
VERBOSE=2
USERNAME="sawyer"
TIMEZONE="America/New_York"
DO_DESKTOP=0

# Parse flags
while getopts "d" opt; do
    case "$opt" in
        d) DO_DESKTOP=1 ;;
        *) ;;
    esac
done

# Extended package list with recommended OpenBSD packages
PACKAGES="
acme-client afl-- ansible aria2 asciidoc autoconf automake \
bash bmake chromium cmake coccinelle cppcheck \
curl cyrus-sasl2 dash dbus dmenu docker docker-cli \
emacs entr expect ffmpeg firefox fzf gcc gdb gettext-tools \
git gmake gnupg go graphviz groff htop i3 icdiff \
jq rsync lynx vim nano mc screen tmux nodejs npm ninja-build meson \
libreoffice libtool lldb llvm mariadb-server mercurial \
mosh mozilla-certificate-store mutt nasm ncdu neovim \
nload nmap node nsd opensc openssh-server p5-App-cpanminus \
p7zip pcre2 perl php postgresql-server pstree py3-asn1crypto \
py3-boto3 py3-cryptography py3-django py3-flask py3-jinja2 \
py3-pip py3-requests py3-setuptools py3-sqlalchemy py3-virtualenv \
python3 qemu quirks r rust shellcheck signify smartmontools \
sndiod socat sphinx sqlite3 sslscan tcpdump tor unbound \
unzip valgrind weechat wget wireguard-tools xclip xfce \
xz zsh zstd
"

# Desktop environment packages (optional)
DESKTOP_PACKAGES="
firefox chromium libreoffice gimp mpv vlc \
xfce4 i3 rofi dunst picom feh xterm sakura \
papirus-icon-theme arc-theme
"

# ------------------------------------------------------------------------------
# LOGGING AND ERROR HANDLING
# ------------------------------------------------------------------------------
log() {
    level="$1"
    shift
    message="$*"
    timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    log_entry="[$timestamp] [$level] $message"
    
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$log_entry" >> "$LOG_FILE"
    
    case "$level" in
        ERROR) echo "$log_entry" >&2 ;;
        WARN)  [ "$VERBOSE" -ge 1 ] && echo "$log_entry" >&2 ;;
        INFO)  [ "$VERBOSE" -ge 2 ] && echo "$log_entry" ;;
        DEBUG) [ "$VERBOSE" -ge 3 ] && echo "$log_entry" ;;
    esac
}

error_handler() {
    local line="$1"
    local command="$2"
    log ERROR "Failed at line $line: $command"
    exit 1
}

trap 'error_handler ${LINENO} "${BASH_COMMAND}"' ERR

# ------------------------------------------------------------------------------
# SYSTEM PREPARATION
# ------------------------------------------------------------------------------
prepare_system() {
    log INFO "Preparing system environment..."
    
    # Set timezone
    ln -sf "/usr/share/zoneinfo/$TIMEZONE" /etc/localtime
    
    # Update /etc/installurl to use fastest mirror
    echo "https://cdn.openbsd.org/pub/OpenBSD" > /etc/installurl
    
    # Configure daily system maintenance
    cat > /etc/daily.local << EOF
/usr/sbin/syspatch -c
/usr/sbin/pkg_add -u
/usr/sbin/fw_update
EOF
    chmod 640 /etc/daily.local
    
    log INFO "System preparation completed"
}

# ------------------------------------------------------------------------------
# FULL SYSTEM UPDATE
# ------------------------------------------------------------------------------
update_system() {
    log INFO "Updating system..."
    syspatch
    pkg_add -u
    log INFO "System update completed"
}

# ------------------------------------------------------------------------------
# PACKAGE INSTALLATION
# ------------------------------------------------------------------------------
install_packages() {
    log INFO "Installing packages..."
    for pkg in $PACKAGES; do
        log INFO "Installing $pkg..."
        pkg_add -I "$pkg" || log WARN "Failed to install package: $pkg"
    done
    log INFO "Package installation completed"
}

# ------------------------------------------------------------------------------
# ADVANCED SECURITY CONFIGURATION
# ------------------------------------------------------------------------------
configure_advanced_security() {
    log INFO "Configuring advanced security settings..."
    
    # Enhanced sysctl hardening
    cat >> /etc/sysctl.conf << EOF
# Network security
net.inet.ip.forwarding=0
net.inet.tcp.syncookies=1
net.inet.tcp.drop_synfin=1
net.inet.icmp.bmcastecho=0
net.inet6.ip6.forwarding=0
net.inet.tcp.always_keepalive=1

# Memory protection
kern.stackgap=1
kern.stackgap_random=1
hw.nx=1
kern.allowkmem=0

# File system security
kern.nosuidcoredump=1
kern.seminfo.semmni=1024
kern.seminfo.semmns=4096
kern.shminfo.shmmax=67108864
kern.shminfo.shmall=32768

# Restrict dmesg
kern.dmesg.restrict=1

# Enhanced security features
kern.watchdog.period=32
kern.splassert=2
kern.maxclusters=32768
kern.maxproc=4096
kern.maxfiles=102400
EOF

    # Enhanced PF configuration
    cat > /etc/pf.conf << EOF
# Macros
ext_if = "egress"
tcp_services = "{ ssh, domain, http, https }"
udp_services = "{ domain }"
icmp_types = "{ echoreq, unreach }"

# Options
set skip on lo
set block-policy drop
set loginterface \$ext_if
set state-policy if-bound
set optimization aggressive

# Queueing
queue rootq on \$ext_if bandwidth 100M max 100M
queue standard parent rootq bandwidth 40% priority 3
queue bulk parent rootq bandwidth 60% priority 1

# Normalization
match in all scrub (no-df random-id max-mss 1440)
match out all scrub (no-df random-id reassemble tcp)

# Blocking
block in quick from urpf-failed
block in all
block out all

# Rules
pass out quick inet proto tcp modulate state flags S/SA
pass out quick inet proto { udp, icmp } keep state

# Allow SSH with rate limiting
pass in on \$ext_if inet proto tcp to any port ssh \\
    flags S/SA modulate state \\
    (max-src-conn 100, max-src-conn-rate 15/5, \\
     overload <bruteforce> flush global)

# Allow other services
pass in on \$ext_if inet proto tcp to any port \$tcp_services
pass in on \$ext_if inet proto udp to any port \$udp_services
pass in inet proto icmp all icmp-type \$icmp_types

# Block bruteforce attempts
table <bruteforce> persist
block quick from <bruteforce>
EOF
    pfctl -f /etc/pf.conf
    rcctl enable pf

    # Configure SSH with enhanced security
    cat > /etc/ssh/sshd_config << EOF
Protocol 2
PermitRootLogin no
PasswordAuthentication yes
PubkeyAuthentication yes
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitUserEnvironment no
PermitTunnel no
MaxStartups 3:50:10
TCPKeepAlive yes
ClientAliveInterval 300
ClientAliveCountMax 3
UseDNS no
PrintMotd yes
Compression no
StrictModes yes
MaxSessions 2
EOF
    rcctl restart sshd

    # Configure daily security checks
    cat > /etc/security.local << EOF
#!/bin/sh
# Daily security checks
/usr/bin/syspatch -c
/usr/sbin/pkg_add -u
/usr/sbin/fw_update
/bin/ls -la /etc/ssh/ssh_host_* 
/usr/bin/find / -xdev -type f \\( -perm -4000 -o -perm -2000 \\) -ls
EOF
    chmod 750 /etc/security.local

    # Configure Pledge and Unveil in rc.conf.local for services (example)
    cat >> /etc/rc.conf.local << EOF
httpd_flags="-u"
nsd_flags="-u"
smtpd_flags="-u"
sndiod_flags="-u"
EOF

    # Enhance login.conf for security defaults
    cat >> /etc/login.conf << 'EOF'
default:\
        :path=/usr/bin /bin /usr/sbin /sbin /usr/X11R6/bin /usr/local/bin /usr/local/sbin:\
        :umask=027:\
        :datasize-max=512M:\
        :datasize-cur=512M:\
        :maxproc-max=256:\
        :maxproc-cur=128:\
        :openfiles-cur=512:\
        :stacksize-cur=4M:\
        :tc=auth-defaults:

auth-defaults:\
        :auth=passwd,skey:\
        :auth-ssh=passwd,skey:\
        :auth-ftp=passwd,skey:\
        :passwordtime=180d:\
        :mixpasswordcase=true:\
        :minpasswordlen=12:\
        :passwordcheck=yes:\
        :tc=auth-bgd:
EOF
    cap_mkdb /etc/login.conf

    log INFO "Advanced security configuration completed"
}

# ------------------------------------------------------------------------------
# ENHANCED DEVELOPMENT ENVIRONMENT
# ------------------------------------------------------------------------------
setup_enhanced_dev_environment() {
    log INFO "Setting up enhanced development environment..."
    
    # Create development directory structure
    install -d -o "$USERNAME" -g wheel -m 750 "/home/$USERNAME/"{github,projects,venv,tmp}
    
    # Configure Python environment
    pkg_add py3-pip py3-virtualenv
    sudo -u "$USERNAME" python3 -m pip install --user \
        pipenv black pylint mypy pytest requests \
        flask django sqlalchemy

    # Configure Go environment
    pkg_add go
    echo 'export GOPATH=$HOME/go' >> "/home/$USERNAME/.profile"
    echo 'export PATH=$PATH:$GOPATH/bin' >> "/home/$USERNAME/.profile"
    
    # Configure Rust
    pkg_add rust cargo
    sudo -u "$USERNAME" cargo install ripgrep fd-find exa bat
    
    # Install additional development tools
    pkg_add vim-9.0.1897-no_x11-perl-python3-ruby git \
        cmake ninja meson autoconf automake libtool \
        pkgconf gmake cppcheck shellcheck

    log INFO "Enhanced development environment setup completed"
}

# ------------------------------------------------------------------------------
# DATABASE SETUP
# ------------------------------------------------------------------------------
setup_databases() {
    log INFO "Setting up databases..."
    
    # PostgreSQL
    pkg_add postgresql-server postgresql-client
    mkdir -p /var/postgresql/data
    chown _postgresql:_postgresql /var/postgresql/data
    sudo -u _postgresql initdb -D /var/postgresql/data -E UTF8
    rcctl enable postgresql
    rcctl start postgresql
    
    # MariaDB/MySQL
    pkg_add mariadb-server mariadb-client
    mysql_install_db
    rcctl enable mysqld
    rcctl start mysqld
    
    # SQLite
    pkg_add sqlite3

    log INFO "Database setup completed"
}

# ------------------------------------------------------------------------------
# WEB SERVER SETUP
# ------------------------------------------------------------------------------
setup_web_server() {
    log INFO "Setting up web server..."
    
    # Install and configure httpd
    pkg_add httpd acme-client
    cat > /etc/httpd.conf << EOF
server "default" {
    listen on * port 80
    root "/htdocs/default"
    location "/.well-known/acme-challenge/*" {
        root "/acme"
        request strip 2
    }
    location * {
        block return 301 "https://\$SERVER_NAME\$REQUEST_URI"
    }
}

server "default" {
    listen on * tls port 443
    root "/htdocs/default"
    tls {
        certificate "/etc/ssl/server.crt"
        key "/etc/ssl/private/server.key"
    }
}
EOF

    mkdir -p /etc/acme
    chmod 700 /etc/acme

    rcctl enable httpd
    rcctl start httpd
    
    log INFO "Web server setup completed"
}

# ------------------------------------------------------------------------------
# MONITORING AND LOGGING
# ------------------------------------------------------------------------------
setup_monitoring() {
    log INFO "Setting up system monitoring..."
    
    pkg_add nload htop systat nmap tcpdump iftop
    rcctl enable accounting
    rcctl start accounting
    
    cat > /etc/newsyslog.conf.local << EOF
/var/log/authlog                        644  7     *    \$M1  Z
/var/log/daemon                         644  7     *    \$M1  Z
/var/log/messages                       644  7     *    \$M1  Z
/var/log/secure                         644  7     *    \$M1  Z
/var/www/logs/access.log                644  7     *    \$M1  Z
/var/www/logs/error.log                 644  7     *    \$M1  Z
EOF

    log INFO "Monitoring setup completed"
}

# ------------------------------------------------------------------------------
# DESKTOP ENVIRONMENT (OPTIONAL)
# ------------------------------------------------------------------------------
setup_desktop() {
    log INFO "Setting up desktop environment..."
    
    pkg_add xorg
    for pkg in $DESKTOP_PACKAGES; do
        pkg_add "$pkg"
    done
    
    # Configure X11 startup for user
    cat > "/home/$USERNAME/.xinitrc" << EOF
#!/bin/sh
xrdb -merge ~/.Xresources
exec i3
EOF
    chmod 644 "/home/$USERNAME/.xinitrc"
    
    mkdir -p "/home/$USERNAME/.config/i3"
    cat > "/home/$USERNAME/.config/i3/config" << EOF
# i3 config
font pango:monospace 8
floating_modifier Mod4
bindsym Mod4+Return exec xterm
bindsym Mod4+d exec dmenu_run
bindsym Mod4+Shift+q kill
bindsym Mod4+Shift+c reload
bindsym Mod4+Shift+r restart
bindsym Mod4+Shift+e exit
EOF

    chown -R "$USERNAME:wheel" "/home/$USERNAME/.config"
    
    log INFO "Desktop environment setup completed"
}

# ------------------------------------------------------------------------------
# SYSTEM OPTIMIZATION
# ------------------------------------------------------------------------------
optimize_system() {
    log INFO "Optimizing system performance..."
    
    # Kernel optimization
    cat >> /etc/sysctl.conf << EOF
# Performance tuning
kern.maxfiles=102400
kern.maxvnodes=262144
kern.bufcachepercent=30
kern.maxproc=4096
EOF

    # Resource limits in login.conf
    cat >> /etc/login.conf << 'EOF'
staff:\
        :datasize-cur=1024M:\
        :datasize-max=8192M:\
        :maxproc-cur=512:\
        :maxproc-max=1024:\
        :openfiles-cur=4096:\
        :openfiles-max=8192:\
        :stacksize-cur=32M:\
        :stacksize-max=64M:
EOF
    cap_mkdb /etc/login.conf

    log INFO "System optimization completed"
}

# ------------------------------------------------------------------------------
# FINALIZE SETUP
# ------------------------------------------------------------------------------
finalize_setup() {
    log INFO "Finalizing system setup..."
    
    syspatch -c
    log INFO "System Information: OpenBSD $(uname -r), $(uname -m) on $(hostname)"
    log INFO "Setup finalization completed"
    log INFO "Please reboot the system to apply all changes"
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------
main() {
    log INFO "Starting Enhanced OpenBSD System Configuration"
    
    prepare_system
    update_system
    install_packages
    configure_advanced_security
    setup_enhanced_dev_environment
    setup_databases
    setup_web_server
    setup_monitoring
    optimize_system

    if [ "$DO_DESKTOP" -eq 1 ]; then
        setup_desktop
    fi
    
    finalize_setup
}

main "$@"